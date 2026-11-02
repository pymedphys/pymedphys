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

"""Tests for planar polygons, each checked against regions found here by
counting crossings, not by the module."""

import fractions
import itertools
import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._geometry import polygons


def _square(x0, y0, x1, y1, z=0.0):
    """An anticlockwise rectangle."""
    return np.array([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], float)


def even_odd(rings, points):
    """Whether each point is within an odd number of rings, by counting the
    crossings of a ray towards positive x, independently of the module."""
    inside = np.zeros(len(points), dtype=bool)
    for ring in rings:
        x, y = np.asarray(ring)[:, 0], np.asarray(ring)[:, 1]
        for start in range(len(ring)):
            end = (start + 1) % len(ring)
            straddles = (y[start] > points[:, 1]) != (y[end] > points[:, 1])
            with np.errstate(divide="ignore", invalid="ignore"):
                at = x[start] + (points[:, 1] - y[start]) * (x[end] - x[start]) / (
                    y[end] - y[start]
                )
            inside ^= straddles & (points[:, 0] < at)
    return inside


def winding_numbers(rings, points):
    """Each point's winding number about the rings, summed, by counting the
    crossings of a ray towards positive x, each upward one as one and each
    downward one as minus one, independently of the module."""
    total = np.zeros(len(points), dtype=int)
    for ring in rings:
        x, y = np.asarray(ring)[:, 0], np.asarray(ring)[:, 1]
        for start in range(len(ring)):
            end = (start + 1) % len(ring)
            straddles = (y[start] > points[:, 1]) != (y[end] > points[:, 1])
            with np.errstate(divide="ignore", invalid="ignore"):
                at = x[start] + (points[:, 1] - y[start]) * (x[end] - x[start]) / (
                    y[end] - y[start]
                )
            upward = 1 if y[end] > y[start] else -1
            total += np.where(straddles & (points[:, 0] < at), upward, 0)
    return total


def test_a_ring_is_clipped_to_a_half_space():
    (part,) = polygons.clip(_square(0, 0, 4, 2), np.array([1.0, 0, 0]), 1.0)

    assert polygons.signed_area(part) == pytest.approx(2.0)
    assert part[:, 0].max() == pytest.approx(1.0)


def test_a_u_shape_is_clipped_into_two_rings():
    u_shape = np.array(
        [
            (0, 0, 0),
            (3, 0, 0),
            (3, 3, 0),
            (2, 3, 0),
            (2, 1, 0),
            (1, 1, 0),
            (1, 3, 0),
            (0, 3, 0),
        ],
        float,
    )

    parts = polygons.clip(u_shape, np.array([0, -1.0, 0]), -2.0)

    assert len(parts) == 2
    assert sorted(polygons.signed_area(part) for part in parts) == pytest.approx(
        [1.0, 1.0]
    )


def test_signed_area_follows_the_winding():
    assert polygons.signed_area(_square(0, 0, 2, 3)) == pytest.approx(6.0)
    assert polygons.signed_area(_square(0, 0, 2, 3)[::-1]) == pytest.approx(-6.0)


def _pentagram_area():
    """The area of a regular pentagram of circumradius 1 with its inner
    pentagon, as a decagon of ten triangles about its centre, each between
    an outer point, at radius 1, and an inner corner, at the radius where
    two of the star's edges cross."""
    inner = math.cos(math.radians(72)) / math.cos(math.radians(36))
    return 10 * inner * math.sin(math.radians(36)) / 2


_PENTAGRAM = [
    (math.cos(math.radians(90 + 144 * index)), math.sin(math.radians(90 + 144 * index)))
    for index in range(5)
]


@pytest.mark.parametrize(
    ("points", "area"),
    [
        ([(0, 0), (2, 0), (2, 3), (0, 3)], 6.0),
        ([(0, 3), (2, 3), (2, 0), (0, 0)], 6.0),
        ([(0, 0), (2, 2), (2, 0), (0, 2)], 2.0),  # a bow tie
        ([(0, 0), (2, 0), (2, 2), (0, 2)] * 2, 4.0),  # wound about twice
        ([(0, 0), (2, 0), (2, 2), (0, 2), (0, 0), (0, 2), (2, 2), (2, 0)], 0.0),
        (
            [(0, 0), (0.8, 0), (0.8, 0.4), (1.4, 0.4), (1.6, 0.6)]
            + [(1.4, 0.4), (0.8, 0.4), (0.8, 0.8), (0, 0.8)],
            0.64,
        ),  # a spike that bends and comes back
        ([(0, 0), (1, 1), (2, 2)], 0.0),
        ([(0, 0), (1, 0)], 0.0),
        (_PENTAGRAM, _pentagram_area()),
    ],
    ids=[
        "anticlockwise",
        "clockwise",
        "bow-tie",
        "twice",
        "out-and-back",
        "bent-spike",
        "line",
        "two-points",
        "pentagram",
    ],
)
def test_the_nonzero_area_counts_each_point_wound_about_once(points, area):
    ring = np.column_stack([np.asarray(points, float), np.full(len(points), 2.5)])

    assert polygons.nonzero_area(ring) == pytest.approx(area, abs=1e-12)
    far = ring + (3000.0, -4000.0, 0.0)
    assert polygons.nonzero_area(far) == pytest.approx(area, abs=1e-9)


