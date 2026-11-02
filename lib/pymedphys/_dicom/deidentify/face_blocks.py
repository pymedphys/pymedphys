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

# pylint: disable = too-many-lines
# One module finds each series' block and checks it against the run's
# structure sets, so it is long.

"""The face block of each CT series of a run, and the air written there.

Under the Clean Recognizable Visual Features Option, a run finds, before it
writes any instance, the face block
(:class:`~pymedphys._dicom.deidentify.defacing.FaceBlock`) of each series of
CT instances, of CT Image, Enhanced CT Image, and Legacy Converted Enhanced
CT Image (:data:`CT_IODS`, :func:`find_face_blocks`), and writes air into
each slice of a series that has one (:class:`CtDefacer`), as
:func:`~pymedphys._dicom.deidentify.pixel_cleaning.black_out` writes its
masks. A slice is a CT Image instance, or a frame of an Enhanced CT Image or
Legacy Converted Enhanced CT Image instance, and a series may hold either
kind, or both. A series is defaced only where all of these hold:

- every instance is read from the file that the run's first pass read, with
  native Pixel Data of one sample and whole bytes
  (:func:`~pymedphys._dicom.deidentify.pixel_cleaning.layout_of`), of one
  frame for CT Image, and a readable Pixel Padding Value and Pixel Padding
  Range Limit where present;
- each slice has finite Image Position (Patient), Image Orientation
  (Patient), Pixel Spacing, Rescale Slope, and Rescale Intercept: a CT
  Image instance's own, its Rescale Slope and Rescale Intercept 1 and 0
  where absent, or, for each frame of a multi-frame instance, those of its
  Plane Position (Patient), Plane Orientation (Patient), Pixel Measures,
  and CT Pixel Value Transformation functional groups, each in either the
  frame's item of the Per-frame Functional Groups Sequence or the Shared
  Functional Groups Sequence, never both
  (:func:`~pymedphys._dicom.deidentify.functional_groups.frame_group`);
- each slice's stored values are in Hounsfield units: a CT Image's Rescale
  Type, which PS3.3 C.8.2.1 requires where they are not, is HU where
  present, and a frame's, which its CT Pixel Value Transformation
  functional group requires (PS3.3 Table C.8-126), is HU, since a material
  map of a multi-energy CT, in other units, has no air to write;
- the slices share their orientation, rows, columns, spacing, and Frame of
  Reference UID, which they have, and the stored values of each can hold
  air, -1000 Hounsfield units, as one stored value, rounded, without
  clipping, each slice by its own rescale;
- :class:`~pymedphys._dicom.deidentify.defacing.FaceFinder` finds the
  block from the slices within :data:`HEAD_REACH` millimetres of the
  volume's superior end, which bounds the memory that a long volume needs,
  no two slices lying at one position, as two phases of one stack do; and
- no contour of a target, an ROI whose RT ROI Interpreted Type is
  :data:`TARGET_TYPES`, of any RT Structure Set of the run searched for the
  series (:func:`_searched`), in the series' Frame of Reference, or naming
  none, reaches the block, or has anything
  between its contours that does, as the convex hull of its contours
  judges it (:func:`_hull_reaches`); no target in another frame, whose
  contours cannot be placed without a registration, has a structure set
  that ties that frame to the series' slices (:func:`_targets_reach`), a
  target whose ROI names no frame, or one that is malformed, counting as
  one in the series' frame and in each frame that its structure set
  declares;
- every point of each eye, an ROI in the series' Frame of Reference or
  naming none, a malformed frame counting as none
  (:func:`_roi_frames`), whose ROI Name names an eye, a globe, or an eyeball
  (:func:`_is_eye`), of those structure sets lies within
  :data:`EYE_REACH` millimetres of the nearer globe that the finder found
  (:func:`_eyes_far`), so that a block placed from something else taken
  for the globes is not written; and
- every structure set searched for it can be read.

Anything else that a series' data raises leaves the series undefaced, as
unreadable, rather than stopping the run, and no message of it, which could
quote a value, is kept. Each instance's pixel data are decoded once for the
finder, and once more for the brain that defacing keeps
(:func:`kept_slices`), a frame at a time, so that a multi-frame instance is
never held decoded whole.

A series with a target in its block is not defaced, and each of its slices
is held for review (:attr:`~.reasons.VisualFeaturesReason.TARGET_IN_FACE_BLOCK`),
so that a release never loses a target to defacing unseen, and so is one
with an eye that disagrees with its globes
(:attr:`~.reasons.VisualFeaturesReason.EYES_DISAGREE_WITH_ROIS`). Any other series
that is not defaced, such as one without a head, is written as it would be
without a block, and the face review's verdict on it decides, as for every
other instance that can show a face. The outcome of each series is counted
for the release report (:class:`FaceBlockCounts`), by series, never naming
one.

Within the block, :class:`CtDefacer` keeps each pixel of Pixel Padding
Value or its range, and each pixel of the brain within the cranial cavity,
which bone at :data:`~pymedphys._dicom.deidentify.defacing.BONE` Hounsfield
units or more encloses within the slice, so that the brain in front of the
block's plane is kept: the cavity's pixels above
:data:`~pymedphys._dicom.deidentify.defacing.BODY` Hounsfield units that
join, within the slice, such pixels behind the plane, and the cavity's
pixels that they enclose, so never bone, which is written as air. So the
air of a frontal sinus, which bone also encloses, is written as air, as is
any tissue lining it, where the sinus lies ahead of the plane and bone
parts it from the brain within the slice; where its back wall reads below
:data:`~pymedphys._dicom.deidentify.defacing.BONE` Hounsfield units in a
slice, as a thin wall can, its lining can join the brain, and the sinus is
kept, as is a sinus whose lining or fluid reaches behind the plane, since
any tissue of the cavity behind the plane counts as brain. A slice with
no brain behind the plane, such as a coronal slice ahead of it, keeps
none. Padding is never taken for bone, so it cannot close a ring around
the face. The cavity is kept only more than :data:`CAVITY_FLOOR`
millimetres above the higher globe's centre, above the orbits, so that
bone enclosing an orbit within a slice, or a thin orbital roof that the
slice's bone does not seal, keeps no part of an eye.
Where no bone encloses the cavity within a slice, the block is air to the
top of the slice. Where air's stored value is itself padding, the pixels
written are padding, which a viewer shows as outside the image, as the air
before the face is in most scans.

Beyond CT instances, the run cleans the same region of an RT Dose
that :mod:`~pymedphys._dicom.deidentify.dose_defacing` sets to zero there,
of an RT Structure Set whose contours, or a PET image, of :data:`PET_IODS`,
whose activity, :mod:`~pymedphys._dicom.deidentify.region_defacing` cuts or
sets to zero there, frame by frame for a multi-frame PET image, and of a
Segmentation whose segments
:mod:`~pymedphys._dicom.deidentify.segmentation_defacing` clears there,
each with that series' Frame of Reference as its only one. Any other RT
Structure Set, RT Dose with pixel data, PET instance, or Segmentation
(:data:`UNDEFACED_IODS`) in the Frame of Reference of a defaced series
keeps its contours or pixel data, which can still outline the face, so it
is held for review whatever its verdict, since a reviewer may have judged
it from the defaced CT's previews
(:attr:`~.reasons.VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME`), until
the run can clean it too (:class:`Defaced`). So is one that names no Frame
of Reference, in a run that defaces any series, or that refers to an
instance of a defaced series, whatever frame it declares. A structure set is searched for targets
in the block of a series where it is in the series' frame, names no valid
frame, or is drawn on its slices, and otherwise unless it and every slice
give Patient IDs that differ, and a target in another frame holds a series
whose slices its structure set ties to that frame, whatever other frames
the set declares.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import io
import math
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import scipy

from . import defacing
from .defacing import FaceBlock, FaceBlockProblem, FaceBlockRefused
from .diagnostics import redacted_diagnostics
from .functional_groups import frame_group
from .pixel_cleaning import (
    FrameMask,
    Layout,
    PixelDataRefused,
    layout_of,
    stored_range,
)
from .pseudonyms import SubjectIdentity
from .reasons import TransformReason
from .references import InstanceRecord
from .sop_classes import iod_for_sop_class
from .source import NATIVE_TRANSFER_SYNTAXES
from .uid_registry import is_uid
from .uids import normalise_uid

CT_IMAGE = "CT Image"
ENHANCED_CT_IMAGE = "Enhanced CT Image"
LEGACY_CONVERTED_ENHANCED_CT_IMAGE = "Legacy Converted Enhanced CT Image"
# The CT IODs whose series the run defaces: CT Image, whose slices are
# instances of one frame, and the two whose instances hold many frames, each
# placed by its functional groups.
CT_IODS = frozenset({CT_IMAGE, ENHANCED_CT_IMAGE, LEGACY_CONVERTED_ENHANCED_CT_IMAGE})
MULTI_FRAME_CT_IODS = CT_IODS - {CT_IMAGE}
RT_STRUCTURE_SET = "RT Structure Set"
PET_IMAGE = "Positron Emission Tomography Image"
ENHANCED_PET_IMAGE = "Enhanced PET Image"
LEGACY_CONVERTED_ENHANCED_PET_IMAGE = "Legacy Converted Enhanced PET Image"
# The PET IODs whose images the run sets to zero activity in a defaced
# frame's block, as for CT.
PET_IODS = frozenset(
    {PET_IMAGE, ENHANCED_PET_IMAGE, LEGACY_CONVERTED_ENHANCED_PET_IMAGE}
)
MULTI_FRAME_PET_IODS = PET_IODS - {PET_IMAGE}
# The only Rescale Type of the Hounsfield units in which the run finds the
# block and writes air (PS3.3 C.8.2.1 and Table C.8-126).
HOUNSFIELD_UNITS = "HU"
AIR = -1000.0  # Hounsfield units
HEAD_REACH = 400.0  # millimetres below the volume's superior end
# How far above the higher globe's centre, in millimetres, the cranial
# cavity is kept: the largest globe radius that the finder accepts, half of
# GLOBE_DIAMETER's upper end, and as much again for the orbit above it. A
# placeholder, to be set by validation.
CAVITY_FLOOR = defacing.GLOBE_DIAMETER[1]
TARGET_TYPES = frozenset({"PTV", "CTV", "GTV"})
# How far, in millimetres, each point of an eye's contour may lie from the
# nearer centre of the globes that the finder found: the largest globe
# radius that it accepts, half of GLOBE_DIAMETER's upper end, and 10 mm
# more for an eye drawn with a margin, or a globe found off its centre. A
# placeholder, to be set by validation.
EYE_REACH = defacing.GLOBE_DIAMETER[1] / 2 + 10.0
# The IODs whose instances in a defaced series' Frame of Reference are held
# unless the run cleans them of the face.
UNDEFACED_IODS = frozenset({RT_STRUCTURE_SET, "RT Dose", *PET_IODS, "Segmentation"})
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
    # slices or frames of more than one sample, orientation, size, spacing,
    # or Frame of Reference, or a CT Image instance of more than one frame
    NOT_ONE_STACK = "not-one-stack"
    # stored values whose Rescale Type is not Hounsfield units, as a
    # material map of a multi-energy CT can be
    NOT_HOUNSFIELD = "not-hounsfield-units"
    # stored values that cannot hold air without clipping
    AIR_NOT_STORED = "air-not-stored"
    # a target that may reach the block
    TARGET_IN_BLOCK = "target-in-block"
    # an eye's contour in the series' frame away from the globes found
    EYES_DISAGREE = "eyes-disagree-with-rois"


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
        its block, or an eye's contour away from the globes that its block
        was found from."""
        return self.problem in (
            SeriesProblem.TARGET_IN_BLOCK,
            SeriesProblem.EYES_DISAGREE,
        )


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
    """Return the outcome of each series of CT instances, of :data:`CT_IODS`,
    by its Series Instance UID.

    Parameters
    ----------
    records : mapping of int to InstanceRecord
        The run's records, by run position, as its first pass gives them.
        A CT instance without a Series Instance UID is not defaced, and has
        no outcome.
    read : callable
        Gives the file at a run position as the first pass read it, or None
        if it can no longer be read or has changed.
    """
    series: dict[str, list[int]] = collections.defaultdict(list)
    slices: dict[str, set[str]] = collections.defaultdict(set)
    structure_sets: list[int] = []
    for position, record in sorted(records.items()):
        if record.iod in CT_IODS and record.series is not None:
            series[record.series].append(position)
            if record.sop_instance:
                slices[record.series].add(record.sop_instance)
        elif record.iod == RT_STRUCTURE_SET:
            structure_sets.append(position)
    outcomes = {}
    for uid, positions in series.items():
        outcome, frame = _series_outcome(positions, read)
        if outcome.block is not None and frame:
            searched = [
                position
                for position in structure_sets
                if _searched(records[position], frame, slices[uid], positions, records)
            ]
            if _target_in(outcome.block, frame, slices[uid], searched, read):
                outcome = SeriesDefacing(None, SeriesProblem.TARGET_IN_BLOCK)
            elif _eyes_disagree(outcome.block, frame, searched, read):
                outcome = SeriesDefacing(None, SeriesProblem.EYES_DISAGREE)
        outcomes[uid] = outcome
    return outcomes


