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

"""Text detection for the Clean Pixel Data Option, on synthetic frames."""

import dataclasses
import hashlib
import importlib.util
import io
import os
import pathlib
import re
import subprocess
import sys
import textwrap
import types
import zipfile

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    method_digest,
    pixel_cleaning,
    policy,
    text_detection,
)
from pymedphys._dicom.deidentify.text_detection import (
    DetectionParameters,
    PinnedModel,
    TextBox,
    TextDetectionError,
    TextDetector,
)

from . import _synthetic_text as synthetic

WHEEL_URL = "https://files.example.org/example-1.0-py3-none-any.whl"
MEMBER = "example/models/detector.onnx"


def _skip_without_onnxruntime() -> None:
    # Importing ONNX Runtime here, as pytest.importorskip would, enables its
    # telemetry for the session, and the detector would then refuse to run.
    if importlib.util.find_spec("onnxruntime") is None:
        pytest.skip(f"needs pymedphys[{text_detection.EXTRA}]")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _wheel(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as wheel:
        for name, content in members.items():
            wheel.writestr(name, content)
    return buffer.getvalue()


@pytest.fixture(name="data_dir")
def fixture_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PYMEDPHYS_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


def _serving(content: bytes):
    calls = []

    def download(url: str, path: pathlib.Path) -> None:
        calls.append(url)
        pathlib.Path(path).write_bytes(content)

    return download, calls


def test_the_pinned_model_names_a_wheel_on_pypi():
    model = text_detection.PP_OCRV6_DET_SMALL
    assert model.url.startswith("https://files.pythonhosted.org/")
    assert model.file == "rapidocr-3.10.0-py3-none-any.whl"
    assert model.member == "rapidocr/models/PP-OCRv6_det_small.onnx"


@pytest.mark.parametrize(
    "fields",
    [
        {"sha256": "0" * 63},
        {"member_sha256": "A" * 64},
        {"url": "http://files.example.org/example.whl"},
        {"url": "https://files.example.org/"},
    ],
)
def test_a_pin_must_be_https_and_full_sha256(fields):
    valid = {
        "url": WHEEL_URL,
        "sha256": "0" * 64,
        "member": MEMBER,
        "member_sha256": "0" * 64,
    }
    with pytest.raises(ValueError):
        PinnedModel(**{**valid, **fields})


def test_model_bytes_downloads_once_and_checks_both_digests(data_dir):
    model_content = b"model"
    wheel = _wheel({MEMBER: model_content, "example/other.txt": b"other"})
    model = PinnedModel(WHEEL_URL, _sha256(wheel), MEMBER, _sha256(model_content))
    download, calls = _serving(wheel)

    assert text_detection.model_bytes(model, download=download) == model_content
    assert text_detection.model_bytes(model, download=download) == model_content
    assert calls == [WHEEL_URL]
    cached = data_dir / text_detection.CACHE_DIRECTORY / model.file
    assert cached.read_bytes() == wheel


def test_a_wheel_without_its_digest_is_never_cached(data_dir):
    wheel = _wheel({MEMBER: b"model"})
    model = PinnedModel(WHEEL_URL, "0" * 64, MEMBER, _sha256(b"model"))
    download, _ = _serving(wheel)

    with pytest.raises(TextDetectionError, match="pinned SHA-256"):
        text_detection.model_bytes(model, download=download)
    cache = data_dir / text_detection.CACHE_DIRECTORY
    assert not [path for path in cache.iterdir() if "lock" not in path.name]


def test_a_cached_wheel_that_changed_is_downloaded_again(data_dir):
    wheel = _wheel({MEMBER: b"model"})
    model = PinnedModel(WHEEL_URL, _sha256(wheel), MEMBER, _sha256(b"model"))
    cached = data_dir / text_detection.CACHE_DIRECTORY / model.file
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"cut short")
    download, calls = _serving(wheel)

    assert text_detection.model_bytes(model, download=download) == b"model"
    assert calls == [WHEEL_URL]


@pytest.mark.parametrize(
    "members",
    [{MEMBER: b"another model"}, {"example/elsewhere.onnx": b"model"}],
)
def test_a_wheel_must_hold_the_pinned_model(data_dir, members):
    del data_dir
    wheel = _wheel(members)
    model = PinnedModel(WHEEL_URL, _sha256(wheel), MEMBER, _sha256(b"model"))
    download, _ = _serving(wheel)

    with pytest.raises(TextDetectionError):
        text_detection.model_bytes(model, download=download)


