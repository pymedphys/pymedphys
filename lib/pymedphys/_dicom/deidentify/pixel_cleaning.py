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

"""Black out burned-in text in native Pixel Data, under Clean Pixel Data (D-037).

The Clean Pixel Data Option (PS3.15 E.3.1) removes burned-in information
from the Pixel Data (7FE0,0010) of the top-level data set; icons, in nested
items, are removed by the Basic Profile. Its Note 2 allows "the most
conservative approach of removing any and all burned in text", so
:func:`black_out` asks a :class:`TextFinder`, such as
:class:`~pymedphys._dicom.deidentify.text_detection.TextDetector`, for the
regions of text in each frame, whatever they say, and sets every pixel of
each region to one stored value, the frame's fill: its smallest stored
value for MONOCHROME2, its largest for MONOCHROME1, and zero for RGB. The
fill erases the text's pattern, but how bright it is displayed depends on
the Modality and VOI LUT attributes that are kept, which can invert it, so
it is not always black. The finder is an aid to review, not a guarantee, so
every instance whose pixel data the option cleans is held for review,
whether or not text was found (:class:`~.reasons.PixelDataReason`).

Only Pixel Data in whole bytes is cleaned: Bits Allocated 8, 16, or 32,
with High Bit one less than Bits Stored, little endian, as every native
transfer syntax in scope is, and MONOCHROME1, MONOCHROME2, or RGB with 8
bits. In native Pixel Data, the new value is written in place of the old,
byte for byte, so the transfer syntax, the frames' layout, and every byte
outside the regions are kept. Bits above Bits Stored could hold an overlay
(PS3.3 Section C.9.2 before 2004) or anything else that a viewer does not
show, so Pixel Data whose unused bits hold more than the value's sign is not
cleaned: each stored word must have those bits all zero, or all one where
the value is negative. A value written into a region has them as its sign
gives them.

Compressed Pixel Data, in a transfer syntax that encapsulates it, is
decoded first, every frame, by :func:`.pixel_decoding.decoded_frames`,
which decodes in a child process the frames of the plugins that run native
code; colour of 8 bits as YBR_FULL, YBR_FULL_422, YBR_ICT, or YBR_RCT is
decoded to RGB. The text finder searches the decoded frames, and where a
region or mask is written, the new value is the decoded frames with it,
written uncompressed, in Explicit VR Little Endian (:attr:`Redaction.transfer_syntax`),
since writing into a codestream would mean encoding it again. Where nothing
is written, the compressed Pixel Data is kept as it would be without the
option. The SHA-256 of the decoded frames (:attr:`Redaction.decoded_sha256`)
binds a reviewer's verdict to the pixels that the reviewer saw, since
another build of a decoder can decode the same lossy codestream otherwise
(D-048).

Under Clean Recognizable Visual Features, :func:`black_out` also writes
the masks that a :class:`Defacer` gives each frame, such as the face block
of a head CT (:mod:`~pymedphys._dicom.deidentify.face_blocks`), each pixel
of a mask set to its one stored value after any region of text is filled,
so that one new value of Pixel Data holds both.

:func:`redaction_problem` then checks the file written: pydicom must read
the same stored values from it as from the source outside the regions and
masks, the fill inside each region outside the masks, and each mask's value
inside it, and every byte outside them must be the source's, or, for
compressed Pixel Data, the decoded frames'. An instance that fails is
sequestered, as one is whose Pixel Data cannot be cleaned
(:class:`PixelDataRefused`).
"""

from __future__ import annotations

import dataclasses
import hashlib
import types
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Protocol

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from .diagnostics import redacted_diagnostics
from .file_layout import ElementPath
from .pixel_decoding import FramesRefused, decoded_frames
from .reasons import PixelDataReason, TransformReason
from .source import NATIVE_TRANSFER_SYNTAXES, SourceEvidence
from .text_detection import TextBox

