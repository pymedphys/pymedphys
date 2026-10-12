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

"""The Retain UIDs Option: which UIDs are kept, and how kept UIDs are written.

Every file is synthetic, from the collection of
:mod:`~pymedphys.tests.dicom._synthetic_references`, whose UIDs are invented
under ``2.25.``. The tags that Table E.1-1 keeps under the option are read
from the generated table here, independently of the engine's policy.
"""

import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    release_report,
    run,
    run_report,
    standard,
    written_references,
)
from pymedphys._dicom.deidentify.element_rules import ElementRules, RuleSource
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
    TransformReason,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import (
    DEVICE_IDENTITY,
    ENGINE_OPTIONS,
    UIDS,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.qc_pack import DropReason
from pymedphys._dicom.deidentify.reference_graph import build_reference_graph
from pymedphys._dicom.deidentify.references import IDENTITY_TAGS, InstanceRecord
from pymedphys._dicom.deidentify.release_report_markdown import to_markdown
from pymedphys._dicom.deidentify.retained_uids import (
    output_name_uid,
    retained_uid_tags,
)
from pymedphys._dicom.deidentify.run_qc import Dropped
from pymedphys._dicom.deidentify.uids import replacement_uid

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
RETAIN_UIDS_CODE = "113110"
SOP_INSTANCE_UID = "(0008,0018)"
MULTI_FRAME_SOURCE = "(0008,1167)"
CONTENT_ITEM_UID = "(0040,A124)"
DIGITAL_SIGNATURE_UID = "(0400,0100)"
FRAME_OF_REFERENCE = "2.25.700"
# Run positions: the collection's CT slices, then its structure set, plan,
# and dose.
SLICES = (0, 1, 2)
STRUCTURE_SET, PLAN, DOSE = 3, 4, 5


def _rows_kept_under(option):
    return {
        row.tag: row
        for row in standard.load_table_e1_1().attributes
        if row.options.get(option) == "K"
    }


def _is_sequence(tag):
    attribute = standard.dictionary_attribute(tag)
    return attribute is not None and attribute.vrs == ("SQ",)


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    """On Windows, a directory whose path leaves room for a run's output names."""
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _transform(options=(UIDS,)):
    return InstanceTransform(
        compose_custom_policy(options), KEY, unvalidated_policy=True
    )


def _result(transform, dataset):
    data = synthetic.written(dataset)
    return transform(data, InstanceRecord.from_file(data))


def _written(transform, dataset):
    result = _result(transform, dataset)
    assert isinstance(result, run.Transformed), result
    return result, pydicom.dcmread(io.BytesIO(result.data))


def _codes(dataset):
    return [item.CodeValue for item in dataset.DeidentificationMethodCodeSequence]


def _plan(omitted=True):
    """The collection's RT Plan, in a frame of reference.

    With ``omitted``, it also has a UID that the table omits, which names
    the dose that the plan references.
    """
    plan = synthetic.rt_plan()
    synthetic.uid(plan, "FrameOfReferenceUID", FRAME_OF_REFERENCE)
    if omitted:
        synthetic.uid(plan, "MultiFrameSourceSOPInstanceUID", synthetic.DOSE)
    return plan


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
def test_the_engine_applies_the_option():
    assert UIDS in ENGINE_OPTIONS
    ElementRules(compose_custom_policy([UIDS]))


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
def test_the_kept_uids_are_the_tables_uids_under_the_option():
    rows = _rows_kept_under(UIDS)
    sequences = {tag for tag in rows if _is_sequence(tag)}

    tags = retained_uid_tags(compose_custom_policy([UIDS]))

    assert len(rows) == 60
    assert sequences == {
        "(0008,1110)",  # Referenced Study Sequence
        "(0008,1111)",  # Referenced Performed Procedure Step Sequence
        "(0008,1120)",  # Referenced Patient Sequence
        "(0008,1140)",  # Referenced Image Sequence
        "(0008,2112)",  # Source Image Sequence
    }
    assert tags == set(rows) - sequences
    assert len(tags) == 55
    assert all("UID" in rows[tag].name.split() for tag in tags)


def test_only_an_option_that_keeps_uids_has_kept_uids():
    assert not retained_uid_tags(compose_policy("basic"))
    assert not retained_uid_tags(compose_policy("basic-clean-descriptors"))
    # Retain Device Identity keeps the device's UIDs as well.
    assert retained_uid_tags(compose_custom_policy([DEVICE_IDENTITY])) == {
        "(0018,1002)",  # Device UID
        "(0018,100B)",  # Manufacturer's Device Class UID
    }


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
def test_the_rules_keep_the_tables_uids_and_replace_every_other():
    rules = ElementRules(compose_custom_policy([UIDS]))

    for tag in _rows_kept_under(UIDS):
        if tag[1:5] not in ("0000", "0002", "0004"):
            assert rules.rule(tag).action == "K", tag
    # The table gives these U under every option.
    for tag in (CONTENT_ITEM_UID, DIGITAL_SIGNATURE_UID):
        rule = rules.rule(tag)
        assert (rule.source, rule.action) == (RuleSource.TABLE, "U")
    # An instance UID that the table omits takes U by its role.
    rule = rules.rule(MULTI_FRAME_SOURCE)
    assert (rule.source, rule.action) == (RuleSource.UID_ROLE, "U")


@pytest.mark.deid_requirement("PS3.15-E.3.9-01", "PS3.15-E.1.1-04")
def test_an_instance_keeps_its_uids_and_references_and_claims_the_option():
    result, written = _written(_transform(), _plan())

    assert written.SOPInstanceUID == synthetic.PLAN
    assert written.SeriesInstanceUID == synthetic.PLAN_SERIES
    assert written.StudyInstanceUID == synthetic.STUDY
    assert written.FrameOfReferenceUID == FRAME_OF_REFERENCE
    assert (
        written.ReferencedStructureSetSequence[0].ReferencedSOPInstanceUID
        == synthetic.STRUCTURE_SET
    )
    assert written.ReferencedDoseSequence[0].ReferencedSOPInstanceUID == synthetic.DOSE
    # A UID that the table does not keep under the option is still replaced.
    assert written.MultiFrameSourceSOPInstanceUID == replacement_uid(
        KEY, synthetic.DOSE
    )
    # PS3.10 Section 7.1: the File Meta Information names the kept UID.
    assert written.file_meta.MediaStorageSOPInstanceUID == synthetic.PLAN
    assert _codes(written) == ["113100", RETAIN_UIDS_CODE]
    # The patient is still pseudonymised.
    assert synthetic.PATIENT_ID.encode() not in result.data


def test_an_instance_is_named_as_under_the_basic_profile_with_the_same_key():
    retained, _ = _written(_transform(), _plan())
    basic, _ = _written(
        InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True),
        _plan(),
    )

    assert retained.path == basic.path
    assert retained.path.stem == replacement_uid(KEY, synthetic.PLAN)
    assert synthetic.PLAN not in str(retained.path)


