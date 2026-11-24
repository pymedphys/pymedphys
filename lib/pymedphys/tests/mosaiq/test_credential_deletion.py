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

"""Password removal is attempted even when its separate username entry fails."""

from types import SimpleNamespace

from pymedphys._imports import pytest

from pymedphys._mosaiq import credentials


@pytest.mark.parametrize(
    "username_error", [None, RuntimeError("missing username entry")]
)
def test_password_deletion_is_attempted_after_username_error(
    monkeypatch, username_error
):
    calls = []

    def delete(storage, name):
        calls.append((storage, name))
        if name == credentials.USERNAME_KEY and username_error is not None:
            raise username_error

    monkeypatch.setattr(credentials, "keyring", SimpleNamespace(delete_password=delete))
    if username_error is None:
        credentials.delete_credentials("server.example", port=1434, database="test")
    else:
        with pytest.raises(RuntimeError) as error:
            credentials.delete_credentials("server.example", port=1434, database="test")
        assert error.value is username_error

    storage = credentials.get_keyring_storage_name("server.example", 1434, "test")
    assert calls == [(storage, "username"), (storage, "password")]


def test_password_deletion_failure_is_not_silenced(monkeypatch):
    failure = RuntimeError("synthetic backend failure")

    def delete(_storage, name):
        if name == credentials.PASSWORD_KEY:
            raise failure

    monkeypatch.setattr(credentials, "keyring", SimpleNamespace(delete_password=delete))
    with pytest.raises(RuntimeError) as error:
        credentials.delete_credentials("server.example")
    assert error.value is failure
