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

"""The Clean Pixel Data Option, claimed from a reviewer's redaction verdicts.

Every name, path, and data set here is invented or synthetic, and every
finder is a stand-in that gives fixed regions, so no model is downloaded and
no network is reached.
"""

# The tests share one first run, its verdicts, and its second run, so they
# stay in one module.
# pylint: disable = too-many-lines

import contextlib
import dataclasses
import datetime
import hashlib
import io
import json
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    attestation_command,
    conformance,
    conformance_markdown,
    markers,
    qc_attestation,
    qc_pack,
    redaction_review,
    release_report,
    release_report_markdown,
    run,
)
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.method_digest import method_digest
from pymedphys._dicom.deidentify.pixel_cleaning import (
    PixelDataRefused,
    black_out_reviewed,
)
from pymedphys._dicom.deidentify.policy import (
    CLEAN_PIXEL_DATA,
    PolicyError,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.qc_attestation import (
    CleanedShape,
    Coverage,
    Outcome,
    Redaction,
    RedactionVerdict,
)
from pymedphys._dicom.deidentify.qc_pack import QcPackError
from pymedphys._dicom.deidentify.reasons import (
    HeldPixelData,
    PixelDataReason,
    TransformReason,
)
from pymedphys._dicom.deidentify.redaction_review import (
    RedactionReview,
    read_redaction_review,
)
from pymedphys._dicom.deidentify.scope import SUPPORTED_IODS
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _synthetic_references as synthetic
from .test_deidentify_pixel_cleaning import (
    BOX,
    KEY,
    Finder,
    _ct,
    _frame,
    _inside,
    _pixels,
    _replaced,
    _source,
)

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

REFERENCE = "A-" + "fedcba9876543210" * 2
CODE = "113101"
COMPLETE = Coverage(retained_strings=True, series=True, high_risk_instances=True)
WHEN = datetime.datetime(2026, 10, 17, 14, 0, tzinfo=datetime.timezone.utc)
# A region of the reviewer's own, in place of the finder's BOX.
REVISED = TextBox(0, 0, 2, 2)
DIGEST = bytes(range(32))


def _policy():
    return compose_custom_policy([CLEAN_PIXEL_DATA])


def _attest(directory, redactions=()):
    return qc_attestation.attest(
        directory,
        reviewer="Quokka Wombatson",
        outcome=Outcome.ATTESTED,
        coverage=COMPLETE,
        attested_at=WHEN,
        redactions=redactions,
    )


def _codes(dataset):
    return [item.CodeValue for item in dataset.DeidentificationMethodCodeSequence]


# The synthetic files of a first run under the option, by file name: three
# CT slices and two more, each with its own stored values, and two instances
# without pixel data.
_ACCEPTED, _REVISED, _REJECTED, _UNJUDGED = (
    "0-accepted.dcm",
    "1-revised.dcm",
    "2-rejected.dcm",
    "3-unjudged.dcm",
)
_PLAN, _STRUCTURE_SET = "4-plan.dcm", "5-structure-set.dcm"
# An image whose added region goes past its eight columns.
_PAST = "6-past.dcm"
_IMAGES = (_ACCEPTED, _REVISED, _REJECTED, _UNJUDGED, _PAST)


def _image(number):
    """A CT slice with its own SOP Instance UID and stored values."""
    dataset = _ct(_frame(start=100 * (number + 1)))
    dataset.SOPInstanceUID = (
        synthetic.CT_SLICES[number] if number < 3 else f"2.25.20{number + 1}"
    )
    dataset.InstanceNumber = number + 1
    return dataset


def _files():
    return {
        **{name: synthetic.written(_image(n)) for n, name in enumerate(_IMAGES)},
        _PLAN: synthetic.written(synthetic.rt_plan()),
        _STRUCTURE_SET: synthetic.written(synthetic.structure_set()),
    }


def _write(directory, files):
    directory.mkdir()
    for name, data in files.items():
        (directory / name).write_bytes(data)


def _run(directory, source, transform):
    directory.mkdir()
    return run.run(
        run.discover(source),
        directory / "release",
        transform,
        ReleaseGate(),
        qc_destination=directory / "qc",
        reporter=transform.reporter,
    )


@pytest.fixture(name="first_run")
def fixture_first_run(tmp_path):
    """The QC pack of a first run under the option, with its run positions by
    file name."""
    source = tmp_path / "source"
    _write(source, _files())
    transform = InstanceTransform(
        _policy(), KEY, finder=Finder(), unvalidated_policy=True
    )
    result = _run(tmp_path / "first", source, transform)
    document = json.loads(result.qc_pack.read_text("utf-8"))
    positions = {
        Path(entry["source"]).name: entry["position"] for entry in document["instances"]
    }
    return result.qc_pack.parent, positions


def _verdicts(positions):
    return (
        RedactionVerdict(positions[_ACCEPTED], Redaction.ACCEPTED),
        RedactionVerdict(positions[_REVISED], Redaction.REVISED, ((0, (REVISED,)),)),
        RedactionVerdict(positions[_REJECTED], Redaction.REJECTED),
    )


def _sha(data):
    return hashlib.sha256(data).digest()


# The verdicts and the attestation.


@pytest.mark.parametrize(
    "fields",
    [
        {"position": -1, "redaction": Redaction.ACCEPTED},
        {"position": True, "redaction": Redaction.ACCEPTED},
        {"position": "0", "redaction": Redaction.ACCEPTED},
        {"position": 0, "redaction": "accepted"},
        {"position": 0, "redaction": Redaction.ACCEPTED, "regions": ((0, (BOX,)),)},
        {"position": 0, "redaction": Redaction.REJECTED, "regions": ((0, (BOX,)),)},
        {"position": 0, "redaction": Redaction.REVISED},
        {"position": 0, "redaction": Redaction.REVISED, "regions": [(0, (BOX,))]},
        {"position": 0, "redaction": Redaction.REVISED, "regions": ((0, ()),)},
        {"position": 0, "redaction": Redaction.REVISED, "regions": ((-1, (BOX,)),)},
        {"position": 0, "redaction": Redaction.REVISED, "regions": ((0, (BOX, BOX)),)},
        {
            "position": 0,
            "redaction": Redaction.REVISED,
            "regions": ((0, (BOX, REVISED)),),
        },
        {
            "position": 0,
            "redaction": Redaction.REVISED,
            "regions": ((1, (BOX,)), (0, (BOX,))),
        },
        {
            "position": 0,
            "redaction": Redaction.REVISED,
            "regions": ((0, ((1, 2, 3, 5),)),),
        },
    ],
)
def test_a_redaction_verdict_is_checked(fields):
    with pytest.raises(QcPackError):
        RedactionVerdict(**fields)


def test_an_attestation_with_redaction_verdicts_is_read_back_as_written(first_run):
    pack, positions = first_run
    attestation = _attest(pack, reversed(_verdicts(positions)))

    # In run position order, whatever the order given.
    assert attestation.redactions == tuple(
        sorted(_verdicts(positions), key=lambda verdict: verdict.position)
    )
    assert qc_attestation.attested_pack(pack)[0] == attestation
    written = json.loads((pack / qc_attestation.ATTESTATION_FILE).read_text("ascii"))
    assert written["format"] == "pymedphys-deid-qc-attestation/3"
    assert {
        "position": positions[_REVISED],
        "redaction": "revised",
        "regions": [{"frame": 0, "boxes": [[0, 0, 2, 2]]}],
    } in written["redactions"]


def test_an_attestation_of_the_earlier_format_is_refused(first_run):
    pack, positions = first_run
    _attest(pack, _verdicts(positions))
    path = pack / qc_attestation.ATTESTATION_FILE
    document = json.loads(path.read_text("ascii"))
    document["format"] = "pymedphys-deid-qc-attestation/2"
    del document["redactions"]
    path.chmod(0o600)
    path.write_text(json.dumps(document), "ascii")

    with pytest.raises(QcPackError, match="not of its format"):
        read_redaction_review(pack)


@pytest.mark.parametrize("name", [_PLAN, _STRUCTURE_SET])
def test_attesting_refuses_a_verdict_on_an_instance_that_was_not_cleaned(
    first_run, name
):
    pack, positions = first_run

    with pytest.raises(QcPackError, match="does not list as cleaned"):
        _attest(pack, [RedactionVerdict(positions[name], Redaction.ACCEPTED)])
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


def test_attesting_refuses_a_region_in_a_frame_that_the_instance_does_not_hold(
    first_run,
):
    pack, positions = first_run
    verdict = RedactionVerdict(
        positions[_REVISED], Redaction.REVISED, ((1, (REVISED,)),)
    )

    with pytest.raises(QcPackError, match="a frame that its Pixel Data do not hold"):
        _attest(pack, [verdict])


@pytest.mark.parametrize(
    "box",
    # The images are of 6 Rows and 8 Columns.
    [TextBox(4, 0, 7, 2), TextBox(0, 6, 2, 9)],
)
def test_attesting_refuses_a_region_past_the_rows_or_columns_of_its_frame(
    first_run, box
):
    pack, positions = first_run
    verdict = RedactionVerdict(positions[_REVISED], Redaction.REVISED, ((0, (box,)),))

    with pytest.raises(QcPackError, match="a region past its 6 Rows or 8 Columns"):
        _attest(pack, [verdict])
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


def test_attesting_accepts_a_region_that_reaches_the_edge_of_its_frame(first_run):
    pack, positions = first_run
    edge = TextBox(4, 6, 6, 8)
    verdict = RedactionVerdict(positions[_REVISED], Redaction.REVISED, ((0, (edge,)),))

    assert _attest(pack, [verdict]).redactions == (verdict,)


# Reading the verdicts.


def test_a_review_gives_each_verdicts_regions_by_source_digest(first_run):
    pack, positions = first_run
    attestation = _attest(pack, _verdicts(positions))
    files = _files()

    review = read_redaction_review(pack)

    assert review.reference == attestation.reference
    assert dict(review.approved) == {
        # The pack's regions, which the finder found.
        _sha(files[_ACCEPTED]): ((0, (BOX,)),),
        # The pack's, with the reviewer's own added.
        _sha(files[_REVISED]): ((0, (REVISED, BOX)),),
    }
    assert review.rejected == frozenset({_sha(files[_REJECTED])})


def test_a_revised_verdict_adds_to_the_packs_regions_in_any_frame():
    regions = ((0, (BOX,)), (2, (REVISED,)))

    # pylint: disable-next = protected-access
    added = redaction_review._added(regions, ((0, (REVISED, BOX)), (1, (BOX,))))

    assert added == ((0, (REVISED, BOX)), (1, (BOX,)), (2, (REVISED,)))


def test_a_pack_that_is_not_attested_gives_no_review(first_run):
    pack, _ = first_run

    with pytest.raises(QcPackError):
        read_redaction_review(pack)


def test_a_rejected_attestation_gives_no_review(first_run):
    pack, positions = first_run
    _attest(pack, _verdicts(positions))
    # Attesting refuses verdicts with a rejection, so the file is changed by
    # hand, as it might be outside the command.
    path = pack / qc_attestation.ATTESTATION_FILE
    document = json.loads(path.read_text("ascii"))
    path.chmod(0o600)
    path.write_text(json.dumps({**document, "outcome": "rejected"}), encoding="ascii")

    with pytest.raises(QcPackError, match="verdicts release nothing"):
        read_redaction_review(pack)


def test_attesting_refuses_a_verdict_with_an_outcome_of_rejected(first_run):
    pack, positions = first_run

    with pytest.raises(QcPackError, match="would release nothing"):
        qc_attestation.attest(
            pack,
            reviewer="Quokka Wombatson",
            outcome=Outcome.REJECTED,
            coverage=COMPLETE,
            attested_at=WHEN,
            redactions=_verdicts(positions)[:1],
        )
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


def test_each_frame_of_each_cleaned_instance_names_its_preview(first_run):
    pack, positions = first_run
    document = json.loads((pack / "qc-pack.json").read_text("utf-8"))
    shown = {
        (frame["position"], frame["frame"]): preview["file"]
        for preview in document["previews"]
        if preview["kind"] == "redaction"
        for frame in preview["frames"]
    }

    previews = qc_attestation.redaction_previews(pack)

    assert previews == shown
    assert {position for position, _ in previews} == {
        positions[name] for name in _IMAGES
    }


def _pack_with_previews(monkeypatch, previews):
    """Have the attestation read a pack that lists ``previews``."""
    document = {"format": qc_pack.FORMAT, "reference": REFERENCE, "previews": previews}
    monkeypatch.setattr(
        qc_attestation,
        "_pack_bytes",
        lambda directory: json.dumps(document).encode("ascii"),
    )


def _preview(number, kind, *frames):
    return {
        "file": f"previews/P-{number:04d}.png",
        "kind": kind,
        "frames": [
            {"position": position, "frame": frame} for position, frame in frames
        ],
    }


def test_each_frame_of_a_multi_frame_instance_names_its_own_preview(monkeypatch):
    _pack_with_previews(
        monkeypatch,
        [
            _preview(1, "instance", (0, 0)),
            _preview(2, "redaction", (0, 0)),
            _preview(3, "redaction", (4, 0)),
            _preview(4, "redaction", (4, 1)),
            _preview(5, "redaction", (4, 2)),
        ],
    )

    assert qc_attestation.redaction_previews("pack") == {
        (0, 0): "previews/P-0002.png",
        (4, 0): "previews/P-0003.png",
        (4, 1): "previews/P-0004.png",
        (4, 2): "previews/P-0005.png",
    }


@pytest.mark.parametrize(
    "previews",
    [
        None,
        ["previews/P-0001.png"],
        [{"file": None, "kind": "redaction", "frames": []}],
        [{"file": "previews/P-0001.png", "kind": "redaction", "frames": [[0, 0]]}],
        [_preview(1, "redaction", (0, "0"))],
    ],
)
def test_previews_not_of_the_packs_format_are_refused(monkeypatch, previews):
    _pack_with_previews(monkeypatch, previews)

    with pytest.raises(QcPackError, match="not of its format"):
        qc_attestation.redaction_previews("pack")


def _with_pack(monkeypatch, attestation, instances, redactions, unshown=()):
    """Have the review read ``attestation`` with a pack of the entries given."""
    data = json.dumps(
        {
            "instances": instances,
            "redactions": redactions,
            "not_previewed": [
                {"position": position, "reason": "source-not-shown"}
                for position in unshown
            ],
        }
    ).encode()
    monkeypatch.setattr(
        redaction_review, "attested_pack", lambda _: (attestation, data)
    )


def _entry(position, digest=DIGEST):
    return {"position": position, "source_sha256": digest.hex()}


def _cleaned(position):
    return {
        "position": position,
        "frames": 1,
        "rows": 6,
        "columns": 8,
        "regions": [],
        "decoded_sha256": None,
    }


def test_verdicts_that_disagree_on_one_source_file_are_refused(first_run, monkeypatch):
    pack, _ = first_run
    attestation = dataclasses.replace(
        _attest(pack),
        redactions=(
            RedactionVerdict(0, Redaction.ACCEPTED),
            RedactionVerdict(1, Redaction.REJECTED),
        ),
    )
    # Two identical copies of one source file, given different verdicts.
    _with_pack(
        monkeypatch, attestation, [_entry(0), _entry(1)], [_cleaned(0), _cleaned(1)]
    )

    with pytest.raises(QcPackError, match="disagree"):
        read_redaction_review(pack)


def test_verdicts_that_agree_on_one_source_file_are_read_once(first_run, monkeypatch):
    pack, _ = first_run
    attestation = dataclasses.replace(
        _attest(pack),
        redactions=(
            RedactionVerdict(0, Redaction.REJECTED),
            RedactionVerdict(1, Redaction.REJECTED),
        ),
    )
    _with_pack(
        monkeypatch, attestation, [_entry(0), _entry(1)], [_cleaned(0), _cleaned(1)]
    )

    assert read_redaction_review(pack).rejected == frozenset({DIGEST})


def test_the_decoded_frames_of_an_approved_compressed_source_are_read(
    first_run, monkeypatch
):
    pack, _ = first_run
    decoded = bytes(range(32, 64))
    attestation = dataclasses.replace(
        _attest(pack),
        redactions=(
            RedactionVerdict(0, Redaction.ACCEPTED),
            RedactionVerdict(1, Redaction.REJECTED),
        ),
    )
    other = bytes(range(1, 33))
    _with_pack(
        monkeypatch,
        attestation,
        [_entry(0), _entry(1, other)],
        [
            {**_cleaned(0), "decoded_sha256": decoded.hex()},
            {**_cleaned(1), "decoded_sha256": bytes(32).hex()},
        ],
    )

    review = read_redaction_review(pack)

    assert dict(review.decoded) == {DIGEST: decoded}
    assert review.rejected == frozenset({other})


@pytest.mark.parametrize("decoded", ["0" * 63, "F" * 64, 64, "absent"])
def test_a_decoded_digest_that_is_not_one_is_refused(first_run, monkeypatch, decoded):
    pack, _ = first_run
    attestation = dataclasses.replace(
        _attest(pack), redactions=(RedactionVerdict(0, Redaction.ACCEPTED),)
    )
    cleaned = _cleaned(0)
    if decoded == "absent":
        del cleaned["decoded_sha256"]
    else:
        cleaned["decoded_sha256"] = decoded
    _with_pack(monkeypatch, attestation, [_entry(0)], [cleaned])

    with pytest.raises(QcPackError, match="not of its format"):
        read_redaction_review(pack)


def test_copies_whose_frames_decoded_otherwise_are_refused(first_run, monkeypatch):
    pack, _ = first_run
    attestation = dataclasses.replace(
        _attest(pack),
        redactions=(
            RedactionVerdict(0, Redaction.ACCEPTED),
            RedactionVerdict(1, Redaction.ACCEPTED),
        ),
    )
    _with_pack(
        monkeypatch,
        attestation,
        [_entry(0), _entry(1)],
        [
            {**_cleaned(0), "decoded_sha256": bytes(32).hex()},
            {**_cleaned(1), "decoded_sha256": bytes(range(32)).hex()},
        ],
    )

    with pytest.raises(QcPackError, match="disagree"):
        read_redaction_review(pack)


@pytest.mark.parametrize(
    "instances, redactions, unshown",
    [
        # The instance is not listed as cleaned.
        ([_entry(0)], [], ()),
        # Or is listed without its source's digest.
        ([{"position": 0}], [_cleaned(0)], ()),
        # Or was not previewed, so the reviewer cannot have seen its frames.
        ([_entry(0)], [_cleaned(0)], (0,)),
    ],
)
def test_a_verdict_on_an_instance_without_a_cleaned_previewed_source_is_refused(
    first_run, monkeypatch, instances, redactions, unshown
):
    pack, _ = first_run
    attestation = dataclasses.replace(
        _attest(pack), redactions=(RedactionVerdict(0, Redaction.ACCEPTED),)
    )
    _with_pack(monkeypatch, attestation, instances, redactions, unshown)

    with pytest.raises(QcPackError, match="does not list as cleaned and previewed"):
        read_redaction_review(pack)


def test_only_a_previewed_cleaned_instance_can_be_given_a_verdict():
    data = json.dumps(
        {
            "redactions": [
                _cleaned(0),
                _cleaned(1),
                {**_cleaned(2), "frames": 3},
                _cleaned(3),
            ],
            "not_previewed": [
                {"position": 1, "reason": "source-not-shown"},
                # An RT Dose whose dose levels are not drawn still has its
                # redaction previews.
                {"position": 3, "reason": "dose-levels-not-shown"},
            ],
        }
    ).encode()

    assert qc_attestation.previewed_redactions(data) == {
        0: CleanedShape(1, 6, 8),
        2: CleanedShape(3, 6, 8),
        3: CleanedShape(1, 6, 8),
    }


def test_attesting_refuses_a_verdict_on_an_instance_that_was_not_previewed(
    first_run, monkeypatch
):
    pack, positions = first_run
    previewed = qc_attestation.previewed_redactions
    # As though the pack had listed the accepted image as not previewed.
    monkeypatch.setattr(
        qc_attestation,
        "previewed_redactions",
        lambda data: {
            position: shape
            for position, shape in previewed(data).items()
            if position != positions[_ACCEPTED]
        },
    )

    with pytest.raises(QcPackError, match="does not list as cleaned and previewed"):
        _attest(pack, [RedactionVerdict(positions[_ACCEPTED], Redaction.ACCEPTED)])
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


@pytest.mark.parametrize(
    "fields",
    [
        {"reference": "A-0123"},
        {"approved": {b"short": ()}},
        {"rejected": {DIGEST}},
        {"approved": {DIGEST: ((0, ()),)}},
        {"approved": {DIGEST: ((1, (BOX,)), (0, (BOX,)))}},
        {"approved": {DIGEST: ((0, ((1, 2, 3, 5),)),)}},
        {"approved": {DIGEST: ()}, "rejected": frozenset({DIGEST})},
    ],
)
def test_a_redaction_review_is_checked(fields):
    with pytest.raises(QcPackError):
        RedactionReview(
            **{
                "reference": REFERENCE,
                "approved": {},
                "rejected": frozenset(),
                **fields,
            }
        )


def test_a_review_cannot_change_and_its_repr_shows_only_the_reference_and_counts():
    review = RedactionReview(
        REFERENCE, {DIGEST: ((0, (BOX,)),)}, frozenset({bytes(32)})
    )

    with pytest.raises(TypeError):
        review.approved[bytes(32)] = ()  # type: ignore[index]
    assert repr(review) == (
        f"RedactionReview(reference={REFERENCE!r}, approved=1, rejected=1)"
    )


# The reviewed regions.


def test_reviewed_regions_are_blacked_out_alone():
    frames = np.stack([_frame(), _frame(start=900)])
    source = _source(_ct(frames))

    redaction = black_out_reviewed(source, source.dataset(), [(1, (BOX,))])

    assert [(r.frame, r.boxes) for r in redaction.regions] == [(1, (BOX,))]
    pixels = _pixels(_replaced(source, redaction))
    inside = _inside(frames.shape[1:])
    # A frame without a region is left as it is.
    assert np.array_equal(pixels[0], frames[0])
    assert np.all(pixels[1][inside] == frames[1].min())
    assert np.array_equal(pixels[1][~inside], frames[1][~inside])


@pytest.mark.parametrize(
    "regions",
    [
        # A frame that the Pixel Data do not hold.
        [(1, (BOX,))],
        # A region past the frame's six rows or eight columns, which is never
        # clipped, since a mistyped region would then miss its text.
        [(0, (TextBox(0, 0, 2, 9),))],
        [(0, (TextBox(5, 0, 7, 2),))],
        [(0, (TextBox(6, 0, 7, 2),))],
    ],
)
def test_a_reviewed_region_that_does_not_fit_the_pixel_data_is_refused(regions):
    source = _source(_ct(_frame()))

    with pytest.raises(PixelDataRefused) as raised:
        black_out_reviewed(source, source.dataset(), regions)
    assert raised.value.reason is TransformReason.REDACTION_MISMATCH


def test_a_redaction_review_is_given_only_with_the_option():
    review = RedactionReview(REFERENCE, {}, frozenset())

    with pytest.raises(PolicyError, match="a redaction review is given only"):
        InstanceTransform(
            compose_policy("basic"),
            KEY,
            redaction_review=review,
            unvalidated_policy=True,
        )


# The markers, the conformance statement, and the release report.


@pytest.mark.deid_requirement("PS3.15-E.3.1-02")
def test_the_markers_set_burned_in_annotation_to_no_with_the_code():
    policy = _policy()
    digest = method_digest(policy, vocabulary=None, reviewed_roi_names=None)
    found = markers.markers_for(policy, digest, satisfied=[CLEAN_PIXEL_DATA])
    unsatisfied = markers.markers_for(policy, digest, satisfied=[])
    dataset = pydicom.Dataset()
    dataset.BurnedInAnnotation = "YES"

    assert found.burned_in_annotation == "NO"
    assert [c.code_value for c in found.method_codes] == [markers.PROFILE_CODE, CODE]
    assert unsatisfied.burned_in_annotation is None
    # Added whether or not the IOD defines it, as in an empty data set.
    assert markers.apply_markers(pydicom.Dataset(), found).BurnedInAnnotation == "NO"
    assert "BurnedInAnnotation" not in markers.apply_markers(
        pydicom.Dataset(), unsatisfied
    )
    assert markers.apply_markers(dataset, unsatisfied).BurnedInAnnotation == "YES"
    assert markers.apply_markers(dataset, found).BurnedInAnnotation == "NO"
    assert dataset.BurnedInAnnotation == "YES"
    with pytest.raises(ValueError, match=r"\(0028,0301\) is not NO"):
        markers.apply_markers(
            dataset, dataclasses.replace(found, burned_in_annotation="YES")
        )


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_statement_gives_the_code_only_after_review():
    statement = conformance.conformance_statement(_policy(), vocabulary=None)

    assert statement.markers.codes == (markers.PROFILE_CODE,)
    assert statement.markers.review_codes == (CODE,)
    text = " ".join(conformance_markdown.render_markdown(statement).split())
    assert "Clean Pixel Data Option (DCM 113101) only in an instance that" in text
    assert (
        "also has Burned In Annotation (0028,0301) set to NO, as PS3.15 E.3.1 "
        "requires, including in an IOD that does not define the attribute, which "
        "of the supported IODs are RT Plan, RT Structure Set, and MR Spectroscopy"
    ) in text
    assert (
        "claims Clean Pixel Data only for an instance without top-level pixel "
        "data or whose regions a reviewer approved"
    ) in text


def test_the_statement_names_each_supported_iod_that_lacks_the_attribute():
    tables = load_iod_tables()
    lacking = {
        name for name in SUPPORTED_IODS if not tables.iods[name].lookup("(0028,0301)")
    }

    assert lacking == {"RT Plan", "RT Structure Set", "MR Spectroscopy"}


def test_the_report_names_the_reviewed_pack_by_its_reference():
    report = release_report.release_report(
        _policy(), vocabulary=None, reviewed_roi_names=None, redaction_review=REFERENCE
    )
    document = release_report.report_document(report)

    assert document["redaction_review"] == {"reference": REFERENCE}
    text = release_report_markdown.to_markdown(release_report.to_json(report))
    assert "## Redaction review" in text
    assert f"`{REFERENCE}`" in text


def test_a_report_without_a_redaction_review_has_none():
    report = release_report.release_report(
        _policy(), vocabulary=None, reviewed_roi_names=None
    )

    assert release_report.report_document(report)["redaction_review"] is None
    text = release_report_markdown.to_markdown(release_report.to_json(report))
    assert "## Redaction review" not in text


@pytest.mark.parametrize("reference", ["A-0123", "S-0001", 7])
def test_the_report_refuses_a_redaction_review_that_is_not_a_reference(reference):
    report = release_report.release_report(
        _policy(), vocabulary=None, reviewed_roi_names=None, redaction_review=reference
    )
    with pytest.raises(ValueError):
        release_report.report_document(report)


# The attestation command.


def _command(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    status = attestation_command.main(list(argv), stdout=stdout, stderr=stderr)
    return status, stdout.getvalue(), stderr.getvalue()


_EVERY_REVIEW = (
    "--reviewer",
    "Quokka Wombatson",
    "--outcome",
    "attested",
    "--reviewed-retained-strings",
    "--reviewed-series",
    "--reviewed-high-risk-instances",
)


def test_the_command_records_each_redaction_verdict(first_run):
    pack, positions = first_run
    revised = str(positions[_REVISED])

    status, stdout, stderr = _command(
        str(pack),
        *_EVERY_REVIEW,
        "--redaction-accepted",
        str(positions[_ACCEPTED]),
        "--redaction-revised",
        revised,
        "--redaction-region",
        revised,
        "0",
        "0",
        "0",
        "2",
        "2",
        "--redaction-rejected",
        str(positions[_REJECTED]),
    )

    assert status == attestation_command.EXIT_RECORDED, stderr
    assert qc_attestation.attested_pack(pack)[0].redactions == tuple(
        sorted(_verdicts(positions), key=lambda verdict: verdict.position)
    )
    lines = stdout.splitlines()
    assert "  cleaned instances with their regions accepted: 1" in lines
    assert "  cleaned instances with the reviewer's regions added: 1" in lines
    assert "  cleaned instances rejected: 1" in lines
    # Each added region, with the preview of its frame, for the reviewer to
    # check.
    shown = qc_attestation.redaction_previews(pack)[positions[_REVISED], 0]
    assert shown.endswith(".png")
    assert f"    instance {revised}, frame 0, shown in {shown}: adds [0, 0, 2, 2]" in (
        lines
    )
    assert "Quokka" not in stdout + stderr


@pytest.mark.parametrize(
    "verdicts, message",
    [
        (
            ("--redaction-accepted", "{0}", "--redaction-rejected", "{0}"),
            "more than one redaction verdict",
        ),
        (
            ("--redaction-accepted", "{0}", "--redaction-region", "{0}", *"00022"),
            "not revised",
        ),
        (
            ("--redaction-revised", "{0}", "--redaction-region", "{0}", *"00000"),
            "no rows or no columns",
        ),
        (
            ("--redaction-revised", "{0}", "--redaction-region", "{0}", "-1", *"0022"),
            "before the first",
        ),
        (("--redaction-revised", "{0}"), "no region to add"),
        (("--redaction-accepted", "{1}"), "does not list as cleaned and previewed"),
    ],
)
def test_the_command_refuses_verdicts_that_cannot_be_recorded(
    first_run, verdicts, message
):
    pack, positions = first_run
    argv = [each.format(positions[_ACCEPTED], positions[_PLAN]) for each in verdicts]

    status, _, stderr = _command(str(pack), *_EVERY_REVIEW, *argv)

    assert status == attestation_command.EXIT_NOT_RECORDED
    assert message in stderr
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


def test_the_command_refuses_a_verdict_with_an_outcome_of_rejected(first_run):
    pack, positions = first_run

    status, _, stderr = _command(
        str(pack),
        "--reviewer",
        "Quokka Wombatson",
        "--outcome",
        "rejected",
        "--redaction-rejected",
        str(positions[_REJECTED]),
    )

    assert status == attestation_command.EXIT_NOT_RECORDED
    assert "would release nothing; nothing was recorded" in stderr
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


# A second run of the same files, given the first run's verdicts.


@pytest.fixture(name="second_run", scope="module")
def fixture_second_run():
    with _second_run() as found:
        yield found


@contextlib.contextmanager
def _second_run():
    """Run the files under the option, attest the pack with a verdict of each
    kind, and run them again, renamed into the reverse order, given the
    verdicts."""
    # A short directory, since a run refuses output paths that could exceed
    # Windows' 259 characters.
    directory = Path(tempfile.mkdtemp(prefix="d"))
    try:
        files = _files()
        _write(directory / "source", files)
        first = _run(
            directory / "first",
            directory / "source",
            InstanceTransform(_policy(), KEY, finder=Finder(), unvalidated_policy=True),
        )
        pack = first.qc_pack.parent
        document = json.loads(first.qc_pack.read_text("utf-8"))
        positions = {
            Path(entry["source"]).name: entry["position"]
            for entry in document["instances"]
        }
        past = RedactionVerdict(
            positions[_PAST], Redaction.REVISED, ((0, (TextBox(0, 0, 2, 9),)),)
        )
        # Attesting refuses that region, given the pack's Rows and Columns;
        # this pack is made to list more Columns for the image, so that the
        # run's own check is what meets it.
        previewed = qc_attestation.previewed_redactions
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                qc_attestation,
                "previewed_redactions",
                lambda data: {
                    position: (
                        dataclasses.replace(shape, columns=9)
                        if position == positions[_PAST]
                        else shape
                    )
                    for position, shape in previewed(data).items()
                },
            )
            attestation = _attest(pack, (*_verdicts(positions), past))
        # The verdicts follow the files' contents alone.
        again = {
            f"{number}{name}": files[name]
            for number, name in enumerate(reversed(sorted(files)))
        }
        _write(directory / "again", again)
        transform = InstanceTransform(
            _policy(),
            KEY,
            finder=Finder(),
            redaction_review=read_redaction_review(pack),
            unvalidated_policy=True,
        )
        second = _run(directory / "second", directory / "again", transform)
        entries = json.loads(second.qc_pack.read_text("utf-8"))["instances"]
        outcomes = {
            Path(entry["source"]).name[1:]: (
                entry["disposition"],
                None
                if entry.get("output") is None
                else pydicom.dcmread(
                    directory / "second" / "release" / entry["output"]
                ),
            )
            for entry in entries
        }
        report = json.loads(
            (directory / "second" / "release" / "release-report.json").read_text()
        )
        yield attestation, outcomes, report, second, entries
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.mark.deid_requirement("PS3.15-E.3.1-01", "PS3.15-E.3.1-02")
@pytest.mark.parametrize(
    "name, regions",
    # A revised image has the reviewer's region as well as the finder's.
    [(_ACCEPTED, (BOX,)), (_REVISED, (BOX, REVISED))],
)
def test_an_approved_image_is_released_with_its_reviewed_regions(
    second_run, name, regions
):
    _, outcomes, _, _, _ = second_run
    number = _IMAGES.index(name)
    frame = _frame(start=100 * (number + 1))

    disposition, dataset = outcomes[name]

    assert disposition == "released"
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
    assert dataset.BurnedInAnnotation == "NO"
    pixels = pydicom.pixels.pixel_array(dataset)
    inside = np.logical_or.reduce([_inside(frame.shape, r) for r in regions])
    assert np.all(pixels[inside] == frame.min())
    assert np.array_equal(pixels[~inside], frame[~inside])


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_rejected_image_is_sequestered(second_run):
    _, outcomes, report, result, entries = second_run
    names = {entry["position"]: Path(entry["source"]).name[1:] for entry in entries}

    assert outcomes[_REJECTED] == ("sequestered", None)
    (rejected,) = [o for o in result.outcomes if names[o.position] == _REJECTED]
    assert rejected.reasons == (TransformReason.REDACTION_REJECTED,)
    codes = [
        reason["code"] for entry in report["sequestered"] for reason in entry["reasons"]
    ]
    assert sorted(codes) == ["redaction-mismatch", "redaction-rejected"]


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_an_image_whose_reviewed_region_goes_past_its_frame_is_sequestered(
    second_run,
):
    _, outcomes, _, result, entries = second_run
    names = {entry["position"]: Path(entry["source"]).name[1:] for entry in entries}

    assert outcomes[_PAST] == ("sequestered", None)
    (past,) = [o for o in result.outcomes if names[o.position] == _PAST]
    assert past.reasons == (TransformReason.REDACTION_MISMATCH,)


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_an_image_without_a_verdict_is_held_as_in_the_first_run(second_run):
    _, outcomes, report, result, entries = second_run
    names = {entry["position"]: Path(entry["source"]).name[1:] for entry in entries}

    assert outcomes[_UNJUDGED] == ("held-for-review", None)
    (held,) = [o for o in result.outcomes if names[o.position] == _UNJUDGED]
    assert held.reasons == (HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT),)
    assert report["held_for_review"] == [
        {"stage": "pixel-data", "code": "text-blacked-out", "count": 1}
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.1-02")
@pytest.mark.parametrize("name", [_PLAN, _STRUCTURE_SET])
def test_an_instance_without_pixel_data_claims_the_option(second_run, name):
    _, outcomes, _, _, _ = second_run

    disposition, dataset = outcomes[name]

    assert disposition == "released"
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
    # Neither IOD defines Burned In Annotation, but E.3.1 adds it with the
    # option's code all the same.
    assert dataset.BurnedInAnnotation == "NO"


def test_the_report_names_the_reviewed_pack(second_run):
    attestation, _, report, _, _ = second_run

    assert report["redaction_review"] == {"reference": attestation.reference}
    assert report["format"] == "pymedphys-deid-release-report/28"


class _Blind(Finder):
    """A finder of another method, which finds no text."""

    method = {"finder": "none", "version": 1}

    def __init__(self):
        super().__init__(boxes=())


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_rerun_writes_the_reviewed_regions_whatever_its_finder(first_run, tmp_path):
    pack, positions = first_run
    _attest(pack, _verdicts(positions))
    finder = _Blind()
    transform = InstanceTransform(
        _policy(),
        KEY,
        finder=finder,
        redaction_review=read_redaction_review(pack),
        unvalidated_policy=True,
    )

    result = _run(tmp_path / "second", tmp_path / "source", transform)

    entries = json.loads(result.qc_pack.read_text("utf-8"))["instances"]
    released = {
        Path(entry["source"]).name: pydicom.dcmread(
            tmp_path / "second" / "release" / entry["output"]
        )
        for entry in entries
        if entry["disposition"] == "released"
    }
    for name, regions in [(_ACCEPTED, (BOX,)), (_REVISED, (BOX, REVISED))]:
        frame = _frame(start=100 * (_IMAGES.index(name) + 1))
        inside = np.logical_or.reduce([_inside(frame.shape, r) for r in regions])
        pixels = pydicom.pixels.pixel_array(released[name])
        assert np.all(pixels[inside] == frame.min())
        assert np.array_equal(pixels[~inside], frame[~inside])
    # The finder was shown the two images without a verdict, and neither an
    # approved image nor the rejected one.
    assert len(finder.seen) == 2
    approved = [_frame(start=100 * (_IMAGES.index(n) + 1)) for n in _IMAGES[:2]]
    assert not any(
        np.array_equal(seen, frame) for seen in finder.seen for frame in approved
    )
    # The images without an approving verdict are not released, though this
    # finder finds no text in them.
    dispositions = {
        Path(entry["source"]).name: entry["disposition"] for entry in entries
    }
    assert [dispositions[name] for name in (_REJECTED, _UNJUDGED, _PAST)] == [
        "sequestered",
        "held-for-review",
        "held-for-review",
    ]
