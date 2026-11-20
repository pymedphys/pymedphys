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

"""The text detector's evaluation measured in shards merges to the run
that one runner measures. Every value is invented."""

import dataclasses
import json

import pytest

from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_shards as shards
from pymedphys._dicom.deidentify.text_evaluation_cases import cases_report
from pymedphys._dicom.deidentify.text_evaluation_criteria import (
    CHOSEN_CRITERIA,
    assess,
)
from pymedphys._dicom.deidentify.text_evaluation_detector import PostProcessing
from pymedphys._dicom.deidentify.text_evaluation_frames import EvaluationRefused
from pymedphys._dicom.deidentify.text_evaluation_idc import OPEN_COLLECTIONS
from pymedphys._dicom.deidentify.text_evaluation_sources import SkippedFiles

from ._text_evaluation_stand_ins import (
    SECRET,
    Raising,
    _frame,
    _settings,
    _text,
    box_detector,
)

SUBJECT = "SUBJECT^SECRET^0815"
_OPEN, _LICENCE = next(iter(OPEN_COLLECTIONS.items()))


@dataclasses.dataclass(frozen=True)
class Case:
    """A case whose frames are given, of a subject where one is given, and
    named by public identifiers where they are given."""

    collection: str
    case: str
    frames: tuple
    subject: str | None = None
    subject_namespace: str | None = None
    public: dict | None = None

    def read(self):
        yield from self.frames


def _texts(count, contrast):
    return tuple(
        _text(2 + 12 * row, 4, 6, 10 + 6 * row, font="f", contrast=contrast)
        for row in range(count)
    )


def _cases():
    """Cases of several subjects, some sharing one, across two namespaces,
    in both parts of the split, with a case that raises and one skipped."""
    public = {
        "collection_id": _OPEN,
        "series_instance_uid": "1.2.826.0.1.3680043.2.1125.1",
        "licence": _LICENCE,
        "doi": "10.1234/invented",
    }
    found = []
    for index in range(14):
        subject = f"{SUBJECT}/{index % 5}" if index % 3 else None
        frames = (
            _frame(case=f"{SECRET}/{index}", texts=_texts(index % 4, f"{index} sigma")),
            _frame(case=f"{SECRET}/{index}"),
        )
        found.append(
            Case(
                "first" if index % 2 else "second",
                f"{SECRET}/{index}",
                frames,
                subject=subject,
                subject_namespace="shared" if subject else None,
                public=public if index == 4 else None,
            )
        )
    found.insert(6, Raising(case=f"{SECRET}/raising"))
    found.insert(9, SkippedFiles("first", f"{SECRET}/skipped", "not-asked-for", 3))
    return found


def _points():
    return (PostProcessing(), PostProcessing(box_threshold=0.7))


def _sharded(cases, settings, count):
    groups = shards.case_groups(cases)
    records = []
    for shard in range(count):
        positions = shards.shard_positions(groups, shard, count)
        run = evaluation.evaluate(
            [cases[place] for place in positions], box_detector, settings
        )
        record = shards.shard_record(run, positions, groups, shard=shard, shards=count)
        # Each record reaches the merge as JSON, as a runner's artefact.
        records.append(json.loads(json.dumps(record)))
    return records


@pytest.mark.parametrize("evaluated", ["tuning", "all"])
@pytest.mark.parametrize("count", [1, 2, 3, 7])
def test_a_run_in_shards_merges_to_the_run_on_one_runner(evaluated, count):
    cases = _cases()
    settings = _settings(points=_points(), evaluated=evaluated)
    whole = evaluation.evaluate(cases, box_detector, settings)
    merged = shards.merged(_sharded(cases, settings, count), settings)
    expected = evaluation.summarise(whole, replicates=200)
    found = evaluation.summarise(merged, replicates=200)
    assert json.dumps(found) == json.dumps(expected)
    assert json.dumps(cases_report(merged)) == json.dumps(cases_report(whole))
    assert assess(found, CHOSEN_CRITERIA) == assess(expected, CHOSEN_CRITERIA)


