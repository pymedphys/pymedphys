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
from pymedphys._dicom.deidentify.residuals import SourceValue

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
# Positions in synthetic.collection(), whose files are named so that they
# sort in that order.
CT_POSITIONS = (0, 1, 2)
STRUCTURE_SET, PLAN, DOSE = 3, 4, 5
SENTINEL = "ZEBEDEE-QUILLON-7731"
OTHER_PATIENT_ID = "SYNTHETIC-9X4M"
POSIX = os.name == "posix"


def _write(directory, datasets, names=None):
    """Write each data set to ``directory`` as a file, in sorted name order."""
    directory.mkdir(parents=True, exist_ok=True)
    names = names or [f"{index:03d}.dcm" for index in range(len(datasets))]
    for name, dataset in zip(names, datasets):
        data = dataset if isinstance(dataset, bytes) else synthetic.written(dataset)
        (directory / name).write_bytes(data)
    return directory


def _output_path(record):
    patient = (
        pseudonyms.SubjectIdentity.from_patient_id("")
        if record.patient is None
        else record.patient
    )
    return output_names.instance_path(
        patient_id=pseudonyms.patient_pseudonym(KEY, patient).patient_id,
        study_instance_uid=uids.replacement_uid(KEY, record.study),
        series_instance_uid=uids.replacement_uid(KEY, record.series),
        sop_instance_uid=uids.replacement_uid(KEY, record.sop_instance),
    )


class Transform:
    """A stand-in for the walker and writer: each output names its source UID."""

    def __init__(self):
        self.calls = []

    def __call__(self, data, record):
        self.calls.append(record.sop_instance)
        value = SourceValue(ElementPath((), "(0008,0018)"), "UI", record.sop_instance)
        return run.Transformed(
            _output_path(record), b"OUTPUT " + record.sop_instance.encode(), (value,)
        )


class Gate:
    """A stand-in for the release condition that passes every file."""

    def __init__(self, verdicts=None):
        self.calls = []
        self.verdicts = verdicts or {}

    def __call__(self, written, transformed, subject_values):
        self.calls.append((written, transformed, subject_values))
        return self.verdicts.get(written)


def _run(tmp_path, transform=None, gate=None, source=None):
    source = source or tmp_path / "source"
    discovery = run.discover(source)
    result = run.run(
        discovery, tmp_path / "release", transform or Transform(), gate or Gate()
    )
    return discovery, result


def _statuses(result):
    return [(outcome.status, outcome.reason) for outcome in result.outcomes]


def _released_files(release):
    return sorted(
        path.relative_to(release).as_posix()
        for path in release.rglob("*")
        if path.is_file()
    )


RELEASED = (run.Status.RELEASED, None)


@pytest.mark.pydicom
def test_a_consistent_collection_is_released_at_its_output_names(tmp_path):
    _write(tmp_path / "source", synthetic.collection())

    discovery, result = _run(tmp_path)

    release = tmp_path / "release"
    assert result.release == release
    assert _statuses(result) == [RELEASED] * 6
    assert not result.findings
    records = [InstanceRecord.from_file(path.read_bytes()) for path in discovery.paths]
    for outcome, record in zip(result.outcomes, records):
        assert outcome.output == _output_path(record)
        written = release.joinpath(*outcome.output.parts).read_bytes()
        assert written == b"OUTPUT " + record.sop_instance.encode()
    assert len(_released_files(release)) == 6
    # Nothing is left beside the release.
    assert sorted(path.name for path in tmp_path.iterdir()) == ["release", "source"]


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
        run.RunReason.SYMBOLIC_LINK,
        run.RunReason.SYMBOLIC_LINK,
        run.RunReason.NOT_A_REGULAR_FILE,
    )
    assert _statuses(result) == [
        RELEASED,
        (run.Status.REFUSED, "symbolic-link"),
        (run.Status.REFUSED, "symbolic-link"),
        (run.Status.REFUSED, "not-a-regular-file"),
    ]
    assert len(_released_files(tmp_path / "release")) == 1


