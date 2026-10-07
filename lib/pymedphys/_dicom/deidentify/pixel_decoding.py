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

"""Decode every frame of compressed pixel data once, before it is released.

The engine writes encapsulated Pixel Data (7FE0,0010) back byte for byte,
without decoding it (:mod:`.preserving_writer`). Before such an instance is
released, :func:`frames_problem` shows that its pixel data are what its
attributes say they are: each frame decodes, there are as many frames as
Number of Frames (0028,0008) gives, or one where it is absent, and each has
Rows (0028,0010) by Columns (0028,0011), with Samples per Pixel (0028,0002)
samples where there are several. A frame that does not decode, or does not
match, sequesters the instance, since pixel data that cannot be read
cannot be checked or reviewed. Native pixel data are not decoded here.

Number of Frames must be greater than zero (PS3.3 Section C.7.6.6.1.1): an
explicit zero, or a value that is empty or cannot be read, is a mismatch,
never one frame.

A decoder shapes what it decodes by these attributes, so a frame of 5 rows
of 7 decodes to an array of 7 rows of 5 where the attributes say so. Each
frame's codestream header is therefore read too, before decoding, by
:func:`.frame_headers.header_problem`, which also requires the transfer
syntax to describe its coding process. RLE Lossless (PS3.5 Annex G) holds
none of what it compares; pydicom refuses a frame whose number of segments
is not Samples per Pixel times the bytes of each sample.

Before decoding, its offset tables are checked, since a decoder uses them to
find where each frame starts (PS3.5 Section A.4). A Basic Offset Table that
is not empty must hold one offset for each frame, the first 0 and each
greater than the last, and each must be where a fragment's Item Tag starts,
counted from the first Item Tag after the table. An Extended Offset Table
(7FE0,0001) must come with an empty Basic Offset Table and with Extended
Offset Table Lengths (7FE0,0002), and, since each frame is then one fragment
(PS3.3 Section C.7.6.3.1.8), must give each fragment's Item Tag in turn,
with the length of its fragment, or one less where the frame was padded
to an even length.
Otherwise the instance is sequestered as
:attr:`.reasons.TransformReason.OFFSET_TABLE_MISMATCH`.

Each transfer syntax of :data:`.source.ENCAPSULATED_TRANSFER_SYNTAXES` is
decoded by one pydicom decoding plugin, :data:`DECODING_PLUGINS`, whatever
else is installed, so that the outcome never depends on which optional
packages happen to be present or on the order in which pydicom tries them.
Where that plugin's packages are not installed, the instance is sequestered
as :attr:`.reasons.TransformReason.NO_DECODER`: it is never released
without its frames decoded.

Frames are decoded one at a time, as stored (pydicom's ``raw``), with no
conversion of colour space, so a run never holds more than one decoded
frame of an instance. pydicom's warnings and log records while it decodes
are redacted by :func:`.diagnostics.redacted_diagnostics`, and an error it
raises is replaced by a reason, never chained, since its message can quote
a value.
"""

from __future__ import annotations

import struct
import types
from collections.abc import Mapping

from pymedphys._imports import pydicom

from .diagnostics import redacted_diagnostics
from .file_layout import ElementPath
from .frame_headers import Declared, header_problem
from .reasons import TransformReason
from .source import SourceEvidence, encapsulated_pixel_data

