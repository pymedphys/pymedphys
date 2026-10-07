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

"""Decode every frame of compressed pixel data once before it is released.

Every image is synthetic, encoded by ``_synthetic_compressed``.
"""

import io
import logging
import struct

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import pixel_decoding
from pymedphys._dicom.deidentify.frame_headers import Declared, header_problem
from pymedphys._dicom.deidentify.pixel_decoding import (
    DECODING_PLUGINS,
    decoder_available,
    frames_problem,
)
from pymedphys._dicom.deidentify.reasons import TransformReason
from pymedphys._dicom.deidentify.source import (
    ENCAPSULATED_TRANSFER_SYNTAXES,
    read_source,
)

from . import _synthetic_compressed as compressed
from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

ROWS, COLUMNS = 5, 7
SENTINEL = "SENTINEL^NAME"


def _frames(count, bits=16, seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 2**bits, size=(count, ROWS, COLUMNS)).astype(np.uint16)


def _needs(transfer_syntax):
    if not decoder_available(transfer_syntax):
        pytest.skip(f"no decoder for {transfer_syntax} is installed")


def _lossless(count=1, syntax=compressed.JPEG_LOSSLESS_SV1, **image):
    _needs(syntax)
    predictor = 1 if syntax == compressed.JPEG_LOSSLESS_SV1 else 7
    codestreams = [
        compressed.jpeg_lossless(f, predictor=predictor) for f in _frames(count)
    ]
    image = {"rows": ROWS, "columns": COLUMNS, "name": SENTINEL, **image}
    if count > 1:
        image.setdefault("number_of_frames", count)
    return compressed.ct_image(syntax, codestreams, **image)


def test_each_encapsulated_syntax_has_one_decoder():
    assert set(DECODING_PLUGINS) == ENCAPSULATED_TRANSFER_SYNTAXES
    assert DECODING_PLUGINS[compressed.RLE_LOSSLESS] == "pydicom"
    assert set(DECODING_PLUGINS.values()) == {"gdcm", "pydicom", "pylibjpeg"}
    # JPEG and JPEG-LS by GDCM, not by pylibjpeg-libjpeg, under the GPL.
    assert {
        syntax for syntax, plugin in DECODING_PLUGINS.items() if plugin == "gdcm"
    } == {
        compressed.JPEG_BASELINE,
        compressed.JPEG_EXTENDED,
        compressed.JPEG_LOSSLESS,
        compressed.JPEG_LOSSLESS_SV1,
        compressed.JPEG_LS_LOSSLESS,
        compressed.JPEG_LS_NEAR_LOSSLESS,
    }


def test_with_the_user_extra_every_encapsulated_syntax_has_its_decoder():
    # The ``user`` extra declares python-gdcm, and pylibjpeg with its
    # openjpeg plugin; the ``dicom`` extra alone declares none of them.
    for module in ("gdcm", "pylibjpeg", "openjpeg"):
        pytest.importorskip(module)

    assert all(decoder_available(ts) for ts in ENCAPSULATED_TRANSFER_SYNTAXES)


@pytest.mark.parametrize(
    "transfer_syntax", ["1.2.840.10008.1.2.1", "1.2.840.10008.1.2.4.92", "2.25.1"]
)
def test_a_syntax_without_a_pinned_decoder_has_none(transfer_syntax):
    assert not decoder_available(transfer_syntax)


def test_native_pixel_data_is_not_decoded_here():
    data = synthetic.written(synthetic.ct_slice(0))

    assert frames_problem(read_source(data)) is None


@pytest.mark.parametrize(
    "syntax", [compressed.JPEG_LOSSLESS, compressed.JPEG_LOSSLESS_SV1]
)
@pytest.mark.parametrize("count", [1, 3])
def test_jpeg_lossless_frames_that_match_their_attributes_pass(syntax, count):
    assert frames_problem(read_source(_lossless(count, syntax))) is None


