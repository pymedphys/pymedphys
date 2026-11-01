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

"""Skin-surface renders for the confidential QC pack's face review (D-017).

A face-recognition system matches the skin surface reconstructed from a
volume, which neither a cine strip nor a frontal maximum intensity projection
shows. :class:`Surface` renders that surface from the six directions of
:data:`VIEWS`, so that a reviewer attesting that a set holds no recognisable
face can see one where it is. :mod:`~pymedphys._dicom.deidentify.qc_previews`
renders:

- each series that forms a volume, as it describes; and
- each RT Dose instance of two or more frames, placed by Image Position
  (Patient), Image Orientation (Patient), Pixel Spacing, and Grid Frame
  Offset Vector, whose axes lie along the patient's three directions and
  whose frames are evenly spaced, at each of a ladder of dose levels.

Enhanced multi-frame images are not rendered.
:mod:`~pymedphys._dicom.deidentify.qc_contours` renders RT Structure Set
contours by :func:`views`, and by :func:`view_crossings` the surfaces
that one region hides behind its own, and
:mod:`~pymedphys._dicom.deidentify.qc_segments` renders a Segmentation's
segments likewise.

The surface encloses the voxels at or above a threshold, applied after
Rescale Slope and Rescale Intercept, or after Dose Grid Scaling for RT Dose:
:data:`CT_THRESHOLD` Hounsfield units for a CT series; and Otsu's threshold
over the sampled volume for any other series, such as MR or PET, with pixel
padding counted below its lowest value, since padding marks where there is
no patient. Pixel padding, which is NaN, lies below every threshold.

An RT Dose, or a series of RT Dose planes, is rendered at each level of
:func:`dose_levels`, one row of views a level, from the top: its support,
the voxels of any dose above 0, then each fraction of its greatest dose of
0.5, 0.2, 0.1, 0.05, and so on down, whose dose is above its smallest dose
above 0, so that no two neighbouring rows, nor the lowest and the smallest
dose, differ by more than a factor of 2.5. A planning system either sets
dose to zero outside the body, so that the support outlines the skin
wherever the grid reaches past it, or computes a dose in air, so that dose
falls steeply across the skin. The region at or above a level lies inside
the region at or above any lower one, so an outline that holds over a band
of dose wider than a factor of 2.5 shows in at least one row; one that
holds only over a narrower band may show in none. The band is that at each
point of an outline, so one whose dose varies along it can show in parts
across rows. Each level's row is followed by the rows of
:func:`hidden_rows`, where its surface hides some of itself, so that a lower
dose enclosed by a higher one is shown. Each level's rows are separated
from the next level's by grey rows of :data:`LEVEL_RULE`, and from each
other by black, so that each level's group of rows can be told apart. A
sheet taller than :data:`MAXIMUM_DOSE_SHEET_PIXELS`, or of more than
:data:`MAXIMUM_DOSE_LEVELS` levels, is not drawn. Nor is the sheet of a grid
any of whose stored doses its Dose Grid Scaling, held in float32, would
lose (:func:`dose_values`): the whole grid, not only that slice, is then
held. A single plane is shown by :func:`level_bands`.

The volume is sampled by nearest neighbour to cubic voxels of
:data:`MINIMUM_VOXEL` millimetres, or of its smallest spacing where that is
larger, however large the volume, so that a long one's views are taller
rather than coarser. A volume more than :data:`LONGEST` millimetres in
extent along any axis, or more than :data:`WIDEST` across, from left to
right or from front to back, is not rendered, so that its views stay
within bounds at those voxels. Its slices are sampled as they are decoded,
so that it is never held at full resolution, and its views are rendered a
few slices at a time. Each slice is also taken into
the voxels nearest it along the slice axis by their maximum, so that every
slice is drawn, as it would not be by nearest neighbour alone where slices
are closer than the voxels: a voxel is in the surface where any of its
slices is there. Each view looks along
horizontal rays, turned about the superior-inferior axis by its angle in
degrees from anterior towards the patient's left. It shows the first voxel
on each ray that is in the surface, shaded by Lambert's law from the slope
of the depths around it, averaged over a few voxels, and lit from the
viewer, on black. The views are
side by side in the order of :data:`VIEWS`, each with the patient's head at
the top: the frontal view, like the frontal projection, with the patient's
right on the viewer's left; at 90 degrees, from the patient's left, with the
face on the viewer's left; at -90 degrees, from the patient's right,
with the face on the viewer's right; and at 180 degrees, from behind, with
the patient's left on the viewer's left. So a surface that faces the
front, the back, or either side is seen face on by some view, where
nothing nearer that view hides it.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Callable, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

# Each view's angle about the superior-inferior axis, in degrees from anterior
# towards the patient's left: frontal, the two obliques, the two profiles,
# and from behind.
VIEWS = (0, 45, -45, 90, -90, 180)
CT_THRESHOLD = -300.0  # Hounsfield units, between air and soft tissue
# The fractions of an RT Dose's greatest dose that dose_levels takes, in
# each decade, and the greatest.
DOSE_STEPS = (5.0, 2.0, 1.0)
DOSE_TOP = 0.5
MINIMUM_VOXEL = 2.0  # millimetres
# The longest extent, in millimetres, along any axis, of a volume that is
# rendered, longer than a patient, and the widest across, from left to right
# or front to back, wider than any scanner's bore, as for a contour sheet's
# frame; so a view of 2 mm voxels is at most about 1,000 pixels tall and 711
# wide.
LONGEST = 2000.0
WIDEST = 1000.0
# The most pixels that an RT Dose's sheet may be tall, as a contour sheet; a
# taller one is not drawn, so that its grid is held rather than shown in an
# image that a viewer may scale down or refuse.
MAXIMUM_DOSE_SHEET_PIXELS = 32768
# The most levels at which an RT Dose is shown. One grid of 32-bit stored
# values needs at most 29, from a greatest dose of 2**32 - 1 times the
# smallest; the rest allows for a series of planes whose scalings differ.
# More are not drawn, so that planes whose scalings span float32's range
# cannot take minutes to render, and their grid is held.
MAXIMUM_DOSE_LEVELS = 40
# The grey of the rows between one level's rows and the next level's, so
# that each level's group of rows can be told apart; the rows within a
# group are separated by black.
LEVEL_RULE = 128
RT_DOSE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.2"

_OTSU_BINS = 256
# How many values Otsu's threshold counts at once.
_OTSU_PART = 1 << 22
# The brightness of a surface seen edge on, so that it stands out from black.
_AMBIENT = 0.2
# The binomial weights by which depths are averaged along each axis before
# shading.
_SMOOTHING = (1.0, 4.0, 6.0, 4.0, 1.0)
# Black columns between views.
_GAP_PIXELS = 4
# The views whose rays look along an axis of the voxels.
_ALONG = (0, 90, -90, 180)
# How many slices are rendered at once, so that a long volume's rays are
# held in memory a few slices at a time.
_SLICES_AT_A_TIME = 64


class Threshold(enum.Enum):
    """Which threshold gives a volume's surface."""

    CT = "ct"  # CT_THRESHOLD
    OTSU = "otsu"  # Otsu's threshold over the sampled volume, padding lowest
    DOSE = "dose"  # each of dose_levels, a row of views each


