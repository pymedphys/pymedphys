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

"""Renders of a Segmentation's segments for the confidential QC pack's face
review (D-017).

A Segmentation's frames are masks of its segments, and a segment of the
skin or body traces the patient's surface, as an RT Structure Set's outline
does, from which a face-recognition system can match a face. Its label or
code need not say that it is one, so :func:`segment_sheet` renders every
segment, as the run wrote it, by :func:`~.qc_surfaces.views`, from the six
directions of :data:`~.qc_surfaces.VIEWS`, so that a reviewer can see a
face where a segment traces one. The sheet's rows, from the top, separated
by grey rows of :data:`~.qc_contours.GUTTER_PIXELS`, are:

- every segment united; then, where the run wrote a volume in the
  Segmentation's Frame of Reference, the surface render of that volume, in
  grey, with the edge of each view's silhouette of the united segments
  drawn over it in magenta, as a contour sheet draws a frame's ROIs; then
- for each item of the Segment Sequence (0062,0002), in order, its segment
  alone, since the union hides a segment wholly inside another, followed by
  the rows of :func:`~.qc_surfaces.hidden_rows` where it hides some of its
  surface behind its own, as one with a cavity does; or a black row of
  :data:`~.qc_contours.GUTTER_PIXELS` for a segment that no pixel holds.

Each frame is placed in the patient's coordinates by its Plane Position
(Patient), Plane Orientation (Patient), and Pixel Measures functional
groups, per frame or shared, and sampled to cubic voxels of
:data:`~.qc_surfaces.MINIMUM_VOXEL` millimetres, or of its smallest
spacing where that is larger, as a volume's surface render is sampled, so
that a long Segmentation's rows are taller rather than coarser. Within a
frame, the mask is sampled along its rows' axis and then its columns', each
voxel along an axis holding every pixel nearest it and the pixel nearest it,
so that no pixel of a segment is left out where pixels are finer than the
voxels, and no voxel is missed where they are coarser, even where they are
finer along one axis and coarser along the other. The frames' planes lie
on a grid of their Spacing Between Slices, or of their Slice Thickness
where they give no spacing, and each slice of voxels is covered by the
plane whose cell of that grid holds it, from half a step below the plane
to just under half a step above, where a frame of the Segmentation is in
that plane; each plane is also taken into the slice of voxels nearest it,
so that every frame is drawn where planes are closer than the voxels. A
segment that has no frame in a plane is empty there, and so is a slice in
the cell of a plane that no frame is in, since a writer may leave out the
empty frames of a segment, or of every segment, and the sheet is then the
same as with them written.

In a BINARY Segmentation a pixel of 1 is in the segment that its frame's
Segment Identification functional group names. In a LABELMAP one a pixel
is in the segment whose Segment Number it holds, and one that Pixel Padding
Value and Pixel Padding Range Limit name is background (PS3.3 Section
C.8.20.2.4). A sheet is drawn only of a Segmentation that it can show
(:func:`segments_of`): of Segmentation Type BINARY or LABELMAP; with a
Segment Sequence of distinct Segment Numbers; with every frame placed, in
one orientation whose rows and columns lie along the patient's axes, of one
Pixel Spacing, and none farther than :data:`~.qc_contours.FARTHEST`
millimetres; where its frames lie in two planes or more, with a Slice
Thickness or Spacing Between Slices, one for every frame, and its planes
on the grid of that step, within 0.01 millimetres, since
otherwise the empty frames that a writer left out cannot be placed, nor
told from planes between those of the grid; of one time point and one
stack, by the Dimension Organization Type (0020,9311) and each frame's
Temporal Position Index and Stack ID, and with no segment in one plane in
two frames, as at two time points, since the union of two could hide the
surface of either, which also refuses one plane's tiles of a segment,
though they may not overlap; and spanning at most
:data:`~.qc_surfaces.LONGEST` millimetres along each axis and :data:`~.qc_surfaces.WIDEST` across, from
left to right and from front to back, as a contour sheet's frame does; and
whose frames' pixels each lie in a segment that the Segment Sequence
describes, or are background. A FRACTIONAL Segmentation, whose segments
are probabilities or occupancies, is not drawn, since a face that a high
fraction traces can lie within a low fraction's region, and no one
threshold would show it; nor is a sheet taller than ``tallest``, which is
drawn only until it is.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import qc_contours, qc_surfaces
from .pixel_risk import SEGMENTATION_SOP_CLASSES
from .uids import normalise_uid

# The Segmentation Types whose segments a sheet draws.
SHOWN_TYPES = frozenset({"BINARY", "LABELMAP"})
# As qc_previews: an axis lies along a patient axis when its other two
# direction cosines are each at most this.
_ALIGNMENT_TOLERANCE = 1e-4
_ORIENTATION_TOLERANCE = 1e-4
# In millimetres, how far apart along the normal frames may lie and still
# be in one plane, as the slices of a volume are told apart.
_COPLANAR = 0.01
# The patient's z, y, and x axes, by the axes of a mask that views take:
# from superior, from anterior, and from the patient's right.
_ARRAY_AXIS = {2: 0, 1: 1, 0: 2}


@dataclasses.dataclass(frozen=True, repr=False)
class Segments:
    """What a sheet needs of a Segmentation's frames; its pixels are decoded
    from the file one frame at a time.

    Its ``repr`` shows only how many segments and frames it has.

    Attributes
    ----------
    numbers : tuple of int
        The Segment Number of each item of the Segment Sequence, in order.
    labelmap : bool
        Whether its Segmentation Type is LABELMAP, whose pixels hold Segment
        Numbers, rather than BINARY, whose frames each hold one segment.
    axes : tuple of int
        The patient axis, 0 for x, 1 for y, and 2 for z, of the frames'
        normal, of increasing row index, and of increasing column index.
    signs : tuple of float
        Whether increasing row index, then column index, runs towards higher
        or lower coordinates along its patient axis, as 1 or -1.
    spacing : tuple of float
        Between rows, then between columns, in millimetres.
    shape : tuple of int
        Rows, then columns.
    origins : tuple of tuple of float
        Each frame's Image Position (Patient), in millimetres.
    segments : tuple of int or None
        Each frame's Referenced Segment Number, for a BINARY Segmentation;
        None for each frame of a LABELMAP one.
    frame : str or None
        Its Frame of Reference UID.
    series : frozenset of str
        The Series Instance UIDs that its Referenced Series Sequence names.
    step : float or None
        The distance between the centres of adjacent planes of its frames'
        grid, in millimetres: their Spacing Between Slices, or their Slice
        Thickness where their Pixel Measures give no spacing.
    """

    numbers: tuple[int, ...]
    labelmap: bool
    axes: tuple[int, int, int]
    signs: tuple[float, float]
    spacing: tuple[float, float]
    shape: tuple[int, int]
    origins: tuple[tuple[float, float, float], ...]
    segments: tuple[int | None, ...]
    frame: str | None = None
    series: frozenset[str] = frozenset()
    step: float | None = None

    def __repr__(self) -> str:
        return f"Segments(segments={len(self.numbers)}, frames={len(self.origins)})"


def is_segmentation(dataset: pydicom.Dataset) -> bool:
    """Whether an instance is a Segmentation, whose frames only a QC pack's
    segments sheet shows as they could show a face (D-017).

    Its SOP Class UID being Segmentation Storage or Label Map Segmentation
    Storage, or its Modality being SEG, makes it one, so that a file of
    either alone is never counted as shown by another preview.
    """
    try:
        sop_class = normalise_uid(str(dataset.get("SOPClassUID") or ""))
    # Whatever reading the value raises, it names no class.
    except Exception:  # pylint: disable = broad-exception-caught
        sop_class = ""
    try:
        modality = str(dataset.get("Modality") or "").strip(" \0").upper()
    except Exception:  # pylint: disable = broad-exception-caught
        modality = ""
    return sop_class in SEGMENTATION_SOP_CLASSES or modality == "SEG"


def segments_of(dataset: pydicom.Dataset) -> Segments | None:
    """Return what a sheet needs of a Segmentation, or None where a sheet
    cannot show it, as the module describes."""
    try:
        return _segments(dataset)
    # Whatever reading the data set raises, it is not shown.
    except Exception:  # pylint: disable = broad-exception-caught
        return None


def _segments(  # pylint: disable = too-many-return-statements
    dataset: pydicom.Dataset,
) -> Segments | None:
    kind = str(dataset.get("SegmentationType") or "").strip().upper()
    if kind not in SHOWN_TYPES:
        return None
    organisation = str(dataset.get("DimensionOrganizationType") or "")
    if organisation.strip().upper() == "3D_TEMPORAL":
        return None
    numbers = tuple(int(item.SegmentNumber) for item in dataset.SegmentSequence)
    if not numbers or len(set(numbers)) != len(numbers):
        return None
    frames = int(dataset.get("NumberOfFrames") or 1)
    rows, columns = int(dataset.Rows), int(dataset.Columns)
    if frames < 1 or rows < 1 or columns < 1:
        return None
    shared = list(dataset.get("SharedFunctionalGroupsSequence") or [])
    per_frame = list(dataset.get("PerFrameFunctionalGroupsSequence") or [])
    if len(shared) > 1 or (per_frame and len(per_frame) != frames):
        return None
    labelmap = kind == "LABELMAP"
    origins = []
    segments: list[int | None] = []
    orientations = []
    spacings = []
    steps = []
    stacks = set()
    for index in range(frames):
        groups = [per_frame[index]] if per_frame else []
        groups.extend(shared)
        origin = _floats(
            _macro(groups, "PlanePositionSequence"), "ImagePositionPatient", 3
        )
        orientation = _floats(
            _macro(groups, "PlaneOrientationSequence"), "ImageOrientationPatient", 6
        )
        measures = _macro(groups, "PixelMeasuresSequence")
        spacing = _floats(measures, "PixelSpacing", 2)
        if origin is None or orientation is None or spacing is None:
            return None
        if labelmap:
            segments.append(None)
        else:
            identified = _macro(groups, "SegmentIdentificationSequence")
            number = None if identified is None else identified.ReferencedSegmentNumber
            if number is None or int(number) not in numbers:
                return None
            segments.append(int(number))
        origins.append(origin)
        orientations.append(orientation)
        spacings.append(spacing)
        steps.append(_step(measures))
        content = _macro(groups, "FrameContentSequence")
        if content is not None:
            stacks.add(
                tuple(
                    str(content.get(keyword) or "").strip()
                    for keyword in ("TemporalPositionIndex", "StackID")
                )
            )
    # Frames of two time points or stacks may each trace a surface that the
    # other, drawn with it, would hide.
    if len(stacks) > 1:
        return None
    first, spacing = orientations[0], spacings[0]
    if (
        min(spacing) <= 0
        or any(
            not np.allclose(each, first, atol=_ORIENTATION_TOLERANCE)
            for each in orientations
        )
        or any(not np.allclose(each, spacing) for each in spacings)
        or any(each != steps[0] for each in steps)
        or steps[0] == 0.0
    ):
        return None
    row, column = np.array(first[:3]), np.array(first[3:])
    axes = []
    for direction in (np.cross(row, column), column, row):
        magnitudes = np.abs(direction)
        axis = int(np.argmax(magnitudes))
        if np.delete(magnitudes, axis).max() > _ALIGNMENT_TOLERANCE:
            return None
        axes.append(axis)
    if len(set(axes)) != 3:
        return None
    if np.abs(np.array(origins)).max() > qc_contours.FARTHEST:
        return None
    found = Segments(
        numbers=numbers,
        labelmap=labelmap,
        axes=(axes[0], axes[1], axes[2]),
        signs=(float(np.sign(column[axes[1]])), float(np.sign(row[axes[2]]))),
        spacing=(spacing[0], spacing[1]),
        shape=(rows, columns),
        origins=tuple(origins),
        segments=tuple(segments),
        frame=_uid(dataset.get("FrameOfReferenceUID")),
        series=frozenset(
            uid
            for item in dataset.get("ReferencedSeriesSequence") or []
            if (uid := _uid(item.get("SeriesInstanceUID"))) is not None
        ),
        step=steps[0],
    )
    low, high = _extent(found)
    spans = high - low
    if spans[2] > qc_surfaces.LONGEST or max(spans[:2]) > qc_surfaces.WIDEST:
        return None
    # A segment in one plane twice, as at two time points, would be drawn as
    # their union, which can hide the surface of either.
    planes = _planes(found)
    held = [
        (segment, int(np.abs(planes - origin[found.axes[0]]).argmin()))
        for segment, origin in zip(found.segments, found.origins)
    ]
    if len(set(held)) != len(held):
        return None
    if len(planes) < 2:
        return found
    # Without a step, frames in two planes or more leave unknown where a
    # writer left out empty frames between them; and frames off the grid
    # of their step, as of two stacks or of a step that is not the planes',
    # cannot be told from planes between those of the grid.
    if found.step is None:
        return None
    cells = np.rint((planes - planes[0]) / found.step)
    if np.abs(planes - planes[0] - cells * found.step).max() > _COPLANAR or len(
        np.unique(cells)
    ) != len(cells):
        return None
    return found


def _step(measures: pydicom.Dataset | None) -> float | None:
    """A Pixel Measures item's Spacing Between Slices, or its Slice Thickness
    where it gives no spacing; None where it gives neither, or 0.0 where
    either is not a finite number above 0."""
    steps = {}
    for keyword in ("SpacingBetweenSlices", "SliceThickness"):
        value = None if measures is None else measures.get(keyword)
        if value is None or value == "":
            continue
        try:
            step = float(value)
        except (TypeError, ValueError):
            return 0.0
        if not (math.isfinite(step) and step > 0):
            return 0.0
        steps[keyword] = step
    return next(iter(steps.values()), None)


def _macro(groups: Sequence[pydicom.Dataset], keyword: str) -> pydicom.Dataset | None:
    """A functional group macro's one item, from the first of ``groups``,
    per frame then shared, that holds it."""
    for group in groups:
        if keyword in group:
            items = list(group[keyword].value or [])
            return items[0] if len(items) == 1 else None
    return None


def _floats(
    item: pydicom.Dataset | None, keyword: str, count: int
) -> tuple[float, ...] | None:
    if item is None or keyword not in item:
        return None
    values = tuple(float(value) for value in item[keyword].value)
    if len(values) != count or not all(math.isfinite(value) for value in values):
        return None
    return values


def _uid(value: object) -> str | None:
    uid = normalise_uid(str(value or ""))
    return uid or None


def _extent(segments: Segments) -> tuple[np.ndarray, np.ndarray]:
    """The lowest and highest coordinate along each patient axis of the
    centre of any pixel of any frame."""
    origins = np.array(segments.origins)
    low, high = origins.min(axis=0), origins.max(axis=0)
    for axis, sign, spacing, count in zip(
        segments.axes[1:], segments.signs, segments.spacing, segments.shape
    ):
        reach = sign * spacing * (count - 1)
        low[axis] += min(reach, 0.0)
        high[axis] += max(reach, 0.0)
    return low, high


@dataclasses.dataclass(frozen=True)
class _Lattice:
    """The patient coordinates of voxels along each axis: x and y ascending,
    z descending, so that a mask of them is indexed as views take one."""

    xs: np.ndarray
    ys: np.ndarray
    zs: np.ndarray

    def along(self, axis: int) -> np.ndarray:
        return (self.xs, self.ys, self.zs)[axis]

    @property
    def shape(self) -> tuple[int, int, int]:
        return (len(self.zs), len(self.ys), len(self.xs))

    @property
    def voxel(self) -> float:
        steps = [
            float(abs(axis[1] - axis[0]))
            for axis in (self.zs, self.ys, self.xs)
            if len(axis) > 1
        ]
        return max(steps, default=0.0)


def _own_lattice(segments: Segments) -> _Lattice:
    """Cubic voxels over the frames' pixels, with a voxel more on each low
    side and 0 to 1 more on each high side, as the division falls."""
    low, high = _extent(segments)
    planes = _planes(segments)
    by_axis: dict[int, np.ndarray] = {segments.axes[0]: planes}
    for axis, spacing, count in zip(
        segments.axes[1:], segments.spacing, segments.shape
    ):
        by_axis[axis] = np.arange(count) * spacing
    voxel = qc_surfaces.voxel_side([by_axis[axis] for axis in range(3)])

    def steps(index: int) -> np.ndarray:
        count = math.floor((high[index] - low[index]) / voxel + 1e-6) + 3
        return np.arange(count) * voxel

    return _Lattice(
        low[0] - voxel + steps(0), low[1] - voxel + steps(1), high[2] + voxel - steps(2)
    )


def _planes(segments: Segments) -> np.ndarray:
    """The positions along the normal of the planes of the frames, ascending,
    those within :data:`_COPLANAR` of the next taken as one."""
    positions = np.sort([origin[segments.axes[0]] for origin in segments.origins])
    breaks = np.flatnonzero(np.diff(positions) > _COPLANAR) + 1
    return np.array([group.mean() for group in np.split(positions, breaks)])


def _covering(planes: np.ndarray, coordinates: np.ndarray, step: float) -> np.ndarray:
    """For each coordinate along the normal, the index of the plane whose
    cell holds it, or -1 for none.

    The planes, ascending, lie on a grid ``step`` apart through the first,
    and each cell spans from half a step below its plane to just under half
    a step above, so that every coordinate lies in one cell of the grid,
    whichever of its planes a writer left out.
    """
    if not planes.size:
        return np.full(len(coordinates), -1, np.intp)
    cells = np.rint((planes - planes[0]) / step).astype(np.intp)
    held = np.floor((coordinates - planes[0]) / step + 0.5).astype(np.intp)
    index = np.clip(np.searchsorted(cells, held), 0, len(cells) - 1)
    return np.asarray(np.where(cells[index] == held, index, -1), np.intp)


def _nearest(coordinates: np.ndarray, wanted: np.ndarray, half: float) -> np.ndarray:
    """The index of the monotonic coordinate nearest each wanted one, or -1
    where it lies more than ``half`` beyond the ends."""
    descending = len(coordinates) > 1 and coordinates[0] > coordinates[-1]
    ascending = coordinates[::-1] if descending else coordinates
    if len(ascending) == 1:
        nearest = np.zeros(len(wanted), np.intp)
    else:
        right = np.clip(np.searchsorted(ascending, wanted), 1, len(ascending) - 1)
        left = right - 1
        closer_left = (wanted - ascending[left]) <= (ascending[right] - wanted)
        nearest = np.where(closer_left, left, right)
    beyond = (wanted < ascending[0] - half) | (wanted > ascending[-1] + half)
    if descending:
        nearest = len(ascending) - 1 - nearest
    return np.asarray(np.where(beyond, -1, nearest), np.intp)


class _Placement:
    """Where a Segmentation's frames fall among a lattice's voxels."""

    def __init__(self, segments: Segments, lattice: _Lattice) -> None:
        self._segments = segments
        self.lattice = lattice
        voxel = lattice.voxel or min(segments.spacing)
        planes = _planes(segments)
        normal = lattice.along(segments.axes[0])
        # Each plane's slices of voxels: those it covers, and the nearest.
        covered = _covering(planes, normal, segments.step or voxel)
        nearest = _nearest(normal, planes, voxel / 2)
        self._slices = [
            np.union1d(np.flatnonzero(covered == index), nearest[index : index + 1])
            for index in range(len(planes))
        ]
        self._slices = [each[each >= 0] for each in self._slices]
        self._planes = planes
        self._maps: dict[tuple[float, float], tuple] = {}

    def slices(self, origin: Sequence[float]) -> np.ndarray:
        """The voxels along the normal that a frame's plane is drawn in."""
        position = origin[self._segments.axes[0]]
        plane = int(np.abs(self._planes - position).argmin())
        return self._slices[plane]

    def pooled(self, origin: Sequence[float], mask: np.ndarray) -> np.ndarray:
        """A frame's mask in the voxels across its plane, indexed along its
        rows' patient axis and then its columns': along each, each voxel
        holds every pixel nearest it, and the pixel nearest it."""
        key = (origin[self._segments.axes[1]], origin[self._segments.axes[2]])
        if key not in self._maps:
            self._maps[key] = tuple(self._map(origin, part) for part in range(2))
        (to_r, from_r), (to_c, from_c) = self._maps[key]
        # Along each axis in turn, so that a pixel kept along one axis also
        # takes, along the other, the voxels nearest it.
        return _along(_along(mask, to_r, from_r, 0), to_c, from_c, 1)

    def _map(self, origin: Sequence[float], part: int) -> tuple[np.ndarray, np.ndarray]:
        """For a frame's rows (0) or columns (1): the voxel nearest each, and
        the one nearest each voxel."""
        segments = self._segments
        axis = segments.axes[1 + part]
        spacing = segments.spacing[part]
        pixels = origin[axis] + segments.signs[part] * spacing * np.arange(
            segments.shape[part]
        )
        voxels = self.lattice.along(axis)
        voxel = self.lattice.voxel or spacing
        return _nearest(voxels, pixels, voxel / 2), _nearest(
            pixels, voxels, spacing / 2
        )


