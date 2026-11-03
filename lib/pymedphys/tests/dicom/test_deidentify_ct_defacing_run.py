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
import io
import json
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest, shapely

from pymedphys._dicom.deidentify import (
    defacing,
    dose_defacing,
    face_blocks,
    markers,
    qc_previews,
    run,
)
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
    DoseChoice,
    HeldPixelData,
    HeldVisualFeatures,
    PixelDataReason,
    VisualFeaturesReason,
)
from pymedphys._dicom.deidentify.redaction_review import read_redaction_review
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.release_gate import ReleaseReason
from pymedphys._dicom.deidentify.target_hulls import TargetHull
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _synthetic_compressed as compressed_files
from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from . import _synthetic_rtdose as rtdose
from ._corpus_run import decoders_installed
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
# The head's slices as one Enhanced CT Image instance, and its PET slices as
# one Enhanced PET Image instance in place of the collection's.
_HEAD_ENHANCED = "01-head-enhanced.dcm"
_PET_ENHANCED = _PET[1]
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
# The transfer syntaxes of the head's compressed slices, PET slices, and RT
# Dose, in turn: decoded in the decoding child and in process.
_COMPRESSED = (compressed_files.JPEG_2000_LOSSLESS, compressed_files.RLE_LOSSLESS)
# The synthetic collection's Enhanced CT Image and Legacy Converted Enhanced
# CT Image instances, whose frames no functional groups place, are each a
# CT series that the run cannot deface.
_UNPLACED = 2
# Deformable registrations, each with a grid that the run does not cut,
# named by how they are tied to the head's Frame of Reference: as their own
# frame, the Registered Frame of Reference, in which the grid lies; as the
# Source Frame of Reference of an item; by a reference to a slice of the
# head; by an item that names no Source Frame of Reference; or not at all.
_ELSEWHERE = files.ROOT + ".81"
_TIED = (
    "19-registration-own-frame.dcm",
    "19-registration-source-frame.dcm",
    "19-registration-slice.dcm",
    "19-registration-no-source.dcm",
)
_UNTIED = "19-registration-elsewhere.dcm"
_REGISTRATIONS = (*_TIED, _UNTIED)
# The collection's own deformable registration, of the PET Image to the
# head's Frame of Reference, which no series of its own marks absent.
_COLLECTION_REGISTRATION = "19-registration-deformable.dcm"


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
# A target in the block, before the right globe, on three slices, which the
# run keeps with whatever lies between its contours.
_KEPT_TARGET_HALF = 4.0
_KEPT_TARGET = (
    "PTV",
    [
        files.square((*_IN_THE_BLOCK[:2], z), _KEPT_TARGET_HALF)
        for z in (15.0, 20.0, 25.0)
    ],
)
# A target in the block drawn past the front of the scan's field of view,
# whose part beyond the slices no image shows, so that the run cannot keep
# it within the images.
_BEYOND_TARGET = (
    "PTV",
    [
        files.square((_IN_THE_BLOCK[0], _SCAN.positions[0][1] + 2.0, z), 4.0)
        for z in (15.0, 20.0, 25.0)
    ],
)
# The ROIs that the run adds to the head's, by ``target``.
_TARGETS = {"kept": _KEPT_TARGET, "beyond": _BEYOND_TARGET}
_TARGET_NAME = "PTV_Orbit"


def _rois(target=False):
    """The head's ROIs, with the requested target from main's fixture."""
    return {**_ROIS, _TARGET_NAME: _TARGETS[target]} if target else dict(_ROIS)


def _head_structure_set(template, *, eyes_away=False, target=False, frames=False):
    rois = _rois(target)
    if eyes_away:
        # The left eye drawn 40 mm below its globe, where the finder found
        # none.
        rois["Eye_L"] = ("ORGAN", _eye(1, below=40.0))
    data = files.structure_set(
        list(rois.values()),
        frame=corpus_module.FRAME_OF_REFERENCE,
        template=template,
        names=list(rois),
    )
    if not frames:
        return data
    # A frame that the run holds no image of, declared, with an ROI there
    # that reaches where the block would be in the head's frame.
    dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))
    other = files.structure_set(
        [("ORGAN", files.square(_IN_THE_BLOCK, 10.0))],
        frame=_OTHER_FRAME,
        names=["Other"],
    )
    added = pydicom.dcmread(pydicom.filebase.DicomBytesIO(other))
    number = len(rois) + 1
    for keyword in (
        "ReferencedFrameOfReferenceSequence",
        "StructureSetROISequence",
        "ROIContourSequence",
        "RTROIObservationsSequence",
    ):
        (item,) = getattr(added, keyword)
        for attribute in ("ROINumber", "ReferencedROINumber", "ObservationNumber"):
            if attribute in item:
                setattr(item, attribute, number)
        getattr(dataset, keyword).append(item)
    return files.written(dataset)


