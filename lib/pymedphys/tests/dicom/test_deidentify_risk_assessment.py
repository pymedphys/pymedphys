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

"""The record of an external statistical risk assessment, and the statistical gate."""

import dataclasses
import datetime
import hashlib
import json
import os
import stat
from pathlib import PurePosixPath

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    policy,
    qc_store,
    release_report,
    risk_assessment,
)
from pymedphys._dicom.deidentify.qc_attestation import AttestationRecord, Outcome
from pymedphys._dicom.deidentify.qc_pack import (
    Disposition,
    InstanceEntry,
    QcPack,
    QcPackError,
)
from pymedphys._dicom.deidentify.risk_assessment import (
    Assessment,
    AssessmentRecord,
    Attacker,
    Model,
    Population,
    RiskAssessmentError,
    StatisticalGate,
    StatisticalReason,
)

PACK = "A-" + "0123456789abcdef" * 2
OTHER_PACK = "A-" + "fedcba9876543210" * 2
WHEN = datetime.datetime(2026, 10, 23, 9, 30, tzinfo=datetime.timezone.utc)
# Text that must never reach an error message or a repr.
SENTINEL = "SENTINEL^Assessor"
# The SHA-256 of three source files, the last read twice, as identical
# copies are.
SOURCES = (bytes([1]) * 32, bytes([2]) * 32, bytes([3]) * 32, bytes([3]) * 32)


def _assessment(**changes):
    fields = {
        "model": Model("Population uniqueness", "2", "Invented Estimator", "1.4.0"),
        "attacker": Attacker("Public registries and news reports", True),
        "population": Population(in_cohort="Every subject is in the release"),
        "matching_variables": ("sex", "age at study", "body habitus from images"),
        "pixel_derived": "Body habitus and implants were matched on",
        "generalisation": "Ages in 5-year bands",
        "missing_data": "Missing values match any value",
        "uncertainty": "95% interval from bootstrap",
        "exclusions": "None",
        "linked_records": "Each subject's studies were assessed together",
        "earlier_releases": "No earlier release",
        "device_identity": "Station names identify the department, so are omitted",
        "facial_reconstruction": False,
        "subjects": 3,
        "threshold": risk_assessment.DEFAULT_THRESHOLD,
        "maximum_risk": 0.04,
        "assessor": SENTINEL,
        "assessed_at": WHEN,
    }
    fields.update(changes)
    return Assessment(**fields)


def _report(reference=PACK, preset="basic", **fields):
    report = release_report.release_report(
        policy.compose_policy(preset),
        vocabulary=None,
        reviewed_roi_names=fields.pop("reviewed_roi_names", None),
        reviewed_descriptors=fields.pop("reviewed_descriptors", None),
        qc_review=AttestationRecord(reference, Outcome.NOT_ATTESTED),
        **fields,
    )
    return release_report.report_document(report)


