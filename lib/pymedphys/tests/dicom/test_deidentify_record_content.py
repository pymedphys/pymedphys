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
EXPLICIT_VR_BIG_ENDIAN = "1.2.840.10008.1.2.2"
# Person Names to Use Sequence (SQ) and Name to Use (LT), which the pinned
# data dictionary lists and pydicom 3.0.2 does not.
PERSON_NAMES_TO_USE = 0x00100011
NAME_TO_USE = 0x00100012
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


def _with_values_whose_vr_is_decided_on_writing(dataset):
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


def _with_standard_elements():
    """Return an RT Plan whose every element has a VR in a data dictionary.

    It has an issuer, values whose VR pydicom decides only when it writes
    them, and a sequence and text that pydicom 3.0.2 does not know, but the
    pinned data dictionary does.
    """
    dataset = _with_values_whose_vr_is_decided_on_writing(synthetic.rt_plan())
    dataset.IssuerOfPatientID = SOURCE_ISSUER
    name = synthetic.item()
    name.add_new(NAME_TO_USE, "LT", "FICTITIOUS NAME")
    dataset.add(synthetic.sequence(PERSON_NAMES_TO_USE, [name]))
    return dataset


def _with_private_elements():
    """Return the RT Plan with standard elements and private ones, one a sequence."""
    dataset = _with_standard_elements()
    block = dataset.private_block(0x0009, PRIVATE_CREATOR, create=True)
    block.add_new(0x01, "LO", "SYNTHETIC PRIVATE TEXT")
    block.add_new(0x02, "US", 7)
    block.add_new(0x03, "SQ", [synthetic.item(PatientID="SYNTHETIC-PRIVATE-ITEM")])
    return dataset


def _digest(dataset):
    return InstanceRecord.from_dataset(dataset).digest


def _private(dataset, offset):
    return dataset.private_block(0x0009, PRIVATE_CREATOR)[offset]


def _read_in_full(dataset, transfer_syntax):
    """Return ``dataset`` written in ``transfer_syntax``, read, and every value read."""
    read = synthetic.written_and_read(dataset, transfer_syntax)
    assert [element.value for element in read.iterall()]
    return read


def _read_after_reading_every_value(dataset):
    return _read_in_full(dataset, IMPLICIT_VR)


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
    # pydicom does not write group lengths, so they are added after reading.
    read = synthetic.written_and_read(dataset, EXPLICIT_VR)
    read.add_new(0x00080000, "UL", 1)
    read.add_new(0x00100000, "UL", 2)
    read.ReferencedDoseSequence[0].add_new(0x00080000, "UL", 3)
    return read


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.filterwarnings("ignore:VR lookup failed:UserWarning")
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
    # Copies of a data set without private elements, in Implicit VR and
    # Explicit VR Little Endian, decode to the same elements, VRs, and
    # values, since every element has a VR in a data dictionary. pydicom
    # reads Person Names to Use Sequence and the Name to Use in its item
    # from the Implicit VR copy as UN, and the content decodes them with
    # their VRs in the pinned data dictionary.
    expected = _digest(
        synthetic.written_and_read(_with_standard_elements(), EXPLICIT_VR)
    )

    assert _digest(copy(_with_standard_elements())) == expected


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "transfer_syntax", [IMPLICIT_VR, EXPLICIT_VR], ids=["implicit-vr", "explicit-vr"]
)
def test_a_vr_that_pydicom_decides_on_writing_is_the_vr_it_writes(transfer_syntax):
    # The data set holds no values as bytes, so it has the content of a copy
    # read from a file, whose VRs pydicom decided when it wrote the file.
    dataset = _with_values_whose_vr_is_decided_on_writing(synthetic.rt_plan())
    del dataset.PixelData
    read = synthetic.written_and_read(
        _with_values_whose_vr_is_decided_on_writing(synthetic.rt_plan()),
        transfer_syntax,
    )
    del read.PixelData

    assert _digest(dataset) == _digest(read)
    assert read["LargestImagePixelValue"].VR == "SS"
    # The data set is unchanged.
    assert dataset["LargestImagePixelValue"].VR == "US or SS"


def _unknown(monkeypatch, tag, value):
    """Return an element whose VR is UN, whatever pydicom's dictionary knows."""
    with monkeypatch.context() as patch:
        patch.setattr(pydicom.config, "replace_un_with_known_vr", False)
        return pydicom.DataElement(tag, "UN", value)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "keyword, value, encoded",
    [
        ("AccessionNumber", "SYNTHETIC-A1", b"SYNTHETIC-A1"),
        ("StudyDescription", "SYNTHETIC", b"SYNTHETIC "),
        ("Rows", 258, b"\x02\x01"),
        ("RedPaletteColorLookupTableData", b"\x01\x00\x02\x00", b"\x01\x00\x02\x00"),
    ],
    ids=["sh", "lo-padded", "us", "ow"],
)
def test_a_value_held_as_unknown_has_the_content_of_its_dictionary_vr(
    monkeypatch, keyword, value, encoded
):
    # PS3.5 Section 6.2.2 lets a reader that knows the VR of a UN value decode
    # it as Implicit VR Little Endian, whatever the transfer syntax.
    typed = synthetic.rt_plan()
    setattr(typed, keyword, value)
    typed = synthetic.written_and_read(typed, EXPLICIT_VR)
    unknown = synthetic.written_and_read(synthetic.rt_plan(), EXPLICIT_VR)
    tag = typed[keyword].tag
    unknown[tag] = _unknown(monkeypatch, tag, encoded)
    assert unknown[tag].VR == "UN"

    assert _digest(unknown) == _digest(typed)
    # The data set is unchanged.
    assert unknown[tag].VR == "UN"
    assert unknown[tag].value == encoded


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


