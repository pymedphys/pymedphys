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

"""Name the residual findings that kept vocabulary, labels, or options explain.

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
- :attr:`Exemption.SHIFTED_DATE`: a date or datetime found in a date that
  Modified Dates shifted, equal to the whole shifted value, which only
  coincides with it (D-039, :mod:`~pymedphys._dicom.deidentify.residual_shifts`).
  It applies to a finding that would otherwise withhold the file.
- :attr:`Exemption.VENDOR_CREATOR`: the finding's source is a private
  creator element, (gggg,0010) to (gggg,00FF) of an odd group, or Private
  Creator Reference (0008,0302) in an item of Private Data Element
  Characteristics Sequence (0008,0300), which names one, and each of its values
  collected for the subject is, without trailing spaces and NULs, exactly
  one of the private creators that the pinned PS3.15 Table E.3.10-1 lists
  (:func:`vendor_creators`), wherever in the data set the finding is.
- :attr:`Exemption.RETAINED_TEXT`: the finding is in a text attribute that
  a selected option keeps, such as Station Name (0008,1010) under Retain
  Device Identity, and its source is a private data element or an attribute
  of that option, such as Station AE Title (0008,0055)
  (:func:`~pymedphys._dicom.deidentify.option_kept.retained_text`).
- :attr:`Exemption.RETAINED_VALUE`: a value of the element, a date, time,
  or datetime that a selected option keeps, equals a whole value of the
  finding's source
  (:func:`~pymedphys._dicom.deidentify.option_kept.retained_value`). It also
  applies to a finding of a date or datetime, which would otherwise
  withhold the file (:func:`retained_date`).
- :attr:`Exemption.UNWRITTEN_CODE_MEANING`: the finding's source is a Code
  Meaning (0008,0104), only instances that the run does not write, such as
  a sequestered dose report, collected its values for the subject, and each
  of them was collected from a code item whose own Coding Scheme Designator
  is one that the pinned PS3.16 Table 8-1 lists
  (:func:`standard_code_meanings`), wherever in the data set the finding is.
- :attr:`Exemption.UNWRITTEN_UID`: a UID found in a UID that a selected
  option keeps, equal to a whole value of it, whose source's values only
  instances that the run does not write collected (:func:`unwritten_uid`).
  It applies to a finding that would otherwise withhold the file.

The search records one finding of a source in each element, so each
exemption is decided by the whole element: a CS value is exempt only if
every one of its values is a term; and a source's values are pooled across
the subject, so a private creator is exempt only if all of them are a
vendor's, a date only if each of them that could be in the element equals a
whole kept value, and a Code Meaning or a UID from unwritten instances only
if no written instance collected any of them. A finding in an element that holds a byte
outside ISO 646's printable characters, a finding of any other kind, and a
finding outside the data set are never exempt. Kept values are read from the
written file's bytes, as text in ISO 646, never decoded by pydicom, and none
is reported.
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
from .option_kept import kept_by, retained_text, retained_value
from .residuals import Finding, SourceValue
from .standard import dictionary_attribute, load_table_e3_10_1
from .uid_registry import RegistryTable, RegistryTableSpec, load_registry_table

_DESIGNATOR = "(0008,0102)"
_CODE_MEANING = "(0008,0104)"
# Private Creator Reference, in an item of Private Data Element
# Characteristics Sequence.
_CREATOR_REFERENCE = "(0008,0302)"
_CHARACTERISTICS = "(0008,0300)"
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
    SHIFTED_DATE = "shifted-date"  # equal to a date that Modified Dates shifted
    VENDOR_CREATOR = "vendor-creator"  # a private creator of Table E.3.10-1
    RETAINED_TEXT = "retained-text"  # in text an option keeps, from its own or private
    RETAINED_VALUE = "retained-value"  # equal to a date or time an option keeps
    # the meaning of a code of a scheme of Table 8-1, from unwritten instances only
    UNWRITTEN_CODE_MEANING = "unwritten-code-meaning"
    UNWRITTEN_UID = "unwritten-uid"  # in a UID an option keeps, from unwritten only


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
) -> Mapping[ElementPath, tuple[SourceValue, ...]]:
    """Return the collected values of each source, pooled across the subject."""
    values: dict[ElementPath, list[SourceValue]] = {}
    for each in collected:
        values.setdefault(each.source, []).append(each)
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

    def text(self, path: ElementPath) -> str | None:
        """Return an element's whole value, with its separators, or ``None``.

        ``None`` as for :meth:`values`; trailing NULs are left out.
        """
        extent = self._extents.get(path)
        if extent is None or extent.items is not None:
            return None
        raw = bytes(self._written[extent.value_start : extent.end]).rstrip(b"\x00")
        if any(byte < 0x20 or byte > 0x7E for byte in raw):
            return None
        return raw.decode("ascii")

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
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
    options: tuple[str, ...] = (),
    meanings: frozenset[SourceValue] = frozenset(),
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
    options : tuple of str, optional
        The run's options. With none, no option explains a finding.
    meanings : frozenset of SourceValue, optional
        The Code Meanings in ``sources`` that only instances the run does
        not write collected, each from an item whose own Coding Scheme
        Designator Table 8-1 lists (:func:`standard_code_meanings`).

    Returns
    -------
    Exemption or None
        As the module describes, or ``None`` if none applies.
    """
    element = finding.location.element
    in_data_set = finding.location.region is Region.DATA_SET
    values = kept.values(element) if in_data_set and element is not None else None
    if element is None or values is None:
        return None
    tag = element.tag
    terms = defined_terms().get(tag)
    if terms is not None and any(values) and all(not v or v in terms for v in values):
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
    why = _retained(finding, kept, sources, options)
    if why is None and _unwritten_code_meaning(finding.source, sources, meanings):
        why = Exemption.UNWRITTEN_CODE_MEANING
    return why


