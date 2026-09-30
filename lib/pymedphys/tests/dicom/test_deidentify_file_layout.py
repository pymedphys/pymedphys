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

"""The layout of a written DICOM file, read independently of pydicom."""

import io
import mmap
import struct
import subprocess
import sys

from pymedphys._imports import hypothesis, pydicom, pytest

from pymedphys._dicom.deidentify import file_layout, standard, uid_registry
from pymedphys._dicom.deidentify.file_layout import (
    ElementPath,
    Location,
    Region,
    Span,
    read_file_layout,
)

st = hypothesis.strategies

UNDEFINED = 0xFFFFFFFF
# The VRs of PS3.5 Table 7.1-2, whose explicit VR header is 8 bytes with a
# 16-bit length. Every other VR has the 12-byte header of Table 7.1-1.
TABLE_7_1_2 = frozenset(
    "AE AS AT CS DA DS DT FL FD IS LO LT PN SH SL SS ST TM UI UL US".split()
)
EXPLICIT = "1.2.840.10008.1.2.1"
IMPLICIT = "1.2.840.10008.1.2"
RLE_LOSSLESS = "1.2.840.10008.1.2.5"
# Invented values, distinctive enough to notice in a repr.
NAME = b"ZEBEDEE^QUILLON "
PATIENT_ID = b"ZQ7741093 "


def _explicit(tag, vr, value=b"", length=None):
    """An explicit VR element with the header of PS3.5 Table 7.1-1 or 7.1-2."""
    group, element = divmod(tag, 0x10000)
    length = len(value) if length is None else length
    if vr in TABLE_7_1_2:
        return struct.pack("<HH2sH", group, element, vr.encode(), length) + value
    return struct.pack("<HH2sHI", group, element, vr.encode(), 0, length) + value


def _implicit(tag, value=b"", length=None):
    """An implicit VR element with the header of PS3.5 Table 7.1-3."""
    group, element = divmod(tag, 0x10000)
    length = len(value) if length is None else length
    return struct.pack("<HHI", group, element, length) + value


def _item(content=b"", length=None):
    """An Item (FFFE,E000) of PS3.5 Section 7.5.1."""
    return _implicit(0xFFFEE000, content, length)


ITEM_END = _implicit(0xFFFEE00D)
SEQUENCE_END = _implicit(0xFFFEE0DD)


def _file(transfer_syntax, data_set=b""):
    """A zeroed preamble, the prefix, File Meta Information, and ``data_set``."""
    uid = transfer_syntax.encode()
    uid += b"\x00" * (len(uid) % 2)  # PS3.5 Section 9.1
    return (
        bytes(128)
        + b"DICM"
        + _explicit(0x00020001, "OB", b"\x00\x01")
        + _explicit(0x00020010, "UI", uid)
        + data_set
    )


