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

"""Tests of the MIDI benchmark harness and its answer-key reader (D-018).

Every answer key here is made by hand in the layout that the NCI validation
script reads, and every DICOM file is synthetic. The category codes are
made up for the tests.
"""

import csv
import os
import stat
import hashlib
import json
import sqlite3

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import midi_benchmark as benchmark
from pymedphys._dicom.deidentify import midi_benchmark_command, midi_script_results
from pymedphys._dicom.deidentify.element_rules import ElementRules
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.midi_answer_key import (
    Action,
    AnswerKeyError,
    Categories,
    Category,
    category_of,
    parse_check,
    parse_path,
    read_answer_key,
)
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys.cli import define_parser

from . import _synthetic_references as synthetic

STUDY_DESCRIPTION = "SYNTHETIC BENCHMARK STUDY"
STUDY_DATE = "20210304"
PIXELS = bytes(range(8))
OTHER_PATIENT = "SYNTHETIC-OTHER-PATIENT"
MR_STUDY = "2.25.702"
MR_SERIES = "2.25.703"
MR_INSTANCE = "2.25.704"
ABSENT_INSTANCE = "2.25.705"
CT_IOD = "CT Image"


def _check(action, place=None, *, value=None, text=None, **categories):
    """Return one check, with its text wrapped as the key wraps it."""
    nested = {}
    for name, code in categories.items():
        family, field = name.split("_")
        nested.setdefault(family, {})[field] = code
    check = {
        "action": f"<{action}>",
        "action_text": None if text is None else f"<{text}>",
        "value": None if value is None else f"<{value}>",
        "tag_ds": place,
        "answer_category_v2": nested,
    }
    return check


def _row(
    instance,
    checks,
    *,
    patient=synthetic.PATIENT_ID,
    study=synthetic.STUDY,
    series=synthetic.CT_SERIES,
    sop_class=synthetic.CT_IMAGE_STORAGE,
    modality="CT",
    scope=None,
):
    return {
        "PatientID": patient,
        "StudyInstanceUID": study,
        "SeriesInstanceUID": series,
        "SOPInstanceUID": instance,
        "SOPClassUID": sop_class,
        "Modality": modality,
        "AnswerData": json.dumps({str(i): check for i, check in enumerate(checks)}),
        **({} if scope is None else {"scope": f"<{scope}>"}),
    }


def _answer_key(path, rows, *, scope=False):
    columns = [
        "PatientID",
        "StudyInstanceUID",
        "SeriesInstanceUID",
        "SOPInstanceUID",
        "SOPClassUID",
        "Modality",
        "AnswerData",
        *(["scope"] if scope else []),
    ]
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(f"CREATE TABLE answer_data ({', '.join(columns)})")
        connection.executemany(
            f"INSERT INTO answer_data VALUES ({', '.join('?' * len(columns))})",
            [[row.get(column) for column in columns] for row in rows],
        )
    connection.close()
    return path


def test_the_reader_unwraps_values_and_reads_places_and_categories(tmp_path):
    checks = [
        _check(
            "text_removed",
            "<(0008,1030)>",
            value=STUDY_DESCRIPTION,
            text=STUDY_DESCRIPTION,
            hipaa_m="TEST-HIPAA-M",
            tcia_p15="TEST-TCIA",
        ),
        _check("uid_consistent", "<(0008,1140)>[<0001>]<(0008,1155)>", value="2.25.9"),
        _check("pixels_hidden"),
    ]
    path = _answer_key(tmp_path / "key.db", [_row(synthetic.CT_SLICES[0], checks)])

    key = read_answer_key(path)

    assert key.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    (instance,) = key.instances
    assert instance.sop_instance_uid == synthetic.CT_SLICES[0]
    assert instance.modality == "CT"
    assert instance.scope is None
    removed, consistent, hidden = instance.checks
    assert removed.action is Action.TEXT_REMOVED
    assert removed.value == removed.action_text == STUDY_DESCRIPTION
    assert str(removed.path) == "(0008,1030)"
    assert removed.categories == Categories(
        hipaa_m="TEST-HIPAA-M", tcia_p15="TEST-TCIA"
    )
    assert removed.category == Category("hipaa", "TEST-HIPAA-M")
    assert consistent.path.items == (1,)
    assert str(consistent.path) == "(0008,1140)/(0008,1155)"
    assert hidden.path is None and not hidden.path_unreadable


