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

"""Tests for a polygon's part within chosen pixels, each checked at random
points against the polygon, by counting crossings, and the nearest pixel,
by rounding, found here, not by the module."""

import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._geometry import pixel_grids, polygons

from .test_polygons import even_odd, winding_numbers

_AXIAL = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def _turned(degrees):
    """An axial orientation turned within its plane."""
    angle = math.radians(degrees)
    return (
        math.cos(angle),
        math.sin(angle),
        0.0,
        -math.sin(angle),
        math.cos(angle),
        0.0,
    )


def _star(generator, centre, z, points=12):
    """A simple polygon, star-shaped about ``centre``."""
    angles = np.sort(generator.uniform(0, 2 * np.pi, points))
    radii = generator.uniform(3, 12, points)
    return np.column_stack(
        [
            centre[0] + radii * np.cos(angles),
            centre[1] + radii * np.sin(angles),
            np.full(points, z),
        ]
    )


def _nearest_chosen(grid, chosen, points):
    """Whether each point's nearest pixel, by its projection, is chosen."""
    orientation = np.asarray(grid.orientation)
    offset = points - np.asarray(grid.position)
    rows = np.rint(offset @ orientation[3:] / grid.spacing[0]).astype(int)
    columns = np.rint(offset @ orientation[:3] / grid.spacing[1]).astype(int)
    height, width = chosen.shape
    within = (rows >= 0) & (rows < height) & (columns >= 0) & (columns < width)
    result = np.zeros(len(points), dtype=bool)
    result[within] = chosen[rows[within], columns[within]]
    return result


@pytest.mark.parametrize(
    "orientation",
    [_AXIAL, (-1.0, 0.0, 0.0, 0.0, -1.0, 0.0), _turned(30), _turned(-61)],
    ids=["axial", "flipped", "turned 30", "turned -61"],
)
@pytest.mark.parametrize("seed", range(25))
def test_a_polygon_within_chosen_pixels_is_exactly_its_part_in_them(orientation, seed):
    generator = np.random.default_rng(seed)
    grid = pixel_grids.PixelGrid((-8.3, -9.1, 4.0), orientation, (1.3, 0.9))
    chosen = generator.random((24, 30)) < 0.55
    centre = (
        np.asarray(grid.position[:2])
        + 12 * np.asarray(orientation[:2])
        + 12 * np.asarray(orientation[3:5])
    )
    ring = _star(generator, centre, 4.7)
    samples = np.column_stack(
        [
            generator.uniform(centre[0] - 13, centre[0] + 13, 4000),
            generator.uniform(centre[1] - 13, centre[1] + 13, 4000),
            np.full(4000, 4.7),
        ]
    )

    pieces = pixel_grids.within_pixels(ring, grid, chosen)

    expected = even_odd([ring], samples) & _nearest_chosen(grid, chosen, samples)
    assert expected.any()
    assert np.array_equal(even_odd(pieces, samples), expected)
    winding = np.sign(polygons.signed_area(ring))
    assert all(np.sign(polygons.signed_area(piece)) == winding for piece in pieces)
    rings = polygons.dissolve([piece[:, :2] for piece in pieces], ring[:, :2], 1e-9)
    assert rings is not None
    assert np.array_equal(even_odd(rings, samples), expected)
    assert len(rings) < len(pieces)


def test_a_polygon_within_chosen_pixels_alone_is_one_ring_as_it_was():
    grid = pixel_grids.PixelGrid((0.0, 0.0, 0.0), _AXIAL, (1.0, 1.0))
    chosen = np.ones((20, 20), dtype=bool)
    ring = np.array([(3.2, 4.1, 0), (12.7, 3.3, 0), (9.9, 15.2, 0)], float)

    pieces = pixel_grids.within_pixels(ring, grid, chosen)
    (joined,) = polygons.dissolve([piece[:, :2] for piece in pieces], ring[:, :2], 1e-9)

    assert polygons.signed_area(joined) == pytest.approx(polygons.signed_area(ring))
    assert sorted(map(tuple, joined)) == sorted(map(tuple, ring[:, :2]))


