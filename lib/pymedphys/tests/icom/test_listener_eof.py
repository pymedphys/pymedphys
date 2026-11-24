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

"""A closed iCOM socket must leave the receive loop without spinning."""

from pymedphys._imports import pytest

from pymedphys._icom import listener


@pytest.mark.parametrize("prefix", [b"", b"unfinished stream"])
def test_remote_close_stops_listening_and_closes_socket(tmp_path, monkeypatch, prefix):
    class ClosedSocket:
        def __init__(self):
            self.responses = [prefix, b""] if prefix else [b""]
            self.closed = False

        def recv(self, _size):
            assert self.responses, "receive loop continued after remote EOF"
            return self.responses.pop(0)

        def close(self):
            self.closed = True

    connection = ClosedSocket()
    monkeypatch.setattr(listener, "initialise_socket", lambda _ip: connection)

    with pytest.raises(ConnectionError, match="closed"):
        listener.listen("192.0.2.1", tmp_path)

    assert connection.closed
    assert not list(tmp_path.rglob("*.txt"))
