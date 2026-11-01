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

"""The face block check, on the analytic head stored as HaN-Seg stores its
cases. Every value here is invented."""

from __future__ import annotations

import json
import math
import zipfile

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    defacing,
    face_blocks,
    face_validation,
    face_validation_command,
)
from pymedphys._dicom.deidentify.face_validation import CaseMeasures, CaseNotMeasured
from pymedphys._dicom.deidentify.face_validation_markdown import markdown

from . import _synthetic_head as head
from . import _synthetic_nrrd as files

_GRID = files.grid_of(files.SCAN)
_SECRET = "SYNTHETIC-PATIENT-NAME"
# The cases of the module's ZIP file, in order, by what each holds.
_CASES = (
    "head",
    "right-anterior-superior",
    "coronal",
    "no-eyes",
    "eyes-moved",
    "eyes-swapped",
    "ct-truncated",
    "no-ct",
    "ct-of-layers",
    "ct-not-finite",
)


def _masks(masks, grid=_GRID, **options) -> dict[str, bytes]:
    return {
        f"OAR_{name}.seg.nrrd": files.segment_file(mask, grid, **options)
        for name, mask in masks.items()
    }


def _ct_files(values, grid=_GRID, **options) -> dict[str, bytes]:
    return {
        "IMG_CT.nrrd": files.nrrd_file(values, grid, **options),
        # MR images are not read.
        "IMG_MR_T1.nrrd": b"not an NRRD file",
    }


def _cases(ct: np.ndarray) -> dict[str, dict[str, bytes]]:
    eyes = files.eye_masks(_GRID)
    organs = files.organ_masks(_GRID)
    cases = {}
    cases["head"] = {**_ct_files(ct), **_masks({**eyes, **organs})}
    # The same, in RAS, raw, with the eyes cut to their boxes and the lips
    # on a finer grid.
    ras = {"space": files.RAS}
    cases["right-anterior-superior"] = _ct_files(ct, encoding="raw", **ras)
    for name, mask in {**eyes, **organs}.items():
        if name.startswith("Eye_"):
            mask, grid = files.cropped(mask, _GRID)
        elif name == "Lips":
            mask, grid = files.finer(mask, _GRID)
        else:
            grid = _GRID
        cases["right-anterior-superior"].update(_masks({name: mask}, grid, **ras))
    stored, grid = files.coronal(ct, _GRID)
    cases["coronal"] = {
        **_ct_files(stored, grid, encoding="bzip2"),
        **_masks({**eyes, **organs}),
    }
    no_eyes = files.ct_values(files.SCAN, head.Head(eyes=(False, False), noise=0.0))
    two_segments = files.nrrd_file(
        organs["Lips"].astype(np.uint8),
        _GRID,
        key_values={"Segment0_ID": "a", "Segment1_ID": "b"},
    )
    cases["no-eyes"] = {
        **_ct_files(no_eyes),
        **_masks(eyes),
        "OAR_Lips.seg.nrrd": two_segments,
        "OAR_Brainstem.seg.nrrd": files.segment_file(organs["Brainstem"], _GRID)[:-3],
    }
    cases["eyes-moved"] = {
        **_ct_files(ct),
        **_masks(files.eye_masks(_GRID, shift=(30.0, 0.0, 0.0))),
    }
    swapped = {
        name.translate(str.maketrans("RL", "LR")): mask for name, mask in eyes.items()
    }
    cases["eyes-swapped"] = {**_ct_files(ct), **_masks(swapped)}
    cases["ct-truncated"] = {
        "IMG_CT.nrrd": files.nrrd_file(ct, _GRID)[:-3],
        **_masks(eyes),
    }
    cases["no-ct"] = _masks(eyes)
    cases["ct-of-layers"] = {
        "IMG_CT.nrrd": files.nrrd_file(ct[..., np.newaxis], _GRID, layered=True)
    }
    not_finite = ct.astype(np.float32)
    not_finite[0, 0, 0] = np.nan
    cases["ct-not-finite"] = {"IMG_CT.nrrd": files.nrrd_file(not_finite, _GRID)}
    assert tuple(cases) == _CASES
    return {
        f"case_{index:02d}": cases[name] for index, name in enumerate(_CASES, start=1)
    }


