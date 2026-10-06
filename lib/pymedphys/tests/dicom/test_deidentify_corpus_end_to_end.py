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

import dataclasses
import logging
import shutil
import tempfile
import warnings
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import run, standard
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import compose_policy
from pymedphys._dicom.deidentify.release_gate import (
    Decision,
    ReasonCode,
    ReleaseReason,
)
from pymedphys._dicom.deidentify.run_report import RELEASE_REPORT
from pymedphys._dicom.deidentify.walker import SequesterReason, Sequestration
from pymedphys._dicom.deidentify.written_references import WrittenFindingKind

pytestmark = pytest.mark.pydicom

KEY = DeidKey(bytes(range(32)))
UNWRITTEN_TARGET = WrittenFindingKind.UNWRITTEN_TARGET
Kind = corpus_module.PlacementKind
# The kinds whose values the Basic Profile removes or replaces.
REMOVED_KINDS = frozenset(Kind) - {
    Kind.SEQUENCE,
    Kind.NOT_PLANTED,
    Kind.REVIEW_COPY,
}
# Values of these VRs are numbers or ages, which occur throughout files, so
# they are checked at their place. Those held as text, DS and IS, are also
# searched for.
NUMERIC_VRS = frozenset(
    {"AS", "AT", "DS", "FD", "FL", "IS", "SL", "SS", "SV", "UL", "US", "UV"}
)
NUMBERS_AS_TEXT = frozenset({"DS", "IS"})
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
    try:
        corpus = corpus_module.build_corpus()
        corpus_module.write_corpus(corpus, directory)
        transform = InstanceTransform(
            compose_policy("basic"), KEY, unvalidated_policy=True
        )
        # Only the run's own records and warnings, not those of the tests.
        shown = _Shown()
        logger = logging.getLogger("pydicom")
        logger.addHandler(shown)
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = run.run(
                    run.discover(directory / corpus_module.INSTANCES_DIRECTORY),
                    directory / "release",
                    transform,
                    ReleaseGate(),
                    qc_destination=directory / "qc",
                    reporter=transform.reporter,
                    written_check=transform.written_check,
                )
        finally:
            logger.removeHandler(shown)
        shown_messages = _Messages(
            tuple(shown.messages), tuple(str(warning.message) for warning in caught)
        )
        yield corpus, result, _released(result), shown_messages
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@dataclasses.dataclass(frozen=True)
class _Messages:
    logged: tuple[str, ...]
    warned: tuple[str, ...]


class _Shown(logging.Handler):
    """Keep the messages of the log records a run lets out."""

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
    """Return each form of a placement's values that is searched for as bytes."""
    forms = set()
    for value in placement.values:
        forms.add(value)
        if placement.vr in ("DA", "DT"):
            forms.add(value[:DATE_DIGITS])
        if placement.vr == "PN":
            # Each component group and component, which a preset could keep
            # on its own.
            forms.update(
                component
                for group in value.split("=")
                for component in (group, *group.split("^"))
            )
    return sorted(form for form in forms if len(form) >= SHORTEST_FORM)


def _searched(placement):
    """Return whether a placement's values are searched for as bytes."""
    return placement.kind in REMOVED_KINDS and (
        placement.vr not in NUMERIC_VRS or placement.vr in NUMBERS_AS_TEXT
    )


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
    # What was written refers to itself as the corpus did, but for the
    # references to the instances that were withheld, which are reported.
    assert result.written_findings
    assert all(
        finding.kind is UNWRITTEN_TARGET
        and all(
            position not in (sequestered, review) for (position,) in finding.instances
        )
        for finding in result.written_findings
    )
    assert result.staging_removed
    assert sorted(outcome.position for outcome in result.outcomes) == list(
        range(len(names))
    )
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
            if not _searched(placement):
                continue
            forms = _forms(placement)
            assert forms, (file.name, placement.path)
            for form in forms:
                for name, data in published.items():
                    for encoded in _encodings(form):
                        assert encoded not in data, (name, file.name, placement.path)


def test_no_released_file_keeps_a_numeric_marker_at_its_place(basic_run):
    corpus, _, released, _ = basic_run
    assert released

    for position, data in released.items():
        file = corpus.files[position]
        source = _read(file.data)
        dataset = _read(data)
        for placement in file.manifest.placements:
            if placement.kind not in REMOVED_KINDS or placement.vr not in NUMERIC_VRS:
                continue
            planted = _numbers(placement.vr, placement.values)
            # The comparison can find the marker where it was planted.
            assert _values_at(source, placement.path) == planted, placement.path
            assert _values_at(dataset, placement.path) != planted, (
                file.name,
                placement.path,
            )


def test_no_released_file_keeps_a_removed_sequence_without_a_marker(basic_run):
    """A sequence whose item holds no marker is checked by its absence."""
    corpus, _, released, _ = basic_run
    actions = {
        row.tag: row.basic_profile for row in standard.load_table_e1_1().attributes
    }
    checked = 0

    for position, data in released.items():
        file = corpus.files[position]
        dataset = _read(data)
        for placement in file.manifest.placements:
            if (
                placement.reason is corpus_module.NotPlantedReason.NO_MARKER_CARRIER
                and actions[placement.profile_tag] == "X"
            ):
                assert _element_at(_read(file.data), placement.path) is not None
                assert _element_at(dataset, placement.path) is None, (
                    file.name,
                    placement.path,
                )
                checked += 1
    assert checked


def test_no_warning_or_log_record_shows_a_marker(basic_run):
    corpus, _, _, messages = basic_run
    # pydicom warns about the invalid Device UID, quoting it.
    (invalid,) = [
        placement
        for file in corpus.files
        for placement in file.manifest.placements
        if placement.kind is Kind.INVALID
    ]
    # Both channels are watched.
    assert messages.logged
    assert messages.warned

    for message in (*messages.logged, *messages.warned):
        assert invalid.values[0] not in message
        for signature in MARKER_SIGNATURES:
            assert signature not in message


def _numbers(vr, values):
    """Return values of a numeric VR in a form that compares across writing."""
    if vr in ("AS", "AT"):
        return [str(value).upper() for value in values]
    return [float(value) for value in values]


def _read(data):
    return pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))


def _element_at(dataset, path):
    """Return the element at an element path, or None."""
    for tag, index in path.items:
        number = int(tag[1:5] + tag[6:10], 16)
        if number not in dataset or len(dataset[number].value) <= index:
            return None
        dataset = dataset[number].value[index]
    number = int(path.tag[1:5] + path.tag[6:10], 16)
    return dataset[number] if number in dataset else None


def _values_at(dataset, path):
    """Return the values at an element path, comparable with _numbers, or None."""
    element = _element_at(dataset, path)
    if element is None:
        return None
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
