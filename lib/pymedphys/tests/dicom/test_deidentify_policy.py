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

"""The presets, and the validation of a policy's options before processing."""

import dataclasses
import itertools
import re
import types

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    actions,
    policy,
    standard,
    supplementary_actions,
)
from pymedphys._dicom.deidentify.temporal_roles import TemporalRole
from pymedphys.tests.dicom.test_deidentify_actions import DEVICE_DATE_CONFLICTS

DEVICE_IDENTITY = "retain_device_identity"
MODIFIED_DATES = "retain_longitudinal_modified_dates"
PATIENT_CHARACTERISTICS = "retain_patient_characteristics"
SAFE_PRIVATE = "retain_safe_private"
CLEAN_DESCRIPTORS = "clean_descriptors"
BEAM_HOLD = "(300C,0127)"  # Beam Hold Transition DateTime
TAG = re.compile(r"\([0-9A-F]{4},[0-9A-F]{4}\)")
# The options that the presets select, in Table E.1-1's order.
PRESET_OPTIONS = tuple(
    option
    for option in standard.OPTIONS
    if any(option in options for options in policy.PRESETS.values())
)


def _rows():
    return standard.load_table_e1_1().attributes


def _basic():
    return {row.tag: row.basic_profile for row in _rows()}


def _altered(tag, option, action):
    """Return Table E.1-1 of the pinned edition with one option action changed."""
    table = standard.load_table_e1_1()
    attributes = tuple(
        dataclasses.replace(
            row, options=types.MappingProxyType({**row.options, option: action})
        )
        if row.tag == tag
        else row
        for row in table.attributes
    )
    return dataclasses.replace(table, attributes=attributes)


def test_the_presets_are_the_designs_option_sets_in_the_tables_order():
    assert dict(policy.PRESETS) == {
        "basic": (),
        "basic-clean-descriptors": (CLEAN_DESCRIPTORS,),
        "tps-import": (
            DEVICE_IDENTITY,
            PATIENT_CHARACTERISTICS,
            MODIFIED_DATES,
            CLEAN_DESCRIPTORS,
        ),
        "public-release": (SAFE_PRIVATE, MODIFIED_DATES, CLEAN_DESCRIPTORS),
    }
    assert list(policy.PRESETS) == [
        "basic",
        "basic-clean-descriptors",
        "tps-import",
        "public-release",
    ]
    assert policy.DEFAULT_PRESET == "basic"
    assert policy.DEVICE_IDENTITY == DEVICE_IDENTITY
    assert policy.MODIFIED_DATES == MODIFIED_DATES


def test_each_option_is_named_in_table_e1_1s_order():
    assert (
        policy.SAFE_PRIVATE,
        policy.UIDS,
        policy.DEVICE_IDENTITY,
        policy.INSTITUTION_IDENTITY,
        policy.PATIENT_CHARACTERISTICS,
        policy.FULL_DATES,
        policy.MODIFIED_DATES,
        policy.CLEAN_DESCRIPTORS,
        policy.CLEAN_STRUCTURED_CONTENT,
        policy.CLEAN_GRAPHICS,
    ) == standard.OPTIONS


def test_the_presets_select_only_options_that_the_engine_applies():
    assert PRESET_OPTIONS == (
        SAFE_PRIVATE,
        DEVICE_IDENTITY,
        PATIENT_CHARACTERISTICS,
        MODIFIED_DATES,
        CLEAN_DESCRIPTORS,
    )
    for options in policy.PRESETS.values():
        assert options == tuple(o for o in policy.ENGINE_OPTIONS if o in options)


@pytest.mark.deid_requirement("PS3.15-E.1.1-09")
def test_the_basic_policy_gives_each_attribute_its_basic_profile_action():
    basic = policy.compose_policy("basic")

    assert basic == policy.compose_policy()
    assert basic.preset == "basic"
    assert basic.edition == "2026d"
    assert not basic.options
    assert len(basic.actions) == 657
    assert dict(basic.actions) == _basic()
    assert not basic.resolved
    assert basic.claims_conformance


