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

"""The face block of each CT series of a run, and the air written there.

Under the Clean Recognizable Visual Features Option, a run finds, before it
writes any instance, the face block
(:class:`~pymedphys._dicom.deidentify.defacing.FaceBlock`) of each series of
CT Image instances (:func:`find_face_blocks`), and writes air into each
slice of a series that has one (:class:`CtDefacer`), as
:func:`~pymedphys._dicom.deidentify.pixel_cleaning.black_out` writes its
masks. A series is defaced only where all of these hold:

- every slice is read from the file that the run's first pass read, with
  native Pixel Data of one frame, one sample, and whole bytes
  (:func:`~pymedphys._dicom.deidentify.pixel_cleaning.layout_of`), and
  finite Image Position (Patient), Image Orientation (Patient), Pixel
  Spacing, Rescale Slope, and Rescale Intercept, and a readable Pixel
  Padding Value and Pixel Padding Range Limit where present;
- the slices share their orientation, rows, columns, spacing, and Frame of
  Reference UID, which they have, and the stored values of each can hold
  air, -1000 Hounsfield units, as one stored value, rounded, without
  clipping;
- :class:`~pymedphys._dicom.deidentify.defacing.FaceFinder` finds the
  block from the slices within :data:`HEAD_REACH` millimetres of the
  volume's superior end, which bounds the memory that a long volume needs;
  and
- no contour of a target, an ROI whose RT ROI Interpreted Type is
  :data:`TARGET_TYPES`, of an RT Structure Set of the run in the series'
  Frame of Reference has a point in the block, a target that names no Frame
  of Reference counting as one in it, and every such structure set can be
  read.

Anything else that a series' data raises leaves the series undefaced, as
unreadable, rather than stopping the run, and no message of it, which could
quote a value, is kept.

A series with a target in its block is not defaced, and each of its slices
is held for review (:attr:`~.reasons.VisualFeaturesReason.TARGET_IN_FACE_BLOCK`),
so that a release never loses a target to defacing unseen. Any other series
that is not defaced, such as one without a head, is written as it would be
without a block, and the face review's verdict on it decides, as for every
other instance that can show a face. The outcome of each series is counted
for the release report (:class:`FaceBlockCounts`), by series, never naming
one.

Within the block, :class:`CtDefacer` keeps each pixel of Pixel Padding
Value or its range, and each pixel inside the cranial cavity, which bone at
:data:`~pymedphys._dicom.deidentify.defacing.BONE` Hounsfield units or more
encloses within the slice, so that the brain in front of the block's plane
is kept. Padding is never taken for bone, so it cannot close a ring around
the face. The cavity is kept only more than :data:`CAVITY_FLOOR`
millimetres above the higher globe's centre, above the orbits, so that bone
enclosing an orbit within a slice, or a thin orbital roof that the slice's
bone does not seal, keeps no part of an eye. Where no bone encloses the
cavity within a slice, the block is air to the top of the slice. Where
air's stored value is itself padding, the pixels written are padding, which
a viewer shows as outside the image, as the air before the face is in most
scans.

Only CT Image instances are defaced. An RT Structure Set, RT Dose, or PET
instance (:data:`UNDEFACED_IODS`) in the Frame of Reference of a defaced
series keeps its contours or pixel data, which can still outline the face,
so it is held for review whatever its verdict, since a reviewer may have
judged it from the defaced CT's previews
(:attr:`~.reasons.VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME`), until
the run can clean it too (:class:`Defaced`). So is one that names no Frame
of Reference, in a run that defaces any series, or that refers to a defaced
slice, whatever frame it declares. A structure set that names no Frame of
Reference is likewise searched for targets in the block of every series.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import io
import math
from collections.abc import Callable, Iterable, Mapping

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import scipy

from . import defacing
from .defacing import FaceBlock, FaceBlockProblem, FaceBlockRefused
from .diagnostics import redacted_diagnostics
from .pixel_cleaning import (
    FrameMask,
    Layout,
    PixelDataRefused,
    layout_of,
    stored_range,
)
from .reasons import TransformReason
from .references import InstanceRecord
from .source import NATIVE_TRANSFER_SYNTAXES
from .uids import normalise_uid

CT_IMAGE = "CT Image"
RT_STRUCTURE_SET = "RT Structure Set"
AIR = -1000.0  # Hounsfield units
HEAD_REACH = 400.0  # millimetres below the volume's superior end
# How far above the higher globe's centre, in millimetres, the cranial
# cavity is kept: the largest globe radius that the finder accepts, half of
# GLOBE_DIAMETER's upper end, and as much again for the orbit above it. A
# placeholder, to be set by validation.
CAVITY_FLOOR = defacing.GLOBE_DIAMETER[1]
TARGET_TYPES = frozenset({"PTV", "CTV", "GTV"})
# The IODs whose instances in a defaced series' Frame of Reference the run
# does not yet clean of the face.
UNDEFACED_IODS = frozenset(
    {
        RT_STRUCTURE_SET,
        "RT Dose",
        "Positron Emission Tomography Image",
        "Enhanced PET Image",
        "Legacy Converted Enhanced PET Image",
    }
)
# How far two slices' direction cosines, or spacings in millimetres, may
# differ and still be one stack's.
_SAME = 1e-4


class SeriesProblem(enum.Enum):
    """Why a CT series is not defaced, other than a
    :class:`~pymedphys._dicom.deidentify.defacing.FaceBlockProblem`."""

    # a slice that cannot be read again, or whose geometry, rescale, or
    # pixel data cannot be read
    UNREADABLE = "unreadable"
    # Pixel Data in an encapsulated transfer syntax, which would have to be
    # encoded again
    COMPRESSED = "compressed-pixel-data"
    # slices of more than one frame, sample, orientation, size, spacing, or
    # Frame of Reference
    NOT_ONE_STACK = "not-one-stack"
    # stored values that cannot hold air without clipping
    AIR_NOT_STORED = "air-not-stored"
    # a target's contour in the block
    TARGET_IN_BLOCK = "target-in-block"


@dataclasses.dataclass(frozen=True)
class SeriesDefacing:
    """The outcome of one CT series.

    Attributes
    ----------
    block : FaceBlock or None
        The block written as air, or None where the series is not defaced.
    problem : FaceBlockProblem or SeriesProblem or None
        Why the series is not defaced, or None where it is.
    frame : str, optional
        The Frame of Reference UID of a defaced series; None for any other.
    """

    block: FaceBlock | None
    problem: FaceBlockProblem | SeriesProblem | None
    frame: str | None = None

    def __post_init__(self) -> None:
        if (self.block is None) == (self.problem is None):
            raise ValueError("a series has a block or a problem, not both")
        if (self.frame is None) != (self.block is None) or self.frame == "":
            raise ValueError("a defaced series has its Frame of Reference UID")

    @property
    def held(self) -> bool:
        """Whether the series' slices are held for review: a target lies in
        its block."""
        return self.problem is SeriesProblem.TARGET_IN_BLOCK


@dataclasses.dataclass
class FaceBlockCounts:
    """How many CT series a run defaced, and how many it did not, by why.

    Filled by :meth:`record`, once a run has found its face blocks, for the
    release report's ``face_review.ct_series``. A series counts as defaced
    where the run found its block and set out to deface it, whatever then
    became of its slices.
    """

    defaced: int = 0
    not_defaced: dict[FaceBlockProblem | SeriesProblem, int] = dataclasses.field(
        default_factory=dict
    )

    def record(self, outcomes: Iterable[SeriesDefacing]) -> None:
        """Count each series' outcome, in place of any counted before."""
        defaced = 0
        not_defaced: collections.Counter[FaceBlockProblem | SeriesProblem] = (
            collections.Counter()
        )
        for outcome in outcomes:
            if outcome.problem is None:
                defaced += 1
            else:
                not_defaced[outcome.problem] += 1
        self.defaced = defaced
        self.not_defaced = dict(not_defaced)