@pytest.fixture(name="pack")
def fixture_pack(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    instances = tuple(
        InstanceEntry(
            position,
            f"/imports/{position}.dcm",
            Disposition.RELEASED,
            output=PurePosixPath(f"ZQ0001/2.25.1/2.25.2/2.25.{position + 3}.dcm"),
            source_sha256=digest.hex(),
        )
        for position, digest in enumerate(SOURCES)
    ) + (
        # A file that the run could not read has no digest.
        InstanceEntry(
            len(SOURCES),
            "/imports/unreadable",
            Disposition.REFUSED,
            reasons=("unreadable file",),
        ),
    )
    return qc_store.write_qc_pack(
        QcPack(PACK, instances), tmp_path / "qc", release_directory=release
    ).parent


@pytest.fixture(name="report_file")
def fixture_report_file(tmp_path):
    path = tmp_path / "release-report.json"
    path.write_text(json.dumps(_report()), "utf-8")
    return path


def _gate(record, **changes):
    run = {
        "collection_sha256": risk_assessment.collection_digest(SOURCES),
        "policy_sha256": risk_assessment.policy_digest(_report()),
        "subjects": 3,
    }
    run.update(changes)
    return risk_assessment.statistical_gate(record, **run)


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-07")
def test_the_record_is_written_beside_the_pack_and_read_back(pack, report_file):
    record = risk_assessment.record_assessment(pack, report_file, _assessment())
    written = pack / risk_assessment.ASSESSMENT_FILE
    document = json.loads(written.read_text("ascii"))
    digest = hashlib.sha256((pack / qc_store.PACK_FILE).read_bytes()).hexdigest()
    assert document == {
        "format": "pymedphys-deid-risk-assessment/1",
        "reference": record.reference,
        "pack": PACK,
        "pack_digest": digest,
        "collection_sha256": risk_assessment.collection_digest(SOURCES),
        "policy_sha256": risk_assessment.policy_digest(_report()),
        "model": {
            "name": "Population uniqueness",
            "version": "2",
            "implementation": "Invented Estimator",
            "implementation_version": "1.4.0",
        },
        "attacker": {
            "knowledge": "Public registries and news reports",
            "membership_known": True,
        },
        "population": {
            "reference": None,
            "sampling": None,
            "in_cohort": "Every subject is in the release",
        },
        "matching_variables": ["sex", "age at study", "body habitus from images"],
        "pixel_derived": "Body habitus and implants were matched on",
        "generalisation": "Ages in 5-year bands",
        "missing_data": "Missing values match any value",
        "uncertainty": "95% interval from bootstrap",
        "exclusions": "None",
        "linked_records": "Each subject's studies were assessed together",
        "earlier_releases": "No earlier release",
        "device_identity": "Station names identify the department, so are omitted",
        "facial_reconstruction": False,
        "subjects": 3,
        "threshold": 0.09,
        "maximum_risk": 0.04,
        "assessor": SENTINEL,
        "assessed_at": "2026-10-23T09:30:00+00:00",
    }
    assert record.reference.startswith("R-") and len(record.reference) == 34
    assert record.pack_digest == digest
    assert risk_assessment.read_assessment(pack) == record
    if os.name == "posix":
        assert stat.S_IMODE(written.stat().st_mode) == 0o600


def test_each_record_has_a_new_random_reference(tmp_path, report_file):
    references = set()
    release = tmp_path / "release"
    release.mkdir()
    for name in ("one", "two"):
        directory = qc_store.write_qc_pack(
            QcPack(PACK, ()), tmp_path / name, release_directory=release
        ).parent
        record = risk_assessment.record_assessment(
            directory, report_file, _assessment()
        )
        references.add(record.reference)
    assert len(references) == 2


def test_a_pack_without_a_record_has_none(pack):
    assert risk_assessment.read_assessment(pack) is None


def test_the_reprs_show_no_statement(pack, report_file):
    record = risk_assessment.record_assessment(pack, report_file, _assessment())
    for shown in (repr(record), repr(record.assessment)):
        assert SENTINEL not in shown
        assert "registries" not in shown
    assert repr(record.assessment) == (
        "Assessment(threshold=0.09, within_threshold=True)"
    )


@pytest.mark.deid_requirement("MIDI-BP-07")
@pytest.mark.parametrize(
    "field",
    [
        "pixel_derived",
        "generalisation",
        "missing_data",
        "uncertainty",
        "exclusions",
        "linked_records",
        "earlier_releases",
        "device_identity",
        "assessor",
    ],
)
@pytest.mark.parametrize("value", [None, "", "   ", 3])
def test_every_statement_is_required(field, value):
    with pytest.raises(RiskAssessmentError) as raised:
        _assessment(**{field: value})
    assert field in str(raised.value)


@pytest.mark.deid_requirement("MIDI-BP-07")
@pytest.mark.parametrize(
    "field", ["name", "version", "implementation", "implementation_version"]
)
def test_the_model_and_its_implementation_are_versioned(field):
    fields = {
        "name": "Model",
        "version": "1",
        "implementation": "Tool",
        "implementation_version": "1.0",
    }
    fields[field] = " "
    with pytest.raises(RiskAssessmentError, match=field):
        Model(**fields)


def test_the_attacker_states_knowledge_and_membership():
    with pytest.raises(RiskAssessmentError, match="knowledge"):
        Attacker("", True)
    with pytest.raises(RiskAssessmentError, match="membership"):
        Attacker("Registries", None)  # type: ignore[arg-type]
    for name in ("model", "attacker", "population"):
        with pytest.raises(RiskAssessmentError, match=name):
            _assessment(**{name: None})


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"reference": "State cancer registry"},
        {"sampling": "Every patient treated in 2025"},
        {
            "reference": "State cancer registry",
            "sampling": "Every patient treated in 2025",
            "in_cohort": "Every subject is in the release",
        },
        {"reference": "State cancer registry", "in_cohort": "The release"},
        {"in_cohort": " "},
    ],
)
def test_the_population_is_a_reference_with_sampling_or_the_cohort(fields):
    with pytest.raises(RiskAssessmentError, match="population"):
        Population(**fields)


