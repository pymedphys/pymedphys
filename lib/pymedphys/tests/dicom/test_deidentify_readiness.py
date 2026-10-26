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

"""The readiness of a ``public-release`` run, by its three gates."""

import dataclasses
import datetime
import hashlib
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    policy,
    qc_attestation,
    qc_previews,
    qc_store,
    readiness,
    release_report,
    release_report_markdown,
    risk_assessment,
    run,
    run_report,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.pixel_region_rules import PixelRegionRules, RuleKey
from pymedphys._dicom.deidentify.pixel_risk import Finding, Indicator
from pymedphys._dicom.deidentify.policy import PolicyError
from pymedphys._dicom.deidentify.qc_attestation import (
    AttestationRecord,
    Coverage,
    Face,
    Outcome,
)
from pymedphys._dicom.deidentify.qc_pack import (
    NO_CONTOURS_SHA256,
    NO_PIXELS_SHA256,
    Disposition,
    InstanceEntry,
    PixelRiskEntry,
    Preview,
    PreviewKind,
    QcPack,
    QcPackError,
    RetainedString,
    SeriesEntry,
)
from pymedphys._dicom.deidentify.readiness import ReadinessReview
from pymedphys._dicom.deidentify.reasons import ReviewReason, StatisticalReason
from pymedphys._dicom.deidentify.release_report import Readiness, ReleaseReportError
from pymedphys._dicom.deidentify.risk_assessment import (
    Assessment,
    Attacker,
    Model,
    Population,
    RiskAssessmentError,
)
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _corpus_run

REVIEWED = "A-" + "0123456789abcdef" * 2
THIS_RUN = "A-" + "fedcba9876543210" * 2
WHEN = datetime.datetime(2026, 10, 23, 9, 30, tzinfo=datetime.timezone.utc)
COMPLETE = Coverage(retained_strings=True, series=True, high_risk_instances=True)
# Text that must never reach an error message, a repr, or a report.
SENTINEL = "SENTINEL^Retained"
REVIEWER = "SENTINEL^Reviewer"
# Instances 0 to 3 are images, each with pixel data that the previews show;
# 4 has neither pixel data nor contours, as an RT Plan has. Two subjects:
# 0, 2, and 3 are one patient's, 1 and 4 the other's.
IMAGES = (0, 1, 2, 3)
SERIES = (SeriesEntry((0, 2, 3)), SeriesEntry((1,)), SeriesEntry((4,)))
FACES = {0: Face.ABSENT, 1: Face.ABSENT}
PATIENTS = {0: "one", 1: "two", 2: "one", 3: "one", 4: "two"}
MANUFACTURER = ElementPath((), "(0008,0070)")
BURNED_IN = Finding(Indicator.BURNED_IN_ANNOTATION, ElementPath((), "(0028,0301)"))
# A region rule of an invented scanner: the top band of its images.
RULE = RuleKey("1.2.840.10008.5.1.4.1.1.6.1", "Acme Sonics", "Echo 5", 480, 640)
BAND = TextBox(0, 0, 40, 640)


def _digest(n):
    return hashlib.sha256(bytes([n])).hexdigest()


def _pixels(n):
    return _digest(100 + n)


def _entry(position, disposition=Disposition.RELEASED, **changes):
    fields = {
        "position": position,
        "source": f"/imports/{position}.dcm",
        "disposition": disposition,
        "source_sha256": _digest(position),
    }
    if disposition is Disposition.SEQUESTERED:
        fields.update(label="S-0001", reasons=("conflicting instance",))
    else:
        fields.update(
            pixel_sha256=_pixels(position) if position in IMAGES else NO_PIXELS_SHA256,
            contour_sha256=NO_CONTOURS_SHA256,
        )
    if disposition is Disposition.HELD_FOR_REVIEW:
        fields.update(reasons=("held",))
    elif disposition is Disposition.RELEASED:
        fields.update(
            output=PurePosixPath(f"ZQ0001/2.25.1/2.25.2/2.25.{position + 3}.dcm")
        )
    fields.update(changes)
    return InstanceEntry(**fields)


