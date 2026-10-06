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
# One module for the report's model, whose checks span its sections.

"""The release report: a record of a de-identification run and its method.

Each de-identification run writes a release report, through
:mod:`~pymedphys._dicom.deidentify.run_report`: a record of what was done
that can be distributed with the output, so it contains no source attribute
value, original path, or key. The run writes it as ``release-report.json``,
with its human-readable form, which
:mod:`~pymedphys._dicom.deidentify.release_report_markdown` generates from
that text alone, as ``release-report.md``. These parts of it do not depend
on the instances of a run:

- ``policy``: the PS3.15 edition, the preset (None for a custom option set),
  the selected options, and whether the policy can claim conformance;
- ``method``: the method digest that each instance records in
  De-identification Method (0012,0063), with the components it is computed
  from, so that two digests can be compared component by component
  (:class:`~pymedphys._dicom.deidentify.method_digest.MethodDigestComponents`);
- ``runtime``: the PyMedPhys, Python, pydicom, and tomlkit versions that ran,
  the same values that Software Versions (0018,1020) of the de-identifying
  equipment records
  (:class:`~pymedphys._dicom.deidentify.runtime.RuntimeEnvironment`).

:func:`report_document` gives a report as JSON values, and :func:`to_json`
as text; each first checks every field's form, as :func:`report_document`
lists. Every field is built from the policy, the engine's own files, the
versions that run it, the keyed digest of the reviewed-names list, the QC
pack's opaque reference, the replacement identifiers that name released
instances, the run's labels, and codes and attribute tags that the engine
defines, never from DICOM data directly, and the check is a backstop: a
field of another form, which could be a source value or a path outside the
package, is refused. A field that fails is named, never quoted.

Eight sections describe a run, by replacement identifiers, attribute tags,
and codes that the engine defines, never by a source value or path:

- ``qc_review``: the run's QC pack by its opaque reference, with the outcome
  of a reviewer's attestation of it (D-016) and the releaser's confirmations
  in it, each true, false, or None where not stated, that the output was
  checked for its intended use and that its residual risk was accepted, from
  :func:`~pymedphys._dicom.deidentify.qc_attestation.attestation_record`;
  None for a run that wrote no QC pack. The pack and the attestation, which
  names the reviewer, stay confidential.
- ``released``: each released instance by its output name, the path below
  the release directory that
  :func:`~pymedphys._dicom.deidentify.output_names.instance_path` gives
  from its replacement Patient ID and UIDs (D-026).
- ``sequestered``: each instance that was sequestered, by a label that
  :func:`sequestration_labels` gives at random for the run, with each
  reason (D-026). A sequestered instance has no output name, and the label
  holds nothing of the instance or its place in the run; only the
  confidential QC pack maps labels to sources (D-016). The release gate's
  reasons, among them the residual search's findings, name the stage
  ``"release"``, a code, and, where the reason names one, the attribute's
  tags.
- ``held_for_review``: how many instances were held for review, by stage and
  reason (D-009), from :func:`held_for_review`: a ROI Name that descriptor
  cleaning held, or a release gate's reason that requires QC review. A held
  instance has neither an output name nor a label.
- ``roi_names``: the outcome of each ROI Name of the structure sets that
  descriptor cleaning cleaned, every name counted, and how many distinct
  names it sent for review for each reason, whether they were then held or
  emptied unreviewed, from
  :meth:`~pymedphys._dicom.deidentify.reviewed_roi_names.ReviewQueue.report_counts`,
  naming none of them (D-009). Only the QC pack lists the names.
- ``reference_findings``: how many instances have each kind of reference
  finding that the run reports without acting on it, such as a dangling
  reference, from :func:`reference_findings`, each instance once for each
  kind. Only the QC pack lists them by instance.
- ``search_coverage``: how many source values of each attribute the
  residual search did not search, in full or in part, by reason (D-027),
  from :func:`search_coverage`. The QC pack lists each by instance and
  place.
- ``source_gaps``: how many instances' sources lack each attribute that
  their IOD unconditionally requires, by its tags and Type, from
  :func:`source_gaps`. The run reports these and never acts on them, since
  the source lacked them before de-identification (MIDI-BP-03). The QC pack
  lists each by instance and place.
"""

from __future__ import annotations

import collections
import dataclasses
import json
import random
import re
import secrets
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath

from pymedphys._nomenclature import tg263

from . import method_digest, output_names
from .method_digest import MethodDigestComponents
from .file_layout import TAG_PATTERN, ElementPath
from .iod_conformance import SourceGap
from .labels import LABEL_PATTERN as _LABEL_PATTERN
from .policy import PRESETS, Policy
from .preservation import PreservationReason
from .preserving_writer import WriteReason
from .qc_attestation import AttestationRecord, Outcome
from .reasons import DescriptorReason, HeldRoiName, RunReason, TransformReason
from .reference_graph import FindingKind
from .release_gate import Decision, ReasonCode, ReleaseReason
from .reviewed_roi_names import Outcome as RoiNameOutcome
from .reviewed_roi_names import RoiNameCounts
from .roi_names import Reason as RoiNameReason
from .residuals import NotSearched, Omission, Unsearched, UnsearchedReason
from .runtime import RuntimeEnvironment, runtime_environment
from .scope import Disposition
from .source import SourceReason
from .standard import OPTIONS, VRS
from .walker import Sequestration, SequesterReason

