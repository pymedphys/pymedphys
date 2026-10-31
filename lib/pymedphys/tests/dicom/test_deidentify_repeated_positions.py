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

# pylint: disable = protected-access
# The tests check the merging of kept slices, the batching of surface
# renders, and the DICOM check's measures of one eye, which are private to
# their modules, directly.

"""Tests of CT series whose slices repeat their positions, such as the time
points of a respiratory-correlated CT or a perfusion scan, the phases of a
contrast study, or two acquisitions that overlap.

Such a series is parted into phases by the time point or acquisition that
each slice names; each phase's face block is found from its own slices,
and the series is defaced by one block that encloses them all; the QC pack
draws each phase as a volume of its own; and the DICOM check counts each
series' phases and how far their globes lie apart. Every image is
synthetic.
"""

from __future__ import annotations

import functools
import io
import zlib

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    face_blocks,
    face_validation_dicom,
    phases,
    qc_previews,
)
from pymedphys._dicom.deidentify.defacing import FaceBlock, FaceBlockProblem
from pymedphys._dicom.deidentify.dose_defacing import find_dose_blocks
from pymedphys._dicom.deidentify.face_blocks import (
    PHASE_REACH,
    CtDefacer,
    KeptSlice,
    SeriesProblem,
    find_face_blocks,
    inspect_series,
    kept_slices,
)
from pymedphys._dicom.deidentify.phases import Named, named_by_frame, split
from pymedphys._dicom.deidentify.qc_pack import PreviewKind
from pymedphys._dicom.deidentify.references import InstanceRecord

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from .test_deidentify_qc_multi_frame_volumes import _multi_frame as _qc_multi_frame
from .test_deidentify_face_validation_dicom import _LEFT, _RIGHT, _globe
from .test_deidentify_qc_previews import _file
from .test_deidentify_qc_surfaces import SIDE, _axial, _body

# As the multi-frame defacing tests' head, coarse to keep the files small.
_SCAN = head.axial(
    spacing=2.0, thickness=3.0, extent=((-100, 100), (-130, 110), (-60, 120))
)
_GROUPS = (
    "PlanePositionSequence",
    "PlaneOrientationSequence",
    "PixelMeasuresSequence",
    "PixelValueTransformationSequence",
)


def _instance(*values: str) -> Named:
    return Named(phases.INSTANCE, values)


def _frame(*values: str) -> Named:
    return Named(phases.FRAME, values)


# phases.split


def test_slices_at_distinct_positions_are_one_phase_whatever_they_name():
    # Two acquisitions that meet without overlapping are one stack, as a
    # series without repeated positions always was.
    named = [_instance("", "1")] * 3 + [_instance("", "2")] * 3

    assert split([0.0, 2.0, 4.0, 6.0, 8.0, 10.0], named) == [[0, 1, 2, 3, 4, 5]]
    assert split([0.0, 2.0], [_instance("", ""), _frame("", "")]) == [[0, 1]]


def test_repeated_positions_are_parted_by_time_point_first():
    heights = [0.0, 2.0, 0.0, 2.0]
    # Each time point is a phase, though the acquisitions differ within it.
    named = [
        _instance("1", "7"),
        _instance("1", "8"),
        _instance("2", "7"),
        _instance("2", "8"),
    ]

    assert split(heights, named) == [[0, 1], [2, 3]]


def test_repeated_positions_are_parted_by_acquisition_where_a_time_is_missing():
    heights = [0.0, 2.0, 0.0, 2.0]
    named = [
        _instance("1", "7"),
        _instance("", "7"),
        _instance("2", "8"),
        _instance("2", "8"),
    ]

    assert split(heights, named) == [[0, 1], [2, 3]]


def test_phases_are_in_the_order_of_their_first_slices():
    heights = [0.0, 0.0, 2.0, 2.0]
    named = [_instance("9", ""), _instance("3", "")] * 2

    assert split(heights, named) == [[0, 2], [1, 3]]


def test_overlapping_acquisitions_are_phases_of_their_own_extents():
    heights = [0.0, 2.0, 4.0, 4.0, 6.0, 8.0]
    named = [_instance("", "1")] * 3 + [_instance("", "2")] * 3

    assert split(heights, named) == [[0, 1, 2], [3, 4, 5]]


def test_positions_within_the_tolerance_coincide():
    near = phases.COINCIDENT / 2
    named = [_instance("", ""), _instance("", "")]

    assert split([0.0, near], named) is None
    assert split([0.0, 2 * phases.COINCIDENT], named) == [[0, 1]]


