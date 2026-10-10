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

"""Compare what independent DICOM validators find in each input and its output.

De-identification must leave each instance conformant with its IOD
(MIDI-BP-03, PS3.15 E.1.1). The engine checks its own output against the
IOD that it generates from PS3.3
(:mod:`~pymedphys._dicom.deidentify.iod_conformance`); this module asks
validators that share none of its code
(:mod:`~pymedphys._dicom.deidentify.dicom_validators`). Inputs are seldom
conformant, and the synthetic corpus deliberately is not, so what matters is
what the de-identification changed: each validator checks each released
instance's input and its output, and each finding that the output gives
more often than its input is **introduced**. What the input already had is
not charged to the de-identification, and what the output no longer has is
counted as **resolved**. ``dcentvfy``, which compares instances, checks the
released inputs of each patient together, and their outputs together.

Each introduced finding is then:

- **explained**, where an entry of the known differences
  (:data:`KNOWN_DIFFERENCES`, :func:`read_known_differences`) matches it.
  Each entry gives the reason, under one of three categories
  (:class:`Category`): a consequence of the profile's own actions, a
  limitation of the validator, or a defect of the engine that is recorded
  until it is fixed. An entry whose reason rests on a property of the output
  names it (:data:`PREMISES`), and explains a finding only in an output
  that has it (:func:`output_premises`);
- **not comparable**, where it lies below an attribute that the validator
  could not parse in the input, because its dictionary lacks it and the
  input is in Implicit VR or gives it the VR UN, while it could parse it in
  the output;
- **unexplained** otherwise. A validator that checked the input but not the
  output gives an unexplained finding too.

A comparison passes when nothing introduced is unexplained.

The results, :meth:`Comparison.json` and :meth:`Comparison.markdown`, hold
no value or path: only versions, counts, SOP Class names, attribute tags and
keywords, message types, and the validators' module and information entity
names. Inputs and outputs are paired by the caller, from a run's outcomes
(:func:`pairs_from_run`) or from the SOP Instance UID mapping that the MIDI
benchmark writes (:func:`pairs_from_uid_mapping`).
"""

from __future__ import annotations

import collections
import concurrent.futures
import csv
import dataclasses
import enum
import fnmatch
import json
import tomllib
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath

from pymedphys._imports import pydicom

from . import dicom_validators as validators
from . import run
from .diagnostics import redacted_diagnostics
from .dicom_validation_markdown import render_markdown
from .dicom_validators import Finding, Status, Validation

SCHEMA = "pymedphys-dicom-validation/1"
KNOWN_DIFFERENCES = Path(__file__).with_name("dicom_validation_known.toml")
RESULTS_JSON = "dicom-validation.json"
RESULTS_MARKDOWN = "dicom-validation.md"
# The message of the finding that a validator gives when it checked an input
# but did not run to the end on its output.
OUTPUT_FAILED = "the validator did not run to the end on the output"
OTHER_SOP_CLASS = "other"

# The Common Instance Reference Module's sequences, which list the instances
# that the rest of an instance references (PS3.3 Section C.12.2).
_REFERENCED_SERIES = 0x00081115
_OTHER_STUDIES = 0x00081200
_REFERENCED_SOP_INSTANCE_UID = 0x00081155
THIS_STUDY_REFERENCED = "instances-of-this-study-referenced-elsewhere"
OTHER_STUDIES_REFERENCED = "instances-of-other-studies-referenced-elsewhere"
# The properties of an output that a known difference can require, each
# with what it means.
PREMISES = {
    THIS_STUDY_REFERENCED: (
        "an instance that Referenced Series Sequence (0008,1115) lists is "
        "referenced outside the Common Instance Reference Module"
    ),
    OTHER_STUDIES_REFERENCED: (
        "an instance that Studies Containing Other Referenced Instances "
        "Sequence (0008,1200) lists is referenced outside the Common Instance "
        "Reference Module"
    ),
}


