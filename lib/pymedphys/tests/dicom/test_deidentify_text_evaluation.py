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

"""The text detector evaluation's measures, summary, criteria, and readers.

Detectors here are stand-ins whose boxes are known, so that every count can
be derived by hand. Every value is invented."""

import dataclasses
import json
import pathlib
import re

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_detection
from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_criteria as criteria_module
from pymedphys._dicom.deidentify import text_evaluation_injection as injection
from pymedphys._dicom.deidentify import text_evaluation_markdown as markdown
from pymedphys._dicom.deidentify import text_evaluation_phantoms as phantoms
from pymedphys._dicom.deidentify import text_evaluation_sources as sources
from pymedphys._dicom.deidentify.text_detection import DetectionParameters, TextBox
from pymedphys._dicom.deidentify.text_evaluation_detector import PostProcessing
from pymedphys._dicom.deidentify.text_evaluation_frames import (
    BurnedText,
    EvaluationFrame,
    EvaluationRefused,
)

from . import _synthetic_nrrd as files
from ._text_evaluation_stand_ins import (
    SECRET,
    SHAPE,
    BoxDetector,
    box_detector,
    Frames,
    Raising,
    _frame,
    _text,
    _settings,
    _run,
    _ct_dataset,
)
from . import _synthetic_references as synthetic

# -- Split --------------------------------------------------------------------


def test_the_split_holds_out_about_a_third_by_a_fixed_rule():
    parts = [evaluation.split_of("c", f"case-{index}") for index in range(3000)]
    assert parts.count("held-out") / 3000 == pytest.approx(1 / 3, abs=0.03)
    assert parts == [evaluation.split_of("c", f"case-{index}") for index in range(3000)]
    assert evaluation.split_of("c", "x", held_out_collections=("c",)) == "held-out"


def test_only_the_part_asked_for_is_evaluated():
    cases = [
        Frames("c", f"case-{index}", (_frame(case=f"case-{index}"),))
        for index in range(12)
    ]
    tuning = _run(cases, evaluated="tuning")
    held = _run(cases, evaluated="held-out")
    split = tuning["split"]["cases"]
    assert split["tuning"] + split["held-out"] == 12
    assert tuning["points"][0]["false_positives"]["frames"] == split["tuning"]
    assert held["points"][0]["false_positives"]["frames"] == split["held-out"]


@dataclasses.dataclass(frozen=True)
class Subjected:
    """A case whose frames are given, of a subject that other cases share."""

    collection: str
    case: str
    subject: str
    frames: tuple

    def read(self):
        yield from self.frames


def _parted(part, count):
    """Case names that the split puts in ``part``, by their own names."""
    names = (f"case-{index}" for index in range(1000))
    return [name for name in names if evaluation.split_of("c", name) == part][:count]


def test_a_subjects_cases_stay_in_one_part_and_resample_as_one():
    (tuning,) = _parted("tuning", 1)
    (held,) = _parted("held-out", 1)
    subject = "patient/one"
    cases = [
        Subjected("c", name, subject, (_frame(case=name),)) for name in (tuning, held)
    ]
    run = evaluation.evaluate(cases, box_detector, _settings())
    part = evaluation.split_of("c", subject)
    assert [each.split for each in run.results] == [part, part]
    assert "patient/one" not in repr(run.results)
    # One subject is one cluster, too few for the bootstrap's interval.
    summary = evaluation.summarise(run, replicates=200)
    assert summary["points"][0]["false_positives"]["bootstrap"] is None
    other = Subjected("c", "case-x", "patient/two", (_frame(case="case-x"),))
    run = evaluation.evaluate([*cases, other], box_detector, _settings())
    summary = evaluation.summarise(run, replicates=200)
    assert summary["points"][0]["false_positives"]["bootstrap"] is not None
    published = json.dumps(summary)
    assert "patient/one" not in published and "patient/two" not in published


def test_a_subject_must_be_a_name():
    case = Subjected("c", "a", "", (_frame(),))
    with pytest.raises(EvaluationRefused):
        evaluation.subject_of(case)
    assert evaluation.subject_of(Frames("c", "a", ())) == "a"


# -- Intervals ----------------------------------------------------------------


def test_wilson_intervals_match_their_formula():
    assert evaluation.wilson(0, 0) is None
    low, high = evaluation.wilson(0, 10)
    assert low == 0 and high == pytest.approx(0.2775, abs=1e-4)
    low, high = evaluation.wilson(10, 10)
    assert high == pytest.approx(1) and low == pytest.approx(0.7225, abs=1e-4)
    low, high = evaluation.wilson(50, 100)
    assert (low, high) == pytest.approx((0.4038, 0.5962), abs=1e-4)


