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

from pymedphys._imports import pydicom

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
from pymedphys._dicom.deidentify.text_evaluation_sources import (
    DicomCase,
    SkippedFiles,
)

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


def _public(index):
    return {
        "collection_id": _OPEN,
        "series_instance_uid": f"1.2.826.0.1.3680043.2.1125.{index}",
        "licence": _LICENCE,
        "doi": "10.1234/invented",
    }


def _case(index, *, subject=None, public=None):
    frames = (
        _frame(case=f"{SECRET}/{index}", texts=_texts(index % 4, f"{index} sigma")),
        _frame(case=f"{SECRET}/{index}"),
    )
    return Case(
        "first" if index % 2 else "second",
        f"{SECRET}/{index}",
        frames,
        subject=subject,
        subject_namespace="shared" if subject else None,
        public=public,
    )


def _cases():
    """Cases of several subjects, some sharing one, across two namespaces,
    in both parts of the split, some named by public identifiers, with a
    case that raises and one skipped."""
    found = [
        _case(
            index,
            subject=f"{SUBJECT}/{index % 5}" if index % 3 else None,
            public=_public(index) if index % 4 == 1 else None,
        )
        for index in range(14)
    ]
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
        record = shards.shard_record(
            run, positions, len(cases), shard=shard, shards=count
        )
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
    found = evaluation.summary_of(
        merged.settings, merged.detector, merged.totals, replicates=200
    )
    assert json.dumps(found) == json.dumps(expected)
    report = cases_report(merged.named, withheld=merged.withheld)
    assert json.dumps(report) == json.dumps(cases_report(whole))
    assert len(report["cases"]) == 4
    assert assess(found, CHOSEN_CRITERIA) == assess(expected, CHOSEN_CRITERIA)


def test_a_shards_record_names_no_subject_or_case():
    cases = _cases()
    settings = _settings(points=_points())
    text = json.dumps(_sharded(cases, settings, 2))
    assert SECRET not in text
    assert SUBJECT not in text
    assert "shared" not in text


def test_a_record_gives_nothing_by_a_withheld_cases_place_or_subject():
    # Cases that the report withholds, moved among their places, which
    # renumbers their subjects, leave the record as it was. (Their subjects'
    # names choose their part of the split, which the summary counts.)
    cases = _cases()
    settings = _settings(points=_points())
    withheld = [
        place
        for place, each in enumerate(cases)
        if getattr(each, "public", None) is None
    ]
    moved = list(cases)
    for place, source in zip(withheld, [*withheld[3:], *withheld[:3]]):
        moved[place] = cases[source]
    assert shards.case_groups(moved) != shards.case_groups(cases)
    assert _sharded(moved, settings, 1) == _sharded(cases, settings, 1)


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
    # Unweighted, "z" of c, with three cases, fills one shard, and the
    # other two subjects the other.
    assert shards.shard_positions(groups, 0, 2) == [0, 2, 4]
    assert shards.shard_positions(groups, 1, 2) == [1, 3]
    # The numbers follow from the order alone, not from what the subjects
    # are named.
    renamed = [
        each if each.subject is None else dataclasses.replace(each, subject="y")
        for each in cases
    ]
    assert shards.case_groups(renamed) == groups


def test_subjects_go_heaviest_first_to_the_least_loaded_shard():
    # Subjects 0 to 4 weigh 2, 9, 4, 4, and 3: 9 alone, then 4 and 4 apart,
    # then 3 and 2 onto the lighter of those, then the lighter again.
    groups = (0, 1, 2, 3, 4, 0)
    weights = (1, 9, 4, 4, 3, 1)
    found = [shards.shard_positions(groups, k, 3, weights) for k in range(3)]
    assert found == [[1], [2, 4], [0, 3, 5]]
    # Every case is in exactly one shard, for any count of shards.
    for count in range(1, 8):
        places = [
            place
            for k in range(count)
            for place in shards.shard_positions(groups, k, count, weights)
        ]
        assert sorted(places) == list(range(len(groups)))


def test_a_shard_needs_each_cases_weight():
    with pytest.raises(EvaluationRefused, match="weight"):
        shards.shard_positions((0, 1), 0, 2, (1,))


def test_a_cases_weight_is_its_files_frames(tmp_path):
    multiframe = tmp_path / "multiframe.dcm"
    dataset = pydicom.Dataset()
    dataset.NumberOfFrames = 7
    dataset.SOPClassUID = "1.2.840.10008.5.1.4.1.1.7"
    dataset.SOPInstanceUID = "1.2.826.0.1.3680043.2.1125.7"
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    dataset.file_meta.MediaStorageSOPClassUID = dataset.SOPClassUID
    dataset.file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
    dataset.save_as(multiframe, enforce_file_format=True)
    other = tmp_path / "other.dcm"
    other.write_bytes(b"not DICOM")
    case = DicomCase("c", "case", (str(multiframe), str(other), str(tmp_path / "gone")))
    # Seven frames, one for the file that is not DICOM, and one for the
    # file that is missing.
    assert shards.case_weight(case) == 9
    assert shards.case_weight(SkippedFiles("c", "s", "not-asked-for", 3)) == 1


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
        ("cases", 99),
        ("run", {"variant": "other"}),
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
    broken = dict(records[0], totals={"tally": {}})
    with pytest.raises(EvaluationRefused, match="shard's record"):
        shards.merged([broken, *records[1:]], settings)


def test_a_merge_refuses_a_case_missing_or_held_twice():
    records, settings = _records()
    named = next(each for each in records if each["named"])
    others = [each for each in records if each is not named]
    for changed in (
        dict(named, named=named["named"][1:]),
        dict(named, named=[*named["named"], named["named"][0]]),
        dict(named, withheld=named["withheld"] + 1),
        dict(named, named=[dict(named["named"][0], place=99)]),
    ):
        with pytest.raises(EvaluationRefused, match="each case"):
            shards.merged([changed, *others], settings)


def test_a_record_needs_each_cases_place():
    cases = _cases()
    settings = _settings(points=_points())
    run = evaluation.evaluate(cases[:2], box_detector, settings)
    with pytest.raises(EvaluationRefused, match="place"):
        shards.shard_record(run, [0], len(cases), shard=0, shards=1)
