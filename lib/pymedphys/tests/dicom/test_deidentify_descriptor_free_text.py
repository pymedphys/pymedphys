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

"""Clean Descriptors in the transform: free-text descriptors cleaned in two tiers."""

import io
import json
import os
import shutil
import tempfile
import types
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import descriptor_cleaning, qc_pack, run
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.method_digest import method_digest
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.qc_pack import DropReason
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.residuals import SourceValue
from pymedphys._dicom.deidentify.reviewed_descriptors import (
    ReviewedDescriptor,
    ReviewedDescriptors,
    descriptor_attributes,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import Review, ReviewedNames
from pymedphys._dicom.deidentify.run_qc import Dropped
from pymedphys._dicom.deidentify.run_report import RELEASE_REPORT
from pymedphys._dicom.deidentify.technique_descriptors import (
    load_technique_vocabulary,
)

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
CLEAN_DESCRIPTORS_CODE = ("113105", "DCM")
SERIES_DESCRIPTION = "(0008,103E)"
STUDY_DESCRIPTION = "(0008,1030)"
ADMITTING_DIAGNOSES = "(0008,1080)"
TOP = ElementPath((), SERIES_DESCRIPTION)
STUDY = ElementPath((), STUDY_DESCRIPTION)
DIAGNOSES = ElementPath((), ADMITTING_DIAGNOSES)


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _reviewed(*decisions):
    reviewed = ReviewedDescriptors.empty()
    for tag, value, review, *to in decisions:
        reviewed.record(tag, value, ReviewedDescriptor(review, *to))
    return reviewed


def _transform(reviewed=None, technique=...):
    extra = {} if technique is ... else {"technique": technique}
    cleaning = DescriptorCleaning(
        None,
        ReviewedNames.empty(),
        reviewed_descriptors=ReviewedDescriptors.empty()
        if reviewed is None
        else reviewed,
        **extra,
    )
    return InstanceTransform(
        compose_policy("basic-clean-descriptors"),
        KEY,
        cleaning=cleaning,
        unvalidated_policy=True,
    )


def _structure_set(**elements):
    dataset = synthetic.structure_set()
    for keyword, value in elements.items():
        setattr(dataset, keyword, value)
    return dataset


def _transformed(transform, dataset):
    data = synthetic.written(dataset)
    return transform(data, InstanceRecord.from_file(data))


def _written(result):
    assert isinstance(result, run.Transformed)
    return pydicom.dcmread(io.BytesIO(result.data))


def _codes(written):
    return [
        (item.get("CodeValue"), item.get("CodingSchemeDesignator"))
        for item in written.DeidentificationMethodCodeSequence
    ]


def _retained(result):
    """Return the retained descriptor values, leaving out what plans keep."""
    return [
        (item.value, item.path)
        for item in result.qc
        if isinstance(item, descriptor_cleaning.RetainedText)
        and item.path.tag in descriptor_attributes()
    ]


def _material(result):
    return [
        item
        for item in result.qc
        if isinstance(item, descriptor_cleaning.DescriptorMaterial)
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_technique_descriptor_of_vocabulary_words_is_kept_and_retained():
    result = _transformed(_transform(), _structure_set(SeriesDescription="CHEST CT"))

    written = _written(result)
    assert written.SeriesDescription == "CHEST CT"
    assert not isinstance(result.evidence, HeldEvidence)
    assert CLEAN_DESCRIPTORS_CODE in _codes(written)
    (material,) = _material(result)
    assert (material.path, material.sources, material.applied) == (
        TOP,
        ("CHEST CT",),
        True,
    )
    assert [r.outcome.value for r in material.results] == ["kept by vocabulary"]
    assert _retained(result) == [("CHEST CT", TOP)]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_value_that_neither_tier_cleans_takes_its_action_and_is_listed():
    result = _transformed(
        _transform(), _structure_set(SeriesDescription="SENTINEL PLAN")
    )

    written = _written(result)
    assert "SeriesDescription" not in written
    assert b"SENTINEL" not in result.data
    # Removing it meets the option, as for any descriptor not cleaned.
    assert CLEAN_DESCRIPTORS_CODE in _codes(written)
    (material,) = _material(result)
    assert material.applied is False
    (cleaned,) = material.results
    assert (cleaned.outcome.value, cleaned.held_because.value, cleaned.value) == (
        "held",
        "unreviewed",
        None,
    )
    assert not _retained(result)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_reviewed_decisions_keep_or_map_a_value_and_take_precedence():
    reviewed = _reviewed(
        (STUDY_DESCRIPTION, "SENTINEL STUDY", Review.KEEP),
        (SERIES_DESCRIPTION, "CHEST CT", Review.MAP, "THORAX"),
    )
    result = _transformed(
        _transform(reviewed),
        _structure_set(StudyDescription="SENTINEL STUDY", SeriesDescription="CHEST CT"),
    )

    written = _written(result)
    assert written.StudyDescription == "SENTINEL STUDY"
    assert written.SeriesDescription == "THORAX"
    outcomes = {
        material.path: [r.outcome.value for r in material.results]
        for material in _material(result)
    }
    assert outcomes == {STUDY: ["kept"], TOP: ["mapped"]}
    # Only the kept value is retained; a mapped value's source is searched.
    assert {path for _, path in _retained(result)} == {STUDY}


def test_a_value_emptied_by_its_reviewer_alone_takes_its_action():
    reviewed = _reviewed((STUDY_DESCRIPTION, "SENTINEL STUDY", Review.EMPTY))
    result = _transformed(
        _transform(reviewed), _structure_set(StudyDescription="SENTINEL STUDY")
    )

    written = _written(result)
    assert "StudyDescription" not in written
    (material,) = _material(result)
    assert (material.results[0].outcome.value, material.applied) == (
        "emptied",
        False,
    )


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_kept_value_that_echoes_the_patient_is_not_cleaned():
    reviewed = _reviewed((STUDY_DESCRIPTION, "STUDY FICTITIOUS", Review.KEEP))
    result = _transformed(
        _transform(reviewed), _structure_set(StudyDescription="STUDY FICTITIOUS")
    )

    written = _written(result)
    assert "StudyDescription" not in written
    assert b"FICTITIOUS" not in result.data
    (material,) = _material(result)
    (cleaned,) = material.results
    assert (cleaned.outcome.value, cleaned.held_because.value) == (
        "held",
        "echoes identifier",
    )
    assert material.applied is False


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_each_value_of_a_multi_valued_descriptor_is_cleaned_alone():
    reviewed = _reviewed(
        (ADMITTING_DIAGNOSES, "SENTINEL ONE", Review.MAP, "OTHER ONE"),
        (ADMITTING_DIAGNOSES, "SENTINEL TWO", Review.EMPTY),
        (ADMITTING_DIAGNOSES, "SENTINEL KEPT", Review.KEEP),
    )
    transform = _transform(reviewed)

    mapped = _transformed(
        transform,
        _structure_set(AdmittingDiagnosesDescription=["SENTINEL ONE", "SENTINEL TWO"]),
    )
    kept = _transformed(
        transform,
        _structure_set(AdmittingDiagnosesDescription=["SENTINEL KEPT", "CHEST CT"]),
    )

    assert list(_written(mapped).AdmittingDiagnosesDescription) == ["OTHER ONE", ""]
    (material,) = _material(mapped)
    assert material.sources == ("SENTINEL ONE", "SENTINEL TWO")
    assert [r.outcome.value for r in material.results] == ["mapped", "emptied"]
    # The vocabulary keeps no value of a diagnosis, so CHEST CT is held.
    assert "AdmittingDiagnosesDescription" not in _written(kept)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "beside", [(Review.MAP, "OTHER"), (Review.EMPTY,)], ids=["mapped", "emptied"]
)
def test_a_kept_value_beside_a_mapped_or_emptied_one_takes_its_action(beside):
    # The residual search leaves out a kept value's element, so it would
    # leave out the other value's source too.
    reviewed = _reviewed(
        (ADMITTING_DIAGNOSES, "SENTINEL ONE", Review.KEEP),
        (ADMITTING_DIAGNOSES, "SENTINEL TWO", *beside),
    )
    result = _transformed(
        _transform(reviewed),
        _structure_set(AdmittingDiagnosesDescription=["SENTINEL ONE", "SENTINEL TWO"]),
    )

    written = _written(result)
    assert "AdmittingDiagnosesDescription" not in written
    assert b"SENTINEL" not in result.data
    (material,) = _material(result)
    assert material.applied is False
    assert not _retained(result)


def test_kept_values_together_are_written_and_retained():
    reviewed = _reviewed(
        (ADMITTING_DIAGNOSES, "SENTINEL ONE", Review.KEEP),
        (ADMITTING_DIAGNOSES, "SENTINEL TWO", Review.KEEP),
    )
    result = _transformed(
        _transform(reviewed),
        _structure_set(AdmittingDiagnosesDescription=["SENTINEL ONE", "SENTINEL TWO"]),
    )

    written = _written(result)
    assert list(written.AdmittingDiagnosesDescription) == [
        "SENTINEL ONE",
        "SENTINEL TWO",
    ]
    assert _retained(result) == [
        ("SENTINEL ONE", DIAGNOSES),
        ("SENTINEL TWO", DIAGNOSES),
    ]


def test_a_value_held_beside_a_cleaned_one_takes_its_action():
    reviewed = _reviewed((ADMITTING_DIAGNOSES, "SENTINEL ONE", Review.KEEP))
    result = _transformed(
        _transform(reviewed),
        _structure_set(AdmittingDiagnosesDescription=["SENTINEL ONE", "SENTINEL TWO"]),
    )

    written = _written(result)
    assert "AdmittingDiagnosesDescription" not in written
    (material,) = _material(result)
    assert [r.outcome.value for r in material.results] == ["kept", "held"]
    assert material.applied is False


def test_without_a_technique_vocabulary_only_reviewed_values_are_kept():
    result = _transformed(
        _transform(technique=None), _structure_set(SeriesDescription="CHEST CT")
    )

    assert "SeriesDescription" not in _written(result)


def test_a_descriptor_is_read_only_in_its_dictionary_vr():
    comments = ElementPath((), "(0032,4000)")
    texts = descriptor_cleaning._descriptor_texts(  # pylint: disable = protected-access
        types.SimpleNamespace(
            source_values=(
                SourceValue(TOP, "UN", "CHEST CT"),
                SourceValue(DIAGNOSES, "LO", "A\\B"),
                SourceValue(comments, "LT", "A\\B"),
            )
        ),
        [TOP, DIAGNOSES, comments, STUDY],
    )

    # A backslash separates the values of an LO, but is a character of LT.
    assert texts == {DIAGNOSES: ["A", "B"], comments: ["A\\B"]}


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_the_method_digest_and_the_report_cover_the_list_and_the_vocabulary():
    reviewed = _reviewed((STUDY_DESCRIPTION, "SENTINEL STUDY", Review.KEEP))
    transform = _transform(reviewed)
    result = _transformed(transform, _structure_set(StudyDescription="STUDY"))

    keyed = reviewed.keyed_digest(KEY)
    technique = load_technique_vocabulary().sha256
    digest = method_digest(
        compose_policy("basic-clean-descriptors"),
        vocabulary=None,
        reviewed_roi_names=ReviewedNames.empty().keyed_digest(KEY),
        reviewed_descriptors=keyed,
        technique_vocabulary=technique,
    )
    written = _written(result)
    assert list(written.DeidentificationMethod)[:1] == [digest]
    method = json.loads(transform.reporter((), {}, qc_pack.new_reference()))["method"]
    assert (
        method["method_digest"],
        method["reviewed_descriptors"],
        method["technique_vocabulary_digest"],
    ) == (digest, keyed, technique)


def test_a_run_without_a_technique_vocabulary_records_none():
    transform = _transform(technique=None)

    method = json.loads(transform.reporter((), {}, qc_pack.new_reference()))["method"]

    assert method["technique_vocabulary_digest"] is None


def test_decisions_recorded_after_the_transform_is_made_do_not_apply():
    reviewed = ReviewedDescriptors.empty()
    transform = _transform(reviewed)
    reviewed.record(
        STUDY_DESCRIPTION, "SENTINEL STUDY", ReviewedDescriptor(Review.KEEP)
    )

    result = _transformed(transform, _structure_set(StudyDescription="SENTINEL STUDY"))

    assert "StudyDescription" not in _written(result)


def test_a_run_lists_and_counts_its_descriptors_naming_none_in_its_report(
    tmp_path,
):
    source = tmp_path / "source"
    source.mkdir()
    datasets = [
        _structure_set(SeriesDescription="CHEST CT"),
        synthetic.ct_slice(0),
    ]
    datasets[1].SeriesDescription = "SENTINEL SERIES"
    for position, dataset in enumerate(datasets):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))
    transform = _transform()

    result = run.run(
        run.discover(source),
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
        reporter=transform.reporter,
    )

    assert [outcome.status for outcome in result.outcomes] == [run.Status.RELEASED] * 2
    pack = json.loads(result.qc_pack.read_text(encoding="utf-8"))
    listed = {
        (entry["position"], entry["applied"]): [
            (value["source"], value["outcome"], value["held_because"], value["written"])
            for value in entry["values"]
        ]
        for entry in pack["descriptors"]
    }
    assert listed == {
        (0, True): [("CHEST CT", "kept by vocabulary", None, "CHEST CT")],
        (1, False): [("SENTINEL SERIES", "held", "unreviewed", None)],
    }
    assert any(string["value"] == "CHEST CT" for string in pack["retained_strings"])
    report = (tmp_path / "release" / RELEASE_REPORT).read_text(encoding="utf-8")
    assert json.loads(report)["descriptors"] == {
        "outcomes": [
            {"outcome": "held", "count": 1},
            {"outcome": "kept by vocabulary", "count": 1},
        ],
        "held": [{"reason": "unreviewed", "count": 1}],
        "fell_back": 1,
    }
    assert "SENTINEL" not in report and "CHEST" not in report


