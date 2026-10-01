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

"""Reviewed supplementary (L2) actions for attributes that Table E.1-1 omits."""

import collections
import dataclasses
import itertools
import re
import types

from pymedphys._imports import pytest, tomlkit

from pymedphys._dicom.deidentify import (
    actions,
    iods,
    policy,
    standard,
    supplementary_actions,
    temporal_roles,
    uid_roles,
)

# The actions of Table E.1-1a that never keep the value as received.
REMOVING_ACTIONS = {"X", "Z", "D", "X/Z", "Z/D", "X/D", "X/Z/D"}
TEXT_VRS = {"LO", "SH", "LT", "ST", "UC", "UT"}
# The IODs of the first supported release.
SUPPORTED_IODS = ("CT Image", "RT Dose", "RT Plan", "RT Structure Set")
CLEAN_DESCRIPTORS = "clean_descriptors"
DEVICE_IDENTITY = "retain_device_identity"
MODIFIED_DATES = "retain_longitudinal_modified_dates"
DEIDENTIFICATION_METHOD = "(0012,0063)"
ALTERNATIVE_CALENDAR_DATES = ("(0010,0033)", "(0010,0034)")

# Examples of each group of text attributes, from the design document.
OPERATOR_TEXT = (
    "(300A,00C2)",  # Beam Name
    "(300A,00FE)",  # Block Name
    "(300A,0183)",  # Patient Setup Label
    "(3004,0006)",  # Dose Comment
    "(300A,0402)",  # Setup Image Comment
    "(0040,A160)",  # Text Value
)
ACCESSORY_IDENTIFIERS = (
    "(300A,00D4)",  # Wedge ID
    "(300A,00F5)",  # Block Tray ID
    "(300A,0108)",  # Applicator ID
    "(300A,00E5)",  # Compensator ID
    "(300A,00DC)",  # Bolus ID
    "(300A,0421)",  # General Accessory ID
)
# The text attributes that the supported IODs use and Table E.1-1 omits that
# are removed by Type under every option, checked by hand against the 2026d
# PS3.3: names and identifiers of people, organisations, records, and
# networks, identifiers that a device reads, and the text of overlays.
REMOVED_UNDER_EVERY_OPTION = {
    "(0008,0116)",  # Coding Scheme Responsible Organization
    "(0008,0122)",  # Mapping Resource Name
    "(0010,0214)",  # Strain Stock Number
    "(0010,0217)",  # Strain Source
    "(0010,2295)",  # Breed Registration Number
    "(0018,1803)",  # NTP Source Address
    "(0024,0202)",  # Algorithm Source
    "(0040,0031)",  # Local Namespace Entity ID
    "(0040,0032)",  # Universal Entity ID
    "(0040,E001)",  # HL7 Instance Identifier
    "(0088,0130)",  # Storage Media File-set ID
    "(300A,00F9)",  # Accessory Code
    "(300A,0355)",  # Tray Accessory Code
    "(60xx,0022)",  # Overlay Description
    "(60xx,1500)",  # Overlay Label
}
# Every text attribute that the supported IODs use, Table E.1-1 omits, and
# the Basic Profile keeps, checked by hand against the 2026d PS3.3: coded
# values, and technical values that the equipment or software writes.
KEPT_TEXT = {
    "(0008,0070)",  # Manufacturer
    "(0008,0100)",  # Code Value
    "(0008,0102)",  # Coding Scheme Designator
    "(0008,0103)",  # Coding Scheme Version
    "(0008,0104)",  # Code Meaning
    "(0008,0112)",  # Coding Scheme Registry
    "(0008,0114)",  # Coding Scheme External ID
    "(0008,0119)",  # Long Code Value
    "(0008,0302)",  # Private Creator Reference
    "(0008,030C)",  # Private Data Element Name
    "(0008,030D)",  # Private Data Element Keyword
    "(0008,1090)",  # Manufacturer's Model Name
    "(0010,0213)",  # Strain Nomenclature
    "(0010,0223)",  # Genetic Modifications Nomenclature
    "(0012,0063)",  # De-identification Method, which the engine adds to
    "(0018,1020)",  # Software Versions
    "(0018,1160)",  # Filter Type
    "(0018,1210)",  # Convolution Kernel
    "(0028,1054)",  # Rescale Type
    "(0066,0031)",  # Algorithm Version
    "(0072,0054)",  # Selector Sequence Pointer Private Creator
    "(0072,0056)",  # Selector Attribute Private Creator
    "(3002,0052)",  # Fluence Mode ID
    "(300A,007B)",  # Fraction Pattern
    "(300A,0226)",  # Source Isotope Name
    "(3010,001A)",  # Manufacturer's Model Version
    "(3010,001D)",  # Device Alternate Identifier Format
    "(60xx,0045)",  # Overlay Subtype
}


