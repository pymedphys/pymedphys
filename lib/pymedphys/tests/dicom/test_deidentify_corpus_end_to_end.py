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

"""A preset run end to end over the synthetic corpus, searched for its markers.

The corpus (:mod:`~pymedphys._dicom.deidentify.synthetic_corpus`) plants a
conspicuous marker in each attribute of Table E.1-1 that its IODs define.
Under the Basic Profile every one of them is removed or replaced, so no
released file may hold any of them. The search here is independent of the
engine's own residual search: it looks for each recorded value as bytes,
and checks numeric values, which cannot be searched for, at their place.
"""

import logging
import shutil
import tempfile
import warnings
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.run_report import RELEASE_REPORT
from pymedphys._dicom.deidentify.release_gate import (
    Decision,
    ReasonCode,
    ReleaseReason,
)
from pymedphys._dicom.deidentify.walker import SequesterReason, Sequestration

pytestmark = pytest.mark.pydicom

KEY = DeidKey(bytes(range(32)))
Kind = corpus_module.PlacementKind
# The kinds whose values the Basic Profile removes or replaces.
REMOVED_KINDS = frozenset(Kind) - {
    Kind.SEQUENCE,
    Kind.NOT_PLANTED,
    Kind.REVIEW_COPY,
}
# Values of these VRs are numbers or ages, which occur throughout files, so
# they are checked at their place rather than searched for.
NUMERIC_VRS = frozenset(
    {"AS", "AT", "DS", "FD", "FL", "IS", "SL", "SS", "SV", "UL", "US", "UV"}
)
# Shorter forms would match by chance.
SHORTEST_FORM = 4
DATE_DIGITS = 8
# The generic parts of every marker.
MARKER_SIGNATURES = (
    corpus_module.MARKER_PREFIX,
    corpus_module.MARKER_UID_ROOT,
    corpus_module.LINKED_UID_ROOT,
    ".424242",
    "MARKER",
    "synmk.invalid",
)