@pytest.mark.parametrize("box", [(0, 0, 0, 1), (0, 0, 1, 0), (-1, 0, 1, 1)])
def test_a_box_has_rows_and_columns(box):
    with pytest.raises(ValueError):
        TextBox(*box)


def _probability(shape, regions):
    probability = np.zeros(shape)
    for (top, left, bottom, right), value in regions:
        probability[top:bottom, left:right] = value
    return probability


def test_a_text_line_gives_a_box_grown_by_the_offset_and_margin():
    parameters = DetectionParameters()
    probability = _probability((64, 64), [((10, 10, 14, 30), 0.9)])

    (box,) = text_detection.boxes_from_probability(probability, (64, 64), parameters)

    # Dilation by a 2 by 2 square grows the region up and left by one, to
    # rows 9 to 14 and columns 9 to 30; its offset is 5 * 21 * 1.6 / 52.
    offset = 5 * 21 * 1.6 / 52
    assert box == TextBox(
        top=int(np.floor(9 - offset - 2)),
        left=int(np.floor(9 - offset - 2)),
        bottom=int(np.ceil(14 + offset + 2)),
        right=int(np.ceil(30 + offset + 2)),
    )


def test_boxes_are_scaled_to_the_frame():
    parameters = DetectionParameters(margin=0, unclip_ratio=0)
    probability = _probability((64, 64), [((10, 10, 14, 30), 0.9)])

    (box,) = text_detection.boxes_from_probability(probability, (32, 128), parameters)

    assert box == TextBox(top=4, left=18, bottom=7, right=60)


@pytest.mark.parametrize(
    "regions",
    [
        # Too unlikely: the region's mean is under the box threshold.
        [((10, 10, 14, 30), 0.4)],
        # Too wide for a line of text: a flat organ the network marks.
        [((4, 4, 60, 60), 0.9)],
        # Too sparse: a ring, as a body outline can be.
        [((4, 4, 60, 6), 0.9), ((4, 4, 6, 60), 0.9), ((58, 4, 60, 60), 0.9)],
    ],
)
def test_regions_that_are_not_text_give_no_box(regions):
    parameters = DetectionParameters(short_side_pixels=10, short_side_fraction=0)
    probability = _probability((64, 64), regions)

    assert not text_detection.boxes_from_probability(probability, (64, 64), parameters)


def test_regions_narrower_than_the_minimum_give_no_box():
    # Dilation makes a region of two rows three rows high.
    probability = _probability((64, 64), [((10, 10, 12, 30), 0.9)])
    narrowest = DetectionParameters(min_short_side=4)

    assert not text_detection.boxes_from_probability(probability, (64, 64), narrowest)
    assert text_detection.boxes_from_probability(
        probability, (64, 64), DetectionParameters()
    )


def test_a_flat_frame_renders_black():
    for image in text_detection.renderings(
        np.full((40, 50), 7.0), DetectionParameters()
    ):
        assert image.dtype == np.uint8
        assert image.shape == (40, 50)
        assert not image.any()


def test_the_top_hats_show_faint_strokes_and_hide_slow_shading():
    rng = np.random.default_rng(0)
    columns = np.mgrid[0:128, 0:128][1]
    frame = 1000.0 + 8 * columns + rng.normal(0, 5, (128, 128))
    ink = synthetic.burn(np.zeros(frame.shape), "AB", 60, 40, 1)[1].ink
    frame[ink] += 100
    full, white, black = text_detection.renderings(frame, DetectionParameters())

    # 100 above its surroundings is under 9% of the frame's range, about 22
    # grey levels of the full range, but 20 noise deviations, so it is near
    # full brightness in the white top-hat.
    assert np.median(full[ink]) - np.median(full[~ink]) < 40
    assert np.median(white[ink]) > 200
    assert np.median(white[~ink]) < 20
    assert np.median(black[ink]) < 20
    assert full.max() == 255


