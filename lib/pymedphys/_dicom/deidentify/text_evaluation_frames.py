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

"""Frames, and the text in them, for the text detector's evaluation (D-056).

An :class:`EvaluationFrame` is one frame of stored values, as a run under
the Clean Pixel Data Option gives it to the text detector, with what the
evaluation counts it by: its collection, IOD, modality, size, and spacing.
Its case names the series or volume it came from, to keep each case in one
part of the split and to cluster the uncertainty; the case is never
published. Its :class:`BurnedText` entries are the ground truth of text in
it: the coverage of each piece of text that a generator, an injection, or an
answer key's box put there.

Neither shows its values in its ``repr``: a frame of a real patient's scan
stays on the runner that read it, and only counts leave it.

Tissue and noise are estimated here for the injection, which places text
over tissue, in air, or across a body's edge at a contrast relative to the
noise, and for the measures, which count how much of a false positive lies
over tissue.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from .text_detection import TextBox

# Hounsfield units above which a CT's pixel is tissue rather than air, as in
# the Text Detector Check.
AIR_HU = -900.0
# A CT is any of these modalities with monochrome frames and a rescale to
# Hounsfield units.
CT_MODALITIES = frozenset({"CT"})


class EvaluationRefused(Exception):
    """A frame or plan that cannot be evaluated; the message quotes no
    value."""


@dataclasses.dataclass(frozen=True, repr=False)
class BurnedText:
    """One piece of text in a frame, with its ground truth.

    Attributes
    ----------
    top, left : int
        The frame pixel of the coverage's first row and column.
    coverage : numpy.ndarray
        The share of each pixel's area that the text's ink covers, from 0
        to 1, as floats: the text, and any outline or shadow drawn with it.
    height : float
        The text's cap height in frame pixels, which sets its zone.
    strata : mapping of str to str
        What the summary counts the text by, such as its font, contrast, and
        style; never its characters.
    """

    top: int
    left: int
    coverage: np.ndarray
    height: float
    strata: Mapping[str, str] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        if self.coverage.ndim != 2 or not self.coverage.size:
            raise EvaluationRefused("A text's coverage must be rows by columns.")
        if self.top < 0 or self.left < 0:
            raise EvaluationRefused("A text must start inside its frame.")

    def __repr__(self) -> str:
        return "BurnedText()"

    @property
    def extent(self) -> TextBox:
        """The rows and columns of the coverage's pixels that hold ink."""
        rows = np.flatnonzero(self.coverage.any(axis=1))
        columns = np.flatnonzero(self.coverage.any(axis=0))
        if not rows.size:
            raise EvaluationRefused("A text's coverage holds no ink.")
        return TextBox(
            self.top + int(rows[0]),
            self.left + int(columns[0]),
            self.top + int(rows[-1]) + 1,
            self.left + int(columns[-1]) + 1,
        )

    def zone(self, shape: tuple[int, int]) -> TextBox:
        """The extent grown on every side by the text's height or 8 pixels,
        whichever is more, and clipped to the frame: a region that meets it
        is taken to be the detector's box around this text, which grows
        with the text, rather than a false positive."""
        extent = self.extent
        margin = max(8, math.ceil(self.height))
        return TextBox(
            max(0, extent.top - margin),
            max(0, extent.left - margin),
            min(shape[0], extent.bottom + margin),
            min(shape[1], extent.right + margin),
        )

    def ink(self, shape: tuple[int, int], level: float) -> np.ndarray:
        """The frame's pixels whose coverage is more than ``level``."""
        mask = np.zeros(shape, bool)
        rows, columns = self.coverage.shape
        bottom = min(shape[0], self.top + rows)
        right = min(shape[1], self.left + columns)
        mask[self.top : bottom, self.left : right] = (
            self.coverage[: bottom - self.top, : right - self.left] > level
        )
        return mask