def test_a_shards_record_names_no_subject_or_case():
    cases = _cases()
    settings = _settings(points=_points())
    text = json.dumps(_sharded(cases, settings, 2))
    assert SECRET not in text
    assert SUBJECT not in text
    assert "shared" not in text


def test_a_subjects_cases_are_numbered_by_order_alone_and_kept_in_one_shard():
    cases = [
        Case("c", "a", (), subject="z"),
        Case("c", "b", ()),
        Case("c", "c", (), subject="z"),
        Case("d", "d", (), subject="z"),
        Case("d", "e", (), subject="z", subject_namespace="c"),
    ]
    groups = shards.case_groups(cases)
    # The subject "z" is one in collection c, another in d, and the first
    # again where d's case names c as where its subject is named.
    assert groups == (0, 1, 0, 2, 0)
    assert shards.shard_positions(groups, 0, 2) == [0, 2, 3, 4]
    assert shards.shard_positions(groups, 1, 2) == [1]
    # The numbers follow from the order alone, not from what the subjects
    # are named.
    renamed = [
        each if each.subject is None else dataclasses.replace(each, subject="y")
        for each in cases
    ]
    assert shards.case_groups(renamed) == groups


@pytest.mark.parametrize("shard, count", [(-1, 2), (2, 2), (0, 0)])
def test_a_shard_must_be_one_of_the_runs(shard, count):
    with pytest.raises(EvaluationRefused):
        shards.shard_positions((0, 1), shard, count)


def _records():
    cases = _cases()
    settings = _settings(points=_points())
    return _sharded(cases, settings, 3), settings


def test_a_merge_refuses_a_shard_missing_or_repeated():
    records, settings = _records()
    with pytest.raises(EvaluationRefused, match="each shard"):
        shards.merged(records[:2], settings)
    with pytest.raises(EvaluationRefused, match="each shard"):
        shards.merged([*records, records[0]], settings)
    with pytest.raises(EvaluationRefused, match="shards' records"):
        shards.merged([], settings)


def test_a_merge_refuses_records_of_another_run_or_settings():
    records, settings = _records()
    for key, value in (
        ("detector", {"network": "other"}),
        ("shards", 4),
        ("run", {"variant": "other"}),
        ("groups", [0]),
        ("settings", {}),
    ):
        changed = [dict(records[0], **{key: value}), *records[1:]]
        with pytest.raises(EvaluationRefused, match="one run"):
            shards.merged(changed, settings)
    other = _settings(points=(PostProcessing(),))
    with pytest.raises(EvaluationRefused, match="settings given"):
        shards.merged(records, other)
    labelled = [dict(records[0], format="another/1"), *records[1:]]
    with pytest.raises(EvaluationRefused, match="shard's record"):
        shards.merged(labelled, settings)
    with pytest.raises(EvaluationRefused, match="shard's record"):
        shards.merged([{"format": shards.SHARD_FORMAT}, *records[1:]], settings)
    with pytest.raises(EvaluationRefused, match="shard's record"):
        shards.merged([dict(each, shards=0) for each in records], settings)


def test_a_merge_refuses_a_record_of_another_shards_cases():
    records, settings = _records()
    swapped = [
        dict(records[0], results=records[1]["results"]),
        dict(records[1], results=records[0]["results"]),
        records[2],
    ]
    with pytest.raises(EvaluationRefused, match="its own cases"):
        shards.merged(swapped, settings)


def test_a_merge_refuses_a_case_missing_or_held_twice():
    records, settings = _records()
    dropped = [dict(records[0], results=records[0]["results"][1:]), *records[1:]]
    with pytest.raises(EvaluationRefused, match="each case"):
        shards.merged(dropped, settings)
    doubled = [
        dict(records[0], results=[*records[0]["results"], records[0]["results"][0]]),
        *records[1:],
    ]
    with pytest.raises(EvaluationRefused, match="each case"):
        shards.merged(doubled, settings)


def test_a_record_needs_each_cases_place():
    cases = _cases()
    settings = _settings(points=_points())
    run = evaluation.evaluate(cases[:2], box_detector, settings)
    with pytest.raises(EvaluationRefused, match="place"):
        shards.shard_record(run, [0], shards.case_groups(cases), shard=0, shards=1)
