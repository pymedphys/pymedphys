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
- a frontal maximum intensity projection of each series that forms a
  volume: at least :data:`VOLUME_SLICES` single-frame instances of one size,
  orientation, and pixel spacing, at distinct positions stacked along the
  normal of their orientation, whose axes lie along the patient's
  anterior-posterior, left-right, and superior-inferior directions. A
  multi-frame volume, such as an Enhanced CT image, is shown by its cine
  strip only. It is projected along the anterior-posterior axis and shown
  with the patient's head at the top and right on the viewer's left, sampled
  to square pixels by nearest neighbour, at most :data:`MIP_PIXELS` a side,
  each slice also taken into the pixel nearest it by the maximum, so that
  every slice is drawn where slices are closer than the pixels;
- a sheet of renders of the skin surface of each such volume, from the
  front, the two obliques, the two profiles, and behind, as
  :mod:`~pymedphys._dicom.deidentify.qc_surfaces` describes, or, for a
  volume of RT Dose planes, and for each RT Dose instance of two or more
  frames whose grid lies along the patient's axes with its frames evenly
  spaced, a dose-levels sheet of such renders at each of its dose levels;
  one that :mod:`~pymedphys._dicom.deidentify.qc_surfaces` finds too large
  to render has none, and such a volume has no projection either, so that
  its slices beyond its cine strip are held;
  an RT Dose is shown so only where it is one by its SOP Class, and its
  stored values are unsigned, not padded, not rescaled, and scaled by a
  finite Dose Grid Scaling above 0 to doses that float32 holds, each above
  0 still above 0 and none infinite;
- a dose-levels map of each RT Dose plane of one frame, so shown, that is
  in no volume, at full resolution, grey by how many of its dose levels
  each pixel reaches, so that each level's outline is an edge;
- a contour sheet of each instance with contours, such as an RT Structure
  Set, high-risk or not, since a face verdict can release only what a
  reviewer saw: its contours as written, drawn in each Frame of Reference
  of its ROIs with the surface of a volume in that frame, of a series that
  it references where there is one, or else of the first, as
  :mod:`~pymedphys._dicom.deidentify.qc_contours` describes;
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
  or colour, is reported rather than shown in part.

A series is the instances that share a Series Instance UID, or an instance
alone without one. Its instances are ordered by their positions along the
normal where every one has a position and they share an orientation, or else
by Instance Number where every one has one, or else by run position, with
ties in run position order. Each
preview lists the frames it shows, by run position and frame index from 0,
and how many frames its series or instance has.

Monochrome pixel data are rescaled by Rescale Slope and Rescale Intercept,
where both can be read, and windowed from the 0.5th to the 99.5th percentile
of what the preview shows, other than a redaction preview's full-range
image, leaving out the stored values that Pixel Padding Value and Pixel
Padding Range Limit name, which are shown black; MONOCHROME1 is inverted so
that higher values are darker. Since that black shows one value, an instance
of which a frame as written pads with more than one stored value, which
could hold an image that every preview shows black, is not counted as
shown, so that no verdict releases its pixel data. Colour pixel data with
8 bits allocated are shown as RGB: as they are, or converted from YBR_FULL
or YBR_FULL_422 by pydicom, while JPEG 2000's YBR_ICT and YBR_RCT are
decoded to RGB. Compressed pixel data are decoded by the plugin
that :data:`.pixel_decoding.DECODING_PLUGINS` pins for its transfer syntax.
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

