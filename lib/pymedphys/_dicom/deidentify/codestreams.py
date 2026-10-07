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

The design removes "metadata in compressed pixel data bitstreams, such as
JPEG APPn segments, ... without recompression" (Architecture item 7), and
MIDI-BP-14 asks, where the bitstream is kept, that it be scanned and the
elements at risk removed. :func:`without_metadata` parses each frame's
codestream of encapsulated Pixel Data (7FE0,0010), accounts for every byte
of it, and cuts out each segment that can carry text or an embedded file:

- JPEG (ITU-T T.81) and JPEG-LS (ITU-T T.87): every comment (COM) and
  application (APP0 to APP15) marker segment, except three of fixed format
  that say how to decode colour and hold nothing else, which are kept once
  parsed: a JFIF APP0 without a thumbnail, an Adobe APP14, and, in JPEG-LS,
  an APP8 colour transform (``mrfx``).
- JPEG 2000 and HTJ2K (ITU-T T.800 and T.814): every comment (COM) marker
  segment of the main header. One in a tile-part header could only be cut
  by rewriting the tile-part's length, so the instance is sequestered
  instead.
- RLE Lossless (PS3.5 Annex G) has no metadata segments; its header and
  every segment are still parsed, and each segment must decode to exactly
  one byte plane.

Every other marker and segment is kept as it is: frame and scan headers,
tables, restart intervals, and entropy-coded data. A marker that the
transfer syntax does not define, a JPEG 2000 codestream inside a JP2 file,
any byte after the end of a frame's codestream other than one padding byte
of 0x00, and a frame that cannot be found are refused, since bytes that no
decoder reads could carry anything. Each refusal names a reason, never a
value or an offset.

