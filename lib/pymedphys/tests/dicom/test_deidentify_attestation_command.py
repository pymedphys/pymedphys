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

"""The private command that records a QC reviewer's attestation of a QC pack.

Every name and path here is invented.
"""

import io
import json
import subprocess
import sys
from pathlib import PurePosixPath

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import attestation_command as command
from pymedphys._dicom.deidentify import qc_attestation, qc_store, release_report
from pymedphys._dicom.deidentify.qc_attestation import AttestationRecord, Outcome
from pymedphys._dicom.deidentify.qc_pack import Disposition, InstanceEntry, QcPack

REFERENCE = "A-" + "0123456789abcdef" * 2
# Words that appear only in the reviewer's name or the pack's path, so a
# message that holds one quotes a name or a path.
REVIEWER = "Quokka Wombatson"
SENTINELS = ("Quokka", "Wombatson", "secretdir")
EVERY_REVIEW = (
    "--reviewed-retained-strings",
    "--reviewed-series",
    "--reviewed-high-risk-instances",
)


@pytest.fixture(name="pack")
def fixture_pack(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    pack = QcPack(
        REFERENCE,
        (
            InstanceEntry(
                0,
                "/imports/a.dcm",
                Disposition.RELEASED,
                output=PurePosixPath("ZQ0001/2.25.1/2.25.2/2.25.3.dcm"),
            ),
        ),
    )
    return qc_store.write_qc_pack(
        pack, tmp_path / "secretdir-qc", release_directory=release
    ).parent


def _run(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    status = command.main(list(argv), stdout=stdout, stderr=stderr)
    return status, stdout.getvalue(), stderr.getvalue()


def _assert_quotes_nothing(*texts):
    for text in texts:
        for sentinel in SENTINELS:
            assert sentinel not in text


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_an_attestation_is_recorded_beside_the_pack(pack):
    status, stdout, stderr = _run(
        str(pack), "--reviewer", REVIEWER, "--outcome", "attested", *EVERY_REVIEW
    )

    assert status == command.EXIT_RECORDED, stderr
    assert qc_attestation.attestation_record(pack) == AttestationRecord(
        REFERENCE, Outcome.ATTESTED
    )
    written = json.loads(
        (pack / qc_attestation.ATTESTATION_FILE).read_text(encoding="ascii")
    )
    assert written["reviewer"] == REVIEWER
    assert written["coverage"] == {
        "retained_strings": True,
        "series": True,
        "high_risk_instances": True,
    }
    assert stdout.splitlines() == [
        f"QC pack {REFERENCE}: attested",
        "  every distinct retained string: reviewed",
        "  every series: reviewed",
        "  every instance in high-risk categories: reviewed",
        "  checked for its intended use: not stated",
        "  residual risk accepted: not stated",
        "the release report published with the run is unchanged",
    ]
    _assert_quotes_nothing(stdout, stderr)


@pytest.mark.deid_requirement("MIDI-BP-17")
@pytest.mark.parametrize(
    "use, risk, expected",
    [
        ("yes", "yes", (True, True)),
        ("no", "yes", (False, True)),
        ("yes", None, (True, None)),
    ],
)
def test_the_releasers_confirmations_reach_the_record(pack, use, risk, expected):
    argv = [str(pack), "--reviewer", REVIEWER, "--outcome", "attested", *EVERY_REVIEW]
    argv += ["--intended-use-checked", use]
    if risk is not None:
        argv += ["--residual-risk-accepted", risk]

    status, stdout, stderr = _run(*argv)

    assert status == command.EXIT_RECORDED, stderr
    assert qc_attestation.attestation_record(pack) == AttestationRecord(
        REFERENCE, Outcome.ATTESTED, *expected
    )
    words = {True: "yes", False: "no", None: "not stated"}
    assert (
        f"  checked for its intended use: {words[expected[0]]}" in stdout.splitlines()
    )
    assert f"  residual risk accepted: {words[expected[1]]}" in stdout.splitlines()


def test_a_rejection_records_the_reviews_that_were_done(pack):
    status, stdout, _ = _run(
        str(pack),
        "--reviewer",
        REVIEWER,
        "--outcome",
        "rejected",
        "--reviewed-series",
    )

    assert status == command.EXIT_RECORDED
    written = json.loads(
        (pack / qc_attestation.ATTESTATION_FILE).read_text(encoding="ascii")
    )
    assert written["outcome"] == "rejected"
    assert written["coverage"] == {
        "retained_strings": False,
        "series": True,
        "high_risk_instances": False,
    }
    assert "  every series: reviewed" in stdout.splitlines()


@pytest.mark.deid_requirement("MIDI-BP-17")
@pytest.mark.parametrize("missing", EVERY_REVIEW)
def test_attested_without_every_review_records_nothing(pack, missing):
    reviews = [flag for flag in EVERY_REVIEW if flag != missing]

    status, stdout, stderr = _run(
        str(pack), "--reviewer", REVIEWER, "--outcome", "attested", *reviews
    )

    assert status == command.EXIT_NOT_RECORDED
    assert "every review that D-017 requires" in stderr
    assert "nothing was recorded" in stderr
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()
    assert not stdout
    _assert_quotes_nothing(stderr)


def test_a_pack_is_attested_once(pack):
    _run(str(pack), "--reviewer", REVIEWER, "--outcome", "attested", *EVERY_REVIEW)
    before = (pack / qc_attestation.ATTESTATION_FILE).read_bytes()

    status, _, stderr = _run(str(pack), "--reviewer", "Bilby", "--outcome", "rejected")

    assert status == command.EXIT_NOT_RECORDED
    assert "already been attested" in stderr
    assert (pack / qc_attestation.ATTESTATION_FILE).read_bytes() == before


@pytest.mark.deid_requirement("MIDI-BP-17")
@pytest.mark.parametrize("where", ["release", "missing", "parent", "file"])
def test_a_path_that_is_not_a_qc_pack_is_refused(tmp_path, pack, where):
    target = {
        "release": tmp_path / "release",
        "missing": tmp_path / "secretdir-missing",
        "parent": pack.parent,
        "file": pack / qc_store.PACK_FILE,
    }[where]

    status, stdout, stderr = _run(
        str(target), "--reviewer", REVIEWER, "--outcome", "rejected"
    )

    assert status == command.EXIT_NOT_RECORDED
    assert "holds no QC pack" in stderr
    assert not stdout
    assert not (target / qc_attestation.ATTESTATION_FILE).exists()
    _assert_quotes_nothing(stderr)


def test_a_directory_with_a_pack_but_no_marker_is_refused(pack):
    (pack / qc_store.MARKER_FILE).unlink()

    status, _, stderr = _run(str(pack), "--reviewer", REVIEWER, "--outcome", "rejected")

    assert status == command.EXIT_NOT_RECORDED
    assert "holds no QC pack" in stderr
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


def test_a_pack_of_another_format_is_refused(pack):
    path = pack / qc_store.PACK_FILE
    document = json.loads(path.read_text(encoding="ascii"))
    path.chmod(0o600)
    path.write_text(json.dumps({**document, "format": "other/1"}), encoding="ascii")

    status, _, stderr = _run(str(pack), "--reviewer", REVIEWER, "--outcome", "rejected")

    assert status == command.EXIT_NOT_RECORDED
    assert "not of its format" in stderr
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["PACK"],
        ["PACK", "--reviewer", REVIEWER],
        ["PACK", "--outcome", "attested"],
        ["PACK", "--reviewer", REVIEWER, "--outcome", "not-attested"],
        ["PACK", "--reviewer", REVIEWER, "--outcome", "rejected", "--Quokka"],
        [
            "PACK",
            "--reviewer",
            REVIEWER,
            "--outcome",
            "rejected",
            "--intended-use-checked",
            "maybe",
        ],
    ],
)
def test_arguments_that_cannot_be_parsed_are_refused_without_quoting(argv):
    with pytest.raises(SystemExit) as raised:
        _run(*argv)
    assert raised.value.code == command.EXIT_USAGE