PIXEL_DATA = ElementPath((), "(7FE0,0010)")
# Top-level pixel data that the option cannot clean.
FLOAT_PIXEL_DATA = (
    ElementPath((), "(7FE0,0008)"),  # Float Pixel Data
    ElementPath((), "(7FE0,0009)"),  # Double Float Pixel Data
)
_BITS_ALLOCATED = (8, 16, 32)
_MONOCHROME = ("MONOCHROME1", "MONOCHROME2")
_RGB = "RGB"
# The colour of compressed Pixel Data that decodes to RGB: by pydicom from
# YBR_FULL and YBR_FULL_422, and by the JPEG 2000 decoder from YBR_ICT and
# YBR_RCT, whose multiple component transformation it reverses.
_DECODED_TO_RGB = (_RGB, "YBR_FULL", "YBR_FULL_422", "YBR_ICT", "YBR_RCT")
EXPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2.1"
"""The transfer syntax of cleaned compressed Pixel Data, written uncompressed."""


class TextFinder(Protocol):
    """Finds the regions of text in one frame, as
    :meth:`~pymedphys._dicom.deidentify.text_detection.TextDetector.find`
    does, and describes what decides them, for the method digest."""

    @property
    def method(self) -> Mapping[str, object]:
        """What decides the regions, as
        :attr:`~pymedphys._dicom.deidentify.text_detection.TextDetector.method`
        gives it: a mapping that is not empty, whose values are text,
        integers, floats, bytes, or UUIDs, in mappings, sequences, and sets."""

    def find(self, frame: np.ndarray) -> Sequence[TextBox]:
        """Return the regions of text in a frame of stored values: rows by
        columns, or rows by columns by 3 for RGB."""


class Defacer(Protocol):
    """Gives the pixels of each frame to set to one stored value, as
    :class:`~pymedphys._dicom.deidentify.face_blocks.CtDefacer` does."""

    def mask(self, frame: int, stored: np.ndarray) -> FrameMask | None:
        """Return the mask of one frame, given its stored values, rows by
        columns, or None where it has none."""


def finder_description(finder: TextFinder) -> Mapping[str, object]:
    """Return what decides a finder's regions, as the method digest takes it.

    That is the finder's class, by module and qualified name, so that another
    finder that gives the text detector's description is not taken for it,
    and a copy of the finder's own description of its method, so that a
    change to the finder afterwards changes neither the digest that the
    markers record nor the one that the release report records.

    Parameters
    ----------
    finder : TextFinder

    Returns
    -------
    Mapping of str to object
        ``{"finder": "<module>.<qualified name>", "method": <description>}``,
        read-only, with each mapping, sequence, and set in the description
        copied.

    Raises
    ------
    TypeError
        If the finder does not describe its method as a mapping, or describes
        it as an empty one.
    """
    method = getattr(finder, "method", None)
    if not isinstance(method, Mapping) or not method:
        raise TypeError(
            "a text finder must describe its method as a mapping that is not empty"
        )
    kind = type(finder)
    return types.MappingProxyType(
        {"finder": f"{kind.__module__}.{kind.__qualname__}", "method": _frozen(method)}
    )


