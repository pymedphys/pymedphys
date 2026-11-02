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

"""A planar polygon's part within chosen pixels of an image's grid.

A pixel is taken as the square of the points whose nearest pixel centre,
by their projection onto the image's plane, it is, as a DICOM image's
Image Position (Patient), Image Orientation (Patient), and Pixel Spacing
place it. A ring's part within a set of pixels is found by clipping it to
the half-spaces that bound each run of chosen pixels along a row
(:func:`~pymedphys._geometry.polygons.clip`), so that it is exact up to
floating point; the pieces, which meet only at their boundaries, can be
joined into rings by :func:`~pymedphys._geometry.polygons.dissolve`.
"""

from __future__ import annotations

import dataclasses

from pymedphys._imports import numpy as np

from .polygons import clip, nonzero_area, signed_area

# The area, in pixels, at or below which a piece bounds nothing: a sliver
# that rounding leaves where a ring's vertex lies on a pixel's corner, or a
# spike that runs into a pixel and back. Pieces are measured by
# :func:`_has_area`, so that a self-crossing piece's opposite windings
# cannot cancel to below it.
NO_AREA = 1e-9


@dataclasses.dataclass(frozen=True, repr=False)
class PixelGrid:
    """The pixels of an image's plane.

    Its ``repr`` shows nothing of it.

    Attributes
    ----------
    position : tuple of float
        The centre of the first pixel, in millimetres: Image Position
        (Patient).
    orientation : tuple of float
        The unit vectors along a row and down a column: Image Orientation
        (Patient).
    spacing : tuple of float
        Between rows, then between columns, in millimetres: Pixel Spacing.
    """

    position: tuple[float, float, float]
    orientation: tuple[float, ...]
    spacing: tuple[float, float]

    def __repr__(self) -> str:
        return "PixelGrid()"

    def indices(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return each point's row and column, as fractions, of its
        projection onto the grid's plane, the centre of a pixel being at
        whole numbers."""
        offset = np.asarray(points, dtype=float) - np.asarray(self.position)
        along_row, down_column = self._directions()
        return (
            offset @ down_column / self.spacing[0],
            offset @ along_row / self.spacing[1],
        )

    def row_bound(self, row: float) -> tuple[np.ndarray, float]:
        """The half-space of the points whose row, as :meth:`indices` gives
        it, is at most ``row``, as an outward normal and an offset."""
        _, down_column = self._directions()
        return down_column, float(
            down_column @ np.asarray(self.position) + row * self.spacing[0]
        )

    def column_bound(self, column: float) -> tuple[np.ndarray, float]:
        """The half-space of the points whose column, as :meth:`indices`
        gives it, is at most ``column``, as an outward normal and an
        offset."""
        along_row, _ = self._directions()
        return along_row, float(
            along_row @ np.asarray(self.position) + column * self.spacing[1]
        )

    def _directions(self) -> tuple[np.ndarray, np.ndarray]:
        orientation = np.asarray(self.orientation, dtype=float)
        return orientation[:3], orientation[3:]


def within_pixels(
    points: np.ndarray, grid: PixelGrid, chosen: np.ndarray
) -> list[np.ndarray]:
    """Return the pieces of a ring's region within the squares of the
    ``chosen`` pixels of a grid.

    Parameters
    ----------
    points : numpy.ndarray
        The ring's points in rows of x, y, and z.
    grid : PixelGrid
        The grid.
    chosen : numpy.ndarray
        Of bool, rows by columns: the pixels whose squares count.

    Returns
    -------
    list of numpy.ndarray
        Rings that meet one another only at their boundaries and together
        are the ring's region within the chosen squares: for each run of
        chosen pixels along a row, the ring's part within the run's
        rectangle, each with the ring's winding where the ring is simple.
        A piece is left out where its signed area, and its region's area
        by the nonzero rule, are each at most :data:`NO_AREA` of a
        pixel's, so that a piece that bounds nothing, such as a spike that
        runs into a chosen pixel and turns back or a sliver along two of a
        pixel's edges, is left out, while a self-crossing piece whose
        lobes' signed areas cancel keeps its region.

    Raises
    ------
    TypeError
        If ``chosen`` is not an array of bool.
    """
    chosen = np.asarray(chosen)
    if chosen.dtype != bool:
        raise TypeError("the chosen pixels must be an array of bool")
    rows, columns = grid.indices(points)
    height, width = chosen.shape
    first = max(int(np.floor(rows.min() + 0.5)), 0)
    last = min(int(np.ceil(rows.max() - 0.5)), height - 1)
    lowest = max(int(np.floor(columns.min() + 0.5)), 0)
    highest = min(int(np.ceil(columns.max() - 0.5)), width - 1)
    if first > last or lowest > highest:
        return []
    pieces: list[np.ndarray] = []
    normal, offset = grid.row_bound(first - 0.5)
    rest = clip(points, -normal, -offset)
    for row in range(first, last + 1):
        normal, offset = grid.row_bound(row + 0.5)
        strip = [part for each in rest for part in clip(each, normal, offset)]
        rest = [part for each in rest for part in clip(each, -normal, -offset)]
        runs = np.diff(
            np.concatenate([[0], chosen[row, lowest : highest + 1].astype(int), [0]])
        )
        for start, end in zip(np.flatnonzero(runs == 1), np.flatnonzero(runs == -1)):
            left_normal, left = grid.column_bound(lowest + start - 0.5)
            right_normal, right = grid.column_bound(lowest + end - 0.5)
            for each in strip:
                for part in clip(each, -left_normal, -left):
                    pieces.extend(clip(part, right_normal, right))
        if not rest:
            break
    return [piece for piece in pieces if len(piece) >= 3 and _has_area(grid, piece)]


def _has_area(grid: PixelGrid, piece: np.ndarray) -> bool:
    """Whether a piece's signed area, or else its region's area by the
    nonzero rule, by its projection onto the grid, is more than
    :data:`NO_AREA` of a pixel's.

    The signed area alone settles most pieces. Where it is within
    :data:`NO_AREA` of zero, the piece either bounds nothing or crosses
    itself with lobes that cancel, which only the area by the nonzero rule
    tells apart. Since that costs time growing at least with the square of
    the piece's edges, and faster where it crosses itself many times, a
    piece is first measured by a bound of both areas that costs time in
    proportion to them, which settles a piece that lies along one line,
    such as a sliver along a pixel's edge.
    """
    rows, columns = grid.indices(piece)
    plane = np.column_stack([columns, rows])
    if abs(signed_area(plane)) > NO_AREA:
        return True
    if _area_bound(plane) <= NO_AREA:
        return False
    return nonzero_area(plane) > NO_AREA


def _area_bound(plane: np.ndarray) -> float:
    """An upper bound of a ring's signed area in magnitude and of its area
    by the nonzero rule, by its x and y: the absolute areas of the
    triangles from its mean point to each of its edges, summed.

    A point's winding number about the ring is the sum of its windings
    about those triangles, so the points that the ring winds about lie
    within them, and the signed area is the sum of the triangles' signed
    areas. The bound is zero where every edge lies on a line through the
    mean point, as for a ring that lies along one line.
    """
    x = plane[:, 0] - plane[:, 0].mean()
    y = plane[:, 1] - plane[:, 1].mean()
    return float(np.abs(x * np.roll(y, -1) - np.roll(x, -1) * y).sum()) / 2
