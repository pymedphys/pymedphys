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

"""Where a contour's slab may lie, by its Contour Slab Thickness and
Contour Offset Vector.

A contour of an RT Structure Set's ROI Contour Sequence may carry Contour
Slab Thickness (3006,0044) and Contour Offset Vector (3006,0045), which
PS3.3 retired in 2021 (C.8.8.6.2, retired; see PS3.3-2020e). As PS3.3-2020e
defines them, the contour then represents a slab of that thickness, whose
central plane is its Contour Data moved by the offset vector, normal to the
contour's plane, and without a thickness the offset is to be zero. A reader
written since may ignore both, and one written before may honour either
alone, so the points that a contour may cover are those of its Contour Data
moved along one direction by any distance from the least to the greatest
that any reading gives (:class:`Slab`, :func:`slab_values`, :func:`slab_of`): from 0, its
Contour Data as written, to the offset, less and plus half the thickness,
along the plane's normal. A run that cuts such a contour by a face block,
or searches it for a target or an eye, takes every point of that span
(:func:`spread`).

A contour whose span cannot be found is refused (:class:`SlabRefused`): one
whose thickness or offset is not finite, beyond :data:`FARTHEST`
millimetres, or of the wrong number of values, a negative thickness, a
thickness without a plane, of a contour whose points lie on one line or do
not lie within :data:`COPLANAR` millimetres of one plane, and an offset
that departs from the plane's normal by more than :data:`COPLANAR`
millimetres.
"""

from __future__ import annotations

import dataclasses
import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from .diagnostics import redacted_diagnostics

THICKNESS = "ContourSlabThickness"
OFFSET = "ContourOffsetVector"
# How far, in millimetres, a contour's points may lie from its plane, and
# its offset from the plane's normal, as region_defacing groups contours in
# one plane.
COPLANAR = 0.15
# The largest magnitude, in millimetres, of a thickness or of a coordinate of
# an offset, as region_defacing bounds a contour's coordinates.
FARTHEST = 1e6


class SlabRefused(Exception):
    """A contour whose slab cannot be placed. Its message names no value."""

    def __init__(self) -> None:
        super().__init__("the contour's slab cannot be placed")


@dataclasses.dataclass(frozen=True, repr=False)
class Slab:
    """The span along which a contour's points may lie: each point of its
    Contour Data moved by ``t`` times :attr:`direction`, for each ``t`` from
    :attr:`near` to :attr:`far`.

    Its ``repr`` shows nothing of it.

    Attributes
    ----------
    direction : tuple of float
        A unit vector: the contour's plane's normal, or the offset's own
        direction for a contour without a plane.
    near, far : float
        In millimetres, ``near`` at most 0 and ``far`` at least 0, so that
        the span holds the Contour Data as written, and not both 0.
    """

    direction: tuple[float, float, float]
    near: float
    far: float

    def __repr__(self) -> str:
        return "Slab()"


@dataclasses.dataclass(frozen=True, repr=False)
class SlabValues:
    """A contour's Contour Slab Thickness and Contour Offset Vector, 0 and
    (0, 0, 0) where absent or empty.

    Its ``repr`` shows nothing of it.
    """

    thickness: float
    offset: tuple[float, float, float]

    def __repr__(self) -> str:
        return "SlabValues()"


def given(contour: pydicom.Dataset) -> bool:
    """Whether a contour gives Contour Slab Thickness or Contour Offset
    Vector a value."""
    return any(
        keyword in contour and contour[keyword].value not in (None, "", [])
        for keyword in (THICKNESS, OFFSET)
    )


