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

"""Benchmark-only detectors, measured through the harness but never
adoptable. Every runner here is a stand-in."""

import dataclasses
import importlib.metadata
import pathlib
import subprocess
import sys

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_benchmarks as benchmarks
from pymedphys._dicom.deidentify import text_evaluation_criteria as criteria
from pymedphys._dicom.deidentify import text_evaluation_injection as injection
from pymedphys._dicom.deidentify import text_evaluation_markdown as markdown
from pymedphys._dicom.deidentify import text_evaluation_phantoms as phantoms
from pymedphys._dicom.deidentify import text_evaluation_rules as rules
from pymedphys._dicom.deidentify.text_detection import RENDERINGS, TextBox
from pymedphys._dicom.deidentify.text_evaluation_detector import PostProcessing
from pymedphys._dicom.deidentify.text_evaluation_frames import EvaluationRefused
from pymedphys._dicom.deidentify.text_evaluation_models import ModelFile

PACKAGE = pathlib.Path(benchmarks.__file__).parent
ROOT = PACKAGE.parents[3]


def _model(**fields):
    return benchmarks.BenchmarkModel(
        **{
            "name": "invented",
            "runner": "invented",
            "packages": (
                benchmarks.RunnerPackage("invented-ocr", "1.2.3", ("a" * 64, "b" * 64)),
                benchmarks.RunnerPackage(
                    "invented-tesseract", "5.0", ("c" * 64,), "system"
                ),
            ),
            "weights": (ModelFile("https://models.example.org/w.pth", "d" * 64),),
            "code_licence": "MIT",
            "weights_licence": "CC-BY-NC-4.0",
            "licence_evidence": ("https://models.example.org/licence",),
            "copyright": "Invented.",
            "homepage": "https://models.example.org/",
            "training_data": "Invented scenes.",
            **fields,
        }
    )


class Runner:
    """A stand-in runner with two boxes on the image's grid, scored 0.9 and
    0.4, that counts its passes and the options it was given."""

    def __init__(self):
        self.passes = []

    def __call__(self, image, options):
        assert image.dtype == np.uint8 and image.ndim == 2
        self.passes.append(dict(options))
        return [(10, 10, 20, 50, 0.9), (60, 30, 70, 40, 0.4)]


def _frame():
    return phantoms.phantom_frame(
        phantoms.Phantom("ct-thorax", 96, 4.0), np.random.default_rng(0), case="a"
    )


def test_a_benchmark_is_pinned_and_licensed_by_evidence():
    model = _model()
    described = model.described()
    assert described["tier"] == benchmarks.TIER
    assert described["packages"] == {
        "invented-ocr": "1.2.3",
        "invented-tesseract": "5.0",
    }
    assert benchmarks.requirements(model) == (
        f"invented-ocr==1.2.3 --hash=sha256:{'a' * 64} --hash=sha256:{'b' * 64}\n"
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"weights_licence": "unlicensed"},
        {"code_licence": "NONE"},
        {"weights_licence": ""},
        {"licence_evidence": ()},
        {"licence_evidence": ("http://models.example.org/licence",)},
        {"homepage": "http://models.example.org/"},
        {"packages": ()},
        {"runner": "../elsewhere"},
        {"training_data": ""},
        {"weights": ("https://models.example.org/w.pth",)},
    ],
)
def test_a_benchmark_without_its_pins_or_licences_is_refused(fields):
    with pytest.raises(EvaluationRefused):
        _model(**fields)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: benchmarks.RunnerPackage("p", "1", ()),
        lambda: benchmarks.RunnerPackage("p", "", ("a" * 64,)),
        lambda: benchmarks.RunnerPackage("p", "1", ("a" * 63,)),
        lambda: benchmarks.RunnerPackage("p", "1", ("a" * 64,), "conda"),
        lambda: benchmarks.BenchmarkPoint(score=1.5),
        lambda: benchmarks.BenchmarkPoint(renderings=()),
        lambda: benchmarks.BenchmarkPoint(margin=-1),
        lambda: benchmarks.BenchmarkPoint(options=(("a", 1), ("a", 2))),
    ],
)
def test_packages_and_settings_out_of_range_are_refused(factory):
    with pytest.raises(EvaluationRefused):
        factory()