def test_the_cluster_bootstrap_resamples_cases():
    assert (
        evaluation.cluster_bootstrap(
            np.array([1]), np.array([2]), replicates=10, seed=0
        )
        is None
    )
    same = evaluation.cluster_bootstrap(
        np.array([1, 2, 3]), np.array([2, 4, 6]), replicates=100, seed=0
    )
    assert same == pytest.approx((0.5, 0.5))
    numerators = np.array([0, 10, 0, 10, 5, 5])
    denominators = np.full(6, 10)
    first = evaluation.cluster_bootstrap(
        numerators, denominators, replicates=500, seed=1
    )
    again = evaluation.cluster_bootstrap(
        numerators, denominators, replicates=500, seed=1
    )
    assert first == again
    assert first[0] < 0.5 < first[1]


# -- Measures -----------------------------------------------------------------


def test_a_frame_without_text_counts_its_regions_and_tissue():
    stored = np.full(SHAPE, 24, np.uint16)  # air, -1000 HU
    stored[32:, :] = 1064  # tissue below row 32
    summary = _run([Frames("c", "a", (_frame(stored),))])
    measure = summary["points"][0]["false_positives"]
    assert measure["frames"] == 1 and measure["with_a_region"] == 1
    assert measure["regions"] == 2
    # The boxes are those that the run's own code gives of the map.
    blacked = np.zeros(SHAPE, bool)
    for box in _boxes():
        blacked[box.top : box.bottom, box.left : box.right] = True
    tissue = np.zeros(SHAPE, bool)
    tissue[32:] = True
    assert measure["pixels_blacked_out"] == pytest.approx(blacked.mean())
    assert measure["tissue_blacked_out"] == pytest.approx(
        (blacked & tissue).sum() / tissue.sum()
    )
    assert measure["blacked_out_over_tissue"] == pytest.approx(
        (blacked & tissue).sum() / blacked.sum()
    )
    zones = summary["points"][0]["zones"]["negative"]
    assert sum(zones.values()) == 2


def _boxes():
    (full_range, *_) = BoxDetector().probabilities(_frame())
    return text_detection.boxes_from_probability(
        full_range.probability, SHAPE, DetectionParameters()
    )


def test_text_is_fully_covered_only_where_every_pixel_of_its_ink_is():
    covered = _text(9, 10, 6, 28, font="f", contrast="c", height="6 px")
    half = _text(42, 22, 6, 20, font="f", contrast="c", height="6 px")
    missed = _text(26, 50, 4, 10, font="f", contrast="c", height="4 px")
    summary = _run([Frames("c", "a", (_frame(texts=(covered, half, missed)),))])
    point = summary["points"][0]
    sensitivity = point["sensitivity"]
    assert sensitivity["texts"] == 3
    assert sensitivity["fully_covered"] == 1
    assert sensitivity["share"] == pytest.approx(1 / 3)
    assert (sensitivity["partly_covered"], sensitivity["missed"]) == (1, 1)
    shares = [each["count"] for each in sensitivity["ink_covered"]["bins"]]
    assert shares[-1] == 1  # all of its ink
    assert shares[0] == 1  # none of its ink
    # Every box meets a text's zone, so none is away from text.
    assert point["away_from_text"]["regions"] == 0
    assert point["away_from_text"]["frames"] == 1
    assert point["false_positives"]["frames"] == 0


def test_a_frame_without_text_is_measured_as_it_is_and_with_text():
    plan = injection.InjectionPlan(
        texts=2, heights=(7.0,), positions=("air", "edge"), contents=("letter",)
    )
    case = phantoms.PhantomCase(phantoms.Phantom("ct-thorax", 96, 4.0), seed=1)
    summary = evaluation.summarise(
        evaluation.evaluate([case], box_detector, _settings(plan=plan)), replicates=50
    )
    point = summary["points"][0]
    assert point["false_positives"]["frames"] == 1
    assert point["away_from_text"]["frames"] == 1
    assert point["sensitivity"]["texts"] + sum(summary["not_placed"].values()) == 2
    by = point["by"]
    assert {
        "font",
        "contrast",
        "style",
        "position",
        "iod",
        "iod+contrast+height_px",
    } <= set(by)


def _known(frame, known_text):
    return dataclasses.replace(frame, known_text=known_text)


