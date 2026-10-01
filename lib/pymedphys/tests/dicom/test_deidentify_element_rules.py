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

"""The rule that decides each element's action under a policy.

The expected rules are derived here from the pinned tables and the reviewed
rule files, or checked by hand against the 2026d PS3.3, PS3.5, PS3.6, and
PS3.15, never taken from the module's own output.
"""

import ast
import dataclasses
import functools
import itertools
import pathlib
import re

from pymedphys._imports import hypothesis, pytest

from pymedphys._dicom.deidentify import (
    compound_actions,
    element_rules,
    iods,
    policy,
    standard,
    supplementary_actions,
    uid_roles,
)
from pymedphys._dicom.deidentify.element_rules import (
    ElementRule,
    ElementRules,
    RuleSource,
)

st = hypothesis.strategies

ENGINE = RuleSource.ENGINE
PRIVATE = RuleSource.PRIVATE
TABLE = RuleSource.TABLE
SUPPLEMENTARY = RuleSource.SUPPLEMENTARY
UID_ROLE = RuleSource.UID_ROLE
UNCOVERED_TEXT = RuleSource.UNCOVERED_TEXT
DEFAULT = RuleSource.DEFAULT
NOT_IN_DICTIONARY = RuleSource.NOT_IN_DICTIONARY

PRIVATE_ROW = "(gggg,eeee) where gggg is odd"
RETAIN_SAFE_PRIVATE = "retain_safe_private"
CLEAN_DESCRIPTORS = "clean_descriptors"
SUPPORTED_IODS = ("CT Image", "RT Dose", "RT Plan", "RT Structure Set")
TEXT_VRS = {"LO", "SH", "LT", "ST", "UC", "UT"}
# The VRs whose attributes each have a reviewed rule or role, so that none
# reaches the rule for attributes that no rule covers.
NAME_DATE_TIME_AND_UID_VRS = {"PN", "DA", "DT", "TM", "UI"}
# Odd groups that PS3.5 Section 7.8.1 does not allow for private use.
RESERVED_ODD_GROUPS = (0x0001, 0x0003, 0x0005, 0x0007, 0xFFFF)

