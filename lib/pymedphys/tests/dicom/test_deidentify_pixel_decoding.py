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

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import pixel_decoding
from pymedphys._dicom.deidentify.pixel_decoding import (
    DECODING_PLUGINS,
    decoder_available,
    frames_problem,
    same_pixels,
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
    assert set(DECODING_PLUGINS.values()) == {"pydicom", "pylibjpeg"}


def test_with_the_user_extra_every_encapsulated_syntax_has_its_decoder():
    # The ``user`` extra declares pylibjpeg with its libjpeg and openjpeg
    # plugins; the ``dicom`` extra alone declares none of them.
    for module in ("pylibjpeg", "libjpeg", "openjpeg"):
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
    assert frames_problem(read_source(_lossless(**image))) in (
        TransformReason.FRAME_MISMATCH,
        TransformReason.UNDECODABLE_PIXEL_DATA,
    )


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
    assert plugins == ["pylibjpeg"]


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


def test_frames_that_decode_to_the_same_pixels_are_the_same():
    frames = _frames(2)
    codestreams = [compressed.jpeg_lossless(f) for f in frames]
    other = [compressed.jpeg_lossless(f, predictor=7) for f in frames]
    _needs(compressed.JPEG_LOSSLESS_SV1)
    image = {"rows": ROWS, "columns": COLUMNS, "number_of_frames": 2}

    before = read_source(
        compressed.ct_image(compressed.JPEG_LOSSLESS_SV1, codestreams, **image)
    )
    after = read_source(
        compressed.ct_image(compressed.JPEG_LOSSLESS_SV1, other, **image)
    )

    assert other != codestreams
    assert same_pixels(before, after)


@pytest.mark.parametrize(
    "change", ["another-frame", "fewer-frames", "undecodable", "another-syntax"]
)
def test_frames_that_differ_are_not_the_same(change):
    _needs(compressed.JPEG_LOSSLESS_SV1)
    frames = _frames(2)
    codestreams = [compressed.jpeg_lossless(f) for f in frames]
    image = {"rows": ROWS, "columns": COLUMNS, "number_of_frames": 2}
    before = read_source(
        compressed.ct_image(compressed.JPEG_LOSSLESS_SV1, codestreams, **image)
    )
    syntax = compressed.JPEG_LOSSLESS_SV1
    if change == "another-frame":
        changed = [codestreams[0], compressed.jpeg_lossless(_frames(1, seed=9)[0])]
    elif change == "fewer-frames":
        changed = codestreams[:1]
    elif change == "undecodable":
        changed = [codestreams[0], codestreams[1][:20]]
    else:
        changed, syntax = codestreams, compressed.JPEG_LOSSLESS
    after = read_source(compressed.ct_image(syntax, changed, **image))

    assert not same_pixels(before, after)