def _dictionary():
    return {
        attribute.tag: attribute
        for attribute in standard.load_data_dictionary().attributes
    }


def _table_e1_1():
    return {row.tag: row for row in standard.load_table_e1_1().attributes}


def _supported_text():
    """Return the text attributes that a supported IOD uses, at any depth."""
    dictionary = _dictionary()
    tables = iods.load_iod_tables()
    return {
        definition.tag
        for name in SUPPORTED_IODS
        for definition in tables.iods[name].definitions
        if TEXT_VRS.intersection(dictionary[definition.tag].vrs)
    }


def _omitted_text():
    """Return the text attributes that a supported IOD uses and Table E.1-1 omits.

    Derived here independently of the loader: Table E.1-1 lists none of the
    supported IODs' text attributes by a masked tag, such as the Curve group's
    (50xx,xxxx), so an exact comparison of tags suffices.
    """
    return _supported_text() - set(_table_e1_1())


def _rules():
    return supplementary_actions.load_supplementary_actions().rules


def _custom_option_sets():
    """Every set of the targeted options that a custom policy accepts."""
    return [
        subset
        for size in range(len(policy.TARGET_OPTIONS) + 1)
        for subset in itertools.combinations(policy.TARGET_OPTIONS, size)
        if not {DEVICE_IDENTITY, MODIFIED_DATES} <= set(subset)
    ]


def _every_policy():
    return [policy.compose_policy(preset) for preset in policy.PRESETS] + [
        policy.compose_custom_policy(options) for options in _custom_option_sets()
    ]


def test_every_person_name_that_table_e1_1_omits_has_an_action():
    listed = _table_e1_1()
    omitted = {
        tag
        for tag, attribute in _dictionary().items()
        if "PN" in attribute.vrs and tag not in listed
    }

    # Checked by hand against the 2026d PS3.6 and PS3.15.
    assert omitted == {"(0014,0104)", "(0014,2006)", "(0040,A067)"}
    assert omitted <= set(supplementary_actions.load_supplementary_actions().rules)


def test_the_basic_profile_keeps_no_person_name():
    # Table E.1-1 and the supplementary actions together give every person
    # name in the dictionary an action that removes or replaces it.
    listed = _table_e1_1()
    rules = supplementary_actions.load_supplementary_actions().rules
    basic = {
        tag: listed[tag].basic_profile if tag in listed else rules[tag].action
        for tag, attribute in _dictionary().items()
        if "PN" in attribute.vrs
    }

    assert len(basic) == 32
    assert set(basic.values()) <= REMOVING_ACTIONS


def test_every_text_attribute_a_supported_iod_uses_and_table_e1_1_omits_has_a_rule():
    omitted = _omitted_text()

    # Checked by hand against the 2026d PS3.3, PS3.6, and PS3.15.
    assert len(omitted) == 110
    assert omitted <= set(_rules())
    assert {"(0008,0100)", "(300A,00C2)", "(60xx,1500)"} <= omitted


def test_the_rules_for_omitted_text_fall_in_the_reviewed_groups():
    rules = _rules()
    groups = collections.Counter(
        (rules[tag].action, tuple(rules[tag].options.items()))
        for tag in _omitted_text()
    )

    assert groups == {
        # Operator-typed labels and text.
        ("X/Z/D", ((CLEAN_DESCRIPTORS, "C"),)): 46,
        # Accessory and equipment identifiers.
        ("X/Z/D", ((DEVICE_IDENTITY, "K"),)): 19,
        # Coded and technical values, and De-identification Method.
        ("K", ()): 28,
        # Names and identifiers of people, organisations, records, and
        # networks, identifiers that a device reads, and the text of overlays.
        ("X/Z/D", ()): 15,
        # Patient's Birth and Death Dates in Alternative Calendar.
        ("X", ()): 2,
    }


