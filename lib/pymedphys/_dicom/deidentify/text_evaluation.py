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

"""Measure the text detector's sensitivity and false positives (D-056).

:func:`evaluate` gives each frame of each case
(:class:`~.text_evaluation_sources.CaseSource`) to an
:class:`~.text_evaluation_detector.EvaluationDetector` once for each pass,
turns its probability maps into the boxes of every point of a
post-processing grid (:func:`~.text_evaluation_detector.grid_boxes`), and
counts, for every point:

sensitivity
    for each piece of text in a frame
    (:class:`~.text_evaluation_frames.BurnedText`), whether the boxes cover
    every pixel of its ink, the pixels whose coverage is more than half
    (**fully covered**, the headline, since any uncovered ink can leak);
    whether they cover every pixel with any coverage; and the share of its
    ink covered;
false positives
    for each frame without text, whether it has a region, how many, the
    share of its pixels blacked out, the share of its tissue
    (:func:`~.text_evaluation_frames.tissue_mask`) blacked out, the share
    of the blacked-out pixels over tissue, and where its regions lie
    (:func:`~.text_evaluation_injection.zone_of`): corners and edges, where
    annotations sit, or the centre;
away from text
    the same for frames with text, counting only the boxes that meet no
    text's zone (:meth:`~.text_evaluation_frames.BurnedText.zone`).

A frame without text is measured as it is (a **negative** pass) and, where
an :class:`~.text_evaluation_injection.InjectionPlan` is given, again with
the plan's text burned in. A frame that already holds text, such as one
whose text an answer key marks, is measured with its text.

Each count is kept overall and by **strata**: the frame's collection, IOD,
modality, slice size, spacing, photometric interpretation, and phantom, and
each text's font, height in pixels and in millimetres, contrast, polarity,
style, orientation, position, content, and zone, singly and in the crosses
that the acceptance criteria need (IOD by contrast by height). Each share
has a Wilson interval; overall and for each IOD, a percentile interval from
a bootstrap that resamples cases, since frames of one case are correlated.

Cases are split (:func:`split_of`) by a rule fixed here: about two-thirds
for tuning and one-third held out, by a SHA-256 of the collection and case,
so that the split needs no list of cases and names none; a collection can
be held out whole. A run evaluates one part, or both.

:func:`summarise` gives the counts, and nothing else, for JSON
(:data:`FORMAT`);
:func:`~.text_evaluation_criteria.assess` checks a summary against
acceptance criteria, which are parameters, set before tuning; none are
built in. A case whose frames raise is counted by the
exception's type and place, never its message, and its frames are dropped.
"""

from __future__ import annotations

import concurrent.futures
import dataclasses
import hashlib
import importlib.metadata
import math
import multiprocessing
import platform
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from pymedphys._imports import numpy as np

from .face_validation import PIXEL_SPACING, SHARE, Bins, crash_site
from .pixel_text_validation import SLICE_SIDE
from .text_detection import TextBox
from .text_evaluation_detector import (
    EvaluationDetector,
    PostProcessing,
    grid_boxes,
)
from .text_evaluation_frames import (
    BurnedText,
    EvaluationFrame,
    EvaluationRefused,
    tissue_mask,
)
from .text_evaluation_injection import InjectionPlan, inject, zone_of
from .text_evaluation_sources import CaseSource, Skipped

