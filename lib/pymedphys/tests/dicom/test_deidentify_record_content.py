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

"""The patient and the content that an instance record holds for the hierarchy."""

import hashlib
import io
import struct
import warnings

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import pseudonyms, reference_graph
from pymedphys._dicom.deidentify.references import InstanceRecord

from . import _synthetic_references as synthetic

SOURCE_ISSUER = "SYNTHETIC-ISSUER-3H8M"
PRIVATE_CREATOR = "SYNTHETIC CREATOR 5T"
IMPLICIT_VR = "1.2.840.10008.1.2"
EXPLICIT_VR = "1.2.840.10008.1.2.1"
# Two copies of one SOP Instance UID with different content.
CONFLICTING = reference_graph.Finding(
    reference_graph.FindingKind.CONFLICTING_INSTANCE, ((0,), (1,)), ("(0008,0018)",)
)


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "patient_id, issuer, expected",
    [
        (synthetic.PATIENT_ID, None, (synthetic.PATIENT_ID, "")),
        (synthetic.PATIENT_ID, "", (synthetic.PATIENT_ID, "")),
        (synthetic.PATIENT_ID, SOURCE_ISSUER, (synthetic.PATIENT_ID, SOURCE_ISSUER)),
        # LO may be padded with leading and trailing spaces (PS3.5 Table 6.2-1).
        (
            f" {synthetic.PATIENT_ID} ",
            f"{SOURCE_ISSUER} ",
            (synthetic.PATIENT_ID, SOURCE_ISSUER),
        ),
        # Patient ID has one value, so its whole text, backslashes and all,
        # identifies the patient.
        (["SYNTHETIC-A", "SYNTHETIC-B"], None, ("SYNTHETIC-A\\SYNTHETIC-B", "")),
        (["SYNTHETIC-A", ""], None, ("SYNTHETIC-A\\", "")),
        (None, SOURCE_ISSUER, None),
        ("", SOURCE_ISSUER, None),
        ("  ", None, None),
    ],
    ids=[
        "no-issuer",
        "empty-issuer",
        "issuer",
        "padded",
        "two-values",
        "second-value-empty",
        "no-patient-id",
        "empty-patient-id",
        "padding-only",
    ],
)
def test_a_record_holds_the_patient_identity(patient_id, issuer, expected):
    dataset = synthetic.rt_plan()
    del dataset.PatientID
    if patient_id is not None:
        dataset.PatientID = patient_id
    if issuer is not None:
        dataset.IssuerOfPatientID = issuer

    record = InstanceRecord.from_dataset(dataset)

    assert record.patient == (
        None
        if expected is None
        else pseudonyms.SubjectIdentity.from_patient_id(*expected)
    )


@pytest.mark.pydicom
def test_a_patient_id_that_is_not_text_names_no_patient(monkeypatch):
    # pydicom keeps the value of a UN element as bytes when it does not
    # replace UN with the VR it knows.
    dataset = synthetic.rt_plan()
    monkeypatch.setattr(pydicom.config, "replace_un_with_known_vr", False)
    dataset[0x00100020] = pydicom.DataElement(0x00100020, "UN", b"SYNTHETIC-7Q2K")
    assert dataset[0x00100020].VR == "UN"

    assert InstanceRecord.from_dataset(dataset).patient is None


def _with_private_elements():
    """Return an RT Plan with an issuer and private elements, one a sequence.

    It also has values whose VR pydicom decides only when it writes them.
    """
    dataset = synthetic.rt_plan()
    dataset.IssuerOfPatientID = SOURCE_ISSUER
    block = dataset.private_block(0x0009, PRIVATE_CREATOR, create=True)
    block.add_new(0x01, "LO", "SYNTHETIC PRIVATE TEXT")
    block.add_new(0x02, "US", 7)
    block.add_new(0x03, "SQ", [synthetic.item(PatientID="SYNTHETIC-PRIVATE-ITEM")])
    # Until pydicom writes these, their VRs are "US or SS" and "OB or OW";
    # it then decides SS from Pixel Representation, and OW from Bits
    # Allocated.
    dataset.PixelRepresentation = 1
    dataset.BitsAllocated = 16
    dataset.SmallestImagePixelValue = -3
    dataset.LargestImagePixelValue = 3
    dataset.LUTDescriptor = [256, -100, 16]
    dataset.PixelData = b"\x01\x02" * 4
    return dataset


