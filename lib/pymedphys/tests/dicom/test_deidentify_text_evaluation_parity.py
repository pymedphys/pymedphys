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

"""The resize parity of a model's boxes, with a stand-in network."""

import dataclasses
import functools
import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_detector as detector
from pymedphys._dicom.deidentify import text_evaluation_injection as injection
from pymedphys._dicom.deidentify import text_evaluation_models as models
from pymedphys._dicom.deidentify import text_evaluation_parity as parity
from pymedphys._dicom.deidentify import text_evaluation_phantoms as phantoms
from pymedphys._dicom.deidentify.text_evaluation_frames import EvaluationRefused

MODEL = models.PADDLE_MODELS[0]


def bright(tensor):
    """A stand-in network whose map is the input's brightness, undoing the
    first channel's normalisation."""
    plane = tensor[0, 0] * MODEL.network_input.deviation[0]
    plane += MODEL.network_input.mean[0]
    return [np.clip(plane, 0, 1)[np.newaxis, np.newaxis]]


def _settings(**options):
    return evaluation.EvaluationSettings(
        points=(detector.published_point(MODEL), detector.PostProcessing()),
        plan=injection.InjectionPlan(texts=2, heights=(7.0,), contents=("letter",)),
        evaluated="all",
        **options,
    )


STAND_IN = functools.partial(
    detector.EvaluationDetector, network=bright, network_name="bright"
)


def test_the_resizes_are_compared_frame_by_frame():
    pytest.importorskip("cv2")
    cases = [
        phantoms.PhantomCase(phantoms.Phantom("ct-thorax", 200, 2.0), seed=seed)
        for seed in range(2)
    ]
    found = parity.resize_parity(
        cases,
        MODEL,
        _settings(),
        first=detector.published_variant(MODEL, "cv2"),
        second=detector.published_variant(MODEL, "harness"),
        detector=STAND_IN,
    )
    assert found["format"] == parity.FORMAT
    assert (found["first"], found["second"]) == ("cv2", "harness")
    assert found["cases"] == 2 and not found["crashed"]
    for point in found["points"]:
        # Each frame as read and with text burned in.
        assert point["frames"] == 4
        assert point["texts"] == 4
        assert (
            point["regions_first"] - point["regions_only_first"]
            == point["regions_second"] - point["regions_only_second"]
        )
        assert point["texts_changed"] >= abs(
            point["fully_covered_first"] - point["fully_covered_second"]
        )
    text = json.dumps(found)
    assert "ct-thorax-200" not in text


def test_the_same_resize_changes_nothing():
    case = phantoms.PhantomCase(phantoms.Phantom("ct-thorax", 96, 4.0), seed=1)
    harness = detector.published_variant(MODEL, "harness")
    renamed = dataclasses.replace(harness, name="again")
    with pytest.raises(EvaluationRefused):
        parity.resize_parity([case], MODEL, _settings(), first=harness, second=harness)
    changed = dataclasses.replace(
        harness,
        network_input=dataclasses.replace(harness.network_input, resampler="cv2"),
        name="other",
        parameters=dataclasses.replace(harness.parameters, limit_side=640),
    )
    with pytest.raises(EvaluationRefused):
        parity.resize_parity([case], MODEL, _settings(), first=renamed, second=changed)


def test_a_case_that_raises_is_counted_by_where():
    @dataclasses.dataclass(frozen=True)
    class Raising:
        collection: str = "c"
        case: str = "SECRET^CASE"

        def read(self):
            raise ValueError("SECRET^CASE")

    harness = detector.published_variant(MODEL, "harness")
    cv2_like = dataclasses.replace(
        harness,
        network_input=dataclasses.replace(harness.network_input, resampler="cv2"),
    )
    found = parity.resize_parity(
        [Raising()],
        MODEL,
        _settings(),
        first=cv2_like,
        second=harness,
        detector=STAND_IN,
    )
    assert sum(found["crashed"].values()) == 1
    assert "SECRET" not in json.dumps(found)
