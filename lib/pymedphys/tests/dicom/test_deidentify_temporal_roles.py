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

"""The role of every date, time, and datetime attribute."""

import collections
import re

from pymedphys._imports import pytest, tomlkit

from pymedphys._dicom.deidentify import attribute_roles, standard, temporal_roles

Role = temporal_roles.TemporalRole

# Table E.1-1 gives these K under Retain Device Identity and C under Retain
# Longitudinal Temporal Information with Modified Dates, so no output can
# satisfy both options while one of them has a value.
CONFLICTING = {
    "(0014,407C)": Role.DEVICE,  # Calibration Time
    "(0014,407E)": Role.DEVICE,  # Calibration Date
    "(0018,1200)": Role.DEVICE,  # Date of Last Calibration
    "(0018,1201)": Role.DEVICE,  # Time of Last Calibration
    "(0018,1202)": Role.DEVICE,  # DateTime of Last Calibration
    "(0018,1203)": Role.DEVICE,  # Calibration DateTime
    "(0018,1204)": Role.DEVICE,  # Date of Manufacture
    "(0018,1205)": Role.DEVICE,  # Date of Installation
    "(0018,700C)": Role.DEVICE,  # Date of Last Detector Calibration
    "(0018,700E)": Role.DEVICE,  # Time of Last Detector Calibration
    "(300C,0127)": Role.SUBJECT_EVENT,  # Beam Hold Transition DateTime
}


def _temporal_attributes():
    return {
        attribute.tag: attribute
        for attribute in standard.load_data_dictionary().attributes
        if attribute.vr in {"DA", "DT", "TM"}
    }


def _table_e1_1():
    return {row.tag: row for row in standard.load_table_e1_1().attributes}


def test_every_temporal_attribute_in_the_dictionary_has_exactly_one_role():
    roles = temporal_roles.load_temporal_roles()

    assert set(roles.rules) == set(_temporal_attributes())
    assert collections.Counter(rule.role for rule in roles.rules.values()) == {
        Role.SUBJECT_EVENT: 151,
        Role.RADIATION_SOURCE: 2,
        Role.DEVICE: 12,
        Role.VOCABULARY_VERSION: 4,
        Role.OTHER: 15,
    }


def test_the_roles_follow_the_dictionarys_edition():
    roles = temporal_roles.load_temporal_roles()

    assert roles.edition == standard.load_data_dictionary().edition
    assert roles.acknowledgement == f"DICOM PS3.6 {roles.edition}, © NEMA"


def test_the_conflicting_options_affect_only_the_listed_attributes():
    # A new edition that adds a conflict fails here once its tables are
    # regenerated, so the new attribute's handling is reviewed.
    conflicting = {
        tag
        for tag, row in _table_e1_1().items()
        if row.options.get("retain_device_identity") == "K"
        and row.options.get("retain_longitudinal_modified_dates") == "C"
    }
    roles = temporal_roles.load_temporal_roles()

    assert conflicting == set(CONFLICTING)
    assert {tag: roles.role(tag) for tag in conflicting} == CONFLICTING


def test_every_attribute_modified_dates_cleans_has_a_role_or_is_known():
    # Table E.1-1 gives C under Modified Dates to 166 temporal attributes and
    # to three of other VRs, which need rules of their own. A new edition that
    # cleans another attribute of another VR fails here.
    cleaned = {
        tag
        for tag, row in _table_e1_1().items()
        if row.options.get("retain_longitudinal_modified_dates") == "C"
    }
    roles = temporal_roles.load_temporal_roles()

    assert len(cleaned & set(roles.rules)) == 166
    assert cleaned - set(roles.rules) == {
        "(0008,0201)",  # Timezone Offset From UTC, SH
        "(0034,0007)",  # Frame Origin Timestamp, OB
        "(0400,0310)",  # Certified Timestamp, OB
    }