def _searched(
    structure_set: InstanceRecord,
    frame: str,
    slices: set[str],
    positions: list[int],
    records: Mapping[int, InstanceRecord],
) -> bool:
    """Whether a structure set is searched for targets in a series' block.

    One in the series' Frame of Reference, naming no valid frame, or drawn
    on its slices always is. So is any other of the same patient as a
    slice of the series (:func:`_same_patient`), since a target in it that
    names no frame, or a malformed one, may be in the series' frame
    whatever frames the set declares; one in another frame that the set
    does not tie to the series' slices is passed over
    (:func:`_targets_reach`).
    """
    frames = frames_of(structure_set)
    if frame in frames or not any(is_uid(each) for each in frames):
        return True
    if not slices.isdisjoint(ref.target for ref in structure_set.references):
        return True
    return any(
        _same_patient(structure_set.patient, records[position].patient)
        for position in positions
    )


def _same_patient(one: SubjectIdentity | None, other: SubjectIdentity | None) -> bool:
    """Whether two instances may be of the same patient.

    They may unless both give one Patient ID of printable ASCII
    characters alone, without its padding, and the two differ without
    case. A Patient ID that is absent, empty, not text, of several values,
    or holds any other character, such as a control character, a letter
    outside ASCII, or a fullwidth form, matches any, since text that may
    be the same in another spelling cannot tell patients apart. The Issuer
    of Patient ID is not compared, since planning systems write their own
    or none. So only a structure set that is clearly another patient's is
    passed over.
    """
    if one is None or other is None:
        return True
    ids = (one.identifier, other.identifier)
    if not all(each.isascii() and each.isprintable() for each in ids):
        return True
    # An empty value or several values, which a backslash separates, tell
    # nothing apart either.
    if not all(each and "\\" not in each for each in ids):
        return True
    return ids[0].casefold() == ids[1].casefold()


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
        The SOP Instance UID of each instance of a defaced series, whether
        it holds one slice or many frames.
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
            if record.iod in CT_IODS and record.series in series and record.sop_instance
        ),
    )


