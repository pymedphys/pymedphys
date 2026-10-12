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

"""Load DICOM PS3.15 Table E.3.4-1, the Clean Structured Content concept names.

Each row gives the concept name of a content item, by its code, and the value
type it has, with the actions of the Basic Profile and of each option for
that content item, as Table E.1-1 gives them for an attribute. The table
applies to the items of Content Sequence (0040,A730), Acquisition Context
Sequence (0040,0555), and Specimen Preparation Sequence (0040,0610) (PS3.15
Section E.3.4). ``pymedphys dev deid-tables`` generates it as ``e3_4_1.json``
in ``_standard/`` from the pinned edition, keeping only the rows whose coding
scheme the pin keeps (D-001).
"""

from __future__ import annotations

import dataclasses
import functools
import pathlib
import re
import types
from collections.abc import Callable, Mapping

from .codes import (
    CODE_MEANING_MAX_LENGTH,
    CODE_VALUE_MAX_LENGTH,
    DESIGNATOR_PATTERN,
    _is_short_text,
)
from .standard import _checked_rows, _default, _is_action, _read

TABLE = "PS3.15 Table E.3.4-1"
FILE = "e3_4_1.json"

# The Enumerated Values of Value Type (0040,A040), PS3.3 Section C.17.3.2.1.
VALUE_TYPES = frozenset(
    {
        "CODE", "COMPOSITE", "CONTAINER", "DATE", "DATETIME", "IMAGE", "NUM",
        "PNAME", "SCOORD", "SCOORD3D", "TABLE", "TCOORD", "TEXT", "TIME",
        "UIDREF", "WAVEFORM",
    }
)  # fmt: skip

# The option columns of Table E.3.4-1, in the table's order. The table has no
# column for the Retain Safe Private, Clean Structured Content, or Clean
# Graphics Options.
STRUCTURED_CONTENT_OPTIONS = (
    "retain_uids",
    "retain_device_identity",
    "retain_institution_identity",
    "retain_patient_characteristics",
    "retain_longitudinal_full_dates",
    "retain_longitudinal_modified_dates",
    "clean_descriptors",
)

# A Coding Scheme Designator as Table E.3.4-1 gives it, with the Coding
# Scheme Version in brackets where the table gives one, as in "NCDR [2.0b]".
DESIGNATOR_WITH_VERSION_PATTERN = re.compile(
    r"(?P<designator>\S+)(?: \[(?P<version>[^\]]+)\])?"
)

_FIELDS = frozenset(
    {
        "code_meaning",
        "code_value",
        "scheme_designator",
        "scheme_version",
        "value_type",
        "retired",
        "in_standard_template",
        "basic_profile",
        "options",
    }
)


@dataclasses.dataclass(frozen=True)
class ContentItemConcept:
    """One row of DICOM PS3.15 Table E.3.4-1.

    Attributes
    ----------
    code_meaning : str
        As the table gives it, such as ``"Person Observer Name"``.
    code_value : str
        Such as ``"121008"``.
    scheme_designator : str
        The Coding Scheme Designator (0008,0102), such as ``"DCM"``.
    scheme_version : str
        The Coding Scheme Version (0008,0103) where the table gives one, as
        ``"2.0b"`` in ``"NCDR [2.0b]"``, or ``""``.
    value_type : str
        The content item's Value Type (0040,A040), one of
        :data:`VALUE_TYPES`. A concept name can have a row for each of
        several value types, with different actions. Items encoded with the
        Content Item Macro (PS3.3 Table 10-2), such as those of Acquisition
        Context Sequence, give a numeric value the type NUMERIC, which the
        table, following Section C.17.3, gives as NUM.
    retired : bool
        Whether PS3.16 lists the code as retired.
    in_standard_template : bool
        Whether a template of PS3.16 uses the concept name.
    basic_profile : str
        The Basic Profile action, one of the codes in Table E.1-1a, such as
        ``"X"`` or ``"X/D"``.
    options : Mapping of str to str
        The action for each option that gives one, keyed by the names in
        :data:`STRUCTURED_CONTENT_OPTIONS`, as
        :attr:`~pymedphys._dicom.deidentify.standard.ProfileAttribute.options`
        is. The mapping is read-only.
    """

    code_meaning: str
    code_value: str
    scheme_designator: str
    scheme_version: str
    value_type: str
    retired: bool
    in_standard_template: bool
    basic_profile: str
    # A mapping is not hashable, so it is left out of the hash.
    options: Mapping[str, str] = dataclasses.field(hash=False)

    @property
    def key(self) -> tuple[str, str, str]:
        """The coding scheme designator, code value, and value type."""
        return (self.scheme_designator, self.code_value, self.value_type)


@dataclasses.dataclass(frozen=True)
class StructuredContentTable:
    """Table E.3.4-1 as generated from one edition of the standard.

    Attributes
    ----------
    edition : str
        The edition of DICOM PS3.15, such as ``"2026d"``.
    acknowledgement : str
        The copyright attribution for the table's source.
    concepts : tuple of ContentItemConcept
        One per generated row, in the table's order.
    """

    edition: str
    acknowledgement: str
    concepts: tuple[ContentItemConcept, ...]


