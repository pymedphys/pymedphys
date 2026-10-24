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

"""Synthetic birth dates under the ``tps-import`` preset (D-008)."""

import datetime
import io
import json
import pathlib
import random

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    birth_dates,
    dates,
    keys,
    profiles,
    run,
    uids,
)
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.edits import Edit, EditKind, InstanceEdits
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.pseudonyms import SubjectIdentity
from pymedphys._dicom.deidentify.reasons import TransformReason
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames

from . import _synthetic_references as synthetic

KEY = keys.DeidKey(bytes(range(32)))
SUBJECT = SubjectIdentity.from_patient_id(synthetic.PATIENT_ID)
OTHER_ID = "SYNTHETIC-8R3L"
OTHER_SUBJECT = SubjectIdentity.from_patient_id(OTHER_ID)
# A source birth date, which no output may hold.
SOURCE_BIRTH_DATE = "19650704"
STUDIES = ("2.25.110", "2.25.120", "2.25.130")


@pytest.fixture(name="home", autouse=True)
def fixture_home(tmp_path, monkeypatch):
    """Keep the PyMedPhys configuration directory inside the test's own."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    return home


def _age(birth, day):
    """Return the age in completed years on ``day`` of someone born on ``birth``.

    Independently of the engine: the difference of the years, less one where
    the birthday has not yet come that year.
    """
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


def _text(day):
    return f"{day.year:04d}{day.month:02d}{day.day:02d}"


def _day(text):
    return datetime.datetime.strptime(text, "%Y%m%d").date()


@pytest.mark.parametrize(
    "shifted, age, expected",
    [
        ("20240615", 45, "19790615"),
        ("20240101", 0, "20240101"),
        ("20240229", 45, "19790228"),
        ("20240229", 44, "19800229"),
        ("20230301", 40, "19830301"),
        ("00500101", 49, "00010101"),
    ],
)
def test_the_birth_date_is_the_shifted_date_less_the_age(shifted, age, expected):
    assert birth_dates.synthetic_birth_date(shifted, age) == expected
    assert _age(_day(expected), _day(shifted)) == age


def test_every_synthetic_birth_date_gives_its_age_on_its_date():
    generator = random.Random(8)
    start = datetime.date(1990, 1, 1).toordinal()
    for _ in range(2000):
        day = datetime.date.fromordinal(start + generator.randrange(40 * 366))
        age = generator.randrange(120)
        birth = birth_dates.synthetic_birth_date(_text(day), age)
        assert _age(_day(birth), day) == age


@pytest.mark.parametrize(
    "shifted, age", [("00500101", 50), ("2024022", 1), ("20240230", 1)]
)
def test_a_birth_date_that_cannot_be_written_is_refused(shifted, age):
    with pytest.raises(ValueError):
        birth_dates.synthetic_birth_date(shifted, age)


def test_ages_are_consistent_exactly_where_one_birth_date_gives_them_all():
    # Checked against every birth date in turn, from the definition of an
    # age in completed years.
    generator = random.Random(24)
    for _ in range(300):
        first = datetime.date(2000, 1, 1) + datetime.timedelta(
            days=generator.randrange(3 * 366)
        )
        observations = []
        for _ in range(generator.randrange(1, 4)):
            day = first + datetime.timedelta(days=generator.randrange(3 * 366))
            observations.append((day, 30 + generator.randrange(5)))
        earliest = min(day for day, _ in observations)
        candidates = (
            datetime.date(earliest.year - 40, 1, 1) + datetime.timedelta(days=n)
            for n in range(20 * 366)
        )
        expected = any(
            all(_age(birth, day) == age for day, age in observations)
            for birth in candidates
        )
        assert birth_dates.ages_agree(observations) == expected, observations


def _set(dataset, keyword, vr, value):
    """Set a value without pydicom's checks, so that it can be padded."""
    tag = pydicom.datadict.tag_for_keyword(keyword)
    dataset[tag] = pydicom.DataElement(
        tag, vr, value, validation_mode=pydicom.config.IGNORE
    )


