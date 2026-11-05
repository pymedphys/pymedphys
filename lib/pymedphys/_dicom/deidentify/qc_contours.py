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
# One module draws, and proves complete, every row of a contour sheet.

"""Renders of RT Structure Set contours for the confidential QC pack's face
review (D-017, D-052).

An RT Structure Set has no pixel data, but its contours can trace the skin
surface, as an outline of the patient's body does, from which a
face-recognition system can match a face as it does from a CT's.
:func:`contour_sheet` renders the region that a structure set's contours,
as the run wrote them, bound, by :func:`~.qc_surfaces.views`, from the six
directions of :data:`~.qc_surfaces.VIEWS`, so that a reviewer can see a
face where its contours trace one. The sheet's rows, from the top,
separated by grey rows of :data:`GUTTER_PIXELS`, are:

- for each Frame of Reference of the ROIs, in the order of the first ROI
  in it: the region of every ROI in it, united; and, where the run wrote a
  volume in that frame, the surface render of that volume, in grey, with
  the edge of each view's silhouette of the united region drawn over it
  in magenta, so that the reviewer can see where the contours lie on the
  patient's surface; then
- for each item of the ROI Contour Sequence, in order, its region alone,
  since the united region hides an ROI wholly inside another, or a black
  row of :data:`GUTTER_PIXELS` for an item without contours. Where a ray
  of the frontal view, the view from behind, or a profile, which look
  along the axes of the voxels and so between them meet every voxel of the region's surface,
  crosses that surface more than twice, the region hides some of its
  surface behind its own, as one with a cavity within it, or with one
  part behind another, does. Its row is then followed by a row of its
  cavities, the voxels that each slice of the region encloses but does not
  hold, as a region of their own, where it has any; and by a row for each
  further crossing, in which each ray shows the surface where it crosses
  it, into or out of the region, that many times from the viewer, so that
  every surface that those rays cross is shown. One surface may be shown
  in parts across those rows, where rays cross different numbers of
  surfaces before it, so they are read together. The oblique views have
  no rows of crossings, since their rays, which step between voxels,
  cross a surface falsely where they graze it. A mark, below, is hidden
  where the ROI's closed contours fill its voxel, if it is a mark of a
  point, of an open contour, or of a closed contour that bounds no voxel,
  as a curve within a box is; and any mark is hidden where what its slice
  of voxels shows, the region and every mark there, holds every voxel
  within two of it in the slice, as around a contour that retraces a loop
  within its region, one that bounds a hole that its own marks or others
  fill, or one in a plane that covers no slice. Those marks, with every
  mark of the first kinds, then have rows of their own after the ROI's, in
  layers: each contour's hidden marks are in the first layer that holds
  none of their voxels, nor any beside one along its row or its column of
  voxels, so that a layer's rows draw each contour's marks as they would
  draw them alone, and a contour's marks the same as an earlier one's are
  left out. Each layer has rows as the ROI's region has, but with no row of
  cavities, and with a row for each further crossing however few times a
  ray crosses it, so that they show every crossing into or out of the
  layer that a ray of the frontal view, the view from behind, or a
  profile makes; so every mark is shown, in those rows or within two
  voxels of the edge of what its slice shows, which the ROI's rows draw
  from the front, the back, and the sides. A layer's rows are taken to
  draw every voxel of it only where each has a neighbour along its row or
  its column of voxels that is not in the layer, counting the views along
  the voxels' axes and not the oblique ones; where one does not, as where
  one contour's marks fill a patch, as a line drawn back and forth with no
  gap between its passes does, no sheet is drawn.

Those rows draw the contours as written. Contour Slab Thickness (3006,0044)
and Contour Offset Vector (3006,0045), which PS3.3 retired in 2021, made a
contour a slab of that thickness whose central plane is its Contour Data
moved by the offset (PS3.3-2020e C.8.8.6.2); a reader written since may
ignore both, and one written before may honour either alone. So where a
contour has either, the sheet also draws each further reading of
:data:`READINGS` that places a contour otherwise than every earlier one:
the offset alone, the thickness alone, and both. Each such reading's rows
follow a gutter of white, not grey: the united row of each frame, with its
volume's render where there is one, as above, then the rows of each item
whose contours the reading places otherwise than as written. A reading moves
each point of a contour by the whole offset vector. It gives a closed
contour's plane a slab along z, half its thickness below and above it,
which covers every slice of voxels within it, or the slice nearest the plane
where none is, and draws the contour's marks through it, at most half a
voxel apart; and it sweeps an open contour likewise along the normal of the
plane within :data:`COPLANAR` millimetres of which its points lie.

Each region is sampled to cubic voxels over the extent of what it draws,
with a voxel more on each low side across, 0 to 1 voxel more on each high
side, and up to a voxel more below, so that its edge and its lowest point
are drawn. A frame's united region has voxels of
:data:`~.qc_surfaces.MINIMUM_VOXEL` millimetres, as :mod:`~.qc_surfaces`
samples a volume, whatever the frame's extent, so
that a longer frame's rows are taller rather than coarser. An ROI alone has
the finer of those voxels and those that keep its extent within
:data:`ROI_VOXELS`, but none finer than
:data:`ROI_MINIMUM_VOXEL`, so that a small ROI is seen in detail, and an
ROI far from another no coarser than if it were alone. Each slice of
voxels is the region of the contours' plane that covers it: each plane of
an ROI, the mean height of its closed contours that lie within
:data:`COPLANAR` millimetres of one another in height, covers half the
distance to the ROI's next plane above and below it, or half the median
distance between its planes, or half a voxel where that is more, where
the next is farther than twice that median or there is none. A slice of
voxels that none of an ROI's planes covers holds none of its region, but
may hold a mark, below, of a contour within half a voxel of it. In a
plane, an ROI's region is the even-odd fill
(:func:`~pymedphys._geometry.rasters.even_odd`) of its closed contours there,
so that a contour within another is a hole, whether the contours are
CLOSED_PLANAR or CLOSEDPLANAR_XOR. The voxel nearest each point of a POINT
contour, or of a closed contour of fewer than three points, which bounds
nothing, is filled as a mark, and so is the voxel nearest each point along
an open contour's segments, and a closed contour's, taken at most half a
voxel apart, so that a marker such as an isocentre, or a line, is drawn
where it lies, and alone in its own ROI's row, where no other ROI hides it,
and a closed contour that bounds no area, such as one that doubles back on
itself, is drawn as its line.

A sheet is drawn only of contours that it can show (:func:`contours_of`):
each of Contour Geometric Type CLOSED_PLANAR, CLOSEDPLANAR_XOR, OPEN_PLANAR,
OPEN_NONPLANAR, or POINT, of finite coordinates, in threes, none greater in
magnitude than :data:`FARTHEST`, as each reading places it, with any Contour
Slab Thickness and Contour Offset Vector of one and three finite values,
none greater in magnitude than :data:`FARTHEST`, and no thickness below 0;
a thickness only where a reading gives it a plane to be normal to, so not
on a point, a closed contour of fewer than three points, or an open
contour on one line or not within :data:`COPLANAR` millimetres of a plane,
nor on a closed contour on one line or whose slab along z strays more than
:data:`COPLANAR` millimetres from its slab along its plane's normal
(:func:`_extrudes_along_z`);
for a closed contour of three or more points, with every point within
:data:`COPLANAR` millimetres of one axial plane, as
:mod:`~.region_defacing` groups contours, and the closed contours of each
such plane of one slab or none, since one may be a hole in another; and
the ROIs of each frame, as each reading places them, spanning at most :data:`LONGEST` millimetres along each axis, and at most
:data:`WIDEST` across, from left to right and from front to back, so that
its rows stay within the sheet's bounds at voxels fine enough to show a
face. A closed contour in an oblique,
coronal, or sagittal plane, whose region the slices of voxels would cut
edge on, is not drawn, so a structure set with one is not shown, and nor is
one with a contour of another type, or one that cannot be read.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Collection, Mapping, Sequence

from pymedphys._geometry.rasters import even_odd
from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import scipy

from . import qc_surfaces
from .uids import normalise_uid

CLOSED = frozenset({"CLOSED_PLANAR", "CLOSEDPLANAR_XOR"})
THICKNESS_KEYWORD = "ContourSlabThickness"
OFFSET_KEYWORD = "ContourOffsetVector"
# The readings of a contour's retired Contour Offset Vector and Contour Slab
# Thickness, in the order that a sheet draws them: neither, as a reader
# written since their retirement does; the offset alone; the thickness
# alone; and both, as PS3.3-2020e defines them.
AS_WRITTEN = "as-written"
OFFSET = "offset"
THICKNESS = "thickness"
BOTH = "offset-and-thickness"
READINGS = (AS_WRITTEN, OFFSET, THICKNESS, BOTH)
# The colour of the gutter above the first row of each further reading, so
# that each reading's rows can be told apart from the grey between rows.
_READING_GUTTER = (255, 255, 255)
OPEN = frozenset({"OPEN_PLANAR", "OPEN_NONPLANAR"})
POINT = "POINT"
# How far, in millimetres, a closed contour's points may lie from one axial
# plane, and contours' heights from one another's in one plane, as
# region_defacing groups a plane's contours: it allows for coordinates
# written to 0.1 mm, and is far less than half of any slice spacing.
COPLANAR = 0.15
# The largest magnitude, in millimetres, of a coordinate that is drawn.
FARTHEST = 1e6
# The longest span, in millimetres, along any axis, of the ROIs of one
# frame that a sheet draws, longer than a patient, and the widest across,
# from left to right or front to back, wider than any scanner's bore; so
# its voxels are at most 2 mm, and each row at most about 1,000 pixels
# tall and 4,300 wide, as :mod:`~.qc_surfaces` bounds a volume.
LONGEST = qc_surfaces.LONGEST
WIDEST = qc_surfaces.WIDEST
ROI_VOXELS = 128
ROI_MINIMUM_VOXEL = 0.5  # millimetres
GUTTER_PIXELS = 8
# The tallest contour sheet that is shown: each row of a frame whose ROIs
# span up to 510 mm along z is at most 257 voxels tall, as is the guide of
# a volume up to 510 mm long, so at least about 120 rows in one such frame,
# about 103 in ten frames each with such a guide, and about 2 fewer for each
# further frame with one; a row of an ROI, or a guide, 2,000 mm long is
# about 1,000 tall, so about 32 of them fit.
# An ROI item has one row, and more where it hides some of its surface
# behind its own, or its marks. A taller one is drawn only until it is too
# tall, and is not shown, so that its set is held rather than shown in an
# image that a viewer may scale down or refuse.
MAXIMUM_SHEET_PIXELS = 32768

# The views whose rays look along an axis of the voxels.
_ALONG = (0, 90, -90, 180)
# As a redaction preview's outline and gutter.
_OUTLINE = (255, 0, 255)
_GUTTER = (128, 128, 128)


@dataclasses.dataclass(frozen=True, repr=False)
class Sweep:
    """The span along which a contour with depth lies: each of its points
    moved by ``t`` times :attr:`direction`, for each ``t`` from :attr:`near`
    to :attr:`far`, in millimetres.

    Its ``repr`` shows nothing of it.
    """

    direction: tuple[float, float, float]
    near: float
    far: float

    def at(self, points: np.ndarray, distance: float) -> np.ndarray:
        """The points moved ``distance`` along :attr:`direction`."""
        return points + distance * np.asarray(self.direction)

    def swept(self, points: np.ndarray, step: float) -> np.ndarray:
        """The points at each end of the span and between, at most ``step``
        apart along it."""
        count = max(1, math.ceil((self.far - self.near) / step))
        return np.concatenate(
            [
                self.at(points, self.near + (self.far - self.near) * index / count)
                for index in range(count + 1)
            ]
        )

    def __repr__(self) -> str:
        return "Sweep()"


def _along_z(slab: tuple[float, float] | None) -> Sweep | None:
    """A closed contour's slab as the span of its points along z."""
    return None if slab is None else Sweep((0.0, 0.0, 1.0), slab[0], slab[1])


