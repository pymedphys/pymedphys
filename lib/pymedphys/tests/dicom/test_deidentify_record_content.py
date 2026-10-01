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

"""The patient and the source bytes that an instance record holds for the hierarchy."""

import hashlib
import io
import struct

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import pseudonyms, reference_graph
from pymedphys._dicom.deidentify.file_layout import Region, read_file_layout
from pymedphys._dicom.deidentify.references import InstanceRecord

from . import _synthetic_references as synthetic

SOURCE_ISSUER = "SYNTHETIC-ISSUER-3H8M"
PRIVATE_CREATOR = "SYNTHETIC CREATOR 5T"
IMPLICIT_VR = synthetic.IMPLICIT_VR_LITTLE_ENDIAN
EXPLICIT_VR = synthetic.EXPLICIT_VR_LITTLE_ENDIAN
EXPLICIT_VR_BIG_ENDIAN = "1.2.840.10008.1.2.2"
DEFLATED_EXPLICIT_VR = "1.2.840.10008.1.2.1.99"
# Person Names to Use Sequence (SQ) and Name to Use (LT), which the pinned
# data dictionary lists and pydicom 3.0.2 does not.
PERSON_NAMES_TO_USE = 0x00100011
NAME_TO_USE = 0x00100012
# Two copies of one SOP Instance UID with different source bytes.
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

    record = synthetic.record(dataset)

    assert record.patient == (
        None
        if expected is None
        else pseudonyms.SubjectIdentity.from_patient_id(*expected)
    )


@pytest.mark.pydicom
def test_a_patient_id_that_is_not_text_names_no_patient(monkeypatch):
    # pydicom keeps the value of a UN element as bytes when it does not
    # replace UN with the VR it knows, here also when it reads the file.
    dataset = synthetic.rt_plan()
    monkeypatch.setattr(pydicom.config, "replace_un_with_known_vr", False)
    dataset[0x00100020] = pydicom.DataElement(0x00100020, "UN", b"SYNTHETIC-7Q2K")
    data = synthetic.written(dataset)
    assert synthetic.read(data)[0x00100020].VR == "UN"

    assert InstanceRecord.from_file(data).patient is None


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


def _plan():
    """Return an RT Plan with an issuer, values of several VRs, and private elements.

    It has values whose VR pydicom decides only when it writes them, a
    sequence and text that pydicom 3.0.2 does not know, but the pinned data
    dictionary does, and private elements, one a sequence.
    """
    dataset = _with_values_whose_vr_is_decided_on_writing(synthetic.rt_plan())
    dataset.IssuerOfPatientID = SOURCE_ISSUER
    name = synthetic.item()
    name.add_new(NAME_TO_USE, "LT", "FICTITIOUS NAME")
    dataset.add(synthetic.sequence(PERSON_NAMES_TO_USE, [name]))
    block = dataset.private_block(0x0009, PRIVATE_CREATOR, create=True)
    block.add_new(0x01, "LO", "SYNTHETIC PRIVATE TEXT")
    block.add_new(0x02, "US", 7)
    block.add_new(0x03, "SQ", [synthetic.item(PatientID="SYNTHETIC-PRIVATE-ITEM")])
    return dataset


def _digest(data):
    return InstanceRecord.from_file(data).digest


def _private(dataset, offset):
    return dataset.private_block(0x0009, PRIVATE_CREATOR)[offset]


def _data_set_start(data):
    """Return where the data set starts, after the File Meta Information.

    The preamble and "DICM" are 132 bytes, and File Meta Information Group
    Length (0002,0000), the first element, is 12 bytes in Explicit VR Little
    Endian, with its value at bytes 140 to 143 (PS3.10 Section 7.1).
    """
    (length,) = struct.unpack_from("<I", data, 140)
    return 144 + length


def _element(tag, vr, value):
    """Return an element in Explicit VR Little Endian with a 16-bit length.

    Its tag's group and element, its VR, and its value's length, each little
    endian, then its value (PS3.5 Section 7.1.2 and Table 7.1-2).
    """
    header = struct.pack("<HH2sH", tag >> 16, tag & 0xFFFF, vr.encode(), len(value))
    return header + value


def _group_length(group):
    """Return a group length (gggg,0000) whose value is arbitrary (PS3.5 7.2)."""
    return _element(group << 16, "UL", struct.pack("<I", 0x1234))


