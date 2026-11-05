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

"""The saturated-overlay rule, a comparator that needs no model."""

import pathlib

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_detector as detector
from pymedphys._dicom.deidentify import text_evaluation_injection as injection
from pymedphys._dicom.deidentify import text_evaluation_phantoms as phantoms
from pymedphys._dicom.deidentify import text_evaluation_rules as rules
from pymedphys._dicom.deidentify.text_detection import TextBox
from pymedphys._dicom.deidentify.text_evaluation_fonts import BitmapFont
from pymedphys._dicom.deidentify.text_evaluation_frames import (
    EvaluationFrame,
    EvaluationRefused,
)

RULE = rules.SaturatedOverlayDetector()


def _frame(stored, **options):
    return EvaluationFrame(
        stored=stored,
        collection="c",
        case="a",
        iod="CT Image Storage",
        modality="CT",
        **options,
    )


def _letters(stored, top, left, value, letters=3, rows=7, gap=2):
    """Draws ``letters`` filled 5 by ``rows`` blocks, ``gap`` columns apart."""
    for index in range(letters):
        start = left + index * (5 + gap)
        stored[top : top + rows, start : start + 5] = value


def _anatomy(seed=0, shape=(96, 96)):
    """Air at the least value, and a body of noisy tissue that reaches
    neither extreme."""
    rng = np.random.default_rng(seed)
    stored = np.zeros(shape, np.int64)
    rows, columns = np.ogrid[: shape[0], : shape[1]]
    body = (rows - 48) ** 2 + (columns - 48) ** 2 < 36**2
    stored[body] = rng.integers(900, 1200, shape)[body]
    return stored


def _one(frame, point=rules.OverlayPoint()):
    (boxes,) = RULE.boxes_of_points(frame, [point])
    return boxes


def test_text_at_the_maximum_is_boxed_as_a_line():
    stored = _anatomy()
    _letters(stored, 4, 4, 4095)
    boxes = _one(_frame(stored))
    # Three letters 2 columns apart join into one box, grown by 2.
    assert boxes == (TextBox(2, 2, 13, 25),)


def test_air_noise_and_anatomy_are_not_glyphs():
    stored = _anatomy()
    stored[60, 60] = stored.max() + 1  # a single pixel at the maximum
    assert _one(_frame(stored)) == ()
    stored[2, 2:90] = stored.max()  # a line far wider than a glyph
    assert _one(_frame(stored)) == ()


def test_glyphs_far_apart_are_boxed_apart():
    stored = _anatomy()
    _letters(stored, 4, 4, 4095, letters=1)
    _letters(stored, 4, 40, 4095, letters=1)
    assert len(_one(_frame(stored))) == 2
    joined = rules.OverlayPoint(join_columns=20)
    assert len(_one(_frame(stored), joined)) == 1


def test_the_reference_tolerance_and_levels_are_settings():
    stored = _anatomy()
    _letters(stored, 4, 4, 3000)
    frame = _frame(stored, stored_range=(0, 4095))
    assert _one(frame)
    assert _one(frame, rules.OverlayPoint(reference="stored-range")) == ()
    stored[4:11, 4:9] = 2998
    assert _one(frame) != _one(frame, rules.OverlayPoint(tolerance=2))
    dark = np.full((64, 64), 2000, np.int64)
    dark += np.random.default_rng(1).integers(0, 50, dark.shape)
    _letters(dark, 30, 10, 0)
    assert _one(_frame(dark), rules.OverlayPoint(levels=("maximum",))) == ()
    assert len(_one(_frame(dark), rules.OverlayPoint(levels=("minimum",)))) == 1


def test_coloured_overlays_saturate_a_channel():
    stored = np.zeros((64, 64, 3), np.int64)
    stored[..., :] = np.random.default_rng(2).integers(40, 200, (64, 64, 1))
    _letters(stored[..., 0], 20, 10, 255)
    _letters(stored[..., 1], 20, 10, 255)
    frame = _frame(stored, photometric="RGB", stored_range=(0, 255))
    point = rules.OverlayPoint(levels=("maximum",), reference="stored-range")
    assert len(_one(frame, point)) == 1
    stored[20:27, 10:30, 2] = 255  # white, every channel at its maximum
    assert len(_one(frame, point)) == 1