@dataclasses.dataclass(frozen=True, repr=False)
class RoiContours:
    """The contours of one item of an ROI Contour Sequence that a sheet draws.

    Its ``repr`` shows nothing of them.

    Attributes
    ----------
    closed : tuple of (float, numpy.ndarray)
        Each closed contour of three or more points, by the mean height of
        its points, z, in millimetres, and their x and y, of shape (n, 2).
    points : numpy.ndarray
        Each point of a POINT contour, or of a closed contour of fewer than
        three points, as x, y, and z, of shape (m, 3).
    lines : tuple of numpy.ndarray
        Each open contour's points, in order, as x, y, and z, of shape
        (n, 3).
    frame : str or None
        The Frame of Reference UID of its ROI, or None where none is named.
    slabs : tuple of (float, float) or None
        For each closed contour, where a reading of its Contour Slab
        Thickness gives it depth, how far its slab reaches along z below and
        above its height, in millimetres, the first at most 0 and the second
        at least 0; or None where it is a plane. Empty where none has depth.
    sweeps : tuple of Sweep or None
        Likewise, for each open contour, the span along which its depth
        moves its points; or None where it has none. Empty where none has
        depth.
    """

    closed: tuple[tuple[float, np.ndarray], ...] = ()
    points: np.ndarray = dataclasses.field(
        default_factory=lambda: np.zeros((0, 3), float)
    )
    lines: tuple[np.ndarray, ...] = ()
    frame: str | None = None
    slabs: tuple[tuple[float, float] | None, ...] = ()
    sweeps: tuple[Sweep | None, ...] = ()

    def slab(self, index: int) -> tuple[float, float] | None:
        """The slab of its closed contour at ``index``, or None."""
        return self.slabs[index] if self.slabs else None

    def sweep(self, index: int) -> Sweep | None:
        """The sweep of its open contour at ``index``, or None."""
        return self.sweeps[index] if self.sweeps else None

    @property
    def empty(self) -> bool:
        """Whether it has no contour."""
        return not self.closed and not len(self.points) and not self.lines

    def coordinates(self) -> np.ndarray:
        """Every point that it draws, as x, y, and z, of shape (m, 3), with
        each point of a contour with depth at both ends of its span, whose
        extent then holds the whole span."""
        rings = []
        for index, (height, ring) in enumerate(self.closed):
            slab = self.slab(index)
            for reach in (0.0,) if slab is None else slab:
                rings.append(
                    np.column_stack([ring, np.full(len(ring), height + reach)])
                )
        lines = []
        for index, line in enumerate(self.lines):
            sweep = self.sweep(index)
            lines.extend(
                [line]
                if sweep is None
                else [sweep.at(line, sweep.near), sweep.at(line, sweep.far)]
            )
        return np.concatenate([*rings, *lines, self.points])

    def marks(self, step: float) -> np.ndarray:
        """Its points, and points along each open contour's segments, and
        each closed contour's, its last point joined to its first, at most
        ``step`` apart, as x, y, and z, of shape (m, 3)."""
        return np.concatenate(
            [self.points, *self.contour_marks(step)[len(self.points) :]]
        )

    def contour_marks(self, step: float) -> list[np.ndarray]:
        """The marks of :meth:`marks`, by contour: each point alone, then
        each open contour's, then each closed contour's, each as x, y, and
        z, of shape (m, 3). A contour with depth has its marks repeated
        along its span, at most ``step`` apart, from one end to the other."""
        sampled = [point[np.newaxis] for point in self.points]
        rings = [
            np.column_stack([ring, np.full(len(ring), height)])
            for height, ring in self.closed
        ]
        spans = [self.sweep(index) for index in range(len(self.lines))] + [
            _along_z(self.slab(index)) for index in range(len(self.closed))
        ]
        for line, span in zip(
            [*self.lines, *(np.vstack([ring, ring[:1]]) for ring in rings)],
            spans,
            strict=True,
        ):
            starts, steps = line[:-1], np.diff(line, axis=0)
            counts = np.maximum(
                1, np.ceil(np.linalg.norm(steps, axis=1) / step).astype(np.intp)
            )
            # Each segment's points from its start, at fractions of it.
            segment = np.repeat(np.arange(len(starts)), counts)
            first = np.cumsum(counts) - counts
            fractions = (np.arange(int(counts.sum())) - first[segment]) / counts[
                segment
            ]
            along = np.concatenate(
                [
                    line[-1:],
                    starts[segment] + fractions[:, np.newaxis] * steps[segment],
                ]
            )
            sampled.append(along if span is None else span.swept(along, step))
        return sampled

    def __repr__(self) -> str:
        return "RoiContours()"