def _withheld_slice(**descriptors):
    """A CT slice that the run sequesters before cleaning its descriptors.

    Responsible Person and Responsible Organization are required where
    present, and the profile removes them.
    """
    dataset = synthetic.ct_slice(0)
    dataset.ResponsiblePerson = "ROLE^PERSON"
    dataset.ResponsibleOrganization = "SENTINEL ORGANISATION"
    for keyword, value in descriptors.items():
        setattr(dataset, keyword, value)
    return dataset


def _collected(result, *tags):
    return sorted(
        value.source.tag
        for value in result.evidence.collected
        if value.source.tag in tags
    )


PROTOCOL_NAME = "(0018,1030)"
ADMITTING_DIAGNOSES_DESCRIPTION = "(0008,1080)"


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_withheld_instance_leaves_out_only_the_descriptors_cleaning_would_keep():
    reviewed = _reviewed(
        (STUDY_DESCRIPTION, "STUDY FICTITIOUS", Review.KEEP),
        (PROTOCOL_NAME, "SENTINEL PROTOCOL", Review.EMPTY),
        (ADMITTING_DIAGNOSES_DESCRIPTION, "SENTINEL ONE", Review.MAP, "OTHER"),
    )
    tags = (
        SERIES_DESCRIPTION,
        STUDY_DESCRIPTION,
        PROTOCOL_NAME,
        ADMITTING_DIAGNOSES_DESCRIPTION,
    )
    dataset = _withheld_slice(
        SeriesDescription="AXIAL CHEST",  # kept by the vocabulary
        StudyDescription="STUDY FICTITIOUS",  # kept, but echoes the patient
        ProtocolName="SENTINEL PROTOCOL",  # emptied by its reviewer
        AdmittingDiagnosesDescription="SENTINEL ONE",  # mapped by its reviewer
    )

    result = _transformed(_transform(reviewed), dataset)

    assert isinstance(result, run.Sequestered)
    assert _collected(result, *tags) == sorted(tags[1:])
    basic = InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)
    assert _collected(_transformed(basic, dataset), *tags) == sorted(tags)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_kept_descriptor_of_a_withheld_instance_does_not_hold_its_series(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    released = synthetic.ct_slice(1)
    released.SeriesDescription = "AXIAL CHEST"
    datasets = [_withheld_slice(SeriesDescription="AXIAL CHEST"), released]
    for position, dataset in enumerate(datasets):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))

    result = run.run(
        run.discover(source),
        tmp_path / "release",
        _transform(),
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
    )

    assert [outcome.status for outcome in result.outcomes] == [
        run.Status.SEQUESTERED,
        run.Status.RELEASED,
    ]


