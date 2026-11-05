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

"""A run told to sequester a study whose instances name several patients (D-026).

By default such a study stops the run before anything is written. With
:attr:`~pymedphys._dicom.deidentify.run.SeveralPatients.SEQUESTER`, every
instance of it is sequestered, its values are still searched for in the
files of every patient that it names, the release report records the
choice and how many studies it sequestered, and the QC pack lists each
study's instances by patient. Every file and value is synthetic.
"""

import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    api,
    command,
    output_names,
    pilot_command,
    policy,
    pseudonyms,
    qc_pack,
    release_report,
    release_report_markdown,
    run,
    uids,
)
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.reasons import RunReason
from pymedphys._dicom.deidentify.reference_graph import FindingKind, SeveralPatients
from pymedphys._dicom.deidentify.release_gate import ReasonCode

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
SEQUESTER = SeveralPatients.SEQUESTER
STOP = SeveralPatients.STOP
SEVERAL = FindingKind.STUDY_WITH_SEVERAL_PATIENTS
SEQUESTERED = run.Status.SEQUESTERED
RELEASED = run.Status.RELEASED
DUPLICATE = run.Status.DUPLICATE
# The study of synthetic.collection(), at positions 0 to 5.
STUDY = (*synthetic.CT_SLICES, synthetic.STRUCTURE_SET, synthetic.PLAN, synthetic.DOSE)
OTHER_PATIENT_ID = "SYNTHETIC-9X4M"
THIRD_PATIENT_ID = "SYNTHETIC-3P3P"
OTHER_STUDY = "2.25.810"
THIRD_STUDY = "2.25.910"
# A name of the other patient, a component of which a kept value of the
# first patient's other study holds.
OTHER_NAME = "QUILLON^ZEBEDEE"
MODEL = "QUILLON SCANNER"
SENTINEL = "ZEBEDEE-QUILLON-7731"
REFERENCES = ("references", SEVERAL.value)


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    """On Windows, a directory whose path leaves room for a run's output names."""
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d")).resolve()
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _write(directory, datasets):
    """Write each data set to ``directory``, named so that they sort in order."""
    directory.mkdir(parents=True, exist_ok=True)
    for index, dataset in enumerate(datasets):
        data = dataset if isinstance(dataset, bytes) else synthetic.written(dataset)
        (directory / f"{index:03d}.dcm").write_bytes(data)
    return directory


def _output_path(record):
    # An instance without a Patient ID needs a curated identity, which this
    # stand-in gives every one alike.
    patient = record.patient or pseudonyms.SubjectIdentity.from_patient_id("x")
    return output_names.instance_path(
        patient_id=pseudonyms.patient_pseudonym(KEY, patient).patient_id,
        study_instance_uid=uids.replacement_uid(KEY, record.study),
        series_instance_uid=uids.replacement_uid(KEY, record.series),
        sop_instance_uid=uids.replacement_uid(KEY, record.sop_instance),
    )


class Transform:
    """A stand-in for the walker and writer, whose evidence is the SOP Instance UID."""

    def __init__(self):
        self.calls = []
        self.prepared = None

    def prepare(self, records, _read):
        self.prepared = sorted(records)

    def __call__(self, data, record):
        self.calls.append(record.sop_instance)
        return run.Transformed(
            _output_path(record),
            b"OUTPUT " + record.sop_instance.encode(),
            record.sop_instance,
        )


class Gate:
    """A stand-in for the release condition, which releases everything."""

    def __init__(self):
        self.subjects = {}

    def __call__(self, written, evidence, subject):
        self.subjects[evidence] = subject
        return run.Release()


def _stray(sop_instance="2.25.7777", patient_id=OTHER_PATIENT_ID):
    """Return a CT slice of the collection's study that names another patient."""
    stray = synthetic.ct_slice(2)
    stray.SOPInstanceUID = sop_instance
    if patient_id is None:
        del stray.PatientID
    else:
        stray.PatientID = patient_id
        stray.PatientName = OTHER_NAME
    return stray


