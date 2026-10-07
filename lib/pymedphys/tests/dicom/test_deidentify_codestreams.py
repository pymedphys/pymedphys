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


"""Cut metadata out of compressed pixel data, without recompressing it.

Every image is synthetic, encoded by ``_synthetic_compressed``; marker
segments are added to its codestreams here.
"""

import io
import struct

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify.codestreams import (
    CodestreamRefused,
    cut_codestream,
    encapsulated,
    without_metadata,
)
from pymedphys._dicom.deidentify.pixel_decoding import decoder_available
from pymedphys._dicom.deidentify.reasons import TransformReason
from pymedphys._dicom.deidentify.source import read_source

from . import _synthetic_compressed as compressed
from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

ROWS, COLUMNS = 5, 7
SENTINEL = b"SENTINEL^TEXT"
LOSSLESS = compressed.JPEG_LOSSLESS_SV1
JPEG_LS = "1.2.840.10008.1.2.4.80"
J2K = "1.2.840.10008.1.2.4.90"
UNPARSABLE = TransformReason.UNPARSABLE_CODESTREAM
UNCUTTABLE = TransformReason.UNCUTTABLE_METADATA


def _segment(marker, payload):
    return struct.pack(">HH", marker, len(payload) + 2) + payload


def _frames(count=1, seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 2**16, size=(count, ROWS, COLUMNS)).astype(np.uint16)


def _lossless(count=1):
    return [compressed.jpeg_lossless(frame) for frame in _frames(count)]


def _after_soi(codestream, *segments):
    return codestream[:2] + b"".join(segments) + codestream[2:]


def _image(codestreams, syntax=LOSSLESS, **image):
    image = {"rows": ROWS, "columns": COLUMNS, **image}
    if len(codestreams) > 1:
        image.setdefault("number_of_frames", len(codestreams))
    return read_source(compressed.ct_image(syntax, codestreams, **image))


def _fragments(value):
    """Return the Basic Offset Table and fragments of a value as pydicom holds it."""
    items, position = [], 0
    while position < len(value):
        assert value[position : position + 4] == b"\xfe\xff\x00\xe0"
        (length,) = struct.unpack_from("<I", value, position + 4)
        items.append(value[position + 8 : position + 8 + length])
        position += 8 + length
    return items[0], items[1:]


def _refused(reason, syntax, frame):
    with pytest.raises(CodestreamRefused) as raised:
        cut_codestream(syntax, frame)
    assert raised.value.reason is reason


