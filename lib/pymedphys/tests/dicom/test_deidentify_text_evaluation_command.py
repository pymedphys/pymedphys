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

"""The evaluation's command on IDC, with invented rows of IDC's index, a
synthetic series, and a stand-in network."""

import argparse
import functools
import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_command as command
from pymedphys._dicom.deidentify import text_evaluation_criteria as criteria
from pymedphys._dicom.deidentify import text_evaluation_detector as detector
from pymedphys._dicom.deidentify import text_evaluation_idc as idc
from pymedphys._dicom.deidentify import text_evaluation_phantoms as phantoms
from pymedphys._dicom.deidentify import text_evaluation_search as search

from . import _classic_images as classic
from .test_deidentify_text_evaluation_idc import UUID, _row, _series_folder
from .test_deidentify_text_evaluation_phantom_report import _phantom_file


def bright(tensor):
    """A stand-in network whose map is the input's first channel, as a
    share."""
    return [np.clip(tensor[0, :1] * 0.5 + 0.5, 0, 1)[np.newaxis]]


@pytest.fixture(name="stand_in")
def _stand_in(monkeypatch):
    monkeypatch.setattr(
        command,
        "EvaluationDetector",
        functools.partial(
            detector.EvaluationDetector, network=bright, network_name="bright"
        ),
    )


def _select(tmp_path, monkeypatch, rows):
    monkeypatch.setattr(command, "index_rows", lambda wheel: rows)
    out = tmp_path / "selected"
    assert command.main(["idc-select", "unused.whl", "--out", str(out)]) == 0
    return out


def test_a_selection_is_written_with_its_manifest(tmp_path, monkeypatch):
    out = _select(tmp_path, monkeypatch, [_row(1), _row(2), _row(3, Modality="SEG")])
    selection = json.loads((out / "selection.json").read_text())
    assert selection["refused"] == {"not-an-image-modality": 1}
    series = json.loads((out / "series.json").read_text())
    assert len(series) == 2
    lines = (out / "manifest.s5cmd").read_text().splitlines()
    assert lines[0].startswith("cp 's3://idc-open-data/")
    assert lines[0].endswith("' 'downloads/" + series[0]["crdc_series_uuid"] + "/'")
    with pytest.raises(SystemExit, match="must not exist"):
        command.main(["idc-select", "unused.whl", "--out", str(out)])


