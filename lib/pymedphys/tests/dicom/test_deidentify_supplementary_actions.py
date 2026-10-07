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

# The tests share the hand-checked lists of attributes and the helpers that
# rewrite the rules file below, so they stay in one module.
# pylint: disable = too-many-lines

import collections
import dataclasses
import itertools
import json
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
TEMPORAL_VRS = {"DA", "DT", "TM"}
# The IODs of the first supported release.
# The CT and RT IODs that the first supported release has always supported,
# and the CT, MR, and PET IODs that it adds.
CT_AND_RT_IODS = ("CT Image", "RT Dose", "RT Plan", "RT Structure Set")
ADDED_IODS = (
    "Enhanced CT Image",
    "Legacy Converted Enhanced CT Image",
    "MR Image",
    "Enhanced MR Image",
    "Enhanced MR Color Image",
    "Legacy Converted Enhanced MR Image",
    "MR Spectroscopy",
    "Positron Emission Tomography Image",
    "Enhanced PET Image",
    "Legacy Converted Enhanced PET Image",
)
SUPPORTED_IODS = CT_AND_RT_IODS + ADDED_IODS
CLEAN_DESCRIPTORS = "clean_descriptors"
DEVICE_IDENTITY = "retain_device_identity"
FULL_DATES = "retain_longitudinal_full_dates"
MODIFIED_DATES = "retain_longitudinal_modified_dates"
DEIDENTIFICATION_METHOD = "(0012,0063)"
ALTERNATIVE_CALENDAR_DATES = ("(0010,0033)", "(0010,0034)")
STUDY_UPDATE = "(0008,041F)"  # Study Update DateTime
# The actions that Table E.1-1 gives nearly every date under the two Retain
# Longitudinal Temporal Information Options.
DATE_OPTIONS = {FULL_DATES: "K", MODIFIED_DATES: "C"}

