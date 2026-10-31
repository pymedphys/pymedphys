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

# Each refusal of a statement is a test of its own, sharing the helpers
# below, so they stay in one module.
# pylint: disable = too-many-lines

"""The private command that records an external risk assessment beside a QC pack.

Every name, statement, and path here is invented.
"""

import contextlib
import copy
import dataclasses
import datetime
import inspect
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import attestation_command, policy, qc_store
from pymedphys._dicom.deidentify import readiness, release_report, risk_assessment
from pymedphys._dicom.deidentify import risk_assessment_command as command
from pymedphys._dicom.deidentify import run, run_report
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.face_review import read_face_review
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.qc_attestation import AttestationRecord, Outcome
from pymedphys._dicom.deidentify.qc_pack import Disposition, InstanceEntry, QcPack
from pymedphys._dicom.deidentify.risk_assessment import (
    Assessment,
    Attacker,
    Model,
    Population,
)

from . import _corpus_run

PACK = "A-" + "0123456789abcdef" * 2
OTHER_PACK = "A-" + "fedcba9876543210" * 2
# Words that appear only in the statement's text, the assessor's name, or
# the paths, so that a message that holds one quotes a statement or a path.
SENTINELS = ("Quokka", "Wombatson", "Numbat", "secretdir")
ASSESSOR = "Quokka Wombatson"
WHEN = datetime.datetime(2026, 10, 23, 9, 30, tzinfo=datetime.timezone.utc)
# The SHA-256 of three source files.
SOURCES = (bytes([1]) * 32, bytes([2]) * 32, bytes([3]) * 32)
EVERY_REVIEW = (
    "--reviewed-retained-strings",
    "--reviewed-series",
    "--reviewed-high-risk-instances",
)
# The members of a statement, other than its format, as its format defines
# them.
MEMBERS = (
    "model",
    "attacker",
    "population",
    "matching_variables",
    "pixel_derived",
    "generalisation",
    "missing_data",
    "uncertainty",
    "exclusions",
    "linked_records",
    "earlier_releases",
    "device_identity",
    "institutional_identity",
    "facial_reconstruction",
    "subjects",
    "threshold",
    "maximum_risk",
    "assessor",
    "assessed_at",
)
TEXTS = (
    "pixel_derived",
    "generalisation",
    "missing_data",
    "uncertainty",
    "exclusions",
    "linked_records",
    "earlier_releases",
    "device_identity",
    "institutional_identity",
    "assessor",
)


def _statement(**changes):
    """A statement as JSON values, every text holding a sentinel."""
    statement = {
        "format": command.STATEMENT_FORMAT,
        "model": {
            "name": "Numbat uniqueness",
            "version": "2",
            "implementation": "Numbat Estimator",
            "implementation_version": "1.4.0",
        },
        "attacker": {
            "knowledge": "Numbat registries and news reports",
            "membership_known": True,
        },
        "population": {"in_cohort": "Every Numbat subject is in the release"},
        "matching_variables": ["Numbat sex", "age at study", "body habitus"],
        "pixel_derived": "Numbat body habitus and implants were matched on",
        "generalisation": "Numbat ages in 5-year bands",
        "missing_data": "Numbat missing values match any value",
        "uncertainty": "Numbat 95% interval from bootstrap",
        "exclusions": "Numbat none",
        "linked_records": "Numbat studies were assessed together",
        "earlier_releases": "No earlier Numbat release",
        "device_identity": "Numbat station names identify the department",
        "institutional_identity": "Numbat local codes were matched on as the site",
        "facial_reconstruction": False,
        "subjects": 3,
        "threshold": 0.09,
        "maximum_risk": 0.04,
        "assessor": ASSESSOR,
        "assessed_at": "2026-10-23T09:30:00Z",
    }
    statement.update(changes)
    return statement


def _assessment(**changes):
    """The assessment that :func:`_statement` states."""
    fields = {
        "model": Model("Numbat uniqueness", "2", "Numbat Estimator", "1.4.0"),
        "attacker": Attacker("Numbat registries and news reports", True),
        "population": Population(in_cohort="Every Numbat subject is in the release"),
        "matching_variables": ("Numbat sex", "age at study", "body habitus"),
        "pixel_derived": "Numbat body habitus and implants were matched on",
        "generalisation": "Numbat ages in 5-year bands",
        "missing_data": "Numbat missing values match any value",
        "uncertainty": "Numbat 95% interval from bootstrap",
        "exclusions": "Numbat none",
        "linked_records": "Numbat studies were assessed together",
        "earlier_releases": "No earlier Numbat release",
        "device_identity": "Numbat station names identify the department",
        "institutional_identity": "Numbat local codes were matched on as the site",
        "facial_reconstruction": False,
        "subjects": 3,
        "threshold": risk_assessment.DEFAULT_THRESHOLD,
        "maximum_risk": 0.04,
        "assessor": ASSESSOR,
        "assessed_at": WHEN,
    }
    fields.update(changes)
    return Assessment(**fields)


