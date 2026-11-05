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

"""The text detector's check-only variants and post-processing grid."""

# pylint: disable = protected-access

import dataclasses
import importlib.util
import inspect

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import command, pixel_cleaning, text_detection
from pymedphys._dicom.deidentify import text_evaluation_detector as detector
from pymedphys._dicom.deidentify import text_evaluation_injection as injection
from pymedphys._dicom.deidentify import text_evaluation_phantoms as phantoms
from pymedphys._dicom.deidentify.text_detection import (
    RENDERINGS,
    DetectionParameters,
    TextBox,
)
from pymedphys._dicom.deidentify.text_evaluation_frames import (
    EvaluationFrame,
    EvaluationRefused,
)


def brightness(tensor: np.ndarray) -> np.ndarray:
    """A stand-in network: the probability of text is the input's
    brightness, so bright strokes in a rendering are text."""
    return np.clip((tensor[0, 0] * 0.5 + 0.5), 0.0, 1.0).astype(np.float32)


def _fake(variant=None) -> detector.EvaluationDetector:
    return detector.EvaluationDetector(
        variant, network=brightness, network_name="brightness"
    )


def _frame(size=128, seed=0, kind="ct-thorax", spacing=None) -> EvaluationFrame:
    spacing = 400 / size if spacing is None else spacing
    frame = phantoms.phantom_frame(
        phantoms.Phantom(kind, size, spacing), np.random.default_rng(seed), case="a"
    )
    return injection.inject(frame, injection.InjectionPlan(texts=2)).frame


# -- Renderings and scaling ---------------------------------------------------


@pytest.mark.parametrize("kind", ["ct-thorax", "mr-head", "pet"])
def test_the_default_variant_renders_as_a_run_renders(kind):
    frame = _frame(kind=kind)
    expected = text_detection.renderings(frame.luminance(), DetectionParameters())
    found = detector.variant_renderings(frame, detector.DetectorVariant())
    assert list(found) == list(RENDERINGS)
    for image, each in zip(expected, found.values()):
        assert np.array_equal(image, each)


def test_a_variant_renders_only_what_it_names():
    variant = detector.DetectorVariant(
        rendering=detector.RenderingVariant(renderings=("full-range", "black-top-hat"))
    )
    found = detector.variant_renderings(_frame(), variant)
    assert list(found) == ["full-range", "black-top-hat"]


def test_a_window_floor_keeps_a_low_contrast_frame_dark():
    values = np.full((64, 64), 1000, np.int16)
    values[30:34, 10:50] = 1003  # three units of contrast
    frame = EvaluationFrame(values, "s", "c", "CT Image Storage", "CT")
    plain = detector.variant_renderings(frame, detector.DetectorVariant())
    floored = detector.variant_renderings(
        frame,
        detector.DetectorVariant(
            rendering=detector.RenderingVariant(window_floor=100.0)
        ),
    )
    assert plain["full-range"].max() == 255
    assert floored["full-range"].max() == round(3 * 255 / 100)


def test_a_structuring_element_in_millimetres_follows_the_spacing():
    variant = detector.DetectorVariant(rendering=detector.RenderingVariant(hat_mm=10.0))
    assert detector._hat_size((512, 512), 0.5, variant) == 21
    assert detector._hat_size((512, 512), 2.0, variant) == 5
    default = detector.DetectorVariant()
    assert detector._hat_size(
        (512, 512), 0.5, default
    ) == DetectionParameters().hat_size((512, 512))


def test_tissue_noise_ignores_the_air_around_the_body():
    frame = _frame(size=128)
    tissue = detector.DetectorVariant(
        rendering=detector.RenderingVariant(noise="tissue")
    )
    a = detector.variant_renderings(frame, detector.DetectorVariant())
    b = detector.variant_renderings(frame, tissue)
    assert np.array_equal(a["full-range"], b["full-range"])
    assert not np.array_equal(a["white-top-hat"], b["white-top-hat"])


