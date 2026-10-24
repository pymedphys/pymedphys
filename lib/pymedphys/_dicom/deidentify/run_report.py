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

"""The release report that a run publishes with its release.

A run gives its :class:`Reporter` the outcome of each input, the QC
material that the transform and gate gave for it, and the opaque reference
of the run's QC pack, and writes the text that
the reporter returns as :data:`RELEASE_REPORT` at the root of the release,
with its human-readable form as :data:`RELEASE_REPORT_MARKDOWN` beside it
(:func:`release_files`), before it publishes it. :class:`ReleaseReporter` builds the report of
:mod:`~pymedphys._dicom.deidentify.release_report` from them: the QC
pack by its reference, not yet attested, since a reviewer attests to it
after the run (D-016); each released instance by its output name, and each
sequestered input by its label and reasons (D-026); how many instances
were held for review by reason (D-009), what descriptor cleaning wrote for
ROI Names and free-text descriptors, by count, how many regions Clean Pixel
Data blacked out, by what gave them, how many instances have each kind
of reference finding that the run reports without acting on it, from the
material that the run adds for them, how many released and held instances
show each risk in their pixel data, and each indicator of it, from the
material that the transform gives and the assessment of their series, as
the QC pack lists them (D-015), and how many source values the
residual searches did not search, by attribute and reason, each counted at
the instance that holds it among those that the transform gave material for
(D-027). The report holds no source value or path (D-016), and
:func:`~pymedphys._dicom.deidentify.release_report.to_json` refuses any
field that could hold one. Before the run labels its outcomes, it asks the
reporter whether it :meth:`~Reporter.admits` each withheld input's reasons,
and sequesters one whose reasons it cannot report for
:attr:`~.reasons.RunReason.INVALID_REASON`, which the report gives alone,
so that one input's reasons never stop the release.

Under the ``public-release`` preset, the run also gives the reporter its
:class:`RunFacts`: its own QC pack, as it writes it, and how many distinct
subjects it releases. From them, and from the earlier run's review that the
reporter was given, if any
(:class:`~pymedphys._dicom.deidentify.readiness.ReadinessReview`), the
report says whether the run is ready for release by its three gates
(:func:`~pymedphys._dicom.deidentify.readiness.readiness`, D-017).

The reporter also gives the conformance statement of the run's policy,
which the run writes as :data:`CONFORMANCE_STATEMENT` beside the report
(Architecture item 10). It is generated from the policy and the vocabulary
alone, so it holds no instance value either.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Protocol

from pymedphys._nomenclature import tg263

from . import (
    conformance,
    conformance_markdown,
    readiness,
    release_report,
    release_report_markdown,
)
from .face_blocks import FaceBlockCounts
from .policy import CLEAN_PIXEL_DATA, Policy
from .qc_attestation import AttestationRecord, Outcome
from .qc_pack import QcPack
from .readiness import ReadinessReview
from .risk_assessment import policy_digest
from .reasons import RunReason
from .residuals import NotSearched, Unsearched, UnsearchedReason
from .iod_conformance import SourceGap
from .reviewed_descriptors import (
    DescriptorCounts,
    DescriptorReviewQueue,
    ReviewedDescriptors,
)
from .reviewed_roi_names import (
    CleanedRoiName,
    ReviewedNames,
    ReviewQueue,
    RoiNameCounts,
)
from .safe_private import SafePrivateList
from .run_qc import (
    DescriptorMaterial,
    Dropped,
    PixelRiskMaterial,
    RedactionMaterial,
    ReferenceFindingMaterial,
    RoiNameMaterial,
    SearchMaterial,
    SeriesEvidence,
    WrittenFindingMaterial,
    assessed_series,
)

# The release report's name at the root of a release. Output names are
# upper case, so it cannot be one.
RELEASE_REPORT = "release-report.json"
# Its human-readable form, beside it.
RELEASE_REPORT_MARKDOWN = "release-report.md"
# The conformance statement of the run's policy, beside them.
CONFORMANCE_STATEMENT = "conformance-statement.md"
# The statuses of withheld outcomes, which this module reads without
# importing the run.
HELD_FOR_REVIEW = "held-for-review"
RELEASED = "released"
SEQUESTERED = "sequestered"


@dataclasses.dataclass(frozen=True, repr=False)
class RunFacts:
    """What a run's reporter needs of the run besides its outcomes and material.

    Its ``repr`` shows nothing, since the pack holds source paths and
    values.

    Attributes
    ----------
    pack : ~pymedphys._dicom.deidentify.qc_pack.QcPack
        The run's QC pack, as the run writes it.
    subjects : int
        How many distinct subjects the instances that the run releases
        have, from
        :func:`~pymedphys._dicom.deidentify.readiness.released_subjects`.
    """

    pack: QcPack
    subjects: int

    def __repr__(self) -> str:
        return "RunFacts()"


class Reporter(Protocol):
    """Return a run's release report as text, from its outcomes and material.

    The text is that which
    :func:`~pymedphys._dicom.deidentify.release_report.to_json` gives, from
    which the run generates the report's human-readable form. ``qc_pack`` is
    the opaque reference of the run's QC pack, and ``facts`` the run's
    :class:`RunFacts`. ``reviewed_lists`` are the reviewed ROI names and
    descriptors lists that the run's descriptor cleaning applies, as it read
    them, or None for each that it was not given, whose salted digest the
    run records in its QC pack.
    """

    @property
    def reviewed_lists(
        self,
    ) -> tuple[ReviewedNames | None, ReviewedDescriptors | None]: ...

    def admits(self, status: str, reasons: tuple[object, ...]) -> bool:
        """Whether the report can give a withheld outcome with these reasons.

        ``status`` is the value of the outcome's status, such as
        ``"sequestered"``.
        """

    def __call__(
        self,
        outcomes: Sequence[object],
        material: Mapping[int, Sequence[object]],
        qc_pack: str,
        facts: RunFacts,
    ) -> str: ...

    def conformance_statement(self) -> str:
        """The conformance statement of the run's policy, as CommonMark."""


