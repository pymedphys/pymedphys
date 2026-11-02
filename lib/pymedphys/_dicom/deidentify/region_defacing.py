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

"""RT Structure Set contours and PET images in the Frame of Reference of a
defaced CT series, cleaned of the face in its block.

Under the Clean Recognizable Visual Features Option, the contours of an RT
Structure Set in the frame of a CT series that a run defaces
(:mod:`~pymedphys._dicom.deidentify.face_blocks`) can trace the face that
the CT no longer shows, as an outline of the skin does, and so can a PET
image's uptake at the skin. A run therefore cleans each in the same block,
as :mod:`~pymedphys._dicom.deidentify.dose_defacing` sets RT Dose to zero
there, on the block of the frame's one defaced series
(:class:`~.dose_defacing.DoseBlock`).

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

A structure set is cut only where each of its ROIs names the defaced
series' frame, and each contour has a known Contour Geometric Type, Contour
Data of finite coordinates, in threes, none greater in magnitude than
:data:`_FARTHEST`, and no Contour Offset Vector or Contour Slab Thickness,
which would place it elsewhere or give it depth. Any other stays held as an
instance in a defaced frame
(:attr:`~.reasons.VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME`), as does
one whose contours an ROI Contour Sequence item gives for an ROI that it
does not declare.

A PET Image instance of native Pixel Data, one frame, and one sample,
placed by Image Position (Patient), Image Orientation (Patient) of two
orthogonal unit vectors, and Pixel Spacing, with a Rescale Slope finite and
positive, and a Rescale Intercept whose zero activity a stored value can
hold, rounded, is written with each pixel whose centre is in the block,
other than one that defacing keeps or one of Pixel Padding Value or its
range, set to that stored value (:class:`PetDefacer`). Any other PET image,
and every Enhanced PET or Legacy Converted Enhanced PET image, stays held.
"""

from __future__ import annotations

import dataclasses
import math

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

