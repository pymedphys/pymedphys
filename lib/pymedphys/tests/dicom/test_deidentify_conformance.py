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

"""The conformance statement generated from a policy and the pinned tables."""

import dataclasses
import platform
import re

from pymedphys._imports import pydicom, pytest, tomlkit

from pymedphys._dicom.deidentify import (
    codes,
    compound_actions,
    conformance,
    conformance_markdown,
    dummy_values,
    element_rules,
    file_meta,
    iods,
    markers,
    method_digest,
    policy,
    pseudonyms,
    scope,
    sop_classes,
    standard,
    uid_roles,
    uids,
    walker,
)
from pymedphys._dicom.deidentify.element_rules import _ENGINE_GROUPS, _ENGINE_TAGS
from pymedphys.tests.dicom.test_deidentify_method_digest import VOCABULARY

INSTITUTION_NAME = "(0008,0080)"  # X/Z/D in the Basic Profile
# ROI Creator Sequence and Referring Physician Identification Sequence, which
# the Basic Profile removes with their contents.
ROI_CREATOR = ("(3006,0020)", "(3006,004D)")
REFERRING_PHYSICIAN_IDENTIFICATION = ("(0008,0096)",)
# Asserter Identification Sequence, which the Basic Profile keeps, within RT
# Assertions Sequence.
ASSERTER_IDENTIFICATION = ("(0044,0110)", "(0044,0103)")
CT_FOR_PROCESSING = "1.2.840.10008.5.1.4.1.1.2.3"
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


@pytest.fixture(name="preset", scope="module", params=list(policy.PRESETS))
def _preset(request):
    return request.param


def _statement(preset, vocabulary=None):
    return conformance.conformance_statement(
        policy.compose_policy(preset), vocabulary=vocabulary
    )


@pytest.fixture(name="statement_for", scope="module")
def _statement_for():
    """Reuse immutable statements for ordinary assertions within this module."""
    statements = {}

    def get_statement(preset, vocabulary=None):
        key = (preset, vocabulary)
        if key not in statements:
            statements[key] = _statement(preset, vocabulary=vocabulary)
        return statements[key]

    return get_statement


def _entry(statement, tag):
    return next(e for e in statement.attributes if e.tag == tag)


def _sequence_action(composed):
    """Return the action of a sequence under a policy at a place in an IOD.

    Without element rules, which the engine refuses for some policies, the
    policy's own action applies, U for a UID, and K otherwise.
    """
    try:
        rules = element_rules.ElementRules(composed)
    except policy.PolicyError:
        rules = None
    given = {**composed.actions, **composed.supplementary_actions}
    roles = uid_roles.load_uid_roles().rules

    def action(iod, tag, path):
        if rules is not None:
            return rules.rule(tag, path, iod=iod).action
        return given.get(tag, "U" if tag in roles else "K")

    return action


def _removed_with_a_sequence(sequence_action, iod, path):
    """Whether the walker removes ``path`` with a sequence that encloses it."""
    for depth, tag in enumerate(path):
        action = sequence_action(iod, tag, path[:depth])
        if action in compound_actions.COMPOUND_ACTIONS:
            action = compound_actions.resolve_in_iod(iod, tag, path[:depth], action)
        else:
            action = compound_actions.resolve_plain_in_iod(
                iod, tag, path[:depth], action
            )
        if action not in walker.DESCENDED:
            return True
    return False


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_the_statement_names_the_edition_preset_and_options(preset, statement_for):
    composed = policy.compose_policy(preset)
    statement = statement_for(preset)
    assert statement.edition == composed.edition == "2026d"
    assert statement.preset == preset
    assert statement.options == composed.options

    text = conformance_markdown.render_markdown(statement)
    assert "DICOM PS3.15 2026d" in text
    assert f"`{preset}`" in text
    meanings = {
        c.code_value: c.code_meaning for c in codes.load_context_group(7050).rows
    }
    for option in composed.options:
        assert meanings[conformance.OPTION_CODES[option]] in text


def test_each_option_names_its_cid_7050_code():
    meanings = {
        c.code_value: c.code_meaning for c in codes.load_context_group(7050).rows
    }
    assert set(conformance.OPTION_CODES) == set(standard.OPTIONS)
    assert len(set(conformance.OPTION_CODES.values())) == len(standard.OPTIONS)
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
def test_options_outside_the_supported_scope_are_listed_as_not_supported(statement_for):
    text = conformance_markdown.render_markdown(statement_for("basic"))
    meanings = {
        c.code_value: c.code_meaning for c in codes.load_context_group(7050).rows
    }
    supported, unsupported = text.split("Options that are not supported")
    for option in policy.TARGET_OPTIONS:
        assert meanings[conformance.OPTION_CODES[option]] in supported
    for option in set(standard.OPTIONS) - set(policy.TARGET_OPTIONS):
        assert meanings[conformance.OPTION_CODES[option]] in unsupported


