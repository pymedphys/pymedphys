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
"""The reviewed tier of ROI Name cleaning, and the reviewed-names list.

Every vocabulary here is invented, in the shape of the TG-263 spreadsheet's
entries, and every ROI Name and identifier is synthetic.
"""

import dataclasses
import json
import os
import pathlib
from unittest import mock

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import reviewed_roi_names as reviewed
from pymedphys._dicom.deidentify import roi_names
from pymedphys._dicom.deidentify.reviewed_roi_names import (
    Outcome,
    Review,
    ReviewedName,
)
from pymedphys._dicom.deidentify.roi_names import Reason
from pymedphys._nomenclature import tg263

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")

KEEP = ReviewedName(Review.KEEP)
EMPTY = ReviewedName(Review.EMPTY)


def _map(to):
    return ReviewedName(Review.MAP, to)


@pytest.fixture(name="home", autouse=True)
def fixture_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    return home


def _list(**decisions):
    names = reviewed.ReviewedNames.empty()
    for name, decision in decisions.items():
        names.record(name.replace("_", " "), decision)
    return names


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_reviewed_decisions_are_reused_on_later_runs(tmp_path):
    path = tmp_path / "custodian" / "reviewed-roi-names.json"
    path.parent.mkdir()
    first = reviewed.ReviewedNames.open(path)
    first.record("PRV cord", KEEP)
    first.record("Lung L old", _map("Lung_L_Old"))
    first.record("Dr X lung", EMPTY)
    first.save()

    later = reviewed.ReviewedNames.open(path)

    assert len(later) == 3
    assert later.get("PRV cord") == KEEP
    assert later.get("Lung L old") == _map("Lung_L_Old")
    assert later.get("Dr X lung") == EMPTY
    assert later.get("prv cord") is None


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_the_list_never_shows_a_name():
    names = _list(PRV_cord=KEEP, Lung_old=_map("Lung_Old"))

    shown = repr(names) + repr(names.get("Lung old"))

    for value in ("PRV", "cord", "Lung", "Old"):
        assert value not in shown


@pytest.mark.parametrize(
    "decision",
    [
        lambda: ReviewedName(Review.MAP),
        lambda: ReviewedName(Review.KEEP, "Heart"),
        lambda: ReviewedName(Review.MAP, ""),
        lambda: ReviewedName(Review.MAP, " Heart"),
        lambda: ReviewedName(Review.MAP, "Heart\\Lung"),
        lambda: ReviewedName(Review.MAP, "Cœur"),
        lambda: ReviewedName(Review.MAP, "H" * 65),
        lambda: ReviewedName("keep"),
    ],
)
def test_a_mapping_needs_a_name_that_roi_name_can_hold(decision):
    with pytest.raises((TypeError, ValueError)) as error:
        decision()

    assert "Heart" not in str(error.value) and "Cœur" not in str(error.value)


@pytest.mark.parametrize(
    "name", ["", "  PRV", "PRV\x00", "PRV\\cord", "PRV\ncord", "PRV\ud800", 3]
)
def test_a_reviewed_name_must_be_an_unpadded_text_value(name):
    with pytest.raises((TypeError, ValueError)) as error:
        reviewed.ReviewedNames.empty().record(name, KEEP)

    assert "PRV" not in str(error.value)


def test_a_non_ascii_name_can_be_reviewed():
    names = _list()
    names.record("Cœur", _map("Heart_Old"))

    assert names.get("Cœur") == _map("Heart_Old")


def test_a_different_decision_replaces_the_recorded_one_only_when_asked():
    names = _list(PRV_cord=KEEP)
    names.record("PRV cord", KEEP)

    with pytest.raises(reviewed.ReviewedNamesError, match="already has a different"):
        names.record("PRV cord", EMPTY)
    names.record("PRV cord", EMPTY, replace=True)

    assert names.get("PRV cord") == EMPTY and len(names) == 1


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize("where", ["config", "protected"])
def test_the_list_is_refused_inside_a_protected_directory(tmp_path, where):
    if where == "config":
        directory = pathlib.Path.home() / ".pymedphys"
    else:
        directory = tmp_path / "output"
    directory.mkdir()

    with pytest.raises(reviewed.ReviewedNamesError, match="refusing"):
        reviewed.ReviewedNames.open(
            directory / "reviewed.json", protected_dirs=[tmp_path / "output"]
        )


def _write(path, document):
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


GOOD = {
    "format": reviewed.FORMAT,
    "names": {
        "PRV cord": {"review": "keep"},
        "Lung old": {"review": "map", "to": "Lung_Old"},
    },
}


