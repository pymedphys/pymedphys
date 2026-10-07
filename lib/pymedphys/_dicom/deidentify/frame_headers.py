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

"""Check what a compressed frame's own codestream says of it against its attributes.

A decoder shapes a frame by Rows (0028,0010) and Columns (0028,0011), and
pydicom corrects some disagreements between a codestream and the attributes
as it decodes, so a decoded frame cannot show them. The attributes must be
consistent with the compressed data stream, and the transfer syntax must
describe its coding process (PS3.5 Sections 8.2.1, 8.2.3, 8.2.4, 8.2.14,
and A.4). :func:`header_problem` therefore reads each frame's codestream
before it is decoded, and requires:

- JPEG (ITU-T T.81): one frame header, before the first scan, of the
  process that the transfer syntax names: SOF0 for JPEG Baseline, SOF0 or
  SOF1 for JPEG Extended, since the baseline process is a restricted case
  of the extended one and lossy like it, and SOF3 for JPEG Lossless and
  JPEG Lossless SV1, with every scan's point transform 0, since a point
  transform drops low-order bits before coding.
- JPEG-LS (ITU-T T.87): one SOF55 frame header, and, for JPEG-LS Lossless,
  every scan lossless: NEAR 0 and point transform 0.
- JPEG 2000 and HTJ2K (ITU-T T.800 and T.814): the SIZ marker segment after
  SOC, with every component of the same precision and signedness and none
  subsampled; for a syntax that is lossless only, every COD and COC marker
  segment, in the main header and in each tile-part header, with the
  reversible 5-3 wavelet; and the multiple component transformation, of
  every COD marker segment, as Photometric Interpretation (0028,0004)
  says: YBR_RCT for the reversible one, YBR_ICT for the irreversible one,
  and neither without one (PS3.5 Section 8.2.4). The reversible wavelet is
  needed for lossless coding but does not show it: a codestream that uses
  it can still be truncated, a lossy process (PS3.5 Section A.4.4), and
  whether every coding pass was kept is recorded only in packet headers,
  which are not read here. So a JPEG 2000 or HTJ2K frame coded lossily
  with the reversible wavelet passes under a lossless syntax, and its bytes
  and transfer syntax are kept as the source has them.

Each must also give the same Rows, Columns, and Samples per Pixel
(0028,0002) as the attributes, a sample precision equal to Bits Stored
(0028,0101), and, for JPEG 2000 and HTJ2K, signed samples where Pixel
Representation (0028,0103) is 1 and unsigned where it is 0. A JPEG frame
header of 0 lines, whose height a later DNL marker segment gives, does not
match. JPEG and JPEG-LS samples are always unsigned, so Pixel
Representation is not compared for them. RLE Lossless (PS3.5 Annex G)
holds none of these, and is not read here.

A JPEG or JPEG-LS codestream must also reach its EOI marker, and each of
its scans must hold entropy-coded data, since GDCM decodes a frame whose
scan is empty, or that lacks only its EOI, without an error, and pylibjpeg
also one cut short within its scan. Damaged entropy-coded data that is
still followed by EOI is not detected here.

A frame without such a header, or whose marker segments do not hold
together, gives :attr:`~.reasons.TransformReason.UNDECODABLE_PIXEL_DATA`;
one whose header does not match gives
:attr:`~.reasons.TransformReason.FRAME_MISMATCH`. Each frame is only read
here; its bytes are kept as they are.
"""

from __future__ import annotations

import dataclasses
import struct

from .reasons import TransformReason

_JPEG_FRAME_MARKERS = {
    "1.2.840.10008.1.2.4.50": frozenset({0xC0}),
    "1.2.840.10008.1.2.4.51": frozenset({0xC0, 0xC1}),
    "1.2.840.10008.1.2.4.57": frozenset({0xC3}),
    "1.2.840.10008.1.2.4.70": frozenset({0xC3}),
    "1.2.840.10008.1.2.4.80": frozenset({0xF7}),
    "1.2.840.10008.1.2.4.81": frozenset({0xF7}),
}
_JPEG_LS = frozenset({"1.2.840.10008.1.2.4.80", "1.2.840.10008.1.2.4.81"})
_JPEG_LOSSLESS = frozenset(
    {"1.2.840.10008.1.2.4.57", "1.2.840.10008.1.2.4.70", "1.2.840.10008.1.2.4.80"}
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
_JPEG_2000_LOSSLESS_ONLY = frozenset(
    {"1.2.840.10008.1.2.4.90", "1.2.840.10008.1.2.4.201", "1.2.840.10008.1.2.4.202"}
)
# Every frame header marker: SOF0 to SOF15 of ITU-T T.81 Table B.1, which
# leave out DHT (C4), JPG (C8), and DAC (CC), and SOF55 of ITU-T T.87.
_FRAME_MARKERS = (frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}) | {0xF7}
_START_OF_SCAN = 0xDA
_END_OF_IMAGE = 0xD9
# Markers without a length: RSTm, and TEM.
_STANDALONE = frozenset({*range(0xD0, 0xD8), 0x01})
_REVERSIBLE = 1
_IRREVERSIBLE = 0


