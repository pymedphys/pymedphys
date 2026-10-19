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

"""The Retain Safe Private Option, applied by TCIA's Private Tag Dictionary.

A run may choose TCIA's dictionary in place of the reviewed rules of
``safe_private.toml`` (D-035). Every DICOM file is synthetic, and the
dictionaries other than the shipped one are written here.
"""

import csv
import io
import json
import re

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    api,
    command,
    conformance,
    conformance_markdown,
    method_digest,
    policy,
    qc_pack,
    release_report_markdown,
    run,
    tcia_private_tags,
)
from pymedphys._dicom.deidentify.element_rules import ElementRules
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import Decision, release_condition
from pymedphys._dicom.deidentify.retained_private import private_actions, private_plan
from pymedphys._dicom.deidentify.safe_private import (
    Basis,
    Handling,
    SafePrivateList,
    SafePrivateRules,
    load_safe_private_rules,
)
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.tcia_private_tags import (
    TciaSafePrivateRules,
    parse_tcia_private_tags,
    tcia_safe_private_rules,
)

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
TRANSFER_SYNTAXES = (
    synthetic.EXPLICIT_VR_LITTLE_ENDIAN,
    synthetic.IMPLICIT_VR_LITTLE_ENDIAN,
)
ACME = "ACME 1.0"
HEADER = ("element_sig_pattern", "tag_name", "vr", "private_disposition")
# A dictionary for a creator that no reviewed rule names, and two rows for an
# attribute that a reviewed rule gives VM 4 as IS.
DICTIONARY = (
    ('(0011,"ACME 1.0",01)', "Acme Count", "US", "k"),
    ('(0011,"ACME 1.0",02)', "Acme Factor", "DS", "k"),
    ('(0011,"ACME 1.0",02)', "Acme Factor", "OB", "k"),
    ('(0011,"ACME 1.0",02)', "Acme Factor", "UN", "k"),
    ('(0011,"ACME 1.0",03)', "Acme Offset", "SL", "k"),
    ('(0011,"ACME 1.0",03)', "Acme Offset", "SS", "k"),
    ('(0011,"ACME 1.0",04)', "Acme Operator", "LO", "d"),
    ('(0011,"ACME 1.0",05)', "Acme Label", "LO", "k"),
    ('(0011,"ACME 1.0",06)', "Acme Unknown", "", "k"),
    ('(0008,1111)[<0>](0011,"ACME 1.0",07)', "Acme Nested", "US", "k"),
    ('(0011,"ACME 1.0",08)', "Acme Mode", "CS", "k"),
    ('(0011,"ACME 1.0",08)', "Acme Mode", "CS", "d"),
    ('(0011,"ACME 1.0",0A)', "Acme State", "CS", "d"),
    ('(0011,"ACME 1.0",0A)', "Acme State", "CS", "k"),
    ('(0011,"ACME 1.0  ",09)', "Acme Padded", "US", " K"),
    ('(0011,"ACME 1.0",0B)', "Acme Gain", "US", "d"),
    ('(0011,"ACME 1.0 ",0B)', "Acme Gain", "US", "k"),
    ('(0011,"ACME 1.0 ",0C)', "Acme Bias", "US", "d"),
    ('(0011,"ACME 1.0",0C)', "Acme Bias", "US", "k"),
    ('(0011,"ACME 1.0",0D)', "Acme Shift", "US", "k"),
    ('(0011,"ACME 1.0 ",0D)', "Acme Shift", "US", "d"),
    ('(0011,"ACME 1.0 ",0E)', "Acme Scale", "US", "k"),
    ('(0011,"ACME 1.0",0E)', "Acme Scale", "US", "d"),
    ('(0011,"ACMÉ 1.0",01)', "Acme Accented", "US", "k"),
    ('(0043,"GEMS_PARM_01",39)', "Slop Integer 6 To Slop Integer 9", "IS", "k"),
    ('(0043,"GEMS_PARM_01",39)', "Slop Integer 6 To Slop Integer 9", "DS", "k"),
)
SAFE_PRIVATE_POLICY = policy.compose_custom_policy([policy.SAFE_PRIVATE])
# Attributes of the shipped dictionary: two that only it keeps, one that it
# keeps with the VM of a reviewed rule, one that a reviewed rule keeps and it
# does not, and one that it keeps and a reviewed rule removes.
PET_ACTIVITY = ("GEMS_PETD_01", 0x0009, 0x38)
FRAME_OF_REFERENCE = ("GEMS_ACQU_01", 0x0019, 0x0F)
SLOP_INTEGERS = ("GEMS_PARM_01", 0x0043, 0x39)
SHAPE = ("Philips Imaging DD 001", 0x2001, 0x67)
TIMESTAMP = ("GEMS_ACQU_01", 0x0019, 0x24)


