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
    dummy_values,
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
)
from pymedphys.tests.dicom.test_deidentify_method_digest import VOCABULARY

INSTITUTION_NAME = "(0008,0080)"  # X/Z/D in the Basic Profile
ROI_CREATOR = ("(3006,0020)", "(3006,004D)")
REFERRING_PHYSICIAN_IDENTIFICATION = ("(0008,0096)",)
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


def test_the_statement_names_the_edition_preset_and_options(preset, statement_for):
    composed = policy.compose_policy(preset)
    statement = statement_for(preset)
    assert statement.edition == composed.edition == "2026d"
    assert statement.preset == preset
    assert statement.options == composed.options

    text = conformance.render_markdown(statement)
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
    assert meanings[conformance.PROFILE_CODE] == (
        "Basic Application Confidentiality Profile"
    )
    for option, code in conformance.OPTION_CODES.items():
        words = meanings[code].lower().split()
        # Each option's own words appear in its code's meaning, in order.
        assert words[-1] == "option"
        for word in option.split("_"):
            assert word in words, (option, meanings[code])


def test_options_outside_the_supported_scope_are_listed_as_not_supported(statement_for):
    text = conformance.render_markdown(statement_for("basic"))
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
    text = conformance.render_markdown(statement_for(preset))
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
    assert [(e.tag, e.action) for e in table] == list(composed.actions.items())
    assert [e.name for e in table] == [
        row.name for row in standard.load_table_e1_1().attributes
    ]
    assert {e.tag: e.action for e in supplementary} == dict(
        composed.supplementary_actions
    )
    names = {a.tag: a.name for a in standard.load_data_dictionary().attributes}
    assert all(e.name == names[e.tag] for e in supplementary)


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


def test_compound_actions_are_resolved_at_every_place_a_supported_iod_defines_them(
    preset,
    statement_for,
):
    statement = statement_for(preset)
    tables = iods.load_iod_tables()
    for entry in statement.attributes:
        if entry.action not in compound_actions.COMPOUND_ACTIONS:
            assert entry.places == ()
            assert entry.elsewhere == ""
            continue
        assert entry.elsewhere == compound_actions.resolve(entry.action, "3")
        expected = []
        for name in sorted(scope.SUPPORTED_IODS):
            iod = tables.iods[name]
            paths = dict.fromkeys(d.path for d in iod.definitions if d.tag == entry.tag)
            for path in paths:
                action = compound_actions.resolve_in_iod(
                    iod, entry.tag.replace("60xx", "6000"), path, entry.action
                )
                expected.append(conformance.Place(name, path, action))
        assert entry.places == tuple(expected), entry.tag


def test_institution_name_in_a_structure_set_is_resolved_by_its_type_at_each_place(
    statement_for,
):
    places = _entry(statement_for("basic"), INSTITUTION_NAME).places
    structure_set = {p.path: p.action for p in places if p.iod == "RT Structure Set"}
    assert structure_set[ROI_CREATOR] == "Z"
    assert structure_set[REFERRING_PHYSICIAN_IDENTIFICATION] == "D"

    text = conformance.render_markdown(statement_for("basic"))
    row = next(line for line in text.splitlines() if f"| {INSTITUTION_NAME} |" in line)
    zeroed = row.split(". Z within ")[1]
    assert (
        "Structure Set ROI Sequence (3006,0020) > ROI Creator Sequence (3006,004D) "
        "in RT Structure Set" in zeroed
    )
    assert "D within Referring Physician Identification Sequence (0008,0096);" in row
    assert row.endswith("X elsewhere |")


def test_x_z_on_a_type_1_attribute_is_described_as_the_dummy_value(statement_for):
    text = conformance.render_markdown(statement_for("basic"))
    assert (
        "X/Z on a Type 1 or 1C attribute gives D, the dummy value that Z may write."
        in (" ".join(text.split()))
    )