@dataclasses.dataclass(frozen=True)
class Declared:
    """What a frame's attributes declare of it."""

    rows: int
    columns: int
    samples: int
    bits_stored: int
    signed: bool
    photometric_interpretation: str


@dataclasses.dataclass(frozen=True)
class _Header:
    """What a frame's codestream says of it."""

    rows: int
    columns: int
    samples: int
    precisions: frozenset[int]
    # JPEG and JPEG-LS: the frame header marker, each scan's NEAR in
    # JPEG-LS, and each scan's point transform.
    frame_marker: int | None = None
    near: frozenset[int] = frozenset()
    point_transforms: frozenset[int] = frozenset()
    # JPEG 2000 and HTJ2K: each component's signedness, whether any is
    # subsampled, each wavelet transformation, and each multiple component
    # transformation.
    signs: frozenset[bool] = frozenset()
    subsampled: bool = False
    transformations: frozenset[int] = frozenset()
    component_transformations: frozenset[int] = frozenset()


def header_problem(
    transfer_syntax: str, codestream: bytes, declared: Declared
) -> TransformReason | None:
    """Return why a frame's codestream does not match its attributes, if it
    does not, as above.

    Parameters
    ----------
    transfer_syntax : str
        A JPEG, JPEG-LS, JPEG 2000, or HTJ2K transfer syntax UID.
    codestream : bytes
        One frame, as :func:`pydicom.encaps.generate_frames` gives it.
    declared : Declared

    Returns
    -------
    TransformReason or None
    """
    if transfer_syntax in _JPEG_2000:
        header = _jpeg_2000(codestream)
    else:
        header = _jpeg(codestream, transfer_syntax in _JPEG_LS)
    if header is None:
        return TransformReason.UNDECODABLE_PIXEL_DATA
    if _matches(transfer_syntax, header, declared):
        return None
    return TransformReason.FRAME_MISMATCH


def _matches(transfer_syntax: str, header: _Header, declared: Declared) -> bool:
    if (header.rows, header.columns, header.samples, header.precisions) != (
        declared.rows,
        declared.columns,
        declared.samples,
        frozenset({declared.bits_stored}),
    ):
        return False
    if transfer_syntax not in _JPEG_2000:
        return header.frame_marker in _JPEG_FRAME_MARKERS.get(
            transfer_syntax, frozenset()
        ) and (
            transfer_syntax not in _JPEG_LOSSLESS
            or (header.point_transforms == {0} and header.near.issubset({0}))
        )
    lossless = header.transformations == {_REVERSIBLE}
    colour = {
        frozenset({0}): declared.photometric_interpretation
        not in ("YBR_RCT", "YBR_ICT"),
        frozenset({1}): declared.photometric_interpretation
        == ("YBR_RCT" if lossless else "YBR_ICT")
        and len(header.transformations) == 1,
    }.get(header.component_transformations, False)
    return (
        header.signs == {declared.signed}
        and not header.subsampled
        and colour
        and (transfer_syntax not in _JPEG_2000_LOSSLESS_ONLY or lossless)
    )


def _jpeg(codestream: bytes, ls: bool) -> _Header | None:
    """Return the frame header and scans of a JPEG or JPEG-LS codestream, or
    ``None`` where :func:`_jpeg_segments` gives none, or it has no scan, no
    frame header before its first scan, or more than one."""
    segments = _jpeg_segments(codestream, ls)
    if segments is None:
        return None
    frames = [
        (index, marker, payload)
        for index, (marker, payload) in enumerate(segments)
        if marker in _FRAME_MARKERS
    ]
    # Ns, then Ns of Csj and Tdj or Tmj, then Ss or NEAR, Se or ILV, and Ah
    # and Al, whose low four bits are a lossless scan's point transform.
    scans = [
        (index, payload)
        for index, (marker, payload) in enumerate(segments)
        if marker == _START_OF_SCAN
    ]
    if (
        len(frames) != 1
        or len(frames[0][2]) < 6
        or not scans
        or scans[0][0] < frames[0][0]
        or any(not scan or len(scan) < 4 + 2 * scan[0] for _, scan in scans)
    ):
        return None
    _, marker, payload = frames[0]
    precision, rows, columns, samples = struct.unpack_from(">BHHB", payload)
    return _Header(
        rows,
        columns,
        samples,
        frozenset({precision}),
        frame_marker=marker,
        near=frozenset(scan[1 + 2 * scan[0]] for _, scan in scans)
        if ls
        else frozenset(),
        point_transforms=frozenset(scan[3 + 2 * scan[0]] & 0x0F for _, scan in scans),
    )