IMAGE_COMMENTS = "(0020,4000)"


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "descriptors, decisions, tag, left_out",
    [
        # Neither tier cleans it.
        ({"SeriesDescription": "SENTINEL SERIES"}, (), SERIES_DESCRIPTION, False),
        # The vocabulary keeps it, but it echoes the patient's name.
        (
            {"SeriesDescription": "AXIAL CHEST", "PatientName": "CHEST^SENTINEL"},
            (),
            SERIES_DESCRIPTION,
            False,
        ),
        # A kept value beside a mapped one in one element.
        (
            {"AdmittingDiagnosesDescription": ["STUDY ONE", "SENTINEL ONE"]},
            (
                (ADMITTING_DIAGNOSES_DESCRIPTION, "STUDY ONE", Review.KEEP),
                (ADMITTING_DIAGNOSES_DESCRIPTION, "SENTINEL ONE", Review.MAP, "X"),
            ),
            ADMITTING_DIAGNOSES_DESCRIPTION,
            False,
        ),
        # In LT, a backslash is part of the one value that a reviewer keeps.
        (
            {"ImageComments": "LEFT\\RIGHT"},
            ((IMAGE_COMMENTS, "LEFT\\RIGHT", Review.KEEP),),
            IMAGE_COMMENTS,
            True,
        ),
    ],
)
def test_a_withheld_instance_leaves_out_a_descriptor_only_where_it_would_be_kept(
    descriptors, decisions, tag, left_out
):
    result = _transformed(
        _transform(_reviewed(*decisions)), _withheld_slice(**descriptors)
    )

    assert isinstance(result, run.Sequestered)
    assert _collected(result, tag) == ([] if left_out else [tag])
    retained = Dropped(ElementPath((), tag), DropReason.RETAINED)
    assert (retained in result.qc) is left_out


