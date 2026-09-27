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

"""Parse the DICOM PS3.6 table that de-identification needs.

This is Table 6-1, the registry of DICOM data elements, which gives each
attribute's tag, name, keyword, VR, and VM.
"""

from __future__ import annotations

from pymedphys._dicom.deidentify.standard import (
    KEYWORD_PATTERN,
    DictionaryAttribute,
    is_dictionary_status,
    is_dictionary_tag,
    is_dictionary_vm,
    is_dictionary_vr,
)

from .chtml import HtmlTable, TableFormatError, check_columns, check_unique

TABLE_6_1 = "Table 6-1"

# The last column has no header. It marks retired attributes, and those that
# DICOS or DICONDE registered.
TABLE_6_1_COLUMNS = {
    "Tag": "tag",
    "Name": "name",
    "Keyword": "keyword",
    "VR": "vr",
    "VM": "vm",
    "": "status",
}


def _row_problem(row: dict[str, str]) -> str | None:
    """Return what is wrong with a row of Table 6-1, or None if it is valid."""
    checks = (
        (is_dictionary_tag(row["tag"]), f"tag {row['tag']!r} is not recognised"),
        (
            bool(row["name"]) == bool(row["keyword"]),
            "it has a name without a keyword, or a keyword without a name",
        ),
        (
            not row["keyword"] or bool(KEYWORD_PATTERN.fullmatch(row["keyword"])),
            f"keyword {row['keyword']!r} is not recognised",
        ),
        (is_dictionary_vr(row["vr"]), f"VR {row['vr']!r} is not recognised"),
        (is_dictionary_vm(row["vm"]), f"VM {row['vm']!r} is not recognised"),
        (
            is_dictionary_status(row["status"]),
            f"status {row['status']!r} is not recognised",
        ),
        (
            bool(row["keyword"]) or row["status"].startswith("RET"),
            "a placeholder without a keyword is not retired",
        ),
    )
    return next((message for valid, message in checks if not valid), None)


def parse_table_6_1(table: HtmlTable) -> tuple[DictionaryAttribute, ...]:
    """Parse Table 6-1 of DICOM PS3.6, the registry of data elements.

    Cell text is kept as published, including alternative VRs and VMs such
    as ``US or SS`` and ``1-n or 1``, notes in place of a VR or status, and
    the empty names and keywords of placeholders.

    Parameters
    ----------
    table : HtmlTable
        The table, as :func:`~pymedphys._dev.deid_tables.chtml.select_table`
        returns it for ``"Table 6-1"``.

    Returns
    -------
    tuple of DictionaryAttribute
        One per row, in the table's order.

    Raises
    ------
    TableFormatError
        If a column is unknown, missing, or repeated; if the table has no
        rows; if a tag, VR, VM, or status is not one that
        :func:`~pymedphys._dicom.deidentify.standard.is_dictionary_tag` and
        its companions accept; if a row has a name without a keyword, a
        keyword without a name, or a keyword that is not letters and digits;
        if a row without a keyword is not retired; or if a tag or keyword
        appears more than once.
    """
    check_columns(TABLE_6_1, table.header, TABLE_6_1_COLUMNS)
    if not table.rows:
        raise TableFormatError(f"{TABLE_6_1} has no rows")

    attributes = []
    for number, cells in enumerate(table.rows, start=1):
        row = {
            TABLE_6_1_COLUMNS[column]: cell for column, cell in zip(table.header, cells)
        }
        problem = _row_problem(row)
        if problem:
            raise TableFormatError(f"{TABLE_6_1} row {number}: {problem}")
        attributes.append(DictionaryAttribute(**row))

    check_unique(TABLE_6_1, (a.tag for a in attributes))
    check_unique(TABLE_6_1, (a.keyword for a in attributes if a.keyword))
    return tuple(attributes)