# The rule of a representative element at each level, under the Basic
# Profile, checked by hand against the 2026d tables: the element's tag, the
# source, the action, and the entry that gives it.
BASIC_RULES = [
    # The engine's own removals come first.
    ("(0002,0010)", ENGINE, "X", "(0002,eeee)"),  # Transfer Syntax UID
    ("(0002,0003)", ENGINE, "X", "(0002,eeee)"),  # which Table E.1-1 gives U
    ("(0004,1511)", ENGINE, "X", "(0004,eeee)"),  # which Table E.1-1 gives U
    ("(0004,1220)", ENGINE, "X", "(0004,eeee)"),  # Directory Record Sequence
    ("(0008,0000)", ENGINE, "X", "(gggg,0000)"),
    ("(0000,0000)", ENGINE, "X", "(gggg,0000)"),
    ("(0009,0000)", ENGINE, "X", "(gggg,0000)"),  # in a private group
    ("(FFFC,FFFC)", ENGINE, "X", "(FFFC,FFFC)"),  # which Table E.1-1 removes too
    ("(0400,0500)", ENGINE, "X", "(0400,0500)"),  # Encrypted Attributes Sequence
    # Every other element of an odd group, by the Private Attributes row.
    ("(0009,0010)", PRIVATE, "X", PRIVATE_ROW),  # a private creator
    ("(0009,1001)", PRIVATE, "X", PRIVATE_ROW),
    ("(300B,1002)", PRIVATE, "X", PRIVATE_ROW),
    ("(6001,3000)", PRIVATE, "X", PRIVATE_ROW),  # odd, so not an overlay group
    ("(5001,0005)", PRIVATE, "X", PRIVATE_ROW),  # odd, so not a curve group
    ("(FFFD,0010)", PRIVATE, "X", PRIVATE_ROW),
    # Odd groups that are not private fall to the later rules.
    ("(0001,0010)", NOT_IN_DICTIONARY, "X", ""),
    ("(0003,1000)", NOT_IN_DICTIONARY, "X", ""),
    ("(0005,0010)", NOT_IN_DICTIONARY, "X", ""),
    ("(0007,0010)", NOT_IN_DICTIONARY, "X", ""),
    ("(FFFF,0010)", NOT_IN_DICTIONARY, "X", ""),
    # Table E.1-1 by exact tag.
    ("(0010,0010)", TABLE, "Z", "(0010,0010)"),  # Patient's Name
    ("(0010,0020)", TABLE, "Z/D", "(0010,0020)"),  # Patient ID
    ("(0008,0080)", TABLE, "X/Z/D", "(0008,0080)"),  # Institution Name
    ("(0008,0018)", TABLE, "U", "(0008,0018)"),  # SOP Instance UID
    ("(006A,0003)", TABLE, "D", "(006A,0003)"),  # a UI attribute given D
    ("(FFFA,FFFA)", TABLE, "X", "(FFFA,FFFA)"),  # Digital Signatures Sequence
    ("(0072,006D)", TABLE, "D", "(0072,006D)"),  # Selector UN Value
    # Command elements, which Table E.1-1 lists but PS3.6 Table 6-1 does not.
    ("(0000,1000)", TABLE, "X", "(0000,1000)"),  # Affected SOP Instance UID
    ("(0000,1001)", TABLE, "U", "(0000,1001)"),  # Requested SOP Instance UID
    ("(0000,0700)", NOT_IN_DICTIONARY, "X", ""),  # Priority
    # Table E.1-1 by masked tag, only in the repeating groups.
    ("(6000,3000)", TABLE, "X", "(60xx,3000)"),  # Overlay Data
    ("(601E,3000)", TABLE, "X", "(60xx,3000)"),
    ("(6000,4000)", TABLE, "X", "(60xx,4000)"),  # Overlay Comments
    ("(601E,4000)", TABLE, "X", "(60xx,4000)"),
    ("(5000,0005)", TABLE, "X", "(50xx,xxxx)"),  # Curve Dimensions
    ("(501E,3000)", TABLE, "X", "(50xx,xxxx)"),  # Curve Data
    ("(5000,9999)", TABLE, "X", "(50xx,xxxx)"),  # not in PS3.6 Table 6-1
    # Just outside the repeating groups, nothing covers them.
    ("(6020,3000)", NOT_IN_DICTIONARY, "X", ""),
    ("(6020,4000)", NOT_IN_DICTIONARY, "X", ""),
    ("(5020,0005)", NOT_IN_DICTIONARY, "X", ""),
    ("(5FFE,3000)", NOT_IN_DICTIONARY, "X", ""),
    ("(6100,3000)", NOT_IN_DICTIONARY, "X", ""),
    # Supplementary rules, by exact or masked tag.
    ("(300A,00C2)", SUPPLEMENTARY, "X/Z/D", "(300A,00C2)"),  # Beam Name
    ("(0008,0100)", SUPPLEMENTARY, "K", "(0008,0100)"),  # Code Value
    ("(0014,0104)", SUPPLEMENTARY, "X/Z/D", "(0014,0104)"),  # a person name
    ("(0008,041F)", SUPPLEMENTARY, "X/Z/D", "(0008,041F)"),  # a datetime
    ("(0028,0301)", SUPPLEMENTARY, "K", "(0028,0301)"),  # Burned In Annotation
    ("(6000,0022)", SUPPLEMENTARY, "X/Z/D", "(60xx,0022)"),  # Overlay Description
    ("(601E,1500)", SUPPLEMENTARY, "X/Z/D", "(60xx,1500)"),  # Overlay Label
    ("(6020,0022)", NOT_IN_DICTIONARY, "X", ""),
    ("(0008,1190)", SUPPLEMENTARY, "X/Z/D", "(0008,1190)"),  # Retrieve URL
    ("(0010,1021)", SUPPLEMENTARY, "X/Z/D", "(0010,1021)"),  # a code sequence
    ("(0028,2000)", SUPPLEMENTARY, "X/Z/D", "(0028,2000)"),  # ICC Profile
    # UI attributes that Table E.1-1 omits, by their roles.
    ("(0008,0016)", UID_ROLE, "U", "(0008,0016)"),  # SOP Class UID
    ("(0008,1150)", UID_ROLE, "U", "(0008,1150)"),  # Referenced SOP Class UID
    ("(0018,991E)", UID_ROLE, "U", "(0018,991E)"),  # an instance UID
    ("(0400,0510)", UID_ROLE, "U", "(0400,0510)"),
    # Text that no rule covers, such as Pulse Sequence Name, an MR attribute.
    ("(0018,9005)", UNCOVERED_TEXT, "X/Z/D", "(0018,9005)"),
    # The rule for attributes that no rule covers.
    ("(0008,0060)", DEFAULT, "K", "(0008,0060)"),  # Modality, CS
    ("(0028,0009)", DEFAULT, "K", "(0028,0009)"),  # Frame Increment Pointer, AT
    ("(300A,00B0)", DEFAULT, "K", "(300A,00B0)"),  # Beam Sequence, SQ
    ("(0028,0030)", DEFAULT, "K", "(0028,0030)"),  # Pixel Spacing, DS
    ("(0028,0010)", DEFAULT, "K", "(0028,0010)"),  # Rows, US
    ("(0028,0106)", DEFAULT, "K", "(0028,0106)"),  # US or SS
    ("(6000,0010)", DEFAULT, "K", "(60xx,0010)"),  # Overlay Rows
    ("(7FE0,0010)", DEFAULT, "X", "(7FE0,0010)"),  # Pixel Data, without an IOD
    ("(0008,0202)", DEFAULT, "X", "(0008,0202)"),  # a placeholder without a VR
    ("(FFFE,E000)", DEFAULT, "X", "(FFFE,E000)"),  # Item, without a VR
    # Not in the pinned data dictionary.
    ("(0008,0002)", NOT_IN_DICTIONARY, "X", ""),
    ("(0010,9999)", NOT_IN_DICTIONARY, "X", ""),
]

