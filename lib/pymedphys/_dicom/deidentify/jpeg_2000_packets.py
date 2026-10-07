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
whether every code-block kept every coding pass.

A JPEG 2000 codestream with the reversible 5-3 wavelet is lossless only
if each code-block holds every coding pass down to the least significant
bit-plane. A codestream truncated to a rate keeps the reversible wavelet
but drops trailing passes, a lossy process (PS3.5 Section A.4.4), and only
the packet headers record how many passes each code-block holds (ITU-T
T.800 Annex B). :func:`coding_passes_kept` reads every packet header of
every tile, in the progression order that the COD marker segment gives,
and compares what each code-block holds with what it must hold:

- A code-block of ITU-T T.800 (Part 1) coding, with ``M_b`` magnitude
  bit-planes in its sub-band, ``G + epsilon_b - 1`` from the guard bits and
  exponent of the QCD or QCC marker segment (T.800 Annex E), and ``P`` zero
  bit-planes from its packet header, must hold ``3 (M_b - P) - 2`` coding
  passes: a cleanup pass for its most significant bit-plane, then a
  significance propagation, a magnitude refinement, and a cleanup pass for
  each bit-plane below it.
- A code-block of ITU-T T.814 (HTJ2K) coding holds one HT cleanup pass,
  which codes down to bit-plane ``M_b - 1 - P``, and may hold a
  significance propagation and a magnitude refinement pass, which code one
  bit-plane further. It must reach bit-plane 0: a cleanup pass alone with
  ``P = M_b - 1``, or with both refinement passes with ``P = M_b - 2``.

The geometry of tiles, resolutions, sub-bands, precincts, and code-blocks,
the progression orders, and the reading of each packet header follow
T.800 Annex B as OpenJPEG 2.5 implements it, since pylibjpeg-openjpeg,
which decodes these syntaxes here, is built on it.

A code-block that no packet includes holds no pass, and is decoded as all
zero. An encoder leaves out a code-block whose coefficients are all zero,
but a codestream truncated so far that it drops whole code-blocks, and
keeps every pass of each code-block it includes, cannot be told from one
coded losslessly. It is not detected here.

Each packet must be where the one before it ends, every packet of every
tile must be present, and the tile-part bodies must end with the last
packet. Where they do not, or the codestream uses what is not read here,
``None`` is returned, so the frame is not taken as lossless: packed packet
headers (PPM and PPT), progression order changes (POC), a region of
interest (RGN), extensions of ITU-T T.801 (Part 2), mixed HT and Part 1
code-blocks, and an HT code-block in more than one packet or with
placeholder passes, which OpenJPEG 2.5 does not read as T.814 gives them.
"""

from __future__ import annotations

import dataclasses
import itertools
import struct
from collections.abc import Iterator

# Marker segments allowed in the main header, in a tile's first tile-part
# header, and in its later ones; any other ends the reading. CAP and CPF
# are of T.814.
_COD, _COC, _QCD, _QCC = 0x52, 0x53, 0x5C, 0x5D
_MAIN_HEADER = frozenset({_COD, _COC, _QCD, _QCC, 0x50, 0x55, 0x57, 0x59, 0x63, 0x64})
_LATER_TILE_PART_HEADER = frozenset({0x58, 0x64})
_FIRST_TILE_PART_HEADER = _LATER_TILE_PART_HEADER | {_COD, _COC, _QCD, _QCC}
_START_OF_TILE_PART, _START_OF_DATA = b"\xff\x90", b"\xff\x93"
_END_OF_CODESTREAM = b"\xff\xd9"
_START_OF_PACKET, _END_OF_PACKET_HEADER = b"\xff\x91", b"\xff\x92"

# Scod: precinct sizes given, SOP marker segments, EPH markers.
_PRECINCTS, _SOP, _EPH = 0x01, 0x02, 0x04
# Code-block style: selective arithmetic coding bypass, termination on
# each coding pass, and, of T.814, HT code-blocks and mixed code-blocks.
_BYPASS, _TERMINATE_ALL, _HT, _HT_MIXED = 0x01, 0x04, 0x40, 0x80
_PART_2 = 0x8000
_LRCP, _RLCP, _RPCL, _PCRL, _CPRL = range(5)


class _Unreadable(Exception):
    """The packets cannot be read here."""


def coding_passes_kept(codestream: bytes) -> bool | None:
    """Return whether every code-block of a JPEG 2000 or HTJ2K codestream
    that its packets include holds every coding pass, as above, or ``None``
    where its packets cannot be read here.

    Parameters
    ----------
    codestream : bytes
        One frame, as :func:`pydicom.encaps.generate_frames` gives it.

    Returns
    -------
    bool or None
    """
    try:
        image = _image(codestream)
        return all(
            _tile_kept(image, tile, b"".join(bodies))
            for tile, bodies in enumerate(image.bodies)
        )
    except _Unreadable:
        return None


@dataclasses.dataclass(frozen=True)
class _Coding:
    """SPcod or SPcoc, with each resolution's precinct size exponents."""

    levels: int
    block_width: int
    block_height: int
    style: int
    precincts: tuple[tuple[int, int], ...]


