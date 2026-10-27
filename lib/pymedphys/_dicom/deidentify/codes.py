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
Equipment". Table O-1 maps each SNOMED ID, the "SNOMED-RT style" Code Value
of the retired designators SRT, SNM3, and 99SDM, to the SNOMED CT Concept ID
of the same concept, for each SNOMED code that DICOM has used (PS3.16 Section
8.1). ``pymedphys dev deid-tables`` generates each table as a file in
``_standard/`` from the pinned edition, and the loaders here check it as
:func:`~pymedphys._dicom.deidentify.uid_registry.load_registry_table` checks
the tables of PS3.6 Annex A.
"""

from __future__ import annotations

import dataclasses
import functools
import pathlib
import re
import types
import unicodedata
from collections.abc import Callable, Mapping

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
_ESC = "\x1b"
# The designators that coded SNOMED concepts by their SNOMED IDs before DICOM
# moved to SNOMED CT Concept IDs under SCT (PS3.16 Section 8.1).
RETIRED_SNOMED_DESIGNATORS = frozenset({"SRT", "SNM3", "99SDM"})
SNOMED_CT_DESIGNATOR = "SCT"
# A SNOMED CT identifier: 6 to 18 digits without a leading zero. Its last
# digit is a Verhoeff check digit, and the two before it are its partition
# identifier, "00" for a concept and "10" for a concept of an extension.
SNOMED_CT_ID_PATTERN = re.compile(r"[1-9][0-9]{5,17}")
_CONCEPT_PARTITIONS = frozenset({"00", "10"})
# A SNOMED ID, such as "T-D1100": a letter or digit, or two, naming its axis,
# a hyphen, and the code within that axis.
SNOMED_ID_PATTERN = re.compile(r"[A-Z0-9]{1,2}-[A-Z0-9]+")
# The Verhoeff dihedral group's multiplication and permutation tables.
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


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


@dataclasses.dataclass(frozen=True)
class SnomedId:
    """One row of DICOM PS3.16 Table O-1, a SNOMED code's two identifiers.

    Attributes
    ----------
    concept_id : str
        The SNOMED CT Concept ID, the Code Value under SCT, such as
        ``"69536005"``.
    snomed_id : str
        The SNOMED ID of the same concept, the "SNOMED-RT style" Code Value
        under SRT, SNM3, or 99SDM, such as ``"T-D1100"``.
    """

    concept_id: str
    snomed_id: str


def is_snomed_ct_concept_id(value: object) -> bool:
    """Return whether ``value`` is a valid SNOMED CT Concept ID.

    That is 6 to 18 digits without a leading zero, whose partition
    identifier, the two digits before the last, marks a concept, and whose
    last digit is its Verhoeff check digit.

    Examples
    --------
    >>> is_snomed_ct_concept_id("69536005")
    True
    >>> is_snomed_ct_concept_id("69536006")
    False
    """
    if not _matches(SNOMED_CT_ID_PATTERN, value):
        return False
    digits = str(value)
    if digits[-3:-1] not in _CONCEPT_PARTITIONS:
        return False
    check = 0
    for position, digit in enumerate(reversed(digits)):
        check = _VERHOEFF_D[check][_VERHOEFF_P[position % 8][int(digit)]]
    return check == 0


def _is_designator(value: object, max_length: int | None = None) -> bool:
    return _matches(DESIGNATOR_PATTERN, value) and (
        max_length is None or len(str(value)) <= max_length
    )


def _is_short_text(value: object, max_length: int) -> bool:
    """Return whether ``value`` is a valid SH or LO value of at most ``max_length``.

    PS3.5 Table 6.2-1 excludes from both the backslash, which separates
    values, and every control character except ESC, which switches
    character sets.
    """
    return (
        _is_text(value)
        and len(str(value)) <= max_length
        and not any(
            char == "\\" or (unicodedata.category(char) == "Cc" and char != _ESC)
            for char in str(value)
        )
    )


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
        "has a code value that is not non-empty text of at most 16 characters "
        "without a backslash or a control character other than ESC",
    ),
    (
        lambda row: _is_short_text(row["code_meaning"], CODE_MEANING_MAX_LENGTH),
        "has a code meaning that is not non-empty text of at most 64 characters "
        "without a backslash or a control character other than ESC",
    ),
)


_SNOMED_ID_CHECKS: tuple[tuple[Callable[[dict], bool], str], ...] = (
    (
        lambda row: is_snomed_ct_concept_id(row["concept_id"]),
        "has a concept ID that is not 6 to 18 digits without a leading zero, "
        "with a concept's partition identifier and a valid check digit",
    ),
    (
        lambda row: (
            _matches(SNOMED_ID_PATTERN, row["snomed_id"])
            and len(row["snomed_id"]) <= CODE_VALUE_MAX_LENGTH
        ),
        "has a SNOMED ID that is not one or two capital letters or digits, a "
        "hyphen, and capital letters or digits, in at most 16 characters",
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
# Table O-1, which ``pymedphys dev deid-tables`` generates without its
# column of Fully Specified Names, since only the codes are looked up.
SNOMED_ID_TABLE = RegistryTableSpec(
    "PS3.16 Table O-1",
    "snomed_ids.json",
    SnomedId,
    _SNOMED_ID_CHECKS,
    (("concept_id",), ("snomed_id",)),
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
        characters, neither containing a backslash or a control character
        other than ESC (PS3.5 Table 6.2-1, SH and LO); and the pair of
        designator and code value must not repeat.
    """
    spec = CODE_TABLES.get(f"Table CID {cid}")
    if spec is None:
        raise ValueError("only context groups 7050 and 7005 are generated")
    return load_registry_table(spec, path)