def _rules():
    text = io.StringIO(newline="")
    csv.writer(text).writerows((HEADER, *DICTIONARY))
    content = text.getvalue().encode("utf-8")
    return tcia_safe_private_rules(parse_tcia_private_tags(content, "test.csv"))


def _rule(rules, key, vr=None):
    creator, group, element = key
    return rules.rule_for(group, creator, element, vr)


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_kept_row_takes_the_handling_of_its_vr_and_one_value():
    rules = _rules()

    count = _rule(rules, (ACME, 0x0011, 0x01), "US")
    label = _rule(rules, (ACME, 0x0011, 0x05), "LO")

    assert (count.vr, count.vm, count.handling) == ("US", "1", Handling.NUMERIC)
    assert (count.basis, count.note) == (Basis.TCIA, "Acme Count")
    # Text is kept by the dictionary, to be cleaned under Clean Descriptors.
    assert label.handling is Handling.TEXT
    assert count in rules.retained() and label in rules.retained()


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_row_that_does_not_keep_removes_its_attribute():
    rules = _rules()

    operator = _rule(rules, (ACME, 0x0011, 0x04), "LO")
    # Two rows for one VR that disagree keep nothing, in either order.
    mode = _rule(rules, (ACME, 0x0011, 0x08), "CS")
    state = _rule(rules, (ACME, 0x0011, 0x0A), "CS")

    assert operator.handling is Handling.REMOVE
    assert mode.handling is Handling.REMOVE and state.handling is Handling.REMOVE
    assert not {operator, mode, state} & set(rules.retained())


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_the_rule_is_that_of_the_vr_as_written_or_the_one_readable_vr():
    rules = _rules()
    factor, offset = (ACME, 0x0011, 0x02), (ACME, 0x0011, 0x03)

    assert _rule(rules, factor, "DS").handling is Handling.NUMERIC
    assert _rule(rules, factor, "OB").handling is Handling.REMOVE
    assert _rule(rules, factor, "FL") is None
    # Without a written VR, DS is the only VR that reads the value.
    assert _rule(rules, factor) == _rule(rules, factor, "DS")
    # SL and SS both read it, so neither does.
    assert _rule(rules, offset, "SS").handling is Handling.NUMERIC
    assert _rule(rules, offset) is None


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_reviewed_rule_for_the_same_vr_gives_its_handling_and_vm():
    rules = _rules()

    assert _rule(rules, SLOP_INTEGERS, "IS").vm == "4"
    assert _rule(rules, SLOP_INTEGERS, "DS").vm == "1"


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize(
    "key, vr",
    [
        pytest.param((ACME, 0x0011, 0x06), None, id="no-vr"),
        pytest.param((ACME, 0x0011, 0x07), "US", id="nested-only"),
        pytest.param(("ACMÉ 1.0", 0x0011, 0x01), "US", id="creator-not-compared"),
        pytest.param(("acme 1.0", 0x0011, 0x01), "US", id="creator-in-another-case"),
        pytest.param((ACME, 0x0013, 0x01), "US", id="another-group"),
    ],
)
def test_an_attribute_without_a_top_level_row_has_no_rule(key, vr):
    assert _rule(_rules(), key, vr) is None


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_creator_is_compared_without_padding():
    rules = _rules()

    padded = _rule(rules, ("ACME 1.0 \x00", 0x0011, 0x09), "US")

    assert padded is not None and padded.private_creator == ACME
    # Rows for two spellings of one creator meet as one attribute's rows,
    # in either order.
    for element in (0x0B, 0x0C, 0x0D, 0x0E):
        assert _rule(rules, (ACME, 0x0011, element), "US").handling is Handling.REMOVE
        assert _rule(rules, (ACME, 0x0011, element)).handling is Handling.REMOVE


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_the_shipped_dictionary_gives_tcia_rules():
    rules = tcia_safe_private_rules()
    reviewed = load_safe_private_rules()

    assert tcia_safe_private_rules() is rules
    assert all(rule.basis is Basis.TCIA for rule in rules.retained())
    assert all(rule.handling.retains for rule in rules.retained())
    assert _rule(rules, PET_ACTIVITY, "FL").handling is Handling.NUMERIC
    assert _rule(reviewed, PET_ACTIVITY) is None
    assert _rule(rules, FRAME_OF_REFERENCE).vr == "DS"
    assert _rule(rules, SLOP_INTEGERS, "IS").vm == "4"
    # TCIA keeps a timestamp that a reviewed rule removes, with a note.
    tags = tcia_private_tags.load_tcia_private_tags()
    top_level = tags.top_level
    timestamp = top_level[TIMESTAMP]
    assert [row.keeps for row in timestamp if row.vr == "DS"] == [True]
    assert _rule(reviewed, TIMESTAMP).handling is Handling.REMOVE
    assert _rule(rules, TIMESTAMP, "DS").handling is Handling.REMOVE
    # A reviewed rule keeps it; TCIA's dictionary does not.
    assert _rule(reviewed, SHAPE).handling is Handling.CODE
    assert _rule(rules, SHAPE, "CS").handling is Handling.REMOVE
    # No attribute's creator is spelt two ways that differ only by padding.
    spelt = {
        (step.private_creator, step.group, step.element)
        for (step, *nested) in (row.path for row in tags.rows)
        if not nested and step.private_creator is not None
    }
    assert len(spelt) == len(top_level)