@dataclasses.dataclass(frozen=True, repr=False)
class Contours:
    """The contours of an RT Structure Set that a sheet draws.

    Its ``repr`` shows only how many ROIs it has.

    Attributes
    ----------
    rois : tuple of RoiContours
        For each item of the ROI Contour Sequence, in order, as written,
        without the retired Contour Offset Vector or Contour Slab
        Thickness.
    series : frozenset of str
        The Series Instance UIDs of the image series that it references.
    readings : tuple of tuple of RoiContours
        For each further reading of those retired attributes, in the order
        of :data:`READINGS`, that moves or gives depth to a contour, as
        ``rois`` gives them, the ROIs as that reading places them; a reading
        that places every contour as an earlier one does is left out.
    """

    rois: tuple[RoiContours, ...]
    series: frozenset[str] = frozenset()
    readings: tuple[tuple[RoiContours, ...], ...] = ()

    @property
    def drawn(self) -> tuple[tuple[RoiContours, ...], ...]:
        """The ROIs as written, then as each further reading places them."""
        return (self.rois, *self.readings)

    @property
    def frames(self) -> tuple[str | None, ...]:
        """The frames of its ROIs with contours, in the order of the first
        ROI in each."""
        return tuple(dict.fromkeys(roi.frame for roi in self.rois if not roi.empty))

    @property
    def empty(self) -> bool:
        """Whether it has no contour."""
        return all(roi.empty for roi in self.rois)

    def __repr__(self) -> str:
        return f"Contours(rois={len(self.rois)})"


@dataclasses.dataclass(frozen=True, repr=False)
class Guide:
    """The surface of a volume that a sheet is drawn with.

    Attributes
    ----------
    inside : numpy.ndarray
        The voxels in its surface, indexed from superior, from anterior,
        and from the patient's right, as
        :meth:`~.qc_surfaces.Surface.mask` gives them.
    zs, ys, xs : numpy.ndarray
        The patient coordinate of each voxel along each axis, in
        millimetres: z descending, y and x ascending.
    """

    inside: np.ndarray
    zs: np.ndarray
    ys: np.ndarray
    xs: np.ndarray

    def __repr__(self) -> str:
        return f"Guide(shape={self.inside.shape})"


def has_contours(dataset: pydicom.Dataset) -> bool:
    """Whether a data set's ROI Contour Sequence holds a contour.

    One that cannot be read is taken to hold one.
    """
    try:
        return any(
            len(item.get("ContourSequence") or [])
            for item in dataset.get("ROIContourSequence") or []
        )
    # pydicom raises many types for a value that it cannot read.
    except Exception:  # pylint: disable = broad-exception-caught
        return True


