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
   not released is deleted at once.
5. The release directory is published by renaming the staging area's
   release tree to it, so it appears whole, holding only files that their
   gate released, or not at all.

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

from . import output_names, qc_store, release_report, run_qc
from .diagnostics import redacted_diagnostics
from .file_layout import Region, read_file_layout
from .reference_graph import Finding, FindingKind, build_reference_graph
from .references import InstanceRecord, UnreadableSequence
from .run_results import (
    Gate,
    HoldForReview,
    Release,
    Sequestered,
    Transform,
    Transformed,
)

# Media Storage SOP Class UID of a DICOMDIR: the Media Storage Directory
# Storage SOP Class (PS3.4 Annex F, PS3.6 Table A-1).
MEDIA_STORAGE_DIRECTORY_STORAGE = "1.2.840.10008.1.3.10"
_MEDIA_STORAGE_SOP_CLASS = "(0002,0002)"
_DIRECTORY_RECORD_SEQUENCE = "(0004,1220)"
_DICOMDIR_NAME = "DICOMDIR"
STAGING_SUFFIX = ".staging"
# The staging area's tree that becomes the release directory.
_STAGED_RELEASE = "release"
_PARTIAL_SUFFIX = ".partial"
# Without long path support, Windows limits a file's path to 259 characters.
_WINDOWS_MAX_PATH = 259
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class RunError(Exception):
    """A run that cannot start, for a reason in its directories.

    Its message names the release directory or staging area, which the
    caller chose, and never a source path.
    """


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


class RunReason(enum.Enum):
    """Why the run itself refused or sequestered an input."""

    # discovery
    SYMBOLIC_LINK = "symbolic-link"  # or another link, such as a junction
    NOT_A_REGULAR_FILE = "not-a-regular-file"
    DICOMDIR = "dicomdir"
    # the first pass
    UNREADABLE_FILE = "unreadable-file"  # the operating system cannot read it
    NOT_READABLE_AS_DICOM = "not-readable-as-dicom"
    UNREADABLE_SEQUENCE = "unreadable-sequence"
    # the second pass and after
    CHANGED_DURING_RUN = "changed-during-run"
    INVALID_OUTPUT_NAME = "invalid-output-name"
    SHARED_OUTPUT_NAME = "shared-output-name"
    STAGED_FILE_CHANGED = "staged-file-changed"
    INVALID_REASON = "invalid-reason"
    INTERNAL_ERROR = "internal-error"


# The first pass's findings that sequester the inputs that they name.
_SEQUESTERING_FINDINGS = (
    FindingKind.MISSING_IDENTIFIER,
    FindingKind.CONFLICTING_INSTANCE,
    FindingKind.SERIES_IN_SEVERAL_STUDIES,
)


@dataclasses.dataclass(frozen=True)
class _Entry:
    """An entry as discovery found it."""

    path: Path
    refusal: RunReason | None
    device: int
    inode: int


