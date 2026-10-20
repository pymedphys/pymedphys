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

from .test_polygons import even_odd

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
