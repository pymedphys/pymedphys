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

"""Benchmark the engine against an NCI MIDI test data set (D-018).

A development tool. It is not registered with the ``pymedphys`` command,
and stays out of the public command line until the first supported release;
:mod:`~pymedphys._dicom.deidentify.midi_benchmark_command` runs it as
``python -m pymedphys._dicom.deidentify.midi_benchmark_command``, with the
subcommands ``run`` and ``script-results``. :func:`run_benchmark`
de-identifies a local copy of a
MIDI-B test data set through the run pipeline, under a preset and a key
drawn for the run, and scores the released files against the data set's
answer key (:mod:`~pymedphys._dicom.deidentify.midi_answer_key`). It writes,
into a work directory that must not exist:

- ``release/``, the run's release, with its release report and conformance
  statement;
- ``qc/``, the run's confidential QC pack;
- ``validation-script/``, the UID and Patient ID mapping files that the NCI
  validation script needs to score the release itself: CSV files with the
  columns ``id_old`` and ``id_new``, mapping each released instance's test
  data set Study, Series, and SOP Instance UIDs, and its Patient ID, to
  those the run wrote. They hold the test data set's identifiers, so they
  are confidential, as the QC pack is, and the work directory, this one, and
  the files are made for their owner alone where the platform allows;
- ``benchmark.json`` and ``benchmark.md``, the results.

The results hold no attribute value from the data set's files: only
versions, digests, counts, attribute tags, and what the answer key names:
its category codes, its action names, and each instance's modality, given
only in the form of a Code String and otherwise as ``other``. They give a
headline over every check of the answer key, and the same counts
separately for each answer-key category rather than as one score:

- the checks of released instances that passed, failed, or were not
  evaluated;
- the checks of instances that the run withheld, those outside the
  supported coverage (an IOD or transfer syntax that the release does not
  support, which the run sequesters), and those of answer-key instances that
  the input did not hold, none of which is scored, but each of which counts
  in the headline as an outcome of its own, so that no check leaves the
  total; the instances that the run did not release are also counted by
  where they ended up, the reasons the run gave, their SOP Class, and their
  transfer syntax, each named as the standard names it;
- the **deliberate differences**: each failed check that asked for an
  attribute to be kept, where the action that the engine selects from the
  policy, for the attribute's Type in the instance's IOD, explains the
  failure (:func:`score_check`), such as a description
  that the Basic Profile removes but TCIA's curation of the source
  collection kept; and each such check of Patient Identity Removed or
  Longitudinal Temporal Information Modified, whose values the PS3.15
  markers replace. The validation manual says that many answers follow that curation rather than
  the standard, so these are counted by category, attribute, and action,
  apart from failures;
- the **source gaps**: each other failed check that asked for an attribute,
  or a value of it, to be present, and fails on the source instance too;
- the **findings**: every other failed check, such as a value that should
  have been removed and was not, however the policy explains it. Each
  failed check that asked for an attribute, or a value, to be present is
  also counted by whether its source instance holds the attribute, empty
  or with a value; and each failed check that asked for a text to be
  removed by the value's VR, by its shape where it is an Integer String,
  and by whether the answer key's text is the whole value
  (:mod:`~pymedphys._dicom.deidentify.midi_benchmark_sources`).

Under a preset with Clean Descriptors, ROI Names are cleaned with the
pinned TG-263 edition and an empty reviewed-names list, since a benchmark
has no custodian to review them: a name that would be held for review is
emptied, as ``--empty-held-roi-names`` empties it, so that its instance is
released and scored. Every other attribute that the option gives C takes
its action under the policy without the option, as the transform takes it,
and that action is the one a deliberate difference is explained by.

The scoring follows the validation script's rules, in this module's words,
with these differences, so the script's own results remain the published
figures
(:func:`~pymedphys._dicom.deidentify.midi_script_results.summarise_script_results`
reads them):

- each check is scored against its own instance only, never against the
  other instances of its series or study, whatever its scope;
- text is split into words at anything that is not a letter, digit, or
  underscore, and no stop words are dropped, where the script uses NLTK's
  tokeniser and English stop words, so a partly removed or kept text value
  can score differently;
- a multi-valued attribute is compared in its encoded form, its values
  joined by ``\\``, and a sequence by the text of everything it holds;
- bytes are read as ISO 8859-1 text, where the script compares Python's
  representation of them, apart from Pixel Data and Overlay Data, which
  both read as removed;
- a check of an attribute that the file holds, where the script cannot
  score it for want of the text or value it compares, is not evaluated
  rather than left blank; so is one of a consistent UID or Patient ID that
  the mapping files do not cover (they map only the released instances'
  Study, Series, and SOP Instance UIDs and Patient IDs, as the manual
  describes them), which the script fails, and one of burned-in text
  (``pixels_hidden``), which needs OCR and review.

:func:`~pymedphys._dicom.deidentify.midi_script_results.summarise_script_results`
counts the script's results for each check
of each instance, as its instance report does, not as its series report,
which counts a check once for each series.
"""

