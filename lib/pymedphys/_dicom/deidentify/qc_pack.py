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
- ``roi_names``: what descriptor cleaning wrote for each ROI Name, for the
  audit of every name renamed, kept, or mapped, and each name held for
  review, with why (D-009).

Its ``reference`` is an opaque random token that the release report records
with the attestation's outcome, in place of the review material (D-016). It
is not derived from the pack's content.

:func:`to_json` gives a pack as a JSON document labelled with its format,
:data:`FORMAT`, which :func:`~.qc_store.write_qc_pack` writes to a designated
directory. Errors name the field that failed, never a value or a path, and
the ``repr`` of each entry leaves out its values and paths.
"""

from __future__ import annotations

import codecs
import dataclasses
import enum
import json
import re
import secrets
from collections.abc import Iterable
from pathlib import PurePosixPath

from . import residuals, roi_names
from .file_layout import ElementPath, Location

# The format of the pack document. A change to its fields takes a new label.
FORMAT = "pymedphys-deid-qc-pack/1"
# The bytes of a written file shown on each side of a residual's offset.
EXCERPT_BYTES = 48

_REFERENCE = re.compile(r"A-[0-9a-f]{32}")
# The release report's opaque per-run label of a sequestered instance, such as
# "S-0001", with more digits beyond S-9999 (D-026).
_LABEL = re.compile(r"S-[0-9]{4,}")


class QcPackError(ValueError):
    """A QC pack, or where it is to be written, that cannot be accepted."""


class Disposition(enum.Enum):
    """What the run did with an input."""

    RELEASED = "released"
    # an identical duplicate of a released input, not written again (D-026)
    DUPLICATE = "duplicate"
    SEQUESTERED = "sequestered"
    # staged, and held until a reviewer decides, such as for a ROI Name (D-009)
    HELD_FOR_REVIEW = "held-for-review"
    # not processed, as when the run stops before anything is written (D-026)
    REFUSED = "refused"


_WITH_OUTPUT = frozenset({Disposition.RELEASED, Disposition.DUPLICATE})


class DropReason(enum.Enum):
    """Why a source value was left out of the residual search (D-027)."""

    # a value that the policy legitimately retains
    RETAINED = "retained"
    # a value that exactly equals a constant that the engine always writes
    WRITTEN_CONSTANT = "written-constant"
    # content that cannot be decoded, inside a sequence that is removed
    UNDECODABLE = "undecodable"
    # a UID that the pinned tables register, which names no one
    REGISTERED_UID = "registered-uid"


class RoiNameOutcome(enum.Enum):
    """What was written for a ROI Name under descriptor cleaning (D-009)."""

    RENAMED = "renamed"  # the automatic tier's vocabulary spelling
    EMPTY = "empty"  # the source name was empty
    KEPT = "kept"  # by a reviewer's decision
    MAPPED = "mapped"  # to another name, by a reviewer's decision
    EMPTIED = "emptied"  # by a reviewer's decision
    HELD = "held"  # held for review; nothing is written
    # held, but the user chose to empty such names so that the run proceeds
    EMPTIED_UNREVIEWED = "emptied unreviewed"


_LO_PADDING = " \x00"
_HELD = frozenset({RoiNameOutcome.HELD, RoiNameOutcome.EMPTIED_UNREVIEWED})
_EMPTIED = frozenset(
    {RoiNameOutcome.EMPTY, RoiNameOutcome.EMPTIED, RoiNameOutcome.EMPTIED_UNREVIEWED}
)
_HELD_BECAUSE = frozenset(
    {
        roi_names.Reason.UNMATCHED,
        roi_names.Reason.AMBIGUOUS,
        roi_names.Reason.ECHOES_IDENTIFIER,
        roi_names.Reason.WOULD_DUPLICATE,
    }
)


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
        released or is a duplicate of one that was.
    label : str, optional
        The opaque per-run label, such as ``S-0001``, by which the release
        report refers to a sequestered input (D-026).
    reasons : tuple of str
        Why an input was sequestered, held for review, or refused, as the
        engine words its findings, which hold no values; empty otherwise.
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
        if self.disposition in _WITH_OUTPUT:
            if self.label is not None or self.reasons:
                return "has no label or reasons"
            return (
                None if _is_output_path(self.output) else "needs a relative output path"
            )
        sequestered = self.disposition is Disposition.SEQUESTERED
        problems = (
            (self.output is not None, "has no output path"),
            (
                sequestered
                and (
                    not isinstance(self.label, str) or not _LABEL.fullmatch(self.label)
                ),
                "needs a label such as S-0001",
            ),
            (not sequestered and self.label is not None, "has no label"),
            (not self.reasons, "needs the reasons for it"),
        )
        return next((problem for failed, problem in problems if failed), None)

    def __repr__(self) -> str:
        return (
            f"InstanceEntry(position={self.position}, "
            f"disposition={self.disposition.value!r}, output={self.output!r}, "
            f"label={self.label!r})"
        )


@dataclasses.dataclass(frozen=True, repr=False)
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
        The codec that both were decoded with: the residual's own, or
        ``latin-1`` where Python cannot decode with that. Bytes that it
        cannot decode are written as backslash escapes, as is each
        backslash in the file, so that the two cannot be confused.

    Its ``repr`` leaves out the text.
    """

    before: str
    after: str
    encoding: str

    def __repr__(self) -> str:
        return (
            f"Excerpt(before={len(self.before)} characters, "
            f"after={len(self.after)} characters, encoding={self.encoding!r})"
        )


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
    >>> cut = excerpt(data, found)
    >>> cut.before, cut.after
    ('Seen by Dr ', 'Zebedee today')
    """
    with memoryview(data) as view, view.cast("B") as octets:
        offset = finding.offset
        if not isinstance(offset, int) or not 0 <= offset < len(octets):
            raise QcPackError("the residual's offset is not in the file")
        width = EXCERPT_BYTES
        # A character of UTF-16LE is two bytes, so keep to the match's parity.
        start = max(offset - width, offset % 2 if _is_wide(finding) else 0)
        end = min(offset + 2 * width, len(octets))
        try:
            decoder = codecs.getincrementaldecoder(finding.encoding)(errors=_UNDECODED)
            # An ISO 2022 codec keeps a state between escape sequences, so
            # decode from the last one before the excerpt, discarding the text.
            escape = bytes(octets[:start]).rfind(b"\x1b")
            if escape >= 0 and "2022" in codecs.lookup(finding.encoding).name:
                decoder.decode(bytes(octets[escape:start]))
            before = decoder.decode(bytes(octets[start:offset]))
            after = decoder.decode(bytes(octets[offset:end]), final=True)
            encoding = finding.encoding
        except (LookupError, UnicodeError):  # a codec Python lacks, or refuses
            before = bytes(octets[start:offset]).decode("latin-1")
            after = bytes(octets[offset:end]).decode("latin-1")
            encoding = "latin-1"
        return Excerpt(_escape(before), _escape(after), encoding)


def _is_wide(finding: residuals.Finding) -> bool:
    return finding.encoding.replace("_", "-").lower() in {"utf-16-le", "utf-16le"}


def _escape(text: str) -> str:
    """Write each undecoded byte, and each backslash, as a backslash escape."""
    return _SENTINELS.sub(
        lambda match: f"\\x{ord(match.group()) - 0xDC00:02x}",
        text.replace("\\", "\\x5c"),
    )


def _mark_undecoded(error: UnicodeError) -> tuple[str, int]:
    """Stand in for each byte that cannot be decoded with a lone surrogate.

    No codec decodes bytes as a lone surrogate, so these are told apart from
    the file's own text and replaced by :func:`_escape`.
    """
    if not isinstance(error, UnicodeDecodeError):
        raise error
    undecoded = error.object[error.start : error.end]
    return "".join(chr(0xDC00 + byte) for byte in undecoded), error.end


_UNDECODED = "pymedphys-deid-qc-undecoded"
_SENTINELS = re.compile("[\udc00-\udcff]")
codecs.register_error(_UNDECODED, _mark_undecoded)


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
    """What descriptor cleaning wrote for one ROI Name, or why it held it (D-009).

    The renamed, kept, and mapped names are the audit of what was retained
    or changed; the held and emptied unreviewed names are the reviewer's
    list. Its ``repr`` leaves out the names.

    Attributes
    ----------
    position : int
        The instance's run position.
    path : ElementPath
        The ROI Name (3006,0026) in its Structure Set ROI Sequence item.
    source : str
        The source ROI Name.
    outcome : RoiNameOutcome
    held_because : ~pymedphys._dicom.deidentify.roi_names.Reason, optional
        Why a held or emptied unreviewed name went to review: unmatched,
        ambiguous, echoes an identifier, or would duplicate another name;
        None for every other outcome.
    written : str, optional
        What was written: the vocabulary's spelling, the source name
        without its leading and trailing spaces and NULs if kept, the reviewer's name if mapped, and ``""`` if emptied or empty;
        None if held.
    """

    position: int
    path: ElementPath
    source: str
    outcome: RoiNameOutcome
    held_because: roi_names.Reason | None = None
    written: str | None = None

    def __post_init__(self) -> None:
        _check_position("a ROI name", self.position)
        if not isinstance(self.path, ElementPath) or not isinstance(self.source, str):
            raise QcPackError(
                f"a ROI name of instance {self.position} needs an ElementPath and text"
            )
        if not isinstance(self.outcome, RoiNameOutcome):
            raise QcPackError(
                f"a ROI name of instance {self.position} needs a RoiNameOutcome"
            )
        problem = self._problem()
        if problem:
            raise QcPackError(
                f"a {self.outcome.value} ROI name of instance {self.position} {problem}"
            )

    def _problem(self) -> str | None:
        if (self.outcome in _HELD) != (self.held_because in _HELD_BECAUSE):
            return "has a reason for review only when it was held"
        if self.outcome is RoiNameOutcome.HELD:
            return None if self.written is None else "has nothing written"
        if not isinstance(self.written, str):
            return "needs what was written"
        if (self.outcome in _EMPTIED) != (self.written == ""):
            return "is written empty only when it was emptied or empty"
        if self.outcome is RoiNameOutcome.KEPT and self.written != self.source.strip(
            _LO_PADDING
        ):
            return "is written as its source name, without padding"
        return None

    def __repr__(self) -> str:
        return (
            f"RoiNameEntry(position={self.position}, path={str(self.path)!r}, "
            f"outcome={self.outcome.value!r})"
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
        each run position from 0; if the sequestered instances' labels are not
        S-0001 to S-n, each once, at the width of n or 4 digits, as the
        release report gives them; if two released instances share an output
        path; if a duplicate's output path is not a released instance's; if an entry names a run position without
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
        width = max(4, len(str(len(labels))))
        if sorted(labels) != [f"S-{n:0{width}d}" for n in range(1, len(labels) + 1)]:
            raise QcPackError(
                "the sequestered instances' labels must be S-0001 onwards, "
                "each once, at one width"
            )
        written = [
            entry.output
            for entry in self.instances
            if entry.disposition is Disposition.RELEASED
        ]
        if len(set(written)) != len(written):
            raise QcPackError("two released instances share an output path")
        if any(
            entry.output not in written
            for entry in self.instances
            if entry.disposition is Disposition.DUPLICATE
        ):
            raise QcPackError("a duplicate's output path is not a released instance's")

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
        and all(
            part not in ("", ".", "..") and "\\" not in part and ":" not in part
            for part in path.parts
        )
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
                "source": entry.source,
                "outcome": entry.outcome.value,
                "held_because": (
                    None if entry.held_because is None else entry.held_because.value
                ),
                "written": entry.written,
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
