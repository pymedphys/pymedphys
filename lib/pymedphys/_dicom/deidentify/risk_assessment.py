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

"""The record of an external statistical risk assessment, for the statistical gate.

A ``public-release`` run is ready for release only when its statistical
gate passes, with its pixel and face review and its human QC attestation
(D-017). The engine has no estimator of re-identification risk: until one
is selected and validated, the evidence is a documented external
assessment, which this module records and checks (D-053).

An assessor who has assessed a run's collection records the assessment with
:func:`record_assessment`, which writes :data:`ASSESSMENT_FILE`, labelled
with its format, :data:`FORMAT`, into the directory of that run's QC pack
(:mod:`~pymedphys._dicom.deidentify.qc_store`), beside any attestation
(:mod:`~pymedphys._dicom.deidentify.qc_attestation`). The record holds what
the assessor states (:class:`Assessment`): the model and its implementation,
each with its version; the attacker's assumed knowledge, including whether
they know who is in the collection; the reference population and its
sampling, or why the assessment is within the release cohort; the matching
variables, and how characteristics derivable from the pixel data were
considered; the generalisation, the handling of missing data, the
uncertainty, and the exclusions; how linked longitudinal records and earlier
linked releases were accounted for; whether keeping machine identity would
raise the risk above the threshold; whether faces reconstructed from the
images were among the channels assessed; the number of distinct subjects
assessed; the threshold, 0.09 or 0.05; the maximum per-subject
re-identification probability; and who assessed it, and when. Every one is
required, and no default stands in for any of them.

It also binds the assessment, as :class:`AssessmentRecord`, to what was
assessed: to the QC pack, by its reference and the SHA-256 of its file; to
the collection, by :func:`collection_digest` of the SHA-256 of each source
file that the pack records; to the policy, by :func:`policy_digest` of the
run's release report; and to the reviewed ROI names and descriptors lists
that descriptor cleaning applied, and the reviewed region rules that Clean
Pixel Data applied, by :func:`lists_digest` under a random salt, both of
which the run recorded in its pack (:func:`bind_lists`) and the record
copies, so that the lists and rules bound are those the run applied, and
never any that whoever records the assessment supplies. A later run of the
same files under the same policy, lists, and rules, given the pack, finds
the same digests, and any change to any of them requires a new assessment.
The policy digest covers the report's policy and every input of the method
digest except the keyed digests of the reviewed lists and region rules,
which differ under each run's key; the lists' own digest binds them
instead. The engine's
files and the text finder's runtime are inputs of the method digest, so a
new version of PyMedPhys, or of a library that the text finder names, needs
a new assessment too.

:func:`statistical_gate` decides the gate for a run from a record, or from
none, as a reason code and no value: it fails without a record, for another
collection, policy, or lists or rules, for a count of subjects other than the run's,
or for a maximum probability above the threshold, and passes otherwise.
The threshold is the one that the assessment states: nothing yet selects
the stricter one for a collection, so a reviewer of the record checks that
it applied the threshold that the collection's sensitivity calls for.
Passing it passes neither of the other gates. A ``public-release`` run
reports it in its release report's readiness, with the other two
(:mod:`~pymedphys._dicom.deidentify.readiness`).

The record is confidential with the pack, since it can describe the cohort
and names the assessor. Only its opaque reference, ``R-`` and 32 hex
digits, which is random and reveals nothing of it, and the gate's outcome
are for a release report (D-016). Nothing here raises with a path or a
value from the record.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import hmac
import json
import math
import os
import re
import secrets
from collections.abc import Iterable, Mapping
from pathlib import Path

from . import qc_store, release_report
from .qc_attestation import _pack_bytes, _read, _reference_of
from .pixel_region_rules import PixelRegionRules
from .qc_pack import Disposition, ListsDigest, QcPackError
from .reviewed_descriptors import ReviewedDescriptors
from .reviewed_roi_names import ReviewedNames

# The statistical gate's reasons, which the release report names, are kept
# with the engine's other reason codes, since this module imports the report.
from .reasons import StatisticalReason

# The format of the record. A change to its fields takes a new label.
FORMAT = "pymedphys-deid-risk-assessment/1"
ASSESSMENT_FILE = "risk-assessment.json"
# The thresholds of the maximum per-subject re-identification probability
# that a public release may accept: the default, and the stricter one for
# more sensitive collections (D-017).
DEFAULT_THRESHOLD = 0.09
STRICT_THRESHOLD = 0.05
THRESHOLDS = (DEFAULT_THRESHOLD, STRICT_THRESHOLD)
# The method components that are keyed by the run's key, so differ in each
# run, and that the policy digest leaves out: the method digest, which is
# computed from them, and the digests of the reviewed lists and region
# rules, which the lists' own digest replaces.
_KEYED = (
    "method_digest",
    "reviewed_roi_names",
    "reviewed_descriptors",
    "pixel_region_rules",
)
# How many random bytes salt the lists' digest.
_SALT_BYTES = 32

_REFERENCE = re.compile(r"R-[0-9a-f]{32}")
_PACK_REFERENCE = re.compile(r"A-[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class RiskAssessmentError(QcPackError):
    """A risk assessment record that cannot be accepted.

    The message names the field or check that failed, never a value or a
    path.
    """


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_texts(what: str, **texts: object) -> None:
    for name, value in texts.items():
        if not _text(value):
            raise RiskAssessmentError(f"{what} needs its {name} as text")


@dataclasses.dataclass(frozen=True)
class Model:
    """The model that estimated the risk, and its implementation.

    Attributes
    ----------
    name, version : str
        The model, such as a named population uniqueness model, and its
        version.
    implementation, implementation_version : str
        The software that computed it, and its version.
    """

    name: str
    version: str
    implementation: str
    implementation_version: str

    def __post_init__(self) -> None:
        _check_texts("the model", **dataclasses.asdict(self))


@dataclasses.dataclass(frozen=True)
class Attacker:
    """The attacker that the assessment assumes.

    Attributes
    ----------
    knowledge : str
        What the attacker is assumed to know, and from which sources.
    membership_known : bool
        Whether the attacker is assumed to know who is in the collection,
        which a sample-based ``1/k`` calculation needs, unless it uses an
        equivalence-class model (D-017).
    """

    knowledge: str
    membership_known: bool

    def __post_init__(self) -> None:
        _check_texts("the attacker", knowledge=self.knowledge)
        if not isinstance(self.membership_known, bool):
            raise RiskAssessmentError(
                "the attacker needs whether membership is known, true or false"
            )


@dataclasses.dataclass(frozen=True)
class Population:
    """Whom the subjects were compared with.

    Either the reference population and its sampling assumptions, or why the
    assessment is within the release cohort, and never both.

    Attributes
    ----------
    reference, sampling : str or None
        The reference population, and how the collection was sampled from
        it.
    in_cohort : str or None
        Why the assessment is within the release cohort.
    """

    reference: str | None = None
    sampling: str | None = None
    in_cohort: str | None = None

    def __post_init__(self) -> None:
        if self.in_cohort is None:
            _check_texts(
                "the population", reference=self.reference, sampling=self.sampling
            )
        elif self.reference is not None or self.sampling is not None:
            raise RiskAssessmentError(
                "the population is a reference population with its sampling, or "
                "the release cohort, not both"
            )
        else:
            _check_texts("the population", in_cohort=self.in_cohort)


@dataclasses.dataclass(frozen=True, repr=False)
class Assessment:
    """What the assessor states of an external risk assessment (D-017).

    Its ``repr`` shows only the threshold and the outcome.

    Attributes
    ----------
    model : Model
    attacker : Attacker
    population : Population
    matching_variables : tuple of str
        The variables matched on, each once, at least one, including any
        derived from the pixel data.
    pixel_derived : str
        How characteristics that can be derived from the pixel data, such as
        body habitus or implants, were considered.
    generalisation, missing_data, uncertainty, exclusions : str
        How values were generalised, how missing data were handled, the
        uncertainty of the estimate, and what was excluded and why.
    linked_records, earlier_releases : str
        How linked longitudinal records, and earlier releases that can be
        linked to this one, were accounted for.
    device_identity : str
        Whether keeping machine identity, such as Station Name and Device
        Serial Number, would raise the risk above the threshold, which
        shows whoever reviews the record whether the policy's omission of
        it was needed.
    facial_reconstruction : bool
        Whether re-identification from faces reconstructed from the images
        was among the channels assessed, so that the assessment may stand
        in for face review (D-017).
    subjects : int
        The number of distinct subjects assessed, not of images, frames, or
        visits; at least 1.
    threshold : float
        :data:`DEFAULT_THRESHOLD` or :data:`STRICT_THRESHOLD`.
    maximum_risk : float
        The maximum per-subject re-identification probability, from 0 to 1.
    assessor : str
        Who assessed it, as they name themselves.
    assessed_at : datetime.datetime
        When, in UTC.
    """

    model: Model
    attacker: Attacker
    population: Population
    matching_variables: tuple[str, ...]
    pixel_derived: str
    generalisation: str
    missing_data: str
    uncertainty: str
    exclusions: str
    linked_records: str
    earlier_releases: str
    device_identity: str
    facial_reconstruction: bool
    subjects: int
    threshold: float
    maximum_risk: float
    assessor: str
    assessed_at: datetime.datetime

    def __post_init__(self) -> None:
        for name, kind in (
            ("model", Model),
            ("attacker", Attacker),
            ("population", Population),
        ):
            if not isinstance(getattr(self, name), kind):
                raise RiskAssessmentError(f"the assessment needs its {name}")
        variables = self.matching_variables
        if (
            not isinstance(variables, tuple)
            or not variables
            or not all(_text(variable) for variable in variables)
        ):
            raise RiskAssessmentError(
                "the assessment needs its matching variables, at least one, as text"
            )
        if len({variable.strip().casefold() for variable in variables}) != len(
            variables
        ):
            raise RiskAssessmentError(
                "the assessment lists each matching variable once"
            )
        _check_texts(
            "the assessment",
            pixel_derived=self.pixel_derived,
            generalisation=self.generalisation,
            missing_data=self.missing_data,
            uncertainty=self.uncertainty,
            exclusions=self.exclusions,
            linked_records=self.linked_records,
            earlier_releases=self.earlier_releases,
            device_identity=self.device_identity,
            assessor=self.assessor,
        )
        if not isinstance(self.facial_reconstruction, bool):
            raise RiskAssessmentError(
                "the assessment needs whether facial reconstruction was assessed, "
                "true or false"
            )
        if (
            not isinstance(self.subjects, int)
            or isinstance(self.subjects, bool)
            or self.subjects < 1
        ):
            raise RiskAssessmentError(
                "the assessment needs its number of subjects, a whole number of at "
                "least 1"
            )
        if not _is_number(self.threshold) or self.threshold not in THRESHOLDS:
            raise RiskAssessmentError("the assessment's threshold is 0.09 or 0.05")
        if not _is_number(self.maximum_risk) or not 0 <= self.maximum_risk <= 1:
            raise RiskAssessmentError(
                "the assessment needs its maximum per-subject probability, from 0 to 1"
            )
        if not isinstance(
            self.assessed_at, datetime.datetime
        ) or self.assessed_at.utcoffset() != datetime.timedelta(0):
            raise RiskAssessmentError("the assessment needs its time in UTC")
        if self.assessed_at > datetime.datetime.now(datetime.timezone.utc):
            raise RiskAssessmentError("the assessment's time is in the future")

    @property
    def within_threshold(self) -> bool:
        """Whether the maximum probability is at or below the threshold."""
        return self.maximum_risk <= self.threshold

    def __repr__(self) -> str:
        return (
            f"Assessment(threshold={self.threshold!r}, "
            f"within_threshold={self.within_threshold!r})"
        )


def _is_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # an int too large for a float
        return False


@dataclasses.dataclass(frozen=True, repr=False)
class AssessmentRecord:
    """An assessment, bound to the QC pack, collection, and policy assessed.

    Its ``repr`` shows only its reference.

    Attributes
    ----------
    reference : str
        The record's opaque reference, ``R-`` and 32 hex digits, which a
        release report records.
    pack : str
        The QC pack's reference, ``A-`` and 32 hex digits.
    pack_digest : str
        The SHA-256 of the pack's file.
    collection_sha256 : str
        :func:`collection_digest` of the source files that the pack records.
    policy_sha256 : str
        :func:`policy_digest` of the release report of the pack's run.
    lists_salt : str
        The random salt of the lists' digest, 64 hex digits, as the pack
        records it.
    lists_sha256 : str
        :func:`lists_digest` of the reviewed lists and region rules that
        the pack's run applied, under ``lists_salt``, as the pack records
        it.
    assessment : Assessment
    """

    reference: str
    pack: str
    pack_digest: str
    collection_sha256: str
    policy_sha256: str
    lists_salt: str
    lists_sha256: str
    assessment: Assessment

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not _REFERENCE.fullmatch(
            self.reference
        ):
            raise RiskAssessmentError("a risk assessment record needs its reference")
        if not isinstance(self.pack, str) or not _PACK_REFERENCE.fullmatch(self.pack):
            raise RiskAssessmentError(
                "a risk assessment record needs the QC pack's reference"
            )
        for name in (
            "pack_digest",
            "collection_sha256",
            "policy_sha256",
            "lists_salt",
            "lists_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                raise RiskAssessmentError(
                    f"a risk assessment record needs its {name} as a SHA-256"
                )
        if not isinstance(self.assessment, Assessment):
            raise RiskAssessmentError("a risk assessment record needs its Assessment")

    def __repr__(self) -> str:
        return f"AssessmentRecord(reference={self.reference!r})"


@dataclasses.dataclass(frozen=True)
class StatisticalGate:
    """The statistical gate of a run, as a release report records it.

    Attributes
    ----------
    assessment : str or None
        The reference of the record that the run was given, or None without
        one.
    reason : StatisticalReason or None
        Why the gate failed, or None where it passed.
    """

    assessment: str | None
    reason: StatisticalReason | None

    def __post_init__(self) -> None:
        if self.assessment is not None and not (
            isinstance(self.assessment, str) and _REFERENCE.fullmatch(self.assessment)
        ):
            raise RiskAssessmentError(
                "the statistical gate names a record by its reference"
            )
        if self.reason is not None and not isinstance(self.reason, StatisticalReason):
            raise RiskAssessmentError(
                "the statistical gate's reason must be a StatisticalReason"
            )
        if (self.assessment is None) != (
            self.reason is StatisticalReason.NO_ASSESSMENT
        ):
            raise RiskAssessmentError(
                "the statistical gate fails for no assessment exactly where it was "
                "given none"
            )

    @property
    def passed(self) -> bool:
        """Whether the gate passed."""
        return self.reason is None


def new_reference() -> str:
    """Return a new opaque reference for a record, ``R-`` and 32 hex digits.

    The reference is random, so it reveals nothing of the record.

    Examples
    --------
    >>> reference = new_reference()
    >>> reference[:2], len(reference)
    ('R-', 34)
    """
    return "R-" + secrets.token_hex(16)


def collection_digest(digests: Iterable[bytes]) -> str:
    """Return the digest of a collection, from the SHA-256 of each source file.

    It is the SHA-256 of the files' digests, sorted and joined, so that it
    depends on which files a run read, and how many copies of each, but not
    on their paths or the order in which it found them.

    Raises
    ------
    RiskAssessmentError
        If a digest is not 32 bytes.

    Examples
    --------
    >>> a, b = bytes(32), bytes(range(32))
    >>> collection_digest([a, b]) == collection_digest([b, a])
    True
    >>> collection_digest([a, b]) == collection_digest([a, b, b])
    False
    """
    digests = list(digests)
    if not all(isinstance(digest, bytes) and len(digest) == 32 for digest in digests):
        raise RiskAssessmentError("a collection is digested from SHA-256 digests")
    return hashlib.sha256(b"".join(sorted(digests))).hexdigest()


def policy_digest(report: Mapping[str, object]) -> str:
    """Return the digest of the policy and method that a release report records.

    It is the SHA-256 of the canonical JSON of the report's ``policy``
    section and of its ``method`` section without the method digest and the
    keyed digests of the reviewed lists and region rules, which differ under
    each run's key and which :func:`lists_digest` binds instead. The other
    components of
    the method digest stay, so another engine, policy, vocabulary, text
    finder, or list of safe private rules gives another digest.

    Parameters
    ----------
    report : mapping
        A release report as JSON values, as
        :func:`~pymedphys._dicom.deidentify.release_report.report_document`
        gives it.

    Raises
    ------
    RiskAssessmentError
        If the report has no ``policy`` and ``method`` sections of its
        format.
    """
    policy = report.get("policy") if isinstance(report, Mapping) else None
    method = report.get("method") if isinstance(report, Mapping) else None
    if (
        not isinstance(policy, Mapping)
        or not isinstance(method, Mapping)
        or not all(name in method for name in _KEYED)
    ):
        raise RiskAssessmentError("the release report is not of its format")
    bound = {
        "policy": dict(policy),
        "method": {name: value for name, value in method.items() if name not in _KEYED},
    }
    try:
        text = json.dumps(
            bound, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
    except (TypeError, ValueError):
        raise RiskAssessmentError("the release report is not of its format") from None
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def new_salt() -> str:
    """Return a new random salt for :func:`lists_digest`, as 64 hex digits."""
    return secrets.token_hex(_SALT_BYTES)


def bind_lists(
    reviewed_names: ReviewedNames | None,
    reviewed_descriptors: ReviewedDescriptors | None,
    pixel_region_rules: PixelRegionRules | None,
) -> ListsDigest:
    """Return the digest of a run's reviewed lists under a new salt, for its pack.

    A run records it in its QC pack, from which :func:`record_assessment`
    takes it, so that a record binds the lists and rules that the run
    applied.

    Parameters
    ----------
    reviewed_names : ReviewedNames or None
    reviewed_descriptors : ReviewedDescriptors or None
        The lists that the run's descriptor cleaning applied, as it read
        them, or None for each that it was not given.
    pixel_region_rules : PixelRegionRules or None
        The reviewed region rules that the run's Clean Pixel Data applied,
        as the version that it applied, or None without any.

    Raises
    ------
    TypeError
        If a list or the rules are not of their type or None.

    Examples
    --------
    >>> bound = bind_lists(None, None, None)
    >>> bound.sha256 == lists_digest(bound.salt, None, None, None)
    True
    """
    salt = new_salt()
    return ListsDigest(
        salt,
        lists_digest(salt, reviewed_names, reviewed_descriptors, pixel_region_rules),
    )


def lists_digest(
    salt: str,
    reviewed_names: ReviewedNames | None,
    reviewed_descriptors: ReviewedDescriptors | None,
    pixel_region_rules: PixelRegionRules | None,
) -> str:
    """Return the digest of the reviewed lists and region rules that a run applied.

    It is the HMAC-SHA-256, under ``salt``, of the canonical JSON of the
    SHA-256 of the canonical form of each list that descriptor cleaning
    applied and of the region rules that Clean Pixel Data applied
    (:meth:`~.reviewed_roi_names.ReviewedNames.canonical_bytes`,
    :meth:`~.reviewed_descriptors.ReviewedDescriptors.canonical_bytes`,
    :meth:`~.pixel_region_rules.PixelRegionRules.canonical_bytes`), in that
    order, or of None for each not given, as without Clean Descriptors or
    without rules. Any change to a decision or a name in either list, or to
    a rule's key or regions, gives another digest, and an empty list or
    store differs from none. The lists hold source names and values, and
    the rules manufacturers' and model names, so their digest is salted, and
    kept only in the confidential pack and record.

    Parameters
    ----------
    salt : str
        64 hex digits, from :func:`new_salt`, a pack's reviewed lists, or a
        record's ``lists_salt``.
    reviewed_names : ReviewedNames or None
    reviewed_descriptors : ReviewedDescriptors or None
    pixel_region_rules : PixelRegionRules or None

    Raises
    ------
    RiskAssessmentError
        If the salt is not 64 hex digits.
    TypeError
        If a list or the rules are not of their type or None.
    """
    if not isinstance(salt, str) or not _SHA256.fullmatch(salt):
        raise RiskAssessmentError("the lists' digest needs a salt of 64 hex digits")
    if reviewed_names is not None and not isinstance(reviewed_names, ReviewedNames):
        raise TypeError("reviewed_names must be ReviewedNames or None")
    if reviewed_descriptors is not None and not isinstance(
        reviewed_descriptors, ReviewedDescriptors
    ):
        raise TypeError("reviewed_descriptors must be ReviewedDescriptors or None")
    if pixel_region_rules is not None and not isinstance(
        pixel_region_rules, PixelRegionRules
    ):
        raise TypeError("pixel_region_rules must be PixelRegionRules or None")
    digests = [
        None if each is None else hashlib.sha256(each.canonical_bytes()).hexdigest()
        for each in (reviewed_names, reviewed_descriptors, pixel_region_rules)
    ]
    text = json.dumps(digests, separators=(",", ":"))
    return hmac.new(
        bytes.fromhex(salt), text.encode("ascii"), hashlib.sha256
    ).hexdigest()


def assessment_document(record: AssessmentRecord) -> dict:
    """Return a record as JSON values, labelled with :data:`FORMAT`."""
    if not isinstance(record, AssessmentRecord):
        raise TypeError("record must be an AssessmentRecord")
    assessment = record.assessment
    return {
        "format": FORMAT,
        "reference": record.reference,
        "pack": record.pack,
        "pack_digest": record.pack_digest,
        "collection_sha256": record.collection_sha256,
        "policy_sha256": record.policy_sha256,
        "lists_salt": record.lists_salt,
        "lists_sha256": record.lists_sha256,
        "model": dataclasses.asdict(assessment.model),
        "attacker": dataclasses.asdict(assessment.attacker),
        "population": dataclasses.asdict(assessment.population),
        "matching_variables": list(assessment.matching_variables),
        "pixel_derived": assessment.pixel_derived,
        "generalisation": assessment.generalisation,
        "missing_data": assessment.missing_data,
        "uncertainty": assessment.uncertainty,
        "exclusions": assessment.exclusions,
        "linked_records": assessment.linked_records,
        "earlier_releases": assessment.earlier_releases,
        "device_identity": assessment.device_identity,
        "facial_reconstruction": assessment.facial_reconstruction,
        "subjects": assessment.subjects,
        "threshold": assessment.threshold,
        "maximum_risk": assessment.maximum_risk,
        "assessor": assessment.assessor,
        "assessed_at": assessment.assessed_at.isoformat(),
    }


def record_assessment(
    pack_directory: os.PathLike | str,
    release_report_file: os.PathLike | str,
    assessment: Assessment,
) -> AssessmentRecord:
    """Record an external risk assessment beside the QC pack of the run assessed.

    Parameters
    ----------
    pack_directory : path-like
        The directory that :func:`~.qc_store.write_qc_pack` wrote for the run
        whose collection was assessed.
    release_report_file : path-like
        That run's release report, the ``release-report.json`` that it
        published, which names the pack by its reference.
    assessment : Assessment
        What the assessor states.

    Returns
    -------
    AssessmentRecord
        Bound to the pack, the collection that it records, the policy that
        the report records, and the reviewed lists' digest that the pack
        records, with a new reference.

    Raises
    ------
    RiskAssessmentError
        If the release report is not of its format, or names another QC
        pack; if the pack records no source file, or a released, duplicate,
        or held instance without its source file's SHA-256; if it records
        no digest of the reviewed lists that its run applied; or if the
        pack already has a risk assessment, since a record is never
        overwritten, and a change requires a new assessment.
    QcPackError
        If the directory holds no QC pack, the pack is not of its format, or
        the release report cannot be read.
    """
    if not isinstance(assessment, Assessment):
        raise TypeError("assessment must be an Assessment")
    directory = Path(pack_directory)
    data = _pack_bytes(directory)
    reference = _reference_of(data)
    report = _release_report(release_report_file)
    qc_review = report.get("qc_review")
    if not isinstance(qc_review, Mapping) or qc_review.get("reference") != reference:
        raise RiskAssessmentError("the release report names another QC pack")
    lists = _pack_lists(data)
    if lists is None:
        raise RiskAssessmentError(
            "the QC pack records no digest of the reviewed lists that its run applied"
        )
    record = AssessmentRecord(
        reference=new_reference(),
        pack=reference,
        pack_digest=hashlib.sha256(data).hexdigest(),
        collection_sha256=_pack_collection(data),
        policy_sha256=policy_digest(report),
        lists_salt=lists.salt,
        lists_sha256=lists.sha256,
        assessment=assessment,
    )
    text = json.dumps(assessment_document(record), indent=2, ensure_ascii=True)
    try:
        qc_store.write_new(directory / ASSESSMENT_FILE, text + "\n")
    except FileExistsError:
        raise RiskAssessmentError("the QC pack already has a risk assessment") from None
    except OSError as error:
        raise qc_store.os_error(
            "the risk assessment could not be written", error
        ) from None
    return record


def read_assessment(pack_directory: os.PathLike | str) -> AssessmentRecord | None:
    """Read the risk assessment recorded beside a QC pack.

    Parameters
    ----------
    pack_directory : path-like
        The directory that :func:`~.qc_store.write_qc_pack` wrote.

    Returns
    -------
    AssessmentRecord or None
        None if no assessment has been recorded.

    Raises
    ------
    RiskAssessmentError
        If the record is not of its format, is for another pack, or does not
        match the pack, which has changed since it was recorded, or binds
        other reviewed lists than those that the pack records.
    QcPackError
        If the directory holds no QC pack, or the pack is not of its format.
    """
    directory = Path(pack_directory)
    data = _pack_bytes(directory)
    reference = _reference_of(data)
    content = _read(directory / ASSESSMENT_FILE, "the risk assessment")
    if content is None:
        return None
    record = _record_from(content)
    if record.pack != reference:
        raise RiskAssessmentError("the risk assessment is for another QC pack")
    if record.pack_digest != hashlib.sha256(
        data
    ).hexdigest() or record.collection_sha256 != _pack_collection(data):
        raise RiskAssessmentError("the QC pack changed after it was assessed")
    lists = _pack_lists(data)
    if (
        lists is None
        or record.lists_salt != lists.salt
        or not hmac.compare_digest(record.lists_sha256, lists.sha256)
    ):
        raise RiskAssessmentError(
            "the risk assessment binds other reviewed lists than the QC pack records"
        )
    return record


def statistical_gate(
    record: AssessmentRecord | None,
    *,
    collection_sha256: str,
    policy_sha256: str,
    reviewed_names: ReviewedNames | None,
    reviewed_descriptors: ReviewedDescriptors | None,
    pixel_region_rules: PixelRegionRules | None,
    subjects: int,
) -> StatisticalGate:
    """Decide a run's statistical gate from a risk assessment record.

    Parameters
    ----------
    record : AssessmentRecord or None
        From :func:`read_assessment`, or None without one.
    collection_sha256 : str
        :func:`collection_digest` of the SHA-256 of each source file that
        the run read.
    policy_sha256 : str
        :func:`policy_digest` of the run's release report.
    reviewed_names, reviewed_descriptors : ReviewedNames or ReviewedDescriptors or None
        The reviewed lists that the run's descriptor cleaning applied, as
        it read them, or None for each that it was not given.
    pixel_region_rules : PixelRegionRules or None
        The reviewed region rules that the run's Clean Pixel Data applied,
        or None without any.
    subjects : int
        The number of distinct subjects of the instances that the run
        releases.

    Returns
    -------
    StatisticalGate
        Failed for the first of these that holds: no record; another
        collection; another policy; other lists or rules; fewer, or more, subjects
        than the run releases; a maximum probability above the threshold.
        Passed otherwise.
    """
    for name, value in (
        ("collection_sha256", collection_sha256),
        ("policy_sha256", policy_sha256),
    ):
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise RiskAssessmentError(f"the run's {name} must be a SHA-256")
    if not isinstance(subjects, int) or isinstance(subjects, bool) or subjects < 0:
        raise RiskAssessmentError("the run's subjects must be a whole number")
    # Checks the lists' and rules' types, whether or not a record was given.
    applied = (reviewed_names, reviewed_descriptors, pixel_region_rules)
    lists_digest(new_salt(), *applied)
    if record is None:
        return StatisticalGate(None, StatisticalReason.NO_ASSESSMENT)
    if not isinstance(record, AssessmentRecord):
        raise TypeError("record must be an AssessmentRecord or None")
    assessment = record.assessment
    reason = None
    if record.collection_sha256 != collection_sha256:
        reason = StatisticalReason.OTHER_COLLECTION
    elif record.policy_sha256 != policy_sha256:
        reason = StatisticalReason.OTHER_POLICY
    elif not hmac.compare_digest(
        record.lists_sha256,
        lists_digest(record.lists_salt, *applied),
    ):
        reason = StatisticalReason.OTHER_LISTS
    elif assessment.subjects < subjects:
        reason = StatisticalReason.FEWER_SUBJECTS
    elif assessment.subjects > subjects:
        reason = StatisticalReason.MORE_SUBJECTS
    elif not assessment.within_threshold:
        reason = StatisticalReason.ABOVE_THRESHOLD
    return StatisticalGate(record.reference, reason)


def _release_report(path: os.PathLike | str) -> Mapping[str, object]:
    """Return a release report's JSON values, after checking its format."""
    try:
        content = Path(path).read_bytes()
    except OSError as error:
        raise qc_store.os_error("the release report could not be read", error) from None
    try:
        report = json.loads(content.decode("utf-8"))
    except ValueError:  # UnicodeError and JSONDecodeError are ValueErrors
        report = None
    if not isinstance(report, dict) or report.get("format") != release_report.FORMAT:
        raise RiskAssessmentError("the release report is not of its format")
    return report


