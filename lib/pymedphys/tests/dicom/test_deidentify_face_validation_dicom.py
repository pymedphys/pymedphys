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

"""The face block check on DICOM files, on the analytic head written as a
planning system's exports. Every UID and value here is invented."""

from __future__ import annotations

import io
import json
import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    defacing,
    dose_defacing,
    face_blocks,
    face_validation,
    face_validation_command,
    face_validation_dicom,
)
from pymedphys._dicom.deidentify.defacing import FaceBlock
from pymedphys._dicom.deidentify.face_validation_dicom import (
    DicomMeasures,
    EyeMeasures,
    SeriesMeasures,
    centroid,
    clearance,
    side_of,
)
from pymedphys._dicom.deidentify.face_validation_dicom_markdown import markdown

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files

# Coarser than the finder's own tests, as the face block tests' scan is.
_SCAN = head.axial(
    spacing=2.0, thickness=3.0, extent=((-100, 100), (-130, 110), (-60, 120))
)
_SECRET = "SYNTHETIC-PATIENT-NAME"
_SECRET_ROI = "SyntheticOrganName"
_RIGHT = (-head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z)
_LEFT = (head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z)
# The heights of the CT's slices that cut each globe, at which a planner
# draws its contours.
_GLOBE_HEIGHTS = tuple(
    float(z)
    for z in sorted({position[2] for position in _SCAN.positions})
    if abs(z - head.GLOBE_Z) < head.GLOBE_RADIUS
)
_DOSE_GREATEST = 1000
_DOSE_LOW, _DOSE_HIGH = 30, 300
RT_PLAN_STORAGE = "1.2.840.10008.5.1.4.1.1.481.5"


def _frame(case: int) -> str:
    return f"{files.ROOT}.{case}0"


def _series(case: int) -> str:
    return f"{files.ROOT}.{case}1"


def _patient(case: int) -> pydicom.Dataset:
    """Each case is its own patient, so that a structure set is searched
    only for its own case's series."""
    dataset = pydicom.Dataset()
    dataset.PatientName = f"{_SECRET}^{case}"
    dataset.PatientID = f"P{case}"
    dataset.StudyInstanceUID = f"{files.ROOT}.{case}2"
    dataset.SeriesInstanceUID = f"{files.ROOT}.{case}3"
    dataset.StudyDate = "20260101"
    return dataset


def _globe(centre, shift=(0.0, 0.0, 0.0)) -> list[np.ndarray]:
    """A planner's contours of a globe, one on each slice that cuts it."""
    x, y, z0 = np.add(centre, shift)
    return [
        files.circle((x, y, z), math.sqrt(head.GLOBE_RADIUS**2 - (z - z0) ** 2), 72)
        for z in _GLOBE_HEIGHTS
    ]


def _structure_set(case: int, rois, names) -> bytes:
    data = files.structure_set(
        rois, frame=_frame(case), template=_patient(case), names=names
    )
    dataset = pydicom.dcmread(io.BytesIO(data))
    dataset.SOPInstanceUID = f"{files.ROOT}.{case}4"
    dataset.file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
    return files.written(dataset)


def _ct(case: int, **parts) -> list[bytes]:
    return files.ct_files(
        _SCAN,
        head.Head(noise=0.0, **parts),
        series=_series(case),
        frame=_frame(case),
        template=_patient(case),
    )


def _dose(case: int, block: FaceBlock, in_block: int, index: int) -> bytes:
    """An RT Dose of the grid's greatest behind the block, and of
    ``in_block`` at every voxel whose centre is in it."""
    spacing = 5.0
    corner = np.array([-100.0, -130.0, -60.0])
    shape = (37, 49, 41)  # frames along z, rows along y, columns along x
    z, y, x = np.meshgrid(*(np.arange(n) * spacing for n in shape), indexing="ij")
    points = corner + np.stack([x, y, z], axis=-1)
    stored = np.asarray(np.where(block.contains(points), in_block, _DOSE_GREATEST))
    return files.dose(
        stored.astype(np.uint32),
        position=tuple(corner),
        spacing=(spacing, spacing),
        offsets=tuple(np.arange(shape[0]) * spacing),
        frame=_frame(case),
        instance=f"{files.ROOT}.{case}5.{index}",
        template=_patient(case),
    )