@pytest.fixture(scope="module", name="ct")
def _ct() -> np.ndarray:
    return files.ct_values(files.SCAN, head.Head(noise=0.0))


@pytest.fixture(scope="module", name="block")
def _block(ct) -> defacing.FaceBlock:
    """The block that the finder finds in the head's CT, given its slices
    directly rather than as DICOM instances."""
    scan = files.SCAN
    finder = defacing.FaceFinder(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )
    for frame in ct:
        finder.add(frame.astype(float))
    return finder.block()


@pytest.fixture(scope="module", name="archive")
def _archive(tmp_path_factory, ct):
    path = tmp_path_factory.mktemp("hanseg") / "HaN-Seg.zip"
    files.hanseg_zip(path, _cases(ct))
    return path


@pytest.fixture(scope="module", name="measured")
def _measured(archive) -> dict[str, CaseMeasures | CaseNotMeasured]:
    return dict(zip(_CASES, face_validation.measure_hanseg(archive), strict=True))


@pytest.fixture(scope="module", name="summary")
def _summary(measured, archive):
    data = {**face_validation.HANSEG, "file": face_validation.file_digest(archive)}
    return face_validation.summarise(list(measured.values()), data)


def _sides(masks: dict[str, np.ndarray]) -> list[np.ndarray]:
    """The positions of each eye's voxels, the patient's right first, from
    the masks of its parts."""
    points = _GRID.points()
    return [points[masks[f"Eye_A{side}"] | masks[f"Eye_P{side}"]] for side in "RL"]


def test_a_head_is_defaced_and_measured_against_the_block_found(measured, block):
    case = measured["head"]
    sides = _sides(files.eye_masks(_GRID))
    centroids = [side.mean(axis=0) for side in sides]
    every = np.concatenate(sides)

    assert case.outcome == "defaced"
    assert case.eyes == "agree"
    assert case.sides_swapped is False
    np.testing.assert_allclose(
        case.globe_errors,
        [np.linalg.norm(np.subtract(g, c)) for g, c in zip(block.globes, centroids)],
        rtol=0,
        atol=1e-9,
    )
    reach = max(
        min(np.linalg.norm(point - globe) for globe in block.globes) for point in every
    )
    assert case.eye_reach == pytest.approx(reach, abs=1e-9)
    assert case.eyes_above_limit == pytest.approx(
        every[:, 2].min() - block.inferior_limit, abs=1e-9
    )
    # As the finder's own tests find this head's globes.
    assert max(case.globe_errors) < 2.0
    assert case.eye_reach < face_blocks.EYE_REACH


def test_the_reference_eyes_are_measured_from_their_voxels(measured):
    case = measured["head"]
    sides = _sides(files.eye_masks(_GRID))
    voxel = abs(float(np.linalg.det(_GRID.axes)))
    right, left = (side.mean(axis=0) for side in sides)

    np.testing.assert_allclose(
        case.diameters,
        [(6 * len(side) * voxel / math.pi) ** (1 / 3) for side in sides],
        rtol=0,
        atol=1e-9,
    )
    assert case.separation == pytest.approx(
        np.linalg.norm((left - right)[:2]), abs=1e-9
    )
    assert case.turn == pytest.approx(0.0, abs=1e-9)
    # A sphere of the voxels' volume is about the globe's diameter.
    np.testing.assert_allclose(case.diameters, 2 * head.GLOBE_RADIUS, atol=1.0)
    assert case.separation == pytest.approx(2 * head.GLOBE_X, abs=1e-9)


