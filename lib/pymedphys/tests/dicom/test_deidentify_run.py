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

"""Running de-identification over a directory, through a staging area."""

import dataclasses
import enum
import io
import os
import stat
from pathlib import PurePosixPath

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import output_names, pseudonyms, run, uids
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.reference_graph import FindingKind
from pymedphys._dicom.deidentify.references import InstanceRecord, UnreadableSequence

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
# Positions in synthetic.collection(), whose files are named so that they
# sort in that order.
STRUCTURE_SET, PLAN, DOSE = 3, 4, 5
STUDY = (*synthetic.CT_SLICES, synthetic.STRUCTURE_SET, synthetic.PLAN, synthetic.DOSE)
SENTINEL = "ZEBEDEE-QUILLON-7731"
OTHER_PATIENT_ID = "SYNTHETIC-9X4M"
POSIX = os.name == "posix"

RELEASED = (run.Status.RELEASED, ())
REFUSED = run.Status.REFUSED
SEQUESTERED = run.Status.SEQUESTERED
HELD = run.Status.HELD_FOR_REVIEW
DUPLICATE = run.Status.DUPLICATE
Reason = run.RunReason


class GateReason(enum.Enum):
    """A gate's reason, as the release condition gives its own."""

    RESIDUAL_PERSON_NAME = "residual-person-name"
    TEXT_FINDING = "text-finding"


@dataclasses.dataclass(frozen=True)
class Finding:
    """A value-free finding with a place, as a gate's reasons can be."""

    code: str
    path: ElementPath


def _write(directory, datasets, names=None):
    """Write each data set to ``directory`` as a file, in sorted name order."""
    directory.mkdir(parents=True, exist_ok=True)
    names = names or [f"{index:03d}.dcm" for index in range(len(datasets))]
    for name, dataset in zip(names, datasets):
        data = dataset if isinstance(dataset, bytes) else synthetic.written(dataset)
        (directory / name).write_bytes(data)
    return directory


def _output_path(record):
    return output_names.instance_path(
        patient_id=pseudonyms.patient_pseudonym(KEY, record.patient).patient_id,
        study_instance_uid=uids.replacement_uid(KEY, record.study),
        series_instance_uid=uids.replacement_uid(KEY, record.series),
        sop_instance_uid=uids.replacement_uid(KEY, record.sop_instance),
    )


def _output(uid):
    return b"OUTPUT " + uid.encode()


class Transform:
    """A stand-in for the walker and writer.

    Each output holds its source's SOP Instance UID, which is also its
    evidence.
    """

    def __init__(self, sequester=()):
        self.calls = []
        self.sequester = sequester

    def __call__(self, data, record):
        self.calls.append(record.sop_instance)
        if record.sop_instance in self.sequester:
            return run.Sequestered((GateReason.TEXT_FINDING,), record.sop_instance)
        return run.Transformed(
            _output_path(record), _output(record.sop_instance), record.sop_instance
        )


class Gate:
    """A stand-in for the release condition: releases unless told otherwise."""

    def __init__(self, verdicts=None):
        self.calls = []
        self.verdicts = verdicts or {}

    def __call__(self, written, evidence, subject):
        self.calls.append((written, evidence, subject))
        return self.verdicts.get(written, run.Release())


def _run(tmp_path, transform=None, gate=None, source=None):
    source = source or tmp_path / "source"
    discovery = run.discover(source)
    result = run.run(
        discovery, tmp_path / "release", transform or Transform(), gate or Gate()
    )
    return discovery, result


def _statuses(result):
    return [(outcome.status, outcome.reasons) for outcome in result.outcomes]


def _released_files(release):
    return sorted(
        path.relative_to(release).as_posix()
        for path in release.rglob("*")
        if path.is_file()
    )


def _listing(directory):
    return sorted(path.name for path in directory.iterdir())


@pytest.mark.pydicom
def test_a_consistent_collection_is_released_at_its_output_names(tmp_path):
    _write(tmp_path / "source", synthetic.collection())

    discovery, result = _run(tmp_path)

    release = tmp_path / "release"
    assert result.release == release
    assert result.staging_removed
    assert _statuses(result) == [RELEASED] * 6
    assert not result.findings
    for outcome, path in zip(result.outcomes, discovery.paths):
        record = InstanceRecord.from_file(path.read_bytes())
        assert outcome.output == _output_path(record)
        written = release.joinpath(*outcome.output.parts).read_bytes()
        assert written == _output(record.sop_instance)
    assert len(_released_files(release)) == 6
    # Nothing is left beside the release.
    assert _listing(tmp_path) == ["release", "source"]


