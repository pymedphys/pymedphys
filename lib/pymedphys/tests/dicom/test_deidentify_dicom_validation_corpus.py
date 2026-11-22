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

"""Each policy's output over the synthetic corpus, checked by independent validators.

dciodvfy, dcentvfy, and dicom-validator
(:mod:`~pymedphys._dicom.deidentify.dicom_validators`) check each released
instance's input and output, and every finding that an output introduces
must be explained by the known differences
(:mod:`~pymedphys._dicom.deidentify.dicom_validation`). The runs are those of
the end-to-end tests, one for each policy of
:data:`~pymedphys.tests.dicom.corpus_runs.CORPUS_RUNS`: among them
``basic``, ``basic-clean-descriptors`` with a reviewed ROI name and one the
automatic tier renames, and ``basic`` over the corpus with its images
compressed, which is skipped where a decoding plugin is not installed. This
module runs and checks the policies whose names begin with a letter from a
to o, and
:mod:`~pymedphys.tests.dicom.test_deidentify_dicom_validation_corpus_p_z`
runs the others through the same checks, so that CI can validate the two
halves on two runners.

The tests are marked ``dicom_validators``, so they run only when asked for,
with ``--dicom-validators`` or ``--include-dicom-validators``. Without the
validators they are skipped, unless the environment variable
``PYMEDPHYS_DICOM_VALIDATORS`` is ``required``, as in CI, when they fail.
Where ``PYMEDPHYS_DICOM_VALIDATION_REPORT`` names a directory, each run's
results are written into a directory of it named after the run.

They are independent evidence for MIDI-BP-03, conformance with the original
IOD, but do not cite it with the ``deid_requirement`` marker: a release's
requirements matrix reads the reports of the full unit-test runs, which do
not run them, so a cited test would read as not run.
"""

import dataclasses
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    api,
    dicom_validation,
    policy,
    run,
    standard,
)
from pymedphys._dicom.deidentify import dicom_validators as validators
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.dicom_validation_command import (
    default_standard_path,
)
from pymedphys._dicom.deidentify.dicom_validators import (
    DCENTVFY,
    DCIODVFY,
    DICOM_VALIDATOR,
    VALIDATORS,
    Status,
    Validation,
    ValidatorUnavailable,
)
from pymedphys._dicom.deidentify.instance_transform import ReleaseGate

from . import _corpus_run as runs
from ._corpus_run import MARKER_SIGNATURES
from .corpus_runs import FIRST_HALF

pytestmark = [pytest.mark.pydicom, pytest.mark.dicom_validators]

