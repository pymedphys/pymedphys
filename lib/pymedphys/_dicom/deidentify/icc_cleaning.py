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

"""Clean a source ICC profile, keeping only its colorimetry (D-021).

D on ICC Profile (0028,2000) writes the profile of :func:`clean_profile`
where the source can be cleaned. The cleaned profile keeps the source's
colorimetry: the tags that define how its device values map to the profile
connection space (PCS) and back, its white and black points, its chromatic
adaptation, and the tags that describe the colorimetry's measurement and
viewing conditions. Each kept tag is parsed against the structure that the
ICC specification gives its type and written again from the values parsed,
so no padding, reserved field, or trailing byte of the source survives.

Everything else is removed: every text tag, such as the description,
copyright, device manufacturer and model descriptions, viewing conditions
description, characterisation target, calibration date, and profile sequence
description, every private tag, every tag that the profile's version does not
define, and every other tag of the source, such as the technology signature
and the output profile's gamut and preview tags. The header names no
preferred CMM, platform, device manufacturer, model, attributes, or creator,
and takes the dummy date of 1 January 1900 (D-021); it keeps the source's
version, PCS, rendering intent, PCS illuminant, and the two profile flags
that ICC.1 defines, which say only whether the profile is embedded and
whether it may be used apart from the image. The written profile is an input
device profile, as PS3.3 Section C.11.15.1.1 requires, whose description and
copyright are the text given. A version 4 profile's profile ID is computed
again over the written bytes.

The source's colorimetric tags must be ones that its version defines, of a
type that the version defines for the tag. These are, for version 2
(ICC.1:2001-04), the matrix and tone curve tags, the media white and black
points, luminance, the 8-bit and 16-bit lookup tables of each rendering
intent in both directions, chromaticity, measurement, and viewing
conditions; and, for version 4 (ICC.1:2010 and ICC.1:2022), the same without
the media black point, which version 4 removed, with parametric curves and
the A-to-B and B-to-A lookup tables, the floating-point multiProcessElements
transforms (``D2B0`` to ``D2B3`` and ``B2D0`` to ``B2D3``), chromatic
adaptation, coding-independent code points, the colorimetric intent image
state, and the perceptual and saturation rendering intent gamuts.

A profile is cleaned only where every byte that it keeps can be accounted
for. :class:`UncleanableProfileError` is raised, with a :class:`Refusal`,
where the source is of another version or device class, has another PCS or a
PCS illuminant that is not D50, has an undefined rendering intent, has a
header, tag table, or tag whose bounds do not parse, holds a tag twice,
holds a colorimetric tag of a type that its version does not define for it,
or one whose data do not parse, or lacks the media white point or a complete
device-to-PCS transform. A tag that only describes the colorimetry
(chromaticity, measurement, viewing conditions, the colorimetric intent
image state, and the rendering intent gamuts) and whose data do not parse is
removed instead, since no transform reads it.

The cleaner reads only the profile given, and needs nothing beyond the
standard library.
"""

from __future__ import annotations

import enum
import math
import struct
from collections.abc import Callable, Mapping

from . import icc_profiles

_HEADER_LENGTH = 128
_TABLE_START = _HEADER_LENGTH + 4
_TAG_ENTRY_LENGTH = 12
_RESERVED = b"\0" * 4
# The device classes whose profiles define a transform from RGB device
# values to the PCS: input device, display device, and colour space.
_DEVICE_CLASSES = frozenset({b"scnr", b"mntr", b"spac"})
_CONNECTION_SPACES = frozenset({b"XYZ ", b"Lab "})
# D50, as the ICC specification encodes it, and the largest difference of
# any component from it that a header's PCS illuminant may have.
_D50 = (0.9642, 1.0, 0.8249)
_ILLUMINANT_TOLERANCE = 0.001
# The rendering intents that ICC.1 defines: perceptual, media-relative
# colorimetric, saturation, and ICC-absolute colorimetric.
_RENDERING_INTENTS = range(4)
# The profile flags that ICC.1 defines: embedded, and not to be used
# independently of the embedded colour data. The other bits are reserved or
# for vendors.
_DEFINED_FLAGS = 0b11
# The number of channels in RGB device space and in either PCS.
_CHANNELS = 3
# The number of parameters of each parametricCurveType function type.
_PARAMETRIC_PARAMETERS = {0: 1, 1: 3, 2: 4, 3: 5, 4: 7}
# The number of parameters of each formulaCurveSegment function type.
_FORMULA_PARAMETERS = {0: 4, 1: 5, 2: 5}
# The registered signatures of the colorimetric intent image state tag and
# of the rendering intent gamut tags.
_IMAGE_STATES = frozenset({b"scoe", b"sape", b"fpce", b"rhoc", b"rpoc"})
_GAMUTS = frozenset({b"prmg"})
# The number of entries that a lut16Type's input and output tables may hold.
_LUT16_ENTRIES = range(2, 4097)