def _pack(  # pylint: disable = too-many-arguments
    reference, instances=None, *, series=SERIES, strings=None, risks=(1,), rules=None
):
    """A pack of these instances, released by default, with a preview of each
    frame whose pixel data's SHA-256 it records, as the pack needs."""
    if instances is None:
        instances = tuple(_entry(n) for n in range(5))
    previews = tuple(
        Preview(
            f"P-{number:04d}.png",
            PreviewKind.INSTANCE,
            ((entry.position, 0),),
            1,
            qc_previews.png(np.zeros((2, 2), np.uint8)),
        )
        for number, entry in enumerate(
            (e for e in instances if e.pixel_sha256 not in (None, NO_PIXELS_SHA256)),
            1,
        )
    )
    return QcPack(
        reference,
        instances,
        retained_strings=(
            (RetainedString(SENTINEL, ((0, MANUFACTURER),)),)
            if strings is None
            else strings
        ),
        pixel_risks=tuple(PixelRiskEntry(p, (BURNED_IN,)) for p in risks),
        series=series,
        previews=previews,
        # As a run without Clean Descriptors records them, with any region
        # rules that its Clean Pixel Data applied.
        reviewed_lists=risk_assessment.bind_lists(None, None, rules),
    )


def _report_document(reference, preset="public-release", rules=None):
    """A run's report, where ``rules`` is its region rules' keyed digest."""
    report = release_report.release_report(
        policy.compose_policy(preset),
        vocabulary=None,
        reviewed_roi_names=None,
        qc_review=AttestationRecord(reference, Outcome.NOT_ATTESTED),
        pixel_region_rules=rules,
    )
    return release_report.report_document(report)


POLICY = risk_assessment.policy_digest(_report_document(THIS_RUN))


def _assessment(**changes):
    fields = {
        "model": Model("Population uniqueness", "2", "Invented Estimator", "1.4.0"),
        "attacker": Attacker("Public registries and news reports", True),
        "population": Population(in_cohort="Every subject is in the release"),
        "matching_variables": ("sex", "age at study"),
        "pixel_derived": "Body habitus was matched on",
        "generalisation": "Ages in 5-year bands",
        "missing_data": "Missing values match any value",
        "uncertainty": "95% interval from bootstrap",
        "exclusions": "None",
        "linked_records": "Each subject's studies were assessed together",
        "earlier_releases": "No earlier release",
        "device_identity": "Station names identify the department",
        "institutional_identity": "Local codes were matched on as the site",
        "facial_reconstruction": False,
        "subjects": 2,
        "threshold": risk_assessment.DEFAULT_THRESHOLD,
        "maximum_risk": 0.04,
        "assessor": "SENTINEL^Assessor",
        "assessed_at": WHEN,
    }
    fields.update(changes)
    return Assessment(**fields)


def _reviewed(  # pylint: disable = too-many-arguments
    tmp_path,
    pack=None,
    *,
    outcome=Outcome.ATTESTED,
    faces=None,
    accepted=True,
    assessment=None,
    preset="public-release",
    rules=None,
):
    """Write a reviewed pack, attest it unless ``outcome`` is None, record an
    assessment beside it unless ``assessment`` is False, and read it back."""
    release = tmp_path / "release"
    release.mkdir(exist_ok=True)
    pack = _pack(REVIEWED) if pack is None else pack
    directory = qc_store.write_qc_pack(
        pack, tmp_path / "qc", release_directory=release
    ).parent
    report_file = tmp_path / "release-report.json"
    report_file.write_text(
        json.dumps(_report_document(REVIEWED, preset, rules)), "utf-8"
    )
    if outcome is not None:
        qc_attestation.attest(
            directory,
            reviewer=REVIEWER,
            outcome=outcome,
            coverage=COMPLETE,
            attested_at=WHEN,
            residual_risk_accepted=None if outcome is Outcome.REJECTED else accepted,
            faces=None
            if outcome is Outcome.REJECTED
            else (FACES if faces is None else faces),
        )
    if assessment is not False:
        risk_assessment.record_assessment(
            directory,
            report_file,
            _assessment() if assessment is None else assessment,
        )
    return readiness.read_readiness_review(directory, report_file)


