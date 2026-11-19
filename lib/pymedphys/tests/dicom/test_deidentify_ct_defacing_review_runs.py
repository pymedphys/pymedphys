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

"""Runs of the analytic head and the synthetic collection, as
test_deidentify_ct_defacing_run.py makes them, whose release turns on more
than a series' face verdict: a target kept in the block, or beyond the
slices; Clean Pixel Data reviewed with the option; and an RT Dose that a
block whose eyes disagree with the ROIs drawn cleaned. The runs of an RT
Dose in the face block are in test_deidentify_ct_defacing_dose_runs.py.
Every UID and value here is invented."""

from __future__ import annotations

import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest, shapely

from pymedphys._dicom.deidentify import face_blocks, markers
from pymedphys._dicom.deidentify.policy import CLEAN_PIXEL_DATA
from pymedphys._dicom.deidentify.qc_attestation import Face
from pymedphys._dicom.deidentify.reasons import (
    HeldPixelData,
    HeldVisualFeatures,
    PixelDataReason,
    VisualFeaturesReason,
)
from pymedphys._dicom.deidentify.target_hulls import TargetHull
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _synthetic_head as head
from . import _synthetic_rtdose as rtdose
from ._ct_defacing_runs import (
    _BEYOND_TARGET,
    _DOSE,
    _IN_FRAME,
    _IN_THE_BLOCK,
    _KEPT_TARGET,
    _KEPT_TARGET_HALF,
    _LOW,
    _PET_GRID,
    _PET_SLICES,
    _ROIS,
    _SCAN,
    _STRUCTURE_SET,
    _TARGET_NAME,
    _UNPLACED,
    _block,
    _contours,
    _dose,
    _elsewhere_name,
    _head_name,
    _pet_points,
    _pet_uptake,
    _region,
    _reviewed,
    _runs,
    _second,
    _undefaced_listed,
    _written_as_air,
)
from .test_deidentify_visual_features_option import CODE, _codes


@pytest.fixture(name="reviewed_with_pixel_data", scope="module")
def fixture_reviewed_with_pixel_data():
    with _reviewed(first=(CLEAN_PIXEL_DATA,)) as found:
        yield found


# The first RT Dose is set to zero in the block of the head's slices, whose
# eyes disagree with the ROIs drawn, and refers to a slice of the head's
# second series, defaced in a frame of its own; the reviewer saw no face in
# its own previews, and the block is left unconfirmed, or confirmed.
@pytest.fixture(name="reviewed_elsewhere", scope="module")
def fixture_reviewed_elsewhere():
    with _reviewed(first=(), eyes_away=True, dose=_dose(_LOW), elsewhere=True) as found:
        yield found


@pytest.fixture(name="elsewhere_own", scope="module")
def fixture_elsewhere_own(reviewed_elsewhere):
    return _second(
        reviewed_elsewhere, name="eu", instance_faces={_DOSE[0]: Face.ABSENT}
    )


@pytest.fixture(name="elsewhere_confirmed", scope="module")
def fixture_elsewhere_confirmed(reviewed_elsewhere):
    return _second(
        reviewed_elsewhere,
        name="ec",
        confirmed=True,
        instance_faces={_DOSE[0]: Face.ABSENT},
    )


# Marked absent as the run wrote them, around the target that it kept.
@pytest.fixture(name="targeted", scope="module")
def fixture_targeted():
    with _runs(first=(), target="kept", dose=_dose(_LOW)) as found:
        yield found


@pytest.fixture(name="beyond_slices", scope="module")
def fixture_beyond_slices():
    with _runs(target="beyond") as found:
        yield found


@pytest.fixture(name="with_pixel_data", scope="module")
def fixture_with_pixel_data(reviewed_with_pixel_data):
    return _second(reviewed_with_pixel_data, CLEAN_PIXEL_DATA, name="p")


@pytest.fixture(name="accepted", scope="module")
def fixture_accepted(reviewed_with_pixel_data):
    return _second(reviewed_with_pixel_data, CLEAN_PIXEL_DATA, name="a", accepted=True)


# A region of the reviewer's own, within the head on each of its slices.
_REVISED = TextBox(46, 36, 51, 45)


