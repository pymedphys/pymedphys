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

"""Runs under Clean Recognizable Visual Features of variants of the head CT
that test_deidentify_ct_defacing_run.py defaces, each compared with that
run: two defaced series in one Frame of Reference, a series of two time
points, a multi-frame series, and a structure set whose eyes are drawn away
from the globes, unconfirmed and confirmed. Every UID and value here is
invented."""

# The runs of the head share _ct_defacing_runs.py with
# test_deidentify_ct_defacing_run.py,
# test_deidentify_ct_defacing_review_runs.py, and
# test_deidentify_ct_defacing_dose_runs.py, which CI runs in parts of their
# own, so that no part reaches the time limit. This module makes the runs
# that its own tests review, and the defaced run of _ct_defacing_runs.py,
# which its tests compare their runs with.

from __future__ import annotations

import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import markers, qc_previews
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.face_review import FaceReview
from pymedphys._dicom.deidentify.qc_attestation import Face
from pymedphys._dicom.deidentify.qc_pack import new_reference
from pymedphys._dicom.deidentify.reasons import HeldVisualFeatures, VisualFeaturesReason
from pymedphys._dicom.deidentify.references import InstanceRecord

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from ._ct_defacing_runs import (
    _CT_FILES,
    _DOSE,
    _ERROR_DOSE,
    _HEAD_ENHANCED,
    _IN_THE_BLOCK,
    _LOW,
    _PET,
    _PET_ENHANCED,
    _PET_SLICES,
    _SCAN,
    _SEGMENTATION,
    _SEGMENTATIONS,
    _SLAB_STRUCTURE_SET,
    _STRUCTURE_SET,
    _UNDEFACED,
    _UNPLACED,
    _contours,
    _dose,
    _head_name,
    _pet_uptake,
    _phase_name,
    _reviewed,
    _runs,
    _second,
    _transform,
)

# The shared runs, which pytest finds here by their names.
from ._ct_defacing_runs import (  # noqa: F401  # pylint: disable = unused-import
    fixture_defaced,
    fixture_reviewed_low,
)
from .test_deidentify_visual_features_option import CODE, _codes


@pytest.fixture(name="eyes_away_own", scope="module")
def fixture_eyes_away_own(reviewed_eyes_away):
    return _second(
        reviewed_eyes_away,
        name="eo",
        instance_faces=dict.fromkeys(_UNDEFACED, Face.ABSENT),
    )


@pytest.fixture(name="multi_frame", scope="module")
def fixture_multi_frame():
    with _runs(first=(), dose=_dose(_LOW), multi_frame=True) as found:
        yield found


@pytest.fixture(name="phased", scope="module")
def fixture_phased():
    with _runs(first=(), dose=_dose(_LOW), time_points=2) as found:
        yield found


@pytest.fixture(name="phases", scope="module")
def fixture_phases():
    with _runs(first=(), dose=_dose(_LOW), phases=True) as found:
        yield found


@pytest.fixture(name="reviewed_eyes_away", scope="module")
def fixture_reviewed_eyes_away():
    with _reviewed(first=(), eyes_away=True) as found:
        yield found


# Marked absent as the run wrote them, with the face block that the eyes
# drawn disagree with left unconfirmed, and confirmed.
@pytest.fixture(name="eyes_away", scope="module")
def fixture_eyes_away(reviewed_eyes_away):
    return _second(reviewed_eyes_away, name="u")


@pytest.fixture(name="eyes_confirmed", scope="module")
def fixture_eyes_confirmed(reviewed_eyes_away):
    return _second(reviewed_eyes_away, name="c", confirmed=True)


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_verdict_of_its_own_needs_no_confirmed_block(eyes_away_own):
    _, outcomes, reasons, _ = eyes_away_own

    # No block cleans anything of an instance written as received, so the
    # eyes that disagree with the block, which hold the head's slices, do
    # not hold it.
    assert outcomes[_head_name(0)][0] == "held-for-review"
    for name in _UNDEFACED:
        assert outcomes[name][0] == "released", reasons[name]


