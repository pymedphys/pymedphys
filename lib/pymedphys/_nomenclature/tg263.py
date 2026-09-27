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

"""Convert AAPM's TG-263 Structure Spreadsheet to JSON.

AAPM publishes the TG-263 structure names as an Excel 97-2003 workbook on its
Radiation Oncology Nomenclature Resource Page. PyMedPhys does not include the
workbook: :func:`read_spreadsheet` reads a copy the user has downloaded, and
:func:`to_json` writes it as JSON that records its source, the source file's
SHA-256, and AAPM's attribution. :func:`load_json` reads that JSON back and
rejects a file edited without updating its content digest (design decision
D-009).

The conversion keeps each entry as published, with three exceptions. Leading
and trailing whitespace is removed from every cell. The "N Characters" column
is not kept, because it is derived from the primary name and disagrees with it
in some rows of the 2017-08-15 edition. Columns without a header are ignored;
that edition has one, holding a single note.
"""

from __future__ import annotations

import collections
import dataclasses
import hashlib
import json
import pathlib
import re
from typing import Any, Mapping, Sequence

from pymedphys._imports import xlrd

FORMAT = "pymedphys-tg263/1"
ATTRIBUTION = (
    "TG-263 Structure Spreadsheet, from AAPM Report No. 263, Standardizing "
    "Nomenclatures in Radiation Oncology (2018), by AAPM Task Group 263. "
    "© American Association of Physicists in Medicine."
)

# Each published column header and the Structure field it fills, or None for
# a column that is read but not kept.
COLUMNS: dict[str, str | None] = {
    "Target Type": "target_type",
    "Major Category": "major_category",
    "Minor Category": "minor_category",
    "Anatomic Group": "anatomic_group",
    "N Characters": None,
    "TG263-Primary Name": "primary_name",
    "TG-263-Reverse Order Name": "reverse_order_name",
    "Description": "description",
    "FMAID": "fma_id",
}
_PRIMARY_NAME_HEADER = "TG263-Primary Name"
_REQUIRED = frozenset(
    {"target_type", "major_category", "primary_name", "reverse_order_name"}
)
_NAMES = ("primary_name", "reverse_order_name")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class TG263Error(ValueError):
    """A TG-263 spreadsheet or JSON file that cannot be read as expected."""


@dataclasses.dataclass(frozen=True)
class Structure:
    """One row of the TG-263 Structure Spreadsheet.

    Attributes
    ----------
    target_type : str
        Such as ``"Anatomic"`` or ``"Target"``, as published.
    major_category, minor_category, anatomic_group : str
        As published, or ``""`` where the spreadsheet gives none. The major
        category is never empty.
    primary_name : str
        The TG-263 name, such as ``"Lung_L"``.
    reverse_order_name : str
        The same name with its parts reversed, such as ``"L_Lung"``.
    description : str
        As published, or ``""``.
    fma_id : int or None
        The Foundational Model of Anatomy identifier, where one is given.
    """

    target_type: str
    major_category: str
    minor_category: str
    anatomic_group: str
    primary_name: str
    reverse_order_name: str
    description: str
    fma_id: int | None


_FIELDS = tuple(field.name for field in dataclasses.fields(Structure))
_HEADERS = {field: header for header, field in COLUMNS.items() if field}


@dataclasses.dataclass(frozen=True)
class Source:
    """The spreadsheet a nomenclature was converted from.

    Attributes
    ----------
    file : str
        The file's name, such as ``"TG263_Nomenclature_Worksheet_20170815.xls"``.
    sha256 : str
        The SHA-256 of the file's bytes, which identifies the exact edition.
    sheet : str
        The worksheet's name, which carries its version, such as
        ``"TG263 v20170815"``.
    """

    file: str
    sha256: str
    sheet: str


@dataclasses.dataclass(frozen=True)
class Nomenclature:
    """The TG-263 structure names from one spreadsheet.

    Attributes
    ----------
    source : Source
    attribution : str
        :data:`ATTRIBUTION`, which any copy must carry.
    structures : tuple of Structure
        One per row, in the spreadsheet's order.
    """

    source: Source
    attribution: str
    structures: tuple[Structure, ...]


