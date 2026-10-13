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

"""The Clean Recognizable Visual Features Option, claimed from a face review.

Every name, path, and data set here is invented or synthetic.
"""

import dataclasses
import datetime
import json
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    markers,
    qc_attestation,
    qc_store,
    release_report,
    release_report_markdown,
    run,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.face_review import (
    FaceReview,
    carries_visual_features,
    read_face_review,
)
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.method_digest import method_digest
from pymedphys._dicom.deidentify.policy import (
    CLEAN_RECOGNIZABLE_VISUAL_FEATURES,
    PolicyError,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.qc_attestation import Coverage, Face, Outcome
from pymedphys._dicom.deidentify.qc_pack import QcPack, QcPackError
from pymedphys._dicom.deidentify.reasons import (
    HeldVisualFeatures,
    VisualFeaturesReason,
)

from .test_deidentify_qc_face_verdicts import SERIES, _digest, _released

REFERENCE = "A-" + "0123456789abcdef" * 2
KEY = DeidKey(bytes(range(32)))
OPTION = CLEAN_RECOGNIZABLE_VISUAL_FEATURES
CODE = "113102"
COMPLETE = Coverage(retained_strings=True, series=True, high_risk_instances=True)
WHEN = datetime.datetime(2026, 10, 12, 22, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture(name="pack")
def fixture_pack(tmp_path):
    """A QC pack of five released instances in two series, (0, 2, 3) and (1, 4)."""
    release = tmp_path / "release"
    release.mkdir()
    written = QcPack(REFERENCE, tuple(_released(n) for n in range(5)), series=SERIES)
    return qc_store.write_qc_pack(
        written, tmp_path / "secretdir-qc", release_directory=release
    ).parent


def _sha(*numbers):
    return frozenset(bytes.fromhex(_digest(n)) for n in numbers)


def _attest(directory, faces):
    return qc_attestation.attest(
        directory,
        reviewer="Quokka Wombatson",
        outcome=Outcome.ATTESTED,
        coverage=COMPLETE,
        attested_at=WHEN,
        faces=faces,
    )


def _policy(*options):
    return compose_custom_policy([*options, OPTION])


# The face review.


def test_each_verdict_gives_its_series_source_digests(pack):
    _attest(pack, {SERIES[0].positions[0]: Face.ABSENT, 1: Face.PRESENT})

    review = read_face_review(pack)

    assert review.absent == _sha(0, 2, 3)
    assert review.present == _sha(1, 4)
    assert review.reference == REFERENCE


def test_a_series_without_a_verdict_gives_no_digests(pack):
    _attest(pack, {1: Face.ABSENT})

    review = read_face_review(pack)

    assert review.absent == _sha(1, 4)
    assert not review.present


def test_a_pack_that_is_not_attested_gives_no_review(pack):
    with pytest.raises(QcPackError, match="has not been attested"):
        read_face_review(pack)


def test_a_pack_changed_after_its_verdicts_gives_no_review(pack):
    _attest(pack, {1: Face.ABSENT})
    written = pack / "qc-pack.json"
    written.write_bytes(written.read_bytes().replace(b'"', b'"', 1) + b" ")

    with pytest.raises(QcPackError) as raised:
        read_face_review(pack)
    assert str(pack) not in str(raised.value)


def test_a_source_file_is_released_only_from_a_series_marked_absent():
    review = FaceReview(REFERENCE, _sha(0), _sha(1))

    assert review.hold_reason(next(iter(_sha(0)))) is None
    assert review.hold_reason(next(iter(_sha(1)))) is VisualFeaturesReason.FACE_PRESENT
    # Any other file, such as one changed since the review, has no verdict.
    assert (
        review.hold_reason(next(iter(_sha(2)))) is VisualFeaturesReason.NO_FACE_VERDICT
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"reference": "A-0123"},
        {"reference": REFERENCE.upper()},
        {"absent": {bytes(32)}},
        {"present": frozenset({bytes(31)})},
        {"absent": frozenset({"0" * 64})},
    ],
    ids=repr,
)
def test_a_face_review_is_checked(fields):
    review = {"reference": REFERENCE, "absent": frozenset(), "present": frozenset()}
    with pytest.raises(QcPackError):
        FaceReview(**{**review, **fields})


def test_the_repr_shows_only_the_reference_and_counts():
    review = FaceReview(REFERENCE, _sha(0, 2), _sha(1))

    assert repr(review) == f"FaceReview(reference={REFERENCE!r}, absent=2, present=1)"


@pytest.mark.parametrize(
    "keyword, iod, carries",
    [
        ("PixelData", "CT Image", True),
        ("FloatPixelData", "Parametric Map", True),
        ("DoubleFloatPixelData", "Parametric Map", True),
        (None, "RT Structure Set", True),
        (None, "RT Plan", False),
        (None, "MR Spectroscopy", False),
    ],
)
def test_an_instance_needs_a_verdict_where_it_can_show_a_face(keyword, iod, carries):
    dataset = pydicom.Dataset()
    if keyword is not None:
        setattr(dataset, keyword, b"\x00\x00\x00\x00")

    assert carries_visual_features(dataset, iod) is carries