def test_basic_clean_descriptors_is_the_basic_profile_with_clean_descriptors():
    composed = policy.compose_policy("basic-clean-descriptors")
    effective = actions.effective_actions([CLEAN_DESCRIPTORS])
    # The Option's action overrides the Profile's (PS3.15 E.1.1).
    overridden = {
        row.tag: row.options.get(CLEAN_DESCRIPTORS, row.basic_profile)
        for row in _rows()
    }
    basic = _basic()
    changed = {tag for tag, action in composed.actions.items() if action != basic[tag]}

    assert composed.preset == "basic-clean-descriptors"
    assert composed.edition == "2026d"
    assert composed.options == (CLEAN_DESCRIPTORS,)
    assert dict(composed.actions) == dict(effective.actions) == overridden
    assert not effective.conflicts
    assert not composed.resolved
    assert composed.claims_conformance
    assert len(changed) == 141
    assert {composed.actions[tag] for tag in changed} == {"C"}
    # Checked by hand against Table E.1-1 of the 2026d PS3.15.
    assert composed.actions["(3006,0026)"] == "C"  # ROI Name, Z in the Profile
    assert composed.actions["(3006,0085)"] == "C"  # ROI Observation Label, X
    assert composed.actions["(300A,0002)"] == "C"  # RT Plan Label, D
    assert composed.actions["(300A,00C3)"] == "C"  # Beam Description, X
    assert composed.actions["(0008,103E)"] == "C"  # Series Description, X
    # Clean Descriptors leaves identifiers and dates to the Profile.
    assert composed.actions["(0010,0010)"] == "Z"  # Patient's Name
    assert composed.actions["(0008,0020)"] == "Z"  # Study Date
    # The engine applies its option, which is valid as a custom set, which
    # allows no conflict.
    assert set(composed.options) <= set(policy.ENGINE_OPTIONS)
    custom = policy.compose_custom_policy(composed.options)
    assert dict(custom.actions) == dict(composed.actions)
    # Defined and validated, but not enabled until its behaviour is.
    assert "basic-clean-descriptors" not in policy.ENABLED_PRESETS
    assert not composed.enabled


def test_public_release_cleans_dates_descriptors_and_safe_private_attributes():
    release = policy.compose_policy("public-release")
    basic = _basic()
    changed = {tag for tag, action in release.actions.items() if action != basic[tag]}

    assert release.claims_conformance
    assert not release.resolved
    assert len(changed) == 311
    assert {release.actions[tag] for tag in changed} == {"C"}
    # Checked by hand against Table E.1-1 of the 2026d PS3.15.
    assert release.actions["(0008,0020)"] == "C"  # Study Date
    assert release.actions["(0008,103E)"] == "C"  # Series Description
    assert release.actions["(gggg,eeee) where gggg is odd"] == "C"
    assert release.actions["(0008,0201)"] == "C"  # Timezone Offset From UTC
    # Device identity and patient characteristics are not retained.
    assert release.actions["(0018,1000)"] == "X/Z/D"  # Device Serial Number
    assert release.actions["(0010,1010)"] == "X"  # Patient's Age


@pytest.mark.deid_requirement("PS3.15-E.3.6-02")
def test_tps_import_modifies_the_eleven_device_identity_and_date_conflicts():
    tps = policy.compose_policy("tps-import")
    roles = {resolution.conflict.tag: resolution.role for resolution in tps.resolved}

    assert set(roles) == DEVICE_DATE_CONFLICTS
    assert len(tps.resolved) == 11
    # Ten are device dates and times; Beam Hold Transition DateTime records an
    # event in the subject's treatment.
    assert roles.pop(BEAM_HOLD) is TemporalRole.SUBJECT_EVENT
    assert set(roles.values()) == {TemporalRole.DEVICE}
    for resolution in tps.resolved:
        assert dict(resolution.conflict.actions) == {
            DEVICE_IDENTITY: "K",
            MODIFIED_DATES: "C",
        }
        assert resolution.action == "C"
        assert resolution.unmet == (DEVICE_IDENTITY,)
        assert tps.actions[resolution.conflict.tag] == "C"
    table_order = [row.tag for row in _rows() if row.tag in DEVICE_DATE_CONFLICTS]
    assert [r.conflict.tag for r in tps.resolved] == table_order
    assert not tps.claims_conformance


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
@pytest.mark.parametrize(
    "tag",
    [
        "(0018,1000)",  # Device Serial Number
        "(0008,1010)",  # Station Name
        "(0018,1002)",  # Device UID
        "(0010,1010)",  # Patient's Age
        "(0010,0040)",  # Patient's Sex
        "(0010,1030)",  # Patient's Weight
    ],
)
def test_tps_import_keeps_device_identity_and_patient_characteristics(tag):
    assert policy.compose_policy("tps-import").actions[tag] == "K"


