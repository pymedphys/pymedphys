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

"""Reviewed rules for the Retain Safe Private Option."""

import collections
import re

from pymedphys._imports import pytest, tomlkit

from pymedphys._dicom.deidentify import safe_private, standard
from pymedphys._dicom.deidentify.safe_private import Basis, Handling

PET = "Philips PET Private Group"
GE_ACQUISITION = "GEMS_ACQU_01"
GE_SERIES = "GEMS_SERS_01"
# The departures from the handling of the VR, checked by hand against the
# meanings that Table E.3.10-1 gives in 2026d: each is a time or timestamps
# that can be an absolute time of the acquisition.
DEPARTURES = {
    (GE_ACQUISITION, 0x0019, 0x24): Handling.REMOVE,  # Mid Scan Time [sec]
    ("SIEMENS Ultrasound SC2000", 0x0149, 0x02): Handling.REMOVE,
    ("SIEMENS Ultrasound SC2000", 0x0149, 0x03): Handling.REMOVE,
}
# A valid reviewed addition, for an element that the table does not list.
ADDITION = {
    "private_creator": GE_SERIES,
    "tag": "(0025,xx06)",
    "vr": "SS",
    "vm": "1",
    "handling": "numeric",
    "source": "A vendor's published DICOM Conformance Statement",
    "note": "A count of images.",
}


@pytest.fixture(name="rules", scope="module")
def _rules():
    return safe_private.load_safe_private_rules()


def _key(row):
    match = standard.PRIVATE_TAG_PATTERN.fullmatch(row.tag)
    return row.private_creator, int(match.group(1), 16), int(match.group(2), 16)


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_every_row_of_table_e3_10_1_has_one_rule_with_its_vr_and_vm(rules):
    table = standard.load_table_e3_10_1()

    assert rules.edition == table.edition
    assert rules.acknowledgement == f"DICOM PS3.15 {table.edition}, © NEMA"
    # The file groups the rows by private creator.
    assert len(rules.rules) == len(table.attributes)
    assert rules.rules.keys() == {_key(row) for row in table.attributes}
    for row in table.attributes:
        rule = rules.rules[_key(row)]
        assert (rule.vr, rule.vm, rule.basis) == (row.vr, row.vm, Basis.TABLE)
        assert rule.tag.upper() == row.tag.upper()
        assert rule.source == ""


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "MIDI-BP-13")
def test_each_rule_takes_the_handling_of_its_vr_unless_its_note_says_why(rules):
    departures = {
        key: rule.handling
        for key, rule in rules.rules.items()
        if rule.handling is not safe_private.default_handling(rule.vr)
    }

    assert departures == DEPARTURES
    assert all(rules.rules[key].note for key in DEPARTURES)
    assert not any(
        rule.note for key, rule in rules.rules.items() if key not in DEPARTURES
    )


@pytest.mark.deid_requirement("PS3.15-E.3.10-01", "MIDI-BP-13")
def test_bulk_binary_data_and_attributes_without_one_vr_are_removed(rules):
    # The Note to Table E.3.10-1 calls bulk binary data particularly unsafe,
    # and a value whose VR the table does not give cannot be checked.
    removed = {
        key for key, rule in rules.rules.items() if rule.vr in ("OB", "OW", "OW/OB", "")
    }

    assert len(removed) == 25
    assert all(rules.rules[key].handling is Handling.REMOVE for key in removed)
    assert {
        key for key, rule in rules.rules.items() if rule.handling is Handling.REMOVE
    } == removed | DEPARTURES.keys()


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_the_examples_that_e3_10_gives_are_retained_as_numbers(rules):
    # E.3.10 names "CT helical span pitch" and "PET SUV rescale factors".
    for key in (
        (PET, 0x7053, 0x00),  # SUV Factor
        (PET, 0x7053, 0x09),  # Activity Concentration Factor
        ("ELSCINT1", 0x01F1, 0x26),  # Pitch
        (GE_ACQUISITION, 0x0019, 0x23),  # Table Speed [mm/rotation]
        ("GEMS_PARM_01", 0x0043, 0x39),  # B Value, among others
    ):
        assert rules.rules[key].handling is Handling.NUMERIC, key


def test_the_handlings_are_counted_by_vr(rules):
    counts = collections.Counter(rule.handling for rule in rules.rules.values())

    assert counts == {
        Handling.NUMERIC: 280,
        Handling.CODE: 65,
        Handling.SEQUENCE: 55,
        Handling.TEXT: 44,
        Handling.REMOVE: 28,
        Handling.UID: 7,
    }
    assert rules.retained() == tuple(
        rule for rule in rules.rules.values() if rule.handling is not Handling.REMOVE
    )
    assert len(rules.retained()) == 451


