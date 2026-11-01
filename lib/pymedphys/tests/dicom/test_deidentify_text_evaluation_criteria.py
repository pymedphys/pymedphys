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

"""The acceptance criteria, on summaries made by hand."""

import dataclasses

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_criteria as criteria
from pymedphys._dicom.deidentify import text_evaluation_injection as injection
from pymedphys._dicom.deidentify import text_evaluation_phantoms as phantoms
from pymedphys._dicom.deidentify.text_evaluation_detector import PostProcessing
from pymedphys._dicom.deidentify.text_evaluation_frames import EvaluationRefused

CT = "CT Image Storage"
RT = "RT Image Storage"
HIGH = "16 to under 32 sigma"
MIDDLE = "4 to under 8 sigma"
LOW = "2 to under 4 sigma"


def _sensitivity(texts, full, missed=0, wilson=None, bootstrap=None):
    share = full / texts if texts else None
    return {
        "texts": texts,
        "fully_covered": full,
        "share": share,
        "wilson": wilson if wilson is not None else [share, share],
        "bootstrap": bootstrap if bootstrap is not None else [share, share],
        "missed": missed,
        "partly_covered": texts - full - missed,
    }


def _false_positives(frames, flagged, tissue=0.0, wilson=None, bootstrap=None):
    share = flagged / frames if frames else None
    return {
        "frames": frames,
        "share": share,
        "wilson": wilson if wilson is not None else [share, share],
        "bootstrap": bootstrap if bootstrap is not None else [share, share],
        "tissue_blacked_out": tissue,
        "tissue_blacked_out_bootstrap": [tissue, tissue],
    }


def _cell(iod, contrast, height, **measure):
    return {
        "value": {"iod": iod, "contrast": contrast, "height": height},
        "sensitivity": _sensitivity(**measure),
    }


def _point(index=0, cells=(), iods=(), sides=(), truths=()):
    return {
        "index": index,
        "by": {
            "iod+contrast+height": list(cells),
            "iod": [
                {
                    "value": {"iod": iod},
                    "sensitivity": _sensitivity(0, 0),
                    "false_positives": _false_positives(**fp),
                }
                for iod, fp in iods
            ],
            "iod+slice_side": [
                {
                    "value": {"iod": iod, "slice_side": side},
                    "false_positives": _false_positives(**fp),
                }
                for iod, side, fp in sides
            ],
            "collection+truth": [
                {
                    "value": {"collection": collection, "truth": truth},
                    "sensitivity": _sensitivity(**measure),
                }
                for collection, truth, measure in truths
            ],
        },
    }


def _passing(index=0):
    return _point(
        index,
        cells=[
            _cell(CT, HIGH, "7 px", texts=1000, full=1000),
            _cell(CT, MIDDLE, "10 px", texts=1000, full=980),
            # Reported only: below either contrast or height.
            _cell(CT, LOW, "10 px", texts=1000, full=10),
            _cell(CT, HIGH, "5 px", texts=1000, full=10),
            _cell(CT, HIGH, "2 mm", texts=1000, full=10),
        ],
        iods=[
            (CT, {"frames": 1000, "flagged": 10}),
            (RT, {"frames": 400, "flagged": 16}),
        ],
        sides=[(CT, "512 to under 768 pixels", {"frames": 600, "flagged": 6})],
        truths=[
            ("MIDI-B-Synthetic-Validation", "annotated", {"texts": 50, "full": 45}),
            ("NSCLC-Radiomics", "injected", {"texts": 10, "full": 0, "missed": 10}),
        ],
    )


def _failures(point, chosen=criteria.CHOSEN_CRITERIA):
    summary = {"points": [_passing(), {**point, "index": 1}]}
    return criteria.assess(summary, chosen)[1]["failures"]


def test_the_chosen_criteria_are_as_picked():
    chosen = criteria.CHOSEN_CRITERIA
    assert (chosen.bound, chosen.bootstrap) == ("interval", True)
    assert (chosen.min_texts, chosen.min_frames) == (400, 300)
    assert (chosen.max_loss, chosen.baseline) == (0.02, 0)
    assert [each.minimum for each in chosen.sensitivity] == [0.99, 0.95]
    assert chosen.sensitivity[0].contrast == (
        "16 to under 32 sigma",
        "32 to under 64 sigma",
        "64 sigma or more",
    )
    assert chosen.sensitivity[1].contrast == (
        "4 to under 8 sigma",
        "8 to under 16 sigma",
    )
    limits = {
        each.max_with_a_region
        for each in chosen.false_positives
        if each.max_with_a_region is not None
    }
    assert limits == {0.02, 0.05}
    assert chosen.false_positives[-1].iod == "*"
    assert chosen.false_positives[-1].max_tissue_blacked_out == 0.0001
    assert criteria.HELD_OUT_COLLECTIONS == ("Pediatric-CT-SEG",)
    assert criteria.assess({"points": [_passing()]}, chosen)[0]["meets"]


