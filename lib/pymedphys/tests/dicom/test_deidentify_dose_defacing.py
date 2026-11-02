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

"""RT Dose set to zero in a defaced CT series' face block. Every UID and
value here is invented."""

from __future__ import annotations

import functools
import io
import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import dose_defacing, face_blocks
from pymedphys._dicom.deidentify.defacing import FaceBlock
from pymedphys._dicom.deidentify.dose_defacing import (
    DOSE_FRACTION,
    DoseBlock,
    RtDoseDefacer,
    find_dose_blocks,
)
from pymedphys._dicom.deidentify.face_blocks import (
    KeptSlice,
    SeriesDefacing,
    SeriesProblem,
)
from pymedphys._dicom.deidentify.pixel_cleaning import PixelDataRefused
from pymedphys._dicom.deidentify.reasons import VisualFeaturesReason
from pymedphys._dicom.deidentify.references import InstanceRecord

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from . import _synthetic_rtdose as rtdose

# The block holds the points with y below 0 and z above 0: anterior is -y.
_BLOCK = FaceBlock((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), 0.0, ((0, 0, 0), (0, 0, 0)))
_CT_Z = (10.0, 20.0, 30.0)


def _kept_slice(z: float) -> KeptSlice:
    """An axial slice over x and y from -20 to 20 mm at 1 mm, whose kept
    pixels are those with x from -5 to 5 mm and y from -10 to -1 mm, above
    z = 15 mm."""
    x = np.arange(-20, 21)[None, :]
    y = np.arange(-20, 21)[:, None]
    kept = (np.abs(x) <= 5) & (y >= -10) & (y <= -1) & (z > 15)
    return KeptSlice((-20.0, -20.0, z), files.AXIAL, (1.0, 1.0), kept)


def _expected_kept(points: np.ndarray) -> np.ndarray:
    x, y, z = np.moveaxis(points, -1, 0)
    near = np.isin(z, _CT_Z) & (z > 15)
    return near & (np.abs(x) <= 5) & (y >= -10) & (y <= -1)


_DOSE_BLOCK = DoseBlock(_BLOCK, tuple(_kept_slice(z) for z in _CT_Z))


def _dataset(stored=None, **geometry) -> pydicom.Dataset:
    """An RT Dose over x and y from -20 to 20 mm at 2 mm, in frames at z =
    10, 20, and 30 mm, of 100 everywhere by default."""
    arguments = {
        "position": (-20.0, -20.0, 10.0),
        "spacing": (2.0, 2.0),
        "offsets": (0.0, 10.0, 20.0),
        **geometry,
    }
    frames = 3 if arguments["offsets"] is None else len(arguments["offsets"])
    if arguments["offsets"] is None:
        frames = 1
    if stored is None:
        stored = np.full((frames, 21, 21), 100, dtype=np.uint32)
    return pydicom.dcmread(io.BytesIO(files.dose(stored, **arguments)))


def _masks(dataset: pydicom.Dataset, dose: DoseBlock = _DOSE_BLOCK):
    defacer = RtDoseDefacer(dose, dataset)
    stored = dataset.pixel_array.reshape(-1, dataset.Rows, dataset.Columns)
    masks = []
    for frame, values in enumerate(stored):
        mask = defacer.mask(frame, values)
        masks.append(np.zeros(values.shape, dtype=bool) if mask is None else mask.mask)
        assert mask is None or (mask.frame, mask.value) == (frame, 0)
    return np.array(masks), defacer


def _expected(dataset: pydicom.Dataset) -> np.ndarray:
    points = rtdose.voxel_positions(dataset)
    return _BLOCK.contains(points) & ~_expected_kept(points)


def test_relative_frame_offsets_set_the_block_less_the_kept_brain_to_zero():
    dataset = _dataset()

    masks, defacer = _masks(dataset)

    assert np.array_equal(masks, _expected(dataset))
    # The kept brain is in the frames at 20 and 30 mm, which the block
    # otherwise covers, so it is set to zero around it only.
    assert (
        masks.any()
        and (~masks & _BLOCK.contains(rtdose.voxel_positions(dataset))).any()
    )
    # 100 is the grid's greatest dose as well as that in the block.
    assert defacer.held is VisualFeaturesReason.DOSE_IN_FACE_BLOCK


def test_absolute_frame_offsets_on_an_axial_grid_give_the_same_region():
    relative = _dataset()
    absolute = _dataset(offsets=(10.0, 20.0, 30.0))

    assert np.array_equal(_masks(absolute)[0], _masks(relative)[0])


