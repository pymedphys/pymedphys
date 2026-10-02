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
   the run reports refers to it. A symbolic link is not followed, a file
   that is not a regular file is not opened, and a DICOMDIR is never passed
   through (PS3.15 E.1.1): each is refused.
2. The first pass reads each file once, builds its
   :class:`~pymedphys._dicom.deidentify.references.InstanceRecord`, and
   builds the :class:`~pymedphys._dicom.deidentify.reference_graph.ReferenceGraph`
   of the inputs, before anything is written. Its findings take their
   graded consequences: a study whose instances name several patients
   stops the run with :class:`RunStopped` before any directory is created;
   every copy of a conflicting instance, and every instance of a series in
   several studies, is sequestered; an identical duplicate is processed
   once, at its first position; a dangling reference is reported only.
3. The second pass reads each remaining file again, sequesters it if its
   bytes differ from the first pass's, and gives it to the run's
   :class:`Transform`, which returns the output file and the source values
   that it removed or replaced, or sequesters the instance. Each output file
   is written to the staging area, as a temporary file renamed into place
   once its bytes are on disk.
4. Each staged file is read back from disk and given to the run's
   :class:`Gate` with the source values of its subject, pooled from every
   instance of the run, as the residual search needs. The gate decides
   whether it may be released. A sequestered instance's staged file is
   deleted at once.
5. The release directory is published by renaming the staging area's
   release tree to it, so it appears whole, holding only files that their
   gate passed, or not at all.

The run decides nothing about an instance's content: the transform and the
gate do. The run fails closed: an exception that either raises sequesters
that instance with :attr:`RunReason.INTERNAL_ERROR`, without its message,
which could quote a value; and any other failure deletes the staging area
and publishes nothing.

Where the design leaves a detail open, the run takes these defaults:

- an instance without its SOP Instance UID, Series Instance UID, or Study
  Instance UID is sequestered, since it cannot be named or checked against
  its series and study;
- an instance whose first pass cannot follow a sequence on the path to a
  reference has no record, and is sequestered;
- the release directory must not exist, so that a run never mixes its
  output with another's;
- the staging area is a directory beside the release directory, named for
  it, created for the run with permissions for its owner alone where the
  platform has them, and removed when the run ends; one left by a run that
  was interrupted holds output that may still identify people, so a run
  refuses to start until someone has reviewed and deleted it.

Nothing here logs, warns, or raises with a source path or value. Outcomes
and findings name inputs by run position and attributes by tag. The source
paths are held only by the :class:`Discovery`, for the confidential QC
material, and are left out of its ``repr``.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import os
import re
import shutil
import stat
from collections.abc import Callable, Iterator
from pathlib import Path, PurePosixPath
from typing import Protocol, TypeGuard

from . import output_names
from .file_layout import Region, read_file_layout
from .reference_graph import Finding, FindingKind, build_reference_graph
from .references import InstanceRecord, UnreadableSequence
from .residuals import SourceValue

# Media Storage SOP Class UID of a DICOMDIR: the Media Storage Directory
# Storage SOP Class (PS3.4 Annex F, PS3.6 Table A-1).
MEDIA_STORAGE_DIRECTORY_STORAGE = "1.2.840.10008.1.3.10"
_MEDIA_STORAGE_SOP_CLASS = "(0002,0002)"
_DICOMDIR_NAME = "DICOMDIR"
STAGING_SUFFIX = ".staging"
# The staging area's tree that becomes the release directory.
_STAGED_RELEASE = "release"
_PARTIAL_SUFFIX = ".partial"
# A reason that a transform or gate gives: a short code, never a value.
_REASON = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_MAX_REASON = 64


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
    DUPLICATE = "duplicate"  # an identical copy of an earlier input
    SEQUESTERED = "sequestered"  # withheld from the release
    REFUSED = "refused"  # not an instance the run can read


class RunReason(enum.Enum):
    """Why the run itself refused or sequestered an input, as a stable code."""

    # discovery
    SYMBOLIC_LINK = "symbolic-link"
    NOT_A_REGULAR_FILE = "not-a-regular-file"
    DICOMDIR = "dicomdir"
    # the first pass
    UNREADABLE_FILE = "unreadable-file"  # the operating system cannot read it
    NOT_READABLE_AS_DICOM = "not-readable-as-dicom"
    UNREADABLE_SEQUENCE = "unreadable-sequence"
    MISSING_IDENTIFIER = "missing-identifier"
    CONFLICTING_INSTANCE = "conflicting-instance"
    SERIES_IN_SEVERAL_STUDIES = "series-in-several-studies"
    # the second pass and after
    CHANGED_DURING_RUN = "changed-during-run"
    INVALID_OUTPUT_NAME = "invalid-output-name"
    SHARED_OUTPUT_NAME = "shared-output-name"
    INVALID_REASON = "invalid-reason"
    INTERNAL_ERROR = "internal-error"