def _frozen(value: object) -> object:
    """Return a read-only copy of mappings, sequences, and sets, at any depth.

    Other values are kept as they are, for the method digest to accept or
    refuse.
    """
    if isinstance(value, Mapping):
        return types.MappingProxyType(
            {key: _frozen(item) for key, item in value.items()}
        )
    if isinstance(value, (tuple, list)):
        return tuple(_frozen(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_frozen(item) for item in value)
    return value


class PixelDataRefused(Exception):
    """Pixel Data that the option cannot clean, with a value-free reason."""

    def __init__(self, reason: TransformReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class PixelsNotReviewed(Exception):
    """Compressed Pixel Data whose frames do not decode to the pixels that a
    reviewer saw, so that the reviewer's regions are not applied to them."""


@dataclasses.dataclass(frozen=True)
class _Review:
    """What a review records of compressed Pixel Data: the SHA-256 of its
    decoded frames, or None where it records none."""

    decoded_sha256: bytes | None


@dataclasses.dataclass(frozen=True)
class Layout:
    """How native Pixel Data holds its frames, from the attributes that say so.

    Attributes
    ----------
    frames, rows, columns, samples : int
        Number of Frames (1 where absent), Rows, Columns, and Samples per
        Pixel.
    bits_allocated, bits_stored : int
    signed : bool
        Whether Pixel Representation is 1, two's complement.
    photometric : str
        Photometric Interpretation.
    planar : bool
        Whether Planar Configuration is 1, each colour plane in turn.
    """

    frames: int
    rows: int
    columns: int
    samples: int
    bits_allocated: int
    bits_stored: int
    signed: bool
    photometric: str
    planar: bool

    @property
    def words(self) -> int:
        """How many stored words the frames hold."""
        return self.frames * self.rows * self.columns * self.samples

    @property
    def dtype(self) -> np.dtype:
        """The little-endian unsigned word of one sample."""
        return np.dtype(f"<u{self.bits_allocated // 8}")

    def word_of(self, value: int) -> int:
        """Return the stored word of a value: in two's complement where
        signed, so that the bits above Bits Stored give its sign."""
        return value % (1 << self.bits_allocated)

    def fill(self, frame: np.ndarray) -> tuple[int, ...]:
        """Return the stored value that fills a frame's regions, once per
        sample: its smallest for MONOCHROME2, its largest for MONOCHROME1,
        and zero for RGB."""
        if self.photometric == _RGB:
            return (0, 0, 0)
        value = frame.min() if self.photometric == "MONOCHROME2" else frame.max()
        return (int(value),)

    def word_index(self, frame: int, box: TextBox, sample: int) -> tuple:
        """Return the index, into the words shaped by :meth:`shaped`, of one
        sample of a box in a frame."""
        rows = slice(box.top, box.bottom)
        columns = slice(box.left, box.right)
        if self.planar:
            return (frame, sample, rows, columns)
        return (frame, rows, columns, sample)

    def shaped(self, words: np.ndarray) -> np.ndarray:
        """Return the frames' words as frames, then samples or rows, as stored."""
        if self.planar:
            shape = (self.frames, self.samples, self.rows, self.columns)
        else:
            shape = (self.frames, self.rows, self.columns, self.samples)
        return words.reshape(shape)


@dataclasses.dataclass(frozen=True)
class FrameRegions:
    """The regions blacked out in one frame, and the value written there.

    ``value`` is a stored pixel value, never reported or logged.
    """

    frame: int
    boxes: tuple[TextBox, ...]
    value: tuple[int, ...] = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True)
class FrameMask:
    """The pixels of one frame set to one stored value.

    ``mask`` is of bool, rows by columns, and ``value`` a stored pixel
    value; neither is reported or logged.
    """

    frame: int
    mask: np.ndarray = dataclasses.field(repr=False, compare=False)
    value: int = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True)
class Redaction:
    """What :func:`black_out` did to an instance's Pixel Data.

    Attributes
    ----------
    layout : Layout
        For compressed Pixel Data, of the decoded frames: RGB for colour,
        with the samples of each pixel together.
    regions : tuple of FrameRegions
        Each frame with a region, by index from 0.
    value : bytes
        The new value field of Pixel Data: for compressed Pixel Data, the
        decoded frames with the regions and masks, padded to an even length.
    masks : tuple of FrameMask
        Each frame with a mask that a :class:`Defacer` gave, by index from
        0, written after the regions.
    decoded : bytes or None
        For compressed Pixel Data, its frames as decoded, in the layout
        that ``value`` has, without padding; None for native Pixel Data.
    """

    layout: Layout
    regions: tuple[FrameRegions, ...]
    value: bytes = dataclasses.field(repr=False)
    masks: tuple[FrameMask, ...] = ()
    decoded: bytes | None = dataclasses.field(default=None, repr=False)

    @property
    def changed(self) -> bool:
        """Whether any pixel was set: a region or a mask."""
        return bool(self.regions or self.masks)

    @property
    def transfer_syntax(self) -> str | None:
        """The transfer syntax in which ``value`` is written where it is not
        the source's: Explicit VR Little Endian for compressed Pixel Data
        with a region or mask, and otherwise None."""
        if self.decoded is None or not self.changed:
            return None
        return EXPLICIT_VR_LITTLE_ENDIAN

    @property
    def decoded_sha256(self) -> bytes | None:
        """The SHA-256 of the decoded frames, or None for native Pixel Data."""
        return None if self.decoded is None else hashlib.sha256(self.decoded).digest()

    @property
    def reason(self) -> PixelDataReason:
        """Why the instance is held for review."""
        if self.regions:
            return PixelDataReason.TEXT_BLACKED_OUT
        return PixelDataReason.NO_TEXT_FOUND


