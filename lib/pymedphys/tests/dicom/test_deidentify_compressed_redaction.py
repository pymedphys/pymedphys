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

"""Clean Pixel Data for compressed Pixel Data (D-037, D-048).

Each frame is decoded, in the child process for GDCM and pylibjpeg, the
finder searches the decoded frames, and the instance is written
uncompressed, in Explicit VR Little Endian, with or without a region, so
that its previews show the samples that the decoder gave. A reviewer's
verdict applies only where the frames decode to the samples whose SHA-256
the reviewed QC pack records.

Every file is synthetic, and every finder is a stand-in that gives fixed
regions, so no model is downloaded and no network is reached.
"""

import base64
import hashlib
import io
import json
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    instance_transform,
    isolated_decoding,
    markers,
    pixel_decoding,
    qc_pack,
    run,
)
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
)
from pymedphys._dicom.deidentify.pixel_cleaning import (
    PixelDataRefused,
    PixelsNotReviewed,
    as_received,
    black_out,
    black_out_reviewed,
    redaction_problem,
)
from pymedphys._dicom.deidentify.preservation import (
    Expectations,
    PreservationFailed,
    PreservationReason,
    verify_preservation,
)
from pymedphys._dicom.deidentify.preserving_writer import (
    WriteReason,
    WriteRefused,
    write_data_set,
)
from pymedphys._dicom.deidentify.qc_attestation import Redaction, RedactionVerdict
from pymedphys._dicom.deidentify.qc_pack import QcPackError, RedactionEntry
from pymedphys._dicom.deidentify.reasons import (
    HeldPixelData,
    PixelDataReason,
    TransformReason,
)
from pymedphys._dicom.deidentify.redaction_review import (
    RedactionReview,
    read_redaction_review,
)
from pymedphys._dicom.deidentify.run_qc import RedactionMaterial
from pymedphys._dicom.deidentify.source import (
    ENCAPSULATED_TRANSFER_SYNTAXES,
    EXPLICIT_VR_LITTLE_ENDIAN,
    read_source,
)
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _synthetic_compressed as compressed
from . import _synthetic_references as synthetic
from .test_deidentify_pixel_cleaning import (
    BOX,
    KEY,
    Finder,
    _codes,
    _ct,
    _inside,
    _transform,
    _transformed,
)
from .test_deidentify_redaction_review import _attest, _policy, _run, _write

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

REFERENCE = "A-" + "0123456789abcdef" * 2
CODE = "113101"
# pylibjpeg-openjpeg encodes with six resolution levels, so neither side of
# a JPEG 2000 image may be under 32 samples.
ROWS, COLUMNS = 32, 48
EXPLICIT_VR = EXPLICIT_VR_LITTLE_ENDIAN
# A region of the reviewer's own, beside the finder's BOX.
REVISED = TextBox(10, 10, 14, 20)


def _needs(syntax):
    if not pixel_decoding.decoder_available(syntax):
        pytest.skip("the decoder pinned to the transfer syntax is not installed")


def _monochrome(start=0):
    """A 12-bit frame, rows by columns, with every value its own."""
    values = np.arange(ROWS * COLUMNS, dtype=np.uint16).reshape(ROWS, COLUMNS)
    return ((values * 7 + start) % 4096).astype(np.uint16)


def _jpeg_2000_ct(frames, *, extended=False):
    """A CT image of ``frames`` in JPEG 2000 Lossless Only, which pylibjpeg
    decodes in the child process, one fragment to a frame."""
    codestreams = [compressed.jpeg_2000(frame, precision=12) for frame in frames]
    starts = compressed.frame_starts(codestreams)
    return compressed.ct_image(
        compressed.JPEG_2000_LOSSLESS,
        codestreams,
        rows=ROWS,
        columns=COLUMNS,
        bits=12,
        number_of_frames=len(frames) if len(frames) > 1 else None,
        extended=((starts, [len(c) for c in codestreams]) if extended else None),
    )


def _rle_ct(frame):
    """A 16-bit CT image in RLE Lossless, which pydicom decodes in process."""
    return compressed.rle_ct_image(frame)


# Each syntax, by whether its decoder runs in the child, with its image.
_IMAGES = {
    "child": (compressed.JPEG_2000_LOSSLESS, lambda f: _jpeg_2000_ct([f])),
    "in process": (compressed.RLE_LOSSLESS, _rle_ct),
}


def _colour():
    """An 8-bit RGB frame, rows by columns by 3, with smooth gradients, which
    JPEG Baseline keeps close to."""
    rows, columns = np.mgrid[0:ROWS, 0:COLUMNS]
    return np.stack([rows * 6, columns * 5, (rows + columns) * 3], axis=-1).astype(
        np.uint8
    )


