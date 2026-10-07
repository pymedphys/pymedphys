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

"""Read JPEG 2000 and HTJ2K packet headers, to tell whether every coding
pass was kept.

Every codestream is synthetic: encoded by Pillow's OpenJPEG encoder from a
generated array, or written by ``_synthetic_jpeg_2000`` with packet headers
that say what a test gives them.
"""

import io
import struct

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify.frame_headers import Declared, header_problem
from pymedphys._dicom.deidentify.jpeg_2000_packets import coding_passes_kept
from pymedphys._dicom.deidentify.reasons import TransformReason

from . import _synthetic_jpeg_2000 as synthetic
from ._synthetic_jpeg_2000 import contribution

BIT_PLANES = synthetic.MAGNITUDE_BIT_PLANES
JPEG_2000_LOSSLESS = "1.2.840.10008.1.2.4.90"
JPEG_2000 = "1.2.840.10008.1.2.4.91"
HTJ2K_LOSSLESS = "1.2.840.10008.1.2.4.201"
HTJ2K_LOSSLESS_RPCL = "1.2.840.10008.1.2.4.202"
HTJ2K = "1.2.840.10008.1.2.4.203"


def _passes(zero_bit_planes):
    """Every coding pass of a Part 1 code-block (T.800 Annex D)."""
    return 3 * (BIT_PLANES - zero_bit_planes) - 2


def _one_block(passes, zero_bit_planes=2, **options):
    return synthetic.codestream(
        [[contribution((passes, 40))]], [zero_bit_planes], **options
    )


@pytest.mark.parametrize("zero_bit_planes", [0, 2, BIT_PLANES - 2])
def test_a_code_block_is_kept_only_with_every_coding_pass(zero_bit_planes):
    passes = _passes(zero_bit_planes)
    assert coding_passes_kept(_one_block(passes, zero_bit_planes)) is True
    assert coding_passes_kept(_one_block(passes - 1, zero_bit_planes)) is False


def test_a_code_block_of_one_bit_plane_has_one_coding_pass():
    assert coding_passes_kept(_one_block(1, BIT_PLANES - 1)) is True


def test_more_coding_passes_than_a_code_block_has_cannot_be_read():
    assert coding_passes_kept(_one_block(_passes(2) + 1)) is None
    # With as many zero bit-planes as magnitude bit-planes, a code-block
    # has no coding pass.
    assert coding_passes_kept(_one_block(1, BIT_PLANES)) is None


def test_coding_passes_add_up_over_the_layers():
    blocks = [
        [contribution((10, 5)), None, contribution((25, 300)), None],
        [contribution((9, 7)), None, None, contribution((1, 2))],
    ]
    kept = synthetic.codestream(blocks, [2, 0, 0, 8], size=(16, 16))
    assert coding_passes_kept(kept) is True
    blocks[1][0] = contribution((8, 7))
    lacking = synthetic.codestream(blocks, [2, 0, 0, 8], size=(16, 16))
    assert coding_passes_kept(lacking) is False


def test_a_code_block_that_no_packet_includes_is_taken_as_all_zero():
    # An encoder leaves out a code-block whose coefficients are all zero;
    # one dropped by truncation cannot be told from it.
    blocks = [[contribution((_passes(1), 9)), None, None, None]]
    assert (
        coding_passes_kept(synthetic.codestream(blocks, [1, 0, 0, 0], size=(16, 16)))
        is True
    )


@pytest.mark.parametrize(
    "packets",
    [
        # 19 passes in segments of 10, then 2 and 1 in turn (T.800 Section
        # D.6), in one packet and over two.
        [[(10, 50), (2, 3), (1, 4), (2, 5), (1, 6), (2, 7), (1, 8)]],
        [[(10, 50), (1, 3)], [(1, 3), (1, 4), (2, 5), (1, 6), (2, 7), (1, 8)]],
    ],
    ids=["one-packet", "two-packets"],
)
def test_bypass_codeword_segments_are_read(packets):
    codestream = synthetic.codestream(
        [[contribution(*segments)] for segments in packets],
        [2],
        style=synthetic.BYPASS,
    )
    assert coding_passes_kept(codestream) is True


