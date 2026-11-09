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

"""Attributes that only the second-generation RT IODs define, five items deep.

The synthetic corpus plants no attribute deeper than four items, so it
plants none of these. RT Patient Position Acquisition Instruction defines
the Selector values of a parameter's constraint, which Table E.1-1 gives D,
in Constraint Value Sequence (0082,0034) and Recommended Default Value
Sequence (0082,0035) of Parameters Specification Sequence (0018,9913), in
CT Imaging Acquisition Parameter Sequence (3002,0126) of each acquisition
subtask. RT Physician Intent defines Source Conceptual Volume UID
(3010,0015), which Table E.1-1 gives U, in Source Conceptual Volume Sequence
(3010,0018) of each derived Conceptual Volume of an anatomic prescription.

Every instance is synthetic. Values that must never reach a written file
carry the text ``SENTINEL``.
"""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import policy, run, standard
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.element_rules import ElementRules
from pymedphys._dicom.deidentify.uids import replacement_uid
from pymedphys._dicom.deidentify.walker import SequesterReason, plan_instance

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
INSTRUCTION = "RT Patient Position Acquisition Instruction"
INTENT = "RT Physician Intent"
INSTRUCTION_STORAGE = "1.2.840.10008.5.1.4.1.1.481.25"
INTENT_STORAGE = "1.2.840.10008.5.1.4.1.1.481.10"
SENTINEL = "SENTINEL"
# The items that hold a constraint's values, by sequence.
TASK = "(3002,0118)"
SUBTASK = "(3002,011A)"
CT_PARAMETERS = "(3002,0126)"
SPECIFICATION = "(0018,9913)"
CONSTRAINT_VALUE = "(0082,0034)"
RECOMMENDED_DEFAULT = "(0082,0035)"
# Each Selector value that Table E.1-1 gives D and whose VR has a dummy
# value, with a source value that identifies, where its VR allows text, by
# the sentinel.
SELECTOR_VALUES = {
    "(0072,0061)": ("DA", "20240229"),
    "(0072,0063)": ("DT", "20240229123456"),
    "(0072,0066)": ("LO", "SENTINEL LO"),
    "(0072,0068)": ("LT", "SENTINEL LT"),
    "(0072,006A)": ("PN", "SENTINEL^PN"),
    "(0072,006B)": ("TM", "123456"),
    "(0072,006C)": ("SH", "SENTINEL SH"),
    "(0072,006E)": ("ST", "SENTINEL ST"),
    "(0072,0070)": ("UT", "SENTINEL UT"),
}
# Each Selector value that Table E.1-1 gives D and whose VR has no dummy
# value, so D sequesters the instance that holds it (D-021).
SELECTOR_VALUES_WITHOUT_DUMMY = {
    "(0072,005E)": ("AE", "SENTINEL_AE"),
    "(0072,005F)": ("AS", "042Y"),
    "(0072,0065)": ("OB", b"SENTINEL"),
    "(0072,006D)": ("UN", b"SENTINEL"),
    "(0072,0071)": ("UR", "https://sentinel.invalid/SENTINEL"),
}
# The places of a Source Conceptual Volume UID in an RT Physician Intent.
PRESCRIPTION = "(3010,006B)"
ANATOMIC_PRESCRIPTION = "(3010,0060)"
CONCEPTUAL_VOLUME = "(3010,0025)"
DERIVATION = "(3010,0014)"
SOURCE_VOLUME = "(3010,0018)"
SOURCE_VOLUME_UID = "(3010,0015)"
SOURCE_UID = "1.2.826.0.1.3680043.10.190.7"


def _number(tag):
    return int(tag[1:5] + tag[6:10], 16)


def _header(sop_class, modality):
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = "1.2.826.0.1.3680043.10.190.1"
    dataset.PatientName = f"{SENTINEL}^PATIENT"
    dataset.PatientID = f"{SENTINEL}-PID"
    dataset.StudyInstanceUID = "1.2.826.0.1.3680043.10.190.2"
    dataset.SeriesInstanceUID = "1.2.826.0.1.3680043.10.190.3"
    dataset.Modality = modality
    return dataset


def _nest(dataset, tags, leaf):
    """Put ``leaf`` as the one item of the innermost of ``tags``, in turn."""
    item = dataset
    for tag in tags[:-1]:
        inner = pydicom.Dataset()
        item.add_new(_number(tag), "SQ", pydicom.Sequence([inner]))
        item = inner
    item.add_new(_number(tags[-1]), "SQ", pydicom.Sequence([leaf]))
    return dataset


def _instruction(values):
    """Return an RT Patient Position Acquisition Instruction with a constraint.

    Its one parameter specification constrains a parameter to ``values``,
    by tag, and recommends the same values as the parameter's default. The
    instance does not hold every attribute that its IOD requires, as the
    synthetic corpus's do not.
    """
    specification = pydicom.Dataset()
    specification.add_new(0x00820018, "LO", "Exposure")
    specification.add_new(0x00820032, "CS", "EQUAL")
    for sequence in (CONSTRAINT_VALUE, RECOMMENDED_DEFAULT):
        item = pydicom.Dataset()
        for tag, (vr, value) in values.items():
            item.add_new(_number(tag), vr, value)
        specification.add_new(_number(sequence), "SQ", pydicom.Sequence([item]))
    return _nest(
        _header(INSTRUCTION_STORAGE, "PLAN"),
        (TASK, SUBTASK, CT_PARAMETERS, SPECIFICATION),
        specification,
    )


