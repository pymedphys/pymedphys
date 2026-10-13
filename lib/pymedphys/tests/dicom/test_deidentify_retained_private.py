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

"""The Retain Safe Private Option, applied by the reviewed rules.

Every file is synthetic. Values that must never reach a written file carry
the text ``SENTINEL``.
"""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    element_rules,
    policy,
    run,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.retained_private import private_actions, private_plan
from pymedphys._dicom.deidentify.run_qc import RetainedText
from pymedphys._dicom.deidentify.safe_private import Handling, load_safe_private_rules
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.standard import PRIVATE_ATTRIBUTES_TAG

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
SAFE_PRIVATE = policy.SAFE_PRIVATE
SAFE_PRIVATE_CODE = "113111"
TRANSFER_SYNTAXES = (
    synthetic.EXPLICIT_VR_LITTLE_ENDIAN,
    synthetic.IMPLICIT_VR_LITTLE_ENDIAN,
)
PET = "Philips PET Private Group"
PHILIPS = "Philips Imaging DD 001"
GE_ACQUISITION = "GEMS_ACQU_01"
GE_PACS = "GEIIS PACS"
NQ_HEADER = "NQHeader"
SC2000 = "SIEMENS Ultrasound SC2000"


def _top(tag):
    return ElementPath((), tag)


def _actions(dataset, transfer_syntax=synthetic.EXPLICIT_VR_LITTLE_ENDIAN, data=None):
    data = synthetic.written(dataset, transfer_syntax) if data is None else data
    return dict(private_actions(read_source(data), load_safe_private_rules()))


def _slice(*elements):
    """A CT slice with the given private elements, each (tag, VR, value)."""
    dataset = synthetic.ct_slice(0)
    for tag, vr, value in elements:
        dataset.add_new(tag, vr, value)
    return dataset


def _patched(data, old, new):
    """Replace the one occurrence of ``old`` in a file with ``new``, as long."""
    assert data.count(old) == 1 and len(old) == len(new)
    return data.replace(old, new)


def _transform(options=(SAFE_PRIVATE,)):
    return InstanceTransform(
        policy.compose_custom_policy(options), KEY, unvalidated_policy=True
    )