@pytest.mark.pydicom
def test_a_dicomdir_is_never_passed_through(tmp_path):
    directory = pydicom.Dataset()
    directory.FileSetID = "SYNTHETIC"
    directory.file_meta = pydicom.dataset.FileMetaDataset()
    directory.file_meta.TransferSyntaxUID = synthetic.EXPLICIT_VR_LITTLE_ENDIAN
    directory.file_meta.MediaStorageSOPClassUID = run.MEDIA_STORAGE_DIRECTORY_STORAGE
    directory.file_meta.MediaStorageSOPInstanceUID = "2.25.9"
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, directory, enforce_file_format=True)
    source = _write(
        tmp_path / "source",
        [synthetic.ct_slice(0), buffer.getvalue(), synthetic.ct_slice(1)],
        ["0.dcm", "1.dcm", "DicomDir"],
    )

    discovery, result = _run(tmp_path, source=source)

    assert discovery.refusals == (None, None, run.RunReason.DICOMDIR)
    assert _statuses(result) == [
        RELEASED,
        (run.Status.REFUSED, "dicomdir"),
        (run.Status.REFUSED, "dicomdir"),
    ]


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
    assert sorted(path.name for path in tmp_path.iterdir()) == ["source"]


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
        == [(run.Status.REFUSED, "not-readable-as-dicom")] + [RELEASED] * 6
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
    assert (
        _statuses(result) == [RELEASED, RELEASED] + [(run.Status.DUPLICATE, None)] * 2
    )
    assert [outcome.duplicate_of for outcome in result.outcomes] == [None, None, 0, 0]
    assert len(_released_files(tmp_path / "release")) == 2


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
    transform = Transform()

    _, result = _run(tmp_path, transform)

    assert _statuses(result) == [
        (run.Status.SEQUESTERED, "conflicting-instance"),
        RELEASED,
        RELEASED,
        RELEASED,
        RELEASED,
        (run.Status.SEQUESTERED, "series-in-several-studies"),
        (run.Status.SEQUESTERED, "conflicting-instance"),
        (run.Status.SEQUESTERED, "series-in-several-studies"),
    ]
    assert synthetic.CT_SLICES[0] not in transform.calls
    assert len(_released_files(tmp_path / "release")) == 4


@pytest.mark.pydicom
def test_an_instance_without_a_uid_it_needs_is_sequestered(tmp_path):
    datasets = synthetic.collection()
    del datasets[PLAN].SeriesInstanceUID
    _write(tmp_path / "source", datasets)

    _, result = _run(tmp_path)

    assert result.outcomes[PLAN].status is run.Status.SEQUESTERED
    assert result.outcomes[PLAN].reason == "missing-identifier"
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

    assert result.outcomes[PLAN].status is run.Status.SEQUESTERED
    assert result.outcomes[PLAN].reason == "unreadable-sequence"


@pytest.mark.pydicom
def test_a_file_that_changes_during_the_run_is_sequestered(tmp_path):
    source = _write(tmp_path / "source", synthetic.collection())
    paths = run.discover(source).paths
    transform = Transform()

    def change_the_dose(data, record):
        paths[DOSE].write_bytes(paths[DOSE].read_bytes() + b"\x00\x00")
        return transform(data, record)

    _, result = _run(tmp_path, change_the_dose)

    assert result.outcomes[DOSE].status is run.Status.SEQUESTERED
    assert result.outcomes[DOSE].reason == "changed-during-run"
    assert synthetic.DOSE not in transform.calls


@pytest.mark.pydicom
def test_a_transform_can_sequester_an_instance(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    transform = Transform()

    def sequester_the_plan(data, record):
        if record.sop_instance == synthetic.PLAN:
            return run.Sequestered("no-dummy-value")
        return transform(data, record)

    _, result = _run(tmp_path, sequester_the_plan)

    assert result.outcomes[PLAN] == run.Outcome(
        PLAN, run.Status.SEQUESTERED, "no-dummy-value"
    )
    assert len(_released_files(tmp_path / "release")) == 5


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "outcome, reason",
    [
        (run.Sequestered(SENTINEL), "invalid-reason"),
        (run.Sequestered("a" * 65), "invalid-reason"),
        (run.Sequestered("with space"), "invalid-reason"),
        (SENTINEL, "internal-error"),
        (None, "internal-error"),
        (run.Transformed(PurePosixPath("x.dcm"), SENTINEL), "internal-error"),
        (run.Transformed(PurePosixPath("x.dcm"), b"", (SENTINEL,)), "internal-error"),
    ],
    ids=[
        "value",
        "too-long",
        "space",
        "not-a-result",
        "none",
        "text-data",
        "not-source-values",
    ],
)
def test_a_reason_that_could_hold_a_value_is_not_kept(tmp_path, outcome, reason):
    _write(tmp_path / "source", synthetic.collection()[:1])

    _, result = _run(tmp_path, lambda data, record: outcome)

    assert _statuses(result) == [(run.Status.SEQUESTERED, reason)]
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

    assert _statuses(result) == [(run.Status.SEQUESTERED, "internal-error"), RELEASED]
    assert SENTINEL not in repr(result)
    assert len(_released_files(tmp_path / "release")) == 1