def test_rgb_frames_are_searched_by_luminance():
    frame = np.zeros((4, 4, 3), np.uint8)
    frame[..., 0] = 255
    assert np.allclose(text_detection._luminance(frame), 0.299 * 255)  # pylint: disable = protected-access
    with pytest.raises(ValueError):
        text_detection._luminance(np.zeros((4, 4, 4)))  # pylint: disable = protected-access


@pytest.mark.parametrize("variable", [None, "0", "1"])
def test_onnxruntime_imported_elsewhere_is_refused(monkeypatch, variable):
    # ONNX Runtime reads the variable as it initialises, so one set only
    # after another import (the "1" case) cannot have disabled its telemetry.
    monkeypatch.setitem(sys.modules, "onnxruntime", object())
    monkeypatch.setattr(text_detection, "_IMPORTED", {})
    monkeypatch.setattr(text_detection, "_installed_onnxruntime", lambda: ((), None))
    if variable is None:
        monkeypatch.delenv(text_detection.TELEMETRY_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(text_detection.TELEMETRY_VARIABLE, variable)

    with pytest.raises(TextDetectionError, match="telemetry"):
        text_detection._onnxruntime()  # pylint: disable = protected-access


def test_the_runtime_text_detection_imported_is_reused(monkeypatch):
    runtime = object()
    monkeypatch.setitem(sys.modules, "onnxruntime", runtime)
    monkeypatch.setattr(text_detection, "_IMPORTED", {"onnxruntime": runtime})

    assert text_detection._onnxruntime() is runtime  # pylint: disable = protected-access


@pytest.mark.parametrize(
    "platform, distributions, version",
    [
        ("win32", ("onnxruntime",), "1.31.0"),
        ("win32", ("onnxruntime",), "1.32.0rc1"),
        ("win32", ("onnxruntime",), "2.0.0"),
        ("win32", (), None),
        ("linux", ("onnxruntime",), "1.20.1"),
        ("linux", ("onnxruntime-gpu",), None),
        ("darwin", ("onnxruntime",), "1.29.0"),
    ],
)
def test_runtimes_whose_telemetry_the_variable_turns_off_are_accepted(
    platform, distributions, version
):
    assert (
        text_detection._runtime_problem(  # pylint: disable = protected-access
            platform, distributions, version
        )
        is None
    )


@pytest.mark.parametrize(
    "distributions, version, message",
    [
        (("onnxruntime",), "1.20.1", r"1\.20\.1 traces through ETW.*1\.31 or later"),
        (("onnxruntime",), "1.30.0", r"1\.30\.0 traces through ETW"),
        (("onnxruntime",), "unknown", "ETW"),
        (("onnxruntime-directml",), None, "onnxruntime-directml"),
        (("onnxruntime", "onnxruntime-gpu"), "1.31.0", "onnxruntime, onnxruntime-gpu"),
    ],
)
def test_windows_runtimes_that_may_trace_through_etw_are_refused(
    distributions, version, message
):
    problem = text_detection._runtime_problem(  # pylint: disable = protected-access
        "win32", distributions, version
    )
    assert problem is not None
    assert re.search(message, problem)


def test_an_older_windows_runtime_is_refused_before_it_is_imported(monkeypatch):
    # A None entry would make an import fail; refusing first never reaches it.
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        text_detection,
        "_installed_onnxruntime",
        lambda: (("onnxruntime",), "1.20.1"),
    )

    with pytest.raises(TextDetectionError, match="ETW"):
        text_detection._onnxruntime()  # pylint: disable = protected-access


def test_the_installed_runtime_is_found_without_importing_it():
    imported = "onnxruntime" in sys.modules
    distributions, version = text_detection._installed_onnxruntime()  # pylint: disable = protected-access

    assert ("onnxruntime" in sys.modules) == imported
    if importlib.util.find_spec("onnxruntime") is None:
        assert not distributions
    if "onnxruntime" in distributions:
        assert version


def test_a_missing_onnxruntime_names_the_extra(monkeypatch):
    # A None entry makes the import fail, as an uninstalled package does.
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    monkeypatch.setenv(text_detection.TELEMETRY_VARIABLE, "1")

    with pytest.raises(TextDetectionError, match=r"pymedphys\[text-detection\]"):
        text_detection._onnxruntime()  # pylint: disable = protected-access