def _along(mask: np.ndarray, to: np.ndarray, back: np.ndarray, axis: int) -> np.ndarray:
    """A mask resampled along ``axis`` to voxels: each voxel holds every
    pixel that ``to`` takes into it, and the pixel that ``back`` gives it,
    -1 for none."""
    pooled = _reduced(mask, to, len(back), axis)
    kept = np.flatnonzero(back >= 0)
    target: list = [slice(None)] * mask.ndim
    target[axis] = kept
    pooled[tuple(target)] |= np.take(mask, back[kept], axis=axis)
    return pooled


def _reduced(mask: np.ndarray, to: np.ndarray, count: int, axis: int) -> np.ndarray:
    """The OR of the mask's pixels along ``axis`` that fall in each of
    ``count`` voxels, by the voxel ``to`` gives each, -1 for none."""
    shape = list(mask.shape)
    shape[axis] = count
    pooled = np.zeros(shape, bool)
    kept = np.flatnonzero(to >= 0)
    if not kept.size:
        return pooled
    order = kept[np.argsort(to[kept], kind="stable")]
    voxels = to[order]
    starts = np.flatnonzero(np.concatenate([[True], np.diff(voxels) != 0]))
    reduced = np.logical_or.reduceat(np.take(mask, order, axis=axis), starts, axis=axis)
    target: list = [slice(None)] * mask.ndim
    target[axis] = voxels[starts]
    pooled[tuple(target)] = reduced
    return pooled