def _own_study(patient_id=synthetic.PATIENT_ID, study=OTHER_STUDY, uid="2.25.801"):
    """Return an MR image of another study, of ``patient_id``."""
    image = synthetic.instance(synthetic.MR_IMAGE_STORAGE, uid, uid + "0")
    image.StudyInstanceUID = study
    if patient_id is None:
        del image.PatientID
    else:
        image.PatientID = patient_id
    return image


def _run(tmp_path, transform=None, gate=None, several_patients=SEQUESTER, **kwargs):
    return run.run(
        run.discover(tmp_path / "source"),
        tmp_path / "release",
        transform or Transform(),
        gate or Gate(),
        qc_destination=tmp_path / "qc",
        several_patients=several_patients,
        **kwargs,
    )


def _pack(tmp_path):
    return json.loads((tmp_path / "qc" / "qc-pack.json").read_text(encoding="utf-8"))


def _listing(directory):
    return sorted(path.name for path in directory.iterdir())


# The run


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
def test_the_default_still_stops_the_run_before_anything_is_created(tmp_path):
    _write(tmp_path / "source", [*synthetic.collection(), _stray()])
    transform = Transform()

    with pytest.raises(run.RunStopped) as raised:
        _run(tmp_path, transform, several_patients=STOP)
    with pytest.raises(run.RunStopped):
        run.run(
            run.discover(tmp_path / "source"),
            tmp_path / "release",
            transform,
            Gate(),
            qc_destination=tmp_path / "qc",
        )

    (finding,) = raised.value.findings
    assert finding.kind is SEVERAL
    assert not transform.calls
    assert _listing(tmp_path) == ["source"]


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
@pytest.mark.parametrize("choice", ["sequester", None, True, 1])
def test_a_choice_that_is_not_a_several_patients_is_refused_before_anything(
    tmp_path, choice
):
    _write(tmp_path / "source", synthetic.collection())

    with pytest.raises(TypeError, match="SeveralPatients"):
        _run(tmp_path, several_patients=choice)

    assert _listing(tmp_path) == ["source"]


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
def test_every_instance_of_the_study_is_sequestered_and_the_rest_released(tmp_path):
    _write(
        tmp_path / "source",
        [
            *synthetic.collection(),
            _stray(),
            _own_study(),
            _own_study(OTHER_PATIENT_ID, THIRD_STUDY, "2.25.901"),
        ],
    )

    result = _run(tmp_path)

    statuses = [(outcome.status, outcome.reasons) for outcome in result.outcomes]
    assert statuses[:7] == [(SEQUESTERED, (SEVERAL,))] * 7
    assert statuses[7:] == [(RELEASED, ())] * 2
    assert all(outcome.label for outcome in result.outcomes[:7])
    (finding,) = [f for f in result.findings if f.kind is SEVERAL]
    assert finding.instances == ((0, 1, 2, 3, 4, 5), (6,))
    released = [p for p in (tmp_path / "release").rglob("*.dcm") if p.is_file()]
    assert len(released) == 2
    assert command.exit_status(result) == command.EXIT_WITHHELD


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
def test_each_instance_of_the_study_is_transformed_but_not_prepared(tmp_path):
    _write(tmp_path / "source", [*synthetic.collection(), _stray(), _own_study()])
    transform = Transform()

    _run(tmp_path, transform)

    # Transformed for its evidence, but kept out of what needs several
    # instances at once, such as a subject's synthetic birth date or a CT
    # series' face block.
    assert sorted(transform.calls) == sorted((*STUDY, "2.25.7777", "2.25.801"))
    assert transform.prepared == [7]


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-03")
@pytest.mark.pydicom
def test_the_studys_values_reach_the_gate_of_every_patient_it_names(tmp_path):
    first_own = _own_study()
    other_own = _own_study(OTHER_PATIENT_ID, THIRD_STUDY, "2.25.901")
    unrelated = _own_study(THIRD_PATIENT_ID, "2.25.920", "2.25.921")
    _write(
        tmp_path / "source",
        [*synthetic.collection(), _stray(), first_own, other_own, unrelated],
    )
    gate = Gate()

    _run(tmp_path, gate=gate)

    named = sorted((*STUDY, "2.25.7777"))
    # Its own first, then the sequestered study's, which names both patients.
    assert gate.subjects["2.25.801"][0] == "2.25.801"
    assert sorted(gate.subjects["2.25.801"]) == sorted(("2.25.801", *named))
    assert gate.subjects["2.25.901"][0] == "2.25.901"
    assert sorted(gate.subjects["2.25.901"]) == sorted(("2.25.901", *named))
    # A patient that the study does not name is searched for its own alone.
    assert gate.subjects["2.25.921"] == ("2.25.921",)


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-03")
@pytest.mark.pydicom
def test_instances_without_a_patient_id_are_a_patient_that_the_study_names(tmp_path):
    without = _own_study(None, THIRD_STUDY, "2.25.901")
    _write(
        tmp_path / "source",
        [*synthetic.collection(), _stray(patient_id=None), _own_study(), without],
    )
    gate = Gate()

    result = _run(tmp_path, gate=gate)

    assert [o.status for o in result.outcomes[:7]] == [SEQUESTERED] * 7
    named = sorted((*STUDY, "2.25.7777"))
    assert sorted(gate.subjects["2.25.801"]) == sorted(("2.25.801", *named))
    assert sorted(gate.subjects["2.25.901"]) == sorted(("2.25.901", *named))


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-03")
@pytest.mark.pydicom
def test_an_instance_of_the_study_that_changes_withholds_every_named_patient(
    tmp_path, monkeypatch
):
    _write(
        tmp_path / "source",
        [
            *synthetic.collection(),
            _stray(),
            _own_study(),
            _own_study(OTHER_PATIENT_ID, THIRD_STUDY, "2.25.901"),
            _own_study(THIRD_PATIENT_ID, "2.25.920", "2.25.921"),
        ],
    )
    discovery = run.discover(tmp_path / "source")
    stray = discovery.paths[6]
    first_pass = run._first_pass  # pylint: disable = protected-access

    def first_pass_then_change(found, *choices):
        result = first_pass(found, *choices)
        stray.write_bytes(stray.read_bytes() + b"\x00\x00")
        return result

    monkeypatch.setattr(run, "_first_pass", first_pass_then_change)
    gate = Gate()

    run.run(
        discovery,
        tmp_path / "release",
        Transform(),
        gate,
        qc_destination=tmp_path / "qc",
        several_patients=SEQUESTER,
    )

    # Its values were not collected, so the gates of both patients it names
    # see that, and withhold their files; a third patient's do not.
    assert run.NO_EVIDENCE in gate.subjects["2.25.801"]
    assert run.NO_EVIDENCE in gate.subjects["2.25.901"]
    assert run.NO_EVIDENCE not in gate.subjects["2.25.921"]


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
def test_identical_copies_in_the_study_are_all_sequestered(tmp_path):
    datasets = synthetic.collection()
    _write(tmp_path / "source", [*datasets, _stray(), datasets[4]])
    transform = Transform()

    result = _run(tmp_path, transform)

    assert [o.status for o in result.outcomes] == [SEQUESTERED] * 8
    assert result.outcomes[7].duplicate_of == 4
    assert transform.calls.count(synthetic.PLAN) == 1
    (study,) = _pack(tmp_path)["several_patient_studies"]
    assert study == {"patients": [[0, 1, 2, 3, 4, 5, 7], [6]]}


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
def test_a_series_also_in_another_study_keeps_both_reasons(tmp_path):
    # A slice of the study's CT series that names another study, which
    # itself names one patient.
    elsewhere = synthetic.ct_slice(1)
    elsewhere.SOPInstanceUID = "2.25.8888"
    elsewhere.StudyInstanceUID = OTHER_STUDY
    _write(tmp_path / "source", [*synthetic.collection(), _stray(), elsewhere])

    result = _run(tmp_path)

    in_both = FindingKind.SERIES_IN_SEVERAL_STUDIES
    assert set(result.outcomes[0].reasons) == {SEVERAL, in_both}
    assert result.outcomes[3].reasons == (SEVERAL,)
    assert result.outcomes[7].reasons == (in_both,)


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-17")
@pytest.mark.pydicom
def test_the_qc_pack_lists_each_study_by_patient_in_order(tmp_path):
    second = [
        _own_study(THIRD_PATIENT_ID, THIRD_STUDY, "2.25.901"),
        _own_study("SYNTHETIC-4Q4Q", THIRD_STUDY, "2.25.902"),
        _own_study(THIRD_PATIENT_ID, THIRD_STUDY, "2.25.903"),
    ]
    _write(tmp_path / "source", [*second, *synthetic.collection(), _stray()])

    result = _run(tmp_path)

    pack = _pack(tmp_path)
    assert pack["format"] == qc_pack.FORMAT
    assert pack["several_patient_studies"] == [
        {"patients": [[0, 2], [1]]},
        {"patients": [[3, 4, 5, 6, 7, 8], [9]]},
    ]
    entries = pack["instances"]
    assert all(entries[p]["disposition"] == "sequestered" for p in range(10))
    assert all(
        entries[p]["reasons"] == ["FindingKind.STUDY_WITH_SEVERAL_PATIENTS"]
        for p in range(10)
    )
    assert [o.status for o in result.outcomes] == [SEQUESTERED] * 10


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-18")
@pytest.mark.pydicom
def test_the_report_counts_the_studies_and_gives_their_instances_reasons(tmp_path):
    second = [
        _own_study(THIRD_PATIENT_ID, THIRD_STUDY, "2.25.901"),
        _own_study("SYNTHETIC-4Q4Q", THIRD_STUDY, "2.25.902"),
    ]
    _write(
        tmp_path / "source",
        [*synthetic.collection(), _stray(), *second, _own_study()],
    )
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)

    _run(
        tmp_path,
        transform,
        ReleaseGate(),
        reporter=transform.reporter,
        written_check=transform.written_check,
    )

    report = json.loads(
        (tmp_path / "release" / "release-report.json").read_text(encoding="utf-8")
    )
    assert report["format"] == release_report.FORMAT
    assert report["studies_with_several_patients"] == {
        "handling": "sequester",
        "sequestered": 2,
    }
    reasons = [
        [(reason["stage"], reason["code"]) for reason in entry["reasons"]]
        for entry in report["sequestered"]
    ]
    assert reasons.count([REFERENCES]) == 9
    references = report["structural_checks"][0]
    assert references == {"check": "references", "sequestered": 9, "reported": 0}
    assert len(report["released"]) == 1
    markdown = (tmp_path / "release" / "release-report.md").read_text(encoding="utf-8")
    assert "## Studies with several patients" in markdown
    assert "| Handling | `sequester` |" in markdown
    assert "| Studies sequestered | `2` |" in markdown


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.pydicom
def test_a_run_that_sequesters_none_reports_its_choice(tmp_path):
    _write(tmp_path / "source", [*synthetic.collection(), _own_study()])
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)

    result = _run(
        tmp_path,
        transform,
        ReleaseGate(),
        reporter=transform.reporter,
        written_check=transform.written_check,
    )

    assert all(o.status is RELEASED for o in result.outcomes)
    report = json.loads(
        (tmp_path / "release" / "release-report.json").read_text(encoding="utf-8")
    )
    assert report["studies_with_several_patients"] == {
        "handling": "sequester",
        "sequestered": 0,
    }
    assert _pack(tmp_path)["several_patient_studies"] == []


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-03", "MIDI-BP-11")
@pytest.mark.pydicom
def test_a_named_patients_file_that_holds_the_studys_value_is_withheld(tmp_path):
    # The stray slice names the other patient, QUILLON^ZEBEDEE. The first
    # patient's other study keeps a model name that holds a component of
    # that name, as does a third patient's study, which the sequestered
    # study does not name.
    first_own = _own_study()
    first_own.ManufacturerModelName = MODEL
    unrelated = _own_study(THIRD_PATIENT_ID, "2.25.920", "2.25.921")
    unrelated.ManufacturerModelName = MODEL
    _write(
        tmp_path / "source",
        [*synthetic.collection(), _stray(), first_own, unrelated],
    )
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)

    result = _run(
        tmp_path,
        transform,
        ReleaseGate(),
        reporter=transform.reporter,
        written_check=transform.written_check,
    )

    assert [o.status for o in result.outcomes[:7]] == [SEQUESTERED] * 7
    (reason,) = result.outcomes[7].reasons
    assert result.outcomes[7].status is SEQUESTERED
    assert reason.code is ReasonCode.RESIDUAL_PERSON_NAME
    assert reason.path.tag == "(0010,0010)"
    assert result.outcomes[8].status is RELEASED


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
def test_the_sequestered_study_names_no_source_path_or_value(tmp_path):
    source = tmp_path / "source"
    stray = _stray()
    stray.PatientName = SENTINEL.replace("-", "^", 1)
    _write(source, [*synthetic.collection(), stray])
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)

    result = _run(
        tmp_path,
        transform,
        ReleaseGate(),
        reporter=transform.reporter,
        written_check=transform.written_check,
    )

    published = "".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "release").iterdir()
        if path.is_file()
    )
    for text in (SENTINEL, OTHER_PATIENT_ID, synthetic.PATIENT_ID, str(source)):
        assert text not in published
        assert text not in repr(result.findings)