class ReleaseReporter:
    """The release report of a run under one policy.

    Parameters
    ----------
    policy : Policy
        The run's policy.
    vocabulary : ~pymedphys._nomenclature.tg263.Nomenclature or None
        The TG-263 vocabulary that descriptor cleaning matches ROI Names
        against, or None without one, as
        :func:`~pymedphys._dicom.deidentify.release_report.release_report`
        takes it.
    reviewed_roi_names : str or None
        The keyed digest of the reviewed-names list that descriptor cleaning
        applies to ROI Names, or None without one, as
        :func:`~pymedphys._dicom.deidentify.release_report.release_report`
        takes it.
    face_review : str, optional
        The reference of the attested QC pack whose face verdicts the run
        applies under the Clean Recognizable Visual Features Option, or
        None, the default, without one.
    redaction_review : str, optional
        The reference of the attested QC pack whose redaction verdicts the
        run applies under the Clean Pixel Data Option, or None, the
        default, without one.
    reviewed_descriptors : str or None, optional
        The keyed digest of the reviewed descriptors list that descriptor
        cleaning applies to free-text descriptors, or None, the default,
        without one, as
        :func:`~pymedphys._dicom.deidentify.release_report.release_report`
        takes it.
    technique_vocabulary : str or None, optional
        The SHA-256 of the technique vocabulary that descriptor cleaning
        applies to technique descriptors, or None, the default, without one,
        as :func:`~pymedphys._dicom.deidentify.release_report.release_report`
        takes it.
    face_blocks : ~pymedphys._dicom.deidentify.face_blocks.FaceBlockCounts, optional
        With ``face_review``, the counts of the run's CT series that the
        transform defaced and did not, which it fills in before the run
        writes any instance, as
        :meth:`~pymedphys._dicom.deidentify.instance_transform.InstanceTransform.prepare`
        does; None, the default, without one.
    text_finder : Mapping of str to object, or None, optional
        The class and description of the method of the text finder that the
        Clean Pixel Data Option applies, or None, the default, without one, as
        :func:`~pymedphys._dicom.deidentify.release_report.release_report`
        takes it.
    pixel_region_rules : str or None, optional
        The keyed digest of the reviewed region rules that the Clean Pixel
        Data Option applies, or None, the default, without rules, as
        :func:`~pymedphys._dicom.deidentify.release_report.release_report`
        takes it.
    safe_private_list : SafePrivateList, optional
        Under the Retain Safe Private Option, the list whose rules settle
        private attributes, the reviewed rules by default, as
        :func:`~pymedphys._dicom.deidentify.release_report.release_report`
        and :func:`~pymedphys._dicom.deidentify.conformance.conformance_statement`
        take it.
    project_key : str, optional
        The identifier of the project key whose subject profiles the run
        reads and records (D-004), or None, the default, for a run-scoped
        key, as
        :func:`~pymedphys._dicom.deidentify.release_report.release_report`
        takes it; the conformance statement then says that the run's
        generated values agree with every other run under that key.
    readiness_review : ~pymedphys._dicom.deidentify.readiness.ReadinessReview, optional
        Under the ``public-release`` preset, the review of an earlier run of
        the collection, from
        :func:`~pymedphys._dicom.deidentify.readiness.read_readiness_review`,
        from which the report says whether the run is ready for release;
        None, the default, without one, which fails every gate. No other
        policy takes one.
    reviewed_lists : tuple of (ReviewedNames or None, ReviewedDescriptors or None), optional
        The reviewed-names and reviewed descriptors lists that descriptor
        cleaning applies, as it read them, whose keyed digests are
        ``reviewed_roi_names`` and ``reviewed_descriptors``, for the
        readiness section's statistical gate; neither, the default, without
        descriptor cleaning.

    Raises
    ------
    TypeError
        If ``policy`` is not a Policy, or ``readiness_review`` is not a
        ReadinessReview.
    ValueError
        If ``readiness_review`` is given with a policy other than the
        ``public-release`` preset.
    """

    def __init__(
        self,
        policy: Policy,
        *,
        vocabulary: tg263.Nomenclature | None,
        reviewed_roi_names: str | None,
        face_review: str | None = None,
        reviewed_descriptors: str | None = None,
        technique_vocabulary: str | None = None,
        face_blocks: FaceBlockCounts | None = None,
        redaction_review: str | None = None,
        text_finder: Mapping[str, object] | None = None,
        pixel_region_rules: str | None = None,
        safe_private_list: SafePrivateList = SafePrivateList.REVIEWED,
        project_key: str | None = None,
        readiness_review: ReadinessReview | None = None,
        reviewed_lists: tuple[ReviewedNames | None, ReviewedDescriptors | None] = (
            None,
            None,
        ),
    ):
        if not isinstance(policy, Policy):
            raise TypeError("policy must be a Policy")
        if readiness_review is not None and not isinstance(
            readiness_review, ReadinessReview
        ):
            raise TypeError("readiness_review must be a ReadinessReview")
        self._readiness = policy.preset == release_report.PUBLIC_RELEASE
        if readiness_review is not None and not self._readiness:
            raise ValueError(
                "a readiness review is given only under the public-release preset"
            )
        self._readiness_review = readiness_review
        self._project_key = project_key
        self._reviewed_lists = reviewed_lists
        self._policy = policy
        self._vocabulary = vocabulary
        self._reviewed_roi_names = reviewed_roi_names
        self._face_review = face_review
        self._reviewed_descriptors = reviewed_descriptors
        self._technique_vocabulary = technique_vocabulary
        self._face_blocks = face_blocks
        self._redaction_review = redaction_review
        self._text_finder = text_finder
        self._pixel_region_rules = pixel_region_rules
        self._safe_private_list = safe_private_list

    def __repr__(self) -> str:
        return "ReleaseReporter()"

    @property
    def reviewed_lists(self) -> tuple[ReviewedNames | None, ReviewedDescriptors | None]:
        """The lists given as ``reviewed_lists``, which the run's QC pack binds."""
        return self._reviewed_lists

    def admits(self, status: str, reasons: tuple[object, ...]) -> bool:
        """Whether the report can give a withheld outcome with these reasons.

        It can if a report that gives them alone can be written.
        """
        if not isinstance(reasons, tuple) or not reasons:
            return False
        try:
            if status == SEQUESTERED:
                given = release_report.SequesteredInstance(
                    _TRIAL_LABEL, _reasons_given(reasons)
                )
                report = self._report(sequestered=(given,))
            elif status == HELD_FOR_REVIEW:
                report = self._report(
                    held=release_report.held_for_review((reasons,))  # type: ignore[arg-type]
                )
            else:
                return False
            release_report.to_json(report)
        # A ReleaseReportError is a ValueError; AttributeError is for a
        # reason whose fields are not as its type says.
        except (TypeError, ValueError, AttributeError):
            return False
        return True

    def __call__(
        self,
        outcomes: Sequence[object],
        material: Mapping[int, Sequence[object]],
        qc_pack: str,
        facts: RunFacts | None = None,
    ) -> str:
        """Return the run's release report, as the module describes.

        Under the ``public-release`` preset it needs the run's ``facts``,
        which no other policy reads.
        """
        report = self._report(
            qc_review=AttestationRecord(qc_pack, Outcome.NOT_ATTESTED),
            released=released_instances(outcomes),
            sequestered=sequestered_instances(outcomes),
            held=held_instances(outcomes),
            coverage=release_report.search_coverage(
                coverage_records(material[position]) for position in sorted(material)
            ),
            roi_names=roi_name_counts(material),
            descriptors=descriptor_counts(material),
            pixel_regions=(
                pixel_regions(outcomes, material)
                if CLEAN_PIXEL_DATA in self._policy.options
                else None
            ),
            findings=reference_findings(outcomes, material),
            pixel=pixel_risks(outcomes, material),
            gaps=release_report.source_gaps(
                [item for item in material[position] if isinstance(item, SourceGap)]
                for position in sorted(material)
            ),
            checks=structural_checks(outcomes, material),
        )
        if self._readiness:
            if not isinstance(facts, RunFacts):
                raise TypeError("a public-release report needs the run's RunFacts")
            report = dataclasses.replace(
                report,
                # The readiness section is not in the policy digest, which
                # reads only the report's policy and method.
                readiness=readiness.readiness(
                    self._readiness_review,
                    facts.pack,
                    subjects=facts.subjects,
                    policy_sha256=policy_digest(release_report.report_document(report)),
                    reviewed_names=self._reviewed_lists[0],
                    reviewed_descriptors=self._reviewed_lists[1],
                ),
            )
        return release_report.to_json(report)

    def conformance_statement(self) -> str:
        """The conformance statement of the run's policy, as CommonMark.

        It is generated by
        :func:`~pymedphys._dicom.deidentify.conformance.conformance_statement`
        from the policy and vocabulary that the report records, and so
        describes the policy, not the run: it holds no instance value, and
        the run's own method digest and reviewed-names digest are those of
        the release report.

        Raises
        ------
        ValueError or MarkerError
            For any reason
            :func:`~pymedphys._dicom.deidentify.conformance.conformance_statement`
            gives.
        """
        statement = conformance.conformance_statement(
            self._policy,
            vocabulary=self._vocabulary,
            safe_private_list=self._safe_private_list,
            project_key=self._project_key is not None,
        )
        return conformance_markdown.render_markdown(statement)

    def _report(self, **run: object) -> release_report.ReleaseReport:
        return release_report.release_report(
            self._policy,
            vocabulary=self._vocabulary,
            reviewed_roi_names=self._reviewed_roi_names,
            face_review=self._face_review,
            face_blocks=self._face_blocks,
            redaction_review=self._redaction_review,
            reviewed_descriptors=self._reviewed_descriptors,
            technique_vocabulary=self._technique_vocabulary,
            text_finder=self._text_finder,
            pixel_region_rules=self._pixel_region_rules,
            safe_private_list=self._safe_private_list,
            project_key=self._project_key,
            **run,  # type: ignore[arg-type]
        )


