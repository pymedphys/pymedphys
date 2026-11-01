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

"""Adapters of text detection models, for the evaluation alone."""

# pylint: disable = protected-access

import dataclasses
import hashlib
import importlib.util
import io
import pathlib
import zipfile

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_detection
from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_detector as detector
from pymedphys._dicom.deidentify import text_evaluation_injection as injection
from pymedphys._dicom.deidentify import text_evaluation_models as models
from pymedphys._dicom.deidentify import text_evaluation_phantoms as phantoms
from pymedphys._dicom.deidentify.text_detection import (
    RENDERINGS,
    PinnedModel,
    TextBox,
    TextDetectionError,
)
from pymedphys._dicom.deidentify.text_evaluation_frames import (
    EvaluationFrame,
    EvaluationRefused,
)

MODEL = b"an invented model"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _file(content=MODEL):
    return models.ModelFile(
        url="https://models.example.org/invented-det.onnx", sha256=_sha256(content)
    )


def _model(**fields):
    return models.DetectionModel(
        **{
            "name": "invented",
            "source": _file(),
            "code_licence": "Apache-2.0",
            "weights_licence": "MIT",
            "copyright": "Invented.",
            "homepage": "https://models.example.org/",
            **fields,
        }
    )


def _frame(size=96, seed=0) -> EvaluationFrame:
    frame = phantoms.phantom_frame(
        phantoms.Phantom("ct-thorax", size, 400 / size),
        np.random.default_rng(seed),
        case="a",
    )
    return injection.inject(frame, injection.InjectionPlan(texts=2)).frame


# -- The adapters ---------------------------------------------------------------


def test_todays_model_has_an_adapter_of_its_pin():
    model = models.PP_OCRV6_SMALL
    assert model.source == text_detection.PP_OCRV6_DET_SMALL
    assert model.gives_maps
    assert model.network_input == models.ModelInput()
    assert model.output == models.ProbabilityOutput()
    described = model.described()
    assert described["model_sha256"] == model.source.member_sha256
    assert described["weights_licence"] == "Apache-2.0"


@pytest.mark.parametrize(
    "fields",
    [
        {"code_licence": "GPL-3.0-only"},
        {"weights_licence": "CC-BY-NC-4.0"},
        {"weights_licence": "AGPL-3.0-or-later"},
        {"weights_licence": "unknown"},
        {"homepage": "http://models.example.org/"},
        {"name": ""},
        {"copyright": ""},
        {"source": "https://models.example.org/invented-det.onnx"},
        {"output": "boxes"},
    ],
)
def test_a_model_must_pass_vetting(fields):
    with pytest.raises(EvaluationRefused):
        _model(**fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"sha256": "0" * 63},
        {"sha256": "A" * 64},
        {"url": "http://models.example.org/det.onnx"},
        {"url": "https://models.example.org/"},
    ],
)
def test_a_model_file_must_be_pinned_over_https(fields):
    with pytest.raises(ValueError):
        models.ModelFile(
            **{"url": "https://e.org/d.onnx", "sha256": "0" * 64, **fields}
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: models.ModelInput(channels=2, mean=(0, 0), deviation=(1, 1)),
        lambda: models.ModelInput(mean=(0.5,)),
        lambda: models.ModelInput(deviation=(0.5, 0.0, 0.5)),
        lambda: models.ModelInput(mean=(0.5, float("nan"), 0.5)),
        lambda: models.ModelInput(layout="chw"),
        lambda: models.ModelInput(fixed_shape=(640, 100)),
        lambda: models.ProbabilityOutput(channels=()),
        lambda: models.ProbabilityOutput(layout="hw"),
        lambda: models.ProbabilityOutput(activation="softmax"),
        lambda: models.ProbabilityOutput(stride=0),
    ],
)
def test_input_and_output_settings_must_be_in_range(factory):
    with pytest.raises(EvaluationRefused):
        factory()


# -- Weights --------------------------------------------------------------------


@pytest.fixture(name="data_dir")
def fixture_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PYMEDPHYS_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


def _serving(content, calls=None):
    def download(url, path):
        if calls is not None:
            calls.append(url)
        pathlib.Path(path).write_bytes(content)

    return download


def test_a_model_file_is_fetched_once_and_checked(data_dir):
    calls = []
    model = _model()
    assert models.model_bytes(model, download=_serving(MODEL, calls)) == MODEL
    assert models.model_bytes(model, download=_serving(MODEL, calls)) == MODEL
    assert len(calls) == 1
    cached = data_dir / models.CACHE_DIRECTORY / "invented-det.onnx"
    assert cached.read_bytes() == MODEL


