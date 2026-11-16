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

"""Series of NCI's Imaging Data Commons, selected from invented rows of its
index, and the per-case report of them. No IDC file is read."""

import dataclasses
import hashlib
import io
import json
import zipfile

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_cases as cases_module
from pymedphys._dicom.deidentify import text_evaluation_criteria as criteria
from pymedphys._dicom.deidentify import text_evaluation_idc as idc
from pymedphys._dicom.deidentify import text_evaluation_markdown as markdown
from pymedphys._dicom.deidentify import text_evaluation_phantom_report as phantom_report
from pymedphys._dicom.deidentify.text_evaluation_detector import PostProcessing
from pymedphys._dicom.deidentify.text_evaluation_frames import EvaluationRefused

from . import _synthetic_references as synthetic
from ._text_evaluation_stand_ins import SHAPE, _ct_dataset, box_detector

UUID = "0123abcd-0000-4000-8000-{:012d}"
DOI = "10.7937/K9/TCIA.2015.LO9QL9SX"


def _row(number=1, **fields):
    uuid = UUID.format(number)
    return {
        "collection_id": "lidc_idri",
        "SeriesInstanceUID": f"2.25.{number}",
        "crdc_series_uuid": uuid,
        "Modality": "CT",
        "SOPClassUID": "1.2.840.10008.5.1.4.1.1.2",
        "license_short_name": "CC BY 3.0",
        "source_DOI": DOI,
        "series_size_MB": 10.0,
        "series_aws_url": f"s3://idc-open-data/{uuid}/*",
        "PatientID": f"INVENTED-{number}",
        **fields,
    }


def test_the_index_is_read_only_from_the_pinned_wheel(tmp_path):
    wheel = tmp_path / idc.INDEX_WHEEL
    wheel.write_bytes(b"not the wheel")
    with pytest.raises(EvaluationRefused):
        idc.index_rows(wheel)


def test_the_index_is_read_from_the_wheels_parquet(tmp_path):
    pyarrow = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")
    rows = [{**_row(1), "PatientAge": "never read"}, _row(2)]
    sink = io.BytesIO()
    parquet.write_table(pyarrow.Table.from_pylist(rows), sink)
    wheel = tmp_path / idc.INDEX_WHEEL
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(idc.INDEX_MEMBER, sink.getvalue())
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    found = idc.index_rows(wheel, digest)
    assert found == [_row(1), _row(2)]
    selected = idc.select_series(found).series
    assert len(selected) == 2
    # The Patient ID is kept only as its salted digest.
    held = json.dumps([dataclasses.asdict(each) for each in selected])
    assert "INVENTED" not in held
    assert {each.subject for each in selected} == {
        idc.subject_key("lidc_idri", "INVENTED-1"),
        idc.subject_key("lidc_idri", "INVENTED-2"),
    }
    assert "INVENTED" not in repr(selected) and "subject/" not in repr(selected)


def test_licences_are_compared_in_one_spelling():
    assert idc.canonical_licence("CC BY-NC 4.0") == "CC BY NC 4.0"
    assert idc.canonical_licence(" cc  by_4.0 ") == "CC BY 4.0"
    # As IDC's index spells the NLM's terms.
    assert (
        idc.canonical_licence(
            "National Library of Medicine Terms and Conditions; May 21, 2019"
        )
        in idc.OPEN_LICENCES
    )
    assert set(idc.OPEN_COLLECTIONS.values()) <= idc.OPEN_LICENCES
    assert idc.OPEN_COLLECTIONS["midrc_ricord_1c"] == "CC BY NC 4.0"
    assert idc.OPEN_COLLECTIONS["lidc_idri"] == "CC BY 3.0"
    assert idc.OPEN_COLLECTIONS["cmb_aml"] == "CC BY 4.0"
    assert idc.OPEN_COLLECTIONS["vestibular_schwannoma_mc_rc"] == "CC BY 4.0"
    assert idc.OPEN_COLLECTIONS["tcga_luad"] == "CC BY 3.0"
    assert idc.OPEN_COLLECTIONS["cptac_cm"] == "CC BY 4.0"
    assert len(idc.OPEN_COLLECTIONS) == 52


