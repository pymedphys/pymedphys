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

"""Find burned-in text in image frames, to be blacked out and reviewed.

The Clean Pixel Data Option (PS3.15 E.3.1) removes burned-in information
from the pixel data. Its Note 2 allows "the most conservative approach of
removing any and all burned in text", so :class:`TextDetector` proposes a box
around every region that looks like text, whatever it says, and reads none.
It is an aid to the review that the option requires, not a guarantee: faint,
small, or noisy text can be missed, and a reviewer sees every frame.

Network
    PaddleOCR's PP-OCRv6 small text detection model, a Differentiable
    Binarization network, which gives the probability that each pixel belongs
    to text. :data:`PP_OCRV6_DET_SMALL` pins it by SHA-256. PyMedPhys does
    not include it: :func:`model_bytes` takes it from the RapidOCR 3.10.0
    wheel on PyPI, itself pinned by SHA-256, and caches the wheel in the
    PyMedPhys data directory, as :mod:`pymedphys._nomenclature.tg263_published`
    does the TG-263 spreadsheet. The wheel's ``MODEL_LICENSES.md`` gives the
    weights as Apache-2.0, copyright Baidu and the PaddleOCR rights holders.
    ONNX Runtime runs it on the CPU, one thread, so that the same frame gives
    the same boxes however many processes run at once.

Renderings
    Stored values have more range than the network's 8-bit input, and one
    window rarely shows text against both air and tissue. Each frame is
    rendered three ways and the boxes of all three joined: its full stored
    range, and the white and black top-hats of the frame (detail brighter or
    darker than its surroundings and narrower than the structuring element),
    each windowed so that its noise, estimated from the median absolute
    deviation, stays dark and faint strokes reach full brightness.

Boxes
    Pixels with a probability above :attr:`DetectionParameters.threshold`
    form regions; a region whose mean probability reaches
    :attr:`DetectionParameters.box_threshold` gives a box, grown by the
    network's own offset (area times :attr:`DetectionParameters.unclip_ratio`
    over perimeter) and by :attr:`DetectionParameters.margin` pixels. Text
    lines are narrow, so a region whose shorter side exceeds
    :meth:`DetectionParameters.max_short_side` frame pixels, or that fills
    less than :attr:`DetectionParameters.min_fill` of its own box, is not
    text: on smooth anatomy the network otherwise marks whole organs.

ONNX Runtime records telemetry and sends it to Microsoft unless the
environment variable ``ORT_DISABLE_TELEMETRY`` is ``1`` when it is first
imported; its ``disable_telemetry_events()`` does not stop the first event,
which carries the interpreter's path. This module sets the variable before it
imports ONNX Runtime, and refuses to run with an ONNX Runtime that anything
else imported, since it cannot tell whether the variable was set then. The
variable governs ONNX Runtime's 1DS telemetry, which
its official wheels use on Linux and macOS from 1.29 and on Windows from
1.31. Earlier official Windows wheels trace through ETW instead, which
ignores it, as do Windows builds made for Windows apps and components, so on
Windows the detector runs only the official ``onnxruntime`` distribution at
1.31 or later, and checks that before importing it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.metadata
import io
import os
import pathlib
import posixpath
import re
import sys
import urllib.parse
import zipfile
from collections.abc import Callable, Mapping
from typing import Any

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from pymedphys._data.download import (
    download_lock,
    download_with_progress,
    get_data_dir,
)

EXTRA = "text-detection"
CACHE_DIRECTORY = "text-detection"
TELEMETRY_VARIABLE = "ORT_DISABLE_TELEMETRY"
# The first official Windows wheel whose telemetry TELEMETRY_VARIABLE turns
# off: before it, those wheels traced through ETW, which ignores it.
WINDOWS_MINIMUM_VERSION = (1, 31)

_SHA256 = re.compile(r"[0-9a-f]{64}")

Download = Callable[[str, pathlib.Path], None]


class TextDetectionError(Exception):
    """The detector cannot run: its model or runtime is missing or wrong."""


@dataclasses.dataclass(frozen=True)
class PinnedModel:
    """A detection model inside a wheel published on PyPI.

    Attributes
    ----------
    url : str
        The wheel's URL on PyPI, over HTTPS.
    sha256 : str
        The SHA-256 of the wheel's bytes.
    member : str
        The model's path inside the wheel.
    member_sha256 : str
        The SHA-256 of the model's bytes.
    """

    url: str
    sha256: str
    member: str
    member_sha256: str

    def __post_init__(self):
        for field in ("sha256", "member_sha256"):
            if not _SHA256.fullmatch(getattr(self, field)):
                raise ValueError(f"{field} must be 64 lowercase hexadecimal digits")
        parts = urllib.parse.urlsplit(self.url)
        if parts.scheme != "https" or not posixpath.basename(parts.path):
            raise ValueError("url must be an https URL that names a file")

    @property
    def file(self) -> str:
        """The wheel's file name, as the last part of its URL."""
        return posixpath.basename(urllib.parse.urlsplit(self.url).path)


