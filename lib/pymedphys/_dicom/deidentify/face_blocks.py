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
  Pixel Data of one sample and whole bytes, of one frame for CT Image, and
  a readable Pixel Padding Value and Pixel Padding Range Limit where
  present: native Pixel Data
  (:func:`~pymedphys._dicom.deidentify.pixel_cleaning.layout_of`), or
  compressed Pixel Data whose frames decode, by the plugin pinned to its
  transfer syntax, in the decoding child where that plugin runs native
  code, as Clean Pixel Data decodes them
  (:func:`~pymedphys._dicom.deidentify.pixel_cleaning.decoded_stored_values`),
  after its offset tables and codestream headers are checked;
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
  block from the slices that reach within :data:`HEAD_REACH` millimetres
  of the volume's superior end, by their highest pixel centres, which
  bounds the memory that a long volume needs (:func:`_head_slices`), no
  two slices lying at one position; slices that repeat a position, as
  the time points of a respiratory-correlated CT or a perfusion scan, the
  phases of a contrast study, or two overlapping acquisitions do, are
  parted into phases by the time point or acquisition that each names
  (:func:`~pymedphys._dicom.deidentify.phases.split`), each found from its
  own slices alone, and the series is defaced only where they part
  (:attr:`SeriesProblem.REPEATED_POSITIONS`), lie on one grid within their
  planes (:attr:`SeriesProblem.NOT_ONE_STACK`), and each phase's globes lie
  within :data:`PHASE_REACH` of every other's
  (:attr:`SeriesProblem.PHASES_DISAGREE`), and where each phase gives a
  block, but for one from which the finder finds no globes and whose
  slices the others' block reaches none of; the series is then defaced by
  one block that holds every pixel of its slices that any phase's block
  holds (:func:`_enclosing`), against which targets are judged, and each
  eye against each phase's globes; and
- every target, an ROI whose RT ROI Interpreted Type is
  :data:`TARGET_TYPES`, of any RT Structure Set of the run searched for the
  series (:func:`_searched`), in the series' Frame of Reference, or naming
  none, can be placed, with finite coordinates of magnitude at most
  :data:`_FARTHEST` millimetres, including every reading of a valid contour
  slab (:func:`_spread`),
  and the part in the block of the convex
  hull of its contours, which holds anything between them, lies within the
  slices (:func:`_kept_targets`), so that every pixel that the run keeps for
  it is one that the reviewer sees; no target in another frame, whose
  contours cannot be placed without a registration, has a structure set
  that ties that frame to the series' slices (:func:`_target_points`), a
  target whose ROI names no frame, or one that is malformed, counting as
  one in the series' frame and in each frame that its structure set
  declares; and
- every structure set searched for targets can be read.

Anything else that a series' data raises leaves the series undefaced, as
unreadable, rather than stopping the run, and no message of it, which could
quote a value, is kept. Each instance's pixel data are decoded once for the
finder, and once more for the brain that defacing keeps
(:func:`kept_slices`), a frame at a time, so that a multi-frame instance is
never held decoded whole.

A target that reaches the block is kept: each target, an item of ROI
Contour Sequence, has its own convex hull
(:class:`~pymedphys._dicom.deidentify.target_hulls.TargetHull`), and a
pixel in the block keeps its stored value where its square, given depth
along the slices' normal of half the smallest spacing between the slices
that the block reaches, may meet a hull
(:class:`~pymedphys._dicom.deidentify.target_hulls.KeptTargets`), so that a
release never loses a target to defacing, and the face review's verdict on
the slices as written decides what they keep of the face. A series with a
target that cannot be kept so, as above, is not defaced, and each of its
slices is held for review
(:attr:`~.reasons.VisualFeaturesReason.TARGET_IN_FACE_BLOCK`). Any other
series that is not defaced, such as one without a head, is written as it
would be without a block, and the face review's verdict on it decides, as
for every other instance that can show a face. The outcome of each series
is counted for the release report (:class:`FaceBlockCounts`), by series,
never naming one.

A defaced series' eyes are checked against its globes (:class:`EyeCheck`):
every point of each eye, an ROI in the series' Frame of Reference or naming
none, a malformed frame counting as none (:func:`_roi_frames`), whose ROI
Name names an eye, a globe, or an eyeball (:func:`_is_eye`), of the
structure sets searched for targets, should lie within :data:`EYE_REACH`
millimetres of the nearer globe that the finder found (:func:`_eyes_far`).
Where one does not, or such a set cannot be read again, the block may have
been placed from something else taken for the globes, so the series is
defaced, and each of its slices, and each RT Dose, RT Structure Set, PET
image, and Segmentation cleaned by its block, is held for review
(:attr:`~.reasons.VisualFeaturesReason.EYES_DISAGREE_WITH_ROIS`), with a
sheet of its globes beside its eye ROIs, drawn from its slices as received
(:mod:`~pymedphys._dicom.deidentify.qc_eyes`), for the QC pack. A reviewer
who finds that the globes are the patient's eyes confirms the block, by the
digest that binds it to these slices (:func:`block_digest`), and a later run
given that confirmation defaces the series with the same block, writing the
same pixel data, and holds nothing for the eyes, so that the face verdicts
on the slices as written decide.

A compressed instance of a defaced series is decoded, its block written as
air, and written uncompressed, in Explicit VR Little Endian, as Clean Pixel
Data writes a compressed instance (D-037), since writing into a codestream
would mean encoding it again; one that its block does not reach, or in
which defacing changes no pixel, is written as received
(:attr:`CtDefacer.reaches`). Where its frames decode lossily, the finder,
the brain kept, and the air written all work from the samples decoded,
which are those written.

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
slice's bone does not seal, keeps no part of an eye. A pixel kept for a
target is kept whatever it holds, the eye included.
Where no bone encloses the cavity within a slice, the slice's part in the
block is air, to the top of the slice. Where air's stored value is itself
padding, the pixels written are padding, which a viewer shows as outside
the image, as the air before the face is in most scans.

A slice need not lie along the patient's axes: one turned by a gantry tilt,
or oblique, spans heights, and each of these rules is applied pixel by
pixel, by the pixel's own centre, within the slice's own plane. A pixel is
in the block by its centre, and above the floor by its centre's own
height, so a tilted slice can keep the brain at its top and write air over
the orbit at its front. The tissue that bone encloses joins within the
slice at any height, the floor deciding only what is kept, so a slice
whose front is raised reaches the brain ahead of the plane above the floor
through the brain below the floor, which it writes as air, and keeps it, as
an axial slice through each of its pixels would. A target is judged
against the slices nearest its part in the block
(:class:`~pymedphys._dicom.deidentify.target_hulls.SliceExtent`), since a
tilt that steps the slices along the table offsets each slice's pixels
within the plane from the last's. The finder samples such a stack to voxels
along the patient's axes
(:mod:`~pymedphys._dicom.deidentify.stack_sampling`), and refuses only
what it still cannot take
(:attr:`~pymedphys._dicom.deidentify.defacing.FaceBlockProblem.NOT_ALONG_PATIENT_AXES`).

Beyond CT instances, the run cleans the same region, the block of each
defaced series in the frame in turn, of an RT Dose that
:mod:`~pymedphys._dicom.deidentify.dose_defacing` sets to zero there, of
an RT Structure Set whose contours, or a PET image, of :data:`PET_IODS`,
whose activity, :mod:`~pymedphys._dicom.deidentify.region_defacing` cuts or
sets to zero there, frame by frame for a multi-frame PET image, and of a
Segmentation whose segments
:mod:`~pymedphys._dicom.deidentify.segmentation_defacing` clears there,
each with that frame as its only one but a structure set, whose ROIs in
each defaced frame are cut by that frame's blocks, keeping whatever lies in
a target's hull and on the pixels kept for it. Any other RT
Structure Set, RT Dose with pixel data, PET instance, or Segmentation, and
every Nuclear Medicine image, which the run does not clean
(:data:`UNDEFACED_IODS`), in the Frame of Reference of a defaced series
keeps its contours or pixel data, which can still outline the face, so it
is held for review whatever its verdict, since a reviewer may have judged
it from the defaced CT's previews
(:attr:`~.reasons.VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME`), as
where a series of the frame can no longer be read to find what defacing
keeps (:class:`Defaced`). So is one that names no Frame of Reference, in
a run that defaces any series, or that refers to an instance of a defaced
series whose block does not clean it, whatever frame it declares. A
structure set is searched for targets in the block of a series where it is in the series' frame, names no valid
frame, or is drawn on its slices, and otherwise unless it and every slice
give Patient IDs that differ, and a target in another frame holds a series
whose slices its structure set ties to that frame, whatever other frames
the set declares. Each contour is searched, and cut, wherever its retired
Contour Slab Thickness and Contour Offset Vector may put it
(:mod:`~pymedphys._dicom.deidentify.contour_slabs`).
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import hashlib
import io
import math
import re
import struct
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import scipy

