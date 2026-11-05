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

"""Compressed CT, PET, RT Dose, and Segmentation instances of the analytic
head, defaced from their decoded frames as native ones are, and written
uncompressed. Every UID and value here is invented."""

# The native instances are those of the defacing tests, so their helpers are
# shared.
# pylint: disable = protected-access

from __future__ import annotations

import functools
import io

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import isolated_decoding, pixel_decoding
from pymedphys._dicom.deidentify.dose_defacing import RtDoseDefacer
from pymedphys._dicom.deidentify.face_blocks import (
    CtDefacer,
    SeriesProblem,
    kept_slices,
)
from pymedphys._dicom.deidentify.pixel_cleaning import (
    PixelDataRefused,
    black_out,
    decoded_stored_values,
    redaction_problem,
)
from pymedphys._dicom.deidentify.pixel_decoding import (
    FramesRefused,
    decoded_frames,
    decoded_frames_at,
)
from pymedphys._dicom.deidentify.reasons import TransformReason
from pymedphys._dicom.deidentify.region_defacing import PetDefacer
from pymedphys._dicom.deidentify.segmentation_defacing import SegmentationDefacer
from pymedphys._dicom.deidentify.source import EXPLICIT_VR_LITTLE_ENDIAN, read_source

from . import _synthetic_compressed as compressed
from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from . import test_deidentify_dose_defacing as dose_tests
from . import test_deidentify_multi_frame_defacing as multi_frame
from . import test_deidentify_segmentation_defacing as segmentation_tests
from ._corpus_run import decoders_installed

RLE_LOSSLESS = compressed.RLE_LOSSLESS
JPEG_LOSSLESS_SV1 = compressed.JPEG_LOSSLESS_SV1
JPEG_2000_LOSSLESS = compressed.JPEG_2000_LOSSLESS
JPEG_2000 = compressed.JPEG_2000
# The lossless syntaxes that the tests encode: by pydicom's own decoder in
# process, and by GDCM and by pylibjpeg in the decoding child.
LOSSLESS = (RLE_LOSSLESS, JPEG_LOSSLESS_SV1, JPEG_2000_LOSSLESS)
# MPEG-2 Main Profile / Main Level, which encapsulates Pixel Data but which
# no run decodes.
_NOT_DECODED = "1.2.840.10008.1.2.4.100"

pytestmark = pytest.mark.skipif(
    not decoders_installed(), reason="needs a decoder of each compressed syntax"
)


def _dataset(data: bytes) -> pydicom.Dataset:
    return pydicom.dcmread(io.BytesIO(data))


# The head's slices, with unsigned stored values, which JPEG Lossless takes.
@functools.cache
def _unsigned() -> tuple[bytes, ...]:
    return tuple(files.ct_files(multi_frame._SCAN, head.Head(noise=0.0), signed=False))


@functools.cache
def _encoded(syntax: str) -> tuple[bytes, ...]:
    return tuple(compressed.compressed_file(each, syntax) for each in _unsigned())


@functools.cache
def _native_outcome():
    return multi_frame._outcome(*_unsigned())


def _outcome(*data: bytes):
    return multi_frame._outcome(*data)


def _written(data: bytes, block) -> tuple:
    """The redaction of a CT slice's file defaced by its block, as a run
    writes it, and its source."""
    source = read_source(data)
    redaction = black_out(
        source, source.dataset(), None, CtDefacer(block, source.dataset())
    )
    return redaction, source


@pytest.mark.parametrize("syntax", LOSSLESS)
def test_compressed_slices_give_the_block_that_native_ones_give(syntax):
    native = _native_outcome()

    outcome = _outcome(*_encoded(syntax))

    assert native.problem is None
    assert outcome.problem is None
    assert outcome.block == native.block
    assert outcome.frame == native.frame


def test_a_series_of_compressed_and_native_slices_has_the_block_of_its_slices():
    slices = [
        compressed.compressed_file(each, LOSSLESS[index % 3]) if index % 4 else each
        for index, each in enumerate(_unsigned())
    ]

    assert _outcome(*slices).block == _native_outcome().block


