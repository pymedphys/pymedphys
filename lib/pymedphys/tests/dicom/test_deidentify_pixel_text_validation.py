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

"""The text detector check, on invented volumes stored as HaN-Seg stores its
cases. Every value here is invented."""

from __future__ import annotations

import dataclasses
import importlib.util
import io
import json
import math

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest
from pymedphys._imports import scipy

from pymedphys._dicom.deidentify import (
    face_validation,
    nrrd,
    pixel_cleaning,
    pixel_text_validation,
    pixel_text_validation_command,
    text_detection,
)
from pymedphys._dicom.deidentify.pixel_text_validation import (
    VolumeMeasures,
    VolumeNotMeasured,
)
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _synthetic_nrrd as files

_SECRET = "SYNTHETIC-PATIENT-NAME"
_MARK = 3000
_BODY = 40
_AIR = -1000
# An axial CT of 4 slices of 30 rows and 40 columns, off centre, with rows
# 1.2 mm apart and columns 0.8 mm apart.
_CT_GRID = files.Grid(
    origin=(-14.3, 22.7, -35.0),
    axes=((0.8, 0.0, 0.0), (0.0, 1.2, 0.0), (0.0, 0.0, 2.5)),
    shape=(4, 30, 40),
)
# Coronal slices: columns along x, rows from superior down, slices from
# anterior back, 3 slices of 20 rows and 24 columns.
_MR_GRID = files.Grid(
    origin=(5.0, -60.0, 40.0),
    axes=((0.5, 0.0, 0.0), (0.0, 0.0, -0.7), (0.0, 1.5, 0.0)),
    shape=(3, 20, 24),
)


class MarkFinder:
    """Finds a box around each group of pixels of at least half of
    :data:`_MARK`, as the text detector finds one around each text line."""

    method = {"finds": "marks", "at_least": _MARK / 2}

    def find(self, frame: np.ndarray) -> tuple[TextBox, ...]:
        labels, _ = scipy.ndimage.label(frame >= _MARK / 2)
        return tuple(
            sorted(
                TextBox(rows.start, columns.start, rows.stop, columns.stop)
                for rows, columns in scipy.ndimage.find_objects(labels)
            )
        )


class _Overhanging(MarkFinder):
    """Gives one box past the frame's bottom right corner beside each mark's,
    and one wholly outside it."""

    def find(self, frame: np.ndarray) -> tuple[TextBox, ...]:
        rows, columns = frame.shape
        return (
            *super().find(frame),
            TextBox(rows - 2, columns - 3, rows + 5, columns + 5),
            TextBox(rows + 1, 0, rows + 4, 3),
        )


def _ct() -> np.ndarray:
    """The CT, in Hounsfield units: a body in air, with marks of text."""
    rows, columns = np.indices(_CT_GRID.shape[1:])
    body = ((rows - 18) / 10) ** 2 + ((columns - 20) / 15) ** 2 <= 1
    ct = np.broadcast_to(np.where(body, _BODY, _AIR), _CT_GRID.shape).astype(np.int16)
    # Slice 1: a line in the air at the top left, 3 rows by 12 columns.
    ct[1, 1:4, 2:14] = _MARK
    # Slice 3: a line of 2 rows by 6 columns inside the body, and a square
    # of 4 rows by 4 columns over its edge at the top right.
    ct[3, 17:19, 17:23] = _MARK
    ct[3, 7:11, 30:34] = _MARK
    return ct


def _mr() -> np.ndarray:
    """The MR, in floats: a mark of 2 rows by 5 columns on slice 0, and a
    value of half the mark less a little, which rounds to below it, on
    slice 2."""
    mr = np.full(_MR_GRID.shape, 100.25, dtype=np.float32)
    mr[0, 4:6, 10:15] = _MARK + 0.4
    mr[2, 10, 10] = _MARK / 2 - 0.6
    return mr


def _volume(values: np.ndarray, grid: files.Grid, **options) -> nrrd.Volume:
    return nrrd.read_nrrd(io.BytesIO(files.nrrd_file(values, grid, **options)))


