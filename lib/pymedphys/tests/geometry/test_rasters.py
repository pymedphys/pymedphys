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

"""Tests of filling polygons onto a grid by the even-odd rule.

Shapely is used only here, as an oracle.
"""

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._geometry.rasters import even_odd

shapely = pytest.importorskip("shapely")


def _square(x, y, half):
    return np.array(
        [
            [x - half, y - half],
            [x + half, y - half],
            [x + half, y + half],
            [x - half, y + half],
        ]
    )


def _oracle(polygons, xs, ys):
    """Each point's parity of the polygons that contain it, by Shapely."""
    grid_x, grid_y = np.meshgrid(xs, ys)
    points = shapely.points(grid_x, grid_y)
    parity = np.zeros(grid_x.shape, bool)
    for polygon in polygons:
        parity ^= shapely.contains(shapely.Polygon(polygon), points)
    return parity


def test_a_point_is_inside_where_a_ray_crosses_an_odd_number_of_edges():
    xs = np.arange(-0.5, 3.0)
    assert even_odd([_square(1.0, 1.0, 1.0)], xs, np.array([1.0])).tolist() == [
        [False, True, True, False]
    ]


@pytest.mark.parametrize("seed", range(5))
def test_random_simple_polygons_match_the_oracle(seed):
    generator = np.random.default_rng(seed)
    angles = np.sort(generator.uniform(0, 2 * np.pi, 40))
    radii = generator.uniform(5, 20, 40)
    star = np.column_stack([radii * np.cos(angles), radii * np.sin(angles)])
    # Points off the polygon's edges, so that the oracle's boundary rule
    # does not matter.
    xs = np.arange(-25.0, 25.0, 0.37) + 0.011
    ys = np.arange(-25.0, 25.0, 0.41) + 0.013
    assert (even_odd([star], xs, ys) == _oracle([star], xs, ys)).all()


def test_a_contour_within_another_is_a_hole_and_contours_apart_are_both_filled():
    outer, inner, apart = _square(0, 0, 10), _square(0, 0, 4), _square(30, 0, 3)
    xs = np.arange(-15.0, 40.0, 0.5) + 0.25
    ys = np.arange(-15.0, 15.0, 0.5) + 0.25
    filled = even_odd([outer, inner, apart], xs, ys)
    assert (filled == _oracle([outer, inner, apart], xs, ys)).all()
    assert not filled[np.searchsorted(ys, 0.25), np.searchsorted(xs, 0.25)]
    assert filled[np.searchsorted(ys, 0.25), np.searchsorted(xs, 7.25)]
    assert filled[np.searchsorted(ys, 0.25), np.searchsorted(xs, 30.25)]


def test_a_ray_through_a_vertex_or_along_a_horizontal_edge_counts_once():
    # A diamond, whose left and right vertices lie on the middle row, and a
    # square whose top and bottom edges lie along rows.
    diamond = np.array([[0.0, -2.0], [2.0, 0.0], [0.0, 2.0], [-2.0, 0.0]])
    xs = np.arange(-3.0, 3.5, 1.0)
    rows = even_odd([diamond], xs, np.array([0.0]))
    # Each vertex is crossed once; a point on the left vertex is not beyond
    # it, and one on the right vertex is beyond the left only.
    assert rows.tolist() == [[False, False, True, True, True, True, False]]
    square = _square(0.0, 0.0, 1.0)
    edges = even_odd([square], np.array([-2.0, 0.5, 2.0]), np.array([-1.0, 1.0]))
    # The lower edge's row is inside, and the upper's is not, as the
    # half-open rule gives.
    assert edges.tolist() == [[False, True, False], [False, False, False]]


def test_a_bow_tie_is_filled_on_both_sides_of_its_crossing():
    bow_tie = np.array([[-2.0, -1.0], [2.0, 1.0], [2.0, -1.0], [-2.0, 1.0]])
    filled = even_odd([bow_tie], np.array([-1.5, 1.5]), np.array([0.3, -0.3]))
    assert filled.all()


def test_a_polygon_of_fewer_than_three_vertices_bounds_nothing():
    line = np.array([[0.0, 0.0], [5.0, 5.0]])
    assert not even_odd([line], np.arange(6.0), np.arange(6.0)).any()


def test_a_polygon_needs_rows_of_x_and_y():
    with pytest.raises(ValueError, match="rows of x and y"):
        even_odd([np.zeros((4, 3))], np.arange(3.0), np.arange(3.0))
