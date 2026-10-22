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
shows. :class:`Surface` renders that surface from the five directions of
:data:`VIEWS`, so that a reviewer attesting that a set holds no recognisable
face can see one where it is. :mod:`~pymedphys._dicom.deidentify.qc_previews`
renders:

- each series that forms a volume, as it describes; and
- each RT Dose instance of two or more frames, placed by Image Position
  (Patient), Image Orientation (Patient), Pixel Spacing, and Grid Frame
  Offset Vector, whose axes lie along the patient's three directions and
  whose frames are evenly spaced.

Enhanced multi-frame images are not rendered.
:mod:`~pymedphys._dicom.deidentify.qc_contours` renders RT Structure Set
contours by :func:`views`, and by :func:`view_crossings` the surfaces
that one region hides behind its own.

The surface encloses the voxels at or above a threshold, applied after
Rescale Slope and Rescale Intercept, or after Dose Grid Scaling for RT Dose:
:data:`CT_THRESHOLD` Hounsfield units for a CT series; Otsu's threshold over
the sampled volume for any other series, such as MR or PET, with pixel
padding counted below its lowest value, since padding marks where there is
no patient; and :data:`DOSE_FRACTION` of the maximum of every voxel of the
grid for RT Dose. Pixel padding, which is NaN, lies below every threshold.

An RT Dose render is a preview of one isodose surface. Lower doses can
outline the patient where it does not, so a render that shows no face is
inconclusive: it does not show that no face can be reconstructed from the
grid.

The volume is sampled by nearest neighbour to cubic voxels of
:data:`MINIMUM_VOXEL` millimetres, or of its smallest spacing where that is
larger, enlarged where needed to keep each axis within
:data:`MAXIMUM_VOXELS` voxels. Its slices are sampled as they are decoded,
so that it is never held at full resolution. Each slice is also taken into
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
face on the viewer's left; and at -90 degrees, from the patient's right,
with the face on the viewer's right.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Sequence

from pymedphys._imports import numpy as np

# Each view's angle about the superior-inferior axis, in degrees from anterior
# towards the patient's left: frontal, the two obliques, and the two profiles.
VIEWS = (0, 45, -45, 90, -90)
CT_THRESHOLD = -300.0  # Hounsfield units, between air and soft tissue
DOSE_FRACTION = 0.05
MINIMUM_VOXEL = 2.0  # millimetres
MAXIMUM_VOXELS = 256
RT_DOSE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.2"

_OTSU_BINS = 256
# The brightness of a surface seen edge on, so that it stands out from black.
_AMBIENT = 0.2
# The binomial weights by which depths are averaged along each axis before
# shading.
_SMOOTHING = (1.0, 4.0, 6.0, 4.0, 1.0)
# Black columns between views.
_GAP_PIXELS = 4


class Threshold(enum.Enum):
    """Which threshold gives a volume's surface."""

    CT = "ct"  # CT_THRESHOLD
    OTSU = "otsu"  # Otsu's threshold over the sampled volume, padding lowest
    DOSE = "dose"  # DOSE_FRACTION of the grid's maximum


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
        voxel = voxel_side(volume.coordinates)
        # For each of the volume's axes, the index sampled at each voxel
        # along its patient axis: from superior, anterior, and the patient's
        # right.
        self._taken = tuple(
            sampled_indices(np.asarray(coordinates), axis, voxel)
            for coordinates, axis in zip(volume.coordinates, volume.axes)
        )
        # The voxel nearest each slice along the slice axis.
        self._nearest = nearest_voxels(
            np.asarray(volume.coordinates[0]), volume.axes[0], voxel
        )
        self._samples = np.full(
            tuple(len(taken) for taken in self._taken), np.nan, np.float32
        )
        self._added = 0
        self._peak = -math.inf

    def add(self, frame: np.ndarray) -> None:
        """Add the next slice, rescaled, with padding as NaN."""
        index = self._added
        self._added += 1
        if index >= len(self._grid.coordinates[0]):
            return
        values = frame
        if self._grid.scale != 1.0:
            values = frame * np.float32(self._grid.scale)
        if self._grid.threshold is Threshold.DOSE:
            finite = values[np.isfinite(values)]
            if finite.size:
                self._peak = max(self._peak, float(finite.max()))
        wanted = np.union1d(
            np.flatnonzero(self._taken[0] == index), self._nearest[index]
        )
        # fmax keeps a voxel's highest slice, and ignores NaN, which is
        # padding or a voxel not yet sampled, unless every value is.
        self._samples[wanted] = np.fmax(
            self._samples[wanted], values[np.ix_(self._taken[1], self._taken[2])]
        )

    def mask(self) -> np.ndarray | None:
        """The voxels in the surface, or None if a slice is missing.

        Indexed from superior, from anterior, then from the patient's right.
        """
        if self._added != len(self._grid.coordinates[0]):
            return None
        level = self._level()
        if level is None:
            inside = np.zeros(self._samples.shape, bool)
        else:
            inside = np.nan_to_num(self._samples, nan=-np.inf) >= level
        return np.transpose(inside, [self._grid.axes.index(axis) for axis in (2, 1, 0)])

    @property
    def sampled(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """For each of the volume's axes, the index sampled at each voxel
        along its patient axis, from superior, anterior, and the patient's
        right."""
        first, second, third = self._taken
        return first, second, third

    def image(self) -> np.ndarray | None:
        """The views side by side, as 8-bit grey, or None if a slice is missing."""
        inside = self.mask()
        if inside is None:
            return None
        return side_by_side(views(inside))

    def _level(self) -> float | None:
        threshold = self._grid.threshold
        if threshold is Threshold.CT:
            return CT_THRESHOLD
        if threshold is Threshold.DOSE:
            return DOSE_FRACTION * self._peak if self._peak > 0 else None
        return _otsu(self._samples, padding=True)


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
    the tiles of :func:`views` are.
    """
    return [_depths(inside, view) for view in VIEWS]


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
    in it, and one out of it at the last.
    """
    return [_crossings(inside, view) for view in directions]


def side_by_side(tiles: Sequence[np.ndarray]) -> np.ndarray:
    """Lay the tiles of one height out from left to right, each separated
    from the next by black columns."""
    gap = np.zeros((tiles[0].shape[0], _GAP_PIXELS, *tiles[0].shape[2:]), np.uint8)
    parts = [part for tile in tiles for part in (gap, tile)][1:]
    return np.concatenate(parts, axis=1)


def voxel_side(
    coordinates: Sequence[Sequence[float]],
    minimum: float = MINIMUM_VOXEL,
    maximum_voxels: int = MAXIMUM_VOXELS,
) -> float:
    """The side of a cubic voxel, in millimetres, to sample a volume to.

    ``minimum``, or the volume's smallest spacing where that is larger,
    enlarged where needed to keep each axis within ``maximum_voxels``
    voxels. ``coordinates`` are a :class:`Grid`'s.
    """
    spacings = [
        float(np.abs(np.diff(values)).min())
        for values in coordinates
        if len(values) > 1
    ]
    voxel = max(minimum, min(spacings, default=minimum))
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
    """
    finite = values[np.isfinite(values)].astype(np.float64)
    padded = int(np.isnan(values).sum()) if padding else 0
    if finite.size == 0:
        return None
    low, high = float(finite.min()), float(finite.max())
    if high <= low:
        return low if padded else None
    counts, edges = np.histogram(finite, bins=_OTSU_BINS, range=(low, high))
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
        (max(1, int(np.max(counts, initial=0))), rows, across), -1, np.intp
    )
    crossings[rank, row, column] = depth
    return crossings


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