def _plan(case: int) -> bytes:
    dataset = files._dataset(  # pylint: disable = protected-access
        RT_PLAN_STORAGE, f"{files.ROOT}.{case}6", _patient(case)
    )
    dataset.Modality = "RTPLAN"
    dataset.FrameOfReferenceUID = _frame(case)
    dataset.RTPlanLabel = "P"
    return files.written(dataset)


@pytest.fixture(scope="module", name="block")
def _block() -> FaceBlock:
    """The block that the finder finds in the head's CT, given its slices
    directly rather than as DICOM files."""
    finder = defacing.FaceFinder(
        _SCAN.orientation, _SCAN.positions, _SCAN.spacing, _SCAN.shape
    )
    for values in _SCAN.slices(head.Head(noise=0.0)):
        finder.add(values.astype(float))
    return finder.block()


# A target behind the block, and one in front of the face inside it.
_BEHIND = files.circle((0.0, 0.0, 40.0), 20.0)
_IN_BLOCK = files.circle((0.0, -85.0, 30.0), 5.0)
_BODY = files.ellipse((0.0, -10.0, 30.0), (95.0, 115.0))


@pytest.fixture(scope="module", name="exports")
def _exports(tmp_path_factory, block):
    """A directory of four cases' exports, in directories of their own:

    1. a head, defaced, with eyes drawn at its globes, a target behind the
       block, a body outline, two RT Doses, of low and high dose in the
       block, and an RT Plan;
    2. a head without eyes, with an eye drawn, an RT Dose, and an RT Plan;
    3. a head with eyes drawn at its globes and a target in its block; and
    4. a head with its right eye drawn at its left globe and its left eye
       drawn 40 mm to the patient's left;

    with a text file and a DICOMDIR, which are not read.
    """
    root = tmp_path_factory.mktemp(_SECRET)
    contents: dict[str, bytes] = {}
    contents |= {f"1/CT{i:03d}.dcm": each for i, each in enumerate(_ct(1))}
    contents["1/RS.dcm"] = _structure_set(
        1,
        [
            ("ORGAN", _globe(_RIGHT)),
            ("ORGAN", _globe(_LEFT)),
            ("ORGAN", _globe(_RIGHT) + _globe(_LEFT)),
            ("PTV", _BEHIND),
            ("EXTERNAL", _BODY),
            ("ORGAN", files.circle((0.0, 20.0, 0.0), 10.0)),
        ],
        ["Eye_R", "LEye", "Eyes", "PTV_High", "BODY", _SECRET_ROI],
    )
    contents["1/RD1.dcm"] = _dose(1, block, _DOSE_LOW, 1)
    contents["1/RD2.dcm"] = _dose(1, block, _DOSE_HIGH, 2)
    contents["1/RP.dcm"] = _plan(1)
    contents |= {
        f"2/CT{i:03d}.dcm": each for i, each in enumerate(_ct(2, eyes=(False, False)))
    }
    contents["2/RS.dcm"] = _structure_set(2, [("ORGAN", _globe(_RIGHT))], ["Globe_Rt"])
    contents["2/RD.dcm"] = _dose(2, block, _DOSE_HIGH, 1)
    contents["2/RP.dcm"] = _plan(2)
    contents |= {f"3/CT{i:03d}.dcm": each for i, each in enumerate(_ct(3))}
    contents["3/RS.dcm"] = _structure_set(
        3,
        [
            ("ORGAN", _globe(_RIGHT)),
            ("ORGAN", _globe(_LEFT)),
            ("GTV", _IN_BLOCK),
        ],
        ["Eye_R", "Eye_L", "GTV"],
    )
    contents |= {f"4/CT{i:03d}.dcm": each for i, each in enumerate(_ct(4))}
    contents["4/RS.dcm"] = _structure_set(
        4,
        [
            ("ORGAN", _globe(_LEFT)),
            ("ORGAN", _globe(_LEFT, shift=(40.0, 0.0, 0.0))),
        ],
        ["Eye_R", "Globe_Lt"],
    )
    contents["notes.txt"] = b"not DICOM"
    contents["DICOMDIR"] = b"refused by name"
    for name, data in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


@pytest.fixture(scope="module", name="measured")
def _measured(exports) -> DicomMeasures:
    return face_validation_dicom.measure_dicom(exports)