def _instances():
    return tuple(
        InstanceEntry(
            position,
            f"/imports/secretdir/{position}.dcm",
            Disposition.RELEASED,
            output=PurePosixPath(f"ZQ0001/2.25.1/2.25.2/2.25.{position + 3}.dcm"),
            source_sha256=digest.hex(),
        )
        for position, digest in enumerate(SOURCES)
    )


_NO_LISTS = object()


def _write_pack(tmp_path, name="secretdir-qc", instances=None, lists=_NO_LISTS):
    release = tmp_path / "release"
    release.mkdir(exist_ok=True)
    return qc_store.write_qc_pack(
        QcPack(
            PACK,
            _instances() if instances is None else instances,
            # As a run without Clean Descriptors records them.
            reviewed_lists=(
                risk_assessment.bind_lists(None, None, None)
                if lists is _NO_LISTS
                else lists
            ),
        ),
        tmp_path / name,
        release_directory=release,
    ).parent


def _report(reference=PACK):
    report = release_report.release_report(
        policy.compose_policy("basic"),
        vocabulary=None,
        reviewed_roi_names=None,
        qc_review=AttestationRecord(reference, Outcome.NOT_ATTESTED),
    )
    return release_report.report_document(report)


@pytest.fixture(name="pack")
def fixture_pack(tmp_path):
    return _write_pack(tmp_path)


@pytest.fixture(name="report_file")
def fixture_report_file(tmp_path):
    path = tmp_path / "secretdir-release" / run_report.RELEASE_REPORT
    path.parent.mkdir()
    path.write_text(json.dumps(_report()), "utf-8")
    return path


@pytest.fixture(name="statement_file")
def fixture_statement_file(tmp_path):
    return _write_statement(tmp_path, _statement())


def _write_statement(tmp_path, statement, name="secretdir-statement.json"):
    path = tmp_path / name
    if isinstance(statement, bytes):
        path.write_bytes(statement)
    else:
        path.write_text(json.dumps(statement), "utf-8")
    return path


