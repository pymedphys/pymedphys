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
compressed, which is skipped where a decoding plugin is not installed.

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
import json
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    dicom_validation,
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
from .corpus_runs import CORPUS_RUNS

pytestmark = [pytest.mark.pydicom, pytest.mark.dicom_validators]

REQUIRE_VARIABLE = "PYMEDPHYS_DICOM_VALIDATORS"
REPORT_VARIABLE = "PYMEDPHYS_DICOM_VALIDATION_REPORT"
BOTH_VALIDATED = "input validated, output validated"
BOTH_FAILED = "input failed, output failed"
BOTH_UNSUPPORTED = "input unsupported, output unsupported"
# The corpus's SOP Classes that dicom3tools' January 2024 snapshot does not
# know.
UNKNOWN_TO_DICOM3TOOLS = tuple(
    dicom_validation.sop_class_name(uid)
    for uid in (
        corpus_module.EXTENSIBLE_SR_STORAGE,
        corpus_module.COLON_CAD_SR_STORAGE,
        corpus_module.MACULAR_GRID_THICKNESS_AND_VOLUME_REPORT_STORAGE,
        corpus_module.WAVEFORM_ANNOTATION_SR_STORAGE,
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
    params=[corpus_run.param() for corpus_run in CORPUS_RUNS],
)
def fixture_validated(request, toolset, published):  # pylint: disable = unused-argument
    spec = request.param
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
    # and output.
    assert comparison.tallies[DICOM_VALIDATOR]["statuses"] == {
        BOTH_VALIDATED: comparison.pairs
    }
    # dciodvfy checks every input and output but the corpus's RT Dose in
    # Implicit VR, whose 32-bit pixels abort it on both, and its reports
    # whose SOP Classes dicom3tools' January 2024 snapshot does not know.
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