def test_sensitivity_is_held_by_contrast_and_height():
    weak = _passing()
    weak["by"]["iod+contrast+height"][0] = _cell(
        CT, HIGH, "7 px", texts=1000, full=1000, wilson=[0.985, 1.0]
    )
    assert _failures(weak) == [
        f"sensitivity: {CT}, {HIGH}, 7 px: Wilson 0.985 below 0.99"
    ]
    few = _passing()
    few["by"]["iod+contrast+height"][1] = _cell(
        CT, MIDDLE, "10 px", texts=399, full=399
    )
    assert _failures(few) == [f"sensitivity: {CT}, {MIDDLE}, 10 px: too few texts"]


def test_the_bootstrap_bound_must_pass_too():
    clustered = _passing()
    clustered["by"]["iod+contrast+height"][1] = _cell(
        CT, MIDDLE, "10 px", texts=1000, full=980, bootstrap=[0.9, 0.99]
    )
    assert _failures(clustered) == [
        f"sensitivity: {CT}, {MIDDLE}, 10 px: bootstrap 0.900 below 0.95"
    ]
    lone = _passing()
    lone["by"]["iod+contrast+height"][0]["sensitivity"]["bootstrap"] = None
    assert _failures(lone) == [
        f"sensitivity: {CT}, {HIGH}, 7 px: no bootstrap interval"
    ]
    without = dataclasses.replace(criteria.CHOSEN_CRITERIA, bootstrap=False)
    assert not _failures(clustered, without)


def test_false_positives_are_held_by_iod_and_slice_size():
    point = _passing()
    point["by"]["iod+slice_side"].append(
        (
            {
                "value": {"iod": CT, "slice_side": "1024 pixels or more"},
                "false_positives": _false_positives(400, 20),
            }
        )
    )
    assert _failures(point) == [
        f"false positives: {CT}, 1024 pixels or more: Wilson 0.050 of frames "
        "with a region, above 0.02",
        f"false positives: {CT}, 1024 pixels or more: bootstrap 0.050 of frames "
        "with a region, above 0.02",
    ]
    # A projection image may have more, but not past its own limit.
    point = _passing()
    point["by"]["iod"][1]["false_positives"] = _false_positives(400, 24)
    assert len(_failures(point)) == 2
    point = _passing()
    point["by"]["iod"][0]["false_positives"] = _false_positives(1000, 0, tissue=0.0002)
    assert _failures(point) == [
        f"false positives: {CT}: 0.0002 of tissue blacked out, above 0.0001",
        f"false positives: {CT}: bootstrap 0.0002 of tissue blacked out, above 0.0001",
    ]


def test_no_answer_key_text_may_be_missed():
    point = _passing()
    point["by"]["collection+truth"][0]["sensitivity"] = _sensitivity(50, 45, missed=1)
    assert _failures(point) == [
        "missed: MIDI-B-Synthetic-Validation: 1 annotated texts missed, above 0"
    ]
    point["by"]["collection+truth"] = []
    assert _failures(point) == ["missed: no annotated texts of MIDI-B"]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: criteria.AcceptanceCriteria(bound="estimate", bootstrap=True),
        lambda: criteria.AcceptanceCriteria(max_loss=2.0),
        lambda: criteria.SensitivityCriterion(1.5),
        lambda: criteria.SensitivityCriterion(0.9, iod=("*",)),
        lambda: criteria.SensitivityCriterion(0.9, contrast=()),
        lambda: criteria.FalsePositiveCriterion(max_with_a_region=-0.1),
        lambda: criteria.MissedTextCriterion(""),
        lambda: criteria.contrasts_from(5.0),
        lambda: criteria.contrasts_between(4.0, 15.0),
    ],
)
def test_criteria_out_of_range_are_refused(factory):
    with pytest.raises(EvaluationRefused):
        factory()


def test_a_summary_gives_every_cell_the_criteria_read():
    plan = injection.InjectionPlan(texts=2, heights=(10.0,), contrasts=(16.0,))
    cases = [
        phantoms.PhantomCase(phantoms.Phantom("ct-thorax", 96, 4.0), seed=seed)
        for seed in range(3)
    ]

    class Nothing:
        """A detector that finds nothing."""

        method = {"network": "nothing"}

        def boxes_of_points(self, frame, points):
            del frame
            return [()] * len(points)

    summary = evaluation.summarise(
        evaluation.evaluate(
            cases,
            Nothing,
            evaluation.EvaluationSettings(
                points=(PostProcessing(),), plan=plan, evaluated="all"
            ),
        ),
        replicates=50,
    )
    by = summary["points"][0]["by"]
    for grouping in ("iod+contrast+height", "iod+slice_side", "collection+truth"):
        assert by[grouping], grouping
        assert all("bootstrap" in row["sensitivity"] for row in by[grouping])
    assert all("bootstrap" in row["false_positives"] for row in by["iod+slice_side"])
    texts = sum(row["sensitivity"]["texts"] for row in by["collection+truth"])
    missed = sum(row["sensitivity"]["missed"] for row in by["collection+truth"])
    assert texts == missed > 0
    failures = criteria.assess(summary, criteria.CHOSEN_CRITERIA)[0]["failures"]
    assert "missed: no annotated texts of MIDI-B" in failures
    assert any("too few" in each for each in failures)