def _colour_image(syntax, photometric, codestream):
    dataset = synthetic.ct_slice(0)
    dataset.SamplesPerPixel = 3
    dataset.PhotometricInterpretation = photometric
    dataset.PlanarConfiguration = 0
    dataset.Rows, dataset.Columns = ROWS, COLUMNS
    dataset.BitsAllocated = dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    dataset.PixelData = compressed.encapsulated([codestream])
    dataset["PixelData"].VR = "OB"
    return synthetic.written(dataset, syntax)


def _jpeg_baseline_colour():
    """A colour image in JPEG Baseline, which Pillow codes as YCbCr with
    subsampled chrominance: YBR_FULL_422."""
    from pymedphys._imports import PIL  # pylint: disable = import-outside-toplevel

    buffer = io.BytesIO()
    PIL.Image.fromarray(_colour()).save(buffer, format="JPEG", quality=95)
    return _colour_image(compressed.JPEG_BASELINE, "YBR_FULL_422", buffer.getvalue())


def _jpeg_2000_colour():
    """A colour image in JPEG 2000 Lossless Only, with the reversible colour
    transform: YBR_RCT."""
    import openjpeg  # pylint: disable = import-outside-toplevel, import-error

    codestream = openjpeg.encode(
        _colour(), photometric_interpretation=1, use_mct=True, bits_stored=8
    )
    return _colour_image(compressed.JPEG_2000_LOSSLESS, "YBR_RCT", codestream)


def _decoding_calls(monkeypatch):
    """Record each frame that :func:`pixel_decoding.decoded_frames` sends to
    the child, by the plugin that decodes it."""
    calls = []
    real = isolated_decoding.run

    def recorded(task, *args, **kwargs):
        if task is pixel_decoding._frame_decoded:  # pylint: disable = protected-access
            calls.append(args[1])
        return real(task, *args, **kwargs)

    monkeypatch.setattr(isolated_decoding, "run", recorded)
    return calls


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
@pytest.mark.parametrize("where", sorted(_IMAGES))
def test_compressed_frames_are_decoded_and_blacked_out(where, monkeypatch):
    syntax, image = _IMAGES[where]
    _needs(syntax)
    frame = _monochrome() if where == "child" else _monochrome() * 16
    source = read_source(image(frame))
    calls = _decoding_calls(monkeypatch)
    finder = Finder()

    redaction = black_out(source, source.dataset(), finder)

    assert redaction is not None
    assert np.array_equal(finder.seen[0], frame)
    assert redaction.decoded == frame.astype("<u2").tobytes()
    assert redaction.decoded_sha256 == hashlib.sha256(redaction.decoded).digest()
    assert redaction.transfer_syntax == EXPLICIT_VR
    assert redaction.layout.photometric == "MONOCHROME2"
    written = np.frombuffer(redaction.value, dtype="<u2").reshape(frame.shape)
    inside = _inside(frame.shape)
    assert np.all(written[inside] == frame.min())
    assert np.array_equal(written[~inside], frame[~inside])
    # GDCM and pylibjpeg decode in the child, frame by frame; pydicom's
    # own RLE decoder in process.
    assert calls == (["pylibjpeg"] if where == "child" else [])


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_each_frame_is_decoded_on_its_own_and_searched():
    _needs(compressed.JPEG_2000_LOSSLESS)
    frames = [_monochrome(start=100 * n) for n in range(3)]
    source = read_source(_jpeg_2000_ct(frames, extended=True))
    finder = Finder(frames={1})

    redaction = black_out(source, source.dataset(), finder)

    assert redaction is not None
    assert [np.array_equal(seen, f) for seen, f in zip(finder.seen, frames)] == [
        True
    ] * 3
    assert [regions.frame for regions in redaction.regions] == [1]
    assert redaction.decoded == b"".join(f.astype("<u2").tobytes() for f in frames)


