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
# One module makes every kind of preview, which share their decoding and
# windowing, so it is long.
"""Image previews for the confidential QC pack's human review (D-016, D-017).

D-017 asks a reviewer to look at every series, by maximum intensity
projection or cine strip, and at every instance in high-risk categories,
and blocks release on facial information that could be reconstructed unless
a risk assessment is recorded.
:func:`previews_of` makes those images, as PNG files, from the files that a
run wrote, so that a reviewer sees the pixel data as written, with any
region that the Clean Pixel Data Option blacked out, and, for each
frame with such regions, also from the file as received:

- a cine strip of each series: up to :data:`CINE_FRAMES` of its frames,
  evenly spaced through the series from its first frame to its last, each
  scaled to fit a square of :data:`TILE_PIXELS` pixels, in rows of
  :data:`CINE_COLUMNS`;
- a frontal maximum intensity projection of each volume that a series
  forms: at least :data:`VOLUME_SLICES` slices of one size, orientation,
  and pixel spacing, at distinct positions along the normal of their
  orientation, either stacked along it with axes along the patient's
  anterior-posterior, left-right, and superior-inferior directions, or
  else, as with a gantry tilt, slices offset within their plane, or an
  oblique orientation, with row and column directions each of unit length,
  and perpendicular, within
  :data:`~.stack_sampling.ORTHONORMAL_TOLERANCE`. A slice is a single-frame
  instance, placed by its Image Position (Patient), Image Orientation
  (Patient), and Pixel Spacing, or a frame of a multi-frame instance, such
  as an Enhanced CT, Enhanced PET, or Enhanced MR image, placed by its Plane
  Position (Patient), Plane Orientation (Patient), and Pixel Measures
  functional groups, per frame or shared, where every frame of the
  instance has them; the frames of each stack and time point, by the Stack
  ID and Temporal Position Index of their Frame Content functional group,
  form a volume of their own, so that frames at one position at two time
  points, whose union could hide the surface of either, are in none
  together; and slices that still repeat a position, such as the
  single-frame instances of a respiratory-correlated CT's time points,
  are parted into phases by the time point or acquisition that each
  names (:func:`~pymedphys._dicom.deidentify.phases.split`), each forming
  a volume of its own, or form none where nothing parts them. The surface
  renders of a series are sampled in batches of at most
  :data:`SAMPLED_AT_ONCE` voxels, and each volume's projection is
  accumulated with its batch, so that the surface samples and projection
  slices held at once are those of one batch, however many volumes the
  series forms; each preview is encoded as a PNG as it is drawn, so that
  only the PNGs, and not their images, are kept. A series with a colour
  instance or a Segmentation forms none.
  It is projected along the anterior-posterior axis and shown
  with the patient's head at the top and right on the viewer's left, sampled
  to square pixels by nearest neighbour, at most :data:`MIP_PIXELS` a side,
  each slice also taken into the pixel nearest it by the maximum, so that
  every slice is drawn where slices are closer than the pixels. A volume
  whose axes do not lie along the patient's, or whose slices are offset
  within their plane, is first sampled to cubic voxels along the patient's
  axes by :mod:`~pymedphys._dicom.deidentify.stack_sampling`, with every
  slice drawn, at most :data:`MIP_VOXELS` of them, and then projected, so
  that the projection superimposes nothing that a frontal view keeps
  apart;
- a sheet of renders of the skin surface of each such volume, from the
  front, the two obliques, the two profiles, and behind, as
  :mod:`~pymedphys._dicom.deidentify.qc_surfaces` describes, or, for a
  volume of RT Dose planes, and for each RT Dose instance of two or more
  frames evenly spaced, a dose-levels sheet of such renders at each of its dose levels;
  one that :mod:`~pymedphys._dicom.deidentify.qc_surfaces` finds too large
  to render has none, and such a volume has no projection either, so that
  its slices beyond its cine strip are held;
  an RT Dose is shown so only where it is one by its SOP Class, and its
  stored values are not padded, not rescaled, and scaled by a finite Dose
  Grid Scaling above 0 to doses that float32 holds, each other than 0
  still other than 0 and none infinite; a grid or series whose stored
  values are signed, by Pixel Representation, as an RT Dose of Dose Type
  ERROR's can be, is shown at the levels of its doses below 0 as well as
  above, as :mod:`~pymedphys._dicom.deidentify.qc_surfaces` describes;
- a dose-levels map of each RT Dose plane of one frame, so shown, that is
  in no volume, at full resolution, grey by how many of its dose levels
  each pixel reaches, so that each level's outline is an edge; a signed
  plane's map of its doses above 0 is followed, after white columns, by
  its map of the magnitudes of its doses below 0;
- a contour sheet of each instance with contours, such as an RT Structure
  Set, high-risk or not, since a face verdict can release only what a
  reviewer saw: its contours as written, drawn in each Frame of Reference
  of its ROIs with the surface of a volume in that frame, of a series that
  it references where there is one, or else of the first, as
  :mod:`~pymedphys._dicom.deidentify.qc_contours` describes;
- a segments sheet of each Segmentation, high-risk or not, for the same
  reason: its segments as written, each frame placed by its functional
  groups, drawn with the surface of a volume in its Frame of Reference, of
  a series that it references where there is one, or else of the first, as
  :mod:`~pymedphys._dicom.deidentify.qc_segments` describes. A
  Segmentation that no segments sheet shows whole, whatever the cause, is
  reported, though its other previews are kept;
- the sheets of each deformation grid of each instance that holds one
  (:func:`~.face_review.holds_deformation_grid`), such as a deformable
  registration, high-risk or not, for the same reason: each grid as
  written, placed by its own geometry, as
  :mod:`~pymedphys._dicom.deidentify.qc_grids` describes, one sheet of each
  of its quantities. An instance any of whose grids' sheets are not all
  drawn, whatever the cause, has none of them, and is reported, though its
  other previews, if any, are kept;
- a sheet of the globes found beside the eye ROIs of each CT series that
  the run defaced and held until a reviewer confirms its face block, which
  :mod:`~pymedphys._dicom.deidentify.qc_eyes` draws from the slices as
  received before the run writes any, and which never counts as showing
  the pixel data written;
- each high-risk instance at full resolution: every frame, or
  :data:`CINE_FRAMES` evenly spaced, unscaled, since burned-in text may be
  small;
- each frame of each instance whose Pixel Data the Clean Pixel Data Option
  cleaned, at full resolution, since the option's review must see every
  frame for text that the finder missed: as written, in grey for a
  monochrome frame, and, for a frame with regions, in colour, first as
  received, then an 8-pixel grey gutter, then as written, so that the
  reviewer can judge what each region covered. Each region is outlined in
  magenta, a colour that burned-in text rarely has, along its own edge
  pixels, inside the region, so that the outline hides nothing next to a
  region, where text that a region only partly covered would show; the two
  images are windowed together, from the frame as received, so the fill
  appears as it would beside the rest. A monochrome frame as written is
  then shown again, after another gutter, windowed from the smallest value
  to the largest of the frame as received, or of the frame as written where
  it has no regions, the full range in which the text finder searches it,
  since the percentile window shows text at or near either extreme as white
  or black with whatever else lies there. Each file is decoded once, frame by
  frame, and each frame's image is encoded as soon as it is drawn, so only
  one frame of an instance is held decoded at a time. An instance whose
  source cannot be shown beside it, because the source cannot be read or
  decoded, or differs from the file written in its frames' shape, number,
  or colour, is reported rather than shown in part;
- after each such frame's preview, its review frame, which the redaction
  review app shows and draws over (D-059): the frame as received where it
  has regions, and as written where it has none, which is then the same
  frame, at full resolution and without outlines, as 16-bit grey linear
  over the frame's full range, brightest last, padding 0
  (:func:`review_frame`), or as 8-bit RGB.

A series is the instances that share a Series Instance UID, or an instance
alone without one. Its instances are ordered by their positions along the
normal where every one has a position and they share an orientation, or else
by Instance Number where every one has one, or else by run position, with
ties in run position order. Each
preview lists the frames it shows, by run position and frame index from 0,
and how many frames its series or instance has.

Monochrome pixel data are rescaled by Rescale Slope and Rescale Intercept,
where both can be read, each frame of a multi-frame instance by those of its
Pixel Value Transformation functional group, where it has one, and a
volume of such frames is formed only where every frame's can be read; and
windowed from the 0.5th to the 99.5th percentile
of what the preview shows, or, where those are drawn alike, as where all
but a few values are one value, from its smallest value to its largest,
other than a redaction preview's full-range image, leaving out the stored values that Pixel Padding Value and Pixel
Padding Range Limit name, which are shown black; MONOCHROME1 is inverted so
that higher values are darker. Since that black shows one value, an instance
of which a frame as written pads with more than one stored value, which
could hold an image that every preview shows black, is not counted as
shown, so that no verdict releases its pixel data. Colour pixel data with
8 bits allocated are shown as RGB: as they are, or converted from YBR_FULL
or YBR_FULL_422 by pydicom, while JPEG 2000's YBR_ICT and YBR_RCT are
decoded to RGB. Compressed pixel data are decoded by the plugin
that :func:`.pixel_decoding.pinned_plugin` pins for its transfer syntax
and attributes, in process, but for those of
:data:`.pixel_decoding.CHILD_ONLY_PLUGINS`, whose frames are decoded in the
decoding child by :func:`.pixel_decoding.isolated_frames` (D-055).
An instance whose pixel data cannot be previewed is reported with why,
rather than left out: pixel data in a compressed transfer syntax that no
installed plugin is pinned to decode; a photometric interpretation other
than those above, or float pixel data; or pixel data that cannot be
decoded. An instance with contours that a sheet cannot show is reported,
and so is a high-risk instance without pixel data or contours, so that the
reviewer knows there is nothing to see of it here. Only the frames that a
preview shows are decoded, one at a time, so an instance is reported as
undecodable only where one of them is.

A PNG is written with no ancillary chunks, so it holds no time or text, and
the same pixels always give the same file with the same zlib.
"""

from __future__ import annotations

import dataclasses
import io
import math
import struct
import zlib
from collections.abc import Collection, Iterator, Mapping, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from .pixel_decoding import (
    CHILD_ONLY_PLUGINS,
    decoder_available,
    isolated_frames,
    pinned_plugin,
)
from . import (
    qc_contours,
    qc_eyes,
    qc_grids,
    qc_segments,
    qc_surfaces,
    stack_sampling,
)
from .face_review import holds_deformation_grid, is_rt_dose, is_segmentation
from .functional_groups import frame_group
from .phases import FRAME, Named, named_by_frame, named_by_instance, split
from .pixel_cleaning import beyond
from .qc_pack import (
    GRID_KINDS,
    NotPreviewedEntry,
    NotPreviewedReason,
    Preview,
    PreviewKind,
    RedactionEntry,
    pictured_frames,
)
from .uids import normalise_uid

CINE_FRAMES = 16
CINE_COLUMNS = 4
TILE_PIXELS = 256
MIP_PIXELS = 1024
# The most voxels to which the projection of a stack whose axes do not lie
# along the patient's is sampled (_StackProjection), so that it takes
# seconds: about 0.9 mm voxels for a head 230 mm across and 210 mm tall.
MIP_VOXELS = 1 << 24
VOLUME_SLICES = 3

_PERCENTILES = (0.5, 99.5)
_MONOCHROME = frozenset({"MONOCHROME1", "MONOCHROME2"})
# Shown as RGB, which pydicom gives for each of them by default.
_COLOUR = frozenset({"RGB", "YBR_FULL", "YBR_FULL_422", "YBR_ICT", "YBR_RCT"})
# Float Pixel Data and Double Float Pixel Data, by their Bits Allocated
# (PS3.3 Sections C.7.6.24 and C.7.6.25), with the padding value and range
# limit of each.
_FLOAT_PIXEL_DATA = {32: "FloatPixelData", 64: "DoubleFloatPixelData"}
_FLOAT_PADDING = {
    "FloatPixelData": ("FloatPixelPaddingValue", "FloatPixelPaddingRangeLimit"),
    "DoubleFloatPixelData": (
        "DoubleFloatPixelPaddingValue",
        "DoubleFloatPixelPaddingRangeLimit",
    ),
}
_PIXEL_KEYWORDS = ("PixelData", *_FLOAT_PIXEL_DATA.values())
# An axis lies along a patient axis when its other two direction cosines are
# each at most this; a volume with any other axis is sampled to voxels along
# the patient's axes before it is projected, since a projection along an
# oblique axis would superimpose what a frontal view keeps apart.
_ALIGNMENT_TOLERANCE = 1e-4
_ORIENTATION_TOLERANCE = 1e-4
# In millimetres, how far a slice's origin may lie off the normal of the first,
# or a dose grid's frame from even spacing.
_STACKING_TOLERANCE = 0.01
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# The outline of a region in a redaction preview, and the columns between
# the frame as received and as written.
_OUTLINE = (255, 0, 255)
_GUTTER_PIXELS = 8
_GUTTER = (128, 128, 128)


