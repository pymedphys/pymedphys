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

"""Load the tables of DICOM PS3.6 Annex A generated from the standard.

Annex A registers the UIDs that the standard defines (Table A-1), the
well-known frames of reference (Table A-2), the UIDs of context groups (Table
A-3), and the UIDs of HL7 CDA templates (Table A-4). ``pymedphys dev
deid-tables`` generates each as a file in ``_standard/`` from the pinned
edition (design decision D-001), and the loaders here check it as
:mod:`~pymedphys._dicom.deidentify.standard` checks the other tables.
"""

from __future__ import annotations

import dataclasses
import functools
import pathlib
import re
import types
from collections.abc import Callable, Sequence
from typing import Any, Generic, TypeVar

from .standard import StandardTableError, _default, _is_text, _read

# A UID as PS3.5 Section 9.1 defines it: numeric components without leading
# zeros, separated by periods. It is also at most 64 characters long.
UID_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))*")
# Keywords in PS3.6 Annex A may contain underscores, as in ITIS_TSN.
UID_KEYWORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
# The UID Type column of PS3.6 Table A-1. A new type fails generation, so its
# handling is reviewed before the tables are updated.
UID_TYPES = frozenset(
    {
        "Application Context Name",
        "Application Hosting Model",
        "Coding Scheme",
        "DICOM UIDs as a Coding Scheme",
        "LDAP OID",
        "Mapping Resource",
        "Meta SOP Class",
        "SOP Class",
        "Service Class",
        "Synchronization Frame of Reference",
        "Transfer Syntax",
        "Well-known SOP Instance",
    }
)
# The UID Type column of PS3.6 Table A-4.
TEMPLATE_UID_TYPES = frozenset(
    {
        "Document TemplateID",
        "Element Set TemplateID",
        "Entry TemplateID",
        "Section TemplateID",
    }
)
_RETIREMENT_YEAR = r"\([0-9]{4}[a-e]?\)"
# The Part column of PS3.6 Tables A-1 and A-4: the part or standard that
# defines the UID, followed by the edition that retired it, or that edition
# alone.
REGISTRY_PART_PATTERN = re.compile(
    rf"(?:PS3\.[0-9]+|DICOS|DICONDE ASTM E[0-9]+)(?: {_RETIREMENT_YEAR})?"
    rf"|{_RETIREMENT_YEAR}"
)
CONTEXT_GROUP_PATTERN = re.compile(r"CID [0-9]+")
CONTEXT_GROUP_COMMENT_PATTERN = re.compile(rf"Retired|RET {_RETIREMENT_YEAR}")


@dataclasses.dataclass(frozen=True)
class RegisteredUID:
    """One row of DICOM PS3.6 Table A-1, the registry of UIDs.

    Attributes
    ----------
    uid : str
    name : str
        As published, such as ``"Implicit VR Little Endian: Default Transfer
        Syntax for DICOM"``. A retired UID's name ends in ``"(Retired)"``,
        and may be nothing else.
    keyword : str
        The keyword, or ``""`` for some retired UIDs.
    uid_type : str
        One of :data:`UID_TYPES`, such as ``"SOP Class"``.
    part : str
        The part or standard that defines the UID, such as ``"PS3.4"`` or
        ``"DICOS"``, followed by the edition that retired it, as in
        ``"PS3.5 (2011)"``, or that edition alone.
    """

    uid: str
    name: str
    keyword: str
    uid_type: str
    part: str

    @property
    def retired(self) -> bool:
        """Whether the UID is retired."""
        return self.name.endswith("(Retired)")


@dataclasses.dataclass(frozen=True)
class WellKnownFrameOfReference:
    """One row of DICOM PS3.6 Table A-2, the well-known frames of reference.

    Attributes
    ----------
    uid, name, keyword : str
    normative_reference : str
        The atlas, coordinate system, or document that defines the frame.
    """

    uid: str
    name: str
    keyword: str
    normative_reference: str


@dataclasses.dataclass(frozen=True)
class ContextGroupUID:
    """One row of DICOM PS3.6 Table A-3, the UIDs of context groups.

    Attributes
    ----------
    uid : str
    identifier : str
        Such as ``"CID 2"``, or ``""`` for a UID that no context group uses.
    name : str
        The context group's name, or ``""`` where there is no identifier.
        Names can repeat.
    comment : str
        ``""``, ``"Retired"``, or ``"RET"`` with the edition that retired
        the group, as in ``"RET (2013)"``.
    """

    uid: str
    identifier: str
    name: str
    comment: str

    @property
    def retired(self) -> bool:
        """Whether the context group is retired."""
        return bool(self.comment)


@dataclasses.dataclass(frozen=True)
class TemplateUID:
    """One row of DICOM PS3.6 Table A-4, the UIDs of HL7 CDA templates.

    Attributes
    ----------
    uid, name : str
    uid_type : str
        One of :data:`TEMPLATE_UID_TYPES`, such as ``"Document TemplateID"``.
    part : str
        The part that defines the template, such as ``"PS3.20"``.
    """

    uid: str
    name: str
    uid_type: str
    part: str


