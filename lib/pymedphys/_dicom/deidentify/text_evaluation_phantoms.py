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

"""Synthetic backgrounds for the text detector's evaluation (D-056).

Each kind of phantom is drawn in millimetres and sampled at the matrix size
and pixel spacing asked for, so that the same anatomy appears at 512, 768,
and 1024 pixels, as scanners store it, and the detector's renderings, whose
structuring element scales with the frame, see it as they would a scan's.
They model what makes the detector mark anatomy as text on real scans: thin
bright and dark detail, such as trabecular bone, air cells, and the edges
of small structures, beside smooth regions and noise. No frame holds real
data; every value comes from a seeded generator.

``ct-thorax``
    An axial chest: body, lungs with vessels, a vertebra, a rib ring, and a
    couch, stored as Hounsfield units plus 1024 in 12 bits.
``ct-head``
    An axial head at the skull base: scalp, a skull of cortical and
    trabecular bone, brain, sinuses, mastoid air cells, and a couch.
``mr-head``
    A T1-weighted axial head: bright scalp fat, dark skull, grey and white
    matter, and dark CSF, with a smooth bias field and Rician noise.
``pet``
    A body with organs of higher uptake, Poisson noise, and a rescale slope,
    in 16 bits.
``projection``
    A radiograph such as an RT Image or a localiser: attenuation integrated
    through ellipsoids, ribs, and a spine, inside a collimated field, in 16
    bits.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Iterator

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from .text_evaluation_frames import EvaluationFrame, EvaluationRefused

COLLECTION = "synthetic"


@dataclasses.dataclass(frozen=True)
class Phantom:
    """A frame of one kind of phantom.

    Attributes
    ----------
    kind : str
        One of :data:`KINDS`.
    size : int
        Rows and columns.
    spacing : float
        Millimetres between pixels.
    """

    kind: str
    size: int
    spacing: float

    def __post_init__(self):
        if self.kind not in KINDS:
            raise EvaluationRefused("The phantom is not one of the known kinds.")
        if self.size < 32 or not math.isfinite(self.spacing) or self.spacing <= 0:
            raise EvaluationRefused(
                "A phantom needs at least 32 pixels a side and a positive spacing."
            )


def _grid(phantom: Phantom) -> tuple[np.ndarray, np.ndarray]:
    """Millimetres from the frame's centre, down the rows and along the
    columns, at each pixel's centre."""
    centre = (phantom.size - 1) / 2
    y, x = np.indices((phantom.size, phantom.size), dtype=np.float64)
    return (y - centre) * phantom.spacing, (x - centre) * phantom.spacing


def _ellipse(y, x, cy, cx, ry, rx) -> np.ndarray:
    return ((y - cy) / ry) ** 2 + ((x - cx) / rx) ** 2 < 1


def _texture(
    rng: np.random.Generator, shape: tuple[int, int], spacing: float, mm: float
) -> np.ndarray:
    """Gaussian noise smoothed over ``mm`` millimetres, scaled to unit
    deviation: the grain of trabecular bone or soft tissue."""
    noise = rng.standard_normal(shape)
    smoothed = scipy.ndimage.gaussian_filter(noise, sigma=max(0.5, mm / spacing))
    deviation = float(smoothed.std())
    return smoothed / deviation if deviation > 0 else smoothed


def _ct_thorax(phantom: Phantom, rng: np.random.Generator) -> np.ndarray:
    y, x = _grid(phantom)
    hu = np.full(y.shape, -1000.0)
    body = _ellipse(y, x, 0, 0, 120, 170)
    hu[body] = 40 + 8 * _texture(rng, y.shape, phantom.spacing, 3.0)[body]
    for side in (-1, 1):
        lung = _ellipse(y, x, -10, side * 65, 85, 50)
        hu[lung] = -850
        # Vessels: small bright dots, thinner towards the edge.
        for _ in range(40):
            cy = rng.uniform(-80, 60)
            cx = side * 65 + rng.uniform(-40, 40)
            radius = rng.uniform(0.8, 3.0)
            hu[_ellipse(y, x, cy, cx, radius, radius) & lung] = 30
    hu[_ellipse(y, x, 80, 0, 14, 14)] = 900
    hu[_ellipse(y, x, 80, 0, 9, 9)] = (
        250
        + 60 * _texture(rng, y.shape, phantom.spacing, 0.6)[_ellipse(y, x, 80, 0, 9, 9)]
    )
    ring = np.abs(np.hypot(y / 110, x / 160) - 1) < 0.02
    hu[ring & body] = 700
    hu[(y > 145) & (y < 152) & (np.abs(x) < 190)] = 200
    return hu + rng.normal(0, 12, hu.shape)