@dataclasses.dataclass(frozen=True)
class _Plane:
    """The geometry of a single-frame image in the patient's coordinates."""

    row: tuple[float, float, float]  # direction of increasing column index
    column: tuple[float, float, float]  # direction of increasing row index
    spacing: tuple[float, float]  # between rows, then between columns
    shape: tuple[int, int]
    origin: tuple[float, float, float]


@dataclasses.dataclass(frozen=True)
class _Instance:
    """What a preview needs of a file; its frames are decoded one at a time."""

    position: int
    data: bytes = dataclasses.field(repr=False)
    plugin: str  # the pydicom decoding plugin, or "" for native pixel data
    series: str | None
    shape: tuple[int, int]
    # Stored values, inclusive, not shown: integers, or floating-point
    # values for floating-point pixel data.
    padding: tuple[float, float] | None
    frames: int
    colour: bool
    inverted: bool
    rescale: tuple[float, float]
    spacing: tuple[float, float] | None
    plane: _Plane | None
    number: int | None
    modality: str
    # An RT Dose grid that dose levels show.
    grid: qc_surfaces.Grid | qc_surfaces.Stacked | None
    frame: str | None  # Frame of Reference UID
    # Whether its native Pixel Data hold no more than its frames, with at most
    # one byte of padding; the bytes beyond them are in no frame a preview
    # can show. Encapsulated Pixel Data are taken as whole here.
    whole: bool = True
    # Whether it is an RT Dose (face_review.is_rt_dose), which only a
    # dose-levels preview shows as it could show a face (D-017).
    dose: bool = False
    # Dose Grid Scaling, where a dose-levels preview can show its doses:
    # an RT Dose by its SOP Class, not padded, not rescaled, and scaled by
    # a finite number above 0.
    dose_scale: float | None = None
    # Whether such an RT Dose's stored values are signed, so that its
    # doses below 0 are shown at their own levels.
    dose_signed: bool = False
    # Whether its native Pixel Data are of 1 bit allocated, packed across
    # frames, which pydicom 3.0 cannot decode one frame at a time where a
    # frame's bits are not a whole number of bytes, as a Segmentation's
    # BINARY masks are (_packed_frames).
    packed: bool = False
    # Whether its pixel data are Float Pixel Data or Double Float Pixel Data,
    # whose values that are not a number are not shown, as padding is not,
    # and whose infinities are shown beyond the frame's finite extremes
    # (_drawn_floats).
    floating: bool = False
    # Whether it is a Segmentation (face_review.is_segmentation), which only
    # a segments sheet shows as it could show a face (D-017), and what the
    # sheet needs of it, or None where none can show it.
    segmentation: bool = False
    segments: qc_segments.Segments | None = None
    # For an instance whose functional groups describe its frames (_framed):
    # each frame's plane, where every frame has one; each frame's Rescale
    # Slope and Rescale Intercept, where its Pixel Value Transformation
    # group gives them, in place of ``rescale``; and each frame's Stack ID
    # and Temporal Position Index, from its Frame Content group.
    planes: tuple[_Plane, ...] | None = None
    rescales: tuple[tuple[float, float], ...] | None = None
    stacks: tuple[tuple[str, str], ...] | None = None
    # What its Stack IDs and Temporal Position Indices are unique within,
    # and so which other instances' frames its frames may share a volume
    # with (_scope): for an instance whose functional groups describe its
    # frames, its Concatenation, or else itself alone; for any other, its
    # series' other instances without functional groups, as "".
    scope: str = ""
    # Whether its rescaled values are Hounsfield units: for an instance
    # without functional groups, where its Rescale Type is HU or absent,
    # which PS3.3 C.8.2.1 allows only for Hounsfield units in a CT Image;
    # for one with them, where every frame's Pixel Value Transformation
    # group gives Rescale Slope, Rescale Intercept, and a Rescale Type of HU.
    hounsfield: bool = False
    # What each frame names of its phase (phases.split), where it can be
    # read: a single-frame instance's own, or each frame's Frame Content
    # group's.
    named: tuple[Named, ...] | None = None

    def plane_of(self, frame: int) -> _Plane | None:
        """The plane of a frame, from 0, or None where it has none."""
        if self.planes is not None:
            return self.planes[frame]
        return self.plane if self.frames == 1 else None

    def rescale_of(self, frame: int) -> tuple[float, float]:
        """The Rescale Slope and Rescale Intercept of a frame, from 0."""
        return self.rescale if self.rescales is None else self.rescales[frame]

    def stack_of(self, frame: int) -> tuple[str, str, str]:
        """The scope of an instance's stacks, then the Stack ID and Temporal
        Position Index of a frame, from 0, or empty strings where it gives
        none."""
        stack, time = ("", "") if self.stacks is None else self.stacks[frame]
        return self.scope, stack, time

    def named_of(self, frame: int) -> Named:
        """What a frame, from 0, names of its phase, or nothing where that
        could not be read."""
        if self.named is None:
            return Named(FRAME, ("", ""))
        return self.named[frame]


@dataclasses.dataclass(frozen=True)
class PreviewSet:
    """The previews of a run, and the instances that could not be previewed.

    Attributes
    ----------
    previews : tuple of ~pymedphys._dicom.deidentify.qc_pack.Preview
        Each series' cine strip, then the projection and the surface render
        of each volume that it forms, then the dose-levels render of each RT Dose
        grid in it, then the dose-levels map of each RT Dose plane in it in
        no volume, series in the order of their first run position; then each
        sheet of a series' eyes, as given; then each contour sheet, in run
        position order; then each segments sheet, in run position order;
        then each grid sheet, in run position order, grid order, and the
        order of :data:`~.qc_pack.GRID_KINDS`; then each high-risk
        instance, in run position order; then each frame of each instance
        that Clean Pixel Data cleaned, in run position and frame order, each
        followed by its review frame. Named ``P-0001.png``
        onwards in that order. A contour sheet shows its instance's frame
        0, then the frames of each volume that it is drawn with, if any; a
        segments sheet shows each of its Segmentation's frames, then the
        frames of the volume that it is drawn with, if any.
    not_previewed : tuple of ~pymedphys._dicom.deidentify.qc_pack.NotPreviewedEntry
        In run position order. An RT Dose that no dose-levels preview shows
        whole, whatever the cause, is listed as ``DOSE_LEVELS_NOT_SHOWN``,
        though its other previews are kept, unless another reason is listed
        first. Likewise, a Segmentation that no segments sheet shows whole
        is listed as ``SEGMENTS_NOT_SHOWN``, and an instance that holds a
        deformation grid whose sheets are not all drawn as
        ``GRIDS_NOT_SHOWN``.
    contours_shown : frozenset of int
        The run positions of the files with contours that a contour sheet
        shows.
    grids_shown : frozenset of int
        The run positions of the files that hold a deformation grid each of
        whose grids a sheet of each kind of :data:`~.qc_pack.GRID_KINDS`
        shows, and that are not listed as not previewed.
    pixels_shown : frozenset of int
        The run positions of the files with pixel data every frame of which
        a preview that could show a face draws, and that are not listed as
        not previewed, and whose native Pixel Data hold no more than their
        frames. A volume's projection and surface render draw each of its
        slices, by its maximum where slices are closer than their pixels,
        so they draw every frame of a multi-frame instance whose frames are
        all in volumes, however many it has. A
        contour sheet lists frames that it cannot show a face in, so its
        frames do not count. Only dose-levels previews count for an RT Dose,
        by :func:`~.face_review.is_rt_dose`: its cine strip is windowed to
        its highest doses, which can leave a low dose outlining the skin
        black, and an Otsu render of a series of its planes shows one level.
        Only a segments sheet counts for a Segmentation, and only for its
        own frames: its cine strip and projection can show a segment as
        windowed values, but not the surface that a segment traces. Nor
        does a file of which a frame that a preview draws pads with more
        than one stored value, since every preview draws its padding as one
        black, or as no patient.
    """

    previews: tuple[Preview, ...]
    not_previewed: tuple[NotPreviewedEntry, ...]
    contours_shown: frozenset[int] = frozenset()
    pixels_shown: frozenset[int] = frozenset()
    grids_shown: frozenset[int] = frozenset()


def previews_of(
    written: Mapping[int, bytes],
    high_risk: Collection[int],
    redactions: Mapping[int, tuple[bytes | None, RedactionEntry]] | None = None,
    eye_sheets: Sequence[qc_eyes.EyeSheet] = (),
) -> PreviewSet:
    """Return the previews of the files that a run wrote, as the module describes.

    Parameters
    ----------
    written : mapping of int to bytes
        Each file to preview, by its instance's run position.
    high_risk : collection of int
        The run positions of the instances in high-risk categories. A
        position without a file is ignored, since nothing of it is released.
    redactions : mapping of int to (bytes or None, RedactionEntry), optional
        The source file of each instance that Clean Pixel Data cleaned, or
        None where no frame has regions, and what it cleaned, by run
        position. A position without a written file is ignored.
    eye_sheets : sequence of ~pymedphys._dicom.deidentify.qc_eyes.EyeSheet, optional
        The sheet of each CT series held until a reviewer confirms its face
        block, drawn from its slices as received, in order of its first
        frame's run position, each listing only frames of held instances;
        none by default.

    Returns
    -------
    PreviewSet
    """
    redactions = {} if redactions is None else redactions
    instances: list[_Instance] = []
    refused: dict[int, NotPreviewedReason] = {}
    contoured: dict[int, qc_contours.Contours] = {}
    # Each instance's grid sheets, drawn as it is read, so that its grids
    # are not all held at once, and those whose sheets were not all drawn.
    gridded: dict[int, list[_Encoded]] = {}
    ungridded: set[int] = set()
    for position in sorted(written):
        dataset = _read(written[position])
        if dataset is not None and holds_deformation_grid(dataset):
            sheets = _grid_images(position, dataset)
            if sheets is None:
                ungridded.add(position)
            else:
                gridded[position] = sheets
        found = _instance(position, written[position], dataset)
        if isinstance(found, _Instance):
            instances.append(found)
        elif isinstance(found, NotPreviewedReason):
            refused[position] = found
        elif found is not None:
            contoured[position] = found
        elif (
            position in high_risk
            and position not in gridded
            and position not in ungridded
        ):
            refused[position] = NotPreviewedReason.NO_PIXEL_DATA
    # Each image is encoded as it is made, so that only its PNG is kept.
    images: list[_Encoded] = []
    decoded = _Decoder(refused)
    framed = [frame for contours in contoured.values() for frame in contours.frames]
    framed.extend(
        instance.segments.frame for instance in instances if instance.segments
    )
    guides: dict[str, list[tuple[_Guided, str | None]]] = {
        frame: [] for frame in framed if frame is not None
    }
    for series in _series(instances):
        images.extend(_encoded(_series_images(series, decoded, guides)))
    for sheet in eye_sheets:
        images.append(
            (
                PreviewKind.SERIES_EYES,
                sheet.frames,
                sheet.total_frames,
                png(sheet.image),
            )
        )
    for position, contours in sorted(contoured.items()):
        sheet = _contour_image(position, contours, guides)
        if sheet is None:
            refused[position] = NotPreviewedReason.CONTOURS_NOT_SHOWN
            continue
        images.extend(_encoded([sheet]))
    for instance in instances:
        if instance.segments is not None:
            segmented = _segments_image(instance, decoded, guides)
            if segmented is not None:
                images.extend(_encoded([segmented]))
    for position, sheets in sorted(gridded.items()):
        if position not in refused:
            images.extend(sheets)
    for instance in instances:
        if instance.position in high_risk:
            image = _instance_image(instance, decoded)
            if image is not None:
                images.extend(_encoded([image]))
    for instance in instances:
        if instance.position in redactions:
            source, entry = redactions[instance.position]
            images.extend(_redaction_images(instance, source, entry, decoded))
    # Only previews that could show a face count, and every frame of an
    # instance must be among theirs; for an RT Dose, only dose levels do,
    # and for a Segmentation, only its segments sheet.
    listed = [(kind.value, frames) for kind, frames, _, _ in images]
    levels = {PreviewKind.SERIES_DOSE_LEVELS.value}
    sheets = {PreviewKind.SEGMENTATION_SEGMENTS.value}
    # An RT Dose whose every frame no dose-levels preview shows is listed,
    # whatever the cause, unless it is listed already. It is listed only
    # once every image is made, so that its frames were still decoded for
    # its other previews, which it keeps.
    dosed = pictured_frames(listed, refused, levels)
    for instance in instances:
        if instance.dose and dosed.get(instance.position) != instance.frames:
            refused.setdefault(
                instance.position, NotPreviewedReason.DOSE_LEVELS_NOT_SHOWN
            )
    # Likewise a Segmentation whose every frame no segments sheet shows.
    segmented = pictured_frames(listed, refused, sheets)
    for instance in instances:
        if (
            instance.segmentation
            and segmented.get(instance.position) != instance.frames
        ):
            refused.setdefault(instance.position, NotPreviewedReason.SEGMENTS_NOT_SHOWN)
    # Likewise an instance with a deformation grid whose sheets were not
    # all drawn.
    for position in sorted(ungridded):
        refused.setdefault(position, NotPreviewedReason.GRIDS_NOT_SHOWN)
    pictured = pictured_frames(listed, refused)
    dosed = pictured_frames(listed, refused, levels)
    segmented = pictured_frames(listed, refused, sheets)
    width = max(4, len(str(len(images))))
    previews = tuple(
        Preview(f"P-{number:0{width}d}.png", kind, frames, total, encoded)
        for number, (kind, frames, total, encoded) in enumerate(images, start=1)
    )
    return PreviewSet(
        previews,
        tuple(
            NotPreviewedEntry(position, reason)
            for position, reason in sorted(refused.items())
        ),
        frozenset(contoured) - frozenset(refused),
        frozenset(
            instance.position
            for instance in instances
            if instance.whole
            and instance.position not in decoded.mixed_padding
            and _shown_by(instance, pictured, dosed, segmented).get(instance.position)
            == instance.frames
        ),
        frozenset(gridded) - frozenset(refused),
    )