# The release report


def _report(**several):
    return release_report.release_report(
        policy.compose_policy("basic"),
        vocabulary=None,
        reviewed_roi_names=None,
        several_patients=release_report.SeveralPatientStudies(**several),
    )


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_the_section_gives_the_choice_and_the_count():
    document = release_report.report_document(
        _report(handling=SEQUESTER, sequestered=3)
    )

    assert list(document)[-1] == "studies_with_several_patients"
    assert document["studies_with_several_patients"] == {
        "handling": "sequester",
        "sequestered": 3,
    }


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.parametrize(
    "several",
    [
        {"handling": STOP, "sequestered": 1},
        {"handling": SEQUESTER, "sequestered": -1},
        {"handling": SEQUESTER, "sequestered": True},
        {"handling": SEQUESTER, "sequestered": 1.0},
        {"handling": "sequester", "sequestered": 1},
        {"handling": SENTINEL, "sequestered": 0},
    ],
    ids=["stop-with-one", "negative", "bool", "float", "text", "sentinel"],
)
def test_a_section_of_another_form_is_refused_naming_no_value(several):
    with pytest.raises(release_report.ReleaseReportError) as raised:
        release_report.to_json(_report(**several))

    assert "studies_with_several_patients" in str(raised.value)
    assert SENTINEL not in str(raised.value)


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_a_section_that_is_not_the_runs_choice_is_refused():
    report = _report()
    broken = release_report.ReleaseReport(
        report.policy, report.method, report.runtime, several_patients=SENTINEL
    )

    with pytest.raises(release_report.ReleaseReportError) as raised:
        release_report.to_json(broken)

    assert SENTINEL not in str(raised.value)


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_a_studys_reason_is_a_reference_reason():
    reason = release_report.sequestration_reason(SEVERAL)

    assert (reason.stage, reason.code) == REFERENCES
    assert release_report.sequestering_checks([reason]) == frozenset({"references"})


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.parametrize("handling", ["stop", "sequester"])
def test_the_markdown_gives_the_choice(handling):
    count = 0 if handling == "stop" else 2
    text = release_report.to_json(
        _report(handling=SeveralPatients(handling), sequestered=count)
    )

    markdown = release_report_markdown.to_markdown(text)

    section = markdown.split("## Studies with several patients", 1)[1]
    assert f"| Handling | `{handling}` |" in section
    assert f"| Studies sequestered | `{count}` |" in section


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.parametrize(
    "section",
    [
        {"handling": "stop", "sequestered": 1},
        {"handling": SENTINEL, "sequestered": 0},
        {"handling": "sequester", "sequestered": -1},
        {"handling": "sequester"},
        None,
    ],
    ids=["stop-with-one", "sentinel", "negative", "missing", "null"],
)
def test_the_markdown_refuses_a_section_of_another_form(section):
    document = json.loads(release_report.to_json(_report()))
    document["studies_with_several_patients"] = section

    with pytest.raises(release_report_markdown.ReleaseReportMarkdownError) as raised:
        release_report_markdown.to_markdown(json.dumps(document))

    assert SENTINEL not in str(raised.value)