def black_out(
    source: SourceEvidence,
    dataset: pydicom.Dataset,
    finder: TextFinder | None,
    defacer: Defacer | None = None,
) -> Redaction | None:
    """Return the instance's Pixel Data with the finder's regions blacked out,
    and the defacer's masks written.

    Parameters
    ----------
    source : SourceEvidence
    dataset : pydicom.Dataset
        The source's data set, as :meth:`SourceEvidence.dataset` reads it.
    finder : TextFinder or None
        None where no text is looked for.
    defacer : Defacer, optional

    Returns
    -------
    Redaction or None
        None where the instance has no top-level Pixel Data, Float Pixel
        Data, or Double Float Pixel Data, so that the option has nothing to
        clean.

    Raises
    ------
    PixelDataRefused
        With :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` for
        float pixel data, or Pixel Data that cannot be read as frames, or
        the reason of :class:`~.pixel_decoding.FramesRefused` for
        compressed Pixel Data whose frames cannot be decoded for cleaning.
    """
    return _blacked_out(
        source,
        dataset,
        None if finder is None else lambda _, frame: finder.find(frame),
        defacer,
    )


def black_out_reviewed(
    source: SourceEvidence,
    dataset: pydicom.Dataset,
    regions: Sequence[tuple[int, Sequence[TextBox]]],
    defacer: Defacer | None = None,
    *,
    decoded_sha256: bytes | None = None,
) -> Redaction | None:
    """Return the instance's Pixel Data with a reviewer's regions blacked out,
    and the defacer's masks written.

    As :func:`black_out`, but each frame's regions are those given, by frame
    index from 0, rather than a finder's, and a frame not given has none.
    A reviewed region is never clipped: one that goes past the frame's rows
    or columns refuses the instance, since a mistyped or transposed region
    would otherwise leave the text it was meant to cover.

    Parameters
    ----------
    source, dataset, defacer
        As for :func:`black_out`.
    regions : sequence of (int, sequence of TextBox)
        The reviewer's regions, by frame index from 0.
    decoded_sha256 : bytes, optional
        For compressed Pixel Data, the SHA-256 of its decoded frames as the
        reviewed QC pack records it (:attr:`Redaction.decoded_sha256`),
        which the frames decoded now must have. Ignored for native Pixel
        Data, whose source file's SHA-256 binds the review.

    Raises
    ------
    PixelDataRefused
        For any reason that :func:`black_out` gives, and with
        :attr:`~.reasons.TransformReason.REDACTION_MISMATCH` where a frame
        given is not one that the Pixel Data hold, or a region goes past
        the frame, so that the review does not fit them.
    PixelsNotReviewed
        Where compressed Pixel Data's frames decode to pixels whose SHA-256
        is not ``decoded_sha256``, or none is given, before any region is
        applied.
    """
    by_frame = {index: tuple(boxes) for index, boxes in regions}

    def reviewed(index: int, frame: np.ndarray) -> Sequence[TextBox]:
        rows, columns = frame.shape[:2]
        boxes = by_frame.get(index, ())
        if any(box.bottom > rows or box.right > columns for box in boxes):
            raise PixelDataRefused(TransformReason.REDACTION_MISMATCH)
        return boxes

    redaction = _blacked_out(
        source, dataset, reviewed, defacer, review=_Review(decoded_sha256)
    )
    if redaction is not None and any(
        not 0 <= index < redaction.layout.frames for index in by_frame
    ):
        raise PixelDataRefused(TransformReason.REDACTION_MISMATCH)
    return redaction


