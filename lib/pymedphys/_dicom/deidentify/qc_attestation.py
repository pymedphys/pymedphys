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

"""A reviewer's attestation of a QC pack, and its record for the release report.

A reviewer who has worked through a run's QC pack
(:mod:`~pymedphys._dicom.deidentify.qc_pack`) attests to it with
:func:`attest`, which writes :data:`ATTESTATION_FILE` into the pack's
directory, labelled with its format, :data:`FORMAT`. The attestation names
the reviewer and when they attested, states whether they reviewed what D-017
requires (every distinct retained string, every series, and every instance in
high-risk categories), and gives the outcome. It may also give a face verdict
for any of the pack's series, by the series' first run position: whether the
reviewer saw a recognisable face in its previews, such as the renders of its
skin surface (D-017). It is bound to the pack by the
SHA-256 of the pack's file, which records the SHA-256 of each of its image
previews, so a pack or preview changed after it was attested is detected. A pack is attested once: the file is never overwritten.

The attestation is confidential with the pack, since it names the reviewer
and sits beside the review material. The release report records only
:func:`attestation_record`: the pack's opaque reference and the outcome
(D-016). An outcome of attested needs every review that D-017 requires; a
reviewer who could not complete them records a rejection.

A face verdict is the reviewer's judgement of what the previews show, and
the pack records the SHA-256 of each source file of the series, so the
verdict is bound, through the pack, to the files the reviewer saw. A series
without a verdict has none. An attestation whose outcome is rejected gives no
verdict of either kind, since its verdicts would release nothing.

The attestation may likewise give a redaction verdict for any instance whose
Pixel Data the Clean Pixel Data Option cleaned and the pack previewed, by
its run position, as the pack's ``redactions`` lists it, from the previews
of each of its frames: :attr:`Redaction.ACCEPTED` where the pack's regions
cover every burned-in text and may be blacked out, :attr:`Redaction.REVISED`
with regions of the reviewer's own, which are blacked out as well as the
pack's, so that together they cover every burned-in text, and
:attr:`Redaction.REJECTED` where the instance is not to be released. Each
is bound to the instance's source file as a face verdict is to its series'.

The person releasing the data may also confirm, yes or no, that the output
was checked for its intended use and that its residual risk was accepted
under the institution's governance. Each confirmation is optional, holds no
text, is bound to the pack with the rest of the attestation, and reaches the
release report's record as its outcome alone. Fitness for a use and an
acceptable residual risk depend on the purpose and the recipient, which only
the releaser knows, so the engine records the releaser's word and decides
neither.

An attestation covers human review of the pack. It is one of the three gates
of a ``public-release`` run, with statistical disclosure control and pixel and
face review (D-017), and passing it does not pass the others.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import os
import re
import stat
from collections.abc import Iterable, Mapping
from pathlib import Path

from . import qc_pack, qc_store
from .qc_pack import QcPackError
from .text_detection import TextBox

# The format of the attestation document. A change to its fields takes a new label.
FORMAT = "pymedphys-deid-qc-attestation/3"
ATTESTATION_FILE = "attestation.json"

_DIGEST = re.compile(r"[0-9a-f]{64}")
_REFERENCE = re.compile(r"A-[0-9a-f]{32}")
_PREVIEW_FILE = re.compile(
    re.escape(qc_pack.PREVIEW_DIRECTORY) + "/" + qc_pack.PREVIEW_NAME.pattern
)


class Outcome(enum.Enum):
    """The outcome of human QC review, as the release report records it."""

    ATTESTED = "attested"  # the reviewer found the output fit for release
    REJECTED = "rejected"  # the reviewer did not
    NOT_ATTESTED = "not-attested"  # no reviewer has attested to the pack


class Face(enum.Enum):
    """A reviewer's face verdict on a series, from its previews."""

    ABSENT = "absent"  # the reviewer saw no recognisable face
    PRESENT = "present"  # the reviewer saw a recognisable face


