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

- each cell of IOD, contrast, and height in frame pixels that a
  :class:`SensitivityCriterion` matches has at least its share of texts
  fully covered;
- each IOD that a :class:`FalsePositiveCriterion` matches, and each cell of
  that IOD and slice size, has at most its share of frames without text
  with a region, and at most its share of their tissue blacked out; an IOD
  matched without enough frames known to be free of text, or with none,
  fails;
- each tier of the corpus that a :class:`MissedTextCriterion` names has at
  most its number of texts of its truth missed, with none of their ink
  covered;
- no single stratum's share of texts fully covered falls, nor its share of
  frames with a region rises, by more than
  :attr:`AcceptanceCriteria.max_loss` from the baseline point's.

:func:`assess` also gives, for each IOD of the summary, the review that a
point allows its frames (:data:`REVIEW_MODES`): ``"flagged-only"``, where
only the frames that the detector flags need review, for an IOD of an
adoptable detector whose own cell, in the summary's cells by IOD, no
failure is of; and ``"every-frame"`` otherwise, as for any IOD the summary
does not hold. A failure that no single IOD's
cells hold, such as missed texts of a tier or a loss in a stratum of
modality, is taken to be of every IOD. An IOD that fails may still be
cleaned; its frames are only all reviewed.

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

from .text_evaluation import HEIGHT_PX, _label
from .text_evaluation_frames import TIERS, EvaluationRefused
from .text_evaluation_injection import CONTRAST, contrast_label

# The review that frames of an IOD need: only those the detector flags, or
# every one. An IOD that :func:`assess` does not name needs every frame's.
FLAGGED_ONLY = "flagged-only"
EVERY_FRAME = "every-frame"
REVIEW_MODES = (FLAGGED_ONLY, EVERY_FRAME)
# A failure is of one IOD, or, where no single IOD's cells hold it, of all.
_Failure = tuple[str | None, str]

ANY = "*"
# Labels of a bin of a text's height in frame pixels, such as "7 to under
# 10 px" or "40 px or more": the first number is the bin's least height.
_PIXELS = re.compile(r"(\d+(?:\.\d+)?) (?:to under \d+(?:\.\d+)? )?px(?: or more)?")

Labels = str | tuple[str, ...]
# The strata of a sensitivity cell.
_CELL = ("iod", "contrast", "height_px")


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
    contrast, and height in frame pixels that matches.

    Each of ``iod``, ``contrast``, and ``height_px`` is a label, ``"*"`` for
    any, or a tuple of labels, any of which matches. ``min_height_px``,
    where given, matches only cells whose bin of height in frame pixels
    starts at that many or more, whether the text was drawn in pixels or in
    millimetres; it must be an edge of the bins
    (:data:`~.text_evaluation.HEIGHT_PX`) for every text at least that high
    to be judged.
    """

    minimum: float
    iod: Labels = ANY
    contrast: Labels = ANY
    height_px: Labels = ANY
    min_height_px: float | None = None

    def __post_init__(self):
        _check_share("minimum", self.minimum)
        for name in _CELL:
            _check_labels(name, getattr(self, name))

    def matches(self, value: Mapping[str, str]) -> bool:
        """Whether a cell of IOD, contrast, and height is the criterion's."""
        if not all(_matches(getattr(self, name), value[name]) for name in _CELL):
            return False
        if self.min_height_px is None:
            return True
        pixels = _PIXELS.fullmatch(value["height_px"])
        return pixels is not None and float(pixels[1]) >= self.min_height_px


@dataclasses.dataclass(frozen=True)
class FalsePositiveCriterion:
    """The most that frames without text of a matching IOD may show, in
    all and in each bin of slice size: the share with a region, and the
    share of their tissue blacked out.

    With ``iod`` of ``"*"``, ``other_than`` names IODs that the criterion
    does not match, so that a criterion can hold every IOD that no other
    names.
    """

    iod: Labels = ANY
    max_with_a_region: float | None = None
    max_tissue_blacked_out: float | None = None
    other_than: tuple[str, ...] = ()

    def __post_init__(self):
        _check_labels("iod", self.iod)
        if self.other_than:
            _check_labels("other_than", self.other_than)
            if self.iod != ANY:
                raise EvaluationRefused(
                    "Only a criterion of every IOD can leave some out."
                )
        _check_share("max_with_a_region", self.max_with_a_region)
        _check_share("max_tissue_blacked_out", self.max_tissue_blacked_out)

    def matches(self, iod: str) -> bool:
        """Whether the criterion holds frames of ``iod``."""
        return _matches(self.iod, iod) and iod not in self.other_than


