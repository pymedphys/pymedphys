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

"""Tests for checking a written instance against its IOD's required attributes."""

import copy
import functools

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import instance_transform, run
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    TransformReason,
)
from pymedphys._dicom.deidentify.iod_conformance import (
    LostRequirement,
    lost_requirements,
)
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.scope import classify
from pymedphys._dicom.deidentify.source import read_source

from . import _synthetic_references as synthetic
from .test_deidentify_descriptor_cleaning import (  # pylint: disable = unused-import
    _published,
)
from .test_deidentify_descriptor_cleaning import _transform as _cleaning_transform

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
MODALITY = ElementPath((), "(0008,0060)")
PATIENTS_NAME = ElementPath((), "(0010,0010)")
SOURCE_SERIES = "(3006,004C)"
RT_ROI_OBSERVATIONS = "(3006,0080)"
ROI_INTERPRETER = 0x3006004E


@functools.lru_cache(maxsize=None)
def _iods():
    return load_iod_tables().iods


def _found(source, output, iod):
    return lost_requirements(
        read_source(synthetic.written(source)),
        read_source(synthetic.written(output)),
        _iods()[iod],
    )


def _ct():
    dataset = synthetic.ct_slice(0)
    dataset.Modality = "CT"
    dataset.ConsultingPhysicianName = "FICTITIOUS^CONSULTANT"
    return dataset


def _structure_set():
    dataset = synthetic.structure_set()
    dataset.SourceSeriesInformationSequence = [
        synthetic.item(SeriesDescription="SYNTHETIC SERIES", Modality="CT")
    ]
    observation = synthetic.item(ObservationNumber=1, ReferencedROINumber=1)
    observation[ROI_INTERPRETER] = synthetic.sequence(
        ROI_INTERPRETER, [synthetic.item(PersonName="FICTITIOUS^INTERPRETER")]
    )
    dataset.RTROIObservationsSequence = [observation]
    return dataset


def _without(dataset, *keywords):
    output = copy.deepcopy(dataset)
    for keyword in keywords:
        delattr(output, keyword)
    return output