def test_the_pixel_options_outside_table_e1_1_are_listed_as_not_supported(
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
    (line,) = [
        line
        for line in text.splitlines()
        if line.startswith("- Options that are not supported: ")
    ]
    for code in conformance.PIXEL_OPTION_CODES:
        assert f"{meanings[code]} (DCM {code})" in line
    assert set(conformance.PIXEL_OPTION_CODES).isdisjoint(
        conformance.OPTION_CODES.values()
    )


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_every_table_row_and_supplementary_rule_is_listed_with_the_policys_action(
    preset,
    statement_for,
):
    composed = policy.compose_policy(preset)
    statement = statement_for(preset)
    table = [e for e in statement.attributes if e.rule == conformance.TABLE_E1_1]
    supplementary = [
        e for e in statement.attributes if e.rule == conformance.SUPPLEMENTARY
    ]
    assert [(e.tag, e.policy_action or e.action) for e in table] == list(
        composed.actions.items()
    )
    assert [e.name for e in table] == [
        row.name for row in standard.load_table_e1_1().attributes
    ]
    assert {e.tag: e.policy_action or e.action for e in supplementary} == dict(
        composed.supplementary_actions
    )
    names = {a.tag: a.name for a in standard.load_data_dictionary().attributes}
    assert all(e.name == names[e.tag] for e in supplementary)


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_every_ui_attribute_that_the_table_omits_is_listed_by_its_role(statement_for):
    statement = statement_for("basic")
    listed = {e.tag: e for e in statement.attributes}
    table = {row.tag for row in standard.load_table_e1_1().attributes}
    roles = uid_roles.load_uid_roles().rules
    omitted = {tag: rule.role for tag, rule in roles.items() if tag not in table}
    assert omitted
    by_role = {
        e.tag: e.rule
        for e in statement.attributes
        if e.rule in (conformance.UID_INSTANCE, conformance.UID_DEFINITION)
    }
    assert by_role == {
        tag: (
            conformance.UID_INSTANCE
            if role is uid_roles.UIDRole.INSTANCE
            else conformance.UID_DEFINITION
        )
        for tag, role in omitted.items()
    }
    assert all(listed[tag].action == "U" for tag in omitted)


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_compound_actions_are_resolved_at_every_place_a_supported_iod_defines_them(
    preset,
    statement_for,
):
    statement = statement_for(preset)
    sequence_action = _sequence_action(policy.compose_policy(preset))
    tables = iods.load_iod_tables()
    for entry in statement.attributes:
        if entry.action not in compound_actions.COMPOUND_ACTIONS:
            continue
        assert entry.elsewhere == compound_actions.resolve(entry.action, "3")
        expected = []
        for name in sorted(scope.SUPPORTED_IODS):
            iod = tables.iods[name]
            paths = dict.fromkeys(d.path for d in iod.definitions if d.tag == entry.tag)
            for path in paths:
                if _removed_with_a_sequence(sequence_action, iod, path):
                    continue
                action = compound_actions.resolve_in_iod(
                    iod, entry.tag.replace("60xx", "6000"), path, entry.action
                )
                expected.append(conformance.Place(name, path, action))
        assert entry.places == tuple(expected), entry.tag


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_institution_name_is_resolved_by_its_type_at_each_place(statement_for):
    places = _entry(statement_for("basic"), INSTITUTION_NAME).places
    found = {(p.iod, p.path): p.action for p in places}
    assert found[("RT Plan", ASSERTER_IDENTIFICATION)] == "Z"
    assert found[("RT Structure Set", ())] == "X"
    # Places within a sequence that the Basic Profile removes are not listed.
    assert ("RT Structure Set", ROI_CREATOR) not in found
    assert ("RT Structure Set", REFERRING_PHYSICIAN_IDENTIFICATION) not in found

    text = conformance_markdown.render_markdown(statement_for("basic"))
    row = next(line for line in text.splitlines() if f"| {INSTITUTION_NAME} |" in line)
    assert row.endswith(
        "| Z within RT Assertions Sequence (0044,0110) > Asserter Identification "
        "Sequence (0044,0103) in RT Plan. X elsewhere. |"
    )


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_x_z_on_a_type_1_attribute_is_described_as_the_dummy_value(statement_for):
    text = conformance_markdown.render_markdown(statement_for("basic"))
    assert (
        "X/Z on a Type 1 or 1C attribute gives D, the dummy value that Z may write."
        in (" ".join(text.split()))
    )


def test_a_place_that_sequesters_the_instance_is_listed_as_such(monkeypatch):
    resolve_in_iod = compound_actions.resolve_in_iod

    def sequestering(iod, tag, path, action):
        if tag == INSTITUTION_NAME and tuple(path) == ASSERTER_IDENTIFICATION:
            return conformance.SEQUESTER
        return resolve_in_iod(iod, tag, path, action)

    monkeypatch.setattr(compound_actions, "resolve_in_iod", sequestering)
    statement = _statement("basic")
    places = _entry(statement, INSTITUTION_NAME).places
    assert conformance.Place(
        "RT Plan", ASSERTER_IDENTIFICATION, conformance.SEQUESTER
    ) in (places)
    text = conformance_markdown.render_markdown(statement)
    row = next(line for line in text.splitlines() if f"| {INSTITUTION_NAME} |" in line)
    assert (
        "instance sequestered within RT Assertions Sequence (0044,0110) > "
        "Asserter Identification Sequence (0044,0103) in RT Plan." in row
    )


def test_the_scope_is_what_the_classifier_supports(statement_for):
    statement = statement_for("basic")
    assert statement.iods == tuple(sorted(scope.SUPPORTED_IODS))
    assert {s.uid for s in statement.transfer_syntaxes} == (
        scope.SUPPORTED_TRANSFER_SYNTAXES
    )
    listed = {s.uid for s in statement.sop_classes}
    for row in sop_classes.load_storage_sop_classes().rows:
        supported = all(
            not scope.classify(row.uid, syntax).sequestered
            for syntax in scope.SUPPORTED_TRANSFER_SYNTAXES
        )
        assert (row.uid in listed) == supported, row.uid
    assert CT_FOR_PROCESSING in listed
    assert {s.iod for s in statement.sop_classes} == scope.SUPPORTED_IODS

    text = conformance_markdown.render_markdown(statement)
    for sop_class in statement.sop_classes:
        assert f"| {sop_class.uid} | {sop_class.name} | {sop_class.iod} |" in text
    for syntax in statement.transfer_syntaxes:
        assert f"| {syntax.uid} | {syntax.name} |" in text


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_dummy_values_are_those_that_d_writes(statement_for):
    text = conformance_markdown.render_markdown(statement_for("basic"))
    for vr, (first, second) in dummy_values.CONSTANTS.items():
        assert f"| {vr} | `{first}` | `{second}` |" in text
    assert f"`{pseudonyms.PATIENT_ID_PREFIX}`" in text
    assert f"`{pseudonyms.FAMILY_NAME}^`" in text
    assert uids.UID_ROOT in text
    assert str(uids.UID_NAMESPACE) in text
    assert "PyMedPhys" not in "".join(map(str, dummy_values.CONSTANTS.values()))


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_key_and_the_scope_of_referential_integrity_are_described(statement_for):
    text = conformance_markdown.render_markdown(statement_for("basic"))
    assert "256-bit" in text
    assert "HMAC-SHA256" in text
    assert "discarded after the run" in text


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_no_attribute_is_encrypted_for_later_reidentification(statement_for):
    text = conformance_markdown.render_markdown(statement_for("basic"))
    assert "Encrypted Attributes Sequence (0400,0500)" in text
    assert "No attribute is placed in an Encrypted Attributes Data Set" in text


@pytest.mark.deid_requirement("MIDI-BP-18")
@pytest.mark.parametrize("vocabulary", [None, VOCABULARY])
def test_the_method_digest_is_the_policys_with_the_same_vocabulary(
    preset, vocabulary, statement_for
):
    composed = policy.compose_policy(preset)
    statement = statement_for(preset, vocabulary=vocabulary)
    assert statement.method_digest == method_digest.method_digest(
        composed, vocabulary=vocabulary
    )
    expected = method_digest.digest_inputs(vocabulary=vocabulary).vocabulary
    assert statement.vocabulary_digest == expected
    text = conformance_markdown.render_markdown(statement)
    assert statement.method_digest in text
    if vocabulary is None:
        assert "without a vocabulary" in text
    else:
        assert expected in text


def test_the_vocabulary_must_be_given_by_name():
    with pytest.raises(TypeError):
        conformance.conformance_statement(policy.compose_policy("basic"))  # pylint: disable=missing-kwoa


def test_a_policy_must_be_a_policy():
    with pytest.raises(TypeError, match="policy must be a Policy"):
        conformance.conformance_statement("basic", vocabulary=None)


def test_a_policy_composed_from_another_table_is_refused():
    table = standard.load_table_e1_1()
    altered = dataclasses.replace(table, attributes=table.attributes[1:])
    composed = policy.compose_policy("basic", table=altered)
    with pytest.raises(ValueError, match="not composed from the pinned Table E.1-1"):
        conformance.conformance_statement(composed, vocabulary=None)


def test_tps_import_claims_no_conformance_and_names_each_unmet_option(statement_for):
    composed = policy.compose_policy("tps-import")
    statement = statement_for("tps-import")
    assert not statement.claims_conformance
    text = conformance_markdown.render_markdown(statement)
    assert "makes no PS3.15 conformance claim" in text
    for resolved in composed.resolved:
        line = next(
            line
            for line in text.splitlines()
            if line.lstrip().startswith(f"- {resolved.conflict.tag} ")
        )
        assert "Retain Device Identity Option" in line


def test_a_preset_that_is_not_enabled_makes_no_claim(preset, statement_for):
    statement = statement_for(preset)
    assert not statement.enabled
    assert not statement.claims_conformance
    text = conformance_markdown.render_markdown(statement)
    assert "is not enabled" in text
    assert "de-identified in accordance with" not in text


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_a_statement_with_sections_still_to_describe_makes_no_claim(monkeypatch):
    # Clean Descriptors leaves the manner of cleaning to describe.
    preset = "basic-clean-descriptors"
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({preset}))
    statement = _statement(preset)
    assert statement.enabled
    assert statement.pending
    assert not statement.claims_conformance
    text = conformance_markdown.render_markdown(statement)
    assert "Not yet described" in text
    for item in statement.pending:
        assert item in text
    assert "de-identified in accordance with" not in text