def contours_of(dataset: pydicom.Dataset) -> Contours | None:
    """Return the contours of a structure set, or None where a sheet cannot
    show every one of them, as the module describes."""
    drawn: list[tuple[RoiContours, ...]] = []
    keys: set[tuple[bytes, ...]] = set()
    try:
        frames = _frames(dataset)
        for reading in READINGS:
            rois = tuple(
                _roi(
                    item.get("ContourSequence") or [],
                    frames.get(_number(item)),
                    reading,
                )
                for item in dataset.get("ROIContourSequence") or []
            )
            if any(roi is None for roi in rois):
                return None
            placed = tuple(roi for roi in rois if roi is not None)
            key = tuple(_key(roi) for roi in placed)
            if key not in keys:
                keys.add(key)
                drawn.append(placed)
    # pydicom raises many types for a value that it cannot read.
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    found = Contours(drawn[0], _series(dataset), tuple(drawn[1:]))
    for rois in found.drawn:
        for frame in found.frames:
            points = np.concatenate(
                [roi.coordinates() for roi in rois if roi.frame == frame]
            )
            spans = np.ptp(points, axis=0)
            if spans.max() > LONGEST or spans[:2].max() > WIDEST:
                return None
    return found


def _number(item: pydicom.Dataset) -> int | None:
    number = item.get("ReferencedROINumber")
    return None if number in (None, "") else int(number)


def _frames(dataset: pydicom.Dataset) -> dict[int, str | None]:
    """Each declared ROI's Frame of Reference UID, by ROI Number; one that
    names none takes the structure set's, if it references only one."""
    referenced = {
        normalise_uid(str(frame.get("FrameOfReferenceUID") or ""))
        for frame in dataset.get("ReferencedFrameOfReferenceSequence") or []
    } - {""}
    only = next(iter(referenced)) if len(referenced) == 1 else None
    frames: dict[int, str | None] = {}
    for roi in dataset.get("StructureSetROISequence") or []:
        uid = normalise_uid(str(roi.get("ReferencedFrameOfReferenceUID") or ""))
        frames[int(roi.ROINumber)] = uid or only
    return frames


def _series(dataset: pydicom.Dataset) -> frozenset[str]:
    """The image Series Instance UIDs that a structure set references; none
    where they cannot be read."""
    found: set[str] = set()
    try:
        for frame in dataset.get("ReferencedFrameOfReferenceSequence") or []:
            for study in frame.get("RTReferencedStudySequence") or []:
                for series in study.get("RTReferencedSeriesSequence") or []:
                    found.add(normalise_uid(str(series.get("SeriesInstanceUID") or "")))
    # pydicom raises many types for a value that it cannot read; a sheet is
    # then drawn with the first volume of each frame.
    except Exception:  # pylint: disable = broad-exception-caught
        return frozenset()
    return frozenset(found - {""})


def _roi(  # pylint: disable = too-many-return-statements
    contours: pydicom.Sequence, frame: str | None, reading: str = AS_WRITTEN
) -> RoiContours | None:
    """The contours of one item of an ROI Contour Sequence, as ``reading``
    places them, or None where a sheet cannot draw them so."""
    closed: list[tuple[float, np.ndarray]] = []
    points: list[np.ndarray] = []
    lines: list[np.ndarray] = []
    slabs: list[tuple[float, float] | None] = []
    sweeps: list[Sweep | None] = []
    for contour in contours:
        kind = str(contour.get("ContourGeometricType") or "").strip().upper()
        if kind not in CLOSED | OPEN | {POINT}:
            return None
        retired = _retired(contour)
        if retired is None:
            return None
        depth = retired[0] if reading in (THICKNESS, BOTH) else 0.0
        moved = retired[1] if reading in (OFFSET, BOTH) else np.zeros(3)
        data = contour.get("ContourData")
        values = (
            [float(each) for each in data]
            if isinstance(data, (list, tuple, pydicom.multival.MultiValue))
            else []
            if data is None
            else [float(data)]
        )
        if not values or len(values) % 3 or not all(math.isfinite(v) for v in values):
            return None
        found = np.asarray(values).reshape(-1, 3) + moved
        if not (np.abs(found) <= FARTHEST).all():
            return None
        if kind in OPEN and len(found) > 1:
            sweep = None
            if depth:
                normal = _normal(found)
                if normal is None:
                    return None
                sweep = Sweep(normal, -depth / 2, depth / 2)
            lines.append(found)
            sweeps.append(sweep)
            continue
        if kind == POINT or len(found) < 3:
            # A point, or a closed contour that bounds nothing, has no
            # plane for a thickness to be normal to.
            if depth:
                return None
            points.append(found)
            continue
        low, high = float(found[:, 2].min()), float(found[:, 2].max())
        if not high - low <= 2 * COPLANAR:
            return None
        if depth and not _extrudes_along_z(found, depth):
            return None
        closed.append((float(found[:, 2].mean()), found[:, :2]))
        slabs.append((-depth / 2, depth / 2) if depth else None)
    roi = RoiContours(
        tuple(closed),
        np.concatenate(points) if points else np.zeros((0, 3), float),
        tuple(lines),
        frame,
        tuple(slabs) if any(slabs) else (),
        tuple(sweeps) if any(sweeps) else (),
    )
    return roi if _slabs_agree(roi) else None


def _retired(contour: pydicom.Dataset) -> tuple[float, np.ndarray] | None:
    """A contour's Contour Slab Thickness and Contour Offset Vector, 0 and
    (0, 0, 0) where absent or empty; or None where either has another number
    of values than 1 and 3, or a value that is not finite or is beyond
    :data:`FARTHEST`, or the thickness is below 0."""
    found = []
    for keyword, count in ((THICKNESS_KEYWORD, 1), (OFFSET_KEYWORD, 3)):
        value = contour[keyword].value if keyword in contour else None
        if value in (None, "", []):
            found.append(np.zeros(count))
            continue
        values = np.asarray(
            [float(each) for each in value]
            if isinstance(value, (list, tuple, pydicom.multival.MultiValue))
            else [float(value)]
        )
        if len(values) != count or not (
            np.isfinite(values).all() and (np.abs(values) <= FARTHEST).all()
        ):
            return None
        found.append(values)
    thickness, offset = found
    if thickness[0] < 0:
        return None
    return float(thickness[0]), offset


def _extrudes_along_z(points: np.ndarray, thickness: float) -> bool:
    """Whether a closed contour's slab of ``thickness``, drawn along z, lies
    within :data:`COPLANAR` millimetres of its slab along its plane's normal.

    Its points must lie within :data:`COPLANAR` millimetres of a plane, not
    on one line (:func:`_normal`). At a depth t within the slab, the unit
    normal n and the unit z of the same sign take a point t |n - z| apart,
    most at either face, so the slab is drawn along z only where that is at
    most :data:`COPLANAR`, the tolerance within which the sheet already
    flattens a closed contour onto its axial plane. A narrow contour tilted
    within the height that the sheet allows a closed contour, and given a
    thickness far greater, is so refused rather than drawn as a slab of
    another shape.
    """
    normal = _normal(points)
    if normal is None:
        return False
    apart = math.hypot(normal[0], normal[1], 1.0 - abs(normal[2]))
    return thickness / 2 * apart <= COPLANAR


