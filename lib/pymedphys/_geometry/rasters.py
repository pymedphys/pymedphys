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

"""Planar polygons filled onto a rectangular grid of points.

:func:`even_odd` finds which points of a grid lie in the region that some
polygons bound together by the even-odd rule, as the contours of one ROI in
one plane bound a region with its holes. Unlike
:mod:`~pymedphys._geometry.pixel_grids`, it approximates the region by the
points that it holds, so it suits a picture of a region or a mask that is
sampled, not the region's area or boundary.
"""

from __future__ import annotations

from collections.abc import Sequence

from pymedphys._imports import numpy as np


def even_odd(
    polygons: Sequence[np.ndarray], xs: np.ndarray, ys: np.ndarray
) -> np.ndarray:
    """Return which points of a grid the polygons bound, by the even-odd rule.

    A point is in the region where a ray from it towards decreasing x
    crosses the polygons' edges an odd number of times. An edge is crossed
    where the point's y is at or above the lower of its ends and below the
    upper, and the edge meets that y at a lower x than the point's, so that
    a ray through a vertex crosses it once, and a horizontal edge is never
    crossed. A point on an edge is therefore in the region on one side of
    it and not the other, and polygons that share an edge, or a polygon
    that crosses itself, are filled as the rule gives.

    Parameters
    ----------
    polygons : sequence of numpy.ndarray
        Each of shape (n, 2), its vertices' x and y in order, the last
        joined to the first. One of fewer than three vertices bounds
        nothing.
    xs, ys : numpy.ndarray
        The grid's x and y coordinates, each ascending.

    Returns
    -------
    numpy.ndarray
        Boolean, of shape ``(len(ys), len(xs))``.
    """
    xs, ys = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
    width = len(xs)
    toggles = np.zeros(len(ys) * (width + 1), np.intp)
    for polygon in polygons:
        points = np.asarray(polygon, dtype=float)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError("a polygon needs its vertices as rows of x and y")
        if len(points) < 3:
            continue
        starts, ends = points, np.roll(points, -1, axis=0)
        low = np.minimum(starts[:, 1], ends[:, 1])
        high = np.maximum(starts[:, 1], ends[:, 1])
        first = np.searchsorted(ys, low, side="left")
        last = np.searchsorted(ys, high, side="left")
        counts = np.maximum(last - first, 0)
        edges = np.repeat(np.arange(len(points)), counts)
        if not edges.size:
            continue
        # The rows of each edge, from its first, laid end to end.
        offsets = np.arange(edges.size) - np.repeat(np.cumsum(counts) - counts, counts)
        rows = first[edges] + offsets
        start, end = starts[edges], ends[edges]
        crossing = start[:, 0] + (ys[rows] - start[:, 1]) * (
            end[:, 0] - start[:, 0]
        ) / (end[:, 1] - start[:, 1])
        # Every point beyond the crossing in x is toggled.
        columns = np.searchsorted(xs, crossing, side="right")
        toggles += np.bincount(rows * (width + 1) + columns, minlength=toggles.size)
    parity = np.cumsum(toggles.reshape(len(ys), width + 1), axis=1) % 2
    inside: np.ndarray = parity[:, :width].astype(bool)
    return inside