def test_rle_lossless_frames_pass():
    data = compressed.rle_ct_image(_frames(1)[0], name=SENTINEL)

    assert frames_problem(read_source(data)) is None


def test_jpeg_baseline_frames_pass():
    _needs(compressed.JPEG_BASELINE)
    pytest.importorskip("PIL")
    frame = np.arange(256, dtype=np.uint8).reshape(16, 16)
    data = compressed.ct_image(
        compressed.JPEG_BASELINE,
        [compressed.jpeg_baseline(frame)],
        rows=16,
        columns=16,
        bits=8,
    )

    assert frames_problem(read_source(data)) is None


def test_jpeg_2000_frames_pass():
    _needs(compressed.JPEG_2000_LOSSLESS)
    pytest.importorskip("openjpeg")
    frame = np.arange(64 * 64, dtype=np.uint16).reshape(64, 64) % 4096
    data = compressed.ct_image(
        compressed.JPEG_2000_LOSSLESS,
        [compressed.jpeg_2000(frame, precision=12)],
        rows=64,
        columns=64,
        bits=12,
    )

    assert frames_problem(read_source(data)) is None


@pytest.mark.parametrize(
    "count, image",
    [(2, {"number_of_frames": 3}), (3, {"number_of_frames": 2})],
    ids=["fewer-frames", "more-frames"],
)
def test_frames_that_do_not_match_number_of_frames_are_refused(count, image):
    data = _lossless(count, **image)

    assert frames_problem(read_source(data)) in (
        TransformReason.FRAME_MISMATCH,
        TransformReason.UNDECODABLE_PIXEL_DATA,
    )


@pytest.mark.parametrize(
    "image", [{"rows": ROWS + 1}, {"columns": COLUMNS + 1}, {"columns": COLUMNS - 1}]
)
def test_frames_of_another_size_are_refused(image):
    assert frames_problem(read_source(_lossless(**image))) is (
        TransformReason.FRAME_MISMATCH
    )


def test_a_frame_whose_codestream_has_the_rows_and_columns_swapped_is_refused():
    # pydicom shapes the 35 decoded samples by the attributes, so only the
    # codestream header shows that the frame is 5 rows of 7, not 7 of 5.
    assert ROWS != COLUMNS
    data = _lossless(rows=COLUMNS, columns=ROWS)

    assert frames_problem(read_source(data)) is TransformReason.FRAME_MISMATCH


def test_a_jpeg_2000_frame_with_the_rows_and_columns_swapped_is_refused():
    _needs(compressed.JPEG_2000_LOSSLESS)
    pytest.importorskip("openjpeg")
    frame = np.arange(48 * 64, dtype=np.uint16).reshape(48, 64) % 4096
    codestream = compressed.jpeg_2000(frame, precision=12)

    def image(rows, columns):
        return read_source(
            compressed.ct_image(
                compressed.JPEG_2000_LOSSLESS,
                [codestream],
                rows=rows,
                columns=columns,
                bits=12,
            )
        )

    assert frames_problem(image(48, 64)) is None
    assert frames_problem(image(64, 48)) is TransformReason.FRAME_MISMATCH


@pytest.mark.parametrize("precision, bits", [(16, 12), (12, 16), (12, 11)])
def test_a_jpeg_precision_other_than_bits_stored_is_refused(precision, bits):
    _needs(compressed.JPEG_LOSSLESS_SV1)
    frame = _frames(1, bits=min(precision, bits))[0]
    data = compressed.ct_image(
        compressed.JPEG_LOSSLESS_SV1,
        [compressed.jpeg_lossless(frame, precision=precision)],
        rows=ROWS,
        columns=COLUMNS,
        bits=bits,
    )

    assert frames_problem(read_source(data)) is TransformReason.FRAME_MISMATCH