FORMAT = "pymedphys-deid-text-detector-evaluation/1"
SPLITS = ("tuning", "held-out")
EVALUATED = (*SPLITS, "all")
SPLIT_SALT = "pymedphys-text-detector-evaluation-split/1"
SPLIT_RULE = (
    "A case is held out where the first 8 bytes of the SHA-256 of "
    f"'{SPLIT_SALT}', its collection, and its case, joined by NUL, read as "
    "a big-endian integer, are a multiple of 3, or its collection is held "
    "out whole; otherwise it is for tuning."
)
FRAME_DIMENSIONS = (
    "collection",
    "iod",
    "modality",
    "slice_side",
    "pixel_spacing",
    "photometric",
    "background",
)
TEXT_DIMENSIONS = (
    "font",
    "height",
    "height_mm",
    "contrast",
    "contrast_drawn",
    "polarity",
    "style",
    "orientation",
    "position",
    "content",
    "zone",
)
# The crosses of strata that the acceptance criteria read.
CROSSES = (("iod", "contrast", "height"),)
# A text's ink is its pixels of more coverage than this.
INK_LEVEL = 0.5
HEIGHT_MM = Bins("mm", (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 7.5, 10.0, 15.0))
FRAME_AREA = Bins(
    "share of the frame",
    (0.0, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2),
)
# Each case's counts that the bootstrap resamples, by position.
_CLUSTER_FIELDS = (
    "texts",
    "fully_covered",
    "frames",
    "frames_with_a_region",
    "tissue",
    "tissue_blacked_out",
)
_KINDS = ("negative", "away")
_Z = 1.959963984540054


def split_of(
    collection: str, case: str, held_out_collections: Iterable[str] = ()
) -> str:
    """The part of the split that a case belongs to, by :data:`SPLIT_RULE`."""
    if collection in set(held_out_collections):
        return "held-out"
    digest = hashlib.sha256("\0".join((SPLIT_SALT, collection, case)).encode()).digest()
    return "held-out" if int.from_bytes(digest[:8], "big") % 3 == 0 else "tuning"


@dataclasses.dataclass(frozen=True)
class EvaluationSettings:
    """What :func:`evaluate` measures.

    Attributes
    ----------
    points : tuple of PostProcessing
        The grid; its first point is the baseline that the criteria compare
        others with, by default.
    plan : InjectionPlan or None
        The text to burn into frames without text; None burns none.
    negatives : bool
        Whether frames without text are also measured as they are.
    evaluated : str
        ``"tuning"``, ``"held-out"``, or ``"all"``: which part of the split
        is evaluated.
    held_out_collections : tuple of str
        Collections held out whole.
    crosses : tuple of tuple of str
        Crosses of strata to count, beside each stratum singly.
    """

    points: tuple[PostProcessing, ...]
    plan: InjectionPlan | None = None
    negatives: bool = True
    evaluated: str = "tuning"
    held_out_collections: tuple[str, ...] = ()
    crosses: tuple[tuple[str, ...], ...] = CROSSES

    def __post_init__(self):
        if not self.points:
            raise EvaluationRefused("The grid must have a point.")
        if self.evaluated not in EVALUATED:
            raise EvaluationRefused("The part evaluated must be a known one.")
        known = set(FRAME_DIMENSIONS) | set(TEXT_DIMENSIONS)
        if not all(cross and set(cross) <= known for cross in self.crosses):
            raise EvaluationRefused("A cross must be of known strata.")
        if not (self.negatives or self.plan is not None):
            raise EvaluationRefused("Something must be measured.")

    @property
    def dimensions(self) -> tuple[tuple[str, ...], ...]:
        """Every grouping counted: overall, each stratum, and the crosses."""
        singles = tuple((each,) for each in (*FRAME_DIMENSIONS, *TEXT_DIMENSIONS))
        return ((), *singles, *self.crosses)