def _blacked_out(
    source: SourceEvidence,
    dataset: pydicom.Dataset,
    boxes_of: Callable[[int, np.ndarray], Sequence[TextBox]] | None,
    defacer: Defacer | None,
    review: _Review | None = None,
) -> Redaction | None:
    """Return the instance's Pixel Data with the regions that ``boxes_of``
    gives each frame, by its index and stored values, blacked out, none
    where it is None, and the defacer's masks written.

    Given a ``review``, compressed Pixel Data whose decoded frames have
    another SHA-256 than it records raises :class:`PixelsNotReviewed`."""
    if any(path in source for path in FLOAT_PIXEL_DATA):
        raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA)
    if PIXEL_DATA not in source:
        return None
    decoded = None
    if source.transfer_syntax in NATIVE_TRANSFER_SYNTAXES:
        layout = layout_of(dataset)
        field = source.value_field(PIXEL_DATA)
    else:
        layout, attributes = _decoded_layout(dataset)
        try:
            field = decoded = decoded_frames(
                source, attributes, layout.frames, layout.photometric
            )
        except FramesRefused as refused:
            raise PixelDataRefused(refused.reason) from None
        if review is not None and review.decoded_sha256 != (
            hashlib.sha256(decoded).digest()
        ):
            raise PixelsNotReviewed()
    words = _words(layout, field)
    if words is None:
        raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA)
    # One frame at a time, so that a long multi-frame image needs no more
    # than a frame's stored values beside its words.
    stored = layout.shaped(words)
    if not all(_plain_unused_bits(layout, frame) for frame in stored):
        raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA)
    written = stored.copy()
    regions = []
    masks = []
    for index in range(layout.frames):
        frame = _frame(layout, _stored_values(layout, stored[index]))
        boxes = (
            ()
            if boxes_of is None
            else tuple(sorted(set(_checked(boxes_of(index, frame), layout))))
        )
        if boxes:
            fill = layout.fill(frame)
            for box in boxes:
                for sample, value in enumerate(fill):
                    written[layout.word_index(index, box, sample)] = layout.word_of(
                        value
                    )
            regions.append(FrameRegions(index, boxes, fill))
        mask = None if defacer is None else defacer.mask(index, frame)
        if mask is not None:
            if (
                mask.frame != index
                or layout.samples != 1
                or np.shape(mask.mask) != (layout.rows, layout.columns)
                or not _storable(layout, mask.value)
            ):
                raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA)
            mask = dataclasses.replace(mask, mask=np.asarray(mask.mask, dtype=bool))
            written[index, mask.mask, 0] = layout.word_of(mask.value)
            masks.append(mask)
    size = layout.words * layout.dtype.itemsize
    # Native Pixel Data keeps any padding after its frames; decoded frames
    # are padded to an even length (PS3.5 Section 8.1.1).
    value = written.tobytes() + (field[size:] if decoded is None else bytes(size % 2))
    return Redaction(layout, tuple(regions), value, tuple(masks), decoded)


def layout_of(dataset: pydicom.Dataset) -> Layout:
    """Return how native Pixel Data holds its frames.

    Raises
    ------
    PixelDataRefused
        With :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` where
        an attribute that says so cannot be read or describes a layout that
        is not cleaned.
    """
    layout = _read_layout(dataset)
    monochrome = layout.samples == 1 and layout.photometric in _MONOCHROME
    rgb = (
        layout.samples == 3
        and layout.photometric == _RGB
        and layout.bits_allocated == 8
        and not layout.signed
    )
    if not (monochrome or rgb):
        raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA)
    return layout


def _decoded_layout(
    dataset: pydicom.Dataset,
) -> tuple[Layout, Mapping[str, int | str]]:
    """Return how compressed Pixel Data's frames are held once decoded, and
    the attributes that describe a frame to its decoder.

    Decoded frames have the samples of each pixel together, and colour of 8
    bits, unsigned, in any of :data:`_DECODED_TO_RGB` decodes to RGB.

    Raises
    ------
    PixelDataRefused
        As :func:`layout_of` does.
    """
    layout = _read_layout(dataset)
    monochrome = layout.samples == 1 and layout.photometric in _MONOCHROME
    colour = (
        layout.samples == 3
        and layout.photometric in _DECODED_TO_RGB
        and layout.bits_allocated == 8
        and not layout.signed
    )
    if not (monochrome or colour):
        raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA)
    attributes: dict[str, int | str] = {
        "Rows": layout.rows,
        "Columns": layout.columns,
        "SamplesPerPixel": layout.samples,
        "BitsAllocated": layout.bits_allocated,
        "BitsStored": layout.bits_stored,
        "HighBit": layout.bits_stored - 1,
        "PixelRepresentation": int(layout.signed),
        "PhotometricInterpretation": layout.photometric,
    }
    if colour:
        attributes["PlanarConfiguration"] = int(layout.planar)
        layout = dataclasses.replace(layout, photometric=_RGB, planar=False)
    return layout, attributes


