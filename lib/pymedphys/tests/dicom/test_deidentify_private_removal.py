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

"""The removal of private attributes without Retain Safe Private, end to end.

The run's instance transform reads each source file's bytes, plans every
element by its rule, and writes the output, so these tests give it written
files and read what it writes. Every file is synthetic. Values that must
never reach the output carry the text ``SENTINEL``.
"""

import functools
import io
import struct

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.element_rules import ElementRules
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.source import SourceReason, read_source
from pymedphys._dicom.deidentify.walker import plan_instance

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
IMPLICIT_VR = synthetic.IMPLICIT_VR_LITTLE_ENDIAN
EXPLICIT_VR = synthetic.EXPLICIT_VR_LITTLE_ENDIAN
TRANSFER_SYNTAXES = pytest.mark.parametrize(
    "transfer_syntax", [IMPLICIT_VR, EXPLICIT_VR], ids=["implicit-vr", "explicit-vr"]
)
# RT Assertions Sequence (0044,0110), which the RT Plan IOD defines and the
# Basic Profile keeps, is in the pinned data dictionary, but pydicom 3.0.2
# does not know it, so it reads the sequence as UN.
RT_ASSERTIONS_SEQUENCE = 0x00440110
BEAM_SEQUENCE = 0x300A00B0
# Concept Name Code Sequence (0040,A043) and Equivalent Code Sequence
# (0008,0121), which the Basic Profile removes in RT Assertions Sequence.
CONCEPT_NAME_CODE_SEQUENCE = 0x0040A043
EQUIVALENT_CODE_SEQUENCE = 0x00080121
ITEM = 0xFFFEE000
ITEM_DELIMITER = 0xFFFEE00D
SEQUENCE_DELIMITER = 0xFFFEE0DD
UNKNOWN_CHARACTER_SET = b"SITE-XYZ"
SENTINEL = b"SENTINEL"
PRIVATE_TEXT = b"SENTINEL TXT"

# The private attributes of _plan(), in the order the data set holds them,
# each removed by its own rule.
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
PRIVATE_SEQUENCE = ElementPath((), "(0009,1002)")


@functools.lru_cache(maxsize=None)
def _transform():
    return InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)


def _transformed(data, record=None):
    """Return the transform's result for a written file.

    ``record`` is the file whose first-pass record to use, by default
    ``data``'s own.
    """
    return _transform()(data, InstanceRecord.from_file(record or data))


def _written_back(result):
    """Return the data set that a transformed instance's output holds."""
    assert isinstance(result, run.Transformed), getattr(result, "reasons", None)
    assert SENTINEL not in result.data
    return pydicom.dcmread(io.BytesIO(result.data))


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


def _private(dataset, group, creator, elements):
    """Reserve block 0x10 of ``group`` for ``creator`` and add its elements."""
    dataset.add_new((group << 16) | 0x0010, "LO", creator)
    for element, vr, value in elements:
        dataset.add_new((group << 16) | 0x1000 | element, vr, value)


def _plan():
    """Return an RT Plan with private attributes at the top level and nested."""
    dataset = synthetic.rt_plan()
    contents = pydicom.Dataset()
    contents.PatientID = "SENTINEL-ID"
    _private(contents, 0x0011, "SYNTHETIC CREATOR B", [(0x01, "SH", "SENTINEL B")])
    _private(
        dataset,
        0x0009,
        "SYNTHETIC CREATOR A",
        [(0x01, "LO", "SENTINEL A"), (0x02, "SQ", [contents])],
    )
    dataset.add_new(0x00211001, "LO", "SENTINEL NO CREATOR")
    dataset.add_new(0x00190010, "LO", "SENTINEL EMPTY BLOCK")
    first, second, control_point = (pydicom.Dataset() for _ in range(3))
    first.BeamNumber = 1
    _private(first, 0x300B, "SYNTHETIC CREATOR C", [(0x01, "DS", "1.5")])
    control_point.ControlPointIndex = 0
    _private(control_point, 0x300B, "SYNTHETIC CREATOR C", [(0x02, "LO", "SENTINEL C")])
    second.BeamNumber = 2
    second.ControlPointSequence = [control_point]
    dataset.BeamSequence = [first, second]
    return dataset


