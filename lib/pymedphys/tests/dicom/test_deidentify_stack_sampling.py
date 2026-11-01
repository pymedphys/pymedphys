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

"""Sampling tilted, sheared, and oblique stacks of slices to voxels along the
patient's axes.

Each expected value is found independently of the sampler: by testing every
voxel against every slice and pixel, by today's sampling of stacks along the
patient's axes (:mod:`~pymedphys._dicom.deidentify.qc_surfaces`), or from the
analytic head, whose anatomy is known.
"""

from __future__ import annotations

import dataclasses
import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest, scipy

from pymedphys._dicom.deidentify import defacing, qc_surfaces, stack_sampling

from . import _synthetic_head as head

# Within this, in millimetres or pixels, the sampler counts two slices or
# two pixels as equally near.
TIE = 1e-6


def _rotation(about_x: float = 0.0, about_y: float = 0.0, about_z: float = 0.0):
    """The rotation by these degrees about x, then y, then z."""
    a, b, c = (math.radians(angle) for angle in (about_x, about_y, about_z))
    x = np.array(
        [[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]]
    )
    y = np.array(
        [[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]]
    )
    z = np.array(
        [[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]]
    )
    return z @ y @ x


def _oblique(scan: head.Scan, rotation: np.ndarray) -> head.Scan:
    """``scan`` with its rows, columns, and slices turned about its middle."""
    along_row = rotation @ np.array(scan.orientation[:3])
    down_column = rotation @ np.array(scan.orientation[3:])
    middle = np.mean(
        [scan.points(0)[0, 0], scan.points(len(scan.positions) - 1)[-1, -1]], axis=0
    )
    positions = tuple(
        tuple(
            float(value) for value in middle + rotation @ (np.array(position) - middle)
        )
        for position in scan.positions
    )
    orientation = tuple(float(value) for value in (*along_row, *down_column))
    return dataclasses.replace(scan, orientation=orientation, positions=positions)


def _sheared(scan: head.Scan, degrees: float) -> head.Scan:
    """``scan``, an axial one from inferior up, with each slice offset
    anteriorly from the last by its step times the tangent of ``degrees``,
    as a gantry tilt is recorded with axial direction cosines."""
    steps = [z - scan.positions[0][2] for _, _, z in scan.positions]
    slope = math.tan(math.radians(degrees))
    positions = tuple(
        (x, y - step * slope, z) for (x, y, z), step in zip(scan.positions, steps)
    )
    return dataclasses.replace(scan, positions=positions)


def _small(
    orientation=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    steps=(0.0, 2.1, 4.2, 6.3, 8.4, 10.5, 12.6, 14.7),
    along=(0.0, 0.0, 1.0),
    spacing=(1.3, 0.9),
    shape=(9, 11),
) -> head.Scan:
    """A small stack: each slice's first pixel at ``steps`` along ``along``
    from the origin."""
    positions = tuple(
        tuple(float(value) for value in step * np.array(along)) for step in steps
    )
    return head.Scan(tuple(orientation), positions, spacing, shape)


def _orientation(rotation: np.ndarray, flip: tuple[float, float] = (1.0, 1.0)):
    along_row = flip[0] * rotation @ np.array([1.0, 0.0, 0.0])
    down_column = flip[1] * rotation @ np.array([0.0, 1.0, 0.0])
    return tuple(float(value) for value in (*along_row, *down_column))


_TILT_15 = _orientation(_rotation(about_x=-15.0))

SMALL = {
    "axial": _small(),
    "gantry-tilt-15": _small(orientation=_TILT_15),
    "gantry-tilt-30-feet-first": _small(
        orientation=_orientation(_rotation(about_x=-30.0), flip=(-1.0, 1.0)),
        steps=(0.0, -2.1, -4.2, -6.3),
    ),
    "sheared": _small(along=(0.0, -math.tan(math.radians(15.0)), 1.0)),
    "oblique-about-z": _small(orientation=_orientation(_rotation(about_z=10.0))),
    "compound-oblique": _small(
        orientation=_orientation(_rotation(about_x=25.0, about_y=-35.0, about_z=50.0)),
        along=_rotation(about_x=25.0, about_y=-35.0, about_z=50.0)
        @ np.array([0.2, -0.1, 1.0]),
    ),
    "uneven-and-unordered": _small(
        orientation=_TILT_15, steps=(6.0, 0.0, 1.0, 9.5, 2.5, 3.0, 20.0)
    ),
    "one-slice-oblique": _small(
        orientation=_orientation(_rotation(about_y=20.0)), steps=(0.0,)
    ),
}