@dataclasses.dataclass(frozen=True, repr=False)
class Discovery:
    """The entries below a source directory, by run position.

    Its ``repr`` shows only how many there are.

    Attributes
    ----------
    source : Path
        The source directory, resolved.
    paths : tuple of Path
        Each entry's path, at its run position. Confidential: they are for
        the QC material alone.
    refusals : tuple of RunReason or None
        For each position, why discovery refused the entry, or ``None`` for
        a regular file.
    """

    source: Path
    entries: tuple[_Entry, ...]

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(entry.path for entry in self.entries)

    @property
    def refusals(self) -> tuple[RunReason | None, ...]:
        return tuple(entry.refusal for entry in self.entries)

    def __repr__(self) -> str:
        refused = sum(entry.refusal is not None for entry in self.entries)
        return f"Discovery(entries={len(self.entries)}, refused={refused})"


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
    staging_removed : bool
        Whether the staging area was deleted. If it was not, it may hold
        output that still identifies people, and needs deleting by hand.
    qc_pack : Path or None
        The QC pack that the run wrote, which :func:`run` always gives.
    """

    release: Path
    outcomes: tuple[Outcome, ...]
    findings: tuple[Finding, ...]
    staging_removed: bool = True
    qc_pack: Path | None = None


def discover(source: str | os.PathLike[str]) -> Discovery:
    """List every entry below a source directory, by run position.

    Entries are ordered by their paths relative to ``source``, compared
    component by component as the bytes that the file system holds, so the
    order is the same on every run. A directory is descended and is not an
    entry itself. A symbolic link, to a directory or a file, or another
    link, such as a Windows junction, is an entry that is refused and not
    followed; any other entry that is not a regular file, such as a named
    pipe, is refused without being opened; and a regular file named
    ``DICOMDIR``, in any case, is refused, as is one that the first pass
    finds to be a DICOMDIR.

    Parameters
    ----------
    source : str or os.PathLike
        The source directory. A symbolic link to it is followed.

    Returns
    -------
    Discovery

    Raises
    ------
    RunError
        If ``source`` is not a directory, or a directory below it cannot be
        listed. The message names no path.
    """
    root = Path(source)
    try:
        root = root.resolve()
        is_directory = root.is_dir()
    except OSError:
        is_directory = False
    if not is_directory:
        raise RunError("the source is not a directory that can be read")
    try:
        found = list(_walk(root))
    except OSError:
        raise RunError("a directory below the source cannot be listed") from None
    found.sort(
        key=lambda entry: tuple(
            os.fsencode(part) for part in entry.path.relative_to(root).parts
        )
    )
    return Discovery(root, tuple(found))


def _walk(root: Path) -> Iterator[_Entry]:
    """Yield every entry below ``root``, without recursion or following links."""
    pending = [root]
    while pending:
        with os.scandir(pending.pop()) as listing:
            entries = list(listing)
        for entry in entries:
            path = Path(entry.path)
            details = entry.stat(follow_symlinks=False)
            refusal = None
            if _is_link(entry, details):
                refusal = RunReason.SYMBOLIC_LINK
            elif stat.S_ISDIR(details.st_mode):
                pending.append(path)
                continue
            elif not stat.S_ISREG(details.st_mode):
                refusal = RunReason.NOT_A_REGULAR_FILE
            elif entry.name.upper() == _DICOMDIR_NAME:
                refusal = RunReason.DICOMDIR
            else:
                # On Windows, a directory entry's own stat has no device or
                # inode, which reading the file compares.
                details = os.lstat(path)
            yield _Entry(path, refusal, details.st_dev, details.st_ino)


def _is_link(entry: os.DirEntry, details: os.stat_result) -> bool:
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, "is_junction", None)  # Python 3.12 and later
    if is_junction is not None and is_junction():
        return True
    attributes = getattr(details, "st_file_attributes", 0)  # Windows
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


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
        does not exist, or is empty, outside the release directory and its
        staging area, as
        :func:`~pymedphys._dicom.deidentify.qc_store.check_confidential_destination`
        checks before anything is created. There is no default (D-016).

    Returns
    -------
    RunResult

    Raises
    ------
    RunError
        If the release directory or its staging area exists, the release
        directory would be inside the source directory, or, on Windows, its
        files' paths could be too long.
    RunStopped
        If a study's instances name several patients. Nothing is created.
    ~pymedphys._dicom.deidentify.qc_pack.QcPackError
        If the QC destination is refused, or the pack cannot be built or
        written. Nothing is published.

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
        return _run(
            discovery, Path(release).absolute(), transform, gate, qc_destination
        )


def _run(
    discovery: Discovery,
    release_path: Path,
    transform: Transform,
    gate: Gate,
    qc_destination: str | os.PathLike[str],
) -> RunResult:
    staging = staging_path(release_path)
    _check_directories(discovery.source, release_path, staging)
    qc_store.check_confidential_destination(
        qc_destination, release_directory=release_path, staging_directory=staging
    )

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
        outcomes, material = _stage_and_gate(discovery, first, staging, transform, gate)
        outcomes = _labelled(outcomes)
        pack = run_qc.qc_pack_of(discovery.paths, outcomes, material)
        # The pack is written before the release is published, so that a
        # release never exists without its QC material.
        qc_pack = qc_store.write_qc_pack(
            pack,
            qc_destination,
            release_directory=release_path,
            staging_directory=staging,
        )
        staged_release = staging / _STAGED_RELEASE
        staged_release.mkdir(exist_ok=True, mode=0o700)
        if os.path.lexists(release_path):
            raise RunError(_RELEASE_EXISTS.format(release=release_path))
        os.rename(staged_release, release_path)
        _sync_directory(release_path.parent)
    finally:
        removed = _remove(staging)
    return RunResult(release_path, outcomes, first.findings, removed, qc_pack)


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
    return _FirstPass(records, digests, findings, settled, copies, frozenset(kinds))


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


def _stage_and_gate(  # pylint: disable = too-many-locals, too-many-branches
    discovery: Discovery,
    first: _FirstPass,
    staging: Path,
    transform: Transform,
    gate: Gate,
) -> tuple[tuple[Outcome, ...], dict[int, tuple[object, ...]]]:
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
        if data is None:
            continue
        following.update((copy, position) for copy in group if copy > position)

        result = _guarded(transform, data, record)
        material[position] += _material(result)
        subject = _WITHOUT_PATIENT_ID if record.patient is None else record.patient
        if isinstance(result, (Transformed, Sequestered)) and (
            result.evidence is not None
        ):
            evidence[subject].append(result.evidence)
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
    )


def _material(result: object) -> tuple[object, ...]:
    """Return the QC material that a transform's or gate's result carries."""
    if isinstance(result, (Transformed, Sequestered, HoldForReview, Release)):
        qc = result.qc
        if isinstance(qc, tuple):
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
