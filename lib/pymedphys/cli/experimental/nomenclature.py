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

"""Convert structure-name nomenclatures, such as TG-263's, to JSON.

These commands are experimental: they belong to the DICOM de-identification
tool, which is still in development, and may change without notice.

``pymedphys experimental nomenclature tg263 OUTPUT`` downloads the edition of AAPM's TG-263
Structure Spreadsheet that PyMedPhys pins, checks it against the pinned
SHA-256, and converts it to JSON that records the spreadsheet's file name,
worksheet version, SHA-256, and AAPM's attribution. PyMedPhys does not include
the spreadsheet; the download is cached in the PyMedPhys data directory. With
``--spreadsheet FILE`` it converts that workbook instead, without downloading:
a copy of the pinned edition is checked against the pin, and any other
workbook is converted with a note that it was not. It never overwrites an
existing file.
Converted files are not to be edited by hand: their loader rejects a file
whose entries no longer match its recorded digest.
"""

import argparse
import http.client
import pathlib
import sys
import urllib.error
from typing import NoReturn

from pymedphys._nomenclature import tg263, tg263_published


def nomenclature_cli(subparsers):
    parser = subparsers.add_parser(
        "nomenclature",
        help="Convert structure-name nomenclatures to JSON (experimental).",
    )
    nomenclature_subparsers = parser.add_subparsers(dest="nomenclature")

    tg263_parser = nomenclature_subparsers.add_parser(
        "tg263",
        help="Convert AAPM's TG-263 Structure Spreadsheet to JSON.",
        description=(
            "Download the pinned edition of AAPM's TG-263 Structure "
            "Spreadsheet (.xls), check its SHA-256, and convert it to JSON "
            "that records its file name, worksheet version, SHA-256, and "
            "AAPM's attribution. PyMedPhys does not include the spreadsheet."
        ),
    )
    tg263_parser.add_argument(
        "output", type=pathlib.Path, help="The JSON file to create; must not exist."
    )
    tg263_parser.add_argument(
        "--spreadsheet",
        type=pathlib.Path,
        metavar="FILE",
        help=(
            "Convert this .xls workbook instead of downloading the pinned "
            "edition. A copy of the pinned edition is checked against the pin; "
            "any other workbook is converted with a note that it was not."
        ),
    )
    tg263_parser.set_defaults(func=convert_tg263_cli)


def convert_tg263_cli(args: argparse.Namespace) -> None:
    """Convert the pinned edition, or ``args.spreadsheet``, to ``args.output``.

    Exits with status 1, writing nothing, on any failure.
    """
    spreadsheet: pathlib.Path | None = args.spreadsheet
    output: pathlib.Path = args.output
    if output.exists():
        _fail(f"{output.name} already exists; choose a new output file")
    published = tg263_published.PUBLISHED
    if spreadsheet is None:
        nomenclature = _published(published)
    else:
        nomenclature = _local(spreadsheet, published)
    _create(output, tg263.to_json(nomenclature))
    print(
        f"Wrote {len(nomenclature.structures)} structures from "
        f"{nomenclature.source.file} ({nomenclature.source.sheet}) to {output.name}"
    )


def _published(edition: tg263_published.Edition) -> tg263.Nomenclature:
    """Download, or read from the cache, and check the pinned edition."""
    try:
        return tg263_published.load(edition)
    except tg263.TG263Error as error:
        _fail(
            f"{error}; AAPM may have changed the file, so please report it to "
            "PyMedPhys, or pass --spreadsheet FILE to convert a copy you trust"
        )
    except (
        urllib.error.URLError,
        http.client.HTTPException,
        ConnectionError,
        TimeoutError,
    ) as error:
        _fail(
            f"cannot download {edition.file}: {_reason(error)}; to convert a "
            "copy you already have, pass --spreadsheet FILE"
        )
    except OSError as error:
        _fail(_reason(error))


def _local(
    spreadsheet: pathlib.Path, edition: tg263_published.Edition
) -> tg263.Nomenclature:
    """Read a local workbook, checking it against the pin if it is a copy."""
    try:
        if tg263_published.sha256(spreadsheet) == edition.sha256:
            return tg263_published.load(edition, spreadsheet=spreadsheet)
        nomenclature = tg263.read_spreadsheet(spreadsheet)
    except OSError as error:
        _fail(f"cannot read {spreadsheet.name}: {_reason(error)}")
    except tg263.TG263Error as error:
        _fail(str(error))
    sys.stderr.write(
        f"note: {spreadsheet.name} is not the pinned edition ({edition.sheet}), "
        "so it was converted but not checked against the pin\n"
    )
    return nomenclature


def _reason(error: BaseException) -> str:
    """Describe an error by its reason and file name, never its directory."""
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code}"
    if isinstance(error, urllib.error.URLError):
        return str(error.reason)
    if isinstance(error, OSError) and error.strerror:
        if error.filename:
            return f"{error.strerror}: {pathlib.Path(error.filename).name}"
        return error.strerror
    return str(error) or type(error).__name__


def _create(output: pathlib.Path, text: str) -> None:
    """Write text to a new file as UTF-8, removing it if the write fails."""
    data = text.encode("utf-8")
    try:
        file = output.open("xb")
    except FileExistsError:
        _fail(f"{output.name} already exists; choose a new output file")
    except OSError as error:
        _fail(f"cannot write {output.name}: {error.strerror or error}")
    try:
        with file:
            file.write(data)
    except BaseException as error:
        output.unlink(missing_ok=True)
        if isinstance(error, OSError):
            _fail(f"cannot write {output.name}: {error.strerror or error}")
        raise


def _fail(message: str) -> NoReturn:
    sys.stderr.write(f"error: {message}\n")
    sys.exit(1)