Frames are found from the Basic Offset Table where it is not empty, as one
fragment each where there are as many fragments as frames, from all the
fragments together for a single frame, and otherwise by parsing the
fragments one codestream after another, each of which must end where a
fragment ends. Where something is cut, the Pixel Data is written anew, one
fragment for each frame, with a Basic Offset Table where the source had
one; where an Extended Offset Table (7FE0,0001) is present, the instance is
sequestered instead, since its values would have to change too. Where
nothing is cut, the Pixel Data is kept byte for byte. The caller shows that
every frame decodes to the same pixels before and after
(:mod:`.instance_transform`).
"""

from __future__ import annotations

import dataclasses
import enum
import struct
from collections.abc import Iterator, Sequence

from pymedphys._imports import pydicom

from .file_layout import ElementPath
from .pixel_decoding import fragment_positions
from .reasons import TransformReason
from .source import SourceEvidence, encapsulated_pixel_data

_PIXEL_DATA = ElementPath((), "(7FE0,0010)")
_EXTENDED_OFFSET_TABLE = ElementPath((), "(7FE0,0001)")
_ITEM = b"\xfe\xff\x00\xe0"
_RLE_LOSSLESS = "1.2.840.10008.1.2.5"
_JPEG_LS = frozenset({"1.2.840.10008.1.2.4.80", "1.2.840.10008.1.2.4.81"})
_JPEG = frozenset(
    {
        "1.2.840.10008.1.2.4.50",
        "1.2.840.10008.1.2.4.51",
        "1.2.840.10008.1.2.4.57",
        "1.2.840.10008.1.2.4.70",
    }
)
_JPEG_2000 = frozenset(
    {
        "1.2.840.10008.1.2.4.90",
        "1.2.840.10008.1.2.4.91",
        "1.2.840.10008.1.2.4.201",
        "1.2.840.10008.1.2.4.202",
        "1.2.840.10008.1.2.4.203",
    }
)

# T.81 Table B.1: frame headers (SOF0 to SOF15 but DHT, JPG, and DAC),
# tables (DHT, DAC, DQT), scan header (SOS), DNL, DRI, DHP, and EXP. T.87
# adds SOF55 and LSE.
_JPEG_KEPT = frozenset(
    {*range(0xC0, 0xD0), 0xDA, 0xDB, 0xDC, 0xDD, 0xDE, 0xDF} - {0xC8}
)
_JPEG_LS_KEPT = _JPEG_KEPT | {0xF7, 0xF8}
_COM = 0xFE
_APP = range(0xE0, 0xF0)
_SOS, _EOI, _SOI = 0xDA, 0xD9, 0xD8
_RESTART = range(0xD0, 0xD8)

# T.800 Table A.2, with T.814's CAP and CPF.
_SOC, _SOT, _SOD, _EOC = 0xFF4F, 0xFF90, 0xFF93, 0xFFD9
_SOP, _EPH = 0xFF91, 0xFF92
# Bit stuffing keeps every two bytes of a tile-part's data below 0xFF90,
# but for SOP and EPH (T.800 Section B.10.1 and Annexes C and D, and T.814).
_IN_DATA = 0xFF90
_J2K_COM = 0xFF64
_SIZ = 0xFF51
_J2K_MAIN = frozenset(
    {
        0xFF50,  # CAP
        _SIZ,
        0xFF52,  # COD
        0xFF53,  # COC
        0xFF55,  # TLM
        0xFF57,  # PLM
        0xFF59,  # CPF
        0xFF5C,  # QCD
        0xFF5D,  # QCC
        0xFF5E,  # RGN
        0xFF5F,  # POC
        0xFF60,  # PPM
        0xFF63,  # CRG
    }
)
_J2K_TILE_PART = frozenset(
    {
        0xFF52,  # COD
        0xFF53,  # COC
        0xFF58,  # PLT
        0xFF5C,  # QCD
        0xFF5D,  # QCC
        0xFF5E,  # RGN
        0xFF5F,  # POC
        0xFF61,  # PPT
    }
)
_JP2_SIGNATURE = b"\x00\x00\x00\x0cjP  \r\n\x87\n"


class CodestreamRefused(Exception):
    """Raised for compressed pixel data that cannot be shown free of metadata.

    The message names the reason alone, never a value or an offset.
    """

    def __init__(self, reason: TransformReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class _Unparsable(Exception):
    """A codestream does not parse; reported as a reason, never a position."""


class _Kind(enum.Enum):
    KEEP = "keep"
    CUT = "cut"


def without_metadata(source: SourceEvidence) -> bytes | None:
    """Return the instance's Pixel Data with its metadata segments cut out.

    Parameters
    ----------
    source : SourceEvidence

    Returns
    -------
    bytes or None
        The new value of encapsulated Pixel Data, as pydicom holds it: the
        Basic Offset Table item and one fragment item for each frame,
        without the Sequence Delimitation Item. ``None`` where the transfer
        syntax does not encapsulate Pixel Data, where the data set has none,
        or where nothing is cut, so that it is kept byte for byte.

    Raises
    ------
    CodestreamRefused
        With :attr:`~.reasons.TransformReason.UNPARSABLE_CODESTREAM` where a
        frame cannot be found or parsed, or holds bytes outside its
        codestream; with
        :attr:`~.reasons.TransformReason.UNCUTTABLE_METADATA` where a
        metadata segment could be cut only by changing other values.
    """
    syntax = source.transfer_syntax
    if syntax not in _JPEG | _JPEG_LS | _JPEG_2000 | {_RLE_LOSSLESS}:
        return None
    if _PIXEL_DATA not in source:
        return None
    if not encapsulated_pixel_data(source, _PIXEL_DATA):
        # The writer refuses it (.preserving_writer).
        return None
    try:
        dataset = source.dataset()
        frames = int(dataset.get("NumberOfFrames") or 1)
        table, codestreams = _frames(source, syntax, frames)
        if syntax == _RLE_LOSSLESS:
            planes = _planes(dataset)
            for codestream in codestreams:
                _rle(codestream, *planes)
            return None
        cut = [_cut(syntax, codestream) for codestream in codestreams]
    except _Unparsable:
        raise CodestreamRefused(TransformReason.UNPARSABLE_CODESTREAM) from None
    if all(new is None for new in cut):
        return None
    if _EXTENDED_OFFSET_TABLE in source:
        raise CodestreamRefused(TransformReason.UNCUTTABLE_METADATA)
    written = [old if new is None else new for old, new in zip(codestreams, cut)]
    return encapsulated(written, with_offsets=bool(table))


def encapsulated(codestreams: Sequence[bytes], *, with_offsets: bool) -> bytes:
    """Return encapsulated Pixel Data as pydicom holds it, one fragment for
    each codestream, padded to an even length with 0x00, after a Basic
    Offset Table that gives each one's offset, or an empty one."""
    fragments = [c + b"\x00" * (len(c) % 2) for c in codestreams]
    offsets, position = [], 0
    for fragment in fragments:
        offsets.append(position)
        position += 8 + len(fragment)
    table = struct.pack(f"<{len(offsets)}I", *offsets) if with_offsets else b""
    return b"".join(
        _ITEM + struct.pack("<I", len(item)) + item for item in (table, *fragments)
    )


