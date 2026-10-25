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

"""The private command that records a region rule from a reviewed QC pack.

A first run under the Clean Pixel Data Option, without rules, holds every
image for review; a reviewer revises one image's regions with the band that
its invented scanner burns text into, and attests the pack; the command
records the band as a rule for that scanner; and a later run with the rules
blacks the band out in the scanner's other image. Every file is synthetic,
every manufacturer and model name invented, and every finder a stand-in
that gives fixed regions.
"""

import io
import json
import pathlib
import subprocess
import sys
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import pixel_region_rules_command as command
from pymedphys._dicom.deidentify import qc_attestation
from pymedphys._dicom.deidentify.pixel_region_rules import (
    PixelRegionRules,
    PixelRegionRulesError,
)
from pymedphys._dicom.deidentify.qc_attestation import (
    Outcome,
    Redaction,
    RedactionVerdict,
)
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _synthetic_references as synthetic
from .test_deidentify_pixel_cleaning import BOX, _ct, _frame
from .test_deidentify_pixel_region_rules_run import (
    BAND,
    MANUFACTURER,
    MODEL,
    RULE,
    _scanned,
    _transform,
)
from .test_deidentify_redaction_review import COMPLETE, WHEN, _attest, _run, _write

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

# The scanner's two images, an image of another model, and an image without
# a Manufacturer, which no rule can match.
_MATCHED, _ALSO_MATCHED, _OTHER, _UNKEYED = (
    "0-matched.dcm",
    "1-matched.dcm",
    "2-other.dcm",
    "3-unkeyed.dcm",
)
# Words that appear only in values or paths, so that a message holding one
# quotes a value or a path.
SENTINELS = (MANUFACTURER, MODEL, "Acme", "secretdir")


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


def _images():
    datasets = {
        _MATCHED: _scanned(_frame(start=100)),
        _ALSO_MATCHED: _scanned(_frame(start=200)),
        _OTHER: _scanned(_frame(start=300), model="Scanner 10"),
        _UNKEYED: _ct(_frame(start=400)),
    }
    for number, dataset in enumerate(datasets.values()):
        dataset.SOPInstanceUID = f"2.25.40{number + 1}"
        dataset.InstanceNumber = number + 1
    return {name: synthetic.written(dataset) for name, dataset in datasets.items()}


@pytest.fixture(name="first_run")
def fixture_first_run(tmp_path):
    """A first run without rules, whose QC pack holds every image: the pack's
    directory, the source directory, and the run positions by file name."""
    source = tmp_path / "secretdir-source"
    _write(source, _images())
    result = _run(tmp_path / "first", source, _transform(PixelRegionRules.empty()))
    document = json.loads(result.qc_pack.read_text("utf-8"))
    positions = {
        Path(entry["source"]).name: entry["position"] for entry in document["instances"]
    }
    return result.qc_pack.parent, source, positions


def _reviewed(first_run, *verdicts):
    """Attest the first run's pack, revising the scanner's first image with
    the band, accepting the image without a Manufacturer, and rejecting the
    other model's image, unless ``verdicts`` are given."""
    pack, _, positions = first_run
    _attest(
        pack,
        verdicts
        or (
            RedactionVerdict(positions[_MATCHED], Redaction.REVISED, ((0, (BAND,)),)),
            RedactionVerdict(positions[_UNKEYED], Redaction.ACCEPTED),
            RedactionVerdict(positions[_OTHER], Redaction.REJECTED),
        ),
    )
    return pack


