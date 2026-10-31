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

"""The frames that pydicom's GDCM plugin refuses, decoded with imagecodecs (D-055).

Every image here is coded by an encoder written in the test helpers, never
by the library that decodes it: 12-bit JPEG Extended whose 8 by 8 blocks
each hold one value (:func:`_synthetic_compressed.jpeg_extended_blocks`),
and JPEG-LS by :mod:`._synthetic_jpeg_ls`, which also gives each sample as
ITU-T T.87 reconstructs it. So the expected samples are known without a
decoder.
"""

import importlib.util
import io
import subprocess
import sys

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    imagecodecs_plugin,
    isolated_decoding,
    pixel_decoding,
    qc_previews,
    run,
)
from pymedphys._dicom.deidentify.pixel_decoding import (
    IMAGECODECS,
    FramesRefused,
    decoded_frames,
    frames_problem,
    gdcm_refuses,
    isolated_frames,
    pinned_plugin,
    same_pixels,
)
from pymedphys._dicom.deidentify.instance_transform import HeldEvidence
from pymedphys._dicom.deidentify.qc_pack import NotPreviewedReason
from pymedphys._dicom.deidentify.reasons import TransformReason
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.source import EXPLICIT_VR_LITTLE_ENDIAN, read_source

from . import _synthetic_compressed as compressed
from . import _synthetic_jpeg_ls as jpeg_ls
from . import _synthetic_references as synthetic
from .test_deidentify_instance_transform import _transform as _basic_transform
from .test_deidentify_pixel_cleaning import Finder, _inside
from .test_deidentify_pixel_cleaning import _transform as _cleaning_transform
from .test_deidentify_qc_previews import _pngs

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

JPEG_EXTENDED = compressed.JPEG_EXTENDED
JPEG_LS = compressed.JPEG_LS_LOSSLESS
JPEG_LS_NEAR = compressed.JPEG_LS_NEAR_LOSSLESS
ROWS, COLUMNS = 21, 30
_RNG_SEED = 2026


def _needs(syntax):
    if not pixel_decoding.decoder_available(syntax, IMAGECODECS):
        pytest.skip(f"imagecodecs cannot decode {syntax} here")