# The rules that differ between policies, checked by hand against the 2026d
# tables: the element's tag, the preset, the source, and the action.
POLICY_RULES = [
    ("(300A,00C2)", "basic", SUPPLEMENTARY, "X/Z/D"),  # Beam Name
    ("(300A,00C2)", "basic-clean-descriptors", SUPPLEMENTARY, "C"),
    ("(0008,103E)", "basic", TABLE, "X"),  # Series Description
    ("(0008,103E)", "basic-clean-descriptors", TABLE, "C"),
    ("(3006,0026)", "basic", TABLE, "Z"),  # ROI Name
    ("(3006,0026)", "basic-clean-descriptors", TABLE, "C"),
    # A sequence that Clean Descriptors gives C keeps its Basic Profile action.
    ("(0008,1084)", "basic-clean-descriptors", TABLE, "X"),
    ("(3010,0081)", "basic-clean-descriptors", TABLE, "Z"),
    ("(3010,0081)", "tps-import", TABLE, "Z"),
    # Modified by its temporal role, which Retain Device Identity would keep.
    ("(0018,1200)", "tps-import", TABLE, "C"),
    ("(300A,00D4)", "tps-import", SUPPLEMENTARY, "K"),  # Wedge ID
    ("(0010,1020)", "tps-import", TABLE, "K"),  # Patient's Size
    # Patient's Size Code Sequence is removed by Type under every option.
    ("(0010,1021)", "tps-import", SUPPLEMENTARY, "X/Z/D"),
]

