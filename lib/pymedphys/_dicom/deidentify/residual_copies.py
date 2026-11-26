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

"""Recognise a removed code's value that a kept code repeats.

Equipment often copies the code of the procedure that was requested into
the code of the procedure that was done. The Basic Profile removes the
request, with Request Attributes Sequence (0040,0275), and keeps Procedure
Code Sequence (0008,1032), so the residual search finds the removed
request's Code Value, Coding Scheme Designator, or Code Meaning in the kept
code (D-027). Where that kept code is of a local scheme, no exemption of
:mod:`~pymedphys._dicom.deidentify.residual_exemptions` explains it, and the
file is held for review. :func:`copied_request_code` explains such a finding
(:attr:`~pymedphys._dicom.deidentify.residual_exemptions.Exemption.COPIED_REQUEST_CODE`)
where the removed value equals a whole value of the same attribute of a kept
code item, since a removed copy of a value that the output still shows
reveals nothing more (D-032).

A Coding Scheme Designator (0008,0102) names its code's scheme and nothing
else. Where de-identification removes a code item, such as a content item
that Clean Structured Content cannot keep, and keeps another code item of
the same local scheme, the search finds the removed item's designator in
the kept item's. :func:`shared_designator` explains such a finding
(:attr:`~pymedphys._dicom.deidentify.residual_exemptions.Exemption.SHARED_DESIGNATOR`)
where the removed designator equals the whole kept one, since it then
shows only that the two items shared a scheme, which the kept item already
shows (D-032).
"""

from __future__ import annotations

from collections.abc import Mapping

from .file_layout import ElementPath, Region
from .option_kept import whole_values
from .residual_exemptions import Exemption, KeptValues
from .residual_vocabulary import INSTITUTIONAL_SEQUENCES
from .residuals import Finding, SourceValue, ValueKind

# Requested Procedure Code Sequence, which the Basic Profile removes with an
# enclosing Request Attributes Sequence (0040,0275).
REQUESTED_PROCEDURE_CODE = "(0032,1064)"
# Code Value, Coding Scheme Designator, and Code Meaning, which equipment
# copies from a requested procedure's code into the procedure's own.
COPIED_CODE_ATTRIBUTES = frozenset({"(0008,0100)", "(0008,0102)", "(0008,0104)"})
# Coding Scheme Designator, which names the scheme of its code item.
CODING_SCHEME_DESIGNATOR = "(0008,0102)"
# The kind of value that a kept code's value can explain.
_TEXT_KINDS = frozenset({ValueKind.TEXT})


def copied_request_code(
    finding: Finding,
    kept: KeptValues,
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
    removed: frozenset[SourceValue],
) -> Exemption | None:
    """Return whether a kept code explains a removed request code's copy of it.

    Parameters
    ----------
    finding : Finding
        A text finding that would otherwise send its file to QC review.
    kept : KeptValues
        The written file's values.
    sources : mapping
        The collected values of each source (:func:`source_values`).
    removed : frozenset of SourceValue
        The values in ``sources`` that no instance's output holds at their
        place (:attr:`~.release_gate.Coverage.removed`).

    Returns
    -------
    Exemption or None
        :attr:`Exemption.COPIED_REQUEST_CODE` where the source is the Code
        Value (0008,0100), Coding Scheme Designator (0008,0102), or Code
        Meaning (0008,0104) of an item of Requested Procedure Code Sequence
        (0032,1064), at any depth; every value of it collected for the
        subject is in ``removed``, so that no written instance holds it
        there; the finding is in a data set element of the same attribute in
        an item, a kept code item such as one of Procedure Code Sequence
        (0008,1032); and one of the source's values equals a whole value of
        it, as does each other value of the source that the search could
        find there (:func:`~.option_kept.whole_values`). A request code found
        inside a longer kept value, in another case, or in another attribute
        of a code, such as a Code Meaning in a Code Value, one in an
        equivalent code inside the request's item, and one that a written
        instance holds give ``None``. Any other finding in the same kept
        code, such as a removed Study Description in its meaning, is decided
        on its own.
    """
    source, element = finding.source, finding.location.element
    if (
        finding.location.region is not Region.DATA_SET
        or element is None
        or not _requested_code(source)
        or element.tag != source.tag
        or not element.items
    ):
        return None
    values = sources.get(source, ())
    if not values or not all(each in removed for each in values):
        return None
    written, text = kept.values(element), kept.text(element)
    if written is None or text is None:
        return None
    if whole_values(values, written, text, _TEXT_KINDS):
        return Exemption.COPIED_REQUEST_CODE
    return None


