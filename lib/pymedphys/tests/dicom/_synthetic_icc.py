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

"""Synthetic ICC profiles, written from the ICC specifications for the tests.

The encoders here follow the structures of ICC.1:2001-04 (version 2) and
ICC.1:2010 (version 4) field by field, independently of
:mod:`pymedphys._dicom.deidentify.icc_cleaning`, so that a test compares the
cleaner with a separate reading of the specification. They can leave
:data:`MARKER` wherever a careless or identifying writer might leave text: in
the header's identity fields, in reserved fields, in the padding between
tags, after a tag's structure, and in text and private tags.
"""

from __future__ import annotations

import dataclasses
import hashlib
import struct

MARKER = b"ZZSYNTHETICICCMARKER"
# D50 as s15Fixed16Number encodings (ICC.1 Section 7.2.16).
D50 = (0x0000F6D6, 0x00010000, 0x0000D32D)
# The sRGB primaries adapted to D50, and the D50 white, as XYZ.
SRGB_MATRIX = (
    (0.4360747, 0.3850649, 0.1430804),
    (0.2225045, 0.7168786, 0.0606169),
    (0.0139322, 0.0971045, 0.7141733),
)
WHITE = (0.9642, 1.0, 0.8249)


def s15(value: float) -> bytes:
    """Return an s15Fixed16Number."""
    return struct.pack(">i", round(value * 65536))


def u16(value: int) -> bytes:
    return struct.pack(">H", value)


def u32(value: int) -> bytes:
    return struct.pack(">I", value)


def f32(*values: float) -> bytes:
    return struct.pack(f">{len(values)}f", *values)


def pad(data: bytes, filler: bytes = b"\0") -> bytes:
    """Return ``data`` padded to a four-byte boundary with ``filler``."""
    return data + (filler * 4)[: -len(data) % 4] if len(data) % 4 else data


def reserved(careless: bool) -> bytes:
    """Return a four-byte reserved field, holding part of the marker if careless."""
    return MARKER[:4] if careless else bytes(4)


# Tag types.


def xyz(x: float, y: float, z: float, careless: bool = False) -> bytes:
    return b"XYZ " + reserved(careless) + s15(x) + s15(y) + s15(z)


def curv(entries: list[int], careless: bool = False) -> bytes:
    return (
        b"curv" + reserved(careless) + u32(len(entries)) + b"".join(map(u16, entries))
    )


def gamma(value: float) -> bytes:
    """Return a curveType holding one u8Fixed8Number gamma."""
    return b"curv" + bytes(4) + u32(1) + u16(round(value * 256))


def para(function: int, *parameters: float, careless: bool = False) -> bytes:
    return (
        b"para"
        + reserved(careless)
        + u16(function)
        + (MARKER[:2] if careless else bytes(2))
        + b"".join(map(s15, parameters))
    )


def sf32(*values: float) -> bytes:
    return b"sf32" + bytes(4) + b"".join(map(s15, values))


def text(value: bytes) -> bytes:
    return b"text" + bytes(4) + value + b"\0"


