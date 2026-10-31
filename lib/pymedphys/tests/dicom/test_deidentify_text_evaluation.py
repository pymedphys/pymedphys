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
from pymedphys._dicom.deidentify.text_detection import (
    RENDERINGS,
    DetectionParameters,
    RenderedProbability,
)
from pymedphys._dicom.deidentify.text_evaluation_detector import PostProcessing
from pymedphys._dicom.deidentify.text_evaluation_frames import (
    BurnedText,
    EvaluationFrame,
    EvaluationRefused,
)

from . import _synthetic_nrrd as files
from . import _synthetic_references as synthetic

SECRET = "SECRET^CASE^4711"
SHAPE = (64, 64)
# A detector's probability is 0.9 inside these regions of every frame, and
# a region of 8 or more network pixels at the default settings gives a box
# grown by the unclip offset and the margin.
REGION_TEXT = (8, 8, 16, 40)
REGION_ANATOMY = (40, 20, 50, 30)


class BoxDetector:
    """A stand-in detector: its full-range map is 0.9 inside its regions,
    on the frame's own grid, and its other maps are empty."""

    def __init__(self, regions=(REGION_TEXT, REGION_ANATOMY)):
        self.regions = tuple(regions)

    @property
    def method(self):
        return {"network": "boxes", "variant": {"name": "boxes"}}

    def probabilities(self, frame):
        maps = []
        for name in RENDERINGS:
            probability = np.zeros(frame.shape, np.float32)
            if name == "full-range":
                for top, left, bottom, right in self.regions:
                    probability[top:bottom, left:right] = 0.9
            maps.append(RenderedProbability(name, frame.shape, probability))
        return tuple(maps)


def box_detector():
    """Makes a :class:`BoxDetector`, picklable for worker processes."""
    return BoxDetector()


def _frame(stored=None, *, case=SECRET, collection="collection", texts=(), **options):
    stored = np.full(SHAPE, 1024, np.uint16) if stored is None else stored
    return EvaluationFrame(
        stored=stored,
        collection=collection,
        case=case,
        iod=options.pop("iod", "CT Image Storage"),
        modality=options.pop("modality", "CT"),
        intercept=-1024.0,
        pixel_spacing=options.pop("pixel_spacing", 1.0),
        texts=tuple(texts),
        **options,
    )


def _text(top, left, rows, columns, **strata):
    return BurnedText(top, left, np.ones((rows, columns)), float(rows), strata)


@dataclasses.dataclass(frozen=True)
class Frames:
    """A case whose frames are given."""

    collection: str
    case: str
    frames: tuple

    def read(self):
        yield from self.frames


@dataclasses.dataclass(frozen=True)
class Raising:
    """A case whose reading raises, with a message that quotes a value."""

    collection: str = "collection"
    case: str = SECRET

    def read(self):
        yield _frame()
        raise ValueError(SECRET)


def _settings(**options):
    return evaluation.EvaluationSettings(
        points=options.pop("points", (PostProcessing(),)),
        evaluated=options.pop("evaluated", "all"),
        **options,
    )


def _run(cases, **options):
    workers = options.pop("workers", 1)
    run = evaluation.evaluate(
        cases, box_detector, _settings(**options), workers=workers
    )
    return evaluation.summarise(run, replicates=200)


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
        "iod+contrast+height",
    } <= set(by)


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
    cells = by["iod+contrast+height"]
    assert {(row["value"]["height"], row["sensitivity"]["texts"]) for row in cells} == {
        ("6 px", 1),
        ("4 px", 1),
    }
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
        r"ValueError at test_deidentify_text_evaluation\.py:\d+ in read", site
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


def test_many_points_are_detailed_only_at_the_first():
    points = tuple(
        PostProcessing(box_threshold=0.5 + index / 100) for index in range(11)
    )
    summary = _run(
        [Frames("c", "a", (_frame(texts=(_text(9, 10, 6, 28),)),))], points=points
    )
    assert "font" in summary["points"][0]["by"]
    assert set(summary["points"][1]["by"]) == {"iod", "iod+contrast+height"}


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
            criteria_module.SensitivityCriterion(0.9, contrast="8 to under 16 sigma"),
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
    criterion = (criteria_module.SensitivityCriterion(0.95),)
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
        sensitivity=(criteria_module.SensitivityCriterion(0.5),),
        min_texts=41,
        bound="estimate",
    )
    (first, _) = criteria_module.assess(summary, criteria)
    assert first["failures"] == [
        "sensitivity: CT Image Storage, 8 to under 16 sigma, 6 px: too few texts"
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
    assert "| Font | Texts | Fully covered | Wilson |\n" in page


# -- Readers ------------------------------------------------------------------


def _ct_dataset(frames, **attributes):
    words = np.asarray(frames)
    dataset = synthetic.ct_slice(0)
    dataset.Modality = "CT"
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows, dataset.Columns = words.shape[1:]
    dataset.BitsAllocated, dataset.BitsStored, dataset.HighBit = 16, 12, 11
    dataset.PixelRepresentation = 0
    if words.shape[0] > 1:
        dataset.NumberOfFrames = words.shape[0]
    for keyword, value in attributes.items():
        setattr(dataset, keyword, value)
    dataset.PixelData = words.astype("<u2").tobytes()
    return dataset


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
