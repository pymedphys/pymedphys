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

"""Dates and times under Retain Longitudinal Temporal Information with Full Dates.

Every file and value is synthetic. Values that must never reach a written file
are dates that the tests look for by value.
"""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    cleaners,
    conformance,
    conformance_markdown,
    run,
    temporal_roles,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import (
    ENGINE_OPTIONS,
    FULL_DATES,
    MODIFIED_DATES,
    PolicyError,
    compose_custom_policy,
    refuse_unapplied_options,
)
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import Decision, release_condition
from pymedphys._dicom.deidentify.residual_exemptions import Exemption

from . import _classic_images as classic
from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
BASIC_PROFILE_CODE = "113100"
FULL_DATES_CODE = "113106"
STUDY_DATE = "20260927"
BIRTH_DATE = "19800101"


def _transform():
    return InstanceTransform(
        compose_custom_policy([FULL_DATES]), KEY, unvalidated_policy=True
    )


def _plan(**attributes):
    plan = synthetic.rt_plan()
    plan.StudyDate = STUDY_DATE
    plan.StudyTime = "101500"
    plan.InstanceCreationDate = "20261004"
    plan.InstanceCreationTime = "083000.25"
    plan.RTPlanDate = "20261004"
    plan.RTPlanTime = "083000"
    plan.TimezoneOffsetFromUTC = "+1000"
    plan.DateOfLastCalibration = "20200101"
    plan.TimeOfLastCalibration = "070000"
    plan.PatientBirthDate = BIRTH_DATE
    plan.PatientBirthTime = "031500"
    for keyword, value in attributes.items():
        setattr(plan, keyword, value)
    return plan


def _result(dataset):
    data = synthetic.written(dataset)
    return _transform()(data, InstanceRecord.from_file(data))


def _written(dataset):
    result = _result(dataset)
    assert isinstance(result, run.Transformed), result
    return pydicom.dcmread(io.BytesIO(result.data)), result


def _decision(result):
    return ReleaseGate()(result.data, result.evidence, (result.evidence,))


def test_the_engine_applies_full_dates_without_a_cleaner():
    composed = compose_custom_policy([FULL_DATES])

    assert FULL_DATES in ENGINE_OPTIONS
    refuse_unapplied_options(composed)
    assert not cleaners.cleaners_for(composed)
    actions = {**composed.actions, **composed.supplementary_actions}
    assert "C" not in {
        actions[tag] for tag in temporal_roles.load_temporal_roles().rules
    }


@pytest.mark.deid_requirement("PS3.15-E.3.6-01")
def test_full_dates_and_modified_dates_together_are_rejected():
    with pytest.raises(PolicyError, match="mutually exclusive"):
        compose_custom_policy([FULL_DATES, MODIFIED_DATES])


@pytest.mark.deid_requirement("PS3.15-E.3.6-01")
def test_every_date_and_time_is_kept_unmodified_and_released():
    plan = _plan()

    written, result = _written(plan)

    for keyword in (
        "StudyDate",
        "StudyTime",
        "InstanceCreationDate",
        "InstanceCreationTime",
        "RTPlanDate",
        "RTPlanTime",
        "TimezoneOffsetFromUTC",
        "DateOfLastCalibration",
        "TimeOfLastCalibration",
    ):
        assert written[keyword].value == plan[keyword].value, keyword
    # The option gives the patient's birth date and time no action, so they
    # keep their Basic Profile actions, Z and X.
    assert written.PatientBirthDate == ""
    assert "PatientBirthTime" not in written
    assert BIRTH_DATE.encode() not in result.data
    assert written.LongitudinalTemporalInformationModified == "UNMODIFIED"
    codes = [i.CodeValue for i in written.DeidentificationMethodCodeSequence]
    assert codes == [BASIC_PROFILE_CODE, FULL_DATES_CODE]
    assert isinstance(_decision(result), run.Release)


@pytest.mark.deid_requirement("PS3.15-E.3.6-01")
@pytest.mark.parametrize("present", ["MODIFIED", "REMOVED"])
def test_a_stricter_marker_from_an_earlier_run_is_kept(present):
    written, _ = _written(_plan(LongitudinalTemporalInformationModified=present))

    assert written.LongitudinalTemporalInformationModified == present


def _request_attributes(date):
    item = pydicom.Dataset()
    item.ScheduledProcedureStepStartDate = date
    return [item]


@pytest.mark.parametrize(
    "attributes",
    [
        {"PatientBirthDate": STUDY_DATE},
        {"RequestAttributesSequence": _request_attributes(STUDY_DATE)},
    ],
    ids=["birth date", "removed sequence"],
)
def test_a_removed_date_equal_to_a_kept_one_is_released_as_explained(attributes):
    # D-042 and D-043: the residual search finds a removed source value equal
    # to a kept date in the kept element, and the value that Full Dates keeps
    # explains it.
    _, result = _written(_plan(**attributes))

    condition = release_condition(result.evidence, result.data)

    assert isinstance(_decision(result), run.Release)
    exempted = [(each.location.element, why) for each, why in condition.exempted]
    assert exempted == [(ElementPath((), "(0008,0020)"), Exemption.RETAINED_VALUE)]