def _digest(dataset):
    return InstanceRecord.from_dataset(dataset).digest


def _private(dataset, offset):
    return dataset.private_block(0x0009, PRIVATE_CREATOR)[offset]


def _read_after_reading_every_value(dataset):
    read = synthetic.written_and_read(dataset, IMPLICIT_VR)
    assert [element.value for element in read.iterall()]
    return read


def _with_padding(dataset):
    # pydicom removes trailing padding when it decodes a value it knows.
    dataset.PatientName = synthetic.PATIENTS_NAME + "  "
    dataset.PatientID = synthetic.PATIENT_ID + "  "
    return synthetic.written_and_read(dataset, IMPLICIT_VR)


def _with_undefined_lengths(dataset):
    for element in dataset.iterall():
        if element.VR == "SQ":
            element.is_undefined_length = True
    return synthetic.written_and_read(dataset, EXPLICIT_VR)


def _deferred(dataset):
    # pydicom reads each value longer than 4 bytes only when it is accessed.
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = IMPLICIT_VR
    written = io.BytesIO()
    pydicom.dcmwrite(written, dataset, enforce_file_format=True)
    read = pydicom.dcmread(io.BytesIO(written.getvalue()), defer_size=4)
    assert read.get_item(0x7FE00010, keep_deferred=True).value is None
    return read


def _with_other_file_meta_and_preamble(dataset):
    dataset.preamble = b"\x01" * 128
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = EXPLICIT_VR
    dataset.file_meta.ImplementationVersionName = "SYNTHETIC"
    dataset.file_meta.SourceApplicationEntityTitle = "SYNTHETIC-AE"
    written = io.BytesIO()
    pydicom.dcmwrite(written, dataset, enforce_file_format=True)
    return pydicom.dcmread(io.BytesIO(written.getvalue()))


def _with_group_lengths(dataset):
    # pydicom does not write group lengths, so the copy stays in memory.
    dataset.add_new(0x00080000, "UL", 1)
    dataset.add_new(0x00090000, "UL", 2)
    dataset.ReferencedDoseSequence[0].add_new(0x00080000, "UL", 3)
    return dataset


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "copy",
    [
        lambda dataset: synthetic.written_and_read(dataset, IMPLICIT_VR),
        lambda dataset: synthetic.written_and_read(dataset, EXPLICIT_VR),
        _read_after_reading_every_value,
        _with_undefined_lengths,
        _deferred,
        _with_other_file_meta_and_preamble,
        _with_group_lengths,
        _with_padding,
    ],
    ids=[
        "implicit-vr",
        "explicit-vr",
        "every-value-read",
        "undefined-lengths",
        "deferred",
        "other-file-meta-and-preamble",
        "group-lengths",
        "padding",
    ],
)
def test_a_copy_in_another_encoding_has_the_same_content(copy):
    # Implicit VR Little Endian holds no VRs, so the private elements that
    # pydicom reads from it as UN have the same content as the explicit copy's.
    expected = _digest(_with_private_elements())
    implicit = synthetic.written_and_read(_with_private_elements(), IMPLICIT_VR)
    assert implicit[0x00091001].VR == "UN"

    assert _digest(copy(_with_private_elements())) == expected
    assert _digest(implicit) == expected


def _changed(attribute, value):
    def change(dataset):
        setattr(dataset, attribute, value)

    return change


def _changed_private(offset, value):
    def change(dataset):
        _private(dataset, offset).value = value

    return change


def _without(attribute):
    def change(dataset):
        delattr(dataset, attribute)

    return change


def _changed_creator(dataset):
    dataset[0x00090010].value = "SYNTHETIC CREATOR 6U"


def _changed_private_item(dataset):
    _private(dataset, 0x03).value[0].PatientID = "SYNTHETIC-PRIVATE-OTHER"


def _changed_nested_value(dataset):
    synthetic.uid(
        dataset.ReferencedDoseSequence[0], "ReferencedSOPInstanceUID", "2.25.9"
    )


def _with_another_item(dataset):
    dataset.ReferencedDoseSequence.append(
        synthetic.reference(synthetic.RT_DOSE_STORAGE, "2.25.9")
    )


def _without_items(dataset):
    dataset.ReferencedDoseSequence = []