def _run(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    status = command.main([str(arg) for arg in argv], stdout=stdout, stderr=stderr)
    return status, stdout.getvalue(), stderr.getvalue()


def _assert_quotes_nothing(*texts):
    for text in texts:
        for sentinel in SENTINELS:
            assert sentinel not in text


def _assert_refused(pack, status, stdout, stderr, message):
    assert status == command.EXIT_NOT_RECORDED
    assert message in stderr
    assert stderr.rstrip().endswith("; nothing was recorded")
    assert not stdout
    assert not (pack / risk_assessment.ASSESSMENT_FILE).exists()
    _assert_quotes_nothing(stderr)


def _reference(stdout):
    match = re.search(r"R-[0-9a-f]{32}", stdout)
    assert match is not None
    return match[0]


# Recording.


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-07")
def test_an_assessment_is_recorded_beside_the_pack(pack, report_file, statement_file):
    status, stdout, stderr = _run(pack, report_file, statement_file)

    assert status == command.EXIT_RECORDED, stderr
    record = risk_assessment.read_assessment(pack)
    assert record is not None
    assert record.pack == PACK
    assert record.assessment == _assessment()
    assert stdout.splitlines() == [
        f"risk assessment {record.reference}: recorded beside QC pack {PACK}",
        "  distinct subjects assessed: 3",
        "  matching variables: 3",
        "  threshold: 0.09",
        "  maximum per-subject probability: within the threshold",
        "  faces reconstructed from the images: not assessed",
        "the release report published with the run is unchanged",
    ]
    assert not stderr
    _assert_quotes_nothing(stdout)


@pytest.mark.deid_requirement("MIDI-BP-07")
def test_the_record_is_bound_as_recording_from_python_binds_it(
    pack, report_file, statement_file
):
    expected = risk_assessment.bind_assessment(pack, report_file, _assessment())

    status, _, stderr = _run(pack, report_file, statement_file)

    assert status == command.EXIT_RECORDED, stderr
    record = risk_assessment.read_assessment(pack)
    assert dataclasses.replace(record, reference=expected.reference) == expected
    assert record.policy_sha256 == risk_assessment.policy_digest(_report())
    assert record.collection_sha256 == risk_assessment.collection_digest(SOURCES)


def test_the_report_is_unchanged(pack, report_file, statement_file):
    before = report_file.read_bytes()

    _run(pack, report_file, statement_file)

    assert report_file.read_bytes() == before


@pytest.mark.deid_requirement("MIDI-BP-07")
def test_a_reference_population_with_its_sampling_is_recorded(
    tmp_path, pack, report_file
):
    population = {"reference": "Numbat state register", "sampling": "Numbat random"}
    statement = _write_statement(tmp_path, _statement(population=population))

    status, _, stderr = _run(pack, report_file, statement)

    assert status == command.EXIT_RECORDED, stderr
    assert risk_assessment.read_assessment(pack).assessment.population == Population(
        reference="Numbat state register", sampling="Numbat random"
    )


@pytest.mark.parametrize(
    "population",
    [
        {"in_cohort": "Numbat cohort", "reference": None, "sampling": None},
        {"reference": "Numbat register", "sampling": "Numbat", "in_cohort": None},
    ],
)
def test_a_population_may_give_the_form_it_does_not_take_as_null(
    tmp_path, pack, report_file, population
):
    statement = _write_statement(tmp_path, _statement(population=population))

    status, _, stderr = _run(pack, report_file, statement)

    assert status == command.EXIT_RECORDED, stderr


def test_text_outside_ascii_is_recorded_as_given(tmp_path, pack, report_file):
    statement = _write_statement(
        tmp_path, _statement(exclusions="Numbat: tēnā koe, naïve, 東京")
    )

    status, stdout, stderr = _run(pack, report_file, statement)

    assert status == command.EXIT_RECORDED, stderr
    record = risk_assessment.read_assessment(pack)
    assert record.assessment.exclusions == "Numbat: tēnā koe, naïve, 東京"
    _assert_quotes_nothing(stdout)


def test_a_statement_with_a_byte_order_mark_is_read(tmp_path, pack, report_file):
    statement = _write_statement(
        tmp_path, b"\xef\xbb\xbf" + json.dumps(_statement()).encode("utf-8")
    )

    status, _, stderr = _run(pack, report_file, statement)

    assert status == command.EXIT_RECORDED, stderr
    assert risk_assessment.read_assessment(pack).assessment == _assessment()


@pytest.mark.parametrize(
    "given, expected",
    [
        ("2026-10-23T09:30:00Z", WHEN),
        ("2026-10-23T09:30:00+00:00", WHEN),
        ("2026-10-23T20:30:00+11:00", WHEN),
        ("2026-10-23T04:00:00-05:30", WHEN),
        (
            "2026-10-23T09:30:00.250000Z",
            WHEN + datetime.timedelta(microseconds=250000),
        ),
    ],
)
def test_the_time_is_recorded_in_utc(tmp_path, pack, report_file, given, expected):
    statement = _write_statement(tmp_path, _statement(assessed_at=given))

    status, _, stderr = _run(pack, report_file, statement)

    assert status == command.EXIT_RECORDED, stderr
    assessed_at = risk_assessment.read_assessment(pack).assessment.assessed_at
    assert assessed_at == expected
    assert assessed_at.utcoffset() == datetime.timedelta(0)


@pytest.mark.deid_requirement("MIDI-BP-07")
@pytest.mark.parametrize(
    "threshold, maximum_risk, line",
    [
        (0.09, 0.09, "within the threshold"),
        (0.05, 0.05, "within the threshold"),
        (0.05, 0.06, "above the threshold, so the statistical gate fails"),
        (0.09, 1, "above the threshold, so the statistical gate fails"),
        (0.09, 0, "within the threshold"),
    ],
)
def test_the_summary_says_whether_the_risk_is_within_the_threshold(
    tmp_path, pack, report_file, threshold, maximum_risk, line
):
    statement = _write_statement(
        tmp_path, _statement(threshold=threshold, maximum_risk=maximum_risk)
    )

    status, stdout, stderr = _run(pack, report_file, statement)

    # An assessment above its threshold is recorded, as the assessor stated
    # it; the gate of any run given it fails.
    assert status == command.EXIT_RECORDED, stderr
    assert f"  threshold: {threshold}" in stdout.splitlines()
    assert f"  maximum per-subject probability: {line}" in stdout.splitlines()
    record = risk_assessment.read_assessment(pack)
    assert record.assessment.within_threshold is (line == "within the threshold")


@pytest.mark.deid_requirement("MIDI-BP-15")
def test_the_summary_says_whether_faces_were_assessed(tmp_path, pack, report_file):
    statement = _write_statement(tmp_path, _statement(facial_reconstruction=True))

    status, stdout, stderr = _run(pack, report_file, statement)

    assert status == command.EXIT_RECORDED, stderr
    assert "  faces reconstructed from the images: assessed" in stdout.splitlines()
    assert risk_assessment.read_assessment(pack).assessment.facial_reconstruction


def test_a_pack_has_one_assessment(tmp_path, pack, report_file, statement_file):
    _run(pack, report_file, statement_file)
    before = (pack / risk_assessment.ASSESSMENT_FILE).read_bytes()
    other = _write_statement(tmp_path, _statement(maximum_risk=0.01), "other.json")

    status, stdout, stderr = _run(pack, report_file, other)

    assert status == command.EXIT_NOT_RECORDED
    assert "the QC pack already has a risk assessment; nothing was recorded" in stderr
    assert not stdout
    assert (pack / risk_assessment.ASSESSMENT_FILE).read_bytes() == before
    _assert_quotes_nothing(stderr)


# Checking without recording.


def test_check_records_nothing_and_says_so(pack, report_file, statement_file):
    status, stdout, stderr = _run(pack, report_file, statement_file, "--check")

    assert status == command.EXIT_RECORDED, stderr
    assert not (pack / risk_assessment.ASSESSMENT_FILE).exists()
    assert stdout.splitlines() == [
        f"risk assessment checked against QC pack {PACK}; nothing was recorded",
        "  distinct subjects assessed: 3",
        "  matching variables: 3",
        "  threshold: 0.09",
        "  maximum per-subject probability: within the threshold",
        "  faces reconstructed from the images: not assessed",
        "the release report published with the run is unchanged",
    ]
    assert not re.search(r"R-[0-9a-f]{32}", stdout)
    # Recording then succeeds.
    assert _run(pack, report_file, statement_file)[0] == command.EXIT_RECORDED


@pytest.mark.parametrize(
    "change, message",
    [
        (
            lambda tmp, pack, report, statement: (
                pack,
                report,
                _write_statement(tmp, _statement(subjects=0)),
            ),
            "the assessment needs its number of subjects",
        ),
        (
            lambda tmp, pack, report, statement: (pack, _other_report(tmp), statement),
            "the release report names another QC pack",
        ),
        (
            lambda tmp, pack, report, statement: (tmp / "release", report, statement),
            "holds no QC pack",
        ),
    ],
)
def test_check_refuses_what_recording_refuses(
    tmp_path, pack, report_file, statement_file, change, message
):
    arguments = change(tmp_path, pack, report_file, statement_file)

    status, stdout, stderr = _run(*arguments, "--check")

    assert status == command.EXIT_NOT_RECORDED
    assert message in stderr
    assert stderr.rstrip().endswith("; nothing was recorded")
    assert not stdout
    assert not (pack / risk_assessment.ASSESSMENT_FILE).exists()
    _assert_quotes_nothing(stderr)


def test_check_refuses_a_pack_that_has_an_assessment(pack, report_file, statement_file):
    _run(pack, report_file, statement_file)
    before = (pack / risk_assessment.ASSESSMENT_FILE).read_bytes()

    status, stdout, stderr = _run(pack, report_file, statement_file, "--check")

    assert status == command.EXIT_NOT_RECORDED
    assert "the QC pack already has a risk assessment" in stderr
    assert not stdout
    assert (pack / risk_assessment.ASSESSMENT_FILE).read_bytes() == before


def _other_report(tmp_path):
    path = tmp_path / "secretdir-other" / run_report.RELEASE_REPORT
    path.parent.mkdir()
    path.write_text(json.dumps(_report(OTHER_PACK)), "utf-8")
    return path


# Statements that are refused.


@pytest.mark.deid_requirement("MIDI-BP-07")
@pytest.mark.parametrize("member", MEMBERS)
def test_a_statement_without_a_member_is_refused(tmp_path, pack, report_file, member):
    statement = _statement()
    del statement[member]

    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, statement)
    )

    _assert_refused(
        pack, status, stdout, stderr, f"the statement needs its member {member}"
    )