@pytest.mark.parametrize(
    "fields",
    [
        {"levels": ()},
        {"levels": ("maximum", "minimum")},
        {"levels": ("brightest",)},
        {"reference": "window"},
        {"tolerance": -1},
        {"min_rows": 0},
        {"min_rows": 10, "max_rows": 5},
        {"max_columns": 0},
        {"margin": 1.5},
        {"renderings": ("full-range",)},
    ],
)
def test_settings_out_of_range_are_refused(fields):
    with pytest.raises(EvaluationRefused):
        rules.OverlayPoint(**fields)


def test_the_rule_takes_only_its_own_settings():
    with pytest.raises(EvaluationRefused):
        RULE.boxes_of_points(_frame(_anatomy()), [detector.PostProcessing()])
    assert RULE.method["rule"] == rules.RULE


def test_saturated_text_is_fully_covered_through_the_harness():
    plan = injection.InjectionPlan(
        fonts=(BitmapFont(),),
        heights=(10.0,),
        contrasts=(injection.SATURATED,),
        polarities=("higher",),
        styles=("solid",),
        orientations=(0,),
        positions=("air",),
        contents=("letter", "identifier"),
        texts=2,
    )
    cases = [
        phantoms.PhantomCase(phantoms.Phantom("ct-thorax", 128, 3.0), seed=seed)
        for seed in range(3)
    ]
    points = (
        rules.OverlayPoint(reference="stored-range"),
        rules.OverlayPoint(reference="frame", margin=0),
    )
    summary = evaluation.summarise(
        evaluation.evaluate(
            cases,
            rules.SaturatedOverlayDetector,
            evaluation.EvaluationSettings(points=points, plan=plan, evaluated="all"),
        ),
        replicates=20,
    )
    first = summary["points"][0]
    assert first["sensitivity"]["texts"] > 0
    assert first["sensitivity"]["fully_covered"] == first["sensitivity"]["texts"]
    assert first["post_processing"]["reference"] == "stored-range"
    assert "renderings" not in first["post_processing"]
    assert summary["detector"]["rule"] == rules.RULE


# -- Combined with a model ------------------------------------------------------


class CountingModel:
    """A stand-in model's detector with one fixed box, that counts its
    calls and the points it was given."""

    def __init__(self):
        self.calls = []

    @property
    def method(self):
        return {"network": "fixed"}

    def boxes_of_points(self, frame, points):
        del frame
        self.calls.append(list(points))
        return [(TextBox(40, 40, 50, 60),)] * len(points)


def test_a_model_and_the_rule_are_joined():
    stored = _anatomy()
    _letters(stored, 4, 4, 4095)
    model = CountingModel()
    combined = rules.CombinedDetector(model)
    grid = detector.post_processing_grid(threshold=(0.3, 0.6))
    points = [
        rules.CombinedPoint(model_point, rule_point)
        for model_point in grid
        for rule_point in (rules.OverlayPoint(), rules.OverlayPoint(margin=0))
    ]
    found = combined.boxes_of_points(_frame(stored), points)
    assert found[0] == (TextBox(2, 2, 13, 25), TextBox(40, 40, 50, 60))
    assert found[1] == (TextBox(4, 4, 11, 23), TextBox(40, 40, 50, 60))
    # The model is asked once, for each of its points once.
    assert model.calls == [list(grid)]
    assert combined.method == {"model": {"network": "fixed"}, "rule": RULE.method}
    described = points[1].described()
    assert described["rule.margin"] == 0
    assert described["model.threshold"] == 0.3


def test_combinations_are_of_a_model_and_the_rule():
    with pytest.raises(EvaluationRefused):
        rules.CombinedDetector(rules.SaturatedOverlayDetector())
    with pytest.raises(EvaluationRefused):
        rules.CombinedPoint(rules.OverlayPoint(), rules.OverlayPoint())
    with pytest.raises(EvaluationRefused):
        rules.CombinedPoint(detector.PostProcessing(), detector.PostProcessing())
    with pytest.raises(EvaluationRefused):
        rules.CombinedDetector(CountingModel()).boxes_of_points(
            _frame(_anatomy()), [rules.OverlayPoint()]
        )


def test_no_run_can_select_the_rule():
    package = pathlib.Path(rules.__file__).parent
    for path in package.glob("*.py"):
        if path.name.startswith("text_evaluation"):
            continue
        assert "text_evaluation_rules" not in path.read_text(encoding="utf-8")
