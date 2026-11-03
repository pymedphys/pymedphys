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

# The analytic head's cases, untilted and tilted, share its helpers, so they
# stay in one module.
# pylint: disable = too-many-lines

"""Finding the face block of a head CT, on an analytic head."""

from __future__ import annotations

import dataclasses
import functools
import itertools
import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import defacing, qc_surfaces, stack_sampling

from . import _synthetic_head as head

_FIXED = defacing.FaceBlock(
    (0.0, -61.0, 20.0),
    (0.0, -1.0, 0.0),
    7.5,
    ((-32.0, -66.0, 20.0), (32.0, -66.0, 20.0)),
)


def _finder(scan: head.Scan) -> defacing.FaceFinder:
    return defacing.FaceFinder(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )


def _block(scan: head.Scan, *heads: head.Head) -> defacing.FaceBlock:
    finder = _finder(scan)
    for values in scan.slices(*heads):
        finder.add(values)
    return finder.block()


def _assert_around_the_globes(block: defacing.FaceBlock, within: float = 1.5) -> None:
    expected = (
        (-head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
        (head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
    )
    np.testing.assert_allclose(block.globes, expected, atol=within)
    np.testing.assert_allclose(block.anterior, (0, -1, 0), atol=0.02)
    np.testing.assert_allclose(
        block.origin, (0, head.GLOBE_Y + defacing.MARGIN, head.GLOBE_Z), atol=within
    )
    # From the globes' inferior edge, or lower by up to two slices, up.
    inferior_edge = head.GLOBE_Z - head.GLOBE_RADIUS
    assert inferior_edge - 10.0 <= block.inferior_limit <= inferior_edge


@pytest.mark.parametrize(
    "scan",
    [
        head.axial(),
        head.axial(feet_first=True),
        head.axial(prone=True),
        head.axial(prone=True, feet_first=True),
        dataclasses.replace(head.axial(), positions=head.axial().positions[::-1]),
        head.sagittal(),
    ],
    ids=[
        "head-first-supine",
        "feet-first",
        "prone",
        "prone-feet-first",
        "slices-from-superior",
        "sagittal",
    ],
)
def test_the_block_is_found_from_the_globes_whatever_the_orientation(scan):
    _assert_around_the_globes(_block(scan))


@pytest.mark.parametrize(
    "scan, anatomy",
    [
        (head.axial(), head.Head(noise=40.0, seed=1)),
        (head.axial(), head.Head(bolus=True)),
        (head.axial(thickness=5.0), head.Head()),
        (head.axial(spacing=1.5, thickness=3.0), head.Head()),
        (
            head.axial(thickness=5.0, extent=((-100, 100), (-130, 110), (-800, 120))),
            head.Head(),
        ),
    ],
    ids=[
        "noisy",
        "bolus-over-the-eyes",
        "thick-slices",
        "coarse-pixels",
        "long-volume",
    ],
)
def test_the_block_is_found_through_noise_and_coarser_sampling(scan, anatomy):
    _assert_around_the_globes(_block(scan, anatomy))


def test_the_block_holds_the_upper_face_and_keeps_the_rest():
    block = _block(head.axial())
    points = {
        "front of each globe": [(-32, -75, 20), (32, -75, 20)],
        "bridge of the nose": [(0, -90, 12)],
        "forehead": [(0, -85, 60), (0, -70, 100)],
        "air before the face, where a mask would lie": [
            (0, -125, 30),
            (-90, -125, 115),
        ],
    }
    kept = {
        "back of each globe": [(-32, -57, 20), (32, -57, 20)],
        "tip of the nose": [(0, -118, -15)],
        "mouth and chin": [(0, -80, -50), (0, -60, -100)],
        "back of the head": [(0, 90, 30), (0, 60, 100)],
    }
    for part, where in points.items():
        assert block.contains(np.array(where)).all(), part
    for part, where in kept.items():
        assert not block.contains(np.array(where)).any(), part


@pytest.mark.parametrize(
    "anatomy",
    [head.Head(eyes=(True, False)), head.Head(eyes=(False, True))],
    ids=["no-left-eye", "no-right-eye"],
)
def test_a_head_without_both_eyes_is_refused(anatomy):
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(head.axial(), anatomy)

    assert refused.value.problem is defacing.FaceBlockProblem.NO_EYES


def test_a_volume_that_cuts_through_the_eyes_is_refused():
    scan = head.axial(extent=((-100, 100), (-130, 110), (-120, 25)))

    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(scan)

    assert refused.value.problem is defacing.FaceBlockProblem.NO_EYES


def test_spheres_without_a_bony_orbit_are_not_eyes():
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(head.axial(), head.Head(orbits=False, skull=False))

    assert refused.value.problem is defacing.FaceBlockProblem.NO_EYES


def test_two_heads_in_view_are_refused():
    scan = head.axial(spacing=1.5, extent=((-230, 230), (-130, 110), (-120, 120)))

    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(scan, head.Head(shift=-120.0), head.Head(shift=120.0))

    assert refused.value.problem is defacing.FaceBlockProblem.AMBIGUOUS_EYES
    assert str(refused.value) == "ambiguous-eyes"


def test_the_block_is_the_same_each_time():
    scan = head.axial(feet_first=True)

    assert _block(scan) == _block(scan)


def test_a_block_needs_every_slice():
    scan = head.axial()
    finder = _finder(scan)
    for values, _ in zip(scan.slices(), range(len(scan.positions) - 1)):
        finder.add(values)

    with pytest.raises(ValueError, match="every slice"):
        finder.block()


@pytest.mark.parametrize(
    "scan",
    [
        head.axial(),
        head.axial(prone=True, feet_first=True),
        head.sagittal(),
        head.tilted(degrees=15.0),
    ],
    ids=["axial", "prone-feet-first", "sagittal", "gantry-tilt-15"],
)
def test_a_slice_mask_marks_the_pixels_whose_centres_are_in_the_block(scan):
    block = _FIXED

    marked = []
    for index in (0, len(scan.positions) // 2, len(scan.positions) - 1):
        mask = block.slice_mask(
            scan.positions[index], scan.orientation, scan.spacing, scan.shape
        )
        points = scan.points(index)
        expected = (points[..., 1] < -61.0) & (points[..., 2] > 7.5)
        assert mask.shape == scan.shape
        np.testing.assert_array_equal(mask, expected)
        marked.append(int(mask.sum()))

    assert 0 < sum(marked) < 3 * scan.shape[0] * scan.shape[1]


def test_a_point_on_either_plane_is_outside_the_block():
    block = _FIXED
    points = np.array([[0.0, -61.0, 50.0], [0.0, -80.0, 7.5], [0.0, -61.1, 7.6]])

    np.testing.assert_array_equal(block.contains(points), [False, False, True])


@pytest.mark.parametrize("turn", [-25.0, 20.0])
def test_the_block_turns_with_a_head_turned_in_its_mask(turn):
    block = _block(head.axial(), head.Head(turn=turn))
    angle = np.radians(turn)

    np.testing.assert_allclose(
        block.anterior, (np.sin(angle), -np.cos(angle), 0), atol=0.03
    )
    # The front of each globe, in the head's own frame, is in the block, and
    # the back of each is not.
    for side in (-1, 1):
        for depth, inside in ((-9.0, True), (9.0, False)):
            x, y = side * head.GLOBE_X, head.GLOBE_Y + depth
            point = (
                x * np.cos(angle) - y * np.sin(angle),
                x * np.sin(angle) + y * np.cos(angle),
                head.GLOBE_Z,
            )
            assert block.contains(np.array(point)) == inside, (side, depth)


def test_a_head_recorded_facing_the_wrong_way_is_refused():
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(head.axial(), head.Head(facing_back=True))

    assert refused.value.problem is defacing.FaceBlockProblem.HEAD_NOT_BEHIND_EYES


_TILTED = {
    **head.tilted_heads(),
    "gantry-tilt-20-feet-first": head.oblique(
        head.axial(feet_first=True), head.rotation(about_x=-20.0)
    ),
    "oblique-sagittal": head.oblique(head.sagittal(), head.rotation(about_z=8.0)),
}


@functools.cache
def _untilted_block() -> defacing.FaceBlock:
    return _block(head.axial(), head.Head(seed=3))


@pytest.mark.parametrize("scan", _TILTED.values(), ids=_TILTED.keys())
def test_a_tilted_sheared_or_oblique_volume_gives_the_untilted_heads_block(scan):
    block = _block(scan, head.Head(seed=3))

    _assert_around_the_globes(block)
    expected = _untilted_block()
    voxel = defacing.MINIMUM_VOXEL
    np.testing.assert_allclose(block.globes, expected.globes, atol=voxel)
    np.testing.assert_allclose(block.origin, expected.origin, atol=voxel)


@pytest.mark.parametrize(
    "anatomy, problem",
    [
        (head.Head(eyes=(True, False)), defacing.FaceBlockProblem.NO_EYES),
        (head.Head(facing_back=True), defacing.FaceBlockProblem.HEAD_NOT_BEHIND_EYES),
        (head.Head(upside_down=True), defacing.FaceBlockProblem.CRANIUM_NOT_ABOVE_EYES),
    ],
    ids=["no-left-eye", "facing-back", "upside-down"],
)
def test_a_tilted_volume_is_refused_as_an_untilted_one_is(anatomy, problem):
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(_TILTED["gantry-tilt-15"], anatomy)

    assert refused.value.problem is problem


def test_tilted_slices_added_out_of_order_give_the_same_block():
    scan = _TILTED["gantry-tilt-15"]
    order = np.random.default_rng(5).permutation(len(scan.positions))
    shuffled = dataclasses.replace(
        scan, positions=tuple(scan.positions[index] for index in order)
    )
    anatomy = head.Head(noise=0.0)
    # The slices are generated in the order of their positions, so the
    # shuffled scan's slices are the same images in another order.
    assert _block(shuffled, anatomy) == _block(scan, anatomy)


def _stack(scan: head.Scan) -> stack_sampling.Stack:
    return stack_sampling.Stack(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )


# An axial scan whose rows rise 3e-5 mm per millimetre: within the alignment
# tolerance, and its slices within 0.01 mm of its first slice's normal.
_NEAR_AXIAL = dataclasses.replace(
    head.axial(), orientation=(1.0, 0.0, 3e-5, *head.axial().orientation[3:])
)


@pytest.mark.parametrize(
    "scan",
    [
        _NEAR_AXIAL,
        dataclasses.replace(head.axial(), spacing=(0.9999999, 0.9999999)),
        head.axial(
            spacing=0.8, thickness=1.2, extent=((-100, 100), (-130, 110), (0, 60))
        ),
        head.sagittal(),
    ],
    ids=["nearly-axial", "spacing-0.9999999", "spacing-0.8", "sagittal"],
)
def test_the_finder_takes_an_aligned_stacks_voxels_from_its_grid_as_before(scan):
    stack = _stack(scan)
    assert stack.aligned
    coordinates = stack.grid().coordinates
    voxel = qc_surfaces.voxel_side(
        [sorted(values) for values in coordinates],
        defacing.MINIMUM_VOXEL,
        defacing.MAXIMUM_VOXELS,
    )

    finder = defacing.FaceFinder(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )
    for values in scan.slices(head.Head(noise=0.0)):
        finder.add(values)

    assert finder.inspect().voxel == voxel


@pytest.mark.parametrize(
    "scan, rise",
    [
        (head.axial(), 2.5),
        (head.axial(feet_first=True, prone=True), 2.5),
        (head.sagittal(), 1.0),
        (head.axial(spacing=0.8, extent=((-100, 100), (-130, 110), (20, 20))), 0.0),
        (
            head.tilted(degrees=15.0),
            2.5 * math.cos(math.radians(15.0)) ** 2 + math.sin(math.radians(15.0)),
        ),
        (head.sheared(head.axial(), 15.0), 2.5),
        # Within the tolerances of a stack along the patient's axes, the
        # heights of its slices, as before, not the rows' rise of 3e-5 mm.
        (_NEAR_AXIAL, 2.5),
        (
            head.oblique(head.axial(), head.rotation(about_y=10.0)),
            # Turned with the rows, the slices stay 2.5 mm apart along the
            # normal.
            2.5 * math.cos(math.radians(10.0)) + 1.0 * math.sin(math.radians(10.0)),
        ),
    ],
    ids=[
        "axial",
        "prone-feet-first",
        "sagittal",
        "one-slice",
        "gantry-tilt-15",
        "sheared",
        "nearly-axial",
        "oblique-about-y",
    ],
)
def test_a_samples_height_is_its_slices_rows_and_columns_along_the_superior_axis(
    scan, rise
):
    # About the globes: the box of the analytic head's globes.
    low = np.array([-head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z]) - head.GLOBE_RADIUS
    high = np.array([head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z]) + head.GLOBE_RADIUS

    spacing = defacing.SampleSpacing.of(_stack(scan))

    assert spacing.across(low, high) == pytest.approx(rise, abs=1e-9)


def test_a_samples_height_takes_the_widest_gap_between_slices_about_the_globes():
    scan = head.axial()
    # Slices every 40 mm below the head, and every 5 mm from just below the
    # globes' inferior edge to above them.
    heights = [*np.arange(-400.0, -120.0, 40.0), *np.arange(-120.0, 7.5, 2.5)]
    heights += [*np.arange(7.5, 120.0, 5.0)]
    scan = dataclasses.replace(
        scan,
        positions=tuple(
            (scan.positions[0][0], scan.positions[0][1], float(height))
            for height in heights
        ),
    )
    spacing = defacing.SampleSpacing.of(_stack(scan))

    def across(bottom: float, top: float) -> float:
        return spacing.across(np.array([0.0, 0.0, bottom]), np.array([0, 0, top]))

    assert across(8.0, 32.0) == pytest.approx(5.0)
    assert across(-50.0, -10.0) == pytest.approx(2.5)
    assert across(-300.0, -200.0) == pytest.approx(40.0)


def _coded(scan: head.Scan) -> list[np.ndarray]:
    """Each slice's pixels, each coded by its slice, row, and column."""
    rows, columns = np.indices(scan.shape)
    return [
        (10000 * index + 100 * rows + columns).astype(np.float32)
        for index in range(len(scan.positions))
    ]


def _small(orientation, along, steps=(0.0, 2.1, 4.2, 6.3, 8.4, 10.5)) -> head.Scan:
    positions = tuple(
        tuple(float(value) for value in step * np.array(along)) for step in steps
    )
    return head.Scan(tuple(orientation), positions, (1.3, 0.9), (9, 11))


def _turned(turn: np.ndarray) -> tuple[float, ...]:
    along_row = turn @ np.array([1.0, 0.0, 0.0])
    down_column = turn @ np.array([0.0, 1.0, 0.0])
    return tuple(float(value) for value in (*along_row, *down_column))


_SMALL_TILTED = {
    "gantry-tilt-15": _small(
        _turned(head.rotation(about_x=-15.0)),
        head.rotation(about_x=-15.0) @ np.array([0.0, 0.0, 1.0]),
    ),
    "gantry-tilt-15-along-the-table": _small(
        _turned(head.rotation(about_x=-15.0)), (0.0, 0.0, 1.0)
    ),
    "sheared": _small(
        (1.0, 0.0, 0.0, 0.0, 1.0, 0.0), (0.0, -math.tan(math.radians(15.0)), 1.0)
    ),
    "compound-oblique": _small(
        _turned(head.rotation(about_x=25.0, about_y=-35.0, about_z=50.0)),
        head.rotation(about_x=25.0, about_y=-35.0, about_z=50.0)
        @ np.array([0.2, -0.1, 1.0]),
        steps=(6.0, 0.0, 1.0, 9.5, 2.5, 3.0),
    ),
}


@pytest.mark.parametrize("scan", _SMALL_TILTED.values(), ids=_SMALL_TILTED.keys())
def test_a_voxel_beyond_a_tilted_stack_takes_the_pixel_at_its_edge_nearest_it(scan):
    stack = _stack(scan)
    sampler = stack_sampling.StackSampler(stack, stack.lattice(0.7))
    beyond = defacing._Beyond.of(sampler)  # pylint: disable = protected-access
    frames = _coded(scan)
    values = np.full(math.prod(sampler.lattice.shape), np.nan)
    reached = np.zeros(values.shape, dtype=bool)
    for index, frame in enumerate(frames):
        taken = sampler.nearest(index)
        values[taken.voxels] = frame[taken.rows, taken.columns]
        reached[taken.voxels] = True
        edge = beyond.of_slice(index)
        values[edge.voxels] = frame[edge.rows, edge.columns]

    # Every voxel takes a pixel, and those beyond the stack are the rest.
    assert np.isfinite(values).all()
    assert beyond.count == int((~reached).sum()) > 0
    # Each found by brute force: the nearest slice along the normal, then
    # the pixel nearest the voxel's projection, clipped to the slice's.
    voxels = np.flatnonzero(~reached)
    points = sampler.lattice.points(np.unravel_index(voxels, sampler.lattice.shape))
    distances = np.abs(points @ stack.normal - stack.offsets[:, np.newaxis])
    nearest = np.argmin(distances, axis=0)
    relative = points - stack.origins[nearest]
    rows = np.clip(
        np.rint(relative @ stack.down_column / stack.spacing[0]), 0, scan.shape[0] - 1
    )
    columns = np.clip(
        np.rint(relative @ stack.along_row / stack.spacing[1]), 0, scan.shape[1] - 1
    )
    np.testing.assert_array_equal(
        values[voxels], 10000 * nearest + 100 * rows + columns
    )


@pytest.mark.parametrize(
    "scan",
    [
        head.axial(),
        head.axial(feet_first=True),
        head.axial(prone=True, feet_first=True),
        head.sagittal(),
        dataclasses.replace(head.axial(), positions=head.axial().positions[::-1]),
    ],
    ids=["axial", "feet-first", "prone-feet-first", "sagittal", "from-superior"],
)
def test_nothing_lies_beyond_a_stack_along_the_patient_axes(scan):
    stack = _stack(scan)
    sampler = stack_sampling.StackSampler(stack, stack.lattice(defacing.MINIMUM_VOXEL))

    assert defacing._Beyond.of(sampler).count == 0  # pylint: disable = protected-access


@pytest.mark.parametrize(
    "orientation",
    [(1.0, 0.0, 0.0, 0.0, 1.0, 0.0), _turned(head.rotation(about_x=-15.0))],
    ids=["axial", "gantry-tilt-15"],
)
def test_the_finder_samples_each_voxel_by_its_nearest_slice_and_pixel(orientation):
    scan = _small(orientation, (0.0, 0.0, 1.0))
    finder = _finder(scan)
    frames = _coded(scan)
    for frame in frames:
        finder.add(frame)
    stack = _stack(scan)
    volume = stack_sampling.SampledVolume(
        stack_sampling.StackSampler(stack, stack.lattice(defacing.MINIMUM_VOXEL))
    )
    for frame in frames:
        volume.add(frame)

    samples = finder._samples  # pylint: disable = protected-access
    taken = np.isfinite(volume.values)
    np.testing.assert_array_equal(samples[taken], volume.values[taken])
    assert np.isfinite(samples).all()


@pytest.mark.parametrize(
    "scan",
    [
        head.tilted(degrees=15.0),
        head.sheared(head.axial(), 15.0),
        head.oblique(head.axial(), head.rotation(about_z=10.0)),
    ],
    ids=["gantry-tilt-15", "sheared", "oblique-10"],
)
def test_a_stack_off_the_patient_axes_is_not_along_them(scan):
    assert not defacing.along_patient_axes(scan.orientation, scan.positions)


@pytest.mark.parametrize(
    "scan",
    [
        head.axial(),
        head.axial(prone=True, feet_first=True),
        head.sagittal(),
        dataclasses.replace(
            head.axial(),
            positions=tuple(
                (x + 0.9 * defacing.STACKING_TOLERANCE * index / 96, y, z)
                for index, (x, y, z) in enumerate(head.axial().positions)
            ),
        ),
    ],
    ids=["axial", "prone-feet-first", "sagittal", "offset-within-tolerance"],
)
def test_a_stack_along_the_patient_axes_is_along_them(scan):
    assert defacing.along_patient_axes(scan.orientation, scan.positions)


def test_two_slices_at_one_position_are_refused():
    scan = head.axial()
    scan = dataclasses.replace(scan, positions=scan.positions[:1] + scan.positions[:-1])

    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _finder(scan)

    assert refused.value.problem is defacing.FaceBlockProblem.NOT_ALONG_PATIENT_AXES


def test_a_head_recorded_upside_down_is_refused():
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(head.axial(), head.Head(upside_down=True))

    assert refused.value.problem is defacing.FaceBlockProblem.CRANIUM_NOT_ABOVE_EYES


def test_a_volume_that_ends_above_the_orbits_is_refused_with_bone_below_or_none():
    # It shows nothing of the cranium above the eyes, so the head may be
    # upside down, whatever bone encloses below them.
    scan = head.axial(extent=((-100, 100), (-130, 110), (-120, 45)))

    for anatomy in (head.Head(), head.Head(skull=False)):
        with pytest.raises(defacing.FaceBlockRefused) as refused:
            _block(scan, anatomy)

        assert (
            refused.value.problem is defacing.FaceBlockProblem.CRANIUM_NOT_ABOVE_EYES
        ), anatomy


def test_slices_added_out_of_order_give_the_same_block():
    scan = head.axial()
    order = np.random.default_rng(3).permutation(len(scan.positions))
    shuffled = dataclasses.replace(
        scan, positions=tuple(scan.positions[index] for index in order)
    )
    anatomy = head.Head(noise=0.0)

    assert _block(shuffled, anatomy) == _block(scan, anatomy)


def test_a_wide_gap_between_slices_far_from_the_eyes_does_not_move_the_block():
    scan = head.axial()
    # Slices every 40 mm below the head, as a long volume might have.
    below = tuple(
        (scan.positions[0][0], scan.positions[0][1], float(height))
        for height in np.arange(-400.0, -120.0, 40.0)
    )
    anatomy = head.Head(noise=0.0)

    block = _block(dataclasses.replace(scan, positions=below + scan.positions), anatomy)

    assert block == _block(scan, anatomy)


def test_slices_offset_within_their_plane_by_less_than_the_tolerance_are_kept():
    scan = head.axial()
    offset = 0.9 * defacing.STACKING_TOLERANCE
    count = len(scan.positions)
    shifted = tuple(
        (x + offset * index / (count - 1), y, z)
        for index, (x, y, z) in enumerate(scan.positions)
    )

    _assert_around_the_globes(_block(dataclasses.replace(scan, positions=shifted)))


@pytest.mark.parametrize(
    "orientation",
    [(1.01, 0, 0, 0, 1 / 1.01, 0), (1, 0, 0, 0.01, 1, 0)],
    ids=["not-of-unit-length", "not-perpendicular"],
)
def test_direction_cosines_not_of_unit_length_or_not_perpendicular_are_refused(
    orientation,
):
    # Unit length: their cross product, the slices' normal, is still of
    # unit length.
    scan = dataclasses.replace(head.axial(), orientation=orientation)

    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _finder(scan)

    assert refused.value.problem is defacing.FaceBlockProblem.NOT_ALONG_PATIENT_AXES


@pytest.mark.parametrize(
    "orientation, heights",
    [
        # Each direction within 1e-4 of its axis and of unit length, but
        # not perpendicular within 1e-4: their dot product is 1.8e-4.
        ((1, 9e-5, 0, 9e-5, 1, 0), (0.0, 2.0)),
        # Two slices whose offsets, rounded to 1e-6 mm, differ, but which
        # lie within 1e-6 mm of each other.
        ((1, 0, 0, 0, 1, 0), (4.9e-7, 1.39e-6)),
    ],
    ids=["not-perpendicular-within-the-alignment-tolerance", "nearly-one-position"],
)
def test_a_stack_the_old_test_takes_but_the_sampler_refuses_is_refused(
    orientation, heights
):
    positions = [(0.0, 0.0, height) for height in heights]
    assert defacing.along_patient_axes(orientation, positions)

    with pytest.raises(defacing.FaceBlockRefused) as refused:
        defacing.FaceFinder(orientation, positions, (1.0, 1.0), (6, 6))

    assert refused.value.problem is defacing.FaceBlockProblem.NOT_ALONG_PATIENT_AXES


def test_a_volume_without_slices_is_an_error():
    with pytest.raises(ValueError, match="position"):
        defacing.FaceFinder((1, 0, 0, 0, 1, 0), [], (1.0, 1.0), (10, 10))


def test_a_slice_of_other_rows_and_columns_is_an_error():
    scan = head.axial()
    finder = _finder(scan)

    with pytest.raises(ValueError, match="rows and columns"):
        finder.add(np.zeros((scan.shape[0] + 1, scan.shape[1]), np.float32))


def test_a_slice_beyond_the_last_is_an_error():
    scan = head.axial(extent=((-100, 100), (-130, 110), (-10, 0)))
    finder = _finder(scan)
    for values in scan.slices():
        finder.add(values)

    with pytest.raises(ValueError, match="every slice"):
        finder.add(np.zeros(scan.shape, np.float32))


@pytest.mark.parametrize(
    "scan", [head.axial(), head.sagittal()], ids=["axial", "sagittal"]
)
def test_the_distance_transform_in_slabs_gives_the_block_of_the_whole(
    scan, monkeypatch
):
    anatomy = head.Head(noise=0.0)
    monkeypatch.setattr(defacing, "_SLAB", 10**6)
    whole = _block(scan, anatomy)
    monkeypatch.setattr(defacing, "_SLAB", 3)

    assert _block(scan, anatomy) == whole


def test_an_orientation_of_other_than_six_values_is_an_error():
    with pytest.raises(ValueError, match="six values"):
        defacing.FaceFinder((1, 0, 0, 0, 1), [(0, 0, 0)], (1.0, 1.0), (10, 10))


@pytest.mark.parametrize(
    "positions",
    [[(0.0, 0.0)], [(0.0, 0.0, 0.0), (0.0, 0.0)], [[(0.0, 0.0, 0.0)]]],
    ids=["two-values", "ragged", "nested"],
)
def test_positions_not_of_three_values_are_an_error(positions):
    with pytest.raises(ValueError, match="position"):
        defacing.FaceFinder((1, 0, 0, 0, 1, 0), positions, (1.0, 1.0), (10, 10))


@pytest.mark.parametrize(
    "orientation, positions, spacing, shape",
    [
        ((1, 0, 0, 0, 1, math.nan), [(0, 0, 0)], (1.0, 1.0), (10, 10)),
        ((1, 0, 0, 0, 1, 0), [(0, 0, math.inf)], (1.0, 1.0), (10, 10)),
        ((1, 0, 0, 0, 1, 0), [(0, 0, "a")], (1.0, 1.0), (10, 10)),
        ((1, 0, 0, 0, 1, 0), [(0, 0, 0)], (1.0, math.nan), (10, 10)),
        ((1, 0, 0, 0, 1, 0), [(0, 0, 0)], (1.0,), (10, 10)),
        ((1, 0, 0, 0, 1, 0), [(0, 0, 0)], (0.0, 1.0), (10, 10)),
        ((1, 0, 0, 0, 1, 0), [(0, 0, 0)], (1.0, 1.0), (10,)),
        ((1, 0, 0, 0, 1, 0), [(0, 0, 0)], (1.0, 1.0), (10, 0)),
    ],
    ids=[
        "orientation-nan",
        "position-infinite",
        "position-text",
        "spacing-nan",
        "spacing-one-value",
        "spacing-zero",
        "shape-one-value",
        "shape-zero",
    ],
)
def test_geometry_that_is_not_finite_and_positive_is_an_error(
    orientation, positions, spacing, shape
):
    with pytest.raises(ValueError):
        defacing.FaceFinder(orientation, positions, spacing, shape)


def test_a_large_volume_is_sampled_more_coarsely_within_the_bound(monkeypatch):
    scan = head.axial(spacing=1.5, thickness=3.0)
    # About 2 mm voxels for the analytic head's volume.
    monkeypatch.setattr(defacing, "MAXIMUM_SAMPLED", 1 << 20)

    finder = _finder(scan)

    voxel = finder._voxel  # pylint: disable = protected-access
    assert defacing.MINIMUM_VOXEL < voxel <= defacing.MAXIMUM_VOXEL
    # Each globe within a voxel.
    _assert_around_the_globes(_block(scan), within=voxel)


def test_a_volume_that_needs_voxels_too_large_is_refused(monkeypatch):
    monkeypatch.setattr(defacing, "MAXIMUM_SAMPLED", 1 << 18)

    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _finder(head.axial(spacing=1.5, thickness=3.0))

    assert refused.value.problem is defacing.FaceBlockProblem.TOO_LARGE


def _inspect(scan: head.Scan, *heads: head.Head) -> defacing.FaceInspection:
    finder = _finder(scan)
    for values in scan.slices(*heads):
        finder.add(values)
    return finder.inspect()


def _kept_near(
    inspection: defacing.FaceInspection, point: tuple[float, float, float]
) -> list[int]:
    """The kept balls whose centres lie within 5 mm of a point."""
    return [
        index
        for index, ball in enumerate(inspection.balls)
        if ball.kept
        and ball.centre is not None
        and np.linalg.norm(np.subtract(ball.centre, point)) <= 5.0
    ]


_GLOBES = (
    (-head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
    (head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
)


@pytest.fixture(scope="module", name="inspection")
def _inspection() -> defacing.FaceInspection:
    return _inspect(head.axial())


def test_an_inspection_shows_each_globe_kept_and_their_pair_passing(inspection):
    (right,), (left,) = (_kept_near(inspection, globe) for globe in _GLOBES)
    (pair,) = [pair for pair in inspection.pairs if pair.eyes]

    assert (pair.right, pair.left) == (right, left)
    assert pair.side_by_side
    assert pair.lateral == pair.superior == (True, True)
    # Each globe lies under the skin in front, which an eyelid covers, and
    # deep in the head behind.
    assert pair.front is not None and pair.back is not None
    for front, back in zip(pair.front, pair.back):
        assert front.open and not back.open
        assert 0 < front.depth <= defacing.FRONT_REACH
        assert not front.bone and back.bone
    behind, in_front = inspection.head_fills(right, left)
    assert behind - in_front >= defacing.HEAD_BEHIND
    above, below = inspection.cranium(right, left)
    assert above > below
    assert inspection.block() == _block(head.axial())
    assert repr(inspection) == "FaceInspection()"


def test_an_inspection_shows_every_ball_considered_and_why_each_was_kept(inspection):
    radii = [ball.radius for ball in inspection.balls]
    kept = []

    assert radii == sorted(radii, reverse=True)
    for ball in inspection.balls:
        if ball.centre is None:
            # Not tested, as its deepest point lies within a ball kept before.
            assert not ball.kept
            assert ball.outside is None and ball.best_half is None
            assert any(
                np.linalg.norm(np.subtract(ball.peak, centre)) < radius
                for centre, radius in kept
            )
            continue
        deep = ball.radius - inspection.voxel >= 9.0
        assert ball.kept == (
            ball.outside is not None
            and ball.best_half is not None
            and ball.outside >= 0.5
            and ball.best_half >= (0.7 if deep else 0.8)
        )
        if ball.kept:
            kept.append((ball.centre, ball.radius))
    # Every two kept balls are tested as a pair, the one of lower x as the
    # patient's right.
    indices = [index for index, ball in enumerate(inspection.balls) if ball.kept]
    assert {(pair.right, pair.left) for pair in inspection.pairs} == {
        tuple(sorted(two, key=lambda index: inspection.balls[index].centre[0]))
        for two in itertools.combinations(indices, 2)
    }


@pytest.mark.parametrize(
    "front, expected",
    [
        (defacing.Front(defacing.FRONT_REACH, defacing.FRONT_FAT, False), True),
        (defacing.Front(-3.0, 0.0, False), True),
        (defacing.Front(defacing.FRONT_REACH + 0.5, 0.0, False), False),
        (defacing.Front(math.inf, 0.0, False), False),
        (defacing.Front(5.0, defacing.FRONT_FAT + 0.5, False), False),
        (defacing.Front(5.0, 0.0, True), False),
    ],
    ids=["at-the-limits", "air-within-the-radius", "deep", "no-air", "fat", "bone"],
)
def test_a_ball_is_open_to_air_only_just_under_the_skin(front, expected):
    assert front.open is expected


@pytest.mark.parametrize(
    "anatomy, reach",
    [(head.Head(), 6.0), (head.Head(bolus=True), 15.0)],
    ids=["eyelids", "bolus-over-the-eyes"],
)
def test_globes_deeper_under_the_skin_than_the_front_reach_are_refused(
    anatomy, reach, monkeypatch
):
    scan = head.axial()
    _assert_around_the_globes(_block(scan, anatomy))
    monkeypatch.setattr(defacing, "FRONT_REACH", reach)

    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(scan, anatomy)

    assert refused.value.problem is defacing.FaceBlockProblem.NO_EYES


def test_a_globe_that_its_muscles_border_on_every_half_is_kept(monkeypatch):
    # Extraocular muscles and an optic nerve, of soft tissue, touch each
    # half of the sphere about the globe. In HaN-Seg's CTs, 0.8 refused 7
    # globes of 0.6 to under 0.8, for soft tissue that the counts cannot
    # name.
    anatomy = head.Head(muscles=7.0)
    inspection = _inspect(head.axial(), anatomy)
    halves = [
        inspection.balls[index].best_half
        for globe in _GLOBES
        for index in _kept_near(inspection, globe)
    ]

    assert len(halves) == 2
    assert min(halves) < 0.8
    _assert_around_the_globes(inspection.block())
    monkeypatch.setattr(defacing, "_OUTSIDE_BEHIND_DEEP", 0.8)
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(head.axial(), anatomy)
    assert refused.value.problem is defacing.FaceBlockProblem.NO_EYES


@pytest.mark.parametrize("eyes", [(True, True), (False, False)], ids=["eyes", "none"])
def test_soft_tissue_over_the_face_is_not_taken_for_globes_at_coarse_voxels(
    eyes, monkeypatch
):
    # At 2.5 mm voxels, the layer of soft tissue over the analytic head's
    # cheekbones gives balls as deep as an infant's globe, with 0.7 to under
    # 0.8 of their best half outside it, which pair beside and below the
    # orbits; only a deeper ball, as an adult's globe is, is kept with less
    # than 0.8.
    scan = head.axial(
        spacing=2.5, thickness=5.0, extent=((-100, 100), (-130, 110), (-30, 110))
    )
    anatomy = head.Head(eyes=eyes)
    inspection = _inspect(scan, anatomy)
    shallow = [
        ball
        for ball in inspection.balls
        if ball.best_half is not None
        and 0.7 <= ball.best_half < 0.8
        and ball.radius - inspection.voxel < 9.0
    ]

    assert shallow and not any(ball.kept for ball in shallow)
    if any(eyes):
        _assert_around_the_globes(inspection.block(), within=inspection.voxel)
    else:
        with pytest.raises(defacing.FaceBlockRefused) as refused:
            inspection.block()
        assert refused.value.problem is defacing.FaceBlockProblem.NO_EYES
    monkeypatch.setattr(defacing, "_DEEP", 0.0)
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        _block(scan, anatomy)
    assert refused.value.problem is defacing.FaceBlockProblem.AMBIGUOUS_EYES


def test_a_volume_ending_just_above_the_globes_tests_them_as_its_edge_shows():
    # The sphere about each globe reaches 16 mm above its centre, beyond
    # the volume, whose top slice holds the orbits' roofs: the globes are
    # kept, and the volume is refused as showing no cranium above them.
    inspection = _inspect(
        head.axial(extent=((-100, 100), (-130, 110), (-120, head.GLOBE_Z + 15)))
    )

    for globe in _GLOBES:
        assert len(_kept_near(inspection, globe)) == 1
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        inspection.block()
    assert refused.value.problem is defacing.FaceBlockProblem.CRANIUM_NOT_ABOVE_EYES


def test_soft_tissue_cut_by_the_edge_of_the_field_of_view_is_not_a_globe():
    # The field of view's front edge cuts the eyelids and cheeks, 14 mm in
    # front of the globes' centres, within the spheres about them. Beyond
    # the edge, a sphere or a line takes the edge's soft tissue, not air, so
    # no ball is kept at the cut, and the globes, though kept, have no air
    # in front.
    inspection = _inspect(
        head.axial(extent=((-100, 100), (head.GLOBE_Y - 14, 110), (-120, 120)))
    )
    kept = [index for index, ball in enumerate(inspection.balls) if ball.kept]

    assert sorted(kept) == sorted(
        index for globe in _GLOBES for index in _kept_near(inspection, globe)
    )
    (pair,) = inspection.pairs
    assert pair.in_orbits and not pair.eyes
    assert pair.front is not None
    assert all(math.isinf(front.depth) for front in pair.front)
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        inspection.block()
    assert refused.value.problem is defacing.FaceBlockProblem.NO_EYES


@pytest.mark.parametrize("eyes", [(True, True), (False, False)], ids=["eyes", "none"])
def test_balls_in_bony_cups_behind_the_eyes_are_not_globes(eyes):
    # As a temporal lobe's pole lies in a middle cranial fossa. In HaN-Seg,
    # pairs below and behind the eyes, as such balls would be, passed the
    # other tests of a pair, leaving volumes with more than one pair, and 2
    # with only such a pair.
    anatomy = head.Head(poles=True, eyes=eyes)
    inspection = _inspect(head.axial(), anatomy)
    poles = [
        _kept_near(inspection, (side * head.POLE_X, head.POLE_Y, head.POLE_Z))
        for side in (-1, 1)
    ]
    (pair,) = [
        pair for pair in inspection.pairs if [[pair.right], [pair.left]] == poles
    ]

    assert pair.in_orbits and not pair.eyes
    assert pair.front is not None and pair.back is not None
    assert all(front.bone for front in pair.front)
    assert not any(back.open for back in pair.back)
    if any(eyes):
        _assert_around_the_globes(inspection.block())
        return
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        inspection.block()
    assert refused.value.problem is defacing.FaceBlockProblem.NO_EYES


def test_a_ball_at_an_orbit_apex_is_not_a_globe():
    # Paired with the other globe, it passes the other tests of a pair, as
    # 6 of HaN-Seg's other pairs, of a ball at an eye and one level with the
    # eyes but behind them, did.
    inspection = _inspect(head.axial(), head.Head(apex=True))
    (apex,) = _kept_near(inspection, head.APEX)
    (right,) = _kept_near(inspection, _GLOBES[0])
    (pair,) = [
        pair for pair in inspection.pairs if (pair.right, pair.left) == (right, apex)
    ]

    assert pair.in_orbits and not pair.eyes
    assert pair.front is not None
    front = pair.front[1]
    assert front.depth > defacing.FRONT_REACH and front.fat > defacing.FRONT_FAT
    _assert_around_the_globes(inspection.block())


def test_balls_one_above_the_other_are_a_pair_given_no_front_test():
    # Two balls of soft tissue in fat, their centres on the finder's voxels
    # and one directly above the other, as balls kept on one column of
    # voxels were in 15 of HaN-Seg's CTs: no horizontal line runs
    # perpendicular to the line between them, so only a pair in orbits is
    # given the front test.
    scan = head.axial(
        spacing=1.5, thickness=1.5, extent=((-39, 39), (-39, 39), (-39, 39))
    )
    finder = _finder(scan)
    for index in range(len(scan.positions)):
        points = scan.points(index)
        values = np.full(points.shape[:-1], -100.0)
        for z in (-16.5, 16.5):
            inside = np.linalg.norm(points - (0.0, 0.0, z), axis=-1) <= 11.0
            values = np.where(inside, 40.0, values)
        finder.add(values.astype(np.float32))
    inspection = finder.inspect()
    centres = [ball.centre for ball in inspection.balls if ball.kept]

    assert sorted(centres) == [(0.0, 0.0, -16.5), (0.0, 0.0, 16.5)]
    (pair,) = inspection.pairs
    assert not pair.side_by_side and not pair.in_orbits and not pair.eyes
    assert pair.front is None and pair.back is None
    with pytest.raises(defacing.FaceBlockRefused) as refused:
        inspection.block()
    assert refused.value.problem is defacing.FaceBlockProblem.NO_EYES


def test_the_depth_near_a_globe_is_about_its_radius(inspection):
    voxel = inspection.voxel

    for globe in _GLOBES:
        depth = inspection.depth_near(globe, 5.0)
        assert head.GLOBE_RADIUS - 2 * voxel <= depth <= head.GLOBE_RADIUS + voxel
    # Air before the face, and a point far outside the volume.
    assert inspection.depth_near((0.0, -125.0, 30.0), 5.0) == 0.0
    assert inspection.depth_near((0.0, -1000.0, 30.0), 5.0) == 0.0


def test_the_shell_of_a_ball_is_where_its_surround_was_tested(inspection):
    for index, ball in enumerate(inspection.balls):
        values = inspection.shell(index)
        if ball.centre is None:
            assert values is None and ball.outside is None
            continue
        assert values is not None
        soft = (values >= defacing.SOFT_TISSUE[0]) & (values <= defacing.SOFT_TISSUE[1])
        assert float(np.mean(~soft)) == ball.outside
    # The orbital fat borders each globe more than air does.
    for globe in _GLOBES:
        (index,) = _kept_near(inspection, globe)
        values = inspection.shell(index)
        assert values is not None
        fat = np.mean((values >= -200) & (values < defacing.SOFT_TISSUE[0]))
        assert fat > np.mean(values < defacing.BODY)


def test_only_tested_balls_are_tested_as_a_pair(inspection):
    untested = next(
        index for index, ball in enumerate(inspection.balls) if ball.centre is None
    )
    (pair,) = [pair for pair in inspection.pairs if pair.eyes]

    with pytest.raises(ValueError, match="tested ball"):
        inspection.head_fills(untested, pair.left)
    with pytest.raises(ValueError, match="tested ball"):
        inspection.cranium(pair.right, untested)


@pytest.mark.parametrize(
    "scan, anatomy, problem",
    [
        (head.axial(), head.Head(eyes=(True, False)), "no-eyes"),
        (head.axial(), head.Head(orbits=False, skull=False), "no-eyes"),
        (head.axial(), head.Head(facing_back=True), "head-not-behind-eyes"),
        (head.axial(), head.Head(upside_down=True), "cranium-not-above-eyes"),
    ],
    ids=["no-left-eye", "no-bony-orbits", "facing-back", "upside-down"],
)
def test_an_inspection_shows_which_test_refused_a_volume(scan, anatomy, problem):
    inspection = _inspect(scan, anatomy)
    # Where the globes would be in the head as it was recorded.
    globes = [
        (x, -y if anatomy.facing_back else y, -z if anatomy.upside_down else z)
        for x, y, z in _GLOBES
    ]
    right, left = (_kept_near(inspection, globe) for globe in globes)

    with pytest.raises(defacing.FaceBlockRefused) as refused:
        inspection.block()

    assert refused.value.problem.value == problem
    if not anatomy.eyes[1]:
        assert len(right) == 1 and not left
        assert inspection.depth_near(globes[1], 5.0) == 0.0
        assert not any(pair.eyes for pair in inspection.pairs)
        return
    (pair,) = [
        pair for pair in inspection.pairs if (pair.right, pair.left) == (*right, *left)
    ]
    if not anatomy.orbits:
        assert pair.side_by_side
        assert pair.lateral == pair.superior == (False, False)
        return
    assert pair.eyes
    behind, in_front = inspection.head_fills(pair.right, pair.left)
    above, below = inspection.cranium(pair.right, pair.left)
    assert (behind - in_front >= defacing.HEAD_BEHIND) is not anatomy.facing_back
    assert (above > below) is not anatomy.upside_down


def test_an_inspection_of_two_heads_shows_two_pairs_of_globes():
    scan = head.axial(spacing=1.5, extent=((-230, 230), (-130, 110), (-120, 120)))
    inspection = _inspect(scan, head.Head(shift=-120.0), head.Head(shift=120.0))

    passing = [pair for pair in inspection.pairs if pair.eyes]

    assert len(passing) == 2
    for pair, shift in zip(
        sorted(passing, key=lambda pair: inspection.balls[pair.right].peak[0]),
        (-120.0, 120.0),
    ):
        for index, (x, y, z) in zip((pair.right, pair.left), _GLOBES):
            centre = inspection.balls[index].centre
            assert centre is not None
            np.testing.assert_allclose(centre, (x + shift, y, z), atol=1.5)


def test_an_inspection_needs_every_slice():
    scan = head.axial()
    finder = _finder(scan)
    for values, _ in zip(scan.slices(), range(len(scan.positions) - 1)):
        finder.add(values)

    with pytest.raises(ValueError, match="every slice"):
        finder.inspect()