def test_a_single_frame_without_offsets_is_placed_at_its_position():
    dataset = _dataset(position=(-20.0, -20.0, 20.0), offsets=None)

    masks, _ = _masks(dataset)

    points = rtdose.voxel_positions(
        _dataset(position=(-20.0, -20.0, 20.0), offsets=(0.0,))
    )
    assert np.array_equal(masks, _BLOCK.contains(points) & ~_expected_kept(points))


@pytest.mark.parametrize("orientation", ["FFS", "HFP", "HFDL"])
def test_any_orientation_with_relative_offsets_is_placed_by_its_direction_cosines(
    orientation,
):
    dataset = _dataset(
        position=(0.0, 0.0, 10.0),
        orientation=rtdose.ORIENTATIONS[orientation],
        offsets=(0.0, 10.0, 20.0),
    )
    # Where the normal points inferior, the frames go down from 10 mm.
    masks, _ = _masks(dataset)

    assert np.array_equal(masks, _expected(dataset))


def test_direction_cosines_rounded_to_six_places_are_accepted():
    # An oblique grid as a system writes it, its cosines rounded, so that
    # each vector's length and their dot product are off by about 1e-7.
    dataset = _dataset(
        position=(0.0, -40.0, 10.0),
        orientation=(0.707107, 0.707107, 0.0, -0.707107, 0.707107, 0.0),
        offsets=(0.0, 10.0, 20.0),
    )

    masks, _ = _masks(dataset)

    # The voxels lie off the slices' pixels and, by the normal's length, a
    # few micrometres off their planes, so each is kept by the pixel and
    # slice nearest it.
    points = rtdose.voxel_positions(dataset)
    kept = _expected_kept(np.rint(points))
    assert masks.any() and kept.any()
    assert np.array_equal(masks, _BLOCK.contains(points) & ~kept)


def test_dose_beyond_the_slices_is_not_kept():
    # Frames at 30 and 40 mm: the slices are 10 mm apart, so 40 mm is beyond
    # their reach, and nothing there is kept.
    dataset = _dataset(position=(-20.0, -20.0, 30.0), offsets=(0.0, 10.0))

    masks, _ = _masks(dataset)

    points = rtdose.voxel_positions(dataset)
    assert np.array_equal(masks[1], _BLOCK.contains(points[1]))
    assert not np.array_equal(masks[0], _BLOCK.contains(points[0]))


def test_a_single_slice_reaches_half_its_largest_pixel_spacing():
    dose = DoseBlock(_BLOCK, (_kept_slice(20.0),))
    points = np.array([(0.0, -5.0, 20.4), (0.0, -5.0, 20.6), (0.0, -5.0, 19.5)])

    assert dose.kept(points).tolist() == [True, False, True]


def test_the_nearest_pixel_of_the_nearest_slice_decides():
    # 24.9 mm is nearer the slice at 20 mm, whose pixel at (5, -1) is kept;
    # (5.6, -1) is nearest (6, -1), which is not; (5.4, -0.6) is nearest
    # (5, -1) and (5.4, -0.4) nearest (5, 0) of the slice at 30 mm; and
    # 14.9 mm is nearer the slice at 10 mm, which keeps nothing.
    points = np.array(
        [
            (5.0, -1.0, 24.9),
            (5.6, -1.0, 24.9),
            (5.4, -0.6, 25.1),
            (5.4, -0.4, 25.1),
            (0.0, -5.0, 14.9),
        ]
    )

    assert _DOSE_BLOCK.kept(points).tolist() == [True, False, True, False, False]


def test_a_point_outside_every_slice_is_not_kept():
    assert not _DOSE_BLOCK.kept(np.array([(100.0, -5.0, 20.0)])).any()
    assert not DoseBlock(_BLOCK, ()).kept(np.array([(0.0, -5.0, 20.0)])).any()


def _stored(in_block: int, elsewhere: int = 100, kept: int | None = None):
    dataset = _dataset()
    points = rtdose.voxel_positions(dataset)
    stored = np.full(points.shape[:-1], elsewhere, dtype=np.uint32)
    stored[_expected(dataset)] = in_block
    if kept is not None:
        stored[_BLOCK.contains(points) & _expected_kept(points)] = kept
    return stored