# The format of the report document. A change to its fields takes a new label.
FORMAT = "pymedphys-deid-release-report/8"

_DIGEST = re.compile(r"[0-9a-f]{64}")
_EDITION = re.compile(r"[0-9]{4}[a-z]")
# A version, or a Python implementation's name: no space, separator, or
# other character that a path or a person's name would need.
_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+!_-]{0,63}")
# A file name within the package, which never starts with "." (so is never
# ".." or a cache), and a table, which is a JSON file of the tables' folder.
_NAME = re.compile(r"[0-9A-Za-z_][0-9A-Za-z_.-]*")
_TABLE = re.compile(r"[0-9A-Za-z_][0-9A-Za-z_.-]*\.json")
# The form of a sequestered instance's label, kept here for the modules that
# name it as the release report's.
LABEL_PATTERN = _LABEL_PATTERN
_ATTRIBUTE = re.compile(rf"{TAG_PATTERN.pattern}( > {TAG_PATTERN.pattern})*")
_ACTIONS = frozenset({"K", "X", "Z", "D", "U", "C"})
# The QC pack's opaque reference, as qc_pack gives it (D-016).
_REFERENCE = re.compile(r"A-[0-9a-f]{32}")

# The reason codes of each stage that sequesters an instance.
_SEQUESTERING = {
    "scope": frozenset(d.value for d in Disposition) - {Disposition.SUPPORTED.value},
    "admission": frozenset(r.value for r in SourceReason),
    "references": frozenset(
        {
            FindingKind.MISSING_IDENTIFIER.value,
            FindingKind.CONFLICTING_INSTANCE.value,
            FindingKind.SERIES_IN_SEVERAL_STUDIES.value,
        }
    ),
    "walker": frozenset(r.value for r in SequesterReason),
    # the run's own checks after the first pass
    "run": frozenset(
        r.value
        for r in (
            RunReason.UNREADABLE_SEQUENCE,
            RunReason.CHANGED_DURING_RUN,
            RunReason.INVALID_OUTPUT_NAME,
            RunReason.SHARED_OUTPUT_NAME,
            RunReason.STAGED_FILE_CHANGED,
            RunReason.INCONSISTENT_REFERENCES,
            RunReason.INVALID_REASON,
            RunReason.INTERNAL_ERROR,
        )
    ),
    "transform": frozenset(
        {*(r.value for r in TransformReason), *(r.value for r in DescriptorReason)}
    ),
    "writer": frozenset(r.value for r in WriteReason),
    "verifier": frozenset(r.value for r in PreservationReason),
    "release": frozenset(r.value for r in ReasonCode),
}
# The first pass's findings that the run acts on: those that sequester the
# inputs they name, stop the run, or have an input written once. The run
# reports every other finding without acting on it.
_ACTED_ON_FINDINGS = frozenset(
    {
        FindingKind.MISSING_IDENTIFIER,
        FindingKind.CONFLICTING_INSTANCE,
        FindingKind.SERIES_IN_SEVERAL_STUDIES,
        FindingKind.STUDY_WITH_SEVERAL_PATIENTS,
        FindingKind.DUPLICATE_INSTANCE,
    }
)
REPORTED_FINDINGS = frozenset(FindingKind) - _ACTED_ON_FINDINGS
"""The first pass's findings that a run reports without acting on them."""
_REPORTED_CODES = frozenset(kind.value for kind in REPORTED_FINDINGS)
# The reason codes of each stage that holds an instance for review.
_HOLDING = {
    "roi-names": frozenset(r.value for r in RoiNameReason),
    "release": _SEQUESTERING["release"],
}
# Each enum whose members are a stage's codes, by its stage.
_STAGES = {
    Disposition: "scope",
    SourceReason: "admission",
    FindingKind: "references",
    RunReason: "run",
    TransformReason: "transform",
    DescriptorReason: "transform",
    WriteReason: "writer",
    PreservationReason: "verifier",
}


class ReleaseReportError(ValueError):
    """A release report has a field that could hold a value or a path.

    The message names the field, never its value.
    """


@dataclasses.dataclass(frozen=True)
class PolicyRecord:
    """The policy that a release report records.

    Attributes
    ----------
    preset : str or None
        The preset, such as ``"basic"``, or None for a custom option set.
    edition : str
        The edition of PS3.15 Table E.1-1, such as ``"2026d"``.
    options : tuple of str
        The selected options, in the table's order.
    claims_conformance : bool
        Whether the policy can claim PS3.15 conformance, which it cannot
        when it leaves a selected option's action unapplied, as
        ``tps-import`` does.
    """

    preset: str | None
    edition: str
    options: tuple[str, ...]
    claims_conformance: bool


