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

"""The QC pack's sheet of a CT series' globes beside its eye ROIs (D-050).

Under the Clean Recognizable Visual Features Option, a run defaces a CT
series whose eye ROIs disagree with the globes that its face block was
found from, and holds it until a reviewer confirms the block
(:mod:`~pymedphys._dicom.deidentify.face_blocks`). The reviewer decides from
this sheet, which the run draws from the series' slices as received, before
it writes any instance, so that it shows the eyes that defacing removes.

The sheet is a grid of square tiles, :data:`FIELD` millimetres a side at
:data:`PIXEL` millimetres a pixel, in rows of three planes through one
point: an axial plane, viewed from the feet, with the patient's anterior up
and right on the viewer's left; a coronal plane, viewed from the front, with
the head up and the patient's right on the viewer's left; and a sagittal
plane, viewed from the patient's left, with the head up and anterior on the
viewer's left. The first row is through the centre of the right globe that
the finder found, the second through the left's, and each row after them
through the point farthest from both globes of one eye ROI that disagrees,
the farthest first, up to :data:`EYE_ROWS` of them. An axial plane, or
whichever lies along the slices, is taken through the slice nearest the
point, so that it shows that slice. Each tile shows:

- the slices in Hounsfield units, sampled by nearest neighbour from the
  nearest slice within half the spacing between slices, and its nearest
  pixel, windowed from :data:`WINDOW`'s lower value, black, to its upper,
  white, so that a globe's vitreous shows grey within the darker orbital
  fat and bright bone; a point beyond the slices is dark grey, and padding
  black;
- the face block (D-046) tinted blue, every pixel whose centre it holds;
  defacing keeps the brain above the orbits, padding, and each kept
  target's hull within it, which the tint does not leave out;
- each globe found, as a cyan cross at its centre where the plane passes
  within the reach of it that a run allows an eye ROI,
  :data:`~.face_blocks.EYE_REACH`, and a cyan circle where the plane cuts
  the sphere of that radius about it, within which every point of an eye
  ROI must lie; and
- each eye ROI's contours where they cross the plane, within half a pixel,
  or, along the slices' normal, half the spacing between slices: yellow
  where a point lies within that reach of the nearer globe, and red where
  it lies beyond, so that the part that disagrees stands out.

A confirmation says that the globes found are the patient's eyes, so that
the block lies where D-046 places it, whatever the ROIs show. The verdict
on the series' face, from the pack's previews of the slices as written, is
separate, and is still needed to release them.

The sheet holds no text, so its layout is this module's, and the QC pack
names the frames that it was drawn from, which never count as shown in a
way that could show a face (:func:`~.qc_pack.pictured_frames`), since the
sheet is of the slices as received, not as written.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence

from pymedphys._imports import numpy as np

from .defacing import FaceBlock

FIELD = 160.0  # millimetres, the side of each tile
PIXEL = 0.5  # millimetres, the side of each tile's pixels
# The most rows of eye ROIs that disagree, after the two globes' rows.
EYE_ROWS = 8
# Hounsfield units, shown from black to white.
WINDOW = (-160.0, 240.0)
# The most points that one contour is sampled at, beyond its own, so that a
# malformed contour cannot take the run's memory; past it, only its points
# are drawn.
_SAMPLES = 1 << 20
# The patient axes, x to the patient's left, y posterior, and z superior,
# along each tile's columns and down its rows, by the axis normal to it:
# a sagittal tile, normal to x, runs posterior along its columns and
# inferior down its rows; a coronal tile, normal to y, runs to the
# patient's left and inferior; an axial tile, normal to z, runs to the
# patient's left and posterior.
_TILE_AXES = {
    0: ((1, 1.0), (2, -1.0)),
    1: ((0, 1.0), (2, -1.0)),
    2: ((0, 1.0), (1, 1.0)),
}
# The order of a row's tiles: axial, coronal, then sagittal.
_ORDER = (2, 1, 0)
_BEYOND = (40, 40, 40)  # a point beyond the slices
_BLOCK = (0, 128, 255)
_BLOCK_SHARE = 0.35
_GLOBE = (0, 255, 255)
_AGREES = (255, 255, 0)
_DISAGREES = (255, 32, 0)
_CROSS = 3.0  # millimetres, half a cross's arm
_GUTTER_PIXELS = 8
_GUTTER = (128, 128, 128)
# How finely, as a share of a pixel, a contour's segments are sampled.
_STEP = 0.5


@dataclasses.dataclass(frozen=True)
class SliceGeometry:
    """Where a CT slice lies, as the face block's finder places it.

    Attributes
    ----------
    position : tuple of float
        Image Position (Patient): the centre of the first pixel.
    orientation : tuple of float
        Image Orientation (Patient).
    spacing : tuple of float
        Pixel Spacing: between rows, then between columns.
    shape : tuple of int
        Rows, then columns.
    """

    position: tuple[float, float, float]
    orientation: tuple[float, ...]
    spacing: tuple[float, float]
    shape: tuple[int, int]


@dataclasses.dataclass(frozen=True)
class Plane:
    """One tile's plane: normal to a patient axis, through a point.

    Attributes
    ----------
    axis : int
        The patient axis normal to it: 0 for a sagittal plane, 1 coronal, 2
        axial.
    centre : tuple of float
        The x, y, and z of the point at the tile's centre, in millimetres.
    """

    axis: int
    centre: tuple[float, float, float]

    def points(self) -> np.ndarray:
        """The x, y, and z of each of the tile's pixels' centres, rows by
        columns along the first two axes."""
        count = round(FIELD / PIXEL)
        offsets = (np.arange(count) - (count - 1) / 2) * PIXEL
        (across, across_sign), (down, down_sign) = _TILE_AXES[self.axis]
        points = np.empty((count, count, 3))
        points[...] = self.centre
        points[..., across] += across_sign * offsets[np.newaxis, :]
        points[..., down] += down_sign * offsets[:, np.newaxis]
        return points

    def pixel(self, points: np.ndarray | Sequence[float]) -> tuple:
        """The row and column, from 0, of each point's projection onto the
        tile: floats for one point, x, y, and z, or arrays for points along
        the last axis."""
        points = np.asarray(points, dtype=float)
        count = round(FIELD / PIXEL)
        (across, across_sign), (down, down_sign) = _TILE_AXES[self.axis]
        middle = (count - 1) / 2
        column = (
            middle + across_sign * (points[..., across] - self.centre[across]) / PIXEL
        )
        row = middle + down_sign * (points[..., down] - self.centre[down]) / PIXEL
        return row, column


@dataclasses.dataclass(frozen=True, repr=False)
class EyeSheet:
    """The sheet of one series' globes beside its eye ROIs, as the module
    describes.

    Its ``repr`` shows only its size and counts.

    Attributes
    ----------
    image : numpy.ndarray
        uint8 RGB, rows by columns by 3.
    frames : tuple of (int, int)
        The slices that it was drawn from, each by its instance's run
        position and frame index from 0, in run position and frame order.
    total_frames : int
        How many slices the series has.
    rows : int
        How many rows of tiles it has: the two globes', then one for each
        eye ROI that disagrees, up to :data:`EYE_ROWS`.
    """

    image: np.ndarray
    frames: tuple[tuple[int, int], ...]
    total_frames: int
    rows: int

    def __repr__(self) -> str:
        return (
            f"EyeSheet(shape={self.image.shape}, frames={len(self.frames)}, "
            f"total_frames={self.total_frames}, rows={self.rows})"
        )


def planes_of(
    block: FaceBlock,
    rois: Sequence[Sequence[tuple[str, np.ndarray]]],
    reach: float,
) -> tuple[Plane, ...]:
    """The planes of a sheet's tiles, row by row, as the module describes.

    Parameters
    ----------
    block : FaceBlock
    rois : sequence of sequence of (str, numpy.ndarray)
        Each eye ROI's contours, each by its Contour Geometric Type and its
        points.
    reach : float
        How far, in millimetres, each point of an eye ROI may lie from the
        nearer globe's centre; an ROI with a point farther, or one that is
        not a number, disagrees.
    """
    rows: list[tuple[float, float, float]] = [_point(globe) for globe in block.globes]
    farthest: list[tuple[float, tuple[float, float, float]]] = []
    for contours in rois:
        given = [
            np.asarray(points, dtype=float).reshape(-1, 3) for _, points in contours
        ]
        if not given:
            continue
        joined = np.concatenate(given)
        finite = joined[np.isfinite(joined).all(axis=1)]
        distances = _distances(finite, block)
        # An ROI with a point that is not a number disagrees, though only
        # its finite points can be drawn.
        if not len(finite) or (len(finite) == len(joined) and distances.max() <= reach):
            continue
        index = int(np.argmax(distances))
        farthest.append((float(distances[index]), _point(finite[index])))
    farthest.sort(key=lambda each: -each[0])
    rows.extend(point for _, point in farthest[:EYE_ROWS])
    return tuple(Plane(axis, point) for point in rows for axis in _ORDER)


def _point(values: Sequence[float]) -> tuple[float, float, float]:
    x, y, z = (float(value) for value in values)
    return x, y, z


class Sampler:
    """Samples a sheet's tiles from a stack of slices, as they are added.

    Parameters
    ----------
    planes : sequence of Plane
    slices : sequence of SliceGeometry
        Each slice of one stack, sharing orientation, spacing, and shape,
        in any order.

    Attributes
    ----------
    wanted : frozenset of int
        The indices into ``slices`` of those from which a tile takes a
        pixel; only these need be added.
    """

    def __init__(self, planes: Sequence[Plane], slices: Sequence[SliceGeometry]):
        if not planes or not slices:
            raise ValueError("a sheet needs a plane and a slice")
        first = slices[0]
        along_row = np.asarray(first.orientation[:3], dtype=float)
        down_column = np.asarray(first.orientation[3:], dtype=float)
        normal = np.cross(along_row, down_column)
        origins = np.asarray([each.position for each in slices], dtype=float)
        offsets = origins @ normal
        order = np.argsort(offsets, kind="stable")
        ordered = offsets[order]
        gaps = np.diff(ordered)
        half = (
            float(np.min(gaps)) / 2
            if len(gaps)
            else max(float(s) for s in first.spacing) / 2
        )
        # A plane along the slices is taken through the nearest slice.
        planes = [self._snapped(plane, ordered, normal) for plane in planes]
        self._planes = tuple(planes)
        self._values = [
            np.full((round(FIELD / PIXEL),) * 2, np.nan, np.float32) for _ in planes
        ]
        self._beyond = []
        self._taken: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
        wanted: set[int] = set()
        rows, columns = first.shape
        for plane in planes:
            points = plane.points()
            along = points @ normal
            nearest = _nearest(ordered, along)
            index = order[nearest]
            within = np.abs(ordered[nearest] - along) <= half + 1e-6
            relative = points - origins[index]
            column = np.rint(relative @ along_row / float(first.spacing[1]))
            row = np.rint(relative @ down_column / float(first.spacing[0]))
            within &= (row >= 0) & (row < rows) & (column >= 0) & (column < columns)
            self._beyond.append(~within)
            self._taken.append(
                (index, row.astype(np.intp), column.astype(np.intp), within)
            )
            wanted.update(int(each) for each in np.unique(index[within]))
        self.wanted = frozenset(wanted)
        self.half_spacing = half
        self.normal = normal

    @staticmethod
    def _snapped(plane: Plane, ordered: np.ndarray, normal: np.ndarray) -> Plane:
        if abs(abs(float(normal[plane.axis])) - 1) > 1e-4:
            return plane
        sign = 1.0 if normal[plane.axis] > 0 else -1.0
        offset = float(
            ordered[_nearest(ordered, np.array([sign * plane.centre[plane.axis]]))[0]]
        )
        centre = list(plane.centre)
        centre[plane.axis] = sign * offset
        return Plane(plane.axis, _point(centre))

    def add(self, index: int, values: np.ndarray) -> None:
        """Take each tile's pixels from slice ``index``, in Hounsfield units,
        with padding as NaN."""
        for tile, (indices, row, column, within) in zip(self._values, self._taken):
            chosen = within & (indices == index)
            tile[chosen] = values[row[chosen], column[chosen]]

    def tiles(self) -> list[tuple[Plane, np.ndarray, np.ndarray]]:
        """Each tile's plane, its values, and where it lies beyond the slices."""
        return list(zip(self._planes, self._values, self._beyond))


