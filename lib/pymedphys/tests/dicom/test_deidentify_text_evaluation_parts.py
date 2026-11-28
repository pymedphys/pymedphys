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

"""The text detector evaluation's large cases, measured in parts by more
than one worker, to the same results as one process.

Detectors here are stand-ins whose boxes are known. Every value is
invented."""

# pylint: disable = protected-access

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify import text_evaluation_injection as injection
from pymedphys._dicom.deidentify import text_evaluation_parts as parts
from pymedphys._dicom.deidentify import text_evaluation_sources as sources
from pymedphys._dicom.deidentify.text_evaluation_cases import cases_report
from pymedphys._dicom.deidentify.text_evaluation_frames import EvaluationRefused

from ._text_evaluation_stand_ins import (
    BoxDetector,
    box_detector,
    Frames,
    Raising,
    _frame,
    _text,
    _settings,
)


def test_a_heavy_case_splits_into_parts_and_the_heaviest_start_first():
    # The fair share of 22 over 4 workers is 5.5, so the case of 9 is cut
    # in two; every other case is one part.
    assert parts.parts_of((1, 9, 4, 4, 3, 1), 4) == [
        (1, 0, 2),
        (1, 1, 2),
        (2, 0, 1),
        (3, 0, 1),
        (4, 0, 1),
        (0, 0, 1),
        (5, 0, 1),
    ]
    # One case of nearly the whole goes to every worker, and no further.
    assert parts.parts_of((100, 1, 1, 1, 1), 4)[:4] == [
        (0, part, 4) for part in range(4)
    ]
    # Two equal cases over four workers take two each.
    assert parts.parts_of((5, 5), 4) == [
        (0, 0, 2),
        (0, 1, 2),
        (1, 0, 2),
        (1, 1, 2),
    ]
    assert parts.parts_of((5, 5), 2) == [(0, 0, 1), (1, 0, 1)]
    assert parts.parts_of((0, 0), 2) == [(0, 0, 1), (1, 0, 1)]


def _many_frames(case):
    """A case of seven frames, two not read, with text on some, so that
    every part of it counts something different."""
    items = []
    for number in range(7):
        texts = (_text(9 + number, 10, 6, 28),) if number % 3 else ()
        items.append(_frame(case=case, number=number, texts=texts))
        if number in (2, 5):
            items.append(sources.Skipped("not-read"))
    return Frames("c", case, tuple(items))


def test_a_case_in_parts_gives_the_same_results_as_one_process():
    cases = [_many_frames("a"), Frames("c", "b", (_frame(case="b"),)), Raising()]
    settings = _settings(plan=injection.InjectionPlan(texts=2))
    one = evaluation.evaluate(cases, box_detector, settings)
    parted = evaluation.evaluate(
        cases, box_detector, settings, workers=3, weights=(20, 1, 20)
    )
    assert [each.crashed for each in parted.results] == [
        each.crashed for each in one.results
    ]
    assert cases_report(parted) == cases_report(one)
    first = evaluation.summarise(one, replicates=200)
    second = evaluation.summarise(parted, replicates=200)
    del first["software"], second["software"]
    assert first == second


def test_each_part_counts_only_its_own_items():
    case = _many_frames("a")
    settings = _settings()
    whole, _ = evaluation._case_part(case, BoxDetector(), settings, 0, 1)
    pieces = [
        evaluation._case_part(case, BoxDetector(), settings, part, 3)
        for part in range(3)
    ]
    assert all(at is None for _, at in pieces)
    added = evaluation.Tally()
    for result, _ in pieces:
        added.add(result.tally)
    assert added == whole.tally
    # Part 0 is items 0, 3, and 6: the frames numbered 0 and 5, and the item
    # after frame 2, which is not read; part 2 holds no such item.
    assert pieces[0][0].tally.counts[("skipped", "not-read")] == 1
    assert ("skipped", "not-read") not in pieces[2][0].tally.counts


def test_a_case_in_parts_raises_where_one_process_would_first_meet_it():
    # Raising reads one frame, then raises on reading the next: every part
    # meets that at the second item's reading.
    for part in range(2):
        result, at = evaluation._case_part(
            Raising(), BoxDetector(), _settings(), part, 2
        )
        assert at == 2
        assert result.crashed is not None
    early = evaluation.CaseResult("c", "tuning", True, crashed="early")
    late = evaluation.CaseResult("c", "tuning", True, crashed="late")
    fine = evaluation.CaseResult("c", "tuning", True)
    assert parts.joined([(0, fine, None), (1, late, 7), (2, early, 3)]) is early
    assert parts.joined([(1, late, 3), (0, early, 3)]) is early


def test_every_case_needs_a_weight_and_there_must_be_a_worker():
    for workers in (1, 2):
        with pytest.raises(EvaluationRefused):
            evaluation.evaluate(
                [Raising()], box_detector, _settings(), workers=workers, weights=(1, 2)
            )
    with pytest.raises(EvaluationRefused):
        parts.parts_of((1,), 0)
