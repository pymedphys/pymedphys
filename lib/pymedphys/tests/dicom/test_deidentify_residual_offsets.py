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

"""A residual value found only inside the nominal UTC offset of Modified Dates.

Every file and value is synthetic. Under Modified Dates every Timezone Offset
From UTC becomes ``+0000``, and so does the offset of every datetime that has
one, so a source offset that was already ``+0000`` is found in what the
engine wrote, whatever the source held.
"""

import dataclasses
import types

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import dates, residual_offsets, run
from pymedphys._dicom.deidentify.file_layout import ElementPath, Region
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import MODIFIED_DATES, compose_custom_policy
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    release_condition,
)
from pymedphys._dicom.deidentify.residual_exemptions import Exemption, KeptValues
from pymedphys._dicom.deidentify.residuals import SourceValue, ValueKind

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
NOMINAL = dates.NOMINAL_UTC_OFFSET
TIMEZONE_OFFSET = "(0008,0201)"
SOP_AUTHORIZATION_DATETIME = "(0100,0420)"
MODEL_NAME = "(0008,1090)"


def _plan(**attributes):
    plan = synthetic.rt_plan()
    plan.StudyDate = "20200102"
    for keyword, value in attributes.items():
        setattr(plan, keyword, value)
    return plan


def _transformed(*plans):
    transform = InstanceTransform(
        compose_custom_policy([MODIFIED_DATES]), KEY, unvalidated_policy=True
    )
    results = []
    for plan in plans:
        data = synthetic.written(plan)
        result = transform(data, InstanceRecord.from_file(data))
        assert isinstance(result, run.Transformed), result
        results.append(result)
    return results


def _condition(result, *others, options=None):
    coverages = [each.evidence for each in (result, *others)]
    if options is not None:
        coverages = [dataclasses.replace(c, options=options) for c in coverages]
    return release_condition(Coverage.merge(*coverages), result.data)


def _exempted(condition):
    return {(f.location.element.tag, why) for f, why in condition.exempted}


def _reasons(condition):
    return {
        (r.code, r.location.element.tag)
        for r in condition.reasons
        if r.location is not None and r.location.element is not None
    }


def test_a_source_offset_of_plus_0000_is_found_in_the_nominal_offset():
    (result,) = _transformed(_plan(TimezoneOffsetFromUTC=NOMINAL))

    condition = _condition(result, options=())

    # Without the exemption, the search finds the source offset in the one
    # that the engine wrote, and holds the file for review.
    assert condition.decision is Decision.QC_REVIEW
    assert (ReasonCode.RESIDUAL_TEXT, TIMEZONE_OFFSET) in _reasons(condition)


@pytest.mark.deid_requirement("PS3.15-E.3.6-02")
def test_a_source_offset_equal_to_the_nominal_offset_is_released():
    (result,) = _transformed(_plan(TimezoneOffsetFromUTC=NOMINAL))

    decision = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    condition = _condition(result)

    assert isinstance(decision, run.Release), decision
    assert condition.decision is Decision.RELEASE
    assert (TIMEZONE_OFFSET, Exemption.NOMINAL_OFFSET) in _exempted(condition)


def test_another_instances_source_offset_in_the_nominal_offset_is_released():
    # The subject's other plan was acquired at UTC; this one at +1000, which
    # the engine also writes as the nominal offset, where the pooled search
    # finds the other plan's source offset.
    at_utc, elsewhere = _transformed(
        _plan(TimezoneOffsetFromUTC=NOMINAL), _plan(TimezoneOffsetFromUTC="+1000")
    )

    condition = _condition(elsewhere, at_utc)

    assert condition.decision is Decision.RELEASE
    assert (TIMEZONE_OFFSET, Exemption.NOMINAL_OFFSET) in _exempted(condition)


def test_an_unsigned_source_offset_found_in_the_nominal_offset_is_released():
    # 0000 is not a valid offset, so it counts as absent and becomes the
    # nominal offset, inside which the search finds it.
    (result,) = _transformed(_plan(TimezoneOffsetFromUTC="0000"))

    assert _condition(result, options=()).decision is Decision.QC_REVIEW
    condition = _condition(result)

    assert condition.decision is Decision.RELEASE
    assert (TIMEZONE_OFFSET, Exemption.NOMINAL_OFFSET) in _exempted(condition)


def test_the_source_offset_at_the_end_of_a_moved_datetime_is_released():
    # A datetime with its own offset is put in local time and given the
    # nominal offset, so the source offset is also found at its end.
    (result,) = _transformed(
        _plan(
            TimezoneOffsetFromUTC=NOMINAL,
            SOPAuthorizationDateTime="20200102123456+0000",
        )
    )

    condition = _condition(result)

    assert condition.decision is Decision.RELEASE
    assert {
        (TIMEZONE_OFFSET, Exemption.NOMINAL_OFFSET),
        (SOP_AUTHORIZATION_DATETIME, Exemption.NOMINAL_OFFSET),
    } <= _exempted(condition)