def test_a_complete_statement_of_an_enabled_preset_claims_conformance(monkeypatch):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    monkeypatch.setattr(conformance, "PENDING", ())
    # As once the walker applies the removals that D-020 decides.
    monkeypatch.setattr(
        compound_actions,
        "resolve_plain_x_in_iod",
        lambda iod, tag, path: compound_actions.PlainRemoval(
            compound_actions.RemovalExtent.ATTRIBUTE
        ),
    )
    statement = _statement("basic")
    assert not statement.pending
    assert statement.claims_conformance
    text = conformance_markdown.render_markdown(statement)
    assert (
        "de-identified in accordance with the DICOM PS3.15 2026d Basic "
        "Application Level Confidentiality Profile" in text
    )
    assert "Not yet described" not in text


def test_a_compound_action_that_no_supported_iod_defines_resolves_elsewhere(
    statement_for,
):
    statement = statement_for("basic")
    text = conformance_markdown.render_markdown(statement)
    undefined = [
        e
        for e in statement.attributes
        if e.action in compound_actions.COMPOUND_ACTIONS and not e.places
    ]
    assert undefined
    for entry in undefined:
        row = next(line for line in text.splitlines() if f"| {entry.tag} |" in line)
        assert row.endswith(f"| {entry.elsewhere} elsewhere. |"), row