def text_description(value: bytes) -> bytes:
    """Return a version 2 textDescriptionType with ASCII, Unicode, and ScriptCode text."""
    unicode = value.decode("ascii").encode("utf-16-be")
    return (
        b"desc"
        + bytes(4)
        + u32(len(value) + 1)
        + value
        + b"\0"
        + u32(0x656E)  # Unicode language code
        + u32(len(unicode) // 2)
        + unicode
        + u16(0)
        + bytes([len(value[:66]) + 1])
        + (value[:66] + b"\0").ljust(67, b"\0")
    )


def mluc(value: bytes) -> bytes:
    """Return a multiLocalizedUnicodeType with one record."""
    encoded = value.decode("ascii").encode("utf-16-be")
    return (
        b"mluc" + bytes(4) + u32(1) + u32(12) + b"enGB" + u32(len(encoded)) + u32(28)
    ) + encoded


def signature(value: bytes) -> bytes:
    return b"sig " + bytes(4) + value


def chrm(*xy: float, careless: bool = False) -> bytes:
    return (
        b"chrm"
        + reserved(careless)
        + u16(3)
        + u16(0)
        + b"".join(struct.pack(">I", round(value * 65536)) for value in xy)
    )


def meas() -> bytes:
    # The CIE 1931 observer, a black backing, 0/45 geometry, 1% flare, and D50.
    return b"meas" + bytes(4) + u32(1) + bytes(12) + u32(1) + u32(655) + u32(1)


def view() -> bytes:
    return (
        b"view"
        + bytes(4)
        + s15(96.42)
        + s15(100.0)
        + s15(82.49)
        + s15(19.284)
        + s15(20.0)
        + s15(16.498)
        + u32(1)
    )


def cicp(primaries: int, transfer: int, matrix: int, full_range: int) -> bytes:
    return b"cicp" + bytes(4) + bytes([primaries, transfer, matrix, full_range])


def matrix_bytes(matrix, offsets=(0.0, 0.0, 0.0)) -> bytes:
    return b"".join(s15(value) for row in matrix for value in row) + b"".join(
        map(s15, offsets)
    )


def srgb_to_linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def rgb_to_xyz(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """Return the D50 XYZ of an sRGB-encoded value, components from zero to one."""
    linear = [srgb_to_linear(value) for value in rgb]
    return tuple(sum(m * v for m, v in zip(row, linear)) for row in SRGB_MATRIX)


def _pcs_xyz_16(xyz_value: tuple[float, float, float]) -> list[int]:
    """Return the 16-bit legacy PCS XYZ encoding (ICC.1 Annex A), 1.0 at 0x8000."""
    return [max(0, min(0xFFFF, round(v * 0x8000))) for v in xyz_value]


def lut16_a2b(grid: int = 5, careless: bool = False) -> bytes:
    """Return a lut16Type from RGB to the XYZ PCS, sampling sRGB on a ``grid`` grid."""
    entries = 256
    identity = [round(i * 0xFFFF / (entries - 1)) for i in range(entries)]
    table = []
    for r in range(grid):
        for g in range(grid):
            for b in range(grid):
                rgb = (r / (grid - 1), g / (grid - 1), b / (grid - 1))
                table += _pcs_xyz_16(rgb_to_xyz(rgb))
    identity_matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    return (
        b"mft2"
        + reserved(careless)
        + bytes([3, 3, grid])
        + (MARKER[:1] if careless else b"\0")
        + matrix_bytes(identity_matrix)[:36]
        + u16(entries)
        + u16(entries)
        + b"".join(map(u16, identity * 3))
        + b"".join(map(u16, table))
        + b"".join(map(u16, identity * 3))
    )


def lut8_b2a(grid: int = 3) -> bytes:
    """Return a lut8Type from the PCS to RGB, a coarse inverse of the matrix."""
    identity = list(range(256))
    table = []
    for x in range(grid):
        for y in range(grid):
            for z in range(grid):
                table += [round(255 * v / (grid - 1)) for v in (x, y, z)]
    identity_matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    return (
        b"mft1"
        + bytes(4)
        + bytes([3, 3, grid, 0])
        + matrix_bytes(identity_matrix)[:36]
        + bytes(identity * 3)
        + bytes(table)
        + bytes(identity * 3)
    )


def lut_ab(
    kind: bytes,
    elements: dict[str, bytes],
    careless: bool = False,
) -> bytes:
    """Return a lutAtoBType (``mAB ``) or lutBtoAType (``mBA ``) of three channels.

    ``elements`` maps each of ``B``, ``matrix``, ``M``, ``CLUT``, and ``A``
    that the table holds to its bytes; the elements are stored in the reverse
    order of their offsets, as a writer may choose, each padded to four bytes.
    """
    order = ("B", "matrix", "M", "CLUT", "A")
    offsets = dict.fromkeys(order, 0)
    body = b""
    for name in reversed(order):
        if name in elements:
            offsets[name] = 32 + len(body)
            body += pad(elements[name], MARKER[:1] if careless else b"\0")
    return (
        kind
        + reserved(careless)
        + bytes([3, 3])
        + bytes(2)
        + b"".join(u32(offsets[name]) for name in order)
        + body
    )


def curve_set(*curves: bytes, careless: bool = False) -> bytes:
    """Return three curves stored one after another, each on a four-byte boundary."""
    return b"".join(pad(curve, MARKER[:1] if careless else b"\0") for curve in curves)


def clut_ab(grid: int, precision: int, function) -> bytes:
    """Return the CLUT of a lutAtoBType or lutBtoAType, sampling ``function``."""
    values = []
    for r in range(grid):
        for g in range(grid):
            for b in range(grid):
                values += function((r / (grid - 1), g / (grid - 1), b / (grid - 1)))
    scale = 0xFF if precision == 1 else 0xFFFF
    form = "B" if precision == 1 else "H"
    samples = [max(0, min(scale, round(v * scale))) for v in values]
    return (
        bytes([grid, grid, grid])
        + bytes(13)
        + bytes([precision, 0, 0, 0])
        + struct.pack(f">{len(samples)}{form}", *samples)
    )


# multiProcessElementsType (ICC.1:2010 Section 10.14).


def parf(function: int, *parameters: float) -> bytes:
    return b"parf" + bytes(4) + u16(function) + u16(0) + f32(*parameters)


def samf(*values: float) -> bytes:
    return b"samf" + bytes(4) + u32(len(values)) + f32(*values)


def curf(breaks: tuple[float, ...], *segments: bytes) -> bytes:
    return (b"curf" + bytes(4) + u16(len(segments)) + u16(0) + f32(*breaks)) + b"".join(
        segments
    )


def positioned(header: bytes, elements: list[bytes], careless: bool = False) -> bytes:
    """Return ``header``, a position table, and ``elements``, each padded."""
    offset = len(header) + 8 * len(elements)
    table = b""
    body = b""
    for element in elements:
        table += u32(offset + len(body)) + u32(len(element))
        body += pad(element, MARKER[:1] if careless else b"\0")
    return header + table + body


def cvst(*curves: bytes) -> bytes:
    return positioned(
        b"cvst" + bytes(4) + u16(len(curves)) + u16(len(curves)), list(curves)
    )


def matf(matrix, offsets) -> bytes:
    inputs = len(matrix[0])
    outputs = len(matrix)
    return (
        b"matf"
        + bytes(4)
        + u16(inputs)
        + u16(outputs)
        + f32(*(value for row in matrix for value in row))
        + f32(*offsets)
    )


def clut_element(grid: int, function) -> bytes:
    values = []
    for r in range(grid):
        for g in range(grid):
            for b in range(grid):
                values += function((r / (grid - 1), g / (grid - 1), b / (grid - 1)))
    return (
        b"clut"
        + bytes(4)
        + u16(3)
        + u16(3)
        + bytes([grid] * 3)
        + bytes(13)
        + f32(*values)
    )


def mpet(*elements: bytes, careless: bool = False) -> bytes:
    header = b"mpet" + reserved(careless) + u16(3) + u16(3) + u32(len(elements))
    return positioned(header, list(elements), careless)


def srgb_curve_segments() -> bytes:
    """Return a segmented curve of the sRGB tone curve: a line, then a power."""
    return curf(
        (0.04045,),
        parf(0, 1.0, 1 / 12.92, 0.0, 0.0),
        parf(0, 2.4, 1 / 1.055, 0.055 / 1.055, 0.0),
    )


# Profiles.


@dataclasses.dataclass
class Header:
    """A profile header's fields, by default those of a version 4.3 input profile."""

    version: bytes = bytes([4, 0x30, 0, 0])
    device_class: bytes = b"scnr"
    colour_space: bytes = b"RGB "
    connection_space: bytes = b"XYZ "
    rendering_intent: int = 0
    illuminant: tuple[int, int, int] = D50
    flags: int = 0
    # Identity fields, which a source fills in.
    cmm: bytes = b"ZZCM"
    created: tuple[int, ...] = (2024, 3, 14, 9, 26, 53)
    platform: bytes = b"ZZPL"
    manufacturer: bytes = b"ZZMF"
    model: bytes = b"ZZMD"
    attributes: bytes = b"ZZATTRIB"
    creator: bytes = b"ZZCR"
    reserved: bytes = bytes(28)


def profile(
    header: Header,
    tags: list[tuple[bytes, bytes]],
    *,
    careless: bool = False,
    with_id: bool = True,
    share: bool = True,
) -> bytes:
    """Return a profile of ``tags``, with its size, and a version 4 profile's ID.

    A careless profile pads its tags with marker bytes and leaves marker bytes
    after its last tag. Tags with equal data share it where ``share`` is true.
    """
    filler = MARKER[:1] if careless else b"\0"
    offset = 132 + 12 * len(tags)
    table = u32(len(tags))
    data = b""
    placed: dict[bytes, int] = {}
    for tag, element in tags:
        if not share or element not in placed:
            placed[element] = offset + len(data)
            data += pad(element, filler)
        table += tag + u32(placed[element]) + u32(len(element))
    if careless:
        data += MARKER
    size = 128 + len(table) + len(data)

    def head(flags: int, intent: int, digest: bytes) -> bytes:
        return (
            u32(size)
            + header.cmm
            + header.version
            + header.device_class
            + header.colour_space
            + header.connection_space
            + struct.pack(">6H", *header.created)
            + b"acsp"
            + header.platform
            + u32(flags)
            + header.manufacturer
            + header.model
            + header.attributes
            + u32(intent)
            + b"".join(map(u32, header.illuminant))
            + header.creator
            + digest
            + header.reserved
        )

    digest = bytes(16)
    if with_id and header.version[0] >= 4:
        digest = hashlib.md5(
            head(0, 0, bytes(16)) + table + data, usedforsecurity=False
        ).digest()
    return head(header.flags, header.rendering_intent, digest) + table + data


def tags_of(written: bytes) -> dict[bytes, bytes]:
    """Return each tag of a profile with its data, read from its tag table."""
    (count,) = struct.unpack_from(">I", written, 128)
    found = {}
    for index in range(count):
        tag, offset, size = struct.unpack_from(">4sII", written, 132 + 12 * index)
        found[tag] = written[offset : offset + size]
    return found


def profile_id(written: bytes) -> bytes:
    """Return the MD5 profile ID of a profile, as ICC.1:2010 Section 7.2.18 defines it."""
    unsigned = bytearray(written)
    unsigned[44:48] = bytes(4)
    unsigned[64:68] = bytes(4)
    unsigned[84:100] = bytes(16)
    return hashlib.md5(bytes(unsigned), usedforsecurity=False).digest()


def text_tags(version: int) -> list[tuple[bytes, bytes]]:
    """Return the text tags that an identifying writer fills in, and private tags."""
    words = MARKER + b" ROYAL EXAMPLE HOSPITAL"
    if version == 2:
        texts = [
            (b"desc", text_description(words)),
            (b"cprt", text(words)),
            (b"dmnd", text_description(words)),
            (b"dmdd", text_description(words)),
            (b"vued", text_description(words)),
            (b"targ", text(words)),
            (b"scrd", text_description(words)),
        ]
    else:
        texts = [
            (b"desc", mluc(words)),
            (b"cprt", mluc(words)),
            (b"dmnd", mluc(words)),
            (b"dmdd", mluc(words)),
            (b"vued", mluc(words)),
            (b"targ", text(words)),
        ]
    return texts + [
        (b"tech", signature(b"dcam")),
        (b"calt", b"dtim" + bytes(4) + struct.pack(">6H", 2024, 3, 14, 9, 26, 53)),
        # Private tags: a vendor's, and an unregistered one holding text.
        (b"ZZPV", text(words)),
        (b"vcgt", b"vcgt" + bytes(4) + words),
    ]


def matrix_tags(version: int, careless: bool = False) -> list[tuple[bytes, bytes]]:
    """Return the colorimetric tags of an sRGB matrix and tone curve profile."""
    columns = list(zip(*SRGB_MATRIX))
    if version == 2:
        curve = curv(
            [round(srgb_to_linear(i / 1023) * 0xFFFF) for i in range(1024)], careless
        )
    else:
        curve = para(
            3, 2.4, 1 / 1.055, 0.055 / 1.055, 1 / 12.92, 0.04045, careless=careless
        )
    return [
        (b"wtpt", xyz(*WHITE, careless=careless)),
        (b"rXYZ", xyz(*columns[0], careless=careless)),
        (b"gXYZ", xyz(*columns[1], careless=careless)),
        (b"bXYZ", xyz(*columns[2], careless=careless)),
        (b"rTRC", curve),
        (b"gTRC", curve),
        (b"bTRC", curve),
    ]


def chromaticity_tags() -> list[tuple[bytes, bytes]]:
    return [(b"chrm", chrm(0.64, 0.33, 0.30, 0.60, 0.15, 0.06))]
