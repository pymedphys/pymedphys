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

"""Name the residual text findings that kept vocabulary or a vendor's label explains.

The residual search finds the text of a removed value wherever it is in a
written file (:mod:`~pymedphys._dicom.deidentify.residuals`), and the release
gate sends a file to QC review for other text found inside its data set
(D-027). Some kept values are standard vocabulary or equipment names, which
removed values often equal: a removed Scatter Correction Method of ``NONE``
is found in a kept Collimator Type of ``NONE``. :func:`exemption` names the
reason that such a finding is not a reason for review (D-032), or returns
``None``:

- :attr:`Exemption.STANDARD_TERM`: the finding is in a value of an attribute
  of VR CS, each of whose values is an Enumerated Value or Defined Term of
  that attribute in the pinned PS3.3 (:func:`load_defined_terms`) or, for
  Body Part Examined (0018,0015), whose Defined Terms PS3.3 leaves to
  PS3.16 Annex L, in the pinned Annex L (:func:`load_body_part_terms`).
- :attr:`Exemption.STANDARD_CODE`: the finding is in the Code Value,
  Coding Scheme Designator, Coding Scheme Version, Code Meaning, Long Code
  Value, or URN Code Value of a code item whose Coding Scheme Designator is
  one that the pinned PS3.16 Table 8-1 lists.
- :attr:`Exemption.EQUIPMENT`: the finding is in Manufacturer (0008,0070),
  Manufacturer's Model Name (0008,1090), or Software Versions (0018,1020),
  which the Basic Profile keeps, and its source is a private data element or
  itself names equipment: one of those three attributes, or Secondary
  Capture Device Manufacturer (0018,1016), its Model Name (0018,1018), or
  its Software Versions (0018,1019).
- :attr:`Exemption.VENDOR_CREATOR`: the finding's source is a private
  creator element, (gggg,0010) to (gggg,00FF) of an odd group, and each
  of its values collected for the subject is, without trailing spaces and
  NULs, exactly one of the private creators that the pinned PS3.15 Table
  E.3.10-1 lists (:func:`vendor_creators`), wherever in the data set the
  finding is.

The search records one finding of a source in each element, so each
exemption is decided by the whole element: a CS value is exempt only if
every one of its values is a term; and a source's values are pooled across
the subject, so a private creator is exempt only if all of them are a
vendor's. A finding of any other kind, or outside
the data set, is never exempt. Kept values are read from the written file's
bytes, as text in ISO 646, never decoded by pydicom, and none is reported.
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import pathlib
import re
from collections.abc import Mapping

from .codes import load_coding_schemes
from .file_layout import ElementPath, Region, read_file_layout
from .residuals import Finding, SourceValue
from .standard import load_table_e3_10_1
from .uid_registry import RegistryTable, RegistryTableSpec, load_registry_table

_DESIGNATOR = "(0008,0102)"
BODY_PART_EXAMINED = "(0018,0015)"
# Code Value, Coding Scheme Version, Code Meaning, Long Code Value, and URN
# Code Value, which the designator in their item qualifies.
_CODE_ITEM = frozenset(
    {"(0008,0100)", "(0008,0103)", "(0008,0104)", "(0008,0119)", "(0008,0120)"}
)
# Manufacturer, Manufacturer's Model Name, and Software Versions.
EQUIPMENT_NAMES = frozenset({"(0008,0070)", "(0008,1090)", "(0018,1020)"})
# The equipment names, and Secondary Capture Device Manufacturer, its
# Manufacturer's Model Name, and its Software Versions.
EQUIPMENT_SOURCES = EQUIPMENT_NAMES | {"(0018,1016)", "(0018,1018)", "(0018,1019)"}
_TAG = re.compile(r"\([0-9A-F]{4},[0-9A-F]{4}\)")
# A value that VR CS can hold (PS3.5 Table 6.2-1), without its padding.
_CS_VALUE = re.compile(r"[A-Z0-9 _]{1,16}")
_PADDING = b" \x00"


class Exemption(enum.Enum):
    """Why a residual text finding is not a reason for review (D-032)."""

    STANDARD_TERM = "standard-term"  # every value a term of its CS attribute
    STANDARD_CODE = "standard-code"  # in a code item of a scheme of Table 8-1
    EQUIPMENT = "equipment"  # an equipment name, found from equipment or private
    VENDOR_CREATOR = "vendor-creator"  # a private creator of Table E.3.10-1


@dataclasses.dataclass(frozen=True)
class DefinedTerm:
    """An Enumerated Value or Defined Term of a CS attribute in PS3.3.

    Attributes
    ----------
    tag : str
        The attribute's tag, such as ``"(0018,1181)"``.
    term : str
        Such as ``"PARA"``.
    """

    tag: str
    term: str


DEFINED_TERMS_TABLE = RegistryTableSpec(
    "PS3.3 Enumerated Values and Defined Terms",
    "defined_terms.json",
    DefinedTerm,
    (
        (
            lambda row: (
                isinstance(row["tag"], str) and bool(_TAG.fullmatch(row["tag"]))
            ),
            "has a tag that is not (gggg,eeee) in upper-case hexadecimal",
        ),
        (
            lambda row: (
                isinstance(row["term"], str) and bool(_CS_VALUE.fullmatch(row["term"]))
            ),
            "has a term that VR CS cannot hold",
        ),
    ),
    (("tag", "term"),),
)


@dataclasses.dataclass(frozen=True)
class BodyPartTerm:
    """A Defined Term of Body Part Examined (0018,0015) in PS3.16 Annex L.

    Attributes
    ----------
    term : str
        Such as ``"CHEST"``.
    """

    term: str


BODY_PART_TERMS_TABLE = RegistryTableSpec(
    "PS3.16 Annex L Body Part Examined Defined Terms",
    "body_part_terms.json",
    BodyPartTerm,
    (
        (
            lambda row: (
                isinstance(row["term"], str) and bool(_CS_VALUE.fullmatch(row["term"]))
            ),
            "has a term that VR CS cannot hold",
        ),
    ),
    (("term",),),
)


def load_defined_terms(path: pathlib.Path | None = None) -> RegistryTable[DefinedTerm]:
    """Load the Enumerated Values and Defined Terms of PS3.3's CS attributes.

    Parameters
    ----------
    path : pathlib.Path, optional
        The generated file. Defaults to the one shipped with PyMedPhys.

    Returns
    -------
    RegistryTable of DefinedTerm

    Raises
    ------
    StandardTableError
        If the file is not a valid generated table.
    """
    return load_registry_table(DEFINED_TERMS_TABLE, path)


def load_body_part_terms(
    path: pathlib.Path | None = None,
) -> RegistryTable[BodyPartTerm]:
    """Load the Defined Terms of Body Part Examined from PS3.16 Annex L.

    Parameters
    ----------
    path : pathlib.Path, optional
        The generated file. Defaults to the one shipped with PyMedPhys.

    Returns
    -------
    RegistryTable of BodyPartTerm

    Raises
    ------
    StandardTableError
        If the file is not a valid generated table.
    """
    return load_registry_table(BODY_PART_TERMS_TABLE, path)


@functools.cache
def defined_terms() -> Mapping[str, frozenset[str]]:
    """Return the terms of each CS attribute, by tag, from the shipped tables."""
    terms: dict[str, set[str]] = {}
    for row in load_defined_terms().rows:
        terms.setdefault(row.tag, set()).add(row.term)
    terms.setdefault(BODY_PART_EXAMINED, set()).update(
        row.term for row in load_body_part_terms().rows
    )
    return {tag: frozenset(each) for tag, each in terms.items()}


@functools.cache
def vendor_creators() -> frozenset[str]:
    """Return the private creators that PS3.15 Table E.3.10-1 lists."""
    return frozenset(row.private_creator for row in load_table_e3_10_1().attributes)


def source_values(
    collected: tuple[SourceValue, ...],
) -> Mapping[ElementPath, tuple[str | bytes, ...]]:
    """Return the collected values of each source, pooled across the subject."""
    values: dict[ElementPath, list[str | bytes]] = {}
    for each in collected:
        values.setdefault(each.source, []).append(each.value)
    return {source: tuple(each) for source, each in values.items()}


@functools.cache
def _designators() -> frozenset[str]:
    return frozenset(row.designator for row in load_coding_schemes().rows)


class KeptValues:
    """The values of a written file's data set elements, read as ISO 646 text.

    Parameters
    ----------
    written : bytes, bytearray, or memoryview
        The whole written file.
    """

    def __init__(self, written: bytes | bytearray | memoryview) -> None:
        self._written = written
        layout = read_file_layout(written)
        self._extents = {
            extent.location.element: extent
            for extent in layout.elements
            if extent.location.region is Region.DATA_SET
            and extent.location.element is not None
        }

    def __repr__(self) -> str:
        return f"KeptValues(elements={len(self._extents)})"

    def values(self, path: ElementPath) -> tuple[str, ...] | None:
        """Return an element's values without padding, or ``None``.

        ``None`` where the element is not in the data set, has items, or
        holds a byte outside ISO 646's printable characters.
        """
        extent = self._extents.get(path)
        if extent is None or extent.items is not None:
            return None
        raw = bytes(self._written[extent.value_start : extent.end])
        if any(byte < 0x20 or byte > 0x7E for byte in raw.rstrip(b"\x00")):
            return None
        return tuple(
            value.strip(_PADDING).decode("ascii") for value in raw.split(b"\\")
        )


def exemption(
    finding: Finding,
    kept: KeptValues,
    sources: Mapping[ElementPath, tuple[str | bytes, ...]],
) -> Exemption | None:
    """Return why a text finding inside the data set is not a reason for review.

    Parameters
    ----------
    finding : Finding
        A finding that would otherwise send its file to QC review.
    kept : KeptValues
        The written file's values.
    sources : mapping
        The collected values of each source (:func:`source_values`).

    Returns
    -------
    Exemption or None
        As the module describes, or ``None`` if none applies.
    """
    location = finding.location
    element = location.element
    if location.region is not Region.DATA_SET or element is None:
        return None
    tag = element.tag
    terms = defined_terms().get(tag)
    if terms is not None:
        values = kept.values(element)
        if values and any(values) and all(not v or v in terms for v in values):
            return Exemption.STANDARD_TERM
    if element.items and (tag == _DESIGNATOR or tag in _CODE_ITEM):
        designator = kept.values(ElementPath(element.items, _DESIGNATOR))
        if designator is not None and len(designator) == 1:
            if designator[0] in _designators():
                return Exemption.STANDARD_CODE
    if tag in EQUIPMENT_NAMES and _equipment_source(finding.source):
        return Exemption.EQUIPMENT
    if _vendor_creator(finding.source, sources):
        return Exemption.VENDOR_CREATOR
    return None


def _vendor_creator(
    source: ElementPath, sources: Mapping[ElementPath, tuple[str | bytes, ...]]
) -> bool:
    """Return whether every value of a private creator source is a vendor's.

    The values of a source are pooled across the subject, so a finding of
    the source could be any of them.
    """
    group, element = int(source.tag[1:5], 16), int(source.tag[6:10], 16)
    if group % 2 == 0 or not 0x0010 <= element <= 0x00FF:
        return False
    values = sources.get(source, ())
    return bool(values) and all(
        isinstance(value, str) and value.rstrip(" \x00") in vendor_creators()
        for value in values
    )


def _equipment_source(source: ElementPath) -> bool:
    """Return whether a source names equipment or is a private data element."""
    group, element = int(source.tag[1:5], 16), int(source.tag[6:10], 16)
    private_data = group % 2 == 1 and element >= 0x1000
    return private_data or source.tag in EQUIPMENT_SOURCES