def _main(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        status = command.main([str(a) for a in argv], stdout=stdout, stderr=stderr)
    except SystemExit as exit_:
        status = exit_.code
    return status, stdout.getvalue(), stderr.getvalue()


def _region(box):
    return ["--region", box.top, box.left, box.bottom, box.right]


def _assert_quotes_nothing(*texts):
    for text in texts:
        for sentinel in SENTINELS:
            assert sentinel not in text


# Recording a rule.


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_region_that_a_reviewer_added_is_recorded_for_the_images_kind(
    first_run, custodian
):
    pack = _reviewed(first_run)
    _, _, positions = first_run
    store = custodian / "rules.json"

    status, stdout, stderr = _main(
        store, pack, positions[_MATCHED], *_region(BAND), "--protect", first_run[1]
    )

    assert status == command.EXIT_RECORDED, stderr
    assert PixelRegionRules.open(store).get(RULE) == (BAND,)
    reference = qc_attestation.attestation_record(pack).reference
    assert stdout.splitlines() == [
        "started a new region rules store",
        f"QC pack: {reference}",
        f"instance: {positions[_MATCHED]}",
        "rule: new",
        "regions in the rule: 1",
        "  [4, 0, 6, 8]",
        "rules in the store: 1",
    ]
    _assert_quotes_nothing(stdout, stderr)


def test_a_region_of_the_pack_that_a_reviewer_accepted_can_be_recorded(
    first_run, custodian
):
    _, _, positions = first_run
    pack = _reviewed(
        first_run, RedactionVerdict(positions[_ALSO_MATCHED], Redaction.ACCEPTED)
    )
    store = custodian / "rules.json"

    recorded = command.record_rule(store, pack, positions[_ALSO_MATCHED], (BOX,))

    assert recorded.change is command.Change.NEW
    assert recorded.created and recorded.rules == 1
    assert PixelRegionRules.open(store).get(RULE) == (BOX,)


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_later_run_with_the_recorded_rule_blacks_out_its_region(
    tmp_path, first_run, custodian
):
    pack = _reviewed(first_run)
    pack_directory, source, positions = first_run
    store = custodian / "rules.json"
    command.record_rule(store, pack, positions[_MATCHED], (BAND,))

    later = _run(tmp_path / "later", source, _transform(PixelRegionRules.open(store)))

    document = json.loads(later.qc_pack.read_text("utf-8"))
    names = {
        entry["position"]: Path(entry["source"]).name for entry in document["instances"]
    }
    rule_boxes = {
        names[entry["position"]]: entry["rule_boxes"]
        for entry in document["redactions"]
    }
    assert rule_boxes == {
        _MATCHED: [[4, 0, 6, 8]],
        _ALSO_MATCHED: [[4, 0, 6, 8]],
        _OTHER: [],
        _UNKEYED: [],
    }
    assert pack_directory.exists()


def test_a_copy_of_the_source_file_can_be_given_in_its_place(
    tmp_path, first_run, custodian
):
    pack = _reviewed(first_run)
    _, source, positions = first_run
    moved = tmp_path / "secretdir-moved.dcm"
    moved.write_bytes((source / _MATCHED).read_bytes())
    (source / _MATCHED).unlink()
    store = custodian / "rules.json"

    status, _, stderr = _main(
        store, pack, positions[_MATCHED], *_region(BAND), "--source", moved
    )

    assert status == command.EXIT_RECORDED, stderr
    assert PixelRegionRules.open(store).get(RULE) == (BAND,)


# A rule that the store already holds for the kind.


def _stored(custodian, *boxes):
    store = custodian / "rules.json"
    rules = PixelRegionRules.open(store)
    rules.record(RULE, boxes)
    rules.save()
    return store


def test_the_same_regions_again_leave_the_rule_unchanged(first_run, custodian):
    pack = _reviewed(first_run)
    store = _stored(custodian, BAND)

    recorded = command.record_rule(store, pack, first_run[2][_MATCHED], (BAND,))

    assert recorded.change is command.Change.UNCHANGED
    assert not recorded.created
    assert PixelRegionRules.open(store).get(RULE) == (BAND,)


def test_other_regions_for_the_kind_are_refused_without_replace_or_add(
    first_run, custodian
):
    pack = _reviewed(first_run)
    store = _stored(custodian, BOX)
    before = store.read_bytes()

    status, stdout, stderr = _main(store, pack, first_run[2][_MATCHED], *_region(BAND))

    assert status == command.EXIT_NOT_RECORDED
    assert stdout == ""
    assert "--replace" in stderr and "--add" in stderr
    assert "nothing was recorded" in stderr
    _assert_quotes_nothing(stderr)
    assert store.read_bytes() == before


def test_replace_makes_the_regions_the_rules_own(first_run, custodian):
    pack = _reviewed(first_run)
    store = _stored(custodian, BOX)

    status, stdout, _ = _main(
        store, pack, first_run[2][_MATCHED], *_region(BAND), "--replace"
    )

    assert status == command.EXIT_RECORDED
    assert "rule: replaced" in stdout.splitlines()
    assert PixelRegionRules.open(store).get(RULE) == (BAND,)


def test_add_adds_the_regions_to_the_rules_own(first_run, custodian):
    pack = _reviewed(first_run)
    store = _stored(custodian, BOX)

    status, stdout, _ = _main(
        store, pack, first_run[2][_MATCHED], *_region(BAND), "--add"
    )

    assert status == command.EXIT_RECORDED
    lines = stdout.splitlines()
    assert "rule: added to" in lines
    assert "regions in the rule: 2" in lines
    assert PixelRegionRules.open(store).get(RULE) == (BOX, BAND)


def test_replace_and_add_cannot_be_given_together(first_run, custodian):
    pack = _reviewed(first_run)

    status, _, stderr = _main(
        custodian / "rules.json",
        pack,
        first_run[2][_MATCHED],
        *_region(BAND),
        "--replace",
        "--add",
    )

    assert status == command.EXIT_USAGE
    _assert_quotes_nothing(stderr)
    assert not (custodian / "rules.json").exists()


# What is refused, leaving the store as it was.


def _refused(store, pack, position, *boxes, **options):
    with pytest.raises(PixelRegionRulesError) as raised:
        command.record_rule(store, pack, position, boxes or (BAND,), **options)
    message = str(raised.value)
    _assert_quotes_nothing(message)
    assert not store.exists()
    return message


def test_a_pack_that_has_not_been_attested_is_refused(first_run, custodian):
    pack, _, positions = first_run

    message = _refused(custodian / "rules.json", pack, positions[_MATCHED])

    assert "has not been attested" in message


def test_a_rejected_pack_is_refused(first_run, custodian):
    pack, _, positions = first_run
    qc_attestation.attest(
        pack,
        reviewer="Quokka Wombatson",
        outcome=Outcome.REJECTED,
        coverage=COMPLETE,
        attested_at=WHEN,
    )

    message = _refused(custodian / "rules.json", pack, positions[_MATCHED])

    assert "rejected" in message


@pytest.mark.parametrize(
    "name, expected",
    [
        (_ALSO_MATCHED, "no verdict that accepts"),
        (_OTHER, "rejected the instance"),
    ],
)
def test_an_instance_without_an_accepting_verdict_is_refused(
    first_run, custodian, name, expected
):
    pack = _reviewed(first_run)

    message = _refused(custodian / "rules.json", pack, first_run[2][name])

    assert expected in message


@pytest.mark.parametrize("position", [99, -1, True, "0"])
def test_a_position_that_the_pack_does_not_list_as_cleaned_is_refused(
    first_run, custodian, position
):
    pack = _reviewed(first_run)

    message = _refused(custodian / "rules.json", pack, position)

    assert "position" in message or "cleaned and previewed" in message


@pytest.mark.parametrize(
    "box",
    [
        # A region of the reviewer's that the pack does not hold.
        TextBox(0, 0, 1, 1),
        # The band with its coordinates transposed.
        TextBox(0, 4, 8, 6),
        # The band one row short.
        TextBox(4, 0, 5, 8),
    ],
)
def test_a_region_that_the_reviewer_did_not_approve_is_refused(
    first_run, custodian, box
):
    pack = _reviewed(first_run)

    message = _refused(custodian / "rules.json", pack, first_run[2][_MATCHED], box)

    assert "region 1 is not among the regions" in message


@pytest.mark.parametrize("boxes", [(), ((4, 0, 6, 8),), [BAND]])
def test_regions_must_be_a_tuple_of_at_least_one_text_box(first_run, custodian, boxes):
    pack = _reviewed(first_run)

    with pytest.raises(PixelRegionRulesError):
        command.record_rule(
            custodian / "rules.json", pack, first_run[2][_MATCHED], boxes
        )


def test_a_source_file_changed_since_the_run_is_refused(first_run, custodian):
    pack = _reviewed(first_run)
    _, source, positions = first_run
    (source / _MATCHED).write_bytes((source / _ALSO_MATCHED).read_bytes())

    message = _refused(custodian / "rules.json", pack, positions[_MATCHED])

    assert "not the file that the QC pack's run read" in message


def test_a_source_file_that_cannot_be_read_is_refused(first_run, custodian):
    pack = _reviewed(first_run)
    _, source, positions = first_run
    (source / _MATCHED).unlink()

    message = _refused(custodian / "rules.json", pack, positions[_MATCHED])

    assert "could not be read" in message
    assert "--source" in message


def test_an_instance_that_no_rule_can_match_is_refused(first_run, custodian):
    pack = _reviewed(first_run)

    message = _refused(custodian / "rules.json", pack, first_run[2][_UNKEYED], BOX)

    assert "no rule can match" in message


def test_a_store_inside_the_qc_pack_is_refused(first_run):
    pack = _reviewed(first_run)

    message = _refused(pack / "rules.json", pack, first_run[2][_MATCHED])

    assert "refusing to keep a pixel region rules store" in message


def test_a_store_inside_a_protected_directory_is_refused(first_run):
    pack = _reviewed(first_run)
    _, source, positions = first_run

    message = _refused(
        source / "rules.json", pack, positions[_MATCHED], protected_dirs=[source]
    )

    assert "refusing to keep a pixel region rules store" in message


def test_a_store_that_cannot_be_written_is_reported_without_its_path(
    tmp_path, first_run
):
    pack = _reviewed(first_run)
    store = tmp_path / "secretdir-missing" / "rules.json"

    status, stdout, stderr = _main(store, pack, first_run[2][_MATCHED], *_region(BAND))

    assert status == command.EXIT_NOT_RECORDED
    assert stdout == ""
    assert "could not be written" in stderr
    _assert_quotes_nothing(stderr)


# The command line.


@pytest.mark.parametrize(
    "argv",
    [
        # No region.
        ["secretdir-store", "secretdir-pack", "0"],
        # A region of three numbers, or of a number that is not whole.
        ["secretdir-store", "secretdir-pack", "0", "--region", "1", "2", "3"],
        ["secretdir-store", "secretdir-pack", "0", "--region", "1", "2", "3", "x"],
        # A position that is not a whole number.
        ["secretdir-store", "secretdir-pack", "secretdir", "--region", "1", "2"],
        ["secretdir-store", "--secretdir-unknown"],
    ],
)
def test_an_argument_error_quotes_no_argument(argv):
    status, _, stderr = _main(*argv)

    assert status == command.EXIT_USAGE
    _assert_quotes_nothing(stderr)


def test_an_empty_region_is_refused(first_run, custodian):
    pack = _reviewed(first_run)

    status, _, stderr = _main(
        custodian / "rules.json",
        pack,
        first_run[2][_MATCHED],
        "--region",
        4,
        0,
        4,
        8,
    )

    assert status == command.EXIT_NOT_RECORDED
    assert "region 1" in stderr
    assert not (custodian / "rules.json").exists()


def test_it_runs_as_a_module_of_the_private_package(first_run, custodian):
    # Like every command of the tool, it stays off the pymedphys command
    # line until release, which test_cli.py checks for the public parser.
    pack = _reviewed(first_run)
    store = custodian / "rules.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pymedphys._dicom.deidentify.pixel_region_rules_command",
            str(store),
            str(pack),
            str(first_run[2][_MATCHED]),
            *map(str, _region(BAND)),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == command.EXIT_RECORDED, completed.stderr
    assert PixelRegionRules.open(store).get(RULE) == (BAND,)