def _retained(
    finding: Finding,
    kept: KeptValues,
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
    options: tuple[str, ...],
) -> Exemption | None:
    """Return whether a value that an option keeps explains a text finding."""
    element = finding.location.element
    if element is not None and retained_text(element.tag, finding.source, options):
        return Exemption.RETAINED_TEXT
    return retained_date(finding, kept, sources, options)


def retained_date(
    finding: Finding,
    kept: KeptValues,
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
    options: tuple[str, ...],
) -> Exemption | None:
    """Return whether a date or time that an option keeps explains a finding.

    For a finding inside the data set, of text, a date, or a datetime, as
    :attr:`Exemption.RETAINED_VALUE` describes; ``None`` otherwise.
    """
    element = finding.location.element
    if finding.location.region is not Region.DATA_SET or element is None:
        return None
    values, text = kept.values(element), kept.text(element)
    if (
        values is None
        or text is None
        or not retained_value(
            element,
            values,
            text,
            finding.source,
            sources.get(finding.source, ()),
            options,
        )
    ):
        return None
    return Exemption.RETAINED_VALUE


def unwritten_uid(
    finding: Finding,
    kept: KeptValues,
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
    unwritten: frozenset[SourceValue],
    options: tuple[str, ...],
) -> Exemption | None:
    """Return whether a kept UID explains a UID found from unwritten instances.

    Parameters
    ----------
    finding : Finding
        A finding that would otherwise withhold its file.
    kept : KeptValues
        The written file's values.
    sources : mapping
        The collected values of each source (:func:`source_values`).
    unwritten : frozenset of SourceValue
        The values in ``sources`` that only instances the run does not
        write collected.
    options : tuple of str
        The run's options.

    Returns
    -------
    Exemption or None
        :attr:`Exemption.UNWRITTEN_UID` where the finding is in a data set
        element of an attribute that a selected option keeps
        (:func:`~pymedphys._dicom.deidentify.option_kept.kept_by`), which the
        pinned dictionary gives only VR UI, one of the source's values
        equals a whole value of that element, and every value of the source
        is in ``unwritten``: the instances that held the source are not
        released, and the option releases the UID where it is found. A UID
        that a written instance also collected at the source, such as a
        reference that the option replaced while keeping the UID it names,
        one found anywhere else, such as in text or in the File Meta
        Information, and one that equals no whole kept value, as where it is
        found only inside a longer kept UID, give ``None``.
    """
    element = finding.location.element
    if finding.location.region is not Region.DATA_SET or element is None:
        return None
    attribute = dictionary_attribute(element.tag)
    if (
        attribute is None
        or attribute.vrs != ("UI",)
        or element.tag not in kept_by(options)
    ):
        return None
    values = sources.get(finding.source, ())
    if not values or not all(each in unwritten for each in values):
        return None
    written = kept.values(element)
    if written is None:
        return None
    if any(
        part and part in written
        for each in values
        if isinstance(each.value, str)
        for part in (value.strip(" \x00") for value in each.value.split("\\"))
    ):
        return Exemption.UNWRITTEN_UID
    return None