class Category(enum.Enum):
    """Why a known difference is not a conformance failure of the output."""

    # The action that the profile names for the attribute gives it.
    PROFILE = "profile"
    # A limitation or heuristic of the validator.
    VALIDATOR = "validator"
    # A defect of the engine's output, recorded until it is fixed.
    ENGINE = "engine"


class Outcome(enum.Enum):
    """How an introduced finding is counted."""

    UNEXPLAINED = "unexplained"
    EXPLAINED = "explained"
    NOT_COMPARABLE = "not comparable"


class KnownDifferencesError(Exception):
    """The known differences cannot be read."""


class PairingError(ValueError):
    """A release cannot be paired with its inputs unambiguously.

    The message names no path or UID.
    """


@dataclasses.dataclass(frozen=True)
class KnownDifference:
    """An introduced finding that is explained, and why.

    Attributes
    ----------
    validator, severity, message : str
        As the finding gives them.
    paths : tuple of str
        Patterns of :func:`fnmatch.fnmatchcase` that the finding's path
        matches one of.
    category : Category
        Why it is not a conformance failure of the output.
    reason : str
        The explanation, in a sentence or two.
    requires : str
        One of :data:`PREMISES` that the output must have for this entry to
        explain the finding, or ``""``.
    """

    validator: str
    severity: str
    message: str
    paths: tuple[str, ...]
    category: Category
    reason: str
    requires: str = ""

    def matches(self, finding: Finding, premises: Collection[str] = ()) -> bool:
        """Return whether this entry explains a finding in an output.

        ``premises`` are those of :data:`PREMISES` that the output has.
        """
        return (
            finding.validator == self.validator
            and finding.severity == self.severity
            and finding.message == self.message
            and any(fnmatch.fnmatchcase(finding.path, path) for path in self.paths)
            and (not self.requires or self.requires in premises)
        )


def read_known_differences(
    path: str | Path = KNOWN_DIFFERENCES,
) -> tuple[KnownDifference, ...]:
    """Read the known differences, a TOML file of ``[[difference]]`` tables.

    Each table has the keys ``validator``, ``severity``, ``message``,
    ``paths``, ``category``, and ``reason``, and may have ``requires``, one
    of :data:`PREMISES`.

    Raises
    ------
    KnownDifferencesError
        If a table lacks a key, has another, or names an unknown validator,
        severity, category, or premise.
    """
    with open(path, "rb") as file:
        document = tomllib.load(file)
    keys = {"validator", "severity", "message", "paths", "category", "reason"}
    differences = []
    for number, table in enumerate(document.get("difference", []), start=1):
        if not keys <= set(table) <= keys | {"requires"}:
            raise KnownDifferencesError(
                f"known difference {number} must have exactly the keys "
                + ", ".join(sorted(keys))
                + ", and may have requires"
            )
        if "requires" in table and table["requires"] not in PREMISES:
            raise KnownDifferencesError(f"known difference {number}: unknown premise")
        if table["validator"] not in validators.VALIDATORS:
            raise KnownDifferencesError(f"known difference {number}: unknown validator")
        if table["severity"] not in (validators.ERROR, validators.WARNING):
            raise KnownDifferencesError(f"known difference {number}: unknown severity")
        try:
            category = Category(table["category"])
        except ValueError:
            raise KnownDifferencesError(
                f"known difference {number}: unknown category"
            ) from None
        if not table["paths"] or not all(isinstance(p, str) for p in table["paths"]):
            raise KnownDifferencesError(
                f"known difference {number}: paths must be a list of patterns"
            )
        differences.append(
            KnownDifference(
                table["validator"],
                table["severity"],
                table["message"],
                tuple(table["paths"]),
                category,
                " ".join(table["reason"].split()),
                table.get("requires", ""),
            )
        )
    return tuple(differences)


@dataclasses.dataclass(frozen=True)
class Pair:
    """A released instance's input and output files.

    Attributes
    ----------
    source, output : Path
        Confidential: they never appear in the results.
    """

    source: Path
    output: Path