def eye_sheet(
    block: FaceBlock,
    rois: Sequence[Sequence[tuple[str, np.ndarray]]],
    reach: float,
    sampler: Sampler,
    frames: tuple[tuple[int, int], ...],
    total_frames: int,
) -> EyeSheet:
    """Draw a series' sheet, as the module describes, from the slices that a
    :class:`Sampler` was given.

    Parameters
    ----------
    block : FaceBlock
    rois : sequence of sequence of (str, numpy.ndarray)
        Each eye ROI's contours, as for :func:`planes_of`, which gave the
        sampler's planes.
    reach : float
        As for :func:`planes_of`.
    sampler : Sampler
        Given every slice that it wanted.
    frames : tuple of (int, int)
        Those slices, by run position and frame index, in order.
    total_frames : int
        How many slices the series has.
    """
    drawn = []
    for plane, values, beyond in sampler.tiles():
        tile = _windowed(values, beyond)
        inside = block.contains(plane.points())
        tile[inside] = np.round(
            tile[inside] * (1 - _BLOCK_SHARE) + np.asarray(_BLOCK, float) * _BLOCK_SHARE
        ).astype(np.uint8)
        _draw_globes(tile, plane, block, reach)
        # Along the slices, a contour is drawn from the slice shown alone.
        slab = (
            sampler.half_spacing
            if abs(abs(float(sampler.normal[plane.axis])) - 1) <= 1e-4
            else PIXEL / 2
        )
        for contours in rois:
            for kind, contour in contours:
                _draw_contour(tile, plane, block, reach, (kind, contour), slab)
        drawn.append(tile)
    columns = len(_ORDER)
    rows = len(drawn) // columns
    laid = [
        _beside(drawn[row * columns : (row + 1) * columns], axis=1)
        for row in range(rows)
    ]
    return EyeSheet(_beside(laid, axis=0), frames, total_frames, rows)