def _read_layout(dataset: pydicom.Dataset) -> Layout:
    """Return the layout that the attributes give, of whole bytes, for any
    photometric interpretation.

    Raises
    ------
    PixelDataRefused
        As :func:`layout_of` does, other than for the photometric
        interpretation.
    """
    uncleanable = PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA)
    try:
        with redacted_diagnostics():
            frames = _integer(dataset, "NumberOfFrames", default=1)
            rows, columns, samples = (
                _integer(dataset, keyword)
                for keyword in ("Rows", "Columns", "SamplesPerPixel")
            )
            allocated, stored, high, representation = (
                _integer(dataset, keyword)
                for keyword in (
                    "BitsAllocated",
                    "BitsStored",
                    "HighBit",
                    "PixelRepresentation",
                )
            )
            photometric = dataset["PhotometricInterpretation"].value
            if not isinstance(photometric, str):
                raise ValueError("not one code string")
            planar = _integer(dataset, "PlanarConfiguration") if samples == 3 else 0
    # pydicom raises many types for a value it cannot convert, and a message
    # can quote the value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise uncleanable from None
    if not (
        min(frames, rows, columns) > 0
        and allocated in _BITS_ALLOCATED
        and 0 < stored <= allocated
        and high == stored - 1
        and representation in (0, 1)
        and planar in (0, 1)
    ):
        raise uncleanable
    return Layout(
        frames=frames,
        rows=rows,
        columns=columns,
        samples=samples,
        bits_allocated=allocated,
        bits_stored=stored,
        signed=bool(representation),
        photometric=photometric,
        planar=bool(planar),
    )


def redaction_problem(
    source: SourceEvidence, output: SourceEvidence, redaction: Redaction
) -> bool:
    """Return whether the written Pixel Data differs from the redaction planned.

    pydicom must read, frame by frame, the source's stored values outside
    the regions and the fill inside them, and every byte of the
    written value field outside the regions must be the source's. For
    compressed Pixel Data, the source's are the decoded frames', and the
    output must be in :attr:`Redaction.transfer_syntax`, with no byte after
    them but one of padding, of zero.
    """
    syntax = redaction.transfer_syntax or source.transfer_syntax
    if PIXEL_DATA not in output or output.transfer_syntax != syntax:
        return True
    decoded = redaction.decoded if redaction.transfer_syntax is not None else None
    if redaction.decoded is not None and decoded is None:
        # Compressed Pixel Data with nothing written is not cleaned here.
        return True
    before = source.value_field(PIXEL_DATA) if decoded is None else decoded
    after = output.value_field(PIXEL_DATA)
    layout = redaction.layout
    size = layout.words * layout.dtype.itemsize
    length = len(before) if decoded is None else size + size % 2
    if after != redaction.value or len(after) != length:
        return True
    words = _words(layout, before)
    if words is None:
        return True
    expected = layout.shaped(words.copy())
    for regions in redaction.regions:
        for box in regions.boxes:
            for sample, value in enumerate(regions.value):
                expected[layout.word_index(regions.frame, box, sample)] = (
                    layout.word_of(value)
                )
    for mask in redaction.masks:
        expected[mask.frame, mask.mask, 0] = layout.word_of(mask.value)
    tail = before[size:] if decoded is None else bytes(size % 2)
    if expected.tobytes() != after[:size] or after[size:] != tail:
        return True
    return not _reads_as_planned(source, output, redaction)


def _source_frames(source: SourceEvidence, redaction: Redaction) -> Iterator:
    """Yield the source's frames as pydicom reads native Pixel Data: from the
    source itself where it is native, and from the decoded frames where it
    is compressed, which are never decoded again in this process."""
    if redaction.transfer_syntax is None:
        yield from pydicom.pixels.iter_pixels(source.dataset())
        return
    layout = redaction.layout
    words = _words(layout, redaction.decoded or b"")
    if words is None:
        raise ValueError("the decoded frames do not fit their layout")
    for frame in layout.shaped(words):
        yield _frame(layout, _stored_values(layout, frame))