def content_sha256(structures: Sequence[Mapping[str, object]]) -> str:
    """Return the SHA-256 of structures in canonical JSON.

    Keys are sorted, separators carry no whitespace, and text is UTF-8, so
    the digest does not depend on how the file is laid out.
    """
    canonical = json.dumps(
        structures, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def read_spreadsheet(path: pathlib.Path) -> Nomenclature:
    """Read a TG-263 Structure Spreadsheet.

    Parameters
    ----------
    path : pathlib.Path
        An ``.xls`` workbook, such as the one AAPM publishes. Exactly one of
        its worksheets must have a "TG263-Primary Name" column.

    Returns
    -------
    Nomenclature

    Raises
    ------
    TG263Error
        If the file is not a readable ``.xls`` workbook, if no worksheet or
        more than one holds the nomenclature, if a cell holds a date, a
        Boolean, or an error, or for any problem :func:`parse_sheet` rejects.
    """
    path = pathlib.Path(path)
    data = path.read_bytes()
    try:
        book = xlrd.open_workbook(file_contents=data)
    except (xlrd.XLRDError, xlrd.compdoc.CompDocError) as error:
        raise TG263Error(f"{path.name} is not a readable .xls workbook") from error
    sheet = _find_sheet(book)
    rows = [
        [
            _cell_value(sheet.cell(row, column), row, column)
            for column in range(sheet.ncols)
        ]
        for row in range(sheet.nrows)
    ]
    return Nomenclature(
        source=Source(
            file=path.name, sha256=hashlib.sha256(data).hexdigest(), sheet=sheet.name
        ),
        attribution=ATTRIBUTION,
        structures=parse_sheet(rows),
    )


def parse_sheet(rows: Sequence[Sequence[object]]) -> tuple[Structure, ...]:
    """Parse the cells of the worksheet that holds the TG-263 nomenclature.

    Parameters
    ----------
    rows : sequence of sequence
        The worksheet's cells, header row first. Each cell is text, a number,
        or ``""`` for an empty cell.

    Returns
    -------
    tuple of Structure
        One per row that is not blank, in order.

    Raises
    ------
    TG263Error
        If a header is not one of :data:`COLUMNS` and not empty, or appears
        more than once; if a column of :data:`COLUMNS` is missing; if a
        required value is empty or a text value is a number; if a name
        contains whitespace; if an FMAID is not a positive integer; if a
        primary or reverse-order name appears more than once; or if there are
        no structures. Errors name the spreadsheet row, counting from 1.
    """
    if not rows:
        raise TG263Error("the worksheet is empty")
    columns = _columns(rows[0])
    structures = []
    for number, row in enumerate(rows[1:], start=2):
        if all(_is_blank(cell) for cell in row):
            continue
        values = {
            field: _normalised(field, row[index] if index < len(row) else "")
            for field, index in columns.items()
        }
        problem = _structure_problem(values, _HEADERS)
        if problem:
            raise TG263Error(f"row {number}: {problem}")
        structures.append(_structure(values))
    _check_structures(structures, _HEADERS)
    return tuple(structures)


def to_json(nomenclature: Nomenclature) -> str:
    """Return a nomenclature as deterministic JSON, ending with a newline."""
    structures = [dataclasses.asdict(s) for s in nomenclature.structures]
    document = {
        "format": FORMAT,
        "source": dataclasses.asdict(nomenclature.source),
        "attribution": nomenclature.attribution,
        "content_sha256": content_sha256(structures),
        "structures": structures,
    }
    return json.dumps(document, indent=1, ensure_ascii=False) + "\n"


def load_json(path: pathlib.Path) -> Nomenclature:
    """Load a nomenclature written by :func:`to_json`.

    Raises
    ------
    TG263Error
        If the file is not JSON; if it does not have exactly the keys
        :func:`to_json` writes, or has another format or attribution; if its
        source is malformed; if a structure does not have exactly the fields
        of :class:`Structure` or has a value :func:`parse_sheet` would
        reject; if a name repeats; if it has no structures; or if its
        structures do not match its ``content_sha256``.
    """
    path = pathlib.Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise TG263Error(f"{path.name} is not valid JSON") from error
    keys = {"format", "source", "attribution", "content_sha256", "structures"}
    if not isinstance(document, dict) or set(document) != keys:
        raise TG263Error(f"{path.name} does not have the keys {sorted(keys)}")
    if document["format"] != FORMAT:
        raise TG263Error(
            f"{path.name} has format {document['format']!r}, not {FORMAT!r}"
        )
    source = document["source"]
    if not _is_source(source):
        raise TG263Error(f"{path.name} has a malformed source")
    if document["attribution"] != ATTRIBUTION:
        raise TG263Error(f"{path.name} does not carry the TG-263 attribution")
    structures = document["structures"]
    if not isinstance(structures, list):
        raise TG263Error(f"{path.name} has no list of structures")
    labels = {field: field for field in _FIELDS}
    for number, values in enumerate(structures, start=1):
        if not isinstance(values, dict) or set(values) != set(_FIELDS):
            raise TG263Error(f"structure {number} has keys other than {list(_FIELDS)}")
        problem = _structure_problem(values, labels)
        if problem:
            raise TG263Error(f"structure {number}: {problem}")
    loaded = [_structure(values) for values in structures]
    _check_structures(loaded, labels)
    if content_sha256(structures) != document["content_sha256"]:
        raise TG263Error(f"{path.name} does not match its content_sha256")
    return Nomenclature(
        source=Source(**source), attribution=ATTRIBUTION, structures=tuple(loaded)
    )


def _find_sheet(book):
    """Return the one worksheet with a "TG263-Primary Name" column."""
    sheets = [
        sheet
        for sheet in book.sheets()
        if sheet.nrows
        and _PRIMARY_NAME_HEADER
        in (str(value).strip() for value in sheet.row_values(0))
    ]
    if not sheets:
        raise TG263Error(f"no sheet has a {_PRIMARY_NAME_HEADER!r} column")
    if len(sheets) > 1:
        raise TG263Error(f"{len(sheets)} sheets have a {_PRIMARY_NAME_HEADER!r} column")
    return sheets[0]


def _cell_value(cell, row: int, column: int) -> str | float:
    """Return a cell's text, number, or ``""`` if it is empty."""
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return ""
    if cell.ctype in (xlrd.XL_CELL_TEXT, xlrd.XL_CELL_NUMBER):
        value: str | float = cell.value
        return value
    raise TG263Error(
        f"row {row + 1}, column {column + 1} holds a date, a Boolean, or an error"
    )


def _columns(header: Sequence[object]) -> dict[str, int]:
    """Map each Structure field to the index of its column."""
    names = [str(cell).strip() for cell in header]
    for name, count in collections.Counter(names).items():
        if name and count > 1:
            raise TG263Error(f"column {name!r} appears {count} times")
    for name in names:
        if name and name not in COLUMNS:
            raise TG263Error(f"unknown column {name!r}")
    for name in COLUMNS:
        if name not in names:
            raise TG263Error(f"missing column {name!r}")
    fields = {}
    for index, name in enumerate(names):
        field = COLUMNS.get(name)
        if field:
            fields[field] = index
    return fields


def _is_blank(cell: object) -> bool:
    return isinstance(cell, str) and not cell.strip()


def _normalised(field: str, cell: object) -> object:
    """Strip text, and turn an FMAID cell into an int or None where it can."""
    if isinstance(cell, str):
        cell = cell.strip()
    if field == "fma_id":
        if cell == "":
            return None
        if isinstance(cell, float) and cell.is_integer():
            return int(cell)
    return cell


def _field_problem(field: str, value: object) -> str | None:
    if field == "fma_id":
        return _fma_id_problem(value)
    if not isinstance(value, str):
        return "is not text"
    if value != value.strip():
        return "has surrounding whitespace"
    if field in _REQUIRED and not value:
        return "is empty"
    if field in _NAMES and re.search(r"\s", value):
        return "contains whitespace"
    return None


def _fma_id_problem(value: object) -> str | None:
    # bool is a subclass of int, but True is not an identifier.
    if value is None or (
        isinstance(value, int) and not isinstance(value, bool) and value > 0
    ):
        return None
    return "is not a positive integer"


def _structure_problem(
    values: Mapping[str, object], labels: Mapping[str, str]
) -> str | None:
    """Return what is wrong with a structure's values, or None."""
    for field in _FIELDS:
        problem = _field_problem(field, values[field])
        if problem:
            return f"{labels[field]!r} {problem}"
    return None


def _structure(values: Mapping[str, Any]) -> Structure:
    """Build a structure from values that :func:`_structure_problem` accepted."""
    return Structure(**values)


def _check_structures(
    structures: Sequence[Structure], labels: Mapping[str, str]
) -> None:
    if not structures:
        raise TG263Error("there are no structures")
    for field in _NAMES:
        counts = collections.Counter(getattr(s, field) for s in structures)
        for name, count in counts.items():
            if count > 1:
                raise TG263Error(f"{labels[field]!r} {name!r} appears {count} times")


def _is_source(source: object) -> bool:
    return (
        isinstance(source, dict)
        and set(source) == {"file", "sha256", "sheet"}
        and all(isinstance(value, str) and value for value in source.values())
        and bool(_SHA256.fullmatch(source["sha256"]))
    )
