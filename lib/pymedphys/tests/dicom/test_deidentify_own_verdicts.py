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

"""A reviewer's face verdict of its own on an instance in a defaced CT
series' Frame of Reference whose outline or pixel data the run does not
clean of the face: the QC pack's undefaced instances, the attestation's
verdicts and its command, the face review that gives them to a later run,
and the release report's record. Every UID and value here is invented."""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import os
import stat
from pathlib import Path, PurePosixPath

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import attestation_command as command
from pymedphys._dicom.deidentify import (
    qc_attestation,
    qc_pack,
    qc_previews,
    qc_store,
    release_report,
    release_report_markdown,
    run,
    run_qc,
    run_report,
)
from pymedphys._dicom.deidentify.face_review import (
    UNDEFACED_TEXT,
    FaceReview,
    read_face_review,
)
from pymedphys._dicom.deidentify.qc_attestation import (
    Coverage,
    Face,
    InstanceFaceVerdict,
    Outcome,
)
from pymedphys._dicom.deidentify.qc_pack import (
    NO_CONTOURS_SHA256,
    NO_GRIDS_SHA256,
    Disposition,
    InstanceEntry,
    QcPack,
    QcPackError,
    UndefacedEntry,
)
from pymedphys._dicom.deidentify.reasons import VisualFeaturesReason

from .test_deidentify_release_report import _output_name
from .test_deidentify_visual_features_option import _policy

REFERENCE = "A-" + "0123456789abcdef" * 2
COMPLETE = Coverage(retained_strings=True, series=True, high_risk_instances=True)
REVIEWER = "Quokka Wombatson"
_EVERY_REVIEW = (
    "--reviewed-retained-strings",
    "--reviewed-series",
    "--reviewed-high-risk-instances",
)


def _digest(n):
    return hashlib.sha256(bytes([n])).hexdigest()


def _sha(n):
    return bytes.fromhex(_digest(n))


# PET instances and RT Doses have no contours, nor deformation grids.
_NONE = bytes.fromhex(NO_CONTOURS_SHA256)


# The QC pack's undefaced instances.


def _held(position, digest=True, shown=True, grids=True):
    """An undefaced instance held for review, whose pack has the digests
    of its pixel data where ``shown``, and of its grids, of none, where
    ``grids``."""
    return InstanceEntry(
        position,
        f"/imports/{position}.dcm",
        Disposition.HELD_FOR_REVIEW,
        reasons=(UNDEFACED_TEXT,),
        source_sha256=_digest(position) if digest else None,
        pixel_sha256=_digest(100 + position) if shown else None,
        contour_sha256=NO_CONTOURS_SHA256,
        grid_sha256=NO_GRIDS_SHA256 if grids else None,
    )


def _released(position, shown=True):
    return InstanceEntry(
        position,
        f"/imports/{position}.dcm",
        Disposition.RELEASED,
        output=PurePosixPath(f"ZQ0001/2.25.1/2.25.2/2.25.{position + 3}.dcm"),
        source_sha256=_digest(position),
        pixel_sha256=_digest(100 + position) if shown else None,
        contour_sha256=NO_CONTOURS_SHA256,
        grid_sha256=NO_GRIDS_SHA256,
    )


def _previews(instances):
    """A cine strip of each instance with a pixel digest, so that the pack
    has a preview that shows its pixel data."""
    shown = [entry.position for entry in instances if entry.pixel_sha256]
    return tuple(
        qc_pack.Preview(
            f"P-{n + 1:04d}.png",
            qc_pack.PreviewKind.SERIES_CINE,
            ((position, 0),),
            1,
            qc_previews.png(np.zeros((2, 2), np.uint8)),
        )
        for n, position in enumerate(shown)
    )


def _pack(instances, entries):
    return QcPack(
        REFERENCE,
        instances,
        previews=_previews(instances),
        undefaced_instances=entries,
    )


def test_the_pack_lists_each_undefaced_instance_with_whether_it_is_shown():
    entries = (
        UndefacedEntry(0, True),
        UndefacedEntry(1, False),
        UndefacedEntry(2, True),
    )

    pack = _pack((_held(0), _held(1, shown=False), _released(2)), entries)

    assert pack.undefaced_instances == entries
    assert _pack((_held(0, grids=False),), (UndefacedEntry(0, False),))
    assert qc_pack.pack_document(pack)["undefaced_instances"] == [
        {"position": 0, "shown": True},
        {"position": 1, "shown": False},
        {"position": 2, "shown": True},
    ]
    assert repr(pack).endswith("undefaced_instances=3)")