@pytest.mark.parametrize(
    "named",
    [
        # Nothing tells the slices at one position apart.
        [_instance("", "")] * 4,
        # One slice names neither its time nor its acquisition.
        [
            _instance("1", "1"),
            _instance("1", "1"),
            _instance("2", "2"),
            _instance("", ""),
        ],
        # Both slices at one position name one time point.
        [
            _instance("1", ""),
            _instance("1", ""),
            _instance("1", ""),
            _instance("2", ""),
        ],
    ],
)
def test_repeated_positions_that_nothing_parts_cannot_be_split(named):
    assert split([0.0, 2.0, 0.0, 2.0], named) is None


def test_a_single_frame_instance_and_a_frame_are_never_one_phase():
    heights = [0.0, 0.0, 2.0, 2.0]
    named = [
        _instance("1", ""),
        _frame("\\1", ""),
        _instance("1", ""),
        _frame("\\1", ""),
    ]

    assert split(heights, named) == [[0, 2], [1, 3]]


def test_frames_are_parted_by_frame_acquisition_where_stack_and_time_are_missing():
    heights = [0.0, 2.0, 0.0, 2.0]
    named = [_frame("", "1"), _frame("", "1"), _frame("", "2"), _frame("", "2")]

    assert split(heights, named) == [[0, 1], [2, 3]]


def test_split_needs_one_name_for_each_slice():
    with pytest.raises(ValueError):
        split([0.0, 0.0], [_instance("1", "")])


def test_names_are_read_as_integers_where_they_can_be():
    dataset = pydicom.Dataset()
    dataset.TemporalPositionIdentifier = "01"
    dataset.AcquisitionNumber = " 7"

    assert phases.named_by_instance(dataset) == _instance("1", "7")
    assert phases.named_by_instance(pydicom.Dataset()) == _instance("", "")


def test_a_frame_names_its_stack_and_time_together_and_its_acquisition():
    content = pydicom.Dataset()
    content.StackID = "A"
    content.TemporalPositionIndex = 2
    content.FrameAcquisitionNumber = 5

    assert named_by_frame(content) == _frame("A\\2", "5")
    assert named_by_frame(None) == _frame("", "")
    content = pydicom.Dataset()
    content.TemporalPositionIndex = 3
    assert named_by_frame(content) == _frame("\\3", "")


def test_a_value_of_several_values_names_nothing():
    dataset = pydicom.Dataset()
    dataset.AcquisitionNumber = ["1", "2"]

    assert phases.named_by_instance(dataset) == _instance("", "")


# The face blocks of a series of phases


@functools.cache
def _phase(
    time: int | None = None,
    acquisition: int | None = None,
    *,
    shift: float = 0.0,
    turn: float = 0.0,
    low: float = -np.inf,
    high: float = np.inf,
    moved: tuple[float, float] = (0.0, 0.0),
) -> tuple[bytes, ...]:
    """The head's slices from ``low`` to ``high`` mm, as one phase of a
    series: with Temporal Position Identifier ``time`` and Acquisition
    Number ``acquisition`` where given, the head shifted and turned, and,
    where ``moved``, each slice's position moved across its plane."""
    found = []
    tag = f"{time}.{acquisition}.{shift}.{turn}.{low}.{high}.{moved}"
    number = zlib.crc32(tag.encode())
    for data in files.ct_files(_SCAN, head.Head(noise=0.0, shift=shift, turn=turn)):
        dataset = pydicom.dcmread(io.BytesIO(data))
        z = float(dataset.ImagePositionPatient[2])
        if not low <= z <= high:
            continue
        dataset.SOPInstanceUID = f"{dataset.SOPInstanceUID}.{number}"
        dataset.file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
        if time is not None:
            dataset.TemporalPositionIdentifier = time
        if acquisition is not None:
            dataset.AcquisitionNumber = acquisition
        if moved != (0.0, 0.0):
            x, y, _ = (float(v) for v in dataset.ImagePositionPatient)
            dataset.ImagePositionPatient = [x + moved[0], y + moved[1], z]
        found.append(files.written(dataset))
    return tuple(found)


def _found(*data: bytes):
    records = {
        position: InstanceRecord.from_file(each) for position, each in enumerate(data)
    }
    return records, find_face_blocks(records, lambda position: data[position])


def _outcome(*data: bytes):
    outcomes = list(_found(*data)[1].values())
    assert len(outcomes) == 1
    return outcomes[0]


