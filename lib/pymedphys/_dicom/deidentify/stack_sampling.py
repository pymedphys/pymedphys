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

"""Sample a stack of parallel slices to cubic voxels along the patient's axes.

:func:`~pymedphys._dicom.deidentify.qc_surfaces.grid` places a volume whose
rows, columns, and slices each lie along one of the patient's axes, and the
face finder (:mod:`~pymedphys._dicom.deidentify.defacing`) and the QC pack's
surface renders (:mod:`~pymedphys._dicom.deidentify.qc_surfaces`) sample
such a volume by nearest neighbour, one index along each axis at a time. A
stack with a gantry tilt does not lie so: either its rows or columns are
turned about the patient's left-right axis while its slices step along the
table, or its slices are recorded as axial while each is offset within its
plane from the last, which shears the stack. Nor does an oblique stack,
whose rows and columns are turned about any axis. This module samples any
of them, and any stack whose axes do lie along the patient's, by nearest
neighbour as those modules do, in the same voxels and with the same
results there.

A :class:`Stack` is a stack of slices that share one Image Orientation
(Patient), Pixel Spacing, and number of rows and columns, each placed by its
own Image Position (Patient), so that the slices are parallel, of one
normal, the cross product of the row and column directions, but may be
offset within their plane, unevenly spaced along the normal, and given in
any order. Its row and column directions must each be of unit length, and
perpendicular, within :data:`ORTHONORMAL_TOLERANCE`, and no two slices may
lie within :data:`SAME_POSITION` millimetres of each other along the
normal; any other is refused with a :class:`StackRefused`.

A :class:`Lattice` holds cubic voxels of a given side whose axes lie along
the patient's, indexed from superior, from anterior, then from the
patient's right, as the face finder and :meth:`qc_surfaces.Surface.mask
<pymedphys._dicom.deidentify.qc_surfaces.Surface.mask>` index theirs. It
spans the centres of every pixel of every slice, from the lowest x, the
lowest y, and the highest z, with as many voxels along each axis as fit
within that span, give or take a millionth of a voxel.

A :class:`StackSampler` maps each voxel of a lattice to one pixel at most:
:meth:`StackSampler.nearest` gives, for a slice, the voxels that take one of
its pixels, and which pixel each takes. Each voxel takes:

1. the slice whose position along the normal is nearest the voxel's centre,
   provided the centre lies no further beyond the first or last slice along
   the normal than half the spacing between that slice and its neighbour,
   or than half a voxel for a stack of one slice; and
2. within it, the pixel nearest the centre's orthogonal projection onto the
   slice's plane, along its rows and along its columns, provided the
   projection lies within half a pixel of the slice's outermost pixel
   centres.

A voxel that meets neither proviso takes no pixel, and is not a number in
a :class:`SampledVolume`, as padding is. Where two slices, or two rows or
columns, lie within :data:`_TIE` of equally near, the one of lower
coordinate along the patient axis that the normal, or the row or column
direction, lies most nearly along wins, as
:func:`qc_surfaces.sampled_indices
<pymedphys._dicom.deidentify.qc_surfaces.sampled_indices>` gives it. So a
stack whose axes lie along the patient's is sampled exactly as by
:func:`qc_surfaces.grid <pymedphys._dicom.deidentify.qc_surfaces.grid>` and
:func:`~pymedphys._dicom.deidentify.qc_surfaces.sampled_indices`, and a
tilted or oblique one by the same rule along its own normal and within its
own slices. Each slice's pixels are its own, placed by its own position, so
a sheared stack is sampled as the shear lays its slices.

Where slices are closer than the voxels, some slice may be nearest no
voxel's centre, and so is not sampled at all. :meth:`StackSampler.crossed`
gives, for each slice, along each line of voxels parallel to the patient
axis that the normal lies most nearly along, the voxel nearest where the
slice's plane meets the line, within the lattice and within a voxel's
extent along the normal, :math:`v \\lVert \\hat{n} \\rVert_1` for voxels
of side :math:`v`, of the plane, and the pixel that it takes from that slice
by step 2. Every slice that meets a line then has a voxel on it, so that a
:class:`SampledVolume` that takes each voxel's greatest value over its
nearest slice and every slice that crosses it, as
:class:`~pymedphys._dicom.deidentify.qc_surfaces.Surface` does, draws every
slice. Where the stack's axes lie along the patient's, this is the voxel
nearest each slice along the slice axis, as
:func:`qc_surfaces.nearest_voxels
<pymedphys._dicom.deidentify.qc_surfaces.nearest_voxels>` gives it.

The sampler holds no voxels: for each slice it finds, along each line of
voxels, the run of voxels whose nearest slice it is, from the slices'
positions along the normal, which vary linearly along the line. So the work
for a slice is of the number of lines and of the voxels it gives, and a
caller samples a volume as each slice is decoded, holding only the sampled
voxels, as the face finder and the surface renders do.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Sequence
from typing import NamedTuple

from pymedphys._imports import numpy as np

# Of a direction cosine's length off 1, and of the cosine of the angle
# between the row and column directions off 0.
ORTHONORMAL_TOLERANCE = 1e-4
# Millimetres along the normal within which two slices are at one position.
SAME_POSITION = 1e-6
# Within this, in millimetres along the normal or in pixels within a slice,
# two slices or two pixels are equally near a voxel's centre.
_TIE = 1e-6
# Within this fraction of a voxel, the lattice reaches the end of a span, as
# qc_surfaces does.
_SPAN = 1e-6
# The lattice's axis, from superior, from anterior, and from the patient's
# right, along each patient axis: x, y, then z.
_LATTICE_AXIS = (2, 1, 0)


class StackProblem(enum.Enum):
    """Why a stack of slices cannot be sampled."""

    NOT_ORTHONORMAL = "not-orthonormal"  # its rows and columns
    SLICES_AT_ONE_POSITION = "slices-at-one-position"  # along the normal


class StackRefused(Exception):
    """A stack cannot be sampled, for :attr:`problem`."""

    def __init__(self, problem: StackProblem) -> None:
        super().__init__(problem.value)
        self.problem = problem


class Taken(NamedTuple):
    """The voxels of a lattice that take pixels of one slice, and which.

    Attributes
    ----------
    voxels : numpy.ndarray
        Each voxel's index into the lattice flattened, in C order.
    rows, columns : numpy.ndarray
        The row and the column of the pixel that each voxel takes.
    """

    voxels: np.ndarray
    rows: np.ndarray
    columns: np.ndarray


@dataclasses.dataclass(frozen=True)
class Lattice:
    """Cubic voxels along the patient's axes.

    Attributes
    ----------
    first : tuple of float
        The x, y, and z of the centre of the voxel at index 0 along each
        axis: the patient's right, anterior, and superior, in millimetres.
    voxel : float
        The side of a voxel, in millimetres.
    shape : tuple of int
        The voxels from superior, from anterior, then from the patient's
        right.
    """

    first: tuple[float, float, float]
    voxel: float
    shape: tuple[int, int, int]

    @property
    def steps(self) -> np.ndarray:
        """The x, y, and z of the step from one voxel to the next along each
        of the lattice's axes: down, back, then to the patient's left."""
        return np.array(
            [[0.0, 0.0, -self.voxel], [0.0, self.voxel, 0.0], [self.voxel, 0.0, 0.0]]
        )

    @property
    def coordinates(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The z of each index from superior, the y of each from anterior,
        and the x of each from the patient's right, in millimetres."""
        x, y, z = self.first
        return (
            z - np.arange(self.shape[0]) * self.voxel,
            y + np.arange(self.shape[1]) * self.voxel,
            x + np.arange(self.shape[2]) * self.voxel,
        )

    def points(self, indices: Sequence[np.ndarray]) -> np.ndarray:
        """The x, y, and z of the centre of each voxel, along the last axis.

        ``indices`` are the voxels' indices along each of the lattice's
        axes, as :func:`numpy.unravel_index` gives them.
        """
        steps = self.steps
        points = np.broadcast_to(
            np.array(self.first, dtype=float),
            (*np.shape(indices[0]), 3),
        ).copy()
        for index, step in zip(indices, steps):
            points += np.asarray(index, dtype=float)[..., np.newaxis] * step
        return points


