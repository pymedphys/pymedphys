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

"""Planar polygons in three dimensions, each a ring of points in rows of x,
y, and z, its last point joined to its first.

A ring is clipped to a half-space by :func:`clip`, which separates the
pieces into which the half-space's plane cuts it; rings are grouped by the
plane they lie in by :func:`coplanar`; and pieces that tile a region, such
as those of a ring clipped to each of several regions that meet only at
their boundaries, are joined back into the region's rings by
:func:`dissolve`. :func:`signed_area` and :func:`is_simple` read a ring
lying in a plane of constant z by its x and y.
"""

from __future__ import annotations

import collections
import itertools
import math

from pymedphys._imports import numpy as np


def clip(points: np.ndarray, normal: np.ndarray, offset: float) -> list[np.ndarray]:
    """Return the rings of a ring's part in the closed half-space where a
    point's dot product with ``normal`` is at most ``offset``.

    A vertex on the plane is taken to lie outside, so that the edges into
    and out of it cross the plane there, as the polygon's would if the
    vertex lay just beyond it. Where the plane cuts the ring into more than
    one piece, they are separated by pairing the points at which its edges
    cross the plane, in order along their line, as a simple polygon's pair;
    where they cannot be paired, as for a ring that crosses itself, the
    part is returned as one ring joined along the plane.

    Parameters
    ----------
    points : numpy.ndarray
        The ring's points in rows of x, y, and z.
    normal : numpy.ndarray
        The half-space's outward normal.
    offset : float
        The plane's dot product with ``normal``.

    Returns
    -------
    list of numpy.ndarray
        Each ring of the part, none where the ring lies wholly outside, and
        the ring itself where it lies wholly inside.
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
    """Split a ring's events, starting with an entry, into chains, each from
    an entry through the vertices kept to the next exit; None where they do
    not run so."""
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
    """Join a ring's chains into rings along the plane, or None where their
    crossings cannot be paired.

    The crossings lie on the line where the plane meets the ring's own. In
    order along it, each pair, the first and second, the third and fourth,
    and so on, bounds a stretch of the line within the ring, so each pair
    is an exit and an entry, and each ring runs along the plane from a
    chain's exit to the entry of its pair.
    """
    centred = points - points.mean(axis=0)
    # Newell's method gives the ring's normal, scaled by twice its area.
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


def coplanar(
    polygons: list[np.ndarray], tolerance: float
) -> tuple[list[list[int]], list[int]]:
    """Group rings, by their indices, into those that lie in one plane,
    within ``tolerance``, and list those that lie in none.

    A ring's plane is the one that fits its points best, its normal the
    direction in which they spread least, so that it is found for any
    winding, and for a ring that crosses itself, such as a bow tie, whose
    signed area may be zero. Two rings lie in one plane where every point of
    one lies within ``tolerance`` of the other's plane, which holds for a
    small ring, whose own normal is uncertain, in a large ring's plane.
    Each pair is compared, and groups that share a ring are joined, so that
    no ring is kept from a group by the order in which they are given. A
    ring whose points lie on one line bounds nothing and is alone; one with
    a point farther than ``tolerance`` from its own plane lies in none.

    Returns
    -------
    tuple
        The groups, each a sorted list of indices, those of rings in a plane
        first, sorted, and then each ring alone, and the indices of the
        rings that lie in no one plane.
    """
    planes: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    alone: list[list[int]] = []
    unplaced: list[int] = []
    for index, points in enumerate(polygons):
        centre = points.mean(axis=0)
        _, spread, axes = np.linalg.svd(points - centre, full_matrices=False)
        if len(spread) < 3 or not spread[1] > 1e-9 * spread[0]:
            alone.append([index])
        elif not np.max(np.abs((points - centre) @ axes[2])) <= tolerance:
            unplaced.append(index)
        else:
            planes[index] = (axes[2], centre)

    def within(polygon: int, plane: int) -> bool:
        normal, centre = planes[plane]
        return bool(np.max(np.abs((polygons[polygon] - centre) @ normal)) <= tolerance)

    root = {index: index for index in planes}

    def find(index: int) -> int:
        while root[index] != index:
            root[index] = root[root[index]]
            index = root[index]
        return index

    placed = sorted(planes)
    for position, one in enumerate(placed):
        for other in placed[position + 1 :]:
            # A ring's centre's signed distance from a plane is the mean of
            # its points', so where the centre lies farther, so does some
            # point, and the ring is not in that plane.
            near = (
                abs(float(planes[other][0] @ (planes[one][1] - planes[other][1])))
                <= tolerance
                or abs(float(planes[one][0] @ (planes[other][1] - planes[one][1])))
                <= tolerance
            )
            if near and (within(one, other) or within(other, one)):
                root[find(one)] = find(other)
    groups: dict[int, list[int]] = collections.defaultdict(list)
    for index in placed:
        groups[find(index)].append(index)
    return sorted(groups.values()) + alone, unplaced


def signed_area(points: np.ndarray) -> float:
    """The area that a ring bounds, by its x and y, positive where it runs
    anticlockwise as seen from positive z.

    The points are taken relative to their mean, so that a ring far from the
    origin loses no more precision than one near it.
    """
    x = points[:, 0] - points[:, 0].mean()
    y = points[:, 1] - points[:, 1].mean()
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)) / 2


def is_simple(points: np.ndarray) -> bool:
    """Whether a ring, by its x and y, has three points or more, no edge of
    no length, and no two edges that meet but at the vertex they share as
    neighbours, so that it bounds one region without crossing or touching
    itself."""
    count = len(points)
    if count < 3:
        return False
    starts = np.asarray(points[:, :2], dtype=float)
    ends = np.roll(starts, -1, axis=0)
    if not np.all(np.isfinite(starts)) or (starts == ends).all(axis=1).any():
        return False
    # Each edge against those after it, in blocks to bound memory; two edges
    # that are neighbours share a vertex and are compared only for overlap.
    block = max(1, (1 << 22) // count)
    for first in range(0, count, block):
        rows = np.arange(first, min(first + block, count))
        a, b, c, d = (
            starts[rows, None],
            ends[rows, None],
            starts[None, :],
            ends[None, :],
        )
        later = np.arange(count)[None, :] > rows[:, None]
        neighbours = (np.arange(count)[None, :] == rows[:, None] + 1) | (
            (rows[:, None] == 0) & (np.arange(count)[None, :] == count - 1)
        )
        # Two edges can meet only where their closed bounding boxes do, so
        # only those pairs are tested exactly and can count as meeting, which
        # spares the exact tests of the many pairs of edges far apart along
        # one line; every pair is still tested with rounding.
        boxes = np.ones(later.shape, dtype=bool)
        for axis in (0, 1):
            boxes &= np.minimum(a[..., axis], b[..., axis]) <= np.maximum(
                c[..., axis], d[..., axis]
            )
            boxes &= np.minimum(c[..., axis], d[..., axis]) <= np.maximum(
                a[..., axis], b[..., axis]
            )
        if _meet(a, b, c, d, boxes & later & ~neighbours).any():
            return False
        if _overlap(a, b, c, d, later & neighbours).any():
            return False
    return True


def _cross(origin: np.ndarray, one: np.ndarray, other: np.ndarray) -> np.ndarray:
    """The z of the cross product of ``one - origin`` and ``other - origin``,
    broadcast."""
    cross: np.ndarray = (one[..., 0] - origin[..., 0]) * (
        other[..., 1] - origin[..., 1]
    ) - (one[..., 1] - origin[..., 1]) * (other[..., 0] - origin[..., 0])
    return cross


# Shewchuk's bound on the rounding error of :func:`_cross`, relative to the
# sum of its two products' magnitudes, for doubles ("Adaptive Precision
# Floating-Point Arithmetic and Fast Robust Geometric Predicates", 1997, as
# ccwerrboundA), which assumes that no product underflows, as none does but
# for points within about 1e-154 of each other. A cross product of less
# magnitude than the bound may have the wrong sign.
_CROSS_ERROR = (3 + 16 * 2.0**-53) * 2.0**-53


def _side(
    origin: np.ndarray,
    one: np.ndarray,
    other: np.ndarray,
    where: np.ndarray | bool = True,
) -> np.ndarray:
    """The sign of :func:`_cross`, broadcast, found exactly for the points as
    given, where ``where`` holds, wherever rounding could have changed it,
    as it can for points in a line that no axis runs along. Where ``where``
    does not hold, the sign is as rounded, which callers mask away."""
    left = (one[..., 0] - origin[..., 0]) * (other[..., 1] - origin[..., 1])
    right = (one[..., 1] - origin[..., 1]) * (other[..., 0] - origin[..., 0])
    cross = left - right
    side: np.ndarray = np.array(np.sign(cross))
    unsure = (np.abs(cross) < _CROSS_ERROR * (np.abs(left) + np.abs(right))) & where
    if unsure.any():
        shape = cross.shape + (2,)
        o, p, q = (
            np.broadcast_to(each[..., :2], shape)[unsure]
            for each in (origin, one, other)
        )
        # Where two of the points are one, it is exactly zero.
        apart = ~((p == o).all(axis=1) | (q == o).all(axis=1) | (q == p).all(axis=1))
        exact = np.zeros(len(o), dtype=side.dtype)
        exact[apart] = [
            _exact_side(*each)
            for each in zip(o[apart].tolist(), p[apart].tolist(), q[apart].tolist())
        ]
        side[unsure] = exact
    return side


def _exact_side(origin: list[float], one: list[float], other: list[float]) -> int:
    """The sign of :func:`_cross` for three points, found exactly by
    integers, each coordinate being an integer over a power of two."""
    ratios = [value.as_integer_ratio() for value in (*origin, *one, *other)]
    scale = max(denominator for _, denominator in ratios)
    ox, oy, px, py, qx, qy = (
        numerator * (scale // denominator) for numerator, denominator in ratios
    )
    exact = (px - ox) * (qy - oy) - (py - oy) * (qx - ox)
    return (exact > 0) - (exact < 0)


def _between(start: np.ndarray, end: np.ndarray, point: np.ndarray) -> np.ndarray:
    """Whether a point collinear with a segment lies on it, ends included."""
    between: np.ndarray = (
        (np.minimum(start[..., 0], end[..., 0]) <= point[..., 0])
        & (point[..., 0] <= np.maximum(start[..., 0], end[..., 0]))
        & (np.minimum(start[..., 1], end[..., 1]) <= point[..., 1])
        & (point[..., 1] <= np.maximum(start[..., 1], end[..., 1]))
    )
    return between


def _meet(
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
    d: np.ndarray,
    where: np.ndarray | bool = True,
) -> np.ndarray:
    """Whether segments ab and cd share a point, ends included, where
    ``where`` holds; false elsewhere."""
    first, second = _side(a, b, c, where), _side(a, b, d, where)
    third, fourth = _side(c, d, a, where), _side(c, d, b, where)
    proper = (first * second < 0) & (third * fourth < 0)
    touching = (
        ((first == 0) & _between(a, b, c))
        | ((second == 0) & _between(a, b, d))
        | ((third == 0) & _between(c, d, a))
        | ((fourth == 0) & _between(c, d, b))
    )
    meet: np.ndarray = (proper | touching) & where
    return meet


def _overlap(
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
    d: np.ndarray,
    where: np.ndarray | bool = True,
) -> np.ndarray:
    """Whether neighbouring segments ab and cd, sharing a vertex, also share
    more than it: they lie along one line and double back over each other,
    where ``where`` holds; false elsewhere."""
    collinear = (_side(a, b, c, where) == 0) & (_side(a, b, d, where) == 0)
    forward = (b[..., 0] - a[..., 0]) * (d[..., 0] - c[..., 0]) + (
        b[..., 1] - a[..., 1]
    ) * (d[..., 1] - c[..., 1])
    overlap: np.ndarray = collinear & (forward < 0) & where
    return overlap


def dissolve(
    pieces: list[np.ndarray], kept: np.ndarray, tolerance: float
) -> list[np.ndarray] | None:
    """Join anticlockwise rings that tile a region, meeting only at their
    boundaries, into the region's own rings, by x and y.

    Points within ``tolerance`` of each other are taken as one, the first
    given standing for them, so that the points of ``kept``, given first,
    are written as they are. An edge is split where another ring's point
    lies on it; edges that two rings share, running opposite ways, are
    dropped; and what is left is chained into rings, turning as far left as
    can be at a point where more than one edge leaves, keeping to the
    region on its left. A ring that passes through a point more than once,
    as where two holes, or a hole and the outer boundary, touch at a point,
    is split there into rings that each pass through it once. A point
    between two edges along one line is dropped, unless it is one of
    ``kept``.

    Parameters
    ----------
    pieces : list of numpy.ndarray
        The rings, each anticlockwise, in rows of x and y.
    kept : numpy.ndarray
        Points, in rows of x and y, to write as they are where they remain.
    tolerance : float
        How far apart two points may be and be taken as one, above zero.

    Returns
    -------
    list of numpy.ndarray or None
        The region's rings, outer ones anticlockwise and holes clockwise,
        none passing through a point twice, whose signed areas sum to the
        pieces'; None where they do not, or a ring cannot be closed, so that
        the caller can keep the pieces.

    Raises
    ------
    ValueError
        If ``tolerance`` is not a finite number above zero.
    """
    if not (math.isfinite(tolerance) and tolerance > 0):
        raise ValueError("the tolerance must be a finite number above zero")
    points = np.concatenate([np.asarray(kept, float).reshape(-1, 2)] + pieces)
    identity = _cluster(points, tolerance)
    first = len(np.asarray(kept).reshape(-1, 2))
    original = set(identity[:first].tolist())
    position: dict[int, np.ndarray] = {}
    for index, each in enumerate(identity.tolist()):
        position.setdefault(each, points[index])
    edges: list[tuple[int, int]] = []
    offset = first
    for piece in pieces:
        ids = identity[offset : offset + len(piece)].tolist()
        offset += len(piece)
        for start, end in zip(ids, ids[1:] + ids[:1]):
            if start != end:
                edges.append((start, end))
    edges = _split(edges, position, tolerance)
    count = collections.Counter(edges)
    left: list[tuple[int, int]] = []
    for (start, end), number in count.items():
        net = number - count.get((end, start), 0)
        left.extend([(start, end)] * max(net, 0))
    rings = _chain(left, position)
    if rings is None:
        return None
    written = [
        np.asarray(
            [
                position[each]
                for each in _straightened(loop, position, original, tolerance)
            ]
        )
        for ring in rings
        for loop in _loops(ring)
    ]
    written = [ring for ring in written if len(ring) >= 3]
    total = sum(signed_area(piece) for piece in pieces)
    got = sum(signed_area(ring) for ring in written)
    scale = max(1.0, sum(abs(signed_area(piece)) for piece in pieces))
    if not abs(got - total) <= 1e-9 * scale:
        return None
    return written


def _cluster(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Return, for each point, the index of the first point within
    ``tolerance`` of it, through any chain of such points."""
    cells = np.floor(points / tolerance).astype(np.int64)
    root = list(range(len(points)))

    def find(index: int) -> int:
        while root[index] != index:
            root[index] = root[root[index]]
            index = root[index]
        return index

    buckets: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    for index, cell in enumerate(map(tuple, cells.tolist())):
        near = [
            other
            for dx, dy in itertools.product((-1, 0, 1), repeat=2)
            for other in buckets.get((cell[0] + dx, cell[1] + dy), ())
            if np.hypot(*(points[index] - points[other])) <= tolerance
        ]
        for other in near:
            one, two = find(index), find(other)
            root[max(one, two)] = min(one, two)
        buckets[cell].append(index)
    return np.array([find(index) for index in range(len(points))])


