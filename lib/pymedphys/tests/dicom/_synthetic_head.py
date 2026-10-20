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

"""An analytic head, in Hounsfield units, for the defacing tests.

Made of ellipsoids and spheres, so that it is nobody's head: skin and soft
tissue, a skull with a brain inside it, two bony orbits filled with fat,
an eye globe with a lens in each, and a nose below the eyes. Its centre is
at the origin of the patient's coordinates, x towards the patient's left,
y towards posterior, and z towards superior, in millimetres.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterator, Sequence

from pymedphys._imports import numpy as np

AIR = -1000.0
SOFT_TISSUE = 40.0
BRAIN = 35.0
BONE = 1200.0
FAT = -90.0
VITREOUS = 10.0
LENS = 120.0

GLOBE_RADIUS = 12.0
GLOBE_X = 32.0
GLOBE_Y = -66.0
GLOBE_Z = 20.0
SINUS_CENTRE = (0.0, -89.0, 62.0)
SINUS_AXES = (12.0, 3.5, 6.0)


@dataclasses.dataclass(frozen=True)
class Head:
    """Which parts the head has."""

    eyes: tuple[bool, bool] = (True, True)  # the patient's right, then left
    orbits: bool = True  # the bone around each orbit
    skull: bool = True
    shift: float = 0.0  # millimetres towards the patient's left
    # Degrees about the superior axis, turning the face towards the
    # patient's left.
    turn: float = 0.0
    # Whether the face is towards posterior, as when a prone patient is
    # recorded as supine.
    facing_back: bool = False
    # Whether the head is upside down, mirrored about the axial plane through
    # the origin, as when a feet-first patient is recorded as head first.
    upside_down: bool = False
    # Whether a bolus of soft-tissue density, 8 mm thick, lies over the
    # eyes and forehead.
    bolus: bool = False
    # Whether a frontal sinus, of air walled in by a thickened frontal bone
    # under a mound of soft tissue, lies ahead of the brain at the midline,
    # from 56 to 68 mm superior.
    sinus: bool = False
    noise: float = 10.0  # the standard deviation, in Hounsfield units
    seed: int = 0


def hounsfield(points: np.ndarray, head: Head = Head()) -> np.ndarray:
    """The head's value at each point, without noise.

    ``points`` hold x, y, and z along their last axis.
    """
    x, y, z = points[..., 0] - head.shift, points[..., 1], points[..., 2]
    if head.turn:
        angle = math.radians(head.turn)
        x, y = (
            x * math.cos(angle) + y * math.sin(angle),
            -x * math.sin(angle) + y * math.cos(angle),
        )
    if head.facing_back:
        y = -y
    if head.upside_down:
        z = -z
    values = np.full(x.shape, AIR)
    if head.bolus:
        over = _inside(x, y, z, (0, 0, 10), (83, 103, 138)) & (y < -40)
        values[over & (z > 0) & (z < 70)] = SOFT_TISSUE
    values[_inside(x, y, z, (0, 0, 10), (75, 95, 130))] = SOFT_TISSUE
    values[_inside(x, y, z, (0, -100, -15), (12, 22, 30))] = SOFT_TISSUE  # nose
    if head.sinus:
        values[_inside(x, y, z, SINUS_CENTRE, (23, 11, 13))] = SOFT_TISSUE
    if head.skull:
        values[_inside(x, y, z, (0, 0, 40), (68, 88, 85))] = BONE
    brain = _inside(x, y, z, (0, 0, 40), (62, 82, 79))
    values[brain] = BRAIN
    if head.sinus:
        values[_inside(x, y, z, SINUS_CENTRE, (20, 8, 10)) & ~brain] = BONE
        values[_inside(x, y, z, SINUS_CENTRE, SINUS_AXES)] = AIR
    for side, present in zip((-1, 1), head.eyes):
        centre = (side * GLOBE_X, GLOBE_Y + 6, GLOBE_Z)
        if head.orbits:
            wall = _inside(x, y, z, centre, (21, 21, 21)) & (y > GLOBE_Y - 4)
            values[wall] = BONE
        values[_inside(x, y, z, centre, (18, 18, 18))] = FAT
        if present:
            globe = (side * GLOBE_X, GLOBE_Y, GLOBE_Z)
            radius = GLOBE_RADIUS
            values[_inside(x, y, z, globe, (radius, radius, radius))] = VITREOUS
            lens = (side * GLOBE_X, GLOBE_Y - radius + 3, GLOBE_Z)
            values[_inside(x, y, z, lens, (4, 2, 4))] = LENS
    return values


@dataclasses.dataclass(frozen=True)
class Scan:
    """Where a scan's slices lie: one Image Orientation (Patient) for all."""

    orientation: tuple[float, float, float, float, float, float]
    positions: tuple[tuple[float, float, float], ...]  # of each slice's first pixel
    spacing: tuple[float, float]  # between rows, then between columns
    shape: tuple[int, int]

    def points(self, index: int) -> np.ndarray:
        """The x, y, and z of each pixel of a slice."""
        along_row = np.array(self.orientation[:3])
        down_column = np.array(self.orientation[3:])
        rows = np.arange(self.shape[0])[:, None, None] * self.spacing[0]
        columns = np.arange(self.shape[1])[None, :, None] * self.spacing[1]
        return (
            np.array(self.positions[index]) + columns * along_row + rows * down_column
        )

    def slices(self, *heads: Head) -> Iterator[np.ndarray]:
        """Each slice of the heads, or of one :class:`Head`, with the first's
        noise, as float32."""
        heads = heads or (Head(),)
        generator = np.random.default_rng(heads[0].seed)
        for index in range(len(self.positions)):
            points = self.points(index)
            values = np.full(points.shape[:-1], AIR)
            for head in heads:
                part = hounsfield(points, head)
                values = np.where(part > AIR, part, values)
            noise = generator.normal(0.0, heads[0].noise, values.shape)
            yield (values + noise).astype(np.float32)


