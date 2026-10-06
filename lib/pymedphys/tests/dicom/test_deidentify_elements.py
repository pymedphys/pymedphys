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

"""Elements decoded with the pinned data dictionary, and the elements written.

Every data set is synthetic, built here or by ``_synthetic_references``.
Values that must never appear in a message carry the text ``SENTINEL``.
"""

# The tests share the element builders below, so they stay in one module.
# pylint: disable = too-many-lines

import copy
import io
import logging
import struct
import warnings

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import elements, file_layout
from pymedphys._dicom.deidentify.file_layout import ElementPath, reads_as_items

from . import _synthetic_references as synthetic

pytestmark = pytest.mark.pydicom

IMPLICIT = "1.2.840.10008.1.2"
EXPLICIT = "1.2.840.10008.1.2.1"
TRANSFER_SYNTAXES = pytest.mark.parametrize(
    "transfer_syntax", [IMPLICIT, EXPLICIT], ids=["implicit-vr", "explicit-vr"]
)

RT_ASSERTIONS = "(0044,0110)"
ASSERTION_UID = "(0044,0102)"
ASSERTER = "(0044,0103)"
PERSON_NAME = "(0040,A123)"
OBSERVER_TYPE = "(0040,A084)"
ASSERTION_UID_VALUE = "2.25.4401"
ASSERTER_NAME = "SYNTHETIC^ASSERTER"
SENTINEL = "SENTINEL"


def _tag(tag):
    return int(tag[1:5] + tag[6:10], 16)


def _path(*steps):
    """Return the path of the last tag, below each (sequence, item) before it."""
    return ElementPath(tuple(steps[:-1]), steps[-1])


def _read(dataset, path, codecs=elements.DEFAULT_CODECS):
    """Read the element at ``path`` as the engine's walker will.

    Each sequence on the path is read in turn, and each item's own Specific
    Character Set, if it has one, applies to its elements.
    """
    ancestors = ()
    for depth, (tag, index) in enumerate(path.items):
        sequence = elements.read_element(
            dataset, ElementPath(path.items[:depth], tag), codecs, ancestors
        )
        assert sequence.vr == "SQ"
        ancestors = (dataset, *ancestors)
        dataset = sequence.items[index]
        codecs = elements.dataset_codecs(dataset, codecs, path.items[: depth + 1])
    return elements.read_element(dataset, path, codecs, ancestors)


def _written_and_read(dataset, transfer_syntax):
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = transfer_syntax
    written = io.BytesIO()
    pydicom.dcmwrite(written, dataset, enforce_file_format=True)
    return pydicom.dcmread(io.BytesIO(written.getvalue()))


def _encoded(tag, value):
    """Return an element or item of defined length in Implicit VR Little Endian."""
    return struct.pack("<HHI", tag >> 16, tag & 0xFFFF, len(value)) + value


def _unknown(monkeypatch, tag, value):
    """Return an element whose VR is UN, whatever pydicom's dictionary knows."""
    with monkeypatch.context() as patch:
        patch.setattr(pydicom.config, "replace_un_with_known_vr", False)
        return pydicom.DataElement(tag, "UN", value)


def _raw(tag, vr, value, length=None):
    """Return an element as pydicom holds it before decoding it.

    It is from Implicit VR unless ``vr`` gives the VR that Explicit VR wrote.
    """
    return pydicom.dataelem.RawDataElement(
        pydicom.tag.Tag(_tag(tag)),
        vr,
        len(value) if length is None else length,
        value,
        0,
        vr is None,
        True,
    )


def _assertion(name=ASSERTER_NAME, **attributes):
    """Return an RT Assertions Sequence item, which pydicom 3.0.2 does not know."""
    asserter = synthetic.item(ObserverType="PSN", PersonName=name)
    assertion = synthetic.item(**attributes)
    assertion.add(synthetic.sequence(_tag(ASSERTER), [asserter]))
    assertion.add_new(_tag(ASSERTION_UID), "UI", ASSERTION_UID_VALUE)
    return assertion


def _plan_with_assertions(*assertions):
    dataset = synthetic.rt_plan()
    dataset.add(synthetic.sequence(_tag(RT_ASSERTIONS), list(assertions)))
    return dataset


ASSERTER_NAME_PATH = _path((RT_ASSERTIONS, 0), (ASSERTER, 0), PERSON_NAME)


@pytest.mark.deid_requirement("PS3.15-E.1.1-09")
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.filterwarnings("ignore:VR lookup failed:UserWarning")
def test_an_implicit_vr_rt_plan_decodes_rt_assertions_with_the_pinned_vr():
    read = _written_and_read(_plan_with_assertions(_assertion()), IMPLICIT)
    # From Implicit VR, pydicom holds the sequence it does not know as bytes.
    assert read.get_item(_tag(RT_ASSERTIONS), keep_deferred=True).VR is None

    sequence = _read(read, _path(RT_ASSERTIONS))
    uid = _read(read, _path((RT_ASSERTIONS, 0), ASSERTION_UID))
    name = _read(read, ASSERTER_NAME_PATH)

    assert (sequence.vr, len(sequence.items), sequence.values) == ("SQ", 1, ())
    assert (uid.vr, uid.values) == ("UI", (ASSERTION_UID_VALUE,))
    assert (name.vr, name.values) == ("PN", (ASSERTER_NAME,))
    # Reading does not change the data set, and pydicom alone reads UN.
    assert isinstance(
        read.get_item(_tag(RT_ASSERTIONS), keep_deferred=True),
        pydicom.dataelem.RawDataElement,
    )
    assert read[_tag(RT_ASSERTIONS)].VR == "UN"


@pytest.mark.deid_requirement("PS3.15-E.1.1-09")
@pytest.mark.usefixtures("pydicom_behaviour")
def test_un_in_explicit_vr_is_decoded_as_implicit_vr_with_the_pinned_vr(
    monkeypatch,
):
    # PS3.5 Section 6.2.2: a UN value is Implicit VR Little Endian, whatever
    # the transfer syntax. Patient's Name is one pydicom knows.
    # A UID of odd length has a trailing NUL (PS3.5 Section 9.1).
    uid = ASSERTION_UID_VALUE.encode() + b"\x00"
    items = _encoded(0xFFFEE000, _encoded(_tag(ASSERTION_UID), uid))
    dataset = synthetic.rt_plan()
    dataset[_tag(RT_ASSERTIONS)] = _unknown(monkeypatch, _tag(RT_ASSERTIONS), items)
    dataset[0x00100010] = _unknown(monkeypatch, 0x00100010, b"SYNTHETIC^UNKNOWN ")

    read = _written_and_read(dataset, EXPLICIT)

    assert read.get_item(0x00100010, keep_deferred=True).VR == "UN"
    name = _read(read, _path("(0010,0010)"))
    uid = _read(read, _path((RT_ASSERTIONS, 0), ASSERTION_UID))
    assert (name.vr, name.values) == ("PN", ("SYNTHETIC^UNKNOWN",))
    assert (uid.vr, uid.values) == ("UI", (ASSERTION_UID_VALUE,))


def _image(pixel_representation=None, **attributes):
    dataset = synthetic.ct_slice(0)
    if pixel_representation is not None:
        dataset.PixelRepresentation = pixel_representation
    for keyword, value in attributes.items():
        setattr(dataset, keyword, value)
    return dataset


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize("representation, vr, value", [(0, "US", 65535), (1, "SS", -1)])
def test_us_or_ss_is_resolved_from_pixel_representation(representation, vr, value):
    # Pixel Padding Value (0028,0120) at the top level, and the second value
    # of LUT Descriptor (0028,3002) in Modality LUT Sequence (0028,3000),
    # whose items take Pixel Representation from the data set that holds them.
    dataset = _image(representation)
    dataset[0x00280120] = _raw("(0028,0120)", None, b"\xff\xff")
    lut = pydicom.Dataset()
    lut[0x00283002] = _raw("(0028,3002)", None, b"\x00\x01\xff\xff\x10\x00")
    dataset.add(synthetic.sequence(0x00283000, [lut]))

    padding = _read(dataset, _path("(0028,0120)"))
    descriptor = _read(dataset, _path(("(0028,3000)", 0), "(0028,3002)"))

    assert (padding.vr, padding.values) == (vr, (value,))
    assert (descriptor.vr, descriptor.values[1]) == (vr, value)


