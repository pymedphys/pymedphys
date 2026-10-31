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

"""Renders of a deformable registration's grids for the confidential QC
pack's face review (D-017).

A Deformable Registration Grid Sequence (0064,0005), in an item of a
Deformable Registration Sequence (0064,0002), holds Vector Grid Data
(0064,0009): the displacement, in millimetres, at the centre of each voxel
of a grid over the patient (PS3.3 Section C.20.3). A registration of two
scans moves the skin and the air or couch beside it differently, so the
displacements can change across the patient's outline and trace a face, as
an RT Dose's dose can. :func:`grid_sheets` therefore renders each grid that
an instance holds (:func:`grids_of`), as the run wrote it, as sheets of
nested surfaces, from the six directions of :data:`~.qc_surfaces.VIEWS`, so
that a reviewer can see a face where a grid traces one. A grid's sheets
are, in the order of :data:`QUANTITIES`:

- its displacement: where any vector is undefined, first the voxels where
  the transformation is defined, whose outline can itself follow the
  patient's; then the magnitude of each vector, at each of a ladder of
  levels;
- its variation: at each grid point, the root of the sum, over the grid's
  three axes, of the square of the larger of the magnitudes of the
  displacement's forward and backward differences along the axis, each
  divided by the axis's Grid Resolution, a dimensionless number that is
  large wherever the displacement changes over a short distance, as it can
  across the skin, though its magnitude does not; an axis along which
  neither neighbour of a point is defined adds nothing. The larger of the
  two one-sided differences is taken, rather than their mean, so that a
  change at a single grid point, or at the edge of the defined region,
  shows rather than cancels; and
- each of the displacement's x, y, and z components, along the patient's
  axes: where it is positive, at each of a ladder of levels, then, after a
  white rule, where it is negative, by its magnitude, at each of another;
  a component's sign can change across the skin where its magnitude, and
  the vector's, does not.

Each ladder is that of an RT Dose's dose-levels sheet
(:func:`~.qc_surfaces.dose_levels`), from the greatest value and the
smallest above 0 of what it shows: its support, the voxels of any value
above 0, then each fraction of the greatest of 0.5, 0.2, 0.1, 0.05, and so
on down, while above the smallest, so that an outline that holds over a
band of values wider than a factor of 2.5 shows in at least one row; but
at most :data:`~.qc_surfaces.MAXIMUM_DOSE_LEVELS` levels, the highest, so
that values more than some 13 decades below the greatest show only in the
support (:func:`ladder_levels`). Each level's row is followed by the rows
of :func:`~.qc_surfaces.hidden_rows`, and the rows are laid out as an RT
Dose's (:func:`~.qc_surfaces.level_sheet`), in grey; ladders are separated
by white rows of :data:`LADDER_RULE`.

Each grid point lies at Image Position (Patient) (0020,0032), plus its
index along each of the grid's axes times that axis's Grid Resolution
(0064,0008), along the row direction, the column direction of Image
Orientation (Patient) (0020,0037), and their cross product, as Equation
C.20.3-1 places it; Grid Dimensions (0064,0007) give how many points lie
along each, and the vectors run along the rows first, then the columns,
then the planes. The grid's orientation is any whose direction cosines are
each of unit length, and the two orthogonal, within
:data:`_ORIENTATION_TOLERANCE`. Its quantities are sampled to cubic voxels
along the patient's axes, of :data:`~.qc_surfaces.MINIMUM_VOXEL`
millimetres, or of its smallest Grid Resolution along an axis of two points
or more where that is larger, which lie at whole multiples of their side,
and span the grid's points and half a cell beyond, with a voxel more on
each side. Each voxel holds the greatest of the value of the grid point
nearest its centre, where that centre is within half a cell of it along
each of the grid's axes, and of the value of each grid point whose nearest
voxel it is, so that every grid point is drawn, where points are closer
than the voxels as where they are farther apart, and every voxel within the
grid is drawn from a grid point. An undefined vector, (NaN, NaN, NaN) as
PS3.3 Section C.20.3.1.3 gives it, is below every level, and its point in
no ladder but the defined voxels' absence.

A grid is drawn only where :func:`grids_of` can read it: an item's Image
Orientation (Patient), Image Position (Patient), Grid Dimensions, Grid
Resolution, and Vector Grid Data are each present and of their
multiplicity, the orientation as above, the position finite and within
:data:`~.qc_contours.FARTHEST` millimetres, the resolutions finite and
above 0, the dimensions at least 1, and the Vector Grid Data, of a data set
read in little endian, of exactly three 32-bit floats for each point, each
vector either finite or undefined in all three of its components; and where
its points span at most :data:`~.qc_surfaces.LONGEST` millimetres along the
patient's z axis and :data:`~.qc_surfaces.WIDEST` across. A grid is not
drawn either where a sheet would be taller than
:data:`MAXIMUM_SHEET_PIXELS`, or a quantity's value would be too large, or
a level too small, for 32-bit floating point, as a voxel holds them. An
instance any of whose grids is not drawn is shown by none of its sheets,
and a verdict cannot release it.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Iterator

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import qc_contours, qc_surfaces
from .face_review import (
    DEFORMABLE_REGISTRATION_GRID_SEQUENCE,
    DEFORMABLE_REGISTRATION_SEQUENCE,
    GRID_TAGS,
)

(
    IMAGE_ORIENTATION,
    IMAGE_POSITION,
    GRID_DIMENSIONS,
    GRID_RESOLUTION,
    VECTOR_GRID_DATA,
) = GRID_TAGS
# The quantities whose sheets a grid has, in order.
QUANTITIES = ("displacement", "variation", "x", "y", "z")
# The grey of the rows between one ladder and the next, white, so that they
# can be told apart from the grey rules between one level's rows and the
# next level's.
LADDER_RULE = 255
# The tallest sheet that is drawn, as an RT Dose's; a taller one is not,
# so that its grid is held rather than shown in an image that a viewer may
# scale down or refuse.
MAXIMUM_SHEET_PIXELS = qc_surfaces.MAXIMUM_DOSE_SHEET_PIXELS
# As qc_previews and qc_segments: how far from unit length, and from
# orthogonal, the direction cosines may be.
_ORIENTATION_TOLERANCE = 1e-4
# The white rows between ladders are as tall as the gaps between rows.
_RULE_PIXELS = 4
# The most points of a grid that is drawn, whose indices are held as 32-bit
# integers, as are its voxels', which, of 2 mm or more within the volume
# limits, are fewer.
_MOST_POINTS = 2**31 - 1


@dataclasses.dataclass(frozen=True, repr=False)
class DeformationGrid:
    """One grid of a deformable registration, placed in the patient's
    coordinates.

    Its ``repr`` shows only its dimensions.

    Attributes
    ----------
    origin : tuple of float
        Image Position (Patient): the centre of its first point.
    directions : numpy.ndarray
        Of shape (3, 3): the row direction, the column direction, and their
        cross product, each a unit vector, along which the first, second,
        and third of ``resolution`` and of the dimensions lie.
    resolution : tuple of float
        Grid Resolution, in millimetres, along each of ``directions``.
    vectors : numpy.ndarray
        Of shape (planes, rows, columns, 3), float32: each point's
        displacement, in millimetres, along the patient's x, y, and z axes;
        an undefined one is NaN in each component.
    """

    origin: tuple[float, float, float]
    directions: np.ndarray
    resolution: tuple[float, float, float]
    vectors: np.ndarray

    @property
    def dimensions(self) -> tuple[int, int, int]:
        """Grid Dimensions: how many points along each of ``directions``."""
        planes, rows, columns = self.vectors.shape[:3]
        return (columns, rows, planes)

    def __repr__(self) -> str:
        return f"DeformationGrid(dimensions={self.dimensions})"


def grids_of(dataset: pydicom.Dataset) -> tuple[DeformationGrid, ...] | None:
    """Return each grid that a data set holds, in the order of its items,
    or None where any cannot be drawn, as the module describes.

    Every item of each Deformable Registration Grid Sequence in each item
    of the Deformable Registration Sequence is a grid, though PS3.3 permits
    one, so that none is left out. A data set without either sequence, or
    with only empty ones, holds none.
    """
    if DEFORMABLE_REGISTRATION_SEQUENCE not in dataset:
        return ()
    try:
        little = getattr(dataset, "original_encoding", (None, True))[1]
        if little is False:
            return None
        found = []
        for item in dataset[DEFORMABLE_REGISTRATION_SEQUENCE].value:
            if DEFORMABLE_REGISTRATION_GRID_SEQUENCE not in item:
                continue
            for grid in item[DEFORMABLE_REGISTRATION_GRID_SEQUENCE].value or ():
                placed = _grid(grid)
                if placed is None:
                    return None
                found.append(placed)
    # Whatever reading a sequence or value raises, its grids cannot be
    # drawn.
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    return tuple(found)


def _grid(item: pydicom.Dataset) -> DeformationGrid | None:  # pylint: disable = too-many-return-statements
    """One grid item's grid, or None where it cannot be drawn."""
    orientation = _floats(item, IMAGE_ORIENTATION, 6)
    origin = _floats(item, IMAGE_POSITION, 3)
    resolution = _floats(item, GRID_RESOLUTION, 3)
    dimensions = _floats(item, GRID_DIMENSIONS, 3)
    if orientation is None or origin is None or resolution is None:
        return None
    if dimensions is None or VECTOR_GRID_DATA not in item:
        return None
    row, column = np.array(orientation[:3]), np.array(orientation[3:])
    if (
        abs(np.linalg.norm(row) - 1) > _ORIENTATION_TOLERANCE
        or abs(np.linalg.norm(column) - 1) > _ORIENTATION_TOLERANCE
        or abs(float(row @ column)) > _ORIENTATION_TOLERANCE
    ):
        return None
    if any(abs(value) > qc_contours.FARTHEST for value in origin):
        return None
    if not all(value > 0 for value in resolution):
        return None
    if not all(value >= 1 and value == int(value) for value in dimensions):
        return None
    columns, rows, planes = (int(value) for value in dimensions)
    count = columns * rows * planes
    # Each point's index is held as a 32-bit integer.
    if count > _MOST_POINTS:
        return None
    data = item[VECTOR_GRID_DATA].value
    if not isinstance(data, bytes) or len(data) != count * 12:
        return None
    vectors = (
        np.frombuffer(data, "<f4").astype(np.float32).reshape(planes, rows, columns, 3)
    )
    undefined = np.isnan(vectors)
    finite = np.isfinite(vectors)
    # A vector is defined in all three components, or undefined in all.
    if not (finite.all(axis=-1) | undefined.all(axis=-1)).all():
        return None
    directions = np.array([row, column, np.cross(row, column)])
    placed = DeformationGrid(
        (origin[0], origin[1], origin[2]),
        directions,
        (resolution[0], resolution[1], resolution[2]),
        vectors,
    )
    low, high = _extent(placed)
    spans = high - low
    if spans[2] > qc_surfaces.LONGEST or max(spans[:2]) > qc_surfaces.WIDEST:
        return None
    return placed


