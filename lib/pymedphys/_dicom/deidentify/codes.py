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

"""Load the DICOM PS3.16 code tables that de-identification uses.

Table 8-1 registers the coding schemes and their UIDs, and Table 8-2 the HL7
version 3 coding schemes. Their UIDs are well-known identifiers that
de-identification retains rather than replaces. CID 7050 holds the codes that
record the profile and options applied, in De-identification Method Code
Sequence (0012,0064), and CID 7005 the purposes of reference for Contributing
Equipment Sequence (0018,A001), including DCM 109104 "De-identifying
Equipment". ``pymedphys dev deid-tables`` generates each table as a file in
``_standard/`` from the pinned edition (design decision D-001), and the
loaders here check it as
:func:`~pymedphys._dicom.deidentify.uid_registry.load_registry_table` checks
the tables of PS3.6 Annex A.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import types
from collections.abc import Callable

from .standard import _is_text
from .uid_registry import (
    RegistryTable,
    RegistryTableSpec,
    _matches,
    is_uid,
    load_registry_table,
)

# A Coding Scheme Designator as the tables publish it, such as "DCM",
# "99SDM", "ISO639_1", or "RFC-3881". In a data set it is SH, at most 16
# characters, which Table 8-1 and the context groups respect; the HL7v3
# designators of Table 8-2 are longer.
DESIGNATOR_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
# The longest Code Value (0008,0100), which is SH, and Code Meaning
# (0008,0104), which is LO.
CODE_VALUE_MAX_LENGTH = 16
CODE_MEANING_MAX_LENGTH = 64


@dataclasses.dataclass(frozen=True)
class CodingScheme:
    """One row of DICOM PS3.16 Table 8-1, the coding schemes.

    Attributes
    ----------
    designator : str
        The Coding Scheme Designator, such as ``"DCM"``. Retired designators
        are listed too, as ``"SRT"`` is beside ``"SCT"``.
    uid : str
        The Coding Scheme UID, or ``""`` where none is registered. Two
        designators of the same scheme share a UID.
    name, responsible_organization : str
        As published, or ``""``.
    resources : str
        The scheme's resources as published, such as
        ``"DOC: http://www.snomed.org/"``, or ``""``.
    description : str
        As published, or ``""``.
    """

    designator: str
    uid: str
    name: str
    responsible_organization: str
    resources: str
    description: str


@dataclasses.dataclass(frozen=True)
class HL7v3CodingScheme:
    """One row of DICOM PS3.16 Table 8-2, the HL7 version 3 coding schemes.

    Attributes
    ----------
    designator : str
        Such as ``"ActCode"``.
    uid : str
    description : str
        As published, or ``""``.
    """

    designator: str
    uid: str
    description: str


@dataclasses.dataclass(frozen=True)
class CodedConcept:
    """One row of a DICOM PS3.16 context group.

    Attributes
    ----------
    scheme_designator : str
        The Coding Scheme Designator, such as ``"DCM"``.
    code_value : str
        Such as ``"113100"`` or ``"FILMD"``.
    code_meaning : str
        Such as ``"Basic Application Confidentiality Profile"``.
    """

    scheme_designator: str
    code_value: str
    code_meaning: str


def _is_designator(value: object, max_length: int | None = None) -> bool:
    return _matches(DESIGNATOR_PATTERN, value) and (
        max_length is None or len(str(value)) <= max_length
    )


def _is_short_text(value: object, max_length: int) -> bool:
    return _is_text(value) and len(str(value)) <= max_length


def _text(field: str, description: str) -> tuple[Callable[[dict], bool], str]:
    return (
        lambda row: _is_text(row[field], empty=True),
        f"has {description} that is not text",
    )


_CODING_SCHEME_CHECKS: tuple[tuple[Callable[[dict], bool], str], ...] = (
    (
        lambda row: _is_designator(row["designator"], CODE_VALUE_MAX_LENGTH),
        "has a designator that is not letters, digits, underscores, periods, "
        "and hyphens, starting with a letter or digit, in at most 16 characters",
    ),
    (
        lambda row: row["uid"] == "" or is_uid(row["uid"]),
        "has a UID that is not empty or numeric components without leading "
        "zeros, in at most 64 characters",
    ),
    _text("name", "a name"),
    _text("responsible_organization", "a responsible organization"),
    _text("resources", "resources"),
    _text("description", "a description"),
)
_HL7V3_CODING_SCHEME_CHECKS: tuple[tuple[Callable[[dict], bool], str], ...] = (
    (
        lambda row: _is_designator(row["designator"]),
        "has a designator that is not letters, digits, underscores, periods, "
        "and hyphens, starting with a letter or digit",
    ),
    (
        lambda row: is_uid(row["uid"]),
        "has a UID that is not numeric components without leading zeros, in at "
        "most 64 characters",
    ),
    _text("description", "a description"),
)
_CODED_CONCEPT_CHECKS: tuple[tuple[Callable[[dict], bool], str], ...] = (
    (
        lambda row: _is_designator(row["scheme_designator"], CODE_VALUE_MAX_LENGTH),
        "has a coding scheme designator that is not letters, digits, "
        "underscores, periods, and hyphens, starting with a letter or digit, in "
        "at most 16 characters",
    ),
    (
        lambda row: _is_short_text(row["code_value"], CODE_VALUE_MAX_LENGTH),
        "has a code value that is not non-empty text of at most 16 characters",
    ),
    (
        lambda row: _is_short_text(row["code_meaning"], CODE_MEANING_MAX_LENGTH),
        "has a code meaning that is not non-empty text of at most 64 characters",
    ),
)


def _context_group(cid: int) -> RegistryTableSpec:
    return RegistryTableSpec(
        f"PS3.16 Table CID {cid}",
        f"cid_{cid}.json",
        CodedConcept,
        _CODED_CONCEPT_CHECKS,
        (("scheme_designator", "code_value"),),
    )


# Each table of PS3.16 that is generated, keyed by its label in the standard.
CODE_TABLES = types.MappingProxyType(
    {
        "Table 8-1": RegistryTableSpec(
            "PS3.16 Table 8-1",
            "coding_schemes.json",
            CodingScheme,
            _CODING_SCHEME_CHECKS,
            (("designator",),),
        ),
        "Table 8-2": RegistryTableSpec(
            "PS3.16 Table 8-2",
            "hl7v3_coding_schemes.json",
            HL7v3CodingScheme,
            _HL7V3_CODING_SCHEME_CHECKS,
            (("designator",), ("uid",)),
        ),
        "Table CID 7050": _context_group(7050),
        "Table CID 7005": _context_group(7005),
    }
)


def load_coding_schemes(
    path: pathlib.Path | None = None,
) -> RegistryTable[CodingScheme]:
    """Load Table 8-1 of DICOM PS3.16, the coding schemes.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The generated file. Defaults to the one shipped with PyMedPhys.

    Returns
    -------
    RegistryTable of CodingScheme

    Raises
    ------
    StandardTableError
        For any of the file-level problems
        :func:`~pymedphys._dicom.deidentify.standard.load_table_e1_1` rejects,
        with the acknowledgement "DICOM PS3.16 <edition>, © NEMA"; if a row
        does not have exactly the fields of :class:`CodingScheme`, has a
        designator that :data:`DESIGNATOR_PATTERN` does not match or that is
        longer than 16 characters, has a UID that is neither empty nor
        accepted by :func:`~pymedphys._dicom.deidentify.uid_registry.is_uid`,
        or has other values that are not text; or if a designator repeats.
        UIDs can repeat.
    """
    return load_registry_table(CODE_TABLES["Table 8-1"], path)


def load_hl7v3_coding_schemes(
    path: pathlib.Path | None = None,
) -> RegistryTable[HL7v3CodingScheme]:
    """Load Table 8-2 of DICOM PS3.16, the HL7 version 3 coding schemes.

    As :func:`load_coding_schemes`, except that a designator can be of any
    length, each row must have a UID, and a UID must not repeat.
    """
    return load_registry_table(CODE_TABLES["Table 8-2"], path)


def load_context_group(
    cid: int, path: pathlib.Path | None = None
) -> RegistryTable[CodedConcept]:
    """Load a context group of DICOM PS3.16 that de-identification uses.

    Parameters
    ----------
    cid : int
        7050, De-identification Method, or 7005, Contributing Equipment
        Purpose of Reference.
    path : pathlib.Path, optional
        The generated file. Defaults to the one shipped with PyMedPhys.

    Returns
    -------
    RegistryTable of CodedConcept

    Raises
    ------
    ValueError
        If ``cid`` is not 7050 or 7005, the context groups that are
        generated.
    StandardTableError
        As :func:`load_coding_schemes`, except for the row checks: each row
        must have a coding scheme designator as Table 8-1 requires, a code
        value of at most 16 characters, and a code meaning of at most 64
        characters, and the pair of designator and code value must not
        repeat.
    """
    spec = CODE_TABLES.get(f"Table CID {cid}")
    if spec is None:
        raise ValueError("only context groups 7050 and 7005 are generated")
    return load_registry_table(spec, path)