@pytest.mark.usefixtures("pydicom_behaviour")
@TRANSFER_SYNTAXES
def test_us_or_ss_read_from_a_file_follows_pixel_representation(transfer_syntax):
    dataset = _image(1)
    dataset.add_new(0x00280120, "SS", -2)

    padding = _read(_written_and_read(dataset, transfer_syntax), _path("(0028,0120)"))

    assert (padding.vr, padding.values) == ("SS", (-2,))


@pytest.mark.parametrize(
    "representation",
    [None, b"\x02\x00", b"\x00\x00\x01\x00", b"\x01"],
    ids=["absent", "two", "two-values", "one-byte"],
)
def test_us_or_ss_without_a_pixel_representation_of_0_or_1_is_refused(
    representation,
):
    # The nearest data set that has Pixel Representation decides, so a valid
    # one in the data set that holds it does not count.
    dataset = _image(1)
    lut = pydicom.Dataset()
    if representation is not None:
        lut[0x00280103] = _raw("(0028,0103)", None, representation)
    lut[0x00283002] = _raw("(0028,3002)", None, b"\x00\x01\xff\xff\x10\x00")
    dataset.add(synthetic.sequence(0x00283000, [lut]))
    path = _path(("(0028,3000)", 0), "(0028,3002)")

    if representation is None:
        assert _read(dataset, path).vr == "SS"
        del dataset[0x00280103]
    with pytest.raises(elements.UndecodableElement) as raised:
        _read(dataset, path)

    assert str(raised.value) == (
        f"{path} has VR US or SS, and nothing in the data sets that hold it "
        "decides which, as Pixel Representation (0028,0103) would"
    )


@pytest.mark.parametrize(
    "tag, stated, attributes, rule",
    [
        ("(0028,0120)", "SS", {}, "Pixel Representation (0028,0103) decides VR US"),
        (
            "(0028,0120)",
            "US",
            {"PixelRepresentation": 1},
            "Pixel Representation (0028,0103) decides VR SS",
        ),
        (
            "(7FE0,0010)",
            "OB",
            {"BitsAllocated": 16},
            "Bits Allocated (0028,0100) decides VR OW",
        ),
    ],
    ids=["us-as-ss", "ss-as-us", "ow-as-ob"],
)
def test_a_vr_that_the_deciding_rule_contradicts_is_refused(
    tag, stated, attributes, rule
):
    # The pinned dictionary gives each VR, but not where the rule that
    # decides between them gives the other.
    dataset = _image(0, **attributes)
    dataset[_tag(tag)] = _raw(tag, stated, b"SENTINEL")

    with pytest.raises(elements.UndecodableElement) as raised:
        _read(dataset, _path(tag))

    assert raised.value.path == _path(tag)
    assert str(raised.value) == f"{tag} has VR {stated}, but {rule}"


VOI_LUT_DESCRIPTOR = _path(("(0028,3010)", 0), "(0028,3002)")
# 4096 entries, the first mapped -1024 as SS or 64512 as US, and 16 bits.
DESCRIPTOR = struct.pack("<HhH", 4096, -1024, 16)
DESCRIPTOR_VALUES = {"SS": (4096, -1024, 16), "US": (4096, 64512, 16)}
SECONDARY_CAPTURE_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.7"


def _voi_lut_image(descriptor, **changes):
    """Return a CT image whose VOI LUT Sequence item holds ``descriptor``.

    Its stored values are unsigned, 12 of 16 bits, and its output is in
    Hounsfield Units, as ``changes`` do not replace or, where None, remove.
    A value of bytes is held as an element that Implicit VR wrote, and a
    list as a sequence of copies of its items.
    """
    dataset = synthetic.ct_slice(0)
    attributes = {
        "BitsAllocated": 16,
        "BitsStored": 12,
        "HighBit": 11,
        "PixelRepresentation": 0,
        "RescaleIntercept": "-1024",
        "RescaleSlope": "1",
        "RescaleType": "HU",
        **changes,
    }
    for keyword, value in attributes.items():
        tag = pydicom.datadict.tag_for_keyword(keyword)
        if isinstance(value, bytes):
            dataset[tag] = _raw(f"({tag >> 16:04X},{tag & 0xFFFF:04X})", None, value)
        elif value is not None:
            setattr(dataset, keyword, copy.deepcopy(value))
    item = pydicom.Dataset()
    if descriptor is not None:
        item[0x00283002] = descriptor
    dataset.add(synthetic.sequence(0x00283010, [item]))
    return dataset


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.usefixtures("pydicom_behaviour")
@TRANSFER_SYNTAXES
def test_the_voi_lut_descriptor_of_a_ct_in_hounsfield_units_is_ss(transfer_syntax):
    # PS3.3 Section C.11.2.1.1: the second value is SS "if the possible
    # output range after application of the Rescale Slope and Intercept may
    # be signed", as Hounsfield Units always are, so Pixel Representation 0
    # does not decide it.
    dataset = _voi_lut_image(None)
    item = dataset.VOILUTSequence[0]
    item.add_new(0x00283002, "SS", [4096, -1024, 16])
    item.add_new(0x00283006, "US", [0] * 4096)

    read = _written_and_read(dataset, transfer_syntax)
    descriptor = _read(read, VOI_LUT_DESCRIPTOR)

    assert (descriptor.vr, descriptor.values) == ("SS", (4096, -1024, 16))


@pytest.mark.parametrize(
    "stated, changes",
    [
        ("SS", {}),
        ("US", {}),
        # Without rescale, Pixel Representation 0 would decide US.
        ("SS", {"RescaleIntercept": None, "RescaleSlope": None, "RescaleType": None}),
    ],
    ids=["ss", "us", "ss-without-rescale"],
)
def test_the_voi_lut_descriptor_takes_the_vr_that_explicit_vr_states(stated, changes):
    # In Explicit VR, "the explicit VR actually used is dictated by the VR
    # needed to represent the second Value" (PS3.3 Section C.11.2.1.1), so
    # the file decides, and the bytes are the same either way.
    dataset = _voi_lut_image(_raw("(0028,3002)", stated, DESCRIPTOR), **changes)

    descriptor = _read(dataset, VOI_LUT_DESCRIPTOR)

    assert (descriptor.vr, descriptor.values) == (stated, DESCRIPTOR_VALUES[stated])


_WITHOUT_RESCALE = {"RescaleIntercept": None, "RescaleSlope": None, "RescaleType": None}


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.parametrize("stated", [None, "UN"], ids=["implicit-vr", "un"])
@pytest.mark.parametrize(
    "changes, vr",
    [
        # Hounsfield Units are always signed (the Note in Section C.11.2.1.1).
        ({}, "SS"),
        ({"RescaleIntercept": "0"}, "SS"),
        # A CT Image leaves out Rescale Type only where it is HU (PS3.3
        # Table C.8-3), but another image does not say so.
        ({"RescaleType": None, "RescaleIntercept": "0"}, "SS"),
        (
            {
                "RescaleType": None,
                "RescaleIntercept": "0",
                "SOPClassUID": SECONDARY_CAPTURE_IMAGE_STORAGE,
            },
            "US",
        ),
        # Otherwise the output range of the stored values that Bits Stored and
        # Pixel Representation give decides (Section C.11.1.1.1).
        ({"RescaleType": None, "RescaleIntercept": "-1024"}, "SS"),
        ({"RescaleType": "US", "RescaleIntercept": "0"}, "US"),
        ({"RescaleType": "US", "RescaleIntercept": "-0.5"}, "SS"),
        ({"RescaleType": "US", "RescaleIntercept": "4095", "RescaleSlope": "-1"}, "US"),
        ({"RescaleType": "US", "RescaleIntercept": "4094", "RescaleSlope": "-1"}, "SS"),
        (
            {"RescaleType": "US", "RescaleIntercept": "2048", "PixelRepresentation": 1},
            "US",
        ),
        (
            {"RescaleType": "US", "RescaleIntercept": "2047", "PixelRepresentation": 1},
            "SS",
        ),
        # Without a Modality LUT or rescale, Pixel Representation decides.
        (_WITHOUT_RESCALE, "US"),
        ({**_WITHOUT_RESCALE, "PixelRepresentation": 1}, "SS"),
        # The output of a Modality LUT "is always unsigned" (C.11.1.1.1).
        (
            {
                **_WITHOUT_RESCALE,
                "PixelRepresentation": 1,
                "ModalityLUTSequence": [pydicom.Dataset()],
            },
            "US",
        ),
    ],
)
def test_without_a_vr_in_the_file_the_voi_lut_input_decides_its_descriptor(
    stated, changes, vr
):
    dataset = _voi_lut_image(_raw("(0028,3002)", stated, DESCRIPTOR), **changes)

    descriptor = _read(dataset, VOI_LUT_DESCRIPTOR)

    assert (descriptor.vr, descriptor.values) == (vr, DESCRIPTOR_VALUES[vr])


