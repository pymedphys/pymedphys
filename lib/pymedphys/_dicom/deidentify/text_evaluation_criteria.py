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

Criteria are set before tuning. :func:`assess` reads only a summary of
:func:`~.text_evaluation.summarise`, so the same summary can be assessed
again, once published, against other criteria. A point meets the criteria
where every cell that a criterion names does:

- each cell of IOD, contrast, and height that a
  :class:`SensitivityCriterion` matches has at least its share of texts
  fully covered;
- each IOD that a :class:`FalsePositiveCriterion` matches, and each cell of
  that IOD and slice size, has at most its share of frames without text
  with a region, and at most its share of their tissue blacked out;
- each collection that a :class:`MissedTextCriterion` matches has at most
  its number of texts of its truth missed, with none of their ink covered;
- no single stratum's share of texts fully covered falls, nor its share of
  frames with a region rises, by more than
  :attr:`AcceptanceCriteria.max_loss` from the baseline point's.

With the ``"interval"`` bound, the least favourable end of each share's
Wilson interval is compared, so that a cell of few texts cannot pass by
chance, and, where :attr:`AcceptanceCriteria.bootstrap` is set, the least
favourable end of the bootstrap's interval over cases too, so that a cell
whose texts or frames come from few cases cannot pass on their number
alone. A cell with fewer texts or frames than the minimum fails, and so
does one without a bootstrap interval where one is needed. A cell that no
criterion matches is reported only.

:data:`CHOSEN_CRITERIA` holds the criteria that the maintainer chose on
1 November 2026, and :data:`HELD_OUT_COLLECTIONS` the collections held out
whole beside the split's rule.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from typing import Any

from .text_evaluation_frames import EvaluationRefused
from .text_evaluation_injection import CONTRAST, contrast_label

ANY = "*"
# Labels of a text's height in pixels, as a plan draws them: "7 px".
_PIXELS = re.compile(r"(\d+(?:\.\d+)?) px")

Labels = str | tuple[str, ...]


def _matches(wanted: Labels, value: str) -> bool:
    if isinstance(wanted, str):
        return wanted in (ANY, value)
    return value in wanted


def _check_labels(name: str, wanted: object) -> None:
    if isinstance(wanted, str):
        return
    if (
        not isinstance(wanted, tuple)
        or not wanted
        or not all(isinstance(each, str) and each != ANY for each in wanted)
    ):
        raise EvaluationRefused(f"A criterion's {name} must be a label or labels.")


def _check_share(name: str, value: float | None) -> None:
    if value is not None and not 0 <= value <= 1:
        raise EvaluationRefused(f"A criterion's {name} must be a share.")


@dataclasses.dataclass(frozen=True)
class SensitivityCriterion:
    """The least share of texts fully covered in every cell of IOD,
    contrast, and height that matches.

    Each of ``iod``, ``contrast``, and ``height`` is a label, ``"*"`` for
    any, or a tuple of labels, any of which matches. ``min_height_px``,
    where given, matches only cells whose height is drawn in pixels, as
    ``"7 px"`` is, at least that many; a height in millimetres matches no
    such criterion.
    """

    minimum: float
    iod: Labels = ANY
    contrast: Labels = ANY
    height: Labels = ANY
    min_height_px: float | None = None

    def __post_init__(self):
        _check_share("minimum", self.minimum)
        for name in ("iod", "contrast", "height"):
            _check_labels(name, getattr(self, name))

    def matches(self, value: Mapping[str, str]) -> bool:
        """Whether a cell of IOD, contrast, and height is the criterion's."""
        if not all(
            _matches(getattr(self, name), value[name])
            for name in ("iod", "contrast", "height")
        ):
            return False
        if self.min_height_px is None:
            return True
        pixels = _PIXELS.fullmatch(value["height"])
        return pixels is not None and float(pixels[1]) >= self.min_height_px


@dataclasses.dataclass(frozen=True)
class FalsePositiveCriterion:
    """The most that frames without text of a matching IOD may show, in
    all and in each bin of slice size: the share with a region, and the
    share of their tissue blacked out."""

    iod: Labels = ANY
    max_with_a_region: float | None = None
    max_tissue_blacked_out: float | None = None

    def __post_init__(self):
        _check_labels("iod", self.iod)
        _check_share("max_with_a_region", self.max_with_a_region)
        _check_share("max_tissue_blacked_out", self.max_tissue_blacked_out)


@dataclasses.dataclass(frozen=True)
class MissedTextCriterion:
    """The most texts of a truth, in collections whose names start with a
    prefix, that may be missed, with none of their ink covered.

    The counts are read from the summary's cells of collection and truth.
    """

    collection_prefix: str
    truth: str = "annotated"
    max_missed: int = 0

    def __post_init__(self):
        if not self.collection_prefix or self.max_missed < 0:
            raise EvaluationRefused("A missed-text criterion needs its collections.")