def test_the_reader_takes_dotted_categories_a_scope_and_an_unknown_action(tmp_path):
    check = {
        "action": "<a_future_action>",
        "tag_ds": "(0010,0010)",
        "answer_category_v2": {"tcia.ptkb": "TEST-PTKB", "hipaa.z": ""},
    }
    path = _answer_key(
        tmp_path / "key.db",
        [_row(synthetic.CT_SLICES[0], [check], scope="Series")],
        scope=True,
    )

    (instance,) = read_answer_key(path).instances

    assert instance.scope == "Series"
    (read,) = instance.checks
    assert read.action is None
    assert read.action_name == "a_future_action"
    assert read.path is None and read.path_unreadable
    assert read.categories == Categories(tcia_ptkb="TEST-PTKB")


def test_a_private_place_is_read_by_its_creator_and_last_two_digits():
    path = parse_path('<(0019,"SYNTHETIC CREATOR",92)>')

    assert path.attribute.group == 0x0019
    assert path.attribute.element == 0x92
    assert path.attribute.creator == "SYNTHETIC CREATOR"
    assert str(path) == "(0019,xx92)"


@pytest.mark.parametrize(
    "place", ["(0010,0010)", "<(0010,0010)>[<0000>]", "<(0010,001)>", "<(0010,0010)>x"]
)
def test_a_place_not_in_the_indexers_form_is_unreadable(place):
    assert parse_path(place) is None


def test_a_key_without_the_answer_table_is_refused_without_a_value(tmp_path):
    path = tmp_path / "key.db"
    connection = sqlite3.connect(path)
    with connection:
        connection.execute("CREATE TABLE other (PatientID)")
    connection.close()

    with pytest.raises(AnswerKeyError, match="no table 'answer_data'"):
        read_answer_key(path)


def test_a_file_that_is_not_a_database_is_refused(tmp_path):
    path = tmp_path / "key.db"
    path.write_bytes(b"not a database, " * 64)

    with pytest.raises(AnswerKeyError, match="not an SQLite database"):
        read_answer_key(path)


def test_the_checks_of_every_row_of_an_instance_are_taken_together(tmp_path):
    first = _row(synthetic.CT_SLICES[0], [_check("tag_retained", "<(0008,0060)>")])
    second = _row(
        synthetic.CT_SLICES[0],
        [_check("date_shifted", "<(0008,0020)>", value=STUDY_DATE)],
        scope="Series",
    )
    key = read_answer_key(_answer_key(tmp_path / "key.db", [first, second], scope=True))

    (instance,) = list(key.by_sop_instance().values())
    assert [check.action for check in instance.checks] == [
        Action.TAG_RETAINED,
        Action.DATE_SHIFTED,
    ]


def test_a_numeric_patient_id_and_missing_identifiers_are_read(tmp_path):
    row = _row(synthetic.CT_SLICES[0], [])
    row["PatientID"] = 1234
    row["Modality"] = None
    row["SOPClassUID"] = None

    (instance,) = read_answer_key(_answer_key(tmp_path / "key.db", [row])).instances

    assert instance.patient_id == "1234"
    assert instance.modality is None and instance.sop_class_uid is None


def test_a_row_without_its_sop_instance_uid_is_refused(tmp_path):
    row = _row(synthetic.CT_SLICES[0], [])
    row["SOPInstanceUID"] = None

    with pytest.raises(AnswerKeyError, match="row 1 has no SOPInstanceUID"):
        read_answer_key(_answer_key(tmp_path / "key.db", [row]))