def _instance(number, study, *, date=None, age=None, patient=synthetic.PATIENT_ID):
    dataset = synthetic.ct_slice(number % len(synthetic.CT_SLICES))
    synthetic.uid(dataset, "SOPInstanceUID", f"{study}.{number}")
    synthetic.uid(dataset, "SeriesInstanceUID", f"{study}.0")
    synthetic.uid(dataset, "StudyInstanceUID", study)
    dataset.PatientID = patient
    dataset.PatientBirthDate = SOURCE_BIRTH_DATE
    if date is not None:
        _set(dataset, "StudyDate", "DA", date)
    if age is not None:
        _set(dataset, "PatientAge", "AS", age)
    return dataset


def _files(datasets):
    return [synthetic.written(dataset) for dataset in datasets]


def _prepared(datasets, store=None, *, order=None):
    store = profiles.ProfileStore.ephemeral(KEY) if store is None else store
    files = _files(datasets)
    positions = range(len(files)) if order is None else order
    chosen = birth_dates.BirthDates(KEY, store)
    chosen.prepare(
        {position: InstanceRecord.from_file(files[position]) for position in positions},
        files.__getitem__,
    )
    return chosen, store


def _expected(source_date, age, store=None, subject=SUBJECT):
    weeks = (store or profiles.ProfileStore.ephemeral(KEY)).profile(subject)
    shifted = dates.shift_date(source_date, weeks.date_offset_weeks)
    return birth_dates.synthetic_birth_date(shifted, age)


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_several_studies_at_one_age_give_one_birth_date():
    chosen, store = _prepared(
        [
            _instance(0, STUDIES[0], date="20200105", age="040Y"),
            _instance(1, STUDIES[0], date="20200105", age="040Y"),
            _instance(2, STUDIES[1], date="20200601", age="040Y"),
        ]
    )

    assert chosen.value(SUBJECT) == _expected("20200105", 40, store)
    assert not chosen.conflicted(SUBJECT)


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_the_earliest_study_is_the_reference_across_a_birthday():
    # The birthday falls between the studies, so the age changes.
    chosen, store = _prepared(
        [
            _instance(0, STUDIES[1], date="20210301", age="041Y"),
            _instance(1, STUDIES[0], date="20200105", age="040Y"),
        ]
    )

    value = chosen.value(SUBJECT)
    assert value == _expected("20200105", 40, store)
    weeks = store.profile(SUBJECT).date_offset_weeks
    reference = store.profile(SUBJECT).birth_date.reference
    assert reference == profiles.ReferenceStudy(
        uids.replacement_uid(KEY, STUDIES[0]), dates.shift_date("20200105", weeks), 40
    )
    # The later study's age is the source's, not the synthetic date's.
    later = dates.shift_date("20210301", weeks)
    assert _age(_day(value), _day(later)) in (40, 41)


def test_studies_on_one_date_take_the_least_replacement_uid():
    chosen, store = _prepared(
        [
            _instance(0, STUDIES[0], date="20200105", age="040Y"),
            _instance(1, STUDIES[1], date="20200105", age="040Y"),
        ]
    )

    least = min(uids.replacement_uid(KEY, study) for study in STUDIES[:2])
    assert store.profile(SUBJECT).birth_date.reference.study == least
    assert chosen.value(SUBJECT) == _expected("20200105", 40, store)


def test_a_leap_day_reference_maps_to_28_february():
    # A source date chosen so that its shifted date is 29 February.
    weeks = dates.date_offset_weeks(KEY, SUBJECT)
    source = datetime.date(2024, 2, 29) + datetime.timedelta(weeks=weeks)
    chosen, _ = _prepared([_instance(0, STUDIES[0], date=_text(source), age="045Y")])

    assert chosen.value(SUBJECT) == "19790228"