@dataclasses.dataclass(frozen=True)
class _Slice:
    """What defacing needs of one CT slice."""

    position: tuple[float, float, float]
    orientation: tuple[float, ...]
    spacing: tuple[float, float]
    shape: tuple[int, int]
    rescale: tuple[float, float]
    padding: tuple[int, int] | None
    air: int
    frame: str | None


class _Unusable(Exception):
    """A series that is not defaced, for :attr:`problem`."""

    def __init__(self, problem: SeriesProblem) -> None:
        super().__init__(problem.value)
        self.problem = problem


def find_face_blocks(
    records: Mapping[int, InstanceRecord],
    read: Callable[[int], bytes | None],
) -> dict[str, SeriesDefacing]:
    """Return the outcome of each series of CT Image instances, by its
    Series Instance UID.

    Parameters
    ----------
    records : mapping of int to InstanceRecord
        The run's records, by run position, as its first pass gives them.
        A CT Image instance without a Series Instance UID is not defaced,
        and has no outcome.
    read : callable
        Gives the file at a run position as the first pass read it, or None
        if it can no longer be read or has changed.
    """
    series: dict[str, list[int]] = collections.defaultdict(list)
    structure_sets: dict[str, list[int]] = collections.defaultdict(list)
    # Structure sets that name no Frame of Reference, which may be in any.
    frameless: list[int] = []
    for position, record in sorted(records.items()):
        if record.iod == CT_IMAGE and record.series is not None:
            series[record.series].append(position)
        elif record.iod == RT_STRUCTURE_SET:
            frames = frames_of(record)
            for frame in frames:
                structure_sets[frame].append(position)
            if not frames:
                frameless.append(position)
    outcomes = {}
    for uid, positions in series.items():
        outcome, frame = _series_outcome(positions, read)
        if outcome.block is not None and frame:
            searched = sorted({*structure_sets.get(frame, []), *frameless})
            if _target_in(outcome.block, frame, searched, read):
                outcome = SeriesDefacing(None, SeriesProblem.TARGET_IN_BLOCK)
        outcomes[uid] = outcome
    return outcomes