def _ct_head(phantom: Phantom, rng: np.random.Generator) -> np.ndarray:
    y, x = _grid(phantom)
    hu = np.full(y.shape, -1000.0)
    head = _ellipse(y, x, 0, 0, 95, 78)
    skull_outer = _ellipse(y, x, 0, 0, 89, 72)
    skull_inner = _ellipse(y, x, 0, 0, 82, 65)
    hu[head] = 20
    bone = skull_outer & ~skull_inner
    trabecular = _texture(rng, y.shape, phantom.spacing, 0.5)
    hu[bone] = np.where(trabecular[bone] > 0.3, 1100, 450)
    cortex = bone & ~_ellipse(y, x, 0, 0, 87, 70) | bone & _ellipse(y, x, 0, 0, 84, 67)
    hu[cortex] = 1400
    brain = skull_inner
    hu[brain] = 35 + 4 * _texture(rng, y.shape, phantom.spacing, 4.0)[brain]
    # Sinuses and the nasal cavity, anterior, with thin bony septa.
    for cy, cx, ry, rx in ((-70, -18, 10, 12), (-70, 18, 10, 12), (-82, 0, 8, 6)):
        cavity = _ellipse(y, x, cy, cx, ry, rx)
        hu[cavity] = -950
        hu[cavity & (np.abs(x - cx) < 0.6)] = 600
    # Mastoid air cells: a bony block posterolaterally on each side,
    # honeycombed with small cells of air.
    for side in (-1, 1):
        block = _ellipse(y, x, 45, side * 62, 16, 12)
        hu[block] = 900
        for _ in range(45):
            radius = rng.uniform(0.6, 2.5)
            cy = 45 + rng.uniform(-14, 14)
            cx = side * 62 + rng.uniform(-10, 10)
            hu[_ellipse(y, x, cy, cx, radius, radius) & block] = -900
    hu[(y > 100) & (y < 106) & (np.abs(x) < 120)] = 200
    return hu + rng.normal(0, 6, hu.shape)


def _mr_head(phantom: Phantom, rng: np.random.Generator) -> np.ndarray:
    y, x = _grid(phantom)
    signal = np.zeros(y.shape)
    head = _ellipse(y, x, 0, 0, 95, 78)
    signal[head] = 900  # scalp fat
    signal[_ellipse(y, x, 0, 0, 90, 73)] = 60  # skull
    brain = _ellipse(y, x, 0, 0, 84, 67)
    grey = 450 + 25 * _texture(rng, y.shape, phantom.spacing, 3.0)
    signal[brain] = grey[brain]
    white = _ellipse(y, x, 0, 0, 62, 48) & (
        _texture(rng, y.shape, phantom.spacing, 6.0) > -0.8
    )
    signal[white & brain] = 620
    for cx in (-9, 9):  # lateral ventricles
        signal[_ellipse(y, x, -8, cx, 22, 5)] = 120
    bias = 1 + 0.25 * (x / 100) + 0.15 * (y / 100) ** 2
    noise = 18.0
    real = signal * bias + rng.normal(0, noise, y.shape)
    imaginary = rng.normal(0, noise, y.shape)
    return np.hypot(real, imaginary)


def _pet(phantom: Phantom, rng: np.random.Generator) -> np.ndarray:
    y, x = _grid(phantom)
    activity = np.zeros(y.shape)
    body = _ellipse(y, x, 0, 0, 120, 170)
    activity[body] = 1.0
    for cy, cx, ry, rx, uptake in (
        (-40, 30, 35, 30, 6.0),  # heart
        (30, -50, 45, 55, 2.5),  # liver
        (10, 70, 22, 12, 4.0),  # kidney
        (60, 0, 15, 15, 12.0),  # bladder
        (-20, -30, 4, 4, 15.0),  # a lesion
    ):
        activity[_ellipse(y, x, cy, cx, ry, rx)] = uptake
    activity = scipy.ndimage.gaussian_filter(activity, sigma=3.0 / phantom.spacing)
    counts = rng.poisson(activity * 40.0).astype(np.float64)
    return counts


