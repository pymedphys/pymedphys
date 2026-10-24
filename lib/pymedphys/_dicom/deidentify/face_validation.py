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

"""The face block and CT defacing, checked against reference masks (D-054).

Under the Clean Recognizable Visual Features Option, a run writes air into
the face block of each CT series in which it finds one
(:mod:`~pymedphys._dicom.deidentify.face_blocks`). This module runs the
same code on CT volumes that come with reference masks of the eyes and
other organs, as the HaN-Seg data set's head and neck planning CTs do
(:func:`check_hanseg`), and counts how the block that it finds, and the
air that it writes, compare with the masks.

Each CT volume (:class:`~pymedphys._dicom.deidentify.nrrd.Volume`) is given
to :func:`~pymedphys._dicom.deidentify.face_blocks.find_face_blocks` as the
CT Image instances of one series, one for each slice along the volume's
third axis, written in memory with the volume's geometry, its values,
rounded, as stored values in Hounsfield units, and no Pixel Padding Value,
so that the finder sees what a run sees of such a series, slices within
:data:`~pymedphys._dicom.deidentify.face_blocks.HEAD_REACH` of the superior
end included. Where it finds a block, each slice is given to
:class:`~pymedphys._dicom.deidentify.face_blocks.CtDefacer`, which gives
the pixels that a run writes as air. Each mask is placed on the CT's voxels
by its own geometry, each of its voxels at the CT voxel nearest its centre,
so that a mask need not share the CT's grid. Of each case
(:class:`CaseMeasures`), it measures:

- the finder's outcome, by the reason that a run counts in its release
  report;
- where the reference eyes, the masks of each eye's parts that the data set
  names, are given: the distance from each globe found to the centroid of
  that eye's voxels; whether the finder took the patient's right for their
  left; the distance from the farther of the eyes' voxels to the nearer
  globe found, which a run compares with
  :data:`~pymedphys._dicom.deidentify.face_blocks.EYE_REACH` for an eye
  ROI, and so whether a run given the eyes as ROIs would hold the series;
  and the height of the eyes' lowest voxel above the block's inferior
  limit;
- the eyes' own size, as the diameter of a sphere of each eye's volume,
  their separation across the axial plane, and the turn of the line between
  them from the patient's left-right axis, which describe the data set
  whatever the finder found, against
  :data:`~pymedphys._dicom.deidentify.defacing.GLOBE_DIAMETER`,
  :data:`~pymedphys._dicom.deidentify.defacing.GLOBE_SEPARATION`, and
  :data:`~pymedphys._dicom.deidentify.defacing.MAXIMUM_TURN`; and
- the share of each organ's voxels written as air.

The cases' measures are summarised (:func:`summarise`) as counts: of cases
by outcome and by format, and of measures in fixed bins, never a value or a
case's name, so that the summary can be published from a run on real
patients' scans. A case that cannot be measured is counted by why, and one
whose measuring raises anything else by the exception's type and the place
in the code that raised it, never its message, which could quote a value.

Nothing here renders a surface or tests whether a face can be recognised;
the data set's masks include no targets, so the hold for a target in the
block is not tested.
"""

from __future__ import annotations

import collections
import dataclasses
import functools
import hashlib
import importlib.metadata
import io
import math
import pathlib
import platform
import re
import traceback
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import defacing, face_blocks, nrrd
from .face_blocks import CtDefacer, find_face_blocks
from .references import InstanceRecord
from .source import EXPLICIT_VR_LITTLE_ENDIAN

