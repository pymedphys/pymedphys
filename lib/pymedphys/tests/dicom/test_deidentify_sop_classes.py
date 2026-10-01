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

"""DICOM PS3.4 Table B.5-1, generated from the standard, and the IOD of each SOP Class."""

import dataclasses
import io
import json
import re

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import iods, sop_classes, standard, uid_registry

SPEC = sop_classes.STORAGE_SOP_CLASS_TABLE


def _loaded(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _redigested(document):
    """Record the digest of the rows as they now are, as a careful editor would."""
    document["content_sha256"] = standard.content_sha256(document["rows"])
    return document


def _write(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def _shipped():
    return _loaded(standard.STANDARD_DIR / SPEC.file)


def test_the_table_has_every_row_of_the_2026d_table():
    # Counts measured from the published 2026d PS3.4.
    rows = sop_classes.load_storage_sop_classes().rows

    assert len(rows) == 173
    assert len({row.iod for row in rows}) == 161
    assert sum(bool(row.specialization) for row in rows) == 57


def test_the_table_carries_its_edition_and_acknowledgement():
    table = sop_classes.load_storage_sop_classes()

    assert table.edition == "2026d"
    assert table.acknowledgement == "DICOM PS3.4 2026d, © NEMA"


@pytest.mark.parametrize(
    "row",
    [
        # Checked by hand against Table B.5-1 of the 2026d PS3.4.
        sop_classes.StorageSOPClass(
            name="CT Image Storage",
            uid="1.2.840.10008.5.1.4.1.1.2",
            iod="CT Image IOD",
            specialization="B.5.1.26",
        ),
        sop_classes.StorageSOPClass(
            name="CT Image Storage - For Processing",
            uid="1.2.840.10008.5.1.4.1.1.2.3",
            iod="CT Image IOD",
            specialization="B.5.1.26",
        ),
        sop_classes.StorageSOPClass(
            name="Enhanced CT Image Storage",
            uid="1.2.840.10008.5.1.4.1.1.2.1",
            iod="Enhanced CT Image IOD",
            specialization="B.5.1.7 B.5.1.23 B.5.1.26",
        ),
        sop_classes.StorageSOPClass(
            name="RT Plan Storage",
            uid="1.2.840.10008.5.1.4.1.1.481.5",
            iod="RT Plan IOD",
            specialization="",
        ),
        # The one name in the table without "Storage", as published; PS3.6
        # Table A-1 calls it "Macular Grid Thickness and Volume Report Storage".
        sop_classes.StorageSOPClass(
            name="Macular Grid Thickness and Volume Report",
            uid="1.2.840.10008.5.1.4.1.1.79.1",
            iod="Macular Grid Thickness and Volume Report IOD",
            specialization="B.5.1.5",
        ),
    ],
)
def test_table_rows(row):
    assert row in sop_classes.load_storage_sop_classes().rows


def test_the_iod_name_drops_the_trailing_iod():
    row = sop_classes.StorageSOPClass(
        name="RT Dose Storage",
        uid="1.2.840.10008.5.1.4.1.1.481.2",
        iod="RT Dose IOD",
        specialization="",
    )

    assert row.iod_name == "RT Dose"


def test_every_storage_sop_class_is_a_current_sop_class_in_ps3_6():
    registered = {
        uid.uid: uid
        for uid in uid_registry.load_uid_values().rows
        if uid.uid_type == "SOP Class"
    }

    for row in sop_classes.load_storage_sop_classes().rows:
        assert row.uid in registered, row.name
        assert not registered[row.uid].retired, row.name


def test_the_generated_iods_without_a_storage_sop_class_are_known():
    # Other parts of PS3.4 define the SOP Classes of these IODs, so no SOP
    # Class of Table B.5-1 finds them.
    named = {row.iod_name for row in sop_classes.load_storage_sop_classes().rows}

    assert set(iods.load_iod_tables().iods) - named == {
        "CT Defined Procedure Protocol",
        "Color Palette",
        "Generic Implant Template",
        "Hanging Protocol",
        "Implant Assembly Template",
        "Implant Template Group",
        "Inventory",
        "Protocol Approval",
        "Rendition Selection Document",
        "XA Defined Procedure Protocol",
    }


@pytest.mark.pydicom
def test_the_first_supported_release_sop_classes_find_their_iods():
    # pydicom's UID dictionary is an independent transcription of PS3.6.
    from pydicom import uid

    expected = {
        uid.CTImageStorage: "CT Image",
        # Added to the standard after pydicom's bundled edition; from Table
        # B.5-1 of the 2026d PS3.4.
        "1.2.840.10008.5.1.4.1.1.2.3": "CT Image",
        uid.RTDoseStorage: "RT Dose",
        uid.RTStructureSetStorage: "RT Structure Set",
        uid.RTPlanStorage: "RT Plan",
    }

    found = {
        sop_class: sop_classes.iod_for_sop_class(sop_class) for sop_class in expected
    }

    assert {sop_class: iod.name for sop_class, iod in found.items()} == expected
    tables = iods.load_iod_tables()
    for iod in found.values():
        assert iod is tables.iods[iod.name]


@pytest.mark.pydicom
def test_the_sop_classes_of_later_releases_find_their_iods():
    from pydicom import uid

    expected = {
        uid.MRImageStorage: "MR Image",
        uid.PositronEmissionTomographyImageStorage: "Positron Emission Tomography Image",
        uid.RTImageStorage: "RT Image",
        uid.RTBeamsTreatmentRecordStorage: "RT Beams Treatment Record",
        uid.RTIonPlanStorage: "RT Ion Plan",
        uid.SpatialRegistrationStorage: "Spatial Registration",
        # IODs whose modules include Functional Group Macros.
        uid.EnhancedCTImageStorage: "Enhanced CT Image",
        uid.EnhancedMRImageStorage: "Enhanced MR Image",
        uid.SegmentationStorage: "Segmentation",
        uid.EnhancedPETImageStorage: "Enhanced PET Image",
    }

    found = {
        sop_class: sop_classes.iod_for_sop_class(sop_class) for sop_class in expected
    }

    assert {
        sop_class: iod.name if iod else None for sop_class, iod in found.items()
    } == expected


@pytest.mark.parametrize(
    "sop_class",
    [
        # SOP Classes that Table B.5-1 does not list: the retired Nuclear
        # Medicine Image Storage, Hanging Protocol Storage, which another
        # service class defines, Verification, which stores nothing, and Video
        # Endoscopic Image Real-Time Communication, whose IOD the pin leaves
        # out.
        "1.2.840.10008.5.1.4.1.1.5",
        "1.2.840.10008.5.1.4.38.1",
        "1.2.840.10008.1.1",
        "1.2.840.10008.10.1",
    ],
)
def test_an_unlisted_sop_class_has_no_iod(sop_class):
    assert sop_classes.iod_for_sop_class(sop_class) is None


def test_every_storage_sop_class_finds_its_iod():
    # Every IOD of Table B.5-1 has generated Types in 2026d, including those
    # whose modules include Functional Group Macros.
    tables = iods.load_iod_tables()

    for row in sop_classes.load_storage_sop_classes().rows:
        assert sop_classes.iod_for_sop_class(row.uid) is tables.iods[row.iod_name]


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_sop_class_uid_read_from_a_file_finds_its_iod():
    # An end-to-end check. pydicom removes the padding when it decodes the
    # value, so test_trailing_padding_is_ignored is what shows that the lookup
    # removes it too.
    rt_plan_storage = "1.2.840.10008.5.1.4.1.1.481.5"
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = rt_plan_storage
    dataset.SOPInstanceUID = "1.2.3.4"  # invented
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    written = io.BytesIO()
    pydicom.dcmwrite(written, dataset, enforce_file_format=True)
    read = pydicom.dcmread(io.BytesIO(written.getvalue()))

    # PS3.5 Section 9.1 pads the odd-length UID with a NUL.
    assert read.get_item(0x00080016).value == rt_plan_storage.encode() + b"\x00"
    found = sop_classes.iod_for_sop_class(read.SOPClassUID)

    assert found is not None
    assert found.name == "RT Plan"


@pytest.mark.parametrize(
    "padding",
    # PS3.5 Section 9.1 pads an odd-length UID with a NUL; some writers pad
    # with a space instead.
    ["\x00", " ", " \x00"],
)
def test_trailing_padding_is_ignored(padding):
    found = sop_classes.iod_for_sop_class("1.2.840.10008.5.1.4.1.1.481.5" + padding)

    assert found is not None
    assert found.name == "RT Plan"


@pytest.mark.parametrize(
    "value",
    [
        # A Private SOP Class under an invented root.
        "1.2.3.4.5",
        # Only trailing padding is removed.
        " 1.2.840.10008.5.1.4.1.1.481.5",
        "1.2.840.10008.5.1.4.1.1.481.5\x00.1",
        "",
    ],
)
def test_a_uid_the_table_does_not_list_has_no_iod(value):
    assert sop_classes.iod_for_sop_class(value) is None


def test_tables_from_different_editions_are_rejected():
    later = dataclasses.replace(sop_classes.load_storage_sop_classes(), edition="2099a")

    with pytest.raises(standard.StandardTableError, match="different editions"):
        sop_classes.iod_for_sop_class(
            "1.2.840.10008.5.1.4.1.1.481.5", sop_classes=later
        )


def test_the_tables_can_be_given(tmp_path):
    document = _shipped()
    plan = next(row for row in document["rows"] if row["name"] == "RT Plan Storage")
    plan["iod"] = "RT Dose IOD"
    table = sop_classes.load_storage_sop_classes(
        _write(tmp_path / SPEC.file, _redigested(document))
    )

    found = sop_classes.iod_for_sop_class(
        "1.2.840.10008.5.1.4.1.1.481.5",
        sop_classes=table,
        iod_tables=iods.load_iod_tables(),
    )

    assert found is not None
    assert found.name == "RT Dose"


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("uid", "1.02", "row 1 has a UID"),
        ("uid", "1." + "2" * 63, "row 1 has a UID"),
        ("name", "", "row 1 has a name"),
        ("name", None, "row 1 has a name"),
        ("iod", "Computed Radiography Image", "row 1 has an IOD"),
        ("iod", "IOD", "row 1 has an IOD"),
        ("iod", 1, "row 1 has an IOD"),
        ("specialization", "5.1.1", "row 1 has a specialization"),
        ("specialization", "B.5.1.1,B.5.1.2", "row 1 has a specialization"),
        ("specialization", "B.5.1.1 ", "row 1 has a specialization"),
        ("specialization", None, "row 1 has a specialization"),
    ],
)
def test_a_malformed_row_is_rejected(tmp_path, field, value, message):
    document = _shipped()
    document["rows"][0][field] = value

    with pytest.raises(standard.StandardTableError, match=re.escape(message)):
        sop_classes.load_storage_sop_classes(
            _write(tmp_path / SPEC.file, _redigested(document))
        )


