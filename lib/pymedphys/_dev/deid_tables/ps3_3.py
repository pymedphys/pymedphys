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

"""Parse the DICOM PS3.3 tables that give the Types of an IOD's attributes.

An IOD's modules table, such as Table A.3-1 "CT Image IOD Modules", lists its
modules with their usage and the section that defines each. A module's
attribute table, such as Table C.7-1 "Patient Module Attributes", gives each
attribute's tag and Type. A row's leading ">" characters give its depth within
the items of the sequence above it, and an "Include" row adds the rows of a
macro table, such as Table 10-11 "SOP Instance Reference Macro Attributes", at
its own depth.

Rows are kept as published: macros are not expanded, and attribute
descriptions are omitted. Tables must be extracted with their merged cells
expanded, because an "Include" row's text spans several columns.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pymedphys._dicom.deidentify.iods import (
    ATTRIBUTE_TYPES,
    MODULE_USAGES,
    TABLE_LABEL_PATTERN,
)
from pymedphys._dicom.deidentify.standard import is_dictionary_tag

from .chtml import (
    HtmlTable,
    TableFormatError,
    check_columns,
    check_unique,
    select_table,
)

IOD_COLUMNS = {
    "IE": "information_entity",
    "Module": "module",
    "Reference": "section",
    "Usage": "usage",
}
_NAME, _TAG, _TYPE = "Attribute Name", "Tag", "Type"
# Most attribute tables head their last column "Attribute Description", and a
# few "Description".
_DESCRIPTIONS = ("Attribute Description", "Description")

# A usage code, optionally followed by a condition or a note, as in
# "C - Required if contrast media was used in this image".
_USAGE = re.compile(r"([A-Z])(?: - (.+))?")
# A section of PS3.3 that defines a module, such as "C.7.1.1".
_SECTION = re.compile(r"[A-Z](?:\.[0-9]+)+")
_INCLUDE = re.compile(r"(>*)Include\b.*?\b(" + TABLE_LABEL_PATTERN.pattern + ")")
_IOD_TITLE_SUFFIX = " IOD Modules"


def natural_key(label: str) -> tuple:
    """Return a key that sorts labels with their numbers compared as numbers.

    Examples
    --------
    >>> sorted(["Table C.8-10", "Table C.8-9", "Table 10-11"], key=natural_key)
    ['Table 10-11', 'Table C.8-9', 'Table C.8-10']
    """
    return tuple(
        int(part) if index % 2 else part
        for index, part in enumerate(re.split(r"([0-9]+)", label))
    )


def _title(table: HtmlTable) -> str:
    """Return a table's title without its label, as in "Patient Module Attributes"."""
    return table.title.partition(". ")[2]


def parse_iod_table(label: str, table: HtmlTable) -> dict[str, Any]:
    """Parse an IOD's modules table, such as Table A.3-1.

    Parameters
    ----------
    label : str
        The table's label, for messages.
    table : HtmlTable
        The table, with merged cells expanded, since an information entity's
        cell spans the rows of its modules.

    Returns
    -------
    dict
        ``label``; ``iod``, the IOD's name, such as ``"CT Image"``; and
        ``modules``, each with its ``information_entity``, ``module``,
        ``section``, ``usage`` code (``"M"``, ``"C"``, or ``"U"``), and
        ``condition``, the text after the usage code, or ``""``.

    Raises
    ------
    TableFormatError
        If a column is unknown, missing, or repeated; if the title does not
        end in "IOD Modules"; if the table has no rows or a row has an empty
        cell; if a reference is not a section number or a usage is not M, C,
        or U; or if a module is listed twice.
    """
    check_columns(label, table.header, IOD_COLUMNS)
    title = _title(table)
    if not title.endswith(_IOD_TITLE_SUFFIX):
        raise TableFormatError(f"{label} is not an IOD Modules table")
    if not table.rows:
        raise TableFormatError(f"{label} has no rows")

    modules = []
    for number, cells in enumerate(table.rows, start=1):
        row = {IOD_COLUMNS[column]: cell for column, cell in zip(table.header, cells)}
        usage = _USAGE.fullmatch(row["usage"])
        if not all(row.values()):
            raise TableFormatError(f"{label} row {number} has an empty cell")
        if not _SECTION.fullmatch(row["section"]):
            raise TableFormatError(f"{label} row {number} has no section reference")
        if not usage or usage.group(1) not in MODULE_USAGES:
            raise TableFormatError(f"{label} row {number} has an unknown usage")
        modules.append(
            {**row, "usage": usage.group(1), "condition": usage.group(2) or ""}
        )
    check_unique(label, (module["module"] for module in modules))
    return {
        "label": label,
        "iod": title.removesuffix(_IOD_TITLE_SUFFIX),
        "modules": modules,
    }


def _row(
    label: str, number: int, cells: dict[str, str], dictionary: Mapping[str, str]
) -> dict[str, Any] | None:
    """Return a row of an attribute table, or None for a heading."""
    name, tag, attribute_type = cells[_NAME], cells[_TAG], cells[_TYPE]
    depth = len(name) - len(name.lstrip(">"))
    include = _INCLUDE.match(name)
    # An Include row's text spans the tag and Type columns too.
    if include and tag == name:
        return {
            "depth": depth,
            "name": "",
            "tag": "",
            "type": "",
            "include": include[2],
        }
    # A heading spans the whole table.
    if len(set(cells.values())) == 1:
        return None
    if attribute_type in ATTRIBUTE_TYPES and (tag == name or is_dictionary_tag(tag)):
        if tag != name and tag not in dictionary:
            raise TableFormatError(
                f"{label} row {number} has {tag}, which PS3.6 does not define"
            )
        # A row whose name spans the tag column describes attributes in words.
        return {
            "depth": depth,
            "name": name[depth:].strip(),
            "tag": "" if tag == name else tag,
            "type": attribute_type,
            "include": "",
        }
    raise TableFormatError(
        f"{label} row {number} is not an attribute, an Include, or a heading"
    )