from . import defacing, qc_eyes
from .contour_slabs import SlabRefused, slab_of, slab_values, spread
from .defacing import FaceBlock, FaceBlockProblem, FaceBlockRefused
from .diagnostics import redacted_diagnostics
from .functional_groups import frame_group
from .phases import COINCIDENT, Named, named_by_frame, named_by_instance, split
from .pixel_cleaning import (
    FrameMask,
    Layout,
    PixelDataRefused,
    decoded_stored_values,
    frames_layout,
    stored_range,
)
from .pixel_decoding import DECODING_PLUGINS
from .pseudonyms import SubjectIdentity
from .qc_eyes import EyeSheet
from .reasons import TransformReason
from .references import InstanceRecord
from .sop_classes import iod_for_sop_class
from .source import NATIVE_TRANSFER_SYNTAXES, read_source
from .target_hulls import (
    KeptTargets,
    SliceExtent,
    TargetHull,
    beyond_slices,
    slice_reach,
)
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
# How far, in millimetres, the centre of each globe found from one phase of
# a series whose slices repeat their positions may lie from the same
# globe's centre found from any other phase: half the smallest diameter of
# a globe that the finder accepts, so that each centre lies within the
# other's globe. A placeholder, to be set by validation.
PHASE_REACH = defacing.GLOBE_DIAMETER[0] / 2
# How far, in millimetres, the plane of a block that encloses the blocks of
# a series' phases lies behind the nearest point of theirs, so that a point
# on their boundary is strictly inside it.
_ENCLOSING = 1e-6
NM_IMAGE = "Nuclear Medicine Image"
# The IODs whose instances in a defaced series' Frame of Reference are held
# unless the run cleans them of the face. The run cleans no Nuclear Medicine
# image, so one in such a frame, such as a SPECT volume reconstructed in a
# SPECT/CT's frame, is always held.
UNDEFACED_IODS = frozenset(
    {RT_STRUCTURE_SET, "RT Dose", *PET_IODS, NM_IMAGE, "Segmentation"}
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
    # compressed Pixel Data whose frames cannot be decoded for defacing:
    # without its decoder, or with an offset table, codestream header, or
    # frame that does not match its attributes or does not decode
    UNDECODABLE = "undecodable-pixel-data"
    # slices or frames of more than one sample, orientation, size, spacing,
    # or Frame of Reference, a CT Image instance of more than one frame, or
    # phases whose slices are not placed on one grid within their planes
    NOT_ONE_STACK = "not-one-stack"
    # slices at one position that no time point or acquisition that they
    # name parts into phases (phases.split)
    REPEATED_POSITIONS = "repeated-positions"
    # phases whose globes lie apart, as a head moved between them, or
    # globes found wrongly in one of them, would leave them
    PHASES_DISAGREE = "phases-disagree"
    # stored values whose Rescale Type is not Hounsfield units, as a
    # material map of a multi-energy CT can be
    NOT_HOUNSFIELD = "not-hounsfield-units"
    # stored values that cannot hold air without clipping
    AIR_NOT_STORED = "air-not-stored"
    # a target that may reach the block where the run cannot keep it: one
    # in another frame that its structure set ties to the series' slices,
    # one with a coordinate that cannot be placed, or one whose hull reaches
    # beyond the slices in the block, or a structure set searched for
    # targets that cannot be read
    TARGET_IN_BLOCK = "target-in-block"
    # an eye's contour in the series' frame away from the globes found: not
    # a reason to leave a series undefaced, but why a defaced series is held
    # until a reviewer confirms its block (EyeCheck.DISAGREE)
    EYES_DISAGREE = "eyes-disagree-with-rois"


class EyeCheck(enum.Enum):
    """How a defaced series' eye ROIs compare with the globes that its block
    was found from (:func:`_eyes_far`)."""

    # every eye ROI searched lies within EYE_REACH of the nearer globe, or
    # none is drawn
    AGREE = "agree"
    # an eye ROI does not, or a structure set searched for it cannot be read,
    # and no reviewer has confirmed the block: the series is defaced, and
    # each of its slices, and each instance cleaned by its block, is held
    DISAGREE = "disagree"
    # likewise, but the face review confirms this block of these slices
    # (FaceReview.confirmed_blocks), so nothing is held for the eyes
    CONFIRMED = "confirmed"


@dataclasses.dataclass(frozen=True)
class SeriesDefacing:
    """The outcome of one CT series.

    Attributes
    ----------
    block : FaceBlock or None
        The block written as air, or None where the series is not defaced.
    problem : FaceBlockProblem or SeriesProblem or None
        Why the series is not defaced, or None where it is. Never
        :attr:`SeriesProblem.EYES_DISAGREE`, which holds a defaced series
        (:attr:`hold`) rather than leaving it undefaced.
    frame : str, optional
        The Frame of Reference UID of a defaced series; None for any other.
    targets : KeptTargets, optional
        The hulls of the targets that defacing keeps in a defaced series'
        block; none for any other series.
    eyes : EyeCheck, optional
        How a defaced series' eye ROIs compare with its globes;
        :attr:`EyeCheck.AGREE` for any other series.
    block_sha256 : bytes, optional
        For a defaced series whose eyes are not :attr:`EyeCheck.AGREE`, the
        digest that binds a reviewer's confirmation to its block
        (:func:`block_digest`); None for any other.
    sheet : EyeSheet, optional
        For a series held as :attr:`EyeCheck.DISAGREE`, the QC pack's
        preview of its globes beside its eye ROIs
        (:func:`~pymedphys._dicom.deidentify.qc_eyes.eye_sheet`), where it
        could be drawn; None otherwise. Not compared.
    """

    block: FaceBlock | None
    problem: FaceBlockProblem | SeriesProblem | None
    frame: str | None = None
    targets: KeptTargets = KeptTargets()
    eyes: EyeCheck = EyeCheck.AGREE
    block_sha256: bytes | None = None
    sheet: EyeSheet | None = dataclasses.field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if (self.block is None) == (self.problem is None):
            raise ValueError("a series has a block or a problem, not both")
        if (self.frame is None) != (self.block is None) or self.frame == "":
            raise ValueError("a defaced series has its Frame of Reference UID")
        if self.block is None and self.targets.hulls:
            raise ValueError("only a defaced series keeps targets")
        if self.problem is SeriesProblem.EYES_DISAGREE:
            raise ValueError("eyes that disagree hold a defaced series")
        if not isinstance(self.eyes, EyeCheck) or (
            self.block is None and self.eyes is not EyeCheck.AGREE
        ):
            raise ValueError("only a defaced series has its eyes checked")
        if (self.eyes is EyeCheck.AGREE) != (self.block_sha256 is None) or not (
            self.block_sha256 is None
            or (isinstance(self.block_sha256, bytes) and len(self.block_sha256) == 32)
        ):
            raise ValueError(
                "a series whose eyes disagree has its block's SHA-256, and no other"
            )
        if self.sheet is not None and self.eyes is not EyeCheck.DISAGREE:
            raise ValueError("only a series held for its eyes has their sheet")

    @property
    def hold(self) -> SeriesProblem | None:
        """Why the series' slices are held for review, if they are: a
        target lies in its block where the run cannot keep it, and the
        series is not defaced; or an eye's contour lies away from the
        globes that its block was found from, and no reviewer has confirmed
        the block, so the series is defaced and held."""
        if self.problem is SeriesProblem.TARGET_IN_BLOCK:
            return SeriesProblem.TARGET_IN_BLOCK
        if self.eyes is EyeCheck.DISAGREE:
            return SeriesProblem.EYES_DISAGREE
        return None

    @property
    def held(self) -> bool:
        """Whether the series' slices are held for review (:attr:`hold`)."""
        return self.hold is not None


@dataclasses.dataclass
class FaceBlockCounts:
    """How many CT series a run defaced, how many of those around a target,
    how many of those whose eye ROIs disagree with their globes, held for a
    reviewer to confirm the block or released with a confirmed block, and
    how many it did not deface, by why.

    Filled by :meth:`record`, once a run has found its face blocks, for the
    release report's ``face_review.ct_series``. A series counts as defaced
    where the run found its block and set out to deface it, whatever then
    became of its slices, as defaced around targets where it also keeps
    a target's hull that reaches the block (:class:`KeptTargets`), and by
    its eyes where they are not :attr:`EyeCheck.AGREE`.
    """

    defaced: int = 0
    not_defaced: dict[FaceBlockProblem | SeriesProblem, int] = dataclasses.field(
        default_factory=dict
    )
    around_targets: int = 0
    eyes_unconfirmed: int = 0
    eyes_confirmed: int = 0

    def record(self, outcomes: Iterable[SeriesDefacing]) -> None:
        """Count each series' outcome, in place of any counted before."""
        defaced = around_targets = 0
        eyes: collections.Counter[EyeCheck] = collections.Counter()
        not_defaced: collections.Counter[FaceBlockProblem | SeriesProblem] = (
            collections.Counter()
        )
        for outcome in outcomes:
            if outcome.problem is None:
                defaced += 1
                around_targets += outcome.targets.in_block
                eyes[outcome.eyes] += 1
            else:
                not_defaced[outcome.problem] += 1
        self.defaced = defaced
        self.not_defaced = dict(not_defaced)
        self.around_targets = around_targets
        self.eyes_unconfirmed = eyes[EyeCheck.DISAGREE]
        self.eyes_confirmed = eyes[EyeCheck.CONFIRMED]


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
    # What the slice names of its phase (phases.split).
    named: Named
    compressed: bool = False


class _Unusable(Exception):
    """A series that is not defaced, for :attr:`problem`."""

    def __init__(self, problem: SeriesProblem) -> None:
        super().__init__(problem.value)
        self.problem = problem


def find_face_blocks(
    records: Mapping[int, InstanceRecord],
    read: Callable[[int], bytes | None],
    confirmed: Collection[bytes] = frozenset(),
    *,
    sheets: bool = True,
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
    confirmed : collection of bytes, optional
        The :func:`block_digest` of each block that a reviewer confirmed in
        an earlier run's QC pack, after its series' eye ROIs disagreed with
        its globes (:attr:`~.face_review.FaceReview.confirmed_blocks`); none
        by default. A series whose eyes disagree is defaced, and held as
        :attr:`EyeCheck.DISAGREE` with the sheet that shows its globes beside
        its eye ROIs, unless its block's digest is among these, when it is
        :attr:`EyeCheck.CONFIRMED`.
    sheets : bool, optional
        Whether to draw that sheet, which only a run's QC pack needs; by
        default it is drawn.
    """
    return {
        uid: outcome
        for uid, (outcome, _) in _outcomes(
            records, read, confirmed, sheets=sheets
        ).items()
    }


def _outcomes(
    records: Mapping[int, InstanceRecord],
    read: Callable[[int], bytes | None],
    confirmed: Collection[bytes] = frozenset(),
    *,
    sheets: bool = True,
) -> dict[str, tuple[SeriesDefacing, _Found]]:
    """Each series' outcome, as :func:`find_face_blocks` gives it, with what
    was found of it before its holds, for the DICOM check (D-054)."""
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
    outcomes: dict[str, tuple[SeriesDefacing, _Found]] = {}
    for uid, positions in series.items():
        found = _series_found(positions, read)
        outcome, frame = found.outcome, found.frame
        if outcome.block is not None and frame:
            searched = [
                position
                for position in structure_sets
                if _searched(records[position], frame, slices[uid], positions, records)
            ]
            targets = _placed_targets(frame, slices[uid], searched, read)
            kept = (
                None
                if targets is None
                else _kept_targets(outcome.block, _distinct(found.slices), targets)
            )
            if kept is None:
                outcome = SeriesDefacing(None, SeriesProblem.TARGET_IN_BLOCK)
            else:
                outcome = _eyes_outcome(
                    SeriesDefacing(outcome.block, None, frame, kept),
                    positions,
                    searched,
                    read,
                    confirmed,
                    sheets,
                    blocks=found.blocks,
                )
        outcomes[uid] = (outcome, found)
    return outcomes


def _eyes_outcome(
    outcome: SeriesDefacing,
    positions: list[int],
    searched: list[int],
    read: Callable[[int], bytes | None],
    confirmed: Collection[bytes],
    sheets: bool,
    *,
    blocks: Sequence[FaceBlock] = (),
) -> SeriesDefacing:
    """A defaced series' outcome with its eyes checked against its globes
    (:func:`_eye_check`): as given where they agree, and otherwise with its
    block's digest, confirmed where that is among ``confirmed``, or held
    with the sheet that shows its globes beside its eye ROIs."""
    block, frame = outcome.block, outcome.frame
    assert block is not None and frame is not None
    disagree, contours = _eye_check(block, frame, searched, read, blocks=blocks)
    if not disagree:
        return outcome
    digest = block_digest(_source_digests(positions, read), block)
    if digest in confirmed:
        return dataclasses.replace(
            outcome, eyes=EyeCheck.CONFIRMED, block_sha256=digest
        )
    return dataclasses.replace(
        outcome,
        eyes=EyeCheck.DISAGREE,
        block_sha256=digest,
        sheet=_eye_sheet(block, positions, read, contours) if sheets else None,
    )


# Labels the digest that binds a reviewer's confirmation to a block.
_BLOCK_DIGEST_LABEL = b"pymedphys-deid-face-block/1"


def block_digest(sources: Iterable[bytes], block: FaceBlock) -> bytes:
    """Return the SHA-256 that binds a reviewer's confirmation of a face
    block to the block and to the files that it was found from.

    It is of a label, the count and sorted SHA-256 of the series' source
    files, and the block's origin, anterior normal, inferior limit, and
    globe centres as 64-bit big-endian floating-point numbers, so that a
    confirmation covers this block of these files and no other: a slice
    changed, added, or left out, or a block found otherwise, as by another
    version of the finder, gives another digest, which no confirmation
    covers.

    Parameters
    ----------
    sources : iterable of bytes
        The SHA-256 of each source file of the series.
    block : FaceBlock
    """
    files = sorted(sources)
    if not all(isinstance(each, bytes) and len(each) == 32 for each in files):
        raise ValueError("a block's sources are SHA-256 digests")
    values = (
        *block.origin,
        *block.anterior,
        block.inferior_limit,
        *block.globes[0],
        *block.globes[1],
    )
    digest = hashlib.sha256(_BLOCK_DIGEST_LABEL)
    digest.update(struct.pack(">Q", len(files)))
    for each in files:
        digest.update(each)
    digest.update(struct.pack(f">{len(values)}d", *(float(v) for v in values)))
    return digest.digest()


def _source_digests(
    positions: Iterable[int], read: Callable[[int], bytes | None]
) -> list[bytes]:
    """The SHA-256 of each file at ``positions``, as the first pass read it;
    of no bytes for one that can no longer be read, which then gives no
    block anyway."""
    return [hashlib.sha256(read(position) or b"").digest() for position in positions]


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
    (:func:`_target_points`).
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
    unconfirmed : frozenset of str, optional
        Of ``frames``, those of a series held until a reviewer confirms its
        block (:attr:`EyeCheck.DISAGREE`), in which an instance that the run
        cleans by that block is held for the same reason; none by default.
    """

    frames: frozenset[str] = frozenset()
    instances: frozenset[str] = frozenset()
    unconfirmed: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.unconfirmed <= self.frames:
            raise ValueError("an unconfirmed block's frame is a defaced frame")

    def __repr__(self) -> str:
        return (
            f"Defaced(frames={len(self.frames)}, instances={len(self.instances)}, "
            f"unconfirmed={len(self.unconfirmed)})"
        )

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
        frozenset(
            outcome.frame
            for outcome in outcomes.values()
            if outcome.frame is not None and outcome.eyes is EyeCheck.DISAGREE
        ),
    )


@dataclasses.dataclass(frozen=True)
class _Found:
    """One series' outcome, its Frame of Reference UID, the block found
    from each of its phases that gave one, in the order of the phases, how
    many phases its slices were parted into, or None where they were not,
    and how many of a series of several phases found no eyes, of those
    searched before the finder stopped, and its slices, where they can be
    read.

    The blocks are given for a series that is not defaced too, such as one
    whose phases disagree, so that how far apart their globes lie can be
    measured (D-054)."""

    outcome: SeriesDefacing
    frame: str | None
    blocks: tuple[FaceBlock, ...] = ()
    phases: int | None = None
    eyeless: int = 0
    slices: tuple[_Slice, ...] = ()


def _series_outcome(
    positions: list[int], read: Callable[[int], bytes | None]
) -> tuple[SeriesDefacing, str | None, list[_Slice]]:
    """Find one series' block, or why it has none, its Frame of Reference
    UID, and its slices, where they can be read."""
    found = _series_found(positions, read)
    return found.outcome, found.frame, list(found.slices)


def _series_found(positions: list[int], read: Callable[[int], bytes | None]) -> _Found:
    """Find one series' block, or why it has none, its Frame of Reference
    UID, its slices, where they can be read, and the block of each of its
    phases.

    A series whose slices repeat their positions is found phase by phase
    (:func:`_phases`), each phase's block from its own slices, as the
    module describes; the series' block encloses them all
    (:func:`_enclosing`).
    """
    frame: str | None = None
    slices: list[_Slice] = []
    # How many phases the slices are parted into, once known, and of those
    # how many find no eyes, once every phase is searched.
    parted: int | None = None
    eyeless: list[list[int]] = []
    blocks: list[FaceBlock] = []

    def found(
        problem: FaceBlockProblem | SeriesProblem | None,
        block: FaceBlock | None = None,
    ) -> _Found:
        outcome = SeriesDefacing(block, problem, None if block is None else frame)
        return _Found(
            outcome, frame, tuple(blocks), parted, len(eyeless), tuple(slices)
        )

    try:
        slices, places = _stack(positions, read)
        first = slices[0]
        frame = first.frame
        # Without one, no structure set's targets can be checked against
        # the block.
        if not frame:
            raise _Unusable(SeriesProblem.UNREADABLE)
        groups = _phases(slices)
        parted = len(groups)
        for group in groups:
            finder = _finder(
                [slices[i] for i in group],
                [places[i] for i in group],
                read,
            )
            try:
                blocks.append(finder.block())
            except FaceBlockRefused as refused:
                # Only a phase of several that finds no globes may be left
                # to the block of the others, and only where that reaches
                # none of its slices, checked once every block is found.
                if len(groups) == 1 or refused.problem is not FaceBlockProblem.NO_EYES:
                    raise
                eyeless.append(group)
        if not blocks:
            raise FaceBlockRefused(FaceBlockProblem.NO_EYES)
        # Every phase's block is found before they are compared, so that a
        # series whose phases disagree gives each of them to be measured.
        if not _agree(blocks):
            return found(SeriesProblem.PHASES_DISAGREE)
        block = blocks[0] if len(groups) == 1 else _enclosing(blocks, slices)
        if any(_reaches(block, slices[i]) for group in eyeless for i in group):
            raise FaceBlockRefused(FaceBlockProblem.NO_EYES)
        return found(None, block)
    except _Unusable as unusable:
        return found(unusable.problem)
    except FaceBlockRefused as refused:
        return found(refused.problem)
    # Whatever else a series' data raises, such as the finder's ValueError
    # for geometry that it cannot use, or MemoryError for a volume too large
    # to sample, leaves the series undefaced rather than stopping the run;
    # its message, which can quote a value, is dropped.
    except Exception:  # pylint: disable = broad-exception-caught
        return found(SeriesProblem.UNREADABLE)


def _phases(slices: list[_Slice]) -> list[list[int]]:
    """The indices of each phase's slices, as :func:`~.phases.split` parts
    them by their heights along the first slice's normal.

    Raises
    ------
    _Unusable
        With :attr:`SeriesProblem.REPEATED_POSITIONS` where the slices
        repeat a position but cannot be parted, and with
        :attr:`SeriesProblem.NOT_ONE_STACK` where they are parted into more
        than one phase but do not all lie on the first slice's grid within
        their planes, within
        :data:`~pymedphys._dicom.deidentify.defacing.STACKING_TOLERANCE`, so
        that the slices at one position of two phases are of the same
        pixels' centres.
    """
    first = slices[0]
    normal = np.cross(first.orientation[:3], first.orientation[3:])
    origins = np.array([each.position for each in slices], dtype=float)
    heights = origins @ normal
    groups = split([float(height) for height in heights], [s.named for s in slices])
    if groups is None:
        raise _Unusable(SeriesProblem.REPEATED_POSITIONS)
    if len(groups) > 1:
        in_plane = (origins - origins[0]) - np.outer(heights - heights[0], normal)
        if np.abs(in_plane).max() > defacing.STACKING_TOLERANCE:
            raise _Unusable(SeriesProblem.NOT_ONE_STACK)
    return groups


def _distinct(slices: Sequence[_Slice]) -> list[_Slice]:
    """One slice at each position along the first slice's normal: of
    slices within :data:`~.phases.COINCIDENT` of the lowest of them, the
    lowest, and of two at one height the earlier; in their order.

    A target is judged against these (:func:`_kept_targets`), so that the
    slices of two phases at one position, which lie on one grid, place it
    as one slice would, rather than as two slices a micrometre apart.
    """
    if not slices:
        return []
    first = slices[0]
    normal = np.cross(first.orientation[:3], first.orientation[3:])
    heights = [float(np.dot(each.position, normal)) for each in slices]
    order = sorted(range(len(slices)), key=lambda index: (heights[index], index))
    kept: list[int] = []
    for index in order:
        if not kept or heights[index] - heights[kept[-1]] > COINCIDENT:
            kept.append(index)
    return [slices[index] for index in sorted(kept)]


def _agree(blocks: Sequence[FaceBlock]) -> bool:
    """Whether each globe's centre in each block lies within
    :data:`PHASE_REACH` of the same globe's centre in every other."""
    globes = np.array([block.globes for block in blocks], dtype=float)
    apart = np.linalg.norm(globes[:, np.newaxis] - globes[np.newaxis, :], axis=-1)
    return bool(np.all(apart <= PHASE_REACH))


def _reaches(block: FaceBlock, each: _Slice) -> bool:
    """Whether a block holds the centre of any pixel of a slice."""
    return bool(
        block.slice_mask(
            each.position, each.orientation, each.spacing, each.shape
        ).any()
    )


def _enclosing(blocks: Sequence[FaceBlock], slices: Sequence[_Slice]) -> FaceBlock:
    """One block that holds every pixel of the slices that any of the
    phases' blocks holds.

    Its plane faces the mean of their anterior directions, and lies
    :data:`_ENCLOSING` behind the point furthest back along it of each
    block's region within the slices' extent across the axial plane, the
    rectangle of their pixels' centres, which the finder has placed along
    the patient's axes; its inferior limit is the lowest of theirs; and its
    globes are those of the block whose higher globe is highest, so that
    the brain is kept above the highest floor (:data:`CAVITY_FLOOR`). Both
    planes of each block are vertical or horizontal, so its region within
    the extent is the rectangle cut by its vertical plane, and the point
    furthest back along the enclosing plane's normal is one of that
    region's corners.
    """
    anterior = np.sum([block.anterior for block in blocks], axis=0)
    anterior[2] = 0.0
    anterior /= np.linalg.norm(anterior)
    corners = np.concatenate([_corners(each) for each in slices])
    low, high = corners[:, :2].min(axis=0), corners[:, :2].max(axis=0)
    rectangle = np.array(
        [[low[0], low[1]], [high[0], low[1]], [high[0], high[1]], [low[0], high[1]]]
    )
    nearest = math.inf
    for block in blocks:
        region = _cut(
            rectangle, np.array(block.anterior[:2]), np.array(block.origin[:2])
        )
        if len(region):
            nearest = min(nearest, float(np.min(region @ anterior[:2])))
    origin = np.array(blocks[0].origin, dtype=float)
    if math.isfinite(nearest):
        origin += (nearest - _ENCLOSING - float(origin @ anterior)) * anterior
    highest = max(blocks, key=lambda block: max(globe[2] for globe in block.globes))
    return FaceBlock(
        (float(origin[0]), float(origin[1]), float(origin[2])),
        (float(anterior[0]), float(anterior[1]), float(anterior[2])),
        min(block.inferior_limit for block in blocks),
        highest.globes,
    )


def _corners(each: _Slice) -> np.ndarray:
    """The x, y, and z of the centres of a slice's four corner pixels."""
    rows, columns = each.shape
    along_row = np.asarray(each.orientation[:3], dtype=float) * each.spacing[1]
    down_column = np.asarray(each.orientation[3:], dtype=float) * each.spacing[0]
    origin = np.asarray(each.position, dtype=float)
    return np.array(
        [
            origin + row * down_column + column * along_row
            for row in (0, rows - 1)
            for column in (0, columns - 1)
        ]
    )


def _cut(polygon: np.ndarray, normal: np.ndarray, point: np.ndarray) -> np.ndarray:
    """The vertices of the part of a convex polygon, in order, on the side of
    a line through ``point`` that ``normal`` points to, the line included,
    by clipping the polygon against it."""
    sides = (polygon - point) @ normal
    kept = []
    for index, vertex in enumerate(polygon):
        following = polygon[(index + 1) % len(polygon)]
        side, next_side = sides[index], sides[(index + 1) % len(polygon)]
        if side >= 0:
            kept.append(vertex)
        if (side < 0 < next_side) or (next_side < 0 < side):
            kept.append(vertex + side / (side - next_side) * (following - vertex))
    return np.array(kept).reshape(-1, 2)


def inspect_series(
    positions: list[int], read: Callable[[int], bytes | None]
) -> defacing.FaceInspection | None:
    """What the finder finds in one series' slices, as a run gives them to
    it, or None where it is given none, for a check on reference masks: the
    slices of its first phase, where they repeat their positions
    (:func:`_phases`).

    Parameters
    ----------
    positions : list of int
        The run positions of the series' CT instances.
    read : callable
        As for :func:`find_face_blocks`.
    """
    try:
        slices, places = _stack(positions, read)
        group = _phases(slices)[0]
        return _finder(
            [slices[i] for i in group],
            [places[i] for i in group],
            read,
        ).inspect()
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
    # By instance, in run order, then by frame, the order in which they are
    # added, which the finder needs their positions in.
    by_instance: dict[int, list[int]] = {}
    for index in _head_slices(slices):
        by_instance.setdefault(places[index][0], []).append(index)
    order = [index for indices in by_instance.values() for index in indices]
    finder = defacing.FaceFinder(
        first.orientation,
        [slices[i].position for i in order],
        first.spacing,
        first.shape,
    )
    for position, indices in by_instance.items():
        stored = _stored(
            read(position),
            first.shape,
            [places[i][1] for i in indices],
            compressed=slices[indices[0]].compressed,
        )
        for index, values in zip(indices, stored, strict=True):
            finder.add(_hounsfield(values, slices[index]))
    return finder


def _head_slices(slices: Sequence[_Slice]) -> list[int]:
    """Return the index of each slice that reaches within :data:`HEAD_REACH`
    millimetres of the volume's superior end, in order.

    A slice reaches as high as its highest pixel centre (:func:`_top`), and
    the volume's superior end is the highest of them all. So of an axial
    stack, each slice at one height, the slices within reach of the top
    slice are taken; of a sagittal or coronal stack, whose every slice
    spans the volume's height, every slice is; and of a stack turned by a
    gantry tilt, or oblique, whose slices each span heights, each slice of
    which any pixel lies within reach, whole, so that each slice that the
    finder is given is the whole of its pixel data.
    """
    tops = [_top(each) for each in slices]
    highest = max(tops)
    return [index for index, top in enumerate(tops) if top >= highest - HEAD_REACH]


def _top(each: _Slice) -> float:
    """The z coordinate of a slice's highest pixel centre, in millimetres:
    its first pixel's, raised along its rows and down its columns wherever
    they rise."""
    rows, columns = each.shape
    row_spacing, column_spacing = each.spacing
    along_row, down_column = each.orientation[2], each.orientation[5]
    return (
        each.position[2]
        + max(0.0, (rows - 1) * row_spacing * down_column)
        + max(0.0, (columns - 1) * column_spacing * along_row)
    )


def _slices(data: bytes | None) -> tuple[_Slice, ...]:
    """Read what defacing needs of each slice of one instance: the instance
    itself, of CT Image, or each frame of a multi-frame instance, of native
    Pixel Data or compressed in a transfer syntax that a run decodes
    (:data:`~.pixel_decoding.DECODING_PLUGINS`), whose frames are described
    as they are held once decoded.

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
    compressed = syntax not in NATIVE_TRANSFER_SYNTAXES
    if compressed and syntax not in DECODING_PLUGINS:
        raise _Unusable(SeriesProblem.UNDECODABLE)
    try:
        layout = frames_layout(dataset, syntax)
    except PixelDataRefused:
        raise _Unusable(SeriesProblem.UNREADABLE) from None
    described = _described(dataset, layout)
    if not compressed:
        return described
    return tuple(dataclasses.replace(each, compressed=True) for each in described)


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
    data: bytes | None,
    shape: tuple[int, int],
    frames: Sequence[int],
    *,
    compressed: bool = False,
) -> Iterator[np.ndarray]:
    """The stored values of each of an instance's ``frames``, in ascending
    order, rows by columns, decoded one at a time, as
    :func:`~.pixel_cleaning.decoded_stored_values` decodes them where they
    are ``compressed``.

    Raises
    ------
    _Unusable
        If the file can no longer be read, or its pixel data decoded as
        that many frames of that shape.
    """
    if data is None:
        raise _Unusable(SeriesProblem.UNREADABLE)
    if compressed:
        yield from _decoded(data, shape, frames)
        return
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


def _decoded(
    data: bytes, shape: tuple[int, int], frames: Sequence[int]
) -> Iterator[np.ndarray]:
    """The stored values of each of a compressed instance's ``frames``, in
    ascending order, rows by columns, decoded one at a time as
    :func:`~.pixel_cleaning.black_out` decodes them, so that defacing finds
    its block and keeps its brain in the samples that it writes air into.

    Raises
    ------
    _Unusable
        With :attr:`SeriesProblem.UNDECODABLE` where the frames cannot be
        decoded, and with :attr:`SeriesProblem.UNREADABLE` where the file
        cannot be read, or its frames are not of that number or shape, or
        hold more than their values in the bits above Bits Stored.
    """
    try:
        with redacted_diagnostics():
            source = read_source(data)
            dataset = source.dataset()
    # The reader raises many types for a file that it cannot read, and a
    # message can quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise _Unusable(SeriesProblem.UNREADABLE) from None
    wanted = sorted(frames)
    given = 0
    try:
        for stored in decoded_stored_values(source, dataset, wanted):
            if stored.shape != shape or given >= len(wanted):
                raise _Unusable(SeriesProblem.UNREADABLE)
            given += 1
            yield stored
    except PixelDataRefused as refused:
        raise _Unusable(
            SeriesProblem.UNREADABLE
            if refused.reason is TransformReason.UNCLEANABLE_PIXEL_DATA
            else SeriesProblem.UNDECODABLE
        ) from None
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


def _placed_targets(
    frame: str,
    slices: set[str],
    positions: list[int],
    read: Callable[[int], bytes | None],
) -> list[np.ndarray] | None:
    """Return the points of each target of these structure sets that may be
    in the Frame of Reference of the series with these slices, as
    :func:`_target_points` places them, or None where a target cannot be
    placed or a structure set cannot be read."""
    found: list[np.ndarray] = []
    for position in positions:
        try:
            with redacted_diagnostics():
                dataset = pydicom.dcmread(io.BytesIO(read(position) or b""))
                points = _target_points(dataset, frame, slices)
        # pydicom raises many types for a file it cannot read, and a message
        # can quote a value: a target in it cannot be ruled out.
        except Exception:  # pylint: disable = broad-exception-caught
            return None
        if points is None:
            return None
        found.extend(points)
    return found


class TargetFate(enum.Enum):
    """What defacing does with a target placed in a series' frame, by its
    convex hull (:func:`_target_fates`)."""

    # Its hull cannot meet the block, or a box of a pixel in it.
    CLEAR = "clear"
    # Its hull may meet a box of a pixel in the block, but not the block
    # itself: defacing keeps the pixels that it reaches.
    NEAR = "near"
    # Its hull reaches the block within the slices: defacing keeps the
    # pixels that it reaches, and writes air in the rest of the block.
    KEPT = "kept-in-block"
    # Its hull's part in the block reaches beyond the slices, where no
    # image shows it: the series is held.
    BEYOND_SLICES = "beyond-slices"


@dataclasses.dataclass(frozen=True)
class _TargetFates:
    """How :func:`_target_fates` judges targets against one series' block
    and slices."""

    block: FaceBlock
    widened: FaceBlock
    extent: SliceExtent
    depth: float

    def fate(self, points: np.ndarray) -> tuple[TargetFate, TargetHull | None]:
        """Judge a target by its points, with its hull where it may reach a
        pixel in the block."""
        if not _hull_reaches(self.widened, points):
            return TargetFate.CLEAR, None
        hull = TargetHull.of(points)
        if not _hull_reaches(self.block, points):
            return TargetFate.NEAR, hull
        if beyond_slices(hull, self.block, self.extent):
            return TargetFate.BEYOND_SLICES, hull
        return TargetFate.KEPT, hull


def _target_fates(block: FaceBlock, stack: Sequence[_Slice]) -> _TargetFates:
    """Judge targets against a series' block and its slices.

    The pixels' boxes reach along the slices' normal half the smallest
    spacing between the slices that the block reaches, as
    :class:`~pymedphys._dicom.deidentify.dose_defacing.DoseBlock` places
    instances on them. A hull may meet a box of a pixel in the block only
    if it meets the block moved out by the boxes' half edges, which hold
    every box's corner.
    """
    reached = [
        each
        for each in stack
        if block.slice_mask(
            each.position, each.orientation, each.spacing, each.shape
        ).any()
    ] or list(stack)
    first = reached[0]
    normal = np.cross(first.orientation[:3], first.orientation[3:])
    depth = slice_reach(
        (float(np.dot(each.position, normal)) for each in reached), first.spacing
    )
    # A millimetre more allows for direction cosines that are not quite of
    # unit length; a hull kept needlessly keeps nothing.
    margin = sum(first.spacing) / 2 + depth + 1.0
    anterior = np.asarray(block.anterior, dtype=float)
    widened = dataclasses.replace(
        block,
        origin=tuple(float(v) for v in np.asarray(block.origin) - margin * anterior),
        inferior_limit=block.inferior_limit - margin,
    )
    extent = SliceExtent.of(
        [(each.position, each.orientation) for each in stack],
        first.spacing,
        first.shape,
        depth,
    )
    return _TargetFates(block, widened, extent, depth)


def _kept_targets(
    block: FaceBlock, stack: Sequence[_Slice], targets: Sequence[np.ndarray]
) -> KeptTargets | None:
    """Return the hulls of the targets that defacing keeps in a series'
    block, as :func:`_target_fates` judges them, or None where a target's
    hull reaches beyond the slices there."""
    if not targets:
        return KeptTargets()
    fates = _target_fates(block, stack)
    hulls = []
    in_block = False
    for points in targets:
        fate, hull = fates.fate(points)
        if fate is TargetFate.BEYOND_SLICES:
            return None
        if hull is not None:
            hulls.append(hull)
            in_block = in_block or fate is TargetFate.KEPT
    return KeptTargets(tuple(hulls), fates.depth, in_block)


def _eye_check(
    block: FaceBlock,
    frame: str,
    positions: list[int],
    read: Callable[[int], bytes | None],
    *,
    blocks: Sequence[FaceBlock] = (),
) -> tuple[bool, list[list[tuple[str, np.ndarray]]]]:
    """Whether an eye of any of these structure sets disagrees with the
    globes that the block of the series with this Frame of Reference was
    found from, as :func:`_eyes_far` judges it, or a set cannot be read,
    with each eye ROI's contours of the sets that can be
    (:func:`_eye_contours`), for the sheet that shows them."""
    disagree = False
    contours: list[list[tuple[str, np.ndarray]]] = []
    for position in positions:
        try:
            with redacted_diagnostics():
                dataset = pydicom.dcmread(io.BytesIO(read(position) or b""))
                found = _eye_contours(dataset, frame)
                # Every phase must agree; confirmation still binds the enclosing
                # block to every original source file of the series.
                disagree = disagree or any(
                    _eyes_far(dataset, frame, each) for each in blocks or (block,)
                )
        # As for a target, an eye in a file that cannot be read cannot be
        # checked.
        except Exception:  # pylint: disable = broad-exception-caught
            disagree = True
            continue
        contours.extend(found)
    return disagree, contours


def _eyes_disagree(
    block: FaceBlock,
    frame: str,
    positions: list[int],
    read: Callable[[int], bytes | None],
) -> bool:
    """Whether an eye of any of these structure sets disagrees with the
    globes that the block was found from, or a set cannot be read
    (:func:`_eye_check`)."""
    return _eye_check(block, frame, positions, read)[0]


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
    or naming none, whose name is an eye's (:func:`_is_eye`), or of a
    point's span, lies farther than :data:`EYE_REACH` from both of the
    block's globes' centres, or cannot be placed (:func:`_eye_far`).

    So an eye drawn where the finder found no globe, as where it took
    something else for one, holds the series until a reviewer confirms its
    block. Each eye is checked alone, or both together in one ROI, but an
    eye that the structure set does not draw, or names otherwise, is not
    checked, nor is one in another frame, which cannot be placed in the
    series' without a registration. An ROI's frame is taken as for a target
    (:func:`_roi_frames`), so one that is malformed, or that its set does
    not declare, counts as naming none, and the eye is checked.
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
            if _eye_far(contour, globes):
                return True
    return False


def _eye_contours(
    dataset: pydicom.Dataset, frame: str
) -> list[list[tuple[str, np.ndarray]]]:
    """Each eye ROI's contours, as :func:`_eyes_far` selects the ROIs, by
    item of the ROI Contour Sequence: each contour's Contour Geometric
    Type, stripped and upper case, and its points, x, y, and z along the
    last axis.

    Raises
    ------
    Exception
        Whatever pydicom or NumPy raises for a value that cannot be read,
        such as Contour Data that are not numbers in threes.
    """
    frames_of_roi = _roi_frames(dataset)
    eyes = {
        int(item.ROINumber)
        for item in dataset.get("StructureSetROISequence") or []
        if frames_of_roi(int(item.ROINumber)) & {"", frame}
        and _is_eye(str(item.get("ROIName") or ""))
    }
    found = []
    for item in dataset.get("ROIContourSequence") or []:
        if int(item.ReferencedROINumber) not in eyes:
            continue
        found.append(
            [
                (
                    str(contour.get("ContourGeometricType") or "").strip().upper(),
                    np.asarray([float(v) for v in contour.ContourData]).reshape(-1, 3),
                )
                for contour in item.get("ContourSequence") or []
            ]
        )
    return found


def _contours_far(
    rois: Iterable[Iterable[tuple[str, np.ndarray]]], block: FaceBlock
) -> bool:
    """Whether a point of these eye ROIs' contours lies farther than
    :data:`EYE_REACH` from both of the block's globes' centres, or is not a
    number."""
    for contours in rois:
        for _, points in contours:
            # Written so that a coordinate that is not a number fails it too.
            if not (eye_distances(points, block) <= EYE_REACH).all():
                return True
    return False


def eye_distances(points: np.ndarray, block: FaceBlock) -> np.ndarray:
    """The distance from each point, x, y, and z along the last axis, to the
    nearer of the block's globes' centres, in millimetres; NaN for a point
    that is not finite."""
    globes = np.asarray(block.globes, dtype=float)
    points = np.asarray(points, dtype=float)
    return np.min(np.linalg.norm(points[..., np.newaxis, :] - globes, axis=-1), axis=-1)


def _eye_sheet(
    block: FaceBlock,
    positions: list[int],
    read: Callable[[int], bytes | None],
    contours: list[list[tuple[str, np.ndarray]]],
) -> EyeSheet | None:
    """The sheet of a series' globes beside its eye ROIs
    (:func:`~pymedphys._dicom.deidentify.qc_eyes.eye_sheet`), drawn from its
    slices as received, each decoded once, or None where they can no longer
    be read, in which case the QC pack lists the series without a sheet."""
    try:
        slices, places = _stack(positions, read)
        planes = qc_eyes.planes_of(block, contours, EYE_REACH)
        sampled = qc_eyes.Sampler(
            planes,
            [
                qc_eyes.SliceGeometry(
                    each.position, each.orientation, each.spacing, each.shape
                )
                for each in slices
            ],
        )
        by_instance: dict[int, list[int]] = {}
        for index in sampled.wanted:
            by_instance.setdefault(places[index][0], []).append(index)
        for position, indices in by_instance.items():
            indices.sort(key=lambda index: places[index][1])
            stored = _stored(
                read(position), slices[0].shape, [places[i][1] for i in indices]
            )
            for index, values in zip(indices, stored, strict=True):
                sampled.add(index, _hounsfield(values, slices[index]))
        return qc_eyes.eye_sheet(
            block,
            contours,
            EYE_REACH,
            sampled,
            tuple(places[index] for index in sorted(sampled.wanted)),
            len(places),
        )
    # Whatever the slices raise, as when one can no longer be read, leaves the
    # series held without a sheet, which no confirmation can then be of.
    except Exception:  # pylint: disable = broad-exception-caught
        return None


def _eye_far(contour: pydicom.Dataset, globes: np.ndarray) -> bool:
    """Whether a point of an eye's contour, or of its span where its retired
    Contour Slab Thickness and Contour Offset Vector give it one, lies
    farther than :data:`EYE_REACH` from every one of ``globes``' centres, or
    the contour cannot be placed.

    Each point's span is a segment, so it is checked whole, not at its
    ends alone: the heights along it within reach of each globe form one
    interval, found exactly, and those intervals must together cover the
    span. A span whose ends lie near different globes may leave both
    between them.
    """
    points = np.asarray([float(v) for v in contour.ContourData]).reshape(-1, 3)
    try:
        values = slab_values(contour)
        slab = None if values is None else slab_of(values, points)
    except SlabRefused:
        return True
    if slab is None:
        nearest = np.min(
            np.linalg.norm(points[:, np.newaxis, :] - globes, axis=2), axis=1
        )
        # Written so that a coordinate that is not a number fails it too.
        return not (nearest <= EYE_REACH).all()
    direction = np.asarray(slab.direction, dtype=float)
    # Along p + t * direction, with direction a unit vector, the heights t
    # within EYE_REACH of a centre g are those where
    # t**2 + 2 * t * b + c <= 0, with b = (p - g) . direction and
    # c = |p - g|**2 - EYE_REACH**2: from -b - root to -b + root, with
    # root = sqrt(b**2 - c), and none where b**2 - c is negative.
    offsets = points[:, np.newaxis, :] - globes[np.newaxis, :, :]
    b = offsets @ direction
    c = np.sum(offsets**2, axis=2) - EYE_REACH**2
    discriminant = b**2 - c
    # Written so that a coordinate that is not a number reaches no globe.
    reached = discriminant >= 0
    root = np.sqrt(np.where(reached, discriminant, 0.0))
    low = np.where(reached, -b - root, np.inf)
    high = np.where(reached, -b + root, -np.inf)
    order = np.argsort(low, axis=1)
    low = np.take_along_axis(low, order, axis=1)
    high = np.take_along_axis(high, order, axis=1)
    # Sweep each point's intervals from the span's near end, in order of
    # their low ends: the span is covered where the sweep passes its far
    # end without a gap.
    covered = np.full(len(points), slab.near)
    for each in range(low.shape[1]):
        joins = low[:, each] <= covered
        covered = np.where(joins, np.maximum(covered, high[:, each]), covered)
    return not (covered >= slab.far).all()


def _targets(dataset: pydicom.Dataset) -> set[int]:
    """The ROI Numbers of a structure set's targets."""
    return {
        int(item.ReferencedROINumber)
        for item in dataset.get("RTROIObservationsSequence", [])
        if str(item.get("RTROIInterpretedType") or "").strip().upper() in TARGET_TYPES
    }


def _target_points(
    dataset: pydicom.Dataset, frame: str, slices: set[str]
) -> list[np.ndarray] | None:
    """Return the points of each target of a structure set that may be in
    the Frame of Reference of the series with these slices, an item of ROI
    Contour Sequence at a time, or None where one cannot be placed there.

    A target in that frame is placed by its contours' points, whose convex
    hull defacing keeps (:func:`_kept_targets`). One in another frame cannot
    be placed in the series' without a registration, so it cannot be placed
    where its structure set ties that frame to the series' slices: a contour
    of an ROI in that frame is drawn on one of them, or the frame's own list
    of contour images names one. A target in another frame that its
    structure set does not tie to them, such as one of another scan, is
    not the series'. A target whose ROI names no frame may be in the
    series' or in any frame that its structure set declares, so it is taken
    as each: placed in the series' frame, and not placed where the set ties
    one of the others. So is one whose ROI's frame is not one UID that its
    set declares alone, as one UID in one item, or whose ROI Number is
    repeated with another frame, which is also taken as each value it names,
    so that a malformed frame that the set ties to the series' slices still
    holds the series. A target with a coordinate that is not finite, or of
    magnitude above :data:`_FARTHEST`, cannot be placed either, nor can one
    with retired slab attributes whose span cannot be placed. A valid slab
    contributes every reading of its span to the kept hull (:func:`_spread`).
    """
    frames_of_roi = _roi_frames(dataset)
    targets = _targets(dataset)
    tied = _tied_frames(dataset, frames_of_roi, slices)
    found = []
    for item in dataset.get("ROIContourSequence", []):
        number = int(item.ReferencedROINumber)
        if number not in targets:
            continue
        frames = frames_of_roi(number)
        if (frames - {"", frame}) & tied:
            return None
        # A target that names no Frame of Reference may be in this one.
        if frames & {"", frame}:
            points = [_spread(contour) for contour in item.get("ContourSequence", [])]
            if any(each is None for each in points):
                return None
            if not points:
                continue
            joined = np.concatenate(points)
            if not (np.abs(joined) <= _FARTHEST).all():
                return None
            found.append(joined)
    return found


def _spread(contour: pydicom.Dataset) -> np.ndarray | None:
    """Return a contour's points, with those that its retired Contour Slab
    Thickness and Contour Offset Vector may move them to
    (:func:`~.contour_slabs.spread`), whose convex hull holds every point
    that any reading of them puts it at, so that a target is searched
    wherever one does, or None where its slab cannot be placed."""
    points = np.asarray([float(v) for v in contour.ContourData]).reshape(-1, 3)
    try:
        values = slab_values(contour)
        return spread(points, None if values is None else slab_of(values, points))
    except SlabRefused:
        return None


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
    an ROI Number repeated with another frame (:func:`_target_points`)."""
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
    which takes one pass over the points. This finds a target wherever any
    part of its hull reaches the block, as the hull of one that wraps around
    the block without entering it can, which errs towards keeping the
    target's region and judging it against the slices. A point that cannot
    be placed reaches the block.
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
    by its own functional groups. The frames of compressed Pixel Data are
    those that it decodes to, which it then writes uncompressed.

    Parameters
    ----------
    block : FaceBlock
        The block of the instance's series.
    dataset : pydicom.Dataset
        The instance's data set.
    targets : KeptTargets, optional
        The hulls of the targets that defacing keeps in the block, as the
        series' outcome gives them; none by default.

    Raises
    ------
    PixelDataRefused
        With :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` where
        the instance is not one that :func:`find_face_blocks` defaces.
    """

    def __init__(
        self,
        block: FaceBlock,
        dataset: pydicom.Dataset,
        targets: KeptTargets = KeptTargets(),
    ) -> None:
        try:
            syntax = str(dataset.file_meta.TransferSyntaxUID)
            if syntax not in NATIVE_TRANSFER_SYNTAXES and syntax not in (
                DECODING_PLUGINS
            ):
                raise _Unusable(SeriesProblem.UNDECODABLE)
            layout = frames_layout(dataset, syntax)
            self._slices = _described(dataset, layout)
        # As for a series, whatever the data set raises refuses the
        # instance, without its message.
        except Exception:  # pylint: disable = broad-exception-caught
            raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA) from None
        self._block = block
        self._targets = targets

    def __repr__(self) -> str:
        return "CtDefacer()"

    @property
    def reaches(self) -> bool:
        """Whether the block holds the centre of a pixel of any slice of the
        instance, by its geometry alone, so that :meth:`mask` may give one
        a mask; an instance that it does not reach is written as received,
        without its pixel data decoded."""
        return any(
            self._block.slice_mask(
                each.position, each.orientation, each.spacing, each.shape
            ).any()
            for each in self._slices
        )

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
        inside &= ~kept & ~padded & ~_targets_kept(self._targets, each)
        if not inside.any():
            return None
        return FrameMask(frame, inside, each.air)