def test_tcias_seven_collections_are_taken_from_idc_under_their_names():
    # D-056's seven collections from TCIA, each under the licence it names.
    assert set(idc.TCIA_NAMES.values()) == cases_module.TCIA_COLLECTIONS
    assert {
        name: idc.OPEN_COLLECTIONS[key] for key, name in idc.TCIA_NAMES.items()
    } == {
        "4D-Lung": "CC BY 3.0",
        "ACRIN-NSCLC-FDG-PET": "CC BY 3.0",
        "Anti-PD-1_Lung": "CC BY 3.0",
        "Lung-PET-CT-Dx": "CC BY 4.0",
        "NSCLC-Radiomics": "CC BY NC 3.0",
        "Pancreatic-CT-CBCT-SEG": "CC BY 4.0",
        "Pediatric-CT-SEG": "CC BY 4.0",
    }
    assert idc.TEXT_UNKNOWN.isdisjoint(idc.TCIA_NAMES)
    assert set(idc.TARGET_SOP_CLASSES).isdisjoint(idc.TCIA_NAMES)


def test_a_tcia_collections_series_is_read_and_reported_by_its_tcia_name(tmp_path):
    _series_folder(tmp_path, 1)
    case = _case(
        tmp_path,
        1,
        collection_id="nsclc_radiomics",
        license_short_name="CC BY-NC 3.0",
    )
    assert case.collection == "NSCLC-Radiomics"
    assert case.public == {
        "collection": "NSCLC-Radiomics",
        "series_instance_uid": "2.25.1",
        "licence": "CC BY NC 3.0",
        "doi": DOI,
    }
    frames = list(case.read())
    assert {frame.collection for frame in frames} == {"NSCLC-Radiomics"}
    (reported,) = cases_module.cases_report(_evaluated([case]))["cases"]
    assert reported["collection"] == "NSCLC-Radiomics"
    assert "collection_id" not in reported


def test_pediatric_ct_seg_from_idc_is_held_out_whole(tmp_path):
    _series_folder(tmp_path, 1)
    case = _case(
        tmp_path,
        1,
        collection_id="pediatric_ct_seg",
        license_short_name="CC BY 4.0",
    )
    run = evaluation.evaluate(
        [case],
        box_detector,
        evaluation.EvaluationSettings(
            points=(PostProcessing(),),
            held_out_collections=criteria.HELD_OUT_COLLECTIONS,
        ),
    )
    (result,) = run.results
    assert (result.collection, result.split) == ("Pediatric-CT-SEG", "held-out")
    assert not result.evaluated


def test_phantom_collections_are_selected_only_apart_from_patients():
    rows = [
        _row(1),
        _row(2, collection_id="cc_radiomics_phantom_3"),
        _row(3, collection_id="victre", Modality="MG"),
    ]
    patients = idc.select_series(rows)
    assert [each.collection_id for each in patients.series] == ["lidc_idri"]
    assert patients.refused == {"collection-not-vetted": 2}
    phantoms = idc.select_series(rows, phantoms=True)
    assert sorted(each.collection_id for each in phantoms.series) == [
        "cc_radiomics_phantom_3",
        "victre",
    ]
    assert phantoms.refused == {"collection-not-vetted": 1}
    assert set(idc.PHANTOM_NAMES) == set(idc.PHANTOM_COLLECTIONS)
    assert set(idc.PHANTOM_NAMES.values()) <= set(phantom_report.PHANTOM_COLLECTIONS)
    assert set(idc.PHANTOM_COLLECTIONS).isdisjoint(idc.OPEN_COLLECTIONS)


def test_collections_taken_for_some_classes_are_vetted_and_read_text_unknown():
    assert set(idc.TARGET_SOP_CLASSES) <= set(idc.OPEN_COLLECTIONS)
    assert idc.TEXT_UNKNOWN <= set(idc.OPEN_COLLECTIONS)
    assert len(idc.TARGET_SOP_CLASSES) == 14
    for classes in idc.TARGET_SOP_CLASSES.values():
        assert "1.2.840.10008.5.1.4.1.1.7" in classes
        assert "1.2.840.10008.5.1.4.1.1.20" in classes
        assert "1.2.840.10008.5.1.4.1.1.6.1" in classes
        # A CT, MR, or PET image of theirs is not one of those taken.
        assert classes.isdisjoint(
            {
                "1.2.840.10008.5.1.4.1.1.2",
                "1.2.840.10008.5.1.4.1.1.4",
                "1.2.840.10008.5.1.4.1.1.128",
            }
        )
    # Collections taken whole, as before, are not limited by class.
    assert "vestibular_schwannoma_mc_rc" not in idc.TARGET_SOP_CLASSES
    assert "cmb_lca" not in idc.TARGET_SOP_CLASSES