def _normal(points: np.ndarray) -> tuple[float, float, float] | None:
    """The unit normal of the plane within :data:`COPLANAR` millimetres of
    which a contour's points lie, or None where they lie on one line, or
    off any such plane, so that no thickness can be given them."""
    if len(points) < 3:
        return None
    centre = points.mean(axis=0)
    _, spread, axes = np.linalg.svd(points - centre, full_matrices=False)
    if len(spread) < 3 or not spread[1] > 1e-9 * spread[0]:
        return None
    normal = axes[2]
    if not np.max(np.abs((points - centre) @ normal)) <= COPLANAR:
        return None
    return (float(normal[0]), float(normal[1]), float(normal[2]))


def _slabs_agree(roi: RoiContours) -> bool:
    """Whether the closed contours of each of an ROI's planes have one slab,
    or none, so that a plane's even-odd fill, in which one may be a hole in
    another, has one depth."""
    if not roi.slabs:
        return True
    planes = _planes(roi)
    of = _plane_of(roi, planes)
    return all(
        len({roi.slab(index) for index in np.flatnonzero(of == plane)}) <= 1
        for plane in range(len(planes))
    )


@dataclasses.dataclass(frozen=True)
class _Grid:
    """The patient coordinates of a sampled region's voxels along each axis."""

    zs: np.ndarray  # descending
    ys: np.ndarray  # ascending
    xs: np.ndarray  # ascending

    @property
    def voxel(self) -> float:
        """The voxels' side, or 0 where every axis has one voxel."""
        steps = [
            float(abs(axis[1] - axis[0]))
            for axis in (self.zs, self.ys, self.xs)
            if len(axis) > 1
        ]
        return max(steps, default=0.0)


def contour_sheet(
    contours: Contours,
    guides: Mapping[str | None, Guide] | None = None,
    tallest: int | None = None,
) -> np.ndarray | None:
    """Return the sheet of a structure set's contours, as the module
    describes, in RGB.

    Parameters
    ----------
    contours : Contours
        The structure set's contours as written, not all empty.
    guides : mapping of str to Guide, optional
        The volume that the sheet is drawn with in each Frame of Reference,
        by its UID.
    tallest : int, optional
        The most pixels that the sheet may be tall.

    Returns
    -------
    numpy.ndarray or None
        uint8, of shape (rows, columns, 3); or None where the sheet would be
        taller than ``tallest``, which is drawn only until it is, or where
        the frontal view, the view from behind, and the profiles of the
        rows of a layer of an ROI's hidden marks would leave any voxel of
        it undrawn.
    """
    guides = {} if guides is None else guides
    if contours.empty:
        raise ValueError("a contour sheet needs a contour")
    # Each ROI's planes, so that the planes of one ROI never empty another's
    # slices.
    if tallest is not None and _least_height(contours, guides) > tallest:
        return None
    rows: list[np.ndarray] = []
    # The rows that start a further reading.
    readings: set[int] = set()
    height = -GUTTER_PIXELS

    def fits(more: Sequence[np.ndarray]) -> bool:
        nonlocal height
        rows.extend(more)
        height += sum(row.shape[0] + GUTTER_PIXELS for row in more)
        return tallest is None or height <= tallest

    # An ROI the same as an earlier one, as a copied item is, is rendered
    # once, though each has its rows.
    rendered: dict[bytes, list[np.ndarray] | None] = {}
    for index, drawn in enumerate(contours.drawn):
        if index:
            readings.add(len(rows))
        planes = [_planes(roi) for roi in drawn]
        for frame in contours.frames:
            chosen = [i for i, roi in enumerate(drawn) if roi.frame == frame]
            rois = [drawn[i] for i in chosen]
            grid = _grid(rois, _united_voxel)
            shown = [planes[i] for i in chosen]
            if not fits([rgb(_views(_mask(rois, grid, shown)))]):
                return None
            guide = guides.get(frame)
            if guide is not None and not fits(
                [guided(guide, _mask(rois, _of(guide), shown))]
            ):
                return None
        for item, (roi, own) in enumerate(zip(drawn, planes, strict=True)):
            # A further reading draws only the items that it places
            # otherwise than as written.
            if index and _key(roi) == _key(contours.rois[item]):
                continue
            if roi.empty:
                if not fits([np.zeros((GUTTER_PIXELS, 1, 3), np.uint8)]):
                    return None
                continue
            key = _key(roi)
            if key not in rendered:
                rendered[key] = _item_rows(
                    roi, own, None if tallest is None else tallest - height
                )
            shown = rendered[key]
            if shown is None or not fits(shown):
                return None
    return stacked(rows, readings)


def _item_rows(
    roi: RoiContours, planes: np.ndarray, room: int | None = None
) -> list[np.ndarray] | None:
    """An ROI's rows, with those of each layer of the marks that its region
    hides; or None where the frontal view, the view from behind, and the
    profiles of a layer's rows would leave any voxel of it undrawn, or
    where the rows, each with the gutter above it, would take more than
    ``room`` pixels."""
    grid = _grid([roi], _roi_voxel)
    filled = _filled(roi, grid, planes)
    rows = _roi_rows(filled | _marked(roi.marks(_step(grid)), grid), room=room)
    left = None if room is None or rows is None else room - _height(rows)
    if rows is None or (left is not None and left < 0):
        return None
    # Its hidden marks are found only where its own rows fit.
    hidden = _hidden(roi, grid, filled)
    if hidden is None:
        return rows
    # Each layer has a row at least.
    most = None if left is None else left // (len(grid.zs) + GUTTER_PIXELS)
    layers = _layered(hidden, filled.shape, most)
    if layers is None or any(
        _undrawn(_layer(voxels, filled.shape)).any() for voxels in layers
    ):
        return None
    for voxels in layers:
        more = _roi_rows(_layer(voxels, filled.shape), marks=True, room=left)
        if more is None or (left is not None and _height(more) > left):
            return None
        rows.extend(more)
        if left is not None:
            left -= _height(more)
    return rows


def _height(rows: Sequence[np.ndarray]) -> int:
    """The pixels that rows take on a sheet, each with the gutter above it."""
    return sum(row.shape[0] + GUTTER_PIXELS for row in rows)