def release_files(report: str, *, statement: str | None = None) -> dict[str, bytes]:
    """Return the files that a run writes at the root of its release.

    They are the report as given, as :data:`RELEASE_REPORT`, its
    human-readable form, generated from it alone by
    :func:`~pymedphys._dicom.deidentify.release_report_markdown.to_markdown`,
    as :data:`RELEASE_REPORT_MARKDOWN`, and the conformance statement, where
    one is given, as :data:`CONFORMANCE_STATEMENT`, each encoded as UTF-8.

    Raises
    ------
    ~pymedphys._dicom.deidentify.release_report_markdown.ReleaseReportMarkdownError
        If the report is not one that
        :func:`~pymedphys._dicom.deidentify.release_report.to_json` gives.
    """
    files = {
        RELEASE_REPORT: report.encode("utf-8"),
        RELEASE_REPORT_MARKDOWN: release_report_markdown.to_markdown(report).encode(
            "utf-8"
        ),
    }
    if statement is not None:
        files[CONFORMANCE_STATEMENT] = statement.encode("utf-8")
    return files


def documents(
    reporter: Reporter | None,
    outcomes: Sequence[object],
    material: Mapping[int, Sequence[object]],
    qc_pack: str,
    facts: RunFacts,
) -> dict[str, bytes]:
    """Return the :func:`release_files` of a run's reporter, or none without one.

    They are the reporter's release report and the conformance statement of
    its policy.
    """
    if reporter is None:
        return {}
    report = reporter(outcomes, material, qc_pack, facts)
    return release_files(report, statement=reporter.conformance_statement())


