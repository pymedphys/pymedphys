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

"""The ICC profiles that D writes in place of ICC Profile (0028,2000) (D-021).

PS3.3 Section C.11.15.1.1 makes ICC Profile an ICC Input Device Profile whose
input colour space is RGB, whatever the image's Photometric Interpretation,
with a PCS of CIEXYZ or CIELab. Where D replaces one, it writes the source
cleaned of everything but its colorimetry
(:mod:`~pymedphys._dicom.deidentify.icc_cleaning`), which :func:`assemble`
writes, or, where the source cannot be cleaned, the fixed profile of
:func:`srgb_profile`, the sRGB colour space of IEC 61966-2.1, built here the
same way every time. The fixed profile is an ICC version 2.4 input profile
(ICC.1:2001-04) of the matrix and tone curve model (Section 6.3.1.2), whose
PCS is CIE XYZ under the D50 illuminant and whose media white point is D50.
Nothing of the source profile is written to it.

:func:`data_colour_space` reads only a profile's file signature and data
colour space, which must be RGB for the profile to be replaced.
"""

from __future__ import annotations

import dataclasses
import hashlib
import struct

_HEADER_LENGTH = 128
# The profile file signature, at bytes 36 to 39 of the header.
_SIGNATURE = b"acsp"
RGB = b"RGB "
# s15Fixed16Number encodings, as the sRGB profiles of IEC 61966-2.1 give
# them: the D50 illuminant, and the red, green, and blue colorants adapted to
# it, whose sum is the D50 white point to within 0.0002.
_D50 = (0x0000F6D6, 0x00010000, 0x0000D32D)
_COLORANTS = (
    (b"rXYZ", (0x00006FA2, 0x000038F5, 0x00000390)),
    (b"gXYZ", (0x00006299, 0x0000B785, 0x000018DA)),
    (b"bXYZ", (0x000024A0, 0x00000F84, 0x0000B6CF)),
)
_CURVE_ENTRIES = 1024
_COPYRIGHT = "No copyright, use freely"
# The date of creation in the header: 1 January 1900, as the dummy dates of
# D-021 are.
CREATED = (1900, 1, 1, 0, 0, 0)


def data_colour_space(profile: bytes) -> bytes | None:
    """Return a profile's data colour space signature, or None if not a profile.

    Only the header's file signature and data colour space field are read.

    Examples
    --------
    >>> data_colour_space(srgb_profile("DEIDENTIFIED sRGB"))
    b'RGB '
    >>> data_colour_space(b"not a profile") is None
    True
    """
    if len(profile) < _HEADER_LENGTH or profile[36:40] != _SIGNATURE:
        return None
    return bytes(profile[16:20])


def srgb_profile(description: str) -> bytes:
    """Return an sRGB input profile, with ``description`` as its description.

    Examples
    --------
    >>> profile = srgb_profile("DEIDENTIFIED sRGB")
    >>> len(profile) == int.from_bytes(profile[:4], "big")
    True
    """
    return assemble(SRGB_HEADER, srgb_tags(description))


def srgb_tags(description: str) -> list[tuple[bytes, bytes]]:
    """Return the tags of :func:`srgb_profile`, each signature with its data.

    Examples
    --------
    >>> [signature for signature, _ in srgb_tags("DEIDENTIFIED sRGB")][:3]
    [b'desc', b'cprt', b'wtpt']
    """
    curve = _curve()
    return [
        (b"desc", text_description(description)),
        (b"cprt", text_type(_COPYRIGHT)),
        (b"wtpt", _xyz(_D50)),
        *((signature, _xyz(values)) for signature, values in _COLORANTS),
        (b"rTRC", curve),
        (b"gTRC", curve),
        (b"bTRC", curve),
    ]


@dataclasses.dataclass(frozen=True)
class Header:
    """The header fields that a written profile takes from its maker.

    Every other header field is fixed: no preferred CMM, platform, device
    manufacturer, model, attributes, or creator, an input device profile of
    the RGB data colour space, :data:`CREATED` as its date, and zero in the
    reserved bytes.

    Attributes
    ----------
    version : bytes
        The profile's version, as the header's four bytes give it.
    connection_space : bytes
        The profile connection space's signature, ``XYZ `` or ``Lab ``.
    rendering_intent : int
        The rendering intent, from 0 to 3.
    illuminant : tuple of int
        The profile connection space's illuminant, as three s15Fixed16Number
        encodings.
    flags : int
        The profile flags.
    """

    version: bytes
    connection_space: bytes = b"XYZ "
    rendering_intent: int = 0
    illuminant: tuple[int, int, int] = _D50
    flags: int = 0


