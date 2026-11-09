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

"""The reviewed rule of Operator Identification Sequence (0008,1072), D-021.

Table E.1-1 gives the sequence X/D. The RT Radiation Record Common Module
(PS3.3 Section C.36.22) makes it Type 1 in each item of Override Sequence
(3008,0060), within Treatment Tolerance Violation Sequence (300A,0731), of
the C-Arm Photon-Electron, Tomotherapeutic, and Robotic-Arm Radiation
Records and of RT Radiation Salvage Record, so it resolves to D, which a
sequence has no generic dummy value for. There D keeps each source item,
with only the attributes of Table C.17-3b, the Identified Person or Device
Macro, each under its own rule, as the maintainer chose on 7 November 2026,
as for Verifying Observer Sequence.

Every record is synthetic. Values that must never reach a written file
carry the text ``SENTINEL``.
"""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    dummy_values,
    policy,
    run,
    standard,
)
from pymedphys._dicom.deidentify.element_rules import ElementRules, RuleSource
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.walker import SequesterReason, plan_instance

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
SALVAGE_RECORD = "RT Radiation Salvage Record"
RT_RADIATION_SALVAGE_RECORD_STORAGE = "1.2.840.10008.5.1.4.1.1.481.17"
TOLERANCE_RECORDS = (
    "C-Arm Photon-Electron Radiation Record",
    "Tomotherapeutic Radiation Record",
    "Robotic-Arm Radiation Record",
    SALVAGE_RECORD,
)
OPERATOR = dummy_values.OPERATOR_IDENTIFICATION_SEQUENCE
VIOLATION = "(300A,0731)"
OVERRIDE = dummy_values.OVERRIDE_SEQUENCE
CONTRIBUTING_SOURCES = "(0018,9506)"
OBSERVER_TYPE = "(0040,A084)"
PERSON_NAME = "(0040,A123)"
PERSON_IDENTIFICATION_CODE = "(0040,1101)"
STATION_NAME = "(0008,1010)"
DEVICE_UID = "(0018,1002)"
MANUFACTURER = "(0008,0070)"
STATION_AE_TITLE = "(0008,0055)"
DEVICE_SERIAL_NUMBER = "(0018,1000)"
INSTITUTION_NAME = "(0008,0080)"
INSTITUTION_CODE = "(0008,0082)"
INSTITUTIONAL_DEPARTMENT_NAME = "(0008,1040)"
INSTITUTION_ADDRESS = "(0008,0081)"
CODE_VALUE = "(0008,0100)"
SENTINEL = "SENTINEL"
DEVICE = "1.2.826.0.1.3680043.10.189.40"


def _code(value, designator, meaning):
    code = pydicom.Dataset()
    code.CodeValue = value
    code.CodingSchemeDesignator = designator
    code.CodeMeaning = meaning
    return code


def _person(*, extra=False):
    """Return an item that identifies a person who approved an override.

    ``extra`` adds Institution Address, which Table C.17-3b does not define
    in the item, and Institutional Department Name, which it does.
    """
    operator = pydicom.Dataset()
    operator.ObserverType = "PSN"
    operator.PersonName = f"{SENTINEL}^OPERATOR"
    operator.PersonIdentificationCodeSequence = pydicom.Sequence(
        [_code(f"{SENTINEL}-ID", "99PMP", f"{SENTINEL}^CODE")]
    )
    operator.InstitutionName = f"{SENTINEL} HOSPITAL"
    operator.InstitutionCodeSequence = pydicom.Sequence(
        [_code(f"{SENTINEL}-INST", "99PMP", f"{SENTINEL} INSTITUTE")]
    )
    if extra:
        operator.InstitutionAddress = f"{SENTINEL} STREET"
        operator.InstitutionalDepartmentName = f"{SENTINEL} DEPARTMENT"
    return operator


def _device():
    """Return a deliberately non-conforming DEV item for robustness checks.

    Table C.17-3b defines a device's attributes, but the RT Radiation Record
    Common Module requires Observer Type PSN in an override (PS3.3 Table
    C.36.22-1), so this item checks that an unexpected device item is cleaned
    too; :func:`_person` gives the conforming item.
    """
    operator = pydicom.Dataset()
    operator.ObserverType = "DEV"
    operator.StationName = f"{SENTINEL}-STATION"
    operator.DeviceUID = DEVICE
    operator.Manufacturer = "FIXTURE MAKER"
    operator.StationAETitle = "SENTINELAE"
    operator.DeviceSerialNumber = f"{SENTINEL}-SERIAL"
    operator.InstitutionName = f"{SENTINEL} HOSPITAL"
    operator.InstitutionCodeSequence = pydicom.Sequence()
    return operator


