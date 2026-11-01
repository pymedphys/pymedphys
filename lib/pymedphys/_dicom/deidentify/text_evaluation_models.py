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

"""Text detection models for the evaluation alone, each through an adapter
(D-056).

The evaluation measures today's model and every model that passes vetting
through the same harness. A :class:`DetectionModel` is one model's adapter:
where its weights come from, pinned by SHA-256; the licences of its code and
its weights, each the Apache License 2.0 or one at least as permissive
(:data:`PERMISSIVE_LICENCES`); how a rendering becomes its input
(:class:`ModelInput`); and what its output is. A model's output is one of
two kinds:

probability maps (:class:`ProbabilityOutput`)
    the probability that each pixel is text, as a Differentiable
    Binarization network such as today's gives it. The harness keeps the maps
    and takes the post-processing grid
    (:func:`~.text_evaluation_detector.grid_boxes`) from one pass.
boxes (:class:`BoxDecoder`)
    boxes that the model's own post-processing gives, at one of its own
    settings (:class:`BoxPoint`). The harness measures each setting as a
    pass of its own (:class:`~.text_evaluation_detector.BoxModelDetector`).

Only the evaluation library makes a detector of these models: nothing in a
run or its command selects one, and the method that a summary records names
the model and its adapter, so that its boxes are never taken for a run's.
"""

from __future__ import annotations

import dataclasses
import math
import os
import pathlib
import posixpath
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, TypeAlias, runtime_checkable

from pymedphys._imports import numpy as np

from pymedphys._data.download import (
    download_lock,
    download_with_progress,
    get_data_dir,
)

from . import text_detection
from .text_detection import (
    PP_OCRV6_DET_SMALL,
    Download,
    PinnedModel,
    TextBox,
    TextDetectionError,
    _resized,
    _sha256,
)
from .text_evaluation_frames import EvaluationRefused

CACHE_DIRECTORY = "text-evaluation-models"
# SPDX identifiers of the licences that vetting admits, for a model's code
# and its weights alike: the Apache License 2.0 and those at least as
# permissive.
PERMISSIVE_LICENCES = frozenset(
    {"Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD"}
)
LAYOUTS = ("nchw", "nhwc")
ACTIVATIONS = ("none", "sigmoid")

_SHA256 = re.compile(r"[0-9a-f]{64}")

# A network's outputs, in its order. A string, so that the module imports
# without NumPy.
Outputs: TypeAlias = "Sequence[np.ndarray]"


@dataclasses.dataclass(frozen=True)
class ModelFile:
    """An ONNX model published as a file of its own.

    Attributes
    ----------
    url : str
        The file's URL, over HTTPS.
    sha256 : str
        The SHA-256 of its bytes.
    """

    url: str
    sha256: str

    def __post_init__(self):
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError("sha256 must be 64 lowercase hexadecimal digits")
        parts = urllib.parse.urlsplit(self.url)
        if parts.scheme != "https" or not posixpath.basename(parts.path):
            raise ValueError("url must be an https URL that names a file")

    @property
    def file(self) -> str:
        """The file's name, as the last part of its URL."""
        return posixpath.basename(urllib.parse.urlsplit(self.url).path)


@dataclasses.dataclass(frozen=True)
class ModelInput:
    """How an 8-bit rendering becomes a model's input.

    The rendering is resized, scaled to 0 to 1, and normalised channel by
    channel: less ``mean``, over ``deviation``. A rendering is grey, so
    every channel holds the same image before normalising, and the order of
    a model's colour channels matters only through its means and deviations.

    Attributes
    ----------
    channels : int
        1 or 3.
    mean, deviation : tuple of float
        One for each channel.
    layout : str
        ``"nchw"`` or ``"nhwc"``: the order of the input's axes.
    fixed_shape : tuple of int or None
        The rows and columns of a model that takes only one shape, each a
        multiple of 32; a rendering is resized to it whatever its proportions.
        None for a model that takes any multiple of 32.
    """

    channels: int = 3
    mean: tuple[float, ...] = (0.5, 0.5, 0.5)
    deviation: tuple[float, ...] = (0.5, 0.5, 0.5)
    layout: str = "nchw"
    fixed_shape: tuple[int, int] | None = None

    def __post_init__(self):
        if self.channels not in (1, 3):
            raise EvaluationRefused("A model takes one channel or three.")
        if not (len(self.mean) == len(self.deviation) == self.channels):
            raise EvaluationRefused("Each channel needs a mean and a deviation.")
        numbers = (*self.mean, *self.deviation)
        if not all(math.isfinite(each) for each in numbers) or min(self.deviation) <= 0:
            raise EvaluationRefused("A model's normalisation must be in range.")
        if self.layout not in LAYOUTS:
            raise EvaluationRefused("A model's layout must be a known one.")
        if self.fixed_shape is not None and not (
            len(self.fixed_shape) == 2
            and all(each >= 32 and each % 32 == 0 for each in self.fixed_shape)
        ):
            raise EvaluationRefused("A fixed shape must be two multiples of 32.")