def test_frames_whose_text_is_unknown_are_counted_apart_from_false_positives():
    plan = injection.InjectionPlan(
        texts=2, heights=(7.0,), positions=("air", "edge"), contents=("letter",)
    )
    phantom = phantoms.Phantom("ct-thorax", 96, 4.0)
    frame = _known(
        phantoms.phantom_frame(phantom, np.random.default_rng(1), case="a"), "unknown"
    )
    summary = _run([Frames("c", "a", (frame,))], plan=plan)
    point = summary["points"][0]
    assert point["false_positives"]["frames"] == 0
    assert point["away_from_text"]["frames"] == 0
    assert point["text_unknown"]["frames"] == 1
    assert point["text_unknown"]["regions"] == 2
    assert point["text_unknown_away_from_injected"]["frames"] == 1
    assert point["sensitivity"]["texts"] >= 1
    known = {row["value"]["known_text"]: row for row in point["by"]["known_text"]}
    assert set(known) == {"unknown"}
    assert known["unknown"]["sensitivity"]["texts"] == point["sensitivity"]["texts"]
    assert sum(point["zones"]["unknown"].values()) == 2
    page = markdown.markdown(summary)
    assert "## Where text is unknown" in page
    assert "## Where text is unknown" not in markdown.markdown(
        _run([Frames("c", "a", (_frame(),))])
    )


def test_annotated_text_is_counted_once_and_injected_text_beside_it():
    phantom = phantoms.Phantom("ct-thorax", 96, 4.0)
    frame = phantoms.phantom_frame(phantom, np.random.default_rng(1), case="a")
    annotated = BurnedText(9, 10, np.ones((6, 28)), 6.0, {"truth": "annotated"})
    frame = dataclasses.replace(frame, texts=(annotated,), known_text="annotated")
    plan = injection.InjectionPlan(
        texts=2, heights=(7.0,), positions=("air", "edge"), contents=("letter",)
    )
    alone = _run([Frames("c", "a", (frame,))])["points"][0]
    assert alone["sensitivity"]["texts"] == 1
    assert alone["away_from_text"]["frames"] == 1
    point = _run([Frames("c", "a", (frame,))], plan=plan)["points"][0]
    truths = {
        row["value"]["truth"]: row["sensitivity"]["texts"]
        for row in point["by"]["truth"]
    }
    assert truths["annotated"] == 1
    assert truths.get("injected", 0) == point["sensitivity"]["texts"] - 1
    assert point["away_from_text"]["frames"] == 1 + (truths.get("injected", 0) > 0)
    assert point["false_positives"]["frames"] == 0


def test_what_is_known_of_a_frames_text_must_be_known():
    with pytest.raises(EvaluationRefused):
        _frame(known_text="maybe")


def test_counts_are_kept_by_each_stratum_and_cross():
    texts = (
        _text(9, 10, 6, 28, font="a", contrast="4 to under 8 sigma", height="6 px"),
        _text(26, 50, 4, 10, font="b", contrast="4 to under 8 sigma", height="4 px"),
    )
    summary = _run([Frames("c", "a", (_frame(texts=texts),))])
    by = summary["points"][0]["by"]
    fonts = {
        row["value"]["font"]: row["sensitivity"]["fully_covered"] for row in by["font"]
    }
    assert fonts == {"a": 1, "b": 0}
    cells = by["iod+contrast+height_px"]
    assert {
        (row["value"]["height_px"], row["sensitivity"]["texts"]) for row in cells
    } == {("5 to under 7 px", 1), ("3 to under 5 px", 1)}
    # A frame has no font or height, so only a grouping of frames' own
    # dimensions counts frames.
    assert all("false_positives" not in row for row in by["font"] + cells)
    assert all("away_from_text" not in row for row in by["font"] + cells)
    assert all("false_positives" in row for row in by["iod"])


def test_strata_read_from_low_to_high():
    texts = tuple(
        _text(2 + 12 * row, 4, 6, 10, font="f", contrast=contrast, height=height)
        for row, (contrast, height) in enumerate(
            (
                ("16 to under 32 sigma", "40 px"),
                ("2 to under 4 sigma", "5 px"),
                ("64 sigma or more", "10 px"),
            )
        )
    )
    by = _run([Frames("c", "a", (_frame(texts=texts),))])["points"][0]["by"]
    assert [row["value"]["contrast"] for row in by["contrast"]] == [
        "2 to under 4 sigma",
        "16 to under 32 sigma",
        "64 sigma or more",
    ]
    assert [row["value"]["height"] for row in by["height"]] == [
        "5 px",
        "10 px",
        "40 px",
    ]


def test_points_that_differ_count_differently_from_one_pass():
    points = (
        PostProcessing(),
        PostProcessing(box_threshold=0.95),
        PostProcessing(renderings=("white-top-hat",)),
    )
    summary = _run([Frames("c", "a", (_frame(),))], points=points)
    regions = [point["false_positives"]["regions"] for point in summary["points"]]
    assert regions == [2, 0, 0]


def test_frames_not_read_and_text_not_placed_are_counted():
    cases = [
        Frames(
            "c",
            "a",
            (sources.Skipped("not-read"), sources.Skipped("not-read"), _frame()),
        ),
    ]
    summary = _run(cases, plan=injection.InjectionPlan(texts=1, heights=(60.0,)))
    assert summary["skipped"] == {"not-read": 2}
    assert sum(summary["not_placed"].values()) == 1