# The markers and the transform.


def test_the_option_can_go_unsatisfied_in_an_instance_held_for_its_face_review():
    policy = _policy()
    digest = method_digest(policy, vocabulary=None, reviewed_roi_names=None)

    held = markers.markers_for(policy, digest, satisfied=[])
    claimed = markers.markers_for(policy, digest, satisfied=[OPTION])

    assert [c.code_value for c in held.method_codes] == [markers.PROFILE_CODE]
    assert [c.code_value for c in claimed.method_codes] == [
        markers.PROFILE_CODE,
        CODE,
    ]


def test_the_markers_set_recognizable_visual_features_to_no_with_the_code():
    policy = _policy()
    digest = method_digest(policy, vocabulary=None, reviewed_roi_names=None)
    found = markers.markers_for(policy, digest, satisfied=[OPTION])
    unsatisfied = markers.markers_for(policy, digest, satisfied=[])
    dataset = pydicom.Dataset()
    dataset.RecognizableVisualFeatures = "YES"

    assert found.recognizable_visual_features == "NO"
    # Added whether or not the IOD defines it, as in an empty data set.
    assert (
        markers.apply_markers(pydicom.Dataset(), found).RecognizableVisualFeatures
        == "NO"
    )
    assert "RecognizableVisualFeatures" not in markers.apply_markers(
        pydicom.Dataset(), unsatisfied
    )
    assert (
        markers.apply_markers(dataset, unsatisfied).RecognizableVisualFeatures == "YES"
    )
    marked = markers.apply_markers(dataset, found)
    assert marked.RecognizableVisualFeatures == "NO"
    assert dataset.RecognizableVisualFeatures == "YES"
    with pytest.raises(ValueError, match=r"\(0028,0302\) is not NO"):
        markers.apply_markers(
            dataset, dataclasses.replace(found, recognizable_visual_features="YES")
        )


def test_a_face_review_is_given_exactly_with_the_option():
    review = FaceReview(REFERENCE, frozenset(), frozenset())

    with pytest.raises(PolicyError, match="a face review is given exactly"):
        InstanceTransform(_policy(), KEY, unvalidated_policy=True)
    with pytest.raises(PolicyError, match="a face review is given exactly"):
        InstanceTransform(
            compose_policy("basic"), KEY, face_review=review, unvalidated_policy=True
        )


def test_the_option_is_applied_but_not_enabled():
    review = FaceReview(REFERENCE, frozenset(), frozenset())

    with pytest.raises(PolicyError, match="not enabled"):
        InstanceTransform(_policy(), KEY, face_review=review)


# The conformance statement and the release report.


def test_the_statement_gives_the_code_only_after_the_face_review():
    statement = conformance.conformance_statement(
        compose_custom_policy(["clean_descriptors", OPTION]), vocabulary=None
    )

    assert CODE not in statement.markers.codes
    # In the policy's order, which puts the option after Table E.1-1's.
    assert statement.markers.review_codes == ("113105", CODE)
    text = conformance_markdown.render_markdown(statement)
    assert (
        "then Clean Recognizable Visual Features Option (DCM 113102) only in an "
        "instance that cannot show a face" in text
    )
    assert (
        "also has Recognizable Visual Features (0028,0302) set to NO, as PS3.15 "
        "E.3.2 requires, including in an IOD that does not define the attribute"
    ) in text


def test_the_statement_of_the_option_alone_has_one_review_code():
    statement = conformance.conformance_statement(_policy(), vocabulary=None)

    assert statement.markers.codes == (markers.PROFILE_CODE,)
    assert statement.markers.review_codes == (CODE,)


def test_the_report_names_the_reviewed_pack_by_its_reference():
    report = release_report.release_report(
        _policy(), vocabulary=None, reviewed_roi_names=None, face_review=REFERENCE
    )
    held = release_report.held_for_review(
        [(HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT),)]
    )
    report = dataclasses.replace(report, held_for_review=held)
    document = release_report.report_document(report)

    assert document["face_review"] == {"reference": REFERENCE}
    assert document["held_for_review"] == [
        {"stage": "visual-features", "code": "no-face-verdict", "count": 1}
    ]
    text = release_report_markdown.to_markdown(release_report.to_json(report))
    assert "## Face review" in text
    assert f"`{REFERENCE}`" in text


def test_a_report_without_a_face_review_has_none():
    report = release_report.release_report(
        compose_policy("basic"), vocabulary=None, reviewed_roi_names=None
    )

    assert release_report.report_document(report)["face_review"] is None
    text = release_report_markdown.to_markdown(release_report.to_json(report))
    assert "## Face review" not in text


@pytest.mark.parametrize("reference", ["A-0123", "S-0001", 7])
def test_the_report_refuses_a_face_review_that_is_not_a_reference(reference):
    report = release_report.release_report(
        _policy(), vocabulary=None, reviewed_roi_names=None, face_review=reference
    )
    with pytest.raises(ValueError):
        release_report.report_document(report)


