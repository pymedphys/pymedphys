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

"""Run de-identification over a directory of source files, through a staging area.

A run has five steps:

1. :func:`discover` lists every entry below a source directory, in an order
   that depends only on their relative paths, and numbers them from 0. The
   number is the input's **run position**, the only name by which anything
   the run reports refers to it. A symbolic link or other link is not
   followed, a file that is not a regular file is not opened, and a
   DICOMDIR is never passed through (PS3.15 E.1.1): each is refused.
2. The first pass reads each file once, builds its
   :class:`~pymedphys._dicom.deidentify.references.InstanceRecord`, and
   builds the :class:`~pymedphys._dicom.deidentify.reference_graph.ReferenceGraph`
   of the inputs, before anything is written. Its findings take their
   graded consequences: a study whose instances name several patients
   stops the run with :class:`RunStopped` before any directory is created;
   every copy of a conflicting instance, every instance of a series in
   several studies, and every instance without its SOP Instance, Series
   Instance, or Study Instance UID is sequestered; identical copies are
   processed once, from the first copy that reads unchanged; and a dangling
   reference is reported only.
3. The second pass reads each file again, sequesters it if it is no longer
   the file that discovery found or its bytes differ from the first pass's,
   and gives it to the run's :class:`Transform`. A transform returns the
   output file with its **evidence**, an object of its own that the run
   passes to the gate unread, such as the source values that it removed or
   replaced; or it sequesters the instance, with evidence too. Each output
   file is written to the staging area under a temporary name, and renamed
   into place once its bytes are on disk. An instance that a finding
   sequesters is still transformed, so that its evidence reaches the gate
   of every other file of its subject; its output is never written.
4. Each staged file is read back from disk and given to the run's
   :class:`Gate` with its own evidence and that of every instance of its
   subject that the transform returned evidence for, its own first. The
   gate releases it, holds it for review, or sequesters it. A file that is
   not released is deleted at once. Then the reference graph's second pass,
   the run's :class:`WrittenCheck`, checks the files that the gate released,
   each read back from disk again and recorded as the first pass recorded
   its input before the next is read, against the first pass's graph. A finding of what was
   written, other than a reference to an input that was not written, is a
   fault of the engine, so the run fails closed: it sequesters the
   instances that the finding names, deleting their files, and checks what
   is left again, until nothing but such references remains; a finding
   that names no released instance, or a check that raises, publishes
   nothing (:class:`ReleaseWithheld`), as
   :mod:`~pymedphys._dicom.deidentify.run_written` describes. A reference
   to an input that was withheld, such as a plan's to a sequestered image,
   is reported only, as the first pass reports a dangling reference.
5. The release directory is published by renaming the staging area's
   release tree to it, so it appears whole, holding only files that their
   gate released and any release report, or not at all.

The run decides nothing about an instance's content: the transform and the
gate do. The run fails closed. An exception that either raises, or a result
of the wrong type, sequesters that instance with
:attr:`RunReason.INTERNAL_ERROR`, without its message, which could quote a
value; only :class:`Release` releases a file; and any other failure deletes
the staging area and publishes nothing.

Where the design leaves a detail open, the run takes these defaults:

- an instance whose first pass cannot follow a sequence on the path to a
  reference has no record, and is sequestered;
- the release directory must not exist, so that a run never mixes its
  output with another's;
- the staging area is a directory beside the release directory, named for
  it, created for the run with permissions for its owner alone where the
  platform has them, and removed when the run ends; one left by a run that
  was interrupted holds output that may still identify people, so a run
  refuses to start until someone has reviewed and deleted it;
- the published tree keeps the staging area's permissions, for its owner
  alone, until whoever releases it decides otherwise;
- a file held for review is not published, and its staged bytes are
  deleted.

Nothing here logs, warns, or raises with a source path or value, and
pydicom's warnings and log records, in the thread that runs it, including
those of the transform and the gate, are redacted by
:func:`~pymedphys._dicom.deidentify.diagnostics.redacted_diagnostics`.
Outcomes and findings name inputs by run position, and attributes by tag. The source
paths are held only by the :class:`Discovery`, for the confidential QC
material, and are left out of its ``repr``.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import hashlib
import os
import shutil
import stat
from collections.abc import Callable, Iterator
from pathlib import Path, PurePosixPath
from typing import TypeGuard

from . import output_names, qc_store, release_report, run_qc, run_report, run_written
from .diagnostics import redacted_diagnostics
from .file_layout import Region, read_file_layout
from .reference_graph import (
    Finding,
    FindingKind,
    ReferenceGraph,
    build_reference_graph,
)
from .references import InstanceRecord, UnreadableSequence
from .reasons import RunReason

# discover and ReleaseWithheld are part of the run's interface, from here.
from .run_discovery import (  # pylint: disable = unused-import
    Discovery,
    RunError,
    _Entry,
    discover,
)
from .run_results import (
    NO_EVIDENCE,
    Gate,
    HoldForReview,
    Release,
    Sequestered,
    Transform,
    Transformed,
    WrittenCheck,
)
from .run_written import ReleaseWithheld  # pylint: disable = unused-import
from .written_references import WrittenFinding

# Media Storage SOP Class UID of a DICOMDIR: the Media Storage Directory
# Storage SOP Class (PS3.4 Annex F, PS3.6 Table A-1).
MEDIA_STORAGE_DIRECTORY_STORAGE = "1.2.840.10008.1.3.10"
_MEDIA_STORAGE_SOP_CLASS = "(0002,0002)"
_DIRECTORY_RECORD_SEQUENCE = "(0004,1220)"
STAGING_SUFFIX = ".staging"
# The staging area's tree that becomes the release directory.
_STAGED_RELEASE = "release"
_PARTIAL_SUFFIX = ".partial"
# Without long path support, Windows limits a file's path to 259 characters.
_WINDOWS_MAX_PATH = 259


class RunStopped(Exception):
    """A run stopped by the first pass before anything was written.

    Attributes
    ----------
    findings : tuple of Finding
        The findings that stopped it, by run position.
    """

    def __init__(self, findings: tuple[Finding, ...]) -> None:
        super().__init__(findings)
        self.findings = findings

    def __str__(self) -> str:
        studies = len(self.findings)
        return (
            f"the run stopped before writing anything: {studies} "
            f"{'study names' if studies == 1 else 'studies name'} several patients"
        )


class Status(enum.Enum):
    """What happened to an input."""

    RELEASED = "released"  # written to the release directory
    DUPLICATE = "duplicate"  # an identical copy of a released input
    HELD_FOR_REVIEW = "held-for-review"  # withheld until it is reviewed
    SEQUESTERED = "sequestered"  # withheld from the release
    REFUSED = "refused"  # not an instance that the run can read


# The first pass's findings that sequester the inputs that they name.
_SEQUESTERING_FINDINGS = (
    FindingKind.MISSING_IDENTIFIER,
    FindingKind.CONFLICTING_INSTANCE,
    FindingKind.SERIES_IN_SEVERAL_STUDIES,
)


@dataclasses.dataclass(frozen=True)
class Outcome:
    """What happened to one input.

    Attributes
    ----------
    position : int
    status : Status
    reasons : tuple
        Why it was refused, sequestered, or held: :class:`RunReason`
        members, the first pass's
        :class:`~pymedphys._dicom.deidentify.reference_graph.FindingKind`, or
        the value-free objects that its transform or gate gave.
    output : PurePosixPath or None
        For a released input, or a duplicate of one, its file below the
        release directory.
    duplicate_of : int or None
        For an identical copy of another input, the position of the copy
        that was processed. A copy takes that copy's status and reasons,
        except that a copy of a released input is a duplicate.
    label : str or None
        For a sequestered input, the opaque per-run label by which the
        release report refers to it, from
        :func:`~pymedphys._dicom.deidentify.release_report.sequestration_labels`;
        only the QC pack maps labels to sources (D-026).
    """

    position: int
    status: Status
    reasons: tuple[object, ...] = ()
    output: PurePosixPath | None = None
    duplicate_of: int | None = None
    label: str | None = None


@dataclasses.dataclass(frozen=True)
class RunResult:
    """What a run did, without a source value or path.

    Attributes
    ----------
    release : Path
        The release directory, as published.
    outcomes : tuple of Outcome
        One for each run position, in order.
    findings : tuple of Finding
        The first pass's findings, by run position.
    written_findings : tuple of WrittenFinding
        The second reference pass's findings, by run position, once each:
        those that sequestered the instances they name, check by check,
        then those of its last check, which name a reference to an input
        that was not written and are reported only. Empty without a
        :class:`WrittenCheck`.
    staging_removed : bool
        Whether the staging area was deleted. If it was not, it may hold
        output that still identifies people, and needs deleting by hand.
    qc_pack : Path or None
        The QC pack that the run wrote, which :func:`run` always gives.
    """

    release: Path
    outcomes: tuple[Outcome, ...]
    findings: tuple[Finding, ...]
    written_findings: tuple[WrittenFinding, ...] = ()
    staging_removed: bool = True
    qc_pack: Path | None = None


def staging_path(release: str | os.PathLike[str]) -> Path:
    """Return the staging area of a release directory: beside it, named for it.

    It is on the release directory's file system, so that publishing is one
    rename, and outside it, so that nothing staged is ever in the release.
    """
    release = Path(release)
    return release.with_name(f".{release.name}{STAGING_SUFFIX}")


def run(
    discovery: Discovery,
    release: str | os.PathLike[str],
    transform: Transform,
    gate: Gate,
    *,
    qc_destination: str | os.PathLike[str],
    reporter: run_report.Reporter | None = None,
    written_check: WrittenCheck | None = None,
) -> RunResult:
    """De-identify the discovered inputs into a new release directory.

    Parameters
    ----------
    discovery : Discovery
        From :func:`discover`.
    release : str or os.PathLike
        The release directory, which must not exist. Its parent must.
    transform : Transform
        Called once for each instance with a record, in run order, other
        than identical copies and inputs that changed during the run.
    gate : Gate
        Called once for each staged file, in run order, after every
        instance has been transformed.
    qc_destination : str or os.PathLike
        Where the run writes its confidential QC pack: a directory that
        does not exist, or is empty, outside the source and release
        directories and the release's staging area, as
        :func:`~pymedphys._dicom.deidentify.qc_store.check_confidential_destination`
        checks before anything is created. There is no default (D-016).
    reporter : Reporter, optional
        Given the labelled outcomes, each input's QC material, and the QC
        pack's reference, returns the report's text, published at the root as
        :data:`~pymedphys._dicom.deidentify.run_report.RELEASE_REPORT`, with
        its human-readable form and its policy's conformance statement beside
        it, as :func:`~pymedphys._dicom.deidentify.run_report.release_files`
        gives them. Without one, neither is written. A withheld input whose reasons
        the reporter does not admit is sequestered for
        :attr:`RunReason.INVALID_REASON`, followed by its own reasons.
    written_check : WrittenCheck, optional
        The reference graph's second pass under the run's key, such as an
        :class:`~pymedphys._dicom.deidentify.instance_transform.InstanceTransform`'s
        ``written_check``, called on the released files once every staged
        file is gated. An instance whose written file it finds at fault, or
        that cannot be recorded to check, is sequestered for
        :attr:`RunReason.INCONSISTENT_REFERENCES`. Without one, what was
        written is not checked, which only a transform that writes no
        keyed replacements, such as a test's, should leave out.

    Returns
    -------
    RunResult

    Raises
    ------
    RunError
        If the release directory or its staging area exists, the release
        directory would be inside the source directory, or, on Windows, its
        files' paths could be too long; or if the release could not be
        published and its QC pack could not be removed, naming the QC
        destination. Otherwise, the error that stopped the publication is
        raised once the pack is removed.
    RunStopped
        If a study's instances name several patients. Nothing is created.
    ReleaseWithheld
        If the second reference pass raises, or finds a fault that names no
        released instance. Nothing is published, and no QC pack is written.
    ~pymedphys._dicom.deidentify.qc_pack.QcPackError
        If the QC destination is refused, or the pack cannot be built or
        written. Nothing is published.
    TypeError
        If a transform's or gate's QC material is not a tuple of the
        material types of :mod:`~pymedphys._dicom.deidentify.run_qc`.
        Nothing is published.
    ~pymedphys._dicom.deidentify.release_report.ReleaseReportError
        If the report has a field that could hold a value or a path, or a
        reason that no stage gives; so does whatever the reporter raises, or
        a ``ReleaseReportMarkdownError`` for a report with no readable form.
        Nothing is published, and no QC pack is written.

    Notes
    -----
    Between the check that the release directory does not exist and the
    rename that publishes it, another process could create it. On POSIX,
    the rename then replaces it if it is empty, and fails otherwise; on
    Windows, it fails.
    """
    # pydicom converts values when they are first read, in the first pass
    # and in the transform and gate, and its warnings and log records can
    # quote them.
    with redacted_diagnostics():
        release_path = Path(release).absolute()
        return _run(
            discovery,
            release_path,
            transform,
            gate,
            qc_destination,
            reporter,
            written_check,
        )


def _run(  # pylint: disable = too-many-arguments, too-many-positional-arguments, too-many-locals
    discovery: Discovery,
    release_path: Path,
    transform: Transform,
    gate: Gate,
    qc_destination: str | os.PathLike[str],
    reporter: run_report.Reporter | None,
    written_check: WrittenCheck | None,
) -> RunResult:
    staging = staging_path(release_path)
    _check_directories(discovery.source, release_path, staging)
    apart = {
        "release_directory": release_path,
        "staging_directory": staging,
        "source_directory": discovery.source,
    }
    qc_store.check_confidential_destination(qc_destination, **apart)

    first = _first_pass(discovery)
    stopping = tuple(
        finding
        for finding in first.findings
        if finding.kind is FindingKind.STUDY_WITH_SEVERAL_PATIENTS
    )
    if stopping:
        raise RunStopped(stopping)

    try:
        staging.mkdir(mode=0o700)
    except FileExistsError:
        raise RunError(_STAGING_EXISTS.format(staging=staging)) from None
    removed = False
    try:
        outcomes, material, written = _stage_and_gate(
            discovery, first, staging, transform, gate, written_check
        )
        material = run_qc.with_reported_findings(material, first.findings)
        if reporter is not None:
            outcomes = _admitted(outcomes, reporter)
        outcomes = _labelled(outcomes)
        pack = run_qc.qc_pack_of(discovery.paths, outcomes, material)
        # Built before the pack is written, so a failure leaves no QC material.
        files = run_report.documents(reporter, outcomes, material, pack.reference)
        staged_release = staging / _STAGED_RELEASE
        staged_release.mkdir(exist_ok=True, mode=0o700)
        _remove_empty_directories(staged_release)
        for name, data in files.items():
            _write_atomically(staged_release / name, data)
        if os.path.lexists(release_path):
            raise RunError(_RELEASE_EXISTS.format(release=release_path))
        # The pack is written before the release is published, so that a
        # release never exists without its QC material.
        qc_pack = qc_store.write_qc_pack(pack, qc_destination, **apart)
        try:
            os.rename(staged_release, release_path)
        except OSError:
            # Nor does a pack outlive a release that was not published.
            if not qc_store.withdraw_qc_pack(qc_pack.parent):
                raise RunError(_PACK_LEFT.format(destination=qc_pack.parent)) from None
            raise
        _sync_directory(release_path.parent)
    finally:
        removed = _remove(staging)
    return RunResult(release_path, outcomes, first.findings, written, removed, qc_pack)


def _remove_empty_directories(root: Path) -> None:
    """Remove each directory below ``root`` that holds no file, deepest first.

    A withheld file's patient, study, or series directory is otherwise
    published empty, which says that something was withheld there.
    """
    for directory, _, _ in os.walk(root, topdown=False):
        # Deepest first, so a directory that held only empty ones is empty.
        if Path(directory) != root and not os.listdir(directory):
            os.rmdir(directory)


def _admitted(
    outcomes: tuple[Outcome, ...], reporter: run_report.Reporter
) -> tuple[Outcome, ...]:
    """Sequester each withheld input whose reasons the reporter cannot give."""
    # Its own reasons follow, for the QC pack; the report gives the first alone.
    return tuple(
        dataclasses.replace(
            outcome,
            status=Status.SEQUESTERED,
            reasons=(RunReason.INVALID_REASON, *outcome.reasons),
        )
        if outcome.status in (Status.SEQUESTERED, Status.HELD_FOR_REVIEW)
        and not reporter.admits(outcome.status.value, outcome.reasons)
        else outcome
        for outcome in outcomes
    )


def _labelled(outcomes: tuple[Outcome, ...]) -> tuple[Outcome, ...]:
    """Give each sequestered outcome its opaque label for the run (D-026)."""
    sequestered = [
        outcome.position for outcome in outcomes if outcome.status is Status.SEQUESTERED
    ]
    labels = dict(
        zip(sequestered, release_report.sequestration_labels(len(sequestered)))
    )
    return tuple(
        dataclasses.replace(outcome, label=labels[outcome.position])
        if outcome.position in labels
        else outcome
        for outcome in outcomes
    )


_RELEASE_EXISTS = "the release directory {release} already exists"
_PACK_LEFT = (
    "the release could not be published, and the QC pack in {destination} "
    "could not be removed; it holds source paths and values, so delete it "
    "before running again"
)
_STAGING_EXISTS = (
    "the staging area {staging} already exists, perhaps from a run that was "
    "interrupted; it may hold output that still identifies people, so review "
    "and delete it before running again"
)


def _check_directories(source: Path, release: Path, staging: Path) -> None:
    if os.path.lexists(release):
        raise RunError(_RELEASE_EXISTS.format(release=release))
    if os.path.lexists(staging):
        raise RunError(_STAGING_EXISTS.format(staging=staging))
    if not release.parent.is_dir():
        raise RunError(
            f"the parent of the release directory {release} is not a directory"
        )
    # The release directory does not exist, so it cannot hold the source.
    # Comparing directories rather than names also covers file systems that
    # ignore case.
    parent = release.parent.resolve()
    for directory in (parent, *parent.parents):
        if os.path.samefile(directory, source):
            raise RunError(
                f"the release directory {release} must not be inside the "
                "source directory"
            )
    longest = (
        len(str(staging / _STAGED_RELEASE))
        + 1
        + output_names.MAX_RELATIVE_PATH_LENGTH
        + len(_PARTIAL_SUFFIX)
    )
    if os.name == "nt" and longest > _WINDOWS_MAX_PATH:
        raise RunError(
            f"the release directory {release} is too deep for the paths of "
            f"its files to fit within {_WINDOWS_MAX_PATH} characters"
        )


@dataclasses.dataclass(frozen=True)
class _FirstPass:
    records: dict[int, InstanceRecord]
    # The graph of the records, whose positions are indices of ``positions``.
    graph: ReferenceGraph
    # The run position of each of the graph's positions.
    positions: tuple[int, ...]
    digests: dict[int, bytes]
    findings: tuple[Finding, ...]
    # The outcome of each position that the second pass does not process.
    settled: dict[int, Outcome]
    # Each group of identical copies, by its first position.
    copies: dict[int, tuple[int, ...]]
    # The positions that a finding sequesters, which are transformed only
    # for their evidence.
    sequestered: frozenset[int]


def _first_pass(discovery: Discovery) -> _FirstPass:
    records: dict[int, InstanceRecord] = {}
    digests: dict[int, bytes] = {}
    settled: dict[int, Outcome] = {}
    for position, entry in enumerate(discovery.entries):
        if entry.refusal is not None:
            settled[position] = _outcome(position, Status.REFUSED, entry.refusal)
            continue
        data = _read(entry)
        if data is None:
            settled[position] = _outcome(
                position, Status.REFUSED, RunReason.UNREADABLE_FILE
            )
            continue
        digests[position] = hashlib.sha256(data).digest()
        if _is_dicomdir(data):
            settled[position] = _outcome(position, Status.REFUSED, RunReason.DICOMDIR)
            continue
        try:
            records[position] = InstanceRecord.from_file(data)
        except UnreadableSequence:
            settled[position] = _outcome(
                position, Status.SEQUESTERED, RunReason.UNREADABLE_SEQUENCE
            )
        # pydicom raises many types for a file that it cannot read, and its
        # message can quote a value, so none is kept.
        except Exception:  # pylint: disable = broad-exception-caught
            settled[position] = _outcome(
                position, Status.REFUSED, RunReason.NOT_READABLE_AS_DICOM
            )

    positions = tuple(records)
    graph = build_reference_graph([records[position] for position in positions])
    findings = tuple(
        dataclasses.replace(
            finding,
            instances=tuple(
                tuple(positions[index] for index in group)
                for group in finding.instances
            ),
        )
        for finding in graph.findings
    )
    kinds: dict[int, list[FindingKind]] = collections.defaultdict(list)
    copies = {}
    for finding in findings:
        if finding.kind in _SEQUESTERING_FINDINGS:
            for group in finding.instances:
                for position in group:
                    if finding.kind not in kinds[position]:
                        kinds[position].append(finding.kind)
        elif finding.kind is FindingKind.DUPLICATE_INSTANCE:
            (group,) = finding.instances
            copies[group[0]] = group
    for position, found in kinds.items():
        settled[position] = _outcome(position, Status.SEQUESTERED, *found)
    return _FirstPass(
        records,
        graph,
        positions,
        digests,
        findings,
        settled,
        copies,
        frozenset(kinds),
    )


def _read(entry: _Entry) -> bytes | None:
    """Return the bytes of the regular file that discovery found, or ``None``.

    The file is opened without following a symbolic link, or blocking on a
    named pipe, and must still be the file that discovery found.
    """
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(entry.path, flags)
    except OSError:
        return None
    try:
        details = os.fstat(descriptor)
        found = (details.st_dev, details.st_ino)
        if not stat.S_ISREG(details.st_mode) or found != (entry.device, entry.inode):
            return None
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            return handle.read()
    except OSError:
        return None
    finally:
        os.close(descriptor)


def _is_dicomdir(data: bytes) -> bool:
    """Whether a file is a DICOMDIR, by its SOP Class or its directory records."""
    try:
        layout = read_file_layout(data)
    # A file whose layout cannot be read is left to its record to refuse.
    except Exception:  # pylint: disable = broad-exception-caught
        return False
    for extent in layout.elements:
        element = extent.location.element
        if element is None:
            continue
        if (
            extent.location.region is Region.FILE_META
            and element.tag == _MEDIA_STORAGE_SOP_CLASS
            and data[extent.value_start : extent.end].rstrip(b"\x00 ")
            == MEDIA_STORAGE_DIRECTORY_STORAGE.encode()
        ):
            return True
        if not element.items and element.tag == _DIRECTORY_RECORD_SEQUENCE:
            return True
    return False


def _outcome(position: int, status: Status, *reasons: object) -> Outcome:
    return Outcome(position, status, tuple(reasons))


@dataclasses.dataclass(frozen=True)
class _Staged:
    position: int
    path: PurePosixPath
    file: Path
    digest: bytes
    evidence: object
    subject: object


# The subject of every instance without a Patient ID, apart from every
# identity, as the first pass counts them.
_WITHOUT_PATIENT_ID = object()


def _stage_and_gate(  # pylint: disable = too-many-locals, too-many-branches, too-many-arguments, too-many-positional-arguments
    discovery: Discovery,
    first: _FirstPass,
    staging: Path,
    transform: Transform,
    gate: Gate,
    written_check: WrittenCheck | None,
) -> tuple[
    tuple[Outcome, ...], dict[int, tuple[object, ...]], tuple[WrittenFinding, ...]
]:
    outcomes: dict[int, Outcome] = dict(first.settled)
    # The QC material of each position, from its transform and gate.
    material: dict[int, tuple[object, ...]] = collections.defaultdict(tuple)
    staged: dict[str, _Staged] = {}
    # File names that several instances gave: none of them is written.
    shared: set[str] = set()
    evidence: dict[object, list[object]] = collections.defaultdict(list)
    release = staging / _STAGED_RELEASE
    later = {position for group in first.copies.values() for position in group[1:]}
    # Each copy that follows another, and the copy it follows.
    following: dict[int, int] = {}

    for start, record in first.records.items():
        if start in later or (start in outcomes and start not in first.sequestered):
            continue
        # The first copy of a group that reads unchanged is processed.
        group = first.copies.get(start, (start,))
        position, data = start, None
        for candidate in group:
            data = _second_read(discovery, first, candidate)
            if data is not None:
                position = candidate
                break
            if candidate not in first.sequestered:
                outcomes[candidate] = _outcome(
                    candidate, Status.SEQUESTERED, RunReason.CHANGED_DURING_RUN
                )
        subject = _WITHOUT_PATIENT_ID if record.patient is None else record.patient
        if data is None:
            evidence[subject].append(NO_EVIDENCE)
            continue
        following.update((copy, position) for copy in group if copy > position)

        result = _guarded(transform, data, record)
        material[position] += _material(result)
        given = (
            result.evidence if isinstance(result, (Transformed, Sequestered)) else None
        )
        evidence[subject].append(NO_EVIDENCE if given is None else given)
        if position in first.sequestered:
            continue  # transformed only for its evidence
        if not _is_transformed(result):
            outcomes[position] = _withheld(position, Status.SEQUESTERED, result)
            continue
        if not _is_output_name(result.path):
            outcomes[position] = _outcome(
                position, Status.SEQUESTERED, RunReason.INVALID_OUTPUT_NAME
            )
            continue
        # A file's name is its replacement SOP Instance UID, so instances
        # that share one are never renamed: all are withheld.
        name = result.path.name
        if name in staged or name in shared:
            shared.add(name)
            other = staged.pop(name, None)
            if other is not None:
                other.file.unlink()
                outcomes[other.position] = _outcome(
                    other.position, Status.SEQUESTERED, RunReason.SHARED_OUTPUT_NAME
                )
            outcomes[position] = _outcome(
                position, Status.SEQUESTERED, RunReason.SHARED_OUTPUT_NAME
            )
            continue
        file = release.joinpath(*result.path.parts)
        _write_atomically(file, result.data)
        staged[name] = _Staged(
            position,
            result.path,
            file,
            hashlib.sha256(result.data).digest(),
            result.evidence,
            subject,
        )

    for entry in sorted(staged.values(), key=lambda entry: entry.position):
        outcomes[entry.position], gated = _gate(entry, evidence[entry.subject], gate)
        material[entry.position] += gated

    written: tuple[WrittenFinding, ...] = ()
    if written_check is not None:
        released = [
            entry
            for entry in sorted(staged.values(), key=lambda entry: entry.position)
            if outcomes[entry.position].status is Status.RELEASED
        ]
        written = _check_written(first, released, outcomes, written_check)

    for copy, processed in following.items():
        outcome = outcomes[processed]
        if outcome.status is Status.RELEASED:
            outcome = dataclasses.replace(outcome, status=Status.DUPLICATE)
        outcomes[copy] = dataclasses.replace(
            outcome, position=copy, duplicate_of=processed
        )
    return (
        tuple(outcomes[position] for position in range(len(discovery.entries))),
        dict(material),
        written,
    )


def _check_written(
    first: _FirstPass,
    released: list[_Staged],
    outcomes: dict[int, Outcome],
    written_check: WrittenCheck,
) -> tuple[WrittenFinding, ...]:
    """Run the second reference pass on the released files, as read back.

    Each file that it withholds, or that changed since it was staged, is
    deleted and sequestered.
    """
    withheld: dict[int, RunReason] = {}

    def read_back() -> Iterator[tuple[int, bytes]]:
        # One file at a time, so only one file's bytes are held at once.
        for entry in released:
            written = entry.file.read_bytes()
            if hashlib.sha256(written).digest() == entry.digest:
                yield entry.position, written
            else:
                withheld[entry.position] = RunReason.STAGED_FILE_CHANGED

    findings, faulty = run_written.second_pass(
        first.graph, first.positions, read_back(), written_check
    )
    withheld.update(faulty)
    for entry in released:
        if entry.position in withheld:
            entry.file.unlink()
            outcomes[entry.position] = _outcome(
                entry.position, Status.SEQUESTERED, withheld[entry.position]
            )
    return findings


def _material(result: object) -> tuple[object, ...]:
    """Return the QC material that a transform's or gate's result carries."""
    if isinstance(result, (Transformed, Sequestered, HoldForReview, Release)):
        qc = result.qc
        if not isinstance(qc, tuple):
            # Material a reviewer needs is never dropped unseen.
            raise TypeError("QC material must be a tuple")
        return qc
    return ()


def _second_read(discovery: Discovery, first: _FirstPass, position: int):
    """Return the file again if it is unchanged since the first pass."""
    data = _read(discovery.entries[position])
    if data is None or hashlib.sha256(data).digest() != first.digests[position]:
        return None
    return data


def _gate(
    entry: _Staged, pooled: list[object], gate: Gate
) -> tuple[Outcome, tuple[object, ...]]:
    """Gate a staged file, deleting it unless it is released.

    Return its outcome and the QC material that the gate gave.
    """
    written = entry.file.read_bytes()
    if hashlib.sha256(written).digest() != entry.digest:
        entry.file.unlink()
        changed = _outcome(
            entry.position, Status.SEQUESTERED, RunReason.STAGED_FILE_CHANGED
        )
        return changed, ()
    own = entry.evidence
    others = tuple(item for item in pooled if item is not own)
    subject = others if own is None else (own, *others)
    verdict = _guarded(gate, written, own, subject)
    gated = _material(verdict)
    if isinstance(verdict, Release):
        return Outcome(entry.position, Status.RELEASED, output=entry.path), gated
    entry.file.unlink()
    status = (
        Status.HELD_FOR_REVIEW
        if isinstance(verdict, HoldForReview)
        else Status.SEQUESTERED
    )
    return _withheld(entry.position, status, verdict), gated


def _guarded(call: Callable[..., object], *args: object) -> object:
    """Return what ``call(*args)`` returns, or a sequestration if it raises."""
    try:
        return call(*args)
    # Whatever the transform or gate raises, its message could quote a value,
    # so it is not kept, and the instance is not released.
    except Exception:  # pylint: disable = broad-exception-caught
        return Sequestered((RunReason.INTERNAL_ERROR,))


def _is_transformed(result: object) -> TypeGuard[Transformed]:
    return isinstance(result, Transformed) and isinstance(result.data, bytes)


def _withheld(position: int, status: Status, result: object) -> Outcome:
    """Return the outcome of a transform's or gate's decision to withhold."""
    if not isinstance(result, (Sequestered, HoldForReview)):
        return _outcome(position, Status.SEQUESTERED, RunReason.INTERNAL_ERROR)
    reasons = result.reasons
    if (
        not isinstance(reasons, tuple)
        or not reasons
        or not all(_is_value_free(reason) for reason in reasons)
    ):
        return _outcome(position, Status.SEQUESTERED, RunReason.INVALID_REASON)
    return Outcome(position, status, reasons)


def _is_value_free(reason: object) -> bool:
    """Whether a reason is an engine object, which by contract holds no value."""
    if isinstance(reason, enum.Enum):
        return True
    return dataclasses.is_dataclass(reason) and not isinstance(reason, type)


def _is_output_name(path: object) -> bool:
    """Whether ``path`` is one that ``output_names.instance_path`` gives."""
    if not isinstance(path, PurePosixPath) or len(path.parts) != 4:
        return False
    patient, study, series, name = path.parts
    if not name.endswith(output_names.FILE_SUFFIX):
        return False
    try:
        expected = output_names.instance_path(
            patient_id=patient,
            study_instance_uid=study,
            series_instance_uid=series,
            sop_instance_uid=name[: -len(output_names.FILE_SUFFIX)],
        )
    except output_names.OutputNameError:
        return False
    return expected == path


def _write_atomically(file: Path, data: bytes) -> None:
    """Write ``data`` to ``file``, renamed into place once it is on disk."""
    for directory in reversed(file.parents):
        if not directory.exists():
            directory.mkdir(mode=0o700)
            _sync_directory(directory.parent)
    partial = file.with_name(file.name + _PARTIAL_SUFFIX)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(partial, flags, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(partial, file)
    _sync_directory(file.parent)


def _sync_directory(directory: Path) -> None:
    """Flush a directory's entries to disk, where the platform allows it.

    Some file systems, such as some network and FUSE file systems, refuse to
    flush a directory; its entries then reach the disk as they would have
    without the flush.
    """
    if os.name != "posix":
        return
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _remove(staging: Path) -> bool:
    """Delete the staging area, and return whether it is gone."""
    shutil.rmtree(staging, ignore_errors=True)
    return not os.path.lexists(staging)
