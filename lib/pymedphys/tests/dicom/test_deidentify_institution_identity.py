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

"""The Retain Institution Identity Option, applied end to end.

Every file is synthetic. Values that must never reach a written file carry
the text ``SENTINEL``.
"""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    cleaners,
    conformance,
    conformance_markdown,
    policy,
    run,
)
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.standard import load_table_e1_1

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
INSTITUTION_IDENTITY = policy.INSTITUTION_IDENTITY
INSTITUTION_IDENTITY_CODE = "113112"
_ETHICS_COMMITTEE_NAME = "(0012,0081)"
# Each kept attribute of the Option that an RT Plan can carry at the top
# level, by keyword, with a synthetic value.
_KEPT = {
    "InstitutionName": "SENTINEL HOSPITAL",
    "InstitutionAddress": "1 SENTINEL STREET",
    "InstitutionalDepartmentName": "SENTINEL ONCOLOGY",
    "ClinicalTrialSiteID": "SENTINEL-SITE-1",
    "ClinicalTrialSiteName": "SENTINEL SITE",
    "ClinicalTrialCoordinatingCenterName": "SENTINEL CENTRE",
}


def _code(value):
    return synthetic.item(
        CodeValue=value, CodingSchemeDesignator="99SENTINEL", CodeMeaning="Synthetic"
    )


def _transform(options):
    return InstanceTransform(
        policy.compose_custom_policy(options), KEY, unvalidated_policy=True
    )


def _basic():
    return InstanceTransform(
        policy.compose_policy("basic"), KEY, unvalidated_policy=True
    )


def _plan(**attributes):
    plan = synthetic.rt_plan()
    for keyword, value in attributes.items():
        setattr(plan, keyword, value)
    return plan