@dataclasses.dataclass(frozen=True)
class Grid:
    """Where a volume's voxels lie along the patient's axes, and its threshold.

    Attributes
    ----------
    axes : tuple of int
        For each of the volume's axes, slices, then rows, then columns, the
        patient axis that it lies along: 0 for x, towards the patient's left;
        1 for y, towards posterior; and 2 for z, towards superior.
    coordinates : tuple of tuple of float
        For each of the volume's axes, the coordinate of each index along its
        patient axis, in millimetres.
    threshold : Threshold
    scale : float
        What each slice is multiplied by before the threshold is applied:
        Dose Grid Scaling, or 1.
    """

    axes: tuple[int, int, int]
    coordinates: tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]
    threshold: Threshold
    scale: float = 1.0


def grid(
    directions: Sequence[np.ndarray],
    offsets: Sequence[float],
    spacing: tuple[float, float],
    shape: tuple[int, int],
    threshold: Threshold,
    scale: float = 1.0,
) -> Grid:
    """Return the grid of a volume whose axes lie along the patient's axes.

    Parameters
    ----------
    directions : sequence of numpy.ndarray
        The direction of each of the volume's axes: the normal, along which
        its slices lie, then the direction of increasing row index, then of
        increasing column index. Each lies along a different patient axis.
    offsets : sequence of float
        Each slice's position along the normal, in millimetres, in slice
        order.
    spacing : tuple of float
        Between rows, then between columns, in millimetres.
    shape : tuple of int
        Rows, then columns.
    threshold : Threshold
    scale : float, optional
        What each slice is multiplied by before the threshold is applied.

    Returns
    -------
    Grid
    """
    axes = tuple(int(np.argmax(np.abs(direction))) for direction in directions)
    if len(axes) != 3 or len(set(axes)) != 3:
        raise ValueError("a grid needs its axes along three different patient axes")
    distances = (
        np.asarray(offsets, dtype=float),
        np.arange(shape[0]) * spacing[0],
        np.arange(shape[1]) * spacing[1],
    )
    slices, rows, columns = (
        tuple(float(value) for value in np.sign(direction[axis]) * distance)
        for direction, axis, distance in zip(directions, axes, distances)
    )
    return Grid((axes[0], axes[1], axes[2]), (slices, rows, columns), threshold, scale)


