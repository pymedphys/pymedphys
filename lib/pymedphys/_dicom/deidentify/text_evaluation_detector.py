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

"""Detector variants and a post-processing grid, for evaluation only (D-056).

The text detector's network is the costly step of detection; turning its
probability maps into boxes is cheap. :class:`EvaluationDetector` runs the
network once for each rendering of a frame and keeps the maps
(:class:`~.text_detection.RenderedProbability`), and :func:`grid_boxes`
turns them into the boxes of every point of a grid of post-processing
settings (:class:`PostProcessing`), so that one pass gives the boxes of every
point. A point can join the boxes of fewer renderings than were computed,
so dropping a top-hat is a point of the grid too.

What changes the maps needs a pass of its own, as a
:class:`DetectorVariant`:

renderings (:class:`RenderingVariant`)
    which renderings to compute; whether each top-hat's noise is estimated
    over the whole frame, as a run does, or over its tissue
    (:func:`~.text_evaluation_frames.tissue_mask`); a floor on each
    rendering's window, in the modality's units (Hounsfield units for a
    CT), so that a frame of little contrast is not stretched to full
    brightness; and a structuring element sized in millimetres rather than
    as a share of the frame.
network input (:class:`InputVariant`)
    whether frames are scaled as a run scales them (``"limit-side"``), to a
    pixel size in millimetres (``"millimetres"``), or to a working size for
    their longer side (``"working-size"``), or down to at most one
    (``"longest-at-most"``), and a normalisation of the network's input in
    place of the model's own.
model
    any ONNX model of a Differentiable Binarization network, given as bytes,
    or a model's adapter (:class:`~.text_evaluation_models.DetectionModel`);
    the default is the pinned model that a run uses.

A model whose adapter gives boxes rather than probability maps has no maps
to keep, so :class:`BoxModelDetector` measures each of its own settings as a
pass of its own, reusing the network's outputs for every setting that does
not reach the network. Both detectors give the harness the boxes of each of
its points (:class:`MeasuredDetector`).

The default variant, with the default post-processing, gives the boxes that
a run's :class:`~.text_detection.TextDetector` gives. Every variant is
check-only: nothing in a run or its command makes an
:class:`EvaluationDetector`, and its description, which the method digest
would take, names its own class and variant, so that its boxes are never
taken for a run's.
"""

from __future__ import annotations

import dataclasses
import itertools
import math
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol, TypeAlias

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from .text_detection import (
    RENDERINGS,
    Detection,
    DetectionParameters,
    RenderedProbability,
    TextBox,
    _multiple_of_32,
    _onnxruntime,
    _session,
    _sha256,
    _window,
    model_bytes,
    network_shape,
)
from .text_evaluation_frames import (
    EvaluationFrame,
    EvaluationRefused,
    tissue_mask,
)
from .text_evaluation_models import (
    RESAMPLERS,
    BoxDecoder,
    DetectionModel,
    ModelInput,
    frame_boxes,
    model_tensor,
    probability_map,
)
from .text_evaluation_models import model_bytes as adapted_model_bytes

if TYPE_CHECKING:
    from collections.abc import Callable

SCALINGS = ("limit-side", "millimetres", "working-size", "longest-at-most")
NOISE_REGIONS = ("frame", "tissue")

# A network: the input tensor, one batch of three channels, to the
# probability map of its rows and columns. A string, so that the module
# imports without NumPy.
Network: TypeAlias = "Callable[[np.ndarray], np.ndarray]"


