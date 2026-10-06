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

A development tool, outside the public command line until the first
supported release: :func:`run_benchmark` de-identifies a local copy of a
MIDI-B test data set through the run pipeline, under a preset and a key
drawn for the run, and scores the released files against the data set's
answer key (:mod:`~pymedphys._dicom.deidentify.midi_answer_key`). It writes,
into a work directory that must not exist:

- ``release/``, the run's release, with its release report;
- ``qc/``, the run's confidential QC pack;
- ``validation-script/``, the UID and Patient ID mapping files that the NCI
  validation script needs to score the release itself: CSV files with the
  columns ``id_old`` and ``id_new``, mapping each released instance's test
  data set Study, Series, and SOP Instance UIDs, and its Patient ID, to
  those the run wrote. They hold the test data set's identifiers, so they
  are confidential, as the QC pack is;
- ``benchmark.json`` and ``benchmark.md``, the results.

The results hold no value from the data set: only versions, digests, counts,
answer-key categories, actions, and attribute tags. They give, separately
for each answer-key category rather than as one score:

- the checks of released instances that passed, failed, or were not
  evaluated;
- the checks of instances that the run withheld, those outside the
  supported coverage (an IOD or transfer syntax that the release does not
  support, which the run sequesters), and those of answer-key instances that
  the input did not hold, none of which is scored;
- the **deliberate differences**: each failed check that asked for an
  attribute to be kept, where the policy's own action for the attribute
  removes or replaces it, such as a description that the Basic Profile
  removes but TCIA's curation of the source collection kept. The validation
  manual says that many answers follow that curation rather than the
  standard, so these are counted by category, attribute, and action, apart
  from failures;
- the **findings**: every other failed check, such as a value that should
  have been removed and was not.

The scoring follows the validation script's rules, in this module's words,
with these differences, so the script's own results remain the published
figures (:func:`summarise_script_results` reads them):

- each check is scored against its own instance only, never against the
  other instances of its series or study, whatever its scope;
- text is split into words at anything that is not a letter, digit, or
  underscore, and no stop words are dropped, where the script uses NLTK's
  tokeniser and English stop words, so a partly removed or kept text value
  can score differently;
- a multi-valued attribute is compared in its encoded form, its values
  joined by ``\\``, and a sequence by the text of everything it holds;
- a check that the script cannot score, such as one without the text it
  compares, is not evaluated rather than left blank, and so is one of a
  consistent UID that the mapping files do not cover (they map only Study,
  Series, and SOP Instance UIDs, as the manual describes them), and one of
  burned-in text (``pixels_hidden``), which needs OCR and review.
"""

from __future__ import annotations

import collections
import csv
import dataclasses
import enum
import hashlib
import io
import json
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath

from pymedphys._imports import pydicom

from . import run
from .descriptor_cleaning import CLEAN_DESCRIPTORS
from .diagnostics import redacted_diagnostics
from .element_rules import KEEP, ElementRules
from .instance_transform import InstanceTransform, ReleaseGate
from .keys import DeidKey
from .method_digest import method_digest
from .midi_answer_key import (
    RETAINING_ACTIONS,
    Action,
    AnswerKey,
    AttributePath,
    Categories,
    Category,
    Check,
    Element,
    category_of,
    read_answer_key,
)
from .policy import Policy, compose_policy
from .runtime import runtime_environment
from .scope import classify

FORMAT = "pymedphys-deid-midi-benchmark/1"
RESULTS_JSON = "benchmark.json"
RESULTS_MARKDOWN = "benchmark.md"
SCRIPT_INPUTS = "validation-script"
UID_MAPPING = "uid_mapping.csv"
PATIENT_ID_MAPPING = "patid_mapping.csv"
# The table and columns of the validation script's results database.
SCRIPT_RESULTS_TABLE = "validation_results"


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
        policy's action for the attribute, such as ``"X"``.
    deliberate : bool
        Whether a failed check is a deliberate difference.
    """

    result: Result
    note: str | None = None
    deliberate: bool = False