@functools.cache
def _single():
    return _outcome(*_phase())


def _masks(block, data):
    dataset = pydicom.dcmread(io.BytesIO(data))
    return block.slice_mask(
        [float(v) for v in dataset.ImagePositionPatient],
        [float(v) for v in dataset.ImageOrientationPatient],
        [float(v) for v in dataset.PixelSpacing],
        (dataset.Rows, dataset.Columns),
    )


def test_a_series_without_repeated_positions_is_found_as_before():
    # Naming a time point changes nothing where no position repeats.
    assert _outcome(*_phase(1)).block == _single().block


@pytest.mark.parametrize("by", ["time", "acquisition"])
def test_each_phase_of_one_head_gives_the_series_its_block(by):
    first, second = (
        (_phase(1), _phase(2)) if by == "time" else (_phase(None, 1), _phase(None, 2))
    )

    outcome = _outcome(*first, *second)

    assert outcome.problem is None
    single = _single().block
    assert outcome.block.globes == single.globes
    assert outcome.block.anterior == single.anterior
    assert outcome.block.inferior_limit == single.inferior_limit
    # Within a micrometre of the plane of each phase's own block.
    assert np.dot(
        np.subtract(single.origin, outcome.block.origin), single.anterior
    ) == pytest.approx(0.0, abs=1e-5)


def test_phases_in_any_order_of_files_give_the_same_block():
    one = _outcome(*_phase(1), *_phase(2))
    other = _outcome(*_phase(2), *_phase(1))
    interleaved = _outcome(*(x for pair in zip(_phase(1), _phase(2)) for x in pair))

    assert one.block == other.block == interleaved.block


def test_slices_at_one_position_that_nothing_parts_leave_the_series_undefaced():
    outcome = _outcome(*_phase(None, 1), *_phase(None, 1, shift=0.5))

    assert outcome.problem is SeriesProblem.REPEATED_POSITIONS
    assert outcome.block is None


def test_phases_whose_globes_lie_apart_leave_the_series_undefaced():
    outcome = _outcome(*_phase(1), *_phase(2, shift=PHASE_REACH + 4.0))

    assert outcome.problem is SeriesProblem.PHASES_DISAGREE


def test_phases_moved_a_little_are_defaced_by_a_block_that_holds_each_phase_block():
    moved = _phase(2, shift=3.0, turn=2.0)
    outcome = _outcome(*_phase(1), *moved)
    own = _outcome(*_phase(None, None, shift=3.0, turn=2.0)).block

    assert outcome.problem is None
    for block in (_single().block, own):
        for each in (*_phase(1), *moved):
            mask = _masks(block, each)
            assert not (mask & ~_masks(outcome.block, each)).any()
    # Its inferior limit is the lower, and its globes those found higher.
    assert outcome.block.inferior_limit == min(
        _single().block.inferior_limit, own.inferior_limit
    )
    assert outcome.block.globes in (_single().block.globes, own.globes)
    assert max(g[2] for g in outcome.block.globes) == max(
        g[2] for block in (_single().block, own) for g in block.globes
    )


def test_a_phase_below_the_eyes_is_left_to_the_block_of_the_others():
    # Two acquisitions that overlap below the eyes: the second finds no
    # globes, but the block found from the first reaches none of its slices.
    lower = _phase(None, 2, high=-20.0)
    outcome = _outcome(*_phase(None, 1), *lower)

    assert outcome.problem is None
    assert outcome.block.globes == _single().block.globes
    assert not any(_masks(outcome.block, data).any() for data in lower)


def test_a_phase_without_eyes_that_the_block_reaches_leaves_the_series_undefaced():
    # A slab above the eyes that the block would reach, from whose own
    # slices no globes were found.
    outcome = _outcome(*_phase(None, 1), *_phase(None, 2, low=40.0))

    assert outcome.problem is FaceBlockProblem.NO_EYES


def test_phases_on_different_grids_within_their_planes_are_not_one_stack():
    outcome = _outcome(*_phase(1), *_phase(2, moved=(1.0, 0.0)))

    assert outcome.problem is SeriesProblem.NOT_ONE_STACK


def test_each_phase_is_written_as_air_as_its_own_slices_would_be():
    outcome = _outcome(*_phase(1), *_phase(2))

    for data, alone in zip((*_phase(1), *_phase(2)), _phase() * 2):
        dataset = pydicom.dcmread(io.BytesIO(data))
        mask = CtDefacer(outcome.block, dataset).mask(0, dataset.pixel_array)
        expected = CtDefacer(_single().block, pydicom.dcmread(io.BytesIO(alone)))
        reference = expected.mask(0, dataset.pixel_array)
        assert (mask is None) == (reference is None)
        if mask is not None:
            assert np.array_equal(mask.mask, reference.mask)
            assert mask.value == reference.value