@pytest.mark.pydicom
def test_discovery_orders_entries_by_relative_path(tmp_path):
    source = tmp_path / "source"
    datasets = synthetic.collection()
    _write(source / "b", datasets[:2], ["2.dcm", "10.dcm"])
    _write(source / "a" / "z", datasets[2:3], ["x.dcm"])
    _write(source, datasets[3:4], ["a.dcm"])

    discovery = run.discover(source)

    assert [path.relative_to(source).as_posix() for path in discovery.paths] == [
        "a/z/x.dcm",
        "a.dcm",
        "b/10.dcm",
        "b/2.dcm",
    ]
    assert discovery.refusals == (None,) * 4
    assert discovery == run.discover(source)


@pytest.mark.pydicom
@pytest.mark.skipif(not POSIX, reason="symbolic links and named pipes need POSIX")
def test_links_and_special_files_are_refused_without_being_followed(tmp_path):
    source = _write(tmp_path / "source", synthetic.collection()[:1], ["0.dcm"])
    elsewhere = _write(tmp_path / "elsewhere", synthetic.collection()[1:2], ["1.dcm"])
    (source / "1-file-link.dcm").symlink_to(elsewhere / "1.dcm")
    (source / "2-directory-link").symlink_to(elsewhere, target_is_directory=True)
    os.mkfifo(source / "3-pipe")

    discovery, result = _run(tmp_path)

    assert discovery.refusals == (
        None,
        Reason.SYMBOLIC_LINK,
        Reason.SYMBOLIC_LINK,
        Reason.NOT_A_REGULAR_FILE,
    )
    assert _statuses(result) == [
        RELEASED,
        (REFUSED, (Reason.SYMBOLIC_LINK,)),
        (REFUSED, (Reason.SYMBOLIC_LINK,)),
        (REFUSED, (Reason.NOT_A_REGULAR_FILE,)),
    ]
    assert len(_released_files(tmp_path / "release")) == 1


@pytest.mark.pydicom
@pytest.mark.skipif(not POSIX, reason="symbolic links and named pipes need POSIX")
@pytest.mark.parametrize("replacement", ["link", "pipe", "other-file"])
def test_a_file_replaced_after_discovery_is_not_read(tmp_path, replacement):
    source = _write(tmp_path / "source", synthetic.collection()[:2])
    elsewhere = _write(tmp_path / "elsewhere", synthetic.collection()[1:2], ["1.dcm"])
    discovery = run.discover(source)
    target = discovery.paths[1]
    # Made before the original is removed, so it cannot reuse its inode.
    replaced = tmp_path / "replacement"
    if replacement == "link":
        replaced.symlink_to(elsewhere / "1.dcm")
    elif replacement == "pipe":
        os.mkfifo(replaced)
    else:
        replaced.write_bytes(target.read_bytes())
    os.replace(replaced, target)

    result = run.run(discovery, tmp_path / "release", Transform(), Gate())

    assert _statuses(result) == [RELEASED, (REFUSED, (Reason.UNREADABLE_FILE,))]


@pytest.mark.pydicom
def test_a_directory_that_cannot_be_listed_stops_discovery_without_its_path(
    tmp_path, monkeypatch
):
    source = _write(tmp_path / "source" / SENTINEL, synthetic.collection()[:1])
    scandir = os.scandir

    def refuse(path):
        if SENTINEL in str(path):
            raise PermissionError(13, "Permission denied", str(path))
        return scandir(path)

    monkeypatch.setattr(run.os, "scandir", refuse)

    with pytest.raises(run.RunError, match="cannot be listed") as raised:
        run.discover(source.parent)

    assert SENTINEL not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


def _dicomdir(**file_meta):
    directory = pydicom.Dataset()
    directory.FileSetID = "SYNTHETIC"
    directory.DirectoryRecordSequence = []
    directory.file_meta = pydicom.dataset.FileMetaDataset()
    directory.file_meta.TransferSyntaxUID = synthetic.EXPLICIT_VR_LITTLE_ENDIAN
    directory.file_meta.MediaStorageSOPInstanceUID = "2.25.9"
    for keyword, value in file_meta.items():
        setattr(directory.file_meta, keyword, value)
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, directory, enforce_file_format=True)
    return buffer.getvalue()