@pytest.mark.pydicom
def test_the_gate_reads_each_staged_file_with_its_subjects_values(tmp_path):
    datasets = synthetic.collection()
    other = synthetic.instance(synthetic.MR_IMAGE_STORAGE, "2.25.801", "2.25.800")
    other.PatientID = OTHER_PATIENT_ID
    other.StudyInstanceUID = "2.25.810"
    _write(tmp_path / "source", [*datasets, other])
    gate = Gate()

    _run(tmp_path, gate=gate)

    assert [written for written, _, _ in gate.calls] == [
        b"OUTPUT " + uid.encode()
        for uid in (*synthetic.CT_SLICES, synthetic.STRUCTURE_SET)
        + (synthetic.PLAN, synthetic.DOSE, "2.25.801")
    ]
    study = (
        *synthetic.CT_SLICES,
        synthetic.STRUCTURE_SET,
        synthetic.PLAN,
        synthetic.DOSE,
    )
    for (_, transformed, values), own in zip(gate.calls, (*study, "2.25.801")):
        uids_searched = [value.value for value in values]
        # Its own first, then its subject's from the run's other instances.
        assert uids_searched[0] == own
        expected = {"2.25.801"} if own == "2.25.801" else set(study)
        assert set(uids_searched) == expected
        assert transformed.source_values[0].value == own


@pytest.mark.pydicom
def test_a_file_the_gate_sequesters_is_deleted_and_never_released(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    withheld = b"OUTPUT " + synthetic.PLAN.encode()
    gate = Gate({withheld: run.Sequestered("residual-person-name")})

    _, result = _run(tmp_path, gate=gate)

    assert result.outcomes[PLAN] == run.Outcome(
        PLAN, run.Status.SEQUESTERED, "residual-person-name"
    )
    release = tmp_path / "release"
    assert all(
        path.read_bytes() != withheld for path in release.rglob("*") if path.is_file()
    )
    assert len(_released_files(release)) == 5


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

    assert _statuses(result) == [(run.Status.SEQUESTERED, "invalid-output-name")]
    assert not _released_files(tmp_path / "release")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["release", "source"]


@pytest.mark.pydicom
def test_instances_that_share_an_output_name_are_all_withheld(tmp_path):
    _write(tmp_path / "source", synthetic.collection())
    transform = Transform()
    shared = _output_path(
        InstanceRecord.from_file(synthetic.written(synthetic.ct_slice(0)))
    )

    def share_for_ct(data, record):
        result = transform(data, record)
        if record.sop_instance in synthetic.CT_SLICES:
            return run.Transformed(shared, result.data, result.source_values)
        return result

    _, result = _run(tmp_path, share_for_ct)

    assert (
        _statuses(result)
        == [(run.Status.SEQUESTERED, "shared-output-name")] * 3 + [RELEASED] * 3
    )
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
    transform = Transform()

    with pytest.raises(run.RunError, match="inside the source directory"):
        run.run(run.discover(source), source / "release", transform, Gate())

    assert not transform.calls


@pytest.mark.pydicom
def test_the_staging_area_is_beside_the_release_and_private(tmp_path):
    _write(tmp_path / "source", synthetic.collection()[:1])
    staging = run.staging_path(tmp_path / "release")
    seen = []
    transform = Transform()

    def inspect(data, record):
        seen.append(stat.S_IMODE(staging.stat().st_mode))
        assert not (tmp_path / "release").exists()
        return transform(data, record)

    _run(tmp_path, inspect)

    assert staging == tmp_path / ".release.staging"
    if POSIX:
        assert seen == [0o700]
    assert not staging.exists()


@pytest.mark.pydicom
def test_an_interrupted_run_publishes_nothing_and_leaves_no_staging(tmp_path):
    _write(tmp_path / "source", synthetic.collection())

    def interrupt(written, transformed, subject_values):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, gate=interrupt)

    assert sorted(path.name for path in tmp_path.iterdir()) == ["source"]


@pytest.mark.pydicom
def test_nothing_a_run_reports_holds_a_source_path_or_value(tmp_path, capsys):
    datasets = synthetic.collection()
    for dataset in datasets:
        dataset.PatientName = SENTINEL
    source = _write(
        tmp_path / f"source-{SENTINEL}",
        datasets,
        [f"{SENTINEL}-{n}.dcm" for n in range(6)],
    )

    discovery, result = _run(tmp_path, source=source)

    shown = repr(discovery) + repr(result) + str(result)
    for outcome in result.outcomes:
        shown += str(outcome.output)
    assert SENTINEL not in shown
    assert synthetic.PATIENT_ID not in shown
    assert all(uid not in shown for uid in synthetic.CT_SLICES)
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out + captured.err


@pytest.mark.pydicom
def test_errors_name_no_source_path(tmp_path):
    source = _write(tmp_path / f"source-{SENTINEL}", synthetic.collection())
    datasets = synthetic.collection()
    datasets[DOSE].PatientID = OTHER_PATIENT_ID
    _write(source, datasets)

    with pytest.raises(run.RunStopped) as stopped:
        _run(tmp_path, source=source)
    with pytest.raises(run.RunError) as refused:
        run.discover(tmp_path / f"missing-{SENTINEL}")

    assert SENTINEL not in str(stopped.value) + repr(stopped.value.findings)
    assert SENTINEL not in str(refused.value)