def _eyes(towards_left: float):
    """A structure set whose eyes are drawn as the globes' outlines, moved
    ``towards_left`` mm towards the patient's left."""
    return files.structure_set(
        [
            (
                "ORGAN",
                files.circle(
                    (side * head.GLOBE_X + towards_left, head.GLOBE_Y, head.GLOBE_Z),
                    head.GLOBE_RADIUS,
                ),
            )
            for side in (-1, 1)
        ],
        names=["Eye_R", "Eye_L"],
    )


@pytest.mark.parametrize("drawn", [16.0, -10.0])
def test_an_eye_far_from_the_globes_of_any_phase_holds_the_series(drawn):
    # The second phase's head is 6 mm to the left, within PHASE_REACH, so
    # the phases agree. Eyes drawn 16 mm to the left lie within EYE_REACH
    # of its globes, 10 mm and a globe's radius away, but not of the first
    # phase's, 16 mm and a radius away; eyes drawn 10 mm to the right lie
    # within reach of the first phase's globes but not of the second's.
    shift = 6.0
    near, far = sorted((abs(drawn - shift), abs(drawn)))
    assert near + head.GLOBE_RADIUS < face_blocks.EYE_REACH - 2
    assert far + head.GLOBE_RADIUS > face_blocks.EYE_REACH + 2
    first, second = _phase(1), _phase(2, shift=shift)
    assert _outcome(*first, *second).problem is None
    nearer = _phase(None, None, shift=shift) if drawn > 0 else _phase()
    assert _outcome(*nearer, _eyes(drawn)).problem is None

    outcome = _outcome(*first, *second, _eyes(drawn))

    assert outcome.problem is SeriesProblem.EYES_DISAGREE


def test_eyes_on_every_phase_s_globes_do_not_hold_the_series():
    outcome = _outcome(*_phase(1), *_phase(2), _eyes(0.0))

    assert outcome.problem is None


def test_a_target_in_the_enclosing_block_holds_the_series():
    target = files.structure_set([("PTV", files.square((-32.0, -76.0, 20.0)))])

    outcome = _outcome(*_phase(1), *_phase(2), target)

    assert outcome.problem is SeriesProblem.TARGET_IN_BLOCK


def test_the_finder_is_inspected_on_the_first_phase():
    data = (*_phase(1), *_phase(2))
    inspection = inspect_series(list(range(len(data))), lambda p: data[p])

    assert inspection is not None
    assert inspection.block() == _single().block


def test_series_that_cannot_be_parted_are_not_inspected():
    data = (*_phase(None, 1), *_phase(None, 1, shift=0.5))

    assert inspect_series(list(range(len(data))), lambda p: data[p]) is None


def test_kept_slices_at_one_position_keep_only_what_every_phase_keeps():
    first, second = _phase(1), _phase(2)
    block = _outcome(*first, *second).block
    data = (*first, *second)
    alone = kept_slices(block, range(len(first)), lambda p: first[p])
    other = kept_slices(block, range(len(second)), lambda p: second[p])

    merged = kept_slices(block, range(len(data)), lambda p: data[p])

    assert len(merged) == len(alone) == len(other)
    for found, one, two in zip(merged, alone, other):
        assert isinstance(found, KeptSlice)
        assert found.position == one.position
        assert np.array_equal(found.kept, one.kept & two.kept)


def test_kept_slices_at_one_position_are_merged_by_and():
    shape = (3, 3)
    keep = np.ones(shape, dtype=bool)
    drop = keep.copy()
    drop[1, 1] = False
    orientation = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    slices = [
        KeptSlice((0.0, 0.0, 0.0), orientation, (1.0, 1.0), keep),
        KeptSlice((0.0, 0.0, 2.0), orientation, (1.0, 1.0), keep),
        KeptSlice((0.0, 0.0, phases.COINCIDENT / 2), orientation, (1.0, 1.0), drop),
    ]

    merged = face_blocks._merged(slices)

    assert [each.position[2] for each in merged] == [0.0, 2.0]
    assert np.array_equal(merged[0].kept, drop)
    assert np.array_equal(merged[1].kept, keep)
    assert not face_blocks._merged([])


