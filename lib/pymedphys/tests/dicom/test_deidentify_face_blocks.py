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

"""Each CT series' face block in a run, and the air written there, on an
analytic head. Every UID and value here is invented."""

from __future__ import annotations

import dataclasses
import functools
import io

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import face_blocks
from pymedphys._dicom.deidentify.defacing import FaceBlockProblem
from pymedphys._dicom.deidentify.face_blocks import (
    CtDefacer,
    FaceBlockCounts,
    SeriesDefacing,
    SeriesProblem,
    find_face_blocks,
)
from pymedphys._dicom.deidentify.pixel_cleaning import PixelDataRefused
from pymedphys._dicom.deidentify.references import InstanceRecord

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files

# Coarser than the finder's own tests, to keep the files small.
_SCAN = head.axial(
    spacing=2.0, thickness=3.0, extent=((-100, 100), (-130, 110), (-60, 120))
)
_EYES_FRONT = [(-32.0, -76.0, 20.0), (32.0, -76.0, 20.0)]


@functools.cache
def _head_files() -> tuple[bytes, ...]:
    return tuple(files.ct_files(_SCAN, head.Head(noise=0.0)))


def _outcomes(*others: bytes, slices: tuple[bytes, ...] | None = None) -> dict:
    data = list(_head_files() if slices is None else slices) + list(others)
    records = {
        position: InstanceRecord.from_file(each) for position, each in enumerate(data)
    }
    return find_face_blocks(records, lambda position: data[position])


def _outcome(*others: bytes, slices: tuple[bytes, ...] | None = None) -> SeriesDefacing:
    (outcome,) = list(_outcomes(*others, slices=slices).values())
    return outcome


def test_a_head_ct_series_has_its_face_block():
    outcome = _outcome()

    assert outcome.problem is None
    np.testing.assert_allclose(
        outcome.block.globes,
        (
            (-head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
            (head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
        ),
        atol=2.0,
    )


def test_each_series_is_found_by_its_series_instance_uid():
    other = files.ct_files(
        _SCAN, head.Head(eyes=(True, False)), series=files.ROOT + ".9"
    )

    outcomes = _outcomes(slices=_head_files() + tuple(other))

    assert outcomes[files.SERIES].problem is None
    assert outcomes[files.ROOT + ".9"].problem is FaceBlockProblem.NO_EYES


def test_a_series_without_a_head_is_not_defaced():
    scan = head.axial(
        spacing=2.0, thickness=3.0, extent=((-100, 100), (-130, 110), (-60, -30))
    )

    outcome = _outcome(slices=tuple(files.ct_files(scan, head.Head(noise=0.0))))

    assert outcome.block is None
    assert outcome.problem is FaceBlockProblem.NO_EYES


def test_a_slice_that_cannot_be_read_again_leaves_the_series_undefaced():
    data = list(_head_files())
    records = {p: InstanceRecord.from_file(each) for p, each in enumerate(data)}

    outcomes = find_face_blocks(
        records, lambda position: None if position == 3 else data[position]
    )

    assert outcomes[files.SERIES].problem is SeriesProblem.UNREADABLE


def test_slices_of_more_than_one_size_are_not_one_stack():
    other = files.ct_files(
        head.axial(
            spacing=2.0, thickness=3.0, extent=((-100, 98), (-130, 110), (-60, -57))
        ),
        head.Head(noise=0.0),
    )[0]

    assert (
        _outcome(slices=_head_files()[1:] + (other,)).problem
        is SeriesProblem.NOT_ONE_STACK
    )


def test_stored_values_that_cannot_hold_air_leave_the_series_undefaced():
    # Unsigned, with an intercept of zero: -1000 has no stored value.
    unsigned = files.ct_files(_SCAN, head.Head(noise=0.0), intercept=0.0, signed=False)

    assert _outcome(slices=tuple(unsigned)).problem is SeriesProblem.AIR_NOT_STORED


def test_compressed_slices_are_not_defaced():
    compressed = []
    for each in _head_files():
        dataset = pydicom.dcmread(io.BytesIO(each))
        dataset.compress(pydicom.uid.RLELossless)
        buffer = io.BytesIO()
        dataset.save_as(buffer, enforce_file_format=True)
        compressed.append(buffer.getvalue())

    assert _outcome(slices=tuple(compressed)).problem is SeriesProblem.COMPRESSED


@pytest.mark.parametrize("kind", ["PTV", "CTV", "GTV", "PTV "])
def test_a_target_with_a_point_in_the_block_holds_the_series(kind):
    rtss = files.structure_set([(kind, files.square(_EYES_FRONT[0]))])

    outcome = _outcome(rtss)

    assert outcome.problem is SeriesProblem.TARGET_IN_BLOCK
    assert outcome.held


@pytest.mark.parametrize(
    "rois",
    [
        [("ORGAN", files.square(_EYES_FRONT[0]))],
        [("EXTERNAL", files.square((0, -90, 40), 30))],
        [("PTV", files.square((0, 0, 40)))],
        [("", files.square(_EYES_FRONT[1]))],
    ],
    ids=["organ", "external", "target-behind", "no-type"],
)
def test_other_rois_and_targets_outside_the_block_leave_the_series_defaced(rois):
    assert _outcome(files.structure_set(rois)).problem is None


def test_a_target_in_another_frame_of_reference_leaves_the_series_defaced():
    rtss = files.structure_set(
        [("PTV", files.square(_EYES_FRONT[0]))], frame=files.ROOT + ".8"
    )

    assert _outcome(rtss).problem is None


def test_a_structure_set_that_cannot_be_read_holds_the_series():
    rtss = bytearray(files.structure_set([("ORGAN", files.square((0, 0, 0)))]))
    data = list(_head_files()) + [bytes(rtss)]
    records = {p: InstanceRecord.from_file(each) for p, each in enumerate(data)}

    outcomes = find_face_blocks(
        records,
        lambda position: b"not DICOM" if position == len(data) - 1 else data[position],
    )

    assert outcomes[files.SERIES].problem is SeriesProblem.TARGET_IN_BLOCK


def test_only_slices_within_reach_of_the_top_are_searched(monkeypatch):
    monkeypatch.setattr(face_blocks, "HEAD_REACH", 60.0)

    # The top 60 mm, above z = 60, holds no eyes.
    assert _outcome().problem is FaceBlockProblem.NO_EYES


def test_counts_are_by_series_and_reason():
    counts = FaceBlockCounts()

    counts.record(
        [
            _outcome(),
            SeriesDefacing(None, FaceBlockProblem.NO_EYES),
            SeriesDefacing(None, FaceBlockProblem.NO_EYES),
            SeriesDefacing(None, SeriesProblem.TARGET_IN_BLOCK),
        ]
    )

    assert counts.defaced == 1
    assert counts.not_defaced == {
        FaceBlockProblem.NO_EYES: 2,
        SeriesProblem.TARGET_IN_BLOCK: 1,
    }


def test_a_series_has_a_block_or_a_problem():
    with pytest.raises(ValueError):
        SeriesDefacing(None, None)


def test_a_defaced_series_has_its_frame_of_reference_and_no_other_does():
    outcome = _outcome()
    held = _outcome(files.structure_set([("PTV", files.square(_EYES_FRONT[0]))]))

    assert outcome.frame == files.FRAME
    assert held.frame is None
    records = {
        position: InstanceRecord.from_file(each)
        for position, each in enumerate(_head_files())
    }
    series = next(iter(_outcomes()))
    found = face_blocks.find_defaced(
        records, {series: outcome, files.ROOT + ".9": held}
    )
    assert found.frames == {files.FRAME}
    assert found.instances == {record.sop_instance for record in records.values()}
    assert repr(found) == f"Defaced(frames=1, instances={len(records)})"
    with pytest.raises(ValueError, match="Frame of Reference UID"):
        SeriesDefacing(outcome.block, None)
    with pytest.raises(ValueError, match="Frame of Reference UID"):
        SeriesDefacing(outcome.block, None, "")
    with pytest.raises(ValueError, match="Frame of Reference UID"):
        SeriesDefacing(None, FaceBlockProblem.NO_EYES, files.FRAME)


def test_a_records_frames_are_its_own_and_its_structure_sets():
    rtss = files.structure_set(
        [("ORGAN", files.square((0, 0, 0)))], frame=files.ROOT + ".8"
    )

    assert face_blocks.frames_of(InstanceRecord.from_file(_head_files()[0])) == {
        files.FRAME
    }
    assert face_blocks.frames_of(InstanceRecord.from_file(rtss)) == {files.ROOT + ".8"}


def _defaced() -> face_blocks.Defaced:
    records = {
        position: InstanceRecord.from_file(each)
        for position, each in enumerate(_head_files())
    }
    return face_blocks.find_defaced(records, _outcomes())


def _record(data: bytes) -> InstanceRecord:
    return InstanceRecord.from_file(data)


def _frameless_structure_set() -> bytes:
    dataset = pydicom.dcmread(
        io.BytesIO(files.structure_set([("ORGAN", files.square((0, 0, 0)))]))
    )
    del dataset.ReferencedFrameOfReferenceSequence
    for roi in dataset.StructureSetROISequence:
        del roi.ReferencedFrameOfReferenceUID
    return files.written(dataset)


def _structure_set_on_slice(sop_instance: str) -> bytes:
    dataset = pydicom.dcmread(
        io.BytesIO(
            files.structure_set(
                [("ORGAN", files.square((0, 0, 0)))], frame=files.ROOT + ".8"
            )
        )
    )
    image = pydicom.Dataset()
    image.ReferencedSOPClassUID = files.CT_IMAGE_STORAGE
    image.ReferencedSOPInstanceUID = sop_instance
    dataset.ROIContourSequence[0].ContourSequence[0].ContourImageSequence = [image]
    return files.written(dataset)


def test_an_rt_instance_in_a_defaced_frame_or_naming_none_is_held():
    found = _defaced()
    in_frame = _record(files.structure_set([("ORGAN", files.square((0, 0, 0)))]))
    frameless = _record(_frameless_structure_set())

    assert face_blocks.frames_of(frameless) == frozenset()
    for iod in sorted(face_blocks.UNDEFACED_IODS):
        assert found.holds(iod, in_frame)
        assert found.holds(iod, frameless)


def test_an_rt_instance_in_another_frame_is_held_only_if_it_refers_to_a_defaced_slice():
    found = _defaced()
    (target, *_) = sorted(found.instances)
    elsewhere = _record(
        files.structure_set(
            [("ORGAN", files.square((0, 0, 0)))], frame=files.ROOT + ".8"
        )
    )
    on_slice = _record(_structure_set_on_slice(target))
    on_other = _record(_structure_set_on_slice(files.ROOT + ".99"))

    assert any(reference.target == target for reference in on_slice.references)
    assert not found.holds(face_blocks.RT_STRUCTURE_SET, elsewhere)
    assert found.holds(face_blocks.RT_STRUCTURE_SET, on_slice)
    assert not found.holds(face_blocks.RT_STRUCTURE_SET, on_other)


def test_only_rt_and_pet_instances_are_held_and_only_where_a_series_is_defaced():
    found = _defaced()
    in_frame = _record(_head_files()[0])
    frameless = _record(_frameless_structure_set())

    assert not found.holds(face_blocks.CT_IMAGE, in_frame)
    assert not found.holds("MR Image", in_frame)
    assert not found.holds(None, frameless)
    assert not face_blocks.Defaced().holds(face_blocks.RT_STRUCTURE_SET, frameless)
    assert not face_blocks.Defaced().holds("RT Dose", in_frame)


# Writing air.


def _slice_at(height: float, *, padding: int | None = None, intercept: float = -1024.0):
    scan = head.axial(
        spacing=2.0, thickness=3.0, extent=((-100, 100), (-130, 110), (height, height))
    )
    (data,) = files.ct_files(
        scan, head.Head(noise=0.0), padding=padding, intercept=intercept
    )
    dataset = pydicom.dcmread(io.BytesIO(data))
    return scan, dataset, np.asarray(dataset.pixel_array)


def test_the_block_is_written_as_air_and_the_rest_kept():
    block = _outcome().block
    scan, dataset, stored = _slice_at(20.0)

    mask = CtDefacer(block, dataset).mask(0, stored)

    points = scan.points(0)
    inside = block.contains(points)
    assert mask.value == -1000 + 1024
    assert mask.mask.shape == stored.shape
    # Nothing outside the block, and the front of each globe within it.
    assert not (mask.mask & ~inside).any()
    for x, y, _ in _EYES_FRONT:
        row, column = round((y + 130) / 2), round((x + 100) / 2)
        assert mask.mask[row, column]


def test_the_brain_within_the_skull_is_kept_in_the_block():
    block = _outcome().block
    scan, dataset, stored = _slice_at(60.0)

    mask = CtDefacer(block, dataset).mask(0, stored)

    points = scan.points(0)
    hounsfield = head.hounsfield(points, head.Head())
    brain = (hounsfield == head.BRAIN) & block.contains(points)
    assert brain.any()
    assert not (mask.mask & brain).any()
    # The forehead's skin and bone before the brain are written as air.
    forehead = block.contains(points) & np.isin(
        hounsfield, [head.SOFT_TISSUE, head.BONE]
    )
    assert forehead.any()
    assert mask.mask[forehead].all()


@pytest.mark.parametrize("guarded", [True, False])
def test_bone_around_an_orbit_keeps_no_part_of_the_eye(monkeypatch, guarded):
    if not guarded:
        monkeypatch.setattr(face_blocks, "CAVITY_FLOOR", -100.0)
    block = _outcome().block
    scan, dataset, stored = _slice_at(head.GLOBE_Z)
    points = scan.points(0)
    # A ring of bone enclosing the patient's right orbit within the slice,
    # as an orbital roof cut obliquely can.
    distance = np.hypot(points[..., 0] + head.GLOBE_X, points[..., 1] - head.GLOBE_Y)
    stored[(distance > 16) & (distance < 19)] = 1500 + 1024
    eye = np.isin(head.hounsfield(points), [head.VITREOUS, head.LENS])
    eye &= block.contains(points) & (points[..., 0] < 0)

    mask = CtDefacer(block, dataset).mask(0, stored)

    assert eye.any()
    # Without the floor, the ring would keep the front of the eye.
    assert mask.mask[eye].all() == guarded


def test_padding_in_the_block_is_kept():
    block = _outcome().block
    _, dataset, stored = _slice_at(20.0, padding=-2000)
    padded = stored == -2000

    mask = CtDefacer(block, dataset).mask(0, stored)

    assert padded.any()
    assert not (mask.mask & padded).any()


def test_a_slice_below_the_block_has_no_mask():
    block = _outcome().block
    _, dataset, stored = _slice_at(-30.0)

    assert CtDefacer(block, dataset).mask(0, stored) is None


def test_a_slice_whose_air_cannot_be_stored_is_refused():
    block = _outcome().block
    _, dataset, _ = _slice_at(20.0)
    dataset.RescaleIntercept = "0"
    dataset.PixelRepresentation = 0

    with pytest.raises(PixelDataRefused):
        CtDefacer(block, dataset)


# Malformed slices leave a series undefaced, and never stop a run.


def _changed(change, *, every=False) -> tuple[bytes, ...]:
    """The head's slices, with ``change`` made to the tenth, or to each."""
    changed = []
    for index, data in enumerate(_head_files()):
        if every or index == 10:
            dataset = pydicom.dcmread(io.BytesIO(data))
            change(dataset)
            data = files.written(dataset)
        changed.append(data)
    return tuple(changed)


def _set(keyword, value):
    def change(dataset):
        if value is None:
            del dataset[keyword]
        else:
            setattr(dataset, keyword, value)

    return change


def _raw(tag, vr, value):
    def change(dataset):
        dataset[tag] = pydicom.dataelem.RawDataElement(
            pydicom.tag.Tag(tag), vr, len(value), value, 0, False, True
        )

    return change


def _padded_limit(value):
    def change(dataset):
        dataset.PixelPaddingValue = -2000
        dataset["PixelPaddingValue"].VR = "SS"
        _raw(0x00280121, "SS", value)(dataset)

    return change


def _truncated(dataset):
    dataset.PixelData = dataset.PixelData[: len(dataset.PixelData) // 2]


def _colour(dataset):
    dataset.SamplesPerPixel = 3
    dataset.PhotometricInterpretation = "RGB"
    dataset.PlanarConfiguration = 0
    dataset.BitsAllocated = dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    dataset.PixelData = bytes(3 * dataset.Rows * dataset.Columns)


@pytest.mark.parametrize(
    "change, problem",
    [
        (_set("ImagePositionPatient", None), SeriesProblem.UNREADABLE),
        (
            _set("ImageOrientationPatient", ["1", "0", "0", "0", "1"]),
            SeriesProblem.UNREADABLE,
        ),
        (_set("PixelSpacing", ["NaN", "2"]), SeriesProblem.UNREADABLE),
        (_set("ImagePositionPatient", ["0", "inf", "0"]), SeriesProblem.UNREADABLE),
        (_set("RescaleSlope", "1e-310"), SeriesProblem.AIR_NOT_STORED),
        (_raw(0x00280120, "SS", b"\x00\x00\x00"), SeriesProblem.UNREADABLE),
        (_padded_limit(b"\x00"), SeriesProblem.UNREADABLE),
        (_truncated, SeriesProblem.UNREADABLE),
        (_colour, SeriesProblem.NOT_ONE_STACK),
    ],
    ids=[
        "no-position",
        "five-direction-cosines",
        "nan-spacing",
        "infinite-position",
        "tiny-slope",
        "short-padding-value",
        "short-padding-limit",
        "truncated-pixel-data",
        "colour",
    ],
)
def test_a_malformed_slice_leaves_its_series_undefaced(change, problem):
    assert _outcome(slices=_changed(change)).problem is problem


def test_a_series_without_a_frame_of_reference_is_not_defaced():
    slices = _changed(_set("FrameOfReferenceUID", None), every=True)

    assert _outcome(slices=slices).problem is SeriesProblem.UNREADABLE


def test_a_target_that_names_no_frame_of_reference_holds_the_series():
    def unnamed(dataset):
        dataset.StructureSetROISequence[0].ReferencedFrameOfReferenceUID = ""

    rtss = pydicom.dcmread(
        io.BytesIO(files.structure_set([("PTV", files.square(_EYES_FRONT[0]))]))
    )
    unnamed(rtss)

    assert _outcome(files.written(rtss)).problem is SeriesProblem.TARGET_IN_BLOCK


def test_a_target_in_a_structure_set_that_names_no_frame_holds_the_series():
    rtss = pydicom.dcmread(
        io.BytesIO(files.structure_set([("PTV", files.square(_EYES_FRONT[0]))]))
    )
    del rtss.ReferencedFrameOfReferenceSequence
    rtss.StructureSetROISequence[0].ReferencedFrameOfReferenceUID = ""
    data = files.written(rtss)

    assert not face_blocks.frames_of(InstanceRecord.from_file(data))
    assert _outcome(data).problem is SeriesProblem.TARGET_IN_BLOCK


def test_the_cavity_is_kept_only_above_its_floor():
    block = _outcome().block
    kept = {}
    for height in (head.GLOBE_Z + 27, head.GLOBE_Z + 33):
        scan, dataset, stored = _slice_at(height)
        points = scan.points(0)
        brain = (head.hounsfield(points) == head.BRAIN) & block.contains(points)
        mask = CtDefacer(block, dataset).mask(0, stored)
        assert brain.any()
        kept[height] = not mask.mask[brain].any()

    assert kept == {head.GLOBE_Z + 27: False, head.GLOBE_Z + 33: True}


def test_the_floor_is_above_the_higher_globe():
    block = _outcome().block
    (right, left) = block.globes
    raised = dataclasses.replace(
        block, globes=(right, (left[0], left[1], left[2] + 10))
    )
    scan, dataset, stored = _slice_at(head.GLOBE_Z + 35)
    points = scan.points(0)
    brain = (head.hounsfield(points) == head.BRAIN) & block.contains(points)

    assert not CtDefacer(block, dataset).mask(0, stored).mask[brain].any()
    assert CtDefacer(raised, dataset).mask(0, stored).mask[brain].all()


def test_a_skull_open_in_the_slice_keeps_no_brain():
    block = _outcome().block
    scan, dataset, stored = _slice_at(60.0)
    points = scan.points(0)
    # A gap through the frontal bone, at the midline.
    gap = (np.abs(points[..., 0]) < 3) & (points[..., 1] < -60)
    bone = stored >= 300 + 1024
    stored[gap & bone] = 40 + 1024
    brain = (head.hounsfield(points) == head.BRAIN) & block.contains(points)

    assert CtDefacer(block, dataset).mask(0, stored).mask[brain].all()


def test_padding_that_reads_as_bone_closes_no_ring():
    block = _outcome().block
    scan, dataset, stored = _slice_at(60.0, padding=2000)
    points = scan.points(0)
    # A frame of padding, which as Hounsfield units would be bone, around
    # the head.
    edge = np.zeros(stored.shape, dtype=bool)
    edge[[0, -1], :] = edge[:, [0, -1]] = True
    stored[edge] = 2000
    skin = (head.hounsfield(points) == head.SOFT_TISSUE) & block.contains(points)

    mask = CtDefacer(block, dataset).mask(0, stored)

    assert skin.any()
    assert mask.mask[skin].all()
