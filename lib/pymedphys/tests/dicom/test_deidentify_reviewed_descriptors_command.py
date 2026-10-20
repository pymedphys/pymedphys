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
"""The private command that records reviewers' descriptor decisions.

Every descriptor value here is synthetic.
"""

import csv
import io
import pathlib
import subprocess
import sys

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import reviewed_descriptors as reviewed
from pymedphys._dicom.deidentify import reviewed_descriptors_command as command
from pymedphys._dicom.deidentify.reviewed_descriptors import (
    Outcome,
    ReviewedDescriptor,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import Review

# Words that appear only in values or paths, so a message that holds one
# quotes a value or a path.
SENTINELS = ("Smithers", "Boost", "Quokka", "Wombat", "Bilby", "secretdir")
SERIES_DESCRIPTION = "(0008,103E)"
IMAGE_COMMENTS = "(0020,4000)"


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
def test_decisions_from_a_csv_start_a_new_list_that_cleaning_applies(
    tmp_path, custodian
):
    decisions = _csv(
        tmp_path / "secretdir-decisions.csv",
        "attribute,value,decision,to\r\n"
        '"(0008,103E)",Smithers protocol,empty,\r\n'
        "SeriesDescription,Quokka AX,keep,\r\n"
        '"(0008,103e)",Wombat old,map,Wombat Boost\r\n'
        'ImageComments,"Quokka\r\nsecond line",keep,\r\n',
    )
    listed = custodian / "reviewed.json"

    status, stdout, stderr = _run(listed, decisions)

    assert status == command.EXIT_RECORDED
    assert stdout.splitlines() == [
        "started a new reviewed descriptors list",
        "decisions recorded: 4",
        "  new: 4",
        "values in the list: 4",
    ]
    _assert_quotes_nothing(stdout, stderr)
    opened = reviewed.ReviewedDescriptors.open(listed)
    assert opened.get(SERIES_DESCRIPTION, "Smithers protocol") == ReviewedDescriptor(
        Review.EMPTY
    )
    assert opened.get(SERIES_DESCRIPTION, "Wombat old") == ReviewedDescriptor(
        Review.MAP, "Wombat Boost"
    )
    assert opened.get(IMAGE_COMMENTS, "Quokka\r\nsecond line") == ReviewedDescriptor(
        Review.KEEP
    )
    cleaned = reviewed.clean_descriptor_values(
        SERIES_DESCRIPTION,
        ["Quokka AX", "Wombat old", "Smithers protocol", "Bilby"],
        opened,
        identifiers=(),
    )
    assert [c.outcome for c in cleaned] == [
        Outcome.KEPT,
        Outcome.MAPPED,
        Outcome.EMPTIED,
        Outcome.HELD,
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_later_decisions_are_added_and_a_different_one_needs_replace(
    tmp_path, custodian
):
    listed = custodian / "reviewed.json"
    first = "attribute,value,decision\nSeriesDescription,Quokka,keep\n"
    _run(listed, _csv(tmp_path / "first.csv", first))
    second = _csv(
        tmp_path / "second.csv",
        "attribute,value,decision\n"
        "SeriesDescription,Quokka,empty\n"
        "SeriesDescription,Bilby,keep\n",
    )

    refused = _run(listed, second)
    status, stdout, _ = _run(listed, second, "--replace")

    assert refused[0] == command.EXIT_NOT_RECORDED
    assert "line 2 gives a value a decision other than the list's" in refused[2]
    assert status == command.EXIT_RECORDED
    assert stdout.splitlines() == [
        "decisions recorded: 2",
        "  new: 1",
        "  replaced: 1",
        "values in the list: 2",
    ]
    opened = reviewed.ReviewedDescriptors.open(listed)
    assert opened.get(SERIES_DESCRIPTION, "Quokka").review is Review.EMPTY


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_a_value_longer_than_the_csv_modules_default_limit_is_recorded(
    tmp_path, custodian
):
    # UT and UC values are not limited to the 131,072 characters that the csv
    # module allows by default.
    limit = csv.field_size_limit()
    long_value = "Quokka " * 30_000
    assert len(long_value) > limit
    decisions = _csv(
        tmp_path / "decisions.csv",
        "attribute,value,decision\n"
        f"SpecimenDetailedDescription,{long_value.strip()},empty\n",
    )
    listed = custodian / "reviewed.json"

    status, stdout, stderr = _run(listed, decisions)

    assert status == command.EXIT_RECORDED, stderr
    assert "decisions recorded: 1" in stdout
    assert csv.field_size_limit() == limit
    opened = reviewed.ReviewedDescriptors.open(listed)
    assert opened.get("(0040,0602)", long_value.strip()) == ReviewedDescriptor(
        Review.EMPTY
    )


def test_one_value_is_decided_on_separately_for_each_attribute(tmp_path, custodian):
    listed = custodian / "reviewed.json"
    decisions = _csv(
        tmp_path / "decisions.csv",
        "attribute,value,decision\n"
        "SeriesDescription,Quokka,keep\n"
        "ProtocolName,Quokka,empty\n"
        "SeriesDescription,Quokka,keep\n",
    )

    status, stdout, _ = _run(listed, decisions)

    assert status == command.EXIT_RECORDED
    assert "decisions recorded: 2" in stdout


def test_different_decisions_on_one_value_in_the_file_are_refused(tmp_path, custodian):
    decisions = _csv(
        tmp_path / "decisions.csv",
        "attribute,value,decision\n"
        "SeriesDescription,Quokka,keep\n"
        '"(0008,103E)",Quokka,empty\n',
    )

    status, _, stderr = _run(custodian / "reviewed.json", decisions)

    assert status == command.EXIT_NOT_RECORDED
    assert "lines 2 and 3 give one value different decisions" in stderr


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
@pytest.mark.parametrize(
    "text, problem",
    [
        ("", "has no header"),
        ("tag,value,decision\n", "needs the columns attribute, value, and decision"),
        ("attribute,value,decision\n", "holds no decisions"),
        (
            "attribute,value,decision\nPatientName,Smithers,keep\n",
            "line 2: the attribute is not a descriptor",
        ),
        (
            "attribute,value,decision\nROIName,Quokka,keep\n",
            "line 2: the attribute is not a descriptor",
        ),
        (
            "attribute,value,decision\nseriesdescription,Quokka,keep\n",
            "line 2: the attribute is not a descriptor",
        ),
        (
            "attribute,value,decision\nSeriesDescription,Quokka,Smithers\n",
            "line 2: the decision must be",
        ),
        (
            "attribute,value,decision\nSeriesDescription,Quokka,map\n",
            "line 2: a mapping needs a value",
        ),
        (
            "attribute,value,decision,to\nSequenceName,Quokka,map,WombatBoostWombat\n",
            "line 2: the value to write is longer than SH allows",
        ),
        (
            "attribute,value,decision\nSeriesDescription,,keep\n",
            "line 2: the value is empty",
        ),
        (
            "attribute,value,decision\nSeriesDescription,Quokka\\Boost,keep\n",
            "line 2: the value holds a backslash",
        ),
        (
            "attribute,value,decision\nSeriesDescription,Quokka,keep,extra\n",
            "line 2 has more cells",
        ),
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


@pytest.mark.deid_requirement("PS3.15-E.3.5-01")
def test_the_list_is_refused_inside_a_protected_directory(tmp_path, home):
    decisions = _csv(
        tmp_path / "decisions.csv",
        "attribute,value,decision\nSeriesDescription,Quokka,keep\n",
    )
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
        assert "refusing to keep a reviewed descriptors list" in stderr
        _assert_quotes_nothing(stderr)
        assert not listed.exists()


def test_a_list_that_cannot_be_written_is_reported_without_its_path(tmp_path):
    decisions = _csv(
        tmp_path / "decisions.csv",
        "attribute,value,decision\nSeriesDescription,Quokka,keep\n",
    )
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


@pytest.mark.parametrize(
    "text, tag",
    [
        ("(0008,103E)", SERIES_DESCRIPTION),
        ("(0008,103e)", SERIES_DESCRIPTION),
        ("SeriesDescription", SERIES_DESCRIPTION),
        ("SequenceName", "(0018,0024)"),
        ("ROIName", None),
        ("(0010,0010)", None),
        ("0008103E", None),
        ("", None),
        ('(0019,"GEMS_ACQU_01",9E) LO', '(0019,"GEMS_ACQU_01",9E) LO'),
        ('(0019,"GEMS_ACQU_01",9e) LO', None),
        ('(0019,"GEMS_ACQU_01",23) DS', None),
    ],
)
def test_an_attribute_is_named_by_its_tag_or_keyword(text, tag):
    assert command.attribute_tag(text) == tag


@pytest.mark.deid_requirement("PS3.15-E.3.10-01")
def test_a_decision_on_private_text_is_recorded_by_its_key(tmp_path, custodian):
    decisions = _csv(
        tmp_path / "secretdir-decisions.csv",
        "attribute,value,decision\r\n"
        '"(0019,""GEMS_ACQU_01"",9E) LO",Quokka FSE,keep\r\n',
    )
    listed = custodian / "reviewed.json"

    status, stdout, stderr = _run(listed, decisions)

    assert status == command.EXIT_RECORDED
    _assert_quotes_nothing(stdout, stderr)
    opened = reviewed.ReviewedDescriptors.open(listed)
    assert opened.get('(0019,"GEMS_ACQU_01",9E) LO', "Quokka FSE") == (
        ReviewedDescriptor(Review.KEEP)
    )


def test_it_runs_as_a_module_of_the_private_package(tmp_path, custodian):
    # Like every command of the tool, it stays off the pymedphys command
    # line until release, which test_cli.py checks for the public parser.
    decisions = _csv(
        tmp_path / "decisions.csv",
        "attribute,value,decision\nSeriesDescription,Quokka,keep\n",
    )
    listed = custodian / "reviewed.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pymedphys._dicom.deidentify.reviewed_descriptors_command",
            str(listed),
            str(decisions),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == command.EXIT_RECORDED, completed.stderr
    opened = reviewed.ReviewedDescriptors.open(listed)
    assert opened.get(SERIES_DESCRIPTION, "Quokka") is not None