@dataclasses.dataclass(frozen=True)
class SequestrationReason:
    """Why an instance was sequestered, by codes that the engine defines.

    Attributes
    ----------
    stage : str
        What sequestered it: ``"scope"``, ``"admission"`` (a source file
        refused, which is set aside like any sequestered instance),
        ``"references"`` (the first pass's reference graph), ``"walker"``,
        ``"run"`` (the run's own checks of each input, of what the transform
        and gate return, and of what was written against the reference
        graph), ``"transform"`` (the transform,
        including descriptor cleaning), ``"writer"``, ``"verifier"`` (the
        check that the source is preserved), or ``"release"`` (the release
        gate).
    code : str
        The stage's reason code, such as ``"conflicting-instance"``.
    attribute : str or None
        For the walker, and for the release gate where its reason names one,
        the attribute's tags from the outermost sequence, without items,
        such as ``"(0010,1002) > (0010,0020)"``; None for every other stage.
    action : str or None
        For the walker, and only for it, the action at that place, such as
        ``"D"``.
    vr : str or None
        For the walker, the VR that the action met, if known; None for every
        other stage.
    """

    stage: str
    code: str
    attribute: str | None = None
    action: str | None = None
    vr: str | None = None


@dataclasses.dataclass(frozen=True)
class SequesteredInstance:
    """An instance that was sequestered, as a release report names it (D-026).

    Attributes
    ----------
    label : str
        Its label for the run, from :func:`sequestration_labels`.
    reasons : tuple of SequestrationReason
    """

    label: str
    reasons: tuple[SequestrationReason, ...]


@dataclasses.dataclass(frozen=True)
class SearchCoverage:
    """How many source values of an attribute were not searched, and why.

    Attributes
    ----------
    attribute : str
        The attribute's tags from the outermost sequence, without items.
    reason : str
        An :class:`~pymedphys._dicom.deidentify.residuals.Omission` or an
        :class:`~pymedphys._dicom.deidentify.residuals.UnsearchedReason`, as
        its value, such as ``"too-short"``.
    count : int
    """

    attribute: str
    reason: str
    count: int


@dataclasses.dataclass(frozen=True)
class HeldForReview:
    """How many instances were held for review for one reason.

    The instances have neither an output name nor a label, and the report
    counts them by reason alone (D-009).

    Attributes
    ----------
    stage : str
        ``"roi-names"`` (descriptor cleaning held a ROI Name) or
        ``"release"`` (the release gate requires QC review).
    code : str
        The stage's reason code, such as ``"unmatched"``.
    count : int
        How many held instances have that reason, each once.
    """

    stage: str
    code: str
    count: int


@dataclasses.dataclass(frozen=True)
class ReferenceFindings:
    """How many instances have one kind of reported reference finding.

    The run reports these findings without acting on them, and the report
    counts the instances by kind alone; only the QC pack lists them by
    position.

    Attributes
    ----------
    kind : str
        A :class:`~pymedphys._dicom.deidentify.reference_graph.FindingKind`
        in :data:`REPORTED_FINDINGS`, as its value, such as
        ``"dangling-reference"``.
    count : int
        How many instances have a finding of that kind, each once.
    """

    kind: str
    count: int


@dataclasses.dataclass(frozen=True)
class SourceGapCount:
    """How many instances' sources lack one attribute that their IOD requires.

    Attributes
    ----------
    attribute : str
        The attribute's tags from the outermost sequence, without items.
    type : str
        ``"1"`` or ``"2"``, the Type that requires it.
    count : int
        How many instances lack it, each once.
    """

    attribute: str
    type: str
    count: int


@dataclasses.dataclass(frozen=True)
class ReleaseReport:
    """A release report's record of the method, the runtime, and the run.

    Attributes
    ----------
    policy : PolicyRecord
    method : ~pymedphys._dicom.deidentify.method_digest.MethodDigestComponents
    runtime : ~pymedphys._dicom.deidentify.runtime.RuntimeEnvironment
    qc_review : ~pymedphys._dicom.deidentify.qc_attestation.AttestationRecord or None
    released : tuple of pathlib.PurePosixPath
    sequestered : tuple of SequesteredInstance
    search_coverage : tuple of SearchCoverage
    held_for_review : tuple of HeldForReview
    roi_names : ~pymedphys._dicom.deidentify.reviewed_roi_names.RoiNameCounts
    reference_findings : tuple of ReferenceFindings
    source_gaps : tuple of SourceGapCount
    """

    policy: PolicyRecord
    method: MethodDigestComponents
    runtime: RuntimeEnvironment
    qc_review: AttestationRecord | None = None
    released: tuple[PurePosixPath, ...] = ()
    sequestered: tuple[SequesteredInstance, ...] = ()
    search_coverage: tuple[SearchCoverage, ...] = ()
    held_for_review: tuple[HeldForReview, ...] = ()
    roi_names: RoiNameCounts = dataclasses.field(
        default_factory=lambda: RoiNameCounts({}, {})
    )
    reference_findings: tuple[ReferenceFindings, ...] = ()
    source_gaps: tuple[SourceGapCount, ...] = ()


def attribute_tags(path: ElementPath) -> str:
    """Return an element's tags from the outermost sequence, without items.

    >>> attribute_tags(ElementPath((("(0010,1002)", 3),), "(0010,0020)"))
    '(0010,1002) > (0010,0020)'
    """
    return " > ".join([*(tag for tag, _ in path.items), path.tag])


