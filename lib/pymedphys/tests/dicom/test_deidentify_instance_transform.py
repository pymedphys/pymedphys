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

"""The run's concrete transform: walker, writer, verifier, and output name.

Every file is synthetic. Values that must never reach a result carry the
text ``SENTINEL``.
"""

import functools
import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    instance_transform,
    output_names,
    preservation,
    preserving_writer,
    run,
)
from pymedphys._dicom.deidentify.edits import EditKind, edit_instance
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceEvidence,
    InstanceTransform,
    PendingEdit,
    TransformReason,
    writer_plan,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.preservation import PreservationReason
from pymedphys._dicom.deidentify.preserving_writer import WriteReason
from pymedphys._dicom.deidentify.pseudonyms import SubjectIdentity, patient_pseudonym
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.scope import Disposition
from pymedphys._dicom.deidentify.source import SourceReason, read_source
from pymedphys._dicom.deidentify.uids import replacement_uid
from pymedphys._dicom.deidentify.walker import SequesterReason, Sequestration

from . import _synthetic_references as synthetic
from .test_deidentify_file_layout import EXPLICIT, _file
from .test_deidentify_walker import _plan, _rt_plan_data_set

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
SENTINEL_NAME = "SENTINEL^NAME"
SENTINEL_LABEL = "SENTINEL PLAN"


@functools.lru_cache(maxsize=None)
def _transform():
    return InstanceTransform(compose_policy("basic"), KEY)


def _transformed(dataset):
    data = synthetic.written(dataset)
    return _transform()(data, InstanceRecord.from_file(data))


def _plan_with_sentinels():
    plan = synthetic.rt_plan()
    plan.PatientName = SENTINEL_NAME
    plan.RTPlanLabel = SENTINEL_LABEL
    return plan


def test_each_instance_of_a_collection_is_written_and_named_by_its_replacements():
    pseudonym = patient_pseudonym(
        KEY, InstanceRecord.from_file(synthetic.written(synthetic.ct_slice(0))).patient
    )
    for dataset in synthetic.collection():
        source_uid = dataset.SOPInstanceUID
        result = _transformed(dataset)

        assert isinstance(result, run.Transformed)
        written = pydicom.dcmread(io.BytesIO(result.data))
        assert written.PatientID == pseudonym.patient_id
        assert written.PatientName == pseudonym.patients_name
        assert written.SOPInstanceUID == replacement_uid(KEY, source_uid)
        assert written.file_meta.MediaStorageSOPInstanceUID == written.SOPInstanceUID
        assert written.file_meta.MediaStorageSOPClassUID == dataset.SOPClassUID
        assert (
            written.file_meta.TransferSyntaxUID == synthetic.EXPLICIT_VR_LITTLE_ENDIAN
        )
        assert result.path == output_names.instance_path(
            patient_id=written.PatientID,
            study_instance_uid=written.StudyInstanceUID,
            series_instance_uid=written.SeriesInstanceUID,
            sop_instance_uid=written.SOPInstanceUID,
        )
        assert synthetic.PATIENT_ID.encode() not in result.data
        assert synthetic.PATIENTS_NAME.encode() not in result.data


def test_references_between_instances_follow_their_replacements():
    dose = pydicom.dcmread(io.BytesIO(_transformed(synthetic.rt_dose()).data))
    plan = pydicom.dcmread(io.BytesIO(_transformed(synthetic.rt_plan()).data))

    referenced = dose.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID
    assert referenced == plan.SOPInstanceUID == replacement_uid(KEY, synthetic.PLAN)


def test_the_output_is_written_from_the_source_and_verified_against_it(monkeypatch):
    verified = []
    original = preservation.verify_preservation

    def recording(source, output, expected):
        verified.append(expected)
        return original(source, output, expected)

    monkeypatch.setattr(instance_transform, "verify_preservation", recording)
    result = _transformed(synthetic.rt_plan())

    assert isinstance(result, run.Transformed)
    (expected,) = verified
    assert expected.kept and expected.changed
    assert read_source(result.data).transfer_syntax == (
        synthetic.EXPLICIT_VR_LITTLE_ENDIAN
    )


def test_the_evidence_holds_the_removed_values_and_shows_only_counts():
    result = _transformed(_plan_with_sentinels())

    assert isinstance(result, run.Transformed)
    evidence = result.evidence
    assert isinstance(evidence, InstanceEvidence)
    values = evidence.edits.source_values  # pylint: disable=no-member
    collected = {str(value.value) for value in values}
    assert SENTINEL_NAME in collected
    assert SENTINEL_LABEL in collected
    assert "SENTINEL" not in repr(evidence)
    assert "SENTINEL" not in repr(result)
    assert b"SENTINEL" not in result.data


def test_an_instance_the_release_does_not_support_is_sequestered_by_its_disposition():
    mr = synthetic.instance(
        synthetic.MR_IMAGE_STORAGE, synthetic.OTHER, synthetic.OTHER_SERIES
    )
    result = _transformed(mr)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (Disposition.UNSUPPORTED_IOD,)
    assert result.evidence is None


def test_a_source_file_that_is_not_ps3_10_is_sequestered_by_the_source_reason():
    data = synthetic.written(synthetic.rt_plan())
    record = InstanceRecord.from_file(data)

    result = _transform()(b"not a DICOM file", record)

    assert result == run.Sequestered((SourceReason.NOT_PS3_10,))