def test_checks_that_are_not_json_are_refused_without_quoting_them(tmp_path):
    row = _row(synthetic.CT_SLICES[0], [])
    row["AnswerData"] = f"{synthetic.PATIENT_ID} is not JSON"
    path = _answer_key(tmp_path / "key.db", [row])

    with pytest.raises(AnswerKeyError) as raised:
        read_answer_key(path)

    assert "row 1" in str(raised.value)
    assert synthetic.PATIENT_ID not in str(raised.value)


@pytest.mark.parametrize(
    "action, expected",
    [
        (Action.TAG_RETAINED, Category("dicom", "TEST-IOD")),
        (Action.TEXT_NOTNULL, Category("dicom", "TEST-IOD")),
        (Action.DATE_SHIFTED, Category("hipaa", "HIPAA-C")),
        (Action.UID_CHANGED, Category("hipaa", "HIPAA-R")),
        (Action.PIXELS_HIDDEN, Category("hipaa", "HIPAA-A")),
        (Action.PATID_CONSISTENT, Category("dicom", "DICOM-P15-BASIC-C")),
        (Action.UID_CONSISTENT, Category("dicom", "DICOM-P15-BASIC-U")),
        (Action.PIXELS_RETAINED, Category("tcia", "TCIA-P15-PIX-K")),
        (Action.TEXT_REMOVED, Category("hipaa", "TEST-Z")),
        (Action.TEXT_RETAINED, Category("tcia", "TEST-PTKB")),
        (None, None),
    ],
)
def test_each_action_scores_under_the_validation_scripts_category(action, expected):
    categories = Categories(
        dicom_iod="TEST-IOD", hipaa_z="TEST-Z", tcia_ptkb="TEST-PTKB"
    )

    assert category_of(action, categories) == expected


def test_text_without_a_category_scores_under_none():
    assert category_of(Action.TEXT_RETAINED, Categories(hipaa_z="TEST-Z")) is None


def _released_ct():
    dataset = pydicom.Dataset()
    dataset.Modality = "CT"
    dataset.StudyDate = ""
    dataset.SliceThickness = "2.5"
    dataset.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
    dataset.PatientID = "DEID-TESTPSEUDONYM0"
    dataset.ReferencedImageSequence = [
        synthetic.reference(synthetic.CT_IMAGE_STORAGE, "2.25.11"),
        synthetic.reference(synthetic.CT_IMAGE_STORAGE, "2.25.12"),
    ]
    block = dataset.private_block(0x0019, "SYNTHETIC CREATOR", create=True)
    block.add_new(0x92, "LO", "SYNTHETIC PRIVATE")
    dataset.PixelData = PIXELS
    return dataset


MAPPING = benchmark.IdentifierMapping(
    uids={"2.25.1": "2.25.12"}, patient_ids={"SYNTHETIC-7Q2K": "DEID-TESTPSEUDONYM0"}
)


def _score(action, place=None, *, iod=CT_IOD, **fields):
    check = read_answer_check(action, place, **fields)
    return benchmark.score_check(
        check,
        _released_ct(),
        MAPPING,
        ElementRules(compose_policy("basic")),
        None if iod is None else load_iod_tables().iods[iod],
    )


def read_answer_check(action, place, *, value=None, text=None):
    return parse_check(_check(action, place, value=value, text=text))


PASSED = benchmark.Scored(benchmark.Result.PASSED)
FAILED = benchmark.Scored(benchmark.Result.FAILED)