# 40000 entries, the first mapped -1024, and 16 bits; then 2**16 entries, which
# the first value gives as 0 (PS3.3 Sections C.11.1.1.1 and C.11.2.1.1).
LARGE_DESCRIPTORS = [(40000, -1024, 16), (0, -1024, 16), (65535, -32768, 16)]


@pytest.mark.parametrize("stated", ["SS", None, "UN"], ids=["ss", "implicit-vr", "un"])
@pytest.mark.parametrize("values", LARGE_DESCRIPTORS, ids=["40000", "65536", "65535"])
def test_the_first_and_third_values_of_an_ss_lut_descriptor_are_unsigned(
    stated, values
):
    # "the first and third values are always by definition interpreted as
    # unsigned", whichever VR the second needs (PS3.3 Section C.11.2.1.1).
    encoded = struct.pack("<HhH", *values)
    dataset = _voi_lut_image(_raw("(0028,3002)", stated, encoded))

    descriptor = _read(dataset, VOI_LUT_DESCRIPTOR)

    assert (descriptor.vr, descriptor.values) == ("SS", values)


@pytest.mark.parametrize("stated", ["SS", None], ids=["ss", "implicit-vr"])
def test_the_modality_lut_descriptor_keeps_its_first_value_unsigned(stated):
    # Section C.11.1.1.1 says the same of the Modality LUT's descriptor,
    # whose second value follows Pixel Representation.
    dataset = _voi_lut_image(None, **_WITHOUT_RESCALE, PixelRepresentation=1)
    item = pydicom.Dataset()
    item[0x00283002] = _raw("(0028,3002)", stated, struct.pack("<HhH", 40000, -2, 16))
    dataset.add(synthetic.sequence(0x00283000, [item]))

    descriptor = _read(dataset, _path(("(0028,3000)", 0), "(0028,3002)"))

    assert (descriptor.vr, descriptor.values) == ("SS", (40000, -2, 16))


@pytest.mark.usefixtures("pydicom_behaviour")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize("values", LARGE_DESCRIPTORS, ids=["40000", "65536", "65535"])
def test_an_ss_lut_descriptor_with_unsigned_values_is_written_and_read_back(
    transfer_syntax, values
):
    dataset = _voi_lut_image(None)
    item = dataset.VOILUTSequence[0]
    item[0x00283002] = elements.new_element(
        VOI_LUT_DESCRIPTOR, "SS", values, elements.DEFAULT_CODECS
    )
    item.add_new(0x00283006, "US", [0, 1])

    read = _written_and_read(dataset, transfer_syntax)
    descriptor = _read(read, VOI_LUT_DESCRIPTOR)
    stored = read.VOILUTSequence[0].get_item(0x00283002, keep_deferred=True).value

    assert stored == struct.pack("<HhH", *values)
    assert (descriptor.vr, descriptor.values) == ("SS", values)


@pytest.mark.parametrize(
    "vr, values",
    [
        ("SS", (65536, -1024, 16)),
        ("SS", (-1, -1024, 16)),
        ("SS", (4096, 32768, 16)),
        ("SS", (4096, -1024, 65536)),
        ("US", (4096, -1, 16)),
    ],
    ids=["first-too-large", "first-negative", "second-not-ss", "third", "us"],
)
def test_a_lut_descriptor_outside_its_ranges_is_not_built(vr, values):
    with pytest.raises(ValueError, match="value [1-3] is not"):
        elements.new_element(VOI_LUT_DESCRIPTOR, vr, values, elements.DEFAULT_CODECS)


PRESENTATION_LUT_DESCRIPTOR = _path(("(2050,0010)", 0), "(0028,3002)")


@pytest.mark.parametrize("stated", [None, "UN", "US"], ids=["implicit-vr", "un", "us"])
def test_the_presentation_lut_descriptor_is_us(stated):
    # "The Value Representation of the second Value is always US" (PS3.3
    # Section C.11.4.1), whatever Pixel Representation says.
    dataset = _voi_lut_image(None, PixelRepresentation=1)
    item = pydicom.Dataset()
    item[0x00283002] = _raw("(0028,3002)", stated, struct.pack("<HHH", 4096, 0, 12))
    dataset.add(synthetic.sequence(0x20500010, [item]))

    descriptor = _read(dataset, PRESENTATION_LUT_DESCRIPTOR)

    assert (descriptor.vr, descriptor.values) == ("US", (4096, 0, 12))


def test_a_presentation_lut_descriptor_stated_as_ss_is_refused():
    dataset = _voi_lut_image(None)
    item = pydicom.Dataset()
    item[0x00283002] = _raw("(0028,3002)", "SS", struct.pack("<HHH", 4096, 0, 12))
    dataset.add(synthetic.sequence(0x20500010, [item]))

    with pytest.raises(elements.UndecodableElement, match="C.11.4.1 decides VR US"):
        _read(dataset, PRESENTATION_LUT_DESCRIPTOR)


@pytest.mark.parametrize(
    "changes",
    [
        {**_WITHOUT_RESCALE, "PixelRepresentation": None},
        {"RescaleType": "US", "PixelRepresentation": None},
        {"RescaleType": "US", "BitsStored": None},
        {"RescaleType": "US", "BitsStored": b"\x00\x00"},
        {"RescaleType": "US", "RescaleSlope": None},
        {"RescaleType": "US", "RescaleIntercept": b"SENTINEL"},
        {"RescaleType": "US", "RescaleIntercept": b"1\\2 "},
        {"RescaleType": "US", "RescaleIntercept": b""},
        # Whether the output is in HU is in doubt.
        {"RescaleType": b"", "RescaleIntercept": "0"},
        {"RescaleType": b"HU\\US ", "RescaleIntercept": "0"},
        # PS3.3 Table C.11-1b allows a Modality LUT Sequence only without
        # rescale, and with a single item.
        {"ModalityLUTSequence": [pydicom.Dataset()]},
        {**_WITHOUT_RESCALE, "ModalityLUTSequence": []},
        {
            **_WITHOUT_RESCALE,
            "ModalityLUTSequence": [pydicom.Dataset(), pydicom.Dataset()],
        },
        # The rescale of each frame of a multi-frame image is in a functional
        # group, which is not read here.
        {"SharedFunctionalGroupsSequence": [pydicom.Dataset()]},
    ],
    ids=[
        "no-pixel-representation",
        "rescale-without-pixel-representation",
        "no-bits-stored",
        "no-bits",
        "no-slope",
        "intercept-not-a-number",
        "two-intercepts",
        "empty-intercept",
        "empty-rescale-type",
        "two-rescale-types",
        "modality-lut-and-rescale",
        "modality-lut-without-items",
        "modality-lut-with-two-items",
        "functional-groups",
    ],
)
def test_a_voi_lut_descriptor_whose_input_is_not_decided_is_refused(changes):
    dataset = _voi_lut_image(_raw("(0028,3002)", None, DESCRIPTOR), **changes)

    with pytest.raises(elements.UndecodableElement) as raised:
        _read(dataset, VOI_LUT_DESCRIPTOR)

    assert raised.value.path == VOI_LUT_DESCRIPTOR
    assert str(raised.value) == (
        f"{VOI_LUT_DESCRIPTOR} has VR US or SS, and nothing in the data sets "
        "that hold it decides which, as PS3.3 Section C.11.2.1.1 would"
    )


