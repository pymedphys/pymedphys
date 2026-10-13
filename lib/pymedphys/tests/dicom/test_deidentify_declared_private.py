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

"""The Retain Safe Private Option, applied by what an instance declares safe.

An instance's Private Data Element Characteristics Sequence (0008,0300) can
mark a private block SAFE, or list its nonidentifying elements, which E.3.10
counts as a way of knowing that they are safe. Every file is synthetic.
Values that must never reach a written file carry the text ``SENTINEL``.
"""

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import conformance, conformance_markdown, policy, run
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import (
    Decision,
    ReasonCode,
    release_condition,
)
from pymedphys._dicom.deidentify.retained_private import private_actions, private_plan
from pymedphys._dicom.deidentify.run_qc import RetainedText
from pymedphys._dicom.deidentify.safe_private import load_safe_private_rules
from pymedphys._dicom.deidentify.source import read_source

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
TRANSFER_SYNTAXES = (
    synthetic.EXPLICIT_VR_LITTLE_ENDIAN,
    synthetic.IMPLICIT_VR_LITTLE_ENDIAN,
)
# A creator that no reviewed rule names, and one that some do.
ACME = "ACME 1.0"
PET = "Philips PET Private Group"
CHARACTERISTICS = "(0008,0300)"


def _top(tag):
    return ElementPath((), tag)


def _declaration(
    status,
    group=0x0011,
    creator=ACME,
    nonidentifying=None,
    identifying=None,
    defined=(),
):
    """An item of (0008,0300) for one block.

    ``defined`` gives (element, VR) pairs, or (element, VR, VM values)
    triples, for Private Data Element Definition Sequence (0008,0310), whose
    VM is a single value where none is given and absent where it is None,
    and ``identifying`` the
    elements of one item of Deidentification Action Sequence (0008,0305).
    """
    item = pydicom.Dataset()
    item.add_new(0x00080301, "US", group)
    item.add_new(0x00080302, "LO", creator)
    item.add_new(0x00080303, "CS", status)
    if nonidentifying is not None:
        item.add_new(0x00080304, "US", list(nonidentifying))
    if identifying is not None:
        action = pydicom.Dataset()
        action.add_new(0x00080306, "US", list(identifying))
        action.add_new(0x00080307, "CS", "X")
        item.add_new(0x00080305, "SQ", pydicom.Sequence([action]))
    if defined:
        definitions = []
        for element, vr, *vm in defined:
            definition = pydicom.Dataset()
            definition.add_new(0x00080308, "US", element)
            multiplicity = vm[0] if vm else [1]
            if multiplicity is not None:
                definition.add_new(0x00080309, "UL", multiplicity)
            definition.add_new(0x0008030A, "CS", vr)
            definition.add_new(0x0008030D, "UC", f"Acme{element:02X}")
            definition.add_new(0x0008030C, "UC", f"Acme {element:02X}")
            definitions.append(definition)
        item.add_new(0x00080310, "SQ", pydicom.Sequence(definitions))
    return item


# The VRs that (0008,0310) defines for the elements of the ACME block below.
ACME_VRS = ((0x01, "US"), (0x02, "DS"), (0x03, "LO"), (0x04, "DA"), (0x05, "UI"))


def _acme(*declarations, elements=None):
    """A CT slice with an ACME block in group 0011, described by ``declarations``."""
    dataset = synthetic.ct_slice(0)
    dataset.add_new(0x00110010, "LO", ACME)
    for tag, vr, value in elements or (
        (0x00111001, "US", 5),
        (0x00111002, "DS", "1.25"),
        (0x00111003, "LO", "SENTINEL TEXT"),
        (0x00111004, "DA", "20200101"),
        (0x00111005, "UI", "2.25.700700"),
        (0x00111006, "SS", -3),  # defined by no item of (0008,0310)
    ):
        dataset.add_new(tag, vr, value)
    if declarations:
        dataset.add_new(0x00080300, "SQ", pydicom.Sequence(declarations))
    return dataset


def _actions(dataset, transfer_syntax=synthetic.EXPLICIT_VR_LITTLE_ENDIAN, data=None):
    data = synthetic.written(dataset, transfer_syntax) if data is None else data
    return dict(private_actions(read_source(data), load_safe_private_rules()))


def _acme_actions(actions):
    """Return the actions of the ACME block at the top level, by element."""
    return {
        path.tag: action
        for path, action in actions.items()
        if not path.items and path.tag.startswith("(0011,")
    }


def _transform():
    return InstanceTransform(
        policy.compose_custom_policy([policy.SAFE_PRIVATE]),
        KEY,
        unvalidated_policy=True,
    )