COM = _segment(0xFFFE, SENTINEL)
EXIF = _segment(0xFFE1, b"Exif\x00\x00" + SENTINEL)
ICC = _segment(0xFFE2, b"ICC_PROFILE\x00\x01\x01" + SENTINEL)
JUMBF = _segment(0xFFEB, b"JP" + SENTINEL)
JFIF_THUMBNAIL = _segment(
    0xFFE0, b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x01\x01" + b"\x00\x00\x00"
)
JFIF = _segment(0xFFE0, b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00")
ADOBE = _segment(0xFFEE, b"Adobe\x00\x64\x00\x00\x00\x00\x01")
MRFX = _segment(0xFFE8, b"mrfx\x01")


@pytest.mark.parametrize(
    "segment",
    [COM, EXIF, ICC, JUMBF, JFIF_THUMBNAIL, _segment(0xFFEF, SENTINEL)],
    ids=["com", "app1-exif", "app2-icc", "app11-jumbf", "jfif-thumbnail", "app15"],
)
def test_comment_and_application_segments_are_cut_from_jpeg(segment):
    codestream = _lossless()[0]

    assert cut_codestream(LOSSLESS, _after_soi(codestream, segment)) == codestream


def test_segments_are_cut_wherever_they_are_in_a_jpeg_codestream():
    codestream = _lossless()[0]
    scan = codestream.index(b"\xff\xda")
    marked = codestream[:scan] + COM + codestream[scan:-2] + EXIF + b"\xff\xd9"

    assert cut_codestream(LOSSLESS, _after_soi(marked, ICC)) == codestream


@pytest.mark.parametrize("segment", [JFIF, ADOBE], ids=["jfif", "adobe"])
def test_segments_that_only_say_how_to_decode_colour_are_kept(segment):
    codestream = _after_soi(_lossless()[0], segment)

    assert cut_codestream(LOSSLESS, codestream) is None
    assert cut_codestream(LOSSLESS, _after_soi(codestream, COM)) == codestream


@pytest.mark.parametrize(
    "segment",
    [
        _segment(0xFFEE, b"Adobe\x00\x64\x00\x00\x00\x00\x01" + SENTINEL),
        _segment(0xFFE0, b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00" + SENTINEL),
        _segment(0xFFE8, b"mrfx\x01"),
    ],
    ids=["adobe-and-more", "jfif-and-more", "mrfx-outside-jpeg-ls"],
)
def test_a_colour_segment_holding_anything_else_is_cut(segment):
    codestream = _lossless()[0]

    assert cut_codestream(LOSSLESS, _after_soi(codestream, segment)) == codestream


def _jpeg_ls(scan_data):
    """A JPEG-LS codestream that parses, though it does not decode."""
    return (
        b"\xff\xd8"
        + _segment(0xFFF7, struct.pack(">BHHB3B", 8, ROWS, COLUMNS, 1, 1, 0x11, 0))
        + _segment(0xFFDA, bytes([1, 1, 0, 0, 0, 0]))
        + scan_data
        + b"\xff\xd9"
    )


def test_jpeg_ls_scan_data_is_read_with_its_own_bit_stuffing():
    # In JPEG-LS, 0xFF followed by a byte below 0x80 is data (T.87 9.1); in
    # T.81 it is a marker that no frame defines.
    codestream = _jpeg_ls(b"\x12\xff\x7f\x34\xff\xd0\x56")

    assert cut_codestream(JPEG_LS, _after_soi(codestream, COM, MRFX)) == (
        _after_soi(codestream, MRFX)
    )
    _refused(UNPARSABLE, LOSSLESS, codestream)


def test_t81_scan_data_is_read_with_stuffed_bytes_restarts_and_fill():
    codestream = _lossless()[0]
    scan_end = len(codestream) - 2
    # A stuffed 0xFF, a restart marker, and fill bytes before EOI.
    marked = codestream[:scan_end] + b"\xff\x00\xff\xd3\x01\xff\xff" + b"\xff\xd9"

    assert cut_codestream(LOSSLESS, marked) is None
    assert cut_codestream(LOSSLESS, _after_soi(marked, COM)) == marked


@pytest.mark.parametrize(
    "frame",
    [
        lambda c: c + b"\x00\x00",
        lambda c: c + b"\x01",
        lambda c: c + SENTINEL,
        lambda c: c + c,
        lambda c: c[:-2],
        lambda c: c[2:],
        lambda c: _after_soi(c, _segment(0xFFC8, b"")),
        lambda c: _after_soi(c, _segment(0xFFF0, SENTINEL)),
        lambda c: _after_soi(c, _segment(0xFFF7, b"\x08")),
        lambda c: _after_soi(c, b"\xff\xfe\xff\xff"),
        lambda c: _after_soi(c, b"\x00" + COM),
    ],
    ids=[
        "two-padding-bytes",
        "a-padding-byte-not-0",
        "text-after-eoi",
        "a-second-codestream",
        "no-eoi",
        "no-soi",
        "jpg-marker",
        "jpg0-marker",
        "sof55-outside-jpeg-ls",
        "a-segment-past-the-end",
        "a-byte-between-segments",
    ],
)
def test_a_jpeg_frame_with_bytes_outside_its_codestream_is_refused(frame):
    _refused(UNPARSABLE, LOSSLESS, frame(_lossless()[0]))


def test_one_padding_byte_of_0_after_a_codestream_is_kept():
    codestream = _lossless()[0]

    assert cut_codestream(LOSSLESS, codestream + b"\x00") is None
    assert cut_codestream(LOSSLESS, _after_soi(codestream, COM) + b"\x00") == (
        codestream
    )


def _j2k():
    if not decoder_available(J2K):
        pytest.skip("no JPEG 2000 decoder is installed")
    pytest.importorskip("openjpeg")
    rng = np.random.default_rng(1)
    frame = rng.integers(0, 2**12, size=(64, 64)).astype(np.uint16)
    codestream = compressed.jpeg_2000(frame, precision=12)
    return frame, codestream


def _j2k_markers(codestream):
    """Return each marker of a codestream's headers, with where it is."""
    markers, position = [], 2
    while True:
        (marker,) = struct.unpack_from(">H", codestream, position)
        markers.append((marker, position))
        if marker == 0xFF93:  # SOD
            return markers
        (length,) = struct.unpack_from(">H", codestream, position + 2)
        position += 2 + length


def test_a_comment_in_a_jpeg_2000_main_header_is_cut():
    _, codestream = _j2k()
    sot = dict(_j2k_markers(codestream))[0xFF90]
    marked = (
        codestream[:sot] + _segment(0xFF64, b"\x00\x01" + SENTINEL) + (codestream[sot:])
    )

    cut = cut_codestream(J2K, marked)

    assert cut is not None
    assert SENTINEL not in cut
    assert 0xFF64 not in dict(_j2k_markers(cut))


def test_a_comment_in_a_jpeg_2000_tile_part_header_cannot_be_cut():
    _, codestream = _j2k()
    sod = dict(_j2k_markers(codestream))[0xFF93]
    sot = dict(_j2k_markers(codestream))[0xFF90]
    comment = _segment(0xFF64, b"\x00\x01" + SENTINEL)
    marked = bytearray(codestream[:sod] + comment + codestream[sod:])
    (psot,) = struct.unpack_from(">I", marked, sot + 6)
    if psot:
        struct.pack_into(">I", marked, sot + 6, psot + len(comment))

    _refused(UNCUTTABLE, J2K, bytes(marked))


@pytest.mark.parametrize(
    "frame",
    [
        lambda c: b"\x00\x00\x00\x0cjP  \r\n\x87\n" + c,
        lambda c: c + SENTINEL,
        lambda c: c[:-2],
        lambda c: c[:4] + _segment(0xFF54, b"") + c[4:],
    ],
    ids=["jp2-file", "text-after-eoc", "no-eoc", "an-undefined-marker"],
)
def test_a_jpeg_2000_frame_with_bytes_outside_its_codestream_is_refused(frame):
    _, codestream = _j2k()

    _refused(UNPARSABLE, J2K, frame(codestream))


def _rle(frame):
    dataset = synthetic.ct_slice(0)
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows, dataset.Columns = frame.shape
    dataset.BitsAllocated = dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.PixelData = frame.astype("<u2").tobytes()
    dataset = pydicom.dcmread(io.BytesIO(synthetic.written(dataset)))
    dataset.compress(
        pydicom.uid.RLELossless, encoding_plugin="pydicom", generate_instance_uid=False
    )
    return synthetic.written(dataset, pydicom.uid.RLELossless)


def _rle_fragment(data):
    dataset = pydicom.dcmread(io.BytesIO(data))
    return next(pydicom.encaps.generate_frames(dataset.PixelData, number_of_frames=1))


def _with_rle_fragment(data, fragment):
    dataset = pydicom.dcmread(io.BytesIO(data))
    dataset.PixelData = pydicom.encaps.encapsulate([fragment])
    return read_source(synthetic.written(dataset, pydicom.uid.RLELossless))


def test_an_rle_lossless_frame_is_parsed_and_kept():
    assert without_metadata(read_source(_rle(_frames()[0]))) is None


@pytest.mark.parametrize(
    "change",
    [
        lambda f: f + SENTINEL + b"\x00",
        lambda f: f[:-2],
        lambda f: struct.pack("<I", 1) + f[4:],
        lambda f: f[:4] + struct.pack("<I", 66) + f[8:],
        lambda f: f[:12] + struct.pack("<I", 70) + f[16:],
    ],
    ids=[
        "text-after-a-segment",
        "a-segment-cut-short",
        "a-segment-too-few",
        "a-first-offset-not-64",
        "an-unused-offset-not-0",
    ],
)
def test_an_rle_lossless_frame_with_bytes_it_does_not_decode_is_refused(change):
    data = _rle(_frames()[0])
    fragment = _rle_fragment(data)

    with pytest.raises(CodestreamRefused) as raised:
        without_metadata(_with_rle_fragment(data, change(fragment)))
    assert raised.value.reason is UNPARSABLE


def test_nothing_to_cut_keeps_the_pixel_data():
    assert without_metadata(_image(_lossless(3))) is None


def test_native_pixel_data_have_no_codestreams():
    assert (
        without_metadata(read_source(synthetic.written(synthetic.ct_slice(0)))) is None
    )


@pytest.mark.parametrize("with_offsets", [False, True])
def test_cut_frames_are_written_one_fragment_each(with_offsets):
    codestreams = _lossless(3)
    marked = [_after_soi(c, COM) for c in codestreams]
    offsets = compressed.frame_starts(marked) if with_offsets else ()

    value = without_metadata(_image(marked, offsets=offsets))

    assert value == encapsulated(codestreams, with_offsets=with_offsets)
    table, fragments = _fragments(value)
    assert bool(table) is with_offsets
    assert [f.rstrip(b"\x00") for f in fragments] == [
        c.rstrip(b"\x00") for c in codestreams
    ]
    assert SENTINEL not in value


def test_frames_split_across_fragments_without_an_offset_table_are_found():
    codestreams = _lossless(2)
    first = _after_soi(codestreams[0], COM)
    first += b"\x00" * (len(first) % 2)
    middle = len(first) // 2
    middle -= middle % 2
    source = read_source(
        compressed.ct_image(
            LOSSLESS,
            [first[:middle], first[middle:], codestreams[1]],
            rows=ROWS,
            columns=COLUMNS,
            number_of_frames=2,
        )
    )

    _, fragments = _fragments(without_metadata(source))

    assert [f.rstrip(b"\x00") for f in fragments] == [
        c.rstrip(b"\x00") for c in codestreams
    ]


def test_a_single_frame_holding_two_codestreams_is_refused():
    # pydicom decodes the first and ignores the second (measured 7 October
    # 2026), so the second could carry anything.
    codestream = _lossless()[0]
    hidden = _after_soi(codestream, COM)
    source = read_source(
        compressed.ct_image(
            LOSSLESS,
            [codestream, hidden],
            rows=ROWS,
            columns=COLUMNS,
        )
    )

    with pytest.raises(CodestreamRefused) as raised:
        without_metadata(source)
    assert raised.value.reason is UNPARSABLE


def test_a_cut_with_an_extended_offset_table_cannot_be_written():
    marked = [_after_soi(c, COM) for c in _lossless(2)]
    lengths = [len(c) + len(c) % 2 for c in marked]
    source = _image(marked, extended=(compressed.frame_starts(marked), lengths))

    with pytest.raises(CodestreamRefused) as raised:
        without_metadata(source)
    assert raised.value.reason is UNCUTTABLE


def test_the_refusal_names_a_reason_and_nothing_else():
    error = CodestreamRefused(UNPARSABLE)

    assert str(error) == "unparsable-codestream"
    assert error.__cause__ is None