def test_element_rules_apply_the_chosen_list():
    reviewed = ElementRules(SAFE_PRIVATE_POLICY)
    tcia = ElementRules(SAFE_PRIVATE_POLICY, safe_private_list=SafePrivateList.TCIA)

    assert reviewed.safe_private_list is SafePrivateList.REVIEWED
    assert isinstance(reviewed.safe_private, SafePrivateRules)
    assert tcia.safe_private_list is SafePrivateList.TCIA
    assert isinstance(tcia.safe_private, TciaSafePrivateRules)
    assert ElementRules(policy.compose_policy("basic")).safe_private_list is None


def test_tcia_s_dictionary_is_refused_without_the_option():
    with pytest.raises(policy.PolicyError, match="Retain Safe Private Option"):
        ElementRules(
            policy.compose_policy("basic"), safe_private_list=SafePrivateList.TCIA
        )
    with pytest.raises(TypeError, match="SafePrivateList"):
        ElementRules(SAFE_PRIVATE_POLICY, safe_private_list="tcia")


def _instance(*elements):
    """A CT slice with GE PET, GE acquisition, and Philips blocks."""
    dataset = synthetic.ct_slice(0)
    dataset.add_new(0x00090010, "LO", "GEMS_PETD_01")
    dataset.add_new(0x00190010, "LO", "GEMS_ACQU_01")
    dataset.add_new(0x20010010, "LO", "Philips Imaging DD 001")
    for tag, vr, value in elements or (
        (0x00091038, "FL", 1.5),
        (0x0019100F, "DS", "2.5"),
        (0x20011067, "CS", "LINEAR"),
    ):
        dataset.add_new(tag, vr, value)
    return dataset