@dataclasses.dataclass(frozen=True)
class RenderingVariant:
    """How a frame is rendered for the network, as the module describes.

    Attributes
    ----------
    renderings : tuple of str
        Which of :data:`~.text_detection.RENDERINGS` to compute, in that
        order.
    noise : str
        ``"frame"`` or ``"tissue"``: where each top-hat's noise is
        estimated.
    window_floor : float or None
        The narrowest window, in the modality's units, of each rendering.
    hat_mm : float or None
        The side of the top-hats' structuring element in millimetres, for
        frames whose spacing is known; at least 3 pixels, always odd.
    """

    renderings: tuple[str, ...] = RENDERINGS
    noise: str = "frame"
    window_floor: float | None = None
    hat_mm: float | None = None

    def __post_init__(self):
        if not self.renderings or tuple(
            name for name in RENDERINGS if name in self.renderings
        ) != tuple(self.renderings):
            raise EvaluationRefused(
                "The renderings must be known ones, each once, in their order."
            )
        if self.noise not in NOISE_REGIONS:
            raise EvaluationRefused("The noise must be estimated over a known region.")
        for name in ("window_floor", "hat_mm"):
            value = getattr(self, name)
            if value is not None and not (math.isfinite(value) and value > 0):
                raise EvaluationRefused(f"The {name} must be positive.")


@dataclasses.dataclass(frozen=True)
class InputVariant:
    """How a rendering is scaled and normalised for the network.

    Attributes
    ----------
    scaling : str
        One of :data:`SCALINGS`. ``"millimetres"`` scales a frame whose
        spacing is unknown as ``"limit-side"`` does. Every scaling keeps the
        longer side to :attr:`~.text_detection.DetectionParameters.max_side`.
    millimetres : float
        The size of the network's pixel, for ``"millimetres"``.
    working_side : int
        The longer side of the network's input, for ``"working-size"``, or
        the most it may be, for ``"longest-at-most"``, which scales a
        rendering down to it but never up, as PaddleOCR's own pipeline
        does.
    mean, deviation : float or None
        Where given, the network's input is the rendering over 255, less
        ``mean``, over ``deviation``, in every channel, in place of the
        model's own normalisation (:class:`~.text_evaluation_models.ModelInput`),
        which for today's model is 0.5 and 0.5.
    resampler : str
        ``"harness"``, the harness's own bilinear resize, or ``"cv2"``, the
        resize and normalisation of PaddleOCR's own pipeline, which needs
        OpenCV (:func:`~.text_evaluation_models.model_tensor`).
    """

    scaling: str = "limit-side"
    millimetres: float = 1.0
    working_side: int = 736
    mean: float | None = None
    deviation: float | None = None
    resampler: str = "harness"

    def __post_init__(self):
        if self.scaling not in SCALINGS:
            raise EvaluationRefused("The scaling must be a known one.")
        if self.resampler not in RESAMPLERS:
            raise EvaluationRefused("The resampler must be a known one.")
        mean = 0.0 if self.mean is None else self.mean
        deviation = 1.0 if self.deviation is None else self.deviation
        if not (
            math.isfinite(self.millimetres)
            and self.millimetres > 0
            and self.working_side >= 32
            and math.isfinite(deviation)
            and deviation > 0
            and math.isfinite(mean)
        ):
            raise EvaluationRefused("The network input's settings must be in range.")


@dataclasses.dataclass(frozen=True)
class DetectorVariant:
    """A variant of the detector that changes its probability maps.

    Attributes
    ----------
    name : str
        What the summary calls it.
    parameters : DetectionParameters
        Its scaling (``limit_side``, ``max_side``) and top-hat settings
        (``hat_pixels``, ``hat_fraction``, ``hat_noise_multiple``), and the
        post-processing that its :meth:`EvaluationDetector.find` uses.
    rendering : RenderingVariant
    network_input : InputVariant
    """

    name: str = "default"
    parameters: DetectionParameters = DetectionParameters()
    rendering: RenderingVariant = RenderingVariant()
    network_input: InputVariant = InputVariant()

    def described(self) -> dict[str, object]:
        """The variant, for the summary and the method."""
        return _plain(dataclasses.asdict(self))


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


