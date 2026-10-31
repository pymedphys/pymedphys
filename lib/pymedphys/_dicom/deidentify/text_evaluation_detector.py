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
    their longer side (``"working-size"``), and the normalisation of the
    network's input, which another detection model may need.
model
    any ONNX model of a Differentiable Binarization network, given as bytes;
    the default is the pinned model that a run uses.

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
from collections.abc import Callable, Iterable, Mapping, Sequence

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
    network_tensor,
)
from .text_evaluation_frames import (
    EvaluationFrame,
    EvaluationRefused,
    tissue_mask,
)

SCALINGS = ("limit-side", "millimetres", "working-size")
NOISE_REGIONS = ("frame", "tissue")

# A network: the input tensor, one batch of three channels, to the
# probability map of its rows and columns.
Network = Callable[[np.ndarray], np.ndarray]


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
        The longer side of the network's input, for ``"working-size"``.
    mean, deviation : float
        The network's input is the rendering over 255, less ``mean``, over
        ``deviation``.
    """

    scaling: str = "limit-side"
    millimetres: float = 1.0
    working_side: int = 736
    mean: float = 0.5
    deviation: float = 0.5

    def __post_init__(self):
        if self.scaling not in SCALINGS:
            raise EvaluationRefused("The scaling must be a known one.")
        if not (
            math.isfinite(self.millimetres)
            and self.millimetres > 0
            and self.working_side >= 32
            and math.isfinite(self.deviation)
            and self.deviation > 0
            and math.isfinite(self.mean)
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
    shape: tuple[int, ...], spacing: float | None, variant: DetectorVariant
) -> tuple[int, int]:
    """The rows and columns of the network's input for a rendering of this
    shape, under the variant's scaling."""
    parameters = variant.parameters
    options = variant.network_input
    if options.scaling == "limit-side" or (
        options.scaling == "millimetres" and spacing is None
    ):
        return network_shape(shape, parameters)
    rows, columns = int(shape[0]), int(shape[1])
    if options.scaling == "millimetres":
        assert spacing is not None
        scale = spacing / options.millimetres
    else:
        scale = options.working_side / max(rows, columns)
    scale = min(scale, parameters.max_side / max(rows, columns))
    return (_multiple_of_32(rows * scale), _multiple_of_32(columns * scale))


class EvaluationDetector:
    """The text detector under a variant, for evaluation alone.

    Parameters
    ----------
    variant : DetectorVariant, optional
    model : bytes, optional
        The ONNX model. Defaults to the pinned model that a run uses.
    network : callable, optional
        Runs the network instead of ONNX Runtime, for tests: the input
        tensor to the probability map. It needs ``network_name``.
    network_name : str, optional
        What the method calls ``network``.

    Raises
    ------
    TextDetectionError
        As :class:`~.text_detection.TextDetector` raises it.
    """

    def __init__(
        self,
        variant: DetectorVariant | None = None,
        model: bytes | None = None,
        *,
        network: Network | None = None,
        network_name: str | None = None,
    ):
        self._variant = DetectorVariant() if variant is None else variant
        if network is not None:
            if not network_name:
                raise EvaluationRefused("A network given for tests needs a name.")
            self._network = network
            self._model = {"network": network_name}
            return
        content = model_bytes() if model is None else model
        session = _session(content)
        name = session.get_inputs()[0].name

        def run(tensor: np.ndarray) -> np.ndarray:
            (output,) = session.run(None, {name: tensor})
            return np.asarray(output[0, 0], dtype=np.float32)

        self._network = run
        self._model = {"model_sha256": _sha256(content)}

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
            shape = input_shape(image.shape, frame.pixel_spacing, self._variant)
            tensor = network_tensor(image, shape, options.mean, options.deviation)
            probability = np.asarray(self._network(tensor), dtype=np.float32)
            if probability.shape != shape:
                raise EvaluationRefused(
                    "The network's map is not the shape of its input."
                )
            found.append(RenderedProbability(name, frame.shape, probability))
        return tuple(found)

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