@pytest.mark.parametrize(
    "network_input, spacing, expected",
    [
        (detector.InputVariant(), 0.5, (1024, 1024)),
        (
            detector.InputVariant(scaling="millimetres", millimetres=1.0),
            0.5,
            (512, 512),
        ),
        (detector.InputVariant(scaling="millimetres"), None, (1024, 1024)),
        (
            detector.InputVariant(scaling="working-size", working_side=640),
            0.5,
            (640, 640),
        ),
    ],
)
def test_the_network_input_is_scaled_as_the_variant_says(
    network_input, spacing, expected
):
    variant = detector.DetectorVariant(network_input=network_input)
    assert detector.input_shape((1024, 1024), spacing, variant) == expected


@pytest.mark.parametrize(
    "make",
    [
        lambda: detector.RenderingVariant(renderings=()),
        lambda: detector.RenderingVariant(renderings=("black-top-hat", "full-range")),
        lambda: detector.RenderingVariant(noise="body"),
        lambda: detector.RenderingVariant(window_floor=0.0),
        lambda: detector.InputVariant(scaling="pixels"),
        lambda: detector.InputVariant(working_side=8),
        lambda: detector.PostProcessing(renderings=("sobel",)),
        lambda: detector.PostProcessing(min_elongation=0.5),
        lambda: detector.PostProcessing(threshold=float("nan")),
    ],
)
def test_unknown_variants_and_points_are_refused(make):
    with pytest.raises(EvaluationRefused):
        make()


# -- The post-processing grid -------------------------------------------------


def _random_maps(rng, frame_shape=(300, 260), net_shape=(320, 288)):
    maps = []
    for name in RENDERINGS:
        probability = np.zeros(net_shape, np.float32)
        for _ in range(25):
            top, left = (
                rng.integers(0, net_shape[0] - 20),
                rng.integers(0, net_shape[1] - 60),
            )
            height, width = rng.integers(1, 20), rng.integers(1, 60)
            probability[top : top + height, left : left + width] = rng.uniform(0.2, 1.0)
        probability += rng.uniform(0, 0.3, net_shape).astype(np.float32)
        maps.append(text_detection.RenderedProbability(name, frame_shape, probability))
    return maps


@pytest.mark.parametrize("seed", range(5))
def test_each_grid_point_gives_the_boxes_a_detector_of_its_parameters_gives(seed):
    rng = np.random.default_rng(seed)
    maps = _random_maps(rng)
    grid = detector.post_processing_grid(
        threshold=(0.3, 0.45),
        box_threshold=(0.5, 0.65),
        unclip_ratio=(1.6, 1.0),
        margin=(2, 0),
        min_fill=(0.3, 0.6),
        short_side_pixels=(48, 16),
    )
    found = detector.grid_boxes(maps, grid)
    for point, boxes in zip(grid, found):
        parameters = dataclasses.replace(
            DetectionParameters(),
            **{
                name: getattr(point, name)
                for name in (
                    "threshold", "box_threshold", "unclip_ratio", "margin",
                    "min_short_side", "short_side_pixels", "short_side_fraction",
                    "min_fill",
                )
            },
        )  # fmt: skip
        expected = {
            box
            for each in maps
            for box in text_detection.boxes_from_probability(
                each.probability, each.frame_shape, parameters
            )
        }
        assert boxes == tuple(sorted(expected))


def test_a_point_joins_only_its_renderings():
    maps = _random_maps(np.random.default_rng(9))
    full_only = detector.PostProcessing(renderings=("full-range",))
    (boxes,) = detector.grid_boxes(maps, [full_only])
    expected = text_detection.boxes_from_probability(
        maps[0].probability, maps[0].frame_shape, DetectionParameters()
    )
    assert boxes == tuple(sorted(set(expected)))


