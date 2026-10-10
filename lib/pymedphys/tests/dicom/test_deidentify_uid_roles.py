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

"""The role of every UI attribute, and how a UID value is transformed."""

import collections
import re

from pymedphys._imports import hypothesis, pytest, tomlkit

from pymedphys._dicom.deidentify import (
    attribute_roles,
    codes,
    keys,
    standard,
    uid_registry,
    uid_roles,
    uids,
)

st = hypothesis.strategies

FIXTURE_KEY = keys.DeidKey(bytes(range(32)))
any_key = st.binary(min_size=32, max_size=32).map(keys.DeidKey)


def _ui_attributes():
    return {
        attribute.tag: attribute
        for attribute in standard.load_data_dictionary().attributes
        if attribute.vr == "UI"
    }


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
def test_every_ui_attribute_in_the_dictionary_has_exactly_one_role():
    roles = uid_roles.load_uid_roles()

    assert set(roles.rules) == set(_ui_attributes())
    assert collections.Counter(rule.role for rule in roles.rules.values()) == {
        uid_roles.UIDRole.INSTANCE: 75,
        uid_roles.UIDRole.DEFINITION: 17,
    }


def test_the_roles_follow_the_dictionarys_edition():
    roles = uid_roles.load_uid_roles()

    assert roles.edition == standard.load_data_dictionary().edition
    assert roles.acknowledgement == f"DICOM PS3.6 {roles.edition}, © NEMA"


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
def test_every_uid_table_e1_1_replaces_is_an_instance_uid():
    # The supplementary rules only strengthen Table E.1-1.
    ui = _ui_attributes()
    roles = uid_roles.load_uid_roles()
    replaced = {
        row.tag
        for row in standard.load_table_e1_1().attributes
        if row.tag in ui and row.basic_profile in ("U", "D")
    }

    assert len(replaced) == 53
    assert {
        tag for tag in replaced if roles.role(tag) != uid_roles.UIDRole.INSTANCE
    } == set()


@pytest.mark.parametrize(
    "keyword, role",
    [
        ("SOPClassUID", "definition"),
        ("ReferencedSOPClassUID", "definition"),
        ("CodingSchemeUID", "definition"),
        ("ContextUID", "definition"),
        ("MappingResourceUID", "definition"),
        ("StoredInstanceTransferSyntaxUID", "definition"),
        ("SegmentationTemplateUID", "definition"),
        ("SOPInstanceUID", "instance"),
        ("FrameOfReferenceUID", "instance"),
        ("ReferencedDoseReferenceUID", "instance"),
        # Instance UIDs that Table E.1-1 does not list.
        ("TargetFrameOfReferenceUID", "instance"),
        ("MultiFrameSourceSOPInstanceUID", "instance"),
        ("EquipmentFrameOfReferenceUID", "instance"),
        # Organisation identifiers.
        ("ContextGroupExtensionCreatorUID", "instance"),
        ("RepositoryUniqueID", "instance"),
    ],
)
def test_attribute_roles(keyword, role):
    tag = next(tag for tag, a in _ui_attributes().items() if a.keyword == keyword)

    assert uid_roles.load_uid_roles().role(tag) == uid_roles.UIDRole(role)


def test_an_attribute_without_a_role_is_rejected():
    with pytest.raises(attribute_roles.RoleError, match="no role"):
        uid_roles.load_uid_roles().role("(0010,0010)")


def _document():
    return tomlkit.parse(uid_roles.UID_ROLES_PATH.read_text(encoding="utf-8")).unwrap()


