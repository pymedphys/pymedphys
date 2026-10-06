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

"""The first pass's frame of reference findings, which are reported only."""

import os
import shutil
import struct
import tempfile
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    output_names,
    pseudonyms,
    reference_graph,
    references,
    run,
    uids,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import FrameUse, InstanceRecord

from . import _synthetic_references as synthetic

pytestmark = pytest.mark.pydicom

Finding = reference_graph.Finding
Kind = reference_graph.FindingKind
FRAME_KINDS = frozenset(
    {
        Kind.SERIES_IN_SEVERAL_FRAMES,
        Kind.UNLISTED_ROI_FRAME,
        Kind.CONTOUR_IMAGE_IN_ANOTHER_FRAME,
    }
)
KEY = DeidKey(bytes(range(32)))
# Positions in synthetic.collection().
SLICES = (0, 1, 2)
STRUCTURE_SET, PLAN, DOSE = 3, 4, 5
CT_FRAME = "2.25.900"
OTHER_FRAME = "2.25.901"
DOSE_FRAME = "2.25.902"
FRAME_OF_REFERENCE_UID = ("(0020,0052)",)
ROI_FRAME = ("(3006,0020)", "(3006,0024)")
CONTOUR_IMAGE = (
    "(3006,0010)",
    "(3006,0012)",
    "(3006,0014)",
    "(3006,0016)",
    "(0008,1155)",
)


def _roi(number, frame):
    roi = synthetic.item(ROINumber=number, ROIName=f"ROI {number}")
    synthetic.uid(roi, "ReferencedFrameOfReferenceUID", frame)
    return roi


def _collection(ct_frames=(CT_FRAME,) * 3, listed=(CT_FRAME,), roi_frames=(CT_FRAME,)):
    """Return the synthetic collection with frames of reference.

    The structure set lists each of ``listed`` in an item of its Referenced
    Frame of Reference Sequence, the first of them with the CT slices as its
    contour images, and has an ROI in each of ``roi_frames``.
    """
    inputs = synthetic.collection()
    for slice_, frame in zip(inputs[: len(SLICES)], ct_frames):
        if frame is not None:
            synthetic.uid(slice_, "FrameOfReferenceUID", frame)
    structure_set = inputs[STRUCTURE_SET]
    first, *_ = structure_set.ReferencedFrameOfReferenceSequence
    items = []
    for index, frame in enumerate(listed):
        each = first if index == 0 else synthetic.item()
        if frame is not None:
            synthetic.uid(each, "FrameOfReferenceUID", frame)
        items.append(each)
    structure_set.ReferencedFrameOfReferenceSequence = items
    structure_set.StructureSetROISequence = [
        _roi(number, frame) for number, frame in enumerate(roi_frames, start=1)
    ]
    synthetic.uid(inputs[DOSE], "FrameOfReferenceUID", DOSE_FRAME)
    return inputs


def _frame_findings(inputs):
    graph = reference_graph.build_reference_graph(
        [synthetic.record(each) for each in inputs]
    )
    return [finding for finding in graph.findings if finding.kind in FRAME_KINDS]


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_the_record_holds_the_frames_of_reference():
    inputs = _collection(listed=(CT_FRAME, OTHER_FRAME), roi_frames=(CT_FRAME, ""))

    structure_set = synthetic.record(inputs[STRUCTURE_SET])
    ct_slice = synthetic.record(inputs[0])
    dose = synthetic.record(inputs[DOSE])

    assert structure_set.frame_of_reference is None
    assert structure_set.frames == (
        FrameUse(CT_FRAME, synthetic.CT_SLICES),
        FrameUse(OTHER_FRAME, ()),
    )
    assert structure_set.roi_frames == (CT_FRAME, "")
    assert (ct_slice.frame_of_reference, ct_slice.frames, ct_slice.roi_frames) == (
        CT_FRAME,
        (),
        (),
    )
    assert dose.frame_of_reference == DOSE_FRAME
    assert CT_FRAME not in repr(structure_set) + repr(structure_set.frames[0])


def test_padding_is_removed_from_a_frame_of_reference():
    inputs = _collection(ct_frames=(CT_FRAME + "\x00",) * 3)

    assert synthetic.record(inputs[0]).frame_of_reference == CT_FRAME
    assert not _frame_findings(inputs)


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_frames_of_reference_that_agree_have_no_findings():
    # The dose is in a frame of reference of its own, which nothing compares.
    assert not _frame_findings(_collection())


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_series_in_several_frames_of_reference_is_reported():
    inputs = _collection(ct_frames=(CT_FRAME, OTHER_FRAME, CT_FRAME))

    assert Finding(
        Kind.SERIES_IN_SEVERAL_FRAMES, ((0, 2), (1,)), FRAME_OF_REFERENCE_UID
    ) in _frame_findings(inputs)


def test_an_input_without_a_frame_of_reference_is_left_out_of_its_series():
    assert not _frame_findings(_collection(ct_frames=(CT_FRAME, None, CT_FRAME)))