@dataclasses.dataclass
class CategoryCounts:
    """The checks of one category, by what happened to them."""

    passed: int = 0
    failed: int = 0
    deliberate: int = 0
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
        A preset without Clean Descriptors, which needs a reviewed-names
        list. The preset need not be enabled: this is a validation run.
    collection : str, optional
        The name and version of the test data set, recorded as given.

    Raises
    ------
    BenchmarkError
        If the work directory exists or its parent does not, or the preset
        needs descriptor cleaning.
    ~pymedphys._dicom.deidentify.midi_answer_key.AnswerKeyError
        If the answer key cannot be read.
    """
    work = Path(work)
    if work.exists() or not work.parent.is_dir():
        raise BenchmarkError("the work directory must not exist, and its parent must")
    key = read_answer_key(answer_key)
    policy = compose_policy(preset)
    if CLEAN_DESCRIPTORS in policy.options:
        raise BenchmarkError(
            "a preset with Clean Descriptors needs a reviewed-names list, "
            "which the benchmark does not take yet"
        )
    transform = InstanceTransform(policy, DeidKey.generate(), unvalidated_policy=True)
    discovery = run.discover(source)
    work.mkdir()
    release = work / "release"
    result = run.run(
        discovery,
        release,
        transform,
        ReleaseGate(),
        qc_destination=work / "qc",
        reporter=transform.reporter,
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
    )
    (work / RESULTS_JSON).write_text(benchmark.json(), encoding="utf-8", newline="\n")
    (work / RESULTS_MARKDOWN).write_text(
        benchmark.markdown(), encoding="utf-8", newline="\n"
    )
    return benchmark


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
    text = str(value).strip(" \x00")
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
    directory.mkdir()
    for name, pairs in (
        (UID_MAPPING, mapping.uids),
        (PATIENT_ID_MAPPING, mapping.patient_ids),
    ):
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(("id_old", "id_new"))
        writer.writerows(pairs.items())
        (directory / name).write_text(text.getvalue(), encoding="utf-8", newline="")


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
) -> Benchmark:
    """Score each check of the answer key against the run's outcome."""
    positions: dict[str, int] = {}
    for position, header in enumerate(headers):
        if header is not None and header.instance is not None:
            positions.setdefault(header.instance, position)
    rules = ElementRules(policy)
    counts: dict[Category | None, CategoryCounts] = collections.defaultdict(
        CategoryCounts
    )
    differences: collections.Counter = collections.Counter()
    findings: collections.Counter = collections.Counter()
    instances: collections.Counter = collections.Counter()
    modalities: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    withheld_reasons: collections.Counter = collections.Counter()
    with redacted_diagnostics():
        for answer in key.by_sop_instance().values():
            position = positions.get(answer.sop_instance_uid)
            context, dataset = _context(position, headers, outcomes, release)
            instances[context] += 1
            modalities[answer.modality][context] += 1
            if context is Context.WITHHELD and position is not None:
                for reason in outcomes[position].reasons:
                    withheld_reasons[reason_code(reason)] += 1
            for check in answer.checks:
                tally = counts[check.category]
                if dataset is None:
                    field = context.value.replace("-", "_")
                    setattr(tally, field, getattr(tally, field) + 1)
                    continue
                scored = score_check(check, dataset, mapping, rules)
                described = (
                    str(check.category or "unknown"),
                    check.action_name,
                    _attribute(check),
                )
                if scored.result is Result.PASSED:
                    tally.passed += 1
                elif scored.result is Result.NOT_EVALUATED:
                    tally.not_evaluated += 1
                elif scored.deliberate:
                    tally.deliberate += 1
                    differences[(*described, scored.note)] += 1
                else:
                    tally.failed += 1
                    findings[described] += 1
    environment = runtime_environment()
    document: dict[str, object] = {
        "format": FORMAT,
        "versions": {
            "pymedphys": environment.pymedphys_version,
            "python": (
                f"{environment.python_implementation} {environment.python_version}"
            ),
            "pydicom": environment.pydicom_version,
            "preset": preset,
            "table_edition": policy.edition,
            "method_digest": method_digest(
                policy, vocabulary=None, reviewed_roi_names=None
            ),
            "answer_key_sha256": key.sha256,
            "collection": collection,
        },
        "coverage": {
            "instances": {context.value: instances[context] for context in Context},
            "by_modality": {
                modality: {context.value: by[context] for context in Context}
                for modality, by in sorted(modalities.items())
            },
            "withheld_reasons": dict(sorted(withheld_reasons.items())),
        },
        "categories": [
            {
                "family": None if category is None else category.family,
                "code": None if category is None else category.code,
                **dataclasses.asdict(tally),
            }
            for category, tally in sorted(
                counts.items(), key=lambda pair: _category_order(pair[0])
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
                differences.items(), key=_counted_order
            )
        ],
        "findings": [
            {
                "category": category,
                "action": action,
                "attribute": attribute,
                "checks": number,
            }
            for (category, action, attribute), number in sorted(
                findings.items(), key=_counted_order
            )
        ],
    }
    return Benchmark(document)