def _cases() -> dict[str, dict[str, bytes]]:
    secret = {"PatientName": _SECRET}
    nan = _ct().astype(np.float32)
    nan[0, 0, 0] = np.nan
    truncated = files.nrrd_file(_ct(), _CT_GRID, encoding="raw")[:-10]
    return {
        "case_01": {
            "IMG_CT.nrrd": files.nrrd_file(_ct(), _CT_GRID, key_values=secret),
            "IMG_MR_T1.nrrd": files.nrrd_file(_mr(), _MR_GRID, key_values=secret),
            # Masks are not read.
            "OAR_Eye_AR.seg.nrrd": b"not an NRRD file",
        },
        # The same CT, in RAS, raw; and no MR.
        "case_02": {
            "IMG_CT.nrrd": files.nrrd_file(
                _ct(), _CT_GRID, space=files.RAS, encoding="raw"
            )
        },
        "case_03": {"IMG_CT.nrrd": truncated},
        "case_04": {
            "IMG_CT.nrrd": files.nrrd_file(
                _ct()[..., np.newaxis], _CT_GRID, layered=True
            )
        },
        "case_05": {"IMG_CT.nrrd": files.nrrd_file(nan, _CT_GRID)},
    }


@pytest.fixture(name="archive", scope="module")
def fixture_archive(tmp_path_factory):
    path = tmp_path_factory.mktemp("hanseg") / "HaN-Seg.zip"
    files.hanseg_zip(path, _cases())
    return path


@pytest.fixture(name="measured", scope="module")
def fixture_measured(archive):
    return pixel_text_validation.measure_hanseg(archive, "CT", finder=MarkFinder)


@pytest.fixture(name="summary", scope="module")
def fixture_summary(archive):
    return pixel_text_validation.check_hanseg(archive, "CT", finder=MarkFinder)


def test_each_slice_is_searched_and_each_region_measured(measured):
    ct = measured[0]
    assert isinstance(ct, VolumeMeasures)
    assert ct.regions == (0, 1, 0, 2)
    # The regions in the finder's order: by top row, the square first.
    frame = 30 * 40
    assert ct.areas == pytest.approx((3 * 12 / frame, 4 * 4 / frame, 2 * 6 / frame))
    assert ct.shorter_sides == (3, 4, 2)
    assert ct.elongations == pytest.approx((4.0, 1.0, 3.0))


def test_a_ct_regions_share_of_pixels_above_air_is_measured(measured):
    ct = measured[0]
    assert isinstance(ct, VolumeMeasures)
    # The line in the air is all mark, which is above air; so is the line in
    # the body. The square over the body's edge is all mark too.
    assert ct.not_air == pytest.approx((1.0, 1.0, 1.0))


def test_a_region_over_air_is_measured_by_its_pixels():
    ct = _ct()
    # A box around two marks a column apart holds the air between them.
    ct[1, 1:4, 2:14] = _AIR
    ct[1, 1:4, 2:5] = _MARK
    ct[1, 1:4, 6:9] = _MARK

    class Spanning(MarkFinder):
        def find(self, frame):
            found = super().find(frame)
            if len(found) != 2 or found[0].top != 1:
                return found
            return (TextBox(1, 2, 4, 9),)

    measures = pixel_text_validation.measure_volume(
        _volume(ct, _CT_GRID), Spanning(), ct=True
    )
    assert measures.regions[1] == 1
    # 18 of 21 pixels are mark; the column between them, 3 pixels, air.
    assert measures.not_air[0] == pytest.approx(18 / 21)


def test_a_volume_in_another_space_measures_the_same(measured):
    first, second = measured[0], measured[1]
    assert isinstance(second, VolumeMeasures)
    for field in ("regions", "areas", "shorter_sides", "elongations", "not_air"):
        assert getattr(first, field) == getattr(second, field)
    assert first.format == "int16 gzip left-posterior-superior"
    assert second.format == "int16 raw right-anterior-superior"


def test_the_volume_geometry_is_measured(measured):
    ct = measured[0]
    assert ct.plane == "axial"
    assert ct.slice_side == 40
    assert ct.pixel_spacing == pytest.approx(1.2)


@pytest.mark.parametrize(
    "index, reason",
    [
        (2, "not-read/data-length"),
        (3, "not-three-dimensional"),
        (4, "values-not-finite"),
    ],
)
def test_a_volume_that_cannot_be_measured_is_counted_by_why(measured, index, reason):
    assert measured[index] == VolumeNotMeasured(reason)