def frames_of(record: InstanceRecord) -> frozenset[str]:
    """Return every Frame of Reference UID that an instance's record names:
    its own, its structure set's referenced frames, and its ROIs'."""
    named = {
        record.frame_of_reference,
        *record.roi_frames,
        *(use.frame for use in record.frames),
    }
    return frozenset(frame for frame in named if frame)


@dataclasses.dataclass(frozen=True, repr=False)
class Defaced:
    """What a run defaces, by which it holds the instances it does not yet
    clean of the face.

    Its ``repr`` shows only the counts.

    Attributes
    ----------
    frames : frozenset of str
        The Frame of Reference UID of each defaced series.
    instances : frozenset of str
        The SOP Instance UID of each slice of a defaced series.
    """

    frames: frozenset[str] = frozenset()
    instances: frozenset[str] = frozenset()

    def __repr__(self) -> str:
        return f"Defaced(frames={len(self.frames)}, instances={len(self.instances)})"

    def holds(self, iod: str | None, record: InstanceRecord) -> bool:
        """Whether an instance is held because the run defaces its frame.

        Only an instance of :data:`UNDEFACED_IODS`, in a run that defaces a
        series, where it names a defaced series' Frame of Reference, names
        none, or refers to a defaced slice, as a structure set's Contour
        Image Sequence does, whatever frame it declares.
        """
        if not self.frames or iod not in UNDEFACED_IODS:
            return False
        frames = frames_of(record)
        return (
            not frames
            or not frames.isdisjoint(self.frames)
            or any(
                reference.target in self.instances for reference in record.references
            )
        )


def find_defaced(
    records: Mapping[int, InstanceRecord], outcomes: Mapping[str, SeriesDefacing]
) -> Defaced:
    """Return what a run defaces, from its records and
    :func:`find_face_blocks`' outcomes."""
    series = {uid for uid, outcome in outcomes.items() if outcome.frame is not None}
    return Defaced(
        frozenset(
            outcome.frame for outcome in outcomes.values() if outcome.frame is not None
        ),
        frozenset(
            record.sop_instance
            for record in records.values()
            if record.iod == CT_IMAGE
            and record.series in series
            and record.sop_instance
        ),
    )