def slab_values(contour: pydicom.Dataset) -> SlabValues | None:
    """Return a contour's thickness and offset, or None where neither moves
    its points or gives them depth, as where both are absent, empty, or
    zero.

    Raises
    ------
    SlabRefused
        Where either cannot be read, has the wrong number of values, or a
        value that is not finite or is beyond :data:`FARTHEST`, or the
        thickness is negative.
    """
    try:
        with redacted_diagnostics():
            thickness = _values(contour, THICKNESS, 1)
            offset = _values(contour, OFFSET, 3)
    # pydicom raises many types for a value it cannot read, and a message can
    # quote it.
    except Exception:  # pylint: disable = broad-exception-caught
        raise SlabRefused() from None
    depth = 0.0 if thickness is None else thickness[0]
    moved = (0.0, 0.0, 0.0) if offset is None else (offset[0], offset[1], offset[2])
    if depth < 0:
        raise SlabRefused()
    if depth == 0 and not any(moved):
        return None
    return SlabValues(depth, moved)


def slab_of(values: SlabValues, points: np.ndarray) -> Slab:
    """Return the span that the points of a contour, or of contours in one
    plane, with these values, may lie along, as the module describes.

    Parameters
    ----------
    values : SlabValues
        The contour's thickness and offset.
    points : numpy.ndarray
        Its Contour Data, the x, y, and z of each point in rows, in
        millimetres, or those of each contour in its plane.

    Raises
    ------
    SlabRefused
        Where the span cannot be found, as the module describes.
    """
    depth = values.thickness
    moved = np.asarray(values.offset, dtype=float)
    normal = _normal(np.asarray(points, dtype=float).reshape(-1, 3))
    if normal is None:
        # Without a plane, an offset alone still moves the points along
        # itself, but a thickness has no direction.
        if depth > 0:
            raise SlabRefused()
        length = float(np.linalg.norm(moved))
        return Slab(_triple(moved / length), 0.0, length)
    along = float(moved @ normal)
    across = float(np.linalg.norm(moved - along * normal))
    if not math.isfinite(across) or across > COPLANAR:
        raise SlabRefused()
    return Slab(
        _triple(normal),
        min(0.0, along - depth / 2),
        max(0.0, along + depth / 2),
    )


def spread(points: np.ndarray, slab: Slab | None) -> np.ndarray:
    """Return a contour's points, and where it has a slab, those points
    moved to each end of its span, whose convex hull holds every point that
    the slab may cover."""
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if slab is None:
        return points
    direction = np.asarray(slab.direction)
    return np.concatenate(
        [points, points + slab.near * direction, points + slab.far * direction]
    )


def _values(
    contour: pydicom.Dataset, keyword: str, count: int
) -> tuple[float, ...] | None:
    """An attribute's ``count`` finite values within :data:`FARTHEST`, or
    None where it is absent or empty.

    Raises
    ------
    ValueError
        Where it has another number of values, or one is not finite or is
        beyond :data:`FARTHEST`.
    """
    if keyword not in contour:
        return None
    value = contour[keyword].value
    if value in (None, "", []):
        return None
    values = (
        tuple(float(each) for each in value)
        if isinstance(value, (list, tuple, pydicom.multival.MultiValue))
        else (float(value),)
    )
    if len(values) != count or not all(
        math.isfinite(each) and abs(each) <= FARTHEST for each in values
    ):
        raise ValueError("not finite numbers")
    return values


def _normal(points: np.ndarray) -> np.ndarray | None:
    """The unit normal of the plane that best fits a contour's points, or
    None where they lie on one line, or are fewer than three.

    Raises
    ------
    SlabRefused
        Where a point lies farther than :data:`COPLANAR` from that plane.
    """
    if len(points) < 3:
        return None
    centre = points.mean(axis=0)
    _, spread_, axes = np.linalg.svd(points - centre, full_matrices=False)
    if len(spread_) < 3 or not spread_[1] > 1e-9 * spread_[0]:
        return None
    normal = axes[2]
    farthest = float(np.max(np.abs((points - centre) @ normal)))
    if not math.isfinite(farthest) or farthest > COPLANAR:
        raise SlabRefused()
    return np.asarray(normal, dtype=float)


def _triple(vector: np.ndarray) -> tuple[float, float, float]:
    return (float(vector[0]), float(vector[1]), float(vector[2]))