def _readiness(review, pack=None, **changes):
    facts = {"subjects": 2, "policy_sha256": POLICY, "pixel_region_rules": None}
    facts.update(changes)
    return readiness.readiness(
        review,
        _pack(THIS_RUN) if pack is None else pack,
        reviewed_names=None,
        reviewed_descriptors=None,
        **facts,
    )


def _gates(result):
    return (result.statistical, result.pixel_and_face, result.attestation)


# The three gates together.


@pytest.mark.deid_requirement(
    "MIDI-BP-01", "MIDI-BP-07", "MIDI-BP-10", "MIDI-BP-11", "MIDI-BP-15"
)
def test_a_run_is_ready_where_all_three_gates_pass(tmp_path):
    review = _reviewed(tmp_path)
    result = _readiness(review)

    assert _gates(result) == (None, None, None)
    assert result.ready
    assert result.review == REVIEWED
    assert result.assessment == review.assessment.reference


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_without_a_review_every_gate_fails():
    result = _readiness(None)

    assert result == Readiness(
        review=None,
        assessment=None,
        statistical=StatisticalReason.NO_ASSESSMENT,
        pixel_and_face=ReviewReason.NO_REVIEW,
        attestation=ReviewReason.NO_REVIEW,
    )
    assert not result.ready


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-17")
@pytest.mark.parametrize(
    "outcome, reason",
    [(None, ReviewReason.NOT_ATTESTED), (Outcome.REJECTED, ReviewReason.REJECTED)],
)
def test_a_pack_not_attested_fails_both_review_gates_but_not_the_statistical(
    tmp_path, outcome, reason
):
    review = _reviewed(tmp_path, outcome=outcome)
    result = _readiness(review)

    # The gates are independent: the assessment still passes its own.
    assert _gates(result) == (None, reason, reason)
    assert not result.ready
    if outcome is None:
        assert review.outcome is Outcome.NOT_ATTESTED and review.faces is None


@pytest.mark.deid_requirement("MIDI-BP-01", "MIDI-BP-07")
def test_without_an_assessment_only_the_statistical_gate_fails(tmp_path):
    result = _readiness(_reviewed(tmp_path, assessment=False))

    assert _gates(result) == (StatisticalReason.NO_ASSESSMENT, None, None)
    assert result.review == REVIEWED and result.assessment is None
    assert not result.ready


def test_another_collection_fails_every_gate(tmp_path):
    review = _reviewed(tmp_path)
    # A copy fewer of the same files is another collection.
    fewer = _pack(THIS_RUN, tuple(_entry(n) for n in range(4)), series=SERIES[:2])

    assert _gates(_readiness(review, fewer)) == (
        StatisticalReason.OTHER_COLLECTION,
        ReviewReason.OTHER_COLLECTION,
        ReviewReason.OTHER_COLLECTION,
    )


def test_another_policy_fails_every_gate(tmp_path):
    review = _reviewed(tmp_path, preset="basic", assessment=False)
    record_free = _readiness(review)

    assert _gates(record_free)[1:] == (
        ReviewReason.OTHER_POLICY,
        ReviewReason.OTHER_POLICY,
    )


def test_an_assessment_of_another_policy_fails_the_statistical_gate(tmp_path):
    review = _reviewed(tmp_path)
    other = risk_assessment.policy_digest(_report_document(THIS_RUN, "basic"))

    assert _gates(_readiness(review, policy_sha256=other)) == (
        StatisticalReason.OTHER_POLICY,
        ReviewReason.OTHER_POLICY,
        ReviewReason.OTHER_POLICY,
    )


def _ruled(*boxes):
    rules = PixelRegionRules.empty()
    rules.record(RULE, boxes or (BAND,))
    return rules