# Each offset is worked out by hand from the header sizes of PS3.5 Tables
# 7.1-1, 7.1-2, and 7.1-3 and Section 7.5.
HAND_BUILT = _file(
    RLE_LOSSLESS,  # the prefix at 128, File Meta Information at 132 and 146
    _explicit(0x00100010, "PN", NAME)  # 174: 8 + 16
    + _explicit(0x300A00B0, "SQ", length=UNDEFINED)  # 198: 12
    + _item(length=UNDEFINED)  # 210: 8
    + _explicit(0x300A00C2, "LO", b"ARC1")  # 218: 8 + 4
    + ITEM_END  # 230: 8
    + _item(_explicit(0x300A00C0, "IS", b"2 "))  # 238: 8, then 246: 8 + 2
    + SEQUENCE_END  # 256: 8
    + _explicit(0x7FE00010, "OB", length=UNDEFINED)  # 264: 12
    + _item()  # 276: 8, an empty Basic Offset Table
    + _item(b"\x00\x01\x02\x03")  # 284: 8 + 4, a fragment
    + SEQUENCE_END  # 296: 8
    + _explicit(0xFFFCFFFC, "OB", bytes(4)),  # 304: 12 + 4, to 320
)
SEQUENCE = "data set element (300A,00B0) (SQ)"
PIXEL_DATA = "data set element (7FE0,0010) (OB)"
HAND_BUILT_SPANS = [
    (0, 128, None, "the preamble"),
    (128, 132, None, "the DICM prefix"),
    (132, 146, 144, "File Meta Information element (0002,0001) (OB)"),
    (146, 174, 154, "File Meta Information element (0002,0010) (UI)"),
    (174, 198, 182, "data set element (0010,0010) (PN)"),
    (198, 210, None, SEQUENCE),
    (210, 218, None, SEQUENCE),
    (218, 230, 226, "data set element (300A,00B0)[0] > (300A,00C2) (LO)"),
    (230, 238, None, SEQUENCE),
    (238, 246, None, SEQUENCE),
    (246, 256, 254, "data set element (300A,00B0)[1] > (300A,00C0) (IS)"),
    (256, 264, None, SEQUENCE),
    (264, 276, None, PIXEL_DATA),
    (276, 284, 284, "item 0 of " + PIXEL_DATA),
    (284, 296, 292, "item 1 of " + PIXEL_DATA),
    (296, 304, None, PIXEL_DATA),
    (304, 320, 316, "Data Set Trailing Padding (FFFC,FFFC)"),
]
# Where the prefix and each element outside a sequence end.
HAND_BUILT_BOUNDARIES = {132, 146, 174, 198, 264, 304, 320}


def _assert_partition(layout, size):
    assert layout.size == size
    end = 0
    for span in layout.spans:
        assert span.start == end < span.end
        assert span.value_start is None or span.start <= span.value_start <= span.end
        end = span.end
    assert end == size


def _described(layout):
    return [(s.start, s.end, s.value_start, str(s.location)) for s in layout.spans]


def _values(layout, data):
    """Each element value of defined length, by its path."""
    return {
        str(span.location.element): bytes(data[span.value_start : span.end])
        for span in layout.spans
        if span.value_start is not None
        and span.location.region in (Region.DATA_SET, Region.TRAILING_PADDING)
        and span.location.item is None
    }


def _write(dataset, transfer_syntax, **file_meta):
    dataset.SOPClassUID = pydicom.uid.RTPlanStorage
    dataset.SOPInstanceUID = "1.2.3.4"  # invented
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = transfer_syntax
    for keyword, value in file_meta.items():
        setattr(dataset.file_meta, keyword, value)
    written = io.BytesIO()
    pydicom.dcmwrite(written, dataset, enforce_file_format=True)
    return written.getvalue()


def _plan(undefined_lengths):
    """A synthetic data set with nested sequences, an empty item, and private data."""
    dataset = pydicom.Dataset()
    dataset.PatientName = NAME.decode().strip()
    dataset.PatientID = PATIENT_ID.decode().strip()
    dataset.PatientBirthDate = "19710203"
    control_point = pydicom.Dataset()
    control_point.ControlPointIndex = 0
    control_point.GantryAngle = "180"
    beam = pydicom.Dataset()
    beam.BeamName = "ARC1"
    beam.BeamNumber = 1
    beam.ControlPointSequence = [control_point, pydicom.Dataset()]
    dataset.BeamSequence = [beam, pydicom.Dataset()]
    dataset.add_new(0x00190010, "LO", "SYNTHETIC CREATOR")
    dataset.add_new(0x00191010, "LO", "SYNTHETIC")
    dataset.PixelData = bytes(range(16))
    dataset["PixelData"].VR = "OW"
    dataset.DataSetTrailingPadding = bytes(8)
    if undefined_lengths:
        for sequence in (dataset["BeamSequence"], beam["ControlPointSequence"]):
            sequence.is_undefined_length = True
            for item in sequence.value:
                item.is_undefined_length_sequence_item = True
    return dataset


def _pydicom_values(data):
    """Each element value, by its path, as pydicom reads the file."""
    found = {}

    def walk(dataset, items):
        for tag in list(dataset.keys()):
            raw = dataset.get_item(tag)
            path = ElementPath(items, f"({tag.group:04X},{tag.element:04X})")
            if dataset[tag].VR == "SQ":
                for index, item in enumerate(dataset[tag].value):
                    walk(item, (*items, (path.tag, index)))
            else:
                found[str(path)] = raw.value

    walk(pydicom.dcmread(io.BytesIO(data)), ())
    return found