FORMAT = "pymedphys-deid-face-validation/1"
CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
# Hounsfield units at or below which a voxel counts as air, for the check
# that a volume's values are in Hounsfield units, and the share of voxels
# that must be: a head CT's field of view holds far more air than this.
_AIR = -900
_AIR_SHARE = 0.01
# The masks of each eye's parts, the patient's right first, in HaN-Seg.
HANSEG_EYES = (("Eye_AR", "Eye_PR"), ("Eye_AL", "Eye_PL"))
HANSEG = {
    "name": "HaN-Seg",
    "version": "1.0",
    "doi": "10.5281/zenodo.7442914",
    "licence": "CC BY-NC-ND 4.0",
    "citation": (
        "G. Podobnik, P. Strojan, P. Peterlin, B. Ibragimov, T. Vrtovec, "
        '"HaN-Seg: The head and neck organ-at-risk CT & MR segmentation '
        'dataset", Medical Physics, 2023, doi:10.1002/mp.16197'
    ),
}
_HANSEG_CT = re.compile(r"(?:.*/)?(case_[0-9]+)/\1_IMG_CT\.nrrd")
_HANSEG_ORGAN = re.compile(r"(?:.*/)?(case_[0-9]+)/\1_OAR_(\w+)\.seg\.nrrd")
_SEGMENT = re.compile(r"Segment([0-9]+)_ID")


@dataclasses.dataclass(frozen=True)
class Bins:
    """Fixed bins of a measure, for counts that name no value.

    Each bin holds the values from one edge up to the next, the last from
    the last edge up, and, where ``below``, the first those below the
    first edge.
    """

    unit: str
    edges: tuple[float, ...]
    below: bool = False

    def counts(self, values: Iterable[float]) -> dict[str, Any]:
        """Count the values in each bin, as ``from``, ``to``, and
        ``count``, with ``None`` for an open end.

        Raises
        ------
        ValueError
            For a value that no bin holds: one that is not a number, or,
            without ``below``, one below the first edge. The message quotes
            no value.
        """
        lows: list[float | None] = [None] if self.below else []
        lows += list(self.edges)
        highs: list[float | None] = [*lows[1:], None]
        counts = [0] * len(lows)
        for value in values:
            if math.isnan(value) or not (self.below or value >= self.edges[0]):
                raise ValueError("A value is in no bin.")
            counts[sum(1 for low in lows if low is None or value >= low) - 1] += 1
        return {
            "unit": self.unit,
            "bins": [
                {"from": low, "to": high, "count": count}
                for low, high, count in zip(lows, highs, counts)
            ],
        }


GLOBE_ERROR = Bins("mm", (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 7.5, 10.0, 15.0))
EYE_REACH = Bins("mm", (0.0, 12.5, 15.0, 17.5, 20.0, 22.5, 25.0, 27.5, 30.0))
EYES_ABOVE_LIMIT = Bins("mm", (-5.0, -2.0, 0.0, 2.0, 5.0, 10.0, 20.0), below=True)
GLOBE_DIAMETER = Bins("mm", (16.0, 20.0, 22.0, 24.0, 26.0, 28.0, 30.0), below=True)
GLOBE_SEPARATION = Bins("mm", (40.0, 50.0, 55.0, 60.0, 65.0, 70.0, 80.0), below=True)
TURN = Bins("degrees", (0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0))
PIXEL_SPACING = Bins("mm", (0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0))
SLICE_SPACING = Bins("mm", (0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0))
# The share of an organ's voxels written as air.
SHARES = (
    "none",
    "under 10%",
    "10% to under 50%",
    "50% to under 90%",
    "90% to under 100%",
    "all",
)


class FaceValidationRefused(Exception):
    """A data set that cannot be checked; the message quotes no value."""