@dataclasses.dataclass(frozen=True)
class FaceVerdict:
    """A reviewer's face verdict on one series of the pack.

    Attributes
    ----------
    series : int
        The run position of the series' first instance, as the pack's
        ``series`` lists it.
    face : Face
    """

    series: int
    face: Face

    def __post_init__(self) -> None:
        if (
            not isinstance(self.series, int)
            or isinstance(self.series, bool)
            or self.series < 0
        ):
            raise QcPackError("a face verdict needs its series' first run position")
        if not isinstance(self.face, Face):
            raise QcPackError(f"the face verdict on series {self.series} needs a Face")


class Redaction(enum.Enum):
    """A reviewer's verdict on an instance whose Pixel Data were cleaned."""

    # the pack's regions cover every burned-in text, and may be blacked out
    ACCEPTED = "accepted"
    # the reviewer's own regions are to be blacked out as well as the pack's
    REVISED = "revised"
    # the instance is not to be released
    REJECTED = "rejected"


@dataclasses.dataclass(frozen=True)
class RedactionVerdict:
    """A reviewer's redaction verdict on one instance of the pack.

    Attributes
    ----------
    position : int
        The instance's run position, as the pack's ``redactions`` lists it.
    redaction : Redaction
    regions : tuple of (int, tuple of TextBox)
        Under :attr:`Redaction.REVISED`, the regions to black out as well as
        the pack's, which the finder missed: each frame with a region, by
        index from 0, in order, with its regions, sorted, each once, as the
        pack gives them; at least one. Empty under any other verdict.
    """

    position: int
    redaction: Redaction
    regions: tuple[tuple[int, tuple[TextBox, ...]], ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.position, int)
            or isinstance(self.position, bool)
            or self.position < 0
        ):
            raise QcPackError("a redaction verdict needs its instance's run position")
        if not isinstance(self.redaction, Redaction):
            raise QcPackError(
                f"the redaction verdict on instance {self.position} needs a Redaction"
            )
        if not isinstance(self.regions, tuple) or not all(
            _is_frame_regions(entry) for entry in self.regions
        ):
            raise QcPackError(
                f"the redaction verdict on instance {self.position} needs regions "
                "of its frames, each a frame index with sorted, distinct boxes"
            )
        frames = [index for index, _ in self.regions]
        if frames != sorted(set(frames)):
            raise QcPackError(
                f"the redaction verdict on instance {self.position} must list each "
                "frame once, in order"
            )
        if bool(self.regions) != (self.redaction is Redaction.REVISED):
            raise QcPackError(
                f"the redaction verdict on instance {self.position} gives regions "
                "exactly where it revises them"
            )


def _is_frame_regions(entry: object) -> bool:
    if not (isinstance(entry, tuple) and len(entry) == 2):
        return False
    index, boxes = entry
    return (
        isinstance(index, int)
        and not isinstance(index, bool)
        and index >= 0
        and isinstance(boxes, tuple)
        and bool(boxes)
        and all(_is_box(box) for box in boxes)
        and list(boxes) == sorted(set(boxes))
    )


def _is_box(box: object) -> bool:
    return isinstance(box, TextBox) and all(
        isinstance(end, int) and not isinstance(end, bool)
        for end in dataclasses.astuple(box)
    )


@dataclasses.dataclass(frozen=True)
class Coverage:
    """Whether the reviewer reviewed what D-017 requires.

    Attributes
    ----------
    retained_strings : bool
        Every distinct retained string.
    series : bool
        Every series, by maximum intensity projection or cine strip.
    high_risk_instances : bool
        Every instance in high-risk categories.
    """

    retained_strings: bool
    series: bool
    high_risk_instances: bool

    def __post_init__(self) -> None:
        if not all(isinstance(value, bool) for value in dataclasses.astuple(self)):
            raise QcPackError("each part of the coverage must be True or False")

    @property
    def complete(self) -> bool:
        """Whether every review that D-017 requires was done."""
        return all(dataclasses.astuple(self))