def _series_outcome(
    positions: list[int], read: Callable[[int], bytes | None]
) -> tuple[SeriesDefacing, str | None]:
    """Find one series' block, or why it has none, and its Frame of
    Reference UID."""
    frame = None
    try:
        slices, places = _stack(positions, read)
        first = slices[0]
        frame = first.frame
        # Without one, no structure set's targets can be checked against
        # the block.
        if not frame:
            raise _Unusable(SeriesProblem.UNREADABLE)
        finder = _finder(slices, places, read)
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


def inspect_series(
    positions: list[int], read: Callable[[int], bytes | None]
) -> defacing.FaceInspection | None:
    """What the finder finds in one series' slices, as a run gives them to
    it, or None where it is given none, for a check on reference masks.

    Parameters
    ----------
    positions : list of int
        The run positions of the series' CT instances.
    read : callable
        As for :func:`find_face_blocks`.
    """
    try:
        slices, places = _stack(positions, read)
        return _finder(slices, places, read).inspect()
    except (_Unusable, FaceBlockRefused):
        return None


def _stack(
    positions: Sequence[int], read: Callable[[int], bytes | None]
) -> tuple[list[_Slice], list[tuple[int, int]]]:
    """Read every slice of a series: each instance's frames in turn, in the
    order of ``positions``, with the run position and frame index of each.

    Raises
    ------
    _Unusable
        If a slice cannot be read, or the slices are not of one stack.
    """
    slices: list[_Slice] = []
    places: list[tuple[int, int]] = []
    for position in positions:
        for index, each in enumerate(_slices(read(position))):
            slices.append(each)
            places.append((position, index))
    _check_stack(slices)
    return slices, places