def _varint(number: int) -> bytes:
    out = bytearray()
    while True:
        low, number = number & 0x7F, number >> 7
        out.append(low | (0x80 if number else 0))
        if not number:
            return bytes(out)


def _field(number: int, value: int | str | bytes) -> bytes:
    if isinstance(value, int):
        return _varint(number << 3) + _varint(value)
    if isinstance(value, str):
        value = value.encode()
    return _varint(number << 3 | 2) + _varint(len(value)) + value


def _identity_model() -> bytes:
    """An ONNX model, encoded by hand, whose one node copies its float input."""
    tensor_type = _field(1, _field(1, 1))  # TypeProto.tensor_type.elem_type FLOAT
    node = _field(1, "x") + _field(2, "y") + _field(4, "Identity")
    graph = (
        _field(1, node)
        + _field(2, "identity")
        + _field(11, _field(1, "x") + _field(2, tensor_type))
        + _field(12, _field(1, "y") + _field(2, tensor_type))
    )
    opset = _field(1, "") + _field(2, 13)
    return _field(1, 8) + _field(7, graph) + _field(8, opset)


def test_a_session_leaves_no_telemetry_behind(tmp_path):
    """ONNX Runtime 1.29 and later write a device ID and a queue of events
    under the user's cache directory, and send them, unless telemetry is
    disabled before it is imported."""
    _skip_without_onnxruntime()
    home = tmp_path / "home"
    home.mkdir()
    model = tmp_path / "identity.onnx"
    model.write_bytes(_identity_model())
    script = textwrap.dedent(
        """
        import pathlib, sys
        import numpy as np
        from pymedphys._dicom.deidentify import text_detection
        session = text_detection._session(pathlib.Path(sys.argv[1]).read_bytes())
        output = session.run(None, {"x": np.arange(3, dtype=np.float32)})[0]
        assert output.tolist() == [0.0, 1.0, 2.0]
        """
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != text_detection.TELEMETRY_VARIABLE
    }
    for variable in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA"):
        environment[variable] = str(home)
    environment["XDG_CACHE_HOME"] = str(home / ".cache")

    subprocess.run(
        [sys.executable, "-c", script, str(model)],
        check=True,
        env=environment,
        timeout=120,
    )

    assert not [path for path in home.rglob("*") if path.is_file()]


def test_a_runtime_imported_before_text_detection_is_refused(tmp_path):
    """Whatever the variable is now, text detection cannot know what it was
    when something else imported ONNX Runtime, so it refuses that runtime.
    The variable is set from the start here, so the import sends nothing."""
    _skip_without_onnxruntime()
    model = tmp_path / "identity.onnx"
    model.write_bytes(_identity_model())
    script = textwrap.dedent(
        """
        import pathlib, sys
        import onnxruntime
        from pymedphys._dicom.deidentify import text_detection
        try:
            text_detection._session(pathlib.Path(sys.argv[1]).read_bytes())
        except text_detection.TextDetectionError as error:
            assert "imported before" in str(error)
        else:
            raise AssertionError("a runtime imported elsewhere was used")
        """
    )
    environment = dict(os.environ)
    environment[text_detection.TELEMETRY_VARIABLE] = "1"

    subprocess.run(
        [sys.executable, "-c", script, str(model)],
        check=True,
        env=environment,
        timeout=120,
    )


@pytest.fixture(name="detector", scope="module")
def fixture_detector():
    _skip_without_onnxruntime()
    return text_detection.TextDetector()


def _covered(boxes, shape) -> np.ndarray:
    mask = np.zeros(shape, bool)
    for box in boxes:
        mask[box.top : box.bottom, box.left : box.right] = True
    return mask


def _zone(burned_strings, shape) -> np.ndarray:
    """Each string's extent, grown on every side by its height, its shorter
    side, or 8 pixels, whichever is most, since boxes grow with the text."""
    zone = np.zeros(shape, bool)
    for burned in burned_strings:
        rows, columns = np.nonzero(burned.ink)
        height = min(np.ptp(rows), np.ptp(columns)) + 1
        margin = max(8, height)
        zone[
            max(0, rows.min() - margin) : rows.max() + margin + 1,
            max(0, columns.min() - margin) : columns.max() + margin + 1,
        ] = True
    return zone