PP_OCRV6_DET_SMALL = PinnedModel(
    url=(
        "https://files.pythonhosted.org/packages/59/07/"
        "203065283bba0c5e9c10af3602dc25ab3e59ee54dc2d1d22c8faeabf5ed8/"
        "rapidocr-3.10.0-py3-none-any.whl"
    ),
    sha256="2fc34e26cd0f48514804a94f8832283039c7334076bff60768b1fed9ad068050",
    member="rapidocr/models/PP-OCRv6_det_small.onnx",
    member_sha256="090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
)


def model_bytes(
    model: PinnedModel | None = None, *, download: Download | None = None
) -> bytes:
    """Return the pinned model's bytes, downloading its wheel if needed.

    Parameters
    ----------
    model : PinnedModel, optional
        Defaults to :data:`PP_OCRV6_DET_SMALL`.
    download : callable, optional
        Writes the file at a URL to a path. Defaults to PyMedPhys's
        downloader, which retries transient failures.

    Raises
    ------
    TextDetectionError
        If the downloaded wheel does not have its pinned SHA-256, which
        removes it, or the model in it does not have its own.
    OSError
        If the wheel cannot be downloaded or written.
    """
    model = PP_OCRV6_DET_SMALL if model is None else model
    path: pathlib.Path = get_data_dir() / CACHE_DIRECTORY / model.file
    path.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(path):
        if not (path.exists() and _sha256(path.read_bytes()) == model.sha256):
            # Download beside the cache, and move the file into place only
            # once it has the pinned SHA-256, so the cache never holds a
            # file that does not match.
            partial = path.with_name(f".{path.name}.download")
            try:
                (download_with_progress if download is None else download)(
                    model.url, partial
                )
                if _sha256(partial.read_bytes()) != model.sha256:
                    raise TextDetectionError(
                        f"the file downloaded from {model.url} does not have "
                        f"the pinned SHA-256 {model.sha256}"
                    )
                os.replace(partial, path)
            finally:
                partial.unlink(missing_ok=True)
        data = path.read_bytes()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as wheel:
            content = wheel.read(model.member)
    except (KeyError, zipfile.BadZipFile):
        raise TextDetectionError(f"{model.file} does not hold {model.member}") from None
    if _sha256(content) != model.member_sha256:
        raise TextDetectionError(
            f"{model.member} does not have the pinned SHA-256 {model.member_sha256}"
        )
    return content


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclasses.dataclass(frozen=True)
class DetectionParameters:
    """Settings of detection, which change what is found.

    Attributes
    ----------
    limit_side : int
        The shorter side of the network's input is scaled up to at least
        this many pixels. Larger finds faint small text more often, and marks
        more anatomy as text.
    max_side : int
        The longer side of the network's input is scaled down to at most this
        many pixels.
    threshold : float
        Probability above which a pixel belongs to a text region.
    box_threshold : float
        Mean probability that a region needs to give a box.
    unclip_ratio : float
        Grows each box by its region's area times this ratio over its
        perimeter, the network's offset from the text's core to its edge.
    margin : int
        Further frame pixels added to every side of each box.
    min_short_side : int
        The narrowest region, in the network's pixels, that gives a box.
    short_side_pixels : int
        A region whose shorter side, in frame pixels, exceeds both this and
        ``short_side_fraction`` of the frame's longer side is not text.
    short_side_fraction : float
        See ``short_side_pixels``.
    min_fill : float
        A region that fills less than this fraction of its own box is not
        text.
    hat_pixels : int
        The smallest side of the top-hats' square structuring element.
    hat_fraction : float
        The structuring element's side as a fraction of the frame's longer
        side, where that is larger than ``hat_pixels``.
    hat_noise_multiple : float
        Each top-hat is windowed from zero to this many robust standard
        deviations of its noise.
    """

    limit_side: int = 736
    max_side: int = 2560
    threshold: float = 0.3
    box_threshold: float = 0.5
    unclip_ratio: float = 1.6
    margin: int = 2
    min_short_side: int = 2
    short_side_pixels: int = 48
    short_side_fraction: float = 0.08
    min_fill: float = 0.3
    hat_pixels: int = 15
    hat_fraction: float = 0.012
    hat_noise_multiple: float = 20.0

    def max_short_side(self, frame_shape: tuple[int, int]) -> float:
        """The widest a text region may be in a frame of this shape."""
        return max(self.short_side_pixels, self.short_side_fraction * max(frame_shape))

    def hat_size(self, frame_shape: tuple[int, int]) -> int:
        """The side of the top-hats' structuring element, always odd."""
        return max(self.hat_pixels, round(self.hat_fraction * max(frame_shape))) | 1