@pytest.mark.parametrize(
    "fields, match",
    [
        ((-1, True), "run position"),
        ((True, True), "run position"),
        ((0, 1), "true or false"),
        ((0, None), "true or false"),
    ],
)
def test_an_undefaced_entry_is_checked(fields, match):
    with pytest.raises(QcPackError, match=match):
        UndefacedEntry(*fields)


def _sequestered(position):
    return InstanceEntry(
        position,
        f"/imports/{position}.dcm",
        Disposition.SEQUESTERED,
        label="S-0001",
        reasons=("x",),
        source_sha256=_digest(position),
    )


@pytest.mark.parametrize(
    "instances, entries, match",
    [
        (
            (_held(0), _held(1)),
            (UndefacedEntry(1, True), UndefacedEntry(0, True)),
            "once, in order",
        ),
        ((_held(0),), (UndefacedEntry(0, True),) * 2, "once, in order"),
        ((_held(0),), (UndefacedEntry(1, True),), "without an instance"),
        ((_held(0, digest=False),), (UndefacedEntry(0, True),), "source's SHA-256"),
        ((_sequestered(0),), (UndefacedEntry(0, False),), "neither released nor"),
        ((_held(0, shown=False),), (UndefacedEntry(0, True),), "shown exactly"),
        ((_held(0),), (UndefacedEntry(0, False),), "shown exactly"),
        # Its pixel data and contours shown do not show it whole where the
        # pack has no digest of its deformation grids, whose sheets did not
        # all show them.
        ((_held(0, grids=False),), (UndefacedEntry(0, True),), "shown exactly"),
    ],
)
def test_a_pack_s_undefaced_instances_are_checked(instances, entries, match):
    with pytest.raises(QcPackError, match=match):
        _pack(instances, entries)


def test_a_run_s_pack_lists_the_released_and_held_undefaced_instances():
    material = {
        0: (run_qc.UndefacedMaterial(),),
        1: (run_qc.UndefacedMaterial(own_verdict=True),),
        2: (run_qc.UndefacedMaterial(),),
        3: (run_qc.UndefacedMaterial(),),
    }
    outcomes = (
        run.Outcome(
            0, run.Status.HELD_FOR_REVIEW, (run.RunReason.DICOMDIR,), None, None, None
        ),
        run.Outcome(1, run.Status.RELEASED, (), PurePosixPath("a/1.dcm"), None, None),
        run.Outcome(
            2, run.Status.SEQUESTERED, (run.RunReason.DICOMDIR,), None, None, "S-0001"
        ),
        run.Outcome(
            3, run.Status.HELD_FOR_REVIEW, (run.RunReason.DICOMDIR,), None, None, None
        ),
    )
    sources = [Path(f"in/{n}.dcm") for n in range(4)]
    # The instance at 3 has no source digest to bind a verdict to.
    digests = {n: _sha(n) for n in range(3)}

    pack = run_qc.qc_pack_of(sources, outcomes, material, digests=digests)

    # The sequestered one reaches no recipient, so needs no verdict. With no
    # written file handed over, neither has its digests, so neither is shown.
    assert pack.undefaced_instances == (
        UndefacedEntry(0, False),
        UndefacedEntry(1, False),
    )


def test_undefaced_material_is_checked():
    assert run_qc.UndefacedMaterial().own_verdict is False
    with pytest.raises(ValueError, match="true or false"):
        run_qc.UndefacedMaterial(own_verdict=1)


# The attestation's verdicts of their own.


@pytest.fixture(name="own_pack")
def fixture_own_pack(tmp_path):
    """A pack of an undefaced instance held at 0, shown, in a series with
    the instance at 1, which is not undefaced; one held at 2, not shown,
    and one released at 3, shown, each in a series of its own."""
    release = tmp_path / "release"
    release.mkdir()
    instances = (
        _held(0),
        dataclasses.replace(
            _released(1), pixel_sha256=None, contour_sha256=None, grid_sha256=None
        ),
        _held(2, shown=False),
        _released(3),
    )
    pack = QcPack(
        REFERENCE,
        instances,
        series=(
            qc_pack.SeriesEntry((0, 1)),
            qc_pack.SeriesEntry((2,)),
            qc_pack.SeriesEntry((3,)),
        ),
        previews=_previews(instances),
        undefaced_instances=(
            UndefacedEntry(0, True),
            UndefacedEntry(2, False),
            UndefacedEntry(3, True),
        ),
    )
    return qc_store.write_qc_pack(
        pack, tmp_path / "qc", release_directory=release
    ).parent


