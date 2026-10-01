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
its own depth. Rows nested one level below an "Include" row are in the items
of the included table's only top-level attribute, a sequence, as in Table
C.18.4-1. A table can include itself below one of its own sequences, as
Table C.17-6 does within Content Sequence (0040,A730), so that the items of
that sequence nest as a tree; the "Include" row is kept, as a reference back
to the table.

The composite IODs are the modules tables of Annex A. Those whose modules
include an IOD's Functional Group Macros, such as the Multi-frame Functional
Groups Module, are not yet generated.

Rows are kept as published, apart from the pin's named corrections: macros
are not expanded, and attribute descriptions are omitted. Tables must be extracted with their merged cells
expanded, because an "Include" row's text spans several columns.
"""

from __future__ import annotations

import dataclasses
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
# A section of PS3.3 that defines a module, such as "C.7.1.1", or "C.7.6.4b"
# for a section inserted after C.7.6.4.
_SECTION = re.compile(r"[A-Z](?:\.[0-9]+)+[a-z]?")
_INCLUDE = re.compile(r"(>*)Include\b.*?\b(" + TABLE_LABEL_PATTERN.pattern + ")")
# A row of the Multi-frame Functional Groups Module, or a module like it, that
# includes the Functional Group Macros each IOD lists in a table of its own.
_FUNCTIONAL_GROUPS = re.compile(
    r">+Include (?:zero or more|one or more) Functional Group Macros\b.*"
)
_IOD_TITLE_SUFFIX = " IOD Modules"
# The composite IODs, whose instances are stored, are defined in Annex A.
_COMPOSITE_IOD_PREFIX = "Table A."


@dataclasses.dataclass(frozen=True)
class Correction:
    """A correction to an error in a published table of the pinned edition.

    Attributes
    ----------
    table : str
        The table's label, such as ``"Table A.29.3-1"``.
    published : str
        The text as published. It must occur in exactly one row of the table,
        counting its title and its header as rows, and that row must not
        already have the corrected text, so a correction fails once a later
        edition changes the text.
    corrected : str
        The text that replaces it in that row.
    """

    table: str
    published: str
    corrected: str


def correct(
    tables: Sequence[HtmlTable], corrections: Iterable[Correction]
) -> list[HtmlTable]:
    """Return the tables with each correction applied.

    Raises
    ------
    TableFormatError
        If a correction's table is missing or not unique, or its published
        text does not occur in exactly one row, or that row already has the
        corrected text.
    """
    corrected = list(tables)
    for correction in corrections:
        table = select_table(corrected, correction.table, allow_merged=True)
        lines = [(table.title,), table.header, *table.rows]
        found = [
            number
            for number, line in enumerate(lines)
            if any(correction.published in cell for cell in line)
        ]
        if len(found) != 1:
            raise TableFormatError(
                f"{correction.table} has {correction.published!r} in "
                f"{len(found)} rows, so its correction no longer applies"
            )
        # The published text can be part of the corrected text, as when a
        # correction adds a word, so it is still found once fixed.
        if any(correction.corrected in cell for cell in lines[found[0]]):
            raise TableFormatError(
                f"{correction.table} already has {correction.corrected!r}, so "
                "its correction no longer applies"
            )
        lines[found[0]] = tuple(
            cell.replace(correction.published, correction.corrected)
            for cell in lines[found[0]]
        )
        corrected[corrected.index(table)] = dataclasses.replace(
            table, title=lines[0][0], header=lines[1], rows=tuple(lines[2:])
        )
    return corrected


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
    if _FUNCTIONAL_GROUPS.fullmatch(name) and tag == name:
        raise TableFormatError(
            f"{label} row {number} includes an IOD's Functional Group Macros, "
            "which are not generated"
        )
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
        not 1, 1C, 2, 2C, or 3, and one that includes an IOD's Functional
        Group Macros; if a tag is not in the dictionary; or if a row is nested
        more deeply than the row above allows, which is one level below a
        sequence or an "Include" row and no deeper than any other row.
        :func:`collect` checks what an "Include" row with rows below it
        includes.
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
            allowed = above["depth"] + (
                bool(above["include"]) or dictionary.get(above["tag"]) == "SQ"
            )
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


def _below_own_sequence(rows: Sequence[Mapping[str, Any]], number: int) -> bool:
    """Return whether a row is in the items of a sequence of its own table."""
    enclosing = [row for row in rows[:number] if row["depth"] < rows[number]["depth"]]
    return bool(enclosing and enclosing[-1]["tag"])


def _functional_group_tables(
    tables: Sequence[HtmlTable], iod: Mapping[str, Any]
) -> list[str]:
    """Return the IOD's module tables that include Functional Group Macros."""
    return [
        module["table"]
        for module in iod["modules"]
        if any(
            _FUNCTIONAL_GROUPS.fullmatch(cell)
            for row in select_table(tables, module["table"], allow_merged=True).rows
            for cell in row
        )
    ]


