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

A run gives its :class:`Reporter` the outcome of each input and the QC
material that the transform and gate gave for it, and writes the text that
the reporter returns as :data:`RELEASE_REPORT` at the root of the release,
before it publishes it. :class:`ReleaseReporter` builds the report of
:mod:`~pymedphys._dicom.deidentify.release_report` from them: each
sequestered input by its label and reasons (D-026), how many instances
were held for review by reason (D-009), and how many source values the
residual searches did not search, by attribute and reason, each counted at
the instance that holds it among those that the transform gave material for
(D-027). The report holds no source value or path (D-016), and
:func:`~pymedphys._dicom.deidentify.release_report.to_json` refuses any
field that could hold one. Before the run labels its outcomes, it asks the
reporter whether it :meth:`~Reporter.admits` each withheld input's reasons,
and sequesters one whose reasons it cannot report for
:attr:`~.reasons.RunReason.INVALID_REASON`, which the report gives alone,
so that one input's reasons never stop the release.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from pymedphys._nomenclature import tg263

from . import release_report
from .policy import Policy
from .reasons import RunReason
from .residuals import NotSearched, Unsearched, UnsearchedReason
from .run_qc import Dropped, SearchMaterial

# The release report's name at the root of a release. Output names are
# upper case, so it cannot be one.
RELEASE_REPORT = "release-report.json"
# The statuses of withheld outcomes, which this module reads without
# importing the run.
HELD_FOR_REVIEW = "held-for-review"
SEQUESTERED = "sequestered"


class Reporter(Protocol):
    """Return a run's release report as text, from its outcomes and material."""

    def admits(self, status: str, reasons: tuple[object, ...]) -> bool:
        """Whether the report can give a withheld outcome with these reasons.

        ``status`` is the value of the outcome's status, such as
        ``"sequestered"``.
        """

    def __call__(
        self,
        outcomes: Sequence[object],
        material: Mapping[int, Sequence[object]],
    ) -> str: ...


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
    """

    def __init__(self, policy: Policy, *, vocabulary: tg263.Nomenclature | None):
        if not isinstance(policy, Policy):
            raise TypeError("policy must be a Policy")
        self._policy = policy
        self._vocabulary = vocabulary

    def __repr__(self) -> str:
        return "ReleaseReporter()"

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
    ) -> str:
        report = self._report(
            sequestered=sequestered_instances(outcomes),
            held=held_instances(outcomes),
            coverage=release_report.search_coverage(
                coverage_records(material[position]) for position in sorted(material)
            ),
        )
        return release_report.to_json(report)

    def _report(self, **run: object) -> release_report.ReleaseReport:
        return release_report.release_report(
            self._policy,
            vocabulary=self._vocabulary,
            **run,  # type: ignore[arg-type]
        )


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


def held_instances(
    outcomes: Sequence[object],
) -> tuple[release_report.HeldForReview, ...]:
    """Count the instances held for review by stage and reason (D-009).

    An identical copy of a held input is the same instance, so it is not
    counted again.

    Raises
    ------
    TypeError
        For a held outcome's reason that is neither a held ROI Name nor a
        release gate's reason.
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
