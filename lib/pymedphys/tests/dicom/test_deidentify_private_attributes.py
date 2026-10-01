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

"""The removal of private attributes under the Basic Profile."""

# The tests share the plan, the encoded values, and the invented values
# below, so they stay in one module.
# pylint: disable = too-many-lines

import copy
import dataclasses
import io
import struct
import traceback

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import policy, private_attributes
from pymedphys._dicom.deidentify.file_layout import ElementPath

PRIVATE_ROW = "(gggg,eeee) where gggg is odd"
IMPLICIT_VR = "1.2.840.10008.1.2"
EXPLICIT_VR = "1.2.840.10008.1.2.1"
RT_PLAN_STORAGE = "1.2.840.10008.5.1.4.1.1.481.5"
# Sequences of the pinned data dictionary that pydicom 3.0.2 does not know,
# so that it reads them from Implicit VR Little Endian as UN.
RT_ASSERTIONS_SEQUENCE = 0x00440110
DOSE_CALCULATION_MODEL_SEQUENCE = 0x30040080
# Sequences that pydicom 3.0.2 knows.
BEAM_SEQUENCE = 0x300A00B0
CONCEPT_NAME_CODE_SEQUENCE = 0x0040A043
EQUIVALENT_CODE_SEQUENCE = 0x00080121
ITEM = 0xFFFEE000
ITEM_DELIMITER = 0xFFFEE00D
SEQUENCE_DELIMITER = 0xFFFEE0DD
# Invented values, which no error message or path may quote.
PRIVATE_VALUE = "SYNTHETIC PRIVATE VALUE"
PATIENT_ID = "SYNTHETIC-7Q2K"
CODE_MEANING = "Prüfung"  # not ASCII, so its encoding matters
UNKNOWN_CHARACTER_SET = "SITE-XYZ"
# A Defined Term of the same length, written in its place and then replaced,
# since pydicom does not write an unknown character set without a warning.
PLACEHOLDER_CHARACTER_SET = "ISO_IR 6"
# Read as an element's tag, its first bytes give an even group, so that a
# private element with this value, read as an item, holds no odd group.
PRIVATE_TEXT = b"PRIVATE TEXT"

# The private attributes of _plan(), in the order the data set holds them.
PLAN_PATHS = [
    "(0009,0010)",  # a private creator
    "(0009,1001)",  # its private data element
    "(0009,1002)",  # a private sequence, removed with its items
    "(0019,0010)",  # a private creator that reserves a block with no elements
    "(0021,1001)",  # a private data element whose block has no creator
    "(300A,00B0)[0] > (300B,0010)",
    "(300A,00B0)[0] > (300B,1001)",
    "(300A,00B0)[1] > (300A,0111)[0] > (300B,0010)",
    "(300A,00B0)[1] > (300A,0111)[0] > (300B,1002)",
]


@pytest.fixture(name="basic", scope="module")
def fixture_basic():
    return policy.compose_policy("basic")


def _private(dataset, group, creator, elements):
    """Reserve block 0x10 of ``group`` for ``creator`` and add its elements."""
    dataset.add_new((group << 16) | 0x0010, "LO", creator)
    for element, vr, value in elements:
        dataset.add_new((group << 16) | 0x1000 | element, vr, value)


def _plan():
    """Return an RT Plan with private attributes at the top level and nested."""
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = RT_PLAN_STORAGE
    dataset.SOPInstanceUID = "2.25.401"
    dataset.PatientID = PATIENT_ID
    contents = pydicom.Dataset()
    contents.PatientID = PATIENT_ID
    _private(contents, 0x0011, "SYNTHETIC CREATOR B", [(0x01, "SH", "SYNTHETIC")])
    _private(
        dataset,
        0x0009,
        "SYNTHETIC CREATOR A",
        [(0x01, "LO", PRIVATE_VALUE), (0x02, "SQ", [contents])],
    )
    # Added out of order, to show that they are listed in the data set's order.
    dataset.add_new(0x00211001, "LO", PRIVATE_VALUE)
    dataset.add_new(0x00190010, "LO", "SYNTHETIC EMPTY BLOCK")
    first, second, control_point = (pydicom.Dataset() for _ in range(3))
    first.BeamNumber = 1
    _private(first, 0x300B, "SYNTHETIC CREATOR C", [(0x01, "DS", "1.5")])
    control_point.ControlPointIndex = 0
    _private(control_point, 0x300B, "SYNTHETIC CREATOR C", [(0x02, "LO", "SYN")])
    second.BeamNumber = 2
    second.ControlPointSequence = [control_point]
    dataset.BeamSequence = [first, second]
    return dataset


def _without(dataset, paths):
    """Return a deep copy of ``dataset`` without the elements at ``paths``."""
    result = copy.deepcopy(dataset)
    for path in paths:
        holder = result
        for tag, index in path.items:
            holder = holder[_number(tag)].value[index]
        del holder[_number(path.tag)]
    return result


def _number(tag):
    return int(tag[1:5] + tag[6:10], 16)


def _odd_groups(dataset):
    """Return every odd-group tag in ``dataset`` and the items of its sequences."""
    found = []
    for element in dataset:
        if element.tag.group % 2:
            found.append(element.tag)
        elif element.VR == "SQ":
            for item in element.value:
                found += _odd_groups(item)
    return found


def _written(dataset, transfer_syntax):
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = transfer_syntax
    written = io.BytesIO()
    pydicom.dcmwrite(written, dataset, enforce_file_format=True)
    return written.getvalue()