def test_an_8_bit_jpeg_baseline_frame_declared_as_7_bits_is_refused():
    _needs(compressed.JPEG_BASELINE)
    pytest.importorskip("PIL")
    frame = np.arange(256, dtype=np.uint8).reshape(16, 16) // 2
    codestream = compressed.jpeg_baseline(frame)

    def image(bits):
        return read_source(
            compressed.ct_image(
                compressed.JPEG_BASELINE, [codestream], rows=16, columns=16, bits=bits
            )
        )

    assert frames_problem(image(8)) is None
    assert frames_problem(image(7)) is TransformReason.FRAME_MISMATCH


def test_a_jpeg_2000_precision_other_than_bits_stored_is_refused():
    _needs(compressed.JPEG_2000_LOSSLESS)
    pytest.importorskip("openjpeg")
    frame = np.arange(48 * 64, dtype=np.uint16).reshape(48, 64) % 4096
    data = compressed.ct_image(
        compressed.JPEG_2000_LOSSLESS,
        [compressed.jpeg_2000(frame, precision=13)],
        rows=48,
        columns=64,
        bits=12,
    )

    assert frames_problem(read_source(data)) is TransformReason.FRAME_MISMATCH


def test_a_subsampled_jpeg_2000_component_is_refused():
    _needs(compressed.JPEG_2000_LOSSLESS)
    pytest.importorskip("openjpeg")
    frame = np.arange(48 * 64, dtype=np.uint16).reshape(48, 64) % 4096
    codestream = bytearray(compressed.jpeg_2000(frame, precision=12))
    # SOC, then SIZ, whose first component's XRsiz follows its Ssiz.
    assert codestream[:4] == b"\xff\x4f\xff\x51"
    codestream[43] = 2
    data = compressed.ct_image(
        compressed.JPEG_2000_LOSSLESS, [bytes(codestream)], rows=48, columns=64, bits=12
    )

    assert frames_problem(read_source(data)) is TransformReason.FRAME_MISMATCH


def test_one_frame_of_several_whose_header_differs_is_refused():
    _needs(compressed.JPEG_LOSSLESS_SV1)
    frames = _frames(3, bits=12)
    codestreams = [
        compressed.jpeg_lossless(frame, precision=12 if i != 1 else 13)
        for i, frame in enumerate(frames)
    ]
    data = compressed.ct_image(
        compressed.JPEG_LOSSLESS_SV1,
        codestreams,
        rows=ROWS,
        columns=COLUMNS,
        bits=12,
        number_of_frames=3,
    )

    assert frames_problem(read_source(data)) is TransformReason.FRAME_MISMATCH


def test_a_jpeg_frame_header_of_0_lines_is_refused():
    # Its height would be given by a DNL marker segment after the first scan.
    _needs(compressed.JPEG_LOSSLESS_SV1)
    codestream = bytearray(compressed.jpeg_lossless(_frames(1)[0]))
    header = codestream.index(b"\xff\xc3")
    codestream[header + 5 : header + 7] = b"\x00\x00"
    data = compressed.ct_image(
        compressed.JPEG_LOSSLESS_SV1,
        [bytes(codestream)],
        rows=ROWS,
        columns=COLUMNS,
    )

    assert frames_problem(read_source(data)) is TransformReason.FRAME_MISMATCH


def _jpeg_ls(
    marker=0xFFF7, rows=ROWS, columns=COLUMNS, near=0, point_transform=0, data=b"\x00"
):
    """Return a JPEG-LS codestream: SOI, a frame header for one 8-bit
    component, SOS, ``data`` as its scan's entropy-coded data, and EOI. Only
    its marker segments are meant to be read."""
    frame = struct.pack(">HHBHHBBBB", marker, 11, 8, rows, columns, 1, 1, 0x11, 0)
    # Ns 1, then component 1 with no mapping table, NEAR, ILV 0, Ah 0, and
    # the point transform as Al.
    scan = struct.pack(">HHBBBBBB", 0xFFDA, 8, 1, 1, 0, near, 0, point_transform)
    return b"\xff\xd8" + frame + scan + data + b"\xff\xd9"


