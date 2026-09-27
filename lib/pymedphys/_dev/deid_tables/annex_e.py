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

"""Parse the DICOM PS3.15 Annex E tables that de-identification needs.

These are Table E.1-1, the attribute confidentiality profile; Table E.1-1a,
its action codes; and Table E.3.10-1, the safe private attributes.
"""

from __future__ import annotations

import collections
import re
import types
from collections.abc import Collection, Iterable

from pymedphys._dicom.deidentify.standard import (
    ACTION_CODES,
    ActionCode,
    ProfileAttribute,
    SafePrivateAttribute,
    is_private_tag,
    is_vm,
    is_vr_text,
)

from .chtml import HtmlTable, TableFormatError

TABLE_E1_1 = "Table E.1-1"
TABLE_E1_1A = "Table E.1-1a"
TABLE_E3_10_1 = "Table E.3.10-1"

# Columns are matched by their header text, so a new edition that reorders
# them still parses, and one that adds, renames, or removes one fails.
_NAME = "Attribute Name"
_TAG = "Tag"
_RETIRED = "Retd. (from PS3.6)"
_IN_STANDARD_IOD = "In Std. Comp. IOD (from PS3.3)"
_BASIC_PROFILE = "Basic Prof."

OPTION_COLUMNS = {
    "Rtn. Safe Priv. Opt.": "retain_safe_private",
    "Rtn. UIDs Opt.": "retain_uids",
    "Rtn. Dev. Id. Opt.": "retain_device_identity",
    "Rtn. Inst. Id. Opt.": "retain_institution_identity",
    "Rtn. Pat. Chars. Opt.": "retain_patient_characteristics",
    "Rtn. Long. Full Dates Opt.": "retain_longitudinal_full_dates",
    "Rtn. Long. Modif. Dates Opt.": "retain_longitudinal_modified_dates",
    "Clean Desc. Opt.": "clean_descriptors",
    "Clean Struct. Cont. Opt.": "clean_structured_content",
    "Clean Graph. Opt.": "clean_graphics",
}

COLUMNS = (_NAME, _TAG, _RETIRED, _IN_STANDARD_IOD, _BASIC_PROFILE, *OPTION_COLUMNS)

# A tag, where an "x" stands for any hexadecimal digit, as in (60xx,3000).
_TAG_PATTERN = re.compile(r"\([0-9A-Fx]{4},[0-9A-Fx]{4}\)")
# The row that covers every private attribute.
PRIVATE_ATTRIBUTES_TAG = "(gggg,eeee) where gggg is odd"


def _flag(value: str, column: str, row: int) -> bool:
    if value == "Y":
        return True
    if value == "N":
        return False
    raise TableFormatError(f"{TABLE_E1_1} row {row}: {column} is {value!r}, not Y or N")


def _action(value: str, column: str, row: int) -> str:
    if value not in ACTION_CODES:
        raise TableFormatError(
            f"{TABLE_E1_1} row {row}: {column} has action {value!r}, "
            "which is not defined in Table E.1-1a"
        )
    return value


def _tag(value: str, row: int) -> str:
    if value != PRIVATE_ATTRIBUTES_TAG and not _TAG_PATTERN.fullmatch(value):
        raise TableFormatError(
            f"{TABLE_E1_1} row {row}: tag {value!r} is not recognised"
        )
    return value


def _check_columns(
    label: str, header: tuple[str, ...], columns: Collection[str]
) -> None:
    for column in header:
        if column not in columns:
            raise TableFormatError(f"{label} has an unknown column {column!r}")
    for column in columns:
        count = header.count(column)
        if count == 0:
            raise TableFormatError(f"{label} is missing column {column!r}")
        if count > 1:
            raise TableFormatError(f"{label} has column {column!r} {count} times")


def _check_unique(label: str, keys: Iterable[str]) -> None:
    counts = collections.Counter(keys)
    repeated = [f"{key} appears {n} times" for key, n in counts.items() if n > 1]
    if repeated:
        raise TableFormatError(f"{label}: " + "; ".join(repeated))


def parse_table_e1_1(table: HtmlTable) -> tuple[ProfileAttribute, ...]:
    """Parse Table E.1-1 of DICOM PS3.15 Annex E.

    Parameters
    ----------
    table : HtmlTable
        The table, as :func:`~pymedphys._dev.deid_tables.chtml.select_table`
        returns it for ``"Table E.1-1"``.

    Returns
    -------
    tuple of ProfileAttribute
        One per row, in the table's order.

    Raises
    ------
    TableFormatError
        If a column is unknown, missing, or repeated; if a Y/N column holds
        anything else; if a tag has an unrecognised form or appears more than
        once; if an action is not defined in Table E.1-1a; or if the table
        has no rows. The Basic Profile action is required; option actions may
        be empty.
    """
    _check_columns(TABLE_E1_1, table.header, COLUMNS)
    if not table.rows:
        raise TableFormatError(f"{TABLE_E1_1} has no rows")

    attributes = []
    for number, cells in enumerate(table.rows, start=1):
        row = dict(zip(table.header, cells))
        name = row[_NAME]
        if not name:
            raise TableFormatError(
                f"{TABLE_E1_1} row {number}: the attribute name is empty"
            )
        attributes.append(
            ProfileAttribute(
                name=name,
                tag=_tag(row[_TAG], number),
                retired=_flag(row[_RETIRED], _RETIRED, number),
                in_standard_iod=_flag(row[_IN_STANDARD_IOD], _IN_STANDARD_IOD, number),
                basic_profile=_action(row[_BASIC_PROFILE], _BASIC_PROFILE, number),
                options=types.MappingProxyType(
                    {
                        option: _action(row[column], column, number)
                        for column, option in OPTION_COLUMNS.items()
                        if row[column]
                    }
                ),
            )
        )

    _check_unique(TABLE_E1_1, (attribute.tag for attribute in attributes))
    return tuple(attributes)


