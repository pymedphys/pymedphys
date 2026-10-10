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

"""The ICC profiles that D writes in place of ICC Profile."""

import io
import struct

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import icc_profiles

# The tags that ICC.1:2001-04 Section 6.3.1.2 requires of a matrix and tone
# curve input profile.
REQUIRED_TAGS = {
    b"desc",
    b"cprt",
    b"wtpt",
    b"rXYZ",
    b"gXYZ",
    b"bXYZ",
    b"rTRC",
    b"gTRC",
    b"bTRC",
}
D50 = (0.9642, 1.0, 0.8249)
SRGB = icc_profiles.srgb_profile("x")


def _tags(profile):
    """Return each tag's signature with its data."""
    (count,) = struct.unpack_from(">I", profile, 128)
    tags = {}
    for index in range(count):
        signature, offset, size = struct.unpack_from(">4sII", profile, 132 + 12 * index)
        assert offset % 4 == 0
        assert offset + size <= len(profile)
        tags[signature] = profile[offset : offset + size]
    return tags


def _xyz(element):
    assert element[:4] == b"XYZ "
    return tuple(value / 65536 for value in struct.unpack_from(">3i", element, 8))


@pytest.mark.deid_requirement("MIDI-BP-14")
def test_the_profile_is_a_version_2_4_rgb_input_profile():
    profile = icc_profiles.srgb_profile("DEIDENTIFIED")

    assert int.from_bytes(profile[:4], "big") == len(profile)
    # OB values have even length (PS3.5 Section 6.2).
    assert len(profile) % 2 == 0
    assert profile[8:12] == bytes([2, 0x40, 0, 0])
    # PS3.3 Section C.11.15.1.1: an input device profile, whose input colour
    # space is RGB, with a PCS of CIEXYZ or CIELab.
    assert profile[12:16] == b"scnr"
    assert profile[16:20] == icc_profiles.RGB
    assert profile[20:24] == b"XYZ "
    assert struct.unpack_from(">6H", profile, 24) == (1900, 1, 1, 0, 0, 0)
    assert profile[36:40] == b"acsp"
    # The header names no platform, maker, model, or creator.
    assert set(profile[40:44] + profile[48:56] + profile[80:84]) == {0}
    # The rendering intent is perceptual, as Section C.11.15.1.1 recommends.
    assert profile[64:68] == bytes(4)
    assert tuple(round(v, 4) for v in _xyz(b"XYZ " + bytes(4) + profile[68:80])) == D50
    assert set(_tags(profile)) == REQUIRED_TAGS


def test_the_description_and_copyright_are_the_only_text():
    tags = _tags(icc_profiles.srgb_profile("DEIDENTIFIED sRGB"))

    description = tags[b"desc"]
    (length,) = struct.unpack_from(">I", description, 8)
    assert description[12 : 12 + length] == b"DEIDENTIFIED sRGB\0"
    assert tags[b"cprt"] == b"text" + bytes(4) + b"No copyright, use freely\0"


def test_the_srgb_colorants_sum_to_the_white_point():
    tags = _tags(icc_profiles.srgb_profile("DEIDENTIFIED sRGB"))

    colorants = [_xyz(tags[signature]) for signature in (b"rXYZ", b"gXYZ", b"bXYZ")]
    white = tuple(sum(component) for component in zip(*colorants))

    # As in the published sRGB profiles, the rounded colorants' Z sums to
    # 0.8251, against D50's 0.8249.
    assert white == pytest.approx(_xyz(tags[b"wtpt"]), abs=2e-4)
    assert _xyz(tags[b"wtpt"]) == pytest.approx(D50, abs=1e-4)


def test_the_tone_curves_are_the_srgb_curve():
    tags = _tags(icc_profiles.srgb_profile("DEIDENTIFIED"))
    curve = tags[b"rTRC"]
    assert tags[b"gTRC"] == tags[b"bTRC"] == curve

    (count,) = struct.unpack_from(">I", curve, 8)
    entries = struct.unpack_from(f">{count}H", curve, 12)

    assert curve[:4] == b"curv"
    assert entries[0] == 0
    assert entries[-1] == 0xFFFF
    assert all(a <= b for a, b in zip(entries, entries[1:]))
    # sRGB 0.5 is linear 0.2140 (IEC 61966-2.1).
    middle = entries[round((count - 1) * 0.5)] / 0xFFFF
    assert middle == pytest.approx(0.2140, abs=1e-3)


def test_the_profile_is_the_same_every_time():
    build = icc_profiles.srgb_profile

    assert build("DEIDENTIFIED") == build("DEIDENTIFIED")
    assert build("DEIDENTIFIED") != build("DE-IDENTIFIED")


@pytest.mark.parametrize(
    "profile, expected",
    [
        (SRGB, icc_profiles.RGB),
        # A grey profile's header, which a source can hold though PS3.3
        # Section C.11.15.1.1 requires RGB.
        (SRGB[:16] + b"GRAY" + SRGB[20:], b"GRAY"),
        (b"", None),
        (bytes(128), None),
        (b"a" * 200, None),
    ],
)
def test_the_data_colour_space_comes_from_a_valid_header_only(profile, expected):
    assert icc_profiles.data_colour_space(profile) == expected


def test_lcms_reads_the_profile():
    image_cms = pytest.importorskip("PIL.ImageCms")

    profile = image_cms.ImageCmsProfile(
        io.BytesIO(icc_profiles.srgb_profile("DEIDENTIFIED sRGB"))
    )

    assert image_cms.getProfileDescription(profile).strip() == "DEIDENTIFIED sRGB"


def test_lcms_maps_the_srgb_profile_to_its_own_srgb():
    image_cms = pytest.importorskip("PIL.ImageCms")
    image = pytest.importorskip("PIL.Image")
    written = image_cms.ImageCmsProfile(
        io.BytesIO(icc_profiles.srgb_profile("DEIDENTIFIED sRGB"))
    )
    transform = image_cms.buildTransform(
        written, image_cms.createProfile("sRGB"), "RGB", "RGB"
    )
    colours = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (128, 128, 128), (255, 255, 255)]
    source = image.new("RGB", (len(colours), 1))
    for index, colour in enumerate(colours):
        source.putpixel((index, 0), colour)

    result = image_cms.applyTransform(source, transform)

    for index, colour in enumerate(colours):
        assert result.getpixel((index, 0)) == pytest.approx(colour, abs=2)
