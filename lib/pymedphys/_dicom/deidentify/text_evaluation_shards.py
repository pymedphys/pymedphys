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
appears in that list (:func:`case_groups`). Each subject goes to one
shard, so that its cases, which the bootstrap resamples together, are
measured together: the subjects are taken from the heaviest down, by the
frames that their cases' files hold (:func:`case_weight`), each to the
shard least loaded so far (:func:`shard_positions`), so that the shards'
measurements take about as long as each other. The frames are read from
the files' headers alone, which every shard reads alike, so every shard
of a run places every subject in the same shard.

A shard's record (:func:`shard_record`, labelled :data:`SHARD_FORMAT`)
holds what :func:`~.text_evaluation.summary_of` and
:func:`~.text_evaluation_cases.cases_report` read, and no subject, name,
path, or value read from a file. Of the cases that the per-case report
names (:func:`~.text_evaluation_cases.reported`), it gives each one's
place in the list and its counts, as the report does. Of every other
case, which the report only counts as withheld, it gives nothing case by
case: only the shard's totals (:class:`~.text_evaluation.Totals`), its
subjects' clusters among them, each table in the order of its own keys and
the clusters in the order of their own counts, and the number withheld; so
nothing in it follows from such a case's place in the list or its
subject, and reordering or renaming those cases leaves the record as it
is. The bootstrap takes no order from its clusters, so the summary of the
merged totals is the one that measuring every case on one runner gives.
:func:`merged` checks that the records are of one run and hold every case
once.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pymedphys._imports import pydicom

from .text_evaluation import (
    SPLITS,
    CaseResult,
    Evaluation,
    EvaluationSettings,
    Tally,
    Totals,
    namespace_of,
    subject_of,
    totals,
)
from .text_evaluation_cases import reported
from .text_evaluation_converted import ConvertedCase
from .text_evaluation_frames import EvaluationRefused
from .text_evaluation_idc import IdcSeriesCase
from .text_evaluation_sources import DicomCase

SHARD_FORMAT = "pymedphys-deid-text-detector-shard/1"


@dataclasses.dataclass
class Merged:
    """A run measured in shards, merged.

    Attributes
    ----------
    settings : EvaluationSettings
    detector : mapping
        The detector's method.
    totals : Totals
        Of every case.
    named : Evaluation
        Of the cases that the per-case report names, in their order.
    withheld : int
        The other cases.
    """

    settings: EvaluationSettings
    detector: Mapping[str, object]
    totals: Totals
    named: Evaluation
    withheld: int


def case_groups(cases: Sequence[object]) -> tuple[int, ...]:
    """Each case's subject's number: its place, counting from zero, among
    the run's subjects in the order that each first appears."""
    numbers: dict[tuple[str, str], int] = {}
    return tuple(
        numbers.setdefault((namespace_of(each), subject_of(each)), len(numbers))
        for each in cases
    )


def shard_positions(
    groups: Sequence[int],
    shard: int,
    shards: int,
    weights: Sequence[int] | None = None,
) -> list[int]:
    """The places in the list of the cases that shard ``shard`` of
    ``shards`` measures.

    Each subject, with its cases' weights summed (one a case where
    ``weights`` is None), is taken from the heaviest down, and the lowest
    numbered first among equals, and goes to the shard of least weight so
    far, the lowest numbered first among equals.
    """
    if shards < 1 or not 0 <= shard < shards:
        raise EvaluationRefused("A shard must be one of the run's shards.")
    if weights is None:
        weights = [1] * len(groups)
    if len(weights) != len(groups):
        raise EvaluationRefused("A shard needs each case's weight.")
    subjects: dict[int, int] = {}
    for group, weight in zip(groups, weights):
        subjects[group] = subjects.get(group, 0) + weight
    loads = [0] * shards
    owners: dict[int, int] = {}
    for group in sorted(subjects, key=lambda each: (-subjects[each], each)):
        lightest = min(range(shards), key=lambda each: (loads[each], each))
        owners[group] = lightest
        loads[lightest] += subjects[group]
    return [place for place, group in enumerate(groups) if owners[group] == shard]


def case_weight(case: object) -> int:
    """About how long a case takes to measure: the frames that its files
    hold, as their headers give them, a file that is not DICOM counting as
    one, and at least one a case."""
    return max(1, sum(_frames(path) for path in _files(case)))


def _files(case: object) -> Iterable[pathlib.Path]:
    if isinstance(case, ConvertedCase):
        case = case.source
    if isinstance(case, DicomCase):
        return [pathlib.Path(path) for path in case.paths]
    if isinstance(case, IdcSeriesCase):
        found = pathlib.Path(case.folder) / case.series.crdc_series_uuid
        if not found.is_dir():
            return []
        return sorted(path for path in found.rglob("*") if path.is_file())
    return []


def _frames(path: pathlib.Path) -> int:
    try:
        found = pydicom.dcmread(
            path, stop_before_pixels=True, specific_tags=["NumberOfFrames"]
        )
        return max(1, int(found.get("NumberOfFrames", 1) or 1))
    except (OSError, pydicom.errors.InvalidDicomError, EOFError, ValueError, TypeError):
        return 1