class Refusal(enum.Enum):
    """Why a source profile cannot be cleaned."""

    STRUCTURE = "structure"
    """The header, tag table, or a tag's bounds do not parse, or a tag is held twice."""

    VERSION = "version"
    """The profile is not of ICC version 2 or 4."""

    DEVICE_CLASS = "device-class"
    """The profile is not an input device, display device, or colour space profile."""

    CONNECTION_SPACE = "connection-space"
    """The PCS is not CIEXYZ or CIELAB."""

    HEADER = "header"
    """The PCS illuminant is not D50, or the rendering intent is undefined."""

    TAG_TYPE = "tag-type"
    """A colorimetric tag is of a type that the profile's version does not define for it."""

    TAG_DATA = "tag-data"
    """A colorimetric tag's data do not parse."""

    NO_WHITE_POINT = "no-white-point"
    """The profile has no media white point."""

    NO_TRANSFORM = "no-transform"
    """The profile has no complete transform from device values to the PCS."""


class UncleanableProfileError(ValueError):
    """A source ICC profile cannot be cleaned.

    The message names the reason, never any of the profile's contents.

    Attributes
    ----------
    refusal : Refusal
        Why the profile cannot be cleaned.
    """

    def __init__(self, refusal: Refusal):
        super().__init__(f"the ICC profile cannot be cleaned: {refusal.value}")
        self.refusal = refusal


class _MalformedError(Exception):
    """A structure's data do not parse."""


class _Data:
    """Bounds-checked big-endian reads from one tag's data."""

    def __init__(self, data: bytes):
        self.data = data

    def take(self, start: int, length: int) -> bytes:
        if start < 0 or length < 0 or start + length > len(self.data):
            raise _MalformedError
        return self.data[start : start + length]

    def u8(self, start: int) -> int:
        return self.take(start, 1)[0]

    def u16(self, start: int) -> int:
        return int.from_bytes(self.take(start, 2), "big")

    def u32(self, start: int) -> int:
        return int.from_bytes(self.take(start, 4), "big")

    def floats(self, start: int, count: int) -> bytes:
        """Return ``count`` float32 values' bytes, each of a finite number."""
        values = self.take(start, 4 * count)
        if not all(
            math.isfinite(value) for (value,) in struct.iter_unpack(">f", values)
        ):
            raise _MalformedError
        return values


