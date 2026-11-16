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

"""The check of the pixel options on IDC's public floating-point Parametric
Maps, on synthetic maps: its selection, its pins, its counts, and that it
writes nothing that names a file."""

import hashlib
import io
import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import parametric_map_check as check_module
from pymedphys._dicom.deidentify.parametric_map_check import (
    CheckRefused,
    MapSeries,
    check,
    files_sha256,
    main,
    manifest,
    markdown,
    select,
)
from pymedphys._dicom.deidentify.text_detection import TextBox

from .test_deidentify_parametric_map_scope import _float_parametric_map

UUIDS = (
    "0b8f3a52-1c2d-4e5f-8a9b-0c1d2e3f4a5b",
    "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
)


def _row(uuid=UUIDS[0], **changes):
    row = {
        "collection_id": "tcga_gbm",
        "analysis_result_id": "tcga_gbm360",
        "crdc_series_uuid": uuid,
        "SOPClassUID": "1.2.840.10008.5.1.4.1.1.30",
        "license_short_name": "CC-BY-4.0",
        "source_DOI": "10.5281/zenodo.17470190",
        "series_aws_url": f"s3://idc-open-data/{uuid}/*",
        "instanceCount": 1,
    }
    row.update(changes)
    return row


OTHER = _row(
    "c1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d", SOPClassUID="1.2.3", collection_id="x"
)


def test_the_index_s_parametric_maps_are_selected_in_order_of_their_identifiers():
    rows = [_row(UUIDS[1]), OTHER, _row(UUIDS[0])]

    selected = select(rows, series=2)

    assert selected == tuple(
        MapSeries(uuid, f"s3://idc-open-data/{uuid}/*") for uuid in UUIDS
    )
    assert manifest(selected, "data/maps/") == "".join(
        f"cp 's3://idc-open-data/{uuid}/*' 'data/maps/{uuid}/'\n" for uuid in UUIDS
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"analysis_result_id": "other"},
        {"collection_id": "other"},
        {"license_short_name": "CC BY-NC 4.0"},
        {"source_DOI": "10.5281/zenodo.1"},
        {"instanceCount": 2},
        {
            "series_aws_url": "s3://another-bucket/0b8f3a52-1c2d-4e5f-8a9b-0c1d2e3f4a5b/*"
        },
        {"series_aws_url": "s3://idc-open-data/a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d/*"},
        {"crdc_series_uuid": "not-a-uuid"},
    ],
    ids=[
        "analysis",
        "collection",
        "licence",
        "doi",
        "instances",
        "bucket",
        "folder",
        "identifier",
    ],
)
def test_a_parametric_map_unlike_the_pinned_ones_refuses_the_selection(changes):
    with pytest.raises(CheckRefused):
        select([_row(**changes)], series=1)


@pytest.mark.parametrize(
    "rows", [[_row()], [_row(), _row(), _row(UUIDS[1])]], ids=["fewer", "twice"]
)
def test_a_selection_of_another_number_of_maps_is_refused(rows):
    with pytest.raises(CheckRefused):
        select(rows, series=2)


def test_a_destination_that_is_not_a_plain_path_is_refused():
    with pytest.raises(CheckRefused):
        manifest(select([_row()], series=1), "data'; rm -rf /")


class Finder:
    """Finds a box in each frame with a value other than 0."""

    method = {"model": "stub"}

    def find(self, frame):
        return (TextBox(0, 0, 1, 2),) if np.any(frame) else ()


def _maps(folder, count=3):
    """``count`` synthetic floating-point Parametric Maps, each in a folder
    of its own, as the manifest places them; their files' digest."""
    paths = []
    for index in range(count):
        dataset = pydicom.dcmread(io.BytesIO(_float_parametric_map(index % 2 == 1)))
        dataset.SOPInstanceUID = f"1.2.826.0.1.3680043.10.1427.{index + 1}"
        if index == 2:
            # The third map's values are all 0, so the finder finds no text.
            dataset.FloatPixelData = bytes(len(dataset.FloatPixelData))
        stream = io.BytesIO()
        pydicom.dcmwrite(stream, dataset, enforce_file_format=True)
        path = folder / f"series-{index}" / "instance.dcm"
        path.parent.mkdir(parents=True)
        path.write_bytes(stream.getvalue())
        paths.append(path)
    return paths, files_sha256(sorted(paths))[0]