def _series(*descriptions):
    items = []
    for position, description in enumerate(descriptions):
        item = pydicom.Dataset()
        item.SeriesInstanceUID = f"2.25.{position + 1}"
        item.Modality = "CT"
        item.SeriesDescription = description
        items.append(item)
    return items


def _items(paths):
    return sorted(path.items[0][1] for path in paths)


def _collected_items(result):
    return _items(
        value.source
        for value in result.evidence.collected
        if value.source.tag == SERIES_DESCRIPTION
    )


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "descriptions, left_out",
    [
        (["AXIAL CHEST", "AXIAL CHEST"], [0, 1]),
        # The value that is not cleaned is removed, which removes the
        # sequence (D-020), and the kept value with it.
        (["AXIAL CHEST", "SENTINEL SERIES"], []),
    ],
)
def test_a_withheld_instance_keeps_in_a_kept_descriptor_that_its_sequence_may_lose(
    descriptions, left_out
):
    """A kept descriptor stays in the search beside one that falls back.

    Series Description is Type 1 in Source Series Information Sequence.
    """
    sources = _structure_set(SourceSeriesInformationSequence=_series(*descriptions))
    withheld = _structure_set(
        SourceSeriesInformationSequence=_series(*descriptions),
        ResponsiblePerson="ROLE^PERSON",
        ResponsibleOrganization="SENTINEL ORGANISATION",
    )

    written = _transformed(_transform(), sources)
    result = _transformed(_transform(), withheld)

    assert isinstance(written, run.Transformed)
    assert _items(path for _, path in _retained(written)) == left_out
    assert isinstance(result, run.Sequestered)
    assert _collected_items(result) == sorted({0, 1} - set(left_out))