@dataclasses.dataclass(frozen=True)
class _Quantisation:
    """Sqcd and SPqcd, or Sqcc and SPqcc: the guard bits, and each
    sub-band's exponent, or, for derived quantisation, the LL band's."""

    guard_bits: int
    exponents: tuple[int, ...]
    derived: bool


@dataclasses.dataclass(frozen=True)
class _Defaults:
    """What the main header, or a tile's first tile-part header over it,
    sets for coding and quantisation."""

    scod: int
    progression: int
    layers: int
    coding: _Coding
    quantisation: _Quantisation
    component_coding: dict[int, _Coding]
    component_quantisation: dict[int, _Quantisation]


@dataclasses.dataclass(frozen=True)
class _Image:
    """The SIZ marker segment, and each tile's headers and tile-part
    bodies."""

    reference: tuple[int, int, int, int]
    tiling: tuple[int, int, int, int]
    across: int
    components: int
    tiles: list[_Defaults]
    bodies: list[list[bytes]]


def _image(codestream: bytes) -> _Image:
    if codestream[:4] != b"\xff\x4f\xff\x51":
        raise _Unreadable
    # EOC ends the codestream, or comes before the byte that pads it to an
    # even length.
    end = len(codestream) - 2
    if codestream[end:] != _END_OF_CODESTREAM:
        end -= 1
        if codestream[end:] != _END_OF_CODESTREAM + b"\x00":
            raise _Unreadable
    size = _payload(codestream, 2, end)
    if len(size) < 38:
        raise _Unreadable
    rsiz, width, height, left, top, tile_width, tile_height, tile_left, tile_top = (
        struct.unpack_from(">H8I", size)
    )
    (components,) = struct.unpack_from(">H", size, 34)
    if rsiz & _PART_2 or not components or len(size) != 36 + 3 * components:
        raise _Unreadable
    # XRsiz and YRsiz: no component is subsampled.
    if any(size[37 + 3 * i : 39 + 3 * i] != b"\x01\x01" for i in range(components)):
        raise _Unreadable
    # The image area starts in the first tile (T.800 Section B.3).
    if not (tile_width and tile_height and tile_left <= left and tile_top <= top):
        raise _Unreadable
    if not (
        left < min(width, tile_left + tile_width)
        and top < min(height, tile_top + tile_height)
    ):
        raise _Unreadable
    across = -(-(width - tile_left) // tile_width)
    count = across * -(-(height - tile_top) // tile_height)
    # Isot numbers at most 65,535 tiles.
    if count > 65535:
        raise _Unreadable
    segments, position = _segments(codestream, 6 + len(size), end, _MAIN_HEADER)
    main = _defaults(segments, components, None)
    tiles: list[_Defaults | None] = [None] * count
    bodies: list[list[bytes]] = [[] for _ in range(count)]
    totals: list[set[int]] = [set() for _ in range(count)]
    while position < end:
        if codestream[position : position + 2] != _START_OF_TILE_PART:
            raise _Unreadable
        tile_part = _payload(codestream, position, end)
        if len(tile_part) != 8:
            raise _Unreadable
        tile, length, index, total = struct.unpack(">HIBB", tile_part)
        # Psot of 0: the last tile-part, which runs to EOC.
        stop = end if length == 0 else position + length
        if tile >= count or index != len(bodies[tile]) or stop > end:
            raise _Unreadable
        headers = _FIRST_TILE_PART_HEADER if index == 0 else _LATER_TILE_PART_HEADER
        segments, data = _segments(codestream, position + 12, stop, headers)
        if codestream[data : data + 2] != _START_OF_DATA:
            raise _Unreadable
        if index == 0:
            tiles[tile] = _defaults(segments, components, main)
        bodies[tile].append(codestream[data + 2 : stop])
        totals[tile] |= {total} - {0}
        position = stop
    complete = [
        defaults
        for defaults, tile_bodies, total in zip(tiles, bodies, totals)
        if defaults is not None and total <= {len(tile_bodies)}
    ]
    if len(complete) != count:
        raise _Unreadable
    return _Image(
        (left, top, width, height),
        (tile_left, tile_top, tile_width, tile_height),
        across,
        components,
        complete,
        bodies,
    )


def _segments(
    codestream: bytes, position: int, end: int, allowed: frozenset[int]
) -> tuple[list[tuple[int, bytes]], int]:
    """Return the marker and payload of each marker segment of a header
    from ``position``, and where the SOT or SOD marker that ends it is."""
    segments = []
    while True:
        if position + 2 > end or codestream[position] != 0xFF:
            raise _Unreadable
        marker = codestream[position : position + 2]
        if marker in (_START_OF_TILE_PART, _START_OF_DATA):
            return segments, position
        if marker[1] not in allowed:
            raise _Unreadable
        payload = _payload(codestream, position, end)
        segments.append((marker[1], payload))
        position += 4 + len(payload)


def _payload(codestream: bytes, position: int, end: int) -> bytes:
    """Return the payload of the marker segment at ``position``, after its
    marker and 16-bit length."""
    if position + 4 > end:
        raise _Unreadable
    (length,) = struct.unpack_from(">H", codestream, position + 2)
    if length < 2 or position + 2 + length > end:
        raise _Unreadable
    return codestream[position + 4 : position + 2 + length]


def _defaults(
    segments: list[tuple[int, bytes]], components: int, main: _Defaults | None
) -> _Defaults:
    """Return what a main header sets, or what a tile's first tile-part
    header sets over ``main``: its COD and QCD marker segments over the main
    header's and over its COC and QCC marker segments, and its own COC and
    QCC marker segments over all of them (T.800 Section A.6)."""
    by_marker: dict[int, list[bytes]] = {}
    for marker, payload in segments:
        by_marker.setdefault(marker, []).append(payload)
    cod, qcd = by_marker.get(_COD, []), by_marker.get(_QCD, [])
    if len(cod) > 1 or len(qcd) > 1 or (main is None and not (cod and qcd)):
        raise _Unreadable
    if cod:
        # Scod, then SGcod: the progression order, the layers, and the
        # multiple component transformation; then SPcod.
        payload = cod[0]
        if len(payload) < 5:
            raise _Unreadable
        scod, progression = payload[0], payload[1]
        (layers,) = struct.unpack_from(">H", payload, 2)
        if progression > _CPRL or not layers:
            raise _Unreadable
        coding = _coding(payload[5:], scod)
        component_coding: dict[int, _Coding] = {}
    else:
        assert main is not None
        scod, progression, layers = main.scod, main.progression, main.layers
        coding = main.coding
        component_coding = dict(main.component_coding)
    if qcd:
        quantisation = _quantisation(qcd[0])
        component_quantisation: dict[int, _Quantisation] = {}
    else:
        assert main is not None
        quantisation = main.quantisation
        component_quantisation = dict(main.component_quantisation)
    wide = components > 256
    for payloads, read, into in (
        (by_marker.get(_COC, []), _component_coding, component_coding),
        (by_marker.get(_QCC, []), _component_quantisation, component_quantisation),
    ):
        seen = set()
        for payload in payloads:
            component, value = read(payload, wide, components)
            if component in seen:
                raise _Unreadable
            seen.add(component)
            into[component] = value
    return _Defaults(
        scod,
        progression,
        layers,
        coding,
        quantisation,
        component_coding,
        component_quantisation,
    )


def _component(payload: bytes, wide: bool, components: int) -> tuple[int, bytes]:
    """Return a COC or QCC marker segment's component, of 1 byte, or 2
    where there are more than 256 components, and the rest of it."""
    width = 2 if wide else 1
    if len(payload) <= width:
        raise _Unreadable
    component = int.from_bytes(payload[:width], "big")
    if component >= components:
        raise _Unreadable
    return component, payload[width:]


def _component_coding(
    payload: bytes, wide: bool, components: int
) -> tuple[int, _Coding]:
    component, rest = _component(payload, wide, components)
    return component, _coding(rest[1:], rest[0])


def _component_quantisation(
    payload: bytes, wide: bool, components: int
) -> tuple[int, _Quantisation]:
    component, rest = _component(payload, wide, components)
    return component, _quantisation(rest)


def _coding(spcod: bytes, scod: int) -> _Coding:
    """Read SPcod or SPcoc: the decomposition levels, the code-block width
    and height exponents less 2, the code-block style, the transformation,
    and, where ``scod`` says, each resolution's precinct size exponents,
    15 by 15 otherwise."""
    if len(spcod) < 5:
        raise _Unreadable
    levels, width, height, style = spcod[0], spcod[1] + 2, spcod[2] + 2, spcod[3]
    sizes = spcod[5:] if scod & _PRECINCTS else bytes([0xFF] * (levels + 1))
    if levels > 32 or len(spcod) != 5 + (levels + 1 if scod & _PRECINCTS else 0):
        raise _Unreadable
    if max(width, height) > 10 or width + height > 12 or style & _HT_MIXED:
        raise _Unreadable
    precincts = tuple((size & 0x0F, size >> 4) for size in sizes)
    if any(0 in precinct for precinct in precincts[1:]):
        raise _Unreadable
    return _Coding(levels, width, height, style, precincts)


def _quantisation(payload: bytes) -> _Quantisation:
    if not payload:
        raise _Unreadable
    style, rest = payload[0] & 0x1F, payload[1:]
    if style == 0:
        exponents = tuple(byte >> 3 for byte in rest)
    elif style in (1, 2) and len(rest) % 2 == 0:
        exponents = tuple(value >> 11 for (value,) in struct.iter_unpack(">H", rest))
    else:
        raise _Unreadable
    if not exponents or (style == 1 and len(exponents) != 1):
        raise _Unreadable
    return _Quantisation(payload[0] >> 5, exponents, style == 1)


@dataclasses.dataclass(frozen=True)
class _Resolution:
    """One resolution level of one tile-component."""

    level: int
    bounds: tuple[int, int, int, int]
    precinct_size: tuple[int, int]
    precincts: tuple[int, int]
    # Each sub-band's bounds and magnitude bit-planes, M_b.
    bands: tuple[tuple[tuple[int, int, int, int], int], ...]
    block_size: tuple[int, int]


@dataclasses.dataclass(slots=True)
class _Block:
    """What the packet headers have said so far of one code-block."""

    magnitude_bit_planes: int
    included: bool = False
    zero_bit_planes: int = 0
    length_bits: int = 3
    passes: int = 0
    packets: int = 0
    # The coding passes in its last codeword segment, and at most how many
    # that segment holds.
    segment_passes: int = 0
    segment_limit: int = 0


@dataclasses.dataclass(frozen=True)
class _Precinct:
    """The code-blocks of one precinct, in the order that its packets give
    them, and each sub-band's inclusion and zero bit-plane tag trees."""

    bands: tuple[tuple[list[_Block], _TagTree, _TagTree], ...]


def _tile_kept(image: _Image, tile: int, body: bytes) -> bool:
    """Read every packet of one tile, and return whether every code-block
    that they include holds every coding pass."""
    defaults = image.tiles[tile]
    column, row = tile % image.across, tile // image.across
    left, top, width, height = image.reference
    tile_left, tile_top, tile_width, tile_height = image.tiling
    bounds = (
        max(tile_left + column * tile_width, left),
        max(tile_top + row * tile_height, top),
        min(tile_left + (column + 1) * tile_width, width),
        min(tile_top + (row + 1) * tile_height, height),
    )
    resolutions = [
        _resolutions(defaults, component, bounds)
        for component in range(image.components)
    ]
    styles = [
        defaults.component_coding.get(component, defaults.coding).style
        for component in range(image.components)
    ]
    # Each packet has a byte at least, so a tile with more packets than
    # bytes cannot hold together.
    if defaults.layers * sum(
        res.precincts[0] * res.precincts[1]
        for component in resolutions
        for res in component
    ) > len(body):
        raise _Unreadable
    precincts: dict[tuple[int, int, int], _Precinct] = {}
    position = 0
    for layer, resolution, component, index in _progression(
        defaults, resolutions, bounds
    ):
        key = (component, resolution, index)
        if layer == 0:
            precincts[key] = _precinct(resolutions[component][resolution], index)
        position = _packet(
            body, position, defaults.scod, styles[component], layer, precincts[key]
        )
    if position != len(body):
        raise _Unreadable
    return all(
        _block_kept(block, styles[component])
        for (component, _, _), precinct in precincts.items()
        for blocks, _, _ in precinct.bands
        for block in blocks
        if block.included
    )


def _block_kept(block: _Block, style: int) -> bool:
    if style & _HT:
        lowest = block.magnitude_bit_planes - 1 - block.zero_bit_planes
        if lowest < 0 or (block.passes == 3 and lowest == 0):
            raise _Unreadable
        return (block.passes, lowest) in ((1, 0), (3, 1))
    bit_planes = block.magnitude_bit_planes - block.zero_bit_planes
    if bit_planes < 1 or block.passes > 3 * bit_planes - 2:
        raise _Unreadable
    return block.passes == 3 * bit_planes - 2


def _resolutions(
    defaults: _Defaults, component: int, tile: tuple[int, int, int, int]
) -> list[_Resolution]:
    """Return each resolution level of one tile-component, and its
    sub-bands, as OpenJPEG's ``opj_tcd_init_tile`` sets them (T.800
    Sections B.5 and B.6)."""
    coding = defaults.component_coding.get(component, defaults.coding)
    quantisation = defaults.component_quantisation.get(component, defaults.quantisation)
    if not quantisation.derived and len(quantisation.exponents) < 3 * coding.levels + 1:
        raise _Unreadable
    x0, y0, x1, y1 = tile
    resolutions = []
    for resolution, precinct_size in enumerate(coding.precincts):
        level = coding.levels - resolution
        bounds = (
            _ceil_shift(x0, level),
            _ceil_shift(y0, level),
            _ceil_shift(x1, level),
            _ceil_shift(y1, level),
        )
        if resolution == 0:
            boxes = [(bounds, 0)]
        else:
            # HL, LH, and HH, each offset by half a sample of this level
            # where it is high-pass.
            boxes = [
                (
                    (
                        _ceil_shift(x0 - (high_x << level), level + 1),
                        _ceil_shift(y0 - (high_y << level), level + 1),
                        _ceil_shift(x1 - (high_x << level), level + 1),
                        _ceil_shift(y1 - (high_y << level), level + 1),
                    ),
                    3 * resolution - 3 + band,
                )
                for band, (high_x, high_y) in enumerate(((1, 0), (0, 1), (1, 1)), 1)
            ]
        bands = []
        for box, index in boxes:
            if quantisation.derived:
                exponent = max(quantisation.exponents[0] - max(resolution - 1, 0), 0)
            else:
                exponent = quantisation.exponents[index]
            bands.append((box, quantisation.guard_bits + exponent - 1))
        resolutions.append(
            _Resolution(
                level,
                bounds,
                precinct_size,
                (
                    _span(bounds[0], bounds[2], precinct_size[0]),
                    _span(bounds[1], bounds[3], precinct_size[1]),
                ),
                tuple(bands),
                (coding.block_width, coding.block_height),
            )
        )
    return resolutions


def _span(start: int, stop: int, exponent: int) -> int:
    """Return how many cells of size ``2 ** exponent``, anchored at 0, meet
    ``[start, stop)``, or 0 where it is empty."""
    return 0 if start == stop else _ceil_shift(stop, exponent) - (start >> exponent)


def _ceil_shift(value: int, shift: int) -> int:
    return -((-value) >> shift)


def _precinct(resolution: _Resolution, index: int) -> _Precinct:
    """Return the code-blocks of one precinct in each sub-band that is not
    empty, as OpenJPEG's ``opj_tcd_init_tile`` sets them (T.800 Section
    B.7)."""
    # Above the lowest resolution, a precinct's size in each sub-band is
    # half its size in the resolution.
    halved = 1 if len(resolution.bands) == 3 else 0
    x0, y0 = resolution.bounds[:2]
    width, height = resolution.precinct_size
    column, row = index % resolution.precincts[0], index // resolution.precincts[0]
    cell_x = _ceil_shift((x0 >> width) << width, halved) + (column << (width - halved))
    cell_y = _ceil_shift((y0 >> height) << height, halved) + (row << (height - halved))
    block_width = min(resolution.block_size[0], width - halved)
    block_height = min(resolution.block_size[1], height - halved)
    bands = []
    for (bx0, by0, bx1, by1), magnitude_bit_planes in resolution.bands:
        if bx0 == bx1 or by0 == by1:
            continue
        px0, py0 = max(cell_x, bx0), max(cell_y, by0)
        px1 = min(cell_x + (1 << (width - halved)), bx1)
        py1 = min(cell_y + (1 << (height - halved)), by1)
        across = max(_ceil_shift(px1, block_width) - (px0 >> block_width), 0)
        down = max(_ceil_shift(py1, block_height) - (py0 >> block_height), 0)
        bands.append(
            (
                [_Block(magnitude_bit_planes) for _ in range(across * down)],
                _TagTree(across, down),
                _TagTree(across, down),
            )
        )
    return _Precinct(tuple(bands))


def _progression(
    defaults: _Defaults,
    resolutions: list[list[_Resolution]],
    tile: tuple[int, int, int, int],
) -> Iterator[tuple[int, int, int, int]]:
    """Yield the layer, resolution, component, and precinct of each packet
    of a tile in its progression order (T.800 Section B.12), as OpenJPEG's
    ``opj_pi_next_*`` functions give them where no component is
    subsampled."""
    layers = range(defaults.layers)
    if defaults.progression in (_LRCP, _RLCP):
        most = max(len(component) for component in resolutions)
        pairs = itertools.product(layers, range(most))
        if defaults.progression == _RLCP:
            pairs = (
                (layer, resolution)
                for resolution, layer in itertools.product(range(most), layers)
            )
        for layer, resolution in pairs:
            for component, component_resolutions in enumerate(resolutions):
                if resolution < len(component_resolutions):
                    res = component_resolutions[resolution]
                    for index in range(res.precincts[0] * res.precincts[1]):
                        yield layer, resolution, component, index
        return
    # The position progressions visit each precinct at its top-left corner
    # on the reference grid, or at the tile's where that is outside it.
    order = []
    for component, component_resolutions in enumerate(resolutions):
        for resolution, res in enumerate(component_resolutions):
            across, down = res.precincts
            width, height = res.precinct_size
            for index in range(across * down):
                column, row = index % across, index // across
                x = max(
                    tile[0], ((res.bounds[0] >> width) + column) << (width + res.level)
                )
                y = max(
                    tile[1],
                    ((res.bounds[1] >> height) + row) << (height + res.level),
                )
                key = {
                    _RPCL: (resolution, y, x, component),
                    _PCRL: (y, x, component, resolution),
                    _CPRL: (component, y, x, resolution),
                }[defaults.progression]
                order.append((key, resolution, component, index))
    for _, resolution, component, index in sorted(order):
        for layer in layers:
            yield layer, resolution, component, index


class _TagTree:
    """A tag tree (T.800 Section B.10.2) over ``across`` by ``down`` leaves,
    decoded as OpenJPEG's ``opj_tgt_decode`` decodes it."""

    def __init__(self, across: int, down: int):
        levels = [(across, down)]
        while levels[-1][0] * levels[-1][1] > 1:
            w, h = levels[-1]
            levels.append((-(-w // 2), -(-h // 2)))
        starts = list(itertools.accumulate((w * h for w, h in levels), initial=0))
        # Each leaf's path from the root.
        self.paths = [
            [
                starts[level] + (y >> level) * levels[level][0] + (x >> level)
                for level in reversed(range(len(levels)))
            ]
            for y in range(down)
            for x in range(across)
        ]
        self.values = [1 << 30] * starts[-1]
        self.lows = [0] * starts[-1]

    def below(self, bits: _Bits, leaf: int, threshold: int) -> bool:
        """Return whether the leaf's value is less than ``threshold``,
        reading only the bits needed to tell."""
        low = 0
        for node in self.paths[leaf]:
            low = max(low, self.lows[node])
            while low < threshold and low < self.values[node]:
                if bits.bit():
                    self.values[node] = low
                else:
                    low += 1
            self.lows[node] = low
        return self.values[self.paths[leaf][-1]] < threshold


class _Bits:
    """Packet header bits, most significant first, with a 0 bit stuffed
    after each byte of 0xFF (T.800 Section B.10.1)."""

    def __init__(self, data: bytes, position: int):
        self.data = data
        self.position = position
        self.byte = 0
        self.left = 0

    def bit(self) -> int:
        if not self.left:
            if self.position >= len(self.data):
                raise _Unreadable
            stuffed = self.byte == 0xFF
            self.byte = self.data[self.position]
            self.position += 1
            self.left = 7 if stuffed else 8
            if stuffed and self.byte & 0x80:
                raise _Unreadable
        self.left -= 1
        return (self.byte >> self.left) & 1

    def bits(self, count: int) -> int:
        value = 0
        for _ in range(count):
            value = value << 1 | self.bit()
        return value

    def end(self) -> int:
        """Return where the packet header ends: after its last byte, and
        after the byte stuffed after it where that is 0xFF."""
        if self.byte == 0xFF:
            self.left = 0
            self.bit()
        return self.position


def _packet(
    body: bytes, position: int, scod: int, style: int, layer: int, precinct: _Precinct
) -> int:
    """Read the packet at ``position`` (T.800 Section B.10), add what its
    header says to the precinct's code-blocks, and return where the next
    packet starts."""
    if scod & _SOP and body[position : position + 2] == _START_OF_PACKET:
        if body[position + 2 : position + 4] != b"\x00\x04":
            raise _Unreadable
        position += 6
    bits = _Bits(body, position)
    lengths = 0
    if bits.bit():
        for blocks, inclusion, zero_bit_planes in precinct.bands:
            for leaf, block in enumerate(blocks):
                lengths += _contribution(
                    bits, block, leaf, layer, style, inclusion, zero_bit_planes
                )
    position = bits.end()
    if scod & _EPH:
        if body[position : position + 2] != _END_OF_PACKET_HEADER:
            raise _Unreadable
        position += 2
    position += lengths
    if position > len(body):
        raise _Unreadable
    return position


def _contribution(
    bits: _Bits,
    block: _Block,
    leaf: int,
    layer: int,
    style: int,
    inclusion: _TagTree,
    zero_bit_planes: _TagTree,
) -> int:
    """Read what a packet header says of one code-block, and return how
    many bytes of the packet body are its."""
    if block.included:
        if not bits.bit():
            return 0
    else:
        if not inclusion.below(bits, leaf, layer + 1):
            return 0
        planes = 0
        while not zero_bit_planes.below(bits, leaf, planes + 1):
            planes += 1
            if planes > block.magnitude_bit_planes:
                raise _Unreadable
        block.zero_bit_planes = planes
    passes = _passes(bits)
    while bits.bit():
        block.length_bits += 1
    first = not block.included
    block.included = True
    block.packets += 1
    block.passes += passes
    if style & _HT:
        # The HT cleanup pass in one codeword segment, and the significance
        # propagation and magnitude refinement passes in another (T.814).
        if block.packets > 1 or passes > 3:
            raise _Unreadable
        return sum(_length(bits, block, count) for count in (1, passes - 1) if count)
    if first or block.segment_passes == block.segment_limit:
        _new_segment(block, style, first)
    total = 0
    while passes:
        count = min(block.segment_limit - block.segment_passes, passes)
        total += _length(bits, block, count)
        block.segment_passes += count
        passes -= count
        if passes:
            _new_segment(block, style, False)
    return total


def _new_segment(block: _Block, style: int, first: bool) -> None:
    """Start a codeword segment, of as many passes as its style lets one
    hold, as OpenJPEG's ``opj_t2_init_seg`` does (T.800 Section D.4)."""
    if style & _TERMINATE_ALL:
        limit = 1
    elif style & _BYPASS:
        limit = 10 if first else 2 if block.segment_limit in (1, 10) else 1
    else:
        limit = 109
    block.segment_passes, block.segment_limit = 0, limit


def _length(bits: _Bits, block: _Block, passes: int) -> int:
    """Read the length of a codeword segment of ``passes`` coding passes
    (T.800 Section B.10.7)."""
    count = block.length_bits + passes.bit_length() - 1
    if count > 32:
        raise _Unreadable
    return bits.bits(count)


def _passes(bits: _Bits) -> int:
    """Read a number of coding passes (T.800 Table B.4)."""
    if not bits.bit():
        return 1
    if not bits.bit():
        return 2
    value = bits.bits(2)
    if value != 3:
        return 3 + value
    value = bits.bits(5)
    if value != 31:
        return 6 + value
    return 37 + bits.bits(7)