def test_a_series_of_a_class_not_targeted_is_refused():
    fields = {"collection_id": "tcga_luad", "license_short_name": "CC BY 3.0"}
    ct = _row(1, **fields)
    capture = _row(2, **fields, Modality="PT", SOPClassUID="1.2.840.10008.5.1.4.1.1.7")
    nm = _row(3, **fields, Modality="NM", SOPClassUID="1.2.840.10008.5.1.4.1.1.20")
    selection = idc.select_series([ct, capture, nm])
    assert dict(selection.refused) == {"not-a-target-class": 1}
    assert sorted(each.series_instance_uid for each in selection.series) == [
        "2.25.2",
        "2.25.3",
    ]
    # A collection taken whole takes its MR.
    whole = {"collection_id": "upenn_gbm", "license_short_name": "CC BY 4.0"}
    assert len(idc.select_series([_row(4, **whole, Modality="MR")]).series) == 1


@pytest.mark.parametrize(
    "fields, reason",
    [
        ({"collection_id": "nlst"}, "collection-not-vetted"),
        ({"license_short_name": "TCIA Restricted"}, "licence-not-open"),
        ({"license_short_name": "CC BY 4.0"}, "licence-differs"),
        ({"Modality": "SEG"}, "not-an-image-modality"),
        ({"Modality": "SM"}, "not-an-image-modality"),
        ({"source_DOI": ""}, "malformed"),
        ({"series_size_MB": "much"}, "malformed"),
        ({"series_aws_url": "s3://idc-open-data/elsewhere/*"}, "malformed"),
        ({"series_aws_url": "https://example.org/x/*"}, "malformed"),
        ({"SeriesInstanceUID": "PATIENT^A"}, "malformed"),
        ({"SOPClassUID": "secondary capture"}, "malformed"),
    ],
)
def test_a_series_is_refused_by_why(fields, reason):
    selection = idc.select_series([_row(**fields)])
    assert not selection.series
    assert dict(selection.refused) == {reason: 1}


def test_a_row_without_its_columns_or_seen_before_is_refused():
    row = _row()
    del row["source_DOI"]
    selection = idc.select_series([row, _row(2), _row(2)])
    assert dict(selection.refused) == {"missing-column": 1, "repeated": 1}
    assert [each.series_instance_uid for each in selection.series] == ["2.25.2"]


def test_a_doi_is_taken_without_its_resolver():
    (series,) = idc.select_series([_row(source_DOI=f"https://doi.org/{DOI}")]).series
    assert series.doi == DOI
    assert series.public == {
        "collection_id": "lidc_idri",
        "series_instance_uid": "2.25.1",
        "licence": "CC BY 3.0",
        "doi": DOI,
    }


def test_midi_bs_answer_keyed_series_are_left_to_it():
    rows = [
        _row(1, collection_id="pseudo_phi_dicom_data", license_short_name="CC BY 4.0"),
        _row(2, collection_id="pseudo_phi_dicom_data", license_short_name="CC BY 4.0"),
    ]
    assert dict(idc.select_series(rows).refused) == {"needs-answer-key": 2}
    selection = idc.select_series(
        rows, answer_keyed_series={"pseudo_phi_dicom_data": frozenset({"2.25.1"})}
    )
    assert [each.series_instance_uid for each in selection.series] == ["2.25.2"]
    assert dict(selection.refused) == {"answer-keyed": 1}