@pytest.fixture(name="basic_run", scope="module")
def fixture_basic_run():
    # A short directory, since a run refuses output paths that could exceed
    # Windows' 259 characters.
    directory = Path(tempfile.mkdtemp(prefix="d"))
    shown = _Shown()
    logger = logging.getLogger("pydicom")
    logger.addHandler(shown)
    try:
        corpus = corpus_module.build_corpus()
        corpus_module.write_corpus(corpus, directory)
        transform = InstanceTransform(
            compose_policy("basic"), KEY, unvalidated_policy=True
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = run.run(
                run.discover(directory / corpus_module.INSTANCES_DIRECTORY),
                directory / "release",
                transform,
                ReleaseGate(),
                qc_destination=directory / "qc",
                reporter=transform.reporter,
            )
        shown.messages.extend(str(warning.message) for warning in caught)
        yield corpus, result, _released(result), shown.messages
    finally:
        logger.removeHandler(shown)
        shutil.rmtree(directory, ignore_errors=True)


class _Shown(logging.Handler):
    """Keep the messages of the log records and warnings a run lets out."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _released(result):
    """Return the released files' bytes by run position."""
    return {
        outcome.position: (result.release / outcome.output).read_bytes()
        for outcome in result.outcomes
        if outcome.status is run.Status.RELEASED
    }


def _published(result):
    """Return the bytes of every file in the release directory, by its path."""
    return {
        path.relative_to(result.release).as_posix(): path.read_bytes()
        for path in sorted(result.release.rglob("*"))
        if path.is_file()
    }


def _forms(placement):
    """Yield each form of a placement's values that is searched for as bytes."""
    for value in placement.values:
        forms = {value}
        if placement.vr in ("DA", "DT"):
            forms.add(value[:DATE_DIGITS])
        for form in forms:
            if len(form) >= SHORTEST_FORM:
                yield form


def _encodings(form):
    return {
        form.encode("latin-1", errors="ignore"),
        form.encode("utf-8"),
        form.encode("utf-16-le"),
    }


def test_the_basic_profile_releases_all_but_the_instances_it_must_hold(
    basic_run,
):
    corpus, result, _, _ = basic_run
    names = [file.name for file in corpus.files]
    sequestered = names.index(corpus_module.SEQUESTERED_FILE)
    review = names.index(corpus_module.REVIEW_FILE)

    assert not result.findings
    assert result.staging_removed
    for outcome in result.outcomes:
        if outcome.position == sequestered:
            assert outcome.status is run.Status.SEQUESTERED
            assert {
                (reason.path.tag, reason.reason)
                for reason in outcome.reasons
                if isinstance(reason, Sequestration)
            } == {
                ("(0010,2297)", SequesterReason.REQUIRED_BY_IOD),
                ("(0010,2299)", SequesterReason.REQUIRED_BY_IOD),
            }
        elif outcome.position == review:
            # The plan's RT Plan Label, found in the dose's Manufacturer's
            # Model Name.
            assert outcome.status is run.Status.HELD_FOR_REVIEW
            assert {
                (reason.decision, reason.code, reason.path)
                for reason in outcome.reasons
                if isinstance(reason, ReleaseReason)
            } == {
                (
                    Decision.QC_REVIEW,
                    ReasonCode.RESIDUAL_TEXT,
                    ElementPath((), "(300A,0002)"),
                )
            }
        else:
            assert outcome.status is run.Status.RELEASED, (
                names[outcome.position],
                outcome.reasons[:5],
            )


def test_no_published_file_holds_a_marker(basic_run):
    corpus, result, released, _ = basic_run
    published = _published(result)
    # The released instances and the release report, and nothing else.
    assert set(published) == {
        *(
            outcome.output.as_posix()
            for outcome in result.outcomes
            if outcome.position in released
        ),
        RELEASE_REPORT,
    }

    for name, data in published.items():
        for signature in MARKER_SIGNATURES:
            for encoded in _encodings(signature):
                assert encoded not in data, (name, signature)
    # Every file's markers, the sequestered file's included, in every
    # published file.
    for file in corpus.files:
        for placement in file.manifest.placements:
            if placement.kind not in REMOVED_KINDS or placement.vr in NUMERIC_VRS:
                continue
            for form in _forms(placement):
                for name, data in published.items():
                    for encoded in _encodings(form):
                        assert encoded not in data, (name, file.name, placement.path)


def test_no_released_file_keeps_a_numeric_marker_at_its_place(basic_run):
    corpus, _, released, _ = basic_run
    assert released

    for position, data in released.items():
        file = corpus.files[position]
        dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))
        for placement in file.manifest.placements:
            if placement.kind not in REMOVED_KINDS or placement.vr not in NUMERIC_VRS:
                continue
            found = _values_at(dataset, placement.path)
            assert found != _numbers(placement.vr, placement.values), (
                file.name,
                placement.path,
            )


def test_no_warning_or_log_record_shows_a_marker(basic_run):
    corpus, _, _, messages = basic_run
    # pydicom warns about the invalid Device UID, quoting it.
    (invalid,) = [
        placement
        for file in corpus.files
        for placement in file.manifest.placements
        if placement.kind is Kind.INVALID
    ]
    assert messages

    for message in messages:
        assert invalid.values[0] not in message
        for signature in MARKER_SIGNATURES:
            assert signature not in message


def _numbers(vr, values):
    """Return values of a numeric VR in a form that compares across writing."""
    if vr in ("AS", "AT"):
        return [str(value).upper() for value in values]
    return [float(value) for value in values]


def _values_at(dataset, path):
    """Return the values at an element path, comparable with _numbers, or None."""
    for tag, index in path.items:
        number = int(tag[1:5] + tag[6:10], 16)
        if number not in dataset or len(dataset[number].value) <= index:
            return None
        dataset = dataset[number].value[index]
    number = int(path.tag[1:5] + path.tag[6:10], 16)
    if number not in dataset:
        return None
    element = dataset[number]
    value = element.value
    values = list(value) if isinstance(value, pydicom.multival.MultiValue) else [value]
    if element.VR == "AT":
        return [f"{int(each):08X}" for each in values]
    if element.VR == "AS":
        return [str(each).upper() for each in values]
    try:
        return [float(each) for each in values]
    except (TypeError, ValueError):
        return None
