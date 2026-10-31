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

"""Counts-only inventories of collections of DICOM files.

Every file here is synthetic, and every value invented."""

import io
import json
import zipfile

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import text_evaluation_inventory as inventory

from . import _synthetic_references as synthetic

SECRETS = (
    "SECRET^PATIENT^4711",
    "2.25.4711",
    "ACME SECRET IMAGING",
    "SECRETTERM",
)


def _image(**attributes):
    dataset = synthetic.ct_slice(0)
    dataset.Modality = "CT"
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows, dataset.Columns = 8, 12
    dataset.BitsAllocated, dataset.BitsStored, dataset.HighBit = 16, 12, 11
    dataset.PixelRepresentation = 0
    dataset.PixelSpacing = [0.6, 0.6]
    dataset.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
    dataset.Manufacturer = "GE MEDICAL SYSTEMS"
    dataset.BurnedInAnnotation = "NO"
    for keyword, value in attributes.items():
        setattr(dataset, keyword, value)
    frames = int(getattr(dataset, "NumberOfFrames", 1))
    dataset.PixelData = np.zeros(
        (frames, dataset.Rows, dataset.Columns), "<u2"
    ).tobytes()
    return synthetic.written(dataset)


def _collection(tmp_path):
    root = tmp_path / "SECRET^PATIENT^4711 export"
    (root / "nested").mkdir(parents=True)
    (root / "ct.dcm").write_bytes(_image())
    (root / "nested" / "localiser.dcm").write_bytes(
        _image(ImageType=["ORIGINAL", "PRIMARY", "LOCALIZER"], Rows=512, Columns=512)
    )
    rt_image = pydicom.dcmread(
        io.BytesIO(
            _image(
                Modality="RTIMAGE",
                Manufacturer="Varian Medical Systems",
                ImageType=["ORIGINAL", "PRIMARY", "PORTAL"],
                ImagePlanePixelSpacing=[0.392, 0.392],
                BurnedInAnnotation="YES",
                Rows=1024,
                Columns=768,
            )
        )
    )
    del rt_image.PixelSpacing
    rt_image.SOPClassUID = "1.2.840.10008.5.1.4.1.1.481.1"
    (root / "rt.dcm").write_bytes(synthetic.written(rt_image))
    (root / "odd.dcm").write_bytes(
        _image(
            Modality="ZZ",
            Manufacturer="ACME SECRET IMAGING",
            ImageType=["DERIVED", "SECONDARY", "SECRETTERM"],
            BurnedInAnnotation="MAYBE",
            PatientID="SECRET^PATIENT^4711",
            SeriesInstanceUID="2.25.4711",
            NumberOfFrames=3,
        )
    )
    (root / "notes.txt").write_text("SECRET^PATIENT^4711")
    return root


def test_files_are_counted_by_fixed_labels_alone(tmp_path):
    root = _collection(tmp_path)
    summary = inventory.inventory(inventory.folder_files(root, "c"))
    entry = summary["collections"]["c"]
    assert summary["format"] == inventory.INVENTORY_FORMAT
    assert (entry["files"], entry["read"]) == (5, 4)
    assert entry["skipped"] == {"not-dicom": 1}
    by = entry["by"]
    assert by["sop_class"] == {"CT Image Storage": 3, "RT Image Storage": 1}
    assert by["modality"] == {"CT": 2, "RTIMAGE": 1, "other": 1}
    assert by["manufacturer"] == {"GE": 2, "Varian": 1, "other": 1}
    assert by["image_type"]["LOCALIZER"] == 1
    assert by["image_type"]["PORTAL"] == 1
    assert by["image_type"]["other"] == 1
    assert by["burned_in_annotation"] == {"NO": 2, "YES": 1, "other": 1}
    assert by["recognizable_visual_features"] == {"absent": 4}
    assert by["photometric"] == {"MONOCHROME2": 4}
    assert by["bits_stored"] == {"12": 4}
    assert by["pixel_data"] == {"yes": 4}
    assert by["frames"] == {"1 to under 2 frames": 3, "3 to under 17 frames": 1}
    assert by["larger_side"]["1024 pixels or more"] == 1
    assert by["pixel_spacing"]["0 to under 0.5 mm"] == 1
    assert entry["frames_by_sop_class"] == {
        "CT Image Storage": 5,
        "RT Image Storage": 1,
    }
    assert (entry["patients"], entry["series"]) == (2, 2)
    localisers = [
        row
        for row in entry["crosses"]["sop_class+image_type"]
        if row["value"] == ["CT Image Storage", "LOCALIZER"]
    ]
    assert localisers == [{"value": ["CT Image Storage", "LOCALIZER"], "files": 1}]
    assert summary["overall"]["read"] == 4