def _written_and_read(dataset, transfer_syntax):
    return pydicom.dcmread(io.BytesIO(_written(dataset, transfer_syntax)))


def _items(element):
    """Return the items of a sequence, decoding one that pydicom read as UN."""
    if element.VR == "UN":
        return pydicom.values.convert_SQ(element.value, True, True)
    return element.value


def _encoded(tag, value):
    """Return an element or item of defined length in Implicit VR Little Endian."""
    return struct.pack("<HHI", tag >> 16, tag & 0xFFFF, len(value)) + value


def _undefined_length(tag, value, delimiter):
    """Return an element or item of undefined length, ended by ``delimiter``."""
    header = struct.pack("<HHI", tag >> 16, tag & 0xFFFF, 0xFFFFFFFF)
    return header + value + _encoded(delimiter, b"")


def _item(value, undefined=False):
    """Return an item of defined or undefined length in Implicit VR Little Endian."""
    if undefined:
        return _undefined_length(ITEM, value, ITEM_DELIMITER)
    return _encoded(ITEM, value)


def _sequence(tag, value, undefined=False):
    """Return a sequence of defined or undefined length in Implicit VR Little Endian."""
    if undefined:
        return _undefined_length(tag, value, SEQUENCE_DELIMITER)
    return _encoded(tag, value)


def _holder(dataset, path):
    """Return the data set in ``dataset`` that holds the element at ``path``."""
    for tag, index in path.items:
        dataset = dataset[_number(tag)].value[index]
    return dataset


def _assert_refused(dataset, basic, path, value):
    """Assert that both functions refuse ``dataset`` by ``path``.

    Neither the message nor the traceback may quote ``value``.
    """
    for apply in (
        private_attributes.private_attribute_paths,
        private_attributes.without_private_attributes,
    ):
        with pytest.raises(private_attributes.PrivateAttributeError) as raised:
            apply(dataset, basic)
        assert raised.value.path == path
        assert str(path) in str(raised.value)
        assert value not in "".join(traceback.format_exception(raised.value))


def _unknown(monkeypatch, tag, value):
    """Return an element whose VR is UN, whatever pydicom's dictionary knows."""
    with monkeypatch.context() as patch:
        patch.setattr(pydicom.config, "replace_un_with_known_vr", False)
        return pydicom.DataElement(tag, "UN", value)


# Elements as Implicit VR Little Endian: Code Value (0008,0100); Code Meaning
# (0008,0104), in UTF-8; and a private block with one element.
CODE_VALUE = _encoded(0x00080100, b"AB")
MEANING = _encoded(0x00080104, CODE_MEANING.encode("utf-8") + b" ")
PRIVATE_BLOCK = _encoded(0x00110010, b"SYNTHETIC CREATOR D ") + _encoded(
    0x00111001, PRIVATE_VALUE.encode() + b" "
)
# The value of an RT Assertions Sequence of one item, which holds Code Meaning
# and the private block.
ASSERTION = _encoded(ITEM, MEANING + PRIVATE_BLOCK)
# Values that pydicom 3.0.2 reads as a sequence without an error, as items
# that leave out part of the value.
MALFORMED = {
    "an-element-without-an-item": _encoded(0x00111001, CODE_VALUE),
    "text-without-an-item": _encoded(0x00111001, PRIVATE_TEXT),
    "an-element-after-an-item": _item(CODE_VALUE) + _encoded(0x00111001, PRIVATE_TEXT),
    "item-too-short": struct.pack("<HHI", 0xFFFE, 0xE000, 4)
    + CODE_VALUE
    + _encoded(0x00111001, PRIVATE_TEXT),
    "not-items": b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a",
}


def _nested(value, depth, undefined=False):
    """Return an RT Assertions Sequence value whose items nest ``value``.

    Its item holds Code Meaning and Concept Name Code Sequence (0040,A043). At
    depth 1, that sequence has ``value``; at depth 2, it holds an item with
    Code Value and Equivalent Code Sequence (0008,0121), which has ``value``.
    The sequence with ``value`` is of defined length. With ``undefined``,
    every sequence and item that encloses it is of undefined length, and
    pydicom decodes such a sequence as it reads the value that holds it.
    """
    if depth == 1:
        nested = _encoded(CONCEPT_NAME_CODE_SEQUENCE, value)
    else:
        item = _item(CODE_VALUE + _encoded(EQUIVALENT_CODE_SEQUENCE, value), undefined)
        nested = _sequence(CONCEPT_NAME_CODE_SEQUENCE, item, undefined)
    return _item(MEANING + nested, undefined)


# The path of the sequence that has the value, at each depth of _nested().
NESTED_PATHS = {
    1: ElementPath((("(0044,0110)", 0),), "(0040,A043)"),
    2: ElementPath((("(0044,0110)", 0), ("(0040,A043)", 0)), "(0008,0121)"),
}


def test_the_basic_profile_removes_every_private_attribute(basic):
    dataset = _plan()

    paths = private_attributes.private_attribute_paths(dataset, basic)
    result = private_attributes.without_private_attributes(dataset, basic)

    assert all(isinstance(path, ElementPath) for path in paths)
    assert [str(path) for path in paths] == PLAN_PATHS
    assert _odd_groups(result) == []
    # Nothing else changes, in the copy or in the source.
    assert result == _without(_plan(), paths)
    assert dataset == _plan()


