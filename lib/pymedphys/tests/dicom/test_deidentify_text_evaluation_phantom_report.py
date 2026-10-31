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

"""Full reports and previews of the text detector, for phantoms alone.

Every image here is synthetic, and every value invented."""

import dataclasses
import json
import struct
import zlib

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_injection as injection
from pymedphys._dicom.deidentify import text_evaluation_phantom_report as report
from pymedphys._dicom.deidentify import text_evaluation_phantoms as phantoms
from pymedphys._dicom.deidentify import text_evaluation_sources as sources
from pymedphys._dicom.deidentify.text_detection import RENDERINGS, RenderedProbability
from pymedphys._dicom.deidentify.text_evaluation_detector import PostProcessing
from pymedphys._dicom.deidentify.text_evaluation_frames import (
    EvaluationFrame,
    EvaluationRefused,
)

from . import _synthetic_references as synthetic

SHAPE = (64, 64)
CC = "CC-Radiomics-Phantom-3"


class BoxDetector:
    """A stand-in detector whose full-range map is 0.9 inside its regions."""

    def __init__(self, regions=((8, 8, 16, 40), (40, 20, 50, 30))):
        self.regions = tuple(regions)

    @property
    def method(self):
        return {"network": "boxes", "variant": {"name": "boxes"}}

    def probabilities(self, frame):
        maps = []
        for name in RENDERINGS:
            probability = np.zeros(frame.shape, np.float32)
            if name == "full-range":
                for top, left, bottom, right in self.regions:
                    probability[top:bottom, left:right] = 0.9
            maps.append(RenderedProbability(name, frame.shape, probability))
        return tuple(maps)


def _settings(**options):
    return evaluation.EvaluationSettings(
        points=options.pop("points", (PostProcessing(),)), evaluated="all", **options
    )


def _phantom_file(project=CC, patient="PHANTOM-01", series="2.25.40", number=1):
    dataset = synthetic.ct_slice(0)
    dataset.Modality = "CT"
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows, dataset.Columns = SHAPE
    dataset.BitsAllocated, dataset.BitsStored, dataset.HighBit = 16, 12, 11
    dataset.PixelRepresentation = 0
    dataset.PatientID = patient
    dataset.SeriesInstanceUID = series
    dataset.SOPInstanceUID = f"{series}.{number}"
    dataset.InstanceNumber = number
    dataset.PixelSpacing = [0.5, 0.5]
    if project is not None:
        block = dataset.private_block(0x0013, "CTP", create=True)
        block.add_new(0x10, "LO", project)
    stored = np.full(SHAPE, 24, np.uint16)
    stored[32:] = 1064
    dataset.PixelData = stored.astype("<u2").tobytes()
    return synthetic.written(dataset)