@pytest.mark.parametrize(
    "tag, stated, attributes, expected",
    [
        # PS3.5 Section A.1: in Implicit VR, Pixel Data and Overlay Data are OW.
        ("(7FE0,0010)", None, {"BitsAllocated": 8}, "OW"),
        ("(6002,3000)", None, {}, "OW"),
        # LUT Data is US or OW in either; its bytes are the same.
        ("(0028,3006)", None, {}, "OW"),
        # Section A.2: in Explicit VR, Pixel Data is OW where Bits Allocated
        # is more than 8, and either where it is 8 or less, as Overlay Data is.
        ("(7FE0,0010)", "OW", {"BitsAllocated": 16}, "OW"),
        ("(7FE0,0010)", "OB", {"BitsAllocated": 8}, "OB"),
        ("(7FE0,0010)", "OW", {"BitsAllocated": 8}, "OW"),
        ("(6002,3000)", "OB", {}, "OB"),
        ("(0028,3006)", "US", {}, "US"),
    ],
)
def test_ob_or_ow_follows_the_transfer_syntax_and_bits_allocated(
    tag, stated, attributes, expected
):
    dataset = _image(0, **attributes)
    dataset[_tag(tag)] = _raw(tag, stated, b"\x01\x02\x03\x04")

    element = _read(dataset, _path(tag))

    assert element.vr == expected
    assert element.values == (
        (0x0201, 0x0403) if expected == "US" else (b"\x01\x02\x03\x04",)
    )


def test_encapsulated_pixel_data_is_ob():
    # PS3.5 Section A.4: encapsulated Pixel Data has undefined length and VR
    # OB, whatever Bits Allocated is.
    fragments = struct.pack("<HHI", 0xFFFE, 0xE000, 0) + struct.pack(
        "<HHI", 0xFFFE, 0xE0DD, 0
    )
    dataset = _image(0, BitsAllocated=16)
    dataset[0x7FE00010] = _raw("(7FE0,0010)", "OB", fragments, 0xFFFFFFFF)

    assert _read(dataset, _path("(7FE0,0010)")).values == (fragments,)
    dataset[0x7FE00010] = _raw("(7FE0,0010)", "OW", fragments, 0xFFFFFFFF)
    with pytest.raises(elements.UndecodableElement) as raised:
        _read(dataset, _path("(7FE0,0010)"))
    assert str(raised.value) == (
        "(7FE0,0010) has VR OW, but encapsulation (PS3.5 Section A.4) decides VR OB"
    )


@pytest.mark.deid_requirement("PS3.15-E.1.1-09")
@pytest.mark.parametrize(
    "tag, stated",
    [
        ("(0028,3006)", "SS"),
        # Patient ID is LO in the pinned dictionary.
        ("(0010,0020)", "SH"),
        ("(0010,0020)", "UT"),
    ],
)
def test_a_vr_that_conflicts_with_the_pinned_dictionary_is_refused(tag, stated):
    dataset = _image(0)
    dataset[_tag(tag)] = _raw(tag, stated, b"SENTINEL")

    with pytest.raises(elements.UndecodableElement) as raised:
        _read(dataset, _path(tag))

    assert raised.value.path == _path(tag)
    assert str(raised.value) == (
        f"{tag} has VR {stated}, which the pinned data dictionary does not give it"
    )


@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_vr_written_in_a_file_that_conflicts_is_refused():
    dataset = synthetic.rt_plan()
    dataset.add_new(0x00100020, "SH", "SENTINEL")

    read = _written_and_read(dataset, EXPLICIT)

    with pytest.raises(elements.UndecodableElement, match="VR SH, which the pinned"):
        _read(read, _path("(0010,0020)"))


@pytest.mark.parametrize(
    "tag, expected",
    [
        ("(6002,3000)", "OB or OW"),  # Overlay Data, in a repeating group
        ("(601E,0022)", "LO"),  # Overlay Description
        ("(6020,3000)", None),  # beyond the repeating groups 6000-601E
        ("(6001,3000)", None),  # private
        ("(0028,0410)", "US"),  # a masked element, (0028,04x0)
        ("(0010,0010)", "PN"),
    ],
)
def test_the_pinned_dictionary_masks_only_its_repeating_groups(tag, expected):
    attribute = elements.dictionary_attribute(tag)
    dataset = pydicom.Dataset()
    dataset[_tag(tag)] = _raw(tag, None, b"AB")

    assert (attribute.vr if attribute else None) == expected
    # The reader of a written file's layout finds the same.
    assert file_layout._dictionary_vrs(tag) == (  # pylint: disable = protected-access
        attribute.vrs if attribute else ()
    )
    # Without a VR in the dictionary or the file, the value is kept as bytes;
    # with one in the file, it is decoded with that VR.
    if expected is None:
        assert _read(dataset, _path(tag)).values == (b"AB",)
        dataset[_tag(tag)] = _raw(tag, "LO", b"AB")
        assert _read(dataset, _path(tag)).values == ("AB",)


@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.filterwarnings("ignore:VR lookup failed:UserWarning")
@TRANSFER_SYNTAXES
def test_an_item_level_character_set_applies_to_its_item(transfer_syntax):
    # PS3.5 Section 7.5.3: an item's own Specific Character Set applies to it,
    # and to the items it holds; otherwise the enclosing data set's applies.
    greek = "ΣΥΝΘΕΤΙΚΟ^ΟΝΟΜΑ"
    latin = "MÜLLER^JÜRGEN"
    utf8 = _assertion(greek, SpecificCharacterSet="ISO_IR 192")
    inherited = _assertion(latin)
    dataset = _plan_with_assertions(utf8, inherited)
    dataset.SpecificCharacterSet = "ISO_IR 100"
    dataset.PatientName = "SØRENSEN^ÅSE"
    read = _written_and_read(dataset, transfer_syntax)
    codecs = elements.dataset_codecs(read)

    top = _read(read, _path("(0010,0010)"), codecs)
    first = _read(read, ASSERTER_NAME_PATH, codecs)
    second = _read(read, _path((RT_ASSERTIONS, 1), (ASSERTER, 0), PERSON_NAME), codecs)

    assert codecs == ("latin_1",)
    assert (top.values, top.codecs) == (("SØRENSEN^ÅSE",), ("latin_1",))
    assert (first.values, first.codecs) == ((greek,), ("UTF8",))
    assert (second.values, second.codecs) == ((latin,), ("latin_1",))


@pytest.mark.parametrize(
    "value, codecs",
    [
        (None, elements.DEFAULT_CODECS),
        ("", elements.DEFAULT_CODECS),
        ("ISO_IR 6", elements.DEFAULT_CODECS),
        ("ISO_IR 100", ("latin_1",)),
        ("ISO_IR 192", ("UTF8",)),
        ("GB18030", ("GB18030",)),
        (["", "ISO 2022 IR 87"], ("iso8859", "iso2022_jp")),
        (["ISO 2022 IR 100", "ISO 2022 IR 126"], ("latin_1", "iso_ir_126")),
    ],
)
def test_a_specific_character_set_gives_its_codecs(value, codecs):
    dataset = pydicom.Dataset()
    if value is not None:
        dataset.SpecificCharacterSet = value

    assert elements.dataset_codecs(dataset, ("inherited",)) == (
        ("inherited",) if value is None else codecs
    )


# The Defined Terms of PS3.3 Section C.12.1.1.2 in 2026d, but ISO_IR 203 and
# ISO 2022 IR 203, which pydicom 3.0 cannot decode.
DEFINED_TERMS = [
    *(f"ISO_IR {n}" for n in (100, 101, 109, 110, 126, 127, 13, 138, 144, 148, 166)),
    *(f"ISO 2022 IR {n}" for n in (6, 100, 101, 109, 110, 126, 127, 13, 138, 144)),
    *(f"ISO 2022 IR {n}" for n in (148, 166, 87, 159, 149, 58)),
    *("ISO_IR 192", "GB18030", "GBK"),
]


@pytest.mark.parametrize("term", DEFINED_TERMS)
def test_each_defined_term_that_pydicom_decodes_is_accepted(term):
    dataset = pydicom.Dataset()
    dataset[0x00080005] = _raw("(0008,0005)", None, term.encode())

    codecs = elements.dataset_codecs(dataset)

    assert codecs == (pydicom.charset.python_encoding[term],)
    assert "".encode(codecs[0]) == b""