from .defacing import ALIGNMENT_TOLERANCE, FaceBlock
from .diagnostics import redacted_diagnostics
from .dose_defacing import DoseBlock, _check_directions, _check_reach, _numbers
from .face_blocks import _padding
from .pixel_cleaning import FrameMask, PixelDataRefused, layout_of, stored_range
from .reasons import TransformReason, VisualFeaturesReason
from .source import NATIVE_TRANSFER_SYNTAXES
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
    region: DoseBlock, dataset: pydicom.Dataset, frame: str
) -> dict[int, tuple[WrittenContour, ...]]:
    """Return the contours of each ROI that the block changes, as the module
    describes.

    Parameters
    ----------
    region : DoseBlock
        The block of the structure set's Frame of Reference.
    dataset : pydicom.Dataset
        The structure set's data set.
    frame : str
        The Frame of Reference UID of the defaced series.

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
    step = (
        min(min(each.spacing) for each in region.slices) / 2 if region.slices else _STEP
    )
    try:
        with redacted_diagnostics():
            frames = {
                int(item.ROINumber): normalise_uid(
                    str(item.get("ReferencedFrameOfReferenceUID") or "")
                )
                for item in dataset.get("StructureSetROISequence") or []
            }
            if any(each != frame for each in frames.values()):
                raise ContoursRefused()
            cut = {}
            for index, item in enumerate(dataset.get("ROIContourSequence") or []):
                if int(item.ReferencedROINumber) not in frames:
                    raise ContoursRefused()
                written = _written(region, item.get("ContourSequence") or [], step)
                if written is not None:
                    cut[index] = written
            return cut
    except ContoursRefused:
        raise
    # pydicom raises many types for a value it cannot read, and a message can
    # quote the value: the structure set stays held.
    except Exception:  # pylint: disable = broad-exception-caught
        raise ContoursRefused() from None


def _written(
    region: DoseBlock, contours: pydicom.Sequence, step: float
) -> tuple[WrittenContour, ...] | None:
    """Return one ROI's contours as written, or None where none is cut.

    Closed contours in one plane bound one region together, as a hole's
    contour does within its outer one, so where one of them reaches the
    face, each of them is cut by the same region, the block less the
    pixels that defacing does not write as air where :class:`_Spare` can
    cut them all so, or else the whole block, and the region that they
    bound together loses just its part in it. Where any is cut, a closed
    contour that lies in no one plane is refused.

    Raises
    ------
    ContoursRefused
        Where a contour cannot be read, or a closed contour that lies in no
        one plane is in an ROI of which a contour is cut.
    """
    parsed = [_contour(contour) for contour in contours]
    cutting = [_reaches_face(region, kind, points, step) for kind, points in parsed]
    # Grouping only spreads a cut, so an ROI with none needs no grouping.
    if not any(cutting):
        return None
    closed = [index for index, (kind, _) in enumerate(parsed) if kind in CLOSED]
    groups, unplaced = coplanar([parsed[index][1] for index in closed], _COPLANAR)
    # A closed contour in no one plane cannot be decided with those it may
    # bound a region with, so an ROI that is cut with one is refused.
    if unplaced:
        raise ContoursRefused()
    spared: dict[int, list[np.ndarray]] = {}
    for group in groups:
        members = [closed[member] for member in group]
        if not any(cutting[index] for index in members):
            continue
        # Every contour of a plane is cut by the same region, the block less
        # the brain that defacing keeps where the plane allows, or the whole
        # block, so that the region they bound together loses just its part
        # in it.
        polygons = [_distinct(parsed[index][1]) for index in members]
        spare = _Spare.of(region, polygons)
        cuts = (
            []
            if spare is None
            else [
                spare.cut(each, parsed[index][0])
                for index, each in zip(members, polygons, strict=True)
            ]
        )
        joined = [each for each in cuts if each is not None]
        if len(joined) != len(members):
            for index in members:
                cutting[index] = _enters(region.block, parsed[index][1])
            continue
        for index, (cut, pieces) in zip(members, joined, strict=True):
            cutting[index], spared[index] = cut, pieces
    if not any(cutting):
        return None
    written: list[WrittenContour] = []
    for index, ((kind, points), cut) in enumerate(zip(parsed, cutting, strict=True)):
        if not cut:
            written.append(WrittenContour(index))
            continue
        pieces = (
            spared[index] if index in spared else _pieces(region.block, kind, points)
        )
        written.extend(
            WrittenContour(index, _decimals(piece), first == 0)
            for first, piece in enumerate(pieces)
        )
    return tuple(written)


@dataclasses.dataclass(frozen=True, repr=False)
class _Spare:
    """The pixels of the slice nearest one axial plane of an ROI's closed
    contours that defacing does not write as air, those of the brain kept
    in the block and those whose centres lie outside it, whose squares a
    contour cut in that plane keeps.

    Its ``repr`` shows nothing of it.
    """

    block: FaceBlock
    grid: PixelGrid
    spared: np.ndarray

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
        outside = _pieces(self.block, CLOSED_PLANAR, ring)
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


def _contour(contour: pydicom.Dataset) -> tuple[str, np.ndarray]:
    """Return a contour's geometric type and points.

    Raises
    ------
    ContoursRefused
        Where the module does not cut it.
    """
    kind = str(contour.get("ContourGeometricType") or "").strip().upper()
    if kind not in CLOSED | OPEN | {POINT}:
        raise ContoursRefused()
    for keyword in ("ContourOffsetVector", "ContourSlabThickness"):
        if keyword in contour and contour[keyword].value not in (None, "", []):
            raise ContoursRefused()
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
    return kind, points


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


def _enters(block: FaceBlock, points: np.ndarray) -> bool:
    """Whether a closed contour's segments enter the open block, which,
    since the block's part of the contour's plane is unbounded, is whether
    the region it bounds meets the block."""
    lower, upper = _intervals(block, *_segments(CLOSED_PLANAR, points))
    return bool((lower < upper).any())


def _pieces(block: FaceBlock, kind: str, points: np.ndarray) -> list[np.ndarray]:
    """Return the pieces of a contour outside the block, written in its
    place."""
    if kind == POINT or len(points) == 1:
        return []
    if kind in OPEN:
        return _outside_polyline(block, points)
    pieces = clip(points, *_behind(block))
    for part in clip(points, *_ahead(block)):
        pieces.extend(clip(part, *_below(block)))
    return [piece for piece in pieces if len(piece) >= 3]


def _behind(block: FaceBlock) -> tuple[np.ndarray, float]:
    """The half-space behind the block's vertical plane, as a normal and an
    offset, the half-space being where a point's dot product with the
    normal is at most the offset."""
    anterior = np.asarray(block.anterior, dtype=float)
    return anterior, float(np.dot(block.origin, anterior))


def _ahead(block: FaceBlock) -> tuple[np.ndarray, float]:
    """The half-space ahead of the block's vertical plane, as for
    :func:`_behind`."""
    normal, offset = _behind(block)
    return -normal, -offset


def _below(block: FaceBlock) -> tuple[np.ndarray, float]:
    """The half-space not above the block's axial plane, as for
    :func:`_behind`."""
    return np.array([0.0, 0.0, 1.0]), float(block.inferior_limit)


def _intervals(
    block: FaceBlock, starts: np.ndarray, ends: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return, for each segment, the bounds of the open interval of its
    parameter from 0 to 1 within the block, which is empty where the lower
    is not less than the upper."""
    anterior, origin = np.asarray(block.anterior), np.asarray(block.origin)
    lower = np.zeros(len(starts))
    upper = np.ones(len(starts))
    for first, last in (
        ((starts - origin) @ anterior, (ends - origin) @ anterior),
        (starts[:, 2] - block.inferior_limit, ends[:, 2] - block.inferior_limit),
    ):
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
    lower, upper = _intervals(region.block, starts, ends)
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