# An image's kind, the frames it shows by run position and index, how many
# frames its series or instance has, and its PNG.
_Encoded = tuple[PreviewKind, tuple[tuple[int, int], ...], int, bytes]
# The surface of a volume that a contour sheet can be drawn with, and the
# frames that it shows.
_Guided = tuple[qc_contours.Guide, tuple[tuple[int, int], ...]]


def _shown_by(
    instance: _Instance,
    pictured: dict[int, int],
    dosed: dict[int, int],
    segmented: dict[int, int],
) -> dict[int, int]:
    """The frames shown, by run position, of the previews that count for an
    instance: dose levels for an RT Dose, segments sheets for a
    Segmentation, and any but a contour sheet for any other."""
    if instance.dose:
        return dosed
    return segmented if instance.segmentation else pictured


def _encoded(images) -> Iterator[_Encoded]:
    """Encode each image as a PNG as it is made."""
    for kind, frames, total, image in images:
        yield kind, frames, total, png(image)


def _read(data: bytes) -> pydicom.Dataset | None:
    """A written file's data set, or None where it cannot be read."""
    try:
        return pydicom.dcmread(io.BytesIO(data))
    except Exception:  # pylint: disable = broad-exception-caught
        # Whatever pydicom raises, the reviewer is told, never the error.
        return None


def _grid_images(position: int, dataset: pydicom.Dataset) -> list[_Encoded] | None:
    """The sheets of each deformation grid of a data set, each as its kind,
    its grid by run position and index among the data set's grids, and how
    many grids it holds; or None where any cannot be drawn
    (:mod:`~pymedphys._dicom.deidentify.qc_grids`)."""
    grids = qc_grids.grids_of(dataset)
    if grids is None:
        return None
    found: list[_Encoded] = []
    for index, grid in enumerate(grids):
        sheets = qc_grids.grid_sheets(grid)
        if sheets is None:
            return None
        found.extend(
            _encoded(
                (kind, ((position, index),), len(grids), sheet)
                for kind, sheet in zip(GRID_KINDS, sheets, strict=True)
            )
        )
    return found


def _instance(
    position: int, data: bytes, dataset: pydicom.Dataset | None = None
) -> _Instance | NotPreviewedReason | qc_contours.Contours | None:
    """Read what a preview needs of a file, or why it cannot be previewed.

    A file without pixel data gives its contours, where it has any that a
    sheet can show, or ``CONTOURS_NOT_SHOWN`` where it has others, or
    ``None`` where it has none. ``dataset``, where given, is the file's,
    already read.
    """
    if dataset is None:
        dataset = _read(data)
    if dataset is None:
        return NotPreviewedReason.UNREADABLE
    held = [keyword for keyword in _PIXEL_KEYWORDS if keyword in dataset]
    if len(held) > 1:
        # Which of them a viewer shows is not defined.
        return NotPreviewedReason.UNSUPPORTED
    if not held:
        if not qc_contours.has_contours(dataset):
            return None
        contours = qc_contours.contours_of(dataset)
        return NotPreviewedReason.CONTOURS_NOT_SHOWN if contours is None else contours
    # The data set is not kept: its frames are decoded from the file one at
    # a time, so that a run's pixel data are never all decoded at once.
    return _described(position, dataset, data)


def _described(
    position: int, dataset: pydicom.Dataset, data: bytes
) -> _Instance | NotPreviewedReason:
    """Describe an image whose pixel data a preview can show, or say why not."""
    try:
        syntax = str(dataset.file_meta.TransferSyntaxUID)
        plugin = ""
        if dataset.file_meta.TransferSyntaxUID.is_compressed:
            plugin = pinned_plugin(
                syntax, dataset.get("BitsStored"), dataset.get("PixelRepresentation")
            )
            if not plugin or not decoder_available(syntax, plugin):
                return NotPreviewedReason.COMPRESSED
        photometric = str(dataset.PhotometricInterpretation).strip()
        samples = int(dataset.SamplesPerPixel)
        allocated = int(dataset.BitsAllocated)
        floating = "PixelData" not in dataset
        frames = int(dataset.get("NumberOfFrames") or 1)
        rows, columns = int(dataset.Rows), int(dataset.Columns)
    except Exception:  # pylint: disable = broad-exception-caught
        return NotPreviewedReason.UNREADABLE
    # Attributes that only adjust a preview are read tolerantly: one that
    # cannot be read is left out, rather than the preview.
    slope = _number(dataset, "RescaleSlope", float)
    intercept = _number(dataset, "RescaleIntercept", float)
    rescale = (
        (1.0, 0.0)
        if slope is None or intercept is None
        else (float(slope), float(intercept))
    )
    number = _number(dataset, "InstanceNumber", int)
    number = None if number is None else int(number)
    try:
        modality = str(dataset.get("Modality") or "").strip()
    except Exception:  # pylint: disable = broad-exception-caught
        modality = ""
    colour = photometric in _COLOUR and samples == 3 and allocated == 8
    segmentation = is_segmentation(dataset)
    if not colour and not (photometric in _MONOCHROME and samples == 1):
        return NotPreviewedReason.UNSUPPORTED
    # Floating-point pixel data are native, of one sample, in the element
    # that Bits Allocated gives.
    if floating and (
        plugin or colour or _FLOAT_PIXEL_DATA.get(allocated, "") not in dataset
    ):
        return NotPreviewedReason.UNSUPPORTED
    if frames < 1 or rows < 1 or columns < 1:
        return NotPreviewedReason.UNREADABLE
    spacing = _spacing(dataset)
    framed = (
        _Framed()
        if colour or segmentation
        else _framed(dataset, frames, (rows, columns))
    )
    planes = framed.planes
    if spacing is None and planes and len({plane.spacing for plane in planes}) == 1:
        spacing = planes[0].spacing
    plane = _plane(dataset, spacing, (rows, columns)) if frames == 1 else None
    if planes is not None and frames == 1:
        plane = planes[0]
    hounsfield = framed.hounsfield if framed.described else _hounsfield(dataset)
    uid = dataset.get("SeriesInstanceUID")
    scale = None if colour or rescale != (1.0, 0.0) else _dose_scale(dataset)
    signed = _number(dataset, "PixelRepresentation", int) == 1
    whole = True
    if not plugin:
        try:
            expected = pydicom.pixels.utils.get_expected_length(dataset, "bytes")
            keyword = _FLOAT_PIXEL_DATA[allocated] if floating else "PixelData"
            whole = len(dataset[keyword].value) <= expected + 1
        except Exception:  # pylint: disable = broad-exception-caught
            whole = False
    return _Instance(
        position=position,
        data=data,
        plugin=plugin,
        series=str(uid) if uid else None,
        shape=(rows, columns),
        padding=None
        if colour
        else _float_padding(dataset, _FLOAT_PIXEL_DATA[allocated])
        if floating
        else _padding(dataset),
        frames=frames,
        colour=colour,
        inverted=photometric == "MONOCHROME1",
        rescale=rescale,
        spacing=spacing,
        plane=plane,
        number=number,
        modality=modality,
        grid=None
        if scale is None
        else _dose_grid(dataset, spacing, (rows, columns), frames, scale, signed),
        frame=_uid(dataset, "FrameOfReferenceUID"),
        whole=whole,
        dose=is_rt_dose(dataset),
        dose_scale=scale,
        dose_signed=scale is not None and signed,
        packed=not plugin and allocated == 1,
        floating=floating,
        segmentation=segmentation,
        segments=qc_segments.segments_of(dataset) if segmentation else None,
        planes=planes,
        rescales=framed.rescales,
        stacks=framed.stacks,
        scope=_scope(position, dataset) if framed.described else "",
        hounsfield=hounsfield,
        named=framed.named if framed.described else _named(dataset, frames),
    )


def _scope(position: int, dataset: pydicom.Dataset) -> str:
    """What the Stack IDs and Temporal Position Indices of an instance with
    functional groups are unique within: its Concatenation, whose SOP
    Instances hold one Multi-frame Image between them, or else itself.

    PS3.3 C.7.6.16.2.2.4 lets another SOP Instance reuse a Stack ID, which
    is unique only within a Dimension Organization UID, if present, or else
    a Concatenation UID; so frames of two instances that a Concatenation
    does not join never share a volume, though their labels match, since
    one acquisition's surface could otherwise hide another's while both are
    counted as shown.
    """
    concatenation = _uid(dataset, "ConcatenationUID")
    if concatenation is not None:
        return f"concatenation {concatenation}"
    return f"instance {position}"


def _uid(dataset: pydicom.Dataset, keyword: str) -> str | None:
    try:
        uid = normalise_uid(str(dataset.get(keyword) or ""))
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    return uid or None


def _number(dataset: pydicom.Dataset, keyword: str, kind: type) -> float | int | None:
    """An attribute's single finite value as ``kind``, or None."""
    try:
        value = kind(dataset[keyword].value) if keyword in dataset else None
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    return value if value is None or math.isfinite(value) else None


def _padding(dataset: pydicom.Dataset) -> tuple[int, int] | None:
    """The stored values that Pixel Padding Value and its range limit pad with."""
    value = _number(dataset, "PixelPaddingValue", int)
    if value is None:
        return None
    limit = _number(dataset, "PixelPaddingRangeLimit", int)
    limit = value if limit is None else limit
    return int(min(value, limit)), int(max(value, limit))


def _float_padding(
    dataset: pydicom.Dataset, keyword: str
) -> tuple[float, float] | None:
    """The values that Float Pixel Padding Value and its range limit, or
    their double-float counterparts for Double Float Pixel Data, pad with
    (PS3.3 Sections C.7.6.24 and C.7.6.25); a value that is not finite
    pads with nothing."""
    value_keyword, limit_keyword = _FLOAT_PADDING[keyword]
    value = _number(dataset, value_keyword, float)
    if value is None:
        return None
    limit = _number(dataset, limit_keyword, float)
    limit = value if limit is None else limit
    return float(min(value, limit)), float(max(value, limit))


def _floats(dataset: pydicom.Dataset, keyword: str, count: int) -> tuple | None:
    try:
        values = tuple(float(value) for value in dataset[keyword].value)
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    if len(values) != count or not all(math.isfinite(value) for value in values):
        return None
    return values


def _spacing(dataset: pydicom.Dataset) -> tuple[float, float] | None:
    spacing = _floats(dataset, "PixelSpacing", 2)
    if spacing is None or min(spacing) <= 0:
        return None
    return spacing[0], spacing[1]


def _plane(
    dataset: pydicom.Dataset,
    spacing: tuple[float, float] | None,
    shape: tuple[int, int],
) -> _Plane | None:
    return _placed(
        _floats(dataset, "ImageOrientationPatient", 6),
        _floats(dataset, "ImagePositionPatient", 3),
        spacing,
        shape,
    )