class Stack:
    """A stack of parallel slices, as the module describes."""

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
            Image Orientation (Patient), shared by every slice: the direction
            along a row, of increasing column index, then down a column, of
            increasing row index.
        positions : sequence of sequence of float
            Image Position (Patient) of each slice, the centre of its first
            pixel, in the order in which the slices are added, which need not
            be their order along the stack.
        spacing : sequence of float
            Pixel Spacing, shared by every slice: between rows, then between
            columns, in millimetres.
        shape : tuple of int
            Rows, then columns, shared by every slice.

        Raises
        ------
        ValueError
            If there are no positions, or ``orientation`` does not hold six
            finite numbers, each position three, ``spacing`` two positive
            ones, or ``shape`` two positive integers.
        StackRefused
            With :attr:`StackProblem.NOT_ORTHONORMAL` unless the row and
            column directions are each of unit length, and perpendicular,
            within :data:`ORTHONORMAL_TOLERANCE`; with
            :attr:`StackProblem.SLICES_AT_ONE_POSITION` if two slices lie
            within :data:`SAME_POSITION` of each other along the normal.
        """
        cosines = _finite(orientation, "Image Orientation (Patient)")
        if cosines.shape != (6,):
            raise ValueError("Image Orientation (Patient) holds six values")
        origins = _finite(positions, "a slice's position")
        if origins.ndim != 2 or origins.shape[1] != 3 or not len(origins):
            raise ValueError("a stack needs a position of three values per slice")
        spacings = _finite(spacing, "Pixel Spacing")
        if spacings.shape != (2,) or spacings.min() <= 0:
            raise ValueError("Pixel Spacing holds two positive values")
        if len(shape) != 2 or not all(
            isinstance(size, (int, np.integer))
            and not isinstance(size, bool)
            and size > 0
            for size in shape
        ):
            raise ValueError("a slice's rows and columns are two positive integers")
        along_row, down_column = cosines[:3], cosines[3:]
        if (
            any(
                abs(float(np.linalg.norm(direction)) - 1) > ORTHONORMAL_TOLERANCE
                for direction in (along_row, down_column)
            )
            or abs(float(along_row @ down_column)) > ORTHONORMAL_TOLERANCE
        ):
            raise StackRefused(StackProblem.NOT_ORTHONORMAL)
        normal = np.cross(along_row, down_column)
        normal /= np.linalg.norm(normal)
        offsets = origins @ normal
        ascending = np.sort(offsets)
        if np.any(np.diff(ascending) <= SAME_POSITION):
            raise StackRefused(StackProblem.SLICES_AT_ONE_POSITION)
        self._along_row = along_row
        self._down_column = down_column
        self._normal = normal
        self._origins = origins
        self._offsets = offsets
        self._spacing = (float(spacings[0]), float(spacings[1]))
        self._shape = (int(shape[0]), int(shape[1]))

    @property
    def along_row(self) -> np.ndarray:
        """The direction along a row, of increasing column index."""
        return self._along_row.copy()

    @property
    def down_column(self) -> np.ndarray:
        """The direction down a column, of increasing row index."""
        return self._down_column.copy()

    @property
    def normal(self) -> np.ndarray:
        """The unit normal of the slices: the cross product of the row
        direction and the column direction."""
        return self._normal.copy()

    @property
    def origins(self) -> np.ndarray:
        """Each slice's Image Position (Patient), in the order given."""
        return self._origins.copy()

    @property
    def offsets(self) -> np.ndarray:
        """Each slice's position along the normal, in millimetres, in the
        order given."""
        return self._offsets.copy()

    @property
    def spacing(self) -> tuple[float, float]:
        """Between rows, then between columns, in millimetres."""
        return self._spacing

    @property
    def shape(self) -> tuple[int, int]:
        """Rows, then columns."""
        return self._shape

    @property
    def smallest_spacing(self) -> float:
        """The smallest of the spacing between rows, between columns, and
        between neighbouring slices along the normal, in millimetres."""
        gaps = np.diff(np.sort(self._offsets))
        return float(min(*self._spacing, *gaps.tolist()))

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """The lowest, then the highest, x, y, and z of any pixel's centre."""
        rows = (0.0, (self._shape[0] - 1) * self._spacing[0])
        columns = (0.0, (self._shape[1] - 1) * self._spacing[1])
        corners = np.array(
            [
                row * self._down_column + column * self._along_row
                for row in rows
                for column in columns
            ]
        )
        points = self._origins[:, np.newaxis, :] + corners[np.newaxis, :, :]
        return points.min(axis=(0, 1)), points.max(axis=(0, 1))

    def pixel_points(
        self, index: int, rows: np.ndarray, columns: np.ndarray
    ) -> np.ndarray:
        """The x, y, and z of the centre of each pixel of a slice, along the
        last axis, for ``rows`` and ``columns`` broadcast together."""
        rows = np.asarray(rows, dtype=float)[..., np.newaxis] * self._spacing[0]
        columns = np.asarray(columns, dtype=float)[..., np.newaxis] * self._spacing[1]
        return (
            self._origins[index] + rows * self._down_column + columns * self._along_row
        )

    def lattice(self, voxel: float) -> Lattice:
        """The lattice of cubic voxels of side ``voxel`` that spans the
        centres of every pixel, as the module describes.

        Raises
        ------
        ValueError
            If ``voxel`` is not a positive finite number.
        """
        if not (math.isfinite(voxel) and voxel > 0):
            raise ValueError("a voxel's side is a positive finite number")
        low, high = self.bounds
        counts = [
            math.floor((float(high[axis]) - float(low[axis])) / voxel + _SPAN) + 1
            for axis in range(3)
        ]
        return Lattice(
            (float(low[0]), float(low[1]), float(high[2])),
            float(voxel),
            (counts[2], counts[1], counts[0]),
        )