@pytest.fixture(name="revised", scope="module")
def fixture_revised(reviewed_with_pixel_data):
    return _second(
        reviewed_with_pixel_data, CLEAN_PIXEL_DATA, name="v", revised=_REVISED
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_verdict_of_its_own_keeps_the_block_that_cleaned_it_unconfirmed(
    reviewed_elsewhere, elsewhere_own, elsewhere_confirmed
):
    held = HeldVisualFeatures(VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME)
    eyes = HeldVisualFeatures(VisualFeaturesReason.EYES_DISAGREE_WITH_ROIS)
    document = json.loads(reviewed_elsewhere.pack.read_text("utf-8"))
    (entry,) = (
        each
        for each in document["instances"]
        if reviewed_elsewhere.names[each["position"]] == _DOSE[0]
    )
    assert entry["disposition"] == "held-for-review"
    assert any(held.reason.value in reason for reason in entry["reasons"])
    assert _undefaced_listed(reviewed_elsewhere)[_DOSE[0]]["shown"]
    _, outcomes, reasons, _ = elsewhere_own

    # Its own verdict decides the slice that it refers to in the other
    # frame, but the block of its own frame set it to zero, so it waits for
    # that block's confirmation, as any instance that block cleans does,
    # while the other series, whose eyes no ROI contradicts, is released.
    assert outcomes[_elsewhere_name(0)][0] == "released"
    assert outcomes[_DOSE[0]] == ("held-for-review", None)
    assert eyes in reasons[_DOSE[0]] and held not in reasons[_DOSE[0]]
    _, outcomes, reasons, _ = elsewhere_confirmed
    disposition, dataset = outcomes[_DOSE[0]]
    assert disposition == "released", reasons[_DOSE[0]]
    assert dataset.RecognizableVisualFeatures == "NO"
    source = pydicom.dcmread(reviewed_elsewhere.instances / _DOSE[0])
    assert dataset.PixelData != source.PixelData


def _near_target(points):
    """Whether each of the head's CT pixels at ``points`` has a square, on
    its slice, that meets the kept target's region, read from its contours:
    those that the run must not write as air."""
    reach = _KEPT_TARGET_HALF + _SCAN.spacing[0] / 2
    heights = [contour[0, 2] for contour in _KEPT_TARGET[1]]
    return (
        (np.abs(points[..., 0] - _IN_THE_BLOCK[0]) <= reach)
        & (np.abs(points[..., 1] - _IN_THE_BLOCK[1]) <= reach)
        & (points[..., 2] >= min(heights))
        & (points[..., 2] <= max(heights))
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_head_ct_with_a_target_in_the_block_is_defaced_around_it(targeted):
    slices, outcomes, reasons, report = targeted
    block = _block(slices)
    kept = 0

    # The run writes air in the block but where the target lies, and the
    # verdict of absent, on the slices as written, releases them.
    for index, data in enumerate(slices):
        disposition, dataset = outcomes[_head_name(index)]
        assert disposition == "released", reasons[_head_name(index)]
        assert dataset.RecognizableVisualFeatures == "NO"
        assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
        before = pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))
        source = pydicom.pixels.apply_rescale(
            pydicom.pixels.pixel_array(before), before
        )
        written = pydicom.pixels.apply_rescale(
            pydicom.pixels.pixel_array(dataset), dataset
        )
        points = _SCAN.points(index)
        inside = block.contains(points)
        near = _near_target(points)
        assert np.array_equal(written[~inside], source[~inside]), index
        assert np.array_equal(written[near], source[near]), index
        assert np.all((written[inside] == -1000) | (written[inside] == source[inside]))
        # Below the kept brain's floor, all else in the block is air.
        floor = head.GLOBE_Z + face_blocks.CAVITY_FLOOR
        if points[0, 0, 2] <= floor:
            assert np.all(written[inside & ~near] == -1000), index
        kept += int(np.count_nonzero(inside & near & (source != -1000)))
    assert kept > 0
    assert report["face_review"]["ct_series"] == {
        "defaced": 1,
        "defaced_around_targets": 1,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_the_structure_set_is_cut_around_a_target_in_the_block(targeted):
    slices, outcomes, reasons, _ = targeted
    block = _block(slices)
    disposition, dataset = outcomes[_STRUCTURE_SET]

    assert disposition == "released", reasons[_STRUCTURE_SET]
    assert dataset.RecognizableVisualFeatures == "NO"
    written = _contours(dataset, "kept")
    # The target is written as received, all of it in the block.
    for source, got in zip(_KEPT_TARGET[1], written[_TARGET_NAME], strict=True):
        assert block.contains(source).all()
        assert np.allclose(got, source, atol=1e-4)
    # On the target's slices, the outline and the right eye lose exactly what
    # the CT writes as air, and so keep the part of them that the target
    # reaches.
    target = shapely.geometry.box(
        _IN_THE_BLOCK[0] - _KEPT_TARGET_HALF,
        _IN_THE_BLOCK[1] - _KEPT_TARGET_HALF,
        _IN_THE_BLOCK[0] + _KEPT_TARGET_HALF,
        _IN_THE_BLOCK[1] + _KEPT_TARGET_HALF,
    )
    heights = {contour[0, 2] for contour in _KEPT_TARGET[1]}
    checked = 0
    for name in ("External", "Eye_R"):
        for source in _ROIS[name][1]:
            z = source[0, 2]
            if z not in heights:
                continue
            got = _region([each for each in written[name] if each[0, 2] == z])
            whole = shapely.geometry.Polygon(source[:, :2])
            expected = whole.difference(_written_as_air(outcomes, block, z))
            assert got.symmetric_difference(expected).area < 1e-6 * whole.area
            assert got.area < whole.area, (name, z)
            reached = whole.intersection(target)
            assert reached.area > 0, (name, z)
            assert got.intersection(reached).area == pytest.approx(
                reached.area, rel=1e-4
            )
            checked += 1
    assert checked > 0


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_dose_and_activity_within_a_target_in_the_block_are_kept(targeted):
    slices, outcomes, reasons, _ = targeted
    block = _block(slices)
    target = TargetHull.of(np.concatenate(_KEPT_TARGET[1]))

    disposition, dataset = outcomes[_DOSE[0]]
    assert disposition == "released", reasons[_DOSE[0]]
    points = rtdose.voxel_positions(dataset)
    written = dataset.pixel_array
    source = _dose(_LOW)
    within = target.contains(points).reshape(points.shape[:-1])
    assert within.any() and block.contains(points[within]).all()
    assert np.array_equal(written[within], source[within])
    inside = block.contains(points)
    floor = head.GLOBE_Z + face_blocks.CAVITY_FLOOR
    assert np.all(written[inside & ~within & (points[..., 2] <= floor)] == 0)
    # The PET slice through the target keeps its activity there, and the one
    # above it is set to zero as without it.
    kept = 0
    for name, z in _PET_SLICES.items():
        disposition, dataset = outcomes[name]
        assert disposition == "released", reasons[name]
        points = _pet_points(z)
        within = target.contains(points).reshape(points.shape[:-1])
        expected = _pet_uptake(z)
        assert np.array_equal(dataset.pixel_array[within], expected[within]), name
        if z <= floor:
            low = block.contains(points) & ~within
            assert np.all(dataset.pixel_array[low] == 0), name
        kept += int(np.count_nonzero(within & (expected > 0)))
    assert kept > 0


def test_a_target_in_the_block_beyond_the_slices_holds_the_head_ct(beyond_slices):
    slices, outcomes, reasons, report = beyond_slices
    held = HeldVisualFeatures(VisualFeaturesReason.TARGET_IN_FACE_BLOCK)
    block = _block(slices)

    # It is drawn in the block past the front of the slices, where no image
    # shows it, so the run cannot keep it within the images: the series is
    # not defaced, and is held.
    for contour in _BEYOND_TARGET[1]:
        assert block.contains(contour).all()
    for index in range(len(slices)):
        assert outcomes[_head_name(index)] == ("held-for-review", None), index
        assert held in reasons[_head_name(index)]
    assert report["face_review"]["ct_series"] == {
        "defaced": 0,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [
            {"reason": "target-in-block", "count": 1},
            {"reason": "unreadable", "count": _UNPLACED},
        ],
    }
    counts = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert counts["target-in-face-block"] == len(slices)
    # With no series defaced, the RT instances marked absent are released,
    # but for the RT Dose that its release gate holds for review, and the
    # structure set is written as received.
    for name in _IN_FRAME:
        assert not any(isinstance(r, HeldVisualFeatures) for r in reasons[name])
        if name != _DOSE[1]:
            disposition, dataset = outcomes[name]
            assert disposition == "released", name
            assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
    _, dataset = outcomes[_STRUCTURE_SET]
    assert all(
        contours is not None for contours in _contours(dataset, "beyond").values()
    )


@pytest.mark.deid_requirement("PS3.15-E.3.1-01", "PS3.15-E.3.2-01")
def test_with_clean_pixel_data_the_head_ct_is_held_for_its_pixel_data(
    with_pixel_data,
):
    slices, outcomes, reasons, report = with_pixel_data

    # Marked absent as defaced and blacked out, as the second run writes it,
    # but its text regions still await review.
    for index in range(len(slices)):
        name = _head_name(index)
        assert outcomes[name] == ("held-for-review", None), index
        assert HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT) in reasons[name]
        assert not any(isinstance(r, HeldVisualFeatures) for r in reasons[name])
    assert report["face_review"]["ct_series"] == {
        "defaced": 1,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }


@pytest.mark.deid_requirement("PS3.15-E.3.1-01", "PS3.15-E.3.2-01")
def test_with_both_options_reviewed_the_head_ct_is_released_with_both(accepted):
    slices, outcomes, reasons, report = accepted
    block = _block(slices)
    corner = np.zeros(_SCAN.shape, dtype=bool)
    corner[0:2, 0:3] = True

    # The reviewer accepted the regions and saw the slices as the first run
    # wrote them, defaced and blacked out. The second run writes the same
    # pixel data, from the pack's regions without the finder, so each slice
    # is released with both options' codes and both attributes NO.
    for index, data in enumerate(slices):
        name = _head_name(index)
        disposition, dataset = outcomes[name]
        assert disposition == "released", (index, reasons[name])
        assert dataset.BurnedInAnnotation == "NO"
        assert dataset.RecognizableVisualFeatures == "NO"
        assert _codes(dataset)[-3:] == [markers.PROFILE_CODE, "113101", CODE]
        before = pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))
        source = pydicom.pixels.pixel_array(before)
        written = pydicom.pixels.pixel_array(dataset)
        inside = block.contains(_SCAN.points(index))
        untouched = ~inside & ~corner
        assert np.array_equal(written[untouched], source[untouched]), index
        assert len(np.unique(written[corner])) == 1, index
    assert report["face_review"]["ct_series"] == {
        "defaced": 1,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }
    assert report["redaction_review"] is not None