# The sequences that Table E.1-1 gives C under Clean Descriptors, with their
# Basic Profile actions.
CLEANED_SEQUENCES = {
    "(0008,1084)": "X",  # Admitting Diagnoses Code Sequence
    "(0008,1301)": "X",  # Principal Diagnosis Code Sequence
    "(0008,1302)": "X",  # Primary Diagnosis Code Sequence
    "(0008,1303)": "X",  # Secondary Diagnoses Code Sequence
    "(0008,1304)": "X",  # Histological Diagnoses Code Sequence
    "(0032,1067)": "X",  # Reason for Visit Code Sequence
    "(0040,100A)": "X",  # Reason for Requested Procedure Code Sequence
    "(0040,0275)": "X",  # Request Attributes Sequence
    "(3010,0081)": "Z",  # Prescription Notes Sequence
}

# The reviewed rules for attributes of other VRs that Table E.1-1 omits:
# the 12 URI and URL attributes, seven sequences whose content can identify
# an institution or other patients or say something about the patient, ICC
# Profile, and MAC Parameters Sequence.
URIS = {
    "(0008,010E)": "CodingSchemeURL",
    "(0008,0120)": "URNCodeValue",
    "(0008,0407)": "StoredInstanceBaseURI",
    "(0008,0408)": "FolderAccessURI",
    "(0008,0409)": "FileAccessURI",
    "(0008,040B)": "FilenameInContainer",
    "(0008,1190)": "RetrieveURL",
    "(0028,7FE0)": "PixelDataProviderURL",
    "(0040,4073)": "StorageURL",
    "(0040,E010)": "RetrieveURI",
    "(0068,7005)": "RelativeURIReferenceWithinEncapsulatedDocument",
    "(0074,100A)": "ContactURI",
}
SEQUENCES = {
    "(0008,0051)": "IssuerOfAccessionNumberSequence",
    "(0010,0024)": "IssuerOfPatientIDQualifiersSequence",
    "(0010,0026)": "SourcePatientGroupIdentificationSequence",
    "(0010,0027)": "GroupOfPatientsIdentificationSequence",
    "(0010,1021)": "PatientSizeCodeSequence",
    "(0032,1034)": "RequestingServiceCodeSequence",
    "(0040,1012)": "ReasonForPerformedProcedureCodeSequence",
}
OTHER_REMOVED = {
    "(0028,2000)": "ICCProfile",
    "(4FFE,0001)": "MACParametersSequence",
}
NEW_RULES = {**URIS, **SEQUENCES, **OTHER_REMOVED}
# The UR attributes that the first supported release's IODs require at a
# place that no removed sequence encloses, so that X/Z/D resolves to D there.
REQUIRED_URIS = {"(0008,010E)", "(0008,0120)", "(0028,7FE0)"}


@functools.cache
def _dictionary():
    return {each.tag: each for each in standard.load_data_dictionary().attributes}


@functools.cache
def _rules(preset="basic"):
    return ElementRules(policy.compose_policy(preset))


def _usable_policies():
    """Every preset and custom option set that does not select Retain Safe Private."""
    custom = [
        options
        for size in range(len(policy.TARGET_OPTIONS) + 1)
        for options in itertools.combinations(policy.TARGET_OPTIONS, size)
        if RETAIN_SAFE_PRIVATE not in options
        and not {policy.DEVICE_IDENTITY, policy.MODIFIED_DATES} <= set(options)
    ]
    return [
        policy.compose_policy(name)
        for name, options in policy.PRESETS.items()
        if RETAIN_SAFE_PRIVATE not in options
    ] + [policy.compose_custom_policy(options) for options in custom]


def _instance(tag):
    """Return a tag of an element that a dictionary attribute's tag matches.

    An "x" in a group, as in (60xx,3000), becomes 0, and an "x" in an element,
    as in (1000,xxx0), becomes 1, so that no element is a group length.
    """
    return f"({tag[1:5].replace('x', '0')},{tag[6:10].replace('x', '1')})"


def _tag(group, element):
    return f"({group:04X},{element:04X})"


@pytest.mark.parametrize("tag, source, action, entry", BASIC_RULES)
def test_each_level_decides_its_elements(tag, source, action, entry):
    rule = _rules().rule(tag)

    assert rule == ElementRule(tag=tag, source=source, action=action, entry=entry)