def test_a_reference_population_needs_its_sampling():
    population = Population("State cancer registry", "Every patient treated in 2025")
    assert _assessment(population=population).population == population


@pytest.mark.deid_requirement("MIDI-BP-07")
@pytest.mark.parametrize(
    "variables", [(), ["sex"], ("sex", ""), ("sex", "sex"), ("sex", None)]
)
def test_the_matching_variables_are_listed_each_once(variables):
    with pytest.raises(RiskAssessmentError, match="matching variable"):
        _assessment(matching_variables=variables)


@pytest.mark.parametrize("subjects", [0, -1, True, 2.0, "3", None])
def test_subjects_are_a_whole_number_of_at_least_one(subjects):
    with pytest.raises(RiskAssessmentError, match="subjects"):
        _assessment(subjects=subjects)


@pytest.mark.parametrize("threshold", [0.1, 0.0, 0.08999, True, "0.09", None])
def test_the_threshold_is_the_default_or_the_strict_one(threshold):
    with pytest.raises(RiskAssessmentError, match="threshold"):
        _assessment(threshold=threshold)


@pytest.mark.parametrize(
    "risk", [-0.001, 1.001, float("nan"), float("inf"), True, "0.01", None]
)
def test_the_maximum_probability_is_from_zero_to_one(risk):
    with pytest.raises(RiskAssessmentError, match="maximum"):
        _assessment(maximum_risk=risk)


@pytest.mark.parametrize(
    "when",
    [
        datetime.datetime(2026, 10, 23, 9, 30),
        datetime.datetime(
            2026, 10, 23, 9, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=11))
        ),
        "2026-10-23T09:30:00+00:00",
    ],
)
def test_the_time_of_the_assessment_is_in_utc(when):
    with pytest.raises(RiskAssessmentError, match="UTC"):
        _assessment(assessed_at=when)


def test_facial_reconstruction_is_true_or_false():
    with pytest.raises(RiskAssessmentError, match="facial"):
        _assessment(facial_reconstruction=None)