class StackSampler:
    """Maps a lattice's voxels to a stack's pixels, as the module describes."""

    def __init__(self, stack: Stack, lattice: Lattice) -> None:
        self._stack = stack
        self._lattice = lattice
        normal = stack.normal
        # The patient axis that the normal lies most nearly along, and the
        # lattice's axis along it, along which each line of voxels runs.
        along = int(np.argmax(np.abs(normal)))
        self._run = _LATTICE_AXIS[along]
        self._across = tuple(axis for axis in range(3) if axis != self._run)
        steps = lattice.steps
        # How far along the normal each step along each lattice axis goes.
        increments = steps @ normal
        self._increment = float(increments[self._run])
        first, second = self._across
        # The position along the normal of the first voxel of each line.
        self._base = (
            float(np.array(lattice.first) @ normal)
            + increments[first] * np.arange(lattice.shape[first])[:, np.newaxis]
            + increments[second] * np.arange(lattice.shape[second])[np.newaxis, :]
        )
        offsets = stack.offsets
        self._rank = np.empty(len(offsets), np.intp)
        order = np.argsort(offsets, kind="stable")
        self._rank[order] = np.arange(len(offsets))
        ascending = offsets[order]
        if len(ascending) > 1:
            below = (ascending[1] - ascending[0]) / 2
            above = (ascending[-1] - ascending[-2]) / 2
        else:
            below = above = lattice.voxel / 2
        # Each slice's slab along the normal runs from one boundary,
        # exclusive, to the next, inclusive. Shifted so that a voxel equally
        # near two slices takes the one of lower coordinate along the patient
        # axis that the normal lies most nearly along.
        shift = _TIE if normal[along] > 0 else -_TIE
        self._boundaries = (
            np.concatenate(
                [
                    [ascending[0] - below],
                    (ascending[1:] + ascending[:-1]) / 2,
                    [ascending[-1] + above],
                ]
            )
            + shift
        )
        # The extent of a voxel along the normal.
        self._reach = lattice.voxel * float(np.abs(normal).sum())
        # From a point's offset from a slice's first pixel to its fractional
        # row and column, by the orthogonal projection onto the plane.
        placing = np.column_stack(
            [
                stack.down_column * stack.spacing[0],
                stack.along_row * stack.spacing[1],
            ]
        )
        self._unplace = np.linalg.pinv(placing)
        # Along rows, then columns, whether a pixel equally near takes the
        # lower index, which has the lower coordinate along the patient axis
        # that the direction lies most nearly along.
        self._lower = tuple(
            bool(direction[int(np.argmax(np.abs(direction)))] > 0)
            for direction in (stack.down_column, stack.along_row)
        )

    @property
    def stack(self) -> Stack:
        """The stack sampled."""
        return self._stack

    @property
    def lattice(self) -> Lattice:
        """The lattice sampled to."""
        return self._lattice

    def nearest(self, index: int) -> Taken:
        """The voxels whose nearest slice is the slice at ``index``, in the
        order in which the slices were given, that take one of its pixels,
        and which pixel each takes.

        Raises
        ------
        IndexError
            If there is no slice at ``index``.
        """
        rank = self._rank[self._slice(index)]
        low, high = self._boundaries[rank], self._boundaries[rank + 1]
        if self._increment > 0:
            start, stop = self._cut(low), self._cut(high)
        else:
            start, stop = self._cut(high), self._cut(low)
        counts = np.maximum(stop - start, 0).ravel()
        lines = np.repeat(np.arange(counts.size), counts)
        firsts = np.cumsum(counts) - counts
        along = np.repeat(start.ravel(), counts) + (
            np.arange(lines.size) - np.repeat(firsts, counts)
        )
        return self._taken(index, lines, along)

    def crossed(self, index: int) -> Taken:
        """The voxels that the plane of the slice at ``index``, in the order
        in which the slices were given, crosses, one along each line of
        voxels that it meets, that take one of its pixels, and which pixel
        each takes.

        Raises
        ------
        IndexError
            If there is no slice at ``index``.
        """
        index = self._slice(index)
        offset = float(self._stack.offsets[index])
        length = self._lattice.shape[self._run]
        exact = (offset - self._base) / self._increment
        # Equally near two voxels, the one of lower index.
        along = np.clip(np.ceil(exact - 0.5 - _TIE), 0, length - 1).astype(np.intp)
        apart = np.abs(self._base + along * self._increment - offset)
        lines = np.flatnonzero(apart.ravel() <= self._reach + _TIE)
        return self._taken(index, lines, along.ravel()[lines])

    def _slice(self, index: int) -> int:
        count = len(self._rank)
        if not -count <= index < count:
            raise IndexError("the stack has no slice at that index")
        return int(index) % count

    def _cut(self, boundary: float) -> np.ndarray:
        """For each line of voxels, the index along it from which the voxels
        lie beyond ``boundary`` along the normal, where the normal increases
        along the line, or up to which they lie at or below it, where it
        decreases, within the line."""
        length = self._lattice.shape[self._run]
        exact = (boundary - self._base) / self._increment
        if self._increment > 0:
            cut = np.floor(exact) + 1
        else:
            cut = np.ceil(exact)
        return np.clip(cut, 0, length).astype(np.intp)

    def _taken(self, index: int, lines: np.ndarray, along: np.ndarray) -> Taken:
        """The voxels at ``along`` on each of ``lines``, flattened over the
        two lattice axes across them, that take a pixel of the slice at
        ``index``, and which pixel each takes."""
        first, second = self._across
        indices: list[np.ndarray] = [np.empty(0, np.intp)] * 3
        indices[self._run] = np.asarray(along, np.intp)
        indices[first], indices[second] = np.divmod(
            np.asarray(lines, np.intp), self._lattice.shape[second]
        )
        points = self._lattice.points(indices)
        fractions = (points - self._stack.origins[index]) @ self._unplace.T
        pixels = []
        for fraction, lower in zip(fractions.T, self._lower):
            # Equally near two pixels, the one of lower coordinate.
            nudge = -_TIE if lower else _TIE
            pixels.append(np.floor(fraction + 0.5 + nudge).astype(np.intp))
        rows, columns = pixels[0], pixels[1]
        within = (
            (rows >= 0)
            & (rows < self._stack.shape[0])
            & (columns >= 0)
            & (columns < self._stack.shape[1])
        )
        voxels = np.ravel_multi_index(
            tuple(axis[within] for axis in indices), self._lattice.shape
        )
        return Taken(np.asarray(voxels, np.intp), rows[within], columns[within])