@pytest.mark.pydicom
def test_a_dicomdir_is_never_passed_through(tmp_path):
    by_class = _dicomdir(MediaStorageSOPClassUID=run.MEDIA_STORAGE_DIRECTORY_STORAGE)
    by_records = _dicomdir(MediaStorageSOPClassUID="2.25.1")
    source = _write(
        tmp_path / "source",
        [synthetic.ct_slice(0), by_class, by_records, synthetic.ct_slice(1)],
        ["0.dcm", "1.dcm", "2.dcm", "DicomDir"],
    )

    discovery, result = _run(tmp_path, source=source)

    assert discovery.refusals == (None, None, None, Reason.DICOMDIR)
    assert _statuses(result) == [RELEASED] + [(REFUSED, (Reason.DICOMDIR,))] * 3


@pytest.mark.pydicom
def test_a_study_with_several_patients_stops_the_run_before_anything_is_created(
    tmp_path,
):
    datasets = synthetic.collection()
    datasets[DOSE].PatientID = OTHER_PATIENT_ID
    _write(tmp_path / "source", datasets)
    transform = Transform()

    with pytest.raises(run.RunStopped) as raised:
        _run(tmp_path, transform)

    (finding,) = raised.value.findings
    assert finding.kind is FindingKind.STUDY_WITH_SEVERAL_PATIENTS
    assert finding.instances == ((0, 1, 2, 3, 4), (5,))
    assert not transform.calls
    assert _listing(tmp_path) == ["source"]


@pytest.mark.pydicom
def test_findings_name_inputs_by_run_position(tmp_path):
    datasets = synthetic.collection()
    datasets[PLAN].ReferencedDoseSequence = [
        synthetic.reference(synthetic.RT_DOSE_STORAGE, "2.25.999")
    ]
    # A file that is not DICOM comes first, so the first pass has no record
    # of position 0.
    _write(tmp_path / "source", [b"not DICOM", *datasets])

    _, result = _run(tmp_path)

    assert (
        _statuses(result)
        == [(REFUSED, (Reason.NOT_READABLE_AS_DICOM,))] + [RELEASED] * 6
    )
    (finding,) = result.findings
    assert finding.kind is FindingKind.DANGLING_REFERENCE
    assert finding.instances == ((PLAN + 1,),)


@pytest.mark.pydicom
def test_an_identical_duplicate_is_processed_once(tmp_path):
    datasets = synthetic.collection()
    _write(tmp_path / "source", [datasets[0], datasets[1], datasets[0], datasets[0]])
    transform = Transform()

    _, result = _run(tmp_path, transform)

    assert transform.calls == [synthetic.CT_SLICES[0], synthetic.CT_SLICES[1]]
    assert _statuses(result) == [RELEASED, RELEASED] + [(DUPLICATE, ())] * 2
    assert [outcome.duplicate_of for outcome in result.outcomes] == [None, None, 0, 0]
    assert result.outcomes[2].output == result.outcomes[0].output
    assert len(_released_files(tmp_path / "release")) == 2


@pytest.mark.pydicom
def test_a_duplicate_follows_the_copy_that_was_processed(tmp_path):
    datasets = synthetic.collection()
    _write(tmp_path / "source", [datasets[PLAN], datasets[PLAN]])
    gate = Gate({_output(synthetic.PLAN): run.Sequestered((GateReason.TEXT_FINDING,))})

    _, result = _run(tmp_path, gate=gate)

    assert _statuses(result) == [(SEQUESTERED, (GateReason.TEXT_FINDING,))] * 2
    assert result.outcomes[1].duplicate_of == 0


@pytest.mark.pydicom
def test_a_later_copy_is_processed_when_the_first_changes(tmp_path, monkeypatch):
    datasets = synthetic.collection()
    source = _write(tmp_path / "source", [datasets[PLAN]] * 3)
    discovery = run.discover(source)
    first = discovery.paths[0]
    transform = Transform()
    first_pass = run._first_pass  # pylint: disable = protected-access

    def first_pass_then_change(found):
        # The first pass finds three identical copies; then the first changes.
        result = first_pass(found)
        first.write_bytes(first.read_bytes() + b"\x00\x00")
        return result

    monkeypatch.setattr(run, "_first_pass", first_pass_then_change)

    result = run.run(discovery, tmp_path / "release", transform, Gate())

    assert _statuses(result) == [
        (SEQUESTERED, (Reason.CHANGED_DURING_RUN,)),
        RELEASED,
        (DUPLICATE, ()),
    ]
    assert result.outcomes[2].duplicate_of == 1
    assert transform.calls == [synthetic.PLAN]


