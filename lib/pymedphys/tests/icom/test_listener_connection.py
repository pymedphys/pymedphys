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

"""Connection failures must not retain sockets or wait without a timeout."""

from pymedphys._imports import pytest

from pymedphys._icom import listener


@pytest.mark.parametrize("failure", [None, OSError("synthetic refusal")])
def test_socket_timeout_precedes_connect_and_failed_socket_is_closed(
    monkeypatch, failure
):
    class Socket:
        def __init__(self):
            self.events = []

        def settimeout(self, value):
            self.events.append(("timeout", value))

        def connect(self, address):
            self.events.append(("connect", address))
            if failure is not None:
                raise failure

        def close(self):
            self.events.append(("close",))

    sock = Socket()
    monkeypatch.setattr(listener.socket, "socket", lambda *args: sock)

    if failure is None:
        assert listener.initialise_socket("192.0.2.1") is sock
    else:
        with pytest.raises(OSError) as error:
            listener.initialise_socket("192.0.2.1")
        assert error.value is failure

    assert sock.events[:2] == [("timeout", 10), ("connect", ("192.0.2.1", 1706))]
    assert (("close",) in sock.events) is (failure is not None)