@dataclasses.dataclass(frozen=True)
class MissedTextCriterion:
    """The most texts of a truth, in frames of a tier of the corpus, that
    may be missed, with none of their ink covered.

    The counts are read from the summary's cells of tier and truth.
    """

    tier: str
    truth: str = "annotated"
    max_missed: int = 0

    def __post_init__(self):
        if self.tier not in TIERS or self.tier == "none" or self.max_missed < 0:
            raise EvaluationRefused("A missed-text criterion needs a tier.")


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
    "Legacy Converted Enhanced CT Image Storage",
    "Legacy Converted Enhanced MR Image Storage",
    "Legacy Converted Enhanced PET Image Storage",
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
# each IOD and each slice size, with every other image IOD held to the
# stricter 2% until it is given a group, and at most 0.01% of tissue blacked
# out in any; 400 texts and 300 frames at the least in each cell; both intervals'
# bounds; no single stratum 2 percentage points worse than today's
# defaults, the first point; and no text of MIDI-B's answer key, tier T5,
# missed. A text's height is judged in frame pixels, however it was drawn.
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
        FalsePositiveCriterion(
            max_with_a_region=0.02, other_than=TOMOGRAPHIC_IODS + PROJECTION_IODS
        ),
        FalsePositiveCriterion(max_tissue_blacked_out=0.0001),
    ),
    missed=(MissedTextCriterion("T5", truth="annotated", max_missed=0),),
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
    fail and why, whether it could be adopted: never for a benchmark-only
    detector, whatever it meets; and the review that it allows each IOD of
    the summary, as the module describes. It reads only the summary, so it
    can be run again on a published one with other criteria."""
    points = summary["points"]
    if not 0 <= criteria.baseline < len(points):
        raise EvaluationRefused("The baseline must be a point of the summary.")
    baseline = points[criteria.baseline]
    adoptable = summary.get("tier", "adoptable") == "adoptable"
    assessed = []
    for point in points:
        failures = list(dict.fromkeys(_failures(point, baseline, criteria)))
        failed = {iod for iod, _ in failures}
        # An IOD without a cell of its own was not judged whole.
        whole = {row["value"]["iod"] for row in point["by"].get("iod", [])}
        review = {
            iod: FLAGGED_ONLY
            if adoptable and None not in failed and iod in whole - failed
            else EVERY_FRAME
            for iod in _iods(point)
        }
        assessed.append(
            {
                "index": point["index"],
                "meets": not failures,
                "adoptable": adoptable and not failures,
                "failures": list(dict.fromkeys(message for _, message in failures)),
                "review": review,
            }
        )
    return assessed


def _iods(point: Mapping[str, Any]) -> list[str]:
    """The IODs of a point's cells, sorted."""
    found = set()
    for grouping, rows in point["by"].items():
        if "iod" in grouping.split("+"):
            found.update(row["value"]["iod"] for row in rows)
    return sorted(found)


def _failures(
    point: Mapping[str, Any], baseline: Mapping[str, Any], criteria: AcceptanceCriteria
) -> list[_Failure]:
    failures = _sensitivity_failures(point, criteria)
    failures += _unmeasured_failures(point, criteria)
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
) -> list[_Failure]:
    failures: list[_Failure] = []
    cells = point["by"].get("iod+contrast+height_px", [])
    if criteria.sensitivity and not cells:
        failures.append(
            (None, "sensitivity: the summary has no IOD, contrast, and height cells")
        )
    for criterion in criteria.sensitivity:
        for cell in cells:
            value = cell["value"]
            if not criterion.matches(value):
                continue
            measure = cell["sensitivity"]
            label = f"{value['iod']}, {value['contrast']}, {value['height_px']}"
            iod = value["iod"]
            if measure["texts"] == 0 or measure["texts"] < criteria.min_texts:
                failures.append((iod, f"sensitivity: {label}: too few texts"))
                continue
            for name, share in _bounds(measure, criteria, 0):
                if share is None:
                    failures.append((iod, f"sensitivity: {label}: no {name}interval"))
                elif share < criterion.minimum:
                    failures.append(
                        (
                            iod,
                            f"sensitivity: {label}: {name}{share:.3f} "
                            f"below {criterion.minimum:g}",
                        )
                    )
    return failures


# Every label of a sensitivity cell's contrast and height in frame pixels,
# so that a cell that no text reached is known to be missing.
_CONTRASTS = tuple(contrast_label(edge) for edge in CONTRAST)
_HEIGHTS_PX = tuple(_label(HEIGHT_PX, edge) for edge in HEIGHT_PX.edges)


