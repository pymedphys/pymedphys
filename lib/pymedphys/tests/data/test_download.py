# Copyright (C) 2026 Jeff
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
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


def test_a_download_needs_no_tqdm(tmp_path: pathlib.Path, monkeypatch):
    # The text-detection extra downloads its model without tqdm.
    monkeypatch.setattr(download, "_tqdm_installed", lambda: False)
    monkeypatch.setattr(download, "tqdm", None)
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


def test_unsupported_scheme_error_omits_sensitive_url(tmp_path):
    url = "ftp://example.invalid/private-file?token=synthetic-credential"

    with pytest.raises(ValueError, match="Unsupported URL scheme") as error:
        download.download_with_progress(url, tmp_path / "unused.bin")

    assert "synthetic-credential" not in str(error.value)
    assert "private-file" not in str(error.value)
    assert "ftp" in str(error.value)


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


@pytest.mark.usefixtures("no_sleep")
def test_truncated_response_error_omits_sensitive_url(tmp_path, monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda _url, **_kwargs: _FakeResponse(b"short", content_length=100),
    )
    destination = tmp_path / "cached.bin"
    destination.write_bytes(b"previous validated contents")
    url = "https://example.invalid/private-file?token=synthetic-credential"

    with pytest.raises(urllib.error.ContentTooShortError) as error:
        download.download_with_progress(url, destination)

    assert "synthetic-credential" not in str(error.value)
    assert "private-file" not in str(error.value)
    assert "5 of 100 bytes" in str(error.value)
    assert destination.read_bytes() == b"previous validated contents"
    assert _leftovers(tmp_path, "cached.bin") == [destination]


def test_oversized_response_is_rejected_without_replacing_cached_file(
    tmp_path: pathlib.Path, monkeypatch
):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda _url, **_kwargs: _FakeResponse(
            b"more-than-advertised", content_length=3
        ),
    )
    destination = tmp_path / "cached.bin"
    destination.write_bytes(b"previous validated contents")

    with pytest.raises(ValueError, match="exceeded the declared Content-Length"):
        download.download_with_progress(
            "https://example.invalid/cached.bin", destination
        )

    assert destination.read_bytes() == b"previous validated contents"
    assert _leftovers(tmp_path, "cached.bin") == [destination]


def test_negative_declared_size_is_rejected_before_cache_replacement(
    tmp_path: pathlib.Path, monkeypatch
):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda _url, **_kwargs: _FakeResponse(b"", content_length=-1),
    )
    destination = tmp_path / "cached.bin"
    destination.write_bytes(b"old cached data")

    with pytest.raises(ValueError, match="Negative Content-Length"):
        download.download_with_progress(
            "https://example.invalid/cached.bin", destination
        )

    assert destination.read_bytes() == b"old cached data"
    assert _leftovers(tmp_path, "cached.bin") == [destination]