def _put(
    inside: np.ndarray,
    start: Sequence[int],
    axes: tuple[int, int, int],
    slices: np.ndarray,
    corner: tuple[int, int],
    plane: np.ndarray,
) -> None:
    """Add a pooled mask, of a frame or part of one, to a mask of voxels.

    ``inside`` is indexed as views take it, and its first voxel is at
    ``start`` among the lattice's; ``slices`` are the lattice's voxels along
    the frames' normal that the plane is drawn in, and ``corner`` the
    lattice's voxel along the rows' and then the columns' patient axis of
    the plane's first.
    """
    normal, down, across = (_ARRAY_AXIS[axis] for axis in axes)
    index: list[np.ndarray] = [np.zeros(0, np.intp)] * 3
    index[normal] = slices - start[normal]
    index[down] = np.arange(plane.shape[0]) + corner[0] - start[down]
    index[across] = np.arange(plane.shape[1]) + corner[1] - start[across]
    block = np.transpose(plane[np.newaxis], np.argsort([normal, down, across]))
    where = np.ix_(*index)
    inside[where] = inside[where] | block


# A segment's part in one frame: the lattice's voxels along the normal that
# it is drawn in, the voxel of its first across the plane, and its pooled
# mask, cropped to what it holds.
type _Piece = tuple[np.ndarray, tuple[int, int], np.ndarray]


