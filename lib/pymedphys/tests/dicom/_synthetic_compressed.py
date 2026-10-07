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

"""Synthetic compressed pixel data, encoded here or by an installed encoder.

No real image is used. JPEG Lossless (ITU-T T.81 Process 14, Annex H) has
no encoder in pydicom or its plugins, so :func:`jpeg_lossless` encodes one
here, with a single Huffman table in which every difference category has
a 5-bit code. The other syntaxes are encoded by pydicom (RLE Lossless),
Pillow (JPEG Baseline), or pylibjpeg-openjpeg (JPEG 2000), which a test
skips without. :func:`compressed_corpus` writes the synthetic corpus's
images again in these syntaxes, with text planted in their codestreams.
"""

import dataclasses
import io
import struct
from collections.abc import Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import _synthetic_references as synthetic

JPEG_BASELINE = "1.2.840.10008.1.2.4.50"
JPEG_EXTENDED = "1.2.840.10008.1.2.4.51"
JPEG_LOSSLESS = "1.2.840.10008.1.2.4.57"
JPEG_LOSSLESS_SV1 = "1.2.840.10008.1.2.4.70"
JPEG_LS_LOSSLESS = "1.2.840.10008.1.2.4.80"
JPEG_LS_NEAR_LOSSLESS = "1.2.840.10008.1.2.4.81"
JPEG_2000_LOSSLESS = "1.2.840.10008.1.2.4.90"
JPEG_2000 = "1.2.840.10008.1.2.4.91"
RLE_LOSSLESS = "1.2.840.10008.1.2.5"

# Difference categories 0 to 16 (T.81 Table H.2), each with a 5-bit code.
_CATEGORIES = 17
_BITS = 5


def _segment(marker: int, payload: bytes) -> bytes:
    return struct.pack(">HH", 0xFF00 | marker, len(payload) + 2) + payload


def _category(difference: int) -> int:
    return abs(difference).bit_length()


def jpeg_lossless(frame, precision: int = 16, predictor: int = 1) -> bytes:
    """Return one frame of unsigned samples as a JPEG Lossless codestream.

    Parameters
    ----------
    frame : numpy.ndarray
        Rows by columns of unsigned integers below ``2 ** precision``.
    precision : int
        Bits per sample, from 2 to 16.
    predictor : int
        Selection value 1 to 7 (T.81 Table H.1); 1 for First-Order
        Prediction.
    """
    frame = np.asarray(frame, dtype=np.int64)
    rows, columns = frame.shape
    modulus = 1 << 16
    huffman = bytes([0x00]) + bytes(_BITS - 1) + bytes([_CATEGORIES])
    huffman += bytes(16 - _BITS) + bytes(range(_CATEGORIES))
    header = (
        b"\xff\xd8"
        + _segment(0xC4, huffman)
        + _segment(
            0xC3, struct.pack(">BHHB3B", precision, rows, columns, 1, 1, 0x11, 0)
        )
        + _segment(0xDA, bytes([1, 1, 0x00, predictor, 0, 0]))
    )
    bits = []
    for row in range(rows):
        for column in range(columns):
            sample = int(frame[row, column])
            left = int(frame[row, column - 1]) if column else None
            above = int(frame[row - 1, column]) if row else None
            diagonal = int(frame[row - 1, column - 1]) if row and column else None
            if left is None and above is None:
                prediction = 1 << (precision - 1)
            elif above is None:
                prediction = left
            elif left is None:
                prediction = above
            else:
                prediction = {
                    1: left,
                    2: above,
                    3: diagonal,
                    4: left + above - diagonal,
                    5: left + ((above - diagonal) >> 1),
                    6: above + ((left - diagonal) >> 1),
                    7: (left + above) >> 1,
                }[predictor]
            difference = (sample - prediction) % modulus
            if difference >= modulus // 2:
                difference -= modulus
            category = _category(difference)
            bits.append(format(category, f"0{_BITS}b"))
            if 0 < category < 16:
                extra = difference if difference > 0 else difference - 1
                bits.append(format(extra & ((1 << category) - 1), f"0{category}b"))
    stream = "".join(bits)
    stream += "1" * (-len(stream) % 8)
    entropy = bytearray()
    for start in range(0, len(stream), 8):
        byte = int(stream[start : start + 8], 2)
        entropy.append(byte)
        if byte == 0xFF:
            entropy.append(0x00)
    return header + bytes(entropy) + b"\xff\xd9"


def jpeg_baseline(frame) -> bytes:
    """Return one 8-bit monochrome frame as a JPEG Baseline codestream, by Pillow."""
    from pymedphys._imports import PIL  # pylint: disable = import-outside-toplevel

    buffer = io.BytesIO()
    PIL.Image.fromarray(np.asarray(frame, dtype=np.uint8)).save(
        buffer, format="JPEG", quality=95
    )
    return buffer.getvalue()


def jpeg_2000(frame, *, precision: int = 16, **options) -> bytes:
    """Return one frame as a JPEG 2000 codestream, by pylibjpeg-openjpeg:
    reversible and monochrome unless ``options`` say otherwise."""
    import openjpeg  # pylint: disable = import-outside-toplevel, import-error

    options = {"photometric_interpretation": 2, **options}
    return openjpeg.encode(np.asarray(frame), bits_stored=precision, **options)


