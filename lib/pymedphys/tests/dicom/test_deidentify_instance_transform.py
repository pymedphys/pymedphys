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

# pylint: disable = too-many-lines

import functools
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    instance_transform,
    output_names,
    preservation,
    preserving_writer,
    release_report,
    run,
)
from pymedphys._dicom.deidentify.edits import EditKind, InstanceEdits, edit_instance
from pymedphys._dicom.deidentify.element_rules import ElementRules
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    PendingEdit,
    ReleaseGate,
    TransformReason,
    coverage_of,
    dropped_of,
    omissions_of,
    satisfied_options,
    transform_for,
    writer_plan,
)
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.markers import MarkerError
from pymedphys._dicom.deidentify.method_digest import method_digest
from pymedphys._dicom.deidentify.policy import PolicyError, compose_policy
from pymedphys._dicom.deidentify.preservation import PreservationReason
from pymedphys._dicom.deidentify.preserving_writer import WriteReason
from pymedphys._dicom.deidentify.pseudonyms import SubjectIdentity, patient_pseudonym
from pymedphys._dicom.deidentify.qc_pack import DropReason
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    ReleaseReason,
)
from pymedphys._dicom.deidentify.residuals import (
    ResidualSearch,
    SourceValue,
    has_written_constant,
    not_searched_of,
    written_constants,
)
from pymedphys._dicom.deidentify.run_qc import Dropped, SearchMaterial
from pymedphys._dicom.deidentify.scope import Disposition
from pymedphys._dicom.deidentify.source import SourceReason, read_source
from pymedphys._dicom.deidentify.uids import UIDOutcome, replacement_uid
from pymedphys._dicom.deidentify.walker import (
    SequesterReason,
    Sequestration,
    plan_instance,
)

from . import _synthetic_references as synthetic
from .test_deidentify_file_layout import EXPLICIT, _file
from .test_deidentify_walker import _plan, _rt_plan_data_set

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
SENTINEL_NAME = "SENTINEL^NAME"
SENTINEL_LABEL = "SENTINEL PLAN"


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


@functools.lru_cache(maxsize=None)
def _transform():
    return InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)


def _transformed(dataset):
    data = synthetic.written(dataset)
    return _transform()(data, InstanceRecord.from_file(data))


def _plan_with_sentinels():
    plan = synthetic.rt_plan()
    plan.PatientName = SENTINEL_NAME
    plan.RTPlanLabel = SENTINEL_LABEL
    return plan


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
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


@pytest.mark.deid_requirement("PS3.15-E.1.1-05", "PS3.15-E.2-01", "PS3.15-E.3.6-03")
def test_each_output_carries_the_de_identification_markers():
    digest = method_digest(
        compose_policy("basic"), vocabulary=None, reviewed_roi_names=None
    )
    for dataset in synthetic.collection():
        written = pydicom.dcmread(io.BytesIO(_transformed(dataset).data))

        assert written.PatientIdentityRemoved == "YES"
        assert list(written.DeidentificationMethod)[:1] == [digest]
        assert [
            (item.CodeValue, item.CodingSchemeDesignator)
            for item in written.DeidentificationMethodCodeSequence
        ] == [("113100", "DCM")]
        assert written.LongitudinalTemporalInformationModified == "REMOVED"
        (equipment,) = written.ContributingEquipmentSequence
        assert equipment.Manufacturer == "PyMedPhys"


@pytest.mark.deid_requirement("PS3.15-E.1.1-05")
def test_markers_already_present_are_updated_as_ps3_15_says():
    # The equipment item that the policy keeps stays first, and the
    # de-identifying equipment's follows it (E.1.1).
    dose = synthetic.rt_dose()
    dose.PatientIdentityRemoved = "NO"
    item = pydicom.Dataset()
    item.Manufacturer = "EARLIER EQUIPMENT"
    dose.ContributingEquipmentSequence = pydicom.Sequence([item])
    result = _transformed(dose)

    assert isinstance(result, run.Transformed)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.PatientIdentityRemoved == "YES"
    assert [item.Manufacturer for item in written.ContributingEquipmentSequence] == [
        "EARLIER EQUIPMENT",
        "PyMedPhys",
    ]