# A label for the report that tries whether a reason can be given.
_TRIAL_LABEL = "S-0001"


def _reasons_given(
    reasons: Sequence[object],
) -> tuple[release_report.SequestrationReason, ...]:
    """Return the report's reasons of a sequestered outcome.

    One that the run sequestered for an invalid reason is given by that
    alone: the reasons after it are those that the report cannot give, which
    only the QC pack lists.
    """
    if reasons and reasons[0] is RunReason.INVALID_REASON:
        reasons = reasons[:1]
    return tuple(
        release_report.sequestration_reason(reason)  # type: ignore[arg-type]
        for reason in reasons
    )


def sequestered_instances(
    outcomes: Sequence[object],
) -> tuple[release_report.SequesteredInstance, ...]:
    """Return each sequestered outcome by its label and reasons (D-026).

    Raises
    ------
    TypeError, ValueError
        For a reason that no stage of the release report gives, as
        :func:`~pymedphys._dicom.deidentify.release_report.sequestration_reason`
        raises them.
    """
    return tuple(
        release_report.SequesteredInstance(
            getattr(outcome, "label"), _reasons_given(getattr(outcome, "reasons"))
        )
        for outcome in outcomes
        if getattr(outcome, "label") is not None
    )


def released_instances(outcomes: Sequence[object]) -> tuple[PurePosixPath, ...]:
    """Return the output name of each released outcome (D-026).

    An identical copy of a released input is a duplicate, not released, so
    each output name is given once.
    """
    return tuple(
        getattr(outcome, "output")
        for outcome in outcomes
        if getattr(outcome, "status").value == RELEASED
    )