def _released(outcomes, reasons, name):
    disposition, dataset = outcomes[name]
    assert disposition == "released", (name, reasons[name])
    assert dataset.RecognizableVisualFeatures == "NO"
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
    return dataset


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_two_defaced_series_in_one_frame_are_each_defaced_by_their_own_block(
    phases, defaced
):
    slices, outcomes, reasons, report = phases
    _, alone, _, _ = defaced

    # The phase series is the head's slices again, so its block, and what
    # each series is written as, is what the head's series alone is.
    for index in range(len(slices)):
        expected = alone[_head_name(index)][1].PixelData
        for name in (_head_name(index), _phase_name(index)):
            assert _released(outcomes, reasons, name).PixelData == expected, name
    assert report["face_review"]["ct_series"] == {
        "defaced": 2,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_what_lies_in_a_frame_of_two_defaced_series_is_cleaned_by_both_blocks(
    phases, defaced
):
    _, outcomes, reasons, _ = phases
    _, alone, _, _ = defaced

    # The PET slices and the low dose grid, cleaned by the two blocks, one
    # the other's, are written as by the head's block alone, and released.
    for name in (*_PET_SLICES, _DOSE[0]):
        dataset = _released(outcomes, reasons, name)
        assert dataset.PixelData == alone[name][1].PixelData, name


def _roi_contours(dataset):
    return {
        int(item.ReferencedROINumber): [
            [float(v) for v in contour.ContourData]
            for contour in item.get("ContourSequence", [])
        ]
        for item in dataset.ROIContourSequence
    }


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_structure_set_of_two_frames_is_cut_in_the_defaced_one_and_released(
    phases, defaced
):
    _, outcomes, reasons, _ = phases
    _, alone, _, _ = defaced
    dataset = _released(outcomes, reasons, _STRUCTURE_SET)
    written = _roi_contours(dataset)
    expected = _roi_contours(alone[_STRUCTURE_SET][1])

    # The head's ROIs, in the defaced frame, are cut as the head's series
    # alone cuts them; the ROI in the frame that the run holds nothing of
    # is as it was, though it lies where the block would be in the head's.
    assert {k: v for k, v in written.items() if k in expected} == expected
    (other,) = set(written) - set(expected)
    (contour,) = written[other]
    assert np.allclose(
        np.reshape(contour, (-1, 3)), files.square(_IN_THE_BLOCK, 10.0), atol=1e-4
    )
    frames = {
        item.FrameOfReferenceUID for item in dataset.ReferencedFrameOfReferenceSequence
    }
    assert len(frames) == 2


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_structure_set_cut_by_a_slab_is_released_on_its_drawn_contours(phases):
    _, outcomes, reasons, _ = phases

    # Main now previews signed doses and every reading of slab contours.
    _released(outcomes, reasons, _SLAB_STRUCTURE_SET)
    assert not reasons[_SLAB_STRUCTURE_SET]


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_an_error_dose_is_released_on_its_signed_dose_previews(phases):
    _, outcomes, reasons, _ = phases

    # Main now previews signed doses and every reading of slab contours.
    _released(outcomes, reasons, _ERROR_DOSE)
    assert not reasons[_ERROR_DOSE]


def _eye_checks(directory):
    """The eye checks of the QC pack in ``directory``, and its sheets."""
    (path,) = directory.glob("*.json")
    document = json.loads(path.read_text("utf-8"))
    sheets = [p for p in document["previews"] if p["kind"] == "series-eyes"]
    return document["eye_checks"], sheets, document


def test_an_eye_drawn_away_from_the_globes_shows_the_block_for_review(
    reviewed_eyes_away,
):
    checks, sheets, document = _eye_checks(reviewed_eyes_away.pack.parent)
    names = reviewed_eyes_away.names
    slices = reviewed_eyes_away.slices

    # The run defaces the series and holds it until a reviewer confirms its
    # block: the pack lists its slices with the block's digest, and draws
    # them, as received, through the globes found and the eye drawn away
    # from them.
    (check,) = checks
    held = {names[position] for position in check["positions"]}
    assert held == {_head_name(index) for index in range(len(slices))}
    assert len(check["block_sha256"]) == 64
    (sheet,) = sheets
    assert {each["position"] for each in sheet["frames"]} <= set(check["positions"])
    assert all(
        names[each["position"]].startswith("01-head") for each in sheet["frames"]
    )
    assert sheet["total_frames"] == len(slices)
    # Not one of the previews that could show a face.
    face_previews = [
        p for p in document["previews"] if p["kind"] not in ("series-eyes",)
    ]
    assert sheet not in face_previews


def test_an_eye_drawn_away_from_the_globes_holds_the_defaced_head_ct(eyes_away):
    slices, outcomes, reasons, report = eyes_away
    held = HeldVisualFeatures(VisualFeaturesReason.EYES_DISAGREE_WITH_ROIS)

    # Marked absent as the run wrote them, but with the block unconfirmed:
    # each slice, and each instance cleaned by the block, is still held.
    for index in range(len(slices)):
        assert outcomes[_head_name(index)] == ("held-for-review", None), index
        assert reasons[_head_name(index)] == {held}, index
    for name in (_STRUCTURE_SET, _DOSE[0], *_PET_SLICES, _SEGMENTATION):
        assert outcomes[name] == ("held-for-review", None), name
        assert reasons[name] == {held}, name
    # As are the RT Dose that its release gate also holds for review and the
    # label map, which no face verdict names.
    for name in (_DOSE[1], _SEGMENTATIONS[1]):
        assert outcomes[name] == ("held-for-review", None), name
        assert held in reasons[name], name
    assert report["face_review"]["ct_series"] == {
        "defaced": 1,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 1,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }
    counts = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert counts[held.reason.value] == (
        len(slices) + 1 + len(_DOSE) + len(_PET_SLICES) + len(_SEGMENTATIONS)
    )


def test_a_confirmed_block_releases_the_head_ct_defaced(eyes_confirmed, defaced):
    slices, outcomes, reasons, report = eyes_confirmed
    _, written, _, _ = defaced

    # Confirmed, the block is the one that eyes drawn at the globes give, so
    # each slice is released as the run defaced it there.
    for index in range(len(slices)):
        name = _head_name(index)
        disposition, dataset = outcomes[name]
        assert disposition == "released", (index, reasons[name])
        assert dataset.RecognizableVisualFeatures == "NO"
        assert dataset.PixelData == written[name][1].PixelData, index
    for name in (_STRUCTURE_SET, _DOSE[0], *_PET_SLICES):
        disposition, dataset = outcomes[name]
        assert disposition == "released", (name, reasons[name])
        assert dataset.RecognizableVisualFeatures == "NO"
    # The structure set is cut by the block, its lens gone.
    _, dataset = outcomes[_STRUCTURE_SET]
    assert _contours(dataset)["Lens_L"] is None
    assert report["face_review"]["ct_series"] == {
        "defaced": 1,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 1,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }
    assert not any(
        entry["code"] == "eyes-disagree-with-rois"
        for entry in report["held_for_review"]
    )


def _written_by_transform(data):
    """Each file of ``data`` as the option's first run writes it, one
    series' files prepared together."""
    transform = _transform((), FaceReview(new_reference(), frozenset(), frozenset()))
    records = {p: InstanceRecord.from_file(each) for p, each in enumerate(data)}
    transform.prepare(records, lambda position: data[position])
    return [
        pydicom.dcmread(pydicom.filebase.DicomBytesIO(transform(each, records[p]).data))
        for p, each in enumerate(data)
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_multi_frame_head_ct_is_written_as_air_where_its_slices_are(tmp_path):
    corpus_module.write_corpus(corpus_module.build_corpus(), tmp_path)
    instances = tmp_path / corpus_module.INSTANCES_DIRECTORY
    template = pydicom.dcmread(instances / _CT_FILES[0])
    slices = files.ct_files(
        _SCAN,
        head.Head(noise=0.0),
        series=corpus_module.CT_SERIES,
        frame=corpus_module.FRAME_OF_REFERENCE,
        template=template,
    )
    enhanced = files.multi_frame(slices, instance=corpus_module.CT_SERIES + ".1000")

    (written,) = _written_by_transform([enhanced])
    expected = _written_by_transform(slices)

    # Each frame is written as its slice is, air in the block but for the
    # kept brain, and the instance keeps its frames' functional groups.
    frames = written.pixel_array
    assert frames.shape == (len(slices), *_SCAN.shape)
    changed = 0
    for index, (frame, single) in enumerate(zip(frames, expected)):
        assert np.array_equal(frame, single.pixel_array), index
        source = pydicom.dcmread(pydicom.filebase.DicomBytesIO(slices[index]))
        changed += int(np.count_nonzero(frame != source.pixel_array))
    assert changed > 0
    assert len(written.PerFrameFunctionalGroupsSequence) == len(slices)


def _contour_points(dataset):
    return [
        [
            np.array([float(v) for v in contour.ContourData])
            for contour in item.get("ContourSequence", [])
        ]
        for item in dataset.ROIContourSequence
    ]


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_multi_frame_head_ct_gives_its_frame_the_block_of_its_slices(
    multi_frame, defaced
):
    _, outcomes, reasons, report = multi_frame
    _, single, _, _ = defaced

    # The RT Structure Set, RT Dose, and PET slices in its frame are cleaned
    # by the block that the run found from its frames, and written as they
    # are beside the same CT's slices.
    for name in (_STRUCTURE_SET, _DOSE[0], *_PET_SLICES):
        disposition, dataset = outcomes[name]
        assert disposition == "released", reasons[name]
        assert dataset.RecognizableVisualFeatures == "NO"
        if name == _STRUCTURE_SET:
            found, expected = _contour_points(dataset), _contour_points(single[name][1])
            assert len(found) == len(expected)
            for one, other in zip(found, expected):
                assert len(one) == len(other)
                for a, b in zip(one, other):
                    np.testing.assert_allclose(a, b)
        else:
            assert np.array_equal(dataset.pixel_array, single[name][1].pixel_array)
    assert report["face_review"]["ct_series"] == {
        "defaced": 1,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }
    # The QC pack draws the defaced instance's frames as a volume, by its
    # projection and surface render, more than its cine strip shows, so the
    # verdict on them releases it, each frame written as its slice is.
    disposition, dataset = outcomes[_HEAD_ENHANCED]
    assert disposition == "released", reasons[_HEAD_ENHANCED]
    assert dataset.RecognizableVisualFeatures == "NO"
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
    frames = dataset.pixel_array
    assert len(frames) > qc_previews.CINE_FRAMES
    for index, frame in enumerate(frames):
        assert np.array_equal(frame, single[_head_name(index)][1].pixel_array), index


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_multi_frame_pet_is_set_to_zero_activity_and_released(multi_frame):
    _, outcomes, reasons, _ = multi_frame
    disposition, dataset = outcomes[_PET_ENHANCED]

    # Each frame is written as its PET slice is, beside it in the run.
    assert disposition == "released", reasons[_PET_ENHANCED]
    assert dataset.RecognizableVisualFeatures == "NO"
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
    frames = dataset.pixel_array
    assert len(frames) == len(_PET_SLICES)
    for frame, (name, z) in zip(frames, _PET_SLICES.items()):
        assert np.array_equal(frame, outcomes[name][1].pixel_array), name
        assert not np.array_equal(frame, _pet_uptake(z)), name
    # The collection's Legacy Converted Enhanced PET, whose frames no
    # functional groups place, is still held.
    assert outcomes[_PET[2]] == ("held-for-review", None)
    assert (
        HeldVisualFeatures(VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME)
        in (reasons[_PET[2]])
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_head_ct_of_two_time_points_is_defaced_and_released(phased, defaced):
    _, outcomes, reasons, report = phased
    _, single, _, _ = defaced

    # Each time point's slices are written as the one time point's are,
    # and the QC pack draws each time point as a volume of its own, so the
    # verdict on them releases them all.
    count = sum(name.startswith("01-head-") and "-t" not in name for name in single)
    assert count > qc_previews.CINE_FRAMES
    for phase in range(2):
        for index in range(count):
            name = _head_name(index, phase)
            disposition, dataset = outcomes[name]
            assert disposition == "released", reasons[name]
            assert dataset.RecognizableVisualFeatures == "NO"
            assert np.array_equal(
                dataset.pixel_array, single[_head_name(index)][1].pixel_array
            ), name
    assert report["face_review"]["ct_series"] == {
        "defaced": 1,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }
    # Beside them, the RT Structure Set, RT Dose, and PET are cleaned as
    # beside one time point, since both keep the same brain.
    for name in (_STRUCTURE_SET, _DOSE[0], *_PET_SLICES):
        disposition, dataset = outcomes[name]
        assert disposition == "released", reasons[name]
        if name == _STRUCTURE_SET:
            found, expected = _contour_points(dataset), _contour_points(single[name][1])
            assert len(found) == len(expected)
            for one, other in zip(found, expected):
                assert len(one) == len(other)
                for a, b in zip(one, other):
                    np.testing.assert_allclose(a, b)
        else:
            assert np.array_equal(dataset.pixel_array, single[name][1].pixel_array)