@pytest.mark.parametrize(
    "style", [synthetic.TERMINATE_ALL, synthetic.TERMINATE_ALL | synthetic.BYPASS]
)
def test_a_codeword_segment_for_each_pass_is_read(style):
    segments = [(1, 3 + index) for index in range(_passes(2))]
    codestream = synthetic.codestream([[contribution(*segments)]], [2], style=style)
    assert coding_passes_kept(codestream) is True


@pytest.mark.parametrize(
    "passes, zero_bit_planes, kept",
    [
        # The cleanup pass alone to bit-plane 0, or with both refinement
        # passes from bit-plane 1.
        (1, BIT_PLANES - 1, True),
        (3, BIT_PLANES - 2, True),
        (1, BIT_PLANES - 2, False),
        (2, BIT_PLANES - 2, False),
        (3, BIT_PLANES - 3, False),
        # Refinement below bit-plane 0, and placeholder passes.
        (3, BIT_PLANES - 1, None),
        (4, BIT_PLANES - 1, None),
    ],
)
def test_an_ht_code_block_must_reach_bit_plane_0(passes, zero_bit_planes, kept):
    segments = [(1, 30)] + ([(passes - 1, 4)] if passes > 1 else [])
    codestream = synthetic.codestream(
        [[contribution(*segments)]], [zero_bit_planes], style=synthetic.HT
    )
    assert coding_passes_kept(codestream) is kept


@pytest.mark.parametrize(
    "passes, zero_bit_planes, kept",
    [
        # Refinement passes with no bytes leave the cleanup pass alone.
        (3, BIT_PLANES - 1, True),
        (3, BIT_PLANES - 2, False),
        (2, BIT_PLANES - 1, True),
        (2, BIT_PLANES - 2, False),
    ],
)
def test_ht_refinement_passes_without_bytes_are_not_counted(
    passes, zero_bit_planes, kept
):
    codestream = synthetic.codestream(
        [[contribution((1, 30), (passes - 1, 0))]],
        [zero_bit_planes],
        style=synthetic.HT,
    )
    assert coding_passes_kept(codestream) is kept


def test_an_ht_cleanup_pass_without_bytes_cannot_be_read():
    codestream = synthetic.codestream(
        [[contribution((1, 0), (2, 4))]], [BIT_PLANES - 2], style=synthetic.HT
    )
    assert coding_passes_kept(codestream) is None


def test_an_ht_code_block_in_more_than_one_packet_cannot_be_read():
    codestream = synthetic.codestream(
        [[contribution((1, 30))], [contribution((2, 4))]],
        [BIT_PLANES - 2],
        style=synthetic.HT,
    )
    assert coding_passes_kept(codestream) is None


def test_mixed_ht_code_blocks_cannot_be_read():
    codestream = _one_block(1, BIT_PLANES - 1, style=synthetic.HT | synthetic.HT_MIXED)
    assert coding_passes_kept(codestream) is None


@pytest.mark.parametrize("sop", [True, False], ids=["sop", "without-sop"])
def test_sop_marker_segments_may_be_left_out_but_eph_markers_may_not(sop):
    passes = _passes(2)
    with_both = _one_block(passes, scod=synthetic.SOP | synthetic.EPH, sop=sop)
    assert coding_passes_kept(with_both) is True
    # The EPH marker is after the packet header's last byte, before the
    # packet body's 40 bytes, EOC, and the tile-part's SOD.
    without_eph = with_both.replace(b"\xff\x92", b"", 1)
    tile_part = without_eph.index(b"\xff\x90")
    (length,) = struct.unpack_from(">I", without_eph, tile_part + 6)
    changed = bytearray(without_eph)
    struct.pack_into(">I", changed, tile_part + 6, length - 2)
    assert coding_passes_kept(bytes(changed)) is None