def _floats(item: pydicom.Dataset, tag: int, count: int) -> tuple[float, ...] | None:
    """An attribute's values as finite numbers, None unless it has ``count``."""
    if tag not in item:
        return None
    value = item[tag].value
    values = (
        list(value)
        if isinstance(value, (list, tuple, pydicom.multival.MultiValue))
        else [value]
    )
    if len(values) != count:
        return None
    found = tuple(float(each) for each in values)
    return found if all(math.isfinite(each) for each in found) else None


def _extent(grid: DeformationGrid) -> tuple[np.ndarray, np.ndarray]:
    """The lowest and highest coordinate along each patient axis of the
    centre of any grid point."""
    origin = np.array(grid.origin)
    reaches = [
        direction * step * (count - 1)
        for direction, step, count in zip(
            grid.directions, grid.resolution, grid.dimensions
        )
    ]
    low, high = origin.copy(), origin.copy()
    for reach in reaches:
        low += np.minimum(reach, 0.0)
        high += np.maximum(reach, 0.0)
    return low, high


class _Sampling:
    """Where a grid's points fall among cubic voxels along the patient's axes."""

    def __init__(self, grid: DeformationGrid) -> None:
        self._grid = grid
        steps = [
            step for step, count in zip(grid.resolution, grid.dimensions) if count > 1
        ]
        voxel = max(qc_surfaces.MINIMUM_VOXEL, min(steps, default=0.0))
        self.voxel = voxel
        low, high = _extent(grid)
        # Half a cell beyond the outermost points, along each patient axis.
        reach = np.abs(grid.directions).T @ (np.array(grid.resolution) / 2)

        def along(index: int) -> np.ndarray:
            first = math.floor((low[index] - reach[index]) / voxel + 1e-6) - 1
            last = math.ceil((high[index] + reach[index]) / voxel - 1e-6) + 1
            return np.arange(first, last + 1) * voxel

        # x and y ascending, z descending, so that a mask of them is indexed
        # from superior, from anterior, and from the patient's right, as
        # views take one.
        self.xs, self.ys, self.zs = along(0), along(1), along(2)[::-1]
        self.shape = (len(self.zs), len(self.ys), len(self.xs))
        self._pulled = self._pull()
        self._pushed = self._push()

    def _pull(self) -> np.ndarray:
        """The flat index of the grid point nearest each voxel's centre, or
        -1 where it is more than half a cell from every point."""
        grid = self._grid
        columns, rows, _ = grid.dimensions
        origin = np.array(grid.origin)
        found = np.full(self.shape, -1, np.int32)
        relative_x = self.xs - origin[0]
        relative_y = self.ys - origin[1]
        for index, z in enumerate(self.zs):
            relative_z = z - origin[2]
            indices = []
            inside = np.ones(self.shape[1:], bool)
            for direction, step, count in zip(
                grid.directions, grid.resolution, grid.dimensions
            ):
                along = np.rint(
                    (
                        direction[0] * relative_x[np.newaxis, :]
                        + direction[1] * relative_y[:, np.newaxis]
                        + direction[2] * relative_z
                    )
                    / step
                )
                inside &= (along >= 0) & (along <= count - 1)
                indices.append(along)
            # Whole numbers, below the most points, so exact as int32.
            flat = (indices[2] * rows + indices[1]) * columns + indices[0]
            found[index] = np.where(inside, flat, -1)
        return found.reshape(-1)

    def _push(self) -> np.ndarray:
        """The flat index of the voxel nearest each grid point."""
        grid = self._grid
        columns, rows, planes = grid.dimensions
        across = np.arange(columns)[np.newaxis, :] * grid.resolution[0]
        down = np.arange(rows)[:, np.newaxis] * grid.resolution[1]
        found = np.empty((planes, rows, columns), np.int32)
        for plane in range(planes):
            points = (
                np.array(grid.origin)[:, np.newaxis, np.newaxis]
                + grid.directions[0][:, np.newaxis, np.newaxis] * across
                + grid.directions[1][:, np.newaxis, np.newaxis] * down
                + grid.directions[2][:, np.newaxis, np.newaxis]
                * (plane * grid.resolution[2])
            )
            x = np.rint((points[0] - self.xs[0]) / self.voxel).astype(np.int64)
            y = np.rint((points[1] - self.ys[0]) / self.voxel).astype(np.int64)
            z = np.rint((self.zs[0] - points[2]) / self.voxel).astype(np.int64)
            found[plane] = (z * self.shape[1] + y) * self.shape[2] + x
        return found.reshape(-1)

    def volume(self, values: np.ndarray) -> np.ndarray:
        """The voxels' values, as the module describes, from a value at each
        grid point, in the order of the vectors; NaN where none is."""
        flat = values.reshape(-1)
        sampled = np.full(self._pulled.shape, np.nan, np.float32)
        pulled = self._pulled >= 0
        sampled[pulled] = flat[self._pulled[pulled]]
        # fmax keeps a voxel's greatest value, and ignores NaN, which is no
        # value, unless every value is.
        np.fmax.at(sampled, self._pushed, flat)
        return sampled.reshape(self.shape)


