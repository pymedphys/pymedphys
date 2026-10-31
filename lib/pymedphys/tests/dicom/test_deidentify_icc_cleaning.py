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

"""Cleaning a source ICC profile keeps its colorimetry and nothing else (D-021).

The source profiles come from :mod:`._synthetic_icc`, written from the ICC
specifications independently of the cleaner, from LittleCMS's own sRGB
profile, and from the profile among pydicom's test files. LittleCMS, through
Pillow, is the independent reader: a cleaned profile must map every colour of
a grid exactly as its source does, at every rendering intent and in both
directions.
"""

import io
import itertools
import struct

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import icc_cleaning, icc_profiles
from pymedphys._dicom.deidentify.icc_cleaning import Refusal, UncleanableProfileError

from . import _synthetic_icc as icc

TEXT = "DEIDENTIFIED"
V2 = bytes([2, 0x40, 0, 0])
V4 = bytes([4, 0x30, 0, 0])
IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _linear_curves():
    return icc.curve_set(icc.para(0, 1.0), icc.para(0, 1.0), icc.para(0, 1.0))


def _srgb_curves(careless=False):
    curve = icc.para(3, 2.4, 1 / 1.055, 0.055 / 1.055, 1 / 12.92, 0.04045)
    return icc.curve_set(curve, icc.gamma(2.2), curve, careless=careless)


def _xyz_16(rgb):
    """Return the D50 XYZ of an sRGB value, scaled as a lutAtoBType's CLUT holds it."""
    return [value * 0x8000 / 0xFFFF for value in icc.rgb_to_xyz(rgb)]


def _a2b(*names, careless=False):
    """Return a lutAtoBType holding the named elements."""
    elements = {
        "B": icc.curve_set(icc.gamma(1.0), icc.gamma(1.0), icc.gamma(1.0)),
        "matrix": icc.matrix_bytes(icc.SRGB_MATRIX),
        "M": _srgb_curves(careless),
        "CLUT": icc.clut_ab(5, 2, _xyz_16),
        "A": _srgb_curves(careless),
    }
    if "CLUT" in names and "matrix" in names:
        # The CLUT then gives linear RGB, which the matrix maps to XYZ.
        elements["CLUT"] = icc.clut_ab(3, 1, list)
        elements["M"] = _linear_curves()
    if names == ("B",):
        elements["B"] = _srgb_curves(careless)
    return icc.lut_ab(b"mAB ", {n: elements[n] for n in names}, careless)


def _b2a(*names):
    """Return a lutBtoAType holding the named elements."""
    elements = {
        "B": _linear_curves(),
        "matrix": icc.matrix_bytes(
            (
                (3.1339, -1.6169, -0.4906),
                (-0.9788, 1.9161, 0.0335),
                (0.0719, -0.229, 1.4052),
            )
        ),
        "M": icc.curve_set(icc.gamma(1 / 2.2), icc.gamma(1 / 2.2), icc.gamma(1 / 2.2)),
        "CLUT": icc.clut_ab(3, 2, list),
        "A": icc.curve_set(icc.gamma(1 / 2.2), icc.gamma(1 / 2.2), icc.gamma(1 / 2.2)),
    }
    return icc.lut_ab(b"mBA ", {n: elements[n] for n in names})


def _d2b():
    """Return a multiProcessElementsType from RGB to XYZ: curves, CLUT, and matrix."""
    curve = icc.srgb_curve_segments()
    sampled = icc.curf(
        (0.0,),
        icc.parf(0, 1.0, 1.0, 0.0, 0.0),
        icc.samf(*(i / 15 for i in range(1, 16))),
    )
    return icc.mpet(
        icc.cvst(curve, sampled, curve),
        icc.clut_element(3, lambda rgb: [0.9 * v + 0.05 for v in rgb]),
        icc.matf(icc.SRGB_MATRIX, (0.0, 0.0, 0.0)),
        careless=True,
    )