def test_the_air_written_takes_the_front_of_the_eyes_and_keeps_the_rest(
    measured, block
):
    written = measured["head"].written
    eyes = files.eye_masks(_GRID)
    points = _GRID.points()

    assert written["Eye_AR"] == written["Eye_AL"] == 1.0
    assert written["Glnd_Lacrimal_R"] == 1.0
    assert written["Lips"] == written["Brainstem"] == 0.0
    # Each eye's posterior part, cut by the block's plane: the share of its
    # voxels whose centres are in the block.
    for name in ("Eye_PR", "Eye_PL"):
        expected = float(np.mean(block.contains(points[eyes[name]])))
        assert 0.0 < expected < 1.0
        assert written[name] == pytest.approx(expected, abs=1e-12)


def test_a_volume_in_another_space_and_masks_on_other_grids_measure_the_same(measured):
    head_case, ras = measured["head"], measured["right-anterior-superior"]

    assert ras.outcome == "defaced"
    np.testing.assert_allclose(ras.globe_errors, head_case.globe_errors, atol=1e-9)
    assert ras.eye_reach == pytest.approx(head_case.eye_reach, abs=1e-9)
    np.testing.assert_allclose(ras.diameters, head_case.diameters, atol=1e-9)
    assert ras.written == pytest.approx(head_case.written, abs=1e-12)
    assert ras.ct_format == "int16 raw right-anterior-superior"
    assert ras.mask_formats == {"uint8 gzip right-anterior-superior": 7}


def test_a_volume_of_coronal_slices_is_defaced_from_the_same_globes(measured):
    case = measured["coronal"]

    assert case.outcome == "defaced"
    assert case.eyes == "agree"
    assert max(case.globe_errors) < 2.5
    assert case.written["Eye_AR"] == case.written["Eye_AL"] == 1.0
    assert case.written["Lips"] == case.written["Brainstem"] == 0.0
    assert case.pixel_spacing == 3.0
    assert case.slice_spacing == 2.0


def test_a_head_without_eyes_is_not_defaced_and_its_masks_still_describe_it(measured):
    case = measured["no-eyes"]

    assert case.outcome == "no-eyes"
    assert case.eyes is None
    assert case.written == {}
    assert case.globe_errors == ()
    assert len(case.diameters) == 2
    assert case.mask_problems == {"data-length": 1, "several-segments": 1}


def test_eyes_away_from_the_globes_found_would_hold_the_series(measured):
    case = measured["eyes-moved"]

    assert case.outcome == "defaced"
    assert case.eyes == "eyes-disagree-with-rois"
    np.testing.assert_allclose(case.globe_errors, 30.0, atol=2.5)
    assert case.eye_reach > face_blocks.EYE_REACH


def test_eyes_named_for_the_other_side_are_counted_as_swapped(measured):
    case = measured["eyes-swapped"]

    assert case.sides_swapped is True
    # The engine checks each eye against the nearer globe, whatever its side.
    assert case.eyes == "agree"
    np.testing.assert_allclose(case.globe_errors, 2 * head.GLOBE_X, atol=2.5)


@pytest.mark.parametrize(
    "name, reason",
    [
        ("ct-truncated", "ct-not-read/data-length"),
        ("no-ct", "ct-missing"),
        ("ct-of-layers", "ct-not-three-dimensional"),
        ("ct-not-finite", "ct-values-not-finite"),
    ],
)
def test_a_case_whose_ct_cannot_be_measured_is_counted_by_why(measured, name, reason):
    assert measured[name] == CaseNotMeasured(reason)