# The QC pack


REFERENCE = "A-" + "0" * 32


def _instances(*sequestered, count=5):
    labels = iter(f"S-{n:04d}" for n in range(1, count + 1))
    return tuple(
        qc_pack.InstanceEntry(
            position,
            f"in/{position}.dcm",
            qc_pack.Disposition.SEQUESTERED,
            label=next(labels),
            reasons=("FindingKind.STUDY_WITH_SEVERAL_PATIENTS",),
        )
        if position in sequestered
        else qc_pack.InstanceEntry(
            position, f"in/{position}.dcm", qc_pack.Disposition.REFUSED, reasons=("x",)
        )
        for position in range(count)
    )


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_the_pack_writes_each_study_by_patient():
    pack = qc_pack.QcPack(
        REFERENCE,
        _instances(0, 1, 2, 3, 4),
        several_patient_studies=(
            qc_pack.SeveralPatientStudyEntry(((0, 2), (1,))),
            qc_pack.SeveralPatientStudyEntry(((3,), (4,))),
        ),
    )

    document = json.loads(qc_pack.to_json(pack))

    assert document["several_patient_studies"] == [
        {"patients": [[0, 2], [1]]},
        {"patients": [[3], [4]]},
    ]


@pytest.mark.deid_requirement("MIDI-BP-17")
@pytest.mark.parametrize(
    "patients",
    [
        ((0, 1),),
        (),
        ((0,), ()),
        ((1, 0), (2,)),
        ((0, 1), (1,)),
        ((1,), (0,)),
        ((0,), (-1,)),
        ((0,), (True,)),
        [(0,), (1,)],
        ((0,), [1]),
    ],
    ids=[
        "one-patient",
        "none",
        "empty-group",
        "unsorted",
        "twice",
        "out-of-order",
        "negative",
        "bool",
        "list",
        "list-group",
    ],
)
def test_a_study_entry_of_another_form_is_refused(patients):
    with pytest.raises(qc_pack.QcPackError):
        qc_pack.SeveralPatientStudyEntry(patients)