def _finder(
    slices: list[_Slice],
    places: list[tuple[int, int]],
    read: Callable[[int], bytes | None],
) -> defacing.FaceFinder:
    """The finder of one stack's slices, each added, with each slice's run
    position and frame index in ``places``.

    Each instance is read once, and its frames decoded one at a time, so
    that a multi-frame instance is never held decoded whole.

    Raises
    ------
    _Unusable
        If a slice can no longer be read.
    FaceBlockRefused
        As :class:`~pymedphys._dicom.deidentify.defacing.FaceFinder` does.
    """
    first = slices[0]
    normal = np.cross(first.orientation[:3], first.orientation[3:])
    # Along the patient's superior axis, the slices within HEAD_REACH of
    # the top; for a stack along another axis, every slice, since each
    # spans the volume's height.
    if abs(abs(normal[2]) - 1) <= _SAME:
        tops = [each.position[2] for each in slices]
        kept = [i for i, top in enumerate(tops) if top >= max(tops) - HEAD_REACH]
    else:
        kept = list(range(len(slices)))
    # By instance, in run order, then by frame, the order in which they are
    # added, which the finder needs their positions in.
    by_instance: dict[int, list[int]] = {}
    for index in kept:
        by_instance.setdefault(places[index][0], []).append(index)
    order = [index for indices in by_instance.values() for index in indices]
    finder = defacing.FaceFinder(
        first.orientation,
        [slices[i].position for i in order],
        first.spacing,
        first.shape,
    )
    for position, indices in by_instance.items():
        stored = _stored(read(position), first.shape, [places[i][1] for i in indices])
        for index, values in zip(indices, stored, strict=True):
            finder.add(_hounsfield(values, slices[index]))
    return finder


def _slices(data: bytes | None) -> tuple[_Slice, ...]:
    """Read what defacing needs of each slice of one instance: the instance
    itself, of CT Image, or each frame of a multi-frame instance.

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


def _stored(
    data: bytes | None, shape: tuple[int, int], frames: Sequence[int]
) -> Iterator[np.ndarray]:
    """The stored values of each of an instance's ``frames``, in ascending
    order, rows by columns, decoded one at a time.

    Raises
    ------
    _Unusable
        If the file can no longer be read, or its pixel data decoded as
        that many frames of that shape.
    """
    if data is None:
        raise _Unusable(SeriesProblem.UNREADABLE)
    wanted = sorted(frames)
    decoded = pydicom.pixels.iter_pixels(io.BytesIO(data), indices=wanted)
    given = 0
    while True:
        try:
            with redacted_diagnostics():
                stored = np.asarray(next(decoded))
        except StopIteration:
            break
        # pydicom raises many types for pixel data it cannot read, and a
        # message can quote a value.
        except Exception:  # pylint: disable = broad-exception-caught
            raise _Unusable(SeriesProblem.UNREADABLE) from None
        if stored.shape != shape or given >= len(wanted):
            raise _Unusable(SeriesProblem.UNREADABLE)
        given += 1
        yield stored
    if given != len(wanted):
        raise _Unusable(SeriesProblem.UNREADABLE)


def _hounsfield(stored: np.ndarray, each: _Slice) -> np.ndarray:
    """One slice's stored values in Hounsfield units, with padding as NaN."""
    slope, intercept = each.rescale
    values = stored.astype(np.float32) * np.float32(slope) + np.float32(intercept)
    if each.padding is not None:
        low, high = each.padding
        values[(stored >= low) & (stored <= high)] = np.nan
    return values


