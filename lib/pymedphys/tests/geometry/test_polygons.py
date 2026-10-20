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
