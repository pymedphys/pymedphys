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

"""The evaluation's command on a folder of DICOM files on a person's own
machine (T6), with synthetic RT Images and a stand-in network."""

import functools
import json
import logging
import multiprocessing
import pathlib

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import diagnostics
from pymedphys._dicom.deidentify import text_evaluation_detector as detector
from pymedphys._dicom.deidentify import text_evaluation_font_files as font_files
from pymedphys._dicom.deidentify import text_evaluation_fonts as fonts
from pymedphys._dicom.deidentify import text_evaluation_local_command as command

from .test_deidentify_text_evaluation import PATIENT_A, PATIENT_B, _clinic
from .test_deidentify_text_evaluation_command import bright

SECRETS = (PATIENT_A, PATIENT_B, "2.25.10", "2.25.11", "2.25.20", "2.25.21")
CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"


@pytest.fixture(name="stand_in")
def _stand_in(monkeypatch):
    monkeypatch.setattr(
        command,
        "EvaluationDetector",
        functools.partial(
            detector.EvaluationDetector, network=bright, network_name="bright"
        ),
    )


@pytest.fixture(name="clinic")
def _clinic_folder(tmp_path):
    """The synthetic clinic's folder, read only, and its annotations."""
    root, _ = _clinic(tmp_path / "read")
    for path in root.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)
    yield root, tmp_path / "read" / "annotations.csv"
    for path in [root, *root.rglob("*")]:
        path.chmod(0o755 if path.is_dir() else 0o644)