REQUIRE_VARIABLE = "PYMEDPHYS_DICOM_VALIDATORS"
REPORT_VARIABLE = "PYMEDPHYS_DICOM_VALIDATION_REPORT"
BOTH_VALIDATED = "input validated, output validated"
BOTH_FAILED = "input failed, output failed"
BOTH_UNSUPPORTED = "input unsupported, output unsupported"
# The corpus's SOP Classes that dicom3tools' January 2024 snapshot does not
# know, including Label Map Segmentation and the XA/XRF Grayscale and Variable
# Modality LUT Softcopy, Grayscale Planar MPR Volumetric, and Volume Rendering
# Volumetric Presentation States, which it names but has no IOD for, and the
# Waveform and Waveform Acquisition Presentation States, which it does not name.
# pydicom 3.0.2 names neither Label Map Segmentation nor either Waveform
# Presentation State, so their instances are counted together as "other", once.
UNKNOWN_TO_DICOM3TOOLS = tuple(
    dict.fromkeys(
        dicom_validation.sop_class_name(uid)
        for uid in (
            corpus_module.EXTENSIBLE_SR_STORAGE,
            corpus_module.ENHANCED_X_RAY_RADIATION_DOSE_SR_STORAGE,
            corpus_module.PATIENT_RADIATION_DOSE_SR_STORAGE,
            corpus_module.LABEL_MAP_SEGMENTATION_STORAGE,
            corpus_module.COLON_CAD_SR_STORAGE,
            corpus_module.MACULAR_GRID_THICKNESS_AND_VOLUME_REPORT_STORAGE,
            corpus_module.WAVEFORM_ANNOTATION_SR_STORAGE,
            corpus_module.IMPLANTATION_PLAN_SR_STORAGE,
            corpus_module.SIMPLIFIED_ADULT_ECHO_SR_STORAGE,
            corpus_module.PLANNED_IMAGING_AGENT_ADMINISTRATION_SR_STORAGE,
            corpus_module.PERFORMED_IMAGING_AGENT_ADMINISTRATION_SR_STORAGE,
            corpus_module.ENHANCED_RT_IMAGE_STORAGE,
            corpus_module.ENHANCED_CONTINUOUS_RT_IMAGE_STORAGE,
            corpus_module.XA_XRF_GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE,
            corpus_module.VARIABLE_MODALITY_LUT_SOFTCOPY_PRESENTATION_STATE_STORAGE,
            corpus_module.GRAYSCALE_PLANAR_MPR_VOLUMETRIC_PRESENTATION_STATE_STORAGE,
            corpus_module.VOLUME_RENDERING_VOLUMETRIC_PRESENTATION_STATE_STORAGE,
            corpus_module.RT_SEGMENT_ANNOTATION_STORAGE,
            corpus_module.RT_RADIATION_SET_STORAGE,
            corpus_module.C_ARM_PHOTON_ELECTRON_RADIATION_STORAGE,
            corpus_module.TOMOTHERAPEUTIC_RADIATION_STORAGE,
            corpus_module.ROBOTIC_ARM_RADIATION_STORAGE,
            corpus_module.RT_BEAMS_DELIVERY_INSTRUCTION_STORAGE,
            corpus_module.RT_BRACHY_APPLICATION_SETUP_DELIVERY_INSTRUCTION_STORAGE,
            corpus_module.RT_RADIATION_SET_DELIVERY_INSTRUCTION_STORAGE,
            corpus_module.RT_PHYSICIAN_INTENT_STORAGE,
            corpus_module.RT_TREATMENT_PREPARATION_STORAGE,
            corpus_module.RT_PATIENT_POSITION_ACQUISITION_INSTRUCTION_STORAGE,
            corpus_module.RT_RADIATION_RECORD_SET_STORAGE,
            corpus_module.C_ARM_PHOTON_ELECTRON_RADIATION_RECORD_STORAGE,
            corpus_module.TOMOTHERAPEUTIC_RADIATION_RECORD_STORAGE,
            corpus_module.ROBOTIC_ARM_RADIATION_RECORD_STORAGE,
            corpus_module.RT_RADIATION_SALVAGE_RECORD_STORAGE,
            corpus_module.WAVEFORM_PRESENTATION_STATE_STORAGE,
            corpus_module.WAVEFORM_ACQUISITION_PRESENTATION_STATE_STORAGE,
        )
    )
)
# The corpus's SOP Classes whose input dicom-validator 0.9.0 cannot check to
# the end. Recorded RT Control Point DateTime (300A,073A) is Type 1C in their
# control points, and the parser gives its condition the type "mandatory, or
# allowed if another condition holds" without the other condition, so the
# validator raises KeyError where the first condition does not hold. A
# version that checks them fails here until they are taken out.
UNCHECKED_BY_DICOM_VALIDATOR = tuple(
    dicom_validation.sop_class_name(uid)
    for uid in (
        corpus_module.C_ARM_PHOTON_ELECTRON_RADIATION_STORAGE,
        corpus_module.TOMOTHERAPEUTIC_RADIATION_STORAGE,
        corpus_module.ROBOTIC_ARM_RADIATION_STORAGE,
        corpus_module.C_ARM_PHOTON_ELECTRON_RADIATION_RECORD_STORAGE,
        corpus_module.TOMOTHERAPEUTIC_RADIATION_RECORD_STORAGE,
        corpus_module.ROBOTIC_ARM_RADIATION_RECORD_STORAGE,
        corpus_module.RT_RADIATION_SALVAGE_RECORD_STORAGE,
    )
)


@pytest.fixture(name="toolset", scope="module")
def fixture_toolset():  # pylint: disable = inconsistent-return-statements
    """The three validators, or a skip or failure without them."""
    try:
        return dicom_validation.Toolset.find(
            default_standard_path(), standard.load_data_dictionary().edition
        )
    except ValidatorUnavailable as error:
        if os.environ.get(REQUIRE_VARIABLE) == "required":
            pytest.fail(str(error))
        pytest.skip(str(error))


@pytest.fixture(name="published", scope="module")
def fixture_published():
    with runs.published_vocabulary():
        yield


@dataclasses.dataclass(frozen=True)
class Validated:
    """A run's comparison, and dcentvfy's findings for its patient.

    Attributes
    ----------
    spec : CorpusRun
    comparison : Comparison
    consistency : tuple of Validation
        dcentvfy's findings in the patient's inputs and in their outputs.
    """

    spec: runs.CorpusRun
    comparison: dicom_validation.Comparison
    consistency: tuple[Validation, Validation]


