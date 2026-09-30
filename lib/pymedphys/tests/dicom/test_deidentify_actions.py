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

"""The action of each attribute of Table E.1-1 under a profile and its options."""

import dataclasses

from pymedphys._imports import hypothesis, pytest

from pymedphys._dicom.deidentify import actions, standard

st = hypothesis.strategies

FULL_DATES = "retain_longitudinal_full_dates"
MODIFIED_DATES = "retain_longitudinal_modified_dates"
DEVICE_IDENTITY = "retain_device_identity"
# The attributes that are K under Retain Device Identity and C under Modified
# Dates in the 2026d Table E.1-1, as the design document lists them.
DEVICE_DATE_CONFLICTS = {
    "(0018,1200)",  # Date of Last Calibration
    "(0018,1201)",  # Time of Last Calibration
    "(0018,1202)",  # DateTime of Last Calibration
    "(0018,1203)",  # Calibration DateTime
    "(0018,1204)",  # Date of Manufacture
    "(0018,1205)",  # Date of Installation
    "(0014,407C)",  # Calibration Time
    "(0014,407E)",  # Calibration Date
    "(0018,700C)",  # Date of Last Detector Calibration
    "(0018,700E)",  # Time of Last Detector Calibration
    "(300C,0127)",  # Beam Hold Transition DateTime
}


def _rows():
    return standard.load_table_e1_1().attributes


def test_the_basic_profile_alone_gives_each_attribute_its_profile_action():
    effective = actions.effective_actions()

    assert not effective.options
    assert effective.edition == "2026d"
    assert not effective.conflicts
    assert len(effective.actions) == 657
    assert dict(effective.actions) == {row.tag: row.basic_profile for row in _rows()}


@pytest.mark.parametrize(
    "option, tag, profile_action, option_action",
    [
        # Checked by hand against Table E.1-1 of the 2026d PS3.15.
        ("retain_patient_characteristics", "(0010,1010)", "X", "K"),  # Age
        ("retain_patient_characteristics", "(0010,0040)", "Z", "K"),  # Sex
        (DEVICE_IDENTITY, "(0018,1000)", "X/Z/D", "K"),  # Device Serial Number
        ("retain_uids", "(0020,000D)", "U", "K"),  # Study Instance UID
        (MODIFIED_DATES, "(0008,0020)", "Z", "C"),  # Study Date
        (FULL_DATES, "(0008,0020)", "Z", "K"),
        ("clean_descriptors", "(0008,103E)", "X", "C"),  # Series Description
        ("retain_safe_private", "(gggg,eeee) where gggg is odd", "X", "C"),
    ],
)
def test_an_option_overrides_the_profile(option, tag, profile_action, option_action):
    assert actions.effective_actions().actions[tag] == profile_action
    assert actions.effective_actions([option]).actions[tag] == option_action


def test_an_option_leaves_the_attributes_it_gives_no_action():
    effective = actions.effective_actions(["retain_patient_characteristics"])

    assert effective.actions["(0010,0010)"] == "Z"  # Patient's Name
    assert effective.actions["(0010,0020)"] == "Z/D"  # Patient ID


@pytest.mark.parametrize(
    "options, tag, action",
    [
        (("retain_uids", DEVICE_IDENTITY), "(0018,1002)", "K"),  # Device UID
        (
            ("retain_patient_characteristics", "clean_descriptors"),
            "(0010,2110)",  # Allergies
            "C",
        ),
    ],
)
def test_options_that_agree_give_their_common_action(options, tag, action):
    effective = actions.effective_actions(options)

    assert effective.actions[tag] == action
    assert not effective.conflicts


def test_full_and_modified_dates_conflict_on_every_date_they_list():
    effective = actions.effective_actions([FULL_DATES, MODIFIED_DATES])
    conflicting = {conflict.tag for conflict in effective.conflicts}

    assert len(conflicting) == 169
    assert "(0008,0020)" in conflicting  # Study Date
    assert conflicting.isdisjoint(effective.actions)
    for conflict in effective.conflicts:
        assert dict(conflict.actions) == {FULL_DATES: "K", MODIFIED_DATES: "C"}


def test_device_identity_and_modified_dates_conflict_on_eleven_attributes():
    effective = actions.effective_actions([DEVICE_IDENTITY, MODIFIED_DATES])

    assert {conflict.tag for conflict in effective.conflicts} == DEVICE_DATE_CONFLICTS
    for conflict in effective.conflicts:
        assert dict(conflict.actions) == {DEVICE_IDENTITY: "K", MODIFIED_DATES: "C"}
    beam_hold = next(c for c in effective.conflicts if c.tag == "(300C,0127)")
    assert beam_hold.name == "Beam Hold Transition DateTime"


def test_a_conflict_lists_every_selected_option_that_gives_an_action():
    effective = actions.effective_actions(
        [DEVICE_IDENTITY, FULL_DATES, MODIFIED_DATES, "retain_uids"]
    )
    beam_hold = next(c for c in effective.conflicts if c.tag == "(300C,0127)")

    # Retain Device Identity and Full Dates agree, but Modified Dates does not.
    assert dict(beam_hold.actions) == {
        DEVICE_IDENTITY: "K",
        FULL_DATES: "K",
        MODIFIED_DATES: "C",
    }
    assert list(beam_hold.actions) == [DEVICE_IDENTITY, FULL_DATES, MODIFIED_DATES]


@hypothesis.given(st.sets(st.sampled_from(standard.OPTIONS)))
def test_each_attribute_has_one_action_or_a_conflict(selected):
    effective = actions.effective_actions(selected)
    conflicts = {conflict.tag: conflict for conflict in effective.conflicts}

    assert effective.options == tuple(o for o in standard.OPTIONS if o in selected)
    assert set(effective.actions).isdisjoint(conflicts)
    for row in _rows():
        given = {o: a for o, a in row.options.items() if o in selected}
        if len(set(given.values())) > 1:
            assert dict(conflicts[row.tag].actions) == given
        elif given:
            assert effective.actions[row.tag] == next(iter(given.values()))
        else:
            assert effective.actions[row.tag] == row.basic_profile


def test_options_are_reported_once_in_the_tables_order():
    effective = actions.effective_actions(
        ["clean_descriptors", "retain_uids", "clean_descriptors"]
    )

    assert effective.options == ("retain_uids", "clean_descriptors")


def test_an_unknown_option_is_rejected():
    with pytest.raises(ValueError, match="'retain_everything'"):
        actions.effective_actions(["retain_uids", "retain_everything"])


def test_a_single_string_is_not_taken_as_its_characters():
    with pytest.raises(TypeError, match="collection of option names"):
        actions.effective_actions("retain_uids")


def test_the_table_can_be_given():
    table = standard.load_table_e1_1()
    first = table.attributes[0]
    altered = dataclasses.replace(
        table,
        edition="2099a",
        attributes=(dataclasses.replace(first, options={"clean_descriptors": "C"}),),
    )

    effective = actions.effective_actions(["clean_descriptors"], table=altered)

    assert effective.edition == "2099a"
    assert dict(effective.actions) == {first.tag: "C"}


def test_the_results_are_read_only():
    effective = actions.effective_actions([FULL_DATES, MODIFIED_DATES])

    with pytest.raises(TypeError):
        effective.actions["(0010,0010)"] = "K"  # type: ignore[index]
    with pytest.raises(TypeError):
        effective.conflicts[0].actions[FULL_DATES] = "X"  # type: ignore[index]