@pytest.mark.parametrize(
    "syntax, codestream, problem",
    [
        (
            compressed.JPEG_LS_LOSSLESS,
            _jpeg_ls(rows=COLUMNS, columns=ROWS),
            TransformReason.FRAME_MISMATCH,
        ),
        (
            compressed.JPEG_LS_LOSSLESS,
            _jpeg_ls(marker=0xFFC3),
            TransformReason.FRAME_MISMATCH,
        ),
        (
            compressed.JPEG_LS_LOSSLESS,
            _jpeg_ls(near=2),
            TransformReason.FRAME_MISMATCH,
        ),
    ],
    ids=["dimensions-swapped", "t81-frame-header", "near-lossless"],
)
def test_a_jpeg_ls_codestream_is_checked_against_its_attributes_and_syntax(
    syntax, codestream, problem
):
    _needs(syntax)
    data = compressed.ct_image(syntax, [codestream], rows=ROWS, columns=COLUMNS, bits=8)

    assert frames_problem(read_source(data)) is problem


@pytest.mark.parametrize(
    "syntax, near, point_transform, problem",
    [
        (compressed.JPEG_LS_LOSSLESS, 0, 0, None),
        (compressed.JPEG_LS_NEAR_LOSSLESS, 0, 0, None),
        (compressed.JPEG_LS_NEAR_LOSSLESS, 2, 0, None),
        (compressed.JPEG_LS_NEAR_LOSSLESS, 0, 1, None),
        (compressed.JPEG_LS_LOSSLESS, 2, 0, TransformReason.FRAME_MISMATCH),
        (compressed.JPEG_LS_LOSSLESS, 0, 1, TransformReason.FRAME_MISMATCH),
    ],
)
def test_only_jpeg_ls_near_lossless_allows_a_lossy_scan(
    syntax, near, point_transform, problem
):
    declared = Declared(ROWS, COLUMNS, 1, 8, False, "MONOCHROME2")
    codestream = _jpeg_ls(near=near, point_transform=point_transform)

    assert header_problem(syntax, codestream, declared) is problem


@pytest.mark.parametrize(
    "syntax", [compressed.JPEG_LOSSLESS, compressed.JPEG_LOSSLESS_SV1]
)
def test_a_jpeg_lossless_scan_with_a_point_transform_is_refused(syntax):
    # A point transform drops low-order bits before coding, so the frame is
    # not lossless.
    _needs(syntax)
    codestream = bytearray(compressed.jpeg_lossless(_frames(1)[0]))
    scan = codestream.index(b"\xff\xda")
    approximation = scan + 4 + 3 + 2 * codestream[scan + 4]
    assert codestream[approximation] == 0

    def problem(point_transform):
        codestream[approximation] = point_transform
        image = compressed.ct_image(
            syntax, [bytes(codestream)], rows=ROWS, columns=COLUMNS
        )
        return frames_problem(read_source(image))

    assert problem(0) is None
    assert problem(1) is TransformReason.FRAME_MISMATCH


def test_a_jpeg_ls_scan_without_data_is_undecodable():
    declared = Declared(ROWS, COLUMNS, 1, 8, False, "MONOCHROME2")

    assert header_problem(compressed.JPEG_LS_LOSSLESS, _jpeg_ls(), declared) is None
    assert (
        header_problem(compressed.JPEG_LS_LOSSLESS, _jpeg_ls(data=b""), declared)
        is TransformReason.UNDECODABLE_PIXEL_DATA
    )