def _target_in(
    block: FaceBlock,
    frame: str,
    slices: set[str],
    positions: list[int],
    read: Callable[[int], bytes | None],
) -> bool:
    """Whether a target of any of these structure sets may reach the block
    of the series with this Frame of Reference and these slices, as
    :func:`_targets_reach` judges it, or one cannot be read."""
    for position in positions:
        try:
            with redacted_diagnostics():
                dataset = pydicom.dcmread(io.BytesIO(read(position) or b""))
                if _targets_reach(dataset, frame, slices, block):
                    return True
        # pydicom raises many types for a file it cannot read, and a message
        # can quote a value: a target in it cannot be ruled out.
        except Exception:  # pylint: disable = broad-exception-caught
            return True
    return False


def _eyes_disagree(
    block: FaceBlock,
    frame: str,
    positions: list[int],
    read: Callable[[int], bytes | None],
) -> bool:
    """Whether an eye of any of these structure sets disagrees with the
    globes that the block of the series with this Frame of Reference was
    found from, as :func:`_eyes_far` judges it, or a set cannot be read."""
    for position in positions:
        try:
            with redacted_diagnostics():
                dataset = pydicom.dcmread(io.BytesIO(read(position) or b""))
                if _eyes_far(dataset, frame, block):
                    return True
        # As for a target, an eye in a file that cannot be read cannot be
        # checked.
        except Exception:  # pylint: disable = broad-exception-caught
            return True
    return False


# A word of an ROI Name that names an eye, alone or with its side.
_EYE = re.compile(
    r"(?:l|r|lt|rt|left|right)?(?:eye|eyeball|globe)s?(?:l|r|lt|rt|left|right)?"
)
# Words that make an ROI named for an eye a part of it, or a region around
# it, whose points need not lie near its centre.
_NOT_EYE = frozenset({"lens", "lenses", "cornea", "ring", "avoid"})


def _is_eye(name: str) -> bool:
    """Whether an ROI Name names an eye or both eyes, by its words, which an
    underscore, a space, other punctuation, or a change of case parts."""
    words = {
        word.lower()
        for word in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+", name)
    }
    return any(_EYE.fullmatch(word) for word in words) and not words & _NOT_EYE


def _eyes_far(dataset: pydicom.Dataset, frame: str, block: FaceBlock) -> bool:
    """Whether a point of the contours of an ROI in this Frame of Reference,
    or naming none, whose name is an eye's (:func:`_is_eye`) lies farther
    than :data:`EYE_REACH` from both of the block's globes' centres, or
    cannot be placed.

    So an eye drawn where the finder found no globe, as where it took
    something else for one, holds the series. Each eye is checked alone,
    or both together in one ROI, but an eye that the structure set does
    not draw, or names otherwise, is not checked, nor is one in another
    frame, which cannot be placed in the series' without a registration.
    An ROI's frame is taken as for a target (:func:`_roi_frames`), so one
    that is malformed, or that its set does not declare, counts as naming
    none, and the eye is checked.
    """
    frames_of_roi = _roi_frames(dataset)
    eyes = {
        int(item.ROINumber)
        for item in dataset.get("StructureSetROISequence") or []
        if frames_of_roi(int(item.ROINumber)) & {"", frame}
        and _is_eye(str(item.get("ROIName") or ""))
    }
    globes = np.asarray(block.globes, dtype=float)
    for item in dataset.get("ROIContourSequence") or []:
        if int(item.ReferencedROINumber) not in eyes:
            continue
        for contour in item.get("ContourSequence") or []:
            points = np.asarray([float(v) for v in contour.ContourData]).reshape(-1, 3)
            nearest = np.min(
                np.linalg.norm(points[:, np.newaxis, :] - globes, axis=2), axis=1
            )
            # Written so that a coordinate that is not a number fails it too.
            if not (nearest <= EYE_REACH).all():
                return True
    return False


def _targets(dataset: pydicom.Dataset) -> set[int]:
    """The ROI Numbers of a structure set's targets."""
    return {
        int(item.ReferencedROINumber)
        for item in dataset.get("RTROIObservationsSequence", [])
        if str(item.get("RTROIInterpretedType") or "").strip().upper() in TARGET_TYPES
    }


def _targets_reach(
    dataset: pydicom.Dataset, frame: str, slices: set[str], block: FaceBlock
) -> bool:
    """Whether a target of a structure set may reach the block of the series
    with this Frame of Reference and these slices.

    A target in that frame reaches it where the convex hull of its contours
    does (:func:`_hull_reaches`). One in another frame cannot be placed in
    the series' without a registration, so it is taken to reach the block
    where its structure set ties that frame to the series' slices: a contour
    of an ROI in that frame is drawn on one of them, or the frame's own list
    of contour images names one. A target in another frame that its
    structure set does not tie to them, such as one of another scan, does
    not. A target whose ROI names no frame may be in the series' or in any
    frame that its structure set declares, so it is taken as each. So is
    one whose ROI's frame is not one UID that its set declares alone, as
    one UID in one item, or whose
    ROI Number is repeated with another frame, which is also taken as each
    value it names, so that a malformed frame that the set ties to the
    series' slices still holds it.
    """
    frames_of_roi = _roi_frames(dataset)
    targets = _targets(dataset)
    tied = _tied_frames(dataset, frames_of_roi, slices)
    for item in dataset.get("ROIContourSequence", []):
        number = int(item.ReferencedROINumber)
        if number not in targets:
            continue
        frames = frames_of_roi(number)
        if (frames - {"", frame}) & tied:
            return True
        # A target that names no Frame of Reference may be in this one.
        if frames & {"", frame}:
            points = [
                np.asarray([float(v) for v in contour.ContourData]).reshape(-1, 3)
                for contour in item.get("ContourSequence", [])
            ]
            if points and _hull_reaches(block, np.concatenate(points)):
                return True
    return False