@dataclasses.dataclass(frozen=True, order=True)
class TextBox:
    """A region to black out: rows ``top`` to ``bottom`` and columns ``left``
    to ``right`` of a frame, each end excluded."""

    top: int
    left: int
    bottom: int
    right: int

    def __post_init__(self):
        if not (0 <= self.top < self.bottom and 0 <= self.left < self.right):
            raise ValueError("a box must have rows and columns")


RENDERINGS = ("full-range", "white-top-hat", "black-top-hat")


@dataclasses.dataclass(frozen=True)
class Detection:
    """A box that one rendering of a frame gives.

    Attributes
    ----------
    box : TextBox
    rendering : str
        One of :data:`RENDERINGS`.
    mean_probability : float
        The mean probability of the box's region, which reaches
        :attr:`DetectionParameters.box_threshold`.
    """

    box: TextBox
    rendering: str
    mean_probability: float


class TextDetector:
    """Propose boxes around burned-in text in frames.

    Parameters
    ----------
    model : bytes, optional
        The ONNX model. Defaults to :func:`model_bytes`, which downloads it.
    parameters : DetectionParameters, optional

    Raises
    ------
    TextDetectionError
        Where ONNX Runtime is not installed, was imported without telemetry
        disabled, or cannot load the model.
    """

    def __init__(
        self,
        model: bytes | None = None,
        parameters: DetectionParameters | None = None,
    ):
        self._parameters = DetectionParameters() if parameters is None else parameters
        content = model_bytes() if model is None else model
        self._model_sha256 = _sha256(content)
        self._session = _session(content)
        self._input = self._session.get_inputs()[0].name

    @property
    def parameters(self) -> DetectionParameters:
        """The settings of detection, fixed when the detector is made."""
        return self._parameters

    @property
    def model_sha256(self) -> str:
        """The SHA-256 of the model that runs, fixed when the detector is made."""
        return self._model_sha256

    @property
    def method(self) -> Mapping[str, object]:
        """What decides the boxes: the model, the runtime, and the parameters.

        The runtime is ONNX Runtime's version and the distributions that
        install it, since ``onnxruntime`` and ``onnxruntime-gpu`` give the
        same version, and the versions of NumPy and SciPy, which scale,
        render, and box every frame. It is an input to the method digest of
        a run under the Clean Pixel Data Option, as
        :func:`~pymedphys._dicom.deidentify.pixel_cleaning.finder_description`
        reads it.
        """
        return {
            "model_sha256": self.model_sha256,
            "onnxruntime": _onnxruntime().__version__,
            "onnxruntime_distributions": list(_installed_onnxruntime()[0]),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "parameters": dataclasses.asdict(self.parameters),
            "renderings": list(RENDERINGS),
        }

    def find(self, frame: np.ndarray) -> tuple[TextBox, ...]:
        """Return the boxes around text in one frame, sorted, each once.

        Parameters
        ----------
        frame : numpy.ndarray
            Stored values of one frame: rows by columns for monochrome, or
            rows by columns by 3 for RGB, which is searched by its luminance.
        """
        return tuple(sorted({each.box for each in self.detections(frame)}))

    def detections(self, frame: np.ndarray) -> tuple[Detection, ...]:
        """Return the boxes that each rendering of one frame gives, with
        their regions' mean probabilities, in the order of
        :data:`RENDERINGS`; :meth:`find` gives each of their boxes once.

        Parameters
        ----------
        frame : numpy.ndarray
            As :meth:`find` takes it.
        """
        values = _luminance(frame)
        found = []
        for rendering, image in zip(
            RENDERINGS, renderings(values, self.parameters), strict=True
        ):
            probability = self._probability(image)
            found += [
                Detection(box, rendering, mean)
                for box, mean in scored_boxes_from_probability(
                    probability, image.shape, self.parameters
                )
            ]
        return tuple(found)

    def _probability(self, image: np.ndarray) -> np.ndarray:
        parameters = self.parameters
        rows, columns = image.shape
        scale = max(1.0, parameters.limit_side / min(rows, columns))
        scale = min(scale, parameters.max_side / max(rows, columns))
        shape = (_multiple_of_32(rows * scale), _multiple_of_32(columns * scale))
        resized = _resized(image.astype(np.float32), shape)
        normalised = (resized / 255.0 - 0.5) / 0.5
        tensor = np.ascontiguousarray(
            np.broadcast_to(normalised, (1, 3) + shape), dtype=np.float32
        )
        (output,) = self._session.run(None, {self._input: tensor})
        return np.asarray(output[0, 0], dtype=np.float32)