@pytest.mark.deid_requirement("MIDI-BP-01", "PS3.15-E.3.1-01")
def test_a_later_run_with_the_same_region_rules_passes_every_gate(tmp_path):
    # Each run's report keys the rules' digest under that run's key, so the
    # reports' digests differ for the same rules, and the policy binding
    # leaves them out; the lists' salted digest in the pack binds them.
    review = _reviewed(tmp_path, _pack(REVIEWED, rules=_ruled()), rules="d" * 64)
    this_run = risk_assessment.policy_digest(_report_document(THIS_RUN, rules="e" * 64))
    assert this_run == POLICY

    same = _readiness(
        review,
        _pack(THIS_RUN, rules=_ruled()),
        policy_sha256=this_run,
        pixel_region_rules=_ruled(),
    )
    assert _gates(same) == (None, None, None)
    # Other rules fail the statistical gate. The pixel and face gate holds
    # what they write otherwise by its pixel data's digests, which these
    # invented packs keep the same.
    for other in (_ruled(TextBox(0, 0, 48, 640)), PixelRegionRules.empty(), None):
        edited = _readiness(
            review,
            _pack(THIS_RUN, rules=other),
            policy_sha256=this_run,
            pixel_region_rules=other,
        )
        assert _gates(edited) == (StatisticalReason.OTHER_LISTS, None, None)


@pytest.mark.deid_requirement("MIDI-BP-07")
@pytest.mark.parametrize(
    "subjects, reason",
    [(3, StatisticalReason.FEWER_SUBJECTS), (1, StatisticalReason.MORE_SUBJECTS)],
)
def test_another_count_of_subjects_fails_only_the_statistical_gate(
    tmp_path, subjects, reason
):
    result = _readiness(_reviewed(tmp_path), subjects=subjects)

    assert _gates(result) == (reason, None, None)


@pytest.mark.deid_requirement("MIDI-BP-04")
@pytest.mark.parametrize("statement", [None, "", "   "])
def test_no_run_is_ready_without_a_statement_on_keeping_machine_identity(
    tmp_path, statement
):
    # The statistical gate needs a record, and no record can be made without
    # the statement of whether keeping machine identity would raise the risk.
    with pytest.raises(RiskAssessmentError, match="device_identity"):
        _assessment(device_identity=statement)
    result = _readiness(_reviewed(tmp_path, assessment=False))

    assert result.statistical is StatisticalReason.NO_ASSESSMENT
    assert not result.ready


@pytest.mark.deid_requirement("MIDI-BP-05")
@pytest.mark.parametrize("statement", [None, "", "   "])
def test_no_run_is_ready_without_an_assessment_of_the_institutional_identity_kept(
    tmp_path, statement
):
    # The statistical gate needs a record, and no record can be made without
    # the statement of how the institutional identity that the policy keeps
    # was assessed, and whether the assessment supports keeping it.
    with pytest.raises(RiskAssessmentError, match="institutional_identity"):
        _assessment(institutional_identity=statement)
    result = _readiness(_reviewed(tmp_path, assessment=False))

    assert result.statistical is StatisticalReason.NO_ASSESSMENT
    assert not result.ready


def test_an_assessment_above_its_threshold_fails_only_the_statistical_gate(tmp_path):
    review = _reviewed(tmp_path, assessment=_assessment(maximum_risk=0.1))

    assert _gates(_readiness(review)) == (StatisticalReason.ABOVE_THRESHOLD, None, None)


# The attestation gate.


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-17")
@pytest.mark.parametrize("accepted", [None, False])
def test_the_attestation_gate_needs_the_residual_risk_accepted(tmp_path, accepted):
    result = _readiness(_reviewed(tmp_path, accepted=accepted))

    assert _gates(result) == (None, None, ReviewReason.RESIDUAL_RISK_NOT_ACCEPTED)


def test_an_instance_that_the_reviewed_run_did_not_write_was_not_reviewed(tmp_path):
    # The reviewed run sequestered 3, so no series preview showed it.
    instances = tuple(
        _entry(n, Disposition.SEQUESTERED) if n == 3 else _entry(n) for n in range(5)
    )
    series = (SeriesEntry((0, 2)), *SERIES[1:])
    review = _reviewed(tmp_path, _pack(REVIEWED, instances, series=series))

    result = _readiness(review)

    assert result.attestation is ReviewReason.UNREVIEWED_INSTANCE
    # Nor was its face reviewed.
    assert result.pixel_and_face is ReviewReason.NO_FACE_VERDICT
    assert result.statistical is None


