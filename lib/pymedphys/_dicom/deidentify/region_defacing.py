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
(:func:`cut_contours`): a pixel in the block, other than one of the cranial
cavity that defacing keeps. So a contour that lies behind the block, below
it, or within the kept cavity alone, as the brain's does above the orbits,
is kept whole. Each segment is sampled within the block at intervals of
half the smallest pixel spacing of those slices. A point with no such pixel
counts where it lies in the block.

Any other contour is cut by the block's two planes, so that what is written
of it lies outside the block or on its boundary, the kept cavity being cut
away with the rest: a closed contour, of Contour Geometric Type
CLOSED_PLANAR or CLOSEDPLANAR_XOR, is written as each polygon of its part
behind the block's vertical plane, and of its part ahead of that plane and
not above the block's axial plane, each its own contour of the same type;
an open contour, OPEN_PLANAR or OPEN_NONPLANAR, as each piece of it outside
the block; and a POINT contour not at all. A part of a polygon is found by
clipping it against one plane at a time, and its pieces are separated where
the plane cuts it into more than one, by pairing the points at which its
edges cross the plane along their line, as a simple polygon's do. Since
each of the two parts lies on its own side of the vertical plane, each
piece is disjoint from the others but for that plane, so the pieces of a
CLOSEDPLANAR_XOR contour combine as the contour's own part outside the
block does. The closed contours of an ROI in one plane bound one region
together, as a hole's contour does within its outer one, so where one of
them is cut, each of them that enters the block is cut too, even one that
enters only the kept cavity, so that a hole kept whole within the cavity
never becomes a region that the cut outer contour no longer surrounds.
Since each is cut to its part outside the same block, the region that they
bound together, whether by exclusive or or by union, is cut to its part
outside the block. A contour's plane is the one that best fits its points,
found for any winding and for a contour that crosses itself, and where a
closed contour of an ROI that is cut lies in no one plane, the structure
set is refused. Where the crossings cannot be paired, as for a polygon that
crosses itself, the part is written as one polygon joined along the plane,
which still lies outside the block. The first piece written of a contour
keeps its Contour Number, and the others have none, since a number names
one contour of its ROI. An ROI left with no contour is written without a
Contour Sequence, which is Type 3.

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

