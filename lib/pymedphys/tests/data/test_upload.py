# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Offline checks of the Zenodo upload helper's authentication."""

import dataclasses
import hashlib

from pymedphys._imports import pytest

from pymedphys._data import upload

URL = "https://zenodo.org/api/deposit/depositions"


@dataclasses.dataclass
class _Response:
    status_code: int
    payload: dict = dataclasses.field(default_factory=dict)

    def json(self):
        return self.payload


class _FakeRequests:
    """Records each call and answers with the queued responses in turn."""

    def __init__(self, *responses: _Response):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def _call(self, method, url, **kwargs):
        files = kwargs.get("files") or {}
        sent = {}
        for key, value in files.items():
            content = value[1] if isinstance(value, tuple) else value
            sent[key] = content.read() if hasattr(content, "read") else content
        self.calls.append({"method": method, "url": url, "sent": sent, **kwargs})
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        return self._call("get", url, **kwargs)

    def post(self, url, **kwargs):
        return self._call("post", url, **kwargs)

    def put(self, url, **kwargs):
        return self._call("put", url, **kwargs)

    def delete(self, url, **kwargs):
        return self._call("delete", url, **kwargs)


class _FakeKeyring:
    def __init__(self):
        self.deleted: list[tuple[str, str]] = []

    def delete_password(self, service, hostname):
        self.deleted.append((service, hostname))


@pytest.fixture(name="zenodo")
def fixture_zenodo(monkeypatch):
    tokens = iter(["first-token", "second-token", "third-token", "fourth-token"])
    monkeypatch.setattr(upload, "get_zenodo_access_token", lambda _: next(tokens))
    fake_keyring = _FakeKeyring()
    monkeypatch.setattr(upload, "keyring", fake_keyring)

    def install(*responses):
        fake_requests = _FakeRequests(*responses)
        monkeypatch.setattr(upload, "requests", fake_requests)
        return fake_requests

    return install, fake_keyring


def test_token_is_sent_in_a_header_not_the_url(zenodo):
    install, _ = zenodo
    fake_requests = install(_Response(201))
    original_headers = dict(upload.HEADERS)

    upload.zenodo_api_with_helpful_fallback(
        URL, "post", json={}, headers=upload.HEADERS
    )

    (call,) = fake_requests.calls
    assert call["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer first-token",
    }
    assert "params" not in call
    assert "token" not in call["url"]
    assert upload.HEADERS == original_headers


@pytest.mark.parametrize("status_code", [401, 403])
def test_rejected_token_is_replaced_and_the_request_retried(zenodo, status_code):
    install, fake_keyring = zenodo
    fake_requests = install(_Response(status_code), _Response(202))

    response = upload.zenodo_api_with_helpful_fallback(URL, "put", data="{}")

    assert response.status_code == 202
    assert [(call["method"], call["url"]) for call in fake_requests.calls] == [
        ("put", URL),
        ("put", URL),
    ]
    assert fake_requests.calls[1]["headers"]["Authorization"] == "Bearer second-token"
    assert fake_requests.calls[1]["data"] == "{}"
    assert fake_keyring.deleted == [("Zenodo", "zenodo.org")]


def test_repeated_rejection_stops_asking_for_tokens(zenodo):
    install, fake_keyring = zenodo
    fake_requests = install(*[_Response(401)] * upload.MAX_TOKEN_ATTEMPTS)

    with pytest.raises(PermissionError, match="Zenodo rejected"):
        upload.zenodo_api_with_helpful_fallback(URL, "get")

    assert len(fake_requests.calls) == upload.MAX_TOKEN_ATTEMPTS
    assert len(fake_keyring.deleted) == upload.MAX_TOKEN_ATTEMPTS


def test_file_is_sent_in_full_when_the_upload_is_retried(zenodo, tmp_path):
    install, _ = zenodo
    filepath = tmp_path / "data.zip"
    content = b"archive contents"
    filepath.write_bytes(content)
    checksum = hashlib.md5(content, usedforsecurity=False).hexdigest()
    fake_requests = install(_Response(401), _Response(201, {"checksum": checksum}))

    upload.upload_filepaths([filepath], deposition_id=1)

    assert [call["sent"]["file"] for call in fake_requests.calls] == [content] * 2
    assert fake_requests.calls[1]["data"] == {"name": "data.zip"}