def _series_outcome(
    positions: list[int], read: Callable[[int], bytes | None]
) -> tuple[SeriesDefacing, str | None]:
    """Find one series' block, or why it has none, and its Frame of
    Reference UID."""
    frame = None
    try:
        slices = [_slice(read(position)) for position in positions]
        _check_stack(slices)
        first = slices[0]
        frame = first.frame
        # Without one, no structure set's targets can be checked against
        # the block.
        if not frame:
            raise _Unusable(SeriesProblem.UNREADABLE)
        normal = np.cross(first.orientation[:3], first.orientation[3:])
        # Along the patient's superior axis, the slices within HEAD_REACH of
        # the top; for a stack along another axis, every slice, since each
        # spans the volume's height.
        if abs(abs(normal[2]) - 1) <= _SAME:
            tops = [each.position[2] for each in slices]
            kept = [i for i, top in enumerate(tops) if top >= max(tops) - HEAD_REACH]
        else:
            kept = list(range(len(slices)))
        finder = defacing.FaceFinder(
            first.orientation,
            [slices[i].position for i in kept],
            first.spacing,
            first.shape,
        )
        for index in kept:
            finder.add(_hounsfield(read(positions[index]), slices[index]))
        return SeriesDefacing(finder.block(), None, frame), frame
    except _Unusable as unusable:
        return SeriesDefacing(None, unusable.problem), frame
    except FaceBlockRefused as refused:
        return SeriesDefacing(None, refused.problem), frame
    # Whatever else a series' data raises, such as the finder's ValueError
    # for geometry that it cannot use, or MemoryError for a volume too large
    # to sample, leaves the series undefaced rather than stopping the run;
    # its message, which can quote a value, is dropped.
    except Exception:  # pylint: disable = broad-exception-caught
        return SeriesDefacing(None, SeriesProblem.UNREADABLE), frame


def _slice(data: bytes | None) -> _Slice:
    """Read what defacing needs of one slice.

    Raises
    ------
    _Unusable
    """
    if data is None:
        raise _Unusable(SeriesProblem.UNREADABLE)
    try:
        with redacted_diagnostics():
            dataset = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
            syntax = str(dataset.file_meta.TransferSyntaxUID)
    # pydicom raises many types for a file that it cannot read, and a
    # message can quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise _Unusable(SeriesProblem.UNREADABLE) from None
    if syntax not in NATIVE_TRANSFER_SYNTAXES:
        raise _Unusable(SeriesProblem.COMPRESSED)
    try:
        layout = layout_of(dataset)
    except PixelDataRefused:
        raise _Unusable(SeriesProblem.UNREADABLE) from None
    return _described(dataset, layout)


def _check_stack(slices: list[_Slice]) -> None:
    """Check that the slices are of one stack.

    Raises
    ------
    _Unusable
    """
    first = slices[0]
    for each in slices[1:]:
        if (
            each.shape != first.shape
            or each.frame != first.frame
            or not np.allclose(each.orientation, first.orientation, rtol=0, atol=_SAME)
            or not np.allclose(each.spacing, first.spacing, rtol=0, atol=_SAME)
        ):
            raise _Unusable(SeriesProblem.NOT_ONE_STACK)


def _numbers(
    dataset: pydicom.Dataset,
    keyword: str,
    count: int,
    default: tuple[float, ...] | None = None,
) -> tuple[float, ...]:
    """An attribute's ``count`` finite values, or ``default`` where it is absent.

    Raises
    ------
    _Unusable
        If it is absent without a default, or its values are not ``count``
        finite numbers.
    """
    if keyword not in dataset and default is not None:
        return default
    try:
        with redacted_diagnostics():
            value = dataset[keyword].value
            values = (
                tuple(float(v) for v in value)
                if isinstance(value, (list, tuple, pydicom.multival.MultiValue))
                else (float(value),)
            )
    # pydicom raises many types for a value it cannot convert, and a message
    # can quote the value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise _Unusable(SeriesProblem.UNREADABLE) from None
    if len(values) != count or not all(math.isfinite(v) for v in values):
        raise _Unusable(SeriesProblem.UNREADABLE)
    return values


