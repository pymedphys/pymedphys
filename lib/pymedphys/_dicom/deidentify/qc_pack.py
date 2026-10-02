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

"""The confidential QC pack: what a reviewer needs, kept apart from releases.

A de-identification run's release report can be distributed with its output,
so it holds no source value or original path (D-016). Human review needs
more: which source file each instance came from, the text that the residual
search found and what surrounds it, and the strings that the policy retains.
That material may still identify people, so it goes in a QC pack, written to
a location that the caller designates explicitly, outside the release and
staging directories, and readable only by its owner (D-016).

A pack holds, for one run:

- ``instances``: each input by its run position and source path, with its
  output path if written, or the opaque per-run label by which the release
  report refers to it if sequestered, and why (D-026);
- ``residual_findings``: each residual that the search of a written file
  found, by instance and place, with a contextual excerpt of the bytes
  around it (D-027);
- ``drops`` and ``not_searched``: each value dropped from the search, because
  the policy retains it or it equals a constant that the engine always
  writes, and each form not searched, by instance and place; the release
  report gives only their counts by attribute and reason (D-027);
- ``retained_strings``: each distinct string that the policy retains, with
  every place it was retained, for the review of every distinct retained
  string (D-017);
- ``roi_names``: each ROI Name that automatic cleaning renamed, for audit,
  or that awaits review (D-009).

Its ``reference`` is an opaque random token that the release report records
with the attestation's outcome, in place of the review material (D-016). It
is not derived from the pack's content.

:func:`write_qc_pack` writes a pack as ``qc-pack.json``, labelled with its
format, :data:`FORMAT`, beside a handling notice and the marker
:data:`MARKER_FILE`, by which :func:`is_qc_material` recognises QC material
so that no release can include it. Errors name the field or check that
failed, never a value or a path.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import os
import re
import secrets
import stat
import sys
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from . import residuals
from .file_layout import ElementPath, Location

# The format of the pack document. A change to its fields takes a new label.
FORMAT = "pymedphys-deid-qc-pack/1"
PACK_FILE = "qc-pack.json"
NOTICE_FILE = "README.txt"
# Marks a directory as QC material. It is written first, so that a pack
# whose writing stopped part way is still recognised.
MARKER_FILE = ".pymedphys-deid-qc-pack"
# The bytes of a written file shown on each side of a residual's offset.
EXCERPT_BYTES = 48

_REFERENCE = re.compile(r"A-[0-9a-f]{32}")
# An opaque per-run label, such as the release report's "S-0001" (D-026).
_LABEL = re.compile(r"[A-Z]-[0-9]{4,9}")
_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600

NOTICE = """\
CONFIDENTIAL: DE-IDENTIFICATION QC PACK

This directory is a QC pack from a PyMedPhys de-identification run. It holds
source file paths, text found in de-identified files, and retained strings,
which may identify people. Treat it as you would the source data.

- Only reviewers whom the data custodian authorises may read it.
- Never copy it, or anything from it, into a release directory or archive,
  and never distribute it with the de-identified output.
- Keep it only as long as the review, the attestation, and the custodian's
  documented retention period require; then delete the whole directory.

