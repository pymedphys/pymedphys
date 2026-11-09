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

"""The reviewed rule of Referenced Study Sequence (0008,1110), D-021.

Table E.1-1 gives the sequence X/Z, and K under Retain UIDs. It is Type 1
only in the Related Information Entities Macro (PS3.3 Table 10.37-1), which
two reference items of RT Physician Intent and one of RT Patient Position
Acquisition Instruction include, so X/Z resolves to D there. D keeps each
source item, with only the three attributes that the macro defines in it,
each under its own rule.

Every instance is synthetic. Values that must never reach a written file
carry the text ``SENTINEL``.
"""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    compound_actions,
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
from pymedphys._dicom.deidentify.uids import replacement_uid
from pymedphys._dicom.deidentify.walker import plan_instance

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
INTENT = "RT Physician Intent"
RT_PHYSICIAN_INTENT_STORAGE = "1.2.840.10008.5.1.4.1.1.481.10"
REFERENCED_STUDY = dummy_values.REFERENCED_STUDY_SEQUENCE
STUDY_INSTANCE_UID = "(0020,000D)"
PERTINENT_SOP_CLASSES_IN_STUDY = "(3010,0052)"
REFERENCED_SERIES = "(0008,1115)"
SERIES_INSTANCE_UID = "(0020,000E)"
REFERENCED_IMAGE = "(0008,1140)"
REFERENCED_SOP_INSTANCE_UID = "(0008,1155)"
STUDY_DESCRIPTION = "(0008,1030)"
INTENT_SEQUENCE = "(3010,0057)"
INPUT_INSTANCE = "(3010,005F)"
# Each place where Referenced Study Sequence is Type 1, by IOD.
TYPE_1_PLACES = {
    ("RT Physician Intent", (INTENT_SEQUENCE, INPUT_INSTANCE)),
    ("RT Physician Intent", ("(3010,006B)", "(3010,0076)")),
    (
        "RT Patient Position Acquisition Instruction",
        ("(3002,0118)", "(3002,011A)", "(3002,0132)"),
    ),
}
STUDY = "1.2.826.0.1.3680043.10.189.1"
SERIES = "1.2.826.0.1.3680043.10.189.2"
IMAGE = "1.2.826.0.1.3680043.10.189.4"
CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
SENTINEL = "SENTINEL"


def _number(tag):
    return int(tag[1:5] + tag[6:10], 16)


def _study_item(*, extra=False):
    """Return an item of Referenced Study Sequence as the macro defines it.

    ``extra`` adds two attributes that the macro does not define in the
    item: Referenced SOP Instance UID and Study Description.
    """
    image = pydicom.Dataset()
    image.ReferencedSOPClassUID = CT_IMAGE_STORAGE
    image.ReferencedSOPInstanceUID = IMAGE
    series = pydicom.Dataset()
    series.SeriesInstanceUID = SERIES
    series.ReferencedImageSequence = pydicom.Sequence([image])
    item = pydicom.Dataset()
    item.StudyInstanceUID = STUDY
    item.add_new(_number(PERTINENT_SOP_CLASSES_IN_STUDY), "UI", [CT_IMAGE_STORAGE])
    item.ReferencedSeriesSequence = pydicom.Sequence([series])
    if extra:
        item.ReferencedSOPInstanceUID = "1.2.826.0.1.3680043.10.189.5"
        item.StudyDescription = f"{SENTINEL} STUDY"
    return item


def _intent(*items):
    """Return an RT Physician Intent whose one input instance names a study.

    Its header holds the Patient, General Study, and General Series Modules'
    identifiers; the instance does not hold every attribute that its IOD
    requires, as the synthetic corpus's do not.
    """
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = RT_PHYSICIAN_INTENT_STORAGE
    dataset.SOPInstanceUID = "1.2.826.0.1.3680043.10.189.3"
    dataset.PatientName = f"{SENTINEL}^PATIENT"
    dataset.PatientID = f"{SENTINEL}-PID"
    dataset.StudyInstanceUID = STUDY
    dataset.SeriesInstanceUID = "1.2.826.0.1.3680043.10.189.6"
    dataset.Modality = "RTINTENT"
    purpose = pydicom.Dataset()
    purpose.CodeValue = "121311"
    purpose.CodingSchemeDesignator = "DCM"
    purpose.CodeMeaning = "Localizer"
    instance = pydicom.Dataset()
    instance.PurposeOfReferenceCodeSequence = pydicom.Sequence([purpose])
    instance.ReferencedStudySequence = pydicom.Sequence(list(items))
    intent = pydicom.Dataset()
    intent.add_new(_number(INPUT_INSTANCE), "SQ", pydicom.Sequence([instance]))
    dataset.add_new(_number(INTENT_SEQUENCE), "SQ", pydicom.Sequence([intent]))
    return dataset


def _plan(dataset, options=()):
    source = read_source(synthetic.written(dataset))
    rules = ElementRules(policy.compose_custom_policy(options))
    return plan_instance(source, rules, load_iod_tables().iods[INTENT])