def test_an_unchanged_instance_loses_no_requirement():
    assert not _found(_ct(), _ct(), "CT Image")
    assert not _found(_structure_set(), _structure_set(), "RT Structure Set")


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_removed_type_1_attribute_is_found():
    assert _found(_ct(), _without(_ct(), "Modality"), "CT Image") == (
        LostRequirement(MODALITY, "1", emptied=False),
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_an_emptied_type_1_attribute_is_found():
    output = _ct()
    output.Modality = ""

    assert _found(_ct(), output, "CT Image") == (
        LostRequirement(MODALITY, "1", emptied=True),
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_removed_type_2_attribute_is_found_but_an_emptied_one_is_not():
    emptied = _ct()
    emptied.PatientName = ""

    assert _found(_ct(), _without(_ct(), "PatientName"), "CT Image") == (
        LostRequirement(PATIENTS_NAME, "2", emptied=False),
    )
    assert not _found(_ct(), emptied, "CT Image")


def test_a_removed_type_3_attribute_is_not_found():
    assert not _found(_ct(), _without(_ct(), "ConsultingPhysicianName"), "CT Image")


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_an_attribute_missing_or_empty_in_the_source_is_not_the_engines():
    empty = _ct()
    empty.Modality = ""

    assert not _found(
        _without(_ct(), "Modality"), _without(_ct(), "Modality"), "CT Image"
    )
    assert not _found(empty, empty, "CT Image")


def test_a_removed_type_1_attribute_is_found_even_if_its_source_was_empty():
    empty = _ct()
    empty.Modality = ""

    assert _found(empty, _without(_ct(), "Modality"), "CT Image") == (
        LostRequirement(MODALITY, "1", emptied=False),
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_required_attribute_in_a_kept_item_is_found_at_its_path():
    output = _structure_set()
    del output.SourceSeriesInformationSequence[0].SeriesDescription

    assert _found(_structure_set(), output, "RT Structure Set") == (
        LostRequirement(
            ElementPath(((SOURCE_SERIES, 0),), "(0008,103E)"), "1", emptied=False
        ),
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_required_attribute_goes_with_its_removed_type_3_sequence():
    output = _without(_structure_set(), "SourceSeriesInformationSequence")

    assert not _found(_structure_set(), output, "RT Structure Set")


def test_an_emptied_required_sequence_is_found():
    output = _structure_set()
    study = output.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[0]
    study.RTReferencedSeriesSequence = []
    path = ElementPath((("(3006,0010)", 0), ("(3006,0012)", 0)), "(3006,0014)")

    # What the emptied sequence's items held goes with them.
    assert _found(_structure_set(), output, "RT Structure Set") == (
        LostRequirement(path, "1", emptied=True),
    )


def test_roi_interpreter_sequence_may_go_alone():
    output = _structure_set()
    del output.RTROIObservationsSequence[0][ROI_INTERPRETER]

    assert not _found(_structure_set(), output, "RT Structure Set")


def test_a_user_optional_overlay_group_may_go():
    source = _ct()
    source.add_new(0x60000010, "US", 4)  # Overlay Rows, Type 1
    source.add_new(0x60000011, "US", 4)  # Overlay Columns, Type 1
    source.add_new(0x60003000, "OW", bytes(2))  # Overlay Data, Type 1

    assert not _found(source, _ct(), "CT Image")


def _with_overlay(dataset, group=0x6000):
    dataset.add_new(group << 16 | 0x0010, "US", 4)  # Overlay Rows, Type 1
    dataset.add_new(group << 16 | 0x0011, "US", 4)  # Overlay Columns, Type 1
    dataset.add_new(group << 16 | 0x0040, "CS", "G")  # Overlay Type, Type 1
    dataset.add_new(group << 16 | 0x0050, "SS", [1, 1])  # Overlay Origin, Type 1
    dataset.add_new(group << 16 | 0x0100, "US", 1)  # Overlay Bits Allocated
    dataset.add_new(group << 16 | 0x0102, "US", 0)  # Overlay Bit Position
    dataset.add_new(group << 16 | 0x3000, "OW", bytes(2))  # Overlay Data
    return dataset


def test_a_partly_removed_overlay_group_is_found():
    output = _with_overlay(_ct())
    del output[0x60000010]

    assert _found(_with_overlay(_ct()), output, "CT Image") == (
        LostRequirement(ElementPath((), "(6000,0010)"), "1", emptied=False),
    )


def test_one_whole_overlay_group_may_go_while_another_stays():
    source = _with_overlay(_with_overlay(_ct()), group=0x6002)
    output = _with_overlay(_ct(), group=0x6002)

    assert not _found(source, output, "CT Image")


def test_the_check_reads_types_at_every_depth():
    output = _structure_set()
    del (
        output.ReferencedFrameOfReferenceSequence[0]
        .RTReferencedStudySequence[0]
        .RTReferencedSeriesSequence[0]
        .SeriesInstanceUID
    )

    (lost,) = _found(_structure_set(), output, "RT Structure Set")

    assert lost.path.items == (
        ("(3006,0010)", 0),
        ("(3006,0012)", 0),
        ("(3006,0014)", 0),
    )
    assert lost.path.tag == "(0020,000E)"
    assert lost.type == "1"


def test_the_items_of_a_replaced_sequence_are_the_engines_own():
    output = _structure_set()
    study = output.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[0]
    del study.RTReferencedSeriesSequence[0].SeriesInstanceUID
    series = ElementPath((("(3006,0010)", 0), ("(3006,0012)", 0)), "(3006,0014)")
    source = read_source(synthetic.written(_structure_set()))
    written = read_source(synthetic.written(output))
    iod = _iods()["RT Structure Set"]

    assert lost_requirements(source, written, iod)
    assert not lost_requirements(source, written, iod, replaced={series})


def test_the_repr_names_only_the_path_and_type():
    lost = LostRequirement(MODALITY, "1", emptied=False)

    assert "CT" not in repr(lost)
    assert "(0008,0060)" in repr(lost)


@functools.lru_cache(maxsize=None)
def _transform():
    return InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)


def _transformed(dataset):
    data = synthetic.written(dataset)
    return _transform()(data, InstanceRecord.from_file(data))


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_each_written_instance_of_a_collection_keeps_its_requirements():
    for dataset in (*synthetic.collection(), _ct(), _structure_set()):
        data = synthetic.written(dataset)
        result = _transform()(data, InstanceRecord.from_file(data))

        assert isinstance(result, run.Transformed)
        iod = classify(dataset.SOPClassUID, synthetic.EXPLICIT_VR_LITTLE_ENDIAN).iod
        assert not lost_requirements(
            read_source(data), read_source(result.data), _iods()[iod]
        )


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_an_instance_whose_de_identification_loses_a_requirement_is_sequestered(
    monkeypatch,
):
    original = instance_transform.writer_plan

    def losing_modality(plan, edits, codecs):
        writing = original(plan, edits, codecs)
        return instance_transform.WriterPlan(
            writing.kept - {MODALITY},
            writing.removed | {MODALITY},
            writing.replacements,
            writing.introduced,
        )

    monkeypatch.setattr(instance_transform, "writer_plan", losing_modality)
    result = _transformed(_ct())

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.REQUIRED_ATTRIBUTE_LOST,)


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_an_instance_whose_de_identification_keeps_part_of_an_overlay_is_sequestered(
    monkeypatch,
):
    original = instance_transform.writer_plan
    rows = ElementPath((), "(6000,0010)")

    def keeping_part_of_the_overlay(plan, edits, codecs):
        writing = original(plan, edits, codecs)
        overlay = {path for path in writing.removed if path.tag.startswith("(6000,")}
        assert rows in overlay
        return instance_transform.WriterPlan(
            writing.kept | (overlay - {rows}),
            writing.removed - (overlay - {rows}),
            writing.replacements,
            writing.introduced,
        )

    monkeypatch.setattr(instance_transform, "writer_plan", keeping_part_of_the_overlay)
    result = _transformed(_with_overlay(_ct()))

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.REQUIRED_ATTRIBUTE_LOST,)


def test_an_instance_whose_whole_overlay_is_removed_is_released():
    result = _transformed(_with_overlay(_ct()))

    assert isinstance(result, run.Transformed)
    assert "OverlayRows" not in synthetic.read(result.data)


def test_the_reason_is_named_by_its_value():
    assert TransformReason.REQUIRED_ATTRIBUTE_LOST.value == "required-attribute-lost"


def test_the_written_file_is_checked_against_its_iod(monkeypatch):
    checked = []
    original = instance_transform.lost_requirements

    def recording(source, output, iod, replaced):
        checked.append((iod.name, output.size))
        return original(source, output, iod, replaced)

    monkeypatch.setattr(instance_transform, "lost_requirements", recording)
    result = _transformed(_ct())

    assert isinstance(result, run.Transformed)
    assert checked == [("CT Image", len(result.data))]


def _plan_with_setup_photo():
    plan = synthetic.rt_plan()
    photo = synthetic.item(PatientSetupPhotoDescription="FICTITIOUS PHOTO")
    preparation = synthetic.item(ReferencedPatientSetupPhotoSequence=[photo])
    plan.PatientSetupSequence = [
        synthetic.item(
            PatientSetupNumber=1, PatientTreatmentPreparationSequence=[preparation]
        )
    ]
    return plan


@pytest.mark.parametrize("cleaning", [False, True])
@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_descriptor_whose_basic_x_needs_its_sequence_takes_the_sequence(cleaning):
    # Patient Setup Photo Description, X in the Basic Profile and C with
    # Clean Descriptors, is Type 2 in Referenced Patient Setup Photo
    # Sequence, which is Type 3, so its X removes that sequence too.
    transform = _cleaning_transform() if cleaning else _transform()
    data = synthetic.written(_plan_with_setup_photo())

    result = transform(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed)
    written = synthetic.read(result.data)
    (setup,) = written.PatientSetupSequence
    (preparation,) = setup.PatientTreatmentPreparationSequence
    assert "ReferencedPatientSetupPhotoSequence" not in preparation
    # A descriptor that its Basic Profile action removes still meets the
    # option, with the sequence that goes with it.
    codes = [item.CodeValue for item in written.DeidentificationMethodCodeSequence]
    assert ("113105" in codes) == cleaning
