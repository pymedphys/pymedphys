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

"""The targets that defacing keeps in a CT series' face block.

Under the Clean Recognizable Visual Features Option, a run defaces a CT
series around its targets, the ROIs whose RT ROI Interpreted Type is PTV,
CTV, or GTV in the structure sets searched for it
(:mod:`~pymedphys._dicom.deidentify.face_blocks`), rather than holding it
for review: it keeps, in the face block, the convex hull of each target's
contours' points (:class:`TargetHull`), which holds the target's every
contour, its interior, and whatever a planning system interpolates between
its contours, and the face verdict on the pixel data written decides
whether the series is released. Each target has a hull of its own, so the
face between two targets is not kept for them.

A pixel of a slice is kept where the box that it stands for may meet a
target's hull (:meth:`KeptTargets.slice_mask`): its square in the slice's
plane, which holds the points whose nearest pixel it is, and
:attr:`KeptTargets.depth` millimetres to either side along the slices'
normal, the distance within which an RT Dose voxel, a PET or Segmentation
pixel, or a contour's point is placed on its nearest slice
(:class:`~pymedphys._dicom.deidentify.dose_defacing.DoseBlock`). So every
point of a hull that is placed on a slice is placed on a pixel that is
kept, and the CT keeps each pixel that a target reaches. A point that no
slice's pixel is near enough is kept where it lies in a hull
(:meth:`KeptTargets.contains`), so that defacing never takes a target's
dose, activity, segments, or contours, wherever they lie.

The tests err towards keeping. A hull is the intersection of half-spaces,
each bounded by the farthest of the target's points along its normal, so
it holds every point whatever the precision of the facets that Qhull finds
for it, and it is bounded along its points' principal axes too, so that a
target drawn on one slice, or on one line, has a hull of no thickness
there. A box is taken to meet a hull where each of the hull's half-spaces,
moved out by the box's own extent along its normal, holds the box's centre,
and the hull's extent along each of the box's edges reaches the box's: a
box near an edge or a corner of the hull can pass without meeting it, never
the reverse.

Every point of a hull that lies in the block must lie within the slices,
since a part of the face kept beyond them would be released without any
preview of the series showing it (:func:`beyond_slices`): along the slices'
normal, within :attr:`KeptTargets.depth` of the first or last slice, and
within the squares of every slice's pixels, as linear programmes over the
hull and the block find it. A run holds a series for review where a hull
reaches beyond them.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from .defacing import FaceBlock

# How thin, in millimetres, a target's points may lie along a principal axis
# for its hull to be found in fewer dimensions, the hull then being bounded
# along that axis by the points' extent alone, as a target drawn on one
# slice is flat along the slices' normal.
_FLAT = 1e-3
# How far, in millimetres, a point or a box may lie beyond a hull's
# half-spaces and still be taken to meet it, or a hull's part in the block
# beyond the slices and still be taken to lie within them. It allows for
# rounding, and for the direction cosines of a slice, which may differ from
# unit length and from orthogonality by as much as the face block's finder
# allows, placing a pixel within hundredths of a millimetre of where a unit
# basis would.
_MARGIN = 1e-2
# How many points are tested against a hull's half-spaces at a time, which
# bounds the memory that a test needs.
_CHUNK = 4096


@dataclasses.dataclass(frozen=True, repr=False, eq=False)
class TargetHull:
    """The convex hull of one target's contours' points, as half-spaces.

    Its ``repr`` shows nothing of it.

    Attributes
    ----------
    vertices : numpy.ndarray
        The target's distinct points, in rows of x, y, and z, in
        millimetres.
    normals : numpy.ndarray
        The unit normal of each half-space, in rows.
    offsets : numpy.ndarray
        The bound of each: a point is in the half-space where its dot
        product with the normal is at most the offset.
    """

    vertices: np.ndarray
    normals: np.ndarray
    offsets: np.ndarray

    def __repr__(self) -> str:
        return "TargetHull()"

    @classmethod
    def of(cls, points: np.ndarray) -> TargetHull:
        """Return the hull of a target's points, as the module describes.

        Parameters
        ----------
        points : numpy.ndarray
            The x, y, and z of each point along the last axis, in
            millimetres, every one finite.

        Raises
        ------
        ValueError
            Where there are no points, or one is not finite.
        """
        points = np.unique(np.asarray(points, dtype=float).reshape(-1, 3), axis=0)
        if not len(points) or not np.isfinite(points).all():
            raise ValueError("a hull needs finite points")
        centre = points.mean(axis=0)
        # The rows of the last factor are the points' principal axes, a
        # basis of all three dimensions whatever the number of points.
        _, _, axes = np.linalg.svd(points - centre)
        coordinates = (points - centre) @ axes.T
        spread = np.ptp(coordinates, axis=0)
        wide = [int(i) for i in np.argsort(-spread, kind="stable") if spread[i] > _FLAT]
        normals = [axes, -axes]
        # Where Qhull cannot find the facets in as many dimensions as the
        # points span, as for points that lie nearly in a plane, it finds
        # them in fewer: the hull is then a prism of the points' extent,
        # which holds them still.
        for count in range(len(wide), 1, -1):
            facets = _facets(coordinates[:, wide[:count]])
            if facets is not None:
                normals.append(facets @ axes[wide[:count]])
                break
        stacked = np.concatenate(normals)
        stacked = stacked / np.linalg.norm(stacked, axis=1, keepdims=True)
        # Each triangle of a facet gives its plane again.
        unique = np.unique(np.round(stacked, 12), axis=0)
        return cls(points, unique, (points @ unique.T).max(axis=0))

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Whether each point lies in the hull, within :data:`_MARGIN`.

        Parameters
        ----------
        points : numpy.ndarray
            The x, y, and z of each point in rows, in millimetres.

        Returns
        -------
        numpy.ndarray
            Of bool, one for each point; False for a point that is not
            finite.
        """
        return self._within(points, np.zeros(len(self.offsets)))

    def meets_boxes(self, centres: np.ndarray, halves: np.ndarray) -> np.ndarray:
        """Whether each box may meet the hull, as the module describes.

        Parameters
        ----------
        centres : numpy.ndarray
            The x, y, and z of each box's centre in rows, in millimetres.
        halves : numpy.ndarray
            Three rows, each half of one of the boxes' edges, as a vector
            in millimetres: the boxes are the points at their centres plus
            any sum of these, each scaled by a factor from -1 to 1.

        Returns
        -------
        numpy.ndarray
            Of bool, one for each box.
        """
        centres = np.asarray(centres, dtype=float).reshape(-1, 3)
        halves = np.asarray(halves, dtype=float)
        within = self._within(centres, np.abs(self.normals @ halves.T).sum(axis=1))
        for edge in halves:
            length = float(np.linalg.norm(edge))
            if not np.isfinite(length) or length <= 0:
                continue
            direction = edge / length
            reach = float(np.abs(halves @ direction).sum())
            along = self.vertices @ direction
            at = centres @ direction
            within &= (at - reach <= along.max() + _MARGIN) & (
                at + reach >= along.min() - _MARGIN
            )
        return within

    def _within(self, points: np.ndarray, slack: np.ndarray) -> np.ndarray:
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        found = np.zeros(len(points), dtype=bool)
        bounds = self.offsets + slack + _MARGIN
        for start in range(0, len(points), _CHUNK):
            chunk = points[start : start + _CHUNK]
            with np.errstate(invalid="ignore"):
                found[start : start + _CHUNK] = (chunk @ self.normals.T <= bounds).all(
                    axis=1
                )
        return found