def test_without_the_subjects_identity_the_pseudonyms_are_pending():
    dataset = synthetic.rt_plan()
    dataset.PatientID = ""
    data = synthetic.written(dataset)
    record = InstanceRecord.from_file(data)
    assert record.patient is None

    result = _transform()(data, record)

    assert isinstance(result, run.Sequestered)
    assert PendingEdit(_top("(0010,0010)"), "Z") in result.reasons
    assert all(isinstance(reason, PendingEdit) for reason in result.reasons)
    assert isinstance(result.evidence, InstanceEvidence)


def test_the_walkers_sequestrations_are_its_reasons_and_keep_the_evidence():
    dataset = _plan_with_sentinels()
    dataset[0x300A0002] = pydicom.DataElement(0x300A0002, "LO", SENTINEL_LABEL)
    result = _transformed(dataset)

    assert isinstance(result, run.Sequestered)
    (reason,) = result.reasons
    assert isinstance(reason, Sequestration)
    assert reason.reason is SequesterReason.VR_NOT_IN_DICTIONARY
    assert isinstance(result.evidence, InstanceEvidence)
    assert "SENTINEL" not in repr(result)


def test_a_write_the_writer_refuses_is_sequestered_by_its_reason(monkeypatch):
    def refusing(*_args, **_kwargs):
        raise preserving_writer.WriteRefused(WriteReason.ENCODING, _top("(0010,0010)"))

    monkeypatch.setattr(instance_transform, "write_data_set", refusing)
    result = _transformed(synthetic.rt_plan())

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (WriteReason.ENCODING,)
    assert isinstance(result.evidence, InstanceEvidence)


def test_output_that_does_not_preserve_its_source_is_sequestered(monkeypatch):
    def failing(*_args):
        raise preservation.PreservationFailed(
            PreservationReason.VALUE, _top("(0028,0010)")
        )

    monkeypatch.setattr(instance_transform, "verify_preservation", failing)
    result = _transformed(synthetic.rt_plan())

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (PreservationReason.VALUE,)


def test_an_instance_without_a_uid_to_name_it_by_is_sequestered():
    dataset = synthetic.rt_plan()
    del dataset.SeriesInstanceUID
    result = _transformed(dataset)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.UNNAMED_OUTPUT,)


def test_no_exception_message_reaches_a_reason(monkeypatch):
    def refusing(*_args, **_kwargs):
        raise preserving_writer.WriteRefused(WriteReason.ELEMENT) from ValueError(
            SENTINEL_NAME
        )

    monkeypatch.setattr(instance_transform, "write_data_set", refusing)
    result = _transformed(_plan_with_sentinels())

    assert isinstance(result, run.Sequestered)
    assert "SENTINEL" not in repr(result.reasons)
    assert "SENTINEL" not in str(result.reasons)


def test_writer_plan_partitions_the_edits_for_the_writer():
    plan = _plan()
    identity = SubjectIdentity.from_patient_id("SENTINEL ID")
    edits = edit_instance(read_source(_rt_plan_file()), plan, KEY, identity)
    by_kind = {}
    for edit in edits.edits:
        by_kind.setdefault(edit.kind, set()).add(edit.path)

    result = writer_plan(plan, edits, ("iso8859",))

    assert result.kept == by_kind[EditKind.KEEP]
    assert result.removed == by_kind[EditKind.REMOVE]
    assert set(result.replacements) == (
        by_kind.get(EditKind.REPLACE, set()) | by_kind.get(EditKind.EMPTY, set())
    )
    for path, element in result.replacements.items():
        assert f"({element.tag.group:04X},{element.tag.element:04X})" == path.tag


def test_writer_plan_refuses_pending_edits_by_path_and_action():
    plan = _plan()
    edits = edit_instance(read_source(_rt_plan_file()), plan, KEY)
    pending = [edit for edit in edits.edits if edit.kind is EditKind.PENDING]
    assert pending  # Patient's Name without an identity

    with pytest.raises(instance_transform._Refused) as raised:  # pylint: disable=protected-access
        writer_plan(plan, edits, ("iso8859",))

    assert raised.value.reasons == tuple(
        PendingEdit(edit.path, edit.action) for edit in pending
    )


def test_the_transform_shows_nothing_of_its_key():
    assert repr(_transform()) == "InstanceTransform()"


def test_a_run_with_the_transform_releases_the_collection(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for position, dataset in enumerate(synthetic.collection()):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))
    subjects = []

    def gate(_written, evidence, subject):
        assert isinstance(evidence, InstanceEvidence)
        subjects.append(len(subject))
        return run.Release()

    release = tmp_path / "release"
    result = run.run(run.discover(source), release, _transform(), gate)

    assert [outcome.status for outcome in result.outcomes] == [run.Status.RELEASED] * 6
    assert subjects == [6] * 6
    for outcome in result.outcomes:
        data = (release / outcome.output).read_bytes()
        assert synthetic.PATIENT_ID.encode() not in data
        pydicom.dcmread(io.BytesIO(data))


def _top(tag):
    return ElementPath((), tag)


def _rt_plan_file():
    return _file(EXPLICIT, _rt_plan_data_set())