@pytest.mark.parametrize(
    "document",
    [
        [],
        {**GOOD, "format": "pymedphys-deid-reviewed-roi-names/0"},
        {**GOOD, "extra": 1},
        {"format": reviewed.FORMAT},
        {**GOOD, "names": []},
        {**GOOD, "names": {"PRV cord": {"review": "rename"}}},
        {**GOOD, "names": {"PRV cord": {"review": "keep", "to": "PRV"}}},
        {**GOOD, "names": {"PRV cord": {"review": "map"}}},
        {**GOOD, "names": {"PRV cord": {"review": "map", "to": "Cœur"}}},
        {**GOOD, "names": {" PRV cord": {"review": "keep"}}},
        {**GOOD, "names": {"PRV cord": "keep"}},
        {**GOOD, "names": {"PRV cord": {"review": ["keep"]}}},
        {**GOOD, "names": {"PRV\ud800": {"review": "keep"}}},
    ],
)
def test_a_malformed_list_is_refused_without_quoting_it(tmp_path, document):
    path = _write(tmp_path / "reviewed.json", document)

    with pytest.raises(reviewed.ReviewedNamesError) as error:
        reviewed.ReviewedNames.open(path)

    assert "PRV" not in str(error.value) and "Lung" not in str(error.value)


def test_a_list_with_a_repeated_name_is_refused(tmp_path):
    path = tmp_path / "reviewed.json"
    path.write_text(
        '{"format": "%s", "names": {"PRV": {"review": "keep"}, '
        '"PRV": {"review": "empty"}}}' % reviewed.FORMAT,
        encoding="utf-8",
    )

    with pytest.raises(
        reviewed.ReviewedNamesError, match="item 2 of an object in the list is repeated"
    ):
        reviewed.ReviewedNames.open(path)


def test_an_unreadable_list_is_refused(tmp_path):
    path = tmp_path / "reviewed.json"
    path.write_bytes(b"\xff{")

    with pytest.raises(reviewed.ReviewedNamesError, match="could not be read"):
        reviewed.ReviewedNames.open(path)


def test_an_empty_list_is_never_saved():
    with pytest.raises(reviewed.ReviewedNamesError, match="no file"):
        reviewed.ReviewedNames.empty().save()


def test_the_saved_list_is_sorted_and_round_trips(tmp_path):
    path = _write(tmp_path / "reviewed.json", GOOD)
    names = reviewed.ReviewedNames.open(path)
    names.record("A name", EMPTY)
    names.save()

    document = json.loads(path.read_text(encoding="utf-8"))
    assert list(document["names"]) == ["A name", "Lung old", "PRV cord"]
    assert reviewed.ReviewedNames.open(path).get("A name") == EMPTY


@posix_only
def test_the_saved_list_is_readable_only_by_its_owner(tmp_path):
    path = tmp_path / "reviewed.json"
    names = reviewed.ReviewedNames.open(path)
    names.record("PRV cord", KEEP)
    names.save()

    assert path.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["home", "reviewed.json"]


def test_a_failed_save_leaves_the_previous_list_and_no_partial_file(tmp_path):
    path = _write(tmp_path / "reviewed.json", GOOD)
    before = path.read_bytes()
    names = reviewed.ReviewedNames.open(path)
    names.record("A name", EMPTY)

    with mock.patch.object(reviewed.os, "replace", side_effect=OSError("disk")):
        with pytest.raises(OSError):
            names.save()

    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["home", "reviewed.json"]


def test_a_read_error_does_not_carry_the_files_text(tmp_path):
    path = tmp_path / "reviewed.json"
    path.write_bytes(b'{"format": "x", "names": {"Smith lung": \xff')

    with pytest.raises(reviewed.ReviewedNamesError) as error:
        reviewed.ReviewedNames.open(path)

    assert error.value.__cause__ is None and error.value.__suppress_context__


def _vocabulary(*names):
    nomenclature = tg263.Nomenclature(
        source=tg263.Source(file="invented.xls", sha256="0" * 64, sheet="Invented"),
        attribution=tg263.ATTRIBUTION,
        structures=tuple(
            tg263.Structure(
                target_type="Anatomic",
                major_category="Invented",
                minor_category="",
                anatomic_group="",
                primary_name=primary,
                reverse_order_name=reverse,
                description="",
                fma_id=None,
            )
            for primary, reverse in names
        ),
    )
    entries = [dataclasses.asdict(s) for s in nomenclature.structures]
    published = {"TG263 vInvented": tg263.content_sha256(entries)}
    with mock.patch.dict(roi_names.PUBLISHED_TG263, published):
        return roi_names.RoiNameVocabulary(nomenclature)


def _clean(names, reviewed_names, identifiers=(), **options):
    return reviewed.clean_roi_names(
        names, VOCABULARY, reviewed_names, identifiers=identifiers, **options
    )