# A second series of the head's slices in their frame, and the frame that
# the structure set also declares, of no image of the run.
_PHASE_SERIES = corpus_module.CT_SERIES + ".900"
_OTHER_FRAME = corpus_module.FRAME_OF_REFERENCE + ".9"
_ERROR_DOSE = "06-rtdose-error.dcm"
_SLAB_STRUCTURE_SET = "04-rtstruct-slab.dcm"


def _phase_name(index):
    return f"01-head-phase-{index:03d}.dcm"


def _error(stored):
    """A grid of differences: of either sign at the low dose in the block,
    and of the greatest magnitude, negative, behind the head."""
    signs = np.where(np.indices(stored.shape).sum(axis=0) % 2, 1, -1)
    differences = (stored.astype(np.int64) * signs).astype(np.int32)
    differences[:, 36:, :] = -_HIGHEST
    return differences


def _slab_structure_set(template):
    """A structure set of the head's frame, in the template's series, with
    one ROI whose contour, 40 mm below the globes and across the block's
    vertical plane, has a slab 100 mm thick, which reaches the block, so
    that its part behind the plane is kept."""
    data = files.structure_set(
        [
            (
                "ORGAN",
                files.square((-32.0, head.GLOBE_Y + 5.0, head.GLOBE_Z - 40.0), 10.0),
            )
        ],
        frame=corpus_module.FRAME_OF_REFERENCE,
        template=template,
        names=["Slab"],
    )
    dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))
    dataset.SOPInstanceUID = f"{template.SOPInstanceUID}.30"
    dataset.file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
    (contour,) = dataset.ROIContourSequence[0].ContourSequence
    contour.ContourSlabThickness = "100"
    return files.written(dataset)


def _error_dose(grid):
    data = files.dose(
        _error(_dose(_LOW)),
        **_GRID,
        frame=corpus_module.FRAME_OF_REFERENCE,
        instance=f"{grid.SOPInstanceUID}.20",
        template=grid,
    )
    dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))
    dataset.DoseType = "ERROR"
    return files.written(dataset)


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
def _runs(
    *others,
    without_ct=False,
    accepted=False,
    revised=None,
    confirmed=False,
    dose_choices=None,
    **first_run,
):
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
            confirmed=confirmed,
            dose_choices=dose_choices,
        )


def _registrations(slices):
    """Each deformable registration of :data:`_REGISTRATIONS`, by name."""
    vectors = np.zeros((2, 3, 4, 3), np.float32)
    vectors[1, 1, 1:3] = (1.0, -2.0, 0.5)
    grid = (vectors, (-20.0, -90.0, 10.0), (5.0, 5.0, 5.0))
    frame = corpus_module.FRAME_OF_REFERENCE
    ties = {
        _TIED[0]: {"frame": frame, "sources": (_ELSEWHERE,)},
        _TIED[1]: {"frame": _ELSEWHERE, "sources": (frame,)},
        _TIED[2]: {"frame": _ELSEWHERE},
        _TIED[3]: {"frame": _ELSEWHERE},
        _UNTIED: {"frame": _ELSEWHERE},
    }
    found = {}
    for index, (name, tie) in enumerate(ties.items()):
        dataset = pydicom.dcmread(
            io.BytesIO(
                files.registration(
                    [grid], instance=f"{files.ROOT}.9.{index + 2}", **tie
                )
            )
        )
        (item,) = dataset.DeformableRegistrationSequence
        if name == _TIED[2]:
            slice_ = pydicom.dcmread(io.BytesIO(slices[0]))
            reference = pydicom.Dataset()
            reference.ReferencedSOPClassUID = slice_.SOPClassUID
            reference.ReferencedSOPInstanceUID = slice_.SOPInstanceUID
            item.ReferencedImageSequence = [reference]
        if name == _TIED[3]:
            del item.SourceFrameOfReferenceUID
        found[name] = files.written(dataset)
    return found