from __future__ import annotations

import collections
import csv
import dataclasses
import enum
import hashlib
import io
import os
import json
import re
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path, PurePosixPath

from pymedphys._imports import pydicom
from pymedphys._nomenclature import tg263, tg263_published

from . import run
from .compound_actions import COMPOUND_ACTIONS, resolve_in_iod, resolve_plain_in_iod
from .descriptor_cleaning import CLEAN_DESCRIPTORS, DescriptorCleaning, fallback_policy
from .diagnostics import redacted_diagnostics
from .element_rules import KEEP, ElementRules
from .instance_transform import InstanceTransform, ReleaseGate
from .iods import IOD, IODTables, load_iod_tables
from .keys import DeidKey
from .method_digest import method_digest
from .midi_answer_key import (
    Action,
    AnswerKey,
    AttributePath,
    Category,
    Check,
    Element,
    category_order,
    read_answer_key,
)
from .midi_benchmark_errors import ErrorRecorder, uid_name
from .midi_benchmark_markdown import render_markdown
from .midi_benchmark_sources import (
    WATCHED,
    counted_order,
    counted_rows,
    describe_finding,
    describe_source,
    described_rows,
    explained_rows,
    place_rows,
    is_source_gap,
    read_source,
    reason_code,
    reason_places,
)
from .midi_benchmark_values import (
    compare_text,
    element_text,
    find_element,
    is_bulk_data,
    unbracketed,
)
from .policy import Policy, compose_policy
from .reviewed_roi_names import ReviewedNames
from .runtime import runtime_environment
from .scope import classify
from .walker import DESCENDED

FORMAT = "pymedphys-deid-midi-benchmark/2"
RESULTS_JSON = "benchmark.json"
RESULTS_MARKDOWN = "benchmark.md"
SCRIPT_INPUTS = "validation-script"
UID_MAPPING = "uid_mapping.csv"
PATIENT_ID_MAPPING = "patid_mapping.csv"
# The two levels of ROI Name, which Clean Descriptors cleans; every other
# attribute given C takes its action under the policy without the option.
_ROI_PATH = ("(3006,0020)", "(3006,0026)")


class BenchmarkError(Exception):
    """A benchmark that cannot run. The message quotes no value or path."""


class Context(enum.Enum):
    """Where an answer-key instance ended up."""

    RELEASED = "released"
    # The run withheld it: sequestered or held for review.
    WITHHELD = "withheld"
    # Its IOD or transfer syntax is outside the release's supported coverage.
    OUTSIDE_COVERAGE = "outside-coverage"
    # The input held no instance with its SOP Instance UID.
    NOT_IN_INPUT = "not-in-input"


