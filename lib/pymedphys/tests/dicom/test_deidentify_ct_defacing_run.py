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
of the analytic head, beside the synthetic collection's RT Structure Set, RT
Dose, PET, and Segmentation in the same Frame of Reference, the RT Structure
Set replaced by one of the head, one RT Dose by a grid over the head, the
PET Image by two slices of the head, and the BINARY Segmentation by one of
the head's body. Every UID and value here is invented."""

# The runs of the head share _ct_defacing_runs.py with
# test_deidentify_ct_defacing_review_runs.py, which CI runs in a part of its
# own, so that neither part reaches the time limit. Each module makes the
# runs that its own tests review, so no run is made in both.
# pylint: disable = too-many-lines

from __future__ import annotations

import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest, shapely

from pymedphys._dicom.deidentify import defacing, face_blocks, markers, qc_previews
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.face_review import FaceReview
from pymedphys._dicom.deidentify.qc_attestation import Face
from pymedphys._dicom.deidentify.qc_pack import new_reference
from pymedphys._dicom.deidentify.reasons import HeldVisualFeatures, VisualFeaturesReason
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import ReleaseReason

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from . import _synthetic_rtdose as rtdose
from ._corpus_run import decoders_installed
from ._ct_defacing_runs import (
    _COLLECTION_REGISTRATION,
    _COMPRESSED,
    _CT_FILES,
    _DOSE,
    _ERROR_DOSE,
    _HEAD_ENHANCED,
    _IN_THE_BLOCK,
    _LOW,
    _PET,
    _PET_ENHANCED,
    _PET_SLICES,
    _ROIS,
    _SCAN,
    _SEGMENTATION,
    _SEGMENTATIONS,
    _SEGMENTED,
    _SLAB_STRUCTURE_SET,
    _STRUCTURE_SET,
    _TIED,
    _UNDEFACED,
    _UNDEFACED_WITH_REGISTRATIONS,
    _UNPLACED,
    _UNTIED,
    _behind,
    _block,
    _body,
    _contours,
    _dose,
    _head_name,
    _output_name,
    _pet_points,
    _pet_uptake,
    _phase_name,
    _region,
    _reviewed,
    _reviewed_again,
    _runs,
    _second,
    _transform,
    _undefaced_listed,
    _written_as_air,
)
from .test_deidentify_visual_features_option import CODE, _codes


# The runs that the defaced, without_ct, and own-verdict runs review are the
# same, so it is made once.
@pytest.fixture(name="reviewed_low", scope="module")
def fixture_reviewed_low():
    with _reviewed(first=(), dose=_dose(_LOW), registrations=True) as found:
        yield found


@pytest.fixture(name="defaced", scope="module")
def fixture_defaced(reviewed_low):
    return _second(reviewed_low, name="d")


# The reviewer saw no face in the own previews of each PET instance that the
# run did not clean in the defaced frame.
@pytest.fixture(name="own_absent", scope="module")
def fixture_own_absent(reviewed_low):
    return _second(
        reviewed_low,
        name="o",
        instance_faces=dict.fromkeys(_UNDEFACED_WITH_REGISTRATIONS, Face.ABSENT),
    )


# The reviewer saw no face in the first's own previews, and saw one in the
# second's.
@pytest.fixture(name="own_mixed", scope="module")
def fixture_own_mixed(reviewed_low):
    return _second(
        reviewed_low,
        name="om",
        instance_faces={_UNDEFACED[0]: Face.ABSENT, _UNDEFACED[1]: Face.PRESENT},
    )


# As own_absent, but with the series of the first marked present.
@pytest.fixture(name="own_series_present", scope="module")
def fixture_own_series_present(reviewed_low):
    return _second(
        reviewed_low,
        name="op",
        instance_faces=dict.fromkeys(_UNDEFACED_WITH_REGISTRATIONS, Face.ABSENT),
        present=(_UNDEFACED[0],),
    )


# As own_absent, in a run without the head's slices, which defaces nothing.
@pytest.fixture(name="own_without_ct", scope="module")
def fixture_own_without_ct(reviewed_low):
    return _second(
        reviewed_low,
        name="ow",
        without_ct=True,
        instance_faces=dict.fromkeys(_UNDEFACED_WITH_REGISTRATIONS, Face.ABSENT),
    )