@pytest.mark.parametrize("tag, preset, source, action", POLICY_RULES)
def test_the_rule_follows_the_policy(tag, preset, source, action):
    rule = _rules(preset).rule(tag)

    assert (rule.source, rule.action) == (source, action)


def test_clean_descriptors_cleans_exactly_what_the_table_and_rules_clean():
    # Derived from the table and the reviewed rules, not from the module: the
    # option changes the rule of each attribute to which it gives C, apart
    # from the sequences, which keep their Basic Profile action.
    table = {row.tag: row for row in standard.load_table_e1_1().attributes}
    rules = supplementary_actions.load_supplementary_actions().rules
    expected = {
        tag
        for tag, row in table.items()
        if row.options.get(CLEAN_DESCRIPTORS) == "C" and tag not in CLEANED_SEQUENCES
    } | {tag for tag, rule in rules.items() if rule.options.get(CLEAN_DESCRIPTORS)}
    basic, cleaned = _rules("basic"), _rules("basic-clean-descriptors")
    changed = {}
    for attribute in _dictionary().values():
        tag = _instance(attribute.tag)
        if basic.rule(tag) != cleaned.rule(tag):
            changed[attribute.tag] = cleaned.rule(tag).action

    assert set(changed) == expected
    assert set(changed.values()) == {"C"}


def test_a_sequence_given_c_takes_its_basic_profile_action():
    dictionary = _dictionary()
    for preset in ("basic-clean-descriptors", "tps-import"):
        composed = policy.compose_policy(preset)
        cleaned = {
            tag
            for tag, action in composed.actions.items()
            if action == "C" and tag in dictionary and "SQ" in dictionary[tag].vrs
        }
        assert cleaned == set(CLEANED_SEQUENCES), preset
        for tag, action in CLEANED_SEQUENCES.items():
            assert ElementRules(composed).rule(tag) == ElementRule(
                tag, TABLE, action, tag
            )
    for composed in _usable_policies():
        rules = ElementRules(composed)
        for attribute in dictionary.values():
            if "SQ" in attribute.vrs:
                assert rules.rule(_instance(attribute.tag)).action != "C"


def test_retain_safe_private_is_refused_until_reviewed_rules_exist():
    refused = [policy.compose_policy("public-release")] + [
        policy.compose_custom_policy(options)
        for options in [
            (RETAIN_SAFE_PRIVATE,),
            (RETAIN_SAFE_PRIVATE, CLEAN_DESCRIPTORS),
        ]
    ]
    for composed in refused:
        with pytest.raises(policy.PolicyError, match="Retain Safe Private"):
            ElementRules(composed)


def test_a_policy_composed_from_another_table_is_refused():
    table = standard.load_table_e1_1()
    other = dataclasses.replace(table, attributes=table.attributes[:-1])

    with pytest.raises(policy.PolicyError, match="pinned Table E.1-1"):
        ElementRules(policy.compose_policy("basic", table=other))


@pytest.mark.parametrize(
    "tag, iod, path, action",
    [
        # A binary value is kept only where the IOD defines its attribute.
        ("(7FE0,0010)", "CT Image", (), "K"),  # Pixel Data, OB or OW
        ("(7FE0,0010)", "CT Image", ("(0088,0200)",), "K"),  # in an icon image
        ("(7FE0,0010)", "RT Plan", (), "X"),
        ("(7FE0,0010)", None, (), "X"),
        ("(0028,3006)", "CT Image", ("(0028,3010)",), "K"),  # LUT Data, US or OW
        ("(0028,3006)", "CT Image", (), "X"),
        # Vertices of the Polygonal Outline, OF, deep in an RT Plan.
        ("(0018,1638)", "RT Plan", ("(300A,00B0)", "(3008,00A1)", "(300A,0646)"), "K"),
        ("(0018,1638)", "RT Plan", ("(300A,00B0)",), "X"),
        ("(0400,0520)", "CT Image", (), "X"),  # Encrypted Content, out of place
        # Codes, numbers, tags, and sequences are kept wherever they are.
        ("(0028,0010)", None, (), "K"),
        ("(0028,0010)", "RT Plan", (), "K"),
        ("(300A,00B0)", "CT Image", (), "K"),
        ("(0008,0060)", "RT Dose", ("(300A,00B0)",), "K"),
    ],
)
def test_the_default_keeps_a_binary_value_only_where_the_iod_defines_it(
    tag, iod, path, action
):
    found = None if iod is None else iods.load_iod_tables().iods[iod]
    rule = _rules().rule(tag, path, iod=found)

    assert (rule.source, rule.action) == (DEFAULT, action)