def _counted_order(pair: tuple[tuple[str | None, ...], int]) -> tuple[str, ...]:
    """Order counted descriptions by their text, a missing attribute first."""
    return tuple("" if part is None else part for part in pair[0])


def _category_order(category: Category | None) -> tuple[str, str]:
    return ("~", "") if category is None else (category.family, category.code)


def _attribute(check: Check) -> str | None:
    return None if check.path is None else str(check.path)


def reason_code(reason: object) -> str:
    """Return a withheld input's reason as a code, without a value."""
    code = getattr(reason, "code", None)
    if isinstance(code, enum.Enum):
        return str(code.value)
    if isinstance(reason, enum.Enum):
        return str(reason.value)
    return type(reason).__name__


def _context(
    position: int | None,
    headers: Sequence[_Header | None],
    outcomes: Sequence[run.Outcome],
    release: Path,
) -> tuple[Context, pydicom.Dataset | None]:
    if position is None:
        return Context.NOT_IN_INPUT, None
    header = headers[position]
    assert header is not None  # positions holds only read headers
    if classify(header.sop_class, header.transfer_syntax).sequestered:
        return Context.OUTSIDE_COVERAGE, None
    outcome = outcomes[position]
    if outcome.output is None or outcome.status not in (
        run.Status.RELEASED,
        run.Status.DUPLICATE,
    ):
        return Context.WITHHELD, None
    return Context.RELEASED, pydicom.dcmread(release / outcome.output)


def score_check(
    check: Check,
    dataset: pydicom.Dataset,
    mapping: IdentifierMapping,
    rules: ElementRules,
) -> Scored:
    """Score one check against a released instance."""
    scored = _score(check, dataset, mapping)
    if scored.result is not Result.FAILED:
        return scored
    if (
        check.action
        in RETAINING_ACTIONS
        - {
            Action.UID_CONSISTENT,
            Action.PATID_CONSISTENT,
        }
        and check.path is not None
    ):
        action = _policy_action(rules, check.path)
        if action is not None and action != KEEP:
            return Scored(Result.FAILED, action, deliberate=True)
    return scored


def _policy_action(rules: ElementRules, path: AttributePath) -> str | None:
    """Return the first action on ``path`` that does not keep, outermost first.

    A sequence that the policy removes or empties takes the attribute in it
    with it, whatever the attribute's own action.
    """
    tags = [_rule_tag(element) for element in path.elements]
    for depth, tag in enumerate(tags):
        try:
            action = rules.rule(tag, tags[:depth]).action
        except ValueError:
            return None
        if action != KEEP:
            return action
    return KEEP


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
    action = check.action
    if action is None:
        return Scored(Result.NOT_EVALUATED, "unknown action")
    if action in _NOT_EVALUATED_ACTIONS:
        return Scored(Result.NOT_EVALUATED, _NOT_EVALUATED_ACTIONS[action])
    if action is Action.PIXELS_RETAINED:
        if check.action_text is None:
            return Scored(Result.NOT_EVALUATED, "no digest")
        pixels = dataset.get(0x7FE00010)
        if pixels is None or not isinstance(pixels.value, bytes):
            return Scored(Result.FAILED)
        digest = hashlib.md5(pixels.value, usedforsecurity=False).hexdigest()
        return _passed(digest == check.action_text.strip().lower())
    if check.path is None:
        return Scored(
            Result.NOT_EVALUATED,
            "unreadable place" if check.path_unreadable else "no place",
        )
    element = find_element(dataset, check.path)
    if action is Action.TAG_RETAINED:
        return _passed(element is not None)
    text = None if element is None else element_text(element)
    if action is Action.TEXT_NOTNULL:
        return _passed(bool(text))
    if action is Action.TEXT_RETAINED:
        if check.action_text is None:
            return Scored(Result.NOT_EVALUATED, "no text to compare")
        if not text:
            return Scored(Result.FAILED)
        return compare_text(text, check.action_text, keep=True)
    if action is Action.TEXT_REMOVED:
        if check.action_text is None:
            return Scored(Result.NOT_EVALUATED, "no text to compare")
        if not text:
            return Scored(Result.PASSED)
        return compare_text(text, check.action_text, keep=False)
    if action in (Action.DATE_SHIFTED, Action.UID_CHANGED):
        value = (check.value or "").replace("\\", "")
        if not value:
            return Scored(Result.NOT_EVALUATED, "no value to compare")
        return _passed(value not in (text or "").replace("\\", ""))
    replacements = (
        mapping.uids if action is Action.UID_CONSISTENT else mapping.patient_ids
    )
    if element is None:
        return Scored(Result.PASSED)
    expected = replacements.get(check.value or "")
    if expected is None:
        return Scored(Result.NOT_EVALUATED, "not in the mapping files")
    return _passed(text == expected)