def clean_profile(source: bytes, text: str) -> bytes:
    """Return a source RGB profile with only its colorimetry kept.

    Parameters
    ----------
    source : bytes
        The source profile, an RGB profile, as
        :func:`~pymedphys._dicom.deidentify.icc_profiles.data_colour_space`
        reads it. A trailing zero byte past the profile's size, which pads an
        OB value of odd length (PS3.5 Section 6.2), is ignored.
    text : str
        The ASCII text of the written profile's description and copyright.

    Returns
    -------
    bytes
        The cleaned profile, of a length that is a multiple of four.

    Raises
    ------
    UncleanableProfileError
        If the source cannot be cleaned, with the reason.
    ValueError
        If the source is not an RGB profile.

    Examples
    --------
    >>> source = icc_profiles.srgb_profile("A scanner's profile")
    >>> cleaned = clean_profile(source, "DEIDENTIFIED")
    >>> b"scanner" in cleaned
    False
    >>> len(cleaned) == int.from_bytes(cleaned[:4], "big")
    True
    """
    if icc_profiles.data_colour_space(source) != icc_profiles.RGB:
        raise ValueError("the source is not an RGB ICC profile")
    profile = _sized(bytes(source))
    header = _header(profile)
    allowed = _V2_TAGS if header.version[0] == 2 else _V4_TAGS
    kept: dict[bytes, bytes] = {}
    for signature, data in _tag_data(profile).items():
        kind = allowed.get(signature)
        if kind is None:
            continue
        normalise = kind.types.get(data[:4])
        if normalise is None:
            if kind.transform:
                raise UncleanableProfileError(Refusal.TAG_TYPE)
            continue
        try:
            kept[signature] = normalise(_Data(data))
        except _MalformedError:
            if kind.transform:
                raise UncleanableProfileError(Refusal.TAG_DATA) from None
    if b"wtpt" not in kept:
        raise UncleanableProfileError(Refusal.NO_WHITE_POINT)
    matrix_and_curves = header.connection_space == b"XYZ " and _MATRIX_TAGS <= set(kept)
    if b"A2B0" not in kept and not matrix_and_curves:
        raise UncleanableProfileError(Refusal.NO_TRANSFORM)
    tags = [*_text_tags(header.version[0], text)]
    tags += [(signature, kept[signature]) for signature in allowed if signature in kept]
    return icc_profiles.assemble(header, tags)


def _sized(profile: bytes) -> bytes:
    """Return the profile's bytes up to its size, refusing any other length."""
    if len(profile) < _TABLE_START:
        raise UncleanableProfileError(Refusal.STRUCTURE)
    size = int.from_bytes(profile[:4], "big")
    padded = len(profile) == size + 1 and profile[-1] == 0
    if size < _TABLE_START or not (len(profile) == size or padded):
        raise UncleanableProfileError(Refusal.STRUCTURE)
    return profile[:size]


def _header(profile: bytes) -> icc_profiles.Header:
    """Return the header fields that the cleaned profile keeps."""
    major = profile[8]
    if major not in (2, 4):
        raise UncleanableProfileError(Refusal.VERSION)
    if profile[12:16] not in _DEVICE_CLASSES:
        raise UncleanableProfileError(Refusal.DEVICE_CLASS)
    connection_space = profile[20:24]
    if connection_space not in _CONNECTION_SPACES:
        raise UncleanableProfileError(Refusal.CONNECTION_SPACE)
    (intent,) = struct.unpack_from(">I", profile, 64)
    illuminant = struct.unpack_from(">3i", profile, 68)
    near_d50 = all(
        abs(value / 65536 - expected) <= _ILLUMINANT_TOLERANCE
        for value, expected in zip(illuminant, _D50)
    )
    if intent not in _RENDERING_INTENTS or not near_d50:
        raise UncleanableProfileError(Refusal.HEADER)
    (flags,) = struct.unpack_from(">I", profile, 44)
    return icc_profiles.Header(
        # The major version, and the minor version and bug-fix level, which
        # share a byte; the last two bytes are reserved.
        version=bytes([major, profile[9], 0, 0]),
        connection_space=connection_space,
        rendering_intent=intent,
        illuminant=struct.unpack_from(">3I", profile, 68),
        flags=flags & _DEFINED_FLAGS,
    )


def _tag_data(profile: bytes) -> dict[bytes, bytes]:
    """Return each tag's signature with its data, in the tag table's order."""
    (count,) = struct.unpack_from(">I", profile, _HEADER_LENGTH)
    table_end = _TABLE_START + _TAG_ENTRY_LENGTH * count
    if table_end > len(profile):
        raise UncleanableProfileError(Refusal.STRUCTURE)
    tags: dict[bytes, bytes] = {}
    for index in range(count):
        signature, offset, size = struct.unpack_from(
            ">4sII", profile, _TABLE_START + _TAG_ENTRY_LENGTH * index
        )
        if signature in tags or offset < table_end or offset + size > len(profile):
            raise UncleanableProfileError(Refusal.STRUCTURE)
        tags[signature] = profile[offset : offset + size]
    return tags