def _placed(
    orientation: tuple | None,
    origin: tuple | None,
    spacing: tuple[float, float] | None,
    shape: tuple[int, int],
) -> _Plane | None:
    """A plane of these direction cosines, origin, and pixel spacing, or
    None where any is missing or the cosines are not of two orthogonal
    unit vectors."""
    if orientation is None or origin is None or spacing is None:
        return None
    row = np.array(orientation[:3])
    column = np.array(orientation[3:])
    if (
        abs(np.linalg.norm(row) - 1) > 1e-3
        or abs(np.linalg.norm(column) - 1) > 1e-3
        or abs(float(row @ column)) > 1e-3
    ):
        return None
    return _Plane(
        row=(orientation[0], orientation[1], orientation[2]),
        column=(orientation[3], orientation[4], orientation[5]),
        spacing=spacing,
        shape=shape,
        origin=(origin[0], origin[1], origin[2]),
    )


# The functional groups that place a frame, by its position, orientation,
# and pixel spacing (PS3.3 C.7.6.16.2.1 to C.7.6.16.2.3), that rescale its
# stored values (C.7.6.16.2.9), and that give its stack and time point
# (C.7.6.16.2.2), each per frame or shared.
_PLACING = (
    "PlanePositionSequence",
    "PlaneOrientationSequence",
    "PixelMeasuresSequence",
)
_RESCALING = "PixelValueTransformationSequence"
_CONTENT = "FrameContentSequence"
_FUNCTIONAL_GROUPS = (
    "SharedFunctionalGroupsSequence",
    "PerFrameFunctionalGroupsSequence",
)


@dataclasses.dataclass(frozen=True)
class _Framed:
    """What an instance's functional groups give of its frames (:func:`_framed`)."""

    described: bool = False  # whether it has functional groups at all
    planes: tuple[_Plane, ...] | None = None
    rescales: tuple[tuple[float, float], ...] | None = None
    stacks: tuple[tuple[str, str], ...] | None = None
    hounsfield: bool = False
    named: tuple[Named, ...] | None = None


def _framed(dataset: pydicom.Dataset, frames: int, shape: tuple[int, int]) -> _Framed:
    """Read each frame's plane, rescale, and stack from an instance's
    functional groups, each group's one item, per frame or shared, as
    :func:`~.functional_groups.frame_group` gives it.

    An instance with neither Functional Groups Sequence has none of them.
    Planes are given only where every frame has one, from its Plane
    Position (Patient), Plane Orientation (Patient), and Pixel Measures
    groups. Rescales are given only where a Pixel Value Transformation group
    is present: then every frame must have its own finite Rescale Slope and
    Rescale Intercept, or no frame has a plane either, so that no volume
    takes frames whose values cannot be compared, and its values are
    Hounsfield units only where every frame's Rescale Type, which PS3.3
    Table C.7.6.16-10 requires, is HU. A frame's stack is its Frame
    Content group's Stack ID and Temporal Position Index, each empty where
    it gives none, and what it names of its phase is read from the same
    group (:func:`~.phases.named_by_frame`). Whatever cannot be read leaves
    out what it would give.
    """
    try:
        if not any(keyword in dataset for keyword in _FUNCTIONAL_GROUPS):
            return _Framed()
        return _read_framed(dataset, frames, shape)
    # Whatever pydicom raises, the frames are left unplaced.
    except Exception:  # pylint: disable = broad-exception-caught
        return _Framed(described=True)


def _read_framed(
    dataset: pydicom.Dataset, frames: int, shape: tuple[int, int]
) -> _Framed:
    # A Stack ID is unique only within a Dimension Organization UID, so
    # the frames of an instance of more than one have no stacks that can be
    # told apart, and none is placed.
    planes: list[_Plane] | None = [] if _organisations(dataset) <= 1 else None
    rescales: list[tuple[float, float]] | None = []
    stacks: list[tuple[str, str]] = []
    named: list[Named] = []
    rescaled = _in_groups(dataset, _RESCALING)
    hounsfield = rescaled
    for frame in range(frames):
        position, orientation, measures = (
            _group(dataset, frames, frame, keyword) for keyword in _PLACING
        )
        plane = _placed(
            None
            if orientation is None
            else _floats(orientation, "ImageOrientationPatient", 6),
            None if position is None else _floats(position, "ImagePositionPatient", 3),
            None if measures is None else _spacing(measures),
            shape,
        )
        if plane is None:
            planes = None
        elif planes is not None:
            planes.append(plane)
        if rescaled:
            item = _group(dataset, frames, frame, _RESCALING)
            slope = None if item is None else _number(item, "RescaleSlope", float)
            intercept = (
                None if item is None else _number(item, "RescaleIntercept", float)
            )
            if slope is None or intercept is None:
                rescales = planes = None
                hounsfield = False
            elif rescales is not None:
                rescales.append((float(slope), float(intercept)))
            hounsfield = (
                hounsfield
                and item is not None
                and "RescaleType" in item
                and _hounsfield(item)
            )
        content = _group(dataset, frames, frame, _CONTENT)
        stacks.append(
            (_text(content, "StackID"), _text(content, "TemporalPositionIndex"))
        )
        named.append(named_by_frame(content))
    return _Framed(
        described=True,
        planes=None if planes is None else tuple(planes),
        rescales=None if not rescaled or rescales is None else tuple(rescales),
        stacks=tuple(stacks),
        hounsfield=hounsfield,
        named=tuple(named),
    )


def _organisations(dataset: pydicom.Dataset) -> int:
    """How many distinct Dimension Organization UIDs an instance names.

    Its Dimension Organization Sequence, where present, must hold an item
    with a Dimension Organization UID for each; one that cannot be read
    raises, which :func:`_framed` takes as leaving its frames unplaced.
    """
    items = dataset.get("DimensionOrganizationSequence") or []
    uids = set()
    for item in items:
        uid = _uid(item, "DimensionOrganizationUID")
        if uid is None:
            raise ValueError("no Dimension Organization UID")
        uids.add(uid)
    return len(uids)


def _group(
    dataset: pydicom.Dataset, frames: int, frame: int, keyword: str
) -> pydicom.Dataset | None:
    """A frame's one item of a functional group, or None where
    :func:`~.functional_groups.frame_group` refuses it."""
    try:
        return frame_group(dataset, frames, frame, keyword)
    except ValueError:
        return None


def _in_groups(dataset: pydicom.Dataset, keyword: str) -> bool:
    """Whether a functional group is in the shared item or any frame's."""
    return any(
        keyword in item
        for sequence in _FUNCTIONAL_GROUPS
        for item in dataset.get(sequence) or []
    )


def _text(item: pydicom.Dataset | None, keyword: str) -> str:
    """An attribute's value as stripped text, or empty where it is absent."""
    if item is None:
        return ""
    value = item.get(keyword)
    return "" if value is None else str(value).strip()


def _hounsfield(dataset: pydicom.Dataset) -> bool:
    """Whether a data set's Rescale Type, if present, is HU."""
    if "RescaleType" not in dataset:
        return True
    try:
        value = dataset["RescaleType"].value
    except Exception:  # pylint: disable = broad-exception-caught
        return False
    return isinstance(value, str) and value.strip().upper() == "HU"


def _named(dataset: pydicom.Dataset, frames: int) -> tuple[Named, ...]:
    """What each frame of an instance without functional groups names of
    its phase: a single-frame instance's own attributes, and nothing for a
    frame of a multi-frame one."""
    if frames == 1:
        return (named_by_instance(dataset),)
    return (named_by_frame(None),) * frames


# The attributes by which stored values pad, and so are read as no patient.
_PADDING = ("PixelPaddingValue", "PixelPaddingRangeLimit")


def _dose_scale(dataset: pydicom.Dataset) -> float | None:
    """Dose Grid Scaling, where the data set is an RT Dose by its SOP Class
    whose stored values are unsigned or signed, by Pixel Representation of
    0 or 1, not padded, and scaled by a finite number above 0; otherwise
    None, as a padded grid has stored values that are read as no dose,
    which no level shows, and a grid without a scaling above 0 has no dose
    to show. A signed grid is shown at the levels of its doses below 0 as
    well as above (:mod:`~pymedphys._dicom.deidentify.qc_surfaces`)."""
    try:
        sop_class = str(dataset.get("SOPClassUID") or "")
    except Exception:  # pylint: disable = broad-exception-caught
        sop_class = ""
    scaling = _number(dataset, "DoseGridScaling", float)
    if (
        sop_class != qc_surfaces.RT_DOSE_STORAGE
        or _number(dataset, "PixelRepresentation", int) not in (0, 1)
        or any(keyword in dataset for keyword in _PADDING)
        or scaling is None
        or scaling <= 0
    ):
        return None
    return float(scaling)


def _dose_grid(
    dataset: pydicom.Dataset,
    spacing: tuple[float, float] | None,
    shape: tuple[int, int],
    frames: int,
    scale: float,
    signed: bool = False,
) -> qc_surfaces.Grid | qc_surfaces.Stacked | None:
    """The grid of an RT Dose instance of two or more frames, if it is rendered.

    Its frames must be evenly spaced. One whose axes do not lie along the
    patient's is a stack (:mod:`~pymedphys._dicom.deidentify.stack_sampling`)
    of its frames, each at its offset along the normal from the first.
    """
    if frames < 2:
        return None
    plane = _plane(dataset, spacing, shape)
    offsets = _floats(dataset, "GridFrameOffsetVector", frames)
    if plane is None or offsets is None:
        return None
    directions = (
        np.cross(plane.row, plane.column),
        np.array(plane.column),
        np.array(plane.row),
    )
    # Absolute z coordinates, which PS3.3 C.8.8.3.2 permits only for an
    # orientation of (1, 0, 0, 0, 1, 0), the first being the origin's; a grid
    # that does not meet this keeps its first offset, and is refused below.
    if (
        offsets[0] != 0
        and np.allclose(
            plane.row + plane.column, (1, 0, 0, 0, 1, 0), atol=_ORIENTATION_TOLERANCE
        )
        and abs(offsets[0] - plane.origin[2]) <= _STACKING_TOLERANCE
    ):
        offsets = tuple(offset - plane.origin[2] for offset in offsets)
    steps = np.diff(offsets)
    if (
        abs(offsets[0]) > _STACKING_TOLERANCE
        or not ((steps > 0).all() or (steps < 0).all())
        or np.ptp(steps) > _STACKING_TOLERANCE
    ):
        return None
    if _roles(directions) is None:
        try:
            stack = stack_sampling.Stack(
                plane.row + plane.column,
                [
                    np.array(plane.origin)
                    + offset * directions[0] / np.linalg.norm(directions[0])
                    for offset in offsets
                ],
                plane.spacing,
                shape,
            )
        except (stack_sampling.StackRefused, ValueError):
            return None
        return qc_surfaces.Stacked(stack, qc_surfaces.Threshold.DOSE, scale, signed)
    return qc_surfaces.grid(
        directions,
        offsets,
        plane.spacing,
        shape,
        qc_surfaces.Threshold.DOSE,
        scale,
        signed,
    )