def _coded(scan: head.Scan) -> list[np.ndarray]:
    """Each slice's pixels, each holding its own slice, row, and column."""
    rows, columns = scan.shape
    return [
        (index * rows * columns + np.arange(rows * columns))
        .reshape(rows, columns)
        .astype(np.float32)
        for index in range(len(scan.positions))
    ]


def _sampled(scan: head.Scan, voxel: float, frames, every_slice=False, order=None):
    stack = stack_sampling.Stack(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )
    volume = stack_sampling.SampledVolume(
        stack_sampling.StackSampler(stack, stack.lattice(voxel)), every_slice
    )
    for index in range(len(frames)) if order is None else order:
        volume.add(frames[index], index)
    return volume


def _expected_lattice(scan: head.Scan, voxel: float):
    """The first voxel's x, y, and z, and the lattice's shape, from every
    pixel's centre."""
    points = np.concatenate(
        [scan.points(index).reshape(-1, 3) for index in range(len(scan.positions))]
    )
    low, high = points.min(axis=0), points.max(axis=0)
    counts = [
        math.floor((high[axis] - low[axis]) / voxel + 1e-6) + 1 for axis in range(3)
    ]
    return (low[0], low[1], high[2]), (counts[2], counts[1], counts[0])


def _expected_nearest(scan: head.Scan, voxel: float) -> np.ndarray:
    """The coded value each voxel takes, by testing it against every slice
    and pixel; NaN where it takes none."""
    first, shape = _expected_lattice(scan, voxel)
    k, j, i = np.indices(shape).reshape(3, -1)
    centres = np.stack(
        [first[0] + i * voxel, first[1] + j * voxel, first[2] - k * voxel], axis=-1
    )
    along_row = np.array(scan.orientation[:3])
    down_column = np.array(scan.orientation[3:])
    normal = np.cross(along_row, down_column)
    normal /= np.linalg.norm(normal)
    origins = np.array(scan.positions)
    offsets = origins @ normal
    ascending = np.sort(offsets)
    if len(ascending) > 1:
        below = (ascending[1] - ascending[0]) / 2
        above = (ascending[-1] - ascending[-2]) / 2
    else:
        below = above = voxel / 2
    dominant = int(np.argmax(np.abs(normal)))
    shift = TIE if normal[dominant] > 0 else -TIE
    depth = centres @ normal
    inside = (depth > ascending[0] - below + shift) & (
        depth <= ascending[-1] + above + shift
    )
    apart = np.abs(depth[:, None] - offsets[None, :])
    near = apart <= apart.min(axis=1, keepdims=True) + TIE
    # Of equally near slices, the one of lower coordinate along the axis
    # that the normal lies most nearly along.
    preference = offsets if normal[dominant] > 0 else -offsets
    nearest = np.argmin(np.where(near, preference[None, :], np.inf), axis=1)
    rows, columns = scan.shape
    fraction_row = (centres - origins[nearest]) @ down_column / scan.spacing[0]
    fraction_column = (centres - origins[nearest]) @ along_row / scan.spacing[1]
    picked = []
    for fraction, direction in (
        (fraction_row, down_column),
        (fraction_column, along_row),
    ):
        lower = direction[int(np.argmax(np.abs(direction)))] > 0
        picked.append(np.floor(fraction + 0.5 + (-TIE if lower else TIE)).astype(int))
    row, column = picked
    taken = inside & (row >= 0) & (row < rows) & (column >= 0) & (column < columns)
    expected = np.full(len(centres), np.nan, np.float32)
    expected[taken] = (
        nearest[taken] * rows * columns + row[taken] * columns + column[taken]
    )
    return expected.reshape(shape)


