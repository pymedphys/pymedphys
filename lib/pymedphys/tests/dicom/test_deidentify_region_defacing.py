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

"""RT Structure Set contours cut by, and PET images set to zero activity
in, a defaced CT series' face block. Every UID and value here is
invented."""

# The tests share the face block, its kept slices, and the structure set
# helpers, so they stay in one module.
# pylint: disable = too-many-lines

from __future__ import annotations

import dataclasses
import itertools
import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest, shapely

from pymedphys._dicom.deidentify.defacing import FaceBlock
from pymedphys._dicom.deidentify.dose_defacing import DoseBlock
from pymedphys._dicom.deidentify.face_blocks import KeptSlice
from pymedphys._dicom.deidentify.pixel_cleaning import PixelDataRefused
from pymedphys._dicom.deidentify import region_defacing
from pymedphys._geometry.polygons import coplanar, is_simple, signed_area
from pymedphys._dicom.deidentify.region_defacing import (
    ContoursRefused,
    PetDefacer,
    cut_contours,
)

from . import _synthetic_head_dicom as files

# The block holds the points with y below 0 and z above 0: anterior is -y.
_BLOCK = FaceBlock((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), 0.0, ((0, 0, 0), (0, 0, 0)))
_CT_Z = (10.0, 20.0, 30.0)
_FRAME = files.FRAME


def _kept_slice(z: float) -> KeptSlice:
    """An axial slice over x and y from -20 to 20 mm at 1 mm, whose kept
    pixels are those in the block with x from -5 to 7 mm and y from -10 to
    -1 mm, above z = 15 mm, so that a mirror image of them is not."""
    x = np.arange(-20, 21)[None, :]
    y = np.arange(-20, 21)[:, None]
    kept = (x >= -5) & (x <= 7) & (y >= -10) & (y <= -1) & (z > 15)
    return KeptSlice((-20.0, -20.0, z), files.AXIAL, (1.0, 1.0), kept)


_REGION = DoseBlock(_BLOCK, tuple(_kept_slice(z) for z in _CT_Z))


def _rectangle(x0, x1, y0, y1, z):
    return np.array([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], float)


def _structure_set(*rois, frame=_FRAME):
    """A structure set of one ROI for each list of contours, each a
    (Contour Geometric Type, points) pair, in ``frame``."""
    dataset = pydicom.Dataset()
    dataset.StructureSetROISequence = []
    dataset.ROIContourSequence = []
    for number, contours in enumerate(rois, start=1):
        roi = pydicom.Dataset()
        roi.ROINumber = number
        roi.ReferencedFrameOfReferenceUID = frame
        dataset.StructureSetROISequence.append(roi)
        item = pydicom.Dataset()
        item.ReferencedROINumber = number
        item.ContourSequence = []
        for kind, points in contours:
            contour = pydicom.Dataset()
            contour.ContourGeometricType = kind
            contour.NumberOfContourPoints = len(points)
            contour.ContourData = [f"{v:.6g}" for v in np.ravel(points)]
            item.ContourSequence.append(contour)
        dataset.ROIContourSequence.append(item)
    return dataset


def _cut(kind, points):
    """The contours written of one contour of one ROI, as points, or None
    where it is written as received."""
    cut = cut_contours(_REGION, _structure_set([(kind, points)]), _FRAME)
    if not cut:
        return None
    ((index, written),) = list(cut.items())
    assert index == 0 and all(each.contour == 0 for each in written)
    return [
        np.array([float(v) for v in each.values]).reshape(-1, 3) for each in written
    ]


def _polygon(points):
    return shapely.geometry.Polygon(points[:, :2])


def _outside(points):
    """Where each point lies outside the open block, within rounding."""
    ahead = -points[:, 1]
    return (ahead <= 1e-9) | (points[:, 2] <= 1e-9)


# What is written as received.


@pytest.mark.parametrize(
    "points",
    [
        _rectangle(-10, 10, 1, 15, 20),  # behind the block
        _rectangle(-10, 10, -15, 15, -5),  # below it
        _rectangle(-4, 4, -9, -2, 20),  # in the kept brain alone
        # Crossing into the block within the kept brain alone, so that the
        # points just ahead of the plane, whose nearest pixels lie on it and
        # are not written as air, do not count.
        _rectangle(-4, 4, -8, 10, 20),
        _rectangle(-10, 10, 0, 15, 20),  # an edge on the plane
    ],
    ids=["behind", "below", "in the cavity", "into the cavity", "touching"],
)
def test_a_contour_that_reaches_no_pixel_written_as_air_is_kept_whole(points):
    assert _cut("CLOSED_PLANAR", points) is None


def test_a_contour_wholly_in_the_face_is_removed():
    # As an eye's is.
    assert _cut("CLOSED_PLANAR", _rectangle(8, 15, -15, -8, 20)) == []


def test_a_point_kept_whole_or_removed_by_where_it_lies():
    assert _cut("POINT", np.array([[0.0, -5.0, 20.0]])) is None  # cavity
    assert _cut("POINT", np.array([[0.0, 5.0, 20.0]])) is None  # behind
    assert _cut("POINT", np.array([[15.0, -5.0, 20.0]])) == []  # face


# What is cut.


@pytest.mark.parametrize("kind", ["CLOSED_PLANAR", "CLOSEDPLANAR_XOR"])
def test_a_contour_that_reaches_the_face_keeps_its_part_in_the_kept_brain(kind):
    # It reaches beyond the kept brain, so its part ahead of the plane is
    # cut away, but for the pixels that defacing keeps: the brain's, and
    # those whose centres lie on the plane.
    points = _rectangle(-10, 10, -15, 10, 20)

    (written,) = _cut(kind, points)

    expected = _polygon(points).difference(_removed(20.0))
    assert _polygon(written).symmetric_difference(expected).area < 1e-9
    assert _polygon(written).area < _polygon(points).area
    # Its corners outside the block are written as they were.
    assert {(-10.0, 10.0), (10.0, 10.0)} <= set(map(tuple, written[:, :2].tolist()))
    assert (written[:, 2] == 20).all()


def test_a_contour_below_the_cavity_floor_is_cut_where_it_enters_the_block():
    # On the slice at 10 mm, defacing keeps nothing.
    (written,) = _cut("CLOSED_PLANAR", _rectangle(-4, 4, -8, 10, 10))

    assert _polygon(written).equals(_polygon(_rectangle(-4, 4, 0, 10, 10)))


def test_a_contour_beyond_the_slices_is_cut_where_it_lies_in_the_block():
    # No slice lies within half their spacing of 50 mm, so each point counts
    # where it is in the block.
    (written,) = _cut("CLOSED_PLANAR", _rectangle(-4, 4, -8, 10, 50))

    assert _polygon(written).equals(_polygon(_rectangle(-4, 4, 0, 10, 50)))


