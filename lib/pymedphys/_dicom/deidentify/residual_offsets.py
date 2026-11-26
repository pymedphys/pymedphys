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

"""Recognise a residual value found only inside the nominal UTC offset.

Under Retain Longitudinal Temporal Information with Modified Dates, every
Timezone Offset From UTC (0008,0201) becomes the nominal offset ``+0000``,
and every datetime with its own UTC offset is put in the instance's local
time and given the same nominal offset (D-007, D-039). The engine writes
``+0000`` there whatever the source held, so it holds no source value. Where
a source value is ``+0000`` itself, as a source Timezone Offset From UTC of
an instance acquired at UTC is, or ``0000``, the residual search finds it in
the nominal offset that the engine wrote (D-027), and the match discloses
nothing: every instance that the option writes holds the same offset, so
the file cannot tell a source at UTC from any other.
:func:`in_nominal_offset` says whether a finding is such a match; the
release gate then neither withholds the file nor holds it for review for it
(:attr:`~pymedphys._dicom.deidentify.residual_exemptions.Exemption.NOMINAL_OFFSET`).

A finding is such a match only where all of these hold:

- the run selects Modified Dates, and the finding is inside the data set, at
  any depth, in an element whose attribute the option gives the nominal
  offset, Timezone Offset From UTC, every value of which is then the
  nominal offset or empty, or in an element of VR DT whose attribute the
  option moves by the subject's offset (D-007);
- the finding's match starts inside the nominal offset: a whole value of
  Timezone Offset From UTC, without its padding, or the five characters
  that end a datetime value, a valid DT value's date and time followed by
  ``+0000``; and
- every place in the element where a form of any value of the finding's
  source, pooled across the subject, starts, in any codec and case, lies
  wholly inside such a nominal offset
  (:func:`~pymedphys._dicom.deidentify.residual_exemptions.matches_within`),
  as for the method digest (D-032).

So the same value anywhere else, in the date or time of a datetime, in a
Timezone Offset From UTC that holds another value, in an element that the
option does not write, or under a run without the option, still counts, and
the finding may be of any kind. Values are read from the written file's
bytes, as text in ISO 646, and none is reported.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .dates import NOMINAL_UTC_OFFSET
from .file_layout import ElementPath, Region
from .modified_dates import TAGS
from .policy import MODIFIED_DATES
from .residual_exemptions import KeptValues, matches_within
from .residuals import Finding, SourceValue
from .standard import dictionary_attribute
from .temporal_roles import TemporalAction, load_temporal_roles

_NOMINAL = NOMINAL_UTC_OFFSET.encode("ascii")
_PADDING = b" \x00"
# A DT value's date and time, without a UTC offset (PS3.5 Table 6.2-1).
_DATE_AND_TIME = re.compile(rb"[0-9]{4,14}(\.[0-9]{1,6})?")


def writes_nominal_offset(tag: str) -> bool:
    """Return whether Modified Dates writes the nominal offset in an attribute.

    It does in Timezone Offset From UTC (0008,0201), whose value it is, and
    at the end of each datetime with its own UTC offset in an attribute of
    VR DT that the option moves by the subject's offset (D-007).

    Examples
    --------
    >>> writes_nominal_offset("(0008,0201)")
    True
    >>> writes_nominal_offset("(0008,002A)")  # Acquisition DateTime
    True
    >>> writes_nominal_offset("(0008,0020)")  # Study Date, DA
    False
    """
    return _action(tag) is not None


def takes_nominal_offset(tag: str) -> bool:
    """Return whether Modified Dates writes the nominal offset as an attribute's value.

    It does in Timezone Offset From UTC (0008,0201), every value of which
    becomes the nominal offset whatever the source held (D-007, D-039). In
    an attribute of VR DT it writes the nominal offset only at the end of
    a value whose date and time come from the source, so such an attribute
    does not take it as its value.

    Examples
    --------
    >>> takes_nominal_offset("(0008,0201)")
    True
    >>> takes_nominal_offset("(0008,002A)")  # Acquisition DateTime
    False
    """
    return _action(tag) is TemporalAction.NOMINAL_OFFSET


def in_nominal_offset(
    finding: Finding,
    kept: KeptValues,
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
    options: tuple[str, ...],
) -> bool:
    """Return whether a finding lies wholly inside the nominal UTC offset.

    Parameters
    ----------
    finding : Finding
        A finding of the residual search, of any kind.
    kept : KeptValues
        The written file's values.
    sources : mapping
        The collected values of each source
        (:func:`~pymedphys._dicom.deidentify.residual_exemptions.source_values`).
    options : tuple of str
        The run's options.

    Returns
    -------
    bool
        Whether every condition that the module lists holds.
    """
    element = finding.location.element
    if (
        MODIFIED_DATES not in options
        or finding.location.region is not Region.DATA_SET
        or element is None
    ):
        return False
    action = _action(element.tag)
    extent = kept.extent(element)
    if action is None or extent is None or extent.items is not None:
        return False
    raw = kept.read(extent.value_start, extent.end)
    if action is TemporalAction.NOMINAL_OFFSET:
        spans = offset_spans(raw, extent.value_start)
    else:
        spans = datetime_spans(raw, extent.value_start)
    return spans is not None and matches_within(finding, kept, sources, extent, spans)


def _action(tag: str) -> TemporalAction | None:
    """Return how the option writes the nominal offset in an attribute, or None.

    :attr:`~.TemporalAction.NOMINAL_OFFSET` for an attribute whose value it
    is, :attr:`~.TemporalAction.SHIFT` for an attribute of VR DT whose values
    end with it, and ``None`` for any other attribute.
    """
    rule = load_temporal_roles().rules.get(tag)
    attribute = dictionary_attribute(tag)
    if tag not in TAGS or rule is None or attribute is None:
        return None
    action = rule.role.action
    if action is TemporalAction.NOMINAL_OFFSET:
        return action
    if action is TemporalAction.SHIFT and "DT" in attribute.vrs:
        return action
    return None


def offset_spans(raw: bytes, offset: int) -> list[tuple[int, int]] | None:
    """Return where a Timezone Offset From UTC's nominal values are, or None.

    ``raw`` is the element's value, which starts at ``offset`` in the file.
    Each span is of a value's own bytes, without padding. ``None`` where any
    value is neither the nominal offset nor empty, so that an element that
    the option did not write as it writes it explains nothing.
    """
    spans, start = [], offset
    for each in raw.split(b"\\"):
        value = each.strip(_PADDING)
        if value == _NOMINAL:
            begin = start + len(each) - len(each.lstrip(_PADDING))
            spans.append((begin, begin + len(_NOMINAL)))
        elif value:
            return None
        start += len(each) + 1
    return spans


def datetime_spans(raw: bytes, offset: int) -> list[tuple[int, int]]:
    """Return where the nominal offsets that end a DT element's values are.

    ``raw`` is the element's value, which starts at ``offset`` in the file.
    Each span is of the five characters ``+0000`` that end a value whose
    date and time before them are a valid DT value's, without padding.
    """
    spans, start = [], offset
    for each in raw.split(b"\\"):
        value = each.strip(_PADDING)
        if value.endswith(_NOMINAL) and _DATE_AND_TIME.fullmatch(
            value[: -len(_NOMINAL)]
        ):
            end = start + (len(each) - len(each.lstrip(_PADDING))) + len(value)
            spans.append((end - len(_NOMINAL), end))
        start += len(each) + 1
    return spans