def test_edits_inside_kept_marker_sequences_are_written():
    # Contributing Equipment Sequence and De-identification Method Code
    # Sequence are kept, but the policy removes or replaces elements in
    # their items, which the markers must not bring back.
    dose = synthetic.rt_dose()
    equipment = pydicom.Dataset()
    equipment.Manufacturer = "EARLIER EQUIPMENT"
    equipment.InstitutionName = "SENTINEL HOSPITAL"
    equipment.DeviceUID = "2.25.731"
    dose.ContributingEquipmentSequence = pydicom.Sequence([equipment])
    code = pydicom.Dataset()
    code.CodeValue = "113101"
    code.CodingSchemeDesignator = "DCM"
    code.ContextGroupExtensionCreatorUID = "2.25.732"
    code.CodeMeaning = "Clean Pixel Data Option"
    dose.DeidentificationMethodCodeSequence = pydicom.Sequence([code])
    result = _transformed(dose)

    assert isinstance(result, run.Transformed)
    assert b"SENTINEL" not in result.data
    assert b"2.25.731" not in result.data
    assert b"2.25.732" not in result.data
    written = pydicom.dcmread(io.BytesIO(result.data))
    earlier, ours = written.ContributingEquipmentSequence
    assert earlier.Manufacturer == "EARLIER EQUIPMENT"
    assert ours.Manufacturer == "PyMedPhys"


def test_an_unplanned_element_in_a_kept_marker_sequence_sequesters():
    source = pydicom.Dataset()
    item = pydicom.Dataset()
    item.Manufacturer = "EARLIER EQUIPMENT"
    item.InstitutionName = "SENTINEL HOSPITAL"
    source.ContributingEquipmentSequence = pydicom.Sequence([item])
    sequence = _top("(0018,A001)")
    writing = instance_transform.WriterPlan(
        kept=frozenset({sequence, ElementPath((("(0018,A001)", 0),), "(0008,0070)")}),
        removed=frozenset(),
        replacements={},
    )

    with pytest.raises(instance_transform._Refused):  # pylint: disable = protected-access
        instance_transform._as_planned(  # pylint: disable = protected-access
            source[0x0018A001], (), writing
        )


def test_markers_that_cannot_be_added_sequester_the_instance(monkeypatch):
    def refuse(_dataset, _markers):
        raise MarkerError("refused")

    monkeypatch.setattr(instance_transform, "apply_markers", refuse)
    result = _transformed(synthetic.rt_dose())

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.UNMARKABLE,)


def test_the_satisfied_options_leave_out_clean_descriptors():
    assert not satisfied_options(compose_policy("basic"))
    assert not satisfied_options(compose_policy("basic-clean-descriptors"))
    assert "clean_descriptors" not in satisfied_options(
        compose_policy("public-release")
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
def test_references_between_instances_follow_their_replacements():
    dose = pydicom.dcmread(io.BytesIO(_transformed(synthetic.rt_dose()).data))
    plan = pydicom.dcmread(io.BytesIO(_transformed(synthetic.rt_plan()).data))

    referenced = dose.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID
    assert referenced == plan.SOPInstanceUID == replacement_uid(KEY, synthetic.PLAN)


@pytest.mark.deid_requirement("PS3.15-E.1.1-06")
def test_the_source_preamble_and_file_meta_are_not_written():
    data = synthetic.written(synthetic.rt_plan())
    source = b"SENTINEL PREAMBLE".ljust(128, b"\0") + data[128:]
    source_meta = pydicom.dcmread(io.BytesIO(source)).file_meta

    result = _transform()(source, InstanceRecord.from_file(source))

    assert isinstance(result, run.Transformed)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.preamble == bytes(128)
    assert (
        written.file_meta.ImplementationClassUID != source_meta.ImplementationClassUID
    )
    assert b"SENTINEL" not in result.data


@pytest.mark.deid_requirement("PS3.15-E.1.1-08")
def test_no_group_0004_element_is_written_at_any_level():
    plan = synthetic.rt_plan()
    plan.add_new(0x00041130, "CS", "SENTINEL TOP")
    plan.ReferencedStructureSetSequence[0].add_new(0x00041500, "CS", "SENTINEL ITEM")
    source = synthetic.written(plan)
    assert b"SENTINEL TOP" in source and b"SENTINEL ITEM" in source

    result = _transform()(source, InstanceRecord.from_file(source))

    assert isinstance(result, run.Transformed)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert not [element for element in written.iterall() if element.tag.group == 4]
    assert b"SENTINEL" not in result.data


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
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
    assert isinstance(evidence, Coverage)
    values = evidence.collected  # pylint: disable=no-member
    collected = {str(value.value) for value in values}
    assert SENTINEL_NAME in collected
    assert SENTINEL_LABEL in collected
    assert "SENTINEL" not in repr(evidence)
    assert "SENTINEL" not in repr(result)
    assert b"SENTINEL" not in result.data


@pytest.mark.deid_requirement("MIDI-BP-06")
def test_an_instance_the_release_does_not_support_is_sequestered_by_its_disposition():
    mr = synthetic.instance(
        synthetic.MR_IMAGE_STORAGE, synthetic.OTHER, synthetic.OTHER_SERIES
    )
    result = _transformed(mr)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (Disposition.UNSUPPORTED_IOD,)
    # Its values are collected for its subject's search, never written (D-027).
    assert isinstance(result.evidence, Coverage)


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

    # A reason that the release report gives, naming no path.
    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.PENDING_EDIT,)
    assert isinstance(result.evidence, Coverage)
    assert release_report.sequestration_reason(TransformReason.PENDING_EDIT)


