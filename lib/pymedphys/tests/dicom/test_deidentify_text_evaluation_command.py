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

import functools
import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_command as command
from pymedphys._dicom.deidentify import text_evaluation_detector as detector
from pymedphys._dicom.deidentify import text_evaluation_idc as idc
from pymedphys._dicom.deidentify import text_evaluation_phantoms as phantoms

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
    counted = json.loads((out / "phantoms.json").read_text())
    assert counted["cases"] == 3
    assert counted["not_in_the_part_evaluated"] == 0
    assert counted["skipped"] == {"not-phantom/other-project": 1}
    summary = json.loads((out / "summary.json").read_text())
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
    counted = json.loads((out / "phantoms.json").read_text())
    assert counted["not_in_the_part_evaluated"] == len(cases) - len(tuning)