def reference_findings(
    outcomes: Sequence[object], material: Mapping[int, Sequence[object]]
) -> tuple[release_report.ReferenceFindings, ...]:
    """Count the instances with each kind of reference finding reported only.

    Each input's kinds come from its
    :class:`~pymedphys._dicom.deidentify.run_qc.ReferenceFindingMaterial`.
    An identical copy of an input is the same instance, so it is not counted
    again, although the QC pack lists the finding at each copy.
    """
    copies = {
        getattr(outcome, "position")
        for outcome in outcomes
        if getattr(outcome, "duplicate_of") is not None
    }
    return release_report.reference_findings(
        [
            item.kind
            for item in material[position]
            if isinstance(item, ReferenceFindingMaterial)
        ]
        for position in sorted(material)
        if position not in copies
    )


def pixel_regions(
    outcomes: Sequence[object], material: Mapping[int, Sequence[object]]
) -> release_report.PixelRegionCounts:
    """Count the regions that Clean Pixel Data blacked out, by what gave them.

    Each released or held input's regions come from its
    :class:`~pymedphys._dicom.deidentify.run_qc.RedactionMaterial`, which
    the transform gives only where no reviewer's verdict applied, each
    region once in each frame that has it: a reviewed region rule's, which
    is in every frame, or otherwise the text finder's (D-037). An identical
    copy of an input is the same instance, so it is not counted again.
    """
    shown = {
        getattr(outcome, "position")
        for outcome in outcomes
        if getattr(outcome, "status").value in release_report.PIXEL_RISK_DISPOSITIONS
        and getattr(outcome, "duplicate_of") is None
    }
    detected = rule = 0
    for position in sorted(material):
        if position not in shown:
            continue
        for item in material[position]:
            if isinstance(item, RedactionMaterial):
                ruled = len(item.rule_boxes) * len(item.regions)
                rule += ruled
                detected += sum(len(boxes) for _, boxes in item.regions) - ruled
                break
    return release_report.PixelRegionCounts(detected=detected, rule=rule)