def test_the_walkers_sequestrations_are_its_reasons_and_keep_the_evidence():
    dataset = _plan_with_sentinels()
    dataset[0x300A0002] = pydicom.DataElement(0x300A0002, "LO", SENTINEL_LABEL)
    result = _transformed(dataset)

    assert isinstance(result, run.Sequestered)
    # The walker may give further reasons for the same element, such as
    # that its value cannot be decoded.
    assert all(isinstance(reason, Sequestration) for reason in result.reasons)
    assert result.reasons[0].reason is SequesterReason.VR_NOT_IN_DICTIONARY
    assert isinstance(result.evidence, Coverage)
    assert "SENTINEL" not in repr(result)


# A SOP Class that PS3.4 Table B.5-1 does not list, as of a private one, so
# that no IOD gives a plan to collect its values by.
_UNLISTED_SOP_CLASS = "2.25.999"
_SHARED = "QUIMBYZELDA7"


def _plan_label_kept_in_a_dose(tmp_path, plan_class=None):
    """A plan, at position 0, whose label its subject's dose keeps."""
    plan = synthetic.rt_plan()
    plan.RTPlanLabel = _SHARED
    if plan_class is not None:
        plan.SOPClassUID = plan_class
    dose = synthetic.rt_dose()
    dose.DoseUnits = _SHARED  # kept as it is (K)
    return _source(tmp_path, [plan, dose])


@pytest.mark.deid_requirement("MIDI-BP-17")
@pytest.mark.parametrize("cause", ["no-iod", "raises", "changed"])
def test_a_sibling_that_gives_no_evidence_withholds_its_subject(
    tmp_path, monkeypatch, cause
):
    # Without the plan's coverage, the dose's search could not look for the
    # plan's label, which the dose keeps (D-027).
    no_iod = _UNLISTED_SOP_CLASS if cause == "no-iod" else None
    discovery = _plan_label_kept_in_a_dose(tmp_path, no_iod)
    transform = _transform()
    if cause == "raises":
        calls = []

        def raising(data, record):
            calls.append(record)
            if len(calls) == 1:
                raise RuntimeError("refused")
            return _transform()(data, record)

        transform = raising

    elif cause == "changed":
        second_read = run._second_read  # pylint: disable = protected-access

        def changed(found, first, position):
            return None if position == 0 else second_read(found, first, position)

        monkeypatch.setattr(run, "_second_read", changed)

    result = run.run(
        discovery,
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )

    dose = result.outcomes[1]
    assert dose.status is run.Status.SEQUESTERED
    assert ReleaseReason(Decision.WITHHOLD, ReasonCode.NOT_REPORTED) in dose.reasons


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_a_walker_sequestered_sibling_withholds_as_uncollected(tmp_path):
    plan = _plan_with_sentinels()
    plan[0x300A0002] = pydicom.DataElement(0x300A0002, "LO", SENTINEL_LABEL)

    result = run.run(
        _source(tmp_path, [plan, synthetic.rt_dose()]),
        tmp_path / "release",
        _transform(),
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )

    # The sibling is withheld for what the walker did not collect, as text
    # that is not an identifier may be held for review rather than
    # sequestered, never as not reported.
    dose = result.outcomes[1]
    assert dose.status in (run.Status.SEQUESTERED, run.Status.HELD_FOR_REVIEW)
    codes = {reason.code for reason in dose.reasons}
    assert ReasonCode.UNCOLLECTED in codes
    assert ReasonCode.NOT_REPORTED not in codes