def test_what_the_finder_saw_at_each_eye_is_measured(measured):
    case = measured["head"]
    finder = case.finder

    assert finder is not None
    assert finder.outcome == "defaced"
    assert finder.kept <= finder.considered
    # The balls at the eyes are the globes of the block found.
    for eye, error in zip(finder.eyes, case.globe_errors, strict=True):
        assert eye.status == "kept"
        assert eye.nearest_kept == pytest.approx(error, abs=1e-9)
        assert eye.nearest is not None and eye.nearest <= eye.nearest_kept
        assert eye.outside is not None and eye.outside >= 0.5
        assert eye.best_half is not None and eye.best_half >= 0.7
        assert eye.depth_window == "within"
        assert head.GLOBE_RADIUS - 2 * finder.voxel <= eye.depth
    pair = finder.pair
    assert pair is not None
    assert pair.side_by_side
    assert pair.lateral == pair.superior == (True, True)
    assert pair.passes
    assert pair.behind - pair.in_front >= defacing.HEAD_BEHIND
    assert pair.cranium_above
    assert finder.other_pairs == ()
    # Each globe lies just under the skin in front.
    (front,) = finder.fronts
    assert front.place == "eyes" and front.side == "in-front"
    assert all(0 < depth <= defacing.FRONT_REACH for depth in front.depth)
    assert all(fat <= defacing.FRONT_FAT for fat in front.fat)
    assert front.bone == (False, False)
    assert sorted(kind for kind, _ in finder.shells).count("eye") == 2
    for _, shares in finder.shells:
        assert set(shares) == set(face_validation.TISSUES)
        assert sum(shares.values()) == pytest.approx(1.0, abs=1e-12)


def test_what_the_finder_saw_without_eyes_shows_no_ball_there(measured):
    finder = measured["no-eyes"].finder

    assert finder is not None
    assert finder.outcome == "no-eyes"
    for eye in finder.eyes:
        assert eye.status == "none-within-5-mm"
        assert eye.outside is None and eye.best_half is None
        # Orbital fat, not soft tissue, fills each orbit.
        assert eye.depth == 0.0
        assert eye.depth_window == "below"
    assert finder.pair is None
    assert all(kind == "other" for kind, _ in finder.shells)


def test_globes_away_from_the_eyes_are_counted_as_another_pair(measured):
    finder = measured["eyes-moved"].finder

    assert finder is not None
    assert finder.outcome == "defaced"
    assert finder.pair is None
    # The eyes' masks moved 30 mm to the patient's left: each globe lies
    # level with their centroids and beside them, 30 mm or more from each.
    assert finder.other_pairs == ("level-beside + level-beside",)
    (front,) = finder.fronts
    assert front.place == "level-beside + level-beside"
    assert front.side == "in-front"


def test_eyes_named_for_the_other_side_are_tested_as_the_same_pair(measured):
    swapped, head_case = measured["eyes-swapped"].finder, measured["head"].finder

    assert swapped is not None and head_case is not None
    assert swapped.pair is not None and head_case.pair is not None
    assert swapped.pair.behind == head_case.pair.behind
    assert swapped.pair.in_front == head_case.pair.in_front
    assert swapped.pair.lateral == swapped.pair.superior == (True, True)


def test_another_head_in_view_is_counted_as_another_pair_beside_the_eyes():
    scan = head.axial(spacing=1.5, extent=((-230, 230), (-130, 110), (-120, 120)))
    finder = defacing.FaceFinder(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )
    for values in scan.slices(head.Head(shift=-120.0), head.Head(shift=120.0)):
        finder.add(values)
    eyes = [
        np.array([[x - 120.0, head.GLOBE_Y, head.GLOBE_Z]])
        for x in (-head.GLOBE_X, head.GLOBE_X)
    ]

    # pylint: disable-next = protected-access
    measures = face_validation._finder_measures(finder.inspect(), eyes)

    assert measures.outcome == "ambiguous-eyes"
    assert measures.pair is not None
    assert measures.pair.side_by_side
    assert measures.other_pairs == ("level-beside + level-beside",)


@pytest.mark.parametrize(
    "offset, place",
    [
        ((0.0, 0.0, 14.0), "at-an-eye"),
        ((30.0, 0.0, 0.0), "level-beside"),
        ((30.0, 0.0, 10.5), "above-beside"),
        ((30.0, 15.5, -10.5), "below-behind"),
        ((30.0, -15.5, 0.0), "level-in-front"),
    ],
)
def test_a_ball_is_placed_from_the_eyes_centroids(offset, place):
    centroids = np.array([[-32.0, -66.0, 20.0], [32.0, -66.0, 20.0]])

    # pylint: disable-next = protected-access
    found = face_validation._place(centroids[0] + np.array(offset), centroids)

    assert found == place