def test_a_case_that_raises_is_counted_by_where_and_never_by_its_message():
    summary = _run([Raising(), Frames("c", "b", (_frame(case="b"),))])
    crashed = summary["collections"]["collection"]["crashed"]
    assert list(crashed.values()) == [1]
    (site,) = crashed
    assert re.fullmatch(
        r"ValueError at _text_evaluation_stand_ins\.py:\d+ in read", site
    )
    assert SECRET not in json.dumps(summary)
    assert summary["points"][0]["false_positives"]["frames"] == 1


def test_the_summary_and_page_name_no_case():
    cases = [Frames("c", SECRET, (_frame(),)), Raising()]
    summary = _run(cases, plan=injection.InjectionPlan(texts=1))
    page = markdown.markdown(summary)
    assert SECRET not in json.dumps(summary)
    assert SECRET not in page
    assert summary["format"] == evaluation.FORMAT


def test_workers_give_the_same_summary_as_one_process():
    cases = [
        phantoms.PhantomCase(phantoms.Phantom("ct-head", 96, 2.5), seed=seed)
        for seed in range(4)
    ]
    plan = injection.InjectionPlan(texts=2)
    one = _run(cases, plan=plan)
    two = _run(cases, plan=plan, workers=2)
    del one["software"], two["software"]
    assert one == two


def test_settings_that_measure_nothing_are_refused():
    with pytest.raises(EvaluationRefused):
        evaluation.EvaluationSettings(points=())
    with pytest.raises(EvaluationRefused):
        evaluation.EvaluationSettings(points=(PostProcessing(),), negatives=False)
    with pytest.raises(EvaluationRefused):
        evaluation.EvaluationSettings(points=(PostProcessing(),), evaluated="test")
    with pytest.raises(EvaluationRefused):
        evaluation.EvaluationSettings(
            points=(PostProcessing(),), crosses=(("iod", "colour"),)
        )


def test_every_point_keeps_every_stratum_and_the_page_details_the_first():
    # The loss rule compares every point with the baseline in every
    # stratum, so no point's strata may be left out of the summary; only
    # the page shows fewer, for a large grid.
    points = tuple(
        PostProcessing(box_threshold=0.5 + index / 100) for index in range(11)
    )
    summary = _run(
        [Frames("c", "a", (_frame(texts=(_text(9, 10, 6, 28),)),))], points=points
    )
    groupings = {"+".join(each) for each in _settings().dimensions if each}
    assert all(set(point["by"]) == groupings for point in summary["points"])
    page = markdown.markdown(summary)
    assert "## Point 0 by stratum" in page
    assert "## Point 1 by stratum" not in page
    assert "The other points' counts by stratum are in the JSON summary." in page
    every = markdown.markdown(summary, detailed=range(11))
    assert "## Point 10 by stratum" in every
    assert "in the JSON summary" not in every


# -- Criteria -----------------------------------------------------------------


def _summary_for_criteria():
    texts = tuple(
        _text(9, 10, 6, 28, contrast="8 to under 16 sigma", height="6 px")
        for _ in range(1)
    )
    frames = [_frame(case=f"c{index}", texts=texts) for index in range(40)]
    negatives = [_frame(case=f"n{index}") for index in range(40)]
    cases = [
        Frames("c", f"c{index}", (each,))
        for index, each in enumerate(frames + negatives)
    ]
    points = (PostProcessing(), PostProcessing(box_threshold=0.95))
    return _run(cases, points=points)


def test_criteria_are_checked_against_each_cell():
    summary = _summary_for_criteria()
    criteria = criteria_module.AcceptanceCriteria(
        sensitivity=(
            criteria_module.SensitivityCriterion(
                0.9, contrast="8 to under 16 sigma", height_px="5 to under 7 px"
            ),
        ),
        false_positives=(
            criteria_module.FalsePositiveCriterion(max_with_a_region=0.5),
        ),
        bound="estimate",
    )
    first, second = criteria_module.assess(summary, criteria)
    # The first point covers every text, but every frame without text has
    # a region; the second finds nothing.
    assert not first["meets"]
    assert any("frames with a region" in each for each in first["failures"])
    assert not any(each.startswith("sensitivity") for each in first["failures"])
    assert any(each.startswith("sensitivity") for each in second["failures"])
    assert not any(each.startswith("false positives") for each in second["failures"])


def test_the_interval_bound_is_stricter_than_the_estimate():
    summary = _summary_for_criteria()
    criterion = (
        criteria_module.SensitivityCriterion(
            0.95, contrast="8 to under 16 sigma", height_px="5 to under 7 px"
        ),
    )
    estimate = criteria_module.assess(
        summary,
        criteria_module.AcceptanceCriteria(sensitivity=criterion, bound="estimate"),
    )
    interval = criteria_module.assess(
        summary, criteria_module.AcceptanceCriteria(sensitivity=criterion)
    )
    assert estimate[0]["meets"]
    assert not interval[0]["meets"]  # 40 of 40 has a Wilson lower bound of 0.912


