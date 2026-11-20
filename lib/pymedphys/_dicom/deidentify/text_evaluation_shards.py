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

"""The text detector's evaluation (D-056) split across runners in shards,
whose records merge into the run that one runner would have measured.

A run's cases are listed in a fixed order, and each case's subject
(:func:`~.text_evaluation.subject_of`, within its namespace,
:func:`~.text_evaluation.namespace_of`) is numbered by where it first
appears in that list (:func:`case_groups`). Shard ``k`` of ``n`` measures
the cases whose subject's number leaves ``k`` when divided by ``n``
(:func:`shard_positions`), so that a subject's cases, which the bootstrap
resamples together, are all in one shard.

A shard's record (:func:`shard_record`, labelled :data:`SHARD_FORMAT`)
holds every case's subject's number, in the order of the list, and, for
each case it measured, the case's place in the list and its counts:
everything that
:func:`~.text_evaluation.summarise` and
:func:`~.text_evaluation_cases.cases_report` read, and no subject, name,
path, or value read from a file. The numbers come from the order of the
list alone, so a record, which a public repository's runs publish, is
derived from no identifier. :func:`merged` checks that the records are of
one run and hold every case once, and returns the evaluation, with the
cases in their order and each subject named by its number, whose summary
is the one that measuring every case on one runner gives.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any

from .text_evaluation import (
    CaseResult,
    Evaluation,
    EvaluationSettings,
    Tally,
    namespace_of,
    subject_of,
)
from .text_evaluation_frames import EvaluationRefused

SHARD_FORMAT = "pymedphys-deid-text-detector-shard/1"

# The namespace of every merged case's subject, which its number alone
# then names.
_GROUPS = "groups"


def case_groups(cases: Sequence[object]) -> tuple[int, ...]:
    """Each case's subject's number: its place, counting from zero, among
    the run's subjects in the order that each first appears."""
    numbers: dict[tuple[str, str], int] = {}
    return tuple(
        numbers.setdefault((namespace_of(each), subject_of(each)), len(numbers))
        for each in cases
    )


def shard_positions(groups: Sequence[int], shard: int, shards: int) -> list[int]:
    """The places in the list of the cases that shard ``shard`` of
    ``shards`` measures: those whose subject's number leaves ``shard``."""
    if shards < 1 or not 0 <= shard < shards:
        raise EvaluationRefused("A shard must be one of the run's shards.")
    return [place for place, group in enumerate(groups) if group % shards == shard]


def shard_record(
    evaluation: Evaluation,
    positions: Sequence[int],
    groups: Sequence[int],
    *,
    shard: int,
    shards: int,
    run: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """The record of one shard's evaluation, for JSON, as the module
    describes.

    Parameters
    ----------
    evaluation : Evaluation
        Of the shard's cases, in the order of ``positions``.
    positions : sequence of int
        Each case's place in the run's list (:func:`shard_positions`).
    groups : sequence of int
        Every case's subject's number (:func:`case_groups`), of the whole
        list.
    shard, shards : int
    run : mapping, optional
        What else names the run, such as the arguments that chose its
        detector and cases, which every record of it must share.
    """
    if len(positions) != len(evaluation.results):
        raise EvaluationRefused("A shard's record needs each case's place.")
    return {
        "format": SHARD_FORMAT,
        "shard": shard,
        "shards": shards,
        "run": _plain(run or {}),
        "groups": list(groups),
        "detector": _plain(evaluation.detector),
        "settings": _settings_of(evaluation.settings),
        "results": [
            _result_out(result, place, groups[place])
            for place, result in zip(positions, evaluation.results)
        ],
    }


def merged(
    records: Sequence[Mapping[str, Any]], settings: EvaluationSettings
) -> Evaluation:
    """The evaluation of every case of a run measured in shards, as the
    module describes.

    Raises
    ------
    EvaluationRefused
        Unless the records are one of each shard of one run, of the
        settings given, each holds its own shard's cases, and together
        they hold every case of the run once.
    """
    if not records:
        raise EvaluationRefused("A sharded run needs its shards' records.")
    try:
        return _merged(records, settings)
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
        raise EvaluationRefused("Each record must be a shard's record.") from None


def _merged(
    records: Sequence[Mapping[str, Any]], settings: EvaluationSettings
) -> Evaluation:
    first = records[0]
    for record in records:
        if record.get("format") != SHARD_FORMAT:
            raise EvaluationRefused("Each record must be a shard's record.")
        for key in ("shards", "run", "groups", "detector", "settings"):
            if record[key] != first[key]:
                raise EvaluationRefused("The records must be of one run.")
    if any(
        each["group"] % record["shards"] != record["shard"]
        for record in records
        for each in record["results"]
    ):
        raise EvaluationRefused("A shard's record must hold its own cases.")
    if first["settings"] != _settings_of(settings):
        raise EvaluationRefused("The records must be of the settings given.")
    if sorted(record["shard"] for record in records) != list(range(first["shards"])):
        raise EvaluationRefused("A sharded run needs one record of each shard.")
    entries = sorted(
        (each for record in records for each in record["results"]),
        key=lambda each: each["place"],
    )
    groups = first["groups"]
    if [each["place"] for each in entries] != list(range(len(groups))):
        raise EvaluationRefused("The records must hold each case of the run once.")
    if any(each["group"] != groups[each["place"]] for each in entries):
        raise EvaluationRefused("The records must be of one run.")
    return Evaluation(
        settings, dict(first["detector"]), [_result_in(each) for each in entries]
    )


def _settings_of(settings: EvaluationSettings) -> dict[str, Any]:
    """What a summary takes from the settings, by which records of one run
    are known."""
    return _plain(
        {
            "points": [dataclasses.asdict(point) for point in settings.points],
            "plan": None if settings.plan is None else settings.plan.described(),
            "negatives": settings.negatives,
            "evaluated": settings.evaluated,
            "held_out_collections": sorted(settings.held_out_collections),
            "crosses": settings.crosses,
        }
    )


def _result_out(result: CaseResult, place: int, group: int) -> dict[str, Any]:
    return {
        "place": place,
        "group": group,
        "collection": result.collection,
        "split": result.split,
        "evaluated": result.evaluated,
        "crashed": result.crashed,
        "public": result.public,
        "tally": {
            "texts": _table_out(result.tally.texts),
            "frames": _table_out(result.tally.frames),
            "zones": _table_out(result.tally.zones),
            "counts": _table_out(result.tally.counts),
        },
        "clusters": _table_out(result.clusters),
    }


def _result_in(entry: Mapping[str, Any]) -> CaseResult:
    tally = entry["tally"]
    return CaseResult(
        collection=entry["collection"],
        split=entry["split"],
        evaluated=entry["evaluated"],
        tally=Tally(
            texts=_table_in(tally["texts"], list),
            frames=_table_in(tally["frames"], list),
            zones=_table_in(tally["zones"], int),
            counts=_table_in(tally["counts"], int),
        ),
        clusters=_table_in(entry["clusters"], list),
        crashed=entry["crashed"],
        public=entry["public"],
        subject=f"group/{entry['group']}",
        namespace=_GROUPS,
    )


def _table_out(table: Mapping[tuple, Any]) -> list[list[Any]]:
    return [[_plain(key), _plain(value)] for key, value in table.items()]


def _table_in(rows: Sequence[Sequence[Any]], kind: type) -> dict[tuple, Any]:
    return {_tuple(key): kind(value) for key, value in rows}


def _tuple(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tuple(each) for each in value)
    return value


def _plain(value: object) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(each) for key, each in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(each) for each in value]
    return value