def test_a_released_instance_without_its_source_digest_was_not_reviewed(tmp_path):
    review = _reviewed(tmp_path)
    # The collection's digest leaves out a source without one, so only the
    # attestation gate can tell that it was not reviewed.
    unknown = _entry(5, source_sha256=None)
    # A pack's series name only instances with a source digest.
    pack = _pack(THIS_RUN, (*(_entry(n) for n in range(5)), unknown))

    result = _readiness(review, pack)

    assert _gates(result) == (None, None, ReviewReason.UNREVIEWED_INSTANCE)


def test_a_duplicate_in_the_reviewed_run_is_not_itself_reviewed(tmp_path):
    # The reviewed run recorded 3 as a copy of 2, so only 2's file was
    # previewed; a later run that releases 3's file shows what no one saw.
    copy = InstanceEntry(
        position=3,
        source="/imports/3.dcm",
        disposition=Disposition.DUPLICATE,
        output=_entry(2).output,
        source_sha256=_digest(3),
    )
    instances = tuple(copy if n == 3 else _entry(n) for n in range(5))
    series = (SeriesEntry((0, 2)), *SERIES[1:])
    review = _reviewed(tmp_path, _pack(REVIEWED, instances, series=series))

    assert _readiness(review).attestation is ReviewReason.UNREVIEWED_INSTANCE


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-11")
def test_a_retained_string_that_the_reviewed_pack_lacks_was_not_reviewed(tmp_path):
    review = _reviewed(tmp_path)
    added = RetainedString("ANOTHER SENTINEL", ((2, MANUFACTURER),))
    strings = (RetainedString(SENTINEL, ((0, MANUFACTURER),)), added)

    result = _readiness(review, _pack(THIS_RUN, strings=strings))

    assert _gates(result) == (None, None, ReviewReason.UNREVIEWED_RETAINED_STRING)


def test_only_the_retained_strings_of_released_instances_need_review(tmp_path):
    review = _reviewed(tmp_path)
    instances = tuple(
        _entry(n, Disposition.HELD_FOR_REVIEW) if n == 2 else _entry(n)
        for n in range(5)
    )
    held_only = RetainedString("ANOTHER SENTINEL", ((2, MANUFACTURER),))
    strings = (RetainedString(SENTINEL, ((0, MANUFACTURER),)), held_only)

    result = _readiness(review, _pack(THIS_RUN, instances, strings=strings))

    assert result.attestation is None


# The pixel and face gate.


@pytest.mark.deid_requirement("MIDI-BP-10", "MIDI-BP-11")
def test_a_high_risk_instance_must_have_been_reviewed_as_one(tmp_path):
    review = _reviewed(tmp_path, _pack(REVIEWED, risks=()))

    result = _readiness(review)

    assert _gates(result) == (None, ReviewReason.UNREVIEWED_HIGH_RISK, None)


def test_a_high_risk_instance_that_is_not_released_needs_no_review(tmp_path):
    review = _reviewed(tmp_path, _pack(REVIEWED, risks=()))
    instances = tuple(
        _entry(n, Disposition.HELD_FOR_REVIEW) if n == 1 else _entry(n)
        for n in range(5)
    )

    assert _readiness(review, _pack(THIS_RUN, instances)).pixel_and_face is None


@pytest.mark.deid_requirement("MIDI-BP-15")
@pytest.mark.parametrize(
    "faces, reason",
    [
        ({0: Face.ABSENT, 1: Face.PRESENT}, ReviewReason.FACE_PRESENT),
        # The gravest reason is given first, whatever the instances' order.
        ({1: Face.PRESENT}, ReviewReason.FACE_PRESENT),
        ({1: Face.ABSENT}, ReviewReason.NO_FACE_VERDICT),
        ({}, ReviewReason.NO_FACE_VERDICT),
    ],
)
def test_every_released_instance_that_can_show_a_face_needs_a_verdict_of_absent(
    tmp_path, faces, reason
):
    result = _readiness(_reviewed(tmp_path, faces=faces))

    assert _gates(result) == (None, reason, None)


@pytest.mark.deid_requirement("MIDI-BP-15")
def test_an_instance_without_pixel_data_or_contours_needs_no_verdict(tmp_path):
    # Instance 4's series has no verdict.
    assert _readiness(_reviewed(tmp_path)).pixel_and_face is None


