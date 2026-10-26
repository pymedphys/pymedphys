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

"""The reviewed rule of Verifying Observer Sequence (0040,A073), D-021.

Table E.1-1 gives the sequence D under every option, and it is Type 1C in
the SR Document General Module, required where Verification Flag is
VERIFIED. D keeps each source item, with only the four attributes that
PS3.3 Table C.17-2 defines in it, each under its own rule.

Every report is synthetic. Values that must never reach a written file
carry the text ``SENTINEL``. Structured Report IODs are not supported yet,
so the tests that write a report add Comprehensive SR to the supported IODs
for that test alone, as supporting it would.
"""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    dummy_values,
    policy,
    run,
    scope,
    standard,
)
from pymedphys._dicom.deidentify.element_rules import ElementRules, RuleSource
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.walker import plan_instance

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
CSC = policy.CLEAN_STRUCTURED_CONTENT
REPORT = "Comprehensive SR"
COMPREHENSIVE_SR = "1.2.840.10008.5.1.4.1.1.88.33"
VERIFYING_OBSERVER = dummy_values.VERIFYING_OBSERVER_SEQUENCE
VERIFYING_ORGANIZATION = "(0040,A027)"
VERIFICATION_DATETIME = "(0040,A030)"
VERIFYING_OBSERVER_NAME = "(0040,A075)"
IDENTIFICATION_CODE = "(0040,A088)"
PERSON_IDENTIFICATION_CODE = "(0040,1101)"
INSTITUTION_NAME = "(0008,0080)"
CODE_VALUE = "(0008,0100)"
CONTENT = "(0040,A730)"
VERIFIED_AT = "20260314101500"
SENTINEL = "SENTINEL"


def _code(value, designator, meaning):
    code = pydicom.Dataset()
    code.CodeValue = value
    code.CodingSchemeDesignator = designator
    code.CodeMeaning = meaning
    return code


def _observer(name=f"{SENTINEL}^VERIFIER", *, extra=False):
    """Return an item of Verifying Observer Sequence.

    ``extra`` adds two attributes that PS3.3 does not define in the item:
    Person Identification Code Sequence, with an item, and Institution Name.
    """
    observer = pydicom.Dataset()
    observer.VerifyingObserverName = name
    observer.VerifyingObserverIdentificationCodeSequence = pydicom.Sequence(
        [_code(f"{SENTINEL}-ID", "99PMP", f"{SENTINEL}^CODE")]
    )
    observer.VerifyingOrganization = f"{SENTINEL} HOSPITAL"
    observer.VerificationDateTime = VERIFIED_AT
    if extra:
        observer.PersonIdentificationCodeSequence = pydicom.Sequence(
            [_code(f"{SENTINEL}-PID", "99PMP", f"{SENTINEL}^PERSON")]
        )
        observer.InstitutionName = f"{SENTINEL} INSTITUTE"
    return observer


def _report(*observers, content=True):
    """Return a VERIFIED Comprehensive SR with ``observers``.

    Its header holds the required attributes of the Patient, General Study,
    SR Document Series, General Equipment, SR Document General, and SOP
    Common Modules. With ``content``, its tree holds one item that Clean
    Structured Content keeps: a code whose concept Table E.3.4-1 does not
    list, coded in the invented local scheme ``99PMP``.
    """
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = COMPREHENSIVE_SR
    dataset.SOPInstanceUID = "1.2.826.0.1.3680043.10.189.3"
    dataset.PatientName = f"{SENTINEL}^PATIENT"
    dataset.PatientID = f"{SENTINEL}-PID"
    dataset.PatientBirthDate = ""
    dataset.PatientSex = ""
    dataset.StudyInstanceUID = "1.2.826.0.1.3680043.10.189.1"
    dataset.StudyDate = "20260314"
    dataset.StudyTime = "093000"
    dataset.ReferringPhysicianName = ""
    dataset.StudyID = ""
    dataset.AccessionNumber = ""
    dataset.Modality = "SR"
    dataset.SeriesInstanceUID = "1.2.826.0.1.3680043.10.189.2"
    dataset.SeriesNumber = 1
    dataset.ReferencedPerformedProcedureStepSequence = pydicom.Sequence()
    dataset.Manufacturer = "FIXTURE MAKER"
    dataset.InstanceNumber = 1
    dataset.CompletionFlag = "COMPLETE"
    dataset.VerificationFlag = "VERIFIED"
    dataset.ContentDate = "20260314"
    dataset.ContentTime = "120000"
    dataset.VerifyingObserverSequence = pydicom.Sequence(list(observers))
    dataset.PerformedProcedureCodeSequence = pydicom.Sequence()
    if content:
        dataset.ValueType = "CONTAINER"
        dataset.ConceptNameCodeSequence = pydicom.Sequence(
            [_code("TTL1", "99PMP", "Fixture report")]
        )
        dataset.ContinuityOfContent = "SEPARATE"
        finding = pydicom.Dataset()
        finding.RelationshipType = "CONTAINS"
        finding.ValueType = "CODE"
        finding.ConceptNameCodeSequence = pydicom.Sequence(
            [_code("CTX1", "99PMP", "Fixture context")]
        )
        finding.ConceptCodeSequence = pydicom.Sequence(
            [_code("VAL1", "99PMP", "Fixture")]
        )
        dataset.ContentSequence = pydicom.Sequence([finding])
    return dataset