def test_the_iod_decides_only_the_default_for_binary_values():
    tables = iods.load_iod_tables()
    rules = _rules()
    for attribute in _dictionary().values():
        tag = _instance(attribute.tag)
        without = rules.rule(tag)
        for name in SUPPORTED_IODS:
            within = rules.rule(tag, iod=tables.iods[name])
            if within != without:
                assert without.source is DEFAULT and without.action == "X"
                assert within == dataclasses.replace(without, action="K")
                assert {"OB", "OD", "OF", "OL", "OV", "OW", "UN"} & set(attribute.vrs)


def test_every_dictionary_attribute_has_the_rule_of_the_first_level_covering_it():
    # Each level is derived here from the tables and rule files: which cover
    # each attribute, and in what order they apply.
    composed = policy.compose_policy("basic")
    supplementary = set(composed.supplementary_actions)
    roles = set(uid_roles.load_uid_roles().rules)
    masked = [tag for tag in composed.actions if "x" in tag]
    rules = _rules()
    for attribute in _dictionary().values():
        tag = _instance(attribute.tag)
        listed = attribute.tag in composed.actions or any(
            all(want in ("x", got) for want, got in zip(pattern, tag))
            for pattern in masked
        )
        covering = [
            source
            for source, covers in (
                (ENGINE, tag in ("(FFFC,FFFC)", "(0400,0500)")),
                (TABLE, listed),
                (SUPPLEMENTARY, attribute.tag in supplementary),
                (UID_ROLE, attribute.tag in roles),
                (UNCOVERED_TEXT, bool(TEXT_VRS & set(attribute.vrs))),
                (DEFAULT, True),
            )
            if covers
        ]
        rule = rules.rule(tag)
        assert rule.source is covering[0], attribute.tag
        assert rule.tag == tag
        assert rule.action in standard.ACTION_CODES
        # The reviewed files never cover an attribute that the table lists,
        # and only UI attributes have both a table action and a role.
        assert not (listed and attribute.tag in supplementary), attribute.tag
        if listed and attribute.tag in roles:
            assert attribute.vrs == ("UI",)


def test_no_name_date_time_or_uid_reaches_the_rule_for_uncovered_attributes():
    for composed in _usable_policies():
        rules = ElementRules(composed)
        for attribute in _dictionary().values():
            if NAME_DATE_TIME_AND_UID_VRS & set(attribute.vrs):
                rule = rules.rule(_instance(attribute.tag))
                assert rule.source in {TABLE, SUPPLEMENTARY, UID_ROLE}, attribute.tag


def test_only_codes_numbers_tags_sequences_and_binary_values_reach_the_default():
    rules = _rules()
    reaching = {}
    for attribute in _dictionary().values():
        rule = rules.rule(_instance(attribute.tag))
        if rule.source is DEFAULT:
            reaching.setdefault(attribute.vr, set()).add(rule.action)

    # Checked by hand against the 2026d PS3.6: each VR, and each set of
    # alternatives, that an attribute without another rule has. Without an
    # IOD, a binary value is removed, and so is an element without a VR.
    kept = ("CS", "AT", "SQ", "DS", "IS", "FD", "FL", "SL", "SS", "SV", "UL")
    binary = ("OB", "OB or OW", "OD", "OF", "OL", "OV", "OW")
    assert reaching == {
        **dict.fromkeys((*kept, "US", "UV", "US or SS"), {"K"}),
        **dict.fromkeys((*binary, "US or OW", "US or SS or OW"), {"X"}),
        "": {"X"},
        "See Note 2": {"X"},
    }


