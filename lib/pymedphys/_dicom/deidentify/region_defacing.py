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

"""RT Structure Set contours and PET images in the Frame of Reference of a
defaced CT series, cleaned of the face in its block.

Under the Clean Recognizable Visual Features Option, the contours of an RT
Structure Set in the frame of a CT series that a run defaces
(:mod:`~pymedphys._dicom.deidentify.face_blocks`) can trace the face that
the CT no longer shows, as an outline of the skin does, and so can a PET
image's uptake at the skin. A run therefore cleans each in the same block,
as :mod:`~pymedphys._dicom.deidentify.dose_defacing` sets RT Dose to zero
there, on the block of each defaced series of the frame in turn
(:class:`~.dose_defacing.DoseBlock`, :class:`~.dose_defacing.FrameRegion`):
a contour is cut by each block, the pieces of one cut being cut by the
next, and a PET image is set to zero activity wherever any block writes
its CT as air.

A contour is written as received where none of its segments enters the
block at a point whose nearest pixel, of the nearest slice that the block
reaches within half the slices' spacing, is one that defacing writes as air
(:func:`cut_contours`): a pixel in the block, other than one of the brain
that defacing keeps. So a contour that lies behind the block, below it, or
within the kept brain alone, as a brain contour above the orbits can, is
kept whole. Each segment is sampled within the block at intervals of
half the smallest pixel spacing of those slices. A point with no such pixel
counts where it lies in the block.

A closed contour that reaches the face loses what defacing writes as air,
as the CT does, and the squares of padding pixels in the block, which the
CT leaves as they are, where it can be cut so (:class:`_Spare`): where the
closed contours of its ROI in its plane are each simple, a point that
repeats the one before it aside, all lie at one z above the block's axial
plane, and every point within them has one nearest slice, whether or not
it lies within the slice's pixels, an axial one with pixels that defacing
keeps in the block. Each of them is then written as its part behind the
block's vertical plane joined with its part ahead of that plane within the
squares of that slice's pixels that defacing does not write as air, those
of the kept brain and those whose centres lie outside the block, each
square being the points whose nearest pixel it is. The part within the
squares is found exactly, a row of pixels at a time
(:func:`~pymedphys._geometry.pixel_grids.within_pixels`), and the pieces
are joined into rings along the edges that they share
(:func:`~pymedphys._geometry.polygons.dissolve`), outer rings winding as
the source contour does and holes the other way, each its own contour of
the same type. CLOSEDPLANAR_XOR contours combine by exclusive or, so a
hole there is a contour of its own, but a reader may fill each
CLOSED_PLANAR contour alone, which would fill the hole. So where a
CLOSED_PLANAR contour's rings would bound a hole, as a pixel written as
air within the kept brain makes one, its pieces are split along the edge
between two columns of the slice's pixels at the hole's lowest column,
the hole becoming a notch in the piece beyond the edge, until no ring
bounds one (:func:`_without_holes`); the edge passes through no pixel's
centre, so each pixel's centre lies within one ring or none. A ring of
no more area than a sliver is dropped. Where the pieces of any of them
cannot be joined, or a CLOSED_PLANAR contour's cannot be split so into
simple rings, all of them are cut by the whole block instead. A contour
whose region loses no area by this is written as received.

Any other contour that reaches the face is cut by the block's two planes,
so that what is written of it lies outside the block or on its boundary,
the kept brain being cut away with the rest: a closed contour, of Contour
Geometric Type CLOSED_PLANAR or CLOSEDPLANAR_XOR, is written as each
polygon of its part behind the block's vertical plane, and of its part
ahead of that plane and not above the block's axial plane, each its own
contour of the same type; an open contour, OPEN_PLANAR or OPEN_NONPLANAR,
as each piece of it outside the block; and a POINT contour not at all. A
part of a polygon is found by clipping it against one plane at a time, and
its pieces are separated where the plane cuts it into more than one, by
pairing the points at which its edges cross the plane along their line, as
a simple polygon's do. Since each of the two parts lies on its own side of
the vertical plane, each piece is disjoint from the others but for that
plane, so the pieces of a CLOSEDPLANAR_XOR contour combine as the contour's
own part outside the block does. The closed contours of an ROI in one plane
bound one region together, as a hole's contour does within its outer one,
so where one of them is cut, each of them is cut the same way, by the same
region, so that a hole within the kept brain never becomes a region that the
cut outer contour no longer surrounds; cut by the whole block, each that
enters the block is cut, even one that enters only the kept brain. Since
each is cut by the same region, the region that they bound together,
whether by exclusive or or by union, is cut by it. A contour's plane is the
one that best fits its points, found for any winding and for a contour that
crosses itself, and where a closed contour of an ROI that is cut lies in no
one plane, the structure set is refused. Where the crossings cannot be
paired, as for a polygon that crosses itself, the part is written as one
polygon joined along the plane, which still lies outside the block. The
first piece written of a contour keeps its Contour Number, and the others
have none, since a number names one contour of its ROI. An ROI left with no
contour is written without a Contour Sequence, which is Type 3.

A contour with a retired Contour Slab Thickness or Contour Offset Vector
may lie anywhere along its span
(:mod:`~pymedphys._dicom.deidentify.contour_slabs`). Where that span
reaches the block, the closed contours of its ROI in its plane, only where
they carry the same thickness and offset, are cut together, as a flat
contour is, by the squares of the pixels that any slice that their span
reaches writes as air, so that they keep the brain kept on every such
slice and no reading of what is written has a nearest pixel written as
air (:meth:`_Spare.slab`): where they lie in one axial plane, their span
runs along the patient's z axis, every point of it has a slice within
reach, and those slices share one grid along x and y. Any other such
contour, and an open or POINT one, is cut by the region of every point
whose span meets the block (:func:`_shadow`), the kept brain not spared,
so that no reading of what is written enters the block. A reader places
each contour's slab by its own points, so a plane's contours are cut by a
span holding each one's reading, the block grown by as far as their
readings can lie from it (:func:`_enclosing`), and every contour with a
slab that a cut writes is read again from its points as written, the
structure set being refused where one would be read elsewhere, as a
straight piece of a thick open contour, which has no plane, would be
(:func:`_check_slabs`). The QC pack's contour
sheet draws no such contour (:mod:`~pymedphys._dicom.deidentify.qc_contours`),
so a structure set so cut is still held without a verdict.

A structure set's ROIs in each defaced frame are cut by that frame's
blocks, and those in a frame that it declares as one UID in one item and
that holds no defaced series are written as received, still read as
contours are. A structure set is cut only where each of its ROIs names
such a frame, under an ROI Number given once, each contour has a known
Contour Geometric Type, Contour Data of finite coordinates, in threes,
none greater in magnitude than :data:`_FARTHEST`, and a slab that can be
placed, and no contour, nor a frame's list of contour images, refers to a
defaced slice of a series in another frame. Any other stays held as an
instance in a defaced frame
(:attr:`~.reasons.VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME`), as does
one whose contours an ROI Contour Sequence item gives for an ROI that it
does not declare.

A PET image of one sample, of native Pixel Data or compressed Pixel Data
whose frames decode as Clean Pixel Data decodes them, is written with each pixel
whose centre is in the block, other than one that defacing keeps or one of
Pixel Padding Value or its range, set to the stored value of zero activity
(:class:`PetDefacer`): a Positron Emission Tomography Image instance of one
frame, placed by Image Position (Patient), Image Orientation (Patient), and
Pixel Spacing, and rescaled by Rescale Slope and Rescale Intercept, or each
frame of an Enhanced PET Image or Legacy Converted Enhanced PET Image
instance, placed by its Plane Position (Patient), Plane Orientation
(Patient), and Pixel Measures functional groups and rescaled by its Pixel
Value Transformation functional group, each in either the frame's item of
the Per-frame Functional Groups Sequence or the Shared Functional Groups
Sequence, never both (:func:`~.functional_groups.frame_group`). Each slice
or frame needs an Image Orientation (Patient) of two orthogonal unit
vectors, a positive Pixel Spacing, every corner within :data:`_FARTHEST`
millimetres, a Rescale Slope finite and positive, and a Rescale Intercept
whose zero activity, -intercept / slope, a stored value can hold, rounded;
each frame is set to its own zero activity, since its rescale is its own.
Compressed Pixel Data is decoded, set to zero activity there, and written
uncompressed, in Explicit VR Little Endian, as Clean Pixel Data writes it,
unless nothing is set (D-037, D-052). Any other PET image stays held, as
does one whose frames do not decode.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Collection, Mapping, Sequence
from typing import TypeAlias

from pymedphys._geometry.pixel_grids import PixelGrid, within_pixels
from pymedphys._geometry.polygons import (
    clip,
    coplanar,
    dissolve,
    is_simple,
    signed_area,
)
from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from .contour_slabs import Slab, SlabRefused, SlabValues, slab_of, slab_values
from .defacing import ALIGNMENT_TOLERANCE, FaceBlock
from .diagnostics import redacted_diagnostics
from .dose_defacing import (
    DoseBlock,
    Region,
    _check_directions,
    _check_reach,
    _numbers,
)
from .face_blocks import MULTI_FRAME_PET_IODS, PET_IMAGE, _padding, iod_of
from .functional_groups import frame_group
from .pixel_cleaning import (
    FrameMask,
    Layout,
    PixelDataRefused,
    frames_layout,
    stored_range,
)
from .pixel_decoding import DECODING_PLUGINS
from .reasons import TransformReason, VisualFeaturesReason
from .source import NATIVE_TRANSFER_SYNTAXES
from .uid_registry import is_uid
from .uids import normalise_uid

CLOSED_PLANAR = "CLOSED_PLANAR"
CLOSED = frozenset({CLOSED_PLANAR, "CLOSEDPLANAR_XOR"})
OPEN = frozenset({"OPEN_PLANAR", "OPEN_NONPLANAR"})
POINT = "POINT"
# The largest magnitude, in millimetres, of a coordinate of a contour that
# is cut, as face_blocks bounds a target's.
_FARTHEST = 1e6
# The interval, in millimetres, at which a segment is sampled within the
# block where the block reaches no slice.
_STEP = 0.5
# How far, in millimetres, each point of a closed contour may lie from
# another's plane, or from its own, and still be taken to lie in it. It
# allows for coordinates written to 0.1 mm, which move a point up to 0.087 mm
# off its plane, and is less than any slice spacing in use. Grouping
# too much cuts more of the kept brain; grouping too little can leave a
# hole whole within a contour that is cut.
_COPLANAR = 0.15
# The area, in square millimetres, of a contour's part in the block, or in
# the brain kept there, of a ring that its pieces join into, or of a piece
# that a split leaves, at or below which it is taken for an artefact of
# floating point.
_SLIVER = 1e-9
# How far, in millimetres or in a unit vector's components, a slab's span
# may depart from the patient's z axis, the block's vertical plane from
# upright, and the slices that a slab reaches from rows and columns along x
# and y and from one another's grid, for the slab to keep the kept brain:
# within this, a point's pixel is the same whatever its height.
_UPRIGHT = 1e-9
# How far, in millimetres, a contour's slab as written may be read beyond
# the span that its cut judged it by: the rounding of its points' decimal
# strings, and of arithmetic on them.
_PLACED = 1e-9
# How far apart, in millimetres, two points of the pieces of a cut contour
# may be and be joined as one.
_SAME_POINT = 1e-9
# How far, in pixels, a hole's leftmost point may lie to the left of an edge
# between columns of pixels and be taken to lie on it, as one found by
# clipping at that edge does but for rounding.
_ON_EDGE = 1e-6
# The most times that the pieces of one contour are split to free it of
# holes; each split frees it of at least one, except where joining takes
# points within a hair of each other as one.
_MOST_SPLITS = 256


class ContoursRefused(Exception):
    """A structure set whose contours cannot be cut by the block.

    Its message names no value.
    """

    def __init__(self) -> None:
        super().__init__("the contours cannot be cut by the block")


@dataclasses.dataclass(frozen=True, repr=False)
class WrittenContour:
    """A contour of an ROI as the run writes it.

    Its ``repr`` shows nothing of it.

    Attributes
    ----------
    contour : int
        The index, from 0, of the source contour in its ROI's Contour
        Sequence, which the written one is made from.
    values : tuple of str, optional
        The Contour Data written, as decimal strings, three to a point; None
        where the contour is written as received.
    numbered : bool
        Whether it keeps the source's Contour Number, if it has one.
    """

    contour: int
    values: tuple[str, ...] | None = None
    numbered: bool = True

    def __repr__(self) -> str:
        return "WrittenContour()"


def cut_contours(
    regions: Mapping[str, Region],
    dataset: pydicom.Dataset,
    defaced: Collection[str] = (),
) -> dict[int, tuple[WrittenContour, ...]]:
    """Return the contours of each ROI that the blocks change, as the module
    describes.

    Parameters
    ----------
    regions : mapping of str to DoseBlock or FrameRegion
        The blocks of each defaced Frame of Reference that the structure set
        names, by its UID.
    dataset : pydicom.Dataset
        The structure set's data set.
    defaced : collection of str
        The Frame of Reference UID of each defaced series of the run; an ROI
        in one of them without a region is refused.

    Returns
    -------
    dict of int to tuple of WrittenContour
        By the index, from 0, of an item of ROI Contour Sequence, each of
        its contours as written, in order, for each item with a contour that
        is cut; any other item is written as received.

    Raises
    ------
    ContoursRefused
        Where the structure set is not one that the module cuts.
    """
    try:
        with redacted_diagnostics():
            frames = _roi_frames_of(dataset)
            certain = _declared(dataset)
            if any(
                frame not in regions and (frame in defaced or frame not in certain)
                for frame in frames.values()
            ):
                raise ContoursRefused()
            _check_images(dataset, frames, regions)
            cut = {}
            for index, item in enumerate(dataset.get("ROIContourSequence") or []):
                number = int(item.ReferencedROINumber)
                if number not in frames:
                    raise ContoursRefused()
                region = regions.get(frames[number])
                contours = item.get("ContourSequence") or []
                if region is None:
                    # Read all the same, so that a contour that the module
                    # cannot read refuses the set wherever its ROI lies.
                    for contour in contours:
                        _contour(contour, 0)
                    continue
                written = _written(region, contours)
                if written is not None:
                    cut[index] = written
            return cut
    except ContoursRefused:
        raise
    # pydicom raises many types for a value it cannot read, and a message can
    # quote the value: the structure set stays held.
    except Exception:  # pylint: disable = broad-exception-caught
        raise ContoursRefused() from None


def _roi_frames_of(dataset: pydicom.Dataset) -> dict[int, str]:
    """Return the Frame of Reference UID of each ROI of a structure set, by
    its ROI Number.

    Raises
    ------
    ContoursRefused
        Where an ROI Number is given twice, so that its frame is not one.
    """
    frames: dict[int, str] = {}
    for item in dataset.get("StructureSetROISequence") or []:
        number = int(item.ROINumber)
        if number in frames:
            raise ContoursRefused()
        frames[number] = normalise_uid(
            str(item.get("ReferencedFrameOfReferenceUID") or "")
        )
    return frames


def _declared(dataset: pydicom.Dataset) -> frozenset[str]:
    """Return each Frame of Reference UID that a structure set declares as
    one UID in one item of Referenced Frame of Reference Sequence, the
    frames in which an ROI can be left as received."""
    declared = set()
    for item in dataset.get("ReferencedFrameOfReferenceSequence") or []:
        value = item.get("FrameOfReferenceUID")
        if isinstance(value, str):
            frame = normalise_uid(value)
            if is_uid(frame):
                declared.add(frame)
    return frozenset(declared)


def _check_images(
    dataset: pydicom.Dataset,
    frames: Mapping[int, str],
    regions: Mapping[str, Region],
) -> None:
    """Check that no contour, and no frame's list of contour images, of a
    structure set refers to a defaced slice of a series in another frame,
    whose contours would be drawn on it uncut by its block.

    Raises
    ------
    ContoursRefused
        Where one does.
    """
    owner = {
        instance: frame
        for frame, region in regions.items()
        for instance in region.instances
    }

    def check(images: pydicom.Sequence, frame: str) -> None:
        for image in images or []:
            uid = normalise_uid(str(image.get("ReferencedSOPInstanceUID") or ""))
            if owner.get(uid, frame) != frame:
                raise ContoursRefused()

    for item in dataset.get("ROIContourSequence") or []:
        frame = frames.get(int(item.ReferencedROINumber), "")
        for contour in item.get("ContourSequence") or []:
            check(contour.get("ContourImageSequence"), frame)
    for use in dataset.get("ReferencedFrameOfReferenceSequence") or []:
        frame = normalise_uid(str(use.get("FrameOfReferenceUID") or ""))
        for study in use.get("RTReferencedStudySequence") or []:
            for series in study.get("RTReferencedSeriesSequence") or []:
                check(series.get("ContourImageSequence"), frame)


@dataclasses.dataclass(frozen=True, repr=False)
class _Contour:
    """One contour of an ROI as a cut has left it.

    Its ``repr`` shows nothing of it.

    Attributes
    ----------
    source : int
        The index, from 0, of the source contour in its ROI's Contour
        Sequence.
    kind : str
        Its Contour Geometric Type.
    points : numpy.ndarray
        Its points, the x, y, and z of each in rows, in millimetres, in its
        Contour Data's place, not moved by its slab.
    slab : SlabValues or None
        Its source's Contour Slab Thickness and Contour Offset Vector, which
        each piece of it keeps.
    numbered : bool
        Whether it keeps its source's Contour Number.
    changed : bool
        Whether a cut has changed it.
    judged : tuple of (Slab, float)
        For a contour with a slab, the span along which each block's cut
        that wrote its ROI judged it, and how far, in millimetres, beyond
        that span the cut reached (:func:`_shadow`), so that what is
        written can be checked to be read along it (:func:`_check_slabs`).
    """

    source: int
    kind: str
    points: np.ndarray
    slab: SlabValues | None
    numbered: bool = True
    changed: bool = False
    judged: tuple[tuple[Slab, float], ...] = ()

    def __repr__(self) -> str:
        return "_Contour()"


def _written(
    region: Region, contours: pydicom.Sequence
) -> tuple[WrittenContour, ...] | None:
    """Return one ROI's contours as written, cut by each block of its frame
    in turn (:func:`_cut_by`), or None where none is cut.

    Raises
    ------
    ContoursRefused
        Where a contour cannot be read, or a block's cut refuses them.
    """
    parsed = [_contour(contour, index) for index, contour in enumerate(contours)]
    cut = False
    for dose in region.blocks:
        pieces = _cut_by(dose, parsed)
        if pieces is not None:
            parsed, cut = pieces, True
    if not cut:
        return None
    _check_slabs(parsed)
    return tuple(
        WrittenContour(
            each.source,
            _decimals(each.points) if each.changed else None,
            each.numbered,
        )
        for each in parsed
    )


def _cut_by(dose: DoseBlock, parsed: list[_Contour]) -> list[_Contour] | None:
    """Return one ROI's contours cut by one series' block, or None where
    none is cut.

    Closed contours in one plane bound one region together, as a hole's
    contour does within its outer one, so where one of them reaches the
    face, each of them is cut by the same region, the block less the
    pixels that defacing does not write as air where :class:`_Spare` can
    cut them all so, or else the whole block, and the region that they
    bound together loses just its part in it. Where any is cut, a closed
    contour that lies in no one plane is refused. A contour with a slab
    (:mod:`~.contour_slabs`) is cut only where its span meets the block
    (:func:`_shadow`), and closed contours in one plane, where one of them
    has a slab, only where each has the same thickness and offset; they are
    cut by the pixels that some slice their span reaches writes as air,
    where :meth:`_Spare.slab` can cut them so, and otherwise by every point
    whose span meets the block.

    Raises
    ------
    ContoursRefused
        Where a closed contour that lies in no one plane is in an ROI of
        which a contour is cut, or contours in one plane that are cut have
        another slab each, or a slab cannot be placed.
    """
    step = min(min(each.spacing) for each in dose.slices) / 2 if dose.slices else _STEP
    # Each contour with a slab is judged along its own span, as a reader
    # places it, until a plane's contours are cut together below.
    judged: list[tuple[Slab, float] | None] = [
        None if each.slab is None else (_placed(each.slab, each.points), 0.0)
        for each in parsed
    ]
    halves = [None if each is None else _shadow(dose.block, *each) for each in judged]
    cutting = [
        _reaches_face(dose, each.kind, each.points, step)
        if halves[index] is None
        else _meets(halves[index], each.kind, each.points)
        for index, each in enumerate(parsed)
    ]
    # Grouping only spreads a cut, so an ROI with none needs no grouping.
    if not any(cutting):
        return None
    closed = [index for index, each in enumerate(parsed) if each.kind in CLOSED]
    groups, unplaced = coplanar([parsed[index].points for index in closed], _COPLANAR)
    # A closed contour in no one plane cannot be decided with those it may
    # bound a region with, so an ROI that is cut with one is refused.
    if unplaced:
        raise ContoursRefused()
    spared: dict[int, list[np.ndarray]] = {}
    for group in groups:
        members = [closed[member] for member in group]
        if not any(cutting[index] for index in members):
            continue
        slabs = {parsed[index].slab for index in members}
        polygons = [_distinct(parsed[index].points) for index in members]
        if slabs != {None}:
            # Contours that bound a region together share its slab, which
            # is placed by the plane of them all.
            if len(slabs) != 1:
                raise ContoursRefused()
            slab, margin = _enclosing(
                _placed(
                    parsed[members[0]].slab,
                    np.concatenate([parsed[index].points for index in members]),
                ),
                [judged[index] for index in members],
            )
            shared = _shadow(dose.block, slab, margin)
            for index in members:
                halves[index] = shared
                judged[index] = (slab, margin)
                cutting[index] = _enters(shared, parsed[index].points)
            spare = None if margin > _PLACED else _Spare.slab(dose, polygons, slab)
            if spare is None:
                continue
        else:
            # Every contour of a plane is cut by the same region, the block
            # less the brain that defacing keeps where the plane allows, or
            # the whole block, so that the region they bound together loses
            # just its part in it.
            spare = _Spare.of(dose, polygons)
        cuts = (
            []
            if spare is None
            else [
                spare.cut(each, parsed[index].kind)
                for index, each in zip(members, polygons, strict=True)
            ]
        )
        joined = [each for each in cuts if each is not None]
        if len(joined) != len(members):
            whole = halves[members[0]] or _block_halves(dose.block)
            for index in members:
                cutting[index] = _enters(whole, parsed[index].points)
            continue
        for index, (cut, pieces) in zip(members, joined, strict=True):
            cutting[index], spared[index] = cut, pieces
    if not any(cutting):
        return None
    written: list[_Contour] = []
    for index, (source, cut) in enumerate(zip(parsed, cutting, strict=True)):
        mark = judged[index]
        each = (
            source
            if mark is None
            else dataclasses.replace(source, judged=(*source.judged, mark))
        )
        if not cut:
            written.append(each)
            continue
        pieces = (
            spared[index]
            if index in spared
            else _pieces(
                halves[index] or _block_halves(dose.block), each.kind, each.points
            )
        )
        written.extend(
            dataclasses.replace(
                each, points=piece, numbered=each.numbered and first == 0, changed=True
            )
            for first, piece in enumerate(pieces)
        )
    return written


def _placed(values: SlabValues | None, points: np.ndarray) -> Slab:
    """The span of a contour's slab, as :func:`~.contour_slabs.slab_of`
    finds it.

    Raises
    ------
    ContoursRefused
        Where it cannot be placed.
    """
    assert values is not None
    try:
        return slab_of(values, points)
    except SlabRefused:
        raise ContoursRefused() from None


# The open half-spaces whose intersection is a region that a contour is cut
# by, each as a normal and an offset: the points whose dot product with the
# normal is more than the offset.
_Halves: TypeAlias = "tuple[tuple[np.ndarray, float], ...]"


def _block_halves(block: FaceBlock) -> _Halves:
    """The block as the intersection of its two open half-spaces: ahead of
    its vertical plane, and above its axial plane."""
    anterior = np.asarray(block.anterior, dtype=float)
    return (
        (anterior, float(np.dot(block.origin, anterior))),
        (np.array([0.0, 0.0, 1.0]), float(block.inferior_limit)),
    )


def _shadow(block: FaceBlock, slab: Slab, margin: float = 0.0) -> _Halves:
    """The points whose span, moved along a slab's direction from its near
    to its far end, meets the block, or the block grown by ``margin``
    millimetres beyond each of its planes, as an intersection of open
    half-spaces.

    For a point ``p``, the span meets the block where some ``t`` from
    ``near`` to ``far`` puts ``p + t d`` ahead of the vertical plane and
    above the axial plane: each is an affine function of ``t``, ``g + t a``,
    so with ``c`` the span's centre and ``h`` its half-length, each holds
    for some ``t`` of the span exactly where ``g + c a + h |a|`` is
    positive, and both hold for one ``t`` where, besides, the two do not
    pull ``t`` apart: where their ``a`` have opposite signs, the two roots
    must be in order, which is a third half-space, ``(g1 + c a1) |a2| +
    (g2 + c a2) |a1| > 0``.
    """
    direction = np.asarray(slab.direction, dtype=float)
    centre = (slab.near + slab.far) / 2
    half = (slab.far - slab.near) / 2
    planes = [(normal, offset - margin) for normal, offset in _block_halves(block)]
    found = []
    rates = []
    for normal, offset in planes:
        rate = float(direction @ normal)
        rates.append(rate)
        found.append((normal, offset - centre * rate - half * abs(rate)))
    (first, first_offset), (second, second_offset) = planes
    if rates[0] * rates[1] < 0:
        found.append(
            (
                abs(rates[1]) * first + abs(rates[0]) * second,
                abs(rates[1]) * (first_offset - centre * rates[0])
                + abs(rates[0]) * (second_offset - centre * rates[1]),
            )
        )
    return tuple(found)


def _beyond(reading: Slab, span: Slab) -> float:
    """How far, in millimetres, a point read along ``reading`` can lie from
    every point read along ``span`` from the same place: by the angle
    between their directions, over the reading's length, and by any part of
    the reading beyond the span's ends; infinite where the directions are
    perpendicular."""
    direction = np.asarray(reading.direction, dtype=float)
    along = np.asarray(span.direction, dtype=float)
    dot = float(direction @ along)
    if dot == 0 or not math.isfinite(dot):
        return math.inf
    sign = 1.0 if dot > 0 else -1.0
    near, far = sorted((sign * reading.near, sign * reading.far))
    length = max(abs(reading.near), abs(reading.far))
    turned = float(np.linalg.norm(direction - sign * along))
    return length * turned + max(0.0, span.near - near, far - span.far)


def _enclosing(
    shared: Slab, owns: Sequence[tuple[Slab, float] | None]
) -> tuple[Slab, float]:
    """Return a span, along the direction of ``shared``, the slab of a
    plane's contours, holding the span of each and of ``shared``, and how
    far each contour's own reading of its slab can lie beyond it, so that
    the block grown by that much and moved back along that span holds every
    point that any of their readings puts in the block (:func:`_shadow`)."""
    near, far, margin = shared.near, shared.far, 0.0
    along = np.asarray(shared.direction, dtype=float)
    for own in owns:
        assert own is not None
        reading = own[0]
        dot = float(np.asarray(reading.direction, dtype=float) @ along)
        sign = 1.0 if dot >= 0 else -1.0
        ends = sorted((sign * reading.near, sign * reading.far))
        near, far = min(near, ends[0]), max(far, ends[1])
    span = Slab(shared.direction, near, far)
    for own in owns:
        assert own is not None
        margin = max(margin, _beyond(own[0], span))
    if not math.isfinite(margin):
        raise ContoursRefused()
    return span, margin


def _check_slabs(contours: Sequence[_Contour]) -> None:
    """Check that each contour with a slab, as it is written, is read along
    a span within reach of each span that a cut judged it by, its own
    direction found from its points as written, as a reader finds it.

    Raises
    ------
    ContoursRefused
        Where one is not, as a piece of an open contour whose cut leaves it
        straight, which has no plane for its thickness, or a sliver of a
        closed contour, whose plane its points no longer fix.
    """
    for each in contours:
        if each.slab is None or not each.judged:
            continue
        points = (
            np.array([float(v) for v in _decimals(each.points)]).reshape(-1, 3)
            if each.changed
            else each.points
        )
        try:
            reading = slab_of(each.slab, points)
        except SlabRefused:
            raise ContoursRefused() from None
        if any(
            _beyond(reading, span) > margin + _PLACED for span, margin in each.judged
        ):
            raise ContoursRefused()


def _meets(halves: _Halves, kind: str, points: np.ndarray) -> bool:
    """Whether a contour meets the open region of ``halves``: a closed one
    where the region it bounds does, an open one where a segment enters it,
    and a point where it lies in it."""
    if kind == POINT or len(points) == 1:
        return bool(_inside(halves, points).any())
    if kind in CLOSED:
        return _enters(halves, points)
    lower, upper = _intervals(halves, *_segments(kind, points))
    return bool((lower < upper).any())


def _inside(halves: _Halves, points: np.ndarray) -> np.ndarray:
    """Whether each point lies in the open region of ``halves``."""
    inside = np.ones(len(points), dtype=bool)
    for normal, offset in halves:
        inside &= points @ normal > offset
    return inside


@dataclasses.dataclass(frozen=True, repr=False)
class _Spare:
    """The pixels of the slice nearest one axial plane of an ROI's closed
    contours that defacing does not write as air, those of the brain kept
    in the block and those whose centres lie outside it, whose squares a
    contour cut in that plane keeps; or, for contours with a slab, the
    pixels that no slice that the slab reaches writes as air (:meth:`slab`).

    Its ``repr`` shows nothing of it.

    Attributes
    ----------
    block : FaceBlock
        The block.
    grid : PixelGrid
        The pixels' grid.
    spared : numpy.ndarray
        Of bool, rows by columns: the pixels whose squares are kept.
    outside : _Halves
        The region whose complement a contour keeps whole: the block, or,
        for a slab, the part of space ahead of its vertical plane.
    """

    block: FaceBlock
    grid: PixelGrid
    spared: np.ndarray
    outside: _Halves

    def __repr__(self) -> str:
        return "_Spare()"

    @classmethod
    def of(cls, region: DoseBlock, polygons: list[np.ndarray]) -> _Spare | None:
        """Return the kept brain of the plane of ``polygons``, or None where
        they are cut by the whole block: where they are not all simple and
        in one axial plane above the block's axial plane, with every point
        within them nearest one axial slice of the series within half its
        spacing, one with pixels kept in the block."""
        z = float(polygons[0][0, 2])
        if (
            not region.slices
            or not z > region.block.inferior_limit
            or any(
                (points[:, 2] != z).any() or not is_simple(points)
                for points in polygons
            )
        ):
            return None
        # Every point of the polygons, and so every point within them, since
        # its height along the slices' normal lies between theirs, must have
        # one nearest slice, whether or not it lies within the slice's
        # pixels: a point beyond them has none kept, as for the cut.
        points = np.concatenate(polygons)
        normal = np.cross(
            region.slices[0].orientation[:3], region.slices[0].orientation[3:]
        )
        along = points @ normal
        ends = points[[int(np.argmin(along)), int(np.argmax(along))]]
        found = np.unique(region.nearest_slices(ends))
        if len(found) != 1 or found[0] < 0:
            return None
        each = region.slices[int(found[0])]
        orientation = np.asarray(each.orientation, dtype=float)
        # Direction cosines may differ from unit length within a tolerance,
        # so the normal's tilt is judged by its direction alone.
        normal = np.cross(orientation[:3], orientation[3:])
        length = float(np.linalg.norm(normal))
        if (
            not each.kept.any()
            or length <= 0
            or abs(abs(normal[2]) / length - 1) > ALIGNMENT_TOLERANCE
        ):
            return None
        inside = region.block.slice_mask(
            each.position, each.orientation, each.spacing, each.kept.shape
        )
        return cls(
            region.block,
            PixelGrid(each.position, each.orientation, each.spacing),
            each.kept | ~inside,
            _block_halves(region.block),
        )

    @classmethod
    def slab(
        cls, region: DoseBlock, polygons: list[np.ndarray], slab: Slab
    ) -> _Spare | None:
        """Return the pixels that no slice that the polygons' slab reaches
        writes as air, so that no point of any reading of them that lies in
        those pixels' squares has a nearest pixel that defacing writes as
        air, or None where they are cut by the block moved back along the
        span instead (:func:`_shadow`).

        That is where the polygons are not all simple and in one axial
        plane; where the span is not along the patient's z axis, or the
        block's vertical plane not upright, within a hair; where some point
        of the span has no slice within reach, or two slices share a
        height (:meth:`~.dose_defacing.DoseBlock.spanned`); where the
        slices that it reaches do not share one grid of pixels, its rows and
        columns along the patient's x and y axes, so that a point's pixel is
        the same in each whatever its z; and where no pixel whose centre
        lies in the block on any of them is kept on all of them.
        """
        z = float(polygons[0][0, 2])
        direction = np.asarray(slab.direction, dtype=float)
        if (
            not region.slices
            or any(
                (points[:, 2] != z).any() or not is_simple(points)
                for points in polygons
            )
            or abs(abs(direction[2]) - 1) > _UPRIGHT
            or abs(float(region.block.anterior[2])) > _UPRIGHT
        ):
            return None
        found = region.spanned(np.concatenate(polygons), direction, slab.near, slab.far)
        if found is None:
            return None
        reached = [region.slices[index] for index in found]
        first = reached[0]
        orientation = np.asarray(first.orientation, dtype=float)
        if (
            abs(orientation[2]) > _UPRIGHT
            or abs(orientation[5]) > _UPRIGHT
            or any(
                tuple(each.orientation) != tuple(first.orientation)
                or tuple(each.spacing) != tuple(first.spacing)
                or each.kept.shape != first.kept.shape
                or abs(each.position[0] - first.position[0]) > _UPRIGHT
                or abs(each.position[1] - first.position[1]) > _UPRIGHT
                for each in reached
            )
        ):
            return None
        spared = np.ones(first.kept.shape, dtype=bool)
        anywhere = np.zeros(first.kept.shape, dtype=bool)
        for each in reached:
            inside = region.block.slice_mask(
                each.position, each.orientation, each.spacing, each.kept.shape
            )
            spared &= each.kept | ~inside
            anywhere |= inside
        if not (spared & anywhere).any():
            return None
        anterior = np.asarray(region.block.anterior, dtype=float)
        return cls(
            region.block,
            PixelGrid(first.position, first.orientation, first.spacing),
            spared,
            ((anterior, float(np.dot(region.block.origin, anterior))),),
        )

    def cut(
        self, points: np.ndarray, kind: str
    ) -> tuple[bool, list[np.ndarray]] | None:
        """Return whether a closed contour's region meets the block where
        defacing writes air, and so is cut, and the polygons written in its
        place: its part outside the block (:func:`_pieces`), joined with
        its part in the block in the squares of the pixels that defacing
        does not write as air, where it has one, into rings, outer ones
        winding as the contour does and holes the other way; for a contour
        of Contour Geometric Type ``kind`` CLOSED_PLANAR, in which a
        contour of its own cannot exclude a hole, into rings that bound
        none (:func:`_without_holes`). Return None where the pieces cannot
        be joined into such rings.
        """
        clockwise = signed_area(points) <= 0
        ring = points[::-1] if clockwise else points
        outside = _pieces(self.outside, CLOSED_PLANAR, ring)
        ahead = clip(ring, *_ahead(self.block))
        kept = [
            piece
            for part in ahead
            for piece in within_pixels(part, self.grid, self.spared)
        ]
        removed = sum(map(signed_area, ahead)) - sum(map(signed_area, kept))
        if not removed > _SLIVER:
            return False, []
        if not sum(map(signed_area, kept)) > _SLIVER:
            written = outside
        else:
            rings = (
                _without_holes(outside + kept, ring, self.grid)
                if kind == CLOSED_PLANAR
                else _joined(outside + kept, ring)
            )
            if rings is None:
                return None
            z = float(ring[0, 2])
            written = [np.column_stack([each, np.full(len(each), z)]) for each in rings]
        # A reader that fills by the nonzero rule takes a hole for one only
        # where it winds against its outer contour.
        return True, [each[::-1] for each in written] if clockwise else written


def _joined(pieces: list[np.ndarray], ring: np.ndarray) -> list[np.ndarray] | None:
    """Join a contour's pieces into rings, by x and y, as
    :func:`~pymedphys._geometry.polygons.dissolve` joins them, keeping the
    points of ``ring`` as they are, but for a ring of no more area than a
    sliver, such as one of three points in a line that joining points within
    a hair of a pixel's corner can leave."""
    rings = dissolve([piece[:, :2] for piece in pieces], ring[:, :2], _SAME_POINT)
    if rings is None:
        return None
    return [each for each in rings if abs(signed_area(each)) > _SLIVER]