_SEQUESTERING_FINDINGS = {
    FindingKind.MISSING_IDENTIFIER: RunReason.MISSING_IDENTIFIER,
    FindingKind.CONFLICTING_INSTANCE: RunReason.CONFLICTING_INSTANCE,
    FindingKind.SERIES_IN_SEVERAL_STUDIES: RunReason.SERIES_IN_SEVERAL_STUDIES,
}


@dataclasses.dataclass(frozen=True)
class Sequestered:
    """A transform's or gate's decision to withhold an instance.

    Attributes
    ----------
    reason : str
        A code of lower-case ASCII letters and digits in words joined by
        hyphens, at most 64 characters, such as ``"residual-person-name"``.
        A reason in any other form is replaced by
        :attr:`RunReason.INVALID_REASON`, since it could hold a value.
    """

    reason: str


@dataclasses.dataclass(frozen=True, repr=False)
class Transformed:
    """An instance's output file, and the source values it removed or replaced.

    Attributes
    ----------
    path : PurePosixPath
        Where the file goes below the release directory, as
        :func:`~pymedphys._dicom.deidentify.output_names.instance_path` gives
        it from the instance's replacement values.
    data : bytes
        The whole output file.
    source_values : tuple of SourceValue
        The values that had to be removed or replaced, for the residual
        search of every file of the instance's subject.
    """

    path: PurePosixPath
    data: bytes
    source_values: tuple[SourceValue, ...] = ()

    def __repr__(self) -> str:
        return (
            f"Transformed(bytes={len(self.data)}, "
            f"source_values={len(self.source_values)})"
        )


class Transform(Protocol):
    """De-identify one instance: the walker, writer, and verification."""

    def __call__(
        self, data: bytes, record: InstanceRecord
    ) -> Transformed | Sequestered: ...


class Gate(Protocol):
    """Decide whether a staged file may be released.

    ``written`` is the file as read back from the staging area, and
    ``subject_values`` the source values of every instance of its subject in
    the run, its own first. ``None`` releases it.
    """

    def __call__(
        self,
        written: bytes,
        transformed: Transformed,
        subject_values: tuple[SourceValue, ...],
    ) -> Sequestered | None: ...


@dataclasses.dataclass(frozen=True, repr=False)
class Discovery:
    """The entries below a source directory, by run position.

    Attributes
    ----------
    source : Path
        The source directory, resolved.
    paths : tuple of Path
        Each entry's path, at its run position. Confidential: they are for
        the QC material alone, and are left out of the ``repr``.
    refusals : tuple of RunReason or None
        For each position, why discovery refused the entry, or ``None`` for
        a regular file.
    """

    source: Path
    paths: tuple[Path, ...]
    refusals: tuple[RunReason | None, ...]

    def __repr__(self) -> str:
        refused = sum(reason is not None for reason in self.refusals)
        return f"Discovery(entries={len(self.paths)}, refused={refused})"


