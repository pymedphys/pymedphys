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

"""Check that each pinned text detection model can be downloaded and has
its pinned SHA-256 (D-056).

Vetting a model checks that CI can download the weights it pins. The
``Text Detection Model Pins`` workflow runs this module on a GitHub-hosted
runner, as ``python -m pymedphys._dicom.deidentify.text_evaluation_model_pins``:
for each pin in :data:`CHECKED_PINS`, it downloads the file at the pin's URL
into memory, never to disk, and prints one row: the URL, its host, the
file's size in bytes, and whether its SHA-256 is the pinned one, and, for a
model inside a wheel, whether the model's is too. A download that fails is
reported as ``unreachable`` by its kind alone, with no message. It exits 1
unless every pin matches. Nothing is cached, kept, or run.
"""

from __future__ import annotations

import dataclasses
import hashlib
import http.client
import io
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from typing import BinaryIO

from .text_detection import PP_OCRV6_DET_SMALL, PinnedModel
from .text_evaluation_models import ModelFile

# The most bytes a pinned file may have: more is reported, not read on.
MAX_BYTES = 512 * 1024 * 1024
ATTEMPTS = 3
TIMEOUT_SECONDS = 60
USER_AGENT = "pymedphys-text-detection-model-pins"

# Each result's code: the file has its pinned SHA-256 (and, in a wheel, so
# does the model); it does not; it is larger than MAX_BYTES; the wheel does
# not hold the model; or the download failed.
MATCH = "match"
MISMATCH = "mismatch"
TOO_LARGE = "too-large"
MEMBER_MISSING = "member-missing"
UNREACHABLE = "unreachable"


@dataclasses.dataclass(frozen=True)
class CheckedPin:
    """A pin whose download is checked.

    Attributes
    ----------
    label : str
        What the check calls it.
    source : PinnedModel or ModelFile
    """

    label: str
    source: PinnedModel | ModelFile


# Today's model, from the wheel that a run takes it from, and from the
# ModelScope file that the same wheel's default_models.yaml lists for it
# with the same SHA-256. Candidates join as their pins are vetted.
CHECKED_PINS: tuple[CheckedPin, ...] = (
    CheckedPin("PP-OCRv6 small (RapidOCR wheel on PyPI)", PP_OCRV6_DET_SMALL),
    CheckedPin(
        "PP-OCRv6 small (ModelScope)",
        ModelFile(
            url=(
                "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/"
                "v3.10.0/onnx/PP-OCRv6/det/PP-OCRv6_det_small.onnx"
            ),
            sha256=PP_OCRV6_DET_SMALL.member_sha256,
        ),
    ),
)


@dataclasses.dataclass(frozen=True)
class PinResult:
    """What the check found of one pin: no message, value, or content.

    Attributes
    ----------
    label, url, host : str
    size : int or None
        The bytes downloaded; None where the download failed.
    result : str
        One of the codes above.
    failure : str or None
        For ``unreachable``, the kind of failure: ``http-<status>``,
        ``url-error``, ``timeout``, or ``connection``.
    """

    label: str
    url: str
    host: str
    size: int | None
    result: str
    failure: str | None = None


Opener = Callable[[urllib.request.Request, float], BinaryIO]


def _open(request: urllib.request.Request, timeout: float) -> BinaryIO:
    # Only the https URLs that pins allow are opened.
    return urllib.request.urlopen(request, timeout=timeout)  # nosec B310


def check_pin(
    pin: CheckedPin,
    *,
    opener: Opener = _open,
    attempts: int = ATTEMPTS,
    pause: Callable[[float], None] = time.sleep,
) -> PinResult:
    """Download one pin's file into memory and check its SHA-256s."""
    source = pin.source
    host = urllib.parse.urlsplit(source.url).hostname or ""
    failure = "url-error"
    for attempt in range(attempts):
        if attempt:
            pause(2.0**attempt)
        try:
            content = _download(source.url, opener)
        except _TooLarge as large:
            return PinResult(pin.label, source.url, host, large.size, TOO_LARGE)
        except urllib.error.HTTPError as error:
            failure = f"http-{error.code}"
            if error.code < 500 and error.code != 429:
                break
            continue
        except TimeoutError:
            failure = "timeout"
            continue
        except urllib.error.URLError:
            failure = "url-error"
            continue
        except (ConnectionError, http.client.HTTPException):
            failure = "connection"
            continue
        return PinResult(
            pin.label, source.url, host, len(content), _result(source, content)
        )
    return PinResult(pin.label, source.url, host, None, UNREACHABLE, failure)


class _TooLarge(Exception):
    def __init__(self, size: int):
        super().__init__()
        self.size = size


def _download(url: str, opener: Opener) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    buffer = io.BytesIO()
    with opener(request, TIMEOUT_SECONDS) as response:
        while chunk := response.read(1024 * 1024):
            buffer.write(chunk)
            if buffer.tell() > MAX_BYTES:
                raise _TooLarge(buffer.tell())
    return buffer.getvalue()


def _result(source: PinnedModel | ModelFile, content: bytes) -> str:
    if _sha256(content) != source.sha256:
        return MISMATCH
    if isinstance(source, ModelFile):
        return MATCH
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as wheel:
            member = wheel.read(source.member)
    except (KeyError, zipfile.BadZipFile):
        return MEMBER_MISSING
    return MATCH if _sha256(member) == source.member_sha256 else MISMATCH


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def markdown(results: Sequence[PinResult]) -> str:
    """The results as a CommonMark table."""
    lines = [
        "# Text detection model pins",
        "",
        "| Pin | URL | Host | Bytes | SHA-256 |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for each in results:
        result = (
            each.result if each.failure is None else f"{each.result} ({each.failure})"
        )
        size = "none" if each.size is None else str(each.size)
        lines.append(
            f"| {each.label} | <{each.url}> | {each.host} | {size} | {result} |"
        )
    return "\n".join(lines) + "\n"


def main(pins: Sequence[CheckedPin] = CHECKED_PINS, **options) -> int:
    """Check every pin and print the table; 0 only where every pin matches."""
    results = [check_pin(pin, **options) for pin in pins]
    sys.stdout.write(markdown(results))
    return 0 if all(each.result == MATCH for each in results) else 1


if __name__ == "__main__":
    sys.exit(main())