def _without_holes(
    pieces: list[np.ndarray], ring: np.ndarray, grid: PixelGrid
) -> list[np.ndarray] | None:
    """Join a contour's pieces into anticlockwise rings, by x and y, that
    bound no hole, as :func:`_joined` joins them.

    Where the rings would bound a hole, the pieces are split along the edge
    between columns of ``grid``'s pixels at, or just beyond, the lowest
    column of the holes' points, each side joined again, and so on until no
    ring bounds one. A hole that the edge crosses or touches becomes a notch
    in the rings beside it, and none lies wholly on the edge's lower side,
    so each split leaves at least one hole fewer, except where joining takes
    points within a hair of each other as one, where ``_MOST_SPLITS`` still
    bounds the splits. Return None where the pieces of a side cannot be
    joined, the edge would miss the hole, a ring is not simple, or
    ``_MOST_SPLITS`` splits leave a hole.
    """
    z = float(ring[0, 2])
    written: list[np.ndarray] = []
    pending = [pieces]
    splits = 0
    while pending:
        parts = pending.pop()
        rings = _joined(parts, ring)
        if rings is None:
            return None
        # Each ring is anticlockwise here but a hole's.
        holes = [each for each in rings if signed_area(each) < 0]
        if not holes:
            written.extend(rings)
            continue
        if splits == _MOST_SPLITS:
            return None
        splits += 1
        hole = min(
            (
                grid.indices(np.column_stack([each, np.full(len(each), z)]))[1]
                for each in holes
            ),
            key=np.min,
        )
        edge = math.ceil(float(hole.min()) - 0.5 - _ON_EDGE) + 0.5
        if not edge < float(hole.max()):
            return None
        normal, offset = grid.column_bound(edge)
        for side in ((normal, offset), (-normal, -offset)):
            half = [
                piece
                for part in parts
                for piece in clip(part, *side)
                if abs(signed_area(piece)) > _SLIVER
            ]
            if half:
                pending.append(half)
    # Joining points within a hair of a pixel's corner can leave a ring that
    # crosses or touches itself there, which a reader may fill otherwise.
    return written if all(map(is_simple, written)) else None


