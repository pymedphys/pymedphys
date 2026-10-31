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

# The tests share the face review's helpers and one reviewed run of the
# synthetic collection, so they stay in one module.
# pylint: disable = too-many-lines

import dataclasses
import datetime
import hashlib
import io
import json
import contextlib
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    markers,
    qc_attestation,
    qc_previews,
    qc_store,
    release_report,
    release_report_markdown,
    run,
    run_qc,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.dose_defacing import RT_DOSE
from pymedphys._dicom.deidentify.face_review import (
    DOSE_IN_FACE_BLOCK_TEXT,
    UNDEFACED_TEXT,
    FaceReview,
    carries_visual_features,
    contour_data_sha256,
    holds_deformation_grid,
    pixel_data_sha256,
    read_face_review,
)
from pymedphys._dicom.deidentify.iods import load_iod_tables
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.run_results import Transformed
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.method_digest import method_digest
from pymedphys._dicom.deidentify.policy import (
    CLEAN_PIXEL_DATA,
    CLEAN_RECOGNIZABLE_VISUAL_FEATURES,
    PolicyError,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.qc_attestation import Coverage, Face, Outcome
from pymedphys._dicom.deidentify.qc_pack import (
    NO_CONTOURS_SHA256,
    NO_PIXELS_SHA256,
    Disposition,
    InstanceEntry,
    Preview,
    PreviewKind,
    QcPack,
    QcPackError,
)
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.scope import SUPPORTED_IODS
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.reasons import (
    HeldPixelData,
    HeldVisualFeatures,
    PixelDataReason,
    VisualFeaturesReason,
)
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _synthetic_compressed as compressed
from ._corpus_run import decoders_installed
from .test_deidentify_qc_face_verdicts import SERIES, _digest, _released

REFERENCE = "A-" + "0123456789abcdef" * 2
KEY = DeidKey(bytes(range(32)))
OPTION = CLEAN_RECOGNIZABLE_VISUAL_FEATURES
CODE = "113102"
COMPLETE = Coverage(retained_strings=True, series=True, high_risk_instances=True)
WHEN = datetime.datetime(2026, 10, 12, 22, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture(name="pack")
def fixture_pack(tmp_path):
    """A QC pack of five released instances in two series, (0, 2, 3) and (1, 4),
    with the pixel data and contours written of each but 3, whose file the
    gate did not hand over."""
    release = tmp_path / "release"
    release.mkdir()
    instances = tuple(
        _released(n) if n == 3 else _with_written(_released(n), n) for n in range(5)
    )
    written = _sheeted(instances)
    return qc_store.write_qc_pack(
        written, tmp_path / "secretdir-qc", release_directory=release
    ).parent


def _sheeted(instances):
    """A pack of these instances, with a preview of each whose pixel data's
    SHA-256 it records, and a contour sheet of each whose contours', as the
    pack needs."""
    shown = [
        (PreviewKind.INSTANCE, entry.position)
        for entry in instances
        if entry.pixel_sha256 not in (None, NO_PIXELS_SHA256)
    ] + [
        (PreviewKind.STRUCTURE_SET_CONTOURS, entry.position)
        for entry in instances
        if entry.contour_sha256 not in (None, NO_CONTOURS_SHA256)
    ]
    previews = tuple(
        Preview(
            f"P-{number:04d}.png",
            kind,
            ((position, 0),),
            1,
            qc_previews.png(np.zeros((2, 2), np.uint8)),
        )
        for number, (kind, position) in enumerate(shown, 1)
    )
    return QcPack(REFERENCE, instances, series=SERIES, previews=previews)


def _sha(*numbers):
    return frozenset(bytes.fromhex(_digest(n)) for n in numbers)


def _pixel_digest(n):
    return _digest(100 + n)


def _contour_digest(n):
    return _digest(200 + n)


def _with_written(entry, n):
    return dataclasses.replace(
        entry, pixel_sha256=_pixel_digest(n), contour_sha256=_contour_digest(n)
    )


def _pairs(*numbers):
    return frozenset(
        (bytes.fromhex(_digest(n)), bytes.fromhex(_pixel_digest(n))) for n in numbers
    )


def _contour_pairs(*numbers):
    return frozenset(
        (bytes.fromhex(_digest(n)), bytes.fromhex(_contour_digest(n))) for n in numbers
    )


def _one(digests):
    (digest,) = digests
    return digest


def _attest(directory, faces, outcome=Outcome.ATTESTED, redactions=()):
    return qc_attestation.attest(
        directory,
        reviewer="Quokka Wombatson",
        outcome=outcome,
        coverage=COMPLETE,
        attested_at=WHEN,
        faces=faces,
        redactions=redactions,
    )


def _policy(*options):
    return compose_custom_policy([*options, OPTION])


# The face review.


def test_each_verdict_gives_its_series_source_digests(pack):
    _attest(pack, {SERIES[0].positions[0]: Face.ABSENT, 1: Face.PRESENT})

    review = read_face_review(pack)

    assert review.absent == _sha(0, 2, 3)
    assert review.present == _sha(1, 4)
    # With the pixel data and contours written of each file marked absent,
    # where the pack has them.
    assert review.absent_pixels == _pairs(0, 2)
    assert review.absent_contours == _contour_pairs(0, 2)
    assert review.reference == REFERENCE


def test_a_series_without_a_verdict_gives_no_digests(pack):
    _attest(pack, {1: Face.ABSENT})

    review = read_face_review(pack)

    assert review.absent == _sha(1, 4)
    assert review.absent_pixels == _pairs(1, 4)
    assert review.absent_contours == _contour_pairs(1, 4)
    assert not review.present


@pytest.mark.parametrize("reason", [UNDEFACED_TEXT, DOSE_IN_FACE_BLOCK_TEXT])
def test_a_verdict_of_absent_leaves_out_a_file_held_because_its_frame_was_defaced(
    tmp_path, reason
):
    # Position 2, an RT Structure Set or RT Dose, say, was held beside the
    # defaced slices that the reviewer judged, with its own outlines or dose
    # left as they were.
    held = InstanceEntry(
        2,
        "/imports/2.dcm",
        Disposition.HELD_FOR_REVIEW,
        reasons=("ReleaseReason.RT_DOSE", reason),
        source_sha256=_digest(2),
        pixel_sha256=_pixel_digest(2),
        contour_sha256=_contour_digest(2),
    )
    instances = tuple(
        held if n == 2 else _with_written(_released(n), n) for n in range(5)
    )
    release = tmp_path / "release"
    release.mkdir()
    directory = qc_store.write_qc_pack(
        _sheeted(instances),
        tmp_path / "qc",
        release_directory=release,
    ).parent
    _attest(directory, {0: Face.ABSENT, 1: Face.PRESENT})

    review = read_face_review(directory)

    assert review.absent == _sha(0, 3)
    assert review.absent_pixels == _pairs(0, 3)
    assert review.absent_contours == _contour_pairs(0, 3)
    assert review.present == _sha(1, 4)
    assert (
        review.hold_reason(
            _one(_sha(2)),
            bytes.fromhex(_pixel_digest(2)),
            bytes.fromhex(_contour_digest(2)),
        )
        is VisualFeaturesReason.NO_FACE_VERDICT
    )


def test_a_verdict_of_present_still_covers_a_file_held_because_its_frame_was_defaced(
    tmp_path,
):
    held = InstanceEntry(
        4,
        "/imports/4.dcm",
        Disposition.HELD_FOR_REVIEW,
        reasons=(UNDEFACED_TEXT,),
        source_sha256=_digest(4),
    )
    instances = tuple(held if n == 4 else _released(n) for n in range(5))
    release = tmp_path / "release"
    release.mkdir()
    directory = qc_store.write_qc_pack(
        _sheeted(instances),
        tmp_path / "qc",
        release_directory=release,
    ).parent
    _attest(directory, {1: Face.PRESENT})

    assert read_face_review(directory).present == _sha(1, 4)


def test_a_pack_entry_without_its_reasons_gives_no_review(pack):
    written = pack / "qc-pack.json"
    document = json.loads(written.read_text("ascii"))
    del document["instances"][0]["reasons"]
    written.write_text(json.dumps(document), "ascii")
    _attest(pack, {1: Face.ABSENT})

    with pytest.raises(QcPackError, match="not of its format"):
        read_face_review(pack)


def test_the_frame_hold_is_matched_as_the_run_words_it():
    assert UNDEFACED_TEXT == run_qc.reason_text(
        HeldVisualFeatures(VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME)
    )
    assert DOSE_IN_FACE_BLOCK_TEXT == run_qc.reason_text(
        HeldVisualFeatures(VisualFeaturesReason.DOSE_IN_FACE_BLOCK)
    )


def test_a_pack_that_is_not_attested_gives_no_review(pack):
    with pytest.raises(QcPackError, match="has not been attested"):
        read_face_review(pack)


def test_a_rejected_attestation_gives_no_review(pack):
    _attest(pack, {1: Face.ABSENT})
    # Attesting refuses verdicts with a rejection, so the file is changed by
    # hand, as it might be outside the command.
    path = pack / qc_attestation.ATTESTATION_FILE
    document = json.loads(path.read_text("ascii"))
    path.chmod(0o600)
    path.write_text(json.dumps({**document, "outcome": "rejected"}), encoding="ascii")

    with pytest.raises(QcPackError, match="verdicts release nothing"):
        read_face_review(pack)


def test_attesting_refuses_a_face_verdict_with_an_outcome_of_rejected(pack):
    with pytest.raises(QcPackError, match="would release nothing"):
        _attest(pack, {1: Face.ABSENT}, Outcome.REJECTED)
    assert not (pack / qc_attestation.ATTESTATION_FILE).exists()


def test_a_pack_changed_after_its_verdicts_gives_no_review(pack):
    _attest(pack, {1: Face.ABSENT})
    written = pack / "qc-pack.json"
    written.write_bytes(written.read_bytes().replace(b'"', b'"', 1) + b" ")

    with pytest.raises(QcPackError) as raised:
        read_face_review(pack)
    assert str(pack) not in str(raised.value)


def test_a_source_file_is_released_only_from_a_series_marked_absent():
    review = FaceReview(REFERENCE, _sha(0, 3), _sha(1), _pairs(0), _contour_pairs(0))
    written = bytes.fromhex(_pixel_digest(0)), bytes.fromhex(_contour_digest(0))

    assert review.hold_reason(_one(_sha(0)), *written) is None
    assert (
        review.hold_reason(_one(_sha(1)), *written) is VisualFeaturesReason.FACE_PRESENT
    )
    # Any other file, such as one changed since the review, has no verdict.
    assert (
        review.hold_reason(_one(_sha(2)), *written)
        is VisualFeaturesReason.NO_FACE_VERDICT
    )


@pytest.mark.parametrize(
    "pixels",
    [bytes.fromhex(_pixel_digest(1)), hashlib.sha256().digest(), None],
    ids=["other", "none written", "unreadable"],
)
def test_a_verdict_releases_only_the_pixel_data_that_the_reviewed_run_wrote(pixels):
    review = FaceReview(
        REFERENCE, _sha(0, 3), frozenset(), _pairs(0), _contour_pairs(0, 3)
    )

    # Such as a CT slice defaced since the reviewer saw it as received, or
    # blacked out in other regions, or a file whose written pixel data the
    # pack does not have.
    assert (
        review.hold_reason(_one(_sha(0)), pixels, bytes.fromhex(_contour_digest(0)))
        is VisualFeaturesReason.OTHER_PIXEL_DATA
    )
    assert (
        review.hold_reason(
            _one(_sha(3)),
            bytes.fromhex(_pixel_digest(3)),
            bytes.fromhex(_contour_digest(3)),
        )
        is VisualFeaturesReason.OTHER_PIXEL_DATA
    )


@pytest.mark.parametrize(
    "contours",
    [bytes.fromhex(_contour_digest(1)), contour_data_sha256(pydicom.Dataset()), None],
    ids=["other", "none written", "unreadable"],
)
def test_a_verdict_releases_only_the_contours_that_the_reviewed_run_wrote(contours):
    review = FaceReview(
        REFERENCE, _sha(0, 3), frozenset(), _pairs(0, 3), _contour_pairs(0)
    )
    pixels = bytes.fromhex(_pixel_digest(0))

    # Such as a structure set cut by a face block since the reviewer saw it
    # as received, or one that the reviewed run cut and this run does not,
    # or a file whose written contours the pack does not have.
    assert (
        review.hold_reason(_one(_sha(0)), pixels, contours)
        is VisualFeaturesReason.OTHER_CONTOURS
    )
    assert (
        review.hold_reason(
            _one(_sha(3)),
            bytes.fromhex(_pixel_digest(3)),
            bytes.fromhex(_contour_digest(3)),
        )
        is VisualFeaturesReason.OTHER_CONTOURS
    )
    assert (
        review.hold_reason(_one(_sha(0)), pixels, bytes.fromhex(_contour_digest(0)))
        is None
    )


def _contoured(*rois):
    """A data set with an ROI Contour Sequence item for each ROI, each a
    list of contours as (Contour Geometric Type, Contour Data)."""
    dataset = pydicom.Dataset()
    dataset.ROIContourSequence = []
    for contours in rois:
        item = pydicom.Dataset()
        item.ContourSequence = []
        for kind, data in contours:
            contour = pydicom.Dataset()
            contour.ContourGeometricType = kind
            contour.ContourData = data
            item.ContourSequence.append(contour)
        dataset.ROIContourSequence.append(item)
    return dataset


def test_contours_are_digested_by_roi_type_and_value():
    square = ["0", "0", "1", "1", "0", "1", "1", "1", "1"]
    one = contour_data_sha256(_contoured([("CLOSED_PLANAR", square)]))

    assert one == contour_data_sha256(_contoured([("CLOSED_PLANAR", square)]))
    # The values are compared as numbers, as written in either form.
    assert one == contour_data_sha256(
        _contoured([("CLOSED_PLANAR", ["0.0", *square[1:]])])
    )
    assert one != contour_data_sha256(
        _contoured([("CLOSED_PLANAR", ["0.5", *square[1:]])])
    )
    assert one != contour_data_sha256(_contoured([("OPEN_PLANAR", square)]))
    # Contours moved to another ROI, or split otherwise, differ.
    assert contour_data_sha256(
        _contoured([("POINT", square[:3]), ("POINT", square[3:6])])
    ) != contour_data_sha256(
        _contoured([("POINT", square[:3])], [("POINT", square[3:6])])
    )
    assert contour_data_sha256(
        _contoured([("OPEN_PLANAR", square[:6]), ("OPEN_PLANAR", square[6:])])
    ) != contour_data_sha256(
        _contoured([("OPEN_PLANAR", square[:3]), ("OPEN_PLANAR", square[3:])])
    )
    # Without contours, every data set gives one digest, as one with an
    # empty ROI Contour Sequence, or with ROIs without contours, does.
    assert contour_data_sha256(pydicom.Dataset()) == contour_data_sha256(_contoured())
    assert contour_data_sha256(pydicom.Dataset()) == contour_data_sha256(
        _contoured([], [])
    )
    assert one != contour_data_sha256(pydicom.Dataset())


def test_contours_that_cannot_be_read_have_no_digest():
    dataset = _contoured([("CLOSED_PLANAR", ["0", "0", "1"])])
    contour = dataset.ROIContourSequence[0].ContourSequence[0]
    # As a file that holds it would be read, converted only when used.
    contour[0x30060050] = pydicom.dataelem.RawDataElement(
        pydicom.tag.Tag(0x30060050), "DS", 6, b"secret", 0, True, True
    )

    with pytest.raises(ValueError) as raised:
        contour_data_sha256(dataset)
    assert "secret" not in str(raised.value)


def test_pixel_data_are_digested_by_tag_and_value():
    def digest(**elements):
        dataset = pydicom.Dataset()
        for keyword, value in elements.items():
            setattr(dataset, keyword, value)
        return pixel_data_sha256(dataset)

    values = b"\x01\x02\x03\x04"
    assert digest(PixelData=values) == digest(PixelData=values)
    assert digest(PixelData=values) != digest(PixelData=b"\x01\x02\x03\x05")
    assert digest(PixelData=values) != digest(FloatPixelData=values)
    # Both elements count, so that values cannot move from one to the other.
    assert digest(FloatPixelData=values, PixelData=values) not in {
        digest(PixelData=values + values),
        digest(FloatPixelData=values + values),
    }
    # A file pads an odd value with a null byte, which the digest takes.
    assert digest(PixelData=b"\x01\x02\x03") == digest(PixelData=b"\x01\x02\x03\x00")
    assert digest() == hashlib.sha256().digest()
    assert digest(Rows=2) == digest()


@pytest.mark.parametrize(
    "fields",
    [
        {"reference": "A-0123"},
        {"reference": REFERENCE.upper()},
        {"absent": {bytes(32)}},
        {"present": frozenset({bytes(31)})},
        {"absent": frozenset({"0" * 64})},
        {"absent_pixels": _pairs(0)},
        {"absent": _sha(0), "absent_pixels": {next(iter(_pairs(0)))}},
        {"absent": _sha(0), "absent_pixels": frozenset({(_one(_sha(0)), bytes(31))})},
        {"absent": _sha(0), "absent_pixels": frozenset({_one(_sha(0))})},
        {"absent_contours": _contour_pairs(0)},
        {
            "absent": _sha(0),
            "absent_contours": frozenset({(_one(_sha(0)), bytes(31))}),
        },
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
        (None, "Spatial Registration", False),
        (None, "Deformable Spatial Registration", False),
    ],
)
def test_an_instance_needs_a_verdict_where_it_can_show_a_face(keyword, iod, carries):
    dataset = pydicom.Dataset()
    if keyword is not None:
        setattr(dataset, keyword, b"\x00\x00\x00\x00")

    assert carries_visual_features(dataset, iod) is carries


def _deformable(*items):
    dataset = pydicom.Dataset()
    dataset.DeformableRegistrationSequence = list(items)
    return dataset


def _with_grid():
    item = pydicom.Dataset()
    grid = pydicom.Dataset()
    grid.VectorGridData = b"\x00" * 12
    item.DeformableRegistrationGridSequence = [grid]
    return item


@pytest.mark.parametrize(
    "dataset, holds",
    [
        (pydicom.Dataset(), False),
        (_deformable(), False),
        # Only matrices, before and after a deformation that it does not
        # give.
        (_deformable(pydicom.Dataset()), False),
        (_deformable(pydicom.Dataset(), _with_grid()), True),
    ],
)
def test_a_deformation_grid_can_show_a_face(dataset, holds):
    iod = "Deformable Spatial Registration"

    assert holds_deformation_grid(dataset) is holds
    assert carries_visual_features(dataset, iod) is holds


def test_a_deformable_registration_sequence_that_cannot_be_read_may_hold_a_grid():
    dataset = pydicom.Dataset()
    # Bytes that are not items.
    dataset[0x00640002] = pydicom.DataElement(0x00640002, "OB", b"\x01\x02")

    assert holds_deformation_grid(dataset)


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


def test_the_statement_names_each_supported_iod_that_lacks_the_attribute():
    tables = load_iod_tables()
    lacking = {
        name for name in SUPPORTED_IODS if not tables.iods[name].lookup("(0028,0302)")
    }

    assert lacking == {
        "RT Plan",
        "RT Structure Set",
        "RT Beams Treatment Record",
        "MR Spectroscopy",
        "Spatial Registration",
        "Deformable Spatial Registration",
        "X-Ray Radiation Dose SR",
        "Radiopharmaceutical Radiation Dose SR",
        "Basic Text SR",
        "Enhanced SR",
        "Comprehensive SR",
        "Comprehensive 3D SR",
        "Extensible SR",
        "Key Object Selection Document",
        "Mammography CAD SR",
        "Chest CAD SR",
        "Colon CAD SR",
        "Procedure Log",
        "Spectacle Prescription Report",
        "Macular Grid Thickness and Volume Report",
        "Waveform Annotation SR",
        "Implantation Plan SR Document",
        "Simplified Adult Echo SR",
        "Planned Imaging Agent Administration SR",
        "Performed Imaging Agent Administration SR",
        "Acquisition Context SR",
    }
    assert (
        "which of the supported IODs are RT Plan, RT Structure Set, RT Beams "
        "Treatment Record, MR Spectroscopy, Spatial Registration, Deformable "
        "Spatial Registration, X-Ray Radiation Dose SR, Radiopharmaceutical "
        "Radiation Dose SR, Basic Text SR, Enhanced SR, Comprehensive SR, "
        "Comprehensive 3D SR, Extensible SR, Key Object Selection Document, "
        "Mammography CAD SR, Chest CAD SR, Colon CAD SR, Procedure Log, "
        "Spectacle Prescription Report, Macular Grid Thickness and Volume "
        "Report, Waveform Annotation SR, Implantation Plan SR Document, "
        "Simplified Adult Echo SR, Planned Imaging Agent Administration SR, "
        "Performed Imaging Agent Administration SR, and Acquisition Context "
        "SR."
    ) in conformance_markdown.render_markdown(
        conformance.conformance_statement(_policy(), vocabulary=None)
    )


def test_the_statement_of_the_option_alone_has_one_review_code():
    statement = conformance.conformance_statement(_policy(), vocabulary=None)

    assert statement.markers.codes == (markers.PROFILE_CODE,)
    assert statement.markers.review_codes == (CODE,)


def test_with_clean_pixel_data_both_options_are_claimed_after_review():
    statement = conformance.conformance_statement(
        _policy("clean_pixel_data"), vocabulary=None
    )

    assert statement.markers.codes == (markers.PROFILE_CODE,)
    # In the policy's order, which puts Clean Pixel Data first.
    assert statement.markers.review_codes == ("113101", CODE)


@pytest.mark.parametrize(
    "pixel, claims",
    [
        (
            (),
            "claims Clean Recognizable Visual Features only for an instance that "
            "cannot show a face or whose source file a reviewer found free of "
            "one, and never Clean Pixel Data.",
        ),
        (
            ("clean_pixel_data",),
            "claims Clean Pixel Data only for an instance without top-level "
            "pixel data or whose regions a reviewer approved, and Clean "
            "Recognizable Visual Features only for one that cannot show a face "
            "or whose source file a reviewer found free of one.",
        ),
    ],
)
def test_the_statement_says_the_option_is_claimed_only_after_review(pixel, claims):
    neither = (
        "claims neither Clean Pixel Data nor Clean Recognizable Visual Features."
        if not pixel
        else "and never Clean Recognizable Visual Features."
    )
    under = conformance_markdown.render_markdown(
        conformance.conformance_statement(_policy(*pixel), vocabulary=None)
    )
    without = conformance_markdown.render_markdown(
        conformance.conformance_statement(
            compose_custom_policy(["clean_descriptors", *pixel]), vocabulary=None
        )
    )

    assert claims in under and neither not in under
    assert neither in without and claims not in without
    # Pixel Data are not said to be written unchanged where the option
    # defaces them.
    face = "unchanged, but for the face region that the Clean Recognizable"
    assert face in under and face not in without


def test_the_report_names_the_reviewed_pack_by_its_reference():
    report = release_report.release_report(
        _policy(), vocabulary=None, reviewed_roi_names=None, face_review=REFERENCE
    )
    held = release_report.held_for_review(
        [(HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT),)]
    )
    report = dataclasses.replace(report, held_for_review=held)
    document = release_report.report_document(report)

    assert document["face_review"] == {
        "reference": REFERENCE,
        "ct_series": {"defaced": 0, "not_defaced": []},
    }
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
_DEFORMABLE = "19-registration-deformable.dcm"
# The instances that cannot show a face.
_FACELESS = (
    "05-rtplan.dcm",
    "14-mr-spectroscopy.dcm",
    "18-registration.dcm",
    "20-rt-beams-record.dcm",
)


class _CornerFinder:
    """Finds text in the top left corner of every frame."""

    # What decides its regions, as the method digest takes it.
    method = {"finder": "top left corner"}

    def find(self, frame):
        del frame
        return (TextBox(0, 0, 2, 3),)


# Both runs review the same first run, so it is made once.
@pytest.fixture(name="first_run", scope="module")
def fixture_first_run():
    with _first_run() as found:
        yield found


@pytest.fixture(name="second_run", scope="module")
def fixture_second_run(first_run):
    return _second_run(first_run, name="s")


@pytest.fixture(name="second_run_with_pixel_data", scope="module")
def fixture_second_run_with_pixel_data(first_run):
    return _second_run(first_run, CLEAN_PIXEL_DATA, name="p")


@contextlib.contextmanager
def _first_run():
    """Run the synthetic collection under ``basic``, and attest its pack."""
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
                # No preview shows its grid, so this verdict releases none
                # of it.
                by_first[_DEFORMABLE]["positions"][0]: Face.ABSENT,
            },
        )
        # The same files, renamed so that they are found in the reverse
        # order, since the verdicts follow the files' contents alone.
        again = directory / "again"
        again.mkdir()
        files = sorted(instances.iterdir())
        for number, file in enumerate(reversed(files)):
            shutil.copyfile(file, again / f"{number:02d}{file.name}")
        yield directory, attestation, read_face_review(pack_directory), again
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _second_run(first_run, *others, name):
    """Run the files of ``first_run`` again, into ``name`` beside them, under
    the option and ``others``, given its verdicts."""
    directory, attestation, review, again = first_run
    directory = directory / name
    directory.mkdir()
    transform = InstanceTransform(
        _policy(*others),
        KEY,
        face_review=review,
        finder=_CornerFinder() if CLEAN_PIXEL_DATA in others else None,
        unvalidated_policy=True,
    )
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
    return attestation, outcomes, report, second


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
        and name not in _FACELESS
        and name not in corpus_module.STRUCTURED_REPORT_FILES
    }

    assert can_show >= {*_DOSE, _DEFORMABLE}
    # The reports cannot show a face, and their Content Sequence sequesters
    # them, as it does without the option (D-021).
    for name in corpus_module.STRUCTURED_REPORT_FILES:
        assert outcomes[name] == ("sequestered", None), name
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


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_with_clean_pixel_data_a_verdict_covers_only_the_pixel_data_seen(
    second_run_with_pixel_data,
):
    _, outcomes, _, result = second_run_with_pixel_data
    entries = json.loads(result.qc_pack.read_text("utf-8"))["instances"]
    names = {entry["position"]: Path(entry["source"]).name[2:] for entry in entries}
    reasons = {names[o.position]: set(o.reasons) for o in result.outcomes}
    blacked_out = HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT)

    # A CT series marked absent is held for its pixel data, which still
    # await review; and since their corners are blacked out, they are not
    # the pixel data that the reviewer saw, so its verdict does not cover
    # them.
    for name in _CT:
        assert outcomes[name] == ("held-for-review", None), name
        assert reasons[name] == {
            blacked_out,
            HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA),
        }
    # A series marked present is held for both.
    assert blacked_out in reasons[_DOSE[0]]
    assert HeldVisualFeatures(VisualFeaturesReason.FACE_PRESENT) in reasons[_DOSE[0]]
    # What has no pixel data is released, and claims both options, since
    # it has nothing for Clean Pixel Data to clean, but for the deformable
    # registration, whose grid no preview shows.
    assert reasons[_DEFORMABLE] == {
        HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT)
    }
    released = (_STRUCTURE_SET, *_FACELESS)
    for name in released:
        disposition, dataset = outcomes[name]
        assert disposition == "released", name
        assert dataset.RecognizableVisualFeatures == "NO"
        assert dataset.BurnedInAnnotation == "NO"
        assert _codes(dataset)[-3:] == [markers.PROFILE_CODE, "113101", CODE]
    assert {
        name for name, (_, dataset) in outcomes.items() if dataset is not None
    } == set(released)