@pytest.mark.parametrize("voxel", [0.7, 1.0, 1.7])
@pytest.mark.parametrize("scan", SMALL.values(), ids=SMALL.keys())
def test_each_voxel_takes_the_nearest_slice_then_the_nearest_pixel_in_it(scan, voxel):
    volume = _sampled(scan, voxel, _coded(scan))

    first, shape = _expected_lattice(scan, voxel)
    lattice = volume.sampler.lattice
    assert lattice.shape == shape
    np.testing.assert_allclose(lattice.first, first, atol=1e-9)
    expected = _expected_nearest(scan, voxel)
    np.testing.assert_array_equal(volume.values, expected)
    # Some voxels, but not every one of a tilted or oblique stack's, take a
    # pixel.
    assert np.isfinite(expected).any()


def _today(scan: head.Scan, voxel: float, frames, every_slice: bool) -> np.ndarray:
    """Sampled as the face finder (nearest) and the surface renders (every
    slice) sample a stack along the patient's axes today."""
    along_row = np.array(scan.orientation[:3])
    down_column = np.array(scan.orientation[3:])
    normal = np.cross(along_row, down_column)
    offsets = np.array(scan.positions) @ normal
    grid = qc_surfaces.grid(
        (normal, down_column, along_row),
        [float(offset) for offset in offsets],
        scan.spacing,
        scan.shape,
        qc_surfaces.Threshold.CT,
    )
    taken = [
        qc_surfaces.sampled_indices(np.asarray(coordinates), axis, voxel)
        for coordinates, axis in zip(grid.coordinates, grid.axes)
    ]
    nearest = qc_surfaces.nearest_voxels(
        np.asarray(grid.coordinates[0]), grid.axes[0], voxel
    )
    samples = np.full(tuple(len(each) for each in taken), np.nan, np.float32)
    for index, frame in enumerate(frames):
        wanted = np.flatnonzero(taken[0] == index)
        values = frame[np.ix_(taken[1], taken[2])]
        if every_slice:
            wanted = np.union1d(wanted, nearest[index])
            samples[wanted] = np.fmax(samples[wanted], values)
        elif wanted.size:
            samples[wanted] = values
    return np.transpose(samples, [grid.axes.index(axis) for axis in (2, 1, 0)])


ALIGNED = {
    "head-first-supine": head.axial(),
    "prone-feet-first": head.axial(prone=True, feet_first=True),
    "sagittal": head.sagittal(),
    "fine-pixels": head.axial(spacing=0.8, extent=((-80, 80), (-100, 100), (-40, 60))),
    # Slices closer than the voxels, some midway between two.
    "thin-slices": head.axial(thickness=0.5, extent=((-80, 80), (-100, 100), (0, 40))),
    "slices-shuffled": dataclasses.replace(
        head.axial(),
        positions=tuple(
            head.axial().positions[index]
            for index in np.random.default_rng(5).permutation(
                len(head.axial().positions)
            )
        ),
    ),
    "wide-gap": dataclasses.replace(
        head.axial(),
        positions=tuple((-100.0, -130.0, float(z)) for z in np.arange(-400, -120, 40))
        + head.axial().positions,
    ),
    "one-slice": dataclasses.replace(head.axial(), positions=((-100.0, -130.0, 20.0),)),
}


@pytest.mark.parametrize("every_slice", [False, True], ids=["nearest", "every-slice"])
@pytest.mark.parametrize("voxel", [1.0, 1.5, 2.0])
@pytest.mark.parametrize("scan", ALIGNED.values(), ids=ALIGNED.keys())
def test_a_stack_along_the_patient_axes_is_sampled_as_today(scan, voxel, every_slice):
    frames = list(scan.slices(head.Head(seed=7)))

    volume = _sampled(scan, voxel, frames, every_slice)

    np.testing.assert_array_equal(
        volume.values, _today(scan, voxel, frames, every_slice)
    )
    assert np.isfinite(volume.values).all()