# The run that own_absent made, reviewed in turn with its series marked absent
# and no verdict of an instance's own.
@pytest.fixture(name="own_reviewed_again", scope="module")
def fixture_own_reviewed_again(reviewed_low, own_absent):
    assert own_absent
    return _second(_reviewed_again(reviewed_low, "o"), name="o3")


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


@pytest.fixture(name="compressed", scope="module")
def fixture_compressed():
    with _runs(first=(), dose=_dose(_LOW), compressed=True) as found:
        yield found


@pytest.fixture(name="as_received", scope="module")
def fixture_as_received():
    with _runs() as found:
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


@pytest.fixture(name="without_ct", scope="module")
def fixture_without_ct(reviewed_low):
    return _second(reviewed_low, name="w", without_ct=True)


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


_NEEDS_DECODERS = pytest.mark.skipif(
    not decoders_installed(), reason="needs a decoder of each compressed syntax"
)


def _pixels(dataset):
    return pydicom.pixels.pixel_array(dataset)


@_NEEDS_DECODERS
@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_compressed_head_ct_is_released_defaced_as_the_native_one_is(
    compressed, defaced
):
    slices, outcomes, reasons, report = compressed
    _, native, _, native_report = defaced
    uncompressed = kept = 0

    # Each slice is released with the pixels that the native series is
    # released with: a slice that defacing changes, decoded and written
    # uncompressed, and any other as received, in its own transfer syntax.
    for index, data in enumerate(slices):
        name = _head_name(index)
        disposition, dataset = outcomes[name]
        assert disposition == "released", reasons[name]
        assert dataset.RecognizableVisualFeatures == "NO"
        assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
        expected = native[name][1]
        assert np.array_equal(_pixels(dataset), _pixels(expected)), index
        syntax = str(dataset.file_meta.TransferSyntaxUID)
        before = pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))
        if expected.PixelData != before.PixelData:
            assert syntax == files.EXPLICIT_VR_LITTLE_ENDIAN, index
            assert "ExtendedOffsetTable" not in dataset
            uncompressed += 1
        else:
            assert syntax == _COMPRESSED[index % len(_COMPRESSED)], index
            kept += 1
    assert uncompressed > 0 and kept > 0
    assert (
        report["face_review"]["ct_series"] == native_report["face_review"]["ct_series"]
    )