def _written(transform, data):
    result = transform(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    return result.data


def _private(dataset):
    """Return the private elements of a data set, by tag, with their values."""
    return {
        f"({e.tag.group:04X},{e.tag.element:04X})": e.value
        for e in dataset
        if e.tag.group % 2
    }


def test_the_engine_applies_the_option_by_the_reviewed_rules():
    composed = policy.compose_custom_policy([SAFE_PRIVATE])
    assert composed.actions[PRIVATE_ATTRIBUTES_TAG] == "C"
    rules = element_rules.ElementRules(composed)
    assert rules.safe_private == load_safe_private_rules()
    assert rules.rule("(7053,1000)").action == "C"
    basic = element_rules.ElementRules(policy.compose_policy("basic"))
    assert basic.safe_private is None
    assert basic.rule("(7053,1000)").action == "X"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_numbers_and_code_strings_are_kept_with_their_creators(transfer_syntax):
    dataset = _slice(
        (0x70530010, "LO", PET),
        (0x70531000, "DS", "1.25"),
        (0x09030010, "LO", GE_PACS),
        (0x09031010, "US", 1),
        (0x20010010, "LO", PHILIPS),
        (0x20011004, "CS", "AP"),
        (0x20011003, "FL", 1000.0),
        (0x01490010, "LO", SC2000),
        (0x01491001, "FD", [1.5, 2.5, 3.5]),
    )

    actions = _actions(dataset, transfer_syntax)

    for tag in (
        "(7053,0010)",
        "(7053,1000)",
        "(0903,0010)",
        "(0903,1010)",
        "(2001,0010)",
        "(2001,1004)",
        "(2001,1003)",
        "(0149,0010)",
        "(0149,1001)",
    ):
        assert actions[_top(tag)] == "K", tag


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_rule_applies_in_whichever_block_its_creator_reserves():
    dataset = _slice(
        (0x70530010, "LO", "SENTINEL CREATOR"),
        (0x70531000, "DS", "1.25"),
        (0x70530042, "LO", PET),
        (0x70534200, "DS", "2.5"),
        (0x70534209, "DS", "3.5"),
    )

    actions = _actions(dataset)

    assert actions[_top("(7053,0042)")] == "K"
    assert actions[_top("(7053,4200)")] == "K"
    assert actions[_top("(7053,4209)")] == "K"
    # The block of a creator that no rule lists is removed whole.
    assert actions[_top("(7053,0010)")] == "X"
    assert actions[_top("(7053,1000)")] == "X"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize(
    "creator, kept",
    [
        (PET, True),
        (PET + " ", True),
        (PET + "\x00", True),
        (PET.upper(), False),
        (" " + PET, False),
        (PET.replace(" ", "_"), False),
        ("SENTINEL", False),
    ],
)
def test_a_creator_matches_exactly_apart_from_trailing_padding(creator, kept):
    dataset = _slice((0x70530010, "LO", creator), (0x70531000, "DS", "1.25"))

    actions = _actions(dataset)

    expected = "K" if kept else "X"
    assert actions[_top("(7053,0010)")] == expected
    assert actions[_top("(7053,1000)")] == expected


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize(
    "written, kept",
    [
        (b"Philips PET Private Group ", True),
        # The same creator once an escape sequence designates ISO 646.
        (b"Philips PET\x1b(B Private Group", False),
        (b"Philips PET Private Gr\xe9up ", False),  # outside ISO 646
        (b"Philips PET Private Group\\A ", False),  # two values
    ],
)
def test_only_a_creator_of_printable_iso_646_is_compared(written, kept):
    # Written as UN, so that its bytes are as given.
    dataset = _slice((0x70530010, "UN", written), (0x70531000, "DS", "1.25"))

    actions = _actions(dataset)

    expected = "K" if kept else "X"
    assert actions[_top("(7053,0010)")] == expected
    assert actions[_top("(7053,1000)")] == expected


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_creator_written_with_another_vr_matches_no_rule():
    dataset = _slice((0x70530010, "UT", PET), (0x70531000, "DS", "1.25"))
    dataset.add_new(0x00990010, "LO", NQ_HEADER)
    dataset.add_new(0x00991004, "SS", 0)

    actions = _actions(dataset)

    assert actions[_top("(0099,1004)")] == "K"
    assert actions[_top("(7053,0010)")] == "X"
    assert actions[_top("(7053,1000)")] == "X"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize(
    "tag, vr, value",
    [
        (0x70531000, "DS", "1.25\\2.5"),  # two values where the VM is 1
        (0x70531000, "IS", "12"),  # another VR than the rule's
        (0x70531000, "LO", "1.25"),
        (0x70531000, "UT", "1.25"),
        (0x20011004, "CS", ["AP", "LR"]),
    ],
)
def test_a_value_of_another_vr_or_vm_is_removed(tag, vr, value):
    dataset = _slice((0x70530010, "LO", PET), (0x20010010, "LO", PHILIPS))
    dataset.add_new(tag, vr, value)

    actions = _actions(dataset)

    path = _top(f"({tag >> 16:04X},{tag & 0xFFFF:04X})")
    assert actions[path] == "X"
    # Nothing of the block is kept, so neither is its creator.
    assert actions[ElementPath((), path.tag[:6] + "0010)")] == "X"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize(
    "tag, vr, value, written",
    [
        (0x70531000, "DS", "1.234567", b"SENTINEL"),  # not a number
        (0x70531000, "DS", "1.234567", b"1.2\x004567"),  # a NUL
        (0x20011002, "IS", "12345678", b"1234.678"),  # not an integer
        (0x20011004, "CS", "SENTINEL", b"sentinel"),  # lower case
        (0x20011004, "CS", "SENTINEL", b"SENT\xc9NEL"),  # outside ISO 646
    ],
)
def test_a_value_that_its_check_refuses_is_removed(tag, vr, value, written):
    dataset = _slice(
        (0x70530010, "LO", PET), (0x20010010, "LO", PHILIPS), (tag, vr, value)
    )
    data = _patched(synthetic.written(dataset), value.encode(), written)

    actions = _actions(None, data=data)

    path = _top(f"({tag >> 16:04X},{tag & 0xFFFF:04X})")
    assert actions[path] == "X"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_binary_value_must_be_whole_values_within_the_vm():
    dataset = _slice(
        (0x09030010, "LO", GE_PACS),
        (0x09031010, "US", [1, 2]),  # VM 1
        (0x09031012, "UN", b"\x01\x00"),
        (0x01490010, "LO", SC2000),
        (0x01491001, "UN", bytes(12)),  # not a whole number of FD values
    )

    actions = _actions(dataset)

    assert actions[_top("(0903,1010)")] == "X"
    assert actions[_top("(0149,1001)")] == "X"
    assert actions[_top("(0149,0010)")] == "X"
    # A value written as UN is read by the rule's VR.
    assert actions[_top("(0903,1012)")] == "K"
    assert actions[_top("(0903,0010)")] == "K"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_text_removed_rules_and_elements_without_a_rule_are_removed():
    dataset = _slice(
        (0x00190010, "LO", GE_ACQUISITION),
        (0x0019109E, "LO", "SENTINEL SEQUENCE"),  # text
        (0x00191024, "DS", "12.5"),  # Mid Scan Time, which its rule removes
        (0x001910F0, "DS", "1"),  # no rule
        (0x00191200, "DS", "1"),  # no creator
        (0x00190001, "UN", b"\x00\x00"),  # not allowed by PS3.5
        (0x00190100, "UN", b"\x00\x00"),
    )

    actions = _actions(dataset)

    assert set(actions.values()) == {"X"}
    assert len(actions) == 7


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_uid_is_replaced_where_it_is_written_as_ui():
    dataset = _slice((0x00990010, "LO", NQ_HEADER), (0x00991002, "UI", "2.25.700700"))

    explicit = _actions(dataset)
    implicit = _actions(dataset, synthetic.IMPLICIT_VR_LITTLE_ENDIAN)

    assert explicit[_top("(0099,1002)")] == "U"
    assert explicit[_top("(0099,0010)")] == "K"
    # Without its VR, its value cannot be read as UIDs.
    assert implicit[_top("(0099,1002)")] == "X"
    assert implicit[_top("(0099,0010)")] == "X"


def _philips_sequence():
    """A Philips private sequence whose item holds kept and removed elements."""
    inner = pydicom.Dataset()
    inner.add_new(0x20010010, "LO", PHILIPS)
    inner.add_new(0x20011003, "FL", 2.0)
    item = pydicom.Dataset()
    item.PatientName = "SENTINEL^NAME"
    item.SliceThickness = "2.5"
    item.add_new(0x20010010, "LO", PHILIPS)
    item.add_new(0x20011003, "FL", 1000.0)
    item.add_new(0x200110FE, "LO", "SENTINEL TEXT")  # no rule
    item.add_new(0x20011065, "SQ", pydicom.Sequence([inner]))
    return _slice(
        (0x20010010, "LO", PHILIPS), (0x2001105F, "SQ", pydicom.Sequence([item]))
    )


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "PS3.15-E.3.10-03")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_private_sequence_is_parsed_and_each_element_judged(transfer_syntax):
    actions = _actions(_philips_sequence(), transfer_syntax)

    item = (("(2001,105F)", 0),)
    inner = (*item, ("(2001,1065)", 0))
    assert actions[_top("(2001,105F)")] == "K"
    assert actions[ElementPath(item, "(2001,0010)")] == "K"
    assert actions[ElementPath(item, "(2001,1003)")] == "K"
    assert actions[ElementPath(item, "(2001,10FE)")] == "X"
    assert actions[ElementPath(item, "(2001,1065)")] == "K"
    assert actions[ElementPath(inner, "(2001,1003)")] == "K"
    # Standard attributes take their own rules, which the walker gives them.
    assert ElementPath(item, "(0010,0010)") not in actions