def _composite_iods(
    tables: Sequence[HtmlTable], functional_group_iods: Iterable[tuple[str, str]]
) -> list[dict[str, Any]]:
    """Return the IODs of Annex A to generate, checking those left out."""
    left_out = dict(functional_group_iods)
    iods = []
    for table in tables:
        label, _, title = table.title.partition(". ")
        if not label.startswith(_COMPOSITE_IOD_PREFIX) or not title.endswith(
            _IOD_TITLE_SUFFIX
        ):
            continue
        iod = parse_iod_table(label, select_table(tables, label, allow_merged=True))
        for module in iod["modules"]:
            module["table"] = _module_table(tables, label, module)
        using = _functional_group_tables(tables, iod)
        if label not in left_out:
            if using:
                raise TableFormatError(
                    f"{label} includes Functional Group Macros through {using[0]}, "
                    "which are not generated, but the pin does not name it"
                )
            iods.append(iod)
        elif left_out.pop(label) != iod["iod"]:
            raise TableFormatError(f"the pin names {label} for another IOD")
        elif not using:
            raise TableFormatError(
                f"the pin names {label}, whose modules include no Functional "
                "Group Macros"
            )
    if left_out:
        raise TableFormatError(
            "the pin names tables that are not IOD Modules tables of Annex A: "
            + ", ".join(left_out)
        )
    if not iods:
        raise TableFormatError("no IOD Modules table of Annex A is generated")
    return iods


def _check_nesting_below_includes(
    parsed: Mapping[str, Mapping[str, Any]], dictionary: Mapping[str, str]
) -> None:
    """Check that rows nest below an Include only of a single sequence."""
    for label, table in parsed.items():
        for row, below in zip(table["rows"], table["rows"][1:]):
            if not row["include"] or below["depth"] <= row["depth"]:
                continue
            top = [
                found for found in parsed[row["include"]]["rows"] if not found["depth"]
            ]
            if len(top) != 1 or dictionary.get(top[0]["tag"]) != "SQ":
                raise TableFormatError(
                    f"{label} nests rows below its Include of {row['include']}, "
                    "which does not define exactly one top-level attribute, a "
                    "sequence"
                )


def collect(
    tables: Sequence[HtmlTable],
    dictionary: Mapping[str, str],
    functional_group_iods: Iterable[tuple[str, str]] = (),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the composite IODs' modules tables and every attribute table they reach.

    Parameters
    ----------
    tables : sequence of HtmlTable
        Every table of PS3.3, extracted with merged cells expanded.
    dictionary : mapping of str to str
        The VR of each tag in the pinned PS3.6 data dictionary.
    functional_group_iods : iterable of (str, str)
        The label and IOD name of each modules table that is left out because
        its modules include Functional Group Macros, such as
        ``("Table A.38-1", "Enhanced CT Image")``.

    Returns
    -------
    iods : list of dict
        Each other table of Annex A titled "<IOD> IOD Modules", in the order
        of PS3.3, as :func:`parse_iod_table` returns it, with each module's
        attribute table label added as ``table``.
    attribute_tables : list of dict
        Each module table and each macro table they include, directly or
        through other macros, as :func:`parse_attribute_table` returns it,
        sorted by :func:`natural_key`.

    Raises
    ------
    TableFormatError
        If a table is missing or malformed; if a module's section does not
        hold exactly one table titled "<module> Module Attributes"; if an
        IOD's modules include Functional Group Macros and it is not left
        out, or it is left out but they do not, or a table left out is not
        an IOD Modules table of Annex A or names another IOD; if no IOD
        remains; if a table includes itself other than below one of its own
        sequences, or through other tables; or if rows are nested below an
        "Include" row of a table that does not define exactly one top-level
        attribute, a sequence.
    """
    iods = _composite_iods(tables, functional_group_iods)
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
        rows = parsed[label]["rows"]
        for number, row in enumerate(rows):
            # A table that includes itself below one of its own sequences
            # refers back to itself, so its items nest as a tree.
            if row["include"] and not (
                row["include"] == label and _below_own_sequence(rows, number)
            ):
                visit(row["include"], (*chain, label))
        checked.add(label)

    for iod in iods:
        for module in iod["modules"]:
            visit(module["table"], ())
    _check_nesting_below_includes(parsed, dictionary)
    return iods, [parsed[label] for label in sorted(parsed, key=natural_key)]