ENCODINGS = [
    pytest.param(syntax, undefined, id=f"{name}-{lengths}")
    for syntax, name in ((EXPLICIT, "explicit"), (IMPLICIT, "implicit"))
    for undefined, lengths in ((False, "defined"), (True, "undefined"))
]


def test_offsets_follow_the_header_sizes_of_ps3_5():
    layout = read_file_layout(HAND_BUILT)

    assert _described(layout) == HAND_BUILT_SPANS
    assert layout.size == len(HAND_BUILT) == 320
    assert layout.readable
    # Without the NUL that pads it to an even length.
    assert layout.transfer_syntax == RLE_LOSSLESS


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize("transfer_syntax, undefined_lengths", ENCODINGS)
def test_the_spans_partition_the_file_as_pydicom_reads_it(
    transfer_syntax, undefined_lengths
):
    data = _write(_plan(undefined_lengths), transfer_syntax)

    layout = read_file_layout(data)

    _assert_partition(layout, len(data))
    assert layout.readable
    assert layout.transfer_syntax == transfer_syntax
    # Every path, and the value at each value_start.
    assert _values(layout, data) == _pydicom_values(data)
    file_meta = {
        str(span.location.element)
        for span in layout.spans
        if span.location.region is Region.FILE_META and span.location.element
    }
    read = pydicom.dcmread(io.BytesIO(data))
    assert file_meta == {
        f"({t.group:04X},{t.element:04X})" for t in read.file_meta.keys()
    }


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_each_vr_has_the_header_size_of_ps3_5_table_7_1_1_or_7_1_2():
    values = {
        "AE": "SYNAE", "AS": "042Y", "AT": 0x00100010, "CS": "SYN",
        "DA": "19710203", "DS": "1.5", "DT": "19710203120000", "FD": 2.5,
        "FL": 1.5, "IS": "7", "LO": "SYNTHETIC", "LT": "text", "OB": b"\x01\x02",
        "OD": bytes(8), "OF": bytes(4), "OL": bytes(4), "OV": bytes(8),
        "OW": b"\x00\x01", "PN": "SYN^THETIC", "SH": "SYN", "SL": -1, "SS": -2,
        "ST": "text", "SV": -3, "TM": "120000", "UC": "unlimited", "UI": "1.2.3",
        "UL": 4, "UN": b"\x00\x01", "UR": "urn:x", "US": 5, "UT": "text", "UV": 6,
    }  # fmt: skip
    assert set(values) == standard.VRS - {"SQ"}
    dataset = pydicom.Dataset()
    dataset.add_new(0x00110010, "LO", "SYNTHETIC VRS")
    for offset, (vr, value) in enumerate(sorted(values.items())):
        dataset.add_new(0x00111000 + offset, vr, value)
    data = _write(dataset, EXPLICIT)
    read = pydicom.dcmread(io.BytesIO(data))

    layout = read_file_layout(data)

    checked = set()
    for span in layout.spans:
        path = span.location.element
        if path is None or not path.tag.startswith("(0011,1"):
            continue
        raw = read.get_item(int(path.tag[1:5] + path.tag[6:10], 16))
        assert span.location.vr == raw.VR
        assert span.value_start == raw.value_tell
        assert span.value_start - span.start == (8 if raw.VR in TABLE_7_1_2 else 12)
        checked.add(raw.VR)
    assert checked == set(values)