def _decoded(data):
    """The RGB image of a PNG file that :func:`report.png` writes, checking
    each chunk's CRC."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    position, chunks = 8, {}
    while position < len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        kind = data[position + 4 : position + 8]
        body = data[position + 8 : position + 8 + length]
        (crc,) = struct.unpack(
            ">I", data[position + 8 + length : position + 12 + length]
        )
        assert crc == zlib.crc32(kind + body) & 0xFFFFFFFF
        chunks[kind] = body
        position += 12 + length
    columns, rows, depth, colour = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    assert (depth, colour) == (8, 2)
    raw = zlib.decompress(chunks[b"IDAT"])
    lines = [
        raw[row * (1 + 3 * columns) : (row + 1) * (1 + 3 * columns)]
        for row in range(rows)
    ]
    assert all(line[0] == 0 for line in lines)
    return np.frombuffer(b"".join(line[1:] for line in lines), np.uint8).reshape(
        rows, columns, 3
    )


def test_png_files_hold_the_image():
    image = np.random.default_rng(0).integers(0, 256, (5, 7, 3), dtype=np.uint8)
    assert np.array_equal(_decoded(report.png(image)), image)
    with pytest.raises(EvaluationRefused):
        report.png(np.zeros((4, 4), np.uint8))


# -- The gates ------------------------------------------------------------------


def test_only_allow_listed_phantom_collections_are_admitted():
    assert set(report.PHANTOM_COLLECTIONS) == {
        "CC-Radiomics-Phantom-3",
        "RIDER PHANTOM PET-CT",
        "MRI-DIR",
    }
    with pytest.raises(EvaluationRefused):
        report.phantom_collection("NSCLC-Radiomics")
    forged = dataclasses.replace(report.phantom_collection(CC), name="NSCLC-Radiomics")
    with pytest.raises(EvaluationRefused):
        report.PhantomDicomCase(forged, "a", ())
    widened = dataclasses.replace(report.phantom_collection("MRI-DIR"), patients=None)
    with pytest.raises(EvaluationRefused):
        report.PhantomDicomCase(widened, "a", ())


def test_mri_dir_admits_no_subject_until_its_phantoms_are_listed():
    assert report.phantom_collection("MRI-DIR").patients == frozenset()
    for name in ("CC-Radiomics-Phantom-3", "RIDER PHANTOM PET-CT"):
        assert report.phantom_collection(name).patients is None


def test_a_patient_source_is_never_reported_in_full(tmp_path):
    path = tmp_path / "patient.dcm"
    path.write_bytes(_phantom_file())
    patient = sources.DicomCase(CC, "a", (str(path),))
    with pytest.raises(EvaluationRefused):
        report.phantom_report(patient, BoxDetector(), _settings(), tmp_path / "out")
    with pytest.raises(EvaluationRefused):
        report.write_phantom_reports(
            [patient], BoxDetector, _settings(), tmp_path / "all"
        )
    elsewhere = sources.SkippedFiles("NSCLC-Radiomics", "x", "not-read", 1)
    with pytest.raises(EvaluationRefused):
        report.write_phantom_reports(
            [elsewhere], BoxDetector, _settings(), tmp_path / "all"
        )
    assert not (tmp_path / "out").exists()
    assert not (tmp_path / "all").exists()


@pytest.mark.parametrize(
    "collection, project, patient, reason",
    [
        (CC, None, "PHANTOM-01", "not-phantom/no-project"),
        (CC, "NSCLC-Radiomics", "PHANTOM-01", "not-phantom/other-project"),
        ("MRI-DIR", "MRI-DIR", "PHANTOM-01", "not-phantom/patient-not-listed"),
    ],
)
def test_files_not_of_the_collections_phantoms_are_skipped_unread(
    tmp_path, collection, project, patient, reason
):
    path = tmp_path / "file.dcm"
    path.write_bytes(_phantom_file(project=project, patient=patient))
    case = report.PhantomDicomCase(
        report.phantom_collection(collection), "a", (str(path),)
    )
    assert list(case.read()) == [sources.Skipped(reason)]


def test_files_of_the_collection_are_read_as_a_run_reads_them(tmp_path):
    path = tmp_path / "file.dcm"
    path.write_bytes(_phantom_file())
    case = report.PhantomDicomCase(report.phantom_collection(CC), "a", (str(path),))
    (frame,) = list(case.read())
    assert isinstance(frame, EvaluationFrame)
    assert frame.collection == CC
    assert frame.iod == "CT Image Storage"
    assert frame.known_text == "none"


# -- Reports ------------------------------------------------------------------


def test_a_synthetic_case_is_reported_with_previews(tmp_path):
    case = phantoms.PhantomCase(phantoms.Phantom("ct-thorax", 96, 4.0), seed=1)
    plan = injection.InjectionPlan(
        texts=2, heights=(7.0,), positions=("air", "edge"), contents=("letter",)
    )
    found = report.phantom_report(
        case, BoxDetector(), _settings(plan=plan), tmp_path / "case"
    )
    assert found["format"] == report.PHANTOM_REPORT_FORMAT
    assert found["attribution"]["collection"] == "synthetic"
    passes = [frame["pass"] for frame in found["frames"]]
    assert passes == ["as read", "with injected text"]
    read, injected = found["frames"]
    assert len(read["boxes"][0]) == 2
    assert read["away_from_text"] == read["boxes"]
    assert injected["texts"]
    for text in injected["texts"]:
        assert text["strata"]["truth"] == "injected"
        assert len(text["fully_covered"]) == 1
    written = json.loads((tmp_path / "case" / "report.json").read_text())
    assert written == found
    files = read["previews"]
    assert files[0].endswith("-overview.png")
    assert sum("-region-" in each for each in files) == 2
    for each in files + injected["previews"]:
        image = _decoded((tmp_path / "case" / each).read_bytes())
        assert image.shape[2] == 3
        assert min(image.shape[:2]) >= 32


def test_previews_beyond_the_limit_are_counted_not_drawn(tmp_path):
    case = phantoms.PhantomCase(
        phantoms.Phantom("ct-thorax", 96, 4.0), seed=1, frames=2
    )
    found = report.phantom_report(
        case,
        BoxDetector(),
        _settings(),
        tmp_path / "case",
        report.PreviewSettings(max_previews=4),
    )
    drawn = sum(len(frame["previews"]) for frame in found["frames"])
    assert drawn == 4
    assert found["previews_not_drawn"] == 2
    assert len(list((tmp_path / "case" / "previews").iterdir())) == 4


def test_a_point_outside_the_grid_is_refused(tmp_path):
    case = phantoms.PhantomCase(phantoms.Phantom("ct-thorax", 96, 4.0), seed=1)
    with pytest.raises(EvaluationRefused):
        report.phantom_report(
            case,
            BoxDetector(),
            _settings(),
            tmp_path,
            report.PreviewSettings(point=1),
        )


def test_a_folder_of_phantoms_is_reported_with_its_attribution(tmp_path):
    root = tmp_path / "CC"
    root.mkdir()
    (root / "1.dcm").write_bytes(_phantom_file(number=1))
    (root / "2.dcm").write_bytes(_phantom_file(number=2))
    (root / "other.dcm").write_bytes(
        _phantom_file(project="NSCLC-Radiomics", series="2.25.50")
    )
    (root / "notes.txt").write_text("not DICOM")
    cases = report.phantom_dicom_cases(root, CC)
    assert all(
        isinstance(each, (report.PhantomDicomCase, sources.SkippedFiles))
        for each in cases
    )
    index = report.write_phantom_reports(
        cases, BoxDetector, _settings(), tmp_path / "out"
    )
    assert index["format"] == report.PHANTOM_REPORT_FORMAT
    assert index["skipped"] == {"not-phantom/other-project": 1, "not-read": 1}
    frames = sorted(entry["frames"] for entry in index["cases"])
    assert frames[-1] == 2
    for entry in index["cases"]:
        assert (tmp_path / "out" / entry["report"]).is_file()
    attribution = (tmp_path / "out" / "ATTRIBUTION.md").read_text()
    assert "https://doi.org/10.7937/tcia.2019.j71i4fah" in attribution
    assert "CC BY 3.0" in attribution
    assert report.CHANGES in attribution
    # The same cases give the counts of the evaluation.
    counts = evaluation.summarise(
        evaluation.evaluate(cases, BoxDetector, _settings()), replicates=50
    )
    assert counts["frames"] == {"CT Image Storage": 2}
