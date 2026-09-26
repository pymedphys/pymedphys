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

"""Parse DICOM PS3.15 Table E.1-1, the attribute confidentiality profile."""

from __future__ import annotations

import collections
import dataclasses
import re

from .chtml import HtmlTable, TableFormatError

TABLE_E1_1 = "Table E.1-1"

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

# Complete action codes from Table E.1-1a. Compound codes have defined
# meanings; other combinations, including "U*" alone, are not defined.
ACTION_CODES = frozenset(
    {"D", "Z", "X", "K", "C", "U", "Z/D", "X/Z", "X/D", "X/Z/D", "X/Z/U*"}
)

# A tag, where an "x" stands for any hexadecimal digit, as in (60xx,3000).
_TAG_PATTERN = re.compile(r"\([0-9A-Fx]{4},[0-9A-Fx]{4}\)")
# The row that covers every private attribute.
PRIVATE_ATTRIBUTES_TAG = "(gggg,eeee) where gggg is odd"


@dataclasses.dataclass(frozen=True)
class ProfileAttribute:
    """One row of Table E.1-1.

    Attributes
    ----------
    name : str
        The attribute name, as the table gives it.
    tag : str
        The tag in the form ``(gggg,eeee)``, where ``x`` may stand for any
        hexadecimal digit, or :data:`PRIVATE_ATTRIBUTES_TAG`.
    retired : bool
        Whether PS3.6 lists the attribute as retired.
    in_standard_iod : bool
        Whether PS3.3 uses the attribute in a standard composite IOD.
    basic_profile : str
        The Basic Profile action, such as ``"X"`` or ``"X/Z/D"``.
    options : dict of str to str
        The action for each option that gives one, keyed by the names in
        :data:`OPTION_COLUMNS`. Options with an empty cell are omitted.
    """

    name: str
    tag: str
    retired: bool
    in_standard_iod: bool
    basic_profile: str
    options: dict[str, str]


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


def _check_columns(header: tuple[str, ...]) -> None:
    for column in header:
        if column not in COLUMNS:
            raise TableFormatError(f"{TABLE_E1_1} has an unknown column {column!r}")
    for column in COLUMNS:
        count = header.count(column)
        if count == 0:
            raise TableFormatError(f"{TABLE_E1_1} is missing column {column!r}")
        if count > 1:
            raise TableFormatError(f"{TABLE_E1_1} has column {column!r} {count} times")


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
        once; or if an action is not defined in Table E.1-1a. The Basic
        Profile action is required; option actions may be empty.
    """
    _check_columns(table.header)

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
                options={
                    option: _action(row[column], column, number)
                    for column, option in OPTION_COLUMNS.items()
                    if row[column]
                },
            )
        )

    counts = collections.Counter(attribute.tag for attribute in attributes)
    repeated = [f"{tag} appears {n} times" for tag, n in counts.items() if n > 1]
    if repeated:
        raise TableFormatError(f"{TABLE_E1_1}: " + "; ".join(repeated))
    return tuple(attributes)
