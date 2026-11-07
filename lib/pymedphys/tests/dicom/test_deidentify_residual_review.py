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

"""A reviewer's clearing of the residual findings that held a file for review.

The residual search holds a written file for review where it finds source
text that nothing explains (``residual-text``), or a source person name in
standard text that a selected option keeps
(``residual-person-name-in-kept-text``), since only a person who sees the
value can tell an institution's own name from a physician's name typed into
it (D-027, D-042). The QC pack shows each finding with an excerpt and the
SHA-256 of the written value that holds it. A reviewer who judges those
values not identifying clears the instance in the pack's attestation, and a
later run given the pack releases the file, exempting each finding that the
pack showed in the same source file, in a value with the same SHA-256, as
reviewed. Anything else still holds or withholds. The names and
institutions here are invented.
"""

import hashlib
import io
import json
import os
import shutil
import struct
import tempfile
from pathlib import Path

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    attestation_command,
    pilot_command,
    policy,
    qc_attestation,
    run,
)
from pymedphys._dicom.deidentify import command as deidentify_command
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.policy import (
    INSTITUTION_IDENTITY,
    compose_custom_policy,
)
from pymedphys._dicom.deidentify.qc_attestation import Coverage, Outcome
from pymedphys._dicom.deidentify.qc_pack import FORMAT as PACK_FORMAT
from pymedphys._dicom.deidentify.qc_pack import QcPackError
from pymedphys._dicom.deidentify.release_gate import (
    Coverage as SearchCoverage,
)
from pymedphys._dicom.deidentify.release_gate import (
    Decision,
    ReasonCode,
    release_condition,
)
from pymedphys._dicom.deidentify.release_report import FORMAT as REPORT_FORMAT
from pymedphys._dicom.deidentify.release_report_markdown import to_markdown
from pymedphys._dicom.deidentify.residual_exemptions import Exemption
from pymedphys._dicom.deidentify.residual_review import (
    ResidualReview,
    read_residual_review,
    residual_review_of,
)
from pymedphys._dicom.deidentify.residuals import (
    ReviewedFinding,
    SourceValue,
    reviewed_findings,
)
from pymedphys._dicom.deidentify.run_report import RELEASE_REPORT

from . import _synthetic_references as synthetic

KEY = DeidKey(bytes(range(32)))
PHYSICIAN = "QUILLONBY^ZAPHOD"
INSTITUTION = "QUILLONBY MEMORIAL HOSPITAL"
OTHER_INSTITUTION = "QUILLONBY ROAD CLINIC"
REVIEWER = "Quokka Wombatson"
COMPLETE = Coverage(retained_strings=True, series=True, high_risk_instances=True)
KEPT_TEXT_NAME = ReasonCode.RESIDUAL_PERSON_NAME_IN_KEPT_TEXT


def _element(tag, vr, value):
    """An explicit VR little endian element with a 16-bit length."""
    group, element = divmod(tag, 0x10000)
    value = value.encode("ascii")
    value += (b"\x00" if vr == "UI" else b" ") * (len(value) % 2)
    return struct.pack("<HH2sH", group, element, vr.encode(), len(value)) + value


def _written(*elements, meta=b""):
    """A written file holding ``elements``, given in the order of their tags."""
    syntax = _element(0x00020010, "UI", "1.2.840.10008.1.2.1")
    return bytes(128) + b"DICM" + syntax + meta + b"".join(elements)


def _top(tag):
    return ElementPath((), tag)


def _coverage(*values, options=(INSTITUTION_IDENTITY,)):
    return SearchCoverage(
        planned=frozenset(value.source for value in values),
        collected=tuple(values),
        uncollected=(),
        options=options,
    )


def _physician(tag="(0008,1050)"):
    return SourceValue(_top(tag), "PN", PHYSICIAN)


KEPT_INSTITUTION = _written(_element(0x00080080, "LO", INSTITUTION))


def _seen(coverage, written):
    """The fingerprints of the findings that a first run's search made."""
    condition = release_condition(coverage, written)
    return frozenset(reviewed_findings(written, condition.search.findings)) - {None}


# The fingerprint of a finding.


def test_a_finding_in_a_value_is_fingerprinted_by_that_value():
    condition = release_condition(_coverage(_physician()), KEPT_INSTITUTION)

    (finding,) = condition.search.findings
    (seen,) = reviewed_findings(KEPT_INSTITUTION, condition.search.findings)

    value = INSTITUTION.encode("ascii") + b" " * (len(INSTITUTION) % 2)
    assert seen == ReviewedFinding(
        source="(0008,1050)",
        kind=finding.kind.value,
        form=finding.form.value,
        encoding=finding.encoding,
        region=finding.location.region.value,
        element="(0008,0080)",
        vr="LO",
        item=None,
        value_sha256=hashlib.sha256(value).hexdigest(),
    )


