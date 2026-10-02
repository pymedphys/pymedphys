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

``pymedphys nomenclature roi-list CSV OUTPUT --list-version VERSION`` converts
an institutional list of ROI names, exported as UTF-8 CSV with a ``Name``
column and an optional ``Description`` column, to JSON that records it as an
institutional list, with the file's name, SHA-256, and the version given.
Structure-name cleaning sends every match against such a list to human
review, since it can hold names that identify a site or a person.

``pymedphys nomenclature tg263 OUTPUT`` downloads the edition of AAPM's TG-263
Structure Spreadsheet that PyMedPhys pins, checks it against the pinned
SHA-256, and converts it to JSON that records the spreadsheet's file name,
worksheet version, SHA-256, and AAPM's attribution. PyMedPhys does not include
the spreadsheet; the download is cached in the PyMedPhys data directory. With
``--spreadsheet FILE`` it converts that workbook instead, without downloading
or checking it against the pin. It never overwrites an existing file.
Converted files are not to be edited by hand: their loader rejects a file
whose entries no longer match its recorded digest.
"""

import argparse
import pathlib
import sys
from typing import NoReturn

from pymedphys._nomenclature import roi_list, tg263, tg263_published


def nomenclature_cli(subparsers):
    parser = subparsers.add_parser(
        "nomenclature", help="Convert structure-name nomenclatures to JSON."
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
            "Convert this .xls workbook instead of the pinned edition. It is "
            "not downloaded or checked against the pin."
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
    try:
        if spreadsheet is None:
            nomenclature = tg263_published.load()
        else:
            nomenclature = tg263.read_spreadsheet(spreadsheet)
    except tg263.TG263Error as error:
        _fail(str(error))
    except OSError as error:
        reason = error.strerror or str(error) or "unknown error"
        if spreadsheet is None:
            _fail(
                f"cannot download {tg263_published.PUBLISHED.file}: {reason}; "
                "to convert a copy you already have, pass --spreadsheet FILE"
            )
        _fail(f"cannot read {spreadsheet.name}: {reason}")
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
    print(
        f"Wrote {len(names.entries)} names from {names.source.file} "
        f"(version {names.source.version}) to {output.name}"
    )


def _create(output: pathlib.Path, text: str) -> None:
    """Write text to a new file as UTF-8, failing if the file exists."""
    try:
        with output.open("xb") as file:
            file.write(text.encode("utf-8"))
    except FileExistsError:
        _fail(f"{output.name} already exists; choose a new output file")


def _fail(message: str) -> NoReturn:
    sys.stderr.write(f"error: {message}\n")
    sys.exit(1)