def test_tps_import_changes_only_what_its_options_change():
    tps = policy.compose_policy("tps-import")
    basic = _basic()
    changed = {tag for tag, action in tps.actions.items() if action != basic[tag]}

    # No option gives Patient's Birth Date an action.
    assert tps.actions["(0010,0030)"] == "Z"
    assert len(changed) == 374
    assert sum(tps.actions[tag] == "K" for tag in changed) == 51


@pytest.mark.deid_requirement("PS3.15-E.1.1-09")
@pytest.mark.parametrize(
    "preset", ["basic", "basic-clean-descriptors", "tps-import", "public-release"]
)
def test_each_preset_gives_each_attribute_one_action(preset):
    composed = policy.compose_policy(preset)

    assert list(composed.actions) == [row.tag for row in _rows()]
    assert set(composed.actions.values()) <= standard.ACTION_CODES
    assert composed.options == policy.PRESETS[preset]
    # Every supplementary rule has an action too, for an attribute that
    # Table E.1-1 omits.
    rules = supplementary_actions.load_supplementary_actions().rules
    assert set(composed.supplementary_actions) == set(rules)
    assert not set(composed.supplementary_actions) & set(composed.actions)
    assert set(composed.supplementary_actions.values()) <= standard.ACTION_CODES
    for resolution in composed.resolved:
        assert resolution.action != "K"
        assert composed.actions[resolution.conflict.tag] != "K"


def test_no_preset_is_enabled_yet():
    assert policy.ENABLED_PRESETS == frozenset()
    assert not any(policy.compose_policy(p).enabled for p in policy.PRESETS)
    with pytest.raises(policy.PolicyError, match="^the basic preset is not enabled"):
        policy.select_policy()


def test_an_enabled_preset_is_selected(monkeypatch):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))

    assert [p for p in policy.PRESETS if policy.compose_policy(p).enabled] == ["basic"]
    selected = policy.select_policy()
    assert selected == policy.select_policy("basic") == policy.compose_policy()
    assert selected.preset == "basic"
    assert selected.enabled


@pytest.mark.parametrize(
    "preset", ["basic", "basic-clean-descriptors", "tps-import", "public-release"]
)
def test_a_preset_that_is_not_enabled_is_not_selected(preset):
    message = (
        f"the {preset} preset is not enabled: its behaviour is not yet "
        "implemented and validated; no preset is enabled yet"
    )
    with pytest.raises(policy.PolicyError, match=f"^{re.escape(message)}$"):
        policy.select_policy(preset)


@pytest.mark.parametrize(
    "enabled, status",
    [
        ({"basic"}, "only basic is enabled"),
        ({"public-release", "basic"}, "only basic and public-release are enabled"),
    ],
)
def test_the_refusal_names_the_enabled_presets(monkeypatch, enabled, status):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset(enabled))
    message = (
        "the tps-import preset is not enabled: its behaviour is not yet "
        f"implemented and validated; {status}"
    )
    with pytest.raises(policy.PolicyError, match=f"^{re.escape(message)}$"):
        policy.select_policy("tps-import")


