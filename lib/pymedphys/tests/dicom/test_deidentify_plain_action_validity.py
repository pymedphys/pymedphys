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

"""Where a plain action of Table E.1-1a cannot keep an instance valid.

The places in the supported records and second-generation RT IODs where a
plain X, a plain Z, or a D on a VR without a generic dummy value would
leave an instance invalid, each pinned against its reviewed rule.
"""

import collections

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    compound_actions,
    dummy_values,
    iods,
    standard,
    supplementary_actions,
)

from .test_deidentify_compound_actions import FIRST_RELEASE_IODS
from .test_deidentify_plain_actions import (
    ALONE,
    EMPTIED,
    PATIENT_SETUP,
    PATIENT_SETUP_PHOTO_DESCRIPTION,
    PATIENT_TREATMENT_PREPARATION,
    PATIENT_TREATMENT_PREPARATION_PROCEDURE,
    PERSON_IDENTIFICATION_CODE_SEQUENCE,
    PROCEDURE_PARAMETER_DESCRIPTION,
    RECORDED_SOURCE,
    REFERENCED_PATIENT_SETUP_PHOTO,
    RESPONSIBLE_ORGANIZATION,
    RESPONSIBLE_PERSON,
    RT_ACCESSORY_HOLDER_SLOT_ID,
    SEQUESTER,
    SOURCE_MANUFACTURER,
    _basic_profile_removes,
    _removal,
)

resolve_in_iod = compound_actions.resolve_in_iod
resolve_plain_in_iod = compound_actions.resolve_plain_in_iod
resolve_plain_x_in_iod = compound_actions.resolve_plain_x_in_iod
strictest_type = compound_actions.strictest_type


@pytest.fixture(name="tables", scope="module")
def _tables():
    return iods.load_iod_tables()


# RT Brachy Treatment Record and RT Treatment Summary Record, which the
# maintainer added to the target coverage on 31 October 2026, reviewed ahead
# of supporting them and now supported, and the IODs reviewed before them.
RECORD_IODS = ("RT Brachy Treatment Record", "RT Treatment Summary Record")
RECORD_REVIEWED_AGAINST = (
    *(name for name in FIRST_RELEASE_IODS if name not in RECORD_IODS),
    "RT Ion Plan",
    "RT Ion Beams Treatment Record",
)


def _record_basic_and_actions():
    """Return the Basic Profile actions, and every action under any option.

    Those of Table E.1-1 for the attributes it lists, else those of the
    reviewed rules, by tag.
    """
    basic = {}
    every = collections.defaultdict(set)
    for attribute in standard.load_table_e1_1().attributes:
        basic[attribute.tag] = attribute.basic_profile
        every[attribute.tag] |= {attribute.basic_profile, *attribute.options.values()}
    for tag, rule in supplementary_actions.load_supplementary_actions().rules.items():
        if tag not in basic:
            basic[tag] = rule.action
            every[tag] |= {rule.action, *rule.options.values()}
    return basic, every