def _frames(
    source: SourceEvidence, syntax: str, frames: int
) -> tuple[bytes, list[bytes]]:
    """Return the Basic Offset Table, and each frame's bytes, with any padding."""
    table, positions = fragment_positions(source)
    extent = source.element(_PIXEL_DATA)
    value = source.encoded(_PIXEL_DATA)[extent.value_start - extent.start :]
    base = 8 + len(table)
    fragments = [
        value[base + start + 8 : base + start + 8 + length]
        for start, length in positions
    ]
    if not fragments or frames < 1:
        raise _Unparsable
    if table:
        # Checked against the fragments already (.pixel_decoding).
        offsets = list(struct.unpack(f"<{len(table) // 4}I", table))
        starts = [start for start, _ in positions]
        bounds = [starts.index(offset) for offset in offsets] + [len(fragments)]
        return table, [b"".join(fragments[a:b]) for a, b in zip(bounds, bounds[1:])]
    if len(fragments) == frames:
        return table, fragments
    if frames == 1:
        return table, [b"".join(fragments)]
    if syntax == _RLE_LOSSLESS:
        # Each frame of RLE Lossless is one fragment (PS3.5 Section A.4.2).
        raise _Unparsable
    return table, list(_sequential(syntax, fragments, frames))


def _sequential(syntax: str, fragments: list[bytes], frames: int) -> Iterator[bytes]:
    """Yield each frame's bytes, parsing codestreams one after another, each
    of which must end, with at most one padding byte, where a fragment ends."""
    data = b"".join(fragments)
    ends, position = set(), 0
    for fragment in fragments:
        position += len(fragment)
        ends.add(position)
    start = 0
    for _ in range(frames):
        end = start + _parse(syntax, data[start:]).end
        if end not in ends:
            end += 1
            if end not in ends or data[end - 1] != 0:
                raise _Unparsable
        yield data[start:end]
        start = end
    if start != len(data):
        raise _Unparsable


def entropy_coded(transfer_syntax: str, data: bytes) -> list[tuple[int, int]] | None:
    """Return where the entropy-coded data of encapsulated pixel data are.

    ``data`` is the values of the fragments of encapsulated Pixel Data after
    its Basic Offset Table, joined. Its codestreams are parsed one after
    another, with at most one padding byte of 0x00 after each, which is
    how every frame is found whatever the fragments are. Every byte of RLE
    Lossless is sample data or offsets, so all of it is given.

    Returns
    -------
    list of (int, int) or None
        The ranges of entropy-coded data, as offsets into ``data``; ``None``
        where the transfer syntax does not encapsulate Pixel Data, or the
        codestreams do not parse to the end of ``data``.
    """
    if transfer_syntax == _RLE_LOSSLESS:
        return [(0, len(data))]
    if transfer_syntax not in _JPEG | _JPEG_LS | _JPEG_2000:
        return None
    ranges: list[tuple[int, int]] = []
    start = 0
    try:
        while start < len(data):
            parsed = _parse(transfer_syntax, data[start:])
            ranges += [(start + a, start + b) for a, b in parsed.entropy]
            start += parsed.end
            if data[start : start + 1] == b"\x00":
                start += 1
    except (_Unparsable, CodestreamRefused):
        return None
    return ranges


def cut_codestream(transfer_syntax: str, frame: bytes) -> bytes | None:
    """Return one frame's JPEG, JPEG-LS, JPEG 2000, or HTJ2K codestream with
    its metadata segments cut, or ``None`` where there is none to cut.

    ``frame`` is the frame's bytes from its fragments, with any padding.

    Raises
    ------
    CodestreamRefused
        As :func:`without_metadata` raises it.
    """
    if transfer_syntax not in _JPEG | _JPEG_LS | _JPEG_2000:
        raise ValueError("not a transfer syntax whose codestreams are cut here")
    try:
        return _cut(transfer_syntax, frame)
    except _Unparsable:
        raise CodestreamRefused(TransformReason.UNPARSABLE_CODESTREAM) from None


def _cut(syntax: str, frame: bytes) -> bytes | None:
    parsed = _parse(syntax, frame)
    cuts, end = parsed.cuts, parsed.end
    padding = frame[end:]
    if len(padding) > 1 or padding.strip(b"\x00"):
        raise _Unparsable
    if not cuts:
        return None
    kept, position = [], 0
    for start, stop in cuts:
        kept.append(frame[position:start])
        position = stop
    kept.append(frame[position:end])
    return b"".join(kept)