def shard_record(
    evaluation: Evaluation,
    positions: Sequence[int],
    cases: int,
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
    cases : int
        The cases in the run's list.
    shard, shards : int
    run : mapping, optional
        What else names the run, such as the arguments that chose its
        detector and cases, which every record of it must share.
    """
    if len(positions) != len(evaluation.results):
        raise EvaluationRefused("A shard's record needs each case's place.")
    named = [
        (place, result)
        for place, result in zip(positions, evaluation.results)
        if reported(result.public) is not None
    ]
    return {
        "format": SHARD_FORMAT,
        "shard": shard,
        "shards": shards,
        "cases": cases,
        "run": _plain(run or {}),
        "detector": _plain(evaluation.detector),
        "settings": _settings_of(evaluation.settings),
        "totals": _totals_out(totals(evaluation.results)),
        "named": [_named_out(result, place) for place, result in named],
        "withheld": len(evaluation.results) - len(named),
    }


def merged(
    records: Sequence[Mapping[str, Any]], settings: EvaluationSettings
) -> Merged:
    """Every shard's record of a run, merged, as the module describes.

    Raises
    ------
    EvaluationRefused
        Unless the records are one of each shard of one run, of the
        settings given, and together hold every case of it once.
    """
    if not records:
        raise EvaluationRefused("A sharded run needs its shards' records.")
    try:
        return _merged(records, settings)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        raise EvaluationRefused("Each record must be a shard's record.") from None


def _merged(
    records: Sequence[Mapping[str, Any]], settings: EvaluationSettings
) -> Merged:
    first = records[0]
    for record in records:
        if record.get("format") != SHARD_FORMAT:
            raise EvaluationRefused("Each record must be a shard's record.")
        for key in ("shards", "cases", "run", "detector", "settings"):
            if record[key] != first[key]:
                raise EvaluationRefused("The records must be of one run.")
    if first["settings"] != _settings_of(settings):
        raise EvaluationRefused("The records must be of the settings given.")
    if sorted(record["shard"] for record in records) != list(range(first["shards"])):
        raise EvaluationRefused("A sharded run needs one record of each shard.")
    entries = sorted(
        (each for record in records for each in record["named"]),
        key=lambda each: each["place"],
    )
    places = [each["place"] for each in entries]
    withheld = sum(int(record["withheld"]) for record in records)
    if (
        len(set(places)) != len(places)
        or not all(0 <= place < first["cases"] for place in places)
        or len(places) + withheld != first["cases"]
    ):
        raise EvaluationRefused("The records must hold each case of the run once.")
    found = Totals(Tally(), [], {}, dict.fromkeys(SPLITS, 0))
    for record in records:
        _add(found, _totals_in(record["totals"]))
    detector = dict(first["detector"])
    named = Evaluation(settings, detector, [_named_in(each) for each in entries])
    return Merged(settings, detector, found, named, withheld)


def _add(found: Totals, other: Totals) -> None:
    found.tally.add(other.tally)
    found.clusters += other.clusters
    for name, entry in other.collections.items():
        mine = found.collections.setdefault(
            name, {"cases": 0, "evaluated": 0, "crashed": {}}
        )
        mine["cases"] += entry["cases"]
        mine["evaluated"] += entry["evaluated"]
        for site, count in entry["crashed"].items():
            mine["crashed"][site] = mine["crashed"].get(site, 0) + count
    for part, count in other.parts.items():
        found.parts[part] = found.parts.get(part, 0) + count


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


def _totals_out(found: Totals) -> dict[str, Any]:
    clusters = [_table_out(each) for each in found.clusters]
    return {
        "tally": _tally_out(found.tally),
        "clusters": sorted(clusters, key=_canonical),
        "collections": {
            name: {
                "cases": entry["cases"],
                "evaluated": entry["evaluated"],
                "crashed": dict(sorted(entry["crashed"].items())),
            }
            for name, entry in sorted(found.collections.items())
        },
        "parts": {part: found.parts.get(part, 0) for part in SPLITS},
    }


def _totals_in(entry: Mapping[str, Any]) -> Totals:
    return Totals(
        _tally_in(entry["tally"]),
        [_table_in(each, list) for each in entry["clusters"]],
        {
            str(name): {
                "cases": int(each["cases"]),
                "evaluated": int(each["evaluated"]),
                "crashed": {str(site): int(n) for site, n in each["crashed"].items()},
            }
            for name, each in entry["collections"].items()
        },
        {str(part): int(count) for part, count in entry["parts"].items()},
    )


def _named_out(result: CaseResult, place: int) -> dict[str, Any]:
    return {
        "place": place,
        "collection": result.collection,
        "split": result.split,
        "evaluated": result.evaluated,
        "crashed": result.crashed,
        "public": result.public,
        "tally": _tally_out(result.tally),
    }


def _named_in(entry: Mapping[str, Any]) -> CaseResult:
    return CaseResult(
        collection=entry["collection"],
        split=entry["split"],
        evaluated=entry["evaluated"],
        tally=_tally_in(entry["tally"]),
        crashed=entry["crashed"],
        public=dict(entry["public"]),
    )


def _tally_out(tally: Tally) -> dict[str, Any]:
    return {
        "texts": _table_out(tally.texts),
        "frames": _table_out(tally.frames),
        "zones": _table_out(tally.zones),
        "counts": _table_out(tally.counts),
    }


def _tally_in(entry: Mapping[str, Any]) -> Tally:
    return Tally(
        texts=_table_in(entry["texts"], list),
        frames=_table_in(entry["frames"], list),
        zones=_table_in(entry["zones"], int),
        counts=_table_in(entry["counts"], int),
    )


def _table_out(table: Mapping[tuple, Any]) -> list[list[Any]]:
    """A table's rows, in the order of their keys alone."""
    rows = [[_plain(key), _plain(value)] for key, value in table.items()]
    return sorted(rows, key=lambda row: _canonical(row[0]))


def _table_in(rows: Sequence[Sequence[Any]], kind: type) -> dict[tuple, Any]:
    return {_tuple(key): kind(value) for key, value in rows}


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True)


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