@pytest.mark.deid_requirement("MIDI-BP-17")
@pytest.mark.parametrize(
    "sequestered, studies, problem",
    [
        ((0, 1), (((0,), (2,)),), "not sequestered"),
        ((0, 1, 2), (((0,), (7,)),), "not sequestered"),
        ((0, 1, 2, 3), (((2,), (3,)), ((0,), (1,))), "in order"),
        ((0, 1, 2), (((0,), (1,)), ((1,), (2,))), "two studies"),
    ],
    ids=["unsequestered", "no-instance", "out-of-order", "overlapping"],
)
def test_a_pack_whose_studies_do_not_fit_its_instances_is_refused(
    sequestered, studies, problem
):
    with pytest.raises(qc_pack.QcPackError, match=problem):
        qc_pack.QcPack(
            REFERENCE,
            _instances(*sequestered),
            several_patient_studies=tuple(
                qc_pack.SeveralPatientStudyEntry(groups) for groups in studies
            ),
        )


# The command line, the library API, and the pilot


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
def test_the_command_sequesters_only_when_asked(tmp_path):
    _write(tmp_path / "source", [*synthetic.collection(), _stray(), _own_study()])
    arguments = [str(tmp_path / "source"), str(tmp_path / "release")]
    stdout, stderr = io.StringIO(), io.StringIO()

    stopped = command.main(
        [*arguments, "--qc-pack", str(tmp_path / "qc")],
        transform=Transform(),
        gate=Gate(),
        stdout=stdout,
        stderr=stderr,
    )
    sequestered = command.main(
        [
            *arguments,
            "--qc-pack",
            str(tmp_path / "qc"),
            "--sequester-studies-with-several-patients",
        ],
        transform=Transform(),
        gate=Gate(),
        stdout=stdout,
        stderr=stderr,
    )

    assert stopped == command.EXIT_NOT_RUN
    assert "several patients" in stderr.getvalue()
    assert sequestered == command.EXIT_WITHHELD
    summary = stdout.getvalue()
    assert "  sequestered: 7" in summary
    assert "  released: 1" in summary
    assert "  FindingKind.STUDY_WITH_SEVERAL_PATIENTS: 7" in summary
    assert "first-pass findings:" in summary