def _private_actions(dataset, rules, transfer_syntax):
    data = synthetic.written(dataset, transfer_syntax)
    return {
        path.tag: action
        for path, action in private_actions(read_source(data), rules).items()
        if not path.items
    }


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_each_list_keeps_what_its_rules_keep(transfer_syntax):
    tcia = _private_actions(_instance(), tcia_safe_private_rules(), transfer_syntax)
    reviewed = _private_actions(_instance(), load_safe_private_rules(), transfer_syntax)

    assert tcia == {
        "(0009,0010)": "K",
        "(0009,1038)": "K",
        "(0019,0010)": "K",
        "(0019,100F)": "K",
        "(2001,0010)": "X",
        "(2001,1067)": "X",
    }
    assert reviewed == {
        "(0009,0010)": "X",
        "(0009,1038)": "X",
        "(0019,0010)": "X",
        "(0019,100F)": "X",
        "(2001,0010)": "K",
        "(2001,1067)": "K",
    }


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_tcia_rule_reads_a_value_whose_vr_is_not_written_by_its_vr(transfer_syntax):
    data = synthetic.written(_instance(), transfer_syntax)

    plan = private_plan(read_source(data), tcia_safe_private_rules())

    vrs = {path.tag: vr for path, vr in plan.vrs.items() if not path.items}
    if transfer_syntax == synthetic.IMPLICIT_VR_LITTLE_ENDIAN:
        assert vrs == {
            "(0009,0010)": "LO",
            "(0009,1038)": "FL",
            "(0019,0010)": "LO",
            "(0019,100F)": "DS",
        }
    else:
        assert vrs == {}


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_value_that_two_vrs_read_is_kept_only_where_its_vr_is_written(
    transfer_syntax,
):
    dataset = synthetic.ct_slice(0)
    dataset.add_new(0x00110010, "LO", ACME)
    dataset.add_new(0x00111003, "SL", -3)

    actions = _private_actions(dataset, _rules(), transfer_syntax)

    kept = transfer_syntax == synthetic.EXPLICIT_VR_LITTLE_ENDIAN
    assert actions["(0011,1003)"] == ("K" if kept else "X")


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize(
    "element, action",
    [
        pytest.param((0x00091038, "FL", [1.5, 2.5]), "X", id="two-values"),
        pytest.param((0x0019100F, "OB", b"2.5 "), "X", id="as-OB"),
        pytest.param((0x0019100F, "UN", b"2.5 "), "K", id="as-UN"),
        pytest.param((0x0019100F, "FD", 2.5), "X", id="another-vr"),
        pytest.param((0x0019100F, "DS", "2.5\\3.5"), "X", id="ds-two-values"),
    ],
)
def test_a_tcia_rule_checks_the_vr_and_number_of_values(element, action):
    actions = _private_actions(
        _instance(element),
        tcia_safe_private_rules(),
        synthetic.EXPLICIT_VR_LITTLE_ENDIAN,
    )

    assert actions[f"({element[0] >> 16:04X},{element[0] & 0xFFFF:04X})"] == action


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_block_declared_unsafe_is_removed_under_tcia_s_dictionary(transfer_syntax):
    dataset = _instance()
    declaration = pydicom.Dataset()
    declaration.add_new(0x00080301, "US", 0x0009)
    declaration.add_new(0x00080302, "LO", "GEMS_PETD_01")
    declaration.add_new(0x00080303, "CS", "UNSAFE")
    dataset.add_new(0x00080300, "SQ", pydicom.Sequence([declaration]))

    actions = _private_actions(dataset, tcia_safe_private_rules(), transfer_syntax)

    assert actions["(0009,1038)"] == "X"
    assert actions["(0019,100F)"] == "K"


def _transform(safe_private_list):
    return InstanceTransform(
        SAFE_PRIVATE_POLICY,
        KEY,
        safe_private_list=safe_private_list,
        unvalidated_policy=True,
    )


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "MIDI-BP-01")
@pytest.mark.parametrize("transfer_syntax", TRANSFER_SYNTAXES)
def test_a_run_that_chooses_tcia_s_dictionary_writes_what_it_keeps(transfer_syntax):
    data = synthetic.written(_instance(), transfer_syntax)

    result = _transform(SafePrivateList.TCIA)(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Transformed), result
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written[0x00091038].value == pytest.approx(1.5)
    assert written[0x0019100F].value == "2.5"
    assert 0x20011067 not in written and 0x20010010 not in written
    condition = release_condition(result.evidence, result.data)
    assert condition.decision is Decision.RELEASE, condition.reasons


def test_the_method_digest_records_the_list_under_the_option():
    basic = policy.compose_policy("basic")

    def components(chosen, selected=SAFE_PRIVATE_POLICY):
        return method_digest.method_digest_components(
            selected,
            vocabulary=None,
            reviewed_roi_names=None,
            safe_private_list=chosen,
        )

    reviewed = components(SafePrivateList.REVIEWED)
    tcia = components(SafePrivateList.TCIA)

    assert (reviewed.safe_private_list, tcia.safe_private_list) == ("reviewed", "tcia")
    assert reviewed.method_digest != tcia.method_digest
    assert tcia.method_digest == method_digest.method_digest(
        SAFE_PRIVATE_POLICY,
        vocabulary=None,
        reviewed_roi_names=None,
        safe_private_list=SafePrivateList.TCIA,
    )
    assert components(SafePrivateList.REVIEWED, basic).safe_private_list is None
    with pytest.raises(ValueError, match="Retain Safe Private Option"):
        components(SafePrivateList.TCIA, basic)
    with pytest.raises(TypeError, match="SafePrivateList"):
        components("tcia")