def test_the_default_keeps_the_vrs_that_the_design_names():
    # From the design document: codes, tags, sequences, and the numeric VRs
    # are kept, and binary values only where the IOD defines the attribute.
    numeric = {"DS", "IS", "FL", "FD", "SL", "SS", "SV", "UL", "US", "UV"}

    assert element_rules.KEPT_VRS == {"CS", "AT", "SQ"} | numeric
    assert element_rules.BINARY_VRS == {"OB", "OD", "OF", "OL", "OV", "OW", "UN"}
    assert not (element_rules.KEPT_VRS | element_rules.BINARY_VRS) & (
        TEXT_VRS | NAME_DATE_TIME_AND_UID_VRS | {"AE", "AS", "UR"}
    )


@pytest.mark.parametrize("tag, keyword", NEW_RULES.items())
def test_each_new_supplementary_rule_removes_by_type_with_a_note(tag, keyword):
    rule = supplementary_actions.load_supplementary_actions().rules[tag]

    assert (rule.keyword, rule.action, dict(rule.options)) == (keyword, "X/Z/D", {})
    assert rule.note.strip()
    assert not re.search(r"\bD-[0-9]{3}\b", rule.note)
    for composed in _usable_policies():
        assert ElementRules(composed).rule(tag) == ElementRule(
            tag, SUPPLEMENTARY, "X/Z/D", tag
        )


def test_the_new_rules_cover_every_uri_that_table_e1_1_omits():
    listed = {row.tag for row in standard.load_table_e1_1().attributes}
    omitted = {
        tag
        for tag, attribute in _dictionary().items()
        if "UR" in attribute.vrs and tag not in listed
    }

    assert omitted == set(URIS)


def test_the_new_rules_remove_by_type_where_the_supported_iods_allow_it():
    # The sequences, ICC Profile, and MAC Parameters Sequence are Type 3
    # wherever the first supported release's IODs define them, so they are
    # removed. Retrieve URL and Retrieve URI are required only in sequences
    # that the table removes, and three UR attributes are required at places
    # where removal by Type needs a dummy value.
    tables = iods.load_iod_tables()
    basic = _rules()
    required = set()
    for name in SUPPORTED_IODS:
        iod = tables.iods[name]
        for definition in iod.definitions:
            if definition.tag not in NEW_RULES:
                continue
            resolved = compound_actions.resolve_in_iod(
                iod, definition.tag, definition.path, "X/Z/D"
            )
            if definition.tag not in URIS:
                assert resolved == "X", (name, definition)
            elif resolved != "X":
                removed = any(basic.rule(tag).action == "X" for tag in definition.path)
                if not removed:
                    required.add(definition.tag)
                    assert resolved == "D", (name, definition)

    assert required == REQUIRED_URIS


def test_patient_size_code_sequence_is_removed_under_retain_patient_characteristics():
    rules = _rules("tps-import")
    ct_image = iods.load_iod_tables().iods["CT Image"]

    assert rules.rule("(0010,1020)").action == "K"  # Patient's Size
    action = rules.rule("(0010,1021)").action
    assert compound_actions.resolve_in_iod(ct_image, "(0010,1021)", (), action) == "X"


@hypothesis.given(st.integers(0, 0xFFFF), st.integers(0, 0xFFFF))
def test_every_tag_has_one_rule_that_depends_only_on_the_tag_and_policy(group, element):
    tag = _tag(group, element)
    rule = _rules().rule(tag)

    assert rule.tag == tag
    assert rule.action in standard.ACTION_CODES
    assert isinstance(rule.source, RuleSource)
    assert rule == ElementRules(policy.compose_policy("basic")).rule(tag)
    assert hash(rule) == hash(dataclasses.replace(rule))


