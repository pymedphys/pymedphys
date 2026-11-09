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

"""Renders of an instance's surface meshes for the confidential QC pack's
face review (D-017).

A Surface Segmentation holds, in each item of its Surface Sequence
(0066,0002), a mesh: points in the patient's coordinates, in Point
Coordinates Data (0066,0016), and the primitives that join them, by their
indices from 1 (PS3.3 Sections C.27.2.1.1 and C.27.4.1). A mesh of the skin
or of the body is a 3D model of the face, from which a face-recognition
system can match it, and its segment's label or code need not say that it
is one, so :func:`mesh_sheet` renders every mesh that an instance holds,
as the run wrote it, by :func:`~.qc_surfaces.views`, from the six
directions of :data:`~.qc_surfaces.VIEWS`, so that a reviewer can see a
face where a mesh traces one. The sheet's rows, from the top, separated by
grey rows of :data:`~.qc_contours.GUTTER_PIXELS`, are every mesh united;
then, for each item of the Surface Sequence, in order, its mesh alone, since
the union hides a mesh wholly inside another, followed by the rows of
:func:`~.qc_surfaces.hidden_rows`, in which every surface that the frontal
view, the view from behind, and the profiles cross is shown, as a closed
mesh's back is.

Each mesh is drawn into cubic voxels along the patient's axes, of
:data:`~.qc_surfaces.MINIMUM_VOXEL` millimetres, which lie at whole
multiples of their side and span every point of every mesh, with a voxel
more on each side, so that neither their side nor their positions depend on
the meshes. A voxel is drawn where it holds a point of the mesh, every
point being drawn, whatever primitive uses it, so that a cloud of points,
or a vertex, shows; where it holds a sample of an edge, of a line between
its consecutive points, or of a facet's edges, the last point joined to the
first; or where it holds a sample of a triangle, of a triangle strip, each
three consecutive points, of a triangle fan, its first point with each two
consecutive others, or of a facet, which is filled exactly, by ear
clipping in its plane (:func:`_facet`), since a facet need not be convex
and a fan from its first point would fill its convex hull, hiding its
outline. Edges and triangles are
sampled at most a quarter of a voxel apart, so that each ray of the views
that crosses a primitive meets a voxel drawn of it. The retired 16-bit
index lists of PS3.3-2014a (Triangle, Edge, and Vertex Point Index List and
Primitive Point Index List) are drawn as their 32-bit replacements are.

A sheet is drawn only of an instance whose meshes it can read
(:func:`meshes_of`): of a data set read in little endian, with at least one
item in its Surface Sequence, each with one Surface Points Sequence item of
Point Coordinates Data, three 32-bit floats for each point, at least one
point, each finite and within :data:`~.qc_contours.FARTHEST` millimetres,
and no Double Point Coordinates Data (0066,0022), which the Points Macro
does not define; each index of each list from 1 to the count of its mesh's
points, an edge list of pairs, a triangle list of triples, a strip or fan
of three points or more, and a line or facet of one or more, each facet a
simple polygon, its outline neither crossing nor touching itself, of at
most :data:`MOST_FACET_POINTS` points, each within
:data:`FACET_FLATNESS` millimetres of its plane, or one that encloses
nothing, its points on one line; and where its
points span at most :data:`~.qc_surfaces.LONGEST` millimetres along the
patient's z axis and :data:`~.qc_surfaces.WIDEST` across, as a contour
sheet's frame does, and its primitives at most :data:`MOST_SAMPLES`
samples; nor is a sheet taller than ``tallest``, which is drawn only until
it is. An instance any of whose meshes cannot be drawn is shown by no
sheet, and a verdict cannot release it.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterator, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import qc_contours, qc_surfaces

# Surface Sequence (0066,0002) of the Surface Mesh Module (PS3.3 Section
# C.27.1), each of whose items holds one mesh.
SURFACE_SEQUENCE = 0x00660002
# Surface Points Sequence (0066,0011), whose one item holds a mesh's points
# as Point Coordinates Data (0066,0016), and Double Point Coordinates Data
# (0066,0022), which the Points Macro does not define.
SURFACE_POINTS_SEQUENCE = 0x00660011
POINT_COORDINATES_DATA = 0x00660016
DOUBLE_POINT_COORDINATES_DATA = 0x00660022
# Surface Mesh Primitives Sequence (0066,0013), whose items list the
# primitives (PS3.3 Table C.27-4).
SURFACE_MESH_PRIMITIVES_SEQUENCE = 0x00660013
# The lists of an item of the Surface Mesh Primitives Sequence, each by its
# Long (OL) and retired (OW) tags: Vertex, Edge, and Triangle Point Index
# List.
VERTEX_LISTS = (0x00660043, 0x00660025)
EDGE_LISTS = (0x00660042, 0x00660024)
TRIANGLE_LISTS = (0x00660041, 0x00660023)
# The sequences of an item of the Surface Mesh Primitives Sequence, each of
# whose items lists one primitive by its Long Primitive Point Index List
# (0066,0040), or the retired Primitive Point Index List (0066,0029).
TRIANGLE_STRIP_SEQUENCE = 0x00660026
TRIANGLE_FAN_SEQUENCE = 0x00660027
LINE_SEQUENCE = 0x00660028
FACET_SEQUENCE = 0x00660034
PRIMITIVE_LISTS = (0x00660040, 0x00660029)
# The tallest sheet that is drawn, as a contour sheet's; a taller one is
# not, so that its instance is held rather than shown in an image that a
# viewer may scale down or refuse.
MAXIMUM_SHEET_PIXELS = qc_contours.MAXIMUM_SHEET_PIXELS
# The most samples of an instance's edges and triangles that are drawn, some
# 1.5 GB of coordinates were they all held at once, which they are not; the
# skin of a whole body, of some 2 square metres, takes about 32 million.
MOST_SAMPLES = 1 << 27
# How many samples a primitive is drawn with per voxel's side.
_SAMPLES_PER_VOXEL = 4
# How many samples are placed at a time.
_SAMPLES_AT_A_TIME = 1 << 20
# The most points of a facet that is triangulated; a mesh with a facet of
# more is not drawn, so that ear clipping, quadratic in a facet's points,
# stays bounded.
MOST_FACET_POINTS = 1 << 10
# How far, in millimetres, a facet's points may lie from its plane, a
# quarter of a voxel's side, the spacing at which its triangles are
# sampled; a facet whose points lie farther is not a planar polygon, as
# PS3.3 Section C.27.4.1 defines one, and its mesh is not drawn.
FACET_FLATNESS = qc_surfaces.MINIMUM_VOXEL / 4
# How many bytes each index takes, by the VR of its list: 32-bit for the
# Long lists, 16-bit for the retired ones.
_INDEX_TYPES = {"OL": "<u4", "OW": "<u2"}


@dataclasses.dataclass(frozen=True, repr=False)
class Mesh:
    """One item of a Surface Sequence, placed in the patient's coordinates.

    Its ``repr`` shows only its counts.

    Attributes
    ----------
    points : numpy.ndarray
        Of shape (points, 3), float64: each point's x, y, and z, in
        millimetres.
    edges : numpy.ndarray
        Of shape (edges, 2), intp: the indices, from 0, of the two points
        of each edge, of an edge list, a line, or a facet's outline.
    triangles : numpy.ndarray
        Of shape (triangles, 3), intp: the indices, from 0, of the three
        points of each triangle, of a triangle list, a strip, a fan, or a
        facet.
    """

    points: np.ndarray
    edges: np.ndarray
    triangles: np.ndarray

    def __repr__(self) -> str:
        return (
            f"Mesh(points={len(self.points)}, edges={len(self.edges)}, "
            f"triangles={len(self.triangles)})"
        )


def meshes_of(  # pylint: disable = too-many-return-statements
    dataset: pydicom.Dataset,
) -> tuple[Mesh, ...] | None:
    """Return each mesh that a data set holds, in the order of its Surface
    Sequence's items, or None where any cannot be drawn, or it has none, as
    the module describes.

    A data set without a Surface Sequence holds none, and gives an empty
    tuple.
    """
    if SURFACE_SEQUENCE not in dataset:
        return ()
    try:
        little = getattr(dataset, "original_encoding", (None, True))[1]
        if little is False:
            return None
        items = dataset[SURFACE_SEQUENCE].value or ()
        found = []
        for item in items:
            mesh = _mesh(item)
            if mesh is None:
                return None
            found.append(mesh)
    # Whatever reading a sequence or value raises, its meshes cannot be
    # drawn.
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    if not found:
        return None
    low, high = _extent(found)
    spans = high - low
    if spans[2] > qc_surfaces.LONGEST or max(spans[:2]) > qc_surfaces.WIDEST:
        return None
    if sum(_samples(mesh) for mesh in found) > MOST_SAMPLES:
        return None
    return tuple(found)


def _mesh(item: pydicom.Dataset) -> Mesh | None:
    """One Surface Sequence item's mesh, or None where it cannot be drawn."""
    points = _points(item)
    if points is None:
        return None
    count = len(points)
    edges: list[np.ndarray] = []
    triangles: list[np.ndarray] = []
    for primitives in _items(item, SURFACE_MESH_PRIMITIVES_SEQUENCE):
        for tags, size in ((VERTEX_LISTS, 1), (EDGE_LISTS, 2), (TRIANGLE_LISTS, 3)):
            for tag in tags:
                indices = _indices(primitives, tag, count)
                if indices is None:
                    return None
                if len(indices) % size:
                    return None
                if size == 2:
                    edges.append(indices.reshape(-1, 2))
                elif size == 3:
                    triangles.append(indices.reshape(-1, 3))
        for sequence in (
            TRIANGLE_STRIP_SEQUENCE,
            TRIANGLE_FAN_SEQUENCE,
            LINE_SEQUENCE,
            FACET_SEQUENCE,
        ):
            for primitive in _items(primitives, sequence):
                indices = _primitive(primitive, count)
                if indices is None:
                    return None
                joined = _joined(sequence, indices, points)
                if joined is None:
                    return None
                edges.extend(joined[0])
                triangles.extend(joined[1])
    return Mesh(
        points,
        np.concatenate([np.zeros((0, 2), np.intp), *edges]).astype(np.intp),
        np.concatenate([np.zeros((0, 3), np.intp), *triangles]).astype(np.intp),
    )