def _pack_lists(data: bytes) -> ListsDigest | None:
    """Return the digest of the reviewed lists that a pack records, if any."""
    document = json.loads(data.decode("ascii"))  # _reference_of has parsed it
    lists = document.get("reviewed_lists")
    if lists is None:
        return None
    if not isinstance(lists, dict) or set(lists) != {"salt", "sha256"}:
        raise QcPackError("the QC pack is not of its format")
    try:
        return ListsDigest(lists["salt"], lists["sha256"])
    except QcPackError:
        raise QcPackError("the QC pack is not of its format") from None


def _pack_collection(data: bytes) -> str:
    """Return the collection digest of the source files that a pack records."""
    document = json.loads(data.decode("ascii"))  # _reference_of has parsed it
    instances = document.get("instances")
    if not isinstance(instances, list):
        raise QcPackError("the QC pack is not of its format")
    digests = []
    for entry in instances:
        if (
            not isinstance(entry, dict)
            or "source_sha256" not in entry
            or entry.get("disposition") not in _DISPOSITIONS
        ):
            raise QcPackError("the QC pack is not of its format")
        digest = entry["source_sha256"]
        if digest is None:
            if entry["disposition"] in _REACHING:
                # Its source is unbound, so no collection could be bound.
                raise RiskAssessmentError(
                    "the QC pack has an instance that reaches a recipient "
                    "without its source's SHA-256"
                )
            # A file that the run could not read, or did not list as a
            # regular file, has none, and is in no run's collection digest.
            continue
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise QcPackError("the QC pack is not of its format")
        digests.append(bytes.fromhex(digest))
    if not digests:
        raise RiskAssessmentError("the QC pack binds no source file")
    return collection_digest(digests)


