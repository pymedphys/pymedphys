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

"""Synthetic JPEG 2000 codestreams whose packet headers a test chooses.

No image is coded. :func:`codestream` writes a codestream of one 8-bit
component in one tile, with no wavelet decomposition, so one LL sub-band
and one precinct, and writes each layer's packet header as ITU-T T.800
B.10 gives it, from the coding passes and codeword segment lengths that a
test gives each code-block. Each packet body is that many bytes of 0. The
codestreams can be read for their packet headers, but not decoded.
"""

import dataclasses
import struct
from collections.abc import Sequence

GUARD_BITS = 2
EXPONENT = 8
MAGNITUDE_BIT_PLANES = GUARD_BITS + EXPONENT - 1

# Code-block style (SPcod): HT code-blocks, mixed HT code-blocks, selective
# arithmetic coding bypass, and termination on each coding pass.
HT = 0x40
HT_MIXED = 0x80
BYPASS = 0x01
TERMINATE_ALL = 0x04
# Scod: SOP marker segments may be used, and EPH markers are used.
SOP = 0x02
EPH = 0x04

# The value of a tag tree leaf, in either tree, of a code-block that no
# packet includes.
_NEVER = 999


@dataclasses.dataclass(frozen=True)
class Contribution:
    """A code-block's part of one packet: its codeword segments, each as
    ``(passes, length)``."""

    segments: tuple[tuple[int, int], ...]

    @property
    def passes(self) -> int:
        return sum(passes for passes, _ in self.segments)


def contribution(*segments: tuple[int, int]) -> Contribution:
    """Return a :class:`Contribution` of ``segments``, each
    ``(passes, length)``."""
    return Contribution(tuple(segments))


def segment(code: int, payload: bytes) -> bytes:
    """Return a marker segment: the marker ``0xFF`` and ``code``, its
    length, and ``payload``."""
    return struct.pack(">BBH", 0xFF, code, len(payload) + 2) + payload


