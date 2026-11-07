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

"""Recognise residual text in a kept Code Meaning made only of reviewed vocabulary.

A procedure or protocol code of a local scheme, one that PS3.16 Table 8-1
does not list, is kept with its Code Meaning (0008,0104) under the Basic
Profile, and a scanner often writes the same text as a description that the
profile removes, such as Study Description (0008,1030). The residual search
then finds the removed description in the kept meaning (D-027), and the
standard code exemption does not apply, since a local scheme's meaning can
be the site's own text (D-032). :func:`vocabulary_meaning` reads that text
instead: the finding is not a reason for review
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
  the run collected for the subject, at any depth; and
- the finding's source is not an institution's or a station's name:
  Institution Name (0008,0080), Institution Address (0008,0081),
  Institutional Department Name (0008,1040), or Station Name (0008,1010), or
  an element in an item of Institution Code Sequence (0008,0082) or
  Institutional Department Type Code Sequence (0008,1041), at any depth.

Whatever removed text is found inside a meaning made only of technique and
anatomy words is itself such words, so the finding reveals nothing that the
kept meaning does not. A meaning with any other word stays under review, as
does any other kept element. The vocabulary is always the one that PyMedPhys
ships, never one that a run gives Clean Descriptors, so the exemption is the
same in every run, and the method digest covers it through the engine's
files under every policy (D-024).

Only a text finding is read: a person name, UID, date, datetime, or direct
identifier found anywhere still withholds the file. No value is reported.
"""

from __future__ import annotations

from collections.abc import Mapping

from .file_layout import ElementPath, Region
from .residual_exemptions import Exemption, KeptValues
from .residuals import Finding, SourceValue
from .reviewed_descriptors import echoes_identifier
from .technique_descriptors import load_technique_vocabulary

_CODE_MEANING = "(0008,0104)"
# Institution Name, Institution Address, Institutional Department Name, and
# Station Name.
INSTITUTIONAL_SOURCES = frozenset(
    {"(0008,0080)", "(0008,0081)", "(0008,1040)", "(0008,1010)"}
)
# Institution Code Sequence and Institutional Department Type Code Sequence,
# whose items' elements code the institution.
INSTITUTIONAL_SEQUENCES = frozenset({"(0008,0082)", "(0008,1041)"})
# Patient ID, Issuer of Patient ID, and Other Patient IDs, as descriptor
# cleaning checks for echoes of them with every person name.
IDENTIFIER_TAGS = frozenset({"(0010,0020)", "(0010,0021)", "(0010,1000)"})


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
        or institutional(finding.source)
    ):
        return None
    values = kept.values(element)
    if not values:
        return None
    vocabulary = load_technique_vocabulary()
    if any(vocabulary.word_rejection(value) is not None for value in values):
        return None
    identifiers = subject_identifiers(sources)
    if any(echoes_identifier(value, identifiers) for value in values):
        return None
    return Exemption.VOCABULARY_MEANING


def institutional(source: ElementPath) -> bool:
    """Return whether a source names or codes an institution or a station."""
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