def test_compressed_pixel_data_without_text_is_still_written_as_decoded():
    _needs(compressed.JPEG_2000_LOSSLESS)
    frame = _monochrome()
    source = read_source(_jpeg_2000_ct([frame]))

    redaction = black_out(source, source.dataset(), Finder(boxes=()))

    assert redaction is not None
    assert not redaction.changed
    assert redaction.transfer_syntax == EXPLICIT_VR
    assert redaction.value == redaction.decoded == frame.tobytes()


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_an_odd_number_of_8_bit_samples_is_padded_to_an_even_length():
    dataset = synthetic.ct_slice(0)
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows, dataset.Columns = 5, 7
    dataset.BitsAllocated = dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    frame = (np.arange(35, dtype=np.uint8) * 3).reshape(5, 7)
    dataset.PixelData = frame.tobytes() + b"\0"
    dataset = pydicom.dcmread(io.BytesIO(synthetic.written(dataset)))
    dataset.compress(
        pydicom.uid.RLELossless, encoding_plugin="pydicom", generate_instance_uid=False
    )
    source = read_source(synthetic.written(dataset, compressed.RLE_LOSSLESS))

    redaction = black_out(source, source.dataset(), Finder())

    assert redaction is not None
    assert len(redaction.value) == 36
    assert redaction.value[-1:] == b"\0"


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
@pytest.mark.parametrize(
    "image, syntax",
    [
        (_jpeg_baseline_colour, compressed.JPEG_BASELINE),
        (_jpeg_2000_colour, compressed.JPEG_2000_LOSSLESS),
    ],
)
def test_colour_is_decoded_to_rgb_and_written_so(image, syntax):
    _needs(syntax)
    data = image()
    decoded = pydicom.pixels.pixel_array(
        io.BytesIO(data),
        decoding_plugin=pixel_decoding.DECODING_PLUGINS[syntax],
    )

    result = _transformed(_transform(), data)

    assert isinstance(result, run.Transformed), result
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.file_meta.TransferSyntaxUID == EXPLICIT_VR
    assert written.PhotometricInterpretation == "RGB"
    assert written.PlanarConfiguration == 0
    pixels = pydicom.pixels.pixel_array(written)
    inside = _inside((ROWS, COLUMNS))
    assert np.all(pixels[inside] == 0)
    assert np.array_equal(pixels[~inside], decoded[~inside])
    if syntax == compressed.JPEG_2000_LOSSLESS:
        assert np.array_equal(pixels[~inside], _colour()[~inside])


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_cleaned_compressed_image_is_written_uncompressed_and_held():
    _needs(compressed.JPEG_2000_LOSSLESS)
    frame = _monochrome()
    data = _jpeg_2000_ct([frame], extended=True)

    result = _transformed(_transform(), data)

    assert isinstance(result, run.Transformed), result
    assert isinstance(result.evidence, HeldEvidence)
    assert getattr(result.evidence, "held") == (
        HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT),
    )
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.file_meta.TransferSyntaxUID == EXPLICIT_VR
    assert written["PixelData"].VR == "OW"
    assert not written["PixelData"].is_undefined_length
    for keyword in ("ExtendedOffsetTable", "ExtendedOffsetTableLengths"):
        assert keyword not in written
    assert written.PhotometricInterpretation == "MONOCHROME2"
    pixels = pydicom.pixels.pixel_array(written)
    inside = _inside(frame.shape)
    assert np.all(pixels[inside] == frame.min())
    assert np.array_equal(pixels[~inside], frame[~inside])
    # Held, so it does not claim the option.
    assert CODE not in _codes(written)
    (material,) = [m for m in result.qc if isinstance(m, RedactionMaterial)]
    assert material.decoded_sha256 == hashlib.sha256(frame.tobytes()).digest()
    # The source as received is shown from its decoded frames, uncompressed,
    # so that the engine's process never decodes the codestream to show it.
    shown = pydicom.dcmread(io.BytesIO(material.source))
    assert shown.file_meta.TransferSyntaxUID == EXPLICIT_VR
    assert shown.PixelData == frame.tobytes()
    assert shown.SOPInstanceUID == pydicom.dcmread(io.BytesIO(data)).SOPInstanceUID
    for keyword in ("ExtendedOffsetTable", "ExtendedOffsetTableLengths"):
        assert keyword not in shown


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_the_source_is_shown_as_the_child_decoded_it(monkeypatch):
    _needs(compressed.JPEG_2000_LOSSLESS)
    data = _jpeg_2000_ct([_monochrome()])
    _decoded_otherwise(monkeypatch, 5)

    result = _transformed(_transform(), data)

    assert isinstance(result, run.Transformed), result
    (material,) = [m for m in result.qc if isinstance(m, RedactionMaterial)]
    shown = pydicom.dcmread(io.BytesIO(material.source))
    assert shown.PixelData == _monochrome(5).tobytes()
    # Written and shown as received are the same decode, outside the region.
    written = pydicom.pixels.pixel_array(pydicom.dcmread(io.BytesIO(result.data)))
    inside = _inside((ROWS, COLUMNS))
    assert np.array_equal(written[~inside], pydicom.pixels.pixel_array(shown)[~inside])


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_compressed_image_without_text_is_written_uncompressed_and_held():
    _needs(compressed.JPEG_2000_LOSSLESS)
    frame = _monochrome()
    data = _jpeg_2000_ct([frame], extended=True)

    result = _transformed(_transform(Finder(boxes=())), data)

    assert isinstance(result, run.Transformed), result
    assert getattr(result.evidence, "held") == (
        HeldPixelData(PixelDataReason.NO_TEXT_FOUND),
    )
    written = pydicom.dcmread(io.BytesIO(result.data))
    # The decoded frames, as the previews show them and a release writes them.
    assert written.file_meta.TransferSyntaxUID == EXPLICIT_VR
    assert "ExtendedOffsetTable" not in written
    assert written.PixelData == frame.tobytes()
    (material,) = [m for m in result.qc if isinstance(m, RedactionMaterial)]
    assert material.decoded_sha256 is not None
    assert material.source is None


