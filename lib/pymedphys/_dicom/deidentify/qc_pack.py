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

# pylint: disable = too-many-lines
# One module for the pack's model, whose checks span its entries.

"""The confidential QC pack: what a reviewer needs, kept apart from releases.

A de-identification run's release report can be distributed with its output,
so it holds no source value or original path (D-016). Human review needs
more: which source file each instance came from, the text that the residual
search found and what surrounds it, and the strings that the policy retains.
That material may still identify people, so it goes in a QC pack, written to
a location that the caller designates explicitly, outside the source,
release, and staging directories, and readable only by its owner (D-016).

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
  review, with why and the names of the run's institutional list that it
  matched (D-009);
- ``reference_findings``: each reference finding that the run reports
  without acting on it, such as a dangling reference, at each instance it
  names, with the attribute's tags and its count; the release report gives
  only how many instances have each kind;
- ``pixel_risks``: each instance in a high-risk category, with the
  indicators of risk in its pixel data that put it there (D-017); and
  ``series_risks``: each series of released or held instances with
  findings of its series assessment, a CT volume, the head or neck, or
  unreadable evidence of either, with the instances that show each (D-015,
  D-017);
- ``previews``: each image preview, by its file in the previews directory
  beside the pack, with what it shows and the file's SHA-256, so that an
  attestation of the pack covers them; and ``not_previewed``: each instance
  whose pixel data could not be previewed, with why (D-017). The images are
  made by :mod:`~pymedphys._dicom.deidentify.qc_previews`.

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
import hashlib
import json
import re
import secrets
from collections.abc import Iterable
from pathlib import PurePosixPath

from . import pixel_risk, residuals, roi_names
from .file_layout import TAG_PATTERN, ElementPath, Location
from .reference_graph import FindingKind
from .labels import LABEL_PATTERN
from .residuals import UnsearchedReason
from .reviewed_roi_names import Outcome

# The format of the pack document. A change to its fields takes a new label.
FORMAT = "pymedphys-deid-qc-pack/1"
# The bytes of a written file shown on each side of a residual's offset.
EXCERPT_BYTES = 48

# The directory, beside the pack's file, that holds its previews.
PREVIEW_DIRECTORY = "previews"
# The most bytes copied at a time while finding an excerpt's decoding state.
_CHUNK_BYTES = 4096

_REFERENCE = re.compile(r"A-[0-9a-f]{32}")


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


# Why a source value was left out of the residual search (D-027), as the
# search and the release report name it.
DropReason = UnsearchedReason
# What was written for a ROI Name under descriptor cleaning (D-009).
RoiNameOutcome = Outcome


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
                    not isinstance(self.label, str)
                    or not LABEL_PATTERN.fullmatch(self.label)
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
            if "2022" in codecs.lookup(finding.encoding).name:
                _prime(decoder, octets, start)
            before = decoder.decode(bytes(octets[start:offset]))
            after = decoder.decode(bytes(octets[offset:end]), final=True)
            encoding = finding.encoding
        except (LookupError, UnicodeError):  # a codec Python lacks, or refuses
            before = bytes(octets[start:offset]).decode("latin-1")
            after = bytes(octets[offset:end]).decode("latin-1")
            encoding = "latin-1"
        return Excerpt(_escape(before), _escape(after), encoding)


def _prime(decoder: codecs.IncrementalDecoder, octets: memoryview, start: int) -> None:
    """Decode from the last escape sequence before ``start``, discarding the text.

    Both the search and the decoding read at most :data:`_CHUNK_BYTES` at a
    time, so a late residual in a large file needs no copy of what precedes
    it.
    """
    end = start
    while end > 0:
        begin = max(0, end - _CHUNK_BYTES)
        found = bytes(octets[begin:end]).rfind(b"\x1b")
        if found >= 0:
            for at in range(begin + found, start, _CHUNK_BYTES):
                decoder.decode(bytes(octets[at : min(at + _CHUNK_BYTES, start)]))
            return
        end = begin


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
class ReferenceFindingEntry:
    """A reference finding at an instance that the run reports only.

    Attributes
    ----------
    position : int
        The instance's run position.
    kind : ~pymedphys._dicom.deidentify.reference_graph.FindingKind
    attribute : tuple of str
        The tags from the outermost sequence to the attribute concerned.
    count : int
        The finding's count, as
        :class:`~pymedphys._dicom.deidentify.reference_graph.Finding` gives
        it, such as how many distinct values of a dangling reference name
        nothing; otherwise 0.
    """

    position: int
    kind: FindingKind
    attribute: tuple[str, ...]
    count: int = 0

    def __post_init__(self) -> None:
        _check_position("a reference finding", self.position)
        tags = isinstance(self.attribute, tuple) and all(
            isinstance(tag, str) and TAG_PATTERN.fullmatch(tag)
            for tag in self.attribute
        )
        if (
            not isinstance(self.kind, FindingKind)
            or not (tags and self.attribute)
            or type(self.count) is not int  # pylint: disable = unidiomatic-typecheck
            or self.count < 0
        ):
            raise QcPackError(
                f"a reference finding of instance {self.position} needs a "
                "FindingKind, its tags, and a count from 0"
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
    institutional_matches : tuple of str, optional
        For a held or emptied unreviewed name, the names of the run's
        institutional list that it matched, to show its reviewer; empty
        otherwise, or where the run had no list.
    """

    position: int
    path: ElementPath
    source: str
    outcome: RoiNameOutcome
    held_because: roi_names.Reason | None = None
    written: str | None = None
    institutional_matches: tuple[str, ...] = ()

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
        problem = self._problem() or self._matches_problem()
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

    def _matches_problem(self) -> str | None:
        if not isinstance(self.institutional_matches, tuple) or not all(
            isinstance(name, str) and name for name in self.institutional_matches
        ):
            return "needs its institutional matches as a tuple of names as text"
        if self.institutional_matches and self.outcome not in _HELD:
            return "has institutional matches only when it was held"
        return None

    def __repr__(self) -> str:
        return (
            f"RoiNameEntry(position={self.position}, path={str(self.path)!r}, "
            f"outcome={self.outcome.value!r})"
        )


