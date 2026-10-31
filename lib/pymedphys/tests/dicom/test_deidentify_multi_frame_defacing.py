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

"""Enhanced CT, Legacy Converted Enhanced CT, Enhanced PET, and Legacy
Converted Enhanced PET instances of the analytic head, defaced as its
single-frame CT and PET slices are, each frame placed and rescaled by its
functional groups. Every UID and value here is invented."""

from __future__ import annotations

import copy
import functools
import io

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify.defacing import FaceBlockProblem
from pymedphys._dicom.deidentify.dose_defacing import find_dose_blocks
from pymedphys._dicom.deidentify.face_blocks import (
    RT_STRUCTURE_SET,
    CtDefacer,
    SeriesProblem,
    find_defaced,
    find_face_blocks,
    kept_slices,
)
from pymedphys._dicom.deidentify.pixel_cleaning import PixelDataRefused
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.region_defacing import PetDefacer

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files

# As the face block tests' head, coarse to keep the files small.
_SCAN = head.axial(
    spacing=2.0, thickness=3.0, extent=((-100, 100), (-130, 110), (-60, 120))
)
_MULTI_FRAME_CT = (
    files.ENHANCED_CT_IMAGE_STORAGE,
    files.LEGACY_CONVERTED_ENHANCED_CT_IMAGE_STORAGE,
)
_MULTI_FRAME_PET = (
    files.ENHANCED_PET_IMAGE_STORAGE,
    files.LEGACY_CONVERTED_ENHANCED_PET_IMAGE_STORAGE,
)
_ENHANCED = files.ROOT + ".6.1"
# PET slices over the head, at 4 mm, below and above the floor of the kept
# brain and through the block's lower edge.
_PET_Z = (6.0, 20.0, 40.0, 70.0, 100.0)
_PET_POSITION = (-100.0, -130.0)
_PET_SPACING = (4.0, 4.0)
_PET_SHAPE = (61, 51)


@functools.cache
def _slices() -> tuple[bytes, ...]:
    return tuple(files.ct_files(_SCAN, head.Head(noise=0.0)))


def _outcomes(*data: bytes) -> dict:
    records = {
        position: InstanceRecord.from_file(each) for position, each in enumerate(data)
    }
    return find_face_blocks(records, lambda position: data[position])


def _outcome(*data: bytes):
    (outcome,) = list(_outcomes(*data).values())
    return outcome


@functools.cache
def _single():
    return _outcome(*_slices())


def _dataset(data: bytes) -> pydicom.Dataset:
    return pydicom.dcmread(io.BytesIO(data))


def _changed(data: bytes, change) -> bytes:
    """The file with ``change`` applied to its data set."""
    dataset = _dataset(data)
    change(dataset)
    return files.written(dataset)


@pytest.mark.parametrize("sop_class", _MULTI_FRAME_CT)
def test_a_multi_frame_ct_instance_has_the_face_block_of_its_slices(sop_class):
    single = _single()

    outcome = _outcome(files.multi_frame(_slices(), sop_class=sop_class))

    assert single.problem is None
    assert outcome.problem is None
    assert outcome.block == single.block
    assert outcome.frame == files.FRAME


@pytest.mark.parametrize(
    "shared",
    [
        (),
        (
            "PlaneOrientationSequence",
            "PixelMeasuresSequence",
            "PixelValueTransformationSequence",
        ),
        ("PixelValueTransformationSequence",),
    ],
    ids=["per-frame", "shared", "rescale-shared"],
)
def test_frames_placed_by_per_frame_or_shared_groups_alike_give_the_block(shared):
    outcome = _outcome(files.multi_frame(_slices(), shared=shared))

    assert outcome.block == _single().block


def test_frames_in_any_order_give_the_block():
    outcome = _outcome(files.multi_frame(_slices()[::-1]))

    assert outcome.problem is None
    np.testing.assert_allclose(outcome.block.globes, _single().block.globes)
    np.testing.assert_allclose(outcome.block.origin, _single().block.origin)
    assert outcome.block.inferior_limit == pytest.approx(_single().block.inferior_limit)