def test_an_mr_is_searched_in_its_own_plane_with_its_values_rounded(archive):
    (mr,) = pixel_text_validation.measure_hanseg(archive, "MR_T1", finder=MarkFinder)
    assert isinstance(mr, VolumeMeasures)
    assert mr.plane == "coronal"
    assert mr.format == "float32 gzip left-posterior-superior"
    # The value just under half the mark rounds to under it, so gives no
    # region.
    assert mr.regions == (1, 0, 0)
    assert mr.areas == pytest.approx((2 * 5 / (20 * 24),))
    assert mr.not_air is None
    assert mr.pixel_spacing == pytest.approx(0.7)


@pytest.mark.parametrize(
    "normal, plane",
    [
        ((0.0, 0.0, 1.0), "axial"),
        ((0.0, -1.0, 0.0), "coronal"),
        ((1.0, 0.0, 0.0), "sagittal"),
        ((0.0, math.sin(math.radians(9.0)), math.cos(math.radians(9.0))), "axial"),
        ((0.0, math.sin(math.radians(11.0)), math.cos(math.radians(11.0))), "oblique"),
    ],
)
def test_the_plane_is_named_by_the_axis_nearest_the_normal(normal, plane):
    normal = np.array(normal)
    # Two axes in the plane, of different lengths, whose cross product is
    # along the normal.
    helper = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0, 1, 0])
    first = np.cross(normal, helper)
    second = np.cross(normal, first)
    axes = np.array([0.8 * first / np.linalg.norm(first), 1.3 * second, normal])
    assert pixel_text_validation._plane(axes) == plane  # pylint: disable = protected-access


def test_regions_are_clipped_to_the_slice_as_a_run_clips_them():
    measures = pixel_text_validation.measure_volume(
        _volume(_ct(), _CT_GRID), _Overhanging(), ct=True
    )
    # Each slice gains the box over its corner, 2 rows by 3 columns once
    # clipped; the box wholly outside is dropped.
    assert measures.regions == (1, 2, 1, 3)
    assert measures.areas.count(pytest.approx(2 * 3 / (30 * 40))) == 4


def test_a_finder_that_gives_anything_but_boxes_is_counted_as_crashed(tmp_path):
    class Wrong:
        method = MarkFinder.method

        def find(self, frame):  # pylint: disable = unused-argument
            return ((0, 0, 1, 1),)

    path = tmp_path / "HaN-Seg.zip"
    files.hanseg_zip(
        path, {"case_01": {"IMG_CT.nrrd": files.nrrd_file(_ct(), _CT_GRID)}}
    )
    (volume,) = pixel_text_validation.measure_hanseg(path, "CT", finder=Wrong)
    assert volume.reason == "crashed"
    assert volume.where.startswith("TypeError at pixel_text_validation.py:")


def test_a_volume_that_raises_is_counted_by_where_without_its_message(tmp_path):
    class Raising(MarkFinder):
        def find(self, frame):
            raise ValueError(_SECRET)

    path = tmp_path / "HaN-Seg.zip"
    files.hanseg_zip(
        path, {"case_01": {"IMG_CT.nrrd": files.nrrd_file(_ct(), _CT_GRID)}}
    )
    summary = pixel_text_validation.check_hanseg(path, "CT", finder=Raising)
    assert summary["volumes"]["not_measured"] == {"crashed": 1}
    (site,) = summary["volumes"]["crashed"]
    assert site.startswith("ValueError at ")
    assert _SECRET not in json.dumps(summary)


def test_workers_find_what_one_process_finds(archive, measured):
    in_workers = pixel_text_validation.measure_hanseg(
        archive, "CT", finder=MarkFinder, workers=2
    )
    assert len(in_workers) == len(measured)
    for first, second in zip(measured, in_workers, strict=True):
        assert type(first) is type(second)
        assert dataclasses.astuple(first) == dataclasses.astuple(second)