def test_no_value_identifier_or_path_reaches_the_inventory(tmp_path):
    root = _collection(tmp_path)
    summary = inventory.inventory(inventory.folder_files(root, "c"))
    published = json.dumps(summary) + inventory.inventory_markdown(summary)
    for secret in SECRETS:
        assert secret not in published
    assert str(tmp_path) not in published
    assert "notes" not in published


def test_absent_and_malformed_values_are_counted_by_code(tmp_path):
    dataset = pydicom.dcmread(io.BytesIO(_image()))
    del dataset.Manufacturer
    del dataset.ImageType
    dataset.BurnedInAnnotation = ""
    data = synthetic.written(dataset)
    # Pixel Spacing that is not a decimal string, written past pydicom.
    assert data.count(b"0.6\\0.6") == 1
    path = tmp_path / "file.dcm"
    path.write_bytes(data.replace(b"0.6\\0.6", b"abc\\def"))
    by = inventory.inventory([inventory.InventoryFile("c", str(path))])["overall"]["by"]
    assert by["manufacturer"] == {"absent": 1}
    assert by["image_type"] == {"absent": 1}
    assert by["burned_in_annotation"] == {"absent": 1}
    assert by["pixel_spacing"] == {"malformed": 1}


def test_zip_files_are_read_without_extracting(tmp_path):
    archive = tmp_path / "collection.zip"
    with zipfile.ZipFile(archive, "w") as written:
        written.writestr("a/1.dcm", _image())
        written.writestr("a/2.dcm", _image(Modality="MR"))
        written.writestr("readme.txt", "text")
    files = inventory.zip_files(archive, "z")
    assert repr(files[0]) == "InventoryFile()"
    summary = inventory.inventory(files)
    entry = summary["collections"]["z"]
    assert (entry["files"], entry["read"]) == (3, 2)
    assert entry["by"]["modality"] == {"CT": 1, "MR": 1}
    assert entry["by"]["pixel_data"] == {"yes": 2}
    assert entry["skipped"] == {"not-dicom": 1}


def test_collections_are_counted_apart_and_together(tmp_path):
    first, second = tmp_path / "1.dcm", tmp_path / "2.dcm"
    first.write_bytes(_image())
    second.write_bytes(_image(Modality="MR"))
    summary = inventory.inventory(
        [
            inventory.InventoryFile("a", str(first)),
            inventory.InventoryFile("b", str(second)),
        ]
    )
    assert set(summary["collections"]) == {"a", "b"}
    assert summary["overall"]["by"]["modality"] == {"CT": 1, "MR": 1}


def test_a_file_whose_reading_raises_is_counted_by_where(tmp_path, monkeypatch):
    path = tmp_path / "1.dcm"
    path.write_bytes(_image())

    def raising(*_):
        raise ValueError("SECRET^PATIENT^4711")

    monkeypatch.setattr(inventory, "_labels", raising)
    summary = inventory.inventory([inventory.InventoryFile("c", str(path))])
    crashed = summary["overall"]["crashed"]
    assert sum(crashed.values()) == 1
    assert "SECRET" not in json.dumps(summary)


def test_unknown_crosses_are_refused():
    with pytest.raises(inventory.InventoryRefused):
        inventory.inventory([], crosses=(("sop_class", "colour"),))


def test_the_page_is_tables_of_counts(tmp_path):
    root = _collection(tmp_path)
    page = inventory.inventory_markdown(
        inventory.inventory(inventory.folder_files(root, "c"))
    )
    assert page.startswith("# DICOM inventory\n")
    for line in page.splitlines():
        assert line == line.rstrip()
        if line.startswith("|"):
            assert line.endswith("|")