def test_weights_without_their_pinned_digest_are_refused(data_dir):
    with pytest.raises(TextDetectionError):
        models.model_bytes(_model(), download=_serving(MODEL + b"changed"))
    kept = [
        path
        for path in (data_dir / models.CACHE_DIRECTORY).iterdir()
        if not path.name.endswith("-lock")
    ]
    assert not kept


def test_a_model_in_a_wheel_is_taken_as_todays_is(data_dir):
    del data_dir
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as wheel:
        wheel.writestr("models/det.onnx", MODEL)
    content = archive.getvalue()
    pin = PinnedModel(
        url="https://files.example.org/invented-1.0-py3-none-any.whl",
        sha256=_sha256(content),
        member="models/det.onnx",
        member_sha256=_sha256(MODEL),
    )
    model = _model(source=pin)
    assert model.sha256 == _sha256(MODEL)
    assert models.model_bytes(model, download=_serving(content)) == MODEL
    wrong = _model(source=dataclasses.replace(pin, member_sha256="0" * 64))
    with pytest.raises(TextDetectionError):
        models.model_bytes(wrong, download=_serving(content))


# -- Inputs and outputs -----------------------------------------------------------


def test_todays_input_is_the_runs_tensor():
    image = np.random.default_rng(0).integers(0, 256, (50, 70)).astype(np.uint8)
    expected = text_detection.network_tensor(image, (64, 96))
    found = models.model_tensor(image, (64, 96), models.ModelInput())
    assert found.dtype == np.float32
    assert np.array_equal(found, expected)


def test_inputs_follow_the_models_channels_layout_and_normalisation():
    image = np.full((32, 32), 255, np.uint8)
    imagenet = models.ModelInput(
        mean=(0.485, 0.456, 0.406), deviation=(0.229, 0.224, 0.225), layout="nhwc"
    )
    tensor = models.model_tensor(image, (64, 32), imagenet)
    assert tensor.shape == (1, 64, 32, 3)
    assert tensor[0, 0, 0] == pytest.approx(
        [(1 - 0.485) / 0.229, (1 - 0.456) / 0.224, (1 - 0.406) / 0.225], rel=1e-6
    )
    grey = models.ModelInput(channels=1, mean=(0.0,), deviation=(1.0,))
    assert models.model_tensor(image, (32, 32), grey).shape == (1, 1, 32, 32)
    overridden = models.model_tensor(image, (32, 32), imagenet, 0.5, 0.5)
    assert np.allclose(overridden, 1.0)


def test_a_map_is_read_from_its_output_and_channels():
    region = np.zeros((1, 2, 4, 6), np.float32)
    region[0, 0, 1, 1] = 0.8
    region[0, 1, 2, 3] = 0.6
    both = models.ProbabilityOutput(output=1, channels=(0, 1))
    found = models.probability_map([np.zeros(1), region], both, (4, 6))
    assert found[1, 1] == pytest.approx(0.8)
    assert found[2, 3] == pytest.approx(0.6)
    last = models.ProbabilityOutput(layout="nhwc", channels=(1,))
    found = models.probability_map([np.moveaxis(region, 1, -1)], last, (4, 6))
    assert found[2, 3] == pytest.approx(0.6)
    assert found[1, 1] == 0
    logits = models.ProbabilityOutput(activation="sigmoid")
    found = models.probability_map([np.zeros((1, 1, 4, 6))], logits, (4, 6))
    assert np.allclose(found, 0.5)


def test_a_map_at_a_stride_is_resized_to_the_input():
    coarse = np.zeros((1, 1, 16, 16), np.float32)
    coarse[0, 0, 4:8, 4:12] = 1.0
    found = models.probability_map(
        [coarse], models.ProbabilityOutput(stride=2), (32, 32)
    )
    assert found.shape == (32, 32)
    assert found[12, 16] == pytest.approx(1.0)
    assert found[0, 0] == 0
    assert 0 <= found.min() and found.max() <= 1