def _passed(passed: bool) -> Scored:
    return Scored(Result.PASSED if passed else Result.FAILED)


_NUMBER = re.compile(r"[0-9]*\.?[0-9]+|[0-9]+\.")
_WORD = re.compile(r"\w+")


def compare_text(text: str, answer: str, *, keep: bool) -> Scored:
    """Compare an attribute's text with the answer key's, ignoring case.

    Two numbers compare as numbers. Otherwise the answer is kept if it is
    within the text, and removed if none of its words is; a text that keeps
    some of its words, but not all, fails both.
    """
    text = text.lower()
    answer = answer.lower()
    if _NUMBER.fullmatch(text) and _NUMBER.fullmatch(answer):
        return _passed((float(text) == float(answer)) == keep)
    if answer in text:
        return _passed(keep)
    words = _WORD.findall(answer)
    if not words:
        return Scored(Result.NOT_EVALUATED, "no words to compare")
    found = sum(word in text for word in words)
    return _passed(found == len(words) if keep else found == 0)


def find_element(
    dataset: pydicom.Dataset, path: AttributePath
) -> pydicom.DataElement | None:
    """Return the element at ``path``, or ``None`` if there is none."""
    current = dataset
    for depth, wanted in enumerate(path.elements):
        element = _element(current, wanted)
        if element is None or depth == len(path.elements) - 1:
            return element
        if element.VR != "SQ":
            return None
        index = path.items[depth]
        if index >= len(element.value):
            return None
        current = element.value[index]
    return None  # pragma: no cover - the loop returns at the last element


def _element(dataset: pydicom.Dataset, wanted: Element) -> pydicom.DataElement | None:
    if not wanted.is_private:
        return dataset.get((wanted.group << 16) | wanted.element)
    for element in dataset:
        tag = element.tag
        if tag.group != wanted.group or tag.element < 0x1000:
            continue
        if tag.element & 0xFF != wanted.element:
            continue
        creator = dataset.get((tag.group << 16) | (tag.element >> 8))
        if (
            creator is not None
            and str(creator.value).strip().upper()
            == (wanted.creator or "").strip().upper()
        ):
            return element
    return None


def element_text(element: pydicom.DataElement) -> str:
    """Return an element's value as text, as the checks compare it.

    A multi-valued value is joined by ``\\``, as it is encoded; bytes are
    read as ISO 8859-1, so that text in them is found; and a sequence is the
    text of every element of its items, joined by spaces.
    """
    value = element.value
    if element.VR == "SQ":
        return " ".join(
            text
            for item in value
            for inner in item
            for text in [element_text(inner)]
            if text
        )
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("latin-1").strip(" \x00")
    if isinstance(value, pydicom.multival.MultiValue):
        return "\\".join(str(each) for each in value).strip(" \x00")
    return str(value).strip(" \x00")