def test_a_statement_without_several_members_names_each(tmp_path, pack, report_file):
    statement = _statement()
    for member in ("uncertainty", "subjects", "assessor"):
        del statement[member]

    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, statement)
    )

    _assert_refused(
        pack,
        status,
        stdout,
        stderr,
        "the statement needs its members uncertainty, subjects, and assessor",
    )


@pytest.mark.parametrize(
    "section, member",
    [
        ("model", "name"),
        ("model", "version"),
        ("model", "implementation"),
        ("model", "implementation_version"),
        ("attacker", "knowledge"),
        ("attacker", "membership_known"),
    ],
)
def test_a_section_without_a_member_is_refused(
    tmp_path, pack, report_file, section, member
):
    statement = _statement()
    del statement[section][member]

    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, statement)
    )

    _assert_refused(
        pack,
        status,
        stdout,
        stderr,
        f"the statement's {section} needs its member {member}",
    )


@pytest.mark.parametrize("section", [None, "model", "attacker", "population"])
def test_a_member_that_the_format_does_not_define_is_refused_unquoted(
    tmp_path, pack, report_file, section
):
    statement = _statement()
    target = statement if section is None else statement[section]
    target["Quokka note"] = "Numbat"
    target["Wombatson"] = "Numbat"
    what = "the statement" if section is None else f"the statement's {section}"

    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, statement)
    )

    _assert_refused(
        pack,
        status,
        stdout,
        stderr,
        f"{what} has 2 members that its format does not define",
    )


@pytest.mark.parametrize("section", ["model", "attacker", "population"])
@pytest.mark.parametrize("value", ["Numbat", ["Numbat"], None, 3])
def test_a_section_that_is_not_an_object_is_refused(
    tmp_path, pack, report_file, section, value
):
    status, stdout, stderr = _run(
        pack,
        report_file,
        _write_statement(tmp_path, _statement(**{section: value})),
    )

    _assert_refused(
        pack, status, stdout, stderr, f"the statement's {section} is not a JSON object"
    )


@pytest.mark.parametrize(
    "content",
    [
        b'{"format": "pymedphys-deid-risk-statement/1", "subjects": 3, "subjects": 4}',
        b'{"format": "pymedphys-deid-risk-statement/1", '
        b'"model": {"name": "a", "name": "b"}}',
    ],
)
def test_a_member_named_twice_is_refused(tmp_path, pack, report_file, content):
    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, content)
    )

    _assert_refused(pack, status, stdout, stderr, "the statement names a member twice")


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"Numbat",
        b"\xff\xfe{}",
        "{}".encode("utf-16"),
        b'{"format": ',
    ],
    ids=["empty", "text", "not-utf-8", "utf-16", "truncated"],
)
def test_a_statement_that_is_not_utf_8_json_is_refused(
    tmp_path, pack, report_file, content
):
    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, content)
    )

    _assert_refused(pack, status, stdout, stderr, "the statement is not UTF-8 JSON")