def _lab_a2b():
    """Return a lutAtoBType from RGB to the Lab PCS through a CLUT."""

    def lab(rgb):
        x, y, z = (v / w for v, w in zip(icc.rgb_to_xyz(rgb), icc.WHITE))

        def f(t):
            return (
                t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29
            )

        lightness = 116 * f(y) - 16
        return [
            lightness / 100,
            (500 * (f(x) - f(y)) + 128) / 255,
            (200 * (f(y) - f(z)) + 128) / 255,
        ]

    return icc.lut_ab(
        b"mAB ",
        {
            "B": _linear_curves(),
            "CLUT": icc.clut_ab(9, 2, lab),
            "A": _linear_curves(),
        },
    )


def _v2_matrix(careless=True):
    return icc.profile(
        icc.Header(version=V2, device_class=b"mntr", flags=0xFFFF0003),
        icc.text_tags(2)
        + icc.matrix_tags(2, careless)
        + [
            (b"bkpt", icc.xyz(0.0, 0.0, 0.0)),
            (b"lumi", icc.xyz(76.0, 80.0, 87.0)),
            (b"meas", icc.meas()),
            (b"view", icc.view()),
        ]
        + icc.chromaticity_tags(),
        careless=careless,
    )


def _v4_matrix(careless=True):
    return icc.profile(
        icc.Header(device_class=b"mntr", rendering_intent=1),
        icc.text_tags(4)
        + icc.matrix_tags(4, careless)
        + [
            (
                b"chad",
                icc.sf32(
                    1.0479,
                    0.0229,
                    -0.0502,
                    0.0296,
                    0.9904,
                    -0.0171,
                    -0.0092,
                    0.0151,
                    0.7519,
                ),
            ),
            (b"cicp", icc.cicp(1, 13, 0, 1)),
            (b"ciis", icc.signature(b"scoe")),
            (b"rig0", icc.signature(b"prmg")),
            (b"meas", icc.meas()),
        ]
        + icc.chromaticity_tags(),
        careless=careless,
    )


def _v2_lut():
    return icc.profile(
        icc.Header(version=V2),
        icc.text_tags(2)
        + [
            (b"wtpt", icc.xyz(*icc.WHITE)),
            (b"A2B0", icc.lut16_a2b(careless=True)),
            (b"A2B1", icc.lut16_a2b(grid=9)),
            (b"B2A0", icc.lut8_b2a()),
        ],
        careless=True,
    )


def _v4_lut(*names):
    return icc.profile(
        icc.Header(device_class=b"spac"),
        icc.text_tags(4)
        + [(b"wtpt", icc.xyz(*icc.WHITE)), (b"A2B0", _a2b(*names, careless=True))],
        careless=True,
    )


def _v4_lut_both_ways():
    return icc.profile(
        icc.Header(),
        icc.text_tags(4)
        + [
            (b"wtpt", icc.xyz(*icc.WHITE)),
            (b"A2B0", _a2b("B", "matrix", "M")),
            (b"A2B1", _a2b("A", "CLUT", "B")),
            (b"A2B2", _a2b("A", "CLUT", "M", "matrix", "B")),
            (b"B2A0", _b2a("B", "matrix", "M")),
            (b"B2A1", _b2a("B", "CLUT", "A")),
            (b"B2A2", _b2a("B", "matrix", "M", "CLUT", "A")),
        ],
    )


def _v4_lab():
    return icc.profile(
        icc.Header(connection_space=b"Lab "),
        icc.text_tags(4) + [(b"wtpt", icc.xyz(*icc.WHITE)), (b"A2B0", _lab_a2b())],
    )


def _v4_multi_process():
    return icc.profile(
        icc.Header(version=bytes([4, 0x40, 0, 0])),
        icc.text_tags(4)
        + icc.matrix_tags(4)
        + [(b"A2B0", _a2b("B", "matrix", "M")), (b"D2B0", _d2b())],
        careless=True,
    )


def _lcms_srgb():
    image_cms = pytest.importorskip("PIL.ImageCms")
    return image_cms.ImageCmsProfile(image_cms.createProfile("sRGB")).tobytes()


def _pydicom_profile():
    pydicom = pytest.importorskip("pydicom")
    path = pydicom.data.get_testdata_file("crayons.icc")
    if path is None:
        pytest.skip("pydicom's test files do not include its ICC profile")
    with open(path, "rb") as file:
        return file.read()