# Text at the largest stored value, as annotations usually are, in the
# margins and across the body, at 7, 14, and 21 pixels high.
ANNOTATIONS = [
    ("SMITH^JANE", 10, 300, 1),
    ("ID 40551873", 480, 20, 1),
    ("2026-10-12 09:41", 20, 20, 1),
    ("W:400 L:40", 470, 330, 1),
    ("DOE^J", 230, 200, 2),
    ("MRN 00988", 150, 300, 1),
    ("ACC A99812", 300, 60, 3),
]


@pytest.mark.slow
def test_annotations_are_covered_and_anatomy_is_left(detector):
    frame = synthetic.ct_slice(np.random.default_rng(7))
    burned_strings = []
    for text, top, left, scale in ANNOTATIONS:
        frame, burned = synthetic.burn(frame, text, top, left, 4095, scale)
        burned_strings.append(burned)

    boxes = detector.find(frame)

    covered = _covered(boxes, frame.shape)
    for burned in burned_strings:
        assert covered[burned.ink].all(), burned.text
    elsewhere = ~_zone(burned_strings, frame.shape)
    assert covered[elsewhere].mean() < 0.01
    assert detector.find(frame) == boxes


@pytest.mark.slow
def test_vertical_annotations_are_covered(detector):
    frame = synthetic.ct_slice(np.random.default_rng(11))
    burned_strings = []
    for text, left in (("SMITH^JANE", 6), ("DOB 1957-03-14", 496)):
        mask = synthetic.text_mask(text).T[::-1]
        ink = np.zeros(frame.shape, bool)
        ink[100 : 100 + mask.shape[0], left : left + mask.shape[1]] = mask
        frame[ink] = 4095
        burned_strings.append(synthetic.Burned(text, ink))

    covered = _covered(detector.find(frame), frame.shape)

    for burned in burned_strings:
        assert covered[burned.ink].all(), burned.text


@pytest.mark.slow
def test_a_frame_without_text_gives_no_box(detector):
    frame = synthetic.ct_slice(np.random.default_rng(8))
    assert detector.find(frame) == ()


@pytest.mark.slow
def test_the_method_names_the_model_runtime_and_parameters(detector):
    method = detector.method
    assert method["model_sha256"] == text_detection.PP_OCRV6_DET_SMALL.member_sha256
    assert method["onnxruntime"]
    assert "onnxruntime" in method["onnxruntime_distributions"]
    assert method["numpy"] == np.__version__
    assert method["scipy"]
    assert method["parameters"] == dataclasses.asdict(DetectionParameters())
    assert method["renderings"] == list(text_detection.RENDERINGS)


def _unloaded_detector(monkeypatch) -> TextDetector:
    """A detector with the default parameters and no model or ONNX Runtime."""
    monkeypatch.setattr(
        text_detection,
        "_onnxruntime",
        lambda: types.SimpleNamespace(__version__="1.31.0"),
    )
    monkeypatch.setattr(
        text_detection, "_installed_onnxruntime", lambda: (("onnxruntime",), "1.31.0")
    )
    detector = object.__new__(TextDetector)
    detector._parameters = DetectionParameters()  # pylint: disable = protected-access
    detector._model_sha256 = "0" * 64  # pylint: disable = protected-access
    return detector


def test_the_detectors_description_has_a_canonical_form(monkeypatch):
    detector = _unloaded_detector(monkeypatch)

    description = pixel_cleaning.finder_description(detector)

    assert description["finder"] == (
        "pymedphys._dicom.deidentify.text_detection.TextDetector"
    )
    assert description["method"]["onnxruntime_distributions"] == ("onnxruntime",)
    components = method_digest.method_digest_components(
        policy.compose_custom_policy((policy.CLEAN_PIXEL_DATA,)),
        vocabulary=None,
        reviewed_roi_names=None,
        text_finder=description,
    )
    assert components.text_finder_digest is not None


def test_what_decides_the_detectors_boxes_cannot_be_reassigned(monkeypatch):
    detector = _unloaded_detector(monkeypatch)
    with pytest.raises(AttributeError):
        detector.parameters = DetectionParameters(threshold=0.1)  # type: ignore[misc]
    with pytest.raises(AttributeError):
        detector.model_sha256 = "1" * 64  # type: ignore[misc]