def _text_tags(major: int, text: str) -> list[tuple[bytes, bytes]]:
    """Return the description and copyright tags, of the types their version defines."""
    if major == 2:
        return [
            (b"desc", icc_profiles.text_description(text)),
            (b"cprt", icc_profiles.text_type(text)),
        ]
    return [(b"desc", _localised(text)), (b"cprt", _localised(text))]


def _localised(text: str) -> bytes:
    """Return a multiLocalizedUnicodeType holding ``text`` in English (US)."""
    text.encode("ascii")
    encoded = text.encode("utf-16-be")
    record_offset = 16 + 12
    return (
        b"mluc"
        + _RESERVED
        + struct.pack(">II", 1, 12)
        + b"enUS"
        + struct.pack(">II", len(encoded), record_offset)
        + encoded
    )


# Normalisers of the tag types: each reads one structure from a tag's data
# and returns it written again, with zero in its reserved fields and nothing
# after it.


def _xyz(data: _Data) -> bytes:
    """Return the first XYZNumber of an XYZType."""
    return b"XYZ " + _RESERVED + data.take(8, 12)


def _s15_fixed16_array(data: _Data) -> bytes:
    """Return the nine values of a chromatic adaptation matrix's s15Fixed16ArrayType."""
    return b"sf32" + _RESERVED + data.take(8, 36)


def _curve_at(data: _Data, start: int, parametric: bool) -> tuple[bytes, int]:
    """Return a curveType or parametricCurveType at ``start``, and where it ends."""
    signature = data.take(start, 4)
    if signature == b"curv":
        count = data.u32(start + 8)
        entries = data.take(start + 12, 2 * count)
        return b"curv" + _RESERVED + struct.pack(">I", count) + entries, start + 12 + (
            2 * count
        )
    if signature == b"para" and parametric:
        function = data.u16(start + 8)
        if function not in _PARAMETRIC_PARAMETERS:
            raise _MalformedError
        length = 4 * _PARAMETRIC_PARAMETERS[function]
        parameters = data.take(start + 12, length)
        written = b"para" + _RESERVED + struct.pack(">HH", function, 0) + parameters
        return written, start + 12 + length
    raise _MalformedError


def _curve(data: _Data) -> bytes:
    return _curve_at(data, 0, parametric=False)[0]


def _curve_or_parametric(data: _Data) -> bytes:
    return _curve_at(data, 0, parametric=True)[0]


def _channels(data: _Data) -> None:
    """Check that a transform maps three channels to three."""
    if data.u8(8) != _CHANNELS or data.u8(9) != _CHANNELS:
        raise _MalformedError


def _lut8(data: _Data) -> bytes:
    """Return an 8-bit lookup table, lut8Type."""
    _channels(data)
    grid = data.u8(10)
    if grid == 1:
        raise _MalformedError
    tables = 256 * _CHANNELS + grid**_CHANNELS * _CHANNELS + 256 * _CHANNELS
    return (
        b"mft1"
        + _RESERVED
        + bytes([_CHANNELS, _CHANNELS, grid, 0])
        + data.take(12, 36)
        + data.take(48, tables)
    )


def _lut16(data: _Data) -> bytes:
    """Return a 16-bit lookup table, lut16Type."""
    _channels(data)
    grid = data.u8(10)
    inputs, outputs = data.u16(48), data.u16(50)
    if grid == 1 or inputs not in _LUT16_ENTRIES or outputs not in _LUT16_ENTRIES:
        raise _MalformedError
    entries = (inputs + grid**_CHANNELS + outputs) * _CHANNELS
    return (
        b"mft2"
        + _RESERVED
        + bytes([_CHANNELS, _CHANNELS, grid, 0])
        + data.take(12, 36)
        + struct.pack(">HH", inputs, outputs)
        + data.take(52, 2 * entries)
    )


# The elements of lutAtoBType and lutBtoAType, in the order of their offsets
# in the type's header, and the combinations that ICC.1 allows.
_ELEMENTS = ("B", "matrix", "M", "CLUT", "A")
_COMBINATIONS = frozenset(
    {
        frozenset({"B"}),
        frozenset({"B", "matrix", "M"}),
        frozenset({"B", "CLUT", "A"}),
        frozenset(_ELEMENTS),
    }
)