@dataclasses.dataclass(frozen=True)
class AcceptanceCriteria:
    """Criteria for a point, set before tuning.

    Attributes
    ----------
    sensitivity : tuple of SensitivityCriterion
    false_positives : tuple of FalsePositiveCriterion
    missed : tuple of MissedTextCriterion
    max_loss : float or None
        No single stratum's share of texts fully covered may be lower, nor
        its share of frames with a region higher, than the baseline's by
        more than this.
    baseline : int
        The point that ``max_loss`` compares with.
    bound : str
        ``"interval"`` compares the Wilson interval's least favourable end
        with each limit; ``"estimate"`` compares the share itself.
    bootstrap : bool
        With the ``"interval"`` bound, whether the bootstrap interval's
        least favourable end must meet each limit too.
    min_texts, min_frames : int
        A cell with fewer fails, as there is too little evidence.
    """

    sensitivity: tuple[SensitivityCriterion, ...] = ()
    false_positives: tuple[FalsePositiveCriterion, ...] = ()
    missed: tuple[MissedTextCriterion, ...] = ()
    max_loss: float | None = None
    baseline: int = 0
    bound: str = "interval"
    bootstrap: bool = False
    min_texts: int = 30
    min_frames: int = 30

    def __post_init__(self):
        if self.bound not in ("interval", "estimate"):
            raise EvaluationRefused("The bound must be interval or estimate.")
        if self.bootstrap and self.bound != "interval":
            raise EvaluationRefused("The bootstrap bound needs the interval bound.")
        _check_share("max_loss", self.max_loss)

    def described(self) -> dict[str, Any]:
        """The criteria, for a report."""
        return dataclasses.asdict(self)


def contrasts_from(low: float) -> tuple[str, ...]:
    """The contrast labels of :data:`~.text_evaluation_injection.CONTRAST`
    from ``low`` multiples of the noise up."""
    return _contrasts(low, None)


def _contrasts(low: float, high: float | None) -> tuple[str, ...]:
    if low not in CONTRAST or (high is not None and high not in CONTRAST):
        raise EvaluationRefused("A contrast range must run between bin edges.")
    return tuple(
        contrast_label(edge)
        for edge in CONTRAST
        if edge >= low and (high is None or edge < high)
    )


def contrasts_between(low: float, high: float) -> tuple[str, ...]:
    """The contrast labels from ``low`` to under ``high`` multiples of the
    noise, each a bin edge."""
    return _contrasts(low, high)


# CT's IODs include cone-beam CTs, which DICOM stores as CT Image Storage;
# PET's, DX's, and XA's include each SOP Class of that modality's images.
TOMOGRAPHIC_IODS = (
    "CT Image Storage",
    "Enhanced CT Image Storage",
    "MR Image Storage",
    "Enhanced MR Image Storage",
    "Positron Emission Tomography Image Storage",
    "Enhanced PET Image Storage",
)
PROJECTION_IODS = (
    "RT Image Storage",
    "Computed Radiography Image Storage",
    "Digital X-Ray Image Storage - For Presentation",
    "Digital X-Ray Image Storage - For Processing",
    "X-Ray Angiographic Image Storage",
    "Enhanced XA Image Storage",
)

# The criteria that the maintainer chose on 1 November 2026: every cell of
# texts at least 7 pixels high fully covered in at least 99% of texts of 16
# times the noise or more, and 95% from 4 to under 16 times; at most 2% of
# text-free tomographic frames and 5% of projection frames with a region, in
# each IOD and each slice size, and at most 0.01% of tissue blacked out in
# any; 400 texts and 300 frames at the least in each cell; both intervals'
# bounds; no single stratum 2 percentage points worse than today's
# defaults, the first point; and no MIDI-B answer-key text missed.
CHOSEN_CRITERIA = AcceptanceCriteria(
    sensitivity=(
        SensitivityCriterion(0.99, contrast=contrasts_from(16.0), min_height_px=7.0),
        SensitivityCriterion(
            0.95, contrast=contrasts_between(4.0, 16.0), min_height_px=7.0
        ),
    ),
    false_positives=(
        FalsePositiveCriterion(iod=TOMOGRAPHIC_IODS, max_with_a_region=0.02),
        FalsePositiveCriterion(iod=PROJECTION_IODS, max_with_a_region=0.05),
        FalsePositiveCriterion(max_tissue_blacked_out=0.0001),
    ),
    missed=(MissedTextCriterion("MIDI-B", truth="annotated", max_missed=0),),
    max_loss=0.02,
    baseline=0,
    bound="interval",
    bootstrap=True,
    min_texts=400,
    min_frames=300,
)
# Held out whole, beside the split's rule.
HELD_OUT_COLLECTIONS = ("Pediatric-CT-SEG",)


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
    failures = _sensitivity_failures(point, criteria)
    failures += _false_positive_failures(point, criteria)
    failures += _missed_failures(point, criteria)
    if criteria.max_loss is not None:
        failures += _losses(point, baseline, criteria.max_loss)
    return failures