def _points(item: pydicom.Dataset) -> np.ndarray | None:
    """A mesh's points, or None where they cannot be drawn."""
    found = _items(item, SURFACE_POINTS_SEQUENCE)
    if len(found) != 1:
        return None
    (points,) = found
    if DOUBLE_POINT_COORDINATES_DATA in points or POINT_COORDINATES_DATA not in points:
        return None
    data = points[POINT_COORDINATES_DATA].value
    if not isinstance(data, bytes) or not data or len(data) % 12:
        return None
    coordinates = np.frombuffer(data, "<f4").astype(np.float64).reshape(-1, 3)
    if not np.isfinite(coordinates).all():
        return None
    if (np.abs(coordinates) > qc_contours.FARTHEST).any():
        return None
    return coordinates


def _items(item: pydicom.Dataset, tag: int) -> Sequence[pydicom.Dataset]:
    """A sequence's items, none where it is absent or empty."""
    if tag not in item:
        return ()
    return item[tag].value or ()


def _indices(item: pydicom.Dataset, tag: int, count: int) -> np.ndarray | None:
    """A list's indices, from 0, none where it is absent or empty; None
    where it cannot be read, or any index is not from 1 to ``count``."""
    if tag not in item:
        return np.zeros(0, np.intp)
    element = item[tag]
    data = element.value
    if data is None or data == b"":
        return np.zeros(0, np.intp)
    kind = _INDEX_TYPES.get(element.VR)
    if kind is None or not isinstance(data, bytes):
        return None
    size = np.dtype(kind).itemsize
    if len(data) % size:
        return None
    indices = np.frombuffer(data, kind).astype(np.int64)
    if indices.size and (indices.min() < 1 or indices.max() > count):
        return None
    return (indices - 1).astype(np.intp)