def test_a_private_sequence_is_removed_with_everything_in_it(basic):
    # X removes a sequence with all its items and their attributes (Table
    # E.1-1a), so the standard and private attributes in a private sequence
    # are removed with it, and only the sequence is listed.
    dataset = _plan()

    paths = private_attributes.private_attribute_paths(dataset, basic)
    result = private_attributes.without_private_attributes(dataset, basic)

    assert ElementPath((), "(0009,1002)") in paths
    assert not any(path.items[:1] == (("(0009,1002)", 0),) for path in paths)
    assert 0x00091002 not in result


@pytest.mark.parametrize(
    "tag",
    [
        0x00010010,  # groups that PS3.5 Section 7.8.1 excludes from private use
        0x00030010,
        0x00051000,
        0x00070001,
        0xFFFF0010,
        0x00090000,  # a private group length, retired (PS3.5 Section 7.2)
        0x00090001,  # elements that PS3.5 Section 7.8.1 does not allow
        0x0009000F,
        0x00090100,
        0x00090FFF,
        0x000900FF,  # the last private creator
        0x0009FFFF,  # the last element of the last block
    ],
    ids=lambda tag: f"{tag >> 16:04X},{tag & 0xFFFF:04X}",
)
def test_every_odd_group_element_is_removed(basic, tag):
    # Table E.1-1 gives every attribute "(gggg,eeee) where gggg is odd" X,
    # whether or not it is a valid private creator or private data element.
    dataset = pydicom.Dataset()
    dataset.PatientID = PATIENT_ID
    dataset.add_new(tag, "LO", PRIVATE_VALUE)
    item = copy.deepcopy(dataset)
    dataset.BeamSequence = [item]
    name = f"({tag >> 16:04X},{tag & 0xFFFF:04X})"

    paths = private_attributes.private_attribute_paths(dataset, basic)
    result = private_attributes.without_private_attributes(dataset, basic)

    assert sorted(str(path) for path in paths) == sorted(
        [name, f"(300A,00B0)[0] > {name}"]
    )
    assert _odd_groups(result) == []
    assert result.PatientID == result.BeamSequence[0].PatientID == PATIENT_ID


@pytest.mark.parametrize("preset", ["basic", "basic-clean-descriptors", "tps-import"])
def test_each_preset_without_retain_safe_private_removes_private_attributes(preset):
    composed = policy.compose_policy(preset)

    paths = private_attributes.private_attribute_paths(_plan(), composed)
    result = private_attributes.without_private_attributes(_plan(), composed)

    assert [str(path) for path in paths] == PLAN_PATHS
    assert _odd_groups(result) == []


@pytest.mark.parametrize(
    "composed",
    [
        lambda: policy.compose_policy("public-release"),
        lambda: policy.compose_custom_policy(["retain_safe_private"]),
    ],
    ids=["public-release", "custom"],
)
@pytest.mark.parametrize(
    "apply",
    [
        private_attributes.private_attribute_paths,
        private_attributes.without_private_attributes,
    ],
    ids=["paths", "copy"],
)
def test_retain_safe_private_is_refused(composed, apply):
    # The option keeps private attributes that are known to be safe, which
    # needs reviewed rules for which are, and none exist yet.
    with pytest.raises(policy.PolicyError, match="Retain Safe Private"):
        apply(_plan(), composed())


@pytest.mark.parametrize(
    "actions",
    [
        lambda actions: {**actions, PRIVATE_ROW: "C"},
        lambda actions: {**actions, PRIVATE_ROW: "K"},
        lambda actions: {
            tag: action for tag, action in actions.items() if tag != PRIVATE_ROW
        },
    ],
    ids=["clean", "keep", "missing"],
)
def test_a_policy_that_does_not_remove_private_attributes_is_refused(basic, actions):
    changed = dataclasses.replace(basic, actions=actions(dict(basic.actions)))

    with pytest.raises(policy.PolicyError, match="private attributes"):
        private_attributes.private_attribute_paths(_plan(), changed)
    with pytest.raises(policy.PolicyError, match="private attributes"):
        private_attributes.without_private_attributes(_plan(), changed)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "transfer_syntax", [IMPLICIT_VR, EXPLICIT_VR], ids=["implicit-vr", "explicit-vr"]
)
@pytest.mark.parametrize("undefined", [False, True], ids=["defined", "undefined"])
def test_private_attributes_read_from_a_file_are_removed(
    basic, transfer_syntax, undefined
):
    # From Implicit VR Little Endian, pydicom reads a private sequence of
    # defined length as UN, and one of undefined length as SQ.
    source = _plan()
    source[0x00091002].is_undefined_length = undefined
    read = _written_and_read(source, transfer_syntax)

    paths = private_attributes.private_attribute_paths(read, basic)
    result = private_attributes.without_private_attributes(read, basic)

    assert [str(path) for path in paths] == PLAN_PATHS
    written = _written_and_read(result, transfer_syntax)
    assert _odd_groups(written) == []
    assert written.PatientID == PATIENT_ID
    assert [beam.BeamNumber for beam in written.BeamSequence] == [1, 2]


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_finding_private_attributes_decodes_no_other_value(basic):
    # Read from Implicit VR Little Endian, each element stays raw until it is
    # decoded. Only sequences need decoding to find what they hold.
    read = _written_and_read(_plan(), IMPLICIT_VR)

    private_attributes.private_attribute_paths(read, basic)

    raw = pydicom.dataelem.RawDataElement
    for tag in [0x00090010, 0x00091001, 0x00091002, 0x00211001, 0x00100020]:
        assert isinstance(read.get_item(tag, keep_deferred=True), raw)
    beam = read.BeamSequence[0]
    for tag in [0x300B0010, 0x300B1001, 0x300A00C0]:
        assert isinstance(beam.get_item(tag, keep_deferred=True), raw)