@pytest.mark.parametrize(
    "vr, handling",
    [
        ("DS", Handling.NUMERIC),
        ("IS", Handling.NUMERIC),
        ("FD", Handling.NUMERIC),
        ("AT", Handling.NUMERIC),
        ("UV", Handling.NUMERIC),
        ("CS", Handling.CODE),
        ("UI", Handling.UID),
        ("LO", Handling.TEXT),
        ("UT", Handling.TEXT),
        ("SQ", Handling.SEQUENCE),
        ("OB", Handling.REMOVE),
        ("OW/OB", Handling.REMOVE),
        ("UN", Handling.REMOVE),
        ("PN", Handling.REMOVE),
        ("DA", Handling.REMOVE),
        ("", Handling.REMOVE),
    ],
)
def test_the_handling_of_each_vr_follows_the_note_to_table_e3_10_1(vr, handling):
    assert safe_private.default_handling(vr) is handling
    assert handling.retains is (handling is not Handling.REMOVE)


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_rule_applies_in_whichever_block_its_creator_reserves(rules):
    # The rule names no block, so every block that the creator reserves finds
    # it; only the creator's padding is ignored.
    rule = rules.rules[(GE_ACQUISITION, 0x0019, 0x23)]

    assert rule.tag == "(0019,xx23)"
    for creator in (GE_ACQUISITION, GE_ACQUISITION + " ", GE_ACQUISITION + "\x00"):
        assert rules.rule_for(0x0019, creator, 0x23) is rule
    for group, creator, element in (
        (0x0019, GE_ACQUISITION.lower(), 0x23),  # another case
        (0x0019, " " + GE_ACQUISITION, 0x23),  # a leading space is significant
        (0x0019, "GEMS_ACQU_02", 0x23),  # another creator
        (0x0021, GE_ACQUISITION, 0x23),  # another group
        (0x0019, GE_ACQUISITION, 0x25),  # an element the table does not list
    ):
        assert rules.rule_for(group, creator, element) is None


@pytest.mark.parametrize(
    "group, element",
    [
        (0x0018, 0x23),  # an even group
        (0x0001, 0x23),  # an odd group that PS3.5 excludes from private use
        (0xFFFF, 0x23),
        (0x10019, 0x23),
        (-1, 0x23),
        (0x0019, 0x100),
        (0x0019, -1),
    ],
)
def test_a_lookup_outside_a_private_block_is_refused(rules, group, element):
    with pytest.raises(ValueError):
        rules.rule_for(group, GE_ACQUISITION, element)


def _document():
    return tomlkit.parse(
        safe_private.SAFE_PRIVATE_PATH.read_text(encoding="utf-8")
    ).unwrap()


def _write(path, document):
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


def _set(**fields):
    return lambda document: document.update(fields)


def _drop(field):
    return lambda document: document.pop(field)


def _table(index=0, **fields):
    return lambda document: document["table"][index].update(fields)


def _element(table=0, index=0, **fields):
    return lambda document: document["table"][table]["elements"][index].update(fields)


def _without_note(table, index):
    return lambda document: document["table"][table]["elements"][index].pop("note")


def _addition(**fields):
    return lambda document: document.setdefault("addition", []).append(
        {**ADDITION, **fields}
    )


def _addition_without(field):
    def change(document):
        addition = dict(ADDITION)
        del addition[field]
        document["addition"] = [addition]

    return change


def _repeat_table(document):
    document["table"].append(dict(document["table"][0]))


def _repeat_element(document):
    elements = document["table"][0]["elements"]
    elements.append(dict(elements[0]))


def _drop_element(document):
    document["table"][0]["elements"].pop()


def _drop_table(document):
    document["table"].pop()


def _repeat_addition(document):
    document["addition"] = [dict(ADDITION), dict(ADDITION)]