@pytest.mark.parametrize("every_slice", [False, True], ids=["nearest", "every-slice"])
def test_slices_added_in_any_order_give_the_same_volume(every_slice):
    scan = SMALL["uneven-and-unordered"]
    frames = _coded(scan)
    order = np.random.default_rng(11).permutation(len(frames))

    shuffled = _sampled(scan, 1.0, frames, every_slice, order=order.tolist())

    np.testing.assert_array_equal(
        shuffled.values, _sampled(scan, 1.0, frames, every_slice).values
    )


def test_thin_slices_are_each_drawn_where_every_slice_is_asked_for():
    # Tilted slices 0.4 mm apart, sampled to 2 mm voxels, so that each is
    # nearest the centres of few voxels.
    scan = _small(
        orientation=_orientation(_rotation(about_x=-20.0)),
        steps=tuple(0.4 * step for step in range(30)),
        shape=(24, 20),
        spacing=(1.0, 1.0),
    )
    voxel = 2.0
    stack = stack_sampling.Stack(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )
    lattice = stack.lattice(voxel)
    normal = stack.normal
    missed = 0
    for bright, position in enumerate(scan.positions):
        frames = [np.full(scan.shape, -1000.0, np.float32) for _ in scan.positions]
        frames[bright][:] = 1000.0
        nearest = _sampled(scan, voxel, frames).values
        drawn = _sampled(scan, voxel, frames, every_slice=True).values

        # Each pixel at least a voxel within the slice's edges lies on a line
        # of voxels along z, the axis that the normal lies most nearly
        # along, that holds a voxel that draws the slice.
        points = scan.points(bright)[2:-2, 2:-2].reshape(-1, 3)
        across = np.rint((points[:, :2] - np.array(lattice.first[:2])) / voxel)
        across = np.minimum(across.astype(int), np.array(lattice.shape[:0:-1]) - 1)
        drawn_lines = (drawn > 0).any(axis=0)[across[:, 1], across[:, 0]]
        assert drawn_lines.all(), bright
        missed += not (nearest > 0).any(axis=0)[across[:, 1], across[:, 0]].all()
        # Each voxel that draws it lies within a voxel's extent along the
        # normal of its plane.
        centres = lattice.points(np.nonzero(drawn > 0))
        apart = np.abs((centres - np.array(position)) @ normal)
        assert apart.max() <= voxel * np.abs(normal).sum() + 1e-9
    # Nearest neighbour alone leaves most of them out somewhere.
    assert missed > len(scan.positions) // 2


def test_every_slice_keeps_the_nearest_slices_values_and_adds_the_crossings():
    scan = SMALL["gantry-tilt-15"]
    frames = _coded(scan)

    nearest = _sampled(scan, 1.7, frames).values
    drawn = _sampled(scan, 1.7, frames, every_slice=True).values

    sampled = np.isfinite(nearest)
    assert (drawn[sampled] >= nearest[sampled]).all()
    assert np.isfinite(drawn).sum() >= sampled.sum()


# The analytic head scanned with a tilt reaching its crown and chin, and
# with a shear reaching the back of its head.
_TALL = ((-100, 100), (-130, 110), (-160, 200))
_DEEP = ((-100, 100), (-130, 180), (-120, 120))
TILTED_HEADS = {
    "gantry-tilt-half-degree": head.tilted(degrees=0.5),
    "gantry-tilt-15": head.tilted(degrees=15.0, extent=_TALL),
    "gantry-tilt-30": head.tilted(degrees=30.0, extent=_TALL),
    "gantry-tilt-15-sheared": _sheared(head.axial(extent=_DEEP), 15.0),
    "oblique-about-z-10": _oblique(head.axial(), _rotation(about_z=10.0)),
    "compound-oblique": _oblique(head.axial(), _rotation(about_x=12.0, about_y=-8.0)),
}


def _classes(values: np.ndarray) -> np.ndarray:
    """Air, fat, soft tissue, or bone, as 0 to 3."""
    return np.digitize(values, [-500.0, -60.0, 300.0])