def _sent_instead(monkeypatch, sent):
    """Have the child send ``sent`` back for each frame it decodes."""
    real = isolated_decoding.run

    def run_(task, *args, **kwargs):
        if task is pixel_decoding._frame_decoded:  # pylint: disable = protected-access
            if isinstance(sent, BaseException):
                raise sent
            return sent
        return real(task, *args, **kwargs)

    monkeypatch.setattr(isolated_decoding, "run", run_)


def _good():
    frame = _monochrome()
    return ["MONOCHROME2", "<u2", [ROWS, COLUMNS], _base64(frame.tobytes())]


def _base64(data):
    return base64.b64encode(data).decode("ascii")


@pytest.mark.parametrize(
    "change, reason",
    [
        ({0: "RGB"}, TransformReason.UNCLEANABLE_PIXEL_DATA),
        ({0: 2}, TransformReason.UNCLEANABLE_PIXEL_DATA),
        ({1: ">u2"}, TransformReason.FRAME_MISMATCH),
        ({1: "<i2"}, TransformReason.FRAME_MISMATCH),
        ({1: "numpy.uint16"}, TransformReason.FRAME_MISMATCH),
        ({2: [COLUMNS, ROWS]}, TransformReason.FRAME_MISMATCH),
        ({2: [ROWS, COLUMNS, 1]}, TransformReason.FRAME_MISMATCH),
        ({3: "!" * 8}, TransformReason.FRAME_MISMATCH),
        ({3: _base64(b"\0" * 10)}, TransformReason.FRAME_MISMATCH),
        ({3: ["not", "text"]}, TransformReason.FRAME_MISMATCH),
        ({4: "more"}, TransformReason.FRAME_MISMATCH),
    ],
)
def test_what_the_child_sends_back_is_checked_before_it_is_used(
    monkeypatch, change, reason
):
    _needs(compressed.JPEG_2000_LOSSLESS)
    source = read_source(_jpeg_2000_ct([_monochrome()]))
    sent = _good()
    for index, value in change.items():
        if index < len(sent):
            sent[index] = value
        else:
            sent.append(value)
    _sent_instead(monkeypatch, sent)

    with pytest.raises(PixelDataRefused) as refused:
        black_out(source, source.dataset(), Finder())
    assert refused.value.reason is reason


def test_samples_that_the_child_sends_back_in_the_expected_form_are_taken(
    monkeypatch,
):
    _needs(compressed.JPEG_2000_LOSSLESS)
    source = read_source(_jpeg_2000_ct([_monochrome()]))
    other = _monochrome(start=5)
    sent = _good()
    sent[3] = _base64(other.tobytes())
    _sent_instead(monkeypatch, sent)

    redaction = black_out(source, source.dataset(), Finder(boxes=()))

    # Other samples than the codestream holds become the decoded frames; a
    # reviewer sees them before any release, and their digest binds the
    # verdict.
    assert redaction is not None
    assert redaction.decoded == other.tobytes()


@pytest.mark.parametrize(
    "raised, reason",
    [
        (isolated_decoding.DecoderUnavailable(), TransformReason.NO_DECODER),
        (isolated_decoding.DecoderEnded(), TransformReason.UNDECODABLE_PIXEL_DATA),
        (isolated_decoding.DecodingFailed(), TransformReason.UNDECODABLE_PIXEL_DATA),
    ],
)
def test_a_frame_that_the_child_does_not_decode_refuses_the_instance(
    monkeypatch, raised, reason
):
    _needs(compressed.JPEG_2000_LOSSLESS)
    source = read_source(_jpeg_2000_ct([_monochrome()]))
    _sent_instead(monkeypatch, raised)

    with pytest.raises(PixelDataRefused) as refused:
        black_out(source, source.dataset(), Finder())
    assert refused.value.reason is reason


def test_a_colour_that_does_not_decode_to_rgb_is_refused_before_decoding(
    monkeypatch,
):
    _needs(compressed.JPEG_2000_LOSSLESS)
    dataset = pydicom.dcmread(io.BytesIO(_jpeg_2000_ct([_monochrome()])))
    dataset.PhotometricInterpretation = "PALETTE COLOR"
    source = read_source(synthetic.written(dataset, compressed.JPEG_2000_LOSSLESS))
    calls = _decoding_calls(monkeypatch)

    with pytest.raises(PixelDataRefused) as refused:
        black_out(source, source.dataset(), Finder())
    assert refused.value.reason is TransformReason.UNCLEANABLE_PIXEL_DATA
    assert not calls