@pytest.mark.pydicom
def test_conflicting_copies_and_a_series_in_several_studies_are_sequestered(
    tmp_path,
):
    datasets = synthetic.collection()
    conflicting = synthetic.ct_slice(0)
    conflicting.SliceThickness = "2.5"
    datasets[DOSE].StudyInstanceUID = "2.25.110"
    other_dose = synthetic.rt_dose()
    other_dose.SOPInstanceUID = "2.25.502"
    _write(tmp_path / "source", [*datasets, conflicting, other_dose])

    _, result = _run(tmp_path)

    conflict = (SEQUESTERED, (FindingKind.CONFLICTING_INSTANCE,))
    several = (SEQUESTERED, (FindingKind.SERIES_IN_SEVERAL_STUDIES,))
    assert _statuses(result) == [
        conflict,
        RELEASED,
        RELEASED,
        RELEASED,
        RELEASED,
        several,
        conflict,
        several,
    ]
    assert len(_released_files(tmp_path / "release")) == 4


@pytest.mark.pydicom
def test_an_instance_without_a_uid_it_needs_is_sequestered(tmp_path):
    datasets = synthetic.collection()
    del datasets[PLAN].SeriesInstanceUID
    _write(tmp_path / "source", datasets)

    _, result = _run(tmp_path)

    assert _statuses(result)[PLAN] == (
        SEQUESTERED,
        (FindingKind.MISSING_IDENTIFIER,),
    )
    assert [outcome.status for outcome in result.outcomes].count(
        run.Status.RELEASED
    ) == 5


@pytest.mark.pydicom
def test_an_instance_whose_references_cannot_be_followed_is_sequestered(
    tmp_path, monkeypatch
):
    datasets = synthetic.collection()
    _write(tmp_path / "source", datasets)
    from_file = InstanceRecord.from_file.__func__
    unreadable = synthetic.written(synthetic.collection()[PLAN])

    def refuse_the_plan(cls, data):
        if bytes(data) == unreadable:
            raise UnreadableSequence(ElementPath((), "(300C,0080)"))
        return from_file(cls, data)

    monkeypatch.setattr(InstanceRecord, "from_file", classmethod(refuse_the_plan))

    _, result = _run(tmp_path)

    assert _statuses(result)[PLAN] == (SEQUESTERED, (Reason.UNREADABLE_SEQUENCE,))


@pytest.mark.pydicom
def test_a_file_that_changes_during_the_run_is_sequestered(tmp_path):
    source = _write(tmp_path / "source", synthetic.collection())
    paths = run.discover(source).paths
    transform = Transform()

    def change_the_dose(data, record):
        paths[DOSE].write_bytes(paths[DOSE].read_bytes() + b"\x00\x00")
        return transform(data, record)

    _, result = _run(tmp_path, change_the_dose)

    assert _statuses(result)[DOSE] == (SEQUESTERED, (Reason.CHANGED_DURING_RUN,))
    assert synthetic.DOSE not in transform.calls