_Row = TypeVar("_Row")


@dataclasses.dataclass(frozen=True)
class RegistryTable(Generic[_Row]):
    """A table of PS3.6 Annex A as generated from one edition of the standard.

    Attributes
    ----------
    edition : str
        The edition of DICOM PS3.6, such as ``"2026d"``.
    acknowledgement : str
        ``"DICOM PS3.6 <edition>, © NEMA"``.
    rows : tuple
        One per row, in the table's order.
    """

    edition: str
    acknowledgement: str
    rows: tuple[_Row, ...]


def is_uid(value: object) -> bool:
    """Return whether ``value`` is a UID as PS3.5 Section 9.1 defines one.

    That is numeric components without leading zeros, separated by periods,
    in at most 64 characters, such as ``"1.2.840.10008.1.2"``.
    """
    return (
        isinstance(value, str)
        and len(value) <= 64
        and bool(UID_PATTERN.fullmatch(value))
    )


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return isinstance(value, str) and bool(pattern.fullmatch(value))


def _first_problem(
    checks: Sequence[tuple[Callable[[dict], bool], str]], row: dict
) -> str | None:
    return next((message for check, message in checks if not check(row)), None)


def _retired_in_part(part: str) -> bool:
    return part.endswith(")")


_UID = (
    lambda row: is_uid(row["uid"]),
    "has a UID that is not numeric components without leading zeros, "
    "in at most 64 characters",
)
_NAME = (lambda row: _is_text(row["name"]), "has a name that is not non-empty text")
_UID_VALUE_CHECKS: tuple[tuple[Callable[[dict], bool], str], ...] = (
    _UID,
    _NAME,
    (
        lambda row: row["keyword"] == ""
        or _matches(UID_KEYWORD_PATTERN, row["keyword"]),
        "has a keyword that is not empty or letters, digits, and underscores "
        "starting with a letter",
    ),
    (
        lambda row: row["uid_type"] in UID_TYPES,
        "has a UID type not listed in UID_TYPES",
    ),
    (
        lambda row: _matches(REGISTRY_PART_PATTERN, row["part"]),
        "has a part that is not a part or standard, a retirement edition, or both",
    ),
    (
        lambda row: row["name"].endswith("(Retired)") == _retired_in_part(row["part"]),
        "is marked retired in its name or its part but not both",
    ),
    (
        lambda row: bool(row["keyword"]) or row["name"].endswith("(Retired)"),
        "has no keyword but is not retired",
    ),
)
_FRAME_OF_REFERENCE_CHECKS: tuple[tuple[Callable[[dict], bool], str], ...] = (
    _UID,
    _NAME,
    (
        lambda row: _matches(UID_KEYWORD_PATTERN, row["keyword"]),
        "has a keyword that is not letters, digits, and underscores starting "
        "with a letter",
    ),
    (
        lambda row: _is_text(row["normative_reference"]),
        "has a normative reference that is not non-empty text",
    ),
)
_CONTEXT_GROUP_CHECKS: tuple[tuple[Callable[[dict], bool], str], ...] = (
    _UID,
    (
        lambda row: row["identifier"] == ""
        or _matches(CONTEXT_GROUP_PATTERN, row["identifier"]),
        "has an identifier that is not empty or of the form CID n",
    ),
    (
        lambda row: _is_text(row["name"], empty=True)
        and bool(row["identifier"]) == bool(row["name"]),
        "has an identifier without a name, or a name without an identifier",
    ),
    (
        lambda row: row["comment"] == ""
        or _matches(CONTEXT_GROUP_COMMENT_PATTERN, row["comment"]),
        "has a comment that is not empty, Retired, or RET with an edition",
    ),
)
_TEMPLATE_CHECKS: tuple[tuple[Callable[[dict], bool], str], ...] = (
    _UID,
    _NAME,
    (
        lambda row: row["uid_type"] in TEMPLATE_UID_TYPES,
        "has a UID type not listed in TEMPLATE_UID_TYPES",
    ),
    (
        lambda row: _matches(REGISTRY_PART_PATTERN, row["part"]),
        "has a part that is not a part or standard",
    ),
)


@dataclasses.dataclass(frozen=True)
class UIDTableSpec:
    """How a table of PS3.6 Annex A is generated, checked, and loaded.

    Attributes
    ----------
    table : str
        The label the generated file records, such as ``"PS3.6 Table A-1"``.
    file : str
        The generated file's name in ``_standard/``.
    row_type : type
        The dataclass each row loads as.
    checks : tuple
        Each check of a row, with what is wrong if it fails, in order.
    unique : tuple of str
        Fields whose values must not repeat, ignoring empty values.
    """

    table: str
    file: str
    row_type: type
    checks: tuple[tuple[Callable[[dict], bool], str], ...]
    unique: tuple[str, ...]

    def problem(self, row: dict) -> str | None:
        """Return what is wrong with a row, or None if it is valid."""
        return _first_problem(self.checks, row)

    @property
    def fields(self) -> tuple[str, ...]:
        """The row type's fields, in order."""
        return tuple(field.name for field in dataclasses.fields(self.row_type))


