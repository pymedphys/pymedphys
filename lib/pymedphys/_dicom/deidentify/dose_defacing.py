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

"""RT Dose in the Frame of Reference of a defaced CT series, set to zero
in its face block.

Under the Clean Recognizable Visual Features Option, an RT Dose grid in the
frame of a CT series that a run defaces
(:mod:`~pymedphys._dicom.deidentify.face_blocks`) traces the face too: its
dose falls away at the skin, so the edge of the dose that a body receives
outlines the face that the CT no longer shows. A run therefore sets the
dose to zero in the same region as the CT's, the face block less the
brain that defacing keeps, on the grid's own geometry
(:class:`RtDoseDefacer`), and never recalculates it. A voxel is in the
region where its centre is in the block, and is kept where the nearest
pixel of the nearest slice that the block reaches, within half the slices'
spacing, is one that defacing keeps (:class:`DoseBlock`), of the brain or
of a target's hull, or where its centre lies in a target's hull
(:mod:`~pymedphys._dicom.deidentify.target_hulls`); any other voxel beyond
the slices is not kept.

The grid is placed by Image Position (Patient), Image Orientation
(Patient), Pixel Spacing, and Grid Frame Offset Vector, as PS3.3 C.8.8.3.2
defines: offsets along the normal from the first frame's position where the
first offset is zero, or, only for an orientation of (1, 0, 0, 0, 1, 0)
whose first offset is the position's z, the frames' z coordinates. A grid
placed otherwise, whose direction cosines are not two orthogonal unit
vectors, as PS3.3 C.7.6.2.1.1 requires, within :data:`_UNIT`, with a
spacing, or a coordinate of a corner of a frame, of magnitude above
:data:`_FARTHEST`, of more than one sample, with compressed Pixel Data whose
frames do not decode, or with a negative stored value other than in a grid
of Dose Type ERROR, is not set to zero, and stays held as an instance in a
defaced frame
(:attr:`~.reasons.VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME`).
Compressed Pixel Data is decoded as Clean Pixel Data decodes it, set to
zero there, and written uncompressed, in Explicit VR Little Endian, as
Clean Pixel Data writes it, unless nothing is set to zero (D-037, D-051).

Setting dose to zero must never take dose from a target that the
structure set does not mark, since RT ROI Interpreted Type is Type 2, nor
dose that matters, so where the greatest dose that it would set to zero is
more than :data:`DOSE_FRACTION` of the grid's greatest, nothing is set to
zero, and the instance is held for review instead
(:attr:`~.reasons.VisualFeaturesReason.DOSE_IN_FACE_BLOCK`). The fraction is
of the grid's own maximum rather than of the prescription, which only an RT
Plan that may not be in the run holds. Dose Grid Scaling multiplies every
stored value alike, so the stored values are compared. A grid of Dose Type
ERROR holds the difference between two doses, as signed stored values
(PS3.3 C.8.8.3.4.6), so its zero is no difference, and the magnitudes of
its stored values are compared; a negative stored value in any other grid,
whose Pixel Representation PS3.3 C.8.8.3.4.6 makes unsigned, holds it as
above.

An RT Dose that names exactly one Frame of Reference, in which a run
defaces a series, is set to zero (:func:`find_dose_blocks`): where it
defaces more than one, as a 4D CT's average, maximum intensity projection,
and phase series share one frame, in the block of each series in turn, by
its own slices, so that a voxel is set to zero where any series' defacing
writes air at it (:class:`FrameRegion`). Any other RT Dose in a defaced
frame, naming none, or referring to a defaced slice stays held, as
:class:`~.face_blocks.Defaced` holds it, as does one set to zero that
refers to a defaced slice of a series in another frame, and one in a frame
of which a series' slices can no longer be read. An RT Dose without pixel
data, which holds only dose-volume histograms, shows no face, and is not
held for its frame. Its dose-volume histograms and any other RT Dose's are
kept as they are, as the dose-volume histograms of the voxels before any
were set to zero.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import TypeAlias

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from .defacing import FaceBlock
from .diagnostics import redacted_diagnostics
from .face_blocks import (
    CT_IODS,
    Defaced,
    KeptSlice,
    SeriesDefacing,
    frames_of,
    kept_slices,
)
from .pixel_cleaning import FrameMask, Layout, PixelDataRefused, frames_layout
from .reasons import TransformReason, VisualFeaturesReason
from .references import InstanceRecord
from .target_hulls import KeptTargets, slice_reach

RT_DOSE = "RT Dose"
# The Dose Type of a grid of differences between doses, whose stored values
# are signed (PS3.3 C.8.8.3.4.6).
ERROR = "ERROR"
# The greatest fraction of the grid's maximum dose that the run sets to zero
# in the face block. A placeholder, to be set by validation.
DOSE_FRACTION = 0.05
# How far, in millimetres, an absolute Grid Frame Offset Vector's first
# offset may lie from Image Position (Patient)'s z.
_SAME_Z = 1e-3
# How far each direction cosine vector's length may lie from 1, and their
# dot product from 0. Cosines written to six decimal places lie well within
# it. It bounds the vectors, not the voxels' positions, whose error also
# grows with their distance from the grid's first voxel.
_UNIT = 1e-4
# The largest magnitude, in millimetres, of each coordinate of a corner of
# a frame of a grid that is placed, or of its spacing, as face_blocks bounds
# each coordinate of a target's points; a larger one, finite, could put the
# block anywhere on the grid.
_FARTHEST = 1e6
_AXIAL = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


@dataclasses.dataclass(frozen=True, repr=False)
class DoseBlock:
    """The face block of the one series defaced in a Frame of Reference,
    with the pixels of its slices that defacing keeps.

    Its ``repr`` shows only the number of slices.

    Attributes
    ----------
    block : FaceBlock
    slices : tuple of KeptSlice
        Each slice of the series that the block reaches: each CT Image
        instance, or frame of a multi-frame CT instance.
    instances : frozenset of str
        The SOP Instance UID of each instance of the series.
    targets : KeptTargets, optional
        The hulls of the targets that defacing keeps in the block, as the
        series' outcome gives them; none by default.
    """

    block: FaceBlock
    slices: tuple[KeptSlice, ...]
    instances: frozenset[str] = frozenset()
    targets: KeptTargets = KeptTargets()

    def __repr__(self) -> str:
        return f"DoseBlock(slices={len(self.slices)})"

    @property
    def blocks(self) -> tuple[DoseBlock, ...]:
        """The block alone, as :attr:`FrameRegion.blocks` gives a frame's."""
        return (self,)

    def holds(self, defaced: Defaced, record: InstanceRecord) -> bool:
        """Whether an RT Dose set to zero in the block is still held for a
        defaced frame: it refers to a defaced slice of another series, as
        :meth:`~.face_blocks.Defaced.holds` would hold it for."""
        return _refers_elsewhere(self.instances, defaced, record)

    def written(
        self,
        position: Sequence[float],
        orientation: Sequence[float],
        spacing: Sequence[float],
        shape: tuple[int, int],
    ) -> np.ndarray:
        """Which pixels of a plane defacing writes over: those whose centres
        lie in the block, other than one whose nearest pixel, of the nearest
        slice, defacing keeps (:meth:`kept`).

        Parameters
        ----------
        position, orientation, spacing, shape
            As for :meth:`~.defacing.FaceBlock.slice_mask`.

        Returns
        -------
        numpy.ndarray
            Of bool, of ``shape``.
        """
        inside = self.block.slice_mask(position, orientation, spacing, shape)
        if inside.any():
            rows, columns = np.nonzero(inside)
            points = (
                np.asarray(position, dtype=float)
                + columns[:, np.newaxis]
                * float(spacing[1])
                * np.asarray(orientation[:3], dtype=float)
                + rows[:, np.newaxis]
                * float(spacing[0])
                * np.asarray(orientation[3:], dtype=float)
            )
            inside[rows, columns] = ~self.kept(points)
        return inside

    def kept(self, points: np.ndarray) -> np.ndarray:
        """Whether defacing keeps the nearest pixel of the nearest slice to
        each point, within half the slices' spacing, or the point lies in a
        target's hull, which defacing keeps wherever no slice's pixel is
        near enough.

        Parameters
        ----------
        points : numpy.ndarray
            The x, y, and z of each point in rows, in millimetres.

        Returns
        -------
        numpy.ndarray
            Of bool, one for each point.
        """
        slices, rows, columns = self.pixels(points)
        kept = np.zeros(len(slices), dtype=bool)
        for index in np.unique(slices[slices >= 0]):
            chosen = slices == index
            kept[chosen] = self.slices[index].kept[rows[chosen], columns[chosen]]
        return kept | self.targets.contains(points)

    def nearest_slices(self, points: np.ndarray) -> np.ndarray:
        """Return the nearest slice to each point, within half the slices'
        spacing, by its height along the slices' normal alone, whether or
        not the point lies within the slice's pixels.

        Parameters
        ----------
        points : numpy.ndarray
            The x, y, and z of each point in rows, in millimetres.

        Returns
        -------
        numpy.ndarray
            Of int, one for each point: the index of the slice in
            :attr:`slices`, or -1 where no slice is near enough.
        """
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        found = np.full(len(points), -1)
        if not self.slices or not len(points):
            return found
        orientation = self.slices[0].orientation
        normal = np.cross(orientation[:3], orientation[3:])
        heights = np.array([np.dot(each.position, normal) for each in self.slices])
        order = np.argsort(heights)
        heights = heights[order]
        # A single slice is taken to span no more than its own pixels.
        reach = slice_reach(heights, self.slices[0].spacing)
        along = points @ normal
        nearest = np.clip(np.searchsorted(heights, along), 1, max(len(heights) - 1, 1))
        if len(heights) > 1:
            below = np.abs(along - heights[nearest - 1])
            above = np.abs(along - heights[nearest])
            nearest = np.where(below <= above, nearest - 1, nearest)
        else:
            nearest = np.zeros(len(points), dtype=int)
        near = np.abs(along - heights[nearest]) <= reach
        found[near] = order[nearest[near]]
        return found

    def spanned(
        self, points: np.ndarray, direction: Sequence[float], near: float, far: float
    ) -> tuple[int, ...] | None:
        """Return every slice that :meth:`nearest_slices` gives a point
        within the convex hull of ``points`` moved along ``direction`` by any
        distance from ``near`` to ``far``, or None where it gives such a
        point none, or two slices lie at one height.

        Each such point's height along the slices' normal lies between the
        least and the greatest of the points' heights at either end, so a
        slice counts where the heights nearer it than any other, within
        half the slices' spacing, meet that interval, both ends included.

        Parameters
        ----------
        points : numpy.ndarray
            The x, y, and z of each point in rows, in millimetres.
        direction : sequence of float
            A unit vector.
        near, far : float
            In millimetres, ``near`` at most ``far``.

        Returns
        -------
        tuple of int or None
            The indices in :attr:`slices`, ascending.
        """
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        if not self.slices or not len(points):
            return None
        orientation = self.slices[0].orientation
        normal = np.cross(orientation[:3], orientation[3:])
        heights = np.array([np.dot(each.position, normal) for each in self.slices])
        order = np.argsort(heights)
        ordered = heights[order]
        steps = np.diff(ordered)
        if (steps <= 0).any():
            return None
        reach = (
            float(np.min(steps)) / 2 if len(steps) else max(self.slices[0].spacing) / 2
        )
        along = points @ normal
        rate = float(np.dot(np.asarray(direction, dtype=float), normal))
        low = float(np.min(along) + min(near * rate, far * rate))
        high = float(np.max(along) + max(near * rate, far * rate))
        # The heights within reach of a slice, and nearer it than any other.
        middles = (ordered[1:] + ordered[:-1]) / 2
        lower = np.maximum(ordered - reach, np.concatenate([[-np.inf], middles]))
        upper = np.minimum(ordered + reach, np.concatenate([middles, [np.inf]]))
        met = (lower <= high) & (upper >= low)
        if not met.any():
            return None
        # Every height of the interval must be within some slice's reach.
        first, last = np.flatnonzero(met)[[0, -1]]
        gaps = upper[first:last] < lower[first + 1 : last + 1]
        if lower[first] > low or upper[last] < high or gaps.any():
            return None
        return tuple(sorted(int(order[index]) for index in np.flatnonzero(met)))

    def pixels(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return the nearest pixel of the nearest slice to each point, within
        half the slices' spacing, where it has one.

        Parameters
        ----------
        points : numpy.ndarray
            The x, y, and z of each point in rows, in millimetres.

        Returns
        -------
        tuple of numpy.ndarray
            Of int, one for each point: the index of the slice in
            :attr:`slices`, or -1 where no slice's pixel is near enough, and
            the pixel's row and column, which are 0 where there is none.
        """
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        nearest = self.nearest_slices(points)
        found = np.full(len(points), -1)
        found_rows = np.zeros(len(points), dtype=int)
        found_columns = np.zeros(len(points), dtype=int)
        for index in np.unique(nearest[nearest >= 0]):
            each = self.slices[index]
            chosen = np.flatnonzero(nearest == index)
            offset = points[chosen] - np.asarray(each.position)
            columns = np.rint(
                offset @ np.asarray(each.orientation[:3]) / each.spacing[1]
            )
            rows = np.rint(offset @ np.asarray(each.orientation[3:]) / each.spacing[0])
            height, width = each.kept.shape
            within = (rows >= 0) & (rows < height) & (columns >= 0) & (columns < width)
            chosen = chosen[within]
            found[chosen] = index
            found_rows[chosen] = rows[within].astype(int)
            found_columns[chosen] = columns[within].astype(int)
        return found, found_rows, found_columns


@dataclasses.dataclass(frozen=True, repr=False)
class FrameRegion:
    """The block of each series that a run defaces in one Frame of
    Reference, by which an instance in that frame is cleaned, in each block
    in turn.

    Its ``repr`` shows only the number of blocks.

    Attributes
    ----------
    blocks : tuple of DoseBlock
        One for each defaced series, in the order of their Series Instance
        UIDs; never empty.
    """

    blocks: tuple[DoseBlock, ...]

    def __post_init__(self) -> None:
        if not self.blocks:
            raise ValueError("a frame's region has a block")

    def __repr__(self) -> str:
        return f"FrameRegion(blocks={len(self.blocks)})"

    @property
    def instances(self) -> frozenset[str]:
        """The SOP Instance UID of each instance of the frame's defaced
        series."""
        return frozenset().union(*(each.instances for each in self.blocks))

    def holds(self, defaced: Defaced, record: InstanceRecord) -> bool:
        """Whether an instance cleaned in the frame's blocks is still held
        for a defaced frame: it refers to a defaced slice of a series in
        another frame, as :meth:`~.face_blocks.Defaced.holds` would hold it
        for."""
        return _refers_elsewhere(self.instances, defaced, record)

    def written(
        self,
        position: Sequence[float],
        orientation: Sequence[float],
        spacing: Sequence[float],
        shape: tuple[int, int],
    ) -> np.ndarray:
        """Which pixels of a plane the defacing of any of the frame's series
        writes over, as :meth:`DoseBlock.written` gives each."""
        written = np.zeros(shape, dtype=bool)
        for each in self.blocks:
            written |= each.written(position, orientation, spacing, shape)
        return written


# The block of an instance's frame, by which a defacer cleans it: one
# series' block, or the blocks of every series defaced in the frame.
Region: TypeAlias = "DoseBlock | FrameRegion"


def _refers_elsewhere(
    instances: frozenset[str], defaced: Defaced, record: InstanceRecord
) -> bool:
    """Whether an instance refers to a defaced slice other than one of
    ``instances``."""
    return any(
        reference.target in defaced.instances and reference.target not in instances
        for reference in record.references
    )


def frame_region(
    record: InstanceRecord, regions: Mapping[str, FrameRegion]
) -> FrameRegion | None:
    """Return the region of an RT Dose's, PET image's, or Segmentation's
    only Frame of Reference, where it names exactly one and the run cleans
    instances there, or None."""
    frames = frames_of(record)
    if len(frames) != 1:
        return None
    return regions.get(next(iter(frames)))


def structure_set_regions(
    record: InstanceRecord, regions: Mapping[str, FrameRegion], defaced: Defaced
) -> dict[str, FrameRegion] | None:
    """Return the region of each defaced Frame of Reference that an RT
    Structure Set names, by which
    :func:`~.region_defacing.cut_contours` cuts its ROIs there, where it
    names one and each has a region; None where it names none, so that
    :meth:`~.face_blocks.Defaced.holds` decides it, or where one has no
    region, so that it stays held."""
    named = frames_of(record) & defaced.frames
    if not named or not named <= regions.keys():
        return None
    return {frame: regions[frame] for frame in sorted(named)}


def joined(regions: Mapping[str, FrameRegion]) -> FrameRegion:
    """Return the blocks of every region of ``regions`` as one region, whose
    :attr:`~FrameRegion.instances` and :meth:`~FrameRegion.holds` are those
    of all of them."""
    return FrameRegion(
        tuple(block for each in regions.values() for block in each.blocks)
    )


def find_dose_blocks(
    records: Mapping[int, InstanceRecord],
    read: Callable[[int], bytes | None],
    outcomes: Mapping[str, SeriesDefacing],
    iods: Collection[str] = (RT_DOSE,),
) -> dict[str, FrameRegion]:
    """Return the blocks of each Frame of Reference whose RT Dose instances
    the run sets to zero there, by its UID.

    That is each frame in which a series is defaced, as
    :func:`~.face_blocks.find_face_blocks`' ``outcomes`` give them, and
    which an RT Dose of the run names, or an instance of any other of
    ``iods``, whose instances
    :mod:`~pymedphys._dicom.deidentify.region_defacing` cleans in the same
    blocks, with the block of each series defaced in it. A frame of which
    any defaced series' slices can no longer be read has none, so that its
    instances stay held.
    """
    defaced: dict[str, list[str]] = {}
    for uid, outcome in sorted(outcomes.items()):
        if outcome.frame is not None and outcome.block is not None:
            defaced.setdefault(outcome.frame, []).append(uid)
    named: set[str] = set()
    for record in records.values():
        if record.iod in iods:
            named |= frames_of(record)
    regions = {}
    for frame in sorted(named & set(defaced)):
        try:
            blocks = tuple(
                _dose_block(records, read, uid, outcomes[uid]) for uid in defaced[frame]
            )
        except ValueError:
            continue
        regions[frame] = FrameRegion(blocks)
    return regions


def _dose_block(
    records: Mapping[int, InstanceRecord],
    read: Callable[[int], bytes | None],
    series: str,
    outcome: SeriesDefacing,
) -> DoseBlock:
    """Return the block of one defaced series, with its slices.

    Raises
    ------
    ValueError
        Where a slice can no longer be read, without its message.
    """
    block = outcome.block
    assert block is not None
    positions = sorted(
        position
        for position, record in records.items()
        if record.iod in CT_IODS and record.series == series
    )
    instances = frozenset(
        uid
        for position in positions
        if (uid := records[position].sop_instance) is not None
    )
    return DoseBlock(
        block,
        kept_slices(block, positions, read, outcome.targets),
        instances,
        outcome.targets,
    )


class RtDoseDefacer:
    """Gives the region of each frame of an RT Dose grid to set to zero, for
    :func:`~pymedphys._dicom.deidentify.pixel_cleaning.black_out`, and
    whether the dose there is too great to set to zero.

    Parameters
    ----------
    dose : DoseBlock or FrameRegion
        The block of the grid's Frame of Reference, or the blocks of each
        series defaced in it.
    dataset : pydicom.Dataset
        The RT Dose's data set.

    Raises
    ------
    PixelDataRefused
        With :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` where
        the grid is not one that the module sets to zero.
    """

    def __init__(self, dose: Region, dataset: pydicom.Dataset) -> None:
        try:
            layout = frames_layout(dataset, str(dataset.file_meta.TransferSyntaxUID))
            if layout.samples != 1:
                raise ValueError("more than one sample")
            with redacted_diagnostics():
                position = _numbers(dataset, "ImagePositionPatient", 3)
                orientation = _numbers(dataset, "ImageOrientationPatient", 6)
                _check_directions(orientation)
                spacing = _numbers(dataset, "PixelSpacing", 2)
                offsets = (
                    _numbers(dataset, "GridFrameOffsetVector", layout.frames)
                    if "GridFrameOffsetVector" in dataset or layout.frames > 1
                    else (0.0,)
                )
                kind = dataset.get("DoseType")
                error = isinstance(kind, str) and kind.strip().upper() == ERROR
            self._origins = _origins(position, orientation, offsets)
            _check_reach(self._origins, orientation, spacing, layout)
        # Whatever the data set raises refuses the grid, without its message,
        # which could quote a value.
        except Exception:  # pylint: disable = broad-exception-caught
            raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA) from None
        if min(spacing) <= 0:
            raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA)
        self._dose = dose
        self._orientation = orientation
        self._spacing = (spacing[0], spacing[1])
        self._shape = (layout.rows, layout.columns)
        self._error = error
        self._greatest = 0
        self._zeroed = 0
        self._negative = False

    def __repr__(self) -> str:
        return "RtDoseDefacer()"

    def mask(self, frame: int, stored: np.ndarray) -> FrameMask | None:
        """Return the voxels of one frame to set to zero, as the module
        describes, or None where the frame has none."""
        stored = np.asarray(stored)
        compared = self.compared(stored)
        if stored.size:
            self._greatest = max(self._greatest, int(compared.max()))
            self._negative |= bool(int(stored.min()) < 0)
        inside = self._dose.written(
            self._origins[frame], self._orientation, self._spacing, self._shape
        )
        if not inside.any():
            return None
        self._zeroed = max(self._zeroed, int(compared[inside].max()))
        return FrameMask(frame, inside, 0)

    def compared(self, stored: np.ndarray) -> np.ndarray:
        """Return the values of a frame's stored values that
        :data:`DOSE_FRACTION` compares: the stored values, or for a grid of
        Dose Type ERROR, of differences, their magnitudes."""
        stored = np.asarray(stored)
        return np.abs(stored.astype(np.int64)) if self._error else stored

    @property
    def held(self) -> VisualFeaturesReason | None:
        """Why the grid is held rather than set to zero, once every frame's
        mask has been given, or None where it is set to zero."""
        if self._negative and not self._error:
            return VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME
        if self._zeroed > DOSE_FRACTION * self._greatest:
            return VisualFeaturesReason.DOSE_IN_FACE_BLOCK
        return None


def _numbers(dataset: pydicom.Dataset, keyword: str, count: int) -> tuple[float, ...]:
    """An attribute's ``count`` finite values.

    Raises
    ------
    ValueError
        If it is absent, or its values are not ``count`` finite numbers.
    """
    value = dataset[keyword].value
    values = (
        tuple(float(v) for v in value)
        if isinstance(value, (list, tuple, pydicom.multival.MultiValue))
        else (float(value),)
    )
    if len(values) != count or not all(math.isfinite(v) for v in values):
        raise ValueError("not finite numbers")
    return values


def _check_directions(orientation: tuple[float, ...]) -> None:
    """Check that Image Orientation (Patient) is two orthogonal unit
    vectors, within :data:`_UNIT`, as PS3.3 C.7.6.2.1.1 requires.

    Raises
    ------
    ValueError
        Where it is not.
    """
    along_row = np.asarray(orientation[:3], dtype=float)
    down_column = np.asarray(orientation[3:], dtype=float)
    # Written so that a value that is not a number fails it too.
    if not (
        abs(float(np.linalg.norm(along_row)) - 1) <= _UNIT
        and abs(float(np.linalg.norm(down_column)) - 1) <= _UNIT
        and abs(float(along_row @ down_column)) <= _UNIT
    ):
        raise ValueError("direction cosines not orthogonal unit vectors")


def _check_reach(
    origins: tuple[tuple[float, float, float], ...],
    orientation: tuple[float, ...],
    spacing: tuple[float, ...],
    layout: Layout,
) -> None:
    """Check that the grid's spacing, and each corner of each of its
    frames, are within :data:`_FARTHEST`.

    Raises
    ------
    ValueError
        Where they are not.
    """
    across = (layout.columns - 1) * spacing[1] * np.asarray(orientation[:3])
    down = (layout.rows - 1) * spacing[0] * np.asarray(orientation[3:])
    corners = np.asarray(origins, dtype=float)[:, None, :] + np.array(
        [np.zeros(3), across, down, across + down]
    )
    # Written so that a value that is not a number fails it too.
    if not (
        np.all(np.abs(corners) <= _FARTHEST)
        and all(abs(value) <= _FARTHEST for value in spacing)
    ):
        raise ValueError("grid beyond the bound")


def _origins(
    position: tuple[float, ...],
    orientation: tuple[float, ...],
    offsets: tuple[float, ...],
) -> tuple[tuple[float, float, float], ...]:
    """The position of each frame's first voxel, from the grid's Image
    Position (Patient), Image Orientation (Patient), and Grid Frame Offset
    Vector, as PS3.3 C.8.8.3.2 defines them.

    Raises
    ------
    ValueError
        Where the offsets are neither relative nor allowed as absolute.
    """
    origin = np.asarray(position, dtype=float)
    if offsets[0] == 0:
        normal = np.cross(orientation[:3], orientation[3:])
        frames = [origin + offset * normal for offset in offsets]
    elif (
        np.allclose(orientation, _AXIAL, rtol=0, atol=1e-6)
        and abs(offsets[0] - position[2]) <= _SAME_Z
    ):
        frames = [np.array([origin[0], origin[1], offset]) for offset in offsets]
    else:
        raise ValueError("offsets neither relative nor absolute")
    return tuple((float(x), float(y), float(z)) for x, y, z in frames)