_GDCM = "gdcm"
_PYLIBJPEG = "pylibjpeg"
_PIXEL_DATA = ElementPath((), "(7FE0,0010)")
_EXTENDED_OFFSET_TABLE = ElementPath((), "(7FE0,0001)")
_EXTENDED_OFFSET_TABLE_LENGTHS = ElementPath((), "(7FE0,0002)")
_RLE_LOSSLESS = "1.2.840.10008.1.2.5"
DECODING_PLUGINS: Mapping[str, str] = types.MappingProxyType(
    {
        "1.2.840.10008.1.2.4.50": _GDCM,  # JPEG Baseline (Process 1)
        "1.2.840.10008.1.2.4.51": _GDCM,  # JPEG Extended (Process 2 and 4)
        "1.2.840.10008.1.2.4.57": _GDCM,  # JPEG Lossless (Process 14)
        "1.2.840.10008.1.2.4.70": _GDCM,  # JPEG Lossless, First-Order Prediction
        "1.2.840.10008.1.2.4.80": _GDCM,  # JPEG-LS Lossless
        "1.2.840.10008.1.2.4.81": _GDCM,  # JPEG-LS Near-Lossless
        "1.2.840.10008.1.2.4.90": _PYLIBJPEG,  # JPEG 2000 Lossless Only
        "1.2.840.10008.1.2.4.91": _PYLIBJPEG,  # JPEG 2000
        "1.2.840.10008.1.2.4.201": _PYLIBJPEG,  # HTJ2K Lossless Only
        "1.2.840.10008.1.2.4.202": _PYLIBJPEG,  # HTJ2K with RPCL, Lossless Only
        "1.2.840.10008.1.2.4.203": _PYLIBJPEG,  # HTJ2K
        _RLE_LOSSLESS: "pydicom",  # which pydicom decodes itself
    }
)
"""The pydicom decoding plugin for each transfer syntax that encapsulates
Pixel Data: GDCM, through python-gdcm, for JPEG and JPEG-LS; pylibjpeg, with
pylibjpeg-openjpeg, for JPEG 2000 and HTJ2K; and pydicom's own for RLE
Lossless. Each is licensed at least as permissively as PyMedPhys's Apache
License 2.0, which is why JPEG and JPEG-LS are not decoded by
pylibjpeg-libjpeg, under the GNU GPL version 3."""


def decoder_available(transfer_syntax: str) -> bool:
    """Return whether the plugin that decodes ``transfer_syntax`` is installed."""
    plugin = DECODING_PLUGINS.get(transfer_syntax)
    if plugin is None:
        return False
    with redacted_diagnostics():
        decoder = pydicom.pixels.get_decoder(transfer_syntax)
        return plugin in decoder.available_plugins


def frames_problem(source: SourceEvidence) -> TransformReason | None:
    """Return why an instance's compressed frames cannot be shown sound, if they cannot.

    Parameters
    ----------
    source : SourceEvidence

    Returns
    -------
    TransformReason or None
        ``None`` where the transfer syntax does not encapsulate Pixel Data,
        where the data set has no Pixel Data, or where every frame decodes
        and matches the attributes; otherwise
        :attr:`~.reasons.TransformReason.NO_DECODER`,
        :attr:`~.reasons.TransformReason.OFFSET_TABLE_MISMATCH`,
        :attr:`~.reasons.TransformReason.UNDECODABLE_PIXEL_DATA`, or
        :attr:`~.reasons.TransformReason.FRAME_MISMATCH`.
    """
    plugin = DECODING_PLUGINS.get(source.transfer_syntax)
    if plugin is None or _PIXEL_DATA not in source:
        return None
    if not decoder_available(source.transfer_syntax):
        return TransformReason.NO_DECODER
    try:
        with redacted_diagnostics():
            return _decoded_problem(source, plugin)
    # pydicom and its plugins raise many types for pixel data they cannot
    # decode, and a message can quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        return TransformReason.UNDECODABLE_PIXEL_DATA


def _decoded_problem(source: SourceEvidence, plugin: str) -> TransformReason | None:
    """Return why the frames do not match the attributes, if they do not,
    having checked the offset tables and each frame's codestream header and
    decoded each frame with ``plugin``.

    Raises
    ------
    Exception
        Whatever pydicom or the plugin raises for a frame it cannot decode.
    """
    dataset = source.dataset()
    expected = _expected(dataset)
    if expected is None:
        return TransformReason.FRAME_MISMATCH
    frames, shape = expected
    if not _offsets_match(source, frames):
        return TransformReason.OFFSET_TABLE_MISMATCH
    headers = _headers_problem(source, dataset, frames)
    if headers is not None:
        return headers
    decoded = 0
    for frame in pydicom.pixels.iter_pixels(dataset, raw=True, decoding_plugin=plugin):
        if decoded == frames or frame.shape != shape:
            return TransformReason.FRAME_MISMATCH
        decoded += 1
    return None if decoded == frames else TransformReason.FRAME_MISMATCH


def _expected(dataset: pydicom.Dataset) -> tuple[int, tuple[int, ...]] | None:
    """Return how many frames the attributes give, and each frame's shape,
    or ``None`` where an attribute is absent, other than Number of Frames,
    or is empty, cannot be read, or is not positive."""
    try:
        frames = int(dataset.NumberOfFrames) if "NumberOfFrames" in dataset else 1
        rows, columns = int(dataset.Rows), int(dataset.Columns)
        samples = int(dataset.SamplesPerPixel)
    except (AttributeError, TypeError, ValueError):
        return None
    if min(frames, rows, columns, samples) < 1:
        return None
    return frames, ((rows, columns) if samples == 1 else (rows, columns, samples))