@pytest.fixture(
    name="validated",
    scope="module",
    params=[corpus_run.param() for corpus_run in FIRST_HALF],
)
def fixture_validated(request, toolset, published):  # pylint: disable = unused-argument
    return _validate(request.param, toolset)


def _validate(spec, toolset):
    """Run ``spec`` and return its outputs' and inputs' validation."""
    prepared = runs.prepare(spec)
    # A short directory, since a run refuses output paths that could exceed
    # Windows' 259 characters.
    directory = Path(tempfile.mkdtemp(prefix="v"))
    try:
        corpus_module.write_corpus(prepared.corpus, directory)
        transform = prepared.transform(spec.policy())
        discovery = run.discover(directory / corpus_module.INSTANCES_DIRECTORY)
        result = run.run(
            discovery,
            directory / "release",
            transform,
            ReleaseGate(),
            qc_destination=directory / "qc",
            reporter=transform.reporter,
            written_check=transform.written_check,
        )
        pairs, unpaired = dicom_validation.pairs_from_run(discovery, result)
        comparison = dicom_validation.compare(pairs, toolset, unpaired=unpaired)
        consistency = _consistency(pairs, toolset)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    reports = os.environ.get(REPORT_VARIABLE)
    if reports:
        Path(reports).mkdir(parents=True, exist_ok=True)
        dicom_validation.write_results(comparison, Path(reports) / spec.name)
    return Validated(spec, comparison, consistency)


@pytest.fixture(name="comparison", scope="module")
def fixture_comparison(validated):
    return validated.comparison


def _consistency(pairs, toolset):
    """Return dcentvfy's findings in the inputs and in the outputs.

    As in the comparison, a pair that dciodvfy cannot read to the end, or
    whose SOP Class it does not know, input or output, is left out, since
    dcentvfy stops at it or cannot place its attributes.
    """
    readable = [
        pair
        for pair in pairs
        if all(
            validators.run_dciodvfy(toolset.dciodvfy, path).status is Status.VALIDATED
            for path in (pair.source, pair.output)
        )
    ]
    return (
        validators.run_dcentvfy(toolset.dcentvfy, [pair.source for pair in readable]),
        validators.run_dcentvfy(toolset.dcentvfy, [pair.output for pair in readable]),
    )


def test_the_output_introduces_no_unexplained_finding(comparison):
    unexplained = [
        introduced.json()
        for introduced in comparison.introduced
        if introduced.outcome is dicom_validation.Outcome.UNEXPLAINED
    ]

    assert comparison.passed, json.dumps(unexplained, indent=2)


def test_every_validator_ran_over_every_released_instance(comparison):
    assert comparison.validators == VALIDATORS
    assert comparison.pairs > 0
    # dicom-validator, which reads files with pydicom, checks every input
    # and output but those of the SOP Classes whose input it cannot check,
    # whose outputs nothing is compared with.
    statuses = dict(comparison.tallies[DICOM_VALIDATOR]["statuses"])
    validated = statuses.pop(BOTH_VALIDATED, 0)
    assert set(statuses) <= {BOTH_FAILED, "input failed, output validated"}
    unchecked = sum(
        comparison.sop_classes.get(name, 0) for name in UNCHECKED_BY_DICOM_VALIDATOR
    )
    assert sum(statuses.values()) == unchecked
    assert validated == comparison.pairs - unchecked
    # dciodvfy checks every input and output but the corpus's RT Dose in
    # Implicit VR, whose 32-bit pixels abort it on both, and the instances of
    # UNKNOWN_TO_DICOM3TOOLS, whose SOP Classes dicom3tools' January 2024
    # snapshot does not know.
    statuses = dict(comparison.tallies[DCIODVFY]["statuses"])
    failed = statuses.pop(BOTH_FAILED, 0)
    unsupported = statuses.pop(BOTH_UNSUPPORTED, 0)
    assert failed <= 1
    assert unsupported == sum(
        comparison.sop_classes.get(name, 0) for name in UNKNOWN_TO_DICOM3TOOLS
    )
    assert statuses == {BOTH_VALIDATED: comparison.pairs - failed - unsupported}


def test_each_patients_outputs_are_consistent(validated):
    # The corpus plants a different marker in each instance's patient and
    # study attributes, which the profile removes or replaces alike. Where an
    # option keeps or modifies some of them alike, their differences stay as
    # they were, and no other appears.
    tally = validated.comparison.tallies[DCENTVFY]
    inputs, outputs = validated.consistency

    assert tally["statuses"] == {BOTH_VALIDATED: 1}
    assert tally["input_findings"].get("error", 0) > 0
    assert outputs.status is Status.VALIDATED
    assert {finding.path for finding in outputs.findings} == (
        validated.spec.inconsistent
    )
    for finding, count in outputs.findings.items():
        assert inputs.findings.get(finding) == count, finding.json()