def grid_sheets(
    grid: DeformationGrid, tallest: int | None = None
) -> tuple[np.ndarray, ...] | None:
    """Return a grid's sheets, in the order of :data:`QUANTITIES`, as the
    module describes, each as 8-bit grey.

    Parameters
    ----------
    grid : DeformationGrid
        As :func:`grids_of` gives it of the file written.
    tallest : int, optional
        The most pixels that each sheet may be tall; by default
        :data:`MAXIMUM_SHEET_PIXELS`.

    Returns
    -------
    tuple of numpy.ndarray or None
        None where any sheet cannot be drawn: a sheet would be taller than
        ``tallest``, or a value would be too large, or a level too small,
        for 32-bit floating point.
    """
    if tallest is None:
        tallest = MAXIMUM_SHEET_PIXELS
    sampling = _Sampling(grid)
    sheets = []
    for ladders in _quantities(grid):
        sheet = _sheet(sampling, ladders, tallest)
        if sheet is None:
            return None
        sheets.append(sheet)
    return tuple(sheets)


# A ladder's values at each grid point, in the order of the vectors, NaN
# where none is, and whether it shows only where they are defined.
type _Ladder = tuple[np.ndarray, bool]


def _quantities(grid: DeformationGrid) -> Iterator[list[_Ladder]]:
    """Each sheet's ladders, in the order of :data:`QUANTITIES`, each
    found only when its sheet is drawn."""
    vectors = grid.vectors.astype(np.float64)
    defined = ~np.isnan(vectors[..., 0])
    magnitude = np.sqrt((vectors**2).sum(axis=-1))
    displacement: list[_Ladder] = []
    if not defined.all():
        displacement.append((np.where(defined, 1.0, np.nan), True))
    displacement.append((magnitude, False))
    yield displacement
    yield [(_variation(vectors, grid.resolution), False)]
    for axis in range(3):
        component = vectors[..., axis]
        yield [(component, False), (-component, False)]