@pytest.mark.parametrize(
    "action, place, fields, expected",
    [
        ("tag_retained", "<(0008,0060)>", {}, PASSED),
        ("tag_retained", "<(0008,0020)>", {}, PASSED),
        # Study Date is Z under the Basic Profile: a deliberate difference.
        (
            "text_notnull",
            "<(0008,0020)>",
            {},
            benchmark.Scored(benchmark.Result.FAILED, "Z", deliberate=True),
        ),
        ("text_notnull", "<(0008,0060)>", {}, PASSED),
        ("text_retained", "<(0018,0050)>", {"text": "2.50"}, PASSED),
        ("text_retained", "<(0008,0008)>", {"text": "primary"}, PASSED),
        (
            "text_retained",
            "<(0008,0008)>",
            {"text": "ORIGINAL\\PRIMARY\\AXIAL"},
            PASSED,
        ),
        ("text_removed", "<(0008,0020)>", {"text": STUDY_DATE}, PASSED),
        ("text_removed", "<(0008,0060)>", {"text": "ct"}, FAILED),
        ("text_removed", "<(0008,0008)>", {"text": "axial plane"}, FAILED),
        ("text_removed", "<(0008,1030)>", {"text": STUDY_DESCRIPTION}, PASSED),
        ("date_shifted", "<(0008,0020)>", {"value": STUDY_DATE}, PASSED),
        (
            "uid_changed",
            "<(0008,1140)>[<0000>]<(0008,1155)>",
            {"value": "2.25.11"},
            FAILED,
        ),
        (
            "uid_changed",
            "<(0008,1140)>[<0005>]<(0008,1155)>",
            {"value": "2.25.11"},
            PASSED,
        ),
        (
            "uid_consistent",
            "<(0008,1140)>[<0001>]<(0008,1155)>",
            {"value": "2.25.1"},
            PASSED,
        ),
        (
            "uid_consistent",
            "<(0008,1140)>[<0000>]<(0008,1155)>",
            {"value": "2.25.1"},
            FAILED,
        ),
        ("patid_consistent", "<(0010,0020)>", {"value": "SYNTHETIC-7Q2K"}, PASSED),
        (
            "text_removed",
            '<(0019,"SYNTHETIC CREATOR",92)>',
            {"text": "private"},
            FAILED,
        ),
        ("text_removed", '<(0019,"OTHER CREATOR",92)>', {"text": "private"}, PASSED),
        (
            "pixels_retained",
            None,
            {"text": hashlib.md5(PIXELS, usedforsecurity=False).hexdigest()},
            PASSED,
        ),
        ("pixels_retained", None, {"text": "0" * 32}, FAILED),
    ],
)
def test_each_check_is_scored_by_the_validation_scripts_rule(
    action, place, fields, expected
):
    assert _score(action, place, **fields) == expected


@pytest.mark.parametrize(
    "action, place, fields, note",
    [
        ("pixels_hidden", None, {"text": "{}"}, "burned-in text needs OCR and review"),
        (
            "uid_consistent",
            "<(0008,1140)>[<0001>]<(0008,1155)>",
            {"value": "2.25.99"},
            "not in the mapping files",
        ),
        ("text_retained", "<(0008,0060)>", {}, "no text to compare"),
        ("date_shifted", "<(0008,0020)>", {}, "no value to compare"),
        ("text_removed", "<(0008,0060)>", {"text": "..."}, "no words to compare"),
        ("tag_retained", None, {}, "no place"),
    ],
)
def test_a_check_that_cannot_be_scored_is_not_evaluated(action, place, fields, note):
    assert _score(action, place, **fields) == benchmark.Scored(
        benchmark.Result.NOT_EVALUATED, note
    )


def test_a_kept_check_on_what_the_policy_removes_is_a_deliberate_difference():
    # Study Description is X under the Basic Profile, and a private
    # attribute is removed whatever its creator.
    assert _score(
        "text_retained", "<(0008,1030)>", text=STUDY_DESCRIPTION
    ) == benchmark.Scored(benchmark.Result.FAILED, "X", deliberate=True)
    assert _score("tag_retained", '<(0019,"OTHER CREATOR",93)>') == benchmark.Scored(
        benchmark.Result.FAILED, "X", deliberate=True
    )


def test_a_kept_check_in_a_sequence_that_the_policy_removes_is_deliberate():
    # Referenced Study Sequence is X/Z under the Basic Profile, which removes
    # or empties it with what it holds, whatever the attribute's own action.
    assert _score(
        "tag_retained", "<(0008,1110)>[<0000>]<(0008,1150)>"
    ) == benchmark.Scored(benchmark.Result.FAILED, "X/Z", deliberate=True)