def test_the_results_hold_no_marker(comparison):
    # Every input holds the corpus's markers, which the validators quote.
    for text in (comparison.json(), comparison.markdown()):
        for signature in MARKER_SIGNATURES:
            assert signature not in text


# The attributes that the DX Positioning and X-Ray Acquisition Dose Modules
# share, and the X-Ray Filtration Module's, which X-Ray Acquisition Dose
# defines too (PS3.3 Tables C.8-72, C.8-33, and C.8-35).
DX_SHARED = {
    "DistanceSourceToDetector": ("(0018,1110)", "1800"),
    "DistanceSourceToPatient": ("(0018,1111)", "1700"),
    "FilterType": ("(0018,1160)", "NONE"),
    "FilterMaterial": ("(0018,7050)", "ALUMINUM"),
    "FilterThicknessMinimum": ("(0018,7052)", "1.0"),
    "FilterThicknessMaximum": ("(0018,7054)", "1.0"),
}
# The DX Positioning Module's attributes that no other module of the
# Digital X-Ray Image IOD defines, which the corpus's instance holds.
DX_POSITIONING_OWN = (
    "ViewPosition",
    "ProjectionEponymousNameCodeSequence",
    "ViewCodeSequence",
    "PatientOrientationCodeSequence",
    "PatientGantryRelationshipCodeSequence",
)


def test_a_dx_output_explains_the_attributes_whose_modules_dicom_validator_skips(
    toolset, tmp_path, monkeypatch
):
    # A DX For Presentation image whose only attribute of X-Ray Acquisition
    # Dose's own is Comments on Radiation Dose, which the Basic Profile
    # removes, and which holds no attribute of DX Positioning's own. The
    # input validates without these findings; the output, which keeps every
    # shared attribute, gives each as unexpected, and the known differences
    # explain each.
    corpus = corpus_module.build_corpus()
    (file,) = [
        file
        for file in corpus.files
        if file.name == corpus_module.DIGITAL_X_RAY_FOR_PRESENTATION_FILE
    ]
    dataset = pydicom.dcmread(io.BytesIO(file.data))
    for keyword in DX_POSITIONING_OWN:
        assert keyword in dataset
        delattr(dataset, keyword)
    assert "CommentsOnRadiationDose" in dataset
    for keyword, (_, value) in DX_SHARED.items():
        setattr(dataset, keyword, value)
    source = tmp_path / "source"
    source.mkdir()
    dataset.save_as(source / "dx.dcm", enforce_file_format=True)
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    api.deidentify(
        source, tmp_path / "release", qc_pack=tmp_path / "qc", preset="basic"
    )
    (output,) = [
        path
        for path in (tmp_path / "release").rglob("*")
        if path.is_file() and pydicom.misc.is_dicom(path)
    ]
    assert "CommentsOnRadiationDose" not in pydicom.dcmread(output)

    comparison = dicom_validation.compare(
        [dicom_validation.Pair(source / "dx.dcm", output)], toolset
    )
    introduced = {
        i.finding.path: i.outcome
        for i in comparison.introduced
        if i.finding.validator == DICOM_VALIDATOR
    }

    assert introduced == dict.fromkeys(
        (tag for tag, _ in DX_SHARED.values()), dicom_validation.Outcome.EXPLAINED
    )


# What a CT Image's output loses where its input is in a PET series: Series
# Date and Series Time, which X/D removes where they are Type 3, and
# Radiopharmaceutical Information Sequence, which the CT Image IOD does not
# define.
CT_IN_PET_SERIES = ("(0008,0021)", "(0008,0031)", "(0054,0016)")