@pytest.mark.deid_requirement("MIDI-BP-15")
@pytest.mark.parametrize("pixels", [_digest(250), None])
def test_a_verdict_covers_only_the_pixel_data_that_the_reviewed_run_showed(
    tmp_path, pixels
):
    review = _reviewed(tmp_path)
    instances = tuple(
        _entry(n, pixel_sha256=pixels) if n == 2 else _entry(n) for n in range(5)
    )

    result = _readiness(review, _pack(THIS_RUN, instances))

    assert result.pixel_and_face is ReviewReason.OTHER_PIXEL_DATA


@pytest.mark.deid_requirement("MIDI-BP-15")
def test_a_verdict_covers_only_the_contours_that_the_reviewed_run_showed(tmp_path):
    review = _reviewed(tmp_path)
    # A structure set whose contours this run's sheet could not show.
    instances = tuple(
        _entry(n, contour_sha256=None) if n == 1 else _entry(n) for n in range(5)
    )

    result = _readiness(review, _pack(THIS_RUN, instances))

    assert result.pixel_and_face is ReviewReason.OTHER_CONTOURS


@pytest.mark.deid_requirement("MIDI-BP-15")
def test_an_assessment_of_facial_reconstruction_stands_in_for_the_verdicts(tmp_path):
    review = _reviewed(
        tmp_path,
        faces={1: Face.PRESENT},
        assessment=_assessment(facial_reconstruction=True),
    )

    assert _gates(_readiness(review)) == (None, None, None)


@pytest.mark.parametrize(
    "assessment",
    [
        _assessment(facial_reconstruction=False),
        # One that fails its own gate stands in for nothing.
        _assessment(facial_reconstruction=True, maximum_risk=0.5),
    ],
    ids=["faces-not-assessed", "above-threshold"],
)
def test_only_a_passing_assessment_of_faces_stands_in_for_the_verdicts(
    tmp_path, assessment
):
    review = _reviewed(tmp_path, faces={}, assessment=assessment)

    assert _readiness(review).pixel_and_face is ReviewReason.NO_FACE_VERDICT


def test_an_assessment_of_faces_does_not_stand_in_for_high_risk_review(tmp_path):
    review = _reviewed(
        tmp_path,
        _pack(REVIEWED, risks=()),
        faces={},
        assessment=_assessment(facial_reconstruction=True),
    )

    assert _readiness(review).pixel_and_face is ReviewReason.UNREVIEWED_HIGH_RISK


# Reading the review.


def test_a_review_holds_nothing_that_names_the_reviewer_and_shows_no_string(
    tmp_path,
):
    review = _reviewed(tmp_path)

    assert isinstance(review, ReadinessReview)
    assert repr(review) == (
        f"ReadinessReview(reference={REVIEWED!r}, outcome='attested')"
    )
    assert REVIEWER not in repr(dataclasses.astuple(review))
    assert review.retained_strings == frozenset({SENTINEL})
    assert review.high_risk == frozenset({bytes.fromhex(_digest(1))})
    assert review.reviewed == frozenset(bytes.fromhex(_digest(n)) for n in range(5))


def test_a_release_report_of_another_pack_is_refused(tmp_path):
    _reviewed(tmp_path)
    other = tmp_path / "other-report.json"
    other.write_text(json.dumps(_report_document(THIS_RUN)), "utf-8")

    with pytest.raises(RiskAssessmentError, match="names another QC pack") as caught:
        readiness.read_readiness_review(tmp_path / "qc", other)
    assert str(tmp_path) not in str(caught.value)


def test_a_pack_changed_after_its_attestation_is_refused(tmp_path):
    _reviewed(tmp_path, assessment=False)
    pack_file = tmp_path / "qc" / qc_store.PACK_FILE
    pack_file.chmod(0o600)
    pack_file.write_bytes(pack_file.read_bytes().replace(b'"S', b'"T', 1))

    with pytest.raises(QcPackError):
        readiness.read_readiness_review(
            tmp_path / "qc", tmp_path / "release-report.json"
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"reference": "A-0"},
        {"outcome": "attested"},
        {"residual_risk_accepted": "yes"},
        {"collection_sha256": "0" * 63},
        {"reviewed": {bytes(32)}},
        {"high_risk": frozenset({bytes([9]) * 32})},
        {"retained_strings": frozenset({1})},
        {"faces": None},
        {"assessment": object()},
    ],
    ids=lambda changes: next(iter(changes)),
)
def test_a_review_is_checked(tmp_path, changes):
    review = _reviewed(tmp_path)
    with pytest.raises(QcPackError):
        dataclasses.replace(review, **changes)


