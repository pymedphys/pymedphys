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

"""The analytic head, the synthetic collection around it, and the two runs
under Clean Recognizable Visual Features that the CT defacing run modules,
test_deidentify_ct_defacing_run.py and
test_deidentify_ct_defacing_review_runs.py, review: the RT Structure Set
replaced by one of the head, one RT Dose by a grid over the head, the PET
Image by two slices of the head, and the BINARY Segmentation by one of the
head's body. Every UID and value here is invented."""

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
from pymedphys._imports import pydicom, shapely

from pymedphys._dicom.deidentify import dose_defacing, face_blocks, run
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.face_review import FaceReview, read_face_review
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.policy import CLEAN_PIXEL_DATA, compose_policy
from pymedphys._dicom.deidentify.qc_attestation import (
    Face,
    Redaction,
    RedactionVerdict,
    previewed_redactions,
)
from pymedphys._dicom.deidentify.qc_pack import new_reference
from pymedphys._dicom.deidentify.redaction_review import read_redaction_review
from pymedphys._dicom.deidentify.references import InstanceRecord

from . import _synthetic_compressed as compressed_files
from . import _synthetic_head as head
from . import _synthetic_head_dicom as files
from .test_deidentify_visual_features_option import KEY, _attest, _CornerFinder, _policy

# As coarse and short as the face block's finder allows, since every slice
# goes through two runs.
_SCAN = head.axial(
    spacing=2.5, thickness=5.0, extent=((-100, 100), (-130, 110), (-30, 110))
)
# The CT's grid less its last row and column, 96 rows by 80 columns, so
# that each 1-bit frame of a Segmentation on it fills whole bytes.
_SEGMENTED = head.axial(
    spacing=2.5, thickness=5.0, extent=((-100, 97.5), (-130, 107.5), (-30, 110))
)
_CT_FILES = ("01-ct-1.dcm", "02-ct-2.dcm", corpus_module.SEQUESTERED_FILE)
_STRUCTURE_SET = "04-rtstruct.dcm"
_DOSE = ("06-rtdose.dcm", "07-rtdose-review.dcm")
_PET = ("15-pet.dcm", "16-pet-enhanced.dcm", "17-pet-legacy-enhanced.dcm")
# A second PET slice of the head, in the first's series.
_PET_ABOVE = "15-pet-above.dcm"
# The BINARY Segmentation, replaced by a segment of the head's body.
_SEGMENTATION = corpus_module.SEGMENTATION_FILES[0]
# The head's BINARY Segmentation and the corpus's label map, both in the head
# CT's frame.
_SEGMENTATIONS = (_SEGMENTATION, corpus_module.SEGMENTATION_FILES[1])
# The instances in the head's frame whose series a review marks absent, the
# collection's Nuclear Medicine image among them.
_IN_FRAME = (
    _STRUCTURE_SET,
    *_DOSE,
    *_PET,
    _PET_ABOVE,
    _SEGMENTATION,
    corpus_module.NM_FILE,
)
# The PET instances that the run does not clean, and the collection's Nuclear
# Medicine image, which no run cleans, all in the head's Frame of Reference.
_UNDEFACED = (*_PET[1:], corpus_module.NM_FILE)
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
# The instances that the run with the deformable registrations does not
# clean in the head's defaced frame: the PET instances, the Nuclear Medicine
# image, and each registration tied to that frame, each of which its pack
# shows whole.
_UNDEFACED_WITH_REGISTRATIONS = (*_UNDEFACED, *_TIED, _COLLECTION_REGISTRATION)


def _dose(low):
    stored = np.full((15, 49, 41), low, dtype=np.uint32)
    # Rows from y = -130 mm at 5 mm: those from 50 mm are behind the head's
    # centre.
    stored[:, 36:, :] = _HIGHEST
    return stored


def _head_name(index, phase=0):
    return (
        f"01-head-{index:03d}.dcm" if not phase else f"01-head-t{phase}-{index:03d}.dcm"
    )


def _phased(data, phase):
    """A head slice as one of a time point's, from 0, which names it by its
    Temporal Position Identifier, with a SOP Instance UID of its own."""
    dataset = pydicom.dcmread(io.BytesIO(data))
    dataset.TemporalPositionIdentifier = phase + 1
    if phase:
        dataset.SOPInstanceUID = f"{dataset.SOPInstanceUID}.{phase}"
        dataset.file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
    return files.written(dataset)


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


def _body(index):
    """The head's body on the slice of :data:`_SEGMENTED` at ``index``: each
    pixel that is not air."""
    return head.hounsfield(_SEGMENTED.points(index)) > head.AIR


def _head_segmentation(template):
    """A segment of the head's body, a frame on each of the CT's slices, as
    a mask of the body could be, which traces the face."""
    return files.segmentation(
        _SEGMENTED,
        [np.stack([_body(index) for index in range(len(_SEGMENTED.positions))])],
        frame=corpus_module.FRAME_OF_REFERENCE,
        series=corpus_module.CT_SERIES,
        instance=template.SOPInstanceUID,
        keep_empty=True,
        template=template,
    )


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