def test_a_packet_header_that_ends_with_0xff_ends_after_a_stuffed_byte():
    # The first length whose packet header's last byte is 0xFF.
    codestream = next(
        codestream
        for length in range(1, 1 << 12)
        for codestream in [
            synthetic.codestream([[contribution((_passes(2), length))]], [2])
        ]
        if codestream[: -length - 2].endswith(b"\xff\x00")
    )
    assert coding_passes_kept(codestream) is True


def test_a_byte_of_0xff_in_a_packet_header_is_followed_by_a_stuffed_0_bit():
    # A length of 16 bits, all 1, gives packet header bytes of 0xFF.
    codestream = synthetic.codestream([[contribution((_passes(2), 0xFFFF))]], [2])
    assert b"\xff\x7f" in codestream[:-0xFFFF]
    assert coding_passes_kept(codestream) is True
    header = codestream.index(b"\xff\x7f")
    changed = bytearray(codestream)
    changed[header + 1] |= 0x80
    assert coding_passes_kept(bytes(changed)) is None


@pytest.mark.parametrize(
    "main_header",
    [
        synthetic.segment(0x5F, bytes([0, 0, 0, 1, 1, 0])),  # POC
        synthetic.segment(0x60, bytes([0])),  # PPM
        synthetic.segment(0x5E, bytes([0, 0, 2])),  # RGN
        synthetic.segment(0x74, bytes(2)),  # MCT of T.801
    ],
    ids=["poc", "ppm", "rgn", "part-2-marker"],
)
def test_what_is_not_read_here_cannot_be_read(main_header):
    passes = _passes(2)
    assert coding_passes_kept(_one_block(passes)) is True
    assert coding_passes_kept(_one_block(passes, main_header=main_header)) is None


def test_a_part_2_codestream_cannot_be_read():
    assert coding_passes_kept(_one_block(_passes(2), rsiz=0x8000)) is None


@pytest.mark.parametrize(
    "change, kept",
    [
        (lambda codestream: codestream + b"\x00", True),
        (lambda codestream: codestream + b"\x00\x00", None),
        (lambda codestream: codestream[:-2], None),
        (lambda codestream: codestream[:-3] + codestream[-2:], None),
    ],
    ids=["padded", "padded-twice", "without-eoc", "cut-short"],
)
def test_the_tile_part_must_end_with_the_last_packet_then_eoc(change, kept):
    assert coding_passes_kept(change(_one_block(_passes(2)))) is kept


def test_a_tile_part_with_bytes_after_the_last_packet_cannot_be_read():
    codestream = bytearray(_one_block(_passes(2)))
    tile_part = codestream.index(b"\xff\x90")
    (length,) = struct.unpack_from(">I", codestream, tile_part + 6)
    struct.pack_into(">I", codestream, tile_part + 6, length + 1)
    codestream[-2:-2] = b"\x00"
    assert coding_passes_kept(bytes(codestream)) is None


def _declared(columns=8, rows=8):
    return Declared(rows, columns, 1, 8, False, "MONOCHROME2")


@pytest.mark.parametrize(
    "syntax, problem",
    [
        (JPEG_2000_LOSSLESS, TransformReason.FRAME_MISMATCH),
        (JPEG_2000, None),
    ],
)
def test_lacking_coding_passes_pass_only_under_a_lossy_jpeg_2000_syntax(
    syntax, problem
):
    lacking = _one_block(_passes(2) - 3)
    assert header_problem(syntax, lacking, _declared()) is problem
    assert header_problem(syntax, _one_block(_passes(2)), _declared()) is None


@pytest.mark.parametrize(
    "syntax, problem",
    [
        (HTJ2K_LOSSLESS, TransformReason.FRAME_MISMATCH),
        (HTJ2K_LOSSLESS_RPCL, TransformReason.FRAME_MISMATCH),
        (HTJ2K, None),
    ],
)
def test_lacking_coding_passes_pass_only_under_the_htj2k_syntax(syntax, problem):
    # HTJ2K Lossless RPCL names a progression order, but a codestream is
    # read in whichever its COD marker segment gives.
    lacking = _one_block(1, BIT_PLANES - 2, style=synthetic.HT)
    assert header_problem(syntax, lacking, _declared()) is problem