def _multiple_of_32(length: float) -> int:
    return max(32, int(round(length / 32)) * 32)


def _resized(image: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    zoom = (shape[0] / image.shape[0], shape[1] / image.shape[1])
    resized = scipy.ndimage.zoom(image, zoom, order=1, mode="nearest", grid_mode=True)
    return np.asarray(resized[: shape[0], : shape[1]])


def _luminance(frame: np.ndarray) -> np.ndarray:
    values = np.asarray(frame)
    if values.ndim == 3 and values.shape[2] == 3:
        weights = np.array([0.299, 0.587, 0.114])
        return np.asarray(values.astype(np.float64) @ weights)
    if values.ndim != 2:
        raise ValueError("a frame must be rows by columns, or rows by columns by 3")
    return values.astype(np.float64)


def renderings(values: np.ndarray, parameters: DetectionParameters) -> list[np.ndarray]:
    """The 8-bit images of one frame that the network searches, in the order
    of :data:`RENDERINGS`."""
    values = np.asarray(values, dtype=np.float64)
    low, high = float(values.min()), float(values.max())
    if high <= low:
        return [np.zeros(values.shape, np.uint8) for _ in RENDERINGS]
    size = parameters.hat_size(values.shape)
    footprint = (size, size)
    white = values - scipy.ndimage.grey_opening(values, size=footprint)
    black = scipy.ndimage.grey_closing(values, size=footprint) - values
    return [
        _window(values, low, high),
        _hat(white, parameters.hat_noise_multiple),
        _hat(black, parameters.hat_noise_multiple),
    ]


def _hat(values: np.ndarray, multiple: float) -> np.ndarray:
    median = float(np.median(values))
    sigma = 1.4826 * float(np.median(np.abs(values - median)))
    if sigma > 0:
        return _window(values, 0.0, multiple * sigma)
    # Without noise, as in synthetic images, show the residue's whole range.
    high = float(values.max())
    if high > 0:
        return _window(values, 0.0, high)
    return np.zeros(values.shape, np.uint8)


def _window(values: np.ndarray, low: float, high: float) -> np.ndarray:
    scaled = (values - low) * (255.0 / (high - low))
    return np.clip(np.rint(scaled), 0, 255).astype(np.uint8)


def boxes_from_probability(
    probability: np.ndarray,
    frame_shape: tuple[int, int],
    parameters: DetectionParameters,
) -> list[TextBox]:
    """Turn the network's probability map into boxes in frame pixels."""
    return [
        box
        for box, _ in scored_boxes_from_probability(
            probability, frame_shape, parameters
        )
    ]


def scored_boxes_from_probability(
    probability: np.ndarray,
    frame_shape: tuple[int, int],
    parameters: DetectionParameters,
) -> list[tuple[TextBox, float]]:
    """Turn the network's probability map into boxes in frame pixels, each
    with its region's mean probability."""
    net_rows, net_columns = probability.shape
    row_scale = frame_shape[0] / net_rows
    column_scale = frame_shape[1] / net_columns
    ndimage = scipy.ndimage
    mask = ndimage.binary_dilation(
        probability > parameters.threshold, structure=np.ones((2, 2), bool)
    )
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), bool))
    if count == 0:
        return []
    indices = np.arange(1, count + 1)
    means = ndimage.mean(probability, labels, index=indices)
    sizes = ndimage.sum(mask, labels, index=indices)
    widest = parameters.max_short_side(frame_shape)
    boxes = []
    for region, (rows, columns) in enumerate(ndimage.find_objects(labels)):
        height = rows.stop - rows.start
        width = columns.stop - columns.start
        if min(height, width) < parameters.min_short_side:
            continue
        if means[region] < parameters.box_threshold:
            continue
        if min(height * row_scale, width * column_scale) > widest:
            continue
        if sizes[region] < parameters.min_fill * height * width:
            continue
        offset = height * width * parameters.unclip_ratio / (2 * (height + width))
        margin = parameters.margin
        top = (rows.start - offset) * row_scale - margin
        bottom = (rows.stop + offset) * row_scale + margin
        left = (columns.start - offset) * column_scale - margin
        right = (columns.stop + offset) * column_scale + margin
        box = TextBox(
            top=max(0, int(np.floor(top))),
            left=max(0, int(np.floor(left))),
            bottom=min(frame_shape[0], int(np.ceil(bottom))),
            right=min(frame_shape[1], int(np.ceil(right))),
        )
        boxes.append((box, float(means[region])))
    return boxes