def _split(
    edges: list[tuple[int, int]], position: dict, tolerance: float
) -> list[tuple[int, int]]:
    """Split each edge at every point that lies on it, in order along it."""
    ids = np.array(sorted(position))
    where = np.array([position[each] for each in ids])
    split: list[tuple[int, int]] = []
    for start, end in edges:
        a, b = position[start], position[end]
        direction = b - a
        length = float(np.hypot(*direction))
        along = (where - a) @ direction / length
        across = np.abs(_cross(a, b, where)) / length
        on = (
            (across <= tolerance)
            & (along > tolerance)
            & (along < length - tolerance)
            & (ids != start)
            & (ids != end)
        )
        chain = [start] + ids[on][np.argsort(along[on])].tolist() + [end]
        split.extend(zip(chain, chain[1:]))
    return split


def _chain(edges: list[tuple[int, int]], position: dict) -> list[list[int]] | None:
    """Chain directed edges into rings, turning as far left as can be where
    more than one edge leaves a point; None where a ring cannot be
    closed."""
    leaving: dict[int, list[int]] = collections.defaultdict(list)
    for start, end in edges:
        leaving[start].append(end)
    rings = []
    while any(leaving.values()):
        start = next(each for each, ends in leaving.items() if ends)
        ring = [start]
        current = leaving[start].pop()
        previous = start
        while current != start:
            ring.append(current)
            ends = leaving.get(current)
            if not ends:
                return None
            incoming = position[current] - position[previous]
            # The most anticlockwise turn from the incoming direction, which
            # keeps to the region on the left, a turn straight back being the
            # least.
            turn = [_turn(incoming, position[end] - position[current]) for end in ends]
            chosen = ends.pop(int(np.argmax(turn)))
            previous, current = current, chosen
            if len(ring) > len(edges) + 1:
                return None
        rings.append(ring)
    return rings