def _variation(vectors: np.ndarray, resolution: tuple[float, ...]) -> np.ndarray:
    """At each grid point, the root sum over the grid's axes of the square
    of the larger of the magnitudes of its forward and backward
    differences, each per millimetre; NaN where its vector is undefined."""
    total = np.zeros(vectors.shape[:3])
    # The vectors' axes are the planes', rows', and columns', along the
    # third, second, and first of the grid's directions.
    for axis, step in zip((2, 1, 0), resolution):
        if vectors.shape[axis] < 2:
            continue
        squared = (np.diff(vectors, axis=axis) ** 2).sum(axis=-1) / step**2
        pad = [(0, 0)] * 3
        forward = np.pad(squared, _padded(pad, axis, (0, 1)), constant_values=np.nan)
        backward = np.pad(squared, _padded(pad, axis, (1, 0)), constant_values=np.nan)
        with np.errstate(invalid="ignore"):
            larger = np.fmax(forward, backward)
        total += np.nan_to_num(larger, nan=0.0)
    result: np.ndarray = np.where(np.isnan(vectors[..., 0]), np.nan, np.sqrt(total))
    return result


def _padded(pad: list, axis: int, ends: tuple[int, int]) -> list:
    pad = list(pad)
    pad[axis] = ends
    return pad