def _windowed(values: np.ndarray, beyond: np.ndarray) -> np.ndarray:
    """A tile's values as RGB under :data:`WINDOW`, padding black, and dark
    grey beyond the slices."""
    low, high = WINDOW
    scaled = np.nan_to_num(np.clip((values - low) / (high - low), 0.0, 1.0), nan=0.0)
    grey = np.round(scaled * 255).astype(np.uint8)
    tile = np.repeat(grey[..., np.newaxis], 3, axis=2)
    tile[beyond] = _BEYOND
    return tile


def _draw_globes(
    tile: np.ndarray, plane: Plane, block: FaceBlock, reach: float
) -> None:
    """Draw each globe's centre and the circle where the plane cuts the
    sphere of ``reach`` about it."""
    for globe in block.globes:
        distance = abs(float(globe[plane.axis]) - plane.centre[plane.axis])
        if distance >= reach:
            continue
        row, column = (float(each) for each in plane.pixel(globe))
        radius = math.sqrt(reach**2 - distance**2) / PIXEL
        steps = max(8, math.ceil(2 * math.pi * radius / _STEP))
        angles = np.linspace(0.0, 2 * math.pi, steps, endpoint=False)
        _mark(
            tile,
            row + radius * np.sin(angles),
            column + radius * np.cos(angles),
            _GLOBE,
        )
        arm = np.linspace(
            -_CROSS / PIXEL, _CROSS / PIXEL, math.ceil(4 * _CROSS / PIXEL) + 1
        )
        _mark(tile, row + arm, np.full(arm.shape, column), _GLOBE)
        _mark(tile, np.full(arm.shape, row), column + arm, _GLOBE)