def sequestration_reason(
    cause: (
        Disposition
        | SourceReason
        | FindingKind
        | Sequestration
        | RunReason
        | TransformReason
        | DescriptorReason
        | WriteReason
        | PreservationReason
        | ReleaseReason
    ),
) -> SequestrationReason:
    """Return the reason that a stage gives for sequestering an instance.

    Raises
    ------
    ValueError
        For a disposition or finding that does not sequester an instance:
        :attr:`~.scope.Disposition.SUPPORTED`; a dangling reference or an
        identical duplicate, which are reported only; or a study with
        several patients, which stops the run instead. An instance missing
        an identifier is sequestered, as the run pipeline does by default;
        or a reason of the run that refuses an input rather than
        sequestering it, such as a symbolic link.
    TypeError
        For anything else.
    """
    if isinstance(cause, Sequestration):
        return SequestrationReason(
            "walker",
            cause.reason.value,
            attribute_tags(cause.path),
            cause.action,
            cause.vr,
        )
    if isinstance(cause, ReleaseReason):
        if not isinstance(cause.code, ReasonCode):
            raise TypeError("a release reason must have a ReasonCode")
        return SequestrationReason(
            "release",
            cause.code.value,
            None if cause.path is None else attribute_tags(cause.path),
        )
    stage = _STAGES.get(type(cause))  # type: ignore[arg-type]
    if stage is None:
        raise TypeError("a reason must come from a stage that sequesters instances")
    if cause.value not in _SEQUESTERING[stage]:
        raise ValueError(f"{type(cause).__name__}.{cause.name} does not sequester")
    return SequestrationReason(stage, cause.value)


def sequestration_labels(
    count: int, *, rng: random.Random | None = None
) -> tuple[str, ...]:
    """Return a label for each of ``count`` sequestered instances, at random.

    The labels are ``S-0001`` to ``S-n``, all with the same number of
    digits, at least four, given in an order drawn from ``rng``, by default the
    operating system's source of randomness, so that a label says nothing
    of an instance or of its place in the run (D-026). Only the QC pack maps
    labels to sources.
    """
    labels = _labels(count)
    (rng or secrets.SystemRandom()).shuffle(labels)
    return tuple(labels)


def _labels(count: int) -> list[str]:
    width = max(4, len(str(count)))
    return [f"S-{number:0{width}d}" for number in range(1, count + 1)]


def search_coverage(
    instances: Iterable[Iterable[NotSearched | Unsearched]],
) -> tuple[SearchCoverage, ...]:
    """Count the values not searched by attribute and reason (D-027).

    ``instances`` holds, for each instance, its records of what the
    residual search did not search. A source value counts once for each
    reason, however many of its forms or spellings that reason left out,
    since a :class:`~pymedphys._dicom.deidentify.residuals.NotSearched`
    names one form of a value at its place, and an
    :class:`~pymedphys._dicom.deidentify.residuals.Unsearched` a value
    left out in whole or, for a written constant, in part. Values at the same place in different instances count apart.
    The counts are in the order of their attributes and reasons.

    >>> from pymedphys._dicom.deidentify.residuals import (
    ...     Unsearched, UnsearchedReason)
    >>> place = ElementPath((), "(0010,0020)")
    >>> retained = Unsearched(place, UnsearchedReason.RETAINED)
    >>> search_coverage([[retained, retained], [retained]])
    (SearchCoverage(attribute='(0010,0020)', reason='retained', count=2),)
    """
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for records in instances:
        if isinstance(records, (NotSearched, Unsearched)):
            raise TypeError("records must be given for each instance")
        places = set()
        for record in records:
            if not isinstance(record, (NotSearched, Unsearched)):
                raise TypeError("a record must be NotSearched or Unsearched")
            places.add((record.source, record.reason.value))
        for source, reason in places:
            counts[attribute_tags(source), reason] += 1
    return tuple(
        SearchCoverage(attribute, reason, count)
        for (attribute, reason), count in sorted(counts.items())
    )


def source_gaps(
    instances: Iterable[Iterable[SourceGap]],
) -> tuple[SourceGapCount, ...]:
    """Count the instances whose sources lack each required attribute.

    ``instances`` holds, for each instance, what its source lacks. An
    instance counts once for an attribute and Type, however many of its
    items lack it. The counts are in the order of their attributes and
    Types.

    >>> gap = SourceGap(ElementPath((), "(0008,0060)"), "1")
    >>> source_gaps([[gap], [gap], []])
    (SourceGapCount(attribute='(0008,0060)', type='1', count=2),)
    """
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for gaps in instances:
        if isinstance(gaps, SourceGap):
            raise TypeError("gaps must be given for each instance")
        found = set()
        for gap in gaps:
            if not isinstance(gap, SourceGap):
                raise TypeError("a gap must be a SourceGap")
            found.add((attribute_tags(gap.path), gap.type))
        counts.update(found)
    return tuple(
        SourceGapCount(attribute, gap_type, count)
        for (attribute, gap_type), count in sorted(counts.items())
    )


def held_for_review(
    instances: Iterable[Iterable[HeldRoiName | ReleaseReason]],
) -> tuple[HeldForReview, ...]:
    """Count the instances held for review by stage and reason (D-009).

    ``instances`` holds, for each held instance, its reasons: a ROI Name
    that descriptor cleaning held, or a release gate's reason that requires
    QC review. An instance
    counts once for each stage and code, however many of its names or
    attributes have it. The counts are in the order of their stages and
    codes.

    Raises
    ------
    TypeError
        For a reason of another type, or a release gate's reason that does
        not require QC review.
    """
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for reasons in instances:
        if isinstance(reasons, (HeldRoiName, ReleaseReason)):
            raise TypeError("reasons must be given for each instance")
        codes = set()
        for reason in reasons:
            if isinstance(reason, HeldRoiName):
                codes.add(("roi-names", reason.reason.value))
            elif (
                isinstance(reason, ReleaseReason)
                and reason.decision is Decision.QC_REVIEW
                and isinstance(reason.code, ReasonCode)
            ):
                codes.add(("release", reason.code.value))
            else:
                raise TypeError(
                    "a held reason must be a HeldRoiName or a release reason "
                    "that requires QC review"
                )
        counts.update(codes)
    return tuple(
        HeldForReview(stage, code, count)
        for (stage, code), count in sorted(counts.items())
    )