def _written(data):
    result = _transform()(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    return result.data


def _in_private(data):
    """Return each element of a file in or under a private group, as text."""
    return {
        str(path)
        for path in read_source(data).paths()
        if any(int(tag[1:5], 16) % 2 for tag in (*(t for t, _ in path.items), path.tag))
    }


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_block_declared_safe_keeps_what_the_handling_of_each_vr_keeps(
    transfer_syntax,
):
    dataset = _acme(_declaration("SAFE", defined=ACME_VRS))

    actions = _acme_actions(_actions(dataset, transfer_syntax))

    explicit = transfer_syntax == synthetic.EXPLICIT_VR_LITTLE_ENDIAN
    assert actions == {
        "(0011,0010)": "K",
        "(0011,1001)": "K",  # a number
        "(0011,1002)": "K",  # a number string
        "(0011,1003)": "X",  # text, which no reviewed cleaner cleans
        "(0011,1004)": "X",  # a date
        # A UID is replaced where the file writes it as UI.
        "(0011,1005)": "U" if explicit else "X",
        # Without (0008,0310), only the file's own VR reads the value.
        "(0011,1006)": "K" if explicit else "X",
    }


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_without_a_declaration_an_unlisted_block_is_removed():
    actions = _acme_actions(_actions(_acme()))

    assert set(actions.values()) == {"X"}


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_mixed_block_keeps_only_its_nonidentifying_elements(transfer_syntax):
    declaration = _declaration("MIXED", nonidentifying=[0x01], defined=ACME_VRS)

    actions = _acme_actions(_actions(_acme(declaration), transfer_syntax))

    assert actions["(0011,0010)"] == "K"
    assert actions["(0011,1001)"] == "K"
    assert actions["(0011,1002)"] == "X"
    assert actions["(0011,1006)"] == "X"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize(
    "declarations",
    [
        [_declaration("UNSAFE", group=0x7053, creator=PET)],
        [_declaration("MIXED", group=0x7053, creator=PET, nonidentifying=[0x09])],
        [_declaration("SAFE", group=0x7053, creator=PET, identifying=[0x00])],
        [
            _declaration("SAFE", group=0x7053, creator=PET),
            _declaration("UNSAFE", group=0x7053, creator=PET),
        ],
        # An item that names the block but cannot otherwise be read.
        [_declaration("safe", group=0x7053, creator=PET)],
        [_declaration("MIXED", group=0x7053, creator=PET)],
        [_declaration("MIXED", group=0x7053, creator=PET, nonidentifying=[0x0100])],
        [_declaration("SAFE", group=0x7053, creator=PET, identifying=[0x0100])],
    ],
    ids=[
        "unsafe",
        "mixed",
        "identifying",
        "items-disagree",
        "lower-case-status",
        "mixed-without-a-list",
        "nonidentifying-above-00FF",
        "identifying-above-00FF",
    ],
)
def test_an_element_declared_possibly_identifying_is_removed_despite_its_rule(
    declarations,
):
    # A reviewed rule keeps the SUV Factor (7053,xx00); the instance says
    # it may identify, so it is not known to be safe.
    dataset = synthetic.ct_slice(0)
    dataset.add_new(0x70530010, "LO", PET)
    dataset.add_new(0x70531000, "DS", "1.25")
    dataset.add_new(0x00080300, "SQ", pydicom.Sequence(declarations))

    actions = _actions(dataset)

    assert actions[_top("(7053,1000)")] == "X"
    assert actions[_top("(7053,0010)")] == "X"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_reviewed_rule_still_settles_an_element_that_is_declared_safe():
    # The rule for the PET SUV Factor checks it as a DS of VM 1.
    dataset = synthetic.ct_slice(0)
    dataset.add_new(0x70530010, "LO", PET)
    dataset.add_new(0x70531000, "DS", ["1.25", "2.5"])
    dataset.add_new(
        0x00080300,
        "SQ",
        pydicom.Sequence([_declaration("SAFE", group=0x7053, creator=PET)]),
    )

    actions = _actions(dataset)

    assert actions[_top("(7053,1000)")] == "X"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize(
    "declaration",
    [
        _declaration("SAFE", group=0x0013),
        _declaration("SAFE", creator="acme 1.0"),
        _declaration("SAFE", creator=" ACME 1.0"),
        _declaration("MIXED", nonidentifying=[0x01, 0x0101]),
        _declaration("SAFE", group=0x0001),
        _declaration("SAFE", group=0x0010),
    ],
    ids=[
        "another-group",
        "another-case",
        "leading-space",
        "element-above-00FF",
        "reserved-group",
        "even-group",
    ],
)
def test_a_declaration_that_does_not_declare_the_block_safe_keeps_nothing(
    declaration,
):
    actions = _acme_actions(_actions(_acme(declaration)))

    assert set(actions.values()) == {"X"}


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_declared_element_is_removed_where_its_vr_is_unknown_or_disputed():
    # Explicit VR writes US, and (0008,0310) defines DS.
    dataset = _acme(_declaration("SAFE", defined=[(0x01, "DS")]))

    explicit = _acme_actions(_actions(dataset))
    implicit = _acme_actions(
        _actions(_acme(_declaration("SAFE")), synthetic.IMPLICIT_VR_LITTLE_ENDIAN)
    )

    assert explicit["(0011,1001)"] == "X"
    assert explicit["(0011,1002)"] == "K"
    assert set(implicit.values()) == {"X"}


def test_definitions_that_disagree_in_one_item_define_nothing():
    # A second item's agreeing definition does not settle the dispute.
    dataset = _acme(
        _declaration("SAFE", defined=[(0x01, "US"), (0x01, "SS")]),
        _declaration("SAFE", defined=[(0x01, "US")]),
        elements=[(0x00111001, "US", 5)],
    )

    actions = _acme_actions(_actions(dataset, synthetic.IMPLICIT_VR_LITTLE_ENDIAN))

    assert actions == {"(0011,0010)": "X", "(0011,1001)": "X"}


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
@pytest.mark.parametrize(
    "multiplicity, values, kept",
    [
        (None, [5], True),  # no VM is defined, so one value
        (None, [5, 6], False),
        ([1], [5, 6], False),
        ([2], [5, 6], True),
        ([1, 0], [5, 6, 7], True),  # 1-n
        ([1, 3], [5, 6, 7, 8], False),  # 1-3
        ([0, 0, 3], [1, 2, 3, 4, 5, 6], True),  # 3-3n
        ([3, 0, 3], [1, 2, 3, 4], False),
        ([2, 6, 2], [5, 6, 7, 8], False),  # no PS3.6 form, so one value
        ([2, 6, 2], [5], True),
        ([1, 0, 0], [5, 6], False),  # a stride of 0 is not allowed
    ],
)
def test_a_declared_number_has_at_most_the_values_its_vm_allows(
    transfer_syntax, multiplicity, values, kept
):
    dataset = _acme(
        _declaration("SAFE", defined=[(0x01, "US", multiplicity)]),
        elements=[(0x00111001, "US", values)],
    )

    actions = _acme_actions(_actions(dataset, transfer_syntax))

    assert actions["(0011,1001)"] == ("K" if kept else "X")


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_an_element_that_no_item_defines_has_one_value():
    # Explicit VR gives the VR, but nothing gives the VM.
    dataset = _acme(_declaration("SAFE"), elements=[(0x00111006, "SS", [-3, 4])])

    assert _acme_actions(_actions(dataset))["(0011,1006)"] == "X"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_declared_value_that_is_not_valid_for_its_vr_is_removed(transfer_syntax):
    dataset = _acme(
        _declaration("SAFE", defined=[(0x02, "DS")]),
        elements=[(0x00111002, "DS", "1.234567")],
    )
    data = synthetic.written(dataset, transfer_syntax)
    assert data.count(b"1.234567") == 1
    data = data.replace(b"1.234567", b"SENTINEL")

    actions = _acme_actions(_actions(None, data=data))

    assert actions == {"(0011,0010)": "X", "(0011,1002)": "X"}


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "PS3.15-E.3.10-03")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_declaration_applies_to_its_block_in_the_items_of_a_sequence(
    transfer_syntax,
):
    # An unlisted private sequence is parsed, and its item's ACME block is
    # declared safe, so the sequence keeps the number in it.
    item = pydicom.Dataset()
    item.add_new(0x00110010, "LO", ACME)
    item.add_new(0x00111001, "US", 5)
    item.add_new(0x00111003, "LO", "SENTINEL TEXT")
    elements = [(0x00111010, "SQ", pydicom.Sequence([item]))]
    declared = _acme(_declaration("SAFE", defined=ACME_VRS), elements=elements)
    undeclared = _acme(elements=elements)

    written = _written(synthetic.written(declared, transfer_syntax))
    removed = _written(synthetic.written(undeclared, transfer_syntax))

    within = "(0011,1010)[0] > "
    assert _in_private(written) == {
        "(0011,0010)",
        "(0011,1010)",
        within + "(0011,0010)",
        within + "(0011,1001)",
    }
    assert b"SENTINEL" not in written
    assert not _in_private(removed)


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_declaration_in_the_items_of_a_sequence_is_ignored_and_removed(
    transfer_syntax,
):
    # Only the top-level (0008,0300), in the SOP Common Module, is read.
    item = pydicom.Dataset()
    item.add_new(
        0x00080300, "SQ", pydicom.Sequence([_declaration("SAFE", defined=ACME_VRS)])
    )
    item.add_new(0x00110010, "LO", ACME)
    item.add_new(0x00111001, "US", 5)
    dataset = _acme(elements=[(0x00111010, "SQ", pydicom.Sequence([item]))])

    written = _written(synthetic.written(dataset, transfer_syntax))

    assert not _in_private(written)
    assert not any(path.tag == CHARACTERISTICS for path in read_source(written).paths())