def _padding(dataset: pydicom.Dataset, layout: Layout) -> tuple[int, int] | None:
    """The stored values that Pixel Padding Value and its range limit pad with.

    Raises
    ------
    _Unusable
        If either is present but is not one integer.
    """
    if "PixelPaddingValue" not in dataset:
        return None
    values = []
    for keyword in ("PixelPaddingValue", "PixelPaddingRangeLimit"):
        if keyword not in dataset:
            continue
        try:
            with redacted_diagnostics():
                value = dataset[keyword].value
        # pydicom raises many types for a value of the wrong length, and a
        # message can quote its bytes.
        except Exception:  # pylint: disable = broad-exception-caught
            raise _Unusable(SeriesProblem.UNREADABLE) from None
        if isinstance(value, bytes) and len(value) == layout.bits_allocated // 8:
            value = int.from_bytes(value, "little", signed=layout.signed)
        if isinstance(value, bool) or not isinstance(value, int):
            raise _Unusable(SeriesProblem.UNREADABLE)
        values.append(int(value))
    return min(values), max(values)


def _stored(data: bytes | None, shape: tuple[int, int]) -> np.ndarray:
    """One slice's stored values, rows by columns.

    Raises
    ------
    _Unusable
        If the file can no longer be read, or its pixel data decoded.
    """
    if data is None:
        raise _Unusable(SeriesProblem.UNREADABLE)
    try:
        with redacted_diagnostics():
            stored = np.asarray(pydicom.pixels.pixel_array(io.BytesIO(data)))
    # pydicom raises many types for pixel data it cannot read, and a message
    # can quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise _Unusable(SeriesProblem.UNREADABLE) from None
    if stored.shape != shape:
        raise _Unusable(SeriesProblem.UNREADABLE)
    return stored


def _hounsfield(data: bytes | None, each: _Slice) -> np.ndarray:
    """One slice in Hounsfield units, with padding as NaN."""
    stored = _stored(data, each.shape)
    slope, intercept = each.rescale
    values = stored.astype(np.float32) * np.float32(slope) + np.float32(intercept)
    if each.padding is not None:
        low, high = each.padding
        values[(stored >= low) & (stored <= high)] = np.nan
    return values


def _target_in(
    block: FaceBlock,
    frame: str,
    positions: list[int],
    read: Callable[[int], bytes | None],
) -> bool:
    """Whether a target of any of these structure sets, in this Frame of
    Reference, has a contour point in the block, or one cannot be read."""
    for position in positions:
        try:
            with redacted_diagnostics():
                dataset = pydicom.dcmread(io.BytesIO(read(position) or b""))
                if _targets_reach(dataset, frame, block):
                    return True
        # pydicom raises many types for a file it cannot read, and a message
        # can quote a value: a target in it cannot be ruled out.
        except Exception:  # pylint: disable = broad-exception-caught
            return True
    return False


def _targets_reach(dataset: pydicom.Dataset, frame: str, block: FaceBlock) -> bool:
    """Whether a target's contour in this Frame of Reference has a point in
    the block."""
    frames = {
        int(item.ROINumber): str(item.get("ReferencedFrameOfReferenceUID", "")).strip()
        for item in dataset.get("StructureSetROISequence", [])
    }
    targets = {
        int(item.ReferencedROINumber)
        for item in dataset.get("RTROIObservationsSequence", [])
        if str(item.get("RTROIInterpretedType") or "").strip().upper() in TARGET_TYPES
    }
    for item in dataset.get("ROIContourSequence", []):
        number = int(item.ReferencedROINumber)
        # A target that names no Frame of Reference may be in this one.
        if number not in targets or frames.get(number) not in ("", None, frame):
            continue
        for contour in item.get("ContourSequence", []):
            points = np.asarray([float(v) for v in contour.ContourData]).reshape(-1, 3)
            if block.contains(points).any():
                return True
    return False