def test_a_truncated_file_is_read_up_to_where_it_stops():
    full = read_file_layout(HAND_BUILT).spans

    for size in range(len(HAND_BUILT) + 1):
        layout = read_file_layout(HAND_BUILT[:size])

        _assert_partition(layout, size)
        assert layout.readable == (size in HAND_BUILT_BOUNDARIES), size
        located = [s for s in layout.spans if s.location.region is not Region.TRAILING]
        if size < 132:
            assert not located
            continue
        # What was read is what the whole file gives, and trailing bytes can
        # only follow it.
        assert located == list(full[: len(located)])
        assert layout.spans[len(located) :] in (
            (),
            (Span(located[-1].end, size, None, Location(Region.TRAILING)),),
        )
        assert located[-1].end >= max(b for b in HAND_BUILT_BOUNDARIES if b <= size)


@hypothesis.given(
    changes=st.lists(
        st.tuples(st.integers(0, len(HAND_BUILT) - 1), st.integers(0, 255)),
        max_size=4,
    )
)
def test_a_corrupted_file_is_still_mapped_byte_for_byte(changes):
    data = bytearray(HAND_BUILT)
    for offset, value in changes:
        data[offset] = value

    layout = read_file_layout(bytes(data))

    _assert_partition(layout, len(data))
    trailing = tuple(s for s in layout.spans if s.location.region is Region.TRAILING)
    assert trailing in ((), layout.spans[-1:])
    assert not (layout.readable and trailing)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_the_preamble_file_meta_padding_and_appended_bytes_are_labelled():
    dataset = pydicom.Dataset()
    dataset.preamble = b"SYNTHETIC PREAMBLE".ljust(128, b"\x00")
    dataset.DataSetTrailingPadding = bytes(8)
    written = _write(dataset, EXPLICIT, SourceApplicationEntityTitle="SYNTHETIC_AE")
    data = written + b"APPENDED"

    layout = read_file_layout(data)

    assert str(layout.locate(0)) == str(layout.locate(127)) == "the preamble"
    assert str(layout.locate(128)) == str(layout.locate(131)) == "the DICM prefix"
    assert str(layout.locate(data.index(b"SYNTHETIC_AE"))) == (
        "File Meta Information element (0002,0016) (AE)"
    )
    assert str(layout.locate(len(data) - 9)) == "Data Set Trailing Padding (FFFC,FFFC)"
    assert layout.locate(len(data) - 9).region is Region.TRAILING_PADDING
    assert layout.spans[-1] == Span(
        len(data) - 8, len(data), None, Location(Region.TRAILING)
    )
    assert str(layout.locate(len(data) - 1)) == "bytes after the last readable element"
    assert not layout.readable


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize("undefined_length", [False, True])
def test_a_private_sequence_in_implicit_vr_is_found_through_its_items(
    undefined_length,
):
    item = pydicom.Dataset()
    item.PatientID = PATIENT_ID.decode().strip()
    dataset = pydicom.Dataset()
    dataset.PatientName = NAME.decode().strip()
    dataset.add_new(0x00190010, "LO", "SYNTHETIC CREATOR")
    dataset.add_new(0x00191001, "SQ", [item])
    dataset[0x00191001].is_undefined_length = undefined_length
    data = _write(dataset, IMPLICIT)

    layout = read_file_layout(data)

    assert layout.readable
    assert _values(layout, data)["(0019,1001)[0] > (0010,0020)"] == PATIENT_ID
    described = {str(s.location) for s in layout.spans}
    # Implicit VR gives each standard attribute its VR from PS3.6.
    assert "data set element (0010,0010) (PN)" in described
    assert "data set element (0019,1001)[0] > (0010,0020) (LO)" in described
    assert "data set element (0019,1001)" in described


def test_a_un_value_of_undefined_length_is_read_as_implicit_vr_items():
    data = _file(
        EXPLICIT,
        _explicit(0x00190010, "LO", b"SYNTHETIC ")
        + _explicit(0x00191001, "UN", length=UNDEFINED)
        + _item(length=UNDEFINED)
        + _implicit(0x00100020, PATIENT_ID)
        + ITEM_END
        + SEQUENCE_END,
    )

    layout = read_file_layout(data)

    un = "data set element (0019,1001) (UN)"
    assert layout.readable
    assert [d for _, _, _, d in _described(layout)[4:]] == [
        "data set element (0019,0010) (LO)",
        un,
        un,
        "data set element (0019,1001)[0] > (0010,0020) (LO)",
        un,
        un,
    ]
    assert _values(layout, data)["(0019,1001)[0] > (0010,0020)"] == PATIENT_ID


