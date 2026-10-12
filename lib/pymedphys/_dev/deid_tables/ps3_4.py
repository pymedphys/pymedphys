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

"""Parse the DICOM PS3.4 table that de-identification needs.

This is Table B.5-1, the Standard Storage SOP Classes, which gives the IOD of
each SOP Class, so that the engine can find an instance's attribute Types from
its SOP Class UID.
"""

from __future__ import annotations

from pymedphys._dicom.deidentify.sop_classes import (
    STORAGE_SOP_CLASS_TABLE,
    StorageSOPClass,
)

from .chtml import HtmlTable, parse_registry_table

TABLE_B_5_1 = "Table B.5-1"

# The columns of Table B.5-1, by header text, and the fields they fill.
TABLE_B_5_1_COLUMNS = {
    "SOP Class Name": "name",
    "SOP Class UID": "uid",
    "IOD Specification (defined in PS3.3)": "iod",
    "Specialization": "specialization",
}


def parse_table_b_5_1(table: HtmlTable) -> tuple[StorageSOPClass, ...]:
    """Parse Table B.5-1 of DICOM PS3.4, the Standard Storage SOP Classes.

    Cell text is kept as published, including the "IOD" that ends each IOD's
    name and the section numbers of each specialization.

    Parameters
    ----------
    table : HtmlTable
        The table, as :func:`~pymedphys._dev.deid_tables.chtml.select_table`
        returns it for ``"Table B.5-1"``.

    Returns
    -------
    tuple of StorageSOPClass
        One per row, in the table's order.

    Raises
    ------
    TableFormatError
        If a column is unknown, missing, or repeated; if the table has no
        rows; if a row fails a check that the table's loader applies, such as
        an invalid UID or an IOD whose name does not end in "IOD"; or if a
        name or UID appears more than once.
    """
    return parse_registry_table(
        TABLE_B_5_1, table, TABLE_B_5_1_COLUMNS, STORAGE_SOP_CLASS_TABLE
    )