@dataclasses.dataclass(frozen=True)
class _Parsed:
    """A codestream parsed from the start of some bytes.

    Attributes
    ----------
    cuts, entropy : list of (int, int)
        The ranges of its metadata segments, to cut, and of its
        entropy-coded data, from the start of the bytes.
    end : int
        Where it ends.
    """

    cuts: list[tuple[int, int]]
    end: int
    entropy: list[tuple[int, int]]


def _parse(syntax: str, data: bytes) -> _Parsed:
    """Parse the codestream at the start of ``data``."""
    if syntax in _JPEG_2000:
        return _jpeg_2000(data)
    return _jpeg(data, syntax in _JPEG_LS)


def _jpeg(data: bytes, ls: bool) -> _Parsed:
    """Parse a T.81 or T.87 codestream, from SOI to EOI."""
    if data[:2] != b"\xff" + bytes([_SOI]):
        raise _Unparsable
    cuts: list[tuple[int, int]] = []
    entropy: list[tuple[int, int]] = []
    position = 2
    while True:
        start = position
        if position >= len(data) or data[position] != 0xFF:
            raise _Unparsable
        # Fill bytes of 0xFF may precede a marker (T.81 Section B.1.1.2).
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            raise _Unparsable
        marker = data[position]
        position += 1
        if marker == _EOI:
            return _Parsed(cuts, position, entropy)
        if position + 2 > len(data):
            raise _Unparsable
        (length,) = struct.unpack_from(">H", data, position)
        end = position + length
        if length < 2 or end > len(data):
            raise _Unparsable
        if _jpeg_kind(marker, data[position + 2 : end], ls) is _Kind.CUT:
            cuts.append((start, end))
        position = end
        if marker == _SOS:
            scan = position
            position = _scan_end(data, position, ls)
            entropy.append((scan, position))


def _jpeg_kind(marker: int, payload: bytes, ls: bool) -> _Kind:
    """Say whether a marker segment is kept or cut; raise for an unknown one."""
    if marker in (_JPEG_LS_KEPT if ls else _JPEG_KEPT):
        return _Kind.KEEP
    if marker == 0xE0 and len(payload) == 14 and payload[:5] == b"JFIF\x00":
        # Version, units, densities, and a thumbnail of 0 by 0.
        return _Kind.CUT if payload[12:14] != b"\x00\x00" else _Kind.KEEP
    if marker == 0xEE and len(payload) == 12 and payload[:5] == b"Adobe":
        # Version, two flags, and the colour transform.
        return _Kind.KEEP
    if ls and marker == 0xE8 and len(payload) == 5 and payload[:4] == b"mrfx":
        # The colour transform of the HP extension to JPEG-LS.
        return _Kind.KEEP
    if marker == _COM or marker in _APP:
        return _Kind.CUT
    raise _Unparsable


def _scan_end(data: bytes, position: int, ls: bool) -> int:
    """Return where a scan's entropy-coded data end: at the next marker
    other than a restart marker."""
    while True:
        found = data.find(b"\xff", position)
        if found < 0:
            raise _Unparsable
        following = found + 1
        while following < len(data) and data[following] == 0xFF:
            following += 1
        if following >= len(data):
            raise _Unparsable
        byte = data[following]
        # In T.81, 0xFF 0x00 is a stuffed byte; in T.87, a byte after 0xFF
        # below 0x80 is data, its first bit stuffed (T.87 Section 9.1).
        stuffed = byte < 0x80 if ls else byte == 0x00
        if following == found + 1 and (stuffed or byte in _RESTART):
            position = following + 1
            continue
        if byte in _RESTART:
            position = following + 1
            continue
        return found