def pairs_from_run(
    discovery: run.Discovery, result: run.RunResult
) -> tuple[tuple[Pair, ...], int]:
    """Pair each input that a run released with its output.

    Returns the pairs and the number of inputs that the run did not release
    under their own output, whether withheld, refused, or duplicates.
    """
    pairs = []
    for path, outcome in zip(discovery.paths, result.outcomes):
        if outcome.status is run.Status.RELEASED and outcome.output is not None:
            pairs.append(Pair(path, result.release / outcome.output))
    return tuple(pairs), len(result.outcomes) - len(pairs)


def pairs_from_uid_mapping(
    source: str | Path, release: str | Path, mapping: str | Path
) -> tuple[tuple[Pair, ...], int]:
    """Pair inputs with outputs through a mapping of SOP Instance UIDs.

    ``mapping`` is a CSV file with the columns ``id_old`` and ``id_new``,
    such as the MIDI benchmark's UID mapping file, and each output is named
    by its SOP Instance UID with the suffix ``.dcm``, as a run names it.
    Returns the pairs and the number of inputs without an output.

    Raises
    ------
    PairingError
        If the mapping lacks either column or maps an input UID to two
        outputs, if two outputs share a name, or if an output is paired with
        no input, since it would not be validated.
    """
    replacements: dict[str, str] = {}
    with open(mapping, encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if not {"id_old", "id_new"} <= set(reader.fieldnames or ()):
            raise PairingError("the UID mapping needs the columns id_old and id_new")
        for row in reader:
            if replacements.setdefault(row["id_old"], row["id_new"]) != row["id_new"]:
                raise PairingError("the UID mapping maps an input UID to two outputs")
    outputs: dict[str, Path] = {}
    for path in Path(release).rglob("*.dcm"):
        if path.is_file() and outputs.setdefault(path.stem, path) != path:
            raise PairingError("two outputs in the release share a file name")
    discovery = run.discover(source)
    pairs = []
    unpaired = 0
    for path, refusal in zip(discovery.paths, discovery.refusals):
        instance = None if refusal is not None else _header(path).get("instance")
        output = outputs.get(replacements.get(instance or "", ""))
        if output is None:
            unpaired += 1
        else:
            pairs.append(Pair(path, output))
    if len({pair.output for pair in pairs}) < len(outputs):
        raise PairingError(
            "the release has outputs that the UID mapping pairs with no input"
        )
    return tuple(pairs), unpaired


def _header(path: Path) -> dict[str, str]:
    """Return a file's SOP Instance and SOP Class UIDs, and its patient."""
    try:
        with redacted_diagnostics():
            dataset = pydicom.dcmread(
                path,
                stop_before_pixels=True,
                specific_tags=[
                    "SOPInstanceUID",
                    "SOPClassUID",
                    "PatientID",
                    "IssuerOfPatientID",
                ],
            )
    except Exception:  # pylint: disable = broad-exception-caught
        return {}
    keywords = {"instance": "SOPInstanceUID", "sop_class": "SOPClassUID"}
    header = {
        key: str(dataset.get(keyword, "")).strip() for key, keyword in keywords.items()
    }
    patient = str(dataset.get("PatientID", "")).strip(" \x00")
    issuer = str(dataset.get("IssuerOfPatientID", "")).strip(" \x00")
    # A file without a Patient ID names no patient to compare it with.
    header["patient"] = f"{patient}\\{issuer}" if patient else ""
    return header


def output_premises(path: Path) -> frozenset[str]:
    """Return those of :data:`PREMISES` that an output has.

    The UIDs are compared here and never leave this function. A file that
    cannot be read has none.
    """
    try:
        with redacted_diagnostics():
            dataset = pydicom.dcmread(path, stop_before_pixels=True, force=True)
    except Exception:  # pylint: disable = broad-exception-caught
        return frozenset()
    listed: dict[int, set[str]] = {_REFERENCED_SERIES: set(), _OTHER_STUDIES: set()}
    elsewhere: set[str] = set()

    def walk(items: pydicom.Dataset, into: set[str]) -> None:
        for element in items:
            if element.tag == _REFERENCED_SOP_INSTANCE_UID:
                into.add(str(element.value).strip(" \x00"))
            elif element.VR == "SQ":
                for item in element.value or ():
                    walk(item, into)

    try:
        for element in dataset:
            if element.VR != "SQ":
                continue
            into = listed.get(int(element.tag), elsewhere)
            for item in element.value or ():
                walk(item, into)
    except Exception:  # pylint: disable = broad-exception-caught
        return frozenset()
    premises = set()
    if listed[_REFERENCED_SERIES] & elsewhere:
        premises.add(THIS_STUDY_REFERENCED)
    if listed[_OTHER_STUDIES] & elsewhere:
        premises.add(OTHER_STUDIES_REFERENCED)
    return frozenset(premises)


def sop_class_name(uid: str) -> str:
    """Return a standard SOP Class's name, or ``"other"``.

    >>> sop_class_name("1.2.840.10008.5.1.4.1.1.2")
    'CT Image Storage'
    """
    name = pydicom.uid.UID(uid).name
    return OTHER_SOP_CLASS if not uid or name == uid else name


@dataclasses.dataclass(frozen=True)
class Toolset:
    """The validators to run.

    Attributes
    ----------
    dciodvfy, dcentvfy : str or None
        The dicom3tools executables, or ``None`` to skip one.
    standard_path : Path or None
        dicom-validator's directory of DocBook source and tables, or ``None``
        to skip dicom-validator.
    edition : str
        The DICOM edition that dicom-validator checks against.
    """

    dciodvfy: str | None
    dcentvfy: str | None
    standard_path: Path | None
    edition: str

    @classmethod
    def find(
        cls,
        standard_path: str | Path | None,
        edition: str,
        *,
        required: Iterable[str] = validators.VALIDATORS,
    ) -> Toolset:
        """Find each validator, skipping those that are missing and not required.

        dicom-validator is used where ``standard_path`` is given and the
        package can load the edition, which this downloads if need be.

        Raises
        ------
        ~pymedphys._dicom.deidentify.dicom_validators.ValidatorUnavailable
            If a required validator is missing.
        """
        required = frozenset(required)
        found: dict[str, object] = {
            validators.DCIODVFY: validators.find_executable(validators.DCIODVFY),
            validators.DCENTVFY: validators.find_executable(validators.DCENTVFY),
        }
        loaded = None
        if standard_path is not None:
            try:
                validators.DicomValidator.load(standard_path, edition)
                loaded = Path(standard_path)
            except (ImportError, validators.ValidatorUnavailable):
                loaded = None
        found[validators.DICOM_VALIDATOR] = loaded
        missing = sorted(name for name in required if found[name] is None)
        if missing:
            raise validators.ValidatorUnavailable(
                "missing validators: " + ", ".join(missing)
            )
        return cls(
            found[validators.DCIODVFY],  # type: ignore[arg-type]
            found[validators.DCENTVFY],  # type: ignore[arg-type]
            loaded,
            edition,
        )

    def names(self) -> tuple[str, ...]:
        """Return the validators that this toolset runs."""
        present = {
            validators.DCIODVFY: self.dciodvfy,
            validators.DCENTVFY: self.dcentvfy,
            validators.DICOM_VALIDATOR: self.standard_path,
        }
        return tuple(name for name in validators.VALIDATORS if present[name])

    def versions(self) -> validators.Versions:
        """Return the validators' versions."""
        executable = self.dciodvfy or self.dcentvfy
        dicom_validator = (
            None
            if self.standard_path is None
            else validators.DicomValidator.load(self.standard_path, self.edition)
        )
        return validators.Versions(
            dicom3tools=(
                None
                if executable is None
                else validators.dicom3tools_version(executable)
            ),
            dicom_validator=(
                None
                if dicom_validator is None
                else validators.dicom_validator_version()
            ),
            edition=None if dicom_validator is None else self.edition,
            docbook_sha256=(
                {} if dicom_validator is None else dicom_validator.docbook_sha256()
            ),
        )


# Each worker's loaded validators: the toolset, and dicom-validator.
_WORKER: dict[str, object] = {}


def _start_worker(toolset: Toolset) -> None:
    _WORKER["toolset"] = toolset
    _WORKER["dicom_validator"] = (
        None
        if toolset.standard_path is None
        else validators.DicomValidator.load(toolset.standard_path, toolset.edition)
    )


def _validate_file(path: Path) -> tuple[Validation, ...]:
    """Check one file with each of the worker's per-file validators."""
    toolset: Toolset = _WORKER["toolset"]  # type: ignore[assignment]
    done = []
    if toolset.dciodvfy is not None:
        done.append(validators.run_dciodvfy(toolset.dciodvfy, path))
    loaded = _WORKER["dicom_validator"]
    if loaded is not None:
        done.append(loaded.validate(path))  # type: ignore[attr-defined]
    return tuple(done)


@dataclasses.dataclass(frozen=True)
class Introduced:
    """One kind of introduced finding, over every pair that gave it.

    Attributes
    ----------
    finding : Finding
        The finding.
    outcome : Outcome
        How it is counted.
    difference : int or None
        For an explained finding, the number of the known difference that
        explains it, counted from 1 in the order they are read.
    files : int
        How many outputs, or for ``dcentvfy`` how many patients' outputs,
        gave it more often than their inputs.
    occurrences : int
        How many more times, over them all.
    sop_classes : tuple of str
        The SOP Classes of those outputs, for the per-file validators.
    """

    finding: Finding
    outcome: Outcome
    difference: int | None
    files: int
    occurrences: int
    sop_classes: tuple[str, ...]

    def json(self) -> dict[str, object]:
        """Return it as a JSON object."""
        return {
            **self.finding.json(),
            "outcome": self.outcome.value,
            "difference": self.difference,
            "files": self.files,
            "occurrences": self.occurrences,
            "sop_classes": list(self.sop_classes),
        }


@dataclasses.dataclass
class _Tally:
    statuses: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    source: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    output: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    resolved: int = 0


@dataclasses.dataclass(frozen=True)
class Comparison:
    """The comparison of each validator's findings in inputs and outputs.

    Attributes
    ----------
    versions : Versions
        The validators' versions.
    validators : tuple of str
        The validators that ran.
    pairs : int
        The released instances compared.
    unpaired : int
        The inputs without an output of their own.
    sop_classes : Mapping[str, int]
        The released instances by SOP Class.
    tallies : Mapping[str, Mapping[str, object]]
        For each validator: how many pairs, or patients for ``dcentvfy``,
        each validated, failed, or unsupported status combination had, the
        findings in the inputs and in the outputs by severity, and how many
        findings of the inputs the outputs no longer gave.
    introduced : tuple of Introduced
        Each kind of introduced finding, unexplained first.
    known : tuple of KnownDifference
        The known differences that the comparison applied.
    """

    versions: validators.Versions
    validators: tuple[str, ...]
    pairs: int
    unpaired: int
    sop_classes: Mapping[str, int]
    tallies: Mapping[str, Mapping[str, object]]
    introduced: tuple[Introduced, ...]
    known: tuple[KnownDifference, ...] = ()

    @property
    def passed(self) -> bool:
        """Whether a released instance was compared, and nothing introduced is
        unexplained."""
        return self.pairs > 0 and not any(
            i.outcome is Outcome.UNEXPLAINED for i in self.introduced
        )

    def json(self) -> str:
        """Return the comparison as JSON text."""
        document = {
            "schema": SCHEMA,
            "passed": self.passed,
            "versions": self.versions.json(),
            "validators": list(self.validators),
            "pairs": self.pairs,
            "unpaired": self.unpaired,
            "sop_classes": dict(sorted(self.sop_classes.items())),
            "tallies": self.tallies,
            "introduced": [introduced.json() for introduced in self.introduced],
            "known_differences": [
                {
                    "number": number,
                    "validator": difference.validator,
                    "severity": difference.severity,
                    "message": difference.message,
                    "paths": list(difference.paths),
                    "category": difference.category.value,
                    "reason": difference.reason,
                    "requires": PREMISES.get(difference.requires),
                }
                for number, difference in enumerate(self.known, start=1)
            ],
        }
        return json.dumps(document, indent=2) + "\n"

    def markdown(self) -> str:
        """Return the comparison as CommonMark."""
        return render_markdown(json.loads(self.json()))


def compare(  # pylint: disable = too-many-locals
    pairs: Sequence[Pair],
    toolset: Toolset,
    *,
    unpaired: int = 0,
    known: Sequence[KnownDifference] | None = None,
    workers: int = 1,
) -> Comparison:
    """Validate each pair's input and output, and compare the findings.

    ``known`` defaults to :func:`read_known_differences`. ``workers`` is the
    number of processes that run the per-file validators; with 1 they run in
    this process.
    """
    known = read_known_differences() if known is None else tuple(known)
    headers = [_header(pair.source) for pair in pairs]
    sop_classes = [sop_class_name(header.get("sop_class", "")) for header in headers]
    sources = [pair.source for pair in pairs]
    outputs = [pair.output for pair in pairs]
    checked = _validate_files([*sources, *outputs], toolset, workers)
    tallies: dict[str, _Tally] = collections.defaultdict(_Tally)
    introduced: dict[_Kind, list[tuple[int, int, str]]] = collections.defaultdict(list)
    # Only an entry that requires a premise needs the output read again.
    required = any(difference.requires for difference in known)
    for index, sop_class in enumerate(sop_classes):
        premises = output_premises(outputs[index]) if required else frozenset()
        for source, output in zip(checked[index], checked[len(pairs) + index]):
            for kind, count in _introduced(source, output, tallies, known, premises):
                introduced[kind].append((count, index, sop_class))
    if toolset.dcentvfy is not None:
        # dcentvfy stops at a file that dicom3tools cannot read, so the files
        # on which dciodvfy did not run to the end, input or output, are left
        # out of the patient's comparison.
        unreadable = {
            index
            for index in range(len(pairs))
            for validation in (*checked[index], *checked[len(pairs) + index])
            if validation.validator == validators.DCIODVFY
            and validation.status is not Status.VALIDATED
        }
        for group in _patients(headers, unreadable):
            source = validators.run_dcentvfy(
                toolset.dcentvfy, [sources[index] for index in group]
            )
            output = validators.run_dcentvfy(
                toolset.dcentvfy, [outputs[index] for index in group]
            )
            for kind, count in _introduced(source, output, tallies, known):
                introduced[kind].append((count, group[0], ""))
    return Comparison(
        versions=toolset.versions(),
        validators=toolset.names(),
        pairs=len(pairs),
        unpaired=unpaired,
        sop_classes=dict(collections.Counter(sop_classes)),
        tallies={name: _tally_json(tallies[name]) for name in toolset.names()},
        introduced=_ordered(introduced),
        known=known,
    )


def _validate_files(
    paths: Sequence[Path], toolset: Toolset, workers: int
) -> list[tuple[Validation, ...]]:
    if workers <= 1:
        _start_worker(toolset)
        try:
            return [_validate_file(path) for path in paths]
        finally:
            _WORKER.clear()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers, initializer=_start_worker, initargs=(toolset,)
    ) as executor:
        return list(executor.map(_validate_file, paths, chunksize=8))