@pytest.mark.deid_requirement("PS3.15-E.3.1-01", "PS3.15-E.3.2-01")
def test_a_revised_region_that_changes_a_defaced_slice_holds_it_for_its_face(
    revised,
):
    slices, outcomes, reasons, report = revised
    region = np.zeros(_SCAN.shape, dtype=bool)
    region[_REVISED.top : _REVISED.bottom, _REVISED.left : _REVISED.right] = True

    # The face verdict is on the pixel data that the first run wrote, without
    # the reviewer's region. The region covers more than the fill, so the
    # second run writes other pixel data, which the verdict does not cover:
    # each slice is held for its face, and not for its text, which the
    # reviewer approved.
    for index, data in enumerate(slices):
        name = _head_name(index)
        before = pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))
        source = pydicom.pixels.pixel_array(before)
        assert np.any(source[region] != source.min()), index
        assert outcomes[name] == ("held-for-review", None), index
        assert reasons[name] == {
            HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA)
        }, index
    assert report["face_review"]["ct_series"] == {
        "defaced": 1,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_with_both_options_reviewed_the_head_pet_is_released_with_both(accepted):
    slices, outcomes, reasons, _ = accepted
    block = _block(slices)
    corner = np.zeros(_PET_GRID["shape"], dtype=bool)
    corner[0:2, 0:3] = True

    # The reviewer accepted the regions of each PET slice, set to zero
    # activity in the block, so the second run blacks out the pack's regions
    # and sets the block to zero again, writing the pixel data the reviewer
    # saw, and releases each slice with both options' codes.
    for name, z in _PET_SLICES.items():
        disposition, dataset = outcomes[name]
        assert disposition == "released", (name, reasons[name])
        assert dataset.BurnedInAnnotation == "NO"
        assert dataset.RecognizableVisualFeatures == "NO"
        assert _codes(dataset)[-3:] == [markers.PROFILE_CODE, "113101", CODE]
        source, written = _pet_uptake(z), dataset.pixel_array
        inside = block.contains(_pet_points(z))
        untouched = ~inside & ~corner
        assert np.array_equal(written[untouched], source[untouched]), name
        assert np.all((written[inside] == 0) | (written[inside] == source[inside]))
        assert (written[inside] != source[inside]).any(), name
        assert len(np.unique(written[corner])) == 1, name