# A second series of the head's slices, in a frame of its own, a slice of
# which the first RT Dose refers to.
_ELSEWHERE_SERIES = corpus_module.CT_SERIES + ".800"
_ELSEWHERE_FRAME = files.ROOT + ".82"


def _elsewhere_name(index):
    return f"01-head-elsewhere-{index:03d}.dcm"


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
    time_points=1,
    registrations=False,
    elsewhere=False,
):
    """Run the collection, with its CT slices replaced by the head's, as one
    Enhanced CT Image instance if ``multi_frame``, or as ``time_points`` time
    points of one series at the same positions, each naming its Temporal
    Position Identifier where there are more than one (:func:`_phased`), its
    RT Structure Set by the head's ROIs, with a target in the block, by
    :data:`_TARGETS`, if ``target``, its PET
    Image by :data:`_PET_SLICES`, and, if ``multi_frame``, its Enhanced PET
    Image by those slices as one instance, its BINARY Segmentation by
    :func:`_head_segmentation`, and its first RT Dose
    by a grid over the head of ``dose`` where given, with the RT Dose
    instances of :data:`_UNPLACEABLE` and :data:`_DVH_ONLY` in its series if
    ``edges``, the head's CT and PET slices and that RT Dose compressed in
    :data:`_COMPRESSED` in turn if ``compressed``, and the deformable
    registrations of :data:`_REGISTRATIONS` if ``registrations``, under
    ``basic``, or under the option and ``first`` with no face verdicts.
    If ``phases``, a second head series shares its frame, the structure set
    also declares an undefaced frame, and an ERROR dose and slab structure
    set are added (:data:`_ERROR_DOSE`, :data:`_SLAB_STRUCTURE_SET`).
    If ``elsewhere``, a second head series is in a frame of its own
    (:data:`_ELSEWHERE_FRAME`), and the first RT Dose refers to its first
    slice."""
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
            for phase in range(time_points):
                for index, data in enumerate(slices):
                    (instances / _head_name(index, phase)).write_bytes(
                        data if time_points == 1 else _phased(data, phase)
                    )
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
        if elsewhere:
            others = files.ct_files(
                _SCAN,
                head.Head(noise=0.0),
                series=_ELSEWHERE_SERIES,
                frame=_ELSEWHERE_FRAME,
                template=template,
            )
            for index, data in enumerate(others):
                (instances / _elsewhere_name(index)).write_bytes(data)
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
        if elsewhere:
            grid = pydicom.dcmread(instances / _DOSE[0])
            other = pydicom.dcmread(io.BytesIO(others[0]))
            image = pydicom.Dataset()
            image.ReferencedSOPClassUID = other.SOPClassUID
            image.ReferencedSOPInstanceUID = other.SOPInstanceUID
            grid.ReferencedInstanceSequence = [image]
            (instances / _DOSE[0]).write_bytes(files.written(grid))
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
        segmentation = pydicom.dcmread(instances / _SEGMENTATION)
        (instances / _SEGMENTATION).write_bytes(_head_segmentation(segmentation))
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
    instance_faces=None,
):
    """Attest a copy of the reviewed run's pack, in ``name`` beside it, with
    the head's series, and those of the RT Structure Set, RT Dose, PET, and
    Segmentation in its frame, and of the deformable registrations, marked
    absent, but for the series of each file named in ``present``, marked
    present, and, if ``accepted``, the regions of each
    of the head's CT and PET slices that the pack previews accepted, or, if
    ``revised``, those of each of its CT slices, revised with that region
    added in their first frame, and, if ``confirmed``, each face block that
    the pack shows beside the eyes drawn confirmed, the choice for each
    RT Dose that ``dose_choices`` names by its file, and the face verdict of
    its own for each instance that ``instance_faces`` names by its file; and
    run the collection
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
    # The reviewer was shown every frame of each instance.
    redactions = (
        [
            RedactionVerdict(position, **verdict, seen=tuple(range(shape.frames)))
            for position, shape in previewed_redactions(
                reviewed.pack.read_bytes()
            ).items()
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
        instance_faces={
            by_name[file]: face for file, face in (instance_faces or {}).items()
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


def _block(slices):
    records = {
        index: InstanceRecord.from_file(data) for index, data in enumerate(slices)
    }
    outcomes = face_blocks.find_face_blocks(records, lambda index: slices[index])
    (outcome,) = list(outcomes.values())
    return outcome.block


def _undefaced_listed(reviewed, name=None):
    """The undefaced instances of the reviewed run's pack, or of the run that
    :func:`_second` made of it in ``name``, by file name."""
    again = reviewed if name is None else _reviewed_again(reviewed, name)
    document = json.loads(again.pack.read_text("utf-8"))
    return {
        again.names[entry["position"]]: entry
        for entry in document["undefaced_instances"]
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


def _output_name(dataset):
    return (
        f"{dataset.PatientID}/{dataset.StudyInstanceUID}/"
        f"{dataset.SeriesInstanceUID}/{dataset.SOPInstanceUID}.dcm"
    )