@dataclasses.dataclass(frozen=True)
class Outcome:
    """What happened to one input.

    Attributes
    ----------
    position : int
    status : Status
    reason : str or None
        Why it was refused or sequestered: a :class:`RunReason` value, or the
        code that its transform or gate gave.
    output : PurePosixPath or None
        For a released input, its file below the release directory.
    duplicate_of : int or None
        For a duplicate, the position of the copy that was processed.
    """

    position: int
    status: Status
    reason: str | None = None
    output: PurePosixPath | None = None
    duplicate_of: int | None = None


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
    """

    release: Path
    outcomes: tuple[Outcome, ...]
    findings: tuple[Finding, ...]


def discover(source: str | os.PathLike[str]) -> Discovery:
    """List every entry below a source directory, by run position.

    Entries are ordered by their paths relative to ``source``, compared
    component by component as the bytes that the file system holds, so the
    order is the same on every run. A directory is descended and is not an
    entry itself; a symbolic link, to a directory or a file, is an entry that
    is refused and not followed; any other entry that is not a regular file,
    such as a named pipe, is refused without being opened; and a regular
    file named ``DICOMDIR``, in any case, is refused, as is a file whose
    Media Storage SOP Class UID is a DICOMDIR's, found by the first pass.

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
        If ``source`` is not a directory.
    """
    root = Path(source).resolve()
    if not root.is_dir():
        raise RunError("the source is not a directory")
    found: list[tuple[tuple[bytes, ...], Path, RunReason | None]] = []
    for path, reason in _walk(root):
        key = tuple(os.fsencode(part) for part in path.relative_to(root).parts)
        found.append((key, path, reason))
    found.sort(key=lambda entry: entry[0])
    return Discovery(
        root,
        tuple(path for _, path, _ in found),
        tuple(reason for _, _, reason in found),
    )


def _walk(directory: Path) -> Iterator[tuple[Path, RunReason | None]]:
    with os.scandir(directory) as entries:
        listed = list(entries)
    for entry in listed:
        path = Path(entry.path)
        if entry.is_symlink():
            yield path, RunReason.SYMBOLIC_LINK
        elif entry.is_dir(follow_symlinks=False):
            yield from _walk(path)
        elif not entry.is_file(follow_symlinks=False):
            yield path, RunReason.NOT_A_REGULAR_FILE
        elif entry.name.upper() == _DICOMDIR_NAME:
            yield path, RunReason.DICOMDIR
        else:
            yield path, None


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
) -> RunResult:
    """De-identify the discovered inputs into a new release directory.

    Parameters
    ----------
    discovery : Discovery
        From :func:`discover`.
    release : str or os.PathLike
        The release directory, which must not exist. Its parent must.
    transform : Transform
        Called once for each instance to process, in run order.
    gate : Gate
        Called once for each staged file, in run order, after every
        instance has been transformed.

    Returns
    -------
    RunResult

    Raises
    ------
    RunError
        If the release directory or its staging area exists, or the release
        directory would be inside the source directory.
    RunStopped
        If a study's instances name several patients. Nothing is created.
    """
    release_path = Path(release).absolute()
    staging = staging_path(release_path)
    _check_directories(discovery.source, release_path, staging)

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
    try:
        outcomes = _stage_and_gate(discovery, first, staging, transform, gate)
        staged_release = staging / _STAGED_RELEASE
        staged_release.mkdir(exist_ok=True, mode=0o700)
        # The release directory must not have appeared since the check.
        if os.path.lexists(release_path):
            raise RunError(_RELEASE_EXISTS.format(release=release_path))
        os.rename(staged_release, release_path)
        _sync_directory(release_path.parent)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return RunResult(release_path, outcomes, first.findings)


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
    resolved = release.parent.resolve() / release.name
    # The release directory does not exist, so it cannot hold the source.
    if resolved.is_relative_to(source):
        raise RunError(
            f"the release directory {release} must not be inside the source directory"
        )


@dataclasses.dataclass(frozen=True)
class _FirstPass:
    records: dict[int, InstanceRecord]
    digests: dict[int, bytes]
    findings: tuple[Finding, ...]
    # Why the run refuses or sequesters each position that it does not process.
    settled: dict[int, Outcome]


def _first_pass(discovery: Discovery) -> _FirstPass:
    records: dict[int, InstanceRecord] = {}
    digests: dict[int, bytes] = {}
    settled: dict[int, Outcome] = {}
    for position, (path, refusal) in enumerate(
        zip(discovery.paths, discovery.refusals)
    ):
        if refusal is not None:
            settled[position] = Outcome(position, Status.REFUSED, refusal.value)
            continue
        try:
            data = path.read_bytes()
        except OSError:
            settled[position] = _refused(position, RunReason.UNREADABLE_FILE)
            continue
        digests[position] = hashlib.sha256(data).digest()
        if _is_dicomdir(data):
            settled[position] = _refused(position, RunReason.DICOMDIR)
            continue
        try:
            records[position] = InstanceRecord.from_file(data)
        except UnreadableSequence:
            settled[position] = _sequestered(position, RunReason.UNREADABLE_SEQUENCE)
        # pydicom raises many types for a file that it cannot read, and its
        # message can quote a value, so none is kept.
        except Exception:  # pylint: disable = broad-exception-caught
            settled[position] = _refused(position, RunReason.NOT_READABLE_AS_DICOM)

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
    for finding in findings:
        reason = _SEQUESTERING_FINDINGS.get(finding.kind)
        if reason is not None:
            for group in finding.instances:
                for position in group:
                    settled.setdefault(position, _sequestered(position, reason))
        elif finding.kind is FindingKind.DUPLICATE_INSTANCE:
            (group,) = finding.instances
            first, *copies = group
            for position in copies:
                settled.setdefault(
                    position,
                    Outcome(position, Status.DUPLICATE, duplicate_of=first),
                )
    return _FirstPass(records, digests, findings, settled)


def _is_dicomdir(data: bytes) -> bool:
    """Whether a file's Media Storage SOP Class UID is a DICOMDIR's."""
    if data[128:132] != b"DICM":
        return False
    try:
        layout = read_file_layout(data)
    # A file whose layout cannot be read is left to the record to refuse.
    except Exception:  # pylint: disable = broad-exception-caught
        return False
    for extent in layout.elements:
        location = extent.location
        if (
            location.region is Region.FILE_META
            and location.element is not None
            and location.element.tag == _MEDIA_STORAGE_SOP_CLASS
        ):
            value = data[extent.value_start : extent.end]
            return value.rstrip(b"\x00 ") == MEDIA_STORAGE_DIRECTORY_STORAGE.encode()
    return False


def _refused(position: int, reason: RunReason) -> Outcome:
    return Outcome(position, Status.REFUSED, reason.value)


def _sequestered(position: int, reason: RunReason | str) -> Outcome:
    code = reason.value if isinstance(reason, RunReason) else reason
    return Outcome(position, Status.SEQUESTERED, code)


@dataclasses.dataclass
class _Staged:
    position: int
    file: Path
    transformed: Transformed
    subject: object


# The subject of every instance without a Patient ID, apart from every
# identity, as the first pass counts them.
_WITHOUT_PATIENT_ID = object()


def _stage_and_gate(
    discovery: Discovery,
    first: _FirstPass,
    staging: Path,
    transform: Transform,
    gate: Gate,
) -> tuple[Outcome, ...]:
    outcomes: dict[int, Outcome] = dict(first.settled)
    staged: dict[PurePosixPath, _Staged] = {}
    # Names that several instances gave: none of them is written.
    shared: set[PurePosixPath] = set()
    values: dict[object, dict[SourceValue, None]] = {}
    release = staging / _STAGED_RELEASE

    for position, record in first.records.items():
        if position in outcomes:
            continue
        try:
            data = discovery.paths[position].read_bytes()
        except OSError:
            outcomes[position] = _sequestered(position, RunReason.UNREADABLE_FILE)
            continue
        if hashlib.sha256(data).digest() != first.digests[position]:
            outcomes[position] = _sequestered(position, RunReason.CHANGED_DURING_RUN)
            continue
        result = _guarded(transform, data, record)
        if not _is_transformed(result):
            outcomes[position] = _sequestered(position, _reason(result))
            continue
        if not _is_output_name(result.path):
            outcomes[position] = _sequestered(position, RunReason.INVALID_OUTPUT_NAME)
            continue
        if result.path in staged or result.path in shared:
            # Instances that share a name are never renamed: all are withheld.
            shared.add(result.path)
            other = staged.pop(result.path, None)
            if other is not None:
                other.file.unlink()
                outcomes[other.position] = _sequestered(
                    other.position, RunReason.SHARED_OUTPUT_NAME
                )
            outcomes[position] = _sequestered(position, RunReason.SHARED_OUTPUT_NAME)
            continue
        file = release.joinpath(*result.path.parts)
        _write_atomically(file, result.data)
        subject = _WITHOUT_PATIENT_ID if record.patient is None else record.patient
        staged[result.path] = _Staged(position, file, result, subject)
        pooled = values.setdefault(subject, {})
        pooled.update(dict.fromkeys(result.source_values))

    for path, entry in sorted(staged.items(), key=lambda item: item[1].position):
        own = entry.transformed.source_values
        subject_values = tuple(dict.fromkeys((*own, *values[entry.subject])))
        written = entry.file.read_bytes()
        verdict = _guarded(gate, written, entry.transformed, subject_values)
        if verdict is None:
            outcomes[entry.position] = Outcome(
                entry.position, Status.RELEASED, output=path
            )
        else:
            entry.file.unlink()
            outcomes[entry.position] = _sequestered(entry.position, _reason(verdict))

    # A duplicate follows the copy that was processed.
    return tuple(outcomes[position] for position in range(len(discovery.paths)))


def _guarded(call: Callable[..., object], *args: object) -> object:
    """Return what ``call(*args)`` returns, or a sequestration if it raises."""
    try:
        return call(*args)
    # Whatever the transform or gate raises, its message could quote a value,
    # so it is not kept, and the instance is not released.
    except Exception:  # pylint: disable = broad-exception-caught
        return Sequestered(RunReason.INTERNAL_ERROR.value)


def _is_transformed(result: object) -> TypeGuard[Transformed]:
    return (
        isinstance(result, Transformed)
        and isinstance(result.data, bytes)
        and isinstance(result.source_values, tuple)
        and all(isinstance(value, SourceValue) for value in result.source_values)
    )


def _reason(result: object) -> str:
    if (
        isinstance(result, Sequestered)
        and isinstance(result.reason, str)
        and len(result.reason) <= _MAX_REASON
        and _REASON.fullmatch(result.reason)
    ):
        return result.reason
    if isinstance(result, Sequestered):
        return RunReason.INVALID_REASON.value
    # Neither Sequestered nor a well-formed Transformed.
    return RunReason.INTERNAL_ERROR.value


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
    """Flush a directory's entries to disk, where the platform allows it."""
    if os.name != "posix":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