_DISPOSITIONS = frozenset(member.value for member in Disposition)
# Released, a duplicate of a released input, or held until a reviewer decides.
_REACHING = frozenset(
    member.value
    for member in (
        Disposition.RELEASED,
        Disposition.DUPLICATE,
        Disposition.HELD_FOR_REVIEW,
    )
)


def _unique_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Return an object's members, refusing one named twice."""
    document = dict(pairs)
    if len(document) != len(pairs):
        raise RiskAssessmentError("the risk assessment names a member twice")
    return document


def _record_from(content: bytes) -> AssessmentRecord:
    """Rebuild a written record, so that it meets every check again."""
    try:
        document = json.loads(
            content.decode("ascii"), object_pairs_hook=_unique_members
        )
        if (
            isinstance(document, dict)
            and document.get("format") == FORMAT
            and set(document) == set(_FIELDS)
            # A string would read as a tuple of its characters.
            and isinstance(document["matching_variables"], list)
        ):
            return AssessmentRecord(
                reference=document["reference"],
                pack=document["pack"],
                pack_digest=document["pack_digest"],
                collection_sha256=document["collection_sha256"],
                policy_sha256=document["policy_sha256"],
                lists_salt=document["lists_salt"],
                lists_sha256=document["lists_sha256"],
                assessment=Assessment(
                    model=Model(**document["model"]),
                    attacker=Attacker(**document["attacker"]),
                    population=Population(**document["population"]),
                    matching_variables=tuple(document["matching_variables"]),
                    pixel_derived=document["pixel_derived"],
                    generalisation=document["generalisation"],
                    missing_data=document["missing_data"],
                    uncertainty=document["uncertainty"],
                    exclusions=document["exclusions"],
                    linked_records=document["linked_records"],
                    earlier_releases=document["earlier_releases"],
                    device_identity=document["device_identity"],
                    facial_reconstruction=document["facial_reconstruction"],
                    subjects=document["subjects"],
                    threshold=document["threshold"],
                    maximum_risk=document["maximum_risk"],
                    assessor=document["assessor"],
                    assessed_at=datetime.datetime.fromisoformat(
                        document["assessed_at"]
                    ),
                ),
            )
    # UnicodeError and RiskAssessmentError are ValueErrors; TypeError covers
    # wrong types and a section's unknown or missing fields.
    except (ValueError, KeyError, TypeError):
        pass
    raise RiskAssessmentError("the risk assessment is not of its format")


# The members of a record's document, in its order.
_FIELDS = (
    "format",
    "reference",
    "pack",
    "pack_digest",
    "collection_sha256",
    "policy_sha256",
    "lists_salt",
    "lists_sha256",
    "model",
    "attacker",
    "population",
    "matching_variables",
    "pixel_derived",
    "generalisation",
    "missing_data",
    "uncertainty",
    "exclusions",
    "linked_records",
    "earlier_releases",
    "device_identity",
    "facial_reconstruction",
    "subjects",
    "threshold",
    "maximum_risk",
    "assessor",
    "assessed_at",
)
