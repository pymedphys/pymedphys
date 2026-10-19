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
cranial cavity that defacing keeps, on the grid's own geometry
(:class:`RtDoseDefacer`), and never recalculates it. A voxel is in the
region where its centre is in the block, and is kept where the nearest
pixel of the nearest slice that the block reaches, within half the slices'
spacing, is one that defacing keeps (:class:`DoseBlock`); a voxel beyond
the slices is not kept.

The grid is placed by Image Position (Patient), Image Orientation
(Patient), Pixel Spacing, and Grid Frame Offset Vector, as PS3.3 C.8.8.3.2
defines: offsets along the normal from the first frame's position where the
first offset is zero, or, only for an orientation of (1, 0, 0, 0, 1, 0)
whose first offset is the position's z, the frames' z coordinates. A grid
placed otherwise, whose direction cosines are not two orthogonal unit
vectors, as PS3.3 C.7.6.2.1.1 requires, within :data:`_UNIT`, compressed,
of more than one sample, or with a negative stored value, as an RT Dose of Dose Type ERROR can hold, is not set to
zero, and stays held as an instance in a defaced frame
(:attr:`~.reasons.VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME`).

Setting dose to zero must never take dose from a target that the
structure set does not mark, since RT ROI Interpreted Type is Type 2, nor
dose that matters, so where the greatest dose that it would set to zero is
more than :data:`DOSE_FRACTION` of the grid's greatest, nothing is set to
zero, and the instance is held for review instead
(:attr:`~.reasons.VisualFeaturesReason.DOSE_IN_FACE_BLOCK`). The fraction is
of the grid's own maximum rather than of the prescription, which only an RT
Plan that may not be in the run holds. Dose Grid Scaling multiplies every
stored value alike, so the stored values are compared.

Only an RT Dose that names exactly one Frame of Reference, in which exactly
one series is defaced, is set to zero (:func:`find_dose_blocks`). Any other
RT Dose in a defaced frame, naming none, or referring to a defaced slice
stays held, as :class:`~.face_blocks.Defaced` holds it, as does one set to
zero that refers to a defaced slice of another series. An RT Dose without
pixel data, which holds only dose-volume histograms, shows no face, and is
not held for its frame. Its dose-volume histograms and any other RT Dose's
are kept as they are, as the dose-volume histograms of the voxels before
any were set to zero.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Mapping

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from .defacing import FaceBlock
from .diagnostics import redacted_diagnostics
from .face_blocks import (
    CT_IMAGE,
    Defaced,
    KeptSlice,
    SeriesDefacing,
    frames_of,
    kept_slices,
)
from .pixel_cleaning import FrameMask, PixelDataRefused, layout_of
from .reasons import TransformReason, VisualFeaturesReason
from .references import InstanceRecord

RT_DOSE = "RT Dose"
# The greatest fraction of the grid's maximum dose that the run sets to zero
# in the face block. A placeholder, to be set by validation.
DOSE_FRACTION = 0.05
# How far, in millimetres, an absolute Grid Frame Offset Vector's first
# offset may lie from Image Position (Patient)'s z.
_SAME_Z = 1e-3
# How far each direction cosine vector's length may lie from 1, and their
# dot product from 0. Cosines written to six decimal places lie well within
# it, and over a grid 500 mm across it moves a voxel by no more than 0.05 mm.
_UNIT = 1e-4
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
        Each slice of the series that the block reaches.
    instances : frozenset of str
        The SOP Instance UID of each slice of the series.
    """

    block: FaceBlock
    slices: tuple[KeptSlice, ...]
    instances: frozenset[str] = frozenset()

    def __repr__(self) -> str:
        return f"DoseBlock(slices={len(self.slices)})"

    def holds(self, defaced: Defaced, record: InstanceRecord) -> bool:
        """Whether an RT Dose set to zero in the block is still held for a
        defaced frame: it refers to a defaced slice of another series, as
        :meth:`~.face_blocks.Defaced.holds` would hold it for."""
        return any(
            reference.target in defaced.instances
            and reference.target not in self.instances
            for reference in record.references
        )

    def kept(self, points: np.ndarray) -> np.ndarray:
        """Whether defacing keeps the nearest pixel of the nearest slice to
        each point, within half the slices' spacing.

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
        kept = np.zeros(len(points), dtype=bool)
        if not self.slices or not len(points):
            return kept
        orientation = self.slices[0].orientation
        normal = np.cross(orientation[:3], orientation[3:])
        heights = np.array([np.dot(each.position, normal) for each in self.slices])
        order = np.argsort(heights)
        heights = heights[order]
        steps = np.diff(heights)
        steps = steps[steps > 0]
        # A single slice is taken to span no more than its own pixels.
        reach = (
            float(np.min(steps)) / 2 if len(steps) else max(self.slices[0].spacing) / 2
        )
        along = points @ normal
        nearest = np.clip(np.searchsorted(heights, along), 1, max(len(heights) - 1, 1))
        if len(heights) > 1:
            below = np.abs(along - heights[nearest - 1])
            above = np.abs(along - heights[nearest])
            nearest = np.where(below <= above, nearest - 1, nearest)
        else:
            nearest = np.zeros(len(points), dtype=int)
        near = np.abs(along - heights[nearest]) <= reach
        for index in np.unique(nearest[near]):
            each = self.slices[order[index]]
            chosen = near & (nearest == index)
            offset = points[chosen] - np.asarray(each.position)
            columns = np.rint(
                offset @ np.asarray(each.orientation[:3]) / each.spacing[1]
            )
            rows = np.rint(offset @ np.asarray(each.orientation[3:]) / each.spacing[0])
            height, width = each.kept.shape
            within = (rows >= 0) & (rows < height) & (columns >= 0) & (columns < width)
            found = np.zeros(len(rows), dtype=bool)
            found[within] = each.kept[
                rows[within].astype(int), columns[within].astype(int)
            ]
            kept[chosen] = found
        return kept