@pytest.mark.parametrize("syntax", LOSSLESS)
def test_a_compressed_slice_is_written_uncompressed_as_the_native_one_is_defaced(
    syntax,
):
    block = _native_outcome().block
    written = 0

    for native, data in zip(_unsigned(), _encoded(syntax)):
        expected, _ = _written(native, block)
        redaction, source = _written(data, block)
        assert redaction.transfer_syntax == EXPLICIT_VR_LITTLE_ENDIAN
        assert redaction.value == expected.value
        assert [m.frame for m in redaction.masks] == [m.frame for m in expected.masks]
        for found, wanted in zip(redaction.masks, expected.masks):
            assert np.array_equal(found.mask, wanted.mask)
            assert found.value == wanted.value
        output = source.dataset()
        output.PixelData = redaction.value
        output["PixelData"].VR = "OW"
        output.file_meta.TransferSyntaxUID = EXPLICIT_VR_LITTLE_ENDIAN
        assert not redaction_problem(
            source, read_source(files.written(output)), redaction
        )
        written += bool(redaction.masks)
    assert written > 0


def test_a_defacer_reaches_only_a_slice_that_its_block_holds():
    block = _native_outcome().block
    reached = [
        CtDefacer(block, _dataset(data)).reaches for data in _encoded(RLE_LOSSLESS)
    ]
    masked = [bool(_written(data, block)[0].masks) for data in _unsigned()]

    # Every slice given a mask is reached, and the slices below the block
    # are not.
    assert all(r for r, m in zip(reached, masked) if m)
    assert any(reached) and not all(reached)


def test_a_lossy_compressed_series_is_defaced_from_its_decoded_frames():
    slices = tuple(
        compressed.compressed_file(each, JPEG_2000, compression_ratios=[8])
        for each in _unsigned()
    )

    outcome = _outcome(*slices)

    assert outcome.problem is None
    np.testing.assert_allclose(
        outcome.block.globes, _native_outcome().block.globes, atol=2.0
    )
    changed = lossy = 0
    for data, native in zip(slices, _unsigned()):
        redaction, source = _written(data, outcome.block)
        decoded = np.asarray(next(decoded_stored_values(source, source.dataset(), [0])))
        written = np.frombuffer(redaction.value, dtype="<u2").reshape(decoded.shape)
        mask = np.zeros(decoded.shape, dtype=bool)
        for each in redaction.masks:
            mask |= each.mask
            assert np.all(written[each.mask] == each.value)
        # Outside the air written, the samples that the lossy decode gives
        # are written as they are, and they differ from the source's.
        assert np.array_equal(written[~mask], decoded[~mask])
        lossy += not np.array_equal(
            decoded, pydicom.pixels.pixel_array(_dataset(native))
        )
        changed += int(mask.any())
    assert changed > 0 and lossy > 0


def _with_rle_segments(data: bytes, count: int) -> bytes:
    """The RLE Lossless file ``data`` with its first frame's header giving
    ``count`` segments, which its samples do not fill."""
    dataset = _dataset(data)
    frames = list(pydicom.encaps.generate_frames(dataset.PixelData, number_of_frames=1))
    first = count.to_bytes(4, "little") + frames[0][4:]
    dataset.PixelData = compressed.encapsulated([first, *frames[1:]])
    return files.written(dataset)


def _with_offsets(data: bytes, offsets) -> bytes:
    """The file ``data``, of one frame, with its Basic Offset Table of
    ``offsets``."""
    dataset = _dataset(data)
    (frame,) = pydicom.encaps.generate_frames(dataset.PixelData, number_of_frames=1)
    dataset.PixelData = compressed.encapsulated([frame], offsets)
    return files.written(dataset)


def _with_bits_stored(data: bytes, bits: int) -> bytes:
    """The file ``data`` with a Bits Stored that its codestream's precision
    does not match."""
    dataset = _dataset(data)
    dataset.BitsStored = bits
    dataset.HighBit = bits - 1
    return files.written(dataset)


def _with_syntax(data: bytes, syntax: str) -> bytes:
    dataset = _dataset(data)
    dataset.file_meta.TransferSyntaxUID = syntax
    return files.written(dataset)


_UNDECODABLE = {
    "rle-segments": lambda: _with_rle_segments(_encoded(RLE_LOSSLESS)[40], 3),
    "offset-table": lambda: _with_offsets(_encoded(JPEG_2000_LOSSLESS)[40], [0, 8]),
    "header": lambda: _with_bits_stored(_encoded(JPEG_2000_LOSSLESS)[40], 14),
    "not-decoded": lambda: _with_syntax(_encoded(RLE_LOSSLESS)[40], _NOT_DECODED),
}