def _reads_as_planned(
    source: SourceEvidence, output: SourceEvidence, redaction: Redaction
) -> bool:
    """Whether pydicom reads the planned stored values from the output."""
    layout = redaction.layout
    planned = {regions.frame: regions for regions in redaction.regions}
    masks = {mask.frame: mask for mask in redaction.masks}
    try:
        with redacted_diagnostics():
            pairs = zip(
                _source_frames(source, redaction),
                pydicom.pixels.iter_pixels(output.dataset()),
                strict=True,
            )
            for index, (before, after) in enumerate(pairs):
                inside = np.zeros((layout.rows, layout.columns), dtype=bool)
                regions = planned.get(index)
                for box in () if regions is None else regions.boxes:
                    inside[box.top : box.bottom, box.left : box.right] = True
                mask = masks.get(index)
                masked = (
                    np.zeros_like(inside) if mask is None else np.asarray(mask.mask)
                )
                if before.shape != after.shape:
                    return False
                changed = inside | masked
                if not np.array_equal(before[~changed], after[~changed]):
                    return False
                filled = inside & ~masked
                if regions is not None and not np.all(
                    after[filled] == np.array(regions.value, dtype=after.dtype)
                ):
                    return False
                if mask is not None and not np.all(after[masked] == mask.value):
                    return False
    # pydicom raises many types for pixel data it cannot read, and a message
    # can quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        return False
    return True


def stored_range(layout: Layout) -> tuple[int, int]:
    """The least and greatest stored value that the layout can hold."""
    if layout.signed:
        return -(1 << (layout.bits_stored - 1)), (1 << (layout.bits_stored - 1)) - 1
    return 0, (1 << layout.bits_stored) - 1


def _storable(layout: Layout, value: object) -> bool:
    """Whether ``value`` is an integer that the layout can store."""
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        return False
    low, high = stored_range(layout)
    return low <= int(value) <= high


def _integer(dataset: pydicom.Dataset, keyword: str, default: int | None = None) -> int:
    if keyword not in dataset and default is not None:
        return default
    value = dataset[keyword].value
    # pydicom reads US as int and IS as a subclass of it; anything else, such
    # as several values or none, is not one integer.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("not one integer")
    return int(value)


def _words(layout: Layout, field: bytes) -> np.ndarray | None:
    """Return the frames' stored words, or None if the value field does not
    hold them with at most one byte of padding."""
    size = layout.words * layout.dtype.itemsize
    if not size <= len(field) <= size + 1:
        return None
    return np.frombuffer(field[:size], dtype=layout.dtype)


def _plain_unused_bits(layout: Layout, words: np.ndarray) -> bool:
    """Whether every word's bits above Bits Stored hold no more than its sign."""
    unused = layout.bits_allocated - layout.bits_stored
    if not unused:
        return True
    high = words >> layout.bits_stored
    if not layout.signed:
        return not high.any()
    negative = (words >> (layout.bits_stored - 1)) & 1
    ones = (1 << unused) - 1
    return bool(np.all((high == 0) | ((high == ones) & (negative == 1))))


def _stored_values(layout: Layout, words: np.ndarray) -> np.ndarray:
    """Return the stored values of the words, as signed integers."""
    values = (words & ((1 << layout.bits_stored) - 1)).astype(np.int64)
    if layout.signed:
        sign = 1 << (layout.bits_stored - 1)
        values = (values ^ sign) - sign
    return values


def _frame(layout: Layout, frame: np.ndarray) -> np.ndarray:
    """Return one frame's stored values, as :meth:`Layout.shaped` gives them,
    rows by columns, by 3 for RGB."""
    if layout.planar:
        frame = np.moveaxis(frame, 0, -1)
    return frame[..., 0] if layout.samples == 1 else frame


def _checked(boxes: Sequence[TextBox], layout: Layout) -> list[TextBox]:
    """Return the finder's boxes, each clipped to the frame.

    Raises
    ------
    TypeError
        If a box is not a :class:`~.text_detection.TextBox`.
    """
    clipped = []
    for box in boxes:
        if not isinstance(box, TextBox):
            raise TypeError("a text finder must give TextBox objects")
        bottom, right = min(box.bottom, layout.rows), min(box.right, layout.columns)
        if box.top < bottom and box.left < right:
            clipped.append(TextBox(box.top, box.left, bottom, right))
    return clipped