def test_only_composing_an_enabled_preset_enables_a_policy(monkeypatch):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    selected = policy.select_policy()
    custom = policy.compose_custom_policy([SAFE_PRIVATE])

    # Python 3.13 changed the error from a ValueError to a TypeError.
    with pytest.raises((TypeError, ValueError), match="enabled"):
        dataclasses.replace(custom, enabled=True)
    given = {f.name: getattr(selected, f.name) for f in dataclasses.fields(selected)}
    with pytest.raises(TypeError, match="enabled"):
        policy.Policy(**given)
    # A copy, whether identical or altered, is not enabled.
    del given["enabled"]
    assert not policy.Policy(**given).enabled
    assert not dataclasses.replace(selected).enabled
    kept = types.MappingProxyType({**selected.actions, "(0010,0010)": "K"})
    assert not dataclasses.replace(selected, actions=kept).enabled
    assert hash(selected) == hash(policy.compose_policy())


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
@pytest.mark.parametrize(
    "options",
    [
        subset
        for size in range(len(PRESET_OPTIONS) + 1)
        for subset in itertools.combinations(PRESET_OPTIONS, size)
    ],
)
def test_a_custom_option_set_is_validated_and_never_enabled(options):
    if {DEVICE_IDENTITY, MODIFIED_DATES} <= set(options):
        with pytest.raises(
            policy.PolicyError, match="no precedence.*only the tps-import preset"
        ):
            policy.compose_custom_policy(options)
        return

    custom = policy.compose_custom_policy(reversed(options))

    assert dict(custom.actions) == dict(actions.effective_actions(options).actions)
    assert dict(custom.supplementary_actions) == dict(
        actions.effective_supplementary_actions(options).actions
    )
    assert custom.options == options
    assert custom.preset is None
    assert not custom.enabled
    assert not custom.resolved
    assert custom.claims_conformance


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
def test_the_tps_import_options_are_rejected_without_the_preset():
    with pytest.raises(policy.PolicyError) as raised:
        policy.compose_custom_policy(policy.PRESETS["tps-import"])

    message = str(raised.value)
    assert f"{DEVICE_IDENTITY} and {MODIFIED_DATES}" in message
    assert "11 attributes" in message
    assert "PS3.15 defines no precedence between options" in message
    assert "only the tps-import preset, which claims no PS3.15 conformance" in message
    table_order = [row.tag for row in _rows() if row.tag in DEVICE_DATE_CONFLICTS]
    assert TAG.findall(message) == table_order


def test_the_tps_import_hint_needs_every_conflict_to_be_one_it_resolves():
    # Retain Patient Characteristics keeping Allergies, which Clean
    # Descriptors cleans, alongside the eleven that tps-import resolves.
    table = _altered("(0010,2110)", PATIENT_CHARACTERISTICS, "K")

    with pytest.raises(policy.PolicyError, match="no precedence") as raised:
        policy.compose_custom_policy(policy.PRESETS["tps-import"], table=table)

    message = str(raised.value)
    assert set(TAG.findall(message)) == DEVICE_DATE_CONFLICTS | {"(0010,2110)"}
    assert "only the tps-import preset" not in message


def test_only_the_tps_import_preset_resolves_its_conflicts(monkeypatch):
    # Another preset selecting both options would not share the exemption.
    presets = {**policy.PRESETS, "device-dates": (DEVICE_IDENTITY, MODIFIED_DATES)}
    monkeypatch.setattr(policy, "PRESETS", types.MappingProxyType(presets))

    with pytest.raises(policy.PolicyError, match="11 attributes"):
        policy.compose_policy("device-dates")
    assert len(policy.compose_policy("tps-import").resolved) == 11


@pytest.mark.deid_requirement("PS3.15-E.1.1-02")
@pytest.mark.parametrize(
    "preset, tag, option, action",
    [
        # Clean Descriptors removing Study Date, which Modified Dates cleans.
        ("public-release", "(0008,0020)", CLEAN_DESCRIPTORS, "X"),
        # Retain Patient Characteristics keeping Allergies, which Clean
        # Descriptors cleans.
        ("tps-import", "(0010,2110)", PATIENT_CHARACTERISTICS, "K"),
        # Two other options conflicting on a subject event.
        ("tps-import", "(0008,0020)", PATIENT_CHARACTERISTICS, "K"),
        # A third option joining a device-date conflict.
        ("tps-import", "(0018,1200)", CLEAN_DESCRIPTORS, "X"),
        # The device-date actions on an attribute without a temporal role.
        ("tps-import", "(0018,1000)", MODIFIED_DATES, "C"),
    ],
)
def test_a_conflict_that_a_new_edition_adds_is_rejected(preset, tag, option, action):
    table = _altered(tag, option, action)
    assert table.edition == "2026d"

    with pytest.raises(policy.PolicyError, match="no precedence") as raised:
        policy.compose_policy(preset, table=table)

    # Only the new conflict is named, not the eleven that tps-import resolves.
    assert TAG.findall(str(raised.value)) == [tag]
    assert "only the tps-import preset" not in str(raised.value)


@pytest.mark.parametrize("option", standard.OPTIONS)
def test_every_option_of_table_e1_1_can_be_composed(option):
    composed = policy.compose_custom_policy([CLEAN_DESCRIPTORS, option])

    assert composed.options == tuple(
        o for o in standard.OPTIONS if o in {CLEAN_DESCRIPTORS, option}
    )
    assert composed.preset is None
    assert not composed.enabled
    assert composed.claims_conformance