def segment_sheet(  # pylint: disable = too-many-return-statements
    segments: Segments,
    frames: Iterable[np.ndarray],
    guide: qc_contours.Guide | None = None,
    tallest: int | None = None,
) -> np.ndarray | None:
    """Return the sheet of a Segmentation's segments, as the module
    describes, in RGB.

    Parameters
    ----------
    segments : Segments
        As :func:`segments_of` gives them of the file written.
    frames : iterable of numpy.ndarray
        Its frames as decoded, in order, each of shape (rows, columns), with
        its padding as NaN, as :mod:`~.qc_previews` decodes them; each is
        read once, and none is kept.
    guide : ~pymedphys._dicom.deidentify.qc_contours.Guide, optional
        The volume that the sheet is drawn with, in its Frame of Reference.
    tallest : int, optional
        The most pixels that the sheet may be tall.

    Returns
    -------
    numpy.ndarray or None
        uint8, of shape (rows, columns, 3); or None where ``frames`` are
        fewer or more than its frames, where a pixel lies in no segment
        that its Segment Sequence describes and is not background, or where
        the sheet would be taller than ``tallest``, which is drawn only
        until it is.
    """
    own = _Placement(segments, _own_lattice(segments))
    placed = None
    if guide is not None:
        placed = _Placement(segments, _Lattice(guide.xs, guide.ys, guide.zs))
    on_guide = np.zeros((0, 0, 0) if guide is None else guide.inside.shape, bool)
    pieces: dict[int, list[_Piece]] = {number: [] for number in segments.numbers}
    count = 0
    for count, values in enumerate(frames, start=1):
        if count > len(segments.origins):
            return None
        origin = segments.origins[count - 1]
        masks = _masks(segments, segments.segments[count - 1], values)
        if masks is None:
            return None
        for number, mask in masks.items():
            pooled = own.pooled(origin, mask)
            rows = np.flatnonzero(pooled.any(axis=1))
            columns = np.flatnonzero(pooled.any(axis=0))
            if not rows.size:
                continue
            crop = pooled[rows[0] : rows[-1] + 1, columns[0] : columns[-1] + 1]
            pieces[number].append(
                (own.slices(origin), (int(rows[0]), int(columns[0])), crop.copy())
            )
            if placed is not None:
                _put(
                    on_guide,
                    (0, 0, 0),
                    segments.axes,
                    placed.slices(origin),
                    (0, 0),
                    placed.pooled(origin, mask),
                )
    if count != len(segments.origins):
        return None
    shape = own.lattice.shape
    everything = [piece for each in pieces.values() for piece in each]
    union = _box(everything, segments.axes, shape) or ((0, 0, 0), shape)
    boxes = [_box(pieces[number], segments.axes, shape) for number in segments.numbers]
    heights = [box[1][0] if box else qc_contours.GUTTER_PIXELS for box in boxes]
    least = [union[1][0], *([] if guide is None else [guide.inside.shape[0]]), *heights]
    if tallest is not None and _height(least) - qc_contours.GUTTER_PIXELS > tallest:
        return None
    rows: list[np.ndarray] = []
    height = -qc_contours.GUTTER_PIXELS

    def fits(more: Sequence[np.ndarray]) -> bool:
        nonlocal height
        rows.extend(more)
        height += _height([row.shape[0] for row in more])
        return tallest is None or height <= tallest

    if not fits([_views(_region(everything, segments.axes, union))]):
        return None
    if guide is not None and not fits([qc_contours.guided(guide, on_guide)]):
        return None
    for index, (number, box) in enumerate(zip(segments.numbers, boxes)):
        if box is None:
            if not fits([np.zeros((qc_contours.GUTTER_PIXELS, 1, 3), np.uint8)]):
                return None
            continue
        inside = _region(pieces[number], segments.axes, box)
        own_row = _views(inside)
        room = None
        if tallest is not None:
            # What the segments after it need at least is kept for them.
            room = tallest - height - _height([own_row.shape[0], *heights[index + 1 :]])
        hidden = qc_surfaces.hidden_rows(inside, room)
        if hidden is None or not fits(
            [own_row, *(qc_contours.rgb(row) for row in hidden)]
        ):
            return None
    return qc_contours.stacked(rows)