def test_an_edge_that_crosses_the_block_between_its_vertices_is_cut():
    # In the plane x = 0, no vertex is in the block, but the edge from the
    # first, behind the plane and above 0 mm, to the second, ahead of it
    # and below, crosses the block's corner.
    points = np.array([(0, 2, 8), (0, -8, -2), (0, 10, -10)], float)

    written = _cut("CLOSED_PLANAR", points)

    def polygon(each):
        return shapely.geometry.Polygon(each[:, 1:])

    expected = polygon(points).difference(shapely.geometry.box(-100, 0, 0, 100))
    assert expected.area < polygon(points).area
    got = shapely.ops.unary_union([polygon(piece) for piece in written])
    assert got.symmetric_difference(expected).area < 1e-9
    assert all(_outside(piece).all() for piece in written)


def _roi(contours):
    """The contours written of one ROI's contours, each as its source index
    and points, or None where none is cut."""
    cut = cut_contours(_REGION, _structure_set(contours), _FRAME)
    if not cut:
        return None
    ((_, written),) = list(cut.items())
    return [
        (
            each.contour,
            contours[each.contour][1]
            if each.values is None
            else np.array([float(v) for v in each.values]).reshape(-1, 3),
        )
        for each in written
    ]


def _region_of(polygons):
    """The region that polygons in one plane bound together, by exclusive
    or, as CLOSEDPLANAR_XOR contours do and nested CLOSED_PLANAR ones are
    commonly read."""
    region = shapely.geometry.Polygon()
    for points in polygons:
        region = region.symmetric_difference(_polygon(points))
    return region


_FACE_SIDE = shapely.geometry.box(-1000, -1000, 1000, 0)
# The squares of the pixels kept in the block.
_CAVITY = shapely.geometry.box(-5.5, -10.5, 7.5, -0.5)


def _removed(z):
    """What a cut removes of the plane at ``z``: the block, less, where the
    nearest slice keeps pixels in the block, the squares of the pixels that
    defacing does not write as air there, those kept and those whose
    centres, at y = 0 or more, lie outside the block."""
    if z not in (20.0, 30.0):
        return _FACE_SIDE
    spared = _CAVITY.union(shapely.geometry.box(-20.5, -0.5, 20.5, 0))
    return _FACE_SIDE.difference(spared)


@pytest.mark.parametrize("kind", ["CLOSEDPLANAR_XOR", "CLOSED_PLANAR"])
def test_a_hole_in_the_cavity_is_cut_with_the_contour_around_it(kind):
    # The outer contour reaches the face; the hole lies in the kept brain
    # alone, so on its own it would be kept whole, and become a filled
    # island once the outer contour is cut.
    outer = _rectangle(-15, 15, -15, 15, 20)
    hole = _rectangle(-4, 4, -9, -2, 20)
    source = _region_of([outer, hole])

    written = _roi([(kind, outer), (kind, hole)])

    # The hole meets nothing that the cut removes, so it is written as it
    # was, and still excludes its region from the outer contour's.
    assert [index for index, _ in written] == [0, 1]
    got = _region_of([points for _, points in written])
    expected = source.difference(_removed(20.0))
    assert got.symmetric_difference(expected).area < 1e-6
    assert not got.contains(shapely.geometry.Point(0, -5))


def _shifted(dz):
    """The region, block and kept slices alike, moved ``dz`` mm along z."""
    block = FaceBlock((0.0, 0.0, dz), (0.0, -1.0, 0.0), dz, ((0, 0, dz), (0, 0, dz)))
    slices = tuple(
        KeptSlice(
            (each.position[0], each.position[1], each.position[2] + dz),
            each.orientation,
            each.spacing,
            each.kept,
        )
        for each in _REGION.slices
    )
    return DoseBlock(block, slices)


@pytest.mark.parametrize("dz", [0.0, -40.0], ids=["at 20 mm", "at -20 mm"])
@pytest.mark.parametrize("hole_first", [False, True], ids=["outer first", "hole first"])
@pytest.mark.parametrize("reverse_hole", [False, True], ids=["hole", "hole reversed"])
@pytest.mark.parametrize(
    "reverse_outer", [False, True], ids=["outer", "outer reversed"]
)
def test_a_hole_is_cut_with_its_contour_whatever_their_winding_order_or_place(
    reverse_outer, reverse_hole, hole_first, dz
):
    z = 20.0 + dz
    outer = _rectangle(-15, 15, -15, 15, z)
    hole = _rectangle(-4, 4, -9, -2, z)
    outer = outer[::-1] if reverse_outer else outer
    hole = hole[::-1] if reverse_hole else hole
    rings = [hole, outer] if hole_first else [outer, hole]
    contours = [("CLOSEDPLANAR_XOR", ring) for ring in rings]

    cut = cut_contours(_shifted(dz), _structure_set(contours), _FRAME)

    ((_, written),) = list(cut.items())
    got = _region_of(
        [
            rings[each.contour]
            if each.values is None
            else np.array([float(v) for v in each.values]).reshape(-1, 3)
            for each in written
        ]
    )
    expected = _region_of(rings).difference(_removed(z - dz))
    assert got.symmetric_difference(expected).area < 1e-6
    assert not got.contains(shapely.geometry.Point(0, -5))


@pytest.mark.parametrize("reverse", [False, True])
def test_contours_in_parallel_planes_either_side_of_the_origin_are_apart(reverse):
    # pylint: disable = protected-access
    ring = _rectangle(-4, 4, -9, -2, 20)
    mirrored = _rectangle(-4, 4, -9, -2, -20)
    mirrored = mirrored[::-1] if reverse else mirrored

    assert sorted(coplanar([ring, mirrored], region_defacing._COPLANAR)[0]) == [
        [0],
        [1],
    ]
    assert coplanar([ring, ring[::-1]], region_defacing._COPLANAR)[0] == [[0, 1]]


def _turned(points, about_x, about_y, shift):
    """``points`` turned ``about_x`` then ``about_y`` degrees and shifted."""
    a, b = np.radians(about_x), np.radians(about_y)
    turn_x = np.array(
        [[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]]
    )
    turn_y = np.array(
        [[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]]
    )
    return points @ (turn_y @ turn_x).T + shift


