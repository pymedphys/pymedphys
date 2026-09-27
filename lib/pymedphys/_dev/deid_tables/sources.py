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

"""Read a source file of the standard only when it matches its pinned digest."""

from __future__ import annotations

import hashlib
import pathlib
import re

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


class SourceDigestError(ValueError):
    """A source file's SHA-256 digest differs from the pinned digest."""


def read_verified_source(path: str | pathlib.Path, expected_sha256: str) -> bytes:
    """Return a source file's bytes after checking its SHA-256 digest.

    Every source file is verified against its pinned digest before it is
    parsed, so a changed, truncated, or substituted publication is never
    read.

    Parameters
    ----------
    path : str or pathlib.Path
        The downloaded or locally supplied source file.
    expected_sha256 : str
        The pinned digest, as 64 hexadecimal characters in either case.

    Returns
    -------
    bytes
        The file's contents.

    Raises
    ------
    ValueError
        If ``expected_sha256`` is not 64 hexadecimal characters.
    SourceDigestError
        If the file's digest differs from ``expected_sha256``.
    """
    expected = expected_sha256.lower()
    if not _SHA256_HEX.fullmatch(expected):
        raise ValueError("expected_sha256 must be 64 hexadecimal characters")

    path = pathlib.Path(path)
    content = path.read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected:
        raise SourceDigestError(
            f"{path.name} has SHA-256 {actual}, but the pinned digest is {expected}"
        )
    return content