def _written_natively(source, value, transfer_syntax=EXPLICIT_VR):
    """The source written with ``value`` as native Pixel Data."""
    dataset = source.dataset()
    dataset.PixelData = value
    dataset["PixelData"].VR = "OW"
    dataset["PixelData"].is_undefined_length = False
    for keyword in ("ExtendedOffsetTable", "ExtendedOffsetTableLengths"):
        if keyword in dataset:
            del dataset[keyword]
    return read_source(synthetic.written(dataset, transfer_syntax))


def test_written_pixel_data_that_differs_from_the_decoded_frames_is_found():
    _needs(compressed.JPEG_2000_LOSSLESS)
    source = read_source(_jpeg_2000_ct([_monochrome()]))
    redaction = black_out(source, source.dataset(), Finder())
    assert redaction is not None

    assert not redaction_problem(
        source, _written_natively(source, redaction.value), redaction
    )
    changed = bytearray(redaction.value)
    changed[-1] ^= 1
    assert redaction_problem(
        source, _written_natively(source, bytes(changed)), redaction
    )
    # In the source's compressed transfer syntax, it is not as planned.
    assert redaction_problem(source, source, redaction)


def test_only_encapsulated_pixel_data_is_written_uncompressed():
    native = read_source(synthetic.written(synthetic.ct_slice(0)))
    paths = frozenset(native.paths())
    with pytest.raises(WriteRefused) as refused:
        write_data_set(
            native,
            kept=paths,
            removed=frozenset(),
            replacements={},
            transfer_syntax=EXPLICIT_VR,
        )
    assert refused.value.reason is WriteReason.TRANSFER_SYNTAX

    _needs(compressed.JPEG_2000_LOSSLESS)
    source = read_source(_jpeg_2000_ct([_monochrome()]))
    # Pixel Data kept as it is, rather than changed, cannot change syntax.
    with pytest.raises(PreservationFailed) as failed:
        verify_preservation(
            source,
            source,
            Expectations(kept=frozenset(source.paths()), transfer_syntax=EXPLICIT_VR),
        )
    assert failed.value.reason is PreservationReason.TRANSFER_SYNTAX


def _review(data, regions, decoded):
    digest = hashlib.sha256(data).digest()
    return RedactionReview(
        REFERENCE,
        {digest: regions},
        frozenset(),
        {} if decoded is None else {digest: decoded},
    )


def _reviewed(data, regions, decoded, finder=None):
    finder = Finder(boxes=()) if finder is None else finder
    transform = InstanceTransform(
        _policy(),
        KEY,
        finder=finder,
        redaction_review=_review(data, regions, decoded),
        unvalidated_policy=True,
    )
    return _transformed(transform, data), finder


@pytest.mark.deid_requirement("PS3.15-E.3.1-01", "PS3.15-E.3.1-02")
def test_reviewed_regions_release_frames_that_decode_as_reviewed():
    _needs(compressed.JPEG_2000_LOSSLESS)
    frame = _monochrome()
    data = _jpeg_2000_ct([frame])
    decoded = hashlib.sha256(frame.tobytes()).digest()

    result, finder = _reviewed(data, ((0, (BOX, REVISED)),), decoded)

    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    assert not finder.seen
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.file_meta.TransferSyntaxUID == EXPLICIT_VR
    assert _codes(written)[-2:] == [markers.PROFILE_CODE, CODE]
    assert written.BurnedInAnnotation == "NO"
    pixels = pydicom.pixels.pixel_array(written)
    inside = _inside(frame.shape) | _inside(frame.shape, REVISED)
    assert np.all(pixels[inside] == frame.min())
    assert np.array_equal(pixels[~inside], frame[~inside])


def test_an_approved_image_without_regions_is_released_as_decoded():
    _needs(compressed.JPEG_2000_LOSSLESS)
    frame = _monochrome()
    data = _jpeg_2000_ct([frame])

    result, _ = _reviewed(data, (), hashlib.sha256(frame.tobytes()).digest())

    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.file_meta.TransferSyntaxUID == EXPLICIT_VR
    assert written.PixelData == frame.tobytes()
    assert _codes(written)[-1] == CODE


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
@pytest.mark.parametrize("decoded", [bytes(32), None])
def test_frames_that_do_not_decode_as_reviewed_are_cleaned_and_held_again(decoded):
    _needs(compressed.JPEG_2000_LOSSLESS)
    data = _jpeg_2000_ct([_monochrome()])
    finder = Finder()

    result, _ = _reviewed(data, ((0, (REVISED,)),), decoded, finder)

    assert isinstance(result, run.Transformed), result
    assert getattr(result.evidence, "held") == (
        HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT),
    )
    assert len(finder.seen) == 1
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert CODE not in _codes(written)


