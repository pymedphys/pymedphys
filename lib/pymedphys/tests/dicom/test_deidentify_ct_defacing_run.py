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
Dose, and PET in the same Frame of Reference, the RT Structure Set replaced
by one of the head, one RT Dose by a grid over the head, and the PET Image
by two slices of the head. Every UID and value here is invented."""

# The runs share the head, its ROIs, and the fixtures that review one run of
# the collection, so they stay in one module.
# pylint: disable = too-many-lines

from __future__ import annotations

import contextlib
import copy
import dataclasses
import json
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest, shapely

from pymedphys._dicom.deidentify import dose_defacing, face_blocks, markers, run
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.face_review import FaceReview, read_face_review
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.policy import CLEAN_PIXEL_DATA, compose_policy
from pymedphys._dicom.deidentify.qc_pack import new_reference
from pymedphys._dicom.deidentify.qc_attestation import (
    Face,
    Redaction,
    RedactionVerdict,
    previewed_redactions,
)
from pymedphys._dicom.deidentify.reasons import (
    HeldPixelData,
    HeldVisualFeatures,
    PixelDataReason,
    VisualFeaturesReason,
)
from pymedphys._dicom.deidentify.redaction_review import read_redaction_review
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import ReleaseReason
from pymedphys._dicom.deidentify.text_detection import TextBox

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
# A second PET slice of the head, in the first's series.
_PET_ABOVE = "15-pet-above.dcm"
_IN_FRAME = (_STRUCTURE_SET, *_DOSE, *_PET, _PET_ABOVE)
# The PET instances that the run does not clean.
_UNDEFACED = _PET[1:]
# The PET slices of the head, by file name, at heights below and above the
# floor of the kept brain.
_PET_SLICES = {_PET[0]: 20.0, _PET_ABOVE: 70.0}
_PET_GRID = {"position": (-100.0, -130.0), "spacing": (5.0, 5.0), "shape": (49, 41)}
_UPTAKE = 100
_IN_THE_BLOCK = (-32.0, -76.0, 20.0)
_GLOBES = [(-head.GLOBE_X, head.GLOBE_Y), (head.GLOBE_X, head.GLOBE_Y)]
# The head's outline and brain, from the analytic head's ellipsoids.
_OUTLINE = ((0.0, 0.0, 10.0), (75.0, 95.0, 130.0))
_BRAIN = ((0.0, 0.0, 40.0), (62.0, 82.0, 79.0))
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


def _section(ellipsoid, z, scale=1.0):
    """An ellipsoid's outline on the axial slice at ``z``, scaled about its
    axis."""
    (x, y, centre), (a, b, c) = ellipsoid
    factor = scale * np.sqrt(1 - ((z - centre) / c) ** 2)
    return files.ellipse((x, y, z), (a * factor, b * factor))


def _eye(side, *, below=0.0):
    """An eye's contours on the slices through its globe, ``below`` its
    centre by that many millimetres."""
    x, y = _GLOBES[side]
    return [
        files.circle(
            (x, y, head.GLOBE_Z - below + dz), np.sqrt(head.GLOBE_RADIUS**2 - dz**2)
        )
        for dz in (-5.0, 0.0, 5.0)
    ]


# The head's ROIs: its outline, which the block cuts on each slice; its
# brain, within the cranial cavity above the floor, and drawn out to the
# skull; its eyes, whose backs lie behind the block's plane; a lens, wholly
# in the block; and a target behind the block.
_ROIS = {
    "External": ("EXTERNAL", [_section(_OUTLINE, z) for z in (20.0, 60.0, 80.0)]),
    "Brain": ("ORGAN", [_section(_BRAIN, z, 0.9) for z in (60.0, 80.0)]),
    # The brain drawn on the inner table, as segmentations commonly are, so
    # that it reaches bone, which defacing writes as air.
    "Brain_Table": ("ORGAN", [_section(_BRAIN, z) for z in (60.0, 80.0)]),
    "Eye_R": ("ORGAN", _eye(0)),
    "Eye_L": ("ORGAN", _eye(1)),
    "Lens_L": (
        "ORGAN",
        [files.circle((head.GLOBE_X, head.GLOBE_Y - 8.0, head.GLOBE_Z), 3.0)],
    ),
    "PTV": ("PTV", [files.square((0.0, 30.0, 40.0))]),
}


def _head_structure_set(template, *, eyes_away=False):
    rois = dict(_ROIS)
    if eyes_away:
        # The left eye drawn 40 mm below its globe, where the finder found
        # none.
        rois["Eye_L"] = ("ORGAN", _eye(1, below=40.0))
    return files.structure_set(
        list(rois.values()),
        frame=corpus_module.FRAME_OF_REFERENCE,
        template=template,
        names=list(rois),
    )


def _pet_points(z):
    rows, columns = _PET_GRID["shape"]
    x0, y0 = _PET_GRID["position"]
    spacing = _PET_GRID["spacing"][0]
    x = x0 + spacing * np.arange(columns)[None, :]
    y = y0 + spacing * np.arange(rows)[:, None]
    x, y = np.broadcast_arrays(x, y)
    return np.stack([x, y, np.full(x.shape, z)], axis=-1)


def _pet_uptake(z):
    """Uptake throughout the head, and none outside it."""
    return np.where(head.hounsfield(_pet_points(z)) > head.AIR, _UPTAKE, 0)


# Grids that cannot be placed, by file name: direction cosines that PS3.3
# C.7.6.2.1.1 does not allow, and finite geometry too far to place.
_UNPLACEABLE = {
    "06-rtdose-zero-cosines.dcm": {"orientation": (0.0,) * 6},
    "06-rtdose-non-unit-cosines.dcm": {"orientation": (2.0, 0.0, 0.0, 0.0, 1.0, 0.0)},
    "06-rtdose-non-orthogonal-cosines.dcm": {
        "orientation": (1.0, 0.0, 0.0, 0.6, 0.8, 0.0)
    },
    "06-rtdose-huge-spacing.dcm": {"spacing": (1e300, 1e300)},
    "06-rtdose-huge-offsets.dcm": {"offsets": tuple(1e299 * k for k in range(15))},
    "06-rtdose-huge-position.dcm": {"position": (1e300, -130.0, -30.0)},
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


@dataclasses.dataclass(frozen=True)
class _Reviewed:
    """The collection as :func:`_reviewed` wrote it, and its first run."""

    directory: Path
    instances: Path
    slices: list
    pack: Path
    names: dict
    marked: list


@contextlib.contextmanager
def _runs(*others, without_ct=False, accepted=False, revised=None, **first_run):
    """Run the collection as :func:`_reviewed` does, given ``first_run``, and
    again as :func:`_second` does, given the rest."""
    with _reviewed(**first_run) as reviewed:
        yield _second(
            reviewed,
            *others,
            name="r",
            without_ct=without_ct,
            accepted=accepted,
            revised=revised,
        )


@contextlib.contextmanager
def _reviewed(first=None, target=False, eyes_away=False, dose=None, edges=False):
    """Run the collection, with its CT slices replaced by the head's, its RT
    Structure Set by the head's ROIs, or by a target in the block if
    ``target``, its PET Image by :data:`_PET_SLICES`, and its first RT Dose
    by a grid over the head of ``dose`` where given, with the RT Dose
    instances of :data:`_UNPLACEABLE` and :data:`_DVH_ONLY` in its series if
    ``edges``, under ``basic``, or under the option and ``first`` with a
    face review that gives no verdicts."""
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
                for index, (name, geometry) in enumerate(_UNPLACEABLE.items()):
                    (instances / name).write_bytes(
                        files.dose(
                            dose,
                            **{**_GRID, **geometry},
                            frame=corpus_module.FRAME_OF_REFERENCE,
                            instance=f"{grid.SOPInstanceUID}.{index + 1}",
                            template=grid,
                        )
                    )
                (instances / _DVH_ONLY).write_bytes(
                    _dvh_only(grid, f"{grid.SOPInstanceUID}.9")
                )
        rtss = pydicom.dcmread(instances / _STRUCTURE_SET)
        (instances / _STRUCTURE_SET).write_bytes(
            files.structure_set(
                [("PTV", files.square(_IN_THE_BLOCK))],
                frame=corpus_module.FRAME_OF_REFERENCE,
                template=rtss,
            )
            if target
            else _head_structure_set(rtss, eyes_away=eyes_away)
        )
        pet = pydicom.dcmread(instances / _PET[0])
        for index, (name, z) in enumerate(_PET_SLICES.items()):
            (instances / name).write_bytes(
                files.pet(
                    _pet_uptake(z),
                    position=(*_PET_GRID["position"], z),
                    spacing=_PET_GRID["spacing"],
                    frame=corpus_module.FRAME_OF_REFERENCE,
                    instance=pet.SOPInstanceUID + ("" if index == 0 else ".1"),
                    template=pet,
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
        yield _Reviewed(directory, instances, slices, reviewed.qc_pack, names, marked)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _second(reviewed, *others, name, without_ct=False, accepted=False, revised=None):
    """Attest a copy of the reviewed run's pack, in ``name`` beside it, with
    the head's series, and those of the RT Structure Set, RT Dose, and PET
    in its frame, marked absent, and, if ``accepted``, the regions of each
    of the head's CT and PET slices that the pack previews accepted, or, if
    ``revised``, those of each of its CT slices, revised with that region
    added in their first frame; and run the collection again under the
    option and ``others``, given those verdicts, without the head's slices
    if ``without_ct``.

    The run that it reviews, and the files that it ran, are left as they
    were, so that one reviewed run serves several second runs."""
    directory = reviewed.directory / name
    pack = directory / "qc1"
    shutil.copytree(reviewed.pack.parent, pack)
    verdict = (
        {"redaction": Redaction.ACCEPTED}
        if revised is None
        else {"redaction": Redaction.REVISED, "regions": ((0, (revised,)),)}
    )
    redactions = (
        [
            RedactionVerdict(position, **verdict)
            for position in previewed_redactions(reviewed.pack.read_bytes())
            if reviewed.names[position].startswith("01-head")
            or (revised is None and reviewed.names[position] in _PET_SLICES)
        ]
        if accepted or revised is not None
        else []
    )
    _attest(pack, dict.fromkeys(reviewed.marked, Face.ABSENT), redactions=redactions)
    instances = reviewed.instances
    if without_ct:
        instances = directory / "i"
        shutil.copytree(
            reviewed.instances,
            instances,
            ignore=lambda _, found: [f for f in found if f.startswith("01-head")],
        )
    transform = _transform(
        others,
        read_face_review(pack),
        read_redaction_review(pack) if accepted or revised is not None else None,
    )
    second = run.run(
        run.discover(instances),
        directory / "r2",
        transform,
        ReleaseGate(),
        qc_destination=directory / "qc2",
        reporter=transform.reporter,
    )
    entries = json.loads(second.qc_pack.read_text("utf-8"))["instances"]
    outcomes = {
        Path(entry["source"]).name: (
            entry["disposition"],
            None
            if entry.get("output") is None
            else pydicom.dcmread(directory / "r2" / entry["output"]),
        )
        for entry in entries
    }
    reasons = {
        Path(entry["source"]).name: set(outcome.reasons)
        for entry in entries
        for outcome in second.outcomes
        if outcome.position == entry["position"]
    }
    report = json.loads((directory / "r2" / "release-report.json").read_text())
    return reviewed.slices, outcomes, reasons, report


def _transform(options, face_review, redaction_review=None):
    return InstanceTransform(
        _policy(*options),
        KEY,
        face_review=face_review,
        finder=_CornerFinder() if CLEAN_PIXEL_DATA in options else None,
        redaction_review=redaction_review,
        unvalidated_policy=True,
    )


# The runs that the defaced and without_ct runs review, and those that the
# with_pixel_data, accepted, and revised runs review, are the same, so each
# is made once.
@pytest.fixture(name="reviewed_low", scope="module")
def fixture_reviewed_low():
    with _reviewed(first=(), dose=_dose(_LOW)) as found:
        yield found


@pytest.fixture(name="reviewed_with_pixel_data", scope="module")
def fixture_reviewed_with_pixel_data():
    with _reviewed(first=(CLEAN_PIXEL_DATA,)) as found:
        yield found


@pytest.fixture(name="defaced", scope="module")
def fixture_defaced(reviewed_low):
    return _second(reviewed_low, name="d")


# With the RT Dose instances that cannot be placed or have no grid, which
# its run holds or releases alike, so that one run tests them all.
@pytest.fixture(name="hot", scope="module")
def fixture_hot():
    with _runs(first=(), dose=_dose(_HIGHEST), edges=True) as found:
        yield found


@pytest.fixture(name="as_received", scope="module")
def fixture_as_received():
    with _runs() as found:
        yield found


@pytest.fixture(name="targeted", scope="module")
def fixture_targeted():
    with _runs(target=True) as found:
        yield found


@pytest.fixture(name="eyes_away", scope="module")
def fixture_eyes_away():
    with _runs(first=(), eyes_away=True) as found:
        yield found


@pytest.fixture(name="without_ct", scope="module")
def fixture_without_ct(reviewed_low):
    return _second(reviewed_low, name="w", without_ct=True)


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
    # So are the PET slices, which the run sets to zero in the block.
    assert counts[VisualFeaturesReason.OTHER_PIXEL_DATA.value] == changed + len(
        _PET_SLICES
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
    assert report["face_review"]["ct_series"] == {"defaced": 1, "not_defaced": []}
    counts = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert counts[held.reason.value] == len(_UNDEFACED)


def _contours(dataset):
    """Each ROI's contours by its name in :data:`_ROIS`, as points, or None
    where it has no Contour Sequence.

    The ROIs are known by their numbers, from 1 in that order, since the run
    cleans their names."""
    names = list(_ROIS)
    return {
        names[int(item.ReferencedROINumber) - 1]: (
            [
                np.array([float(v) for v in contour.ContourData]).reshape(-1, 3)
                for contour in item.ContourSequence
            ]
            if "ContourSequence" in item
            else None
        )
        for item in dataset.ROIContourSequence
    }


def _behind(block, z):
    """The axial plane at ``z`` behind the block's vertical plane, or all of
    it below the block, as a polygon."""
    if z <= block.inferior_limit:
        return shapely.geometry.box(-1e4, -1e4, 1e4, 1e4)
    origin = np.array(block.origin[:2])
    anterior = np.array(block.anterior[:2]) / np.linalg.norm(block.anterior[:2])
    along = np.array([-anterior[1], anterior[0]])
    return shapely.geometry.Polygon(
        [
            origin + 1e4 * along,
            origin - 1e4 * along,
            origin - 1e4 * along - 1e4 * anterior,
            origin + 1e4 * along - 1e4 * anterior,
        ]
    )


def _written_as_air(outcomes, block, z):
    """The parts in the block of the squares of the pixels of the head's CT
    slice at ``z`` that the run wrote as air there, as a polygon, read from
    the released slice."""
    (index,) = [i for i, each in enumerate(_SCAN.positions) if each[2] == z]
    _, dataset = outcomes[_head_name(index)]
    written = pydicom.pixels.apply_rescale(pydicom.pixels.pixel_array(dataset), dataset)
    points = _SCAN.points(index)
    air = block.contains(points) & (written == -1000)
    half = _SCAN.spacing[0] / 2
    squares = shapely.ops.unary_union(
        [
            shapely.geometry.box(x - half, y - half, x + half, y + half)
            for x, y in points[air][:, :2]
        ]
    )
    return squares.difference(_behind(block, z))


def _region(contours):
    """The region that contours in one plane bound together, by exclusive
    or."""
    region = shapely.geometry.Polygon()
    for points in contours:
        region = region.symmetric_difference(shapely.geometry.Polygon(points[:, :2]))
    return region


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


@pytest.mark.deid_requirement("PS3.15-E.3.2-01")
def test_the_head_structure_set_and_pet_seen_as_received_are_held_once_cut(
    as_received,
):
    _, outcomes, reasons, _ = as_received

    # The reviewer saw them as received, which the run, cutting them by the
    # block, no longer writes.
    assert outcomes[_STRUCTURE_SET] == ("held-for-review", None)
    assert reasons[_STRUCTURE_SET] == {
        HeldVisualFeatures(VisualFeaturesReason.OTHER_CONTOURS)
    }
    for name in _PET_SLICES:
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


def test_an_eye_drawn_away_from_the_globes_holds_the_head_ct(eyes_away):
    slices, outcomes, reasons, report = eyes_away
    held = HeldVisualFeatures(VisualFeaturesReason.EYES_DISAGREE_WITH_ROIS)

    # The structure set draws the left eye where the finder found no globe,
    # so the block may be wrong: the series is not defaced, and is held.
    for index in range(len(slices)):
        assert outcomes[_head_name(index)] == ("held-for-review", None), index
        assert held in reasons[_head_name(index)]
    assert report["face_review"]["ct_series"] == {
        "defaced": 0,
        "not_defaced": [{"reason": "eyes-disagree-with-rois", "count": 1}],
    }
    counts = {
        entry["code"]: entry["count"]
        for entry in report["held_for_review"]
        if entry["stage"] == "visual-features"
    }
    assert counts[held.reason.value] == len(slices)
    # With no series defaced, the structure set is written as received.
    disposition, dataset = outcomes[_STRUCTURE_SET]
    assert disposition == "released", reasons[_STRUCTURE_SET]
    assert all(contours is not None for contours in _contours(dataset).values())


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
    assert report["face_review"]["ct_series"] == {"defaced": 1, "not_defaced": []}
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
    assert report["face_review"]["ct_series"] == {"defaced": 1, "not_defaced": []}


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