@pytest.fixture(scope="module", name="summary")
def _summary(measured):
    return face_validation_dicom.summarise(measured)


def _by_outcome(measured: DicomMeasures) -> dict[str, SeriesMeasures]:
    return {each.outcome: each for each in measured.series}


def test_each_series_has_its_outcome_as_a_run_finds_it(measured):
    assert sorted(_by_outcome(measured)) == [
        "defaced",
        "eyes-disagree-with-rois",
        "no-eyes",
        "target-in-block",
    ]
    assert measured.crashed == {}


def test_the_files_are_counted_by_how_they_were_read(measured):
    slices = len(_SCAN.positions)

    assert measured.files == {
        "total": 4 * slices + 11,
        "read": 4 * slices + 9,
        "not-read": 1,
    }
    assert measured.refused == {"dicomdir": 1}
    assert measured.iods == {
        "CT Image": 4 * slices,
        "RT Dose": 3,
        "RT Plan": 2,
        "RT Structure Set": 4,
    }
    assert measured.ct_without_series == 0


def test_each_series_storage_spacings_and_air_are_measured(measured):
    for each in measured.series:
        assert each.storage == "native 16/16 signed"
        assert each.pixel_spacing == pytest.approx(2.0)
        assert each.slice_spacing == pytest.approx(3.0)
        assert each.air is True


def _expected_eye(block: FaceBlock, contours, side: int | None) -> dict:
    """An eye ROI's measures from its circles: their centroid weighted by
    each circle's area, pi r squared, rather than its polygon's."""
    points = np.concatenate(contours)
    globes = np.asarray(block.globes)
    radii = [np.ptp(each[:, 0]) / 2 for each in contours]
    centres = [each.mean(axis=0) for each in contours]
    centre = np.average(centres, axis=0, weights=np.square(radii))
    nearest = np.min(np.linalg.norm(points[:, None, :] - globes, axis=2), axis=1)
    return {
        "error": None if side is None else np.linalg.norm(globes[side] - centre),
        "reach": np.max(nearest),
        "above_limit": np.min(points[:, 2]) - block.inferior_limit,
    }


def test_eye_rois_are_measured_against_the_globes_found(measured, block):
    defaced = _by_outcome(measured)["defaced"]
    right, left, both = defaced.eyes

    assert defaced.eye_rois == 3
    assert (right.side, left.side, both.side) == ("right", "left", "not-named")
    for eye, contours, side in ((right, _globe(_RIGHT), 0), (left, _globe(_LEFT), 1)):
        expected = _expected_eye(block, contours, side)
        # Contour Data holds each coordinate to six significant figures.
        assert eye.globe_errors == (pytest.approx(expected["error"], abs=1e-3),)
        assert eye.reach == pytest.approx(expected["reach"], abs=1e-3)
        assert eye.above_limit == pytest.approx(expected["above_limit"], abs=1e-3)
        assert eye.swapped is False
        # The finder places each globe within a few millimetres of the
        # head's, whose contours are drawn at it.
        assert eye.globe_errors[0] < 3.0
        assert eye.reach <= face_blocks.EYE_REACH
    # A name that gives no side is measured from each globe to its own
    # contours.
    assert both.globe_errors == (
        pytest.approx(right.globe_errors[0]),
        pytest.approx(left.globe_errors[0]),
    )
    assert both.swapped is None


def test_an_eye_named_for_the_other_side_and_one_far_off_are_measured(measured, block):
    held = _by_outcome(measured)["eyes-disagree-with-rois"]
    swapped, far = held.eyes

    assert swapped.swapped is True
    assert swapped.reach <= face_blocks.EYE_REACH
    assert far.swapped is False
    expected = _expected_eye(block, _globe(_LEFT, shift=(40.0, 0.0, 0.0)), 1)
    assert far.reach == pytest.approx(expected["reach"], abs=1e-3)
    assert far.reach > face_blocks.EYE_REACH
    assert far.globe_errors == (pytest.approx(expected["error"], abs=1e-3),)