@pytest.fixture(name="reading_validation", params=["default", "raise"])
def fixture_reading_validation(request, monkeypatch):
    """Read values with pydicom's default validation, then raising on errors.

    monkeypatch restores pydicom's setting afterwards. The public setter
    cannot restore its default, which follows another setting.
    """
    if request.param == "raise":
        monkeypatch.setattr(
            pydicom.config.settings, "_reading_validation_mode", pydicom.config.RAISE
        )
    return request.param


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour", "reading_validation")
@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize(
    "tag, value",
    [
        (0x00280010, b"\x01\x02\x03"),  # Rows, US, whose value has 2 bytes
        (0x00081155, b"2.25.SYNTHETIC"),  # Referenced SOP Instance UID, UI
        (0x00100010, b"SYNTHETIC^NAME"),  # Patient's Name, PN
    ],
    ids=["us-of-the-wrong-length", "invalid-ui", "pn"],
)
def test_an_unknown_value_read_from_explicit_vr_is_left_unless_a_sequence(
    monkeypatch, basic, tag, value
):
    # Explicit VR Little Endian can carry the value of any attribute with VR
    # UN. pydicom decodes one with its attribute's VR when it is read, which
    # can raise an error or warning that quotes the value, so only a value
    # that can hold items is decoded.
    source = _plan()
    source[tag] = _unknown(monkeypatch, tag, value)
    read = _written_and_read(source, EXPLICIT_VR)
    raw = read.get_item(tag, keep_deferred=True)
    assert isinstance(raw, pydicom.dataelem.RawDataElement)
    assert (raw.VR, raw.value) == ("UN", value)

    paths = private_attributes.private_attribute_paths(read, basic)
    result = private_attributes.without_private_attributes(read, basic)

    assert [str(path) for path in paths] == PLAN_PATHS
    # The element stays as it was read, in the source and in the copy.
    assert read.get_item(tag, keep_deferred=True) == raw
    assert result.get_item(tag, keep_deferred=True) == raw


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour", "reading_validation")
@pytest.mark.filterwarnings("error")
def test_a_sequence_read_from_explicit_vr_as_unknown_is_searched(monkeypatch, basic):
    # Explicit VR Little Endian can carry a sequence with VR UN, as Implicit
    # VR Little Endian (PS3.5 Section 6.2.2). pydicom decodes Beam Sequence,
    # which it knows, as it is read; RT Assertions Sequence it does not know.
    beams = _written_and_read(_plan(), IMPLICIT_VR).get_item(
        BEAM_SEQUENCE, keep_deferred=True
    )
    source = _plan()
    source.SpecificCharacterSet = "ISO_IR 192"
    source[BEAM_SEQUENCE] = _unknown(monkeypatch, BEAM_SEQUENCE, beams.value)
    source[RT_ASSERTIONS_SEQUENCE] = _unknown(
        monkeypatch, RT_ASSERTIONS_SEQUENCE, ASSERTION
    )
    read = _written_and_read(source, EXPLICIT_VR)
    for tag in [BEAM_SEQUENCE, RT_ASSERTIONS_SEQUENCE]:
        assert read.get_item(tag, keep_deferred=True).VR == "UN"

    paths = private_attributes.private_attribute_paths(read, basic)
    result = private_attributes.without_private_attributes(read, basic)

    assert [str(path) for path in paths] == [
        *PLAN_PATHS[:-4],
        "(0044,0110)[0] > (0011,0010)",
        "(0044,0110)[0] > (0011,1001)",
        *PLAN_PATHS[-4:],
    ]
    written = _written_and_read(result, EXPLICIT_VR)
    assert _odd_groups(written) == []
    assert [beam.BeamNumber for beam in written.BeamSequence] == [1, 2]
    assert written[RT_ASSERTIONS_SEQUENCE].value[0].CodeMeaning == CODE_MEANING


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_a_sequence_of_a_repeating_group_is_searched(basic):
    # The pinned dictionary lists the retired Curve Referenced Overlay
    # Sequence as (50xx,2600), and pydicom's dictionary gives it VR SQ in each
    # of its groups, so it is decoded when read from Implicit VR Little Endian.
    overlay = pydicom.Dataset()
    _private(overlay, 0x0011, "SYNTHETIC CREATOR E", [(0x01, "LO", PRIVATE_VALUE)])
    source = _plan()
    source.add_new(0x50002600, "SQ", [overlay])
    read = _written_and_read(source, IMPLICIT_VR)
    assert read.get_item(0x50002600, keep_deferred=True).VR is None

    paths = private_attributes.private_attribute_paths(read, basic)

    assert [str(path) for path in paths] == [
        *PLAN_PATHS,
        "(5000,2600)[0] > (0011,0010)",
        "(5000,2600)[0] > (0011,1001)",
    ]


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
def test_private_attributes_in_a_sequence_read_as_unknown_are_removed(
    monkeypatch, basic
):
    # PS3.5 Section 6.2.2 lets a reader that knows the VR of a UN value decode
    # it as Implicit VR Little Endian.
    dataset = _plan()
    dataset.SpecificCharacterSet = "ISO_IR 192"
    dataset[RT_ASSERTIONS_SEQUENCE] = _unknown(
        monkeypatch, RT_ASSERTIONS_SEQUENCE, ASSERTION
    )

    paths = private_attributes.private_attribute_paths(dataset, basic)
    result = private_attributes.without_private_attributes(dataset, basic)

    assert [str(path) for path in paths] == [
        *PLAN_PATHS[:-4],
        "(0044,0110)[0] > (0011,0010)",
        "(0044,0110)[0] > (0011,1001)",
        *PLAN_PATHS[-4:],
    ]
    assertions = result[RT_ASSERTIONS_SEQUENCE]
    assert assertions.VR == "SQ"
    assert _odd_groups(result) == []
    # The item keeps Code Meaning, decoded in the data set's character set.
    assert [list(item.keys()) for item in assertions.value] == [[0x00080104]]
    assert assertions.value[0].CodeMeaning == CODE_MEANING
    # The source keeps its encoded value.
    assert dataset[RT_ASSERTIONS_SEQUENCE].VR == "UN"
    assert dataset[RT_ASSERTIONS_SEQUENCE].value == ASSERTION


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "outer, inner",
    [("ISO_IR 192", None), ("ISO_IR 192", ""), (None, "ISO_IR 192")],
    ids=["inherited", "inherited-past-an-empty-one", "the-items-own"],
)
def test_a_sequence_read_as_unknown_takes_its_items_character_set(
    monkeypatch, basic, outer, inner
):
    # An item takes the character set of the data set that holds it, unless
    # it has a Specific Character Set of its own.
    dataset = _plan()
    beam = dataset.BeamSequence[1]
    if outer is not None:
        dataset.SpecificCharacterSet = outer
    if inner is not None:
        beam.SpecificCharacterSet = inner
    beam[DOSE_CALCULATION_MODEL_SEQUENCE] = _unknown(
        monkeypatch, DOSE_CALCULATION_MODEL_SEQUENCE, ASSERTION
    )

    result = private_attributes.without_private_attributes(dataset, basic)

    model = result.BeamSequence[1][DOSE_CALCULATION_MODEL_SEQUENCE]
    assert model.VR == "SQ"
    assert model.value[0].CodeMeaning == CODE_MEANING
    # Explicit VR Little Endian carries the VR, SQ, so the value is read back
    # as items, and its text as it was.
    written = _written_and_read(result, EXPLICIT_VR)
    assert _odd_groups(written) == []
    model = written.BeamSequence[1][DOSE_CALCULATION_MODEL_SEQUENCE]
    assert model.value[0].CodeMeaning == CODE_MEANING


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.filterwarnings("ignore:VR lookup failed:UserWarning")
def test_a_sequence_read_from_implicit_vr_as_unknown_is_searched(basic):
    # pydicom 3.0.2 reads an RT Assertions Sequence of defined length from
    # Implicit VR Little Endian as UN, since it does not know it; a pydicom
    # that knows it reads it as SQ. Either way, its private attributes are
    # found and removed.
    assertion = pydicom.Dataset()
    assertion.CodeMeaning = "SYNTHETIC"
    _private(assertion, 0x0011, "SYNTHETIC CREATOR D", [(0x01, "LO", PRIVATE_VALUE)])
    source = _plan()
    source.add(pydicom.DataElement(RT_ASSERTIONS_SEQUENCE, "SQ", [assertion]))
    read = _written_and_read(source, IMPLICIT_VR)

    paths = private_attributes.private_attribute_paths(read, basic)
    result = private_attributes.without_private_attributes(read, basic)

    assert "(0044,0110)[0] > (0011,1001)" in [str(path) for path in paths]
    written = _written_and_read(result, IMPLICIT_VR)
    assert [list(item.keys()) for item in _items(written[RT_ASSERTIONS_SEQUENCE])] == [
        [0x00080104]
    ]


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour", "reading_validation")
@pytest.mark.parametrize("reading_validation", ["raise"], indirect=True)
@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize(
    "path",
    [
        ElementPath((), "(0044,0110)"),
        ElementPath((("(300A,00B0)", 0),), "(3004,0080)"),
    ],
    ids=["top-level", "in-an-item"],
)
def test_a_sequence_that_pydicom_cannot_look_up_is_refused(basic, path):
    # Raising its validation errors, pydicom 3.0.2 raises KeyError for an
    # element read from Implicit VR Little Endian whose attribute its
    # dictionary does not list, such as RT Assertions Sequence (0044,0110)
    # or Dose Calculation Model Sequence (3004,0080).
    assertion = pydicom.Dataset()
    assertion.CodeMeaning = "SYNTHETIC"
    _private(assertion, 0x0011, "SYNTHETIC CREATOR D", [(0x01, "LO", PRIVATE_VALUE)])
    source = _plan()
    holder = source
    for tag, index in path.items:
        holder = holder[_number(tag)].value[index]
    holder.add(pydicom.DataElement(_number(path.tag), "SQ", [assertion]))
    read = _written_and_read(source, IMPLICIT_VR)

    for apply in (
        private_attributes.private_attribute_paths,
        private_attributes.without_private_attributes,
    ):
        with pytest.raises(private_attributes.PrivateAttributeError) as raised:
            apply(read, basic)
        assert raised.value.path == path
        assert str(path) in str(raised.value)
        assert "SYNTHETIC" not in str(raised.value)


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "value",
    [
        _encoded(ITEM, _encoded(0x00080104, b"SYNTHETIC ")),
        _item(MEANING, undefined=True),
        _item(MEANING) + _item(b""),
        _nested(b"", 1),
        _nested(_item(CODE_VALUE), 1),
        _nested(_item(CODE_VALUE, undefined=True), 1, undefined=True),
        _nested(_item(CODE_VALUE), 2),
        _nested(_item(CODE_VALUE, undefined=True), 2, undefined=True),
    ],
    ids=[
        "an-item",
        "an-item-of-undefined-length",
        "an-empty-item",
        "an-empty-nested-sequence",
        "a-nested-sequence",
        "a-nested-sequence-of-undefined-length",
        "nested-at-depth-2",
        "nested-at-depth-2-of-undefined-length",
    ],
)
def test_a_sequence_read_as_unknown_without_private_attributes_is_unchanged(
    monkeypatch, basic, value
):
    dataset = _plan()
    dataset[RT_ASSERTIONS_SEQUENCE] = _unknown(
        monkeypatch, RT_ASSERTIONS_SEQUENCE, value
    )

    paths = private_attributes.private_attribute_paths(dataset, basic)
    result = private_attributes.without_private_attributes(dataset, basic)

    assert [str(path) for path in paths] == PLAN_PATHS
    assert result[RT_ASSERTIONS_SEQUENCE].VR == "UN"
    assert result[RT_ASSERTIONS_SEQUENCE].value == value


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.parametrize(
    "undefined", [False, True], ids=["defined-length", "undefined-length"]
)
@pytest.mark.parametrize("depth", [1, 2], ids=["depth-1", "depth-2"])
def test_private_attributes_in_a_sequence_nested_in_an_unknown_value_are_removed(
    monkeypatch, basic, depth, undefined
):
    # A sequence nested in the items of a decoded UN value is searched too,
    # and its text decoded in the character set of the item that holds it.
    dataset = _plan()
    dataset.SpecificCharacterSet = "ISO_IR 192"
    innermost = _item(CODE_VALUE + MEANING + PRIVATE_BLOCK, undefined)
    value = _nested(innermost, depth, undefined)
    dataset[RT_ASSERTIONS_SEQUENCE] = _unknown(
        monkeypatch, RT_ASSERTIONS_SEQUENCE, value
    )
    within = f"{NESTED_PATHS[depth]}[0]"

    paths = private_attributes.private_attribute_paths(dataset, basic)
    result = private_attributes.without_private_attributes(dataset, basic)

    assert [str(path) for path in paths] == [
        *PLAN_PATHS[:-4],
        f"{within} > (0011,0010)",
        f"{within} > (0011,1001)",
        *PLAN_PATHS[-4:],
    ]
    assert _odd_groups(result) == []
    item = result[RT_ASSERTIONS_SEQUENCE].value[0]
    for tag, index in (*NESTED_PATHS[depth].items[1:], (NESTED_PATHS[depth].tag, 0)):
        item = item[_number(tag)].value[index]
    assert list(item.keys()) == [0x00080100, 0x00080104]
    assert item.CodeMeaning == CODE_MEANING
    # The source keeps its encoded value.
    assert dataset[RT_ASSERTIONS_SEQUENCE].value == value
    written = _written_and_read(result, EXPLICIT_VR)
    assert _odd_groups(written) == []


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "undefined", [False, True], ids=["defined-length", "undefined-length"]
)
@pytest.mark.parametrize("depth", [1, 2], ids=["depth-1", "depth-2"])
@pytest.mark.parametrize("value", list(MALFORMED.values()), ids=list(MALFORMED))
def test_a_malformed_sequence_nested_in_an_unknown_value_is_refused(
    monkeypatch, basic, value, depth, undefined
):
    # pydicom writes the elements of a decoded item as it read them, so a
    # sequence of defined length in one encodes to the same bytes however
    # pydicom decodes it. Its own items must encode it exactly too.
    dataset = _plan()
    dataset[RT_ASSERTIONS_SEQUENCE] = _unknown(
        monkeypatch, RT_ASSERTIONS_SEQUENCE, _nested(value, depth, undefined)
    )

    for apply in (
        private_attributes.private_attribute_paths,
        private_attributes.without_private_attributes,
    ):
        with pytest.raises(private_attributes.PrivateAttributeError) as raised:
            apply(dataset, basic)
        assert raised.value.path == NESTED_PATHS[depth]
        assert str(NESTED_PATHS[depth]) in str(raised.value)
        assert "PRIVATE" not in str(raised.value)