@_NEEDS_DECODERS
@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_compressed_pet_and_rt_dose_in_the_frame_are_cleaned_as_native_ones_are(
    compressed, defaced
):
    _, outcomes, reasons, _ = compressed
    _, native, _, _ = defaced

    # Each is decoded, set to zero in the block less the kept brain, and
    # written uncompressed, as its native version is set to zero, and the
    # verdict on the pixel data that the reviewed run wrote releases it.
    for name in (*_PET_SLICES, _DOSE[0]):
        disposition, dataset = outcomes[name]
        assert disposition == "released", reasons[name]
        assert dataset.RecognizableVisualFeatures == "NO"
        assert str(dataset.file_meta.TransferSyntaxUID) == (
            files.EXPLICIT_VR_LITTLE_ENDIAN
        )
        assert np.array_equal(_pixels(dataset), _pixels(native[name][1])), name


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
    assert report["face_review"]["ct_series"] == {
        "defaced": 1,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }
    counts = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    # So are the PET slices, which the run sets to zero in the block, and
    # the Segmentation, which it clears there.
    assert (
        counts[VisualFeaturesReason.OTHER_PIXEL_DATA.value]
        == changed + len(_PET_SLICES) + 1
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
@pytest.mark.parametrize("fixture", ["defaced", "as_received"])
def test_pet_instances_in_the_defaced_frame_that_are_not_cleaned_are_held(
    fixture, request
):
    _, outcomes, reasons, report = request.getfixturevalue(fixture)
    held = HeldVisualFeatures(VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME)
    # Where the reviewed run defaced their frame too, it held them for it,
    # so the verdict of absent on them does not count either.
    expected = {held}
    if fixture == "defaced":
        expected.add(HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT))

    # Marked absent, the enhanced PET images in the head's Frame of
    # Reference, which the run does not clean, still trace the face that the
    # defaced CT no longer shows, so neither is released, and nothing claims
    # the option for them because their CT was defaced.
    for name in _UNDEFACED:
        assert outcomes[name] == ("held-for-review", None), name
        assert reasons[name] == expected, name
    assert report["face_review"]["ct_series"] == {
        "defaced": 1,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }
    counts = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    # Besides them, the deformable registrations tied to the head's frame,
    # which the run does not clean either.
    registrations = [
        name for name in (*_TIED, _COLLECTION_REGISTRATION) if name in outcomes
    ]
    for name in registrations:
        assert held in reasons[name], name
    assert counts[held.reason.value] == len(_UNDEFACED) + len(registrations)


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_registration_whose_grid_is_tied_to_the_defaced_frame_is_held(defaced):
    _, outcomes, reasons, report = defaced
    held = HeldVisualFeatures(VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME)

    # Marked absent, a registration's grid in the head's Frame of Reference,
    # or registering it, or tied to its slices, can still trace the face
    # that the defaced CT no longer shows, and the run does not cut it; so
    # can one that names no Source Frame of Reference, which may be the
    # head's. Since the reviewed run defaced that frame too, it held them
    # for it, so the verdict of absent on them does not count either.
    for name in _TIED:
        assert outcomes[name] == ("held-for-review", None), name
        assert reasons[name] == {
            held,
            HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT),
        }, name
    # One tied to the head in no way is released on its verdict, with the
    # grid that the reviewed run wrote and its grid sheets showed.
    disposition, dataset = outcomes[_UNTIED]
    assert disposition == "released", reasons[_UNTIED]
    assert not reasons[_UNTIED]
    assert dataset.RecognizableVisualFeatures == "NO"
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
    (item,) = dataset.DeformableRegistrationSequence
    (grid,) = item.DeformableRegistrationGridSequence
    vectors = np.frombuffer(grid.VectorGridData, "<f4").reshape(2, 3, 4, 3)
    assert vectors[1, 1, 1:3].tolist() == [[1.0, -2.0, 0.5]] * 2
    assert report["face_review"]["ct_series"] == {
        "defaced": 1,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }


def _vector_grids(dataset):
    """The Vector Grid Data of each grid of a deformable registration."""
    return [
        grid.VectorGridData
        for item in dataset.DeformableRegistrationSequence
        for grid in item.get("DeformableRegistrationGridSequence", [])
    ]