@dataclasses.dataclass
class Tally:
    """Counts, which merge by adding; for :func:`summarise` alone.

    Keys of ``texts`` are a point's index, a grouping, and its values; of
    ``frames``, also the kind (``"negative"`` or ``"away"``). Each value of
    ``texts`` is the texts, those fully covered, those fully covered with
    any coverage, then the texts in each bin of :data:`SHARE` by the share
    of ink covered; of ``frames``, the frames, those with a region, the
    regions, the pixels, those blacked out, the tissue, the tissue blacked
    out, then the frames with a region in each bin of :data:`FRAME_AREA`.
    """

    texts: dict[tuple, list[int]] = dataclasses.field(default_factory=dict)
    frames: dict[tuple, list[int]] = dataclasses.field(default_factory=dict)
    zones: dict[tuple, int] = dataclasses.field(default_factory=dict)
    counts: dict[tuple, int] = dataclasses.field(default_factory=dict)

    def add(self, other: Tally) -> None:
        for mine, theirs in (
            (self.texts, other.texts),
            (self.frames, other.frames),
        ):
            for key, values in theirs.items():
                if key in mine:
                    mine[key] = [a + b for a, b in zip(mine[key], values)]
                else:
                    mine[key] = list(values)
        for mine_counts, their_counts in (
            (self.zones, other.zones),
            (self.counts, other.counts),
        ):
            for key, value in their_counts.items():
                mine_counts[key] = mine_counts.get(key, 0) + value

    def count(self, *key: str, by: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + by


@dataclasses.dataclass
class CaseResult:
    """One case's counts, with no name of it.

    Attributes
    ----------
    collection : str
    split : str
    evaluated : bool
        Whether its part of the split was evaluated.
    tally : Tally
    clusters : dict
        By ``(point, iod)``, ``iod`` None for all, the counts of
        :data:`_CLUSTER_FIELDS`, for the bootstrap.
    crashed : str or None
        Where its frames raised, if they did.
    """

    collection: str
    split: str
    evaluated: bool
    tally: Tally = dataclasses.field(default_factory=Tally)
    clusters: dict[tuple, list[int]] = dataclasses.field(default_factory=dict)
    crashed: str | None = None


@dataclasses.dataclass
class Evaluation:
    """Every case's results, in the order of the cases, and what made them."""

    settings: EvaluationSettings
    detector: Mapping[str, object]
    results: list[CaseResult]


def evaluate(
    cases: Sequence[CaseSource],
    detector: Callable[[], EvaluationDetector],
    settings: EvaluationSettings,
    *,
    workers: int = 1,
) -> Evaluation:
    """Measure the cases, as the module describes.

    Parameters
    ----------
    cases : sequence of CaseSource
        Picklable where ``workers`` is more than one.
    detector : callable
        Makes the detector; called once in each worker, so picklable where
        ``workers`` is more than one, as a class or a
        :func:`functools.partial` of one is.
    settings : EvaluationSettings
    workers : int
        Processes that measure the cases; one measures them here.
    """
    if workers < 1:
        raise EvaluationRefused("There must be at least one worker.")
    made = detector()
    method = dict(made.method)
    if workers == 1:
        results = [_case(each, made, settings) for each in cases]
        return Evaluation(settings, method, results)
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=_start_worker,
        initargs=(detector,),
    ) as pool:
        results = list(pool.map(_case_in_worker, cases, [settings] * len(cases)))
    return Evaluation(settings, method, results)


_WORKER: dict[str, EvaluationDetector] = {}


def _start_worker(detector: Callable[[], EvaluationDetector]) -> None:
    _WORKER["detector"] = detector()


def _case_in_worker(source: CaseSource, settings: EvaluationSettings) -> CaseResult:
    return _case(source, _WORKER["detector"], settings)


def _case(
    source: CaseSource, detector: EvaluationDetector, settings: EvaluationSettings
) -> CaseResult:
    split = split_of(source.collection, source.case, settings.held_out_collections)
    evaluated = settings.evaluated in ("all", split)
    result = CaseResult(source.collection, split, evaluated)
    if not evaluated:
        return result
    try:
        for item in source.read():
            if isinstance(item, Skipped):
                result.tally.count("skipped", item.reason)
                continue
            _frame(item, detector, settings, result)
    # A case that raises is counted by where, and its counts dropped; the
    # message, which could quote a value, is never kept.
    except Exception as error:  # pylint: disable = broad-exception-caught
        return CaseResult(
            source.collection, split, evaluated, crashed=crash_site(error)
        )
    return result


def _frame(
    frame: EvaluationFrame,
    detector: EvaluationDetector,
    settings: EvaluationSettings,
    result: CaseResult,
) -> None:
    tally = result.tally
    strata = frame_strata(frame)
    tally.count("frames", strata["iod"])
    tissue = tissue_mask(frame)
    points = settings.points
    if frame.texts:
        _measure(frame, detector, points, tissue, strata, settings, result)
        return
    if settings.negatives:
        _measure(frame, detector, points, tissue, strata, settings, result)
    if settings.plan is None:
        return
    if frame.rgb:
        tally.count("not-injected", "rgb")
        return
    injected = inject(frame, settings.plan)
    for reason, count in injected.not_placed.items():
        tally.count("not-placed", reason, by=count)
    if injected.frame.texts:
        _measure(injected.frame, detector, points, tissue, strata, settings, result)