@dataclasses.dataclass(frozen=True, repr=False)
class Attestation:
    """A reviewer's attestation of one QC pack.

    Its ``repr`` leaves out the reviewer.

    Attributes
    ----------
    reference : str
        The pack's opaque reference.
    pack_digest : str
        The SHA-256 of the pack's file, in lower-case hexadecimal.
    outcome : Outcome
        :attr:`Outcome.ATTESTED` or :attr:`Outcome.REJECTED`.
    coverage : Coverage
    reviewer : str
        Who attested, as they name themselves.
    attested_at : datetime.datetime
        When, in UTC.
    intended_use_checked, residual_risk_accepted : bool or None
        The releaser's confirmations, as the module describes; ``None``
        where not stated.
    faces : tuple of FaceVerdict
        The face verdicts, by series in run position order, each series
        once; empty where the reviewer gave none.
    redactions : tuple of RedactionVerdict
        The redaction verdicts, by instance in run position order, each
        instance once; empty where the reviewer gave none.
    """

    reference: str
    pack_digest: str
    outcome: Outcome
    coverage: Coverage
    reviewer: str
    attested_at: datetime.datetime
    intended_use_checked: bool | None = None
    residual_risk_accepted: bool | None = None
    faces: tuple[FaceVerdict, ...] = ()
    redactions: tuple[RedactionVerdict, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not _REFERENCE.fullmatch(
            self.reference
        ):
            raise QcPackError("an attestation needs the pack's reference")
        if not isinstance(self.pack_digest, str) or not _DIGEST.fullmatch(
            self.pack_digest
        ):
            raise QcPackError("an attestation needs the SHA-256 of the pack")
        if self.outcome not in (Outcome.ATTESTED, Outcome.REJECTED):
            raise QcPackError("an attestation's outcome is attested or rejected")
        if not isinstance(self.coverage, Coverage):
            raise QcPackError("an attestation needs its Coverage")
        if self.outcome is Outcome.ATTESTED and not self.coverage.complete:
            raise QcPackError(
                "an outcome of attested needs every retained string, series, "
                "and high-risk instance reviewed"
            )
        if not isinstance(self.reviewer, str) or not self.reviewer.strip():
            raise QcPackError("an attestation needs its reviewer")
        if not isinstance(
            self.attested_at, datetime.datetime
        ) or self.attested_at.utcoffset() != datetime.timedelta(0):
            raise QcPackError("an attestation needs its time in UTC")
        _check_confirmations(self.intended_use_checked, self.residual_risk_accepted)
        if not isinstance(self.faces, tuple) or not all(
            isinstance(verdict, FaceVerdict) for verdict in self.faces
        ):
            raise QcPackError("an attestation's face verdicts must be FaceVerdicts")
        series = [verdict.series for verdict in self.faces]
        if series != sorted(set(series)):
            raise QcPackError(
                "an attestation gives each series at most one face verdict, in order"
            )
        if not isinstance(self.redactions, tuple) or not all(
            isinstance(verdict, RedactionVerdict) for verdict in self.redactions
        ):
            raise QcPackError(
                "an attestation's redaction verdicts must be RedactionVerdicts"
            )
        positions = [verdict.position for verdict in self.redactions]
        if positions != sorted(set(positions)):
            raise QcPackError(
                "an attestation gives each instance at most one redaction verdict, "
                "in order"
            )

    def __repr__(self) -> str:
        return (
            f"Attestation(reference={self.reference!r}, outcome={self.outcome.value!r})"
        )


@dataclasses.dataclass(frozen=True)
class AttestationRecord:
    """What the release report records of human QC review (D-016).

    Attributes
    ----------
    reference : str
        The QC pack's opaque reference, ``A-`` and 32 hex digits.
    outcome : Outcome
    intended_use_checked, residual_risk_accepted : bool or None
        The releaser's confirmations in the attestation; ``None`` where not
        stated or not attested.
    """

    reference: str
    outcome: Outcome
    intended_use_checked: bool | None = None
    residual_risk_accepted: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not _REFERENCE.fullmatch(
            self.reference
        ):
            raise QcPackError("an attestation record needs the pack's reference")
        if not isinstance(self.outcome, Outcome):
            raise QcPackError("an attestation record needs an Outcome")
        _check_confirmations(self.intended_use_checked, self.residual_risk_accepted)
        if self.outcome is Outcome.NOT_ATTESTED and (
            self.intended_use_checked is not None
            or self.residual_risk_accepted is not None
        ):
            raise QcPackError("a pack that is not attested has no confirmations")


def _check_confirmations(*confirmations: object) -> None:
    if not all(each is None or isinstance(each, bool) for each in confirmations):
        raise QcPackError("each confirmation must be True, False, or None")


def attestation_document(attestation: Attestation) -> dict:
    """Return an attestation as JSON values, labelled with :data:`FORMAT`."""
    if not isinstance(attestation, Attestation):
        raise TypeError("attestation must be an Attestation")
    return {
        "format": FORMAT,
        "reference": attestation.reference,
        "pack_digest": attestation.pack_digest,
        "outcome": attestation.outcome.value,
        "coverage": dataclasses.asdict(attestation.coverage),
        "reviewer": attestation.reviewer,
        "attested_at": attestation.attested_at.isoformat(),
        "releaser": {
            "intended_use_checked": attestation.intended_use_checked,
            "residual_risk_accepted": attestation.residual_risk_accepted,
        },
        "faces": [
            {"series": verdict.series, "face": verdict.face.value}
            for verdict in attestation.faces
        ],
        "redactions": [
            {
                "position": verdict.position,
                "redaction": verdict.redaction.value,
                "regions": [
                    {
                        "frame": index,
                        "boxes": [
                            [box.top, box.left, box.bottom, box.right] for box in boxes
                        ],
                    }
                    for index, boxes in verdict.regions
                ],
            }
            for verdict in attestation.redactions
        ],
    }


def attest(
    pack_directory: os.PathLike | str,
    *,
    reviewer: str,
    outcome: Outcome,
    coverage: Coverage,
    attested_at: datetime.datetime | None = None,
    intended_use_checked: bool | None = None,
    residual_risk_accepted: bool | None = None,
    faces: Mapping[int, Face] | None = None,
    redactions: Iterable[RedactionVerdict] = (),
) -> Attestation:
    """Attest to a QC pack, and write the attestation beside it.

    Parameters
    ----------
    pack_directory : path-like
        The directory that :func:`~.qc_store.write_qc_pack` wrote.
    reviewer : str
        Who attests, as they name themselves.
    outcome : Outcome
        :attr:`Outcome.ATTESTED` or :attr:`Outcome.REJECTED`.
    coverage : Coverage
        What the reviewer reviewed; complete for an outcome of attested.
    attested_at : datetime.datetime, optional
        When, in UTC; now if not given.
    intended_use_checked, residual_risk_accepted : bool, optional
        The releaser's confirmations, as the module describes; not stated
        if not given.
    faces : mapping of int to Face, optional
        A face verdict for each series that the reviewer judged, by the run
        position of its first instance, as the pack's ``series`` lists it;
        none if not given.
    redactions : iterable of RedactionVerdict, optional
        A redaction verdict for each instance that the reviewer judged, of
        those that the pack's ``redactions`` lists and that it previewed;
        none if not given.

    Returns
    -------
    Attestation

    Raises
    ------
    QcPackError
        If the directory holds no QC pack, the pack is not of its format, a
        preview that it lists is missing or changed, a face verdict names a
        run position that does not begin one of the pack's series, a
        redaction verdict names an instance that the pack's ``redactions``
        does not list, or lists as not previewed, or gives a region in a
        frame that its Pixel Data do not hold, or it has already been
        attested; if an outcome of rejected is given a verdict; or for any
        reason that :class:`Attestation` gives.
    """
    directory = Path(pack_directory)
    data = _pack_bytes(directory)
    reference = _reference_of(data)
    if not _previews_intact(directory, data):
        raise QcPackError("a preview of the QC pack is missing or changed")
    verdicts = _face_verdicts({} if faces is None else faces)
    by_position = _redaction_verdicts(redactions)
    if outcome is Outcome.REJECTED and (verdicts or by_position):
        # A rejected attestation's verdicts release nothing, and a pack is
        # attested once, so a verdict given with it is refused (D-016).
        raise QcPackError(
            "an outcome of rejected is given a verdict, which would release nothing"
        )
    firsts = _firsts(data)
    unknown = [verdict.series for verdict in verdicts if verdict.series not in firsts]
    if unknown:
        raise QcPackError(
            "a face verdict names run position "
            + ", ".join(str(series) for series in unknown)
            + ", which begins none of the QC pack's series"
        )
    cleaned = previewed_redactions(data)
    for verdict in by_position:
        if verdict.position not in cleaned:
            raise QcPackError(
                f"a redaction verdict names run position {verdict.position}, "
                "which the QC pack does not list as cleaned and previewed"
            )
        if any(index >= cleaned[verdict.position] for index, _ in verdict.regions):
            raise QcPackError(
                f"the redaction verdict on run position {verdict.position} gives "
                "a region in a frame that its Pixel Data do not hold"
            )
    attestation = Attestation(
        reference=reference,
        pack_digest=hashlib.sha256(data).hexdigest(),
        outcome=outcome,
        coverage=coverage,
        reviewer=reviewer,
        attested_at=(
            datetime.datetime.now(datetime.timezone.utc)
            if attested_at is None
            else attested_at
        ),
        intended_use_checked=intended_use_checked,
        residual_risk_accepted=residual_risk_accepted,
        faces=verdicts,
        redactions=by_position,
    )
    text = json.dumps(attestation_document(attestation), indent=2, ensure_ascii=True)
    try:
        qc_store.write_new(directory / ATTESTATION_FILE, text + "\n")
    except FileExistsError:
        raise QcPackError("the QC pack has already been attested") from None
    except OSError as error:
        raise qc_store.os_error("the attestation could not be written", error) from None
    return attestation


def _face_verdicts(faces: Mapping[int, Face]) -> tuple[FaceVerdict, ...]:
    """Return face verdicts by series in run position order, after checking them."""
    if not isinstance(faces, Mapping):
        raise QcPackError("faces must map a series' first run position to a Face")
    verdicts = [FaceVerdict(series, face) for series, face in faces.items()]
    return tuple(sorted(verdicts, key=lambda verdict: verdict.series))


def _redaction_verdicts(
    redactions: Iterable[RedactionVerdict],
) -> tuple[RedactionVerdict, ...]:
    """Return redaction verdicts in run position order, after checking them."""
    if isinstance(redactions, (str, bytes, Mapping)) or not isinstance(
        redactions, Iterable
    ):
        raise QcPackError("redactions must be RedactionVerdicts")
    verdicts = list(redactions)
    if not all(isinstance(verdict, RedactionVerdict) for verdict in verdicts):
        raise QcPackError("redactions must be RedactionVerdicts")
    return tuple(sorted(verdicts, key=lambda verdict: verdict.position))


def previewed_redactions(data: bytes) -> dict[int, int]:
    """Return how many frames each cleaned instance holds, by run position,
    for the instances that the QC pack ``data`` previewed.

    A cleaned instance that the pack lists as not previewed is left out,
    since a reviewer cannot have seen its frames, and so can give it no
    verdict.

    Raises
    ------
    QcPackError
        If the pack's ``redactions`` or ``not_previewed`` is not of its
        format.
    """
    document = json.loads(data.decode("ascii"))
    redactions = document.get("redactions")
    unshown = document.get("not_previewed")
    if not isinstance(redactions, list) or not isinstance(unshown, list):
        raise QcPackError("the QC pack is not of its format")
    hidden = set()
    for entry in unshown:
        position = entry.get("position") if isinstance(entry, dict) else None
        if not isinstance(position, int):
            raise QcPackError("the QC pack is not of its format")
        hidden.add(position)
    frames = {}
    for entry in redactions:
        position = entry.get("position") if isinstance(entry, dict) else None
        count = entry.get("frames") if isinstance(entry, dict) else None
        if not isinstance(position, int) or not isinstance(count, int):
            raise QcPackError("the QC pack is not of its format")
        if position not in hidden:
            frames[position] = count
    return frames


def redaction_previews(pack_directory: os.PathLike | str) -> dict[tuple[int, int], str]:
    """Return the preview that shows each frame of each cleaned instance, as
    a file name within the QC pack, by run position and frame.

    The attestation command names it beside each region that a revised
    verdict adds, so that the reviewer can check the region against the
    frame it was read from (D-048).

    Raises
    ------
    QcPackError
        If the directory holds no QC pack, or its ``previews`` are not of its
        format.
    """
    data = _pack_bytes(Path(pack_directory))
    _reference_of(data)  # refuses a pack that is not of its format
    document = json.loads(data.decode("ascii"))
    previews = document.get("previews")
    if not isinstance(previews, list):
        raise QcPackError("the QC pack is not of its format")
    files = {}
    for preview in previews:
        if not isinstance(preview, dict):
            raise QcPackError("the QC pack is not of its format")
        if preview.get("kind") != qc_pack.PreviewKind.REDACTION.value:
            continue
        name, frames = preview.get("file"), preview.get("frames")
        if not isinstance(name, str) or not isinstance(frames, list):
            raise QcPackError("the QC pack is not of its format")
        for shown in frames:
            position = shown.get("position") if isinstance(shown, dict) else None
            frame = shown.get("frame") if isinstance(shown, dict) else None
            if not isinstance(position, int) or not isinstance(frame, int):
                raise QcPackError("the QC pack is not of its format")
            files[(position, frame)] = name
    return files


def _firsts(data: bytes) -> frozenset[int]:
    """Return the first run position of each series that the pack lists."""
    document = json.loads(data.decode("ascii"))  # _reference_of has parsed it
    series = document.get("series")
    if not isinstance(series, list):
        raise QcPackError("the QC pack is not of its format")
    firsts = set()
    for entry in series:
        positions = entry.get("positions") if isinstance(entry, dict) else None
        if not isinstance(positions, list) or not positions:
            raise QcPackError("the QC pack is not of its format")
        firsts.add(positions[0])
    return frozenset(firsts)


def attestation_record(pack_directory: os.PathLike | str) -> AttestationRecord:
    """Return the release report's record of a QC pack's attestation.

    Parameters
    ----------
    pack_directory : path-like
        The directory that :func:`~.qc_store.write_qc_pack` wrote.

    Returns
    -------
    AttestationRecord
        The pack's reference, with :attr:`Outcome.NOT_ATTESTED` if no
        attestation has been written, and otherwise its outcome and the
        releaser's confirmations.

    Raises
    ------
    QcPackError
        If the directory holds no QC pack; if the attestation is not of its
        format or is for another pack; or if the pack, or a preview that it
        lists, changed after it was attested.
    """
    directory = Path(pack_directory)
    data = _pack_bytes(directory)
    attestation = _attestation_of(directory, data)
    if attestation is None:
        return AttestationRecord(_reference_of(data), Outcome.NOT_ATTESTED)
    return AttestationRecord(
        attestation.reference,
        attestation.outcome,
        attestation.intended_use_checked,
        attestation.residual_risk_accepted,
    )


def attested_pack(pack_directory: os.PathLike | str) -> tuple[Attestation, bytes]:
    """Return a QC pack's attestation and the bytes of the pack it attests.

    Both are checked as :func:`attestation_record` checks them, so the pack
    is the one that the attestation's digest binds, unchanged, with every
    preview it lists.

    Raises
    ------
    QcPackError
        If the directory holds no QC pack, or no attestation; or for any
        reason that :func:`attestation_record` gives.
    """
    directory = Path(pack_directory)
    data = _pack_bytes(directory)
    attestation = _attestation_of(directory, data)
    if attestation is None:
        raise QcPackError("the QC pack has not been attested")
    return attestation, data


def _attestation_of(directory: Path, data: bytes) -> Attestation | None:
    """Return the pack's checked attestation, or None if it has none."""
    reference = _reference_of(data)
    content = _read(directory / ATTESTATION_FILE, "the attestation")
    if content is None:
        return None
    attestation = _attestation_from(content)
    if attestation.reference != reference:
        raise QcPackError("the attestation is for another QC pack")
    if attestation.pack_digest != hashlib.sha256(
        data
    ).hexdigest() or not _previews_intact(directory, data):
        raise QcPackError("the QC pack changed after it was attested")
    return attestation


def _attestation_from(content: bytes) -> Attestation:
    """Rebuild a written attestation, so that it meets every check again."""
    try:
        document = json.loads(content.decode("ascii"))
        if isinstance(document, dict) and document.get("format") == FORMAT:
            coverage = document["coverage"]
            # An attestation written before the releaser's confirmations
            # has none, which reads as not stated.
            releaser = document.get("releaser", {})
            faces = document["faces"]
            redactions = document["redactions"]
            if (
                isinstance(coverage, dict)
                and isinstance(releaser, dict)
                and isinstance(faces, list)
                and isinstance(redactions, list)
            ):
                if set(releaser) - {"intended_use_checked", "residual_risk_accepted"}:
                    raise QcPackError("the attestation is not of its format")
                return Attestation(
                    reference=document["reference"],
                    pack_digest=document["pack_digest"],
                    outcome=Outcome(document["outcome"]),
                    coverage=Coverage(**coverage),
                    reviewer=document["reviewer"],
                    attested_at=datetime.datetime.fromisoformat(
                        document["attested_at"]
                    ),
                    intended_use_checked=releaser.get("intended_use_checked"),
                    residual_risk_accepted=releaser.get("residual_risk_accepted"),
                    faces=tuple(
                        FaceVerdict(verdict["series"], Face(verdict["face"]))
                        for verdict in faces
                    ),
                    redactions=tuple(map(_redaction_verdict_from, redactions)),
                )
    # UnicodeError and QcPackError are ValueErrors; TypeError covers wrong
    # types and Coverage's unknown or missing fields.
    except (ValueError, KeyError, TypeError):
        pass
    raise QcPackError("the attestation is not of its format")


def _redaction_verdict_from(verdict: dict) -> RedactionVerdict:
    """Rebuild a written redaction verdict; malformed input raises as
    :func:`_attestation_from` expects."""
    return RedactionVerdict(
        verdict["position"],
        Redaction(verdict["redaction"]),
        tuple(
            (
                regions["frame"],
                tuple(TextBox(*box) for box in regions["boxes"]),
            )
            for regions in verdict["regions"]
        ),
    )


def _pack_bytes(directory: Path) -> bytes:
    marker = qc_store.path_status(
        directory / qc_store.MARKER_FILE, "the QC pack could not be read"
    )
    if marker is None or not stat.S_ISREG(marker.st_mode):
        raise QcPackError("the directory holds no QC pack")
    data = _read(directory / qc_store.PACK_FILE, "the QC pack")
    if data is None:
        raise QcPackError("the directory holds no QC pack")
    return data


def _previews_intact(directory: Path, data: bytes) -> bool:
    """Whether every preview that the pack lists has the SHA-256 it records."""
    document = json.loads(data.decode("ascii"))  # _reference_of has parsed it
    previews = document.get("previews", [])
    if not isinstance(previews, list):
        return False
    for preview in previews:
        name = preview.get("file") if isinstance(preview, dict) else None
        digest = preview.get("sha256") if isinstance(preview, dict) else None
        if (
            not isinstance(name, str)
            or not _PREVIEW_FILE.fullmatch(name)
            or not isinstance(digest, str)
        ):
            return False
        # Only a regular file is read, so that a preview replaced by a link,
        # a FIFO, or a device is not followed.
        status = qc_store.path_status(
            directory / name, "a preview of the QC pack could not be read", follow=False
        )
        if status is None or not stat.S_ISREG(status.st_mode):
            return False
        content = _read(directory / name, "a preview of the QC pack")
        if content is None or hashlib.sha256(content).hexdigest() != digest:
            return False
    return True


def _read(path: Path, what: str) -> bytes | None:
    """Return a file's bytes, or None if it does not exist.

    Any other failure raises, naming ``what`` and the operating system's
    reason, but never the path.
    """
    try:
        return path.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as error:
        raise qc_store.os_error(f"{what} could not be read", error) from None


def _reference_of(data: bytes) -> str:
    try:
        document = json.loads(data.decode("ascii"))
    except ValueError:  # UnicodeError and JSONDecodeError are ValueErrors
        document = None
    reference = document.get("reference") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("format") != qc_pack.FORMAT
        or not isinstance(reference, str)
        or not _REFERENCE.fullmatch(reference)
    ):
        raise QcPackError("the QC pack is not of its format")
    return reference