def _tied_frames(
    dataset: pydicom.Dataset,
    frames_of_roi: Callable[[int], set[str]],
    slices: set[str],
) -> set[str]:
    """Return the Frames of Reference that a structure set ties to any of
    these slices: by an ROI in the frame with a contour drawn on one, or by
    the frame's own list of contour images naming one."""
    tied = set()
    for item in dataset.get("ROIContourSequence", []):
        if any(
            _images(contour) & slices for contour in item.get("ContourSequence", [])
        ):
            tied |= frames_of_roi(int(item.ReferencedROINumber))
    for use in dataset.get("ReferencedFrameOfReferenceSequence", []):
        images = {
            uid
            for study in use.get("RTReferencedStudySequence", [])
            for series in study.get("RTReferencedSeriesSequence", [])
            for uid in _images(series)
        }
        if images & slices:
            tied |= _frames(use, "FrameOfReferenceUID")
    return tied - {""}


def _roi_frames(dataset: pydicom.Dataset) -> Callable[[int], set[str]]:
    """The Frames of Reference that each ROI of a structure set, by its ROI
    Number, may be in: its own, where it is one UID that the set declares
    alone, as one UID in one item; otherwise ``""``, for none, with each
    frame that the set declares and each label that the ROI gives, as for
    an ROI Number repeated with another frame (:func:`_targets_reach`)."""
    named: dict[int, set[str]] = collections.defaultdict(set)
    for item in dataset.get("StructureSetROISequence", []):
        named[int(item.ROINumber)] |= _frames(item, "ReferencedFrameOfReferenceUID")
    declarations = [
        _frames(item, "FrameOfReferenceUID")
        for item in dataset.get("ReferencedFrameOfReferenceSequence", [])
    ]
    # Every label a declaration gives may be a frame, but only one UID
    # declared alone makes an ROI's frame certain.
    declared = set().union(*declarations) - {""}
    certain = {frame for each in declarations if "" not in each for frame in each}

    def frames_of_roi(number: int) -> set[str]:
        frames = named.get(number, {""})
        # An ROI's frame is one that its set declares (PS3.3 C.8.8.5), so
        # one that is not is malformed too.
        return (
            frames
            if len(frames) == 1 and frames <= certain
            else {"", *declared, *frames}
        )

    return frames_of_roi


def _frames(item: pydicom.Dataset, keyword: str) -> set[str]:
    """The Frames of Reference that an item's Frame of Reference UID may
    name: the UID alone, where it is one; otherwise each of its values
    without padding, as labels that can still tie a target to a frame, and
    ``""`` for no frame, where it is absent, empty, of more than one value,
    or not a UID."""
    value = item.get(keyword)
    if value is None:
        values = []
    elif isinstance(value, (str, bytes)):
        values = [value]
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    labels = {normalise_uid(str(each)) for each in values} - {""}
    if len(values) == 1 and len(labels) == 1 and is_uid(next(iter(labels))):
        return labels
    return {"", *labels}


def _images(item: pydicom.Dataset) -> set[str]:
    """The SOP Instance UIDs of an item's Contour Image Sequence."""
    return {
        normalise_uid(str(image.get("ReferencedSOPInstanceUID") or ""))
        for image in item.get("ContourImageSequence", [])
    }


# The largest magnitude, in millimetres, of a coordinate of a target that
# is placed; a larger one, or one not finite, cannot be.
_FARTHEST = 1e6


def _hull_reaches(block: FaceBlock, points: np.ndarray) -> bool:
    """Whether the convex hull of a target's points meets the block or its
    boundary.

    Whatever a planning system interpolates between a target's contours,
    such as between two drawn on PET slices between the CT's, or between
    sagittal ones, lies within their convex hull, as does each contour's
    every segment and interior. The block is the intersection of two closed
    half-spaces, and the distances into each are affine, so the hull meets
    it exactly where, in the plane of each point's two distances, the
    points' hull meets the closed quadrant where both are not negative:
    where a point lies in it, or else, since the quadrant is unbounded,
    where an edge crosses it, which must run from a point behind the plane
    and not below the limit to one ahead of the plane and below the limit.
    There is such a pair exactly where the steepest of the first kind, its
    height above the limit over its distance behind the plane, is at least
    the shallowest of the second, its depth below over its distance ahead,
    which takes one pass over the points. This holds a target wherever any
    part of its hull reaches the block, as the hull of one that wraps around
    the block without entering it can, which errs towards holding. A point
    that cannot be placed reaches the block.
    """
    if not (np.abs(points) <= _FARTHEST).all():
        return True
    anterior, origin = np.array(block.anterior), np.array(block.origin)
    ahead = (points - origin) @ anterior
    above = points[:, 2] - block.inferior_limit
    if ((ahead >= 0) & (above >= 0)).any():
        return True
    behind = (ahead < 0) & (above >= 0)
    below = (ahead > 0) & (above < 0)
    if not (behind.any() and below.any()):
        return False
    first = np.flatnonzero(behind)[np.argmax(above[behind] / -ahead[behind])]
    second = np.flatnonzero(below)[np.argmin(-above[below] / ahead[below])]
    return bool(ahead[second] * above[first] - ahead[first] * above[second] >= 0)