def reference_findings(
    instances: Iterable[Iterable[FindingKind]],
) -> tuple[ReferenceFindings, ...]:
    """Count the instances with reported reference findings, by kind.

    ``instances`` holds, for each instance with one, the kinds of its
    findings that the run reports without acting on them. An instance
    counts once for each kind, however many of its findings or groups have
    it. The counts are in the order of their kinds' values.

    >>> reference_findings(
    ...     [[FindingKind.DANGLING_REFERENCE] * 2, [FindingKind.DANGLING_REFERENCE]]
    ... )
    (ReferenceFindings(kind='dangling-reference', count=2),)

    Raises
    ------
    TypeError
        For a kind that is not a
        :class:`~pymedphys._dicom.deidentify.reference_graph.FindingKind` in
        :data:`REPORTED_FINDINGS`.
    """
    counts: collections.Counter[str] = collections.Counter()
    for kinds in instances:
        if isinstance(kinds, FindingKind):
            raise TypeError("kinds must be given for each instance")
        found = set()
        for kind in kinds:
            if kind not in REPORTED_FINDINGS:
                raise TypeError(
                    "a reference finding must be a FindingKind that the run "
                    "reports without acting on it"
                )
            found.add(kind.value)
        counts.update(found)
    return tuple(
        ReferenceFindings(kind, count) for kind, count in sorted(counts.items())
    )


def release_report(
    policy: Policy,
    *,
    vocabulary: tg263.Nomenclature | None,
    reviewed_roi_names: str | None,
    qc_review: AttestationRecord | None = None,
    released: Iterable[PurePosixPath] = (),
    sequestered: Iterable[SequesteredInstance] = (),
    coverage: Iterable[SearchCoverage] = (),
    held: Iterable[HeldForReview] = (),
    roi_names: RoiNameCounts | None = None,
    findings: Iterable[ReferenceFindings] = (),
    gaps: Iterable[SourceGapCount] = (),
) -> ReleaseReport:
    """Return the release report of a policy, its method, the runtime, and a run.

    Parameters
    ----------
    policy : Policy
        A validated policy, such as one from
        :func:`~pymedphys._dicom.deidentify.policy.compose_policy`.
    vocabulary : ~pymedphys._nomenclature.tg263.Nomenclature or None
        The TG-263 vocabulary that descriptor cleaning matches ROI Names
        against, or None without one. It must be given by name, and has no
        default, so that every caller states whether there is one. The
        report records only its content digest.
    reviewed_roi_names : str or None
        The keyed digest of the reviewed-names list whose decisions
        descriptor cleaning applies to ROI Names, or None without a list. It
        must be given by name, and has no default, so that every caller
        states whether there is one. The report records only this digest.
    qc_review : ~pymedphys._dicom.deidentify.qc_attestation.AttestationRecord, optional
        The run's QC pack by its reference, with its attestation's outcome
        and the releaser's confirmations, from
        :func:`~pymedphys._dicom.deidentify.qc_attestation.attestation_record`;
        None, the default, where the run wrote no QC pack.
    released : iterable of pathlib.PurePosixPath, optional
        The output name of each released instance, as
        :func:`~pymedphys._dicom.deidentify.output_names.instance_path`
        gives it.
    sequestered : iterable of SequesteredInstance, optional
        The run's sequestered instances.
    coverage : iterable of SearchCoverage, optional
        How many values the run's residual search did not search, from
        :func:`search_coverage`.
    held : iterable of HeldForReview, optional
        How many of the run's instances were held for review, by reason,
        from :func:`held_for_review`.
    roi_names : ~pymedphys._dicom.deidentify.reviewed_roi_names.RoiNameCounts, optional
        What descriptor cleaning wrote for the run's ROI Names, from
        :meth:`~pymedphys._dicom.deidentify.reviewed_roi_names.ReviewQueue.report_counts`;
        None, the default, counts none.
    findings : iterable of ReferenceFindings, optional
        How many of the run's instances have each kind of reference finding
        that the run reports without acting on it, from
        :func:`reference_findings`.
    gaps : iterable of SourceGapCount, optional
        How many of the run's instances' sources lack each attribute that
        their IOD requires, from :func:`source_gaps`.

    Returns
    -------
    ReleaseReport

    Raises
    ------
    TypeError, ValueError
        For any reason
        :func:`~pymedphys._dicom.deidentify.method_digest.method_digest_components`
        gives.

    Examples
    --------
    >>> from pymedphys._dicom.deidentify.policy import compose_policy
    >>> report = release_report(
    ...     compose_policy("basic"), vocabulary=None, reviewed_roi_names=None
    ... )
    >>> report.policy.preset, report.policy.options
    ('basic', ())
    >>> list(report_document(report))
    ['format', 'policy', 'method', 'runtime', 'qc_review', 'released', 'sequestered', 'held_for_review', 'roi_names', 'reference_findings', 'search_coverage', 'source_gaps']
    """
    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    return ReleaseReport(
        policy=PolicyRecord(
            preset=policy.preset,
            edition=policy.edition,
            options=tuple(policy.options),
            claims_conformance=policy.claims_conformance,
        ),
        method=method_digest.method_digest_components(
            policy, vocabulary=vocabulary, reviewed_roi_names=reviewed_roi_names
        ),
        runtime=runtime_environment(),
        qc_review=qc_review,
        released=tuple(released),
        sequestered=tuple(sequestered),
        search_coverage=tuple(coverage),
        held_for_review=tuple(held),
        roi_names=RoiNameCounts({}, {}) if roi_names is None else roi_names,
        reference_findings=tuple(findings),
        source_gaps=tuple(gaps),
    )