@pytest.mark.parametrize(
    "outputs, output",
    [
        ([np.zeros((1, 1, 32, 32))], models.ProbabilityOutput(output=1)),
        ([np.zeros((1, 1, 32, 32))], models.ProbabilityOutput(channels=(1,))),
        ([np.zeros((2, 1, 32, 32))], models.ProbabilityOutput()),
        ([np.zeros((32, 32))], models.ProbabilityOutput()),
        ([np.zeros((1, 1, 16, 16))], models.ProbabilityOutput()),
        ([np.zeros((1, 1, 8, 8))], models.ProbabilityOutput(stride=2)),
    ],
)
def test_outputs_that_are_not_the_maps_named_are_refused(outputs, output):
    with pytest.raises(EvaluationRefused):
        models.probability_map(outputs, output, (32, 32))


def test_boxes_are_scaled_to_the_frame_grown_and_clipped():
    boxes = [(2.0, 4.0, 6.0, 8.0), (2.0, 4.0, 6.0, 8.0), (0.0, 60.0, 4.0, 64.0)]
    found = models.frame_boxes(boxes, (32, 64), (64, 32), margin=1)
    assert found == (TextBox(0, 29, 9, 32), TextBox(3, 1, 13, 5))
    assert not models.frame_boxes([(3.0, 3.0, 3.0, 3.0)], (32, 32), (32, 32), 0)
    with pytest.raises(EvaluationRefused):
        models.frame_boxes([(0.0, 0.0, float("nan"), 4.0)], (8, 8), (8, 8), 0)


# -- A model that gives maps -----------------------------------------------------


def coarse_two_channel(tensor):
    """A stand-in network of an NHWC model whose map is at a stride of 2 in
    two channels: the input's brightness in the second channel alone."""
    bright = np.clip(tensor[0, ::2, ::2, 0] * 0.5 + 0.5, 0, 1)
    return [np.stack([np.zeros_like(bright), bright], axis=-1)[np.newaxis]]


MAPS = models.ModelInput(layout="nhwc")
MAPS_OUTPUT = models.ProbabilityOutput(layout="nhwc", channels=(0, 1), stride=2)


def test_a_model_that_gives_maps_takes_the_grid():
    model = _model(network_input=MAPS, output=MAPS_OUTPUT)
    found = detector.EvaluationDetector(
        model=model, network=coarse_two_channel, network_name="coarse"
    )
    frame = _frame()
    maps = found.probabilities(frame)
    assert [each.probability.shape for each in maps] == [(736, 736)] * 3
    grid = detector.post_processing_grid(threshold=(0.3, 0.6))
    boxes = found.boxes_of_points(frame, grid)
    assert boxes == detector.grid_boxes(maps, grid)
    assert found.method["model"]["name"] == "invented"
    assert found.method["model"]["output"]["kind"] == "probability"
    with pytest.raises(EvaluationRefused):
        found.boxes_of_points(frame, [Setting()])


def test_a_fixed_shape_is_the_networks_input_whatever_the_frame():
    model = _model(
        network_input=dataclasses.replace(MAPS, fixed_shape=(640, 640)),
        output=MAPS_OUTPUT,
    )
    found = detector.EvaluationDetector(
        model=model, network=coarse_two_channel, network_name="coarse"
    )
    maps = found.probabilities(_frame(size=128))
    assert {each.probability.shape for each in maps} == {(640, 640)}


# -- A model that gives boxes ----------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Setting:
    """An invented model's own post-processing: a score threshold, which
    stays outside the network, and a size, which the network takes."""

    score: float = 0.5
    size: int = 0
    renderings: tuple[str, ...] = RENDERINGS
    margin: int = 0

    def described(self):
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Decoder:
    """Boxes where the second output's score passes the setting's: each row
    of the first output is a box, top, left, bottom, right, on the input."""

    name: str = "invented"
    point_type: type = Setting

    def feeds(self, point):
        return {"size": np.array([point.size], np.int64)} if point.size else {}

    def boxes(self, outputs, shape, point):
        rows, scores = outputs
        assert rows.shape[1] == 4 and shape[0] >= 32
        return [tuple(row) for row, score in zip(rows, scores) if score >= point.score]

    def described(self):
        return {"kind": "boxes", "name": self.name}


class BoxNetwork:
    """A stand-in network with two boxes on the input's grid, one scored
    0.9 and one 0.4, that counts its passes."""

    def __init__(self):
        self.passes = []

    def __call__(self, tensor, feeds):
        assert tensor.shape == (1, 3, 96, 96)
        self.passes.append(dict(feeds))
        boxes = np.array([[10, 10, 20, 50], [60, 30, 70, 40]], np.float32)
        return [boxes, np.array([0.9, 0.4])]


# The network's input is the frame's own size, so that its boxes are the
# frame's.
SAME_SIZE = detector.DetectorVariant(
    network_input=detector.InputVariant(scaling="working-size", working_side=96)
)