@pytest.mark.parametrize(
    "value",
    [
        "ISO_IR 203",  # Defined Terms that pydicom 3.0 cannot decode
        "ISO 2022 IR 203",
        # ISO_IR 6, which names the Default Character Repertoire, is accepted
        # only alone: with code extensions, it is ISO 2022 IR 6.
        ["ISO_IR 6", "ISO 2022 IR 87"],
        ["ISO 2022 IR 100", "ISO_IR 6"],
        "ISO-IR 100",
        "SENTINEL",
        ["ISO_IR 192", "ISO 2022 IR 100"],  # UTF-8 has no code extensions
        ["ISO 2022 IR 100", "ISO_IR 100"],
        ["ISO 2022 IR 100", ""],
    ],
)
def test_an_unsupported_character_set_is_refused(value):
    encoded = "\\".join([value] if isinstance(value, str) else value).encode()
    item = pydicom.Dataset()
    item[0x00080005] = _raw("(0008,0005)", None, encoded)
    items = ((RT_ASSERTIONS, 2),)

    with pytest.raises(elements.UndecodableElement) as raised:
        elements.dataset_codecs(item, elements.DEFAULT_CODECS, items)

    assert raised.value.path == ElementPath(items, "(0008,0005)")
    assert "Specific Character Set" in str(raised.value)
    assert SENTINEL not in str(raised.value)
    assert not isinstance(raised.value, ValueError)


def test_a_specific_character_set_not_in_the_default_repertoire_is_refused():
    item = pydicom.Dataset()
    item[0x00080005] = _raw("(0008,0005)", None, "ISO_IR 1ØØ".encode("latin-1"))

    with pytest.raises(elements.UndecodableElement, match="Specific Character Set"):
        elements.dataset_codecs(item)


@pytest.mark.usefixtures("pydicom_behaviour")
@TRANSFER_SYNTAXES
def test_iso_ir_6_gives_the_default_character_repertoire(transfer_syntax):
    # PS3.3 Section C.12.1.1.2 gives the Default Character Repertoire by the
    # absence of a value, but real data often names it ISO_IR 6.
    dataset = synthetic.rt_plan()
    dataset.SpecificCharacterSet = "ISO_IR 6"
    read = _written_and_read(dataset, transfer_syntax)

    codecs = elements.dataset_codecs(read)
    name = _read(read, _path("(0010,0010)"), codecs)

    assert codecs == elements.DEFAULT_CODECS
    assert (name.values, name.codecs) == ((synthetic.PATIENTS_NAME,), codecs)


@pytest.mark.parametrize("in_memory", [False, True], ids=["raw", "in-memory"])
@pytest.mark.parametrize(
    "value",
    [None, "", "ISO_IR 6", "ISO 2022 IR 6"],
    ids=["absent", "empty", "ISO_IR 6", "ISO 2022 IR 6"],
)
def test_a_byte_outside_the_default_character_repertoire_is_refused(value, in_memory):
    # The Default Character Repertoire is ISO 646 (PS3.5 Section 6.1.2.1),
    # whose bytes are below 0x80, but pydicom reads it as ISO 8859-1. Text
    # set in memory is checked as text.
    dataset = pydicom.Dataset()
    if value is not None:
        dataset[0x00080005] = _raw("(0008,0005)", None, value.encode())
    dataset[0x00100010] = _raw("(0010,0010)", None, b"SENTINEL^REN\xc9 ")
    if in_memory:
        dataset[0x00100010] = pydicom.DataElement(0x00100010, "PN", "SENTINEL^RENÉ")
    codecs = elements.dataset_codecs(dataset)

    with pytest.raises(elements.OutsideDefaultRepertoire) as raised:
        _read(dataset, _path("(0010,0010)"), codecs)

    assert codecs == elements.DEFAULT_CODECS
    assert raised.value.path == _path("(0010,0010)")
    assert "Default Character Repertoire" in str(raised.value)
    assert SENTINEL not in str(raised.value) and SENTINEL not in repr(raised.value)
    assert raised.value.__cause__ is None

    # Where its rule removes or replaces it, it is read as ISO 8859-1, as
    # decided on 1 October 2026.
    read = elements.read_element(
        dataset, _path("(0010,0010)"), codecs, outside_repertoire_as_latin_1=True
    )
    assert read.values == ("SENTINEL^RENÉ",)


@pytest.mark.parametrize(
    "encoded, expected",
    [
        (b"SENTINEL\x1b(B\xe9XYZ ", ("SENTINEL\x1b(B\xe9XYZ",)),
        (b"SENTINEL\x1b(BXYZ ", ("SENTINEL\x1b(BXYZ",)),
        (b" SENTINEL\\\xe9 ", ("SENTINEL", "\xe9")),
    ],
    ids=["escape-and-latin-1", "escape-alone", "values"],
)
def test_text_outside_iso_646_is_read_as_latin_1_from_its_bytes(encoded, expected):
    # Before pydicom interprets an escape sequence, which the Default
    # Character Repertoire alone does not allow (PS3.5 Section 6.1.2.5.3),
    # and with the leading and trailing spaces that LO disregards removed.
    dataset = pydicom.Dataset()
    dataset[0x00081030] = _raw("(0008,1030)", None, encoded)

    with pytest.raises(elements.OutsideDefaultRepertoire):
        _read(dataset, _path("(0008,1030)"))
    read = elements.read_element(
        dataset,
        _path("(0008,1030)"),
        elements.DEFAULT_CODECS,
        outside_repertoire_as_latin_1=True,
    )
    assert read.values == expected


@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.filterwarnings("ignore:VR lookup failed:UserWarning")
@TRANSFER_SYNTAXES
def test_an_item_whose_character_set_is_iso_ir_6_takes_the_default_repertoire(
    transfer_syntax,
):
    # pydicom writes ISO_IR 6 text as ISO 8859-1, so É becomes the byte 0xC9.
    default = _assertion(SpecificCharacterSet="ISO_IR 6")
    beyond = _assertion(f"{SENTINEL}^RENÉ", SpecificCharacterSet="ISO_IR 6")
    dataset = _plan_with_assertions(default, beyond)
    dataset.SpecificCharacterSet = "ISO_IR 100"
    dataset.PatientName = "SØRENSEN^ÅSE"
    read = _written_and_read(dataset, transfer_syntax)
    codecs = elements.dataset_codecs(read)
    beyond_path = _path((RT_ASSERTIONS, 1), (ASSERTER, 0), PERSON_NAME)

    top = _read(read, _path("(0010,0010)"), codecs)
    asserter = _read(read, ASSERTER_NAME_PATH, codecs)
    with pytest.raises(elements.UndecodableElement) as raised:
        _read(read, beyond_path, codecs)

    assert (top.values, top.codecs) == (("SØRENSEN^ÅSE",), ("latin_1",))
    assert (asserter.values, asserter.codecs) == (
        (ASSERTER_NAME,),
        elements.DEFAULT_CODECS,
    )
    assert raised.value.path == beyond_path
    assert "Default Character Repertoire" in str(raised.value)
    assert SENTINEL not in str(raised.value) and SENTINEL not in repr(raised.value)


@pytest.mark.parametrize(
    "tag, vr, value",
    [
        ("(300A,00C8)", None, b"SENTINEL"),  # an IS that is not a number
        ("(300A,00C8)", None, b"1.5 "),  # an IS that pydicom reads as a float
        ("(300A,0084)", None, b"SENTINEL"),  # a DS that is not a number
        ("(300A,0084)", None, b"1.0\\SENTINEL"),
        ("(0028,0010)", None, b"\x01\x02\x03"),  # a US of three bytes
        ("(0028,0010)", "UN", b"\x01"),
        ("(0010,0010)", None, b"\x1b(XSENTINEL"),  # an unknown escape sequence
        ("(0010,0010)", "PN", b"SENTINEL"),  # shorter than its length
    ],
)
def test_a_value_that_does_not_decode_as_its_vr_is_refused_without_quoting_it(
    tag, vr, value
):
    dataset = pydicom.Dataset()
    length = 16 if vr == "PN" else None  # a file that ends inside the value
    dataset[_tag(tag)] = _raw(tag, vr, value, length)

    with pytest.raises(elements.UndecodableElement) as raised:
        _read(dataset, _path(tag))

    assert raised.value.path == _path(tag)
    assert SENTINEL not in str(raised.value) and SENTINEL not in repr(raised.value)
    # No exception from pydicom, whose message could quote the value, is chained.
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None or raised.value.__suppress_context__


def test_text_that_does_not_decode_in_its_character_set_is_refused():
    dataset = pydicom.Dataset()
    dataset.SpecificCharacterSet = "ISO_IR 192"
    dataset[0x00100010] = _raw("(0010,0010)", None, b"SENTINEL\xff^NAME")

    with pytest.raises(elements.UndecodableElement, match="could not be decoded"):
        _read(dataset, _path("(0010,0010)"), elements.dataset_codecs(dataset))