def test_a_statement_too_deep_for_the_parser_is_refused(
    tmp_path, pack, report_file, monkeypatch
):
    # How deep the parser can go depends on the platform's stack, so the
    # parser's refusal is made certain here; the next test nests for real.
    def too_deep(*_args, **_kwargs):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(command.json, "loads", too_deep)

    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, _statement())
    )

    _assert_refused(pack, status, stdout, stderr, "the statement is not UTF-8 JSON")


def test_a_deeply_nested_statement_is_refused_whatever_the_parser_reaches(
    tmp_path, pack, report_file
):
    # Nested deeper than CPython's parser goes on a default stack: it is
    # refused as JSON where the parser gives up, or as not a statement
    # where it does not, and never raises.
    content = b"[" * 100_000 + b"]" * 100_000

    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, content)
    )

    assert status == command.EXIT_NOT_RECORDED
    assert (
        "the statement is not UTF-8 JSON" in stderr
        or f"the statement is not of its format, {command.STATEMENT_FORMAT}" in stderr
    )
    _assert_refused(pack, status, stdout, stderr, "the statement is not")


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_a_number_that_is_not_finite_is_refused(tmp_path, pack, report_file, constant):
    text = json.dumps(_statement()).replace(
        '"maximum_risk": 0.04', f'"maximum_risk": {constant}'
    )

    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, text.encode("ascii"))
    )

    _assert_refused(
        pack, status, stdout, stderr, "the statement holds a number that is not finite"
    )


@pytest.mark.parametrize(
    "document",
    [
        [],
        "Numbat",
        3,
        None,
        {key: value for key, value in _statement().items() if key != "format"},
        _statement(format="pymedphys-deid-risk-statement/2"),
        _statement(format="pymedphys-deid-risk-assessment/2"),
        _statement(format=None),
    ],
    ids=[
        "array",
        "string",
        "number",
        "null",
        "no-format",
        "later",
        "record",
        "null-format",
    ],
)
def test_a_statement_not_of_its_format_is_refused(
    tmp_path, pack, report_file, document
):
    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, document)
    )

    _assert_refused(
        pack,
        status,
        stdout,
        stderr,
        "the statement is not of its format, pymedphys-deid-risk-statement/1",
    )


def test_a_record_given_as_the_statement_is_refused(
    tmp_path, pack, report_file, statement_file
):
    # A record carries its own format, so cannot be given again as a
    # statement of another pack.
    _run(pack, report_file, statement_file)
    other_pack = _write_pack(tmp_path, "secretdir-qc-other")
    record = pack / risk_assessment.ASSESSMENT_FILE

    status, stdout, stderr = _run(other_pack, report_file, record)

    _assert_refused(other_pack, status, stdout, stderr, "not of its format")


@pytest.mark.deid_requirement("MIDI-BP-04", "MIDI-BP-05", "MIDI-BP-07")
@pytest.mark.parametrize("member", TEXTS)
@pytest.mark.parametrize("value", ["", "   ", None, 3, ["Numbat"], True])
def test_a_statement_that_is_not_text_is_refused(
    tmp_path, pack, report_file, member, value
):
    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, _statement(**{member: value}))
    )

    _assert_refused(
        pack, status, stdout, stderr, f"the assessment needs its {member} as text"
    )


@pytest.mark.parametrize(
    "member", ["name", "version", "implementation", "implementation_version"]
)
@pytest.mark.parametrize("value", ["", None, 2])
def test_each_part_of_the_model_is_text(tmp_path, pack, report_file, member, value):
    statement = _statement()
    statement["model"][member] = value

    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, statement)
    )

    _assert_refused(
        pack, status, stdout, stderr, f"the model needs its {member} as text"
    )


@pytest.mark.parametrize(
    "attacker, message",
    [
        (
            {"knowledge": " ", "membership_known": True},
            "the attacker needs its knowledge as text",
        ),
        (
            {"knowledge": "Numbat", "membership_known": "yes"},
            "the attacker needs whether membership is known, true or false",
        ),
        (
            {"knowledge": "Numbat", "membership_known": 1},
            "the attacker needs whether membership is known, true or false",
        ),
        (
            {"knowledge": "Numbat", "membership_known": None},
            "the attacker needs whether membership is known, true or false",
        ),
    ],
)
def test_the_attacker_is_checked(tmp_path, pack, report_file, attacker, message):
    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, _statement(attacker=attacker))
    )

    _assert_refused(pack, status, stdout, stderr, message)


@pytest.mark.parametrize(
    "population, message",
    [
        ({}, "the population needs its reference as text"),
        ({"reference": "Numbat"}, "the population needs its sampling as text"),
        ({"sampling": "Numbat"}, "the population needs its reference as text"),
        ({"in_cohort": " "}, "the population needs its in_cohort as text"),
        ({"in_cohort": 3}, "the population needs its in_cohort as text"),
        (
            {"in_cohort": "Numbat", "reference": "Numbat", "sampling": "Numbat"},
            "not both",
        ),
        ({"in_cohort": "Numbat", "reference": "Numbat"}, "not both"),
    ],
)
def test_the_population_is_one_of_its_forms(
    tmp_path, pack, report_file, population, message
):
    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, _statement(population=population))
    )

    _assert_refused(pack, status, stdout, stderr, message)