def _without_a_private_element(dataset):
    del dataset[0x00091002]


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "change",
    [
        _changed("PatientName", "FICTITIOUS^OTHER"),
        _changed_nested_value,
        _changed("StudyDescription", "SYNTHETIC"),
        _changed("StudyDescription", ""),
        _without("PatientName"),
        _with_another_item,
        _without_items,
        _changed("SmallestImagePixelValue", -4),
        _changed("LargestImagePixelValue", None),
        _changed_private(0x01, "SYNTHETIC PRIVATE TEXT 2"),
        _changed_private(0x02, 8),
        _changed_private_item,
        _changed_creator,
        _without_a_private_element,
    ],
    ids=[
        "changed-value",
        "changed-value-in-an-item",
        "added-element",
        "added-empty-element",
        "removed-element",
        "added-item",
        "removed-item",
        "changed-signed-number",
        "emptied-signed-number",
        "changed-private-text",
        "changed-private-number",
        "changed-private-item",
        "changed-private-creator",
        "removed-private-element",
    ],
)
def test_any_change_to_the_data_set_changes_the_content(change):
    changed = _with_private_elements()
    change(changed)
    # Before writing the data set, which settles its VRs.
    in_memory = _digest(changed)

    implicit = synthetic.written_and_read(_with_private_elements(), IMPLICIT_VR)
    explicit = synthetic.written_and_read(changed, EXPLICIT_VR)

    assert _digest(implicit) != _digest(explicit)
    assert _digest(_with_private_elements()) != in_memory


def _findings(*datasets):
    records = [InstanceRecord.from_dataset(dataset) for dataset in datasets]
    return reference_graph.build_reference_graph(records).findings


PIXELS = (0, 1, 2, 3, 4, 5)


def _image():
    """Return a CT slice with an image of two rows of three pixels."""
    dataset = synthetic.ct_slice(0)
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows = 2
    dataset.Columns = 3
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.PixelData = struct.pack("<6H", *PIXELS)
    return dataset


def _rle_lossless(dataset):
    # pydicom's own RLE Lossless encoder needs no optional codec, and
    # encapsulates Pixel Data (PS3.5 Section A.4). It starts from a data set
    # with a transfer syntax.
    dataset = synthetic.written_and_read(dataset, EXPLICIT_VR)
    dataset.compress(
        pydicom.uid.RLELossless, encoding_plugin="pydicom", generate_instance_uid=False
    )
    return synthetic.written_and_read(dataset, pydicom.uid.RLELossless)


def _big_endian(dataset):
    # A big endian file holds an OW value in big endian byte order (PS3.5
    # Section 7.3), and pydicom keeps the value's bytes as the file has them.
    dataset.PixelData = struct.pack(">6H", *PIXELS)
    return synthetic.written_and_read(dataset, pydicom.uid.ExplicitVRBigEndian)


def _pixels(dataset):
    decoder = pydicom.pixels.get_decoder(dataset.file_meta.TransferSyntaxUID)
    return decoder.as_array(dataset)[0].ravel().tolist()


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "copy", [_rle_lossless, _big_endian], ids=["rle-lossless", "big-endian"]
)
def test_a_copy_whose_pixel_data_is_encoded_otherwise_conflicts(copy):
    # The content holds Pixel Data as the file encodes it, so copies of one
    # image conflict, and are sequestered, when one is compressed or big
    # endian.
    native = synthetic.written_and_read(_image(), EXPLICIT_VR)
    other = copy(_image())

    assert _pixels(other) == _pixels(native) == list(PIXELS)
    assert _findings(native, other) == (CONFLICTING,)
    # Only Pixel Data differs.
    del native.PixelData, other.PixelData
    assert _digest(native) == _digest(other)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_padding_that_a_private_element_read_as_un_keeps_makes_copies_conflict():
    # pydicom reads the private element from the Implicit VR file as UN and
    # keeps its bytes, and from the Explicit VR file as LO, removing its
    # trailing spaces; encoding adds back only the one that makes the
    # length even.
    def ct_slice():
        dataset = synthetic.ct_slice(0)
        block = dataset.private_block(0x0009, PRIVATE_CREATOR, create=True)
        block.add_new(0x01, "LO", "SYNTHETIC PRIVATE TEXT  ")
        return dataset

    implicit = synthetic.written_and_read(ct_slice(), IMPLICIT_VR)
    explicit = synthetic.written_and_read(ct_slice(), EXPLICIT_VR)

    assert implicit[0x00091001].value == b"SYNTHETIC PRIVATE TEXT  "
    assert explicit[0x00091001].value == "SYNTHETIC PRIVATE TEXT"
    assert _findings(implicit, explicit) == (CONFLICTING,)