def _intent():
    """Return an RT Physician Intent whose prescription derives a volume."""
    source = pydicom.Dataset()
    source.add_new(_number(SOURCE_VOLUME_UID), "UI", SOURCE_UID)
    return _nest(
        _header(INTENT_STORAGE, "RTINTENT"),
        (
            PRESCRIPTION,
            ANATOMIC_PRESCRIPTION,
            CONCEPTUAL_VOLUME,
            DERIVATION,
            SOURCE_VOLUME,
        ),
        source,
    )


def _plan(dataset, name):
    source = read_source(synthetic.written(dataset))
    rules = ElementRules(policy.compose_custom_policy(()))
    return plan_instance(source, rules, load_iod_tables().iods[name])


def _transformed(dataset):
    data = synthetic.written(dataset)
    transform = InstanceTransform(
        policy.compose_custom_policy(()), KEY, unvalidated_policy=True
    )
    return transform(data, InstanceRecord.from_file(data))


def test_the_corpus_iods_define_these_only_five_items_deep():
    tables = load_iod_tables()
    rows = {row.tag: row for row in standard.load_table_e1_1().attributes}
    for tag in (*SELECTOR_VALUES, *SELECTOR_VALUES_WITHOUT_DUMMY):
        assert rows[tag].basic_profile == "D", tag
        paths = {
            definition.path
            for definition in tables.iods[INSTRUCTION].definitions
            if definition.tag == tag
        }
        assert paths == {
            (TASK, SUBTASK, CT_PARAMETERS, SPECIFICATION, sequence)
            for sequence in (CONSTRAINT_VALUE, RECOMMENDED_DEFAULT)
        }, tag
    assert rows[SOURCE_VOLUME_UID].basic_profile == "U"
    assert (
        PRESCRIPTION,
        ANATOMIC_PRESCRIPTION,
        CONCEPTUAL_VOLUME,
        DERIVATION,
        SOURCE_VOLUME,
    ) in {
        definition.path
        for definition in tables.iods[INTENT].definitions
        if definition.tag == SOURCE_VOLUME_UID
    }


@pytest.mark.deid_requirement("PS3.15-E.1.1-01", "MIDI-BP-03")
def test_d_gives_each_selector_value_its_dummy_value():
    values = {tag: value for tag, (_, value) in SELECTOR_VALUES.items()}
    plan = _plan(_instruction(SELECTOR_VALUES), INSTRUCTION)
    planned = {element.path: element.action for element in plan.elements}

    assert not plan.sequestrations
    for sequence in (CONSTRAINT_VALUE, RECOMMENDED_DEFAULT):
        within = (
            (TASK, 0),
            (SUBTASK, 0),
            (CT_PARAMETERS, 0),
            (SPECIFICATION, 0),
            (sequence, 0),
        )
        for tag in SELECTOR_VALUES:
            assert planned[ElementPath(within, tag)] == "D", (sequence, tag)

    result = _transformed(_instruction(SELECTOR_VALUES))
    assert isinstance(result, run.Transformed), result
    assert SENTINEL.encode() not in result.data
    written = pydicom.dcmread(io.BytesIO(result.data))
    (task,) = written[_number(TASK)].value
    (subtask,) = task[_number(SUBTASK)].value
    (parameters,) = subtask[_number(CT_PARAMETERS)].value
    (specification,) = parameters[_number(SPECIFICATION)].value
    for sequence in (CONSTRAINT_VALUE, RECOMMENDED_DEFAULT):
        (item,) = specification[_number(sequence)].value
        for tag, value in values.items():
            element = item[_number(tag)]
            # Type 1C, so a dummy value rather than none (D-020).
            assert element.value not in ("", None), tag
            assert str(element.value) != value, tag


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@pytest.mark.parametrize("tag", sorted(SELECTOR_VALUES_WITHOUT_DUMMY))
def test_a_selector_value_without_a_dummy_value_sequesters_the_instance(tag):
    # Selector AE, AS, OB, UN, and UR Values: no IOD supported before RT
    # Patient Position Acquisition Instruction defines them.
    values = {tag: SELECTOR_VALUES_WITHOUT_DUMMY[tag]}
    plan = _plan(_instruction(values), INSTRUCTION)

    assert {
        (sequestration.path.tag, sequestration.action, sequestration.reason)
        for sequestration in plan.sequestrations
    } == {(tag, "D", SequesterReason.NO_DUMMY_VALUE)}
    assert len(plan.sequestrations) == 2
    assert not isinstance(_transformed(_instruction(values)), run.Transformed)


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
def test_a_source_conceptual_volume_uid_is_replaced_by_the_runs_key():
    result = _transformed(_intent())

    assert isinstance(result, run.Transformed), result
    written = pydicom.dcmread(io.BytesIO(result.data))
    item = written
    for tag in (
        PRESCRIPTION,
        ANATOMIC_PRESCRIPTION,
        CONCEPTUAL_VOLUME,
        DERIVATION,
        SOURCE_VOLUME,
    ):
        (item,) = item[_number(tag)].value
    assert item[_number(SOURCE_VOLUME_UID)].value == replacement_uid(KEY, SOURCE_UID)