@contextlib.contextmanager
def _reviewed(
    first=None,
    target=False,
    eyes_away=False,
    dose=None,
    edges=False,
    multi_frame=False,
    compressed=False,
    phases=False,
    registrations=False,
):
    """Run the collection, with its CT slices replaced by the head's, as one
    Enhanced CT Image instance if ``multi_frame``, its RT Structure Set by
    the head's ROIs, with a target in the block, by :data:`_TARGETS`, if
    ``target``, its PET
    Image by :data:`_PET_SLICES`, and, if ``multi_frame``, its Enhanced PET
    Image by those slices as one instance, and its first RT Dose
    by a grid over the head of ``dose`` where given, with the RT Dose
    instances of :data:`_UNPLACEABLE` and :data:`_DVH_ONLY` in its series if
    ``edges``, the head's CT and PET slices and that RT Dose compressed in
    :data:`_COMPRESSED` in turn if ``compressed``, and the deformable
    registrations of :data:`_REGISTRATIONS` if ``registrations``, under
    ``basic``, or under the option and ``first`` with no face verdicts.
    If ``phases``, a second head series shares its frame, the structure set
    also declares an undefaced frame, and an ERROR dose and slab structure
    set are added (:data:`_ERROR_DOSE`, :data:`_SLAB_STRUCTURE_SET`)."""
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
        if multi_frame:
            (instances / _HEAD_ENHANCED).write_bytes(
                files.multi_frame(slices, instance=corpus_module.CT_SERIES + ".1000")
            )
        else:
            for index, data in enumerate(slices):
                (instances / _head_name(index)).write_bytes(data)
        if phases:
            for index, data in enumerate(
                files.ct_files(
                    _SCAN,
                    head.Head(noise=0.0),
                    series=_PHASE_SERIES,
                    frame=corpus_module.FRAME_OF_REFERENCE,
                    template=template,
                )
            ):
                (instances / _phase_name(index)).write_bytes(data)
        if registrations:
            for name, data in _registrations(slices).items():
                (instances / name).write_bytes(data)
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
            _head_structure_set(rtss, eyes_away=eyes_away, target=target, frames=phases)
        )
        if phases:
            grid = pydicom.dcmread(instances / _DOSE[0])
            (instances / _ERROR_DOSE).write_bytes(_error_dose(grid))
            (instances / _SLAB_STRUCTURE_SET).write_bytes(_slab_structure_set(rtss))
        pet = pydicom.dcmread(instances / _PET[0])
        pet_slices = [
            files.pet(
                _pet_uptake(z),
                position=(*_PET_GRID["position"], z),
                spacing=_PET_GRID["spacing"],
                frame=corpus_module.FRAME_OF_REFERENCE,
                instance=pet.SOPInstanceUID + ("" if index == 0 else ".1"),
                template=pet,
            )
            for index, z in enumerate(_PET_SLICES.values())
        ]
        for name, data in zip(_PET_SLICES, pet_slices):
            (instances / name).write_bytes(data)
        if multi_frame:
            enhanced = pydicom.dcmread(instances / _PET_ENHANCED)
            (instances / _PET_ENHANCED).write_bytes(
                files.multi_frame(
                    pet_slices,
                    sop_class=files.ENHANCED_PET_IMAGE_STORAGE,
                    instance=enhanced.SOPInstanceUID,
                    rescale_type="US",
                    template=enhanced,
                    mapped=True,
                )
            )
        if compressed:
            names = [
                *sorted(path.name for path in instances.glob("01-head*")),
                *_PET_SLICES,
                *(_DOSE[:1] if dose is not None else ()),
            ]
            for index, name in enumerate(names):
                path = instances / name
                path.write_bytes(
                    compressed_files.compressed_file(
                        path.read_bytes(), _COMPRESSED[index % len(_COMPRESSED)]
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
                names[p].startswith("01-head")
                or names[p] in _IN_FRAME
                or names[p] in _REGISTRATIONS
                for p in s["positions"]
            )
        ]
        yield _Reviewed(directory, instances, slices, reviewed.qc_pack, names, marked)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _second(
    reviewed,
    *others,
    name,
    without_ct=False,
    accepted=False,
    revised=None,
    confirmed=False,
    dose_choices=None,
    present=(),
):
    """Attest a copy of the reviewed run's pack, in ``name`` beside it, with
    the head's series, and those of the RT Structure Set, RT Dose, and PET
    in its frame, and of the deformable registrations, marked absent, but for the series of each file named in
    ``present``, marked present, and, if ``accepted``, the regions of each
    of the head's CT and PET slices that the pack previews accepted, or, if
    ``revised``, those of each of its CT slices, revised with that region
    added in their first frame, and, if ``confirmed``, each face block that
    the pack shows beside the eyes drawn confirmed, and the choice for each
    RT Dose that ``dose_choices`` names by its file; and run the collection
    again under the option and ``others``, given those verdicts, without
    the head's slices if ``without_ct``.

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
    document = json.loads(reviewed.pack.read_text("utf-8"))
    checks = document["eye_checks"]
    by_name = {name: position for position, name in reviewed.names.items()}
    shown = {
        each["positions"][0]: {reviewed.names[p] for p in each["positions"]}
        for each in document["series"]
    }
    _attest(
        pack,
        {
            first: Face.PRESENT if files & set(present) else Face.ABSENT
            for first, files in shown.items()
            if first in reviewed.marked
        },
        redactions=redactions,
        confirmed_blocks=(
            [check["positions"][0] for check in checks] if confirmed else ()
        ),
        dose_choices={
            by_name[file]: choice for file, choice in (dose_choices or {}).items()
        },
    )
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
    with _reviewed(first=(), dose=_dose(_LOW), registrations=True) as found:
        yield found


@pytest.fixture(name="reviewed_with_pixel_data", scope="module")
def fixture_reviewed_with_pixel_data():
    with _reviewed(first=(CLEAN_PIXEL_DATA,)) as found:
        yield found


@pytest.fixture(name="defaced", scope="module")
def fixture_defaced(reviewed_low):
    return _second(reviewed_low, name="d")


@pytest.fixture(name="multi_frame", scope="module")
def fixture_multi_frame():
    with _runs(first=(), dose=_dose(_LOW), multi_frame=True) as found:
        yield found


@pytest.fixture(name="phases", scope="module")
def fixture_phases():
    with _runs(first=(), dose=_dose(_LOW), phases=True) as found:
        yield found


@pytest.fixture(name="compressed", scope="module")
def fixture_compressed():
    with _runs(first=(), dose=_dose(_LOW), compressed=True) as found:
        yield found


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


def _reviewed_again(reviewed, name):
    """The run that :func:`_second` made of ``reviewed`` in ``name``, as one
    for :func:`_second` to review in turn."""
    directory = reviewed.directory / name
    (pack,) = (directory / "qc2").rglob("qc-pack.json")
    entries = json.loads(pack.read_text("utf-8"))
    names = {e["position"]: Path(e["source"]).name for e in entries["instances"]}
    marked = [
        s["positions"][0]
        for s in entries["series"]
        if any(
            names[p].startswith("01-head") or names[p] in _IN_FRAME
            for p in s["positions"]
        )
    ]
    return _Reviewed(
        directory, reviewed.instances, reviewed.slices, pack, names, marked
    )


@pytest.fixture(name="as_received", scope="module")
def fixture_as_received():
    with _runs() as found:
        yield found


# Marked absent as the run wrote them, around the target that it kept.
@pytest.fixture(name="targeted", scope="module")
def fixture_targeted():
    with _runs(first=(), target="kept", dose=_dose(_LOW)) as found:
        yield found


@pytest.fixture(name="beyond_slices", scope="module")
def fixture_beyond_slices():
    with _runs(target="beyond") as found:
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


def _contours(dataset, target=False):
    """Each ROI's contours by its name in :func:`_rois` of ``target``, as
    points, or None where it has no Contour Sequence.

    The ROIs are known by their numbers, from 1 in that order, since the run
    cleans their names."""
    names = list(_rois(target))
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


def _output_name(dataset):
    return (
        f"{dataset.PatientID}/{dataset.StudyInstanceUID}/"
        f"{dataset.SeriesInstanceUID}/{dataset.SOPInstanceUID}.dcm"
    )


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
    for name in (_STRUCTURE_SET, _DOSE[0], *_PET_SLICES):
        assert outcomes[name] == ("held-for-review", None), name
        assert reasons[name] == {held}, name
    # As is the RT Dose that its release gate also holds for review.
    assert outcomes[_DOSE[1]] == ("held-for-review", None)
    assert held in reasons[_DOSE[1]]
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
        len(slices) + 1 + len(_DOSE) + len(_PET_SLICES)
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