def test_a_kept_check_on_what_the_policy_keeps_is_a_finding():
    # The Basic Profile keeps Rows, so its absence is not deliberate.
    assert _score("tag_retained", "<(0028,0010)>") == FAILED


@pytest.mark.parametrize(
    "place",
    [
        # Patient's Name is Z and Study Instance UID is U: the policy
        # replaces them, so a file without them breaks the policy.
        "<(0010,0010)>",
        "<(0020,000D)>",
        # The CT Image IOD defines Derivation Code Sequence, which the
        # Basic Profile therefore keeps; without the IOD it would be removed.
        "<(0008,9215)>",
    ],
)
def test_a_missing_attribute_that_the_policy_replaces_or_keeps_is_a_finding(place):
    assert _score("tag_retained", place) == FAILED


def test_the_iod_decides_whether_a_missing_sequence_is_deliberate():
    assert _score("tag_retained", "<(0008,9215)>", iod=None) == benchmark.Scored(
        benchmark.Result.FAILED, "X", deliberate=True
    )


def test_changed_pixel_data_is_never_deliberate():
    assert _score("pixels_retained", "<(7FE0,0010)>", text="0" * 32) == FAILED


@pytest.mark.parametrize(
    "action, expected",
    [
        ("text_removed", PASSED),
        ("text_retained", FAILED),
        ("date_shifted", PASSED),
        ("uid_changed", PASSED),
    ],
)
def test_a_missing_attribute_is_scored_before_what_the_check_compares(action, expected):
    # As the script does: the check has no text or value to compare, but
    # the attribute is not in the file, so the check is scored all the same.
    assert _score(action, "<(0028,0010)>") == expected


def test_an_empty_value_is_within_any_text_as_the_script_finds():
    assert _score("date_shifted", "<(0008,0060)>", value="") == FAILED


def _source(tmp_path):
    datasets = synthetic.collection()
    ct = datasets[0]
    ct.Modality = "CT"
    ct.StudyDate = STUDY_DATE
    ct.StudyDescription = STUDY_DESCRIPTION
    ct.Rows = 2
    ct.Columns = 2
    ct.BitsAllocated = 16
    ct.BitsStored = 16
    ct.HighBit = 15
    ct.PixelRepresentation = 0
    ct.SamplesPerPixel = 1
    ct.PhotometricInterpretation = "MONOCHROME2"
    ct.PixelData = PIXELS
    mr = synthetic.instance(synthetic.MR_IMAGE_STORAGE, MR_INSTANCE, MR_SERIES)
    mr.PatientID = OTHER_PATIENT
    mr.StudyInstanceUID = MR_STUDY
    source = tmp_path / "source"
    source.mkdir()
    for position, dataset in enumerate([*datasets, mr]):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))
    return source


def _benchmark_key(tmp_path):
    ct = [
        _check(
            "text_retained",
            "<(0008,1030)>",
            text=STUDY_DESCRIPTION,
            tcia_p15="TEST-RETAIN-DESCRIPTION",
        ),
        _check("date_shifted", "<(0008,0020)>", value=STUDY_DATE),
        _check("text_removed", "<(0008,0060)>", text="CT", hipaa_z="TEST-MODALITY"),
        _check("tag_retained", "<(0008,0060)>", dicom_iod="TEST-IOD"),
        _check("uid_consistent", "<(0020,000E)>", value=synthetic.CT_SERIES),
        _check("patid_consistent", "<(0010,0020)>", value=synthetic.PATIENT_ID),
        _check(
            "pixels_retained",
            text=hashlib.md5(PIXELS, usedforsecurity=False).hexdigest(),
        ),
        _check("pixels_hidden", text="{}"),
    ]
    rows = [
        _row(synthetic.CT_SLICES[0], ct),
        _row(
            synthetic.DOSE,
            [_check("uid_changed", "<(0008,0018)>", value=synthetic.DOSE)],
            series=synthetic.DOSE_SERIES,
            sop_class=synthetic.RT_DOSE_STORAGE,
            modality="RTDOSE",
        ),
        _row(
            MR_INSTANCE,
            [_check("tag_retained", "<(0008,0060)>", dicom_iod="TEST-IOD")],
            patient=OTHER_PATIENT,
            study=MR_STUDY,
            series=MR_SERIES,
            sop_class=synthetic.MR_IMAGE_STORAGE,
            modality="MR",
        ),
        _row(
            ABSENT_INSTANCE,
            [_check("date_shifted", "<(0008,0020)>", value=STUDY_DATE)],
            modality="CT",
        ),
    ]
    return _answer_key(tmp_path / "key.db", rows)


