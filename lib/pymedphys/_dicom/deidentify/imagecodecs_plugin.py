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

"""A pydicom decoding plugin that decodes with imagecodecs.

pydicom 3.0.2's GDCM plugin refuses three kinds of frame before GDCM sees
them: JPEG Extended at a precision of 12 bits, JPEG-LS at 6 or 7 bits, and
signed JPEG-LS Near-Lossless below 8 bits (D-055).
:mod:`.pixel_decoding` decodes those with this plugin instead: JPEG with
libjpeg-turbo 3, which decodes 12-bit lossy JPEG, and JPEG-LS with CharLS,
each through imagecodecs. imagecodecs is BSD-3-Clause, libjpeg-turbo is
under the IJG, BSD-3-Clause, and zlib licences, and CharLS is BSD-3-Clause,
each at least as permissive as PyMedPhys's Apache License 2.0.

The plugin has the form that pydicom's decoding plugins have
(:func:`is_available`, :data:`DECODER_DEPENDENCIES`, and
:func:`_decode_frame`), so that pydicom applies to its frames what it
applies to every plugin's: the sign of JPEG-LS samples, Bits Stored, and
conversion of YBR_FULL and YBR_FULL_422 to RGB where asked. It returns the
samples as the codestream holds them, with no conversion of colour space
of its own, as pydicom's other plugins do for JPEG. It is never added to
pydicom's own decoders, so it changes nothing that pydicom decodes
elsewhere: :mod:`.pixel_decoding` adds it to a decoder of its own, only in
the decoding child (:mod:`.isolated_decoding`), since libjpeg-turbo and
CharLS are native libraries that a malformed codestream could make end
the process that calls them.

libjpeg-turbo's warnings, as for entropy-coded data that ends early, are
not passed on by imagecodecs, so a frame with them still decodes; the
codestream's markers are read beforehand (:mod:`.frame_headers`), and
damaged entropy-coded data still followed by EOI is not detected, as with
GDCM.
"""

from __future__ import annotations

import re
import types
from collections.abc import Mapping

from pymedphys._imports import imagecodecs
from pymedphys._imports import pydicom

JPEG_EXTENDED = "1.2.840.10008.1.2.4.51"
JPEG_LS_LOSSLESS = "1.2.840.10008.1.2.4.80"
JPEG_LS_NEAR_LOSSLESS = "1.2.840.10008.1.2.4.81"
_REQUIREMENT = ("imagecodecs>=2025.11.11",)
DECODER_DEPENDENCIES: Mapping[str, tuple[str, ...]] = types.MappingProxyType(
    {
        JPEG_EXTENDED: _REQUIREMENT,
        JPEG_LS_LOSSLESS: _REQUIREMENT,
        JPEG_LS_NEAR_LOSSLESS: _REQUIREMENT,
    }
)
"""What the plugin needs for each transfer syntax that it decodes, as
pydicom's plugins give it."""
# The first libjpeg-turbo that decodes 12-bit lossy JPEG.
_TWELVE_BIT_TURBO = (3, 0)
_TURBO = re.compile(r"libjpeg_turbo (\d+)\.(\d+)")


def is_available(uid: str) -> bool:
    """Return whether the plugin can decode the transfer syntax ``uid``.

    JPEG needs imagecodecs built with libjpeg-turbo 3 or later, and JPEG-LS
    imagecodecs built with CharLS.
    """
    if uid not in DECODER_DEPENDENCIES:
        return False
    try:
        if uid == JPEG_EXTENDED:
            if not imagecodecs.JPEG8.available:
                return False
            version = _TURBO.match(str(imagecodecs.jpeg8_version()))
            return version is not None and (
                tuple(int(part) for part in version.groups()) >= _TWELVE_BIT_TURBO
            )
        return bool(imagecodecs.JPEGLS.available)
    # imagecodecs is not installed, or was built without the codec.
    except (ImportError, AttributeError):
        return False


def _decode_frame(
    src: bytes, runner: pydicom.pixels.decoders.base.DecodeRunner
) -> bytearray:
    """Return one frame's samples, as its codestream ``src`` holds them.

    The samples of a pixel are together, so a colour frame is given as
    Planar Configuration 0, and each sample is in one byte where the
    codestream's precision is at most 8 bits and two otherwise.
    """
    if runner.transfer_syntax == JPEG_EXTENDED:
        if runner.samples_per_pixel > 1:
            # libjpeg-turbo converts nothing from a colour space to itself.
            space = imagecodecs.JPEG8.CS.YCbCr
            frame = imagecodecs.jpeg8_decode(src, colorspace=space, outcolorspace=space)
        else:
            frame = imagecodecs.jpeg8_decode(src)
    else:
        frame = imagecodecs.jpegls_decode(src)
    if runner.samples_per_pixel > 1:
        runner.set_option("planar_configuration", 0)
    runner.set_option("bits_allocated", 8 * frame.dtype.itemsize)
    # Writable, as pydicom corrects the sign of JPEG-LS samples in place.
    return bytearray(frame.tobytes())