def test_a_ct_not_in_hounsfield_units_is_counted_as_without_air(tmp_path):
    # Stored as CT scanners store values before the rescale, air near 0.
    ct = np.full((3, 8, 8), 24, dtype=np.uint16)
    grid = files.Grid(
        (0.0, 0.0, 0.0), ((1.5, 0, 0), (0, 1.5, 0), (0, 0, 3.0)), ct.shape
    )
    path = tmp_path / "HaN-Seg.zip"
    files.hanseg_zip(path, {"case_01": {"IMG_CT.nrrd": files.nrrd_file(ct, grid)}})

    (case,) = face_validation.measure_hanseg(path)

    assert isinstance(case, CaseMeasures)
    assert case.air is False
    assert case.outcome == "no-eyes"


def test_the_summary_counts_the_cases_by_outcome(summary):
    assert summary["format"] == "pymedphys-deid-face-validation/3"
    assert summary["cases"] == {
        "total": 10,
        "measured": 6,
        "not_measured": {
            "ct-missing": 1,
            "ct-not-read/data-length": 1,
            "ct-not-three-dimensional": 1,
            "ct-values-not-finite": 1,
        },
        "crashed": {},
    }
    assert summary["series"] == {"defaced": 5, "not_defaced": {"no-eyes": 1}}
    finder = summary["finder"]
    assert finder["cases"] == {"defaced": 5, "no-eyes": 1}
    assert finder["not_inspected"] == {}
    assert finder["finder_outcome"] == {
        "defaced": {"defaced": 5},
        "no-eyes": {"no-eyes": 1},
    }
    assert finder["eyes"]["kept_ball_at_each_eye"] == {
        "defaced": {"both": 4, "neither": 1},
        "no-eyes": {"neither": 1},
    }
    assert finder["eye_pair"]["passes"] == {"defaced": {"yes": 4}, "no-eyes": {}}
    assert finder["other_pair_places"] == {
        "defaced": {"level-beside + level-beside": 1},
        "no-eyes": {},
    }
    front = finder["front"]
    assert front["eyes"]["side"] == {"defaced": {"in-front": 4}, "no-eyes": {}}
    assert front["other"]["places"] == finder["other_pair_places"]
    assert front["other"]["side"] == {"defaced": {"in-front": 1}, "no-eyes": {}}
    assert front["eyes"]["bone"] == {"defaced": {"no": 8}, "no-eyes": {}}
    depths = front["eyes"]["depth"]["defaced"]["bins"]
    assert sum(each["count"] for each in depths) == 8
    assert summary["eyes_of_defaced_series"] == {
        "agree": 4,
        "eyes-disagree-with-rois": 1,
    }
    assert summary["sides_swapped"] == 1
    assert summary["ct"]["air_in_hounsfield_units"] == {"yes": 6, "no": 0}
    assert summary["masks"]["not_read"] == {"data-length": 1, "several-segments": 1}
    assert summary["reference_eyes"]["cases"] == 6
    assert sum(each["count"] for each in summary["globe_centre_error"]["bins"]) == 10
    lips = summary["written_as_air"]["Lips"]
    assert lips == dict.fromkeys(face_validation.SHARES, 0) | {"none": 3}


def test_the_summary_holds_only_counts_codes_digests_versions_and_settings(summary):
    constants = {
        edge
        for bins in vars(face_validation).values()
        if isinstance(bins, face_validation.Bins)
        for edge in bins.edges
    }
    for value in summary["settings"].values():
        constants.update(value if isinstance(value, list) else [value])

    def numbers(value):
        if isinstance(value, dict):
            for each in value.values():
                yield from numbers(each)
        elif isinstance(value, list):
            for each in value:
                yield from numbers(each)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            yield value

    found = list(numbers(summary))
    assert found
    assert all(isinstance(each, int) or each in constants for each in found)
    assert json.loads(json.dumps(summary)) == summary