def test_a_removed_private_datetime_of_the_kept_date_is_released_as_explained():
    # A vendor's private scan time, which the Basic Profile removes, is
    # searched for by its date too, and found in the kept Study Date of the
    # same day, which explains it: the found text is the whole kept date.
    plan = _plan()
    plan.private_block(0x0009, "ZARQUON SCANNERS", create=True).add_new(
        0x10, "DT", f"{STUDY_DATE}101500.000000"
    )

    written, result = _written(plan)

    assert 0x00091010 not in written
    condition = release_condition(result.evidence, result.data)
    assert isinstance(_decision(result), run.Release)
    exempted = [
        (each.source, each.location.element, why) for each, why in condition.exempted
    ]
    assert exempted == [
        (
            ElementPath((), "(0009,1010)"),
            ElementPath((), "(0008,0020)"),
            Exemption.RETAINED_VALUE,
        )
    ]


# A PET image keeps its injection time in Radiopharmaceutical Start DateTime
# (0018,1078), inside Radiopharmaceutical Information Sequence (0054,0016).
# GE's writes times of the same day, such as its scan and injection times,
# into private elements of its GEMS_PETD_01 block, which the Basic Profile
# removes, and the search finds each by its date at the start of the kept
# datetime: that is the kept value's date, which holds none of their times.
PET_DAY = "20200102"
RADIOPHARMACEUTICAL_START = ElementPath((("(0054,0016)", 0),), "(0018,1078)")
GE_PET_TIMES = (0x0D, 0x0E, 0x3B, 0x3D, 0x68)


def _pet(times):
    """A PET image injected on ``PET_DAY``, with GE's private ``times``."""
    (dataset,) = classic.classic_series("PT", 1)
    # A name none of whose words the kept Manufacturer holds.
    dataset.PatientName = "Zarquon^Agrajag"
    for tag in (0x00090010, 0x00091001, 0x00091002):
        del dataset[tag]
    item = dataset.RadiopharmaceuticalInformationSequence[0]
    del item.RadiopharmaceuticalStartTime
    item.RadiopharmaceuticalStartDateTime = f"{PET_DAY}093000.000000"
    block = dataset.private_block(0x0009, "GEMS_PETD_01", create=True)
    for element, time in times:
        block.add_new(element, "DT", time)
    data = classic.encoded(dataset)
    return _transform()(data, InstanceRecord.from_file(data))


def test_removed_private_datetimes_of_a_kept_datetimes_day_are_released_as_explained():
    times = [
        (element, f"{PET_DAY}{101500 + index}.00")
        for index, element in enumerate(GE_PET_TIMES)
    ]

    result = _pet(times)

    assert isinstance(result, run.Transformed), result
    written = pydicom.dcmread(io.BytesIO(result.data))
    kept = written.RadiopharmaceuticalInformationSequence[0]
    assert kept.RadiopharmaceuticalStartDateTime == f"{PET_DAY}093000.000000"
    assert 0x00090010 not in written
    assert isinstance(_decision(result), run.Release)
    condition = release_condition(result.evidence, result.data)
    assert {
        (each.source.tag, why)
        for each, why in condition.exempted
        if each.location.element == RADIOPHARMACEUTICAL_START
    } == {
        (f"(0009,10{element:02X})", Exemption.RETAINED_VALUE)
        for element in GE_PET_TIMES
    }


@pytest.mark.parametrize(
    "time",
    [
        # Written to the minute, and found whole at the start of the kept
        # datetime, which is longer, so its time is not explained.
        f"{PET_DAY}0930",
        # Found whole inside the kept datetime.
        f"{PET_DAY}093000",
    ],
)
def test_a_removed_datetime_found_whole_in_a_longer_kept_datetime_withholds(time):
    result = _pet([(0x0D, time)])

    assert isinstance(result, run.Transformed), result
    condition = release_condition(result.evidence, result.data)
    assert condition.decision is Decision.WITHHOLD
    assert not isinstance(_decision(result), run.Release)


@pytest.mark.deid_requirement("PS3.15-E.3.6-01")
def test_the_statement_describes_kept_dates_and_needs_nothing_else():
    statement = conformance.conformance_statement(
        compose_custom_policy([FULL_DATES]), vocabulary=None
    )

    assert not statement.pending
    assert not statement.cleaned
    assert statement.temporal.option == FULL_DATES
    assert statement.markers.temporal == "UNMODIFIED"
    kept = dict(statement.temporal.actions)["K"]
    text = conformance_markdown.render_markdown(statement)
    section = text.split("## Dates and times")[1].split("\n## ")[0]
    assert "no date or time is shifted or otherwise modified" in section
    assert f"The {kept} that take `K` keep their source values" in section
    assert "the kept value explains it" in section
    assert "nor does a removed datetime whose date" in section
    assert "the date that begins a kept datetime" in section
    assert "it still does." in section
    assert "`UNMODIFIED`" in section
    assert "not yet described" not in section