def test_a_selection_is_fixed_and_limited():
    rows = [_row(number) for number in range(1, 21)]
    first = idc.select_series(rows, per_collection=5)
    again = idc.select_series(list(reversed(rows)), per_collection=5)
    assert first == again
    assert len(first.series) == 5
    assert dict(first.refused) == {"over-collection-limit": 15}
    # Not simply the first rows: the order is a digest's.
    assert [each.series_instance_uid for each in first.series] != [
        f"2.25.{number}" for number in range(1, 6)
    ]
    sized = idc.select_series(rows, max_mb=35.0)
    assert len(sized.series) == 3
    assert dict(sized.refused) == {"over-size-limit": 17}
    huge = idc.select_series([_row(1, series_size_MB=5000.0), _row(2)])
    assert [each.series_instance_uid for each in huge.series] == ["2.25.2"]
    assert dict(huge.refused) == {"over-series-size-limit": 1}
    # Collections take turns, so the size limit is not spent on the first.
    mixed = rows + [
        _row(number, collection_id="cmmd", license_short_name="CC BY 4.0")
        for number in range(21, 41)
    ]
    shared = idc.select_series(mixed, max_mb=40.0)
    assert sorted(each.collection_id for each in shared.series) == [
        "cmmd",
        "cmmd",
        "lidc_idri",
        "lidc_idri",
    ]
    with pytest.raises(EvaluationRefused):
        idc.select_series(rows, per_collection=0)


def test_a_selection_is_described_by_collection_without_a_series():
    selection = idc.select_series(
        [
            _row(1),
            _row(
                2,
                collection_id="cmmd",
                license_short_name="CC BY 4.0",
                Modality="MG",
            ),
            _row(3, collection_id="nlst"),
        ]
    )
    described = selection.described()
    assert described["collections"] == {
        "cmmd": {
            "series": 1,
            "subjects": 1,
            "size_mb": 10.0,
            "licence": "CC BY 4.0",
            "dois": [DOI],
            "sop_classes": {"1.2.840.10008.5.1.4.1.1.2": 1},
            "modalities": {"MG": 1},
        },
        "lidc_idri": {
            "series": 1,
            "subjects": 1,
            "size_mb": 10.0,
            "licence": "CC BY 3.0",
            "dois": [DOI],
            "sop_classes": {"1.2.840.10008.5.1.4.1.1.2": 1},
            "modalities": {"CT": 1},
        },
    }
    assert described["refused"] == {"collection-not-vetted": 1}
    text = json.dumps(described)
    assert "2.25." not in text and "0123abcd" not in text


def test_the_manifest_copies_each_series_to_a_folder_of_its_own():
    selection = idc.select_series([_row(1), _row(2)])
    lines = idc.manifest(selection, "idc/").splitlines()
    assert sorted(lines) == [
        f"cp 's3://idc-open-data/{UUID.format(number)}/*' 'idc/{UUID.format(number)}/'"
        for number in (1, 2)
    ]
    with pytest.raises(EvaluationRefused):
        idc.manifest(selection, "idc; rm -rf /")


def _series_folder(root, number=1, series=None):
    folder = root / UUID.format(number)
    folder.mkdir(parents=True)
    for instance in (1, 2):
        dataset = _ct_dataset(
            np.full((1, *SHAPE), 1024),
            SeriesInstanceUID=series or f"2.25.{number}",
            SOPInstanceUID=f"2.25.{number}.{instance}",
            InstanceNumber=instance,
            PixelSpacing=[1.0, 1.0],
        )
        (folder / f"{instance}.dcm").write_bytes(synthetic.written(dataset))


def _case(tmp_path, number=1, **fields):
    (series,) = idc.select_series([_row(number, **fields)]).series
    return idc.IdcSeriesCase(series, tmp_path)


def test_a_downloaded_series_is_read_as_a_t3_case(tmp_path):
    _series_folder(tmp_path)
    case = _case(tmp_path)
    assert (case.collection, case.case) == ("lidc_idri", "2.25.1")
    frames = list(case.read())
    assert len(frames) == 2
    assert {frame.tier for frame in frames} == {"T3"}
    assert {frame.known_text for frame in frames} == {"none"}
    assert isinstance(case, evaluation.CaseSource)


def test_a_targeted_collections_series_is_read_with_its_text_unknown(tmp_path):
    _series_folder(tmp_path)
    case = _case(
        tmp_path,
        collection_id="cptac_pda",
        license_short_name="CC BY 4.0",
        SOPClassUID="1.2.840.10008.5.1.4.1.1.7",
    )
    assert case.known_text == "unknown"
    frames = list(case.read())
    assert len(frames) == 2
    assert {frame.known_text for frame in frames} == {"unknown"}
    assert {frame.tier for frame in frames} == {"T3"}