def test_a_finding_outside_any_value_has_no_fingerprint():
    # In the File Meta Information's Source AE Title, the finding is in a
    # value; in bytes after the data set, it is in none.
    written = KEPT_INSTITUTION + b"QUILLONBY"
    condition = release_condition(_coverage(_physician()), written)

    seen = reviewed_findings(written, condition.search.findings)

    assert None in seen
    assert len(seen) == len(condition.search.findings)


# The release gate.


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.3.11-01")
def test_a_cleared_name_in_kept_text_is_exempted_as_reviewed():
    coverage = _coverage(_physician())

    condition = release_condition(
        coverage, KEPT_INSTITUTION, reviewed=_seen(coverage, KEPT_INSTITUTION)
    )

    assert condition.decision is Decision.RELEASE
    assert not condition.reasons
    assert [exemption for _, exemption in condition.exempted] == [Exemption.REVIEWED]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_name_in_another_value_is_not_cleared():
    coverage = _coverage(_physician())
    other = _written(_element(0x00080080, "LO", OTHER_INSTITUTION))

    condition = release_condition(
        coverage, other, reviewed=_seen(coverage, KEPT_INSTITUTION)
    )

    assert condition.decision is Decision.QC_REVIEW
    assert [reason.code for reason in condition.reasons] == [KEPT_TEXT_NAME]
    assert not condition.exempted


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_name_from_another_source_is_not_cleared():
    coverage = _coverage(_physician())
    referring = _coverage(_physician("(0008,0090)"))

    condition = release_condition(
        referring, KEPT_INSTITUTION, reviewed=_seen(coverage, KEPT_INSTITUTION)
    )

    assert condition.decision is Decision.QC_REVIEW


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_clearing_never_releases_a_withholding_finding():
    # The same name also in Study Description, which no option keeps.
    written = _written(
        _element(0x00080080, "LO", INSTITUTION),
        _element(0x00081030, "LO", "QUILLONBY REVIEW"),
    )
    coverage = _coverage(_physician())

    # Even a clearing that names every finding releases nothing withheld.
    condition = release_condition(coverage, written, reviewed=_seen(coverage, written))

    assert condition.decision is Decision.WITHHOLD
    assert [(r.decision, r.code) for r in condition.reasons] == [
        (Decision.WITHHOLD, ReasonCode.RESIDUAL_PERSON_NAME)
    ]
    assert [exemption for _, exemption in condition.exempted] == [Exemption.REVIEWED]


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_clearing_never_releases_another_kind_of_finding():
    written = _written(_element(0x00080080, "LO", "QUILLONBY7 HOSPITAL"))
    coverage = _coverage(SourceValue(_top("(0010,0020)"), "LO", "QUILLONBY7"))

    condition = release_condition(coverage, written, reviewed=_seen(coverage, written))

    assert condition.decision is Decision.WITHHOLD
    assert [r.code for r in condition.reasons] == [
        ReasonCode.RESIDUAL_DIRECT_IDENTIFIER
    ]
    assert not condition.exempted


def test_the_gate_refuses_a_clearing_that_is_not_fingerprints():
    with pytest.raises(TypeError):
        release_condition(
            _coverage(_physician()), KEPT_INSTITUTION, reviewed={"(0008,1050)"}
        )


def test_a_residual_review_shows_only_counts():
    finding = next(iter(_seen(_coverage(_physician()), KEPT_INSTITUTION)))
    review = ResidualReview("A-" + "0" * 32, {bytes(32): frozenset({finding})})

    assert repr(review) == (
        f"ResidualReview(reference='A-{'0' * 32}', files=1, findings=1)"
    )
    assert review.of(bytes(32)) == frozenset({finding})
    assert review.of(bytes(range(32))) == frozenset()


@pytest.mark.parametrize(
    "reference, cleared",
    [
        ("A-1", {}),
        ("A-" + "0" * 32, {b"short": frozenset({"x"})}),
        ("A-" + "0" * 32, {bytes(32): frozenset()}),
        ("A-" + "0" * 32, {bytes(32): frozenset({"(0008,1050)"})}),
    ],
)
def test_a_residual_review_is_checked(reference, cleared):
    with pytest.raises(QcPackError):
        ResidualReview(reference, cleared)