def _places_a_plain_action_cannot_keep_valid(tables, names):
    """Return each place where a plain X, a plain Z, or a D cannot stand.

    A plain X on an attribute that the IOD requires, with what it removes
    there; a plain Z on a Type 1 attribute; and a D, plain or resolved by
    Type, on an attribute of a VR without a generic dummy value, such as a
    sequence or a URL (D-021). Places
    inside a sequence that the Basic Profile removes are left out, since the
    attribute goes with it.
    """
    basic, every = _record_basic_and_actions()
    dictionary = {
        attribute.tag: attribute
        for attribute in standard.load_data_dictionary().attributes
    }
    found = {}
    for name in names:
        iod = tables.iods[name]
        for definition in iod.definitions:
            tag = definition.tag.replace("xx", "00")
            path = definition.path
            if any(
                _basic_profile_removes(iod, path[depth], path[:depth], basic)
                for depth in range(len(path))
            ):
                continue
            strictest = strictest_type(iod, tag, path)
            actions = every.get(definition.tag, set())
            if "X" in actions and strictest != "3":
                found[name, path, definition.tag, "X"] = resolve_plain_x_in_iod(
                    iod, tag, path
                )
            if "Z" in actions and strictest == "1":
                found[name, path, definition.tag, "Z"] = "Z"
            action = basic.get(definition.tag)
            if set(dictionary[definition.tag].vrs) - dummy_values.DUMMY_VRS and action:
                resolved = (
                    resolve_in_iod(iod, tag, path, action)
                    if action in compound_actions.COMPOUND_ACTIONS
                    else resolve_plain_in_iod(iod, tag, path, action)
                )
                if resolved == "D":
                    found[name, path, definition.tag, "D"] = "D"
    return found


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_the_places_where_a_plain_action_cannot_stand_in_the_brachy_and_summary_records(
    tables,
):
    found = _places_a_plain_action_cannot_keep_valid(tables, RECORD_IODS)
    reviewed = {
        (tag, action, removal)
        for (_, _, tag, action), removal in _places_a_plain_action_cannot_keep_valid(
            tables, RECORD_REVIEWED_AGAINST
        ).items()
    }

    patient = {
        (name, (), tag, "X"): _removal(*SEQUESTER)
        for name in RECORD_IODS
        for tag in (RESPONSIBLE_PERSON, RESPONSIBLE_ORGANIZATION)
    }
    # Within Patient Setup Sequence, as in RT Plan and RT Beams Treatment
    # Record; RT Treatment Summary Record has no RT Patient Setup Module.
    preparation = {
        (
            "RT Brachy Treatment Record",
            (PATIENT_SETUP, PATIENT_TREATMENT_PREPARATION, inner),
            tag,
            "X",
        ): _removal("SEQUENCE", 1 + (inner == REFERENCED_PATIENT_SETUP_PHOTO))
        for inner, tag in (
            (REFERENCED_PATIENT_SETUP_PHOTO, PATIENT_SETUP_PHOTO_DESCRIPTION),
            (PATIENT_TREATMENT_PREPARATION_PROCEDURE, PROCEDURE_PARAMETER_DESCRIPTION),
        )
    }
    # Source Manufacturer, which Table E.1-1 gives X, is Type 2 in the Type 1
    # Recorded Source Sequence, so its removal would sequester every
    # conforming RT Brachy Treatment Record; a plain X empties it there
    # instead (D-020). It is Type 3 in RT Plan's Source Sequence (300A,0210),
    # where it is removed alone.
    source = {
        (
            "RT Brachy Treatment Record",
            (RECORDED_SOURCE,),
            SOURCE_MANUFACTURER,
            "X",
        ): _removal(*EMPTIED)
    }
    assert found == {**patient, **preparation, **source}
    # Only Source Manufacturer is new: each other place matches one that the
    # IODs reviewed before them have, with the same removal.
    new = {
        key
        for key, removal in found.items()
        if (key[2], key[3], removal) not in reviewed
    }
    assert new == set(source)
    assert (
        strictest_type(tables.iods["RT Brachy Treatment Record"], RECORDED_SOURCE)
        == "1"
    )
    assert resolve_plain_x_in_iod(
        tables.iods["RT Plan"], SOURCE_MANUFACTURER, ("(300A,0210)",)
    ) == _removal(*ALONE)