def test_downloaded_series_are_measured(tmp_path, monkeypatch, stand_in):
    del stand_in
    selected = _select(tmp_path, monkeypatch, [_row(1)])
    downloads = tmp_path / "downloads"
    _series_folder(downloads, 1)
    out = tmp_path / "measured"
    code = command.main(
        [
            "idc-measure",
            str(selected / "series.json"),
            str(downloads),
            "--evaluated",
            "all",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert sorted(each.name for each in out.iterdir()) == [
        "assessment.json",
        "cases.json",
        "summary.json",
        "summary.md",
    ]
    cases = json.loads((out / "cases.json").read_text())
    (case,) = cases["cases"]
    assert case["series_instance_uid"] == "2.25.1"
    assert case["frames"] == {"CT Image Storage": 2}
    summary = json.loads((out / "summary.json").read_text())
    assert summary["frames"] == {"CT Image Storage": 2}
    assert "2.25.1" not in (out / "summary.json").read_text()
    (assessed,) = json.loads((out / "assessment.json").read_text())
    assert not assessed["meets"]
    # Today's detector is its own baseline for the rule of no loss.
    assert criteria.NOT_TODAYS not in assessed["failures"]


def test_published_settings_are_measured_with_their_own_point(
    tmp_path, monkeypatch, stand_in
):
    del stand_in
    pytest.importorskip("cv2")
    selected = _select(tmp_path, monkeypatch, [_row(1)])
    downloads = tmp_path / "downloads"
    _series_folder(downloads, 1)
    out = tmp_path / "published"
    command.main(
        [
            "idc-measure",
            str(selected / "series.json"),
            str(downloads),
            "--model",
            "PP-OCRv6 small (PaddlePaddle)",
            "--settings",
            "published",
            "--evaluated",
            "all",
            "--out",
            str(out),
        ]
    )
    summary = json.loads((out / "summary.json").read_text())
    (point,) = summary["points"]
    assert point["post_processing"]["threshold"] == 0.2
    assert summary["detector"]["variant"]["network_input"]["resampler"] == "cv2"


def test_a_tuning_run_measures_a_named_variant_and_grid(
    tmp_path, monkeypatch, stand_in
):
    del stand_in
    selected = _select(tmp_path, monkeypatch, [_row(1)])
    downloads = tmp_path / "downloads"
    _series_folder(downloads, 1)
    out = tmp_path / "searched"
    command.main(
        [
            "idc-measure",
            str(selected / "series.json"),
            str(downloads),
            "--variant",
            "noise over tissue",
            "--grid",
            "single settings",
            "--evaluated",
            "all",
            "--out",
            str(out),
        ]
    )
    summary = json.loads((out / "summary.json").read_text())
    grid = search.GRIDS["single settings"]
    assert [point["post_processing"] for point in summary["points"]] == [
        point.described() for point in grid
    ]
    assert summary["detector"]["variant"]["name"] == "noise over tissue"
    assert summary["detector"]["variant"]["rendering"]["noise"] == "tissue"
    assessment = json.loads((out / "assessment.json").read_text())
    assert [each["index"] for each in assessment] == list(range(len(grid)))
    # A variant's first point is not today's detector, so no point of it can
    # show that it loses nothing against today's.
    for each in assessment:
        assert criteria.NOT_TODAYS in each["failures"] and not each["meets"]
    # The page marks each point against the criteria, as the assessment does.
    assert "Meets" in (out / "summary.md").read_text()


def test_only_todays_model_at_todays_settings_and_variant_is_todays_detector():
    def named(**changes):
        arguments = {"model": "PP-OCRv6 small", "settings": "today", **changes}
        return command.todays_detector(argparse.Namespace(**arguments))

    assert named() and named(variant="today")
    assert not named(variant="noise over tissue")
    assert not named(settings="published")
    assert not named(model="PP-OCRv6 small (PaddlePaddle)")


def test_a_variant_or_grid_is_refused_with_published_settings(tmp_path):
    for option, name in (
        ("--variant", "top-hats of 8 mm"),
        ("--grid", "single settings"),
    ):
        with pytest.raises(SystemExit, match="today's settings alone"):
            command.main(
                [
                    "idc-measure",
                    str(tmp_path / "series.json"),
                    str(tmp_path),
                    "--settings",
                    "published",
                    option,
                    name,
                    "--out",
                    str(tmp_path / "o"),
                ]
            )


def test_an_unknown_variant_or_grid_is_refused(tmp_path):
    for option in ("--variant", "--grid"):
        with pytest.raises(SystemExit):
            command.main(
                [
                    "idc-measure",
                    "series.json",
                    str(tmp_path),
                    option,
                    "invented",
                    "--out",
                    str(tmp_path / "o"),
                ]
            )


def test_a_series_file_not_of_the_selection_is_refused(tmp_path):
    path = tmp_path / "series.json"
    path.write_text(json.dumps([{"collection_id": "clinic"}]))
    with pytest.raises(SystemExit, match="not idc-select's"):
        command.main(
            ["idc-measure", str(path), str(tmp_path), "--out", str(tmp_path / "o")]
        )
    record = {
        "collection_id": "lidc_idri",
        "series_instance_uid": "2.25.1",
        "crdc_series_uuid": UUID.format(1),
        "modality": "CT",
        "sop_class_uid": "1.2.840.10008.5.1.4.1.1.2",
        "licence": "CC BY 3.0",
        "doi": "10.7937/K9/TCIA.2015.LO9QL9SX",
        "size_mb": 1.0,
        "aws_url": f"s3://idc-open-data/{UUID.format(1)}/*",
        "subject": idc.subject_key("lidc_idri", "INVENTED-1"),
    }
    assert command.read_series(_written(tmp_path, [record])) == (
        idc.IdcSeries(**record),
    )
    with pytest.raises(Exception, match="not idc-select's"):
        command.read_series(_written(tmp_path, [record, record]))
    # A series without its subject's key is not idc-select's.
    unkeyed = {key: value for key, value in record.items() if key != "subject"}
    with pytest.raises(Exception, match="not idc-select's"):
        command.read_series(_written(tmp_path, [unkeyed]))


def _written(tmp_path, records):
    path = tmp_path / "records.json"
    path.write_text(json.dumps(records))
    return path


def test_every_adapter_can_be_chosen():
    assert "PP-OCRv6 small" in command.MODELS
    assert len(command.MODELS) == 10


# -- Phantoms ---------------------------------------------------------------


def _small_phantoms():
    return (phantoms.PhantomCase(phantoms.Phantom("ct-thorax", 96, 4.0), seed=1),)


def _phantom_downloads(tmp_path, number=1):
    folder = tmp_path / "downloads" / UUID.format(number)
    folder.mkdir(parents=True)
    for instance in (1, 2):
        (folder / f"{instance}.dcm").write_bytes(_phantom_file(number=instance))
    # A file of a patient collection, in the phantom's folder, is skipped
    # unread by the project gate.
    (folder / "other.dcm").write_bytes(
        _phantom_file(project="NSCLC-Radiomics", series="2.25.50")
    )
    return tmp_path / "downloads"


def _phantom_report(tmp_path, series, downloads, evaluated="all"):
    out = tmp_path / f"reported-{evaluated}"
    code = command.main(
        [
            "phantom-report",
            str(series),
            str(downloads),
            "--evaluated",
            evaluated,
            "--out",
            str(out),
        ]
    )
    assert code == 0
    return out


def test_phantoms_are_selected_apart_and_reported_in_full(
    tmp_path, monkeypatch, stand_in
):
    del stand_in
    monkeypatch.setattr(command, "phantom_cases", _small_phantoms)
    rows = [_row(1, collection_id="cc_radiomics_phantom_3"), _row(2)]
    monkeypatch.setattr(command, "index_rows", lambda wheel: rows)
    selected = tmp_path / "selected"
    command.main(["idc-select", "unused.whl", "--phantoms", "--out", str(selected)])
    (series,) = json.loads((selected / "series.json").read_text())
    assert series["collection_id"] == "cc_radiomics_phantom_3"
    out = _phantom_report(
        tmp_path, selected / "series.json", _phantom_downloads(tmp_path)
    )
    index = json.loads((out / "phantoms" / "index.json").read_text())
    # Each frame is reported as read and, where text was burned in, with
    # it; the patient collection's file forms a case of its own, of none.
    assert sorted(
        (each["collection"], each["frames"] > 0) for each in index["cases"]
    ) == [
        ("CC-Radiomics-Phantom-3", False),
        ("CC-Radiomics-Phantom-3", True),
        ("synthetic", True),
    ]
    assert index["skipped"] == {"not-phantom/other-project": 1}
    for entry in index["cases"]:
        assert (out / "phantoms" / entry["report"]).is_file()
    assert (
        "10.7937/tcia.2019.j71i4fah"
        in (out / "phantoms" / "ATTRIBUTION.md").read_text()
    )
    summary = json.loads((out / "summary.json").read_text())
    assert sum(summary["split"]["cases"].values()) == 3
    assert summary["frames"]["CT Image Storage"] == 3


def test_a_patient_selection_is_never_reported_in_full(tmp_path, monkeypatch):
    selected = _select(tmp_path, monkeypatch, [_row(1)])
    downloads = tmp_path / "downloads"
    _series_folder(downloads, 1)
    with pytest.raises(SystemExit, match="Only a selection of phantoms"):
        command.main(
            [
                "phantom-report",
                str(selected / "series.json"),
                str(downloads),
                "--out",
                str(tmp_path / "out"),
            ]
        )
    assert not (tmp_path / "out").exists()


def test_phantoms_held_out_are_not_previewed_while_tuning(
    tmp_path, monkeypatch, stand_in
):
    del stand_in
    cases = tuple(
        phantoms.PhantomCase(phantoms.Phantom("ct-thorax", 48, 4.0), seed=seed)
        for seed in range(12)
    )
    monkeypatch.setattr(command, "phantom_cases", lambda: cases)
    series = tmp_path / "series.json"
    series.write_text("[]")
    out = _phantom_report(tmp_path, series, tmp_path, evaluated="tuning")
    tuning = [
        each
        for each in cases
        if evaluation.split_of(each.collection, evaluation.subject_of(each)) == "tuning"
    ]
    # Both parts occur among twelve seeds, so the filter is exercised.
    assert 0 < len(tuning) < len(cases)
    index = json.loads((out / "phantoms" / "index.json").read_text())
    assert sorted(each["case"] for each in index["cases"]) == sorted(
        each.case for each in tuning
    )
    # The summary still counts every case, by its part.
    summary = json.loads((out / "summary.json").read_text())
    assert summary["split"]["cases"] == {
        "tuning": len(tuning),
        "held-out": len(cases) - len(tuning),
    }
    assert sorted(out.iterdir()) == [
        out / "phantoms",
        out / "summary.json",
        out / "summary.md",
    ]


def _measured(tmp_path, selected, downloads, name, *options):
    out = tmp_path / name
    arguments = [str(selected / "series.json"), str(downloads), "--evaluated", "all"]
    command.main(["idc-measure", *arguments, *options, "--out", str(out)])
    return out


@pytest.mark.parametrize("converted", [False, True])
def test_a_run_measured_in_shards_merges_to_the_run_measured_whole(
    tmp_path, monkeypatch, stand_in, converted
):
    del stand_in
    rows = [_row(number) for number in range(1, 6)]
    # Two series of one patient, which the bootstrap resamples as one.
    rows[2]["PatientID"] = rows[0]["PatientID"]
    monkeypatch.setattr(command, "index_rows", lambda wheel: rows)
    selected = tmp_path / "selected"
    command.main(
        ["idc-select", "unused.whl", "--per-collection", "9", "--out", str(selected)]
    )
    downloads = tmp_path / "downloads"
    for number in range(1, 6):
        # Classic CT images that convert, three slices of each series but the
        # fourth, which has nine.
        folder = downloads / UUID.format(number)
        folder.mkdir(parents=True)
        slices = 9 if number == 4 else 3
        series = classic.classic_series("CT", slices, series=number)
        for index, dataset in enumerate(series):
            dataset.SeriesInstanceUID = f"2.25.{number}"
            (folder / f"{index}.dcm").write_bytes(classic.encoded(dataset))
    extra = ["--converted"] if converted else []
    whole = _measured(tmp_path, selected, downloads, "whole", *extra)
    records = [
        _measured(
            tmp_path, selected, downloads, f"shard-{k}", *extra, "--shard", f"{k}/3"
        )
        / "shard.json"
        for k in range(3)
    ]
    subjects = [
        each["subject"] for each in json.loads((selected / "series.json").read_text())
    ]
    held = []
    for record in records:
        assert sorted(each.name for each in record.parent.iterdir()) == ["shard.json"]
        text = record.read_text()
        assert not any(name in text for name in ("INVENTED", *subjects))
        found = json.loads(text)
        held.append(len(found["named"]) + found["withheld"])
    # Four subjects in three shards, by their frames: the fourth series'
    # subject, of nine frames, fills the first shard; the patient's two
    # series, of six, stay together in the second; and the two subjects of
    # three frames each go to the third. Counted by cases alone, the two
    # series would fill the first shard instead.
    assert len(set(subjects)) == 4
    assert held == [1, 2, 2]
    out = tmp_path / "merged"
    assert command.main(["idc-merge", *map(str, records), "--out", str(out)]) == 0
    names = sorted(each.name for each in whole.iterdir())
    assert sorted(each.name for each in out.iterdir()) == names
    for name in names:
        assert (out / name).read_text() == (whole / name).read_text()
    summary = json.loads((out / "summary.json").read_text())
    assert sum(summary["frames"].values()) == 21
    assert not summary["skipped"]


def test_a_merge_refuses_records_not_of_idc_measure(tmp_path):
    path = tmp_path / "shard.json"
    for content in ("not JSON", "[]", json.dumps({"run": {"model": "other"}})):
        path.write_text(content)
        with pytest.raises(SystemExit, match="shard's record"):
            command.main(["idc-merge", str(path), "--out", str(tmp_path / "o")])


@pytest.mark.parametrize("shard", ["1/1", "-1/2", "a/2", "1", "0/0"])
def test_a_shard_must_be_k_of_n(tmp_path, shard):
    with pytest.raises(SystemExit):
        command.main(
            [
                "idc-measure",
                "s.json",
                "d",
                "--shard",
                shard,
                "--out",
                str(tmp_path / "o"),
            ]
        )