# Two runs of a CT slice whose kept Institution Name is named after its
# physician.


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    # A run refuses output paths that could exceed Windows' 259 characters.
    if os.name != "nt":
        yield tmp_path
        return
    directory = Path(tempfile.mkdtemp(prefix="d"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


def _source(directory, institution=INSTITUTION):
    directory.mkdir()
    dataset = synthetic.ct_slice(0)
    dataset.InstitutionName = institution
    dataset.PerformingPhysicianName = PHYSICIAN
    (directory / "0.dcm").write_bytes(synthetic.written(dataset))
    return directory


def _run(directory, source, residual_review=None):
    directory.mkdir()
    transform = InstanceTransform(
        compose_custom_policy((INSTITUTION_IDENTITY,)),
        KEY,
        unvalidated_policy=True,
        residual_review=residual_review,
    )
    result = run.run(
        run.discover(source),
        directory / "release",
        transform,
        ReleaseGate(),
        qc_destination=directory / "qc",
        reporter=transform.reporter,
        written_check=transform.written_check,
    )
    report = json.loads((result.release / RELEASE_REPORT).read_text(encoding="utf-8"))
    return result, report


def _attest(pack, outcome=Outcome.ATTESTED, cleared=(0,)):
    return qc_attestation.attest(
        pack,
        reviewer=REVIEWER,
        outcome=outcome,
        coverage=COMPLETE
        if outcome is Outcome.ATTESTED
        else Coverage(False, False, False),
        cleared_residuals=cleared,
    )


@pytest.fixture(name="first_run")
def fixture_first_run(tmp_path):
    """The source and QC pack of a first run that holds the slice for review."""
    source = _source(tmp_path / "source")
    result, _ = _run(tmp_path / "first", source)
    assert [outcome.status for outcome in result.outcomes] == [
        run.Status.HELD_FOR_REVIEW
    ]
    return source, result.qc_pack.parent


def test_the_pack_shows_the_finding_with_its_values_digest(first_run):
    _, pack = first_run
    document = json.loads((pack / "qc-pack.json").read_text("utf-8"))

    assert document["format"] == PACK_FORMAT == "pymedphys-deid-qc-pack/36"
    (finding,) = document["residual_findings"]
    assert finding["location"]["element"] == "(0008,0080)"
    assert finding["excerpt"] is not None
    value = INSTITUTION.encode("ascii") + b" " * (len(INSTITUTION) % 2)
    assert finding["value_sha256"] == hashlib.sha256(value).hexdigest()
    assert set(
        qc_attestation.shown_residuals(pack.joinpath("qc-pack.json").read_bytes())
    ) == {0}


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-17", "PS3.15-E.3.11-01")
def test_a_cleared_slice_is_released_by_a_later_run(first_run, tmp_path):
    source, pack = first_run
    attestation = _attest(pack)
    assert attestation.cleared_residuals == (0,)

    review = read_residual_review(pack)
    result, report = _run(tmp_path / "second", source, review)

    assert [outcome.status for outcome in result.outcomes] == [run.Status.RELEASED]
    assert report["format"] == REPORT_FORMAT == "pymedphys-deid-release-report/57"
    assert report["residual_review"] == {"reference": attestation.reference}
    assert report["held_for_review"] == []
    assert [
        (entry["exemption"], entry["attribute"], entry["found_in"], entry["count"])
        for entry in report["exempted_findings"]
    ] == [("reviewed", "(0008,1050)", "(0008,0080)", 1)]
    markdown = to_markdown(
        (result.release / RELEASE_REPORT).read_text(encoding="utf-8")
    )
    assert "## Residual review" in markdown
    assert INSTITUTION not in markdown and "QUILLONBY" not in markdown


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_an_uncleared_slice_is_still_held(first_run, tmp_path):
    source, pack = first_run
    # Attested, but the reviewer cleared nothing.
    _attest(pack, cleared=())

    review = read_residual_review(pack)
    result, report = _run(tmp_path / "second", source, review)

    assert not review.cleared
    assert [outcome.status for outcome in result.outcomes] == [
        run.Status.HELD_FOR_REVIEW
    ]
    assert report["residual_review"] == {"reference": review.reference}


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_changed_source_is_still_held(first_run, tmp_path):
    _, pack = first_run
    _attest(pack)
    # Another institution's name, with the same physician's name in it.
    changed = _source(tmp_path / "changed", OTHER_INSTITUTION)

    result, _ = _run(tmp_path / "second", changed, read_residual_review(pack))

    assert [outcome.status for outcome in result.outcomes] == [
        run.Status.HELD_FOR_REVIEW
    ]


def test_a_rejected_attestation_clears_nothing(first_run):
    _, pack = first_run
    with pytest.raises(QcPackError, match="rejected"):
        _attest(pack, Outcome.REJECTED)

    _attest(pack, Outcome.REJECTED, cleared=())
    with pytest.raises(QcPackError, match="rejected"):
        read_residual_review(pack)


def test_a_clearing_names_an_instance_whose_findings_the_pack_shows(first_run):
    _, pack = first_run
    with pytest.raises(QcPackError, match="no finding"):
        _attest(pack, cleared=(1,))


@pytest.mark.parametrize("cleared", [(-1,), (True,), ("0",), (0, 0)])
def test_a_clearing_is_a_run_position_given_once(first_run, cleared):
    _, pack = first_run
    with pytest.raises(QcPackError):
        _attest(pack, cleared=cleared)


def test_an_unattested_pack_is_refused(first_run):
    _, pack = first_run
    with pytest.raises(QcPackError):
        read_residual_review(pack)


def test_the_clearings_are_read_back_as_written(first_run):
    _, pack = first_run
    attestation = _attest(pack)

    written = json.loads((pack / qc_attestation.ATTESTATION_FILE).read_text("ascii"))
    assert written["format"] == "pymedphys-deid-qc-attestation/8"
    assert written["cleared_residuals"] == [0]
    read, data = qc_attestation.attested_pack(pack)
    assert read == attestation
    assert residual_review_of(read, data) == read_residual_review(pack)


# The commands.


def test_the_attestation_command_records_a_clearing(first_run):
    _, pack = first_run
    stdout, stderr = io.StringIO(), io.StringIO()
    status = attestation_command.main(
        [
            str(pack),
            "--reviewer",
            REVIEWER,
            "--outcome",
            "attested",
            "--reviewed-retained-strings",
            "--reviewed-series",
            "--reviewed-high-risk-instances",
            "--residuals-cleared",
            "0",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert status == attestation_command.EXIT_RECORDED, stderr.getvalue()
    assert "  instances with their residual findings cleared: 1" in (
        stdout.getvalue().splitlines()
    )
    assert REVIEWER not in stdout.getvalue() + stderr.getvalue()
    assert read_residual_review(pack).of(
        hashlib.sha256((first_run[0] / "0.dcm").read_bytes()).digest()
    )


def test_the_attestation_command_refuses_an_unshown_clearing(first_run):
    _, pack = first_run
    stdout, stderr = io.StringIO(), io.StringIO()
    status = attestation_command.main(
        [
            str(pack),
            "--reviewer",
            REVIEWER,
            "--outcome",
            "attested",
            "--reviewed-retained-strings",
            "--reviewed-series",
            "--reviewed-high-risk-instances",
            "--residuals-cleared",
            "5",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert status != attestation_command.EXIT_RECORDED
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()
    assert REVIEWER not in stdout.getvalue() + stderr.getvalue()
    assert str(pack) not in stdout.getvalue() + stderr.getvalue()


def _command(tmp_path, pack):
    stdout, stderr = io.StringIO(), io.StringIO()
    status = deidentify_command.main(
        [
            str(tmp_path / "source"),
            str(tmp_path / "release"),
            "--qc-pack",
            str(tmp_path / "qc"),
            "--preset",
            "basic",
            "--residual-review",
            str(pack),
        ],
        stdout=stdout,
        stderr=stderr,
    )
    return status, stdout.getvalue() + stderr.getvalue()


@pytest.fixture(name="enabled")
def _enabled(monkeypatch):
    """Enable ``basic``, which nothing enables yet."""
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))


@pytest.mark.usefixtures("enabled")
def test_the_run_command_refuses_an_unattested_residual_review(first_run, tmp_path):
    _, pack = first_run

    status, output = _command(tmp_path, pack)

    assert status == deidentify_command.EXIT_NOT_RUN
    assert "the residual review could not be read" in output
    assert str(pack) not in output
    assert not (tmp_path / "release").exists()


@pytest.mark.usefixtures("enabled")
def test_the_run_command_gives_the_transform_the_residual_review(
    first_run, tmp_path, monkeypatch
):
    _, pack = first_run
    _attest(pack)
    calls = []

    def recording(*_, **kwargs):
        calls.append(kwargs)
        return deidentify_command.EXIT_RELEASED

    monkeypatch.setattr(deidentify_command, "deidentify_directory", recording)

    status, output = _command(tmp_path, pack)

    assert status == deidentify_command.EXIT_RELEASED, output
    (call,) = calls
    # pylint: disable-next=protected-access
    assert call["transform"]._residual_review == read_residual_review(pack)


def test_a_pilot_releases_a_cleared_slice(first_run, tmp_path):
    source, pack = first_run
    _attest(pack)
    stdout, stderr = io.StringIO(), io.StringIO()

    status = pilot_command.main(
        [
            str(source),
            "--option",
            INSTITUTION_IDENTITY,
            "--release",
            str(tmp_path / "pilot"),
            "--residual-review",
            str(pack),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert (status, stderr.getvalue()) == (pilot_command.EXIT_RELEASED, "")
    assert "  released: 1" in stdout.getvalue().splitlines()
    report = json.loads((tmp_path / "pilot" / RELEASE_REPORT).read_text("utf-8"))
    assert report["residual_review"] == {
        "reference": read_residual_review(pack).reference
    }