The release report refers to this pack only by its opaque reference, which
is in qc-pack.json.
"""


class QcPackError(ValueError):
    """A QC pack, or where it is to be written, that cannot be accepted."""


class Disposition(enum.Enum):
    """What the run did with an input."""

    WRITTEN = "written"
    # an identical duplicate of a written input, not written again (D-026)
    DUPLICATE = "duplicate"
    SEQUESTERED = "sequestered"


class DropReason(enum.Enum):
    """Why a value was dropped from the residual search (D-027)."""

    # a value that the policy legitimately retains
    RETAINED = "retained"
    # a value that exactly equals a constant that the engine always writes
    ENGINE_CONSTANT = "engine-constant"


class RoiNameStatus(enum.Enum):
    """What happened to a ROI Name under descriptor cleaning (D-009)."""

    # written in the vocabulary's spelling, recorded for audit
    RENAMED = "renamed"
    AWAITING_REVIEW = "awaiting-review"


def new_reference() -> str:
    """Return a new opaque reference for a QC pack, ``A-`` and 32 hex digits.

    The reference is random, so it reveals nothing of the pack's content.

    Examples
    --------
    >>> reference = new_reference()
    >>> reference[:2], len(reference)
    ('A-', 34)
    """
    return "A-" + secrets.token_hex(16)


@dataclasses.dataclass(frozen=True, repr=False)
class InstanceEntry:
    """An input of the run, and what became of it.

    Its ``repr`` leaves out the source path.

    Attributes
    ----------
    position : int
        The input's run position, from 0.
    source : str
        The input's path as the run was given it.
    disposition : Disposition
    output : pathlib.PurePosixPath, optional
        The output path below the output directory, for an input that was
        written or is a duplicate of one that was.
    label : str, optional
        The opaque per-run label, such as ``S-0001``, by which the release
        report refers to a sequestered input (D-026).
    reasons : tuple of str
        Why a sequestered input was sequestered, as the engine words its
        findings, which hold no values; empty otherwise.
    """

    position: int
    source: str
    disposition: Disposition
    output: PurePosixPath | None = None
    label: str | None = None
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _check_position("an instance", self.position)
        if not isinstance(self.source, str) or not self.source:
            raise QcPackError(f"instance {self.position} needs its source path")
        if not isinstance(self.disposition, Disposition):
            raise QcPackError(f"instance {self.position} needs a Disposition")
        if not isinstance(self.reasons, tuple) or not all(
            isinstance(reason, str) and reason for reason in self.reasons
        ):
            raise QcPackError(f"instance {self.position} needs reasons as text")
        problem = self._problem()
        if problem:
            raise QcPackError(
                f"{self.disposition.value} instance {self.position} {problem}"
            )

    def _problem(self) -> str | None:
        if self.disposition is not Disposition.SEQUESTERED:
            if self.label is not None or self.reasons:
                return "has no label or reasons"
            return (
                None if _is_output_path(self.output) else "needs a relative output path"
            )
        problems = (
            (self.output is not None, "has no output path"),
            (
                not isinstance(self.label, str) or not _LABEL.fullmatch(self.label),
                "needs a label such as S-0001",
            ),
            (not self.reasons, "needs the reasons it was sequestered"),
        )
        return next((problem for failed, problem in problems if failed), None)

    def __repr__(self) -> str:
        return (
            f"InstanceEntry(position={self.position}, "
            f"disposition={self.disposition.value!r}, output={self.output!r}, "
            f"label={self.label!r})"
        )


@dataclasses.dataclass(frozen=True)
class Excerpt:
    """The bytes around a residual in a written file, decoded for a reviewer.

    Attributes
    ----------
    before : str
        Up to :data:`EXCERPT_BYTES` bytes before the residual's offset.
    after : str
        Up to twice :data:`EXCERPT_BYTES` bytes from the offset, which hold
        the residual and what follows it.
    encoding : str
        The codec that both were decoded with, the residual's own. Bytes that
        it cannot decode are written as backslash escapes.
    """

    before: str
    after: str
    encoding: str


def excerpt(
    data: bytes | bytearray | memoryview, finding: residuals.Finding
) -> Excerpt:
    """Return the contextual excerpt of a residual in the file it was found in.

    Parameters
    ----------
    data : bytes, bytearray, or memoryview
        The whole written file that was searched.
    finding : ~pymedphys._dicom.deidentify.residuals.Finding
        A residual that the search of ``data`` found.

    Returns
    -------
    Excerpt

    Raises
    ------
    QcPackError
        If the finding's offset is not in ``data``.

    Examples
    --------
    >>> from pymedphys._dicom.deidentify.residuals import SourceValue, find_residuals
    >>> name = SourceValue(ElementPath((), "(0010,0010)"), "PN", "ZEBEDEE^QUILLON")
    >>> data = b"Seen by Dr Zebedee today"
    >>> found = find_residuals(data, [name]).findings[0]
    >>> excerpt(data, found)
    Excerpt(before='Seen by Dr ', after='Zebedee today', encoding='utf-8')
    """
    with memoryview(data) as view, view.cast("B") as octets:
        offset = finding.offset
        if not isinstance(offset, int) or not 0 <= offset < len(octets):
            raise QcPackError("the residual's offset is not in the file")
        width = EXCERPT_BYTES
        # A character of UTF-16LE is two bytes, so keep to the match's parity.
        start = max(offset - width, offset % 2 if _is_wide(finding) else 0)
        end = min(offset + 2 * width, len(octets))
        return Excerpt(
            before=_decode(bytes(octets[start:offset]), finding.encoding),
            after=_decode(bytes(octets[offset:end]), finding.encoding),
            encoding=finding.encoding,
        )


def _is_wide(finding: residuals.Finding) -> bool:
    return finding.encoding.replace("_", "-").lower() in {"utf-16-le", "utf-16le"}


def _decode(octets: bytes, encoding: str) -> str:
    try:
        return octets.decode(encoding, errors="backslashreplace")
    except LookupError:  # a codec that a caller named but Python lacks
        return octets.decode("latin-1")


@dataclasses.dataclass(frozen=True)
class ResidualEntry:
    """A residual that the search of an instance's written file found.

    Attributes
    ----------
    position : int
        The instance's run position.
    finding : ~pymedphys._dicom.deidentify.residuals.Finding
    excerpt : Excerpt, optional
        The bytes around it, from :func:`excerpt`.
    """

    position: int
    finding: residuals.Finding
    excerpt: Excerpt | None = None

    def __post_init__(self) -> None:
        _check_position("a residual", self.position)
        if not isinstance(self.finding, residuals.Finding):
            raise QcPackError(
                f"the residual of instance {self.position} needs a Finding"
            )
        if self.excerpt is not None and not isinstance(self.excerpt, Excerpt):
            raise QcPackError(
                f"the residual of instance {self.position} has a bad excerpt"
            )


@dataclasses.dataclass(frozen=True)
class DropEntry:
    """A source value dropped from an instance's residual search (D-027).

    Attributes
    ----------
    position : int
        The instance's run position.
    source : ElementPath
        Where the value was in the source.
    reason : DropReason
    """

    position: int
    source: ElementPath
    reason: DropReason

    def __post_init__(self) -> None:
        _check_position("a drop", self.position)
        if not isinstance(self.source, ElementPath) or not isinstance(
            self.reason, DropReason
        ):
            raise QcPackError(
                f"a drop of instance {self.position} needs an ElementPath and a DropReason"
            )


@dataclasses.dataclass(frozen=True)
class NotSearchedEntry:
    """A form of a source value that an instance's residual search did not search.

    Attributes
    ----------
    position : int
        The instance's run position.
    omission : ~pymedphys._dicom.deidentify.residuals.NotSearched
    """

    position: int
    omission: residuals.NotSearched

    def __post_init__(self) -> None:
        _check_position("an omission", self.position)
        if not isinstance(self.omission, residuals.NotSearched):
            raise QcPackError(
                f"an omission of instance {self.position} needs a NotSearched"
            )


@dataclasses.dataclass(frozen=True, repr=False)
class RetainedString:
    """A distinct string that the policy retains, and every place it was retained.

    Its ``repr`` leaves out the string.

    Attributes
    ----------
    value : str
        The string as retained.
    places : tuple of (int, ElementPath)
        Each instance's run position and the element that retained it,
        each once, in order.
    """

    value: str
    places: tuple[tuple[int, ElementPath], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise QcPackError("a retained string needs its value as text")
        if not (
            isinstance(self.places, tuple)
            and self.places
            and all(_is_place(place) for place in self.places)
        ):
            raise QcPackError(
                "a retained string needs places of a run position and an ElementPath"
            )
        if list(self.places) != sorted(set(self.places), key=_place_key):
            raise QcPackError(
                "a retained string's places must be distinct and in order"
            )

    def __repr__(self) -> str:
        return f"RetainedString(places={len(self.places)})"


@dataclasses.dataclass(frozen=True, repr=False)
class RoiNameEntry:
    """A ROI Name that descriptor cleaning renamed or set aside for review (D-009).

    Its ``repr`` leaves out the names.

    Attributes
    ----------
    position : int
        The instance's run position.
    path : ElementPath
        The ROI Name (3006,0026) in its Structure Set ROI Sequence item.
    name : str
        The source ROI Name.
    status : RoiNameStatus
    vocabulary_name : str, optional
        The name written in the vocabulary's spelling, for a rename only.
    """

    position: int
    path: ElementPath
    name: str
    status: RoiNameStatus
    vocabulary_name: str | None = None

    def __post_init__(self) -> None:
        _check_position("a ROI name", self.position)
        if not isinstance(self.path, ElementPath) or not isinstance(self.name, str):
            raise QcPackError(
                f"a ROI name of instance {self.position} needs an ElementPath and text"
            )
        if not isinstance(self.status, RoiNameStatus):
            raise QcPackError(f"a ROI name of instance {self.position} needs a status")
        renamed = self.status is RoiNameStatus.RENAMED
        if renamed != (
            isinstance(self.vocabulary_name, str) and bool(self.vocabulary_name)
        ):
            raise QcPackError(
                f"a ROI name of instance {self.position} has a vocabulary name "
                "only when it was renamed"
            )

    def __repr__(self) -> str:
        return (
            f"RoiNameEntry(position={self.position}, path={str(self.path)!r}, "
            f"status={self.status.value!r})"
        )


@dataclasses.dataclass(frozen=True, repr=False)
class QcPack:
    """What a reviewer needs from one run, as the module describes.

    Its ``repr`` shows only its reference and how many entries it holds.

    Attributes
    ----------
    reference : str
        The opaque reference from :func:`new_reference`.
    instances : tuple of InstanceEntry
        One for each run position from 0, in order.
    residual_findings : tuple of ResidualEntry
    drops : tuple of DropEntry
    not_searched : tuple of NotSearchedEntry
    retained_strings : tuple of RetainedString
        Each value once.
    roi_names : tuple of RoiNameEntry

    Raises
    ------
    QcPackError
        If an attribute is not of its type; if the instances are not one for
        each run position from 0; if two sequestered instances share a label
        or two written instances an output path; if a duplicate's output path
        is not a written instance's; if an entry names a run position without
        an instance; or if two retained strings are the same.
    """

    reference: str
    instances: tuple[InstanceEntry, ...]
    residual_findings: tuple[ResidualEntry, ...] = ()
    drops: tuple[DropEntry, ...] = ()
    not_searched: tuple[NotSearchedEntry, ...] = ()
    retained_strings: tuple[RetainedString, ...] = ()
    roi_names: tuple[RoiNameEntry, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not _REFERENCE.fullmatch(
            self.reference
        ):
            raise QcPackError("a QC pack needs a reference from new_reference()")
        sections = {
            "instances": InstanceEntry,
            "residual_findings": ResidualEntry,
            "drops": DropEntry,
            "not_searched": NotSearchedEntry,
            "retained_strings": RetainedString,
            "roi_names": RoiNameEntry,
        }
        for name, kind in sections.items():
            entries = getattr(self, name)
            if not isinstance(entries, tuple) or not all(
                isinstance(entry, kind) for entry in entries
            ):
                raise QcPackError(f"{name} must be a tuple of {kind.__name__}")
        if [entry.position for entry in self.instances] != list(
            range(len(self.instances))
        ):
            raise QcPackError("instances must be one for each run position from 0")
        self._check_names()
        positions = len(self.instances)
        for name in ("residual_findings", "drops", "not_searched", "roi_names"):
            if any(entry.position >= positions for entry in getattr(self, name)):
                raise QcPackError(f"{name} names a run position without an instance")
        if any(
            position >= positions
            for retained in self.retained_strings
            for position, _ in retained.places
        ):
            raise QcPackError(
                "retained_strings names a run position without an instance"
            )
        values = [retained.value for retained in self.retained_strings]
        if len(set(values)) != len(values):
            raise QcPackError("retained_strings must hold each value once")

    def _check_names(self) -> None:
        labels = [entry.label for entry in self.instances if entry.label is not None]
        if len(set(labels)) != len(labels):
            raise QcPackError("two sequestered instances share a label")
        written = [
            entry.output
            for entry in self.instances
            if entry.disposition is Disposition.WRITTEN
        ]
        if len(set(written)) != len(written):
            raise QcPackError("two written instances share an output path")
        if any(
            entry.output not in written
            for entry in self.instances
            if entry.disposition is Disposition.DUPLICATE
        ):
            raise QcPackError("a duplicate's output path is not a written instance's")

    def __repr__(self) -> str:
        return (
            f"QcPack(reference={self.reference!r}, instances={len(self.instances)}, "
            f"residual_findings={len(self.residual_findings)}, "
            f"drops={len(self.drops)}, not_searched={len(self.not_searched)}, "
            f"retained_strings={len(self.retained_strings)}, "
            f"roi_names={len(self.roi_names)})"
        )


def _check_position(what: str, position: object) -> None:
    if not isinstance(position, int) or isinstance(position, bool) or position < 0:
        raise QcPackError(f"{what} needs a run position from 0")


def _is_place(place: object) -> bool:
    return (
        isinstance(place, tuple)
        and len(place) == 2
        and isinstance(place[0], int)
        and not isinstance(place[0], bool)
        and place[0] >= 0
        and isinstance(place[1], ElementPath)
    )


def _place_key(place: tuple[int, ElementPath]) -> tuple[int, tuple, str]:
    position, path = place
    return position, path.items, path.tag


def _is_output_path(path: object) -> bool:
    return (
        isinstance(path, PurePosixPath)
        and bool(path.parts)
        and not path.is_absolute()
        and all(part not in ("", ".", "..") for part in path.parts)
    )


def pack_document(pack: QcPack) -> dict:
    """Return a QC pack as JSON values, labelled with :data:`FORMAT`.

    Element paths and places are written as their ``str`` forms, with items
    numbered from 0, such as ``(300A,00B0)[1] > (300A,00C2)``.

    Parameters
    ----------
    pack : QcPack

    Returns
    -------
    dict
        With the keys ``format``, ``reference``, and one for each section.

    Examples
    --------
    >>> pack = QcPack(new_reference(), (
    ...     InstanceEntry(0, "in/a.dcm", Disposition.SEQUESTERED,
    ...                   label="S-0001", reasons=("conflicting instance",)),
    ... ))
    >>> document = pack_document(pack)
    >>> document["instances"][0]["label"], document["instances"][0]["source"]
    ('S-0001', 'in/a.dcm')
    """
    if not isinstance(pack, QcPack):
        raise TypeError("pack must be a QcPack")
    return {
        "format": FORMAT,
        "reference": pack.reference,
        "instances": [_instance(entry) for entry in pack.instances],
        "residual_findings": [_residual(entry) for entry in pack.residual_findings],
        "drops": [
            {
                "position": entry.position,
                "source": str(entry.source),
                "reason": entry.reason.value,
            }
            for entry in pack.drops
        ],
        "not_searched": [_omission(entry) for entry in pack.not_searched],
        "retained_strings": [
            {
                "value": retained.value,
                "places": [
                    {"position": position, "element": str(path)}
                    for position, path in retained.places
                ],
            }
            for retained in pack.retained_strings
        ],
        "roi_names": [
            {
                "position": entry.position,
                "element": str(entry.path),
                "name": entry.name,
                "status": entry.status.value,
                "vocabulary_name": entry.vocabulary_name,
            }
            for entry in pack.roi_names
        ],
    }


def _instance(entry: InstanceEntry) -> dict:
    return {
        "position": entry.position,
        "source": entry.source,
        "disposition": entry.disposition.value,
        "output": None if entry.output is None else entry.output.as_posix(),
        "label": entry.label,
        "reasons": list(entry.reasons),
    }


def _location(location: Location) -> dict:
    return {
        "region": location.region.value,
        "element": None if location.element is None else str(location.element),
        "vr": location.vr,
        "item": location.item,
        "description": str(location),
    }


def _residual(entry: ResidualEntry) -> dict:
    finding = entry.finding
    document = {
        "position": entry.position,
        "source": str(finding.source),
        "kind": finding.kind.value,
        "form": finding.form.value,
        "encoding": finding.encoding,
        "location": _location(finding.location),
        "offset": finding.offset,
        "excerpt": None,
    }
    if entry.excerpt is not None:
        document["excerpt"] = dataclasses.asdict(entry.excerpt)
    return document


def _omission(entry: NotSearchedEntry) -> dict:
    omission = entry.omission
    return {
        "position": entry.position,
        "source": str(omission.source),
        "vr": omission.vr,
        "form": omission.form.value,
        "reason": omission.reason.value,
        "encoding": omission.encoding,
    }


def to_json(pack: QcPack) -> str:
    """Return a QC pack as JSON text, ASCII only, ending with a newline.

    Text that is not ASCII is escaped, including a source path that the
    operating system gave as bytes that are not valid in its encoding, which
    Python holds as lone surrogates (PEP 383).
    """
    return json.dumps(pack_document(pack), indent=2, ensure_ascii=True) + "\n"


def check_confidential_destination(
    destination: os.PathLike | str,
    *,
    release_directory: os.PathLike | str,
    staging_directory: os.PathLike | str | None = None,
) -> Path:
    """Check that a directory may receive confidential material, and return it.

    The destination must be given explicitly: there is no default. It must
    be neither inside the release directory or the staging directory nor
    contain either, once each path is made absolute and its symbolic links
    are resolved, so that no release or archive of either can include it. It
    must not exist yet, or be an empty directory; on POSIX, an existing one
    must also grant no access to its group or to others. On Windows, access
    rests on the location's access control lists, which this does not check.

    Parameters
    ----------
    destination : path-like
    release_directory : path-like
        Where released output goes.
    staging_directory : path-like, optional
        Where output waits for its residual search (D-027).

    Returns
    -------
    pathlib.Path
        The destination, absolute, with its symbolic links resolved.

    Raises
    ------
    QcPackError
        For each reason above, naming the check, never the path.
    """
    target = _resolved(destination, "the QC destination")
    others = {
        "release directory": _resolved(release_directory, "the release directory")
    }
    if staging_directory is not None:
        others["staging directory"] = _resolved(
            staging_directory, "the staging directory"
        )
    for name, other in others.items():
        if _within(target, other) or _within(other, target):
            raise QcPackError(
                f"the QC destination must be neither inside the {name} nor contain it"
            )
    if target.exists() or target.is_symlink():
        if not target.is_dir():
            raise QcPackError("the QC destination exists and is not a directory")
        if any(target.iterdir()):
            raise QcPackError("the QC destination must be new or an empty directory")
        if os.name == "posix" and stat.S_IMODE(target.stat().st_mode) & 0o077:
            raise QcPackError(
                "the QC destination grants access to its group or others; "
                "restrict it to its owner (chmod 700)"
            )
    return target


def _resolved(path: object, what: str) -> Path:
    if not isinstance(path, (str, os.PathLike)) or not os.fspath(path):
        raise QcPackError(f"{what} must be given as a path")
    return Path(path).expanduser().resolve(strict=False)


def _within(path: Path, directory: Path) -> bool:
    """Return whether ``path`` is ``directory`` or below it.

    Windows paths compare without case already. macOS volumes are
    case-insensitive by default, so there case is disregarded too, which
    errs towards refusing a destination.
    """
    if sys.platform == "darwin":
        path, directory = Path(str(path).casefold()), Path(str(directory).casefold())
    return path.is_relative_to(directory)


def write_qc_pack(
    pack: QcPack,
    destination: os.PathLike | str,
    *,
    release_directory: os.PathLike | str,
    staging_directory: os.PathLike | str | None = None,
) -> Path:
    """Write a QC pack to a designated, restricted directory.

    The destination is checked by :func:`check_confidential_destination`,
    and created, with any missing parents, if it does not exist. It is given
    mode 0o700, and each file mode 0o600, on POSIX. It receives, in this
    order, the marker :data:`MARKER_FILE`, :data:`PACK_FILE` from
    :func:`to_json`, and :data:`NOTICE_FILE`, the handling notice
    :data:`NOTICE`. A file is never overwritten.

    Parameters
    ----------
    pack : QcPack
    destination : path-like
    release_directory, staging_directory : path-like
        As for :func:`check_confidential_destination`.

    Returns
    -------
    pathlib.Path
        The path of the written :data:`PACK_FILE`.

    Raises
    ------
    QcPackError
        If the destination is refused.
    TypeError
        If ``pack`` is not a :class:`QcPack`.
    """
    document = to_json(pack)  # checks the pack before anything is written
    target = check_confidential_destination(
        destination,
        release_directory=release_directory,
        staging_directory=staging_directory,
    )
    target.mkdir(mode=_DIRECTORY_MODE, parents=True, exist_ok=True)
    if os.name == "posix":
        target.chmod(_DIRECTORY_MODE)  # mkdir's mode is masked by the umask
    write_new(target / MARKER_FILE, FORMAT + "\n")
    write_new(target / PACK_FILE, document)
    write_new(target / NOTICE_FILE, NOTICE)
    return target / PACK_FILE


def write_new(path: Path, text: str) -> None:
    """Write ASCII text to a new file, mode 0o600 on POSIX, never overwriting.

    Raises
    ------
    FileExistsError
        If the file exists.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, _FILE_MODE)
    with os.fdopen(descriptor, "wb") as file:
        file.write(text.encode("ascii"))