def _write(path, document):
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda d: d.update(schema="pymedphys-deid-uid-roles/0"), "schema"),
        (lambda d: d.update(edition="2099a"), "edition"),
        (lambda d: d.update(acknowledgement="NEMA"), "acknowledgement"),
        (lambda d: d["attribute"][0].update(role="retain"), "rule 1 has a role"),
        (lambda d: d["attribute"][0].update(extra=1), "rule 1 does not have"),
        (lambda d: d["attribute"][0].pop("keyword"), "rule 1 does not have"),
        (lambda d: d["attribute"][0].update(keyword="SOPClassUID"), "rule 1 names"),
        (lambda d: d["attribute"][0].update(tag="(0010,0010)"), "rule 1 is not a UI"),
        (lambda d: d["attribute"][0].update(tag=[]), "rule 1 is not a UI"),
        (lambda d: d["attribute"][0].update(tag={}), "rule 1 is not a UI"),
        (lambda d: d["attribute"][0].update(role=[]), "rule 1 has a role"),
        (lambda d: d["attribute"][0].update(role={}), "rule 1 has a role"),
        (lambda d: d["attribute"][0].update(note=""), "rule 1 has a note"),
        (lambda d: d["attribute"].append(dict(d["attribute"][0])), "repeats"),
        (lambda d: d["attribute"].pop(), "has no role for"),
        (lambda d: d.update(attribute=1), "rules are not an array of tables"),
        (lambda d: d.update(attribute={}), "rules are not an array of tables"),
    ],
)
def test_a_malformed_roles_file_is_rejected(tmp_path, change, message):
    document = _document()
    change(document)

    with pytest.raises(attribute_roles.RoleError, match=re.escape(message)):
        uid_roles.load_uid_roles(_write(tmp_path / "uid_roles.toml", document))


def test_the_well_known_uids_are_those_the_pinned_tables_register():
    expected = (
        {row.uid for row in uid_registry.load_uid_values().rows}
        | {row.uid for row in uid_registry.load_frames_of_reference().rows}
        | {row.uid for row in uid_registry.load_context_group_uids().rows}
        | {row.uid for row in uid_registry.load_template_uids().rows}
        | {row.uid for row in codes.load_coding_schemes().rows if row.uid}
        | {row.uid for row in codes.load_hl7v3_coding_schemes().rows}
    )

    assert uids.well_known_uids() == expected
    assert "" not in expected


@pytest.mark.parametrize(
    "value",
    [
        "1.2.840.10008.5.1.4.1.1.2",  # CT Image Storage
        "1.2.840.10008.1.2.1",  # Explicit VR Little Endian
        "1.2.840.10008.15.1.1",  # Universal Coordinated Time
        "1.2.840.10008.1.4.1.1",  # Talairach Brain Atlas Frame of Reference
        "1.2.840.10008.6.1.1",  # CID 2
        "2.16.840.1.113883.6.96",  # SNOMED CT
        "2.16.840.1.113883.5.4",  # HL7v3 ActCode
    ],
)
@pytest.mark.parametrize("role", list(uid_roles.UIDRole))
def test_a_registered_uid_is_retained_whatever_the_role(role, value):
    assert uids.transform_uid(FIXTURE_KEY, role, value + "\x00") == (
        value,
        uids.UIDOutcome.RETAINED,
    )


@hypothesis.given(any_key, st.sampled_from(sorted(uids.well_known_uids())))
def test_registered_uids_are_retained_under_any_key(key, value):
    assert uids.transform_uid(key, uid_roles.UIDRole.INSTANCE, value)[0] == value


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
def test_an_instance_uid_is_replaced():
    value = "1.2.840.99999.1.2.3"

    assert uids.transform_uid(FIXTURE_KEY, uid_roles.UIDRole.INSTANCE, value) == (
        uids.replacement_uid(FIXTURE_KEY, value),
        uids.UIDOutcome.REPLACED,
    )


def test_an_unregistered_definition_uid_is_replaced_and_reported():
    # For example a local coding scheme under an institution's root, which
    # could identify the institution.
    value = "1.2.840.99999.4.5.6 "

    assert uids.transform_uid(FIXTURE_KEY, uid_roles.UIDRole.DEFINITION, value) == (
        uids.replacement_uid(FIXTURE_KEY, value),
        uids.UIDOutcome.REPLACED_UNREGISTERED_DEFINITION,
    )