def test_a_standard_sequence_written_as_un_has_its_dictionary_vr():
    data = _file(
        EXPLICIT,
        _explicit(0x300A00B0, "UN", _item(_implicit(0x300A00C2, b"ARC1"))),
    )

    layout = read_file_layout(data)

    assert layout.readable
    assert [d for _, _, _, d in _described(layout)[4:]] == [
        SEQUENCE,
        SEQUENCE,
        "data set element (300A,00B0)[0] > (300A,00C2) (LO)",
    ]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_item(_implicit(0x00100020, PATIENT_ID)) + b"\x01\x02", id="more"),
        pytest.param(_item(length=8) + bytes(4), id="item-past-the-end"),
        pytest.param(_item(b"\x01\x02\x03\x04"), id="not-a-data-set"),
    ],
)
def test_a_un_value_whose_items_do_not_fill_it_is_one_value(value):
    data = _file(EXPLICIT, _explicit(0x00191001, "UN", value))

    layout = read_file_layout(data)

    assert layout.readable
    assert _described(layout)[4:] == [
        (174, len(data), 186, "data set element (0019,1001) (UN)")
    ]


def test_an_empty_value_is_not_read_as_items_from_the_bytes_after_it():
    # The empty private element ends item 0, so item 1's tag follows it.
    items = _item(_implicit(0x00191002)) + _item(_implicit(0x00100020, PATIENT_ID))
    data = _file(
        IMPLICIT,
        _implicit(0x00190010, b"SYNTHETIC ") + _implicit(0x00191001, items),
    )

    layout = read_file_layout(data)

    path = "(0019,1001)[0] > (0019,1002)"
    (empty,) = [s for s in layout.spans if str(s.location.element) == path]
    assert empty.value_start == empty.end == empty.start + 8
    assert _values(layout, data)["(0019,1001)[1] > (0010,0020)"] == PATIENT_ID
    assert layout.readable


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_contour_data_that_pydicom_writes_as_un_has_its_dictionary_vr():
    contour = pydicom.Dataset()
    contour.ContourData = ["1.5"] * 30000  # 119,999 characters, over 64 KiB
    roi = pydicom.Dataset()
    roi.ContourSequence = [contour]
    dataset = pydicom.Dataset()
    dataset.ROIContourSequence = [roi]
    with pytest.warns(UserWarning, match="64 kByte"):
        data = _write(dataset, EXPLICIT)

    layout = read_file_layout(data)

    path = "(3006,0039)[0] > (3006,0040)[0] > (3006,0050)"
    (span,) = [s for s in layout.spans if str(s.location.element) == path]
    assert data[span.start + 4 : span.start + 6] == b"UN"
    assert span.location.vr == "DS"
    assert bytes(data[span.value_start : span.end]).rstrip() == b"\\".join(
        [b"1.5"] * 30000
    )


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_encapsulated_fragments_are_numbered_from_the_basic_offset_table():
    from pydicom.encaps import encapsulate

    # Each of even length, which pydicom would otherwise pad.
    frames = [b"\xff\xd8SYNTHETIC ONE.\xff\xd9", b"\xff\xd8SYNTHETIC TWO.\xff\xd9"]
    dataset = pydicom.Dataset()
    dataset.PixelData = encapsulate(frames)
    dataset["PixelData"].VR = "OB"
    data = _write(dataset, pydicom.uid.JPEGBaseline8Bit)

    layout = read_file_layout(data)

    fragments = [
        (span.location.item, bytes(data[span.value_start : span.end]))
        for span in layout.spans
        if span.location.item is not None
    ]
    assert [item for item, _ in fragments] == [0, 1, 2]
    assert fragments[1:] == [(1, frames[0]), (2, frames[1])]
    assert layout.readable


