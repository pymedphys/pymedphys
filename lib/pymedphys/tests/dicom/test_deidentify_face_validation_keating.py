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

"""The Keating face block check (D-058), on the analytic head written as a
hospital's CD export, as the Keating record holds its CT. Every value here
is invented."""

from __future__ import annotations

import importlib.util
import io
import json
import zipfile

import pytest

from pymedphys._imports import pydicom

from pymedphys._dicom.deidentify import face_validation_command
from pymedphys._dicom.deidentify import face_validation_keating as keating
from pymedphys._dicom.deidentify import face_validation_vhp as vhp
from pymedphys._dicom.deidentify.face_validation import (
    FaceValidationRefused,
    file_digest,
)
from pymedphys._dicom.deidentify.face_validation_keating_markdown import markdown

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files

GLOBES = (
    (-head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
    (head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
)
SCAN = head.axial(
    spacing=1.0, thickness=2.5, extent=((-100, 100), (-130, 110), (-40, 120))
)
EXPORT = "CT Export"
_SECRET = "SYNTHETIC-PATIENT-NAME"
# The folders over which the export spreads each series' files, as a CD
# export does, giving files of the same name in different folders.
_FOLDERS = "ABC"


def _axial(series_number: str, series_uid: str) -> list[bytes]:
    written = []
    for data in files.ct_files(SCAN, series=series_uid, padding=-2000):
        dataset = pydicom.dcmread(io.BytesIO(data))
        dataset.SeriesNumber = series_number
        dataset.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
        dataset.PatientName = _SECRET
        written.append(files.written(dataset))
    return written


def _export(path) -> None:
    """A ZIP file laid out as the Keating record's: the series' files, a
    localiser of series 3, a structured report, the CD's viewer, a
    DICOMDIR-like file, and the macOS archiver's metadata."""
    series = {"3": _axial("3", files.SERIES), "4": _axial("4", files.ROOT + ".8")}
    localiser = pydicom.dcmread(io.BytesIO(series["3"][0]))
    localiser.ImageType = ["ORIGINAL", "PRIMARY", "LOCALIZER"]
    localiser.SOPInstanceUID = files.ROOT + ".9.1"
    localiser.file_meta.MediaStorageSOPInstanceUID = localiser.SOPInstanceUID
    report = pydicom.dcmread(io.BytesIO(series["4"][0]))
    report.SOPClassUID = "1.2.840.10008.5.1.4.1.1.88.22"
    report.file_meta.MediaStorageSOPClassUID = report.SOPClassUID
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{EXPORT}/", b"")
        archive.writestr(f"{EXPORT}/CDVIEWER.EXE", b"MZ not DICOM")
        archive.writestr(f"{EXPORT}/A/Z99", files.written(localiser))
        archive.writestr(f"{EXPORT}/C/Z98", files.written(report))
        archive.writestr(f"__MACOSX/{EXPORT}/A/._Z00", series["3"][0])
        for number, written in series.items():
            for index, data in enumerate(written):
                folder = _FOLDERS[index % len(_FOLDERS)]
                name = f"Z{index // len(_FOLDERS):02d}"
                archive.writestr(f"{EXPORT}/{number}{folder}/{name}", data)


@pytest.fixture(name="data", scope="module")
def _data(tmp_path_factory):
    root = tmp_path_factory.mktemp("keating")
    archive = root / "export.zip"
    _export(archive)
    extracted = root / "extracted"
    with zipfile.ZipFile(archive) as opened:
        counts = keating.extract_series(opened, extracted)
    series = tuple(
        vhp.VhpSeries(
            each.uuid,
            keating.SUBJECT,
            each.description,
            *vhp.manifest_digest(extracted / each.uuid),
            GLOBES,
            rendered=each.uuid == "series-4",
            name=each.name,
        )
        for each in keating.SERIES
    )
    return archive, extracted, counts, series


@pytest.fixture(name="pinned")
def _pinned(data, monkeypatch):
    """The synthetic export and its series pinned in place of the record's."""
    archive, _, _, series = data
    digest = file_digest(archive)
    monkeypatch.setattr(keating, "ARCHIVE_SIZE", digest["size"])
    monkeypatch.setattr(keating, "ARCHIVE_MD5", digest["md5"])
    monkeypatch.setattr(keating, "ARCHIVE_SHA256", digest["sha256"])
    monkeypatch.setattr(keating, "SERIES", series)
    return archive, series


@pytest.fixture(name="summary", scope="module")
def _summary(data, tmp_path_factory):
    archive, _, _, series = data
    digest = file_digest(archive)
    renders = tmp_path_factory.mktemp("renders") / "renders"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(keating, "ARCHIVE_SIZE", digest["size"])
        patch.setattr(keating, "ARCHIVE_MD5", digest["md5"])
        patch.setattr(keating, "ARCHIVE_SHA256", digest["sha256"])
        return keating.check_keating(archive, renders, series), renders


@pytest.fixture(name="rendering")
def _rendering():
    # The user extra supplies Matplotlib for this private evidence renderer.
    if importlib.util.find_spec("matplotlib") is None:
        pytest.importorskip(
            "matplotlib", reason="This private validation renderer needs Matplotlib."
        )


def test_the_pinned_series_are_the_records_two_axial_series():
    assert [each.uuid for each in keating.SERIES] == ["series-3", "series-4"]
    assert {each.subject for each in keating.SERIES} == {"Keating"}
    assert len({each.name for each in keating.SERIES}) == 2
    for each in keating.SERIES:
        assert each.files == 216
        assert len(each.sha256) == 64
        assert each.rendered
        assert each.globes == keating.GLOBES
    right, left = keating.GLOBES
    # The patient's right is towards lower x.
    assert right[0] < left[0]
    assert 50.0 < left[0] - right[0] < 70.0
    assert len(keating.ARCHIVE_MD5) == 32
    assert len(keating.ARCHIVE_SHA256) == 64


def test_only_the_axial_ct_of_each_series_is_extracted(data):
    _, extracted, counts, _ = data
    assert counts == {"series-3": len(SCAN.positions), "series-4": len(SCAN.positions)}
    names = sorted(path.name for path in (extracted / "series-3").iterdir())
    # Named for their folders, since names repeat across folders.
    assert names[:3] == ["3A-Z00", "3A-Z01", "3A-Z02"]
    assert not any("Z99" in name or "Z98" in name for name in names)
    assert sorted(path.name for path in extracted.iterdir()) == [
        "series-3",
        "series-4",
    ]


def test_each_series_block_is_found_and_measured_against_the_reference(summary):
    for series in summary[0]["series"]:
        # Only rendering needs Matplotlib, so only the rendered series,
        # series 4 here, could crash without it.
        if series["series"] != "series-4":
            assert "crashed" not in series
        assert series["engine"]["outcome"] == "block"
        assert max(series["engine"]["globe_error_mm"]) < 2.0
        assert series["engine"]["swapped"] is False
        assert set(series["defacing"]) >= {"engine", "reference"}
        engine = series["defacing"]["engine"]
        assert engine["pixels_written_outside_block"] == 0
        for globe in engine["reference_globes"]:
            assert globe["anterior_pole_written"]


@pytest.mark.usefixtures("rendering")
def test_the_rendered_series_carries_the_records_credit(summary):
    whole, renders = summary
    plain, rendered = whole["series"]
    assert "crashed" not in rendered
    assert "renders" not in plain
    assert "Keating-series-4-globes.png" in rendered["renders"]
    assert "Keating-series-4-surface-engine.png" in rendered["renders"]
    for name in rendered["renders"]:
        if name.endswith(".png"):
            assert (renders / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    notice = (renders / "NOTICE.txt").read_text(encoding="utf-8")
    assert keating.ATTRIBUTION in notice
    assert keating.NOTICE in notice
    assert "National Library of Medicine" not in notice


def test_the_summary_carries_the_source_and_nothing_of_the_headers(summary):
    whole = summary[0]
    assert whole["format"] == keating.FORMAT
    assert whole["source"]["record_doi"] == "10.5281/zenodo.16816"
    assert whole["source"]["licence"] == "CC0 1.0"
    assert whole["held_out"] == keating.HELD_OUT
    text = json.dumps(whole)
    assert _SECRET not in text
    assert files.SERIES not in text


def test_an_archive_that_is_not_the_one_pinned_is_refused(pinned, tmp_path):
    archive, _ = pinned
    changed = tmp_path / "export.zip"
    changed.write_bytes(archive.read_bytes() + b"\0")
    with pytest.raises(FaceValidationRefused, match="archive is not the one pinned"):
        keating.check_keating(changed, tmp_path / "renders")
    assert not (tmp_path / "renders").exists()


def test_a_series_that_is_not_the_one_pinned_is_refused_before_any_render(
    pinned, tmp_path, monkeypatch
):
    archive, series = pinned
    first, second = series
    other = vhp.VhpSeries(
        second.uuid, second.subject, second.description, second.files, "0" * 64
    )
    monkeypatch.setattr(keating, "SERIES", (first, other))
    with pytest.raises(FaceValidationRefused, match="series-4 is not the one pinned"):
        keating.check_keating(archive, tmp_path / "renders")
    assert not (tmp_path / "renders").exists()


@pytest.mark.usefixtures("rendering")
def test_the_page_shows_the_measures_as_commonmark(summary):
    page = markdown(summary[0])
    assert page.startswith("# Face block check on Steven Keating's cranial CT\n")
    assert page.count(keating.ATTRIBUTION) == 2
    assert "| `series-3` |" in page
    assert "### Defacing" in page
    assert "\t" not in page
    assert "\n\n\n" not in page
    assert page.endswith("\n")


@pytest.mark.usefixtures("rendering")
def test_the_command_writes_the_summary_page_and_renders(pinned, tmp_path, capsys):
    archive, _ = pinned
    out = tmp_path / "out"
    assert (
        face_validation_command.main(["keating", str(archive), "--out", str(out)]) == 0
    )
    summary = json.loads((out / keating.JSON_NAME).read_text(encoding="utf-8"))
    assert [each["engine"]["outcome"] for each in summary["series"]] == [
        "block",
        "block",
    ]
    page = (out / keating.MARKDOWN_NAME).read_text(encoding="utf-8")
    assert capsys.readouterr().out == page
    assert (out / keating.RENDERS / "Keating-series-4-globes.png").is_file()
    with pytest.raises(SystemExit, match="must not exist"):
        face_validation_command.main(["keating", str(archive), "--out", str(out)])


def test_the_command_refuses_an_archive_that_is_not_the_one_pinned(tmp_path):
    archive = tmp_path / f"{_SECRET}.zip"
    archive.write_bytes(b"not the record")
    with pytest.raises(SystemExit) as refused:
        face_validation_command.main(
            ["keating", str(archive), "--out", str(tmp_path / "out")]
        )
    assert "not the one pinned" in str(refused.value.code)
    assert _SECRET not in str(refused.value.code)
    assert not (tmp_path / "out").exists()
