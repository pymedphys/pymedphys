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

"""Recognise residual text in kept text made only of reviewed vocabulary.

A procedure or protocol code of a local scheme, one that PS3.16 Table 8-1
does not list, is kept with its Code Meaning (0008,0104) under the Basic
Profile, and a scanner often writes the same text as a description that the
profile removes, such as Study Description (0008,1030). Under Clean
Descriptors, a kept technique descriptor, such as Series Description
(0008,103E) or Performed Procedure Step Description (0040,0254), often
repeats such a description too. The residual search then finds the removed
description in the kept value (D-027), and no standard exemption applies,
since a local scheme's meaning, and a descriptor, can be the site's own text
(D-032). This module reads that text instead. :func:`vocabulary_meaning`
finds that the finding is not a reason for review
(:attr:`~pymedphys._dicom.deidentify.residual_exemptions.Exemption.VOCABULARY_MEANING`)
only where all of these hold:

- it is inside the data set, in a Code Meaning (0008,0104) in a sequence
  item, at any depth, whatever the item's Coding Scheme Designator;
- every value of that element, read from the written file's bytes as ISO
  646 text, is kept by the word rules of the reviewed technique vocabulary
  that PyMedPhys ships (D-036), as
  :meth:`~pymedphys._dicom.deidentify.technique_descriptors.TechniqueVocabulary.word_rejection`
  reads them: printable, with no date, time, long number, personal name,
  initials, age, or sex, and every word a vocabulary word, a unit, or a
  reviewed reconstruction kernel;
- no value of that element echoes an identifier of the subject, as
  :func:`~pymedphys._dicom.deidentify.reviewed_descriptors.echoes_identifier`
  finds it, among every person name and every Patient ID (0010,0020),
  Issuer of Patient ID (0010,0021), and Other Patient IDs (0010,1000) that
  the run collected for the subject, at any depth;
- the finding's source is one of :data:`DESCRIPTIVE_SOURCES`, at any depth:
  a description, comment, or technique descriptor of the study, procedure,
  series, or image, a contrast agent or radiopharmaceutical, or an SR
  TEXT content item's value, each of which describes the examination
  rather than naming anyone or anything. Every other source stays under
  review, so an attribute that names a place, an organisation, a station,
  or a device, such as Station Name or Gantry ID, or a private element,
  which can hold any of them, is never exempt, however the kept meaning
  reads: a station named ``HEAD`` found in a kept ``CT HEAD`` is still seen;
  and
- the source is not in an item of one of :data:`INSTITUTIONAL_SEQUENCES`,
  nor one of :data:`INSTITUTIONAL_SOURCES` (:func:`institutional`), which
  list the attributes of PS3.15 Table E.1-1 that name, code, or address a
  place, an organisation, or a device. None of them is descriptive, so this
  repeats the test above for a descriptive attribute nested in such an item.

:func:`vocabulary_descriptor` finds the same of a finding in a technique
descriptor
(:attr:`~pymedphys._dicom.deidentify.residual_exemptions.Exemption.VOCABULARY_DESCRIPTOR`):
one of the attributes whose values the shipped vocabulary's automatic tier
may keep, such as Series Description, Protocol Name (0018,1030), or
Performed Procedure Step Description, at the top level or in an item, at any
depth, under the other conditions above. Its values are read as
descriptor cleaning reads them: split at backslashes where the element's VR
holds several values (SH, LO, or UC), and whole otherwise, as Derivation
Description (0008,2111), whose VR is ST, is.

Whatever removed text is found inside a value made only of technique and
anatomy words is itself such words, so the finding reveals nothing that the
kept value does not. A value with any other word stays under review, as
does any other kept element. The vocabulary, and its list of technique
descriptors, are always the ones that PyMedPhys ships, never ones that a
run gives Clean Descriptors, so each exemption is the same in every run, and
the method digest covers them through the engine's files under every policy
(D-024).

Only a text finding is read: a person name, UID, date, datetime, or direct
identifier found anywhere still withholds the file. No value is reported.
"""

from __future__ import annotations

from collections.abc import Mapping

from .file_layout import ElementPath, Region
from .residual_exemptions import Exemption, KeptValues
from .residuals import Finding, SourceValue
from .reviewed_descriptors import echoes_identifier
from .standard import dictionary_attribute
from .technique_descriptors import TechniqueVocabulary, load_technique_vocabulary