def _category(document, family, code):
    (row,) = [
        row
        for row in document["categories"]
        if row["family"] == family and row["code"] == code
    ]
    return row


def test_a_benchmark_run_scores_each_category_and_writes_the_scripts_inputs(
    tmp_path,
):
    work = tmp_path / "work"

    result = benchmark.run_benchmark(
        _source(tmp_path),
        _benchmark_key(tmp_path),
        work,
        collection="Synthetic test collection 1",
    )
    document = result.document

    assert document["format"] == benchmark.FORMAT
    assert document["versions"]["preset"] == "basic"
    assert document["versions"]["collection"] == "Synthetic test collection 1"
    assert document["coverage"]["instances"] == {
        "released": 2,
        "withheld": 0,
        "outside-coverage": 1,
        "not-in-input": 1,
    }
    assert document["coverage"]["by_modality"]["MR"]["outside-coverage"] == 1
    assert _category(document, "tcia", "TEST-RETAIN-DESCRIPTION")["deliberate"] == 1
    assert _category(document, "hipaa", "HIPAA-C") == {
        "family": "hipaa",
        "code": "HIPAA-C",
        "passed": 1,
        "failed": 0,
        "deliberate": 0,
        "not_evaluated": 0,
        "withheld": 0,
        "outside_coverage": 0,
        "not_in_input": 1,
    }
    assert _category(document, "hipaa", "TEST-MODALITY")["failed"] == 1
    assert _category(document, "hipaa", "HIPAA-R")["passed"] == 1
    assert _category(document, "hipaa", "HIPAA-A")["not_evaluated"] == 1
    assert _category(document, "dicom", "DICOM-P15-BASIC-U")["passed"] == 1
    assert _category(document, "dicom", "DICOM-P15-BASIC-C")["passed"] == 1
    assert _category(document, "tcia", "TCIA-P15-PIX-K")["passed"] == 1
    iod = _category(document, "dicom", "TEST-IOD")
    assert (iod["passed"], iod["outside_coverage"]) == (1, 1)
    assert document["deliberate_differences"] == [
        {
            "category": "tcia TEST-RETAIN-DESCRIPTION",
            "action": "text_retained",
            "attribute": "(0008,1030)",
            "policy_action": "X",
            "checks": 1,
        }
    ]
    assert document["findings"] == [
        {
            "category": "hipaa TEST-MODALITY",
            "action": "text_removed",
            "attribute": "(0008,0060)",
            "checks": 1,
        }
    ]
    assert json.loads((work / benchmark.RESULTS_JSON).read_text()) == document
    assert (work / benchmark.RESULTS_MARKDOWN).read_text() == result.markdown()
    assert (work / "release" / "release-report.json").is_file()
    assert (work / "qc").is_dir()


def test_the_mapping_files_name_what_the_run_wrote(tmp_path):
    work = tmp_path / "work"
    benchmark.run_benchmark(_source(tmp_path), _benchmark_key(tmp_path), work)

    with open(work / "validation-script" / "uid_mapping.csv", newline="") as file:
        uids = list(csv.reader(file))
    with open(work / "validation-script" / "patid_mapping.csv", newline="") as file:
        patients = list(csv.reader(file))

    assert uids[0] == patients[0] == ["id_old", "id_new"]
    mapped = dict(uids[1:])
    (patient,) = [new for old, new in patients[1:] if old == synthetic.PATIENT_ID]
    released = sorted(
        path.relative_to(work / "release").as_posix()
        for path in (work / "release").rglob("*.dcm")
    )
    assert len(released) == 6
    for name in released:
        assert name.startswith(f"{patient}/{mapped[synthetic.STUDY]}/")
    assert f"{mapped[synthetic.CT_SERIES]}/{mapped[synthetic.CT_SLICES[0]]}.dcm" in (
        "/".join(name.split("/")[2:]) for name in released
    )
    # The sequestered MR instance is not mapped.
    assert MR_INSTANCE not in mapped
    assert OTHER_PATIENT not in dict(patients[1:])