# Data Set Trailing Padding (FFFC,FFFC) of four bytes, as OB, whose header is
# 12 bytes in Explicit VR (PS3.5 Table 7.1-1, PS3.10 Section 7.2).
TRAILING_PADDING = struct.pack("<HH2s2xI", 0xFFFC, 0xFFFC, b"OB", 4) + bytes(4)


def _inserted(data, inserted, where):
    """Return ``data`` with ``inserted`` before the first element ``where`` picks.

    ``where`` is given the path of each data set element in file order.
    """
    start = next(
        span.start
        for span in read_file_layout(data).spans
        if span.location.region is Region.DATA_SET and where(span.location.element)
    )
    return data[:start] + inserted + data[start:]


def _top_level_group(group):
    return lambda path: not path.items and path.tag[1:5] == f"{group:04X}"


def _written_again(dataset):
    return synthetic.written(dataset)


def _with_other_file_meta_and_preamble(dataset):
    dataset.preamble = b"\x01" * 128
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = EXPLICIT_VR
    dataset.file_meta.ImplementationVersionName = "SYNTHETIC"
    dataset.file_meta.SourceApplicationEntityTitle = "SYNTHETIC-AE"
    written = io.BytesIO()
    pydicom.dcmwrite(written, dataset, enforce_file_format=True)
    data = written.getvalue()
    plain = synthetic.written(_plan())
    assert data[: _data_set_start(data)] != plain[: _data_set_start(plain)]
    return data


def _with_group_lengths(dataset):
    # pydicom does not write group lengths, so they are inserted.
    data = synthetic.written(dataset)
    for group in (0x0008, 0x0010):
        data = _inserted(data, _group_length(group), _top_level_group(group))
    assert 0x00080000 in synthetic.read(data)
    return data


def _with_trailing_padding(dataset):
    data = synthetic.written(dataset) + TRAILING_PADDING
    assert 0xFFFCFFFC in synthetic.read(data)
    return data


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "copy",
    [
        _written_again,
        _with_other_file_meta_and_preamble,
        _with_group_lengths,
        _with_trailing_padding,
    ],
    ids=[
        "written-again",
        "other-file-meta-and-preamble",
        "group-lengths",
        "trailing-padding",
    ],
)
def test_copies_with_the_same_source_bytes_have_the_same_digest(copy):
    # The preamble, the File Meta Information, and the top-level group
    # lengths and Data Set Trailing Padding are not part of the source bytes.
    expected = _digest(synthetic.written(_plan()))

    assert expected is not None
    assert _digest(copy(_plan())) == expected


def _undefined_lengths(dataset):
    for element in dataset.iterall():
        if element.VR == "SQ":
            element.is_undefined_length = True
            for item in element.value:
                item.is_undefined_length_sequence_item = True
    return dataset


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_copies_in_implicit_and_explicit_vr_have_different_digests():
    implicit = synthetic.written(synthetic.rt_plan(), IMPLICIT_VR)
    explicit = synthetic.written(synthetic.rt_plan(), EXPLICIT_VR)

    assert synthetic.read(implicit) == synthetic.read(explicit)
    assert None not in (_digest(implicit), _digest(explicit))
    assert _digest(implicit) != _digest(explicit)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_sequences_of_undefined_length_have_another_digest():
    defined = synthetic.written(synthetic.rt_plan())
    undefined = synthetic.written(_undefined_lengths(synthetic.rt_plan()))

    assert synthetic.read(defined) == synthetic.read(undefined)
    assert _digest(defined) != _digest(undefined)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_value_with_more_padding_has_another_digest():
    # pydicom removes the trailing spaces of a Person Name when it decodes it.
    plain = synthetic.written(synthetic.rt_plan())
    dataset = synthetic.rt_plan()
    dataset.PatientName = synthetic.PATIENTS_NAME + "  "
    padded = synthetic.written(dataset)

    assert synthetic.read(padded).PatientName == synthetic.PATIENTS_NAME
    assert _digest(plain) != _digest(padded)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_group_length_in_an_item_changes_the_digest():
    # Every sequence and item has undefined length, so the group length
    # needs no other length changed.
    data = synthetic.written(_undefined_lengths(synthetic.rt_plan()))
    in_item = _inserted(
        data,
        _group_length(0x0008),
        lambda path: path.items == (("(300C,0080)", 0),),
    )

    assert 0x00080000 in synthetic.read(in_item).ReferencedDoseSequence[0]
    assert _digest(in_item) not in (None, _digest(data))


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_the_same_data_set_in_another_transfer_syntax_has_another_digest():
    # RLE Lossless encodes the data set as Explicit VR Little Endian (PS3.5
    # Section A.4.2), so a data set without Pixel Data has the same bytes.
    explicit = synthetic.written(synthetic.rt_plan(), EXPLICIT_VR)
    rle = synthetic.written(synthetic.rt_plan(), pydicom.uid.RLELossless)

    assert explicit[_data_set_start(explicit) :] == rle[_data_set_start(rle) :]
    assert None not in (_digest(explicit), _digest(rle))
    assert _digest(explicit) != _digest(rle)


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
        _changed("PixelData", b"\x02\x01" * 4),
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
        "changed-pixel-data",
        "changed-private-text",
        "changed-private-number",
        "changed-private-item",
        "changed-private-creator",
        "removed-private-element",
        "changed-private-vr",
    ],
)
def test_any_change_to_the_data_set_changes_the_digest(change):
    changed = _plan()
    change(changed)

    assert _digest(synthetic.written(changed)) not in (
        None,
        _digest(synthetic.written(_plan())),
    )