@pytest.mark.deid_requirement("PS3.15-E.1.1-09")
@pytest.mark.parametrize(
    "character_set, tag, value",
    [
        # Where Value 1 is the Default Character Repertoire with code
        # extensions, ISO 646 is active, with no G1 set, until an escape
        # sequence (PS3.5 Section 6.1.2.5.4), but pydicom decodes a byte
        # there as ISO 8859-1.
        (b"\\ISO 2022 IR 87", "(0010,0010)", b"SENTINEL\xdc^REN\xc9"),
        (b"ISO 2022 IR 6\\ISO 2022 IR 87", "(0010,0010)", b"SENTINEL\xdc^REN\xc9"),
        (b"\\ISO 2022 IR 100", "(0010,0010)", b"SENTINEL\xdc^REN\xc9"),
        (b"\\ISO 2022 IR 100", "(0008,1030)", b"SENTINEL\xdc"),
        (b"ISO 2022 IR 6\\ISO 2022 IR 100", "(0008,1030)", b"SENTINEL\xdc"),
        # pydicom would write this character without its escape sequence.
        (b"\\ISO 2022 IR 100", "(0008,1030)", b"SENTINEL\x1b-A\xdc"),
        # ISO_IR 13 is single-byte: JIS X 0201, not the kanji of Shift JIS.
        (b"ISO_IR 13", "(0010,0010)", "SENTINEL^山田".encode("shift_jis")),
    ],
    ids=[
        "ir-87",
        "ir-6-ir-87",
        "ir-100-pn",
        "ir-100-lo",
        "ir-6-ir-100-lo",
        "ir-100-escaped",
        "ir-13-kanji",
    ],
)
def test_text_that_could_not_be_written_back_is_refused(character_set, tag, value):
    # Reading is no more lenient than writing: what written_value_problem
    # finds in the decoded text, the reader refuses.
    dataset = pydicom.Dataset()
    dataset[0x00080005] = _raw("(0008,0005)", None, character_set)
    dataset[_tag(tag)] = _raw(tag, None, value)
    codecs = elements.dataset_codecs(dataset)
    vr = elements.dictionary_attribute(tag).vr
    decoded = pydicom.values.convert_value(vr, dataset.get_item(_tag(tag)), codecs)

    with pytest.raises(elements.UndecodableElement) as raised:
        _read(dataset, _path(tag), codecs)

    assert elements.written_value_problem(vr, "1", [str(decoded)], codecs)
    assert raised.value.path == _path(tag)
    assert str(raised.value) == (
        f"{tag} could not be written back as VR {vr}, since value 1 cannot be "
        "encoded in the data set's Specific Character Set"
    )
    assert SENTINEL not in repr(raised.value)


@pytest.mark.usefixtures("pydicom_behaviour")
@TRANSFER_SYNTAXES
def test_text_in_a_character_set_with_code_extensions_is_read(transfer_syntax):
    name = "YAMADA^TARO=山田^太郎=やまだ^たろう"
    dataset = synthetic.rt_plan()
    dataset.SpecificCharacterSet = ["", "ISO 2022 IR 87"]
    dataset.PatientName = name
    dataset.StudyDescription = "SYNTHETIC 研究"
    read = _written_and_read(dataset, transfer_syntax)
    codecs = elements.dataset_codecs(read)

    found = [
        _read(read, _path(tag), codecs).values for tag in ("(0010,0010)", "(0008,1030)")
    ]

    assert found == [(name,), ("SYNTHETIC 研究",)]


@pytest.mark.deid_requirement("PS3.15-E.1.1-09")
@pytest.mark.parametrize(
    "value",
    [
        b"SENTINEL",  # not an item
        # An item whose element is longer than the item.
        _encoded(0xFFFEE000, struct.pack("<HHI", 0x0010, 0x0010, 16) + b"SENTINEL"),
        # An item longer than the value.
        struct.pack("<HHI", 0xFFFE, 0xE000, 64) + _encoded(0x00100010, b"SENTINEL"),
        # Elements in an item whose tags do not increase (PS3.5 Section 7.1).
        _encoded(
            0xFFFEE000,
            _encoded(0x00100020, b"SENTINEL") + _encoded(0x00100010, b"SENTINEL"),
        ),
    ],
    ids=["not-an-item", "element-past-item", "item-past-value", "tags-out-of-order"],
)
def test_a_sequence_whose_items_cannot_be_read_is_refused(monkeypatch, value):
    # pydicom reads each of these without complaint, losing what follows.
    dataset = pydicom.Dataset()
    dataset[_tag(RT_ASSERTIONS)] = _unknown(monkeypatch, _tag(RT_ASSERTIONS), value)

    with pytest.raises(elements.UndecodableElement, match="items that cannot be"):
        _read(dataset, _path(RT_ASSERTIONS))
    assert not reads_as_items(value, explicit=False)


def test_an_unknown_value_set_in_memory_is_decoded_with_the_pinned_vr(
    monkeypatch,
):
    dataset = pydicom.Dataset()
    dataset[0x00100010] = _unknown(monkeypatch, 0x00100010, b"SYNTHETIC^NAME")

    assert _read(dataset, _path("(0010,0010)")).values == ("SYNTHETIC^NAME",)


def test_an_absent_element_is_a_key_error():
    with pytest.raises(KeyError):
        elements.read_element(
            pydicom.Dataset(), _path("(0010,0010)"), elements.DEFAULT_CODECS
        )


@pytest.mark.parametrize(
    "value, explicit",
    [
        (b"", False),
        (_encoded(0xFFFEE000, _encoded(0x00100010, b"AB")), False),
        (_encoded(0xFFFEE000, struct.pack("<HH", 0x10, 0x10) + b"PN\x02\x00AB"), True),
        # An item of undefined length, with its delimiter.
        (
            struct.pack("<HHI", 0xFFFE, 0xE000, 0xFFFFFFFF)
            + _encoded(0x00100010, b"AB")
            + struct.pack("<HHI", 0xFFFE, 0xE00D, 0),
            False,
        ),
    ],
)
def test_a_sequence_value_that_holds_only_items_reads_as_items(value, explicit):
    assert reads_as_items(value, explicit=explicit)


def _accessed(dataset, tag, access):
    """Access an element through pydicom, which decodes it in place."""
    number = _tag(tag)
    if access == "index":
        return dataset[number]
    if access == "get":
        return dataset.get(number)
    if access == "attribute":
        return getattr(dataset, pydicom.datadict.keyword_for_tag(number))
    return list(dataset)


ACCESSES = pytest.mark.parametrize("access", ["index", "get", "attribute", "iteration"])


@pytest.mark.deid_requirement("PS3.15-E.1.1-09")
@pytest.mark.usefixtures("pydicom_behaviour")
@ACCESSES
def test_a_un_sequence_that_pydicom_has_decoded_is_refused(monkeypatch, access):
    # Elements in an item whose tags do not increase (PS3.5 Section 7.1), in
    # Referenced Study Sequence written as UN. pydicom reads its items when
    # the element is accessed, without complaint.
    item = _encoded(_tag("(0008,1155)"), b"2.25.2\x00") + _encoded(
        _tag("(0008,1150)"), b"1.2.3\x00"
    )
    dataset = synthetic.rt_plan()
    dataset[0x00081110] = _unknown(monkeypatch, 0x00081110, _encoded(0xFFFEE000, item))
    read = _written_and_read(dataset, EXPLICIT)
    path = _path("(0008,1110)")

    with pytest.raises(elements.UndecodableElement, match="items that cannot be"):
        _read(read, path)
    _accessed(read, "(0008,1110)", access)
    with pytest.raises(elements.UndecodableElement) as raised:
        _read(read, path)

    assert read[0x00081110].VR == "SQ"
    assert str(raised.value) == (
        f"{path} was decoded by pydicom before it was read here, so its "
        "encoded value cannot be checked"
    )


@pytest.mark.usefixtures("pydicom_behaviour")
@ACCESSES
def test_a_vr_that_pydicom_has_chosen_is_refused(access):
    # Without Pixel Representation, nothing decides whether Smallest Image
    # Pixel Value is US or SS, but pydicom chooses one as it decodes it.
    dataset = synthetic.rt_plan()
    dataset[0x00280106] = _raw("(0028,0106)", None, b"\xff\xff")
    read = _written_and_read(dataset, IMPLICIT)
    path = _path("(0028,0106)")

    with pytest.raises(elements.UndecodableElement, match="nothing in the data"):
        _read(read, path)
    _accessed(read, "(0028,0106)", access)
    with pytest.raises(elements.UndecodableElement, match="decoded by pydicom"):
        _read(read, path)