class PreviewKind(enum.Enum):
    """What an image preview shows (D-017)."""

    SERIES_CINE = "series-cine"  # frames evenly spaced through a series
    SERIES_MIP = "series-mip"  # a frontal maximum intensity projection
    INSTANCE = "instance"  # a high-risk instance at full resolution


class NotPreviewedReason(enum.Enum):
    """Why an instance has no image preview."""

    COMPRESSED = "compressed-pixel-data"
    UNSUPPORTED = "unsupported-pixel-data"
    UNREADABLE = "unreadable-pixel-data"
    # a high-risk instance, such as an RT Structure Set, without pixel data
    NO_PIXEL_DATA = "no-pixel-data"
    # a released or held instance whose written file the run did not hand over
    NOT_AVAILABLE = "file-not-available"


PREVIEW_NAME = re.compile(r"P-[0-9]{4,}\.png")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# The dispositions whose written files a reviewer sees.
_REVIEWED = frozenset({Disposition.RELEASED, Disposition.HELD_FOR_REVIEW})


@dataclasses.dataclass(frozen=True, repr=False)
class Preview:
    """An image preview, as a PNG file, for the review of D-017.

    Its ``repr`` leaves out the image.

    Attributes
    ----------
    name : str
        Its file name, ``P-0001.png`` onwards, which the pack's previews
        directory holds.
    kind : PreviewKind
    frames : tuple of (int, int)
        The frames it shows, each by run position and frame index from 0,
        in the order shown: row by row for a strip.
    total_frames : int
        How many frames its series or instance has, at least as many as it
        shows.
    png : bytes
        The PNG file.
    """

    name: str
    kind: PreviewKind
    frames: tuple[tuple[int, int], ...]
    total_frames: int
    png: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not PREVIEW_NAME.fullmatch(self.name):
            raise QcPackError("a preview needs a name such as P-0001.png")
        if not isinstance(self.kind, PreviewKind):
            raise QcPackError(f"preview {self.name} needs a PreviewKind")
        if not (
            isinstance(self.frames, tuple)
            and self.frames
            and all(_is_frame(frame) for frame in self.frames)
            and len(set(self.frames)) == len(self.frames)
        ):
            raise QcPackError(
                f"preview {self.name} needs distinct frames of a run position "
                "and a frame index"
            )
        if (
            not isinstance(self.total_frames, int)
            or isinstance(self.total_frames, bool)
            or self.total_frames < len(self.frames)
        ):
            raise QcPackError(
                f"preview {self.name} needs at least as many frames as it shows"
            )
        if not isinstance(self.png, bytes) or not self.png.startswith(_PNG_SIGNATURE):
            raise QcPackError(f"preview {self.name} needs a PNG file")

    @property
    def sha256(self) -> str:
        """The SHA-256 of the PNG file, in lower-case hexadecimal."""
        return hashlib.sha256(self.png).hexdigest()

    def __repr__(self) -> str:
        return (
            f"Preview(name={self.name!r}, kind={self.kind.value!r}, "
            f"frames={len(self.frames)}, total_frames={self.total_frames})"
        )


