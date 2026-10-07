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

PS3.3 Section C.11.15.1.1 makes ICC Profile an ICC Input Device Profile.
Where D replaces one, it writes a fixed profile of the same data colour
space, built here the same way every time: :func:`srgb_profile` for an RGB
source profile, the sRGB colour space of IEC 61966-2.1, and
:func:`grey_profile` for a grey one, with the sRGB tone curve. Each is an
ICC version 2.4 input profile (ICC.1:2001-04), of the matrix and tone curve
model (Section 6.3.1.2) or the monochrome one (Section 6.3.1.1), whose PCS
is CIE XYZ under the D50 illuminant and whose media white point is D50.

Nothing of the source profile is written. Its header gives only its data
colour space, which decides the profile written; its contents are not
otherwise read.
"""

from __future__ import annotations

import struct

_HEADER_LENGTH = 128
# The profile file signature, at bytes 36 to 39 of the header.
_SIGNATURE = b"acsp"
RGB = b"RGB "
GREY = b"GRAY"
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
_CREATED = (1900, 1, 1, 0, 0, 0)


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
    curve = _curve()
    tags = [
        (b"desc", _description(description)),
        (b"cprt", _text(_COPYRIGHT)),
        (b"wtpt", _xyz(_D50)),
        *((signature, _xyz(values)) for signature, values in _COLORANTS),
        (b"rTRC", curve),
        (b"gTRC", curve),
        (b"bTRC", curve),
    ]
    return _profile(RGB, tags)


def grey_profile(description: str) -> bytes:
    """Return a grey input profile with the sRGB tone curve.

    Examples
    --------
    >>> data_colour_space(grey_profile("DEIDENTIFIED grey"))
    b'GRAY'
    """
    tags = [
        (b"desc", _description(description)),
        (b"cprt", _text(_COPYRIGHT)),
        (b"wtpt", _xyz(_D50)),
        (b"kTRC", _curve()),
    ]
    return _profile(GREY, tags)


def _profile(colour_space: bytes, tags: list[tuple[bytes, bytes]]) -> bytes:
    """Return a profile's bytes: its header, tag table, and tag data.

    Tags with the same data share it, as the three tone curves of an RGB
    profile do, and each tag's data starts on a four-byte boundary.
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
    header = (
        struct.pack(">I", size)
        + b"\0" * 4  # preferred CMM: none
        + struct.pack(">I", 0x02400000)  # version 2.4
        + b"scnr"  # an input device profile
        + colour_space
        + b"XYZ "
        + struct.pack(">6H", *_CREATED)
        + _SIGNATURE
        + b"\0" * 4  # primary platform: none
        + b"\0" * 4  # flags
        + b"\0" * 8  # device manufacturer and model: none
        + b"\0" * 8  # device attributes
        + struct.pack(">I", 0)  # perceptual rendering intent
        + struct.pack(">3I", *_D50)
        + b"\0" * 4  # profile creator: none
        + b"\0" * 44  # reserved
    )
    return header + table + data


def _description(text: str) -> bytes:
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


def _text(text: str) -> bytes:
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