def test_names_identifiers_and_overlay_text_are_removed_under_every_option():
    rules = _rules()

    assert {
        tag
        for tag in _omitted_text()
        if rules[tag].action == "X/Z/D" and not rules[tag].options
    } == REMOVED_UNDER_EVERY_OPTION
    for composed in _every_policy():
        for tag in REMOVED_UNDER_EVERY_OPTION:
            assert composed.supplementary_actions[tag] == "X/Z/D", (
                tag,
                composed.options,
            )


@pytest.mark.parametrize(
    "options, operator_text, accessory_identifier",
    [
        ((), "X/Z/D", "X/Z/D"),
        ((CLEAN_DESCRIPTORS,), "C", "X/Z/D"),
        ((DEVICE_IDENTITY,), "X/Z/D", "K"),
        ((DEVICE_IDENTITY, CLEAN_DESCRIPTORS), "C", "K"),
    ],
)
def test_each_group_takes_the_action_of_its_option(
    options, operator_text, accessory_identifier
):
    composed = policy.compose_custom_policy(options).supplementary_actions

    for tag in OPERATOR_TEXT:
        assert composed[tag] == operator_text, tag
    for tag in ACCESSORY_IDENTIFIERS:
        assert composed[tag] == accessory_identifier, tag
    for tag in KEPT_TEXT:
        assert composed[tag] == "K", tag


@pytest.mark.parametrize(
    "preset, operator_text, accessory_identifier",
    [
        ("basic", "X/Z/D", "X/Z/D"),
        ("public-release", "C", "X/Z/D"),
        ("tps-import", "C", "K"),
    ],
)
def test_each_preset_gives_each_group_its_action(
    preset, operator_text, accessory_identifier
):
    composed = policy.compose_policy(preset).supplementary_actions

    assert {composed[tag] for tag in OPERATOR_TEXT} == {operator_text}
    assert {composed[tag] for tag in ACCESSORY_IDENTIFIERS} == {accessory_identifier}


def test_the_basic_profile_keeps_only_the_reviewed_coded_and_technical_text():
    # Every text attribute of the supported IODs, whether Table E.1-1 lists
    # it or a supplementary rule covers it.
    composed = policy.compose_policy("basic")
    basic = {
        tag: composed.actions.get(tag) or composed.supplementary_actions[tag]
        for tag in _supported_text()
    }

    assert len(basic) == 228
    assert {tag for tag, action in basic.items() if action == "K"} == KEPT_TEXT
    assert set(basic.values()) - {"K"} <= REMOVING_ACTIONS


def test_no_option_keeps_more_than_the_coded_text_and_device_identity():
    rules = _rules()
    device_identity = {
        tag for tag in _omitted_text() if rules[tag].options.get(DEVICE_IDENTITY)
    }
    for composed in _every_policy():
        kept = {
            tag for tag in _omitted_text() if composed.supplementary_actions[tag] == "K"
        }
        expected = KEPT_TEXT | (
            device_identity if DEVICE_IDENTITY in composed.options else set()
        )
        assert kept == expected, composed.options


@pytest.mark.parametrize("tag", ALTERNATIVE_CALENDAR_DATES)
def test_the_alternative_calendar_dates_are_removed_under_every_option(tag):
    rule = _rules()[tag]

    assert (rule.action, dict(rule.options)) == ("X", {})
    for composed in _every_policy():
        assert composed.supplementary_actions[tag] == "X", composed.options


def test_deidentification_method_keeps_earlier_values_for_the_engine_to_add_to():
    rule = _rules()[DEIDENTIFICATION_METHOD]

    assert (rule.keyword, rule.action, dict(rule.options)) == (
        "DeidentificationMethod",
        "K",
        {},
    )
    # The rule says that the engine writes the attribute itself.
    assert "the engine keeps the values already present and adds" in rule.note
    for composed in _every_policy():
        assert composed.supplementary_actions[DEIDENTIFICATION_METHOD] == "K"


def test_a_text_attribute_without_a_rule_is_removed_by_type():
    rules = _rules()
    listed = _table_e1_1()
    uncovered = {
        tag
        for tag, attribute in _dictionary().items()
        if TEXT_VRS.intersection(attribute.vrs)
        and tag not in listed
        and tag not in rules
    }

    # Such as Pulse Sequence Name, an MR attribute that no supported IOD uses.
    assert "(0018,9005)" in uncovered
    assert not uncovered & _omitted_text()
    assert supplementary_actions.UNCOVERED_TEXT_ACTION == "X/Z/D"