@pytest.mark.pydicom
def test_a_malformed_nested_sequence_is_refused_beside_private_attributes(
    monkeypatch, basic
):
    # Finding a private attribute in an item does not end the checks.
    nested = _encoded(CONCEPT_NAME_CODE_SEQUENCE, MALFORMED["text-without-an-item"])
    dataset = _plan()
    dataset[RT_ASSERTIONS_SEQUENCE] = _unknown(
        monkeypatch, RT_ASSERTIONS_SEQUENCE, _item(MEANING + PRIVATE_BLOCK + nested)
    )

    for apply in (
        private_attributes.private_attribute_paths,
        private_attributes.without_private_attributes,
    ):
        with pytest.raises(private_attributes.PrivateAttributeError) as raised:
            apply(dataset, basic)
        assert raised.value.path == NESTED_PATHS[1]


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "tag",
    [0x30040082, 0x0044FFF0],
    ids=["dictionary-cs", "not-in-dictionary"],
)
def test_an_unknown_value_is_decoded_only_where_the_dictionary_gives_sq(
    monkeypatch, basic, tag
):
    # Commissioning Status (3004,0082) is CS, and (0044,FFF0) is not in the
    # pinned dictionary, so neither value holds items to search, even when its
    # bytes read as items. The engine removes an attribute that the
    # dictionary does not list.
    dataset = _plan()
    dataset[tag] = _unknown(monkeypatch, tag, ASSERTION)

    paths = private_attributes.private_attribute_paths(dataset, basic)
    result = private_attributes.without_private_attributes(dataset, basic)

    assert [str(path) for path in paths] == PLAN_PATHS
    assert result[tag].VR == "UN"
    assert result[tag].value == ASSERTION


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "value",
    [
        b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a",
        _encoded(0x00111001, PRIVATE_VALUE.encode() + b" "),
        ASSERTION[:-6],
        ASSERTION + b"\x00\x00",
        struct.pack("<HHI", 0xFFFE, 0xE000, 100) + ASSERTION[8:],
        _encoded(ITEM, struct.pack("<HHI", 0x0011, 0x1001, 100) + b"SYNTHETIC "),
    ],
    ids=[
        "not-items",
        "an-element-without-an-item",
        "truncated",
        "trailing-bytes",
        "item-too-long",
        "element-too-long",
    ],
)
def test_an_unknown_value_that_cannot_be_read_as_items_is_refused(
    monkeypatch, basic, value
):
    # pydicom decodes some malformed values without an error, as items that
    # leave out part of the value, which could hold a private attribute.
    dataset = _plan()
    dataset.BeamSequence[0][RT_ASSERTIONS_SEQUENCE] = _unknown(
        monkeypatch, RT_ASSERTIONS_SEQUENCE, value
    )

    for apply in (
        private_attributes.private_attribute_paths,
        private_attributes.without_private_attributes,
    ):
        with pytest.raises(private_attributes.PrivateAttributeError) as raised:
            apply(dataset, basic)
        assert raised.value.path == ElementPath((("(300A,00B0)", 0),), "(0044,0110)")
        assert "(300A,00B0)[0] > (0044,0110)" in str(raised.value)
        assert "SYNTHETIC" not in str(raised.value)
        assert not isinstance(raised.value, ValueError)