def test_reviewed_regions_are_not_applied_to_other_decoded_pixels():
    _needs(compressed.JPEG_2000_LOSSLESS)
    source = read_source(_jpeg_2000_ct([_monochrome()]))

    with pytest.raises(PixelsNotReviewed):
        black_out_reviewed(
            source, source.dataset(), ((0, (BOX,)),), decoded_sha256=bytes(32)
        )


def test_a_review_records_decoded_frames_only_of_approved_files():
    with pytest.raises(QcPackError, match="decoded frames"):
        RedactionReview(REFERENCE, {}, frozenset({bytes(32)}), {bytes(32): bytes(32)})
    with pytest.raises(QcPackError, match="SHA-256"):
        RedactionReview(REFERENCE, {bytes(32): ()}, frozenset(), {bytes(32): b"1"})


@pytest.mark.parametrize("digest", ["0" * 63, "A" * 64, 7])
def test_a_redaction_entrys_decoded_digest_is_64_lowercase_hex_digits(digest):
    with pytest.raises(QcPackError, match="decoded frames"):
        RedactionEntry(
            0, PixelDataReason.NO_TEXT_FOUND, 1, 6, 8, (), decoded_sha256=digest
        )


def _numbered(data, number):
    """The image with a SOP Instance UID and Instance Number of its own."""
    dataset = pydicom.dcmread(io.BytesIO(data))
    dataset.SOPInstanceUID = synthetic.CT_SLICES[number]
    dataset.InstanceNumber = number + 1
    return synthetic.written(dataset, dataset.file_meta.TransferSyntaxUID)


def _first_and_second_runs(tmp_path, files, verdicts, finder=None, between=None):
    """Run the files under the option, with ``finder`` or one that marks BOX
    in each frame, attest the pack with the verdicts that ``verdicts`` gives
    by file name, call ``between``, if given, and run them again given the
    review."""
    _write(tmp_path / "source", files)
    first = _run(
        tmp_path / "first",
        tmp_path / "source",
        InstanceTransform(
            _policy(),
            KEY,
            finder=Finder() if finder is None else finder,
            unvalidated_policy=True,
        ),
    )
    pack = first.qc_pack.parent
    document = json.loads(first.qc_pack.read_text("utf-8"))
    positions = {
        Path(entry["source"]).name: entry["position"] for entry in document["instances"]
    }
    _attest(
        pack,
        [
            RedactionVerdict(positions[name], *verdict)
            for name, verdict in verdicts.items()
        ],
    )
    if between is not None:
        between()
    second = _run(
        tmp_path / "second",
        tmp_path / "source",
        InstanceTransform(
            _policy(),
            KEY,
            finder=Finder(),
            redaction_review=read_redaction_review(pack),
            unvalidated_policy=True,
        ),
    )
    return document, first, second


@pytest.mark.deid_requirement("PS3.15-E.3.1-01", "PS3.15-E.3.1-02")
def test_a_reviewed_compressed_image_is_released_as_its_previews_showed_it(
    tmp_path,
):
    _needs(compressed.JPEG_2000_LOSSLESS)
    frames = {"0-accepted.dcm": _monochrome(), "1-revised.dcm": _monochrome(9)}
    files = {
        name: _numbered(_jpeg_2000_ct([frame]), number)
        for number, (name, frame) in enumerate(frames.items())
    }
    files["2-unjudged.dcm"] = _numbered(_jpeg_2000_ct([_monochrome(3)]), 2)

    document, _, second = _first_and_second_runs(
        tmp_path,
        files,
        {
            "0-accepted.dcm": (Redaction.ACCEPTED,),
            "1-revised.dcm": (Redaction.REVISED, ((0, (REVISED,)),)),
        },
    )

    assert document["format"] == qc_pack.FORMAT == "pymedphys-deid-qc-pack/15"
    assert {entry["decoded_sha256"] for entry in document["redactions"]} == {
        hashlib.sha256(frame.tobytes()).hexdigest()
        for frame in (*frames.values(), _monochrome(3))
    }
    entries = json.loads(second.qc_pack.read_text("utf-8"))["instances"]
    outcomes = {Path(entry["source"]).name: entry for entry in entries}
    assert outcomes["2-unjudged.dcm"]["disposition"] == "held-for-review"
    for name, regions in (
        ("0-accepted.dcm", (BOX,)),
        ("1-revised.dcm", (BOX, REVISED)),
    ):
        assert outcomes[name]["disposition"] == "released"
        written = pydicom.dcmread(
            tmp_path / "second" / "release" / outcomes[name]["output"]
        )
        assert written.file_meta.TransferSyntaxUID == EXPLICIT_VR
        assert written.BurnedInAnnotation == "NO"
        frame = frames[name]
        inside = np.logical_or.reduce([_inside(frame.shape, r) for r in regions])
        pixels = pydicom.pixels.pixel_array(written)
        assert np.all(pixels[inside] == frame.min())
        assert np.array_equal(pixels[~inside], frame[~inside])


