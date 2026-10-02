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

"""A reviewer's attestation of a QC pack, and the release report's record of it."""

import datetime
import hashlib
import json
import os
import stat
from pathlib import PurePosixPath

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import qc_attestation, qc_store
from pymedphys._dicom.deidentify.qc_attestation import (
    Attestation,
    AttestationRecord,
    Coverage,
    Outcome,
)
from pymedphys._dicom.deidentify.qc_pack import (
    Disposition,
    InstanceEntry,
    QcPack,
    QcPackError,
)

REFERENCE = "A-" + "0123456789abcdef" * 2
REVIEWER = "Invented Reviewer"
WHEN = datetime.datetime(2026, 10, 2, 17, 30, tzinfo=datetime.timezone.utc)
COMPLETE = Coverage(retained_strings=True, series=True, high_risk_instances=True)


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
        pack, tmp_path / "qc", release_directory=release
    ).parent


def _attest(directory, outcome=Outcome.ATTESTED, coverage=COMPLETE):
    return qc_attestation.attest(
        directory,
        reviewer=REVIEWER,
        outcome=outcome,
        coverage=coverage,
        attested_at=WHEN,
    )


def test_an_unattested_pack_is_recorded_as_not_attested(pack):
    assert qc_attestation.attestation_record(pack) == AttestationRecord(
        REFERENCE, Outcome.NOT_ATTESTED
    )


@pytest.mark.parametrize("outcome", [Outcome.ATTESTED, Outcome.REJECTED])
def test_the_record_holds_only_the_reference_and_outcome(pack, outcome):
    _attest(pack, outcome)
    record = qc_attestation.attestation_record(pack)
    assert record == AttestationRecord(REFERENCE, outcome)
    assert [field.name for field in qc_attestation.dataclasses.fields(record)] == [
        "reference",
        "outcome",
    ]


def test_the_attestation_is_written_beside_the_pack(pack):
    attestation = _attest(pack)
    written = pack / qc_attestation.ATTESTATION_FILE
    digest = hashlib.sha256((pack / qc_store.PACK_FILE).read_bytes()).hexdigest()
    assert json.loads(written.read_text("ascii")) == {
        "format": "pymedphys-deid-qc-attestation/1",
        "reference": REFERENCE,
        "pack_digest": digest,
        "outcome": "attested",
        "coverage": {
            "retained_strings": True,
            "series": True,
            "high_risk_instances": True,
        },
        "reviewer": REVIEWER,
        "attested_at": "2026-10-02T17:30:00+00:00",
    }
    assert attestation.pack_digest == digest
    if os.name == "posix":
        assert stat.S_IMODE(written.stat().st_mode) == 0o600


def test_attested_needs_every_review_that_d_017_requires(pack):
    for missing in ("retained_strings", "series", "high_risk_instances"):
        partial = Coverage(
            **{**qc_attestation.dataclasses.asdict(COMPLETE), missing: False}
        )
        assert not partial.complete
        with pytest.raises(QcPackError, match="every review that D-017 requires"):
            _attest(pack, Outcome.ATTESTED, partial)
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()
    rejected = _attest(pack, Outcome.REJECTED, Coverage(False, False, False))
    assert rejected.outcome is Outcome.REJECTED


def test_not_attested_cannot_be_attested(pack):
    with pytest.raises(QcPackError, match="attested or rejected"):
        _attest(pack, Outcome.NOT_ATTESTED)


def test_a_pack_is_attested_once(pack):
    _attest(pack, Outcome.REJECTED, Coverage(False, True, True))
    with pytest.raises(QcPackError, match="already been attested"):
        _attest(pack)
    assert qc_attestation.attestation_record(pack).outcome is Outcome.REJECTED


def test_a_pack_changed_after_attestation_is_detected(pack):
    _attest(pack)
    path = pack / qc_store.PACK_FILE
    path.chmod(0o600)
    path.write_bytes(path.read_bytes().replace(b"a.dcm", b"b.dcm"))
    with pytest.raises(QcPackError, match="changed after it was attested"):
        qc_attestation.attestation_record(pack)


