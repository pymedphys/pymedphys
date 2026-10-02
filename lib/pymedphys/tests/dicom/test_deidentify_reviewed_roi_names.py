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
"""The reviewed-names list for ROI Name cleaning.

Every ROI Name here is synthetic.
"""

import json
import os
import pathlib
from unittest import mock

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import reviewed_roi_names as reviewed
from pymedphys._dicom.deidentify.reviewed_roi_names import Review, ReviewedName

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