@hypothesis.given(st.sampled_from([0x0002, 0x0004]), st.integers(0, 0xFFFF))
def test_every_element_of_groups_0002_and_0004_in_a_data_set_is_removed(group, element):
    # The engine builds the File Meta Information itself, and group 0004
    # belongs only in a DICOMDIR, which is never passed through.
    for preset in ("basic", "basic-clean-descriptors", "tps-import"):
        rule = _rules(preset).rule(_tag(group, element), ("(300A,00B0)",))

        assert (rule.source, rule.action) == (ENGINE, "X")


@hypothesis.given(
    st.integers(0, 0x7FFF)
    .map(lambda half: 2 * half + 1)
    .filter(lambda group: group not in RESERVED_ODD_GROUPS),
    st.integers(1, 0xFFFF),
)
def test_every_element_of_a_private_group_is_private(group, element):
    for preset in ("basic", "basic-clean-descriptors", "tps-import"):
        rule = _rules(preset).rule(_tag(group, element))

        assert (rule.source, rule.action, rule.entry) == (PRIVATE, "X", PRIVATE_ROW)


@hypothesis.given(st.sampled_from(RESERVED_ODD_GROUPS), st.integers(1, 0xFFFF))
def test_an_odd_group_that_is_not_private_falls_to_the_later_rules(group, element):
    rule = _rules().rule(_tag(group, element))

    assert (rule.source, rule.action, rule.entry) == (NOT_IN_DICTIONARY, "X", "")


@hypothesis.given(st.integers(0, 15), st.sampled_from(["3000", "4000"]))
def test_the_overlay_masks_match_every_repeating_group(index, element):
    tag = f"({0x6000 + 2 * index:04X},{element})"

    assert _rules().rule(tag).entry == f"(60xx,{element})"


@hypothesis.given(st.integers(1, 0xFFFF), st.integers(0, 15))
def test_the_curve_mask_matches_every_element_of_every_repeating_group(element, index):
    rule = _rules().rule(_tag(0x5000 + 2 * index, element))

    assert (rule.source, rule.action, rule.entry) == (TABLE, "X", "(50xx,xxxx)")


@hypothesis.given(
    st.sampled_from([0x50, 0x60]),
    st.integers(0x10, 0x7F).map(lambda half: 2 * half),
    st.integers(1, 0xFFFF),
)
def test_no_mask_matches_outside_the_repeating_groups(high, low, element):
    rule = _rules().rule(_tag(high << 8 | low, element))

    assert rule.source is NOT_IN_DICTIONARY
    assert "x" not in rule.entry


def test_a_rule_names_its_tag_source_action_and_entry_only():
    rule = _rules().rule("(0010,0010)")

    assert repr(rule) == (
        "ElementRule(tag='(0010,0010)', source=<RuleSource.TABLE: 'table'>, "
        "action='Z', entry='(0010,0010)')"
    )
    assert [field.name for field in dataclasses.fields(rule)] == [
        "tag",
        "source",
        "action",
        "entry",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        rule.action = "K"  # type: ignore[misc]


@pytest.mark.parametrize(
    "tag, path",
    [
        ("(0010,001g)", ()),
        ("(0010,001e)", ()),
        ("0010,0010", ()),
        ("(0010,0010)", "(300A,00B0)"),
        ("(0010,0010)", ("(300A,00b0)",)),
    ],
)
def test_a_malformed_tag_or_path_is_rejected(tag, path):
    with pytest.raises(ValueError, match="upper-case hexadecimal"):
        _rules().rule(tag, path)


def test_the_rules_keep_their_policy():
    composed = policy.compose_policy("basic-clean-descriptors")

    assert ElementRules(composed).policy is composed


def test_rules_classify_with_the_pinned_dictionary_not_the_decoder():
    # Deciding an element's rule needs only its pinned classification, so
    # the rules depend on the standard data, not on the module that decodes
    # values (the B+ decision of 1 October 2026).
    source = pathlib.Path(element_rules.__file__).read_text(encoding="utf-8")
    imported = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }

    assert "elements" not in imported
    assert "standard" in imported