class CtDefacer:
    """Gives the face block of one CT slice as air, for
    :func:`~pymedphys._dicom.deidentify.pixel_cleaning.black_out`.

    Parameters
    ----------
    block : FaceBlock
        The block of the slice's series.
    dataset : pydicom.Dataset
        The slice's data set.

    Raises
    ------
    PixelDataRefused
        With :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` where
        the slice is not one that :func:`find_face_blocks` defaces.
    """

    def __init__(self, block: FaceBlock, dataset: pydicom.Dataset) -> None:
        try:
            if str(dataset.file_meta.TransferSyntaxUID) not in NATIVE_TRANSFER_SYNTAXES:
                raise _Unusable(SeriesProblem.COMPRESSED)
            layout = layout_of(dataset)
            self._slice = _described(dataset, layout)
        # As for a series, whatever the data set raises refuses the slice,
        # without its message.
        except Exception:  # pylint: disable = broad-exception-caught
            raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA) from None
        self._block = block

    def __repr__(self) -> str:
        return "CtDefacer()"

    def mask(self, frame: int, stored: np.ndarray) -> FrameMask | None:
        """Return the pixels of the block to write as air, as the module
        describes, or None where the slice has none."""
        each = self._slice
        inside = self._block.slice_mask(
            each.position, each.orientation, each.spacing, each.shape
        )
        if not inside.any():
            return None
        slope, intercept = each.rescale
        padded = np.zeros(each.shape, dtype=bool)
        if each.padding is not None:
            low, high = each.padding
            padded = (stored >= low) & (stored <= high)
        # Padding is never bone, whatever Hounsfield units its stored value
        # would give, so that it cannot close a ring around the face.
        bone = (stored * slope + intercept >= defacing.BONE) & ~padded
        cavity = scipy.ndimage.binary_fill_holes(bone) & ~bone
        floor = max(globe[2] for globe in self._block.globes) + CAVITY_FLOOR
        inside &= ~(cavity & (_heights(each) > floor)) & ~padded
        if not inside.any():
            return None
        return FrameMask(frame, inside, each.air)


def _heights(each: _Slice) -> np.ndarray:
    """The z coordinate of each pixel's centre, in millimetres."""
    rows, columns = each.shape
    row_spacing, column_spacing = each.spacing
    along_row, down_column = each.orientation[2], each.orientation[5]
    return (
        each.position[2]
        + np.arange(rows)[:, np.newaxis] * (row_spacing * down_column)
        + np.arange(columns)[np.newaxis, :] * (column_spacing * along_row)
    )


def _described(dataset: pydicom.Dataset, layout: Layout) -> _Slice:
    """What defacing needs of a slice's data set, as :func:`_slice` reads it."""
    if layout.frames != 1 or layout.samples != 1:
        raise _Unusable(SeriesProblem.NOT_ONE_STACK)
    position = _numbers(dataset, "ImagePositionPatient", 3)
    orientation = _numbers(dataset, "ImageOrientationPatient", 6)
    spacing = _numbers(dataset, "PixelSpacing", 2)
    slope = _numbers(dataset, "RescaleSlope", 1, default=(1.0,))
    intercept = _numbers(dataset, "RescaleIntercept", 1, default=(0.0,))
    if min(spacing) <= 0 or slope[0] <= 0:
        raise _Unusable(SeriesProblem.UNREADABLE)
    exact = (AIR - intercept[0]) / slope[0]
    low, high = stored_range(layout)
    # A finite but tiny slope gives an infinite stored value.
    if not math.isfinite(exact) or not low <= round(exact) <= high:
        raise _Unusable(SeriesProblem.AIR_NOT_STORED)
    air = round(exact)
    frame = dataset.get("FrameOfReferenceUID")
    return _Slice(
        position=(position[0], position[1], position[2]),
        orientation=orientation,
        spacing=(spacing[0], spacing[1]),
        shape=(layout.rows, layout.columns),
        rescale=(slope[0], intercept[0]),
        padding=_padding(dataset, layout),
        air=int(air),
        frame=None if frame is None else normalise_uid(str(frame)) or None,
    )