_CODE_MEANING = "(0008,0104)"
# The removed values that describe the examination, whose finding in a kept
# meaning of vocabulary words can be released.
DESCRIPTIVE_SOURCES = frozenset(
    {
        # Descriptions and comments of the study, procedure, and image.
        "(0008,1030)",  # Study Description
        "(0032,1060)",  # Requested Procedure Description
        "(0040,0007)",  # Scheduled Procedure Step Description
        "(0040,0254)",  # Performed Procedure Step Description
        "(0040,1400)",  # Requested Procedure Comments
        "(0032,4000)",  # Study Comments
        "(0040,0280)",  # Comments on the Performed Procedure Step
        "(0040,0400)",  # Comments on the Scheduled Procedure Step
        "(0020,4000)",  # Image Comments
        # Technique descriptors (D-036) and the device's processing.
        "(0008,103E)",  # Series Description
        "(0018,1030)",  # Protocol Name
        "(0018,0024)",  # Sequence Name
        "(0008,2111)",  # Derivation Description
        "(0028,1055)",  # Window Center & Width Explanation
        "(0054,1101)",  # Attenuation Correction Method
        "(0054,1105)",  # Scatter Correction Method
        "(0054,1103)",  # Reconstruction Method
        "(0018,1400)",  # Acquisition Device Processing Description
        # What was given.
        "(0018,0010)",  # Contrast/Bolus Agent
        "(0018,1040)",  # Contrast/Bolus Route
        "(0018,0031)",  # Radiopharmaceutical
        # An SR TEXT content item's value.
        "(0040,A160)",  # Text Value
    }
)
# The attributes of PS3.15 Table E.1-1 that name or address a place, an
# organisation, or a device, whose value a site can write as words of the
# vocabulary. None is descriptive; listing them also keeps such a source
# out of any rule that reads this module.
INSTITUTIONAL_SOURCES = frozenset(
    {
        # Institutions and departments.
        "(0008,0080)",  # Institution Name
        "(0008,0081)",  # Institution Address
        "(0008,1040)",  # Institutional Department Name
        "(0038,0400)",  # Patient's Institution Residence
        "(0038,001E)",  # Scheduled Patient Institution Residence
        # Stations and their AE titles.
        "(0008,1010)",  # Station Name
        "(0040,0010)",  # Scheduled Station Name
        "(0040,0242)",  # Performed Station Name
        "(0008,0055)",  # Station AE Title
        "(0040,0001)",  # Scheduled Station AE Title
        "(0040,0241)",  # Performed Station AE Title
        "(0008,0054)",  # Retrieve AE Title
        "(0032,1021)",  # Scheduled Study Location AE Title
        # Locations.
        "(0038,0300)",  # Current Patient Location
        "(0040,2009)",  # Order Enterer's Location
        "(0040,0243)",  # Performed Location
        "(0040,1005)",  # Requested Procedure Location
        "(0040,0011)",  # Scheduled Procedure Step Location
        "(0032,1020)",  # Scheduled Study Location
        # Organisations and clinical trial sites.
        "(0040,4036)",  # Human Performer's Organization
        "(0010,2299)",  # Responsible Organization
        "(0040,A027)",  # Verifying Organization
        "(0012,0060)",  # Clinical Trial Coordinating Center Name
        "(0012,0030)",  # Clinical Trial Site ID
        "(0012,0031)",  # Clinical Trial Site Name
        "(0012,0032)",  # Issuer of Clinical Trial Site ID
        # Addresses and telephone numbers.
        "(0010,1040)",  # Patient's Address
        "(0040,1102)",  # Person's Address
        "(0008,0092)",  # Referring Physician's Address
        "(0040,A353)",  # Address (Trial)
        "(4008,011A)",  # Distribution Address
        "(0010,2154)",  # Patient's Telephone Numbers
        "(0040,1103)",  # Person's Telephone Numbers
        "(0008,0094)",  # Referring Physician's Telephone Numbers
        "(0040,A354)",  # Telephone Number (Trial)
        # Devices' identifiers.
        "(0018,1000)",  # Device Serial Number
        "(0018,1010)",  # Secondary Capture Device ID
        "(0018,1011)",  # Hardcopy Creation Device ID
        "(0020,3401)",  # Modifying Device ID
        "(3010,001B)",  # Device Alternate Identifier
        "(3010,002D)",  # Device Label
        "(3010,0043)",  # Manufacturer's Device Identifier
        "(0018,1008)",  # Gantry ID
        "(0018,1007)",  # Cassette ID
        "(0018,1004)",  # Plate ID
        "(0018,1005)",  # Generator ID
        # Clinical trial organisations.
        "(0012,0010)",  # Clinical Trial Sponsor Name
        "(0012,0081)",  # Clinical Trial Protocol Ethics Committee Name
    }
)
# The sequences of Table E.1-1 whose items code or name one of them.
INSTITUTIONAL_SEQUENCES = frozenset(
    {
        "(0008,0082)",  # Institution Code Sequence
        "(0008,1041)",  # Institutional Department Type Code Sequence
        "(0040,4025)",  # Scheduled Station Name Code Sequence
        "(0040,4028)",  # Performed Station Name Code Sequence
        "(0040,4027)",  # Scheduled Station Geographic Location Code Sequence
        "(0040,4030)",  # Performed Station Geographic Location Code Sequence
        "(0040,A07C)",  # Custodial Organization Sequence
    }
)
# Patient ID, Issuer of Patient ID, and Other Patient IDs, as descriptor
# cleaning checks for echoes of them with every person name.
IDENTIFIER_TAGS = frozenset({"(0010,0020)", "(0010,0021)", "(0010,1000)"})
# The VRs that hold several values, split at backslashes, as descriptor
# cleaning reads a technique descriptor's.
MULTI_VALUED_VRS = frozenset({"SH", "LO", "UC"})