def _primitive(primitive: pydicom.Dataset, count: int) -> np.ndarray | None:
    """One primitive's indices, from 0, of its Long Primitive Point Index
    List and its retired Primitive Point Index List; None where either
    cannot be read, or both are given, or neither."""
    lists = [tag for tag in PRIMITIVE_LISTS if tag in primitive]
    if len(lists) != 1:
        return None
    return _indices(primitive, lists[0], count)


def _joined(
    sequence: int, indices: np.ndarray, points: np.ndarray
) -> tuple[list[np.ndarray], list[np.ndarray]] | None:
    """The edges and the triangles of one primitive of a sequence, as the
    module describes; None where it has too few points to be one, or is a
    facet that :func:`_facet` cannot triangulate."""
    count = len(indices)
    if sequence in (TRIANGLE_STRIP_SEQUENCE, TRIANGLE_FAN_SEQUENCE):
        if count < 3:
            return None
        following = np.stack([indices[1:-1], indices[2:]], axis=1)
        if sequence == TRIANGLE_STRIP_SEQUENCE:
            first = indices[:-2, np.newaxis]
        else:
            first = np.full((count - 2, 1), indices[0])
        return [], [np.concatenate([first, following], axis=1)]
    if count < 1:
        return None
    if sequence == LINE_SEQUENCE:
        return [np.stack([indices[:-1], indices[1:]], axis=1)], []
    # A facet: its outline, closed, and the triangles that fill it.
    outline = np.stack([indices, np.roll(indices, -1)], axis=1)
    filled = _facet(indices, points)
    if filled is None:
        return None
    return [outline], [filled]