# The 16 second-generation RT IODs, which the maintainer added to the target
# coverage on 31 October 2026, reviewed ahead of supporting them against the
# IODs supported before them, Enhanced RT Image and Enhanced Continuous RT
# Image among them. RT Segment Annotation, RT Radiation Set, and the three
# radiations are supported.
SECOND_GENERATION_RT_IODS = (
    "RT Physician Intent",
    "RT Segment Annotation",
    "RT Radiation Set",
    "RT Radiation Record Set",
    "RT Radiation Salvage Record",
    "RT Treatment Preparation",
    "RT Patient Position Acquisition Instruction",
    "RT Beams Delivery Instruction",
    "RT Brachy Application Setup Delivery Instruction",
    "RT Radiation Set Delivery Instruction",
    "C-Arm Photon-Electron Radiation",
    "C-Arm Photon-Electron Radiation Record",
    "Tomotherapeutic Radiation",
    "Tomotherapeutic Radiation Record",
    "Robotic-Arm Radiation",
    "Robotic-Arm Radiation Record",
)
SECOND_GENERATION_REVIEWED_AGAINST = tuple(
    name
    for name in dict.fromkeys(
        (
            *RECORD_REVIEWED_AGAINST,
            *RECORD_IODS,
            "Enhanced RT Image",
            "Enhanced Continuous RT Image",
        )
    )
    if name not in SECOND_GENERATION_RT_IODS
)
# The records whose RT Radiation Record Common Module records treatment
# tolerance violations and their overrides.
TOLERANCE_RECORD_IODS = (
    "C-Arm Photon-Electron Radiation Record",
    "Tomotherapeutic Radiation Record",
    "Robotic-Arm Radiation Record",
    "RT Radiation Salvage Record",
)
OPERATOR_IDENTIFICATION = "(0008,1072)"
REFERENCED_STUDY = "(0008,1110)"
# The selector values whose VRs have no dummy value: AE, AS, OB, UN, and UR.
SELECTOR_VALUES_WITHOUT_DUMMY = (
    "(0072,005E)",  # Selector AE Value
    "(0072,005F)",  # Selector AS Value
    "(0072,0065)",  # Selector OB Value
    "(0072,006D)",  # Selector UN Value
    "(0072,0071)",  # Selector UR Value
)
POSITION_ACQUISITION_TEMPLATE_NAME = "(3002,0121)"
POSITION_ACQUISITION_TEMPLATE_DESCRIPTION = "(3002,0123)"
PRIOR_TREATMENT_DOSE_DESCRIPTION = "(3010,0061)"
ACQUISITION_SUBTASK = ("(3002,0118)", "(3002,011A)")
PARAMETERS_SPECIFICATION = (*ACQUISITION_SUBTASK, "(3002,0126)", "(0018,9913)")
RT_PRESCRIPTION = "(3010,006B)"
OVERRIDE = ("(300A,0731)", "(3008,0060)")
RT_ACCESSORY_HOLDER_SLOT = ("(300A,0614)", "(300A,0610)")