def test_too_little_evidence_fails():
    summary = _summary_for_criteria()
    criteria = criteria_module.AcceptanceCriteria(
        sensitivity=(
            criteria_module.SensitivityCriterion(
                0.5, contrast="8 to under 16 sigma", height_px="5 to under 7 px"
            ),
        ),
        min_texts=41,
        bound="estimate",
    )
    (first, _) = criteria_module.assess(summary, criteria)
    assert first["failures"] == [
        "sensitivity: CT Image Storage, 8 to under 16 sigma, 5 to under 7 px: too few texts"
    ]


def test_no_stratum_may_lose_more_than_the_margin():
    summary = _summary_for_criteria()
    criteria = criteria_module.AcceptanceCriteria(max_loss=0.05)
    first, second = criteria_module.assess(summary, criteria)
    assert first["meets"]
    assert any(
        each.startswith("loss: iod CT Image Storage: sensitivity")
        for each in second["failures"]
    )
    with pytest.raises(EvaluationRefused):
        criteria_module.assess(summary, dataclasses.replace(criteria, baseline=5))


def test_the_page_shows_the_trade_off_and_the_criteria():
    summary = _summary_for_criteria()
    assessed = criteria_module.assess(
        summary, criteria_module.AcceptanceCriteria(max_loss=0.05)
    )
    page = markdown.markdown(summary, assessed)
    assert "## Trade-off" in page
    assert "| Point | box threshold |" in page
    assert "Meets the criteria" in page
    assert "Point 1 fails" in page
    columns = None
    for line in page.splitlines():
        assert line == line.rstrip()
        if not line.startswith("|"):
            columns = None
            continue
        assert line.endswith("|")
        # Every row of a table has as many cells as its header.
        cells = line.count("|") - line.count("\\|")
        columns = cells if columns is None else columns
        assert cells == columns, line
    assert (
        "| Font | Texts | Fully covered | Wilson | Partly covered | Missed |\n" in page
    )


# -- Readers ------------------------------------------------------------------


def test_dicom_frames_are_the_stored_values_a_run_searches():
    frames = np.arange(2 * 6 * 8).reshape(2, 6, 8) + 1000
    data = synthetic.written(
        _ct_dataset(
            frames, PixelSpacing=[0.7, 0.9], RescaleSlope=1, RescaleIntercept=-1024
        )
    )
    found = sources.dicom_frames(data, collection="c", case="a", first=3)
    assert [each.number for each in found] == [3, 4]
    for frame, expected in zip(found, frames):
        assert np.array_equal(frame.stored, expected)
        assert frame.pixel_spacing == pytest.approx(0.9)
        assert (frame.slope, frame.intercept) == (1.0, -1024.0)
        assert frame.stored_range == (0, 4095)
        assert frame.iod == "CT Image Storage"
        assert frame.hounsfield


def test_enhanced_images_take_spacing_and_rescale_from_functional_groups():
    from pymedphys._imports import pydicom  # pylint: disable = import-outside-toplevel

    def group(**attributes):
        item = pydicom.Dataset()
        for keyword, value in attributes.items():
            setattr(item, keyword, value)
        return item

    shared = group(
        PixelMeasuresSequence=[group(PixelSpacing=[0.4, 0.5])],
        PixelValueTransformationSequence=[
            group(RescaleSlope=2, RescaleIntercept=-2048, RescaleType="HU")
        ],
    )
    per_frame = [
        group(PixelMeasuresSequence=[group(PixelSpacing=[0.25, 0.25])]),
        group(),
    ]
    dataset = _ct_dataset(
        np.zeros((2, 4, 4)) + 7,
        SharedFunctionalGroupsSequence=[shared],
        PerFrameFunctionalGroupsSequence=per_frame,
    )
    found = sources.dicom_frames(synthetic.written(dataset), collection="c", case="a")
    assert [each.pixel_spacing for each in found] == [0.25, 0.5]
    assert all((each.slope, each.intercept) == (2.0, -2048.0) for each in found)


def test_rt_images_take_their_image_plane_spacing():
    dataset = _ct_dataset(
        np.zeros((1, 4, 4)), Modality="RTIMAGE", ImagePlanePixelSpacing=[0.4, 0.4]
    )
    dataset.SOPClassUID = "1.2.840.10008.5.1.4.1.1.481.1"
    (frame,) = sources.dicom_frames(
        synthetic.written(dataset), collection="c", case="a"
    )
    assert frame.pixel_spacing == pytest.approx(0.4)
    assert frame.iod == "RT Image Storage"
    assert frame.modality == "RTIMAGE"