@dataclasses.dataclass(frozen=True, repr=False)
class CaseMeasures:
    """What one case shows, for :func:`summarise` alone.

    Its ``repr`` shows nothing of it, and nothing of it but the counts that
    :func:`summarise` makes is to be written, printed, or logged.

    Attributes
    ----------
    outcome : str
        ``"defaced"``, or the reason that a run counts for a series that it
        does not deface, such as ``"no-eyes"``.
    ct_format : str
        How the CT was stored (:class:`~.nrrd.NrrdFormat`).
    air : bool
        Whether at least 1% of the CT's voxels are at -900 Hounsfield units
        or below, as a head CT's are where its values are in Hounsfield
        units.
    pixel_spacing, slice_spacing : float
        The larger spacing within a slice, and between slices, in
        millimetres.
    eyes : str or None
        Where the series is defaced: ``"agree"`` where every voxel of the
        reference eyes is within EYE_REACH of the nearer globe found,
        ``"eyes-disagree-with-rois"`` where one is not, as a run would hold
        the series, or ``"no-reference-eyes"``; otherwise None.
    globe_errors : tuple of float
        Where the series is defaced and the reference eyes are given: the
        distance from each globe found, the patient's right first, to the
        centroid of that eye's voxels, in millimetres; otherwise empty.
    sides_swapped : bool or None
        Whether each globe found is nearer the other eye's centroid, taken
        together, than its own; None where not measured.
    eye_reach : float or None
        The distance from the reference eyes' voxel farthest from the nearer
        globe found to that globe, in millimetres.
    eyes_above_limit : float or None
        The height of the reference eyes' lowest voxel centre above the
        block's inferior limit, in millimetres.
    diameters : tuple of float
        Where the reference eyes are given: the diameter of a sphere of
        each eye's volume, the patient's right first, in millimetres.
    separation, turn : float or None
        The distance between the eyes' centroids across the axial plane, in
        millimetres, and the angle of the line between them from the
        patient's left-right axis, in degrees.
    written : mapping of str to float
        Where the series is defaced: the share of each organ's voxels
        written as air, by the organ's mask's name.
    mask_formats, mask_problems : mapping of str to int
        How many masks were stored in each format, and how many were not
        read, by why.
    masks_outside : int
        How many masks have a voxel outside the CT, which is left out.
    """

    outcome: str
    ct_format: str
    air: bool
    pixel_spacing: float
    slice_spacing: float
    eyes: str | None = None
    globe_errors: tuple[float, ...] = ()
    sides_swapped: bool | None = None
    eye_reach: float | None = None
    eyes_above_limit: float | None = None
    diameters: tuple[float, ...] = ()
    separation: float | None = None
    turn: float | None = None
    written: Mapping[str, float] = dataclasses.field(default_factory=dict)
    mask_formats: Mapping[str, int] = dataclasses.field(default_factory=dict)
    mask_problems: Mapping[str, int] = dataclasses.field(default_factory=dict)
    masks_outside: int = 0

    def __repr__(self) -> str:
        return "CaseMeasures()"


@dataclasses.dataclass(frozen=True)
class CaseNotMeasured:
    """A case that was not measured, for why.

    Attributes
    ----------
    reason : str
        A code, such as ``"ct-missing"``, or ``"ct-not-read"`` and an
        :class:`~.nrrd.NrrdProblem`'s value, such as
        ``"ct-not-read/data-length"``, or ``"crashed"``.
    where : str or None
        For ``"crashed"``, the exception's type and the place in the code
        that raised it, such as ``"ValueError at nrrd.py:120 in _vector"``.
    """

    reason: str
    where: str | None = None


class _NotMeasured(Exception):
    """A case that cannot be measured, for :attr:`reason`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def measure_case(
    ct: nrrd.Volume,
    organs: Mapping[str, Callable[[], nrrd.Volume]],
    eyes: tuple[Sequence[str], Sequence[str]] = HANSEG_EYES,
) -> CaseMeasures:
    """Measure one case, as the module describes.

    Parameters
    ----------
    ct : Volume
        The CT, in Hounsfield units.
    organs : mapping of str to callable
        Each reference mask's loader, by the mask's name; each is loaded
        once, in turn, so that one mask at a time is in memory.
    eyes : tuple of two sequences of str
        The names of the masks of each eye's parts, the patient's right
        first.

    Raises
    ------
    _NotMeasured
        For a CT that is not of three dimensions, or whose values cannot be
        stored as integers.
    """
    stored = _stored(ct.values)
    series = _Series(ct, stored)
    outcome = series.outcome()
    block = outcome.block
    written = None if block is None else series.written(block)
    voxels, formats, problems, outside = _organ_voxels(ct, organs)
    measures: dict[str, Any] = {
        "outcome": "defaced" if block is not None else _code(outcome.problem),
        "ct_format": str(ct.format),
        "air": bool(np.count_nonzero(stored <= _AIR) >= _AIR_SHARE * stored.size),
        "pixel_spacing": float(max(np.linalg.norm(ct.axes[:2], axis=1))),
        "slice_spacing": _slice_spacing(ct.axes),
        "mask_formats": dict(sorted(formats.items())),
        "mask_problems": dict(sorted(problems.items())),
        "masks_outside": outside,
    }
    sides = [_union(voxels, names) for names in eyes]
    reference = None
    if all(side is not None and len(side) for side in sides):
        reference = [ct.positions(side) for side in sides if side is not None]
        measures.update(_reference_geometry(reference, _voxel_volume(ct.axes)))
    if block is not None and written is not None:
        measures["written"] = {
            name: float(np.mean(written[tuple(indices.T)]))
            for name, indices in voxels.items()
            if len(indices)
        }
        measures["eyes"] = "no-reference-eyes"
        if reference is not None:
            measures.update(_against_block(block, reference))
    return CaseMeasures(**measures)


def _code(problem: object) -> str:
    """The reason code of a series' problem."""
    value = getattr(problem, "value", None)
    return value if isinstance(value, str) else "unknown"