@pytest.mark.deid_requirement("PS3.15-E.3.10-03")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_sequence_is_parsed_whatever_its_block_is_declared(transfer_syntax):
    item = pydicom.Dataset()
    item.SliceThickness = "2.5"
    dataset = _acme(
        _declaration("UNSAFE"),
        elements=[(0x00111010, "SQ", pydicom.Sequence([item]))],
    )

    written = _written(synthetic.written(dataset, transfer_syntax))

    assert _in_private(written) == {
        "(0011,0010)",
        "(0011,1010)",
        "(0011,1010)[0] > (0018,0050)",
    }


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_the_option_keeps_declared_attributes_end_to_end(transfer_syntax):
    data = synthetic.written(
        _acme(_declaration("SAFE", defined=ACME_VRS)), transfer_syntax
    )

    result = _transform()(data, InstanceRecord.from_file(data))
    plan = private_plan(read_source(data), load_safe_private_rules())

    assert isinstance(result, run.Transformed), result
    written = read_source(result.data)
    explicit = transfer_syntax == synthetic.EXPLICIT_VR_LITTLE_ENDIAN
    kept = {"(0011,0010)", "(0011,1001)", "(0011,1002)"}
    if explicit:
        kept |= {"(0011,1005)", "(0011,1006)"}
    assert _in_private(result.data) == kept
    # (0008,0300) is removed, as under every policy.
    assert _top(CHARACTERISTICS) not in written
    assert b"SENTINEL" not in result.data
    assert b"20200101" not in result.data
    assert b"2.25.700700" not in result.data
    # The VR that (0008,0310) defines reads each kept value that the file
    # writes without one, so the creator and DS are reviewed as strings.
    assert dict(plan.vrs) == (
        {}
        if explicit
        else {
            _top("(0011,0010)"): "LO",
            _top("(0011,1001)"): "US",
            _top("(0011,1002)"): "DS",
        }
    )
    assert [
        text
        for text in result.qc
        if isinstance(text, RetainedText) and text.path.tag.startswith("(0011,")
    ] == [
        RetainedText(ACME, _top("(0011,0010)")),
        RetainedText("1.25", _top("(0011,1002)")),
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "MIDI-BP-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_declared_vendor_block_is_released_and_another_reviewed(transfer_syntax):
    # (0008,0302) is removed with (0008,0300), and found in the kept creator.
    vendor = synthetic.ct_slice(0)
    vendor.add_new(0x70530010, "LO", PET)
    vendor.add_new(0x70531000, "DS", "1.25")
    vendor.add_new(
        0x00080300,
        "SQ",
        pydicom.Sequence([_declaration("SAFE", group=0x7053, creator=PET)]),
    )
    other = _acme(_declaration("SAFE", defined=ACME_VRS))

    conditions = {}
    for name, dataset in (("vendor", vendor), ("other", other)):
        data = synthetic.written(dataset, transfer_syntax)
        result = _transform()(data, InstanceRecord.from_file(data))
        assert isinstance(result, run.Transformed), result
        conditions[name] = release_condition(result.evidence, result.data)

    assert conditions["vendor"].decision is Decision.RELEASE
    assert conditions["other"].decision is Decision.QC_REVIEW
    assert {
        (reason.code, reason.path.tag) for reason in conditions["other"].reasons
    } == {(ReasonCode.RESIDUAL_TEXT, "(0008,0302)")}


@pytest.mark.deid_requirement("PS3.15-E.3.10-04")
def test_the_statement_describes_the_blocks_an_instance_declares_safe():
    statement = conformance.conformance_statement(
        policy.compose_custom_policy([policy.SAFE_PRIVATE]), vocabulary=None
    )

    text = conformance_markdown.render_markdown(statement)

    # Every route of E.3.10 is applied, so none is pending.
    assert not statement.pending
    assert "Block Identifying Information Status (0008,0303)" in text
    assert "Nonidentifying Private Elements (0008,0304)" in text