@pytest.mark.deid_requirement("MIDI-BP-07")
@pytest.mark.parametrize(
    "variables, message",
    [
        ([], "the assessment needs its matching variables, at least one, as text"),
        (
            "Numbat sex",
            "the assessment needs its matching variables, at least one, as text",
        ),
        (
            {"Numbat": 1},
            "the assessment needs its matching variables, at least one, as text",
        ),
        (
            ["Numbat", 3],
            "the assessment needs its matching variables, at least one, as text",
        ),
        (
            ["Numbat", " "],
            "the assessment needs its matching variables, at least one, as text",
        ),
        (None, "the assessment needs its matching variables, at least one, as text"),
        (
            ["Numbat sex", " numbat SEX "],
            "the assessment lists each matching variable once",
        ),
    ],
)
def test_the_matching_variables_are_checked(
    tmp_path, pack, report_file, variables, message
):
    status, stdout, stderr = _run(
        pack,
        report_file,
        _write_statement(tmp_path, _statement(matching_variables=variables)),
    )

    _assert_refused(pack, status, stdout, stderr, message)


@pytest.mark.parametrize(
    "member, value, message",
    [
        ("facial_reconstruction", "no", "whether facial reconstruction was assessed"),
        ("facial_reconstruction", 0, "whether facial reconstruction was assessed"),
        ("facial_reconstruction", None, "whether facial reconstruction was assessed"),
        ("subjects", 0, "its number of subjects, a whole number of at least 1"),
        ("subjects", -3, "its number of subjects, a whole number of at least 1"),
        ("subjects", 3.0, "its number of subjects, a whole number of at least 1"),
        ("subjects", "3", "its number of subjects, a whole number of at least 1"),
        ("subjects", True, "its number of subjects, a whole number of at least 1"),
        ("subjects", None, "its number of subjects, a whole number of at least 1"),
        ("threshold", 0.1, "the assessment's threshold is 0.09 or 0.05"),
        ("threshold", "0.09", "the assessment's threshold is 0.09 or 0.05"),
        ("threshold", None, "the assessment's threshold is 0.09 or 0.05"),
        ("threshold", True, "the assessment's threshold is 0.09 or 0.05"),
        ("maximum_risk", 1.5, "its maximum per-subject probability, from 0 to 1"),
        ("maximum_risk", -0.01, "its maximum per-subject probability, from 0 to 1"),
        ("maximum_risk", "0.04", "its maximum per-subject probability, from 0 to 1"),
        ("maximum_risk", None, "its maximum per-subject probability, from 0 to 1"),
        ("maximum_risk", False, "its maximum per-subject probability, from 0 to 1"),
    ],
)
def test_the_answers_and_numbers_are_checked(
    tmp_path, pack, report_file, member, value, message
):
    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, _statement(**{member: value}))
    )

    _assert_refused(pack, status, stdout, stderr, message)


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-23T09:30:00",
        "2026-10-23",
        "23/10/2026 09:30",
        "Numbat",
        "",
        1_792_000_000,
        None,
    ],
)
def test_a_time_without_its_utc_offset_is_refused(tmp_path, pack, report_file, value):
    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, _statement(assessed_at=value))
    )

    _assert_refused(
        pack,
        status,
        stdout,
        stderr,
        "the statement needs its assessed_at as an ISO 8601 date and time with its "
        "UTC offset, such as 2026-10-23T09:30:00Z",
    )


@pytest.mark.parametrize(
    "value", ["0001-01-01T00:30:00+01:00", "9999-12-31T23:30:00-01:00"]
)
def test_a_time_outside_the_years_of_a_datetime_in_utc_is_refused(
    tmp_path, pack, report_file, value
):
    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, _statement(assessed_at=value))
    )

    _assert_refused(
        pack,
        status,
        stdout,
        stderr,
        "the statement's assessed_at is outside the years 1 to 9999 in UTC",
    )


def test_a_member_that_the_format_does_not_define_is_counted(
    tmp_path, pack, report_file
):
    statement = _statement()
    statement["Quokka"] = "Numbat"

    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, statement)
    )

    _assert_refused(
        pack,
        status,
        stdout,
        stderr,
        "the statement has 1 member that its format does not define",
    )


def test_a_time_in_the_future_is_refused(tmp_path, pack, report_file):
    later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    statement = _statement(assessed_at=later.isoformat())

    status, stdout, stderr = _run(
        pack, report_file, _write_statement(tmp_path, statement)
    )

    _assert_refused(
        pack, status, stdout, stderr, "the assessment's time is in the future"
    )


@pytest.mark.parametrize("where", ["missing", "directory"])
def test_a_statement_that_cannot_be_read_is_refused(tmp_path, pack, report_file, where):
    path = tmp_path / "secretdir-statement.json"
    if where == "directory":
        path.mkdir()

    status, stdout, stderr = _run(pack, report_file, path)

    _assert_refused(pack, status, stdout, stderr, "the statement could not be read")


# What the statement is recorded against.