def variant_renderings(
    frame: EvaluationFrame, variant: DetectorVariant
) -> dict[str, np.ndarray]:
    """The 8-bit renderings of a frame that the variant computes, by name;
    the default variant's are those of
    :func:`~.text_detection.renderings`."""
    values = frame.luminance()
    parameters = variant.parameters
    options = variant.rendering
    names = options.renderings
    low, high = float(values.min()), float(values.max())
    if high <= low:
        return {name: np.zeros(values.shape, np.uint8) for name in names}
    floor = None
    if options.window_floor is not None:
        floor = options.window_floor / abs(frame.slope)
    found: dict[str, np.ndarray] = {}
    if "full-range" in names:
        found["full-range"] = _window(
            values, low, high if floor is None else max(high, low + floor)
        )
    hats = [name for name in names if name != "full-range"]
    if not hats:
        return found
    size = _hat_size(values.shape, frame.pixel_spacing, variant)
    footprint = (size, size)
    where = tissue_mask(frame) if options.noise == "tissue" else None
    if "white-top-hat" in hats:
        white = values - scipy.ndimage.grey_opening(values, size=footprint)
        found["white-top-hat"] = _hat(
            white, parameters.hat_noise_multiple, where, floor
        )
    if "black-top-hat" in hats:
        black = scipy.ndimage.grey_closing(values, size=footprint) - values
        found["black-top-hat"] = _hat(
            black, parameters.hat_noise_multiple, where, floor
        )
    return {name: found[name] for name in names}


def _hat_size(
    shape: tuple[int, ...], spacing: float | None, variant: DetectorVariant
) -> int:
    hat_mm = variant.rendering.hat_mm
    if hat_mm is None or spacing is None:
        return variant.parameters.hat_size((int(shape[0]), int(shape[1])))
    return max(3, round(hat_mm / spacing)) | 1


def _hat(
    values: np.ndarray, multiple: float, where: np.ndarray | None, floor: float | None
) -> np.ndarray:
    """A top-hat windowed from 0 to ``multiple`` robust deviations of its
    noise, as :func:`~.text_detection.renderings` windows it, with the noise
    over ``where`` where it holds 100 pixels or more, and the window no
    narrower than ``floor``."""
    sample = (
        values[where]
        if where is not None and np.count_nonzero(where) >= 100
        else values
    )
    median = float(np.median(sample))
    sigma = 1.4826 * float(np.median(np.abs(sample - median)))
    top = multiple * sigma if sigma > 0 else float(values.max())
    if floor is not None:
        top = max(top, floor)
    if top > 0:
        return _window(values, 0.0, top)
    return np.zeros(values.shape, np.uint8)


