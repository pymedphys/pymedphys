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

"""Acceptance criteria for the text detector's evaluation (D-056).

Criteria are set before tuning, and none are built in: each is a
parameter. :func:`assess` reads only a summary of
:func:`~.text_evaluation.summarise`, so the same summary can be assessed
again, once published, against other criteria. A point meets the criteria
where every cell that a criterion names does:

- each cell of IOD, contrast, and height that a
  :class:`SensitivityCriterion` matches has at least its share of texts
  fully covered;
- each IOD that a :class:`FalsePositiveCriterion` matches has at most its
  share of frames without text with a region, and at most its share of
  their tissue blacked out;
- no stratum's share of texts fully covered falls, nor its share of frames
  with a region rises, by more than :attr:`AcceptanceCriteria.max_loss`
  from the baseline point's.

With the ``"interval"`` bound, the least favourable end of each share's
Wilson interval is compared, so that a cell of few texts cannot pass by
chance; a cell with fewer texts or frames than the minimum fails.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from .text_evaluation_frames import EvaluationRefused


@dataclasses.dataclass(frozen=True)
class SensitivityCriterion:
    """The least share of texts fully covered in every cell of IOD,
    contrast, and height that matches; ``"*"`` matches any."""

    minimum: float
    iod: str = "*"
    contrast: str = "*"
    height: str = "*"


@dataclasses.dataclass(frozen=True)
class FalsePositiveCriterion:
    """The most that frames without text of a matching IOD may show: the
    share with a region, and the share of their tissue blacked out."""

    iod: str = "*"
    max_with_a_region: float | None = None
    max_tissue_blacked_out: float | None = None


@dataclasses.dataclass(frozen=True)
class AcceptanceCriteria:
    """Criteria for a point, set before tuning; none are built in.

    Attributes
    ----------
    sensitivity : tuple of SensitivityCriterion
    false_positives : tuple of FalsePositiveCriterion
    max_loss : float or None
        No stratum's share of texts fully covered may be lower, nor its
        share of frames with a region higher, than the baseline's by more
        than this.
    baseline : int
        The point that ``max_loss`` compares with.
    bound : str
        ``"interval"`` compares the Wilson interval's least favourable end
        with each limit; ``"estimate"`` compares the share itself.
    min_texts, min_frames : int
        A cell with fewer fails, as there is too little evidence.
    """

    sensitivity: tuple[SensitivityCriterion, ...] = ()
    false_positives: tuple[FalsePositiveCriterion, ...] = ()
    max_loss: float | None = None
    baseline: int = 0
    bound: str = "interval"
    min_texts: int = 30
    min_frames: int = 30

    def __post_init__(self):
        if self.bound not in ("interval", "estimate"):
            raise EvaluationRefused("The bound must be interval or estimate.")


def assess(
    summary: Mapping[str, Any], criteria: AcceptanceCriteria
) -> list[dict[str, Any]]:
    """Whether each point of a summary meets the criteria, and which cells
    fail and why. It reads only the summary, so it can be run again on a
    published one with other criteria."""
    points = summary["points"]
    if not 0 <= criteria.baseline < len(points):
        raise EvaluationRefused("The baseline must be a point of the summary.")
    baseline = points[criteria.baseline]
    assessed = []
    for point in points:
        failures = _failures(point, baseline, criteria)
        assessed.append(
            {"index": point["index"], "meets": not failures, "failures": failures}
        )
    return assessed


def _failures(
    point: Mapping[str, Any], baseline: Mapping[str, Any], criteria: AcceptanceCriteria
) -> list[str]:
    failures = []
    interval = criteria.bound == "interval"
    cells = point["by"].get("iod+contrast+height", [])
    if criteria.sensitivity and not cells:
        failures.append(
            "sensitivity: the summary has no IOD, contrast, and height cells"
        )
    for criterion in criteria.sensitivity:
        for cell in cells:
            value = cell["value"]
            if not all(
                wanted in ("*", value[name])
                for name, wanted in (
                    ("iod", criterion.iod),
                    ("contrast", criterion.contrast),
                    ("height", criterion.height),
                )
            ):
                continue
            measure = cell["sensitivity"]
            label = f"{value['iod']}, {value['contrast']}, {value['height']}"
            if measure["texts"] == 0 or measure["texts"] < criteria.min_texts:
                failures.append(f"sensitivity: {label}: too few texts")
                continue
            share = measure["wilson"][0] if interval else measure["share"]
            if share < criterion.minimum:
                failures.append(
                    f"sensitivity: {label}: {share:.3f} below {criterion.minimum:g}"
                )
    by_iod = point["by"].get("iod", [])
    for criterion in criteria.false_positives:
        for cell in by_iod:
            iod = cell["value"]["iod"]
            if criterion.iod not in ("*", iod):
                continue
            measure = cell["false_positives"]
            if measure["frames"] == 0:
                continue
            if measure["frames"] < criteria.min_frames:
                failures.append(f"false positives: {iod}: too few frames")
                continue
            share = measure["wilson"][1] if interval else measure["share"]
            if (
                criterion.max_with_a_region is not None
                and share > criterion.max_with_a_region
            ):
                failures.append(
                    f"false positives: {iod}: {share:.3f} of frames with a region, "
                    f"above {criterion.max_with_a_region:g}"
                )
            tissue = measure["tissue_blacked_out"]
            if (
                criterion.max_tissue_blacked_out is not None
                and tissue is not None
                and tissue > criterion.max_tissue_blacked_out
            ):
                failures.append(
                    f"false positives: {iod}: {tissue:.4f} of tissue blacked out, "
                    f"above {criterion.max_tissue_blacked_out:g}"
                )
    if criteria.max_loss is not None:
        failures += _losses(point, baseline, criteria.max_loss)
    return failures


def _losses(
    point: Mapping[str, Any], baseline: Mapping[str, Any], margin: float
) -> list[str]:
    failures = []
    for grouping, rows in point["by"].items():
        if "+" in grouping:
            continue
        before = {
            tuple(sorted(row["value"].items())): row
            for row in baseline["by"].get(grouping, [])
        }
        for row in rows:
            old = before.get(tuple(sorted(row["value"].items())))
            if old is None:
                continue
            label = (
                f"{grouping} {', '.join(str(each) for each in row['value'].values())}"
            )
            new_share, old_share = (
                row["sensitivity"]["share"],
                old["sensitivity"]["share"],
            )
            if (
                new_share is not None
                and old_share is not None
                and new_share < old_share - margin
            ):
                failures.append(
                    f"loss: {label}: sensitivity {new_share:.3f} from {old_share:.3f}"
                )
            if "false_positives" not in row:
                continue
            new_fp = row["false_positives"]["share"]
            old_fp = old["false_positives"]["share"]
            if new_fp is not None and old_fp is not None and new_fp > old_fp + margin:
                failures.append(
                    f"loss: {label}: frames with a region {new_fp:.3f} from {old_fp:.3f}"
                )
    return failures