class CtDefacer:
    """Gives the face block of each slice of one CT instance as air, for
    :func:`~pymedphys._dicom.deidentify.pixel_cleaning.black_out`: the
    instance's one slice, for CT Image, or each of its frames, each placed
    by its own functional groups.

    Parameters
    ----------
    block : FaceBlock
        The block of the instance's series.
    dataset : pydicom.Dataset
        The instance's data set.

    Raises
    ------
    PixelDataRefused
        With :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` where
        the instance is not one that :func:`find_face_blocks` defaces.
    """

    def __init__(self, block: FaceBlock, dataset: pydicom.Dataset) -> None:
        try:
            if str(dataset.file_meta.TransferSyntaxUID) not in NATIVE_TRANSFER_SYNTAXES:
                raise _Unusable(SeriesProblem.COMPRESSED)
            layout = layout_of(dataset)
            self._slices = _described(dataset, layout)
        # As for a series, whatever the data set raises refuses the
        # instance, without its message.
        except Exception:  # pylint: disable = broad-exception-caught
            raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA) from None
        self._block = block

    def __repr__(self) -> str:
        return "CtDefacer()"

    def mask(self, frame: int, stored: np.ndarray) -> FrameMask | None:
        """Return the pixels of one frame's block to write as air, as the
        module describes, or None where the frame has none."""
        each = self._slices[frame]
        inside = self._block.slice_mask(
            each.position, each.orientation, each.spacing, each.shape
        )
        if not inside.any():
            return None
        kept, padded = _kept(self._block, each, stored)
        inside &= ~kept & ~padded
        if not inside.any():
            return None
        return FrameMask(frame, inside, each.air)