def input_shape(
    shape: tuple[int, ...],
    spacing: float | None,
    variant: DetectorVariant,
    fixed: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """The rows and columns of the network's input for a rendering of this
    shape, under the variant's scaling, or ``fixed`` for a model that takes
    only that shape."""
    if fixed is not None:
        return (int(fixed[0]), int(fixed[1]))
    parameters = variant.parameters
    options = variant.network_input
    if options.scaling == "limit-side" or (
        options.scaling == "millimetres" and spacing is None
    ):
        return network_shape(shape, parameters)
    rows, columns = int(shape[0]), int(shape[1])
    if options.scaling == "longest-at-most":
        return paddle_shape((rows, columns), options.working_side)
    if options.scaling == "millimetres":
        assert spacing is not None
        scale = spacing / options.millimetres
    else:
        scale = options.working_side / max(rows, columns)
    scale = min(scale, parameters.max_side / max(rows, columns))
    return (_multiple_of_32(rows * scale), _multiple_of_32(columns * scale))


# PaddleX's own limit on the longer side of a scaled image.
PADDLE_MAX_SIDE = 4000


def paddle_shape(shape: tuple[int, int], limit: int) -> tuple[int, int]:
    """The rows and columns that PaddleX's ``DetResizeForTest`` gives an
    image under ``limit_type`` "max": the longer side scaled down to at most
    ``limit``, never up; each side truncated to an integer, then rounded to
    a multiple of 32, at least 32. Read from PaddleX's
    ``text_detection/processors.py`` at commit
    4c968d30b9d0d4a693d9eaaef0881c20f8d7d0e0."""
    rows, columns = shape
    ratio = 1.0
    if max(rows, columns) > limit:
        ratio = float(limit) / (rows if rows > columns else columns)
    rows_scaled, columns_scaled = int(rows * ratio), int(columns * ratio)
    if max(rows_scaled, columns_scaled) > PADDLE_MAX_SIDE:
        ratio = float(PADDLE_MAX_SIDE) / max(rows_scaled, columns_scaled)
        rows_scaled = int(rows_scaled * ratio)
        columns_scaled = int(columns_scaled * ratio)
    return (
        max(int(round(rows_scaled / 32) * 32), 32),
        max(int(round(columns_scaled / 32) * 32), 32),
    )


class MeasuredDetector(Protocol):
    """What the harness measures: a detector that gives the boxes of each
    of its points for a frame, and the method that decides them."""

    @property
    def method(self) -> Mapping[str, object]:
        """What decides the boxes."""
        ...  # pylint: disable = unnecessary-ellipsis

    def boxes_of_points(
        self, frame: EvaluationFrame, points: Sequence[Any]
    ) -> list[tuple[TextBox, ...]]:
        """The boxes of each point, for one frame."""
        ...  # pylint: disable = unnecessary-ellipsis


def _onnx_network(content: bytes) -> Callable[..., list[np.ndarray]]:
    """Runs a model in ONNX Runtime, as a run does: its first input is the
    tensor, and further inputs are given by name."""
    session = _session(content)
    name = session.get_inputs()[0].name

    def run(tensor: np.ndarray, feeds: Mapping[str, np.ndarray] | None = None):
        return list(session.run(None, {name: tensor, **(feeds or {})}))

    return run


def _model_method(model: DetectionModel | None, content: bytes) -> dict[str, object]:
    if model is None:
        return {"model_sha256": _sha256(content)}
    return {"model_sha256": _sha256(content), "model": model.described()}


class EvaluationDetector:
    """The text detector under a variant, for evaluation alone.

    Parameters
    ----------
    variant : DetectorVariant, optional
    model : bytes or DetectionModel, optional
        The ONNX model of a Differentiable Binarization network, or the
        adapter of a model that gives probability maps. Defaults to the
        pinned model that a run uses.
    network : callable, optional
        Runs the network instead of ONNX Runtime, for tests: the input
        tensor to the probability map, or, with an adapter, to the model's
        outputs. It needs ``network_name``.
    network_name : str, optional
        What the method calls ``network``.

    Raises
    ------
    TextDetectionError
        As :class:`~.text_detection.TextDetector` raises it, or where the
        adapter's weights do not have their pinned SHA-256.
    EvaluationRefused
        For an adapter of a model that gives boxes, which
        :class:`BoxModelDetector` measures.
    """

    def __init__(
        self,
        variant: DetectorVariant | None = None,
        model: bytes | DetectionModel | None = None,
        *,
        network: Network | Callable[..., list[np.ndarray]] | None = None,
        network_name: str | None = None,
    ):
        self._variant = DetectorVariant() if variant is None else variant
        adapter = model if isinstance(model, DetectionModel) else None
        if adapter is not None and not adapter.gives_maps:
            raise EvaluationRefused(
                "A model that gives boxes is measured by a BoxModelDetector."
            )
        self._adapter = adapter
        self._input = ModelInput() if adapter is None else adapter.network_input
        if network is not None:
            if not network_name:
                raise EvaluationRefused("A network given for tests needs a name.")
            self._network = network
            self._model: dict[str, object] = {"network": network_name}
            if adapter is not None:
                self._model["model"] = adapter.described()
            return
        if adapter is not None:
            content = adapted_model_bytes(adapter)
        else:
            content = model_bytes() if model is None else model
            assert isinstance(content, bytes)
        run = _onnx_network(content)
        if adapter is None:
            self._network = lambda tensor: np.asarray(run(tensor)[0][0, 0], np.float32)
        else:
            self._network = run
        self._model = _model_method(adapter, content)

    @property
    def variant(self) -> DetectorVariant:
        """The variant, fixed when the detector is made."""
        return self._variant

    @property
    def parameters(self) -> DetectionParameters:
        """The variant's parameters."""
        return self._variant.parameters

    @property
    def method(self) -> Mapping[str, object]:
        """What decides the maps: the model or test network, the variant,
        and, for ONNX Runtime, its version."""
        method: dict[str, object] = {
            **self._model,
            "variant": self._variant.described(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        }
        if "model_sha256" in self._model:
            method["onnxruntime"] = _onnxruntime().__version__
        return method

    def probabilities(self, frame: EvaluationFrame) -> tuple[RenderedProbability, ...]:
        """The network's probability map of each rendering of the frame
        that the variant computes."""
        options = self._variant.network_input
        found = []
        for name, image in variant_renderings(frame, self._variant).items():
            shape = input_shape(
                image.shape,
                frame.pixel_spacing,
                self._variant,
                self._input.fixed_shape,
            )
            tensor = model_tensor(
                image,
                shape,
                self._input,
                options.mean,
                options.deviation,
                options.resampler,
            )
            if self._adapter is None:
                probability = np.asarray(self._network(tensor), dtype=np.float32)
            else:
                outputs = self._network(tensor)
                probability = probability_map(outputs, self._adapter.output, shape)
            if probability.shape != shape:
                raise EvaluationRefused(
                    "The network's map is not the shape of its input."
                )
            found.append(RenderedProbability(name, frame.shape, probability))
        return tuple(found)

    def boxes_of_points(
        self, frame: EvaluationFrame, points: Sequence[Any]
    ) -> list[tuple[TextBox, ...]]:
        """The boxes of each point of the post-processing grid, from one
        pass of the network (:func:`grid_boxes`)."""
        if not all(isinstance(point, PostProcessing) for point in points):
            raise EvaluationRefused("A model that gives maps takes the grid's points.")
        return grid_boxes(self.probabilities(frame), points)

    def detections(self, frame: np.ndarray) -> tuple[Detection, ...]:
        """The boxes of each rendering of a frame of stored values, under
        the variant's own post-processing, as
        :meth:`~.text_detection.TextDetector.detections` gives them."""
        maps = self.probabilities(_bare(frame))
        return tuple(
            Detection(box, each.rendering, mean)
            for each in maps
            for box, mean in _scored(
                _regions(each.probability, self.parameters.threshold),
                each,
                PostProcessing.of(self.parameters),
            )
        )

    def find(self, frame: np.ndarray) -> tuple[TextBox, ...]:
        """The boxes around text in a frame of stored values, each once,
        sorted, as :meth:`~.text_detection.TextDetector.find` gives them."""
        return tuple(sorted({each.box for each in self.detections(frame)}))


class BoxModelDetector:
    """A model whose adapter gives boxes, under a variant, for evaluation
    alone: each of the model's own settings is a point, measured as a pass
    of its own.

    The variant's renderings and network input apply as they do to
    :class:`EvaluationDetector`; its post-processing parameters do not,
    since the model's settings take their place.

    Parameters
    ----------
    model : DetectionModel
        An adapter whose output is a
        :class:`~.text_evaluation_models.BoxDecoder`.
    variant : DetectorVariant, optional
    network : callable, optional
        Runs the network instead of ONNX Runtime, for tests: the input
        tensor and further inputs by name to the model's outputs. It needs
        ``network_name``.
    network_name : str, optional

    Raises
    ------
    TextDetectionError
        Where the adapter's weights do not have their pinned SHA-256, or
        ONNX Runtime cannot run.
    EvaluationRefused
        For an adapter of a model that gives maps, which
        :class:`EvaluationDetector` measures with the grid.
    """

    def __init__(
        self,
        model: DetectionModel,
        variant: DetectorVariant | None = None,
        *,
        network: Callable[..., list[np.ndarray]] | None = None,
        network_name: str | None = None,
    ):
        if not isinstance(model.output, BoxDecoder) or model.gives_maps:
            raise EvaluationRefused(
                "A model that gives maps is measured by an EvaluationDetector."
            )
        self._adapter = model
        self._decoder: BoxDecoder = model.output
        self._variant = DetectorVariant() if variant is None else variant
        if network is not None:
            if not network_name:
                raise EvaluationRefused("A network given for tests needs a name.")
            self._network = network
            self._model: dict[str, object] = {
                "network": network_name,
                "model": model.described(),
            }
            return
        content = adapted_model_bytes(model)
        self._network = _onnx_network(content)
        self._model = _model_method(model, content)

    @property
    def variant(self) -> DetectorVariant:
        """The variant, fixed when the detector is made."""
        return self._variant

    @property
    def method(self) -> Mapping[str, object]:
        """What decides the boxes: the model and its adapter, or the test
        network, the variant, and, for ONNX Runtime, its version."""
        method: dict[str, object] = {
            **self._model,
            "variant": self._variant.described(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        }
        if "model_sha256" in self._model:
            method["onnxruntime"] = _onnxruntime().__version__
        return method

    def boxes_of_points(
        self, frame: EvaluationFrame, points: Sequence[Any]
    ) -> list[tuple[TextBox, ...]]:
        """The boxes of each of the model's settings, for one frame: for
        each, the boxes of the renderings it joins, each once, sorted.

        Raises
        ------
        EvaluationRefused
            For a point not of the decoder's settings, or one that joins a
            rendering that the variant does not compute.
        """
        if not all(isinstance(point, self._decoder.point_type) for point in points):
            raise EvaluationRefused("A point is not one of the model's settings.")
        renderings = variant_renderings(frame, self._variant)
        options = self._variant.network_input
        model_input = self._adapter.network_input
        outputs: dict[tuple[str, tuple], tuple[tuple[int, int], list[np.ndarray]]] = {}
        found = []
        for point in points:
            if not set(point.renderings) <= set(renderings):
                raise EvaluationRefused(
                    "A point joins a rendering that was not computed."
                )
            feeds = dict(self._decoder.feeds(point))
            boxes: set[TextBox] = set()
            for name in point.renderings:
                key = (name, _feeds_key(feeds))
                if key not in outputs:
                    image = renderings[name]
                    shape = input_shape(
                        image.shape,
                        frame.pixel_spacing,
                        self._variant,
                        model_input.fixed_shape,
                    )
                    tensor = model_tensor(
                        image,
                        shape,
                        model_input,
                        options.mean,
                        options.deviation,
                        options.resampler,
                    )
                    outputs[key] = (shape, list(self._network(tensor, feeds)))
                shape, network_outputs = outputs[key]
                decoded = self._decoder.boxes(network_outputs, shape, point)
                boxes.update(frame_boxes(decoded, shape, frame.shape, point.margin))
            found.append(tuple(sorted(boxes)))
        return found


def _feeds_key(feeds: Mapping[str, np.ndarray]) -> tuple:
    """A key that two settings share only where they give the network the
    same further inputs."""
    return tuple(
        (
            name,
            str(np.asarray(value).dtype),
            np.asarray(value).shape,
            np.asarray(value).tobytes(),
        )
        for name, value in sorted(feeds.items())
    )


def _bare(frame: np.ndarray) -> EvaluationFrame:
    """A frame of stored values with nothing known of it, as the Text
    Detector Check gives its slices."""
    values = np.asarray(frame)
    if values.dtype.kind == "f":
        values = np.rint(values).astype(np.int64)
    return EvaluationFrame(
        stored=values,
        collection="",
        case="",
        iod="",
        modality="",
        stored_range=(int(values.min()), int(values.max()) + 1),
    )


@dataclasses.dataclass(frozen=True)
class PostProcessing:
    """One point of the post-processing grid.

    The first eight attributes are those of
    :class:`~.text_detection.DetectionParameters`, with the same meanings
    and defaults.

    Attributes
    ----------
    renderings : tuple of str
        The renderings whose boxes are joined.
    min_elongation : float
        A region whose longer side over its shorter, in frame pixels, is
        less than this is not text, where its shorter side is at least
        ``elongation_from_side`` frame pixels: a shape filter for the
        nearly square regions that anatomy gives, which spares single
        letters smaller than that side. 1 keeps every region.
    elongation_from_side : float
        See ``min_elongation``.
    """

    threshold: float = DetectionParameters.threshold
    box_threshold: float = DetectionParameters.box_threshold
    unclip_ratio: float = DetectionParameters.unclip_ratio
    margin: int = DetectionParameters.margin
    min_short_side: int = DetectionParameters.min_short_side
    short_side_pixels: int = DetectionParameters.short_side_pixels
    short_side_fraction: float = DetectionParameters.short_side_fraction
    min_fill: float = DetectionParameters.min_fill
    renderings: tuple[str, ...] = RENDERINGS
    min_elongation: float = 1.0
    elongation_from_side: float = 0.0

    def __post_init__(self):
        if not self.renderings or not set(self.renderings) <= set(RENDERINGS):
            raise EvaluationRefused("A point must join known renderings.")
        numbers = [
            getattr(self, field.name)
            for field in dataclasses.fields(self)
            if field.name != "renderings"
        ]
        if not all(math.isfinite(each) and each >= 0 for each in numbers):
            raise EvaluationRefused("A point's settings must be non-negative numbers.")
        if self.min_elongation < 1:
            raise EvaluationRefused("A minimum elongation must be at least 1.")

    @classmethod
    def of(
        cls, parameters: DetectionParameters, renderings: Sequence[str] = RENDERINGS
    ) -> PostProcessing:
        """The point that a detector of these parameters uses."""
        return cls(
            **{
                field.name: getattr(parameters, field.name)
                for field in dataclasses.fields(cls)
                if hasattr(parameters, field.name)
            },
            renderings=tuple(renderings),
        )

    def described(self) -> dict[str, object]:
        """The point, for the summary."""
        return _plain(dataclasses.asdict(self))


def post_processing_grid(
    base: PostProcessing | None = None, **axes: Iterable[object]
) -> tuple[PostProcessing, ...]:
    """Every combination of the values given for each attribute of
    :class:`PostProcessing`, the others as ``base`` has them, the last
    attribute varying fastest, each point once, in that order.

    Raises
    ------
    EvaluationRefused
        For an attribute that a point does not have, or an axis without
        values.
    """
    base = PostProcessing() if base is None else base
    names = [field.name for field in dataclasses.fields(PostProcessing)]
    unknown = set(axes) - set(names)
    if unknown:
        raise EvaluationRefused("A grid's axis is not a post-processing setting.")
    ordered = [(name, tuple(axes[name])) for name in names if name in axes]
    if any(not values for _, values in ordered):
        raise EvaluationRefused("A grid's axis must have values.")
    points: dict[PostProcessing, None] = {}
    for values in itertools.product(*(each for _, each in ordered)):
        changes = {name: value for (name, _), value in zip(ordered, values)}
        points[dataclasses.replace(base, **changes)] = None
    return tuple(points)


@dataclasses.dataclass(frozen=True)
class _Regions:
    """The regions of one map above one threshold, in the network's
    pixels."""

    top: np.ndarray
    left: np.ndarray
    bottom: np.ndarray
    right: np.ndarray
    mean: np.ndarray
    size: np.ndarray


def _regions(probability: np.ndarray, threshold: float) -> _Regions:
    """Label the map's pixels above the threshold as
    :func:`~.text_detection.scored_boxes_from_probability` does."""
    ndimage = scipy.ndimage
    mask = ndimage.binary_dilation(
        probability > threshold, structure=np.ones((2, 2), bool)
    )
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), bool))
    if count == 0:
        empty = np.zeros(0, np.int64)
        return _Regions(empty, empty, empty, empty, np.zeros(0), np.zeros(0))
    indices = np.arange(1, count + 1)
    slices = ndimage.find_objects(labels)
    return _Regions(
        top=np.array([rows.start for rows, _ in slices], np.int64),
        left=np.array([columns.start for _, columns in slices], np.int64),
        bottom=np.array([rows.stop for rows, _ in slices], np.int64),
        right=np.array([columns.stop for _, columns in slices], np.int64),
        mean=np.asarray(ndimage.mean(probability, labels, index=indices), np.float64),
        size=np.asarray(ndimage.sum(mask, labels, index=indices), np.float64),
    )