def test_the_choice_does_not_depend_on_the_order_of_the_run():
    datasets = [
        _instance(0, STUDIES[2], date="20220110", age="042Y"),
        _instance(1, STUDIES[0], date="20200105", age="040Y"),
        _instance(2, STUDIES[1], date="20210601", age="041Y"),
    ]
    values = {
        _prepared(datasets, order=order)[0].value(SUBJECT)
        for order in ([0, 1, 2], [2, 1, 0], [1, 2, 0])
    }

    assert len(values) == 1
    assert values == {_expected("20200105", 40)}


@pytest.mark.parametrize(
    "datasets",
    [
        # No age.
        [_instance(0, STUDIES[0], date="20200105")],
        # No date.
        [_instance(0, STUDIES[0], age="040Y")],
        # An age that is not in completed years.
        [_instance(0, STUDIES[0], date="20200105", age="040M")],
        # A date that is not a date.
        [_instance(0, STUDIES[0], date="20200230", age="040Y")],
        # One study's instances hold different ages.
        [
            _instance(0, STUDIES[0], date="20200105", age="040Y"),
            _instance(1, STUDIES[0], date="20200105", age="041Y"),
        ],
        # One study's instances hold different dates.
        [
            _instance(0, STUDIES[0], date="20200105", age="040Y"),
            _instance(1, STUDIES[0], date="20200106", age="040Y"),
        ],
        # No birth date gives both ages.
        [
            _instance(0, STUDIES[0], date="20200105", age="040Y"),
            _instance(1, STUDIES[1], date="20200601", age="042Y"),
        ],
        # The age decreases while the date increases.
        [
            _instance(0, STUDIES[0], date="20200105", age="041Y"),
            _instance(1, STUDIES[1], date="20210601", age="040Y"),
        ],
    ],
)
def test_missing_or_inconsistent_ages_give_no_birth_date(datasets):
    chosen, store = _prepared(datasets)

    assert chosen.value(SUBJECT) == ""
    assert store.profile(SUBJECT).birth_date == profiles.NO_BIRTH_DATE


def test_an_instance_without_values_adds_nothing():
    chosen, store = _prepared(
        [
            _instance(0, STUDIES[0], date="20200105", age="040Y"),
            _instance(1, STUDIES[0]),
            _instance(2, STUDIES[1]),
        ]
    )

    assert chosen.value(SUBJECT) == _expected("20200105", 40, store)


def test_padded_values_are_read_without_their_padding():
    chosen, store = _prepared(
        [
            _instance(0, STUDIES[0], date="20200105", age="040Y"),
            _instance(1, STUDIES[0], date="20200105 ", age="040Y "),
        ]
    )

    assert chosen.value(SUBJECT) == _expected("20200105", 40, store)


def test_subjects_are_chosen_apart():
    chosen, store = _prepared(
        [
            _instance(0, STUDIES[0], date="20200105", age="040Y"),
            _instance(1, STUDIES[1], date="20200105", age="060Y", patient=OTHER_ID),
        ]
    )

    assert chosen.value(SUBJECT) == _expected("20200105", 40, store)
    assert chosen.value(OTHER_SUBJECT) == _expected(
        "20200105", 60, store, OTHER_SUBJECT
    )


def test_a_subject_that_was_not_prepared_has_no_birth_date():
    chosen, _ = _prepared([_instance(0, STUDIES[0], date="20200105", age="040Y")])

    assert chosen.value(OTHER_SUBJECT) is None
    assert chosen.value(None) is None
    assert not chosen.conflicted(OTHER_SUBJECT)
    assert not chosen.conflicted(None)


def _store(tmp_path):
    return profiles.ProfileStore.open(KEY, tmp_path / "custodian" / "profiles.json")


def _reopened(store, tmp_path):
    store.save()
    return _store(tmp_path)


@pytest.fixture(name="custodian")
def fixture_custodian(tmp_path):
    (tmp_path / "custodian").mkdir()


