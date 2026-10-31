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
pydicom 3.0.2's GDCM plugin refuses three kinds of frame before GDCM sees
them, by Bits Stored (0028,0101) and Pixel Representation (0028,0103):
JPEG Extended at 12 bits, JPEG-LS at 6 or 7 bits, and signed JPEG-LS
Near-Lossless below 8 bits. :func:`pinned_plugin` pins those to
:data:`IMAGECODECS`, the plugin of :mod:`.imagecodecs_plugin`, instead,
whatever GDCM would do, so that each kind of frame still has one decoder
(D-055). Where the pinned plugin's packages are not installed, the
instance is sequestered as :attr:`.reasons.TransformReason.NO_DECODER`: it
is never released without its frames decoded.

Frames are decoded one at a time, as stored (pydicom's ``raw``), with no
conversion of colour space, so a run never holds more than one decoded
frame of an instance. pydicom's warnings and log records while it decodes
are redacted by :func:`.diagnostics.redacted_diagnostics`, and an error it
raises is replaced by a reason, never chained, since its message can quote
a value.

GDCM, pylibjpeg, and imagecodecs, :data:`ISOLATED_PLUGINS`, decode in a
child process, by :func:`.isolated_decoding.run`, since their native
libraries can end the process that calls them on a malformed codestream,
as GDCM does for a JPEG frame whose header makes libjpeg warn. imagecodecs
is never added to pydicom's own decoders: the child decodes with a decoder
of its own that holds it, so it decodes nothing in the engine's process,
not even to preview a file, for which :func:`isolated_frames` decodes in
the child (D-055). A frame whose decoder ends the child
is undecodable, like any other, and the next instance is decoded by a new
child; where :func:`same_pixels` decodes it, the frames are not the same.
Where the child cannot be started, the instance is sequestered as
:attr:`.reasons.TransformReason.NO_DECODER`, as where the plugin is not
installed, since its frames cannot be decoded either way. The offset tables
and codestream headers are checked in process.

Under the Clean Pixel Data Option, :func:`decoded_frames` decodes every
frame once more, for the text finder and for writing the frames
uncompressed where a region is blacked out (D-037). The child decodes one
frame at a time, from that frame's codestream and the Image Pixel
attributes that the engine read from the source, and sends back the frame's
samples as base64 text in its JSON, with their photometric interpretation,
NumPy type, and shape, each of which the engine checks against what it
expects before it takes the samples: plain data, never a type or name to
resolve. A decoder that a codestream subverts can therefore give the engine
no more than other samples of the expected size, which become output bytes
only through an instance held for review, whose every frame the QC pack
shows as written (D-037, D-048).
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import functools
import importlib.util
import io
import itertools
import struct
import types
from collections.abc import Iterator, Mapping, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import imagecodecs_plugin, isolated_decoding
from .diagnostics import redacted_diagnostics
from .file_layout import ElementPath
from .frame_headers import Declared, header_problem
from .reasons import TransformReason
from .source import SourceEvidence, encapsulated_pixel_data

_GDCM = "gdcm"
_PYLIBJPEG = "pylibjpeg"
IMAGECODECS = "pymedphys-imagecodecs"
"""The label of :mod:`.imagecodecs_plugin` in the decoders that hold it,
which are never pydicom's own."""
_JPEG_EXTENDED = imagecodecs_plugin.JPEG_EXTENDED
_JPEG_LS = frozenset(
    {imagecodecs_plugin.JPEG_LS_LOSSLESS, imagecodecs_plugin.JPEG_LS_NEAR_LOSSLESS}
)
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
# The NumPy type of a decoded sample, by Bits Allocated and whether Pixel
# Representation is 1, two's complement, as pydicom gives it.
_SAMPLE_TYPES = types.MappingProxyType(
    {
        (8, False): "|u1",
        (8, True): "|i1",
        (16, False): "<u2",
        (16, True): "<i2",
        (32, False): "<u4",
        (32, True): "<i4",
    }
)
ISOLATED_PLUGINS = frozenset({_GDCM, _PYLIBJPEG, IMAGECODECS})
"""The plugins whose native libraries can end the process that calls them
on a malformed codestream, and so decode in a child process
(:mod:`.isolated_decoding`). pydicom's own decoder of RLE Lossless is
Python, and decodes in process."""
CHILD_ONLY_PLUGINS = frozenset({IMAGECODECS})
"""The plugins that never decode in the engine's process, even to preview a
file that a check in the child has already decoded: QC previews decode
their frames by :func:`isolated_frames`."""
# Whether the decoding child can decode each transfer syntax with
# imagecodecs, once it has been asked.
_IMAGECODECS_READY: dict[str, bool] = {}


def gdcm_refuses(transfer_syntax: str, bits_stored: int, signed: bool) -> bool:
    """Return whether pydicom 3.0.2's GDCM plugin refuses frames of
    ``transfer_syntax`` with that Bits Stored and sign, before GDCM sees
    them: JPEG Extended at other than 8 bits, JPEG-LS at 6 or 7 bits, and
    signed JPEG-LS Near-Lossless below 8 bits."""
    if transfer_syntax == _JPEG_EXTENDED:
        return bits_stored != 8
    if transfer_syntax not in _JPEG_LS:
        return False
    return bits_stored in (6, 7) or (
        transfer_syntax == imagecodecs_plugin.JPEG_LS_NEAR_LOSSLESS
        and signed
        and bits_stored < 8
    )


def pinned_plugin(
    transfer_syntax: str, bits_stored: object, pixel_representation: object
) -> str | None:
    """Return the plugin pinned to decode frames of ``transfer_syntax`` with
    that Bits Stored and Pixel Representation, or ``None`` for a transfer
    syntax that does not encapsulate Pixel Data.

    The plugin of :data:`DECODING_PLUGINS`, but :data:`IMAGECODECS` for the
    frames that :func:`gdcm_refuses`. Where Bits Stored or Pixel
    Representation cannot be read as an integer, the transfer syntax's own
    plugin, whose check of the attributes then refuses the frames.
    """
    plugin = DECODING_PLUGINS.get(transfer_syntax)
    if plugin != _GDCM:
        return plugin
    try:
        bits = int(bits_stored)  # type: ignore[call-overload]
        signed = int(pixel_representation) == 1  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return plugin
    return IMAGECODECS if gdcm_refuses(transfer_syntax, bits, signed) else plugin


def _dataset_plugin(transfer_syntax: str, dataset: pydicom.Dataset) -> str | None:
    """Return :func:`pinned_plugin` for the frames of ``dataset``."""
    return pinned_plugin(
        transfer_syntax,
        dataset.get("BitsStored"),
        dataset.get("PixelRepresentation"),
    )


def decoder_available(transfer_syntax: str, plugin: str | None = None) -> bool:
    """Return whether ``plugin``, by default the plugin of
    :data:`DECODING_PLUGINS`, can decode ``transfer_syntax``.

    Whether :data:`IMAGECODECS` can is asked of the decoding child, once
    per transfer syntax, since imagecodecs is never imported in the
    engine's process; it cannot where imagecodecs is not installed or the
    child cannot be started.
    """
    if plugin is None:
        plugin = DECODING_PLUGINS.get(transfer_syntax)
    if plugin == IMAGECODECS:
        return _imagecodecs_available(transfer_syntax)
    if plugin is None or DECODING_PLUGINS.get(transfer_syntax) != plugin:
        return False
    with redacted_diagnostics():
        decoder = pydicom.pixels.get_decoder(transfer_syntax)
        return plugin in decoder.available_plugins


def _imagecodecs_available(transfer_syntax: str) -> bool:
    """Return whether the decoding child can decode ``transfer_syntax`` with
    imagecodecs, as :func:`decoder_available` describes."""
    if transfer_syntax not in imagecodecs_plugin.DECODER_DEPENDENCIES:
        return False
    if importlib.util.find_spec("imagecodecs") is None:
        return False
    ready = _IMAGECODECS_READY.get(transfer_syntax)
    if ready is None:
        try:
            with redacted_diagnostics():
                ready = (
                    isolated_decoding.run(_imagecodecs_ready, transfer_syntax) is True
                )
        # Not remembered: a later child may start.
        except isolated_decoding.DecoderUnavailable:
            return False
        except isolated_decoding.DecodingFailed:
            ready = False
        _IMAGECODECS_READY[transfer_syntax] = ready
    return ready


def _imagecodecs_ready(transfer_syntax: str) -> bool:
    """Return whether imagecodecs can decode ``transfer_syntax`` here, in
    the decoding child."""
    return IMAGECODECS in _decoder(transfer_syntax, IMAGECODECS).available_plugins


@functools.lru_cache(maxsize=None)
def _imagecodecs_decoder(transfer_syntax: str) -> pydicom.pixels.decoders.base.Decoder:
    """Return a decoder of ``transfer_syntax`` that holds only
    :mod:`.imagecodecs_plugin`, as :data:`IMAGECODECS`: never pydicom's own,
    so that adding the plugin changes nothing that pydicom decodes."""
    decoder = pydicom.pixels.decoders.base.Decoder(pydicom.uid.UID(transfer_syntax))
    decoder.add_plugin(IMAGECODECS, (imagecodecs_plugin.__name__, "_decode_frame"))
    return decoder


def _decoder(transfer_syntax: str, plugin: str) -> pydicom.pixels.decoders.base.Decoder:
    """Return the decoder that holds ``plugin`` for ``transfer_syntax``:
    pydicom's own, but for :data:`IMAGECODECS`."""
    if plugin == IMAGECODECS:
        return _imagecodecs_decoder(transfer_syntax)
    return pydicom.pixels.get_decoder(transfer_syntax)


def _iter_frames(dataset: pydicom.Dataset, plugin: str) -> Iterator["np.ndarray"]:
    """Yield each frame of ``dataset`` decoded by ``plugin``, as stored, as
    :func:`pydicom.pixels.iter_pixels` yields them with ``raw``."""
    syntax = str(dataset.file_meta.TransferSyntaxUID)
    options = pydicom.pixels.as_pixel_options(dataset)
    for frame, _ in _decoder(syntax, plugin).iter_array(
        dataset, validate=True, raw=True, decoding_plugin=plugin, **options
    ):
        yield frame


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
    if source.transfer_syntax not in DECODING_PLUGINS or _PIXEL_DATA not in source:
        return None
    try:
        with redacted_diagnostics():
            dataset = source.dataset()
            plugin = _dataset_plugin(source.transfer_syntax, dataset)
        if plugin is None or not decoder_available(source.transfer_syntax, plugin):
            return TransformReason.NO_DECODER
        with redacted_diagnostics():
            return _decoded_problem(source, dataset, plugin)
    # The plugin is installed, but the process that runs it cannot be.
    except isolated_decoding.DecoderUnavailable:
        return TransformReason.NO_DECODER
    # pydicom and its plugins raise many types for pixel data they cannot
    # decode, and a message can quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        return TransformReason.UNDECODABLE_PIXEL_DATA


def _decoded_problem(
    source: SourceEvidence, dataset: pydicom.Dataset, plugin: str
) -> TransformReason | None:
    """Return why the frames do not match the attributes, if they do not,
    having checked the offset tables and each frame's codestream header and
    decoded each frame with ``plugin``.

    Raises
    ------
    Exception
        Whatever pydicom or the plugin raises for a frame it cannot decode.
    """
    expected = _expected(dataset)
    if expected is None:
        return TransformReason.FRAME_MISMATCH
    frames, shape = expected
    if not _offsets_match(source, frames):
        return TransformReason.OFFSET_TABLE_MISMATCH
    headers = _headers_problem(source, dataset, frames)
    if headers is not None:
        return headers
    if plugin in ISOLATED_PLUGINS:
        # The child sends back only data, so anything but True is a mismatch.
        matched = isolated_decoding.run(
            _file_decoded, source.data, plugin, frames, shape
        )
        return None if matched is True else TransformReason.FRAME_MISMATCH
    return _decoded(dataset, plugin, frames, shape)


def _file_decoded(
    data: bytes, plugin: str, frames: int, shape: tuple[int, ...]
) -> bool:
    """Return whether :func:`_decoded` of the data set that ``data`` holds,
    read as :meth:`.source.SourceEvidence.dataset` reads it, finds no
    problem."""
    return _decoded(_dataset(data), plugin, frames, shape) is None


def _decoded(
    dataset: pydicom.Dataset, plugin: str, frames: int, shape: tuple[int, ...]
) -> TransformReason | None:
    """Return :attr:`~.reasons.TransformReason.FRAME_MISMATCH` unless
    ``plugin`` decodes ``frames`` frames, each of ``shape``."""
    decoded = 0
    for frame in _iter_frames(dataset, plugin):
        if decoded == frames or frame.shape != shape:
            return TransformReason.FRAME_MISMATCH
        decoded += 1
    return None if decoded == frames else TransformReason.FRAME_MISMATCH


def _dataset(data: bytes) -> pydicom.Dataset:
    """Return the data set that ``data`` holds, as
    :meth:`.source.SourceEvidence.dataset` reads it, but in the child, whose
    warnings and log records the caller redacts as it issues them again."""
    return pydicom.dcmread(io.BytesIO(data), defer_size=None)


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
    for codestream in _codestreams(source, frames):
        problem = header_problem(source.transfer_syntax, codestream, declared)
        if problem is not None:
            return problem
    return None


def _codestreams(source: SourceEvidence, frames: int) -> Iterator[bytes]:
    """Yield each frame's codestream, found as pydicom finds it to decode
    it, by :func:`pydicom.encaps.generate_frames`, from the offset tables
    that :func:`_offsets_match` shows sound."""
    extended = None
    if _EXTENDED_OFFSET_TABLE in source:
        extended = (
            source.value_field(_EXTENDED_OFFSET_TABLE),
            source.value_field(_EXTENDED_OFFSET_TABLE_LENGTHS),
        )
    yield from pydicom.encaps.generate_frames(
        _value(source), number_of_frames=frames, extended_offsets=extended
    )


def _offsets_match(source: SourceEvidence, frames: int) -> bool:
    """Return whether the offset tables give where frames start, as above.

    Pixel Data that is not encapsulated, such as Pixel Data of VR OW in a
    syntax that encapsulates it, has no offset tables to check; the writer
    refuses to write it (:mod:`.preserving_writer`).
    """
    if not encapsulated_pixel_data(source, _PIXEL_DATA):
        return True
    table, fragments = fragment_positions(source)
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


def fragment_positions(source: SourceEvidence) -> tuple[bytes, list[tuple[int, int]]]:
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


def same_pixels(source: SourceEvidence, output: SourceEvidence) -> bool:
    """Return whether every frame of ``output`` decodes to the same pixels as
    the frame of ``source`` at the same index, as stored, by the plugin
    pinned to their transfer syntax.

    Frames are decoded one pair at a time. A frame that does not decode,
    another number of frames, or another transfer syntax gives ``False``.
    """
    if (
        source.transfer_syntax not in DECODING_PLUGINS
        or output.transfer_syntax != source.transfer_syntax
    ):
        return False
    try:
        with redacted_diagnostics():
            plugin = _dataset_plugin(source.transfer_syntax, source.dataset())
            if plugin is None:
                return False
            if plugin in ISOLATED_PLUGINS:
                # The child sends back only data.
                return (
                    isolated_decoding.run(_same_files, source.data, output.data, plugin)
                    is True
                )
            return _same(source.dataset(), output.dataset(), plugin)
    # pydicom and its plugins raise many types for pixel data they cannot
    # decode, and a message can quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        return False


def _same_files(before: bytes, after: bytes, plugin: str) -> bool:
    """Return :func:`_same` of the data sets that ``before`` and ``after`` hold."""
    return _same(_dataset(before), _dataset(after), plugin)


def _same(before: pydicom.Dataset, after: pydicom.Dataset, plugin: str) -> bool:
    """Return whether ``plugin`` decodes ``before`` and ``after`` to the same
    frames, as :func:`same_pixels` describes."""
    sentinel = object()
    pairs = itertools.zip_longest(
        _iter_frames(before, plugin), _iter_frames(after, plugin), fillvalue=sentinel
    )
    for first, second in pairs:
        if first is sentinel or second is sentinel:
            return False
        if first.dtype != second.dtype or not np.array_equal(first, second):
            return False
    return True


class FramesRefused(Exception):
    """Compressed frames that :func:`decoded_frames` cannot give, with a
    value-free reason."""

    def __init__(self, reason: TransformReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def decoded_frames(
    source: SourceEvidence,
    attributes: Mapping[str, int | str],
    frames: int,
    photometric: str,
) -> bytes:
    """Return every frame of compressed Pixel Data decoded, for Clean Pixel Data.

    Each frame is decoded by the plugin pinned to the transfer syntax, as
    :func:`frames_problem` decodes it, but with YBR_FULL and YBR_FULL_422
    converted to RGB by pydicom, and JPEG 2000's YBR_ICT and YBR_RCT by the
    decoder, so that the samples are those that native Pixel Data of the
    photometric interpretation ``photometric`` would hold. Frames that
    :data:`ISOLATED_PLUGINS` decode are decoded in the child process, one
    at a time, and what it sends back is checked, as the module describes.

    Parameters
    ----------
    source : SourceEvidence
        A source whose frames :func:`frames_problem` has shown sound.
    attributes : mapping of str to int or str
        The source's Rows, Columns, Samples per Pixel, Bits Allocated, Bits
        Stored, High Bit, Pixel Representation, Photometric Interpretation,
        and, for colour, Planar Configuration, by keyword, as read from it,
        which describe one frame to its decoder.
    frames : int
        How many frames the Pixel Data hold.
    photometric : str
        The photometric interpretation of the decoded samples: the source's
        for monochrome, and ``"RGB"`` for colour.

    Returns
    -------
    bytes
        The samples of every frame, in order, as native Pixel Data holds
        them in little endian: each sample in a word of Bits Allocated, in
        two's complement where signed, with the samples of each pixel
        together, as Planar Configuration 0 gives them, and no padding.

    Raises
    ------
    FramesRefused
        With :attr:`~.reasons.TransformReason.NO_DECODER` where the plugin
        is not installed or the child cannot be started,
        :attr:`~.reasons.TransformReason.UNDECODABLE_PIXEL_DATA` where a
        frame does not decode,
        :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` where a
        frame decodes to another photometric interpretation, and
        :attr:`~.reasons.TransformReason.FRAME_MISMATCH` where a frame's
        samples are not of the expected type, shape, or size, or the frames
        are not ``frames`` in number.
    """
    plugin = pinned_plugin(
        source.transfer_syntax,
        attributes["BitsStored"],
        attributes["PixelRepresentation"],
    )
    if plugin is None or not decoder_available(source.transfer_syntax, plugin):
        raise FramesRefused(TransformReason.NO_DECODER)
    expected = _expected_frame(attributes, photometric)
    described = tuple(sorted(attributes.items()))
    decoded: list[bytes] = []
    try:
        with redacted_diagnostics():
            for codestream in _codestreams(source, frames):
                decoded.append(
                    _decoded_frame(
                        source.transfer_syntax, plugin, codestream, described, expected
                    )
                )
    except FramesRefused:
        raise
    # The plugin is installed, but the process that runs it cannot be.
    except isolated_decoding.DecoderUnavailable:
        raise FramesRefused(TransformReason.NO_DECODER) from None
    # pydicom and its plugins raise many types for pixel data they cannot
    # decode, and a message can quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise FramesRefused(TransformReason.UNDECODABLE_PIXEL_DATA) from None
    if len(decoded) != frames:
        raise FramesRefused(TransformReason.FRAME_MISMATCH)
    return b"".join(decoded)


def isolated_frames(
    data: bytes, indices: Sequence[int] | None = None
) -> Iterator["np.ndarray"]:
    """Yield frames of the compressed Pixel Data of the file ``data``, each
    decoded in the decoding child, for a QC preview.

    For the plugins of :data:`CHILD_ONLY_PLUGINS`, which never decode in
    the engine's process. Each frame is decoded as :func:`decoded_frames`
    decodes it, from its own codestream, and what the child sends back is
    checked in the same way, so that the frames are those that
    :func:`pydicom.pixels.iter_pixels` would give in process: monochrome as
    stored, and YBR_FULL and YBR_FULL_422 converted to RGB.

    Parameters
    ----------
    data : bytes
        The file.
    indices : sequence of int, optional
        The frames to decode, in the order to yield them; every frame, in
        order, by default.

    Raises
    ------
    FramesRefused
        As :func:`decoded_frames` raises it.
    """
    try:
        with redacted_diagnostics():
            dataset = pydicom.dcmread(io.BytesIO(data))
            syntax = str(dataset.file_meta.TransferSyntaxUID)
            attributes = _described_frame(dataset)
            frames = int(dataset.get("NumberOfFrames") or 1)
            extended = None
            if "ExtendedOffsetTable" in dataset:
                extended = (
                    dataset.ExtendedOffsetTable,
                    dataset.ExtendedOffsetTableLengths,
                )
            pixel_data = dataset.PixelData
    # pydicom raises many types for a file it cannot read, and a message can
    # quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise FramesRefused(TransformReason.UNDECODABLE_PIXEL_DATA) from None
    plugin = pinned_plugin(
        syntax, attributes["BitsStored"], attributes["PixelRepresentation"]
    )
    if plugin is None or not decoder_available(syntax, plugin):
        raise FramesRefused(TransformReason.NO_DECODER)
    samples = int(attributes["SamplesPerPixel"])
    photometric = str(attributes["PhotometricInterpretation"])
    if samples == 3 and photometric in _CONVERTED_TO_RGB:
        photometric = "RGB"
    expected = _expected_frame(attributes, photometric)
    described = tuple(sorted(attributes.items()))
    for index in range(frames) if indices is None else indices:
        try:
            with redacted_diagnostics():
                codestream = pydicom.encaps.get_frame(
                    pixel_data,
                    index,
                    number_of_frames=frames,
                    extended_offsets=extended,
                )
                frame = _decoded_frame(syntax, plugin, codestream, described, expected)
        except FramesRefused:
            raise
        except isolated_decoding.DecoderUnavailable:
            raise FramesRefused(TransformReason.NO_DECODER) from None
        # As in decoded_frames.
        except Exception:  # pylint: disable = broad-exception-caught
            raise FramesRefused(TransformReason.UNDECODABLE_PIXEL_DATA) from None
        yield np.frombuffer(frame, dtype=expected.kind).reshape(expected.shape)


# The photometric interpretations that pydicom converts to RGB as it decodes,
# where asked.
_CONVERTED_TO_RGB = frozenset({"RGB", "YBR_FULL", "YBR_FULL_422"})
_DESCRIBING = (
    "Rows",
    "Columns",
    "SamplesPerPixel",
    "BitsAllocated",
    "BitsStored",
    "HighBit",
    "PixelRepresentation",
)


def _described_frame(dataset: pydicom.Dataset) -> dict[str, int | str]:
    """Return the attributes that describe one frame of ``dataset`` to its
    decoder, as :func:`decoded_frames` takes them.

    Raises
    ------
    Exception
        Whatever pydicom raises for an attribute that is absent or cannot be
        read as an integer or text.
    """
    attributes: dict[str, int | str] = {
        keyword: int(dataset[keyword].value) for keyword in _DESCRIBING
    }
    attributes["PhotometricInterpretation"] = str(dataset.PhotometricInterpretation)
    if int(attributes["SamplesPerPixel"]) > 1:
        attributes["PlanarConfiguration"] = int(dataset.PlanarConfiguration)
    return attributes


def _expected_frame(attributes: Mapping[str, int | str], photometric: str) -> _Expected:
    """Return what a frame that ``attributes`` describe must decode to, with
    the photometric interpretation ``photometric``.

    Raises
    ------
    FramesRefused
        With :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` where
        Bits Allocated and Pixel Representation give no NumPy type.
    """
    rows, columns, samples = (
        int(attributes[keyword]) for keyword in ("Rows", "Columns", "SamplesPerPixel")
    )
    kind = _SAMPLE_TYPES.get(
        (int(attributes["BitsAllocated"]), int(attributes["PixelRepresentation"]) == 1)
    )
    if kind is None:
        raise FramesRefused(TransformReason.UNCLEANABLE_PIXEL_DATA)
    return _Expected(
        photometric,
        kind,
        (rows, columns) if samples == 1 else (rows, columns, samples),
        rows * columns * samples * int(kind[2:]),
    )


def _decoded_frame(
    transfer_syntax: str,
    plugin: str,
    codestream: bytes,
    described: tuple[tuple[str, int | str], ...],
    expected: _Expected,
) -> bytes:
    """Return one frame decoded by ``plugin``, in the decoding child for
    :data:`ISOLATED_PLUGINS`, once what was sent back is checked.

    Raises
    ------
    FramesRefused
        With the reason that :meth:`_Expected.checked` gives.
    Exception
        Whatever the child or the decoder raises.
    """
    arguments = (transfer_syntax, plugin, codestream, described)
    if plugin in ISOLATED_PLUGINS:
        sent = isolated_decoding.run(
            _frame_decoded,
            *arguments,
            # The samples' size once encoded as base64.
            result_bytes=4 * -(-expected.size // 3),
        )
    else:
        sent = _frame_decoded(*arguments)
    frame = expected.checked(sent)
    if isinstance(frame, TransformReason):
        raise FramesRefused(frame)
    return frame


@dataclasses.dataclass(frozen=True)
class _Expected:
    """What a decoded frame must be: its photometric interpretation, its
    samples' NumPy type, its shape, and its size in bytes."""

    photometric: str
    kind: str
    shape: tuple[int, ...]
    size: int

    def checked(self, sent: object) -> bytes | TransformReason:
        """Return the samples of a frame that :func:`_frame_decoded` sent,
        or why they are refused.

        ``sent`` may come from a child that a codestream subverted, so it is
        only compared with what is expected and decoded from base64, never
        used to find a type, a name, or an attribute.
        """
        if not (isinstance(sent, list) and len(sent) == 4):
            return TransformReason.FRAME_MISMATCH
        photometric, kind, shape, text = sent
        if not isinstance(photometric, str) or photometric != self.photometric:
            return TransformReason.UNCLEANABLE_PIXEL_DATA
        if (
            not isinstance(kind, str)
            or kind != self.kind
            or not isinstance(shape, list)
            or tuple(shape) != self.shape
            or not isinstance(text, str)
        ):
            return TransformReason.FRAME_MISMATCH
        try:
            samples = base64.b64decode(text.encode("ascii"), validate=True)
        except (UnicodeError, binascii.Error):
            return TransformReason.FRAME_MISMATCH
        if len(samples) != self.size:
            return TransformReason.FRAME_MISMATCH
        return samples


def _frame_decoded(
    transfer_syntax: str,
    plugin: str,
    codestream: bytes,
    attributes: tuple[tuple[str, int | str], ...],
) -> list:
    """Return one frame decoded by ``plugin``, as JSON can send it back: its
    photometric interpretation as decoded, its samples' NumPy type and
    shape, and its samples as base64 text, in C order.

    The frame's codestream is decoded as the only frame of a data set that
    holds ``attributes`` and the codestream, encapsulated.
    """
    dataset = pydicom.Dataset()
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = transfer_syntax
    for keyword, value in attributes:
        setattr(dataset, keyword, value)
    dataset.PixelData = pydicom.encaps.encapsulate([codestream])
    dataset["PixelData"].VR = "OB"
    frame, properties = next(
        _decoder(transfer_syntax, plugin).iter_array(
            dataset, decoding_plugin=plugin, as_rgb=True
        )
    )
    photometric = properties["photometric_interpretation"]
    return [
        str(getattr(photometric, "value", photometric)),
        frame.dtype.str,
        list(frame.shape),
        base64.b64encode(np.ascontiguousarray(frame).tobytes()).decode("ascii"),
    ]
