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

"""Which instances the first supported release de-identifies, and which it sequesters."""

import dataclasses

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import iods, scope, sop_classes, uid_registry

Disposition = scope.Disposition

IMPLICIT_LE = "1.2.840.10008.1.2"
EXPLICIT_LE = "1.2.840.10008.1.2.1"

# The Storage SOP Classes of the first release's IODs, from Table B.5-1 of the
# 2026d PS3.4.
SUPPORTED = {
    "1.2.840.10008.5.1.4.1.1.2": "CT Image",  # CT Image Storage
    "1.2.840.10008.5.1.4.1.1.2.3": "CT Image",  # CT Image Storage - For Processing
    "1.2.840.10008.5.1.4.1.1.481.2": "RT Dose",
    "1.2.840.10008.5.1.4.1.1.481.3": "RT Structure Set",
    "1.2.840.10008.5.1.4.1.1.481.5": "RT Plan",
}


def test_the_first_release_supports_uncompressed_ct_and_rt_objects():
    assert scope.SUPPORTED_IODS == {
        "CT Image",
        "RT Dose",
        "RT Plan",
        "RT Structure Set",
    }
    assert scope.SUPPORTED_TRANSFER_SYNTAXES == {IMPLICIT_LE, EXPLICIT_LE}


def test_every_supported_iod_has_generated_types():
    assert scope.SUPPORTED_IODS <= set(iods.load_iod_tables().iods)


def test_the_supported_transfer_syntaxes_are_current_in_ps3_6():
    registered = {
        uid.uid: uid
        for uid in uid_registry.load_uid_values().rows
        if uid.uid_type == "Transfer Syntax"
    }

    assert registered[IMPLICIT_LE].name.startswith("Implicit VR Little Endian")
    assert registered[EXPLICIT_LE].name == "Explicit VR Little Endian"
    assert not any(registered[uid].retired for uid in scope.SUPPORTED_TRANSFER_SYNTAXES)


def test_only_the_storage_sop_classes_of_the_supported_iods_are_supported():
    # A new edition that maps another SOP Class to a supported IOD fails
    # here once its tables are regenerated.
    supported = {
        row.uid
        for row in sop_classes.load_storage_sop_classes().rows
        if scope.classify(row.uid, EXPLICIT_LE).disposition is Disposition.SUPPORTED
    }

    assert supported == set(SUPPORTED)


@pytest.mark.parametrize("sop_class, iod", SUPPORTED.items())
@pytest.mark.parametrize("transfer_syntax", [IMPLICIT_LE, EXPLICIT_LE])
def test_a_supported_instance_is_de_identified(sop_class, iod, transfer_syntax):
    found = scope.classify(sop_class, transfer_syntax)

    assert found == scope.Classification(Disposition.SUPPORTED, iod)
    assert not found.sequestered


def test_padding_is_ignored():
    # PS3.5 Section 9.1 pads an odd-length UID with a NUL; some writers pad
    # with a space.
    found = scope.classify("1.2.840.10008.5.1.4.1.1.481.5\x00", EXPLICIT_LE + "\x00")

    assert found.disposition is Disposition.SUPPORTED
    assert scope.classify("1.2.840.10008.5.1.4.1.1.2 ", IMPLICIT_LE + " ") == (
        scope.Classification(Disposition.SUPPORTED, "CT Image")
    )


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize(
    "sop_class, iod",
    [
        # Structured Reports, including dose reports, Key Object Selection
        # documents, and Presentation States, which the design always
        # sequesters.
        ("1.2.840.10008.5.1.4.1.1.88.33", "Comprehensive SR"),
        ("1.2.840.10008.5.1.4.1.1.88.67", "X-Ray Radiation Dose SR"),
        ("1.2.840.10008.5.1.4.1.1.88.59", "Key Object Selection Document"),
        ("1.2.840.10008.5.1.4.1.1.11.1", "Grayscale Softcopy Presentation State"),
        # Outside the first release: other images, RT Ion and second-generation
        # RT objects, and treatment records.
        ("1.2.840.10008.5.1.4.1.1.4", "MR Image"),
        ("1.2.840.10008.5.1.4.1.1.2.1", "Enhanced CT Image"),
        ("1.2.840.10008.5.1.4.1.1.481.8", "RT Ion Plan"),
        ("1.2.840.10008.5.1.4.1.1.481.10", "RT Physician Intent"),
        ("1.2.840.10008.5.1.4.1.1.481.14", "Tomotherapeutic Radiation"),
        ("1.2.840.10008.5.1.4.1.1.481.4", "RT Beams Treatment Record"),
        ("1.2.840.10008.5.1.4.1.1.481.6", "RT Brachy Treatment Record"),
    ],
)
def test_a_standard_sop_class_of_another_iod_is_sequestered(sop_class, iod):
    found = scope.classify(sop_class, EXPLICIT_LE)

    assert found == scope.Classification(Disposition.UNSUPPORTED_IOD, iod)
    assert found.sequestered


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize(
    "sop_class",
    [
        # A Private SOP Class under an invented root.
        "1.2.3.4.5",
        # The retired Nuclear Medicine Image Storage, Hanging Protocol Storage,
        # which another service class defines, and Verification.
        "1.2.840.10008.5.1.4.1.1.5",
        "1.2.840.10008.5.1.4.38.1",
        "1.2.840.10008.1.1",
        # Not a UID.
        "1.02",
        "CT",
    ],
)
def test_a_sop_class_that_table_b_5_1_does_not_list_is_sequestered(sop_class):
    found = scope.classify(sop_class, EXPLICIT_LE)

    assert found == scope.Classification(Disposition.UNLISTED_SOP_CLASS, None)
    assert found.sequestered