def test_a_record_checks_its_binding():
    good = {
        "reference": "R-" + "0" * 32,
        "pack": PACK,
        "pack_digest": "a" * 64,
        "collection_sha256": "b" * 64,
        "policy_sha256": "c" * 64,
        "assessment": _assessment(),
    }
    assert AssessmentRecord(**good).reference == good["reference"]
    for name, value in (
        ("reference", PACK),
        ("pack", "R-" + "0" * 32),
        ("pack_digest", "A" * 64),
        ("collection_sha256", None),
        ("policy_sha256", "c" * 63),
        ("assessment", None),
    ):
        with pytest.raises(RiskAssessmentError):
            AssessmentRecord(**{**good, name: value})


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-07")
def test_the_gate_passes_a_bound_assessment_within_its_threshold(pack, report_file):
    record = risk_assessment.record_assessment(pack, report_file, _assessment())
    gate = _gate(risk_assessment.read_assessment(pack))
    assert gate == StatisticalGate(record.reference, None)
    assert gate.passed


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_the_gate_fails_without_an_assessment():
    gate = _gate(None)
    assert gate == StatisticalGate(None, StatisticalReason.NO_ASSESSMENT)
    assert not gate.passed


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-07")
@pytest.mark.parametrize(
    ("threshold", "risk", "reason"),
    [
        (0.09, 0.09, None),
        (0.09, 0.0, None),
        (0.09, 0.09000000000000001, StatisticalReason.ABOVE_THRESHOLD),
        (0.09, 1, StatisticalReason.ABOVE_THRESHOLD),
        (0.05, 0.05, None),
        (0.05, 0.0500001, StatisticalReason.ABOVE_THRESHOLD),
        (0.05, 0.07, StatisticalReason.ABOVE_THRESHOLD),
    ],
)
def test_the_threshold_is_met_at_its_boundary(
    pack, report_file, threshold, risk, reason
):
    risk_assessment.record_assessment(
        pack, report_file, _assessment(threshold=threshold, maximum_risk=risk)
    )
    record = risk_assessment.read_assessment(pack)
    assert record.assessment.maximum_risk == risk
    assert _gate(record).reason is reason


@pytest.mark.deid_requirement("MIDI-BP-07")
@pytest.mark.parametrize(
    ("subjects", "reason"),
    [
        (2, StatisticalReason.FEWER_SUBJECTS),
        (3, None),
        # Counting files, or visits, rather than subjects.
        (4, StatisticalReason.MORE_SUBJECTS),
    ],
)
def test_the_gate_counts_subjects_not_instances(pack, report_file, subjects, reason):
    risk_assessment.record_assessment(pack, report_file, _assessment(subjects=subjects))
    assert _gate(risk_assessment.read_assessment(pack)).reason is reason


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "collection",
    [
        SOURCES[:3],  # one copy fewer
        SOURCES + SOURCES[:1],
        SOURCES[:3] + (bytes([4]) * 32,),  # a file changed
        (),
    ],
)
def test_the_gate_fails_for_another_collection(pack, report_file, collection):
    risk_assessment.record_assessment(pack, report_file, _assessment())
    gate = _gate(
        risk_assessment.read_assessment(pack),
        collection_sha256=risk_assessment.collection_digest(collection),
    )
    assert gate.reason is StatisticalReason.OTHER_COLLECTION


@pytest.mark.deid_requirement("MIDI-BP-01")
@pytest.mark.parametrize(
    "report",
    [
        {"preset": "basic-clean-descriptors"},
        {"reviewed_roi_names": "d" * 64},
        {"reviewed_descriptors": "e" * 64},
    ],
)
def test_the_gate_fails_for_another_policy(pack, report_file, report):
    risk_assessment.record_assessment(pack, report_file, _assessment())
    gate = _gate(
        risk_assessment.read_assessment(pack),
        policy_sha256=risk_assessment.policy_digest(_report(**report)),
    )
    assert gate.reason is StatisticalReason.OTHER_POLICY


def test_the_first_failure_is_given():
    record = AssessmentRecord(
        "R-" + "0" * 32,
        PACK,
        "a" * 64,
        "b" * 64,
        "c" * 64,
        _assessment(subjects=2, maximum_risk=0.5),
    )
    run = {"collection_sha256": "b" * 64, "policy_sha256": "c" * 64, "subjects": 3}
    assert (
        risk_assessment.statistical_gate(
            record, **{**run, "collection_sha256": "f" * 64, "policy_sha256": "f" * 64}
        ).reason
        is StatisticalReason.OTHER_COLLECTION
    )
    assert (
        risk_assessment.statistical_gate(
            record, **{**run, "policy_sha256": "f" * 64}
        ).reason
        is StatisticalReason.OTHER_POLICY
    )
    assert (
        risk_assessment.statistical_gate(record, **run).reason
        is StatisticalReason.FEWER_SUBJECTS
    )
    assert (
        risk_assessment.statistical_gate(record, **{**run, "subjects": 2}).reason
        is StatisticalReason.ABOVE_THRESHOLD
    )