def test_packet_headers_that_cannot_be_read_are_undecodable_under_a_lossless_syntax():
    unreadable = _one_block(_passes(2) + 1)
    assert header_problem(JPEG_2000_LOSSLESS, unreadable, _declared()) is (
        TransformReason.UNDECODABLE_PIXEL_DATA
    )
    assert header_problem(JPEG_2000, unreadable, _declared()) is None


# Of a size that leaves precincts and code-blocks of several sizes, so that
# a packet read for the wrong precinct does not hold together.
_FRAME = np.random.default_rng(0).integers(0, 4096, (45, 61)).astype(np.uint16)
_FRAME[:16] = 100  # so that some code-blocks are all zero

_CODINGS = {
    "defaults": {},
    "precincts": {
        "num_resolutions": 3,
        "codeblock_size": (8, 8),
        "precinct_size": (32, 32),
    },
    "tiles": {
        "num_resolutions": 4,
        "codeblock_size": (8, 16),
        "precinct_size": (16, 16),
        "tile_size": (16, 32),
    },
    "offsets": {
        "num_resolutions": 3,
        "codeblock_size": (4, 4),
        "precinct_size": (16, 16),
        "tile_size": (17, 23),
        "offset": (3, 5),
        "tile_offset": (1, 2),
    },
    # The last column of tiles is 1 sample wide, so some of its sub-bands
    # are empty.
    "narrow-tiles": {
        "num_resolutions": 3,
        "codeblock_size": (4, 4),
        "precinct_size": (8, 8),
        "tile_size": (20, 20),
    },
    "no-wavelet": {"num_resolutions": 1, "codeblock_size": (16, 16)},
}
_LAYERS = {
    "one-layer": {},
    "lossless-last-layer": {"quality_mode": "rates", "quality_layers": [40, 10, 0]},
    "truncated": {"quality_mode": "rates", "quality_layers": [8]},
}


def _pillow_jpeg_2000(frame, **options):
    image = pytest.importorskip("PIL.Image")
    features = pytest.importorskip("PIL.features")
    if not features.check("jpg_2000"):
        pytest.skip("Pillow was built without OpenJPEG")
    buffer = io.BytesIO()
    image.fromarray(frame).save(
        buffer, "JPEG2000", no_jp2=True, irreversible=False, **options
    )
    return buffer.getvalue()


def _decoded(codestream):
    image = pytest.importorskip("PIL.Image")
    return np.asarray(image.open(io.BytesIO(codestream)))


@pytest.mark.parametrize("layers", _LAYERS)
@pytest.mark.parametrize("coding", _CODINGS)
@pytest.mark.parametrize("progression", ["LRCP", "RLCP", "RPCL", "PCRL", "CPRL"])
def test_pillow_codestreams_keep_every_pass_unless_truncated(
    progression, coding, layers
):
    options = {"progression": progression, **_CODINGS[coding]}
    codestream = _pillow_jpeg_2000(_FRAME, **options, **_LAYERS[layers])
    truncated = layers == "truncated"
    # Truncation changes the decoded image, so passes were dropped.
    assert truncated != np.array_equal(
        _decoded(codestream), _decoded(_pillow_jpeg_2000(_FRAME, **options))
    )

    assert coding_passes_kept(codestream) is (not truncated)


@pytest.mark.parametrize("progression", ["RPCL", "PCRL", "CPRL"])
@pytest.mark.parametrize("mct", [0, 1])
def test_pillow_colour_codestreams_keep_every_pass_unless_truncated(progression, mct):
    frame = np.stack([_FRAME % 256, _FRAME // 16, _FRAME % 7 * 30], axis=-1)
    options = {
        "progression": progression,
        "mct": mct,
        "num_resolutions": 3,
        "codeblock_size": (16, 16),
        "precinct_size": (16, 16),
    }
    kept = _pillow_jpeg_2000(frame.astype(np.uint8), **options)
    truncated = _pillow_jpeg_2000(
        frame.astype(np.uint8), **options, quality_mode="rates", quality_layers=[10]
    )
    assert coding_passes_kept(kept) is True
    assert coding_passes_kept(truncated) is False