@pytest.mark.usefixtures("custodian")
def test_a_later_run_reads_the_recorded_birth_date_back(tmp_path):
    first, store = _prepared(
        [_instance(0, STUDIES[1], date="20200105", age="040Y")], _store(tmp_path)
    )
    recorded = first.value(SUBJECT)
    # An earlier study arrives later; the reference does not change.
    later, _ = _prepared(
        [
            _instance(0, STUDIES[0], date="20190105", age="039Y"),
            _instance(1, STUDIES[1], date="20200105", age="040Y"),
        ],
        _reopened(store, tmp_path),
    )

    assert later.value(SUBJECT) == recorded
    assert not later.conflicted(SUBJECT)


@pytest.mark.usefixtures("custodian")
def test_a_recorded_birth_date_wins_over_a_changed_derivation(tmp_path):
    first, store = _prepared(
        [_instance(0, STUDIES[0], date="20200105", age="040Y")], _store(tmp_path)
    )
    store.save()
    path = tmp_path / "custodian" / "profiles.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    (profile,) = document["subjects"].values()
    profile["birth_date"]["date"] = "19000101"
    path.write_text(json.dumps(document), encoding="utf-8")

    later, _ = _prepared(
        [_instance(0, STUDIES[0], date="20200105", age="040Y")], _store(tmp_path)
    )

    assert first.value(SUBJECT) != "19000101"
    assert later.value(SUBJECT) == "19000101"


@pytest.mark.usefixtures("custodian")
def test_a_recorded_choice_of_no_birth_date_is_kept(tmp_path):
    _, store = _prepared([_instance(0, STUDIES[0], date="20200105")], _store(tmp_path))
    later, _ = _prepared(
        [_instance(0, STUDIES[0], date="20200105", age="040Y")],
        _reopened(store, tmp_path),
    )

    assert later.value(SUBJECT) == ""
    assert not later.conflicted(SUBJECT)


@pytest.mark.parametrize(
    "later",
    [
        # The reference study with another age.
        [_instance(0, STUDIES[0], date="20200105", age="041Y")],
        # The reference study with another date.
        [_instance(0, STUDIES[0], date="20200106", age="040Y")],
        # Another study whose age no birth date reconciles with the reference's.
        [_instance(0, STUDIES[1], date="20190105", age="041Y")],
        # Another study whose instances disagree.
        [
            _instance(0, STUDIES[1], date="20210105", age="041Y"),
            _instance(1, STUDIES[1], date="20210105", age="040Y"),
        ],
    ],
)
@pytest.mark.usefixtures("custodian")
def test_a_later_run_that_contradicts_the_reference_is_conflicted(tmp_path, later):
    _, store = _prepared(
        [_instance(0, STUDIES[0], date="20200105", age="040Y")], _store(tmp_path)
    )
    recorded = store.profile(SUBJECT).birth_date

    chosen, reopened = _prepared(later, _reopened(store, tmp_path))

    assert chosen.conflicted(SUBJECT)
    assert chosen.value(SUBJECT) is None
    # The profile is unchanged.
    assert reopened.profile(SUBJECT).birth_date == recorded


@pytest.mark.usefixtures("custodian")
def test_a_later_run_without_the_reference_agrees_with_consistent_ages(tmp_path):
    _, store = _prepared(
        [_instance(0, STUDIES[0], date="20200105", age="040Y")], _store(tmp_path)
    )
    later, _ = _prepared(
        [
            _instance(0, STUDIES[1], date="20210105", age="041Y"),
            _instance(1, STUDIES[2], date="20200105"),
        ],
        _reopened(store, tmp_path),
    )

    assert later.value(SUBJECT) == store.profile(SUBJECT).birth_date.value


def _edits(action="Z", kind=EditKind.EMPTY, path=birth_dates.PATIENTS_BIRTH_DATE):
    return InstanceEdits((Edit(path, action, kind),), (), (), ())


@pytest.mark.parametrize(
    "action, kind", [("Z", EditKind.EMPTY), ("D", EditKind.REPLACE)]
)
def test_the_birth_date_replaces_z_and_d_at_the_top_level(action, kind):
    (edit,) = birth_dates.with_birth_date(_edits(action, kind), "19790615").edits

    assert (edit.kind, edit.values, edit.action) == (
        EditKind.REPLACE,
        ("19790615",),
        action,
    )