def summarise_script_results(path: str | Path) -> dict[str, object]:
    """Count the validation script's results by answer-key category.

    Parameters
    ----------
    path : str or Path
        The script's ``validation_results.db``.

    Returns
    -------
    dict
        ``categories``: for each category, the checks that the script
        passed, failed, and left blank, ordered as :func:`run_benchmark`
        orders them; and ``results_sha256``, naming the file.

    Raises
    ------
    BenchmarkError
        If the file is not an SQLite database with the script's table.
    """
    path = Path(path)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        connection = sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True)
    except (OSError, sqlite3.Error):
        raise BenchmarkError("the validation results could not be read") from None
    fields = [field.name for field in dataclasses.fields(Categories)]
    try:
        rows = connection.execute(
            f"SELECT action, check_passed, {', '.join(fields)} "  # nosec B608
            f"FROM {SCRIPT_RESULTS_TABLE}"
        ).fetchall()
    except sqlite3.Error:
        raise BenchmarkError(
            f"the validation results have no table {SCRIPT_RESULTS_TABLE!r} "
            "with the script's columns"
        ) from None
    finally:
        connection.close()
    counts: dict[Category | None, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    for action_text, passed, *codes in rows:
        name = action_text.strip("<>") if isinstance(action_text, str) else ""
        try:
            action: Action | None = Action(name)
        except ValueError:
            action = None
        categories = Categories(
            *(code if isinstance(code, str) and code else None for code in codes)
        )
        outcome = {1: "passed", 0: "failed"}.get(
            int(passed) if isinstance(passed, (int, float)) else -1, "blank"
        )
        counts[category_of(action, categories)][outcome] += 1
    return {
        "results_sha256": digest,
        "categories": [
            {
                "family": None if category is None else category.family,
                "code": None if category is None else category.code,
                "passed": tally["passed"],
                "failed": tally["failed"],
                "blank": tally["blank"],
            }
            for category, tally in sorted(
                counts.items(), key=lambda pair: _category_order(pair[0])
            )
        ],
    }


def render_markdown(document: Mapping[str, object]) -> str:
    """Render a benchmark's results as CommonMark."""
    versions = document["versions"]
    coverage = document["coverage"]
    assert isinstance(versions, Mapping) and isinstance(coverage, Mapping)
    lines = [
        "# MIDI benchmark results",
        "",
        f"Format `{document['format']}`. Development results: the NCI "
        "validation script's own results, from the mapping files that the "
        "run wrote, are the published figures (D-018).",
        "",
        "## Versions",
        "",
        "| Item | Version |",
        "| --- | --- |",
        *(f"| {name} | {_cell(value)} |" for name, value in versions.items()),
        "",
        "## Supported coverage",
        "",
        "Answer-key instances by where they ended up:",
        "",
        _table(
            ("Modality", *(context.value for context in Context)),
            [
                (modality, *by.values())
                for modality, by in coverage["by_modality"].items()
            ]
            + [("All", *coverage["instances"].values())],
        ),
        "",
    ]
    reasons = coverage["withheld_reasons"]
    if reasons:
        lines += [
            "Reasons the run gave for withheld instances:",
            "",
            _table(("Reason", "Times given"), list(reasons.items())),
            "",
        ]
    lines += [
        "## Results by answer-key category",
        "",
        "Checks of released instances passed, failed, failed by a deliberate "
        "difference, or were not evaluated; checks of other instances are "
        "counted where those instances ended up, and not scored.",
        "",
        _table(
            (
                "Category",
                "Passed",
                "Failed",
                "Deliberate",
                "Not evaluated",
                "Withheld",
                "Outside coverage",
                "Not in input",
            ),
            [
                (
                    "unknown"
                    if row["code"] is None
                    else f"{row['family']} {row['code']}",
                    row["passed"],
                    row["failed"],
                    row["deliberate"],
                    row["not_evaluated"],
                    row["withheld"],
                    row["outside_coverage"],
                    row["not_in_input"],
                )
                for row in document["categories"]
            ],
        ),
        "",
        "## Deliberate differences",
        "",
        "Checks that asked for an attribute to be kept, where the policy "
        "removes or replaces it:",
        "",
    ]
    lines += _rows_or_none(
        ("Category", "Action", "Attribute", "Policy action", "Checks"),
        [
            (
                row["category"],
                row["action"],
                row["attribute"],
                row["policy_action"],
                row["checks"],
            )
            for row in document["deliberate_differences"]
        ],
    )
    lines += ["", "## Findings", "", "Every other failed check:", ""]
    lines += _rows_or_none(
        ("Category", "Action", "Attribute", "Checks"),
        [
            (row["category"], row["action"], row["attribute"], row["checks"])
            for row in document["findings"]
        ],
    )
    return "\n".join(lines) + "\n"


def _rows_or_none(header: Sequence[str], rows: list[Sequence[object]]) -> list[str]:
    return [_table(header, rows)] if rows else ["None."]


def _table(header: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines += ["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]
    return "\n".join(lines)


def _cell(value: object) -> str:
    return "none" if value is None else str(value).replace("|", "\\|")