def test_the_options_override_the_basic_profile_action_of_a_rule():
    effective = actions.effective_supplementary_actions([CLEAN_DESCRIPTORS])
    rules = _rules()

    assert effective.edition == "2026d"
    assert effective.options == (CLEAN_DESCRIPTORS,)
    assert not effective.conflicts
    assert set(effective.actions) == set(rules)
    for tag, rule in rules.items():
        assert effective.actions[tag] == rule.options.get(
            CLEAN_DESCRIPTORS, rule.action
        )
    basic = actions.effective_supplementary_actions()
    assert dict(basic.actions) == {tag: rule.action for tag, rule in rules.items()}


def _with_beam_name_options(given):
    """Return the rules with Beam Name's option actions replaced, unchecked."""
    loaded = supplementary_actions.load_supplementary_actions()
    rules = dict(loaded.rules)
    rules["(300A,00C2)"] = dataclasses.replace(
        rules["(300A,00C2)"], options=types.MappingProxyType(given)
    )
    return dataclasses.replace(loaded, rules=types.MappingProxyType(rules))


def test_a_rule_whose_options_conflict_is_reported_as_a_conflict():
    rules = _with_beam_name_options({DEVICE_IDENTITY: "K", CLEAN_DESCRIPTORS: "C"})
    effective = actions.effective_supplementary_actions(
        [CLEAN_DESCRIPTORS, DEVICE_IDENTITY], rules=rules
    )

    assert [(c.name, c.tag, dict(c.actions)) for c in effective.conflicts] == [
        ("BeamName", "(300A,00C2)", {DEVICE_IDENTITY: "K", CLEAN_DESCRIPTORS: "C"})
    ]
    assert "(300A,00C2)" not in effective.actions
    alone = actions.effective_supplementary_actions([CLEAN_DESCRIPTORS], rules=rules)
    assert not alone.conflicts
    assert alone.actions["(300A,00C2)"] == "C"


def test_a_policy_rejects_a_conflict_between_the_options_of_a_rule(monkeypatch):
    rules = _with_beam_name_options({DEVICE_IDENTITY: "K", CLEAN_DESCRIPTORS: "C"})
    monkeypatch.setattr(actions, "load_supplementary_actions", lambda: rules)

    with pytest.raises(policy.PolicyError, match="no precedence") as raised:
        policy.compose_policy("tps-import")
    assert "(300A,00C2)" in str(raised.value)
    assert (
        policy.compose_policy("public-release").supplementary_actions["(300A,00C2)"]
        == "C"
    )


@pytest.mark.parametrize(
    "tag, keyword, action",
    [
        # Marked DICONDE in PS3.6 and used by none of the generated IODs, so
        # the action suits any Type an IOD gives them.
        ("(0014,0104)", "SecondaryReviewerName", "X/Z/D"),
        ("(0014,2006)", "EvaluatorName", "X/Z/D"),
        # Retired, like the other (Trial) person names, which Table E.1-1
        # removes.
        ("(0040,A067)", "DocumentAuthorTrial", "X"),
        # Kept as received and never set to NO, since the pixel data are
        # unchanged.
        ("(0028,0301)", "BurnedInAnnotation", "K"),
        ("(0028,0302)", "RecognizableVisualFeatures", "K"),
    ],
)
def test_actions(tag, keyword, action):
    rule = supplementary_actions.load_supplementary_actions().rules[tag]

    assert (rule.tag, rule.keyword, rule.action) == (tag, keyword, action)
    assert rule.note


def test_the_vrs_the_roles_files_cover_are_left_to_them():
    # pylint: disable=protected-access
    assert supplementary_actions._ROLE_VRS == (
        uid_roles._FORMAT.vrs | temporal_roles._FORMAT.vrs
    )


def test_every_note_says_why_without_citing_a_decision_number():
    # Decision numbers belong to the design document and its register.
    for rule in supplementary_actions.load_supplementary_actions().rules.values():
        assert rule.note.strip(), rule.tag
        assert not re.search(r"\bD-[0-9]{3}\b", rule.note), rule.tag


def test_the_actions_follow_the_editions_of_the_tables():
    loaded = supplementary_actions.load_supplementary_actions()

    assert loaded.edition == standard.load_data_dictionary().edition
    assert loaded.edition == standard.load_table_e1_1().edition
    assert loaded.edition == iods.load_iod_tables().edition
    assert loaded.acknowledgement == f"DICOM PS3.6 {loaded.edition}, © NEMA"


