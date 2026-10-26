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

"""Dates and times under Retain Longitudinal Temporal Information with Modified Dates.

Every file and value is synthetic. Values that must never reach a written file
carry the text ``SENTINEL``, or are dates that the tests look for by value.
"""

import datetime
import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    cleaners,
    conformance,
    conformance_markdown,
    dates,
    dummy_values,
    modified_dates,
    run,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
    TransformReason,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import (
    DEVICE_IDENTITY,
    MODIFIED_DATES,
    PATIENT_CHARACTERISTICS,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.pseudonyms import SubjectIdentity
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.standard import dictionary_attribute
from pymedphys._dicom.deidentify.temporal_roles import (
    TemporalRole,
    load_temporal_roles,
)
from pymedphys._dicom.deidentify.values import values_problem

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
OTHER_KEY = DeidKey(bytes(range(1, 33)))
SUBJECT = SubjectIdentity.from_patient_id("SENTINEL-1", "SENTINEL ISSUER")
WEEKS = dates.date_offset_weeks(KEY, SUBJECT)
MODIFIED_DATES_CODE = "113107"

_STUDY_DATE = ElementPath((), "(0008,0020)")
_STUDY_TIME = ElementPath((), "(0008,0030)")
_ACQUISITION_DATETIME = ElementPath((), "(0008,002A)")
_CONTENT_DATE = ElementPath((), "(0008,0023)")
_TIMEZONE = ElementPath((), "(0008,0201)")
_CALIBRATION_DATE = ElementPath((), "(0018,1200)")
_CALIBRATION_TIME = ElementPath((), "(0018,1201)")
_CONTEXT_GROUP_VERSION = ElementPath((("(0040,A730)", 0),), "(0008,0106)")
_SOURCE_DATE = ElementPath((("(300A,0210)", 0),), "(300A,022C)")
_SOURCE_TIME = ElementPath((("(300A,0210)", 0),), "(300A,022E)")
_TREATMENT_DATE = ElementPath((), "(3008,0250)")
_FRAME_ORIGIN = ElementPath((("(5200,9230)", 3),), "(0034,0007)")


def _moved(date, weeks=WEEKS):
    """Return a YYYYMMDD date moved back by ``weeks``, computed independently."""
    day = datetime.date(int(date[:4]), int(date[4:6]), int(date[6:8]))
    return (day - datetime.timedelta(days=7 * weeks)).strftime("%Y%m%d")


def _value(path, vr, value):
    return SourceValue(path, vr, value)


def _modified(*values, key=KEY, identity=SUBJECT):
    return modified_dates.modify_dates(values, key, identity)


def _date_of(text):
    return datetime.date(int(text[:4]), int(text[4:6]), int(text[6:8]))


def test_the_cleaner_covers_exactly_what_modified_dates_gives_c():
    composed = compose_custom_policy([MODIFIED_DATES])
    actions = {**composed.actions, **composed.supplementary_actions}
    roles = load_temporal_roles().rules
    given_c = {tag for tag, action in actions.items() if action == "C"}

    assert modified_dates.TAGS == given_c
    # Every attribute with a temporal role but the three the option removes.
    assert modified_dates.TAGS == set(roles) - {
        "(0010,0030)",  # Patient's Birth Date
        "(0010,0032)",  # Patient's Birth Time
        "(0016,0077)",  # GPS Time Stamp
    }
    for tag in modified_dates.TAGS:
        assert set(dictionary_attribute(tag).vrs) <= modified_dates.VRS
    (cleaner,) = [c for c in cleaners.CLEANERS if c.option == MODIFIED_DATES]
    assert cleaner.tags == modified_dates.TAGS
    assert cleaner.method == modified_dates.METHOD
    assert cleaner.clean_instance is modified_dates.modify_dates


@pytest.mark.deid_requirement("PS3.15-E.3.6-02", "MIDI-BP-12")
def test_subject_dates_move_back_by_whole_weeks_keeping_intervals_and_weekdays():
    written = _modified(
        _value(_STUDY_DATE, "DA", "20260927"),
        _value(_CONTENT_DATE, "DA", "20261004 "),
        _value(_TREATMENT_DATE, "DA", "20261005\\\\20261012"),
    )

    study, content, treatment = (
        written[p] for p in (_STUDY_DATE, _CONTENT_DATE, _TREATMENT_DATE)
    )
    assert study == ((_moved("20260927"),), False)
    assert content == ((_moved("20261004"),), False)
    assert treatment == ((_moved("20261005"), "", _moved("20261012")), False)
    before, after = _date_of("20260927"), _date_of(study[0][0])
    assert before.weekday() == after.weekday()
    assert (before - after).days == 7 * WEEKS
    assert 52 <= WEEKS <= 520
    assert (_date_of(content[0][0]) - after).days == 7


@pytest.mark.deid_requirement("PS3.15-E.3.6-02")
def test_times_are_kept_and_left_out_of_the_search():
    written = _modified(
        _value(_STUDY_TIME, "TM", "101500.25"),
        _value(_SOURCE_TIME, "TM", "0930"),
    )

    assert written[_STUDY_TIME] == (("101500.25",), True)
    assert written[_SOURCE_TIME] == (("0930",), True)
    assert _modified(_value(_STUDY_TIME, "TM", ""))[_STUDY_TIME] == ((), False)


@pytest.mark.deid_requirement("PS3.15-E.3.6-02", "MIDI-BP-12")
def test_a_sources_decay_interval_to_treatment_is_kept():
    written = _modified(
        _value(_SOURCE_DATE, "DA", "20260901"),
        _value(_TREATMENT_DATE, "DA", "20260927"),
    )

    source = _date_of(written[_SOURCE_DATE][0][0])
    treatment = _date_of(written[_TREATMENT_DATE][0][0])
    assert (treatment - source).days == 26
    assert written[_SOURCE_DATE][0] == (_moved("20260901"),)


@pytest.mark.deid_requirement("PS3.15-E.3.6-02")
def test_datetimes_move_their_date_in_local_time_with_the_nominal_offset():
    written = _modified(
        _value(_TIMEZONE, "SH", "+1000 "),
        # 00:30 at -0200 is 12:30 at +1000.
        _value(_ACQUISITION_DATETIME, "DT", "20260927003000.5-0200\\20260927"),
    )

    assert written[_TIMEZONE] == (("+0000",), False)
    assert written[_ACQUISITION_DATETIME] == (
        (_moved("20260927") + "123000.5+0000", _moved("20260927")),
        False,
    )


def test_without_a_timezone_the_earliest_datetime_with_one_is_local_time():
    written = _modified(
        _value(_ACQUISITION_DATETIME, "DT", "20260927120000+1000"),
        # Earlier, so local time is +0000, and the other moves to it.
        _value(ElementPath((), "(0018,9074)"), "DT", "20260927013000+0000"),
        # Later, at 12:00 UTC, and a device's, so it takes a dummy value.
        _value(ElementPath((), "(0018,1202)"), "DT", "20260927000000-1200"),
    )

    acquisition = written[_ACQUISITION_DATETIME][0][0]
    assert acquisition == _moved("20260927") + "020000+0000"
    assert written[ElementPath((), "(0018,1202)")][0] == ("19000101000000",)


@pytest.mark.deid_requirement("PS3.15-E.3.6-02")
def test_device_vocabulary_and_other_values_take_d_dummy_values():
    first = dummy_values.CONSTANTS
    written = _modified(
        _value(_CALIBRATION_DATE, "DA", "20200101\\20210101"),
        _value(_CALIBRATION_TIME, "TM", "083000"),
        _value(_CONTEXT_GROUP_VERSION, "DT", "20240101"),
        # Equal to D's first constant, so the value written still differs.
        _value(ElementPath((), "(0018,1204)"), "DA", "19000101"),
        _value(ElementPath((), "(0018,1205)"), "DA", ""),
    )

    assert written[_CALIBRATION_DATE] == ((first["DA"][0],), False)
    assert written[_CALIBRATION_TIME] == ((first["TM"][0],), False)
    assert written[_CONTEXT_GROUP_VERSION] == ((first["DT"][0],), False)
    assert written[ElementPath((), "(0018,1204)")] == ((first["DA"][1],), False)
    assert written[ElementPath((), "(0018,1205)")] == ((), False)
    # The dummy values are the same for every subject and key, so they
    # disclose nothing of the offset.
    other = _modified(
        _value(_CALIBRATION_DATE, "DA", "20200101"),
        key=OTHER_KEY,
        identity=SubjectIdentity.from_patient_id("SENTINEL-2"),
    )
    assert other[_CALIBRATION_DATE] == written[_CALIBRATION_DATE]


def test_frame_origin_timestamps_move_their_seconds():
    seconds = 1_790_000_000
    nanoseconds = 123_456_789
    stamp = seconds.to_bytes(6, "big") + nanoseconds.to_bytes(4, "big")

    ((value,), own) = _modified(_value(_FRAME_ORIGIN, "OB", stamp))[_FRAME_ORIGIN]

    assert own is False
    assert int.from_bytes(value[:6], "big") == seconds - WEEKS * 7 * 24 * 60 * 60
    assert value[6:] == stamp[6:]


def test_offsets_differ_by_subject_and_key_but_not_within_a_run():
    study = _value(_STUDY_DATE, "DA", "20260927")
    others = [
        _modified(study, identity=SubjectIdentity.from_patient_id(f"SENTINEL-{n}"))
        for n in range(2, 12)
    ]

    assert _modified(study) == _modified(study)
    assert len({each[_STUDY_DATE] for each in others}) > 1
    assert _modified(study, key=OTHER_KEY) != _modified(study)
    for weeks in (dates.date_offset_weeks(k, SUBJECT) for k in (KEY, OTHER_KEY)):
        assert dates.MIN_OFFSET_WEEKS <= weeks <= dates.MAX_OFFSET_WEEKS


@pytest.mark.parametrize(
    "value",
    [
        _value(_STUDY_DATE, "DA", "20260231"),  # no such date
        _value(_STUDY_DATE, "DA", "2026.09.27"),  # ACR-NEMA's form
        _value(_ACQUISITION_DATETIME, "DT", "2026"),  # no full date
        _value(_ACQUISITION_DATETIME, "DT", "20261231235960"),  # a leap second
        _value(_ACQUISITION_DATETIME, "DT", "20260927+1000"),  # needs an hour
        _value(_STUDY_DATE, "DA", "00010101"),  # before year 1 once moved
        _value(_STUDY_TIME, "DA", "20260927"),  # read in a VR its role does not use
        _value(_FRAME_ORIGIN, "OB", b"\x00" * 9),  # not an IEEE 1588 timestamp
    ],
)
def test_a_value_that_cannot_be_modified_stays_pending(value):
    zone = _value(ElementPath((), "(0008,0201)"), "SH", "+1100")
    given = (value,) if value.source == _TIMEZONE else (value, zone)

    assert value.source not in _modified(*given)


def test_differing_timezones_leave_offsets_and_local_datetimes_pending():
    nested = ElementPath((("(0018,A001)", 0),), "(0008,0201)")
    written = _modified(
        _value(_TIMEZONE, "SH", "+1000"),
        _value(nested, "SH", "+1100"),
        _value(_ACQUISITION_DATETIME, "DT", "20260927120000+1000"),
        _value(ElementPath((), "(0018,9074)"), "DT", "20260927120000"),
        _value(_STUDY_DATE, "DA", "20260927"),
    )

    assert set(written) == {ElementPath((), "(0018,9074)"), _STUDY_DATE}


@pytest.mark.parametrize("zone", ["+1500", "SENTINEL"])
def test_an_invalid_timezone_counts_as_absent_and_becomes_nominal(zone):
    nested = ElementPath((("(0018,A001)", 0),), "(0008,0201)")
    written = _modified(
        _value(_TIMEZONE, "SH", zone),
        _value(nested, "SH", "+1000"),
        _value(_ACQUISITION_DATETIME, "DT", "20260927013000+0000"),
    )

    assert written[_TIMEZONE] == (("+0000",), False)
    assert written[nested] == (("+0000",), False)
    # The local time is the valid offset, as if the invalid one were absent.
    (local,) = written[_ACQUISITION_DATETIME][0]
    assert local == dates.shift_datetime("20260927113000+0000", WEEKS)


def test_without_a_subject_only_values_that_do_not_move_are_settled():
    written = _modified(
        _value(_STUDY_DATE, "DA", "20260927"),
        _value(_STUDY_TIME, "TM", "101500"),
        _value(_CALIBRATION_DATE, "DA", "20200101"),
        _value(_TIMEZONE, "SH", "+1000"),
        identity=None,
    )

    assert set(written) == {_CALIBRATION_DATE, _TIMEZONE}


def _transform(options, key=KEY):
    return InstanceTransform(
        compose_custom_policy(options), key, unvalidated_policy=True
    )


def _plan(patient_id=synthetic.PATIENT_ID, **attributes):
    plan = synthetic.rt_plan()
    plan.PatientID = patient_id
    plan.StudyDate = "20260927"
    plan.StudyTime = "101500"
    plan.RTPlanDate = "20261004"
    plan.RTPlanTime = "083000"
    plan.TimezoneOffsetFromUTC = "+1000"
    plan.DateOfLastCalibration = "20200101"
    for keyword, value in attributes.items():
        setattr(plan, keyword, value)
    return plan


def _result(transform, dataset):
    data = synthetic.written(dataset)
    return transform(data, InstanceRecord.from_file(data))


def _written(transform, dataset):
    result = _result(transform, dataset)
    assert isinstance(result, run.Transformed), result
    return pydicom.dcmread(io.BytesIO(result.data)), result


@pytest.mark.deid_requirement("PS3.15-E.3.6-02", "MIDI-BP-12")
@pytest.mark.deid_requirement("PS3.15-E.3.6-03")
def test_an_instance_is_written_with_every_date_modified_and_released():
    weeks = dates.date_offset_weeks(
        KEY, SubjectIdentity.from_patient_id(synthetic.PATIENT_ID)
    )
    plan = _plan()

    written, result = _written(_transform([MODIFIED_DATES]), plan)

    assert written.StudyDate == _moved("20260927", weeks)
    assert written.RTPlanDate == _moved("20261004", weeks)
    assert written.StudyTime == "101500"
    assert written.RTPlanTime == "083000"
    assert written.TimezoneOffsetFromUTC == "+0000"
    assert written.DateOfLastCalibration == dummy_values.CONSTANTS["DA"][0]
    assert written.LongitudinalTemporalInformationModified == "MODIFIED"
    codes = [i.CodeValue for i in written.DeidentificationMethodCodeSequence]
    assert codes == ["113100", MODIFIED_DATES_CODE]
    for source in ("20260927", "20261004", "20200101"):
        assert source.encode() not in result.data
    for element in written.iterall():
        if element.VR in ("DA", "DT", "TM") and element.value:
            assert values_problem(element.VR, "1-n", list(_values(element))) is None
    # The residual search finds no source date in the written file.
    decision = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    assert isinstance(decision, run.Release), decision


def _values(element):
    value = element.value
    return value if isinstance(value, (list, pydicom.multival.MultiValue)) else [value]


@pytest.mark.deid_requirement("MIDI-BP-12")
def test_a_subject_moves_by_one_offset_in_every_instance_and_other_subjects_apart():
    transform = _transform([MODIFIED_DATES])
    first, _ = _written(transform, _plan())
    second, _ = _written(transform, _plan(StudyDate="20261011"))
    others = [
        _written(transform, _plan(patient_id=f"SENTINEL-{n}"))[0].StudyDate
        for n in range(2, 8)
    ]

    gap = _date_of(second.StudyDate) - _date_of(first.StudyDate)
    assert gap == datetime.timedelta(days=14)
    assert len(set(others)) > 1
    # A run with another key moves the same subject by an unrelated offset.
    again, _ = _written(_transform([MODIFIED_DATES], OTHER_KEY), _plan())
    assert again.StudyDate != first.StudyDate


def test_an_instance_with_a_date_that_cannot_be_modified_is_sequestered():
    result = _result(_transform([MODIFIED_DATES]), _plan(StudyDate="20260231"))

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.PENDING_EDIT,)