def _changed_private_vr(dataset):
    # The value, 7, is encoded as the same two bytes in either VR.
    _private(dataset, 0x02).VR = "SS"


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
        _changed_private_vr,
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
        "changed-private-vr",
    ],
)
def test_any_change_to_the_data_set_changes_the_content(change):
    changed = _with_private_elements()
    change(changed)
    # Before writing the data set, which settles its VRs.
    in_memory = _digest(changed)

    # Both copies are in Explicit VR, which keeps the private elements' VRs,
    # so only the change can make them differ.
    original = synthetic.written_and_read(_with_private_elements(), EXPLICIT_VR)
    explicit = synthetic.written_and_read(changed, EXPLICIT_VR)

    assert _digest(original) != _digest(explicit)
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
    return synthetic.written_and_read(dataset, EXPLICIT_VR_BIG_ENDIAN)


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
def test_the_same_bytes_in_another_byte_order_conflict():
    # An OW value is words in the byte order of the transfer syntax (PS3.5
    # Section 7.3), so the bytes 01 00 are pixels of 1 in Explicit VR Little
    # Endian and of 256 in Explicit VR Big Endian.
    def image(transfer_syntax):
        dataset = _image()
        dataset.PixelData = b"\x01\x00" * len(PIXELS)
        return _read_in_full(dataset, transfer_syntax)

    little = image(EXPLICIT_VR)
    big = image(EXPLICIT_VR_BIG_ENDIAN)

    assert little.PixelData == big.PixelData
    assert little["PixelData"].VR == big["PixelData"].VR == "OW"
    assert _pixels(little) == [1] * len(PIXELS)
    assert _pixels(big) == [256] * len(PIXELS)
    assert _findings(little, big) == (CONFLICTING,)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_8_bit_pixel_data_in_implicit_and_explicit_vr_conflicts():
    # Implicit VR Little Endian holds native Pixel Data as OW, and pydicom
    # writes 8-bit Pixel Data in Explicit VR Little Endian as OB (PS3.5
    # Annex A), so the copies have different VRs.
    def image(transfer_syntax):
        dataset = _image()
        dataset.BitsAllocated = dataset.BitsStored = 8
        dataset.HighBit = 7
        dataset.PixelData = bytes(PIXELS)
        return _read_in_full(dataset, transfer_syntax)

    implicit = image(IMPLICIT_VR)
    explicit = image(EXPLICIT_VR)

    assert _pixels(implicit) == _pixels(explicit) == list(PIXELS)
    assert (implicit["PixelData"].VR, explicit["PixelData"].VR) == ("OW", "OB")
    assert _findings(implicit, explicit) == (CONFLICTING,)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_private_number_in_another_vr_with_the_same_bytes_conflicts():
    # Two copies of a CT slice, each written in Explicit VR Little Endian and
    # read in full, whose private element under one creator holds the same
    # two bytes, ff ff: -1 as SS in one copy, 65535 as US in the other.
    def ct_slice(vr, value):
        dataset = synthetic.ct_slice(0)
        block = dataset.private_block(0x0009, PRIVATE_CREATOR, create=True)
        block.add_new(0x01, vr, value)
        return _read_in_full(dataset, EXPLICIT_VR)

    signed = ct_slice("SS", -1)
    unsigned = ct_slice("US", 65535)

    assert struct.pack("<h", -1) == struct.pack("<H", 65535) == b"\xff\xff"
    assert (signed[0x00091001].VR, signed[0x00091001].value) == ("SS", -1)
    assert (unsigned[0x00091001].VR, unsigned[0x00091001].value) == ("US", 65535)
    assert _findings(signed, unsigned) == (CONFLICTING,)