def test_a_place_that_sequesters_the_instance_is_listed_as_such(monkeypatch):
    resolve_in_iod = compound_actions.resolve_in_iod

    def sequestering(iod, tag, path, action):
        if tag == INSTITUTION_NAME and tuple(path) == ROI_CREATOR:
            return conformance.SEQUESTER
        return resolve_in_iod(iod, tag, path, action)

    monkeypatch.setattr(compound_actions, "resolve_in_iod", sequestering)
    statement = _statement("basic")
    places = _entry(statement, INSTITUTION_NAME).places
    assert conformance.Place(
        "RT Structure Set", ROI_CREATOR, conformance.SEQUESTER
    ) in (places)
    text = conformance.render_markdown(statement)
    row = next(line for line in text.splitlines() if f"| {INSTITUTION_NAME} |" in line)
    assert (
        "instance sequestered within Structure Set ROI Sequence (3006,0020) > "
        "ROI Creator Sequence (3006,004D) in RT Structure Set" in row
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

    text = conformance.render_markdown(statement)
    for sop_class in statement.sop_classes:
        assert f"| {sop_class.uid} | {sop_class.name} | {sop_class.iod} |" in text
    for syntax in statement.transfer_syntaxes:
        assert f"| {syntax.uid} | {syntax.name} |" in text


def test_the_dummy_values_are_those_that_d_writes(statement_for):
    text = conformance.render_markdown(statement_for("basic"))
    for vr, (first, second) in dummy_values.CONSTANTS.items():
        assert f"| {vr} | `{first}` | `{second}` |" in text
    assert f"`{pseudonyms.PATIENT_ID_PREFIX}`" in text
    assert f"`{pseudonyms.FAMILY_NAME}^`" in text
    assert uids.UID_ROOT in text
    assert str(uids.UID_NAMESPACE) in text
    assert "PyMedPhys" not in "".join(map(str, dummy_values.CONSTANTS.values()))


def test_the_key_and_the_scope_of_referential_integrity_are_described(statement_for):
    text = conformance.render_markdown(statement_for("basic"))
    assert "256-bit" in text
    assert "HMAC-SHA256" in text
    assert "discarded after the run" in text


def test_no_attribute_is_encrypted_for_later_reidentification(statement_for):
    text = conformance.render_markdown(statement_for("basic"))
    assert "Encrypted Attributes Sequence (0400,0500)" in text
    assert "No attribute is placed in an Encrypted Attributes Data Set" in text


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
    text = conformance.render_markdown(statement)
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
    text = conformance.render_markdown(statement)
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
    text = conformance.render_markdown(statement)
    assert "is not enabled" in text
    assert "de-identified in accordance with" not in text


def test_a_statement_with_sections_still_to_describe_makes_no_claim(monkeypatch):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    statement = _statement("basic")
    assert statement.enabled
    assert statement.pending
    assert not statement.claims_conformance
    text = conformance.render_markdown(statement)
    assert "Not yet described" in text
    for item in statement.pending:
        assert item in text
    assert "de-identified in accordance with" not in text


def test_a_complete_statement_of_an_enabled_preset_claims_conformance(monkeypatch):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    monkeypatch.setattr(conformance, "PENDING", ())
    statement = _statement("basic")
    assert not statement.pending
    assert statement.claims_conformance
    text = conformance.render_markdown(statement)
    assert (
        "de-identified in accordance with the DICOM PS3.15 2026d Basic "
        "Application Level Confidentiality Profile" in text
    )
    assert "Not yet described" not in text


def test_a_compound_action_that_no_supported_iod_defines_resolves_elsewhere(
    statement_for,
):
    statement = statement_for("basic")
    text = conformance.render_markdown(statement)
    undefined = [
        e
        for e in statement.attributes
        if e.action in compound_actions.COMPOUND_ACTIONS and not e.places
    ]
    assert undefined
    for entry in undefined:
        row = next(line for line in text.splitlines() if f"| {entry.tag} |" in line)
        assert row.endswith(f"| {entry.elsewhere} elsewhere |"), row


def test_places_name_their_enclosing_sequences(statement_for):
    text = conformance.render_markdown(statement_for("basic"))
    row = next(line for line in text.splitlines() if "| (0010,0020) |" in line)
    assert "D within Other Patient IDs Sequence (0010,1002);" in row
    assert row.endswith(". Z elsewhere |")


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
    assert (conformance.PENDING_CLEANING in statement.pending) == cleans
    assert set(conformance.PENDING) <= set(statement.pending)


def test_no_enabled_preset_has_an_incomplete_statement():
    # Enabling a preset needs a complete statement for it.
    for name in policy.ENABLED_PRESETS:
        assert not _statement(name).pending, name


def test_the_statement_is_the_same_every_time_it_is_generated(preset):
    first = conformance.render_markdown(_statement(preset))
    assert conformance.render_markdown(_statement(preset)) == first
    assert _statement(preset) == _statement(preset)


def test_every_table_in_the_markdown_has_a_cell_for_each_column(preset, statement_for):
    text = conformance.render_markdown(statement_for(preset))
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
    text = conformance.render_markdown(statement_for("basic"))
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


def test_every_attribute_the_markers_write_is_described(preset, statement_for):
    composed = policy.compose_policy(preset)
    statement = statement_for(preset)
    written = markers.apply_markers(
        pydicom.Dataset(),
        markers.markers_for(
            composed, statement.method_digest, satisfied=_satisfied(composed)
        ),
    )
    section = _section(conformance.render_markdown(statement), "Attributes inserted")
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


def test_the_inserted_codes_are_listed_with_their_meanings(preset, statement_for):
    statement = statement_for(preset)
    section = _section(conformance.render_markdown(statement), "Attributes inserted")
    meanings = {
        c.code_value: c.code_meaning for c in codes.load_context_group(7050).rows
    }
    for code in statement.markers.codes + statement.markers.review_codes:
        assert f"{meanings[code]} (DCM {code})" in section
    if not statement.markers.codes:
        assert "no item" in section


def test_the_runtime_versions_are_described_not_quoted(statement_for):
    text = conformance.render_markdown(statement_for("basic"))
    assert f"pydicom {pydicom.__version__}" not in text
    assert f"tomlkit {tomlkit.__version__}" not in text
    assert f"{platform.python_implementation()} {platform.python_version()}" not in text
    # No example quotes a version, which could match the runtime's.
    assert not re.search(r"(CPython|PyPy|pydicom|tomlkit) \d", text)
    assert "`CPython <version>`" in text


def test_private_attribute_removal_is_described(preset, statement_for):
    statement = statement_for(preset)
    section = _section(conformance.render_markdown(statement), "Actions")
    row = _entry(statement, standard.PRIVATE_ATTRIBUTES_TAG)
    described = "X on Private Attributes removes every element" in section
    assert described == (row.action == "X")
    if described:
        assert "every level of nesting" in section
        assert "private creator" in section


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
    section = _section(conformance.render_markdown(statement), "Attributes inserted")
    shown = [f"(DCM {code})" for code in expected_codes + review_codes]
    positions = [section.index(code) for code in shown]
    assert positions == sorted(positions)


def test_the_markers_are_said_to_depend_on_the_satisfied_options(statement_for):
    section = _section(
        conformance.render_markdown(statement_for("basic-clean-descriptors")),
        "Attributes inserted",
    )
    assert "the options that the instance satisfies" in section
    assert "never on the instance's values" not in section
