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

import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_cases as cases_module
from pymedphys._dicom.deidentify import text_evaluation_idc as idc
from pymedphys._dicom.deidentify import text_evaluation_markdown as markdown
from pymedphys._dicom.deidentify.text_evaluation_detector import PostProcessing
from pymedphys._dicom.deidentify.text_evaluation_frames import EvaluationRefused

from . import _synthetic_references as synthetic
from .test_deidentify_text_evaluation import SHAPE, _ct_dataset, box_detector

UUID = "0123abcd-0000-4000-8000-{:012d}"
DOI = "10.7937/K9/TCIA.2015.LO9QL9SX"


def _row(number=1, **fields):
    uuid = UUID.format(number)
    return {
        "collection_id": "lidc_idri",
        "SeriesInstanceUID": f"2.25.{number}",
        "crdc_series_uuid": uuid,
        "Modality": "CT",
        "license_short_name": "CC BY 3.0",
        "source_DOI": DOI,
        "series_size_MB": 10.0,
        "series_aws_url": f"s3://idc-open-data/{uuid}/*",
        **fields,
    }


def test_licences_are_compared_in_one_spelling():
    assert idc.canonical_licence("CC BY-NC 4.0") == "CC BY NC 4.0"
    assert idc.canonical_licence(" cc  by_4.0 ") == "CC BY 4.0"
    assert set(idc.OPEN_COLLECTIONS.values()) <= idc.OPEN_LICENCES
    assert idc.OPEN_COLLECTIONS["midrc_ricord_1c"] == "CC BY NC 4.0"
    assert idc.OPEN_COLLECTIONS["lidc_idri"] == "CC BY 3.0"
    assert idc.OPEN_COLLECTIONS["cmb_aml"] == "CC BY 4.0"
    assert len(idc.OPEN_COLLECTIONS) == 28


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
        "cmmd": {"series": 1, "size_mb": 10.0, "licence": "CC BY 4.0", "dois": [DOI]},
        "lidc_idri": {
            "series": 1,
            "size_mb": 10.0,
            "licence": "CC BY 3.0",
            "dois": [DOI],
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
    assert {frame.known_text for frame in frames} == {"unknown"}
    assert isinstance(case, evaluation.CaseSource)


def test_a_folder_not_of_its_series_is_not_read(tmp_path):
    assert [each.reason for each in _case(tmp_path).read()] == ["not-downloaded"]
    _series_folder(tmp_path, 2, series="2.25.99")
    assert [each.reason for each in _case(tmp_path, 2).read()] == ["not-the-series"]


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
    assert point["text_unknown"]["frames"] == 2
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


def test_tcias_collections_wait_on_their_switch(monkeypatch):
    tcia = {
        "collection": "NSCLC-Radiomics",
        "series_instance_uid": "2.25.5",
        "licence": "CC BY NC 3.0",
        "doi": DOI,
    }
    assert not cases_module.TCIA_PER_CASE
    assert cases_module.reported(tcia) is None
    monkeypatch.setattr(cases_module, "TCIA_PER_CASE", True)
    assert cases_module.reported(tcia) == tcia
    assert cases_module.reported({**tcia, "collection": "HaN-Seg"}) is None


def test_a_series_reported_twice_is_refused(tmp_path):
    _series_folder(tmp_path, 1)
    case = _case(tmp_path, 1)
    with pytest.raises(EvaluationRefused):
        cases_module.cases_report(_evaluated([case, case]))