def load_snomed_ids(path: pathlib.Path | None = None) -> RegistryTable[SnomedId]:
    """Load Table O-1 of DICOM PS3.16, the SNOMED Concept ID to SNOMED ID mapping.

    As :func:`load_coding_schemes`, except for the row checks: each row must
    have a concept ID that :func:`is_snomed_ct_concept_id` accepts and a
    SNOMED ID that :data:`SNOMED_ID_PATTERN` matches in at most 16
    characters; and neither may repeat, so that each identifies one concept.
    """
    return load_registry_table(SNOMED_ID_TABLE, path)


@functools.lru_cache(maxsize=None)
def _concept_ids() -> Mapping[str, str]:
    return types.MappingProxyType(
        {row.snomed_id: row.concept_id for row in load_snomed_ids().rows}
    )


def snomed_ct_code(designator: str, code_value: str) -> tuple[str, str] | None:
    """Return the SNOMED CT code of a code given by a retired SNOMED designator.

    PS3.16 Section 8.1 requires a receiver to map the SNOMED ID of a code
    whose designator is SRT, SNM3, or 99SDM to the SNOMED CT Concept ID of
    the same concept, and Table O-1 gives that mapping for each SNOMED code
    that DICOM has used.

    Parameters
    ----------
    designator : str
        The Coding Scheme Designator (0008,0102), such as ``"SRT"``.
    code_value : str
        The Code Value (0008,0100), without padding, such as ``"T-D1100"``.

    Returns
    -------
    tuple of str, or None
        ``("SCT", concept_id)`` where ``designator`` is one of
        :data:`RETIRED_SNOMED_DESIGNATORS` and Table O-1 lists
        ``code_value``; otherwise None.

    Examples
    --------
    >>> snomed_ct_code("SRT", "T-D1100")
    ('SCT', '69536005')
    >>> snomed_ct_code("SRT", "T-FIXTURE") is None
    True
    >>> snomed_ct_code("DCM", "T-D1100") is None
    True
    """
    if designator not in RETIRED_SNOMED_DESIGNATORS:
        return None
    concept_id = _concept_ids().get(code_value)
    return None if concept_id is None else (SNOMED_CT_DESIGNATOR, concept_id)