def test_a_runner_needs_the_versions_pinned():
    model = _model()
    benchmarks.check_packages(model, version=lambda name: "1.2.3")
    with pytest.raises(EvaluationRefused, match="1.2.3, not 1.2.4"):
        benchmarks.check_packages(model, version=lambda name: "1.2.4")

    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    with pytest.raises(EvaluationRefused, match="not installed"):
        benchmarks.check_packages(model, version=missing)
    # Without a stand-in, the detector checks before it downloads or imports.
    with pytest.raises(EvaluationRefused, match="not installed"):
        benchmarks.BenchmarkDetector(model)


def test_each_setting_is_measured_and_each_set_of_options_is_a_pass():
    runner = Runner()
    found = benchmarks.BenchmarkDetector(
        _model(), runner=runner, runner_name="stand-in"
    )
    strict = benchmarks.BenchmarkPoint(0.5, margin=0)
    loose = benchmarks.BenchmarkPoint(0.3, margin=2)
    other = benchmarks.BenchmarkPoint(0.3, margin=0, options=(("size", 640),))
    first, second, third = found.boxes_of_points(_frame(), [strict, loose, other])
    assert first == (TextBox(10, 10, 20, 50),)
    assert second == (TextBox(8, 8, 22, 52), TextBox(58, 28, 72, 42))
    assert third == (TextBox(10, 10, 20, 50), TextBox(60, 30, 70, 40))
    assert len(runner.passes) == 2 * len(RENDERINGS)
    assert sum(each == {"size": 640} for each in runner.passes) == len(RENDERINGS)
    assert found.method["tier"] == benchmarks.TIER
    assert found.method["model"]["weights_licence"] == "CC-BY-NC-4.0"
    with pytest.raises(EvaluationRefused):
        found.boxes_of_points(_frame(), [PostProcessing()])
    with pytest.raises(EvaluationRefused):
        benchmarks.BenchmarkDetector(_model(), runner=runner)


def test_a_runner_must_give_four_sides_and_a_score():
    found = benchmarks.BenchmarkDetector(
        _model(), runner=lambda image, options: [(1, 2, 3, 4)], runner_name="bad"
    )
    with pytest.raises(EvaluationRefused):
        found.boxes_of_points(_frame(), [benchmarks.BenchmarkPoint()])


def stand_in():
    """Makes a benchmark detector with a stand-in runner."""
    return benchmarks.BenchmarkDetector(_model(), runner=Runner(), runner_name="s")


def test_benchmark_results_are_marked_and_never_adoptable():
    plan = injection.InjectionPlan(texts=2, heights=(7.0,), contents=("letter",))
    case = phantoms.PhantomCase(phantoms.Phantom("ct-thorax", 96, 4.0), seed=1)
    summary = evaluation.summarise(
        evaluation.evaluate(
            [case],
            stand_in,
            evaluation.EvaluationSettings(
                points=(benchmarks.BenchmarkPoint(),), plan=plan, evaluated="all"
            ),
        ),
        replicates=20,
    )
    assert summary["tier"] == benchmarks.TIER
    lenient = criteria.AcceptanceCriteria()
    (assessed,) = criteria.assess(summary, lenient)
    assert assessed["meets"] and not assessed["adoptable"]
    page = markdown.markdown(summary)
    assert "**Benchmark only**" in page
    assert "| Tier | benchmark-only |" in page
    assert "| Model | invented, runner `s` |" in page
    combined = rules.CombinedDetector(stand_in())
    assert benchmarks.tier_of(combined.method) == benchmarks.TIER
    assert benchmarks.tier_of({"network": "x", "model": {"name": "y"}}) == "adoptable"


def test_runners_stay_out_of_the_package_and_its_lock():
    if not (ROOT / "uv.lock").exists():
        pytest.skip("needs the repository, not an installed package")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    for model in benchmarks.BENCHMARK_MODELS:
        for package in model.packages:
            assert f'name = "{package.name}"' not in lock
            assert f'"{package.name}' not in pyproject
    for path in PACKAGE.glob("*.py"):
        if path.name.startswith("text_evaluation"):
            continue
        source = path.read_text(encoding="utf-8")
        assert "text_evaluation_benchmarks" not in source
        assert "text_evaluation_runner_" not in source


def test_the_module_imports_no_runner():
    code = (
        "import sys\n"
        "import pymedphys._dicom.deidentify.text_evaluation_benchmarks\n"
        "found = {'torch', 'easyocr', 'cv2', 'mmocr', 'doctr', 'surya', "
        "'pytesseract', 'transformers'} & set(sys.modules)\n"
        "print(sorted(found))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"


def test_a_changed_model_is_a_new_model():
    assert dataclasses.replace(_model(), name="other") != _model()
