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

"""A run under Clean Recognizable Visual Features that defaces a CT series
of the analytic head, beside the synthetic collection's RT Structure Set and
RT Dose in the same Frame of Reference, one RT Dose replaced by a grid over
the head. Every UID and value here is invented."""

from __future__ import annotations

import contextlib
import copy
import json
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import dose_defacing, face_blocks, markers, run
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.face_review import FaceReview, read_face_review
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.policy import CLEAN_PIXEL_DATA, compose_policy
from pymedphys._dicom.deidentify.qc_pack import new_reference
from pymedphys._dicom.deidentify.qc_attestation import Face
from pymedphys._dicom.deidentify.reasons import (
    HeldPixelData,
    HeldVisualFeatures,
    PixelDataReason,
    VisualFeaturesReason,
)
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import ReleaseReason

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from . import _synthetic_rtdose as rtdose
from .test_deidentify_visual_features_option import (
    CODE,
    KEY,
    _attest,
    _codes,
    _CornerFinder,
    _policy,
)

# As coarse and short as the face block's finder allows, since every slice
# goes through two runs.
_SCAN = head.axial(
    spacing=2.5, thickness=5.0, extent=((-100, 100), (-130, 110), (-30, 110))
)
_CT_FILES = ("01-ct-1.dcm", "02-ct-2.dcm", corpus_module.SEQUESTERED_FILE)
_STRUCTURE_SET = "04-rtstruct.dcm"
_DOSE = ("06-rtdose.dcm", "07-rtdose-review.dcm")
_PET = ("15-pet.dcm", "16-pet-enhanced.dcm", "17-pet-legacy-enhanced.dcm")
_IN_FRAME = (_STRUCTURE_SET, *_DOSE, *_PET)
_UNDEFACED = (_STRUCTURE_SET, *_PET)
_IN_THE_BLOCK = (-32.0, -76.0, 20.0)
# A dose grid over the head, on the CT's pixels and every other slice, with
# its greatest dose behind the head, and DOSE_FRACTION of it, or all of it,
# everywhere else.
_GRID = {
    "position": (-100.0, -130.0, -30.0),
    "spacing": (5.0, 5.0),
    "offsets": tuple(10.0 * k for k in range(15)),
}
_HIGHEST = 20000
_LOW = round(dose_defacing.DOSE_FRACTION * _HIGHEST)


def _dose(low):
    stored = np.full((15, 49, 41), low, dtype=np.uint32)
    # Rows from y = -130 mm at 5 mm: those from 50 mm are behind the head's
    # centre.
    stored[:, 36:, :] = _HIGHEST
    return stored


def _head_name(index):
    return f"01-head-{index:03d}.dcm"