def _files(root):
    return {
        str(path.relative_to(root)): (path.stat().st_mtime_ns, path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _run(clinic, out, *options):
    root, _ = clinic
    return command.main(
        [str(root), "--out", str(out), "--fonts", "bitmaps", "--evaluated", "all"]
        + list(options)
    )


def test_a_folders_rt_images_are_measured_by_counts_alone(
    tmp_path, monkeypatch, capsys, clinic, stand_in
):
    """Each RT Image is measured as read, its regions counted where text is
    unknown, and with text burned into a copy in memory; only counts are
    written, outside the folder, which is left as it was."""
    del stand_in
    root, _ = clinic
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)
    before = _files(root)
    out = tmp_path / "results"
    assert _run(clinic, out) == 0
    assert _files(root) == before
    assert not list(working.iterdir())
    assert sorted(each.name for each in out.iterdir()) == list(command.WRITTEN)
    summary = json.loads((out / "summary.json").read_text())
    assert summary["frames"] == {"RT Image Storage": 3}
    assert summary["skipped"] == {"not-read": 1, "sop-class-not-selected": 1}
    assert list(summary["collections"]) == [command.DEFAULT_COLLECTION]
    point = summary["points"][0]
    assert point["text_unknown"]["frames"] == 3
    assert point["false_positives"]["frames"] == 0
    sensitivity = point["sensitivity"]
    assert sensitivity["texts"] > 0
    assert (
        sensitivity["fully_covered"]
        + sensitivity["partly_covered"]
        + sensitivity["missed"]
        == sensitivity["texts"]
    )
    tiers = {row["value"]["tier"] for row in point["by"]["tier"]}
    assert tiers == {"T6"}
    assert summary["plan"]["fonts"] == ["bitmap-5x7", "bitmap-5x7-smooth"]
    assessment = json.loads((out / "assessment.json").read_text())
    assert assessment and not assessment[0]["meets"]
    printed = capsys.readouterr().out
    assert printed == (out / "summary.md").read_text()
    written = "".join(path.read_text() for path in out.iterdir()) + printed
    for secret in (*SECRETS, str(root), "clinic export", "notes"):
        assert secret not in written


def test_annotated_text_is_measured_and_the_folder_said_to_hold_none(
    tmp_path, clinic, stand_in
):
    del stand_in
    _, annotations = clinic
    out = tmp_path / "annotated"
    assert _run(clinic, out, "--annotations", str(annotations)) == 0
    summary = json.loads((out / "summary.json").read_text())
    point = summary["points"][0]
    known = {row["value"]["known_text"] for row in point["by"]["known_text"]}
    assert known == {"annotated", "unknown"}
    assert summary["skipped"]["annotation-not-found"] == 1
    out = tmp_path / "none"
    assert _run(clinic, out, "--known-text", "none") == 0
    point = json.loads((out / "summary.json").read_text())["points"][0]
    assert point["text_unknown"]["frames"] == 0
    assert point["false_positives"]["frames"] == 3


def test_other_sop_classes_are_read_only_when_asked_for(tmp_path, clinic, stand_in):
    del stand_in
    out = tmp_path / "all"
    assert _run(clinic, out, "--all-sop-classes") == 0
    frames = json.loads((out / "summary.json").read_text())["frames"]
    assert frames == {"CT Image Storage": 1, "RT Image Storage": 3}
    out = tmp_path / "ct"
    assert _run(clinic, out, "--sop-class", CT_IMAGE_STORAGE) == 0
    frames = json.loads((out / "summary.json").read_text())["frames"]
    assert frames == {"CT Image Storage": 1}
    with pytest.raises(SystemExit):
        _run(clinic, tmp_path / "both", "--all-sop-classes", "--sop-class", "1.2")


def test_refusals_quote_no_path(tmp_path, clinic):
    root, _ = clinic
    taken = tmp_path / "taken"
    taken.mkdir()
    refusals = (
        ([str(root), "--out", str(taken)], "must not exist"),
        ([str(root), "--out", str(root / "results")], "outside the folder"),
        ([str(root / "a" / "2.dcm"), "--out", str(tmp_path / "o")], "a directory"),
        (
            [str(root), "--out", str(tmp_path / "o"), "--sop-class", "1.2.3"],
            "no DICOM file of a SOP Class read",
        ),
        (
            [
                str(root),
                "--out",
                str(tmp_path / "o"),
                "--annotations",
                str(tmp_path / "missing.csv"),
            ],
            "annotations file cannot be read",
        ),
    )
    for argv, message in refusals:
        with pytest.raises(SystemExit, match=message) as raised:
            command.main(argv)
        assert str(root) not in str(raised.value)
        assert str(tmp_path) not in str(raised.value)
    assert not (root / "results").exists()
    assert not (tmp_path / "o").exists()


def test_a_crash_is_reported_by_where_alone(tmp_path, monkeypatch, clinic):
    def raising(*args, **kwargs):
        raise ValueError(f"{PATIENT_A} in {tmp_path}")

    monkeypatch.setattr(command, "dicom_folder_cases", raising)
    with pytest.raises(SystemExit, match="ValueError at") as raised:
        _run(clinic, tmp_path / "o")
    assert PATIENT_A not in str(raised.value)
    assert str(tmp_path) not in str(raised.value)
    assert not (tmp_path / "o").exists()


def _measured(arguments):
    del arguments
    return {name: "counts\n" for name in command.WRITTEN}


def _no_path_or_traceback(raised, *paths):
    message = str(raised.value)
    assert "Traceback" not in message
    for path in paths:
        assert str(path) not in message
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


def test_an_output_directory_that_cannot_be_made_is_reported_by_where_alone(
    tmp_path, monkeypatch, clinic
):
    monkeypatch.setattr(command, "measure", _measured)
    blocking = tmp_path / "a file"
    blocking.write_text("not a directory")
    out = blocking / "results"
    with pytest.raises(SystemExit, match="The command stopped: ") as raised:
        _run(clinic, out)
    _no_path_or_traceback(raised, tmp_path, out)


def test_a_result_that_cannot_be_written_is_reported_by_where_alone(
    tmp_path, monkeypatch, clinic
):
    monkeypatch.setattr(command, "measure", _measured)

    def refused(path, *args, **kwargs):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(pathlib.Path, "write_text", refused)
    out = tmp_path / "results"
    with pytest.raises(SystemExit, match="PermissionError at ") as raised:
        _run(clinic, out)
    _no_path_or_traceback(raised, tmp_path, out)


def test_published_settings_without_opencv_are_refused(tmp_path, monkeypatch, clinic):
    found = command.importlib.util.find_spec
    monkeypatch.setattr(
        command.importlib.util,
        "find_spec",
        lambda name, *args: None if name == "cv2" else found(name, *args),
    )
    with pytest.raises(SystemExit, match="--settings today"):
        _run(
            clinic,
            tmp_path / "o",
            "--model",
            "PP-OCRv6 small (PaddlePaddle)",
            "--settings",
            "published",
        )
    assert not (tmp_path / "o").exists()


def test_all_fonts_add_pillows_bitmap_font_and_every_pinned_font(monkeypatch):
    monkeypatch.setattr(
        command, "pinned_font", lambda font: fonts.PillowFont(font.name)
    )
    plan = command.injection_plan("all")
    names = [each.name for each in plan.fonts]
    assert names[:4] == [
        "bitmap-5x7",
        "bitmap-5x7-smooth",
        "pillow-bitmap",
        "pillow-bitmap-smooth",
    ]
    assert names[4:] == [each.name for each in font_files.PINNED_FONTS]
    assert command.injection_plan("bitmaps") == command.InjectionPlan()


def test_a_font_that_cannot_be_fetched_is_refused_with_the_way_round(
    tmp_path, monkeypatch, clinic, stand_in
):
    del stand_in

    def offline(font):
        raise OSError(f"no network for {font.name}")

    monkeypatch.setattr(command, "pinned_font", offline)
    root, _ = clinic
    with pytest.raises(SystemExit, match="--fonts bitmaps"):
        command.main([str(root), "--out", str(tmp_path / "o")])
    assert not (tmp_path / "o").exists()


def test_a_worker_process_redacts_pydicoms_records(monkeypatch):
    """A worker process, which the command's own redaction does not reach,
    redacts pydicom's log records once it makes its detector."""
    monkeypatch.setattr(multiprocessing, "parent_process", object)
    monkeypatch.setattr(command, "EvaluationDetector", lambda *args: "made")
    monkeypatch.setattr(command, "WORKER_REDACTION", [])
    try:
        assert command.process_detector(None, None) == "made"
        assert command.process_detector(None, None) == "made"
        assert len(command.WORKER_REDACTION) == 1
        record = logging.getLogger("pydicom").makeRecord(
            "pydicom", logging.WARNING, "", 0, "read %s", (PATIENT_A,), None
        )
        assert record.getMessage() == diagnostics.SUMMARY
    finally:
        for stack in command.WORKER_REDACTION:
            stack.close()