def test_device_dates_that_retain_device_identity_would_keep_are_modified_by_role():
    # tps-import resolves Retain Device Identity's K and Modified Dates' C on
    # eleven attributes as C, by role (D-007).
    composed = compose_policy("tps-import")
    actions = {**composed.actions, **composed.supplementary_actions}
    assert actions["(0018,1200)"] == "C"
    (cleaner,) = [
        c for c in cleaners.cleaners_for(composed) if c.option == MODIFIED_DATES
    ]
    assert "(0018,1200)" in cleaner.tags
    assert [c.option for c in cleaners.cleaners_for(composed)] == [
        DEVICE_IDENTITY,
        PATIENT_CHARACTERISTICS,
        MODIFIED_DATES,
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.6-04")
def test_the_statement_describes_how_dates_are_modified_and_needs_nothing_else():
    statement = conformance.conformance_statement(
        compose_custom_policy([MODIFIED_DATES]), vocabulary=None
    )

    assert not statement.pending
    (cleaned,) = statement.cleaned
    assert cleaned.option == MODIFIED_DATES
    assert set(cleaned.tags) == modified_dates.TAGS
    roles = load_temporal_roles().rules
    expected = {
        role.value: sum(roles[tag].role is role for tag in modified_dates.TAGS)
        for role in TemporalRole
    }
    assert dict(statement.temporal.roles) == {
        role: count for role, count in expected.items() if count
    }
    text = conformance_markdown.render_markdown(statement)
    section = text.split("## Dates and times")[1].split("\n## ")[0]
    assert f"gives C to {len(modified_dates.TAGS)} of them" in section
    assert f"{expected['subject-event']} subject events" in section
    assert "is not yet described" not in section
    assert modified_dates.METHOD in text
    assert "`MODIFIED`" in section