def _without_transfer_syntax(data):
    """Return the file with File Meta Information that has no Transfer Syntax UID."""
    meta = b"".join(
        _element(tag, "UI", uid)
        for tag, uid in [(0x00020002, b"2.25.1\x00"), (0x00020003, b"2.25.2\x00")]
    )
    length = _element(0x00020000, "UL", struct.pack("<I", len(meta)))
    return data[:132] + length + meta + data[_data_set_start(data) :]


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
# pydicom reads the last UID of the truncated file without its last bytes.
@pytest.mark.filterwarnings("ignore:Invalid value for VR UI:UserWarning")
@pytest.mark.parametrize(
    "unsound",
    [
        lambda: synthetic.written(synthetic.rt_plan(), EXPLICIT_VR_BIG_ENDIAN),
        lambda: synthetic.written(synthetic.rt_plan(), DEFLATED_EXPLICIT_VR),
        lambda: synthetic.written(synthetic.rt_plan()) + b"\x01\x02\x03",
        lambda: synthetic.written(synthetic.rt_plan())[:-3],
        lambda: _without_transfer_syntax(synthetic.written(synthetic.rt_plan())),
    ],
    ids=[
        "big-endian",
        "deflated",
        "trailing-bytes",
        "truncated",
        "no-transfer-syntax",
    ],
)
def test_a_file_whose_bytes_cannot_be_shown_sound_has_no_digest(unsound):
    # pydicom reads each of these files, so the record has its identity.
    record = InstanceRecord.from_file(unsound())

    assert record.digest is None
    assert record.sop_instance == synthetic.PLAN


@pytest.mark.pydicom
def test_the_digest_is_of_the_transfer_syntax_and_the_data_set_bytes():
    # A data set with a group length and Data Set Trailing Padding, both of
    # which are left out of the digest, as the File Meta Information is.
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = synthetic.CT_IMAGE_STORAGE
    dataset.SOPInstanceUID = "2.25.71"
    dataset.PatientID = "SYNTHETIC-X"
    plain = synthetic.written(dataset)
    data = _inserted(plain, _group_length(0x0010), _top_level_group(0x0010))
    data += TRAILING_PADDING
    assert len(data) == len(plain) + 12 + len(TRAILING_PADDING)

    expected = hashlib.sha256(
        EXPLICIT_VR.encode() + b"\x00" + plain[_data_set_start(plain) :]
    ).digest()

    assert _digest(data) == _digest(plain) == expected


def _findings(*files):
    records = [InstanceRecord.from_file(data) for data in files]
    return reference_graph.build_reference_graph(records).findings


@pytest.mark.pydicom
def test_copies_whose_bytes_cannot_be_shown_sound_conflict_each_alone():
    # The same file without a digest twice, a copy in another transfer
    # syntax that also has none, and a copy that has one.
    big_endian = synthetic.written(synthetic.ct_slice(0), EXPLICIT_VR_BIG_ENDIAN)
    deflated = synthetic.written(synthetic.ct_slice(0), DEFLATED_EXPLICIT_VR)
    sound = synthetic.written(synthetic.ct_slice(0))
    assert _digest(big_endian) is _digest(deflated) is None

    assert _findings(big_endian, big_endian, deflated, sound) == (
        reference_graph.Finding(
            reference_graph.FindingKind.CONFLICTING_INSTANCE,
            ((0,), (1,), (2,), (3,)),
            ("(0008,0018)",),
        ),
    )
    assert _findings(sound, big_endian) == (CONFLICTING,)


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
    dataset = synthetic.read(synthetic.written(dataset))
    dataset.compress(
        pydicom.uid.RLELossless, encoding_plugin="pydicom", generate_instance_uid=False
    )
    return synthetic.written(dataset, pydicom.uid.RLELossless)


