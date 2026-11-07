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

"""Split a MIDI benchmark run into shards by patient, and combine them (D-018).

A run under Clean Pixel Data takes longer than one CI job may run, since
the text detector reads every frame. So a run can be split into shards, each
run in a job of its own on its own copy of the test data set. Each shard
de-identifies the instances of its patients alone, and scores the answer
key's checks of those instances alone, so that each check is scored in
exactly one shard. :func:`combine` adds the shards' results up.

A patient's instances stay together, since a run withholds all of a
patient's files where one is withheld, and finds what needs more than one
instance, such as a CT series' face block or a subject's synthetic birth
date, within a patient. Patients are assigned by :func:`assign`, which
balances the shards' pixels, the text detector's work. Instances whose
header cannot be read, or that name no patient, go to the first shard, as do
the checks of answer-key instances that the input does not hold.

Assigning by Patient ID is an assumption: a run that related instances of
different Patient IDs to one another would give different results when
sharded.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Mapping, Sequence

from .midi_benchmark_exemptions import EXEMPTIONS

_SHARD = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)")


class ShardError(ValueError):
    """A shard that cannot be named or results that cannot be combined.

    The message quotes no value.
    """


@dataclasses.dataclass(frozen=True)
class Shard:
    """One of ``count`` shards of a run, numbered from 1.

    >>> Shard.parse("2/6")
    Shard(number=2, count=6)
    >>> str(Shard(2, 6))
    '2/6'
    """

    number: int
    count: int

    def __post_init__(self) -> None:
        if not 1 <= self.number <= self.count:
            raise ShardError("a shard's number must be from 1 to the count")

    def __str__(self) -> str:
        return f"{self.number}/{self.count}"

    @classmethod
    def parse(cls, text: str) -> Shard:
        """Read a shard written as ``number/count``, such as ``2/6``."""
        match = _SHARD.fullmatch(text)
        if match is None:
            raise ShardError("a shard is written as number/count, such as 2/6")
        return cls(int(match[1]), int(match[2]))


def assign(
    patients: Sequence[str | None], weights: Sequence[int], count: int
) -> tuple[int, ...]:
    """Return the shard, from 1, of each input, by its patient.

    Each patient's inputs go to one shard. Patients are taken from the
    heaviest down, by the sum of their inputs' ``weights``, and each goes to
    the lightest shard so far, the first of equals, so the assignment
    depends only on the inputs, in their order. An input without a patient
    goes to the first shard.

    >>> assign(["A", "B", "A", None, "C"], [5, 4, 5, 1, 3], 2)
    (2, 1, 2, 1, 1)
    """
    totals: dict[str, int] = {}
    first: dict[str, int] = {}
    for position, (patient, weight) in enumerate(zip(patients, weights, strict=True)):
        if patient is not None:
            totals[patient] = totals.get(patient, 0) + max(weight, 1)
            first.setdefault(patient, position)
    loads = [0] * count
    loads[0] = sum(
        max(weight, 1)
        for patient, weight in zip(patients, weights, strict=True)
        if patient is None
    )
    shard_of: dict[str, int] = {}
    for patient in sorted(totals, key=lambda name: (-totals[name], first[name])):
        lightest = min(range(count), key=lambda index: (loads[index], index))
        shard_of[patient] = lightest + 1
        loads[lightest] += totals[patient]
    return tuple(1 if patient is None else shard_of[patient] for patient in patients)


def combine(documents: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Add up the results of every shard of one run.

    Each document is a shard's ``benchmark.json``. They must be of one
    format, with the same versions apart from ``shard``, and be shards 1 to
    *n* of *n*, each once. The combined document names ``shard`` as
    ``combined n``. Each count is the sum of the shards' counts. Each
    table's rows are merged by their fields that are not counts, and
    ordered as a whole run orders them; so are the names of a mapping that
    the shards do not all hold alike, such as the modalities. Since each
    check is scored in one shard, the combined results are those of a whole
    run, apart from ``shard``, where no instance of one Patient ID depends
    on another's (:mod:`~pymedphys._dicom.deidentify.midi_benchmark_shards`).

    Raises
    ------
    ShardError
        If the documents are not every shard of one run, or differ where
        they cannot be added up.
    """
    if not documents:
        raise ShardError("there are no shards to combine")
    formats = {str(document.get("format")) for document in documents}
    if len(formats) != 1:
        raise ShardError("the shards' results are of different formats")
    versions: list[Mapping[str, object]] = []
    for document in documents:
        each = document.get("versions")
        if not isinstance(each, Mapping):
            raise ShardError("a shard's results have no versions")
        versions.append(each)
    shards = sorted(
        (Shard.parse(str(each.get("shard"))) for each in versions),
        key=lambda shard: shard.number,
    )
    count = shards[0].count
    if [str(shard) for shard in shards] != [
        f"{number}/{count}" for number in range(1, count + 1)
    ]:
        raise ShardError("the results are not each shard of one run, once")
    unsharded = [
        {name: value for name, value in each.items() if name != "shard"}
        for each in versions
    ]
    if any(each != unsharded[0] for each in unsharded):
        raise ShardError("the shards ran with different versions")
    names = list(documents[0])
    if any(list(document) != names for document in documents):
        raise ShardError("the shards' results hold different fields")
    combined: dict[str, object] = {}
    for name in names:
        if name == "format":
            combined[name] = formats.pop()
        elif name == "versions":
            combined[name] = {**versions[0], "shard": f"combined {count}"}
        else:
            combined[name] = _merged(
                [document[name] for document in documents], (name,)
            )
    return combined