@pytest.mark.parametrize("name", list(_UNDECODABLE))
def test_a_slice_whose_frames_do_not_decode_leaves_its_series_undefaced(name):
    slices = list(_encoded(RLE_LOSSLESS))
    slices[40] = _UNDECODABLE[name]()

    assert _outcome(*slices).problem is SeriesProblem.UNDECODABLE


def test_a_compressed_series_without_its_decoder_is_undecodable(monkeypatch):
    monkeypatch.setattr(pixel_decoding, "decoder_available", lambda *_: False)

    assert _outcome(*_encoded(JPEG_2000_LOSSLESS)).problem is (
        SeriesProblem.UNDECODABLE
    )


def test_a_compressed_series_whose_decoding_child_cannot_start_is_undecodable(
    monkeypatch,
):
    def unavailable(*args, **kwargs):
        raise isolated_decoding.DecoderUnavailable()

    monkeypatch.setattr(isolated_decoding, "run", unavailable)

    assert _outcome(*_encoded(JPEG_2000_LOSSLESS)).problem is (
        SeriesProblem.UNDECODABLE
    )


def test_native_slices_need_no_decoder(monkeypatch):
    monkeypatch.setattr(pixel_decoding, "decoder_available", lambda *_: False)

    assert _outcome(*_unsigned()).problem is None


@pytest.mark.parametrize(
    ("syntax", "isolated"),
    [(RLE_LOSSLESS, False), (JPEG_LOSSLESS_SV1, True), (JPEG_2000_LOSSLESS, True)],
)
def test_frames_that_native_code_decodes_are_decoded_in_the_child(
    monkeypatch, syntax, isolated
):
    calls = []
    run = isolated_decoding.run

    def counted(task, *args, **kwargs):
        calls.append(task.__name__)
        return run(task, *args, **kwargs)

    monkeypatch.setattr(isolated_decoding, "run", counted)

    assert _outcome(*_encoded(syntax)).problem is None
    # The finder reads each slice within reach of the volume's top, all of
    # this scan's, once.
    assert calls == (["_frame_decoded"] * len(_unsigned()) if isolated else [])


def test_only_the_frames_that_the_block_reaches_are_decoded_for_the_kept_brain(
    monkeypatch,
):
    data = compressed.compressed_file(files.multi_frame(_unsigned()), RLE_LOSSLESS)
    block = _native_outcome().block
    decoded = []
    frame_decoded = pixel_decoding._frame_decoded

    def counted(*args):
        decoded.append(args)
        return frame_decoded(*args)

    monkeypatch.setattr(pixel_decoding, "_frame_decoded", counted)

    found = kept_slices(block, [0], lambda _: data)

    reached = sum(CtDefacer(block, _dataset(each)).reaches for each in _unsigned())
    assert 0 < len(decoded) == len(found) == reached < len(_unsigned())


@pytest.mark.parametrize("syntax", LOSSLESS)
def test_the_brain_kept_in_compressed_slices_is_that_kept_in_native_ones(syntax):
    block = _native_outcome().block
    positions = list(range(len(_unsigned())))

    native = kept_slices(block, positions, lambda p: _unsigned()[p])
    found = kept_slices(block, positions, lambda p: _encoded(syntax)[p])

    assert len(found) == len(native) > 0
    for each, expected in zip(found, native):
        assert each.position == expected.position
        assert np.array_equal(each.kept, expected.kept)
    assert any(each.kept.any() for each in found)


@pytest.mark.parametrize("sop_class", multi_frame._MULTI_FRAME_CT)
@pytest.mark.parametrize("syntax", LOSSLESS)
def test_a_compressed_multi_frame_instance_is_defaced_as_its_slices_are(
    sop_class, syntax
):
    instance = files.multi_frame(_unsigned(), sop_class=sop_class)
    data = compressed.compressed_file(instance, syntax)

    outcome = _outcome(data)
    redaction, _ = _written(data, outcome.block)
    expected, _ = _written(instance, outcome.block)

    assert outcome.problem is None
    assert outcome.block == _native_outcome().block
    assert redaction.transfer_syntax == EXPLICIT_VR_LITTLE_ENDIAN
    assert redaction.value == expected.value
    assert len(redaction.masks) == len(expected.masks) > 0