class Surface:
    """Samples a volume slice by slice, and renders its skin surface."""

    def __init__(self, volume: Grid) -> None:
        self._grid = volume
        spans = [0.0, 0.0, 0.0]
        for coordinates, axis in zip(volume.coordinates, volume.axes):
            spans[axis] = max(coordinates) - min(coordinates)
        # Whether the volume is too large to render, found before any of it
        # is sampled.
        self._large = spans[2] > LONGEST or max(spans[:2]) > WIDEST
        voxel = voxel_side(volume.coordinates)
        none = np.zeros(0, np.intp)
        # For each of the volume's axes, the index sampled at each voxel
        # along its patient axis: from superior, anterior, and the patient's
        # right.
        self._taken = tuple(
            none if self._large else sampled_indices(np.asarray(values), axis, voxel)
            for values, axis in zip(volume.coordinates, volume.axes)
        )
        # The voxel nearest each slice along the slice axis.
        self._nearest = (
            none
            if self._large
            else nearest_voxels(
                np.asarray(volume.coordinates[0]), volume.axes[0], voxel
            )
        )
        self._samples = np.full(
            tuple(len(taken) for taken in self._taken), np.nan, np.float32
        )
        self._added = 0
        # An RT Dose's greatest dose, and its smallest above 0, over every
        # pixel of every slice.
        self._peak = -math.inf
        self._floor = math.inf
        # Whether an RT Dose's scaling lost a dose of a slice (dose_values).
        self._lost = False

    def add(self, frame: np.ndarray, scale: float | None = None) -> None:
        """Add the next slice, rescaled, with padding as NaN.

        ``scale`` multiplies it in place of the grid's, as each plane of a
        series of RT Dose planes has its own Dose Grid Scaling.
        """
        index = self._added
        self._added += 1
        if self._large or index >= len(self._grid.coordinates[0]):
            return
        scale = self._grid.scale if scale is None else scale
        values = frame
        if self._grid.threshold is Threshold.DOSE:
            scaled = dose_values(frame, scale)
            if scaled is None:
                self._lost = True
                return
            values = scaled
            finite = values[np.isfinite(values)]
            if finite.size:
                self._peak = max(self._peak, float(finite.max()))
            positive = finite[finite > 0]
            if positive.size:
                self._floor = min(self._floor, float(positive.min()))
        elif scale != 1.0:
            values = frame * np.float32(scale)
        wanted = np.union1d(
            np.flatnonzero(self._taken[0] == index), self._nearest[index]
        )
        # fmax keeps a voxel's highest slice, and ignores NaN, which is
        # padding or a voxel not yet sampled, unless every value is.
        self._samples[wanted] = np.fmax(
            self._samples[wanted], values[np.ix_(self._taken[1], self._taken[2])]
        )

    def mask(self, level: float | None = None) -> np.ndarray | None:
        """The voxels in the surface, or None if a slice is missing, if an
        RT Dose's scaling lost a dose (:func:`dose_values`), or if the volume
        is too large to render.

        Indexed from superior, from anterior, then from the patient's right.
        For an RT Dose, the voxels at or above ``level``, or of any dose
        above 0 where it is 0 or not given.
        """
        if self._added != len(self._grid.coordinates[0]) or self._lost or self._large:
            return None
        samples = self._samples
        # NaN, padding, is below every level, and compares so.
        with np.errstate(invalid="ignore"):
            if self._grid.threshold is Threshold.DOSE:
                inside = samples >= level if level else samples > 0
            else:
                level = self._level()
                if level is None:
                    inside = np.zeros(samples.shape, bool)
                else:
                    inside = samples >= level
        return np.transpose(inside, [self._grid.axes.index(axis) for axis in (2, 1, 0)])

    @property
    def large(self) -> bool:
        """Whether the volume is too large to render: more than
        :data:`LONGEST` millimetres in extent along z, or more than
        :data:`WIDEST` along x or y."""
        return self._large

    @property
    def levels(self) -> tuple[float, ...] | None:
        """An RT Dose's :func:`dose_levels`, or None for another volume."""
        if self._grid.threshold is not Threshold.DOSE:
            return None
        return dose_levels(self._peak, self._floor)

    @property
    def sampled(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """For each of the volume's axes, the index sampled at each voxel
        along its patient axis, from superior, anterior, and the patient's
        right."""
        first, second, third = self._taken
        return first, second, third

    def image(self) -> np.ndarray | None:
        """The views side by side, as 8-bit grey, or None if a slice is
        missing, if an RT Dose's scaling lost a dose, or if the volume is
        too large to render.

        An RT Dose's has a row of views for each of its levels, from the
        support down, each followed by the rows of :func:`hidden_rows`; the
        rows of a level are separated by black rows, and each level's from
        the next by grey rows of :data:`LEVEL_RULE`. It is None where it
        would have more than :data:`MAXIMUM_DOSE_LEVELS` levels, before any
        is drawn, or would be taller than :data:`MAXIMUM_DOSE_SHEET_PIXELS`.
        """
        levels = self.levels
        if levels is None:
            inside = self.mask()
            return None if inside is None else side_by_side(views(inside))
        return level_sheet(self.mask, levels)

    def _level(self) -> float | None:
        if self._grid.threshold is Threshold.CT:
            return CT_THRESHOLD
        return _otsu(self._samples, padding=True)


def dose_levels(peak: float, floor: float) -> tuple[float, ...]:
    """Return the levels at which an RT Dose is shown, ascending.

    0, its support, of any dose above 0; then each fraction of ``peak`` of
    :data:`DOSE_STEPS` in each decade, from :data:`DOSE_TOP` down, whose
    dose is above ``floor``, so that the lowest is within a factor of 2.5
    of it. Only the support where ``peak`` is not above 0 and finite, as for
    a grid of no dose.

    Parameters
    ----------
    peak : float
        The greatest dose.
    floor : float
        The smallest dose above 0.
    """
    if not (math.isfinite(peak) and peak > 0):
        return (0.0,)
    levels: list[float] = []
    decade = DOSE_TOP / DOSE_STEPS[0]
    while True:
        for step in DOSE_STEPS:
            level = step * decade * peak
            # The level falls by at least half a step, so this ends.
            if not level > floor:
                return (0.0, *reversed(levels))
            levels.append(level)
        decade /= 10


def level_sheet(
    mask: Callable[[float], np.ndarray | None],
    levels: Sequence[float],
    tallest: int | None = None,
) -> np.ndarray | None:
    """Return a row of views at each of ``levels``, as 8-bit grey, as an RT
    Dose's sheet lays them out.

    Each level's row is followed by the rows of :func:`hidden_rows`; the
    rows of a level are separated by black rows, and each level's from the
    next by grey rows of :data:`LEVEL_RULE`.

    Parameters
    ----------
    mask : callable
        Given a level, the voxels at or above it, or of any value above 0
        where it is 0, indexed as :meth:`Surface.mask` gives them, or None
        where they cannot be found.
    levels : sequence of float
        Ascending, as :func:`dose_levels` gives them.
    tallest : int, optional
        The most pixels that the sheet may be tall; by default
        :data:`MAXIMUM_DOSE_SHEET_PIXELS`.

    Returns
    -------
    numpy.ndarray or None
        None where there are more than :data:`MAXIMUM_DOSE_LEVELS` levels,
        before any is drawn, where ``mask`` gives None, or where the sheet
        would be taller than ``tallest``, which is drawn only until it is.
    """
    if len(levels) > MAXIMUM_DOSE_LEVELS:
        return None
    if tallest is None:
        tallest = MAXIMUM_DOSE_SHEET_PIXELS
    height = -_GAP_PIXELS
    rows = []
    # Each level's rows, after the first level's, start a new group.
    starts = set()
    for index, level in enumerate(levels):
        inside = mask(level)
        if inside is None:
            return None
        # Each level has a row at least, so a sheet that cannot fit is
        # refused before the rest is drawn, and so is a level's hidden
        # rows that would not fit in what the levels below leave.
        rest = (len(levels) - index) * (inside.shape[0] + _GAP_PIXELS)
        if height + rest > tallest:
            return None
        hidden = hidden_rows(inside, tallest - height - rest)
        if hidden is None:
            return None
        if rows:
            starts.add(len(rows))
        # A sheet now too tall is refused by the next level's bound, before
        # it is drawn, or after the last level.
        for row in (side_by_side(views(inside)), *hidden):
            rows.append(row)
            height += row.shape[0] + _GAP_PIXELS
    gap = np.zeros((_GAP_PIXELS, rows[0].shape[1]), np.uint8)
    rule = np.full(gap.shape, LEVEL_RULE, np.uint8)
    parts = [
        part
        for index, row in enumerate(rows)
        for part in (rule if index in starts else gap, row)
    ]
    return None if height > tallest else np.concatenate(parts[1:])


def dose_values(frame: np.ndarray, scale: float) -> np.ndarray | None:
    """Return an RT Dose slice's doses as float32, or None if scaling loses one.

    Each stored value is multiplied by ``scale``, its Dose Grid Scaling, in
    float64, then held in float32 as a surface samples it. A scaling far
    from 1 can take a stored value above 0 to 0, or below a normal float32,
    where doses run together, or take a finite one to infinity; no level
    would then show what that stored value held, so the slice is refused,
    and its grid held, rather than shown without it.
    """
    stored = np.asarray(frame, np.float64)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        values = (stored * scale).astype(np.float32)
    finite = np.isfinite(stored)
    positive = finite & (stored > 0)
    if (
        not np.isfinite(values[finite]).all()
        or not (values[positive] >= np.finfo(np.float32).tiny).all()
    ):
        return None
    return values


def hidden_rows(inside: np.ndarray, room: int | None = None) -> list[np.ndarray] | None:
    """Return the rows of views that show the surfaces of ``inside`` that
    its first surfaces hide, each as 8-bit grey; none where it hides none.
    None, before any is drawn, where its rows of crossings, each with the
    gap above it, would take more than ``room`` pixels.

    The rays of the frontal view, the view from behind, and the profiles
    look along axes of the voxels, and so meet every voxel of the surface;
    where one crosses the surface more than twice, the region hides some of
    its surface behind its own, as a lower dose enclosed by a higher one is
    hidden behind it. The rows are then, as a contour sheet draws an ROI that
    hides its own surface, one of its cavities, the voxels that each slice
    encloses but does not hold, as a region of their own, where it has any;
    and one for each further crossing, in which each ray shows the surface
    where it crosses it, into or out of the region, that many times from
    the viewer, so that every surface that those rays cross is shown. One
    surface may be shown in parts across those rows, where rays cross
    different numbers of surfaces before it, so they are read together. The
    oblique views are black in those rows, since their rays, which step
    between voxels, cross a surface falsely where they graze it. The rows
    of crossings are counted (:func:`most_crossings`) before any is drawn,
    so that, within a sheet's height bound, the crossings found are at
    most about 32,768 by 711 for each of four views, as 16-bit integers,
    some 190 MB, however intricate the region.

    ``inside`` is indexed from superior, from anterior, and from the
    patient's right, as :meth:`Surface.mask` gives it.
    """
    most = max(most_crossings(inside, axis) for axis in (1, 2))
    if most <= 2:
        return []
    if room is not None and (most - 1) * (len(inside) + _GAP_PIXELS) > room:
        return None
    rows = []
    # Each slice's cavities: what its region encloses, but does not hold.
    within = np.zeros((3, 3, 3), bool)
    within[1] = [[False, True, False], [True, True, True], [False, True, False]]
    cavities = scipy.ndimage.binary_fill_holes(inside, within) & ~inside
    if cavities.any():
        rows.append(side_by_side(views(cavities)))
    along = dict(zip(_ALONG, view_crossings(inside, _ALONG)))
    none = np.full(along[0].shape[1:], -1)
    for crossing in range(1, max(len(each) for each in along.values())):
        depths = []
        for view in VIEWS:
            each = along.get(view)
            depths.append(
                none if each is None or crossing >= len(each) else each[crossing]
            )
        rows.append(side_by_side([shaded(each) for each in depths]))
    return rows


def most_crossings(inside: np.ndarray, axis: int) -> int:
    """The most times that a line of voxels along an axis within a slice
    crosses in or out of the region, found a few slices at a time.

    For axis 1, from anterior, it is the most crossings of any ray of the
    frontal view or the view from behind, and for axis 2, from the
    patient's right, of either profile.
    """
    padding = [(0, 0)] * inside.ndim
    padding[axis] = (1, 1)
    return max(
        int(np.diff(np.pad(part, padding), axis=axis).sum(axis=axis).max(initial=0))
        for part in _slice_runs(inside)
    )


def level_bands(values: np.ndarray, levels: Sequence[float]) -> np.ndarray:
    """Return an RT Dose plane as 8-bit grey by the levels its dose reaches.

    Each pixel is ``255 * k / len(levels)``, rounded, where ``k`` levels of
    ``levels``, as :func:`dose_levels` gives them, are at or below its dose,
    the support counting where its dose is above 0; padding, NaN, is black.
    So each level's outline is an edge between two greys.
    """
    finite = np.nan_to_num(values, nan=-np.inf)
    reached = (finite > 0).astype(np.intp)
    for level in levels[1:]:
        reached += finite >= level
    return np.rint(reached * (255.0 / len(levels))).astype(np.uint8)


def views(inside: np.ndarray) -> list[np.ndarray]:
    """Render voxels from each direction of :data:`VIEWS`, as the module
    describes, each as 8-bit grey.

    ``inside`` is indexed from superior, from anterior, and from the
    patient's right, as :meth:`Surface.mask` gives it.
    """
    return [shaded(depths) for depths in view_depths(inside)]


def view_depths(inside: np.ndarray) -> list[np.ndarray]:
    """For each direction of :data:`VIEWS`, the depth along each ray of the
    first voxel in ``inside``, or -1 where a ray meets none.

    Each is indexed from superior, and across from the viewer's left, as
    the tiles of :func:`views` are. Each slice's rays are stepped alone, so
    the slices are rendered a few at a time.
    """
    parts = [[_depths(part, view) for view in VIEWS] for part in _slice_runs(inside)]
    return [np.concatenate(each) for each in zip(*parts)]


def view_crossings(
    inside: np.ndarray, directions: Sequence[float] = VIEWS
) -> list[np.ndarray]:
    """For each of ``directions``, by default :data:`VIEWS`, the depth along
    each ray of each voxel at which it crosses the surface, entering or
    leaving it, in order from the viewer.

    Each is of shape (crossings, rows, across), indexed from superior, and
    across from the viewer's left, as the tiles of :func:`views` are, with
    -1 where a ray crosses the surface fewer times; its first crossings are
    :func:`view_depths`. A crossing into the surface is at the first voxel
    in it, and one out of it at the last. They are 16-bit integers, since
    no ray is 32,768 voxels long, found a few slices at a time.
    """
    parts = [
        [_crossings(part, view) for view in directions] for part in _slice_runs(inside)
    ]
    found = []
    for each in zip(*parts):
        most = max(len(part) for part in each)
        padded = [
            np.pad(part, ((0, most - len(part)), (0, 0), (0, 0)), constant_values=-1)
            for part in each
        ]
        found.append(np.concatenate(padded, axis=1))
    return found


def side_by_side(tiles: Sequence[np.ndarray]) -> np.ndarray:
    """Lay the tiles of one height out from left to right, each separated
    from the next by black columns."""
    gap = np.zeros((tiles[0].shape[0], _GAP_PIXELS, *tiles[0].shape[2:]), np.uint8)
    parts = [part for tile in tiles for part in (gap, tile)][1:]
    return np.concatenate(parts, axis=1)


def voxel_side(
    coordinates: Sequence[Sequence[float]],
    minimum: float = MINIMUM_VOXEL,
    maximum_voxels: int | None = None,
) -> float:
    """The side of a cubic voxel, in millimetres, to sample a volume to.

    ``minimum``, or the volume's smallest spacing where that is larger,
    enlarged where needed to keep each axis within ``maximum_voxels``
    voxels, if given. ``coordinates`` are a :class:`Grid`'s.
    """
    spacings = [
        float(np.abs(np.diff(values)).min())
        for values in coordinates
        if len(values) > 1
    ]
    voxel = max(minimum, min(spacings, default=minimum))
    if maximum_voxels is None:
        return voxel
    extent = max(max(values) - min(values) for values in coordinates)
    return max(voxel, extent / (maximum_voxels - 1))


def sampled_indices(coordinates: np.ndarray, axis: int, voxel: float) -> np.ndarray:
    """The index nearest each voxel along one axis, from superior, anterior,
    and the patient's right, which have the highest z and the lowest x and y.

    The voxels are ``voxel`` millimetres apart, from the highest coordinate
    along z and from the lowest along x and y.
    """
    wanted = _voxel_coordinates(coordinates, axis, voxel)
    if len(coordinates) == 1:
        return np.zeros(len(wanted), np.intp)
    order = np.argsort(coordinates, kind="stable")
    ascending = coordinates[order]
    right = np.clip(np.searchsorted(ascending, wanted), 1, len(ascending) - 1)
    left = right - 1
    closer_left = (wanted - ascending[left]) <= (ascending[right] - wanted)
    return order[np.where(closer_left, left, right)]


def nearest_voxels(coordinates: np.ndarray, axis: int, voxel: float) -> np.ndarray:
    """The index of the voxel nearest each coordinate along one axis, the
    voxels being those of :func:`sampled_indices`."""
    wanted = _voxel_coordinates(coordinates, axis, voxel)
    return np.abs(coordinates[:, np.newaxis] - wanted[np.newaxis, :]).argmin(axis=1)


def _voxel_coordinates(coordinates: np.ndarray, axis: int, voxel: float) -> np.ndarray:
    """The coordinate of each voxel along one axis, ``voxel`` millimetres
    apart, from the highest coordinate along z and from the lowest along x
    and y."""
    low, high = float(coordinates.min()), float(coordinates.max())
    # The end is kept, though the division may fall a little short of it.
    count = math.floor((high - low) / voxel + 1e-6) + 1
    return (
        high - np.arange(count) * voxel if axis == 2 else low + np.arange(count) * voxel
    )


def _otsu(values: np.ndarray, padding: bool = False) -> float | None:
    """Otsu's threshold of the finite values, or None if they are all one value.

    The values are put in :data:`_OTSU_BINS` bins from the lowest to the
    highest. The threshold is the lower edge of the first bin of the upper
    class, where the split into two classes maximises the variance between
    them; the first such split where several do.

    With ``padding``, NaN values are pixel padding, which marks where there
    is no patient, and count as a bin of their own just below the lowest
    finite value, with the background. A padded volume whose other values
    are all one then has the threshold of that value, so its padding still
    outlines it. Where padding is the only background and the patient's
    values vary, the threshold can still fall among them.

    The values are counted a few million at a time, each bin by value
    alone, so the counts are those of all of them at once.
    """
    flat = values.reshape(-1)
    parts = [
        flat[start : start + _OTSU_PART] for start in range(0, flat.size, _OTSU_PART)
    ]
    low, high, padded = math.inf, -math.inf, 0
    for part in parts:
        finite = part[np.isfinite(part)]
        if finite.size:
            low = min(low, float(finite.min()))
            high = max(high, float(finite.max()))
        if padding:
            padded += int(np.isnan(part).sum())
    if low > high:
        return None
    if high <= low:
        return low if padded else None
    counts = np.zeros(_OTSU_BINS, np.int64)
    for part in parts:
        finite = part[np.isfinite(part)].astype(np.float64)
        counts += np.histogram(finite, bins=_OTSU_BINS, range=(low, high))[0]
    edges = np.histogram_bin_edges(np.zeros(0), bins=_OTSU_BINS, range=(low, high))
    centres = (edges[:-1] + edges[1:]) / 2
    if padded:
        # In float64, a bin's width below a float32 value stays distinct from it.
        below_low = low - (edges[1] - edges[0])
        counts = np.concatenate([[padded], counts])
        centres = np.concatenate([[below_low], centres])
        edges = np.concatenate([[below_low], edges])
    below = np.cumsum(counts)[:-1].astype(np.float64)
    above = counts.sum() - below
    sums = np.cumsum(counts * centres)
    below_mean = np.divide(sums[:-1], below, out=np.zeros_like(below), where=below > 0)
    above_mean = np.divide(
        sums[-1] - sums[:-1], above, out=np.zeros_like(above), where=above > 0
    )
    between = below * above * (below_mean - above_mean) ** 2
    return float(edges[int(np.argmax(between)) + 1])


def _depths(inside: np.ndarray, view: float) -> np.ndarray:
    """For each ray of a view, the depth of the first voxel in the surface.

    ``inside`` is indexed from superior, from anterior, and from the
    patient's right. The result is indexed from superior, and across from
    the viewer's left, with -1 where a ray meets no voxel.
    """
    rays = _rays(inside, view)
    met = rays.any(axis=1)
    return np.where(met, rays.argmax(axis=1), -1)


def _crossings(inside: np.ndarray, view: float) -> np.ndarray:
    """For each ray of a view, the depth of each voxel at which it crosses
    the surface, as :func:`view_crossings` gives them."""
    rays = _rays(inside, view)
    rows, steps, across = rays.shape
    # Each ray's voxels in order, so that its crossings are found in order,
    # and one beyond its end, so that a ray that ends in the surface leaves it.
    along = np.zeros((rows, across, steps + 1), bool)
    along[..., :steps] = np.moveaxis(rays, 1, 2)
    before = np.zeros_like(along)
    before[..., 1:] = along[..., :-1]
    row, column, step = np.nonzero(along != before)
    depth = np.where(along[row, column, step], step, step - 1)
    ray = row * across + column
    counts = np.bincount(ray, minlength=rows * across)
    rank = np.arange(len(ray)) - (np.cumsum(counts) - counts)[ray]
    crossings = np.full(
        (max(1, int(np.max(counts, initial=0))), rows, across), -1, np.int16
    )
    crossings[rank, row, column] = depth
    return crossings


def _slice_runs(inside: np.ndarray) -> list[np.ndarray]:
    """Runs of up to ``_SLICES_AT_A_TIME`` slices, in order, as views; one
    run where there are no slices."""
    return [
        inside[start : start + _SLICES_AT_A_TIME]
        for start in range(0, max(len(inside), 1), _SLICES_AT_A_TIME)
    ]


def _rays(inside: np.ndarray, view: float) -> np.ndarray:
    """The voxels along each ray of a view, indexed from superior, by depth
    from the viewer, and across from the viewer's left, with False beyond
    ``inside``. Rays turn about a voxel at or next to the middle, and reach
    every voxel in every view."""
    rows, deep, wide = inside.shape
    middle_y, middle_x = (deep - 1) // 2, (wide - 1) // 2
    reach = math.ceil(
        math.hypot(
            max(middle_y, deep - 1 - middle_y), max(middle_x, wide - 1 - middle_x)
        )
    )
    steps = np.arange(-reach, reach + 1, dtype=np.float64)
    angle = math.radians(view)
    # The viewer looks along (-sin, cos) in the patient's (x, y), and their
    # right is (cos, sin): (1, 0), the patient's left, in the frontal view.
    across, depth = steps[np.newaxis, :], steps[:, np.newaxis]
    x = np.rint(middle_x + across * math.cos(angle) - depth * math.sin(angle))
    y = np.rint(middle_y + across * math.sin(angle) + depth * math.cos(angle))
    outside = (x < 0) | (x >= wide) | (y < 0) | (y >= deep)
    padded = np.zeros((rows, deep + 1, wide + 1), bool)
    padded[:, :deep, :wide] = inside
    rays: np.ndarray = padded[
        :,
        np.asarray(np.where(outside, deep, y), dtype=np.intp),
        np.asarray(np.where(outside, wide, x), dtype=np.intp),
    ]
    return rays


def shaded(depths: np.ndarray) -> np.ndarray:
    """Shade each surface voxel of a view by Lambert's law, lit from the
    viewer, as 8-bit grey, from the depth along each ray, or -1 where a ray
    meets none."""
    met = depths >= 0
    depth = _smoothed(depths.astype(np.float64), met)
    down, across = _slope(depth, met, 0), _slope(depth, met, 1)
    lambert = 1.0 / np.sqrt(1.0 + down**2 + across**2)
    grey = np.rint(255 * (_AMBIENT + (1 - _AMBIENT) * lambert))
    return np.asarray(np.where(met, grey, 0), dtype=np.uint8)


def _smoothed(depth: np.ndarray, met: np.ndarray) -> np.ndarray:
    """The depths averaged over the surface around each, by :data:`_SMOOTHING`.

    Depths are whole voxels, so their slopes alone would shade a curved
    surface in terraces. Rays that meet no voxel are left out of the average.
    """
    weights = met.astype(np.float64)
    total, count = np.where(met, depth, 0.0), weights
    for axis in (0, 1):
        total, count = _blurred(total, axis), _blurred(count, axis)
    return np.divide(total, count, out=np.zeros_like(total), where=met)


def _blurred(values: np.ndarray, axis: int) -> np.ndarray:
    """Convolve along an axis with :data:`_SMOOTHING`, with zeros beyond the ends."""
    half = len(_SMOOTHING) // 2
    padding = [(0, 0), (0, 0)]
    padding[axis] = (half, half)
    padded = np.pad(values, padding)
    length = values.shape[axis]
    return sum(
        weight * np.take(padded, range(offset, offset + length), axis=axis)
        for offset, weight in enumerate(_SMOOTHING)
    )


def _slope(depth: np.ndarray, met: np.ndarray, axis: int) -> np.ndarray:
    """The slope of the depths along an axis, in voxels a voxel.

    The mean of the differences with each neighbour that is on the surface
    too, or 0 where neither is.
    """
    depth, met = np.moveaxis(depth, axis, 0), np.moveaxis(met, axis, 0)
    both = met[1:] & met[:-1]
    difference = np.where(both, depth[1:] - depth[:-1], 0.0)
    total = np.zeros(depth.shape)
    count = np.zeros(depth.shape)
    total[:-1] += difference
    total[1:] += difference
    count[:-1] += both
    count[1:] += both
    slope = np.divide(total, count, out=np.zeros_like(total), where=count > 0)
    return np.moveaxis(slope, 0, axis)