def _undefaced_report(held=0, released=(), held_with_own_verdict=0):
    return {
        "held": held,
        "released": sorted(released),
        "held_with_own_verdict": held_with_own_verdict,
    }


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_the_pack_lists_each_undefaced_instance_for_a_verdict_of_its_own(
    reviewed_low, defaced
):
    _, _, _, report = defaced
    listed = _undefaced_listed(reviewed_low)

    # Only the PET instances and deformable registrations that the run did
    # not clean are listed, each shown, since its previews drew every frame
    # and grid, and nothing else in the frame is, since the run cleaned it.
    assert set(listed) == set(_UNDEFACED_WITH_REGISTRATIONS)
    assert all(entry["shown"] for entry in listed.values())
    entries = {
        reviewed_low.names[e["position"]]: e
        for e in json.loads(reviewed_low.pack.read_text("utf-8"))["instances"]
    }
    for name in _UNDEFACED_WITH_REGISTRATIONS:
        for digest in ("pixel_sha256", "contour_sha256", "grid_sha256"):
            assert entries[name][digest] is not None, (name, digest)
    assert report["face_review"]["undefaced_in_defaced_frame"] == _undefaced_report(
        held=len(_UNDEFACED_WITH_REGISTRATIONS)
    )
    # The run without verdicts of their own lists them again, held.
    assert set(_undefaced_listed(reviewed_low, "d")) == set(
        _UNDEFACED_WITH_REGISTRATIONS
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_an_undefaced_instance_is_released_on_a_verdict_of_absent_of_its_own(
    reviewed_low, own_absent
):
    _, outcomes, reasons, report = own_absent

    # The reviewer judged each from its own previews, which drew every frame
    # and grid as written, so each is released as received, with the
    # option's code, though the run does not clean it in its defaced frame.
    names = []
    for name in _UNDEFACED_WITH_REGISTRATIONS:
        disposition, dataset = outcomes[name]
        assert disposition == "released", reasons[name]
        assert dataset.RecognizableVisualFeatures == "NO"
        assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
        source = pydicom.dcmread(reviewed_low.instances / name)
        if name in _UNDEFACED:
            assert dataset.PixelData == source.PixelData
        else:
            assert _vector_grids(dataset) == _vector_grids(source), name
        names.append(_output_name(dataset))
    assert report["face_review"]["undefaced_in_defaced_frame"] == _undefaced_report(
        released=names
    )
    assert set(names) <= set(report["released"])
    # Everything else in the frame is as without such verdicts.
    assert outcomes[_STRUCTURE_SET][0] == "released", reasons[_STRUCTURE_SET]
    assert outcomes[_DOSE[0]][0] == "released", reasons[_DOSE[0]]
    # The run lists them again for the next review, released.
    listed = _undefaced_listed(reviewed_low, "o")
    assert set(listed) == set(_UNDEFACED_WITH_REGISTRATIONS)
    assert all(entry["shown"] for entry in listed.values())


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_verdict_of_present_of_its_own_or_on_its_series_holds_it(
    own_mixed, own_series_present
):
    _, outcomes, reasons, report = own_mixed
    present = HeldVisualFeatures(VisualFeaturesReason.FACE_PRESENT)

    # Its own verdict decides it in place of its frame, so the instance in
    # which the reviewer saw a face is held for that face alone.
    assert outcomes[_UNDEFACED[0]][0] == "released", reasons[_UNDEFACED[0]]
    assert outcomes[_UNDEFACED[1]] == ("held-for-review", None)
    assert reasons[_UNDEFACED[1]] == {present}
    section = report["face_review"]["undefaced_in_defaced_frame"]
    # The registrations, given none, are held without one.
    assert section["held"] == len(_UNDEFACED_WITH_REGISTRATIONS) - 2
    assert section["held_with_own_verdict"] == 1
    assert len(section["released"]) == 1

    # A face seen in its series holds it whatever its own verdict.
    _, outcomes, reasons, report = own_series_present
    assert outcomes[_UNDEFACED[0]] == ("held-for-review", None)
    assert reasons[_UNDEFACED[0]] == {present}
    assert (
        report["face_review"]["undefaced_in_defaced_frame"]["held_with_own_verdict"]
        >= 1
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_verdict_of_its_own_is_on_its_pixel_data_whatever_is_defaced(
    reviewed_low, own_without_ct
):
    _, outcomes, reasons, report = own_without_ct

    # Without the head's slices nothing is defaced, and each is written as
    # the reviewed run wrote it, which its own verdict judged, so it is
    # released; it is not in a defaced frame, so it is not counted as such.
    for name in _UNDEFACED_WITH_REGISTRATIONS:
        disposition, dataset = outcomes[name]
        assert disposition == "released", reasons[name]
        source = pydicom.dcmread(reviewed_low.instances / name)
        if name in _UNDEFACED:
            assert dataset.PixelData == source.PixelData
        else:
            assert _vector_grids(dataset) == _vector_grids(source), name
    assert report["face_review"]["undefaced_in_defaced_frame"] == _undefaced_report()


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_a_released_undefaced_instance_needs_a_new_verdict_of_its_own(
    own_reviewed_again,
):
    _, outcomes, reasons, report = own_reviewed_again
    held = HeldVisualFeatures(VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME)

    # The earlier run released each on its own verdict, and its pack listed
    # each again, so the verdict of absent on its series in that pack does
    # not cover it either, and with none of its own it is held.
    for name in _UNDEFACED_WITH_REGISTRATIONS:
        assert outcomes[name] == ("held-for-review", None), name
        assert reasons[name] == {
            held,
            HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT),
        }, name
    assert report["face_review"]["undefaced_in_defaced_frame"] == _undefaced_report(
        held=len(_UNDEFACED_WITH_REGISTRATIONS)
    )


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_a_verdict_of_its_own_needs_no_confirmed_block(eyes_away_own):
    _, outcomes, reasons, _ = eyes_away_own

    # No block cleans anything of an instance written as received, so the
    # eyes that disagree with the block, which hold the head's slices, do
    # not hold it.
    assert outcomes[_head_name(0)][0] == "held-for-review"
    for name in _UNDEFACED:
        assert outcomes[name][0] == "released", reasons[name]


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_the_head_structure_set_is_cut_by_the_block_and_released(defaced):
    slices, outcomes, reasons, _ = defaced
    block = _block(slices)
    disposition, dataset = outcomes[_STRUCTURE_SET]

    assert disposition == "released", reasons[_STRUCTURE_SET]
    assert dataset.RecognizableVisualFeatures == "NO"
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
    written = _contours(dataset)
    floor = head.GLOBE_Z + face_blocks.CAVITY_FLOOR
    # Below the kept brain's floor, the outline and the eyes lose their
    # parts in the block, on each slice; each slice's contour is one
    # polygon, which is its part behind the block's plane, as the CT keeps
    # the backs of the globes.
    for name in ("External", "Eye_R", "Eye_L"):
        cuts = iter(written[name])
        for source in _ROIS[name][1]:
            z = source[0, 2]
            if z > floor:
                continue
            cut = next(cuts)
            assert cut[0, 2] == z
            assert not block.contains(cut).any(), (name, z)
            expected = shapely.geometry.Polygon(source[:, :2]).intersection(
                _behind(block, z)
            )
            got = shapely.geometry.Polygon(cut[:, :2])
            assert got.symmetric_difference(expected).area < 1e-3 * expected.area
            assert got.area < shapely.geometry.Polygon(source[:, :2]).area, name
    # Above it, the outline, and the brain drawn out to the skull, lose
    # exactly what the CT writes as air, keeping the brain that the CT
    # keeps, and so more than the block's plane would leave them.
    for name in ("External", "Brain_Table"):
        for source in _ROIS[name][1]:
            z = source[0, 2]
            if z <= floor:
                continue
            got = _region([each for each in written[name] if each[0, 2] == z])
            whole = shapely.geometry.Polygon(source[:, :2])
            expected = whole.difference(_written_as_air(outcomes, block, z))
            assert got.symmetric_difference(expected).area < 1e-6 * whole.area
            assert got.area < whole.area, (name, z)
            assert got.area > whole.intersection(_behind(block, z)).area, (name, z)
    # The brain, kept above the floor, and the target behind the block, are as
    # they were; the lens, wholly in the block, is gone, without a Contour
    # Sequence.
    for name in ("Brain", "PTV"):
        for source, kept in zip(_ROIS[name][1], written[name], strict=True):
            assert np.allclose(kept, source, atol=1e-4), name
    assert written["Lens_L"] is None


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_the_head_pet_is_set_to_zero_activity_in_the_block_and_released(defaced):
    slices, outcomes, reasons, _ = defaced
    block = _block(slices)
    floor = head.GLOBE_Z + face_blocks.CAVITY_FLOOR

    for name, z in _PET_SLICES.items():
        disposition, dataset = outcomes[name]
        assert disposition == "released", reasons[name]
        assert dataset.RecognizableVisualFeatures == "NO"
        assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
        points = _pet_points(z)
        source, written = _pet_uptake(z), dataset.pixel_array
        inside = block.contains(points)
        # Outside the block, nothing changes; within it, zero but for the
        # brain above the floor.
        assert np.array_equal(written[~inside], source[~inside]), name
        assert np.all((written[inside] == 0) | (written[inside] == source[inside]))
        changed = written != source
        assert changed.any(), name
        brain = inside & (head.hounsfield(points) == head.BRAIN)
        if z <= floor:
            assert np.all(written[inside] == 0), name
        else:
            assert brain.any() and np.array_equal(written[brain], source[brain])


@pytest.mark.deid_requirement("PS3.15-E.3.2-01", "PS3.15-E.3.2-02")
def test_the_head_segmentation_is_cleared_in_the_block_and_released(defaced):
    slices, outcomes, reasons, _ = defaced
    block = _block(slices)
    floor = head.GLOBE_Z + face_blocks.CAVITY_FLOOR

    # The reviewer saw its segment as the run wrote it, on its segments
    # sheet, so the verdict of absent releases it.
    disposition, dataset = outcomes[_SEGMENTATION]
    assert disposition == "released", reasons[_SEGMENTATION]
    assert dataset.RecognizableVisualFeatures == "NO"
    assert _codes(dataset)[-2:] == [markers.PROFILE_CODE, CODE]
    written = pydicom.pixels.pixel_array(dataset)
    assert written.shape == (len(_SEGMENTED.positions), *_SEGMENTED.shape)
    changed = kept = 0
    for index in range(len(_SEGMENTED.positions)):
        points = _SEGMENTED.points(index)
        source, inside = _body(index), block.contains(points)
        # Outside the block, nothing changes; within it, the segment is
        # cleared but for the brain above the floor.
        assert np.array_equal(written[index][~inside], source[~inside]), index
        assert not np.any(written[index][inside] & ~source[inside]), index
        brain = inside & (head.hounsfield(points) == head.BRAIN)
        brain &= points[..., 2] > floor
        assert np.all(written[index][brain]), index
        kept += int(np.count_nonzero(brain))
        changed += int(np.count_nonzero(written[index] != source))
    assert changed > 0 and kept > 0


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_the_head_structure_set_pet_and_segmentation_seen_as_received_are_held(
    as_received,
):
    _, outcomes, reasons, _ = as_received

    # The reviewer saw them as received, which the run, cutting them by the
    # block, setting them to zero there, or clearing their segments there,
    # no longer writes.
    assert outcomes[_STRUCTURE_SET] == ("held-for-review", None)
    assert reasons[_STRUCTURE_SET] == {
        HeldVisualFeatures(VisualFeaturesReason.OTHER_CONTOURS)
    }
    for name in (*_PET_SLICES, _SEGMENTATION):
        assert outcomes[name] == ("held-for-review", None), name
        assert reasons[name] == {
            HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA)
        }, name


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
    # The verdicts on the structure set cut by the block and the PET set to
    # zero in it are of what that run wrote, which this run, writing them as
    # received, does not.
    assert outcomes[_STRUCTURE_SET] == ("held-for-review", None)
    assert reasons[_STRUCTURE_SET] == {
        HeldVisualFeatures(VisualFeaturesReason.OTHER_CONTOURS)
    }
    for name in _PET_SLICES:
        assert outcomes[name] == ("held-for-review", None), name
        assert reasons[name] == {
            HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA)
        }, name
    # The verdict on the dose set to zero is of what that run wrote, which
    # this run, writing it as received, does not.
    assert outcomes[_DOSE[0]] == ("held-for-review", None)
    assert reasons[_DOSE[0]] == {
        HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA)
    }
    # Nor the deformable registrations that the reviewed run held for their
    # frame, while the one tied to the head in no way is released.
    for name in _TIED:
        assert outcomes[name] == ("held-for-review", None), name
        assert reasons[name] == {held}, name
    assert outcomes[_UNTIED][0] == "released"
    assert report["face_review"]["ct_series"] == {
        "defaced": 0,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": _UNPLACED}],
    }


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