@dataclasses.dataclass(frozen=True, repr=False)
class EvaluationFrame:
    """One frame of stored values, and what the evaluation counts it by.

    Attributes
    ----------
    stored : numpy.ndarray
        Stored values, rows by columns, or rows by columns by 3 for RGB, as
        a run gives the text detector.
    collection : str
        The collection or generator it came from, such as ``"synthetic"``.
    case : str
        The case, series, or volume it came from; never published.
    iod : str
        The name of its SOP Class, or a name for a source that is not DICOM.
    modality : str
    pixel_spacing : float or None
        The larger spacing between its pixels, in millimetres, where known.
    slope, intercept : float
        Its rescale to the modality's units (Hounsfield units for a CT).
    stored_range : tuple of int
        The least and greatest stored value that its Pixel Data can hold.
    photometric : str
        Its photometric interpretation.
    number : int
        Its frame number within its case, from 0, to seed its injection.
    background : str or None
        For a synthetic frame, the kind of phantom.
    texts : tuple of BurnedText
        The text in it, with its ground truth; none for a frame without text.
    """

    stored: np.ndarray
    collection: str
    case: str
    iod: str
    modality: str
    pixel_spacing: float | None = None
    slope: float = 1.0
    intercept: float = 0.0
    stored_range: tuple[int, int] = (0, 4095)
    photometric: str = "MONOCHROME2"
    number: int = 0
    background: str | None = None
    texts: tuple[BurnedText, ...] = ()

    def __post_init__(self):
        stored = np.asarray(self.stored)
        rgb = stored.ndim == 3 and stored.shape[2] == 3
        if not (stored.ndim == 2 or rgb) or min(stored.shape[:2]) < 1:
            raise EvaluationRefused(
                "A frame must be rows by columns, or rows by columns by 3."
            )
        if stored.dtype.kind not in "iu":
            raise EvaluationRefused("A frame must hold integer stored values.")
        if self.stored_range[0] >= self.stored_range[1]:
            raise EvaluationRefused("A frame's stored range must not be empty.")
        if self.pixel_spacing is not None and not (
            math.isfinite(self.pixel_spacing) and self.pixel_spacing > 0
        ):
            raise EvaluationRefused("A pixel spacing must be a positive number.")
        if not (math.isfinite(self.slope) and self.slope != 0):
            raise EvaluationRefused("A rescale slope must be a non-zero number.")

    def __repr__(self) -> str:
        return "EvaluationFrame()"

    @property
    def shape(self) -> tuple[int, int]:
        """The frame's rows and columns."""
        return int(self.stored.shape[0]), int(self.stored.shape[1])

    @property
    def rgb(self) -> bool:
        """Whether the frame is RGB."""
        return self.stored.ndim == 3

    @property
    def hounsfield(self) -> bool:
        """Whether the frame is a monochrome CT, whose rescaled values are
        Hounsfield units."""
        return self.modality in CT_MODALITIES and not self.rgb

    def luminance(self) -> np.ndarray:
        """The frame's stored values as floats, RGB by its luminance, as the
        detector searches it."""
        values = np.asarray(self.stored, dtype=np.float64)
        if self.rgb:
            return values @ np.array([0.299, 0.587, 0.114])
        return values

    def with_texts(
        self, stored: np.ndarray, texts: tuple[BurnedText, ...]
    ) -> EvaluationFrame:
        """A copy of the frame with other stored values and text."""
        return dataclasses.replace(self, stored=stored, texts=texts)


def tissue_mask(frame: EvaluationFrame) -> np.ndarray:
    """The frame's pixels over tissue.

    A CT's tissue is every pixel above :data:`AIR_HU`, lung included. Any
    other frame's is its body: the logarithm of one plus its luminance less
    its least, smoothed over 5 pixels, above Otsu's threshold, with holes
    filled and specks of under 0.1% of the frame removed. A flat frame has
    no tissue. For a projection, such as an RT Image, whose open field is
    brighter than the body, this "body" may be the open field: its tissue
    counts are a proxy.
    """
    values = frame.luminance()
    if frame.hounsfield:
        return values * frame.slope + frame.intercept > AIR_HU
    # On a logarithmic scale, so that a body of low signal, such as a PET's,
    # separates from air before organs of high signal do from the body.
    logarithm = np.log1p(values - values.min())
    smoothed = scipy.ndimage.uniform_filter(logarithm, size=5, mode="nearest")
    threshold = otsu_threshold(smoothed)
    if threshold is None:
        return np.zeros(frame.shape, bool)
    body = scipy.ndimage.binary_fill_holes(smoothed > threshold)
    labels, count = scipy.ndimage.label(body)
    if count == 0:
        return np.zeros(frame.shape, bool)
    sizes = scipy.ndimage.sum(body, labels, index=np.arange(1, count + 1))
    keep = np.flatnonzero(sizes >= 0.001 * body.size) + 1
    return np.isin(labels, keep)


def otsu_threshold(values: np.ndarray, bins: int = 256) -> float | None:
    """The threshold that best splits the values in two by Otsu's method,
    over a histogram of ``bins`` bins, or None where the values are all one."""
    low, high = float(values.min()), float(values.max())
    if high <= low:
        return None
    counts, edges = np.histogram(values, bins=bins, range=(low, high))
    centres = (edges[:-1] + edges[1:]) / 2
    weight = np.cumsum(counts).astype(np.float64)
    total = weight[-1]
    mean = np.cumsum(counts * centres)
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mean[-1] * weight / total - mean) ** 2 / (weight * (total - weight))
    between = np.nan_to_num(between[:-1], nan=-1.0, posinf=-1.0)
    return float(edges[int(np.argmax(between)) + 1])


# The robust deviation of white Gaussian noise less its 3 by 3 median, as a
# share of the noise's deviation, found by simulation.
_MEDIAN_RESIDUAL = 0.8625


def noise_sigma(values: np.ndarray, where: np.ndarray | None = None) -> float:
    """A robust estimate of the noise's standard deviation, in the values'
    units: 1.4826 times the median absolute deviation of the values less
    their 3 by 3 median, over ``where`` where it holds at least 100 pixels,
    otherwise over the frame, over 0.8625, so that it estimates white
    Gaussian noise's deviation. Edges and other structure barely change it.
    It is 0 for noise-free values."""
    values = np.asarray(values, dtype=np.float64)
    residual = values - scipy.ndimage.median_filter(values, size=3, mode="nearest")
    if where is not None and int(np.count_nonzero(where)) >= 100:
        residual = residual[where]
    residual = residual.ravel()
    median = float(np.median(residual))
    return 1.4826 * float(np.median(np.abs(residual - median))) / _MEDIAN_RESIDUAL