def _misclassified(scan: head.Scan, voxel: float) -> tuple[float, np.ndarray]:
    """The share of sampled voxels of the noiseless head whose tissue
    differs from the head's at their centres, and the voxels near the eyes,
    which the stack covers."""
    anatomy = head.Head(noise=0.0)
    volume = _sampled(scan, voxel, list(scan.slices(anatomy)))
    lattice = volume.sampler.lattice
    centres = lattice.points(np.indices(lattice.shape))
    values = volume.values
    sampled = np.isfinite(values)
    differs = _classes(values[sampled]) != _classes(
        head.hounsfield(centres[sampled], anatomy)
    )
    near_the_eyes = (
        (np.abs(centres[..., 0]) < head.GLOBE_X + 25)
        & (np.abs(centres[..., 1] - head.GLOBE_Y) < 25)
        & (np.abs(centres[..., 2] - head.GLOBE_Z) < 25)
    )
    return float(differs.mean()), sampled[near_the_eyes]


@pytest.mark.parametrize("scan", TILTED_HEADS.values(), ids=TILTED_HEADS.keys())
def test_a_tilted_head_samples_to_the_head_as_it_lies(scan):
    voxel = 2.0

    differs, near_the_eyes = _misclassified(scan, voxel)

    assert near_the_eyes.all()
    # Nearest neighbour moves each edge by up to half a slice along the
    # normal and half a pixel each way within the slice, whatever the tilt,
    # so a tilted head is no further from the head as it lies than the
    # untilted head is: about 0.6% of voxels.
    untilted, _ = _misclassified(head.axial(), voxel)
    assert 0 < untilted < 0.01
    assert differs < 2 * untilted


def _block(values: np.ndarray, lattice: stack_sampling.Lattice) -> defacing.FaceBlock:
    """The face block of a sampled volume, averaged as the face finder
    averages it, with the lattice's heights as the volume's."""
    averaged = scipy.ndimage.uniform_filter(
        np.nan_to_num(values, nan=-1000.0), size=3, mode="nearest"
    )
    heights = np.sort(lattice.coordinates[0])
    return defacing.FaceInspection(
        averaged, np.array(lattice.first), lattice.voxel, heights
    ).block()