def test_a_series_of_several_instances_of_either_kind_gives_the_block():
    slices = _slices()
    data = (
        files.multi_frame(slices[:20], instance=files.ROOT + ".6.1"),
        files.multi_frame(
            slices[20:40],
            sop_class=files.LEGACY_CONVERTED_ENHANCED_CT_IMAGE_STORAGE,
            instance=files.ROOT + ".6.2",
        ),
        *slices[40:],
    )

    outcome = _outcome(*data)

    assert outcome.block == _single().block


def _rescaled(intercept: float) -> tuple[bytes, ...]:
    return tuple(files.ct_files(_SCAN, head.Head(noise=0.0), intercept=intercept))


@functools.cache
def _alternating() -> tuple[bytes, ...]:
    """The head's slices, every other one stored with Rescale Intercept
    -1000 rather than -1024."""
    other = _rescaled(-1000.0)
    return tuple(
        other[index] if index % 2 else each for index, each in enumerate(_slices())
    )


def test_each_frame_is_rescaled_by_its_own_group():
    data = files.multi_frame(_alternating(), shared=("PlaneOrientationSequence",))
    dataset = _dataset(data)
    block = _single().block

    outcome = _outcome(data)
    masks = [
        CtDefacer(block, dataset).mask(index, stored)
        for index, stored in enumerate(dataset.pixel_array)
    ]

    assert outcome.block == block
    airs = {mask.value for index, mask in enumerate(masks) if mask and index % 2}
    assert airs == {0}
    airs = {mask.value for index, mask in enumerate(masks) if mask and not index % 2}
    assert airs == {24}


@pytest.mark.parametrize("sop_class", _MULTI_FRAME_CT)
def test_each_frame_is_written_as_air_as_its_slice_would_be(sop_class):
    block = _single().block
    dataset = _dataset(files.multi_frame(_slices(), sop_class=sop_class))
    defacer = CtDefacer(block, dataset)

    reached = 0
    for index, (stored, data) in enumerate(zip(dataset.pixel_array, _slices())):
        expected = CtDefacer(block, _dataset(data)).mask(0, stored)
        found = defacer.mask(index, stored)
        assert (found is None) == (expected is None), index
        if expected is not None:
            reached += 1
            assert found.frame == index
            assert found.value == expected.value
            np.testing.assert_array_equal(found.mask, expected.mask)
    assert reached > 0


def test_a_multi_frame_series_keeps_the_brain_of_its_slices():
    block = _single().block
    data = files.multi_frame(_slices())

    found = kept_slices(block, [0], lambda _: data)
    expected = kept_slices(block, range(len(_slices())), lambda p: _slices()[p])

    assert len(found) == len(expected) > 0
    for one, other in zip(found, expected):
        assert one.position == other.position
        assert one.orientation == other.orientation
        assert one.spacing == other.spacing
        np.testing.assert_array_equal(one.kept, other.kept)


def test_a_multi_frame_series_is_defaced_by_its_instance():
    data = files.multi_frame(_slices())
    records = {0: InstanceRecord.from_file(data)}

    defaced = find_defaced(records, _outcomes(data))

    assert defaced.frames == frozenset({files.FRAME})
    assert defaced.instances == frozenset({_ENHANCED})


def _organ() -> bytes:
    return files.structure_set([("ORGAN", files.square((0.0, 40.0, 0.0)))])


def test_a_multi_frame_series_gives_its_frame_the_block_of_its_slices():
    def blocks(*data: bytes):
        records = {p: InstanceRecord.from_file(each) for p, each in enumerate(data)}

        def read(position: int) -> bytes:
            return data[position]

        outcomes = find_face_blocks(records, read)
        return find_dose_blocks(records, read, outcomes, (RT_STRUCTURE_SET,))

    found = blocks(files.multi_frame(_slices()), _organ())[files.FRAME]
    expected = blocks(*_slices(), _organ())[files.FRAME]

    assert found.block == expected.block
    assert found.instances == frozenset({_ENHANCED})
    assert len(found.slices) == len(expected.slices) > 0
    for one, other in zip(found.slices, expected.slices):
        np.testing.assert_array_equal(one.kept, other.kept)


def _in_both(dataset: pydicom.Dataset) -> None:
    for item in dataset.PerFrameFunctionalGroupsSequence:
        item.PlaneOrientationSequence = copy.deepcopy(
            dataset.SharedFunctionalGroupsSequence[0].PlaneOrientationSequence
        )