def _written(results):
    return [(result.outcome, result.value) for result in results]


VOCABULARY = _vocabulary(("Lung_L", "L_Lung"), ("Heart", "Heart"), ("Hand_L", "L_Hand"))


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_reviewers_decision_to_keep_map_or_empty_a_name_is_applied():
    names = _list(PRV_cord=KEEP, Lung_L_old=_map("Lung_L_Old"), Dr_X_lung=EMPTY)

    results = _clean(["PRV cord", "Lung L old", "Dr X lung"], names)

    assert _written(results) == [
        (Outcome.KEPT, "PRV cord"),
        (Outcome.MAPPED, "Lung_L_Old"),
        (Outcome.EMPTIED, ""),
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_bulk_rename_applies_to_every_structure_set_with_the_name():
    names = _list(GTV_boost_1=_map("GTV_Boost"))

    first = _clean(["GTV boost 1", "Heart"], names)
    second = _clean(["Lung_L", "GTV boost 1"], names)

    assert _written(first)[0] == _written(second)[1] == (Outcome.MAPPED, "GTV_Boost")


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_name_neither_renamed_nor_reviewed_is_held_with_the_automatic_reason():
    results = _clean(["Lung_L1", "Heart"], _list())

    assert [(r.outcome, r.held_because, r.value) for r in results] == [
        (Outcome.HELD, Reason.UNMATCHED, None),
        (Outcome.RENAMED, None, "Heart"),
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_held_name_is_emptied_only_when_the_user_chooses_so():
    results = _clean(["Lung_L1", "PRV cord"], _list(PRV_cord=KEEP), empty_held=True)

    assert [(r.outcome, r.held_because, r.value) for r in results] == [
        (Outcome.EMPTIED_UNREVIEWED, Reason.UNMATCHED, ""),
        (Outcome.KEPT, None, "PRV cord"),
    ]


def test_the_automatic_tier_renames_before_the_list_is_consulted():
    results = _clean(["lung l"], _list(lung_l=EMPTY))

    assert _written(results) == [(Outcome.RENAMED, "Lung_L")]


def test_an_empty_name_stays_empty():
    assert _written(_clean(["  ", ""], _list())) == [
        (Outcome.EMPTY, ""),
        (Outcome.EMPTY, ""),
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01", "MIDI-BP-11")
@pytest.mark.parametrize(
    "source, decision",
    [("Lung Smith", KEEP), ("Lung Doe", _map("Smith_Lung"))],
)
def test_a_reviewed_name_that_echoes_an_identifier_is_held(source, decision):
    names = reviewed.ReviewedNames.empty()
    names.record(source, decision)

    results = _clean([source], names, identifiers=["Smith^Jo"])

    assert [(r.outcome, r.held_because, r.value) for r in results] == [
        (Outcome.HELD, Reason.ECHOES_IDENTIFIER, None)
    ]


def test_a_reviewed_mapping_is_checked_for_echoes_in_what_it_writes():
    results = _clean(
        ["Hand L"], _list(Hand_L=_map("Hand_L_Old")), identifiers=["Hand^Jo"]
    )

    # The written name still holds "Hand", so it is held.
    assert results[0].held_because is Reason.ECHOES_IDENTIFIER
    results = _clean(["Hand L"], _list(Hand_L=_map("Wrist_L")), identifiers=["Hand^Jo"])
    assert _written(results) == [(Outcome.MAPPED, "Wrist_L")]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "names, decisions",
    [
        (["lung l", "Lung L old"], {"Lung L old": _map("Lung_L")}),
        (["PRV a", "PRV b"], {"PRV a": _map("PRV"), "PRV b": _map("PRV")}),
        (["PRV", "prv"], {"PRV": KEEP, "prv": _map("PRV")}),
        (["PRV a", "prv A"], {"PRV a": KEEP, "prv A": KEEP}),
        (["Lung_L", "Lung L old"], {"Lung L old": _map("LUNG_L")}),
    ],
)
def test_different_names_that_would_be_written_as_one_name_are_held(names, decisions):
    reviewed_names = reviewed.ReviewedNames.empty()
    for name, decision in decisions.items():
        reviewed_names.record(name, decision)

    results = _clean(names, reviewed_names)

    assert [(r.outcome, r.held_because) for r in results] == [
        (Outcome.HELD, Reason.WOULD_DUPLICATE)
    ] * 2


def test_a_reviewed_mapping_resolves_an_automatic_duplicate():
    names = reviewed.ReviewedNames.empty()
    names.record("LUNG-L", _map("Lung_L_2"))

    results = _clean(["Lung_L", "LUNG-L"], names)

    assert _written(results) == [
        (Outcome.RENAMED, "Lung_L"),
        (Outcome.MAPPED, "Lung_L_2"),
    ]


def test_names_the_automatic_tier_would_duplicate_stay_held_without_decisions():
    results = _clean(["Lung_L", "LUNG-L"], _list())

    assert [(r.outcome, r.held_because) for r in results] == [
        (Outcome.HELD, Reason.WOULD_DUPLICATE)
    ] * 2


@pytest.mark.parametrize(
    "names, identifiers", [("Heart", ()), (["Heart"], "Smith"), ([3], ())]
)
def test_names_and_identifiers_must_be_sequences_of_strings(names, identifiers):
    with pytest.raises(TypeError):
        _clean(names, _list(), identifiers=identifiers)


def test_the_same_reviewed_name_twice_is_written_twice():
    results = _clean(["PRV cord", "PRV cord  "], _list(PRV_cord=KEEP))

    assert _written(results) == [(Outcome.KEPT, "PRV cord")] * 2


def test_a_reviewed_name_matches_only_its_exact_spelling():
    results = _clean(["prv cord", "PRV  cord"], _list(PRV_cord=KEEP))

    assert [r.outcome for r in results] == [Outcome.HELD, Outcome.HELD]


def test_without_a_vocabulary_every_name_needs_the_list():
    results = reviewed.clean_roi_names(
        ["Heart", "PRV cord"], None, _list(PRV_cord=KEEP), identifiers=()
    )

    assert [(r.outcome, r.held_because) for r in results] == [
        (Outcome.HELD, Reason.UNMATCHED),
        (Outcome.KEPT, None),
    ]


def test_results_and_the_list_never_show_a_name():
    names = _list(PRV_cord=KEEP, Lung_old=_map("Lung_Old"))
    results = _clean(["PRV cord", "Lung old", "Dr X"], names)

    shown = repr(results) + repr(names) + repr(_map("Lung_Old"))

    for value in ("PRV", "cord", "Lung", "Old", "Dr X"):
        assert value not in shown


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_the_review_queue_lists_each_distinct_held_name_once():
    queue = reviewed.ReviewQueue()
    for names in (["Lung_L1", "Heart", "Dr X"], ["Lung_L1"], ["lung l", "LUNG-L"]):
        queue.add(names, _clean(names, _list()))

    assert queue.entries() == (
        reviewed.PendingName("Dr X", frozenset({Reason.UNMATCHED}), 1),
        reviewed.PendingName("LUNG-L", frozenset({Reason.WOULD_DUPLICATE}), 1),
        reviewed.PendingName("Lung_L1", frozenset({Reason.UNMATCHED}), 2),
        reviewed.PendingName("lung l", frozenset({Reason.WOULD_DUPLICATE}), 1),
    )
    assert queue.summary() == {Reason.UNMATCHED: 2, Reason.WOULD_DUPLICATE: 2}
    assert "Lung" not in repr(queue) and "Dr X" not in repr(queue.entries()[0])


def test_the_review_queue_needs_one_result_per_name():
    with pytest.raises(ValueError, match="one result for each name"):
        reviewed.ReviewQueue().add(["Lung_L1", "Heart"], _clean(["Heart"], _list()))


def test_several_emptied_names_are_not_duplicates():
    results = _clean(
        ["A b", "C d", "Lung_L1"], _list(A_b=EMPTY, C_d=EMPTY), empty_held=True
    )

    assert [r.outcome for r in results] == [
        Outcome.EMPTIED,
        Outcome.EMPTIED,
        Outcome.EMPTIED_UNREVIEWED,
    ]


def test_nul_padding_is_removed_before_the_list_is_consulted():
    assert _written(_clean(["PRV cord\x00"], _list(PRV_cord=KEEP))) == [
        (Outcome.KEPT, "PRV cord")
    ]


def test_the_review_queue_counts_structure_sets_and_merges_reasons():
    queue = reviewed.ReviewQueue()
    first = ["Hand L", "Hand L ", "Lung_L1\x00"]
    queue.add(first, _clean(first, _list(), identifiers=["Hand^Jo"]))
    second = ["Hand L"]
    queue.add(second, _clean(second, _list(Hand_L=EMPTY), identifiers=["Hand^Jo"]))
    queue.add(["Hand L"], _clean(["Hand L"], _list(Hand_L=KEEP), identifiers=["Hand"]))

    assert queue.entries() == (
        reviewed.PendingName("Hand L", frozenset({Reason.ECHOES_IDENTIFIER}), 2),
        reviewed.PendingName("Lung_L1", frozenset({Reason.UNMATCHED}), 1),
    )
