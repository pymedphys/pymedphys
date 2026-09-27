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
Action = temporal_roles.TemporalAction

# Attributes of other VRs that Table E.1-1 cleans under Modified Dates.
OTHER_VRS = {
    "(0008,0201)": Role.TIME_ZONE,  # Timezone Offset From UTC, SH
    "(0034,0007)": Role.SUBJECT_EVENT,  # Frame Origin Timestamp, OB
    "(0400,0310)": Role.OTHER,  # Certified Timestamp, OB
}

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


def _tag(keyword):
    return next(
        attribute.tag
        for attribute in standard.load_data_dictionary().attributes
        if attribute.keyword == keyword
    )


def _table_e1_1():
    return {row.tag: row for row in standard.load_table_e1_1().attributes}


def test_every_temporal_attribute_in_the_dictionary_has_exactly_one_role():
    roles = temporal_roles.load_temporal_roles()

    assert set(roles.rules) == set(_temporal_attributes()) | set(OTHER_VRS)
    assert collections.Counter(rule.role for rule in roles.rules.values()) == {
        Role.SUBJECT_EVENT: 152,
        Role.RADIATION_SOURCE: 2,
        Role.DEVICE: 12,
        Role.VOCABULARY_VERSION: 4,
        Role.TIME_ZONE: 1,
        Role.OTHER: 16,
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


def test_every_attribute_modified_dates_cleans_has_a_role():
    # Table E.1-1 gives C under Modified Dates to 166 temporal attributes and
    # to three of other VRs. A new edition that cleans another attribute of
    # any VR has no rule until one is reviewed, so the file fails to load.
    cleaned = {
        tag
        for tag, row in _table_e1_1().items()
        if row.options.get("retain_longitudinal_modified_dates") == "C"
    }
    roles = temporal_roles.load_temporal_roles()

    assert len(cleaned) == 169
    assert cleaned <= set(roles.rules)
    assert cleaned - set(_temporal_attributes()) == set(OTHER_VRS)
    assert {tag: roles.role(tag) for tag in OTHER_VRS} == OTHER_VRS


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
        # Attributes of other VRs that Modified Dates cleans.
        ("TimezoneOffsetFromUTC", Role.TIME_ZONE),
        ("FrameOriginTimestamp", Role.SUBJECT_EVENT),
        ("CertifiedTimestamp", Role.OTHER),
    ],
)
def test_attribute_roles(keyword, role):
    assert temporal_roles.load_temporal_roles().role(_tag(keyword)) is role


@pytest.mark.parametrize(
    "role, action",
    [
        (Role.SUBJECT_EVENT, Action.SHIFT),
        (Role.RADIATION_SOURCE, Action.SHIFT),
        (Role.DEVICE, Action.DUMMY),
        (Role.VOCABULARY_VERSION, Action.DUMMY),
        (Role.TIME_ZONE, Action.REMOVE),
        (Role.OTHER, Action.DUMMY),
    ],
)
def test_modified_dates_shifts_subject_events_and_removes_time_zones(role, action):
    assert role.action is action


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
            "device, vocabulary-version, time-zone, or other",
        ),
        (
            lambda d: d["attribute"][0].update(
                tag="(0008,0018)", keyword="SOPInstanceUID"
            ),
            "rule 1 is not a DA, DT, or TM attribute",
        ),
        (lambda d: d["attribute"].pop(), "has no role for"),
        (
            lambda d: d.update(
                attribute=[a for a in d["attribute"] if a["tag"] != "(0008,0201)"]
            ),
            "has no role for (0008,0201)",
        ),
    ],
)
def test_a_malformed_roles_file_is_rejected(tmp_path, change, message):
    document = _document()
    change(document)

    with pytest.raises(attribute_roles.RoleError, match=re.escape(message)):
        temporal_roles.load_temporal_roles(
            _write(tmp_path / "temporal_roles.toml", document)
        )