class _Decoder:
    """Decodes an instance's frames one at a time, recording one that fails."""

    def __init__(self, refused: dict[int, NotPreviewedReason]) -> None:
        self._refused = refused
        # The run positions of written files of which a frame pads with more
        # than one stored value: every preview draws padding as one black, or
        # as no patient, so what those values hold, which could be a face,
        # is shown in none.
        self.mixed_padding: set[int] = set()

    def refuse(self, position: int, reason: NotPreviewedReason) -> None:
        """Record that an instance's pixel data cannot be previewed."""
        self._refused.setdefault(position, reason)

    def frame(self, instance: _Instance, index: int) -> np.ndarray | None:
        """Return one frame as (row, column[, sample]), or None.

        Monochrome frames are rescaled to float32, with padding as NaN; RGB
        frames are uint8.
        """
        if instance.position in self._refused:
            return None
        try:
            if instance.packed:
                (pixels,) = _packed_frames(instance, [index])
            elif instance.plugin in CHILD_ONLY_PLUGINS:
                (pixels,) = isolated_frames(instance.data, [index])
            else:
                pixels = np.asarray(
                    pydicom.pixels.pixel_array(
                        io.BytesIO(instance.data),
                        index=index,
                        decoding_plugin=instance.plugin,
                    )
                )
        except Exception:  # pylint: disable = broad-exception-caught
            self._refused[instance.position] = NotPreviewedReason.UNREADABLE
            return None
        return self._shown(instance, index, pixels, NotPreviewedReason.UNREADABLE)

    def frames(
        self,
        instance: _Instance,
        indices: Sequence[int] | None = None,
        reason: NotPreviewedReason = NotPreviewedReason.UNREADABLE,
        received: bool = False,
    ) -> Iterator[np.ndarray]:
        """Yield an instance's frames, or those at ``indices``, in ascending
        order, each once, as :meth:`frame` gives them, reading its file once.

        Stops at a frame that cannot be decoded, recording ``reason``. The
        frames of a file as ``received``, which is not released, are not
        checked for padding of more than one value.
        """
        if instance.position in self._refused:
            return
        wanted = sorted(set(range(instance.frames) if indices is None else indices))
        if not wanted:
            return
        try:
            decoded = (
                _packed_frames(instance, wanted)
                if instance.packed
                else isolated_frames(instance.data, indices)
                if instance.plugin in CHILD_ONLY_PLUGINS
                else pydicom.pixels.iter_pixels(
                    io.BytesIO(instance.data),
                    indices=None if indices is None else wanted,
                    decoding_plugin=instance.plugin,
                )
            )
            # Each frame is rescaled by its own Rescale Slope and Intercept.
            # Its index is counted alongside, not zipped, since zip would
            # hold the frame before while the next is decoded.
            count = 0
            for pixels in decoded:
                index = wanted[count]
                count += 1
                shown = self._shown(
                    instance, index, np.asarray(pixels), reason, received
                )
                if shown is None:
                    return
                yield shown
                # Freed before the next frame is decoded, so no two are held.
                del shown, pixels
        except Exception:  # pylint: disable = broad-exception-caught
            self._refused.setdefault(instance.position, reason)

    def _shown(
        self,
        instance: _Instance,
        index: int,
        pixels: np.ndarray,
        reason: NotPreviewedReason,
        received: bool = False,
    ) -> np.ndarray | None:
        shape = instance.shape + ((3,) if instance.colour else ())
        if pixels.size != math.prod(shape):
            self._refused[instance.position] = reason
            return None
        pixels = pixels.reshape(shape)
        if instance.colour:
            return pixels.astype(np.uint8)
        undrawn = None
        if instance.floating:
            pixels, undrawn, kinds = _drawn_floats(pixels, instance.padding)
            if kinds > 1 and not received:
                self.mixed_padding.add(instance.position)
        slope, intercept = instance.rescale_of(index)
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            shown = pixels.astype(np.float32) * np.float32(slope) + np.float32(
                intercept
            )
        padded = undrawn
        if instance.padding is not None and not instance.floating:
            low, high = instance.padding
            padded = (pixels >= low) & (pixels <= high)
            if low < high and not received and padded.any():
                values = pixels[padded]
                if values.min() != values.max():
                    self.mixed_padding.add(instance.position)
        if not _contrast_kept(pixels, shown, padded):
            self._refused[instance.position] = (
                reason if received else NotPreviewedReason.UNSUPPORTED
            )
            return None
        if padded is not None:
            shown[padded] = np.nan
        return shown


def _drawn_floats(
    pixels: np.ndarray, padding: tuple[float, float] | None
) -> tuple[np.ndarray, np.ndarray, int]:
    """Return a frame of floating-point values as previews draw it, the
    values that they do not draw, and how many kinds of value those are.

    Values that are not a number, and padding, are not drawn: every
    preview draws them as one black, or as no patient. Positive infinity is
    drawn above the frame's largest value that is drawn and finite, and
    negative infinity below its smallest, each by those values' range, or,
    where they are all one value, by its magnitude or 1, whichever is
    larger. A viewer that clips to a window would show an infinity as the
    finite values at that end of it, so a pattern drawn in an infinity
    beside those values, or among finite values that are all one value,
    would show in no preview; drawn apart from them, it shows, at the cost
    of some of the finite values' contrast. In a frame with no drawn finite
    value, infinities are not drawn either. The kinds of value not drawn
    are not a number, whatever its bits, since no viewer tells one apart
    from another, each infinity, and each padding value; a frame with more
    than one could hold a face in their pattern that no preview shows, so
    its instance is counted as not shown whole, as one that pads with more
    than one stored value is. A drawn value beyond float32 leaves the frame
    not previewed (:func:`_contrast_kept`).
    """
    nan = np.isnan(pixels)
    padded = np.zeros(pixels.shape, dtype=bool)
    if padding is not None:
        low, high = padding
        padded = (pixels >= low) & (pixels <= high)
    infinite = np.isinf(pixels)
    drawn = ~(nan | padded | infinite)
    undrawn = nan | padded
    shown = pixels
    if infinite.any():
        if drawn.any():
            shown = pixels.astype(np.float64)
            low, high = float(shown[drawn].min()), float(shown[drawn].max())
            gap = high - low or max(abs(high), 1.0)
            shown[np.isposinf(pixels)] = beyond(high, gap)
            shown[np.isneginf(pixels)] = beyond(low, -gap)
        else:
            undrawn = undrawn | infinite
    kinds = int(nan.any()) + len(np.unique(pixels[padded]))
    if not drawn.any():
        kinds += int(np.isposinf(pixels).any()) + int(np.isneginf(pixels).any())
    return shown, undrawn, kinds


# How many steps of float32 a frame's rescaled values must span, at least,
# where its stored values differ: the 256 grey levels of a preview's PNG.
_RESCALED_LEVELS = 256


def _contrast_kept(
    pixels: np.ndarray, shown: np.ndarray, padded: np.ndarray | None
) -> bool:
    """Whether a frame's rescaled values, as float32, keep what its stored
    values show, other than padding.

    A Rescale Slope and Rescale Intercept that are finite can still take a
    frame beyond float32, where its values are infinite or not a number, or
    collapse it, as a slope too small for float32 rounds to 0, so that a
    preview drawn of it is blank though it lists every frame. So every
    value must be finite, and where the stored values differ, the rescaled
    ones must span at least :data:`_RESCALED_LEVELS` steps of float32 at
    their magnitude, which a linear rescale spreads evenly over the frame's
    range.
    """
    if padded is not None:
        pixels, shown = pixels[~padded], shown[~padded]
    if not pixels.size:
        return True
    if not np.isfinite(shown).all():
        return False
    if pixels.min() == pixels.max():
        return True
    low, high = float(shown.min()), float(shown.max())
    step = float(np.spacing(np.float32(max(abs(low), abs(high)))))
    return high - low >= _RESCALED_LEVELS * step


def _packed_frames(instance: _Instance, indices: Sequence[int]) -> Iterator[np.ndarray]:
    """Yield the frames at ``indices`` of native Pixel Data of 1 bit, in
    order, as 0 and 1.

    The bits are packed across frames, from the least significant bit of
    each byte (PS3.5 Section 8.1.1), so a frame can start within a byte.
    Raises ValueError where the Pixel Data stop short of a frame.
    """
    data = pydicom.dcmread(io.BytesIO(instance.data)).PixelData
    size = instance.shape[0] * instance.shape[1]
    for index in indices:
        start = index * size
        first, stop = start // 8, -(-(start + size) // 8)
        if stop > len(data):
            raise ValueError("the Pixel Data stop short of a frame")
        bits = np.unpackbits(
            np.frombuffer(data, np.uint8, stop - first, first), bitorder="little"
        )
        offset = start - 8 * first
        yield bits[offset : offset + size].reshape(instance.shape)


def _series(instances: Sequence[_Instance]) -> Iterator[list[_Instance]]:
    """Yield each series, in order of its first position, its instances ordered."""
    groups: dict[object, list[_Instance]] = {}
    for instance in instances:
        uid = instance.series
        key = ("series", uid) if uid else ("instance", instance.position)
        groups.setdefault(key, []).append(instance)
    for group in groups.values():
        yield sorted(group, key=_order_key(group))


def _order_key(group: list[_Instance]):
    normal = _common_normal(group)
    if normal is not None:
        return lambda instance: (
            float(np.dot(normal, instance.plane.origin)),
            instance.position,
        )
    if all(instance.number is not None for instance in group):
        return lambda instance: (instance.number, instance.position)
    return lambda instance: instance.position


def _common_normal(group: list[_Instance]) -> np.ndarray | None:
    """The normal of the group's one orientation, if every instance has one."""
    planes = [instance.plane for instance in group]
    if not all(planes):
        return None
    first = planes[0]
    assert first is not None
    if not all(
        np.allclose(plane.row, first.row, atol=_ORIENTATION_TOLERANCE)
        and np.allclose(plane.column, first.column, atol=_ORIENTATION_TOLERANCE)
        for plane in planes
        if plane is not None
    ):
        return None
    return np.cross(first.row, first.column)


def _evenly(count: int, limit: int) -> list[int]:
    """Up to ``limit`` indices from 0 to ``count - 1``, evenly spaced, each once."""
    if count <= limit:
        return list(range(count))
    return sorted({round(i * (count - 1) / (limit - 1)) for i in range(limit)})


def _series_images(
    series: list[_Instance],
    decoder: _Decoder,
    guides: dict[str, list[tuple[_Guided, str | None]]] | None = None,
):
    frames = [
        (instance.position, frame)
        for instance in series
        for frame in range(instance.frames)
    ]
    chosen = {frames[i] for i in _evenly(len(frames), CINE_FRAMES)}
    volumes = _volumes(series)
    renders = _renders(series, volumes)
    # A volume too large for a surface render has no projection either, so
    # that no preview that could show a face draws its slices beyond its
    # cine strip, and their pixel data are held.
    projections: list[_Projection | _StackProjection | None] = [
        None
        if render.large
        else _Projection(volume)
        if volume.stack is None
        else _StackProjection(volume)
        for volume, render in zip(volumes, renders)
    ]
    in_volume = {each for volume in volumes for each in volume.slices}
    # Each RT Dose plane in no volume, mapped by the levels of its dose.
    planes = {
        instance.position: instance
        for instance in series
        if instance.frames == 1
        and instance.dose_scale is not None
        and (instance.position, 0) not in in_volume
    }
    reference = series[0].frame
    # Whether the guide drawn behind the contours and segments in the
    # series' Frame of Reference is still to be found: from the first
    # volume whose surface can be placed.
    guiding = (
        guides is not None
        and reference in guides
        and all(instance.frame == reference for instance in series)
    )
    tiles: list[tuple[int, int, np.ndarray, _Instance]] = []
    # Each slice's map is drawn as soon as it is decoded, so that only its
    # 8-bit map, or None, and not its pixels, is kept to the series' end.
    maps: list[tuple[_Instance, np.ndarray | None]] = []
    # The renders are sampled a batch at a time (_batches), the first with
    # the cine strip and the maps, so that a series of many volumes, such
    # as the phases of a respiratory-correlated CT, holds only one batch's
    # surface samples at once; each later batch reads its files again. The
    # cine strip is given once the first batch is read, and each volume's
    # projection, then its surface render, once its batch is drawn, so
    # that each is encoded as it is made and none is kept to the series'
    # end; a projection's slices are let go with its image. The previews
    # are given in the same order in any batches.
    for number, batch in enumerate(_batches(renders)):
        first = number == 0
        for index in batch:
            renders[index].begin()
        wanted = {
            each
            for index in batch
            if not renders[index].large
            for each in renders[index].places
        }
        for instance in series:
            needed = [
                frame
                for frame in range(instance.frames)
                if (instance.position, frame) in wanted
                or (
                    first
                    and (
                        (instance.position, frame) in chosen
                        or instance.position in planes
                    )
                )
            ]
            # Each file is read once a batch for the frames that its
            # previews draw, which are decoded one at a time, in order.
            count = 0
            for pixels in decoder.frames(instance, needed):
                frame = needed[count]
                count += 1
                each = (instance.position, frame)
                if first and each in chosen:
                    tiles.append(
                        (instance.position, frame, _fitted(pixels, instance), instance)
                    )
                for index in batch:
                    render = renders[index]
                    if each not in render.places:
                        continue
                    projection = (
                        projections[index] if index < len(projections) else None
                    )
                    if projection is not None:
                        projection.add(render.places[each], instance, pixels)
                    # A volume of RT Dose planes scales each by its own.
                    render.sampled.add(
                        pixels,
                        instance.dose_scale if render.planed else None,
                        render.places[each],
                    )
                if first and instance.position in planes:
                    maps.append((instance, _level_map(instance, pixels)))
                # Freed before the next frame is decoded, so no two are held.
                del pixels
        if first and tiles:
            image = _sheet(
                _windowed_tiles([(tile, instance) for _, _, tile, instance in tiles]),
                TILE_PIXELS,
                TILE_PIXELS,
            )
            yield (
                PreviewKind.SERIES_CINE,
                tuple((position, frame) for position, frame, *_ in tiles),
                len(frames),
                image,
            )
            del image
            tiles.clear()
        for index in batch:
            render = renders[index]
            if guiding and index < len(volumes):
                guide = _guide(volumes[index], render.sampled)
                if guide is not None:
                    assert guides is not None
                    guides[reference].append(((guide, render.shown), series[0].series))
                    guiding = False
            projection = projections[index] if index < len(projections) else None
            if projection is not None:
                projections[index] = None
                projected = projection.image()
                del projection
                if projected is not None:
                    yield projected
                del projected
            image = render.sampled.image()
            render.end()
            if image is not None:
                yield (render.kind, render.shown, len(render.shown), image)
            del image
    for instance, level_map in maps:
        if level_map is not None:
            yield (
                PreviewKind.SERIES_DOSE_LEVELS,
                ((instance.position, 0),),
                1,
                level_map,
            )


