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

"""Read the packet headers of a JPEG 2000 or HTJ2K codestream, to tell
whether every code-block they include holds every coding pass.

A codestream that keeps the reversible 5-3 wavelet can still be truncated
to a rate, a lossy process (PS3.5 Section A.4.4), and only its packet
headers record how many coding passes each code-block holds.
:func:`coding_passes_kept` reads every packet header of every tile, in the
progression order that the coding style gives (ITU-T T.800 Annex B), and
adds up each code-block's coding passes over all layers. It then requires,
of each code-block that some packet includes:

- a Part 1 code-block (T.800 Annex D) with ``B`` magnitude bit-planes left
  after its zero bit-planes: all ``3 B - 2`` coding passes;
- an HT code-block (ITU-T T.814): its cleanup pass coded down to bit-plane
  0, alone, or from bit-plane 1 with both refinement passes, where an HT
  refinement segment of no bytes leaves the cleanup pass alone.

The magnitude bit-planes of a sub-band are ``G + epsilon_b - 1`` (T.800
Annex E), from the guard bits and the exponent that the QCD or QCC marker
segment in force gives.

One limit remains. A code-block that no packet includes is decoded as all
zero, which is how an encoder leaves out a code-block whose coefficients
are all zero. So a codestream truncated so far that it drops only whole
code-blocks, and keeps every coding pass of each code-block it includes,
is taken as kept.

``None`` means that the packets cannot be read here. That is so for a
codestream that does not hold together: one that does not start with SOC
and SIZ, does not end with EOC (or EOC and a single pad byte of 0), has a
marker segment that runs past EOC, a tile-part out of order, a packet
header that runs past its tile-part data, or packets that do not end
exactly where the tile's data ends. It is also so for what is not read
here: a Part 2 (T.801) codestream, subsampled components, more than 65,535
tiles, POC, PPM, PPT, RGN, or any other marker segment not listed in
:func:`coding_passes_kept`, mixed HT code-blocks, an HT code-block in more
than one packet, with placeholder passes, or with an empty cleanup
segment, and a code-block with no bit-plane left to code or with more
coding passes than its bit-planes allow.

Reading is bounded. A tile whose layers and precincts give more packets
than its tile-part data has bytes gives ``None`` before any packet is
read, since each packet takes at least one byte. A few bytes of headers
can still declare billions of code-blocks, so each call has a budget of
:data:`WORK_ALLOWANCE` plus the codestream's length, in code-blocks. A
precinct spends its number of code-blocks once when its first packet is
read and again for each of its packets that is not empty, and the reading
stops with ``None`` before the budget would go below 0. A lossless codestream has far more bytes than
code-blocks, unless its frame is almost all zero; the allowance covers
such a frame of 8,192 by 8,192 samples coded in code-blocks of 64 by 64.
"""

from __future__ import annotations

import dataclasses
import struct

WORK_ALLOWANCE: int = 1 << 15

# Markers, by their second byte (T.800 Annex A).
_COD = 0x52
_COC = 0x53
_QCD = 0x5C
_QCC = 0x5D
_SOT = 0x90
_SOD = 0x93
_CAP, _TLM, _PLM, _PLT, _CPF, _CRG, _COM = 0x50, 0x55, 0x57, 0x58, 0x59, 0x63, 0x64
_MAIN_HEADER = frozenset({_COD, _COC, _QCD, _QCC, _CAP, _TLM, _PLM, _CPF, _CRG, _COM})
_FIRST_TILE_PART_HEADER = frozenset({_COD, _COC, _QCD, _QCC, _PLT, _COM})
_LATER_TILE_PART_HEADER = frozenset({_PLT, _COM})
_START_OF_PACKET = b"\xff\x91"
_END_OF_PACKET_HEADER = b"\xff\x92"
_END_OF_CODESTREAM = b"\xff\xd9"

_MAXIMUM_TILES = 65535
_PART_2_CAPABILITIES = 0x8000

# Progression orders, as COD gives them (T.800 Annex A).
_LRCP, _RLCP, _RPCL, _PCRL, _CPRL = range(5)

# Scod (T.800 Annex A).
_PRECINCTS_GIVEN = 0x01
_SOP_MAY_BE_USED = 0x02
_EPH_USED = 0x04