def _encoded(tag, value):
    """Return an element or item of defined length in Implicit VR Little Endian."""
    return struct.pack("<HHI", tag >> 16, tag & 0xFFFF, len(value)) + value


def _undefined_length(tag, value, delimiter):
    """Return an element or item of undefined length, ended by ``delimiter``."""
    header = struct.pack("<HHI", tag >> 16, tag & 0xFFFF, 0xFFFFFFFF)
    return header + value + _encoded(delimiter, b"")


def _item(value, undefined=False):
    if undefined:
        return _undefined_length(ITEM, value, ITEM_DELIMITER)
    return _encoded(ITEM, value)


def _sequence(tag, value, undefined=False):
    if undefined:
        return _undefined_length(tag, value, SEQUENCE_DELIMITER)
    return _encoded(tag, value)


def _unknown(monkeypatch, tag, value):
    """Return an element whose VR is UN, whatever pydicom's dictionary knows."""
    with monkeypatch.context() as patch:
        patch.setattr(pydicom.config, "replace_un_with_known_vr", False)
        return pydicom.DataElement(tag, "UN", value)


def _items(element):
    """Return the items of a sequence, decoding one that pydicom read as UN."""
    if element.VR == "UN":
        return pydicom.values.convert_SQ(element.value, True, True)
    return element.value


# Elements as Implicit VR Little Endian, with even lengths: Code Value
# (0008,0100), Code Meaning (0008,0104), and a private block with one element.
CODE_VALUE = _encoded(0x00080100, b"AB")
CODE_MEANING = _encoded(0x00080104, b"SYNTHETIC MEANING ")
PRIVATE_BLOCK = _encoded(0x00110010, b"SYNTHETIC CREATOR D ") + _encoded(
    0x00111001, b"SENTINEL PRIVATE"
)
# Values that do not hold only items, of which pydicom 3.0.2 reads some as a
# sequence without an error, as items that leave out part of the value.
MALFORMED = {
    "an-element-without-an-item": _encoded(0x00111001, CODE_VALUE),
    "text-without-an-item": _encoded(0x00111001, PRIVATE_TEXT),
    "an-element-after-an-item": _item(CODE_VALUE) + _encoded(0x00111001, PRIVATE_TEXT),
    "item-too-short": struct.pack("<HHI", 0xFFFE, 0xE000, 4)
    + CODE_VALUE
    + _encoded(0x00111001, PRIVATE_TEXT),
    "not-items": bytes(range(1, 11)),
}


def _nested(value, depth, undefined=False):
    """Return an RT Assertions Sequence value whose items nest ``value``.

    Its item holds Code Meaning, a private block, and, at depth 1, Concept
    Name Code Sequence with ``value``; at depth 2, that sequence holds an
    item with Code Value and Equivalent Code Sequence, which has ``value``.
    With ``undefined``, every sequence and item that encloses ``value`` is
    of undefined length.
    """
    if depth == 1:
        nested = _encoded(CONCEPT_NAME_CODE_SEQUENCE, value)
    else:
        item = _item(CODE_VALUE + _encoded(EQUIVALENT_CODE_SEQUENCE, value), undefined)
        nested = _sequence(CONCEPT_NAME_CODE_SEQUENCE, item, undefined)
    return _item(CODE_MEANING + PRIVATE_BLOCK + nested, undefined)