def _record(*operators):
    """Return an RT Radiation Salvage Record whose one override has ``operators``.

    Its header holds the patient, study, series, equipment, and SOP Common
    attributes that the de-identification reads, and one treatment
    tolerance violation with one override.
    """
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = RT_RADIATION_SALVAGE_RECORD_STORAGE
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
    dataset.Modality = "RTRAD"
    dataset.SeriesInstanceUID = "1.2.826.0.1.3680043.10.189.2"
    dataset.SeriesNumber = 1
    dataset.Manufacturer = "FIXTURE MAKER"
    dataset.InstanceNumber = 1
    override = pydicom.Dataset()
    override.OperatorIdentificationSequence = pydicom.Sequence(list(operators))
    override.OverrideDateTime = "20260314101500"
    override.OverrideReason = f"{SENTINEL} REASON"
    override.AlternateValueSequence = pydicom.Sequence()
    violation = pydicom.Dataset()
    violation.TreatmentToleranceViolationDateTime = "20260314101400"
    violation.TreatmentToleranceViolationCategory = "WARNING"
    violation.TreatmentToleranceViolationTypeCodeSequence = pydicom.Sequence(
        [_code("TYP1", "99PMP", "Fixture violation type")]
    )
    violation.TreatmentToleranceViolationCauseCodeSequence = pydicom.Sequence(
        [_code("CAU1", "99PMP", "Fixture violation cause")]
    )
    violation.OverrideSequence = pydicom.Sequence([override])
    dataset.TreatmentToleranceViolationSequence = pydicom.Sequence([violation])
    return dataset


def _plan(dataset, iod=SALVAGE_RECORD, options=()):
    source = read_source(synthetic.written(dataset))
    rules = ElementRules(policy.compose_custom_policy(options))
    return plan_instance(source, rules, load_iod_tables().iods[iod])


def _in_item(index, tag, *deeper):
    items = ((VIOLATION, 0), (OVERRIDE, 0), (OPERATOR, index), *deeper)
    return ElementPath(items, tag)