# The report's section.


def _report(readiness_section, preset="public-release"):
    return release_report.release_report(
        policy.compose_policy(preset),
        vocabulary=None,
        reviewed_roi_names=None,
        readiness=readiness_section,
    )


@pytest.mark.deid_requirement("MIDI-BP-01")
def test_the_report_records_the_gates_by_reason_and_reference_alone(tmp_path):
    result = _readiness(_reviewed(tmp_path, faces={}))
    document = release_report.report_document(_report(result))

    assert document["readiness"] == {
        "ready": False,
        "review": REVIEWED,
        "assessment": result.assessment,
        "statistical": None,
        "pixel_and_face": "no-face-verdict",
        "attestation": None,
    }
    assert SENTINEL not in json.dumps(document)
    assert document["format"] == "pymedphys-deid-release-report/30"


def test_a_public_release_report_given_no_readiness_is_not_ready():
    document = release_report.report_document(_report(None))

    assert document["readiness"] == {
        "ready": False,
        "review": None,
        "assessment": None,
        "statistical": "no-assessment",
        "pixel_and_face": "no-review",
        "attestation": "no-review",
    }


def test_a_report_of_another_policy_has_no_readiness():
    assert release_report.report_document(_report(None, "basic"))["readiness"] is None
    with pytest.raises(ReleaseReportError, match="readiness"):
        release_report.report_document(_report(_readiness(None), "basic"))


@pytest.mark.parametrize(
    "changes",
    [
        {"review": "R-" + "0" * 32},
        {"assessment": "A-" + "0" * 32},
        # An assessment without the pack it is recorded beside.
        {"assessment": "R-" + "0" * 32, "statistical": None},
        # A gate fails for the lack of a review exactly without one.
        {"review": REVIEWED},
        {"pixel_and_face": None},
        {"statistical": None},
        # Each gate gives only its own reasons.
        {"attestation": ReviewReason.UNREVIEWED_HIGH_RISK},
        {"pixel_and_face": ReviewReason.UNREVIEWED_RETAINED_STRING},
        {"statistical": ReviewReason.NO_REVIEW},
        {"attestation": "no-review"},
    ],
    ids=repr,
)
def test_the_section_is_checked(changes):
    section = dataclasses.replace(_readiness(None), **changes)

    with pytest.raises(ReleaseReportError, match="readiness") as caught:
        release_report.report_document(_report(section))
    assert "R-" + "0" * 32 not in str(caught.value)


def test_the_markdown_gives_each_gate(tmp_path):
    result = _readiness(_reviewed(tmp_path, accepted=False))
    markdown = release_report_markdown.to_markdown(
        release_report.to_json(_report(result))
    )

    assert "## Readiness for public release" in markdown
    assert "| Ready | `false` |" in markdown
    assert f"| Reviewed QC pack | `{REVIEWED}` |" in markdown
    assert f"| Risk assessment | `{result.assessment}` |" in markdown
    assert "| Statistical gate | passed |" in markdown
    assert "| Pixel and face review gate | passed |" in markdown
    assert "| Attestation gate | `residual-risk-not-accepted` |" in markdown


def test_the_markdown_of_a_run_without_a_review():
    markdown = release_report_markdown.to_markdown(
        release_report.to_json(_report(_readiness(None)))
    )

    assert "| Reviewed QC pack | none |" in markdown
    assert "| Statistical gate | `no-assessment` |" in markdown


# The reporter and the transform.


def test_only_a_public_release_reporter_takes_a_review(tmp_path):
    review = _reviewed(tmp_path)
    with pytest.raises(ValueError, match="public-release"):
        run_report.ReleaseReporter(
            policy.compose_policy("basic"),
            vocabulary=None,
            reviewed_roi_names=None,
            readiness_review=review,
        )
    with pytest.raises(PolicyError, match="public-release"):
        InstanceTransform(
            policy.compose_policy("basic"),
            DeidKey(bytes(range(32))),
            readiness_review=review,
            unvalidated_policy=True,
        )