# The most voxels that the surface renders of one series sample at once,
# 256 MiB as float32: the renders of a series of many volumes, such as the
# phases of a respiratory-correlated CT or the time points of a perfusion
# scan, are sampled in batches within it, in order, and a volume that
# samples more alone is sampled alone, so that the surface samples held at
# once do not grow with the number of its volumes.
SAMPLED_AT_ONCE = 1 << 26


def _batches(renders: Sequence[_Render]) -> list[list[int]]:
    """The indices of the renders, in order, in batches that each sample no
    more than :data:`SAMPLED_AT_ONCE` voxels in all, or one render alone;
    always at least one batch, which may be empty."""
    batches: list[list[int]] = [[]]
    total = 0
    for index, render in enumerate(renders):
        if batches[-1] and total + render.size > SAMPLED_AT_ONCE:
            batches.append([])
            total = 0
        batches[-1].append(index)
        total += render.size
    return batches


def _level_map(instance: _Instance, pixels: np.ndarray) -> np.ndarray | None:
    """An RT Dose plane at full resolution, grey by the levels of its dose,
    or None if its scaling loses a dose (:func:`~.qc_surfaces.dose_values`)
    or it has more than :data:`~.qc_surfaces.MAXIMUM_DOSE_LEVELS` levels of
    either sign. A signed plane's map of its doses above 0 is followed, after
    columns of :data:`~.qc_surfaces.SIGN_RULE`, by the map of the magnitudes
    of its doses below 0."""
    assert instance.dose_scale is not None
    values = qc_surfaces.dose_values(pixels, instance.dose_scale)
    if values is None:
        return None
    finite = values[np.isfinite(values)]
    maps = []
    for below in (False, True) if instance.dose_signed else (False,):
        doses = -finite[finite < 0] if below else finite[finite > 0]
        levels = qc_surfaces.dose_levels(
            float(doses.max()) if doses.size else -math.inf,
            float(doses.min()) if doses.size else math.inf,
        )
        if len(levels) > qc_surfaces.MAXIMUM_DOSE_LEVELS:
            return None
        maps.append(qc_surfaces.level_bands(values, levels, below))
    if len(maps) == 1:
        return maps[0]
    rule = np.full(
        (values.shape[0], qc_surfaces.SIGN_RULE_PIXELS), qc_surfaces.SIGN_RULE, np.uint8
    )
    return np.concatenate([maps[0], rule, maps[1]], axis=1)


@dataclasses.dataclass
class _Render:
    """A surface render of a series, with its kind and the frames it shows,
    in order along its slice axis.

    ``planed`` is whether each is scaled by its own Dose Grid Scaling, as
    the planes of a volume of RT Dose planes are, and ``places`` gives each
    frame's place along the slice axis. Its surface samples the volume
    only from :meth:`begin` to :meth:`end`, so that its samples are held
    only while its batch is drawn (:func:`_batches`); ``size`` is how many
    voxels it samples, and ``large`` whether the volume is too large to
    render.
    """

    kind: PreviewKind
    shown: tuple[tuple[int, int], ...]
    grid: qc_surfaces.Grid | qc_surfaces.Stacked
    planed: bool = False
    places: dict[tuple[int, int], int] = dataclasses.field(init=False)
    size: int = dataclasses.field(init=False)
    large: bool = dataclasses.field(init=False)
    surface: qc_surfaces.Surface | None = dataclasses.field(init=False, default=None)

    def __post_init__(self) -> None:
        self.places = {each: index for index, each in enumerate(self.shown)}
        self.large = qc_surfaces.too_large(self.grid)
        self.size = qc_surfaces.sampled_voxels(self.grid)

    def begin(self) -> None:
        """Start sampling the volume."""
        self.surface = qc_surfaces.Surface(self.grid)

    def end(self) -> None:
        """Let the samples go, once the render is drawn."""
        self.surface = None

    @property
    def sampled(self) -> qc_surfaces.Surface:
        """The surface, between :meth:`begin` and :meth:`end`."""
        assert self.surface is not None
        return self.surface


def _renders(series: list[_Instance], volumes: Sequence[_Volume]) -> list[_Render]:
    """The surface renders of a series: each volume's, in the order of
    ``volumes``, then each RT Dose grid's.

    A volume's surface is at a fixed level where every slice is of a CT
    instance whose values are Hounsfield units; a volume of RT Dose planes,
    each of whose doses a dose-levels preview can show, is shown at each of
    its dose levels; and any other's surface, such as an MR or PET
    volume's, or a CT volume's of other units, is by Otsu's threshold.
    """
    members = {instance.position: instance for instance in series}
    renders = []
    for volume in volumes:
        instances = [members[position] for position, _ in volume.slices]
        kind = PreviewKind.SERIES_SURFACE
        planed = False
        if all(
            instance.modality == "CT" and instance.hounsfield for instance in instances
        ):
            threshold = qc_surfaces.Threshold.CT
        elif all(instance.dose_scale is not None for instance in instances):
            threshold = qc_surfaces.Threshold.DOSE
            kind = PreviewKind.SERIES_DOSE_LEVELS
            planed = True
        else:
            threshold = qc_surfaces.Threshold.OTSU
        # A signed dose series keeps its ladder below zero on either path.
        signed = threshold is qc_surfaces.Threshold.DOSE and any(
            instance.dose_signed for instance in series
        )
        if volume.stack is None:
            placed: qc_surfaces.Grid | qc_surfaces.Stacked = qc_surfaces.grid(
                volume.directions,
                volume.positions,
                volume.spacing,
                volume.shape,
                threshold,
                signed=signed,
            )
        else:
            placed = qc_surfaces.Stacked(volume.stack, threshold, signed=signed)
        renders.append(_Render(kind, volume.slices, placed, planed=planed))
    for instance in series:
        if instance.grid is not None:
            shown = tuple(
                (instance.position, frame) for frame in range(instance.frames)
            )
            renders.append(
                _Render(PreviewKind.SERIES_DOSE_LEVELS, shown, instance.grid)
            )
    return renders


def _guide(volume: _Volume, surface: qc_surfaces.Surface) -> qc_contours.Guide | None:
    """The surface of a volume, placed in the patient's coordinates.

    None if a slice is missing.
    """
    inside = surface.mask()
    if inside is None:
        return None
    lattice = surface.lattice
    if lattice is not None:
        zs, ys, xs = lattice.coordinates
        return qc_contours.Guide(inside, zs, ys, xs)
    normal, column, row = volume.directions
    axes = [int(np.argmax(np.abs(d))) for d in (normal, column, row)]
    origins = np.array(volume.origins)
    first = origins[0]
    along = (
        origins[:, axes[0]],
        first[axes[1]]
        + column[axes[1]] * volume.spacing[0] * np.arange(volume.shape[0]),
        first[axes[2]] + row[axes[2]] * volume.spacing[1] * np.arange(volume.shape[1]),
    )
    sampled = {
        axis: values[taken] for axis, values, taken in zip(axes, along, surface.sampled)
    }
    return qc_contours.Guide(inside, sampled[2], sampled[1], sampled[0])


def _contour_image(
    position: int,
    contours: qc_contours.Contours,
    guides: Mapping[str, list[tuple[_Guided, str | None]]],
):
    """The contour sheet of a structure set, drawn in each Frame of
    Reference of its ROIs with the surface of a volume in that frame: of a
    series that the structure set references, if there is one, or else the
    first; or None where it would be taller than
    :data:`~.qc_contours.MAXIMUM_SHEET_PIXELS`, which is drawn only until
    it is."""
    chosen: dict[str | None, qc_contours.Guide] = {}
    frames: list[tuple[int, int]] = [(position, 0)]
    for frame in contours.frames:
        candidates = guides.get(frame, []) if frame is not None else []
        found = next(
            (guided for guided, uid in candidates if uid in contours.series),
            candidates[0][0] if candidates else None,
        )
        if found is not None:
            chosen[frame] = found[0]
            frames.extend(each for each in found[1] if each not in frames)
    sheet = qc_contours.contour_sheet(
        contours, chosen, qc_contours.MAXIMUM_SHEET_PIXELS
    )
    if sheet is None:
        return None
    return (
        PreviewKind.STRUCTURE_SET_CONTOURS,
        tuple(frames),
        len(frames),
        sheet,
    )


def _segments_image(
    instance: _Instance,
    decoder: _Decoder,
    guides: Mapping[str, list[tuple[_Guided, str | None]]],
):
    """The segments sheet of a Segmentation, drawn with the surface of a
    volume in its Frame of Reference: of a series that it references, if
    there is one, or else the first; or None where
    :func:`~.qc_segments.segment_sheet` does not draw it, or a frame cannot
    be decoded. It lists the Segmentation's frames, then the volume's."""
    segments = instance.segments
    assert segments is not None
    candidates = guides.get(segments.frame, []) if segments.frame is not None else []
    found = next(
        (guided for guided, uid in candidates if uid in segments.series),
        candidates[0][0] if candidates else None,
    )
    sheet = qc_segments.segment_sheet(
        segments,
        decoder.frames(instance),
        None if found is None else found[0],
        qc_contours.MAXIMUM_SHEET_PIXELS,
    )
    if sheet is None:
        return None
    frames = [(instance.position, frame) for frame in range(instance.frames)]
    if found is not None:
        frames.extend(found[1])
    return PreviewKind.SEGMENTATION_SEGMENTS, tuple(frames), len(frames), sheet


def _instance_image(instance: _Instance, decoder: _Decoder):
    chosen = _evenly(instance.frames, CINE_FRAMES)
    frames = []
    for frame in chosen:
        pixels = decoder.frame(instance, frame)
        if pixels is None:
            return None
        frames.append((pixels, instance))
    tiles = _windowed_tiles(frames)
    return (
        PreviewKind.INSTANCE,
        tuple((instance.position, frame) for frame in chosen),
        instance.frames,
        _sheet(tiles, tiles[0].shape[0], tiles[0].shape[1]),
    )


def _redaction_images(
    instance: _Instance, source: bytes | None, entry: RedactionEntry, decoder: _Decoder
) -> list[_Encoded]:
    """Each frame of a cleaned instance, as written, beside the frame as
    received where it has regions; none if a frame cannot be decoded."""
    regions = dict(entry.regions)
    received = None
    if regions:
        received = None if source is None else _instance(instance.position, source)
        if not (
            isinstance(received, _Instance)
            and received.shape == instance.shape
            and received.frames == instance.frames
            and received.colour == instance.colour
        ):
            decoder.refuse(instance.position, NotPreviewedReason.SOURCE_NOT_SHOWN)
            return []
    written = decoder.frames(instance)
    sources = iter(())
    if isinstance(received, _Instance):
        # Only here are frames decoded as received; every other decoding is
        # of a file as written, whose padding of more than one value holds it.
        sources = decoder.frames(
            received,
            sorted(regions),
            NotPreviewedReason.SOURCE_NOT_SHOWN,
            received=True,
        )
    images = []
    for index in range(instance.frames):
        after = next(written, None)
        boxes = regions.get(index, ())
        before = next(sources, None) if boxes else None
        if after is None or (boxes and before is None):
            return []
        images.append(
            (
                PreviewKind.REDACTION,
                ((instance.position, index),),
                instance.frames,
                png(_redaction_image(instance, after, before, boxes)),
            )
        )
        images.append(
            (
                PreviewKind.REVIEW_FRAME,
                ((instance.position, index),),
                instance.frames,
                png(
                    review_frame(after if before is None else before, instance.inverted)
                ),
            )
        )
    return images