# Code-block style (T.800 Annex A, and T.814 for the HT bits).
_BYPASS = 0x01
_TERMINATE_EACH_PASS = 0x04
_HT = 0x40
_HT_MIXED = 0x80

# Passes in a codeword segment without bypass or termination on each
# pass: every pass of the most bit-planes a code-block can have.
_PASSES_IN_ONE_SEGMENT = 109
_MAXIMUM_LENGTH_BITS = 32
_MAXIMUM_LEVELS = 32
_MAXIMUM_BLOCK_EXPONENT = 10
_MAXIMUM_BLOCK_AREA_EXPONENT = 12

# Sub-band orientations above resolution 0: HL, LH, and HH, as (xob, yob)
# of T.800 Equation B-15.
_ORIENTATIONS = ((1, 0), (0, 1), (1, 1))


class _Unreadable(Exception):
    """The packets cannot be read here."""


def coding_passes_kept(codestream: bytes) -> bool | None:
    """Return whether every code-block that a JPEG 2000 or HTJ2K
    codestream's packets include holds every coding pass, as above.

    The main header may hold only COD, COC, QCD, QCC, CAP, TLM, PLM, CPF,
    CRG, and COM marker segments, and a tile-part header only COD, COC,
    QCD, QCC, PLT, and COM, the first four in a tile's first tile-part
    only.

    Parameters
    ----------
    codestream : bytes
        One frame, as :func:`pydicom.encaps.generate_frames` gives it.

    Returns
    -------
    bool or None
        ``True`` where every included code-block holds every coding pass,
        ``False`` where one holds fewer, and ``None`` where the packets
        cannot be read here. Never raises.
    """
    try:
        return _kept(codestream)
    except _Unreadable:
        return None