def frame_strata(frame: EvaluationFrame) -> dict[str, str]:
    """A frame's strata, as the module lists them, never a value of it."""
    return {
        "collection": frame.collection,
        "iod": frame.iod,
        "modality": frame.modality,
        "slice_side": _label(SLICE_SIDE, max(frame.shape)),
        "pixel_spacing": (
            "unknown"
            if frame.pixel_spacing is None
            else _label(PIXEL_SPACING, frame.pixel_spacing)
        ),
        "photometric": frame.photometric,
        "background": frame.background or "none",
    }


def _label(bins: Bins, value: float) -> str:
    edges = bins.counts(())["bins"][bins.index(value)]
    low, high = edges["from"], edges["to"]
    if low is None:
        return f"below {high:g} {bins.unit}"
    if high is None:
        return f"{low:g} {bins.unit} or more"
    return f"{low:g} to under {high:g} {bins.unit}"


@dataclasses.dataclass(frozen=True)
class _Covered:
    """What one set of boxes blacks out of a frame."""

    texts: tuple[tuple[bool, bool, float], ...]
    regions: int
    blacked_out: int
    tissue_blacked_out: int
    zones: tuple[str, ...]


def _measure(
    frame: EvaluationFrame,
    detector: EvaluationDetector,
    points: Sequence[PostProcessing],
    tissue: np.ndarray,
    strata: Mapping[str, str],
    settings: EvaluationSettings,
    result: CaseResult,
) -> None:
    boxes_of_points = grid_boxes(detector.probabilities(frame), points)
    shape = frame.shape
    inks = [(text.ink(shape, INK_LEVEL), text.ink(shape, 0.0)) for text in frame.texts]
    zones = np.zeros(shape, bool)
    zone_boxes = [text.zone(shape) for text in frame.texts]
    for zone in zone_boxes:
        zones[zone.top : zone.bottom, zone.left : zone.right] = True
    kind = "away" if frame.texts else "negative"
    text_strata = [_text_strata(text, frame, strata) for text in frame.texts]
    pixels = shape[0] * shape[1]
    tissue_pixels = int(np.count_nonzero(tissue))
    groupings = settings.dimensions
    measured: dict[tuple[TextBox, ...], _Covered] = {}
    tally = result.tally
    for index, boxes in enumerate(boxes_of_points):
        if boxes not in measured:
            measured[boxes] = _covered(boxes, inks, zone_boxes, zones, tissue)
        covered = measured[boxes]
        for each, (full, full_any, share) in zip(text_strata, covered.texts):
            row = [1, int(full), int(full_any)] + [0] * len(SHARE.edges)
            row[3 + SHARE.index(share)] = 1
            for grouping in groupings:
                key = (
                    index,
                    grouping,
                    tuple(each.get(name, "none") for name in grouping),
                )
                _added(tally.texts, key, row)
            _cluster(result, index, strata["iod"], [1, int(full), 0, 0, 0, 0])
        area = covered.blacked_out / pixels
        row = [
            1,
            int(covered.regions > 0),
            covered.regions,
            pixels,
            covered.blacked_out,
            tissue_pixels,
            covered.tissue_blacked_out,
        ] + [0] * len(FRAME_AREA.edges)
        if covered.regions:
            row[7 + FRAME_AREA.index(area)] = 1
        for grouping in groupings:
            if any(name in TEXT_DIMENSIONS for name in grouping):
                continue
            key = (index, kind, grouping, tuple(strata[name] for name in grouping))
            _added(tally.frames, key, row)
        if kind == "negative":
            _cluster(
                result,
                index,
                strata["iod"],
                [
                    0,
                    0,
                    1,
                    int(covered.regions > 0),
                    tissue_pixels,
                    covered.tissue_blacked_out,
                ],
            )
        for zone in covered.zones:
            key = (index, kind, zone)
            tally.zones[key] = tally.zones.get(key, 0) + 1