def ct_image(
    transfer_syntax: str,
    codestreams,
    *,
    rows: int,
    columns: int,
    bits: int = 16,
    number_of_frames: int | None = None,
    name: str = "FICTITIOUS^PERSON",
    offsets: Sequence[int] = (),
    extended: tuple[Sequence[int], Sequence[int]] | None = None,
) -> bytes:
    """Return a CT image file whose Pixel Data encapsulates ``codestreams``.

    One fragment per frame, each padded to an even length, after a Basic
    Offset Table of ``offsets``, empty by default (PS3.5 Section A.4), and
    with an Extended Offset Table and its lengths where ``extended`` gives
    them.
    """
    dataset = synthetic.ct_slice(0)
    dataset.PatientName = name
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows, dataset.Columns = rows, columns
    dataset.BitsAllocated = 16 if bits > 8 else 8
    dataset.BitsStored = bits
    dataset.HighBit = bits - 1
    dataset.PixelRepresentation = 0
    if number_of_frames is not None:
        dataset.NumberOfFrames = number_of_frames
    dataset.PixelData = encapsulated(codestreams, offsets)
    dataset["PixelData"].VR = "OB"
    if extended is not None:
        table, lengths = extended
        dataset.ExtendedOffsetTable = struct.pack(f"<{len(table)}Q", *table)
        dataset["ExtendedOffsetTable"].VR = "OV"
        dataset.ExtendedOffsetTableLengths = struct.pack(f"<{len(lengths)}Q", *lengths)
        dataset["ExtendedOffsetTableLengths"].VR = "OV"
    return synthetic.written(dataset, transfer_syntax)


def encapsulated(codestreams, offsets: Sequence[int] = ()) -> bytes:
    """Return encapsulated Pixel Data as pydicom holds it: a Basic Offset
    Table of ``offsets``, then one fragment for each codestream, padded to an
    even length. pydicom writes the Sequence Delimitation Item after it."""
    table = struct.pack(f"<{len(offsets)}I", *offsets)
    items = [table, *(c + b"\0" * (len(c) % 2) for c in codestreams)]
    return b"".join(
        b"\xfe\xff\x00\xe0" + struct.pack("<I", len(item)) + item for item in items
    )


def frame_starts(codestreams) -> list[int]:
    """Return where each fragment's Item Tag starts, counted as offset tables
    count, with one fragment for each codestream as :func:`encapsulated`
    writes them."""
    starts, position = [], 0
    for codestream in codestreams:
        starts.append(position)
        position += 8 + len(codestream) + len(codestream) % 2
    return starts


def rle_ct_image(frame, *, name: str = "FICTITIOUS^PERSON") -> bytes:
    """Return a 16-bit CT image file in RLE Lossless, encoded by pydicom."""
    dataset = synthetic.ct_slice(0)
    dataset.PatientName = name
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows, dataset.Columns = np.asarray(frame).shape
    dataset.BitsAllocated = dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.PixelData = np.asarray(frame, dtype="<u2").tobytes()
    dataset = pydicom.dcmread(io.BytesIO(synthetic.written(dataset)))
    dataset.compress(
        pydicom.uid.RLELossless, encoding_plugin="pydicom", generate_instance_uid=False
    )
    return synthetic.written(dataset, RLE_LOSSLESS)


# The text planted in the comment and application segments of each
# codestream of :func:`compressed_corpus`; the corpus's end-to-end tests
# search every published file for its prefix.
CODESTREAM_TEXT = "SYNMK-CODESTREAM"
# The syntaxes of :func:`compressed_corpus`, taken in turn by its images.
CORPUS_SYNTAXES = (
    JPEG_LOSSLESS,
    JPEG_LOSSLESS_SV1,
    JPEG_2000_LOSSLESS,
    JPEG_2000,
    RLE_LOSSLESS,
)
_SOT = 0xFF90
_MAX_PRECISION = 16
# pylibjpeg-openjpeg encodes with six resolution levels, so neither side of
# an image it encodes may be under 2 ** 5 samples.
_SMALLEST_JPEG_2000 = 32


def compressed_corpus(corpus):
    """Return the synthetic corpus with each image written again, compressed.

    The images, the instances with Pixel Data, take :data:`CORPUS_SYNTAXES`
    in turn, each the next that can encode it, so that RLE Lossless takes
    any that the others cannot, such as 32-bit samples, and JPEG 2000 none
    smaller than 32 by 32. Each frame of a JPEG
    codestream gets a comment and an Exif APP1 segment after its SOI marker,
    and each of a JPEG 2000 codestream a comment at the end of its main
    header, holding :data:`CODESTREAM_TEXT` and the file's name. Every other
    element is written as pydicom reads it, in Explicit VR Little Endian, so
    the planted attributes and their places are unchanged.

    Parameters
    ----------
    corpus : SyntheticCorpus
        From :func:`~pymedphys._dicom.deidentify.synthetic_corpus.build_corpus`.

    Returns
    -------
    SyntheticCorpus
        The corpus, with each image's file and manifest's transfer syntax
        replaced.
    """
    files, images = [], 0
    for file in corpus.files:
        dataset = pydicom.dcmread(io.BytesIO(file.data))
        if "PixelData" not in dataset:
            files.append(file)
            continue
        syntax = next(
            each
            for each in (*CORPUS_SYNTAXES[images:], *CORPUS_SYNTAXES[:images])
            if _encodes(each, dataset)
        )
        images += 1
        data = _compressed(dataset, syntax, f"{CODESTREAM_TEXT}-{file.name}")
        manifest = dataclasses.replace(file.manifest, transfer_syntax=syntax)
        files.append(dataclasses.replace(file, manifest=manifest, data=data))
    return dataclasses.replace(corpus, files=tuple(files))