def test_places_name_their_enclosing_sequences(statement_for):
    text = conformance_markdown.render_markdown(statement_for("basic"))
    row = next(line for line in text.splitlines() if f"| {INSTITUTION_NAME} |" in line)
    assert (
        "Z within RT Assertions Sequence (0044,0110) > Asserter Identification "
        "Sequence (0044,0103) in RT Plan." in row
    )
    assert row.endswith(". X elsewhere. |")


def test_retained_safe_private_attributes_are_pending_where_selected(
    preset, statement_for
):
    composed = policy.compose_policy(preset)
    pending = statement_for(preset).pending
    assert (conformance.PENDING_SAFE_PRIVATE in pending) == (
        "retain_safe_private" in composed.options
    )


def test_synthetic_birth_dates_are_pending_only_for_tps_import(preset, statement_for):
    pending = statement_for(preset).pending
    assert (conformance.PENDING_BIRTH_DATES in pending) == (preset == "tps-import")


def test_cleaning_is_pending_only_for_a_policy_that_cleans(preset, statement_for):
    statement = statement_for(preset)
    composed = policy.compose_policy(preset)
    cleans = "C" in {
        *composed.actions.values(),
        *composed.supplementary_actions.values(),
    }
    assert cleans == (preset != "basic")
    assert (conformance.PENDING_CLEANING in statement.pending) == cleans
    assert set(conformance.PENDING) <= set(statement.pending)


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_no_enabled_preset_has_an_incomplete_statement():
    # Enabling a preset needs a complete statement for it.
    for name in policy.ENABLED_PRESETS:
        assert not _statement(name).pending, name


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_the_statement_is_the_same_every_time_it_is_generated(preset):
    first = conformance_markdown.render_markdown(_statement(preset))
    assert conformance_markdown.render_markdown(_statement(preset)) == first
    assert _statement(preset) == _statement(preset)