def _layer(voxels: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    """A mask of ``shape`` of a layer's voxels, by flat index."""
    layer = np.zeros(shape, bool)
    layer.flat[voxels] = True
    return layer


def _least_height(contours: Contours, guides: Mapping[str | None, Guide]) -> int:
    """The height, in pixels, of a sheet without the rows of any ROI's
    cavities, of the surfaces that it hides behind its own, or of the marks
    that it hides, found without drawing it."""
    heights = []
    for index, drawn in enumerate(contours.drawn):
        for frame in contours.frames:
            rois = [roi for roi in drawn if roi.frame == frame]
            heights.append(len(_grid(rois, _united_voxel).zs))
            guide = guides.get(frame)
            if guide is not None:
                heights.append(guide.inside.shape[0])
        heights.extend(
            GUTTER_PIXELS if roi.empty else len(_grid([roi], _roi_voxel).zs)
            for item, roi in enumerate(drawn)
            if not index or _key(roi) != _key(contours.rois[item])
        )
    return sum(heights) + GUTTER_PIXELS * (len(heights) - 1)


def _roi_rows(
    inside: np.ndarray, marks: bool = False, room: int | None = None
) -> list[np.ndarray] | None:
    """An ROI's rows, or those of a layer of its hidden marks, as the module
    describes, from their voxels; a layer has no row of cavities, and a row
    of each further crossing however few times a ray crosses it. None,
    before any is drawn, where the rows that it draws at least, each with
    the gutter above it, would take more than ``room`` pixels."""
    # The rays of the views that look along an axis of the voxels meet every
    # voxel of its surface, and cross the surface more than twice only where
    # it hides some of its surface behind its own; the oblique views' rays,
    # which step between voxels, cross a surface falsely where they graze it.
    most = max(qc_surfaces.most_crossings(inside, axis) for axis in (1, 2))
    crossed = marks or most > 2
    # The views' row, and a row for each crossing after the first.
    least = 1 + (max(most - 1, 0) if crossed else 0)
    if room is not None and least * (len(inside) + GUTTER_PIXELS) > room:
        return None
    # So, within a sheet's height bound, the crossings found are at most
    # about 32,768 by 711 for each of four views, as 16-bit integers, some
    # 190 MB, however intricate the region.
    rows = [rgb(_views(inside))]
    if not crossed:
        return rows
    if not marks:
        # Each slice's cavities: what its region encloses, but does not hold.
        within = np.zeros((3, 3, 3), bool)
        within[1] = [[False, True, False], [True, True, True], [False, True, False]]
        enclosed = scipy.ndimage.binary_fill_holes(inside, within) & ~inside
        if enclosed.any():
            rows.append(rgb(_views(enclosed)))
    along = dict(zip(_ALONG, qc_surfaces.view_crossings(inside, _ALONG)))
    none = np.full(along[0].shape[1:], -1)
    for crossing in range(1, max(len(each) for each in along.values())):
        tiles = []
        for view in qc_surfaces.VIEWS:
            each = along.get(view)
            tiles.append(
                none if each is None or crossing >= len(each) else each[crossing]
            )
        rows.append(rgb(_tiles(tiles)))
    return rows


def _undrawn(marks: np.ndarray) -> np.ndarray:
    """The voxels of a layer of hidden marks that its rows, which show every
    crossing into or out of it that a ray of the frontal view, the view
    from behind, or a profile makes, draw in no tile: those whose neighbours
    along their row and their column of voxels are all in the layer too.
    The oblique views are not counted, so as to claim no voxel that they may
    miss."""
    around = np.zeros((3, 3, 3), bool)
    around[1] = [[False, True, False], [True, True, True], [False, True, False]]
    return marks & scipy.ndimage.binary_erosion(marks, around, border_value=0)


def _tiles(depths: Sequence[np.ndarray]) -> np.ndarray:
    return qc_surfaces.side_by_side([qc_surfaces.shaded(each) for each in depths])


def _key(roi: RoiContours) -> bytes:
    """What an ROI draws, and in which frame, as bytes."""
    parts = [str(roi.frame).encode("utf-8", "surrogateescape"), b"|"]
    for index, (height, ring) in enumerate(roi.closed):
        parts.extend([b"c", np.float64(height).tobytes(), _sized(ring)])
        slab = roi.slab(index)
        if slab is not None:
            parts.extend([b"s", _sized(np.asarray(slab))])
    parts.extend([b"p", _sized(roi.points)])
    for index, line in enumerate(roi.lines):
        parts.extend([b"l", _sized(line)])
        sweep = roi.sweep(index)
        if sweep is not None:
            parts.extend(
                [b"w", _sized(np.asarray([*sweep.direction, sweep.near, sweep.far]))]
            )
    return b"".join(parts)


def _sized(values: np.ndarray) -> bytes:
    data = np.ascontiguousarray(values, np.float64)
    return np.int64(data.size).tobytes() + data.tobytes()


def _views(inside: np.ndarray) -> np.ndarray:
    return qc_surfaces.side_by_side(qc_surfaces.views(inside))


def _of(guide: Guide) -> _Grid:
    return _Grid(guide.zs, guide.ys, guide.xs)


def _united_voxel(extent: float) -> float:  # pylint: disable = unused-argument
    """The side of a united region's voxels, whatever its extent: as fine as
    a volume's surface render samples one, and no coarser for a long one,
    whose rows are taller instead."""
    return qc_surfaces.MINIMUM_VOXEL


def _roi_voxel(extent: float) -> float:
    """The side of an ROI's own voxels: the finer of those that a united
    region of its extent would have and those that keep it within
    ``ROI_VOXELS``, but none finer than ``ROI_MINIMUM_VOXEL``, so that an ROI
    far from another is sampled as if alone."""
    return max(ROI_MINIMUM_VOXEL, min(extent / (ROI_VOXELS - 1), _united_voxel(extent)))


def _grid(rois: Sequence[RoiContours], voxel_of: Callable[[float], float]) -> _Grid:
    """The voxels over the extent of what the ROIs draw, of the side that
    ``voxel_of`` gives for its longest axis."""
    points = np.concatenate([roi.coordinates() for roi in rois])
    low, high = points.min(axis=0), points.max(axis=0)
    voxel = voxel_of(float((high - low).max()))
    # A voxel more on each low side across, and 0 to 1 more on each high
    # side, as the division falls, and up to one more below, where the
    # slices, which start at the top, would otherwise stop short of the
    # lowest point, so that a region's edge and every point are drawn.
    low -= voxel
    high[:2] += voxel

    def axis(start: float, length: float) -> np.ndarray:
        # The end is kept, though the division may fall a little short of it.
        return start + np.arange(math.floor(length / voxel + 1e-6) + 1) * voxel

    return _Grid(
        float(high[2]) - axis(0.0, float(high[2] - low[2])),
        axis(float(low[1]), float(high[1] - low[1])),
        axis(float(low[0]), float(high[0] - low[0])),
    )


def _planes(roi: RoiContours) -> np.ndarray:
    """The heights of the planes of an ROI's closed contours, ascending."""
    heights = np.sort([height for height, _ in roi.closed])
    if not heights.size:
        return heights
    breaks = np.flatnonzero(np.diff(heights) > COPLANAR) + 1
    return np.array([group.mean() for group in np.split(heights, breaks)])


def _covering(planes: np.ndarray, zs: np.ndarray, voxel: float) -> np.ndarray:
    """For each height, the index of the plane that covers it, or -1."""
    if not planes.size:
        return np.full(len(zs), -1, np.intp)
    gaps = np.diff(planes)
    typical = float(np.median(gaps)) if gaps.size else 0.0
    limit = max(typical / 2, voxel / 2)
    halves = np.where(gaps <= 2 * typical, gaps / 2, limit)
    below = np.concatenate([[limit], halves])
    above = np.concatenate([halves, [limit]])
    right = np.clip(np.searchsorted(planes, zs), 1, max(len(planes) - 1, 1))
    left = right - 1
    if len(planes) == 1:
        nearest = np.zeros(len(zs), np.intp)
    else:
        nearest = np.asarray(
            np.where(zs - planes[left] <= planes[right] - zs, left, right), np.intp
        )
    offset = zs - planes[nearest]
    covered = np.where(offset >= 0, offset <= above[nearest], -offset <= below[nearest])
    return np.where(covered, nearest, -1)


def _mask(
    rois: Sequence[RoiContours], grid: _Grid, planes: Sequence[np.ndarray]
) -> np.ndarray:
    """The voxels of the ROIs' regions, united, indexed as a surface's mask;
    each ROI's slices of voxels are covered by its own ``planes``."""
    inside = np.zeros((len(grid.zs), len(grid.ys), len(grid.xs)), bool)
    for roi, own in zip(rois, planes, strict=True):
        inside |= _filled(roi, grid, own) | _marked(roi.marks(_step(grid)), grid)
    return inside


def _plane_of(roi: RoiContours, planes: np.ndarray) -> np.ndarray:
    """For each of an ROI's closed contours, the index of its plane among
    ``planes``: the nearest, within which it lies."""
    heights = np.array([height for height, _ in roi.closed])
    return np.abs(heights[:, np.newaxis] - planes[np.newaxis, :]).argmin(axis=1)


def _filled(roi: RoiContours, grid: _Grid, planes: np.ndarray) -> np.ndarray:
    """The voxels that an ROI's closed contours fill, indexed as a surface's
    mask, its slices of voxels covered by its ``planes``; or, for a plane
    whose contours have a slab, the slices within it, or the slice nearest
    the plane where none is."""
    filled = np.zeros((len(grid.zs), len(grid.ys), len(grid.xs)), bool)
    if roi.closed:
        covering = _covering(planes, grid.zs, grid.voxel)
        of = _plane_of(roi, planes)
        for plane in np.unique(of):
            first = int(np.flatnonzero(of == plane)[0])
            slab = roi.slab(first)
            if slab is None:
                slices = np.flatnonzero(covering == plane)
            else:
                low, high = planes[plane] + slab[0], planes[plane] + slab[1]
                slices = np.flatnonzero((grid.zs >= low) & (grid.zs <= high))
                if not slices.size:
                    slices = np.abs(grid.zs - planes[plane]).argmin(keepdims=True)
            if not slices.size:
                continue
            rings = [ring for (_, ring), at in zip(roi.closed, of) if at == plane]
            filled[slices] |= even_odd(rings, grid.xs, grid.ys)
    return filled


def _hidden(
    roi: RoiContours, grid: _Grid, filled: np.ndarray
) -> list[np.ndarray] | None:
    """The voxels of an ROI's marks that its rows hide, with those of its
    points and open contours, by contour, as flat indices of a surface's
    mask, where they hide any; or else None.

    A mark of a point, of an open contour, or of a closed contour that
    bounds no voxel, such as one that doubles back on itself, is hidden
    where the ROI's closed contours fill its voxel, ``filled`` being their
    region. Any mark is hidden where what its slice shows, its region and
    every mark in it, holds every voxel within two of the mark's in the
    slice, as where a contour retraces a loop within its region, bounds a
    hole narrower than a voxel or one that marks fill, or lies in a plane
    that covers no slice. A mark that is not hidden lies within two voxels
    of the edge of what its slice shows, which the rows draw from the front,
    the back, and the sides. A mark that near the edge is not
    counted as hidden, since a contour in a plane that covers no slice,
    between those of a smooth outline, lies there without hiding anything
    that its neighbours do not show. Near a rounded end, such as the top of
    a head, an outline can shrink by more than two voxels from one such
    plane to the next, so the marks of those planes there are hidden.

    Each contour gives every voxel of its marks if it is a point, an open
    contour, or a closed contour that bounds no voxel, and otherwise those
    of its marks' voxels that are hidden, in the order of
    :meth:`RoiContours.contour_marks`, leaving out any that gives none."""
    step = _step(grid)
    alone = [True] * (len(roi.points) + len(roi.lines)) + [
        not _bounds_any(ring, grid) for _, ring in roi.closed
    ]
    each = [_voxels(marks, grid) for marks in roi.contour_marks(step)]
    every = np.zeros(filled.shape, bool)
    marked = np.zeros(filled.shape, bool)
    for voxels, by_itself in zip(each, alone, strict=True):
        every.flat[voxels] = True
        if by_itself:
            marked.flat[voxels] = True
    buried = _buried(every, filled | every)
    if not ((marked & filled).any() or buried.any()):
        return None
    hidden = [
        voxels if by_itself else voxels[buried.flat[voxels]]
        for voxels, by_itself in zip(each, alone, strict=True)
    ]
    return [voxels for voxels in hidden if voxels.size]


def _layered(
    hidden: Sequence[np.ndarray], shape: tuple[int, ...], most: int | None = None
) -> list[np.ndarray] | None:
    """The hidden marks of each contour, as flat indices of a mask of
    ``shape``, laid out in layers, each as the ascending flat indices of its
    voxels: each contour's in the first layer that holds none of its voxels,
    nor any beside one along its row or its column of voxels, so that a
    layer's rows draw each contour's marks as they would draw them alone. A
    contour's marks the same as an earlier one's are left out. None where it
    would take more than ``most`` layers."""
    layers: list[list[np.ndarray]] = []
    # For each voxel on or beside one in a layer, the bits of those layers,
    # so that memory and time go with the marks, not the grid or the layers.
    near: dict[int, int] = {}
    seen: set[bytes] = set()
    for voxels in hidden:
        key = voxels.tobytes()
        if key in seen:
            continue
        seen.add(key)
        taken = 0
        for voxel in voxels.tolist():
            taken |= near.get(voxel, 0)
        # The lowest layer whose bit is not taken.
        chosen = ((taken + 1) & ~taken).bit_length() - 1
        if chosen == len(layers):
            if most is not None and len(layers) >= most:
                return None
            layers.append([])
        layers[chosen].append(voxels)
        bit = 1 << chosen
        for voxel in _beside(voxels, shape).tolist():
            near[voxel] = near.get(voxel, 0) | bit
    return [np.unique(np.concatenate(each)) for each in layers]


def _beside(voxels: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    """Flat indices of a mask of ``shape``: the voxels, and those beside
    each along its row and its column of voxels."""
    z, y, x = np.unravel_index(voxels, shape)
    found = [voxels]
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        ny, nx = y + dy, x + dx
        within = (ny >= 0) & (ny < shape[1]) & (nx >= 0) & (nx < shape[2])
        found.append(np.ravel_multi_index((z[within], ny[within], nx[within]), shape))
    return np.concatenate(found)


def _buried(marked: np.ndarray, shown: np.ndarray) -> np.ndarray:
    """The voxels of marks around which what each slice shows holds every
    voxel within two in the slice."""
    around = np.zeros((3, 3, 3), bool)
    around[1] = True
    inner = scipy.ndimage.binary_erosion(shown, around, iterations=2, border_value=0)
    return marked & inner


def _step(grid: _Grid) -> float:
    """How far apart marks are taken along a contour: half a voxel."""
    return grid.voxel / 2 if grid.voxel else qc_surfaces.MINIMUM_VOXEL


def _bounds_any(ring: np.ndarray, grid: _Grid) -> bool:
    """Whether a closed contour bounds a voxel of its own."""
    low, high = ring.min(axis=0), ring.max(axis=0)
    xs = grid.xs[(grid.xs >= low[0]) & (grid.xs <= high[0])]
    ys = grid.ys[(grid.ys >= low[1]) & (grid.ys <= high[1])]
    if not (xs.size and ys.size):
        return False
    # Most do in their middle row of voxels, which is quicker to find.
    middle = ys[len(ys) // 2 :][:1]
    return bool(even_odd([ring], xs, middle).any() or even_odd([ring], xs, ys).any())


def _marked(marks: np.ndarray, grid: _Grid) -> np.ndarray:
    """The voxels nearest marks, indexed as a surface's mask."""
    marked = np.zeros((len(grid.zs), len(grid.ys), len(grid.xs)), bool)
    marked.flat[_voxels(marks, grid)] = True
    return marked


def _voxels(marks: np.ndarray, grid: _Grid) -> np.ndarray:
    """The voxels nearest marks, as ascending flat indices of a surface's
    mask, each once."""
    shape = (len(grid.zs), len(grid.ys), len(grid.xs))
    if not len(marks):
        return np.zeros(0, np.intp)
    z = _nearest(grid.zs[::-1], marks[:, 2])
    y = _nearest(grid.ys, marks[:, 1])
    x = _nearest(grid.xs, marks[:, 0])
    within = (z >= 0) & (y >= 0) & (x >= 0)
    flat = np.ravel_multi_index(
        (len(grid.zs) - 1 - z[within], y[within], x[within]), shape
    )
    return np.unique(flat)


def _nearest(coordinates: np.ndarray, wanted: np.ndarray) -> np.ndarray:
    """The index of the ascending coordinate nearest each wanted one, or -1
    where it lies more than half a step beyond the ends."""
    if len(coordinates) == 1:
        return np.zeros(len(wanted), np.intp)
    right = np.clip(np.searchsorted(coordinates, wanted), 1, len(coordinates) - 1)
    left = right - 1
    closer_left = (wanted - coordinates[left]) <= (coordinates[right] - wanted)
    nearest = np.where(closer_left, left, right)
    half = float(np.abs(np.diff(coordinates)).max()) / 2
    beyond = (wanted < coordinates[0] - half) | (wanted > coordinates[-1] + half)
    return np.asarray(np.where(beyond, -1, nearest), np.intp)


def guided(guide: Guide, written: np.ndarray) -> np.ndarray:
    """The guide's views in grey, each with the outline of the written
    region's silhouette in that view drawn over it."""
    tiles = []
    for tile, depths in zip(
        qc_surfaces.views(guide.inside), qc_surfaces.view_depths(written)
    ):
        coloured = np.repeat(tile[..., np.newaxis], 3, axis=2)
        coloured[_edge(depths >= 0)] = _OUTLINE
        tiles.append(coloured)
    return qc_surfaces.side_by_side(tiles)


def _edge(silhouette: np.ndarray) -> np.ndarray:
    """The pixels of a silhouette that are beside one outside it, or at the
    image's edge."""
    padded = np.pad(silhouette, 1)
    interior = (
        padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    )
    edge: np.ndarray = silhouette & ~interior
    return edge


def rgb(image: np.ndarray) -> np.ndarray:
    """An 8-bit grey image as RGB."""
    return np.repeat(image[..., np.newaxis], 3, axis=2)


def stacked(rows: Sequence[np.ndarray], white: Collection[int] = ()) -> np.ndarray:
    """Lay RGB rows out from top to bottom, each padded with black on the
    right to the widest, with a grey gutter between each and the next, or a
    white one above each row whose index is in ``white``, as above each
    further reading's first row of a contour sheet."""
    width = max(row.shape[1] for row in rows)
    gutter = np.empty((GUTTER_PIXELS, width, 3), np.uint8)
    gutter[...] = _GUTTER
    ruled = np.empty((GUTTER_PIXELS, width, 3), np.uint8)
    ruled[...] = _READING_GUTTER
    laid: list[np.ndarray] = []
    for index, row in enumerate(rows):
        padded = np.zeros((row.shape[0], width, 3), np.uint8)
        padded[:, : row.shape[1]] = row
        above = ruled if index in white else gutter
        laid.extend([above, padded] if laid else [padded])
    return np.vstack(laid)