# (0008,0002), in a standard group, is in neither pydicom's data dictionary
# nor the pinned one.
UNLISTED = 0x00080002


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.filterwarnings("ignore:VR lookup failed:UserWarning")
@pytest.mark.parametrize(
    "tag, vr, value",
    [
        (0x00091001, "LO", "SYNTHETIC PRIVATE TEXT"),
        (0x00091001, "LO", "SYNTHETIC PRIVATE TEXT  "),
        (0x00091001, "US", 7),
        (0x00091001, "OW", b"\x01\x00"),
        (0x00091001, "SQ", None),
        (UNLISTED, "LO", "SYNTHETIC TEXT"),
    ],
    ids=[
        "private-text",
        "private-padded-text",
        "private-number",
        "private-words",
        "private-sequence",
        "unlisted",
    ],
)
def test_an_element_read_as_unknown_conflicts_with_a_copy_that_has_its_vr(
    tag, vr, value
):
    # Implicit VR Little Endian holds no VRs, and no data dictionary gives
    # this element's VR, so pydicom reads it from the Implicit VR copy as UN
    # and keeps its bytes. Without a VR to decode them with, the copies
    # cannot be shown to be equal.
    def ct_slice():
        dataset = synthetic.ct_slice(0)
        held = value
        if vr == "SQ":
            held = [synthetic.item(PatientID="SYNTHETIC-PRIVATE-ITEM")]
        if tag == UNLISTED:
            dataset.add_new(tag, vr, held)
        else:
            block = dataset.private_block(0x0009, PRIVATE_CREATOR, create=True)
            block.add_new(0x01, vr, held)
        return dataset

    implicit = _read_in_full(ct_slice(), IMPLICIT_VR)
    explicit = _read_in_full(ct_slice(), EXPLICIT_VR)

    assert implicit[tag].VR == "UN"
    assert explicit[tag].VR == vr
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


def _content(tag, vr, value, byte_order=b"-"):
    """Return an element's content, built by hand.

    Its tag's group and element, each little endian; the length of its VR,
    in one byte, then the VR; one byte for the byte order of a value that
    pydicom holds as bytes, other than an OB value, ``<`` for little endian,
    ``>`` for big endian, and ``?`` for none, or ``-`` for any other value;
    then the value's length, little endian, and the value, each as Implicit
    VR Little Endian encodes them (PS3.5 Sections 7.1.3 and 7.5).
    """
    return (
        struct.pack("<HHB", tag >> 16, tag & 0xFFFF, len(vr))
        + vr.encode()
        + byte_order
        + struct.pack("<I", len(value))
        + value
    )


def _item(*contents):
    """Return an item of defined length: its tag, length, and contents."""
    value = b"".join(contents)
    return struct.pack("<HHI", 0xFFFE, 0xE000, len(value)) + value


def _uid(uid):
    # A UID of odd length has a trailing NUL (PS3.5 Section 9.1).
    return uid.encode() + b"\x00" * (len(uid) % 2)


@pytest.mark.pydicom
def test_the_content_is_each_elements_tag_vr_and_value_without_the_file_meta():
    # Each element in tag order, with every sequence and item of defined
    # length, and without group lengths (PS3.5 Section 7.2). Group 0002 is
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
    dataset.Rows = 258
    encoded_image = _item(
        _content(0x00020010, "UI", _uid(IMPLICIT_VR)),
        _content(0x00081155, "UI", _uid("2.25.72")),
    )
    expected = b"".join(
        [
            _content(0x00080018, "UI", _uid("2.25.71")),
            _content(0x00081140, "SQ", encoded_image),
            _content(0x00100020, "LO", b"SYNTHETIC-X "),
            _content(0x00280010, "US", b"\x02\x01"),
        ]
    )

    assert _digest(dataset) == hashlib.sha256(expected).digest()


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "transfer_syntax, byte_order",
    [
        (None, b"?"),
        (EXPLICIT_VR, b"<"),
        (EXPLICIT_VR_BIG_ENDIAN, b">"),
    ],
    ids=["built-in-memory", "little-endian", "big-endian"],
)
def test_a_value_held_as_bytes_has_the_byte_order_of_its_data_set(
    monkeypatch, transfer_syntax, byte_order
):
    # pydicom holds an OW value as bytes in the byte order of its file (PS3.5
    # Section 7.3), and a data set built in memory has none. An OB value is a
    # stream of bytes, in no byte order. A UN value is decoded as Implicit VR
    # Little Endian, whatever the transfer syntax (PS3.5 Section 6.2.2).
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = synthetic.CT_IMAGE_STORAGE
    dataset.SOPInstanceUID = "2.25.71"
    dataset.RedPaletteColorLookupTableData = b"\x01\x00\x02\x00"
    dataset.EncapsulatedDocument = b"\x01\x00"
    if transfer_syntax is not None:
        dataset = synthetic.written_and_read(dataset, transfer_syntax)
    # Green Palette Color Lookup Table Data, whose dictionary VR is OW.
    dataset[0x00281202] = _unknown(monkeypatch, 0x00281202, b"\x03\x00")
    expected = b"".join(
        [
            _content(0x00080016, "UI", _uid(synthetic.CT_IMAGE_STORAGE)),
            _content(0x00080018, "UI", _uid("2.25.71")),
            _content(0x00281201, "OW", b"\x01\x00\x02\x00", byte_order),
            _content(0x00281202, "OW", b"\x03\x00", b"<"),
            _content(0x00420011, "OB", b"\x01\x00"),
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