def _draw_contour(
    tile: np.ndarray,
    plane: Plane,
    block: FaceBlock,
    reach: float,
    contour: tuple[str, np.ndarray],
    slab: float,
) -> None:
    """Draw the points of a contour, and of its segments, that lie within
    ``slab`` of the plane, coloured by their reach from the nearer globe."""
    kind, points = contour
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    points = points[np.isfinite(points).all(axis=1)]
    if not len(points):
        return
    level = plane.centre[plane.axis]
    shown = [points]
    if kind != "POINT" and len(points) > 1:
        closed = kind.startswith("CLOSED")
        starts = points if closed else points[:-1]
        ends = np.roll(points, -1, axis=0) if closed else points[1:]
        # Only the segments that reach the slab, sampled finely enough that
        # no pixel along them is missed.
        low = np.minimum(starts[:, plane.axis], ends[:, plane.axis])
        high = np.maximum(starts[:, plane.axis], ends[:, plane.axis])
        crossing = (low <= level + slab) & (high >= level - slab)
        starts, ends = starts[crossing], ends[crossing]
        counts = np.maximum(
            1, np.ceil(np.linalg.norm(ends - starts, axis=1) / (PIXEL * _STEP))
        ).astype(np.int64)
        if len(counts) and int(counts.sum()) <= _SAMPLES:
            shown.extend(
                start + np.outer(np.arange(count) / count, end - start)
                for start, end, count in zip(starts, ends, counts)
            )
    joined = np.concatenate(shown)
    joined = joined[np.abs(joined[:, plane.axis] - level) <= slab]
    if not len(joined):
        return
    far = _distances(joined, block) > reach
    for chosen, colour in ((~far, _AGREES), (far, _DISAGREES)):
        if chosen.any():
            rows, columns = plane.pixel(joined[chosen])
            _mark(tile, rows, columns, colour)