def test_a_compressed_slice_of_colour_is_not_one_stack():
    slices = list(_encoded(RLE_LOSSLESS))
    dataset = _dataset(_unsigned()[40])
    stored = pydicom.pixels.pixel_array(dataset)
    dataset.SamplesPerPixel = 3
    dataset.PhotometricInterpretation = "RGB"
    dataset.PlanarConfiguration = 0
    dataset.BitsAllocated = dataset.BitsStored = 8
    dataset.HighBit = 7
    colour = np.repeat((stored % 256).astype(np.uint8)[..., None], 3, axis=-1)
    dataset.PixelData = compressed.encapsulated([compressed.rle_lossless(colour)])
    dataset["PixelData"].VR = "OB"
    dataset.file_meta.TransferSyntaxUID = RLE_LOSSLESS
    slices[40] = files.written(dataset)

    assert _outcome(*slices).problem is SeriesProblem.NOT_ONE_STACK


def test_a_ct_defacer_refuses_a_syntax_that_no_run_decodes():
    data = _with_syntax(_encoded(RLE_LOSSLESS)[40], _NOT_DECODED)

    with pytest.raises(PixelDataRefused):
        CtDefacer(_native_outcome().block, _dataset(data))


# PET, RT Dose, and Segmentation in the defaced frame.


@pytest.mark.parametrize("syntax", LOSSLESS)
def test_a_compressed_pet_slice_is_set_to_zero_activity_as_a_native_one(syntax):
    region = multi_frame._region()
    reached = 0

    for native in multi_frame._pet_slices():
        data = compressed.compressed_file(native, syntax)
        source, expected_source = read_source(data), read_source(native)
        redaction = black_out(
            source, source.dataset(), None, PetDefacer(region, source.dataset())
        )
        expected = black_out(
            expected_source,
            expected_source.dataset(),
            None,
            PetDefacer(region, expected_source.dataset()),
        )
        assert redaction.transfer_syntax == EXPLICIT_VR_LITTLE_ENDIAN
        assert redaction.value == expected.value
        reached += bool(redaction.masks)
    assert reached > 0


@pytest.mark.parametrize("sop_class", multi_frame._MULTI_FRAME_PET)
def test_a_compressed_multi_frame_pet_is_set_to_zero_activity_frame_by_frame(
    sop_class,
):
    region = multi_frame._region()
    native = multi_frame._pet_frames(sop_class)
    source = read_source(compressed.compressed_file(native, JPEG_2000_LOSSLESS))
    expected_source = read_source(native)

    redaction = black_out(
        source, source.dataset(), None, PetDefacer(region, source.dataset())
    )
    expected = black_out(
        expected_source,
        expected_source.dataset(),
        None,
        PetDefacer(region, expected_source.dataset()),
    )

    assert redaction.transfer_syntax == EXPLICIT_VR_LITTLE_ENDIAN
    assert redaction.value == expected.value
    assert [m.frame for m in redaction.masks] == [m.frame for m in expected.masks]
    assert redaction.masks


def test_a_pet_in_a_syntax_that_no_run_decodes_is_refused():
    data = _with_syntax(
        compressed.compressed_file(multi_frame._pet_slices()[0], RLE_LOSSLESS),
        _NOT_DECODED,
    )

    with pytest.raises(PixelDataRefused):
        PetDefacer(multi_frame._region(), _dataset(data))


def test_a_compressed_rt_dose_is_set_to_zero_as_a_native_one():
    stored = np.full((3, 21, 21), 100, dtype=np.uint32)
    # Behind the block, the greatest dose, beside which 100 is low.
    stored[:, 20, 20] = 100 * 1000
    native = files.written(dose_tests._dataset(stored))
    source = read_source(compressed.compressed_file(native, RLE_LOSSLESS))
    expected_source = read_source(native)

    defacer = RtDoseDefacer(dose_tests._DOSE_BLOCK, source.dataset())
    redaction = black_out(source, source.dataset(), None, defacer)
    expected = black_out(
        expected_source,
        expected_source.dataset(),
        None,
        RtDoseDefacer(dose_tests._DOSE_BLOCK, expected_source.dataset()),
    )

    assert defacer.held is None
    assert redaction.transfer_syntax == EXPLICIT_VR_LITTLE_ENDIAN
    assert redaction.value == expected.value
    assert redaction.masks