def test_an_attestation_for_another_pack_is_detected(pack):
    _attest(pack)
    path = pack / qc_attestation.ATTESTATION_FILE
    document = json.loads(path.read_text("ascii"))
    document["reference"] = "A-" + "f" * 32
    path.write_text(json.dumps(document), "ascii")
    with pytest.raises(QcPackError, match="for another QC pack"):
        qc_attestation.attestation_record(pack)


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not json",
        b"[]",
        b'{"format": "x"}',
        b'{"format": "pymedphys-deid-qc-attestation/1"}',
    ],
)
def test_a_malformed_attestation_is_refused(pack, content):
    (pack / qc_attestation.ATTESTATION_FILE).write_bytes(content)
    with pytest.raises(QcPackError, match="not of its format"):
        qc_attestation.attestation_record(pack)


def test_an_attestation_with_another_outcome_is_refused(pack):
    _attest(pack)
    path = pack / qc_attestation.ATTESTATION_FILE
    document = json.loads(path.read_text("ascii"))
    document["outcome"] = "not-attested"
    path.write_text(json.dumps(document), "ascii")
    with pytest.raises(QcPackError, match="not of its format"):
        qc_attestation.attestation_record(pack)


def test_a_directory_without_a_pack_is_refused(tmp_path, pack):
    with pytest.raises(QcPackError, match="holds no QC pack"):
        qc_attestation.attestation_record(tmp_path)
    with pytest.raises(QcPackError, match="holds no QC pack"):
        _attest(tmp_path)
    (pack / qc_store.PACK_FILE).unlink()
    with pytest.raises(QcPackError, match="holds no QC pack"):
        qc_attestation.attestation_record(pack)


def test_a_pack_of_another_format_is_refused(pack):
    path = pack / qc_store.PACK_FILE
    path.chmod(0o600)
    path.write_text('{"format": "other", "reference": "%s"}' % REFERENCE, "ascii")
    with pytest.raises(QcPackError, match="not of its format"):
        _attest(pack)


@pytest.mark.parametrize(
    "fields, match",
    [
        ({"reference": "A-1"}, "reference"),
        ({"pack_digest": "0" * 63}, "SHA-256"),
        ({"coverage": (True, True, True)}, "Coverage"),
        ({"reviewer": "  "}, "reviewer"),
        ({"attested_at": WHEN.replace(tzinfo=None)}, "UTC"),
        (
            {
                "attested_at": WHEN.astimezone(
                    datetime.timezone(datetime.timedelta(hours=10))
                )
            },
            "UTC",
        ),
    ],
)
def test_an_attestation_is_checked(fields, match):
    fields = {
        "reference": REFERENCE,
        "pack_digest": "0" * 64,
        "outcome": Outcome.ATTESTED,
        "coverage": COMPLETE,
        "reviewer": REVIEWER,
        "attested_at": WHEN,
        **fields,
    }
    with pytest.raises(QcPackError, match=match):
        Attestation(**fields)


def test_coverage_is_true_or_false():
    with pytest.raises(QcPackError, match="True or False"):
        Coverage(1, True, True)


def test_the_attestation_repr_leaves_out_the_reviewer(pack):
    assert REVIEWER not in repr(_attest(pack))


def test_the_time_defaults_to_now_in_utc(pack):
    before = datetime.datetime.now(datetime.timezone.utc)
    attestation = qc_attestation.attest(
        pack, reviewer=REVIEWER, outcome=Outcome.ATTESTED, coverage=COMPLETE
    )
    assert (
        before
        <= attestation.attested_at
        <= datetime.datetime.now(datetime.timezone.utc)
    )


def test_the_record_matches_the_release_report_shape():
    record = AttestationRecord(REFERENCE, Outcome.ATTESTED)
    assert record.outcome.value in {"attested", "rejected", "not-attested"}
    with pytest.raises(QcPackError, match="reference"):
        AttestationRecord("S-0001", Outcome.ATTESTED)
    with pytest.raises(QcPackError, match="Outcome"):
        AttestationRecord(REFERENCE, "attested")
