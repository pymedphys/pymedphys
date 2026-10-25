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

"""Segmentations in the Frame of Reference of a defaced CT series, cleaned
of the face in its block.

Under the Clean Recognizable Visual Features Option, a Segmentation, of
Segmentation Storage or Label Map Segmentation Storage, whose masks lie in
the frame of a CT series that a run defaces
(:mod:`~pymedphys._dicom.deidentify.face_blocks`) can trace the face that
the CT no longer shows, as a mask of the body or the skin does. A run
therefore cleans it in the same region as the CT's, the face block less the
brain that defacing keeps, on the block of the frame's one defaced series
(:class:`~.dose_defacing.DoseBlock`), as
:class:`~.region_defacing.PetDefacer` sets a PET image to zero activity
there (:class:`SegmentationDefacer`). A pixel is in the region where its
centre is in the block, and is kept where the nearest pixel of the nearest
slice that the block reaches, within half the slices' spacing, is one that
defacing keeps.

Each pixel in the region that lies in a segment is written as the
segmentation's background, so that it lies in none: 0 for a Segmentation
Type of BINARY, whose 1 marks a segment's presence and 0 its absence, and
FRACTIONAL, whose 0 is a probability or occupancy of zero (PS3.3
C.8.20.2.3). A LABELMAP's pixel value is a Segment Number, and only a Pixel
Padding Value marks one as background (PS3.3 C.8.20.2.4), so a label map is
written with that value, which must be one value that its pixels can hold,
without Pixel Padding Range Limit; a label map without it has no background
to write, and is refused. Any other pixel is written as received, so a
segmentation that the region does not reach, or whose masks there lie only
in the kept brain, is written unchanged.

Each frame is placed by its own Plane Position (Patient), Plane Orientation
(Patient), and Pixel Measures functional groups, each from either the
Per-frame Functional Groups Sequence item of the frame or the Shared
Functional Groups Sequence, never both, since PS3.3 C.7.6.16.1.1 lets a
functional group be in only one of them and gives neither precedence, and
each sequence of one item:
Image Position (Patient), Image Orientation (Patient) of two orthogonal unit
vectors within :data:`~.dose_defacing._UNIT`, and Pixel Spacing, finite and
positive, every corner of the frame within :data:`~.dose_defacing._FARTHEST`,
as :class:`~.dose_defacing.RtDoseDefacer` checks a dose grid. A
segmentation of native Pixel Data, one sample, MONOCHROME2, and unsigned
pixels, of 1 bit for BINARY, 8 for FRACTIONAL, and 8 or 16 for LABELMAP, as
PS3.3 C.8.20.2 enumerates them, packed eight to a byte for BINARY with each
frame filling whole bytes
(:func:`~pymedphys._dicom.deidentify.pixel_cleaning.black_out`), is cleaned
so. Any other, such as one that a Derivation Image functional group places
on its source images instead, one of TILED_FULL frames, compressed, or of
PALETTE COLOR, is refused, and stays held as an instance in a defaced frame
(:attr:`~.reasons.VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME`).
"""

from __future__ import annotations

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from .diagnostics import redacted_diagnostics
from .dose_defacing import DoseBlock, _check_directions, _check_reach, _numbers
from .face_blocks import _padding
from .pixel_cleaning import FrameMask, PixelDataRefused, layout_of, stored_range
from .reasons import TransformReason, VisualFeaturesReason
from .source import NATIVE_TRANSFER_SYNTAXES

# The IOD of Segmentation Storage and Label Map Segmentation Storage, as
# Table B.5-1 names it without "IOD".
SEGMENTATION = "Segmentation"
# The Bits Allocated that PS3.3 C.8.20.2 enumerates for each Segmentation
# Type, with Bits Stored the same.
_BITS = {"BINARY": (1,), "FRACTIONAL": (8,), "LABELMAP": (8, 16)}
_LABELMAP = "LABELMAP"