def _without_rescale(dataset: pydicom.Dataset) -> None:
    del dataset.SharedFunctionalGroupsSequence[0].PixelValueTransformationSequence


def _one_item_short(dataset: pydicom.Dataset) -> None:
    dataset.PerFrameFunctionalGroupsSequence = list(
        dataset.PerFrameFunctionalGroupsSequence
    )[:-1]


def _two_items(dataset: pydicom.Dataset) -> None:
    groups = dataset.SharedFunctionalGroupsSequence[0]
    groups.PixelMeasuresSequence = [
        groups.PixelMeasuresSequence[0],
        copy.deepcopy(groups.PixelMeasuresSequence[0]),
    ]


def _no_spacing(dataset: pydicom.Dataset) -> None:
    del dataset.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing


def _no_position(dataset: pydicom.Dataset) -> None:
    del dataset.PerFrameFunctionalGroupsSequence[3].PlanePositionSequence


def _no_slope(dataset: pydicom.Dataset) -> None:
    group = dataset.SharedFunctionalGroupsSequence[0]
    del group.PixelValueTransformationSequence[0].RescaleSlope


def _of_mr(dataset: pydicom.Dataset) -> None:
    dataset.SOPClassUID = "1.2.840.10008.5.1.4.1.1.4.1"  # Enhanced MR Image


@pytest.mark.parametrize(
    "change",
    [
        _in_both,
        _without_rescale,
        _one_item_short,
        _two_items,
        _no_spacing,
        _no_position,
        _no_slope,
    ],
    ids=lambda change: change.__name__.strip("_"),
)
def test_frames_whose_groups_cannot_be_read_leave_the_series_undefaced(change):
    data = _changed(files.multi_frame(_slices()), change)

    assert _outcome(data).problem is SeriesProblem.UNREADABLE
    with pytest.raises(PixelDataRefused):
        CtDefacer(_single().block, _dataset(data))


def test_an_instance_of_another_iod_is_refused_by_the_ct_defacer():
    data = _changed(files.multi_frame(_slices()), _of_mr)

    assert not _outcomes(data)
    with pytest.raises(PixelDataRefused):
        CtDefacer(_single().block, _dataset(data))


def test_a_frame_without_its_rescale_type_leaves_the_series_undefaced():
    data = files.multi_frame(_slices(), rescale_type=None)

    assert _outcome(data).problem is SeriesProblem.UNREADABLE


@pytest.mark.parametrize("units", ["US", "MGML", "10^-2CM2/G"])
def test_frames_of_other_units_than_hounsfield_leave_the_series_undefaced(units):
    data = files.multi_frame(_slices(), rescale_type=units)

    assert _outcome(data).problem is SeriesProblem.NOT_HOUNSFIELD
    with pytest.raises(PixelDataRefused):
        CtDefacer(_single().block, _dataset(data))


def test_one_frame_of_other_units_leaves_the_series_undefaced():
    data = _changed(
        files.multi_frame(_slices(), shared=()),
        lambda dataset: setattr(
            dataset.PerFrameFunctionalGroupsSequence[
                5
            ].PixelValueTransformationSequence[0],
            "RescaleType",
            "US",
        ),
    )

    assert _outcome(data).problem is SeriesProblem.NOT_HOUNSFIELD


def _typed(units: str):
    def change(dataset: pydicom.Dataset) -> None:
        dataset.RescaleType = units

    return change


@pytest.mark.parametrize("units", ["US", "MGML"])
def test_ct_images_of_other_units_than_hounsfield_are_not_defaced(units):
    slices = tuple(_changed(each, _typed(units)) for each in _slices())

    assert _outcome(*slices).problem is SeriesProblem.NOT_HOUNSFIELD


def test_ct_images_whose_rescale_type_is_hounsfield_units_are_defaced():
    slices = tuple(_changed(each, _typed("HU")) for each in _slices())

    assert _outcome(*slices).block == _single().block


