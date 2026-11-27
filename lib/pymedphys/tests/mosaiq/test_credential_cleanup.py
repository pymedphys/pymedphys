# Copyright (C) 2026 Jeffrey D. Cooney

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Credential cleanup must never retain a password for a missing username."""

from types import SimpleNamespace

from pymedphys._imports import pytest
from pymedphys._mosaiq import credentials


class MissingPassword(Exception):
    pass


def test_delete_credentials_removes_password_when_username_is_absent(monkeypatch):
    stored = {credentials.PASSWORD_KEY: "synthetic-secret"}
    attempts = []

    def delete_password(_service, key):
        attempts.append(key)
        if key not in stored:
            raise MissingPassword(key)
        del stored[key]

    monkeypatch.setattr(
        credentials,
        "keyring",
        SimpleNamespace(
            delete_password=delete_password,
            errors=SimpleNamespace(PasswordDeleteError=MissingPassword),
        ),
    )

    credentials.delete_credentials("test-host")
    assert stored == {}
    assert attempts == [credentials.USERNAME_KEY, credentials.PASSWORD_KEY]

    # An already-cleared keyring should also be safe to clear again.
    credentials.delete_credentials("test-host")
    assert stored == {}


def test_delete_credentials_does_not_swallow_backend_failures(monkeypatch):
    def failing_delete(_service, _key):
        raise RuntimeError("keyring unavailable")

    monkeypatch.setattr(
        credentials,
        "keyring",
        SimpleNamespace(
            delete_password=failing_delete,
            errors=SimpleNamespace(PasswordDeleteError=MissingPassword),
        ),
    )

    with pytest.raises(RuntimeError, match="keyring unavailable"):
        credentials.delete_credentials("test-host")