@pytest.mark.parametrize(
    "run",
    [
        {"collection_sha256": "B" * 64},
        {"policy_sha256": None},
        {"subjects": -1},
        {"subjects": True},
    ],
)
def test_the_gate_checks_the_run(run):
    with pytest.raises(RiskAssessmentError):
        _gate(None, **run)


def test_the_gate_names_a_record_exactly_where_one_was_given():
    with pytest.raises(RiskAssessmentError):
        StatisticalGate(None, None)
    with pytest.raises(RiskAssessmentError):
        StatisticalGate("R-" + "0" * 32, StatisticalReason.NO_ASSESSMENT)
    with pytest.raises(RiskAssessmentError):
        StatisticalGate(PACK, None)


def test_the_collection_is_the_files_read_whatever_their_order():
    digest = risk_assessment.collection_digest(SOURCES)
    assert digest == risk_assessment.collection_digest(reversed(SOURCES))
    assert digest == hashlib.sha256(b"".join(sorted(SOURCES))).hexdigest()
    assert digest != risk_assessment.collection_digest(SOURCES[:3])
    with pytest.raises(RiskAssessmentError):
        risk_assessment.collection_digest([bytes(31)])
    with pytest.raises(RiskAssessmentError):
        risk_assessment.collection_digest(["0" * 64])


def test_the_policy_digest_leaves_out_only_what_each_run_keys():
    plain = risk_assessment.policy_digest(_report())
    # Another pack, and the keyed digests of the same lists under another
    # key, give the same digest.
    assert risk_assessment.policy_digest(_report(OTHER_PACK)) == plain
    listed = risk_assessment.policy_digest(
        _report(reviewed_roi_names="d" * 64, reviewed_descriptors="e" * 64)
    )
    assert listed != plain
    assert listed == risk_assessment.policy_digest(
        _report(reviewed_roi_names="1" * 64, reviewed_descriptors="2" * 64)
    )
    document = _report()
    document["method"] = {**document["method"], "method_digest": "f" * 64}
    assert risk_assessment.policy_digest(document) == plain
    # Every other component of the method is bound, such as an engine file.
    document["method"]["engine_files"] = {
        **document["method"]["engine_files"],
        "policy.py": "0" * 64,
    }
    assert risk_assessment.policy_digest(document) != plain


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"policy": {}},
        {"policy": {}, "method": {"reviewed_roi_names": None}},
        {"policy": [], "method": {}},
        [],
    ],
)
def test_the_policy_digest_needs_the_report_sections(document):
    with pytest.raises(RiskAssessmentError, match="format"):
        risk_assessment.policy_digest(document)


def test_a_report_of_another_pack_is_refused(pack, tmp_path):
    other = tmp_path / "other.json"
    other.write_text(json.dumps(_report(OTHER_PACK)), "utf-8")
    with pytest.raises(RiskAssessmentError, match="another QC pack"):
        risk_assessment.record_assessment(pack, other, _assessment())
    assert not (pack / risk_assessment.ASSESSMENT_FILE).exists()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "[]",
        "not json",
        json.dumps({"format": "pymedphys-deid-release-report/1"}),
    ],
)
def test_a_report_not_of_its_format_is_refused(pack, tmp_path, text):
    path = tmp_path / SENTINEL
    path.write_text(text, "utf-8")
    with pytest.raises(RiskAssessmentError, match="format") as raised:
        risk_assessment.record_assessment(pack, path, _assessment())
    assert SENTINEL not in str(raised.value)