SOURCES = {
    "v2-matrix": _v2_matrix,
    "v4-matrix": _v4_matrix,
    "v2-lut16-lut8": _v2_lut,
    "v4-a2b-b": lambda: _v4_lut("B"),
    "v4-a2b-m-matrix-b": lambda: _v4_lut("B", "matrix", "M"),
    "v4-a2b-a-clut-b": lambda: _v4_lut("A", "CLUT", "B"),
    "v4-a2b-all": lambda: _v4_lut("A", "CLUT", "M", "matrix", "B"),
    "v4-a2b-b2a": _v4_lut_both_ways,
    "v4-lab": _v4_lab,
    "v4-multi-process": _v4_multi_process,
    "lcms-srgb": _lcms_srgb,
    "pydicom-crayons": _pydicom_profile,
}
# The sources that hold a transform from the PCS back to RGB, or a matrix
# and tone curves, which LittleCMS inverts, so that they can be an output.
INVERTIBLE = {
    "v2-matrix",
    "v4-matrix",
    "v2-lut16-lut8",
    "v4-a2b-b2a",
    "v4-multi-process",
    "lcms-srgb",
    "pydicom-crayons",
}


@pytest.fixture(name="source", params=sorted(SOURCES))
def fixture_source(request):
    return request.param, SOURCES[request.param]()


def _grid_image():
    image = pytest.importorskip("PIL.Image")
    colours = list(itertools.product(range(0, 256, 15), repeat=3))
    picture = image.new("RGB", (len(colours), 1))
    picture.frombytes(bytes(itertools.chain.from_iterable(colours)))
    return picture


def _mapped(profile, intent, as_output=False):
    """Return the grid's colours mapped from the profile to sRGB, or the reverse."""
    image_cms = pytest.importorskip("PIL.ImageCms")
    read = image_cms.ImageCmsProfile(io.BytesIO(profile))
    srgb = image_cms.createProfile("sRGB")
    ends = (srgb, read) if as_output else (read, srgb)
    transform = image_cms.buildTransform(*ends, "RGB", "RGB", renderingIntent=intent)
    return image_cms.applyTransform(_grid_image(), transform).tobytes()


@pytest.mark.parametrize("intent", range(4))
def test_lcms_maps_every_colour_as_the_source_does(source, intent):
    name, profile = source
    cleaned = icc_cleaning.clean_profile(profile, TEXT)

    assert _mapped(cleaned, intent) == _mapped(profile, intent)
    if name in INVERTIBLE:
        assert _mapped(cleaned, intent, as_output=True) == _mapped(
            profile, intent, as_output=True
        )


def test_the_floating_point_transform_is_kept_where_it_differs():
    # LittleCMS reads D2B0 in place of A2B0 where both are present, so the
    # source maps differently without it; the cleaned profile keeps it.
    profile = _v4_multi_process()
    without = icc.profile(
        icc.Header(version=bytes([4, 0x40, 0, 0])),
        icc.matrix_tags(4) + [(b"A2B0", _a2b("B", "matrix", "M"))],
    )
    cleaned = icc_cleaning.clean_profile(profile, TEXT)

    assert _mapped(profile, 0) != _mapped(without, 0)
    assert _mapped(cleaned, 0) == _mapped(profile, 0)


def test_lcms_reads_the_text_given(source):
    image_cms = pytest.importorskip("PIL.ImageCms")
    _, profile = source
    read = image_cms.ImageCmsProfile(
        io.BytesIO(icc_cleaning.clean_profile(profile, TEXT))
    )

    assert image_cms.getProfileDescription(read).strip() == TEXT
    assert image_cms.getProfileCopyright(read).strip() == TEXT


def test_nothing_of_the_text_tags_header_padding_or_reserved_fields_survives(source):
    name, profile = source
    cleaned = icc_cleaning.clean_profile(profile, TEXT)

    assert icc.MARKER[:4] not in cleaned
    assert b"ROYAL" not in cleaned
    for field in (b"ZZCM", b"ZZPL", b"ZZMF", b"ZZMD", b"ZZATTRIB", b"ZZCR"):
        assert field not in cleaned
    assert not set(icc.tags_of(cleaned)) & {
        b"dmnd",
        b"dmdd",
        b"vued",
        b"targ",
        b"scrd",
        b"tech",
        b"calt",
        b"ZZPV",
        b"vcgt",
    }, name