from .pixel_decoding import DECODING_PLUGINS, decoder_available
from . import qc_contours, qc_surfaces
from .face_review import is_rt_dose
from .qc_pack import (
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
VOLUME_SLICES = 3

_PERCENTILES = (0.5, 99.5)
_MONOCHROME = frozenset({"MONOCHROME1", "MONOCHROME2"})
# Shown as RGB, which pydicom gives for each of them by default.
_COLOUR = frozenset({"RGB", "YBR_FULL", "YBR_FULL_422", "YBR_ICT", "YBR_RCT"})
_FLOAT_PIXEL_DATA = ("FloatPixelData", "DoubleFloatPixelData")
# An axis lies along a patient axis when its other two direction cosines are
# each at most this; a projection along an oblique axis would superimpose
# what a frontal view keeps apart.
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
    padding: tuple[int, int] | None  # stored values, inclusive, not shown
    frames: int
    colour: bool
    inverted: bool
    rescale: tuple[float, float]
    spacing: tuple[float, float] | None
    plane: _Plane | None
    number: int | None
    modality: str
    grid: qc_surfaces.Grid | None  # an RT Dose grid that dose levels show
    frame: str | None  # Frame of Reference UID
    # Whether its native Pixel Data hold no more than its frames, with at most
    # one byte of padding; the bytes beyond them are in no frame a preview
    # can show. Encapsulated Pixel Data are taken as whole here.
    whole: bool = True
    # Whether it is an RT Dose (face_review.is_rt_dose), which only a
    # dose-levels preview shows as it could show a face (D-017).
    dose: bool = False
    # Dose Grid Scaling, where a dose-levels preview can show its doses:
    # an RT Dose by its SOP Class, unsigned, not rescaled, and scaled by a
    # finite number above 0.
    dose_scale: float | None = None


@dataclasses.dataclass(frozen=True)
class PreviewSet:
    """The previews of a run, and the instances that could not be previewed.

    Attributes
    ----------
    previews : tuple of ~pymedphys._dicom.deidentify.qc_pack.Preview
        Each series' cine strip, then its projection and its surface render
        if it forms a volume, then the dose-levels render of each RT Dose
        grid in it, then the dose-levels map of each RT Dose plane in it in
        no volume, series in the order of their first run position; then each
        contour sheet, in run position order; then each high-risk instance,
        in run position order; then each frame of each instance that Clean
        Pixel Data cleaned, in run position and frame order. Named
        ``P-0001.png`` onwards in that order. A contour sheet shows its
        instance's frame 0, then the frames of each volume that it is
        drawn with, if any.
    not_previewed : tuple of ~pymedphys._dicom.deidentify.qc_pack.NotPreviewedEntry
        In run position order. An RT Dose that no dose-levels preview shows
        whole, whatever the cause, is listed as ``DOSE_LEVELS_NOT_SHOWN``,
        though its other previews are kept, unless another reason is listed
        first.
    contours_shown : frozenset of int
        The run positions of the files with contours that a contour sheet
        shows.
    pixels_shown : frozenset of int
        The run positions of the files with pixel data every frame of which
        a preview that could show a face draws, and that are not listed as
        not previewed, and whose native Pixel Data hold no more than their
        frames. A volume's projection and surface render draw each of its
        slices, by its maximum where slices are closer than their pixels. A
        contour sheet lists frames that it cannot show a face in, so its
        frames do not count. Only dose-levels previews count for an RT Dose,
        by :func:`~.face_review.is_rt_dose`: its cine strip is windowed to
        its highest doses, which can leave a low dose outlining the skin
        black, and an Otsu render of a series of its planes shows one level.
        Nor does a file of which a frame that a preview draws pads with more
        than one stored value, since every preview draws its padding as one
        black, or as no patient.
    """

    previews: tuple[Preview, ...]
    not_previewed: tuple[NotPreviewedEntry, ...]
    contours_shown: frozenset[int] = frozenset()
    pixels_shown: frozenset[int] = frozenset()


def previews_of(
    written: Mapping[int, bytes],
    high_risk: Collection[int],
    redactions: Mapping[int, tuple[bytes | None, RedactionEntry]] | None = None,
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

    Returns
    -------
    PreviewSet
    """
    redactions = {} if redactions is None else redactions
    instances: list[_Instance] = []
    refused: dict[int, NotPreviewedReason] = {}
    contoured: dict[int, qc_contours.Contours] = {}
    for position in sorted(written):
        found = _instance(position, written[position])
        if isinstance(found, _Instance):
            instances.append(found)
        elif isinstance(found, NotPreviewedReason):
            refused[position] = found
        elif found is not None:
            contoured[position] = found
        elif position in high_risk:
            refused[position] = NotPreviewedReason.NO_PIXEL_DATA
    # Each image is encoded as it is made, so that only its PNG is kept.
    images: list[_Encoded] = []
    decoded = _Decoder(refused)
    guides: dict[str, list[tuple[_Guided, str | None]]] = {
        frame: []
        for contours in contoured.values()
        for frame in contours.frames
        if frame is not None
    }
    for series in _series(instances):
        images.extend(_encoded(_series_images(series, decoded, guides)))
    for position, contours in sorted(contoured.items()):
        sheet = _contour_image(position, contours, guides)
        if sheet is None:
            refused[position] = NotPreviewedReason.CONTOURS_NOT_SHOWN
            continue
        images.extend(_encoded([sheet]))
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
    # instance must be among theirs; for an RT Dose, only dose levels do.
    listed = [(kind.value, frames) for kind, frames, _, _ in images]
    levels = {PreviewKind.SERIES_DOSE_LEVELS.value}
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
    pictured = pictured_frames(listed, refused)
    dosed = pictured_frames(listed, refused, levels)
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
            and (dosed if instance.dose else pictured).get(instance.position)
            == instance.frames
        ),
    )


# An image's kind, the frames it shows by run position and index, how many
# frames its series or instance has, and its PNG.
_Encoded = tuple[PreviewKind, tuple[tuple[int, int], ...], int, bytes]
# The surface of a volume that a contour sheet can be drawn with, and the
# frames that it shows.
_Guided = tuple[qc_contours.Guide, tuple[tuple[int, int], ...]]


def _encoded(images) -> Iterator[_Encoded]:
    """Encode each image as a PNG as it is made."""
    for kind, frames, total, image in images:
        yield kind, frames, total, png(image)


def _instance(
    position: int, data: bytes
) -> _Instance | NotPreviewedReason | qc_contours.Contours | None:
    """Read what a preview needs of a file, or why it cannot be previewed.

    A file without pixel data gives its contours, where it has any that a
    sheet can show, or ``CONTOURS_NOT_SHOWN`` where it has others, or
    ``None`` where it has none.
    """
    try:
        dataset = pydicom.dcmread(io.BytesIO(data))
    except Exception:  # pylint: disable = broad-exception-caught
        # Whatever pydicom raises, the reviewer is told, never the error.
        return NotPreviewedReason.UNREADABLE
    if any(keyword in dataset for keyword in _FLOAT_PIXEL_DATA):
        return NotPreviewedReason.UNSUPPORTED
    if "PixelData" not in dataset:
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
            plugin = DECODING_PLUGINS.get(syntax, "")
            if not plugin or not decoder_available(syntax):
                return NotPreviewedReason.COMPRESSED
        photometric = str(dataset.PhotometricInterpretation).strip()
        samples = int(dataset.SamplesPerPixel)
        allocated = int(dataset.BitsAllocated)
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
    if not colour and not (photometric in _MONOCHROME and samples == 1):
        return NotPreviewedReason.UNSUPPORTED
    if frames < 1 or rows < 1 or columns < 1:
        return NotPreviewedReason.UNREADABLE
    spacing = _spacing(dataset)
    uid = dataset.get("SeriesInstanceUID")
    scale = None if colour or rescale != (1.0, 0.0) else _dose_scale(dataset)
    whole = True
    if not plugin:
        try:
            expected = pydicom.pixels.utils.get_expected_length(dataset, "bytes")
            whole = len(dataset.PixelData) <= expected + 1
        except Exception:  # pylint: disable = broad-exception-caught
            whole = False
    return _Instance(
        position=position,
        data=data,
        plugin=plugin,
        series=str(uid) if uid else None,
        shape=(rows, columns),
        padding=None if colour else _padding(dataset),
        frames=frames,
        colour=colour,
        inverted=photometric == "MONOCHROME1",
        rescale=rescale,
        spacing=spacing,
        plane=_plane(dataset, spacing, (rows, columns)) if frames == 1 else None,
        number=number,
        modality=modality,
        grid=None
        if scale is None
        else _dose_grid(dataset, spacing, (rows, columns), frames, scale),
        frame=_uid(dataset, "FrameOfReferenceUID"),
        whole=whole,
        dose=is_rt_dose(dataset),
        dose_scale=scale,
    )


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
    orientation = _floats(dataset, "ImageOrientationPatient", 6)
    origin = _floats(dataset, "ImagePositionPatient", 3)
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


# The attributes by which stored values pad, and so are read as no patient.
_PADDING = ("PixelPaddingValue", "PixelPaddingRangeLimit")


def _dose_scale(dataset: pydicom.Dataset) -> float | None:
    """Dose Grid Scaling, where the data set is an RT Dose by its SOP Class
    whose stored values are unsigned, not padded, and scaled by a finite
    number above 0; otherwise None, as a signed grid can hold doses below 0,
    which no level shows, a padded one has stored values that are read as
    no dose, which no level shows either, and a grid without a scaling above
    0 has no dose to show."""
    try:
        sop_class = str(dataset.get("SOPClassUID") or "")
    except Exception:  # pylint: disable = broad-exception-caught
        sop_class = ""
    scaling = _number(dataset, "DoseGridScaling", float)
    if (
        sop_class != qc_surfaces.RT_DOSE_STORAGE
        or _number(dataset, "PixelRepresentation", int) != 0
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
) -> qc_surfaces.Grid | None:
    """The grid of an RT Dose instance of two or more frames, if it is rendered.

    Its axes must lie along the patient's, and its frames be evenly spaced.
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
        _roles(directions) is None
        or abs(offsets[0]) > _STACKING_TOLERANCE
        or not ((steps > 0).all() or (steps < 0).all())
        or np.ptp(steps) > _STACKING_TOLERANCE
    ):
        return None
    return qc_surfaces.grid(
        directions,
        offsets,
        plane.spacing,
        shape,
        qc_surfaces.Threshold.DOSE,
        scale,
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
        return self._shown(instance, pixels, NotPreviewedReason.UNREADABLE)

    def frames(
        self,
        instance: _Instance,
        indices: Sequence[int] | None = None,
        reason: NotPreviewedReason = NotPreviewedReason.UNREADABLE,
        received: bool = False,
    ) -> Iterator[np.ndarray]:
        """Yield an instance's frames, or those at ``indices``, in order, as
        :meth:`frame` gives them, reading its file once.

        Stops at a frame that cannot be decoded, recording ``reason``. The
        frames of a file as ``received``, which is not released, are not
        checked for padding of more than one value.
        """
        if instance.position in self._refused:
            return
        try:
            for pixels in pydicom.pixels.iter_pixels(
                io.BytesIO(instance.data),
                indices=indices,
                decoding_plugin=instance.plugin,
            ):
                shown = self._shown(instance, np.asarray(pixels), reason, received)
                if shown is None:
                    return
                yield shown
        except Exception:  # pylint: disable = broad-exception-caught
            self._refused.setdefault(instance.position, reason)

    def _shown(
        self,
        instance: _Instance,
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
        slope, intercept = instance.rescale
        shown = pixels.astype(np.float32) * np.float32(slope) + np.float32(intercept)
        if instance.padding is not None:
            low, high = instance.padding
            padded = (pixels >= low) & (pixels <= high)
            if low < high and not received and padded.any():
                values = pixels[padded]
                if values.min() != values.max():
                    self.mixed_padding.add(instance.position)
            shown[padded] = np.nan
        return shown


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
    volume = _volume(series)
    tiles: list[tuple[int, int, np.ndarray, _Instance]] = []
    surfaces = _surfaces(series, volume)
    # A volume too large for a surface render has no projection either, so
    # that no preview that could show a face draws its slices beyond its
    # cine strip, and their pixel data are held.
    projection = (
        _Projection(volume) if volume is not None and not surfaces[0][2].large else None
    )
    rendered = {
        frame for _, shown, surface in surfaces if not surface.large for frame in shown
    }
    # Each RT Dose plane in no volume, mapped by the levels of its dose.
    planes = {
        instance.position: instance
        for instance in series
        if volume is None and instance.frames == 1 and instance.dose_scale is not None
    }
    # Each slice's map is drawn as soon as it is decoded, so that only its
    # 8-bit map, or None, and not its pixels, is kept to the series' end.
    maps: list[tuple[_Instance, np.ndarray | None]] = []
    for instance in series:
        for frame in range(instance.frames):
            shown = (instance.position, frame) in chosen
            projected = projection is not None and not frame
            mapped = instance.position in planes
            if not (
                shown or projected or mapped or (instance.position, frame) in rendered
            ):
                continue
            pixels = decoder.frame(instance, frame)
            if pixels is None:
                break
            if shown:
                tiles.append(
                    (instance.position, frame, _fitted(pixels, instance), instance)
                )
            if projection is not None:
                projection.add(instance, pixels)
            for kind, each, surface in surfaces:
                if (instance.position, frame) in each:
                    # A series of RT Dose planes scales each by its own.
                    planed = (
                        kind is PreviewKind.SERIES_DOSE_LEVELS and volume is not None
                    )
                    surface.add(pixels, instance.dose_scale if planed else None)
            if mapped:
                maps.append((instance, _level_map(instance, pixels)))
            # Freed before the next frame is decoded, so no two are held.
            del pixels
    if tiles:
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
    if projection is not None:
        projected = projection.image()
        if projected is not None:
            yield projected
    frame = series[0].frame
    if (
        guides is not None
        and volume is not None
        and frame in guides
        and all(instance.frame == frame for instance in series)
    ):
        guide = _guide(series, surfaces[0][2])
        if guide is not None:
            guides[frame].append(((guide, surfaces[0][1]), series[0].series))
    for kind, shown, surface in surfaces:
        image = surface.image()
        if image is not None:
            yield kind, shown, len(shown), image
    for instance, level_map in maps:
        if level_map is not None:
            yield (
                PreviewKind.SERIES_DOSE_LEVELS,
                ((instance.position, 0),),
                1,
                level_map,
            )


def _level_map(instance: _Instance, pixels: np.ndarray) -> np.ndarray | None:
    """An RT Dose plane at full resolution, grey by the levels of its dose,
    or None if its scaling loses a dose (:func:`~.qc_surfaces.dose_values`)
    or it has more than :data:`~.qc_surfaces.MAXIMUM_DOSE_LEVELS` levels."""
    assert instance.dose_scale is not None
    values = qc_surfaces.dose_values(pixels, instance.dose_scale)
    if values is None:
        return None
    finite = values[np.isfinite(values)]
    positive = finite[finite > 0]
    levels = qc_surfaces.dose_levels(
        float(finite.max()) if finite.size else -math.inf,
        float(positive.min()) if positive.size else math.inf,
    )
    if len(levels) > qc_surfaces.MAXIMUM_DOSE_LEVELS:
        return None
    return qc_surfaces.level_bands(values, levels)


def _surfaces(
    series: list[_Instance], volume: _Volume | None
) -> list[tuple[PreviewKind, tuple[tuple[int, int], ...], qc_surfaces.Surface]]:
    """The surface renders of a series, each with its kind and the frames
    that it shows.

    The volume's first, if the series forms one, then each RT Dose grid's.
    A CT series' surface is at a fixed level; a series of RT Dose planes,
    each of whose doses a dose-levels preview can show, is shown at each of
    its dose levels; and any other's surface is by Otsu's threshold.
    """
    surfaces = []
    if volume is not None:
        kind = PreviewKind.SERIES_SURFACE
        if all(instance.modality == "CT" for instance in series):
            threshold = qc_surfaces.Threshold.CT
        elif all(instance.dose_scale is not None for instance in series):
            threshold = qc_surfaces.Threshold.DOSE
            kind = PreviewKind.SERIES_DOSE_LEVELS
        else:
            threshold = qc_surfaces.Threshold.OTSU
        grid = qc_surfaces.grid(
            volume.directions, volume.positions, volume.spacing, volume.shape, threshold
        )
        shown = tuple((instance.position, 0) for instance in series)
        surfaces.append((kind, shown, qc_surfaces.Surface(grid)))
    for instance in series:
        if instance.grid is not None:
            shown = tuple(
                (instance.position, frame) for frame in range(instance.frames)
            )
            surfaces.append(
                (
                    PreviewKind.SERIES_DOSE_LEVELS,
                    shown,
                    qc_surfaces.Surface(instance.grid),
                )
            )
    return surfaces


def _guide(
    series: list[_Instance], surface: qc_surfaces.Surface
) -> qc_contours.Guide | None:
    """The surface of a volume, placed in the patient's coordinates.

    None if a slice is missing.
    """
    inside = surface.mask()
    if inside is None:
        return None
    planes = [instance.plane for instance in series]
    first = planes[0]
    assert first is not None
    normal = np.cross(first.row, first.column)
    axes = [int(np.argmax(np.abs(d))) for d in (normal, first.column, first.row)]
    along = (
        np.array([plane.origin[axes[0]] for plane in planes if plane is not None]),
        first.origin[axes[1]]
        + first.column[axes[1]] * first.spacing[0] * np.arange(first.shape[0]),
        first.origin[axes[2]]
        + first.row[axes[2]] * first.spacing[1] * np.arange(first.shape[1]),
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
    return images


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
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return -0.5, 0.5
    low, high = (float(value) for value in np.percentile(finite, _PERCENTILES))
    # A uniform image is shown mid-grey, so that it stands out from the
    # black around the tiles.
    return (low, high) if high > low else (low - 0.5, low + 0.5)


def _full_range(values: np.ndarray) -> tuple[float, float]:
    """The window from the smallest value to the largest, under which no
    value is clipped."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return -0.5, 0.5
    low, high = float(finite.min()), float(finite.max())
    return (low, high) if high > low else (low - 0.5, low + 0.5)


def _grey(image: np.ndarray, window: tuple[float, float], inverted: bool) -> np.ndarray:
    low, high = window
    scaled = np.clip((image - low) / (high - low), 0.0, 1.0)
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
    """A series that forms a volume, and the roles of its three axes.

    Axis 0 runs through the slices along the normal; axis 1 down the rows,
    along the plane's column direction; axis 2 along the columns, along its
    row direction.
    """

    positions: tuple[float, ...]  # along the normal, ascending, one per slice
    directions: tuple[np.ndarray, np.ndarray, np.ndarray]
    spacing: tuple[float, float]  # between rows, then between columns
    shape: tuple[int, int]
    anterior: int  # the axis along the patient's anterior-posterior direction
    vertical: int  # along superior-inferior
    horizontal: int  # along left-right


def _volume(series: list[_Instance]) -> _Volume | None:
    if len(series) < VOLUME_SLICES or any(instance.colour for instance in series):
        return None
    normal = _common_normal(series)
    if normal is None:
        return None
    planes = [instance.plane for instance in series]
    first = planes[0]
    assert first is not None
    if any(
        plane is None
        or plane.shape != first.shape
        or not np.allclose(plane.spacing, first.spacing)
        for plane in planes
    ):
        return None
    origins = np.array([plane.origin for plane in planes if plane])
    positions = _stacked(origins, normal)
    if positions is None:
        return None
    directions = (normal, np.array(first.column), np.array(first.row))
    roles = _roles(directions)
    if roles is None:
        return None
    anterior, vertical, horizontal = roles
    return _Volume(
        positions,
        directions,
        first.spacing,
        first.shape,
        anterior=anterior,
        vertical=vertical,
        horizontal=horizontal,
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
        self._slices: list[np.ndarray] = []
        self._maximum: np.ndarray | None = None
        self._order: list[int] = []
        self._inverted: list[bool] = []

    def add(self, instance: _Instance, frame: np.ndarray) -> None:
        """Add the next slice, in series order."""
        self._order.append(instance.position)
        self._inverted.append(instance.inverted)
        anterior = self._volume.anterior
        if anterior == 0:
            # fmax ignores padding, which is NaN, unless every value is.
            self._maximum = (
                frame.copy() if self._maximum is None else np.fmax(self._maximum, frame)
            )
        else:
            self._slices.append(np.fmax.reduce(frame, axis=anterior - 1))

    def image(self):
        volume = self._volume
        if len(self._order) != len(volume.positions):
            return None  # a slice could not be decoded
        coordinates = {
            0: np.array(volume.positions) - volume.positions[0],
            1: np.arange(volume.shape[0]) * volume.spacing[0],
            2: np.arange(volume.shape[1]) * volume.spacing[1],
        }
        if volume.anterior == 0:
            assert self._maximum is not None
            image, axes = self._maximum, (1, 2)
        else:
            image = np.stack(self._slices)
            axes = (0, 3 - volume.anterior)
        if axes.index(volume.vertical) == 1:
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
        frames = tuple((position, 0) for position in self._order)
        return PreviewKind.SERIES_MIP, frames, len(volume.positions), shown


def _nearest(coordinates: np.ndarray, wanted: np.ndarray) -> np.ndarray:
    """The index of the coordinate nearest each wanted one; coordinates ascend."""
    if len(coordinates) == 1:
        return np.zeros(len(wanted), np.intp)
    right = np.clip(np.searchsorted(coordinates, wanted), 1, len(coordinates) - 1)
    left = right - 1
    closer_left = (wanted - coordinates[left]) <= (coordinates[right] - wanted)
    return np.where(closer_left, left, right)


def png(image: np.ndarray) -> bytes:
    """Return an 8-bit greyscale or RGB image as a PNG file.

    Parameters
    ----------
    image : numpy.ndarray
        uint8, of shape (rows, columns) or (rows, columns, 3).

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
    if image.dtype != np.uint8 or not (
        image.ndim == 2 or (image.ndim == 3 and image.shape[2] == 3)
    ):
        raise ValueError("a PNG needs a uint8 image of grey or RGB samples")
    rows, columns = image.shape[:2]
    if rows < 1 or columns < 1:
        raise ValueError("a PNG needs at least one pixel")
    colour_type = 0 if image.ndim == 2 else 2
    header = struct.pack(">IIBBBBB", columns, rows, 8, colour_type, 0, 0, 0)
    raw = np.ascontiguousarray(image).reshape(rows, -1)
    filtered = np.concatenate([np.zeros((rows, 1), np.uint8), raw], axis=1)
    return (
        _PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(filtered.tobytes(), 6))
        + _chunk(b"IEND", b"")
    )


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )
