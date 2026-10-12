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

"""A residual date that only coincides with a date that Modified Dates shifted.

Every file and value is synthetic. Two plans of one subject have Study Dates
that differ by exactly the subject's offset, so the later plan's shifted Study
Date equals the earlier plan's source Study Date.
"""

import dataclasses
import datetime

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import dates, run
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import MODIFIED_DATES, compose_custom_policy
from pymedphys._dicom.deidentify.pseudonyms import SubjectIdentity
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    release_condition,
)
from pymedphys._dicom.deidentify.residual_exemptions import Exemption

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
WEEKS = dates.date_offset_weeks(
    KEY, SubjectIdentity.from_patient_id(synthetic.PATIENT_ID)
)
EARLIER = "20200102"
STUDY_DATE = "(0008,0020)"


def _later(date=EARLIER, weeks=WEEKS):
    day = datetime.date.fromisoformat(date) + datetime.timedelta(weeks=weeks)
    return day.strftime("%Y%m%d")


def _plan(study_date, **attributes):
    plan = synthetic.rt_plan()
    plan.StudyDate = study_date
    plan.RTPlanDate = study_date
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


def test_the_later_plans_shifted_date_equals_the_earlier_source_date():
    earlier, later = _transformed(_plan(EARLIER), _plan(_later()))

    assert EARLIER.encode() in later.data
    assert EARLIER.encode() not in earlier.data


@pytest.mark.deid_requirement("PS3.15-E.3.6-02")
def test_a_shifted_date_that_equals_another_source_date_is_released():
    earlier, later = _transformed(_plan(EARLIER), _plan(_later()))

    # The gate pools the evidence of every instance of the subject.
    subject = (earlier.evidence, later.evidence)
    decision = ReleaseGate()(later.data, later.evidence, subject)
    condition = _condition(later, earlier)

    assert isinstance(decision, run.Release), decision
    assert condition.decision is Decision.RELEASE
    whys = {(f.location.element.tag, why) for f, why in condition.exempted}
    assert (STUDY_DATE, Exemption.SHIFTED_DATE) in whys


def test_the_same_source_date_in_an_element_that_was_not_shifted_withholds():
    # The earlier date also stands in the later plan's kept Manufacturer's
    # Model Name, which the engine did not write.
    earlier, later = _transformed(
        _plan(EARLIER), _plan(_later(), ManufacturerModelName=EARLIER)
    )

    condition = _condition(later, earlier)

    assert condition.decision is Decision.WITHHOLD
    withheld = {
        (r.code, r.location.element.tag)
        for r in condition.reasons
        if r.location is not None and r.location.element is not None
    }
    assert (ReasonCode.RESIDUAL_DATE, "(0008,1090)") in withheld


def test_without_modified_dates_in_the_runs_options_the_coincidence_withholds():
    earlier, later = _transformed(_plan(EARLIER), _plan(_later()))

    condition = _condition(later, earlier, options=())

    assert condition.decision is Decision.WITHHOLD
    assert not condition.exempted


def test_a_date_not_moved_by_whole_weeks_in_range_is_not_exempt():
    # A source Study Date eight weeks after the earlier one shifts to a date
    # that is not the earlier one, so nothing coincides, and the earlier
    # date planted as the later plan's own Instance Creation Date, which
    # Modified Dates also shifts, is moved, not kept.
    earlier, later = _transformed(_plan(EARLIER), _plan(_later(weeks=8)))

    condition = _condition(later, earlier)

    assert condition.decision is Decision.RELEASE
    assert not condition.exempted