# The header of the fixed sRGB profile: version 2.4, perceptual.
SRGB_HEADER = Header(version=bytes([2, 0x40, 0, 0]))


def assemble(header: Header, tags: list[tuple[bytes, bytes]]) -> bytes:
    """Return a profile's bytes: its header, tag table, and tag data.

    Tags with the same data share it, as the three tone curves of a matrix and
    tone curve profile usually do, and each tag's data starts on a four-byte
    boundary, padded with zero bytes. In a version 4 profile, the header's
    profile ID is the MD5 digest of the profile that ICC.1:2022 Section 7.2.18
    defines, computed with the profile flags, rendering intent, and profile ID
    fields set to zero; in a version 2 profile, those bytes are reserved and
    zero.

    Examples
    --------
    >>> profile = assemble(Header(version=bytes([4, 0x30, 0, 0])), [])
    >>> len(profile) == int.from_bytes(profile[:4], "big") == 132
    True
    """
    table_length = 4 + 12 * len(tags)
    offset = _HEADER_LENGTH + table_length
    data = b""
    entries = []
    placed: dict[bytes, int] = {}
    for signature, element in tags:
        if element not in placed:
            placed[element] = offset + len(data)
            data += element + b"\0" * (-len(element) % 4)
        entries.append(struct.pack(">4sII", signature, placed[element], len(element)))
    table = struct.pack(">I", len(tags)) + b"".join(entries)
    size = _HEADER_LENGTH + len(table) + len(data)

    def header_bytes(flags: int, intent: int, profile_id: bytes) -> bytes:
        return (
            struct.pack(">I", size)
            + b"\0" * 4  # preferred CMM: none
            + header.version
            + b"scnr"  # an input device profile
            + RGB
            + header.connection_space
            + struct.pack(">6H", *CREATED)
            + _SIGNATURE
            + b"\0" * 4  # primary platform: none
            + struct.pack(">I", flags)
            + b"\0" * 8  # device manufacturer and model: none
            + b"\0" * 8  # device attributes
            + struct.pack(">I", intent)
            + struct.pack(">3I", *header.illuminant)
            + b"\0" * 4  # profile creator: none
            + profile_id
            + b"\0" * 28  # reserved
        )

    profile_id = bytes(16)
    if header.version[0] >= 4:
        unsigned = header_bytes(0, 0, profile_id) + table + data
        profile_id = hashlib.md5(unsigned, usedforsecurity=False).digest()
    return (
        header_bytes(header.flags, header.rendering_intent, profile_id) + table + data
    )


def text_description(text: str) -> bytes:
    """Return a textDescriptionType with ``text`` as its ASCII description."""
    ascii_text = text.encode("ascii") + b"\0"
    return (
        b"desc"
        + b"\0" * 4
        + struct.pack(">I", len(ascii_text))
        + ascii_text
        + struct.pack(">II", 0, 0)  # no Unicode description
        + struct.pack(">HB", 0, 0)  # no ScriptCode description
        + b"\0" * 67
    )


def text_type(text: str) -> bytes:
    """Return a textType holding ``text``."""
    return b"text" + b"\0" * 4 + text.encode("ascii") + b"\0"


def _xyz(values: tuple[int, int, int]) -> bytes:
    """Return an XYZType holding one s15Fixed16Number XYZ value."""
    return b"XYZ " + b"\0" * 4 + struct.pack(">3I", *values)


def _curve() -> bytes:
    """Return a curveType sampling the sRGB tone curve of IEC 61966-2.1."""
    entries = [
        round(_srgb_linear(index / (_CURVE_ENTRIES - 1)) * 0xFFFF)
        for index in range(_CURVE_ENTRIES)
    ]
    return (
        b"curv"
        + b"\0" * 4
        + struct.pack(">I", _CURVE_ENTRIES)
        + struct.pack(f">{_CURVE_ENTRIES}H", *entries)
    )


def _srgb_linear(value: float) -> float:
    """Return the linear value of an sRGB-encoded value from zero to one."""
    if value <= 0.04045:
        return value / 12.92
    return float(((value + 0.055) / 1.055) ** 2.4)