def _scored(
    regions: _Regions, each: RenderedProbability, point: PostProcessing
) -> list[tuple[TextBox, float]]:
    """The boxes, with their regions' mean probabilities, that a point
    gives of one map's regions, in the regions' order, as
    :func:`~.text_detection.scored_boxes_from_probability` gives them where
    the elongation filter keeps every region."""
    net_rows, net_columns = each.probability.shape
    rows, columns = each.frame_shape
    row_scale = rows / net_rows
    column_scale = columns / net_columns
    height = regions.bottom - regions.top
    width = regions.right - regions.left
    widest = max(
        point.short_side_pixels, point.short_side_fraction * max(rows, columns)
    )
    frame_height = height * row_scale
    frame_width = width * column_scale
    shorter = np.minimum(frame_height, frame_width)
    longer = np.maximum(frame_height, frame_width)
    keep = (
        (np.minimum(height, width) >= point.min_short_side)
        & (regions.mean >= point.box_threshold)
        & (shorter <= widest)
        & (regions.size >= point.min_fill * height * width)
    )
    if point.min_elongation > 1:
        with np.errstate(divide="ignore", invalid="ignore"):
            elongation = longer / shorter
        keep &= (shorter < point.elongation_from_side) | (
            elongation >= point.min_elongation
        )
    offset = height * width * point.unclip_ratio / (2 * (height + width))
    top = np.floor((regions.top - offset) * row_scale - point.margin)
    bottom = np.ceil((regions.bottom + offset) * row_scale + point.margin)
    left = np.floor((regions.left - offset) * column_scale - point.margin)
    right = np.ceil((regions.right + offset) * column_scale + point.margin)
    return [
        (
            TextBox(
                top=max(0, int(top[index])),
                left=max(0, int(left[index])),
                bottom=min(rows, int(bottom[index])),
                right=min(columns, int(right[index])),
            ),
            float(regions.mean[index]),
        )
        for index in np.flatnonzero(keep)
    ]