def _installed_onnxruntime() -> tuple[tuple[str, ...], str | None]:
    """The distributions that install the ``onnxruntime`` module, and the
    version of the one named ``onnxruntime``, read without importing it."""
    distributions = tuple(
        sorted(set(importlib.metadata.packages_distributions().get("onnxruntime", ())))
    )
    if "onnxruntime" not in distributions:
        return distributions, None
    return distributions, importlib.metadata.version("onnxruntime")


def _runtime_problem(
    platform: str, distributions: tuple[str, ...], version: str | None
) -> str | None:
    """Why ``ORT_DISABLE_TELEMETRY`` may not turn off the installed ONNX
    Runtime's telemetry, or None where it does or nothing is installed.
    Elsewhere than Windows, official wheels before 1.29 have no telemetry,
    and later ones use 1DS, which the variable turns off."""
    if platform != "win32" or not distributions:
        return None
    if distributions != ("onnxruntime",):
        return (
            f"the onnxruntime module comes from {', '.join(distributions)}; on "
            "Windows only the official onnxruntime distribution is known to "
            f"turn its telemetry off with {TELEMETRY_VARIABLE}"
        )
    release = re.match(r"(\d+)\.(\d+)", version or "")
    if release is None or (
        tuple(int(part) for part in release.groups()) < WINDOWS_MINIMUM_VERSION
    ):
        minimum = ".".join(str(part) for part in WINDOWS_MINIMUM_VERSION)
        return (
            f"ONNX Runtime {version} traces through ETW on Windows, which "
            f"ignores {TELEMETRY_VARIABLE}; install onnxruntime {minimum} or later"
        )
    return None


# The ONNX Runtime module that _onnxruntime imported itself, with telemetry
# disabled. ONNX Runtime reads TELEMETRY_VARIABLE only as it initialises, so
# the variable's value now says nothing about a module imported elsewhere.
_IMPORTED: dict[str, Any] = {}


def _onnxruntime():
    """Import ONNX Runtime with its telemetry disabled.

    Raises
    ------
    TextDetectionError
        Where ONNX Runtime is not installed, was imported by something other
        than this function, which cannot tell whether ``ORT_DISABLE_TELEMETRY``
        was ``1`` then, or is a Windows build whose telemetry that variable
        does not turn off.
    """
    existing = sys.modules.get("onnxruntime")
    if existing is not None and existing is _IMPORTED.get("onnxruntime"):
        return existing
    problem = _runtime_problem(sys.platform, *_installed_onnxruntime())
    if problem is not None:
        raise TextDetectionError(problem)
    if existing is not None:
        raise TextDetectionError(
            "ONNX Runtime was imported before text detection could disable its "
            "telemetry, which it reads only on import; run text detection in a "
            "Python process that has not imported onnxruntime"
        )
    os.environ[TELEMETRY_VARIABLE] = "1"
    try:
        import onnxruntime  # pylint: disable = import-outside-toplevel
    except ImportError:
        raise TextDetectionError(
            f'text detection needs ONNX Runtime: install "pymedphys[{EXTRA}]"'
        ) from None
    _IMPORTED["onnxruntime"] = onnxruntime
    return onnxruntime


def _session(model: bytes):
    onnxruntime = _onnxruntime()
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
    options.log_severity_level = 3
    try:
        return onnxruntime.InferenceSession(
            model, sess_options=options, providers=["CPUExecutionProvider"]
        )
    except Exception:  # pylint: disable = broad-exception-caught
        # ONNX Runtime raises its own exception types, which differ between
        # versions; none quotes image data, but none is needed either.
        raise TextDetectionError("ONNX Runtime cannot load the model") from None