def _plan(dataset, options=()):
    source = read_source(synthetic.written(dataset))
    rules = ElementRules(policy.compose_custom_policy(options))
    return plan_instance(source, rules, load_iod_tables().iods[REPORT])


def _path(*items, tag):
    return ElementPath(tuple(items), tag)


def _in_item(index, tag, *deeper):
    return _path((VERIFYING_OBSERVER, index), *deeper, tag=tag)


@pytest.fixture(name="supported")
def _supported(monkeypatch):
    """Add Comprehensive SR to the supported IODs, as supporting it would."""
    monkeypatch.setattr(scope, "SUPPORTED_IODS", scope.SUPPORTED_IODS | {REPORT})


def _written(options, dataset):
    data = synthetic.written(dataset)
    transform = InstanceTransform(
        policy.compose_custom_policy(options), KEY, unvalidated_policy=True
    )
    result = transform(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    assert SENTINEL.encode() not in result.data
    return pydicom.dcmread(io.BytesIO(result.data))


def test_the_rule_keeps_the_attributes_that_ps3_3_defines_in_an_item():
    kept = dummy_values.KEPT_ITEM_ATTRIBUTES[VERIFYING_OBSERVER]
    reports = [
        iod
        for iod in load_iod_tables().iods.values()
        if iod.lookup(VERIFYING_OBSERVER, ())
    ]

    assert REPORT in {iod.name for iod in reports}
    for iod in reports:
        defined = {
            definition.tag
            for definition in iod.definitions
            if definition.path == (VERIFYING_OBSERVER,)
        }
        assert defined == kept, iod.name
    rows = {row.tag: row for row in standard.load_table_e1_1().attributes}
    assert rows[VERIFYING_OBSERVER].basic_profile == "D"
    assert {tag: rows[tag].basic_profile for tag in kept} == {
        VERIFYING_ORGANIZATION: "D",
        VERIFICATION_DATETIME: "D",
        VERIFYING_OBSERVER_NAME: "D",
        IDENTIFICATION_CODE: "Z",
    }
    # Its items' attributes stay its own: the rule writes no items.
    with pytest.raises(dummy_values.NoDummyValueError):
        dummy_values.items_for_d(VERIFYING_OBSERVER, [], KEY)


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_d_keeps_each_item_with_only_its_reviewed_attributes():
    plan = _plan(_report(_observer(), _observer(extra=True), content=False))
    planned = {element.path: element for element in plan.elements}

    assert not plan.sequestrations
    observer = planned[_path(tag=VERIFYING_OBSERVER)]
    assert (observer.rule.action, observer.action) == ("D", "D")
    assert observer.removed_with is None
    for index in (0, 1):
        assert planned[_in_item(index, VERIFYING_OBSERVER_NAME)].action == "D"
        assert planned[_in_item(index, VERIFYING_ORGANIZATION)].action == "D"
        assert planned[_in_item(index, VERIFICATION_DATETIME)].action == "D"
        code_sequence = _in_item(index, IDENTIFICATION_CODE)
        assert planned[code_sequence].action == "Z"
        code_value = _in_item(index, CODE_VALUE, (IDENTIFICATION_CODE, 0))
        assert planned[code_value].removed_with == code_sequence
    # The attributes that PS3.3 does not define in the item are removed,
    # whatever their own rules, and so is everything in them.
    for tag in (PERSON_IDENTIFICATION_CODE, INSTITUTION_NAME):
        extra = planned[_in_item(1, tag)]
        assert extra.action == "X"
        assert extra.rule.source is RuleSource.ENGINE
    person_code = _in_item(1, CODE_VALUE, (PERSON_IDENTIFICATION_CODE, 0))
    assert planned[person_code].removed_with == _in_item(1, PERSON_IDENTIFICATION_CODE)


@pytest.mark.parametrize(
    "options, action",
    [
        ((), "D"),
        ((policy.FULL_DATES,), "K"),
        ((policy.MODIFIED_DATES,), "C"),
    ],
)
def test_verification_datetime_takes_its_own_rows_action(options, action):
    plan = _plan(_report(_observer(), content=False), options)
    planned = {element.path: element.action for element in plan.elements}

    assert planned[_in_item(0, VERIFICATION_DATETIME)] == action
    assert planned[_in_item(0, VERIFYING_OBSERVER_NAME)] == "D"
    assert not plan.sequestrations


def test_a_report_without_verifying_observers_keeps_an_empty_sequence():
    plan = _plan(_report(content=False))

    (observer,) = [e for e in plan.elements if e.path.tag == VERIFYING_OBSERVER]
    assert observer.action == "D"
    assert not plan.sequestrations


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@pytest.mark.usefixtures("supported")
def test_a_verified_report_is_written_with_one_dummy_verifier_per_item():
    # The second verifier's name equals the first constant, so it takes the
    # second, as D compares values (D-021).
    dataset = _report(_observer(), _observer("Deidentified", extra=True))

    written = _written((CSC,), dataset)

    assert written.VerificationFlag == "VERIFIED"
    first, second = written.VerifyingObserverSequence
    for item, name in ((first, "DEIDENTIFIED"), (second, "DE-IDENTIFIED")):
        assert set(item.keys()) == {
            pydicom.tag.Tag(int(tag[1:5] + tag[6:10], 16))
            for tag in dummy_values.KEPT_ITEM_ATTRIBUTES[VERIFYING_OBSERVER]
        }
        assert item.VerifyingObserverName == name
        assert item.VerifyingOrganization == "DEIDENTIFIED"
        assert item.VerificationDateTime == "19000101000000"
        assert len(item.VerifyingObserverIdentificationCodeSequence) == 0


@pytest.mark.usefixtures("supported")
def test_full_dates_keep_a_verification_datetime():
    written = _written((CSC, policy.FULL_DATES), _report(_observer()))

    (item,) = written.VerifyingObserverSequence
    assert item.VerificationDateTime == VERIFIED_AT
    assert item.VerifyingObserverName == "DEIDENTIFIED"


@pytest.mark.usefixtures("supported")
def test_modified_dates_modify_a_verification_datetime():
    written = _written((CSC, policy.MODIFIED_DATES), _report(_observer()))

    (item,) = written.VerifyingObserverSequence
    modified = item.VerificationDateTime
    assert modified and modified not in (VERIFIED_AT, "19000101000000")
    assert item.VerifyingObserverName == "DEIDENTIFIED"


@pytest.mark.parametrize(
    "options, action",
    [
        ((), "D"),
        ((policy.FULL_DATES,), "K"),
        ((policy.MODIFIED_DATES,), "C"),
    ],
)
def test_the_statement_describes_the_kept_items(options, action):
    composed = policy.compose_custom_policy(options)
    statement = conformance.conformance_statement(composed, vocabulary=None)
    markdown = conformance_markdown.render_markdown(statement)

    assert (
        "D on Verifying Observer Sequence (0040,A073) keeps each source item, "
        "and in it only these attributes, each under the action that the "
        "policy gives it: Verifying Organization (0040,A027), `D`; "
        f"Verification DateTime (0040,A030), `{action}`; Verifying Observer "
        "Name (0040,A075), `D`; Verifying Observer Identification Code "
        "Sequence (0040,A088), `Z`."
    ) in " ".join(markdown.split())