def _curves(data: _Data, start: int) -> bytes:
    """Return the three curves stored from ``start``, each on a four-byte boundary."""
    written = b""
    for _ in range(_CHANNELS):
        curve, end = _curve_at(data, start, parametric=True)
        written += curve + b"\0" * (-len(curve) % 4)
        start = end + (-end % 4)
    return written


def _grid_table(data: _Data, start: int) -> bytes:
    """Return the CLUT of a lutAtoBType or lutBtoAType, padded to four bytes."""
    points = data.take(start, 16)
    if any(count < 2 for count in points[:_CHANNELS]):
        raise _MalformedError
    precision = data.u8(start + 16)
    if precision not in (1, 2):
        raise _MalformedError
    entries = math.prod(points[:_CHANNELS]) * _CHANNELS * precision
    written = (
        points[:_CHANNELS]
        + bytes(16 - _CHANNELS)
        + bytes([precision, 0, 0, 0])
        + data.take(start + 20, entries)
    )
    return written + b"\0" * (-len(written) % 4)


def _lut_ab(data: _Data) -> bytes:
    """Return a lutAtoBType or lutBtoAType.

    Both types hold the same elements at offsets in the same order; with
    three channels in and out, each set of curves holds three curves.
    """
    _channels(data)
    offsets = dict(zip(_ELEMENTS, struct.unpack(">5I", data.take(12, 20))))
    present = frozenset(name for name, offset in offsets.items() if offset)
    if present not in _COMBINATIONS:
        raise _MalformedError
    read: dict[str, Callable[[int], bytes]] = {
        "B": lambda start: _curves(data, start),
        "matrix": lambda start: data.take(start, 48),
        "M": lambda start: _curves(data, start),
        "CLUT": lambda start: _grid_table(data, start),
        "A": lambda start: _curves(data, start),
    }
    body = b""
    written_offsets = []
    for name in _ELEMENTS:
        if name not in present:
            written_offsets.append(0)
            continue
        written_offsets.append(32 + len(body))
        body += read[name](offsets[name])
    signature = data.take(0, 4)
    return (
        signature
        + _RESERVED
        + bytes([_CHANNELS, _CHANNELS, 0, 0])
        + struct.pack(">5I", *written_offsets)
        + body
    )


def _segment_at(data: _Data, start: int) -> tuple[bytes, int]:
    """Return a formulaCurveSegment or sampledCurveSegment, and where it ends."""
    signature = data.take(start, 4)
    if signature == b"parf":
        function = data.u16(start + 8)
        if function not in _FORMULA_PARAMETERS:
            raise _MalformedError
        count = _FORMULA_PARAMETERS[function]
        values = data.floats(start + 12, count)
        written = b"parf" + _RESERVED + struct.pack(">HH", function, 0) + values
        return written, start + 12 + 4 * count
    if signature == b"samf":
        count = data.u32(start + 8)
        if count < 1:
            raise _MalformedError
        values = data.floats(start + 12, count)
        return b"samf" + _RESERVED + struct.pack(">I", count) + values, start + 12 + (
            4 * count
        )
    raise _MalformedError


def _segmented_curve(data: _Data) -> bytes:
    """Return a segmentedCurve, of its segments and their break points."""
    if data.take(0, 4) != b"curf":
        raise _MalformedError
    segments = data.u16(8)
    if segments < 1:
        raise _MalformedError
    breaks = data.floats(12, segments - 1)
    written = b"curf" + _RESERVED + struct.pack(">HH", segments, 0) + breaks
    start = 12 + 4 * (segments - 1)
    for _ in range(segments):
        segment, start = _segment_at(data, start)
        written += segment
    return written


def _positioned(data: _Data, start: int, count: int) -> list[_Data]:
    """Return the structures that a position table at ``start`` places."""
    placed = []
    for index in range(count):
        offset = data.u32(start + 8 * index)
        size = data.u32(start + 8 * index + 4)
        placed.append(_Data(data.take(offset, size)))
    return placed


