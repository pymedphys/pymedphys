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

"""Generate the list of common personal names that descriptor cleaning excludes.

Run as ``python -m pymedphys._dev.deid_common_names [SOURCE]``. It reads the
United States Census Bureau's name files from the 1990 census, which are in
the public domain, as the ``names`` 0.3.0 source distribution on PyPI
redistributes them, checked against the SHA-256 pinned here, and writes
:data:`~pymedphys._dicom.deidentify.common_names.COMMON_NAMES_FILE`.

The list holds every given name of the male and female first-name files,
and every surname of the surname file held by at least
:data:`MIN_SURNAME_PERCENT` percent of the population, the files' finest
precision. Without ``SOURCE``, the distribution is downloaded.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import pathlib
import re
import sys
import tarfile
import tempfile
from collections.abc import Sequence
from decimal import Decimal

from pymedphys._data.download import download_with_progress
from pymedphys._dicom.deidentify.common_names import (
    COMMON_NAMES_FILE,
    SCHEMA,
    names_sha256,
)

SOURCE_URL = (
    "https://files.pythonhosted.org/packages/44/4e/"
    "f9cb7ef2df0250f4ba3334fbdabaa94f9c88097089763d8e85ada8092f84/names-0.3.0.tar.gz"
)
SOURCE_SHA256 = "726e46254f2ed03f1ffb5d941dae3bc67c35123941c29becd02d48d0caa2a671"
ORIGIN = (
    "United States Census Bureau, 1990 census name files (public domain), as "
    "redistributed in the names 0.3.0 source distribution on PyPI"
)
GIVEN_NAME_FILES = ("names/dist.male.first", "names/dist.female.first")
SURNAME_FILE = "names/dist.all.last"
# The files give each name's share of the population in percent, to three
# decimal places, so this keeps every surname that they do not round to zero.
MIN_SURNAME_PERCENT = Decimal("0.001")
# A row: the name, its percentage, the cumulative percentage, and its rank.
_ROW = re.compile(r"([A-Z]+) +(\d+\.\d{3}) +\d+\.\d{3} +\d+")


class CommonNamesError(ValueError):
    """The source cannot be read as the pinned distribution of the name files."""


def _rows(text: str, member: str) -> list[tuple[str, Decimal]]:
    rows = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = _ROW.fullmatch(line.strip())
        if match is None:
            raise CommonNamesError(f"line {number} of {member} is not a name row")
        rows.append((match[1], Decimal(match[2])))
    if not rows:
        raise CommonNamesError(f"{member} holds no names")
    return rows


def common_names(source: bytes) -> list[str]:
    """Return the sorted common names of the pinned distribution.

    Raises
    ------
    CommonNamesError
        If ``source`` does not have the pinned SHA-256, or a name file is
        missing or holds a line that is not a name row.
    """
    actual = hashlib.sha256(source).hexdigest()
    if actual != SOURCE_SHA256:
        raise CommonNamesError(
            f"the source has SHA-256 {actual}, but the pinned digest is {SOURCE_SHA256}"
        )
    texts = {}
    with tarfile.open(fileobj=io.BytesIO(source), mode="r:gz") as archive:
        for member in (*GIVEN_NAME_FILES, SURNAME_FILE):
            try:
                extracted = archive.extractfile(f"names-0.3.0/{member}")
            except KeyError:
                extracted = None
            if extracted is None:
                raise CommonNamesError(f"the source has no {member}")
            texts[member] = extracted.read().decode("ascii")
    names = {
        name for member in GIVEN_NAME_FILES for name, _ in _rows(texts[member], member)
    }
    names |= {
        name
        for name, percent in _rows(texts[SURNAME_FILE], SURNAME_FILE)
        if percent >= MIN_SURNAME_PERCENT
    }
    return sorted(names)


def document(names: Sequence[str]) -> dict:
    """Return the generated file's document for ``names``."""
    return {
        "schema": SCHEMA,
        "origin": ORIGIN,
        "source": {"url": SOURCE_URL, "sha256": SOURCE_SHA256},
        "rule": (
            "every name of dist.male.first and dist.female.first, and every "
            f"name of dist.all.last held by at least {MIN_SURNAME_PERCENT} "
            "percent of the population"
        ),
        "names_sha256": names_sha256(names),
        "names": list(names),
    }


def generate(source: pathlib.Path | None, output: pathlib.Path) -> int:
    """Write the common names to ``output``, and return how many there are.

    Raises
    ------
    CommonNamesError
        As :func:`common_names` does.
    """
    if source is None:
        with tempfile.TemporaryDirectory() as directory:
            downloaded = pathlib.Path(directory) / "names-0.3.0.tar.gz"
            download_with_progress(SOURCE_URL, downloaded)
            content = downloaded.read_bytes()
    else:
        content = source.read_bytes()
    names = common_names(content)
    output.write_text(
        json.dumps(document(names), indent=1, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return len(names)


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the common names, as the module describes."""
    parser = argparse.ArgumentParser(
        prog="python -m pymedphys._dev.deid_common_names",
        description="Generate the common personal names that descriptor "
        "cleaning excludes from its vocabulary.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=pathlib.Path,
        help="a local copy of the pinned names-0.3.0.tar.gz; downloaded if omitted",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=COMMON_NAMES_FILE,
        help="the file to write",
    )
    arguments = parser.parse_args(argv)
    try:
        count = generate(arguments.source, arguments.output)
    except CommonNamesError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"wrote {count} names")
    return 0


if __name__ == "__main__":
    sys.exit(main())