def test_a_kept_uid_names_output_by_its_keyed_replacement():
    assert output_name_uid(KEY, synthetic.PLAN, True) == replacement_uid(
        KEY, synthetic.PLAN
    )
    replaced = replacement_uid(KEY, synthetic.PLAN)
    assert output_name_uid(KEY, replaced, False) == replaced


# pydicom warns of the invalid UID that the test writes, and the engine
# redacts the value from the warning it passes on.
@pytest.mark.filterwarnings("ignore:Invalid value for VR UI")
def test_an_instance_whose_kept_sop_instance_uid_is_not_valid_is_sequestered():
    plan = _plan()
    # A component with a leading zero is not valid in VR UI (PS3.5 9.1).
    synthetic.uid(plan, "SOPInstanceUID", "2.25.0401")

    result = _result(_transform(), plan)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.UNNAMED_OUTPUT,)
    # The Basic Profile replaces it, so it names its output.
    basic = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)
    assert isinstance(_result(basic, plan), run.Transformed)


def _plan_with_a_request():
    """An RT Plan whose request repeats its Study Instance UID, and an ID."""
    plan = _plan(omitted=False)
    request = synthetic.item(RequestedProcedureID="SENTINEL REQUEST")
    synthetic.uid(request, "StudyInstanceUID", synthetic.STUDY)
    plan.RequestAttributesSequence = [request]
    return plan


@pytest.mark.deid_requirement("PS3.15-E.3.9-01")
def test_a_kept_uid_in_a_removed_sequence_is_left_out_of_the_search():
    removed_study = ElementPath(
        (("(0040,0275)", 0),), "(0020,000D)"
    )  # in Request Attributes Sequence
    request_id = ElementPath((("(0040,0275)", 0),), "(0040,1001)")

    result, written = _written(_transform(), _plan_with_a_request())

    # The Basic Profile removes the request; the option keeps the study's UID.
    assert "RequestAttributesSequence" not in written
    assert written.StudyInstanceUID == synthetic.STUDY
    collected = {value.source for value in result.evidence.collected}
    assert removed_study not in collected
    assert removed_study not in result.evidence.planned
    assert request_id in collected
    assert Dropped(removed_study, DropReason.RETAINED) in result.qc
    # So finding the study's UID where it is kept withholds nothing.
    verdict = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    assert isinstance(verdict, run.Release)


def test_under_the_basic_profile_the_removed_uid_is_still_searched_for():
    basic = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)
    removed_study = ElementPath((("(0040,0275)", 0),), "(0020,000D)")

    result, _ = _written(basic, _plan_with_a_request())

    assert removed_study in {value.source for value in result.evidence.collected}


def _source(tmp_path, datasets):
    source = tmp_path / "source"
    source.mkdir()
    for index, dataset in enumerate(datasets):
        (source / f"{index:03d}.dcm").write_bytes(synthetic.written(dataset))
    return source


def _run(tmp_path, datasets):
    transform = _transform()
    return run.run(
        run.discover(_source(tmp_path, datasets)),
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
        reporter=transform.reporter,
        written_check=transform.written_check,
    )


