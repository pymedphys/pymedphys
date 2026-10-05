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

These commands belong to the DICOM de-identification tool, which is still in
development, so they are kept out of the ``pymedphys`` command line until the
tool is released, and may change without notice. Until then they run as
``python -m pymedphys._nomenclature``. Releasing the tool makes them public
commands with user documentation (milestone M5 of the design).

``python -m pymedphys._nomenclature roi-list CSV OUTPUT --list-version
VERSION`` converts an institutional list of ROI names, exported as UTF-8 CSV
with a ``Name`` column and an optional ``Description`` column, to JSON that records it as an
institutional list, with the file's name, SHA-256, and the version given.
Structure-name cleaning sends every match against such a list to human
review, since it can hold names that identify a site or a person.

``python -m pymedphys._nomenclature tg263 OUTPUT`` downloads the edition of AAPM's TG-263
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

from pymedphys._nomenclature import roi_list, tg263, tg263_published

PROG = "python -m pymedphys._nomenclature"


def define_parser() -> argparse.ArgumentParser:
    """Return the parser of the commands, which the ``pymedphys`` command lacks."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Convert structure-name nomenclatures to JSON for the DICOM "
            "de-identification tool, which is in development."
        ),
    )
    add_commands(parser.add_subparsers(dest="command"))
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run a command, or print the usage without one."""
    parser = define_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


def add_commands(nomenclature_subparsers) -> None:
    """Add the ``tg263`` and ``roi-list`` commands to ``nomenclature_subparsers``."""

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

    roi_list_parser = nomenclature_subparsers.add_parser(
        "roi-list",
        help="Convert an institutional list of ROI names from CSV to JSON.",
        description=(
            "Convert an institutional list of ROI names, exported as UTF-8 CSV "
            "with a Name column and an optional Description column, to JSON "
            "that records its source, SHA-256, and version."
        ),
    )
    roi_list_parser.add_argument(
        "csv", type=pathlib.Path, help="The UTF-8 CSV file to convert."
    )
    roi_list_parser.add_argument(
        "output", type=pathlib.Path, help="The JSON file to create; must not exist."
    )
    roi_list_parser.add_argument(
        "--list-version",
        required=True,
        help="The list's version, such as the date it was approved.",
    )
    roi_list_parser.set_defaults(func=convert_roi_list_cli)


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


def convert_roi_list_cli(args: argparse.Namespace) -> None:
    """Convert ``args.csv`` to ``args.output``, exiting 1 on failure."""
    source: pathlib.Path = args.csv
    output: pathlib.Path = args.output
    try:
        names = roi_list.read_csv(source, version=args.list_version)
    except OSError as error:
        _fail(f"cannot read {source.name}: {error.strerror or 'unreadable'}")
    except roi_list.RoiListError as error:
        _fail(str(error))
    _create(output, roi_list.to_json(names))
    count = len(names.entries)
    print(
        f"Wrote {count} {'name' if count == 1 else 'names'} from {names.source.file} "
        f"(version {names.source.version}) to {output.name}"
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