def _stored(values: np.ndarray) -> np.ndarray:
    """A CT's values, rounded, as 16-bit integers where they fit, or else
    32-bit, by slice, row, and column."""
    if values.ndim != 3:
        raise _NotMeasured("ct-not-three-dimensional")
    if values.dtype.kind == "f":
        if not np.isfinite(values).all():
            raise _NotMeasured("ct-values-not-finite")
        values = np.rint(values)
    elif values.dtype.kind not in "iu":
        raise _NotMeasured("ct-values-not-numbers")
    low, high = values.min(), values.max()
    for kind in (np.int16, np.int32):
        limits = np.iinfo(kind)
        if limits.min <= low and high <= limits.max:
            return values.astype(kind, copy=False)
    raise _NotMeasured("ct-values-out-of-range")


def _slice_spacing(axes: np.ndarray) -> float:
    """The distance between slices along the normal to their plane, in
    millimetres."""
    normal = np.cross(axes[0], axes[1])
    return float(abs(axes[2] @ normal) / np.linalg.norm(normal))


def _voxel_volume(axes: np.ndarray) -> float:
    """A voxel's volume, in cubic millimetres."""
    return float(abs(np.linalg.det(axes)))


@functools.cache
def _uids() -> tuple[str, str, str]:
    """The Study Instance, Series Instance, and Frame of Reference UIDs that
    every volume's slices are given: they stay in memory, so one set
    serves."""
    study, series, frame = (
        str(pydicom.uid.generate_uid(None, entropy_srcs=["face validation", part]))
        for part in ("study", "series", "frame")
    )
    return study, series, frame