def _position_table(header: bytes, elements: list[bytes]) -> bytes:
    """Return ``header``, a position table, and ``elements``, each on a four-byte boundary."""
    offset = len(header) + 8 * len(elements)
    table = b""
    body = b""
    for element in elements:
        table += struct.pack(">II", offset + len(body), len(element))
        body += element + b"\0" * (-len(element) % 4)
    return header + table + body


def _curve_set_element(data: _Data) -> tuple[bytes, int, int]:
    """Return a curveSetElement, with its numbers of input and output channels."""
    channels = data.u16(8)
    if data.u16(10) != channels:
        raise _MalformedError
    curves = [_segmented_curve(curve) for curve in _positioned(data, 12, channels)]
    header = b"cvst" + _RESERVED + struct.pack(">HH", channels, channels)
    return _position_table(header, curves), channels, channels


def _matrix_element(data: _Data) -> tuple[bytes, int, int]:
    """Return a matrixElement, with its numbers of input and output channels."""
    inputs, outputs = data.u16(8), data.u16(10)
    values = data.floats(12, inputs * outputs + outputs)
    written = b"matf" + _RESERVED + struct.pack(">HH", inputs, outputs) + values
    return written, inputs, outputs


def _clut_element(data: _Data) -> tuple[bytes, int, int]:
    """Return a CLutElement, with its numbers of input and output channels."""
    inputs, outputs = data.u16(8), data.u16(10)
    points = data.take(12, 16)
    if not 1 <= inputs <= 16 or outputs < 1 or any(n < 2 for n in points[:inputs]):
        raise _MalformedError
    values = data.floats(28, math.prod(points[:inputs]) * outputs)
    written = (
        b"clut"
        + _RESERVED
        + struct.pack(">HH", inputs, outputs)
        + points[:inputs]
        + bytes(16 - inputs)
        + values
    )
    return written, inputs, outputs


# The processing elements that ICC.1 defines with a transform. The bACS and
# eACS elements, which it reserves for colour appearance spaces, are not
# among them, so a profile holding one is not cleaned.
_PROCESSING_ELEMENTS: Mapping[bytes, Callable[[_Data], tuple[bytes, int, int]]] = {
    b"cvst": _curve_set_element,
    b"matf": _matrix_element,
    b"clut": _clut_element,
}


def _multi_process_elements(data: _Data) -> bytes:
    """Return a multiProcessElementsType, whose elements chain three channels to three."""
    if data.u16(8) != _CHANNELS or data.u16(10) != _CHANNELS:
        raise _MalformedError
    count = data.u32(12)
    if count < 1:
        raise _MalformedError
    channels = _CHANNELS
    elements = []
    for element in _positioned(data, 16, count):
        read = _PROCESSING_ELEMENTS.get(element.take(0, 4))
        if read is None:
            raise _MalformedError
        written, inputs, outputs = read(element)
        if inputs != channels:
            raise _MalformedError
        channels = outputs
        elements.append(written)
    if channels != _CHANNELS:
        raise _MalformedError
    header = b"mpet" + _RESERVED + struct.pack(">HHI", _CHANNELS, _CHANNELS, count)
    return _position_table(header, elements)


def _chromaticity(data: _Data) -> bytes:
    """Return a chromaticityType of three channels."""
    if data.u16(8) != _CHANNELS:
        raise _MalformedError
    colorants = data.u16(10)
    return (
        b"chrm"
        + _RESERVED
        + struct.pack(">HH", _CHANNELS, colorants)
        + data.take(12, 8 * _CHANNELS)
    )


def _code_points(data: _Data) -> bytes:
    """Return a cicpType's colour primaries, transfer, matrix, and range."""
    return b"cicp" + _RESERVED + data.take(8, 4)


def _measurement(data: _Data) -> bytes:
    """Return a measurementType's observer, backing, geometry, flare, and illuminant."""
    return b"meas" + _RESERVED + data.take(8, 28)


def _viewing_conditions(data: _Data) -> bytes:
    """Return a viewingConditionsType's illuminant, surround, and illuminant type."""
    return b"view" + _RESERVED + data.take(8, 28)