def test_the_commands_help_names_the_opt_in_and_its_caveat():
    parser = command.build_parser()
    text = parser.format_help()

    assert "--sequester-studies-with-several-patients" in text
    assert not parser.parse_args(
        ["s", "r", "--qc-pack", "q"]
    ).sequester_studies_with_several_patients
    assert (
        command.several_patients_of(
            parser.parse_args(
                [
                    "s",
                    "r",
                    "--qc-pack",
                    "q",
                    "--sequester-studies-with-several-patients",
                ]
            )
        )
        is SEQUESTER
    )
    assert (
        command.several_patients_of(parser.parse_args(["s", "r", "--qc-pack", "q"]))
        is STOP
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.parametrize("given", ["yes", 1, None])
def test_the_api_refuses_a_choice_that_is_not_a_bool(tmp_path, given):
    with pytest.raises(TypeError, match="sequester_studies_with_several_patients"):
        api.deidentify(
            tmp_path / "source",
            tmp_path / "release",
            qc_pack=tmp_path / "qc",
            sequester_studies_with_several_patients=given,
        )

    assert not any(tmp_path.iterdir())


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
@pytest.mark.parametrize("sequester", [False, True])
def test_the_api_passes_its_choice_to_the_run(tmp_path, monkeypatch, sequester):
    _write(tmp_path / "source", synthetic.collection())
    given = {}

    def recorded(*_args, **kwargs):
        given.update(kwargs)
        raise run.RunError("stopped here")

    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    monkeypatch.setattr(run, "run", recorded)

    with pytest.raises(run.RunError, match="stopped here"):
        api.deidentify(
            tmp_path / "source",
            tmp_path / "release",
            qc_pack=tmp_path / "qc",
            sequester_studies_with_several_patients=sequester,
        )

    assert given["several_patients"] is (SEQUESTER if sequester else STOP)


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.pydicom
def test_the_pilot_counts_the_study_and_measures_the_rest(tmp_path):
    _write(tmp_path / "source", [*synthetic.collection(), _stray(), _own_study()])
    stdout, stderr = io.StringIO(), io.StringIO()

    stopped = pilot_command.main(
        [str(tmp_path / "source"), "--preset", "basic"], stdout=stdout, stderr=stderr
    )
    status = pilot_command.main(
        [
            str(tmp_path / "source"),
            "--preset",
            "basic",
            "--sequester-studies-with-several-patients",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert stopped == command.EXIT_NOT_RUN
    assert status == command.EXIT_WITHHELD
    summary = stdout.getvalue()
    assert "  FindingKind.STUDY_WITH_SEVERAL_PATIENTS: 1" in summary
    assert f"  stage=references code={SEVERAL.value}: 7" in summary
    assert RunReason.INVALID_REASON.name not in summary