def test_targets_are_counted_by_where_they_lie(measured, block):
    by_outcome = _by_outcome(measured)
    defaced, held = by_outcome["defaced"], by_outcome["target-in-block"]

    assert defaced.targets == {"clear": 1}
    # The target lies above the block's inferior limit, so its clearance
    # is its distance behind the block's plane.
    ahead = (_BEHIND - np.array(block.origin)) @ np.array(block.anterior)
    assert np.min(_BEHIND[:, 2]) > block.inferior_limit
    assert defaced.clearances == (pytest.approx(-np.max(ahead), abs=1e-3),)
    assert held.targets == {"reaches-block": 1}
    assert held.clearances == ()
    assert [eye.side for eye in held.eyes] == ["right", "left"]


def test_a_series_without_a_block_counts_its_eye_rois_alone(measured):
    no_eyes = _by_outcome(measured)["no-eyes"]

    assert no_eyes.eye_rois == 1
    assert no_eyes.eyes == ()
    assert no_eyes.targets == {}


def test_rt_doses_in_the_defaced_frame_are_set_to_zero_or_held(measured):
    doses = sorted(measured.doses, key=lambda each: each.outcome)

    assert [each.outcome for each in doses] == ["dose-in-face-block", "set-to-zero"]
    assert doses[0].share == pytest.approx(_DOSE_HIGH / _DOSE_GREATEST)
    assert doses[1].share == pytest.approx(_DOSE_LOW / _DOSE_GREATEST)
    assert _DOSE_LOW / _DOSE_GREATEST <= dose_defacing.DOSE_FRACTION
    assert _DOSE_HIGH / _DOSE_GREATEST > dose_defacing.DOSE_FRACTION


def test_the_structure_set_in_the_defaced_frame_is_cut(measured):
    (cut,) = measured.structure_sets

    assert cut.outcome == "cut"
    # The body and the three eye ROIs reach the face; the target behind the
    # block and the organ within the head do not.
    assert cut.cut == {"EXTERNAL": 1, "ORGAN": 3}


def test_rt_plans_in_a_defaced_frame_are_counted(measured):
    assert (measured.plans, measured.plans_in_defaced_frames) == (2, 1)


def test_the_summary_counts_the_measures(summary):
    assert summary["format"] == "pymedphys-deid-face-validation-dicom/1"
    assert summary["series"] == {
        "defaced": 1,
        "not_defaced": {
            "eyes-disagree-with-rois": 1,
            "no-eyes": 1,
            "target-in-block": 1,
        },
        "with_eye_rois": {
            "defaced": 1,
            "eyes-disagree-with-rois": 1,
            "no-eyes": 1,
            "target-in-block": 1,
        },
    }
    eyes = summary["eye_rois"]
    assert eyes["series_with_a_block"] == 3
    assert eyes["by_series"] == {"agree": 2, "eyes-disagree-with-rois": 1}
    assert eyes["sides"] == {"left": 3, "not-named": 1, "right": 3}
    assert eyes["sides_swapped"] == 1
    assert eyes["not_placed"] == 0
    assert sum(each["count"] for each in eyes["globe_centre_error"]["bins"]) == 8
    assert sum(each["count"] for each in eyes["eye_reach"]["bins"]) == 7
    assert summary["targets"]["by_where"] == {"clear": 1, "reaches-block": 1}
    assert summary["rt_doses"]["outcomes"] == {
        "dose-in-face-block": 1,
        "set-to-zero": 1,
    }
    shares = [
        each["count"] for each in summary["rt_doses"]["share_set_to_zero"]["bins"]
    ]
    # 3% and 30% of the grid's greatest.
    assert shares == [0, 0, 1, 0, 0, 1, 0]
    assert summary["rt_structure_sets"] == {
        "outcomes": {"cut": 1},
        "rois_cut": {"EXTERNAL": 1, "ORGAN": 3},
    }
    assert summary["rt_plans"] == {"total": 2, "in_defaced_frames": 1}
    assert summary["ct"]["air_in_hounsfield_units"] == {
        "yes": 4,
        "no": 0,
        "not-measured": 0,
    }