@pytest.mark.usefixtures("pydicom_behaviour")
@TRANSFER_SYNTAXES
def test_what_dcmread_decodes_itself_is_read(transfer_syntax):
    # dcmread decodes Specific Character Set, and reads a sequence of
    # undefined length as items, before anything accesses them.
    dataset = _plan_with_assertions(_assertion())
    dataset.SpecificCharacterSet = "ISO_IR 100"
    dataset[_tag(RT_ASSERTIONS)].is_undefined_length = True
    read = _written_and_read(dataset, transfer_syntax)
    held = read.get_item(_tag(RT_ASSERTIONS), keep_deferred=True)
    assert isinstance(held, pydicom.DataElement) and held.is_undefined_length

    codecs = elements.dataset_codecs(read)
    name = _read(read, ASSERTER_NAME_PATH, codecs)

    assert codecs == ("latin_1",)
    assert (name.vr, name.values) == ("PN", (ASSERTER_NAME,))


@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_deferred_value_is_refused():
    dataset = synthetic.rt_plan()
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = EXPLICIT
    written = io.BytesIO()
    pydicom.dcmwrite(written, dataset, enforce_file_format=True)
    deferred = pydicom.dcmread(io.BytesIO(written.getvalue()), defer_size=4)

    with pytest.raises(elements.UndecodableElement, match="deferred"):
        _read(deferred, _path("(0010,0010)"))


@pytest.mark.parametrize(
    "tag, vr, value, expected",
    [
        ("(0008,1070)", "PN", ["A^B", "", "C^D"], ("A^B", "", "C^D")),
        ("(0010,0010)", "PN", "A^B", ("A^B",)),
        ("(0010,0020)", "LO", "", ()),
        ("(0028,0010)", "US", None, ()),
        ("(7FE0,0010)", "OB", b"", ()),
        ("(7FE0,0010)", "OB", b"\x01\x02", (b"\x01\x02",)),
    ],
)
def test_values_are_normalised_into_a_tuple(tag, vr, value, expected):
    dataset = _image(0, BitsAllocated=8)
    dataset[_tag(tag)] = pydicom.DataElement(_tag(tag), vr, value)

    element = _read(dataset, _path(tag))

    assert element.values == expected
    assert all(type(each) in (str, int, bytes) for each in element.values)


def test_a_person_name_set_as_text_is_read_as_text():
    # pydicom keeps the text given it as already converted.
    dataset = pydicom.Dataset()
    dataset[0x00100010] = pydicom.DataElement(
        0x00100010, "PN", "A^B", already_converted=True
    )

    assert _read(dataset, _path("(0010,0010)")).values == ("A^B",)


def test_numbers_and_number_strings_are_plain_python_values():
    dataset = pydicom.Dataset()
    dataset[0x00280030] = _raw("(0028,0030)", None, b"1.50\\2e1 ")  # DS
    dataset[0x300A00C8] = _raw("(300A,00C8)", None, b" 7")  # IS
    # A DS and an IS with an empty value between two others.
    dataset[0x00081160] = _raw("(0008,1160)", None, b"1\\\\2 ")
    dataset[0x30060050] = _raw("(3006,0050)", None, b"1.5\\\\2 ")
    dataset[0x00209165] = _raw("(0020,9165)", None, b"\x10\x00\x10\x00")  # AT
    dataset[0x00189306] = _raw("(0018,9306)", None, struct.pack("<d", 1.5))  # FD

    found = {
        tag: _read(dataset, _path(tag)).values
        for tag in (
            "(0028,0030)",
            "(300A,00C8)",
            "(0020,9165)",
            "(0018,9306)",
            "(0008,1160)",
            "(3006,0050)",
        )
    }

    assert found == {
        "(0028,0030)": ("1.50", "2e1"),
        "(300A,00C8)": ("7",),
        "(0020,9165)": (0x00100010,),
        "(0018,9306)": (1.5,),
        "(0008,1160)": ("1", "", "2"),
        "(3006,0050)": ("1.5", "", "2"),
    }
    assert [type(each[0]) for each in found.values()] == [str, str, int, float] + [
        str
    ] * 2


@pytest.mark.parametrize(
    "tag, vr", [("(0028,0010)", "US"), ("(0018,9306)", "FD"), ("(7FE0,0010)", "OB")]
)
def test_a_number_or_bytes_value_of_another_type_is_refused(tag, vr):
    # pydicom keeps such a value as given when its own checks are off.
    dataset = _image(0, BitsAllocated=8)
    dataset[_tag(tag)] = pydicom.DataElement(
        _tag(tag), vr, "SENTINEL", validation_mode=pydicom.config.IGNORE
    )

    with pytest.raises(elements.UndecodableElement, match=f"as VR {vr}"):
        _read(dataset, _path(tag))


def test_an_element_value_shows_only_its_path_and_vr():
    dataset = pydicom.Dataset()
    dataset.PatientName = "SENTINEL^NAME"

    element = _read(dataset, _path("(0010,0010)"))

    assert repr(element) == "ElementValue(path='(0010,0010)', vr='PN')"
    assert SENTINEL not in repr(element) and SENTINEL not in str(element)


def _sentinel_inputs():
    """Return data sets whose decoding makes pydicom report a SENTINEL value."""
    invalid_is = pydicom.Dataset()
    invalid_is[0x300A00C8] = _raw("(300A,00C8)", None, b"7SENTINEL")
    invalid_text = pydicom.Dataset()
    invalid_text.SpecificCharacterSet = "ISO_IR 192"
    invalid_text[0x00100010] = _raw("(0010,0010)", None, b"SENTINEL\xff")
    return [(invalid_is, "(300A,00C8)"), (invalid_text, "(0010,0010)")]


def test_diagnostics_hold_no_value(caplog, capsys, monkeypatch):
    monkeypatch.setattr(pydicom.config, "debugging", True)
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="pydicom")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for dataset, tag in _sentinel_inputs():
            codecs = elements.dataset_codecs(dataset)
            with pytest.raises(elements.UndecodableElement):
                elements.read_element(dataset, _path(tag), codecs)

    output = capsys.readouterr()
    reported = [str(each.message) for each in caught]
    reported += [record.getMessage() for record in caplog.records]
    reported += [output.out, output.err]
    assert caplog.records  # pydicom did report a problem
    assert not [each for each in reported if SENTINEL in each]


# Each attribute, its VR, and values in the form read_element gives them.
WRITTEN = [
    ("(0010,0010)", "PN", ("SYNTHÉTIQUE^PATIENT",)),
    ("(0010,0020)", "LO", ("SYNTH-0001",)),
    ("(0008,1030)", "LO", ()),
    ("(300A,0084)", "DS", ("1.50",)),
    ("(0028,0030)", "DS", ("0.5", "0.25")),
    ("(300A,00C8)", "IS", ("12",)),
    ("(0028,0120)", "SS", (-2,)),
    ("(0028,0010)", "US", (512,)),
    ("(0028,0009)", "AT", (0x00100010, 0x7FE00010)),
    ("(0018,9306)", "FD", (1.5,)),
    ("(0008,0018)", "UI", ("2.25.12345",)),
    ("(0008,0020)", "DA", ("20250102",)),
    ("(0008,0060)", "CS", ("RTPLAN",)),
    ("(7FE0,0010)", "OW", (b"\x01\x00\x02\x00",)),
    ("(300A,0002)", "SH", ("PLAN",)),
]


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.filterwarnings("ignore:VR lookup failed:UserWarning")
@TRANSFER_SYNTAXES
def test_written_elements_carry_the_pinned_vr_and_round_trip(transfer_syntax):
    codecs = ("latin_1",)
    dataset = synthetic.rt_plan()
    dataset.SpecificCharacterSet = "ISO_IR 100"
    dataset.PixelRepresentation = 1
    dataset.BitsAllocated = 16
    for tag, vr, values in WRITTEN:
        dataset[_tag(tag)] = elements.new_element(_path(tag), vr, values, codecs)
    asserter = pydicom.Dataset()
    asserter[_tag(PERSON_NAME)] = elements.new_element(
        _path(PERSON_NAME), "PN", (ASSERTER_NAME,), codecs
    )
    assertion = pydicom.Dataset()
    for tag, vr, values in [
        (ASSERTION_UID, "UI", (ASSERTION_UID_VALUE,)),
        (ASSERTER, "SQ", (asserter,)),
    ]:
        assertion[_tag(tag)] = elements.new_element(_path(tag), vr, values, codecs)
    dataset[_tag(RT_ASSERTIONS)] = elements.new_element(
        _path(RT_ASSERTIONS), "SQ", (assertion,), codecs
    )

    read = _written_and_read(dataset, transfer_syntax)

    for tag, vr, values in WRITTEN:
        element = _read(read, _path(tag), codecs)
        assert (tag, element.vr, element.values) == (tag, vr, values)
    name = _read(read, ASSERTER_NAME_PATH, codecs)
    assert (name.vr, name.values) == ("PN", (ASSERTER_NAME,))