def review_frame(frame: np.ndarray, inverted: bool = False) -> np.ndarray:
    """Return a frame as the redaction review app shows it (D-059).

    An RGB frame is returned as it is. A monochrome frame's finite values
    are mapped linearly, from its smallest to its largest, to the 16-bit
    samples 1 to 65,535, brightest last, so inverted for MONOCHROME1, and
    padding, which is NaN, to 0, so that the app can window it as it
    likes. Distinct values stay distinct wherever the frame spans at most
    65,535 equally spaced values, as stored values of up to 16 bits under
    one linear rescale do; a frame that spans more is quantised to that
    many levels, which no display can tell apart.

    Examples
    --------
    >>> import numpy as np
    >>> review_frame(np.array([[-1000.0, 0.0], [np.nan, 1000.0]], np.float32))
    array([[    1, 32768],
           [    0, 65535]], dtype=uint16)
    """
    if frame.ndim == 3:
        return frame
    finite = np.isfinite(frame)
    if not finite.any():
        return np.zeros(frame.shape, np.uint16)
    values = frame.astype(np.float64)
    low, high = float(values[finite].min()), float(values[finite].max())
    scaled = (values - low) / (high - low) if high > low else np.zeros(frame.shape)
    if inverted:
        scaled = 1.0 - scaled
    samples = np.zeros(frame.shape, np.uint16)
    samples[finite] = np.round(scaled[finite] * 65534).astype(np.uint16) + 1
    return samples


def _redaction_image(
    instance: _Instance, after: np.ndarray, before: np.ndarray | None, boxes
) -> np.ndarray:
    """A frame as written, in grey if monochrome, or, with regions, in
    colour beside the frame as received, both windowed from it.

    A monochrome frame as written is shown again over its full range, from
    the smallest value to the largest of the frame as received, or as
    written where it has no regions, as the text finder searches it, so
    that text at or near the extremes, which the percentile window shows
    as white or black with whatever else lies there, stands apart.
    """
    if instance.colour:
        if before is None:
            return after
        return _beside([_outlined(image, boxes) for image in (before, after)])
    reference = after if before is None else before
    windows = (_window(reference), _full_range(reference))
    shown = [_grey(after, window, instance.inverted) for window in windows]
    if before is None:
        return _beside(shown)
    shown.insert(0, _grey(before, windows[0], instance.inverted))
    return _beside(
        [
            _outlined(np.repeat(image[..., np.newaxis], 3, axis=2), boxes)
            for image in shown
        ]
    )


def _beside(images: list[np.ndarray]) -> np.ndarray:
    """Lay images of one shape out from left to right, with a grey gutter
    between each and the next."""
    gutter = np.empty(
        (images[0].shape[0], _GUTTER_PIXELS, *images[0].shape[2:]), np.uint8
    )
    gutter[...] = _GUTTER if images[0].ndim == 3 else _GUTTER[0]
    laid: list[np.ndarray] = []
    for image in images:
        laid.extend([gutter, image] if laid else [image])
    return np.hstack(laid)


def _outlined(image: np.ndarray, boxes) -> np.ndarray:
    """Draw each box's edge pixels in the outline colour, clipped to the image."""
    outlined = image.copy()
    rows, columns = image.shape[:2]
    for box in boxes:
        top, left = min(box.top, rows - 1), min(box.left, columns - 1)
        bottom, right = min(box.bottom, rows), min(box.right, columns)
        outlined[top, left:right] = _OUTLINE
        outlined[bottom - 1, left:right] = _OUTLINE
        outlined[top:bottom, left] = _OUTLINE
        outlined[top:bottom, right - 1] = _OUTLINE
    return outlined


def _fitted(frame: np.ndarray, instance: _Instance) -> np.ndarray:
    """Scale a frame by nearest neighbour to fit the tile, keeping its aspect."""
    rows, columns = frame.shape[:2]
    row_spacing, column_spacing = instance.spacing or (1.0, 1.0)
    height, width = rows * row_spacing, columns * column_spacing
    scale = TILE_PIXELS / max(height, width)
    return _resampled(
        frame,
        max(1, min(TILE_PIXELS, round(height * scale))),
        max(1, min(TILE_PIXELS, round(width * scale))),
    )


def _resampled(image: np.ndarray, rows: int, columns: int) -> np.ndarray:
    """Sample an image by nearest neighbour to the given shape."""
    row_index = np.minimum(
        (np.arange(rows) + 0.5) * image.shape[0] // rows, image.shape[0] - 1
    ).astype(int)
    column_index = np.minimum(
        (np.arange(columns) + 0.5) * image.shape[1] // columns, image.shape[1] - 1
    ).astype(int)
    sampled: np.ndarray = image[row_index][:, column_index]
    return sampled


def _windowed_tiles(tiles: list[tuple[np.ndarray, _Instance]]) -> list[np.ndarray]:
    """Window monochrome tiles together, and give every tile one sample layout.

    If any tile is RGB, every tile is given as RGB.
    """
    monochrome = [tile for tile, instance in tiles if not instance.colour]
    window = (
        _window(np.concatenate([tile.ravel() for tile in monochrome]))
        if monochrome
        else None
    )
    colour = any(instance.colour for _, instance in tiles)
    shown = []
    for tile, instance in tiles:
        if not instance.colour:
            assert window is not None
            tile = _grey(tile, window, instance.inverted)
            if colour:
                tile = np.repeat(tile[..., np.newaxis], 3, axis=2)
        shown.append(tile)
    return shown


def _window(values: np.ndarray) -> tuple[float, float]:
    """The window from the 0.5th to the 99.5th percentile of the finite
    values, or, where those are drawn alike, the full range.

    Where all but a few values are one value, as in a frame of one value
    with a small pattern of another, both percentiles are that value; a
    window of a fixed width about it would draw a pattern of a value
    within that width, or of one that the width is lost against at the
    value's magnitude, as the value itself, so the full range is used
    instead (:func:`_full_range`).
    """
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return -0.5, 0.5
    low, high = (float(value) for value in np.percentile(finite, _PERCENTILES))
    return (low, high) if _apart(low, high) else _full_range(finite)


def _full_range(values: np.ndarray) -> tuple[float, float]:
    """The window from the smallest value to the largest, under which no
    value is clipped.

    A uniform image is shown mid-grey, so that it stands out from the black
    around the tiles, by a window about its value wide enough to be kept
    apart from it at its magnitude.
    """
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return -0.5, 0.5
    low, high = float(finite.min()), float(finite.max())
    if _apart(low, high):
        return low, high
    half = max(0.5, abs(low) * 2.0**-10)
    return low - half, low + half


def _apart(low: float, high: float) -> bool:
    """Whether a window from ``low`` to ``high`` draws values apart: its
    limits differ as float32, which previews are drawn in, and its width is
    finite."""
    return bool(np.float32(high) > np.float32(low)) and math.isfinite(high - low)


def _grey(image: np.ndarray, window: tuple[float, float], inverted: bool) -> np.ndarray:
    """Draw an image as 8-bit grey under a window from ``low`` to ``high``.

    Each value and each limit is halved before they are subtracted, which
    is exact in binary floating point: values that float32 holds can lie
    further apart than float32 holds, as -3e38 and 3e38 do, and their
    difference, and the window's width, would then overflow float32, in
    which a float32 image is drawn, and draw the image black. Halved, both
    stay within float32.
    """
    low, high = window
    scaled = np.clip((image * 0.5 - low * 0.5) / ((high - low) * 0.5), 0.0, 1.0)
    if inverted:
        scaled = 1.0 - scaled
    # Padding, which is NaN, is black whatever the photometric interpretation.
    scaled = np.nan_to_num(scaled, nan=0.0)
    return np.round(scaled * 255).astype(np.uint8)