def _judge(directory, own, outcome=Outcome.ATTESTED, faces=None):
    return qc_attestation.attest(
        directory,
        reviewer=REVIEWER,
        outcome=outcome,
        coverage=COMPLETE,
        faces=faces,
        instance_faces=own,
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_reviewer_gives_an_instance_its_own_verdict_by_its_run_position(own_pack):
    attestation = _judge(own_pack, {3: Face.PRESENT, 0: Face.ABSENT})
    written = json.loads((own_pack / qc_attestation.ATTESTATION_FILE).read_text())

    assert attestation.instance_faces == (
        InstanceFaceVerdict(0, Face.ABSENT),
        InstanceFaceVerdict(3, Face.PRESENT),
    )
    assert written["instance_faces"] == [
        {"position": 0, "face": "absent"},
        {"position": 3, "face": "present"},
    ]
    assert qc_attestation.attested_pack(own_pack)[0] == attestation


def test_the_pack_gives_whether_each_undefaced_instance_is_shown(own_pack):
    data = (own_pack / qc_store.PACK_FILE).read_bytes()

    assert qc_attestation.undefaced_instances(data) == {0: True, 2: False, 3: True}


@pytest.mark.parametrize(
    "own, match",
    [
        ({1: Face.ABSENT}, "undefaced_instances does not list"),
        ({2: Face.ABSENT}, "do not show all"),
        ({-1: Face.ABSENT}, "run position"),
        ({0: "absent"}, "needs a Face"),
        ([(0, Face.ABSENT)], "must map"),
    ],
)
def test_an_own_verdict_needs_an_undefaced_instance_that_the_pack_shows(
    own_pack, own, match
):
    with pytest.raises(QcPackError, match=match):
        _judge(own_pack, own)
    assert not (own_pack / qc_attestation.ATTESTATION_FILE).exists()


def test_a_rejected_pack_gives_no_verdict_of_an_instance_s_own(own_pack):
    with pytest.raises(QcPackError, match="rejected"):
        _judge(own_pack, {0: Face.ABSENT}, outcome=Outcome.REJECTED)


@pytest.mark.parametrize(
    "verdicts",
    [
        (InstanceFaceVerdict(3, Face.ABSENT), InstanceFaceVerdict(0, Face.ABSENT)),
        (InstanceFaceVerdict(0, Face.ABSENT), InstanceFaceVerdict(0, Face.PRESENT)),
        [InstanceFaceVerdict(0, Face.ABSENT)],
        ((0, Face.ABSENT),),
    ],
)
def test_an_attestation_s_own_verdicts_are_by_position_in_order(own_pack, verdicts):
    attestation = _judge(own_pack, {})

    with pytest.raises(QcPackError, match="instance"):
        dataclasses.replace(attestation, instance_faces=verdicts)


def _rewrite(directory, change):
    path = directory / qc_attestation.ATTESTATION_FILE
    document = json.loads(path.read_text())
    change(document)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    path.write_text(json.dumps(document), "ascii")


def test_an_attestation_without_its_own_verdicts_is_not_of_its_format(own_pack):
    _judge(own_pack, {})
    _rewrite(own_pack, lambda document: document.pop("instance_faces"))

    with pytest.raises(QcPackError, match="not of its format"):
        qc_attestation.attested_pack(own_pack)


@pytest.mark.parametrize("position", [1, 2])
def test_an_own_verdict_changed_to_another_instance_is_refused(own_pack, position):
    _judge(own_pack, {0: Face.ABSENT})

    def change(document):
        document["instance_faces"] = [{"position": position, "face": "absent"}]

    _rewrite(own_pack, change)

    # The attestation no longer matches what attest checked: an instance
    # that is not undefaced, or one whose previews do not show it whole.
    with pytest.raises(QcPackError, match="names no undefaced instance"):
        read_face_review(own_pack)


# The face review's verdicts of their own.


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_series_verdict_never_covers_an_undefaced_instance(own_pack):
    _judge(own_pack, {}, faces={0: Face.ABSENT, 3: Face.ABSENT})

    review = read_face_review(own_pack)

    # The held one and the released one alike were in a defaced frame and
    # not cleaned of the face, so their series' verdicts may have been given
    # beside the defaced CT; the other instance of the first series is
    # covered.
    assert _sha(0) not in review.absent
    assert _sha(3) not in review.absent
    assert _sha(1) in review.absent
    assert not review.own_verdicts
    assert review.hold_reason(_sha(0), _sha(100), _NONE, 1) is (
        VisualFeaturesReason.NO_FACE_VERDICT
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_an_own_verdict_decides_its_instance(own_pack):
    _judge(own_pack, {0: Face.ABSENT, 3: Face.PRESENT})

    review = read_face_review(own_pack)

    # Its own verdict of absent binds it to the pixel data and contours that
    # its previews showed, as a series' verdict binds its files.
    assert review.own_verdicts == {_sha(0), _sha(3)}
    assert review.own_verdict(_sha(0)) and review.own_verdict(_sha(3))
    assert not review.own_verdict(_sha(1))
    assert _sha(0) in review.absent and _sha(3) in review.present
    assert review.hold_reason(_sha(0), _sha(100), _NONE, 1) is None
    assert review.hold_reason(_sha(0), _sha(101), _NONE, 1) is (
        VisualFeaturesReason.OTHER_PIXEL_DATA
    )
    assert review.hold_reason(_sha(0), _sha(100), _sha(201), 1) is (
        VisualFeaturesReason.OTHER_CONTOURS
    )
    # Pixel data of more frames than its previews showed were not all seen.
    assert review.hold_reason(_sha(0), _sha(100), _NONE, 2) is (
        VisualFeaturesReason.OTHER_PIXEL_DATA
    )
    assert review.hold_reason(_sha(3), _sha(103), _NONE, 1) is (
        VisualFeaturesReason.FACE_PRESENT
    )


def test_a_face_seen_in_its_series_holds_an_instance_its_own_verdict_clears(
    own_pack,
):
    _judge(own_pack, {0: Face.ABSENT}, faces={0: Face.PRESENT})

    review = read_face_review(own_pack)

    assert review.hold_reason(_sha(0), _sha(100), _NONE, 1) is (
        VisualFeaturesReason.FACE_PRESENT
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"own_verdicts": frozenset({b"x" * 31})},
        {"own_verdicts": {b"x" * 32}},
        {"own_verdicts": frozenset({b"x" * 32})},
    ],
)
def test_a_face_review_s_own_verdicts_are_checked(fields):
    with pytest.raises(QcPackError, match="SHA-256 digests|own verdicts"):
        FaceReview(REFERENCE, frozenset(), frozenset(), **fields)