def test_the_rules_are_read_only():
    rules = supplementary_actions.load_supplementary_actions().rules

    with pytest.raises(TypeError):
        rules["(0010,0010)"] = rules["(0028,0301)"]  # type: ignore[index]


def _document():
    return tomlkit.parse(
        supplementary_actions.SUPPLEMENTARY_ACTIONS_PATH.read_text(encoding="utf-8")
    ).unwrap()


def _write(path, document):
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


def _drop(document, tag):
    document["attribute"] = [
        rule for rule in document["attribute"] if rule["tag"] != tag
    ]


def _first(**fields):
    return lambda document: document["attribute"][0].update(fields)


def _rule(tag, **fields):
    """Return a change that updates the rule for ``tag`` with ``fields``."""

    def change(document):
        (rule,) = [rule for rule in document["attribute"] if rule["tag"] == tag]
        rule.update(fields)

    return change


BEAM_NAME = "(300A,00C2)"


@pytest.mark.parametrize(
    "change, message",
    [
        (
            lambda d: d.update(schema="pymedphys-deid-supplementary-actions/0"),
            "schema",
        ),
        (lambda d: d.update(edition="2099a"), "edition"),
        (lambda d: d.update(acknowledgement="NEMA"), "acknowledgement"),
        (lambda d: d.update(attribute=1), "rules are not an array of tables"),
        (lambda d: d.update(attribute={}), "rules are not an array of tables"),
        (_first(extra=1), "rule 1 does not have"),
        (lambda d: d["attribute"][0].pop("keyword"), "rule 1 does not have"),
        (lambda d: d["attribute"][0].pop("note"), "rule 1 does not have"),
        (_first(tag="(7777,7777)"), "rule 1 is not an attribute of the data"),
        (_first(tag=[]), "rule 1 is not an attribute of the data"),
        (_first(keyword="EvaluatorName"), "rule 1 names"),
        (
            _first(tag="(0010,0010)", keyword="PatientName"),
            "rule 1 is listed in Table E.1-1",
        ),
        # Table E.1-1 lists the whole retired Curve group as (50xx,xxxx).
        (
            _first(tag="(50xx,2500)", keyword="CurveLabel"),
            "rule 1 is listed in Table E.1-1",
        ),
        (
            _first(tag="(50xx,200A)", keyword="TotalTime"),
            "rule 1 is listed in Table E.1-1",
        ),
        (
            _first(tag="(0008,0016)", keyword="SOPClassUID"),
            "rule 1 is of a VR that a roles file covers",
        ),
        (_first(action="retain"), "rule 1 has an action not defined in Table"),
        (_first(action="U*"), "rule 1 has an action not defined in Table"),
        (_first(action=[]), "rule 1 has an action not defined in Table"),
        (_first(note=""), "rule 1 has a note that is not non-empty text"),
        (_first(note=" "), "rule 1 has a note that is not non-empty text"),
        (lambda d: d["attribute"].append(dict(d["attribute"][0])), "repeats"),
        (lambda d: _drop(d, "(0014,2006)"), "has no action for (0014,2006)"),
        # Text attributes that the supported IODs use and Table E.1-1 omits.
        (lambda d: _drop(d, BEAM_NAME), f"has no action for {BEAM_NAME}"),
        (lambda d: _drop(d, "(60xx,1500)"), "has no action for (60xx,1500)"),
        (lambda d: _drop(d, "(0008,0100)"), "has no action for (0008,0100)"),
        # Option actions.
        (_rule(BEAM_NAME, options=1), "has options that are not a table"),
        (_rule(BEAM_NAME, options={}), "has options that are not a table"),
        (_rule(BEAM_NAME, options=[]), "has options that are not a table"),
        (
            _rule(BEAM_NAME, options={"retain_everything": "K"}),
            "has an option that Table E.1-1 does not define",
        ),
        (
            _rule(BEAM_NAME, options={CLEAN_DESCRIPTORS: "clean"}),
            "has an option action not defined in Table E.1-1a",
        ),
        (
            _rule(BEAM_NAME, options={CLEAN_DESCRIPTORS: []}),
            "has an option action not defined in Table E.1-1a",
        ),
        # Defined, but not an action a supplementary rule may give.
        (
            _rule(BEAM_NAME, options={CLEAN_DESCRIPTORS: "K"}),
            "gives clean_descriptors an action other than C",
        ),
        (
            _rule(BEAM_NAME, options={DEVICE_IDENTITY: "C"}),
            "gives retain_device_identity an action other than K",
        ),
        (
            _rule(BEAM_NAME, options={"retain_uids": "K"}),
            "gives an action under retain_uids",
        ),
        (
            _rule(BEAM_NAME, options={MODIFIED_DATES: "C"}),
            "gives an action under retain_longitudinal_modified_dates",
        ),
        (
            _rule(BEAM_NAME, options={DEVICE_IDENTITY: "K", CLEAN_DESCRIPTORS: "C"}),
            "gives different actions under two or more options",
        ),
        # An option action on a rule whose design does not allow one.
        (
            _rule("(0008,0100)", options={CLEAN_DESCRIPTORS: "C"}),
            "has an option action, but its Basic Profile action keeps the value",
        ),
        (
            _rule("(0028,0301)", options={DEVICE_IDENTITY: "K"}),
            "has an option action, but its Basic Profile action keeps the value",
        ),
        (
            _first(options={CLEAN_DESCRIPTORS: "C"}),
            "rule 1 has an option action, but is not a text attribute",
        ),
    ],
)
def test_a_malformed_file_is_rejected(tmp_path, change, message):
    document = _document()
    change(document)

    with pytest.raises(
        supplementary_actions.SupplementaryActionError, match=re.escape(message)
    ):
        supplementary_actions.load_supplementary_actions(
            _write(tmp_path / "supplementary_actions.toml", document)
        )