def test_the_summary_holds_only_counts_codes_versions_and_settings(summary, exports):
    constants = {
        edge
        for module in (face_validation, face_validation_dicom)
        for bins in vars(module).values()
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
    text = json.dumps(summary) + markdown(summary)
    for secret in (_SECRET, _SECRET_ROI, "Eye_R", files.ROOT, "P1", str(exports)):
        assert secret not in text
    assert json.loads(json.dumps(summary)) == summary


def test_the_summary_is_the_same_each_time(measured, summary):
    assert face_validation_dicom.summarise(measured) == summary


def test_the_settings_are_the_engines(summary):
    settings = summary["settings"]

    assert settings["eye_reach_mm"] == face_blocks.EYE_REACH
    assert settings["margin_mm"] == defacing.MARGIN
    assert settings["cavity_floor_mm"] == face_blocks.CAVITY_FLOOR
    assert settings["dose_fraction"] == dose_defacing.DOSE_FRACTION


def test_measures_show_nothing_of_the_files(measured):
    assert repr(measured) == "DicomMeasures()"
    assert repr(measured.series[0]) == "SeriesMeasures()"
    assert repr(EyeMeasures("right")) == "EyeMeasures()"
    assert repr(measured.doses[0]) == "DoseMeasures()"
    assert repr(measured.structure_sets[0]) == "StructureSetMeasures()"


@pytest.mark.parametrize(
    "name, side",
    [
        ("Eye_R", 0),
        ("Eye_L", 1),
        ("EyeL", 1),
        ("LEye", 1),
        ("lefteye", 1),
        ("Globe Rt", 0),
        ("Right eyeball", 0),
        ("Eyes", None),
        ("Eye", None),
        ("Eye_L_Eye_R", None),
    ],
)
def test_an_eye_rois_side_is_read_from_its_name(name, side):
    assert side_of(name) == side


def test_the_centroid_weights_each_closed_contour_by_its_area():
    small = files.square((0.0, 0.0, 0.0), 1.0)
    large = files.square((10.0, 0.0, 3.0), 2.0)
    # A concave L of three unit squares, whose centroid is not its points'
    # mean.
    ell = np.array(
        [(0, 0, 9), (2, 0, 9), (2, 1, 9), (1, 1, 9), (1, 2, 9), (0, 2, 9)], float
    )

    np.testing.assert_allclose(
        centroid([("CLOSED_PLANAR", small), ("CLOSED_PLANAR", large)]),
        (np.array([0.0, 0.0, 0.0]) * 4 + np.array([10.0, 0.0, 3.0]) * 16) / 20,
    )
    np.testing.assert_allclose(
        centroid([("CLOSED_PLANAR", ell[::-1])]), (5 / 6, 5 / 6, 9.0)
    )
    # Contours that bound no area give their points' mean.
    np.testing.assert_allclose(
        centroid([("POINT", np.array([[1.0, 2.0, 3.0]])), ("POINT", small)]),
        np.concatenate([[[1.0, 2.0, 3.0]], small]).mean(axis=0),
    )


# A block whose plane is y = 0 with anterior towards -y, and whose inferior
# limit is z = 0: a point's distance ahead of the plane is -y.
_CORNER = FaceBlock((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), 0.0, ((0, 0, 0), (0, 0, 0)))


def test_clearance_is_found_where_an_edge_passes_behind_and_below_the_corner():
    # Ahead 2 mm and 10 mm below the limit, and 10 mm behind and 2 mm above
    # it: each point is 10 mm from the block, but the edge between them
    # passes within 4 root 2 mm of its corner.
    points = np.array([(5.0, -2.0, -10.0), (-5.0, 10.0, 2.0), (30.0, -2.0, -10.0)])

    assert not face_blocks._hull_reaches(  # pylint: disable = protected-access
        _CORNER, points
    )
    assert clearance(_CORNER, points) == pytest.approx(4 * math.sqrt(2))


@pytest.mark.parametrize(
    "points, expected",
    [
        (np.array([(0.0, 5.0, 3.0), (0.0, 7.0, 9.0), (4.0, 6.0, 1.0)]), 5.0),
        (np.array([(0.0, -4.0, -3.0), (2.0, -9.0, -6.0), (1.0, -6.0, -8.0)]), 3.0),
        (np.array([(0.0, 3.0, -4.0)]), 5.0),
    ],
)
def test_clearance_is_the_distance_to_the_block_from_its_nearest_vertex(
    points, expected
):
    assert clearance(_CORNER, points) == pytest.approx(expected)


def test_a_series_that_raises_is_counted_by_where_without_its_message(
    exports, monkeypatch
):
    def raising(*_):
        raise ValueError(f"/data/{_SECRET}/series")

    monkeypatch.setattr(face_validation_dicom, "_measure_series", raising)

    measured = face_validation_dicom.measure_dicom(exports)
    summary = face_validation_dicom.summarise(measured)
    page = markdown(summary)

    ((where, count),) = measured.crashed.items()
    assert count == 4
    assert where.startswith(
        "series: ValueError at test_deidentify_face_validation_dicom.py:"
    )
    assert where.endswith(" in raising")
    assert summary["crashed"] == {where: 4}
    assert f"| Crashed: `{where}` | 4 |\n" in page
    assert _SECRET not in json.dumps(summary) + page


def test_the_page_shows_the_counts_as_commonmark(summary):
    page = markdown(summary)

    assert page.startswith("# Face block check on DICOM files\n\n")
    assert page.endswith("|\n")
    assert "| Defaced | 1 |\n" in page
    assert "| Not defaced: `target-in-block` | 1 |\n" in page
    assert "| `EXTERNAL` | 1 |\n" in page
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
    exports, measured, tmp_path, capsys, monkeypatch
):
    # The files as the other tests measured them, rather than again.
    def measure(directory):
        assert directory == exports
        return measured

    monkeypatch.setattr(face_validation_dicom, "measure_dicom", measure)
    out = tmp_path / "results"

    status = face_validation_command.main(["dicom", str(exports), "--out", str(out)])

    assert status == 0
    summary = json.loads((out / "face-validation.json").read_text(encoding="utf-8"))
    page = (out / "face-validation.md").read_text(encoding="utf-8")
    assert summary["series"]["defaced"] == 1
    assert page == markdown(summary)
    assert capsys.readouterr().out == page