def test_the_elongation_filter_drops_only_large_square_regions():
    probability = np.zeros((128, 128), np.float32)
    probability[10:30, 10:30] = 0.9  # a large square, as anatomy gives
    probability[50:54, 10:14] = 0.9  # a small square, as a single letter
    probability[80:86, 10:60] = 0.9  # a line of text
    maps = [text_detection.RenderedProbability("full-range", (128, 128), probability)]
    point = detector.PostProcessing(
        renderings=("full-range",), min_elongation=2.0, elongation_from_side=12.0
    )
    every, filtered = detector.grid_boxes(
        maps, [detector.PostProcessing(renderings=("full-range",)), point]
    )
    assert len(every) == 3
    assert len(filtered) == 2
    assert all(box.top > 40 for box in filtered)


def test_a_grid_is_every_combination_once_in_order():
    grid = detector.post_processing_grid(
        box_threshold=(0.5, 0.6), threshold=(0.3, 0.3, 0.4)
    )
    assert [(point.threshold, point.box_threshold) for point in grid] == [
        (0.3, 0.5), (0.3, 0.6), (0.4, 0.5), (0.4, 0.6),
    ]  # fmt: skip
    with pytest.raises(EvaluationRefused):
        detector.post_processing_grid(colour=(1,))
    with pytest.raises(EvaluationRefused):
        detector.post_processing_grid(threshold=())


def test_a_point_needs_its_renderings_computed():
    maps = _random_maps(np.random.default_rng(1))[:1]
    with pytest.raises(EvaluationRefused):
        detector.grid_boxes(maps, [detector.PostProcessing()])


def test_the_default_point_is_the_detectors():
    assert (
        detector.PostProcessing.of(DetectionParameters()) == detector.PostProcessing()
    )


# -- The evaluation detector --------------------------------------------------


def test_a_test_network_needs_a_name():
    with pytest.raises(EvaluationRefused):
        detector.EvaluationDetector(network=brightness)


def test_the_evaluation_detector_gives_maps_of_its_input_shape():
    found = _fake().probabilities(_frame(size=96))
    assert [each.rendering for each in found] == list(RENDERINGS)
    assert all(each.probability.shape == (736, 736) for each in found)
    assert all(each.frame_shape == (96, 96) for each in found)


def test_find_and_detections_follow_the_text_detector_protocol():
    fake = _fake()
    frame = _frame(size=96).stored
    detections = fake.detections(frame)
    assert all(isinstance(each, text_detection.Detection) for each in detections)
    assert fake.find(frame) == tuple(sorted({each.box for each in detections}))
    assert all(isinstance(box, TextBox) for box in fake.find(frame))


def test_its_description_names_its_class_and_variant():
    fake = _fake(detector.DetectorVariant(name="tissue-noise"))
    described = pixel_cleaning.finder_description(fake)
    assert described["finder"].endswith("text_evaluation_detector.EvaluationDetector")
    assert described["method"]["variant"]["name"] == "tissue-noise"
    assert described["method"]["network"] == "brightness"


def test_a_run_makes_only_the_text_detector():
    source = inspect.getsource(command)
    assert "EvaluationDetector" not in source
    assert "text_evaluation" not in source


def _skip_without_onnxruntime() -> None:
    # Importing ONNX Runtime here would enable its telemetry for the session.
    if importlib.util.find_spec("onnxruntime") is None:
        pytest.skip(f"needs pymedphys[{text_detection.EXTRA}]")


@pytest.mark.slow
@pytest.mark.parametrize("kind", phantoms.KINDS)
def test_the_default_variant_gives_a_runs_maps_and_boxes(kind):
    _skip_without_onnxruntime()
    run = text_detection.TextDetector()
    evaluation = detector.EvaluationDetector()
    frame = _frame(size=512, seed=3, kind=kind)
    expected = run.probabilities(frame.stored)
    found = evaluation.probabilities(frame)
    for first, second in zip(expected, found, strict=True):
        assert first.rendering == second.rendering
        assert np.array_equal(first.probability, second.probability)
    (boxes,) = detector.grid_boxes(found, [detector.PostProcessing()])
    assert boxes == run.find(frame.stored) == evaluation.find(frame.stored)
    assert evaluation.method["model_sha256"] == run.model_sha256