def test_deflated_image_frames_leave_the_data_set_readable():
    # PS3.5 Section A.4.13 deflates each frame, not the data set.
    data = _file("1.2.840.10008.1.2.8.1", _explicit(0x00100010, "PN", NAME))

    layout = read_file_layout(data)

    assert layout.readable
    assert str(layout.spans[-1].location) == "data set element (0010,0010) (PN)"


@pytest.mark.parametrize(
    "transfer_syntax",
    [
        "1.2.840.10008.1.2.1.99",  # PS3.5 Section A.5
        "1.2.840.10008.1.2.4.95",  # Section A.7
        "1.2.840.10008.1.2.4.205",  # Section A.12
    ],
)
def test_a_deflated_data_set_is_refused(transfer_syntax):
    with pytest.raises(ValueError, match="deflated"):
        read_file_layout(_file(transfer_syntax, bytes(8)))


def test_transfer_syntaxes_are_classified_as_ps3_6_names_them():
    rows = uid_registry.load_uid_values().rows
    syntaxes = [row for row in rows if row.uid_type == "Transfer Syntax"]

    def named(text):
        return frozenset(row.uid for row in syntaxes if text in row.name)

    assert file_layout.IMPLICIT_VR_TRANSFER_SYNTAXES == named("Implicit VR")
    assert file_layout.BIG_ENDIAN_TRANSFER_SYNTAXES == named("Big Endian")
    assert file_layout.DEFLATED_TRANSFER_SYNTAXES == named("Deflate") - {
        "1.2.840.10008.1.2.8.1"  # Deflated Image Frame Compression
    }


def test_a_big_endian_data_set_is_left_trailing():
    big_endian = "1.2.840.10008.1.2.2"
    # An empty Specific Character Set, which would also read as little endian.
    data_set = struct.pack(">HH2sH", 0x08, 0x05, b"CS", 0)
    data = _file(
        big_endian, data_set + struct.pack(">HH2sH", 0x10, 0x10, b"PN", 16) + NAME
    )

    layout = read_file_layout(data)

    assert layout.transfer_syntax == big_endian
    assert _described(layout)[2:] == [
        (132, 146, 144, "File Meta Information element (0002,0001) (OB)"),
        (146, 174, 154, "File Meta Information element (0002,0010) (UI)"),
        (174, len(data), None, "bytes after the last readable element"),
    ]
    assert not layout.readable


def test_without_a_transfer_syntax_the_data_set_is_left_trailing():
    data = (
        bytes(128)
        + b"DICM"
        + _explicit(0x00020001, "OB", b"\x00\x01")
        + _explicit(0x00100010, "PN", NAME)
    )

    layout = read_file_layout(data)

    assert layout.transfer_syntax is None
    assert layout.spans[-1] == Span(146, len(data), None, Location(Region.TRAILING))
    assert not layout.readable


def test_the_file_meta_group_length_is_not_trusted():
    # (0002,0000) claims that the group ends after (0002,0001).
    data = (
        bytes(128)
        + b"DICM"
        + _explicit(0x00020000, "UL", struct.pack("<I", 14))
        + _file(EXPLICIT, _explicit(0x00100010, "PN", NAME))[132:]
    )

    layout = read_file_layout(data)

    assert layout.readable
    assert [d for _, _, _, d in _described(layout)[2:]] == [
        "File Meta Information element (0002,0000) (UL)",
        "File Meta Information element (0002,0001) (OB)",
        "File Meta Information element (0002,0010) (UI)",
        "data set element (0010,0010) (PN)",
    ]


@pytest.mark.parametrize(
    "data",
    [
        b"",
        bytes(131),
        bytes(128) + b"dicm" + bytes(20),
        _file(EXPLICIT)[:131],
        _file(EXPLICIT)[4:],
    ],
)
def test_without_the_dicm_prefix_every_byte_is_trailing(data):
    layout = read_file_layout(data)

    expected = (Span(0, len(data), None, Location(Region.TRAILING)),) if data else ()
    assert layout.spans == expected
    assert layout.transfer_syntax is None
    assert not layout.readable