def _added(table: dict[tuple, list[int]], key: tuple, row: Sequence[int]) -> None:
    existing = table.get(key)
    if existing is None:
        table[key] = list(row)
    else:
        for position, value in enumerate(row):
            existing[position] += value


def _cluster(result: CaseResult, point: int, iod: str, row: Sequence[int]) -> None:
    for key in ((point, None), (point, iod)):
        _added(result.clusters, key, row)


def _text_strata(
    text: BurnedText, frame: EvaluationFrame, strata: Mapping[str, str]
) -> dict[str, str]:
    found = {**strata, **{name: "none" for name in TEXT_DIMENSIONS}}
    found.update(
        {key: value for key, value in text.strata.items() if key in TEXT_DIMENSIONS}
    )
    if frame.pixel_spacing is not None:
        found["height_mm"] = _label(HEIGHT_MM, text.height * frame.pixel_spacing)
    else:
        found["height_mm"] = "unknown"
    if found["zone"] == "none":
        found["zone"] = zone_of(text.extent, frame.shape)
    return found


def _covered(
    boxes: Sequence[TextBox],
    inks: Sequence[tuple[np.ndarray, np.ndarray]],
    zone_boxes: Sequence[TextBox],
    zones: np.ndarray,
    tissue: np.ndarray,
) -> _Covered:
    shape = tissue.shape
    covered = np.zeros(shape, bool)
    for box in boxes:
        covered[box.top : box.bottom, box.left : box.right] = True
    texts = []
    for core, any_ink in inks:
        ink = core if core.any() else any_ink
        hits = covered[ink]
        texts.append(
            (
                bool(hits.all()),
                bool(covered[any_ink].all()),
                float(hits.mean()) if hits.size else 0.0,
            )
        )
    away = [box for box in boxes if not any(_meet(box, zone) for zone in zone_boxes)]
    blacked = np.zeros(shape, bool)
    for box in away:
        blacked[box.top : box.bottom, box.left : box.right] = True
    blacked &= ~zones
    return _Covered(
        texts=tuple(texts),
        regions=len(away),
        blacked_out=int(np.count_nonzero(blacked)),
        tissue_blacked_out=int(np.count_nonzero(blacked & tissue)),
        zones=tuple(zone_of(box, shape) for box in away),
    )


def _meet(first: TextBox, second: TextBox) -> bool:
    return (
        first.top < second.bottom
        and second.top < first.bottom
        and first.left < second.right
        and second.left < first.right
    )


def wilson(successes: int, trials: int) -> tuple[float, float] | None:
    """The 95% Wilson score interval of a share, or None without trials."""
    if trials <= 0:
        return None
    share = successes / trials
    z2 = _Z * _Z
    denominator = 1 + z2 / trials
    centre = (share + z2 / (2 * trials)) / denominator
    half = (
        _Z
        * math.sqrt(share * (1 - share) / trials + z2 / (4 * trials * trials))
        / denominator
    )
    return (max(0.0, centre - half), min(1.0, centre + half))


def cluster_bootstrap(
    numerators: np.ndarray,
    denominators: np.ndarray,
    *,
    replicates: int,
    seed: int,
) -> tuple[float, float] | None:
    """The 95% percentile interval of a ratio of sums, resampling clusters
    with replacement; None with fewer than two clusters that count."""
    numerators = np.asarray(numerators, dtype=np.float64)
    denominators = np.asarray(denominators, dtype=np.float64)
    counted = denominators > 0
    if int(np.count_nonzero(counted)) < 2 or replicates < 1:
        return None
    numerators, denominators = numerators[counted], denominators[counted]
    rng = np.random.default_rng(seed)
    chosen = rng.integers(0, numerators.size, size=(replicates, numerators.size))
    ratios = numerators[chosen].sum(axis=1) / denominators[chosen].sum(axis=1)
    low, high = np.percentile(ratios, [2.5, 97.5])
    return (float(low), float(high))