_PATIENTS_NAME = 0x00100010
_INSTITUTION_NAME = 0x00080080


def _with_latin_1(dataset, tag, character_set=None):
    # Bytes outside ISO 646, which no Specific Character Set decodes unless
    # one is declared.
    vr = "PN" if tag == _PATIENTS_NAME else "LO"
    dataset[tag] = pydicom.DataElement(tag, vr, b"Synth\xe9tic^Name")
    if character_set is not None:
        dataset.SpecificCharacterSet = character_set
    return dataset


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "tag, decision",
    [(_PATIENTS_NAME, Decision.WITHHOLD), (_INSTITUTION_NAME, Decision.QC_REVIEW)],
)
def test_a_removed_value_read_as_latin_1_makes_collection_incomplete(tag, decision):
    data = synthetic.written(_with_latin_1(synthetic.rt_plan(), tag))
    record = InstanceRecord.from_file(data)
    transformed = _transform()(data, record)
    assert isinstance(transformed, run.Transformed)

    evidence = transformed.evidence
    assert isinstance(evidence, Coverage)
    path = _top(f"({tag >> 16:04X},{tag & 0xFFFF:04X})")
    read_as_latin_1 = evidence.decoded_as_bytes  # pylint: disable=no-member
    assert read_as_latin_1 == frozenset({path})
    result = ReleaseGate()(transformed.data, evidence, (evidence,))
    assert ReleaseReason(decision, ReasonCode.READ_AS_LATIN_1, path) in result.reasons


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_value_read_as_latin_1_withholds_its_siblings(tmp_path):
    plan = _with_latin_1(synthetic.rt_plan(), _PATIENTS_NAME)

    result = run.run(
        _source(tmp_path, [plan, synthetic.rt_dose()]),
        tmp_path / "release",
        _transform(),
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )

    path = _top("(0010,0010)")
    for outcome in result.outcomes:
        assert outcome.status is run.Status.SEQUESTERED
        reason = ReleaseReason(Decision.WITHHOLD, ReasonCode.READ_AS_LATIN_1, path)
        assert reason in outcome.reasons


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_value_in_a_declared_character_set_is_not_read_as_latin_1():
    plan = _with_latin_1(synthetic.rt_plan(), _PATIENTS_NAME, "ISO_IR 100")
    transformed = _transformed(plan)

    assert isinstance(transformed, run.Transformed)
    evidence = transformed.evidence
    assert isinstance(evidence, Coverage)
    assert not evidence.decoded_as_bytes  # pylint: disable=no-member


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_value_left_out_of_the_search_is_not_read_as_latin_1():
    data = synthetic.written(_with_latin_1(synthetic.rt_plan(), _PATIENTS_NAME))
    source = read_source(data)
    rules = ElementRules(compose_policy("basic"))
    plan = plan_instance(source, rules, _iod("RT Plan"))
    edits = edit_instance(source, plan, KEY)
    path = _top("(0010,0010)")
    assert path in edits.read_as_latin_1

    assert coverage_of(plan, edits).decoded_as_bytes == frozenset({path})
    assert coverage_of(plan, edits, frozenset({path})).decoded_as_bytes == frozenset()


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
def test_a_write_the_writer_refuses_is_sequestered_by_its_reason(monkeypatch):
    def refusing(*_args, **_kwargs):
        raise preserving_writer.WriteRefused(WriteReason.ENCODING, _top("(0010,0010)"))

    monkeypatch.setattr(instance_transform, "write_data_set", refusing)
    result = _transformed(synthetic.rt_plan())

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (WriteReason.ENCODING,)
    assert isinstance(result.evidence, Coverage)


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
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