MALFORMED = {
    "an unknown VR": (_explicit(0x00100010, "ZZ", b"ABCD"), 174),
    "an item where an element belongs": (_item(), 174),
    "an item delimiter where an element belongs": (ITEM_END, 174),
    "a length past the end of the file": (
        _explicit(0x00100010, "PN", NAME, length=100),
        174,
    ),
    # The element at 194 claims 6 bytes, but its item holds only 2 more.
    "a length past the end of its item": (
        _explicit(0x300A00B0, "SQ", _item(_explicit(0x300A00C2, "LO", b"AR", 6)))
        + _explicit(0x7FE00010, "OB", bytes(8)),
        194,
    ),
    "an item past the end of its sequence": (
        _explicit(0x300A00B0, "SQ", _item(length=4))
        + _explicit(0x7FE00010, "OB", bytes(8)),
        186,
    ),
    # PS3.5 Section 7.5.1 gives an item of defined length no delimiter.
    "an item delimiter in an item of defined length": (
        _explicit(
            0x300A00B0, "SQ", _item(_explicit(0x300A00C2, "LO", b"ARC1") + ITEM_END)
        )
        + _explicit(0x7FE00010, "OB", bytes(8)),
        206,
    ),
    "a sequence delimiter in a sequence of defined length": (
        _explicit(0x300A00B0, "SQ", SEQUENCE_END)
        + _explicit(0x7FE00010, "OB", bytes(8)),
        186,
    ),
    "a fragment of undefined length": (
        _explicit(0x7FE00010, "OB", length=UNDEFINED) + _item(length=UNDEFINED),
        186,
    ),
}


@pytest.mark.parametrize("data_set, stop", MALFORMED.values(), ids=MALFORMED)
def test_reading_stops_at_the_first_unreadable_structure(data_set, stop):
    data = _file(EXPLICIT, data_set)

    layout = read_file_layout(data)

    _assert_partition(layout, len(data))
    assert layout.spans[-1] == Span(stop, len(data), None, Location(Region.TRAILING))
    assert not layout.readable


def test_an_item_where_an_element_belongs_ends_reading_in_implicit_vr():
    # In explicit VR the item's length would also fail as a VR; here only the
    # tag shows that this is not an element.
    data = _file(IMPLICIT, _item(_implicit(0x00100020, PATIENT_ID)))

    layout = read_file_layout(data)

    # The File Meta Information ends at 172, as the UID is 18 bytes with its NUL.
    assert layout.spans[-1] == Span(172, len(data), None, Location(Region.TRAILING))
    assert not layout.readable


def test_padding_inside_an_item_is_a_data_set_element():
    # PS3.10 Section 7.2 allows Data Set Trailing Padding in nested data sets.
    data = _file(
        EXPLICIT,
        _explicit(0x300A00B0, "SQ", _item(_explicit(0xFFFCFFFC, "OB", bytes(4)))),
    )

    layout = read_file_layout(data)

    assert layout.readable
    assert layout.spans[-1].location == Location(
        Region.DATA_SET, ElementPath((("(300A,00B0)", 0),), "(FFFC,FFFC)"), "OB"
    )


def test_a_vr_that_differs_from_ps3_6_is_read_as_written():
    # PS3.6 gives Beam Sequence VR SQ.
    data = _file(EXPLICIT, _explicit(0x300A00B0, "OB", _item()))

    layout = read_file_layout(data)

    assert layout.readable
    assert _described(layout)[4:] == [
        (174, len(data), 186, "data set element (300A,00B0) (OB)")
    ]


def test_a_repeating_group_in_implicit_vr_has_its_dictionary_vr():
    # Overlay Rows (60xx,0010) is US in PS3.6. Group 6001 is private, not an
    # overlay group (PS3.5 Section 7.6).
    data = _file(
        IMPLICIT,
        _implicit(0x60010010, b"SYNTHETIC ") + _implicit(0x60020010, b"\x00\x02"),
    )

    layout = read_file_layout(data)

    assert [d for _, _, _, d in _described(layout)[4:]] == [
        "data set element (6001,0010)",
        "data set element (6002,0010) (US)",
    ]


