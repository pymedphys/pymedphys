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

"""Clean Descriptors in the transform: ROI Names cleaned or held, others not."""

import dataclasses
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._nomenclature import tg263

from pymedphys._dicom.deidentify import (
    descriptor_cleaning,
    instance_transform,
    qc_pack,
    roi_names,
    run,
    run_qc,
    synthetic_corpus,
)
from pymedphys._dicom.deidentify.descriptor_cleaning import (
    DescriptorCleaning,
    DescriptorReason,
    DescriptorsRefused,
    HeldRoiName,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.method_digest import method_digest
from pymedphys._dicom.deidentify.policy import PolicyError, compose_policy
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.reviewed_roi_names import (
    Review,
    ReviewedName,
    ReviewedNames,
)
from pymedphys._dicom.deidentify.roi_names import Reason

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
CLEAN_DESCRIPTORS_CODE = ("113105", "DCM")
_NOMENCLATURE = tg263.Nomenclature(
    source=tg263.Source(file="invented.xls", sha256="0" * 64, sheet="Invented"),
    attribution=tg263.ATTRIBUTION,
    structures=(
        tg263.Structure(
            target_type="Anatomic",
            major_category="Invented",
            minor_category="",
            anatomic_group="",
            primary_name="Lung_L",
            reverse_order_name="L_Lung",
            description="",
            fma_id=None,
        ),
    ),
)


@pytest.fixture(name="published", autouse=True)
def _published(monkeypatch):
    entries = [dataclasses.asdict(s) for s in _NOMENCLATURE.structures]
    monkeypatch.setitem(
        roi_names.PUBLISHED_TG263, "TG263 vInvented", tg263.content_sha256(entries)
    )


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _reviewed(**decisions):
    names = ReviewedNames.empty()
    for name, decision in decisions.items():
        names.record(name, decision)
    return names


def _transform(reviewed=None, empty_held=False):
    cleaning = DescriptorCleaning(
        _NOMENCLATURE,
        ReviewedNames.empty() if reviewed is None else reviewed,
        empty_held=empty_held,
    )
    return InstanceTransform(
        compose_policy("basic-clean-descriptors"),
        KEY,
        cleaning=cleaning,
        unvalidated_policy=True,
    )


def _structure_set(*names, **elements):
    dataset = synthetic.structure_set()
    items = []
    for number, name in enumerate(names, start=1):
        item = pydicom.Dataset()
        item.ROINumber = number
        item.ROIName = name
        items.append(item)
    dataset.StructureSetROISequence = pydicom.Sequence(items)
    for keyword, value in elements.items():
        setattr(dataset, keyword, value)
    return dataset


def _transformed(transform, dataset):
    data = synthetic.written(dataset)
    return transform(data, InstanceRecord.from_file(data))


def _codes(written):
    # An item already present may hold a Long or URN Code Value instead.
    return [
        (item.get("CodeValue"), item.get("CodingSchemeDesignator"))
        for item in written.DeidentificationMethodCodeSequence
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_roi_names_are_renamed_or_given_their_reviewed_decision():
    transform = _transform(
        _reviewed(
            PTV_CUSTOM=ReviewedName(Review.KEEP),
            GTV1=ReviewedName(Review.MAP, "GTVp"),
        )
    )
    result = _transformed(transform, _structure_set("lung_l", "PTV_CUSTOM", "GTV1"))

    assert isinstance(result, run.Transformed)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert [item.ROIName for item in written.StructureSetROISequence] == [
        "Lung_L",
        "PTV_CUSTOM",
        "GTVp",
    ]
    assert CLEAN_DESCRIPTORS_CODE in _codes(written)
    assert not transform.review_queue.entries()


def test_retained_roi_names_are_left_out_of_the_residual_search(tmp_path):
    datasets = [
        _structure_set("PTV_CUSTOM") if index == 3 else dataset
        for index, dataset in enumerate(synthetic.collection())
    ]
    source = tmp_path / "source"
    source.mkdir()
    for position, dataset in enumerate(datasets):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))
    transform = _transform(_reviewed(PTV_CUSTOM=ReviewedName(Review.KEEP)))

    result = run.run(
        run.discover(source),
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )

    assert [outcome.status for outcome in result.outcomes] == [run.Status.RELEASED] * 6
    # Each kept ROI Name is a drop that the QC pack lists (D-027).
    drops = json.loads(result.qc_pack.read_text(encoding="utf-8"))["drops"]
    assert any(
        drop["position"] == 3
        and drop["reason"] == "retained"
        and drop["source"].endswith("(3006,0026)")
        for drop in drops
    )
    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    (name,) = pack["roi_names"]
    assert (name["position"], name["source"], name["outcome"]) == (
        3,
        "PTV_CUSTOM",
        "kept",
    )
    # Among the strings that each plan keeps as they are.
    (kept,) = [
        string for string in pack["retained_strings"] if string["value"] == "PTV_CUSTOM"
    ]
    assert [place["position"] for place in kept["places"]] == [3]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_roi_name_without_a_decision_holds_the_instance_for_review():
    transform = _transform()
    result = _transformed(transform, _structure_set("lung_l", "SURGEONS ROI"))

    assert isinstance(result, run.Transformed)
    assert isinstance(result.evidence, HeldEvidence)
    path = ElementPath((("(3006,0020)", 1),), "(3006,0026)")
    evidence = result.evidence
    assert isinstance(evidence, HeldEvidence)
    assert evidence.held == (HeldRoiName(path, Reason.UNMATCHED),)  # pylint: disable=no-member
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert [item.ROIName for item in written.StructureSetROISequence] == [
        "Lung_L",
        "",
    ]
    assert b"SURGEONS" not in result.data
    assert CLEAN_DESCRIPTORS_CODE not in _codes(written)
    (entry,) = transform.review_queue.entries()
    assert entry.reasons == frozenset({Reason.UNMATCHED})

    decision = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    assert isinstance(decision, run.HoldForReview)
    assert decision.reasons[0] == HeldRoiName(path, Reason.UNMATCHED)
    assert "SURGEONS" not in repr(decision) + repr(result)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_the_method_digest_and_the_report_cover_the_reviewed_names():
    reviewed = _reviewed(PTV_CUSTOM=ReviewedName(Review.KEEP))
    transform = _transform(reviewed)
    result = _transformed(transform, _structure_set("PTV_CUSTOM"))

    keyed = reviewed.keyed_digest(KEY)
    digest = method_digest(
        compose_policy("basic-clean-descriptors"),
        vocabulary=_NOMENCLATURE,
        reviewed_roi_names=keyed,
    )
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert list(written.DeidentificationMethod)[:1] == [digest]
    report = transform.reporter((), {}, qc_pack.new_reference())
    method = json.loads(report)["method"]
    assert (method["method_digest"], method["reviewed_roi_names"]) == (digest, keyed)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_decisions_recorded_after_the_transform_is_made_do_not_apply():
    reviewed = ReviewedNames.empty()
    transform = _transform(reviewed)
    reviewed.record("PTV_CUSTOM", ReviewedName(Review.MAP, "GTVp"))

    for _ in range(2):
        result = _transformed(transform, _structure_set("PTV_CUSTOM"))
        assert isinstance(result, run.Transformed)
        assert isinstance(result.evidence, HeldEvidence)
        reviewed.record("GTV1", ReviewedName(Review.KEEP))

    method = json.loads(transform.reporter((), {}, qc_pack.new_reference()))["method"]
    assert method["reviewed_roi_names"] == ReviewedNames.empty().keyed_digest(KEY)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01", "MIDI-BP-17")
