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

from pymedphys._dicom.deidentify import roi_names, run
from pymedphys._dicom.deidentify.descriptor_cleaning import (
    DescriptorCleaning,
    HeldRoiName,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
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
    return [
        (item.CodeValue, item.CodingSchemeDesignator)
        for item in written.DeidentificationMethodCodeSequence
    ]


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


def test_a_kept_name_that_echoes_the_patient_is_held():
    surname = synthetic.PATIENTS_NAME.split("^")[0]
    transform = _transform(_reviewed(**{surname: ReviewedName(Review.KEEP)}))
    result = _transformed(transform, _structure_set(surname))

    evidence = result.evidence
    assert isinstance(evidence, HeldEvidence)
    assert evidence.held[0].reason is Reason.ECHOES_IDENTIFIER  # pylint: disable=no-member


def test_other_descriptors_take_their_basic_profile_action_and_lose_the_claim():
    result = _transformed(
        _transform(),
        _structure_set("lung_l", StudyDescription="SENTINEL STUDY"),
    )

    assert isinstance(result, run.Transformed)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert "StudyDescription" not in written
    assert b"SENTINEL" not in result.data
    assert written.StructureSetROISequence[0].ROIName == "Lung_L"
    assert CLEAN_DESCRIPTORS_CODE not in _codes(written)
    assert ("113100", "DCM") in _codes(written)


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