def _loops(ring: list[int]) -> list[list[int]]:
    """Split a ring, by its points, at each point it passes through more
    than once, into rings that each pass through it once."""
    loops = []
    path: list[int] = []
    where: dict[int, int] = {}
    for each in ring:
        if each in where:
            # The ring has come back to a point: what it passed through
            # since is a ring of its own.
            start = where[each]
            loops.append(path[start:])
            for passed in path[start + 1 :]:
                del where[passed]
            del path[start + 1 :]
        else:
            where[each] = len(path)
            path.append(each)
    loops.append(path)
    return loops


def _turn(incoming: np.ndarray, outgoing: np.ndarray) -> float:
    """The angle, in radians from -pi to just below pi, anticlockwise
    positive, from one direction to another, a turn straight back being
    -pi."""
    angle = math.atan2(
        float(incoming[0] * outgoing[1] - incoming[1] * outgoing[0]),
        float(incoming @ outgoing),
    )
    return -math.pi if abs(angle) >= math.pi else angle


def _straightened(
    ring: list[int], position: dict, original: set, tolerance: float
) -> list[int]:
    """Drop each point of a ring within ``tolerance`` of the line between its
    neighbours and between them, unless it is one of the points kept as
    given."""
    changed = True
    while changed and len(ring) > 3:
        changed = False
        for index, each in enumerate(ring):
            if each in original:
                continue
            before = position[ring[index - 1]]
            after = position[ring[(index + 1) % len(ring)]]
            here = position[each]
            span = float(np.hypot(*(after - before)))
            if (
                span > 0
                and abs(float(_cross(before, here, after))) <= tolerance * span
                and (here - before) @ (after - here) > 0
            ):
                del ring[index]
                changed = True
                break
    return ring
