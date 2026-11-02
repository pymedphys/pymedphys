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

"""Whether a ``public-release`` run is ready for release, by its three gates.

A ``public-release`` run is marked ready only when three gates pass:
statistical disclosure control, pixel and face review, and a human QC
attestation (D-017). A run's own QC pack cannot be reviewed before the run
writes it, so, as a face or redaction review is (D-046, D-048), the evidence
is that of an earlier run of the collection: its QC pack, which a reviewer
attested, its release report, and any risk assessment recorded beside the
pack (D-053). :func:`read_readiness_review` reads them, and
:func:`readiness` decides each gate for the later run, from its own QC pack,
before the run publishes the release:

- **Statistical.** The record, if there is one, must be of this run's
  collection, policy, and reviewed lists and region rules, count the
  distinct subjects that it releases, and
  give a maximum per-subject probability within its threshold, as
  :func:`~pymedphys._dicom.deidentify.risk_assessment.statistical_gate`
  decides.
- **Pixel and face.** The reviewed pack must be attested, not rejected, and
  of this run's collection and policy, so that its previews show what this
  run writes. Every instance that the run releases in a high-risk category
  must have been listed as one there, released or held, so that the
  reviewer saw its full-resolution previews (D-015). Every instance that it
  releases that can show a face, one with pixel data or contours, must be
  in a series that the reviewer marked absent, and written with the pixel
  data and contours that the reviewed run's previews showed, as
  :meth:`~pymedphys._dicom.deidentify.face_review.FaceReview.hold_reason`
  decides under the Clean Recognizable Visual Features Option; unless the
  statistical gate passes with an assessment that covered faces
  reconstructed from the images, which then stands in for the verdicts as
  D-017's risk assessment reference.
- **Attestation.** The reviewed pack must be attested, not rejected, and of
  this run's collection and policy; its releaser must have confirmed that
  the output's residual risk was accepted; every instance that the run
  releases must have been released or held by the reviewed run, so that
  its series' previews showed it; and every string that the run retains in
  an instance that it releases must be one of the reviewed pack's retained
  strings, which the reviewer reviewed. The policy binding leaves out the
  reviewed lists and region rules, whose keyed digests differ under each
  run's key, and which the risk assessment binds on its own, so this last
  check is what holds a string that an edited list now keeps, as the pixel
  data's digests of the pixel and face gate hold pixel data that edited
  rules now write otherwise.

Each gate fails with the first of its reasons that holds, as a code and no
value, and passing one passes no other. The reviewed material is
confidential (D-016): the release report records only the pack's and the
record's opaque references and the gates' reasons. Nothing here raises with
a path or a value.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path

from . import release_report
from .face_review import FaceReview, _previews, read_face_review
from .pixel_region_rules import PixelRegionRules
from .qc_attestation import Outcome, _attestation_of, _pack_bytes, _reference_of
from .qc_pack import NO_CONTOURS_SHA256, NO_PIXELS_SHA256, Disposition, QcPack
from .qc_pack import QcPackError, pack_document
from .reasons import ReviewReason
from .reviewed_descriptors import ReviewedDescriptors
from .reviewed_roi_names import ReviewedNames
from .risk_assessment import (
    AssessmentRecord,
    RiskAssessmentError,
    _pack_collection,
    _release_report,
    collection_digest,
    policy_digest,
    read_assessment,
    statistical_gate,
)

# The dispositions of an instance that the reviewed run wrote, and so
# previewed. An identical copy of one has its source's digest already; a
# copy is not counted itself, since its group's first copy may not have
# been written.
_WRITTEN = frozenset({Disposition.RELEASED.value, Disposition.HELD_FOR_REVIEW.value})
# The face reasons in the order that the gate gives the first of them, the
# gravest first.
_FACE_REASONS = (
    ReviewReason.FACE_PRESENT,
    ReviewReason.NO_FACE_VERDICT,
    ReviewReason.OTHER_PIXEL_DATA,
    ReviewReason.OTHER_CONTOURS,
)
_NO_PIXELS = bytes.fromhex(NO_PIXELS_SHA256)
_NO_CONTOURS = bytes.fromhex(NO_CONTOURS_SHA256)
_REFERENCE = re.compile(r"A-[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclasses.dataclass(frozen=True, repr=False)
class ReadinessReview:
    """What a ``public-release`` run needs of an earlier run of its collection.

    It is confidential, since it holds the retained strings that the
    reviewed pack lists, so its ``repr`` shows only the pack's reference
    and the attestation's outcome. It holds nothing that names the
    reviewer.

    Attributes
    ----------
    reference : str
        The reviewed pack's opaque reference, ``A-`` and 32 hex digits.
    outcome : ~pymedphys._dicom.deidentify.qc_attestation.Outcome
        Its attestation's outcome, or ``NOT_ATTESTED`` without one.
    residual_risk_accepted : bool or None
        The releaser's confirmation in the attestation that the output's
        residual risk was accepted; None where not stated or not attested.
    collection_sha256 : str
        :func:`~.risk_assessment.collection_digest` of the source files that
        the pack records.
    policy_sha256 : str
        :func:`~.risk_assessment.policy_digest` of the reviewed run's
        release report.
    reviewed : frozenset of bytes
        The SHA-256 of each source file that the reviewed run released or
        held.
    high_risk : frozenset of bytes
        The SHA-256 of each source file that the pack lists in a high-risk
        category and that the reviewed run released or held.
    retained_strings : frozenset of str
        Each distinct retained string that the pack lists.
    faces : ~pymedphys._dicom.deidentify.face_review.FaceReview or None
        The reviewer's face verdicts, from
        :func:`~.face_review.read_face_review`; None unless attested.
    assessment : ~pymedphys._dicom.deidentify.risk_assessment.AssessmentRecord or None
        The risk assessment recorded beside the pack, or None without one.
    """

    reference: str
    outcome: Outcome
    residual_risk_accepted: bool | None
    collection_sha256: str
    policy_sha256: str
    reviewed: frozenset[bytes]
    high_risk: frozenset[bytes]
    retained_strings: frozenset[str]
    faces: FaceReview | None
    assessment: AssessmentRecord | None

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not _REFERENCE.fullmatch(
            self.reference
        ):
            raise QcPackError("a readiness review needs the reviewed pack's reference")
        if not isinstance(self.outcome, Outcome):
            raise QcPackError("a readiness review needs its attestation's Outcome")
        if self.residual_risk_accepted not in (None, True, False) or (
            self.outcome is Outcome.NOT_ATTESTED
            and self.residual_risk_accepted is not None
        ):
            raise QcPackError(
                "a readiness review's confirmation is true, false, or None, and "
                "None without an attestation"
            )
        for name in ("collection_sha256", "policy_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                raise QcPackError(f"a readiness review needs its {name} as a SHA-256")
        for name in ("reviewed", "high_risk"):
            digests = getattr(self, name)
            if not isinstance(digests, frozenset) or not all(
                isinstance(d, bytes) and len(d) == 32 for d in digests
            ):
                raise QcPackError(f"a readiness review's {name} are SHA-256 digests")
        if not self.high_risk <= self.reviewed:
            raise QcPackError(
                "a readiness review's high-risk sources are among those reviewed"
            )
        if not isinstance(self.retained_strings, frozenset) or not all(
            isinstance(value, str) for value in self.retained_strings
        ):
            raise QcPackError("a readiness review's retained strings are text")
        if (self.faces is not None) != (self.outcome is Outcome.ATTESTED) or not (
            self.faces is None or isinstance(self.faces, FaceReview)
        ):
            raise QcPackError(
                "a readiness review has a FaceReview exactly where it is attested"
            )
        if self.faces is not None and self.faces.reference != self.reference:
            raise QcPackError("a readiness review's verdicts are of another pack")
        if self.assessment is not None and (
            not isinstance(self.assessment, AssessmentRecord)
            or self.assessment.pack != self.reference
        ):
            raise QcPackError(
                "a readiness review's assessment is an AssessmentRecord of its pack"
            )

    def __repr__(self) -> str:
        return (
            f"ReadinessReview(reference={self.reference!r}, "
            f"outcome={self.outcome.value!r})"
        )


def read_readiness_review(
    pack_directory: os.PathLike | str, release_report_file: os.PathLike | str
) -> ReadinessReview:
    """Read what a ``public-release`` run needs of an earlier run's review.

    Parameters
    ----------
    pack_directory : path-like
        The directory of the earlier run's QC pack, which a reviewer has
        attested, or has yet to: a pack that is not attested fails the
        gates that rest on it, rather than raising.
    release_report_file : path-like
        That run's release report, the ``release-report.json`` that it
        published, which names the pack by its reference and records its
        policy.

    Returns
    -------
    ReadinessReview

    Raises
    ------
    RiskAssessmentError
        If the release report cannot be read, is not of its format, or names
        another QC pack; or if the risk assessment beside the pack cannot be
        accepted, as :func:`~.risk_assessment.read_assessment` raises.
    QcPackError
        If the directory holds no QC pack, or the pack or its attestation is
        not of its format, or is for another pack, or changed after it was
        attested, as :func:`~.qc_attestation.attestation_record` raises; or
        for any reason that :func:`~.face_review.read_face_review` gives.
    """
    directory = Path(pack_directory)
    data = _pack_bytes(directory)
    reference = _reference_of(data)
    report = _release_report(release_report_file)
    qc_review = report.get("qc_review")
    if not isinstance(qc_review, Mapping) or qc_review.get("reference") != reference:
        raise RiskAssessmentError("the release report names another QC pack")
    attestation = _attestation_of(directory, data)
    outcome = Outcome.NOT_ATTESTED if attestation is None else attestation.outcome
    faces = read_face_review(directory) if outcome is Outcome.ATTESTED else None
    assessment = read_assessment(directory)
    collection = _pack_collection(data)
    document = json.loads(data.decode("ascii"))  # _reference_of has parsed it
    reviewed, high_risk, retained = _reviewed_pack(document)
    return ReadinessReview(
        reference=reference,
        outcome=outcome,
        residual_risk_accepted=(
            None if attestation is None else attestation.residual_risk_accepted
        ),
        collection_sha256=collection,
        policy_sha256=policy_digest(report),
        reviewed=reviewed,
        high_risk=high_risk,
        retained_strings=retained,
        faces=faces,
        assessment=assessment,
    )


def readiness(
    review: ReadinessReview | None,
    pack: QcPack,
    *,
    subjects: int,
    policy_sha256: str,
    reviewed_names: ReviewedNames | None,
    reviewed_descriptors: ReviewedDescriptors | None,
    pixel_region_rules: PixelRegionRules | None,
) -> release_report.Readiness:
    """Decide a ``public-release`` run's readiness from an earlier run's review.

    Parameters
    ----------
    review : ReadinessReview or None
        From :func:`read_readiness_review`, or None where the run was given
        none, which fails every gate.
    pack : ~pymedphys._dicom.deidentify.qc_pack.QcPack
        The run's own QC pack, as it writes it.
    subjects : int
        The number of distinct subjects of the instances that the run
        releases.
    policy_sha256 : str
        :func:`~.risk_assessment.policy_digest` of the run's release report.
    reviewed_names, reviewed_descriptors : ReviewedNames or ReviewedDescriptors or None
        The reviewed lists that the run's descriptor cleaning applied, as it
        read them, or None for each that it was not given, which the
        statistical gate checks against the risk assessment's.
    pixel_region_rules : PixelRegionRules or None
        The reviewed region rules that the run's Clean Pixel Data applied,
        or None without any, which the statistical gate checks in the same
        way.

    Returns
    -------
    ~pymedphys._dicom.deidentify.release_report.Readiness
        Each gate with the first of its reasons that holds, as the module
        describes, or none where it passed.

    Raises
    ------
    TypeError
        If ``review`` is not a ReadinessReview or None, or ``pack`` is not a
        QcPack.
    RiskAssessmentError
        If ``subjects``, ``policy_sha256``, a list, or the rules are not of
        their form, as :func:`~.risk_assessment.statistical_gate` raises.
    """
    if review is not None and not isinstance(review, ReadinessReview):
        raise TypeError("review must be a ReadinessReview or None")
    if not isinstance(pack, QcPack):
        raise TypeError("pack must be a QcPack")
    collection = collection_digest(
        bytes.fromhex(entry.source_sha256)
        for entry in pack.instances
        if entry.source_sha256 is not None
    )
    record = None if review is None else review.assessment
    statistical = statistical_gate(
        record,
        collection_sha256=collection,
        policy_sha256=policy_sha256,
        reviewed_names=reviewed_names,
        reviewed_descriptors=reviewed_descriptors,
        pixel_region_rules=pixel_region_rules,
        subjects=subjects,
    )
    if review is None:
        return release_report.Readiness(
            review=None,
            assessment=None,
            statistical=statistical.reason,
            pixel_and_face=ReviewReason.NO_REVIEW,
            attestation=ReviewReason.NO_REVIEW,
        )
    bound = _bound(review, collection, policy_sha256)
    # The assessment stands in for face verdicts only where its own gate
    # passes, so that it is of this collection, policy, lists, rules, and
    # subjects, and within its threshold.
    faces_assessed = (
        statistical.passed
        and record is not None
        and record.assessment.facial_reconstruction
    )
    return release_report.Readiness(
        review=review.reference,
        assessment=statistical.assessment,
        statistical=statistical.reason,
        pixel_and_face=bound or _pixel_and_face(review, pack, faces_assessed),
        attestation=bound or _attestation(review, pack),
    )


def released_subjects(
    patients: Mapping[int, object], positions: frozenset[int] | set[int]
) -> int:
    """Return how many distinct subjects the released instances have.

    Parameters
    ----------
    patients : mapping of int to object
        Each input's subject identity by run position, such as its first
        pass record's ``patient``, which is None for an instance that names
        no patient. Those that name none count as one subject.
    positions : set of int
        The run positions of the instances that the run releases.

    Examples
    --------
    >>> released_subjects({0: "a", 1: "a", 2: "b", 3: None, 4: None}, {0, 1, 3, 4})
    2
    """
    # Instances that name no patient are one subject, as the run groups them
    # for the residual search.
    return len({patients[p] for p in positions if p in patients})


def _bound(
    review: ReadinessReview, collection: str, policy_sha256: str
) -> ReviewReason | None:
    """Why the reviewed pack does not show what this run writes, if it does not."""
    if review.outcome is Outcome.NOT_ATTESTED:
        return ReviewReason.NOT_ATTESTED
    if review.outcome is Outcome.REJECTED:
        return ReviewReason.REJECTED
    if review.collection_sha256 != collection:
        return ReviewReason.OTHER_COLLECTION
    if review.policy_sha256 != policy_sha256:
        return ReviewReason.OTHER_POLICY
    return None


def _released(pack: QcPack) -> list:
    return [e for e in pack.instances if e.disposition is Disposition.RELEASED]


def _pixel_and_face(
    review: ReadinessReview, pack: QcPack, faces_assessed: bool
) -> ReviewReason | None:
    released = {entry.position: entry for entry in _released(pack)}
    for entry in pack.pixel_risks:
        source = released.get(entry.position)
        if source is not None and _digest(source.source_sha256) not in review.high_risk:
            return ReviewReason.UNREVIEWED_HIGH_RISK
    if faces_assessed:
        return None
    faces = review.faces
    if faces is None:  # an attested review always has its verdicts
        return ReviewReason.NO_FACE_VERDICT
    # How many frames the run's own previews show of each instance, from
    # the first, which its pack records a pixel data digest only where they
    # are every frame, and of each that its dose-levels previews show,
    # which alone show an RT Dose as it could show a face.
    _, _, pictured, dosed = _previews(pack_document(pack))
    found = set()
    for position, entry in released.items():
        pixels = _digest(entry.pixel_sha256)
        contours = _digest(entry.contour_sha256)
        if pixels == _NO_PIXELS and contours == _NO_CONTOURS:
            continue  # nothing of it can show a face
        held = faces.hold_reason(
            _digest(entry.source_sha256) or b"",
            pixels,
            contours,
            pictured.get(position),
            dose=position in dosed,
        )
        if held is not None:
            found.add(ReviewReason(held.value))
    return next((reason for reason in _FACE_REASONS if reason in found), None)


def _attestation(review: ReadinessReview, pack: QcPack) -> ReviewReason | None:
    if review.residual_risk_accepted is not True:
        return ReviewReason.RESIDUAL_RISK_NOT_ACCEPTED
    released = {entry.position: entry for entry in _released(pack)}
    if any(
        _digest(entry.source_sha256) not in review.reviewed
        for entry in released.values()
    ):
        return ReviewReason.UNREVIEWED_INSTANCE
    for retained in pack.retained_strings:
        if retained.value not in review.retained_strings and any(
            position in released for position, _ in retained.places
        ):
            return ReviewReason.UNREVIEWED_RETAINED_STRING
    return None


def _digest(text: str | None) -> bytes | None:
    return None if text is None else bytes.fromhex(text)


def _reviewed_pack(
    document: dict,
) -> tuple[frozenset[bytes], frozenset[bytes], frozenset[str]]:
    """Return what a reviewed pack's document says the reviewer saw: the
    sources it released or held, those of them in a high-risk category, and
    its retained strings."""
    malformed = QcPackError("the QC pack is not of its format")
    instances = document.get("instances")
    risks = document.get("pixel_risks")
    strings = document.get("retained_strings")
    if not all(isinstance(each, list) for each in (instances, risks, strings)):
        raise malformed
    written: dict[int, bytes] = {}
    reviewed = set()
    for entry in instances:  # type: ignore[union-attr]
        if not isinstance(entry, dict):
            raise malformed
        digest, disposition = entry.get("source_sha256"), entry.get("disposition")
        if digest is None:
            continue
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise malformed
        if disposition in _WRITTEN:
            reviewed.add(bytes.fromhex(digest))
            written[entry.get("position")] = bytes.fromhex(digest)  # type: ignore[index]
    high_risk = set()
    for entry in risks:  # type: ignore[union-attr]
        if not isinstance(entry, dict):
            raise malformed
        if entry.get("position") in written:
            high_risk.add(written[entry["position"]])
    retained = set()
    for entry in strings:  # type: ignore[union-attr]
        value = entry.get("value") if isinstance(entry, dict) else None
        if not isinstance(value, str):
            raise malformed
        retained.add(value)
    return frozenset(reviewed), frozenset(high_risk), frozenset(retained)
