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

"""The reference graph's second pass in a run: what was written, checked before publishing."""

import functools
import io
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    command,
    diagnostics,
    output_names,
    pseudonyms,
    release_report,
    run,
    run_written,
    uid_roles,
    uids,
    written_references,
)
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.reference_graph import build_reference_graph
from pymedphys._dicom.deidentify.references import (
    IDENTITY_TAGS,
    REFERENCE_TAGS,
    InstanceRecord,
)

from . import _synthetic_references as synthetic

pytestmark = pytest.mark.pydicom

KEY = DeidKey(bytes(range(32)))
OTHER_KEY = DeidKey(bytes(range(1, 33)))
# Run positions: a file that is not DICOM sorts first, so the collection's
# positions in the graph are one less than their run positions.
NOT_DICOM = 0
SLICES = (1, 2, 3)
STRUCTURE_SET, PLAN, DOSE = 4, 5, 6
SOP_INSTANCE_UID = IDENTITY_TAGS[next(iter(IDENTITY_TAGS))]
RELEASED = run.Status.RELEASED
SEQUESTERED = run.Status.SEQUESTERED
INCONSISTENT = run.RunReason.INCONSISTENT_REFERENCES
Kind = written_references.WrittenFindingKind
UID_TAGS = frozenset(
    int(tag[1:5] + tag[6:10], 16) for tag in (*IDENTITY_TAGS.values(), *REFERENCE_TAGS)
)


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    """On Windows, a directory whose path leaves room for a run's output names."""
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _source(tmp_path, datasets=None):
    """Write the synthetic collection, after a file that is not DICOM."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "000.bin").write_bytes(b"not DICOM")
    for index, dataset in enumerate(datasets or synthetic.collection(), start=1):
        (source / f"{index:03d}.dcm").write_bytes(synthetic.written(dataset))
    return source


def _replacement(value, key=KEY):
    return uids.transform_uid(key, uid_roles.UIDRole.INSTANCE, value)[0]


class Transform:
    """A stand-in for the walker and writer that replaces every UID it must.

    ``faults`` maps a source SOP Instance UID to a function that changes
    that instance's written data set, or to bytes written in its place; and
    the instances in ``withhold`` are sequestered.
    """

    def __init__(self, faults=None, withhold=()):
        self.faults = faults or {}
        self.withhold = withhold

    def __call__(self, data, record):
        if record.sop_instance in self.withhold:
            return run.Sequestered((run.RunReason.INTERNAL_ERROR,))
        dataset = synthetic.read(data)

        def replace(each, element):
            del each
            if element.tag in UID_TAGS and element.value:
                element.value = _replacement(element.value)

        dataset.walk(replace)
        del dataset.file_meta
        fault = self.faults.get(record.sop_instance)
        if callable(fault):
            fault(dataset)
        output = fault if isinstance(fault, bytes) else synthetic.written(dataset)
        path = output_names.instance_path(
            patient_id=pseudonyms.patient_pseudonym(KEY, record.patient).patient_id,
            study_instance_uid=_replacement(record.study),
            series_instance_uid=_replacement(record.series),
            sop_instance_uid=_replacement(record.sop_instance),
        )
        return run.Transformed(path, output)


def _gate(written, evidence, subject):
    del written, evidence, subject
    return run.Release()


def _run(tmp_path, source, transform=None, written_check=None, key=KEY, gate=_gate):
    if written_check is None:
        written_check = functools.partial(
            written_references.verify_written_references, key
        )
    return run.run(
        run.discover(source),
        tmp_path / "release",
        transform or Transform(),
        gate,
        qc_destination=tmp_path / "qc",
        written_check=written_check,
    )


def _statuses(result):
    return {
        outcome.position: (outcome.status, outcome.reasons)
        for outcome in result.outcomes
        if outcome.position != NOT_DICOM
    }


def _released(result):
    return sorted(
        outcome.position
        for outcome in result.outcomes
        if outcome.status is run.Status.RELEASED
    )


def _published(result):
    return sorted(
        path.relative_to(result.release).as_posix()
        for path in result.release.rglob("*")
        if path.is_file()
    )


def _outputs(result):
    return sorted(
        outcome.output.as_posix()
        for outcome in result.outcomes
        if outcome.status is run.Status.RELEASED
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_consistently_written_collection_is_released_without_findings(tmp_path):
    result = _run(tmp_path, _source(tmp_path))

    assert _released(result) == [*SLICES, STRUCTURE_SET, PLAN, DOSE]
    assert not result.written_findings
    assert _published(result) == _outputs(result)


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_an_instance_written_with_its_source_uid_is_sequestered(tmp_path):
    def keep_uid(dataset):
        dataset.SOPInstanceUID = synthetic.PLAN

    transform = Transform({synthetic.PLAN: keep_uid})
    result = _run(tmp_path, _source(tmp_path), transform)

    assert _statuses(result)[PLAN] == (SEQUESTERED, (INCONSISTENT,))
    # The dose's reference to the plan is sound, and names an instance that
    # was withheld, which is reported only.
    assert _released(result) == [*SLICES, STRUCTURE_SET, DOSE]
    assert _published(result) == _outputs(result)
    assert result.written_findings == (
        written_references.WrittenFinding(
            Kind.ORIGINAL_UID, ((PLAN,),), (SOP_INSTANCE_UID,), 1
        ),
        written_references.WrittenFinding(
            Kind.UNWRITTEN_TARGET, ((DOSE,),), synthetic.REFERENCED_PLAN, 1
        ),
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_reference_written_wrongly_sequesters_only_its_instance(tmp_path):
    def wrong_reference(dataset):
        dataset.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID = "2.25.999"

    transform = Transform({synthetic.DOSE: wrong_reference})
    result = _run(tmp_path, _source(tmp_path), transform)

    assert _statuses(result)[DOSE] == (SEQUESTERED, (INCONSISTENT,))
    assert _released(result) == [*SLICES, STRUCTURE_SET, PLAN]
    # The plan's reference to the withheld dose is reported only.
    assert [finding.kind for finding in result.written_findings] == [
        Kind.MISMATCHED_REFERENCE,
        Kind.UNWRITTEN_TARGET,
    ]
    assert result.written_findings[0].instances == ((DOSE,),)
    assert result.written_findings[1].instances == ((PLAN,),)


def test_instances_written_with_one_sop_instance_uid_are_all_sequestered(tmp_path):
    def shared(dataset):
        dataset.SOPInstanceUID = _replacement(synthetic.CT_SLICES[0])

    transform = Transform({synthetic.CT_SLICES[1]: shared})
    result = _run(tmp_path, _source(tmp_path), transform)

    assert _statuses(result)[SLICES[0]] == (SEQUESTERED, (INCONSISTENT,))
    assert _statuses(result)[SLICES[1]] == (SEQUESTERED, (INCONSISTENT,))
    assert _released(result) == [SLICES[2], STRUCTURE_SET, PLAN, DOSE]
    assert _published(result) == _outputs(result)
    kinds = {finding.kind for finding in result.written_findings}
    assert {Kind.MISMATCHED_IDENTIFIER, Kind.DUPLICATE_INSTANCE} <= kinds
    # The structure set's references to the withheld slices are reported.
    assert Kind.UNWRITTEN_TARGET in kinds


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_reference_whose_replacement_is_shared_is_sequestered(tmp_path, monkeypatch):
    # Two input UIDs whose replacements collide, as SHA-1 names almost never
    # do. The slices then share an output name, which withholds both before
    # the check; the structure set's references to them are ambiguous.
    collide = {synthetic.CT_SLICES[0], synthetic.CT_SLICES[1]}
    transform_uid = uids.transform_uid

    def colliding(key, role, uid):
        if uid in collide:
            return transform_uid(key, role, synthetic.CT_SLICES[0])
        return transform_uid(key, role, uid)

    monkeypatch.setattr(uids, "transform_uid", colliding)
    monkeypatch.setattr(written_references, "transform_uid", colliding)
    result = _run(tmp_path, _source(tmp_path))

    shared_name = (SEQUESTERED, (run.RunReason.SHARED_OUTPUT_NAME,))
    assert _statuses(result)[SLICES[0]] == shared_name
    assert _statuses(result)[SLICES[1]] == shared_name
    assert _statuses(result)[STRUCTURE_SET] == (SEQUESTERED, (INCONSISTENT,))
    assert result.written_findings[0] == written_references.WrittenFinding(
        Kind.SHARED_REPLACEMENT, ((STRUCTURE_SET,), (STRUCTURE_SET,)), ()
    )
    assert _released(result) == [SLICES[2], PLAN, DOSE]


def test_a_written_file_that_cannot_be_recorded_is_sequestered(tmp_path):
    transform = Transform({synthetic.STRUCTURE_SET: b"not DICOM either"})
    result = _run(tmp_path, _source(tmp_path), transform)

    assert _statuses(result)[STRUCTURE_SET] == (SEQUESTERED, (INCONSISTENT,))
    assert _released(result) == [*SLICES, PLAN, DOSE]


def test_a_run_under_another_key_releases_nothing(tmp_path):
    result = _run(tmp_path, _source(tmp_path), key=OTHER_KEY)

    assert _released(result) == []
    assert all(
        status == (SEQUESTERED, (INCONSISTENT,))
        for status in _statuses(result).values()
    )
    assert not _published(result)


def test_a_copy_of_an_instance_at_fault_is_sequestered_with_it(tmp_path):
    datasets = synthetic.collection()
    datasets.append(synthetic.rt_plan())

    def keep_uid(dataset):
        dataset.SOPInstanceUID = synthetic.PLAN

    result = _run(
        tmp_path, _source(tmp_path, datasets), Transform({synthetic.PLAN: keep_uid})
    )
    copy = len(datasets)

    assert _statuses(result)[PLAN] == (SEQUESTERED, (INCONSISTENT,))
    assert result.outcomes[copy].status is SEQUESTERED
    assert result.outcomes[copy].duplicate_of == PLAN


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_check_that_raises_publishes_nothing(tmp_path):
    def raising(graph, written):
        raise RuntimeError("2.25.401")

    with pytest.raises(run.ReleaseWithheld) as raised:
        _run(tmp_path, _source(tmp_path), written_check=raising)

    assert "2.25" not in str(raised.value)
    assert not raised.value.findings
    assert not (tmp_path / "release").exists()
    assert not run.staging_path(tmp_path / "release").exists()
    assert not (tmp_path / "qc").exists() or not any((tmp_path / "qc").iterdir())


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_fault_that_names_no_released_instance_publishes_nothing(tmp_path):
    def unwritten(graph, written):
        del written
        assert len(graph.records) == 6
        # The plan's graph position: a finding of an instance that was not
        # released, which no sequestration can isolate.
        return (
            written_references.WrittenFinding(
                Kind.MISMATCHED_IDENTIFIER, ((PLAN - 1,),), (SOP_INSTANCE_UID,), 1
            ),
        )

    transform = Transform(withhold=(synthetic.PLAN,))
    with pytest.raises(run.ReleaseWithheld) as raised:
        _run(tmp_path, _source(tmp_path), transform, written_check=unwritten)

    assert [finding.instances for finding in raised.value.findings] == [((PLAN,),)]
    assert "1 finding" in str(raised.value)
    assert not (tmp_path / "release").exists()
    assert not run.staging_path(tmp_path / "release").exists()


def test_the_check_is_given_each_released_file_as_read_back(tmp_path):
    given = {}

    def recording(graph, written):
        given.update(written)
        return written_references.verify_written_references(KEY, graph, written)

    result = _run(tmp_path, _source(tmp_path), written_check=recording)

    assert sorted(given) == [position - 1 for position in _released(result)]
    for position, record in given.items():
        outcome = result.outcomes[position + 1]
        assert record == InstanceRecord.from_file(
            (result.release / outcome.output).read_bytes()
        )


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_each_file_is_recorded_before_the_next_is_read(monkeypatch):
    inputs = synthetic.collection()
    graph = build_reference_graph([synthetic.record(each) for each in inputs])
    events = []
    record = InstanceRecord.from_file

    def recording(data):
        events.append("record")
        return record(data)

    def read_back():
        for position, dataset in enumerate(inputs):
            events.append("read")
            yield position, synthetic.written(dataset)

    monkeypatch.setattr(InstanceRecord, "from_file", recording)
    findings, withheld = run_written.second_pass(
        graph, tuple(range(len(inputs))), read_back(), lambda graph, written: ()
    )

    assert (findings, withheld) == ((), {})
    assert events == ["read", "record"] * len(inputs)


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_released_file_that_changes_before_it_is_read_back_is_sequestered(
    tmp_path,
):
    staging = run.staging_path(tmp_path / "release")
    gated = []

    def tampering(written, evidence, subject):
        gated.append(written)
        if len(gated) == len(SLICES) + 3:
            (first,) = [
                path for path in staging.rglob("*.dcm") if path.read_bytes() == gated[0]
            ]
            first.write_bytes(b"CHANGED")
        return _gate(written, evidence, subject)

    result = _run(tmp_path, _source(tmp_path), gate=tampering)

    assert _statuses(result)[SLICES[0]] == (
        SEQUESTERED,
        (run.RunReason.STAGED_FILE_CHANGED,),
    )
    assert _released(result) == [*SLICES[1:], STRUCTURE_SET, PLAN, DOSE]
    assert {finding.kind for finding in result.written_findings} == {
        Kind.UNWRITTEN_TARGET
    }
    assert b"CHANGED" not in b"".join(
        path.read_bytes() for path in result.release.rglob("*") if path.is_file()
    )


def test_the_transforms_check_is_the_second_pass_under_its_key():
    transform = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)
    inputs = synthetic.collection()
    graph = build_reference_graph([synthetic.record(each) for each in inputs])
    written = {}
    for position, each in enumerate(inputs):
        output = Transform()(synthetic.written(each), synthetic.record(each))
        assert isinstance(output, run.Transformed)
        written[position] = InstanceRecord.from_file(output.data)

    assert not transform.written_check(graph, written)
    del written[3]  # the structure set, which the plan refers to
    findings = transform.written_check(graph, written)
    assert findings
    assert findings == written_references.verify_written_references(KEY, graph, written)


def test_the_release_report_gives_the_reason():
    reason = release_report.sequestration_reason(INCONSISTENT)

    assert reason.stage == "run"
    assert reason.code == INCONSISTENT.value


def test_the_command_runs_the_check_it_is_given(tmp_path):
    def raising(graph, written):
        raise RuntimeError("2.25.401")

    stdout, stderr = io.StringIO(), io.StringIO()
    status = command.deidentify_directory(
        _source(tmp_path),
        tmp_path / "release",
        transform=Transform(),
        gate=_gate,
        qc_destination=tmp_path / "qc",
        written_check=raising,
        stdout=stdout,
        stderr=stderr,
    )

    assert status == command.EXIT_INTERNAL_ERROR
    assert "ReleaseWithheld" in stderr.getvalue()
    assert not (tmp_path / "release").exists()


def test_the_command_summary_counts_the_second_passs_findings(tmp_path):
    def keep_uid(dataset):
        dataset.SOPInstanceUID = synthetic.PLAN

    result = _run(tmp_path, _source(tmp_path), Transform({synthetic.PLAN: keep_uid}))

    lines = command.summary_lines(result, diagnostics.RedactionCounts())

    assert lines[-3:] == [
        "second-pass findings:",
        "  WrittenFindingKind.ORIGINAL_UID: 1",
        "  WrittenFindingKind.UNWRITTEN_TARGET: 1",
    ]
    assert "  RunReason.INCONSISTENT_REFERENCES: 1" in lines
    assert not any(synthetic.PLAN in line for line in lines)