def test_every_table_in_the_markdown_has_a_cell_for_each_column(preset, statement_for):
    text = conformance_markdown.render_markdown(statement_for(preset))
    blocks = re.findall(r"(?:^\|.*\|\n)+", text + "\n", flags=re.MULTILINE)
    assert len(blocks) >= 4
    for block in blocks:
        rows = block.splitlines()
        assert re.fullmatch(r"\|(?: --- \|)+", rows[1]), rows[1]
        widths = {len(UNESCAPED_PIPE.findall(row)) for row in rows}
        assert len(widths) == 1, rows[0]
    assert "\n\n\n" not in text
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert not any(line != line.rstrip() for line in text.splitlines())


def test_the_markdown_acknowledges_every_part_of_the_standard_it_quotes(statement_for):
    text = conformance_markdown.render_markdown(statement_for("basic"))
    for part in ("PS3.3", "PS3.4", "PS3.6", "PS3.15", "PS3.16"):
        assert f"DICOM {part} 2026d, © NEMA" in text


def _section(text, heading):
    """Return the lines of one second-level section of a rendered statement."""
    lines = text.splitlines()
    start = lines.index(f"## {heading}") + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _satisfied(composed):
    unmet = {option for r in composed.resolved for option in r.unmet}
    return tuple(
        o for o in composed.options if o != "clean_descriptors" and o not in unmet
    )


def test_the_markers_are_no_longer_pending(preset, statement_for):
    assert not any("markers" in item for item in statement_for(preset).pending)


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_markers_match_those_the_engine_writes(preset, statement_for):
    composed = policy.compose_policy(preset)
    statement = statement_for(preset)
    written = markers.markers_for(
        composed, statement.method_digest, satisfied=_satisfied(composed)
    )
    assert statement.markers.method == written.method[1]
    assert statement.markers.codes == tuple(c.code_value for c in written.method_codes)
    assert statement.markers.temporal == written.temporal_information_modified
    assert statement.markers.review_codes == (
        (conformance.OPTION_CODES["clean_descriptors"],)
        if composed.claims_conformance and "clean_descriptors" in composed.options
        else ()
    )


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_every_attribute_the_markers_write_is_described(preset, statement_for):
    composed = policy.compose_policy(preset)
    statement = statement_for(preset)
    written = markers.apply_markers(
        pydicom.Dataset(),
        markers.markers_for(
            composed, statement.method_digest, satisfied=_satisfied(composed)
        ),
    )
    section = _section(
        conformance_markdown.render_markdown(statement), "Attributes inserted"
    )
    for element in written:
        assert (
            f"{element.name} ({element.tag.group:04X},{element.tag.element:04X})"
            in (section)
        ), element.name
    assert f"`{statement.markers.method}`" in section
    assert f"`{statement.method_digest}`" not in section  # named, not repeated
    assert f"`{markers.MANUFACTURER}`" in section
    assert f"DCM {markers.DEIDENTIFYING_EQUIPMENT}" in section
    assert f"`{statement.markers.temporal}`" in section


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_the_inserted_codes_are_listed_with_their_meanings(preset, statement_for):
    statement = statement_for(preset)
    section = _section(
        conformance_markdown.render_markdown(statement), "Attributes inserted"
    )
    meanings = {
        c.code_value: c.code_meaning for c in codes.load_context_group(7050).rows
    }
    for code in statement.markers.codes + statement.markers.review_codes:
        assert f"{meanings[code]} (DCM {code})" in section
    if not statement.markers.codes:
        assert "no item" in section