def test_oblique_contours_written_to_a_tenth_of_a_millimetre_share_a_plane():
    # pylint: disable = protected-access
    rng = np.random.default_rng(2404)
    for size in [0.3, 0.5, 2.5] * 100:
        about_x, about_y = rng.uniform(-60, 60, 2)
        shift = rng.uniform(-500, 500, 3)
        # A hole a few tenths of a millimetre to 2.5 mm across, whose own
        # rounded normal is uncertain or meaningless.
        hole = _rectangle(0, size, 0, size, 0) + (
            rng.uniform(-40, 40),
            rng.uniform(-60, 60),
            0,
        )
        outer = _rectangle(-60, 60, -80, 80, 0)
        # The next slice, half a millimetre away.
        beside = _rectangle(-60, 60, -80, 80, 0.5)
        ring, hole, beside = (
            np.round(_turned(points, about_x, about_y, shift), 1)
            for points in (outer, hole, beside)
        )

        assert coplanar([hole, ring], region_defacing._COPLANAR)[0] == [[0, 1]]
        assert coplanar([ring, hole[::-1]], region_defacing._COPLANAR)[0] == [[0, 1]]
        assert sorted(coplanar([ring, hole, beside], region_defacing._COPLANAR)[0]) == [
            [0, 1],
            [2],
        ]