def test_a_missing_report_is_refused_without_its_path(pack, tmp_path):
    with pytest.raises(QcPackError) as raised:
        risk_assessment.record_assessment(pack, tmp_path / SENTINEL, _assessment())
    assert SENTINEL not in str(raised.value)


def test_a_directory_without_a_pack_is_refused(tmp_path, report_file):
    with pytest.raises(QcPackError, match="no QC pack"):
        risk_assessment.record_assessment(tmp_path, report_file, _assessment())
    with pytest.raises(QcPackError, match="no QC pack"):
        risk_assessment.read_assessment(tmp_path)


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_pack_is_assessed_once(pack, report_file):
    first = risk_assessment.record_assessment(pack, report_file, _assessment())
    with pytest.raises(RiskAssessmentError, match="already"):
        risk_assessment.record_assessment(
            pack, report_file, _assessment(maximum_risk=0.01)
        )
    assert risk_assessment.read_assessment(pack) == first


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_a_pack_changed_after_it_was_assessed_is_refused(pack, report_file):
    risk_assessment.record_assessment(pack, report_file, _assessment())
    file = pack / qc_store.PACK_FILE
    document = json.loads(file.read_text("ascii"))
    document["instances"][0]["source_sha256"] = "9" * 64
    os.chmod(file, 0o600)
    file.write_text(json.dumps(document), "ascii")
    with pytest.raises(RiskAssessmentError, match="changed"):
        risk_assessment.read_assessment(pack)


def _rewrite(pack, change):
    file = pack / risk_assessment.ASSESSMENT_FILE
    document = json.loads(file.read_text("ascii"))
    change(document)
    os.chmod(file, 0o600)
    file.write_text(json.dumps(document), "ascii")


def test_a_record_for_another_pack_is_refused(pack, report_file):
    risk_assessment.record_assessment(pack, report_file, _assessment())
    _rewrite(pack, lambda document: document.update(pack=OTHER_PACK))
    with pytest.raises(RiskAssessmentError, match="another QC pack"):
        risk_assessment.read_assessment(pack)


def test_a_record_whose_collection_was_edited_is_refused(pack, report_file):
    risk_assessment.record_assessment(pack, report_file, _assessment())
    _rewrite(pack, lambda document: document.update(collection_sha256="0" * 64))
    with pytest.raises(RiskAssessmentError, match="changed"):
        risk_assessment.read_assessment(pack)


@pytest.mark.parametrize(
    "change",
    [
        lambda document: document.update(format="pymedphys-deid-risk-assessment/0"),
        lambda document: document.update(extra=1),
        lambda document: document.pop("earlier_releases"),
        lambda document: document.pop("linked_records"),
        lambda document: document.pop("device_identity"),
        lambda document: document.pop("model"),
        lambda document: document["model"].pop("version"),
        lambda document: document["attacker"].update(extra=1),
        lambda document: document.update(threshold=0.2),
        lambda document: document.update(maximum_risk="0.01"),
        lambda document: document.update(subjects=0),
        lambda document: document.update(assessed_at="23 October 2026"),
        lambda document: document.update(matching_variables="sex"),
        lambda document: document.update(reference=PACK),
    ],
)
def test_a_record_not_of_its_format_is_refused(pack, report_file, change):
    risk_assessment.record_assessment(pack, report_file, _assessment())
    _rewrite(pack, change)
    with pytest.raises(RiskAssessmentError, match="not of its format") as raised:
        risk_assessment.read_assessment(pack)
    assert SENTINEL not in str(raised.value)


def test_errors_quote_no_statement():
    for changes in (
        {"generalisation": ""},
        {"matching_variables": (SENTINEL, SENTINEL)},
        {"threshold": 0.5},
    ):
        with pytest.raises(RiskAssessmentError) as raised:
            _assessment(**changes)
        assert SENTINEL not in str(raised.value)
    # Every field of the statement is checked when a record is made, whatever
    # changed it.
    with pytest.raises(RiskAssessmentError):
        dataclasses.replace(_assessment(), assessor="")