class _Series:
    """A CT volume as the CT Image instances of one series, one for each
    slice along its third axis, written in memory."""

    def __init__(self, ct: nrrd.Volume, stored: np.ndarray) -> None:
        along_row, down_column, across = ct.axes
        self._stored = stored
        self._orientation = [
            _decimal(value)
            for value in (
                *(along_row / np.linalg.norm(along_row)),
                *(down_column / np.linalg.norm(down_column)),
            )
        ]
        self._spacing = [
            _decimal(np.linalg.norm(down_column)),
            _decimal(np.linalg.norm(along_row)),
        ]
        self._positions = [
            [_decimal(value) for value in ct.origin + index * across]
            for index in range(len(stored))
        ]

    def outcome(self) -> face_blocks.SeriesDefacing:
        """The series' outcome, as a run finds it."""
        records = {
            index: InstanceRecord.from_file(self.file(index))
            for index in range(len(self._stored))
        }
        # One series: every slice has the same Series Instance UID.
        (outcome,) = list(find_face_blocks(records, self.file).values())
        return outcome

    def written(self, block: defacing.FaceBlock) -> np.ndarray:
        """The voxels that a run writes as air, of bool, by slice, row, and
        column."""
        written = np.zeros(self._stored.shape, dtype=bool)
        for index, stored in enumerate(self._stored):
            mask = CtDefacer(block, self.dataset(index)).mask(0, stored)
            if mask is not None:
                written[index] = mask.mask
        return written

    def dataset(self, index: int) -> pydicom.Dataset:
        """A slice's data set, without its Pixel Data."""
        study, series, frame = _uids()
        instance = f"{series}.{index + 1}"
        dataset = pydicom.Dataset()
        dataset.SOPClassUID = CT_IMAGE_STORAGE
        dataset.SOPInstanceUID = instance
        dataset.StudyInstanceUID = study
        dataset.SeriesInstanceUID = series
        dataset.FrameOfReferenceUID = frame
        dataset.Modality = "CT"
        dataset.InstanceNumber = index + 1
        dataset.ImagePositionPatient = self._positions[index]
        dataset.ImageOrientationPatient = self._orientation
        dataset.PixelSpacing = self._spacing
        dataset.Rows, dataset.Columns = self._stored.shape[1:]
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = "MONOCHROME2"
        bits = self._stored.dtype.itemsize * 8
        dataset.BitsAllocated = bits
        dataset.BitsStored = bits
        dataset.HighBit = bits - 1
        dataset.PixelRepresentation = 1
        dataset.RescaleIntercept = "0"
        dataset.RescaleSlope = "1"
        meta = pydicom.dataset.FileMetaDataset()
        meta.MediaStorageSOPClassUID = CT_IMAGE_STORAGE
        meta.MediaStorageSOPInstanceUID = instance
        meta.TransferSyntaxUID = EXPLICIT_VR_LITTLE_ENDIAN
        dataset.file_meta = meta
        return dataset

    def file(self, index: int) -> bytes:
        """A slice's file, Explicit VR Little Endian."""
        dataset = self.dataset(index)
        words = self._stored[index]
        dataset.PixelData = words.astype(words.dtype.newbyteorder("<")).tobytes()
        dataset["PixelData"].VR = "OW"
        buffer = io.BytesIO()
        dataset.save_as(buffer, enforce_file_format=True)
        return buffer.getvalue()


def _decimal(value: float) -> str:
    """A Decimal String of up to 16 characters."""
    return pydicom.valuerep.format_number_as_ds(float(value))


def _organ_voxels(
    ct: nrrd.Volume, organs: Mapping[str, Callable[[], nrrd.Volume]]
) -> tuple[
    dict[str, np.ndarray], collections.Counter[str], collections.Counter[str], int
]:
    """Each organ's voxels on the CT, by its name, with how many masks were
    stored in each format, how many were not read, by why, and how many
    have a voxel outside the CT."""
    voxels = {}
    formats: collections.Counter[str] = collections.Counter()
    problems: collections.Counter[str] = collections.Counter()
    outside = 0
    for name, load in organs.items():
        try:
            mask = load()
            indices, dropped = _on_ct(ct, _segment(mask))
        except nrrd.NrrdRefused as refused:
            problems[refused.problem.value] += 1
            continue
        except _NotMeasured as unusable:
            problems[unusable.reason] += 1
            continue
        formats[str(mask.format)] += 1
        outside += dropped > 0
        voxels[name] = indices
    return voxels, formats, problems, outside


def _segment(mask: nrrd.Volume) -> nrrd.Volume:
    """A mask's one segment, as a volume of bool on the mask's grid.

    A 3D Slicer segmentation names each segment's label value and layer by
    its key/value pairs; any other mask's segment is its voxels that are
    not zero, in any layer.

    Raises
    ------
    _NotMeasured
        For a mask of more than one segment, or a segment whose label value
        or layer cannot be read.
    """
    numbers = {
        match[1]
        for key in mask.key_values
        if (match := _SEGMENT.fullmatch(key)) is not None
    }
    values = mask.values
    if len(numbers) > 1:
        raise _NotMeasured("several-segments")
    if numbers:
        (number,) = numbers
        label = mask.key_values.get(f"Segment{number}_LabelValue", "1").strip()
        layer = mask.key_values.get(f"Segment{number}_Layer", "0").strip()
        if not (label.isdigit() and layer.isdigit()):
            raise _NotMeasured("segment-not-read")
        if values.ndim == 4:
            if int(layer) >= values.shape[3]:
                raise _NotMeasured("segment-not-read")
            values = values[..., int(layer)]
        selected = values == int(label)
    else:
        selected = values != 0
        if selected.ndim == 4:
            selected = selected.any(axis=3)
    return dataclasses.replace(mask, values=selected)