def test_a_vertex_on_a_pixel_corner_leaves_no_piece_without_area():
    grid = pixel_grids.PixelGrid((-8.0, -9.0, 4.0), _AXIAL, (1.0, 1.0))
    chosen = np.zeros((30, 30), dtype=bool)
    chosen[16, 16] = True
    ring = np.array([(9.5, 3.5, 4), (5.5, 9.5, 4), (6.5, 0.5, 4)], float)

    pieces = pixel_grids.within_pixels(ring, grid, chosen)

    assert all(abs(polygons.signed_area(piece)) > 1e-9 for piece in pieces)
    samples = np.column_stack(
        [
            np.linspace(7.55, 8.45, 10).repeat(10),
            np.tile(np.linspace(6.55, 7.45, 10), 10),
        ]
    )
    samples = np.column_stack([samples, np.full(len(samples), 4.0)])
    assert np.array_equal(
        even_odd(pieces, samples),
        even_odd([ring], samples) & _nearest_chosen(grid, chosen, samples),
    )


@pytest.mark.parametrize(
    "orientation",
    [_AXIAL, _turned(30)],
    ids=["axial", "turned 30"],
)
def test_a_self_crossing_ring_within_a_pixel_keeps_its_region(orientation):
    grid = pixel_grids.PixelGrid((0.0, 0.0, 0.0), orientation, (1.0, 1.0))
    bow_tie = np.array([(-0.4, -0.4), (0.4, 0.4), (0.4, -0.4), (-0.4, 0.4)])
    along_row, down_column = np.asarray(orientation[:3]), np.asarray(orientation[3:])
    ring = bow_tie[:, :1] * along_row + bow_tie[:, 1:] * down_column
    assert polygons.signed_area(ring) == pytest.approx(0, abs=1e-12)

    pieces = pixel_grids.within_pixels(ring, grid, np.ones((1, 1), dtype=bool))

    samples = np.array([(-0.3, 0.0), (0.3, 0.0), (0.0, 0.3), (0.0, -0.3)])
    samples = samples[:, :1] * along_row + samples[:, 1:] * down_column
    assert even_odd([ring], samples).tolist() == [True, True, False, False]
    assert np.array_equal(
        even_odd([piece[:, :2] for piece in pieces], samples), even_odd([ring], samples)
    )


def _placed(grid, columns, rows):
    """The points at the given columns and rows of a grid, by its position,
    orientation, and spacing, independently of the module."""
    along_row, down_column = (
        np.asarray(grid.orientation[:3]),
        np.asarray(grid.orientation[3:]),
    )
    return (
        np.asarray(grid.position)
        + np.asarray(columns)[:, None] * grid.spacing[1] * along_row
        + np.asarray(rows)[:, None] * grid.spacing[0] * down_column
    )


@pytest.mark.parametrize(
    "orientation",
    [_AXIAL, (-1.0, 0.0, 0.0, 0.0, -1.0, 0.0), _turned(30), _turned(-61)],
    ids=["axial", "flipped", "turned 30", "turned -61"],
)
@pytest.mark.parametrize("seed", range(25))
def test_a_ring_whose_lobes_cancel_across_pixels_keeps_its_region(orientation, seed):
    generator = np.random.default_rng(seed)
    grid = pixel_grids.PixelGrid((-8.3, -9.1, 4.0), orientation, (1.3, 0.9))
    # Points to one side of column 6's centre line, then their mirror images
    # in the same order: the mirror maps the ring onto itself but reverses
    # its winding, so its signed area is zero, as it is within any run of
    # chosen pixels that the mirror maps onto itself.
    columns = 6 - generator.uniform(0.05, 3.0, 6)
    rows = generator.uniform(2.0, 8.0, 6)
    ring = _placed(grid, np.concatenate([columns, 12 - columns]), np.tile(rows, 2))
    half = generator.random((11, 7)) < 0.6
    chosen = np.concatenate([half, half[:, -2::-1]], axis=1)
    sample_columns = generator.uniform(2.5, 9.5, 4000)
    sample_rows = generator.uniform(1.5, 8.5, 4000)
    samples = _placed(grid, sample_columns, sample_rows)
    assert polygons.signed_area(ring) == pytest.approx(0, abs=1e-9)

    pieces = pixel_grids.within_pixels(ring, grid, chosen)

    in_chosen = _nearest_chosen(grid, chosen, samples)
    assert (even_odd([ring], samples) & in_chosen).any()
    assert np.array_equal(
        even_odd(pieces, samples), even_odd([ring], samples) & in_chosen
    )
    assert np.array_equal(
        winding_numbers(pieces, samples) != 0,
        (winding_numbers([ring], samples) != 0) & in_chosen,
    )