def _kept(
    block: FaceBlock, each: _Slice, stored: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return a slice's pixels of the brain, within the cranial cavity, that
    defacing keeps, and those of padding, each of bool, rows by columns."""
    slope, intercept = each.rescale
    padded = np.zeros(each.shape, dtype=bool)
    if each.padding is not None:
        low, high = each.padding
        padded = (stored >= low) & (stored <= high)
    # Padding is never bone, whatever Hounsfield units its stored value
    # would give, so that it cannot close a ring around the face.
    hounsfield = stored * slope + intercept
    bone = (hounsfield >= defacing.BONE) & ~padded
    floor = max(globe[2] for globe in block.globes) + CAVITY_FLOOR
    cavity = scipy.ndimage.binary_fill_holes(bone) & ~bone & (_heights(each) > floor)
    # Of the cavity, only the brain: its tissue that joins, within the slice,
    # its tissue behind the block's plane, with the cavity that it encloses,
    # so that nothing is kept that the cavity alone would not keep. Bone
    # also encloses the air of a frontal sinus in its wall, which, kept,
    # would differ from air written around it only by noise, and any tissue
    # lining it, which joins none behind the plane where it lies ahead of
    # the plane and bone parts it from the brain.
    tissue = cavity & (hounsfield > defacing.BODY)
    labels, _ = scipy.ndimage.label(tissue)
    inside = block.slice_mask(each.position, each.orientation, each.spacing, each.shape)
    joined = np.unique(labels[tissue & ~inside])
    brain = np.isin(labels, joined[joined > 0])
    return scipy.ndimage.binary_fill_holes(brain) & cavity & ~padded, padded


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


def iod_of(dataset: pydicom.Dataset) -> str | None:
    """Return the name of an instance's IOD, by its SOP Class UID, as
    Table B.5-1 gives it, or None where that cannot be read or names
    none."""
    try:
        with redacted_diagnostics():
            iod = iod_for_sop_class(str(dataset.SOPClassUID))
    # A SOP Class UID that cannot be read names no IOD; the message, which
    # could quote it, is dropped.
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    return None if iod is None else iod.name


def _described(dataset: pydicom.Dataset, layout: Layout) -> tuple[_Slice, ...]:
    """What defacing needs of each slice of an instance's data set, as
    :func:`_slices` reads it.

    A CT Image instance is one slice, placed and rescaled by its own
    attributes; each frame of an Enhanced CT Image or Legacy Converted
    Enhanced CT Image instance is one, placed by its Plane Position
    (Patient), Plane Orientation (Patient), and Pixel Measures functional
    groups and rescaled by its CT Pixel Value Transformation functional
    group, each read by :func:`~.functional_groups.frame_group`. Pixel
    Padding Value, its range limit, and the Frame of Reference UID are the
    instance's, for every frame.

    Raises
    ------
    _Unusable
    """
    if layout.samples != 1:
        raise _Unusable(SeriesProblem.NOT_ONE_STACK)
    iod = iod_of(dataset)
    if iod == CT_IMAGE:
        if layout.frames != 1:
            raise _Unusable(SeriesProblem.NOT_ONE_STACK)
        return (_described_slice(dataset, layout, (dataset,) * 4, multi_frame=False),)
    if iod not in MULTI_FRAME_CT_IODS:
        raise _Unusable(SeriesProblem.UNREADABLE)
    groups = []
    for frame in range(layout.frames):
        try:
            groups.append(
                tuple(
                    frame_group(dataset, layout.frames, frame, keyword)
                    for keyword in (
                        "PlanePositionSequence",
                        "PlaneOrientationSequence",
                        "PixelMeasuresSequence",
                        "PixelValueTransformationSequence",
                    )
                )
            )
        except ValueError:
            raise _Unusable(SeriesProblem.UNREADABLE) from None
    return tuple(
        _described_slice(dataset, layout, each, multi_frame=True) for each in groups
    )


def _described_slice(
    dataset: pydicom.Dataset,
    layout: Layout,
    groups: tuple[pydicom.Dataset, ...],
    *,
    multi_frame: bool,
) -> _Slice:
    """What defacing needs of one slice, from the data sets that hold its
    Image Position (Patient), Image Orientation (Patient), Pixel Spacing,
    and rescale, in that order: the instance's own for CT Image, or the
    frame's functional groups' items.

    A CT Image's Rescale Slope and Rescale Intercept default to 1 and 0
    where absent, and its Rescale Type, which PS3.3 C.8.2.1 requires where
    the values are not Hounsfield units, must be HU where present; a
    frame's three are Type 1 in its CT Pixel Value Transformation
    functional group (PS3.3 Table C.8-126), so each must be present, and
    its Rescale Type HU.

    Raises
    ------
    _Unusable
    """
    placed, oriented, measured, rescaled = groups
    position = _numbers(placed, "ImagePositionPatient", 3)
    orientation = _numbers(oriented, "ImageOrientationPatient", 6)
    spacing = _numbers(measured, "PixelSpacing", 2)
    defaults = (None, None) if multi_frame else ((1.0,), (0.0,))
    slope = _numbers(rescaled, "RescaleSlope", 1, default=defaults[0])
    intercept = _numbers(rescaled, "RescaleIntercept", 1, default=defaults[1])
    _check_hounsfield(rescaled, required=multi_frame)
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


def _check_hounsfield(rescaled: pydicom.Dataset, *, required: bool) -> None:
    """Check that a slice's Rescale Type, if present, is HU, and that it is
    present where ``required``.

    Raises
    ------
    _Unusable
        With :attr:`SeriesProblem.NOT_HOUNSFIELD` where it names other
        units, or with :attr:`SeriesProblem.UNREADABLE` where it is absent
        but required, or is not one text value.
    """
    if "RescaleType" not in rescaled:
        if required:
            raise _Unusable(SeriesProblem.UNREADABLE)
        return
    try:
        with redacted_diagnostics():
            value = rescaled["RescaleType"].value
    # pydicom raises many types for a value it cannot read, and a message
    # can quote the value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise _Unusable(SeriesProblem.UNREADABLE) from None
    if not isinstance(value, str):
        raise _Unusable(SeriesProblem.UNREADABLE)
    if value.strip().upper() != HOUNSFIELD_UNITS:
        raise _Unusable(SeriesProblem.NOT_HOUNSFIELD)


@dataclasses.dataclass(frozen=True, repr=False)
class KeptSlice:
    """A slice of a defaced series that its face block reaches, with the
    pixels of the block that :class:`CtDefacer` keeps as brain.

    Its ``repr`` shows nothing of it.

    Attributes
    ----------
    position : tuple of float
        Image Position (Patient), in millimetres.
    orientation : tuple of float
        Image Orientation (Patient).
    spacing : tuple of float
        Pixel Spacing: between rows, then between columns, in millimetres.
    kept : numpy.ndarray
        Of bool, rows by columns: the pixels in the block that defacing
        keeps, which no pixel of padding is.
    """

    position: tuple[float, float, float]
    orientation: tuple[float, ...]
    spacing: tuple[float, float]
    kept: np.ndarray

    def __repr__(self) -> str:
        return "KeptSlice()"


def kept_slices(
    block: FaceBlock, positions: Iterable[int], read: Callable[[int], bytes | None]
) -> tuple[KeptSlice, ...]:
    """Return each slice of a defaced series that its block reaches, with
    the pixels that defacing keeps there, in the order of ``positions``,
    and of the frames of each multi-frame instance.

    Parameters
    ----------
    block : FaceBlock
        The series' block.
    positions : iterable of int
        The run positions of the series' instances.
    read : callable
        Gives the file at a run position as the first pass read it, or None.

    Raises
    ------
    ValueError
        Where a slice can no longer be read, without its message.
    """
    slices = []
    for position in positions:
        data = read(position)
        try:
            reached = []
            for index, each in enumerate(_slices(data)):
                inside = block.slice_mask(
                    each.position, each.orientation, each.spacing, each.shape
                )
                if inside.any():
                    reached.append((index, each, inside))
            if not reached:
                continue
            stored = _stored(data, reached[0][1].shape, [i for i, _, _ in reached])
            for (_, each, inside), values in zip(reached, stored, strict=True):
                kept, padded = _kept(block, each, values)
                slices.append(
                    KeptSlice(
                        each.position,
                        each.orientation,
                        each.spacing,
                        inside & kept & ~padded,
                    )
                )
        except (_Unusable, ValueError):
            raise ValueError("a slice can no longer be read") from None
    return tuple(slices)