def _jpeg_segments(codestream: bytes, ls: bool) -> list[tuple[int, bytes]] | None:
    """Return the marker and payload of each marker segment of a JPEG or
    JPEG-LS codestream, from SOI to EOI, or ``None`` where they do not hold
    together, a scan has no entropy-coded data, or there is no EOI."""
    if codestream[:2] != b"\xff\xd8":
        return None
    segments: list[tuple[int, bytes]] = []
    position, end = 2, len(codestream)
    while position + 2 <= end and codestream[position] == 0xFF:
        marker = codestream[position + 1]
        if marker == _END_OF_IMAGE:
            return segments
        if marker == 0xFF or marker in _STANDALONE:
            position += 1 if marker == 0xFF else 2
            continue
        payload = _payload(codestream, position)
        if payload is None:
            return None
        segments.append((marker, payload))
        position += 2 + 2 + len(payload)
        if marker == _START_OF_SCAN:
            scan = position
            position = _scan_end(codestream, position, ls)
            if position == scan:
                return None
    return None


def _scan_end(codestream: bytes, position: int, ls: bool) -> int:
    """Return where the entropy-coded data that starts at ``position`` ends:
    at the first marker other than RSTm. In T.81 data, 0xFF is followed by
    a stuffed 0x00; in T.87 data, by a byte below 0x80."""
    while True:
        position = codestream.find(b"\xff", position)
        if position < 0 or position + 1 >= len(codestream):
            return len(codestream)
        following = codestream[position + 1]
        if (following < 0x80 if ls else following == 0x00) or (
            0xD0 <= following <= 0xD7
        ):
            position += 2
            continue
        return position


def _jpeg_2000(codestream: bytes) -> _Header | None:
    """Return the SIZ marker segment, and each COD and COC marker segment's
    transformations, of a JPEG 2000 or HTJ2K codestream, or ``None`` where
    its main header and tile-part headers do not hold together."""
    if codestream[:4] != b"\xff\x4f\xff\x51":
        return None
    size = _payload(codestream, 2)
    if size is None or len(size) < 36:
        return None
    width, height, left, top = struct.unpack_from(">4I", size, 2)
    (samples,) = struct.unpack_from(">H", size, 34)
    if len(size) != 36 + 3 * samples:
        return None
    components = [size[36 + 3 * i : 39 + 3 * i] for i in range(samples)]
    coding: dict[str, set[int]] = {"wavelet": set(), "components": set()}
    position = _coding(codestream, 6 + len(size), 0x90, samples, coding)
    while position is not None and codestream[position : position + 2] == b"\xff\x90":
        tile_part = _payload(codestream, position)
        if tile_part is None or len(tile_part) != 8:
            return None
        (length,) = struct.unpack_from(">I", tile_part, 2)
        start = position
        position = _coding(codestream, position + 12, 0x93, samples, coding)
        if position is None or length == 0:
            break
        position = start + length
    if position is None or not coding["components"]:
        return None
    return _Header(
        height - top,
        width - left,
        samples,
        # Ssiz: the sign in its high bit, and the precision less one.
        frozenset((ssiz & 0x7F) + 1 for ssiz, _, _ in components),
        signs=frozenset(bool(ssiz & 0x80) for ssiz, _, _ in components),
        subsampled=any((across, down) != (1, 1) for _, across, down in components),
        transformations=frozenset(coding["wavelet"]),
        component_transformations=frozenset(coding["components"]),
    )


def _coding(
    codestream: bytes,
    position: int,
    until: int,
    samples: int,
    coding: dict[str, set[int]],
) -> int | None:
    """Read the marker segments of a main or tile-part header from
    ``position`` until the marker ``until``, SOT or SOD, and collect each
    COD and COC marker segment's transformations into ``coding``.

    Returns where ``until`` is, or ``None`` where the header does not hold
    together.
    """
    # Ccoc is 1 byte for fewer than 257 components, otherwise 2.
    component = 1 if samples < 257 else 2
    while codestream[position : position + 1] == b"\xff":
        marker = codestream[position + 1 : position + 2]
        if marker == bytes([until]):
            return position
        payload = _payload(codestream, position)
        if payload is None:
            return None
        if marker == b"\x52":  # COD: Scod, SGcod, then SPcod.
            if len(payload) < 10:
                return None
            coding["components"].add(payload[4])
            coding["wavelet"].add(payload[9])
        elif marker == b"\x53":  # COC: Ccoc, Scoc, then SPcoc.
            if len(payload) < component + 6:
                return None
            coding["wavelet"].add(payload[component + 5])
        position += 4 + len(payload)
    return None


def _payload(codestream: bytes, position: int) -> bytes | None:
    """Return the payload of the marker segment at ``position``, after its
    marker and 16-bit length, or ``None`` where it runs past the end or its
    length is less than 2."""
    if position + 4 > len(codestream):
        return None
    (length,) = struct.unpack_from(">H", codestream, position + 2)
    if length < 2 or position + 2 + length > len(codestream):
        return None
    return codestream[position + 4 : position + 2 + length]