def _targets_kept(targets: KeptTargets, each: _Slice) -> np.ndarray:
    """Return a slice's pixels that defacing keeps for the targets, of
    bool, rows by columns."""
    return targets.slice_mask(each.position, each.orientation, each.spacing, each.shape)


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
    enclosed = scipy.ndimage.binary_fill_holes(bone) & ~bone
    behind = _behind_plane(block, each)
    cavity = enclosed & (_heights(each) > floor)
    # Of the cavity, only the brain: the tissue that bone encloses that
    # joins, within the slice, such tissue behind the block's plane, with
    # what it encloses, so that nothing is kept that the cavity alone would
    # not keep. Bone also encloses the air of a frontal sinus in its wall,
    # which, kept, would differ from air written around it only by noise,
    # and any tissue lining it, which joins none behind the plane where it
    # lies ahead of the plane and bone parts it from the brain. The tissue
    # joins at any height, the floor deciding only what is kept: an axial
    # slice lies at one height, so this is the cavity's tissue alone, but a
    # slice that spans heights, as a tilted one does, joins the brain ahead
    # of the plane above the floor to the brain behind the plane through
    # the brain ahead of it below the floor, which it writes as air, as an
    # axial slice through each of its pixels would join them.
    tissue = enclosed & (hounsfield > defacing.BODY)
    labels, _ = scipy.ndimage.label(tissue)
    joined = np.unique(labels[tissue & behind])
    brain = np.isin(labels, joined[joined > 0])
    return scipy.ndimage.binary_fill_holes(brain) & cavity & ~padded, padded