def test_a_row_without_exactly_its_fields_is_rejected(tmp_path):
    document = _shipped()
    del document["rows"][0]["specialization"]

    with pytest.raises(standard.StandardTableError, match="exactly the fields"):
        sop_classes.load_storage_sop_classes(
            _write(tmp_path / SPEC.file, _redigested(document))
        )


@pytest.mark.parametrize("field", ["uid", "name"])
def test_a_repeated_uid_or_name_is_rejected(tmp_path, field):
    document = _shipped()
    rows = document["rows"]
    rows[1][field] = rows[0][field]

    with pytest.raises(standard.StandardTableError, match=f"row 2 repeats the {field}"):
        sop_classes.load_storage_sop_classes(
            _write(tmp_path / SPEC.file, _redigested(document))
        )


def test_an_altered_row_is_rejected(tmp_path):
    document = _shipped()
    document["rows"][0]["iod"] = "RT Plan IOD"

    with pytest.raises(standard.StandardTableError, match="recorded digest"):
        sop_classes.load_storage_sop_classes(_write(tmp_path / SPEC.file, document))


def test_another_part_is_rejected(tmp_path):
    document = _shipped()
    document["acknowledgement"] = "DICOM PS3.3 2026d, © NEMA"

    with pytest.raises(standard.StandardTableError, match="acknowledgement"):
        sop_classes.load_storage_sop_classes(_write(tmp_path / SPEC.file, document))