def _nonzero_area_by_faces(ring):
    """The area of the faces into which a ring's edges divide the plane
    whose winding number is not zero, the faces found by Shapely and their
    winding numbers by :func:`winding_numbers`, independently of the module."""
    # Shapely serves only as an independent oracle here; the private
    # geometry module does not use it.
    shapely = pytest.importorskip("shapely")
    boundary = shapely.LineString(np.vstack([ring[:, :2], ring[:1, :2]]))
    faces = shapely.get_parts(
        shapely.polygonize(shapely.get_parts(shapely.node(boundary)))
    )
    inner = shapely.point_on_surface(faces)
    numbers = winding_numbers(
        [ring], np.column_stack([shapely.get_x(inner), shapely.get_y(inner)])
    )
    return float(shapely.area(faces)[numbers != 0].sum())


@pytest.mark.parametrize("seed", range(40))
def test_the_nonzero_area_of_a_ring_that_crosses_itself_is_its_faces(seed):
    generator = np.random.default_rng(seed)
    points = generator.uniform(-5, 5, (9, 2))
    ring = np.column_stack([points, np.zeros(9)])

    area = polygons.nonzero_area(ring)

    assert area == pytest.approx(_nonzero_area_by_faces(ring), abs=1e-9)


@pytest.mark.parametrize(
    ("points", "simple"),
    [
        ([(0, 0), (2, 0), (2, 2), (0, 2)], True),
        ([(0, 0), (2, 2), (2, 0), (0, 2)], False),  # a bow tie
        ([(0, 0), (2, 0), (2, 2), (2, 2), (0, 2)], False),  # an edge of no length
        ([(0, 0), (4, 0), (4, 4), (2, 0), (0, 4)], False),  # touching itself
        ([(0, 0), (2, 0), (1, 0), (1, 1)], False),  # doubling back
        ([(0, 0), (1, 0)], False),
        ([(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (4, 3), (4, 4), (0, 4)], True),
    ],
)
def test_a_ring_is_simple_only_where_it_neither_crosses_nor_touches_itself(
    points, simple
):
    ring = np.array([(x, y, 0.0) for x, y in points])

    assert polygons.is_simple(ring) is simple


# A block with a slot cut along one line, turned, as a split leaves a ring
# beside a notch: its edges 3 and 7 lie on the line, 0.1 mm apart along it,
# their cross products rounding noise of alternating sign.
_SLOTTED = np.array(
    [
        [5.591580643830662, 5.8598852851148955],
        [7.753063463012837, 9.127094527282036],
        [7.836464212518324, 9.071919215937895],
        [5.67498139333615, 5.804709973770754],
        [13.973355969132163, 0.3147664950287048],
        [23.307629263052693, 14.424073172909232],
        [6.627479361955177, 25.45913544173747],
        [-2.706793931965353, 11.34982876385694],
    ]
)


def test_edges_in_one_turned_line_with_a_gap_between_them_do_not_meet():
    assert polygons.is_simple(_SLOTTED)


def test_turned_rings_with_edges_in_one_line_are_simple():
    # A C whose two edges either side of its opening lie in one line, at
    # random turns near the origin, where rounding makes their cross
    # products alternate in sign.
    c = [(0, 0), (0, -13), (26, -13), (26, 0), (19, 0), (19, -6.5), (7, -6.5), (7, 0)]
    rng = np.random.default_rng(20261022)
    for _ in range(1000):
        angle = rng.uniform(0, 2 * np.pi)
        along = np.array([np.cos(angle), np.sin(angle)])
        across = np.array([-along[1], along[0]])
        origin = rng.uniform(-10, 10, 2)
        ring = np.array([origin + s * along + t * across for s, t in c])

        assert polygons.is_simple(ring)


def test_a_ring_that_touches_itself_on_a_turned_line_is_not_simple():
    # Its fourth point lies on its first edge, every point on y = 3x but the
    # third and fifth, though rounding leaves the cross product not zero.
    ring = np.array(
        [
            [3.6195273440350184e-16, 1.0858582032105055e-15],
            [5.166494424426352, 15.499483273279056],
            [2.166494424426352, 16.499483273279054],
            [1.7417566800693303, 5.225270040207991],
            [-2.9999999999999996, 1.000000000000001],
        ]
    )

    assert not polygons.is_simple(ring)


def test_edges_far_apart_along_one_turned_line_are_not_tested_exactly(
    monkeypatch,
):
    # Two runs of 400 points along parallel lines turned to y = 3x, joined
    # at their ends; testing every pair of edges took about 200,000 exact
    # tests.
    steps = np.arange(400) * 1.7
    line = np.stack([steps * 0.1, steps * 0.3], axis=1)
    ring = np.concatenate([line, line[::-1] + np.array([-5.0, 1.0])])
    exact = polygons._exact_side  # pylint: disable = protected-access
    calls = []

    def counted(*points):
        calls.append(points)
        return exact(*points)

    monkeypatch.setattr(polygons, "_exact_side", counted)

    assert polygons.is_simple(ring)
    assert len(calls) < 4 * len(ring)


def _exact_side(origin, one, other):
    """The sign of the cross product of ``one - origin`` and ``other -
    origin``, in fractions, independently of the module."""
    (ox, oy), (px, py), (qx, qy) = (
        map(fractions.Fraction, map(float, point[:2])) for point in (origin, one, other)
    )
    cross = (px - ox) * (qy - oy) - (py - oy) * (qx - ox)
    return (cross > 0) - (cross < 0)


def test_a_turn_is_found_exactly_on_a_grid_of_neighbouring_floats():
    # Kettner and others' grid: points a few units in the last place from
    # (0.5, 0.5), turned against (12, 12) and (24, 24), where rounding
    # gives the wrong sign for many.
    # pylint: disable = protected-access
    step = 2.0**-53
    offsets = np.arange(64) * step
    origin = np.stack(np.meshgrid(0.5 + offsets, 0.5 + offsets), axis=-1)
    one, other = np.array([12.0, 12.0]), np.array([24.0, 24.0])

    got = polygons._side(origin, one, other)

    expected = [[_exact_side(point, one, other) for point in row] for row in origin]
    assert (got == np.array(expected)).all()


def _exactly_simple(ring):
    """Whether a ring is simple, as :func:`polygons.is_simple` defines it,
    by fractions and every pair of edges, independently of the module."""
    points = [tuple(map(fractions.Fraction, map(float, each[:2]))) for each in ring]
    count = len(points)
    edges = [(points[i], points[(i + 1) % count]) for i in range(count)]
    if count < 3 or any(a == b for a, b in edges):
        return False

    def on(a, b, point):
        return (
            _exact_side(a, b, point) == 0
            and min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= point[1] <= max(a[1], b[1])
        )

    for i, j in itertools.combinations(range(count), 2):
        (a, b), (c, d) = edges[i], edges[j]
        if j == i + 1 or (i == 0 and j == count - 1):
            shared, mine, theirs = (b, a, d) if j == i + 1 else (a, b, c)
            back = (mine[0] - shared[0]) * (theirs[0] - shared[0]) + (
                mine[1] - shared[1]
            ) * (theirs[1] - shared[1])
            if _exact_side(shared, mine, theirs) == 0 and back > 0:
                return False
        elif (
            _exact_side(a, b, c) * _exact_side(a, b, d) < 0
            and _exact_side(c, d, a) * _exact_side(c, d, b) < 0
        ) or any(
            on(*segment, point)
            for segment, point in (((a, b), c), ((a, b), d), ((c, d), a), ((c, d), b))
        ):
            return False
    return True


def test_rings_with_points_in_a_turned_line_are_simple_as_exactly_found():
    # Rings of points that mostly lie on one turned line, so that edges lie
    # along it, touch, overlap, or pass each other with gaps between them.
    rng = np.random.default_rng(20261020)
    simple = 0
    for _ in range(2000):
        angle = rng.uniform(0, 2 * np.pi)
        along = np.array([np.cos(angle), np.sin(angle)])
        origin = rng.uniform(-10, 10, 2)
        count = int(rng.integers(4, 9))
        on_line = rng.random(count) < 0.6
        ring = np.where(
            on_line[:, None],
            origin + rng.choice(np.arange(6) * 1.7, count)[:, None] * along,
            origin + rng.uniform(-8, 8, (count, 2)),
        )

        assert polygons.is_simple(ring) == _exactly_simple(ring)
        simple += _exactly_simple(ring)
    assert 100 < simple < 1900, simple


def _dissolved(pieces, kept=np.empty((0, 2))):
    return polygons.dissolve([np.asarray(piece)[:, :2] for piece in pieces], kept, 1e-9)


def test_squares_of_an_l_join_into_one_ring():
    pieces = [_square(0, 0, 1, 1), _square(1, 0, 2, 1), _square(0, 1, 1, 2)]

    (ring,) = _dissolved(pieces)

    assert polygons.signed_area(ring) == pytest.approx(3.0)
    assert len(ring) == 6


def test_squares_meeting_at_a_corner_stay_two_rings():
    rings = _dissolved([_square(0, 0, 1, 1), _square(1, 1, 2, 2)])

    assert sorted(polygons.signed_area(ring) for ring in rings) == pytest.approx(
        [1.0, 1.0]
    )


def test_squares_around_a_gap_join_into_a_ring_and_its_hole():
    pieces = [
        _square(x, y, x + 1, y + 1)
        for x in range(3)
        for y in range(3)
        if (x, y) != (1, 1)
    ]

    rings = _dissolved(pieces)

    assert sorted(polygons.signed_area(ring) for ring in rings) == pytest.approx(
        [-1.0, 9.0]
    )
    grid = np.stack(
        np.meshgrid(np.linspace(-0.25, 3.25, 15), np.linspace(-0.25, 3.25, 15)), -1
    ).reshape(-1, 2)
    assert np.array_equal(even_odd(rings, grid), even_odd(pieces, grid))


def test_pieces_split_unevenly_along_a_shared_edge_join():
    # The lower rectangle's top edge holds the upper ones' corners only as
    # points of theirs, not of its own.
    pieces = [_square(0, 0, 3, 1), _square(0, 1, 1, 2), _square(1, 1, 3, 2)]

    (ring,) = _dissolved(pieces)

    assert polygons.signed_area(ring) == pytest.approx(6.0)
    assert len(ring) == 4


def test_points_kept_are_written_as_given():
    kept = np.array([(0.5, 0.0)])
    pieces = [
        np.array([(0, 0), (0.5, 0), (1, 0), (1, 1), (0, 1)], float),
        _square(1, 0, 2, 1)[:, :2],
    ]

    (ring,) = polygons.dissolve(pieces, kept, 1e-9)

    assert any((point == (0.5, 0.0)).all() for point in ring)
    assert polygons.signed_area(ring) == pytest.approx(2.0)


def test_points_within_the_tolerance_are_one():
    nudge = 1e-12
    pieces = [_square(0, 0, 1, 1), _square(1 + nudge, 0, 2, 1 - nudge)]

    (ring,) = _dissolved(pieces)

    assert polygons.signed_area(ring) == pytest.approx(2.0)


def _unit_squares(size, left_out, first=None):
    """Anticlockwise unit squares of a block, less those left out, with
    ``first``, if given, before the rest."""
    pieces = [
        _square(x, y, x + 1, y + 1)
        for x in range(size)
        for y in range(size)
        if (x, y) not in left_out
    ]
    return pieces if first is None else [first, *pieces]


@pytest.mark.parametrize(
    ("pieces", "areas"),
    [
        (_unit_squares(4, {(1, 1), (2, 2)}), [-1.0, -1.0, 16.0]),
        (_unit_squares(3, {(1, 1), (2, 2)}), [-1.0, 8.0]),
        (
            _unit_squares(
                3,
                {(1, 1), (2, 2), (2, 1)},
                first=np.roll(_square(2, 1, 3, 2), -3, axis=0),
            ),
            [-1.0, 8.0],
        ),
    ],
    ids=["holes-meeting-at-a-point", "hole-meeting-the-outside", "another-order"],
)
def test_rings_that_touch_at_a_point_are_kept_apart(pieces, areas):
    rings = _dissolved(pieces)

    assert sorted(polygons.signed_area(ring) for ring in rings) == pytest.approx(areas)
    for ring in rings:
        assert len({tuple(point) for point in ring}) == len(ring)
        assert polygons.is_simple(np.column_stack([ring, np.zeros(len(ring))]))
    grid = np.stack(
        np.meshgrid(np.linspace(-0.25, 4.25, 19), np.linspace(-0.25, 4.25, 19)), -1
    ).reshape(-1, 2)
    assert np.array_equal(even_odd(rings, grid), even_odd(pieces, grid))


def test_pieces_far_from_the_origin_join():
    pieces = [
        _square(3000.1, -3000.6, 3000.8, -2999.7),
        _square(3000.8, -3000.6, 3001.5, -2999.7),
    ]

    (ring,) = _dissolved(pieces)

    assert polygons.signed_area(ring) == pytest.approx(2 * 0.7 * 0.9)


@pytest.mark.parametrize("tolerance", [0.0, -1e-9, float("nan"), float("inf")])
def test_a_dissolve_needs_a_tolerance_above_zero(tolerance):
    with pytest.raises(ValueError, match="tolerance"):
        polygons.dissolve([_square(0, 0, 1, 1)[:, :2]], np.empty((0, 2)), tolerance)