def _read(dataset, **options):
    """Return ``dataset`` written in Explicit VR and read with ``options``."""
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = EXPLICIT_VR
    written = io.BytesIO()
    pydicom.dcmwrite(written, dataset, enforce_file_format=True)
    return pydicom.dcmread(io.BytesIO(written.getvalue()), **options)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "options, change",
    [
        ({"stop_before_pixels": True}, _changed("PixelData", b"\x02\x01" * 4)),
        (
            {"specific_tags": ["SOPClassUID", "SOPInstanceUID"]},
            _changed("PatientName", "FICTITIOUS^OTHER"),
        ),
    ],
    ids=["stop-before-pixels", "specific-tags"],
)
def test_a_record_needs_a_data_set_read_in_full(options, change):
    # A record has the content of the data set it is given, so copies that
    # differ only in the elements that reading skipped would be identical.
    changed = _with_private_elements()
    change(changed)

    assert _digest(_read(changed)) != _digest(_read(_with_private_elements()))
    assert _digest(_read(changed, **options)) == _digest(
        _read(_with_private_elements(), **options)
    )


def _encoded(tag, value):
    """Return an element or item of defined length in Implicit VR Little Endian.

    Its tag's group and element, then the length of ``value``, each little
    endian, then ``value`` (PS3.5 Sections 7.1.3 and 7.5).
    """
    return struct.pack("<HHI", tag >> 16, tag & 0xFFFF, len(value)) + value


def _encoded_uid(tag, uid):
    # A UID of odd length has a trailing NUL (PS3.5 Section 9.1).
    return _encoded(tag, uid.encode() + b"\x00" * (len(uid) % 2))


@pytest.mark.pydicom
def test_the_content_is_the_implicit_vr_encoding_without_the_file_meta():
    # Built by hand from PS3.5 Sections 7.1.3 and 7.5: each element's tag,
    # value length, and value, in tag order, with every sequence and item of
    # defined length, and without group lengths (Section 7.2). Group 0002 is
    # the File Meta Information only at the top level (PS3.10 Section 7.1).
    dataset = pydicom.Dataset()
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = EXPLICIT_VR
    dataset.PatientID = "SYNTHETIC-X"
    dataset.add_new(0x00080000, "UL", 1)
    dataset.SOPInstanceUID = "2.25.71"
    image = synthetic.reference(None, "2.25.72")
    image.add_new(0x00080000, "UL", 2)
    image.add_new(0x00020010, "UI", IMPLICIT_VR)
    dataset.ReferencedImageSequence = [image]
    dataset["ReferencedImageSequence"].is_undefined_length = True
    dataset.add_new(0x00020010, "UI", IMPLICIT_VR)
    encoded_image = [
        _encoded_uid(0x00020010, IMPLICIT_VR),
        _encoded_uid(0x00081155, "2.25.72"),
    ]
    expected = b"".join(
        [
            _encoded_uid(0x00080018, "2.25.71"),
            _encoded(0x00081140, _encoded(0xFFFEE000, b"".join(encoded_image))),
            _encoded(0x00100020, b"SYNTHETIC-X "),
        ]
    )

    assert _digest(dataset) == hashlib.sha256(expected).digest()


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize("nested", [False, True], ids=["top-level", "in-an-item"])
def test_text_is_compared_in_its_character_set(nested):
    # The letters differ only outside ISO 8859-1, pydicom's default, so
    # encoding them without the data set's character set would lose them.
    def plan(letter):
        dataset = synthetic.rt_plan()
        dataset.SpecificCharacterSet = "ISO_IR 192"
        if nested:
            dataset.OtherPatientIDsSequence = [
                synthetic.item(PatientID=f"SYNTHETIC-{letter}")
            ]
        else:
            dataset.PatientID = f"SYNTHETIC-{letter}"
        return dataset

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        first, second = (_digest(plan(letter)) for letter in "\u0100\u0102")
        read = _digest(synthetic.written_and_read(plan("\u0100"), IMPLICIT_VR))

    assert first != second
    assert read == first