@dataclasses.dataclass(frozen=True)
class ProbabilityOutput:
    """A model whose output is a map of the probability that each pixel is
    text, as today's model gives it.

    Attributes
    ----------
    output : int
        Which of the model's outputs holds the map.
    layout : str
        ``"nchw"`` or ``"nhwc"``: the order of that output's axes.
    channels : tuple of int
        The output's channels whose greatest value, pixel by pixel, is the
        map: one for a map of its own, or several, such as a region score and
        an affinity score.
    activation : str
        ``"none"`` for probabilities, or ``"sigmoid"`` for logits.
    stride : int
        The input's pixels to each of the map's along each side; the map is
        resized to the input's shape.
    """

    output: int = 0
    layout: str = "nchw"
    channels: tuple[int, ...] = (0,)
    activation: str = "none"
    stride: int = 1

    def __post_init__(self):
        if self.output < 0 or not self.channels or min(self.channels) < 0:
            raise EvaluationRefused("A map's output and channels must exist.")
        if self.layout not in LAYOUTS:
            raise EvaluationRefused("A map's layout must be a known one.")
        if self.activation not in ACTIVATIONS:
            raise EvaluationRefused("A map's activation must be a known one.")
        if self.stride < 1:
            raise EvaluationRefused("A map's stride must be at least 1.")

    def described(self) -> dict[str, object]:
        """The adapter, for the method."""
        return {"kind": "probability", **_plain(dataclasses.asdict(self))}


@runtime_checkable
class BoxPoint(Protocol):
    """One of a box model's own post-processing settings.

    Attributes
    ----------
    renderings : tuple of str
        The renderings of :data:`~.text_detection.RENDERINGS` whose boxes are
        joined.
    margin : int
        Frame pixels added to every side of each box.
    """

    renderings: tuple[str, ...]
    margin: int

    def described(self) -> dict[str, object]:
        """The setting, for the summary."""
        ...  # pylint: disable = unnecessary-ellipsis


@runtime_checkable
class BoxDecoder(Protocol):
    """A model's own post-processing, from its outputs to boxes.

    A decoder must be picklable, as a frozen dataclass of a module is, since
    workers make their own detectors.

    Attributes
    ----------
    name : str
        What the method calls it.
    point_type : type
        The class of its settings, each a :class:`BoxPoint`.
    """

    name: str
    point_type: type

    def feeds(self, point: Any) -> Mapping[str, np.ndarray]:
        """Further inputs of the network, by name, that the setting gives;
        empty where the setting does not reach the network, so that one
        pass of the network serves every such setting."""
        ...  # pylint: disable = unnecessary-ellipsis

    def boxes(
        self, outputs: Outputs, shape: tuple[int, int], point: Any
    ) -> Sequence[tuple[float, float, float, float]]:
        """The boxes, each top, left, bottom, and right in the pixels of the
        network's input of this shape, that the setting gives of the
        network's outputs."""
        ...  # pylint: disable = unnecessary-ellipsis

    def described(self) -> dict[str, object]:
        """The decoder, for the method."""
        ...  # pylint: disable = unnecessary-ellipsis