@pytest.mark.parametrize("order", list(itertools.permutations(range(3))))
def test_a_hole_is_cut_with_its_contour_whatever_else_lies_near_their_plane(order):
    # pylint: disable = protected-access
    outer = _rectangle(-15, 15, -15, 15, 20)
    hole = _rectangle(-4, 4, -9, -2, 20)
    # A small contour half a millimetre below them, turned 5 degrees about x
    # so that its plane passes through the outer contour's centre.
    turn = np.radians(5)
    normal = np.array([0, -np.sin(turn), np.cos(turn)])
    centre = np.array([0, -0.5 / np.tan(turn), 19.5])
    across = np.cross(normal, (1, 0, 0))
    small = np.array(
        [
            centre + 0.75 * (x * np.array([1, 0, 0]) + y * across)
            for x, y in [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        ]
    )
    rings = [(outer, hole, small)[each] for each in order]

    groups, _ = coplanar(rings, region_defacing._COPLANAR)
    written = _roi([("CLOSEDPLANAR_XOR", ring) for ring in rings])

    assert sorted(sorted(group) for group in groups) == sorted(
        [sorted([order.index(0), order.index(1)]), [order.index(2)]]
    )
    got = _region_of([points for index, points in written if index != order.index(2)])
    expected = _region_of([outer, hole]).difference(_removed(20.0))
    assert got.symmetric_difference(expected).area < 1e-6


def _even_odd(rings, x, y):
    """Whether (x, y) lies within an odd number of the rings, by counting
    the edges that a ray from it along x crosses, as for any polygon."""
    inside = False
    for ring in rings:
        for (x0, y0, _), (x1, y1, _) in zip(ring, np.roll(ring, -1, axis=0)):
            if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                inside = not inside
    return inside


@pytest.mark.parametrize("hole_first", [False, True], ids=["outer first", "hole first"])
@pytest.mark.parametrize("reverse_hole", [False, True], ids=["hole", "hole reversed"])
@pytest.mark.parametrize(
    "reverse_outer", [False, True], ids=["outer", "outer reversed"]
)
def test_a_hole_in_a_bow_tie_is_cut_with_it(reverse_outer, reverse_hole, hole_first):
    # A bow tie's lobes are wound oppositely, so its signed area is zero,
    # yet it lies in one plane, and its left lobe holds the hole, which lies
    # within the kept brain alone.
    outer = np.array(
        [(-10, -10, 20), (10, 10, 20), (10, -10, 20), (-10, 10, 20)], float
    )
    hole = _rectangle(-4, -3, -2, -1, 20)
    outer = outer[::-1] if reverse_outer else outer
    hole = hole[::-1] if reverse_hole else hole
    rings = [hole, outer] if hole_first else [outer, hole]

    written = _roi([("CLOSEDPLANAR_XOR", ring) for ring in rings])

    got = [points for _, points in written]
    assert not _even_odd(rings, -3.5, -1.5)
    assert not _even_odd(got, -3.5, -1.5)
    # Nothing in the block is included, and what is outside it is as it was.
    for x in np.arange(-11.25, 11.5, 0.5):
        for y in np.arange(-11.25, 11.5, 0.5):
            expected = y > 0 and _even_odd(rings, x, y)
            assert _even_odd(got, x, y) == expected, (x, y)


def test_a_closed_contour_in_no_one_plane_refuses_an_roi_that_is_cut():
    bent = _rectangle(-4, 4, 2, 9, 20)
    bent[2, 2] = 21

    with pytest.raises(ContoursRefused):
        cut_contours(
            _REGION,
            _structure_set(
                [
                    ("CLOSED_PLANAR", _rectangle(-15, 15, -15, 15, 20)),
                    ("CLOSED_PLANAR", bent),
                ]
            ),
            _FRAME,
        )
    # Where none of its ROI's contours is cut, it is kept as received.
    assert not cut_contours(
        _REGION,
        _structure_set(
            [("CLOSED_PLANAR", _rectangle(-15, 15, 2, 15, 20)), ("CLOSED_PLANAR", bent)]
        ),
        _FRAME,
    )


def test_a_hole_that_crosses_the_plane_is_cut_with_the_contour_around_it():
    outer = _rectangle(-15, 15, -15, 15, 20)
    hole = _rectangle(-4, 4, -9, 6, 20)

    written = _roi([("CLOSEDPLANAR_XOR", outer), ("CLOSEDPLANAR_XOR", hole)])

    got = _region_of([points for _, points in written])
    expected = _region_of([outer, hole]).difference(_removed(20.0))
    assert got.symmetric_difference(expected).area < 1e-6
    assert not got.contains(shapely.geometry.Point(0, 3))


def test_contours_in_another_plane_are_not_cut_with_those_that_reach_the_face():
    outer = _rectangle(-15, 15, -15, 15, 20)
    # On the slice above, a contour and its hole within the cavity alone.
    above = _rectangle(-4, 4, -9, -2, 30)
    hole = _rectangle(-2, 2, -6, -4, 30)

    written = _roi(
        [
            ("CLOSEDPLANAR_XOR", outer),
            ("CLOSEDPLANAR_XOR", above),
            ("CLOSEDPLANAR_XOR", hole),
        ]
    )

    assert [index for index, _ in written] == [0, 1, 2]
    assert np.array_equal(written[1][1], above)
    assert np.array_equal(written[2][1], hole)


def test_random_holes_leave_the_roi_its_part_outside_the_block():
    rng = np.random.default_rng(20261019)
    cut = 0
    for _ in range(200):
        # Rounded so that Contour Data hold them exactly.
        x0, y0 = np.round(rng.uniform(-14, 0, 2), 3)
        x1, y1 = np.round(rng.uniform(1, 14, 2), 3)
        outer = _rectangle(x0, x1, y0, y1, 20)
        hx0, hx1 = np.sort(np.round(rng.uniform(x0 + 0.5, x1 - 0.5, 2), 3))
        hy0, hy1 = np.sort(np.round(rng.uniform(y0 + 0.5, y1 - 0.5, 2), 3))
        hole = _rectangle(hx0, hx1, hy0, hy1, 20)
        contours = [("CLOSEDPLANAR_XOR", outer), ("CLOSEDPLANAR_XOR", hole)]
        source = _region_of([outer, hole])

        written = _roi(contours)

        if written is None:
            continue
        cut += 1
        got = _region_of([points for _, points in written])
        expected = source.difference(_removed(20.0))
        assert got.symmetric_difference(expected).area < 1e-6
    assert cut > 100, cut


def test_a_contour_cut_in_two_is_written_as_two_numbered_once():
    # A U whose base is in the block leaves its two arms behind the plane,
    # on the slice at 10 mm, where defacing keeps nothing.
    points = np.array(
        [
            (-15, -15, 10),
            (15, -15, 10),
            (15, 10, 10),
            (8, 10, 10),
            (8, -8, 10),
            (-8, -8, 10),
            (-8, 10, 10),
            (-15, 10, 10),
        ],
        float,
    )
    structure_set = _structure_set([("CLOSED_PLANAR", points)])

    for reverse in (False, True):
        each = points[::-1] if reverse else points
        structure_set.ROIContourSequence[0].ContourSequence[0].ContourData = [
            f"{v:.6g}" for v in each.ravel()
        ]
        ((_, written),) = list(cut_contours(_REGION, structure_set, _FRAME).items())
        assert [piece.numbered for piece in written] == [True, False]
        areas = sorted(
            _polygon(np.array([float(v) for v in piece.values]).reshape(-1, 3)).area
            for piece in written
        )
        assert areas == [70.0, 70.0]


def test_a_polygon_that_crosses_itself_is_written_outside_the_block():
    # A bow tie, whose crossings along the plane cannot be paired as a
    # simple polygon's are.
    points = np.array(
        [(-10, -10, 20), (10, 10, 20), (10, -10, 20), (-10, 10, 20)], float
    )

    written = _cut("CLOSED_PLANAR", points)

    assert written
    assert all(_outside(piece).all() for piece in written)


def test_random_simple_polygons_lose_exactly_their_part_in_the_block():
    # Star-shaped polygons about points near the plane, which are simple.
    rng = np.random.default_rng(20261019)
    block = shapely.geometry.box(-1000, -1000, 1000, 0)
    cut = kept_whole = 0
    for _ in range(200):
        count = int(rng.integers(3, 30))
        angles = np.sort(rng.uniform(0, 2 * np.pi, count))
        radii = rng.uniform(2, 15, count)
        centre = rng.uniform(-8, 8, 2)
        points = np.column_stack(
            [
                centre[0] + radii * np.cos(angles),
                centre[1] + radii * np.sin(angles),
                np.full(count, 10.0),
            ]
        )
        points = np.round(points, 4)
        source = _polygon(points)
        if not source.is_valid:
            continue
        written = _cut("CLOSED_PLANAR", points)
        expected = source.difference(block)
        if written is None:
            # On the slice at 10 mm, defacing keeps nothing, so only a
            # contour that enters the block no farther than its nearest
            # pixels, whose centres lie on the plane, is kept whole.
            deep = shapely.geometry.box(-1000, -1000, 1000, -1)
            assert source.intersection(deep).area == 0
            kept_whole += 1
            continue
        assert all(_outside(piece).all() for piece in written)
        got = shapely.ops.unary_union([_polygon(piece) for piece in written])
        assert got.symmetric_difference(expected).area < 1e-3 * max(expected.area, 1)
        cut += 1
    assert cut > 100, (cut, kept_whole)


def test_random_simple_polygons_keep_exactly_their_part_in_the_kept_brain():
    # As above, on the slice at 20 mm, where defacing keeps pixels in the
    # block, so each loses exactly what defacing writes as air.
    rng = np.random.default_rng(20261020)
    removed = _removed(20.0)
    spared = kept_whole = 0
    for _ in range(200):
        count = int(rng.integers(3, 30))
        angles = np.sort(rng.uniform(0, 2 * np.pi, count))
        radii = rng.uniform(2, 15, count)
        centre = rng.uniform(-8, 8, 2)
        points = np.column_stack(
            [
                centre[0] + radii * np.cos(angles),
                centre[1] + radii * np.sin(angles),
                np.full(count, 20.0),
            ]
        )
        points = np.round(points, 4)
        source = _polygon(points)
        if not source.is_valid:
            continue
        written = _cut("CLOSED_PLANAR", points)
        if written is None:
            # A contour is judged by points sampled along its edges at half
            # a pixel, so one kept whole can graze a pixel written as air.
            assert source.intersection(removed).area < 0.25
            kept_whole += 1
            continue
        got = _region_of(written)
        expected = source.difference(removed)
        assert got.symmetric_difference(expected).area < 1e-6 * max(expected.area, 1)
        assert all((piece[:, 2] == 20).all() for piece in written)
        spared += got.intersection(_CAVITY).area > 1
    assert spared > 100, (spared, kept_whole)


def _winding(point, rings):
    """The sum of the rings' winding numbers about a point, by x and y."""
    total = 0
    for ring in rings:
        starts = ring[:, :2]
        for (x0, y0), (x1, y1) in zip(starts, np.roll(starts, -1, axis=0)):
            cross = (x1 - x0) * (point[1] - y0) - (point[0] - x0) * (y1 - y0)
            if y0 <= point[1] < y1 and cross > 0:
                total += 1
            elif y1 <= point[1] < y0 and cross < 0:
                total -= 1
    return total


@pytest.mark.parametrize("reverse", [False, True], ids=["outer", "outer reversed"])
def test_a_cut_contour_keeps_its_winding_so_a_hole_stays_one_by_any_rule(reverse):
    # A reader that fills by the nonzero rule takes a hole for one only
    # where it winds against its outer contour, so the outer contour, which
    # is cut, keeps its winding, and the hole, which is not, is as it was.
    outer = _rectangle(-15, 15, -15, 15, 20)
    hole = _rectangle(-4, 4, -9, -2, 20)[::-1]
    if reverse:
        outer, hole = outer[::-1], hole[::-1]

    written = _roi([("CLOSED_PLANAR", outer), ("CLOSED_PLANAR", hole)])

    assert [index for index, _ in written] == [0, 1]
    assert np.sign(signed_area(written[0][1])) == np.sign(signed_area(outer))
    rings = [points for _, points in written]
    expected = _region_of([outer, hole]).difference(_removed(20.0))
    for x in np.arange(-16, 16, 0.37) + 0.011:
        for y in np.arange(-16, 16, 0.37) + 0.013:
            filled = _winding((x, y), rings) != 0
            assert filled == expected.contains(shapely.geometry.Point(x, y)), (x, y)


def test_contours_whose_pieces_cannot_be_joined_are_cut_by_the_whole_block(
    monkeypatch,
):
    # Where the pieces of one contour of a plane cannot be joined into
    # rings, every closed contour of the plane is cut by the whole block,
    # so that the hole within the kept brain goes with the brain.
    monkeypatch.setattr(region_defacing, "dissolve", lambda *_: None)
    outer = _rectangle(-15, 15, -15, 15, 20)
    hole = _rectangle(-4, 4, -9, -2, 20)

    written = _roi([("CLOSEDPLANAR_XOR", outer), ("CLOSEDPLANAR_XOR", hole)])

    assert [index for index, _ in written] == [0]
    assert _polygon(written[0][1]).equals(_polygon(_rectangle(-15, 15, 0, 15, 20)))


@pytest.mark.parametrize("repeat", [0, 2], ids=["closing point", "middle point"])
def test_a_contour_with_a_repeated_point_keeps_its_part_in_the_kept_brain(repeat):
    # Some planning systems write a closed contour's first point again at
    # its end; a point repeated in place draws no edge, so the contour is
    # still simple.
    points = _rectangle(-10, 10, -15, 10, 20)
    repeated = (
        np.vstack([points, points[:1]])
        if repeat == 0
        else np.insert(points, repeat, points[repeat], axis=0)
    )

    (written,) = _cut("CLOSED_PLANAR", repeated)

    expected = _polygon(points).difference(_removed(20.0))
    assert _polygon(written).symmetric_difference(expected).area < 1e-9
    assert _polygon(written).intersection(_CAVITY).area > 1


def test_a_contour_on_slices_with_short_direction_cosines_keeps_the_kept_brain():
    # Face finding takes direction cosines within 1e-4 of unit length, so a
    # slice's normal is judged by its direction alone.
    short = (0.99994, 0.0, 0.0, 0.0, 0.99994, 0.0)
    region = DoseBlock(
        _BLOCK,
        tuple(
            KeptSlice(each.position, short, each.spacing, each.kept)
            for each in _REGION.slices
        ),
    )
    points = _rectangle(-10, 10, -15, 10, 20)

    cut = cut_contours(region, _structure_set([("CLOSED_PLANAR", points)]), _FRAME)

    ((_, written),) = list(cut.items())
    got = _region_of(
        [np.array([float(v) for v in each.values]).reshape(-1, 3) for each in written]
    )
    # The pixels centred on the plane now lie 1.2 um ahead of it, in the
    # block, so the contour loses their row, as the CT does, and the kept
    # brain's squares move by up to 2 um.
    expected = _polygon(points).difference(_FACE_SIDE.difference(_CAVITY))
    assert got.symmetric_difference(expected).area < 0.1
    assert got.intersection(_CAVITY).area > 100


def _holed_region(air):
    """As :data:`_REGION`, but with the pixels at the (x, y) of ``air``, as of
    bone within the cavity, written as air."""
    x = np.arange(-20, 21)[None, :]
    y = np.arange(-20, 21)[:, None]
    bone = np.zeros((41, 41), bool)
    for each in air:
        bone |= (x == each[0]) & (y == each[1])
    return DoseBlock(
        _BLOCK,
        tuple(
            dataclasses.replace(_kept_slice(z), kept=_kept_slice(z).kept & ~bone)
            for z in _CT_Z
        ),
    )


def _rings_cut(region, kind, points):
    """As :func:`_cut`, in ``region``, but with the points of a contour
    written as received."""
    cut = cut_contours(region, _structure_set([(kind, points)]), _FRAME)
    if not cut:
        return [points]
    ((_, written),) = list(cut.items())
    return [
        np.array([float(v) for v in each.values]).reshape(-1, 3) for each in written
    ]


def _air_removed(air):
    """As :func:`_removed` at 20 mm, but for the pixels of ``air`` too."""
    squares = [shapely.geometry.box(x - 0.5, y - 0.5, x + 0.5, y + 0.5) for x, y in air]
    return _removed(20.0).union(shapely.ops.unary_union(squares))


def _assert_hole_free(rings, expected, clockwise=False):
    """That the rings are simple, wind one way, overlap nowhere, and bound
    ``expected``, and that where two meet along a line, it is an edge
    between columns of pixels, through no pixel's centre."""
    for ring in rings:
        assert is_simple(ring)
        assert (signed_area(ring) < 0) == clockwise
    polygons = [_polygon(each) for each in rings]
    union = shapely.ops.unary_union(polygons)
    assert math.isclose(sum(each.area for each in polygons), union.area)
    assert union.symmetric_difference(expected).area < 1e-6 * max(expected.area, 1)
    for one, other in itertools.combinations(polygons, 2):
        met = one.boundary.intersection(other.boundary)
        for part in getattr(met, "geoms", [met]):
            if part.is_empty or part.geom_type != "LineString":
                continue
            x = np.asarray(part.coords)[:, 0]
            assert np.ptp(x) < 1e-9
            assert abs(x[0] - 0.5 - round(x[0] - 0.5)) < 1e-9


@pytest.mark.parametrize("kind", ["CLOSED_PLANAR", "CLOSEDPLANAR_XOR"])
def test_a_hole_that_a_cut_makes_is_written_as_its_type_encodes_it(kind):
    # CLOSEDPLANAR_XOR contours combine by exclusive or, so a hole around
    # the pixel written as air is a contour of its own. A reader may fill
    # each CLOSED_PLANAR contour alone, so there the hole becomes a notch
    # in the part to its right of the edge between its column of pixels and
    # the one before, at x = -0.5 mm, which passes through no pixel's centre.
    region = _holed_region([(0, -4)])
    points = _rectangle(-8, 8, -9, 5, 20)

    rings = _rings_cut(region, kind, points)

    expected = _polygon(points).difference(_air_removed([(0, -4)]))
    if kind == "CLOSED_PLANAR":
        assert len(rings) == 2
        _assert_hole_free(rings, expected)
        assert sorted(min(each[:, 0]) for each in rings) == [-8, -0.5]
    else:
        areas = sorted(signed_area(each) for each in rings)
        assert np.allclose(areas, [-1, expected.area + 1])
        assert _region_of(rings).symmetric_difference(expected).area < 1e-9


def test_holes_in_one_column_of_pixels_and_another_are_split_away_at_each():
    # The pixels at x = 0 mm are split from those before them first, which
    # makes notches of both holes there; then the one at x = 3 mm.
    air = [(0, -4), (0, -7), (3, -2)]
    points = _rectangle(-8, 8, -9, 5, 20)

    rings = _rings_cut(_holed_region(air), "CLOSED_PLANAR", points)

    assert len(rings) == 3
    _assert_hole_free(rings, _polygon(points).difference(_air_removed(air)))
    assert sorted(min(each[:, 0]) for each in rings) == [-8, -0.5, 2.5]


@pytest.mark.parametrize("reverse", [False, True], ids=["anticlockwise", "clockwise"])
def test_random_holes_that_cuts_make_are_split_away_from_closed_planar_contours(
    reverse,
):
    # Random polygons around random pixels written as air within the kept
    # cavity, some touching at a corner, some at an edge.
    rng = np.random.default_rng(20261020 + reverse)
    split = 0
    for _ in range(150):
        count = int(rng.integers(3, 30))
        angles = np.sort(rng.uniform(0, 2 * np.pi, count))
        radii = rng.uniform(4, 15, count)
        centre = rng.uniform(-3, 3, 2) + (1, -5)
        points = np.column_stack(
            [
                centre[0] + radii * np.cos(angles),
                centre[1] + radii * np.sin(angles),
                np.full(count, 20.0),
            ]
        )
        points = np.round(points, 4)
        if not _polygon(points).is_valid:
            continue
        air = {
            (int(x), int(y))
            for x, y in zip(
                rng.integers(-4, 7, int(rng.integers(1, 7))),
                rng.integers(-9, -1, 7),
            )
        }
        expected = _polygon(points).difference(_air_removed(air))

        rings = _rings_cut(
            _holed_region(air), "CLOSED_PLANAR", points[::-1] if reverse else points
        )

        _assert_hole_free(rings, expected, clockwise=reverse)
        split += any(
            each.interiors
            for each in getattr(expected, "geoms", [expected])
            if each.geom_type == "Polygon"
        )
    assert split > 50, split


def test_a_contour_that_cannot_be_freed_of_holes_is_cut_by_the_whole_block(
    monkeypatch,
):
    # The holes in two columns need two splits, one more than allowed.
    monkeypatch.setattr(region_defacing, "_MOST_SPLITS", 1)

    rings = _rings_cut(
        _holed_region([(0, -4), (0, -7), (3, -2)]),
        "CLOSED_PLANAR",
        _rectangle(-8, 8, -9, 5, 20),
    )

    assert len(rings) == 1
    assert _polygon(rings[0]).equals(_polygon(_rectangle(-8, 8, 0, 5, 20)))


def test_the_limit_counts_splits_not_the_joins_between_them(monkeypatch):
    # Two splits free the contour of its holes, with four joins.
    monkeypatch.setattr(region_defacing, "_MOST_SPLITS", 2)
    air = [(0, -4), (0, -7), (3, -2)]
    points = _rectangle(-8, 8, -9, 5, 20)

    rings = _rings_cut(_holed_region(air), "CLOSED_PLANAR", points)

    assert len(rings) == 3
    _assert_hole_free(rings, _polygon(points).difference(_air_removed(air)))


def _turned_grid_l_shape(dx, dy, quadrant):
    """A region of slices on a 1 mm grid turned 133.1 degrees about z, its
    kept pixels those centred within |x| <= 9 mm and -15 <= y <= -0.2 mm but
    the one nearest (0, -7) mm, and an L-shaped contour at z = 20 mm, written
    to 13 significant figures, whose inner corner lies 1e-9 mm from a corner
    of that pixel's square, towards (``dx``, ``dy``), and which lacks the
    ``quadrant`` of a square of 16 mm about it, "upper" or "lower"."""
    angle = math.radians(133.1)
    along = np.array([math.cos(angle), math.sin(angle), 0.0])
    down = np.array([-math.sin(angle), math.cos(angle), 0.0])
    origin = -30 * (along + down)
    index = np.arange(61)
    centres = origin + index[None, :, None] * along + index[:, None, None] * down
    x, y = centres[..., 0], centres[..., 1]
    air = np.unravel_index(np.argmin(np.hypot(x, y + 7)), x.shape)
    kept = (np.abs(x) <= 9) & (y >= -15) & (y <= -0.2)
    kept[air] = False
    region = DoseBlock(
        _BLOCK,
        tuple(
            KeptSlice(
                tuple(origin + (0, 0, z)),
                tuple(along) + tuple(down),
                (1.0, 1.0),
                kept & (z > 15),
            )
            for z in _CT_Z
        ),
    )
    corner = centres[air] + 0.5 * (down - along)
    px, py = corner[:2] + 1e-9 / math.sqrt(2) * np.array([dx, dy])
    x0, x1, y0, y1 = px - 8, px + 8, py - 8, py + 8
    outline = {
        "upper": [(x0, y0), (x1, y0), (x1, py), (px, py), (px, y1), (x0, y1)],
        "lower": [(px, y0), (x1, y0), (x1, y1), (x0, y1), (x0, py), (px, py)],
    }[quadrant]
    points = np.array([(u, v, 20.0) for u, v in outline])
    structure_set = _structure_set([("CLOSED_PLANAR", points)])
    structure_set.ROIContourSequence[0].ContourSequence[0].ContourData = [
        f"{v:.13g}" for v in np.ravel(points)
    ]
    spared = shapely.ops.unary_union(
        [shapely.geometry.box(-100, 0, 100, 100)]
        + [
            shapely.geometry.Polygon(
                [
                    tuple((centres[each] + 0.5 * (a * along + b * down))[:2])
                    for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))
                ]
            )
            for each in zip(*np.nonzero(kept | (y >= 0)))
        ]
    )
    return region, structure_set, _polygon(points).intersection(spared)