def _headers_problem(
    source: SourceEvidence, dataset: pydicom.Dataset, frames: int
) -> TransformReason | None:
    """Return why a frame's codestream header does not match the attributes,
    if one does not, as above.

    Frames are found as pydicom finds them to decode them, by
    :func:`pydicom.encaps.generate_frames`, after the offset tables are
    shown sound.
    """
    if source.transfer_syntax == _RLE_LOSSLESS or not encapsulated_pixel_data(
        source, _PIXEL_DATA
    ):
        return None
    declared = Declared(
        int(dataset.Rows),
        int(dataset.Columns),
        int(dataset.SamplesPerPixel),
        int(dataset.BitsStored),
        int(dataset.PixelRepresentation) == 1,
        str(dataset.PhotometricInterpretation),
    )
    extended = None
    if _EXTENDED_OFFSET_TABLE in source:
        extended = (
            source.value_field(_EXTENDED_OFFSET_TABLE),
            source.value_field(_EXTENDED_OFFSET_TABLE_LENGTHS),
        )
    for codestream in pydicom.encaps.generate_frames(
        _value(source), number_of_frames=frames, extended_offsets=extended
    ):
        problem = header_problem(source.transfer_syntax, codestream, declared)
        if problem is not None:
            return problem
    return None


def _offsets_match(source: SourceEvidence, frames: int) -> bool:
    """Return whether the offset tables give where frames start, as above.

    Pixel Data that is not encapsulated, such as Pixel Data of VR OW in a
    syntax that encapsulates it, has no offset tables to check; the writer
    refuses to write it (:mod:`.preserving_writer`).
    """
    if not encapsulated_pixel_data(source, _PIXEL_DATA):
        return True
    table, fragments = _fragments(source)
    starts = [start for start, _ in fragments]
    if _EXTENDED_OFFSET_TABLE in source or _EXTENDED_OFFSET_TABLE_LENGTHS in source:
        if table or _EXTENDED_OFFSET_TABLE not in source:
            return False
        if _EXTENDED_OFFSET_TABLE_LENGTHS not in source:
            return False
        offsets = _unsigned(source.value_field(_EXTENDED_OFFSET_TABLE), "Q")
        lengths = _unsigned(source.value_field(_EXTENDED_OFFSET_TABLE_LENGTHS), "Q")
        return (
            offsets is not None
            and lengths is not None
            and offsets == starts
            and len(lengths) == frames == len(fragments)
            and all(
                length in (size, size - 1)
                for length, (_, size) in zip(lengths, fragments)
            )
        )
    if not table:
        return True
    offsets = _unsigned(table, "I")
    return (
        offsets is not None
        and len(offsets) == frames
        and offsets[0] == 0
        and all(a < b for a, b in zip(offsets, offsets[1:]))
        and set(offsets) <= set(starts)
    )


def _fragments(source: SourceEvidence) -> tuple[bytes, list[tuple[int, int]]]:
    """Return the Basic Offset Table, and where each fragment's Item Tag is
    and how long its value is.

    Positions are counted from the first byte of the Item Tag after the
    Basic Offset Table item, as offset tables count them. The reader has
    already shown the items sound (:mod:`.file_layout`).
    """
    value = _value(source)
    (length,) = struct.unpack_from("<I", value, 4)
    table = value[8 : 8 + length]
    base = position = 8 + length
    fragments: list[tuple[int, int]] = []
    while value[position : position + 4] == b"\xfe\xff\x00\xe0":
        (length,) = struct.unpack_from("<I", value, position + 4)
        fragments.append((position - base, length))
        position += 8 + length
    return table, fragments


def _value(source: SourceEvidence) -> bytes:
    """Return the Value Field of encapsulated Pixel Data, from its Basic Offset
    Table's Item Tag to its Sequence Delimitation Item."""
    extent = source.element(_PIXEL_DATA)
    return source.encoded(_PIXEL_DATA)[extent.value_start - extent.start :]


def _unsigned(value: bytes, code: str) -> list[int] | None:
    """Return little endian unsigned integers, or ``None`` where ``value`` is
    not a whole number of them."""
    size = struct.calcsize(code)
    if len(value) % size:
        return None
    return list(struct.unpack(f"<{len(value) // size}{code}", value))
