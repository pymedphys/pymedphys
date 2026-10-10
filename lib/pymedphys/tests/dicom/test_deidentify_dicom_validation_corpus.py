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

"""Each preset's output over the synthetic corpus, checked by independent validators.

dciodvfy, dcentvfy, and dicom-validator
(:mod:`~pymedphys._dicom.deidentify.dicom_validators`) check each released
instance's input and output, and every finding that an output introduces
must be explained by the known differences
(:mod:`~pymedphys._dicom.deidentify.dicom_validation`). The runs are those of
the end-to-end tests: ``basic``, ``basic-clean-descriptors`` with a reviewed
ROI name and one the automatic tier renames, and ``basic`` over the corpus
with its images compressed, which is skipped where a decoding plugin is not
installed.

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
    pixel_decoding,
    roi_names,
    run,
    standard,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.dicom_validation_command import (
    default_standard_path,
)
from pymedphys._dicom.deidentify.dicom_validators import (
    DCENTVFY,
    DICOM_VALIDATOR,
    VALIDATORS,
    ValidatorUnavailable,
)
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.reviewed_roi_names import (
    Review,
    ReviewedName,
    ReviewedNames,
)

from pymedphys._nomenclature import tg263

from . import _synthetic_compressed as compressed
from .test_deidentify_corpus_end_to_end import (
    CLEAN_DESCRIPTORS,
    COMPRESSED,
    KEY,
    MAPPED_NAME,
    MARKER_SIGNATURES,
    VOCABULARY,
    _planted_roi_name,
    _with_a_second_roi,
)

pytestmark = [pytest.mark.pydicom, pytest.mark.dicom_validators]

REQUIRE_VARIABLE = "PYMEDPHYS_DICOM_VALIDATORS"
REPORT_VARIABLE = "PYMEDPHYS_DICOM_VALIDATION_REPORT"
BOTH_VALIDATED = "input validated, output validated"


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
    """Treat the end-to-end tests' invented vocabulary as a published edition."""
    entries = [dataclasses.asdict(s) for s in VOCABULARY.structures]
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(
            roi_names.PUBLISHED_TG263, "TG263 vInvented", tg263.content_sha256(entries)
        )
        yield


@pytest.fixture(
    name="comparison",
    scope="module",
    params=[
        "basic",
        CLEAN_DESCRIPTORS,
        pytest.param(
            COMPRESSED,
            marks=pytest.mark.skipif(
                not all(
                    pixel_decoding.decoder_available(syntax)
                    for syntax in compressed.CORPUS_SYNTAXES
                ),
                reason="a decoding plugin of the compressed corpus is not installed",
            ),
        ),
    ],
)
def fixture_comparison(request, toolset, published):  # pylint: disable = unused-argument
    corpus = corpus_module.build_corpus()
    reviewed = None
    preset = request.param
    if preset == COMPRESSED:
        corpus = compressed.compressed_corpus(corpus)
        preset = "basic"
    elif preset == CLEAN_DESCRIPTORS:
        corpus = _with_a_second_roi(corpus)
        reviewed = ReviewedNames.empty()
        reviewed.record(
            _planted_roi_name(corpus), ReviewedName(Review.MAP, MAPPED_NAME)
        )
    # A short directory, since a run refuses output paths that could exceed
    # Windows' 259 characters.
    directory = Path(tempfile.mkdtemp(prefix="v"))
    try:
        corpus_module.write_corpus(corpus, directory)
        cleaning = (
            None if reviewed is None else DescriptorCleaning(VOCABULARY, reviewed)
        )
        transform = InstanceTransform(
            compose_policy(preset), KEY, cleaning=cleaning, unvalidated_policy=True
        )
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
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    reports = os.environ.get(REPORT_VARIABLE)
    if reports:
        Path(reports).mkdir(parents=True, exist_ok=True)
        dicom_validation.write_results(comparison, Path(reports) / request.param)
    return comparison


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


def test_each_patients_outputs_are_consistent(comparison):
    # The corpus plants a different marker in each instance's patient and
    # study attributes, which the profile removes or replaces alike.
    tally = comparison.tallies[DCENTVFY]

    assert tally["statuses"] == {BOTH_VALIDATED: 1}
    assert tally["input_findings"].get("error", 0) > 0
    assert tally["output_findings"] == {}


def test_the_results_hold_no_marker(comparison):
    # Every input holds the corpus's markers, which the validators quote.
    for text in (comparison.json(), comparison.markdown()):
        for signature in MARKER_SIGNATURES:
            assert signature not in text