class SampledVolume:
    """A stack sampled to a lattice, slice by slice, as the module describes.

    Each voxel takes its nearest slice's pixel, or, where ``every_slice``,
    its greatest value over that and every slice that crosses it
    (:meth:`StackSampler.crossed`), ignoring padding, which is NaN, unless
    every value is, so that every slice is drawn.
    """

    def __init__(self, sampler: StackSampler, every_slice: bool = False) -> None:
        self._sampler = sampler
        self._every_slice = every_slice
        self._values = np.full(sampler.lattice.shape, np.nan, np.float32)
        self._added: set[int] = set()
        self._next = 0

    @property
    def sampler(self) -> StackSampler:
        """The sampler that places each slice's pixels."""
        return self._sampler

    @property
    def complete(self) -> bool:
        """Whether every slice has been added."""
        return len(self._added) == len(self._sampler.stack.offsets)

    @property
    def values(self) -> np.ndarray:
        """The sampled volume, as float32, indexed from superior, from
        anterior, then from the patient's right; NaN where a voxel takes no
        pixel, or padding.

        Raises
        ------
        ValueError
            If a slice has not been added.
        """
        if not self.complete:
            raise ValueError("a sampled volume needs every slice of the stack")
        return self._values

    def add(self, frame: np.ndarray, index: int | None = None) -> None:
        """Add a slice, with padding as NaN.

        ``index`` is its place in the order in which the stack's slices
        were given; by default, the slice after the last one added. A slice
        added twice counts once.

        Raises
        ------
        ValueError
            If ``index`` is not a slice of the stack, or ``frame`` is not of
            its rows and columns.
        """
        count = len(self._sampler.stack.offsets)
        if index is None:
            index = self._next
        if not 0 <= index < count:
            raise ValueError("the stack has no slice at that index")
        frame = np.asarray(frame, dtype=np.float32)
        if frame.shape != self._sampler.stack.shape:
            raise ValueError("a slice must have the stack's rows and columns")
        self._next = index + 1
        self._added.add(index)
        flat = self._values.reshape(-1)
        nearest = self._sampler.nearest(index)
        values = frame[nearest.rows, nearest.columns]
        if not self._every_slice:
            flat[nearest.voxels] = values
            return
        # fmax keeps a voxel's highest slice, and ignores NaN, which is
        # padding or a voxel not yet sampled, unless every value is.
        flat[nearest.voxels] = np.fmax(flat[nearest.voxels], values)
        crossed = self._sampler.crossed(index)
        flat[crossed.voxels] = np.fmax(
            flat[crossed.voxels], frame[crossed.rows, crossed.columns]
        )


def _finite(values: object, name: str) -> np.ndarray:
    """``values`` as an array of finite numbers.

    Raises
    ------
    ValueError
        Naming ``name``, but not the values, which are not finite numbers in
        a regular array.
    """
    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(f"{name} is not of finite numbers") from None
    if not np.isfinite(array).all():
        raise ValueError(f"{name} is not of finite numbers")
    return array