def test_the_transform_refuses_a_policy_that_is_not_enabled():
    with pytest.raises(PolicyError, match="not enabled"):
        InstanceTransform(compose_policy("basic"), KEY)


def test_the_transform_shows_nothing_of_its_key():
    assert repr(_transform()) == "InstanceTransform()"


def test_a_run_with_the_transform_releases_the_collection(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for position, dataset in enumerate(synthetic.collection()):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))
    subjects = []

    def gate(_written, evidence, subject):
        assert isinstance(evidence, Coverage)
        subjects.append(len(subject))
        return run.Release()

    release = tmp_path / "release"
    result = run.run(
        run.discover(source),
        release,
        _transform(),
        gate,
        qc_destination=tmp_path / "qc",
    )

    assert [outcome.status for outcome in result.outcomes] == [run.Status.RELEASED] * 6
    assert subjects == [6] * 6
    for outcome in result.outcomes:
        data = (release / outcome.output).read_bytes()
        assert synthetic.PATIENT_ID.encode() not in data
        pydicom.dcmread(io.BytesIO(data))


def _source(tmp_path, datasets):
    source = tmp_path / "source"
    source.mkdir()
    for position, dataset in enumerate(datasets):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))
    return run.discover(source)


def test_retained_registered_uids_are_neither_planned_nor_collected():
    data = synthetic.written(synthetic.rt_dose())
    source = read_source(data)
    plan = _plan_of(data)
    edits = edit_instance(source, plan, KEY, InstanceRecord.from_file(data).patient)
    retained = [
        edit.path
        for edit in edits.edits
        if edit.uid_outcomes and set(edit.uid_outcomes) == {UIDOutcome.RETAINED}
    ]
    assert _top("(0008,0016)") in retained
    assert any(path.tag == "(0008,1150)" for path in retained)

    coverage = coverage_of(plan, edits)

    assert not set(retained) & coverage.planned
    assert not set(retained) & {value.source for value in coverage.collected}
    assert _top("(0008,0018)") in coverage.planned
    assert _top("(0008,0018)") in {value.source for value in coverage.collected}


def _dose_referencing_an_image():
    # Referenced Image Sequence is removed, and its Referenced SOP Class UID
    # is registered, so the edits collect nothing from it.
    dose = synthetic.rt_dose()
    item = pydicom.Dataset()
    item.ReferencedSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    item.ReferencedSOPInstanceUID = "2.25.4242"
    dose.ReferencedImageSequence = pydicom.Sequence([item])
    return dose


def test_registered_uids_the_edits_do_not_collect_are_not_planned():
    data = synthetic.written(_dose_referencing_an_image())
    plan = _plan_of(data)
    edits = edit_instance(
        read_source(data), plan, KEY, InstanceRecord.from_file(data).patient
    )
    path = ElementPath((("(0008,1140)", 0),), "(0008,1150)")
    assert path in edits.registered_uids
    assert path not in {value.source for value in edits.source_values}

    coverage = coverage_of(plan, edits)

    assert path not in coverage.planned
    assert path not in {missing.path for missing in coverage.uncollected}
    instance = ElementPath((("(0008,1140)", 0),), "(0008,1155)")
    assert instance in coverage.planned
    assert instance in {value.source for value in coverage.collected}


def test_a_removed_registered_uid_does_not_withhold_the_collection(tmp_path):
    dose = _dose_referencing_an_image()
    datasets = [
        dose if dataset.SOPInstanceUID == dose.SOPInstanceUID else dataset
        for dataset in synthetic.collection()
    ]
    assert dose in datasets
    result = run.run(
        _source(tmp_path, datasets),
        tmp_path / "release",
        _transform(),
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )

    assert [outcome.status for outcome in result.outcomes] == [run.Status.RELEASED] * 6


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_run_with_the_transform_and_gate_releases_the_collection(tmp_path):
    release = tmp_path / "release"
    result = run.run(
        _source(tmp_path, synthetic.collection()),
        release,
        _transform(),
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )

    assert [outcome.status for outcome in result.outcomes] == [run.Status.RELEASED] * 6
    for outcome in result.outcomes:
        data = (release / outcome.output).read_bytes()
        assert synthetic.PATIENT_ID.encode() not in data
        assert synthetic.PATIENTS_NAME.encode() not in data


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_value_removed_from_one_instance_withholds_its_siblings_that_keep_it(
    tmp_path,
):
    # The plan's RT Plan Label is replaced, and the dose's Dose Units, which
    # the Basic Profile keeps, holds the same text.
    plan = synthetic.rt_plan()
    plan.RTPlanLabel = "SENTINELPLAN7"
    dose = synthetic.rt_dose()
    dose.DoseUnits = "SENTINELPLAN7"
    release = tmp_path / "release"

    result = run.run(
        _source(tmp_path, [plan, dose]),
        release,
        _transform(),
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )

    statuses = [outcome.status for outcome in result.outcomes]
    assert statuses[0] is run.Status.RELEASED
    assert statuses[1] is not run.Status.RELEASED
    assert all(
        isinstance(reason, ReleaseReason) for reason in result.outcomes[1].reasons
    )
    assert len(list(release.rglob("*.dcm"))) == 1
    assert "SENTINEL" not in repr(result)