def _nested(depth):
    """An element nested in ``depth`` items of Content Sequence (0040,A730)."""
    element = _explicit(0x00100020, "LO", PATIENT_ID)
    for _ in range(depth):
        element = _explicit(0x0040A730, "SQ", _item(element))
    return element


def test_elements_nested_in_up_to_32_items_are_read():
    layout = read_file_layout(_file(EXPLICIT, _nested(32)))

    assert layout.readable
    assert file_layout.MAX_NESTING == 32
    assert max(len(s.location.element.items) for s in layout.spans[2:]) == 32


@pytest.mark.parametrize("depth", [33, 1000])
def test_deeper_nesting_is_left_trailing(depth):
    layout = read_file_layout(_file(EXPLICIT, _nested(depth)))

    *located, trailing = layout.spans
    assert trailing.location == Location(Region.TRAILING)
    assert located[-1].location == Location(
        Region.DATA_SET, ElementPath((("(0040,A730)", 0),) * 32, "(0040,A730)"), "SQ"
    )
    assert not layout.readable


def test_bytes_bytearray_memoryview_and_mmap_give_the_same_layout(tmp_path):
    expected = read_file_layout(HAND_BUILT)
    path = tmp_path / "hand-built.dcm"
    path.write_bytes(HAND_BUILT)

    with path.open("rb") as file:
        mapped = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
        assert read_file_layout(mapped) == expected
        # Closing fails if the reader still holds a view of the file.
        mapped.close()
    assert read_file_layout(bytearray(HAND_BUILT)) == expected
    assert read_file_layout(memoryview(HAND_BUILT)) == expected


def test_locate_finds_the_location_of_each_byte():
    layout = read_file_layout(HAND_BUILT)

    for span in layout.spans:
        for offset in range(span.start, span.end):
            assert layout.locate(offset) == span.location


@pytest.mark.parametrize("offset", [-1, len(HAND_BUILT)])
def test_locate_rejects_an_offset_outside_the_file(offset):
    with pytest.raises(ValueError, match="outside the file"):
        read_file_layout(HAND_BUILT).locate(offset)


def test_reprs_quote_no_values():
    layout = read_file_layout(HAND_BUILT)

    text = repr(layout) + "".join(repr(s) + str(s.location) for s in layout.spans)

    assert "ZEBEDEE" not in text
    assert "ARC1" not in text
    assert RLE_LOSSLESS not in text


def test_an_element_path_reads_outermost_first():
    path = ElementPath((("(300A,00B0)", 1), ("(300A,0111)", 0)), "(300A,011E)")

    assert str(path) == "(300A,00B0)[1] > (300A,0111)[0] > (300A,011E)"
    assert str(ElementPath((), "(0010,0010)")) == "(0010,0010)"


@pytest.mark.parametrize(
    "items, tag",
    [
        ((), "(300a,00c3)"),
        ((), "300A,00C3"),
        ((), "(300A,00C3) "),
        ((("(300A,00B0)", -1),), "(300A,00C3)"),
        ((("(300A,00B0)", True),), "(300A,00C3)"),
        ((("(300A,00B0)", 0.0),), "(300A,00C3)"),
        ((("300A00B0", 0),), "(300A,00C3)"),
        ((("(300A,00B0)",),), "(300A,00C3)"),
        ([("(300A,00B0)", 0)], "(300A,00C3)"),
    ],
)
def test_an_invalid_element_path_is_rejected(items, tag):
    with pytest.raises(ValueError):
        ElementPath(items, tag)


def test_the_reader_does_not_import_pydicom(tmp_path):
    # Implicit VR, so the reader also loads the PS3.6 data dictionary.
    path = tmp_path / "implicit.dcm"
    path.write_bytes(_file(IMPLICIT, _implicit(0x00100010, NAME)))
    code = (
        "import pathlib, sys\n"
        "from pymedphys._dicom.deidentify.file_layout import read_file_layout\n"
        "layout = read_file_layout(pathlib.Path(sys.argv[1]).read_bytes())\n"
        "print(layout.readable, 'pydicom' in sys.modules)\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", code, str(path)],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.split() == ["True", "False"]