def _on_ct(ct: nrrd.Volume, segment: nrrd.Volume) -> tuple[np.ndarray, int]:
    """The slice, row, and column of the CT voxel nearest each of a
    segment's voxels, once each, and how many of its voxels lie outside the
    CT."""
    indices = np.argwhere(segment.values)
    same = (
        segment.shape == ct.shape
        and np.allclose(segment.origin, ct.origin, rtol=0, atol=1e-6)
        and np.allclose(segment.axes, ct.axes, rtol=0, atol=1e-6)
    )
    if not same:
        indices = np.rint(ct.indices(segment.positions(indices))).astype(np.int64)
    inside = ((indices >= 0) & (indices < np.array(ct.shape))).all(axis=1)
    return np.unique(indices[inside], axis=0), int(np.count_nonzero(~inside))


def _union(voxels: Mapping[str, np.ndarray], names: Sequence[str]) -> np.ndarray | None:
    """The voxels of all of these organs, once each, or None where one is
    not given."""
    if not all(name in voxels for name in names):
        return None
    return np.unique(np.concatenate([voxels[name] for name in names]), axis=0)


def _reference_geometry(
    eyes: Sequence[np.ndarray], voxel_volume: float
) -> dict[str, Any]:
    """The reference eyes' sizes, separation, and turn, from each eye's
    voxels' positions, the patient's right first."""
    right, left = (np.mean(each, axis=0) for each in eyes)
    across = left[:2] - right[:2]
    return {
        "diameters": tuple(
            float((6 * len(each) * voxel_volume / math.pi) ** (1 / 3)) for each in eyes
        ),
        "separation": float(np.linalg.norm(across)),
        "turn": float(abs(math.degrees(math.atan2(across[1], across[0])))),
    }


def _against_block(
    block: defacing.FaceBlock, eyes: Sequence[np.ndarray]
) -> dict[str, Any]:
    """How the block found compares with the reference eyes, from each
    eye's voxels' positions, the patient's right first."""
    globes = np.asarray(block.globes, dtype=float)
    centroids = np.array([np.mean(each, axis=0) for each in eyes])
    errors = np.linalg.norm(globes - centroids, axis=1)
    swapped = np.linalg.norm(globes - centroids[::-1], axis=1)
    points = np.concatenate(eyes)
    nearest = np.min(np.linalg.norm(points[:, np.newaxis, :] - globes, axis=2), axis=1)
    reach = float(np.max(nearest))
    return {
        "eyes": (
            "agree"
            if reach <= face_blocks.EYE_REACH
            else face_blocks.SeriesProblem.EYES_DISAGREE.value
        ),
        "globe_errors": tuple(float(each) for each in errors),
        "sides_swapped": bool(swapped.sum() < errors.sum()),
        "eye_reach": reach,
        "eyes_above_limit": float(np.min(points[:, 2]) - block.inferior_limit),
    }