@pytest.mark.parametrize(
    ("in_block", "kept", "held"),
    [
        (round(DOSE_FRACTION * 100), None, None),
        (round(DOSE_FRACTION * 100) + 1, None, VisualFeaturesReason.DOSE_IN_FACE_BLOCK),
        (0, None, None),
        # Dose in the kept brain is not set to zero, so does not count.
        (1, 100, None),
    ],
)
def test_dose_set_to_zero_is_held_only_above_the_fraction_of_the_grids_greatest(
    in_block, kept, held
):
    _, defacer = _masks(_dataset(_stored(in_block, kept=kept)))

    assert defacer.held is held


def test_a_negative_stored_value_holds_the_grid_as_not_set_to_zero():
    stored = _stored(1).astype(np.int32)
    stored[0, 0, 0] = -1

    _, defacer = _masks(_dataset(stored))

    assert defacer.held is VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME


def _without(keyword: str) -> pydicom.Dataset:
    dataset = _dataset()
    del dataset[keyword]
    return dataset


def _with(**values) -> pydicom.Dataset:
    dataset = _dataset()
    for keyword, value in values.items():
        setattr(dataset, keyword, value)
    return dataset


@pytest.mark.parametrize(
    "dataset",
    [
        # Absolute offsets are defined only for this orientation.
        _dataset(orientation=rtdose.ORIENTATIONS["FFS"], offsets=(10.0, 20.0, 30.0)),
        # The first absolute offset is not the position's z.
        _dataset(offsets=(11.0, 21.0, 31.0)),
        _without("PixelSpacing"),
        _without("ImagePositionPatient"),
        _without("ImageOrientationPatient"),
        # More than one frame needs the vector.
        _without("GridFrameOffsetVector"),
        _with(GridFrameOffsetVector=["0", "10"]),
        _with(PixelSpacing=["0", "2"]),
        _with(PixelSpacing=["1e999", "2"]),
        _with(ImagePositionPatient=["0", "0"]),
        _with(ImageOrientationPatient=["1", "0", "0", "0", "1"]),
        # PS3.3 C.7.6.2.1.1 requires two orthogonal unit vectors.
        _with(ImageOrientationPatient=["0"] * 6),
        _with(ImageOrientationPatient=["2", "0", "0", "0", "1", "0"]),
        _with(ImageOrientationPatient=["1", "0", "0", "0", "1.001", "0"]),
        _with(ImageOrientationPatient=["1", "0", "0", "0.6", "0.8", "0"]),
        # Finite but too far to place, which would put the block elsewhere.
        _with(PixelSpacing=["1e300", "1e300"]),
        _with(GridFrameOffsetVector=["0", "7e299", "1.4e300"]),
        _with(ImagePositionPatient=["1e300", "0", "0"]),
        # A frame placed beyond the bound, though each value is within it.
        _dataset(position=(-20.0, -20.0, 10.0), offsets=(0.0, 10.0, 1e6)),
        _with(SamplesPerPixel=3),
    ],
    ids=[
        "absolute-oblique",
        "absolute-elsewhere",
        "no-spacing",
        "no-position",
        "no-orientation",
        "no-offsets",
        "too-few-offsets",
        "zero-spacing",
        "infinite-spacing",
        "short-position",
        "five-cosines",
        "zero-cosines",
        "non-unit-cosines",
        "nearly-unit-cosines",
        "non-orthogonal-cosines",
        "huge-spacing",
        "huge-offsets",
        "huge-position",
        "frame-too-far",
        "colour",
    ],
)
def test_a_grid_that_cannot_be_placed_is_refused(dataset):
    with pytest.raises(PixelDataRefused):
        RtDoseDefacer(_DOSE_BLOCK, dataset)


def test_direction_cosines_that_are_not_numbers_are_refused():
    # pylint: disable = protected-access
    with pytest.raises(ValueError):
        dose_defacing._check_directions((math.nan,) * 6)


def test_the_reprs_show_nothing_of_the_grid():
    assert repr(_DOSE_BLOCK) == "DoseBlock(slices=3)"
    assert repr(RtDoseDefacer(_DOSE_BLOCK, _dataset())) == "RtDoseDefacer()"


# The analytic head, coarse, for the blocks found from files.
_SCAN = head.axial(
    spacing=2.5, thickness=5.0, extent=((-100, 100), (-130, 110), (-30, 110))
)


@functools.cache
def _head_files(series: str = files.SERIES, frame: str = files.FRAME):
    return tuple(
        files.ct_files(_SCAN, head.Head(noise=0.0), series=series, frame=frame)
    )