def test_the_summary_is_the_same_each_time(measured, summary, archive):
    data = {**face_validation.HANSEG, "file": face_validation.file_digest(archive)}

    assert face_validation.summarise(list(measured.values()), data) == summary


@pytest.mark.parametrize(
    "bins, values, counts",
    [
        (face_validation.Bins("mm", (0.0, 1.0)), [0.0, 0.5, 1.0, 7.0], [2, 2]),
        (
            face_validation.Bins("mm", (0.0, 1.0), below=True),
            [-3.0, 0.0, 1.0],
            [1, 1, 1],
        ),
    ],
)
def test_each_value_is_counted_in_the_bin_from_its_lower_edge(bins, values, counts):
    result = bins.counts(values)

    assert [each["count"] for each in result["bins"]] == counts
    lows = [each["from"] for each in result["bins"]]
    highs = [each["to"] for each in result["bins"]]
    assert lows == ([None] if bins.below else []) + list(bins.edges)
    assert highs == lows[1:] + [None]
    positions = [bins.index(value) for value in values]
    assert [positions.count(each) for each in range(len(counts))] == counts


@pytest.mark.parametrize("value", [-0.5, math.nan])
def test_a_value_that_no_bin_holds_is_refused_without_quoting_it(value):
    with pytest.raises(ValueError, match="^A value is in no bin.$"):
        face_validation.Bins("mm", (0.0, 1.0)).counts([0.25, value])
    with pytest.raises(ValueError, match="^A value is in no bin.$"):
        face_validation.Bins("mm", (0.0, 1.0)).index(value)


def test_measures_show_nothing_of_a_case(measured):
    assert repr(CaseMeasures("defaced", "int16 gzip lps", True, 1.0, 2.0)) == (
        "CaseMeasures()"
    )
    finder = measured["head"].finder
    assert finder is not None and finder.pair is not None
    assert repr(finder) == "FinderMeasures()"
    assert repr(finder.eyes[0]) == "EyeMeasures()"
    assert repr(finder.pair) == "PairMeasures()"
    assert repr(finder.fronts[0]) == "FrontMeasures()"


def test_a_case_that_raises_is_counted_by_where_without_its_message(
    tmp_path, monkeypatch
):
    def raising(*_):
        raise ValueError(f"/data/{_SECRET}/case_01")

    ct = np.zeros((2, 2, 2), dtype=np.int16)
    grid = files.Grid((0.0, 0.0, 0.0), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), ct.shape)
    path = tmp_path / "HaN-Seg.zip"
    files.hanseg_zip(path, {"case_01": {"IMG_CT.nrrd": files.nrrd_file(ct, grid)}})
    monkeypatch.setattr(face_validation, "measure_case", raising)

    (case,) = face_validation.measure_hanseg(path)
    data = {**face_validation.HANSEG, "file": face_validation.file_digest(path)}
    summary = face_validation.summarise([case], data)
    page = markdown(summary)

    assert isinstance(case, CaseNotMeasured)
    assert case.reason == "crashed"
    assert case.where is not None
    assert case.where.startswith("ValueError at test_deidentify_face_validation.py:")
    assert case.where.endswith(" in raising")
    assert summary["cases"]["crashed"] == {case.where: 1}
    assert f"| Crashed: `{case.where}` | 1 |\n" in page
    assert _SECRET not in json.dumps(summary)
    assert _SECRET not in page