@pytest.mark.deid_requirement("MIDI-BP-03")
def test_the_places_where_a_plain_action_cannot_stand_in_the_second_generation_rt_iods(
    tables,
):
    found = _places_a_plain_action_cannot_keep_valid(tables, SECOND_GENERATION_RT_IODS)
    reviewed = {
        (tag, action, removal)
        for (_, _, tag, action), removal in _places_a_plain_action_cannot_keep_valid(
            tables, SECOND_GENERATION_REVIEWED_AGAINST
        ).items()
    }
    new = {
        key: removal
        for key, removal in found.items()
        if (key[2], key[3], removal) not in reviewed
    }

    # Operator Identification Sequence, which Table E.1-1 gives X/D, is Type 1
    # in the Type 2 Override Sequence of the four records, so it resolves to
    # D, which a sequence has no generic dummy value for. Its reviewed rule
    # keeps each item there, each attribute under its own rule, as the
    # maintainer chose for Verifying Observer Sequence (D-021).
    operator = {
        (name, OVERRIDE, OPERATOR_IDENTIFICATION, "D"): "D"
        for name in TOLERANCE_RECORD_IODS
    }
    assert dummy_values.kept_item_attributes(OPERATOR_IDENTIFICATION, OVERRIDE)
    # Referenced Study Sequence, which Table E.1-1 gives X/Z, is Type 1 in
    # three reference items, so it resolves to D, as above.
    study = {
        (name, path, REFERENCED_STUDY, "D"): "D"
        for name, path in (
            (
                "RT Patient Position Acquisition Instruction",
                (*ACQUISITION_SUBTASK, "(3002,0132)"),
            ),
            ("RT Physician Intent", ("(3010,0057)", "(3010,005F)")),
            ("RT Physician Intent", (RT_PRESCRIPTION, "(3010,0076)")),
        )
    }
    # Selector AE, AS, OB, UN, and UR Value, which Table E.1-1 gives D, are
    # Type 1C where a constraint holds a value of their VR, which has no
    # dummy value (D-021).
    selector = {
        (
            "RT Patient Position Acquisition Instruction",
            (*PARAMETERS_SPECIFICATION, inner),
            tag,
            "D",
        ): "D"
        for inner in ("(0082,0034)", "(0082,0035)")
        for tag in SELECTOR_VALUES_WITHOUT_DUMMY
    }
    # The position acquisition template's name, Type 1, and description,
    # Type 2, are in its Type 3 identification sequence, which their plain X
    # removes.
    template = {
        (
            "RT Patient Position Acquisition Instruction",
            (*ACQUISITION_SUBTASK, "(3002,011F)"),
            tag,
            "X",
        ): _removal("SEQUENCE", 2)
        for tag in (
            POSITION_ACQUISITION_TEMPLATE_NAME,
            POSITION_ACQUISITION_TEMPLATE_DESCRIPTION,
        )
    }
    # RT Treatment Preparation holds the Patient Treatment Preparation
    # descriptions at its top level rather than within Patient Setup
    # Sequence: the photo's in the Type 3 Referenced Patient Setup Photo
    # Sequence, which its plain X removes, and the procedure parameter's as
    # Type 2 in the Type 2 Patient Treatment Preparation Procedure Sequence,
    # where no Type 3 sequence encloses it. Prior Treatment Dose Description
    # is Type 2 in the Type 1 RT Prescription Sequence. The changes that
    # support these IODs settle where a plain X sequesters (D-020).
    preparation = {
        (
            "RT Treatment Preparation",
            (REFERENCED_PATIENT_SETUP_PHOTO,),
            PATIENT_SETUP_PHOTO_DESCRIPTION,
            "X",
        ): _removal("SEQUENCE", 0),
        (
            "RT Treatment Preparation",
            (PATIENT_TREATMENT_PREPARATION_PROCEDURE,),
            PROCEDURE_PARAMETER_DESCRIPTION,
            "X",
        ): _removal(*SEQUESTER),
        (
            "RT Physician Intent",
            (RT_PRESCRIPTION,),
            PRIOR_TREATMENT_DOSE_DESCRIPTION,
            "X",
        ): _removal(*SEQUESTER),
    }
    # RT Accessory Holder Slot ID, which Table E.1-1 gives Z, takes the dummy
    # value where it is Type 1 (D-021).
    slot = {
        (name, RT_ACCESSORY_HOLDER_SLOT, RT_ACCESSORY_HOLDER_SLOT_ID, "Z"): "Z"
        for name in (
            "C-Arm Photon-Electron Radiation",
            "C-Arm Photon-Electron Radiation Record",
            "Robotic-Arm Radiation",
            "Robotic-Arm Radiation Record",
            "RT Patient Position Acquisition Instruction",
        )
    }
    assert new == {
        **operator,
        **study,
        **selector,
        **template,
        **preparation,
        **slot,
    }
    # Each other place matches one that the IODs reviewed before them have,
    # with the same removal: Responsible Person and Responsible Organization
    # in the Patient Module of all 16, and the D on the sequences that
    # reviewed rules give items, Person Identification Code Sequence,
    # Referenced Performed Procedure Step Sequence, and Institution Code
    # Sequence in Interlock Resolution User Sequence (D-021).
    assert {(tag, action) for (_, _, tag, action) in set(found) - set(new)} == {
        (RESPONSIBLE_PERSON, "X"),
        (RESPONSIBLE_ORGANIZATION, "X"),
        (PERSON_IDENTIFICATION_CODE_SEQUENCE, "D"),
        ("(0008,1111)", "D"),
        ("(0008,0082)", "D"),
    }
    for name in SECOND_GENERATION_RT_IODS:
        for tag in (RESPONSIBLE_PERSON, RESPONSIBLE_ORGANIZATION):
            assert found[name, (), tag, "X"] == _removal(*SEQUESTER), (name, tag)
    assert {path[-1] for (_, path, tag, _) in found if tag == "(0008,0082)"} == {
        "(300A,0746)"
    }