import collections
import dataclasses
import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from .defacing import FaceBlock
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
# off its plane, and is far less than half of any slice spacing. Grouping
# too much cuts more of the kept cavity; grouping too little can leave a
# hole whole within a contour that is cut.
_COPLANAR = 0.15


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
    face, each of them that enters the block is cut by it, and the region
    that they bound together loses just its part in the block. Where any
    is cut, a closed contour that lies in no one plane is refused.

    Raises
    ------
    ContoursRefused
        Where a contour cannot be read, or a closed contour that lies in no
        one plane is in an ROI of which a contour is cut.
    """
    parsed = [_contour(contour) for contour in contours]
    cutting = [_reaches_face(region, kind, points, step) for kind, points in parsed]
    closed = [index for index, (kind, _) in enumerate(parsed) if kind in CLOSED]
    groups, unplaced = _coplanar([parsed[index][1] for index in closed])
    # A closed contour in no one plane cannot be decided with those it may
    # bound a region with, so an ROI that is cut with one is refused.
    if unplaced and any(cutting):
        raise ContoursRefused()
    for group in groups:
        if any(cutting[closed[member]] for member in group):
            for member in group:
                cutting[closed[member]] = _enters(
                    region.block, parsed[closed[member]][1]
                )
    if not any(cutting):
        return None
    written: list[WrittenContour] = []
    for index, ((kind, points), cut) in enumerate(zip(parsed, cutting, strict=True)):
        if not cut:
            written.append(WrittenContour(index))
            continue
        written.extend(
            WrittenContour(index, _decimals(piece), first == 0)
            for first, piece in enumerate(_pieces(region.block, kind, points))
        )
    return tuple(written)


def _coplanar(polygons: list[np.ndarray]) -> tuple[list[list[int]], list[int]]:
    """Group polygons, by their indices, into those that lie in one plane,
    within :data:`_COPLANAR` millimetres, and list those that lie in none.

    A polygon's plane is the one that fits its points best, its normal
    the direction in which they spread least, so that it is found for any
    winding, and for a polygon that crosses itself, such as a bow tie,
    whose signed area may be zero. Two polygons lie in one plane where
    every point of one lies within :data:`_COPLANAR` of the other's plane,
    which holds for a small hole, whose own normal is uncertain, in a
    large contour's plane. Each pair is compared, and groups that share a
    polygon are joined, so that no polygon is kept from a group by the
    order in which they are given. A polygon whose points lie on one line
    bounds nothing and is alone; one with a point farther than
    :data:`_COPLANAR` from its own plane lies in none.
    """
    planes: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    alone: list[list[int]] = []
    unplaced: list[int] = []
    for index, points in enumerate(polygons):
        centre = points.mean(axis=0)
        _, spread, axes = np.linalg.svd(points - centre, full_matrices=False)
        if len(spread) < 3 or not spread[1] > 1e-9 * spread[0]:
            alone.append([index])
        elif not np.max(np.abs((points - centre) @ axes[2])) <= _COPLANAR:
            unplaced.append(index)
        else:
            planes[index] = (axes[2], centre)

    def within(polygon: int, plane: int) -> bool:
        normal, centre = planes[plane]
        return bool(np.max(np.abs((polygons[polygon] - centre) @ normal)) <= _COPLANAR)

    root = {index: index for index in planes}

    def find(index: int) -> int:
        while root[index] != index:
            root[index] = root[root[index]]
            index = root[index]
        return index

    placed = sorted(planes)
    for position, one in enumerate(placed):
        for other in placed[position + 1 :]:
            # A polygon's centre's signed distance from a plane is the mean
            # of its points', so where the centre lies farther, so does some
            # point, and the polygon is not in that plane.
            near = (
                abs(float(planes[other][0] @ (planes[one][1] - planes[other][1])))
                <= _COPLANAR
                or abs(float(planes[one][0] @ (planes[other][1] - planes[one][1])))
                <= _COPLANAR
            )
            if near and (within(one, other) or within(other, one)):
                root[find(one)] = find(other)
    groups: dict[int, list[int]] = collections.defaultdict(list)
    for index in placed:
        groups[find(index)].append(index)
    return sorted(groups.values()) + alone, unplaced


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
    pieces = _clip(points, *_behind(block))
    for part in _clip(points, *_ahead(block)):
        pieces.extend(_clip(part, *_below(block)))
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


def _clip(points: np.ndarray, normal: np.ndarray, offset: float) -> list[np.ndarray]:
    """Return the polygons of a polygon's part in the closed half-space where
    a point's dot product with ``normal`` is at most ``offset``.

    A vertex on the plane is taken to lie outside, so that the edges into
    and out of it cross the plane there, as the polygon's would if the
    vertex lay just beyond it.
    """
    distance = points @ normal - offset
    inside = distance < 0
    if inside.all():
        return [points]
    if not inside.any():
        return []
    # Each event: 0 for a vertex kept, 1 where an edge leaves the half-space,
    # and 2 where one enters it, with its point.
    events: list[tuple[int, np.ndarray]] = []
    count = len(points)
    for index in range(count):
        following = (index + 1) % count
        if inside[index]:
            events.append((0, points[index]))
        if inside[index] != inside[following]:
            near, far = distance[index], distance[following]
            if far == 0:
                crossing = points[following]
            elif near == 0:
                crossing = points[index]
            else:
                crossing = points[index] + near / (near - far) * (
                    points[following] - points[index]
                )
            events.append((1 if inside[index] else 2, crossing))
    joined = [point for _, point in events]
    start = next(i for i, (kind, _) in enumerate(events) if kind == 2)
    chains = _chains(events[start:] + events[:start])
    rings = None if chains is None else _rings(points, normal, chains)
    if rings is None:
        return [np.asarray(joined)]
    return rings


def _chains(events: list[tuple[int, np.ndarray]]) -> list[list[np.ndarray]] | None:
    """Split a polygon's events, starting with an entry, into chains, each
    from an entry through the vertices kept to the next exit; None where
    they do not run so."""
    chains: list[list[np.ndarray]] = []
    ended = True
    for kind, point in events:
        if (kind == 2) != ended:
            return None
        if kind == 2:
            chains.append([])
        chains[-1].append(point)
        ended = kind == 1
    return chains if ended else None


def _rings(
    points: np.ndarray, normal: np.ndarray, chains: list[list[np.ndarray]]
) -> list[np.ndarray] | None:
    """Join a polygon's chains into polygons along the plane, or None where
    their crossings cannot be paired.

    The crossings lie on the line where the plane meets the polygon's own.
    In order along it, each pair, the first and second, the third and
    fourth, and so on, bounds a stretch of the line within the polygon, so
    each pair is an exit and an entry, and each polygon runs along the
    plane from a chain's exit to the entry of its pair.
    """
    centred = points - points.mean(axis=0)
    # Newell's method gives the polygon's normal, scaled by twice its area.
    plane = np.cross(centred, np.roll(centred, -1, axis=0)).sum(axis=0)
    line = np.cross(plane, normal)
    length = float(np.linalg.norm(line))
    if not math.isfinite(length) or length <= 0:
        return None
    line /= length
    crossings = sorted(
        [(float(chain[0] @ line), 2, index) for index, chain in enumerate(chains)]
        + [(float(chain[-1] @ line), 1, index) for index, chain in enumerate(chains)],
        key=lambda crossing: crossing[0],
    )
    partner: dict[int, int] = {}
    for first, second in zip(crossings[::2], crossings[1::2]):
        if first[1] == second[1]:
            return None
        exit_, entry = (first, second) if first[1] == 1 else (second, first)
        partner[exit_[2]] = entry[2]
    rings = []
    joined: set[int] = set()
    for index in range(len(chains)):
        if index in joined:
            continue
        ring: list[np.ndarray] = []
        current = index
        while current not in joined:
            joined.add(current)
            ring.extend(chains[current])
            current = partner[current]
        if current != index:
            return None
        rings.append(np.asarray(ring))
    return rings


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