def test_the_run_s_report_and_statement_record_tcia_s_dictionary():
    transform = _transform(SafePrivateList.TCIA)

    text = transform.reporter((), {}, qc_pack.new_reference())
    report = json.loads(text)
    statement = transform.reporter.conformance_statement()
    readable = release_report_markdown.to_markdown(text)

    assert report["method"]["safe_private_list"] == "tcia"
    assert "| Safe private list | `tcia` |" in readable
    assert tcia_private_tags.PIN.sha256 in statement
    assert tcia_private_tags.ACKNOWLEDGEMENT in statement
    assert "| GEMS_PETD_01 | (0009,xx38) | FL | 1 | numeric | Tracer Activity |" in (
        statement
    )
    assert "reviewed rules of `safe_private.toml` settle" not in statement
    # A reader of the statement has no design document to look a number up in.
    assert re.search(r"\bD-\d{3}\b", statement) is None


def test_the_default_statement_lists_the_reviewed_rules():
    statement = conformance.conformance_statement(SAFE_PRIVATE_POLICY, vocabulary=None)

    text = conformance_markdown.render_markdown(statement)

    assert statement.safe_private_list is SafePrivateList.REVIEWED
    assert "reviewed rules of `safe_private.toml` settle" in text
    assert tcia_private_tags.PIN.sha256 not in text
    assert tcia_private_tags.ACKNOWLEDGEMENT not in text
    with pytest.raises(ValueError, match="Retain Safe Private Option"):
        conformance.conformance_statement(
            policy.compose_policy("basic"),
            vocabulary=None,
            safe_private_list=SafePrivateList.TCIA,
        )
    with pytest.raises(TypeError, match="SafePrivateList"):
        conformance.conformance_statement(
            SAFE_PRIVATE_POLICY, vocabulary=None, safe_private_list="tcia"
        )


def test_the_command_line_chooses_the_list():
    parser = command.build_parser()

    assert parser.parse_args(["s", "r", "--qc-pack", "q"]).safe_private_list == (
        "reviewed"
    )
    assert (
        parser.parse_args(
            ["s", "r", "--qc-pack", "q", "--safe-private-list", "tcia"]
        ).safe_private_list
        == "tcia"
    )


def test_the_command_line_refuses_a_list_it_cannot_apply(tmp_path, capsys, monkeypatch):
    # No release enables a preset yet.
    monkeypatch.setattr(
        policy, "ENABLED_PRESETS", frozenset({"basic", "basic-clean-descriptors"})
    )
    monkeypatch.setattr(policy, "ENABLED_OPTIONS", frozenset({"clean_descriptors"}))
    arguments = [str(tmp_path / "s"), str(tmp_path / "r"), "--qc-pack", "q"]

    with pytest.raises(SystemExit) as unknown:
        command.main([*arguments, "--safe-private-list", "TCIA"])
    status = command.main([*arguments, "--safe-private-list", "tcia"])
    # Refused before the Clean Descriptors resources, which do not exist.
    with pytest.raises(command.TransformNotBuilt, match="Retain Safe Private"):
        command.transform_for(
            "basic-clean-descriptors",
            DeidKey.generate(),
            source=tmp_path / "s",
            release=tmp_path / "r",
            qc_pack=tmp_path / "q",
            safe_private_list=SafePrivateList.TCIA,
        )

    assert unknown.value.code == command.EXIT_USAGE
    assert status == command.EXIT_NOT_RUN
    assert "only under the Retain Safe Private Option" in capsys.readouterr().err
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize(
    "arguments, message",
    [
        pytest.param(
            {"safe_private_list": "TCIA"}, '"reviewed" or "tcia"', id="unknown"
        ),
        pytest.param(
            {"safe_private_list": "tcia"}, "only under Retain Safe Private", id="basic"
        ),
        pytest.param(
            {"safe_private_list": "tcia", "options": ["clean_descriptors"]},
            "only under Retain Safe Private",
            id="options",
        ),
    ],
)
def test_the_library_refuses_a_list_it_cannot_apply(tmp_path, arguments, message):
    with pytest.raises(ValueError, match=message):
        api.deidentify(
            tmp_path / "source",
            tmp_path / "release",
            qc_pack=tmp_path / "qc",
            **arguments,
        )
    assert not any(tmp_path.iterdir())