def _sheet(
    sampling: _Sampling, ladders: list[_Ladder], tallest: int
) -> np.ndarray | None:
    """A sheet of ladders, each after a white rule, or None where it cannot
    be drawn."""
    found = []
    for values, defined_only in ladders:
        levels = (0.0,) if defined_only else ladder_levels(values)
        held = _held(values, levels)
        if held is None:
            return None
        found.append((held, levels))
    # Each level has a row at least, so a sheet that cannot fit is refused
    # before any is drawn.
    rows = sampling.shape[0]
    least = (
        sum(len(levels) * (rows + _RULE_PIXELS) for _, levels in found) - _RULE_PIXELS
    )
    if least > tallest:
        return None
    parts: list[np.ndarray] = []
    height = 0
    for held, levels in found:
        volume = sampling.volume(held)
        if parts:
            height += _RULE_PIXELS
        drawn = qc_surfaces.level_sheet(_masks(volume), levels, tallest - height)
        if drawn is None:
            return None
        if parts:
            parts.append(np.full((_RULE_PIXELS, drawn.shape[1]), LADDER_RULE, np.uint8))
        parts.append(drawn)
        height += drawn.shape[0]
    return np.concatenate(parts)


def _masks(volume: np.ndarray) -> Callable[[float], np.ndarray]:
    """The voxels at or above a level, or above 0 at a level of 0; NaN, no
    value, is below every level."""

    def mask(level: float) -> np.ndarray:
        with np.errstate(invalid="ignore"):
            inside: np.ndarray = volume >= np.float32(level) if level else volume > 0
        return inside

    return mask


def ladder_levels(values: np.ndarray) -> tuple[float, ...]:
    """Return the levels of a ladder of values, ascending: its support, 0,
    then :func:`~.qc_surfaces.dose_levels` of the greatest value and the
    smallest above 0, the highest :data:`~.qc_surfaces.MAXIMUM_DOSE_LEVELS`
    less one of them.

    A displacement that a smooth registration spreads into the air or
    couch can fall to a fraction of its greatest smaller than any dose
    grid's, such as 1e-45, which would take some 135 levels; the ladder
    then stops some 13 decades below its greatest value, and values below
    its lowest level show only in its support.
    """
    finite = values[np.isfinite(values)]
    positive = finite[finite > 0]
    if not positive.size:
        return (0.0,)
    levels = qc_surfaces.dose_levels(float(positive.max()), float(positive.min()))
    most = qc_surfaces.MAXIMUM_DOSE_LEVELS - 1
    return (0.0, *levels[1:][-most:])


def _held(values: np.ndarray, levels: tuple[float, ...]) -> np.ndarray | None:
    """Values as 32-bit floats, as a voxel holds them, those above 0 that
    are too small for one held as its smallest above 0, below every level;
    or None where one would be too large for one, or a level other than 0
    smaller than its smallest normal number, below which values and levels
    run together."""
    if any(0 < level < np.finfo(np.float32).tiny for level in levels):
        return None
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        held = values.astype(np.float32)
    positive = values > 0
    if not np.isfinite(held[positive]).all():
        return None
    smallest = np.nextafter(np.float32(0), np.float32(1))
    held[positive & (held == 0)] = smallest
    return held