def test_a_report_of_another_pack_is_refused(tmp_path, pack, statement_file):
    status, stdout, stderr = _run(pack, _other_report(tmp_path), statement_file)

    _assert_refused(
        pack, status, stdout, stderr, "the release report names another QC pack"
    )


@pytest.mark.parametrize(
    "content",
    [b"", b"\xff", b"[]", json.dumps({"format": "other/1"}).encode("ascii")],
    ids=["empty", "not-utf-8", "array", "other-format"],
)
def test_a_report_not_of_its_format_is_refused(
    report_file, pack, statement_file, content
):
    report_file.write_bytes(content)

    status, stdout, stderr = _run(pack, report_file, statement_file)

    _assert_refused(
        pack, status, stdout, stderr, "the release report is not of its format"
    )


def test_a_report_that_cannot_be_read_is_refused(tmp_path, pack, statement_file):
    status, stdout, stderr = _run(
        pack, tmp_path / "secretdir-missing" / "release-report.json", statement_file
    )

    _assert_refused(
        pack, status, stdout, stderr, "the release report could not be read"
    )


@pytest.mark.parametrize("where", ["release", "missing", "parent", "file"])
def test_a_path_that_is_not_a_qc_pack_is_refused(
    tmp_path, pack, report_file, statement_file, where
):
    target = {
        "release": tmp_path / "release",
        "missing": tmp_path / "secretdir-missing",
        "parent": pack.parent,
        "file": pack / qc_store.PACK_FILE,
    }[where]

    status, stdout, stderr = _run(target, report_file, statement_file)

    _assert_refused(pack, status, stdout, stderr, "holds no QC pack")
    assert not (target / risk_assessment.ASSESSMENT_FILE).exists()


def test_a_pack_without_the_reviewed_lists_digest_is_refused(
    tmp_path, report_file, statement_file
):
    # As a run without a release reporter writes it.
    pack = _write_pack(tmp_path, "secretdir-qc-unbound", lists=None)

    status, stdout, stderr = _run(pack, report_file, statement_file)

    _assert_refused(
        pack,
        status,
        stdout,
        stderr,
        "the QC pack records no digest of the reviewed lists that its run applied",
    )


def test_a_pack_that_binds_no_source_file_is_refused(
    tmp_path, report_file, statement_file
):
    pack = _write_pack(
        tmp_path,
        "secretdir-qc-unread",
        instances=(
            InstanceEntry(
                0,
                "/imports/secretdir/unreadable",
                Disposition.REFUSED,
                reasons=("unreadable file",),
            ),
        ),
    )

    status, stdout, stderr = _run(pack, report_file, statement_file)

    _assert_refused(pack, status, stdout, stderr, "the QC pack binds no source file")


def test_a_pack_changed_after_its_assessment_is_refused_on_reading(
    pack, report_file, statement_file
):
    _run(pack, report_file, statement_file)
    path = pack / qc_store.PACK_FILE
    document = json.loads(path.read_text("ascii"))
    document["instances"] = document["instances"][:-1]
    path.chmod(0o600)
    path.write_text(json.dumps(document), "ascii")

    with pytest.raises(risk_assessment.RiskAssessmentError, match="changed after"):
        risk_assessment.read_assessment(pack)


# Arguments.


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["PACK"],
        ["PACK", "REPORT"],
        ["PACK", "REPORT", "STATEMENT", "EXTRA"],
        ["PACK", "REPORT", "STATEMENT", "--Quokka"],
        ["PACK", "REPORT", "STATEMENT", "--check=Wombatson"],
    ],
)
def test_arguments_that_cannot_be_parsed_are_refused(argv):
    with pytest.raises(SystemExit) as raised:
        _run(*argv)
    assert raised.value.code == command.EXIT_USAGE


def test_a_usage_error_quotes_no_argument(capsys):
    stderr = io.StringIO()
    with pytest.raises(SystemExit):
        command.main(
            ["secretdir", "Quokka", "Wombatson", "Numbat"],
            stdout=io.StringIO(),
            stderr=stderr,
        )
    _assert_quotes_nothing(stderr.getvalue(), capsys.readouterr().err)
    assert "could not be parsed" in stderr.getvalue()


def test_help_describes_the_statement():
    stdout = io.StringIO()
    with pytest.raises(SystemExit) as raised, contextlib.redirect_stdout(stdout):
        command.main(["--help"])
    assert raised.value.code == 0
    # argparse may wrap the format's label at a hyphen.
    text = "".join(stdout.getvalue().split())
    assert command.STATEMENT_FORMAT in text
    assert "--check" in text
    for member in command.MEMBERS:
        assert member in text