# A second run of the synthetic collection, given the first run's verdicts.

_CT = ("01-ct-1.dcm", "02-ct-2.dcm")
_DOSE = ("06-rtdose.dcm", "07-rtdose-review.dcm")
_STRUCTURE_SET = "04-rtstruct.dcm"


@pytest.fixture(name="second_run", scope="module")
def fixture_second_run():
    corpus = corpus_module.build_corpus()
    # A short directory, since a run refuses output paths that could exceed
    # Windows' 259 characters.
    directory = Path(tempfile.mkdtemp(prefix="d"))
    try:
        corpus_module.write_corpus(corpus, directory)
        instances = directory / corpus_module.INSTANCES_DIRECTORY
        first = run.run(
            run.discover(instances),
            directory / "r1",
            InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True),
            ReleaseGate(),
            qc_destination=directory / "qc1",
        )
        pack_directory = first.qc_pack.parent
        entries = json.loads(first.qc_pack.read_text("utf-8"))
        names = {e["position"]: Path(e["source"]).name for e in entries["instances"]}
        by_first = {names[s["positions"][0]]: s for s in entries["series"]}
        attestation = _attest(
            pack_directory,
            {
                by_first[_CT[0]]["positions"][0]: Face.ABSENT,
                by_first[_STRUCTURE_SET]["positions"][0]: Face.ABSENT,
                by_first[_DOSE[0]]["positions"][0]: Face.PRESENT,
            },
        )
        review = read_face_review(pack_directory)
        transform = InstanceTransform(
            _policy(), KEY, face_review=review, unvalidated_policy=True
        )
        # The same files, renamed so that they are found in the reverse
        # order, since the verdicts follow the files' contents alone.
        again = directory / "again"
        again.mkdir()
        files = sorted(instances.iterdir())
        for number, file in enumerate(reversed(files)):
            shutil.copyfile(file, again / f"{number:02d}{file.name}")
        second = run.run(
            run.discover(again),
            directory / "r2",
            transform,
            ReleaseGate(),
            qc_destination=directory / "qc2",
            reporter=transform.reporter,
        )
        pack_entries = json.loads(second.qc_pack.read_text("utf-8"))["instances"]
        outcomes = {
            Path(entry["source"]).name[2:]: (
                entry["disposition"],
                None
                if entry.get("output") is None
                else pydicom.dcmread(directory / "r2" / entry["output"]),
            )
            for entry in pack_entries
        }
        report = json.loads((directory / "r2" / "release-report.json").read_text())
        yield attestation, outcomes, report, second
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _codes(dataset):
    return [
        item.get("CodeValue") for item in dataset.DeidentificationMethodCodeSequence
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_series_marked_absent_is_released_with_the_option(second_run):
    _, outcomes, _, _ = second_run

    # The RT Structure Set's IOD does not define the attribute, but E.3.2
    # adds it with the option's code all the same.
    for name in (*_CT, _STRUCTURE_SET):
        disposition, dataset = outcomes[name]
        assert disposition == "released", name
        assert dataset.RecognizableVisualFeatures == "NO"
        assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_every_other_instance_that_can_show_a_face_is_held(second_run):
    _, outcomes, report, result = second_run
    can_show = {
        name
        for name in outcomes
        if name not in (*_CT, _STRUCTURE_SET)
        and name != corpus_module.SEQUESTERED_FILE
        and name not in ("05-rtplan.dcm", "14-mr-spectroscopy.dcm")
    }

    assert can_show >= set(_DOSE)
    for name in can_show:
        assert outcomes[name] == ("held-for-review", None), name
    held = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert held == {"face-present": 2, "no-face-verdict": len(can_show) - 2}
    reasons = {
        reason
        for outcome in result.outcomes
        for reason in outcome.reasons
        if isinstance(reason, HeldVisualFeatures)
    }
    assert reasons == {
        HeldVisualFeatures(VisualFeaturesReason.FACE_PRESENT),
        HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT),
    }


@pytest.mark.deid_requirement("PS3.15-E.3.2-02")
def test_an_instance_that_cannot_show_a_face_satisfies_the_option(second_run):
    _, outcomes, _, _ = second_run

    for name in ("05-rtplan.dcm", "14-mr-spectroscopy.dcm"):
        disposition, dataset = outcomes[name]
        assert disposition == "released", name
        assert CODE in _codes(dataset)
        # Neither IOD defines Recognizable Visual Features, but E.3.2 adds
        # it with the option's code all the same.
        assert dataset.RecognizableVisualFeatures == "NO"


def test_the_report_names_the_attested_pack(second_run):
    attestation, _, report, _ = second_run

    assert report["face_review"] == {"reference": attestation.reference}
    assert report["format"] == "pymedphys-deid-release-report/14"


def test_a_held_reason_is_a_visual_features_reason():
    with pytest.raises(TypeError):
        HeldVisualFeatures("face-present")  # type: ignore[arg-type]
