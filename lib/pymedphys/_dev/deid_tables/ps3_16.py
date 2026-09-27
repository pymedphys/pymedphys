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
coding schemes, which register each scheme's designator and UID; and the
context groups CID 7050, De-identification Method, and CID 7005, Contributing
Equipment Purpose of Reference.
"""

from __future__ import annotations

from pymedphys._dicom.deidentify.codes import CODE_TABLES

from .chtml import HtmlTable, parse_registry_table

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