def _is_frame(frame: object) -> bool:
    return (
        isinstance(frame, tuple)
        and len(frame) == 2
        and all(
            isinstance(index, int) and not isinstance(index, bool) and index >= 0
            for index in frame
        )
    )


@dataclasses.dataclass(frozen=True)
class NotPreviewedEntry:
    """An instance whose written file has no preview, and why.

    Attributes
    ----------
    position : int
        The instance's run position.
    reason : NotPreviewedReason
    """

    position: int
    reason: NotPreviewedReason

    def __post_init__(self) -> None:
        _check_position("an instance not previewed", self.position)
        if not isinstance(self.reason, NotPreviewedReason):
            raise QcPackError(
                f"instance {self.position} not previewed needs a NotPreviewedReason"
            )


@dataclasses.dataclass(frozen=True)
class PixelRiskEntry:
    """An instance in a high-risk category, and the indicators that put it there.

    Attributes
    ----------
    position : int
        The instance's run position.
    findings : tuple of ~pymedphys._dicom.deidentify.pixel_risk.Finding
        At least one; each names an indicator, its risk, and an attribute
        path, never a value.
    """

    position: int
    findings: tuple[pixel_risk.Finding, ...]

    def __post_init__(self) -> None:
        _check_position("a high-risk instance", self.position)
        if not (
            isinstance(self.findings, tuple)
            and self.findings
            and all(
                isinstance(finding, pixel_risk.Finding) for finding in self.findings
            )
        ):
            raise QcPackError(
                f"high-risk instance {self.position} needs its pixel risk findings"
            )


