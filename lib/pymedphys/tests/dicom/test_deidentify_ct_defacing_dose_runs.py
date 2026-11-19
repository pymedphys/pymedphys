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
test_deidentify_ct_defacing_run.py makes them, whose release turns on an RT
Dose in the face block: one with too much dose there to set to zero, which
the reviewer chooses to have written as received or set to zero, beside a
block that is confirmed or not, and those that cannot be placed or hold no
grid. Every UID and value here is invented."""

# The runs of the head share _ct_defacing_runs.py with
# test_deidentify_ct_defacing_run.py,
# test_deidentify_ct_defacing_variant_runs.py, and
# test_deidentify_ct_defacing_review_runs.py, which CI runs in parts of their
# own, so that no part reaches the time limit. This module makes the runs that
# its own tests review. They were in the review module until each run, which
# writes the whole synthetic collection, made that part come within minutes of
# the limit at the NumPy and pandas minimum versions.

from __future__ import annotations

import json
import shutil

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import face_blocks, markers
from pymedphys._dicom.deidentify.qc_attestation import Face
from pymedphys._dicom.deidentify.qc_pack import QcPackError
from pymedphys._dicom.deidentify.reasons import (
    DoseChoice,
    HeldVisualFeatures,
    VisualFeaturesReason,
)

from . import _synthetic_head as head
from . import _synthetic_rtdose as rtdose
from ._ct_defacing_runs import (
    _DOSE,
    _DVH_ONLY,
    _HIGHEST,
    _UNPLACEABLE,
    _block,
    _dose,
    _head_name,
    _output_name,
    _reviewed,
    _reviewed_again,
    _second,
    _undefaced_listed,
)
from .test_deidentify_visual_features_option import CODE, _attest, _codes


# The reviewer saw no face in the dose levels of the grid placed too far for
# the block to be found on it, which the run does not set to zero.
_FAR_DOSE = "06-rtdose-huge-position.dcm"


@pytest.fixture(name="hot_own", scope="module")
def fixture_hot_own(reviewed_hot):
    return _second(reviewed_hot, name="ho", instance_faces={_FAR_DOSE: Face.ABSENT})


# With the RT Dose instances that cannot be placed or have no grid, which
# its run holds or releases alike, so that one run tests them all.
@pytest.fixture(name="reviewed_hot", scope="module")
def fixture_reviewed_hot():
    with _reviewed(first=(), dose=_dose(_HIGHEST), edges=True) as found:
        yield found


@pytest.fixture(name="hot", scope="module")
def fixture_hot(reviewed_hot):
    return _second(reviewed_hot, name="r")


# The reviewer chose to have the hot grid written as received, from its own
# dose levels, on which they saw no face.
@pytest.fixture(name="hot_as_written", scope="module")
def fixture_hot_as_written(reviewed_hot):
    return _second(
        reviewed_hot, name="aw", dose_choices={_DOSE[0]: DoseChoice.AS_WRITTEN}
    )


# The reviewer saw a face in the hot grid's dose levels, and chose to have it
# set to zero in the block anyway; then, given the later run's pack, saw none
# in its dose levels as set to zero, and chose nothing more.
@pytest.fixture(name="hot_set_to_zero", scope="module")
def fixture_hot_set_to_zero(reviewed_hot):
    return _second(
        reviewed_hot,
        name="z",
        dose_choices={_DOSE[0]: DoseChoice.SET_TO_ZERO},
        present=(_DOSE[0],),
    )


@pytest.fixture(name="hot_zeroed_reviewed", scope="module")
def fixture_hot_zeroed_reviewed(reviewed_hot, hot_set_to_zero):
    assert hot_set_to_zero
    return _second(_reviewed_again(reviewed_hot, "z"), name="t")


# The reviewer chose the same for a hot grid in the frame of a series whose
# eye ROIs disagree with its globes, without confirming the block.
@pytest.fixture(name="reviewed_eyes_away_hot", scope="module")
def fixture_reviewed_eyes_away_hot():
    with _reviewed(first=(), eyes_away=True, dose=_dose(_HIGHEST)) as found:
        yield found


@pytest.fixture(name="eyes_away_as_written", scope="module")
def fixture_eyes_away_as_written(reviewed_eyes_away_hot):
    return _second(
        reviewed_eyes_away_hot,
        name="ea",
        dose_choices={_DOSE[0]: DoseChoice.AS_WRITTEN},
    )


@pytest.fixture(name="eyes_away_set_to_zero", scope="module")
def fixture_eyes_away_set_to_zero(reviewed_eyes_away_hot):
    return _second(
        reviewed_eyes_away_hot,
        name="ez",
        dose_choices={_DOSE[0]: DoseChoice.SET_TO_ZERO},
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_an_rt_dose_not_set_to_zero_is_released_on_its_own_dose_levels(
    reviewed_hot, hot_own
):
    _, outcomes, reasons, report = hot_own
    disposition, dataset = outcomes[_FAR_DOSE]

    # Its own verdict was on its dose levels, which drew every frame as
    # written, so it is released as received, while the other grids that
    # cannot be placed, without one, are still held for their frame.
    assert disposition == "released", reasons[_FAR_DOSE]
    assert dataset.RecognizableVisualFeatures == "NO"
    source = pydicom.dcmread(reviewed_hot.instances / _FAR_DOSE)
    assert dataset.PixelData == source.PixelData
    held = HeldVisualFeatures(VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME)
    for name in set(_UNPLACEABLE) - {_FAR_DOSE}:
        assert outcomes[name] == ("held-for-review", None), name
        assert held in reasons[name], name
    section = report["face_review"]["undefaced_in_defaced_frame"]
    assert section["released"] == [_output_name(dataset)]


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_an_undefaced_instance_its_pack_does_not_show_gets_no_verdict(
    reviewed_hot,
):
    listed = _undefaced_listed(reviewed_hot)
    by_name = {name: position for position, name in reviewed_hot.names.items()}

    # No dose-levels preview draws a grid of direction cosines that PS3.3
    # does not allow, or of a spacing or offsets too great to sample, so the
    # pack lists each as not shown, and refuses a verdict of its own on it.
    # One placed too far for its block to be found on it is still drawn in
    # its own grid, which needs no place in the patient, so it is shown.
    assert set(_UNPLACEABLE) <= set(listed)
    far = _FAR_DOSE
    assert listed[far]["shown"]
    unshown = sorted(set(_UNPLACEABLE) - {far})
    assert not any(listed[name]["shown"] for name in unshown)
    directory = reviewed_hot.directory / "unshown"
    shutil.copytree(reviewed_hot.pack.parent, directory)
    for name in unshown:
        with pytest.raises(QcPackError, match="do not show all"):
            _attest(directory, {}, instance_faces={by_name[name]: Face.ABSENT})
    assert not (directory / "attestation.json").exists()


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_high_dose_in_the_block_holds_the_dose_as_received(hot):
    _, outcomes, reasons, report = hot
    held = HeldVisualFeatures(VisualFeaturesReason.DOSE_IN_FACE_BLOCK)

    # Setting it to zero would take more than the fraction of the grid's
    # greatest dose, which may be a target's, so it is held as it is; the
    # reviewed run held it so too, beside the defaced CT, so the verdict of
    # absent on it does not count.
    assert outcomes[_DOSE[0]] == ("held-for-review", None)
    assert reasons[_DOSE[0]] == {
        held,
        HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT),
    }
    counts = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert counts[held.reason.value] == 1


def _dose_checks(reviewed, name):
    """The dose checks of the run that :func:`_second` made in ``name``, by
    file name."""
    again = _reviewed_again(reviewed, name)
    document = json.loads(again.pack.read_text("utf-8"))
    return {again.names[check["position"]]: check for check in document["dose_checks"]}


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_hot_grid_is_listed_for_the_reviewer_to_choose(reviewed_hot, hot):
    _, _, _, report = hot
    first = json.loads(reviewed_hot.pack.read_text("utf-8"))["dose_checks"]

    # The reviewed run lists the grid that it held, with no choice and all
    # of its greatest dose in the block, and so does the run without one.
    assert [reviewed_hot.names[check["position"]] for check in first] == [_DOSE[0]]
    (check,) = first
    assert check["choice"] is None
    assert check["fraction"] == 1.0
    assert _dose_checks(reviewed_hot, "r")[_DOSE[0]]["choice"] is None
    assert report["face_review"]["rt_doses_in_face_block"] == {
        "held": 1,
        "released_as_written": [],
        "held_as_written": 0,
        "released_set_to_zero": [],
        "held_set_to_zero": 0,
    }


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_hot_grid_chosen_as_written_is_released_as_received(
    reviewed_hot, hot_as_written
):
    _, outcomes, reasons, report = hot_as_written
    disposition, dataset = outcomes[_DOSE[0]]

    # The verdict of absent was on its own dose levels, which drew it as
    # received, so it is released so, with the option's code, and none of
    # its dose is lost.
    assert disposition == "released", reasons[_DOSE[0]]
    assert dataset.RecognizableVisualFeatures == "NO"
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
    assert np.array_equal(dataset.pixel_array, _dose(_HIGHEST))
    check = _dose_checks(reviewed_hot, "aw")[_DOSE[0]]
    assert check["choice"] == "as-written"
    assert report["face_review"]["rt_doses_in_face_block"] == {
        "held": 0,
        "released_as_written": [_output_name(dataset)],
        "held_as_written": 0,
        "released_set_to_zero": [],
        "held_set_to_zero": 0,
    }
    assert _output_name(dataset) in report["released"]


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_hot_grid_chosen_to_set_to_zero_is_held_for_its_new_dose_levels(
    reviewed_hot, hot_set_to_zero
):
    _, outcomes, reasons, report = hot_set_to_zero

    # No reviewer has seen it set to zero, so whatever its verdict as
    # received, the face seen then, it is held for this run's dose levels.
    assert outcomes[_DOSE[0]] == ("held-for-review", None)
    assert reasons[_DOSE[0]] == {
        HeldVisualFeatures(VisualFeaturesReason.DOSE_SET_TO_ZERO_ON_REVIEW)
    }
    check = _dose_checks(reviewed_hot, "z")[_DOSE[0]]
    assert check["choice"] == "set-to-zero"
    assert check["fraction"] == 1.0
    assert report["face_review"]["rt_doses_in_face_block"]["held_set_to_zero"] == 1
    counts = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert counts[VisualFeaturesReason.DOSE_SET_TO_ZERO_ON_REVIEW.value] == 1


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_hot_grid_set_to_zero_is_released_on_a_verdict_on_it_so(
    hot_zeroed_reviewed,
):
    slices, outcomes, reasons, report = hot_zeroed_reviewed
    block = _block(slices)
    disposition, dataset = outcomes[_DOSE[0]]

    # The second review saw it set to zero, and kept the choice, which its
    # pack recorded, so it is released set to zero beyond the fraction.
    assert disposition == "released", reasons[_DOSE[0]]
    assert dataset.RecognizableVisualFeatures == "NO"
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
    points = rtdose.voxel_positions(dataset)
    written = dataset.pixel_array
    source = _dose(_HIGHEST)
    inside = block.contains(points)
    assert np.array_equal(written[~inside], source[~inside])
    floor = head.GLOBE_Z + face_blocks.CAVITY_FLOOR
    assert np.all(written[inside & (points[..., 2] <= floor)] == 0)
    values = head.hounsfield(points)
    brain = inside & (values == head.BRAIN) & (points[..., 2] > floor + 5)
    assert brain.any() and np.array_equal(written[brain], source[brain])
    assert report["face_review"]["rt_doses_in_face_block"] == {
        "held": 0,
        "released_as_written": [],
        "held_as_written": 0,
        "released_set_to_zero": [_output_name(dataset)],
        "held_set_to_zero": 0,
    }


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_hot_grid_chosen_as_written_needs_no_confirmed_block(eyes_away_as_written):
    _, outcomes, reasons, _ = eyes_away_as_written
    disposition, dataset = outcomes[_DOSE[0]]

    # The block cleans nothing of a grid written as received, so the eyes
    # that disagree with it, which hold the head's slices, do not hold it.
    assert outcomes[_head_name(0)][0] == "held-for-review"
    assert disposition == "released", reasons[_DOSE[0]]
    assert np.array_equal(dataset.pixel_array, _dose(_HIGHEST))


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_hot_grid_set_to_zero_by_an_unconfirmed_block_waits_for_it(
    eyes_away_set_to_zero,
):
    _, outcomes, reasons, _ = eyes_away_set_to_zero

    # A wrong block would leave the face in the grid set to zero by it.
    assert outcomes[_DOSE[0]] == ("held-for-review", None)
    assert reasons[_DOSE[0]] == {
        HeldVisualFeatures(VisualFeaturesReason.DOSE_SET_TO_ZERO_ON_REVIEW),
        HeldVisualFeatures(VisualFeaturesReason.EYES_DISAGREE_WITH_ROIS),
    }


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_grid_that_cannot_be_placed_is_held_as_received(hot):
    _, outcomes, reasons, _ = hot
    held = HeldVisualFeatures(VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME)

    # Its direction cosines are not allowed, or it lies too far to place,
    # so it is not set to zero, and stays held for its frame, in this run as
    # in the reviewed one.
    for name in _UNPLACEABLE:
        assert outcomes[name] == ("held-for-review", None), name
        assert held in reasons[name], name


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_an_rt_dose_of_dose_volume_histograms_alone_is_not_held_for_its_frame(
    hot,
):
    _, outcomes, reasons, _ = hot

    # Without a grid, it shows no face, in a defaced frame or not, so it
    # needs no verdict, and is released, as in the reviewed run, which gave
    # none.
    assert not any(isinstance(r, HeldVisualFeatures) for r in reasons[_DVH_ONLY])
    disposition, dataset = outcomes[_DVH_ONLY]
    assert disposition == "released", reasons[_DVH_ONLY]
    assert "PixelData" not in dataset
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