@pytest.mark.parametrize(
    "make, message",
    [
        (lambda path: path, "The directory holds no CT Image series."),
        (
            lambda path: path / "missing",
            "The input is not a directory whose files can be listed.",
        ),
    ],
)
def test_the_command_refuses_input_without_quoting_its_path(tmp_path, make, message):
    source = tmp_path / _SECRET
    source.mkdir()
    (source / "notes.txt").write_bytes(b"not DICOM")

    with pytest.raises(SystemExit) as refused:
        face_validation_command.main(
            ["dicom", str(make(source)), "--out", str(tmp_path / "out")]
        )

    assert refused.value.code == message
    assert not (tmp_path / "out").exists()


def test_the_command_reports_a_crash_by_where_without_its_message(
    tmp_path, monkeypatch
):
    def raising(_):
        raise ValueError(f"/data/{_SECRET}")

    monkeypatch.setattr(face_validation_dicom, "check_dicom", raising)

    with pytest.raises(SystemExit) as stopped:
        face_validation_command.main(
            ["dicom", str(tmp_path), "--out", str(tmp_path / "out")]
        )

    assert stopped.value.code.startswith(
        "The check stopped: ValueError at test_deidentify_face_validation_dicom.py:"
    )
    assert _SECRET not in stopped.value.code
    assert not (tmp_path / "out").exists()


def _segment_clearance(first: np.ndarray, second: np.ndarray) -> float:
    """The least distance from a segment to the quadrant where a point's
    distance ahead and height above are not negative, in the plane of the
    two, by the segment's nearest point to the corner or an end."""
    edge = second - first
    along = np.clip(-(first @ edge) / (edge @ edge), 0, 1) if edge @ edge else 0
    candidates = [first, second, first + along * edge]
    return min(float(np.linalg.norm(np.minimum(each, 0))) for each in candidates)


@pytest.mark.parametrize("seed", range(5))
def test_clearance_is_the_least_over_every_segment_between_the_points(seed):
    # Points behind the plane, or below the limit, but not both ahead and
    # above, in clusters whose hull may still pass the corner.
    generator = np.random.default_rng(seed)
    behind = generator.uniform((-50, 1, 0), (50, 30, 30), (20, 3))
    below = generator.uniform((-50, -30, -30), (50, -1, -1), (20, 3))
    for points in (behind, below, np.concatenate([behind[:10], below[:10]])):
        if face_blocks._hull_reaches(  # pylint: disable = protected-access
            _CORNER, points
        ):
            continue
        plane = np.column_stack([-points[:, 1], points[:, 2]])
        expected = min(
            _segment_clearance(plane[i], plane[j])
            for i in range(len(plane))
            for j in range(i, len(plane))
        )
        assert clearance(_CORNER, points) == pytest.approx(expected)