def test_private_sop_classes_are_not_named():
    dataset = _ct_dataset(np.zeros((1, 4, 4)))
    dataset.SOPClassUID = "1.3.12.2.1107.5.9.1"
    (frame,) = sources.dicom_frames(
        synthetic.written(dataset), collection="c", case="a"
    )
    assert frame.iod == sources.PRIVATE_SOP_CLASS


def test_files_without_frames_are_skipped_by_why():
    assert sources.dicom_frames(
        b"not DICOM", collection="c", case="a"
    ) == sources.Skipped("not-read")
    no_pixels = synthetic.ct_slice(0)
    assert sources.dicom_frames(
        synthetic.written(no_pixels), collection="c", case="a"
    ) == sources.Skipped("no-pixel-data")
    floating = _ct_dataset(np.zeros((1, 4, 4)))
    for keyword in ("PixelData", "BitsStored", "HighBit", "PixelRepresentation"):
        delattr(floating, keyword)
    floating.BitsAllocated = 32
    floating.FloatPixelData = np.zeros(16, "<f4").tobytes()
    assert sources.dicom_frames(
        synthetic.written(floating), collection="c", case="a"
    ) == sources.Skipped("float-pixel-data")


def test_a_dicom_case_reads_its_files_in_turn(tmp_path):
    paths = []
    for index in range(2):
        path = tmp_path / f"{index}.dcm"
        path.write_bytes(synthetic.written(_ct_dataset(np.full((2, 4, 4), index))))
        paths.append(str(path))
    paths.append(str(tmp_path / "missing.dcm"))
    case = sources.DicomCase("c", "a", tuple(paths))
    read = list(case.read())
    assert [each.number for each in read[:4]] == [0, 1, 2, 3]
    assert read[4] == sources.Skipped("not-opened")


def test_hanseg_volumes_are_cases_of_slices(tmp_path):
    grid = files.Grid(
        origin=(0.0, 0.0, 0.0),
        axes=((0.8, 0.0, 0.0), (0.0, 1.2, 0.0), (0.0, 0.0, 2.5)),
        shape=(3, 10, 12),
    )
    values = np.full(grid.shape, -1000, np.int16)
    path = tmp_path / "HaN-Seg.zip"
    files.hanseg_zip(
        path,
        {
            "case_02": {"IMG_CT.nrrd": files.nrrd_file(values, grid)},
            "case_01": {"IMG_CT.nrrd": b"not an NRRD file"},
        },
    )
    cases = sources.hanseg_cases(path, "CT")
    assert [each.case.rsplit("/", 1)[-1] for each in cases] == [
        "case_01_IMG_CT.nrrd",
        "case_02_IMG_CT.nrrd",
    ]
    assert isinstance(list(cases[0].read())[0], sources.Skipped)
    read = list(cases[1].read())
    assert len(read) == 3
    assert read[0].pixel_spacing == pytest.approx(1.2)
    assert read[0].stored_range == (-32768, 32767)
    assert read[0].hounsfield
    assert isinstance(cases[1], sources.CaseSource)


# -- Folders of DICOM files, such as a clinic's own -------------------------

PATIENT_A = "PATIENT^A^0001"
PATIENT_B = "PATIENT^B^0002"


def _rt_image(patient, series, instance, number, value=24):
    dataset = _ct_dataset(
        np.full((1, *SHAPE), value),
        Modality="RTIMAGE",
        ImagePlanePixelSpacing=[0.4, 0.4],
        PatientID=patient,
        StudyInstanceUID=f"{series}.0",
        SeriesInstanceUID=series,
        SOPInstanceUID=instance,
        InstanceNumber=number,
    )
    dataset.SOPClassUID = sources.RT_IMAGE_STORAGE
    return synthetic.written(dataset)


def _clinic(tmp_path):
    root = tmp_path / "clinic export"
    (root / "a" / "deeper").mkdir(parents=True)
    (root / "b").mkdir()
    (root / "a" / "2.dcm").write_bytes(_rt_image(PATIENT_A, "2.25.10", "2.25.12", 2))
    (root / "a" / "deeper" / "1.dcm").write_bytes(
        _rt_image(PATIENT_A, "2.25.10", "2.25.11", 1)
    )
    (root / "b" / "1.dcm").write_bytes(_rt_image(PATIENT_B, "2.25.20", "2.25.21", 1))
    ct = _ct_dataset(np.zeros((1, 4, 4)), PatientID=PATIENT_B)
    (root / "b" / "ct.dcm").write_bytes(synthetic.written(ct))
    (root / "notes.txt").write_text("not DICOM")
    annotations = tmp_path / "annotations.csv"
    annotations.write_text(
        "sop_instance_uid,frame,top,left,bottom,right\n"
        "2.25.11,1,9,10,15,38\n"
        "2.25.21,,,,,\n"
        "2.25.99,1,0,0,4,4\n"
    )
    return root, sources.TextAnnotations.from_csv(annotations)