def split_designator(value: str) -> tuple[str, str] | None:
    """Split a designator as Table E.3.4-1 gives it into designator and version.

    Returns
    -------
    tuple of str, or None
        The designator and the version, ``""`` if none is given, such as
        ``("NCDR", "2.0b")`` for ``"NCDR [2.0b]"``; or None if ``value`` is
        not a designator that
        :data:`~pymedphys._dicom.deidentify.codes.DESIGNATOR_PATTERN` matches
        in at most 16 characters, optionally followed by a space and a
        version of at most 16 characters in brackets.
    """
    match = DESIGNATOR_WITH_VERSION_PATTERN.fullmatch(value)
    if match is None:
        return None
    designator, version = match["designator"], match["version"] or ""
    if not is_designator(designator) or not (
        version == "" or is_code_text(version, CODE_VALUE_MAX_LENGTH)
    ):
        return None
    return designator, version


def is_designator(value: object) -> bool:
    """Return whether ``value`` is a Coding Scheme Designator of at most 16 characters."""
    return (
        isinstance(value, str)
        and bool(DESIGNATOR_PATTERN.fullmatch(value))
        and len(value) <= CODE_VALUE_MAX_LENGTH
    )


def is_code_text(value: object, max_length: int) -> bool:
    """Return whether ``value`` is a code value or meaning as the table gives one.

    That is non-empty text of at most ``max_length`` characters without
    leading or trailing spaces, a backslash, or a control character other
    than ESC (PS3.5 Table 6.2-1, SH and LO).
    """
    return _is_short_text(value, max_length) and str(value) == str(value).strip()


def _is_options(value: object) -> bool:
    return isinstance(value, dict) and all(
        option in STRUCTURED_CONTENT_OPTIONS and _is_action(action)
        for option, action in value.items()
    )


# Each check of a row, with what is wrong if it fails, in order.
_CHECKS: tuple[tuple[Callable[[dict], bool], str], ...] = (
    (
        lambda row: is_code_text(row["code_meaning"], CODE_MEANING_MAX_LENGTH),
        "has a code meaning that is not text of at most 64 characters",
    ),
    (
        lambda row: is_code_text(row["code_value"], CODE_VALUE_MAX_LENGTH),
        "has a code value that is not text of at most 16 characters",
    ),
    (
        lambda row: is_designator(row["scheme_designator"]),
        "has a coding scheme designator that is not a designator such as DCM",
    ),
    (
        lambda row: (
            row["scheme_version"] == ""
            or is_code_text(row["scheme_version"], CODE_VALUE_MAX_LENGTH)
        ),
        "has a coding scheme version that is not text of at most 16 characters",
    ),
    (
        lambda row: (
            isinstance(row["value_type"], str) and row["value_type"] in VALUE_TYPES
        ),
        "has a value type that PS3.3 does not define",
    ),
    (
        lambda row: all(
            isinstance(row[field], bool)
            for field in ("retired", "in_standard_template")
        ),
        "has a retired or in_standard_template value that is not true or false",
    ),
    (
        lambda row: _is_action(row["basic_profile"]),
        "has a Basic Profile action not defined in Table E.1-1a",
    ),
    (
        lambda row: _is_options(row["options"]),
        "has an unknown option or an option action not defined in Table E.1-1a",
    ),
)


def _problem(row: dict) -> str | None:
    """Return what is wrong with a row of Table E.3.4-1, or None if it is valid."""
    return next((message for check, message in _CHECKS if not check(row)), None)


def load_table_e3_4_1(path: pathlib.Path | None = None) -> StructuredContentTable:
    """Load Table E.3.4-1 of DICOM PS3.15, the Clean Structured Content concept names.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The generated file. Defaults to the one shipped with PyMedPhys.

    Returns
    -------
    StructuredContentTable

    Raises
    ------
    StandardTableError
        For any of the file-level problems
        :func:`~pymedphys._dicom.deidentify.standard.load_table_e1_1` rejects;
        if a row does not have exactly the fields of
        :class:`ContentItemConcept`, with a code meaning of at most 64
        characters and a code value of at most 16, neither with leading or
        trailing spaces, a backslash, or a control character; a designator
        that :func:`is_designator` accepts; a version that is empty or text
        of at most 16 characters; a value type in :data:`VALUE_TYPES`; true
        or false for the flags; and actions defined in Table E.1-1a for the
        Basic Profile and for each option in
        :data:`STRUCTURED_CONTENT_OPTIONS`; or if a designator, code value,
        and value type repeat.
    """
    return _load_table_e3_4_1(_default(path, FILE))


@functools.lru_cache(maxsize=None)
def _load_table_e3_4_1(path: pathlib.Path) -> StructuredContentTable:
    document = _read(path, TABLE)
    rows = _checked_rows(
        path,
        document,
        _FIELDS,
        _problem,
        lambda row: (row["scheme_designator"], row["code_value"], row["value_type"]),
        "a coding scheme designator, code value, and value type",
    )
    return StructuredContentTable(
        edition=document["edition"],
        acknowledgement=document["acknowledgement"],
        concepts=tuple(
            ContentItemConcept(
                **{
                    **row,
                    "options": types.MappingProxyType(dict(row["options"])),
                }
            )
            for row in rows
        ),
    )