@dataclasses.dataclass(frozen=True)
class DetectionModel:
    """A model's adapter, as the module describes.

    Attributes
    ----------
    name : str
        What the summary calls the model.
    source : PinnedModel or ModelFile
        Where its weights come from, pinned by SHA-256.
    code_licence, weights_licence : str
        SPDX identifiers, each one of :data:`PERMISSIVE_LICENCES`.
    copyright : str
        The holders of the weights' copyright, as their licence names them.
    homepage : str
        The model's published home, over HTTPS.
    network_input : ModelInput
    output : ProbabilityOutput or BoxDecoder
    """

    name: str
    source: PinnedModel | ModelFile
    code_licence: str
    weights_licence: str
    copyright: str
    homepage: str
    network_input: ModelInput = ModelInput()
    output: ProbabilityOutput | BoxDecoder = ProbabilityOutput()

    def __post_init__(self):
        if not (self.name and self.copyright):
            raise EvaluationRefused("A model needs a name and its copyright.")
        if not isinstance(self.source, (PinnedModel, ModelFile)):
            raise EvaluationRefused("A model's weights must be pinned.")
        if not {self.code_licence, self.weights_licence} <= PERMISSIVE_LICENCES:
            raise EvaluationRefused(
                "A model's code and weights must each be under the Apache "
                "License 2.0 or a licence at least as permissive."
            )
        if urllib.parse.urlsplit(self.homepage).scheme != "https":
            raise EvaluationRefused("A model's home must be an https URL.")
        if not isinstance(self.output, (ProbabilityOutput, BoxDecoder)):
            raise EvaluationRefused("A model's output must be maps or a decoder.")

    @property
    def gives_maps(self) -> bool:
        """Whether the model gives probability maps, and so takes the
        post-processing grid."""
        return isinstance(self.output, ProbabilityOutput)

    @property
    def sha256(self) -> str:
        """The SHA-256 of the model's own bytes."""
        if isinstance(self.source, PinnedModel):
            return self.source.member_sha256
        return self.source.sha256

    def described(self) -> dict[str, object]:
        """The model and its adapter, for the method."""
        return {
            "name": self.name,
            "model_sha256": self.sha256,
            "url": self.source.url,
            "code_licence": self.code_licence,
            "weights_licence": self.weights_licence,
            "copyright": self.copyright,
            "homepage": self.homepage,
            "input": _plain(dataclasses.asdict(self.network_input)),
            "output": self.output.described(),
        }


# Today's model, as D-037 pins it, through its adapter: RapidOCR's wheel and
# PaddleOCR are under the Apache License 2.0, and the wheel's
# MODEL_LICENSES.md gives the weights as Apache-2.0.
PP_OCRV6_SMALL = DetectionModel(
    name="PP-OCRv6 small",
    source=PP_OCRV6_DET_SMALL,
    code_licence="Apache-2.0",
    weights_licence="Apache-2.0",
    copyright="Baidu and the PaddleOCR rights holders",
    homepage="https://github.com/PaddlePaddle/PaddleOCR",
)


def model_bytes(model: DetectionModel, *, download: Download | None = None) -> bytes:
    """Return a model's bytes, downloading them if they are not cached.

    A model in a wheel is taken as :func:`~.text_detection.model_bytes`
    takes today's. A model published as a file of its own is cached in the
    PyMedPhys data directory, and only once it has its pinned SHA-256.

    Parameters
    ----------
    model : DetectionModel
    download : callable, optional
        Writes the file at a URL to a path. Defaults to PyMedPhys's
        downloader, which retries transient failures.

    Raises
    ------
    TextDetectionError
        If the bytes downloaded do not have their pinned SHA-256.
    OSError
        If they cannot be downloaded or written.
    """
    source = model.source
    if isinstance(source, PinnedModel):
        return text_detection.model_bytes(source, download=download)
    path: pathlib.Path = get_data_dir() / CACHE_DIRECTORY / source.file
    path.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(path):
        if not (path.exists() and _sha256(path.read_bytes()) == source.sha256):
            partial = path.with_name(f".{path.name}.download")
            try:
                (download_with_progress if download is None else download)(
                    source.url, partial
                )
                if _sha256(partial.read_bytes()) != source.sha256:
                    raise TextDetectionError(
                        f"the file downloaded from {source.url} does not have "
                        f"the pinned SHA-256 {source.sha256}"
                    )
                os.replace(partial, path)
            finally:
                partial.unlink(missing_ok=True)
        return path.read_bytes()