def _decoded_otherwise(monkeypatch, start):
    """Have the child decode every frame to the samples of
    ``_monochrome(start)``, which the codestream does not hold, as a
    subverted decoder, or another build of one, could."""
    sent = _good()
    sent[3] = _base64(_monochrome(start).tobytes())
    _sent_instead(monkeypatch, sent)


@pytest.mark.deid_requirement("PS3.15-E.3.1-01", "PS3.15-E.3.1-02")
@pytest.mark.parametrize("again", [True, False])
def test_regions_a_reviewer_adds_to_an_unmarked_image_release_what_was_previewed(
    tmp_path, monkeypatch, again
):
    # The finder marks nothing, and the reviewer adds a region. The cleaning
    # decode, in the child, differs from what the source's codestream holds.
    # What the first run wrote, and so what its previews showed, is the
    # child's decode, and the second run releases it, with the reviewer's
    # region, only if the child decodes it so again.
    _needs(compressed.JPEG_2000_LOSSLESS)
    frame = _monochrome()
    data = _jpeg_2000_ct([frame])
    _decoded_otherwise(monkeypatch, 5)
    shown = _monochrome(5)
    assert not np.array_equal(pydicom.pixels.pixel_array(io.BytesIO(data)), shown)
    # The file that the first run holds, and previews without publishing it,
    # is the child's decode.
    held = _transformed(_transform(Finder(boxes=())), data)
    assert isinstance(held, run.Transformed), held
    previewed = pydicom.dcmread(io.BytesIO(held.data))
    assert previewed.file_meta.TransferSyntaxUID == EXPLICIT_VR
    assert previewed.PixelData == shown.tobytes()

    document, _, second = _first_and_second_runs(
        tmp_path,
        {"0.dcm": data},
        {"0.dcm": (Redaction.REVISED, ((0, (REVISED,)),))},
        finder=Finder(boxes=()),
        between=None if again else lambda: _decoded_otherwise(monkeypatch, 6),
    )

    (entry,) = document["redactions"]
    assert entry["regions"] == []
    assert entry["decoded_sha256"] == hashlib.sha256(shown.tobytes()).hexdigest()
    (held,) = document["instances"]
    assert held["disposition"] == "held-for-review"
    (outcome,) = json.loads(second.qc_pack.read_text("utf-8"))["instances"]
    if not again:
        assert outcome["disposition"] == "held-for-review"
        return
    assert outcome["disposition"] == "released"
    written = pydicom.dcmread(tmp_path / "second" / "release" / outcome["output"])
    assert written.BurnedInAnnotation == "NO"
    pixels = pydicom.pixels.pixel_array(written)
    inside = _inside(frame.shape, REVISED)
    assert np.all(pixels[inside] == shown.min())
    assert np.array_equal(pixels[~inside], shown[~inside])


def test_a_pack_whose_decoded_digest_is_malformed_is_refused(tmp_path):
    _needs(compressed.JPEG_2000_LOSSLESS)
    files = {"0.dcm": _jpeg_2000_ct([_monochrome()])}
    _write(tmp_path / "source", files)
    first = _run(
        tmp_path / "first",
        tmp_path / "source",
        InstanceTransform(_policy(), KEY, finder=Finder(), unvalidated_policy=True),
    )
    pack = first.qc_pack.parent
    document = json.loads(first.qc_pack.read_text("utf-8"))
    document["redactions"][0]["decoded_sha256"] = "not a digest"
    first.qc_pack.write_text(json.dumps(document), "utf-8")
    _attest(pack, [RedactionVerdict(0, Redaction.ACCEPTED)])

    with pytest.raises(QcPackError, match="not of its format"):
        read_redaction_review(pack)


def test_a_result_can_be_given_room_beyond_the_childs_limit():
    size = (1 << 24) + 1
    with pytest.raises(isolated_decoding.DecoderEnded):
        isolated_decoding.run(bytes.decode, b"x" * size, "ascii")

    sent = isolated_decoding.run(
        bytes.decode, b"x" * size, "ascii", result_bytes=1 << 10
    )

    assert sent == "x" * size