def _patients(
    headers: Sequence[Mapping[str, str]], left_out: Collection[int]
) -> list[list[int]]:
    """Group the pairs by their inputs' patient, for those of two or more.

    A patient is a Patient ID with its issuer; inputs without a Patient ID
    are left out.
    """
    groups: dict[str, list[int]] = collections.defaultdict(list)
    for index, header in enumerate(headers):
        if index not in left_out and header.get("patient"):
            groups[header["patient"]].append(index)
    return [group for group in groups.values() if len(group) > 1]


def _status(validation: Validation) -> str:
    return validation.status.value


# An introduced finding, its outcome, and the number of the known difference
# that explains it, or None.
_Kind = tuple[Finding, Outcome, "int | None"]


def _introduced(
    source: Validation,
    output: Validation,
    tallies: Mapping[str, _Tally],
    known: Sequence[KnownDifference],
    premises: Collection[str] = (),
) -> Iterable[tuple[_Kind, int]]:
    """Tally one comparison, and yield what the output introduced.

    ``premises`` are those of :data:`PREMISES` that the output has.
    """
    tally = tallies[source.validator]
    tally.statuses[f"input {_status(source)}, output {_status(output)}"] += 1
    for finding, count in source.findings.items():
        tally.source[finding.severity] += count
    for finding, count in output.findings.items():
        tally.output[finding.severity] += count
    if source.status is not Status.VALIDATED:
        # Nothing the output gives can be compared with the input's; the
        # statuses count it.
        return
    if output.status is not Status.VALIDATED:
        failed = Finding(
            output.validator, validators.ERROR, validators.NO_PATH, OUTPUT_FAILED
        )
        yield (failed, *_outcome(failed, source, known, premises)), 1
        return
    gained = collections.Counter(output.findings)
    gained.subtract(source.findings)
    for finding, count in sorted(gained.items()):
        if count > 0:
            yield (finding, *_outcome(finding, source, known, premises)), count
        else:
            tally.resolved -= count