def codestream(
    packets: Sequence[Sequence[Contribution | None]],
    zero_bit_planes: Sequence[int],
    *,
    size: tuple[int, int] = (8, 8),
    block: tuple[int, int] = (3, 3),
    style: int = 0,
    scod: int = 0,
    sop: bool = True,
    main_header: bytes = b"",
    rsiz: int = 0,
) -> bytes:
    """Return a codestream whose packet headers give what ``packets`` says.

    Parameters
    ----------
    packets : sequence of sequences of Contribution or None
        For each layer, each code-block's contribution to its packet, in
        raster order, or ``None`` where the packet does not include it.
    zero_bit_planes : sequence of int
        Each code-block's zero bit-planes.
    size : tuple of int
        The image's columns and rows.
    block : tuple of int
        The code-block width and height exponents.
    style : int
        SPcod's code-block style.
    scod : int
        Scod. With :data:`SOP` set, each packet starts with an SOP marker
        segment where ``sop`` is true; with :data:`EPH` set, each packet
        header ends with an EPH marker.
    sop : bool
    main_header : bytes
        Marker segments placed after QCD.
    rsiz : int
        SIZ's Rsiz.

    Returns
    -------
    bytes
        SOC, SIZ, COD, QCD, ``main_header``, then one tile-part of every
        packet, in layer order, and EOC.
    """
    columns, rows = size
    blocks = _CodeBlocks(
        -(-columns // (1 << block[0])),
        -(-rows // (1 << block[1])),
        packets,
        zero_bit_planes,
    )
    body = bytearray()
    for layer, contributions in enumerate(packets):
        if scod & SOP and sop:
            body += segment(0x91, struct.pack(">H", layer & 0xFFFF))
        body += blocks.packet_header(layer, contributions)
        if scod & EPH:
            body += b"\xff\x92"
        # The packet body: as many bytes of 0 as the lengths add up to.
        body += bytes(
            sum(
                length
                for each in contributions
                if each is not None
                for _, length in each.segments
            )
        )

    tile_part = struct.pack(">HIBB", 0, 12 + 2 + len(body), 0, 1)
    image = struct.pack(">H8IH", rsiz, columns, rows, 0, 0, columns, rows, 0, 0, 1)
    coding = struct.pack(">BBHB", scod, 0, len(packets), 0) + bytes(
        [0, block[0] - 2, block[1] - 2, style, 1]
    )
    return b"".join(
        [
            b"\xff\x4f",
            segment(0x51, image + bytes([7, 1, 1])),
            segment(0x52, coding),
            segment(0x5C, bytes([GUARD_BITS << 5, EXPONENT << 3])),
            main_header,
            segment(0x90, tile_part),
            b"\xff\x93",
            bytes(body),
            b"\xff\xd9",
        ]
    )


class _Bits:
    """Packet header bits, most significant first, where the byte after a
    byte of 0xFF carries only 7 bits, with its top bit 0 (T.800 B.10.1)."""

    def __init__(self):
        self._bytes = bytearray()
        self._byte = 0
        self._count = 0

    def write(self, bit: int | bool):
        capacity = 7 if self._bytes[-1:] == b"\xff" else 8
        self._byte = (self._byte << 1) | int(bit)
        self._count += 1
        if self._count == capacity:
            self._bytes.append(self._byte)
            self._byte, self._count = 0, 0

    def write_value(self, value: int, count: int):
        for shift in reversed(range(count)):
            self.write((value >> shift) & 1)

    def flush(self) -> bytes:
        """Return the header's bytes: the partial byte, padded with 0 bits,
        where it holds any bit, then a byte of 0 after a last byte of
        0xFF."""
        if self._count:
            capacity = 7 if self._bytes[-1:] == b"\xff" else 8
            self._bytes.append(self._byte << (capacity - self._count))
        if self._bytes[-1:] == b"\xff":
            self._bytes.append(0)
        return bytes(self._bytes)


class _TagTree:
    """A tag tree's encoding state (T.800 B.10.2): each node's value, the
    minimum of its leaves, the lower bound already conveyed, and whether
    the value has been sent, level by level from the leaves."""

    def __init__(self, across: int, down: int, leaves: Sequence[int]):
        self._sizes = [(across, down)]
        self._values = [list(leaves)]
        while self._sizes[-1] != (1, 1):
            below_across, below_down = self._sizes[-1]
            below = self._values[-1]
            across, down = -(-below_across // 2), -(-below_down // 2)
            self._sizes.append((across, down))
            self._values.append(
                [
                    min(
                        below[y * below_across + x]
                        for y in (2 * row, 2 * row + 1)
                        for x in (2 * column, 2 * column + 1)
                        if x < below_across and y < below_down
                    )
                    for row in range(down)
                    for column in range(across)
                ]
            )
        self._bounds = [[0] * len(values) for values in self._values]
        self._sent = [[False] * len(values) for values in self._values]

    def encode(self, bits: _Bits, column: int, row: int, threshold: int):
        """Write whether the leaf's value is below ``threshold``, walking
        from the root to the leaf."""
        bound = 0
        for level in reversed(range(len(self._sizes))):
            index = (row >> level) * self._sizes[level][0] + (column >> level)
            bound = max(bound, self._bounds[level][index])
            while bound < threshold:
                if bound >= self._values[level][index]:
                    if not self._sent[level][index]:
                        bits.write(1)
                        self._sent[level][index] = True
                    break
                bits.write(0)
                bound += 1
            self._bounds[level][index] = bound


class _CodeBlocks:
    """The code-blocks of the one precinct, with their first layers,
    ``Lblock``, and inclusion and zero bit-plane tag trees."""

    def __init__(
        self,
        across: int,
        down: int,
        packets: Sequence[Sequence[Contribution | None]],
        zero_bit_planes: Sequence[int],
    ):
        self._across = across
        self._first_layers = [
            next(
                (
                    layer
                    for layer, each in enumerate(packets)
                    if each[index] is not None
                ),
                _NEVER,
            )
            for index in range(across * down)
        ]
        self._zero_bit_planes = zero_bit_planes
        self._lblocks = [3] * (across * down)
        self._inclusion = _TagTree(across, down, self._first_layers)
        self._zero_bit_plane_tree = _TagTree(
            across,
            down,
            [
                _NEVER if first == _NEVER else planes
                for first, planes in zip(self._first_layers, zero_bit_planes)
            ],
        )

    def packet_header(
        self, layer: int, contributions: Sequence[Contribution | None]
    ) -> bytes:
        """Return the packet header of ``layer`` (T.800 B.10)."""
        bits = _Bits()
        bits.write(any(each is not None for each in contributions))
        if any(each is not None for each in contributions):
            for index, each in enumerate(contributions):
                self._inclusion_and_zero_bit_planes(bits, layer, index, each)
                if each is not None:
                    self._lblocks[index] = _write_code_block(
                        bits, each, self._lblocks[index]
                    )
        return bits.flush()

    def _inclusion_and_zero_bit_planes(
        self, bits: _Bits, layer: int, index: int, each: Contribution | None
    ):
        """Write a code-block's inclusion, by one bit where an earlier packet
        included it, otherwise by the inclusion tag tree, followed by its
        zero bit-planes where this packet includes it first."""
        if self._first_layers[index] < layer:
            bits.write(each is not None)
            return
        column, row = index % self._across, index // self._across
        self._inclusion.encode(bits, column, row, layer + 1)
        if each is not None:
            # To completion: until the value is below the threshold.
            for threshold in range(1, self._zero_bit_planes[index] + 2):
                self._zero_bit_plane_tree.encode(bits, column, row, threshold)


def _write_code_block(bits: _Bits, each: Contribution, lblock: int) -> int:
    """Write an included code-block's coding passes, ``Lblock`` increment,
    and segment lengths, and return its ``Lblock`` after the increment."""
    _write_pass_count(bits, each.passes)
    increment = 0
    while any(
        length >= 1 << (lblock + increment + passes.bit_length() - 1)
        for passes, length in each.segments
    ):
        increment += 1
    for _ in range(increment):
        bits.write(1)
    bits.write(0)
    lblock += increment
    for passes, length in each.segments:
        bits.write_value(length, lblock + passes.bit_length() - 1)
    return lblock


def _write_pass_count(bits: _Bits, passes: int):
    """Write a number of coding passes, 1 to 164 (T.800 Table B.4)."""
    if passes == 1:
        bits.write(0)
    elif passes == 2:
        bits.write_value(0b10, 2)
    elif passes <= 5:
        bits.write_value(0b1100 | (passes - 3), 4)
    elif passes <= 36:
        bits.write_value((0b1111 << 5) | (passes - 6), 9)
    else:
        bits.write_value((0b111111111 << 7) | (passes - 37), 16)
