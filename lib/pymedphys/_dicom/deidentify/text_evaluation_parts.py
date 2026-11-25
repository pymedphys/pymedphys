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

"""The text detector's evaluation (D-056) in worker processes, a large case
in parts.

Each worker measures one task at a time, and each case is at least one
task, so a case much larger than the rest would keep one worker busy long
after the others had finished. Given each case's weight, about how long it
takes to measure (:func:`~.text_evaluation_shards.case_weight`), a case
heavier than the workers' fair share of the whole is cut into parts
(:func:`parts_of`): part ``k`` of ``n`` measures the case's items ``k``,
``k + n``, ``k + 2n``, and so on, still reading every item, and the parts
start heaviest first. A part counts its own items as one measure of the
whole case would; each frame's injected text depends on its case and
number alone (:func:`~.text_evaluation_injection.frame_rng`), not on the
frames measured before it, and every count adds. So the parts' counts,
added (:func:`joined`), are the case's counts, and a case that raises is
counted by where one measure of it would first have raised.
"""

from __future__ import annotations

import concurrent.futures
import dataclasses
import multiprocessing
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from .text_evaluation_frames import EvaluationRefused

if TYPE_CHECKING:
    from .text_evaluation import CaseResult, EvaluationSettings, MeasuredDetector
    from .text_evaluation_sources import CaseSource

    # A part of a case, as text_evaluation measures it: its result and
    # where it raised, if it did.
    CasePart = Callable[
        [CaseSource, MeasuredDetector, EvaluationSettings, int, int],
        tuple[CaseResult, int | None],
    ]


def check_workers(cases: int, workers: int, weights: Sequence[float] | None) -> None:
    """Refuse fewer than one worker, or weights that are not one a case."""
    if workers < 1:
        raise EvaluationRefused("There must be at least one worker.")
    if weights is not None and len(weights) != cases:
        raise EvaluationRefused("Every case needs a weight.")


def parts_of(weights: Sequence[float], workers: int) -> list[tuple[int, int, int]]:
    """The tasks that measure cases of these weights with this many workers:
    for each, the case's place, the part, and the case's parts, the
    heaviest parts first, and among equals the earlier case and part.

    A case of more than the workers' fair share of the whole is cut into
    as many parts as it holds fair shares, rounded up, and at most one for
    each worker; every other case is one part.
    """
    if workers < 1:
        raise EvaluationRefused("There must be at least one worker.")
    total = sum(weights)
    share = total / workers
    tasks = []
    for place, weight in enumerate(weights):
        parts = min(workers, -(-weight // share)) if 0 < share < weight else 1
        tasks.extend((place, part, int(parts)) for part in range(int(parts)))
    return sorted(
        tasks,
        key=lambda task: (-weights[task[0]] / task[2], task[0], task[1]),
    )


def measured_in_workers(
    cases: Sequence[CaseSource],
    detector: Callable[[], MeasuredDetector],
    settings: EvaluationSettings,
    *,
    workers: int,
    weights: Sequence[float] | None,
    case_part: CasePart,
) -> list[CaseResult]:
    """Every case's result, in the order of the cases, measured by
    ``case_part`` in this many worker processes: a case to a task without
    weights, and as :func:`parts_of` cuts them with one weight a case."""
    check_workers(len(cases), workers, weights)
    tasks = (
        [(place, 0, 1) for place in range(len(cases))]
        if weights is None
        else parts_of(weights, workers)
    )
    found: dict[int, list[tuple[int, CaseResult, int | None]]] = {}
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=_start_worker,
        initargs=(detector, case_part),
    ) as pool:
        done = pool.map(
            _part_in_worker,
            [cases[place] for place, _, _ in tasks],
            [settings] * len(tasks),
            [part for _, part, _ in tasks],
            [parts for _, _, parts in tasks],
        )
        for (place, part, _), (result, raised_at) in zip(tasks, done):
            found.setdefault(place, []).append((part, result, raised_at))
    return [joined(found[place]) for place in range(len(cases))]


_WORKER: dict[str, Any] = {}


def _start_worker(
    detector: Callable[[], MeasuredDetector], case_part: CasePart
) -> None:
    _WORKER["detector"] = detector()
    _WORKER["case_part"] = case_part


def _part_in_worker(
    source: CaseSource, settings: EvaluationSettings, part: int, parts: int
) -> tuple[CaseResult, int | None]:
    return _WORKER["case_part"](source, _WORKER["detector"], settings, part, parts)


def joined(found: Sequence[tuple[int, CaseResult, int | None]]) -> CaseResult:
    """A case's result from its parts' results, each with its part and
    where it raised, if it did: the result of the part that raised where one
    measure of the whole case would first have met it, or else every part's
    counts, added."""
    ordered = sorted(found, key=lambda each: each[0])
    if len(ordered) == 1:
        return ordered[0][1]
    raised = [(at, part, result) for part, result, at in ordered if at is not None]
    if raised:
        return min(raised, key=lambda each: (each[0], each[1]))[2]
    first = ordered[0][1]
    whole = dataclasses.replace(first, tally=type(first.tally)(), clusters={})
    for _, result, _ in ordered:
        whole.tally.add(result.tally)
        for key, row in result.clusters.items():
            existing = whole.clusters.setdefault(key, [0] * len(row))
            for position, value in enumerate(row):
                existing[position] += value
    return whole