# Each table of PS3.6 Annex A, keyed by its label in the standard.
UID_TABLES = types.MappingProxyType(
    {
        "Table A-1": UIDTableSpec(
            "PS3.6 Table A-1",
            "uid_values.json",
            RegisteredUID,
            _UID_VALUE_CHECKS,
            ("uid", "keyword"),
        ),
        "Table A-2": UIDTableSpec(
            "PS3.6 Table A-2",
            "frames_of_reference.json",
            WellKnownFrameOfReference,
            _FRAME_OF_REFERENCE_CHECKS,
            ("uid", "keyword"),
        ),
        "Table A-3": UIDTableSpec(
            "PS3.6 Table A-3",
            "context_group_uids.json",
            ContextGroupUID,
            _CONTEXT_GROUP_CHECKS,
            ("uid", "identifier"),
        ),
        "Table A-4": UIDTableSpec(
            "PS3.6 Table A-4",
            "template_uids.json",
            TemplateUID,
            _TEMPLATE_CHECKS,
            ("uid",),
        ),
    }
)


def load_uid_values(path: pathlib.Path | None = None) -> RegistryTable[RegisteredUID]:
    """Load Table A-1 of DICOM PS3.6, the registry of UIDs.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The generated file. Defaults to the one shipped with PyMedPhys.

    Returns
    -------
    RegistryTable of RegisteredUID

    Raises
    ------
    StandardTableError
        For any of the file-level problems
        :func:`~pymedphys._dicom.deidentify.standard.load_table_e1_1` rejects,
        with the acknowledgement "DICOM PS3.6 <edition>, © NEMA"; if a row
        does not have exactly the fields of :class:`RegisteredUID`, or has a
        UID :func:`is_uid` rejects, an empty name, a keyword that is not
        letters, digits, and underscores, a type not in :data:`UID_TYPES`, or
        a part :data:`REGISTRY_PART_PATTERN` does not match; if a row is
        retired in its name or its part but not both, or has no keyword but
        is not retired; or if a UID or keyword repeats.
    """
    return _load_uid_table(_default(path, UID_TABLES["Table A-1"].file), "Table A-1")


def load_frames_of_reference(
    path: pathlib.Path | None = None,
) -> RegistryTable[WellKnownFrameOfReference]:
    """Load Table A-2 of DICOM PS3.6, the well-known frames of reference.

    As :func:`load_uid_values`, except that each row must have a UID, name,
    keyword, and normative reference, and a UID or keyword must not repeat.
    """
    return _load_uid_table(_default(path, UID_TABLES["Table A-2"].file), "Table A-2")


def load_context_group_uids(
    path: pathlib.Path | None = None,
) -> RegistryTable[ContextGroupUID]:
    """Load Table A-3 of DICOM PS3.6, the UIDs of context groups.

    As :func:`load_uid_values`, except that each row must have a UID; an
    identifier of the form ``CID n``, with a name, or neither; and a comment
    that is empty, ``Retired``, or ``RET`` with an edition. A UID or
    identifier must not repeat; names can.
    """
    return _load_uid_table(_default(path, UID_TABLES["Table A-3"].file), "Table A-3")


def load_template_uids(path: pathlib.Path | None = None) -> RegistryTable[TemplateUID]:
    """Load Table A-4 of DICOM PS3.6, the UIDs of HL7 CDA templates.

    As :func:`load_uid_values`, except that each row must have a UID, a name,
    a type in :data:`TEMPLATE_UID_TYPES`, and a part, and a UID must not
    repeat.
    """
    return _load_uid_table(_default(path, UID_TABLES["Table A-4"].file), "Table A-4")


@functools.lru_cache(maxsize=None)
def _load_uid_table(path: pathlib.Path, label: str) -> RegistryTable[Any]:
    spec = UID_TABLES[label]
    document = _read(path, spec.table)
    rows: list[dict] = document["rows"]
    seen: dict[str, set] = {field: set() for field in spec.unique}
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or set(row) != set(spec.fields):
            raise StandardTableError(
                f"{path.name} row {number} does not have exactly the fields "
                + ", ".join(spec.fields)
            )
        problem = spec.problem(row)
        if problem:
            raise StandardTableError(f"{path.name} row {number} {problem}")
        for field in spec.unique:
            value = row[field]
            if value and value in seen[field]:
                raise StandardTableError(
                    f"{path.name} row {number} repeats the "
                    f"{field.replace('_', ' ')} {value!r}"
                )
            seen[field].add(value)
    return RegistryTable(
        edition=document["edition"],
        acknowledgement=document["acknowledgement"],
        rows=tuple(spec.row_type(**row) for row in rows),
    )