class Result(enum.Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUATED = "not-evaluated"


@dataclasses.dataclass(frozen=True)
class IdentifierMapping:
    """The run's replacements of the test data set's identifiers.

    Attributes
    ----------
    uids : dict of str to str
        Each released instance's Study, Series, and SOP Instance UIDs.
    patient_ids : dict of str to str
        Each released instance's Patient ID; the first released instance of
        a Patient ID that two subjects share, by issuer, wins.
    """

    uids: dict[str, str]
    patient_ids: dict[str, str]


@dataclasses.dataclass(frozen=True)
class Scored:
    """How one check of a released instance scored.

    Attributes
    ----------
    result : Result
    note : str or None
        For a check not evaluated, why; for a deliberate difference, the
        policy's action for the attribute, such as ``"X"``, or ``"marker"``.
    deliberate : bool
        Whether a failed check is a deliberate difference.
    source_gap : bool
        Whether a failed check fails on the source instance too.
    """

    result: Result
    note: str | None = None
    deliberate: bool = False
    source_gap: bool = False


@dataclasses.dataclass
class CategoryCounts:
    """The checks of one category, by what happened to them."""

    passed: int = 0
    failed: int = 0
    deliberate: int = 0
    source_gap: int = 0
    not_evaluated: int = 0
    withheld: int = 0
    outside_coverage: int = 0
    not_in_input: int = 0


@dataclasses.dataclass(frozen=True)
class Benchmark:
    """The results of a benchmark run, without a value from the data set."""

    document: dict[str, object]

    def json(self) -> str:
        return json.dumps(self.document, indent=2, sort_keys=False) + "\n"

    def markdown(self) -> str:
        return render_markdown(self.document)


@dataclasses.dataclass(frozen=True)
class _Header:
    patient_id: str | None
    study: str | None
    series: str | None
    instance: str | None
    sop_class: object
    transfer_syntax: object


def run_benchmark(
    source: str | Path,
    answer_key: str | Path,
    work: str | Path,
    *,
    preset: str = "basic",
    collection: str | None = None,
    tg263_spreadsheet: str | Path | None = None,
    watched: Collection[str] = (),
) -> Benchmark:
    """De-identify a MIDI test data set and score the release.

    Parameters
    ----------
    source : str or Path
        The local copy of the test data set's DICOM files.
    answer_key : str or Path
        Its answer key, an SQLite database.
    work : str or Path
        A directory that does not exist, whose parent does, for the release,
        the QC pack, the validation script's inputs, and the results.
    preset : str, default "basic"
        The preset, which need not be enabled: this is a validation run.
        Under Clean Descriptors, ROI Names are cleaned with the pinned TG-263
        edition, and a name that would be held for review is emptied.
    collection : str, optional
        The name and version of the test data set, recorded as given.
    tg263_spreadsheet : str or Path, optional
        A copy of the pinned TG-263 edition's spreadsheet, for a preset with
        Clean Descriptors; by default, PyMedPhys's cached download.
    watched : collection of str, optional
        Attributes, such as ``(0020,0011)``, each of whose checks is counted
        by where it ended up.

    Raises
    ------
    BenchmarkError
        If the work directory exists or its parent does not, the pinned
        TG-263 edition cannot be loaded, or a spreadsheet is given for a
        preset without Clean Descriptors.
    ~pymedphys._dicom.deidentify.midi_answer_key.AnswerKeyError
        If the answer key cannot be read.
    """
    work = Path(work)
    if work.exists() or not work.parent.is_dir():
        raise BenchmarkError("the work directory must not exist, and its parent must")
    key = read_answer_key(answer_key)
    policy = compose_policy(preset)
    cleaning = _cleaning(policy, tg263_spreadsheet)
    deid_key = DeidKey.generate()
    transform = InstanceTransform(
        policy, deid_key, cleaning=cleaning, unvalidated_policy=True
    )
    # The method digest that the transform's markers and release report
    # record, computed as the transform computes it.
    digest = method_digest(
        policy,
        vocabulary=None if cleaning is None else cleaning.nomenclature,
        reviewed_roi_names=(
            None if cleaning is None else cleaning.reviewed.keyed_digest(deid_key)
        ),
    )
    discovery = run.discover(source)
    # The work directory holds the QC pack and the mapping files, which hold
    # the test data set's identifiers: for its owner alone, as the QC store's.
    work.mkdir(mode=0o700)
    release = work / "release"
    errors = ErrorRecorder()
    result = run.run(
        discovery,
        release,
        errors.transform(transform),
        errors.gate(ReleaseGate()),
        qc_destination=work / "qc",
        reporter=transform.reporter,
        written_check=transform.written_check,
    )
    headers = _headers(discovery)
    mapping = released_mapping(headers, result.outcomes)
    write_mapping_files(work / SCRIPT_INPUTS, mapping)
    benchmark = score(
        key,
        headers,
        result.outcomes,
        release,
        mapping,
        policy,
        preset=preset,
        collection=collection,
        method=digest,
        roi_names=None if cleaning is None else _roi_names_used(),
        internal_errors=errors.records(),
        sources=discovery.paths,
        watched=frozenset(watched),
    )
    (work / RESULTS_JSON).write_text(benchmark.json(), encoding="utf-8", newline="\n")
    (work / RESULTS_MARKDOWN).write_text(
        benchmark.markdown(), encoding="utf-8", newline="\n"
    )
    return benchmark


def _cleaning(
    policy: Policy, tg263_spreadsheet: str | Path | None
) -> DescriptorCleaning | None:
    """Return what a benchmark cleans ROI Names with, under Clean Descriptors."""
    if CLEAN_DESCRIPTORS not in policy.options:
        if tg263_spreadsheet is not None:
            raise BenchmarkError(
                "a TG-263 spreadsheet applies only to a preset with Clean Descriptors"
            )
        return None
    try:
        nomenclature = (
            tg263_published.load()
            if tg263_spreadsheet is None
            else tg263_published.load(spreadsheet=Path(tg263_spreadsheet))
        )
    except (tg263.TG263Error, OSError):
        raise BenchmarkError("the pinned TG-263 edition could not be loaded") from None
    # No custodian reviews a benchmark's ROI Names: empty a name that would be
    # held, so that its instance is released and scored.
    return DescriptorCleaning(nomenclature, ReviewedNames.empty(), empty_held=True)


def _roi_names_used() -> str:
    return (
        f"cleaned with {tg263_published.PUBLISHED.sheet}, no reviewed names, "
        "held names emptied"
    )


def _headers(discovery: run.Discovery) -> tuple[_Header | None, ...]:
    """Each input's identifiers, or ``None`` where it cannot be read."""
    headers: list[_Header | None] = []
    with redacted_diagnostics():
        for path, refusal in zip(discovery.paths, discovery.refusals):
            headers.append(None if refusal is not None else _header(path))
    return tuple(headers)


_HEADER_TAGS = (
    "PatientID",
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "SOPInstanceUID",
    "SOPClassUID",
)


def _header(path: Path) -> _Header | None:
    try:
        dataset = pydicom.dcmread(
            path, stop_before_pixels=True, specific_tags=list(_HEADER_TAGS)
        )
        values = [_text_of(dataset.get(keyword)) for keyword in _HEADER_TAGS[:4]]
        sop_class = dataset.get("SOPClassUID")
        transfer_syntax = dataset.file_meta.get("TransferSyntaxUID")
    except Exception:  # pylint: disable = broad-exception-caught
        # The run refuses or sequesters what cannot be read; so does this.
        return None
    return _Header(
        *values,
        sop_class=None if sop_class is None else str(sop_class),
        transfer_syntax=None if transfer_syntax is None else str(transfer_syntax),
    )


def _text_of(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip(" \t\r\n\x00")
    return text or None


def released_mapping(
    headers: Sequence[_Header | None], outcomes: Sequence[run.Outcome]
) -> IdentifierMapping:
    """Map each released input's identifiers to those named by its output."""
    uids: dict[str, str] = {}
    patient_ids: dict[str, str] = {}
    for header, outcome in zip(headers, outcomes):
        if header is None or outcome.output is None:
            continue
        if outcome.status not in (run.Status.RELEASED, run.Status.DUPLICATE):
            continue
        patient, study, series, name = outcome.output.parts
        instance = PurePosixPath(name).stem
        for old, new in (
            (header.study, study),
            (header.series, series),
            (header.instance, instance),
        ):
            if old is not None:
                uids.setdefault(old, new)
        if header.patient_id is not None:
            patient_ids.setdefault(header.patient_id, patient)
    return IdentifierMapping(uids, patient_ids)


def write_mapping_files(directory: Path, mapping: IdentifierMapping) -> None:
    """Write the validation script's UID and Patient ID mapping files."""
    directory.mkdir(mode=0o700)
    for name, pairs in (
        (UID_MAPPING, mapping.uids),
        (PATIENT_ID_MAPPING, mapping.patient_ids),
    ):
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(("id_old", "id_new"))
        writer.writerows(pairs.items())
        descriptor = os.open(
            directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with open(descriptor, "w", encoding="utf-8", newline="") as file:
            file.write(text.getvalue())


def score(  # pylint: disable = too-many-arguments, too-many-locals
    key: AnswerKey,
    headers: Sequence[_Header | None],
    outcomes: Sequence[run.Outcome],
    release: Path,
    mapping: IdentifierMapping,
    policy: Policy,
    *,
    preset: str,
    collection: str | None,
    method: str | None = None,
    roi_names: str | None = None,
    internal_errors: Sequence[Mapping[str, object]] = (),
    sources: Sequence[Path] = (),
    watched: Collection[str] = (),
) -> Benchmark:
    """Score each check of the answer key against the run's outcome.

    ``method`` is the run's method digest, by default that of ``policy``
    without a vocabulary or reviewed-names list; ``roi_names``, given under
    Clean Descriptors, says what ROI Names were cleaned with; and
    ``internal_errors``, from
    :meth:`~pymedphys._dicom.deidentify.midi_benchmark_errors.ErrorRecorder.records`,
    where the run's transform and gate raised. ``sources``, each input's
    path by position, lets a finding be counted as a source gap
    (:func:`~pymedphys._dicom.deidentify.midi_benchmark_sources.is_source_gap`)
    and be described at its source; and each check of
    an attribute in ``watched``, such as ``(0020,0011)``, is counted by
    where it ended up.
    """
    positions: dict[str, int] = {}
    for position, header in enumerate(headers):
        if header is not None and header.instance is not None:
            positions.setdefault(header.instance, position)
    rules = ElementRules(policy)
    fallback = (
        ElementRules(fallback_policy(policy))
        if CLEAN_DESCRIPTORS in policy.options
        else None
    )
    iod_tables: IODTables = load_iod_tables()
    counts: dict[Category | None, CategoryCounts] = collections.defaultdict(
        CategoryCounts
    )
    differences: collections.Counter = collections.Counter()
    findings: collections.Counter = collections.Counter()
    gaps: collections.Counter = collections.Counter()
    explained: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    instances: collections.Counter = collections.Counter()
    modalities: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    withheld_reasons: collections.Counter = collections.Counter()
    places: collections.Counter = collections.Counter()
    watching: collections.Counter = collections.Counter()
    not_released: dict[tuple[str, str | None, str, str], list[int]] = (
        collections.defaultdict(lambda: [0, 0])
    )
    with redacted_diagnostics():
        for answer in key.by_sop_instance().values():  # one per instance
            position = positions.get(answer.sop_instance_uid)
            context, dataset, iod_name = _context(position, headers, outcomes, release)
            iod = None if iod_name is None else iod_tables.iods.get(iod_name)
            instances[context] += 1
            modalities[_modality(answer.modality)][context] += 1
            if context is Context.WITHHELD and position is not None:
                for reason in outcomes[position].reasons:
                    withheld_reasons[reason_code(reason)] += 1
                places.update(reason_places(outcomes[position].reasons))
            if dataset is None and position is not None:
                kind = _not_released(context, headers[position], outcomes[position])
                not_released[kind][0] += 1
                not_released[kind][1] += len(answer.checks)
            source: list[pydicom.Dataset | None] = []
            for check in answer.checks:
                tally = counts[check.category]
                described = (
                    str(check.category or "unknown"),
                    check.action_name,
                    _attribute(check),
                )
                watch = described[2] in watched
                if dataset is None:
                    field = context.value.replace("-", "_")
                    setattr(tally, field, getattr(tally, field) + 1)
                    if watch:
                        watching[(*described, context.value)] += 1
                    continue
                scored = score_check(
                    check, dataset, mapping, rules, iod, fallback=fallback
                )
                if (
                    scored.result is Result.FAILED
                    and not scored.deliberate
                    and position is not None
                    and position < len(sources)
                ):
                    if not source:
                        source.append(read_source(sources[position]))
                    describe_source(check, source[0], described, explained)
                    if is_source_gap(check, source[0]):
                        scored = Scored(Result.FAILED, _GAP, source_gap=True)
                outcome = _outcome(scored)
                setattr(tally, outcome, getattr(tally, outcome) + 1)
                if watch:
                    watching[(*described, outcome.replace("_", " "))] += 1
                if outcome == "deliberate":
                    differences[(*described, scored.note)] += 1
                elif outcome == "source_gap":
                    gaps[described] += 1
                elif outcome == "failed":
                    findings[described] += 1
                    describe_finding(
                        check,
                        None
                        if not source or source[0] is None
                        else _score(check, source[0], mapping).result is Result.FAILED,
                        described,
                        explained,
                        source=sources[position] if source else None,
                        output=release / outcomes[position].output,  # type: ignore[index, operator]
                    )
    environment = runtime_environment()
    if method is None:
        method = method_digest(policy, vocabulary=None, reviewed_roi_names=None)
    versions: dict[str, object] = {
        "pymedphys": environment.pymedphys_version,
        "python": (f"{environment.python_implementation} {environment.python_version}"),
        "pydicom": environment.pydicom_version,
        "preset": preset,
        "table_edition": policy.edition,
        "method_digest": method,
        "answer_key_sha256": key.sha256,
        "collection": collection,
    }
    if roi_names is not None:
        versions["roi_names"] = roi_names
    totals = CategoryCounts()
    for tally in counts.values():
        for field in dataclasses.fields(CategoryCounts):
            setattr(
                totals,
                field.name,
                getattr(totals, field.name) + getattr(tally, field.name),
            )
    document: dict[str, object] = {
        "format": FORMAT,
        "versions": versions,
        "headline": {
            "checks": sum(dataclasses.astuple(totals)),
            **dataclasses.asdict(totals),
        },
        "coverage": {
            "instances": {context.value: instances[context] for context in Context},
            "by_modality": {
                modality: {context.value: by[context] for context in Context}
                for modality, by in sorted(modalities.items())
            },
            "withheld_reasons": dict(sorted(withheld_reasons.items())),
            "withheld_places": place_rows(places),
            "internal_errors": [dict(error) for error in internal_errors],
            "not_released": [
                {
                    "context": context,
                    "reasons": reasons,
                    "sop_class": sop_class,
                    "transfer_syntax": transfer_syntax,
                    "instances": number[0],
                    "checks": number[1],
                }
                for (context, reasons, sop_class, transfer_syntax), number in sorted(
                    not_released.items(), key=counted_order
                )
            ],
        },
        "categories": [
            {
                "family": None if category is None else category.family,
                "code": None if category is None else category.code,
                **dataclasses.asdict(tally),
            }
            for category, tally in sorted(
                counts.items(), key=lambda pair: category_order(pair[0])
            )
        ],
        "deliberate_differences": [
            {
                "category": category,
                "action": action,
                "attribute": attribute,
                "policy_action": policy_action,
                "checks": number,
            }
            for (category, action, attribute, policy_action), number in sorted(
                differences.items(), key=counted_order
            )
        ],
        "source_gaps": described_rows(gaps),
        "findings": described_rows(findings),
        "failed_at_source": explained_rows(explained),
        "watched": counted_rows(watching, WATCHED),
    }
    return Benchmark(document)


def _outcome(scored: Scored) -> str:
    """Return the CategoryCounts field that a released instance's check adds to."""
    if scored.result is not Result.FAILED:
        return "passed" if scored.result is Result.PASSED else "not_evaluated"
    return (
        "deliberate"
        if scored.deliberate
        else "source_gap"
        if scored.source_gap
        else "failed"
    )


def _attribute(check: Check) -> str | None:
    return None if check.path is None else str(check.path)


def _not_released(
    context: Context, header: _Header | None, outcome: run.Outcome
) -> tuple[str, str | None, str, str]:
    """Describe an instance that the run did not release, without a value.

    A withheld instance is described as held for review, sequestered, or
    refused, with the run's reasons.
    """
    where = context.value
    reasons = None
    if context is Context.WITHHELD:
        where = f"{where}: {outcome.status.value}"
        reasons = ", ".join(sorted({reason_code(reason) for reason in outcome.reasons}))
    if header is None:
        return where, reasons or None, "none", "none"
    return (
        where,
        reasons or None,
        uid_name(header.sop_class),
        uid_name(header.transfer_syntax),
    )


def _context(
    position: int | None,
    headers: Sequence[_Header | None],
    outcomes: Sequence[run.Outcome],
    release: Path,
) -> tuple[Context, pydicom.Dataset | None, str | None]:
    """Return where an instance ended up, its released file, and its IOD."""
    if position is None:
        return Context.NOT_IN_INPUT, None, None
    header = headers[position]
    assert header is not None  # positions holds only read headers
    classification = classify(header.sop_class, header.transfer_syntax)
    if classification.sequestered:
        return Context.OUTSIDE_COVERAGE, None, None
    outcome = outcomes[position]
    if outcome.output is None or outcome.status not in (
        run.Status.RELEASED,
        run.Status.DUPLICATE,
    ):
        return Context.WITHHELD, None, None
    dataset = pydicom.dcmread(release / outcome.output)
    return Context.RELEASED, dataset, classification.iod


_MODALITY = re.compile(r"[A-Z0-9_]{1,16}")


def _modality(modality: str | None) -> str:
    """Return a modality as a code string of the standard's form, or ``other``."""
    if modality is None or not _MODALITY.fullmatch(modality.strip()):
        return "other"
    return modality.strip()


def score_check(
    check: Check,
    dataset: pydicom.Dataset,
    mapping: IdentifierMapping,
    rules: ElementRules,
    iod: IOD | None = None,
    *,
    fallback: ElementRules | None = None,
) -> Scored:
    """Score one check against a released instance.

    A failed check is a deliberate difference only where the action that the
    engine selects explains it. That action is the policy's, resolved for the
    attribute's Type at its place in the instance's IOD as the walker resolves
    it (D-020): a compound action such as X/D gives one of its alternatives,
    and a plain Z on a Type 1 attribute gives D. An attribute that a
    ``tag_retained`` check asks for is missing because the selected action
    is X, or because an enclosing sequence is not kept as a container (any
    action but K or U, which remove, empty, or replace its items); a value
    that ``text_notnull`` asks for is missing because the selected action is
    X or Z, or for such a sequence; and a text that ``text_retained`` asks
    for differs because the selected action is anything but K, or for such
    a sequence. Any other failure, such as a missing attribute that the
    selected action replaces (D or U) or keeps, or changed pixel data, is a
    finding. Without the instance's IOD no action can be selected, so every
    such failure is a finding.

    A check that asks for Patient Identity Removed or Longitudinal Temporal
    Information Modified to be kept, as the source holds it, fails on the
    value that the markers write in its place: where the value is present,
    a deliberate difference noted ``marker``, with or without the IOD. A
    text that a check asks to be removed is never a deliberate difference,
    even where the policy keeps it.

    Under Clean Descriptors, ``fallback`` holds the rules of the policy
    without the option: an attribute given C other than a ROI Name takes
    its action from them, as the transform takes it.
    """
    scored = _score(check, dataset, mapping)
    if scored.result is not Result.FAILED or check.path is None:
        return scored
    note = _explanation(check, check.path, dataset, rules, iod, fallback)
    return scored if note is None else Scored(Result.FAILED, note, deliberate=True)


def _explanation(  # pylint: disable = too-many-arguments
    check: Check,
    path: AttributePath,
    dataset: pydicom.Dataset,
    rules: ElementRules,
    iod: IOD | None,
    fallback: ElementRules | None,
) -> str | None:
    """Return what makes a failed check a deliberate difference, if anything."""
    if check.action not in _EXPLAINING:
        return None
    if (
        len(path.elements) == 1
        and str(path.attribute) in _MARKERS
        and find_element(dataset, path) is not None
    ):
        return "marker"
    return _explaining_action(
        rules,
        path,
        iod,
        _EXPLAINING[check.action],  # type: ignore[index]
        fallback,
    )


# A source gap's note: the source had nothing for the check to find.
_GAP = "absent from the source"


# The markers that replace what the source holds (PS3.15 E.2 and E.3): a
# check that asks for the source's own value fails on them by design.
_MARKERS = frozenset({"(0012,0062)", "(0028,0303)"})


# For each action that asks for something to be kept, the selected actions
# for the attribute itself that explain its failure; None means any action
# but K. A sequence that holds the attribute explains it if its selected
# action does not keep it as a container.
_EXPLAINING: dict[Action, frozenset[str] | None] = {
    Action.TAG_RETAINED: frozenset({"X"}),
    Action.TEXT_NOTNULL: frozenset({"X", "Z"}),
    Action.TEXT_RETAINED: None,
}


def _explaining_action(
    rules: ElementRules,
    path: AttributePath,
    iod: IOD | None,
    allowed: frozenset[str] | None,
    fallback: ElementRules | None = None,
) -> str | None:
    """Return the selected action on ``path`` that explains a failure, if any.

    The enclosing sequences are taken outermost first, then the attribute.
    """
    if iod is None:
        return None
    tags = [_rule_tag(element) for element in path.elements]
    for depth, tag in enumerate(tags):
        try:
            action = _selected_action(rules, iod, tag, tags[:depth])
            if (
                action == "C"
                and fallback is not None
                and tuple(tags[: depth + 1]) != _ROI_PATH
            ):
                action = _selected_action(fallback, iod, tag, tags[:depth])
        except ValueError:
            return None
        if depth < len(tags) - 1:
            if action not in DESCENDED:
                return action
        elif (action != KEEP) if allowed is None else action in allowed:
            return action
    return None


def _selected_action(
    rules: ElementRules, iod: IOD, tag: str, sequences: list[str]
) -> str:
    """Return the action that the walker selects for an attribute (D-020)."""
    action = rules.rule(tag, tuple(sequences), iod=iod).action
    resolve = resolve_in_iod if action in COMPOUND_ACTIONS else resolve_plain_in_iod
    return resolve(iod, tag, tuple(sequences), action)


def _rule_tag(element: Element) -> str:
    if element.is_private:
        # Any element of a private block takes the Private Attributes row.
        return f"({element.group:04X},10{element.element:02X})"
    return str(element)


_NOT_EVALUATED_ACTIONS = {
    Action.PIXELS_HIDDEN: "burned-in text needs OCR and review",
}


def _score(  # pylint: disable = too-many-return-statements, too-many-branches
    check: Check, dataset: pydicom.Dataset, mapping: IdentifierMapping
) -> Scored:
    """Score a check, deciding from what the file holds first, as the script does."""
    action = check.action
    if action is None:
        return Scored(Result.NOT_EVALUATED, "unknown action")
    if action in _NOT_EVALUATED_ACTIONS:
        return Scored(Result.NOT_EVALUATED, _NOT_EVALUATED_ACTIONS[action])
    if action is Action.PIXELS_RETAINED:
        pixels = dataset.get(0x7FE00010)
        if pixels is None or not isinstance(pixels.value, bytes):
            return Scored(Result.FAILED)
        if check.action_text is None:
            return Scored(Result.NOT_EVALUATED, "no digest")
        digest = hashlib.md5(pixels.value, usedforsecurity=False).hexdigest()
        return _passed(digest == unbracketed(check.action_text).strip().lower())
    if check.path is None:
        return Scored(
            Result.NOT_EVALUATED,
            "unreadable place" if check.path_unreadable else "no place",
        )
    element = find_element(dataset, check.path)
    if action is Action.TAG_RETAINED:
        return _passed(element is not None)
    if action is Action.TEXT_NOTNULL:
        return _passed(element is not None and bool(element_text(element)))
    if element is None:
        # Only a check that asks for a text to be kept fails on its absence.
        return _passed(action is not Action.TEXT_RETAINED)
    text = element_text(element)
    if action in (Action.TEXT_RETAINED, Action.TEXT_REMOVED):
        keep = action is Action.TEXT_RETAINED
        if not text or (not keep and is_bulk_data(element)):
            # The script reads Pixel Data and Overlay Data as removed.
            return _passed(not keep)
        if check.action_text is None:
            return Scored(Result.NOT_EVALUATED, "no text to compare")
        passed = compare_text(text, check.action_text, keep=keep)
        if passed is None:
            return Scored(Result.NOT_EVALUATED, "no words to compare")
        return _passed(passed)
    if check.value is None:
        return Scored(Result.NOT_EVALUATED, "no value to compare")
    if action in (Action.DATE_SHIFTED, Action.UID_CHANGED):
        value = unbracketed(check.value).replace("\\", "")
        return _passed(value not in text.replace("\\", ""))
    replacements = (
        mapping.uids if action is Action.UID_CONSISTENT else mapping.patient_ids
    )
    expected = replacements.get(check.value)
    if expected is None:
        return Scored(Result.NOT_EVALUATED, "not in the mapping files")
    return _passed(text == expected)


def _passed(passed: bool) -> Scored:
    return Scored(Result.PASSED if passed else Result.FAILED)