def test_the_cases_are_found_by_their_directories(tmp_path):
    path = tmp_path / "HaN-Seg.zip"
    files.hanseg_zip(
        path,
        {
            "case_02": {
                "OAR_Lips.seg.nrrd": b"",
                "IMG_CT.nrrd": b"",
                "IMG_MR_T1.nrrd": b"",
            },
            "case_01": {"OAR_Eye_AL.seg.nrrd": b"", "OAR_Brainstem.seg.nrrd": b""},
        },
    )
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("HaN-Seg/set_1/OAR_data.csv", "")
    with zipfile.ZipFile(path) as archive:
        cases = face_validation.hanseg_cases(archive)

    assert [case.ct is None for case in cases] == [True, False]
    assert [list(case.organs) for case in cases] == [["Brainstem", "Eye_AL"], ["Lips"]]
    ct = cases[1].ct
    assert ct is not None
    assert ct.filename == "HaN-Seg/set_1/case_02/case_02_IMG_CT.nrrd"


def test_the_page_shows_the_counts_as_commonmark(summary):
    page = markdown(summary)

    assert page.startswith("# Face block check on HaN-Seg\n\n")
    assert page.endswith("|\n")
    assert "| Defaced | 5 |\n" in page
    assert "| Not defaced: `no-eyes` | 1 |\n" in page
    assert "| `Lips` | 3 | 0 | 0 | 0 | 0 | 0 |\n" in page
    assert "| Eyes with a kept ball within 5 mm | `defaced` | `no-eyes` |\n" in page
    assert "| `both` | 4 | 0 |\n" in page
    lines = page.split("\n")
    # markdownlint's MD009, MD012, and MD022: no trailing spaces, no blank
    # lines in a row, and a blank line around each heading.
    assert not any(line != line.rstrip() for line in lines)
    assert "\n\n\n" not in page
    for index, line in enumerate(lines):
        if line.startswith("#"):
            assert index == 0 or lines[index - 1] == ""
            assert lines[index + 1] == ""


def test_the_command_writes_the_counts_and_prints_the_page(
    archive, measured, tmp_path, capsys, monkeypatch
):
    # The cases as the other tests measured them, rather than again.
    def measure(path):
        assert path == archive
        return list(measured.values())

    monkeypatch.setattr(face_validation, "measure_hanseg", measure)
    out = tmp_path / "results"

    status = face_validation_command.main(["hanseg", str(archive), "--out", str(out)])

    assert status == 0
    summary = json.loads((out / "face-validation.json").read_text(encoding="utf-8"))
    page = (out / "face-validation.md").read_text(encoding="utf-8")
    assert summary["series"]["defaced"] == 5
    assert page == markdown(summary)
    assert capsys.readouterr().out == page


def test_the_command_refuses_an_output_directory_that_exists(archive, tmp_path):
    with pytest.raises(SystemExit) as refused:
        face_validation_command.main(["hanseg", str(archive), "--out", str(tmp_path)])

    assert refused.value.code == "The output directory must not exist."


@pytest.mark.parametrize("contents", [b"not a ZIP file", None])
def test_the_command_refuses_a_file_that_is_not_a_zip_file_or_holds_no_case(
    tmp_path, contents
):
    path = tmp_path / f"{_SECRET}.zip"
    if contents is None:
        files.hanseg_zip(path, {})
        message = "The ZIP file holds no HaN-Seg case."
    else:
        path.write_bytes(contents)
        message = "The data set is not a readable ZIP file."

    with pytest.raises(SystemExit) as refused:
        face_validation_command.main(
            ["hanseg", str(path), "--out", str(tmp_path / "out")]
        )

    assert refused.value.code == message
    assert not (tmp_path / "out").exists()


def test_the_settings_are_the_engines(summary):
    settings = summary["settings"]

    assert settings["head_reach_mm"] == face_blocks.HEAD_REACH
    assert settings["margin_mm"] == defacing.MARGIN
    assert settings["eye_reach_mm"] == face_blocks.EYE_REACH
    assert settings["cavity_floor_mm"] == face_blocks.CAVITY_FLOOR
    assert settings["globe_diameter_mm"] == list(defacing.GLOBE_DIAMETER)
    assert settings["front_reach_mm"] == defacing.FRONT_REACH
    assert settings["front_fat_mm"] == defacing.FRONT_FAT
