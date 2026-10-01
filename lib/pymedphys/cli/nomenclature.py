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

``pymedphys nomenclature tg263 SPREADSHEET OUTPUT`` converts a copy of AAPM's
TG-263 Structure Spreadsheet, which PyMedPhys does not include, to JSON that
records the spreadsheet's file name, worksheet version, SHA-256, and AAPM's
attribution. It never overwrites an existing file. Converted files are not to
be edited by hand: their loader rejects a file whose entries no longer match
its recorded digest.
"""

import argparse
import pathlib
import sys
from typing import NoReturn

from pymedphys._nomenclature import tg263


def nomenclature_cli(subparsers):
    parser = subparsers.add_parser(
        "nomenclature", help="Convert structure-name nomenclatures to JSON."
    )
    nomenclature_subparsers = parser.add_subparsers(dest="nomenclature")

    tg263_parser = nomenclature_subparsers.add_parser(
        "tg263",
        help="Convert a copy of AAPM's TG-263 Structure Spreadsheet to JSON.",
        description=(
            "Convert a copy of AAPM's TG-263 Structure Spreadsheet (.xls) to "
            "JSON that records its file name, worksheet version, SHA-256, and "
            "AAPM's attribution. PyMedPhys does not include the spreadsheet."
        ),
    )
    tg263_parser.add_argument(
        "spreadsheet", type=pathlib.Path, help="The .xls workbook to convert."
    )
    tg263_parser.add_argument(
        "output", type=pathlib.Path, help="The JSON file to create; must not exist."
    )
    tg263_parser.set_defaults(func=convert_tg263_cli)


def convert_tg263_cli(args: argparse.Namespace) -> None:
    """Convert ``args.spreadsheet`` to ``args.output``, exiting 1 on failure."""
    spreadsheet: pathlib.Path = args.spreadsheet
    output: pathlib.Path = args.output
    try:
        nomenclature = tg263.read_spreadsheet(spreadsheet)
    except OSError as error:
        _fail(f"cannot read {spreadsheet.name}: {error.strerror or 'unreadable'}")
    except tg263.TG263Error as error:
        _fail(str(error))
    try:
        with output.open("xb") as file:
            file.write(tg263.to_json(nomenclature).encode("utf-8"))
    except FileExistsError:
        _fail(f"{output.name} already exists; choose a new output file")
    print(
        f"Wrote {len(nomenclature.structures)} structures from "
        f"{nomenclature.source.file} ({nomenclature.source.sheet}) to {output.name}"
    )


def _fail(message: str) -> NoReturn:
    sys.stderr.write(f"error: {message}\n")
    sys.exit(1)