@pytest.mark.deid_requirement("PS3.15-E.1.1-09", "PS3.15-E.3.10-02", "MIDI-BP-13")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize("undefined", [False, True], ids=["defined", "undefined"])
def test_the_basic_profile_removes_every_private_attribute(transfer_syntax, undefined):
    # In Implicit VR Little Endian, a private sequence of defined length has
    # no VR to show that it holds items, and one of undefined length does.
    dataset = _plan()
    dataset[0x00091002].is_undefined_length = undefined
    data = synthetic.written(dataset, transfer_syntax)

    plan = plan_instance(
        read_source(data),
        ElementRules(compose_policy("basic")),
        load_iod_tables().iods["RT Plan"],
    )
    written = _written_back(_transformed(data))

    removed = [
        str(element.path)
        for element in plan.elements
        if element.action == "X"
        and element.removed_with is None
        and int(element.path.tag[1:5], 16) % 2
    ]
    assert removed == PLAN_PATHS
    # X removes a sequence with all its items and their attributes (Table
    # E.1-1a), the standard ones included.
    inside = [
        element
        for element in plan.elements
        if element.path.items[:1] == ((PRIVATE_SEQUENCE.tag, 0),)
    ]
    assert inside
    assert {element.removed_with for element in inside} == {PRIVATE_SEQUENCE}
    assert _odd_groups(written) == []
    assert [beam.BeamNumber for beam in written.BeamSequence] == [1, 2]
    assert written.BeamSequence[1].ControlPointSequence[0].ControlPointIndex == 0


@pytest.mark.deid_requirement("PS3.15-E.3.10-02", "MIDI-BP-06", "MIDI-BP-13")
@TRANSFER_SYNTAXES
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
def test_every_odd_group_element_is_removed(transfer_syntax, tag):
    # Table E.1-1 gives every attribute "(gggg,eeee) where gggg is odd" X,
    # whether or not it is a valid private creator or private data element.
    dataset = synthetic.rt_plan()
    dataset.add_new(tag, "LO", "SENTINEL ODD")
    beam = pydicom.Dataset()
    beam.BeamNumber = 1
    beam.add_new(tag, "LO", "SENTINEL ODD")
    dataset.BeamSequence = [beam]

    written = _written_back(_transformed(synthetic.written(dataset, transfer_syntax)))

    assert _odd_groups(written) == []
    assert written.BeamSequence[0].BeamNumber == 1


@pytest.mark.deid_requirement("PS3.15-E.1.1-09", "PS3.15-E.3.10-02")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize("depth", [0, 1, 2], ids=["its-item", "depth-1", "depth-2"])
@pytest.mark.parametrize("undefined", [False, True], ids=["defined", "undefined"])
def test_private_attributes_in_a_sequence_read_as_unknown_are_removed(
    monkeypatch, transfer_syntax, depth, undefined
):
    # pydicom reads RT Assertions Sequence as UN, and writes it so in
    # Explicit VR Little Endian; the pinned dictionary gives it SQ, so its
    # items are read as Implicit VR Little Endian (PS3.5 Section 6.2.2), at
    # every depth, and the private attributes in them are found.
    value = (
        _item(CODE_MEANING + PRIVATE_BLOCK, undefined)
        if depth == 0
        else _nested(_item(CODE_VALUE + PRIVATE_BLOCK), depth, undefined)
    )
    dataset = synthetic.rt_plan()
    dataset[RT_ASSERTIONS_SEQUENCE] = _unknown(
        monkeypatch, RT_ASSERTIONS_SEQUENCE, value
    )

    written = _written_back(_transformed(synthetic.written(dataset, transfer_syntax)))

    (assertion,) = _items(written[RT_ASSERTIONS_SEQUENCE])
    assert _odd_groups(assertion) == []
    assert assertion.CodeMeaning == "SYNTHETIC MEANING"


