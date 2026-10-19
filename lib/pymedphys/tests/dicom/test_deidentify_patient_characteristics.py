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

"""The Retain Patient Characteristics Option, applied end to end.

Every file is synthetic. Values that must never reach a written file carry
the text ``SENTINEL``.
"""

import io

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    cleaners,
    conformance,
    conformance_markdown,
    patient_characteristics,
    run,
)
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.edits import Edit, EditKind, InstanceEdits
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    TransformReason,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import (
    PATIENT_CHARACTERISTICS,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.reasons import DescriptorReason
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.reviewed_descriptors import (
    ReviewedDescriptor,
    ReviewedDescriptors,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import Review, ReviewedNames
from pymedphys._dicom.deidentify.standard import load_table_e1_1

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
PATIENT_CHARACTERISTICS_CODE = "113108"
CLEAN_DESCRIPTORS_CODE = "113105"
_ALLERGIES = ElementPath((), "(0010,2110)")
_SEX_PARAMETERS = 0x00100043
_SEX_PARAMETERS_COMMENT = 0x00100042
_SEX_PARAMETERS_REFERENCE = 0x00100047
# Each kept attribute of the Option that a plan can carry at the top level,
# by keyword, with a synthetic value.
_KEPT = {
    "PatientAge": "045Y",
    "PatientSex": "O",
    "PatientSexNeutered": "ALTERED",
    "PatientSize": "1.72",
    "PatientWeight": "68.5",
    "EthnicGroup": "SENTINEL GROUP",
    "SmokingStatus": "NO",
    "PregnancyStatus": 4,
}
# Ethnic Groups, which pydicom's data dictionary does not name, with its VR
# and a synthetic value.
_ETHNIC_GROUPS = (0x00102162, "UC", ["SENTINEL GROUP A", "SENTINEL GROUP B"])
# A value of each attribute that the Option gives C.
_FREE_TEXT = {
    "Allergies": "SENTINEL ALLERGY",
    "PatientState": "SENTINEL STATE",
    "PreMedication": "SENTINEL MEDICATION",
    "SpecialNeeds": "SENTINEL NEEDS",
}


def _rows(option_action):
    return {
        row.tag
        for row in load_table_e1_1().attributes
        if row.options.get(PATIENT_CHARACTERISTICS) == option_action
    }


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
def test_every_attribute_that_the_option_gives_c_has_a_cleaner():
    cleaned = {
        tag
        for cleaner in cleaners.CLEANERS
        if cleaner.option == PATIENT_CHARACTERISTICS
        for tag in cleaner.tags
    }

    assert _rows("C") == cleaned == patient_characteristics.TAGS
    # The Option gives every other attribute of its column K.
    assert len(_rows("K")) == 14


@pytest.mark.parametrize("source", ["", " ", "  \x00", "\\", " \\ \\"])
def test_an_attribute_with_no_value_or_only_padding_is_written_with_none(source):
    assert patient_characteristics.is_empty(source)
    value = SourceValue(_ALLERGIES, "LO", source)

    settled = patient_characteristics.held_unless_empty([value], KEY, None)

    assert settled == {_ALLERGIES: ((), False)}


@pytest.mark.parametrize(
    "source", ["SENTINEL", " SENTINEL ", "\\SENTINEL", "SENTINEL\\", "NONE"]
)
def test_an_attribute_with_a_value_is_left_out(source):
    assert not patient_characteristics.is_empty(source)
    value = SourceValue(_ALLERGIES, "LO", source)

    assert not patient_characteristics.held_unless_empty([value], KEY, None)


def test_the_cleaner_leaves_a_value_that_it_cannot_clean_pending():
    edits = InstanceEdits(
        edits=(
            Edit(_ALLERGIES, "C", EditKind.PENDING),
            Edit(ElementPath((), "(0038,0500)"), "C", EditKind.PENDING),
        ),
        source_values=(
            SourceValue(_ALLERGIES, "LO", "SENTINEL ALLERGY"),
            SourceValue(ElementPath((), "(0038,0500)"), "LO", " "),
        ),
        not_collected=(),
        sequestrations=(),
    )
    option = cleaners.cleaners_for(compose_custom_policy([PATIENT_CHARACTERISTICS]))

    cleaned = cleaners.apply_cleaners(edits, option, KEY)

    allergies, state = cleaned.edits.edits
    assert allergies == edits.edits[0]
    assert (state.kind, state.values) == (EditKind.EMPTY, ())
    assert cleaned.retained == frozenset()


def _transform(options, cleaning=None):
    return InstanceTransform(
        compose_custom_policy(options), KEY, cleaning=cleaning, unvalidated_policy=True
    )


def _plan(**attributes):
    plan = synthetic.rt_plan()
    for keyword, value in attributes.items():
        setattr(plan, keyword, value)
    return plan


def _result(transform, dataset):
    data = synthetic.written(dataset)
    return transform(data, InstanceRecord.from_file(data))


def _written(transform, dataset):
    result = _result(transform, dataset)
    assert isinstance(result, run.Transformed), result
    return pydicom.dcmread(io.BytesIO(result.data))


def _collected(result):
    return {value.source for value in result.evidence.collected}


def _codes(dataset):
    return [item.CodeValue for item in dataset.DeidentificationMethodCodeSequence]


def _sex_parameters(comment):
    code = synthetic.item(
        CodeValue="SENTINEL-CODE", CodingSchemeDesignator="99SENTINEL"
    )
    code.CodeMeaning = "Synthetic"
    parameters = synthetic.item()
    parameters.add_new(0x00100046, "SQ", pydicom.Sequence([code]))
    parameters.add_new(_SEX_PARAMETERS_COMMENT, "UT", comment)
    parameters.add_new(_SEX_PARAMETERS_REFERENCE, "UR", "https://example.org/sentinel")
    return pydicom.Sequence([parameters])


@pytest.mark.deid_requirement("PS3.15-E.3.7-01")
def test_the_option_keeps_the_patients_characteristics():
    plan = _plan(**_KEPT)
    plan.add_new(*_ETHNIC_GROUPS)

    written = _written(_transform([PATIENT_CHARACTERISTICS]), plan)

    for keyword, value in _KEPT.items():
        assert written.get(keyword) == value, keyword
    tag, _, groups = _ETHNIC_GROUPS
    assert list(written[tag].value) == groups
    assert _codes(written) == ["113100", PATIENT_CHARACTERISTICS_CODE]

    basic = _written(
        InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True), plan
    )
    # The Basic Profile removes or empties each of them.
    for keyword in _KEPT:
        assert basic.get(keyword) in (None, ""), keyword
    assert tag not in basic
    assert PATIENT_CHARACTERISTICS_CODE not in _codes(basic)


@pytest.mark.deid_requirement("PS3.15-E.3.7-01")
def test_the_option_keeps_the_sex_parameters_and_writes_an_empty_comment_empty():
    plan = _plan()
    plan.add_new(_SEX_PARAMETERS, "SQ", _sex_parameters(""))

    written = _written(_transform([PATIENT_CHARACTERISTICS]), plan)

    (parameters,) = written[_SEX_PARAMETERS].value
    (code,) = parameters[0x00100046].value
    assert code.CodeValue == "SENTINEL-CODE"
    assert parameters[_SEX_PARAMETERS_REFERENCE].value == "https://example.org/sentinel"
    # Its comment is Type 2C there, so it is written with no value.
    assert parameters[_SEX_PARAMETERS_COMMENT].value in ("", None)
    assert _codes(written) == ["113100", PATIENT_CHARACTERISTICS_CODE]

    basic = _written(
        InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True), plan
    )
    assert _SEX_PARAMETERS not in basic


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
@pytest.mark.parametrize("keyword", sorted(_FREE_TEXT))
def test_an_attribute_of_free_text_with_a_value_holds_its_instance(keyword):
    result = _result(
        _transform([PATIENT_CHARACTERISTICS]),
        _plan(**{keyword: _FREE_TEXT[keyword]}),
    )

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.PENDING_EDIT,)


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
def test_a_sex_parameters_comment_with_a_value_holds_its_instance():
    plan = _plan()
    plan.add_new(_SEX_PARAMETERS, "SQ", _sex_parameters("SENTINEL COMMENT"))

    result = _result(_transform([PATIENT_CHARACTERISTICS]), plan)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.PENDING_EDIT,)


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
@pytest.mark.parametrize("keyword", sorted(_FREE_TEXT))
def test_an_attribute_of_free_text_with_no_value_is_written_with_none(keyword):
    written = _written(_transform([PATIENT_CHARACTERISTICS]), _plan(**{keyword: ""}))

    assert written[keyword].value in ("", None)
    assert _codes(written) == ["113100", PATIENT_CHARACTERISTICS_CODE]


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
def test_under_clean_descriptors_too_the_shared_attributes_are_settled_the_same():
    cleaning = DescriptorCleaning(None, ReviewedNames.empty())
    transform = _transform([PATIENT_CHARACTERISTICS, "clean_descriptors"], cleaning)

    # Clean Descriptors' fallback cannot remove a value that the Option
    # keeps, so a value still holds the instance, as an unsettled descriptor.
    held = _result(transform, _plan(Allergies="SENTINEL ALLERGY"))
    assert isinstance(held, run.Sequestered)
    assert held.reasons == (DescriptorReason.UNSETTLED_DESCRIPTOR,)

    written = _written(
        transform,
        _plan(Allergies="", PatientState=" ", PatientWeight="68.5"),
    )
    assert written.Allergies in ("", None)
    assert written.PatientState in ("", None)
    assert written.PatientWeight == "68.5"
    assert _codes(written) == [
        "113100",
        PATIENT_CHARACTERISTICS_CODE,
        CLEAN_DESCRIPTORS_CODE,
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
@pytest.mark.parametrize(
    "decision",
    [ReviewedDescriptor(Review.KEEP), ReviewedDescriptor(Review.MAP, "NONE")],
)
def test_a_reviewed_descriptor_decision_does_not_settle_the_shared_attributes(
    decision,
):
    reviewed = ReviewedDescriptors.empty()
    reviewed.record(_ALLERGIES.tag, "SENTINEL ALLERGY", decision)
    cleaning = DescriptorCleaning(
        None, ReviewedNames.empty(), reviewed_descriptors=reviewed
    )
    transform = _transform([PATIENT_CHARACTERISTICS, "clean_descriptors"], cleaning)

    held = _result(
        transform, _plan(Allergies="SENTINEL ALLERGY", SeriesDescription="AXIAL CHEST")
    )

    # The reviewed descriptors list is Clean Descriptors', and does not
    # clean what the Option's cleaner leaves, which still holds the instance.
    assert isinstance(held, run.Sequestered)
    assert held.reasons == (DescriptorReason.UNSETTLED_DESCRIPTOR,)
    # The refused instance still leaves out of its subject's search a
    # descriptor that cleaning would keep, but not the Option's attribute.
    collected = _collected(held)
    assert _ALLERGIES in collected
    assert ElementPath((), "(0008,103E)") not in collected


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
@pytest.mark.parametrize(
    "options",
    [[PATIENT_CHARACTERISTICS], [PATIENT_CHARACTERISTICS, "clean_descriptors"]],
)
def test_the_statement_describes_how_the_free_text_is_settled(options):
    statement = conformance.conformance_statement(
        compose_custom_policy(options), vocabulary=None
    )

    (cleaned,) = statement.cleaned
    (cleaner,) = (c for c in cleaners.CLEANERS if c.option == PATIENT_CHARACTERISTICS)
    assert cleaned == conformance.CleanedAttributes(
        PATIENT_CHARACTERISTICS,
        tuple(sorted(patient_characteristics.TAGS)),
        cleaner.method,
    )
    assert conformance.PENDING_CLEANING not in statement.pending
    text = conformance_markdown.render_markdown(statement)
    heading = "## Cleaning under the Retain Patient Characteristics Option"
    section = text.split(heading)[1].split("\n## ")[0]
    assert "Allergies (0010,2110)" in section
    assert "is held" in section
    assert cleaner.method in section


def test_tps_import_describes_the_free_text():
    statement = conformance.conformance_statement(
        compose_policy("tps-import"), vocabulary=None
    )

    assert PATIENT_CHARACTERISTICS in [c.option for c in statement.cleaned]