def pixel_risks(
    outcomes: Sequence[object], material: Mapping[int, Sequence[object]]
) -> tuple[release_report.PixelRiskCount, ...]:
    """Count the released and held instances by the risks in their pixel data.

    Each input's own indicators come from its
    :class:`~pymedphys._dicom.deidentify.run_qc.PixelRiskMaterial`, and its
    series' from the assessment of the released and held instances'
    :class:`~pymedphys._dicom.deidentify.run_qc.SeriesEvidence`, grouped by
    series as the QC pack groups them, so that the report counts the
    findings that the pack lists (D-015). An identical copy of an input is
    the same instance, so it is not counted again, although it is assessed
    with its series.
    """
    statuses = {
        getattr(outcome, "position"): getattr(outcome, "status").value
        for outcome in outcomes
        if getattr(outcome, "status").value in release_report.PIXEL_RISK_DISPOSITIONS
    }
    copies = {
        getattr(outcome, "position")
        for outcome in outcomes
        if getattr(outcome, "duplicate_of") is not None
    }
    found: dict[int, list] = {}
    evidence: dict[int, SeriesEvidence] = {}
    for position in sorted(material):
        for item in material[position]:
            if isinstance(item, PixelRiskMaterial):
                found.setdefault(position, []).extend(
                    (finding.risk, finding.indicator)
                    for finding in item.assessment.findings
                )
            elif isinstance(item, SeriesEvidence):
                evidence.setdefault(position, item)
    for positions, series_findings in assessed_series(statuses, evidence):
        for finding in series_findings:
            for index in finding.instances:
                found.setdefault(positions[index], []).append(
                    (finding.risk, finding.indicator)
                )
    return release_report.pixel_risks(
        (statuses[position], found[position])
        for position in sorted(found)
        if position in statuses and position not in copies
    )


# The material by which each structural check reports an instance.
_REPORTED_BY_CHECK = {
    "references": ReferenceFindingMaterial,
    "iod-requirements": SourceGap,
    "written-references": WrittenFindingMaterial,
}


def structural_checks(
    outcomes: Sequence[object], material: Mapping[int, Sequence[object]]
) -> tuple[release_report.StructuralCheck, ...]:
    """Count the instances that each structural check sequestered and reported.

    An instance is sequestered by a check for the reasons that
    :func:`~pymedphys._dicom.deidentify.release_report.sequestering_checks`
    gives it for. It is reported by the first pass's references for a
    :class:`~pymedphys._dicom.deidentify.run_qc.ReferenceFindingMaterial`,
    by the IOD requirements for a gap in its source, a
    :class:`~pymedphys._dicom.deidentify.iod_conformance.SourceGap`, and by
    the written references for a
    :class:`~pymedphys._dicom.deidentify.run_qc.WrittenFindingMaterial`.
    Each is counted once however many it has, and an identical copy of an
    input is the same instance, so it is not counted again.
    """
    copies = {
        getattr(outcome, "position")
        for outcome in outcomes
        if getattr(outcome, "duplicate_of") is not None
    }
    sequestered = [
        release_report.sequestering_checks(_reasons_given(getattr(outcome, "reasons")))
        for outcome in outcomes
        if getattr(outcome, "label") is not None
        and getattr(outcome, "duplicate_of") is None
    ]
    return tuple(
        release_report.StructuralCheck(
            check,
            sum(check in checks for checks in sequestered),
            sum(
                any(isinstance(item, kind) for item in material[position])
                for position in material
                if position not in copies
            ),
        )
        for check, kind in _REPORTED_BY_CHECK.items()
    )