def _facet(  # pylint: disable = too-many-return-statements
    indices: np.ndarray, points: np.ndarray
) -> np.ndarray | None:
    """The triangles, by point index, that fill a facet's polygon exactly,
    whatever point its list starts from; None where it is not a simple
    planar polygon, or has more than :data:`MOST_FACET_POINTS` points.

    A facet is a closed planar polygon (PS3.3 Section C.27.4.1), which need
    not be convex, so it is filled by ear clipping in its plane, which
    covers the polygon and nothing more. Repeated consecutive points are
    one; a polygon of fewer than three distinct points, or whose points
    are collinear, encloses nothing, and is drawn by its outline alone.
    """
    if len(indices) > MOST_FACET_POINTS:
        return None
    none = np.zeros((0, 3), np.intp)
    corners = points[indices]
    distinct = np.any(corners != np.roll(corners, -1, axis=0), axis=1)
    indices, corners = indices[distinct], corners[distinct]
    if len(indices) < 3:
        return none
    centre = corners.mean(axis=0)
    # Newell's normal, whose length is twice the polygon's area.
    following = np.roll(corners, -1, axis=0)
    normal = np.cross(corners - centre, following - centre).sum(axis=0)
    size = float(np.max(np.ptp(corners, axis=0)))
    length = float(np.linalg.norm(normal))
    if length <= 1e-12 * size * size:
        # Points on one line enclose nothing; others of no net area are an
        # outline that crosses itself, as a figure of eight's.
        spread = np.linalg.svd(corners - centre, compute_uv=False)
        return none if spread[1] <= 1e-9 * spread[0] else None
    normal = normal / length
    if np.max(np.abs((corners - centre) @ normal)) > FACET_FLATNESS:
        return None
    across = np.cross(normal, [1.0, 0.0, 0.0])
    if np.linalg.norm(across) < 0.5:
        across = np.cross(normal, [0.0, 1.0, 0.0])
    across = across / np.linalg.norm(across)
    flat = (corners - centre) @ np.stack([across, np.cross(normal, across)], axis=1)
    if _crossed(flat):
        return None
    clipped = _ears(flat)
    if clipped is None:
        return None
    return indices[clipped]


def _crossed(flat: np.ndarray) -> bool:
    """Whether a closed polygon's outline, in its plane, meets itself other
    than where each side meets the next, or doubles back along it."""
    count = len(flat)
    ends = np.roll(flat, -1, axis=0)
    sides = ends - flat
    tolerance = 1e-12 * float(np.max(np.ptp(flat, axis=0))) ** 2
    # A side that doubles back along the one before it.
    before = np.roll(sides, 1, axis=0)
    turned = before[:, 0] * sides[:, 1] - before[:, 1] * sides[:, 0]
    if np.any((np.abs(turned) <= tolerance) & (np.sum(before * sides, axis=1) < 0)):
        return True
    for first in range(count - 2):
        # Each later side that is not adjacent to this one.
        last = count - 1 if first == 0 else count
        others = np.arange(first + 2, last)
        if len(others) == 0:
            continue
        if np.any(
            _meet(flat[first], ends[first], flat[others], ends[others], tolerance)
        ):
            return True
    return False