def axial(
    *,
    spacing: float = 1.0,
    thickness: float = 2.5,
    extent: Sequence[tuple[float, float]] = ((-100, 100), (-130, 110), (-120, 120)),
    feet_first: bool = False,
    prone: bool = False,
) -> Scan:
    """An axial scan over ``extent``, the low and high of x, y, then z.

    Head first and supine by default: rows from anterior to posterior and
    columns from the patient's right to left, slices from inferior up.
    ``feet_first`` orders the slices from superior down. Image Orientation
    (Patient) is the one scanners commonly give for each patient position:
    (1, 0, 0, 0, 1, 0) head first supine, (-1, 0, 0, 0, -1, 0) head first
    prone, (-1, 0, 0, 0, 1, 0) feet first supine, and (1, 0, 0, 0, -1, 0)
    feet first prone.
    """
    (x_low, x_high), (y_low, y_high), (z_low, z_high) = extent
    columns = int(round((x_high - x_low) / spacing)) + 1
    rows = int(round((y_high - y_low) / spacing)) + 1
    heights = np.arange(z_low, z_high + 1e-9, thickness)
    if feet_first:
        heights = heights[::-1]
    across = -1.0 if prone != feet_first else 1.0
    down = -1.0 if prone else 1.0
    orientation = (across, 0.0, 0.0, 0.0, down, 0.0)
    corner = (x_low if across > 0 else x_high, y_low if down > 0 else y_high)
    positions = tuple((corner[0], corner[1], float(height)) for height in heights)
    return Scan(orientation, positions, (spacing, spacing), (rows, columns))


def tilted(
    *,
    degrees: float = 15.0,
    spacing: float = 1.0,
    thickness: float = 2.5,
    extent: Sequence[tuple[float, float]] = ((-100, 100), (-130, 110), (-120, 120)),
) -> Scan:
    """An axial scan with a gantry tilt: each slice turned about the
    patient's left-right axis by ``degrees``, and the slices stacked along
    the table, from inferior up, so not along the slices' normal."""
    (x_low, x_high), (y_low, y_high), (z_low, z_high) = extent
    angle = math.radians(degrees)
    columns = int(round((x_high - x_low) / spacing)) + 1
    rows = int(round((y_high - y_low) / spacing)) + 1
    orientation = (1.0, 0.0, 0.0, 0.0, math.cos(angle), -math.sin(angle))
    heights = np.arange(z_low, z_high + 1e-9, thickness)
    positions = tuple((x_low, y_low, float(height)) for height in heights)
    return Scan(orientation, positions, (spacing, spacing), (rows, columns))


def sagittal(
    *,
    spacing: float = 1.0,
    thickness: float = 2.0,
    extent: Sequence[tuple[float, float]] = ((-100, 100), (-130, 110), (-120, 120)),
) -> Scan:
    """A sagittal scan: rows from superior down, columns from anterior back,
    and slices from the patient's right to left."""
    (x_low, x_high), (y_low, y_high), (z_low, z_high) = extent
    columns = int(round((y_high - y_low) / spacing)) + 1
    rows = int(round((z_high - z_low) / spacing)) + 1
    orientation = (0.0, 1.0, 0.0, 0.0, 0.0, -1.0)
    widths = np.arange(x_low, x_high + 1e-9, thickness)
    positions = tuple((float(width), y_low, z_high) for width in widths)
    return Scan(orientation, positions, (spacing, spacing), (rows, columns))


def _inside(x, y, z, centre, semi_axes) -> np.ndarray:
    return (
        ((x - centre[0]) / semi_axes[0]) ** 2
        + ((y - centre[1]) / semi_axes[1]) ** 2
        + ((z - centre[2]) / semi_axes[2]) ** 2
    ) <= 1.0