def _distinct(points: np.ndarray) -> np.ndarray:
    """Return a closed contour's points without a point that repeats the
    one before it, the last point being before the first, so that a contour
    whose first point is written again at its end can still be simple."""
    repeated = (points == np.roll(points, 1, axis=0)).all(axis=1)
    distinct: np.ndarray = points[:1] if repeated.all() else points[~repeated]
    return distinct


def _contour(contour: pydicom.Dataset, index: int) -> _Contour:
    """Return a contour, the ``index``-th of its ROI's Contour Sequence, as
    read for a cut.

    Raises
    ------
    ContoursRefused
        Where the module does not cut it.
    """
    kind = str(contour.get("ContourGeometricType") or "").strip().upper()
    if kind not in CLOSED | OPEN | {POINT}:
        raise ContoursRefused()
    try:
        slab = slab_values(contour)
    except SlabRefused:
        raise ContoursRefused() from None
    data = contour.get("ContourData")
    values = (
        [float(each) for each in data]
        if isinstance(data, (list, tuple, pydicom.multival.MultiValue))
        else [float(data)]
    )
    if not values or len(values) % 3 or not all(math.isfinite(v) for v in values):
        raise ContoursRefused()
    points = np.asarray(values).reshape(-1, 3)
    if not (np.abs(points) <= _FARTHEST).all():
        raise ContoursRefused()
    return _Contour(index, kind, points, slab)