def _meet(
    start: np.ndarray,
    end: np.ndarray,
    starts: np.ndarray,
    ends: np.ndarray,
    tolerance: float,
) -> np.ndarray:
    """Whether a segment meets, or touches, each of others."""

    def turn(a, b, c):
        return (b[..., 0] - a[..., 0]) * (c[..., 1] - a[..., 1]) - (
            b[..., 1] - a[..., 1]
        ) * (c[..., 0] - a[..., 0])

    def between(a, b, c):
        # Whether c, collinear with a and b, lies within their box.
        return np.all(
            (np.minimum(a, b) - 1e-12 <= c) & (c <= np.maximum(a, b) + 1e-12), axis=-1
        )

    one = turn(start, end, starts)
    two = turn(start, end, ends)
    three = turn(starts, ends, start)
    four = turn(starts, ends, end)
    sign = [
        np.where(np.abs(t) <= tolerance, 0, np.sign(t)) for t in (one, two, three, four)
    ]
    crossing = (sign[0] * sign[1] < 0) & (sign[2] * sign[3] < 0)
    touching = (
        ((sign[0] == 0) & between(start, end, starts))
        | ((sign[1] == 0) & between(start, end, ends))
        | ((sign[2] == 0) & between(starts, ends, start))
        | ((sign[3] == 0) & between(starts, ends, end))
    )
    return crossing | touching