@pytest.mark.parametrize(
    ("content_lengths", "transfer_encodings", "error_message"),
    [
        (("3",), ("chunked",), "Conflicting Content-Length"),
        (("",), ("chunked",), "Conflicting Content-Length"),
        (("3",), ("",), "Conflicting Content-Length"),
        (("3", "7"), (), "Multiple Content-Length"),
        (("3, 7",), (), "Invalid Content-Length"),
        (("",), (), "Invalid Content-Length"),
    ],
)
def test_invalid_http_framing_is_rejected_before_caching(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    content_lengths: tuple[str, ...],
    transfer_encodings: tuple[str, ...],
    error_message: str,
):
    # The real urllib HTTPResponse preserves blank and repeated header lines.
    # Disable proxies so system or CI proxy settings cannot intercept loopback.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    monkeypatch.setattr(urllib.request, "urlopen", opener.open)

    class InvalidResponse(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            for content_length in content_lengths:
                self.send_header("Content-Length", content_length)
            for transfer_encoding in transfer_encodings:
                self.send_header("Transfer-Encoding", transfer_encoding)
            self.end_headers()
            self.wfile.write(b"B\r\nhello world\r\n0\r\n\r\n")

        def log_message(self, format: str, *_args: object) -> None:  # pylint: disable = redefined-builtin
            # Suppress the test-only HTTP server's request logging.
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), InvalidResponse)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    destination = tmp_path / "cache.bin"
    destination.write_bytes(b"previously cached content")
    try:
        with pytest.raises(ValueError, match=error_message):
            download.download_with_progress(
                f"http://127.0.0.1:{server.server_port}/bad",
                destination,
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert destination.read_bytes() == b"previously cached content"
    assert _leftovers(tmp_path, "cache.bin") == [destination]


def test_data_directory_can_be_overridden(tmp_path: pathlib.Path, monkeypatch):
    override = tmp_path / "nested" / "data"
    monkeypatch.setenv("PYMEDPHYS_DATA_DIR", str(override))

    assert download.get_data_dir() == override
    assert override.is_dir()


@pytest.mark.usefixtures("no_sleep")
def test_retry_diagnostics_do_not_disclose_exception_details(capsys):
    """Sensitive URL query parameters from failed downloads never reach stdout."""
    signed_url = "https://example.invalid/data?token=synthetic-secret-value"
    attempts = []

    @retry.retry(urllib.error.URLError, tries=2, delay=0)
    def fail_once():
        attempts.append(1)
        if len(attempts) == 1:
            raise urllib.error.URLError(signed_url)
        return "recovered"

    assert fail_once() == "recovered"
    assert len(attempts) == 2
    output = capsys.readouterr().out
    assert "URLError, Retrying in 0 seconds" in output
    assert signed_url not in output
    assert "synthetic-secret-value" not in output


@pytest.mark.usefixtures("no_sleep")
def test_retry_logger_receives_only_safe_exception_metadata():
    """A supplied logger must not receive sensitive exception text either."""
    from unittest.mock import Mock

    logger = Mock()
    secret = "synthetic-password-not-for-logs"
    attempts = []

    @retry.retry(ConnectionError, tries=2, delay=0, logger=logger)
    def fail_once():
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError(secret)
        return "ok"

    assert fail_once() == "ok"
    logger.warning.assert_called_once_with("ConnectionError, Retrying in 0 seconds...")
    assert secret not in str(logger.warning.call_args)


@pytest.mark.usefixtures("no_sleep")
def test_retry_http_status_does_not_disclose_url_or_reason(capsys):
    """An HTTP retry retains the numeric status but not sensitive text."""
    signed_url = "https://example.invalid/data?token=synthetic-secret-value"
    attempts = []

    @retry.retry(urllib.error.URLError, tries=2, delay=0)
    def fail_once():
        attempts.append(1)
        if len(attempts) == 1:
            raise urllib.error.HTTPError(
                signed_url, 503, "private reason: synthetic-secret-value", None, None
            )
        return "recovered"

    assert fail_once() == "recovered"
    assert len(attempts) == 2
    output = capsys.readouterr().out
    assert output == "HTTPError 503, Retrying in 0 seconds...\n"
    assert signed_url not in output
    assert "synthetic-secret-value" not in output


@pytest.mark.usefixtures("no_sleep")
def test_retry_http_status_is_safe_with_injected_logger():
    """The logger receives the HTTP status without an exception message."""
    from unittest.mock import Mock

    logger = Mock()
    signed_url = "https://example.invalid/data?token=synthetic-secret-value"
    attempts = []

    @retry.retry(urllib.error.URLError, tries=2, delay=0, logger=logger)
    def fail_once():
        attempts.append(1)
        if len(attempts) == 1:
            raise urllib.error.HTTPError(
                signed_url, 429, "private reason: synthetic-secret-value", None, None
            )
        return "recovered"

    assert fail_once() == "recovered"
    assert len(attempts) == 2
    logger.warning.assert_called_once_with("HTTPError 429, Retrying in 0 seconds...")
    assert signed_url not in str(logger.warning.call_args)
    assert "synthetic-secret-value" not in str(logger.warning.call_args)