def test_it_runs_as_a_module_of_the_private_package(pack, report_file, statement_file):
    # Like every command of the tool, it stays off the pymedphys command
    # line until release, which test_cli.py checks for the public parser.
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pymedphys._dicom.deidentify.risk_assessment_command",
            str(pack),
            str(report_file),
            str(statement_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == command.EXIT_RECORDED, completed.stderr
    record = risk_assessment.read_assessment(pack)
    assert record is not None
    assert record.reference == _reference(completed.stdout)
    _assert_quotes_nothing(completed.stdout, completed.stderr)


# The documented statement.


def _documented_statement():
    """The example statement in the module's docstring, as JSON values."""
    lines = inspect.getdoc(command).splitlines()
    start = next(i for i, line in enumerate(lines) if line.endswith("For example::"))
    start += 1
    block = []
    for line in lines[start:]:
        if line and not line.startswith("    "):
            break
        block.append(line)
    return json.loads("\n".join(block))


def test_the_documented_example_is_a_statement_that_is_recorded(
    tmp_path, pack, report_file
):
    example = _documented_statement()
    assert set(example) == {"format", *MEMBERS}

    status, _, stderr = _run(pack, report_file, _write_statement(tmp_path, example))

    assert status == command.EXIT_RECORDED, stderr


def test_the_documented_members_are_the_assessments_fields():
    # Each member of the format is one of the Assessment's fields, so that
    # a field added to it needs a new format and a new example.
    assert {"format", *MEMBERS} == set(command.MEMBERS)
    assert set(MEMBERS) == {field.name for field in dataclasses.fields(Assessment)}
    assert set(command.SECTIONS["model"]) == {
        field.name for field in dataclasses.fields(Model)
    }
    assert set(command.SECTIONS["attacker"]) == {
        field.name for field in dataclasses.fields(Attacker)
    }
    assert set(command.SECTIONS["population"]) == {
        field.name for field in dataclasses.fields(Population)
    }


def test_assessment_of_reads_json_values_without_a_file():
    assert command.assessment_of(_statement()) == _assessment()
    statement = _statement()
    original = copy.deepcopy(statement)
    command.assessment_of(statement)
    assert statement == original


# The commands end to end.


_RADIOTHERAPY = frozenset({"CT Image", "RT Structure Set", "RT Dose", "RT Plan"})


def _public_release(cleaning, faces, review=None):
    return InstanceTransform(
        policy.compose_policy("public-release"),
        _corpus_run.KEY,
        cleaning=cleaning,
        face_review=faces,
        readiness_review=review,
        unvalidated_policy=True,
    )


@pytest.mark.deid_requirement(
    "MIDI-BP-01", "MIDI-BP-07", "MIDI-BP-10", "MIDI-BP-11", "MIDI-BP-15", "MIDI-BP-17"
)
def test_a_collection_reviewed_and_assessed_with_the_commands_is_ready():
    # The radiotherapy files alone, which keep the runs short, as the
    # readiness tests take them.
    corpus = corpus_module.build_corpus()
    corpus = dataclasses.replace(
        corpus,
        files=tuple(f for f in corpus.files if f.manifest.iod in _RADIOTHERAPY),
    )
    subjects = len(
        {
            pydicom.dcmread(io.BytesIO(file.data), stop_before_pixels=True).PatientID
            for file in corpus.files
        }
    )
    # A short directory, since a run refuses output paths that could exceed
    # Windows' 259 characters.
    directory = Path(tempfile.mkdtemp(prefix="d"))
    try:
        corpus_module.write_corpus(corpus, directory)
        instances = run.discover(directory / corpus_module.INSTANCES_DIRECTORY)
        with _corpus_run.published_vocabulary():
            cleaning = DescriptorCleaning(
                _corpus_run.VOCABULARY, _corpus_run.mapped_planted_name(corpus)
            )
            transform = _public_release(cleaning, _corpus_run.NO_FACE_VERDICTS)
            first = run.run(
                instances,
                directory / "r1",
                transform,
                ReleaseGate(),
                qc_destination=directory / "qc1",
                reporter=transform.reporter,
            )
            first_report = first.release / run_report.RELEASE_REPORT
            pack = first.qc_pack.parent
            entries = json.loads(first.qc_pack.read_text("utf-8"))
            # The reviewer attests, and the assessor records, each with
            # their command, as a person would.
            attested = attestation_command.main(
                [
                    str(pack),
                    "--reviewer",
                    ASSESSOR,
                    "--outcome",
                    "attested",
                    *EVERY_REVIEW,
                    "--residual-risk-accepted",
                    "yes",
                    *(
                        argument
                        for series in entries["series"]
                        for argument in ("--face-absent", str(series["positions"][0]))
                    ),
                ],
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
            assert attested == attestation_command.EXIT_RECORDED
            statement = directory / "statement.json"
            statement.write_text(json.dumps(_statement(subjects=subjects)), "utf-8")
            status, stdout, stderr = _run(pack, first_report, statement)
            assert status == command.EXIT_RECORDED, stderr
            review = readiness.read_readiness_review(pack, first_report)
            transform = _public_release(cleaning, read_face_review(pack), review)
            second = run.run(
                instances,
                directory / "r2",
                transform,
                ReleaseGate(),
                qc_destination=directory / "qc2",
                reporter=transform.reporter,
            )
        document = json.loads(
            (second.release / run_report.RELEASE_REPORT).read_text("utf-8")
        )
    finally:
        shutil.rmtree(directory, ignore_errors=True)

    assert subjects >= 1
    assert document["readiness"] == {
        "ready": True,
        "review": entries["reference"],
        "assessment": _reference(stdout),
        "statistical": None,
        "pixel_and_face": None,
        "attestation": None,
    }