def _written_rings(region, structure_set):
    ((_, written),) = list(cut_contours(region, structure_set, _FRAME).items())
    return [
        np.array([float(v) for v in each.values]).reshape(-1, 3) for each in written
    ]


def test_a_ring_of_no_area_that_joining_leaves_is_not_written():
    # Joining points within 1e-9 mm of a turned pixel's corner left a ring
    # of three points in a line, written as a contour of its own.
    region, structure_set, expected = _turned_grid_l_shape(1, -1, "upper")

    rings = _written_rings(region, structure_set)

    assert all(abs(signed_area(each)) > 1e-9 for each in rings)
    _assert_simple_and_bounding(rings, expected)


def test_a_ring_that_crosses_itself_after_splitting_falls_back_to_the_block():
    # Here joining the split pieces near the corner left a ring that
    # crosses itself, which a reader may fill otherwise.
    region, structure_set, _ = _turned_grid_l_shape(-1, 1, "lower")

    rings = _written_rings(region, structure_set)

    assert all(is_simple(each) for each in rings)
    assert all(_outside(each).all() for each in rings)


@pytest.mark.parametrize("kind", ["CLOSED_PLANAR", "CLOSEDPLANAR_XOR"])
def test_rings_that_meet_at_points_around_gaps_are_written_as_they_are(kind):
    # On a 45 by 45 grid turned 133.1 degrees about z, centred on (0, -6)
    # mm, an L-shaped contour's inner corner lies 1e-9 mm beyond a corner of
    # the pixel written as air nearest (0, -7) mm. Squares written as air
    # that straddle the plane leave gaps between two rings that meet at
    # points, and joining left a third ring of no area.
    angle = math.radians(133.1)
    along = np.array([math.cos(angle), math.sin(angle), 0.0])
    down = np.array([-math.sin(angle), math.cos(angle), 0.0])
    origin = np.array([0.0, -6.0, 0.0]) - 22 * (along + down)
    rows, columns = np.mgrid[0:45, 0:45]
    centres = origin + columns[..., None] * along + rows[..., None] * down
    x, y = centres[..., 0], centres[..., 1]
    offset = np.array([0.0, -7.0, 0.0]) - origin
    air = (int(round(offset @ down)), int(round(offset @ along)))
    kept = (np.abs(x) <= 9) & (y >= -15) & (y <= -0.2)
    kept[air] = False
    region = DoseBlock(
        _BLOCK,
        tuple(
            KeptSlice(
                tuple(origin + (0, 0, z)),
                tuple(along) + tuple(down),
                (1.0, 1.0),
                kept & (z > 15),
            )
            for z in _CT_Z
        ),
    )
    reach = 0.5 + 1e-9 / math.sqrt(2)
    corners = [(-14, -reach), (reach, -reach), (reach, -14), (14, -14), (14, 14)]
    points = np.array(
        [centres[air] + p * along + q * down for p, q in corners + [(-14, 14)]]
    )
    points[:, 2] = 20.0
    if signed_area(points) < 0:
        points = points[::-1]
    structure_set = _structure_set([(kind, points)])
    structure_set.ROIContourSequence[0].ContourSequence[0].ContourData = [
        pydicom.valuerep.format_number_as_ds(float(v)) for v in np.ravel(points)
    ]
    spared = shapely.ops.unary_union(
        [shapely.geometry.box(-100, 0, 100, 100)]
        + [
            shapely.geometry.Polygon(
                [
                    tuple((centres[each] + 0.5 * (a * along + b * down))[:2])
                    for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))
                ]
            )
            for each in zip(*np.nonzero(kept | (y >= 0)))
        ]
    )

    rings = _written_rings(region, structure_set)

    assert len(rings) == 2
    assert all(signed_area(each) > 1e-9 for each in rings)
    expected = _polygon(points).intersection(spared)
    assert len(getattr(expected, "geoms", [expected])[0].interiors) > 0
    _assert_simple_and_bounding(rings, expected)