def _levels(seed=0, signed=False):
    """One 12-bit value for each 8 by 8 block, with both extremes."""
    rng = np.random.default_rng(_RNG_SEED + seed)
    levels = rng.integers(0, 4096, (-(-ROWS // 8), -(-COLUMNS // 8)))
    levels.flat[0], levels.flat[-1] = 0, 4095
    if signed:
        levels.flat[1], levels.flat[2] = 2047, 2048
    return levels


def _image(syntax, codestreams, *, bits, signed=False, samples=1, frames=None):
    """A CT image, or an RGB one of ``samples`` 3, whose Pixel Data
    encapsulates ``codestreams``, one to a frame."""
    dataset = synthetic.ct_slice(0)
    dataset.SamplesPerPixel = samples
    dataset.PhotometricInterpretation = "MONOCHROME2" if samples == 1 else "RGB"
    if samples > 1:
        dataset.PlanarConfiguration = 0
    dataset.Rows, dataset.Columns = ROWS, COLUMNS
    dataset.BitsAllocated = 16 if bits > 8 else 8
    dataset.BitsStored = bits
    dataset.HighBit = bits - 1
    dataset.PixelRepresentation = int(signed)
    if frames is not None:
        dataset.NumberOfFrames = frames
    dataset.PixelData = compressed.encapsulated(codestreams)
    dataset["PixelData"].VR = "OB"
    return synthetic.written(dataset, syntax)


def _signed(values, bits):
    """The two's complement values of ``bits``-bit patterns."""
    values = np.asarray(values, dtype=np.int64)
    return np.where(values >= 1 << (bits - 1), values - (1 << bits), values)


def _attributes(bits, signed=False, samples=1):
    attributes = {
        "Rows": ROWS,
        "Columns": COLUMNS,
        "SamplesPerPixel": samples,
        "BitsAllocated": 16 if bits > 8 else 8,
        "BitsStored": bits,
        "HighBit": bits - 1,
        "PixelRepresentation": int(signed),
        "PhotometricInterpretation": "MONOCHROME2" if samples == 1 else "RGB",
    }
    if samples > 1:
        attributes["PlanarConfiguration"] = 0
    return attributes


def _jpeg_extended(levels, *, signed=False, frames=None):
    """A 12-bit JPEG Extended image of ``levels``, and its samples as stored."""
    codestream = compressed.jpeg_extended_blocks(levels, ROWS, COLUMNS)
    count = 1 if frames is None else frames
    data = _image(
        JPEG_EXTENDED, [codestream] * count, bits=12, signed=signed, frames=frames
    )
    expected = compressed.block_levels_image(levels, ROWS, COLUMNS)
    return data, _signed(expected, 12) if signed else expected


def _jpeg_ls(syntax, *, bits, near=0, signed=False, samples=1, seed=0):
    """A JPEG-LS image of random samples, and its samples as a decoder
    reconstructs and stores them."""
    rng = np.random.default_rng(_RNG_SEED + seed)
    shape = (ROWS, COLUMNS) if samples == 1 else (ROWS, COLUMNS, samples)
    patterns = rng.integers(0, 1 << bits, shape)
    # Runs of one value too, which run mode codes.
    patterns[3:6, 4:20] = patterns[3, 4]
    codestream, reconstructed = jpeg_ls.encode(patterns, precision=bits, near=near)
    data = _image(syntax, [codestream], bits=bits, signed=signed, samples=samples)
    return data, _signed(reconstructed, bits) if signed else reconstructed


# Each kind of frame that pydicom 3.0.2's GDCM plugin refuses, with the
# image that tests it: (syntax, bits, signed, near, samples).
_KINDS = {
    "jpeg-extended-12": (JPEG_EXTENDED, 12, False, 0, 1),
    "jpeg-extended-12-signed": (JPEG_EXTENDED, 12, True, 0, 1),
    "jpeg-ls-lossless-6": (JPEG_LS, 6, False, 0, 1),
    "jpeg-ls-lossless-7": (JPEG_LS, 7, False, 0, 1),
    "jpeg-ls-lossless-7-signed": (JPEG_LS, 7, True, 0, 1),
    "jpeg-ls-lossless-6-rgb": (JPEG_LS, 6, False, 0, 3),
    "jpeg-ls-near-6": (JPEG_LS_NEAR, 6, False, 2, 1),
    "jpeg-ls-near-7-rgb": (JPEG_LS_NEAR, 7, False, 1, 3),
    "jpeg-ls-near-2-signed": (JPEG_LS_NEAR, 2, True, 1, 1),
    "jpeg-ls-near-4-signed": (JPEG_LS_NEAR, 4, True, 0, 1),
    "jpeg-ls-near-5-signed": (JPEG_LS_NEAR, 5, True, 3, 1),
    "jpeg-ls-near-7-signed": (JPEG_LS_NEAR, 7, True, 2, 1),
}


def _kind(name, seed=0):
    """The image of a kind of :data:`_KINDS`, and its expected samples."""
    syntax, bits, signed, near, samples = _KINDS[name]
    _needs(syntax)
    if syntax == JPEG_EXTENDED:
        return _jpeg_extended(_levels(seed, signed), signed=signed)
    return _jpeg_ls(
        syntax, bits=bits, near=near, signed=signed, samples=samples, seed=seed
    )


@pytest.mark.parametrize(
    "syntax, bits, signed, refused",
    [
        (JPEG_EXTENDED, 8, False, False),
        (JPEG_EXTENDED, 8, True, False),
        (JPEG_EXTENDED, 12, False, True),
        (JPEG_EXTENDED, 12, True, True),
        (JPEG_LS, 5, False, False),
        (JPEG_LS, 6, False, True),
        (JPEG_LS, 7, True, True),
        (JPEG_LS, 8, False, False),
        (JPEG_LS, 5, True, False),
        (JPEG_LS_NEAR, 5, False, False),
        (JPEG_LS_NEAR, 6, False, True),
        (JPEG_LS_NEAR, 7, False, True),
        (JPEG_LS_NEAR, 2, True, True),
        (JPEG_LS_NEAR, 5, True, True),
        (JPEG_LS_NEAR, 8, True, False),
        (JPEG_LS_NEAR, 12, True, False),
        (compressed.JPEG_BASELINE, 12, False, False),
        (compressed.JPEG_LOSSLESS_SV1, 7, True, False),
        (compressed.JPEG_2000_LOSSLESS, 6, False, False),
    ],
)
def test_the_frames_gdcm_refuses_are_pinned_to_imagecodecs(
    syntax, bits, signed, refused
):
    assert gdcm_refuses(syntax, bits, signed) is refused
    expected = IMAGECODECS if refused else pixel_decoding.DECODING_PLUGINS[syntax]
    assert pinned_plugin(syntax, bits, int(signed)) == expected


@pytest.mark.parametrize("bits, representation", [(None, 0), ("", 0), (12, None)])
def test_unreadable_attributes_leave_the_syntax_with_its_own_plugin(
    bits, representation
):
    assert pinned_plugin(JPEG_EXTENDED, bits, representation) == "gdcm"


def test_a_syntax_that_encapsulates_nothing_has_no_pinned_plugin():
    assert pinned_plugin(EXPLICIT_VR_LITTLE_ENDIAN, 12, 0) is None


@pytest.mark.parametrize("name", sorted(_KINDS))
def test_pydicoms_gdcm_plugin_refuses_each_kind_that_is_pinned_away_from_it(name):
    # The rules are pydicom 3.0.2's; GDCM decodes each in a process of its
    # own, since it can abort.
    pytest.importorskip("gdcm")
    data, _ = _kind(name)

    assert compressed.gdcm_outcome(data) == "raises"


@pytest.mark.parametrize("name", sorted(_KINDS))
def test_each_kind_decodes_to_the_samples_it_codes(name):
    data, expected = _kind(name)
    source = read_source(data)
    _, bits, signed, _, samples = _KINDS[name]

    assert frames_problem(source) is None
    decoded = decoded_frames(
        source,
        _attributes(bits, signed, samples),
        1,
        "MONOCHROME2" if samples == 1 else "RGB",
    )
    kind = {(8, False): "u1", (8, True): "i1", (16, False): "<u2", (16, True): "<i2"}[
        (16 if bits > 8 else 8, signed)
    ]
    assert np.array_equal(
        np.frombuffer(decoded, dtype=kind).reshape(expected.shape), expected
    )
    frame = np.asarray(next(isolated_frames(data)))
    assert np.array_equal(frame, expected)


def test_near_lossless_samples_are_within_near_of_those_coded():
    # The encoder's reconstruction is T.87's, which the decoder must give.
    _needs(JPEG_LS_NEAR)
    patterns = np.random.default_rng(_RNG_SEED).integers(0, 64, (ROWS, COLUMNS))
    codestream, reconstructed = jpeg_ls.encode(patterns, precision=6, near=3)
    data = _image(JPEG_LS_NEAR, [codestream], bits=6)

    frame = np.asarray(next(isolated_frames(data)))

    assert np.array_equal(frame, reconstructed)
    assert np.abs(frame.astype(int) - patterns).max() <= 3
    assert not np.array_equal(frame, patterns)


def test_every_frame_of_a_multi_frame_image_is_decoded():
    _needs(JPEG_EXTENDED)
    data, expected = _jpeg_extended(_levels(), frames=3)

    assert frames_problem(read_source(data)) is None
    assert [np.array_equal(f, expected) for f in isolated_frames(data)] == [True] * 3
    assert [np.array_equal(f, expected) for f in isolated_frames(data, [2, 0])] == [
        True,
        True,
    ]


@pytest.mark.parametrize("count, frames", [(2, 3), (3, 2)], ids=["fewer", "more"])
def test_frames_other_than_number_of_frames_are_refused(count, frames):
    _needs(JPEG_EXTENDED)
    codestream = compressed.jpeg_extended_blocks(_levels(), ROWS, COLUMNS)
    data = _image(JPEG_EXTENDED, [codestream] * count, bits=12, frames=frames)

    # As for frames that GDCM decodes: pydicom refuses fewer fragments than
    # frames before decoding.
    assert frames_problem(read_source(data)) in (
        TransformReason.FRAME_MISMATCH,
        TransformReason.UNDECODABLE_PIXEL_DATA,
    )


def test_a_damaged_jpeg_ls_scan_is_undecodable():
    _needs(JPEG_LS)
    patterns = np.random.default_rng(_RNG_SEED).integers(0, 64, (ROWS, COLUMNS))
    codestream, _ = jpeg_ls.encode(patterns, precision=6)
    scan = codestream.index(b"\xff\xda") + 10
    cut = codestream[: scan + 20] + b"\xff\xd9"
    data = _image(JPEG_LS, [cut], bits=6)

    assert frames_problem(read_source(data)) is TransformReason.UNDECODABLE_PIXEL_DATA
    with pytest.raises(FramesRefused) as refused:
        list(isolated_frames(data))
    assert refused.value.reason is TransformReason.UNDECODABLE_PIXEL_DATA


def test_frames_of_other_samples_are_not_the_same_pixels():
    data, _ = _kind("jpeg-extended-12")
    other, _ = _kind("jpeg-extended-12", seed=1)

    assert same_pixels(read_source(data), read_source(data))
    assert not same_pixels(read_source(data), read_source(other))


def test_without_imagecodecs_the_instance_has_no_decoder(monkeypatch):
    data, _ = _kind("jpeg-ls-lossless-6")
    real = importlib.util.find_spec

    def find_spec(name, *args, **kwargs):
        return None if name == "imagecodecs" else real(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)

    assert not pixel_decoding.decoder_available(JPEG_LS, IMAGECODECS)
    assert frames_problem(read_source(data)) is TransformReason.NO_DECODER
    with pytest.raises(FramesRefused) as refused:
        list(isolated_frames(data))
    assert refused.value.reason is TransformReason.NO_DECODER


def test_where_the_child_cannot_decode_it_the_instance_has_no_decoder(monkeypatch):
    data, _ = _kind("jpeg-extended-12")
    monkeypatch.setattr(pixel_decoding, "_IMAGECODECS_READY", {})

    def unavailable(task, *args, **kwargs):
        raise isolated_decoding.DecoderUnavailable()

    monkeypatch.setattr(isolated_decoding, "run", unavailable)

    assert frames_problem(read_source(data)) is TransformReason.NO_DECODER
    # Not remembered, since a later child may start.
    assert not pixel_decoding._IMAGECODECS_READY  # pylint: disable = protected-access


def test_a_child_whose_imagecodecs_lacks_the_codec_has_no_decoder(monkeypatch):
    data, _ = _kind("jpeg-extended-12")
    monkeypatch.setattr(pixel_decoding, "_IMAGECODECS_READY", {JPEG_EXTENDED: False})

    assert frames_problem(read_source(data)) is TransformReason.NO_DECODER


@pytest.mark.parametrize(
    "version, available",
    [("libjpeg_turbo 3.0.0/8.0", True), ("libjpeg_turbo 2.1.5/8.0", False)],
)
def test_12_bit_jpeg_needs_libjpeg_turbo_3(monkeypatch, version, available):
    imagecodecs = pytest.importorskip("imagecodecs")
    monkeypatch.setattr(imagecodecs, "jpeg8_version", lambda: version)

    assert imagecodecs_plugin.is_available(JPEG_EXTENDED) is available


def test_the_plugin_decodes_only_the_syntaxes_it_is_pinned_to():
    assert set(imagecodecs_plugin.DECODER_DEPENDENCIES) == {
        JPEG_EXTENDED,
        JPEG_LS,
        JPEG_LS_NEAR,
    }
    assert not imagecodecs_plugin.is_available(compressed.JPEG_BASELINE)


def test_pydicoms_own_decoders_never_hold_the_plugin():
    data, _ = _kind("jpeg-ls-lossless-6")

    assert frames_problem(read_source(data)) is None
    for syntax in imagecodecs_plugin.DECODER_DEPENDENCIES:
        decoder = pydicom.pixels.get_decoder(syntax)
        assert IMAGECODECS not in decoder.available_plugins
        assert IMAGECODECS not in decoder.missing_dependencies
        # So pydicom, asked in the engine's process, cannot decode with it.
        with pytest.raises(ValueError):
            next(
                pydicom.pixels.iter_pixels(
                    io.BytesIO(data), decoding_plugin=IMAGECODECS
                )
            )


# Decodes every kind as the engine does, then says whether imagecodecs was
# imported in the engine's process.
_PARENT_IMPORTS = """
import sys
from pymedphys._dicom.deidentify import pixel_decoding
from pymedphys._dicom.deidentify.source import read_source
for path in sys.argv[1:]:
    data = open(path, "rb").read()
    assert pixel_decoding.frames_problem(read_source(data)) is None
    assert len(list(pixel_decoding.isolated_frames(data))) == 1
print("imagecodecs" in sys.modules)
"""


def test_imagecodecs_is_never_imported_in_the_engines_process(tmp_path):
    paths = []
    for name in ("jpeg-extended-12", "jpeg-ls-near-2-signed"):
        data, _ = _kind(name)
        path = tmp_path / f"{name}.dcm"
        path.write_bytes(data)
        paths.append(str(path))

    completed = subprocess.run(
        [sys.executable, "-c", _PARENT_IMPORTS, *paths],
        capture_output=True,
        check=True,
        text=True,
        timeout=300,
    )

    assert completed.stdout.strip() == "False"


def test_a_kept_compressed_image_is_written_as_received():
    data, expected = _kind("jpeg-extended-12-signed")

    result = _basic_transform()(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed), result
    assert read_source(result.data).transfer_syntax == JPEG_EXTENDED
    (frame,) = isolated_frames(result.data)
    assert np.array_equal(frame, expected)


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
@pytest.mark.parametrize("name", ["jpeg-extended-12", "jpeg-ls-near-7-signed"])
def test_clean_pixel_data_blacks_out_and_writes_the_decoded_frames(name):
    data, expected = _kind(name)
    finder = Finder()

    result = _cleaning_transform(finder)(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence)
    assert np.array_equal(finder.seen[0], expected)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.file_meta.TransferSyntaxUID == EXPLICIT_VR_LITTLE_ENDIAN
    pixels = pydicom.pixels.pixel_array(written)
    inside = _inside(expected.shape)
    assert np.all(pixels[inside] == expected.min())
    assert np.array_equal(pixels[~inside], expected[~inside])


@pytest.mark.parametrize("name", ["jpeg-extended-12-signed", "jpeg-ls-lossless-6-rgb"])
def test_a_qc_preview_decodes_the_frames_in_the_child_as_a_native_copy_shows(
    name, monkeypatch
):
    data, expected = _kind(name)
    calls = []
    real = isolated_decoding.run

    def recorded(task, *args, **kwargs):
        calls.append(task.__name__)
        return real(task, *args, **kwargs)

    monkeypatch.setattr(isolated_decoding, "run", recorded)

    assert _pngs({0: data}, {0}) == _pngs({0: _native(data, expected)}, {0})
    assert "_frame_decoded" in calls


def test_a_qc_preview_of_an_undecodable_frame_says_so():
    _needs(JPEG_LS)
    patterns = np.random.default_rng(_RNG_SEED).integers(0, 64, (ROWS, COLUMNS))
    codestream, _ = jpeg_ls.encode(patterns, precision=6)
    scan = codestream.index(b"\xff\xda") + 10
    data = _image(JPEG_LS, [codestream[: scan + 20] + b"\xff\xd9"], bits=6)

    shown = qc_previews.previews_of({0: data}, {0})

    assert [entry.reason for entry in shown.not_previewed] == [
        NotPreviewedReason.UNREADABLE
    ]


def _native(data, frame):
    """The image ``data`` with ``frame`` as its native Pixel Data."""
    dataset = pydicom.dcmread(io.BytesIO(data))
    kind = {1: "u", 2: "<u"}[2 if dataset.BitsAllocated > 8 else 1]
    if dataset.PixelRepresentation == 1:
        kind = kind.replace("u", "i")
    dataset.PixelData = (
        np.asarray(frame).astype(f"{kind}{dataset.BitsAllocated // 8}").tobytes()
    )
    dataset["PixelData"].VR = "OW" if dataset.BitsAllocated > 8 else "OB"
    dataset["PixelData"].is_undefined_length = False
    return synthetic.written(dataset, EXPLICIT_VR_LITTLE_ENDIAN)


def test_with_the_user_extra_imagecodecs_decodes_each_syntax_it_is_pinned_to():
    # The ``user`` extra declares imagecodecs; the ``dicom`` extra does not.
    pytest.importorskip("imagecodecs")

    assert all(
        pixel_decoding.decoder_available(syntax, IMAGECODECS)
        for syntax in imagecodecs_plugin.DECODER_DEPENDENCIES
    )