def _cut_short(codestream, cut):
    scan = codestream.index(b"\xff\xda")
    data = scan + 2 + int.from_bytes(codestream[scan + 2 : scan + 4], "big")
    if cut == "without-eoi":
        return codestream[:-2]
    if cut == "halfway":
        return codestream[: (data + len(codestream) - 2) // 2]
    return codestream[:data] + b"\xff\xd9"


@pytest.mark.parametrize("cut", ["without-eoi", "halfway", "empty-scan"])
def test_a_jpeg_frame_cut_short_is_undecodable(cut):
    # GDCM decodes a frame without its EOI, or whose scan is empty, without
    # an error, filling the rest of the frame.
    _needs(compressed.JPEG_LOSSLESS_SV1)
    codestream = compressed.jpeg_lossless(_frames(1)[0])
    data = compressed.ct_image(
        compressed.JPEG_LOSSLESS_SV1,
        [_cut_short(codestream, cut)],
        rows=ROWS,
        columns=COLUMNS,
    )

    assert frames_problem(read_source(data)) is TransformReason.UNDECODABLE_PIXEL_DATA


def _baseline():
    pytest.importorskip("PIL")
    frame = np.arange(256, dtype=np.uint8).reshape(16, 16)
    return compressed.jpeg_baseline(frame)


@pytest.mark.parametrize(
    "syntax, problem",
    [
        (compressed.JPEG_BASELINE, None),
        (compressed.JPEG_EXTENDED, None),
        (compressed.JPEG_LOSSLESS, TransformReason.FRAME_MISMATCH),
        (compressed.JPEG_LOSSLESS_SV1, TransformReason.FRAME_MISMATCH),
    ],
)
def test_a_jpeg_baseline_frame_passes_only_under_a_lossy_syntax(syntax, problem):
    _needs(syntax)
    data = compressed.ct_image(syntax, [_baseline()], rows=16, columns=16, bits=8)

    assert frames_problem(read_source(data)) is problem


@pytest.mark.parametrize(
    "syntax, problem",
    [
        (compressed.JPEG_LOSSLESS, None),
        (compressed.JPEG_LOSSLESS_SV1, None),
        (compressed.JPEG_BASELINE, TransformReason.FRAME_MISMATCH),
        (compressed.JPEG_EXTENDED, TransformReason.FRAME_MISMATCH),
    ],
)
def test_a_jpeg_lossless_frame_passes_only_under_a_lossless_syntax(syntax, problem):
    _needs(syntax)
    codestream = compressed.jpeg_lossless(_frames(1)[0])
    data = compressed.ct_image(syntax, [codestream], rows=ROWS, columns=COLUMNS)

    assert frames_problem(read_source(data)) is problem


def _with(data, syntax, **attributes):
    """Return ``data`` with ``attributes`` set, written in ``syntax``."""
    dataset = pydicom.dcmread(io.BytesIO(data))
    for keyword, value in attributes.items():
        setattr(dataset, keyword, value)
    return synthetic.written(dataset, syntax)


def _needs_openjpeg(syntax=compressed.JPEG_2000_LOSSLESS):
    _needs(syntax)
    pytest.importorskip("openjpeg")


def _jpeg_2000_image(
    codestream, *, syntax=compressed.JPEG_2000_LOSSLESS, bits=12, **attributes
):
    """Return a 48 by 64 image of ``codestream``, with ``attributes`` set."""
    data = compressed.ct_image(syntax, [codestream], rows=48, columns=64, bits=bits)
    return read_source(_with(data, syntax, **attributes))


_UNSIGNED = np.arange(48 * 64, dtype=np.uint16).reshape(48, 64) % 4096
_SIGNED = (_UNSIGNED.astype(np.int16) - 2048).astype(np.int16)


@pytest.mark.parametrize(
    "frame, representation, problem",
    [
        (_UNSIGNED, 0, None),
        (_SIGNED, 1, None),
        (_UNSIGNED, 1, TransformReason.FRAME_MISMATCH),
        (_SIGNED, 0, TransformReason.FRAME_MISMATCH),
    ],
    ids=["unsigned", "signed", "unsigned-declared-signed", "signed-declared-unsigned"],
)
def test_jpeg_2000_signedness_must_match_pixel_representation(
    frame, representation, problem
):
    _needs_openjpeg()
    codestream = compressed.jpeg_2000(frame, precision=12)
    image = _jpeg_2000_image(codestream, PixelRepresentation=representation)

    assert frames_problem(image) is problem


def test_an_irreversible_jpeg_2000_frame_passes_only_under_a_lossy_syntax():
    _needs_openjpeg(compressed.JPEG_2000)
    codestream = compressed.jpeg_2000(_UNSIGNED, precision=12, compression_ratios=[20])
    lossy = _jpeg_2000_image(codestream, syntax=compressed.JPEG_2000)
    lossless = _jpeg_2000_image(codestream)

    assert frames_problem(lossy) is None
    assert frames_problem(lossless) is TransformReason.FRAME_MISMATCH


def _rate_limited_jpeg_2000(frame):
    """Return ``frame`` as a JPEG 2000 codestream with the reversible
    wavelet, truncated to a rate of 12 by Pillow's OpenJPEG encoder."""
    image = pytest.importorskip("PIL.Image")
    features = pytest.importorskip("PIL.features")
    if not features.check("jpg_2000"):
        pytest.skip("Pillow was built without OpenJPEG")
    buffer = io.BytesIO()
    image.fromarray(frame).save(
        buffer,
        "JPEG2000",
        no_jp2=True,
        irreversible=False,
        quality_mode="rates",
        quality_layers=[12],
    )
    return buffer.getvalue()


def test_a_truncated_reversible_jpeg_2000_frame_is_not_detected():
    # The reversible wavelet is needed for lossless coding but does not show
    # it: a truncated codestream is lossy (PS3.5 Section A.4.4), and whether
    # every coding pass was kept is recorded only in packet headers, which
    # are not read. This records that limit; it is not a requirement.
    _needs_openjpeg()
    _needs(compressed.JPEG_2000)
    openjpeg = pytest.importorskip("openjpeg")
    frame = np.random.default_rng(0).integers(0, 256, (48, 64), dtype=np.uint8)
    exact = compressed.jpeg_2000(frame, precision=8)
    truncated = _rate_limited_jpeg_2000(frame)
    _, cod = _segment_at(truncated, b"\xff\x52")
    assert cod[13] == 1  # the reversible 5-3 wavelet
    assert np.array_equal(openjpeg.decode(exact), frame)
    assert not np.array_equal(openjpeg.decode(truncated), frame)

    assert frames_problem(_jpeg_2000_image(exact, bits=8)) is None
    lossy = _jpeg_2000_image(truncated, syntax=compressed.JPEG_2000, bits=8)
    assert frames_problem(lossy) is None
    assert frames_problem(_jpeg_2000_image(truncated, bits=8)) is None


def _segment_at(codestream, marker):
    """Return where the first ``marker`` segment is, and the segment."""
    start = codestream.index(marker)
    (length,) = struct.unpack_from(">H", codestream, start + 2)
    return start, codestream[start : start + 2 + length]


def test_an_irreversible_tile_part_under_a_lossless_syntax_is_refused():
    _needs_openjpeg()
    codestream = compressed.jpeg_2000(_UNSIGNED, precision=12)
    _, cod = _segment_at(codestream, b"\xff\x52")
    # The same COD in the first tile-part header, with the 9-7 wavelet: the
    # marker and Lcod, then Scod, SGcod's 4 bytes, and SPcod's 4 bytes
    # before its transformation.
    irreversible = bytearray(cod)
    assert irreversible[13] == 1
    irreversible[13] = 0
    tile_part, _ = _segment_at(codestream, b"\xff\x90")
    (length,) = struct.unpack_from(">I", codestream, tile_part + 6)
    changed = bytearray(codestream)
    struct.pack_into(">I", changed, tile_part + 6, length + len(irreversible))
    changed[tile_part + 12 : tile_part + 12] = irreversible

    assert frames_problem(_jpeg_2000_image(codestream)) is None
    assert frames_problem(_jpeg_2000_image(bytes(changed))) is (
        TransformReason.FRAME_MISMATCH
    )


_RGB = np.stack([_UNSIGNED % 256, _UNSIGNED // 16 % 256, _UNSIGNED % 7 * 30], axis=-1)


@pytest.mark.parametrize(
    "transformed, photometric, problem",
    [
        (True, "YBR_RCT", None),
        (False, "RGB", None),
        (True, "RGB", TransformReason.FRAME_MISMATCH),
        (True, "YBR_ICT", TransformReason.FRAME_MISMATCH),
        (False, "YBR_RCT", TransformReason.FRAME_MISMATCH),
    ],
)
def test_the_jpeg_2000_component_transformation_must_match_photometric_interpretation(
    transformed, photometric, problem
):
    _needs_openjpeg()
    codestream = compressed.jpeg_2000(
        _RGB.astype(np.uint8),
        precision=8,
        photometric_interpretation=1,
        use_mct=transformed,
    )
    image = _jpeg_2000_image(
        codestream,
        bits=8,
        SamplesPerPixel=3,
        PhotometricInterpretation=photometric,
        PlanarConfiguration=0,
    )

    assert frames_problem(image) is problem


@pytest.mark.parametrize("value", [0, None], ids=["zero", "empty"])
def test_number_of_frames_of_zero_or_empty_is_refused(value):
    data = _lossless()
    dataset = pydicom.dcmread(io.BytesIO(data))
    dataset.NumberOfFrames = value
    data = synthetic.written(dataset, compressed.JPEG_LOSSLESS_SV1)

    assert frames_problem(read_source(data)) is TransformReason.FRAME_MISMATCH


def test_without_number_of_frames_an_image_has_one_frame():
    data = _lossless()

    assert "NumberOfFrames" not in pydicom.dcmread(io.BytesIO(data))
    assert frames_problem(read_source(data)) is None


def test_a_frame_that_does_not_decode_is_refused_without_quoting_anything(caplog):
    _needs(compressed.JPEG_LOSSLESS_SV1)
    data = compressed.ct_image(
        compressed.JPEG_LOSSLESS_SV1,
        [b"\xff\xd8SENTINEL\xff\xd9"],
        rows=ROWS,
        columns=COLUMNS,
        name=SENTINEL,
    )

    with caplog.at_level(logging.DEBUG):
        problem = frames_problem(read_source(data))

    assert problem is TransformReason.UNDECODABLE_PIXEL_DATA
    assert "SENTINEL" not in caplog.text


def test_without_its_decoder_an_instance_is_refused(monkeypatch):
    data = compressed.rle_ct_image(_frames(1)[0])
    monkeypatch.setattr(
        pixel_decoding,
        "DECODING_PLUGINS",
        {**DECODING_PLUGINS, compressed.RLE_LOSSLESS: "no-such-plugin"},
    )

    assert not decoder_available(compressed.RLE_LOSSLESS)
    assert frames_problem(read_source(data)) is TransformReason.NO_DECODER


def test_the_pinned_decoder_is_used_whatever_else_is_installed(monkeypatch):
    data = _lossless()
    plugins = []
    iter_pixels = pydicom.pixels.iter_pixels

    def recording(*args, **kwargs):
        plugins.append(kwargs.get("decoding_plugin"))
        return iter_pixels(*args, **kwargs)

    monkeypatch.setattr(pydicom.pixels, "iter_pixels", recording)

    assert frames_problem(read_source(data)) is None
    assert plugins == ["gdcm"]


def _codestreams(count=3):
    _needs(compressed.JPEG_LOSSLESS_SV1)
    return [compressed.jpeg_lossless(f) for f in _frames(count)]


def _three_frames(**tables):
    return compressed.ct_image(
        compressed.JPEG_LOSSLESS_SV1,
        _codestreams(),
        rows=ROWS,
        columns=COLUMNS,
        number_of_frames=3,
        **tables,
    )


def _lengths(codestreams):
    return [len(c) + len(c) % 2 for c in codestreams]


def test_a_basic_offset_table_that_gives_each_frame_passes():
    starts = compressed.frame_starts(_codestreams())

    assert frames_problem(read_source(_three_frames(offsets=starts))) is None


@pytest.mark.parametrize(
    "offsets",
    [
        lambda s: s[:2],
        lambda s: [*s, s[-1] + 8],
        lambda s: [s[1], s[1], s[2]],
        lambda s: [0, s[2], s[1]],
        lambda s: [0, s[1] + 2, s[2]],
        lambda s: [4, s[1], s[2]],
    ],
    ids=[
        "too-few",
        "too-many",
        "not-from-0",
        "not-increasing",
        "mid-fragment",
        "first-not-0",
    ],
)
def test_a_basic_offset_table_that_does_not_give_each_frame_is_refused(offsets):
    starts = compressed.frame_starts(_codestreams())

    assert (
        frames_problem(read_source(_three_frames(offsets=offsets(starts))))
        is TransformReason.OFFSET_TABLE_MISMATCH
    )


def test_a_basic_offset_table_of_part_of_an_offset_is_refused():
    data = _three_frames(offsets=[0])
    # Two more bytes in the table item, so that it is not a whole number of
    # 32-bit offsets.
    data = data.replace(
        b"\xfe\xff\x00\xe0\x04\x00\x00\x00\x00\x00\x00\x00",
        b"\xfe\xff\x00\xe0\x06\x00\x00\x00" + bytes(6),
        1,
    )

    assert frames_problem(read_source(data)) is TransformReason.OFFSET_TABLE_MISMATCH


@pytest.mark.parametrize("padding", [0, 1])
def test_an_extended_offset_table_that_gives_each_frame_passes(padding):
    codestreams = _codestreams()
    lengths = [n - padding * (n % 2 == 0) for n in _lengths(codestreams)]
    data = _three_frames(extended=(compressed.frame_starts(codestreams), lengths))

    assert frames_problem(read_source(data)) is None


@pytest.mark.parametrize(
    "tables",
    [
        lambda s, n: {"extended": (s, n), "offsets": s},
        lambda s, n: {"extended": (s[:2], n[:2])},
        lambda s, n: {"extended": ([0, s[2], s[1]], n)},
        lambda s, n: {"extended": (s, [n[0] + 2, *n[1:]])},
        lambda s, n: {"extended": (s, [n[0] - 2, *n[1:]])},
        lambda s, n: {"extended": (s, n[:2])},
    ],
    ids=[
        "with-basic-offsets",
        "too-few",
        "out-of-order",
        "length-too-long",
        "length-too-short",
        "lengths-too-few",
    ],
)
def test_an_extended_offset_table_that_does_not_give_each_frame_is_refused(tables):
    codestreams = _codestreams()
    data = _three_frames(
        **tables(compressed.frame_starts(codestreams), _lengths(codestreams))
    )

    assert frames_problem(read_source(data)) is TransformReason.OFFSET_TABLE_MISMATCH


@pytest.mark.parametrize("kept", ["ExtendedOffsetTable", "ExtendedOffsetTableLengths"])
def test_an_extended_offset_table_without_its_lengths_or_the_reverse_is_refused(kept):
    codestreams = _codestreams()
    data = _three_frames(
        extended=(compressed.frame_starts(codestreams), _lengths(codestreams))
    )
    dataset = pydicom.dcmread(io.BytesIO(data))
    other = ({"ExtendedOffsetTable", "ExtendedOffsetTableLengths"} - {kept}).pop()
    del dataset[other]
    data = synthetic.written(dataset, compressed.JPEG_LOSSLESS_SV1)

    assert frames_problem(read_source(data)) is TransformReason.OFFSET_TABLE_MISMATCH


def test_an_instance_without_pixel_data_has_nothing_to_decode():
    dataset = synthetic.ct_slice(0)

    data = synthetic.written(dataset, compressed.JPEG_LOSSLESS_SV1)

    assert frames_problem(read_source(data)) is None