class SegmentationDefacer:
    """Gives the pixels of each frame of a segmentation in the face block,
    less what defacing keeps, that lie in a segment, to write as its
    background, for
    :func:`~pymedphys._dicom.deidentify.pixel_cleaning.black_out`.

    Parameters
    ----------
    region : DoseBlock
        The block of the segmentation's Frame of Reference.
    dataset : pydicom.Dataset
        The segmentation's data set.

    Raises
    ------
    PixelDataRefused
        With :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` where
        the segmentation is not one that the module cleans.
    """

    def __init__(self, region: DoseBlock, dataset: pydicom.Dataset) -> None:
        try:
            if str(dataset.file_meta.TransferSyntaxUID) not in NATIVE_TRANSFER_SYNTAXES:
                raise ValueError("compressed")
            layout = layout_of(dataset, packed=True)
            with redacted_diagnostics():
                kind = str(dataset.SegmentationType).strip().upper()
                tiled = str(dataset.get("DimensionOrganizationType") or "")
            if tiled.strip().upper() == "TILED_FULL":
                raise ValueError("tiled")
            if (
                layout.samples != 1
                or layout.photometric != "MONOCHROME2"
                or layout.signed
                or layout.bits_allocated not in _BITS.get(kind, ())
                or layout.bits_stored != layout.bits_allocated
            ):
                raise ValueError("not a segmentation that is cleaned")
            background = 0
            if kind == _LABELMAP:
                padding = _padding(dataset, layout)
                if padding is None or "PixelPaddingRangeLimit" in dataset:
                    raise ValueError("no background")
                background = padding[0]
                low, high = stored_range(layout)
                if not low <= background <= high:
                    raise ValueError("background not stored")
            planes = tuple(
                _plane(dataset, layout.frames, frame) for frame in range(layout.frames)
            )
            for position, orientation, spacing in planes:
                _check_reach((position,), orientation, spacing, layout)
        # Whatever the data set raises refuses the segmentation, without its
        # message, which could quote a value.
        except Exception:  # pylint: disable = broad-exception-caught
            raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA) from None
        self._region = region
        self._planes = planes
        self._shape = (layout.rows, layout.columns)
        self._background = background

    def __repr__(self) -> str:
        return "SegmentationDefacer()"

    @property
    def held(self) -> VisualFeaturesReason | None:
        """None, since a segmentation is cleaned in the block whatever its
        segments there, as the CT is written as air."""
        return None

    def mask(self, frame: int, stored: np.ndarray) -> FrameMask | None:
        """Return the pixels of one frame to write as the background, as the
        module describes, or None where the frame has none: the frame's
        pixels in a segment, so that a segmentation that reaches the face
        is one given a mask."""
        position, orientation, spacing = self._planes[frame]
        inside = self._region.block.slice_mask(
            position, orientation, spacing, self._shape
        )
        if inside.any():
            rows, columns = np.nonzero(inside)
            points = (
                np.asarray(position)
                + columns[:, np.newaxis] * spacing[1] * np.asarray(orientation[:3])
                + rows[:, np.newaxis] * spacing[0] * np.asarray(orientation[3:])
            )
            inside[rows, columns] = ~self._region.kept(points)
        inside &= np.asarray(stored) != self._background
        if not inside.any():
            return None
        return FrameMask(frame, inside, self._background)


def _plane(
    dataset: pydicom.Dataset, frames: int, frame: int
) -> tuple[tuple[float, float, float], tuple[float, ...], tuple[float, float]]:
    """Return one frame's Image Position (Patient), Image Orientation
    (Patient), and Pixel Spacing, from its functional groups, of a
    segmentation of ``frames`` frames.

    Raises
    ------
    ValueError
        Where any is absent, or not finite numbers, the orientation is not
        two orthogonal unit vectors, or the spacing is not positive.
    """
    with redacted_diagnostics():
        x, y, z = _numbers(
            _group(dataset, frames, frame, "PlanePositionSequence"),
            "ImagePositionPatient",
            3,
        )
        orientation = _numbers(
            _group(dataset, frames, frame, "PlaneOrientationSequence"),
            "ImageOrientationPatient",
            6,
        )
        rows, columns = _numbers(
            _group(dataset, frames, frame, "PixelMeasuresSequence"), "PixelSpacing", 2
        )
    _check_directions(orientation)
    if not min(rows, columns) > 0:
        raise ValueError("not a spacing")
    return (x, y, z), orientation, (rows, columns)


def _group(
    dataset: pydicom.Dataset, frames: int, frame: int, keyword: str
) -> pydicom.Dataset:
    """Return the one item of a functional group's sequence for a frame,
    from either the frame's item of the Per-frame Functional Groups Sequence
    or the Shared Functional Groups Sequence.

    A group in both is refused rather than one taken over the other, since
    PS3.3 C.7.6.16.1.1 lets a group be in only one and gives neither
    precedence. A segmentation without the Per-frame Functional Groups
    Sequence, which PS3.3 A.51.5 permits where it would be empty, is refused
    too, which only holds it.

    Raises
    ------
    ValueError
        Where the Per-frame Functional Groups Sequence does not have one item
        for each of the ``frames`` frames, the Shared Functional Groups
        Sequence has more than one, or the group is not in exactly one of
        them, in one item.
    """
    each = dataset.get("PerFrameFunctionalGroupsSequence") or []
    shared = dataset.get("SharedFunctionalGroupsSequence") or []
    if len(each) != frames or len(shared) > 1:
        raise ValueError("not one item for each frame")
    found = [
        groups[keyword].value for groups in (each[frame], *shared) if keyword in groups
    ]
    if len(found) != 1:
        raise ValueError("not one functional group")
    (items,) = found
    if len(items) != 1:
        raise ValueError("not one item")
    return items[0]
