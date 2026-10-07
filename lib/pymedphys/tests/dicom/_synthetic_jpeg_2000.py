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

"""Synthetic JPEG 2000 codestreams whose packet headers say what a test
gives them.

No image is coded. Each codestream has one tile, one 8-bit component, no
wavelet decomposition, and so one sub-band and one precinct, whose
code-blocks are given in raster order. Each packet header is written as
ITU-T T.800 Section B.10 gives it, with each codeword segment's passes and
length as the test gives them, and the packet body holds that many zero
bytes, so the codestream can be read for its packet headers but not
decoded.
"""

import dataclasses
import itertools
import struct
from collections.abc import Sequence

GUARD_BITS, EXPONENT = 2, 8
# M_b = G + epsilon_b - 1 (T.800 Annex E).
MAGNITUDE_BIT_PLANES = GUARD_BITS + EXPONENT - 1
HT, HT_MIXED, BYPASS, TERMINATE_ALL = 0x40, 0x80, 0x01, 0x04
SOP, EPH = 0x02, 0x04


@dataclasses.dataclass(frozen=True)
class Contribution:
    """What one packet header says of one code-block: the coding passes and
    length of each codeword segment, as ``(passes, length)``."""

    segments: tuple[tuple[int, int], ...]

    @property
    def passes(self) -> int:
        return sum(passes for passes, _ in self.segments)


def contribution(*segments: tuple[int, int]) -> Contribution:
    return Contribution(tuple(segments))


def segment(code: int, payload: bytes) -> bytes:
    """Return a marker segment of marker ``0xFF`` then ``code``."""
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
    """Return a codestream of one packet for each layer in ``packets``.

    Parameters
    ----------
    packets : sequence of sequences of Contribution or None
        For each layer, what its packet says of each code-block, or
        ``None`` where it does not include it.
    zero_bit_planes : sequence of int
        Each code-block's zero bit-planes, written where a packet first
        includes it.
    size : tuple of int
        The columns and rows.
    block : tuple of int
        The code-block width and height exponents.
    style : int
        The code-block style of SPcod.
    scod : int
        Scod; with ``SOP`` set, ``sop`` says whether each packet has its
        SOP marker segment, and with ``EPH`` set, each packet header ends
        with an EPH marker.
    main_header : bytes
        Marker segments put after QCD in the main header.
    rsiz : int
        Rsiz of SIZ.
    """
    columns, rows = size
    across, down = -(-columns >> block[0]), -(-rows >> block[1])
    count = across * down
    first = [
        next(
            (layer for layer, packet in enumerate(packets) if packet[index]),
            999,
        )
        for index in range(count)
    ]
    inclusion = _TagTree(across, down, first)
    planes = _TagTree(across, down, list(zero_bit_planes))
    length_bits = [3] * count
    body = bytearray()
    for layer, packet in enumerate(packets):
        if scod & SOP and sop:
            body += segment(0x91, struct.pack(">H", layer))
        bits = _Bits()
        data = 0
        bits.put(int(any(packet)))
        for index, part in enumerate(packet if any(packet) else ()):
            if first[index] < layer:
                bits.put(int(part is not None))
            else:
                inclusion.encode(bits, index, layer + 1)
                if part is not None:
                    planes.encode(bits, index, 999)
            if part is None:
                continue
            _put_passes(bits, part.passes)
            needed = max(
                length.bit_length() - (passes.bit_length() - 1)
                for passes, length in part.segments
            )
            increment = max(needed - length_bits[index], 0)
            bits.put_bits((1 << (increment + 1)) - 2, increment + 1)
            length_bits[index] += increment
            for passes, length in part.segments:
                bits.put_bits(length, length_bits[index] + passes.bit_length() - 1)
                data += length
        body += bits.flush()
        if scod & EPH:
            body += b"\xff\x92"
        body += bytes(data)
    tile_part = struct.pack(">HIBB", 0, 12 + 2 + len(body), 0, 1)
    return b"".join(
        [
            b"\xff\x4f",
            segment(
                0x51,
                struct.pack(">H8IH", rsiz, columns, rows, 0, 0, columns, rows, 0, 0, 1)
                + bytes([7, 1, 1]),
            ),
            # Scod, LRCP, the layers, no component transformation, then no
            # decomposition, the code-block size and style, and the 5-3
            # reversible wavelet.
            segment(
                0x52,
                struct.pack(">BBHB", scod, 0, len(packets), 0)
                + bytes([0, block[0] - 2, block[1] - 2, style, 1]),
            ),
            segment(0x5C, bytes([GUARD_BITS << 5, EXPONENT << 3])),
            main_header,
            segment(0x90, tile_part),
            b"\xff\x93",
            bytes(body),
            b"\xff\xd9",
        ]
    )


class _Bits:
    """Packet header bits, most significant first, with a 0 bit stuffed
    after each byte of 0xFF (T.800 Section B.10.1)."""

    def __init__(self):
        self.data = bytearray()
        self.byte = 0
        self.free = 8

    def put(self, bit: int) -> None:
        if not self.free:
            self._emit()
        self.free -= 1
        self.byte |= bit << self.free

    def put_bits(self, value: int, count: int) -> None:
        for shift in reversed(range(count)):
            self.put((value >> shift) & 1)

    def _emit(self) -> None:
        self.data.append(self.byte)
        self.free = 7 if self.byte == 0xFF else 8
        self.byte = 0

    def flush(self) -> bytes:
        if self.free < (7 if self.data[-1:] == b"\xff" else 8):
            self._emit()
        if self.data[-1:] == b"\xff":
            self.data.append(0)
        return bytes(self.data)


class _TagTree:
    """A tag tree (T.800 Section B.10.2), encoded as OpenJPEG's
    ``opj_tgt_encode`` encodes it."""

    def __init__(self, across: int, down: int, leaves: list[int]):
        levels = [(across, down)]
        while levels[-1][0] * levels[-1][1] > 1:
            levels.append((-(-levels[-1][0] // 2), -(-levels[-1][1] // 2)))
        starts = list(itertools.accumulate((w * h for w, h in levels), initial=0))
        self.paths = [
            [
                starts[level] + (y >> level) * levels[level][0] + (x >> level)
                for level in reversed(range(len(levels)))
            ]
            for y in range(down)
            for x in range(across)
        ]
        self.values = [999] * starts[-1]
        for leaf, value in enumerate(leaves):
            for node in self.paths[leaf]:
                self.values[node] = min(self.values[node], value)
        self.lows = [0] * starts[-1]
        self.known = [False] * starts[-1]

    def encode(self, bits: _Bits, leaf: int, threshold: int) -> None:
        low = 0
        for node in self.paths[leaf]:
            low = max(low, self.lows[node])
            while low < threshold:
                if low >= self.values[node]:
                    if not self.known[node]:
                        bits.put(1)
                        self.known[node] = True
                    break
                bits.put(0)
                low += 1
            self.lows[node] = low


def _put_passes(bits: _Bits, passes: int) -> None:
    """Write a number of coding passes (T.800 Table B.4)."""
    if passes == 1:
        bits.put(0)
    elif passes == 2:
        bits.put_bits(0b10, 2)
    elif passes <= 5:
        bits.put_bits(0b1100 | (passes - 3), 4)
    elif passes <= 36:
        bits.put_bits(0b111100000 | (passes - 6), 9)
    else:
        bits.put_bits(0xFF80 | (passes - 37), 16)