@pytest.mark.parametrize(
    "decision, expected",
    [
        (Decision.RELEASE, run.Release),
        (Decision.QC_REVIEW, run.HoldForReview),
        (Decision.WITHHOLD, run.Sequestered),
    ],
)
def test_the_gate_maps_each_decision_with_its_reasons(decision, expected):
    reason = ReleaseReason(decision, ReasonCode.RESIDUAL_TEXT, _top("(300A,0002)"))
    seen = []

    def condition(coverage, written):
        seen.append((coverage, written))
        return _Condition(
            decision, (reason,) if decision is not Decision.RELEASE else ()
        )

    own = Coverage(planned=frozenset({_top("(0010,0010)")}), collected=())
    other = Coverage(planned=frozenset({_top("(300A,0002)")}), collected=())

    result = ReleaseGate(condition)(b"written", own, (own, other))

    assert isinstance(result, expected)
    if expected is not run.Release:
        assert result.reasons == (reason,)
    (material,) = result.qc
    assert isinstance(material.search, ResidualSearch)
    assert material.written == b"written"
    ((pooled, written),) = seen
    assert written == b"written"
    assert pooled.planned == own.planned | other.planned


def test_the_gate_refuses_evidence_that_is_not_coverage():
    own = Coverage(planned=frozenset(), collected=())
    with pytest.raises(TypeError):
        ReleaseGate()(b"", own, (own, "SENTINEL"))
    assert repr(ReleaseGate()) == "ReleaseGate()"


class _Condition:
    def __init__(self, decision, reasons):
        self.decision = decision
        self.reasons = reasons
        self.search = ResidualSearch((), (), True)


def _plan_of(data):
    source = read_source(data)
    return plan_instance(source, ElementRules(compose_policy("basic")), _iod("RT Dose"))


def _iod(name):
    return load_iod_tables().iods[name]


def _top(tag):
    return ElementPath((), tag)


def _rt_plan_file():
    return _file(EXPLICIT, _rt_plan_data_set())


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_values_left_out_of_the_search_are_dropped_with_their_reasons():
    data = synthetic.written(_dose_referencing_an_image())
    plan = _plan_of(data)
    edits = edit_instance(
        read_source(data), plan, KEY, InstanceRecord.from_file(data).patient
    )

    drops = {(drop.source, drop.reason) for drop in dropped_of(edits)}

    assert (_top("(0008,0016)"), DropReason.RETAINED) in drops
    registered = ElementPath((("(0008,1140)", 0),), "(0008,1150)")
    assert (registered, DropReason.REGISTERED_UID) in drops
    # Every registered UID is dropped, and nothing else that the search is
    # given.
    assert {path for path, reason in drops if reason is DropReason.REGISTERED_UID} == (
        set(edits.registered_uids)
    )
    collected = {value.source for value in edits.source_values}
    assert all(
        path not in collected
        for path, reason in drops
        if reason is not DropReason.REGISTERED_UID
    )
    result = _transform()(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed)
    assert result.qc == dropped_of(edits)