def _facets(coordinates: np.ndarray) -> np.ndarray | None:
    """The unit outward normals of the facets of the convex hull of points
    in two or three dimensions, or None where Qhull cannot find them, as
    for points that lie in a line or a plane of those dimensions."""
    # Qhull's bindings are compiled, so pylint cannot see their members.
    # pylint: disable = no-member
    try:
        hull = scipy.spatial.ConvexHull(coordinates)
    # Qhull raises its own error for degenerate points, and ValueError for
    # too few.
    except (scipy.spatial.QhullError, ValueError):
        return None
    # pylint: enable = no-member
    normals: np.ndarray = hull.equations[:, :-1]
    return normals


@dataclasses.dataclass(frozen=True, repr=False)
class KeptTargets:
    """The hulls of the targets that defacing keeps in one series' face
    block.

    Its ``repr`` shows only the number of hulls.

    Attributes
    ----------
    hulls : tuple of TargetHull
        Each target's hull that may reach the block, or any box of a pixel
        in it.
    depth : float
        How far, in millimetres, each pixel's box reaches to either side of
        its slice along the slices' normal: half the smallest spacing
        between the slices that the block reaches, as an instance in their
        frame is placed on them.
    in_block : bool
        Whether a hull reaches the block itself, so that the series is
        defaced around a target.
    """

    hulls: tuple[TargetHull, ...] = ()
    depth: float = 0.0
    in_block: bool = False

    def __post_init__(self) -> None:
        if self.in_block and not self.hulls:
            raise ValueError("a target in the block has a hull")
        if not (math.isfinite(self.depth) and self.depth >= 0):
            raise ValueError("a depth is finite and not negative")

    def __repr__(self) -> str:
        return f"KeptTargets(hulls={len(self.hulls)})"

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Whether each point lies in a target's hull.

        Parameters
        ----------
        points : numpy.ndarray
            The x, y, and z of each point in rows, in millimetres.

        Returns
        -------
        numpy.ndarray
            Of bool, one for each point.
        """
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        found = np.zeros(len(points), dtype=bool)
        for hull in self.hulls:
            found |= hull.contains(points)
        return found

    def slice_mask(
        self,
        position: Sequence[float],
        orientation: Sequence[float],
        spacing: Sequence[float],
        shape: tuple[int, int],
    ) -> np.ndarray:
        """Which pixels of a slice defacing keeps for the targets: those
        whose boxes may meet a hull.

        Parameters
        ----------
        position : sequence of float
            Image Position (Patient): the centre of the first pixel.
        orientation : sequence of float
            Image Orientation (Patient): the direction along a row, of
            increasing column index, then down a column.
        spacing : sequence of float
            Pixel Spacing: between rows, then between columns, in
            millimetres.
        shape : tuple of int
            Rows, then columns.

        Returns
        -------
        numpy.ndarray
            Of bool, of ``shape``.
        """
        kept = np.zeros(shape, dtype=bool)
        if not self.hulls:
            return kept
        origin = np.asarray(position, dtype=float)
        along_row = np.asarray(orientation[:3], dtype=float)
        down_column = np.asarray(orientation[3:], dtype=float)
        normal = np.cross(along_row, down_column)
        normal = normal / np.linalg.norm(normal)
        row_spacing, column_spacing = float(spacing[0]), float(spacing[1])
        halves = np.array(
            [
                along_row * column_spacing / 2,
                down_column * row_spacing / 2,
                normal * self.depth,
            ]
        )
        rows, columns = shape
        for hull in self.hulls:
            offsets = hull.vertices - origin
            heights = offsets @ normal
            if (
                heights.min() > self.depth + _MARGIN
                or heights.max() < -self.depth - _MARGIN
            ):
                continue
            # The pixels whose boxes the hull's points may reach, with one
            # more to each side for direction cosines that are not quite
            # orthogonal.
            along = offsets @ along_row / (column_spacing * (along_row @ along_row))
            down = offsets @ down_column / (row_spacing * (down_column @ down_column))
            first_column = max(0, math.floor(along.min()) - 1)
            last_column = min(columns - 1, math.ceil(along.max()) + 1)
            first_row = max(0, math.floor(down.min()) - 1)
            last_row = min(rows - 1, math.ceil(down.max()) + 1)
            if first_column > last_column or first_row > last_row:
                continue
            grid_rows, grid_columns = np.mgrid[
                first_row : last_row + 1, first_column : last_column + 1
            ]
            centres = (
                origin
                + grid_columns[..., np.newaxis] * column_spacing * along_row
                + grid_rows[..., np.newaxis] * row_spacing * down_column
            )
            met = hull.meets_boxes(centres.reshape(-1, 3), halves)
            kept[first_row : last_row + 1, first_column : last_column + 1] |= (
                met.reshape(grid_rows.shape)
            )
        return kept


def slice_reach(heights: Iterable[float], spacing: Sequence[float]) -> float:
    """How far, in millimetres, a point may lie along the slices' normal from
    its nearest slice and be placed on it: half the smallest spacing between
    the slices, or, for a single slice, half its larger pixel spacing.

    Parameters
    ----------
    heights : iterable of float
        Each slice's position along the slices' normal.
    spacing : sequence of float
        The slices' Pixel Spacing.
    """
    ordered = np.sort(np.asarray(list(heights), dtype=float))
    steps = np.diff(ordered)
    steps = steps[steps > 0]
    return float(np.min(steps)) / 2 if len(steps) else max(spacing) / 2


@dataclasses.dataclass(frozen=True)
class SliceRange:
    """The extent of a series' slices along one direction.

    Attributes
    ----------
    direction : tuple of float
        A unit vector.
    low, high : float
        The least and greatest dot product with it, in millimetres, of a
        point within the slices.
    """

    direction: tuple[float, float, float]
    low: float
    high: float


def slice_ranges(
    slices: Sequence[tuple[Sequence[float], Sequence[float]]],
    spacing: Sequence[float],
    shape: tuple[int, int],
    depth: float,
) -> tuple[SliceRange, ...]:
    """Return the extent of a stack's slices: along their normal, from the
    first to the last, ``depth`` beyond each; and along each of their rows
    and columns, within the squares of every slice's pixels.

    Parameters
    ----------
    slices : sequence of tuple
        Each slice's Image Position (Patient) and Image Orientation
        (Patient); the first's orientation gives the directions.
    spacing : sequence of float
        Their Pixel Spacing, between rows then between columns.
    shape : tuple of int
        Their rows and columns.
    depth : float
        As :attr:`KeptTargets.depth`.
    """
    orientation = np.asarray(slices[0][1], dtype=float)
    along_row, down_column = orientation[:3], orientation[3:]
    normal = np.cross(along_row, down_column)
    ranges = []
    # Along a row, the columns lie a column's spacing apart, and down a
    # column, the rows a row's.
    for vector, step, count in (
        (along_row, float(spacing[1]), shape[1]),
        (down_column, float(spacing[0]), shape[0]),
    ):
        length = float(np.linalg.norm(vector))
        direction = vector / length
        starts = [float(np.dot(position, direction)) for position, _ in slices]
        pixel = step * length
        ranges.append(
            SliceRange(
                (float(direction[0]), float(direction[1]), float(direction[2])),
                max(starts) - pixel / 2,
                min(starts) + (count - 1) * pixel + pixel / 2,
            )
        )
    direction = normal / np.linalg.norm(normal)
    heights = [float(np.dot(position, direction)) for position, _ in slices]
    ranges.append(
        SliceRange(
            (float(direction[0]), float(direction[1]), float(direction[2])),
            min(heights) - depth,
            max(heights) + depth,
        )
    )
    return tuple(ranges)


def beyond_slices(
    hull: TargetHull, block: FaceBlock, ranges: Iterable[SliceRange]
) -> bool:
    """Whether a hull's part in the block may reach beyond the slices, or
    whether that cannot be told.

    The part is the hull's half-spaces with the block's, closed, and its
    greatest and least extent along each range's direction are found as
    linear programmes. A hull that does not meet the block reaches nowhere
    in it.
    """
    anterior = np.asarray(block.anterior, dtype=float)
    origin = np.asarray(block.origin, dtype=float)
    bounds_matrix = np.vstack([hull.normals, -anterior, (0.0, 0.0, -1.0)])
    bounds = np.concatenate(
        [hull.offsets, (-float(origin @ anterior), -float(block.inferior_limit))]
    )
    for each in ranges:
        direction = np.asarray(each.direction, dtype=float)
        for sign, limit in ((1.0, each.high), (-1.0, -each.low)):
            result = scipy.optimize.linprog(
                -sign * direction,
                A_ub=bounds_matrix,
                b_ub=bounds,
                bounds=(None, None),
                method="highs",
            )
            if result.status == 2:
                return False
            if result.status != 0 or not -result.fun <= limit + _MARGIN:
                return True
    return False