def test_one_patients_series_are_one_subject(tmp_path):
    # Two series of one invented patient, and one of another: the first
    # two take one part of the split, whichever their own UIDs would take.
    rows = [_row(1, PatientID="INVENTED-A"), _row(2, PatientID="INVENTED-A"), _row(3)]
    series = idc.select_series(rows).series
    cases = [idc.IdcSeriesCase(each, tmp_path) for each in series]
    by_uid = {each.case: each for each in cases}
    first, second = by_uid["2.25.1"], by_uid["2.25.2"]
    assert first.subject == second.subject != by_uid["2.25.3"].subject
    assert evaluation.subject_of(first) == idc.subject_key("lidc_idri", "INVENTED-A")
    run = _evaluated(cases)
    parts = {
        result.public["series_instance_uid"]: result.split for result in run.results
    }
    assert (
        parts["2.25.1"]
        == parts["2.25.2"]
        == evaluation.split_of("lidc_idri", first.subject)
    )
    report = json.dumps(cases_module.cases_report(run))
    assert "INVENTED" not in report and "subject/" not in report
    summary = json.dumps(evaluation.summarise(run, replicates=50))
    assert "INVENTED" not in summary and "subject/" not in summary
    assert idc.select_series([_row(4, PatientID=" ")]).refused == {"no-patient": 1}


def test_a_folder_not_of_its_series_is_not_read(tmp_path):
    assert [each.reason for each in _case(tmp_path).read()] == ["not-downloaded"]
    _series_folder(tmp_path, 2, series="2.25.99")
    assert [each.reason for each in _case(tmp_path, 2).read()] == ["not-the-series"]


def test_a_patient_shared_by_two_collections_is_one_subject(tmp_path):
    # An invented patient of both vestibular schwannoma collections, under
    # one Patient ID with distinct series, as TCIA describes 58 of them, and
    # another patient of one collection alone.
    shared = {"license_short_name": "CC BY 4.0", "Modality": "MR"}
    shared["SOPClassUID"] = "1.2.840.10008.5.1.4.1.1.4"
    rows = [
        _row(
            1,
            collection_id="vestibular_schwannoma_mc_rc",
            PatientID="VS-SEG-INVENTED",
            **shared,
        ),
        _row(
            2,
            collection_id="vestibular_schwannoma_seg",
            PatientID="VS-SEG-INVENTED",
            **shared,
        ),
        _row(3, collection_id="vestibular_schwannoma_mc_rc", **shared),
    ]
    series = idc.select_series(rows).series
    assert len(series) == 3
    cases = {
        each.case: each for each in (idc.IdcSeriesCase(s, tmp_path) for s in series)
    }
    first, second, other = cases["2.25.1"], cases["2.25.2"], cases["2.25.3"]
    assert first.collection != second.collection
    assert first.subject == second.subject != other.subject
    assert (
        evaluation.namespace_of(first)
        == evaluation.namespace_of(second)
        == "vestibular_schwannoma"
    )
    run = _evaluated(list(cases.values()))
    parts = {
        result.public["series_instance_uid"]: result.split for result in run.results
    }
    assert (
        parts["2.25.1"]
        == parts["2.25.2"]
        == evaluation.split_of(
            "vestibular_schwannoma_seg",
            first.subject,
            namespace="vestibular_schwannoma",
        )
    )
    # The bootstrap's units, keyed as it keys them: one for the shared
    # patient, one for the other.
    units = {(each.namespace or each.collection, each.subject) for each in run.results}
    assert len(units) == 2
    report = json.dumps(cases_module.cases_report(run))
    assert "INVENTED" not in report and "subject/" not in report


def _split_as_described(namespace, subject):
    """The split as SPLIT_RULE, which each summary exports, describes it."""
    joined = "\0".join((evaluation.SPLIT_SALT, namespace, subject))
    number = int.from_bytes(hashlib.sha256(joined.encode()).digest()[:8], "big")
    return "held-out" if number % 3 == 0 else "tuning"


def test_the_exported_split_rule_describes_the_namespace():
    assert "namespace" in evaluation.SPLIT_RULE
    for number in range(200):
        subject = idc.subject_key("vestibular_schwannoma_mc_rc", f"P-{number}")
        assert evaluation.split_of(
            "vestibular_schwannoma_mc_rc",
            subject,
            namespace=idc.subject_namespace("vestibular_schwannoma_mc_rc"),
        ) == _split_as_described("vestibular_schwannoma", subject)
        ordinary = idc.subject_key("lidc_idri", f"P-{number}")
        assert evaluation.split_of("lidc_idri", ordinary) == _split_as_described(
            "lidc_idri", ordinary
        )


