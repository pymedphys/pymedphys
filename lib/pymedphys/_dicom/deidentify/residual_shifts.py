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

"""Recognise a residual date that only coincides with a shifted date.

Under Retain Longitudinal Temporal Information with Modified Dates, every
date of a subject moves back by one offset of whole weeks (D-006, D-039).
Where two of the subject's source dates differ by exactly that offset, the
later one's shifted value equals the earlier one's source value, and the
residual search finds that source value in the shifted element (D-027).
The written value is the engine's own shift of the element's source, so the
match discloses only the coincidence. :func:`shifted_date` says whether a
finding is such a match; the release gate then does not withhold the file
for it (:attr:`~pymedphys._dicom.deidentify.residual_exemptions.Exemption.SHIFTED_DATE`).

A finding is such a match only where all of these hold:

- the run selects Modified Dates, and the finding is of a date or
  datetime, inside the data set, in an element of VR DA or DT whose
  attribute Modified Dates moves by the subject's offset, by its temporal
  role (D-007);
- a value of the element, or, for a datetime, its date, equals a whole
  value of the finding's source, pooled across the subject, which may be the
  same element of another instance, or, for a datetime, that value's date;
  and
- every value of the element is a source value of the same element, pooled
  across the subject, moved back by whole weeks within the offset's range,
  with the same time of day, as the engine writes it, so that no value of
  the element that the search could have found is left unexplained.

A finding anywhere else, or of any other source value, still withholds the
file. Values are read from the written file's bytes, as text in ISO 646, and
none is reported.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping

from . import dates
from .file_layout import ElementPath, Region
from .modified_dates import TAGS
from .policy import MODIFIED_DATES
from .residual_exemptions import KeptValues
from .residuals import Finding, SourceValue, ValueKind
from .standard import dictionary_attribute
from .temporal_roles import TemporalAction, load_temporal_roles

# The kinds of finding that a shifted value can explain.
KINDS = frozenset({ValueKind.DATE, ValueKind.DATETIME})
_SHIFTED_VRS = frozenset({"DA", "DT"})
_PADDING = " \x00"
_DAYS = range(7 * dates.MIN_OFFSET_WEEKS, 7 * dates.MAX_OFFSET_WEEKS + 1, 7)


def shifted_date(
    finding: Finding,
    kept: KeptValues,
    sources: Mapping[ElementPath, tuple[SourceValue, ...]],
    options: tuple[str, ...],
) -> bool:
    """Return whether a finding only matches a date that the engine shifted.

    Parameters
    ----------
    finding : Finding
        A finding of the residual search.
    kept : KeptValues
        The written file's values.
    sources : mapping
        The collected values of each source
        (:func:`~pymedphys._dicom.deidentify.residual_exemptions.source_values`).
    options : tuple of str
        The run's options.
    """
    element = finding.location.element
    if (
        MODIFIED_DATES not in options
        or finding.kind not in KINDS
        or finding.location.region is not Region.DATA_SET
        or element is None
        or not _shifts(element.tag)
    ):
        return False
    written = kept.values(element)
    # A multi-valued element's source values are collected as one value.
    own = [
        value
        for each in sources.get(element, ())
        if isinstance(each.value, str)
        for value in each.value.split("\\")
    ]
    if written is None:
        return False
    values = [value for value in written if value]
    if not values or not all(any(_moved(s, value) for s in own) for value in values):
        return False
    found = {
        form
        for each in sources.get(finding.source, ())
        if isinstance(each.value, str)
        for form in _whole_forms(each.value)
    }
    return any(found & {value, value[:8]} for value in values)


def _shifts(tag: str) -> bool:
    """Whether Modified Dates moves the attribute's DA or DT values."""
    attribute = dictionary_attribute(tag)
    rule = load_temporal_roles().rules.get(tag)
    return (
        tag in TAGS
        and attribute is not None
        and bool(set(attribute.vrs) & _SHIFTED_VRS)
        and rule is not None
        and rule.role.action is TemporalAction.SHIFT
    )


def _whole_forms(value: str) -> set[str]:
    """Return each value of a source, and the date of each datetime."""
    forms = set()
    for one in value.split("\\"):
        one = one.strip(_PADDING)
        if one:
            forms.update({one, one[:8]} if len(one) > 8 else {one})
    return forms


def _moved(source: str, written: str) -> bool:
    """Whether ``written`` is ``source`` moved back by whole weeks in range."""
    source, written = source.strip(_PADDING), written.strip(_PADDING)
    before, after = _date(source), _date(written)
    if before is None or after is None:
        return False
    return (before - after).days in _DAYS and _time(source) == _time(written)


def _date(value: str) -> datetime.date | None:
    """Return the date that a DA or DT value starts with, or None."""
    if len(value) < 8 or not value[:8].isdigit():
        return None
    try:
        return datetime.date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError:
        return None


def _time(value: str) -> str:
    """Return the time of day of a DT value, without its UTC offset."""
    rest = value[8:]
    for sign in "+-":
        if sign in rest:
            rest = rest[: rest.index(sign)]
    return rest
