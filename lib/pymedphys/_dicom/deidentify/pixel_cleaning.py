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

Only native Pixel Data in whole bytes is cleaned: Bits Allocated 8, 16, or
32, with High Bit one less than Bits Stored, little endian, as every native
transfer syntax in scope is, and MONOCHROME1, MONOCHROME2, or RGB with 8
bits. The new value is written in place of the old, byte for byte, so the
transfer syntax, the frames' layout, and every byte outside the regions are
kept. Bits above Bits Stored could hold an overlay (PS3.3 Section C.9.2 before
2004) or anything else that a viewer does not show, so Pixel Data whose
unused bits hold more than the value's sign is not cleaned: each stored word
must have those bits all zero, or all one where the value is negative. A
value written into a region has them as its sign gives them.

:func:`redaction_problem` then checks the file written: pydicom must read
the same stored values from it as from the source outside the regions, and
the fill inside them, and every byte outside the regions must be
the source's. An instance that fails is sequestered, as one is whose Pixel
Data cannot be cleaned (:class:`PixelDataRefused`).
"""

from __future__ import annotations

import dataclasses
import types
from collections.abc import Mapping, Sequence
from typing import Protocol

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from .diagnostics import redacted_diagnostics
from .file_layout import ElementPath
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
class Redaction:
    """What :func:`black_out` did to an instance's Pixel Data.

    Attributes
    ----------
    layout : Layout
    regions : tuple of FrameRegions
        Each frame with a region, by index from 0.
    value : bytes
        The new value field of Pixel Data.
    """

    layout: Layout
    regions: tuple[FrameRegions, ...]
    value: bytes = dataclasses.field(repr=False)

    @property
    def reason(self) -> PixelDataReason:
        """Why the instance is held for review."""
        if self.regions:
            return PixelDataReason.TEXT_BLACKED_OUT
        return PixelDataReason.NO_TEXT_FOUND


def black_out(
    source: SourceEvidence, dataset: pydicom.Dataset, finder: TextFinder
) -> Redaction | None:
    """Return the instance's Pixel Data with the finder's regions blacked out.

    Parameters
    ----------
    source : SourceEvidence
    dataset : pydicom.Dataset
        The source's data set, as :meth:`SourceEvidence.dataset` reads it.
    finder : TextFinder

    Returns
    -------
    Redaction or None
        None where the instance has no top-level Pixel Data, Float Pixel
        Data, or Double Float Pixel Data, so that the option has nothing to
        clean.

    Raises
    ------
    PixelDataRefused
        With :attr:`~.reasons.TransformReason.COMPRESSED_PIXEL_DATA` for
        Pixel Data in an encapsulated transfer syntax, and
        :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` for float
        pixel data, or native Pixel Data that cannot be read as frames.
    """
    if any(path in source for path in FLOAT_PIXEL_DATA):
        raise PixelDataRefused(TransformReason.UNCLEANABLE_PIXEL_DATA)
    if PIXEL_DATA not in source:
        return None
    if source.transfer_syntax not in NATIVE_TRANSFER_SYNTAXES:
        raise PixelDataRefused(TransformReason.COMPRESSED_PIXEL_DATA)
    layout = layout_of(dataset)
    field = source.value_field(PIXEL_DATA)
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
    for index in range(layout.frames):
        frame = _frame(layout, _stored_values(layout, stored[index]))
        boxes = tuple(sorted(set(_checked(finder.find(frame), layout))))
        if not boxes:
            continue
        fill = layout.fill(frame)
        for box in boxes:
            for sample, value in enumerate(fill):
                written[layout.word_index(index, box, sample)] = layout.word_of(value)
        regions.append(FrameRegions(index, boxes, fill))
    size = layout.words * layout.dtype.itemsize
    value = written.tobytes() + field[size:]
    return Redaction(layout, tuple(regions), value)


def layout_of(dataset: pydicom.Dataset) -> Layout:
    """Return how native Pixel Data holds its frames.

    Raises
    ------
    PixelDataRefused
        With :attr:`~.reasons.TransformReason.UNCLEANABLE_PIXEL_DATA` where
        an attribute that says so cannot be read or describes a layout that
        is not cleaned.
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
    monochrome = samples == 1 and photometric in _MONOCHROME
    rgb = samples == 3 and photometric == _RGB and allocated == 8 and not representation
    if not (monochrome or rgb):
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
    written value field outside the regions must be the source's.
    """
    if PIXEL_DATA not in output or output.transfer_syntax != source.transfer_syntax:
        return True
    before, after = source.value_field(PIXEL_DATA), output.value_field(PIXEL_DATA)
    if after != redaction.value or len(after) != len(before):
        return True
    layout = redaction.layout
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
    size = expected.nbytes
    if expected.tobytes() != after[:size] or after[size:] != before[size:]:
        return True
    return not _reads_as_planned(source, output, redaction)


def _reads_as_planned(
    source: SourceEvidence, output: SourceEvidence, redaction: Redaction
) -> bool:
    """Whether pydicom reads the planned stored values from the output."""
    layout = redaction.layout
    planned = {regions.frame: regions for regions in redaction.regions}
    try:
        with redacted_diagnostics():
            pairs = zip(
                pydicom.pixels.iter_pixels(source.dataset()),
                pydicom.pixels.iter_pixels(output.dataset()),
                strict=True,
            )
            for index, (before, after) in enumerate(pairs):
                inside = np.zeros((layout.rows, layout.columns), dtype=bool)
                regions = planned.get(index)
                for box in () if regions is None else regions.boxes:
                    inside[box.top : box.bottom, box.left : box.right] = True
                if before.shape != after.shape:
                    return False
                if not np.array_equal(before[~inside], after[~inside]):
                    return False
                if regions is not None and not np.all(
                    after[inside] == np.array(regions.value, dtype=after.dtype)
                ):
                    return False
    # pydicom raises many types for pixel data it cannot read, and a message
    # can quote a value.
    except Exception:  # pylint: disable = broad-exception-caught
        return False
    return True


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