def test_a_usage_error_quotes_no_argument(capsys):
    stderr = io.StringIO()
    with pytest.raises(SystemExit):
        command.main(
            ["secretdir", "--reviewer", REVIEWER, "--outcome", "Wombatson"],
            stdout=io.StringIO(),
            stderr=stderr,
        )
    _assert_quotes_nothing(stderr.getvalue(), capsys.readouterr().err)


def test_an_empty_reviewer_records_nothing(pack):
    status, _, stderr = _run(str(pack), "--reviewer", " ", "--outcome", "rejected")

    assert status == command.EXIT_NOT_RECORDED
    assert "needs its reviewer" in stderr
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


@pytest.mark.deid_requirement("MIDI-BP-17")
def test_the_release_report_record_comes_from_the_pack(pack):
    # The report written at run time records not attested; the record that a
    # report takes is read from the pack, which now holds the attestation.
    assert qc_attestation.attestation_record(pack).outcome is Outcome.NOT_ATTESTED

    _run(str(pack), "--reviewer", REVIEWER, "--outcome", "attested", *EVERY_REVIEW)

    record = qc_attestation.attestation_record(pack)
    assert record == AttestationRecord(REFERENCE, Outcome.ATTESTED)
    assert release_report.AttestationRecord is AttestationRecord


def test_it_runs_as_a_module_of_the_private_package(pack):
    # Like every command of the tool, it stays off the pymedphys command
    # line until release, which a test of the public parser checks.
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pymedphys._dicom.deidentify.attestation_command",
            str(pack),
            "--reviewer",
            REVIEWER,
            "--outcome",
            "attested",
            *EVERY_REVIEW,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == command.EXIT_RECORDED, completed.stderr
    assert qc_attestation.attestation_record(pack).outcome is Outcome.ATTESTED
    _assert_quotes_nothing(completed.stdout, completed.stderr)