def _behind_plane(block: FaceBlock, each: _Slice) -> np.ndarray:
    """Whether each pixel's centre lies behind the block's vertical plane,
    or on it, whatever its height, of bool, rows by columns.

    Each centre is placed as
    :meth:`~pymedphys._dicom.deidentify.defacing.FaceBlock.slice_mask`
    places it, so that a pixel lies behind the plane exactly where the
    block, above its axial plane, does not hold it.
    """
    origin = np.asarray(each.position, dtype=float)
    along_row = np.asarray(each.orientation[:3], dtype=float)
    down_column = np.asarray(each.orientation[3:], dtype=float)
    rows = np.arange(each.shape[0], dtype=float)[:, None, None] * float(each.spacing[0])
    columns = np.arange(each.shape[1], dtype=float)[None, :, None] * float(
        each.spacing[1]
    )
    points = origin + columns * along_row + rows * down_column
    ahead = (points - np.array(block.origin)) @ np.array(block.anterior)
    return ~(ahead > 0)


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
        return (
            _described_slice(
                dataset,
                layout,
                (dataset,) * 4,
                named_by_instance(dataset),
                multi_frame=False,
            ),
        )
    if iod not in MULTI_FRAME_CT_IODS:
        raise _Unusable(SeriesProblem.UNREADABLE)
    groups = []
    named = []
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
        # A frame without one Frame Content group names no phase.
        try:
            content = frame_group(dataset, layout.frames, frame, "FrameContentSequence")
        except ValueError:
            content = None
        named.append(named_by_frame(content))
    return tuple(
        _described_slice(dataset, layout, each, name, multi_frame=True)
        for each, name in zip(groups, named, strict=True)
    )