def _box_model():
    return _model(output=Decoder())


def test_a_model_that_gives_boxes_is_measured_at_each_of_its_settings():
    network = BoxNetwork()
    found = detector.BoxModelDetector(
        _box_model(), SAME_SIZE, network=network, network_name="boxes"
    )
    frame = _frame()
    strict, loose, sized = Setting(0.5), Setting(0.3, margin=2), Setting(0.3, size=4)
    first, second, third = found.boxes_of_points(frame, [strict, loose, sized])
    assert first == (TextBox(10, 10, 20, 50),)
    assert second == (TextBox(8, 8, 22, 52), TextBox(58, 28, 72, 42))
    assert third == (TextBox(10, 10, 20, 50), TextBox(60, 30, 70, 40))
    # A setting outside the network reuses its pass; one that it takes
    # needs a pass of its own.
    assert len(network.passes) == 2 * len(RENDERINGS)
    assert sum(bool(each) for each in network.passes) == len(RENDERINGS)
    assert found.method["model"]["output"] == {"kind": "boxes", "name": "invented"}


def test_a_box_model_refuses_settings_not_its_own():
    found = detector.BoxModelDetector(
        _box_model(), SAME_SIZE, network=BoxNetwork(), network_name="boxes"
    )
    frame = _frame()
    with pytest.raises(EvaluationRefused):
        found.boxes_of_points(frame, [detector.PostProcessing()])
    narrow = detector.BoxModelDetector(
        _box_model(),
        dataclasses.replace(
            SAME_SIZE,
            rendering=detector.RenderingVariant(renderings=("full-range",)),
        ),
        network=BoxNetwork(),
        network_name="boxes",
    )
    with pytest.raises(EvaluationRefused):
        narrow.boxes_of_points(frame, [Setting()])


def test_each_kind_of_model_is_measured_by_its_own_detector():
    with pytest.raises(EvaluationRefused):
        detector.EvaluationDetector(
            model=_box_model(), network=BoxNetwork(), network_name="boxes"
        )
    with pytest.raises(EvaluationRefused):
        detector.BoxModelDetector(_model(), network=BoxNetwork(), network_name="x")
    with pytest.raises(EvaluationRefused):
        detector.BoxModelDetector(_box_model(), network=BoxNetwork())


def box_model_detector():
    """Makes a box model's detector with a stand-in network."""
    return detector.BoxModelDetector(
        _box_model(), SAME_SIZE, network=BoxNetwork(), network_name="boxes"
    )


def test_the_harness_measures_a_box_models_settings_as_its_points():
    plan = injection.InjectionPlan(texts=2, heights=(7.0,), contents=("letter",))
    case = phantoms.PhantomCase(phantoms.Phantom("ct-thorax", 96, 4.0), seed=1)
    settings = evaluation.EvaluationSettings(
        points=(Setting(0.5), Setting(0.3)), plan=plan, evaluated="all"
    )
    summary = evaluation.summarise(
        evaluation.evaluate([case], box_model_detector, settings), replicates=20
    )
    assert [point["post_processing"]["score"] for point in summary["points"]] == [
        0.5,
        0.3,
    ]
    assert summary["detector"]["model"]["name"] == "invented"
    assert not summary["collections"][case.collection]["crashed"]
    with pytest.raises(EvaluationRefused):
        evaluation.EvaluationSettings(
            points=(Setting(), detector.PostProcessing()), evaluated="all"
        )


# -- Today's model through its adapter ---------------------------------------------


def _skip_without_onnxruntime() -> None:
    # Importing ONNX Runtime here would enable its telemetry for the session.
    if importlib.util.find_spec("onnxruntime") is None:
        pytest.skip(f"needs pymedphys[{text_detection.EXTRA}]")


@pytest.mark.slow
def test_todays_adapter_gives_todays_maps():
    _skip_without_onnxruntime()
    frame = _frame(size=256, seed=3)
    plain = detector.EvaluationDetector().probabilities(frame)
    adapted_detector = detector.EvaluationDetector(model=models.PP_OCRV6_SMALL)
    adapted = adapted_detector.probabilities(frame)
    for first, second in zip(plain, adapted, strict=True):
        assert np.array_equal(first.probability, second.probability)
    method = adapted_detector.method
    assert method["model_sha256"] == models.PP_OCRV6_SMALL.sha256
    assert method["model"]["name"] == "PP-OCRv6 small"
