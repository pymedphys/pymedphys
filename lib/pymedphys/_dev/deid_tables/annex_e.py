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
its action codes; Table E.3.4-1, the concept names of content items for the
Clean Structured Content Option; and Table E.3.10-1, the safe private
attributes.
"""

from __future__ import annotations

import re
import types

from pymedphys._dicom.deidentify.codes import (
    CODE_MEANING_MAX_LENGTH,
    CODE_VALUE_MAX_LENGTH,
)
from pymedphys._dicom.deidentify.standard import (
    ACTION_CODES,
    PRIVATE_ATTRIBUTES_TAG,
    ActionCode,
    ProfileAttribute,
    SafePrivateAttribute,
    is_private_tag,
    is_vm,
    is_vr_text,
)
from pymedphys._dicom.deidentify.structured_content import (
    VALUE_TYPES,
    ContentItemConcept,
    is_code_text,
    split_designator,
)

from .chtml import HtmlTable, TableFormatError, check_columns, check_unique

TABLE_E1_1 = "Table E.1-1"
TABLE_E1_1A = "Table E.1-1a"
TABLE_E3_4_1 = "Table E.3.4-1"
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


def _flag(value: str, column: str, row: int, table: str = TABLE_E1_1) -> bool:
    if value == "Y":
        return True
    if value == "N":
        return False
    raise TableFormatError(f"{table} row {row}: {column} is {value!r}, not Y or N")


def _action(value: str, column: str, row: int, table: str = TABLE_E1_1) -> str:
    if value not in ACTION_CODES:
        raise TableFormatError(
            f"{table} row {row}: {column} has action {value!r}, "
            "which is not defined in Table E.1-1a"
        )
    return value


def _tag(value: str, row: int) -> str:
    if value != PRIVATE_ATTRIBUTES_TAG and not _TAG_PATTERN.fullmatch(value):
        raise TableFormatError(
            f"{TABLE_E1_1} row {row}: tag {value!r} is not recognised"
        )
    return value


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
    check_columns(TABLE_E1_1, table.header, COLUMNS)
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

    check_unique(TABLE_E1_1, (attribute.tag for attribute in attributes))
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

    check_unique(TABLE_E1_1A, (action.code for action in codes))
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
    check_columns(TABLE_E3_10_1, table.header, E3_10_1_COLUMNS)
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

    check_unique(
        TABLE_E3_10_1,
        (f"{a.private_creator} {a.tag.upper()}" for a in attributes),
    )
    return tuple(attributes)


# Columns of Table E.3.4-1 by header text. The flags and actions are headed as
# in Table E.1-1, except that the table records whether a code is retired in
# PS3.16 and used in a template of PS3.16, and has no column for the Retain
# Safe Private, Clean Structured Content, or Clean Graphics Options.
_CODE_MEANING = "Code Meaning"
_CODE_VALUE = "Code Value"
_DESIGNATOR = "Coding Scheme Designator"
_VALUE_TYPE = "Value Type"
_RETIRED_CODE = "Retd. (from PS3.16)"
_IN_STANDARD_TEMPLATE = "In Std. Tpl. (from PS3.16)"
E3_4_1_OPTION_COLUMNS = {
    column: option
    for column, option in OPTION_COLUMNS.items()
    if option
    not in ("retain_safe_private", "clean_structured_content", "clean_graphics")
}
E3_4_1_COLUMNS = (
    _CODE_MEANING,
    _CODE_VALUE,
    _DESIGNATOR,
    _VALUE_TYPE,
    _RETIRED_CODE,
    _IN_STANDARD_TEMPLATE,
    _BASIC_PROFILE,
    *E3_4_1_OPTION_COLUMNS,
)


def _content_item_concept(row: dict[str, str], number: int) -> ContentItemConcept:
    """Return a row of Table E.3.4-1, checking each of its cells."""
    where = f"{TABLE_E3_4_1} row {number}"
    if not is_code_text(row[_CODE_MEANING], CODE_MEANING_MAX_LENGTH):
        raise TableFormatError(
            f"{where}: the code meaning is not text of at most 64 characters"
        )
    if not is_code_text(row[_CODE_VALUE], CODE_VALUE_MAX_LENGTH):
        raise TableFormatError(
            f"{where}: the code value is not text of at most 16 characters"
        )
    designator = split_designator(row[_DESIGNATOR])
    if designator is None:
        raise TableFormatError(
            f"{where}: coding scheme designator {row[_DESIGNATOR]!r} is not recognised"
        )
    if row[_VALUE_TYPE] not in VALUE_TYPES:
        raise TableFormatError(
            f"{where}: value type {row[_VALUE_TYPE]!r} is not defined in PS3.3"
        )
    return ContentItemConcept(
        code_meaning=row[_CODE_MEANING],
        code_value=row[_CODE_VALUE],
        scheme_designator=designator[0],
        scheme_version=designator[1],
        value_type=row[_VALUE_TYPE],
        retired=_flag(row[_RETIRED_CODE], _RETIRED_CODE, number, TABLE_E3_4_1),
        in_standard_template=_flag(
            row[_IN_STANDARD_TEMPLATE], _IN_STANDARD_TEMPLATE, number, TABLE_E3_4_1
        ),
        basic_profile=_action(
            row[_BASIC_PROFILE], _BASIC_PROFILE, number, TABLE_E3_4_1
        ),
        options=types.MappingProxyType(
            {
                option: _action(row[column], column, number, TABLE_E3_4_1)
                for column, option in E3_4_1_OPTION_COLUMNS.items()
                if row[column]
            }
        ),
    )


def parse_table_e3_4_1(
    table: HtmlTable, designators: frozenset[str], left_out: frozenset[str]
) -> tuple[ContentItemConcept, ...]:
    """Parse Table E.3.4-1 of DICOM PS3.15 Annex E, keeping the rows of some schemes.

    The table gives the Coding Scheme Version after the designator, in
    brackets, where it gives one, as in ``"NCDR [2.0b]"``.

    Parameters
    ----------
    table : HtmlTable
        The table, as :func:`~pymedphys._dev.deid_tables.chtml.select_table`
        returns it for ``"Table E.3.4-1"``.
    designators : frozenset of str
        The coding schemes whose rows are kept, by designator without
        version, such as ``"DCM"``.
    left_out : frozenset of str
        The coding schemes whose rows are left out. Every row's scheme must
        be in exactly one of the two sets, and every scheme in them must have
        a row, so that a new edition that adds or drops a scheme fails until
        the pin is reviewed.

    Returns
    -------
    tuple of ContentItemConcept
        One per kept row, in the table's order.

    Raises
    ------
    TableFormatError
        If a column is unknown, missing, or repeated; if the table has no
        rows; if a code meaning is not text of at most 64 characters or a
        code value of at most 16, or either has leading or trailing spaces, a
        backslash, or a control character; if a designator is not one such
        as ``"DCM"``, optionally followed by a version in brackets; if a
        value type is not one of PS3.3 Section C.17.3.2.1; if a Y/N column
        holds anything else; if an action is not defined in Table E.1-1a,
        the Basic Profile action being required; if a designator, code value,
        and value type appear more than once; or if the schemes do not match
        ``designators`` and ``left_out`` as described above.
    """
    check_columns(TABLE_E3_4_1, table.header, E3_4_1_COLUMNS)
    if not table.rows:
        raise TableFormatError(f"{TABLE_E3_4_1} has no rows")
    both = designators & left_out
    if both:
        raise TableFormatError(
            f"{TABLE_E3_4_1}: the pin both keeps and leaves out "
            + ", ".join(sorted(both))
        )

    concepts = [
        _content_item_concept(dict(zip(table.header, cells)), number)
        for number, cells in enumerate(table.rows, start=1)
    ]
    check_unique(
        TABLE_E3_4_1,
        (
            f"{concept.scheme_designator} {concept.code_value} {concept.value_type}"
            for concept in concepts
        ),
    )

    found = {concept.scheme_designator for concept in concepts}
    unknown = found - designators - left_out
    if unknown:
        raise TableFormatError(
            f"{TABLE_E3_4_1} has rows of coding schemes the pin neither keeps nor "
            "leaves out: " + ", ".join(sorted(unknown))
        )
    absent = (designators | left_out) - found
    if absent:
        raise TableFormatError(
            f"{TABLE_E3_4_1} has no rows of coding schemes the pin names: "
            + ", ".join(sorted(absent))
        )
    return tuple(
        concept for concept in concepts if concept.scheme_designator in designators
    )