def parse_table_e1_1a(table: HtmlTable) -> tuple[ActionCode, ...]:
    """Parse Table E.1-1a of DICOM PS3.15 Annex E, the action codes.

    The published table has no header row: each row is a code and its
    description.

    Parameters
    ----------
    table : HtmlTable
        The table, as :func:`~pymedphys._dev.deid_tables.chtml.select_table`
        returns it for ``"Table E.1-1a"``.

    Returns
    -------
    tuple of ActionCode
        One per row, in the table's order.

    Raises
    ------
    TableFormatError
        If the table has a header row or no rows; if a row does not have
        exactly two cells or has an empty description; or if the codes are
        not exactly :data:`~pymedphys._dicom.deidentify.standard.ACTION_CODES`,
        each once. A new edition that adds or removes a code therefore fails
        until the engine implements the change.
    """
    if table.header:
        raise TableFormatError(
            f"{TABLE_E1_1A} has a header row; expected only code and description rows"
        )
    if not table.rows:
        raise TableFormatError(f"{TABLE_E1_1A} has no rows")

    codes = []
    for number, cells in enumerate(table.rows, start=1):
        if len(cells) != 2:
            raise TableFormatError(
                f"{TABLE_E1_1A} row {number} has {len(cells)} cells, not 2"
            )
        code, description = cells
        if code not in ACTION_CODES:
            raise TableFormatError(
                f"{TABLE_E1_1A} row {number}: {code!r} is not an action code "
                "PyMedPhys implements"
            )
        if not description:
            raise TableFormatError(
                f"{TABLE_E1_1A} row {number}: the description is empty"
            )
        codes.append(ActionCode(code=code, description=description))

    _check_unique(TABLE_E1_1A, (action.code for action in codes))
    missing = ACTION_CODES - {action.code for action in codes}
    if missing:
        raise TableFormatError(
            f"{TABLE_E1_1A} does not define {', '.join(sorted(missing))}"
        )
    return tuple(codes)


# Columns of Table E.3.10-1 by header text, and the field each fills.
E3_10_1_COLUMNS = {
    "Data Element": "tag",
    "Private Creator": "private_creator",
    "VR": "vr",
    "VM": "vm",
    "Meaning": "meaning",
}


def parse_table_e3_10_1(table: HtmlTable) -> tuple[SafePrivateAttribute, ...]:
    """Parse Table E.3.10-1 of DICOM PS3.15 Annex E, the safe private attributes.

    Cell text is kept as published, including lower-case hexadecimal digits
    in some tags, empty VRs, and empty meanings.

    Parameters
    ----------
    table : HtmlTable
        The table, as :func:`~pymedphys._dev.deid_tables.chtml.select_table`
        returns it for ``"Table E.3.10-1"``.

    Returns
    -------
    tuple of SafePrivateAttribute
        One per row, in the table's order.

    Raises
    ------
    TableFormatError
        If a column is unknown, missing, or repeated; if the table has no
        rows; if a Data Element is not a private tag of the form
        ``(gggg,xxee)``; if a private creator is empty; if a VR is neither
        empty nor one or more VRs from PS3.5 Table 6.2-1 such as ``OW/OB``;
        if a VM is not of the form ``1``, ``1-n``, or ``3-4`` with ascending
        bounds; or if a private creator and tag appear more than once,
        comparing tags without regard to case.
    """
    _check_columns(TABLE_E3_10_1, table.header, E3_10_1_COLUMNS)
    if not table.rows:
        raise TableFormatError(f"{TABLE_E3_10_1} has no rows")

    attributes = []
    for number, cells in enumerate(table.rows, start=1):
        row = {
            E3_10_1_COLUMNS[column]: cell for column, cell in zip(table.header, cells)
        }
        where = f"{TABLE_E3_10_1} row {number}"
        if not is_private_tag(row["tag"]):
            raise TableFormatError(
                f"{where}: {row['tag']!r} is not a private Data Element such as "
                "(0019,xx0C)"
            )
        if not row["private_creator"]:
            raise TableFormatError(f"{where}: the private creator is empty")
        if not is_vr_text(row["vr"]):
            raise TableFormatError(f"{where}: VR {row['vr']!r} is not recognised")
        if not is_vm(row["vm"]):
            raise TableFormatError(f"{where}: VM {row['vm']!r} is not recognised")
        attributes.append(SafePrivateAttribute(**row))

    _check_unique(
        TABLE_E3_10_1,
        (f"{a.private_creator} {a.tag.upper()}" for a in attributes),
    )
    return tuple(attributes)