def _seed(*parts: object) -> int:
    digest = hashlib.sha256("\0".join(str(each) for each in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def summarise(
    evaluation: Evaluation,
    *,
    replicates: int = 2000,
    detailed: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Return the evaluation's counts, as the module describes, for JSON.

    Parameters
    ----------
    evaluation : Evaluation
    replicates : int
        The bootstrap's replicates.
    detailed : sequence of int, optional
        The points whose counts are given by every stratum; the others are
        given overall, by IOD, and by the crosses. By default every point
        where the grid has ten or fewer, otherwise the first.
    """
    settings = evaluation.settings
    points = settings.points
    if detailed is None:
        detailed = range(len(points)) if len(points) <= 10 else (0,)
    detailed = set(detailed)
    tally = Tally()
    evaluated = [each for each in evaluation.results if each.evaluated]
    for each in evaluated:
        tally.add(each.tally)
    clusters = [each.clusters for each in evaluated if each.crashed is None]
    return {
        "format": FORMAT,
        "software": _software(),
        "detector": _plain(evaluation.detector),
        "plan": None if settings.plan is None else settings.plan.described(),
        "negatives": settings.negatives,
        "split": {
            "rule": SPLIT_RULE,
            "evaluated": settings.evaluated,
            "held_out_collections": sorted(settings.held_out_collections),
            "cases": {
                part: sum(each.split == part for each in evaluation.results)
                for part in SPLITS
            },
        },
        "collections": _collections(evaluation.results),
        "frames": _counted(tally, "frames"),
        "skipped": _counted(tally, "skipped"),
        "not_placed": _counted(tally, "not-placed"),
        "not_injected": _counted(tally, "not-injected"),
        "points": [
            _point(
                index, point, tally, clusters, settings, replicates, index in detailed
            )
            for index, point in enumerate(points)
        ],
    }


def _collections(results: Sequence[CaseResult]) -> dict[str, Any]:
    found: dict[str, dict[str, Any]] = {}
    for each in results:
        entry = found.setdefault(
            each.collection,
            {"cases": 0, "evaluated": 0, "crashed": {}},
        )
        entry["cases"] += 1
        entry["evaluated"] += int(each.evaluated and each.crashed is None)
        if each.crashed is not None:
            entry["crashed"][each.crashed] = entry["crashed"].get(each.crashed, 0) + 1
    return {name: found[name] for name in sorted(found)}


def _counted(tally: Tally, kind: str) -> dict[str, int]:
    return dict(
        sorted((key[1], value) for key, value in tally.counts.items() if key[0] == kind)
    )


def _point(
    index: int,
    point: PostProcessing,
    tally: Tally,
    clusters: Sequence[Mapping[tuple, list[int]]],
    settings: EvaluationSettings,
    replicates: int,
    detailed: bool,
) -> dict[str, Any]:
    groupings = [
        grouping
        for grouping in settings.dimensions
        if grouping
        and (detailed or grouping == ("iod",) or grouping in settings.crosses)
    ]
    entry: dict[str, Any] = {
        "index": index,
        "post_processing": point.described(),
        **_measures(index, (), (), tally),
        "zones": {
            kind: {
                zone: tally.zones.get((index, kind, zone), 0)
                for zone in ("corner", "edge", "centre")
            }
            for kind in _KINDS
        },
        "by": {},
    }
    _intervals(entry, index, None, clusters, replicates)
    for grouping in groupings:
        values = sorted(
            {key[2] for key in tally.texts if key[0] == index and key[1] == grouping}
            | {
                key[3] for key in tally.frames if key[0] == index and key[2] == grouping
            },
            key=_in_order,
        )
        # A frame has no text dimension, so a grouping with one counts only
        # texts; its frames' measures would be empty, not zero.
        per_text = any(name in TEXT_DIMENSIONS for name in grouping)
        rows = []
        for value in values:
            row = {
                "value": dict(zip(grouping, value)),
                **_measures(index, grouping, value, tally),
            }
            if per_text:
                del row["false_positives"], row["away_from_text"]
            if grouping == ("iod",):
                _intervals(row, index, value[0], clusters, replicates)
            rows.append(row)
        entry["by"]["+".join(grouping)] = rows
    return entry


_NUMBER = re.compile(r"(\d+(?:\.\d+)?)")


def _in_order(value: tuple) -> tuple:
    """Order a stratum's labels by the numbers in them, so that bins of
    contrast, height, or spacing read from low to high."""
    return tuple(
        tuple(
            (0, float(part), "") if position % 2 else (1, 0.0, part)
            for position, part in enumerate(_NUMBER.split(str(each)))
        )
        for each in value
    )


def _measures(
    index: int, grouping: tuple[str, ...], value: tuple, tally: Tally
) -> dict[str, Any]:
    texts = tally.texts.get((index, grouping, value))
    found: dict[str, Any] = {"sensitivity": _sensitivity(texts)}
    for kind, name in (("negative", "false_positives"), ("away", "away_from_text")):
        found[name] = _false_positives(tally.frames.get((index, kind, grouping, value)))
    return found


def _sensitivity(row: Sequence[int] | None) -> dict[str, Any]:
    row = list(row) if row is not None else [0, 0, 0] + [0] * len(SHARE.edges)
    texts, full, full_any = row[:3]
    bins = SHARE.counts(())
    for position, each in enumerate(bins["bins"]):
        each["count"] = row[3 + position]
    return {
        "texts": texts,
        "fully_covered": full,
        "share": full / texts if texts else None,
        "wilson": _pair(wilson(full, texts)),
        "fully_covered_any_ink": full_any,
        "ink_covered": bins,
    }


def _false_positives(row: Sequence[int] | None) -> dict[str, Any]:
    row = list(row) if row is not None else [0] * (7 + len(FRAME_AREA.edges))
    frames, with_region, regions, pixels, blacked, tissue, tissue_blacked = row[:7]
    bins = FRAME_AREA.counts(())
    for position, each in enumerate(bins["bins"]):
        each["count"] = row[7 + position]
    return {
        "frames": frames,
        "with_a_region": with_region,
        "share": with_region / frames if frames else None,
        "wilson": _pair(wilson(with_region, frames)),
        "regions": regions,
        "pixels_blacked_out": blacked / pixels if pixels else None,
        "tissue_blacked_out": tissue_blacked / tissue if tissue else None,
        "blacked_out_over_tissue": tissue_blacked / blacked if blacked else None,
        "area_of_frames_with_a_region": bins,
    }


def _intervals(
    entry: dict[str, Any],
    index: int,
    iod: str | None,
    clusters: Sequence[Mapping[tuple, list[int]]],
    replicates: int,
) -> None:
    """Add the bootstrap's intervals over cases to an entry's shares."""
    rows = np.array(
        [each.get((index, iod), [0] * len(_CLUSTER_FIELDS)) for each in clusters],
        dtype=np.float64,
    ).reshape(-1, len(_CLUSTER_FIELDS))
    seed = _seed(FORMAT, index, iod)
    entry["sensitivity"]["bootstrap"] = _pair(
        cluster_bootstrap(rows[:, 1], rows[:, 0], replicates=replicates, seed=seed)
    )
    entry["false_positives"]["bootstrap"] = _pair(
        cluster_bootstrap(rows[:, 3], rows[:, 2], replicates=replicates, seed=seed + 1)
    )
    entry["false_positives"]["tissue_blacked_out_bootstrap"] = _pair(
        cluster_bootstrap(rows[:, 5], rows[:, 4], replicates=replicates, seed=seed + 2)
    )


def _pair(interval: tuple[float, float] | None) -> list[float] | None:
    return None if interval is None else [interval[0], interval[1]]


def _software() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for package in ("pymedphys", "numpy", "scipy", "pydicom", "onnxruntime", "pillow"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unknown"
    return versions


def _plain(value: object) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(each) for key, each in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(each) for each in value]
    return value