def _big_endian(dataset):
    # A big endian file holds an OW value in big endian byte order (PS3.5
    # Section 7.3).
    dataset.PixelData = struct.pack(">6H", *PIXELS)
    return synthetic.written(dataset, EXPLICIT_VR_BIG_ENDIAN)


def _pixels(data):
    dataset = synthetic.read(data)
    decoder = pydicom.pixels.get_decoder(dataset.file_meta.TransferSyntaxUID)
    return decoder.as_array(dataset)[0].ravel().tolist()


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "copy", [_rle_lossless, _big_endian], ids=["rle-lossless", "big-endian"]
)
def test_a_copy_whose_pixel_data_is_encoded_otherwise_conflicts(copy):
    # Copies of one image conflict, and are sequestered, when one is
    # compressed or big endian.
    native = synthetic.written(_image())
    other = copy(_image())

    assert _pixels(other) == _pixels(native) == list(PIXELS)
    assert _findings(native, other) == (CONFLICTING,)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_the_same_bytes_in_another_byte_order_conflict():
    # An OW value is words in the byte order of the transfer syntax (PS3.5
    # Section 7.3), so the bytes 01 00 are pixels of 1 in Explicit VR Little
    # Endian and of 256 in Explicit VR Big Endian.
    def image(transfer_syntax):
        dataset = _image()
        dataset.PixelData = b"\x01\x00" * len(PIXELS)
        return synthetic.written(dataset, transfer_syntax)

    little = image(EXPLICIT_VR)
    big = image(EXPLICIT_VR_BIG_ENDIAN)

    assert synthetic.read(little).PixelData == synthetic.read(big).PixelData
    assert _pixels(little) == [1] * len(PIXELS)
    assert _pixels(big) == [256] * len(PIXELS)
    assert _findings(little, big) == (CONFLICTING,)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_8_bit_pixel_data_in_implicit_and_explicit_vr_conflicts():
    # Implicit VR Little Endian holds native Pixel Data as OW, and pydicom
    # writes 8-bit Pixel Data in Explicit VR Little Endian as OB (PS3.5
    # Annex A).
    def image(transfer_syntax):
        dataset = _image()
        dataset.BitsAllocated = dataset.BitsStored = 8
        dataset.HighBit = 7
        dataset.PixelData = bytes(PIXELS)
        return synthetic.written(dataset, transfer_syntax)

    implicit = image(IMPLICIT_VR)
    explicit = image(EXPLICIT_VR)

    assert _pixels(implicit) == _pixels(explicit) == list(PIXELS)
    assert synthetic.read(explicit)["PixelData"].VR == "OB"
    assert _findings(implicit, explicit) == (CONFLICTING,)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_private_number_in_another_vr_with_the_same_bytes_conflicts():
    # Two copies of a CT slice, each written in Explicit VR Little Endian,
    # whose private element under one creator holds the same two bytes,
    # ff ff: -1 as SS in one copy, 65535 as US in the other.
    def ct_slice(vr, value):
        dataset = synthetic.ct_slice(0)
        block = dataset.private_block(0x0009, PRIVATE_CREATOR, create=True)
        block.add_new(0x01, vr, value)
        return synthetic.written(dataset)

    signed = ct_slice("SS", -1)
    unsigned = ct_slice("US", 65535)

    assert struct.pack("<h", -1) == struct.pack("<H", 65535) == b"\xff\xff"
    assert synthetic.read(signed)[0x00091001].VR == "SS"
    assert synthetic.read(unsigned)[0x00091001].VR == "US"
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
    # this element's VR, so pydicom reads it from the Implicit VR copy as UN.
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

    implicit = synthetic.written(ct_slice(), IMPLICIT_VR)
    explicit = synthetic.written(ct_slice(), EXPLICIT_VR)

    assert synthetic.read(implicit)[tag].VR == "UN"
    assert synthetic.read(explicit)[tag].VR == vr
    assert _findings(implicit, explicit) == (CONFLICTING,)