def test_the_header_keeps_only_the_colorimetric_fields(source):
    _, profile = source
    cleaned = icc_cleaning.clean_profile(profile, TEXT)

    assert int.from_bytes(cleaned[:4], "big") == len(cleaned)
    assert len(cleaned) % 4 == 0
    # No preferred CMM; the source's version, with its reserved bytes zero.
    assert cleaned[4:8] == bytes(4)
    assert cleaned[8:10] == profile[8:10]
    assert cleaned[10:12] == bytes(2)
    # An input device profile (PS3.3 Section C.11.15.1.1) of the source's
    # data colour space and PCS.
    assert cleaned[12:16] == b"scnr"
    assert cleaned[16:24] == profile[16:24]
    assert struct.unpack_from(">6H", cleaned, 24) == (1900, 1, 1, 0, 0, 0)
    assert cleaned[36:40] == b"acsp"
    # No platform, device, attributes, or creator; only the defined flags.
    assert cleaned[40:44] == bytes(4)
    assert int.from_bytes(cleaned[44:48], "big") == (
        int.from_bytes(profile[44:48], "big") & 0b11
    )
    assert cleaned[48:64] == bytes(16)
    # The rendering intent and PCS illuminant are the source's.
    assert cleaned[64:80] == profile[64:80]
    assert cleaned[80:84] == bytes(4)
    assert cleaned[100:128] == bytes(28)


def test_the_tests_profile_id_is_the_one_lcms_writes():
    # pydicom's profile was written by LittleCMS with its profile ID, so the
    # digest that these tests compute is checked against another writer's.
    profile = _pydicom_profile()

    assert profile[84:100] != bytes(16)
    assert icc.profile_id(profile) == profile[84:100]


def test_a_version_4_profile_id_is_the_digest_of_the_cleaned_profile(source):
    _, profile = source
    cleaned = icc_cleaning.clean_profile(profile, TEXT)

    if cleaned[8] == 4:
        assert cleaned[84:100] == icc.profile_id(cleaned)
        assert cleaned[84:100] != bytes(16)
    else:
        assert cleaned[84:100] == bytes(16)


def test_every_tag_is_one_its_version_defines_within_the_profile(source):
    _, profile = source
    cleaned = icc_cleaning.clean_profile(profile, TEXT)
    (count,) = struct.unpack_from(">I", cleaned, 128)

    for index in range(count):
        _, offset, size = struct.unpack_from(">4sII", cleaned, 132 + 12 * index)
        assert offset % 4 == 0
        assert 132 + 12 * count <= offset
        assert offset + size <= len(cleaned)
    tags = icc.tags_of(cleaned)
    if cleaned[8] == 2:
        assert tags[b"desc"][:4] == b"desc"
        assert tags[b"cprt"][:4] == b"text"
    else:
        assert tags[b"desc"][:4] == tags[b"cprt"][:4] == b"mluc"
        assert b"bkpt" not in tags


@pytest.mark.parametrize(
    "make, expected",
    [
        (
            _v2_matrix,
            {
                b"desc",
                b"cprt",
                b"wtpt",
                b"bkpt",
                b"lumi",
                b"rXYZ",
                b"gXYZ",
                b"bXYZ",
                b"rTRC",
                b"gTRC",
                b"bTRC",
                b"chrm",
                b"meas",
                b"view",
            },
        ),
        (
            _v4_matrix,
            {
                b"desc",
                b"cprt",
                b"wtpt",
                b"chad",
                b"rXYZ",
                b"gXYZ",
                b"bXYZ",
                b"rTRC",
                b"gTRC",
                b"bTRC",
                b"chrm",
                b"cicp",
                b"meas",
                b"ciis",
                b"rig0",
            },
        ),
        (_v2_lut, {b"desc", b"cprt", b"wtpt", b"A2B0", b"A2B1", b"B2A0"}),
    ],
    ids=["v2-matrix", "v4-matrix", "v2-lut"],
)
def test_the_colorimetric_tags_are_kept_and_no_others(make, expected):
    assert set(icc.tags_of(icc_cleaning.clean_profile(make(), TEXT))) == expected