def _masks(
    segments: Segments, number: int | None, values: np.ndarray
) -> dict[int, np.ndarray] | None:
    """Each segment's pixels in a frame, by its Segment Number, those that
    hold none left out; None where a pixel lies in no segment that the
    Segment Sequence describes and is not background."""
    if values.shape != segments.shape:
        return None
    finite = np.isfinite(values)
    if number is not None:
        mask = finite & (values != 0)
        return {number: mask} if mask.any() else {}
    held = np.unique(values[finite])
    if not np.isin(held, segments.numbers).all():
        return None
    return {int(value): finite & (values == value) for value in held}


def _box(
    pieces: Sequence[_Piece], axes: tuple[int, int, int], shape: tuple[int, int, int]
) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
    """The first voxel and the shape of the voxels that pieces hold, with a
    voxel more on each side within the lattice's ``shape``; None for none."""
    if not pieces:
        return None
    normal, down, across = (_ARRAY_AXIS[axis] for axis in axes)
    low = [0, 0, 0]
    high = [0, 0, 0]
    low[normal] = min(int(slices.min()) for slices, _, _ in pieces)
    high[normal] = max(int(slices.max()) for slices, _, _ in pieces)
    low[down] = min(corner[0] for _, corner, _ in pieces)
    high[down] = max(corner[0] + plane.shape[0] - 1 for _, corner, plane in pieces)
    low[across] = min(corner[1] for _, corner, _ in pieces)
    high[across] = max(corner[1] + plane.shape[1] - 1 for _, corner, plane in pieces)
    start = tuple(max(value - 1, 0) for value in low)
    stop = tuple(min(value + 2, size) for value, size in zip(high, shape))
    return (
        (start[0], start[1], start[2]),
        (stop[0] - start[0], stop[1] - start[1], stop[2] - start[2]),
    )


def _region(
    pieces: Sequence[_Piece],
    axes: tuple[int, int, int],
    box: tuple[tuple[int, int, int], tuple[int, int, int]],
) -> np.ndarray:
    """The voxels of ``box`` that the pieces hold, indexed as views take them."""
    start, shape = box
    inside = np.zeros(shape, bool)
    for slices, corner, plane in pieces:
        _put(inside, start, axes, slices, corner, plane)
    return inside


def _views(inside: np.ndarray) -> np.ndarray:
    return qc_contours.rgb(qc_surfaces.side_by_side(qc_surfaces.views(inside)))


def _height(heights: Sequence[int]) -> int:
    """The pixels that rows of these heights take, each with a gutter above it."""
    return sum(each + qc_contours.GUTTER_PIXELS for each in heights)