def summarise(
    cases: Sequence[CaseMeasures | CaseNotMeasured], data: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the cases' counts, as the module describes, for JSON.

    Parameters
    ----------
    cases : sequence of CaseMeasures or CaseNotMeasured
    data : mapping
        What names the data set and its file: its name, version, DOI,
        licence, and citation, and its file's size, MD5, and SHA-256.
    """
    measured = [case for case in cases if isinstance(case, CaseMeasures)]
    not_measured = [case for case in cases if isinstance(case, CaseNotMeasured)]
    defaced = [case for case in measured if case.outcome == "defaced"]
    against = [case for case in defaced if case.eye_reach is not None]
    with_eyes = [case for case in measured if case.diameters]
    organs = sorted({name for case in defaced for name in case.written})
    return {
        "format": FORMAT,
        "data": dict(data),
        "software": _software(),
        "settings": _settings(),
        "cases": {
            "total": len(cases),
            "measured": len(measured),
            "not_measured": _counted(case.reason for case in not_measured),
            "crashed": _counted(
                case.where or "" for case in not_measured if case.where
            ),
        },
        "ct": {
            "formats": _counted(case.ct_format for case in measured),
            "air_in_hounsfield_units": {
                "yes": sum(case.air for case in measured),
                "no": sum(not case.air for case in measured),
            },
            "pixel_spacing": PIXEL_SPACING.counts(
                case.pixel_spacing for case in measured
            ),
            "slice_spacing": SLICE_SPACING.counts(
                case.slice_spacing for case in measured
            ),
        },
        "masks": {
            "formats": _added(case.mask_formats for case in measured),
            "not_read": _added(case.mask_problems for case in measured),
            "partly_outside_ct": sum(case.masks_outside for case in measured),
        },
        "series": {
            "defaced": len(defaced),
            "not_defaced": _counted(
                case.outcome for case in measured if case.outcome != "defaced"
            ),
        },
        "eyes_of_defaced_series": _counted(case.eyes or "" for case in defaced),
        "globe_centre_error": GLOBE_ERROR.counts(
            error for case in against for error in case.globe_errors
        ),
        "sides_swapped": sum(bool(case.sides_swapped) for case in against),
        "eye_reach": EYE_REACH.counts(_present(case.eye_reach for case in against)),
        "eyes_above_inferior_limit": EYES_ABOVE_LIMIT.counts(
            _present(case.eyes_above_limit for case in against)
        ),
        "reference_eyes": {
            "cases": len(with_eyes),
            "globe_diameter": GLOBE_DIAMETER.counts(
                diameter for case in with_eyes for diameter in case.diameters
            ),
            "globe_separation": GLOBE_SEPARATION.counts(
                _present(case.separation for case in with_eyes)
            ),
            "turn": TURN.counts(_present(case.turn for case in with_eyes)),
        },
        "written_as_air": {
            name: _shares(
                case.written[name] for case in defaced if name in case.written
            )
            for name in organs
        },
    }


def _present(values: Iterable[float | None]) -> list[float]:
    return [value for value in values if value is not None]


def _counted(codes: Iterable[str]) -> dict[str, int]:
    """How many of each code, in the codes' order."""
    return dict(sorted(collections.Counter(codes).items()))


def _added(counts: Iterable[Mapping[str, int]]) -> dict[str, int]:
    """Counts by code, added up."""
    total: collections.Counter[str] = collections.Counter()
    for each in counts:
        total.update(each)
    return dict(sorted(total.items()))


def _shares(fractions: Iterable[float]) -> dict[str, int]:
    """How many organs had each share of their voxels written as air
    (:data:`SHARES`)."""
    counts = dict.fromkeys(SHARES, 0)
    for fraction in fractions:
        if fraction <= 0:
            share = "none"
        elif fraction >= 1:
            share = "all"
        elif fraction < 0.1:
            share = "under 10%"
        elif fraction < 0.5:
            share = "10% to under 50%"
        elif fraction < 0.9:
            share = "50% to under 90%"
        else:
            share = "90% to under 100%"
        counts[share] += 1
    return counts


def _settings() -> dict[str, Any]:
    """The engine's settings that the counts depend on."""
    return {
        "head_reach_mm": face_blocks.HEAD_REACH,
        "margin_mm": defacing.MARGIN,
        "globe_diameter_mm": list(defacing.GLOBE_DIAMETER),
        "globe_separation_mm": list(defacing.GLOBE_SEPARATION),
        "maximum_turn_degrees": defacing.MAXIMUM_TURN,
        "eye_reach_mm": face_blocks.EYE_REACH,
        "cavity_floor_mm": face_blocks.CAVITY_FLOOR,
    }


def _software() -> dict[str, str]:
    """The versions of Python and of the packages that the counts depend
    on."""
    versions = {"python": platform.python_version()}
    for package in ("pymedphys", "numpy", "scipy", "pydicom"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unknown"
    return versions


def crash_site(error: BaseException) -> str:
    """An exception's type and the place in PyMedPhys's code, or failing
    that the innermost place, that raised it: never its message."""
    frames = traceback.extract_tb(error.__traceback__)
    ours = [
        frame
        for frame in frames
        if "pymedphys" in pathlib.PurePath(frame.filename).parts
    ]
    kind = type(error).__qualname__
    if not (ours or frames):
        return kind
    frame = (ours or frames)[-1]
    name = pathlib.PurePath(frame.filename).name
    return f"{kind} at {name}:{frame.lineno} in {frame.name}"


def file_digest(path: pathlib.Path) -> dict[str, Any]:
    """A file's size, in bytes, its MD5, which Zenodo gives for each file of
    a record, and its SHA-256."""
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return {
        "size": path.stat().st_size,
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


@dataclasses.dataclass(frozen=True, repr=False)
class _HanSegCase:
    """The members of one case of HaN-Seg's ZIP file."""

    ct: zipfile.ZipInfo | None
    organs: Mapping[str, zipfile.ZipInfo]


def hanseg_cases(archive: zipfile.ZipFile) -> list[_HanSegCase]:
    """The cases of HaN-Seg's ZIP file, by directory: each case's CT, and
    its organs' masks by name, as ``case_NN/case_NN_IMG_CT.nrrd`` and
    ``case_NN/case_NN_OAR_<name>.seg.nrrd`` name them. Its MR images are
    not read."""
    cts: dict[str, zipfile.ZipInfo] = {}
    organs: dict[str, dict[str, zipfile.ZipInfo]] = collections.defaultdict(dict)
    for info in archive.infolist():
        directory = info.filename.rpartition("/")[0]
        if (match := _HANSEG_CT.fullmatch(info.filename)) is not None:
            cts[directory] = info
        elif (match := _HANSEG_ORGAN.fullmatch(info.filename)) is not None:
            organs[directory][match[2]] = info
    return [
        _HanSegCase(cts.get(directory), dict(sorted(organs[directory].items())))
        for directory in sorted({*cts, *organs})
    ]


def check_hanseg(path: pathlib.Path) -> dict[str, Any]:
    """Check the face block and CT defacing against HaN-Seg's masks.

    Parameters
    ----------
    path : pathlib.Path
        HaN-Seg's ZIP file, ``HaN-Seg.zip``, from its Zenodo record.

    Returns
    -------
    dict
        :func:`summarise`'s counts of :func:`measure_hanseg`'s cases.

    Raises
    ------
    FaceValidationRefused
        As :func:`measure_hanseg` does.
    """
    cases = measure_hanseg(path)
    return summarise(cases, {**HANSEG, "file": file_digest(path)})


def measure_hanseg(path: pathlib.Path) -> list[CaseMeasures | CaseNotMeasured]:
    """Measure each case of HaN-Seg's ZIP file, in the order of their
    directories, reading each member from the ZIP file without extracting
    it.

    Raises
    ------
    FaceValidationRefused
        Where the file is not a ZIP file, or holds no case.
    """
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        raise FaceValidationRefused(
            "The data set is not a readable ZIP file."
        ) from None
    with archive:
        cases = hanseg_cases(archive)
        if not cases:
            raise FaceValidationRefused("The ZIP file holds no HaN-Seg case.")
        return [_measured(archive, case) for case in cases]


def _measured(
    archive: zipfile.ZipFile, case: _HanSegCase
) -> CaseMeasures | CaseNotMeasured:
    """One case's measures, or why it has none."""
    if case.ct is None:
        return CaseNotMeasured("ct-missing")
    try:
        try:
            ct = _read(archive, case.ct)
        except nrrd.NrrdRefused as refused:
            return CaseNotMeasured(f"ct-not-read/{refused.problem.value}")
        organs = {
            name: functools.partial(_read, archive, info)
            for name, info in case.organs.items()
        }
        return measure_case(ct, organs)
    except _NotMeasured as unusable:
        return CaseNotMeasured(unusable.reason)
    # Anything else that a case raises is counted, by where, rather than
    # stopping the check; its message, which could quote a value, is
    # dropped.
    except Exception as error:  # pylint: disable = broad-exception-caught
        return CaseNotMeasured("crashed", crash_site(error))


def _read(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> nrrd.Volume:
    with archive.open(info) as stream:
        return nrrd.read_nrrd(stream)
