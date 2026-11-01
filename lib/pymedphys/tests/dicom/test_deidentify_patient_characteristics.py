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
import json
import os
import shutil
import tempfile
from pathlib import Path

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
    HeldEvidence,
    InstanceTransform,
    ReleaseGate,
    TransformReason,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import (
    PATIENT_CHARACTERISTICS,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.reasons import DescriptorReason, HeldDescriptor
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.reviewed_descriptors import (
    Held,
    Outcome,
    ReviewedDescriptor,
    ReviewedDescriptors,
    descriptor_vr,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import Review, ReviewedNames
from pymedphys._dicom.deidentify.run_qc import DescriptorMaterial
from pymedphys._dicom.deidentify.run_report import RELEASE_REPORT
from pymedphys._dicom.deidentify.standard import load_table_e1_1

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


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


def _cleaning(*decisions):
    reviewed = ReviewedDescriptors.empty()
    for tag, value, decision in decisions:
        reviewed.record(tag, value, decision)
    return DescriptorCleaning(
        None, ReviewedNames.empty(), reviewed_descriptors=reviewed
    )


def _both(*decisions):
    return _transform(
        [PATIENT_CHARACTERISTICS, "clean_descriptors"], _cleaning(*decisions)
    )


def _held(result):
    """Return why review holds a written instance."""
    assert isinstance(result, run.Transformed), result
    evidence = result.evidence
    assert isinstance(evidence, HeldEvidence)
    return evidence.held  # pylint: disable = no-member


def _path(keyword):
    tag = pydicom.datadict.tag_for_keyword(keyword)
    return ElementPath((), f"({tag >> 16:04X},{tag & 0xFFFF:04X})")


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
def test_under_clean_descriptors_too_empty_values_are_written_with_none():
    written = _written(
        _both(), _plan(Allergies="", PatientState=" ", PatientWeight="68.5")
    )

    assert written.Allergies in ("", None)
    assert written.PatientState in ("", None)
    assert written.PatientWeight == "68.5"
    assert _codes(written) == [
        "113100",
        PATIENT_CHARACTERISTICS_CODE,
        CLEAN_DESCRIPTORS_CODE,
    ]


def test_a_reviewer_can_decide_on_each_attribute_of_free_text():
    for tag in patient_characteristics.TAGS:
        assert descriptor_vr(tag) in patient_characteristics.VRS
    (cleaner,) = (c for c in cleaners.CLEANERS if c.option == PATIENT_CHARACTERISTICS)
    assert cleaner.reviewed
    with pytest.raises(ValueError, match="cannot decide"):
        cleaners.Cleaner(
            option=PATIENT_CHARACTERISTICS,
            tags=frozenset({"(0010,1030)"}),  # Patient's Weight, DS
            vrs=frozenset({"DS"}),
            method="",
            clean_instance=patient_characteristics.held_unless_empty,
            reviewed=True,
        )


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
@pytest.mark.parametrize("keyword", sorted(_FREE_TEXT))
@pytest.mark.parametrize(
    "decision, written",
    [
        (ReviewedDescriptor(Review.KEEP), None),
        (ReviewedDescriptor(Review.MAP, "NONE KNOWN"), "NONE KNOWN"),
        (ReviewedDescriptor(Review.EMPTY), ""),
    ],
)
def test_under_clean_descriptors_a_reviewed_decision_settles_the_free_text(
    keyword, decision, written
):
    value = _FREE_TEXT[keyword]
    path = _path(keyword)
    transform = _both((path.tag, value, decision))

    result = _result(transform, _plan(**{keyword: value}))

    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    dataset = pydicom.dcmread(io.BytesIO(result.data))
    assert (dataset[keyword].value or "") == (value if written is None else written)
    assert _codes(dataset) == [
        "113100",
        PATIENT_CHARACTERISTICS_CODE,
        CLEAN_DESCRIPTORS_CODE,
    ]
    # A kept value is retained, so its source is left out of the subject's
    # search; a mapped or emptied value's source is still searched for.
    assert (path in _collected(result)) is (written is not None)
    # The QC pack's material lists what was written.
    (material,) = (
        item
        for item in result.qc
        if isinstance(item, DescriptorMaterial) and item.path == path
    )
    assert material.applied
    assert not material.holds


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
@pytest.mark.parametrize("keyword", sorted(_FREE_TEXT))
def test_under_clean_descriptors_an_unreviewed_value_holds_the_instance(keyword):
    value = _FREE_TEXT[keyword]
    path = _path(keyword)

    result = _result(_both(), _plan(**{keyword: value}))

    assert _held(result) == (HeldDescriptor(path, Held.UNREVIEWED),)
    evidence = result.evidence
    # Written empty in the staged file, which is not released.
    assert b"SENTINEL" not in result.data
    dataset = pydicom.dcmread(io.BytesIO(result.data))
    assert dataset[keyword].value in ("", None)
    assert CLEAN_DESCRIPTORS_CODE not in _codes(dataset)
    (material,) = (
        item
        for item in result.qc
        if isinstance(item, DescriptorMaterial) and item.path == path
    )
    assert material.sources == (value,)
    assert [r.outcome for r in material.results] == [Outcome.HELD]
    assert (material.applied, material.holds) == (False, True)

    decision = ReleaseGate()(result.data, evidence, (evidence,))
    assert isinstance(decision, run.HoldForReview)
    assert HeldDescriptor(path, Held.UNREVIEWED) in decision.reasons
    assert "SENTINEL" not in repr(decision) + repr(result)


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
def test_an_unreviewed_sex_parameters_comment_holds_the_instance():
    plan = _plan()
    plan.add_new(_SEX_PARAMETERS, "SQ", _sex_parameters("SENTINEL COMMENT"))

    result = _result(_both(), plan)

    path = ElementPath((("(0010,0043)", 0),), "(0010,0042)")
    assert _held(result) == (HeldDescriptor(path, Held.UNREVIEWED),)
    assert b"SENTINEL COMMENT" not in result.data


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
def test_a_decision_that_echoes_an_identifier_holds_the_instance():
    value = "PENICILLIN PER FICTITIOUS"
    transform = _both((_ALLERGIES.tag, value, ReviewedDescriptor(Review.KEEP)))

    result = _result(transform, _plan(Allergies=value))

    assert _held(result) == (HeldDescriptor(_ALLERGIES, Held.ECHOES_IDENTIFIER),)
    assert b"PENICILLIN" not in result.data


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
def test_a_kept_value_beside_a_mapped_one_sequesters_the_instance():
    transform = _both(
        (_ALLERGIES.tag, "SENTINEL ALLERGY", ReviewedDescriptor(Review.KEEP)),
        (_ALLERGIES.tag, "SENTINEL OTHER", ReviewedDescriptor(Review.MAP, "OTHER")),
        ("(0038,0500)", "SENTINEL STATE", ReviewedDescriptor(Review.KEEP)),
    )

    held = _result(
        transform,
        _plan(
            Allergies=["SENTINEL ALLERGY", "SENTINEL OTHER"],
            PatientState="SENTINEL STATE",
        ),
    )

    # The residual search would leave out the mapped value's source with
    # the kept one's, so the element is not written.
    assert isinstance(held, run.Sequestered)
    assert held.reasons == (DescriptorReason.UNSETTLED_DESCRIPTOR,)
    # The refused instance still leaves out of its subject's search a value
    # that cleaning would keep, but not the element that it would not write.
    collected = _collected(held)
    assert _ALLERGIES in collected
    assert ElementPath((), "(0038,0500)") not in collected


@pytest.mark.deid_requirement("PS3.15-E.3.7-02")
def test_without_clean_descriptors_a_reviewed_value_still_sequesters():
    # Without Clean Descriptors, a run is given no reviewed descriptors list.
    result = _result(
        _transform([PATIENT_CHARACTERISTICS]), _plan(Allergies="SENTINEL ALLERGY")
    )

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.PENDING_EDIT,)


@pytest.mark.deid_requirement("PS3.15-E.3.7-02", "MIDI-BP-18")
def test_the_run_reports_an_instance_held_for_its_free_text_naming_no_value(
    tmp_path,
):
    datasets = [
        _plan(Allergies="SENTINEL ALLERGY") if index == 4 else dataset
        for index, dataset in enumerate(synthetic.collection())
    ]
    source = tmp_path / "source"
    source.mkdir()
    for position, dataset in enumerate(datasets):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))
    transform = _both()

    result = run.run(
        run.discover(source),
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
        reporter=transform.reporter,
    )

    statuses = [outcome.status for outcome in result.outcomes]
    assert statuses.count(run.Status.HELD_FOR_REVIEW) == 1
    text = (tmp_path / "release" / RELEASE_REPORT).read_text(encoding="utf-8")
    report = json.loads(text)
    assert report["format"] == "pymedphys-deid-release-report/33"
    assert {"stage": "descriptors", "code": "unreviewed", "count": 1} in report[
        "held_for_review"
    ]
    # The held element did not take its action without Clean Descriptors.
    assert report["descriptors"]["fell_back"] == 0
    assert {"reason": "unreviewed", "count": 1} in report["descriptors"]["held"]
    assert "SENTINEL" not in text
    # The confidential QC pack lists the value for a reviewer to decide on.
    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    (entry,) = (e for e in pack["descriptors"] if e["element"] == _ALLERGIES.tag)
    assert entry["applied"] is False


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