def test_the_repr_counts_the_own_verdicts():
    review = FaceReview(
        REFERENCE, frozenset({_sha(0)}), frozenset(), own_verdicts=frozenset({_sha(0)})
    )

    assert repr(review).endswith("dose_choices=0, own_verdicts=1)")


# The command's verdicts of their own.


def _command(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    status = command.main(list(argv), stdout=stdout, stderr=stderr)
    return status, stdout.getvalue(), stderr.getvalue()


def test_the_command_records_each_own_verdict(own_pack):
    status, stdout, stderr = _command(
        str(own_pack),
        "--reviewer",
        REVIEWER,
        "--outcome",
        "attested",
        *_EVERY_REVIEW,
        "--instance-face-absent",
        "0",
        "--instance-face-present",
        "3",
        "--instance-face-absent",
        "0",
    )

    assert status == command.EXIT_RECORDED, stderr
    written = json.loads((own_pack / qc_attestation.ATTESTATION_FILE).read_text())
    assert written["instance_faces"] == [
        {"position": 0, "face": "absent"},
        {"position": 3, "face": "present"},
    ]
    lines = stdout.splitlines()
    assert (
        "  undefaced instances without a recognisable face in their own previews: 1"
        in lines
    )
    assert (
        "  undefaced instances with a recognisable face in their own previews: 1"
        in lines
    )
    assert REVIEWER not in stdout + stderr


@pytest.mark.parametrize(
    "verdicts, message",
    [
        (
            ("--instance-face-absent", "0", "--instance-face-present", "0"),
            "both face verdicts of its own",
        ),
        (("--instance-face-absent", "1"), "undefaced_instances does not list"),
        (("--instance-face-present", "2"), "do not show all"),
    ],
)
def test_the_command_refuses_an_own_verdict_it_cannot_record(
    own_pack, verdicts, message
):
    status, stdout, stderr = _command(
        str(own_pack),
        "--reviewer",
        REVIEWER,
        "--outcome",
        "attested",
        *_EVERY_REVIEW,
        *verdicts,
    )

    assert status == command.EXIT_NOT_RECORDED
    assert message in stderr and "nothing was recorded" in stderr
    assert not stdout
    assert not (own_pack / qc_attestation.ATTESTATION_FILE).exists()


# The release report's record.


_NAMES = tuple(_output_name(instance=f"sop-{n}") for n in range(3))


def _report(undefaced, released=_NAMES):
    return release_report.release_report(
        _policy(),
        vocabulary=None,
        reviewed_roi_names=None,
        face_review=REFERENCE,
        undefaced_instances=undefaced,
        released=released,
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_the_report_records_each_undefaced_instance_by_its_own_verdict():
    undefaced = release_report.UndefacedInstances(
        held=2, released=(_NAMES[2], _NAMES[0]), held_with_own_verdict=1
    )

    report = _report(undefaced)
    document = release_report.report_document(report)

    assert document["face_review"]["undefaced_in_defaced_frame"] == {
        "held": 2,
        "released": [str(_NAMES[0]), str(_NAMES[2])],
        "held_with_own_verdict": 1,
    }
    text = release_report_markdown.to_markdown(release_report.to_json(report))
    assert "held without such a verdict: `2`" in text
    assert "the run writes other pixel data, contours, or deformation grids" in text
    assert "a block of its own frame that cleaned it awaits confirmation" in text
    assert "or another hold applies: `1`" in text
    assert "cleaned only by the blocks of its own frame:" in text
    assert f"| `{_NAMES[0]}` |" in text
    assert f"| `{_NAMES[2]}` |" in text


def test_the_report_with_a_face_review_records_no_undefaced_instance_by_default():
    report = _report(None)

    assert report.undefaced_instances == release_report.UndefacedInstances()
    assert release_report.report_document(report)["face_review"][
        "undefaced_in_defaced_frame"
    ] == {"held": 0, "released": [], "held_with_own_verdict": 0}
    text = release_report_markdown.to_markdown(release_report.to_json(report))
    assert "held without such a verdict: `0`" in text


def test_the_report_without_a_face_review_records_no_undefaced_instances():
    report = release_report.release_report(
        _policy(), vocabulary=None, reviewed_roi_names=None
    )

    assert report.undefaced_instances is None
    with pytest.raises(ValueError, match="undefaced instances without a face review"):
        release_report.report_document(
            dataclasses.replace(
                report, undefaced_instances=release_report.UndefacedInstances()
            )
        )


@pytest.mark.parametrize(
    "undefaced, match",
    [
        (release_report.UndefacedInstances(held=-1), "held is negative"),
        (release_report.UndefacedInstances(held=1.0), "held is not a whole"),
        (
            release_report.UndefacedInstances(held_with_own_verdict=True),
            "held_with_own_verdict is not a whole",
        ),
        (
            release_report.UndefacedInstances(
                released=(PurePosixPath("elsewhere/x.dcm"),)
            ),
            "not a tuple of output names",
        ),
        (
            release_report.UndefacedInstances(released=[_NAMES[0]]),
            "not a tuple of output names",
        ),
        (
            release_report.UndefacedInstances(
                released=(_output_name(instance="sop-9"),)
            ),
            "not released",
        ),
        (
            release_report.UndefacedInstances(released=(_NAMES[0], _NAMES[0])),
            "names an instance twice",
        ),
        ({"held": 1}, "not counts of undefaced instances"),
    ],
)
def test_the_report_refuses_undefaced_instances_it_cannot_record(undefaced, match):
    with pytest.raises(ValueError, match=match):
        release_report.report_document(_report(undefaced))


def test_the_reporter_counts_the_undefaced_instances_it_released_or_held_once():
    material = {
        n: (run_qc.UndefacedMaterial(own_verdict=own),)
        for n, own in enumerate((False, True, True, False, True, False))
    }
    outcomes = (
        run.Outcome(
            0, run.Status.HELD_FOR_REVIEW, (run.RunReason.DICOMDIR,), None, None, None
        ),
        run.Outcome(1, run.Status.RELEASED, (), _NAMES[0], None, None),
        run.Outcome(
            2, run.Status.HELD_FOR_REVIEW, (run.RunReason.DICOMDIR,), None, None, None
        ),
        run.Outcome(
            3, run.Status.SEQUESTERED, (run.RunReason.DICOMDIR,), None, None, "S-0001"
        ),
        # A copy of the instance at 1, which is not released again.
        run.Outcome(4, run.Status.DUPLICATE, (), _NAMES[0], 1, None),
        run.Outcome(
            5, run.Status.HELD_FOR_REVIEW, (run.RunReason.DICOMDIR,), None, None, None
        ),
    )

    assert run_report.undefaced_instances(
        outcomes, material
    ) == release_report.UndefacedInstances(
        held=2, released=(_NAMES[0],), held_with_own_verdict=1
    )
