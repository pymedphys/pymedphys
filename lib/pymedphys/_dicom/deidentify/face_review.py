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

# pylint: disable = too-many-lines

"""A reviewer's face verdicts, for the Clean Recognizable Visual Features Option.

A run claims the option (PS3.15 E.3.2) only for an instance that cannot
show a face, or in which a reviewer found no recognisable face, whether or
not it removes a face block from the instance
(:mod:`~pymedphys._dicom.deidentify.face_blocks`). The reviewer records a verdict for
each series of a first run's QC pack, by its first run position, in the
pack's attestation (:mod:`~pymedphys._dicom.deidentify.qc_attestation`),
and the pack records the SHA-256 of each source file of each series. A
second run of the same files under a policy that selects the option is
given that pack (:func:`read_face_review`). The pack also records the
SHA-256 of the pixel data of each file that the first run wrote
(:func:`pixel_data_sha256`), only where previews that could show a face
draw every frame of them, which for an RT Dose (:func:`is_rt_dose`) only
dose-levels previews do, and for a Segmentation (:func:`is_segmentation`)
only its segments sheet, and the second run holds pixel data of more frames
than they listed, counting for an RT Dose only its dose-levels previews' and
for a Segmentation only its segments sheet's;
of the contours of each RT Structure Set that it wrote
(:func:`contour_data_sha256`), only where its contour sheet shows them;
of the deformation grids of each deformable registration that it wrote
(:func:`grid_data_sha256`), only where its grid sheets show every one of
them (:mod:`~pymedphys._dicom.deidentify.qc_grids`); and of the surface
meshes of each Surface Segmentation that it wrote
(:func:`surface_data_sha256`), only where its surfaces sheet shows every
one of them (:mod:`~pymedphys._dicom.deidentify.qc_meshes`). An instance
that carries visual features (:func:`carries_visual_features`) satisfies
the option only where the SHA-256 of its source file is that of an
instance of a series marked absent, and the pixel data, contours,
deformation grids, and surface meshes that the second run writes are those
that the first run wrote of it; any other such instance is held for review
(:func:`FaceReview.hold_reason`), so it is never released. A source file
changed since the review no longer matches, and nor does one whose pixel
data, contours, grids, or meshes the second run writes otherwise, such as a CT slice defaced since the reviewer saw it
as received, or blacked out in other regions, or a structure set cut by a
face block that the first run did not find.

An RT Dose that the reviewed run held because it has too much dose in a
defaced series' face block to set to zero there is likewise not covered by
a verdict on its series, unless the attestation also chose to have it
written as received (:class:`~.reasons.DoseChoice`), which makes the
verdict one on its own dose-levels previews of it as received. The review
gives each dose choice, the attestation's or else the one that the reviewed
run applied, by the digest that binds it to the RT Dose's source file and
the block (:attr:`FaceReview.dose_choices`).

An instance that the reviewed run released or held in a defaced CT series'
Frame of Reference, naming none, or referring to a defaced slice, whose
outline, pixel data, or deformation grids it did not clean of the face,
which the pack lists in its ``undefaced_instances``, is never covered by a
verdict on its series, since the reviewer may have judged that beside the
defaced CT. It is covered only by a face verdict of its own, which the
attestation gives by its run position, from the pack's previews of it
alone, which the pack lists as shown only where they draw every frame of
its pixel data, every contour, and every deformation grid as written
(:attr:`FaceReview.own_verdicts`). Its own verdict counts as a verdict on
its file as a series' does, so a verdict of absent releases it only where
a later run writes the pixel data, contours, and grids that the pack
showed, and a verdict of present on it, or on its series, holds it.

The verdicts are read by digest, never by path or run position, so the
second run may discover the files in another order, or among others, which
have no verdict.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re

from pymedphys._imports import pydicom

from . import face_review_digests, qc_meshes
from .qc_attestation import (
    Face,
    Outcome,
    attested_pack,
    dose_checks,
    eye_checks,
    undefaced_instances,
)
from .qc_pack import (
    GRID_KINDS,
    NO_CONTOURS_SHA256,
    NO_GRIDS_SHA256,
    NO_PIXELS_SHA256,
    NO_SURFACES_SHA256,
    NotPreviewedReason,
    PreviewKind,
    QcPackError,
    pictured_frames,
)
from .pixel_risk import SEGMENTATION_SOP_CLASSES
from .qc_surfaces import RT_DOSE_STORAGE
from .reasons import DoseChoice, VisualFeaturesReason
from .uids import normalise_uid

# Float Pixel Data (7FE0,0008), Double Float Pixel Data (7FE0,0009), and
# Pixel Data (7FE0,0010), in the order that their digest takes them.
PIXEL_DATA_TAGS = (0x7FE00008, 0x7FE00009, 0x7FE00010)
# The IOD whose contours can trace a face, although it has no pixel data.
_RT_STRUCTURE_SET = "RT Structure Set"
# Deformable Registration Sequence (0064,0002), and the Deformable
# Registration Grid Sequence (0064,0005) in its items, whose Vector Grid Data
# (0064,0009) can follow the patient's outline.
DEFORMABLE_REGISTRATION_SEQUENCE = 0x00640002
DEFORMABLE_REGISTRATION_GRID_SEQUENCE = 0x00640005
# Each grid's Image Orientation (Patient), Image Position (Patient), Grid
# Dimensions, Grid Resolution, and Vector Grid Data, in the order that its
# digest takes them; the first four place the grid, and the last gives its
# displacements.
GRID_TAGS = (0x00200037, 0x00200032, 0x00640007, 0x00640008, 0x00640009)
# Surface Sequence (0066,0002) of the Surface Mesh Module (PS3.3 Section
# C.27.1), whose items' Point Coordinates Data (0066,0016) place each point
# of a mesh in the patient, so that a mesh of the skin traces the face.
SURFACE_SEQUENCE = qc_meshes.SURFACE_SEQUENCE
# The Surface Points Sequence (0066,0011) of a Surface Sequence item, and
# the elements of its item that place its points: Point Coordinates Data
# (0066,0016), and Double Point Coordinates Data (0066,0022), which no
# sheet draws, in the order that the digest takes them.
SURFACE_POINTS = (
    qc_meshes.SURFACE_POINTS_SEQUENCE,
    (qc_meshes.POINT_COORDINATES_DATA, qc_meshes.DOUBLE_POINT_COORDINATES_DATA),
)
# The Surface Mesh Primitives Sequence (0066,0013) of a Surface Sequence
# item, its items' Vertex, Edge, and Triangle Point Index Lists, Long and
# retired, its items' Triangle Strip, Triangle Fan, Line, and Facet
# Sequences, and their items' Primitive Point Index Lists, Long and
# retired, in the order that the digest takes them.
SURFACE_PRIMITIVES = (
    qc_meshes.SURFACE_MESH_PRIMITIVES_SEQUENCE,
    (*qc_meshes.VERTEX_LISTS, *qc_meshes.EDGE_LISTS, *qc_meshes.TRIANGLE_LISTS),
    (
        qc_meshes.TRIANGLE_STRIP_SEQUENCE,
        qc_meshes.TRIANGLE_FAN_SEQUENCE,
        qc_meshes.LINE_SEQUENCE,
        qc_meshes.FACET_SEQUENCE,
    ),
    qc_meshes.PRIMITIVE_LISTS,
)
# The IOD whose instances hold surface meshes (PS3.3 Section A.57).
SURFACE_SEGMENTATION = "Surface Segmentation"
# Source Frame of Reference UID (0064,0003), in each item of the Deformable
# Registration Sequence, and the top-level Frame of Reference UID, the
# Registered Frame of Reference, in which a grid lies.
SOURCE_FRAME_OF_REFERENCE = 0x00640003
FRAME_OF_REFERENCE = 0x00200052
_SHA256 = re.compile(r"[0-9a-f]{64}")
_NO_PIXELS = bytes.fromhex(NO_PIXELS_SHA256)
NO_GRIDS = bytes.fromhex(NO_GRIDS_SHA256)
NO_SURFACES = bytes.fromhex(NO_SURFACES_SHA256)


@dataclasses.dataclass(frozen=True, repr=False)
class FaceReview:
    """The source files of a reviewed QC pack's series, by the reviewer's verdict.

    Its ``repr`` shows only the pack's reference and the counts.

    Attributes
    ----------
    reference : str
        The reviewed QC pack's opaque reference, ``A-`` and 32 hex digits,
        which the release report records.
    absent : frozenset of bytes
        The SHA-256 of each source file of each series that the reviewer
        marked :attr:`~.qc_attestation.Face.ABSENT`, other than one that the
        reviewed run held beside a CT series that it defaced
        (:attr:`~.reasons.VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME`),
        by its frame, by naming none, or by a reference to a defaced slice,
        or held as an RT Dose with too much dose in that series' block to
        set to zero (:attr:`~.reasons.VisualFeaturesReason.DOSE_IN_FACE_BLOCK`)
        where the attestation did not choose to have it written as received,
        and that of each source file of an instance that the reviewer gave
        a face verdict of its own of absent.
    present : frozenset of bytes
        Likewise, of each series marked :attr:`~.qc_attestation.Face.PRESENT`,
        and of each instance given a face verdict of its own of present.
    absent_pixels : frozenset of (bytes, bytes)
        The SHA-256 of each source file in ``absent`` whose written file the
        pack had, with the :func:`pixel_data_sha256` of that file's pixel
        data; empty by default, so that no instance satisfies the option.
    absent_contours : frozenset of (bytes, bytes)
        Likewise, with the :func:`contour_data_sha256` of that file's
        contours.
    absent_frames : frozenset of (bytes, bytes, int), optional
        For each pair in ``absent_pixels`` other than of no pixel data, how
        many frames, from the first, the pack's previews showed of it; an
        instance with more is held. :func:`read_face_review` always gives
        it; None, the default, bounds no instance's frames.
    absent_dose_frames : frozenset of (bytes, bytes, int), optional
        Likewise, how many frames its dose-levels previews showed, which
        alone show an RT Dose as it could show a face, so bound an RT
        Dose's. :func:`read_face_review` always gives it; None, the
        default, releases no RT Dose with pixel data.
    absent_grids : frozenset of (bytes, bytes), optional
        The SHA-256 of each source file in ``absent`` whose written file the
        pack had, with the :func:`grid_data_sha256` of that file's
        deformation grids, where its grid sheets showed every one of them,
        or it has none; empty by default, so that no instance with a grid
        satisfies the option.
    confirmed_blocks : frozenset of bytes, optional
        The digest of each face block that the reviewer confirmed, of a CT
        series that the reviewed run defaced and held because its eye ROIs
        disagree with its globes, as
        :func:`~pymedphys._dicom.deidentify.face_blocks.block_digest` gives
        it of the series' source files and the block; a run given the
        review defaces such a series without holding it for its eyes where
        it finds a block of this digest. Empty by default.
    dose_choices : frozenset of (bytes, DoseChoice, bool), optional
        For each RT Dose that the reviewed pack lists with too much dose in a
        face block to set to zero there, and for which the attestation gave a
        choice, or else the reviewed run applied one: the digest that binds
        the choice to its source file and the block, as
        :func:`~pymedphys._dicom.deidentify.dose_defacing.dose_check_digest`
        gives it, the choice, and whether the reviewed run wrote it set to
        zero, so that its previews showed it so. Each digest once; none by
        default.
    own_verdicts : frozenset of bytes, optional
        The SHA-256 of each source file of an instance that the reviewed
        pack lists in its ``undefaced_instances`` and that the reviewer gave
        a face verdict of its own, of either kind, which is in ``absent`` or
        ``present`` by that verdict; a run given the review holds such an
        instance, which it does not clean of the face in a defaced frame,
        by that verdict, as :meth:`hold_reason` gives it, in place of
        holding it for its frame. None by default.
    absent_segment_frames : frozenset of (bytes, bytes, int), optional
        Like ``absent_dose_frames``, how many frames its segments sheet
        showed, which alone shows a Segmentation (:func:`is_segmentation`)
        as it could show a face, since its cine strip and projection show a
        segment as windowed values rather than as the surface that it
        traces, so bound a Segmentation's. :func:`read_face_review` always
        gives it; None, the default, releases no Segmentation with pixel
        data.
    absent_surfaces : frozenset of (bytes, bytes), optional
        Like ``absent_grids``, with the :func:`surface_data_sha256` of that
        file's surface meshes, where its surfaces sheet showed every one of
        them, or it has none; empty by default, so that no instance with a
        mesh satisfies the option.
    """

    reference: str
    absent: frozenset[bytes]
    present: frozenset[bytes]
    absent_pixels: frozenset[tuple[bytes, bytes]] = frozenset()
    absent_contours: frozenset[tuple[bytes, bytes]] = frozenset()
    absent_frames: frozenset[tuple[bytes, bytes, int]] | None = None
    absent_dose_frames: frozenset[tuple[bytes, bytes, int]] | None = None
    absent_grids: frozenset[tuple[bytes, bytes]] = frozenset()
    confirmed_blocks: frozenset[bytes] = frozenset()
    dose_choices: frozenset[tuple[bytes, DoseChoice, bool]] = frozenset()
    own_verdicts: frozenset[bytes] = frozenset()
    absent_segment_frames: frozenset[tuple[bytes, bytes, int]] | None = None
    absent_surfaces: frozenset[tuple[bytes, bytes]] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not re.fullmatch(
            r"A-[0-9a-f]{32}", self.reference
        ):
            raise QcPackError("a face review needs the reviewed pack's reference")
        for digests in (
            self.absent,
            self.present,
            self.confirmed_blocks,
            self.own_verdicts,
        ):
            if not isinstance(digests, frozenset) or not all(
                isinstance(d, bytes) and len(d) == 32 for d in digests
            ):
                raise QcPackError("a face review's files are SHA-256 digests")
        for pairs in (
            self.absent_pixels,
            self.absent_contours,
            self.absent_grids,
            self.absent_surfaces,
        ):
            if not isinstance(pairs, frozenset) or not all(
                isinstance(pair, tuple)
                and len(pair) == 2
                and all(isinstance(d, bytes) and len(d) == 32 for d in pair)
                and pair[0] in self.absent
                for pair in pairs
            ):
                raise QcPackError(
                    "a face review's pixel data, contours, grids, and surfaces "
                    "are SHA-256 digests of files marked absent"
                )
        for counts in (
            self.absent_frames,
            self.absent_dose_frames,
            self.absent_segment_frames,
        ):
            if counts is not None and (
                not isinstance(counts, frozenset)
                or not all(
                    isinstance(each, tuple)
                    and len(each) == 3
                    and each[:2] in self.absent_pixels
                    and isinstance(each[2], int)
                    and not isinstance(each[2], bool)
                    and each[2] >= 1
                    for each in counts
                )
            ):
                raise QcPackError(
                    "a face review's frames shown are counts of pixel data "
                    "marked absent"
                )
        if (
            not isinstance(self.dose_choices, frozenset)
            or not all(
                isinstance(each, tuple)
                and len(each) == 3
                and isinstance(each[0], bytes)
                and len(each[0]) == 32
                and isinstance(each[1], DoseChoice)
                and isinstance(each[2], bool)
                for each in self.dose_choices
            )
            or len({each[0] for each in self.dose_choices}) != len(self.dose_choices)
        ):
            raise QcPackError(
                "a face review's dose choices are a choice and whether it was "
                "seen set to zero, for each dose check's SHA-256 once"
            )
        if not self.own_verdicts <= self.absent | self.present:
            raise QcPackError(
                "a face review's own verdicts are of files it marks absent or present"
            )

    def __repr__(self) -> str:
        return (
            f"FaceReview(reference={self.reference!r}, absent={len(self.absent)}, "
            f"present={len(self.present)}, "
            f"confirmed_blocks={len(self.confirmed_blocks)}, "
            f"dose_choices={len(self.dose_choices)}, "
            f"own_verdicts={len(self.own_verdicts)})"
        )

    def own_verdict(self, digest: bytes) -> bool:
        """Whether the reviewer gave the instance of a source file, by its
        SHA-256, a face verdict of its own, which then decides it in place
        of a hold for its defaced frame."""
        return digest in self.own_verdicts

    def dose_choice(self, check: bytes) -> tuple[DoseChoice, bool] | None:
        """Return the choice for the RT Dose and block that a dose check's
        digest names, with whether the reviewed run wrote it set to zero,
        or None where the review gives none."""
        for digest, choice, zeroed in self.dose_choices:
            if digest == check:
                return choice, zeroed
        return None

    def hold_reason(  # pylint: disable = too-many-return-statements
        self,
        digest: bytes,
        pixels: bytes | None,
        contours: bytes | None,
        frames: int | None = None,
        dose: bool = False,
        grids: bytes | None = NO_GRIDS,
        segmentation: bool = False,
        surfaces: bytes | None = NO_SURFACES,
    ) -> VisualFeaturesReason | None:
        """Return why an instance cannot claim the option.

        Parameters
        ----------
        digest : bytes
            The SHA-256 of the instance's source file.
        pixels : bytes or None
            The :func:`pixel_data_sha256` of the pixel data that the run
            writes of it, or None where that cannot be found.
        contours : bytes or None
            The :func:`contour_data_sha256` of the contours that the run
            writes of it, or None where that cannot be found.
        frames : int, optional
            How many frames the pixel data that the run writes have, or None
            where that cannot be found. Where ``absent_frames`` is given,
            pixel data other than none are held unless the pack showed at
            least this many of their frames.
        dose : bool, optional
            Whether the instance is an RT Dose (:func:`is_rt_dose`), whose
            pixel data other than none are held unless its dose-levels
            previews showed at least ``frames`` of their frames, and so
            always where ``absent_dose_frames`` is not given.
        grids : bytes or None, optional
            The :func:`grid_data_sha256` of the deformation grids that the
            run writes of it, or None where that cannot be found; by
            default, that of none, which needs no preview.
        segmentation : bool, optional
            Whether the instance is a Segmentation (:func:`is_segmentation`),
            whose pixel data other than none are held unless its segments
            sheet showed at least ``frames`` of their frames, and so always
            where ``absent_segment_frames`` is not given. An instance that
            is both an RT Dose and a Segmentation, by one's SOP Class UID
            and the other's Modality, is held unless both showed them.
        surfaces : bytes or None, optional
            The :func:`surface_data_sha256` of the surface meshes that the
            run writes of it, or None where that cannot be found; by
            default, that of none, which needs no sheet.

        Returns
        -------
        VisualFeaturesReason or None
            None where the reviewer marked its series absent, and not also a
            series with the same file present, which a pack never holds, and
            the run writes the pixel data, contours, deformation grids, and
            surface meshes that the reviewed run wrote of it, and the pack
            showed every frame of those pixel data, which it records only
            where its previews draw them all, and every one of those grids
            and meshes.
        """
        if digest in self.present:
            return VisualFeaturesReason.FACE_PRESENT
        if digest not in self.absent:
            return VisualFeaturesReason.NO_FACE_VERDICT
        if (digest, pixels) not in self.absent_pixels:
            return VisualFeaturesReason.OTHER_PIXEL_DATA
        # Pixel data with more frames than the pack showed were not all
        # seen, only dose levels show an RT Dose, and only a segments sheet
        # a Segmentation; one that is both needs both.
        bounds = [
            counts
            for counts, needed in (
                (self.absent_dose_frames, dose),
                (self.absent_segment_frames, segmentation),
            )
            if needed
        ]
        if not bounds and self.absent_frames is not None:
            bounds = [self.absent_frames]
        if pixels != _NO_PIXELS and not all(
            any(
                (source, written) == (digest, pixels)
                and frames is not None
                and 1 <= frames <= shown
                for source, written, shown in counts or ()
            )
            for counts in bounds
        ):
            return VisualFeaturesReason.OTHER_PIXEL_DATA
        if (digest, contours) not in self.absent_contours:
            return VisualFeaturesReason.OTHER_CONTOURS
        # A file without a grid needs no grid sheet, so a review built
        # before grids were shown still covers it.
        if grids != NO_GRIDS and (digest, grids) not in self.absent_grids:
            return VisualFeaturesReason.OTHER_GRIDS
        # Likewise, a file without a mesh needs no surfaces sheet.
        if surfaces != NO_SURFACES and (digest, surfaces) not in self.absent_surfaces:
            return VisualFeaturesReason.OTHER_SURFACES
        return None


def read_face_review(pack_directory: os.PathLike | str) -> FaceReview:
    """Read the face verdicts of an attested QC pack.

    Parameters
    ----------
    pack_directory : path-like
        The directory of a first run's QC pack, which a reviewer has
        attested with face verdicts.

    Returns
    -------
    FaceReview
        Empty of files where the attestation gives no verdict, and of
        blocks where it confirms none. A file that
        the pack lists as held because the run defaced its frame, or as an
        RT Dose with too much dose in the face block to set to zero, is not
        taken as absent, since its verdict was on the defaced images beside
        it, unless the attestation chose to have that RT Dose written as
        received, when its verdict was on its own dose-levels previews of it
        so; nor is one whose contours, deformation grids, or surface meshes
        the pack could not show, since its verdict was on none of them. Each RT Dose of the pack's
        ``dose_checks`` has the attestation's dose choice, or else the one
        that the pack's run applied, if any. A file of the pack's
        ``undefaced_instances`` is never taken by its series' verdict, but
        by a verdict of its own where the attestation gives one.

    Raises
    ------
    QcPackError
        If the directory holds no QC pack, or the pack has not been
        attested, or its attestation's outcome is rejected, whose verdicts
        release nothing; if either is not of its format, or the attestation
        is for another pack; if the pack or a preview changed after it was
        attested; or if a verdict names a series that the pack does not
        list, or an instance's contours' or pixel data's SHA-256 has no
        preview that shows them, or a confirmed block names no eye check
        of the pack with a sheet of its eyes, or a dose choice names no
        dose check of the pack, or two dose checks share a digest, or an
        instance's own face verdict names no undefaced instance of the pack
        that it lists as shown. The message names no path and no value.
    """
    attestation, data = attested_pack(pack_directory)
    if attestation.outcome is not Outcome.ATTESTED:
        raise QcPackError(
            "the QC pack's attestation rejected it, so its verdicts release nothing"
        )
    doses = dose_checks(data)
    chosen = {verdict.position: verdict.choice for verdict in attestation.dose_choices}
    if not set(chosen) <= set(doses):
        raise QcPackError("a dose choice names no dose check of the QC pack")
    choices = {
        position: chosen.get(position, check.choice)
        for position, check in doses.items()
    }
    listed = undefaced_instances(data)
    own = {verdict.position: verdict.face for verdict in attestation.instance_faces}
    if not all(listed.get(position) for position in own):
        raise QcPackError(
            "an instance's face verdict names no undefaced instance of the QC "
            "pack that it shows"
        )
    files, by_position = _series_files(
        data,
        frozenset(
            p for p, choice in choices.items() if choice is DoseChoice.AS_WRITTEN
        ),
        frozenset(listed),
    )
    checks = eye_checks(data)
    if not all(
        first in checks and checks[first].sheet
        for first in attestation.confirmed_blocks
    ):
        raise QcPackError(
            "a confirmed block names no eye check of the QC pack with a sheet "
            "of its eyes"
        )
    by_face: dict[Face, set[_File]] = {face: set() for face in Face}
    for verdict in attestation.faces:
        if verdict.series not in files:
            raise QcPackError(
                "a face verdict names a series that the QC pack does not list"
            )
        by_face[verdict.face].update(files[verdict.series])
    # A file that the reviewed run held beside a CT series that it defaced
    # was judged beside defaced images, while its own outlines, pixel data,
    # or grids were left as they were, so a verdict of absent does not cover
    # it, whatever a later run defaces. One whose contours no contour sheet
    # showed, whose grids its grid sheets did not all show, or whose meshes
    # no surfaces sheet showed, was judged without them.
    absent = {each for each in by_face[Face.ABSENT] if not each[3]}
    # Such a file, in a defaced frame and not cleaned of the face, is judged
    # by its own verdict instead, from its own previews, which showed all of
    # it, so the pack recorded the digests that bind the verdict to them.
    for position, face in own.items():
        if position not in by_position:
            raise QcPackError(
                "an instance's face verdict names an instance without its "
                "source's SHA-256"
            )
        (absent if face is Face.ABSENT else by_face[Face.PRESENT]).add(
            by_position[position]
        )
    return FaceReview(
        attestation.reference,
        frozenset(each[0] for each in absent),
        frozenset(each[0] for each in by_face[Face.PRESENT]),
        frozenset(
            (source, pixels) for source, pixels, *_ in absent if pixels is not None
        ),
        frozenset(
            (source, contours)
            for source, _, contours, *_ in absent
            if contours is not None
        ),
        frozenset(
            (source, pixels, shown)
            for source, pixels, _, _, shown, _, _, _, _ in absent
            if pixels is not None and shown is not None
        ),
        frozenset(
            (source, pixels, shown)
            for source, pixels, _, _, _, shown, _, _, _ in absent
            if pixels is not None and shown is not None
        ),
        frozenset(
            (source, grids) for source, *_, grids, _ in absent if grids is not None
        ),
        confirmed_blocks=frozenset(
            bytes.fromhex(checks[first].block_sha256)
            for first in attestation.confirmed_blocks
        ),
        dose_choices=_dose_choices(doses, choices),
        own_verdicts=frozenset(by_position[position][0] for position in own),
        absent_segment_frames=frozenset(
            (source, pixels, shown)
            for source, pixels, _, _, _, _, shown, _, _ in absent
            if pixels is not None and shown is not None
        ),
        absent_surfaces=frozenset(
            (source, surfaces)
            for source, *_, surfaces in absent
            if surfaces is not None
        ),
    )


def _dose_choices(
    doses: dict, choices: dict[int, DoseChoice | None]
) -> frozenset[tuple[bytes, DoseChoice, bool]]:
    """Each dose check's choice, by its digest, with whether the pack's run
    wrote its RT Dose set to zero, which it did only on that choice.

    Raises
    ------
    QcPackError
        If two dose checks share a digest, which the same source file in
        the same block would give, so that a choice could not tell them
        apart.
    """
    digests = [check.check_sha256 for check in doses.values()]
    if len(set(digests)) != len(digests):
        raise QcPackError("two dose checks of the QC pack share a digest")
    return frozenset(
        (
            bytes.fromhex(doses[position].check_sha256),
            choice,
            doses[position].choice is DoseChoice.SET_TO_ZERO,
        )
        for position, choice in choices.items()
        if choice is not None
    )


# A source file's SHA-256, those of the pixel data and the contours written
# of it, if any, whether a verdict of absent on its series leaves it out:
# where the run held it beside a CT series that it defaced, as received, or
# released it on a verdict of its own, or the pack could not show its
# contours, its deformation grids, or its surface meshes; how many frames
# of pixel data other than none its previews showed, from the first, where
# it has their digest, how many its dose-levels previews showed, and how
# many its segments sheet showed, where each shows any so; and the SHA-256
# of the deformation grids and of the surface meshes written of it, if any.
_File = tuple[
    bytes,
    bytes | None,
    bytes | None,
    bool,
    int | None,
    int | None,
    int | None,
    bytes | None,
    bytes | None,
]
# Those holds' reasons as the QC pack words them, which run_qc.reason_text
# gives.
UNDEFACED_TEXT = (
    "HeldVisualFeatures(reason="
    f"{VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME.value})"
)
DOSE_IN_FACE_BLOCK_TEXT = (
    f"HeldVisualFeatures(reason={VisualFeaturesReason.DOSE_IN_FACE_BLOCK.value})"
)


def _series_files(
    data: bytes,
    as_written: frozenset[int] = frozenset(),
    undefaced: frozenset[int] = frozenset(),
) -> tuple[dict[int, frozenset[_File]], dict[int, _File]]:
    """Return each series' files, by the series' first run position, a verdict
    of absent leaving out each file held as an RT Dose with too much dose in
    a face block to set to zero there unless it is at a run position of
    ``as_written``, chosen to be written as received, and each at a run
    position of ``undefaced``, released or held, which only a verdict of its
    own covers; and each instance's file with a source digest, by its run
    position."""
    malformed = QcPackError("the QC pack is not of its format")
    document = json.loads(data.decode("ascii"))  # attested_pack has parsed it
    instances = document.get("instances")
    series = document.get("series")
    if not isinstance(instances, list) or not isinstance(series, list):
        raise malformed
    shown, unshown, pictured, dosed, segmented = _previews(document)
    gridded = _gridded(document)
    surfaced = _surfaced(document)
    digests: dict[int, _File] = {}
    for instance in instances:
        if not isinstance(instance, dict):
            raise malformed
        position, digest = instance.get("position"), instance.get("source_sha256")
        pixels = instance.get("pixel_sha256")
        contours = instance.get("contour_sha256")
        grids = instance.get("grid_sha256")
        surfaces = instance.get("surface_sha256")
        reasons = instance.get("reasons")
        if isinstance(position, int) and isinstance(digest, str):
            if (
                not _SHA256.fullmatch(digest)
                or not all(
                    each is None or (isinstance(each, str) and _SHA256.fullmatch(each))
                    for each in (pixels, contours, grids, surfaces)
                )
                or not isinstance(reasons, list)
            ):
                raise malformed
            # Contours' digest binds a verdict only to contours that a
            # contour sheet showed.
            if contours not in (None, NO_CONTOURS_SHA256) and position not in shown:
                raise malformed
            # Likewise, grids' only to grids that every grid sheet showed.
            if grids not in (None, NO_GRIDS_SHA256) and position not in gridded:
                raise malformed
            # Likewise, surface meshes' only to meshes that a surfaces sheet
            # showed.
            if surfaces not in (None, NO_SURFACES_SHA256) and position not in surfaced:
                raise malformed
            # Likewise, pixel data's binds it only to the frames previewed.
            frames = dose_frames = segment_frames = None
            if pixels not in (None, NO_PIXELS_SHA256):
                if position not in pictured:
                    raise malformed
                frames = pictured[position]
                dose_frames = dosed.get(position)
                segment_frames = segmented.get(position)
            digests[position] = (
                bytes.fromhex(digest),
                None if pixels is None else bytes.fromhex(pixels),
                None if contours is None else bytes.fromhex(contours),
                UNDEFACED_TEXT in reasons
                or position in undefaced
                or (DOSE_IN_FACE_BLOCK_TEXT in reasons and position not in as_written)
                or position in unshown,
                frames,
                dose_frames,
                segment_frames,
                None if grids is None else bytes.fromhex(grids),
                None if surfaces is None else bytes.fromhex(surfaces),
            )
    files: dict[int, frozenset[_File]] = {}
    for entry in series:
        positions = entry.get("positions") if isinstance(entry, dict) else None
        if not isinstance(positions, list) or not positions:
            raise malformed
        if not all(isinstance(p, int) and p in digests for p in positions):
            raise malformed
        files[positions[0]] = frozenset(digests[p] for p in positions)
    return files, digests


def _previews(
    document: dict,
) -> tuple[set[int], set[int], dict[int, int], dict[int, int], dict[int, int]]:
    """The run positions whose contours a pack's contour sheet shows, those
    whose contours or deformation grids it lists as not shown, and how many
    frames of each other position its other previews, its dose-levels
    previews, and its segments sheets show in a way that could show a face, as
    :func:`~.qc_pack.pictured_frames` counts them."""
    malformed = QcPackError("the QC pack is not of its format")
    previews, missing = document.get("previews"), document.get("not_previewed")
    if not isinstance(previews, list) or not isinstance(missing, list):
        raise malformed
    shown, unshown, framed = set(), set(), []
    for preview in previews:
        if not isinstance(preview, dict) or not isinstance(preview.get("frames"), list):
            raise malformed
        if not all(
            isinstance(frame, dict)
            and all(
                isinstance(frame.get(key), int) and not isinstance(frame[key], bool)
                for key in ("position", "frame")
            )
            for frame in preview["frames"]
        ):
            raise malformed
        if preview.get("kind") == PreviewKind.STRUCTURE_SET_CONTOURS.value:
            if not preview["frames"]:
                raise malformed
            shown.add(preview["frames"][0]["position"])
        framed.append(
            (
                preview.get("kind"),
                [(frame["position"], frame["frame"]) for frame in preview["frames"]],
            )
        )
    for entry in missing:
        if not isinstance(entry, dict):
            raise malformed
        if entry.get("reason") in _UNSHOWN:
            unshown.add(entry.get("position"))
    refused = {entry.get("position") for entry in missing}
    pictured = pictured_frames(framed, refused)
    dosed = pictured_frames(framed, refused, {PreviewKind.SERIES_DOSE_LEVELS.value})
    segmented = pictured_frames(
        framed, refused, {PreviewKind.SEGMENTATION_SEGMENTS.value}
    )
    return shown, unshown, pictured, dosed, segmented


# The reasons for which a pack lists a file whose contours, deformation
# grids, or surface meshes it does not show, so that a verdict is not of
# them.
_UNSHOWN = frozenset(
    {
        NotPreviewedReason.CONTOURS_NOT_SHOWN.value,
        NotPreviewedReason.GRIDS_NOT_SHOWN.value,
        NotPreviewedReason.SURFACES_NOT_SHOWN.value,
    }
)


def _gridded(document: dict) -> set[int]:
    """The run positions each of whose deformation grids a pack's grid
    sheets show, a sheet of each kind for each grid, as
    :class:`~.qc_pack.QcPack` checks them.

    The pack's previews have been checked to be of their format by
    :func:`_previews`.
    """
    kinds = {kind.value: kind for kind in GRID_KINDS}
    shown: dict[int, dict[str, set[int]]] = {}
    counts: dict[int, set[object]] = {}
    for preview in document["previews"]:
        if preview.get("kind") not in kinds or len(preview["frames"]) != 1:
            continue
        position, grid = preview["frames"][0]["position"], preview["frames"][0]["frame"]
        shown.setdefault(position, {}).setdefault(preview["kind"], set()).add(grid)
        counts.setdefault(position, set()).add(preview.get("total_frames"))
    whole = set()
    for position, by_kind in shown.items():
        (total,) = counts[position] if len(counts[position]) == 1 else (None,)
        if not isinstance(total, int) or isinstance(total, bool):
            continue
        if all(by_kind.get(kind) == set(range(total)) for kind in kinds):
            whole.add(position)
    return whole


def _surfaced(document: dict) -> set[int]:
    """The run positions each of whose surface meshes a pack's surfaces
    sheet shows, its one sheet listing each of them, as
    :class:`~.qc_pack.QcPack` checks it.

    The pack's previews have been checked to be of their format by
    :func:`_previews`.
    """
    whole = set()
    for preview in document["previews"]:
        if preview.get("kind") != PreviewKind.SURFACE_MESHES.value:
            continue
        frames = preview["frames"]
        total = preview.get("total_frames")
        if not frames or not isinstance(total, int) or isinstance(total, bool):
            continue
        positions = {frame["position"] for frame in frames}
        if len(positions) != 1:
            continue
        if sorted(frame["frame"] for frame in frames) == list(range(total)):
            whole |= positions
    return whole


def pixel_data_sha256(dataset: pydicom.Dataset) -> bytes:
    """Return the SHA-256 of a data set's top-level pixel data.

    The byte layout, padding and ValueError conditions are described by
    :func:`~.face_review_digests.pixel_data_sha256`.
    """
    return face_review_digests.pixel_data_sha256(dataset, PIXEL_DATA_TAGS)


def contour_data_sha256(dataset: pydicom.Dataset) -> bytes:
    """Return the SHA-256 of a data set's ROI contours.

    The byte layout, placement values and ValueError conditions are
    described by :func:`~.face_review_digests.contour_data_sha256`.
    """
    return face_review_digests.contour_data_sha256(dataset)


def grid_data_sha256(dataset: pydicom.Dataset) -> bytes:
    """Return the SHA-256 of a data set's deformation grids.

    The byte layout, placement values and ValueError conditions are
    described by :func:`~.face_review_digests.grid_data_sha256`.
    """
    return face_review_digests.grid_data_sha256(
        dataset,
        DEFORMABLE_REGISTRATION_SEQUENCE,
        DEFORMABLE_REGISTRATION_GRID_SEQUENCE,
        GRID_TAGS,
    )


def surface_data_sha256(dataset: pydicom.Dataset) -> bytes:
    """Return the SHA-256 of a data set's surface meshes.

    The byte layout, the elements taken, and ValueError conditions are
    described by :func:`~.face_review_digests.surface_data_sha256`, which is
    given every element of a mesh that a surfaces sheet draws
    (:mod:`~pymedphys._dicom.deidentify.qc_meshes`) or refuses for.
    """
    return face_review_digests.surface_data_sha256(
        dataset, SURFACE_SEQUENCE, SURFACE_POINTS, SURFACE_PRIMITIVES
    )


def registration_frames(dataset: pydicom.Dataset) -> frozenset[str] | None:
    """Return the Frames of Reference that a deformable registration names:
    its own Frame of Reference UID (0020,0052), the Registered Frame of
    Reference, in which its grids lie, and the Source Frame of Reference UID
    (0064,0003) of each item of its Deformable Registration Sequence, each
    without its padding.

    None where any of them is absent, empty, or not one text value, or the
    sequence or a value cannot be read, since the registration may then be
    in any frame.
    """
    try:
        found = [_frame_text(dataset, FRAME_OF_REFERENCE)]
        if DEFORMABLE_REGISTRATION_SEQUENCE in dataset:
            for item in dataset[DEFORMABLE_REGISTRATION_SEQUENCE].value:
                found.append(_frame_text(item, SOURCE_FRAME_OF_REFERENCE))
    # Whatever reading a sequence or value raises, its frames are unknown.
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    if not all(found):
        return None
    return frozenset(uid for uid in found if uid)


def _frame_text(dataset: pydicom.Dataset, tag: int) -> str | None:
    """An attribute's one text value without its padding, or None where it
    is absent, empty, or not one text value."""
    if tag not in dataset:
        return None
    value = dataset[tag].value
    if not isinstance(value, str):
        return None
    return normalise_uid(value) or None


def is_rt_dose(dataset: pydicom.Dataset) -> bool:
    """Whether an instance is an RT Dose, which only a QC pack's
    dose-levels previews show as it could show a face (D-017).

    Its SOP Class UID being RT Dose Storage, or its Modality possibly being
    RTDOSE (:func:`_modality_may_be`), makes it one, so that a file of either
    alone is never counted as shown, nor released under the option. A SOP
    Class UID that cannot be read leaves the Modality to decide.
    """
    return _sop_class(dataset) == RT_DOSE_STORAGE or _modality_may_be(dataset, "rtdose")


def is_segmentation(dataset: pydicom.Dataset) -> bool:
    """Whether an instance is a Segmentation, which only a QC pack's
    segments sheet shows as it could show a face (D-017).

    Its SOP Class UID being Segmentation Storage or Label Map Segmentation
    Storage, as Table B.5-1 of PS3.4 names them, or its Modality possibly
    being SEG (:func:`_modality_may_be`), makes it one, so that a file of
    either alone is never released under the option on a verdict given
    through other previews. A SOP Class UID that cannot be read leaves the
    Modality to decide.
    """
    return normalise_uid(_sop_class(dataset)) in SEGMENTATION_SOP_CLASSES or (
        _modality_may_be(dataset, "seg")
    )


def _sop_class(dataset: pydicom.Dataset) -> str:
    """The SOP Class UID as stripped text, or "" where it cannot be read."""
    try:
        return str(dataset.get("SOPClassUID") or "").strip()
    # Whatever reading the value raises, it names no class.
    except Exception:  # pylint: disable = broad-exception-caught
        return ""


def _modality_may_be(dataset: pydicom.Dataset, modality: str) -> bool:
    """Whether the Modality may be ``modality``, given in lower case.

    It may where it cannot be read, is not text, holds more than one value,
    holds a character outside printable ASCII once its padding is gone, such
    as a control character, a letter outside ASCII, or a fullwidth form, or
    is ``modality`` in any case, since text that may be it in another
    spelling cannot rule it out, as
    :mod:`~pymedphys._dicom.deidentify.face_blocks` compares Patient IDs. A
    missing or empty Modality says nothing, so it is not.
    """
    try:
        value = dataset.get("Modality")
        if value is None:
            return False
        if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
            if len(value) > 1:
                return True
            value = value[0] if value else ""
        if not isinstance(value, str):
            return True
        text = value.rstrip(" \0").lstrip(" ")
    # Whatever reading the value raises, it may be the modality.
    except Exception:  # pylint: disable = broad-exception-caught
        return True
    if not (text.isascii() and text.isprintable()) or "\\" in text:
        return True
    return text.casefold() == modality


def carries_visual_features(dataset: pydicom.Dataset, iod: str) -> bool:
    """Whether an instance can show a face, so that it needs a verdict.

    An instance does where it holds Pixel Data, Float Pixel Data, or Double
    Float Pixel Data, is an RT Structure Set, whose contours can trace the
    skin surface, or holds a deformation grid
    (:func:`holds_deformation_grid`), whose displacements can trace it too.
    It does too where it is a Surface Segmentation, or holds a surface mesh
    (:func:`holds_surface_mesh`), whose points can trace the skin surface.
    Any other, such as an RT Plan, an MR Spectroscopy instance, or a spatial
    registration, has nothing that can show a face, so it satisfies the
    option without a verdict.
    """
    return (
        iod in (_RT_STRUCTURE_SET, SURFACE_SEGMENTATION)
        or any(tag in dataset for tag in PIXEL_DATA_TAGS)
        or holds_deformation_grid(dataset)
        or holds_surface_mesh(dataset)
    )


def holds_surface_mesh(dataset: pydicom.Dataset) -> bool:
    """Whether an instance holds a surface mesh.

    It does where it holds a Surface Sequence (0066,0002), as every Surface
    Segmentation does (PS3.3 Section C.27.1), whatever its items: their
    Point Coordinates Data (0066,0016) place each point of a mesh in the
    patient, so a mesh of the skin or of the body traces the face, whatever
    its segment's label or code says, and a verdict covers it only where
    the QC pack's surfaces sheet showed every mesh
    (:mod:`~pymedphys._dicom.deidentify.qc_meshes`).
    """
    return SURFACE_SEQUENCE in dataset


def holds_deformation_grid(dataset: pydicom.Dataset) -> bool:
    """Whether an instance holds a deformable registration's grid.

    It does where an item of its Deformable Registration Sequence
    (0064,0002) holds a Deformable Registration Grid Sequence (0064,0005),
    whose Vector Grid Data (0064,0009) give a displacement at each point of
    a grid over the patient, which can follow the outline of the face, so
    that a verdict covers it only where the QC pack's grid sheets showed
    every grid (:mod:`~pymedphys._dicom.deidentify.qc_grids`). A Deformable
    Registration Sequence whose items cannot be read may hold one.
    """
    if DEFORMABLE_REGISTRATION_SEQUENCE not in dataset:
        return False
    try:
        return any(
            DEFORMABLE_REGISTRATION_GRID_SEQUENCE in item
            for item in dataset[DEFORMABLE_REGISTRATION_SEQUENCE].value
        )
    # Whatever reading the sequence raises, it may hold a grid.
    except Exception:  # pylint: disable = broad-exception-caught
        return True