def model_tensor(
    image: np.ndarray,
    shape: tuple[int, int],
    network_input: ModelInput,
    mean: float | None = None,
    deviation: float | None = None,
) -> np.ndarray:
    """A model's input for an 8-bit rendering: resized to ``shape``, scaled
    to 0 to 1, and normalised by the model's means and deviations, or by
    ``mean`` and ``deviation`` for every channel where they are given; for
    today's model, :func:`~.text_detection.network_tensor`'s tensor."""
    resized = _resized(image.astype(np.float32), shape) / 255.0
    channels = network_input.channels
    means = network_input.mean if mean is None else (mean,) * channels
    deviations = (
        network_input.deviation if deviation is None else (deviation,) * channels
    )
    planes = [(resized - means[index]) / deviations[index] for index in range(channels)]
    axis = 0 if network_input.layout == "nchw" else -1
    return np.ascontiguousarray(np.stack(planes, axis=axis)[np.newaxis], np.float32)


def probability_map(
    outputs: Outputs, output: ProbabilityOutput, shape: tuple[int, int]
) -> np.ndarray:
    """The probability map, on the input's grid of this shape, that a
    model's outputs hold.

    Raises
    ------
    EvaluationRefused
        Where the outputs do not hold a map of one batch, with the channels
        named, whose sides are the input's over the stride, rounded either
        way.
    """
    if output.output >= len(outputs):
        raise EvaluationRefused("The model has no such output.")
    values = np.asarray(outputs[output.output], np.float32)
    if values.ndim != 4 or values.shape[0] != 1:
        raise EvaluationRefused("A model's map must be one batch of channels.")
    planes = values[0] if output.layout == "nchw" else np.moveaxis(values[0], -1, 0)
    if max(output.channels) >= planes.shape[0]:
        raise EvaluationRefused("The model's map has no such channel.")
    probability = planes[list(output.channels)].max(axis=0)
    if output.activation == "sigmoid":
        probability = 1.0 / (1.0 + np.exp(-probability))
    stride = output.stride
    for side, length in zip(shape, probability.shape):
        if length not in (side // stride, -(-side // stride)):
            raise EvaluationRefused("The model's map is not the shape of its input.")
    if probability.shape != shape:
        probability = np.clip(_resized(probability, shape), 0.0, 1.0)
    return np.asarray(probability, np.float32)


def frame_boxes(
    boxes: Sequence[tuple[float, float, float, float]],
    shape: tuple[int, int],
    frame_shape: tuple[int, int],
    margin: int,
) -> tuple[TextBox, ...]:
    """Boxes on the network's input of this shape, scaled to the frame,
    grown by ``margin`` frame pixels, and clipped to it; each once, sorted,
    with empty ones dropped."""
    row_scale = frame_shape[0] / shape[0]
    column_scale = frame_shape[1] / shape[1]
    found = set()
    for top, left, bottom, right in boxes:
        if not all(math.isfinite(each) for each in (top, left, bottom, right)):
            raise EvaluationRefused("A decoder gave a box that is not finite.")
        sides = (
            max(0, math.floor(top * row_scale - margin)),
            max(0, math.floor(left * column_scale - margin)),
            min(frame_shape[0], math.ceil(bottom * row_scale + margin)),
            min(frame_shape[1], math.ceil(right * column_scale + margin)),
        )
        if sides[2] > sides[0] and sides[3] > sides[1]:
            found.add(TextBox(*sides))
    return tuple(sorted(found))


def _plain(value: object) -> dict[str, object]:
    def plain(each: object) -> object:
        if isinstance(each, Mapping):
            return {str(key): plain(item) for key, item in each.items()}
        if isinstance(each, (list, tuple)):
            return [plain(item) for item in each]
        return each

    result = plain(value)
    assert isinstance(result, dict)
    return result