@pytest.mark.deid_requirement("MIDI-BP-18")
def test_the_runtime_versions_are_described_not_quoted(statement_for):
    text = conformance_markdown.render_markdown(statement_for("basic"))
    assert f"pydicom {pydicom.__version__}" not in text
    assert f"tomlkit {tomlkit.__version__}" not in text
    assert f"{platform.python_implementation()} {platform.python_version()}" not in text
    # No example quotes a version, which could match the runtime's.
    assert not re.search(r"(CPython|PyPy|pydicom|tomlkit) \d", text)
    assert "`CPython <version>`" in text


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_private_attribute_removal_is_described(preset, statement_for):
    statement = statement_for(preset)
    section = _section(conformance_markdown.render_markdown(statement), "Actions")
    row = _entry(statement, standard.PRIVATE_ATTRIBUTES_TAG)
    described = "X on Private Attributes removes every element" in section
    assert described == (row.action == "X")
    if described:
        assert "every level of nesting" in section
        assert "private creator" in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
@pytest.mark.parametrize(
    ("name", "expected_codes", "review_codes", "temporal"),
    [
        ("basic", ("113100",), (), "REMOVED"),
        ("basic-clean-descriptors", ("113100",), ("113105",), "REMOVED"),
        ("tps-import", (), (), "MODIFIED"),
        ("public-release", ("113100", "113111", "113107"), ("113105",), "MODIFIED"),
    ],
)
def test_each_presets_inserted_codes_and_temporal_value(
    name, expected_codes, review_codes, temporal, statement_for
):
    statement = statement_for(name)
    assert statement.markers.codes == expected_codes
    assert statement.markers.review_codes == review_codes
    assert statement.markers.temporal == temporal
    section = _section(
        conformance_markdown.render_markdown(statement), "Attributes inserted"
    )
    shown = [f"(DCM {code})" for code in expected_codes + review_codes]
    positions = [section.index(code) for code in shown]
    assert positions == sorted(positions)


def test_the_markers_are_said_to_depend_on_the_satisfied_options(statement_for):
    section = _section(
        conformance_markdown.render_markdown(statement_for("basic-clean-descriptors")),
        "Attributes inserted",
    )
    assert "the options that the instance satisfies" in section
    assert "never on the instance's values" not in section


# A tag of each masked row of Table E.1-1 that the row covers.
CONCRETE = {
    "(50xx,xxxx)": "(5000,0010)",
    standard.PRIVATE_ATTRIBUTES_TAG: "(0009,0010)",
}
ENGINE_REMOVED = {
    "(0000,1001)": "U",  # Requested SOP Instance UID
    "(0004,1511)": "U",  # Referenced SOP Instance UID in File
}
MEDIA_STORAGE_SOP_INSTANCE_UID = "(0002,0003)"
# The sequences that Table E.1-1 gives C under Clean Descriptors, with their
# Basic Profile actions.
CLEANED_SEQUENCES = {
    "(0008,1084)": "X",  # Admitting Diagnoses Code Sequence
    "(0032,1067)": "X",  # Reason for Visit Code Sequence
    "(3010,0081)": "Z",  # Prescription Notes Sequence
}
SUPPORTED_BY_THE_ENGINE = [p for p in policy.PRESETS if p != "public-release"]