def test_a_series_that_mixes_modalities_explains_what_each_iod_decides(
    toolset, tmp_path, monkeypatch
):
    # A PET image and a CT image under one Series Instance UID, as in a
    # MIDI-B Test series, which PS3.3 A.1.2.3 does not allow. The CT input
    # holds the PET series' attributes too, so dcentvfy finds none of them
    # missing in the inputs; their outputs differ by IOD, and the known
    # differences explain each such attribute as the input's.
    corpus = corpus_module.build_corpus()
    files = {
        file.name: pydicom.dcmread(io.BytesIO(file.data))
        for file in corpus.files
        if file.name in ("15-pet.dcm", "01-ct-1.dcm")
    }
    pet, ct = files["15-pet.dcm"], files["01-ct-1.dcm"]
    ct.SeriesInstanceUID = pet.SeriesInstanceUID
    ct.SeriesDate, ct.SeriesTime = pet.SeriesDate, pet.SeriesTime
    ct.RadiopharmaceuticalInformationSequence = (
        pet.RadiopharmaceuticalInformationSequence
    )
    source = tmp_path / "source"
    source.mkdir()
    pet.save_as(source / "pet.dcm", enforce_file_format=True)
    ct.save_as(source / "ct.dcm", enforce_file_format=True)
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    discovery = run.discover(source)
    result = api.deidentify(
        source, tmp_path / "release", qc_pack=tmp_path / "qc", preset="basic"
    ).result
    pairs, unpaired = dicom_validation.pairs_from_run(discovery, result)
    assert len(pairs) == 2 and unpaired == 0

    comparison = dicom_validation.compare(pairs, toolset)
    introduced = {
        i.finding.path: (i.finding.message, i.outcome)
        for i in comparison.introduced
        if i.finding.validator == DCENTVFY
    }

    assert introduced == dict.fromkeys(
        CT_IN_PET_SERIES,
        (
            "Attribute present in one instance but not the other",
            dicom_validation.Outcome.EXPLAINED,
        ),
    )
    (difference,) = {
        comparison.known[i.difference - 1]
        for i in comparison.introduced
        if i.finding.validator == DCENTVFY
    }
    assert difference.category is dicom_validation.Category.SOURCE
    assert comparison.passed


def test_a_mixed_series_explains_none_of_another_series_of_its_patient(
    toolset, tmp_path
):
    # The outputs are written here, not by the engine, so that one of them
    # can lose what no rule removes. Series A is a PET image and a CT image
    # under one Series Instance UID, whose CT output loses what the CT Image
    # IOD decides; series B is two CT images of the same patient, one of
    # whose outputs loses Series Date, a new inconsistency that dcentvfy
    # counts under the same finding as series A's.
    corpus = corpus_module.build_corpus()
    files = {
        file.name: pydicom.dcmread(io.BytesIO(file.data))
        for file in corpus.files
        if file.name in ("15-pet.dcm", "01-ct-1.dcm", "02-ct-2.dcm")
    }
    pet, ct = files["15-pet.dcm"], files["01-ct-1.dcm"]
    ct.SeriesInstanceUID = pet.SeriesInstanceUID
    ct.SeriesDate, ct.SeriesTime = pet.SeriesDate, pet.SeriesTime
    ct.RadiopharmaceuticalInformationSequence = (
        pet.RadiopharmaceuticalInformationSequence
    )
    other = []
    for template in (files["02-ct-2.dcm"], files["02-ct-2.dcm"]):
        copy = pydicom.dcmread(io.BytesIO(_bytes(template)))
        copy.SeriesInstanceUID = "1.2.826.0.1.3680043.10.1083.99.1"
        copy.SOPInstanceUID = pydicom.uid.generate_uid()
        copy.file_meta.MediaStorageSOPInstanceUID = copy.SOPInstanceUID
        copy.SeriesDate = pet.SeriesDate
        other.append(copy)
    (tmp_path / "in").mkdir()
    (tmp_path / "out").mkdir()
    pairs = []
    for name, dataset, lose in (
        ("pet", pet, ()),
        (
            "ct",
            ct,
            ("SeriesDate", "SeriesTime", "RadiopharmaceuticalInformationSequence"),
        ),
        ("b1", other[0], ()),
        ("b2", other[1], ("SeriesDate",)),
    ):
        source = tmp_path / "in" / f"{name}.dcm"
        dataset.save_as(source, enforce_file_format=True)
        written = pydicom.dcmread(source)
        for keyword in lose:
            delattr(written, keyword)
        output = tmp_path / "out" / f"{name}.dcm"
        written.save_as(output, enforce_file_format=True)
        pairs.append(dicom_validation.Pair(source, output))

    alone = dicom_validation.compare(pairs[:2], toolset)
    together = dicom_validation.compare(pairs, toolset)

    def dates(comparison):
        return {
            i.outcome: i.occurrences
            for i in comparison.introduced
            if i.finding.validator == DCENTVFY and i.finding.path == "(0008,0021)"
        }

    explained = dicom_validation.Outcome.EXPLAINED
    unexplained = dicom_validation.Outcome.UNEXPLAINED
    assert set(dates(alone)) == {explained}
    assert dates(together)[explained] == dates(alone)[explained]
    assert dates(together)[unexplained] > 0
    assert not together.passed


def _bytes(dataset):
    buffer = io.BytesIO()
    dataset.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()