def test_a_folder_is_grouped_by_patient_and_names_no_one(tmp_path):
    root, annotations = _clinic(tmp_path)
    cases = sources.dicom_folder_cases(
        root,
        collection="clinic RT Images",
        sop_classes=(sources.RT_IMAGE_STORAGE,),
        annotations=annotations,
    )
    dicom = [each for each in cases if isinstance(each, sources.DicomCase)]
    patients = [each for each in dicom if each.case.startswith("patient/")]
    assert sorted(len(each.paths) for each in patients) == [1, 2]
    (two,) = [each for each in patients if len(each.paths) == 2]
    # In order of Instance Number, not of path.
    assert [pathlib.Path(each).name for each in two.paths] == ["1.dcm", "2.dcm"]
    for each in cases:
        for secret in (PATIENT_A, PATIENT_B, "2.25.1", str(tmp_path)):
            assert secret not in each.case
    skipped = {
        each.reason: each.count
        for each in cases
        if isinstance(each, sources.SkippedFiles)
    }
    assert skipped == {"sop-class-not-selected": 1, "annotation-not-found": 1}
    by_series = sources.dicom_folder_cases(root, collection="c", group_by="series")
    assert sum(each.case.startswith("series/") for each in by_series) == 3
    # Grouped more finely than by patient, a case gives its patient as its
    # subject, so that the split and the bootstrap keep a patient whole.
    subjects = [
        evaluation.subject_of(each)
        for each in by_series
        if isinstance(each, sources.DicomCase) and each.case.startswith("series/")
    ]
    assert sorted(subjects.count(each) for each in set(subjects)) == [1, 2]
    assert all(each.startswith("patient/") for each in subjects)
    by_file = sources.dicom_folder_cases(root, collection="c", group_by="file")
    assert sum(each.case.startswith("file/") for each in by_file) == 4
    assert len({evaluation.subject_of(each) for each in by_file}) < len(by_file)
    assert all(each.subject is None for each in patients)
    again = sources.dicom_folder_cases(
        root,
        collection="clinic RT Images",
        sop_classes=(sources.RT_IMAGE_STORAGE,),
        annotations=annotations,
    )
    assert again == cases


def test_a_folder_is_measured_by_counts_alone(tmp_path):
    root, annotations = _clinic(tmp_path)
    cases = sources.dicom_folder_cases(
        root,
        collection="clinic RT Images",
        sop_classes=(sources.RT_IMAGE_STORAGE,),
        annotations=annotations,
    )
    summary = _run(cases)
    point = summary["points"][0]
    assert summary["frames"] == {"RT Image Storage": 3}
    assert summary["skipped"] == {
        "annotation-not-found": 1,
        "not-read": 1,
        "sop-class-not-selected": 1,
    }
    known = {
        row["value"]["known_text"]: row["false_positives"]["frames"]
        + row["away_from_text"]["frames"]
        + row["text_unknown"]["frames"]
        for row in point["by"]["known_text"]
    }
    assert known == {"annotated": 2, "unknown": 1}
    # The box drawn around 2.25.11's text is the only text, and is covered.
    assert point["sensitivity"]["texts"] == 1
    assert point["sensitivity"]["fully_covered"] == 1
    assert point["text_unknown"]["frames"] == 1
    assert point["false_positives"]["frames"] == 1  # 2.25.21, annotated empty
    published = json.dumps(summary) + markdown.markdown(summary)
    for secret in (PATIENT_A, PATIENT_B, "2.25.11", "2.25.21", "2.25.99", "notes"):
        assert secret not in published
    assert str(tmp_path) not in published
    assert "clinic export" not in published