@pytest.mark.parametrize("sop_class", [None, "", " ", "\x00", 1, b"1.2"])
def test_an_instance_without_a_sop_class_is_sequestered(sop_class):
    found = scope.classify(sop_class, EXPLICIT_LE)

    assert found == scope.Classification(Disposition.NO_SOP_CLASS, None)


@pytest.mark.parametrize(
    "transfer_syntax",
    [
        "1.2.840.10008.1.2.2",  # Explicit VR Big Endian, retired
        "1.2.840.10008.1.2.1.98",  # Encapsulated Uncompressed Explicit VR LE
        "1.2.840.10008.1.2.1.99",  # Deflated Explicit VR Little Endian
        "1.2.840.10008.1.2.4.50",  # JPEG Baseline
        "1.2.840.10008.1.2.5",  # RLE Lossless
        "1.2.3.4.5",  # a private transfer syntax under an invented root
        "",
        None,
        1,
    ],
)
def test_a_supported_sop_class_in_another_transfer_syntax_is_sequestered(
    transfer_syntax,
):
    found = scope.classify("1.2.840.10008.5.1.4.1.1.2", transfer_syntax)

    assert found == scope.Classification(
        Disposition.UNSUPPORTED_TRANSFER_SYNTAX, "CT Image"
    )
    assert found.sequestered


def test_the_sop_class_decides_before_the_transfer_syntax():
    found = scope.classify("1.2.840.10008.5.1.4.1.1.88.33", "1.2.840.10008.1.2.4.50")

    assert found.disposition is Disposition.UNSUPPORTED_IOD


def test_the_table_can_be_given():
    table = sop_classes.load_storage_sop_classes()
    plan = next(row for row in table.rows if row.name == "RT Plan Storage")
    altered = dataclasses.replace(
        table, rows=(dataclasses.replace(plan, iod="MR Image IOD"),)
    )

    found = scope.classify(plan.uid, EXPLICIT_LE, sop_classes=altered)

    assert found == scope.Classification(Disposition.UNSUPPORTED_IOD, "MR Image")
    # CT Image Storage is not in the altered table.
    ct = scope.classify("1.2.840.10008.5.1.4.1.1.2", EXPLICIT_LE, sop_classes=altered)
    assert ct.disposition is Disposition.UNLISTED_SOP_CLASS


@pytest.mark.pydicom
def test_pydicom_names_the_same_uids():
    # pydicom's UID dictionary is an independent transcription of PS3.6.
    from pydicom import uid

    assert scope.SUPPORTED_TRANSFER_SYNTAXES == {
        uid.ImplicitVRLittleEndian,
        uid.ExplicitVRLittleEndian,
    }
    for sop_class in (
        uid.CTImageStorage,
        uid.RTDoseStorage,
        uid.RTStructureSetStorage,
        uid.RTPlanStorage,
    ):
        assert scope.classify(sop_class, uid.ExplicitVRLittleEndian).disposition is (
            Disposition.SUPPORTED
        )
