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

"""The check that each pinned model downloads with its pinned SHA-256.

Every download here is served from memory; nothing reaches the network."""

import hashlib
import io
import urllib.error
import urllib.parse
import zipfile


from pymedphys._dicom.deidentify import text_detection
from pymedphys._dicom.deidentify import text_evaluation_model_pins as pins
from pymedphys._dicom.deidentify.text_detection import PinnedModel
from pymedphys._dicom.deidentify.text_evaluation_models import PADDLE_FILES, ModelFile

MODEL = b"an invented model"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _wheel(members):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as wheel:
        for name, content in members.items():
            wheel.writestr(name, content)
    return data.getvalue()


def _serving(*responses, requests=None):
    """An opener that gives each response in turn: bytes are served, an
    exception raised."""
    queue = list(responses)

    def opener(request, timeout):
        assert timeout > 0
        if requests is not None:
            requests.append(request)
        response = queue.pop(0)
        if isinstance(response, BaseException):
            raise response
        return io.BytesIO(response)

    return opener


def _file_pin(content=MODEL):
    return pins.CheckedPin(
        "invented",
        ModelFile("https://models.example.org/det.onnx", _sha256(content)),
    )


def _check(pin, *responses, **options):
    return pins.check_pin(
        pin, opener=_serving(*responses, **options), pause=lambda _: None
    )


def test_a_file_with_its_pinned_digest_matches():
    requests = []
    found = _check(_file_pin(), MODEL, requests=requests)
    assert found == pins.PinResult(
        "invented",
        "https://models.example.org/det.onnx",
        "models.example.org",
        len(MODEL),
        pins.MATCH,
    )
    assert requests[0].get_header("User-agent") == pins.USER_AGENT


def test_a_file_without_its_pinned_digest_does_not():
    assert _check(_file_pin(), MODEL + b"changed").result == pins.MISMATCH


def test_a_wheel_and_its_model_are_each_checked():
    wheel = _wheel({"models/det.onnx": MODEL})
    pin = pins.CheckedPin(
        "wheel",
        PinnedModel(
            url="https://files.example.org/invented-1.0-py3-none-any.whl",
            sha256=_sha256(wheel),
            member="models/det.onnx",
            member_sha256=_sha256(MODEL),
        ),
    )
    assert _check(pin, wheel).result == pins.MATCH
    other = _wheel({"models/det.onnx": MODEL + b"changed"})
    changed = pins.CheckedPin(
        "wheel",
        PinnedModel(pin.source.url, _sha256(other), "models/det.onnx", _sha256(MODEL)),
    )
    assert _check(changed, other).result == pins.MISMATCH
    empty = _wheel({"other.txt": b""})
    missing = pins.CheckedPin(
        "wheel",
        PinnedModel(pin.source.url, _sha256(empty), "models/det.onnx", _sha256(MODEL)),
    )
    assert _check(missing, empty).result == pins.MEMBER_MISSING


def test_transient_failures_are_retried_and_others_are_not():
    server_error = urllib.error.HTTPError("u", 503, "m", None, None)  # type: ignore[arg-type]
    assert _check(_file_pin(), server_error, MODEL).result == pins.MATCH
    not_found = urllib.error.HTTPError("u", 404, "m", None, None)  # type: ignore[arg-type]
    found = _check(_file_pin(), not_found)
    assert (found.result, found.failure, found.size) == (
        pins.UNREACHABLE,
        "http-404",
        None,
    )
    refused = urllib.error.URLError("SECRET reason")
    found = _check(_file_pin(), refused, TimeoutError(), ConnectionResetError())
    assert (found.result, found.failure) == (pins.UNREACHABLE, "connection")


def test_a_file_larger_than_the_limit_is_not_read_on(monkeypatch):
    monkeypatch.setattr(pins, "MAX_BYTES", 4)
    found = _check(_file_pin(), MODEL)
    assert found.result == pins.TOO_LARGE
    assert found.size is not None and found.size > 4


def test_the_table_gives_only_url_host_size_and_result(capsys):
    refused = urllib.error.URLError("SECRET reason")
    code = pins.main(
        [_file_pin(), _file_pin(b"other")],
        opener=_serving(MODEL, refused, refused, refused),
        pause=lambda _: None,
    )
    page = capsys.readouterr().out
    assert code == 1
    assert "| invented | <https://models.example.org/det.onnx> |" in page
    assert f"| {len(MODEL)} | match |" in page
    assert "| none | unreachable (url-error) |" in page
    assert "SECRET" not in page
    assert pins.main([_file_pin()], opener=_serving(MODEL)) == 0
    for line in page.splitlines():
        assert line == line.rstrip()


def test_todays_model_and_each_paddle_file_are_checked():
    sources = [pin.source for pin in pins.CHECKED_PINS]
    assert text_detection.PP_OCRV6_DET_SMALL in sources
    files = [source for source in sources if isinstance(source, ModelFile)]
    assert files == list(PADDLE_FILES.values())
    # RapidOCR's conversion of today's model on ModelScope is the very
    # file inside the wheel.
    assert (
        PADDLE_FILES["RapidOCR PP-OCRv6 small"].sha256
        == text_detection.PP_OCRV6_DET_SMALL.member_sha256
    )
    hosts = {urllib.parse.urlsplit(source.url).hostname for source in files}
    assert hosts == {"huggingface.co", "www.modelscope.cn"}
    assert len({source.sha256 for source in files}) == len(files)
    assert len({pin.label for pin in pins.CHECKED_PINS}) == len(pins.CHECKED_PINS)