def vocabulary_meaning(
    finding: Finding,
    kept: KeptValues,
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
) -> Exemption | None:
    """Return whether a kept Code Meaning of reviewed vocabulary explains a finding.

    Parameters
    ----------
    finding : Finding
        A text finding that would otherwise send its file to QC review.
    kept : KeptValues
        The written file's values.
    sources : mapping
        The collected values of each source, pooled across the subject
        (:func:`~pymedphys._dicom.deidentify.residual_exemptions.source_values`).

    Returns
    -------
    Exemption or None
        :attr:`~pymedphys._dicom.deidentify.residual_exemptions.Exemption.VOCABULARY_MEANING`
        as the module describes, or ``None``.
    """
    element = finding.location.element
    if (
        finding.location.region is not Region.DATA_SET
        or element is None
        or element.tag != _CODE_MEANING
        or not element.items
        or finding.source.tag not in DESCRIPTIVE_SOURCES
        or institutional(finding.source)
    ):
        return None
    vocabulary = load_technique_vocabulary()
    if not _only_vocabulary(kept.values(element), vocabulary, sources):
        return None
    return Exemption.VOCABULARY_MEANING


def vocabulary_descriptor(
    finding: Finding,
    kept: KeptValues,
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
) -> Exemption | None:
    """Return whether a kept technique descriptor of reviewed vocabulary explains a finding.

    Parameters
    ----------
    finding : Finding
        A text finding that would otherwise send its file to QC review.
    kept : KeptValues
        The written file's values.
    sources : mapping
        The collected values of each source, pooled across the subject
        (:func:`~pymedphys._dicom.deidentify.residual_exemptions.source_values`).

    Returns
    -------
    Exemption or None
        :attr:`~pymedphys._dicom.deidentify.residual_exemptions.Exemption.VOCABULARY_DESCRIPTOR`
        as the module describes, or ``None``.
    """
    element = finding.location.element
    if (
        finding.location.region is not Region.DATA_SET
        or element is None
        or finding.source.tag not in DESCRIPTIVE_SOURCES
        or institutional(finding.source)
    ):
        return None
    vocabulary = load_technique_vocabulary()
    if element.tag not in vocabulary.attributes:
        return None
    if not _only_vocabulary(descriptor_values(element, kept), vocabulary, sources):
        return None
    return Exemption.VOCABULARY_DESCRIPTOR


def descriptor_values(element: ElementPath, kept: KeptValues) -> tuple[str, ...] | None:
    """Return a kept descriptor's values as descriptor cleaning reads them.

    Split at backslashes where every VR that the pinned dictionary gives the
    attribute holds several values, and whole otherwise; ``None`` as
    :meth:`~pymedphys._dicom.deidentify.residual_exemptions.KeptValues.values`
    gives it.
    """
    attribute = dictionary_attribute(element.tag)
    if attribute is not None and set(attribute.vrs) <= MULTI_VALUED_VRS:
        return kept.values(element)
    text = kept.text(element)
    return None if text is None else (text.strip(" "),)


def _only_vocabulary(
    values: tuple[str, ...] | None,
    vocabulary: TechniqueVocabulary,
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
) -> bool:
    """Return whether every value is reviewed vocabulary that echoes no identifier."""
    if not values:
        return False
    if any(vocabulary.word_rejection(value) is not None for value in values):
        return False
    identifiers = subject_identifiers(sources)
    return not any(echoes_identifier(value, identifiers) for value in values)


def institutional(source: ElementPath) -> bool:
    """Return whether a source names a place, an organisation, or a device.

    It does where its tag is one of :data:`INSTITUTIONAL_SOURCES`, or it is
    in an item of one of :data:`INSTITUTIONAL_SEQUENCES`, at any depth.
    """
    return source.tag in INSTITUTIONAL_SOURCES or any(
        tag in INSTITUTIONAL_SEQUENCES for tag, _ in source.items
    )


def subject_identifiers(
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
) -> tuple[str, ...]:
    """Return the person names and patient identifiers collected for the subject."""
    return tuple(
        each.value
        for values in sources.values()
        for each in values
        if isinstance(each.value, str)
        and (each.vr == "PN" or each.source.tag in IDENTIFIER_TAGS)
    )