@pytest.mark.deid_requirement("PS3.15-E.1.1-09", "PS3.15-E.3.10-02")
@pytest.mark.parametrize("undefined", [False, True], ids=["defined", "undefined"])
def test_private_attributes_in_a_known_sequence_written_as_unknown_are_removed(
    monkeypatch, undefined
):
    # Explicit VR Little Endian can carry any sequence as UN, whose items,
    # and the sequences nested in them, are Implicit VR Little Endian.
    control_point = _item(PRIVATE_BLOCK + _encoded(0x300A0112, b"0 "))
    beams = _item(PRIVATE_BLOCK + _encoded(0x300A00C0, b"1 "), undefined) + _item(
        PRIVATE_BLOCK
        + _encoded(0x300A00C0, b"2 ")
        + _sequence(0x300A0111, control_point, undefined),
        undefined,
    )
    dataset = synthetic.rt_plan()
    dataset[BEAM_SEQUENCE] = _unknown(monkeypatch, BEAM_SEQUENCE, beams)

    written = _written_back(_transformed(synthetic.written(dataset, EXPLICIT_VR)))

    assert _odd_groups(written) == []
    assert [beam.BeamNumber for beam in written.BeamSequence] == [1, 2]
    assert written.BeamSequence[1].ControlPointSequence[0].ControlPointIndex == 0


@pytest.mark.deid_requirement("PS3.15-E.3.10-02")
@TRANSFER_SYNTAXES
@pytest.mark.parametrize("kept", [True, False], ids=["kept", "in-a-removed-sequence"])
@pytest.mark.parametrize("value", list(MALFORMED.values()), ids=list(MALFORMED))
def test_a_sequence_read_as_unknown_that_is_not_only_items_is_refused(
    monkeypatch, transfer_syntax, kept, value
):
    # Private attributes in bytes that do not read as items could not be
    # found, so the source is refused, even where a rule would remove the
    # sequence that holds them.
    nested = value if kept else _nested(value, 1)
    dataset = synthetic.rt_plan()
    dataset[RT_ASSERTIONS_SEQUENCE] = _unknown(
        monkeypatch, RT_ASSERTIONS_SEQUENCE, nested
    )
    data = synthetic.written(dataset, transfer_syntax)
    # The run's first pass sequesters a file whose referencing sequences
    # cannot be read before the transform sees it, so the record is the
    # file's without the sequence.
    record = synthetic.written(synthetic.rt_plan(), transfer_syntax)

    result = _transformed(data, record)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (SourceReason.STRUCTURE,)


@pytest.mark.deid_requirement("PS3.15-E.3.10-02")
# The output keeps the item's character set, of which pydicom warns again
# when the test reads it back.
@pytest.mark.filterwarnings("ignore:Unknown encoding:UserWarning")
@TRANSFER_SYNTAXES
def test_an_item_character_set_does_not_stop_private_attributes_being_removed(
    transfer_syntax,
):
    # Removing an element decodes no value, so a Specific Character Set that
    # is not supported matters only to the values that are kept or cleaned.
    beam = pydicom.Dataset()
    beam.SpecificCharacterSet = "ISO_IR 6"
    beam.BeamNumber = 1
    _private(beam, 0x300B, "SYNTHETIC CREATOR C", [(0x01, "LO", "SENTINEL C")])
    dataset = synthetic.rt_plan()
    dataset.BeamSequence = [beam]
    data = bytearray(synthetic.written(dataset, transfer_syntax))
    # pydicom does not write an unknown character set without a warning, so
    # a Defined Term of the same length is written in its place and replaced.
    start = data.index(b"ISO_IR 6")
    data[start : start + len(UNKNOWN_CHARACTER_SET)] = UNKNOWN_CHARACTER_SET
    record = synthetic.written(synthetic.rt_plan(), transfer_syntax)

    # pydicom warns of the character set as it reads the item, which the
    # engine summarises without the value.
    with pytest.warns(UserWarning, match="Details are not shown"):
        result = _transformed(bytes(data), record)

    written = _written_back(result)
    assert _odd_groups(written) == []
    assert written.BeamSequence[0].BeamNumber == 1