def _jpeg_2000(data: bytes) -> _Parsed:
    """Parse a T.800 or T.814 codestream, from SOC to EOC."""
    if data.startswith(_JP2_SIGNATURE) or _marker(data, 0) != _SOC:
        raise _Unparsable
    cuts: list[tuple[int, int]] = []
    entropy: list[tuple[int, int]] = []
    position = 2
    first = True
    while True:
        marker = _marker(data, position)
        if marker == _SOT and not first:
            break
        end = _segment_end(data, position)
        if first and marker != _SIZ:
            raise _Unparsable
        if marker == _J2K_COM:
            cuts.append((position, end))
        elif marker not in _J2K_MAIN:
            raise _Unparsable
        first = False
        position = end
    while True:
        marker = _marker(data, position)
        if marker == _EOC:
            return _Parsed(cuts, position + 2, entropy)
        if marker != _SOT:
            raise _Unparsable
        end = _segment_end(data, position)
        if end - position != 12:
            raise _Unparsable
        (tile_part_length,) = struct.unpack_from(">I", data, position + 6)
        tile_part_end = position + tile_part_length
        position = end
        while True:
            marker = _marker(data, position)
            if marker == _SOD:
                break
            if marker == _J2K_COM:
                raise CodestreamRefused(TransformReason.UNCUTTABLE_METADATA)
            if marker not in _J2K_TILE_PART:
                raise _Unparsable
            position = _segment_end(data, position)
        if tile_part_length == 0:
            # The last tile-part, running to this codestream's EOC marker
            # (T.800 Section A.4.2), which another frame may follow.
            tile_part_end = _eoc(data, position + 2)
        if not position + 2 <= tile_part_end <= len(data):
            raise _Unparsable
        entropy.append((position + 2, tile_part_end))
        position = tile_part_end


def _eoc(data: bytes, position: int) -> int:
    """Return where the EOC marker after the tile-part data at ``position``
    is, stepping over SOP marker segments and EPH markers (T.800 Sections
    A.8.1 and A.8.2), whose parameters may hold any bytes."""
    while True:
        position = data.find(b"\xff", position)
        if position < 0:
            raise _Unparsable
        marker = _marker(data, position)
        if marker < _IN_DATA:
            position += 1
        elif marker == _SOP:
            position = _segment_end(data, position)
        elif marker == _EPH:
            position += 2
        elif marker == _EOC:
            return position
        else:
            raise _Unparsable


def _marker(data: bytes, position: int) -> int:
    if position + 2 > len(data):
        raise _Unparsable
    return struct.unpack_from(">H", data, position)[0]


def _segment_end(data: bytes, position: int) -> int:
    """Return where the marker segment at ``position`` ends."""
    if position + 4 > len(data):
        raise _Unparsable
    (length,) = struct.unpack_from(">H", data, position + 2)
    end = position + 2 + length
    if length < 2 or end > len(data):
        raise _Unparsable
    return end


def _planes(dataset: pydicom.Dataset) -> tuple[int, int]:
    """Return how many segments an RLE Lossless frame has, one for each byte
    of each sample, and how many bytes each decodes to (PS3.5 Annex G)."""
    try:
        samples = int(dataset.SamplesPerPixel)
        allocated = int(dataset.BitsAllocated)
        pixels = int(dataset.Rows) * int(dataset.Columns)
    except Exception:  # pylint: disable = broad-exception-caught
        # pydicom raises many types for a value it cannot read.
        raise _Unparsable from None
    if allocated % 8 or min(samples, allocated, pixels) < 1:
        raise _Unparsable
    return samples * allocated // 8, pixels


def _rle(frame: bytes, segments: int, plane: int) -> None:
    """Parse an RLE Lossless frame: its header (PS3.5 Section G.5) and every
    segment, which must decode to one byte plane and end there, but for one
    padding byte of 0x00 (Section G.3.1)."""
    if len(frame) < 64:
        raise _Unparsable
    count, *offsets = struct.unpack_from("<16I", frame)
    if count != segments or offsets[0] != 64 or any(offsets[count:]):
        raise _Unparsable
    bounds = [*offsets[:count], len(frame)]
    if any(a >= b for a, b in zip(bounds, bounds[1:])):
        raise _Unparsable
    if any(_packbits_length(frame[a:b]) != plane for a, b in zip(bounds, bounds[1:])):
        raise _Unparsable


def _packbits_length(segment: bytes) -> int:
    """Return how many bytes an RLE segment decodes to, refusing one with any
    byte after its last run other than one padding byte of 0x00."""
    position = produced = 0
    while position < len(segment):
        if position == len(segment) - 1 and segment[position] == 0 and produced:
            # Padding to an even length, or a literal run of one byte with no
            # byte after it, which does not decode.
            return produced
        header = segment[position]
        position += 1
        if header < 0x80:
            produced += header + 1
            position += header + 1
        elif header > 0x80:
            produced += 257 - header
            position += 1
        # A header of 0x80 (-128) is a no-op, followed by nothing.
        if position > len(segment):
            raise _Unparsable
    return produced