def test_a_role_that_is_not_obvious_has_a_note():
    # Other than a subject event that Modified Dates cleans, every rule says
    # why the attribute has its role.
    table = _table_e1_1()
    for tag, rule in temporal_roles.load_temporal_roles().rules.items():
        row = table.get(tag)
        cleaned = (
            row is not None
            and row.options.get("retain_longitudinal_modified_dates") == "C"
        )
        if rule.role is not Role.SUBJECT_EVENT or not cleaned:
            assert rule.note, tag


@pytest.mark.parametrize(
    "keyword, role",
    [
        ("StudyDate", Role.SUBJECT_EVENT),
        ("AcquisitionDateTime", Role.SUBJECT_EVENT),
        ("TreatmentDate", Role.SUBJECT_EVENT),
        ("RTPlanDate", Role.SUBJECT_EVENT),
        ("RadiopharmaceuticalStartDateTime", Role.SUBJECT_EVENT),
        ("DecayCorrectionDateTime", Role.SUBJECT_EVENT),
        # Must be at or after Content Date, so it moves with the subject.
        ("ItemInventoryDateTime", Role.SUBJECT_EVENT),
        ("SourceStrengthReferenceDate", Role.RADIATION_SOURCE),
        ("SourceStrengthReferenceTime", Role.RADIATION_SOURCE),
        ("DateOfGainCalibration", Role.DEVICE),
        ("ContextGroupVersion", Role.VOCABULARY_VERSION),
        ("ContextGroupLocalVersion", Role.VOCABULARY_VERSION),
        ("TemplateVersion", Role.VOCABULARY_VERSION),
        # Published or organisational, not events in the subject's record.
        ("EthicsCommitteeApprovalEffectivenessStartDate", Role.OTHER),
        ("ProductExpirationDateTime", Role.OTHER),
        ("EffectiveDateTime", Role.OTHER),
        ("HangingProtocolCreationDateTime", Role.OTHER),
        ("SelectorDAValue", Role.OTHER),
    ],
)
def test_attribute_roles(keyword, role):
    tag = next(tag for tag, a in _temporal_attributes().items() if a.keyword == keyword)

    assert temporal_roles.load_temporal_roles().role(tag) is role


@pytest.mark.parametrize(
    "role, shifted",
    [
        (Role.SUBJECT_EVENT, True),
        (Role.RADIATION_SOURCE, True),
        (Role.DEVICE, False),
        (Role.VOCABULARY_VERSION, False),
        (Role.OTHER, False),
    ],
)
def test_only_subject_event_and_radiation_source_dates_are_shifted(role, shifted):
    assert role.shifted is shifted


def test_an_attribute_without_a_role_is_rejected():
    with pytest.raises(attribute_roles.RoleError, match="no role"):
        temporal_roles.load_temporal_roles().role("(0010,0010)")


def _document():
    return tomlkit.parse(
        temporal_roles.TEMPORAL_ROLES_PATH.read_text(encoding="utf-8")
    ).unwrap()


def _write(path, document):
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "change, message",
    [
        (
            lambda d: d.update(schema="pymedphys-deid-uid-roles/1"),
            "is not a pymedphys-deid-temporal-roles/1 file",
        ),
        (
            lambda d: d["attribute"][0].update(role="shifted"),
            "rule 1 has a role that is not subject-event, radiation-source, "
            "device, vocabulary-version, or other",
        ),
        (
            lambda d: d["attribute"][0].update(
                tag="(0008,0018)", keyword="SOPInstanceUID"
            ),
            "rule 1 is not a DA, DT, or TM attribute",
        ),
        (lambda d: d["attribute"].pop(), "has no role for"),
    ],
)
def test_a_malformed_roles_file_is_rejected(tmp_path, change, message):
    document = _document()
    change(document)

    with pytest.raises(attribute_roles.RoleError, match=re.escape(message)):
        temporal_roles.load_temporal_roles(
            _write(tmp_path / "temporal_roles.toml", document)
        )