def _sheet(tiles: list[np.ndarray], cell_rows: int, cell_columns: int) -> np.ndarray:
    """Lay tiles out in rows of :data:`CINE_COLUMNS`, each centred in its cell."""
    columns = min(CINE_COLUMNS, len(tiles))
    rows = math.ceil(len(tiles) / columns)
    trailing = tiles[0].shape[2:]
    sheet = np.zeros((rows * cell_rows, columns * cell_columns, *trailing), np.uint8)
    for index, tile in enumerate(tiles):
        top = (index // columns) * cell_rows + (cell_rows - tile.shape[0]) // 2
        left = (index % columns) * cell_columns + (cell_columns - tile.shape[1]) // 2
        sheet[top : top + tile.shape[0], left : left + tile.shape[1]] = tile
    return sheet


@dataclasses.dataclass(frozen=True)
class _Volume:
    """Slices of a series that form a volume, and the roles of its three axes.

    Axis 0 runs through the slices along the normal; axis 1 down the rows,
    along the plane's column direction; axis 2 along the columns, along its
    row direction. A volume whose axes lie along the patient's, with its
    slices stacked along the normal, has the roles of its axes and no stack;
    any other, such as one with a gantry tilt, sheared, or oblique, has a
    stack and no roles, and is sampled by
    :mod:`~pymedphys._dicom.deidentify.stack_sampling`.
    """

    # Each slice's run position and frame, ascending along the normal.
    slices: tuple[tuple[int, int], ...]
    origins: tuple[tuple[float, float, float], ...]  # each slice's
    positions: tuple[float, ...]  # along the normal, ascending, one per slice
    directions: tuple[np.ndarray, np.ndarray, np.ndarray]
    spacing: tuple[float, float]  # between rows, then between columns
    shape: tuple[int, int]
    # The axes along the patient's anterior-posterior, superior-inferior,
    # and left-right directions.
    roles: tuple[int, int, int] | None
    # The slices, in the order of ``slices``.
    stack: stack_sampling.Stack | None


def _volumes(series: list[_Instance]) -> list[_Volume]:
    """The volumes of a series, one for each stack and time point that forms one.

    Its frames are grouped by the scope of their instance's stacks
    (:func:`_scope`), then by their Stack ID and Temporal Position Index, as
    their Frame Content functional groups give them, so that the frames of
    a multi-frame instance at each time point, or in each stack, can each
    form a volume, and frames of instances that no Concatenation joins never
    share one. The instances without functional groups, such as single-frame
    CT Images, form one group of their own. A group whose slices repeat a
    position is parted into its phases, by the time point or acquisition
    that each slice names (:func:`~.phases.split`), each of which may form a
    volume, so that the single-frame instances of a respiratory-correlated
    CT or a perfusion scan form one for each time point, and no volume holds
    two slices at one position, whose union could hide the surface of
    either. A series with a colour instance, or a Segmentation, which only
    its segments sheet shows (D-017), forms none.
    """
    if any(instance.colour or instance.segmentation for instance in series):
        return []
    groups: dict[tuple[str, str, str], list[tuple[_Instance, int]]] = {}
    for instance in series:
        for frame in range(instance.frames):
            groups.setdefault(instance.stack_of(frame), []).append((instance, frame))
    found = (_volume(part) for group in groups.values() for part in _phases_of(group))
    return [volume for volume in found if volume is not None]


def _phases_of(
    group: list[tuple[_Instance, int]],
) -> list[list[tuple[_Instance, int]]]:
    """A group's slices parted into phases where they repeat a position, as
    :func:`~.phases.split` parts them along the first slice's normal; the
    group whole where any slice has no plane, or where they cannot be
    parted, so that :func:`_volume` refuses it as it would."""
    planes = [instance.plane_of(frame) for instance, frame in group]
    if not planes or any(plane is None for plane in planes):
        return [group]
    placed = [plane for plane in planes if plane is not None]
    normal = np.cross(placed[0].row, placed[0].column)
    parts = split(
        [float(np.dot(normal, plane.origin)) for plane in placed],
        [instance.named_of(frame) for instance, frame in group],
    )
    if parts is None:
        return [group]
    return [[group[index] for index in part] for part in parts]


def _volume(group: list[tuple[_Instance, int]]) -> _Volume | None:
    """The volume of slices, each an instance's frame, or None unless at
    least :data:`VOLUME_SLICES` of them, each with a plane, of one size,
    orientation, and pixel spacing, lie at distinct positions along the
    normal, with row and column directions each of unit length and
    perpendicular (:class:`~.stack_sampling.Stack`) unless the volume's axes
    lie along the patient's with its slices stacked along the normal."""
    if len(group) < VOLUME_SLICES:
        return None
    planes = [instance.plane_of(frame) for instance, frame in group]
    first = planes[0]
    if first is None or any(
        plane is None
        or plane.shape != first.shape
        or not np.allclose(plane.spacing, first.spacing)
        or not np.allclose(plane.row, first.row, atol=_ORIENTATION_TOLERANCE)
        or not np.allclose(plane.column, first.column, atol=_ORIENTATION_TOLERANCE)
        for plane in planes
    ):
        return None
    placed = [plane for plane in planes if plane is not None]
    normal = np.cross(first.row, first.column)
    # In order along the normal, then of run position and frame, as a
    # series of single-frame instances is ordered.
    order = sorted(
        range(len(group)),
        key=lambda i: (
            float(np.dot(normal, placed[i].origin)),
            group[i][0].position,
            group[i][1],
        ),
    )
    origins = np.array([placed[i].origin for i in order])
    directions = (normal, np.array(first.column), np.array(first.row))
    positions = _stacked(origins, normal)
    roles = None if positions is None else _roles(directions)
    stack = None
    if positions is None or roles is None:
        # A gantry tilt, a shear, or an oblique orientation, sampled to
        # voxels along the patient's axes.
        try:
            stack = stack_sampling.Stack(
                first.row + first.column, origins, first.spacing, first.shape
            )
        except (stack_sampling.StackRefused, ValueError):
            return None
        positions = tuple(float(offset) for offset in stack.offsets)
    return _Volume(
        tuple((group[i][0].position, group[i][1]) for i in order),
        tuple(placed[i].origin for i in order),
        positions,
        directions,
        first.spacing,
        first.shape,
        roles=roles,
        stack=stack,
    )


def _stacked(origins: np.ndarray, normal: np.ndarray) -> tuple[float, ...] | None:
    """Each slice's position along the normal, if the slices stack along it.

    None if two share a position, or if any is offset within the plane or
    sheared, as by a gantry tilt.
    """
    positions = tuple(float(position) for position in origins @ normal)
    if any(later - earlier <= 1e-6 for earlier, later in zip(positions, positions[1:])):
        return None
    offsets = origins - origins[0]
    in_plane = offsets - np.outer(offsets @ normal, normal)
    if np.abs(in_plane).max() > _STACKING_TOLERANCE:
        return None
    return positions


def _roles(directions) -> tuple[int, int, int] | None:
    """The axes along anterior-posterior, superior-inferior, and left-right.

    None unless each lies along a different one of the three, within
    :data:`_ALIGNMENT_TOLERANCE`.
    """
    along = []
    for direction in directions:
        magnitudes = np.abs(np.asarray(direction, dtype=float))
        axis = int(np.argmax(magnitudes))
        if np.delete(magnitudes, axis).max() > _ALIGNMENT_TOLERANCE:
            return None
        along.append(axis)
    if len(set(along)) != 3:
        return None
    # The patient's y (anterior-posterior), z (superior), then x (left).
    return along.index(1), along.index(2), along.index(0)


class _Projection:
    """Accumulates a volume's maximum intensity projection, slice by slice."""

    def __init__(self, volume: _Volume) -> None:
        self._volume = volume
        self._slices: dict[int, np.ndarray] = {}
        self._maximum: np.ndarray | None = None
        self._added: set[int] = set()
        self._inverted: list[bool] = []

    def add(self, index: int, instance: _Instance, frame: np.ndarray) -> None:
        """Add the slice at ``index`` along the normal, in any order."""
        if index in self._added:
            return
        self._added.add(index)
        self._inverted.append(instance.inverted)
        assert self._volume.roles is not None
        anterior = self._volume.roles[0]
        if anterior == 0:
            # fmax ignores padding, which is NaN, unless every value is.
            self._maximum = (
                frame.copy() if self._maximum is None else np.fmax(self._maximum, frame)
            )
        else:
            self._slices[index] = np.fmax.reduce(frame, axis=anterior - 1)

    def image(self):
        volume = self._volume
        if len(self._added) != len(volume.positions):
            return None  # a slice could not be decoded
        assert volume.roles is not None
        anterior, vertical, _ = volume.roles
        coordinates = {
            0: np.array(volume.positions) - volume.positions[0],
            1: np.arange(volume.shape[0]) * volume.spacing[0],
            2: np.arange(volume.shape[1]) * volume.spacing[1],
        }
        if anterior == 0:
            assert self._maximum is not None
            image, axes = self._maximum, (1, 2)
        else:
            image = np.stack([self._slices[i] for i in range(len(volume.positions))])
            axes = (0, 3 - anterior)
        if axes.index(vertical) == 1:
            image, axes = image.T, (axes[1], axes[0])
        in_plane = [volume.spacing[axis - 1] for axis in axes if axis != 0]
        step = min(in_plane)
        extents = [float(coordinates[axis][-1]) for axis in axes]
        step = max(step, max(extents) / (MIP_PIXELS - 1))
        for dimension, axis in enumerate(axes):
            # The end is kept, though the division falls a little short of it.
            count = math.floor(extents[dimension] / step + 1e-6) + 1
            wanted = np.arange(count) * step
            nearest = _nearest(coordinates[axis], wanted)
            sampled = np.take(image, nearest, axis=dimension)
            if axis == 0:
                # Each slice is also taken into the pixel nearest it by its
                # maximum, so that every slice is drawn where slices are
                # closer than the pixels.
                np.fmax.at(
                    np.moveaxis(sampled, dimension, 0),
                    _nearest(wanted, coordinates[axis]),
                    np.moveaxis(image, dimension, 0),
                )
            image = sampled
        vertical, horizontal = (volume.directions[axis] for axis in axes)
        if vertical[2] > 0:  # increasing index runs superior, so flip
            image = image[::-1]
        if horizontal[0] < 0:  # increasing index runs to the patient's right
            image = image[:, ::-1]
        shown = _grey(image, _window(image.ravel()), all(self._inverted))
        return PreviewKind.SERIES_MIP, volume.slices, len(volume.positions), shown


class _StackProjection:
    """Accumulates the maximum intensity projection of a volume that a
    stack places, such as one with a gantry tilt, sheared, or oblique, slice
    by slice.

    The stack is sampled (:mod:`~pymedphys._dicom.deidentify.stack_sampling`)
    to cubic voxels along the patient's axes, of its smaller pixel spacing,
    or larger where needed to keep each axis within :data:`MIP_PIXELS` and
    the voxels within :data:`MIP_VOXELS`, each
    voxel taking its nearest slice's pixel and the pixels of every slice
    that crosses it, by their maximum, so that every slice is drawn; and the
    voxels are projected along the anterior-posterior axis as each slice is
    added, so that only the projection is held, with the patient's head at
    the top and right on the viewer's left. A voxel that takes no pixel is
    shown black, as padding is.
    """

    def __init__(self, volume: _Volume) -> None:
        assert volume.stack is not None
        self._volume = volume
        stack = volume.stack
        low, high = stack.bounds
        extents = high - low
        step = max(
            min(stack.spacing),
            float(np.max(extents)) / (MIP_PIXELS - 1),
            (float(np.prod(extents)) / MIP_VOXELS) ** (1 / 3),
        )
        lattice = stack.lattice(step)
        # The lattice holds a voxel more along each axis than its extent
        # divided by its side, so it is coarsened until within bounds.
        while math.prod(lattice.shape) > MIP_VOXELS:
            step *= 1.01
            lattice = stack.lattice(step)
        self._slabs = qc_surfaces.Slabs(stack, lattice)
        shape = self._slabs.lattice.shape
        # From superior, then from the patient's right.
        self._maximum = np.full((shape[0], shape[2]), np.nan, np.float32)
        self._added: set[int] = set()
        self._inverted: list[bool] = []

    def add(self, index: int, instance: _Instance, frame: np.ndarray) -> None:
        """Add the slice at ``index`` along the normal, in any order."""
        if index in self._added:
            return
        self._added.add(index)
        self._inverted.append(instance.inverted)
        values = np.asarray(frame, np.float32)
        for taken in self._slabs.taken(index):
            superior, _, right = taken.indices
            # fmax ignores padding, which is NaN, unless every value is.
            np.fmax.at(
                self._maximum,
                (superior, right),
                values[taken.rows, taken.columns],
            )

    def image(self):
        volume = self._volume
        if len(self._added) != len(volume.positions):
            return None  # a slice could not be decoded
        image = self._maximum
        shown = _grey(image, _window(image.ravel()), all(self._inverted))
        return PreviewKind.SERIES_MIP, volume.slices, len(volume.positions), shown


def _nearest(coordinates: np.ndarray, wanted: np.ndarray) -> np.ndarray:
    """The index of the coordinate nearest each wanted one; coordinates ascend."""
    if len(coordinates) == 1:
        return np.zeros(len(wanted), np.intp)
    right = np.clip(np.searchsorted(coordinates, wanted), 1, len(coordinates) - 1)
    left = right - 1
    closer_left = (wanted - coordinates[left]) <= (coordinates[right] - wanted)
    return np.where(closer_left, left, right)


def png(image: np.ndarray) -> bytes:
    """Return an 8-bit greyscale or RGB image, or a 16-bit greyscale one, as
    a PNG file.

    Parameters
    ----------
    image : numpy.ndarray
        uint8, of shape (rows, columns) or (rows, columns, 3), or uint16 of
        shape (rows, columns).

    Returns
    -------
    bytes
        A PNG with only its IHDR, IDAT, and IEND chunks, each row filtered
        with filter type 0.

    Examples
    --------
    >>> import numpy as np
    >>> png(np.zeros((2, 3), np.uint8))[:8]
    b'\\x89PNG\\r\\n\\x1a\\n'
    """
    wide = image.dtype == np.uint16 and image.ndim == 2
    if not wide and (
        image.dtype != np.uint8
        or not (image.ndim == 2 or (image.ndim == 3 and image.shape[2] == 3))
    ):
        raise ValueError(
            "a PNG needs a uint8 image of grey or RGB samples, or a uint16 "
            "image of grey samples"
        )
    rows, columns = image.shape[:2]
    if rows < 1 or columns < 1:
        raise ValueError("a PNG needs at least one pixel")
    colour_type = 0 if image.ndim == 2 else 2
    depth = 16 if wide else 8
    header = struct.pack(">IIBBBBB", columns, rows, depth, colour_type, 0, 0, 0)
    # PNG holds 16-bit samples most significant byte first.
    raw = (
        np.ascontiguousarray(image.astype(">u2") if wide else image)
        .view(np.uint8)
        .reshape(rows, -1)
    )
    filtered = np.concatenate([np.zeros((rows, 1), np.uint8), raw], axis=1)
    return (
        _PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(filtered.tobytes(), 6))
        + _chunk(b"IEND", b"")
    )


def decoded_png(data: bytes) -> np.ndarray:
    """Return the image of a PNG file that :func:`png` wrote.

    Only what :func:`png` writes is read: 8-bit grey or RGB, or 16-bit grey,
    not interlaced, each row filtered with filter type 0.

    Returns
    -------
    numpy.ndarray
        uint8 of shape (rows, columns) or (rows, columns, 3), or uint16 of
        shape (rows, columns).

    Raises
    ------
    ValueError
        If the file is not one that :func:`png` writes, or is damaged.

    Examples
    --------
    >>> import numpy as np
    >>> image = np.array([[0, 1], [256, 65535]], np.uint16)
    >>> np.array_equal(decoded_png(png(image)), image)
    True
    """
    if not data.startswith(_PNG_SIGNATURE):
        raise ValueError("not a PNG file")
    offset, header, compressed = len(_PNG_SIGNATURE), None, []
    while True:
        if offset + 8 > len(data):
            raise ValueError("a PNG file ends before its IEND chunk")
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        kind = data[offset + 4 : offset + 8]
        body = data[offset + 8 : offset + 8 + length]
        stored = data[offset + 8 + length : offset + 12 + length]
        if len(body) != length or len(stored) != 4:
            raise ValueError("a PNG chunk is cut short")
        if struct.unpack(">I", stored)[0] != zlib.crc32(kind + body) & 0xFFFFFFFF:
            raise ValueError("a PNG chunk is damaged")
        offset += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            compressed.append(body)
        elif kind == b"IEND":
            break
    if header is None:
        raise ValueError("a PNG file has no header")
    columns, rows, depth, colour_type, compression, filtering, interlace = header
    if (depth, colour_type) not in ((8, 0), (8, 2), (16, 0)) or (
        compression,
        filtering,
        interlace,
    ) != (0, 0, 0):
        raise ValueError("a PNG file of a kind that is not read")
    samples = 3 if colour_type == 2 else 1
    width = columns * samples * depth // 8
    raw = np.frombuffer(zlib.decompress(b"".join(compressed)), np.uint8)
    if raw.size != rows * (width + 1):
        raise ValueError("a PNG file's image is not of its size")
    raw = raw.reshape(rows, width + 1)
    if raw[:, 0].any():
        raise ValueError("a PNG file's rows are filtered")
    pixels = raw[:, 1:]
    if depth == 16:
        return pixels.copy().view(">u2").astype(np.uint16).reshape(rows, columns)
    return pixels.reshape(
        (rows, columns, 3) if samples == 3 else (rows, columns)
    ).copy()


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )
