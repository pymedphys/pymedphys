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
from pymedphys._dicom.deidentify.defacing import FaceBlock, FaceBlockProblem
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


# A block of the points with y < 0 and z > 0.
_CORNER = FaceBlock((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), 0.0, ((0, 0, 0), (0, 0, 0)))
# A sagittal triangle with no vertex in that block, whose first segment and
# interior cross it.
_ACROSS = np.array([(0.0, -10.0, -1.0), (0.0, 1.0, 10.0), (0.0, 1.0, -1.0)])


def _square(y: tuple[float, float], z: float) -> np.ndarray:
    return np.array([(0.0, y[0], z), (1.0, y[0], z), (1.0, y[1], z), (0.0, y[1], z)])


def test_a_target_reaches_the_block_where_the_hull_of_its_contours_does():
    reaches = face_blocks._hull_reaches  # pylint: disable = protected-access

    assert not _CORNER.contains(_ACROSS).any()
    assert _CORNER.contains(np.array([(0.0, -4.5, 4.5), (0.0, -8 / 3, 8 / 3)])).all()
    assert reaches(_CORNER, _ACROSS)
    assert reaches(_CORNER, np.array([(5.0, 0.0, 0.0)]))
    # Two axial contours, one ahead of the plane and below the limit, the
    # other behind it and above, neither reaching the block, between which
    # a planning system's interpolation does.
    ahead, behind = _square((-10.0, -6.0), -1.0), _square((2.0, 6.0), 3.0)
    assert not _CORNER.contains(np.concatenate([ahead, behind])).any()
    assert _CORNER.contains(np.mean([ahead, behind], axis=0)).any()
    assert not reaches(_CORNER, ahead)
    assert not reaches(_CORNER, behind)
    assert reaches(_CORNER, np.concatenate([ahead, behind]))
    assert not reaches(_CORNER, np.concatenate([behind, behind - [0, 0, 4]]))
    # Whose hull passes below the block's corner.
    assert not reaches(
        _CORNER, np.concatenate([_square((-2.0, -1.0), -10.0), _square((9, 10), 1)])
    )
    assert not reaches(_CORNER, _ACROSS[:0])
    assert reaches(_CORNER, np.array([(0.0, np.nan, 50.0)]))
    # Far enough that the distances would overflow, it holds, as the same
    # segment scaled down does.
    far = np.array([(0.0, -1.5e308, -10.0), (0.0, 1.5e308, 30.0)])
    assert reaches(_CORNER, far / 1e308)
    assert reaches(_CORNER, far)
    assert reaches(_CORNER, np.array([(0.0, 2e6, -10.0)]))


def test_two_target_contours_with_the_block_between_them_hold_the_series():
    block = _outcome().block
    x, y, _ = block.origin
    ax, ay, _ = block.anterior
    globe_x = block.globes[0][0]
    corner = np.array([globe_x, y - ax * (globe_x - x) / ay, block.inferior_limit])
    ahead = np.array([0.0, 1 / ay, 0.0])
    up = np.array([0.0, 0.0, 1.0])
    below = files.square(corner + 8 * ahead - 2 * up)
    behind = files.square(corner - 8 * ahead + 4 * up)
    rtss = files.structure_set([("PTV", below)])
    # One ROI with both contours.
    data = pydicom.dcmread(io.BytesIO(rtss))
    contour = pydicom.Dataset()
    contour.ContourGeometricType = "CLOSED_PLANAR"
    contour.NumberOfContourPoints = len(behind)
    contour.ContourData = [f"{v:.6f}" for v in np.ravel(behind)]
    data.ROIContourSequence[0].ContourSequence.append(contour)

    assert not block.contains(np.concatenate([below, behind])).any()
    assert _outcome(rtss).problem is None
    assert _outcome(files.structure_set([("PTV", behind)])).problem is None
    assert _outcome(files.written(data)).problem is SeriesProblem.TARGET_IN_BLOCK


def test_a_sagittal_target_crossing_the_block_between_its_vertices_holds_the_series():
    block = _outcome().block
    x, y, _ = block.origin
    ax, ay, _ = block.anterior
    globe_x = block.globes[0][0]
    # The point on the block's plane at the right globe's x and its
    # inferior limit, and a millimetre ahead of the plane in y.
    corner = np.array([globe_x, y - ax * (globe_x - x) / ay, block.inferior_limit])
    ahead = np.array([0.0, 1 / ay, 0.0])
    up = np.array([0.0, 0.0, 1.0])
    triangle = np.array(
        [corner + 10 * ahead - up, corner - ahead + 10 * up, corner - ahead - up]
    )

    assert not block.contains(triangle).any()
    assert block.contains(corner + 4.5 * (ahead + up))
    outcome = _outcome(files.structure_set([("PTV", triangle)]))
    assert outcome.problem is SeriesProblem.TARGET_IN_BLOCK
    assert outcome.held


@pytest.mark.parametrize(
    ("rois", "held"),
    [
        ([("PTV", files.square(_EYES_FRONT[0]))], True),
        ([("PTV", files.square((0, 0, 40)))], True),
        ([("ORGAN", files.square(_EYES_FRONT[0]))], False),
    ],
    ids=["target-in-block", "target-behind", "organ"],
)
def test_a_structure_set_in_another_frame_drawn_on_the_series_slices(rois, held):
    elsewhere = files.ROOT + ".8"
    rtss = pydicom.dcmread(io.BytesIO(files.structure_set(rois, frame=elsewhere)))
    unreferenced = files.written(rtss)
    rtss.ROIContourSequence[0].ContourSequence[0].ContourImageSequence = [
        _slice_image()
    ]
    drawn = files.written(rtss)

    assert face_blocks.frames_of(InstanceRecord.from_file(drawn)) == {elsewhere}
    assert _outcome(unreferenced).problem is None
    # Its contours cannot be placed without a registration, so any target
    # in it holds the series.
    assert _outcome(drawn).problem is (SeriesProblem.TARGET_IN_BLOCK if held else None)


def _slice_image() -> pydicom.Dataset:
    image = pydicom.Dataset()
    image.ReferencedSOPClassUID = files.CT_IMAGE_STORAGE
    image.ReferencedSOPInstanceUID = InstanceRecord.from_file(
        _head_files()[0]
    ).sop_instance
    return image


def _frame_images(frame: pydicom.Dataset) -> None:
    """List one of the series' slices as a contour image of the frame."""
    series = pydicom.Dataset()
    series.SeriesInstanceUID = files.ROOT + ".9"
    series.ContourImageSequence = [_slice_image()]
    study = pydicom.Dataset()
    study.ReferencedSOPClassUID = "1.2.840.10008.3.1.2.3.1"
    study.ReferencedSOPInstanceUID = files.ROOT + ".10"
    study.RTReferencedSeriesSequence = [series]
    frame.RTReferencedStudySequence = [study]


def _mixed(tie: str, target_at=(0, 0, 40)) -> bytes:
    """A structure set with an organ in the series' frame drawn on one of
    its slices, and a target in another frame, behind the block unless
    placed elsewhere, tied to the series' slices as ``tie`` says."""
    elsewhere = files.ROOT + ".8"
    behind = files.square((0, 0, 40))
    rtss = pydicom.dcmread(
        io.BytesIO(
            files.structure_set(
                [
                    ("ORGAN", behind),
                    ("ORGAN", behind),
                    ("PTV", files.square(target_at)),
                ]
            )
        )
    )
    for roi in rtss.StructureSetROISequence[1:]:
        roi.ReferencedFrameOfReferenceUID = elsewhere
    other = pydicom.Dataset()
    other.FrameOfReferenceUID = elsewhere
    rtss.ReferencedFrameOfReferenceSequence.append(other)
    organ, other_organ, target = (
        item.ContourSequence[0] for item in rtss.ROIContourSequence
    )
    organ.ContourImageSequence = [_slice_image()]
    if tie == "target":
        target.ContourImageSequence = [_slice_image()]
    elif tie == "organ-in-its-frame":
        other_organ.ContourImageSequence = [_slice_image()]
    elif tie == "frame":
        _frame_images(other)
    return files.written(rtss)


@pytest.mark.parametrize(
    ("tie", "held"),
    [
        ("target", True),
        ("organ-in-its-frame", True),
        ("frame", True),
        ("none", False),
    ],
)
def test_a_target_in_another_frame_holds_the_series_only_if_tied_to_its_slices(
    tie, held
):
    rtss = _mixed(tie)

    assert face_blocks.frames_of(InstanceRecord.from_file(rtss)) == {
        files.FRAME,
        files.ROOT + ".8",
    }
    # A target in another frame cannot be placed without a registration, so
    # one tied to the series' slices holds it even though another ROI of
    # the set is in its frame, and one of another scan does not.
    assert _outcome(rtss).problem is (SeriesProblem.TARGET_IN_BLOCK if held else None)


def test_an_untied_target_in_another_frame_does_not_hold_the_series_from_the_block():
    # Its coordinates are of another frame, so its being where the series'
    # block would be says nothing.
    assert _outcome(_mixed("none", _EYES_FRONT[0])).problem is None
    assert _outcome(_mixed("target", _EYES_FRONT[0])).problem is (
        SeriesProblem.TARGET_IN_BLOCK
    )


def _elsewhere_only(rois) -> pydicom.Dataset:
    return pydicom.dcmread(
        io.BytesIO(files.structure_set(rois, frame=files.ROOT + ".8"))
    )


def test_a_set_in_another_frame_tied_only_by_its_frame_images_holds_the_series():
    rtss = _elsewhere_only([("PTV", files.square((0, 0, 40)))])
    _frame_images(rtss.ReferencedFrameOfReferenceSequence[0])

    assert _outcome(files.written(rtss)).problem is SeriesProblem.TARGET_IN_BLOCK


@pytest.mark.parametrize("unnamed", ["empty", "absent"])
def test_a_target_naming_no_frame_in_a_set_in_another_frame_drawn_on_the_slices(
    unnamed,
):
    rtss = _elsewhere_only([("PTV", files.square((0, 0, 40)))])
    if unnamed == "empty":
        rtss.StructureSetROISequence[0].ReferencedFrameOfReferenceUID = ""
    else:
        del rtss.StructureSetROISequence[0].ReferencedFrameOfReferenceUID
    unreferenced = files.written(rtss)
    rtss.ROIContourSequence[0].ContourSequence[0].ContourImageSequence = [
        _slice_image()
    ]

    # Its hull misses the block, and it may be in the set's frame.
    assert _outcome(unreferenced).problem is None
    assert _outcome(files.written(rtss)).problem is SeriesProblem.TARGET_IN_BLOCK


def test_a_target_naming_no_frame_tied_only_by_its_frame_images_holds_the_series():
    rtss = _elsewhere_only([("PTV", files.square((0, 0, 40)))])
    del rtss.StructureSetROISequence[0].ReferencedFrameOfReferenceUID
    unreferenced = files.written(rtss)
    _frame_images(rtss.ReferencedFrameOfReferenceSequence[0])

    assert _outcome(unreferenced).problem is None
    assert _outcome(files.written(rtss)).problem is SeriesProblem.TARGET_IN_BLOCK


def test_a_target_naming_no_frame_holds_the_series_where_another_frame_is_tied():
    # In a set of the series' frame and another, whose own list of contour
    # images ties it to the series' slices, a target behind the plane that
    # names no frame may be in the other, so it holds the series, although
    # its hull misses the block.
    rtss = pydicom.dcmread(
        io.BytesIO(files.structure_set([("PTV", files.square((0, 0, 40)))]))
    )
    rtss.StructureSetROISequence[0].ReferencedFrameOfReferenceUID = ""
    other = pydicom.Dataset()
    other.FrameOfReferenceUID = files.ROOT + ".8"
    rtss.ReferencedFrameOfReferenceSequence.append(other)
    untied = files.written(rtss)
    _frame_images(other)

    assert _outcome(untied).problem is None
    assert _outcome(files.written(rtss)).problem is SeriesProblem.TARGET_IN_BLOCK


def _several(roi: pydicom.Dataset) -> None:
    roi.ReferencedFrameOfReferenceUID = [files.FRAME, files.ROOT + ".8"]


def _not_a_uid(roi: pydicom.Dataset) -> None:
    roi.ReferencedFrameOfReferenceUID = "FRAME"


@pytest.mark.parametrize(
    "malformed",
    ["several-frames", "not-a-uid", "repeated-roi-number"],
)
def test_a_target_in_the_block_with_a_malformed_frame_holds_the_series(malformed):
    rtss = pydicom.dcmread(
        io.BytesIO(files.structure_set([("PTV", files.square(_EYES_FRONT[0]))]))
    )
    (roi,) = rtss.StructureSetROISequence
    if malformed == "several-frames":
        _several(roi)
    elif malformed == "not-a-uid":
        _not_a_uid(roi)
    else:
        # A second item for the same ROI Number, naming another frame: which
        # one the target is in cannot be told.
        repeated = pydicom.Dataset()
        repeated.ROINumber = roi.ROINumber
        repeated.ReferencedFrameOfReferenceUID = files.ROOT + ".8"
        repeated.ROIName = "R2"
        repeated.ROIGenerationAlgorithm = "MANUAL"
        rtss.StructureSetROISequence.append(repeated)

    # It may be in the series' frame, so its hull is judged, and reaches
    # the block.
    assert _outcome(files.written(rtss)).problem is SeriesProblem.TARGET_IN_BLOCK


def test_a_structure_set_naming_frames_that_are_not_uids_is_searched_as_frameless():
    rtss = pydicom.dcmread(
        io.BytesIO(files.structure_set([("PTV", files.square(_EYES_FRONT[0]))]))
    )
    rtss.ReferencedFrameOfReferenceSequence[0].FrameOfReferenceUID = "FRAME"
    _not_a_uid(rtss.StructureSetROISequence[0])
    data = files.written(rtss)

    assert face_blocks.frames_of(InstanceRecord.from_file(data)) == {"FRAME"}
    assert _outcome(data).problem is SeriesProblem.TARGET_IN_BLOCK


def test_a_malformed_frame_tied_to_the_slices_holds_the_series_from_behind():
    # The set's frame and its target's are the same label, which is not a
    # UID, and the frame's own list of contour images names one of the
    # series' slices: the target, behind the plane, may be in a frame tied
    # to the series, so the label still ties it.
    rtss = pydicom.dcmread(
        io.BytesIO(files.structure_set([("PTV", files.square((0, 0, 40)))]))
    )
    rtss.ReferencedFrameOfReferenceSequence[0].FrameOfReferenceUID = "FRAME"
    _not_a_uid(rtss.StructureSetROISequence[0])
    untied = files.written(rtss)
    _frame_images(rtss.ReferencedFrameOfReferenceSequence[0])

    assert _outcome(untied).problem is None
    assert _outcome(files.written(rtss)).problem is SeriesProblem.TARGET_IN_BLOCK


def _repeated(roi: pydicom.Dataset, frame: str) -> pydicom.Dataset:
    repeated = pydicom.Dataset()
    repeated.ROINumber = roi.ROINumber
    repeated.ReferencedFrameOfReferenceUID = frame
    repeated.ROIName = "R2"
    repeated.ROIGenerationAlgorithm = "MANUAL"
    return repeated


@pytest.mark.parametrize(
    "frame",
    [
        "empty",
        "absent",
        "not-a-uid",
        "several-frames",
        "repeated-roi-number",
        "undeclared",
    ],
)
def test_a_target_in_the_block_in_a_set_of_another_frame_holds_where_its_frame_is_unsure(
    frame,
):
    # The set declares only another frame, and is not tied to the series'
    # slices, but the target's own frame does not say that it is in that
    # frame, so it may be in the series', where its hull reaches the block.
    elsewhere = files.ROOT + ".8"
    rtss = _elsewhere_only([("PTV", files.square(_EYES_FRONT[0]))])
    (roi,) = rtss.StructureSetROISequence
    if frame == "empty":
        roi.ReferencedFrameOfReferenceUID = ""
    elif frame == "absent":
        del roi.ReferencedFrameOfReferenceUID
    elif frame == "not-a-uid":
        _not_a_uid(roi)
    elif frame == "several-frames":
        _several(roi)
    elif frame == "repeated-roi-number":
        rtss.StructureSetROISequence.append(_repeated(roi, files.ROOT + ".11"))
    else:
        # A valid UID, but not one that the set declares.
        roi.ReferencedFrameOfReferenceUID = files.ROOT + ".11"
    data = files.written(rtss)

    assert files.FRAME not in face_blocks.frames_of(InstanceRecord.from_file(data))
    assert elsewhere in face_blocks.frames_of(InstanceRecord.from_file(data))
    assert _outcome(data).problem is SeriesProblem.TARGET_IN_BLOCK


def test_a_set_of_another_frame_and_patient_is_not_searched_for_an_unsure_target():
    rtss = _elsewhere_only([("PTV", files.square(_EYES_FRONT[0]))])
    rtss.StructureSetROISequence[0].ReferencedFrameOfReferenceUID = ""
    rtss.PatientID = "H2"

    # Its frames are not the series', it is not drawn on the series'
    # slices, and it is another patient's, so its target cannot be in the
    # series' frame.
    assert _outcome(files.written(rtss)).problem is None


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