def standard_code_meanings(
    collected: tuple[SourceValue, ...],
) -> frozenset[SourceValue]:
    """Return the Code Meanings of one instance's values that name a standard code.

    Parameters
    ----------
    collected : tuple of SourceValue
        The values that one instance collected, never values pooled across
        a subject, whose places can be the same in another instance.

    Returns
    -------
    frozenset of SourceValue
        Each Code Meaning (0008,0104) in an item whose own Coding Scheme
        Designator (0008,0102), collected from the same instance at the same
        item, is one value that is, without trailing spaces and NULs, a
        designator that the pinned PS3.16 Table 8-1 lists. A meaning whose
        item has a local designator, such as one starting with 99, none, as
        a URN code may have, or one that the instance did not collect, is
        not one, since a local code's meaning can be the site's own text.
    """
    designators = {
        each.source.items: each.value
        for each in collected
        if each.source.tag == _DESIGNATOR and each.source.items
    }
    return frozenset(
        each
        for each in collected
        if each.source.tag == _CODE_MEANING
        and each.source.items
        and _listed(designators.get(each.source.items))
    )


def _listed(designator: str | bytes | None) -> bool:
    """Return whether a designator is one value that Table 8-1 lists."""
    return isinstance(designator, str) and designator.rstrip(" \x00") in _designators()


def _unwritten_code_meaning(
    source: ElementPath,
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
    meanings: frozenset[SourceValue],
) -> bool:
    """Return whether a source is a standard code's meaning from unwritten instances.

    The source must be a Code Meaning (0008,0104) in an item, and every value
    of it collected for the subject must be in ``meanings``: collected only
    by instances that the run does not write, each from an item whose own
    Coding Scheme Designator Table 8-1 lists.
    """
    if source.tag != _CODE_MEANING or not source.items:
        return False
    values = sources.get(source, ())
    return bool(values) and all(each in meanings for each in values)


def _vendor_creator(
    source: ElementPath, sources: Mapping[ElementPath, tuple[SourceValue, ...]]
) -> bool:
    """Return whether every value of a private creator source is a vendor's.

    A source names a private creator where it is one, or where it is
    Private Creator Reference (0008,0302) in Private Data Element
    Characteristics Sequence (0008,0300). The values of a source are pooled
    across the subject, so a finding of the source could be any of them.
    """
    group, element = int(source.tag[1:5], 16), int(source.tag[6:10], 16)
    creator = group % 2 == 1 and 0x0010 <= element <= 0x00FF
    reference = (
        source.tag == _CREATOR_REFERENCE
        and bool(source.items)
        and source.items[-1][0] == _CHARACTERISTICS
    )
    if not creator and not reference:
        return False
    values = sources.get(source, ())
    return bool(values) and all(
        isinstance(each.value, str) and each.value.rstrip(" \x00") in vendor_creators()
        for each in values
    )


def _equipment_source(source: ElementPath) -> bool:
    """Return whether a source names equipment or is a private data element."""
    group, element = int(source.tag[1:5], 16), int(source.tag[6:10], 16)
    private_data = group % 2 == 1 and element >= 0x1000
    return private_data or source.tag in EQUIPMENT_SOURCES