@pytest.mark.pydicom
@pytest.mark.parametrize("value", [None, b""], ids=["none", "empty"])
def test_an_unknown_value_of_zero_length_has_no_items(monkeypatch, basic, value):
    # pydicom reads a UN element of zero length with the value None.
    dataset = _plan()
    dataset[RT_ASSERTIONS_SEQUENCE] = _unknown(
        monkeypatch, RT_ASSERTIONS_SEQUENCE, value
    )

    paths = private_attributes.private_attribute_paths(dataset, basic)
    result = private_attributes.without_private_attributes(dataset, basic)

    assert [str(path) for path in paths] == PLAN_PATHS
    assert result[RT_ASSERTIONS_SEQUENCE].value == value


@pytest.mark.pydicom
def test_a_sequence_that_pydicom_cannot_decode_is_refused(basic):
    # A Beam Sequence read from Explicit VR Little Endian, still raw, whose
    # value of three bytes is too short to hold an item.
    dataset = _plan()
    dataset[0x300A00B0] = pydicom.dataelem.RawDataElement(
        pydicom.tag.Tag(0x300A00B0), "SQ", 3, b"SYN", 0, False, True
    )

    for apply in (
        private_attributes.private_attribute_paths,
        private_attributes.without_private_attributes,
    ):
        with pytest.raises(private_attributes.PrivateAttributeError) as raised:
            apply(dataset, basic)
        assert raised.value.path == ElementPath((), "(300A,00B0)")
        assert "SYN" not in str(raised.value)


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour", "reading_validation")
@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize(
    "transfer_syntax", [IMPLICIT_VR, EXPLICIT_VR], ids=["implicit-vr", "explicit-vr"]
)
def test_an_unknown_character_set_in_an_item_read_from_a_file_is_refused(
    caplog, basic, transfer_syntax
):
    # pydicom reads the items of Beam Sequence as it decodes the sequence. It
    # reads the text of an item whose Specific Character Set it does not know
    # with its default encoding, warning and logging with the value, or,
    # raising its validation errors, raises an error that quotes it.
    source = _plan()
    source.BeamSequence[1].SpecificCharacterSet = PLACEHOLDER_CHARACTER_SET
    written = _written(source, transfer_syntax)
    placeholder = PLACEHOLDER_CHARACTER_SET.encode()
    assert written.count(placeholder) == 1
    read = pydicom.dcmread(
        io.BytesIO(written.replace(placeholder, UNKNOWN_CHARACTER_SET.encode()))
    )
    caplog.clear()

    _assert_refused(read, basic, ElementPath((), "(300A,00B0)"), UNKNOWN_CHARACTER_SET)
    assert UNKNOWN_CHARACTER_SET not in caplog.text


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour", "reading_validation")
@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize("depth", [0, 1], ids=["its-item", "a-nested-item"])
def test_an_unknown_character_set_in_an_item_of_an_unknown_value_is_refused(
    monkeypatch, caplog, basic, depth
):
    # The items of a UN value, and of each sequence nested in them, are
    # decoded here, with the character set that each item gives.
    character_set = _encoded(0x00080005, UNKNOWN_CHARACTER_SET.encode())
    if depth:
        value = _nested(_item(character_set + CODE_VALUE + MEANING), depth)
        path = NESTED_PATHS[depth]
    else:
        value = _item(character_set + MEANING + PRIVATE_BLOCK)
        path = ElementPath((), "(0044,0110)")
    dataset = _plan()
    dataset[RT_ASSERTIONS_SEQUENCE] = _unknown(
        monkeypatch, RT_ASSERTIONS_SEQUENCE, value
    )

    _assert_refused(dataset, basic, path, UNKNOWN_CHARACTER_SET)
    assert UNKNOWN_CHARACTER_SET not in caplog.text


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour", "reading_validation")
@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize(
    "value",
    [
        UNKNOWN_CHARACTER_SET,
        "latin_1",
        "ISO-IR 100",
        ["ISO_IR 192", "ISO 2022 IR 100"],
    ],
    ids=["unknown", "a-python-codec", "misspelt", "stand-alone-with-extensions"],
)
@pytest.mark.parametrize(
    "where, path",
    [
        (ElementPath((), "(0008,0005)"), ElementPath((), "(0008,0005)")),
        (
            ElementPath((("(300A,00B0)", 1),), "(0008,0005)"),
            ElementPath((), "(300A,00B0)"),
        ),
        (
            ElementPath((("(300A,00B0)", 1), ("(300A,0111)", 0)), "(0008,0005)"),
            ElementPath((("(300A,00B0)", 1),), "(300A,0111)"),
        ),
    ],
    ids=["top-level", "in-an-item", "in-a-nested-item"],
)
def test_a_character_set_that_pydicom_does_not_map_as_given_is_refused(
    caplog, basic, value, where, path
):
    # pydicom reads text in a Specific Character Set that is not one of its
    # terms, or that gives a code extension with a character set that allows
    # none, with another encoding than the one given. A character set in an
    # item is refused by the path of the sequence that holds the item.
    dataset = _plan()
    _holder(dataset, where).add(
        pydicom.DataElement(
            0x00080005, "CS", value, validation_mode=pydicom.config.IGNORE
        )
    )
    quoted = value if isinstance(value, str) else value[0]

    _assert_refused(dataset, basic, path, quoted)
    assert quoted not in caplog.text


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize(
    "vr, value",
    [
        ("US", b"SITE-XY"),
        ("FD", b"SITE-XYZ1"),
        ("SQ", b"SITE-XYZ"),
        ("DS", b"SITE-XYZ"),
    ],
    ids=["us-of-odd-length", "fd-of-odd-length", "sq", "ds"],
)
@pytest.mark.parametrize(
    "where, path",
    [
        (ElementPath((), "(0008,0005)"), ElementPath((), "(0008,0005)")),
        (
            ElementPath((("(300A,00B0)", 1),), "(0008,0005)"),
            ElementPath((), "(300A,00B0)"),
        ),
    ],
    ids=["top-level", "in-an-item"],
)
def test_a_character_set_stored_with_another_vr_is_refused(
    caplog, basic, vr, value, where, path
):
    # A raw Specific Character Set with a VR other than CS, in a data set
    # built in memory, is converted by pydicom when it is first accessed:
    # with a value that the VR cannot hold, pydicom raises an error of its own,
    # and otherwise it gives a value that is not a character set.
    dataset = _plan()
    _holder(dataset, where)[0x00080005] = pydicom.dataelem.RawDataElement(
        pydicom.tag.Tag(0x00080005), vr, len(value), value, 0, False, True
    )

    _assert_refused(dataset, basic, path, "SITE-XY")
    assert "SITE-XY" not in caplog.text


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour")
@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize(
    "value",
    ["ISO_IR 100", ["", "ISO 2022 IR 87"], ["ISO 2022 IR 6", "ISO 2022 IR 100"]],
    ids=["a-term", "code-extensions", "code-extensions-without-an-empty-value"],
)
def test_a_character_set_that_pydicom_maps_as_given_is_accepted(basic, value):
    dataset = _plan()
    dataset.BeamSequence[1].ControlPointSequence[0].SpecificCharacterSet = value

    paths = private_attributes.private_attribute_paths(dataset, basic)
    result = private_attributes.without_private_attributes(dataset, basic)

    assert [str(path) for path in paths] == PLAN_PATHS
    assert _odd_groups(result) == []


@pytest.mark.pydicom
@pytest.mark.usefixtures("pydicom_behaviour", "reading_validation")
@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize(
    "vr, value",
    [("OB", ASSERTION), ("UT", "SYNTHETIC TEXT")],
    ids=["ob", "ut"],
)
@pytest.mark.parametrize(
    "path",
    [
        ElementPath((), "(300A,00B0)"),
        ElementPath((("(300A,00B0)", 0),), "(0044,0110)"),
    ],
    ids=["top-level", "in-an-item"],
)
def test_a_sequence_stored_with_another_vr_is_refused(basic, vr, value, path):
    # Explicit VR Little Endian gives each element's VR. A sequence stored
    # with one other than SQ or UN is not read as items, so a private
    # attribute that it holds could not be found.
    source = _plan()
    _holder(source, path)[_number(path.tag)] = pydicom.DataElement(
        _number(path.tag), vr, value
    )
    read = _written_and_read(source, EXPLICIT_VR)
    raw = _holder(read, path).get_item(_number(path.tag), keep_deferred=True)
    assert raw.VR == vr

    _assert_refused(read, basic, path, "SYNTHETIC")