def test_a_run_holds_the_structure_set_and_releases_the_rest(tmp_path):
    datasets = [
        _structure_set("SURGEONS ROI") if index == 3 else dataset
        for index, dataset in enumerate(synthetic.collection())
    ]
    source = tmp_path / "source"
    source.mkdir()
    for position, dataset in enumerate(datasets):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))

    result = run.run(
        run.discover(source),
        tmp_path / "release",
        _transform(),
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )

    statuses = [outcome.status for outcome in result.outcomes]
    assert (
        statuses
        == [run.Status.RELEASED] * 3
        + [run.Status.HELD_FOR_REVIEW]
        + [run.Status.RELEASED] * 2
    )
    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    (name,) = pack["roi_names"]
    assert (name["source"], name["outcome"], name["written"]) == (
        "SURGEONS ROI",
        "held",
        None,
    )
    assert name["held_because"]
    assert pack["instances"][3]["disposition"] == "held-for-review"


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_held_names_are_emptied_where_the_user_chooses_so():
    transform = _transform(empty_held=True)
    result = _transformed(transform, _structure_set("SURGEONS ROI"))

    assert isinstance(result, run.Transformed)
    assert not isinstance(result.evidence, HeldEvidence)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.StructureSetROISequence[0].ROIName == ""
    assert CLEAN_DESCRIPTORS_CODE not in _codes(written)
    (entry,) = transform.review_queue.entries()
    assert entry.reasons == frozenset({Reason.UNMATCHED})


@pytest.mark.deid_requirement("PS3.15-E.3.5-01", "MIDI-BP-11")
def test_a_kept_name_that_echoes_the_patient_is_held():
    surname = synthetic.PATIENTS_NAME.split("^")[0]
    transform = _transform(_reviewed(**{surname: ReviewedName(Review.KEEP)}))
    result = _transformed(transform, _structure_set(surname))

    evidence = result.evidence
    assert isinstance(evidence, HeldEvidence)
    assert evidence.held[0].reason is Reason.ECHOES_IDENTIFIER  # pylint: disable=no-member