@pytest.mark.deid_requirement("PS3.15-E.3.2-02")
def test_an_instance_that_cannot_show_a_face_satisfies_the_option(second_run):
    _, outcomes, _, _ = second_run

    for name in _FACELESS:
        disposition, dataset = outcomes[name]
        assert disposition == "released", name
        assert CODE in _codes(dataset)
        # None of their IODs defines Recognizable Visual Features, but E.3.2
        # adds it with the option's code all the same.
        assert dataset.RecognizableVisualFeatures == "NO"


def test_the_report_names_the_attested_pack(second_run):
    attestation, _, report, _ = second_run

    assert report["face_review"]["reference"] == attestation.reference
    assert report["format"] == "pymedphys-deid-release-report/32"


def test_the_report_counts_the_ct_series_that_were_not_defaced(second_run):
    _, _, report, _ = second_run

    # The collection's one CT series, of slices two pixels square, holds no
    # head to find.
    assert report["face_review"]["ct_series"] == {
        "defaced": 0,
        "not_defaced": [{"reason": "no-eyes", "count": 1}],
    }


def test_a_held_reason_is_a_visual_features_reason():
    with pytest.raises(TypeError):
        HeldVisualFeatures("face-present")  # type: ignore[arg-type]


@pytest.mark.skipif(
    not decoders_installed(), reason="needs a decoder of each compressed syntax"
)
def test_a_verdict_releases_compressed_pixel_data_as_the_reviewed_run_wrote_them():
    corpus = compressed.compressed_corpus(corpus_module.build_corpus())
    held = HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA)
    released = cut = doses = 0

    for file in corpus.files:
        if file.manifest.transfer_syntax not in compressed.CORPUS_SYNTAXES:
            continue
        record = InstanceRecord.from_file(file.data)
        source = hashlib.sha256(file.data).digest()
        unseen = InstanceTransform(
            _policy(),
            KEY,
            face_review=FaceReview(REFERENCE, frozenset({source}), frozenset()),
            unvalidated_policy=True,
        )(file.data, record)
        if not isinstance(unseen, Transformed):
            continue
        # Marked absent, but with no pixel data seen, it is held; given the
        # pixel data that this run wrote, with each codestream's metadata
        # cut, it is released; an RT Dose only where its dose levels showed
        # every frame, as a review built by hand says only where asked.
        assert isinstance(unseen.evidence, HeldEvidence)
        assert held in getattr(unseen.evidence, "held")
        dataset = read_source(unseen.data).dataset()
        written = pixel_data_sha256(dataset)
        review = FaceReview(
            REFERENCE,
            frozenset({source}),
            frozenset(),
            frozenset({(source, written)}),
            frozenset({(source, contour_data_sha256(dataset))}),
        )
        seen = _seen(file.data, record, review)
        if record.iod == RT_DOSE:
            assert isinstance(seen.evidence, HeldEvidence), file.name
            assert getattr(seen.evidence, "held") == (held,), file.name
            frames = int(dataset.get("NumberOfFrames") or 1)
            review = dataclasses.replace(
                review, absent_dose_frames=frozenset({(source, written, frames)})
            )
            seen = _seen(file.data, record, review)
            doses += 1
        assert not isinstance(seen.evidence, HeldEvidence), file.name
        assert CODE in _codes(pydicom.dcmread(io.BytesIO(seen.data)))
        released += 1
        cut += written != pixel_data_sha256(read_source(file.data).dataset())
    assert released and cut
    # The collection's RT Dose images, in RLE Lossless, are among them.
    assert doses == 2


def _seen(data, record, review):
    return InstanceTransform(
        _policy(), KEY, face_review=review, unvalidated_policy=True
    )(data, record)