def _segments(kind: str, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the starts and ends of a contour's segments, a closed
    contour's last running back to its first point."""
    if kind in OPEN:
        return points[:-1], points[1:]
    return points, np.roll(points, -1, axis=0)


def _reaches_face(
    region: DoseBlock, kind: str, points: np.ndarray, step: float
) -> bool:
    """Whether a contour reaches a point that defacing writes as air, and so
    is cut by the block."""
    if kind == POINT or len(points) == 1:
        return bool(_defaced(region, points).any())
    return _reaches(region, *_segments(kind, points), step)


def _enters(halves: _Halves, points: np.ndarray) -> bool:
    """Whether a closed contour's segments enter the open region of
    ``halves``, which, since that region's part of the contour's plane is
    unbounded, is whether the region it bounds meets it."""
    lower, upper = _intervals(halves, *_segments(CLOSED_PLANAR, points))
    return bool((lower < upper).any())


def _pieces(halves: _Halves, kind: str, points: np.ndarray) -> list[np.ndarray]:
    """Return the pieces of a contour outside the open region of ``halves``,
    written in its place: a closed one's part outside the first half-space,
    then its part within the first and outside the second, and so on, each
    disjoint from the others but for the planes between them."""
    if kind == POINT or len(points) == 1:
        return [] if _inside(halves, points).any() else [points]
    if kind in OPEN:
        return _outside_polyline(halves, points)
    pieces: list[np.ndarray] = []
    within = [points]
    for normal, offset in halves:
        for part in within:
            pieces.extend(clip(part, normal, offset))
        within = [piece for part in within for piece in clip(part, -normal, -offset)]
    return [piece for piece in pieces if len(piece) >= 3]


def _ahead(block: FaceBlock) -> tuple[np.ndarray, float]:
    """The half-space ahead of the block's vertical plane, as a normal and
    an offset, the half-space being where a point's dot product with the
    normal is at most the offset, as
    :func:`~pymedphys._geometry.polygons.clip` keeps it."""
    normal, offset = _block_halves(block)[0]
    return -normal, -offset


def _intervals(
    halves: _Halves, starts: np.ndarray, ends: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return, for each segment, the bounds of the open interval of its
    parameter from 0 to 1 within the open region of ``halves``, which is
    empty where the lower is not less than the upper."""
    lower = np.zeros(len(starts))
    upper = np.ones(len(starts))
    for normal, offset in halves:
        first = starts @ normal - offset
        last = ends @ normal - offset
        rise = last - first
        with np.errstate(divide="ignore", invalid="ignore"):
            root = np.where(rise != 0, -first / np.where(rise != 0, rise, 1), 0.0)
        lower = np.where(rise > 0, np.maximum(lower, root), lower)
        upper = np.where(rise < 0, np.minimum(upper, root), upper)
        upper = np.where((rise == 0) & (first <= 0), -1.0, upper)
    return lower, upper


def _reaches(
    region: DoseBlock, starts: np.ndarray, ends: np.ndarray, step: float
) -> bool:
    """Whether a segment enters the block at a point that defacing writes
    as air, sampled at midpoints no more than ``step`` apart."""
    lower, upper = _intervals(_block_halves(region.block), starts, ends)
    inside = np.flatnonzero(lower < upper)
    if not len(inside):
        return False
    samples = []
    for index in inside:
        span = upper[index] - lower[index]
        length = float(np.linalg.norm(ends[index] - starts[index]))
        count = max(1, math.ceil(span * length / step))
        at = lower[index] + (np.arange(count) + 0.5) * span / count
        samples.append(
            starts[index] + at[:, np.newaxis] * (ends[index] - starts[index])
        )
    return bool(_defaced(region, np.concatenate(samples)).any())


def _defaced(region: DoseBlock, points: np.ndarray) -> np.ndarray:
    """Whether defacing writes air at the nearest pixel to each point, of
    the nearest slice that the block reaches, or, where none is near
    enough, whether the point is in the block."""
    block = region.block
    defaced = block.contains(points)
    slices, rows, columns = region.pixels(points)
    for index in np.unique(slices[slices >= 0]):
        chosen = slices == index
        each = region.slices[index]
        centres = (
            np.asarray(each.position)
            + columns[chosen, np.newaxis]
            * each.spacing[1]
            * np.asarray(each.orientation[:3])
            + rows[chosen, np.newaxis]
            * each.spacing[0]
            * np.asarray(each.orientation[3:])
        )
        defaced[chosen] = (
            block.contains(centres) & ~each.kept[rows[chosen], columns[chosen]]
        )
    return defaced


def _outside_polyline(halves: _Halves, points: np.ndarray) -> list[np.ndarray]:
    """Return the pieces of an open contour outside the open region of
    ``halves``, each of two points or more and some length."""
    lower, upper = _intervals(halves, points[:-1], points[1:])
    pieces: list[list[np.ndarray]] = []
    current: list[np.ndarray] = []
    for index in range(len(points) - 1):
        start, end = points[index], points[index + 1]
        if not current:
            current = [start]
        if not lower[index] < upper[index]:
            current.append(end)
            continue
        if lower[index] > 0:
            current.append(start + lower[index] * (end - start))
        pieces.append(current)
        current = []
        if upper[index] < 1:
            current = [start + upper[index] * (end - start), end]
    pieces.append(current)
    return [
        np.asarray(piece)
        for piece in pieces
        if len(piece) >= 2 and np.ptp(np.asarray(piece), axis=0).any()
    ]


def _decimals(points: np.ndarray) -> tuple[str, ...]:
    """A contour's points as Contour Data's decimal strings, of 16
    characters at most."""
    return tuple(
        pydicom.valuerep.format_number_as_ds(float(value)) for value in points.ravel()
    )


class PetDefacer:
    """Gives the face block of one PET slice, less what defacing keeps, as
    zero activity, for
    :func:`~pymedphys._dicom.deidentify.pixel_cleaning.black_out`.

    Parameters
    ----------
    region : DoseBlock or FrameRegion
        The block of the slice's Frame of Reference, or the blocks of each
        series defaced in it.
    dataset : pydicom.Dataset
        The slice's data set.

    Raises
    ------
    PixelDataRefused
        With :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` where
        the slice is not one that the module cleans.
    """

    def __init__(self, region: Region, dataset: pydicom.Dataset) -> None:
        try:
            syntax = str(dataset.file_meta.TransferSyntaxUID)
            if syntax not in NATIVE_TRANSFER_SYNTAXES and syntax not in (
                DECODING_PLUGINS
            ):
                raise ValueError("not decoded")
            layout = frames_layout(dataset, syntax)
            if layout.samples != 1:
                raise ValueError("not one sample")
            iod = iod_of(dataset)
            if iod == PET_IMAGE:
                if layout.frames != 1:
                    raise ValueError("not one frame")
                planes = (_pet_plane((dataset,) * 4, layout),)
            elif iod in MULTI_FRAME_PET_IODS:
                planes = tuple(
                    _pet_plane(
                        tuple(
                            frame_group(dataset, layout.frames, frame, keyword)
                            for keyword in (
                                "PlanePositionSequence",
                                "PlaneOrientationSequence",
                                "PixelMeasuresSequence",
                                "PixelValueTransformationSequence",
                            )
                        ),
                        layout,
                    )
                    for frame in range(layout.frames)
                )
            else:
                raise ValueError("not a PET image")
            padding = _padding(dataset, layout)
        # Whatever the data set raises refuses the image, without its
        # message, which could quote a value.
        except Exception:  # pylint: disable = broad-exception-caught
            raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA) from None
        self._region = region
        self._planes = planes
        self._shape = (layout.rows, layout.columns)
        self._padding = padding

    def __repr__(self) -> str:
        return "PetDefacer()"

    @property
    def held(self) -> VisualFeaturesReason | None:
        """None, since a PET image is set to zero activity in the block
        whatever its uptake there, as the CT is written as air."""
        return None

    def mask(self, frame: int, stored: np.ndarray) -> FrameMask | None:
        """Return the pixels of one frame to write as its zero activity, as
        the module describes, or None where the frame has none."""
        plane = self._planes[frame]
        inside = self._region.written(
            plane.position, plane.orientation, plane.spacing, self._shape
        )
        if self._padding is not None:
            low, high = self._padding
            stored = np.asarray(stored)
            inside &= ~((stored >= low) & (stored <= high))
        if not inside.any():
            return None
        return FrameMask(frame, inside, plane.background)


@dataclasses.dataclass(frozen=True)
class _PetPlane:
    """Where one PET slice or frame lies, and its stored value of zero
    activity."""

    position: tuple[float, float, float]
    orientation: tuple[float, ...]
    spacing: tuple[float, float]
    background: int


def _pet_plane(groups: tuple[pydicom.Dataset, ...], layout: Layout) -> _PetPlane:
    """Return where a PET slice or frame lies and its zero activity, from
    the data sets that hold its Image Position (Patient), Image Orientation
    (Patient), Pixel Spacing, and Rescale Slope and Rescale Intercept, in
    that order: the instance's own for a PET Image, or the frame's
    functional groups' items.

    Raises
    ------
    ValueError
        Where any is absent or cannot be read, or the module's checks fail,
        without any value.
    """
    placed, oriented, measured, rescaled = groups
    with redacted_diagnostics():
        x, y, z = _numbers(placed, "ImagePositionPatient", 3)
        orientation = _numbers(oriented, "ImageOrientationPatient", 6)
        _check_directions(orientation)
        rows, columns = _numbers(measured, "PixelSpacing", 2)
        (slope,) = _numbers(rescaled, "RescaleSlope", 1)
        (intercept,) = _numbers(rescaled, "RescaleIntercept", 1)
    if not min(rows, columns) > 0 or not slope > 0:
        raise ValueError("not a spacing or slope")
    _check_reach(((x, y, z),), orientation, (rows, columns), layout)
    exact = -intercept / slope
    low, high = stored_range(layout)
    # A finite but tiny slope gives an infinite stored value.
    if not math.isfinite(exact) or not low <= round(exact) <= high:
        raise ValueError("zero activity not stored")
    return _PetPlane((x, y, z), orientation, (rows, columns), int(round(exact)))