@pytest.mark.skipif(os.name != "posix", reason="owner-only modes are POSIX")
def test_the_mapping_files_are_for_their_owner_alone(tmp_path):
    work = tmp_path / "work"
    benchmark.run_benchmark(_source(tmp_path), _benchmark_key(tmp_path), work)

    for directory in (work, work / "validation-script"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for name in ("uid_mapping.csv", "patid_mapping.csv"):
        mode = (work / "validation-script" / name).stat().st_mode
        assert stat.S_IMODE(mode) == 0o600


@pytest.mark.parametrize(
    "modality, expected",
    [("CT", "CT"), (" RTDOSE ", "RTDOSE"), (None, "other"), ("Not a code", "other")],
)
def test_a_modality_is_reported_only_as_a_code_string(modality, expected):
    assert benchmark._modality(modality) == expected  # pylint: disable = protected-access


def test_the_results_hold_no_value_from_the_test_data_set(tmp_path):
    work = tmp_path / "work"
    benchmark.run_benchmark(_source(tmp_path), _benchmark_key(tmp_path), work)

    for name in (benchmark.RESULTS_JSON, benchmark.RESULTS_MARKDOWN):
        text = (work / name).read_text()
        for value in (
            synthetic.PATIENT_ID,
            OTHER_PATIENT,
            STUDY_DESCRIPTION,
            STUDY_DATE,
            synthetic.STUDY,
            synthetic.CT_SLICES[0],
            MR_INSTANCE,
            str(tmp_path),
        ):
            assert value not in text


def test_the_markdown_gives_each_section(tmp_path):
    markdown = benchmark.run_benchmark(
        _source(tmp_path), _benchmark_key(tmp_path), tmp_path / "work"
    ).markdown()

    for heading in (
        "# MIDI benchmark results",
        "## Versions",
        "## Supported coverage",
        "## Results by answer-key category",
        "## Deliberate differences",
        "## Findings",
    ):
        assert f"\n{heading}\n" in f"\n{markdown}"
    assert "| tcia TEST-RETAIN-DESCRIPTION | text_retained | (0008,1030) | X | 1 |" in (
        markdown
    )


def test_an_existing_work_directory_is_refused(tmp_path):
    (tmp_path / "work").mkdir()

    with pytest.raises(benchmark.BenchmarkError, match="must not exist"):
        benchmark.run_benchmark(
            _source(tmp_path), _benchmark_key(tmp_path), tmp_path / "work"
        )


def test_a_preset_with_clean_descriptors_is_refused_for_now(tmp_path):
    with pytest.raises(benchmark.BenchmarkError, match="reviewed-names list"):
        benchmark.run_benchmark(
            _source(tmp_path),
            _benchmark_key(tmp_path),
            tmp_path / "work",
            preset="basic-clean-descriptors",
        )
    assert not (tmp_path / "work").exists()


def _script_results(path, rows):
    fields = [
        "hipaa_z",
        "hipaa_m",
        "dicom_p15",
        "dicom_iod",
        "dicom_safe",
        "tcia_ptkb",
        "tcia_p15",
        "tcia_rev",
    ]
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "CREATE TABLE validation_results "
            f"(action, check_passed, file_value, {', '.join(fields)})"
        )
        for action, passed, categories in rows:
            connection.execute(
                "INSERT INTO validation_results VALUES "
                f"({', '.join('?' * (len(fields) + 3))})",
                [
                    action,
                    passed,
                    "SYNTHETIC VALUE",
                    *(categories.get(f) for f in fields),
                ],
            )
    connection.close()
    return path