# The dates, times, and datetimes that Table E.1-1 omits, checked by hand
# against the 2026d PS3.6 and PS3.15: three general attributes, eight that
# PS3.6 marks DICONDE, and four that it marks DICOS.
OMITTED_DATES = {
    "(0008,0404)": "ItemInventoryDateTime",
    "(0008,0416)": "ExpirationDateTime",
    "(0008,041F)": "StudyUpdateDateTime",
    "(0014,0102)": "SecondaryReviewDate",
    "(0014,0103)": "SecondaryReviewTime",
    "(0014,1020)": "ExpiryDate",
    "(0014,3076)": "DateOfGainCalibration",
    "(0014,3077)": "TimeOfGainCalibration",
    "(0014,4076)": "ProcedureCreationDate",
    "(0014,4078)": "ProcedureExpirationDate",
    "(0014,407A)": "ProcedureLastModifiedDate",
    "(4010,1025)": "RouteSegmentStartTime",
    "(4010,1026)": "RouteSegmentEndTime",
    "(4010,102B)": "AlarmDecisionTime",
    "(4010,1041)": "OOIOwnerCreationTime",
}
# What each rule's note says Modified Dates does to the value, by the action
# of its temporal role.
SAID_OF = {
    temporal_roles.TemporalAction.SHIFT: "shifts it with the subject's other dates",
    temporal_roles.TemporalAction.DUMMY: "replaces it with a fixed dummy value",
}
# The claims that a note can make about the IODs that use its attribute,
# which the generated IOD tables can check: that none uses it, or none uses
# the only modules that define it ("which none of the IODs ... uses").
NO_GENERATED_IOD_USES_IT = re.compile(
    r"\b(?:none of the IODs whose Types are generated|no IOD whose Types are "
    r"generated|none of the generated IODs) uses\b"
)
NO_SUPPORTED_IOD_USES_IT = re.compile(
    r"\bno (?:supported IOD|IOD of the first supported release) uses\b"
)
INVENTORIED_STUDIES = "(0008,0423)"  # Inventoried Studies Sequence
# The omitted dates that, of the IODs whose Types are generated, only the
# Inventory IOD uses, in its Inventory Module, with the path and Type that
# Table C.38.1-1 gives each, checked by hand against the 2026d PS3.3.
INVENTORY_DATES = {
    "(0008,0404)": ((INVENTORIED_STUDIES,), "1"),  # Item Inventory DateTime
    "(0008,041F)": ((INVENTORIED_STUDIES,), "2"),  # Study Update DateTime
    # Expiration DateTime, in File Access Sequence (0008,041A) of each
    # inventoried instance of each inventoried series.
    "(0008,0416)": (
        (INVENTORIED_STUDIES, "(0008,0424)", "(0008,0425)", "(0008,041A)"),
        "3",
    ),
}

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
# Every text attribute that the CT and RT IODs use, Table E.1-1 omits, and
# the Basic Profile keeps, checked by hand against the 2026d PS3.3: coded
# values, and technical values that the equipment or software writes. The
# added IODs keep ADDED_KEPT_TEXT too.
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
# The UR attributes that Table E.1-1 omits and the supported IODs use,
# checked by hand against the 2026d PS3.3, PS3.6, and PS3.15. Two name coding
# concepts and schemes and are kept, like Code Value and Coding Scheme
# Designator; the others are removed by Type.
KEPT_URLS = {
    "(0008,010E)": "CodingSchemeURL",
    "(0008,0120)": "URNCodeValue",
}
OTHER_URLS = {
    "(0008,1190)",  # Retrieve URL
    "(0028,7FE0)",  # Pixel Data Provider URL
    "(0040,E010)",  # Retrieve URI
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


def _definitions_of(tags, names=None):
    """Return where the IODs whose Types are generated define each of ``tags``.

    Each definition, at any depth, is given as the IOD's name, the module's
    name, the path, and the Type. Only the IODs in ``names`` are searched, if
    given. An IOD's definitions include those in the items of every sequence;
    the items of a table that includes itself repeat definitions already
    listed.
    """
    tables = iods.load_iod_tables()
    found = collections.defaultdict(set)
    for name in tables.iods if names is None else names:
        for definition in tables.iods[name].definitions:
            if definition.tag in tags:
                found[definition.tag].add(
                    (name, definition.module, definition.path, definition.type)
                )
    return dict(found)


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


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06")
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


@pytest.mark.deid_requirement("MIDI-BP-05")
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


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_every_text_attribute_a_supported_iod_uses_and_table_e1_1_omits_has_a_rule():
    omitted = _omitted_text()

    # Checked by hand against the 2026d PS3.3, PS3.6, and PS3.15.
    assert len(omitted) == 141
    assert omitted <= set(_rules())
    assert {"(0008,0100)", "(300A,00C2)", "(60xx,1500)"} <= omitted


@pytest.mark.deid_requirement("MIDI-BP-06")
def test_the_rules_for_omitted_text_fall_in_the_reviewed_groups():
    rules = _rules()
    groups = collections.Counter(
        (rules[tag].action, tuple(rules[tag].options.items()))
        for tag in _omitted_text()
    )

    assert groups == {
        # Operator-typed labels and text.
        ("X/Z/D", ((CLEAN_DESCRIPTORS, "C"),)): 62,
        # Accessory and equipment identifiers.
        ("X/Z/D", ((DEVICE_IDENTITY, "K"),)): 24,
        # Coded and technical values, and De-identification Method.
        ("K", ()): 38,
        # Names and identifiers of people, organisations, records, and
        # networks, identifiers that a device reads, and the text of overlays.
        ("X/Z/D", ()): 15,
        # Patient's Birth and Death Dates in Alternative Calendar.
        ("X", ()): 2,
    }


# The text attributes that the added IODs use and that neither Table E.1-1
# nor the CT and RT IODs cover, by group, checked by hand against the 2026d
# PS3.3.
ADDED_OPERATOR_TEXT = {
    "(0018,0024)",  # Sequence Name
    "(0018,0031)",  # Radiopharmaceutical
    "(0018,0034)",  # Intervention Drug Name
    "(0018,003A)",  # Intervention Description
    "(0018,1070)",  # Radiopharmaceutical Route
    "(0018,1085)",  # PVC Rejection
    "(0018,9046)",  # Multi-Coil Configuration
    "(0018,9080)",  # Metabolite Map Description
    "(0018,9252)",  # ASL Technique Description
    "(0018,925B)",  # ASL Crusher Description
    "(0018,925E)",  # ASL Bolus Cut-off Technique
    "(0020,9421)",  # Dimension Description Label
    "(0054,1101)",  # Attenuation Correction Method
    "(0054,1103)",  # Reconstruction Method
    "(0054,1104)",  # Detector Lines of Response Used
    "(0054,1105)",  # Scatter Correction Method
}
ADDED_DEVICE_IDENTITY = {
    "(0018,1250)",  # Receive Coil Name
    "(0018,1251)",  # Transmit Coil Name
    "(0018,9041)",  # Receive Coil Manufacturer Name
    "(0018,9047)",  # Multi-Coil Element Name
    "(0018,9050)",  # Transmit Coil Manufacturer Name
}
ADDED_KEPT_TEXT = {
    "(0018,0085)",  # Imaged Nucleus
    "(0018,1064)",  # Cardiac Framing Type
    "(0018,1180)",  # Collimator/Grid Name
    "(0018,9005)",  # Pulse Sequence Name
    "(0018,9175)",  # Applicable Safety Standard Description
    "(0018,9320)",  # Image Filter
    "(0020,9056)",  # Stack ID
    "(0020,9213)",  # Dimension Index Private Creator
    "(0020,9238)",  # Functional Group Private Creator
    "(0020,9453)",  # Frame Label
}


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_the_text_that_only_the_added_ct_mr_and_pet_iods_use_has_reviewed_rules():
    dictionary = _dictionary()
    tables = iods.load_iod_tables()

    def text_of(names):
        return {
            definition.tag
            for name in names
            for definition in tables.iods[name].definitions
            if TEXT_VRS.intersection(dictionary[definition.tag].vrs)
        } - set(_table_e1_1())

    added = text_of(ADDED_IODS) - text_of(CT_AND_RT_IODS)
    rules = _rules()

    assert added == ADDED_OPERATOR_TEXT | ADDED_DEVICE_IDENTITY | ADDED_KEPT_TEXT
    assert len(added) == 31
    for tags, action, options in (
        (ADDED_OPERATOR_TEXT, "X/Z/D", {CLEAN_DESCRIPTORS: "C"}),
        (ADDED_DEVICE_IDENTITY, "X/Z/D", {DEVICE_IDENTITY: "K"}),
        (ADDED_KEPT_TEXT, "K", {}),
    ):
        for tag in tags:
            assert (rules[tag].action, dict(rules[tag].options)) == (
                action,
                options,
            ), tag


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


@pytest.mark.deid_requirement("MIDI-BP-06")
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
    for tag in KEPT_TEXT | ADDED_KEPT_TEXT:
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


@pytest.mark.deid_requirement("MIDI-BP-11")
def test_the_basic_profile_keeps_only_the_reviewed_coded_and_technical_text():
    # Every text attribute of the supported IODs, whether Table E.1-1 lists
    # it or a supplementary rule covers it.
    composed = policy.compose_policy("basic")
    basic = {
        tag: composed.actions.get(tag) or composed.supplementary_actions[tag]
        for tag in _supported_text()
    }

    assert len(basic) == 261
    assert {tag for tag, action in basic.items() if action == "K"} == (
        KEPT_TEXT | ADDED_KEPT_TEXT
    )
    assert set(basic.values()) - {"K"} <= REMOVING_ACTIONS


@pytest.mark.deid_requirement("MIDI-BP-05")
def test_no_option_keeps_more_than_the_coded_text_and_device_identity():
    rules = _rules()
    device_identity = {
        tag for tag in _omitted_text() if rules[tag].options.get(DEVICE_IDENTITY)
    }
    for composed in _every_policy():
        kept = {
            tag for tag in _omitted_text() if composed.supplementary_actions[tag] == "K"
        }
        expected = (
            KEPT_TEXT
            | ADDED_KEPT_TEXT
            | (device_identity if DEVICE_IDENTITY in composed.options else set())
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


@pytest.mark.deid_requirement("MIDI-BP-05")
def test_the_urls_that_name_coding_concepts_and_schemes_are_kept():
    rules = _rules()
    listed = _table_e1_1()
    omitted = {
        tag
        for tag, attribute in _dictionary().items()
        if "UR" in attribute.vrs and tag not in listed
    }

    assert len(omitted) == 12
    assert set(_definitions_of(omitted, SUPPORTED_IODS)) == (
        set(KEPT_URLS) | OTHER_URLS
    )
    for tag, keyword in KEPT_URLS.items():
        rule = rules[tag]
        assert (rule.keyword, rule.action, dict(rule.options)) == (keyword, "K", {})
        assert rule.note.strip()
        for composed in _every_policy():
            assert composed.supplementary_actions[tag] == "K", composed.options


def test_the_declared_default_for_text_without_a_rule_removes_by_type():
    rules = _rules()
    listed = _table_e1_1()
    uncovered = {
        tag
        for tag, attribute in _dictionary().items()
        if TEXT_VRS.intersection(attribute.vrs)
        and tag not in listed
        and tag not in rules
    }

    # Such as Stage Name, an ultrasound attribute that no supported IOD uses.
    assert "(0008,2120)" in uncovered
    assert not uncovered & _omitted_text()
    assert supplementary_actions.UNCOVERED_TEXT_ACTION == "X/Z/D"


@pytest.mark.deid_requirement("MIDI-BP-06")
def test_every_date_and_time_that_table_e1_1_omits_has_a_rule():
    # Derived here independently of the loader: Table E.1-1 lists no date or
    # time by a masked tag, so an exact comparison of tags suffices.
    dictionary = _dictionary()
    listed = _table_e1_1()
    omitted = {
        tag
        for tag, attribute in dictionary.items()
        if TEMPORAL_VRS.intersection(attribute.vrs) and tag not in listed
    }

    assert omitted == set(OMITTED_DATES)
    assert collections.Counter(dictionary[tag].status for tag in omitted) == {
        "": 3,
        "DICONDE": 8,
        "DICOS": 4,
    }
    assert omitted <= set(_rules())


def test_the_basic_profile_keeps_no_date_or_time():
    # Table E.1-1 and the supplementary actions together give every date,
    # time, and datetime in the dictionary an action that removes or
    # replaces it.
    listed = _table_e1_1()
    rules = _rules()
    basic = {
        tag: listed[tag].basic_profile if tag in listed else rules[tag].action
        for tag, attribute in _dictionary().items()
        if TEMPORAL_VRS.intersection(attribute.vrs)
    }

    assert len(basic) == 184
    assert set(basic.values()) <= REMOVING_ACTIONS


@pytest.mark.parametrize("tag, keyword", OMITTED_DATES.items())
def test_each_omitted_date_is_removed_by_type_and_kept_or_cleaned_by_the_date_options(
    tag, keyword
):
    rule = _rules()[tag]

    assert (rule.tag, rule.keyword, rule.action) == (tag, keyword, "X/Z/D")
    assert dict(rule.options) == DATE_OPTIONS
    assert rule.note.strip()


def test_the_omitted_dates_take_the_date_option_actions_of_the_dates_the_table_lists():
    # Table E.1-1 keeps under Full Dates, and cleans under Modified Dates,
    # every date and time it lists but Patient's Birth Date, Patient's Birth
    # Time, and GPS Time Stamp, which it removes under every option. The
    # rules do the same for the dates that it omits.
    dictionary = _dictionary()
    date_options = collections.Counter(
        tuple(
            (option, action)
            for option, action in row.options.items()
            if option in (FULL_DATES, MODIFIED_DATES)
        )
        for tag, row in _table_e1_1().items()
        if tag in dictionary and TEMPORAL_VRS.intersection(dictionary[tag].vrs)
    )

    assert date_options == {tuple(DATE_OPTIONS.items()): 166, (): 3}
    for tag in OMITTED_DATES:
        assert dict(_rules()[tag].options) == DATE_OPTIONS, tag


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize(
    "options, action",
    [
        ((), "X/Z/D"),
        ((FULL_DATES,), "K"),
        ((MODIFIED_DATES,), "C"),
        # No other option gives them an action, so Retain Device Identity
        # keeps none of them, not even the dates of gain calibration.
        ((DEVICE_IDENTITY,), "X/Z/D"),
        ((CLEAN_DESCRIPTORS,), "X/Z/D"),
        ((FULL_DATES, DEVICE_IDENTITY, CLEAN_DESCRIPTORS), "K"),
        ((DEVICE_IDENTITY, MODIFIED_DATES, CLEAN_DESCRIPTORS), "C"),
    ],
)
def test_only_the_date_options_override_the_action_of_an_omitted_date(options, action):
    effective = actions.effective_supplementary_actions(options)

    assert not effective.conflicts
    assert {effective.actions[tag] for tag in OMITTED_DATES} == {action}


def test_every_policy_cleans_the_omitted_dates_only_under_modified_dates():
    # Every preset, including basic (X/Z/D), and public-release and
    # tps-import (C), and every custom option set.
    for composed in _every_policy():
        expected = "C" if MODIFIED_DATES in composed.options else "X/Z/D"
        assert {composed.supplementary_actions[tag] for tag in OMITTED_DATES} == {
            expected
        }, composed.options
        # No conflict involves them, for a preset to resolve.
        assert not {r.conflict.tag for r in composed.resolved} & set(OMITTED_DATES)


def test_each_date_rule_says_what_the_date_options_and_its_role_do():
    rules = _rules()
    roles = temporal_roles.load_temporal_roles()

    for tag in OMITTED_DATES:
        note = rules[tag].note
        assert "kept (K) under Full Dates" in note, tag
        assert "cleaned (C) under Modified Dates" in note, tag
        assert SAID_OF[roles.role(tag).action] in note, tag
    # The dates of gain calibration say why Retain Device Identity, which
    # keeps the calibration dates that Table E.1-1 lists, does not keep them.
    for tag in ("(0014,3076)", "(0014,3077)"):
        assert roles.role(tag) is temporal_roles.TemporalRole.DEVICE
        assert "Retain Device Identity" in rules[tag].note


@pytest.mark.parametrize(
    "claim, names, claimed_of",
    [
        # The DICONDE and DICOS person names and dates.
        (
            NO_GENERATED_IOD_USES_IT,
            None,
            {"(0014,0104)", "(0014,2006)"}
            | (set(OMITTED_DATES) - set(INVENTORY_DATES)),
        ),
        (NO_SUPPORTED_IOD_USES_IT, SUPPORTED_IODS, set(INVENTORY_DATES)),
    ],
    ids=["generated", "supported"],
)
def test_a_note_that_no_iod_uses_its_attribute_is_true(claim, names, claimed_of):
    # Checked again whenever the IOD tables are regenerated, since an IOD
    # whose Types are newly generated can use an attribute that none did.
    claimed = {tag for tag, rule in _rules().items() if claim.search(rule.note)}

    assert claimed_of <= claimed
    assert not _definitions_of(claimed, names)


def test_only_the_inventory_iod_uses_the_inventory_dates_as_their_notes_say():
    found = _definitions_of(set(INVENTORY_DATES))
    rules = _rules()

    for tag, (path, attribute_type) in INVENTORY_DATES.items():
        assert found[tag] == {("Inventory", "Inventory", path, attribute_type)}, tag
        note = rules[tag].note
        assert (
            f"PS3.3 defines it only in the Inventory Module, as Type {attribute_type}"
            in note
        ), tag
        assert "Only the Inventory IOD uses the Inventory Module" in note, tag


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


def test_uids_are_left_to_their_roles_and_dates_have_actions_besides():
    # pylint: disable=protected-access
    assert supplementary_actions._ROLES_ONLY_VRS == uid_roles._FORMAT.vrs
    assert supplementary_actions.TEMPORAL_VRS == temporal_roles._FORMAT.vrs
    assert supplementary_actions.COVERED_VRS == {"PN"} | TEMPORAL_VRS


def test_each_option_that_can_give_an_action_names_the_attributes_it_applies_to():
    # Otherwise a rule's action under such an option would raise a KeyError,
    # not a SupplementaryActionError.
    # pylint: disable=protected-access
    assert set(supplementary_actions._OPTION_ATTRIBUTES) == set(
        supplementary_actions.OPTION_ACTIONS
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
        # A date that Table E.1-1 lists keeps the table's actions.
        (
            _first(tag="(0008,0020)", keyword="StudyDate"),
            "rule 1 is listed in Table E.1-1",
        ),
        (
            _first(tag="(0008,0016)", keyword="SOPClassUID"),
            "rule 1 is a UI attribute, which the UID roles file covers",
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
        # Dates and times that Table E.1-1 omits.
        (lambda d: _drop(d, STUDY_UPDATE), f"has no action for {STUDY_UPDATE}"),
        (lambda d: _drop(d, "(0014,3077)"), "has no action for (0014,3077)"),
        (lambda d: _drop(d, "(4010,1041)"), "has no action for (4010,1041)"),
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
            _rule(STUDY_UPDATE, options={FULL_DATES: "C", MODIFIED_DATES: "C"}),
            "gives retain_longitudinal_full_dates an action other than K",
        ),
        (
            _rule(STUDY_UPDATE, options={FULL_DATES: "K", MODIFIED_DATES: "K"}),
            "gives retain_longitudinal_modified_dates an action other than C",
        ),
        (
            _rule(BEAM_NAME, options={"retain_uids": "K"}),
            "gives an action under retain_uids; a rule may give one only under "
            "retain_device_identity, retain_longitudinal_full_dates, "
            "retain_longitudinal_modified_dates, or clean_descriptors",
        ),
        (
            _rule(BEAM_NAME, options={DEVICE_IDENTITY: "K", CLEAN_DESCRIPTORS: "C"}),
            "gives different actions under two or more options that can be "
            "selected together",
        ),
        (
            _rule(STUDY_UPDATE, options={FULL_DATES: "K", CLEAN_DESCRIPTORS: "C"}),
            "gives different actions under two or more options that can be "
            "selected together",
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
            _rule(STUDY_UPDATE, action="K"),
            "has an option action, but its Basic Profile action keeps the value",
        ),
        (
            _first(options={CLEAN_DESCRIPTORS: "C"}),
            "rule 1 has an option action under clean_descriptors, but is not a "
            "text attribute",
        ),
        # Each option gives an action only to the attributes it applies to.
        (
            _rule(BEAM_NAME, options={MODIFIED_DATES: "C"}),
            "has an option action under retain_longitudinal_modified_dates, but is "
            "not a date, time, or datetime attribute",
        ),
        (
            _rule(BEAM_NAME, options={FULL_DATES: "K", MODIFIED_DATES: "C"}),
            "has an option action under retain_longitudinal_full_dates, but is not "
            "a date, time, or datetime attribute",
        ),
        (
            _rule(STUDY_UPDATE, options={DEVICE_IDENTITY: "K"}),
            "has an option action under retain_device_identity, but is not a text "
            "attribute",
        ),
        # Every option is checked, not only the first.
        (
            _rule(STUDY_UPDATE, options={FULL_DATES: "K", DEVICE_IDENTITY: "K"}),
            "has an option action under retain_device_identity, but is not a text "
            "attribute",
        ),
        (
            _rule(STUDY_UPDATE, options={CLEAN_DESCRIPTORS: "C"}),
            "has an option action under clean_descriptors, but is not a text attribute",
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


def _with_definition(tmp_path, iod_name, tag):
    """Return IOD tables in which ``iod_name`` defines ``tag`` in a sequence.

    The tables are loaded, through the public loader, from copies of the
    generated files with a module added: its attribute table defines ``tag``
    in Beam Sequence (300A,00B0). An IOD that the files lack is added too.
    """
    modules, attributes = (
        json.loads((standard.STANDARD_DIR / name).read_text(encoding="utf-8"))
        for name in ("iod_modules.json", "module_attributes.json")
    )
    attributes["rows"].append(
        {
            "label": "Table X.0-1",
            "title": "Test Module Attributes",
            "rows": [
                {
                    "depth": 0,
                    "name": "Beam Sequence",
                    "tag": "(300A,00B0)",
                    "type": "3",
                    "include": "",
                },
                {"depth": 1, "name": "Test", "tag": tag, "type": "3", "include": ""},
            ],
        }
    )
    entry = next((row for row in modules["rows"] if row["iod"] == iod_name), None)
    if entry is None:
        entry = {"label": "Table X.0-2", "iod": iod_name, "modules": []}
        modules["rows"].append(entry)
    entry["modules"].append(
        {
            "information_entity": "Equipment",
            "module": "Test",
            "section": "X.0",
            "usage": "U",
            "condition": "",
            "table": "Table X.0-1",
        }
    )
    paths = []
    for name, document in (
        ("iod_modules.json", modules),
        ("module_attributes.json", attributes),
    ):
        document["content_sha256"] = standard.content_sha256(document["rows"])
        paths.append(tmp_path / name)
        paths[-1].write_text(json.dumps(document), encoding="utf-8")
    return iods.load_iod_tables(*paths)


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize(
    "iod_name, required",
    [
        # A supported IOD that comes to use Stage Name, which has no rule, at
        # any depth, needs a rule for it.
        ("RT Plan", True),
        # An IOD that is not supported does not, even once its Types are
        # generated.
        ("Nuclear Medicine Image", False),
    ],
)
def test_only_the_text_of_the_supported_iods_needs_rules(
    tmp_path, monkeypatch, iod_name, required
):
    tables = _with_definition(tmp_path, iod_name, "(0008,2120)")
    assert tables.iods[iod_name].lookup("(0008,2120)", ["(300A,00B0)"])
    monkeypatch.setattr(supplementary_actions, "load_iod_tables", lambda: tables)
    path = _write(tmp_path / "supplementary_actions.toml", _document())

    if required:
        with pytest.raises(
            supplementary_actions.SupplementaryActionError,
            match=re.escape("has no action for (0008,2120)"),
        ):
            supplementary_actions.load_supplementary_actions(path)
    else:
        assert "(0008,2120)" not in (
            supplementary_actions.load_supplementary_actions(path).rules
        )


NEW_TAG = "(0014,0109)"  # Not in the 2026d data dictionary.


def _with_dictionary_attribute(tmp_path, vr):
    """Return the data dictionary with an attribute of ``vr`` added at ``NEW_TAG``.

    The dictionary is loaded, through the public loader, from a copy of the
    generated file with the row added, as a regenerated dictionary would add
    an attribute that Table E.1-1 omits.
    """
    document = json.loads(
        (standard.STANDARD_DIR / "data_dictionary.json").read_text(encoding="utf-8")
    )
    document["rows"].append(
        {
            "tag": NEW_TAG,
            "name": "Test Attribute",
            "keyword": "TestAttribute",
            "vr": vr,
            "vm": "1",
            "status": "",
        }
    )
    document["content_sha256"] = standard.content_sha256(document["rows"])
    path = tmp_path / "data_dictionary.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return standard.load_data_dictionary(path)


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize(
    "vr, required",
    [
        ("DA", True),
        ("DT", True),
        ("TM", True),
        ("PN", True),
        # An attribute of another VR, such as CS, needs no rule.
        ("CS", False),
    ],
)
def test_a_new_attribute_that_table_e1_1_omits_needs_a_rule_by_its_vr(
    tmp_path, monkeypatch, vr, required
):
    dictionary = _with_dictionary_attribute(tmp_path, vr)
    monkeypatch.setattr(
        supplementary_actions, "load_data_dictionary", lambda: dictionary
    )
    document = _document()
    path = _write(tmp_path / "supplementary_actions.toml", document)

    if not required:
        assert (
            NEW_TAG not in supplementary_actions.load_supplementary_actions(path).rules
        )
        return
    with pytest.raises(
        supplementary_actions.SupplementaryActionError,
        match=re.escape(f"has no action for {NEW_TAG}"),
    ):
        supplementary_actions.load_supplementary_actions(path)
    # A reviewed rule for the attribute lets the rules load again.
    document["attribute"].append(
        {
            "tag": NEW_TAG,
            "keyword": "TestAttribute",
            "action": "X/Z/D",
            "note": "A test.",
        }
    )
    loaded = supplementary_actions.load_supplementary_actions(
        _write(tmp_path / "reviewed.toml", document)
    )
    assert loaded.rules[NEW_TAG].action == "X/Z/D"