def _written(transform, dataset):
    data = synthetic.written(dataset)
    result = transform(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    return pydicom.dcmread(io.BytesIO(result.data))


def _codes(dataset):
    return [item.CodeValue for item in dataset.DeidentificationMethodCodeSequence]


def test_the_engine_applies_the_option_alone_and_with_the_others():
    assert INSTITUTION_IDENTITY in policy.TARGET_OPTIONS
    assert INSTITUTION_IDENTITY in policy.ENGINE_OPTIONS
    for other in policy.ENGINE_OPTIONS:
        composed = policy.compose_custom_policy({INSTITUTION_IDENTITY, other})
        if other != policy.SAFE_PRIVATE:
            policy.refuse_unapplied_options(composed)
    # The Option gives K only, and no other option gives its attributes an
    # action, so it needs no cleaner and conflicts with none.
    rows = [
        row
        for row in load_table_e1_1().attributes
        if INSTITUTION_IDENTITY in row.options
    ]
    assert len(rows) == 10
    for row in rows:
        assert row.options == {INSTITUTION_IDENTITY: "K"}, row.tag
    assert all(c.option != INSTITUTION_IDENTITY for c in cleaners.CLEANERS)


@pytest.mark.deid_requirement("PS3.15-E.3.11-01")
def test_the_option_keeps_the_institutions_identity():
    plan = _plan(**_KEPT)
    plan.InstitutionCodeSequence = pydicom.Sequence([_code("SENTINEL-INST")])
    plan.InstitutionalDepartmentTypeCodeSequence = pydicom.Sequence(
        [_code("SENTINEL-DEPT")]
    )
    equipment = synthetic.item(
        Manufacturer="SENTINEL MAKER", InstitutionName="SENTINEL HOSPITAL"
    )
    plan.ContributingEquipmentSequence = pydicom.Sequence([equipment])

    written = _written(_transform([INSTITUTION_IDENTITY]), plan)

    for keyword, value in _KEPT.items():
        assert written.get(keyword) == value, keyword
    (code,) = written.InstitutionCodeSequence
    assert code.CodeValue == "SENTINEL-INST"
    (code,) = written.InstitutionalDepartmentTypeCodeSequence
    assert code.CodeValue == "SENTINEL-DEPT"
    # The engine's own item follows the source's, which keeps its
    # institution.
    assert written.ContributingEquipmentSequence[0].InstitutionName == (
        "SENTINEL HOSPITAL"
    )
    assert _codes(written) == ["113100", INSTITUTION_IDENTITY_CODE]

    basic = _written(_basic(), plan)
    assert "SENTINEL" not in str(basic.get("InstitutionName", ""))
    for keyword in _KEPT:
        assert "SENTINEL" not in str(basic.get(keyword, "")), keyword
    assert "InstitutionCodeSequence" not in basic
    assert "InstitutionalDepartmentTypeCodeSequence" not in basic
    assert "InstitutionName" not in basic.ContributingEquipmentSequence[0]
    assert INSTITUTION_IDENTITY_CODE not in _codes(basic)


@pytest.mark.deid_requirement("PS3.15-E.3.11-01")
def test_the_ethics_committees_name_is_still_removed_with_its_approval_number():
    plan = _plan(
        ClinicalTrialProtocolEthicsCommitteeName="SENTINEL COMMITTEE",
        ClinicalTrialProtocolEthicsCommitteeApprovalNumber="SENTINEL 0001",
        InstitutionName="SENTINEL HOSPITAL",
    )

    written = _written(_transform([INSTITUTION_IDENTITY]), plan)

    assert "ClinicalTrialProtocolEthicsCommitteeName" not in written
    assert "ClinicalTrialProtocolEthicsCommitteeApprovalNumber" not in written
    assert written.InstitutionName == "SENTINEL HOSPITAL"
    assert _codes(written) == ["113100", INSTITUTION_IDENTITY_CODE]


@pytest.mark.deid_requirement("PS3.15-E.3.11-01")
def test_other_organisations_and_original_attributes_stay_removed():
    plan = _plan(InstitutionName="SENTINEL HOSPITAL")
    scheme = synthetic.item(
        CodingSchemeDesignator="99SENTINEL",
        CodingSchemeResponsibleOrganization="SENTINEL ORGANISATION",
    )
    plan.CodingSchemeIdentificationSequence = pydicom.Sequence([scheme])
    original = synthetic.item(
        SourceOfPreviousValues="SENTINEL SOURCE",
        AttributeModificationDateTime="20260101000000",
        ModifyingSystem="SENTINEL SYSTEM",
        ReasonForTheAttributeModification="CORRECT",
    )
    plan.OriginalAttributesSequence = pydicom.Sequence([original])

    written = _written(_transform([INSTITUTION_IDENTITY]), plan)

    assert written.InstitutionName == "SENTINEL HOSPITAL"
    for item in written.get("CodingSchemeIdentificationSequence", []):
        assert "CodingSchemeResponsibleOrganization" not in item
    assert "OriginalAttributesSequence" not in written


@pytest.mark.deid_requirement("PS3.15-E.3.11-01")
def test_the_statement_keeps_the_institution_and_removes_the_committees_name():
    statement = conformance.conformance_statement(
        policy.compose_custom_policy([INSTITUTION_IDENTITY]), vocabulary=None
    )

    assert not statement.pending
    assert not statement.cleaned
    kept = {
        row.tag
        for row in load_table_e1_1().attributes
        if row.options.get(INSTITUTION_IDENTITY) == "K"
    }
    actions = {entry.tag: entry for entry in statement.attributes}
    for tag in kept:
        assert actions[tag].action == "K", tag
    # The ethics committee's name is removed wherever it is (D-020).
    committee = actions[_ETHICS_COMMITTEE_NAME]
    assert committee.places
    assert {place.action for place in committee.places} == {"X"}
    assert committee.elsewhere == "X"
    text = conformance_markdown.render_markdown(statement)
    assert "or K under the Retain Institution Identity Option, is removed" in text
    assert "Options applied: Retain Institution Identity Option (DCM 113112)" in text