def test_the_scripts_results_are_counted_by_category(tmp_path):
    path = _script_results(
        tmp_path / "validation_results.db",
        [
            ("<date_shifted>", 1, {}),
            ("<date_shifted>", 0, {}),
            ("<text_removed>", 1.0, {"hipaa_z": "TEST-Z"}),
            ("<pixels_hidden>", None, {}),
            ("<text_retained>", 1, {}),
        ],
    )

    summary = midi_script_results.summarise_script_results(path)

    assert summary["results_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert summary["categories"] == [
        {"family": "hipaa", "code": "HIPAA-A", "passed": 0, "failed": 0, "blank": 1},
        {"family": "hipaa", "code": "HIPAA-C", "passed": 1, "failed": 1, "blank": 0},
        {"family": "hipaa", "code": "TEST-Z", "passed": 1, "failed": 0, "blank": 0},
        {"family": None, "code": None, "passed": 1, "failed": 0, "blank": 0},
    ]
    assert "SYNTHETIC VALUE" not in json.dumps(summary)


def test_the_scripts_results_need_only_the_category_columns_it_made(tmp_path):
    path = tmp_path / "validation_results.db"
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "CREATE TABLE validation_results (action, check_passed, hipaa_z)"
        )
        connection.execute(
            "INSERT INTO validation_results VALUES (?, ?, ?)",
            ["<text_removed>", 0, "TEST-Z"],
        )
    connection.close()

    assert midi_script_results.summarise_script_results(path)["categories"] == [
        {"family": "hipaa", "code": "TEST-Z", "passed": 0, "failed": 1, "blank": 0}
    ]


def test_results_without_the_scripts_table_are_refused(tmp_path):
    path = tmp_path / "validation_results.db"
    connection = sqlite3.connect(path)
    with connection:
        connection.execute("CREATE TABLE other (action)")
    connection.close()

    with pytest.raises(
        midi_script_results.ScriptResultsError, match="validation_results"
    ):
        midi_script_results.summarise_script_results(path)


def test_the_commands_are_not_on_the_pymedphys_command_line(capsys):
    # Nothing de-identification related joins the public command line before
    # the first supported release.
    with pytest.raises(SystemExit):
        define_parser().parse_args(["dev", "--help"])
    assert "benchmark" not in capsys.readouterr().out
    for command in ("deid-benchmark", "deid-benchmark-script-results"):
        with pytest.raises(SystemExit):
            define_parser().parse_args(["dev", command])


def _command(*arguments):
    assert midi_benchmark_command.main(arguments) == 0


def test_the_command_runs_a_benchmark(tmp_path, capsys):
    work = tmp_path / "work"

    _command(
        "run",
        "--source",
        str(_source(tmp_path)),
        "--answer-key",
        str(_benchmark_key(tmp_path)),
        "--work",
        str(work),
        "--collection",
        "Synthetic test collection 1",
    )

    document = json.loads((work / benchmark.RESULTS_JSON).read_text())
    assert document["versions"]["collection"] == "Synthetic test collection 1"
    assert capsys.readouterr().out == (work / benchmark.RESULTS_MARKDOWN).read_text()


def test_the_command_summarises_the_scripts_results(tmp_path, capsys):
    path = _script_results(
        tmp_path / "validation_results.db", [("<uid_changed>", 1, {})]
    )

    _command("script-results", str(path))

    assert json.loads(capsys.readouterr().out)["categories"] == [
        {"family": "hipaa", "code": "HIPAA-R", "passed": 1, "failed": 0, "blank": 0}
    ]


def test_the_command_reports_a_refusal_without_a_traceback(tmp_path):
    (tmp_path / "work").mkdir()

    with pytest.raises(SystemExit, match="must not exist"):
        _command(
            "run",
            "--source",
            str(tmp_path),
            "--answer-key",
            str(tmp_path / "key.db"),
            "--work",
            str(tmp_path / "work"),
        )