def _unlisted(*items):
    """A PET block with an unlisted sequence (7053,10F0) of ``items``."""
    return _slice((0x70530010, "LO", PET), (0x705310F0, "SQ", pydicom.Sequence(items)))


def _pet_item(*elements):
    """An item with the PET creator and the given elements, each (tag, VR, value)."""
    item = pydicom.Dataset()
    item.add_new(0x70530010, "LO", PET)
    for tag, vr, value in elements:
        item.add_new(tag, vr, value)
    return item


def _in_private(data):
    """Return each element of a file in or under a private group, as text.

    The file's own structure is read, so that a private sequence that no
    dictionary lists reads as items in implicit VR too.
    """
    return {
        str(path)
        for path in read_source(data).paths()
        if any(int(tag[1:5], 16) % 2 for tag in (*(t for t, _ in path.items), path.tag))
    }


def _qc_private_strings(result):
    return [
        text
        for text in result.qc
        if isinstance(text, RetainedText) and int(text.path.tag[1:5], 16) % 2
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.10-03")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_private_sequence_without_a_rule_is_parsed(transfer_syntax):
    # E.3.10: a sequence not known to hold only safe content is parsed, and
    # each nested attribute handled on its own merits.
    item = _pet_item((0x70531000, "DS", "1.25"), (0x705310FE, "LO", "SENTINEL"))
    item.PatientName = "SENTINEL^NAME"
    item.SliceThickness = "2.5"
    data = synthetic.written(_unlisted(item), transfer_syntax)

    actions = _actions(None, data=data)
    result = _transform()(data, InstanceRecord.from_file(data))

    within = (("(7053,10F0)", 0),)
    assert actions[_top("(7053,10F0)")] == "K"
    assert actions[_top("(7053,0010)")] == "K"
    assert actions[ElementPath(within, "(7053,1000)")] == "K"
    assert actions[ElementPath(within, "(7053,10FE)")] == "X"
    assert isinstance(result, run.Transformed), result
    assert b"SENTINEL" not in result.data
    assert _in_private(result.data) == {
        "(7053,0010)",
        "(7053,10F0)",
        "(7053,10F0)[0] > (7053,0010)",
        "(7053,10F0)[0] > (7053,1000)",
        "(7053,10F0)[0] > (0010,0010)",  # emptied
        "(7053,10F0)[0] > (0018,0050)",
    }
    assert _qc_private_strings(result) == [
        RetainedText(PET, _top("(7053,0010)")),
        RetainedText(PET, ElementPath(within, "(7053,0010)")),
        RetainedText("1.25", ElementPath(within, "(7053,1000)")),
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.10-03")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_parsed_sequence_that_keeps_nothing_goes_with_its_creator(transfer_syntax):
    # What is emptied, given a dummy value, or removed, and a creator kept
    # only for a nested sequence that itself keeps nothing, keep nothing.
    inner = _pet_item((0x705310FE, "LO", "SENTINEL"))
    item = _pet_item(
        (0x705310FE, "LO", "SENTINEL"), (0x705310F1, "SQ", pydicom.Sequence([inner]))
    )
    item.PatientName = "SENTINEL^NAME"
    data = synthetic.written(_unlisted(item), transfer_syntax)

    written = _written(_transform(), data)

    assert b"SENTINEL" not in written
    assert not _in_private(written)


@pytest.mark.deid_requirement("PS3.15-E.3.10-03")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_kept_value_keeps_each_parsed_sequence_that_holds_it(transfer_syntax):
    deepest = _pet_item((0x70531000, "DS", "1.25"))
    inner = _pet_item((0x705310F1, "SQ", pydicom.Sequence([deepest])))
    empty = _pet_item((0x705310FE, "LO", "SENTINEL"))
    dataset = _unlisted(inner)
    dataset.add_new(0x705310F2, "SQ", pydicom.Sequence([empty]))
    data = synthetic.written(dataset, transfer_syntax)

    written = _written(_transform(), data)

    assert b"SENTINEL" not in written
    within = "(7053,10F0)[0] > "
    assert _in_private(written) == {
        "(7053,0010)",
        "(7053,10F0)",
        within + "(7053,0010)",
        within + "(7053,10F1)",
        within + "(7053,10F1)[0] > (7053,0010)",
        within + "(7053,10F1)[0] > (7053,1000)",
    }


@pytest.mark.deid_requirement("PS3.15-E.3.10-03")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_parsed_sequence_keeps_a_creator_that_no_rule_names_for_review(
    transfer_syntax,
):
    # A standard attribute that its own rule keeps is kept in the items of
    # a private sequence of any creator that is compared; the creator,
    # which no rule has reviewed, is listed among the retained strings.
    item = pydicom.Dataset()
    item.SliceThickness = "2.5"
    dataset = _slice(
        (0x00190010, "LO", "ACME 1.0"), (0x00191001, "SQ", pydicom.Sequence([item]))
    )
    data = synthetic.written(dataset, transfer_syntax)

    result = _transform()(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed), result
    assert _in_private(result.data) == {
        "(0019,0010)",
        "(0019,1001)",
        "(0019,1001)[0] > (0018,0050)",
    }
    assert _qc_private_strings(result) == [
        RetainedText("ACME 1.0", _top("(0019,0010)"))
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.10-03")
@pytest.mark.parametrize("creator", [None, b"SENTINEL \xc9"], ids=["none", "latin-1"])
def test_a_private_sequence_without_a_compared_creator_is_removed_whole(creator):
    item = _pet_item((0x70531000, "DS", "1.25"))
    item.SliceThickness = "2.5"
    dataset = _slice((0x00191001, "SQ", pydicom.Sequence([item])))
    if creator is not None:
        dataset.add_new(0x00190010, "LO", creator)
    data = synthetic.written(dataset)

    actions = _actions(None, data=data)
    written = _written(_transform(), data)

    assert actions[_top("(0019,1001)")] == "X"
    assert b"SENTINEL" not in written
    assert not _in_private(written)


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_sequence_rule_without_items_is_removed():
    dataset = _slice((0x20010010, "LO", PHILIPS), (0x2001105F, "OB", b"\x00\x00"))

    actions = _actions(dataset)

    assert actions[_top("(2001,105F)")] == "X"
    assert actions[_top("(2001,0010)")] == "X"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_private_block_in_a_standard_sequence_is_judged_there():
    item = pydicom.Dataset()
    item.add_new(0x70530010, "LO", PET)
    item.add_new(0x70531000, "DS", "1.25")
    item.add_new(0x70531001, "LO", "SENTINEL")
    dataset = _slice()
    dataset.ReferencedImageSequence = pydicom.Sequence([item])

    actions = _actions(dataset)

    within = (("(0008,1140)", 0),)
    assert actions[ElementPath(within, "(7053,0010)")] == "K"
    assert actions[ElementPath(within, "(7053,1000)")] == "K"
    assert actions[ElementPath(within, "(7053,1001)")] == "X"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "PS3.15-E.3.10-03")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_the_option_keeps_safe_private_attributes_end_to_end(transfer_syntax):
    dataset = _philips_sequence()
    for tag, vr, value in (
        (0x70530010, "LO", PET),
        (0x70531000, "DS", "1.25"),
        (0x70531009, "DS", "1.234567"),
        (0x00990010, "LO", NQ_HEADER),
        (0x00991002, "UI", "2.25.700700"),
        (0x00090010, "LO", "SENTINEL CREATOR"),
        (0x00091001, "LO", "SENTINEL VALUE"),
    ):
        dataset.add_new(tag, vr, value)
    data = _patched(
        synthetic.written(dataset, transfer_syntax), b"1.234567", b"SENTINEL"
    )

    written = _written(_transform(), data)

    assert b"SENTINEL" not in written
    output = pydicom.dcmread(io.BytesIO(written))
    private = _private(output)
    assert private["(7053,0010)"] == PET
    assert float(private["(7053,1000)"]) == 1.25
    assert "(7053,1009)" not in private
    assert "(0009,0010)" not in private and "(0009,1001)" not in private
    explicit = transfer_syntax == synthetic.EXPLICIT_VR_LITTLE_ENDIAN
    assert ("(0099,1002)" in private) == explicit
    if explicit:
        replacement = private["(0099,1002)"]
        assert replacement.startswith("2.25.") and replacement != "2.25.700700"
    (item,) = output[0x2001105F].value
    assert "PatientName" not in item or not item.PatientName
    assert _private(item).keys() == {"(2001,0010)", "(2001,1003)", "(2001,1065)"}
    (inner,) = item[0x20011065].value
    assert _private(inner).keys() == {"(2001,0010)", "(2001,1003)"}
    codes = [i.CodeValue for i in output.DeidentificationMethodCodeSequence]
    assert codes == ["113100", SAFE_PRIVATE_CODE]

    basic = pydicom.dcmread(
        io.BytesIO(
            _written(
                InstanceTransform(
                    policy.compose_policy("basic"), KEY, unvalidated_policy=True
                ),
                data,
            )
        )
    )
    assert not _private(basic)


def _diffusion(vr):
    """Philips codes and a PET factor, top level and in an item, with ``vr``."""
    item = pydicom.Dataset()
    item.add_new(0x20010010, "LO", PHILIPS)
    item.add_new(0x20011004, vr or "CS", b"RIGHT " if vr == "UN" else "RIGHT")
    dataset = _slice(
        (0x20010010, "LO", PHILIPS),
        (0x20011004, vr or "CS", b"LEFT" if vr == "UN" else "LEFT"),
        (0x2001105F, "SQ", pydicom.Sequence([item])),
        (0x70530010, "LO", PET),
        (0x70531000, vr or "DS", b"1.25" if vr == "UN" else "1.25"),
    )
    return dataset


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "MIDI-BP-17")
@pytest.mark.parametrize(
    "transfer_syntax, vr",
    [
        (synthetic.EXPLICIT_VR_LITTLE_ENDIAN, None),
        (synthetic.EXPLICIT_VR_LITTLE_ENDIAN, "UN"),
        (synthetic.IMPLICIT_VR_LITTLE_ENDIAN, None),
    ],
    ids=["explicit", "explicit-UN", "implicit"],
)
def test_each_kept_private_string_is_given_to_the_qc_pack(transfer_syntax, vr):
    # A kept creator, code, or number string is reviewed whether or not its
    # VR is written, read by its rule's VR, or as LO for a creator.
    data = synthetic.written(_diffusion(vr), transfer_syntax)

    result = _transform()(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed), result
    output = pydicom.dcmread(io.BytesIO(result.data))
    assert {"(2001,1004)", "(7053,1000)"} <= _private(output).keys()
    item = (("(2001,105F)", 0),)
    retained = [
        text
        for text in result.qc
        if isinstance(text, RetainedText) and int(text.path.tag[1:5], 16) % 2
    ]
    assert retained == [
        RetainedText(PHILIPS, _top("(2001,0010)")),
        RetainedText("LEFT", _top("(2001,1004)")),
        RetainedText(PHILIPS, ElementPath(item, "(2001,0010)")),
        RetainedText("RIGHT", ElementPath(item, "(2001,1004)")),
        RetainedText(PET, _top("(7053,0010)")),
        RetainedText("1.25", _top("(7053,1000)")),
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "MIDI-BP-17")
@pytest.mark.parametrize(
    "transfer_syntax, vr",
    [
        (synthetic.EXPLICIT_VR_LITTLE_ENDIAN, None),
        (synthetic.EXPLICIT_VR_LITTLE_ENDIAN, "UN"),
        (synthetic.IMPLICIT_VR_LITTLE_ENDIAN, None),
    ],
    ids=["explicit", "explicit-UN", "implicit"],
)
def test_each_value_of_a_kept_private_string_is_reviewed(transfer_syntax, vr):
    # A creator padded to an even length with a NUL, and integer and
    # decimal strings of more than one value, each value listed on its own.
    pet = PET.encode() + b"\x00"
    dataset = _slice(
        (0x20010010, vr or "LO", PHILIPS.encode() if vr else PHILIPS),
        (0x20011043, vr or "IS", b"3\\7 " if vr else ["3", "7"]),
        (0x20011074, vr or "DS", b"1.5\\2.5\\3.5 " if vr else ["1.5", "2.5", "3.5"]),
        (0x70530010, vr or "LO", pet),
        (0x70531000, vr or "DS", b"1.25" if vr else "1.25"),
    )
    data = synthetic.written(dataset, transfer_syntax)

    result = _transform()(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed), result
    assert _qc_private_strings(result) == [
        RetainedText(PHILIPS, _top("(2001,0010)")),
        RetainedText("3", _top("(2001,1043)")),
        RetainedText("7", _top("(2001,1043)")),
        RetainedText("1.5", _top("(2001,1074)")),
        RetainedText("2.5", _top("(2001,1074)")),
        RetainedText("3.5", _top("(2001,1074)")),
        RetainedText(PET, _top("(7053,0010)")),
        RetainedText("1.25", _top("(7053,1000)")),
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_the_plan_gives_the_vr_that_reads_each_kept_value_without_one():
    # A sequence holds no value of its own, so is given none.
    dataset = _philips_sequence()
    data = synthetic.written(dataset, synthetic.IMPLICIT_VR_LITTLE_ENDIAN)

    plan = private_plan(read_source(data), load_safe_private_rules())

    item = (("(2001,105F)", 0),)
    assert dict(plan.vrs) == {
        _top("(2001,0010)"): "LO",
        ElementPath(item, "(2001,0010)"): "LO",
        ElementPath(item, "(2001,1003)"): "FL",
        ElementPath((*item, ("(2001,1065)", 0)), "(2001,0010)"): "LO",
        ElementPath((*item, ("(2001,1065)", 0)), "(2001,1003)"): "FL",
    }
    explicit = private_plan(
        read_source(synthetic.written(dataset)), load_safe_private_rules()
    )
    assert not explicit.vrs


@pytest.mark.deid_requirement("PS3.15-E.3.10-04")
def test_the_statement_lists_the_safe_private_attributes_retained():
    composed = policy.compose_custom_policy([SAFE_PRIVATE])

    statement = conformance.conformance_statement(composed, vocabulary=None)

    rules = load_safe_private_rules()
    listed = [rule for rule in rules.retained() if rule.handling is not Handling.TEXT]
    assert statement.safe_private == tuple(listed)
    assert len(listed) == 280 + 65 + 7 + 55
    # It says what the routes of E.3.10 not yet applied would retain.
    assert statement.pending == (conformance.PENDING_SAFE_PRIVATE_ROUTES,)
    text = conformance_markdown.render_markdown(statement)
    assert "## Safe private attributes" in text
    assert conformance.PENDING_SAFE_PRIVATE_ROUTES in text
    rows = [line for line in text.splitlines() if line.startswith(f"| {PET} |")]
    assert rows == [
        f"| {PET} | (7053,xx00) | DS | 1 | numeric | SUV Factor - Multiplying "
        "Stored Pixel Values by Rescale Slope then this factor results in SUVbw "
        "in g/l |",
        f"| {PET} | (7053,xx09) | DS | 1 | numeric | Activity Concentration "
        "Factor - Multiplying Stored Pixel Values by Rescale Slope then this "
        "factor results in MBq/ml. |",
    ]
    # Rules for text, and those that remove, are not listed.
    assert f"| {GE_ACQUISITION} | (0019,xx9E) |" not in text
    assert f"| {GE_ACQUISITION} | (0019,xx24) |" not in text


def test_a_statement_without_the_option_lists_none():
    statement = conformance.conformance_statement(
        policy.compose_policy("basic"), vocabulary=None
    )

    assert not statement.safe_private
    text = conformance_markdown.render_markdown(statement)
    assert "## Safe private attributes" not in text
    assert "X on Private Attributes removes every element of an odd group" in text
