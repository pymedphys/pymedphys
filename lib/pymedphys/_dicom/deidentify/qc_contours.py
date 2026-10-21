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

"""Renders of RT Structure Set contours for the confidential QC pack's face
review (D-017, D-052).

An RT Structure Set has no pixel data, but its contours can trace the skin
surface, as an outline of the patient's body does, from which a
face-recognition system can match a face as it does from a CT's.
:func:`contour_sheet` renders the region that a structure set's contours,
as the run wrote them, bound, by :func:`~.qc_surfaces.views`, from the five
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
  of the frontal view or of a profile, which look along the axes of the
  voxels and so between them meet every voxel of the region's surface,
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
  cross a surface falsely where they graze it. Where an ROI's closed
  contours fill a voxel of its marks, below, that no closed contour
  bounding a voxel draws, as a box's do a curve within it, the mark leaves
  its region as it was, so those marks, alone, then have rows of their own
  after the ROI's, as its region has, but with no row of cavities.

Each region is sampled to cubic voxels over the extent of what it draws,
with a voxel more on each low side across, 0 to 1 voxel more on each high
side, and up to a voxel more below, so that its edge and its lowest point
are drawn. A frame's united region has voxels of
:data:`~.qc_surfaces.MINIMUM_VOXEL` millimetres, enlarged where needed to
keep each axis within :data:`~.qc_surfaces.MAXIMUM_VOXELS` voxels, as
:mod:`~.qc_surfaces` samples a volume. An ROI alone has the finer of the
voxels that a united region of its own extent would have and those that
keep its extent within :data:`ROI_VOXELS`, but none finer than
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
magnitude than :data:`FARTHEST`, without a Contour Offset Vector or Contour
Slab Thickness, which would place it elsewhere or give it depth, and, for a
closed contour of three or more points, with every point within
:data:`COPLANAR` millimetres of one axial plane, as
:mod:`~.region_defacing` groups contours; and the ROIs of each frame
spanning at most :data:`LONGEST` millimetres along each axis, so that its
voxels stay fine enough to show a face. A closed contour in an oblique,
coronal, or sagittal plane, whose region the slices of voxels would cut
edge on, is not drawn, so a structure set with one is not shown, and nor is
one with a contour of another type, or one that cannot be read.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Mapping, Sequence

from pymedphys._geometry.rasters import even_odd
from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import scipy

from . import qc_surfaces
from .uids import normalise_uid

CLOSED = frozenset({"CLOSED_PLANAR", "CLOSEDPLANAR_XOR"})
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
# frame that a sheet draws: longer than a patient, and drawn in voxels of
# under 8 mm.
LONGEST = 2000.0
ROI_VOXELS = 128
ROI_MINIMUM_VOXEL = 0.5  # millimetres
GUTTER_PIXELS = 8
# The tallest contour sheet that is shown: each row is at most 257 voxels
# tall, so at least about 120 rows, of which an ROI item has one, and more
# where it hides some of its surface behind its own, or its marks. A taller
# one is drawn only until it is too tall, and is not shown, so that its set
# is held rather than shown in an image that a viewer may scale down or
# refuse.
MAXIMUM_SHEET_PIXELS = 32768

# The views whose rays look along an axis of the voxels.
_ALONG = (0, 90, -90)
# As a redaction preview's outline and gutter.
_OUTLINE = (255, 0, 255)
_GUTTER = (128, 128, 128)


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
    """

    closed: tuple[tuple[float, np.ndarray], ...] = ()
    points: np.ndarray = dataclasses.field(
        default_factory=lambda: np.zeros((0, 3), float)
    )
    lines: tuple[np.ndarray, ...] = ()
    frame: str | None = None

    @property
    def empty(self) -> bool:
        """Whether it has no contour."""
        return not self.closed and not len(self.points) and not self.lines

    def coordinates(self) -> np.ndarray:
        """Every point that it draws, as x, y, and z, of shape (m, 3)."""
        rings = [
            np.column_stack([ring, np.full(len(ring), height)])
            for height, ring in self.closed
        ]
        return np.concatenate([*rings, *self.lines, self.points])

    def marks(self, step: float) -> np.ndarray:
        """Its points, and points along each open contour's segments, and
        each closed contour's, its last point joined to its first, at most
        ``step`` apart, as x, y, and z, of shape (m, 3)."""
        sampled = [self.points]
        rings = [
            np.column_stack([ring, np.full(len(ring), height)])
            for height, ring in self.closed
        ]
        for line in [*self.lines, *(np.vstack([ring, ring[:1]]) for ring in rings)]:
            sampled.append(line[-1:])
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
            sampled.append(starts[segment] + fractions[:, np.newaxis] * steps[segment])
        return np.concatenate(sampled)

    def __repr__(self) -> str:
        return "RoiContours()"