def _projection(phantom: Phantom, rng: np.random.Generator) -> np.ndarray:
    y, x = _grid(phantom)
    path = np.zeros(y.shape)
    for cy, cx, ry, rx, mu in (
        (0, 0, 180, 140, 0.02),  # body
        (-20, -60, 110, 50, -0.012),  # lungs
        (-20, 60, 110, 50, -0.012),
        (40, 10, 45, 40, 0.006),  # heart
    ):
        inside = np.clip(1 - ((y - cy) / ry) ** 2 - ((x - cx) / rx) ** 2, 0, None)
        path += 2 * rx * np.sqrt(inside) * mu
    spine = np.abs(x) < 18
    path[spine] += (0.6 + 0.1 * np.sin(y / 9.0))[spine]
    for row in range(-150, 120, 24):  # ribs
        rib = (np.abs(y - row - 0.002 * x**2) < 3.5) & _ellipse(y, x, 0, 0, 175, 135)
        path[rib] += 0.25
    path += 0.02 * _texture(rng, y.shape, phantom.spacing, 2.0)
    intensity = np.exp(-path)
    field = (np.abs(y) < 160) & (np.abs(x) < 150)
    image = np.where(field, 40000 * intensity, 2500)
    return image + rng.normal(0, 60, y.shape)


@dataclasses.dataclass(frozen=True)
class _Kind:
    draw: Callable[[Phantom, np.random.Generator], np.ndarray]
    iod: str
    modality: str
    bits: int
    slope: float
    intercept: float
    stored: Callable[[np.ndarray], np.ndarray]


def _offset(value: float) -> Callable[[np.ndarray], np.ndarray]:
    return lambda values: values + value


def _scaled(value: float) -> Callable[[np.ndarray], np.ndarray]:
    return lambda values: values * value


_KINDS: dict[str, _Kind] = {
    "ct-thorax": _Kind(
        _ct_thorax, "CT Image Storage", "CT", 12, 1.0, -1024.0, _offset(1024)
    ),
    "ct-head": _Kind(
        _ct_head, "CT Image Storage", "CT", 12, 1.0, -1024.0, _offset(1024)
    ),
    "mr-head": _Kind(_mr_head, "MR Image Storage", "MR", 12, 1.0, 0.0, _offset(0)),
    "pet": _Kind(
        _pet,
        "Positron Emission Tomography Image Storage",
        "PT",
        16,
        0.25,
        0.0,
        _scaled(4.0),
    ),
    "projection": _Kind(
        _projection, "RT Image Storage", "RTIMAGE", 16, 1.0, 0.0, _offset(0)
    ),
}
KINDS = tuple(_KINDS)


def phantom_frame(
    phantom: Phantom, rng: np.random.Generator, *, case: str, number: int = 0
) -> EvaluationFrame:
    """Draw one frame of a phantom as stored values.

    Parameters
    ----------
    phantom : Phantom
    rng : numpy.random.Generator
        Draws its texture and noise.
    case : str
        The case the frame belongs to, for the split.
    number : int
        Its frame number within the case.
    """
    kind = _KINDS[phantom.kind]
    high = (1 << kind.bits) - 1
    stored = np.clip(np.rint(kind.stored(kind.draw(phantom, rng))), 0, high)
    return EvaluationFrame(
        stored=stored.astype(np.uint16),
        collection=COLLECTION,
        case=case,
        iod=kind.iod,
        modality=kind.modality,
        pixel_spacing=float(phantom.spacing),
        slope=kind.slope,
        intercept=kind.intercept,
        stored_range=(0, high),
        photometric="MONOCHROME2",
        number=number,
        background=phantom.kind,
    )


@dataclasses.dataclass(frozen=True)
class PhantomCase:
    """A case of synthetic frames: ``frames`` frames of one phantom, each
    with its own noise and texture, from a generator seeded by ``seed``.

    It gives its frames as :class:`~.text_evaluation.CaseSource` asks, so
    that synthetic cases run through the evaluation as a collection's do.
    """

    phantom: Phantom
    seed: int
    frames: int = 1

    @property
    def collection(self) -> str:
        return COLLECTION

    @property
    def case(self) -> str:
        return f"{self.phantom.kind}-{self.phantom.size}-{self.phantom.spacing:g}-{self.seed}"

    def read(self) -> Iterator[EvaluationFrame]:
        rng = np.random.default_rng(self.seed)
        for number in range(self.frames):
            yield phantom_frame(self.phantom, rng, case=self.case, number=number)


def phantom_cases(
    kinds: tuple[str, ...] = KINDS,
    sizes: tuple[int, ...] = (512, 768, 1024),
    fields_of_view: tuple[float, ...] = (250.0, 400.0),
    seeds: tuple[int, ...] = (0,),
    frames: int = 1,
) -> tuple[PhantomCase, ...]:
    """Every combination of kind, size, field of view in millimetres, and
    seed, as cases, in that order. A field of view over a size gives the
    spacing, so that the same field is sampled more finely at 1024 pixels,
    as scanners do."""
    return tuple(
        PhantomCase(Phantom(kind, size, field / size), seed, frames)
        for kind in kinds
        for size in sizes
        for field in fields_of_view
        for seed in seeds
    )