def parse_attribute_table(
    label: str, table: HtmlTable, dictionary: Mapping[str, str]
) -> dict[str, Any]:
    """Parse a module or macro attribute table, such as Table C.7-1.

    Parameters
    ----------
    label : str
        The table's label, for messages.
    table : HtmlTable
        The table, with merged cells expanded.
    dictionary : mapping of str to str
        The VR of each tag in the pinned PS3.6 data dictionary.

    Returns
    -------
    dict
        ``label``, ``title``, and ``rows``, each with ``depth``, ``name``,
        ``tag``, ``type``, and ``include``:

        - an attribute row has its name, tag, and Type, and ``include`` is
          ``""``;
        - an "Include" row has its depth and the included table's label in
          ``include``, and the other fields are ``""``;
        - a row that describes attributes in words, such as "Any Attribute
          from the top level Data Set that was modified or removed", has its
          name and Type, and ``tag`` is ``""``.

        Headings that span the whole table, such as "BASIC CODED ENTRY
        ATTRIBUTES", are omitted.

    Raises
    ------
    TableFormatError
        If the columns are not an attribute table's; if the table has no rows;
        if a row is not one of the kinds above, including one whose Type is
        not 1, 1C, 2, 2C, or 3; if a tag is not in the dictionary; or if a row
        is nested more deeply than the row above allows, which is one level
        below a sequence and no deeper than any other row.
    """
    description = [column for column in table.header if column in _DESCRIPTIONS]
    check_columns(label, table.header, (_NAME, _TAG, _TYPE, *description[:1]))
    if not table.rows:
        raise TableFormatError(f"{label} has no rows")

    rows: list[dict[str, Any]] = []
    for number, cells in enumerate(table.rows, start=1):
        row = _row(label, number, dict(zip(table.header, cells)), dictionary)
        if row is None:
            continue
        allowed = 0
        if rows:
            above = rows[-1]
            allowed = above["depth"] + (dictionary.get(above["tag"]) == "SQ")
        if row["depth"] > allowed:
            raise TableFormatError(
                f"{label} row {number} is nested more deeply than the row above allows"
            )
        rows.append(row)
    return {"label": label, "title": _title(table), "rows": rows}


def _module_table(
    tables: Sequence[HtmlTable], label: str, module: Mapping[str, str]
) -> str:
    """Return the label of a module's attribute table, found in its section."""
    title = f"{module['module']} Module Attributes"
    found = [
        table.title.partition(". ")[0]
        for table in tables
        if table.section == module["section"] and _title(table) == title
    ]
    if len(found) != 1:
        raise TableFormatError(
            f"{label} lists module {module['module']}, but there is "
            f"{len(found) or 'no'} {title} table in {module['section']}"
        )
    return found[0]


def collect(
    tables: Sequence[HtmlTable],
    iod_labels: Iterable[str],
    dictionary: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse IOD modules tables and every attribute table they reach.

    Parameters
    ----------
    tables : sequence of HtmlTable
        Every table of PS3.3, extracted with merged cells expanded.
    iod_labels : iterable of str
        The labels of the IOD modules tables, such as ``"Table A.3-1"``.
    dictionary : mapping of str to str
        The VR of each tag in the pinned PS3.6 data dictionary.

    Returns
    -------
    iods : list of dict
        Each IOD modules table as :func:`parse_iod_table` returns it, with
        each module's attribute table label added as ``table``, in the given
        order.
    attribute_tables : list of dict
        Each module table and each macro table they include, directly or
        through other macros, as :func:`parse_attribute_table` returns it,
        sorted by :func:`natural_key`.

    Raises
    ------
    TableFormatError
        If a table is missing or malformed; if a module's section does not
        hold exactly one table titled "<module> Module Attributes"; or if a
        table includes itself, directly or through other tables.
    """
    iods = []
    for label in iod_labels:
        iod = parse_iod_table(label, select_table(tables, label, allow_merged=True))
        for module in iod["modules"]:
            module["table"] = _module_table(tables, label, module)
        iods.append(iod)

    parsed: dict[str, dict[str, Any]] = {}
    checked: set[str] = set()

    def visit(label: str, chain: tuple[str, ...]) -> None:
        if label in chain:
            raise TableFormatError(
                f"{label} includes itself: "
                + " > ".join((*chain[chain.index(label) :], label))
            )
        if label in checked:
            return
        if label not in parsed:
            table = select_table(tables, label, allow_merged=True)
            parsed[label] = parse_attribute_table(label, table, dictionary)
        for row in parsed[label]["rows"]:
            if row["include"]:
                visit(row["include"], (*chain, label))
        checked.add(label)

    for iod in iods:
        for module in iod["modules"]:
            visit(module["table"], ())
    return iods, [parsed[label] for label in sorted(parsed, key=natural_key)]