def is_qc_material(path: os.PathLike | str) -> bool:
    """Return whether a path is QC material, or a directory that holds some.

    A path is QC material if it is a QC pack directory, one of its files, or
    anything below one, or if it is a directory with a QC pack anywhere
    below it, recognised by :data:`MARKER_FILE`. A release step refuses such
    a path, so that no release or archive includes QC material (D-016).
    Symbolic links below a directory are not followed.

    Parameters
    ----------
    path : path-like

    Returns
    -------
    bool
    """
    resolved = Path(path).resolve(strict=False)
    if any(
        (directory / MARKER_FILE).is_file()
        for directory in (resolved, *resolved.parents)
    ):
        return True
    if not resolved.is_dir():
        return False
    return any(MARKER_FILE in files for _, _, files in os.walk(resolved))


def entries_for_search(
    position: int,
    search: residuals.ResidualSearch,
    data: bytes | bytearray | memoryview,
) -> tuple[tuple[ResidualEntry, ...], tuple[NotSearchedEntry, ...]]:
    """Return an instance's residual findings, with excerpts, and its omissions.

    Parameters
    ----------
    position : int
        The instance's run position.
    search : ~pymedphys._dicom.deidentify.residuals.ResidualSearch
        The search of its written file.
    data : bytes, bytearray, or memoryview
        That file, to cut each finding's excerpt from.

    Returns
    -------
    tuple
        The :class:`ResidualEntry` of each finding, and the
        :class:`NotSearchedEntry` of each omission, in the search's order.
    """
    if not isinstance(search, residuals.ResidualSearch):
        raise TypeError("search must be a ResidualSearch")
    return (
        tuple(
            ResidualEntry(position, finding, excerpt(data, finding))
            for finding in search.findings
        ),
        tuple(NotSearchedEntry(position, omission) for omission in search.not_searched),
    )


def retained_strings(
    occurrences: Iterable[tuple[str, int, ElementPath]],
) -> tuple[RetainedString, ...]:
    """Group retained strings by value, for the review of each distinct one.

    Parameters
    ----------
    occurrences : iterable of (str, int, ElementPath)
        Each retained string, with the run position and element that
        retained it.

    Returns
    -------
    tuple of RetainedString
        One for each distinct value, ordered by its first place, with its
        places in order and each once. A value is the string as retained:
        strings that differ only in case or padding are distinct.
    """
    places: dict[str, set[tuple[int, ElementPath]]] = {}
    for value, position, path in occurrences:
        if not isinstance(value, str) or not _is_place((position, path)):
            raise QcPackError(
                "a retained string needs its value as text, a run position, "
                "and an ElementPath"
            )
        places.setdefault(value, set()).add((position, path))
    grouped = [
        RetainedString(value, tuple(sorted(found, key=_place_key)))
        for value, found in places.items()
    ]
    return tuple(sorted(grouped, key=lambda retained: _place_key(retained.places[0])))
