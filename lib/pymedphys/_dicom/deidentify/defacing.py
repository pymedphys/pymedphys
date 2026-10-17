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

"""Where to remove the face from a head CT, found from the image alone.

The Clean Recognizable Visual Features Option (PS3.15 E.3.2) asks for
"sufficient removal or distortion of the Pixel Data ... to prevent
recognition". This module finds the region to remove, the face block, in
the patient's coordinates: every point anterior to a vertical plane
:data:`MARGIN` millimetres posterior to the centres of the two eye globes,
facing the way the eyes face, and superior to an axial plane at the lower
of the globes' inferior edges, lowered by a voxel or by the spacing of the
slices there, whichever is larger, for the sampling. It reaches the edges of the field of
view, so that an immobilisation mask or anything else resting on the face
is inside it. It keeps the nose below the eyes, the mouth, and the jaw,
which most head and neck targets and organs at risk need. Nothing here
changes pixel data.

The block follows the region of defaceRT (O'Sullivan-Steben, Galarneau, and
Kildea, Med Phys 2025;52:e70160; MIT licence), which removes everything
anterior to the eyes from eye level up, but this module reads no ROI names
and no image layout: it finds the globes in the image, and places the block
by Image Position (Patient) and Image Orientation (Patient), so that a
feet-first, prone, or sagittal acquisition gives the same block as a
head-first supine axial one. The plane is turned with the head: it is
perpendicular to the line between the globes' centres, so a head turned
within its mask by up to :data:`MAXIMUM_TURN` degrees is still cut behind
both eyes.

:class:`FaceFinder` takes a volume whose slices lie along the patient's
axes, each slice's rows and columns along two of them and the slices
stacked along the third, within :data:`ALIGNMENT_TOLERANCE` and
:data:`STACKING_TOLERANCE`; it refuses any other, such as one with a gantry
tilt, rather than place a block that the tilt would shift. It samples the
volume slice by slice, in Hounsfield units, to cubic voxels along the
patient's axes, as
:class:`~pymedphys._dicom.deidentify.qc_surfaces.Surface` does, of
:data:`MINIMUM_VOXEL` millimetres or more. It then:

1. averages each voxel with its neighbours, and marks the soft tissue, at
   :data:`SOFT_TISSUE` Hounsfield units, which includes the vitreous and
   the lens and excludes the orbital fat around the globe and bone;
2. finds each ball of soft tissue whose centre is as far from other
   tissue as anywhere near it, of a diameter within :data:`GLOBE_DIAMETER`,
   give or take a voxel at each end for the sampling, the largest first,
   and keeps those with at least half of a sphere around them, and most of
   one half of it, outside the soft tissue, in fat, air, or bone, as each
   globe has the orbital fat behind and beside it, whatever touches its
   front;
3. pairs two such balls that lie side by side: their centres
   :data:`GLOBE_SEPARATION` millimetres apart across the axial plane, at
   heights within :data:`PAIR_TOLERANCE` millimetres, and the line between
   them within :data:`MAXIMUM_TURN` degrees of the patient's left-right
   axis, each with bone, at :data:`BONE` Hounsfield units or more, lateral
   to it and superior to it within :data:`ORBIT_REACH` millimetres, as the
   bony orbit is;
4. checks that the head lies behind the eyes: that, at the eyes' height and
   between them, tissue fills at least :data:`HEAD_BEHIND` more of the
   region from :data:`CHECKED_DEPTH` millimetres behind the globes' centres
   than of the region as far in front, so that a patient position entered
   wrongly, which would turn the block onto the back of the head, is
   refused; and
5. checks that the cranium lies above the eyes: that bone encloses more of
   the axial slices from :data:`CRANIUM_DEPTH` millimetres above the
   globes' centres, where it encloses the brain, than of those as far
   below, so that a head recorded upside down, which would turn the block
   onto the nose and mouth and keep the forehead, is refused, as is a
   volume that shows no cranium above the eyes.

Exactly one such pair gives the block. No pair, as where the volume does
not include both eyes, more than one, or a head that does not lie behind
them or below its cranium, refuses with a :class:`FaceBlockProblem`, so
that the caller holds the volume or leaves it to review rather than guess.
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import itertools
import math
from collections.abc import Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from . import qc_surfaces

MINIMUM_VOXEL = 1.5  # millimetres
MAXIMUM_VOXELS = 512
ALIGNMENT_TOLERANCE = 1e-4  # of a direction cosine off its patient axis
STACKING_TOLERANCE = 0.01  # millimetres of a slice's offset within the plane
SOFT_TISSUE = (-40.0, 160.0)  # Hounsfield units
BODY = -500.0  # Hounsfield units
BONE = 300.0  # Hounsfield units
GLOBE_DIAMETER = (16.0, 30.0)  # millimetres, from an infant's to a large adult's
# Millimetres, between the centres: a young child's eyes may be closer, and
# are then not found.
GLOBE_SEPARATION = (40.0, 80.0)
PAIR_TOLERANCE = 10.0  # millimetres
MAXIMUM_TURN = 30.0  # degrees
ORBIT_REACH = 15.0  # millimetres beyond the globe
MARGIN = 5.0  # millimetres posterior to the globes' centres
CHECKED_DEPTH = (20.0, 60.0)  # millimetres from the globes' centres
HEAD_BEHIND = 0.4  # of the checked region filled by tissue
CRANIUM_DEPTH = (30.0, 70.0)  # millimetres above and below the globes' centres

# The sphere, as a multiple of a ball's radius, on which at least the
# fraction _OUTSIDE of points, and _OUTSIDE_BEHIND of those on one half of it,
# must lie outside the soft tissue, and the directions in which those points
# lie: a Fibonacci sphere, the same each run.
_SHELL = 1.3
_OUTSIDE = 0.5
_OUTSIDE_BEHIND = 0.8
# How far from a ball's deepest point, as a multiple of its radius, the soft
# tissue that gives its centre reaches.
_CENTRING = 1.1
_DIRECTION_COUNT = 128
# Half the side of the square, across the ray, in which bone is looked for
# lateral and superior to a globe, in millimetres.
_ORBIT_HALF_WIDTH = 6.0
# Half the height of the region checked for tissue behind and in front of
# the eyes, in millimetres; it is as wide as the globes are apart.
_CHECKED_HALF_HEIGHT = 10.0


class FaceBlockProblem(enum.Enum):
    """Why no face block was found."""

    NOT_ALONG_PATIENT_AXES = "not-along-patient-axes"  # as with a gantry tilt
    NO_EYES = "no-eyes"  # no pair of eye globes, as when an eye is out of view
    AMBIGUOUS_EYES = "ambiguous-eyes"  # more than one pair
    HEAD_NOT_BEHIND_EYES = "head-not-behind-eyes"  # as for a wrong position
    CRANIUM_NOT_ABOVE_EYES = "cranium-not-above-eyes"  # as for a head upside down


class FaceBlockRefused(Exception):
    """No face block was found, for :attr:`problem`."""

    def __init__(self, problem: FaceBlockProblem) -> None:
        super().__init__(problem.value)
        self.problem = problem


@dataclasses.dataclass(frozen=True)
class FaceBlock:
    """The region of a head to remove, in the patient's coordinates.

    Attributes
    ----------
    origin : tuple of float
        The x, y, and z of a point on the block's vertical plane, in
        millimetres.
    anterior : tuple of float
        The x, y, and z of the unit normal of that plane, horizontal, which
        points the way the eyes face: the block holds the points on that
        side.
    inferior_limit : float
        The z coordinate of the block's axial plane, in millimetres: the
        block holds the points of higher z, which are superior to it.
    globes : tuple of tuple of float
        The x, y, and z of each globe's centre, in millimetres, the
        patient's right first.
    """

    origin: tuple[float, float, float]
    anterior: tuple[float, float, float]
    inferior_limit: float
    globes: tuple[tuple[float, float, float], tuple[float, float, float]]

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Whether each point is in the block.

        Parameters
        ----------
        points : numpy.ndarray
            The x, y, and z of each point along the last axis, in
            millimetres.

        Returns
        -------
        numpy.ndarray
            Of bool, with the shape of ``points`` without its last axis.
        """
        points = np.asarray(points, dtype=float)
        ahead = (points - np.array(self.origin)) @ np.array(self.anterior)
        return (ahead > 0) & (points[..., 2] > self.inferior_limit)

    def slice_mask(
        self,
        position: Sequence[float],
        orientation: Sequence[float],
        spacing: Sequence[float],
        shape: tuple[int, int],
    ) -> np.ndarray:
        """Which pixels of a slice have their centres in the block.

        The slice may lie in any plane: each pixel is placed by the slice's
        own Image Position (Patient) and direction cosines.

        Parameters
        ----------
        position : sequence of float
            Image Position (Patient): the centre of the first pixel.
        orientation : sequence of float
            Image Orientation (Patient): the direction along a row, of
            increasing column index, then down a column, of increasing row
            index.
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
        origin = np.asarray(position, dtype=float)
        along_row = np.asarray(orientation[:3], dtype=float)
        down_column = np.asarray(orientation[3:], dtype=float)
        rows = np.arange(shape[0], dtype=float)[:, None, None] * float(spacing[0])
        columns = np.arange(shape[1], dtype=float)[None, :, None] * float(spacing[1])
        points = origin + columns * along_row + rows * down_column
        return self.contains(points)


@dataclasses.dataclass(frozen=True)
class _Region:
    """A region that may be a globe, in the sampled volume."""

    centre: np.ndarray  # x, y, and z, in millimetres
    radius: float  # millimetres: the ball's depth, and a voxel for the sampling


class FaceFinder:
    """Samples a CT volume slice by slice, and finds its face block."""

    def __init__(
        self,
        orientation: Sequence[float],
        positions: Sequence[Sequence[float]],
        spacing: Sequence[float],
        shape: tuple[int, int],
    ) -> None:
        """
        Parameters
        ----------
        orientation : sequence of float
            Image Orientation (Patient), shared by every slice.
        positions : sequence of sequence of float
            Image Position (Patient) of each slice, in the order in which
            the slices are added, which need not be their order along the
            stack.
        spacing : sequence of float
            Pixel Spacing, shared by every slice: between rows, then between
            columns, in millimetres.
        shape : tuple of int
            Rows, then columns, shared by every slice.

        Raises
        ------
        ValueError
            If there are no positions, or ``orientation`` does not hold six
            values or each position three.
        FaceBlockRefused
            With :attr:`FaceBlockProblem.NOT_ALONG_PATIENT_AXES` unless the
            rows and the columns each lie along a patient axis, with unit
            direction cosines, and the slices are stacked along the third,
            with no two at one position.
        """
        if len(orientation) != 6:
            raise ValueError("Image Orientation (Patient) holds six values")
        origins = np.asarray(positions, dtype=float)
        if origins.ndim != 2 or origins.shape[1] != 3 or not len(origins):
            raise ValueError("a face block needs a position of three values per slice")
        along_row = np.asarray(orientation[:3], dtype=float)
        down_column = np.asarray(orientation[3:], dtype=float)
        normal = np.cross(along_row, down_column)
        offsets = origins @ normal
        in_plane = (origins - origins[0]) - np.outer(offsets - offsets[0], normal)
        directions = (normal, down_column, along_row)
        axes = {int(np.argmax(np.abs(direction))) for direction in directions}
        if (
            len(axes) != 3
            or any(
                np.delete(np.abs(direction), np.argmax(np.abs(direction))).max()
                > ALIGNMENT_TOLERANCE
                for direction in directions
            )
            or any(
                abs(float(np.linalg.norm(direction)) - 1) > ALIGNMENT_TOLERANCE
                for direction in (along_row, down_column)
            )
            or np.abs(in_plane).max() > STACKING_TOLERANCE
            or len(np.unique(np.round(offsets, 6))) != len(offsets)
        ):
            raise FaceBlockRefused(FaceBlockProblem.NOT_ALONG_PATIENT_AXES)
        self._grid = qc_surfaces.grid(
            directions,
            [float(offset) for offset in offsets],
            (float(spacing[0]), float(spacing[1])),
            shape,
            qc_surfaces.Threshold.CT,
        )
        self._shape = (int(shape[0]), int(shape[1]))
        # Sorted, since the slices may be added in any order.
        self._voxel = qc_surfaces.voxel_side(
            [sorted(coordinates) for coordinates in self._grid.coordinates],
            MINIMUM_VOXEL,
            MAXIMUM_VOXELS,
        )
        # As in qc_surfaces.Surface: for each of the volume's axes, the index
        # sampled at each voxel along its patient axis.
        self._taken = tuple(
            qc_surfaces.sampled_indices(np.asarray(coordinates), axis, self._voxel)
            for coordinates, axis in zip(self._grid.coordinates, self._grid.axes)
        )
        self._samples = np.full(
            tuple(len(taken) for taken in self._taken), np.nan, np.float32
        )
        self._added = 0
        # A grid's row and column coordinates run from the first pixel, and
        # its slice coordinates from the patient's origin.
        shifts = (0.0, origins[0][self._grid.axes[1]], origins[0][self._grid.axes[2]])
        vertical = self._grid.axes.index(2)
        # The z of each slice, row, or column along the patient's superior
        # axis, from inferior up.
        self._heights = np.sort(
            np.asarray(self._grid.coordinates[vertical]) + float(shifts[vertical])
        )
        lowest, highest = {}, {}
        for coordinates, axis, shift in zip(
            self._grid.coordinates, self._grid.axes, shifts
        ):
            lowest[axis] = min(coordinates) + float(shift)
            highest[axis] = max(coordinates) + float(shift)
        # The x, y, and z of the sampled voxel at index 0 along each patient
        # axis: the patient's right, anterior, and superior.
        self._first = np.array([lowest[0], lowest[1], highest[2]], dtype=float)

    def add(self, frame: np.ndarray) -> None:
        """Add the next slice, in Hounsfield units, with padding as NaN.

        Raises
        ------
        ValueError
            If every slice has been added, or ``frame`` is not of the
            volume's rows and columns.
        """
        index = self._added
        if index >= len(self._grid.coordinates[0]):
            raise ValueError("every slice of the volume has been added")
        frame = np.asarray(frame, dtype=np.float32)
        if frame.shape != self._shape:
            raise ValueError("a slice must have the volume's rows and columns")
        self._added += 1
        wanted = np.flatnonzero(self._taken[0] == index)
        if wanted.size:
            self._samples[wanted] = frame[np.ix_(self._taken[1], self._taken[2])]

    def block(self) -> FaceBlock:
        """The volume's face block.

        Raises
        ------
        ValueError
            If a slice has not been added.
        FaceBlockRefused
            If the volume has no one pair of eye globes, or the head does
            not lie behind them, or its cranium above them.
        """
        if self._added != len(self._grid.coordinates[0]):
            raise ValueError("a face block needs every slice of the volume")
        # Indexed from superior, from anterior, then from the patient's right.
        values = np.transpose(
            self._samples, [self._grid.axes.index(axis) for axis in (2, 1, 0)]
        )
        values = scipy.ndimage.uniform_filter(
            np.nan_to_num(values, nan=-1000.0), size=3, mode="nearest"
        )
        bone = values >= BONE
        pairs = [
            (right, left)
            for first, second in itertools.combinations(self._regions(values), 2)
            for right, left in [sorted((first, second), key=lambda r: r.centre[0])]
            if _paired(right, left)
            and self._in_orbit(bone, right, -1)
            and self._in_orbit(bone, left, 1)
        ]
        if not pairs:
            raise FaceBlockRefused(FaceBlockProblem.NO_EYES)
        if len(pairs) > 1:
            raise FaceBlockRefused(FaceBlockProblem.AMBIGUOUS_EYES)
        right, left = pairs[0]
        across = left.centre - right.centre
        # Horizontal and perpendicular to the line between the globes, on
        # the side of lower y, which the patient's coordinates call anterior.
        anterior = np.array([across[1], -across[0], 0.0])
        anterior /= np.linalg.norm(anterior)
        middle = (right.centre + left.centre) / 2
        if not self._head_behind(values >= BODY, middle, anterior, across):
            raise FaceBlockRefused(FaceBlockProblem.HEAD_NOT_BEHIND_EYES)
        if not self._cranium_above(bone, middle):
            raise FaceBlockRefused(FaceBlockProblem.CRANIUM_NOT_ABOVE_EYES)
        # Lower by a voxel, or by the volume's spacing along the patient's
        # superior axis about the globes where that is larger, for the
        # sampling.
        edges = [
            (globe.centre[2] - globe.radius, globe.centre[2] + globe.radius)
            for globe in (right, left)
        ]
        inferior = min(low for low, _ in edges) - max(
            self._voxel,
            _spacing_over(
                self._heights,
                min(low for low, _ in edges),
                max(high for _, high in edges),
            ),
        )
        return FaceBlock(
            _point(middle - MARGIN * anterior),
            _point(anterior),
            float(inferior),
            (_point(right.centre), _point(left.centre)),
        )

    def _regions(self, values: np.ndarray) -> list[_Region]:
        """The balls of soft tissue, mostly bordered by other tissue or air,
        that may be globes, as the module describes."""
        soft = (values >= SOFT_TISSUE[0]) & (values <= SOFT_TISSUE[1])
        depth = scipy.ndimage.distance_transform_edt(soft) * self._voxel
        # A ball's depth at its centre falls short of its radius by up to
        # about a voxel, from the sampling and the averaging, so a ball's
        # radius, taken as its depth and a voxel, runs from half the least
        # diameter to a voxel more than half the greatest.
        low, high = GLOBE_DIAMETER[0] / 2 - self._voxel, GLOBE_DIAMETER[1] / 2
        peaks = (
            (depth >= low)
            & (depth <= high)
            & (depth == scipy.ndimage.maximum_filter(depth, footprint=_ball(2.0)))
        )
        candidates = sorted(
            (
                (-float(depth[index]), index)
                for index in zip(*(axis.tolist() for axis in np.nonzero(peaks)))
            ),
        )
        regions: list[_Region] = []
        for negative, peak in candidates:
            radius = -negative + self._voxel
            if any(
                np.linalg.norm(self._position(np.array(peak, float)) - region.centre)
                < region.radius
                for region in regions
            ):
                continue
            index = self._centred(soft, np.array(peak, dtype=float), radius)
            if self._surrounded(soft, index, radius):
                regions.append(_Region(self._position(index), radius))
        return regions

    def _centred(self, soft: np.ndarray, peak: np.ndarray, radius: float) -> np.ndarray:
        """The centre of the soft tissue within :data:`_CENTRING` times a
        ball's radius of its deepest point, which may lie off its centre
        where the ball is coarsely sampled."""
        reach = _CENTRING * radius / self._voxel
        box = _box(soft.shape, *((value - reach, value + reach) for value in peak))
        offsets = np.stack(
            np.meshgrid(
                *(np.arange(part.start, part.stop) for part in box), indexing="ij"
            ),
            axis=-1,
        )
        near = soft[box] & (np.linalg.norm(offsets - peak, axis=-1) <= reach)
        return offsets[near].mean(axis=0) if near.any() else peak

    def _surrounded(self, soft: np.ndarray, index: np.ndarray, radius: float) -> bool:
        """Whether a ball of soft tissue is mostly bordered by other tissue
        or air.

        Of the points on a sphere :data:`_SHELL` times its radius, at least
        :data:`_OUTSIDE` must be outside the soft tissue, and at least
        :data:`_OUTSIDE_BEHIND` of those on one half of it, as the orbital
        fat behind a globe is, whatever touches its front. A cylinder, such
        as a muscle, has soft tissue along its axis on every half.
        """
        points = index + _directions() * (_SHELL * radius / self._voxel)
        inside = np.all((points >= 0) & (points <= np.array(soft.shape) - 1), axis=1)
        if not inside.all():
            return False
        nearest = np.rint(points).astype(np.intp)
        outside = ~soft[nearest[:, 0], nearest[:, 1], nearest[:, 2]]
        halves = _directions() @ _directions().T > 0
        behind = (halves & outside).sum(axis=1) / halves.sum(axis=1)
        return (
            float(outside.mean()) >= _OUTSIDE and float(behind.max()) >= _OUTSIDE_BEHIND
        )

    def _position(self, index: np.ndarray) -> np.ndarray:
        """The x, y, and z of a point indexed from superior, anterior, right."""
        superior, anterior, right = index
        return self._first + self._voxel * np.array([right, anterior, -superior])

    def _index(self, point: np.ndarray) -> np.ndarray:
        """The index, from superior, anterior, and right, of a point."""
        return (
            np.array(
                [
                    self._first[2] - point[2],
                    point[1] - self._first[1],
                    point[0] - self._first[0],
                ]
            )
            / self._voxel
        )

    def _in_orbit(self, bone: np.ndarray, region: _Region, outwards: int) -> bool:
        """Whether there is bone lateral to and superior to a globe.

        Lateral is towards lower x for the patient's right globe, so
        ``outwards`` is -1, and towards higher x for the left, +1. Each is
        looked for in a box from the globe's surface to :data:`ORBIT_REACH`
        beyond it, :data:`_ORBIT_HALF_WIDTH` either side of the ray, and
        reaching as far posterior, since the orbit's rim lies behind the
        globe's centre.
        """
        superior, anterior, right = self._index(region.centre)
        near = region.radius / self._voxel
        far = (region.radius + ORBIT_REACH) / self._voxel
        half = _ORBIT_HALF_WIDTH / self._voxel
        lateral = _box(
            bone.shape,
            (superior - half, superior + half),
            (anterior - half, anterior + far),
            (right + near, right + far)
            if outwards > 0
            else (right - far, right - near),
        )
        above = _box(
            bone.shape,
            (superior - far, superior - near),
            (anterior - half, anterior + far),
            (right - half, right + half),
        )
        return bool(bone[lateral].any()) and bool(bone[above].any())

    def _head_behind(
        self,
        body: np.ndarray,
        middle: np.ndarray,
        anterior: np.ndarray,
        across: np.ndarray,
    ) -> bool:
        """Whether tissue fills more of the region behind the eyes than in
        front, by :data:`HEAD_BEHIND`, as the module describes."""
        superior = self._index(middle)[0]
        half = _CHECKED_HALF_HEIGHT / self._voxel
        rows = slice(
            max(0, math.floor(superior - half)),
            max(0, min(body.shape[0], math.ceil(superior + half) + 1)),
        )
        slab = body[rows]
        anteriors, rights = np.meshgrid(
            np.arange(slab.shape[1]), np.arange(slab.shape[2]), indexing="ij"
        )
        x = self._first[0] + self._voxel * rights - middle[0]
        y = self._first[1] + self._voxel * anteriors - middle[1]
        ahead = x * anterior[0] + y * anterior[1]
        width = float(np.linalg.norm(across[:2]))
        sideways = np.abs(x * across[0] + y * across[1]) / width
        between = sideways <= width / 2
        low, high = CHECKED_DEPTH
        front = between & (ahead >= low) & (ahead <= high)
        back = between & (-ahead >= low) & (-ahead <= high)
        filled = {}
        for name, where in (("front", front), ("back", back)):
            count = int(where.sum()) * slab.shape[0]
            filled[name] = float(slab[:, where].sum()) / count if count else 0.0
        return filled["back"] - filled["front"] >= HEAD_BEHIND

    def _cranium_above(self, bone: np.ndarray, middle: np.ndarray) -> bool:
        """Whether bone encloses more of the axial slices above the eyes
        than below them, as the module describes."""
        superior = self._index(middle)[0]
        low, high = (depth / self._voxel for depth in CRANIUM_DEPTH)
        enclosed = {}
        for name, start, stop in (
            ("above", superior - high, superior - low),
            ("below", superior + low, superior + high),
        ):
            rows = range(
                max(0, math.ceil(start)),
                max(0, min(bone.shape[0], math.floor(stop) + 1)),
            )
            enclosed[name] = sum(
                int((scipy.ndimage.binary_fill_holes(bone[row]) & ~bone[row]).sum())
                for row in rows
            )
        return enclosed["above"] > enclosed["below"]


def _spacing_over(heights: np.ndarray, low: float, high: float) -> float:
    """The largest spacing between consecutive sorted ``heights`` that
    overlaps the span from ``low`` to ``high``, or 0 for one height."""
    overlapping = (heights[1:] >= low) & (heights[:-1] <= high)
    gaps = np.diff(heights)[overlapping]
    return float(gaps.max()) if gaps.size else 0.0


def _paired(right: _Region, left: _Region) -> bool:
    """Whether two regions lie side by side, as the module describes."""
    across = left.centre - right.centre
    apart = float(np.linalg.norm(across[:2]))
    turn = math.degrees(math.atan2(abs(across[1]), across[0]))
    return (
        GLOBE_SEPARATION[0] <= apart <= GLOBE_SEPARATION[1]
        and abs(across[2]) <= PAIR_TOLERANCE
        and turn <= MAXIMUM_TURN
    )


@functools.cache
def _directions() -> np.ndarray:
    """:data:`_DIRECTION_COUNT` unit vectors spread evenly over the sphere."""
    count = _DIRECTION_COUNT
    steps = np.arange(count) + 0.5
    polar = np.arccos(1 - 2 * steps / count)
    azimuth = math.pi * (1 + 5**0.5) * steps
    return np.stack(
        [
            np.cos(polar),
            np.sin(polar) * np.cos(azimuth),
            np.sin(polar) * np.sin(azimuth),
        ],
        axis=1,
    )


def _box(
    shape: tuple[int, ...], *ranges: tuple[float, float]
) -> tuple[slice, slice, slice]:
    """The voxels from each low to each high index, within the volume."""
    parts = [
        slice(
            max(0, math.floor(low)),
            max(0, min(size, math.ceil(high) + 1)),
        )
        for size, (low, high) in zip(shape, ranges)
    ]
    return parts[0], parts[1], parts[2]


def _ball(radius: float) -> np.ndarray:
    """The voxels within ``radius`` voxels of the centre."""
    reach = max(0, math.floor(radius))
    steps = np.arange(-reach, reach + 1)
    squared = (
        steps[:, None, None] ** 2
        + steps[None, :, None] ** 2
        + steps[None, None, :] ** 2
    )
    return squared <= radius**2 + 1e-9


def _point(centre: np.ndarray) -> tuple[float, float, float]:
    return float(centre[0]), float(centre[1]), float(centre[2])
