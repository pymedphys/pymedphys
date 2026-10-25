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

"""A reviewer's redaction verdicts, for the Clean Pixel Data Option.

A first run under the option blacks out the text that its finder finds in
each instance's Pixel Data and holds the instance for review, since the
finder can miss text. Its QC pack lists each cleaned instance's regions by
frame and previews every frame, and records the SHA-256 of each source
file. The reviewer gives a verdict on each instance that they judged, by its
run position, in the pack's attestation
(:mod:`~pymedphys._dicom.deidentify.qc_attestation`): the pack's regions
accepted, the pack's regions with the reviewer's own added to them, or the
instance rejected. A cleaned instance that the pack lists as not previewed
can have no verdict, since the reviewer has not seen its frames, unless it is
an RT Dose listed only because its dose levels are not shown. A second
run of the same files under a policy that selects the option is given that
pack (:func:`read_redaction_review`), and an attestation whose outcome is
rejected is refused. An instance whose source file has, by its SHA-256, an
accepted or revised verdict has exactly the reviewed regions blacked out,
without the finder, and satisfies the option; one with a rejected verdict is
sequestered; and any other is cleaned by the finder and held for review, as
in the first run, so a source file changed since the review no longer
matches. For compressed Pixel Data, the pack also records the SHA-256 of
the frames as decoded, which the second run's decoding must give again
before the reviewed regions are applied, since another build of a decoder
can decode the same lossy codestream to other pixels than those that the
reviewer saw.

The verdicts are read by digest, never by path or run position, so the
second run may discover the files in another order, or among others, which
have no verdict. A pack whose verdicts disagree on one source file, such as
two identical copies given different verdicts, is refused.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import types
from collections.abc import Mapping

from .qc_attestation import (
    Attestation,
    Outcome,
    Redaction,
    attested_pack,
    previewed_redactions,
)
from .qc_pack import QcPackError
from .text_detection import TextBox

_SHA256 = re.compile(r"[0-9a-f]{64}")

# Each frame with a region, by index from 0, in order, with its regions.
Regions = tuple[tuple[int, tuple[TextBox, ...]], ...]


@dataclasses.dataclass(frozen=True, repr=False)
class RedactionReview:
    """The source files of a reviewed QC pack's cleaned instances, by verdict.

    Its ``repr`` shows only the pack's reference and the counts.

    Attributes
    ----------
    reference : str
        The reviewed QC pack's opaque reference, ``A-`` and 32 hex digits,
        which the release report records.
    approved : mapping of bytes to regions
        The regions to black out in each source file whose instance the
        reviewer accepted or revised, by its SHA-256: each frame with a
        region, by index from 0, in order, with its regions; none where
        neither the finder nor the reviewer found text.
    rejected : frozenset of bytes
        The SHA-256 of each source file whose instance the reviewer
        rejected.
    decoded : mapping of bytes to bytes
        For each approved source file whose Pixel Data is compressed, by
        its SHA-256, the SHA-256 of its frames as the reviewed run decoded
        them.
    """

    reference: str
    approved: Mapping[bytes, Regions]
    rejected: frozenset[bytes]
    decoded: Mapping[bytes, bytes] = dataclasses.field(
        default_factory=lambda: types.MappingProxyType({})
    )

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not re.fullmatch(
            r"A-[0-9a-f]{32}", self.reference
        ):
            raise QcPackError("a redaction review needs the reviewed pack's reference")
        if not isinstance(self.approved, Mapping) or not isinstance(
            self.rejected, frozenset
        ):
            raise QcPackError("a redaction review's files are SHA-256 digests")
        if not isinstance(self.decoded, Mapping) or not all(
            _is_digest(d)
            for d in (*self.approved, *self.rejected, *self.decoded.values())
        ):
            raise QcPackError("a redaction review's files are SHA-256 digests")
        if not set(self.decoded) <= set(self.approved):
            raise QcPackError(
                "a redaction review records decoded frames only of approved files"
            )
        if not all(_is_regions(regions) for regions in self.approved.values()):
            raise QcPackError(
                "a redaction review's regions are frames, in order, with boxes"
            )
        if self.rejected & set(self.approved):
            raise QcPackError(
                "a redaction review cannot both approve and reject a source file"
            )
        # A read-only copy, so that the review cannot change once made.
        object.__setattr__(
            self, "approved", types.MappingProxyType(dict(self.approved))
        )
        object.__setattr__(self, "decoded", types.MappingProxyType(dict(self.decoded)))

    def __repr__(self) -> str:
        return (
            f"RedactionReview(reference={self.reference!r}, "
            f"approved={len(self.approved)}, rejected={len(self.rejected)})"
        )


def _is_digest(digest: object) -> bool:
    return isinstance(digest, bytes) and len(digest) == 32


def _is_regions(regions: object) -> bool:
    if not isinstance(regions, tuple):
        return False
    frames = []
    for entry in regions:
        if not (isinstance(entry, tuple) and len(entry) == 2):
            return False
        index, boxes = entry
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not isinstance(boxes, tuple)
            or not boxes
            or not all(isinstance(box, TextBox) for box in boxes)
        ):
            return False
        frames.append(index)
    return frames == sorted(set(frames)) and all(index >= 0 for index in frames)


def read_redaction_review(pack_directory: os.PathLike | str) -> RedactionReview:
    """Read the redaction verdicts of an attested QC pack.

    Parameters
    ----------
    pack_directory : path-like
        The directory of a first run's QC pack under the Clean Pixel Data
        Option, which a reviewer has attested with redaction verdicts.

    Returns
    -------
    RedactionReview
        Empty of files where the attestation gives no verdict. An accepted
        instance's regions are those that the pack lists for it, and a
        revised one's those and the ones that the verdict adds, in each
        frame, with the SHA-256 of its decoded frames where the pack
        records one.

    Raises
    ------
    QcPackError
        If the directory holds no QC pack, or the pack has not been
        attested, or its attestation's outcome is rejected; if either is not
        of its format, or the attestation is for another pack; if the pack
        or a preview changed after it was attested; if a verdict names an
        instance that the pack does not list as cleaned and previewed, or
        that it lists without its source's SHA-256; or if verdicts disagree
        on one source file, or on the decoded frames of one. The message
        names no path and no value.
    """
    return redaction_review_of(*attested_pack(pack_directory))


def redaction_review_of(attestation: Attestation, data: bytes) -> RedactionReview:
    """Return the redaction verdicts of an attestation of a QC pack.

    Parameters
    ----------
    attestation : ~pymedphys._dicom.deidentify.qc_attestation.Attestation
    data : bytes
        The bytes of the pack that ``attestation`` attests, as
        :func:`~pymedphys._dicom.deidentify.qc_attestation.attested_pack`
        returns them with it, so that a caller that reads the pack's other
        members reads the same bytes.

    Returns
    -------
    RedactionReview
        As :func:`read_redaction_review` returns it.

    Raises
    ------
    QcPackError
        As :func:`read_redaction_review` raises it, other than for reading
        the pack and its attestation.
    """
    if attestation.outcome is not Outcome.ATTESTED:
        raise QcPackError(
            "the QC pack's attestation rejected it, so its verdicts release nothing"
        )
    digests, cleaned = _cleaned(data)
    # The regions to black out in each source file, or None to reject it,
    # and the SHA-256 of its decoded frames, if compressed.
    decisions: dict[bytes, tuple[Regions | None, bytes | None]] = {}
    for verdict in attestation.redactions:
        if verdict.position not in cleaned or verdict.position not in digests:
            raise QcPackError(
                "a redaction verdict names an instance that the QC pack does not "
                "list as cleaned and previewed"
            )
        digest = digests[verdict.position]
        regions, decoded = cleaned[verdict.position]
        if verdict.redaction is Redaction.REJECTED:
            decided: Regions | None = None
        elif verdict.redaction is Redaction.ACCEPTED:
            decided = regions
        else:
            decided = _added(regions, verdict.regions)
        if decisions.setdefault(digest, (decided, decoded)) != (decided, decoded):
            raise QcPackError(
                "the redaction verdicts disagree on a source file that the QC "
                "pack lists more than once"
            )
    approved = {
        digest: (regions, decoded)
        for digest, (regions, decoded) in decisions.items()
        if regions is not None
    }
    return RedactionReview(
        attestation.reference,
        {digest: regions for digest, (regions, _) in approved.items()},
        frozenset(
            digest for digest, (regions, _) in decisions.items() if regions is None
        ),
        {
            digest: decoded
            for digest, (_, decoded) in approved.items()
            if decoded is not None
        },
    )


def _added(regions: Regions, more: Regions) -> Regions:
    """Return ``regions`` with ``more`` added, each frame's boxes sorted and
    distinct."""
    by_frame: dict[int, set[TextBox]] = {}
    for index, boxes in (*regions, *more):
        by_frame.setdefault(index, set()).update(boxes)
    return tuple((index, tuple(sorted(by_frame[index]))) for index in sorted(by_frame))


def _cleaned(
    data: bytes,
) -> tuple[dict[int, bytes], dict[int, tuple[Regions, bytes | None]]]:
    """Return each instance's source digest, and the regions of each cleaned
    instance that the pack previewed, with the SHA-256 of its decoded
    frames where the pack records one, by run position."""
    malformed = QcPackError("the QC pack is not of its format")
    document = json.loads(data.decode("ascii"))  # attested_pack has parsed it
    instances = document.get("instances")
    redactions = document.get("redactions")
    if not isinstance(instances, list) or not isinstance(redactions, list):
        raise malformed
    digests: dict[int, bytes] = {}
    for instance in instances:
        if not isinstance(instance, dict):
            raise malformed
        position, digest = instance.get("position"), instance.get("source_sha256")
        if isinstance(position, int) and isinstance(digest, str):
            if not _SHA256.fullmatch(digest):
                raise malformed
            digests[position] = bytes.fromhex(digest)
    cleaned: dict[int, Regions] = {}
    decoded: dict[int, bytes | None] = {}
    try:
        for entry in redactions:
            cleaned[entry["position"]] = tuple(
                (
                    regions["frame"],
                    tuple(TextBox(*box) for box in regions["boxes"]),
                )
                for regions in entry["regions"]
            )
            sha256 = entry["decoded_sha256"]
            if sha256 is not None and not (
                isinstance(sha256, str) and _SHA256.fullmatch(sha256)
            ):
                raise malformed
            decoded[entry["position"]] = (
                None if sha256 is None else bytes.fromhex(sha256)
            )
    # A pack that attested_pack read is of its format, but one written by
    # another tool could still hold anything.
    except (KeyError, TypeError, ValueError):
        raise malformed from None
    if not all(_is_regions(regions) for regions in cleaned.values()):
        raise malformed
    previewed = previewed_redactions(data)
    return digests, {
        position: (regions, decoded[position])
        for position, regions in cleaned.items()
        if position in previewed
    }
