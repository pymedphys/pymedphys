# Copyright (C) 2026 Jeff

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Noise before a frame must not grow the receive buffer without a bound."""

import re
from types import SimpleNamespace

from pymedphys._imports import pytest

from pymedphys._icom import listener


class StopListening(Exception):
    pass


def _receive(chunks, tmp_path, monkeypatch):
    sizes = []
    saved = []
    real_pattern = re.compile(rb"\d\d\d\d-\d\d-\d\d\d\d:\d\d:\d\d")

    class Pattern:
        def finditer(self, data):
            sizes.append(len(data))
            return real_pattern.finditer(data)

    class Socket:
        def __init__(self):
            self.chunks = iter(chunks)
            self.closed = False

        def recv(self, _size):
            try:
                return next(self.chunks)
            except StopIteration:
                raise StopListening from None

        def close(self):
            self.closed = True

    sock = Socket()
    monkeypatch.setattr(listener, "re", SimpleNamespace(compile=lambda _: Pattern()))
    monkeypatch.setattr(listener, "initialise_socket", lambda _: sock)
    monkeypatch.setattr(
        listener, "save_an_icom_batch", lambda _, __, data: saved.append(data)
    )
    monkeypatch.setattr(
        listener.patients,
        "PatientIcomData",
        lambda _: SimpleNamespace(
            update_data=lambda *args: None,
        ),
    )

    with pytest.raises(StopListening):
        listener.listen("192.0.2.1", tmp_path)
    assert sock.closed
    return sizes, saved


def test_unframed_data_retains_only_a_possible_split_header(tmp_path, monkeypatch):
    sizes, saved = _receive([b"x" * 256] * 100, tmp_path, monkeypatch)
    assert max(sizes) <= 256 + 25
    assert saved == []


@pytest.mark.parametrize("split", range(1, 26))
def test_valid_header_survives_every_receive_boundary(tmp_path, monkeypatch, split):
    first = b"\x00" * 8 + b"2026-01-0100:00:00" + b"\x00payload"
    second = b"\x00" * 8 + b"2026-01-0100:00:01" + b"\x01tail"
    _, saved = _receive(
        [b"x" * 256, b"x" * 256, first[:split], first[split:], second],
        tmp_path,
        monkeypatch,
    )
    assert saved == [first]