# Direction cosines that PS3.3 C.7.6.2.1.1 does not allow, by file name.
_UNPLACEABLE = {
    "06-rtdose-zero-cosines.dcm": (0.0,) * 6,
    "06-rtdose-non-unit-cosines.dcm": (2.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    "06-rtdose-non-orthogonal-cosines.dcm": (1.0, 0.0, 0.0, 0.6, 0.8, 0.0),
}
_DVH_ONLY = "06-rtdose-dvh-only.dcm"
# Pixel Data and the Image Plane and Image Pixel modules' attributes, which
# Table A.18.3-1 of PS3.3 requires only of a grid.
_GRID_ONLY = (
    "PixelData",
    "ImagePositionPatient",
    "ImageOrientationPatient",
    "PixelSpacing",
    "SliceThickness",
    "GridFrameOffsetVector",
    "FrameIncrementPointer",
    "NumberOfFrames",
    "Rows",
    "Columns",
    "SamplesPerPixel",
    "PhotometricInterpretation",
    "BitsAllocated",
    "BitsStored",
    "HighBit",
    "PixelRepresentation",
    "DoseGridScaling",
)


def _dvh_only(grid, instance):
    """The corpus' RT Dose without its grid, as one of dose-volume
    histograms alone is."""
    dataset = copy.deepcopy(grid)
    for keyword in _GRID_ONLY:
        if keyword in dataset:
            delattr(dataset, keyword)
    dataset.SOPInstanceUID = instance
    dataset.file_meta.MediaStorageSOPInstanceUID = instance
    return files.written(dataset)


@contextlib.contextmanager
def _runs(*others, first=None, target=False, without_ct=False, dose=None, edges=False):
    """Run the collection, with its CT slices replaced by the head's, and
    its first RT Dose by a grid over the head of ``dose`` where given, with
    the RT Dose instances of :data:`_UNPLACEABLE` and :data:`_DVH_ONLY` in
    its series if ``edges``, under
    ``basic``, or under the option and ``first`` with a face review that
    gives no verdicts; attest the pack with the head's series, and those of
    the RT Structure Set, RT Dose, and PET in its frame, marked absent; and
    run it again under the option and ``others``, without the head's slices
    if ``without_ct``."""
    corpus = corpus_module.build_corpus()
    directory = Path(tempfile.mkdtemp(prefix="d"))
    try:
        corpus_module.write_corpus(corpus, directory)
        instances = directory / corpus_module.INSTANCES_DIRECTORY
        template = pydicom.dcmread(instances / _CT_FILES[0])
        for name in _CT_FILES:
            (instances / name).unlink()
        slices = files.ct_files(
            _SCAN,
            head.Head(noise=0.0),
            series=corpus_module.CT_SERIES,
            frame=corpus_module.FRAME_OF_REFERENCE,
            template=template,
        )
        for index, data in enumerate(slices):
            (instances / _head_name(index)).write_bytes(data)
        if dose is not None:
            grid = pydicom.dcmread(instances / _DOSE[0])
            (instances / _DOSE[0]).write_bytes(
                files.dose(
                    dose,
                    **_GRID,
                    frame=corpus_module.FRAME_OF_REFERENCE,
                    instance=grid.SOPInstanceUID,
                    template=grid,
                )
            )
            if edges:
                for index, (name, orientation) in enumerate(_UNPLACEABLE.items()):
                    (instances / name).write_bytes(
                        files.dose(
                            dose,
                            **_GRID,
                            orientation=orientation,
                            frame=corpus_module.FRAME_OF_REFERENCE,
                            instance=f"{grid.SOPInstanceUID}.{index + 1}",
                            template=grid,
                        )
                    )
                (instances / _DVH_ONLY).write_bytes(
                    _dvh_only(grid, f"{grid.SOPInstanceUID}.9")
                )
        if target:
            rtss = pydicom.dcmread(instances / _STRUCTURE_SET)
            (instances / _STRUCTURE_SET).write_bytes(
                files.structure_set(
                    [("PTV", files.square(_IN_THE_BLOCK))],
                    frame=corpus_module.FRAME_OF_REFERENCE,
                    template=rtss,
                )
            )
        reviewed = run.run(
            run.discover(instances),
            directory / "r1",
            InstanceTransform(compose_policy("basic"), KEY, unvalidated_policy=True)
            if first is None
            else _transform(
                first, FaceReview(new_reference(), frozenset(), frozenset())
            ),
            ReleaseGate(),
            qc_destination=directory / "qc1",
        )
        entries = json.loads(reviewed.qc_pack.read_text("utf-8"))
        names = {e["position"]: Path(e["source"]).name for e in entries["instances"]}
        marked = [
            s["positions"][0]
            for s in entries["series"]
            if any(
                names[p].startswith("01-head") or names[p] in _IN_FRAME
                for p in s["positions"]
            )
        ]
        _attest(reviewed.qc_pack.parent, dict.fromkeys(marked, Face.ABSENT))
        if without_ct:
            for index in range(len(slices)):
                (instances / _head_name(index)).unlink()
        transform = _transform(others, read_face_review(reviewed.qc_pack.parent))
        second = run.run(
            run.discover(instances),
            directory / "r2",
            transform,
            ReleaseGate(),
            qc_destination=directory / "qc2",
            reporter=transform.reporter,
        )
        pack = json.loads(second.qc_pack.read_text("utf-8"))["instances"]
        outcomes = {
            Path(entry["source"]).name: (
                entry["disposition"],
                None
                if entry.get("output") is None
                else pydicom.dcmread(directory / "r2" / entry["output"]),
            )
            for entry in pack
        }
        reasons = {
            Path(entry["source"]).name: set(outcome.reasons)
            for entry in pack
            for outcome in second.outcomes
            if outcome.position == entry["position"]
        }
        report = json.loads((directory / "r2" / "release-report.json").read_text())
        yield slices, outcomes, reasons, report
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _transform(options, face_review):
    return InstanceTransform(
        _policy(*options),
        KEY,
        face_review=face_review,
        finder=_CornerFinder() if CLEAN_PIXEL_DATA in options else None,
        unvalidated_policy=True,
    )


@pytest.fixture(name="defaced", scope="module")
def fixture_defaced():
    with _runs(first=(), dose=_dose(_LOW)) as found:
        yield found


@pytest.fixture(name="edges", scope="module")
def fixture_edges():
    with _runs(first=(), dose=_dose(_LOW), edges=True) as found:
        yield found


@pytest.fixture(name="hot", scope="module")
def fixture_hot():
    with _runs(first=(), dose=_dose(_HIGHEST)) as found:
        yield found


@pytest.fixture(name="as_received", scope="module")
def fixture_as_received():
    with _runs() as found:
        yield found


@pytest.fixture(name="targeted", scope="module")
def fixture_targeted():
    with _runs(target=True) as found:
        yield found


@pytest.fixture(name="without_ct", scope="module")
def fixture_without_ct():
    with _runs(first=(), without_ct=True, dose=_dose(_LOW)) as found:
        yield found


@pytest.fixture(name="with_pixel_data", scope="module")
def fixture_with_pixel_data():
    with _runs(CLEAN_PIXEL_DATA, first=(CLEAN_PIXEL_DATA,)) as found:
        yield found


def _block(slices):
    records = {
        index: InstanceRecord.from_file(data) for index, data in enumerate(slices)
    }
    outcomes = face_blocks.find_face_blocks(records, lambda index: slices[index])
    (outcome,) = list(outcomes.values())
    return outcome.block


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_head_ct_marked_absent_as_defaced_is_released_defaced_with_the_option(
    defaced,
):
    slices, outcomes, _, _ = defaced
    block = _block(slices)
    changed = kept = 0

    for index, data in enumerate(slices):
        disposition, dataset = outcomes[_head_name(index)]
        assert disposition == "released", index
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
        values = head.hounsfield(points)
        # Outside the block, nothing changes; within it, each voxel is air
        # or as it was, the eyes are air, and the brain above the orbits,
        # which the skull encloses there, is kept.
        assert np.array_equal(written[~inside], source[~inside]), index
        assert np.all((written[inside] == -1000) | (written[inside] == source[inside]))
        eye = inside & np.isin(values, [head.VITREOUS, head.LENS])
        assert np.all(written[eye] == -1000), index
        floor = head.GLOBE_Z + face_blocks.CAVITY_FLOOR
        brain = inside & (values == head.BRAIN) & (points[..., 2] > floor)
        assert np.array_equal(written[brain], source[brain]), index
        kept += int(np.count_nonzero(brain))
        changed += int(np.count_nonzero(written != source))
    assert changed > 0 and kept > 0


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_head_ct_marked_absent_as_received_is_held_where_defaced(
    as_received, defaced
):
    slices, outcomes, reasons, report = as_received
    _, written, _, _ = defaced
    held = HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA)
    changed = 0

    # The reviewer saw the slices as received. A slice that the run writes
    # defaced is not what the verdict was of, so it is held; one with
    # nothing in the block is written as received, and released.
    for index, data in enumerate(slices):
        name = _head_name(index)
        before = pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))
        if written[name][1].PixelData != before.PixelData:
            changed += 1
            assert outcomes[name] == ("held-for-review", None), index
            assert reasons[name] == {held}, index
        else:
            assert outcomes[name][0] == "released", index
            assert _codes(outcomes[name][1])[-2:] == [markers.PROFILE_CODE, CODE]
    assert 0 < changed < len(slices)
    assert report["face_review"]["ct_series"] == {"defaced": 1, "not_defaced": []}
    counts = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert counts[VisualFeaturesReason.OTHER_PIXEL_DATA.value] == changed


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
@pytest.mark.parametrize("fixture", ["defaced", "as_received"])
def test_rt_instances_in_the_defaced_frame_are_held_whatever_their_verdict(
    fixture, request
):
    _, outcomes, reasons, report = request.getfixturevalue(fixture)
    held = HeldVisualFeatures(VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME)
    # Where the reviewed run defaced their frame too, it held them for it,
    # so the verdict of absent on them does not count either.
    expected = {held}
    if fixture == "defaced":
        expected.add(HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT))

    # Marked absent, the RT Structure Set's outline and the PET in the
    # head's Frame of Reference still trace the face that the defaced CT no
    # longer shows, so neither is released, and nothing claims the option
    # for them because their CT was defaced.
    for name in _UNDEFACED:
        assert outcomes[name] == ("held-for-review", None), name
        assert reasons[name] == expected, name
    assert report["face_review"]["ct_series"] == {"defaced": 1, "not_defaced": []}
    counts = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert counts[held.reason.value] == len(_UNDEFACED)


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
@pytest.mark.parametrize("fixture", ["defaced", "as_received"])
def test_rt_dose_behind_the_block_is_released_unchanged(fixture, request):
    _, outcomes, reasons, _ = request.getfixturevalue(fixture)
    names = _DOSE[1:] if fixture == "defaced" else _DOSE

    # The synthetic collection's grids lie behind the block, so nothing of
    # them is set to zero, and the verdicts of absent on them, on the pixel
    # data written, release them. The RT Dose for review is held by its
    # release gate alone.
    for name in names:
        assert not any(isinstance(r, HeldVisualFeatures) for r in reasons[name])
        if name == _DOSE[1]:
            assert outcomes[name] == ("held-for-review", None)
            assert reasons[name]
            assert all(isinstance(r, ReleaseReason) for r in reasons[name])
        else:
            disposition, dataset = outcomes[name]
            assert disposition == "released", name
            assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_low_dose_in_the_block_is_set_to_zero_there_and_released(defaced):
    slices, outcomes, reasons, _ = defaced
    block = _block(slices)
    disposition, dataset = outcomes[_DOSE[0]]

    assert disposition == "released", reasons[_DOSE[0]]
    assert dataset.RecognizableVisualFeatures == "NO"
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
    points = rtdose.voxel_positions(dataset)
    written = dataset.pixel_array
    source = _dose(_LOW)
    inside = block.contains(points)
    # Outside the block, the dose is as it was; within it, zero, but for the
    # brain above the floor, which defacing keeps on the CT slices that each
    # voxel lies on.
    assert np.array_equal(written[~inside], source[~inside])
    assert np.all((written[inside] == 0) | (written[inside] == source[inside]))
    floor = head.GLOBE_Z + face_blocks.CAVITY_FLOOR
    assert np.all(written[inside & (points[..., 2] <= floor)] == 0)
    values = head.hounsfield(points)
    brain = inside & (values == head.BRAIN) & (points[..., 2] > floor + 5)
    assert brain.any() and np.array_equal(written[brain], source[brain])
    assert np.count_nonzero(written[inside] == 0) > np.count_nonzero(brain)


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


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_grid_whose_direction_cosines_are_not_allowed_is_held_as_received(
    edges,
):
    _, outcomes, reasons, _ = edges
    held = HeldVisualFeatures(VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME)

    # It cannot be placed, so it is not set to zero, and stays held for its
    # frame, in this run as in the reviewed one.
    for name in _UNPLACEABLE:
        assert outcomes[name] == ("held-for-review", None), name
        assert held in reasons[name], name


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_an_rt_dose_of_dose_volume_histograms_alone_is_not_held_for_its_frame(
    edges,
):
    _, outcomes, reasons, _ = edges

    # Without a grid, it shows no face, in a defaced frame or not, so the
    # verdict of absent on its series releases it.
    assert not any(isinstance(r, HeldVisualFeatures) for r in reasons[_DVH_ONLY])
    disposition, dataset = outcomes[_DVH_ONLY]
    assert disposition == "released", reasons[_DVH_ONLY]
    assert "PixelData" not in dataset
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_rt_instances_judged_beside_a_defaced_ct_are_held_in_a_run_without_it(
    without_ct,
):
    _, outcomes, reasons, report = without_ct
    held = HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT)

    # The reviewed run held them because it defaced their frame, so the
    # verdict of absent on them was given beside the defaced CT. A run
    # without that CT defaces nothing, and must not release them on it.
    for name in _UNDEFACED:
        assert outcomes[name] == ("held-for-review", None), name
        assert reasons[name] == {held}, name
    # The verdict on the dose set to zero is of what that run wrote, which
    # this run, writing it as received, does not.
    assert outcomes[_DOSE[0]] == ("held-for-review", None)
    assert reasons[_DOSE[0]] == {
        HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA)
    }
    assert report["face_review"]["ct_series"] == {"defaced": 0, "not_defaced": []}


def test_a_target_in_the_block_holds_the_head_ct(targeted):
    slices, outcomes, reasons, report = targeted
    held = HeldVisualFeatures(VisualFeaturesReason.TARGET_IN_FACE_BLOCK)

    for index in range(len(slices)):
        assert outcomes[_head_name(index)] == ("held-for-review", None), index
        assert held in reasons[_head_name(index)]
    assert report["face_review"]["ct_series"] == {
        "defaced": 0,
        "not_defaced": [{"reason": "target-in-block", "count": 1}],
    }
    counts = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert counts["target-in-face-block"] == len(slices)
    # With no series defaced, the RT instances marked absent are released,
    # but for the RT Dose that its release gate holds for review.
    for name in _IN_FRAME:
        assert not any(isinstance(r, HeldVisualFeatures) for r in reasons[name])
        if name != _DOSE[1]:
            disposition, dataset = outcomes[name]
            assert disposition == "released", name
            assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]


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
    assert report["face_review"]["ct_series"] == {"defaced": 1, "not_defaced": []}
