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

"""Offline checks of the data download helper."""

import email.message
import io
import pathlib
import urllib.error
import urllib.request

from pymedphys._imports import pytest

from pymedphys._data import download, retry


class _FakeResponse(io.BytesIO):
    """A minimal stand-in for the object ``urllib.request.urlopen`` returns."""

    def __init__(self, payload: bytes, content_length: int | None = None):
        super().__init__(payload)
        self.headers = email.message.Message()
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)


class _FailingResponse(_FakeResponse):
    """A response whose connection drops after the first chunk."""

    def read(self, size: int | None = -1) -> bytes:  # pylint: disable = unused-argument
        if self.tell() > 0:
            raise ConnectionResetError("connection dropped mid-download")
        return super().read(4)


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(retry.time, "sleep", lambda _: None)


def _leftovers(directory: pathlib.Path, name: str):
    return [path for path in directory.iterdir() if name in path.name]


def test_file_url_is_copied(tmp_path: pathlib.Path):
    source = tmp_path / "source.bin"
    payload = bytes(range(256)) * 4
    source.write_bytes(payload)
    destination = tmp_path / "destination.bin"

    download.download_with_progress(source.as_uri(), destination)

    assert destination.read_bytes() == payload


@pytest.mark.parametrize("url", ["ftp://example.invalid/data.zip", "data:,hello"])
def test_unsupported_scheme_is_rejected(url: str, tmp_path: pathlib.Path):
    destination = tmp_path / "unused.bin"

    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        download.download_with_progress(url, destination)

    assert not destination.exists()


def test_download_uses_a_timeout(tmp_path: pathlib.Path, monkeypatch):
    seen = {}

    def fake_urlopen(_url, timeout=None):
        seen["timeout"] = timeout
        return _FakeResponse(b"payload", content_length=7)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    download.download_with_progress("https://example.invalid/a.bin", tmp_path / "a.bin")

    assert seen["timeout"] == download.DOWNLOAD_TIMEOUT_SECONDS
    assert (tmp_path / "a.bin").read_bytes() == b"payload"


@pytest.mark.usefixtures("no_sleep")
def test_not_found_is_not_retried(tmp_path: pathlib.Path, monkeypatch):
    calls = []

    def fake_urlopen(url, **_kwargs):
        calls.append(url)
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(urllib.error.HTTPError):
        download.download_with_progress(
            "https://example.invalid/missing.bin", tmp_path / "missing.bin"
        )

    assert len(calls) == 1


@pytest.mark.usefixtures("no_sleep")
def test_transient_error_is_retried(tmp_path: pathlib.Path, monkeypatch):
    calls = []

    def fake_urlopen(url, **_kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.URLError("temporary failure in name resolution")
        return _FakeResponse(b"second time lucky")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    destination = tmp_path / "retried.bin"
    download.download_with_progress("https://example.invalid/retried.bin", destination)

    assert len(calls) == 2
    assert destination.read_bytes() == b"second time lucky"


@pytest.mark.usefixtures("no_sleep")
def test_interrupted_download_leaves_nothing_behind(
    tmp_path: pathlib.Path, monkeypatch
):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda _url, **_kwargs: _FailingResponse(b"0123456789" * 100),
    )

    destination = tmp_path / "interrupted.bin"
    with pytest.raises(ConnectionResetError):
        download.download_with_progress(
            "https://example.invalid/interrupted.bin", destination
        )

    assert _leftovers(tmp_path, "interrupted.bin") == []


@pytest.mark.usefixtures("no_sleep")
def test_truncated_response_is_rejected(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda _url, **_kwargs: _FakeResponse(b"short", content_length=100),
    )

    destination = tmp_path / "truncated.bin"
    with pytest.raises(urllib.error.ContentTooShortError):
        download.download_with_progress(
            "https://example.invalid/truncated.bin", destination
        )

    assert _leftovers(tmp_path, "truncated.bin") == []


def test_data_directory_can_be_overridden(tmp_path: pathlib.Path, monkeypatch):
    override = tmp_path / "nested" / "data"
    monkeypatch.setenv("PYMEDPHYS_DATA_DIR", str(override))

    assert download.get_data_dir() == override
    assert override.is_dir()