def _refuse(field: str, problem: str) -> ReleaseReportError:
    return ReleaseReportError(f"the release report's {field} {problem}")


def _matches(pattern: re.Pattern, value: object) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _digest(field: str, value: object) -> str:
    if not _matches(_DIGEST, value):
        raise _refuse(field, "is not 64 lowercase hexadecimal digits")
    return str(value)


def _optional_digest(field: str, value: object) -> str | None:
    return None if value is None else _digest(field, value)


def _version(field: str, value: object) -> str:
    if not _matches(_VERSION, value):
        raise _refuse(field, "is not a version")
    return str(value)


def _package_path(value: object) -> bool:
    return isinstance(value, str) and all(
        _NAME.fullmatch(part) for part in value.split("/")
    )


def _digests(field: str, value: object, name: re.Pattern | None) -> dict[str, str]:
    """Return a mapping of names or package paths to digests, sorted by name."""
    if not isinstance(value, Mapping):
        raise _refuse(field, "is not a mapping")
    for key in value:
        if not (_matches(name, key) if name else _package_path(key)):
            raise _refuse(field, "has a name that is not within the package")
    return {key: _digest(field, value[key]) for key in sorted(value)}


def _policy_section(record: PolicyRecord) -> dict:
    if record.preset is not None and not (
        isinstance(record.preset, str) and record.preset in PRESETS
    ):
        raise _refuse("preset", "is not a preset")
    if not _matches(_EDITION, record.edition):
        raise _refuse("edition", "is not an edition")
    if not isinstance(record.options, tuple) or any(
        option not in OPTIONS for option in record.options
    ):
        raise _refuse("options", "are not PS3.15 options")
    if not isinstance(record.claims_conformance, bool):
        raise _refuse("claims_conformance", "is not true or false")
    return {
        "preset": record.preset,
        "edition": record.edition,
        "options": list(record.options),
        "claims_conformance": record.claims_conformance,
    }


def _method_section(method: MethodDigestComponents) -> dict:
    if method.method_digest_format != method_digest.FORMAT:
        raise _refuse("method_digest_format", "is not the method digest's format")
    return {
        "method_digest": _digest("method_digest", method.method_digest),
        "method_digest_format": method.method_digest_format,
        "engine_version": _version("engine_version", method.engine_version),
        "table_digests": _digests("table_digests", method.table_digests, _TABLE),
        "l2_rules_digest": _digest("l2_rules_digest", method.l2_rules_digest),
        "l3_rules": _optional_digest("l3_rules", method.l3_rules),
        "vocabulary_digest": _optional_digest(
            "vocabulary_digest", method.vocabulary_digest
        ),
        "reviewed_roi_names": _optional_digest(
            "reviewed_roi_names", method.reviewed_roi_names
        ),
        "generated_values_digest": _digest(
            "generated_values_digest", method.generated_values_digest
        ),
        "engine_files": _digests("engine_files", method.engine_files, None),
    }


def _runtime_section(environment: RuntimeEnvironment) -> dict:
    return {
        field.name: _version(field.name, getattr(environment, field.name))
        for field in dataclasses.fields(environment)
    }


def _string(value: object) -> str | None:
    # A str subclass could carry anything in its methods or attributes, so
    # only a str itself is written, as the value that was checked.
    return value if type(value) is str else None  # pylint: disable=unidiomatic-typecheck


def _code(field: str, value: object, codes: Iterable[str]) -> str:
    text = _string(value)
    if text is None or text not in frozenset(codes):
        raise _refuse(field, "is not a code that the engine defines")
    return text


def _attribute(field: str, value: object) -> str:
    text = _string(value)
    if text is None or _ATTRIBUTE.fullmatch(text) is None:
        raise _refuse(field, "is not a path of tags")
    return text


def _reason_entry(reason: object) -> dict:
    if not isinstance(reason, SequestrationReason):
        raise _refuse("sequestered reasons", "are not a tuple of reasons")
    stage = _code("sequestered stage", reason.stage, _SEQUESTERING)
    code = _code("sequestered code", reason.code, _SEQUESTERING[stage])
    if stage == "release":
        if (reason.action, reason.vr) != (None, None):
            raise _refuse("sequestered action", "is given for another stage")
        if reason.attribute is None:
            return {"stage": stage, "code": code}
        return {
            "stage": stage,
            "code": code,
            "attribute": _attribute("sequestered attribute", reason.attribute),
        }
    if stage != "walker":
        if (reason.attribute, reason.action, reason.vr) != (None, None, None):
            raise _refuse("sequestered attribute", "is given for another stage")
        return {"stage": stage, "code": code}
    return {
        "stage": stage,
        "code": code,
        "attribute": _attribute("sequestered attribute", reason.attribute),
        "action": _code("sequestered action", reason.action, _ACTIONS),
        "vr": None if reason.vr is None else _code("sequestered vr", reason.vr, VRS),
    }