def _outside_polyline(block: FaceBlock, points: np.ndarray) -> list[np.ndarray]:
    """Return the pieces of an open contour outside the open block, each of
    two points or more and some length."""
    lower, upper = _intervals(block, points[:-1], points[1:])
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
    region : DoseBlock
        The block of the slice's Frame of Reference.
    dataset : pydicom.Dataset
        The slice's data set.

    Raises
    ------
    PixelDataRefused
        With :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` where
        the slice is not one that the module cleans.
    """

    def __init__(self, region: DoseBlock, dataset: pydicom.Dataset) -> None:
        try:
            if str(dataset.file_meta.TransferSyntaxUID) not in NATIVE_TRANSFER_SYNTAXES:
                raise ValueError("compressed")
            layout = layout_of(dataset)
            if layout.frames != 1 or layout.samples != 1:
                raise ValueError("not one frame of one sample")
            with redacted_diagnostics():
                position = _numbers(dataset, "ImagePositionPatient", 3)
                orientation = _numbers(dataset, "ImageOrientationPatient", 6)
                _check_directions(orientation)
                spacing = _numbers(dataset, "PixelSpacing", 2)
                (slope,) = _numbers(dataset, "RescaleSlope", 1)
                (intercept,) = _numbers(dataset, "RescaleIntercept", 1)
            _check_reach(
                ((position[0], position[1], position[2]),), orientation, spacing, layout
            )
            padding = _padding(dataset, layout)
            if min(spacing) <= 0 or slope <= 0:
                raise ValueError("not a spacing or slope")
            exact = -intercept / slope
            low, high = stored_range(layout)
            # A finite but tiny slope gives an infinite stored value.
            if not math.isfinite(exact) or not low <= round(exact) <= high:
                raise ValueError("zero activity not stored")
        # Whatever the data set raises refuses the slice, without its
        # message, which could quote a value.
        except Exception:  # pylint: disable = broad-exception-caught
            raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA) from None
        self._region = region
        self._position = position
        self._orientation = orientation
        self._spacing = (spacing[0], spacing[1])
        self._shape = (layout.rows, layout.columns)
        self._padding = padding
        self._background = int(round(exact))

    def __repr__(self) -> str:
        return "PetDefacer()"

    @property
    def held(self) -> VisualFeaturesReason | None:
        """None, since a PET image is set to zero activity in the block
        whatever its uptake there, as the CT is written as air."""
        return None

    def mask(self, frame: int, stored: np.ndarray) -> FrameMask | None:
        """Return the pixels to write as zero activity, as the module
        describes, or None where the slice has none."""
        inside = self._region.block.slice_mask(
            self._position, self._orientation, self._spacing, self._shape
        )
        if inside.any():
            rows, columns = np.nonzero(inside)
            points = (
                np.asarray(self._position)
                + columns[:, np.newaxis]
                * self._spacing[1]
                * np.asarray(self._orientation[:3])
                + rows[:, np.newaxis]
                * self._spacing[0]
                * np.asarray(self._orientation[3:])
            )
            inside[rows, columns] = ~self._region.kept(points)
        if self._padding is not None:
            low, high = self._padding
            stored = np.asarray(stored)
            inside &= ~((stored >= low) & (stored <= high))
        if not inside.any():
            return None
        return FrameMask(frame, inside, self._background)