# The fields of a table's rows that are counts, which are added up; a row's
# other fields describe it. Those of the categories' counts, and of each
# other table's.
COUNTS = frozenset(
    {
        "passed",
        "failed",
        "deliberate",
        "source_gap",
        "replacement_match",
        "not_evaluated",
        "withheld",
        "outside_coverage",
        "not_in_input",
        "checks",
        "instances",
        "times",
    }
)

# The tables that a whole run orders by their rows' counts, the most first,
# and then by their other fields.
_MOST_FIRST = frozenset({("coverage", "withheld_places"), ("coverage", "no_sop_class")})


def _merged(values: list[object], where: tuple[str, ...]) -> object:
    """Add up one field of every shard's results."""
    present = [value for value in values if value is not None]
    if not present:
        return None
    if all(_is_count(value) for value in present):
        return sum(value for value in present if isinstance(value, int))
    if all(isinstance(value, Mapping) for value in present):
        mappings = [value for value in present if isinstance(value, Mapping)]
        names = list(mappings[0])
        if any(list(value) != names for value in mappings):
            names = sorted({name for value in mappings for name in value})
        return {
            name: _merged([value.get(name) for value in mappings], (*where, name))
            for name in names
        }
    if all(isinstance(value, list) for value in present):
        rows = [row for value in present if isinstance(value, list) for row in value]
        if all(isinstance(row, Mapping) for row in rows):
            return _merged_rows(rows, where)
    if all(value == present[0] for value in present):
        return present[0]
    raise ShardError("the shards' results differ where they cannot be added up")


def _merged_rows(
    rows: list[Mapping[str, object]], where: tuple[str, ...]
) -> list[dict[str, object]]:
    """Merge a table's rows by their fields that are not counts."""
    merged: dict[tuple[tuple[str, object], ...], dict[str, object]] = {}
    for row in rows:
        described = tuple(
            (name, _frozen(value)) for name, value in row.items() if name not in COUNTS
        )
        if described not in merged:
            merged[described] = dict(row)
            continue
        total = merged[described]
        for name, value in row.items():
            if name in COUNTS:
                if not _is_count(value) or not _is_count(total.get(name)):
                    raise ShardError("a shard's table has a count that is not one")
                total[name] = int(total[name]) + int(value)  # type: ignore[call-overload]
    return sorted(merged.values(), key=_row_order(where))


def _row_order(where: tuple[str, ...]) -> Callable[[Mapping[str, object]], object]:
    """Return the key that orders a table's rows as a whole run does."""

    def text(row: Mapping[str, object]) -> tuple[str, ...]:
        # As counted_order orders counted descriptions: by their text, a
        # missing field first.
        return tuple(
            "" if value is None else str(value)
            for name, value in row.items()
            if name not in COUNTS
        )

    if where in _MOST_FIRST:
        return lambda row: (-sum(_count(row.get(name)) for name in COUNTS), text(row))
    if where == ("categories",):
        # As category_order: by family and code, no category last.
        return lambda row: (
            ("~", "")
            if row.get("family") is None
            else (str(row["family"]), str(row["code"]))
        )
    if where == ("coverage", "would_release"):
        return lambda row: (_exemption_order(row.get("exemption")), text(row))
    return text


def _exemption_order(exemption: object) -> int:
    return EXEMPTIONS.index(exemption) if exemption in EXEMPTIONS else len(EXEMPTIONS)


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _count(value: object) -> int:
    return value if _is_count(value) else 0  # type: ignore[return-value]


def _frozen(value: object) -> object:
    if isinstance(value, list):
        return tuple(_frozen(each) for each in value)
    if isinstance(value, Mapping):
        return tuple((name, _frozen(each)) for name, each in value.items())
    return value