def test_frames_at_one_position_are_not_one_stack_for_the_finder():
    # Every frame at the first's position, as two phases of one stack can
    # put two.
    data = files.multi_frame(
        _slices(),
        shared=(
            "PlanePositionSequence",
            "PlaneOrientationSequence",
            "PixelMeasuresSequence",
            "PixelValueTransformationSequence",
        ),
    )

    assert _outcome(data).problem is FaceBlockProblem.NOT_ALONG_PATIENT_AXES


def test_frames_of_another_size_or_frame_of_reference_are_not_one_stack():
    other = files.ct_files(_SCAN, head.Head(noise=0.0), frame=files.ROOT + ".9")

    assert (
        _outcome(files.multi_frame(_slices()[:30]), *other[30:]).problem
        is SeriesProblem.NOT_ONE_STACK
    )


def test_a_compressed_multi_frame_instance_is_not_defaced():
    dataset = _dataset(files.multi_frame(_slices()))
    dataset.compress(pydicom.uid.RLELossless)

    assert _outcome(files.written(dataset)).problem is SeriesProblem.COMPRESSED


def test_a_ct_image_of_two_frames_is_not_one_stack():
    def doubled(dataset: pydicom.Dataset) -> None:
        dataset.NumberOfFrames = 2
        dataset.PixelData = dataset.PixelData * 2

    slices = (_changed(_slices()[0], doubled), *_slices()[1:])

    assert _outcome(*slices).problem is SeriesProblem.NOT_ONE_STACK