@dataclasses.dataclass(frozen=True)
class SeriesRiskEntry:
    """A series with indicators of risk as a whole, and the instances that show each.

    Attributes
    ----------
    positions : tuple of int
        The run positions of the series' instances that were assessed, in
        order, each once.
    findings : tuple of ~pymedphys._dicom.deidentify.pixel_risk.SeriesFinding
        At least one, as :func:`~.pixel_risk.assess_ct_series` gave them for
        those instances, so that each finding's ``instances`` count from 0
        in ``positions``, each once, in order; each names an indicator, its risk, and an
        attribute path or none, never a value.
    """

    positions: tuple[int, ...]
    findings: tuple[pixel_risk.SeriesFinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.positions, tuple) or not self.positions:
            raise QcPackError("a series with risks needs its instances' run positions")
        for position in self.positions:
            _check_position("a series with risks", position)
        if list(self.positions) != sorted(set(self.positions)):
            raise QcPackError(
                "a series with risks must list each instance once, in order"
            )
        if not (
            isinstance(self.findings, tuple)
            and self.findings
            and all(
                isinstance(finding, pixel_risk.SeriesFinding)
                and finding.instances
                and all(
                    isinstance(index, int)
                    and not isinstance(index, bool)
                    and 0 <= index < len(self.positions)
                    for index in finding.instances
                )
                and list(finding.instances) == sorted(set(finding.instances))
                for finding in self.findings
            )
        ):
            raise QcPackError(
                f"the series at run position {self.positions[0]} needs its "
                "findings, each of its own instances"
            )

    def shown_by(self, finding: pixel_risk.SeriesFinding) -> tuple[int, ...]:
        """Return the run positions of the instances that show a finding."""
        return tuple(self.positions[index] for index in finding.instances)


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
    reference_findings : tuple of ReferenceFindingEntry
    pixel_risks : tuple of PixelRiskEntry
        Each high-risk instance once, in run position order.
    series_risks : tuple of SeriesRiskEntry
        Each instance in at most one, by its first run position in order;
        each instance released or held for review.
    previews : tuple of Preview
        Named ``P-0001.png`` onwards, in order, at one width.
    not_previewed : tuple of NotPreviewedEntry
        Each instance once, in run position order.

    Raises
    ------
    QcPackError
        If an attribute is not of its type; if the instances are not one for
        each run position from 0; if the sequestered instances' labels are not
        S-0001 to S-n, each once, at the width of n or 4 digits, as the
        release report gives them; if two released instances share an output
        path; if a duplicate's output path is not a released instance's; if an entry names a run position without
        an instance; or if two retained strings are the same; if a preview
        shows a frame of an instance that was neither released nor held for
        review, or the previews are not named P-0001.png onwards; or if an
        instance is listed twice as high-risk or as not previewed, or out of
        order; or if an instance is in two series with risks, the series are
        out of order, or one has an instance that was neither released nor
        held for review.
    """

    reference: str
    instances: tuple[InstanceEntry, ...]
    residual_findings: tuple[ResidualEntry, ...] = ()
    drops: tuple[DropEntry, ...] = ()
    not_searched: tuple[NotSearchedEntry, ...] = ()
    retained_strings: tuple[RetainedString, ...] = ()
    roi_names: tuple[RoiNameEntry, ...] = ()
    reference_findings: tuple[ReferenceFindingEntry, ...] = ()
    pixel_risks: tuple[PixelRiskEntry, ...] = ()
    series_risks: tuple[SeriesRiskEntry, ...] = ()
    previews: tuple[Preview, ...] = ()
    not_previewed: tuple[NotPreviewedEntry, ...] = ()

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
            "reference_findings": ReferenceFindingEntry,
            "pixel_risks": PixelRiskEntry,
            "series_risks": SeriesRiskEntry,
            "previews": Preview,
            "not_previewed": NotPreviewedEntry,
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
        for name in (
            "residual_findings",
            "drops",
            "not_searched",
            "roi_names",
            "reference_findings",
            "pixel_risks",
            "not_previewed",
        ):
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
        for name in ("pixel_risks", "not_previewed"):
            listed = [entry.position for entry in getattr(self, name)]
            if listed != sorted(set(listed)):
                raise QcPackError(f"{name} must list each instance once, in order")
        self._check_series()
        self._check_previews()

    def _check_series(self) -> None:
        firsts = [entry.positions[0] for entry in self.series_risks]
        if firsts != sorted(firsts):
            raise QcPackError("series_risks must be in order of their first instance")
        listed = [
            position for entry in self.series_risks for position in entry.positions
        ]
        if len(set(listed)) != len(listed):
            raise QcPackError("an instance is in two series of series_risks")
        if any(
            position >= len(self.instances)
            or self.instances[position].disposition not in _REVIEWED
            for position in listed
        ):
            raise QcPackError(
                "series_risks names an instance that was neither released nor "
                "held for review"
            )

    def _check_previews(self) -> None:
        width = max(4, len(str(len(self.previews))))
        if [preview.name for preview in self.previews] != [
            f"P-{number:0{width}d}.png" for number in range(1, len(self.previews) + 1)
        ]:
            raise QcPackError("previews must be named P-0001.png onwards, at one width")
        if any(
            position >= len(self.instances)
            or self.instances[position].disposition not in _REVIEWED
            for preview in self.previews
            for position, _ in preview.frames
        ):
            raise QcPackError(
                "a preview shows an instance that was neither released nor held "
                "for review"
            )

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
            f"roi_names={len(self.roi_names)}, "
            f"reference_findings={len(self.reference_findings)}, "
            f"pixel_risks={len(self.pixel_risks)}, "
            f"series_risks={len(self.series_risks)}, previews={len(self.previews)}, "
            f"not_previewed={len(self.not_previewed)})"
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
                "institutional_matches": list(entry.institutional_matches),
            }
            for entry in pack.roi_names
        ],
        "reference_findings": [
            {
                "position": entry.position,
                "kind": entry.kind.value,
                "attribute": " > ".join(entry.attribute),
                "count": entry.count,
            }
            for entry in pack.reference_findings
        ],
        "pixel_risks": [
            {
                "position": entry.position,
                "findings": [
                    {
                        "indicator": finding.indicator.value,
                        "risk": finding.risk.value if finding.risk else None,
                        "element": str(finding.path),
                    }
                    for finding in entry.findings
                ],
            }
            for entry in pack.pixel_risks
        ],
        "series_risks": [
            {
                "positions": list(entry.positions),
                "findings": [
                    {
                        "indicator": finding.indicator.value,
                        "risk": finding.risk.value if finding.risk else None,
                        "element": None if finding.path is None else str(finding.path),
                        "positions": list(entry.shown_by(finding)),
                    }
                    for finding in entry.findings
                ],
            }
            for entry in pack.series_risks
        ],
        "previews": [
            {
                "file": f"{PREVIEW_DIRECTORY}/{preview.name}",
                "kind": preview.kind.value,
                "frames": [
                    {"position": position, "frame": frame}
                    for position, frame in preview.frames
                ],
                "total_frames": preview.total_frames,
                "sha256": preview.sha256,
            }
            for preview in pack.previews
        ],
        "not_previewed": [
            {"position": entry.position, "reason": entry.reason.value}
            for entry in pack.not_previewed
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