# The releaser's confirmations in an attestation, in the report's order.
_CONFIRMATIONS = ("intended_use_checked", "residual_risk_accepted")


def _qc_review_section(record: AttestationRecord | None) -> dict | None:
    if record is None:
        return None
    if not isinstance(record, AttestationRecord):
        raise _refuse("qc_review", "is not an attestation record")
    if _string(record.reference) is None or not _REFERENCE.fullmatch(record.reference):
        raise _refuse("qc_review reference", "is not a QC pack's reference")
    if type(record.outcome) is not Outcome:  # pylint: disable = unidiomatic-typecheck
        raise _refuse("qc_review outcome", "is not an attestation outcome")
    confirmations = {name: getattr(record, name) for name in _CONFIRMATIONS}
    for name, value in confirmations.items():
        if value is not None and type(value) is not bool:  # pylint: disable = unidiomatic-typecheck
            raise _refuse(f"qc_review {name}", "is not true, false, or None")
        if value is not None and record.outcome is Outcome.NOT_ATTESTED:
            raise _refuse(f"qc_review {name}", "is given without an attestation")
    return {
        "reference": record.reference,
        "outcome": record.outcome.value,
        **confirmations,
    }


def _is_output_name(path: object) -> bool:
    """Whether ``path`` is one that ``output_names.instance_path`` gives."""
    if type(path) is not PurePosixPath:  # pylint: disable = unidiomatic-typecheck
        return False
    if len(path.parts) != 4 or not path.name.endswith(output_names.FILE_SUFFIX):
        return False
    patient, study, series, name = path.parts
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


def _released_section(released: tuple[PurePosixPath, ...]) -> list:
    if not all(_is_output_name(path) for path in released):
        raise _refuse("released", "is not a tuple of output names")
    names = sorted(str(path) for path in released)
    if len(set(names)) != len(names):
        raise _refuse("released", "names an instance twice")
    return names


def _sequestered_section(instances: tuple[SequesteredInstance, ...]) -> list:
    if not all(isinstance(each, SequesteredInstance) for each in instances):
        raise _refuse("sequestered", "is not a tuple of sequestered instances")
    labels = {_string(instance.label) for instance in instances}
    if labels != set(_labels(len(instances))):
        raise _refuse("sequestered label", "are not the labels S-0001 to S-n")
    entries = []
    for instance in sorted(instances, key=lambda each: each.label):
        if not (isinstance(instance.reasons, tuple) and instance.reasons):
            raise _refuse("sequestered reasons", "are not a tuple of reasons")
        reasons: list[dict] = []
        for reason in instance.reasons:
            entry = _reason_entry(reason)
            if entry not in reasons:
                reasons.append(entry)
        entries.append({"label": instance.label, "reasons": reasons})
    return entries


_UNSEARCHED = frozenset(
    {*(o.value for o in Omission), *(r.value for r in UnsearchedReason)}
)


def _coverage_section(coverage: tuple[SearchCoverage, ...]) -> list:
    entries = []
    for each in coverage:
        if not isinstance(each, SearchCoverage):
            raise _refuse("search_coverage", "is not a tuple of coverage counts")
        if not (isinstance(each.count, int) and not isinstance(each.count, bool)):
            raise _refuse("search_coverage count", "is not a whole number")
        if each.count < 1:
            raise _refuse("search_coverage count", "is not positive")
        entries.append(
            {
                "attribute": _attribute("search_coverage attribute", each.attribute),
                "reason": _code("search_coverage reason", each.reason, _UNSEARCHED),
                "count": each.count,
            }
        )
    return sorted(entries, key=lambda entry: (entry["attribute"], entry["reason"]))


def _held_section(held: tuple[HeldForReview, ...]) -> list:
    entries = []
    for each in held:
        if not isinstance(each, HeldForReview):
            raise _refuse("held_for_review", "is not a tuple of held counts")
        if not (isinstance(each.count, int) and not isinstance(each.count, bool)):
            raise _refuse("held_for_review count", "is not a whole number")
        if each.count < 1:
            raise _refuse("held_for_review count", "is not positive")
        stage = _code("held_for_review stage", each.stage, _HOLDING)
        entries.append(
            {
                "stage": stage,
                "code": _code("held_for_review code", each.code, _HOLDING[stage]),
                "count": each.count,
            }
        )
    return sorted(entries, key=lambda entry: (entry["stage"], entry["code"]))


def _roi_name_counts(
    field: str, counts: object, codes: type[RoiNameOutcome] | type[RoiNameReason]
) -> list[tuple[str, int]]:
    """Return the counts of one kind of ROI Name code, sorted by code."""
    if not isinstance(counts, Mapping):
        raise _refuse(f"roi_names {field}", "is not counts by code")
    entries = []
    for code, count in counts.items():
        if type(code) is not codes:  # pylint: disable = unidiomatic-typecheck
            raise _refuse(f"roi_names {field}", "is not a code that the engine defines")
        if type(count) is not int:  # pylint: disable = unidiomatic-typecheck
            raise _refuse(f"roi_names {field} count", "is not a whole number")
        if count < 1:
            raise _refuse(f"roi_names {field} count", "is not positive")
        entries.append((code.value, count))
    return sorted(entries)