def grid_boxes(
    maps: Sequence[RenderedProbability], points: Sequence[PostProcessing]
) -> list[tuple[TextBox, ...]]:
    """The boxes of each point of the grid, from one frame's maps: for each
    point, the boxes of the renderings it joins, each once, sorted, as
    :meth:`~.text_detection.TextDetector.find` gives them.

    Raises
    ------
    EvaluationRefused
        If a point joins a rendering that has no map.
    """
    by_name = {each.rendering: each for each in maps}
    cache: dict[tuple[str, float], _Regions] = {}
    found = []
    for point in points:
        if not set(point.renderings) <= set(by_name):
            raise EvaluationRefused("A point joins a rendering that was not computed.")
        boxes: set[TextBox] = set()
        for name in point.renderings:
            key = (name, point.threshold)
            if key not in cache:
                cache[key] = _regions(by_name[name].probability, point.threshold)
            boxes.update(box for box, _ in _scored(cache[key], by_name[name], point))
        found.append(tuple(sorted(boxes)))
    return found


def published_variant(model: DetectionModel, resampler: str = "cv2") -> DetectorVariant:
    """The variant that scales a rendering as the model's publishers do,
    with the model's own normalisation; today's renderings and top-hats
    are kept, as no publisher's pipeline has them. By default it resizes
    with OpenCV, as their pipeline does; ``"harness"`` resizes as today's
    settings do, so that the two can be compared."""
    if model.published is None:
        raise EvaluationRefused("The model's publishers give no settings.")
    return DetectorVariant(
        name=f"published by {model.name}",
        network_input=InputVariant(
            scaling="longest-at-most",
            working_side=model.published.longest_side,
            resampler=resampler,
        ),
    )


def published_point(model: DetectionModel) -> PostProcessing:
    """The post-processing point at the model's published thresholds, with
    today's other settings."""
    if model.published is None:
        raise EvaluationRefused("The model's publishers give no settings.")
    return PostProcessing(
        threshold=model.published.threshold,
        box_threshold=model.published.box_threshold,
        unclip_ratio=model.published.unclip_ratio,
    )