@pytest.mark.pydicom
def test_a_transform_can_sequester_an_instance(tmp_path):
    _write(tmp_path / "source", synthetic.collection())

    _, result = _run(tmp_path, Transform(sequester={synthetic.PLAN}))

    assert result.outcomes[PLAN] == run.Outcome(
        PLAN, SEQUESTERED, (GateReason.TEXT_FINDING,)
    )
    assert len(_released_files(tmp_path / "release")) == 5


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "outcome, reasons",
    [
        (run.Sequestered((SENTINEL,)), (Reason.INVALID_REASON,)),
        (
            run.Sequestered((GateReason.TEXT_FINDING, SENTINEL)),
            (Reason.INVALID_REASON,),
        ),
        (run.Sequestered(()), (Reason.INVALID_REASON,)),
        (run.Sequestered(SENTINEL), (Reason.INVALID_REASON,)),
        (run.Sequestered((Finding,)), (Reason.INVALID_REASON,)),
        (SENTINEL, (Reason.INTERNAL_ERROR,)),
        (None, (Reason.INTERNAL_ERROR,)),
        (run.Release(), (Reason.INTERNAL_ERROR,)),
        (run.Transformed(PurePosixPath("x.dcm"), SENTINEL), (Reason.INTERNAL_ERROR,)),
    ],
    ids=[
        "text",
        "text-among-others",
        "none-given",
        "not-a-tuple",
        "a-class",
        "not-a-result",
        "none",
        "a-gate-result",
        "text-data",
    ],
)
def test_a_reason_that_could_hold_a_value_is_not_kept(tmp_path, outcome, reasons):
    _write(tmp_path / "source", synthetic.collection()[:1])

    _, result = _run(tmp_path, lambda data, record: outcome)

    assert _statuses(result) == [(SEQUESTERED, reasons)]
    assert SENTINEL not in repr(result)


@pytest.mark.pydicom
@pytest.mark.parametrize("stage", ["transform", "gate"])
def test_an_exception_sequesters_its_instance_without_its_message(tmp_path, stage):
    _write(tmp_path / "source", synthetic.collection()[:2])
    transform, gate = Transform(), Gate()

    def failing(call):
        def first_fails(*args):
            result = call(*args)
            if len(call.calls) == 1:
                raise ValueError(SENTINEL)
            return result

        return first_fails

    if stage == "transform":
        _, result = _run(tmp_path, transform=failing(transform))
    else:
        _, result = _run(tmp_path, gate=failing(gate))

    assert _statuses(result) == [(SEQUESTERED, (Reason.INTERNAL_ERROR,)), RELEASED]
    assert SENTINEL not in repr(result)
    assert len(_released_files(tmp_path / "release")) == 1


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "verdict", [None, True, "release", run.Transformed(PurePosixPath("x"), b"")]
)
def test_only_an_explicit_release_releases_a_file(tmp_path, verdict):
    _write(tmp_path / "source", synthetic.collection()[:1])

    _, result = _run(tmp_path, gate=lambda *args: verdict)

    assert _statuses(result) == [(SEQUESTERED, (Reason.INTERNAL_ERROR,))]
    assert not _released_files(tmp_path / "release")


@pytest.mark.pydicom
def test_the_gate_reads_each_staged_file_with_its_subjects_evidence(tmp_path):
    datasets = synthetic.collection()
    other = synthetic.instance(synthetic.MR_IMAGE_STORAGE, "2.25.801", "2.25.800")
    other.PatientID = OTHER_PATIENT_ID
    other.StudyInstanceUID = "2.25.810"
    _write(tmp_path / "source", [*datasets, other])
    gate = Gate()

    _run(tmp_path, gate=gate)

    assert [written for written, _, _ in gate.calls] == [
        _output(uid) for uid in (*STUDY, "2.25.801")
    ]
    for (_, evidence, subject), own in zip(gate.calls, (*STUDY, "2.25.801")):
        assert evidence == own
        # Its own first, then its subject's from the run's other instances.
        assert subject[0] == own
        assert sorted(subject) == sorted({own} if own == "2.25.801" else STUDY)


@pytest.mark.pydicom
def test_the_evidence_of_withheld_instances_reaches_their_subjects_gates(tmp_path):
    datasets = synthetic.collection()
    conflicting = synthetic.rt_dose()
    conflicting.DoseComment = "different bytes"
    _write(tmp_path / "source", [*datasets, conflicting])
    gate = Gate()
    transform = Transform(sequester={synthetic.PLAN})

    _, result = _run(tmp_path, transform, gate)

    # The plan, sequestered by the transform, and both copies of the
    # conflicting dose, sequestered by the first pass, are searched for in
    # the subject's released files.
    assert result.outcomes[PLAN].status is SEQUESTERED
    assert result.outcomes[DOSE].status is SEQUESTERED
    assert transform.calls.count(synthetic.DOSE) == 2
    for written, _, subject in gate.calls:
        assert written not in (_output(synthetic.PLAN), _output(synthetic.DOSE))
        assert sorted(subject) == sorted((*STUDY, synthetic.DOSE))


