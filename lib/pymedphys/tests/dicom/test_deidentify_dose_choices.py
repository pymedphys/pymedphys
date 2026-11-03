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

"""A reviewer's choice for an RT Dose with too much dose in a defaced CT
series' face block to set to zero there: the QC pack's dose checks, the
attestation's dose choices and its command, the face review that gives
them to a later run, the grid set to zero beyond the fraction, and the
release report's record. Every UID and value here is invented."""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import math
import os
import stat
from pathlib import Path, PurePosixPath

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import attestation_command as command
from pymedphys._dicom.deidentify import (
    dose_defacing,
    face_blocks,
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
from pymedphys._dicom.deidentify.dose_defacing import (
    DOSE_FRACTION,
    DoseBlock,
    FrameRegion,
    RtDoseDefacer,
    dose_check_digest,
)
from pymedphys._dicom.deidentify.face_blocks import EyeCheck, SeriesDefacing
from pymedphys._dicom.deidentify.face_review import (
    DOSE_IN_FACE_BLOCK_TEXT,
    FaceReview,
    read_face_review,
)
from pymedphys._dicom.deidentify.qc_attestation import (
    Coverage,
    DoseChoiceVerdict,
    Face,
    Outcome,
)
from pymedphys._dicom.deidentify.qc_pack import (
    Disposition,
    DoseCheckEntry,
    InstanceEntry,
    QcPack,
    QcPackError,
)
from pymedphys._dicom.deidentify.reasons import DoseChoice, VisualFeaturesReason
from pymedphys._dicom.deidentify.references import InstanceRecord

from .test_deidentify_release_report import _output_name
from .test_deidentify_visual_features_option import _policy
from .test_deidentify_dose_defacing import (
    _DOSE_BLOCK,
    _dataset,
    _expected,
    _grid,
    _head_files,
    _stored,
)

REFERENCE = "A-" + "0123456789abcdef" * 2
COMPLETE = Coverage(retained_strings=True, series=True, high_risk_instances=True)
REVIEWER = "Quokka Wombatson"
_CHECK = "d0" * 32
_OTHER_CHECK = "e1" * 32
_EVERY_REVIEW = (
    "--reviewed-retained-strings",
    "--reviewed-series",
    "--reviewed-high-risk-instances",
)


def _digest(n):
    return hashlib.sha256(bytes([n])).hexdigest()


def _sha(n):
    return bytes.fromhex(_digest(n))


# The grid set to zero beyond the fraction.


def _defaced(dataset, *, beyond_fraction):
    defacer = RtDoseDefacer(_DOSE_BLOCK, dataset, beyond_fraction=beyond_fraction)
    stored = dataset.pixel_array.reshape(-1, dataset.Rows, dataset.Columns)
    masks = []
    for frame, values in enumerate(stored):
        mask = defacer.mask(frame, values)
        masks.append(np.zeros(values.shape, dtype=bool) if mask is None else mask.mask)
    return np.array(masks), defacer


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
@pytest.mark.parametrize("beyond", [False, True])
def test_a_grid_beyond_the_fraction_is_held_or_set_to_zero_as_chosen(beyond):
    in_block = round(DOSE_FRACTION * 100) + 10
    dataset = _dataset(_stored(in_block))

    masks, defacer = _defaced(dataset, beyond_fraction=beyond)

    # The region is the same either way; only whether it is held differs,
    # and the fraction is given for the reviewer either way.
    assert np.array_equal(masks, _expected(dataset))
    assert defacer.exceeded == pytest.approx(in_block / 100)
    assert defacer.held is (None if beyond else VisualFeaturesReason.DOSE_IN_FACE_BLOCK)


@pytest.mark.parametrize("in_block", [0, round(DOSE_FRACTION * 100)])
def test_a_grid_within_the_fraction_exceeds_nothing(in_block):
    _, defacer = _defaced(_dataset(_stored(in_block)), beyond_fraction=False)

    assert defacer.exceeded is None
    assert defacer.held is None


def test_a_negative_stored_value_is_held_whatever_the_choice():
    stored = _stored(90).astype(np.int32)
    stored[0, 0, 0] = -1

    _, defacer = _defaced(_dataset(stored), beyond_fraction=True)

    assert defacer.held is VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME


def test_a_dose_checks_digest_binds_the_file_and_the_block():
    digest = dose_check_digest(_sha(1), _sha(2))

    assert digest == dose_check_digest(_sha(1), _sha(2))
    assert len(digest) == 32
    assert digest not in (
        dose_check_digest(_sha(3), _sha(2)),
        dose_check_digest(_sha(1), _sha(3)),
        dose_check_digest(_sha(2), _sha(1)),
    )
    expected = hashlib.sha256(b"pymedphys-deid-dose-in-face-block/1")
    expected.update((2).to_bytes(8, "big") + _sha(1) + _sha(2))
    assert digest == expected.digest()


@pytest.mark.parametrize(
    "source, block", [(b"x" * 31, b"y" * 32), (b"x" * 32, "y" * 32), (None, b"y" * 32)]
)
def test_a_dose_checks_digest_is_of_two_sha256_digests(source, block):
    with pytest.raises(ValueError, match="two SHA-256"):
        dose_check_digest(source, block)


def test_a_dose_block_s_digest_is_a_sha256():
    with pytest.raises(ValueError, match="SHA-256"):
        DoseBlock(_DOSE_BLOCK.block, _DOSE_BLOCK.slices, block_sha256=b"x" * 31)


def test_a_choice_for_several_blocks_binds_every_block_digest():
    first = dataclasses.replace(_DOSE_BLOCK, block_sha256=_sha(1))
    second = dataclasses.replace(_DOSE_BLOCK, block_sha256=_sha(2))
    digest = FrameRegion((first, second)).block_sha256

    assert digest is not None and len(digest) == 32
    assert FrameRegion((first,)).block_sha256 == _sha(1)
    assert digest == FrameRegion((first, second)).block_sha256
    assert digest != FrameRegion((first, first)).block_sha256
    assert digest != FrameRegion((second, second)).block_sha256
    assert FrameRegion((first, _DOSE_BLOCK)).block_sha256 is None


def _records(data):
    return {
        position: InstanceRecord.from_file(each) for position, each in enumerate(data)
    }


def test_a_frame_that_an_rt_dose_names_has_its_series_and_block_digest():
    slices = _head_files()
    data = (*slices, _grid())
    records = _records(data)
    outcomes = face_blocks.find_face_blocks(records, data.__getitem__)

    (found,) = tuple(
        dose_defacing.find_dose_blocks(records, data.__getitem__, outcomes).values()
    )

    assert found.block_sha256 == face_blocks.block_digest(
        [hashlib.sha256(each).digest() for each in slices], found.blocks[0].block
    )


def test_a_series_whose_block_has_a_digest_gives_its_frame_that_one():
    slices = _head_files()
    data = (*slices, _grid())
    records = _records(data)
    outcomes = face_blocks.find_face_blocks(records, data.__getitem__)
    digest = b"\x5a" * 32
    outcomes = {
        uid: dataclasses.replace(outcome, eyes=EyeCheck.CONFIRMED, block_sha256=digest)
        for uid, outcome in outcomes.items()
    }

    (found,) = tuple(
        dose_defacing.find_dose_blocks(records, data.__getitem__, outcomes).values()
    )

    assert found.block_sha256 == digest


def test_a_frame_that_no_rt_dose_names_has_no_digest():
    slices = _head_files()
    data = (*slices, _grid())
    records = _records(data)
    # The grid's record, as though it were of a structure set, which the
    # run cleans in the same block, but for which no choice is made.
    records[len(slices)] = dataclasses.replace(
        records[len(slices)], iod="RT Structure Set"
    )
    outcomes: dict[str, SeriesDefacing] = face_blocks.find_face_blocks(
        records, data.__getitem__
    )

    (found,) = tuple(
        dose_defacing.find_dose_blocks(
            records, data.__getitem__, outcomes, ("RT Structure Set",)
        ).values()
    )

    assert found.block_sha256 is None


# The QC pack's dose checks.


def _held(position, reasons=(DOSE_IN_FACE_BLOCK_TEXT,), digest=True):
    return InstanceEntry(
        position,
        f"/imports/{position}.dcm",
        Disposition.HELD_FOR_REVIEW,
        reasons=reasons,
        source_sha256=_digest(position) if digest else None,
    )


def _released(position):
    return InstanceEntry(
        position,
        f"/imports/{position}.dcm",
        Disposition.RELEASED,
        output=PurePosixPath(f"ZQ0001/2.25.1/2.25.2/2.25.{position + 3}.dcm"),
        source_sha256=_digest(position),
    )


def _check(position, choice=None, digest=_CHECK, fraction=0.5):
    return DoseCheckEntry(position, digest, choice, fraction)


def test_a_dose_check_lists_its_rt_dose_with_its_digest_choice_and_fraction():
    checks = (_check(0), _check(1, DoseChoice.AS_WRITTEN, _OTHER_CHECK, 1.0))

    pack = QcPack(REFERENCE, (_held(0), _released(1)), dose_checks=checks)

    assert qc_pack.pack_document(pack)["dose_checks"] == [
        {"position": 0, "check_sha256": _CHECK, "choice": None, "fraction": 0.5},
        {
            "position": 1,
            "check_sha256": _OTHER_CHECK,
            "choice": "as-written",
            "fraction": 1.0,
        },
    ]
    assert repr(pack).endswith("dose_checks=2)")


@pytest.mark.parametrize(
    "fields, match",
    [
        ((-1, _CHECK, None, 0.5), "run position"),
        ((True, _CHECK, None, 0.5), "run position"),
        ((0, "D0" * 32, None, 0.5), "SHA-256"),
        ((0, "d0" * 31, None, 0.5), "SHA-256"),
        ((0, bytes(32), None, 0.5), "SHA-256"),
        ((0, _CHECK, "as-written", 0.5), "DoseChoice"),
        ((0, _CHECK, None, 0.0), "fraction"),
        ((0, _CHECK, None, 1.5), "fraction"),
        ((0, _CHECK, None, math.nan), "fraction"),
        ((0, _CHECK, None, 1), "fraction"),
    ],
)
def test_a_dose_check_entry_is_checked(fields, match):
    with pytest.raises(QcPackError, match=match):
        DoseCheckEntry(*fields)


@pytest.mark.parametrize(
    "instances, checks, match",
    [
        ((_held(0), _held(1)), (_check(1), _check(0)), "once, in order"),
        ((_held(0),), (_check(0), _check(0)), "once, in order"),
        ((_held(0),), (_check(1),), "without an instance"),
        ((_held(0, digest=False),), (_check(0),), "source's SHA-256"),
        ((_released(0),), (_check(0),), "released without a choice"),
        (
            (
                InstanceEntry(
                    0,
                    "/imports/0.dcm",
                    Disposition.SEQUESTERED,
                    label="S-0001",
                    reasons=("x",),
                    source_sha256=_digest(0),
                ),
            ),
            (_check(0, DoseChoice.AS_WRITTEN),),
            "neither released nor held",
        ),
    ],
)
def test_a_pack_s_dose_checks_are_checked(instances, checks, match):
    with pytest.raises(QcPackError, match=match):
        QcPack(REFERENCE, instances, dose_checks=checks)


def test_a_run_s_pack_lists_the_released_and_held_rt_doses_it_checked():
    material = {
        n: (run_qc.DoseCheckMaterial(_sha(n), choice, 0.123456),)
        for n, choice in enumerate(
            (None, DoseChoice.AS_WRITTEN, DoseChoice.SET_TO_ZERO, None)
        )
    }
    outcomes = (
        run.Outcome(
            0, run.Status.HELD_FOR_REVIEW, (run.RunReason.DICOMDIR,), None, None, None
        ),
        run.Outcome(1, run.Status.RELEASED, (), PurePosixPath("a/1.dcm"), None, None),
        run.Outcome(
            2, run.Status.HELD_FOR_REVIEW, (run.RunReason.DICOMDIR,), None, None, None
        ),
        run.Outcome(
            3, run.Status.SEQUESTERED, (run.RunReason.DICOMDIR,), None, None, "S-0001"
        ),
    )
    sources = [Path(f"in/{n}.dcm") for n in range(4)]
    digests = {n: _sha(n) for n in range(4)}

    pack = run_qc.qc_pack_of(sources, outcomes, material, digests=digests)

    # The sequestered one reaches no recipient, so needs no choice.
    assert pack.dose_checks == (
        DoseCheckEntry(0, _digest(0), None, 0.1235),
        DoseCheckEntry(1, _digest(1), DoseChoice.AS_WRITTEN, 0.1235),
        DoseCheckEntry(2, _digest(2), DoseChoice.SET_TO_ZERO, 0.1235),
    )


@pytest.mark.parametrize(
    "fields, match",
    [
        ((b"x" * 31, None, 0.5), "SHA-256"),
        ((b"x" * 32, "set-to-zero", 0.5), "DoseChoice"),
        ((b"x" * 32, None, 0.0), "fraction"),
        ((b"x" * 32, None, math.inf), "fraction"),
    ],
)
def test_dose_check_material_is_checked(fields, match):
    with pytest.raises(ValueError, match=match):
        run_qc.DoseCheckMaterial(*fields)


def test_dose_check_material_shows_only_its_choice():
    material = run_qc.DoseCheckMaterial(_sha(1), DoseChoice.SET_TO_ZERO, 0.5)

    assert repr(material) == "DoseCheckMaterial(choice='set-to-zero')"


# The attestation's dose choices.


@pytest.fixture(name="dose_pack")
def fixture_dose_pack(tmp_path):
    """A pack of two RT Doses held with too much dose in a face block, at 0
    and 2, and a third released on the choice to write it as received, at
    3, each in a series of its own but for 0 and 1, the first with a
    preview of its pixel data."""
    release = tmp_path / "release"
    release.mkdir()
    instances = (
        dataclasses.replace(_held(0), pixel_sha256=_digest(100)),
        _released(1),
        _held(2),
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
        previews=(
            qc_pack.Preview(
                "P-0001.png",
                qc_pack.PreviewKind.SERIES_DOSE_LEVELS,
                ((0, 0),),
                1,
                qc_previews.png(np.zeros((2, 2), np.uint8)),
            ),
        ),
        dose_checks=(
            _check(0),
            _check(2, digest=_OTHER_CHECK),
            _check(3, DoseChoice.AS_WRITTEN, "f2" * 32),
        ),
    )
    return qc_store.write_qc_pack(
        pack, tmp_path / "qc", release_directory=release
    ).parent


def _choose(directory, choices, outcome=Outcome.ATTESTED, faces=None):
    return qc_attestation.attest(
        directory,
        reviewer=REVIEWER,
        outcome=outcome,
        coverage=COMPLETE,
        faces=faces,
        dose_choices=choices,
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_reviewer_chooses_by_the_rt_dose_s_run_position(dose_pack):
    attestation = _choose(
        dose_pack, {2: DoseChoice.SET_TO_ZERO, 0: DoseChoice.AS_WRITTEN}
    )
    written = json.loads((dose_pack / qc_attestation.ATTESTATION_FILE).read_text())

    assert attestation.dose_choices == (
        DoseChoiceVerdict(0, DoseChoice.AS_WRITTEN),
        DoseChoiceVerdict(2, DoseChoice.SET_TO_ZERO),
    )
    assert written["dose_choices"] == [
        {"position": 0, "choice": "as-written"},
        {"position": 2, "choice": "set-to-zero"},
    ]
    assert qc_attestation.attested_pack(dose_pack)[0] == attestation


def test_the_pack_gives_each_dose_check_with_the_choice_its_run_applied(dose_pack):
    data = (dose_pack / qc_store.PACK_FILE).read_bytes()

    assert qc_attestation.dose_checks(data) == {
        0: qc_attestation.DoseCheck(_CHECK, None),
        2: qc_attestation.DoseCheck(_OTHER_CHECK, None),
        3: qc_attestation.DoseCheck("f2" * 32, DoseChoice.AS_WRITTEN),
    }


@pytest.mark.parametrize(
    "choices, match",
    [
        ({1: DoseChoice.AS_WRITTEN}, "dose_checks does not list"),
        ({0: "as-written"}, "DoseChoice"),
        ({"0": DoseChoice.AS_WRITTEN}, "run position"),
        ({True: DoseChoice.AS_WRITTEN}, "run position"),
        ({-1: DoseChoice.AS_WRITTEN}, "run position"),
        ([(0, DoseChoice.AS_WRITTEN)], "map"),
    ],
)
def test_a_dose_choice_needs_a_dose_check_of_the_pack(dose_pack, choices, match):
    with pytest.raises(QcPackError, match=match):
        _choose(dose_pack, choices)
    assert not (dose_pack / qc_attestation.ATTESTATION_FILE).exists()


def test_a_rejected_pack_makes_no_dose_choice(dose_pack):
    with pytest.raises(QcPackError, match="release nothing"):
        _choose(dose_pack, {0: DoseChoice.AS_WRITTEN}, Outcome.REJECTED)


@pytest.mark.parametrize(
    "choices",
    [
        (
            DoseChoiceVerdict(2, DoseChoice.AS_WRITTEN),
            DoseChoiceVerdict(0, DoseChoice.AS_WRITTEN),
        ),
        (
            DoseChoiceVerdict(0, DoseChoice.AS_WRITTEN),
            DoseChoiceVerdict(0, DoseChoice.SET_TO_ZERO),
        ),
        [DoseChoiceVerdict(0, DoseChoice.AS_WRITTEN)],
        ((0, DoseChoice.AS_WRITTEN),),
    ],
)
def test_an_attestation_s_dose_choices_are_by_position_in_order(dose_pack, choices):
    attestation = _choose(dose_pack, {})

    with pytest.raises(QcPackError, match="dose choice"):
        dataclasses.replace(attestation, dose_choices=choices)


def _rewrite(directory, change):
    path = directory / qc_attestation.ATTESTATION_FILE
    document = json.loads(path.read_text())
    change(document)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    path.write_text(json.dumps(document), "ascii")


def test_an_attestation_without_its_dose_choices_is_not_of_its_format(dose_pack):
    _choose(dose_pack, {})
    _rewrite(dose_pack, lambda document: document.pop("dose_choices"))

    with pytest.raises(QcPackError, match="not of its format"):
        qc_attestation.attested_pack(dose_pack)


def test_a_dose_choice_changed_to_another_rt_dose_is_refused(dose_pack):
    _choose(dose_pack, {0: DoseChoice.AS_WRITTEN})

    def change(document):
        document["dose_choices"] = [{"position": 1, "choice": "as-written"}]

    _rewrite(dose_pack, change)

    with pytest.raises(QcPackError, match="names no dose check"):
        read_face_review(dose_pack)


# The face review's dose choices.


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_the_face_review_gives_each_choice_by_its_dose_check_s_digest(dose_pack):
    _choose(dose_pack, {0: DoseChoice.AS_WRITTEN, 2: DoseChoice.SET_TO_ZERO})

    review = read_face_review(dose_pack)

    # The pack's run applied the choice at 3, so it is given again, and
    # none of the three was written set to zero.
    assert review.dose_choices == {
        (bytes.fromhex(_CHECK), DoseChoice.AS_WRITTEN, False),
        (bytes.fromhex(_OTHER_CHECK), DoseChoice.SET_TO_ZERO, False),
        (bytes.fromhex("f2" * 32), DoseChoice.AS_WRITTEN, False),
    }
    assert review.dose_choice(bytes.fromhex(_CHECK)) == (DoseChoice.AS_WRITTEN, False)
    assert review.dose_choice(bytes(32)) is None
    assert "dose_choices=3" in repr(review)


def test_an_attestation_s_choice_replaces_the_one_its_pack_applied(dose_pack):
    _choose(dose_pack, {3: DoseChoice.SET_TO_ZERO})

    review = read_face_review(dose_pack)

    assert review.dose_choice(bytes.fromhex("f2" * 32)) == (
        DoseChoice.SET_TO_ZERO,
        False,
    )
    # Without a choice, a held RT Dose has none.
    assert review.dose_choice(bytes.fromhex(_CHECK)) is None


def test_a_choice_that_the_pack_s_run_set_to_zero_is_given_as_seen_so(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    pack = QcPack(
        REFERENCE,
        (_held(0, reasons=("set to zero on review",)),),
        dose_checks=(_check(0, DoseChoice.SET_TO_ZERO),),
    )
    directory = qc_store.write_qc_pack(
        pack, tmp_path / "qc", release_directory=release
    ).parent
    _choose(directory, {})

    assert read_face_review(directory).dose_choices == {
        (bytes.fromhex(_CHECK), DoseChoice.SET_TO_ZERO, True)
    }


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
@pytest.mark.parametrize(
    "choice, covered",
    [(None, False), (DoseChoice.AS_WRITTEN, True), (DoseChoice.SET_TO_ZERO, False)],
)
def test_a_verdict_of_absent_covers_a_held_rt_dose_only_chosen_as_written(
    dose_pack, choice, covered
):
    _choose(
        dose_pack,
        {} if choice is None else {0: choice},
        faces={0: Face.ABSENT},
    )

    review = read_face_review(dose_pack)

    # Only the choice makes the verdict one on the grid as received, from
    # its own dose levels, which its pack drew.
    assert (_sha(0) in review.absent) is covered
    assert ((_sha(0), _sha(100)) in review.absent_pixels) is covered
    assert ((_sha(0), _sha(100), 1) in (review.absent_dose_frames or ())) is covered
    assert _sha(1) in review.absent
    hold = review.hold_reason(_sha(0), _sha(100), None, 1, dose=True)
    assert (hold is None or hold is VisualFeaturesReason.OTHER_CONTOURS) is covered


def test_two_dose_checks_of_one_digest_give_no_review(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    pack = QcPack(
        REFERENCE,
        (_held(0), _held(1)),
        dose_checks=(_check(0), _check(1)),
    )
    directory = qc_store.write_qc_pack(
        pack, tmp_path / "qc", release_directory=release
    ).parent
    _choose(directory, {0: DoseChoice.AS_WRITTEN})

    with pytest.raises(QcPackError, match="share a digest"):
        read_face_review(directory)


@pytest.mark.parametrize(
    "choices",
    [
        frozenset({(b"x" * 31, DoseChoice.AS_WRITTEN, False)}),
        frozenset({(b"x" * 32, "as-written", False)}),
        frozenset({(b"x" * 32, DoseChoice.AS_WRITTEN, 0)}),
        frozenset({(b"x" * 32, DoseChoice.AS_WRITTEN)}),
        frozenset(
            {
                (b"x" * 32, DoseChoice.AS_WRITTEN, False),
                (b"x" * 32, DoseChoice.SET_TO_ZERO, False),
            }
        ),
        {(b"x" * 32, DoseChoice.AS_WRITTEN, False)},
    ],
)
def test_a_face_review_s_dose_choices_are_checked(choices):
    with pytest.raises(QcPackError, match="dose choices"):
        FaceReview(REFERENCE, frozenset(), frozenset(), dose_choices=choices)


# The command's dose choices.


def _command(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    status = command.main(list(argv), stdout=stdout, stderr=stderr)
    return status, stdout.getvalue(), stderr.getvalue()


def test_the_command_records_each_dose_choice(dose_pack):
    status, stdout, stderr = _command(
        str(dose_pack),
        "--reviewer",
        REVIEWER,
        "--outcome",
        "attested",
        *_EVERY_REVIEW,
        "--dose-as-written",
        "0",
        "--dose-set-to-zero",
        "2",
    )

    assert status == command.EXIT_RECORDED, stderr
    written = json.loads((dose_pack / qc_attestation.ATTESTATION_FILE).read_text())
    assert written["dose_choices"] == [
        {"position": 0, "choice": "as-written"},
        {"position": 2, "choice": "set-to-zero"},
    ]
    lines = stdout.splitlines()
    assert "  RT Doses with dose in a face block to write as received: 1" in lines
    assert "  RT Doses with dose in a face block to set to zero: 1" in lines
    assert REVIEWER not in stdout + stderr


@pytest.mark.parametrize(
    "choices, message",
    [
        (("--dose-as-written", "0", "--dose-set-to-zero", "0"), "both dose choices"),
        (("--dose-set-to-zero", "1"), "dose_checks does not list"),
    ],
)
def test_the_command_refuses_a_dose_choice_it_cannot_record(
    dose_pack, choices, message
):
    status, stdout, stderr = _command(
        str(dose_pack),
        "--reviewer",
        REVIEWER,
        "--outcome",
        "attested",
        *_EVERY_REVIEW,
        *choices,
    )

    assert status == command.EXIT_NOT_RECORDED
    assert message in stderr and "nothing was recorded" in stderr
    assert not stdout
    assert not (dose_pack / qc_attestation.ATTESTATION_FILE).exists()


# The release report's record.


_NAMES = tuple(_output_name(instance=f"sop-{n}") for n in range(3))


def _report(doses, released=_NAMES):
    return release_report.release_report(
        _policy(),
        vocabulary=None,
        reviewed_roi_names=None,
        face_review=REFERENCE,
        doses_in_face_block=doses,
        released=released,
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_the_report_records_each_rt_dose_by_what_the_run_did_with_it():
    doses = release_report.DosesInFaceBlock(
        held=2,
        released_as_written=(_NAMES[1],),
        held_as_written=1,
        released_set_to_zero=(_NAMES[2], _NAMES[0]),
        held_set_to_zero=3,
    )

    report = _report(doses)
    document = release_report.report_document(report)

    assert document["face_review"]["rt_doses_in_face_block"] == {
        "held": 2,
        "released_as_written": [str(_NAMES[1])],
        "held_as_written": 1,
        "released_set_to_zero": [str(_NAMES[0]), str(_NAMES[2])],
        "held_set_to_zero": 3,
    }
    text = release_report_markdown.to_markdown(release_report.to_json(report))
    assert "held without a choice: `2`" in text
    assert "held, written as received on a reviewer's choice: `1`" in text
    assert "held, set to zero on a reviewer's choice: `3`" in text
    assert f"| `{_NAMES[1]}` | written as received |" in text
    assert f"| `{_NAMES[2]}` | set to zero in the face block |" in text


def test_the_report_without_a_face_review_records_no_rt_doses():
    report = release_report.release_report(
        _policy(), vocabulary=None, reviewed_roi_names=None
    )

    assert report.doses_in_face_block is None
    assert release_report.report_document(report)["face_review"] is None
    with pytest.raises(ValueError, match="RT Doses without a face review"):
        release_report.report_document(
            dataclasses.replace(
                report, doses_in_face_block=release_report.DosesInFaceBlock()
            )
        )


@pytest.mark.parametrize(
    "doses, match",
    [
        (release_report.DosesInFaceBlock(held=-1), "held is negative"),
        (release_report.DosesInFaceBlock(held=1.0), "held is not a whole"),
        (
            release_report.DosesInFaceBlock(held_set_to_zero=True),
            "held_set_to_zero is not a whole",
        ),
        (
            release_report.DosesInFaceBlock(
                released_as_written=(PurePosixPath("elsewhere/x.dcm"),)
            ),
            "not a tuple of output names",
        ),
        (
            release_report.DosesInFaceBlock(released_as_written=[_NAMES[0]]),
            "not a tuple of output names",
        ),
        (
            release_report.DosesInFaceBlock(
                released_set_to_zero=(_output_name(instance="sop-9"),)
            ),
            "not released",
        ),
        (
            release_report.DosesInFaceBlock(
                released_as_written=(_NAMES[0],), released_set_to_zero=(_NAMES[0],)
            ),
            "names an instance twice",
        ),
        ({"held": 1}, "not counts of RT Doses"),
    ],
)
def test_the_report_refuses_rt_doses_it_cannot_record(doses, match):
    with pytest.raises(ValueError, match=match):
        release_report.report_document(_report(doses))


def test_the_reporter_counts_the_rt_doses_it_released_or_held_once():
    material = {
        n: (run_qc.DoseCheckMaterial(_sha(n), choice, 0.5),)
        for n, choice in enumerate(
            (
                None,
                DoseChoice.AS_WRITTEN,
                DoseChoice.AS_WRITTEN,
                DoseChoice.SET_TO_ZERO,
                DoseChoice.SET_TO_ZERO,
                None,
                DoseChoice.AS_WRITTEN,
            )
        )
    }
    outcomes = (
        run.Outcome(
            0, run.Status.HELD_FOR_REVIEW, (run.RunReason.DICOMDIR,), None, None, None
        ),
        run.Outcome(1, run.Status.RELEASED, (), _NAMES[0], None, None),
        run.Outcome(
            2, run.Status.HELD_FOR_REVIEW, (run.RunReason.DICOMDIR,), None, None, None
        ),
        run.Outcome(3, run.Status.RELEASED, (), _NAMES[1], None, None),
        run.Outcome(
            4, run.Status.HELD_FOR_REVIEW, (run.RunReason.DICOMDIR,), None, None, None
        ),
        run.Outcome(
            5, run.Status.SEQUESTERED, (run.RunReason.DICOMDIR,), None, None, "S-0001"
        ),
        # A copy of the instance at 1, which is not released again.
        run.Outcome(6, run.Status.DUPLICATE, (), _NAMES[0], 1, None),
    )

    assert run_report.doses_in_face_block(
        outcomes, material
    ) == release_report.DosesInFaceBlock(
        held=1,
        released_as_written=(_NAMES[0],),
        held_as_written=1,
        released_set_to_zero=(_NAMES[1],),
        held_set_to_zero=1,
    )