@pytest.mark.parametrize(
    "change, message",
    [
        (_set(schema="other/1"), "is not a pymedphys-deid-safe-private/1 file"),
        (_set(additions=[]), "has an unknown field additions"),
        (_set(edition="2099a"), "does not cover the edition of Table E.3.10-1"),
        (_drop("acknowledgement"), "lacks the acknowledgement DICOM PS3.15"),
        (_set(table={}), "table is not an array of tables"),
        (_set(addition={}), "addition is not an array of tables"),
        (
            _table(note="x"),
            "table rule 1 does not have exactly the fields private_creator and elements",
        ),
        (
            _table(private_creator="Philips PET Private Group "),
            "table rule 1 has a private creator that Table E.3.10-1 does not list",
        ),
        (_repeat_table, "repeats a private creator of an earlier table rule"),
        (_table(elements=[]), "table rule 1 has no array of elements"),
        (_table(elements={}), "table rule 1 has no array of elements"),
        (
            _element(source="x"),
            "table rule 1 element 1 does not have exactly the fields tag, vr, vm, "
            "and handling, and optionally note",
        ),
        (
            _element(tag="(7053,XX00)"),
            "has a tag that is not a private Data Element in upper case",
        ),
        (
            _element(table=2, index=3, tag="(0019,xx9e)"),
            "has a tag that is not a private Data Element in upper case",
        ),
        (_element(tag="(7054,xx00)"), "has a tag that is not a private Data Element"),
        (
            _element(tag="(7053,xx01)"),
            "is not a row of Table E.3.10-1 for its private creator",
        ),
        (_element(vr="FL"), "has a VR or VM other than Table E.3.10-1 gives"),
        (_element(vm="1-n"), "has a VR or VM other than Table E.3.10-1 gives"),
        (_element(handling="keep"), "has a handling that is not one of numeric"),
        (
            _element(handling="code"),
            "has the handling code, which cannot check a value of its VR",
        ),
        (
            _element(handling="remove"),
            "departs from the handling of its VR without a note that says why",
        ),
        (
            _without_note(2, 1),
            "table rule 3 element 2 departs from the handling of its VR without a note",
        ),
        (_element(note=" "), "has a note that is not non-empty text"),
        (_repeat_element, "repeats Philips PET Private Group (7053,xx00)"),
        (_drop_element, "has no rule for Philips PET Private Group (7053,xx09)"),
        (_drop_table, "or for 3 other rows"),
        (
            _addition_without("source"),
            "addition 1 does not have exactly the fields private_creator, tag, vr, "
            "vm, handling, source, and note",
        ),
        (_addition(extra="x"), "does not have exactly the fields"),
        (_addition(private_creator=""), "has a private creator that is not non-empty"),
        (
            _addition(private_creator=GE_SERIES + " "),
            "has a private creator with trailing padding",
        ),
        (
            _addition(private_creator="A\\B"),
            "has a private creator that VR LO cannot hold",
        ),
        (
            _addition(private_creator="A\nB"),
            "has a private creator that VR LO cannot hold",
        ),
        (
            _addition(private_creator="A" * 65),
            "has a private creator that VR LO cannot hold",
        ),
        *(
            (
                _addition(private_creator=f"A{character}B"),
                "has a private creator outside printable ISO 646",
            )
            for character in ("\x1b", "\x7f", "\u00e9", "\u3042")
        ),
        (_addition(tag="(0025,1006)"), "has a tag that is not a private Data Element"),
        (_addition(tag="(0025,xx6a)"), "has a tag that is not a private Data Element"),
        (_addition(vr="OW/OB"), "has a VR that is not one PS3.5 VR"),
        (_addition(vr=""), "has a VR that is not one PS3.5 VR"),
        (_addition(vm="2-1"), "has a VM that is not of the form"),
        (_addition(handling="remove"), "has a handling that does not retain its value"),
        (_addition(handling="keep"), "has a handling that does not retain its value"),
        (
            _addition(vr="LO"),
            "has the handling numeric, which cannot check a value of its VR",
        ),
        (_addition(source=" "), "has a source or note that is not non-empty text"),
        (_addition(note=""), "has a source or note that is not non-empty text"),
        (
            _addition(private_creator=GE_SERIES, tag="(0025,xx07)", vr="SL"),
            "addition 1 adds a row of Table E.3.10-1, which a table rule covers",
        ),
        (_repeat_addition, "addition 2 repeats GEMS_SERS_01 (0025,xx06)"),
    ],
)
def test_a_malformed_file_is_rejected(tmp_path, change, message):
    document = _document()
    change(document)

    with pytest.raises(safe_private.SafePrivateRuleError, match=re.escape(message)):
        safe_private.load_safe_private_rules(
            _write(tmp_path / "safe_private.toml", document)
        )


def test_a_file_that_cannot_be_read_is_rejected(tmp_path):
    (tmp_path / "invalid.toml").write_text("schema = ", encoding="utf-8")

    for path in (tmp_path / "missing.toml", tmp_path / "invalid.toml"):
        with pytest.raises(
            safe_private.SafePrivateRuleError, match="could not be read"
        ):
            safe_private.load_safe_private_rules(path)


def test_a_reviewed_addition_is_read_with_its_source(tmp_path):
    document = _document()
    _addition()(document)

    loaded = safe_private.load_safe_private_rules(
        _write(tmp_path / "safe_private.toml", document)
    )
    rule = loaded.rule_for(0x0025, GE_SERIES, 0x06)

    assert rule == safe_private.SafePrivateRule(
        private_creator=GE_SERIES,
        group=0x0025,
        element=0x06,
        vr="SS",
        vm="1",
        handling=Handling.NUMERIC,
        basis=Basis.REVIEWED,
        note=ADDITION["note"],
        source=ADDITION["source"],
    )
    assert list(loaded.rules)[-1] == (GE_SERIES, 0x0025, 0x06)
    assert rule in loaded.retained()
    # The rules are read-only.
    with pytest.raises(TypeError):
        loaded.rules[(GE_SERIES, 0x0025, 0x06)] = rule  # type: ignore[index]


def test_the_shipped_file_has_no_reviewed_addition(rules):
    # Additions need a reviewed public source. TCIA's Private Tag Dictionary
    # is a separate list, not a source of additions.
    assert {rule.basis for rule in rules.rules.values()} == {Basis.TABLE}