@pytest.mark.parametrize(
    "listed, roi_frames, count",
    [
        ((CT_FRAME,), (OTHER_FRAME,), 1),  # not listed
        ((CT_FRAME, CT_FRAME), (CT_FRAME,), 1),  # listed twice
        ((CT_FRAME,), ("",), 1),  # no value
        ((CT_FRAME,), (OTHER_FRAME, OTHER_FRAME, DOSE_FRAME), 2),
        ((CT_FRAME, None), (CT_FRAME,), 0),  # an item without a frame
    ],
    ids=["not-listed", "listed-twice", "empty", "distinct", "item-without-frame"],
)
@pytest.mark.deid_requirement("MIDI-BP-03")
def test_an_roi_whose_frame_of_reference_is_not_listed_once_is_reported(
    listed, roi_frames, count
):
    findings = _frame_findings(_collection(listed=listed, roi_frames=roi_frames))

    expected = [Finding(Kind.UNLISTED_ROI_FRAME, ((STRUCTURE_SET,),), ROI_FRAME, count)]
    assert [f for f in findings if f.kind is Kind.UNLISTED_ROI_FRAME] == (
        expected if count else []
    )


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_contour_image_in_another_frame_of_reference_is_reported():
    inputs = _collection(listed=(OTHER_FRAME,), roi_frames=(OTHER_FRAME,))

    assert _frame_findings(inputs) == [
        Finding(
            Kind.CONTOUR_IMAGE_IN_ANOTHER_FRAME,
            ((STRUCTURE_SET,), SLICES),
            CONTOUR_IMAGE,
            3,
        )
    ]


def test_contour_images_without_a_frame_or_outside_the_run_are_left_out():
    # One slice has no frame of reference, and an item without one lists none.
    inputs = _collection(ct_frames=(None, OTHER_FRAME, OTHER_FRAME), listed=(CT_FRAME,))

    assert _frame_findings(inputs) == [
        Finding(
            Kind.CONTOUR_IMAGE_IN_ANOTHER_FRAME,
            ((STRUCTURE_SET,), (1, 2)),
            CONTOUR_IMAGE,
            2,
        )
    ]
    # Without the slices in the run, nothing names them.
    outside = _collection(listed=(OTHER_FRAME,), roi_frames=(OTHER_FRAME,))
    assert not _frame_findings(outside[len(SLICES) :])


def test_frame_findings_hold_no_values():
    inputs = _collection(
        ct_frames=(CT_FRAME, OTHER_FRAME, CT_FRAME),
        listed=(OTHER_FRAME,),
        roi_frames=(DOSE_FRAME,),
    )

    findings = _frame_findings(inputs)

    assert {finding.kind for finding in findings} == FRAME_KINDS
    for value in (CT_FRAME, OTHER_FRAME, DOSE_FRAME, *synthetic.CT_SLICES):
        assert value not in repr(findings)


def _item_past_its_sequence(data, tag):
    """Return the file with the first item of ``tag`` running past its value."""
    data = bytearray(data)
    header = struct.pack("<HH", tag >> 16, tag & 0xFFFF)
    at = data.index(header + b"SQ\x00\x00")
    length_at = at + 8
    (length,) = struct.unpack_from("<I", data, length_at)
    assert data[length_at + 4 : length_at + 8] == b"\xfe\xff\x00\xe0"
    struct.pack_into("<I", data, length_at + 8, length + 40)
    return bytes(data)


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.filterwarnings("ignore:VR lookup failed:UserWarning")
def test_a_structure_set_roi_sequence_that_cannot_be_read_is_refused():
    structure_set = _collection()[STRUCTURE_SET]
    # Another element after it, for the item to run into.
    structure_set.ApprovalStatus = "UNAPPROVED"
    data = _item_past_its_sequence(synthetic.written(structure_set), 0x30060020)

    with pytest.raises(references.UnreadableSequence) as raised:
        InstanceRecord.from_file(data)

    assert raised.value.path == ElementPath((), "(3006,0020)")


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    """On Windows, a directory whose path leaves room for a run's output names."""
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _transform(data, record):
    del data
    path = output_names.instance_path(
        patient_id=pseudonyms.patient_pseudonym(KEY, record.patient).patient_id,
        study_instance_uid=uids.replacement_uid(KEY, record.study),
        series_instance_uid=uids.replacement_uid(KEY, record.series),
        sop_instance_uid=uids.replacement_uid(KEY, record.sop_instance),
    )
    return run.Transformed(path, b"OUTPUT " + record.sop_instance.encode())


def _gate(written, evidence, subject):
    del written, evidence, subject
    return run.Release()


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_a_run_reports_frame_findings_and_releases_their_instances(tmp_path):
    inputs = _collection(
        ct_frames=(CT_FRAME, OTHER_FRAME, CT_FRAME),
        listed=(OTHER_FRAME,),
        roi_frames=(DOSE_FRAME,),
    )
    source = tmp_path / "source"
    source.mkdir()
    for index, dataset in enumerate(inputs):
        (source / f"{index:03d}.dcm").write_bytes(synthetic.written(dataset))

    result = run.run(
        run.discover(source),
        tmp_path / "release",
        _transform,
        _gate,
        qc_destination=tmp_path / "qc",
    )

    assert {finding.kind for finding in result.findings} >= FRAME_KINDS
    assert all(outcome.status is run.Status.RELEASED for outcome in result.outcomes)