@pytest.mark.deid_requirement("PS3.15-E.3.5-01", "PS3.15-E.3.5-02")
def test_other_descriptors_take_their_basic_profile_action_and_keep_the_claim():
    # PS3.15 E.3.5 specifies what the option removes, not what it retains,
    # and E.1.1 makes Table E.1-1 the minimum actions, so a descriptor that
    # takes its Basic Profile action instead of being cleaned still meets it.
    result = _transformed(
        _transform(),
        _structure_set(
            "lung_l",
            StudyDescription="SENTINEL STUDY",
            StructureSetLabel="SENTINEL LABEL",
        ),
    )

    assert isinstance(result, run.Transformed)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert "StudyDescription" not in written
    # Type 1, so D writes a dummy value rather than removing it.
    assert written.StructureSetLabel
    assert b"SENTINEL" not in result.data
    assert written.StructureSetROISequence[0].ROIName == "Lung_L"
    assert CLEAN_DESCRIPTORS_CODE in _codes(written)
    assert ("113100", "DCM") in _codes(written)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_descriptor_that_the_fallback_keeps_loses_the_claim(monkeypatch):
    fallen_back = descriptor_cleaning._fallen_back  # pylint: disable=protected-access

    def kept(others, fallback):
        return {
            path: dataclasses.replace(edit, kind=descriptor_cleaning.EditKind.KEEP)
            for path, edit in fallen_back(others, fallback).items()
        }

    monkeypatch.setattr(descriptor_cleaning, "_fallen_back", kept)

    result = _transformed(
        _transform(),
        _structure_set("lung_l", StudyDescription="SENTINEL STUDY"),
    )

    assert isinstance(result, run.Transformed)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.StudyDescription == "SENTINEL STUDY"
    assert CLEAN_DESCRIPTORS_CODE not in _codes(written)


# The corpus plants markers in UI elements, which pydicom warns of on reading.
@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.filterwarnings("ignore:Invalid value for VR UI:UserWarning")
def test_the_synthetic_rt_plan_claims_the_option():
    # Its RT Plan Label, which is Type 1, and its other descriptors given C
    # take their Basic Profile actions.
    (plan,) = [
        file
        for file in synthetic_corpus.build_corpus().files
        if file.manifest.iod == "RT Plan"
    ]

    result = _transform()(plan.data, InstanceRecord.from_file(plan.data))

    assert isinstance(result, run.Transformed)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.RTPlanLabel
    assert CLEAN_DESCRIPTORS_CODE in _codes(written)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_roi_name_that_was_not_collected_sequesters_its_instance(monkeypatch):
    path = ElementPath((("(3006,0020)", 0),), "(3006,0026)")
    collect = instance_transform.edit_instance

    def without_the_name(*args):
        edits = collect(*args)
        return dataclasses.replace(
            edits,
            source_values=tuple(
                value for value in edits.source_values if value.source != path
            ),
        )

    monkeypatch.setattr(instance_transform, "edit_instance", without_the_name)
    transform = _transform()

    result = _transformed(transform, _structure_set("lung_l"))

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (DescriptorReason.UNDECODABLE_ROI_NAME,)
    assert not transform.review_queue.entries()


def test_a_refused_instance_adds_nothing_to_the_review(monkeypatch):
    def refuse(*_):
        raise DescriptorsRefused(DescriptorReason.UNSETTLED_DESCRIPTOR)

    monkeypatch.setattr(descriptor_cleaning, "_fallen_back", refuse)
    transform = _transform()

    result = _transformed(
        transform,
        _structure_set("SURGEONS ROI", StudyDescription="SENTINEL STUDY"),
    )

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (DescriptorReason.UNSETTLED_DESCRIPTOR,)
    assert not transform.review_queue.entries()


def test_only_kept_and_renamed_names_are_left_out_of_the_search():
    transform = _transform(
        _reviewed(
            PTV_CUSTOM=ReviewedName(Review.KEEP),
            GTV1=ReviewedName(Review.MAP, "GTVp"),
        )
    )

    result = _transformed(transform, _structure_set("lung_l", "PTV_CUSTOM", "GTV1"))

    assert isinstance(result, run.Transformed)
    dropped = {
        str(item.source)
        for item in result.qc
        if isinstance(item, run_qc.Dropped) and item.reason.value == "retained"
    }
    names = [str(ElementPath((("(3006,0020)", i),), "(3006,0026)")) for i in range(3)]
    # A mapped name's source is still searched for.
    assert dropped & set(names) == set(names[:2])


def test_cleaning_is_given_exactly_when_the_policy_selects_clean_descriptors():
    cleaning = DescriptorCleaning(_NOMENCLATURE, ReviewedNames.empty())
    with pytest.raises(PolicyError, match="exactly when"):
        InstanceTransform(
            compose_policy("basic-clean-descriptors"), KEY, unvalidated_policy=True
        )
    with pytest.raises(PolicyError, match="exactly when"):
        InstanceTransform(
            compose_policy("basic"), KEY, cleaning=cleaning, unvalidated_policy=True
        )


def test_cleaning_shows_neither_its_vocabulary_nor_its_names():
    cleaning = DescriptorCleaning(
        _NOMENCLATURE, _reviewed(SENTINEL=ReviewedName(Review.KEEP))
    )

    assert "SENTINEL" not in repr(cleaning)
    assert "Lung" not in repr(cleaning)


def test_cleaning_refuses_a_vocabulary_that_is_not_published(monkeypatch):
    monkeypatch.delitem(roi_names.PUBLISHED_TG263, "TG263 vInvented")

    with pytest.raises(ValueError):
        DescriptorCleaning(_NOMENCLATURE, ReviewedNames.empty())