def test_a_dose_beside_a_series_of_phases_takes_its_block():
    first, second = _phase(1), _phase(2)
    grid = files.dose(
        np.full((3, 49, 41), 100, dtype=np.uint32),
        position=(-100.0, -130.0, 0.0),
        spacing=(5.0, 5.0),
        offsets=(0.0, 20.0, 40.0),
        frame=files.FRAME,
    )
    data = (*first, *second, grid)
    records, outcomes = _found(*data)

    blocks = find_dose_blocks(records, lambda p: data[p], outcomes)

    assert len(blocks) == 1
    dose = next(iter(blocks.values()))
    assert dose.block == outcomes[files.SERIES].block
    # One kept slice for each position that the block reaches.
    alone = kept_slices(dose.block, range(len(first)), lambda p: first[p])
    assert len(dose.slices) == len(alone)


def _enhanced(stacks, *, acquisitions=None):
    """The head's slices twice over as one Enhanced CT Image instance, each
    frame's Frame Content group naming its (Stack ID, Temporal Position
    Index) of ``stacks``, or none where ``stacks`` is None, and Frame
    Acquisition Number of ``acquisitions`` where given."""
    slices = _phase() * 2
    dataset = pydicom.dcmread(io.BytesIO(files.multi_frame(slices)))
    for index, item in enumerate(dataset.PerFrameFunctionalGroupsSequence):
        content = pydicom.Dataset()
        if stacks is not None:
            stack, time = stacks[index]
            if stack:
                content.StackID = stack
            if time:
                content.TemporalPositionIndex = time
        if acquisitions is not None:
            content.FrameAcquisitionNumber = acquisitions[index]
        if len(content):
            item.FrameContentSequence = [content]
    return files.written(dataset)