def _roi_names_section(counts: RoiNameCounts) -> dict:
    if not isinstance(counts, RoiNameCounts):
        raise _refuse("roi_names", "is not counts of ROI Names")
    return {
        "outcomes": [
            {"outcome": code, "count": count}
            for code, count in _roi_name_counts(
                "outcome", counts.outcomes, RoiNameOutcome
            )
        ],
        "held": [
            {"reason": code, "count": count}
            for code, count in _roi_name_counts("reason", counts.held, RoiNameReason)
        ],
    }


def _reference_findings_section(found: tuple[ReferenceFindings, ...]) -> list:
    entries = []
    for each in found:
        if not isinstance(each, ReferenceFindings):
            raise _refuse("reference_findings", "is not a tuple of finding counts")
        if type(each.count) is not int:  # pylint: disable = unidiomatic-typecheck
            raise _refuse("reference_findings count", "is not a whole number")
        if each.count < 1:
            raise _refuse("reference_findings count", "is not positive")
        kind = _code("reference_findings kind", each.kind, _REPORTED_CODES)
        entries.append({"kind": kind, "count": each.count})
    kinds = [entry["kind"] for entry in entries]
    if len(set(kinds)) != len(kinds):
        raise _refuse("reference_findings kind", "is counted more than once")
    return sorted(entries, key=lambda entry: entry["kind"])


def _gaps_section(gaps: tuple[SourceGapCount, ...]) -> list:
    entries = []
    for each in gaps:
        if not isinstance(each, SourceGapCount):
            raise _refuse("source_gaps", "is not a tuple of gap counts")
        if not (isinstance(each.count, int) and not isinstance(each.count, bool)):
            raise _refuse("source_gaps count", "is not a whole number")
        if each.count < 1:
            raise _refuse("source_gaps count", "is not positive")
        entries.append(
            {
                "attribute": _attribute("source_gaps attribute", each.attribute),
                "type": _code("source_gaps type", each.type, _REQUIRED_TYPES),
                "count": each.count,
            }
        )
    return sorted(entries, key=lambda entry: (entry["attribute"], entry["type"]))


_REQUIRED_TYPES = frozenset({"1", "2"})


def report_document(report: ReleaseReport) -> dict:
    """Return a release report as JSON values, after checking every field.

    The document is an object with the members ``format`` (:data:`FORMAT`),
    ``policy``, ``method``, ``runtime``, ``qc_review``, ``released``,
    ``sequestered``, ``held_for_review``, ``roi_names``,
    ``reference_findings``, ``search_coverage``, and ``source_gaps``, in that
    order, each section's fields in the order of its class, the digests of
    tables and files sorted by name, ``qc_review`` null where the run wrote no
    QC pack, the released output names sorted, the sequestered instances by
    label, each with its reasons once, in the order given, the held counts by
    stage and code, the ROI Names' ``outcomes`` and ``held`` counts each by
    code, the reference findings' counts by kind, the coverage by attribute
    and reason, and the source gaps by attribute and Type. A walker
    reason has its stage, code, attribute, action, and VR, which is null
    where it is not known; a release gate's reason has its stage and code,
    and its attribute where it names one; and a reason from any other stage
    has only its stage and code.

    Parameters
    ----------
    report : ReleaseReport

    Returns
    -------
    dict

    Raises
    ------
    ReleaseReportError
        If a field does not have the form of a digest, a version, a known
        edition, preset, or option, the method digest's format, a file name
        or path within the engine's package, a QC pack's reference and an
        attestation outcome, a confirmation given only with an attestation,
        an output name that
        :func:`~pymedphys._dicom.deidentify.output_names.instance_path`
        gives, listed once, one of the labels ``S-0001`` to ``S-n`` for ``n``
        sequestered instances, a path of tags, a code that the engine
        defines for its stage, a positive count, or true or false, or is not
        of its class. The message names the field, never its value.
    """
    return {
        "format": FORMAT,
        "policy": _policy_section(report.policy),
        "method": _method_section(report.method),
        "runtime": _runtime_section(report.runtime),
        "qc_review": _qc_review_section(report.qc_review),
        "released": _released_section(report.released),
        "sequestered": _sequestered_section(report.sequestered),
        "held_for_review": _held_section(report.held_for_review),
        "roi_names": _roi_names_section(report.roi_names),
        "reference_findings": _reference_findings_section(report.reference_findings),
        "search_coverage": _coverage_section(report.search_coverage),
        "source_gaps": _gaps_section(report.source_gaps),
    }


def to_json(report: ReleaseReport) -> str:
    """Return a release report as JSON text, after checking every field.

    The text is :func:`report_document` indented by two spaces, with
    characters outside ASCII written as themselves and a final newline, so
    the same report always gives the same text.

    Parameters
    ----------
    report : ReleaseReport

    Returns
    -------
    str

    Raises
    ------
    ReleaseReportError
        For any reason :func:`report_document` gives.
    """
    return json.dumps(report_document(report), indent=2, ensure_ascii=False) + "\n"