def _outcome(
    finding: Finding,
    source: Validation,
    known: Sequence[KnownDifference],
    premises: Collection[str],
) -> tuple[Outcome, int | None]:
    for number, difference in enumerate(known, start=1):
        if difference.matches(finding, premises):
            return Outcome.EXPLAINED, number
    parts = PurePosixPath(finding.path).parts if finding.path else ()
    for depth in range(1, len(parts)):
        if "/".join(parts[:depth]) in source.unparsed:
            return Outcome.NOT_COMPARABLE, None
    return Outcome.UNEXPLAINED, None


def _tally_json(tally: _Tally) -> dict[str, object]:
    return {
        "statuses": dict(sorted(tally.statuses.items())),
        "input_findings": dict(sorted(tally.source.items())),
        "output_findings": dict(sorted(tally.output.items())),
        "resolved": tally.resolved,
    }


_ORDER = {Outcome.UNEXPLAINED: 0, Outcome.EXPLAINED: 1, Outcome.NOT_COMPARABLE: 2}


def _ordered(
    introduced: Mapping[_Kind, list[tuple[int, int, str]]],
) -> tuple[Introduced, ...]:
    kinds = []
    for (finding, outcome, number), occurrences in introduced.items():
        kinds.append(
            Introduced(
                finding=finding,
                outcome=outcome,
                difference=number,
                files=len({index for _, index, _ in occurrences}),
                occurrences=sum(count for count, _, _ in occurrences),
                sop_classes=tuple(sorted({name for _, _, name in occurrences if name})),
            )
        )
    return tuple(
        sorted(kinds, key=lambda i: (_ORDER[i.outcome], i.finding, i.difference or 0))
    )


def write_results(comparison: Comparison, directory: str | Path) -> None:
    """Write the comparison's JSON and CommonMark into a new directory."""
    directory = Path(directory)
    directory.mkdir()
    (directory / RESULTS_JSON).write_text(
        comparison.json(), encoding="utf-8", newline="\n"
    )
    (directory / RESULTS_MARKDOWN).write_text(
        comparison.markdown(), encoding="utf-8", newline="\n"
    )
