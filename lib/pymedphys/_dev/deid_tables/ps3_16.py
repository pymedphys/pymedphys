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

"""Parse the DICOM PS3.16 tables that de-identification needs.

These are Table 8-1, the coding schemes, and Table 8-2, the HL7 version 3
coding schemes, which register each scheme's designator and UID; the context
groups CID 7050, De-identification Method, and CID 7005, Contributing
Equipment Purpose of Reference; and Tables L-1, L-2, and L-3 of Annex L,
which list the Defined Terms of Body Part Examined (0018,0015) that PS3.3
refers to.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from pymedphys._dicom.deidentify.codes import CODE_TABLES

from .chtml import HtmlTable, TableFormatError, parse_registry_table

_CONTEXT_GROUP_COLUMNS = {
    "Coding Scheme Designator": "scheme_designator",
    "Code Value": "code_value",
    "Code Meaning": "code_meaning",
}

# Each table's columns, by header text, and the fields they fill. Table 8-1's
# headers name the attributes that carry each value in a data set.
CODE_TABLE_COLUMNS = {
    "Table 8-1": {
        "Coding Scheme Designator (0008,0102)": "designator",
        "Coding Scheme UID (0008,010C)": "uid",
        "Coding Scheme Name (0008,0115)": "name",
        "Coding Scheme Responsible Organization (0008,0116)": (
            "responsible_organization"
        ),
        "Coding Scheme Resources Sequence (0008,0109) Type: URL": "resources",
        "Description": "description",
    },
    "Table 8-2": {
        "Coding Scheme Designator": "designator",
        "Coding Scheme UID": "uid",
        "Description": "description",
    },
    "Table CID 7050": _CONTEXT_GROUP_COLUMNS,
    "Table CID 7005": _CONTEXT_GROUP_COLUMNS,
}


def parse_code_table(label: str, table: HtmlTable) -> tuple:
    """Parse Table 8-1 or 8-2, or CID 7050 or 7005, of DICOM PS3.16.

    Cell text is kept as published, including the empty UIDs, names, and
    descriptions of some coding schemes, and the text of each scheme's
    resources.

    Parameters
    ----------
    label : str
        ``"Table 8-1"``, ``"Table 8-2"``, ``"Table CID 7050"``, or
        ``"Table CID 7005"``.
    table : HtmlTable
        The table, as :func:`~pymedphys._dev.deid_tables.chtml.select_table`
        returns it for ``label``.

    Returns
    -------
    tuple
        One row of the type
        :data:`~pymedphys._dicom.deidentify.codes.CODE_TABLES` gives for
        ``label``, per row of the table, in order.

    Raises
    ------
    TableFormatError
        If a column is unknown, missing, or repeated; if the table has no
        rows; if a row fails a check that the table's loader applies, such as
        an invalid UID; or if a designator, an HL7v3 coding scheme UID, or a
        context group's pair of designator and code value appears more than
        once.
    """
    return parse_registry_table(
        label, table, CODE_TABLE_COLUMNS[label], CODE_TABLES[label]
    )


# Annex L's tables of codes and terms for human, large animal, and small
# animal use, each with a column of Body Part Examined terms.
BODY_PART_TABLES = ("Table L-1", "Table L-2", "Table L-3")
BODY_PART_LABEL = "Annex L Body Part Examined Defined Terms"
_BODY_PART_COLUMN = "Body Part Examined"
# A value that VR CS can hold (PS3.5 Table 6.2-1), without its padding.
_CS_VALUE = re.compile(r"[A-Z0-9 _]{1,16}")


def parse_body_part_terms(tables: Mapping[str, HtmlTable]) -> list[dict[str, str]]:
    """Parse the Defined Terms of Body Part Examined from Annex L of PS3.16.

    PS3.3 gives no Defined Terms of Body Part Examined (0018,0015) in its
    General Series Module, but refers to Annex L for them. Rows whose Body
    Part Examined cell is empty, which have a code but no term, are skipped.

    Parameters
    ----------
    tables : mapping of str to HtmlTable
        Each of :data:`BODY_PART_TABLES`, by its label, as
        :func:`~pymedphys._dev.deid_tables.chtml.select_table` returns it.

    Returns
    -------
    list of dict
        Each distinct term, as a ``term``, in order.

    Raises
    ------
    TableFormatError
        If a table does not have exactly one Body Part Examined column, if a
        term is not a value that VR CS can hold, or if no table gives a term.
    """
    terms: set[str] = set()
    for label, table in tables.items():
        if table.header.count(_BODY_PART_COLUMN) != 1:
            raise TableFormatError(
                f"{label} does not have one {_BODY_PART_COLUMN!r} column"
            )
        column = table.header.index(_BODY_PART_COLUMN)
        for number, row in enumerate(table.rows, start=1):
            if row[column] and not _CS_VALUE.fullmatch(row[column]):
                raise TableFormatError(
                    f"{label}: row {number} has a term that VR CS cannot hold"
                )
            if row[column]:
                terms.add(row[column])
    if not terms:
        raise TableFormatError(f"PS3.16 gives no {BODY_PART_LABEL}")
    return [{"term": term} for term in sorted(terms)]