def test_the_summary_counts_the_volumes_slices_and_regions(summary):
    assert summary["format"] == "pymedphys-deid-pixel-text-validation/1"
    assert summary["image"] == "CT"
    assert summary["volumes"] == {
        "total": 5,
        "measured": 2,
        "not_measured": {
            "not-read/data-length": 1,
            "not-three-dimensional": 1,
            "values-not-finite": 1,
        },
        "crashed": {},
        "formats": {
            "int16 gzip left-posterior-superior": 1,
            "int16 raw right-anterior-superior": 1,
        },
        "planes": {"axial": 2},
        "slice_side": pixel_text_validation.SLICE_SIDE.counts([40, 40]),
        "pixel_spacing": face_validation.PIXEL_SPACING.counts([1.2, 1.2]),
    }
    assert summary["slices"] == {
        "searched": 8,
        "with_a_region": 4,
        "regions": pixel_text_validation.REGIONS_PER_SLICE.counts(
            [0, 1, 0, 2, 0, 1, 0, 2]
        ),
    }
    assert summary["slices"]["regions"]["bins"][:4] == [
        {"from": 0, "to": 1, "count": 4},
        {"from": 1, "to": 2, "count": 2},
        {"from": 2, "to": 3, "count": 2},
        {"from": 3, "to": 4, "count": 0},
    ]
    by_volume = summary["volumes_by_regions"]
    assert by_volume["with_a_region"] == 2
    assert by_volume["regions"] == pixel_text_validation.REGIONS_PER_VOLUME.counts(
        [3, 3]
    )
    assert by_volume["share_of_slices_with_a_region"] == (
        face_validation.SHARE.counts([0.5, 0.5])
    )
    regions = summary["regions"]
    assert regions["total"] == 6
    assert [each["count"] for each in regions["shorter_side"]["bins"]] == [
        6,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    ]
    assert regions["share_not_air"] == face_validation.SHARE.counts([1.0] * 6)


def test_an_mr_summary_gives_no_share_above_air(archive):
    summary = pixel_text_validation.check_hanseg(archive, "MR_T1", finder=MarkFinder)
    assert summary["image"] == "MR_T1"
    assert summary["volumes"]["planes"] == {"coronal": 1}
    assert summary["regions"]["share_not_air"] is None
    assert "above -900 HU" not in pixel_text_validation.markdown(summary)


def test_the_summary_holds_only_counts_codes_digests_versions_and_the_method(
    summary, archive
):
    text = json.dumps(summary)
    assert _SECRET not in text
    assert "case_0" not in text
    assert str(archive.parent) not in text
    assert summary["data"]["file"] == face_validation.file_digest(archive)
    assert summary["data"]["doi"] == "10.5281/zenodo.7442914"
    assert set(summary["software"]) == {
        "python",
        "pymedphys",
        "numpy",
        "scipy",
        "onnxruntime",
    }


def test_the_method_is_the_one_the_method_digest_takes(summary):
    assert summary["detector"] == {
        "finder": f"{MarkFinder.__module__}.MarkFinder",
        "method": {"finds": "marks", "at_least": _MARK / 2},
    }
    described = pixel_cleaning.finder_description(MarkFinder())
    assert summary["detector"]["finder"] == described["finder"]


def test_the_summary_is_the_same_each_time(summary, archive):
    again = pixel_text_validation.check_hanseg(archive, "CT", finder=MarkFinder)
    assert json.dumps(again, sort_keys=True) == json.dumps(summary, sort_keys=True)


def test_measures_show_nothing_of_a_volume(measured):
    assert repr(measured[0]) == "VolumeMeasures()"


def test_the_page_shows_the_counts_as_commonmark(summary):
    page = pixel_text_validation.markdown(summary)
    assert page.startswith("# Text detector check on HaN-Seg CT\n")
    assert page.endswith("\n") and not page.endswith("\n\n")
    assert "| Not measured: `values-not-finite` | 1 |" in page
    assert "Slices searched: 8. Slices with a region: 4. Regions: 6." in page
    assert "| 0 to under 1 | 4 |" in page
    assert "| Share of the region's pixels above -900 HU (share) | Regions |" in page
    assert _SECRET not in page
    # Every table's rows have the header's columns.
    for block in page.split("\n\n"):
        rows = [line for line in block.splitlines() if line.startswith("|")]
        assert len({row.count("|") for row in rows}) <= 1