@pytest.mark.pydicom
def test_instances_without_a_patient_id_are_one_subject(tmp_path):
    first = synthetic.ct_slice(0)
    second = synthetic.instance(synthetic.MR_IMAGE_STORAGE, "2.25.801", "2.25.800")
    second.StudyInstanceUID = "2.25.810"
    for dataset in (first, second):
        del dataset.PatientID
    _write(tmp_path / "source", [first, second])
    gate = Gate()

    def transform(_data, record):
        path = _output_path(
            dataclasses.replace(
                record, patient=pseudonyms.SubjectIdentity.from_patient_id("x")
            )
        )
        return run.Transformed(path, _output(record.sop_instance), record.sop_instance)

    _run(tmp_path, transform, gate)

    assert [subject for _, _, subject in gate.calls] == [
        (synthetic.CT_SLICES[0], "2.25.801"),
        ("2.25.801", synthetic.CT_SLICES[0]),
    ]


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "verdict, status",
    [
        (run.Sequestered((GateReason.RESIDUAL_PERSON_NAME,)), SEQUESTERED),
        (run.HoldForReview((Finding("text", ElementPath((), "(300A,00C2)")),)), HELD),
    ],
    ids=["sequestered", "held"],
)
def test_a_file_the_gate_withholds_is_deleted_and_never_released(
    tmp_path, verdict, status
):
    _write(tmp_path / "source", synthetic.collection())
    withheld = _output(synthetic.PLAN)

    _, result = _run(tmp_path, gate=Gate({withheld: verdict}))

    assert result.outcomes[PLAN] == run.Outcome(PLAN, status, verdict.reasons)
    release = tmp_path / "release"
    assert all(
        path.read_bytes() != withheld for path in release.rglob("*") if path.is_file()
    )
    assert len(_released_files(release)) == 5


@pytest.mark.pydicom
def test_a_staged_file_that_changes_before_its_gate_is_withheld(tmp_path):
    _write(tmp_path / "source", synthetic.collection()[:2])
    staging = run.staging_path(tmp_path / "release")
    transform = Transform()

    def tamper(data, record):
        result = transform(data, record)
        if len(transform.calls) == 2:
            (staged,) = [path for path in staging.rglob("*.dcm") if path.read_bytes()]
            staged.write_bytes(b"CHANGED")
        return result

    _, result = _run(tmp_path, tamper)

    assert _statuses(result) == [(SEQUESTERED, (Reason.STAGED_FILE_CHANGED,)), RELEASED]


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "path",
    [
        "../escaped.dcm",
        "DEID-AAAAAAAAAAAAAAAA/2.25.1/2.25.2/../../x.dcm",
        "/absolute/path.dcm",
        "DEID-AAAAAAAAAAAAAAAA/2.25.1/2.25.2/2.25.3.dcm",  # not version 5 UUIDs
    ],
)
def test_an_output_name_that_is_not_a_replacement_is_refused(tmp_path, path):
    _write(tmp_path / "source", synthetic.collection()[:1])

    _, result = _run(
        tmp_path,
        lambda data, record: run.Transformed(PurePosixPath(path), b"OUTPUT"),
    )

    assert _statuses(result) == [(SEQUESTERED, (Reason.INVALID_OUTPUT_NAME,))]
    assert not _released_files(tmp_path / "release")
    assert _listing(tmp_path) == ["release", "source"]