def test_the_two_retain_longitudinal_temporal_information_options_are_exclusive():
    message = (
        "the options retain_longitudinal_full_dates and "
        "retain_longitudinal_modified_dates are mutually exclusive (PS3.15 E.3.6)"
    )
    with pytest.raises(policy.PolicyError, match=f"^{re.escape(message)}$"):
        policy.compose_custom_policy(
            [MODIFIED_DATES, CLEAN_DESCRIPTORS, "retain_longitudinal_full_dates"]
        )


def test_the_engine_applies_the_options_that_it_marks_applied():
    assert tuple(policy.ENGINE_APPLIES) == standard.OPTIONS
    assert policy.ENGINE_OPTIONS == tuple(
        o for o in standard.OPTIONS if policy.ENGINE_APPLIES[o]
    )


@pytest.mark.parametrize(
    "options, named",
    [
        (
            ["retain_longitudinal_full_dates"],
            "the option retain_longitudinal_full_dates, so a policy that selects it",
        ),
        (
            ["retain_uids", "retain_longitudinal_full_dates", CLEAN_DESCRIPTORS],
            "the options retain_uids and retain_longitudinal_full_dates, so a "
            "policy that selects them",
        ),
    ],
)
def test_an_option_the_engine_does_not_yet_apply_is_refused_by_name(
    monkeypatch, options, named
):
    # The refusal names the options, whichever the engine applies.
    applied = (SAFE_PRIVATE, DEVICE_IDENTITY, CLEAN_DESCRIPTORS)
    monkeypatch.setattr(policy, "ENGINE_OPTIONS", applied)
    composed = policy.compose_custom_policy(options)
    message = (
        f"the engine does not yet apply {named} can be composed and described "
        "but not applied; the engine applies retain_safe_private, "
        "retain_device_identity, and clean_descriptors"
    )

    with pytest.raises(policy.PolicyError, match=f"^{re.escape(message)}$"):
        policy.refuse_unapplied_options(composed)


@pytest.mark.parametrize("preset", policy.PRESETS)
def test_no_preset_selects_an_option_the_engine_does_not_yet_apply(preset):
    policy.refuse_unapplied_options(policy.compose_policy(preset))


def test_an_unknown_preset_is_rejected():
    message = (
        "unknown preset 'research'; the presets are basic, "
        "basic-clean-descriptors, tps-import, and public-release"
    )
    with pytest.raises(policy.PolicyError, match=f"^{re.escape(message)}$"):
        policy.compose_policy("research")
    with pytest.raises(policy.PolicyError, match="unknown preset"):
        policy.select_policy("research")


@pytest.mark.parametrize("preset", [None, ["basic"], 1])
def test_a_preset_must_be_named(preset):
    with pytest.raises(TypeError, match="^preset must be the name of a preset$"):
        policy.compose_policy(preset)


def test_an_unknown_option_is_rejected():
    with pytest.raises(policy.PolicyError, match="'retain_everything'"):
        policy.compose_custom_policy([CLEAN_DESCRIPTORS, "retain_everything"])


def test_a_single_string_is_not_taken_as_its_characters():
    with pytest.raises(TypeError, match="collection of option names"):
        policy.compose_custom_policy(CLEAN_DESCRIPTORS)


def test_a_table_of_another_edition_is_rejected():
    table = dataclasses.replace(standard.load_table_e1_1(), edition="2099a")

    with pytest.raises(policy.PolicyError, match="2099a.*2026d"):
        policy.compose_policy("basic", table=table)
    with pytest.raises(policy.PolicyError, match="2099a.*2026d"):
        policy.compose_custom_policy([], table=table)


def test_a_policy_from_a_given_table_is_not_enabled(monkeypatch):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    given = policy.compose_policy("basic", table=standard.load_table_e1_1())

    assert dict(given.actions) == _basic()
    assert not given.enabled
    assert policy.compose_policy("basic").enabled


def test_the_policy_is_read_only():
    tps = policy.compose_policy("tps-import")

    with pytest.raises(TypeError):
        tps.actions["(0010,0010)"] = "K"  # type: ignore[index]
    with pytest.raises(TypeError):
        tps.supplementary_actions["(300A,00C2)"] = "K"  # type: ignore[index]
    with pytest.raises(TypeError):
        policy.PRESETS["basic"] = (DEVICE_IDENTITY,)  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        tps.enabled = True  # type: ignore[misc]