def _concrete(tag):
    return CONCRETE.get(tag, tag.replace("60xx", "6000"))


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
@pytest.mark.parametrize("name", SUPPORTED_BY_THE_ENGINE)
def test_every_listed_action_is_the_one_the_engine_applies(name):
    composed = policy.compose_policy(name)
    rules = element_rules.ElementRules(composed)
    statement = conformance.conformance_statement(composed, vocabulary=None)
    given = {**composed.actions, **composed.supplementary_actions}
    for entry in statement.attributes:
        rule = rules.rule(_concrete(entry.tag))
        assert entry.action == rule.action, entry.tag
        policy_action = given.get(entry.tag, "U")
        if policy_action == rule.action:
            assert (entry.policy_action, entry.superseded_by) == ("", ""), entry.tag
            continue
        assert entry.policy_action == policy_action, entry.tag
        if rule.source is element_rules.RuleSource.ENGINE:
            expected = (
                conformance.FILE_META_WRITTEN
                if entry.tag.startswith("(0002,")
                else conformance.ENGINE_REMOVAL
            )
        else:
            attribute = standard.dictionary_attribute(entry.tag)
            assert policy_action == "C" and "SQ" in attribute.vrs, entry.tag
            assert rule.source is element_rules.RuleSource.TABLE, entry.tag
            expected = conformance.SEQUENCE_NOT_CLEANED
        assert entry.superseded_by == expected, entry.tag


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_engines_own_removals_supersede_the_table():
    statement = _statement("basic")
    for tag, given in ENGINE_REMOVED.items():
        entry = _entry(statement, tag)
        assert (entry.action, entry.policy_action) == ("X", given)
        assert entry.superseded_by == conformance.ENGINE_REMOVAL
    text = conformance_markdown.render_markdown(statement)
    row = next(line for line in text.splitlines() if "| (0000,1001) |" in line)
    assert "| `X`, in place of `U` |" in row
    section = _section(text, "Actions")
    paragraph = next(
        line for line in section.splitlines() if line.startswith("The engine's own")
    )
    for tag in ENGINE_REMOVED:
        assert tag in paragraph
    assert MEDIA_STORAGE_SOP_INSTANCE_UID not in paragraph


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_file_meta_information_the_engine_writes_is_described():
    statement = _statement("basic")
    entry = _entry(statement, MEDIA_STORAGE_SOP_INSTANCE_UID)
    assert (entry.action, entry.policy_action) == ("X", "U")
    assert entry.superseded_by == conformance.FILE_META_WRITTEN
    section = _section(conformance_markdown.render_markdown(statement), "Actions")
    paragraph = next(
        line
        for line in section.splitlines()
        if line.startswith("The engine writes its own File Meta Information")
    )
    written = file_meta.file_meta_information(
        sop_class_uid=CT_FOR_PROCESSING,
        sop_instance_uid="2.25.1",
        transfer_syntax_uid=next(iter(scope.SUPPORTED_TRANSFER_SYNTAXES)),
    )
    names = {a.tag: a.name for a in standard.load_data_dictionary().attributes}
    for element in written:
        tag = f"({element.tag.group:04X},{element.tag.element:04X})"
        assert f"{names.get(tag, element.name)} {tag}" in paragraph, tag
    assert "holds only" in paragraph
    assert "replacement SOP Instance UID" in paragraph


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_a_sequence_that_the_policy_cleans_takes_its_basic_profile_action():
    statement = _statement("basic-clean-descriptors")
    for tag, basic in CLEANED_SEQUENCES.items():
        entry = _entry(statement, tag)
        assert (entry.action, entry.policy_action) == (basic, "C"), tag
        assert entry.superseded_by == conformance.SEQUENCE_NOT_CLEANED
    section = _section(conformance_markdown.render_markdown(statement), "Actions")
    paragraph = next(
        line for line in section.splitlines() if line.startswith("No rules for")
    )
    for tag in CLEANED_SEQUENCES:
        assert tag in paragraph
    basic = _section(
        conformance_markdown.render_markdown(_statement("basic")), "Actions"
    )
    assert "No rules for cleaning" not in basic


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_elements_that_no_row_covers_are_no_longer_pending(preset):
    statement = _statement(preset)
    assert not any("data dictionary does not list" in i for i in statement.pending)


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
@pytest.mark.parametrize("name", SUPPORTED_BY_THE_ENGINE)
def test_the_rules_for_other_elements_are_the_engines(name):
    other = _statement(name).other_elements
    assert other == conformance.OtherElements(
        engine_groups=tuple(sorted(_ENGINE_GROUPS)),
        engine_attributes=tuple(sorted(_ENGINE_TAGS)),
        text_vrs=tuple(sorted(element_rules.TEXT_VRS)),
        text_action=element_rules.UNCOVERED_TEXT_ACTION,
        kept_vrs=tuple(sorted(element_rules.KEPT_VRS)),
        iod_defined_vrs=tuple(sorted(element_rules.IOD_DEFINED_VRS)),
    )


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_rules_for_other_elements_are_described():
    statement = _statement("basic")
    other = statement.other_elements
    section = _section(
        conformance_markdown.render_markdown(statement), "Other elements"
    )
    for group in other.engine_groups:
        assert f"{group:04X}" in section
    assert "(gggg,0000)" in section
    assert "Data Set Trailing Padding (FFFC,FFFC)" in section
    assert "Encrypted Attributes Sequence (0400,0500)" in section
    for vrs, conjunction in (
        (other.text_vrs, "or"),
        (other.kept_vrs, "and"),
        (other.iod_defined_vrs, "and"),
    ):
        assert ", ".join(vrs[:-1]) + f", {conjunction} {vrs[-1]}" in section
    assert f"get `{other.text_action}`, resolved by Type" in section
    assert "items" in section
    assert "does not list" in section
    # Group 0002 is the File Meta Information, which the engine writes.
    assert "File Meta Information" in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_every_engine_group_has_its_reason():
    assert set(conformance_markdown.ENGINE_GROUP_REASONS) == set(_ENGINE_GROUPS)


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_a_policy_that_the_engine_refuses_lists_the_policys_actions():
    composed = policy.compose_policy("public-release")
    with pytest.raises(policy.PolicyError):
        element_rules.ElementRules(composed)
    statement = conformance.conformance_statement(composed, vocabulary=None)
    assert statement.other_elements is None
    assert conformance.PENDING_REFUSED in statement.pending
    table = [e for e in statement.attributes if e.rule == conformance.TABLE_E1_1]
    assert [(e.tag, e.action) for e in table] == list(composed.actions.items())
    assert not any(e.policy_action for e in statement.attributes)
    text = conformance_markdown.render_markdown(statement)
    assert "## Other elements" not in text
    assert conformance.PENDING_REFUSED in text
    for name in SUPPORTED_BY_THE_ENGINE:
        assert conformance.PENDING_REFUSED not in _statement(name).pending