def _assert_simple_and_bounding(rings, expected):
    """That the rings are simple, overlap nowhere, and bound ``expected``."""
    assert all(is_simple(each) for each in rings)
    polygons = [_polygon(each) for each in rings]
    union = shapely.ops.unary_union(polygons)
    assert math.isclose(sum(each.area for each in polygons), union.area)
    assert union.symmetric_difference(expected).area < 1e-6


def test_a_contour_nearer_two_tilted_slices_is_cut_by_the_whole_block():
    # Slices tilted within face finding's tolerance, 2 mm apart along their
    # normal, keep the same pixels but for one bone pixel of the upper. An
    # axial triangle near their midpoint, its lower corners beyond their
    # pixels, has its one corner within them nearest the lower slice, but
    # points within it nearest the upper, so no one slice's pixels decide it.
    tilt = 0.00008
    orientation = (1.0, 0.0, 0.0, 0.0, math.sqrt(1 - tilt**2), tilt)
    normal = np.cross(orientation[:3], orientation[3:])
    lower = np.array([-20.0, -20.0, 40.0])
    x = np.arange(-20, 21)[None, :]
    y = np.arange(-20, 21)[:, None]
    kept = (np.abs(x) <= 5) & (y >= -10) & (y <= -1)
    bone = kept & ~((x == 0) & (y == -8))
    region = DoseBlock(
        _BLOCK,
        (
            KeptSlice(tuple(lower), orientation, (1.0, 1.0), kept),
            KeptSlice(tuple(lower + 2 * normal), orientation, (1.0, 1.0), bone),
        ),
    )
    z = 41.0012800032041
    points = np.array([(-30, -15, z), (30, -15, z), (0, 10, z)], float)

    cut = cut_contours(region, _structure_set([("CLOSED_PLANAR", points)]), _FRAME)

    ((_, written),) = list(cut.items())
    got = shapely.ops.unary_union(
        [
            _polygon(np.array([float(v) for v in each.values]).reshape(-1, 3))
            for each in written
        ]
    )
    # No point within what is written and in the block is one that defacing
    # writes as air, by the nearest pixel of the nearest slice, the removed
    # bone pixel's among them.
    grid = np.array(
        [
            (px, py, z)
            for px in np.arange(-25, 25, 0.25) + 0.01
            for py in np.arange(-16, 11, 0.25) + 0.01
            if got.contains(shapely.geometry.Point(px, py))
            and _BLOCK.contains(np.array([[px, py, z]]))[0]
        ]
    )
    # pylint: disable = protected-access
    assert not len(grid) or not region_defacing._defaced(region, grid).any()
    assert not got.contains(shapely.geometry.Point(0, -8))
    assert got.equals(
        _polygon(points).intersection(shapely.geometry.box(-50, 0, 50, 50))
    )