def _described_slice(
    dataset: pydicom.Dataset,
    layout: Layout,
    groups: tuple[pydicom.Dataset, ...],
    named: Named,
    *,
    multi_frame: bool,
) -> _Slice:
    """What defacing needs of one slice, from the data sets that hold its
    Image Position (Patient), Image Orientation (Patient), Pixel Spacing,
    and rescale, in that order: the instance's own for CT Image, or the
    frame's functional groups' items, with what it names of its phase.

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
        named=named,
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
        keeps, those of the brain, which no pixel of padding is, and those
        that it keeps for the targets, whether or not they are padding, so
        that no target's dose, activity, segments, or contours are taken
        where the slice holds padding.
    """

    position: tuple[float, float, float]
    orientation: tuple[float, ...]
    spacing: tuple[float, float]
    kept: np.ndarray

    def __repr__(self) -> str:
        return "KeptSlice()"


def kept_slices(
    block: FaceBlock,
    positions: Iterable[int],
    read: Callable[[int], bytes | None],
    targets: KeptTargets = KeptTargets(),
) -> tuple[KeptSlice, ...]:
    """Return each slice of a defaced series that its block reaches, with
    the pixels that defacing keeps there, in the order of ``positions``,
    and of the frames of each multi-frame instance; slices at one position,
    of a series' phases, are one, keeping only what each keeps
    (:func:`_merged`).

    Parameters
    ----------
    block : FaceBlock
        The series' block.
    positions : iterable of int
        The run positions of the series' instances.
    read : callable
        Gives the file at a run position as the first pass read it, or None.
    targets : KeptTargets, optional
        As for :class:`CtDefacer`.

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
            stored = _stored(
                data,
                reached[0][1].shape,
                [i for i, _, _ in reached],
                compressed=reached[0][1].compressed,
            )
            for (_, each, inside), values in zip(reached, stored, strict=True):
                kept, padded = _kept(block, each, values)
                slices.append(
                    KeptSlice(
                        each.position,
                        each.orientation,
                        each.spacing,
                        inside & ((kept & ~padded) | _targets_kept(targets, each)),
                    )
                )
        except (_Unusable, ValueError):
            raise ValueError("a slice can no longer be read") from None
    return _merged(slices)


def _merged(slices: list[KeptSlice]) -> tuple[KeptSlice, ...]:
    """The slices, with those at one position, within
    :data:`~.phases.COINCIDENT` along their normal, as the phases of a
    series that repeats its positions give them, merged into the first of
    them, keeping only the pixels that each of them keeps, so that whatever
    is cleaned beside the series is kept only where every phase keeps it.

    The phases of such a series lie on one grid (:func:`_phases`), so the
    slices at one position are of the same pixels.
    """
    if not slices:
        return ()
    orientation = slices[0].orientation
    normal = np.cross(orientation[:3], orientation[3:])
    heights = [float(np.dot(each.position, normal)) for each in slices]
    order = sorted(range(len(slices)), key=lambda i: (heights[i], i))
    clusters = [[order[0]]]
    for earlier, later in zip(order, order[1:]):
        if heights[later] - heights[earlier] <= COINCIDENT:
            clusters[-1].append(later)
        else:
            clusters.append([later])
    merged = {}
    for cluster in clusters:
        kept = slices[cluster[0]].kept
        for index in cluster[1:]:
            kept = kept & slices[index].kept
        merged[min(cluster)] = dataclasses.replace(slices[min(cluster)], kept=kept)
    return tuple(merged[index] for index in sorted(merged))