def held_instances(
    outcomes: Sequence[object],
) -> tuple[release_report.HeldForReview, ...]:
    """Count the instances held for review by stage and reason (D-009).

    An identical copy of a held input is the same instance, so it is not
    counted again.

    Raises
    ------
    TypeError
        For a held outcome's reason that is not a held ROI Name, why a pixel
        option held it, held visual features, or a release gate's reason.
    """
    return release_report.held_for_review(
        getattr(outcome, "reasons")
        for outcome in outcomes
        if getattr(outcome, "status").value == HELD_FOR_REVIEW
        and getattr(outcome, "duplicate_of") is None
    )


def coverage_records(material: Sequence[object]) -> list[NotSearched | Unsearched]:
    """Return what the residual searches did not search of one input's values.

    Each drop is an :class:`~.residuals.Unsearched` with the same reason;
    each :class:`~.residuals.NotSearched` of the input's own values is as it
    is; and so is each form that a search of its file lists, which
    :class:`~.instance_transform.ReleaseGate` leaves to the transform.
    """
    records: list[NotSearched | Unsearched] = []
    for item in material:
        if isinstance(item, Dropped):
            records.append(Unsearched(item.source, UnsearchedReason(item.reason.value)))
        elif isinstance(item, NotSearched):
            records.append(item)
        elif isinstance(item, SearchMaterial):
            records.extend(item.search.not_searched)
    return records


def roi_name_counts(material: Mapping[int, Sequence[object]]) -> RoiNameCounts:
    """Return what descriptor cleaning wrote for a run's ROI Names, by count.

    ``material`` is each input's QC material, by its position. Each input's
    :class:`~.run_qc.RoiNameMaterial` is the ROI Names of the one structure
    set that descriptor cleaning cleaned for it, as the QC pack lists them,
    so every name counts by its outcome, and each distinct held name once
    for each of its reasons, as
    :meth:`~pymedphys._dicom.deidentify.reviewed_roi_names.ReviewQueue.report_counts`
    gives, without a name.
    """
    queue = ReviewQueue()
    for position in sorted(material):
        names = [
            item for item in material[position] if isinstance(item, RoiNameMaterial)
        ]
        queue.add(
            [name.source for name in names],
            [
                CleanedRoiName(name.outcome, name.held_because, name.written)
                for name in names
            ],
        )
    return queue.report_counts()


def descriptor_counts(material: Mapping[int, Sequence[object]]) -> DescriptorCounts:
    """Return what descriptor cleaning wrote for a run's descriptors, by count.

    ``material`` is each input's QC material, by its position. Each
    :class:`~.run_qc.DescriptorMaterial` is the values of one descriptor
    element that descriptor cleaning read, as the QC pack lists them, so
    every value counts by its outcome, each distinct value held for review,
    of one attribute, once for each of its reasons, and each element that
    took its action without Clean Descriptors once, as
    :meth:`~pymedphys._dicom.deidentify.reviewed_descriptors.DescriptorReviewQueue.report_counts`
    gives, without a value.
    """
    queue = DescriptorReviewQueue()
    for position in sorted(material):
        for item in material[position]:
            if isinstance(item, DescriptorMaterial):
                queue.add(
                    item.attribute or item.path.tag,
                    item.sources,
                    item.results,
                    applied=item.applied,
                )
    return queue.report_counts()