def _files(root):
    return {
        str(path.relative_to(root)): (path.stat().st_mtime_ns, path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_text_is_injected_into_a_folders_rt_images_in_memory_alone(
    tmp_path, monkeypatch
):
    """Synthetic text drawn into a local folder's RT Images is counted as
    fully covered, partly covered, or missed, and nothing is written."""
    root, _ = _clinic(tmp_path / "read")
    for path in root.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)
    monkeypatch.setenv("PYMEDPHYS_DATA_DIR", str(tmp_path / "data"))
    before = _files(tmp_path)
    plan = injection.InjectionPlan(
        texts=3, heights=(6.0,), positions=("air", "edge"), contents=("letter",)
    )
    cases = sources.dicom_folder_cases(
        root, collection="clinic RT Images", sop_classes=(sources.RT_IMAGE_STORAGE,)
    )
    try:
        summary = _run(cases, plan=plan)
        page = markdown.markdown(summary)
    finally:
        for path in [root, *root.rglob("*")]:
            path.chmod(0o755 if path.is_dir() else 0o644)
    assert _files(tmp_path) == before
    assert not list(working.iterdir())
    assert not (tmp_path / "data").exists()
    sensitivity = summary["points"][0]["sensitivity"]
    assert summary["frames"] == {"RT Image Storage": 3}
    assert sensitivity["texts"] + sum(summary["not_placed"].values()) == 9
    assert sensitivity["texts"] > 0
    assert (
        sensitivity["fully_covered"]
        + sensitivity["partly_covered"]
        + sensitivity["missed"]
        == sensitivity["texts"]
    )
    bins = [each["count"] for each in sensitivity["ink_covered"]["bins"]]
    assert sum(bins) == sensitivity["texts"]
    assert bins[0] >= sensitivity["missed"]  # the first bin is under 10%
    truths = {row["value"]["truth"] for row in summary["points"][0]["by"]["truth"]}
    assert truths == {"injected"}
    published = json.dumps(summary) + page
    for secret in (PATIENT_A, PATIENT_B, "2.25.11", "2.25.21", "clinic export"):
        assert secret not in published
    assert str(tmp_path) not in published


def test_an_annotated_box_outside_its_frame_skips_the_file():
    data = _rt_image(PATIENT_A, "2.25.10", "2.25.11", 1)
    annotations = sources.TextAnnotations({"2.25.11": ((0, TextBox(60, 60, 70, 70)),)})
    found = sources.dicom_frames(
        data, collection="c", case="a", annotations=annotations
    )
    assert found == sources.Skipped("annotation-outside-frame")
    (frame,) = sources.dicom_frames(
        data, collection="c", case="a", known_text="unknown"
    )
    assert frame.known_text == "unknown" and not frame.texts


@pytest.mark.parametrize(
    "content",
    [
        "uid,frame,top,left,bottom,right\n",
        "sop_instance_uid,frame,top,left,bottom,right\n2.25.5,1,0,0,4\n",
        "sop_instance_uid,frame,top,left,bottom,right\n2.25.5,one,0,0,4,4\n",
        "sop_instance_uid,frame,top,left,bottom,right\n2.25.5,1,4,0,4,4\n",
        "sop_instance_uid,frame,top,left,bottom,right\n2.25.5,0,0,0,4,4\n",
        "sop_instance_uid,frame,top,left,bottom,right\n,1,0,0,4,4\n",
        "",
    ],
)
def test_annotations_not_of_the_form_are_refused_without_a_value(tmp_path, content):
    path = tmp_path / "annotations.csv"
    path.write_text(content)
    with pytest.raises(EvaluationRefused) as refused:
        sources.TextAnnotations.from_csv(path)
    assert "2.25.5" not in str(refused.value)


def test_annotations_are_read_by_instance_and_frame(tmp_path):
    path = tmp_path / "annotations.csv"
    path.write_text(
        "sop_instance_uid, frame, top, left, bottom, right\n"
        "2.25.5,2,1,2,5,10\n"
        "2.25.5,,0,0,3,3\n"
        "\n"
        "2.25.6,,,,,\n"
    )
    annotations = sources.TextAnnotations.from_csv(path)
    assert annotations.instances == {"2.25.5", "2.25.6"}
    assert repr(annotations) == "TextAnnotations()"
    (second,) = annotations.texts("2.25.5", 1, (16, 16))
    assert (second.top, second.left, second.coverage.shape) == (1, 2, (4, 8))
    assert second.height == 4.0
    assert second.strata == {"truth": "annotated"}
    assert len(annotations.texts("2.25.5", 0, (16, 16))) == 1
    assert not annotations.texts("2.25.6", 0, (16, 16))
    assert annotations.subset(["2.25.6", "2.25.7"]).instances == {"2.25.6"}


def test_each_frame_names_its_tier_of_the_corpus(tmp_path):
    root, _ = _clinic(tmp_path)
    cases = sources.dicom_folder_cases(
        root, collection="c", sop_classes=(sources.RT_IMAGE_STORAGE,)
    )
    frames = [
        frame
        for case in cases
        if isinstance(case, sources.DicomCase)
        for frame in case.read()
        if isinstance(frame, EvaluationFrame)
    ]
    assert frames and {frame.tier for frame in frames} == {"T6"}
    phantom = phantoms.phantom_frame(
        phantoms.Phantom("ct-thorax", 64, 4.0), np.random.default_rng(0), case="a"
    )
    assert phantom.tier == "T1"
    # T4 is text burned into T3's frames: injected truth on a T3 frame.
    for tier in ("T4", "T7", ""):
        with pytest.raises(EvaluationRefused):
            _frame(tier=tier)
    with pytest.raises(EvaluationRefused):
        sources.dicom_folder_cases(root, collection="c", tier="T4")