def _encodes(syntax, dataset) -> bool:
    """Return whether an encoder here writes the image in ``syntax``."""
    if syntax == RLE_LOSSLESS:
        return True
    if syntax in (JPEG_2000_LOSSLESS, JPEG_2000) and (
        min(dataset.Rows, dataset.Columns) < _SMALLEST_JPEG_2000
    ):
        return False
    return dataset.SamplesPerPixel == 1 and dataset.BitsStored <= _MAX_PRECISION


def _compressed(dataset, syntax, text) -> bytes:
    """Return the image written in ``syntax``, with ``text`` in its codestreams."""
    bits = dataset.BitsStored
    pixels = dataset.pixel_array
    frames = pixels if pixels.ndim == 3 else pixels[np.newaxis]
    if syntax == RLE_LOSSLESS:
        # RLE Lossless has no segment that could hold text.
        codestreams = [rle_lossless(frame) for frame in frames]
    else:
        if syntax in (JPEG_LOSSLESS, JPEG_LOSSLESS_SV1):
            # T.81 codes samples as unsigned; signed ones keep their bits.
            mask = (1 << bits) - 1
            codestreams = [
                _with_jpeg_text(
                    jpeg_lossless(
                        np.asarray(frame, dtype=np.int64) & mask,
                        precision=bits,
                        predictor=1 if syntax == JPEG_LOSSLESS_SV1 else 7,
                    ),
                    text,
                )
                for frame in frames
            ]
        else:
            codestreams = [
                _with_jpeg_2000_text(jpeg_2000(frame, precision=bits), text)
                for frame in frames
            ]
    offsets = frame_starts(codestreams) if len(codestreams) > 1 else ()
    dataset.PixelData = encapsulated(codestreams, offsets)
    dataset["PixelData"].VR = "OB"
    dataset.file_meta.TransferSyntaxUID = syntax
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, dataset, enforce_file_format=True)
    return buffer.getvalue()


def rle_lossless(frame) -> bytes:
    """Return one monochrome frame as an RLE Lossless frame (PS3.5 Annex G).

    pydicom's encoder takes samples of at most 16 bits, so this one, for any
    width, writes each byte plane, most significant first, as literal runs
    of at most 128 bytes, one more run where that makes a segment's length
    even.
    """
    frame = np.asarray(frame)
    planes = frame.astype(frame.dtype.newbyteorder(">")).view(np.uint8)
    planes = planes.reshape(*frame.shape, frame.dtype.itemsize)
    segments = []
    for plane in np.moveaxis(planes, -1, 0):
        data = plane.tobytes()
        runs = [data[i : i + 128] for i in range(0, len(data), 128)]
        if sum(1 + len(run) for run in runs) % 2:
            # A run of one byte takes two, so the odd length has a longer one.
            longer = next(i for i, run in enumerate(runs) if len(run) > 1)
            runs[longer : longer + 1] = [runs[longer][:1], runs[longer][1:]]
        segments.append(b"".join(bytes([len(run) - 1]) + run for run in runs))
    offsets, position = [], 64
    for segment in segments:
        offsets.append(position)
        position += len(segment)
    header = struct.pack("<16I", len(segments), *offsets, *([0] * (15 - len(offsets))))
    return header + b"".join(segments)


def _with_jpeg_text(codestream: bytes, text: str) -> bytes:
    """Return a JPEG codestream with a COM and an Exif APP1 segment of ``text``
    after its SOI marker."""
    planted = _segment(0xFE, text.encode("ascii"))
    planted += _segment(0xE1, b"Exif\0\0" + text.encode("ascii"))
    return codestream[:2] + planted + codestream[2:]


def _with_jpeg_2000_text(codestream: bytes, text: str) -> bytes:
    """Return a JPEG 2000 codestream with a COM segment of ``text``, in Latin
    characters, before its first SOT marker (ITU-T T.800 Section A.9.2)."""
    position = 2  # after SOC
    while struct.unpack_from(">H", codestream, position)[0] != _SOT:
        (length,) = struct.unpack_from(">H", codestream, position + 2)
        position += 2 + length
    comment = struct.pack(">H", 1) + text.encode("ascii")
    planted = struct.pack(">HH", 0xFF64, len(comment) + 2) + comment
    return codestream[:position] + planted + codestream[position:]