@dataclasses.dataclass(frozen=True)
class _Size:
    """The SIZ marker segment: the image area ``(x0, y0, x1, y1)``, the
    tile size and the tile grid's origin, and the number of components."""

    image: tuple[int, int, int, int]
    tile_size: tuple[int, int]
    tile_origin: tuple[int, int]
    components: int

    @property
    def across(self) -> int:
        return -(-(self.image[2] - self.tile_origin[0]) // self.tile_size[0])

    @property
    def tiles(self) -> int:
        down = -(-(self.image[3] - self.tile_origin[1]) // self.tile_size[1])
        return self.across * down

    def tile_bounds(self, tile: int) -> tuple[int, int, int, int]:
        """The tile's bounds, clipped to the image area (T.800 B.3)."""
        column, row = tile % self.across, tile // self.across
        x0 = self.tile_origin[0] + column * self.tile_size[0]
        y0 = self.tile_origin[1] + row * self.tile_size[1]
        return (
            max(x0, self.image[0]),
            max(y0, self.image[1]),
            min(x0 + self.tile_size[0], self.image[2]),
            min(y0 + self.tile_size[1], self.image[3]),
        )


@dataclasses.dataclass(frozen=True)
class _Coding:
    """SPcod or SPcoc: decomposition levels, code-block width and height
    exponents, code-block style, and each resolution's precinct width and
    height exponents."""

    levels: int
    block: tuple[int, int]
    style: int
    precincts: tuple[tuple[int, int], ...]


@dataclasses.dataclass(frozen=True)
class _Defaults:
    """The COD marker segment."""

    scod: int
    progression: int
    layers: int
    coding: _Coding


@dataclasses.dataclass(frozen=True)
class _Quantisation:
    """The QCD or QCC marker segment: guard bits, whether the exponents are
    derived from the first (scalar derived), and the exponents."""

    guard_bits: int
    derived: bool
    exponents: tuple[int, ...]


@dataclasses.dataclass
class _Markers:
    """The coding and quantisation marker segments of one header."""

    cod: _Defaults | None = None
    coc: dict[int, _Coding] = dataclasses.field(default_factory=dict)
    qcd: _Quantisation | None = None
    qcc: dict[int, _Quantisation] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class _SubBand:
    """A sub-band's bounds, ``(x0, y0, x1, y1)``, and magnitude bit-planes."""

    bounds: tuple[int, int, int, int]
    magnitude_bit_planes: int


@dataclasses.dataclass(frozen=True)
class _Resolution:
    """Resolution ``index`` of a tile-component, at decomposition ``level``
    (T.800 B.5 to B.7): its bounds, precinct width and height exponents,
    precincts across and down, sub-bands, and coding style."""

    index: int
    level: int
    bounds: tuple[int, int, int, int]
    precinct: tuple[int, int]
    precincts: tuple[int, int]
    sub_bands: tuple[_SubBand, ...]
    coding: _Coding

    @property
    def precinct_count(self) -> int:
        return self.precincts[0] * self.precincts[1]


@dataclasses.dataclass(slots=True)
class _CodeBlock:
    """What the packet headers have given a code-block so far: its zero
    bit-planes, coding passes, ``Lblock``, and the codeword segment in
    progress, with the passes it holds and its capacity."""

    included: bool = False
    zero_bit_planes: int = 0
    passes: int = 0
    lblock: int = 3
    segment_passes: int = 0
    segment_capacity: int = 0


class _TagTree:
    """A tag tree's decoding state (T.800 B.10.2): each node's lower bound
    and whether its value is known, level by level from the leaves."""

    def __init__(self, across: int, down: int):
        self._sizes = [(across, down)]
        while self._sizes[-1] != (1, 1):
            across, down = self._sizes[-1]
            self._sizes.append((-(-across // 2), -(-down // 2)))
        self._bounds = [[0] * (across * down) for across, down in self._sizes]
        self._known = [[False] * (across * down) for across, down in self._sizes]

    def value_below(
        self, bits: _Bits, column: int, row: int, threshold: int
    ) -> int | None:
        """Read whether the leaf's value is below ``threshold``, walking from
        the root, and return the value where it is, otherwise ``None``."""
        bound = 0
        known = False
        for level in reversed(range(len(self._sizes))):
            index = (row >> level) * self._sizes[level][0] + (column >> level)
            bound = max(bound, self._bounds[level][index])
            known = self._known[level][index]
            while not known and bound < threshold:
                if bits.bit():
                    known = True
                else:
                    bound += 1
            self._bounds[level][index] = bound
            self._known[level][index] = known
        return bound if known and bound < threshold else None


class _Bits:
    """The bits of a packet header, most significant first, from
    ``position``, where a byte after 0xFF holds only 7 bits (T.800
    B.10.1)."""

    def __init__(self, data: bytes, position: int):
        self.data = data
        self.position = position
        self._byte = 0
        self._left = 0

    def bit(self) -> int:
        if not self._left:
            self._next_byte()
        self._left -= 1
        return (self._byte >> self._left) & 1

    def bits(self, count: int) -> int:
        value = 0
        for _ in range(count):
            value = (value << 1) | self.bit()
        return value

    def end(self) -> int:
        """Return where the header ends: after its current byte, and after
        the stuffed byte that follows where that byte is 0xFF."""
        if self._byte == 0xFF:
            self._next_byte()
        return self.position

    def _next_byte(self):
        if self.position >= len(self.data):
            raise _Unreadable
        stuffed = self._byte == 0xFF
        self._byte = self.data[self.position]
        if stuffed and self._byte & 0x80:
            raise _Unreadable
        self._left = 7 if stuffed else 8
        self.position += 1


@dataclasses.dataclass
class _PrecinctBand:
    """A precinct's code-blocks in one sub-band, with its inclusion and zero
    bit-plane tag trees."""

    sub_band: _SubBand
    style: int
    across: int
    blocks: list[_CodeBlock]
    inclusion: _TagTree
    zero_bit_planes: _TagTree

    @property
    def ht(self) -> bool:
        return bool(self.style & _HT)


class _Budget:
    """The code-blocks that a call may still visit."""

    def __init__(self, units: int):
        self.units = units

    def spend(self, units: int):
        self.units -= units
        if self.units < 0:
            raise _Unreadable


def _kept(codestream: bytes) -> bool:
    if codestream[:4] != b"\xff\x4f\xff\x51":
        raise _Unreadable
    if codestream[-2:] == _END_OF_CODESTREAM:
        end = len(codestream) - 2
    elif codestream[-3:] == _END_OF_CODESTREAM + b"\x00":
        end = len(codestream) - 3
    else:
        raise _Unreadable
    size, position = _read_size(codestream, end)
    main, position = _read_header(codestream, position, end, _MAIN_HEADER, _SOT, size)
    if main.cod is None or main.qcd is None:
        raise _Unreadable
    headers, bodies = _read_tile_parts(codestream, position, end, size)
    budget = _Budget(WORK_ALLOWANCE + len(codestream))
    kept = True
    for tile, (header, body) in enumerate(zip(headers, bodies)):
        kept = _read_tile(size, main, header, body, tile, budget) and kept
    return kept


def _marker_segment(data: bytes, position: int, limit: int) -> tuple[int, bytes]:
    """Return the marker and payload of the marker segment at ``position``,
    which must end by ``limit``."""
    if position + 4 > limit or data[position] != 0xFF:
        raise _Unreadable
    (length,) = struct.unpack_from(">H", data, position + 2)
    if length < 2 or position + 2 + length > limit:
        raise _Unreadable
    return data[position + 1], data[position + 4 : position + 2 + length]


def _read_size(data: bytes, end: int) -> tuple[_Size, int]:
    """Read SIZ, and return it with where the main header continues."""
    _, payload = _marker_segment(data, 2, end)
    if len(payload) < 36:
        raise _Unreadable
    rsiz, x1, y1, x0, y0, tile_width, tile_height, tile_x0, tile_y0, components = (
        struct.unpack_from(">H8IH", payload)
    )
    if (
        components < 1
        or len(payload) != 36 + 3 * components
        or rsiz & _PART_2_CAPABILITIES
    ):
        raise _Unreadable
    # XRsiz and YRsiz of every component: none is subsampled.
    if any(payload[37 + 3 * i : 39 + 3 * i] != b"\x01\x01" for i in range(components)):
        raise _Unreadable
    # The tile grid starts at or before the image, and the image starts
    # inside the first tile and inside the image.
    if not (
        tile_x0 <= x0 < min(x1, tile_x0 + tile_width)
        and tile_y0 <= y0 < min(y1, tile_y0 + tile_height)
    ):
        raise _Unreadable
    size = _Size(
        (x0, y0, x1, y1), (tile_width, tile_height), (tile_x0, tile_y0), components
    )
    if size.tiles > _MAXIMUM_TILES:
        raise _Unreadable
    return size, 6 + len(payload)


def _read_header(
    data: bytes,
    position: int,
    limit: int,
    allowed: frozenset[int],
    until: int,
    size: _Size,
) -> tuple[_Markers, int]:
    """Read the marker segments of a main or tile-part header from
    ``position`` up to the marker ``until``, SOT or SOD, and return those
    that set coding and quantisation, with where ``until`` is."""
    markers = _Markers()
    while True:
        if position + 2 > limit or data[position] != 0xFF:
            raise _Unreadable
        if data[position + 1] == until:
            return markers, position
        code, payload = _marker_segment(data, position, limit)
        if code not in allowed:
            raise _Unreadable
        if code == _COD:
            if markers.cod is not None:
                raise _Unreadable
            markers.cod = _read_cod(payload)
        elif code == _QCD:
            if markers.qcd is not None:
                raise _Unreadable
            markers.qcd = _read_quantisation(payload)
        elif code == _COC:
            component, rest = _component(payload, size.components, markers.coc)
            # Scoc, then SPcoc.
            markers.coc[component] = _read_coding(rest[1:], rest[0] & _PRECINCTS_GIVEN)
        elif code == _QCC:
            component, rest = _component(payload, size.components, markers.qcc)
            markers.qcc[component] = _read_quantisation(rest)
        position += 4 + len(payload)


def _component(payload: bytes, components: int, seen: dict) -> tuple[int, bytes]:
    """Split the component index, Ccoc or Cqcc, from a COC or QCC payload,
    where it is a component that ``seen`` does not yet hold, and something
    follows it."""
    width = 1 if components <= 256 else 2
    if len(payload) <= width:
        raise _Unreadable
    component = int.from_bytes(payload[:width], "big")
    if component >= components or component in seen:
        raise _Unreadable
    return component, payload[width:]


def _read_cod(payload: bytes) -> _Defaults:
    """Read COD: Scod, progression order, layers, the multiple component
    transformation, then SPcod."""
    if len(payload) < 5:
        raise _Unreadable
    scod, progression, layers = struct.unpack_from(">BBH", payload)
    if progression > _CPRL or not layers:
        raise _Unreadable
    coding = _read_coding(payload[5:], scod & _PRECINCTS_GIVEN)
    return _Defaults(scod, progression, layers, coding)


def _read_coding(parameters: bytes, precincts_given: int) -> _Coding:
    """Read SPcod or SPcoc."""
    if len(parameters) < 5:
        raise _Unreadable
    levels, width, height, style = parameters[0], *parameters[1:4]
    block = (width + 2, height + 2)
    if (
        levels > _MAXIMUM_LEVELS
        or len(parameters) != 5 + (levels + 1 if precincts_given else 0)
        or max(block) > _MAXIMUM_BLOCK_EXPONENT
        or sum(block) > _MAXIMUM_BLOCK_AREA_EXPONENT
        or style & _HT_MIXED
    ):
        raise _Unreadable
    if precincts_given:
        # PPx in the low four bits and PPy in the high four.
        precincts = tuple((each & 0x0F, each >> 4) for each in parameters[5:])
        if any(0 in each for each in precincts[1:]):
            raise _Unreadable
    else:
        precincts = ((15, 15),) * (levels + 1)
    return _Coding(levels, block, style, precincts)


def _read_quantisation(payload: bytes) -> _Quantisation:
    """Read QCD, or QCC after its component: Sqcd or Sqcc, then each
    sub-band's exponent in the top 5 bits of its byte or 16 bits."""
    if not payload:
        raise _Unreadable
    guard_bits, style = payload[0] >> 5, payload[0] & 0x1F
    values = payload[1:]
    if style == 0:
        exponents = tuple(each >> 3 for each in values)
    elif style in (1, 2) and len(values) % 2 == 0:
        exponents = tuple(each >> 3 for each in values[::2])
    else:
        raise _Unreadable
    if not exponents or (style == 1 and len(exponents) > 1):
        raise _Unreadable
    return _Quantisation(guard_bits, style == 1, exponents)


def _read_tile_parts(
    data: bytes, position: int, end: int, size: _Size
) -> tuple[list[_Markers], list[bytes]]:
    """Read the tile-parts from ``position`` to EOC, and return each tile's
    first tile-part header and its tile-part bodies joined in order."""
    headers: dict[int, _Markers] = {}
    bodies: list[list[bytes]] = [[] for _ in range(size.tiles)]
    # Each tile's non-zero TNsot values.
    declared: list[set[int]] = [set() for _ in range(size.tiles)]
    while position < end:
        code, payload = _marker_segment(data, position, end)
        if code != _SOT or len(payload) != 8:
            raise _Unreadable
        # Isot, Psot, TPsot, and TNsot.
        tile, length, part, parts = struct.unpack(">HIBB", payload)
        if tile >= size.tiles or part != len(bodies[tile]):
            raise _Unreadable
        part_end = end if length == 0 else position + length
        if part_end > end:
            raise _Unreadable
        allowed = _LATER_TILE_PART_HEADER if part else _FIRST_TILE_PART_HEADER
        markers, sod = _read_header(data, position + 12, part_end, allowed, _SOD, size)
        if not part:
            headers[tile] = markers
        bodies[tile].append(data[sod + 2 : part_end])
        if parts:
            declared[tile].add(parts)
        position = part_end
    for tile, tile_parts in enumerate(bodies):
        if not tile_parts or declared[tile] - {len(tile_parts)}:
            raise _Unreadable
    return [headers[tile] for tile in range(size.tiles)], [
        b"".join(tile_parts) for tile_parts in bodies
    ]


def _read_tile(
    size: _Size,
    main: _Markers,
    header: _Markers,
    body: bytes,
    tile: int,
    budget: _Budget,
) -> bool:
    """Read every packet of a tile, and return whether every code-block they
    include holds every coding pass."""
    # T.800 Section A.6: a tile's COD or QCD replaces the main header's,
    # with the main header's COC or QCC entries, and the tile's own COC and
    # QCC entries apply over whatever is in force.
    cod = header.cod or main.cod
    qcd = header.qcd or main.qcd
    if cod is None or qcd is None:
        raise _Unreadable
    cocs = {**(main.coc if header.cod is None else {}), **header.coc}
    qccs = {**(main.qcc if header.qcd is None else {}), **header.qcc}
    bounds = size.tile_bounds(tile)
    components = []
    precincts = 0
    for component in range(size.components):
        resolutions = _resolutions(
            bounds, cocs.get(component, cod.coding), qccs.get(component, qcd)
        )
        components.append(resolutions)
        # Each packet takes at least one byte. The highest resolution has
        # at least one precinct, so this stops within as many components
        # as the body has bytes.
        precincts += sum(resolution.precinct_count for resolution in resolutions)
        if cod.layers * precincts > len(body):
            raise _Unreadable

    states: dict[tuple[int, int, int], list[_PrecinctBand]] = {}
    position = 0
    for layer, component, r, precinct in _packets(cod, components, bounds):
        bands = states.get((component, r, precinct))
        if bands is None:
            bands = _precinct_bands(components[component][r], precinct, budget)
            states[(component, r, precinct)] = bands
        position = _read_packet(body, position, cod.scod, bands, layer, budget)
    if position != len(body):
        raise _Unreadable

    kept = True
    for bands in states.values():
        for band in bands:
            for block in band.blocks:
                if block.included:
                    kept = _block_kept(band, block) and kept
    return kept


def _resolutions(
    bounds: tuple[int, int, int, int], coding: _Coding, quantisation: _Quantisation
) -> list[_Resolution]:
    """Return a tile-component's resolutions, with their sub-bands and
    precincts (T.800 B.5, B.6, and B.7)."""
    levels = coding.levels
    if not quantisation.derived and len(quantisation.exponents) < 3 * levels + 1:
        raise _Unreadable
    resolutions = []
    for r in range(levels + 1):
        level = levels - r
        x0, y0, x1, y1 = (-(-each >> level) for each in bounds)
        if r == 0:
            sub_bands = [_SubBand((x0, y0, x1, y1), _bit_planes(quantisation, 0, 0))]
        else:
            sub_bands = [
                _SubBand(
                    _sub_band_bounds(bounds, level + 1, orientation),
                    _bit_planes(quantisation, r, index),
                )
                for index, orientation in enumerate(_ORIENTATIONS)
            ]
        width, height = coding.precincts[r]
        precincts = (
            -(-x1 >> width) - (x0 >> width) if x1 > x0 else 0,
            -(-y1 >> height) - (y0 >> height) if y1 > y0 else 0,
        )
        resolutions.append(
            _Resolution(
                r,
                level,
                (x0, y0, x1, y1),
                (width, height),
                precincts,
                tuple(sub_bands),
                coding,
            )
        )
    return resolutions


def _sub_band_bounds(
    bounds: tuple[int, int, int, int], level: int, orientation: tuple[int, int]
) -> tuple[int, int, int, int]:
    """Return the bounds of a sub-band at decomposition ``level`` of the
    tile-component of ``bounds`` (T.800 Equation B-15)."""
    x_offset, y_offset = (each << (level - 1) for each in orientation)
    x0, y0, x1, y1 = bounds
    return (
        -(-(x0 - x_offset) >> level),
        -(-(y0 - y_offset) >> level),
        -(-(x1 - x_offset) >> level),
        -(-(y1 - y_offset) >> level),
    )


def _bit_planes(quantisation: _Quantisation, r: int, orientation: int) -> int:
    """Return ``M_b`` of a sub-band of resolution ``r``: LL, or HL, LH, and
    HH as ``orientation`` 0, 1, and 2 (T.800 Annex E)."""
    if quantisation.derived:
        # Scalar derived: the first exponent, less NL less the sub-band's
        # decomposition level, which is r - 1 above resolution 0.
        exponent = max(quantisation.exponents[0] - max(r - 1, 0), 0)
    else:
        exponent = quantisation.exponents[3 * r - 2 + orientation if r else 0]
    return quantisation.guard_bits + exponent - 1


def _packets(
    cod: _Defaults,
    components: list[list[_Resolution]],
    bounds: tuple[int, int, int, int],
) -> list[tuple[int, int, int, int]]:
    """Return each packet of a tile, as layer, component, resolution, and
    precinct, in the progression order (T.800 B.12) with no component
    subsampled."""
    layers = range(cod.layers)
    if cod.progression in (_LRCP, _RLCP):
        top = range(max(len(resolutions) for resolutions in components))
        if cod.progression == _LRCP:
            order = [(layer, r) for layer in layers for r in top]
        else:
            order = [(layer, r) for r in top for layer in layers]
        return [
            (layer, component, r, precinct)
            for layer, r in order
            for component, resolutions in enumerate(components)
            if r < len(resolutions)
            for precinct in range(resolutions[r].precinct_count)
        ]
    # Each precinct at its position on the reference grid, every layer of
    # it before the next.
    keys = []
    for component, resolutions in enumerate(components):
        for r, resolution in enumerate(resolutions):
            for precinct in range(resolution.precinct_count):
                x, y = _precinct_position(resolution, precinct, bounds)
                key = {
                    _RPCL: (r, y, x, component),
                    _PCRL: (y, x, component, r),
                    _CPRL: (component, y, x, r),
                }[cod.progression]
                keys.append((key, component, r, precinct))
    return [(layer, *packet) for _, *packet in sorted(keys) for layer in layers]


def _precinct_position(
    resolution: _Resolution, precinct: int, bounds: tuple[int, int, int, int]
) -> tuple[int, int]:
    """Return the top-left corner of a precinct's cell on the reference
    grid, or the tile's origin on an axis where the cell starts before it."""
    across = resolution.precincts[0]
    column, row = precinct % across, precinct // across
    width, height = resolution.precinct
    x0, y0 = resolution.bounds[:2]
    x = ((x0 >> width) + column) << (width + resolution.level)
    y = ((y0 >> height) + row) << (height + resolution.level)
    return max(x, bounds[0]), max(y, bounds[1])


def _precinct_bands(
    resolution: _Resolution, precinct: int, budget: _Budget
) -> list[_PrecinctBand]:
    """Return the state of a precinct's code-blocks in each sub-band where
    it has some, after spending their number from ``budget`` (T.800 B.7)."""
    across = resolution.precincts[0]
    column, row = precinct % across, precinct // across
    # Above resolution 0, a precinct's cell in a sub-band is half its size
    # in the resolution.
    halved = 1 if resolution.index else 0
    width, height = (each - halved for each in resolution.precinct)
    x0, y0 = resolution.bounds[:2]
    cell_x = ((x0 >> resolution.precinct[0]) + column) << width
    cell_y = ((y0 >> resolution.precinct[1]) + row) << height
    block_width = min(resolution.coding.block[0], width)
    block_height = min(resolution.coding.block[1], height)
    grids = []
    for sub_band in resolution.sub_bands:
        bx0, by0, bx1, by1 = sub_band.bounds
        if bx1 <= bx0 or by1 <= by0:
            continue
        px0, px1 = max(cell_x, bx0), min(cell_x + (1 << width), bx1)
        py0, py1 = max(cell_y, by0), min(cell_y + (1 << height), by1)
        blocks_across = max(0, -(-px1 >> block_width) - (px0 >> block_width))
        blocks_down = max(0, -(-py1 >> block_height) - (py0 >> block_height))
        if blocks_across and blocks_down:
            grids.append((sub_band, blocks_across, blocks_down))
    budget.spend(
        sum(blocks_across * blocks_down for _, blocks_across, blocks_down in grids)
    )
    return [
        _PrecinctBand(
            sub_band,
            resolution.coding.style,
            blocks_across,
            [_CodeBlock() for _ in range(blocks_across * blocks_down)],
            _TagTree(blocks_across, blocks_down),
            _TagTree(blocks_across, blocks_down),
        )
        for sub_band, blocks_across, blocks_down in grids
    ]


def _read_packet(
    body: bytes,
    position: int,
    scod: int,
    bands: list[_PrecinctBand],
    layer: int,
    budget: _Budget,
) -> int:
    """Read the packet at ``position`` of a precinct's ``layer``, and return
    where it ends (T.800 B.10)."""
    if scod & _SOP_MAY_BE_USED and body[position : position + 2] == _START_OF_PACKET:
        # Lsop must be 4; Nsop is not checked.
        if body[position + 2 : position + 4] != b"\x00\x04" or position + 6 > len(body):
            raise _Unreadable
        position += 6
    bits = _Bits(body, position)
    length = 0
    if bits.bit():
        budget.spend(sum(len(band.blocks) for band in bands))
        for band in bands:
            for index, block in enumerate(band.blocks):
                length += _read_code_block(bits, band, index, block, layer)
    position = bits.end()
    if scod & _EPH_USED:
        if body[position : position + 2] != _END_OF_PACKET_HEADER:
            raise _Unreadable
        position += 2
    position += length
    if position > len(body):
        raise _Unreadable
    return position


def _read_code_block(
    bits: _Bits, band: _PrecinctBand, index: int, block: _CodeBlock, layer: int
) -> int:
    """Read a code-block's part of a packet header, and return the length of
    its codeword segments in the packet's body."""
    if block.included:
        if not bits.bit():
            return 0
        if band.ht:
            raise _Unreadable
    else:
        column, row = index % band.across, index // band.across
        # Included here where its first layer is below this one plus 1.
        if band.inclusion.value_below(bits, column, row, layer + 1) is None:
            return 0
        # Reading the zero bit-planes against a threshold one above M_b
        # reads the same bits as raising it one at a time, and stops once
        # they could only exceed M_b.
        zero_bit_planes = band.zero_bit_planes.value_below(
            bits, column, row, band.sub_band.magnitude_bit_planes + 1
        )
        if zero_bit_planes is None:
            raise _Unreadable
        block.included = True
        block.zero_bit_planes = zero_bit_planes
    passes = _read_pass_count(bits)
    while bits.bit():
        block.lblock += 1
    if band.ht:
        return _read_ht_lengths(bits, block, passes)
    length = 0
    remaining = passes
    while remaining:
        if block.segment_passes == block.segment_capacity:
            block.segment_capacity = _segment_capacity(band.style, block)
            block.segment_passes = 0
        part = min(remaining, block.segment_capacity - block.segment_passes)
        length += _read_length(bits, block.lblock + part.bit_length() - 1)
        block.segment_passes += part
        remaining -= part
    block.passes += passes
    return length


def _read_pass_count(bits: _Bits) -> int:
    """Read a number of coding passes (T.800 Table B.4)."""
    if not bits.bit():
        return 1
    if not bits.bit():
        return 2
    value = bits.bits(2)
    if value < 3:
        return 3 + value
    value = bits.bits(5)
    if value < 31:
        return 6 + value
    return 37 + bits.bits(7)


def _segment_capacity(style: int, block: _CodeBlock) -> int:
    """Return how many passes a code-block's next codeword segment holds
    (T.800 Annex D.4 and B.10.7)."""
    if style & _TERMINATE_EACH_PASS:
        return 1
    if style & _BYPASS:
        if not block.segment_capacity:
            return 10
        return 2 if block.segment_capacity in (1, 10) else 1
    return _PASSES_IN_ONE_SEGMENT


def _read_ht_lengths(bits: _Bits, block: _CodeBlock, passes: int) -> int:
    """Read the lengths of an HT code-block's cleanup segment and, where it
    has refinement passes, its refinement segment (T.814 B.3), and
    return their sum."""
    if passes > 3:
        raise _Unreadable
    cleanup = _read_length(bits, block.lblock)
    if not cleanup:
        raise _Unreadable
    refinement = 0
    if passes > 1:
        refinement = _read_length(bits, block.lblock + (passes - 1).bit_length() - 1)
    # Refinement passes without bytes leave the cleanup pass alone.
    block.passes = passes if refinement else 1
    return cleanup + refinement


def _read_length(bits: _Bits, count: int) -> int:
    if count > _MAXIMUM_LENGTH_BITS:
        raise _Unreadable
    return bits.bits(count)


def _block_kept(band: _PrecinctBand, block: _CodeBlock) -> bool:
    """Return whether an included code-block holds every coding pass."""
    planes = band.sub_band.magnitude_bit_planes - block.zero_bit_planes
    if band.ht:
        # The bit-plane that the cleanup pass codes down to.
        lowest = planes - 1
        if lowest < 0 or (block.passes == 3 and lowest == 0):
            raise _Unreadable
        return (block.passes, lowest) in ((1, 0), (3, 1))
    if planes < 1 or block.passes > 3 * planes - 2:
        raise _Unreadable
    return block.passes == 3 * planes - 2