def test_a_registered_uid_beside_a_collected_one_is_still_dropped():
    # A multi-valued UI whose other UID is collected still has its
    # registered UID left out of the search.
    path = _top("(0008,001A)")
    edits = InstanceEdits(
        edits=(),
        source_values=(SourceValue(path, "UI", "2.25.4242"),),
        not_collected=(),
        sequestrations=(),
        registered_uids=(path,),
    )

    assert dropped_of(edits) == (Dropped(path, DropReason.REGISTERED_UID),)


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_an_instances_own_omissions_are_its_material_not_the_gates():
    vr, constant = next((vr, value) for vr, value in written_constants() if vr == "LO")
    path = _top("(0008,1030)")
    written_constant = SourceValue(path, vr, constant)
    other = SourceValue(_top("(0010,0010)"), "PN", "SENTINEL^NAME")
    short = SourceValue(_top("(0008,1010)"), "SH", "AB")
    assert has_written_constant(written_constant)
    assert has_written_constant(SourceValue(path, vr, f"KEEP\\{constant}"))
    assert not has_written_constant(other)
    own = Coverage(
        planned=frozenset({path, other.source, short.source}),
        collected=(written_constant, other, short),
    )
    sibling = Coverage(
        planned=frozenset({short.source}),
        collected=(SourceValue(short.source, "SH", "CD"),),
    )

    omissions = omissions_of(own)

    assert omissions[0] == Dropped(path, DropReason.WRITTEN_CONSTANT)
    assert omissions[1:] == not_searched_of([other, short])
    assert {item.source for item in omissions[1:]} == {short.source}

    result = ReleaseGate()(b"written", own, (own, sibling))

    # The gate's search covers the sibling's value too, so what it leaves
    # out is listed by each instance's own transform, never by the gate.
    (search,) = result.qc
    assert isinstance(search, SearchMaterial)
    assert search.search.not_searched == ()
    assert search.search.unsearched == ()


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_each_value_not_searched_is_listed_once_at_its_own_instance(tmp_path):
    datasets = synthetic.collection()
    datasets[0].StationName = "AB"

    result = run.run(
        _source(tmp_path, datasets),
        tmp_path / "release",
        _transform(),
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )

    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    positions = {
        entry["position"]
        for entry in pack["not_searched"]
        if entry["source"] == "(0008,1010)"
    }
    assert positions == {0}


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_a_sequestered_instance_keeps_its_written_constant_drops(monkeypatch):
    # Its values are still searched for in its subject's other files.
    _, constant = next((vr, value) for vr, value in written_constants() if vr == "LO")
    dataset = synthetic.rt_dose()
    dataset.StudyDescription = constant

    def refuse(_dataset, _markers):
        raise MarkerError("refused")

    monkeypatch.setattr(instance_transform, "apply_markers", refuse)
    result = _transformed(dataset)

    assert isinstance(result, run.Sequestered)
    assert Dropped(_top("(0008,1030)"), DropReason.WRITTEN_CONSTANT) in result.qc


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_a_run_writes_the_qc_pack_of_the_transform_and_gate(tmp_path):
    plan = synthetic.rt_plan()
    plan.RTPlanLabel = "SENTINELPLAN7"
    dose = _dose_referencing_an_image()
    dose.DoseUnits = "SENTINELPLAN7"

    result = run.run(
        _source(tmp_path, [plan, dose]),
        tmp_path / "release",
        _transform(),
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )

    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    assert [entry["disposition"] for entry in pack["instances"]] == [
        "released",
        "held-for-review",
    ]
    assert pack["instances"][1]["reasons"]
    assert {entry["position"] for entry in pack["residual_findings"]} == {1}
    registered = {
        "position": 1,
        "source": "(0008,1140)[0] > (0008,1150)",
        "reason": "registered-uid",
    }
    assert registered in pack["drops"]


def test_transform_for_selects_an_enabled_preset_only(monkeypatch):
    with pytest.raises(PolicyError):
        transform_for("basic", KEY)

    policy = compose_policy("basic")
    made = []
    monkeypatch.setattr(instance_transform, "select_policy", lambda preset: policy)
    monkeypatch.setattr(
        instance_transform,
        "InstanceTransform",
        lambda *args, **kwargs: made.append((*args, kwargs)) or args,
    )
    cleaning = object()

    transform_for(key=KEY, cleaning=cleaning)
    transform_for("basic")

    (given, generated) = made
    assert given == (policy, KEY, None, {"cleaning": cleaning})
    assert generated[3] == {"cleaning": None}
    assert generated[0] is policy and generated[1] != KEY