def _statuses(result):
    return {outcome.position: outcome.status for outcome in result.outcomes}


@pytest.mark.deid_requirement("PS3.15-E.3.9-01", "MIDI-BP-03")
def test_a_collection_keeps_its_uids_and_still_refers_to_itself(tmp_path):
    result = _run(tmp_path, synthetic.collection())

    assert set(_statuses(result).values()) == {run.Status.RELEASED}
    assert not result.written_findings
    published = {
        pydicom.dcmread(path).SOPInstanceUID for path in result.release.rglob("*.dcm")
    }
    assert published == {
        *synthetic.CT_SLICES,
        synthetic.STRUCTURE_SET,
        synthetic.PLAN,
        synthetic.DOSE,
    }
    report = (result.release / run_report.RELEASE_REPORT_MARKDOWN).read_text(
        encoding="utf-8"
    )
    assert "keep their source UIDs" in report


def _dose_extracted_from(sop_instance):
    dose = synthetic.rt_dose()
    extraction = pydicom.Dataset()
    synthetic.uid(extraction, "MultiFrameSourceSOPInstanceUID", sop_instance)
    dose.FrameExtractionSequence = [extraction]
    return dose


def test_a_reference_the_table_does_not_keep_cannot_name_a_kept_uid(tmp_path):
    # The dose's Multi-frame Source SOP Instance UID names the first CT
    # slice. The option keeps the slice's SOP Instance UID, but not the
    # reference, which is replaced, so its source value, found where the
    # slice and the structure set keep it, withholds both.
    datasets = synthetic.collection()
    datasets[DOSE] = _dose_extracted_from(synthetic.CT_SLICES[0])

    result = _run(tmp_path, datasets)

    statuses = _statuses(result)
    assert statuses[SLICES[0]] is run.Status.SEQUESTERED
    assert statuses[STRUCTURE_SET] is run.Status.SEQUESTERED
    assert {statuses[p] for p in (*SLICES[1:], PLAN, DOSE)} == {run.Status.RELEASED}
    # The dose's reference names an instance that was withheld.
    assert {finding.kind for finding in result.written_findings} == {
        written_references.WrittenFindingKind.UNWRITTEN_TARGET
    }


def _records(datasets):
    return {position: synthetic.record(each) for position, each in enumerate(datasets)}


def test_the_second_pass_expects_the_kept_uids_where_the_policy_keeps_them():
    inputs = synthetic.collection()
    graph = build_reference_graph([synthetic.record(each) for each in inputs])
    kept = retained_uid_tags(compose_custom_policy([UIDS]))
    # Written as they were given: every UID kept.
    written = _records(inputs)

    assert not written_references.verify_written_references(
        KEY, graph, written, retained=kept
    )
    # Without the kept UIDs, each instance's identifiers are source UIDs.
    findings = written_references.verify_written_references(KEY, graph, written)
    assert {finding.kind for finding in findings} == {
        written_references.WrittenFindingKind.ORIGINAL_UID
    }


def test_the_second_pass_reports_a_replacement_where_a_kept_uid_was_required():
    inputs = synthetic.collection()
    graph = build_reference_graph([synthetic.record(each) for each in inputs])
    kept = retained_uid_tags(compose_custom_policy([UIDS]))
    replaced = synthetic.collection()
    synthetic.uid(
        replaced[PLAN], "SOPInstanceUID", replacement_uid(KEY, synthetic.PLAN)
    )

    findings = written_references.verify_written_references(
        KEY, graph, _records(replaced), retained=kept
    )

    assert (
        written_references.WrittenFinding(
            written_references.WrittenFindingKind.MISMATCHED_IDENTIFIER,
            ((PLAN,),),
            (IDENTITY_TAGS[next(iter(IDENTITY_TAGS))],),
            1,
        )
        in findings
    )


def test_the_statement_says_what_keeping_uids_does_only_under_the_option():
    def integrity(policy):
        text = conformance_markdown.render_markdown(
            conformance.conformance_statement(policy, vocabulary=None)
        )
        return text.split("## Referential integrity")[1].split("\n## ")[0]

    kept = integrity(compose_custom_policy([UIDS]))
    assert "Under the Retain UIDs Option" in kept
    assert "Multi-frame Source SOP Instance UID (0008,1167)" in kept
    assert "Retain UIDs" not in integrity(compose_policy("basic"))


def test_the_release_report_cautions_that_kept_uids_link_to_the_source():
    def markdown(policy):
        report = release_report.release_report(
            policy, vocabulary=None, reviewed_roi_names=None
        )
        return to_markdown(release_report.to_json(report))

    kept = markdown(compose_custom_policy([UIDS]))
    assert "keep their source UIDs" in kept
    assert "PS3.15 E.3.9" in kept
    assert "source UIDs" not in markdown(compose_policy("basic"))
    document = json.loads(
        release_report.to_json(
            release_report.release_report(
                compose_custom_policy([UIDS]),
                vocabulary=None,
                reviewed_roi_names=None,
            )
        )
    )
    assert document["policy"]["options"] == [UIDS]
