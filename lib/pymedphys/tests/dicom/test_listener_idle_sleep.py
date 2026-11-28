# Copyright (C) 2026 Jeffrey D. Cooney
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The listener's foreground loop yields CPU time while serving DICOM."""

import importlib
from types import SimpleNamespace

from pymedphys._imports import pytest


def test_listener_does_not_spin_in_foreground(monkeypatch, tmp_path):
    listen = importlib.import_module("pymedphys._dicom.connect.listen")
    started = []
    sleeps = []

    class FakeListener:
        def __init__(self, **kwargs):
            self.port = kwargs["port"]

        def start(self):
            started.append(True)

        def stop(self):
            pass

    class EndTest(Exception):
        pass

    def sleep(seconds):
        sleeps.append(seconds)
        raise EndTest

    monkeypatch.setattr(listen, "DicomListener", FakeListener)
    monkeypatch.setattr(listen.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(listen.time, "sleep", sleep)

    arguments = SimpleNamespace(
        host="127.0.0.1",
        port=11112,
        aetitle="TEST",
        storage_directory=tmp_path,
    )

    with pytest.raises(EndTest):
        listen.listen_cli(arguments)

    assert started == [True]
    assert sleeps == [1]