def _written(options, dataset):
    data = synthetic.written(dataset)
    transform = InstanceTransform(
        policy.compose_custom_policy(options), KEY, unvalidated_policy=True
    )
    result = transform(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    assert SENTINEL.encode() not in result.data
    return pydicom.dcmread(io.BytesIO(result.data))


def test_the_rule_keeps_the_attributes_of_the_identified_person_or_device_macro():
    kept = dummy_values.KEPT_ITEM_ATTRIBUTES[OPERATOR]
    tables = load_iod_tables().iods
    # Wherever an IOD makes the sequence anything but Type 3, its X/D
    # resolves to D. The rule holds only at the place that the maintainer
    # reviewed, where the item holds the macro's attributes and no others.
    required = {
        (iod.name, definition.path)
        for iod in tables.values()
        for path in iod.paths(OPERATOR)
        for definition in iod.lookup(OPERATOR, path)
        if definition.type != "3"
    }
    reviewed = {(name, path) for name, path in required if path[-1:] == (OVERRIDE,)}

    assert reviewed == {(name, (VIOLATION, OVERRIDE)) for name in TOLERANCE_RECORDS}
    for name, path in reviewed:
        defined = {
            definition.tag
            for definition in tables[name].definitions
            if definition.path == (*path, OPERATOR)
        }
        assert defined == kept, name
        assert {
            definition.tables[-1]
            for definition in tables[name].definitions
            if definition.path == (*path, OPERATOR)
        } == {"Table C.17-3b"}
    for name, path in required - reviewed:
        assert dummy_values.kept_item_attributes(OPERATOR, path) is None, name
    rows = {row.tag: row for row in standard.load_table_e1_1().attributes}
    assert rows[OPERATOR].basic_profile == "X/D"
    # Its items' attributes stay its own: the rule writes no items.
    with pytest.raises(dummy_values.NoDummyValueError):
        dummy_values.items_for_d(OPERATOR, [], KEY, within=(VIOLATION, OVERRIDE))


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_d_keeps_each_item_with_each_attribute_under_its_own_rule():
    plan = _plan(_record(_person(), _device(), _person(extra=True)))
    planned = {element.path: element for element in plan.elements}

    assert not plan.sequestrations
    operator = planned[ElementPath(((VIOLATION, 0), (OVERRIDE, 0)), OPERATOR)]
    assert (operator.rule.action, operator.action) == ("X/D", "D")
    assert operator.removed_with is None
    for index in (0, 2):
        assert planned[_in_item(index, OBSERVER_TYPE)].action == "K"
        assert planned[_in_item(index, PERSON_NAME)].action == "D"
        assert planned[_in_item(index, PERSON_IDENTIFICATION_CODE)].action == "D"
        # Institution Name and Institution Code Sequence are Type 2 there,
        # so their X/Z/D empties them.
        assert planned[_in_item(index, INSTITUTION_NAME)].action == "Z"
        institution = _in_item(index, INSTITUTION_CODE)
        assert planned[institution].action == "Z"
        code_value = _in_item(index, CODE_VALUE, (INSTITUTION_CODE, 0))
        assert planned[code_value].removed_with == institution
    assert planned[_in_item(1, OBSERVER_TYPE)].action == "K"
    # In the non-conforming device item, Station Name is Type 2C, Device UID
    # a UID, and Manufacturer kept by the Basic Profile; the Type 3
    # attributes are removed by their rows.
    assert planned[_in_item(1, STATION_NAME)].action == "Z"
    assert planned[_in_item(1, DEVICE_UID)].action == "U"
    assert planned[_in_item(1, MANUFACTURER)].action == "K"
    assert planned[_in_item(1, STATION_AE_TITLE)].action == "X"
    assert planned[_in_item(1, DEVICE_SERIAL_NUMBER)].action == "X"
    department = planned[_in_item(2, INSTITUTIONAL_DEPARTMENT_NAME)]
    assert department.action == "X"
    assert department.rule.source is not RuleSource.ENGINE
    # An attribute that the macro does not define in the item is removed,
    # whatever its own rule.
    address = planned[_in_item(2, INSTITUTION_ADDRESS)]
    assert address.action == "X"
    assert address.rule.source is RuleSource.ENGINE


def test_an_override_without_operators_keeps_an_empty_sequence():
    plan = _plan(_record())

    (operator,) = [e for e in plan.elements if e.path.tag == OPERATOR]
    assert operator.action == "D"
    assert not plan.sequestrations


def test_d_elsewhere_has_no_reviewed_rule_and_sequesters():
    # The Contributing Sources Sequence of the X-Ray 3D image IODs makes the
    # sequence Type 1C, with the Person Identification Macro in its items, a
    # place that the maintainer has not reviewed (D-021).
    iod = "X-Ray 3D Angiographic Image"
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = "1.2.840.10008.5.1.4.1.1.13.1.1"
    dataset.SOPInstanceUID = "1.2.826.0.1.3680043.10.189.3"
    source = pydicom.Dataset()
    source.OperatorIdentificationSequence = pydicom.Sequence([_person()])
    dataset.ContributingSourcesSequence = pydicom.Sequence([source])

    plan = _plan(dataset, iod)

    path = ElementPath(((CONTRIBUTING_SOURCES, 0),), OPERATOR)
    assert [(s.path, s.reason) for s in plan.sequestrations] == [
        (path, SequesterReason.NO_DUMMY_VALUE)
    ]


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_a_record_is_written_with_each_operator_item_de_identified():
    written = _written((), _record(_person(), _device()))

    (violation,) = written.TreatmentToleranceViolationSequence
    (override,) = violation.OverrideSequence
    person, device = override.OperatorIdentificationSequence
    assert person.ObserverType == "PSN"
    assert person.PersonName == "DEIDENTIFIED"
    (code,) = person.PersonIdentificationCodeSequence
    assert (code.CodeValue, code.CodingSchemeDesignator) == (
        "DEIDENTIFIED",
        "99PYMEDPHYS",
    )
    assert person.InstitutionName == ""
    assert len(person.InstitutionCodeSequence) == 0
    assert device.ObserverType == "DEV"
    assert device.StationName == ""
    assert device.DeviceUID not in ("", DEVICE)
    assert device.Manufacturer == "FIXTURE MAKER"
    assert "StationAETitle" not in device
    assert "DeviceSerialNumber" not in device


@pytest.mark.parametrize("preset", ["basic", "public-release"])
def test_the_statement_describes_the_kept_items_at_their_place(preset):
    statement = conformance.conformance_statement(
        policy.compose_policy(preset), vocabulary=None
    )
    markdown = " ".join(conformance_markdown.render_markdown(statement).split())

    assert (
        "D on Operator Identification Sequence (0008,1072) directly in an item "
        "of Override Sequence (3008,0060) keeps each source item, and in it "
        "only these attributes, each under the action that the policy gives "
        "it there: "
    ) in markdown
    assert (
        "Observer Type (0040,A084), `K`, as an attribute of VR CS that no rule covers"
    ) in markdown
    assert "Person Name (0040,A123), `D`" in markdown