def test_an_unexpected_error_in_the_finder_releases_no_slice_it_would_deface(
    reviewed_low, defaced, monkeypatch
):
    # As the IndexError that an earlier front test raised on real heads: the
    # series is not defaced, and a slice is released only as the reviewer
    # saw it, so each slice that defacing changes is held.
    def fail(*_):
        raise IndexError("index out of bounds")

    monkeypatch.setattr(defacing.FaceInspection, "_front", fail)
    slices, outcomes, reasons, report = _second(reviewed_low, name="e")
    _, written, _, _ = defaced
    held = HeldVisualFeatures(VisualFeaturesReason.OTHER_PIXEL_DATA)
    changed = 0

    for index, data in enumerate(slices):
        name = _head_name(index)
        before = pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))
        if written[name][1].PixelData != before.PixelData:
            changed += 1
            assert outcomes[name] == ("held-for-review", None), index
            assert reasons[name] == {held}, index
        else:
            disposition, dataset = outcomes[name]
            assert disposition == "released", index
            assert dataset.PixelData == before.PixelData, index
    assert 0 < changed < len(slices)
    assert report["face_review"]["ct_series"] == {
        "defaced": 0,
        "defaced_around_targets": 0,
        "defaced_eyes_unconfirmed": 0,
        "defaced_eyes_confirmed": 0,
        "not_defaced": [{"reason": "unreadable", "count": 1 + _UNPLACED}],
    }


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