def _unmeasured_failures(
    point: Mapping[str, Any], criteria: AcceptanceCriteria
) -> list[_Failure]:
    """A failure of each IOD of the point for each cell of contrast and
    height that a sensitivity criterion matches but no text reached, so
    that an IOD without texts, such as one whose frames take no injection,
    or without texts of some contrast or height, is not judged on cells it
    lacks."""
    present = {
        tuple(cell["value"][name] for name in _CELL)
        for cell in point["by"].get("iod+contrast+height_px", [])
    }
    failures: list[_Failure] = []
    for iod in _iods(point):
        for criterion in criteria.sensitivity:
            for contrast in _CONTRASTS:
                for height in _HEIGHTS_PX:
                    value = {"iod": iod, "contrast": contrast, "height_px": height}
                    if criterion.matches(value) and (
                        (iod, contrast, height) not in present
                    ):
                        failures.append(
                            (
                                iod,
                                f"sensitivity: {iod}, {contrast}, {height}: no texts",
                            )
                        )
    return failures


def _false_positive_failures(
    point: Mapping[str, Any], criteria: AcceptanceCriteria
) -> list[_Failure]:
    failures: list[_Failure] = []
    # An IOD's own cell fails without frames known to be free of text; a
    # cell of its slice sizes without any is left to the IOD's.
    cells = [(row, row["value"]["iod"], True) for row in point["by"].get("iod", [])]
    cells += [
        (row, f"{row['value']['iod']}, {row['value']['slice_side']}", False)
        for row in point["by"].get("iod+slice_side", [])
    ]
    for criterion in criteria.false_positives:
        for cell, label, whole in cells:
            iod = cell["value"]["iod"]
            if not criterion.matches(iod):
                continue
            measure = cell.get("false_positives", {"frames": 0})
            if measure["frames"] == 0 and not whole:
                continue
            if measure["frames"] < criteria.min_frames:
                failures.append((iod, f"false positives: {label}: too few frames"))
                continue
            if criterion.max_with_a_region is not None:
                failures += _over(
                    iod,
                    f"false positives: {label}",
                    _bounds(measure, criteria, 1),
                    criterion.max_with_a_region,
                    "of frames with a region",
                    3,
                )
            if criterion.max_tissue_blacked_out is not None:
                failures += _over(
                    iod,
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
    # A cell that two criteria match is too thin only once.
    return list(dict.fromkeys(failures))


def _over(  # pylint: disable = too-many-arguments
    iod: str,
    label: str,
    bounds: list[tuple[str, float | None]],
    limit: float,
    what: str,
    digits: int,
) -> list[_Failure]:
    """The failures of the values that exceed a limit, or that are missing
    where an interval is needed."""
    failures: list[_Failure] = []
    for name, share in bounds:
        if share is None:
            if name:
                failures.append((iod, f"{label}: no {name}interval {what}"))
        elif share > limit:
            failures.append(
                (iod, f"{label}: {name}{share:.{digits}f} {what}, above {limit:g}")
            )
    return failures


def _missed_failures(
    point: Mapping[str, Any], criteria: AcceptanceCriteria
) -> list[_Failure]:
    # A tier's texts are of whichever IODs its frames are, so each failure
    # is of every IOD.
    failures: list[_Failure] = []
    rows = point["by"].get("tier+truth", [])
    for criterion in criteria.missed:
        matched = [
            row
            for row in rows
            if row["value"] == {"tier": criterion.tier, "truth": criterion.truth}
        ]
        if not matched or matched[0]["sensitivity"]["texts"] == 0:
            failures.append(
                (None, f"missed: no {criterion.truth} texts of {criterion.tier}")
            )
            continue
        missed = matched[0]["sensitivity"]["missed"]
        if missed > criterion.max_missed:
            failures.append(
                (
                    None,
                    f"missed: {criterion.tier}: {missed} {criterion.truth} texts "
                    f"missed, above {criterion.max_missed}",
                )
            )
    return failures


def _losses(
    point: Mapping[str, Any], baseline: Mapping[str, Any], margin: float
) -> list[_Failure]:
    # A loss in a stratum of one IOD is of that IOD; one in any other
    # stratum, such as a collection or a modality, is of every IOD. A
    # stratum that only one of the two summarises cannot be compared, so
    # it fails rather than passing unjudged.
    failures: list[_Failure] = []
    singles = {name for name in point["by"] if "+" not in name}
    for grouping in sorted(
        singles ^ {name for name in baseline["by"] if "+" not in name}
    ):
        failures.append((None, f"loss: {grouping}: not counted at both points"))
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
            iod = row["value"]["iod"] if grouping == "iod" else None
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
                    (
                        iod,
                        f"loss: {label}: sensitivity {new_share:.3f} "
                        f"from {old_share:.3f}",
                    )
                )
            if "false_positives" not in row:
                continue
            new_fp = row["false_positives"]["share"]
            old_fp = old["false_positives"]["share"]
            if new_fp is not None and old_fp is not None and new_fp > old_fp + margin:
                failures.append(
                    (
                        iod,
                        f"loss: {label}: frames with a region {new_fp:.3f} "
                        f"from {old_fp:.3f}",
                    )
                )
    return failures