def _l_shape(degrees):
    """An L traced along the edges of pixels on a turned grid, its inner
    corner on a corner of the pixel at row 2 and column 2, which lies
    outside it."""
    grid = pixel_grids.PixelGrid((10.1, -20.3, 5.0), _turned(degrees), (0.9, 0.9))
    columns, rows = np.array(
        [(0.5, 0.5), (3.5, 0.5), (3.5, 3.5), (2.5, 3.5), (2.5, 1.5), (0.5, 1.5)]
    ).T
    chosen = np.zeros((5, 5), dtype=bool)
    chosen[2, 2] = True
    return _placed(grid, columns, rows), grid, chosen


def _spike(turn):
    """A square within the pixel at row 1 and column 1 of an axial grid,
    with a spike that runs into the pixel at row 1 and column 2, turning
    there or not, and back the same way."""
    grid = pixel_grids.PixelGrid((0.0, 0.0, 0.0), _AXIAL, (1.0, 1.0))
    tip = [(2.0, 1.0), (2.2, 1.2), (2.0, 1.0)] if turn else [(2.2, 1.0)]
    points = (
        [(0.6, 0.6), (1.4, 0.6), (1.4, 1.0)]
        + tip
        + [(1.4, 1.0), (1.4, 1.4), (0.6, 1.4)]
    )
    chosen = np.zeros((3, 4), dtype=bool)
    chosen[1, 2] = True
    return np.column_stack([points, np.zeros(len(points))]), grid, chosen


@pytest.mark.parametrize(
    ("ring", "grid", "chosen"),
    [_spike(True), _spike(False), _l_shape(67), _l_shape(74), _l_shape(88)],
    ids=["bent-spike", "straight-spike", "l-turned-67", "l-turned-74", "l-turned-88"],
)
def test_a_piece_that_bounds_nothing_is_left_out(ring, grid, chosen):
    assert pixel_grids.within_pixels(ring, grid, chosen) == []


def test_a_piece_along_one_line_is_left_out_without_its_exact_area(monkeypatch):
    def refuse(points):
        raise AssertionError("measured exactly")

    monkeypatch.setattr(pixel_grids, "nonzero_area", refuse)
    grid = pixel_grids.PixelGrid((-8.3, -9.1, 4.0), _AXIAL, (1.3, 0.9))
    # Out and back along the edge between rows 2 and 3, as a contour traced
    # along pixels' edges can leave, with a vertex at every half column.
    steps = np.linspace(0.5, 400.5, 801)
    columns = np.concatenate([steps, steps[-2:0:-1]])
    piece = _placed(grid, columns, np.full(len(columns), 2.5))

    assert not pixel_grids._has_area(grid, piece)  # pylint: disable = protected-access


@pytest.mark.parametrize(
    "chosen",
    [np.array([[0, 2]]), np.array([[0.0, 0.5]])],
    ids=["integers", "floats"],
)
def test_chosen_pixels_must_be_bool(chosen):
    grid = pixel_grids.PixelGrid((0.0, 0.0, 0.0), _AXIAL, (1.0, 1.0))
    ring = np.array([(0, 0, 0), (1, 0, 0), (0.5, 0.5, 0)], float)

    with pytest.raises(TypeError, match="bool"):
        pixel_grids.within_pixels(ring, grid, chosen)


def test_a_polygon_beyond_the_grid_has_no_part_in_it():
    grid = pixel_grids.PixelGrid((0.0, 0.0, 0.0), _AXIAL, (1.0, 1.0))

    ring = np.array([(30, 30, 0), (40, 30, 0), (35, 40, 0)], float)

    assert pixel_grids.within_pixels(ring, grid, np.ones((10, 10), bool)) == []


def test_a_grid_shows_nothing_in_its_repr():
    grid = pixel_grids.PixelGrid((1.0, 2.0, 3.0), _AXIAL, (1.0, 1.0))

    assert repr(grid) == "PixelGrid()"