@pytest.mark.parametrize("scan", TILTED_HEADS.values(), ids=TILTED_HEADS.keys())
def test_a_tilted_head_sampled_gives_the_untilted_heads_face_block(scan):
    voxel = defacing.MINIMUM_VOXEL
    anatomy = head.Head(seed=3)
    untilted = head.axial()
    finder = defacing.FaceFinder(
        untilted.orientation, untilted.positions, untilted.spacing, untilted.shape
    )
    for frame in untilted.slices(anatomy):
        finder.add(frame)
    expected = finder.block()

    volume = _sampled(scan, voxel, list(scan.slices(anatomy)))
    block = _block(volume.values, volume.sampler.lattice)

    truth = (
        (-head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
        (head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
    )
    np.testing.assert_allclose(block.globes, truth, atol=1.5)
    np.testing.assert_allclose(block.globes, expected.globes, atol=voxel)
    np.testing.assert_allclose(block.anterior, (0, -1, 0), atol=0.02)
    np.testing.assert_allclose(block.origin, expected.origin, atol=voxel)
    inferior_edge = head.GLOBE_Z - head.GLOBE_RADIUS
    assert inferior_edge - 10.0 <= block.inferior_limit <= inferior_edge


@pytest.mark.parametrize(
    "orientation",
    [
        (1.0, 0.0, 0.0, 0.0, 1.01, 0.0),
        (0.999, 0.0, 0.0, 0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0, 0.01, 1.0, 0.0),
    ],
    ids=["column-too-long", "row-too-short", "not-perpendicular"],
)
def test_directions_not_of_unit_length_or_not_perpendicular_are_refused(orientation):
    scan = _small()

    with pytest.raises(stack_sampling.StackRefused) as refused:
        stack_sampling.Stack(orientation, scan.positions, scan.spacing, scan.shape)

    assert refused.value.problem is stack_sampling.StackProblem.NOT_ORTHONORMAL


def test_directions_within_the_tolerance_are_kept():
    scan = _small()
    stretch = 1 + 0.5 * stack_sampling.ORTHONORMAL_TOLERANCE

    stack_sampling.Stack(
        (stretch, 0.0, 0.0, 0.0, 1.0, 0.0), scan.positions, scan.spacing, scan.shape
    )


def test_two_slices_at_one_position_along_the_normal_are_refused():
    # The second is offset only within the first's plane.
    scan = _small(orientation=_TILT_15)
    in_plane = 3.0 * np.array(scan.orientation[3:])
    positions = (scan.positions[0], tuple(np.array(scan.positions[0]) + in_plane))

    with pytest.raises(stack_sampling.StackRefused) as refused:
        stack_sampling.Stack(scan.orientation, positions, scan.spacing, scan.shape)

    assert refused.value.problem is stack_sampling.StackProblem.SLICES_AT_ONE_POSITION


@pytest.mark.parametrize(
    "orientation, positions, spacing, shape, message",
    [
        ((1.0, 0.0, 0.0, 0.0, 1.0), ((0.0, 0.0, 0.0),), (1.0, 1.0), (2, 2), "six"),
        (
            (1.0, 0.0, 0.0, 0.0, math.nan, 0.0),
            ((0.0, 0.0, 0.0),),
            (1.0, 1.0),
            (2, 2),
            "finite",
        ),
        ((1.0, 0.0, 0.0, 0.0, 1.0, 0.0), (), (1.0, 1.0), (2, 2), "position"),
        ((1.0, 0.0, 0.0, 0.0, 1.0, 0.0), ((0.0, 0.0),), (1.0, 1.0), (2, 2), "position"),
        (
            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            ((0.0, 0.0, 0.0),),
            (1.0, 0.0),
            (2, 2),
            "Pixel",
        ),
        (
            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            ((0.0, 0.0, 0.0),),
            (1.0, 1.0),
            (2, 0),
            "rows",
        ),
        (
            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            ((0.0, 0.0, 0.0),),
            (1.0, 1.0),
            (True, 2),
            "rows",
        ),
    ],
)
def test_malformed_geometry_is_rejected(
    orientation, positions, spacing, shape, message
):
    with pytest.raises(ValueError, match=message):
        stack_sampling.Stack(orientation, positions, spacing, shape)


@pytest.mark.parametrize("voxel", [0.0, -1.0, math.inf, math.nan])
def test_a_voxel_must_have_a_positive_finite_side(voxel):
    scan = _small()
    stack = stack_sampling.Stack(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )

    with pytest.raises(ValueError, match="voxel"):
        stack.lattice(voxel)


def test_a_sampled_volume_needs_every_slice_and_slices_of_its_shape():
    scan = _small()
    stack = stack_sampling.Stack(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )
    volume = stack_sampling.SampledVolume(
        stack_sampling.StackSampler(stack, stack.lattice(1.0))
    )
    frames = _coded(scan)

    with pytest.raises(ValueError, match="rows and columns"):
        volume.add(np.zeros((2, 2)))
    with pytest.raises(ValueError, match="no slice"):
        volume.add(frames[0], len(frames))
    for frame in frames[:-1]:
        volume.add(frame)
    # Added twice, it counts once.
    volume.add(frames[0], 0)
    assert not volume.complete
    with pytest.raises(ValueError, match="every slice"):
        _ = volume.values
    volume.add(frames[-1], len(frames) - 1)
    assert volume.complete
    with pytest.raises(IndexError):
        volume.sampler.nearest(len(frames))


def test_a_stack_reports_its_geometry_without_letting_it_change():
    scan = SMALL["gantry-tilt-15"]
    stack = stack_sampling.Stack(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )

    stack.normal[:] = 0
    stack.origins[:] = 0

    np.testing.assert_allclose(
        stack.normal, (0, math.sin(math.radians(15.0)), math.cos(math.radians(15.0)))
    )
    np.testing.assert_allclose(stack.origins, scan.positions)
    np.testing.assert_allclose(
        stack.pixel_points(3, np.arange(9)[:, None], np.arange(11)[None, :]),
        scan.points(3),
    )
    assert stack.smallest_spacing == pytest.approx(
        min(0.9, 2.1 * math.cos(math.radians(15.0)))
    )