def _requested_code(source: ElementPath) -> bool:
    """Return whether a source is a copied attribute of a requested procedure code.

    It must be the Code Value, Coding Scheme Designator, or Code Meaning of
    an item directly in Requested Procedure Code Sequence (0032,1064).
    """
    return (
        source.tag in COPIED_CODE_ATTRIBUTES
        and bool(source.items)
        and source.items[-1][0] == REQUESTED_PROCEDURE_CODE
    )


def shared_designator(
    finding: Finding,
    kept: KeptValues,
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
    removed: frozenset[SourceValue],
) -> Exemption | None:
    """Return whether a kept code explains a removed code's designator in it.

    Parameters
    ----------
    finding : Finding
        A text finding that would otherwise send its file to QC review.
    kept : KeptValues
        The written file's values.
    sources : mapping
        The collected values of each source (:func:`source_values`).
    removed : frozenset of SourceValue
        The values in ``sources`` that no instance's output holds at their
        place (:attr:`~.release_gate.Coverage.removed`).

    Returns
    -------
    Exemption or None
        :attr:`Exemption.SHARED_DESIGNATOR` where the source is the Coding
        Scheme Designator (0008,0102) of a code item, at any depth, none of
        whose enclosing sequences is private or codes or names an
        institution, a department, a station, or a custodial organisation
        (:data:`~.residual_vocabulary.INSTITUTIONAL_SEQUENCES`); every value
        of it collected for the subject is in ``removed``, so that no
        written instance holds it there; the finding is in the Coding
        Scheme Designator of a kept code item, at any depth; and one of the
        source's values equals a whole value of it, as does each other
        value of the source that the search could find there
        (:func:`~.option_kept.whole_values`). A designator found inside a
        longer one, in another case, or in any other attribute, such as a
        Code Value or Code Meaning, and one that a written instance holds
        give ``None``, as does text of any other source found in a
        designator, such as an organisation's name or a private creator.
    """
    source, element = finding.source, finding.location.element
    if (
        finding.location.region is not Region.DATA_SET
        or element is None
        or element.tag != CODING_SCHEME_DESIGNATOR
        or not element.items
        or not _code_designator(source)
    ):
        return None
    values = sources.get(source, ())
    if not values or not all(each in removed for each in values):
        return None
    written, text = kept.values(element), kept.text(element)
    if written is None or text is None:
        return None
    if whole_values(values, written, text, _TEXT_KINDS):
        return Exemption.SHARED_DESIGNATOR
    return None


def _code_designator(source: ElementPath) -> bool:
    """Return whether a source is the designator of a standard code item.

    It must be a Coding Scheme Designator (0008,0102) in an item, and no
    sequence that encloses it may be private or one that codes or names an
    institution, a department, a station, or a custodial organisation.
    """
    return (
        source.tag == CODING_SCHEME_DESIGNATOR
        and bool(source.items)
        and not any(
            _private(tag) or tag in INSTITUTIONAL_SEQUENCES for tag, _ in source.items
        )
    )


def _private(tag: str) -> bool:
    """Return whether a tag, such as ``"(0009,1010)"``, is of an odd group."""
    return int(tag[1:5], 16) % 2 == 1