def test_the_same_value_in_an_element_that_was_not_written_so_still_counts():
    # The source offset also stands in the kept Manufacturer's Model Name,
    # which the engine did not write.
    (result,) = _transformed(
        _plan(TimezoneOffsetFromUTC=NOMINAL, ManufacturerModelName=NOMINAL)
    )

    condition = _condition(result)

    assert condition.decision is Decision.QC_REVIEW
    assert (ReasonCode.RESIDUAL_TEXT, MODEL_NAME) in _reasons(condition)
    assert (TIMEZONE_OFFSET, Exemption.NOMINAL_OFFSET) in _exempted(condition)


def test_without_modified_dates_in_the_runs_options_the_finding_counts():
    (result,) = _transformed(_plan(TimezoneOffsetFromUTC=NOMINAL))

    condition = _condition(result, options=())

    assert not any(why is Exemption.NOMINAL_OFFSET for _, why in condition.exempted)


def _finding(source, element, offset):
    return types.SimpleNamespace(
        kind=ValueKind.TEXT,
        source=source,
        offset=offset,
        location=types.SimpleNamespace(region=Region.DATA_SET, element=element),
    )


def _element_finding(result, tag, source_value, source_vr="SH"):
    """Return a finding of a planted source value in the written ``tag``."""
    kept = KeptValues(result.data)
    element = ElementPath((), tag)
    extent = kept.extent(element)
    assert extent is not None
    raw = kept.read(extent.value_start, extent.end)
    at = raw.lower().find(source_value.lower().encode("ascii"))
    assert at != -1
    source = ElementPath((), "(0009,1001)" if tag != TIMEZONE_OFFSET else tag)
    sources = {source: (SourceValue(source, source_vr, source_value),)}
    return _finding(source, element, extent.value_start + at), kept, sources


def test_a_source_also_found_in_the_time_of_a_datetime_is_not_exempt():
    # 0000 is in the moved datetime's time as well as in its nominal offset.
    # The search would not report a match there, after a digit, but every
    # place where the source starts must lie in the nominal offset, as for
    # the method digest, so the finding counts.
    (result,) = _transformed(
        _plan(
            TimezoneOffsetFromUTC="+1000",
            SOPAuthorizationDateTime="20200102000000+1000",
        )
    )
    finding, kept, sources = _element_finding(
        result, SOP_AUTHORIZATION_DATETIME, "0000"
    )
    # The finding's match starts inside the nominal offset.
    extent = kept.extent(finding.location.element)
    raw = kept.read(extent.value_start, extent.end)
    finding.offset = extent.value_start + raw.index(b"+0000") + 1

    assert not residual_offsets.in_nominal_offset(
        finding, kept, sources, (MODIFIED_DATES,)
    )


def test_a_finding_that_starts_outside_the_nominal_offset_is_not_exempt():
    (result,) = _transformed(
        _plan(
            TimezoneOffsetFromUTC="+1000",
            SOPAuthorizationDateTime="20200102123456+1000",
        )
    )
    # A source of the datetime's date and time, found before its offset.
    finding, kept, sources = _element_finding(
        result, SOP_AUTHORIZATION_DATETIME, "123456"
    )

    assert not residual_offsets.in_nominal_offset(
        finding, kept, sources, (MODIFIED_DATES,)
    )


@pytest.mark.parametrize(
    "tag, writes",
    [
        (TIMEZONE_OFFSET, True),
        (SOP_AUTHORIZATION_DATETIME, True),
        ("(0008,0020)", False),  # Study Date, DA
        ("(0008,0030)", False),  # Study Time, TM
        ("(0018,1203)", False),  # Calibration DateTime, a device's dummy value
        (MODEL_NAME, False),
    ],
)
def test_the_attributes_in_which_the_option_writes_the_nominal_offset(tag, writes):
    assert residual_offsets.writes_nominal_offset(tag) is writes


@pytest.mark.parametrize(
    "raw, spans",
    [
        (b"+0000 ", [(10, 15)]),
        (b" +0000", [(11, 16)]),
        (b"", []),
        (b"+1000 ", None),
        (b"+0000\\+0100", None),
    ],
)
def test_the_nominal_offsets_of_a_timezone_offset(raw, spans):
    assert residual_offsets._offset_spans(raw, 10) == spans


@pytest.mark.parametrize(
    "raw, spans",
    [
        (b"20200102123456+0000 ", [(24, 29)]),
        (b"20200102123456.123+0000", [(28, 33)]),
        (b"20200102123456", []),
        (b"20200102123456+1000", []),
        (b"TEXT+0000", []),
        (b"20200102+0000\\20200103+0000", [(18, 23), (32, 37)]),
    ],
)
def test_the_nominal_offsets_that_end_a_datetime(raw, spans):
    assert residual_offsets._datetime_spans(raw, 10) == spans