def test_contours_of_a_plane_at_more_than_one_z_are_cut_by_the_whole_block():
    # The hole lies 0.1 mm above the outer contour, in its plane by the
    # grouping, but not in one slice's, so neither keeps the kept brain.
    outer = _rectangle(-15, 15, -15, 15, 20)
    hole = _rectangle(-4, 4, -9, -2, 20.1)

    written = _roi([("CLOSEDPLANAR_XOR", outer), ("CLOSEDPLANAR_XOR", hole)])

    assert [index for index, _ in written] == [0]
    assert _polygon(written[0][1]).equals(_polygon(_rectangle(-15, 15, 0, 15, 20)))


def test_a_sagittal_contour_is_cut_by_both_planes():
    # In the plane x = 0, from y = -20 to 20 mm and z = -10 to 10 mm: the
    # block takes its quarter ahead of the plane and above 0 mm.
    points = np.array([(0, -20, -10), (0, 20, -10), (0, 20, 10), (0, -20, 10)], float)

    written = _cut("CLOSED_PLANAR", points)

    assert all(_outside(piece).all() for piece in written)
    areas = [shapely.geometry.Polygon(piece[:, 1:]).area for piece in written]
    assert math.isclose(sum(areas), 40 * 20 - 20 * 10)


def test_an_open_contour_is_written_as_its_pieces_outside_the_block():
    line = np.array([(-10, 10, 20), (-10, -15, 20), (10, -15, 20), (10, 10, 20)], float)

    written = _cut("OPEN_PLANAR", line)

    assert [piece.tolist() for piece in written] == [
        [[-10, 10, 20], [-10, 0, 20]],
        [[10, 0, 20], [10, 10, 20]],
    ]