def test_a_multi_frame_instance_whose_frames_cannot_be_decoded_is_unreadable():
    def short(dataset: pydicom.Dataset) -> None:
        dataset.PixelData = dataset.PixelData[: len(dataset.PixelData) // 2]

    data = _changed(files.multi_frame(_slices()), short)

    assert _outcome(data).problem is SeriesProblem.UNREADABLE


def _pet_uptake(z: float) -> np.ndarray:
    rows, columns = _PET_SHAPE
    x = _PET_POSITION[0] + _PET_SPACING[1] * np.arange(columns)[None, :]
    y = _PET_POSITION[1] + _PET_SPACING[0] * np.arange(rows)[:, None]
    x, y = np.broadcast_arrays(x, y)
    points = np.stack([x, y, np.full(x.shape, z)], axis=-1)
    return np.where(head.hounsfield(points) > head.AIR, 100, 0)


@functools.cache
def _pet_slices() -> tuple[bytes, ...]:
    return tuple(
        files.pet(
            _pet_uptake(z),
            position=(*_PET_POSITION, z),
            spacing=_PET_SPACING,
            instance=f"{files.ROOT}.7.{index + 1}",
        )
        for index, z in enumerate(_PET_Z)
    )


@functools.cache
def _region():
    data = (*_slices(), _organ())
    records = {p: InstanceRecord.from_file(each) for p, each in enumerate(data)}

    def read(position: int) -> bytes:
        return data[position]

    outcomes = find_face_blocks(records, read)
    return find_dose_blocks(records, read, outcomes, (RT_STRUCTURE_SET,))[files.FRAME]


def _pet_frames(sop_class: str, **options) -> bytes:
    return files.multi_frame(
        _pet_slices(), sop_class=sop_class, rescale_type="BQML", **options
    )


@pytest.mark.parametrize("sop_class", _MULTI_FRAME_PET)
@pytest.mark.parametrize("shared", [(), ("PlaneOrientationSequence",)])
def test_each_pet_frame_is_set_to_zero_activity_as_its_slice_would_be(
    sop_class, shared
):
    dataset = _dataset(_pet_frames(sop_class, shared=shared))
    defacer = PetDefacer(_region(), dataset)

    reached = 0
    for index, (stored, data) in enumerate(zip(dataset.pixel_array, _pet_slices())):
        expected = PetDefacer(_region(), _dataset(data)).mask(0, stored)
        found = defacer.mask(index, stored)
        assert (found is None) == (expected is None), index
        if expected is not None:
            reached += 1
            assert found.frame == index
            assert found.value == expected.value == 0
            np.testing.assert_array_equal(found.mask, expected.mask)
    assert reached > 0
    assert defacer.held is None


def test_each_pet_frame_is_set_to_its_own_zero_activity():
    def rescaled(dataset: pydicom.Dataset) -> None:
        group = dataset.PerFrameFunctionalGroupsSequence[1]
        item = group.PixelValueTransformationSequence[0]
        item.RescaleSlope = "2"
        item.RescaleIntercept = "-100"

    data = _changed(_pet_frames(files.ENHANCED_PET_IMAGE_STORAGE, shared=()), rescaled)
    dataset = _dataset(data)
    defacer = PetDefacer(_region(), dataset)

    masks = [
        defacer.mask(index, stored) for index, stored in enumerate(dataset.pixel_array)
    ]

    assert masks[1] is not None and masks[1].value == 50
    assert {mask.value for i, mask in enumerate(masks) if mask and i != 1} == {0}


def test_a_pet_frame_keeps_pixel_padding():
    def padded(dataset: pydicom.Dataset) -> None:
        dataset.PixelPaddingValue = 100
        dataset["PixelPaddingValue"].VR = "US"

    dataset = _dataset(_changed(_pet_frames(files.ENHANCED_PET_IMAGE_STORAGE), padded))
    defacer = PetDefacer(_region(), dataset)

    for index, stored in enumerate(dataset.pixel_array):
        mask = defacer.mask(index, stored)
        if mask is not None:
            assert not (stored[mask.mask] == 100).any()


def _pet_zero_not_stored(dataset: pydicom.Dataset) -> None:
    group = dataset.PerFrameFunctionalGroupsSequence[2]
    group.PixelValueTransformationSequence[0].RescaleIntercept = "10"


def _pet_not_unit(dataset: pydicom.Dataset) -> None:
    group = dataset.SharedFunctionalGroupsSequence[0]
    group.PlaneOrientationSequence[0].ImageOrientationPatient = [2, 0, 0, 0, 1, 0]


def _pet_in_both(dataset: pydicom.Dataset) -> None:
    for item in dataset.PerFrameFunctionalGroupsSequence:
        item.PlaneOrientationSequence = copy.deepcopy(
            dataset.SharedFunctionalGroupsSequence[0].PlaneOrientationSequence
        )


def _pet_without_rescale(dataset: pydicom.Dataset) -> None:
    for item in dataset.PerFrameFunctionalGroupsSequence:
        del item.PixelValueTransformationSequence


def _pet_one_item_short(dataset: pydicom.Dataset) -> None:
    dataset.PerFrameFunctionalGroupsSequence = list(
        dataset.PerFrameFunctionalGroupsSequence
    )[:-1]


def _pet_of_ct(dataset: pydicom.Dataset) -> None:
    dataset.SOPClassUID = files.ENHANCED_CT_IMAGE_STORAGE


def _pet_zero_slope(dataset: pydicom.Dataset) -> None:
    group = dataset.PerFrameFunctionalGroupsSequence[0]
    group.PixelValueTransformationSequence[0].RescaleSlope = "0"


@pytest.mark.parametrize(
    "change",
    [
        _pet_zero_not_stored,
        _pet_not_unit,
        _pet_in_both,
        _pet_without_rescale,
        _pet_one_item_short,
        _pet_of_ct,
        _pet_zero_slope,
    ],
    ids=lambda change: change.__name__.removeprefix("_pet_"),
)
def test_a_pet_frame_that_cannot_be_placed_or_cleaned_refuses_the_image(change):
    data = _changed(
        _pet_frames(
            files.ENHANCED_PET_IMAGE_STORAGE, shared=("PlaneOrientationSequence",)
        ),
        change,
    )

    with pytest.raises(PixelDataRefused):
        PetDefacer(_region(), _dataset(data))


def test_a_pet_image_of_two_frames_is_refused():
    def doubled(dataset: pydicom.Dataset) -> None:
        dataset.NumberOfFrames = 2
        dataset.PixelData = dataset.PixelData * 2

    with pytest.raises(PixelDataRefused):
        PetDefacer(_region(), _dataset(_changed(_pet_slices()[0], doubled)))


def test_a_compressed_multi_frame_pet_is_refused():
    dataset = _dataset(_pet_frames(files.ENHANCED_PET_IMAGE_STORAGE))
    dataset.compress(pydicom.uid.RLELossless)

    with pytest.raises(PixelDataRefused):
        PetDefacer(_region(), _dataset(files.written(dataset)))