def _mark(
    tile: np.ndarray, rows: np.ndarray, columns: np.ndarray, colour: tuple
) -> None:
    """Colour the pixels nearest these rows and columns, within the tile."""
    rows, columns = np.rint(rows).astype(np.intp), np.rint(columns).astype(np.intp)
    within = (
        (rows >= 0)
        & (rows < tile.shape[0])
        & (columns >= 0)
        & (columns < tile.shape[1])
    )
    tile[rows[within], columns[within]] = colour


def _distances(points: np.ndarray, block: FaceBlock) -> np.ndarray:
    """The distance from each point to the nearer globe's centre."""
    globes = np.asarray(block.globes, dtype=float)
    if not len(points):
        return np.zeros(0)
    return np.min(
        np.linalg.norm(np.asarray(points)[:, np.newaxis, :] - globes, axis=2), axis=1
    )


def _nearest(coordinates: np.ndarray, wanted: np.ndarray) -> np.ndarray:
    """The index of the coordinate nearest each wanted one; coordinates ascend."""
    if len(coordinates) == 1:
        return np.zeros(wanted.shape, np.intp)
    right = np.clip(np.searchsorted(coordinates, wanted), 1, len(coordinates) - 1)
    left = right - 1
    closer_left = (wanted - coordinates[left]) <= (coordinates[right] - wanted)
    return np.where(closer_left, left, right)


def _beside(images: list[np.ndarray], axis: int) -> np.ndarray:
    """Lay RGB images out along ``axis``, 1 left to right and 0 top to
    bottom, with a grey gutter between each and the next."""
    shape = list(images[0].shape)
    shape[axis] = _GUTTER_PIXELS
    gutter = np.empty(shape, np.uint8)
    gutter[...] = _GUTTER
    laid: list[np.ndarray] = []
    for image in images:
        laid.extend([gutter, image] if laid else [image])
    return np.concatenate(laid, axis=axis)