def test_contours_that_are_cut_are_written_in_their_rois_order():
    structure_set = _structure_set(
        [("CLOSED_PLANAR", _rectangle(-10, 10, 1, 15, 20))],
        [
            ("CLOSED_PLANAR", _rectangle(-10, 10, 1, 15, 20)),
            ("POINT", np.array([[15.0, -5.0, 20.0]])),
            ("CLOSED_PLANAR", _rectangle(-10, 10, -15, 10, 20)),
        ],
    )

    cut = cut_contours(_REGION, structure_set, _FRAME)

    # The first ROI is unchanged; the second keeps its first contour as
    # received, loses its point, and has its third cut.
    assert list(cut) == [1]
    assert [(each.contour, each.values is None) for each in cut[1]] == [
        (0, True),
        (2, False),
    ]


# What is refused, so that the structure set stays held.


@pytest.mark.parametrize(
    "change",
    [
        lambda ds: setattr(
            ds.StructureSetROISequence[0], "ReferencedFrameOfReferenceUID", "1.2.3"
        ),
        lambda ds: delattr(
            ds.StructureSetROISequence[0], "ReferencedFrameOfReferenceUID"
        ),
        lambda ds: setattr(ds.ROIContourSequence[0], "ReferencedROINumber", 9),
        lambda ds: setattr(_contour(ds), "ContourGeometricType", "CURVED"),
        lambda ds: setattr(_contour(ds), "ContourData", ["1", "2"]),
        lambda ds: setattr(_contour(ds), "ContourData", ["nan", "0", "0"]),
        lambda ds: setattr(_contour(ds), "ContourData", ["1e7", "0", "0"]),
        lambda ds: setattr(_contour(ds), "ContourOffsetVector", ["0", "0", "1"]),
        lambda ds: setattr(_contour(ds), "ContourSlabThickness", "2"),
    ],
    ids=[
        "another frame",
        "no frame",
        "undeclared ROI",
        "unknown type",
        "not in threes",
        "not finite",
        "too far",
        "offset",
        "slab",
    ],
)
def test_a_structure_set_that_cannot_be_cut_is_refused(change):
    structure_set = _structure_set([("CLOSED_PLANAR", _rectangle(-10, 10, 1, 15, 20))])
    change(structure_set)

    with pytest.raises(ContoursRefused) as raised:
        cut_contours(_REGION, structure_set, _FRAME)
    assert str(raised.value) == "the contours cannot be cut by the block"


def _contour(dataset):
    return dataset.ROIContourSequence[0].ContourSequence[0]


# PET.


def _pet(stored=None, *, slope="1", intercept="0", **changes):
    """A PET slice at z = 20 mm over x and y from -20 to 20 mm at 2 mm, of
    100 everywhere by default."""
    dataset = pydicom.Dataset()
    dataset.ImagePositionPatient = ["-20", "-20", "20"]
    dataset.ImageOrientationPatient = [str(v) for v in files.AXIAL]
    dataset.PixelSpacing = ["2", "2"]
    dataset.Rows = dataset.Columns = 21
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.RescaleSlope = slope
    dataset.RescaleIntercept = intercept
    if stored is None:
        stored = np.full((21, 21), 100, dtype=np.uint16)
    dataset.PixelData = stored.astype("<u2").tobytes()
    meta = pydicom.dataset.FileMetaDataset()
    meta.TransferSyntaxUID = files.EXPLICIT_VR_LITTLE_ENDIAN
    dataset.file_meta = meta
    for keyword, value in changes.items():
        setattr(dataset, keyword, value)
    return dataset


def _pet_points():
    x = -20 + 2 * np.arange(21)[None, :]
    y = -20 + 2 * np.arange(21)[:, None]
    return np.broadcast_arrays(x, y)


def test_pet_is_set_to_zero_activity_in_the_block_less_the_kept_brain():
    dataset = _pet()

    mask = PetDefacer(_REGION, dataset).mask(0, dataset.pixel_array)

    x, y = _pet_points()
    kept = (x >= -5) & (x <= 7) & (y >= -10) & (y <= -1)
    assert mask.frame == 0 and mask.value == 0
    assert np.array_equal(mask.mask, (y < 0) & ~kept)


def test_pet_background_is_the_stored_value_of_zero_activity_and_padding_is_kept():
    stored = np.full((21, 21), 100, dtype=np.uint16)
    stored[0, :] = 7
    dataset = _pet(stored, slope="2", intercept="-100", PixelPaddingValue=7)
    dataset["PixelPaddingValue"].VR = "US"

    mask = PetDefacer(_REGION, dataset).mask(0, dataset.pixel_array)

    assert mask.value == 50
    assert not mask.mask[0].any() and mask.mask[1].any()


def test_a_pet_slice_behind_or_below_the_block_has_no_mask():
    behind = _pet(ImagePositionPatient=["-20", "1", "20"])
    below = _pet(ImagePositionPatient=["-20", "-20", "-5"])

    for dataset in (behind, below):
        assert PetDefacer(_REGION, dataset).mask(0, dataset.pixel_array) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"slope": "0"},
        {"slope": "1e-300", "intercept": "-1"},
        # Zero activity would need a stored value below 0.
        {"intercept": "100"},
        {"ImageOrientationPatient": ["2", "0", "0", "0", "1", "0"]},
        {"PixelSpacing": ["0", "2"]},
        {"ImagePositionPatient": ["1e300", "0", "0"]},
        {"NumberOfFrames": 2},
    ],
    ids=repr,
)
def test_a_pet_slice_that_cannot_be_placed_or_cleaned_is_refused(changes):
    dataset = _pet(**changes)

    with pytest.raises(PixelDataRefused):
        PetDefacer(_REGION, dataset)


def test_compressed_pet_is_refused():
    dataset = _pet()
    dataset.file_meta.TransferSyntaxUID = "1.2.840.10008.1.2.5"

    with pytest.raises(PixelDataRefused):
        PetDefacer(_REGION, dataset)


def test_a_pet_defacer_shows_nothing_and_holds_nothing():
    defacer = PetDefacer(_REGION, _pet())

    assert repr(defacer) == "PetDefacer()"
    assert defacer.held is None


def test_contour_values_are_written_as_decimal_strings_of_sixteen_characters():
    points = _rectangle(-10, 10, -15, 10, 20) + 1 / 3

    ((_, (written,)),) = list(
        cut_contours(
            _REGION, _structure_set([("CLOSED_PLANAR", points)]), _FRAME
        ).items()
    )

    assert all(len(value) <= 16 for value in written.values)
    assert len(written.values) % 3 == 0
    assert repr(written) == "WrittenContour()"