def test_the_colorimetric_tags_are_kept_value_for_value():
    profile = _v4_matrix(careless=False)
    source = icc.tags_of(profile)
    cleaned = icc.tags_of(icc_cleaning.clean_profile(profile, TEXT))

    for tag in (b"wtpt", b"chad", b"rXYZ", b"rTRC", b"chrm", b"cicp", b"meas", b"ciis"):
        assert cleaned[tag] == source[tag]


def test_cleaning_is_deterministic_and_a_cleaned_profile_cleans_to_itself(source):
    _, profile = source
    cleaned = icc_cleaning.clean_profile(profile, TEXT)

    assert icc_cleaning.clean_profile(profile, TEXT) == cleaned
    assert icc_cleaning.clean_profile(cleaned, TEXT) == cleaned
    assert icc_cleaning.clean_profile(profile, "DE-IDENTIFIED") != cleaned


def test_the_padding_of_an_odd_length_ob_value_is_ignored():
    profile = icc.profile(icc.Header(version=V2), icc.matrix_tags(2))
    padded = profile + b"\0"

    assert icc_cleaning.clean_profile(padded, TEXT) == icc_cleaning.clean_profile(
        profile, TEXT
    )


def test_the_fixed_srgb_profile_is_cleaned_to_the_same_colorimetry():
    source = icc_profiles.srgb_profile("DEIDENTIFIED sRGB")
    cleaned = icc_cleaning.clean_profile(source, TEXT)

    assert icc.tags_of(cleaned)[b"rTRC"] == icc.tags_of(source)[b"rTRC"]
    assert icc.tags_of(cleaned)[b"desc"] == icc_profiles.text_description(TEXT)


def test_a_descriptive_tag_that_does_not_parse_is_removed():
    profile = icc.profile(
        icc.Header(),
        icc.matrix_tags(4)
        + [
            # Four channels, which an RGB profile cannot have; and a
            # signature that ICC.1 does not register.
            (b"chrm", b"chrm" + bytes(4) + icc.u16(4) + icc.u16(0) + bytes(32)),
            (b"ciis", icc.signature(b"ZZZZ")),
            (b"meas", b"meas" + bytes(4)),
        ],
    )

    tags = icc.tags_of(icc_cleaning.clean_profile(profile, TEXT))

    assert not {b"chrm", b"ciis", b"meas"} & set(tags)
    assert b"rTRC" in tags


def _with_header(**fields):
    return icc.profile(icc.Header(**fields), icc.matrix_tags(4))


def _with_tags(tags, version=V4, connection_space=b"XYZ "):
    return icc.profile(
        icc.Header(version=version, connection_space=connection_space), tags
    )


def _matrix_with(tag, data, version=4):
    return [(t, data if t == tag else d) for t, d in icc.matrix_tags(version)]


def _truncated(profile):
    return profile[:-8]


def _out_of_bounds(profile):
    written = bytearray(profile)
    struct.pack_into(">I", written, 132 + 4, len(profile))
    return bytes(written)


def _duplicated(profile):
    written = bytearray(profile)
    written[132 + 12 : 132 + 16] = written[132:136]
    return bytes(written)


MATRIX_V4 = icc.profile(icc.Header(), icc.matrix_tags(4))