def test_subject_namespaces_name_vetted_collections_alone():
    assert set(idc.SUBJECT_NAMESPACES) <= set(idc.OPEN_COLLECTIONS)
    assert not set(idc.SUBJECT_NAMESPACES.values()) & set(idc.OPEN_COLLECTIONS)
    # Any other collection names its patients in itself, as before.
    assert idc.subject_namespace("lidc_idri") == "lidc_idri"
    assert evaluation.namespace_of(Withheld()) == "clinic"


def _evaluated(cases):
    return evaluation.evaluate(
        cases,
        box_detector,
        evaluation.EvaluationSettings(points=(PostProcessing(),), evaluated="all"),
    )


class Withheld:
    """A clinic's case, with a public-looking identity it may not use."""

    collection = "clinic"
    case = "patient/secret"
    public = {
        "collection_id": "clinic",
        "series_instance_uid": "2.25.77",
        "licence": "CC BY 4.0",
        "doi": DOI,
    }

    def read(self):
        return iter(())


def test_the_per_case_report_names_only_idc_series(tmp_path):
    _series_folder(tmp_path, 1)
    run = _evaluated([_case(tmp_path, 1), Withheld()])
    report = cases_module.cases_report(run)
    assert report["format"] == "pymedphys-deid-text-detector-cases/1"
    assert report["withheld"] == 1
    (case,) = report["cases"]
    assert {key: case[key] for key in ("collection_id", "series_instance_uid")} == {
        "collection_id": "lidc_idri",
        "series_instance_uid": "2.25.1",
    }
    assert (case["licence"], case["doi"]) == ("CC BY 3.0", DOI)
    assert case["frames"] == {"CT Image Storage": 2}
    (point,) = case["points"]
    assert point["false_positives"]["frames"] == 2
    assert point["text_unknown"]["frames"] == 0
    assert point["texts"] == 0
    text = json.dumps(report)
    assert "2.25.77" not in text and "clinic" not in text
    assert "1024" not in text
    # The counts-only summary is as it was: it names no series.
    summary = evaluation.summarise(run, replicates=20)
    published = json.dumps(summary) + markdown.markdown(summary)
    assert "2.25.1" not in published and DOI not in published


def test_a_public_identity_must_hold_up():
    good = {
        "collection_id": "lidc_idri",
        "series_instance_uid": "2.25.1",
        "licence": "CC BY 3.0",
        "doi": DOI,
    }
    assert cases_module.reported(good) == good
    for changed in (
        {"licence": "CC BY 4.0"},
        {"licence": "CC BY-SA 4.0"},
        {"series_instance_uid": "PATIENT^A"},
        {"doi": "none"},
        {"extra": "x"},
    ):
        assert cases_module.reported({**good, **changed}) is None
    assert cases_module.reported(None) is None


def test_tcias_collections_are_reported_under_cc_by_and_cc_by_nc(monkeypatch):
    tcia = {
        "collection": "NSCLC-Radiomics",
        "series_instance_uid": "2.25.5",
        "licence": "CC BY NC 3.0",
        "doi": DOI,
    }
    assert cases_module.TCIA_PER_CASE
    assert cases_module.reported(tcia) == tcia
    by = {**tcia, "collection": "4D-Lung", "licence": "CC BY 3.0"}
    assert cases_module.reported(by) == by
    assert cases_module.reported({**tcia, "collection": "HaN-Seg"}) is None
    # Confirmed for CC BY and CC BY-NC alone, so any other licence withholds.
    for licence in ("CC0 1.0", "PDDL 1.0", "CC BY-SA 4.0"):
        assert cases_module.reported({**tcia, "licence": licence}) is None
    monkeypatch.setattr(cases_module, "TCIA_PER_CASE", False)
    assert cases_module.reported(tcia) is None


def test_a_series_reported_twice_is_refused(tmp_path):
    _series_folder(tmp_path, 1)
    case = _case(tmp_path, 1)
    with pytest.raises(EvaluationRefused):
        cases_module.cases_report(_evaluated([case, case]))