def find_dose_blocks(
    records: Mapping[int, InstanceRecord],
    read: Callable[[int], bytes | None],
    outcomes: Mapping[str, SeriesDefacing],
) -> dict[str, DoseBlock]:
    """Return the block of each Frame of Reference whose RT Dose instances
    the run sets to zero there, by its UID.

    That is each frame in which exactly one series is defaced, as
    :func:`~.face_blocks.find_face_blocks`' ``outcomes`` give them, and
    which an RT Dose of the run names as its only frame. A frame whose
    series' slices can no longer be read has none, so that its RT Dose
    instances stay held.
    """
    defaced: dict[str, list[str]] = {}
    for uid, outcome in outcomes.items():
        if outcome.frame is not None and outcome.block is not None:
            defaced.setdefault(outcome.frame, []).append(uid)
    named = set()
    for record in records.values():
        if record.iod == RT_DOSE:
            frames = frames_of(record)
            if len(frames) == 1:
                named |= frames
    blocks = {}
    for frame in sorted(named):
        if len(defaced.get(frame, ())) != 1:
            continue
        (uid,) = defaced[frame]
        block = outcomes[uid].block
        assert block is not None
        positions = sorted(
            position
            for position, record in records.items()
            if record.iod == CT_IMAGE and record.series == uid
        )
        instances = frozenset(
            uid
            for position in positions
            if (uid := records[position].sop_instance) is not None
        )
        try:
            blocks[frame] = DoseBlock(
                block, kept_slices(block, positions, read), instances
            )
        except ValueError:
            continue
    return blocks


class RtDoseDefacer:
    """Gives the region of each frame of an RT Dose grid to set to zero, for
    :func:`~pymedphys._dicom.deidentify.pixel_cleaning.black_out`, and
    whether the dose there is too great to set to zero.

    Parameters
    ----------
    dose : DoseBlock
        The block of the grid's Frame of Reference.
    dataset : pydicom.Dataset
        The RT Dose's data set.

    Raises
    ------
    PixelDataRefused
        With :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` where
        the grid is not one that the module sets to zero.
    """

    def __init__(self, dose: DoseBlock, dataset: pydicom.Dataset) -> None:
        try:
            layout = layout_of(dataset)
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
            self._origins = _origins(position, orientation, offsets)
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
        self._greatest = 0
        self._zeroed = 0
        self._negative = False

    def __repr__(self) -> str:
        return "RtDoseDefacer()"

    def mask(self, frame: int, stored: np.ndarray) -> FrameMask | None:
        """Return the voxels of one frame to set to zero, as the module
        describes, or None where the frame has none."""
        stored = np.asarray(stored)
        if stored.size:
            self._greatest = max(self._greatest, int(stored.max()))
            self._negative |= bool(int(stored.min()) < 0)
        inside = self._dose.block.slice_mask(
            self._origins[frame], self._orientation, self._spacing, self._shape
        )
        if inside.any():
            rows, columns = np.nonzero(inside)
            points = (
                np.asarray(self._origins[frame])
                + columns[:, None]
                * self._spacing[1]
                * np.asarray(self._orientation[:3])
                + rows[:, None] * self._spacing[0] * np.asarray(self._orientation[3:])
            )
            inside[rows, columns] = ~self._dose.kept(points)
        if not inside.any():
            return None
        self._zeroed = max(self._zeroed, int(stored[inside].max()))
        return FrameMask(frame, inside, 0)

    @property
    def held(self) -> VisualFeaturesReason | None:
        """Why the grid is held rather than set to zero, once every frame's
        mask has been given, or None where it is set to zero."""
        if self._negative:
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
    if (
        abs(float(np.linalg.norm(along_row)) - 1) > _UNIT
        or abs(float(np.linalg.norm(down_column)) - 1) > _UNIT
        or abs(float(along_row @ down_column)) > _UNIT
    ):
        raise ValueError("direction cosines not orthogonal unit vectors")


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
