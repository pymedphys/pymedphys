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

"""The options that the conformance statement names, and how it names them."""

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    codes,
    conformance,
    conformance_markdown,
    markers,
    policy,
    standard,
)


@pytest.fixture(name="preset", scope="module", params=list(policy.PRESETS))
def _preset(request):
    return request.param


@pytest.fixture(name="statement_for", scope="module")
def _statement_for():
    """Reuse immutable statements for ordinary assertions within this module."""
    statements = {}

    def get_statement(preset):
        if preset not in statements:
            statements[preset] = conformance.conformance_statement(
                policy.compose_policy(preset), vocabulary=None
            )
        return statements[preset]

    return get_statement


def test_each_option_names_its_cid_7050_code():
    meanings = {
        c.code_value: c.code_meaning for c in codes.load_context_group(7050).rows
    }
    assert tuple(conformance.OPTION_CODES) == standard.ALL_OPTIONS
    assert len(set(conformance.OPTION_CODES.values())) == len(standard.ALL_OPTIONS)
    assert meanings[markers.PROFILE_CODE] == (
        "Basic Application Confidentiality Profile"
    )
    for option, code in conformance.OPTION_CODES.items():
        words = meanings[code].lower().split()
        # Each option's own words appear in its code's meaning, in order.
        assert words[-1] == "option"
        for word in option.split("_"):
            assert word in words, (option, meanings[code])


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_statement_lists_the_options_composed_applied_and_not_supported(
    statement_for,
):
    text = conformance_markdown.render_markdown(statement_for("basic"))
    meanings = {
        c.code_value: c.code_meaning for c in codes.load_context_group(7050).rows
    }
    lines = {
        line.split(": ")[0]: line
        for line in text.splitlines()
        if line.startswith("- Options ")
    }
    composed = lines["- Options that PyMedPhys can compose into a policy"]
    applied = lines["- Options whose policies the engine applies"]
    unsupported = lines[
        "- Options that are not supported, since the engine does not yet apply them"
    ]
    for option in standard.ALL_OPTIONS:
        named = meanings[conformance.OPTION_CODES[option]]
        assert named in composed
        assert (named in applied) == (option in policy.ENGINE_OPTIONS)
        assert (named in unsupported) == (option not in policy.ENGINE_OPTIONS)


def test_the_statement_says_when_every_option_is_supported(monkeypatch):
    monkeypatch.setattr(conformance_markdown, "ENGINE_OPTIONS", standard.ALL_OPTIONS)
    statement = conformance.conformance_statement(
        policy.compose_policy("basic"), vocabulary=None
    )

    text = conformance_markdown.render_markdown(statement)

    assert (
        "- Options that are not supported, since the engine does not yet apply "
        "them: none.\n"
    ) in text


# Each option in turn is taken out of the options the engine applies, so the
# test runs whatever the engine applies.
@pytest.mark.parametrize("option", standard.ALL_OPTIONS)
def test_a_policy_with_an_option_the_engine_does_not_yet_apply_is_described(
    option, monkeypatch
):
    unapplied = tuple(o for o in policy.ENGINE_OPTIONS if o != option)
    monkeypatch.setattr(policy, "ENGINE_OPTIONS", unapplied)
    monkeypatch.setattr(conformance_markdown, "ENGINE_OPTIONS", unapplied)
    composed = policy.compose_custom_policy([option])
    statement = conformance.conformance_statement(composed, vocabulary=None)

    assert statement.other_elements is None
    assert conformance.PENDING_UNAPPLIED in statement.pending
    table = [e for e in statement.attributes if e.rule == conformance.TABLE_E1_1]
    assert [(e.tag, e.action) for e in table] == list(composed.actions.items())
    text = conformance_markdown.render_markdown(statement)
    assert conformance.PENDING_UNAPPLIED in text
    meanings = {
        c.code_value: c.code_meaning for c in codes.load_context_group(7050).rows
    }
    (unsupported,) = [
        line
        for line in text.splitlines()
        if line.startswith("- Options that are not supported")
    ]
    assert meanings[conformance.OPTION_CODES[option]] in unsupported


def test_the_pixel_options_outside_table_e1_1_can_be_composed_and_are_listed(
    preset, statement_for
):
    # PS3.15 E.1.1 Note 11 leaves Clean Pixel Data and Clean Recognizable
    # Visual Features out of Table E.1-1; CID 7050 still codes them.
    text = conformance_markdown.render_markdown(statement_for(preset))
    meanings = {
        c.code_value: c.code_meaning for c in codes.load_context_group(7050).rows
    }
    assert meanings["113101"] == "Clean Pixel Data Option"
    assert meanings["113102"] == "Clean Recognizable Visual Features Option"
    assert conformance.OPTION_CODES["clean_pixel_data"] == "113101"
    assert conformance.OPTION_CODES["clean_recognizable_visual_features"] == "113102"
    lines = {
        line.split(": ")[0]: line
        for line in text.splitlines()
        if line.startswith("- Options ")
    }
    unsupported = lines[
        "- Options that are not supported, since the engine does not yet apply them"
    ]
    for option in standard.PIXEL_OPTIONS:
        code = conformance.OPTION_CODES[option]
        named = f"{meanings[code]} (DCM {code})"
        applied = option in policy.ENGINE_OPTIONS
        assert named in lines["- Options that PyMedPhys can compose into a policy"]
        assert (
            named in lines["- Options whose policies the engine applies"]
        ) is applied
        assert (named in unsupported) is not applied


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_no_enabled_option_has_an_incomplete_statement():
    # Enabling an option needs a complete statement for it alone (D-033).
    for option in sorted(policy.ENABLED_OPTIONS):
        statement = conformance.conformance_statement(
            policy.compose_custom_policy([option]), vocabulary=None
        )
        assert not statement.pending, option


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_an_enabled_custom_option_set_claims_its_options(monkeypatch):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    monkeypatch.setattr(policy, "ENABLED_OPTIONS", frozenset({"clean_descriptors"}))

    statement = conformance.conformance_statement(
        policy.select_policy(options=["clean_descriptors"]), vocabulary=None
    )

    assert (statement.preset, statement.options) == (None, ("clean_descriptors",))
    assert statement.enabled and statement.claims_conformance
    text = conformance_markdown.render_markdown(statement)
    assert text.startswith(
        "# DICOM PS3.15 conformance statement for a custom option set\n"
    )
    assert (
        "Confidentiality Profile with Clean Descriptors Option (DCM 113105), for "
        "each instance whose validated result satisfies them"
    ) in " ".join(text.split())