@pytest.mark.parametrize(
    "profile, refusal",
    [
        (_with_header(version=bytes([3, 0, 0, 0])), Refusal.VERSION),
        (_with_header(version=bytes([5, 0, 0, 0])), Refusal.VERSION),
        (_with_header(device_class=b"prtr"), Refusal.DEVICE_CLASS),
        (_with_header(device_class=b"link"), Refusal.DEVICE_CLASS),
        (_with_header(device_class=b"abst"), Refusal.DEVICE_CLASS),
        (_with_header(device_class=b"nmcl"), Refusal.DEVICE_CLASS),
        (_with_header(connection_space=b"RGB "), Refusal.CONNECTION_SPACE),
        # D65 in place of D50.
        (_with_header(illuminant=(0xF351, 0x10000, 0x116CC)), Refusal.HEADER),
        (_with_header(rendering_intent=4), Refusal.HEADER),
        (_with_header(rendering_intent=0x10000), Refusal.HEADER),
        (_truncated(MATRIX_V4), Refusal.STRUCTURE),
        (MATRIX_V4 + bytes(4), Refusal.STRUCTURE),
        (_out_of_bounds(MATRIX_V4), Refusal.STRUCTURE),
        (_duplicated(MATRIX_V4), Refusal.STRUCTURE),
        # A parametric curve, which version 2 does not define.
        (
            _with_tags(_matrix_with(b"rTRC", icc.para(0, 2.2), 2), version=V2),
            Refusal.TAG_TYPE,
        ),
        # A lutAtoBType, which version 2 does not define.
        (
            _with_tags(icc.matrix_tags(2) + [(b"A2B0", _a2b("B"))], version=V2),
            Refusal.TAG_TYPE,
        ),
        (_with_tags(_matrix_with(b"rXYZ", icc.text(b"x"))), Refusal.TAG_TYPE),
        (_with_tags(_matrix_with(b"rTRC", icc.curv([0, 1, 2])[:-2])), Refusal.TAG_DATA),
        (_with_tags(_matrix_with(b"rTRC", icc.para(5, 1.0))), Refusal.TAG_DATA),
        (_with_tags(_matrix_with(b"rXYZ", b"XYZ " + bytes(8))), Refusal.TAG_DATA),
        (
            _with_tags(icc.matrix_tags(4) + [(b"A2B0", _a2b("A", "CLUT", "M", "B"))]),
            Refusal.TAG_DATA,
        ),
        (
            _with_tags(
                icc.matrix_tags(4)
                + [(b"A2B0", icc.lut16_a2b()[:48] + icc.u16(1) + icc.lut16_a2b()[50:])]
            ),
            Refusal.TAG_DATA,
        ),
        (
            _with_tags(
                icc.matrix_tags(4)
                + [
                    (
                        b"D2B0",
                        icc.mpet(
                            b"bACS" + bytes(4) + icc.u16(3) + icc.u16(3) + bytes(4)
                        ),
                    )
                ]
            ),
            Refusal.TAG_DATA,
        ),
        (
            _with_tags(
                icc.matrix_tags(4)
                + [(b"D2B0", icc.mpet(icc.matf(IDENTITY, (float("nan"), 0.0, 0.0))))]
            ),
            Refusal.TAG_DATA,
        ),
        (
            _with_tags(
                icc.matrix_tags(4)
                + [
                    (
                        b"D2B0",
                        icc.mpet(
                            icc.matf(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), (0.0, 0.0))
                        ),
                    )
                ]
            ),
            Refusal.TAG_DATA,
        ),
        (_with_tags(icc.matrix_tags(4)[1:]), Refusal.NO_WHITE_POINT),
        (_with_tags(icc.matrix_tags(4)[:-1]), Refusal.NO_TRANSFORM),
        (
            _with_tags(icc.matrix_tags(4), connection_space=b"Lab "),
            Refusal.NO_TRANSFORM,
        ),
    ],
)
def test_a_profile_that_cannot_be_accounted_for_is_refused(profile, refusal):
    with pytest.raises(UncleanableProfileError) as raised:
        icc_cleaning.clean_profile(profile, TEXT)

    assert raised.value.refusal is refusal
    assert str(raised.value) == f"the ICC profile cannot be cleaned: {refusal.value}"


@pytest.mark.parametrize(
    "profile",
    [
        b"",
        b"not a profile",
        icc.profile(icc.Header(colour_space=b"GRAY"), icc.matrix_tags(4)),
        icc.profile(icc.Header(colour_space=b"CMYK"), icc.matrix_tags(4)),
    ],
)
def test_a_source_that_is_not_an_rgb_profile_is_rejected(profile):
    with pytest.raises(ValueError, match="not an RGB ICC profile"):
        icc_cleaning.clean_profile(profile, TEXT)
