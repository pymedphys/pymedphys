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
"""The private command that records reviewers' ROI Name decisions.

Every ROI Name here is synthetic.
"""

import io
import pathlib
import subprocess
import sys

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import reviewed_names_command as command
from pymedphys._dicom.deidentify import reviewed_roi_names as reviewed
from pymedphys._dicom.deidentify.reviewed_roi_names import (
    Outcome,
    Review,
    ReviewedName,
)

# Words that appear only in names or values, so a message that holds one
# quotes a name, a value, or a path.
SENTINELS = ("Smithers", "Boost", "Quokka", "Wombat", "Bilby", "secretdir")


@pytest.fixture(name="home", autouse=True)
def fixture_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture(name="custodian")
def fixture_custodian(tmp_path):
    directory = tmp_path / "secretdir-custodian"
    directory.mkdir()
    return directory


def _csv(path, text):
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _run(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        status = command.main([str(a) for a in argv], stdout=stdout, stderr=stderr)
    except SystemExit as exit_:
        status = exit_.code
    return status, stdout.getvalue(), stderr.getvalue()


def _assert_quotes_nothing(*texts):
    for text in texts:
        for sentinel in SENTINELS:
            assert sentinel not in text


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_decisions_from_a_csv_start_a_new_list_that_a_run_applies(tmp_path, custodian):
    decisions = _csv(
        tmp_path / "secretdir-decisions.csv",
        "roi_name,decision,to\r\n"
        "PTV Smithers,empty,\r\n"
        "Quokka,keep,\r\n"
        "Wombat old,map,Wombat_Boost\r\n",
    )
    listed = custodian / "reviewed.json"

    status, stdout, stderr = _run(listed, decisions)

    assert status == command.EXIT_RECORDED
    assert stdout.splitlines() == [
        "started a new reviewed-names list",
        "decisions recorded: 3",
        "  new: 3",
        "names in the list: 3",
    ]
    _assert_quotes_nothing(stdout, stderr)
    names = reviewed.ReviewedNames.open(listed)
    assert names.get("PTV Smithers") == ReviewedName(Review.EMPTY)
    assert names.get("Quokka") == ReviewedName(Review.KEEP)
    assert names.get("Wombat old") == ReviewedName(Review.MAP, "Wombat_Boost")
    cleaned = reviewed.clean_roi_names(
        ["Quokka", "Wombat old", "PTV Smithers", "Bilby"],
        None,
        names,
        identifiers=(),
    )
    assert [c.outcome for c in cleaned] == [
        Outcome.KEPT,
        Outcome.MAPPED,
        Outcome.EMPTIED,
        Outcome.HELD,
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_later_decisions_are_added_to_the_list(tmp_path, custodian):
    listed = custodian / "reviewed.json"
    _run(listed, _csv(tmp_path / "first.csv", "roi_name,decision\nQuokka,keep\n"))

    status, stdout, _ = _run(
        listed,
        _csv(tmp_path / "second.csv", "roi_name,decision\nQuokka,keep\nBilby,empty\n"),
    )

    assert status == command.EXIT_RECORDED
    assert stdout.splitlines() == [
        "decisions recorded: 2",
        "  new: 1",
        "  unchanged: 1",
        "names in the list: 2",
    ]
    names = reviewed.ReviewedNames.open(listed)
    assert names.get("Bilby") == ReviewedName(Review.EMPTY)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_different_decision_on_a_listed_name_is_refused_unless_replaced(
    tmp_path, custodian
):
    listed = custodian / "reviewed.json"
    _run(listed, _csv(tmp_path / "first.csv", "roi_name,decision\nQuokka,keep\n"))
    before = listed.read_bytes()
    changed = _csv(
        tmp_path / "changed.csv",
        "roi_name,decision,to\nBilby,empty,\nQuokka,map,Quokka_Boost\n",
    )

    status, stdout, stderr = _run(listed, changed)

    assert status == command.EXIT_NOT_RECORDED
    assert stdout == ""
    assert "line 3" in stderr
    assert "--replace" in stderr
    _assert_quotes_nothing(stderr)
    assert listed.read_bytes() == before

    status, stdout, _ = _run(listed, changed, "--replace")

    assert status == command.EXIT_RECORDED
    assert "  replaced: 1" in stdout.splitlines()
    names = reviewed.ReviewedNames.open(listed)
    assert names.get("Quokka") == ReviewedName(Review.MAP, "Quokka_Boost")
    assert names.get("Bilby") == ReviewedName(Review.EMPTY)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_different_decisions_on_one_name_in_the_file_are_refused(tmp_path, custodian):
    listed = custodian / "reviewed.json"
    decisions = _csv(
        tmp_path / "decisions.csv",
        "roi_name,decision\nQuokka,keep\nBilby,keep\n Quokka ,empty\n",
    )

    status, _, stderr = _run(listed, decisions, "--replace")

    assert status == command.EXIT_NOT_RECORDED
    assert "lines 2 and 4" in stderr
    _assert_quotes_nothing(stderr)
    assert not listed.exists()


def test_the_same_decision_twice_in_the_file_is_recorded_once(tmp_path, custodian):
    listed = custodian / "reviewed.json"
    decisions = _csv(
        tmp_path / "decisions.csv", "roi_name,decision\nQuokka,keep\nQuokka,keep\n"
    )

    status, stdout, _ = _run(listed, decisions)

    assert status == command.EXIT_RECORDED
    assert stdout.splitlines()[1:] == [
        "decisions recorded: 1",
        "  new: 1",
        "names in the list: 1",
    ]


def test_padding_case_and_extra_columns_are_tolerated(tmp_path, custodian):
    # A spreadsheet adds a byte order mark, and a reviewer may pad cells,
    # write a decision in capitals, or keep notes in a column of their own.
    listed = custodian / "reviewed.json"
    decisions = tmp_path / "decisions.csv"
    decisions.write_bytes(
        "﻿Notes, ROI_Name ,Decision,TO\n"
        "Smithers,  Wombat old  , MAP , Wombat_Boost \n"
        ",Quokka,Keep,\n"
        ",,,\n".encode("utf-8")
    )

    status, _, _ = _run(listed, decisions)

    assert status == command.EXIT_RECORDED
    names = reviewed.ReviewedNames.open(listed)
    assert len(names) == 2
    assert names.get("Wombat old") == ReviewedName(Review.MAP, "Wombat_Boost")
    assert names.get("Quokka") == ReviewedName(Review.KEEP)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "text, problem",
    [
        ("", "has no header"),
        ("name,decision\nQuokka,keep\n", "needs the columns roi_name and decision"),
        ("roi_name,decision,decision\nQuokka,keep,keep\n", "repeats a column"),
        ("roi_name,decision\n", "holds no decisions"),
        ("roi_name,decision\nQuokka,Smithers\n", "line 2: the decision must be"),
        ("roi_name,decision\nQuokka,map\n", "line 2: a mapping needs a name"),
        ("roi_name,decision,to\nQuokka,keep,Boost\n", "line 2: only a mapping"),
        (
            "roi_name,decision,to\nQuokka,map,Wombat\\Boost\n",
            "line 2: a mapping needs a name",
        ),
        ("roi_name,decision\n,keep\n", "line 2: the ROI Name is empty"),
        ("roi_name,decision\nQuokka\tBoost,keep\n", "line 2: the ROI Name holds"),
        ("roi_name,decision\nQuokka,keep,extra\n", "line 2 has more cells"),
        ('roi_name,decision\n"Quokka,keep\n', "could not be read as CSV"),
    ],
)
def test_a_malformed_decisions_file_is_refused_and_nothing_is_written(
    tmp_path, custodian, text, problem
):
    listed = custodian / "reviewed.json"

    status, stdout, stderr = _run(listed, _csv(tmp_path / "decisions.csv", text))

    assert status == command.EXIT_NOT_RECORDED
    assert stdout == ""
    assert problem in stderr
    _assert_quotes_nothing(stderr)
    assert not listed.exists()


def test_a_decisions_file_that_is_not_utf8_is_refused(tmp_path, custodian):
    decisions = tmp_path / "secretdir-decisions.csv"
    decisions.write_bytes("roi_name,decision\nQuokka Bœuf,keep\n".encode("cp1252"))

    status, _, stderr = _run(custodian / "reviewed.json", decisions)

    assert status == command.EXIT_NOT_RECORDED
    assert "is not UTF-8" in stderr
    _assert_quotes_nothing(stderr)


def test_a_missing_decisions_file_is_refused_without_its_path(tmp_path, custodian):
    status, _, stderr = _run(
        custodian / "reviewed.json", tmp_path / "secretdir-missing.csv"
    )

    assert status == command.EXIT_NOT_RECORDED
    assert "could not be read" in stderr
    _assert_quotes_nothing(stderr)


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_the_list_is_refused_inside_a_protected_directory(tmp_path, home):
    decisions = _csv(tmp_path / "decisions.csv", "roi_name,decision\nQuokka,keep\n")
    output = tmp_path / "secretdir-output"
    output.mkdir()
    configuration = home / ".pymedphys"
    configuration.mkdir()

    for listed, extra in [
        (output / "reviewed.json", ["--protect", output]),
        (configuration / "reviewed.json", []),
    ]:
        status, _, stderr = _run(listed, decisions, *extra)

        assert status == command.EXIT_NOT_RECORDED
        assert "refusing to keep a reviewed-names list" in stderr
        _assert_quotes_nothing(stderr)
        assert not listed.exists()


def test_an_unreadable_list_is_refused_and_left_alone(tmp_path, custodian):
    listed = custodian / "reviewed.json"
    listed.write_text('{"Smithers": "Boost"}', encoding="utf-8")
    decisions = _csv(tmp_path / "decisions.csv", "roi_name,decision\nQuokka,keep\n")

    status, _, stderr = _run(listed, decisions)

    assert status == command.EXIT_NOT_RECORDED
    assert "is not a pymedphys-deid-reviewed-roi-names/1 file" in stderr
    _assert_quotes_nothing(stderr)
    assert listed.read_text(encoding="utf-8") == '{"Smithers": "Boost"}'


def test_a_list_that_cannot_be_written_is_reported_without_its_path(tmp_path):
    decisions = _csv(tmp_path / "decisions.csv", "roi_name,decision\nQuokka,keep\n")
    listed = tmp_path / "secretdir-missing" / "reviewed.json"

    status, stdout, stderr = _run(listed, decisions)

    assert status == command.EXIT_NOT_RECORDED
    assert stdout == ""
    assert "could not be written" in stderr
    _assert_quotes_nothing(stderr)


def test_an_argument_error_quotes_no_argument(tmp_path):
    status, _, stderr = _run(tmp_path / "secretdir-a", "--secretdir-unknown")

    assert status == command.EXIT_USAGE
    _assert_quotes_nothing(stderr)


def test_it_runs_as_a_module_of_the_private_package(tmp_path, custodian):
    # Like every command of the tool, it stays off the pymedphys command
    # line until release, which test_cli.py checks for the public parser.
    decisions = _csv(tmp_path / "decisions.csv", "roi_name,decision\nQuokka,keep\n")
    listed = custodian / "reviewed.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pymedphys._dicom.deidentify.reviewed_names_command",
            str(listed),
            str(decisions),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == command.EXIT_RECORDED, completed.stderr
    assert reviewed.ReviewedNames.open(listed).get("Quokka") is not None