def _described_action(other, attribute, defined):
    """Return the action that the Other elements section gives an attribute."""
    vrs = set(attribute.vrs)
    if vrs & set(other.text_vrs):
        return other.text_action
    if vrs and vrs <= set(other.kept_vrs):
        return "K"
    if vrs and vrs <= set(other.kept_vrs) | set(other.iod_defined_vrs):
        return "K" if defined else "X"
    return "X"


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_every_attribute_that_no_row_covers_takes_the_action_described():
    composed = policy.compose_policy("basic")
    rules = element_rules.ElementRules(composed)
    other = _statement("basic").other_elements
    ct = iods.load_iod_tables().iods["CT Image"]
    covered = 0
    for attribute in standard.load_data_dictionary().attributes:
        tag = attribute.tag.replace("xx", "00")
        if not re.fullmatch(r"\([0-9A-F]{4},[0-9A-F]{4}\)", tag):
            continue
        rule = rules.rule(tag)
        if rule.source not in (
            element_rules.RuleSource.UNCOVERED_TEXT,
            element_rules.RuleSource.DEFAULT,
        ):
            continue
        covered += 1
        assert rule.action == _described_action(other, attribute, False), tag
        defined = bool(ct.lookup(tag, ()))
        assert rules.rule(tag, iod=ct).action == _described_action(
            other, attribute, defined
        ), tag
    assert covered > 1000


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
@pytest.mark.parametrize(
    ("tag", "action"),
    [
        ("(0001,0010)", "X"),  # an odd group that is not private, not listed
        ("(6020,3000)", "X"),  # outside the repeating groups, not listed
        ("(1234,5678)", "X"),  # not in the data dictionary
        ("(0009,0010)", "X"),  # a private creator, under the Basic Profile
    ],
)
def test_elements_outside_the_dictionary_and_rows_are_removed(tag, action):
    rules = element_rules.ElementRules(policy.compose_policy("basic"))
    assert rules.rule(tag).action == action
    section = _section(
        conformance_markdown.render_markdown(_statement("basic")), "Other elements"
    )
    assert "an element that the pinned data dictionary does not list" in section
    assert "0001, 0003, 0005, 0007, and FFFF" in section
    assert "6000 to 601E" in section


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_cleaning_is_pending_only_where_the_engine_cleans():
    # A policy whose only C is on sequences cleans nothing, since a sequence
    # to which the policy gives C takes its Basic Profile action.
    composed = policy.compose_policy("basic-clean-descriptors")
    basic = {
        row.tag: row.basic_profile for row in standard.load_table_e1_1().attributes
    }
    sequences = {
        tag
        for tag, action in composed.actions.items()
        if action == "C"
        and (a := standard.dictionary_attribute(tag)) is not None
        and "SQ" in a.vrs
    }
    assert sequences
    only_sequences = dataclasses.replace(
        composed,
        actions={
            tag: action if action != "C" or tag in sequences else basic[tag]
            for tag, action in composed.actions.items()
        },
        supplementary_actions={
            tag: action
            for tag, action in composed.supplementary_actions.items()
            if action != "C"
        },
    )
    statement = conformance.conformance_statement(only_sequences, vocabulary=None)
    assert "C" in only_sequences.actions.values()
    assert not any(e.action == "C" for e in statement.attributes)
    assert conformance.PENDING_CLEANING not in statement.pending