def _bounds(
    measure: Mapping[str, Any],
    criteria: AcceptanceCriteria,
    end: int,
    share: str = "share",
    wilson: str | None = "wilson",
    bootstrap: str = "bootstrap",
) -> list[tuple[str, float | None]]:
    """The values to compare with a limit: the share, or its intervals'
    ends at ``end``, 0 for the lower and 1 for the upper."""
    if criteria.bound == "estimate":
        return [("", measure[share])]
    found: list[tuple[str, float | None]] = []
    if wilson is not None:
        found.append(("Wilson ", measure[wilson][end]))
    else:
        found.append(("", measure[share]))
    if criteria.bootstrap:
        interval = measure.get(bootstrap)
        found.append(("bootstrap ", None if interval is None else interval[end]))
    return found


def _sensitivity_failures(
    point: Mapping[str, Any], criteria: AcceptanceCriteria
) -> list[str]:
    failures = []
    cells = point["by"].get("iod+contrast+height", [])
    if criteria.sensitivity and not cells:
        failures.append(
            "sensitivity: the summary has no IOD, contrast, and height cells"
        )
    for criterion in criteria.sensitivity:
        for cell in cells:
            value = cell["value"]
            if not criterion.matches(value):
                continue
            measure = cell["sensitivity"]
            label = f"{value['iod']}, {value['contrast']}, {value['height']}"
            if measure["texts"] == 0 or measure["texts"] < criteria.min_texts:
                failures.append(f"sensitivity: {label}: too few texts")
                continue
            for name, share in _bounds(measure, criteria, 0):
                if share is None:
                    failures.append(f"sensitivity: {label}: no {name}interval")
                elif share < criterion.minimum:
                    failures.append(
                        f"sensitivity: {label}: {name}{share:.3f} "
                        f"below {criterion.minimum:g}"
                    )
    return failures


def _false_positive_failures(
    point: Mapping[str, Any], criteria: AcceptanceCriteria
) -> list[str]:
    failures = []
    cells = [(row, row["value"]["iod"]) for row in point["by"].get("iod", [])]
    cells += [
        (row, f"{row['value']['iod']}, {row['value']['slice_side']}")
        for row in point["by"].get("iod+slice_side", [])
    ]
    for criterion in criteria.false_positives:
        for cell, label in cells:
            if not _matches(criterion.iod, cell["value"]["iod"]):
                continue
            measure = cell["false_positives"]
            if measure["frames"] == 0:
                continue
            if measure["frames"] < criteria.min_frames:
                failures.append(f"false positives: {label}: too few frames")
                continue
            if criterion.max_with_a_region is not None:
                failures += _over(
                    f"false positives: {label}",
                    _bounds(measure, criteria, 1),
                    criterion.max_with_a_region,
                    "of frames with a region",
                    3,
                )
            if criterion.max_tissue_blacked_out is not None:
                failures += _over(
                    f"false positives: {label}",
                    _bounds(
                        measure,
                        criteria,
                        1,
                        share="tissue_blacked_out",
                        wilson=None,
                        bootstrap="tissue_blacked_out_bootstrap",
                    ),
                    criterion.max_tissue_blacked_out,
                    "of tissue blacked out",
                    4,
                )
    return failures


def _over(
    label: str,
    bounds: list[tuple[str, float | None]],
    limit: float,
    what: str,
    digits: int,
) -> list[str]:
    """The failures of the values that exceed a limit, or that are missing
    where an interval is needed."""
    failures = []
    for name, share in bounds:
        if share is None:
            if name:
                failures.append(f"{label}: no {name}interval {what}")
        elif share > limit:
            failures.append(
                f"{label}: {name}{share:.{digits}f} {what}, above {limit:g}"
            )
    return failures


def _missed_failures(
    point: Mapping[str, Any], criteria: AcceptanceCriteria
) -> list[str]:
    failures = []
    rows = point["by"].get("collection+truth", [])
    for criterion in criteria.missed:
        matched = [
            row
            for row in rows
            if row["value"]["collection"].startswith(criterion.collection_prefix)
            and row["value"]["truth"] == criterion.truth
        ]
        if not matched:
            failures.append(
                f"missed: no {criterion.truth} texts of {criterion.collection_prefix}"
            )
        for row in matched:
            missed = row["sensitivity"]["missed"]
            if missed > criterion.max_missed:
                failures.append(
                    f"missed: {row['value']['collection']}: {missed} "
                    f"{criterion.truth} texts missed, above {criterion.max_missed}"
                )
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