def test_a_file_that_cannot_be_read_is_rejected(tmp_path):
    with pytest.raises(
        supplementary_actions.SupplementaryActionError, match="could not be read"
    ):
        supplementary_actions.load_supplementary_actions(tmp_path / "missing.toml")


def test_an_option_action_is_read_as_given(tmp_path):
    document = _document()
    _rule(BEAM_NAME, options={CLEAN_DESCRIPTORS: "C"})(document)
    loaded = supplementary_actions.load_supplementary_actions(
        _write(tmp_path / "supplementary_actions.toml", document)
    )

    assert dict(loaded.rules[BEAM_NAME].options) == {CLEAN_DESCRIPTORS: "C"}
    # A rule without options has none, and the options are read-only.
    assert not loaded.rules["(0014,0104)"].options
    with pytest.raises(TypeError):
        loaded.rules[BEAM_NAME].options[DEVICE_IDENTITY] = "K"  # type: ignore[index]


def test_rules_for_iod_tables_of_another_edition_are_rejected(tmp_path, monkeypatch):
    other = dataclasses.replace(iods.load_iod_tables(), edition="2099a")
    monkeypatch.setattr(supplementary_actions, "load_iod_tables", lambda: other)

    with pytest.raises(supplementary_actions.SupplementaryActionError, match="edition"):
        supplementary_actions.load_supplementary_actions(
            _write(tmp_path / "supplementary_actions.toml", _document())
        )


def _with_definition(iod_name, tag):
    """Return the IOD tables with an IOD that defines ``tag`` in a sequence."""
    tables = iods.load_iod_tables()
    definition = iods.AttributeDefinition(
        path=("(300A,00B0)",), tag=tag, name="", type="3", module="", tables=()
    )
    given = dict(tables.iods)
    if iod_name in given:
        given[iod_name] = dataclasses.replace(
            given[iod_name], definitions=(*given[iod_name].definitions, definition)
        )
    else:
        given[iod_name] = iods.IOD(iod_name, "Table A.0-0", (), (definition,))
    return dataclasses.replace(tables, iods=types.MappingProxyType(given))


@pytest.mark.parametrize(
    "iod_name, required",
    [
        # A supported IOD that comes to use Pulse Sequence Name, which has no
        # rule, at any depth, needs a rule for it.
        ("RT Plan", True),
        # An IOD that is not supported does not, even once its Types are
        # generated.
        ("MR Image", False),
    ],
)
def test_only_the_text_of_the_supported_iods_needs_rules(
    tmp_path, monkeypatch, iod_name, required
):
    tables = _with_definition(iod_name, "(0018,9005)")
    monkeypatch.setattr(supplementary_actions, "load_iod_tables", lambda: tables)
    path = _write(tmp_path / "supplementary_actions.toml", _document())

    if required:
        with pytest.raises(
            supplementary_actions.SupplementaryActionError,
            match=re.escape("has no action for (0018,9005)"),
        ):
            supplementary_actions.load_supplementary_actions(path)
    else:
        assert "(0018,9005)" not in (
            supplementary_actions.load_supplementary_actions(path).rules
        )