@pytest.mark.pydicom
def test_instances_that_share_a_file_name_are_all_withheld(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    transform = Transform()
    records = {}

    def share_a_name(data, record):
        result = transform(data, record)
        records[record.sop_instance] = record
        if record.sop_instance in synthetic.CT_SLICES:
            # The same file name in a different series.
            first = records[synthetic.CT_SLICES[0]]
            path = _output_path(dataclasses.replace(record, series=record.sop_instance))
            path = path.with_name(_output_path(first).name)
            return run.Transformed(path, result.data, result.evidence)
        return result

    _, result = _run(tmp_path, share_a_name)

    shared = (SEQUESTERED, (Reason.SHARED_OUTPUT_NAME,))
    assert _statuses(result) == [shared] * 3 + [RELEASED] * 3
    assert len(_released_files(tmp_path / "release")) == 3


@pytest.mark.pydicom
@pytest.mark.parametrize("existing", ["release", ".release.staging"])
def test_a_run_refuses_an_existing_release_or_staging_directory(tmp_path, existing):
    _write(tmp_path / "source", synthetic.collection()[:1])
    (tmp_path / existing).mkdir()
    transform = Transform()

    with pytest.raises(run.RunError, match="already exists"):
        _run(tmp_path, transform)

    assert not transform.calls
    assert (tmp_path / existing).is_dir()


@pytest.mark.pydicom
def test_the_release_directory_must_not_be_inside_the_source(tmp_path):
    source = _write(tmp_path / "source", synthetic.collection()[:1])
    (source / "nested").mkdir()
    transform = Transform()

    for release in (source / "release", source / "nested" / "release"):
        with pytest.raises(run.RunError, match="inside the source directory"):
            run.run(run.discover(source), release, transform, Gate())

    assert not transform.calls


@pytest.mark.pydicom
def test_the_staging_area_is_beside_the_release_and_private(tmp_path):
    _write(tmp_path / "source", synthetic.collection()[:1])
    staging = run.staging_path(tmp_path / "release")
    seen = []
    transform = Transform()

    def inspect(*_args):
        (staged,) = staging.rglob("*.dcm")
        seen.append(
            (
                stat.S_IMODE(staging.stat().st_mode),
                stat.S_IMODE(staged.stat().st_mode),
            )
        )
        assert not (tmp_path / "release").exists()
        return run.Release()

    _run(tmp_path, transform, inspect)

    assert staging == tmp_path / ".release.staging"
    if POSIX:
        assert seen == [(0o700, 0o600)]
    assert not staging.exists()


@pytest.mark.pydicom
@pytest.mark.parametrize("failure", [KeyboardInterrupt, OSError])
def test_a_failed_run_publishes_nothing_and_leaves_no_staging(
    tmp_path, monkeypatch, failure
):
    _write(tmp_path / "source", synthetic.collection())

    def fail(*args):
        raise failure

    if failure is OSError:
        # Writing a staged file fails, as when the disk is full.
        monkeypatch.setattr(run, "_write_atomically", fail)
        with pytest.raises(OSError):
            _run(tmp_path)
    else:
        with pytest.raises(KeyboardInterrupt):
            _run(tmp_path, gate=fail)

    assert _listing(tmp_path) == ["source"]


@pytest.mark.pydicom
def test_a_staging_area_that_cannot_be_deleted_is_reported(tmp_path, monkeypatch):
    _write(tmp_path / "source", synthetic.collection()[:1])
    monkeypatch.setattr(run.shutil, "rmtree", lambda *args, **kwargs: None)

    _, result = _run(tmp_path)

    assert not result.staging_removed
    assert _statuses(result) == [RELEASED]


@pytest.mark.pydicom
def test_a_directory_that_cannot_be_flushed_does_not_fail_the_run(
    tmp_path, monkeypatch
):
    _write(tmp_path / "source", synthetic.collection()[:1])
    fsync = os.fsync

    def refuse_directories(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(22, "Invalid argument")
        return fsync(descriptor)

    monkeypatch.setattr(run.os, "fsync", refuse_directories)

    _, result = _run(tmp_path)

    assert _statuses(result) == [RELEASED]


@pytest.mark.pydicom
def test_nothing_a_run_reports_holds_a_source_path_or_value(tmp_path, capsys):
    datasets = synthetic.collection()
    for dataset in datasets:
        dataset.PatientName = SENTINEL
    source = _write(
        tmp_path / f"source-{SENTINEL}",
        datasets,
        [f"{SENTINEL}-{number}.dcm" for number in range(6)],
    )

    discovery, result = _run(tmp_path, source=source)

    shown = repr(discovery) + repr(result) + str(result)
    for outcome in result.outcomes:
        shown += str(outcome.output)
    assert SENTINEL not in shown
    assert synthetic.PATIENT_ID not in shown
    assert all(uid not in shown for uid in STUDY)
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out + captured.err


@pytest.mark.pydicom
def test_errors_name_no_source_path(tmp_path):
    datasets = synthetic.collection()
    datasets[DOSE].PatientID = OTHER_PATIENT_ID
    source = _write(tmp_path / f"source-{SENTINEL}", datasets)

    with pytest.raises(run.RunStopped) as stopped:
        _run(tmp_path, source=source)
    with pytest.raises(run.RunError) as refused:
        run.discover(tmp_path / f"missing-{SENTINEL}")

    assert SENTINEL not in str(stopped.value) + repr(stopped.value.findings)
    assert SENTINEL not in str(refused.value)