def test_the_command_writes_the_counts_and_prints_the_page(
    archive, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(pixel_text_validation_command, "TextDetector", MarkFinder)
    out = tmp_path / "results"
    assert (
        pixel_text_validation_command.main(
            ["hanseg", str(archive), "--image", "CT", "--out", str(out)]
        )
        == 0
    )
    written = json.loads((out / "pixel-text-validation.json").read_text("utf-8"))
    page = (out / "pixel-text-validation.md").read_text("utf-8")
    assert written["slices"]["searched"] == 8
    assert page == pixel_text_validation.markdown(written)
    assert capsys.readouterr().out == page


def test_the_command_refuses_an_output_directory_that_exists(archive, tmp_path):
    with pytest.raises(SystemExit, match="must not exist"):
        pixel_text_validation_command.main(
            ["hanseg", str(archive), "--image", "CT", "--out", str(tmp_path)]
        )


def test_the_command_refuses_a_file_that_is_not_a_zip_file_or_holds_no_volume(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(pixel_text_validation_command, "TextDetector", MarkFinder)
    path = tmp_path / f"{_SECRET}.zip"
    path.write_bytes(b"not a ZIP file")
    with pytest.raises(SystemExit) as refused:
        pixel_text_validation_command.main(
            ["hanseg", str(path), "--image", "CT", "--out", str(tmp_path / "a")]
        )
    assert str(refused.value) == "The data set is not a readable ZIP file."
    files.hanseg_zip(path, {"case_01": {"IMG_CT.nrrd": b""}})
    with pytest.raises(SystemExit) as refused:
        pixel_text_validation_command.main(
            ["hanseg", str(path), "--image", "MR_T1", "--out", str(tmp_path / "b")]
        )
    assert str(refused.value) == "The ZIP file holds no HaN-Seg MR_T1 volume."
    assert not (tmp_path / "a").exists() and not (tmp_path / "b").exists()


def test_the_command_reports_a_detector_that_cannot_run_without_a_traceback(
    archive, tmp_path, monkeypatch
):
    def unmade():
        raise text_detection.TextDetectionError("ONNX Runtime cannot load the model")

    monkeypatch.setattr(pixel_text_validation_command, "TextDetector", unmade)
    with pytest.raises(SystemExit) as refused:
        pixel_text_validation_command.main(
            ["hanseg", str(archive), "--image", "CT", "--out", str(tmp_path / "a")]
        )
    assert str(refused.value) == (
        "The text detector cannot run: ONNX Runtime cannot load the model."
    )


@pytest.mark.parametrize(
    "image, workers, message",
    [
        ("PET", 1, "The image must be one of CT, MR_T1."),
        ("CT", 0, "There must be at least one worker."),
    ],
)
def test_an_unknown_image_or_no_worker_is_refused(archive, image, workers, message):
    with pytest.raises(pixel_text_validation.PixelTextValidationRefused) as refused:
        pixel_text_validation.measure_hanseg(
            archive, image, finder=MarkFinder, workers=workers
        )
    assert str(refused.value) == message


@pytest.mark.slow
def test_the_text_detector_runs_as_a_run_makes_it_in_one_process_or_several(
    tmp_path,
):
    # Importing ONNX Runtime here, as pytest.importorskip would, enables its
    # telemetry for the session, and the detector would then refuse to run.
    if importlib.util.find_spec("onnxruntime") is None:
        pytest.skip(f"needs pymedphys[{text_detection.EXTRA}]")
    path = tmp_path / "HaN-Seg.zip"
    files.hanseg_zip(
        path, {"case_01": {"IMG_CT.nrrd": files.nrrd_file(_ct(), _CT_GRID)}}
    )
    detector = text_detection.TextDetector
    one = pixel_text_validation.check_hanseg(path, "CT", finder=detector)
    several = pixel_text_validation.check_hanseg(path, "CT", finder=detector, workers=2)
    assert json.dumps(one, sort_keys=True) == json.dumps(several, sort_keys=True)
    assert one["detector"] == pixel_text_validation.described(detector())
    method = one["detector"]["method"]
    assert method["model_sha256"] == text_detection.PP_OCRV6_DET_SMALL.member_sha256
    assert method["parameters"] == dataclasses.asdict(
        text_detection.DetectionParameters()
    )
    assert one["slices"]["searched"] == 4