EMPTY = QcPack(THIS_RUN, ())


def test_a_public_release_report_needs_the_run_facts():
    reporter = run_report.ReleaseReporter(
        policy.compose_policy("public-release"),
        vocabulary=None,
        reviewed_roi_names=None,
    )
    with pytest.raises(TypeError, match="RunFacts"):
        reporter((), {}, THIS_RUN)

    facts = run_report.RunFacts(EMPTY, 0)
    document = json.loads(reporter((), {}, THIS_RUN, facts))
    assert document["readiness"]["ready"] is False
    assert repr(facts) == "RunFacts()"


def test_a_report_of_another_preset_ignores_the_run_facts():
    reporter = run_report.ReleaseReporter(
        policy.compose_policy("basic"), vocabulary=None, reviewed_roi_names=None
    )
    facts = run_report.RunFacts(EMPTY, 0)

    assert json.loads(reporter((), {}, THIS_RUN, facts))["readiness"] is None


def test_released_subjects_counts_distinct_patients_of_released_instances():
    assert readiness.released_subjects(PATIENTS, {0, 1, 2, 3, 4}) == 2
    assert readiness.released_subjects(PATIENTS, {0, 2}) == 1
    # Instances that name no patient are one subject, as the run groups them.
    assert readiness.released_subjects({0: None, 1: None}, {0, 1}) == 1
    assert readiness.released_subjects({**PATIENTS, 5: None}, {0, 1, 5}) == 3
    assert readiness.released_subjects(PATIENTS, set()) == 0


# Two runs of the synthetic collection.


_RADIOTHERAPY = frozenset({"CT Image", "RT Structure Set", "RT Dose", "RT Plan"})


def _public_release(cleaning, review=None):
    return InstanceTransform(
        policy.compose_policy("public-release"),
        _corpus_run.KEY,
        cleaning=cleaning,
        readiness_review=review,
        unvalidated_policy=True,
    )


def _released_patients(release):
    return {
        pydicom.dcmread(path, stop_before_pixels=True).PatientID
        for path in release.rglob("*.dcm")
    }


@pytest.mark.deid_requirement(
    "MIDI-BP-01", "MIDI-BP-07", "MIDI-BP-10", "MIDI-BP-11", "MIDI-BP-15"
)
def test_a_second_run_of_a_reviewed_and_assessed_collection_is_ready():
    # The radiotherapy files alone, which keep the run short: images, a
    # structure set whose contours can show a face, a dose, and a plan,
    # which can show none.
    corpus = corpus_module.build_corpus()
    corpus = dataclasses.replace(
        corpus,
        files=tuple(f for f in corpus.files if f.manifest.iod in _RADIOTHERAPY),
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
            transform = _public_release(cleaning)
            first = run.run(
                instances,
                directory / "r1",
                transform,
                ReleaseGate(),
                qc_destination=directory / "qc1",
                reporter=transform.reporter,
            )
            first_report = first.release / run_report.RELEASE_REPORT
            assert json.loads(first_report.read_text("utf-8"))["readiness"] == {
                "ready": False,
                "review": None,
                "assessment": None,
                "statistical": "no-assessment",
                "pixel_and_face": "no-review",
                "attestation": "no-review",
            }
            pack = first.qc_pack.parent
            entries = json.loads(first.qc_pack.read_text("utf-8"))
            qc_attestation.attest(
                pack,
                reviewer=REVIEWER,
                outcome=Outcome.ATTESTED,
                coverage=COMPLETE,
                attested_at=WHEN,
                residual_risk_accepted=True,
                faces={s["positions"][0]: Face.ABSENT for s in entries["series"]},
            )
            subjects = len(_released_patients(first.release))
            risk_assessment.record_assessment(
                pack,
                first_report,
                _assessment(subjects=subjects),
            )
            review = readiness.read_readiness_review(pack, first_report)
            transform = _public_release(cleaning, review)
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
        "assessment": review.assessment.reference,
        "statistical": None,
        "pixel_and_face": None,
        "attestation": None,
    }