@pytest.mark.parametrize("by", ["time", "stack", "acquisition"])
def test_each_time_point_of_a_multi_frame_ct_is_a_phase(by):
    count = len(_phase())
    stacks = [
        ("", 1 + k // count) if by == "time" else (str(1 + k // count), "")
        for k in range(2 * count)
    ]
    data = (
        _enhanced(None, acquisitions=[1 + k // count for k in range(2 * count)])
        if by == "acquisition"
        else _enhanced(stacks)
    )

    outcome = _outcome(data)

    assert outcome.problem is None
    assert outcome.block.globes == _single().block.globes


def test_frames_at_one_position_that_nothing_parts_are_repeated_positions():
    assert _outcome(_enhanced(None)).problem is SeriesProblem.REPEATED_POSITIONS


def test_each_frame_of_a_multi_frame_series_of_phases_is_written_as_air():
    count = len(_phase())
    data = _enhanced([("", 1 + k // count) for k in range(2 * count)])
    outcome = _outcome(data)
    dataset = pydicom.dcmread(io.BytesIO(data))
    defacer = CtDefacer(outcome.block, dataset)
    frames = dataset.pixel_array

    for index, single in enumerate(_phase() * 2):
        expected = CtDefacer(_single().block, pydicom.dcmread(io.BytesIO(single)))
        mask = defacer.mask(index, frames[index])
        reference = expected.mask(0, frames[index])
        assert (mask is None) == (reference is None)
        if mask is not None:
            assert mask.frame == index
            assert np.array_equal(mask.mask, reference.mask)


def test_a_series_of_phases_is_counted_by_its_reason():
    counts = face_blocks.FaceBlockCounts()
    counts.record(
        [
            _outcome(*_phase(1), *_phase(2)),
            _outcome(*_phase(None, 1), *_phase(None, 1, shift=0.5)),
            _outcome(*_phase(1), *_phase(2, shift=PHASE_REACH + 4.0)),
        ]
    )

    assert counts.defaced == 1
    assert counts.not_defaced == {
        SeriesProblem.REPEATED_POSITIONS: 1,
        SeriesProblem.PHASES_DISAGREE: 1,
    }


# The QC pack's volumes of a series of phases


def _timed(body, *, time=None, acquisition=None, offset=0, series="2.25.7101"):
    """The axial slices of qc_surfaces' tests, at run positions from
    ``offset``, each naming ``time`` and ``acquisition`` where given."""
    found = {}
    for position, data in _axial(body, series=series).items():
        dataset = pydicom.dcmread(io.BytesIO(data))
        dataset.SOPInstanceUID = f"{dataset.SOPInstanceUID}.{offset + 1}"
        if time is not None:
            dataset.TemporalPositionIdentifier = time
        if acquisition is not None:
            dataset.AcquisitionNumber = acquisition
        found[offset + position] = _file(dataset)
    return found


def _kinds(previews):
    return [preview.kind for preview in previews.previews]


def _of(previews, kind):
    return [preview for preview in previews.previews if preview.kind is kind]


@pytest.mark.pydicom
@pytest.mark.parametrize("by", ["time", "acquisition"])
def test_each_phase_of_single_frame_slices_is_a_volume_of_its_own(by):
    named = {"time": "time", "acquisition": "acquisition"}[by]
    written = {
        **_timed(_body(), **{named: 1}),
        **_timed(_body(ear=True), **{named: 2}, offset=SIDE),
    }

    previews = qc_previews.previews_of(written, ())

    assert _kinds(previews) == [
        PreviewKind.SERIES_CINE,
        PreviewKind.SERIES_MIP,
        PreviewKind.SERIES_SURFACE,
        PreviewKind.SERIES_MIP,
        PreviewKind.SERIES_SURFACE,
    ]
    for index, body in enumerate((_body(), _body(ear=True))):
        expected = qc_previews.previews_of(_axial(body), ())
        for kind in (PreviewKind.SERIES_MIP, PreviewKind.SERIES_SURFACE):
            found = _of(previews, kind)[index]
            (alone,) = _of(expected, kind)
            assert found.png == alone.png
            assert found.frames == tuple((index * SIDE + k, 0) for k in range(SIDE))
    # Every slice is drawn, so a face verdict can release each of them.
    assert previews.pixels_shown == frozenset(range(2 * SIDE))


@pytest.mark.pydicom
def test_single_frame_slices_at_one_position_that_nothing_parts_form_no_volume():
    written = {**_timed(_body()), **_timed(_body(ear=True), offset=SIDE)}

    previews = qc_previews.previews_of(written, ())

    # Only the slices that the cine strip shows are drawn whole.
    assert _kinds(previews) == [PreviewKind.SERIES_CINE]
    (cine,) = previews.previews
    assert previews.pixels_shown == frozenset(p for p, _ in cine.frames)
    assert len(previews.pixels_shown) == qc_previews.CINE_FRAMES < 2 * SIDE


@pytest.mark.pydicom
def test_a_multi_frame_instance_is_parted_by_frame_acquisition_number():
    slices = {**_axial(_body()), **{SIDE + k: v for k, v in _axial(_body()).items()}}

    def acquired(dataset):
        for index, item in enumerate(dataset.PerFrameFunctionalGroupsSequence):
            content = pydicom.Dataset()
            content.FrameAcquisitionNumber = 1 + index // SIDE
            item.FrameContentSequence = [content]

    written = {0: _qc_multi_frame(slices, changed=acquired)}

    previews = qc_previews.previews_of(written, ())

    assert _kinds(previews) == [
        PreviewKind.SERIES_CINE,
        PreviewKind.SERIES_MIP,
        PreviewKind.SERIES_SURFACE,
        PreviewKind.SERIES_MIP,
        PreviewKind.SERIES_SURFACE,
    ]
    assert previews.pixels_shown == frozenset({0})


@pytest.mark.pydicom
def test_volumes_beyond_the_samples_held_at_once_are_drawn_in_later_batches(
    monkeypatch,
):
    written = {
        **_timed(_body(), time=1),
        **_timed(_body(ear=True), time=2, offset=SIDE),
        **_timed(_body(nose=False), time=3, offset=2 * SIDE),
    }
    together = qc_previews.previews_of(written, ())
    surfaces = []
    original = qc_previews._Render.begin

    def begin(self):
        original(self)
        surfaces.append(self)

    # Room for one volume at a time, each sampled only while it is drawn.
    monkeypatch.setattr(qc_previews, "SAMPLED_AT_ONCE", 1)
    monkeypatch.setattr(qc_previews._Render, "begin", begin)

    batched = qc_previews.previews_of(written, ())

    assert len(_of(together, PreviewKind.SERIES_SURFACE)) == 3
    assert [p.kind for p in batched.previews] == [p.kind for p in together.previews]
    assert [p.png for p in batched.previews] == [p.png for p in together.previews]
    assert [p.frames for p in batched.previews] == [p.frames for p in together.previews]
    assert batched.pixels_shown == together.pixels_shown == frozenset(range(3 * SIDE))
    assert len(surfaces) == 3
    assert all(render.surface is None for render in surfaces)


def test_batches_hold_no_more_than_the_samples_at_once_unless_one_alone():
    class _Sized:
        def __init__(self, size):
            self.size = size

    limit = qc_previews.SAMPLED_AT_ONCE
    renders = [_Sized(limit // 2), _Sized(limit // 2), _Sized(1), _Sized(2 * limit)]

    assert qc_previews._batches(renders) == [[0, 1], [2], [3]]
    assert qc_previews._batches([]) == [[]]


# The DICOM check's measures of a series of phases (D-054)


def _as_case(data: bytes, case: int) -> bytes:
    """A file of a series, Frame of Reference, and patient of its own case."""
    dataset = pydicom.dcmread(io.BytesIO(data))
    dataset.SeriesInstanceUID = f"2.25.7301{case}"
    dataset.FrameOfReferenceUID = f"2.25.7302{case}"
    dataset.PatientID = f"P{case}"
    return files.written(dataset)


def _eye_set(case: int) -> bytes:
    """Eye ROIs drawn at the head's own globes, in a case's frame."""
    template = pydicom.Dataset()
    template.PatientName = "Head^Analytic"
    template.PatientID = f"P{case}"
    template.StudyInstanceUID = f"2.25.7303{case}"
    template.SeriesInstanceUID = f"2.25.7304{case}"
    return files.structure_set(
        [("ORGAN", _globe(_RIGHT)), ("ORGAN", _globe(_LEFT))],
        frame=f"2.25.7302{case}",
        template=template,
        names=["Eye_R", "Eye_L"],
    )


def _own(*data: bytes) -> FaceBlock:
    """The block of one phase's slices alone."""
    block = _outcome(*data).block
    assert block is not None
    return block


_MOVED = {"shift": 3.0, "turn": 2.0}
_APART = {"shift": PHASE_REACH + 4.0}


@pytest.fixture(scope="module", name="checked")
def _checked(tmp_path_factory):
    """The DICOM check's measures of a directory of five series, one to a
    directory in order:

    1. two time points, the second of the head moved a little, with eye
       ROIs drawn at the first's globes;
    2. two time points whose globes lie too far apart;
    3. two acquisitions, the second below the eyes;
    4. slices at one position that nothing parts; and
    5. two time points of one Enhanced CT Image instance.
    """
    count = len(_phase())
    cases = {
        1: (*_phase(1), *_phase(2, **_MOVED)),
        2: (*_phase(1), *_phase(2, **_APART)),
        3: (*_phase(None, 1), *_phase(None, 2, high=-20.0)),
        4: (*_phase(None, 1), *_phase(None, 1, shift=0.5)),
        5: (_enhanced([("", 1 + k // count) for k in range(2 * count)]),),
    }
    root = tmp_path_factory.mktemp("phases")
    for case, data in cases.items():
        (root / str(case)).mkdir()
        for index, each in enumerate(data):
            (root / str(case) / f"CT{index:03d}.dcm").write_bytes(_as_case(each, case))
    (root / "1" / "RS.dcm").write_bytes(_eye_set(1))
    return face_validation_dicom.measure_dicom(root)


def test_the_dicom_check_counts_each_series_phases(checked):
    assert checked.crashed == {}
    assert [each.outcome for each in checked.series] == [
        "defaced",
        "phases-disagree",
        "defaced",
        "repeated-positions",
        "defaced",
    ]
    assert [each.phases for each in checked.series] == [2, 2, 2, None, 2]
    assert [each.phases_without_eyes for each in checked.series] == [0, 0, 1, 0, 0]


def test_the_dicom_check_measures_how_far_each_globe_lies_from_itself():
    right, left = (-30.0, -70.0, 0.0), (30.0, -70.0, 0.0)

    def block(*globes):
        return FaceBlock((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), -50.0, globes)

    blocks = [
        block(right, left),
        block((-29.0, -70.0, 0.0), (30.0, -70.0, 0.0)),
        block(right, (30.0, -73.0, 4.0)),
    ]

    # Each globe against itself, never against the other side's.
    assert face_validation_dicom.globe_spread(blocks) == pytest.approx(5.0)
    assert face_validation_dicom.globe_spread(blocks[:2]) == pytest.approx(1.0)
    assert face_validation_dicom.globe_spread(blocks[:1]) is None


def test_the_globe_spread_is_of_every_phase_whether_they_agree_or_not(checked):
    single, moved, apart = (
        _single().block,
        _own(*_phase(None, None, **_MOVED)),
        (_own(*_phase(None, None, **_APART))),
    )
    spreads = [each.globe_spread for each in checked.series]

    assert spreads[0] == pytest.approx(
        face_validation_dicom.globe_spread([single, moved])
    )
    assert spreads[1] == pytest.approx(
        face_validation_dicom.globe_spread([single, apart])
    )
    assert spreads[1] > PHASE_REACH >= spreads[0]
    # Only one phase of the third found a block; the fourth was not parted.
    assert spreads[2] is None
    assert spreads[3] is None
    assert spreads[4] == 0.0


def test_an_eye_is_measured_against_the_phase_whose_globes_lie_farthest(checked):
    single, moved = _single().block, _own(*_phase(None, None, **_MOVED))
    eyes = face_validation_dicom._eye_rois(
        pydicom.dcmread(io.BytesIO(_eye_set(1))), "2.25.73021"
    )
    limit = min(single.inferior_limit, moved.inferior_limit)

    measured = checked.series[0].eyes

    assert len(measured) == len(eyes) == 2
    for eye, (side, contours) in zip(measured, eyes, strict=True):
        against = [
            face_validation_dicom._eye_against(block, limit, side, contours)
            for block in (single, moved)
        ]
        reaches = [each.reach for each in against]
        assert reaches[1] > reaches[0]
        assert eye.reach == pytest.approx(max(reaches))
        assert eye.globe_errors == pytest.approx(against[1].globe_errors)
        assert eye.above_limit == pytest.approx(against[1].above_limit)


def test_an_eye_swapped_against_any_phase_is_counted_as_swapped():
    def block(*globes):
        return FaceBlock((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), -50.0, globes)

    # The first phase's right globe found 3 mm off, so that the eye lies
    # farthest from it, and the second's globes found the other way round.
    off = block((-33.0, -70.0, 0.0), (30.0, -70.0, 0.0))
    swapped = block((30.0, -70.0, 0.0), (-30.0, -70.0, 0.0))
    contours = [
        ("CLOSED_PLANAR", np.array([[-30.0, -70.0, z] for z in (0.0, 1.0, 2.0)]))
    ]

    for blocks in ([off, swapped], [swapped, off]):
        eye = face_validation_dicom._eye_measures(blocks, -50.0, 0, contours)
        # Measured against the phase it lies farthest from, yet swapped.
        assert eye.reach == pytest.approx(np.hypot(3.0, 2.0))
        assert eye.swapped is True
    assert (
        face_validation_dicom._eye_measures([off], -50.0, 0, contours).swapped is False
    )


def test_the_dicom_check_measures_multi_frame_ct_as_the_finder_reads_it(checked):
    enhanced = checked.series[4]

    assert enhanced.storage == "native 16/16 signed"
    assert enhanced.pixel_spacing == pytest.approx(2.0)
    assert enhanced.air is True


def test_slices_at_one_position_are_not_counted_as_a_spacing(checked):
    # Two phases at the same heights, and two slices half a micrometre apart.
    assert all(each.slice_spacing == pytest.approx(3.0) for each in checked.series)
    data = list(_phase()[:2])
    dataset = pydicom.dcmread(io.BytesIO(data[0]))
    x, y, z = (float(v) for v in dataset.ImagePositionPatient)
    dataset.ImagePositionPatient = [x, y, z + phases.COINCIDENT / 2]
    dataset.SOPInstanceUID = f"{dataset.SOPInstanceUID}.9"
    data.append(files.written(dataset))

    stored = face_validation_dicom._stored(list(range(3)), lambda i: data[i])

    assert stored["slice_spacing"] == pytest.approx(3.0, abs=phases.COINCIDENT)


def test_the_dicom_check_summarises_the_phases(checked):
    summary = face_validation_dicom.summarise(checked)
    counted = summary["phases"]

    assert counted["not_parted"] == 1
    assert [
        (each["from"], each["count"])
        for each in counted["by_series"]["bins"]
        if each["count"]
    ] == [(2, 4)]
    assert counted["outcomes_of_several"] == {"defaced": 3, "phases-disagree": 1}
    assert counted["series_with_phases_without_eyes"] == 1
    assert counted["phases_without_eyes"] == 1
    spread = counted["globe_spread"]
    assert spread["unit"] == "mm"
    assert sum(each["count"] for each in spread["bins"]) == 3
    # The bins part spreads that a run accepts from those it does not.
    assert PHASE_REACH in face_validation_dicom.GLOBE_SPREAD.edges
    assert (
        sum(each["count"] for each in spread["bins"] if each["from"] >= PHASE_REACH)
        == 1
    )
    assert summary["settings"]["phase_reach_mm"] == PHASE_REACH