def test_no_birth_date_leaves_z_as_it_is():
    edits = _edits()

    assert birth_dates.with_birth_date(edits, "").edits == edits.edits


def test_an_unprepared_subjects_birth_date_stays_pending():
    (edit,) = birth_dates.with_birth_date(_edits(), None).edits

    assert edit.kind is EditKind.PENDING


def test_a_birth_date_inside_a_sequence_is_left_as_it_is():
    nested = birth_dates.ElementPath(
        (("(0010,1002)", 0),), birth_dates.PATIENTS_BIRTH_DATE.tag
    )
    edits = _edits(path=nested)

    assert birth_dates.with_birth_date(edits, "19790615").edits == edits.edits


def _transform(store=None):
    return InstanceTransform(
        compose_policy("tps-import"),
        KEY,
        cleaning=DescriptorCleaning(None, ReviewedNames.empty()),
        profiles=store,
        unvalidated_policy=True,
    )


def _transformed_all(transform, datasets):
    files = _files(datasets)
    records = {
        position: InstanceRecord.from_file(f) for position, f in enumerate(files)
    }
    transform.prepare(records, files.__getitem__)
    return [transform(f, records[position]) for position, f in enumerate(files)]


def _written(result):
    assert isinstance(result, run.Transformed), result
    return pydicom.dcmread(io.BytesIO(result.data))


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_every_instance_of_a_subject_takes_its_birth_date():
    transform = _transform()
    results = _transformed_all(
        transform,
        [
            _instance(0, STUDIES[0], date="20200105", age="040Y"),
            _instance(1, STUDIES[0], date="20200105", age="040Y"),
            _instance(2, STUDIES[1], date="20210601"),
        ],
    )

    written = [_written(result) for result in results]
    expected = _expected("20200105", 40, transform.profiles)
    assert [each.PatientBirthDate for each in written] == [expected] * 3
    for result in results:
        assert SOURCE_BIRTH_DATE.encode() not in result.data
    # Patient's Age is kept, as Retain Patient Characteristics keeps it.
    assert written[0].PatientAge == "040Y"


def test_without_ages_the_birth_date_is_emptied():
    (result,) = _transformed_all(_transform(), [_instance(0, STUDIES[0])])

    written = _written(result)
    assert "PatientBirthDate" in written
    assert written.PatientBirthDate == ""


@pytest.mark.usefixtures("custodian")
def test_a_conflict_sequesters_every_instance_of_the_subject(tmp_path):
    store = _store(tmp_path)
    _transformed_all(
        _transform(store), [_instance(0, STUDIES[0], date="20200105", age="040Y")]
    )

    results = _transformed_all(
        _transform(_reopened(store, tmp_path)),
        [
            _instance(0, STUDIES[0], date="20200105", age="041Y"),
            _instance(1, STUDIES[1]),
            _instance(2, STUDIES[2], date="20200105", age="030Y", patient=OTHER_ID),
        ],
    )

    for result in results[:2]:
        assert isinstance(result, run.Sequestered)
        assert result.reasons == (TransformReason.BIRTH_DATE_CONFLICT,)
    # Another subject is unaffected.
    assert isinstance(results[2], run.Transformed)


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.usefixtures("custodian")
def test_incremental_runs_write_the_same_birth_date(tmp_path):
    store = _store(tmp_path)
    first = _transformed_all(
        _transform(store), [_instance(0, STUDIES[1], date="20200105", age="040Y")]
    )
    later = _transformed_all(
        _transform(_reopened(store, tmp_path)),
        [_instance(1, STUDIES[0], date="20190105", age="039Y")],
    )

    assert _written(first[0]).PatientBirthDate == _written(later[0]).PatientBirthDate


def test_other_policies_empty_the_birth_date():
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)
    (result,) = _transformed_all(
        transform, [_instance(0, STUDIES[0], date="20200105", age="040Y")]
    )

    assert _written(result).PatientBirthDate == ""