@dataclasses.dataclass(frozen=True, repr=False)
class Contours:
    """The contours of an RT Structure Set that a sheet draws.

    Its ``repr`` shows only how many ROIs it has.

    Attributes
    ----------
    rois : tuple of RoiContours
        For each item of the ROI Contour Sequence, in order.
    series : frozenset of str
        The Series Instance UIDs of the image series that it references.
    """

    rois: tuple[RoiContours, ...]
    series: frozenset[str] = frozenset()

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
    try:
        frames = _frames(dataset)
        rois = tuple(
            _roi(item.get("ContourSequence") or [], frames.get(_number(item)))
            for item in dataset.get("ROIContourSequence") or []
        )
    # pydicom raises many types for a value that it cannot read.
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    if any(roi is None for roi in rois):
        return None
    found = Contours(tuple(roi for roi in rois if roi is not None), _series(dataset))
    for frame in found.frames:
        points = np.concatenate(
            [roi.coordinates() for roi in found.rois if roi.frame == frame]
        )
        if np.ptp(points, axis=0).max() > LONGEST:
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


def _roi(contours: pydicom.Sequence, frame: str | None) -> RoiContours | None:
    closed: list[tuple[float, np.ndarray]] = []
    points: list[np.ndarray] = []
    lines: list[np.ndarray] = []
    for contour in contours:
        kind = str(contour.get("ContourGeometricType") or "").strip().upper()
        if kind not in CLOSED | OPEN | {POINT}:
            return None
        for keyword in ("ContourOffsetVector", "ContourSlabThickness"):
            if keyword in contour and contour[keyword].value not in (None, "", []):
                return None
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
        found = np.asarray(values).reshape(-1, 3)
        if not (np.abs(found) <= FARTHEST).all():
            return None
        if kind in OPEN and len(found) > 1:
            lines.append(found)
            continue
        if kind == POINT or len(found) < 3:
            points.append(found)
            continue
        low, high = float(found[:, 2].min()), float(found[:, 2].max())
        if not high - low <= 2 * COPLANAR:
            return None
        closed.append((float(found[:, 2].mean()), found[:, :2]))
    return RoiContours(
        tuple(closed),
        np.concatenate(points) if points else np.zeros((0, 3), float),
        tuple(lines),
        frame,
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
        taller than ``tallest``, which is drawn only until it is.
    """
    guides = {} if guides is None else guides
    if contours.empty:
        raise ValueError("a contour sheet needs a contour")
    # Each ROI's planes, so that the planes of one ROI never empty another's
    # slices.
    if tallest is not None and _least_height(contours, guides) > tallest:
        return None
    planes = [_planes(roi) for roi in contours.rois]
    rows: list[np.ndarray] = []
    height = -GUTTER_PIXELS

    def fits(more: Sequence[np.ndarray]) -> bool:
        nonlocal height
        rows.extend(more)
        height += sum(row.shape[0] + GUTTER_PIXELS for row in more)
        return tallest is None or height <= tallest

    for frame in contours.frames:
        chosen = [i for i, roi in enumerate(contours.rois) if roi.frame == frame]
        rois = [contours.rois[i] for i in chosen]
        grid = _grid(rois, _united_voxel)
        shown = [planes[i] for i in chosen]
        if not fits([_rgb(_views(_mask(rois, grid, shown)))]):
            return None
        guide = guides.get(frame)
        if guide is not None and not fits(
            [_guided(guide, _mask(rois, _of(guide), shown))]
        ):
            return None
    # An ROI the same as an earlier one, as a copied item is, is rendered
    # once, though each has its rows.
    rendered: dict[bytes, list[np.ndarray]] = {}
    for roi, own in zip(contours.rois, planes):
        if roi.empty:
            if not fits([np.zeros((GUTTER_PIXELS, 1, 3), np.uint8)]):
                return None
            continue
        key = _key(roi)
        if key not in rendered:
            grid = _grid([roi], _roi_voxel)
            filled = _filled(roi, grid, own)
            hidden = _hidden(roi, grid, filled)
            rendered[key] = _roi_rows(filled | _marked(roi.marks(_step(grid)), grid))
            if hidden is not None:
                rendered[key] += _roi_rows(hidden, cavities=False)
        if not fits(rendered[key]):
            return None
    return _stacked(rows)


def _least_height(contours: Contours, guides: Mapping[str | None, Guide]) -> int:
    """The height, in pixels, of a sheet without the rows of any ROI's
    cavities, of the surfaces that it hides behind its own, or of the marks
    that it hides, found without drawing it."""
    heights = []
    for frame in contours.frames:
        rois = [roi for roi in contours.rois if roi.frame == frame]
        heights.append(len(_grid(rois, _united_voxel).zs))
        guide = guides.get(frame)
        if guide is not None:
            heights.append(guide.inside.shape[0])
    heights.extend(
        GUTTER_PIXELS if roi.empty else len(_grid([roi], _roi_voxel).zs)
        for roi in contours.rois
    )
    return sum(heights) + GUTTER_PIXELS * (len(heights) - 1)


def _roi_rows(inside: np.ndarray, cavities: bool = True) -> list[np.ndarray]:
    """An ROI's rows, or its hidden marks', as the module describes, from
    their voxels; the marks have no row of cavities."""
    rows = [_rgb(_views(inside))]
    # The rays of the views that look along an axis of the voxels meet every
    # voxel of its surface, and cross the surface more than twice only where
    # it hides some of its surface behind its own; the oblique views' rays,
    # which step between voxels, cross a surface falsely where they graze it.
    if max(_most_crossings(inside, axis) for axis in (1, 2)) <= 2:
        return rows
    if cavities:
        # Each slice's cavities: what its region encloses, but does not hold.
        within = np.zeros((3, 3, 3), bool)
        within[1] = [[False, True, False], [True, True, True], [False, True, False]]
        enclosed = scipy.ndimage.binary_fill_holes(inside, within) & ~inside
        if enclosed.any():
            rows.append(_rgb(_views(enclosed)))
    along = dict(zip(_ALONG, qc_surfaces.view_crossings(inside, _ALONG)))
    none = np.full(along[0].shape[1:], -1)
    for crossing in range(1, max(len(each) for each in along.values())):
        tiles = []
        for view in qc_surfaces.VIEWS:
            each = along.get(view)
            tiles.append(
                none if each is None or crossing >= len(each) else each[crossing]
            )
        rows.append(_rgb(_tiles(tiles)))
    return rows


def _most_crossings(inside: np.ndarray, axis: int) -> int:
    """The most times that a line of voxels along an axis crosses in or out
    of the region."""
    padding = [(0, 0)] * inside.ndim
    padding[axis] = (1, 1)
    changes = np.diff(np.pad(inside, padding), axis=axis)
    return int(changes.sum(axis=axis).max(initial=0))


def _tiles(depths: Sequence[np.ndarray]) -> np.ndarray:
    return qc_surfaces.side_by_side([qc_surfaces.shaded(each) for each in depths])


def _key(roi: RoiContours) -> bytes:
    """What an ROI draws, and in which frame, as bytes."""
    parts = [str(roi.frame).encode("utf-8", "surrogateescape"), b"|"]
    for height, ring in roi.closed:
        parts.extend([b"c", np.float64(height).tobytes(), _sized(ring)])
    parts.extend([b"p", _sized(roi.points)])
    for line in roi.lines:
        parts.extend([b"l", _sized(line)])
    return b"".join(parts)


def _sized(values: np.ndarray) -> bytes:
    data = np.ascontiguousarray(values, np.float64)
    return np.int64(data.size).tobytes() + data.tobytes()


def _views(inside: np.ndarray) -> np.ndarray:
    return qc_surfaces.side_by_side(qc_surfaces.views(inside))


def _of(guide: Guide) -> _Grid:
    return _Grid(guide.zs, guide.ys, guide.xs)


def _united_voxel(extent: float) -> float:
    """The side of a united region's voxels, as a volume's surface render
    samples one of that extent."""
    return max(qc_surfaces.MINIMUM_VOXEL, extent / (qc_surfaces.MAXIMUM_VOXELS - 1))


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


def _filled(roi: RoiContours, grid: _Grid, planes: np.ndarray) -> np.ndarray:
    """The voxels that an ROI's closed contours fill, indexed as a surface's
    mask, its slices of voxels covered by its ``planes``."""
    filled = np.zeros((len(grid.zs), len(grid.ys), len(grid.xs)), bool)
    if roi.closed:
        covering = _covering(planes, grid.zs, grid.voxel)
        heights = np.array([height for height, _ in roi.closed])
        # Each contour's plane: the nearest, within which it lies.
        of = np.abs(heights[:, np.newaxis] - planes[np.newaxis, :]).argmin(axis=1)
        for plane in np.unique(of):
            slices = np.flatnonzero(covering == plane)
            if not slices.size:
                continue
            rings = [ring for (_, ring), at in zip(roi.closed, of) if at == plane]
            filled[slices] |= even_odd(rings, grid.xs, grid.ys)
    return filled


def _hidden(roi: RoiContours, grid: _Grid, filled: np.ndarray) -> np.ndarray | None:
    """Where a voxel of an ROI's marks that no closed contour bounding a
    voxel draws is one that its closed contours fill, which the mark then
    leaves as it was, the voxels of those marks alone, indexed as a
    surface's mask; or else None."""
    # The marks of its points, of its open contours, and of its closed
    # contours that bound no voxel, such as one that doubles back on itself;
    # the others' marks trace the edges of what they fill.
    alone = RoiContours(
        closed=tuple(each for each in roi.closed if not _bounds_any(each[1], grid)),
        points=roi.points,
        lines=roi.lines,
    )
    if not (alone.closed or alone.points.size or alone.lines):
        return None
    marked = _marked(alone.marks(_step(grid)), grid)
    return marked if (marked & filled).any() else None


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
    if len(marks):
        z = _nearest(grid.zs[::-1], marks[:, 2])
        y = _nearest(grid.ys, marks[:, 1])
        x = _nearest(grid.xs, marks[:, 0])
        within = (z >= 0) & (y >= 0) & (x >= 0)
        marked[len(grid.zs) - 1 - z[within], y[within], x[within]] = True
    return marked


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


def _guided(guide: Guide, written: np.ndarray) -> np.ndarray:
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


def _rgb(image: np.ndarray) -> np.ndarray:
    return np.repeat(image[..., np.newaxis], 3, axis=2)


def _stacked(rows: Sequence[np.ndarray]) -> np.ndarray:
    """Lay RGB rows out from top to bottom, each padded with black on the
    right to the widest, with a grey gutter between each and the next."""
    width = max(row.shape[1] for row in rows)
    gutter = np.empty((GUTTER_PIXELS, width, 3), np.uint8)
    gutter[...] = _GUTTER
    laid: list[np.ndarray] = []
    for row in rows:
        padded = np.zeros((row.shape[0], width, 3), np.uint8)
        padded[:, : row.shape[1]] = row
        laid.extend([gutter, padded] if laid else [padded])
    return np.vstack(laid)