@pytest.mark.pydicom
def test_each_map_is_cleaned_previewed_and_released_and_counted(tmp_path):
    paths, digest = _maps(tmp_path / "maps")

    summary = check(
        tmp_path / "maps",
        Finder(),
        series=3,
        sha256=digest,
    )

    assert summary["format"] == "pymedphys-deid-parametric-map-check/1"
    assert summary["data"]["files"] == 3
    assert summary["data"]["bytes"] == sum(path.stat().st_size for path in paths)
    assert summary["pixel_data_elements"] == {
        "DoubleFloatPixelData": 1,
        "FloatPixelData": 2,
    }
    cleaned = summary["clean_pixel_data"]
    assert cleaned["outcome: text-blacked-out"] == 2
    assert cleaned["outcome: no-text-found"] == 1
    assert cleaned["written in the element that held it, same data type and shape"] == 3
    assert cleaned["pixels changed"] == 2 and cleaned["pixels unchanged"] == 1
    # A box in each of a map's two frames.
    assert cleaned["regions_per_file"]["0"] == 1
    assert cleaned["regions_per_file"]["2"] == 2
    reviewed = summary["clean_recognizable_visual_features"]
    assert reviewed["held without a verdict"] == 3
    assert reviewed["previewed"] == reviewed["shown whole"] == 3
    released = "released on a face verdict of absent, Recognizable Visual Features NO"
    assert reviewed[released] == 3
    assert reviewed["not_previewed"] == {}
    assert not summary["crashed"]
    assert summary["finder"] == {"model": "stub"}


@pytest.mark.pydicom
def test_files_other_than_the_pinned_ones_are_refused(tmp_path):
    _, digest = _maps(tmp_path / "maps", count=2)

    with pytest.raises(CheckRefused, match="pinned number"):
        check(tmp_path / "maps", Finder(), series=3, sha256=digest)
    with pytest.raises(CheckRefused, match="not the pinned ones"):
        check(tmp_path / "maps", Finder(), series=2, sha256="0" * 64)


def test_the_files_digest_is_of_their_sorted_digests(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    digests = sorted(hashlib.sha256(data).hexdigest() for data in (b"one", b"two"))

    assert files_sha256([second, first]) == (
        hashlib.sha256("".join(f"{each}\n" for each in digests).encode()).hexdigest(),
        6,
    )


@pytest.mark.pydicom
def test_the_command_writes_counts_that_name_no_file(tmp_path, monkeypatch, capsys):
    paths, digest = _maps(tmp_path / "maps")
    monkeypatch.setattr(check_module, "SERIES", 3)
    monkeypatch.setattr(check_module, "FILES_SHA256", digest)
    monkeypatch.setattr(check_module, "check", _pinned(check_module.check, digest))
    monkeypatch.setattr(check_module, "_detector", Finder)

    assert main(["check", str(tmp_path / "maps"), "--out", str(tmp_path / "out")]) == 0

    page = (tmp_path / "out" / "parametric-map-check.md").read_text(encoding="utf-8")
    text = (tmp_path / "out" / "parametric-map-check.json").read_text(encoding="utf-8")
    assert capsys.readouterr().out == page
    assert json.loads(text)["data"]["files"] == 3
    assert page == markdown(json.loads(text))
    for path in paths:
        dataset = pydicom.dcmread(path)
        for value in (
            dataset.SOPInstanceUID,
            dataset.StudyInstanceUID,
            dataset.SeriesInstanceUID,
            str(path),
            path.parent.name,
        ):
            assert value not in page and value not in text


def _pinned(function, digest):
    def pinned(folder, finder, **kwargs):
        return function(folder, finder, series=3, sha256=digest, **kwargs)

    return pinned


def test_the_command_refuses_an_existing_output(tmp_path):
    with pytest.raises(SystemExit, match="must not exist"):
        main(["check", str(tmp_path), "--out", str(tmp_path)])