def _in_item(index, tag, *deeper):
    return ElementPath(
        ((INTENT_SEQUENCE, 0), (INPUT_INSTANCE, 0), (REFERENCED_STUDY, index), *deeper),
        tag,
    )


def test_x_z_resolves_to_d_only_where_the_macro_makes_the_sequence_type_1():
    # Every other place in the generated IODs is Type 2 or 3, where X/Z
    # resolves to Z or X, so the rule applies only at these three places.
    rows = {row.tag: row for row in standard.load_table_e1_1().attributes}
    assert rows[REFERENCED_STUDY].basic_profile == "X/Z"
    assert dict(rows[REFERENCED_STUDY].options) == {"retain_uids": "K"}
    found = {
        (name, definition.path)
        for name, iod in load_iod_tables().iods.items()
        for definition in iod.definitions
        if definition.tag == REFERENCED_STUDY
        and compound_actions.resolve_in_iod(
            iod, REFERENCED_STUDY, definition.path, "X/Z"
        )
        == "D"
    }
    assert found == TYPE_1_PLACES


def test_the_rule_keeps_the_attributes_that_the_macro_defines_in_an_item():
    kept = dummy_values.KEPT_ITEM_ATTRIBUTES[REFERENCED_STUDY]
    tables = load_iod_tables()
    for name, path in TYPE_1_PLACES:
        iod = tables.iods[name]
        inside = (*path, REFERENCED_STUDY)
        defined = {
            definition.tag
            for definition in iod.definitions
            if definition.path == inside
        }
        assert defined == kept, (name, path)
    assert kept == {
        STUDY_INSTANCE_UID,
        PERTINENT_SOP_CLASSES_IN_STUDY,
        REFERENCED_SERIES,
    }
    # Its items' attributes stay its own: the rule writes no items.
    with pytest.raises(dummy_values.NoDummyValueError):
        dummy_values.items_for_d(REFERENCED_STUDY, [], KEY)


@pytest.mark.deid_requirement("PS3.15-E.1.1-04", "MIDI-BP-03")
def test_d_keeps_each_item_with_only_its_reviewed_attributes():
    plan = _plan(_intent(_study_item(), _study_item(extra=True)))
    planned = {element.path: element for element in plan.elements}

    assert not [s for s in plan.sequestrations if REFERENCED_STUDY in str(s.path)]
    study = planned[
        ElementPath(((INTENT_SEQUENCE, 0), (INPUT_INSTANCE, 0)), REFERENCED_STUDY)
    ]
    assert (study.rule.action, study.action) == ("X/Z", "D")
    assert study.removed_with is None
    for index in (0, 1):
        assert planned[_in_item(index, STUDY_INSTANCE_UID)].action == "U"
        assert planned[_in_item(index, REFERENCED_SERIES)].action == "K"
        assert planned[_in_item(index, PERTINENT_SOP_CLASSES_IN_STUDY)].action == "U"
        series = (REFERENCED_SERIES, 0)
        assert planned[_in_item(index, SERIES_INSTANCE_UID, series)].action == "U"
        # X/Z/U* on Referenced Image Sequence, Type 3 there, removes it.
        assert planned[_in_item(index, REFERENCED_IMAGE, series)].action == "X"
    # The attributes that the macro does not define in the item are removed,
    # whatever their own rules.
    for tag in (REFERENCED_SOP_INSTANCE_UID, STUDY_DESCRIPTION):
        extra = planned[_in_item(1, tag)]
        assert extra.action == "X"
        assert extra.rule.source is RuleSource.ENGINE


def test_retain_uids_keeps_the_sequence():
    plan = _plan(_intent(_study_item()), ("retain_uids",))
    planned = {element.path: element.action for element in plan.elements}

    path = ElementPath(((INTENT_SEQUENCE, 0), (INPUT_INSTANCE, 0)), REFERENCED_STUDY)
    assert planned[path] == "K"
    assert planned[_in_item(0, STUDY_INSTANCE_UID)] == "K"


@pytest.mark.deid_requirement("PS3.15-E.1.1-04")
def test_the_written_intent_names_the_written_study():
    data = synthetic.written(_intent(_study_item(), _study_item(extra=True)))
    transform = InstanceTransform(
        policy.compose_custom_policy(()), KEY, unvalidated_policy=True
    )
    result = transform(data, InstanceRecord.from_file(data))
    assert isinstance(result, run.Transformed), result
    assert SENTINEL.encode() not in result.data
    written = pydicom.dcmread(io.BytesIO(result.data))

    (intent,) = written[_number(INTENT_SEQUENCE)].value
    (instance,) = intent[_number(INPUT_INSTANCE)].value
    items = instance.ReferencedStudySequence
    assert len(items) == 2
    kept = {_number(tag) for tag in dummy_values.KEPT_ITEM_ATTRIBUTES[REFERENCED_STUDY]}
    for item in items:
        assert {element.tag for element in item} == kept
        assert item.StudyInstanceUID == replacement_uid(KEY, STUDY)
        assert item.StudyInstanceUID == written.StudyInstanceUID
        (series,) = item.ReferencedSeriesSequence
        assert series.SeriesInstanceUID == replacement_uid(KEY, SERIES)
        assert "ReferencedImageSequence" not in series