@pytest.mark.parametrize("kind", ["FRACTIONAL", "LABELMAP"])
def test_a_compressed_segmentation_of_whole_bytes_is_cleared_as_a_native_one(kind):
    stored = np.random.default_rng(1).integers(
        0, 2, size=(2, segmentation_tests._SIZE, segmentation_tests._SIZE)
    )
    dataset = segmentation_tests._segmentation(stored, kind=kind)
    if kind == "LABELMAP":
        segmentation_tests._padded(dataset, 0)
    native = files.written(dataset)
    source = read_source(compressed.compressed_file(native, RLE_LOSSLESS))
    expected_source = read_source(native)
    region = segmentation_tests._REGION

    redaction = black_out(
        source, source.dataset(), None, SegmentationDefacer(region, source.dataset())
    )
    expected = black_out(
        expected_source,
        expected_source.dataset(),
        None,
        SegmentationDefacer(region, expected_source.dataset()),
    )

    assert redaction.transfer_syntax == EXPLICIT_VR_LITTLE_ENDIAN
    assert redaction.value == expected.value
    assert [m.frame for m in redaction.masks] == [0, 1]


def test_a_compressed_binary_segmentation_is_refused():
    dataset = segmentation_tests._segmentation()
    dataset.file_meta.TransferSyntaxUID = RLE_LOSSLESS

    with pytest.raises(PixelDataRefused):
        SegmentationDefacer(segmentation_tests._REGION, dataset)


# The decoding of chosen frames.


def _attributes(dataset: pydicom.Dataset) -> dict:
    return {
        "Rows": int(dataset.Rows),
        "Columns": int(dataset.Columns),
        "SamplesPerPixel": 1,
        "BitsAllocated": int(dataset.BitsAllocated),
        "BitsStored": int(dataset.BitsStored),
        "HighBit": int(dataset.HighBit),
        "PixelRepresentation": int(dataset.PixelRepresentation),
        "PhotometricInterpretation": "MONOCHROME2",
    }


@functools.cache
def _frames_source():
    return read_source(
        compressed.compressed_file(
            files.multi_frame(_unsigned()[30:36]), JPEG_2000_LOSSLESS
        )
    )


@pytest.mark.parametrize("indices", [(), (0,), (5,), (1, 3), (4, 2, 4)])
def test_the_frames_asked_for_are_decoded_in_order_as_all_frames_are(indices):
    source = _frames_source()
    attributes = _attributes(source.dataset())
    size = 2 * attributes["Rows"] * attributes["Columns"]
    every = decoded_frames(source, attributes, 6, "MONOCHROME2")

    found = list(decoded_frames_at(source, attributes, 6, "MONOCHROME2", indices))

    assert found == [every[i * size : (i + 1) * size] for i in sorted(set(indices))]


@pytest.mark.parametrize("indices", [(-1,), (6,)])
def test_a_frame_that_the_pixel_data_do_not_hold_is_a_mismatch(indices):
    source = _frames_source()

    with pytest.raises(FramesRefused) as refused:
        list(
            decoded_frames_at(
                source, _attributes(source.dataset()), 6, "MONOCHROME2", indices
            )
        )

    assert refused.value.reason is TransformReason.FRAME_MISMATCH


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (
            lambda data: _with_offsets(data, [0, 8]),
            TransformReason.OFFSET_TABLE_MISMATCH,
        ),
        (lambda data: _with_bits_stored(data, 14), None),
    ],
    ids=["offset-table", "header"],
)
def test_offset_tables_and_headers_are_checked_before_any_frame_is_decoded(
    monkeypatch, change, reason
):
    source = read_source(change(_encoded(JPEG_2000_LOSSLESS)[40]))
    # As the check before a release finds it.
    expected = pixel_decoding.frames_problem(source)
    calls = []
    monkeypatch.setattr(isolated_decoding, "run", lambda *a, **k: calls.append(a))

    with pytest.raises(FramesRefused) as refused:
        list(
            decoded_frames_at(
                source, _attributes(source.dataset()), 1, "MONOCHROME2", [0]
            )
        )

    assert not calls
    assert expected is not None
    assert refused.value.reason is expected
    assert reason is None or expected is reason
