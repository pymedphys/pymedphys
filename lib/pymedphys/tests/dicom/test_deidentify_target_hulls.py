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

"""The targets' hulls that defacing keeps in a face block, and the RT Dose
voxels and contours that they keep. Every value here is invented."""

from __future__ import annotations

import itertools

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest, scipy

from pymedphys._dicom.deidentify.defacing import FaceBlock
from pymedphys._dicom.deidentify.dose_defacing import DoseBlock
from pymedphys._dicom.deidentify.face_blocks import KeptSlice
from pymedphys._dicom.deidentify.region_defacing import cut_contours
from pymedphys._dicom.deidentify.target_hulls import (
    KeptTargets,
    SliceRange,
    TargetHull,
    beyond_slices,
    slice_ranges,
    slice_reach,
)

from . import _synthetic_head_dicom as files

# The block holds the points with y below 0 and z above 0: anterior is -y.
_BLOCK = FaceBlock((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), 0.0, ((0, 0, 0), (0, 0, 0)))
_AXIAL = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def _inside_hull(vertices: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Whether each point lies in the convex hull of vertices spanning three
    dimensions, by Delaunay's simplices, independently of the module."""
    # Qhull's bindings are compiled, so pylint cannot see their members.
    triangulation = scipy.spatial.Delaunay(vertices)  # pylint: disable = no-member
    return triangulation.find_simplex(points) >= 0


def _box(low, high) -> np.ndarray:
    """The eight corners of an axis-aligned box."""
    return np.array(list(itertools.product(*zip(low, high))), dtype=float)


# A hull's points.


def test_a_hull_holds_its_points_and_their_combinations_and_nothing_far():
    rng = np.random.default_rng(0)
    points = rng.normal(size=(300, 3)) * (20.0, 10.0, 5.0) + (5.0, -30.0, 40.0)
    hull = TargetHull.of(points)
    weights = rng.dirichlet(np.ones(len(points)), size=200)
    probes = rng.uniform(-80, 80, size=(4000, 3)) + (5.0, -30.0, 40.0)

    assert hull.contains(points).all()
    assert hull.contains(weights @ points).all()
    expected = _inside_hull(points, probes)

    # It holds what the independent hull holds, and nothing else, but for
    # points within the margin of its surface, which none of these is.
    assert expected.any() and not expected.all()
    assert np.array_equal(hull.contains(probes), expected)
    assert repr(hull) == "TargetHull()"


@pytest.mark.parametrize(
    "points",
    [
        # On one axial slice, as a target drawn on one CT slice is.
        files.circle((10.0, -20.0, 30.0), 8.0),
        # On one oblique plane.
        np.array([(0, 0, 0), (10, 0, 10), (0, 10, 0), (10, 10, 10)], float),
        # On one line, and a single point, as a POINT target is.
        np.array([(0, 0, 0), (10, 5, 2)], float),
        np.array([(3.0, -4.0, 5.0)]),
    ],
    ids=["axial", "oblique", "line", "point"],
)
def test_a_flat_hull_holds_its_points_and_no_thickness(points):
    hull = TargetHull.of(points)
    centre = points.mean(axis=0)
    _, _, axes = np.linalg.svd(points - centre)

    assert hull.contains(points).all()
    assert hull.contains(centre[np.newaxis])
    # Off its plane, line, or point by more than the margin, nothing.
    for axis in axes[np.ptp((points - centre) @ axes.T, axis=0) <= 1e-9]:
        assert not hull.contains((centre + 0.05 * axis)[np.newaxis]).any()
        assert hull.contains((centre + 0.005 * axis)[np.newaxis]).all()


def test_a_hull_needs_finite_points():
    with pytest.raises(ValueError):
        TargetHull.of(np.empty((0, 3)))
    with pytest.raises(ValueError):
        TargetHull.of(np.array([(0.0, np.nan, 0.0), (1.0, 1.0, 1.0)]))
    assert not TargetHull.of(np.array([(0.0, 0.0, 0.0)])).contains(
        np.array([(np.nan, 0.0, 0.0)])
    )


# The boxes of a slice's pixels.


def _pixel_boxes_met(vertices, position, orientation, spacing, shape, depth):
    """Which pixels' boxes hold a point of the hull, by sampling each box
    densely and testing the samples with Delaunay's simplices."""
    along_row, down_column = np.array(orientation[:3]), np.array(orientation[3:])
    normal = np.cross(along_row, down_column)
    steps = np.linspace(-1, 1, 9)
    offsets = np.array(
        [
            s * along_row * spacing[1] / 2
            + t * down_column * spacing[0] / 2
            + u * normal * depth
            for s, t, u in itertools.product(steps, steps, steps)
        ]
    )
    rows, columns = np.mgrid[0 : shape[0], 0 : shape[1]]
    centres = (
        np.asarray(position)
        + columns[..., np.newaxis] * spacing[1] * along_row
        + rows[..., np.newaxis] * spacing[0] * down_column
    ).reshape(-1, 3)
    samples = centres[:, np.newaxis, :] + offsets[np.newaxis]
    met = _inside_hull(vertices, samples.reshape(-1, 3)).reshape(len(centres), -1)
    return met.any(axis=1).reshape(shape)


@pytest.mark.parametrize(
    "orientation",
    [_AXIAL, (-1.0, 0.0, 0.0, 0.0, -1.0, 0.0), (0.0, 1.0, 0.0, 0.0, 0.0, -1.0)],
    ids=["axial", "axial-prone", "sagittal"],
)
def test_every_pixel_whose_box_meets_a_tilted_hull_is_kept(orientation):
    rng = np.random.default_rng(1)
    rotation = scipy.spatial.transform.Rotation.from_euler("xyz", (20, 35, -15), True)
    vertices = rotation.apply(_box((-6, -4, -3), (6, 4, 3))) + (1.3, -2.1, 0.7)
    vertices += rng.normal(scale=0.2, size=vertices.shape)
    hull = TargetHull.of(vertices)
    kept = KeptTargets((hull,), depth=1.25)
    along_row, down_column = np.array(orientation[:3]), np.array(orientation[3:])
    normal = np.cross(along_row, down_column)
    # An off-centre grid of 1.5 by 2 mm pixels, its plane 0.9 mm from the
    # hull's centre.
    position = (
        (1.3, -2.1, 0.7) + 0.9 * normal - 11 * 2.0 * along_row - 9 * 1.5 * down_column
    )
    shape = (19, 23)

    found = kept.slice_mask(position, orientation, (1.5, 2.0), shape)
    expected = _pixel_boxes_met(
        vertices, position, orientation, (1.5, 2.0), shape, 1.25
    )

    assert expected.any()
    assert found[expected].all()
    # The test may keep a box near an edge or a corner of the hull that the
    # samples miss, never many.
    assert np.count_nonzero(found & ~expected) <= 0.3 * np.count_nonzero(expected)


def test_the_pixels_kept_for_an_axis_aligned_box_are_those_whose_boxes_meet_it():
    # A box from x = -3 to 3, y = -10 to -4, and z = 9 to 11: on a slice at
    # z = 12 whose pixels reach 1.5 mm either side, the pixels at 1 mm whose
    # squares meet it, from x = -3.5 to 3.5 and y = -10.5 to -3.5.
    hull = TargetHull.of(_box((-3, -10, 9), (3, -4, 11)))
    kept = KeptTargets((hull,), depth=1.5)
    x = np.arange(-20, 21)[np.newaxis, :]
    y = np.arange(-20, 21)[:, np.newaxis]

    near = kept.slice_mask((-20.0, -20.0, 12.0), _AXIAL, (1.0, 1.0), (41, 41))
    far = kept.slice_mask((-20.0, -20.0, 12.6), _AXIAL, (1.0, 1.0), (41, 41))

    expected = (np.abs(x) <= 3) & (y >= -10) & (y <= -4)
    assert np.array_equal(near, expected)
    assert not far.any()
    assert not KeptTargets().slice_mask((0, 0, 0), _AXIAL, (1, 1), (3, 3)).any()


def test_the_kept_targets_are_checked():
    with pytest.raises(ValueError):
        KeptTargets((), 1.0, in_block=True)
    with pytest.raises(ValueError):
        KeptTargets((), float("nan"))
    with pytest.raises(ValueError):
        KeptTargets((), -1.0)
    assert repr(KeptTargets((TargetHull.of(_box((0, 0, 0), (1, 1, 1))),))) == (
        "KeptTargets(hulls=1)"
    )


# The slices' reach and extent.


def test_a_point_reaches_its_nearest_slice_within_half_the_smallest_spacing():
    assert slice_reach([0.0, 2.0, 4.0, 7.0], (1.0, 1.0)) == 1.0
    # A slice given twice is one slice.
    assert slice_reach([7.0, 0.0, 0.0, 4.0], (1.0, 1.0)) == 1.5
    assert slice_reach([3.0], (0.8, 1.2)) == 0.6


def test_the_slices_extend_half_a_pixel_beyond_their_edge_centres_and_depth_beyond():
    slices = [((-10.0, -20.0, z), _AXIAL) for z in (0.0, 2.0, 4.0)]
    # One slice shifted along its rows: only where all reach counts.
    slices.append(((-9.0, -20.0, 6.0), _AXIAL))

    along_row, down_column, normal = slice_ranges(slices, (2.0, 1.0), (11, 21), 1.0)

    assert along_row == SliceRange((1.0, 0.0, 0.0), -9.5, 10.5)
    assert down_column == SliceRange((0.0, 1.0, 0.0), -21.0, 1.0)
    assert normal == SliceRange((0.0, 0.0, 1.0), -1.0, 7.0)


@pytest.mark.parametrize(
    ("low", "high", "beyond"),
    [
        ((-3, -10, 1), (3, -4, 6), False),
        # Above the last slice's reach, in the block.
        ((-3, -10, 1), (3, -4, 7.5), True),
        # Beyond the pixels along a row, in the block.
        ((-3, -10, 1), (11, -4, 6), True),
        # Beyond the slices but behind the block's plane, and below it.
        ((-3, 1, 1), (3, 4, 30), False),
        ((-3, -10, -30), (3, -4, -1), False),
    ],
    ids=["within", "above", "beside", "behind-the-plane", "below-the-block"],
)
def test_a_hull_reaches_beyond_the_slices_only_by_its_part_in_the_block(
    low, high, beyond
):
    ranges = slice_ranges(
        [((-10.0, -20.0, z), _AXIAL) for z in (0.0, 2.0, 4.0)],
        (1.0, 1.0),
        (21, 21),
        2.0,
    )
    hull = TargetHull.of(_box(low, high))

    assert beyond_slices(hull, _BLOCK, ranges) is beyond


# What the hulls keep of RT Dose and contours.


def _kept_slice(z: float, kept: KeptTargets) -> KeptSlice:
    """An axial slice over x and y from -20 to 20 mm at 1 mm, keeping only
    the pixels that the targets keep."""
    return KeptSlice(
        (-20.0, -20.0, z),
        _AXIAL,
        (1.0, 1.0),
        kept.slice_mask((-20.0, -20.0, z), _AXIAL, (1.0, 1.0), (41, 41)),
    )


def test_a_dose_voxel_is_kept_where_its_pixel_is_kept_or_it_lies_in_a_hull():
    hull = TargetHull.of(_box((-3, -10, 9), (3, -4, 31)))
    kept = KeptTargets((hull,), depth=2.5, in_block=True)
    region = DoseBlock(
        _BLOCK, tuple(_kept_slice(z, kept) for z in (10.0, 15.0)), targets=kept
    )
    without = DoseBlock(_BLOCK, region.slices)
    points = np.array(
        [
            # On a pixel kept for the target, just outside its hull.
            (3.4, -7.0, 10.0),
            # In the hull, beyond the slices.
            (0.0, -7.0, 30.0),
            # In the block, beyond the slices and every hull.
            (0.0, -15.0, 30.0),
        ]
    )

    assert not hull.contains(points[:1]).any()
    assert list(region.kept(points)) == [True, True, False]
    assert list(without.kept(points)) == [True, False, False]


def _structure_set(*contours: np.ndarray) -> pydicom.Dataset:
    """A structure set of one ROI, of these closed planar contours, in the
    synthetic head's frame."""
    dataset = pydicom.Dataset()
    roi = pydicom.Dataset()
    roi.ROINumber = 1
    roi.ReferencedFrameOfReferenceUID = files.FRAME
    dataset.StructureSetROISequence = [roi]
    item = pydicom.Dataset()
    item.ReferencedROINumber = 1
    item.ContourSequence = []
    for points in contours:
        contour = pydicom.Dataset()
        contour.ContourGeometricType = "CLOSED_PLANAR"
        contour.NumberOfContourPoints = len(points)
        contour.ContourData = [f"{v:.6g}" for v in np.ravel(points)]
        item.ContourSequence.append(contour)
    dataset.ROIContourSequence = [item]
    return dataset


def _rectangle(x0, x1, y0, y1, z):
    return np.array([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], float)


def test_a_target_s_contours_are_written_as_received_wherever_they_lie():
    # Drawn on the slices at 10 and 15 mm, between those at 15 and 25 mm
    # beyond either's reach, and above the last, beyond its reach.
    contours = [_rectangle(-3, 3, -10, -4, z) for z in (10.0, 15.0, 20.0, 30.0)]
    hull = TargetHull.of(np.concatenate(contours))
    kept = KeptTargets((hull,), depth=2.5, in_block=True)
    slices = tuple(_kept_slice(z, kept) for z in (10.0, 15.0, 25.0))
    region = DoseBlock(_BLOCK, slices, targets=kept)

    # No contour is cut.
    assert not cut_contours(region, _structure_set(*contours), files.FRAME)
    # Without the hulls, the slices' pixels alone keep those on them, and
    # the others, wholly in the block, are removed.
    cut = cut_contours(
        DoseBlock(_BLOCK, slices), _structure_set(*contours), files.FRAME
    )
    assert [(each.contour, each.values) for each in cut[0]] == [(0, None), (1, None)]


def test_an_outline_keeps_the_squares_of_the_pixels_kept_for_a_target():
    hull = TargetHull.of(_box((-3, -10, 9), (3, -4, 11)))
    kept = KeptTargets((hull,), depth=2.5, in_block=True)
    region = DoseBlock(_BLOCK, (_kept_slice(10.0, kept),), targets=kept)
    outline = _rectangle(-15, 15, -15, 15, 10.0)

    ((_, written),) = list(
        cut_contours(region, _structure_set(outline), files.FRAME).items()
    )

    polygons = [
        np.array([float(v) for v in each.values]).reshape(-1, 3) for each in written
    ]
    area = sum(
        abs(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])) / 2
        for p in polygons
    )
    # Its part behind the plane, 30 by 15 mm, with the half of the squares
    # of the row of pixels on the plane that lies ahead of it, whose centres
    # lie outside the open block, and the squares of the pixels kept for the
    # target, from x = -3.5 to 3.5 and y = -10.5 to -3.5.
    assert area == pytest.approx(30 * 15 + 30 * 0.5 + 7 * 7)
    assert len(polygons) == 2