def test_a_source_is_shown_as_decoded_only_where_pydicom_can_write_it(monkeypatch):
    _needs(compressed.JPEG_2000_LOSSLESS)
    source = read_source(_jpeg_2000_ct([_monochrome()]))
    redaction = black_out(source, source.dataset(), Finder())
    assert redaction is not None
    assert as_received(source, redaction) is not None
    native = read_source(synthetic.written(_ct(_monochrome())))
    native_redaction = black_out(native, native.dataset(), Finder())
    assert native_redaction is not None
    # Native Pixel Data is shown from the source as it is.
    assert as_received(native, native_redaction) is None

    def refused(*args, **kwargs):
        raise ValueError("a message that quotes a value")

    monkeypatch.setattr(pydicom, "dcmwrite", refused)

    # A source that pydicom cannot write in Explicit VR Little Endian has no
    # file that shows its decoded frames, and its error is not raised.
    assert as_received(source, redaction) is None


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_compressed_source_that_cannot_be_shown_as_decoded_is_not_previewed(
    tmp_path, monkeypatch
):
    # Without the source as decoded, the frame with a region cannot be shown
    # as received beside the frame as written, so the pack lists the
    # instance as not previewed, takes no digest of its pixel data, and
    # refuses a verdict on it, which so cannot release it.
    _needs(compressed.JPEG_2000_LOSSLESS)
    frame = _monochrome()
    monkeypatch.setattr(instance_transform, "as_received", lambda *_: None)
    _write(tmp_path / "source", {"0.dcm": _jpeg_2000_ct([frame])})

    first = _run(
        tmp_path / "first",
        tmp_path / "source",
        InstanceTransform(_policy(), KEY, finder=Finder(), unvalidated_policy=True),
    )

    document = json.loads(first.qc_pack.read_text("utf-8"))
    (instance,) = document["instances"]
    position = instance["position"]
    assert instance["disposition"] == "held-for-review"
    assert instance["pixel_sha256"] is None
    (entry,) = document["redactions"]
    assert entry["regions"]
    assert entry["decoded_sha256"] == hashlib.sha256(frame.tobytes()).hexdigest()
    assert document["not_previewed"] == [
        {"position": position, "reason": "source-not-shown"}
    ]
    assert not [
        preview for preview in document["previews"] if preview["kind"] == "redaction"
    ]
    with pytest.raises(QcPackError, match="not list as cleaned and previewed"):
        _attest(first.qc_pack.parent, [RedactionVerdict(position, Redaction.ACCEPTED)])


def _native_decodes(monkeypatch):
    """Record each frame that a decoding plugin other than pydicom's own
    decodes in this process, by its plugin, whatever the transfer syntax."""
    calls = []
    for syntax in ENCAPSULATED_TRANSFER_SYNTAXES:
        decoder = pydicom.pixels.get_decoder(syntax)
        plugins = decoder._available  # pylint: disable = protected-access
        for plugin, decode in list(plugins.items()):
            if plugin == "pydicom":
                continue

            def recorded(*args, plugin=plugin, decode=decode, **kwargs):
                calls.append(plugin)
                return decode(*args, **kwargs)

            monkeypatch.setitem(plugins, plugin, recorded)
    return calls


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
@pytest.mark.parametrize(
    "image, syntax",
    [
        (lambda: _jpeg_2000_ct([_monochrome()]), compressed.JPEG_2000_LOSSLESS),
        (_jpeg_baseline_colour, compressed.JPEG_BASELINE),
    ],
    ids=["pylibjpeg", "gdcm"],
)
def test_a_cleaned_compressed_image_is_previewed_without_a_native_decoder(
    tmp_path, monkeypatch, image, syntax
):
    # Under the option, GDCM and pylibjpeg decode a compressed image only in
    # the child (D-037), and the QC pack shows each frame, as written and as
    # received, from the child's decode written uncompressed, never from the
    # codestream decoded again in the engine's process, which a codestream
    # could end, or decode otherwise than the release writes (D-048).
    _needs(syntax)
    plugin = pixel_decoding.DECODING_PLUGINS[syntax]
    data = image()
    native = _native_decodes(monkeypatch)
    pydicom.pixels.pixel_array(io.BytesIO(data), decoding_plugin=plugin)
    assert native == [plugin]
    native.clear()
    child = _decoding_calls(monkeypatch)
    _write(tmp_path / "source", {"0.dcm": data})

    first = _run(
        tmp_path / "first",
        tmp_path / "source",
        InstanceTransform(_policy(), KEY, finder=Finder(), unvalidated_policy=True),
    )

    assert not native
    assert child == [plugin]
    document = json.loads(first.qc_pack.read_text("utf-8"))
    (instance,) = document["instances"]
    assert instance["pixel_sha256"] is not None
    assert not document["not_previewed"]
    shown = [
        frame
        for preview in document["previews"]
        if preview["kind"] == "redaction"
        for frame in preview["frames"]
    ]
    assert shown == [{"position": instance["position"], "frame": 0}]