def _grid(frame: str = files.FRAME, instance: str = files.ROOT + ".6.1") -> bytes:
    return files.dose(
        np.ones((2, 2, 2), dtype=np.uint32),
        position=(0.0, 0.0, 0.0),
        spacing=(1.0, 1.0),
        offsets=(0.0, 1.0),
        frame=frame,
        instance=instance,
    )


def _dose_blocks(*data: bytes, outcomes=None) -> dict[str, DoseBlock]:
    records = {
        position: InstanceRecord.from_file(each) for position, each in enumerate(data)
    }

    def read(position):
        return data[position]

    if outcomes is None:
        outcomes = face_blocks.find_face_blocks(records, read)
    return find_dose_blocks(records, read, outcomes)


def test_a_defaced_series_gives_its_frame_a_block_with_the_cavity_kept():
    slices = _head_files()

    blocks = _dose_blocks(*slices, _grid())

    assert list(blocks) == [files.FRAME]
    found = blocks[files.FRAME]
    assert found.slices and all(each.kept.dtype == bool for each in found.slices)
    # The brain above the floor is kept, and the eyes are not.
    floor = head.GLOBE_Z + face_blocks.CAVITY_FLOOR
    brain = np.array([(0.0, -65.0, floor + 10.0)])
    eye = np.array([(head.GLOBE_X, head.GLOBE_Y - 5.0, head.GLOBE_Z)])
    assert found.block.contains(brain).all() and found.block.contains(eye).all()
    assert found.kept(brain).all()
    assert not found.kept(eye).any()


def test_no_block_without_a_dose_in_the_frame_or_for_one_naming_none():
    slices = _head_files()
    frameless = pydicom.dcmread(io.BytesIO(_grid()))
    del frameless.FrameOfReferenceUID

    assert not _dose_blocks(*slices)
    assert not _dose_blocks(*slices, _grid(frame=files.ROOT + ".9"))
    assert not _dose_blocks(*slices, files.written(frameless))


def test_no_block_where_two_series_are_defaced_in_the_frame():
    first = _head_files()
    second = _head_files(series=files.ROOT + ".7")

    assert not _dose_blocks(*first, *second, _grid())


def test_no_block_for_a_frame_whose_series_is_not_defaced():
    slices = _head_files()
    records = {
        position: InstanceRecord.from_file(each)
        for position, each in enumerate((*slices, _grid()))
    }
    outcomes = {files.SERIES: SeriesDefacing(None, SeriesProblem.UNREADABLE)}

    assert not find_dose_blocks(records, lambda p: None, outcomes)


def test_no_block_where_a_slice_can_no_longer_be_read():
    slices = _head_files()
    data = (*slices, _grid())
    records = {
        position: InstanceRecord.from_file(each) for position, each in enumerate(data)
    }
    outcomes = face_blocks.find_face_blocks(records, lambda p: data[p])

    def read(position):
        return None if position == len(slices) - 1 else data[position]

    assert not find_dose_blocks(records, read, outcomes)


def test_the_module_names_the_dose_iod_as_the_tables_do():
    assert dose_defacing.RT_DOSE in face_blocks.UNDEFACED_IODS


def _referring(instance: str) -> InstanceRecord:
    dataset = pydicom.dcmread(io.BytesIO(_grid()))
    image = pydicom.Dataset()
    image.ReferencedSOPClassUID = files.CT_IMAGE_STORAGE
    image.ReferencedSOPInstanceUID = instance
    dataset.ReferencedInstanceSequence = [image]
    return InstanceRecord.from_file(files.written(dataset))


def test_a_dose_set_to_zero_is_held_only_if_it_refers_to_another_defaced_series():
    own = _head_files()
    other = _head_files(series=files.ROOT + ".7", frame=files.ROOT + ".8")
    data = (*own, *other)
    records = {
        position: InstanceRecord.from_file(each) for position, each in enumerate(data)
    }
    outcomes = face_blocks.find_face_blocks(records, lambda p: data[p])
    defaced = face_blocks.find_defaced(records, outcomes)
    block = _dose_blocks(*own, _grid())[files.FRAME]
    mine = records[0].sop_instance
    theirs = records[len(own)].sop_instance

    assert mine in block.instances and theirs not in block.instances
    assert {mine, theirs} <= defaced.instances
    assert not block.holds(defaced, InstanceRecord.from_file(_grid()))
    assert not block.holds(defaced, _referring(mine))
    assert block.holds(defaced, _referring(theirs))
    assert not block.holds(defaced, _referring(files.ROOT + ".99"))