def _signature(registered: frozenset[bytes]) -> Callable[[_Data], bytes]:
    def normalise(data: _Data) -> bytes:
        value = data.take(8, 4)
        if value not in registered:
            raise _MalformedError
        return b"sig " + _RESERVED + value

    return normalise


class _Kind:
    """A colorimetric tag's types, each with its normaliser.

    A transform tag is one that a colour management module reads to convert
    colours; a profile whose transform tag cannot be cleaned is refused,
    while a descriptive tag that cannot be cleaned is removed.
    """

    def __init__(
        self, types: Mapping[bytes, Callable[[_Data], bytes]], transform: bool = True
    ):
        self.types = types
        self.transform = transform


_XYZ = _Kind({b"XYZ ": _xyz})
_V2_CURVE = _Kind({b"curv": _curve})
_V4_CURVE = _Kind({b"curv": _curve_or_parametric, b"para": _curve_or_parametric})
_V2_LUT = _Kind({b"mft1": _lut8, b"mft2": _lut16})
_V4_A2B = _Kind({b"mft1": _lut8, b"mft2": _lut16, b"mAB ": _lut_ab})
_V4_B2A = _Kind({b"mft1": _lut8, b"mft2": _lut16, b"mBA ": _lut_ab})
_MULTI_PROCESS = _Kind({b"mpet": _multi_process_elements})
_DESCRIPTIVE = {
    b"chrm": _Kind({b"chrm": _chromaticity}, transform=False),
    b"meas": _Kind({b"meas": _measurement}, transform=False),
    b"view": _Kind({b"view": _viewing_conditions}, transform=False),
}
_MATRIX_TAGS = frozenset({b"rXYZ", b"gXYZ", b"bXYZ", b"rTRC", b"gTRC", b"bTRC"})

# The colorimetric tags of each version, in the order the cleaned profile
# writes them, after its description and copyright.
_V2_TAGS: Mapping[bytes, _Kind] = {
    b"wtpt": _XYZ,
    b"bkpt": _XYZ,
    b"lumi": _XYZ,
    b"rXYZ": _XYZ,
    b"gXYZ": _XYZ,
    b"bXYZ": _XYZ,
    b"rTRC": _V2_CURVE,
    b"gTRC": _V2_CURVE,
    b"bTRC": _V2_CURVE,
    b"A2B0": _V2_LUT,
    b"A2B1": _V2_LUT,
    b"A2B2": _V2_LUT,
    b"B2A0": _V2_LUT,
    b"B2A1": _V2_LUT,
    b"B2A2": _V2_LUT,
    **_DESCRIPTIVE,
}
_V4_TAGS: Mapping[bytes, _Kind] = {
    b"wtpt": _XYZ,
    b"lumi": _XYZ,
    b"chad": _Kind({b"sf32": _s15_fixed16_array}),
    b"rXYZ": _XYZ,
    b"gXYZ": _XYZ,
    b"bXYZ": _XYZ,
    b"rTRC": _V4_CURVE,
    b"gTRC": _V4_CURVE,
    b"bTRC": _V4_CURVE,
    b"A2B0": _V4_A2B,
    b"A2B1": _V4_A2B,
    b"A2B2": _V4_A2B,
    b"B2A0": _V4_B2A,
    b"B2A1": _V4_B2A,
    b"B2A2": _V4_B2A,
    b"D2B0": _MULTI_PROCESS,
    b"D2B1": _MULTI_PROCESS,
    b"D2B2": _MULTI_PROCESS,
    b"D2B3": _MULTI_PROCESS,
    b"B2D0": _MULTI_PROCESS,
    b"B2D1": _MULTI_PROCESS,
    b"B2D2": _MULTI_PROCESS,
    b"B2D3": _MULTI_PROCESS,
    b"cicp": _Kind({b"cicp": _code_points}),
    **_DESCRIPTIVE,
    b"ciis": _Kind({b"sig ": _signature(_IMAGE_STATES)}, transform=False),
    b"rig0": _Kind({b"sig ": _signature(_GAMUTS)}, transform=False),
    b"rig2": _Kind({b"sig ": _signature(_GAMUTS)}, transform=False),
}