def test_a_new_element_is_built_without_pydicoms_checks():
    # The engine checks every value itself before building the element, so
    # pydicom has no reason to warn, and quote the value, when it is set.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        element = elements.new_element(
            _path("(300A,0084)"), "DS", ("1.5",), elements.DEFAULT_CODECS
        )
    assert element.validation_mode == pydicom.config.IGNORE
    assert (element.VR, str(element.value)) == ("DS", "1.5")


@pytest.mark.deid_requirement("MIDI-BP-03")
@pytest.mark.parametrize(
    "tag, vr, values, codecs, problem",
    [
        ("(0008,0020)", "DA", ("20250230",), ("iso8859",), "is not a valid DA"),
        ("(0010,0020)", "LO", ("SENTINEL\\X",), ("iso8859",), "is not a valid LO"),
        # Ω is not in ISO 8859-1, and é is not in the default repertoire.
        ("(0010,0020)", "LO", ("SENTINELΩ",), ("latin_1",), "cannot be encoded"),
        ("(0010,0020)", "LO", ("SENTINELé",), ("iso8859",), "cannot be encoded"),
        # pydicom would write é in ISO 8859-1, without the escape sequence of
        # ISO 2022 IR 100, where Value 1 is the Default Character Repertoire.
        (
            "(0010,0020)",
            "LO",
            ("SENTINELé",),
            ("iso8859", "latin_1"),
            "cannot be encoded",
        ),
        # ISO_IR 13 is single-byte: JIS X 0201, not the kanji of Shift JIS.
        ("(0010,0020)", "LO", ("SENTINEL山",), ("shift_jis",), "cannot be encoded"),
        # Each character is one byte in JIS X 0201, but pydicom writes the
        # whole value with replacement characters.
        ("(0010,0020)", "LO", ("SENTINELｱ",), ("shift_jis",), "cannot be encoded"),
        # JIS X 0201 puts the yen sign at 05/12, the backslash of ISO 646,
        # which would split the value in two (PS3.5 Section 6.1.2.3), even
        # with a second character set that pydicom does not choose for it.
        ("(0010,0020)", "LO", ("SENTINEL¥",), ("shift_jis",), "cannot be encoded"),
        (
            "(0010,0020)",
            "LO",
            ("SENTINEL¥",),
            ("shift_jis", "latin_1"),
            "cannot be encoded",
        ),
        ("(0010,0010)", "PN", ("SENTINEL^¥",), ("shift_jis",), "cannot be encoded"),
        # PS3.5 Section 6.2.1.2: in UTF-8, the first component group holds
        # code points up to U+1FFF and a few Japanese punctuation marks and
        # kana only, and no code extensions are used in it.
        ("(0010,0010)", "PN", ("山田^SENTINEL",), ("UTF8",), "first component group"),
        (
            "(0010,0010)",
            "PN",
            ("\u3042^SENTINEL",),  # HIRAGANA LETTER A
            ("iso8859", "iso2022_jp"),
            "first component group",
        ),
    ],
)
def test_a_written_value_problem_is_described_without_quoting_it(
    tag, vr, values, codecs, problem
):
    attribute = elements.dictionary_attribute(tag)

    found = elements.written_value_problem(vr, attribute.vm, values, codecs)

    assert problem in found and SENTINEL not in found
    with pytest.raises(ValueError, match=problem) as raised:
        elements.new_element(_path(tag), vr, values, codecs)
    assert SENTINEL not in str(raised.value)


@pytest.mark.parametrize(
    "vr, values, codecs",
    [
        ("PN", ("YAMADA^TARO=山田^太郎=やまだ^たろう",), ("iso8859", "iso2022_jp")),
        ("PN", ("Ελληνικό^Όνομα",), ("UTF8",)),  # Greek is below U+1FFF
        ("PN", ("ｱｲ^ｳｴ",), ("shift_jis",)),
        # Katakana, and the ideographic comma, which the first group allows.
        ("PN", ("\u30a2\u30a4^\u3001",), ("UTF8",)),
        ("LO", ("Ωmega",), ("iso_ir_126",)),
        ("LO", ("A\u00e9\u3042",), ("latin_1", "iso2022_jp")),
        ("PN", ("SMITH^JOHN",), ("iso8859",)),
    ],
)
def test_a_written_value_in_its_character_set_has_no_problem(vr, values, codecs):
    assert elements.written_value_problem(vr, "1", values, codecs) is None


@pytest.mark.parametrize(
    "tag, vr",
    [("(0010,0010)", "LO"), ("(0028,0120)", "OW"), ("(0009,1010)", "LO")],
    ids=["not-the-pinned-vr", "not-an-alternative", "not-in-the-dictionary"],
)
def test_a_new_element_takes_only_a_vr_the_pinned_dictionary_gives(tag, vr):
    with pytest.raises(ValueError, match="pinned data dictionary"):
        elements.new_element(_path(tag), vr, (), elements.DEFAULT_CODECS)


def test_a_new_sequence_takes_only_data_sets_as_items():
    with pytest.raises(ValueError, match="data sets as its items"):
        elements.new_element(
            _path(RT_ASSERTIONS), "SQ", ("SENTINEL",), elements.DEFAULT_CODECS
        )


@pytest.mark.usefixtures("pydicom_behaviour")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize(
    "character_set, codecs, value",
    [
        ("ISO_IR 13", ("shift_jis",), "SENTINELｱ"),
        ("ISO_IR 13", ("shift_jis",), "SENTINEL¥"),
        (["ISO 2022 IR 13", "ISO 2022 IR 100"], ("shift_jis", "latin_1"), "SENTINEL¥"),
    ],
    ids=["latin-and-kana", "yen", "two-character-sets"],
)
def test_text_that_the_writer_would_change_is_refused_before_writing(
    transfer_syntax, character_set, codecs, value
):
    # Written as pydicom would write it, each value reads back changed: with
    # a replacement character, or split in two at the yen sign's byte.
    dataset = synthetic.rt_plan()
    dataset.SpecificCharacterSet = character_set
    dataset.add(
        pydicom.DataElement(
            0x0008103E, "LO", value, validation_mode=pydicom.config.IGNORE
        )
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        read = _written_and_read(dataset, transfer_syntax)

    assert read.get(0x0008103E).value != value
    with pytest.raises(ValueError, match="cannot be encoded") as raised:
        elements.new_element(_path("(0008,103E)"), "LO", (value,), codecs)
    assert SENTINEL not in str(raised.value)


@pytest.mark.usefixtures("pydicom_behaviour")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize(
    "character_set, codecs, value",
    [
        ("ISO_IR 13", ("shift_jis",), "ｱｲｳ"),
        ("ISO_IR 100", ("latin_1",), "Ångström"),
        (["", "ISO 2022 IR 87"], ("iso8859", "iso2022_jp"), "PLAN 表"),
    ],
    ids=["kana", "latin-1", "jis-x-0208"],
)
def test_text_that_the_writer_keeps_is_built_and_read_back(
    transfer_syntax, character_set, codecs, value
):
    dataset = synthetic.rt_plan()
    dataset.SpecificCharacterSet = character_set
    dataset[0x0008103E] = elements.new_element(
        _path("(0008,103E)"), "LO", (value,), codecs
    )

    read = _written_and_read(dataset, transfer_syntax)

    assert _read(read, _path("(0008,103E)"), codecs).values == (value,)