def _turn(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Twice the signed area of the triangle a, b, c in a plane, positive
    where it turns anticlockwise."""
    return float((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))


def _ears(flat: np.ndarray) -> np.ndarray | None:
    """The triangles, by corner, that ear clipping fills a simple polygon
    with, in its plane; None where no ear can be found, as of a polygon
    that is not simple."""
    tolerance = 1e-12 * float(np.max(np.ptp(flat, axis=0))) ** 2
    following = np.roll(flat, -1, axis=0)
    area = float(np.sum(flat[:, 0] * following[:, 1] - following[:, 0] * flat[:, 1]))
    orientation = 1.0 if area > 0 else -1.0
    left = list(range(len(flat)))
    triangles = []
    corner = 0
    misses = 0
    while len(left) > 3:
        count = len(left)
        before, at, after = (
            left[(corner - 1) % count],
            left[corner % count],
            left[(corner + 1) % count],
        )
        if _is_ear(flat, left, before, at, after, orientation, tolerance):
            triangles.append((before, at, after))
            del left[corner % count]
            misses = 0
            continue
        corner = (corner + 1) % count
        misses += 1
        if misses > count:
            # Only corners on a line remain, which enclose nothing, or no
            # ear exists.
            remaining = flat[left]
            ahead = np.roll(remaining, -1, axis=0)
            rest = float(
                np.sum(remaining[:, 0] * ahead[:, 1] - ahead[:, 0] * remaining[:, 1])
            )
            if abs(rest) <= tolerance:
                return np.array(triangles, np.intp).reshape(-1, 3)
            return None
    a, b, c = flat[left]
    if orientation * _turn(a, b, c) > tolerance:
        triangles.append(tuple(left))
    return np.array(triangles, np.intp).reshape(-1, 3)


def _is_ear(
    flat: np.ndarray,
    left: list[int],
    before: int,
    at: int,
    after: int,
    orientation: float,
    tolerance: float,
) -> bool:
    """Whether a polygon's corner is an ear: convex, with no other corner
    in or on the triangle that it makes with its neighbours."""
    a, b, c = flat[before], flat[at], flat[after]
    if orientation * _turn(a, b, c) <= tolerance:
        return False
    others = flat[[i for i in left if i not in (before, at, after)]]
    if len(others) == 0:
        return True
    sides = [
        orientation
        * (
            (q[0] - p[0]) * (others[:, 1] - p[1])
            - (q[1] - p[1]) * (others[:, 0] - p[0])
        )
        for p, q in ((a, b), (b, c), (c, a))
    ]
    inside = (
        (sides[0] >= -tolerance) & (sides[1] >= -tolerance) & (sides[2] >= -tolerance)
    )
    return not np.any(inside)


def _extent(meshes: Sequence[Mesh]) -> tuple[np.ndarray, np.ndarray]:
    """The lowest and highest coordinate along each patient axis of any
    point of any mesh."""
    low = np.min([mesh.points.min(axis=0) for mesh in meshes], axis=0)
    high = np.max([mesh.points.max(axis=0) for mesh in meshes], axis=0)
    return low, high


def _steps(lengths: np.ndarray) -> np.ndarray:
    """How many steps each primitive of these longest sides is sampled in,
    at most a quarter of a voxel apart, and at least one."""
    spacing = qc_surfaces.MINIMUM_VOXEL / _SAMPLES_PER_VOXEL
    return np.maximum(np.ceil(lengths / spacing), 1).astype(np.int64)


def _samples(mesh: Mesh) -> int:
    """How many samples a mesh's edges and triangles are drawn with."""
    edges = _steps(_edge_lengths(mesh))
    triangles = _steps(_longest_sides(mesh))
    return int((edges + 1).sum() + ((triangles + 1) * (triangles + 2) // 2).sum())


def _edge_lengths(mesh: Mesh) -> np.ndarray:
    ends = mesh.points[mesh.edges]
    return np.linalg.norm(ends[:, 1] - ends[:, 0], axis=1)


def _longest_sides(mesh: Mesh) -> np.ndarray:
    corners = mesh.points[mesh.triangles]
    sides = [
        np.linalg.norm(corners[:, (k + 1) % 3] - corners[:, k], axis=1)
        for k in range(3)
    ]
    return np.max(sides, axis=0) if sides[0].size else np.zeros(0)


@dataclasses.dataclass(frozen=True)
class _Lattice:
    """The voxels that meshes are drawn in: the voxel index, at whole
    multiples of the side, of the first voxel along z, which is the
    highest, and along y and x, which are the lowest, and how many voxels
    there are along each, indexed from superior, from anterior, and from
    the patient's right."""

    first: tuple[int, int, int]
    shape: tuple[int, int, int]

    @classmethod
    def of(cls, meshes: Sequence[Mesh]) -> _Lattice:
        low, high = _extent(meshes)
        voxel = qc_surfaces.MINIMUM_VOXEL
        lows = [math.floor(value / voxel + 0.5) - 1 for value in low]
        highs = [math.floor(value / voxel + 0.5) + 1 for value in high]
        first = (highs[2], lows[1], lows[0])
        shape = (
            highs[2] - lows[2] + 1,
            highs[1] - lows[1] + 1,
            highs[0] - lows[0] + 1,
        )
        return cls(first, shape)

    def voxels(self, coordinates: np.ndarray) -> tuple[np.ndarray, ...]:
        """The index of the voxel that holds each point, by axis."""
        nearest = np.floor(coordinates / qc_surfaces.MINIMUM_VOXEL + 0.5).astype(
            np.int64
        )
        return (
            self.first[0] - nearest[:, 2],
            nearest[:, 1] - self.first[1],
            nearest[:, 0] - self.first[2],
        )

    def box(self, mesh: Mesh) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        """The first voxel and the shape of the voxels that a mesh's points
        lie in, with a voxel more on each side, which hold every sample of
        its primitives too, since each lies between its points."""
        voxels = self.voxels(mesh.points)
        low = [int(each.min()) - 1 for each in voxels]
        high = [int(each.max()) + 1 for each in voxels]
        return (
            (low[0], low[1], low[2]),
            (high[0] - low[0] + 1, high[1] - low[1] + 1, high[2] - low[2] + 1),
        )


def _drawn(
    mesh: Mesh,
    lattice: _Lattice,
    start: tuple[int, int, int],
    shape: tuple[int, int, int],
) -> np.ndarray:
    """The voxels of a box of the lattice, from ``start``, of ``shape``,
    that a mesh is drawn in."""
    inside = np.zeros(shape, bool)
    for samples in _sampled(mesh):
        z, y, x = lattice.voxels(samples)
        inside[z - start[0], y - start[1], x - start[2]] = True
    return inside


def _sampled(mesh: Mesh) -> Iterator[np.ndarray]:
    """A mesh's points, then samples of its edges and of its triangles, a
    batch at a time, each of shape (samples, 3)."""
    yield mesh.points
    steps = _steps(_edge_lengths(mesh))
    for count in np.unique(steps):
        chosen = mesh.edges[steps == count]
        weights = np.linspace(0.0, 1.0, int(count) + 1)
        per = max(1, _SAMPLES_AT_A_TIME // len(weights))
        for start in range(0, len(chosen), per):
            ends = mesh.points[chosen[start : start + per]]
            yield (
                ends[:, 0, np.newaxis] * (1 - weights)[:, np.newaxis]
                + ends[:, 1, np.newaxis] * weights[:, np.newaxis]
            ).reshape(-1, 3)
    steps = _steps(_longest_sides(mesh))
    for count in np.unique(steps):
        chosen = mesh.triangles[steps == count]
        weights = _barycentric(int(count))
        per = max(1, _SAMPLES_AT_A_TIME // len(weights))
        for start in range(0, len(chosen), per):
            corners = mesh.points[chosen[start : start + per]]
            yield np.einsum("sk,tkd->tsd", weights, corners).reshape(-1, 3)


def _barycentric(steps: int) -> np.ndarray:
    """The weights of a triangle's corners at each sample of it, ``steps``
    along each side, of shape (samples, 3)."""
    i, j = np.meshgrid(np.arange(steps + 1), np.arange(steps + 1), indexing="ij")
    keep = i + j <= steps
    a = i[keep] / steps
    b = j[keep] / steps
    return np.stack([1 - a - b, a, b], axis=1)


def mesh_sheet(meshes: Sequence[Mesh], tallest: int | None = None) -> np.ndarray | None:
    """Return the sheet of an instance's meshes, as the module describes,
    in RGB.

    Each mesh alone is drawn in the voxels about its own points, as a
    segments sheet draws each segment, so that a small mesh beside a large
    one takes a short row.

    Parameters
    ----------
    meshes : sequence of Mesh
        As :func:`meshes_of` gives them of the file written; at least one.
    tallest : int, optional
        The most pixels that the sheet may be tall; by default
        :data:`MAXIMUM_SHEET_PIXELS`.

    Returns
    -------
    numpy.ndarray or None
        uint8, of shape (rows, columns, 3); or None where the sheet would
        be taller than ``tallest``, which is drawn only until it is.
    """
    if tallest is None:
        tallest = MAXIMUM_SHEET_PIXELS
    lattice = _Lattice.of(meshes)
    boxes = [lattice.box(mesh) for mesh in meshes]
    heights = [lattice.shape[0], *(shape[0] for _, shape in boxes)]
    if _height(heights) - qc_contours.GUTTER_PIXELS > tallest:
        return None
    # Each mesh is drawn twice, into the union and alone, so that only one
    # is held beside the union.
    union = np.zeros(lattice.shape, bool)
    for mesh, (start, shape) in zip(meshes, boxes):
        region = tuple(slice(first, first + size) for first, size in zip(start, shape))
        union[region] |= _drawn(mesh, lattice, start, shape)
    rows = [_views(union)]
    del union
    height = lattice.shape[0]
    for index, (mesh, (start, shape)) in enumerate(zip(meshes, boxes)):
        inside = _drawn(mesh, lattice, start, shape)
        rows.append(_views(inside))
        height += _height([shape[0]])
        # What the meshes after it need at least is kept for them.
        room = tallest - height - _height(heights[index + 2 :])
        hidden = qc_surfaces.hidden_rows(inside, room)
        if hidden is None:
            return None
        rows.extend(qc_contours.rgb(row) for row in hidden)
        height += _height([row.shape[0] for row in hidden])
        if height > tallest:
            return None
    return qc_contours.stacked(rows)


def _height(heights: Sequence[int]) -> int:
    """The pixels that rows of these heights take, each with a gutter above it."""
    return sum(each + qc_contours.GUTTER_PIXELS for each in heights)


def _views(inside: np.ndarray) -> np.ndarray:
    return qc_contours.rgb(qc_surfaces.side_by_side(qc_surfaces.views(inside)))
