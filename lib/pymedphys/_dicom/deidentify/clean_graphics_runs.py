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

"""The runs and expectations of the check of the Clean Graphics Option on
public human DICOM (:mod:`.clean_graphics_check`).

:func:`run_instance` gives an instance to de-identification transforms as a
run does, under Retain Longitudinal Temporal Information with Modified
Dates, alone and with Clean Graphics, and gives each file that a transform
writes to a release gate, with the instance's own evidence as its
subject's. The Basic Profile alone would sequester a Presentation State for
its creation date (D-020). A Presentation State with annotations is run
without a reviewed annotations list (D-062), and with lists built in memory
from its own annotations, as a reviewer would decide on them (:data:`RUNS`):
an empty list; each annotation kept; each annotation kept and each set of
annotations that a display shows together kept too, by the digests of the
sets that a first pass holds, as a reviewer takes them from the QC pack;
each annotation removed; each annotation that holds a text object removed,
the rest and their sets kept; and, where keeping them all holds an
annotation for echoing an identifier, those removed, the rest and their
sets kept. An image, and a Presentation State without annotations, are run
without a list alone, and their two written files are compared. An image
with an overlay in unused bits of Pixel Data, an overlay group without
Overlay Data, is also run with Clean Graphics and Clean Pixel Data, whose
text finder the caller gives, since only Clean Pixel Data can release a
Secondary Capture (D-060).

For each run, :func:`instance_summary` counts the outcome and its reasons,
as the release report names them, what is decided for each annotation and
each set, and what the written file holds. :func:`evaluate` tests the runs
against what Table E.1-1 and the design give the option
(:data:`EXPECTATIONS`): Graphic Annotation Sequence takes D without a list,
which sequesters a Presentation State, since the Type 1 sequence has no
dummy value (D-021); with a list, each annotation is kept as received but
for its UIDs, removed, or held, as the list decides, and kept annotations
shown together need a decision on them together; curve groups and
overlay groups that hold Overlay Data are removed whole, as under the Basic
Profile (D-020); the bit plane of an overlay in unused bits of Pixel Data
is cleared, so that each stored value holds only its sign above High Bit
(:func:`unused_bits`), and its group is removed, in the write that blacks
out text, which holds the image for review, with its Pixel Data described
as received and each stored value as received outside the regions in which
text was found in its frame (:func:`stored_values_changed`); an overlay
group whose only attribute is Overlay Activation Layer (60xx,1001), with
which a Presentation State shows an overlay of the image that it
references, places no overlay in the state, so it is kept and the state is
released; and every file written under the option claims it (D-041). A run
that raises is counted by the exception's type and place, never its
message.

The annotations' digests, which the reviewed annotations list keeps
confidential, the Overlay Activation Layers, Pixel Data, the regions in
which text was found, and the written files stay in memory: no summary
holds them.
"""

from __future__ import annotations

import collections
import dataclasses
import io
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import policy
from .face_validation import crash_site
from .graphic_annotations import (
    AnnotationMaterial,
    ImageReference,
    annotation_images,
    enclosing_images,
    shown_together,
)
from .instance_transform import InstanceTransform, ReleaseGate
from .keys import DeidKey
from .midi_benchmark_errors import uid_name
from .midi_benchmark_graphics import graphics_of
from .pixel_cleaning import TextFinder
from .reasons import PixelDataReason, TransformReason
from .references import InstanceRecord
from .release_report import held_for_review, sequestration_reason
from .reviewed_annotations import (
    Held,
    Outcome,
    Review,
    ReviewedAnnotation,
    ReviewedAnnotations,
    annotation_digest,
)
from .run_results import HoldForReview, Release, Sequestered, Transformed
from .source import read_source
from .text_detection import TextBox

GRAYSCALE_SOFTCOPY_PRESENTATION_STATE = "1.2.840.10008.5.1.4.1.1.11.1"
PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE = "1.2.840.10008.5.1.4.1.1.11.3"
PRESENTATION_STATES = frozenset(
    {GRAYSCALE_SOFTCOPY_PRESENTATION_STATE, PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE}
)
# The five Secondary Capture SOP Classes, Secondary Capture Image Storage
# and its four multi-frame forms, each sequestered without Clean Pixel Data
# (D-060).
SECONDARY_CAPTURE = "1.2.840.10008.5.1.4.1.1.7"
SECONDARY_CAPTURES = frozenset(
    SECONDARY_CAPTURE + suffix for suffix in ("", ".1", ".2", ".3", ".4")
)
CLEAN_GRAPHICS_CODE = "113103"

# The runs, by the names that the summary gives them, and what each is.
RUNS: Mapping[str, str] = {
    "modified_dates": "Modified Dates alone, without a list",
    "no_list": "Clean Graphics, without a list",
    "empty_list": "Clean Graphics, an empty list",
    "each_kept": "Clean Graphics, each annotation kept",
    "each_and_sets_kept": "Clean Graphics, each annotation and each set kept",
    "each_removed": "Clean Graphics, each annotation removed",
    "text_removed": (
        "Clean Graphics, each annotation with a text object removed, the rest "
        "and their sets kept"
    ),
    "echoes_removed": (
        "Clean Graphics, each annotation held for echoing an identifier "
        "removed, the rest and their sets kept"
    ),
    "with_pixel_data": "Clean Graphics and Clean Pixel Data, without a list",
}
# The runs without a list, which are the only runs of an image and of a
# Presentation State without annotations.
WITHOUT_A_LIST = ("modified_dates", "no_list")
# The runs of an image whose overlay lies in unused bits of Pixel Data: those
# without a list, and one with Clean Pixel Data too, which cleans its pixels.
WITH_PIXEL_DATA = (*WITHOUT_A_LIST, "with_pixel_data")
# The reason that the walker gives for sequestering a Presentation State
# whose Graphic Annotation Sequence takes D, as the release report names it.
NO_DUMMY_VALUE = "walker: no-dummy-value at (0070,0001), D"
# The reason that the transform gives for sequestering a Secondary Capture
# whose Pixel Data no option cleans, as the release report names it.
UNCLEANED_SECONDARY_CAPTURE = (
    f"transform: {TransformReason.SECONDARY_CAPTURE_NOT_CLEANED.value}"
)
# The tags in which a file written with Clean Graphics may differ from one
# written without it: De-identification Method and its Code Sequence.
MARKERS = ("(0012,0063)", "(0012,0064)")
# What no file written under the option may hold: three of its four rows of
# Table E.1-1, as midi_benchmark_graphics names them, and an overlay that may
# lie in Pixel Data.
REMOVED_GRAPHICS = frozenset(
    {"curve_data", "overlay_data", "overlay_comments", "overlay_in_pixel_data"}
)

_KEY = DeidKey(bytes(range(32)))
_BASELINE = (policy.MODIFIED_DATES,)
_OPTION = (policy.MODIFIED_DATES, policy.CLEAN_GRAPHICS)
_PIXEL_OPTIONS = (policy.MODIFIED_DATES, policy.CLEAN_GRAPHICS, policy.CLEAN_PIXEL_DATA)
_GRAPHIC_ANNOTATION_SEQUENCE = 0x00700001
_METHOD_CODES = 0x00120064
_PIXEL_DATA = 0x7FE00010
# The first of the repeating groups of curves, 50xx, and of overlays, 60xx.
_CURVE_GROUPS = 0x5000
_OVERLAY_GROUPS = 0x6000
# Overlay Activation Layer (60xx,1001), the only attribute of a softcopy
# Presentation State's Overlay Activation Module (PS3.3 C.11.7).
_OVERLAY_ACTIVATION_LAYER = 0x1001
# A first pass, then a second with the decisions on the sets that it held.
_PASSES = 2
# Why a kept annotation can be held for itself, whatever the list decides on
# the annotations shown with it: for its text, or for its drawing.
_HELD_FOR_ITSELF = frozenset({Held.ECHOES_IDENTIFIER, Held.NOT_DRAWN})
_HELD_CODES = frozenset(
    f"annotations: {reason.value}"
    for reason in (Held.NOT_REVIEWED_TOGETHER, *_HELD_FOR_ITSELF)
)
# The graphics, as midi_benchmark_graphics names them, of which an image in
# the check holds one or both: those that the Basic Profile removes by their
# groups.
_HELD_GROUPS = frozenset({"curve_data", "overlay_data"})
# Why Clean Pixel Data holds an image that it cleans, as the release report
# names it: whether its detector found text or not, review looks for text
# that it missed (D-037).
_PIXEL_DATA_CODES = frozenset(
    f"pixel-data: {reason.value}" for reason in PixelDataReason
)
# Implicit and Explicit VR Little Endian: the transfer syntaxes whose Pixel
# Data is read here, as stored words.
_NATIVE = frozenset({"1.2.840.10008.1.2", "1.2.840.10008.1.2.1"})
# The attributes that say how Pixel Data holds its stored values, each with
# the value that it takes where it is absent, or None where it must be
# present; a written file must describe its Pixel Data as its source does.
_PIXEL_DESCRIPTION: tuple[tuple[str, int | None], ...] = (
    ("NumberOfFrames", 1),
    ("Rows", None),
    ("Columns", None),
    ("SamplesPerPixel", 1),
    ("PlanarConfiguration", 0),
    ("BitsAllocated", None),
    ("BitsStored", None),
    ("HighBit", None),
    ("PixelRepresentation", 0),
)


@dataclasses.dataclass(frozen=True)
class _Annotations:
    """A Presentation State's annotations, as the engine reads them.

    Their digests are what a reviewed annotations list decides by, and stay
    in memory: no summary holds them.
    """

    digests: tuple[str, ...]
    with_text: tuple[bool, ...]
    images: tuple[tuple[ImageReference, ...] | None, ...]

    def sets(self, shown: Sequence[int]) -> tuple[tuple[int, ...], ...]:
        """Each set of two or more of the annotations ``shown`` that a
        display shows together, as the engine decides on them: all of them
        where any one's images are not known."""
        shown = list(shown)
        found = shown_together([self.images[index] for index in shown])
        groups = (tuple(range(len(shown))),) if found is None else found
        return tuple(
            tuple(shown[place] for place in each) for each in groups if len(each) > 1
        )


@dataclasses.dataclass(frozen=True)
class _Written:
    """What a transform wrote, in memory: the digests of the annotations
    that its file holds, in order, and its Overlay Activation Layers never
    leave the check."""

    data: bytes
    digests: tuple[str, ...]
    text_objects: int
    graphic_objects: int
    graphics: frozenset[str]
    curve_groups: int
    overlay_groups: int
    unused_bits: int | None
    nested_graphics: int
    claims_clean_graphics: bool
    activation_layers: tuple[pydicom.DataElement, ...]
    # Of a run with Clean Pixel Data: how many regions of text the finder
    # found in all frames, and how many stored values the file holds
    # otherwise than its source outside the regions of their own frame, as
    # :func:`stored_values_changed` counts them.
    text_regions: int | None = None
    changed_outside_text_regions: int | None = None


class _Recorded:
    """A text finder that keeps, in memory, the regions of text that the
    finder that it is given finds in each frame, in the order in which the
    frames are given to it, so that the stored values of a written file can
    be compared with its source's outside each frame's own regions; no
    region leaves the check."""

    def __init__(self, finder: TextFinder):
        self._finder = finder
        self.frames: list[tuple[TextBox, ...]] = []

    @property
    def method(self) -> Mapping[str, object]:
        """The given finder's method, so that the method digest is its."""
        return self._finder.method

    def find(self, frame: np.ndarray) -> Sequence[TextBox]:
        found = tuple(self._finder.find(frame))
        self.frames.append(found)
        return found


@dataclasses.dataclass
class _Ran:
    """One run of one instance."""

    outcome: str
    reasons: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    passes: int = 0
    decisions: collections.Counter[str] | None = None
    annotations: dict[int, ReviewedAnnotation] = dataclasses.field(default_factory=dict)
    sets: list[ReviewedAnnotation] = dataclasses.field(default_factory=list)
    written: _Written | None = None

    def survivors(self, count: int) -> list[int] | None:
        """The annotations, of ``count``, that the run did not remove, or
        None where it did not decide on each of them."""
        if sorted(self.annotations) != list(range(count)):
            return None
        return [
            index
            for index in range(count)
            if self.annotations[index].outcome is not Outcome.REMOVED
        ]

    def held_for_itself(self) -> frozenset[int]:
        return frozenset(
            index
            for index, result in self.annotations.items()
            if result.held_because in _HELD_FOR_ITSELF
        )

    def kept_as_received(self, source: _Annotations) -> int:
        """How many kept annotations the written file holds as received but
        for their UIDs, by their digests, which leave out UIDs."""
        survivors = self.survivors(len(source.digests))
        written = self.written
        if survivors is None or written is None:
            return 0
        if len(written.digests) != len(survivors):
            return 0
        return sum(
            1
            for place, index in enumerate(survivors)
            if self.annotations[index].outcome is Outcome.KEPT
            and written.digests[place] == source.digests[index]
        )


@dataclasses.dataclass
class InstanceRuns:
    """An instance's runs, in memory, and what it holds, by counts.

    Attributes
    ----------
    label : str
        Its name in the summary, which names no file.
    sop_class : str
        Its SOP Class UID.
    holds : dict
        Counts of the graphics that it holds, and no value.
    annotations : _Annotations or None
        A Presentation State's annotations; None for an image.
    runs : dict of str to _Ran
        Each of its runs, by the name that :data:`RUNS` gives it.
    crashed : str or None
        Where reading it raised, by the exception's type and place, if it
        did.
    activation_layers : tuple of pydicom.DataElement
        The Overlay Activation Layer (60xx,1001) of each of its overlay
        groups that holds no other attribute, as :func:`_activation_layers`
        reads them; they stay in memory.
    """

    label: str
    sop_class: str
    holds: dict[str, Any]
    annotations: _Annotations | None
    runs: dict[str, _Ran]
    crashed: str | None = None
    activation_layers: tuple[pydicom.DataElement, ...] = ()

    @property
    def presentation_state(self) -> bool:
        """Whether it is a softcopy Presentation State."""
        return self.sop_class in PRESENTATION_STATES

    @property
    def embedded(self) -> bool:
        """Whether it is an image with an overlay in unused bits of Pixel
        Data: an overlay group without Overlay Data, as
        :func:`~.midi_benchmark_graphics.graphics_of` finds it."""
        return not self.presentation_state and "overlay_in_pixel_data" in (
            self.holds.get("graphics", ())
        )


def run_instance(
    label: str,
    sop_class: str,
    data: bytes,
    finder: Callable[[], TextFinder] | None = None,
) -> InstanceRuns:
    """Run one instance, a Presentation State or an image, as the module
    describes. ``finder`` gives the text finder of the run with Clean Pixel
    Data, which only an image with an overlay in unused bits of Pixel Data
    takes."""
    try:
        dataset = pydicom.dcmread(io.BytesIO(data))
        annotations = _annotations(data) if sop_class in PRESENTATION_STATES else None
        layers = _activation_layers(dataset)
        holds = _holds(dataset, annotations, layers)
    # Anything that reading the instance raises is counted, by where; its
    # message, which could quote a value, is dropped.
    except Exception as error:  # pylint: disable = broad-exception-caught
        return InstanceRuns(label, sop_class, {}, None, {}, crashed=crash_site(error))
    ran = InstanceRuns(
        label, sop_class, holds, annotations, {}, activation_layers=layers
    )
    if annotations is None or not annotations.digests:
        for name in WITH_PIXEL_DATA if ran.embedded else WITHOUT_A_LIST:
            ran.runs[name] = _run(data, name, None, None, finder)
        return ran
    count = len(annotations.digests)
    plans: list[tuple[str, dict[int, Review] | None]] = [
        ("modified_dates", None),
        ("no_list", None),
        ("empty_list", {}),
        ("each_kept", dict.fromkeys(range(count), Review.KEEP)),
        ("each_and_sets_kept", dict.fromkeys(range(count), Review.KEEP)),
        ("each_removed", dict.fromkeys(range(count), Review.REMOVE)),
        (
            "text_removed",
            {
                index: Review.REMOVE if text else Review.KEEP
                for index, text in enumerate(annotations.with_text)
            },
        ),
    ]
    for name, decisions in plans:
        ran.runs[name] = _run(data, name, annotations, decisions)
    echoes = {
        index
        for index, result in ran.runs["each_and_sets_kept"].annotations.items()
        if result.held_because is Held.ECHOES_IDENTIFIER
    }
    if echoes:
        decisions = {
            index: Review.REMOVE if index in echoes else Review.KEEP
            for index in range(count)
        }
        ran.runs["echoes_removed"] = _run(
            data, "echoes_removed", annotations, decisions
        )
    return ran


def _annotations(data: bytes) -> _Annotations:
    """A Presentation State's annotations, read as the transform reads them."""
    dataset = read_source(data).dataset()
    element = dataset.get(_GRAPHIC_ANNOTATION_SEQUENCE)
    items = list(element.value) if element is not None and element.value else []
    enclosing = enclosing_images(dataset)
    return _Annotations(
        tuple(annotation_digest(item) for item in items),
        tuple(bool(item.get("TextObjectSequence")) for item in items),
        tuple(annotation_images(item, enclosing) for item in items),
    )


def _activation_layers(dataset: pydicom.Dataset) -> tuple[pydicom.DataElement, ...]:
    """The Overlay Activation Layer (60xx,1001) of each overlay group that
    holds no other attribute but its group length, in the order of the data
    set. With such a group, a Presentation State shows an overlay of the
    image that it references, and places no overlay in itself."""
    groups: dict[int, set[int]] = {}
    for tag in dataset.keys():
        if 0x6000 <= tag.group <= 0x601E and tag.group % 2 == 0 and tag.element:
            groups.setdefault(tag.group, set()).add(tag.element)
    return tuple(
        dataset[group << 16 | _OVERLAY_ACTIVATION_LAYER]
        for group, elements in groups.items()
        if elements == {_OVERLAY_ACTIVATION_LAYER}
    )


def _holds(
    dataset: pydicom.Dataset,
    annotations: _Annotations | None,
    layers: Sequence[pydicom.DataElement],
) -> dict[str, Any]:
    """Counts of the graphics that an instance holds, and of a Presentation
    State's overlay groups that hold only Overlay Activation Layer, and no
    value."""
    holds: dict[str, Any] = {
        "graphics": sorted(graphics_of(dataset)),
        "curve_groups": _groups(dataset, _CURVE_GROUPS),
        "overlay_groups": _groups(dataset, _OVERLAY_GROUPS),
    }
    unused = unused_bits(dataset)
    if unused is not None:
        holds["unused_bits"] = unused
    if annotations is None:
        return holds
    element = dataset.get(_GRAPHIC_ANNOTATION_SEQUENCE)
    items = list(element.value) if element is not None and element.value else []
    sets = annotations.sets(range(len(annotations.digests)))
    holds.update(
        {
            "graphic_annotations": len(items),
            "with_text_objects": sum(annotations.with_text),
            "text_objects": _objects(items, "TextObjectSequence"),
            "graphic_objects": _objects(items, "GraphicObjectSequence"),
            "compound_graphics": _objects(items, "CompoundGraphicSequence"),
            "sets_shown_together": len(sets),
            "set_sizes": sorted(len(each) for each in sets),
            "activation_only_overlay_groups": len(layers),
        }
    )
    return holds


def _objects(items: Iterable[pydicom.Dataset], keyword: str) -> int:
    return sum(len(item.get(keyword) or ()) for item in items)


def unused_bits(dataset: pydicom.Dataset) -> int | None:
    """How many stored values of a data set's Pixel Data hold more than
    their sign in the bits above High Bit, as an overlay in unused bits of
    Pixel Data does; or None where it has no Pixel Data that is native and
    little endian, in words of 8, 16, or 32 bits.

    The words are read as stored, never through pydicom's pixel handlers,
    which may mask the bits above High Bit. Each unused bit of a value holds
    its sign where Pixel Representation is 1, and zero otherwise, as Clean
    Graphics clears an overlay's bit plane (D-041).
    """
    meta = getattr(dataset, "file_meta", None)
    syntax = None if meta is None else meta.get("TransferSyntaxUID")
    element = dataset.get(_PIXEL_DATA)
    if syntax not in _NATIVE or element is None or element.value is None:
        return None
    try:
        allocated = int(dataset.BitsAllocated)
        high = int(dataset.HighBit)
        signed = int(dataset.get("PixelRepresentation", 0)) == 1
    except (AttributeError, TypeError, ValueError):
        return None
    if allocated not in (8, 16, 32) or not 0 <= high < allocated:
        return None
    width = allocated // 8
    data = bytes(element.value)
    words = np.frombuffer(data, dtype=f"<u{width}", count=len(data) // width)
    if high == allocated - 1:
        return 0
    above = words >> (high + 1)
    unused = (1 << (allocated - high - 1)) - 1
    expected = ((words >> high) & 1) * unused if signed else np.zeros_like(above)
    return int(np.count_nonzero(above != expected))


def stored_values_changed(
    source: pydicom.Dataset,
    written: pydicom.Dataset,
    regions: Sequence[Iterable[TextBox]],
) -> int | None:
    """How many stored values a written file holds otherwise than its source
    outside the regions of text of their frame, in any frame or sample; or
    None where either has no Pixel Data that is native and little endian, in
    words of 8, 16, or 32 bits, where the written file describes its Pixel
    Data otherwise than its source does, or where ``regions`` does not give
    the regions of each frame.

    Only the Bits Stored bits that end at High Bit are compared, so that
    clearing the bit plane of an overlay in unused bits, as Clean Graphics
    does, changes no stored value; :func:`unused_bits` counts what is left
    in those bits. ``regions`` holds, for each frame in order, the regions
    of text that a finder found in it, as rows and columns of the frame,
    which Clean Pixel Data blacks out in that frame alone; the transform
    clips each to the frame, and so does this count. As in
    :func:`unused_bits`, the words are read as stored.
    """
    described = _pixel_description(source)
    if described is None or described != _pixel_description(written):
        return None
    frames, rows, columns, samples, planar, allocated, stored, high, _ = described
    if len(regions) != frames:
        return None
    by_plane = planar == 1 and samples > 1
    width = allocated // 8
    count = frames * rows * columns * samples
    shape = (
        (frames, samples, rows, columns)
        if by_plane
        else (frames, rows, columns, samples)
    )
    found = []
    for dataset in (source, written):
        data = bytes(dataset[_PIXEL_DATA].value)
        if len(data) < count * width:
            return None
        words = np.frombuffer(data, dtype=f"<u{width}", count=count).reshape(shape)
        # As frames, samples, rows, and columns, however they are stored.
        found.append(words if by_plane else np.moveaxis(words, 3, 1))
    before, after = found
    bits = np.asarray(((1 << stored) - 1) << (high - stored + 1), dtype=before.dtype)
    changed = (before & bits) != (after & bits)
    total = 0
    for frame, boxes in zip(changed, regions, strict=True):
        inside = np.zeros((rows, columns), dtype=bool)
        for box in boxes:
            inside[box.top : box.bottom, box.left : box.right] = True
        total += int(np.count_nonzero(frame[:, ~inside]))
    return total


def _pixel_description(dataset: pydicom.Dataset) -> tuple[int, ...] | None:
    """How a data set's Pixel Data holds its stored values, as the attributes
    of :data:`_PIXEL_DESCRIPTION` give it, in their order; or None where it
    has no Pixel Data that is native and little endian, in words of 8, 16,
    or 32 bits, or the attributes do not describe one."""
    meta = getattr(dataset, "file_meta", None)
    syntax = None if meta is None else meta.get("TransferSyntaxUID")
    element = dataset.get(_PIXEL_DATA)
    if syntax not in _NATIVE or element is None or element.value is None:
        return None
    try:
        found = tuple(
            int(dataset.get(keyword, default))
            for keyword, default in _PIXEL_DESCRIPTION
        )
    except (TypeError, ValueError):
        return None
    frames, rows, columns, samples, _, allocated, stored, high, _ = found
    if min(frames, rows, columns, samples) < 1 or allocated not in (8, 16, 32):
        return None
    if not 0 < stored <= high + 1 <= allocated:
        return None
    return found


def _groups(dataset: pydicom.Dataset, first: int) -> int:
    """How many of the repeating groups ``first`` to ``first`` + 0x1E, those
    of curves or of overlays, hold an attribute but their group length."""
    return len(
        {
            tag.group
            for tag in dataset.keys()
            if first <= tag.group <= first + 0x1E and tag.group % 2 == 0 and tag.element
        }
    )


def _run(
    data: bytes,
    name: str,
    annotations: _Annotations | None,
    decisions: Mapping[int, Review] | None,
    finder: Callable[[], TextFinder] | None = None,
) -> _Ran:
    """Run an instance once, or twice where the run keeps the sets that its
    first pass holds, and count what the run decides and writes."""
    options = {"modified_dates": _BASELINE, "with_pixel_data": _PIXEL_OPTIONS}.get(
        name, _OPTION
    )
    keeps_sets = name in ("each_and_sets_kept", "text_removed", "echoes_removed")
    try:
        # A run with Clean Pixel Data needs a text finder, and the transform
        # refuses one without it.
        found = finder() if finder is not None and name == "with_pixel_data" else None
        recorded = None if found is None else _Recorded(found)
        reviewed = None
        counted: collections.Counter[str] | None = None
        if decisions is not None and annotations is not None:
            reviewed = ReviewedAnnotations.empty()
            counted = collections.Counter()
            for index, review in decisions.items():
                reviewed.record(annotations.digests[index], review)
                counted[review.value] += 1
        passes = 1
        result = _transform(options, reviewed, recorded)(
            data, InstanceRecord.from_file(data)
        )
        while keeps_sets and reviewed is not None and counted is not None:
            held = sorted(
                {
                    each.digest
                    for each in _materials(result)
                    if each.together
                    and each.result.held_because is Held.NOT_REVIEWED_TOGETHER
                    and reviewed.get(each.digest) is None
                }
            )
            if not held or passes == _PASSES:
                break
            for digest in held:
                reviewed.record(digest, Review.KEEP)
            counted["keep together"] += len(held)
            passes += 1
            result = _transform(options, reviewed, recorded)(
                data, InstanceRecord.from_file(data)
            )
        ran = _outcome(result)
        if recorded is not None and ran.written is not None:
            ran.written = dataclasses.replace(
                ran.written,
                text_regions=sum(len(boxes) for boxes in recorded.frames),
                changed_outside_text_regions=stored_values_changed(
                    pydicom.dcmread(io.BytesIO(data)),
                    pydicom.dcmread(io.BytesIO(ran.written.data)),
                    recorded.frames,
                ),
            )
        ran.passes = passes if reviewed is not None else 0
        ran.decisions = counted
        for each in _materials(result):
            if each.together:
                ran.sets.append(each.result)
            else:
                ran.annotations[each.path.items[-1][1]] = each.result
        return ran
    # Anything that a run raises is counted, by where; its message, which
    # could quote a value, is dropped.
    except Exception as error:  # pylint: disable = broad-exception-caught
        return _Ran(f"raised: {crash_site(error)}")


def _transform(
    options: Sequence[str],
    reviewed: ReviewedAnnotations | None,
    finder: TextFinder | None = None,
) -> InstanceTransform:
    return InstanceTransform(
        policy.compose_custom_policy(options),
        _KEY,
        finder=finder,
        reviewed_annotations=reviewed,
        unvalidated_policy=True,
    )


def _materials(result: Transformed | Sequestered) -> list[AnnotationMaterial]:
    return [each for each in result.qc if isinstance(each, AnnotationMaterial)]


def _outcome(result: Transformed | Sequestered) -> _Ran:
    """The run's outcome: the transform's sequestration, or the release
    gate's decision on the written file, with the instance's own evidence as
    its subject's, and the reasons, as the release report names them."""
    if isinstance(result, Sequestered):
        return _Ran("sequestered", _sequestering(result.reasons))
    written = _written(result.data)
    decision = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    if isinstance(decision, Release):
        return _Ran("released", written=written)
    if isinstance(decision, HoldForReview):
        held = held_for_review([decision.reasons])
        reasons = collections.Counter(f"{each.stage}: {each.code}" for each in held)
        return _Ran("held", reasons, written=written)
    return _Ran("sequestered", _sequestering(decision.reasons), written=written)


def _sequestering(reasons: Iterable[object]) -> collections.Counter[str]:
    counted: collections.Counter[str] = collections.Counter()
    for cause in reasons:
        found = sequestration_reason(cause)
        text = f"{found.stage}: {found.code}"
        if found.attribute is not None:
            text += f" at {found.attribute}"
        if found.action is not None:
            text += f", {found.action}"
        counted[text] += 1
    return counted


def _written(data: bytes) -> _Written:
    """What a written file holds, by counts; its annotations' digests stay in
    memory."""
    dataset = pydicom.dcmread(io.BytesIO(data))
    element = dataset.get(_GRAPHIC_ANNOTATION_SEQUENCE)
    items = list(element.value) if element is not None and element.value else []
    codes = dataset.get(_METHOD_CODES)
    claims = any(
        str(item.get("CodeValue", "")) == CLEAN_GRAPHICS_CODE
        and str(item.get("CodingSchemeDesignator", "")) == "DCM"
        for item in (codes.value if codes is not None and codes.value else ())
    )
    return _Written(
        data,
        tuple(annotation_digest(item) for item in items),
        _objects(items, "TextObjectSequence"),
        _objects(items, "GraphicObjectSequence"),
        graphics_of(dataset),
        _groups(dataset, _CURVE_GROUPS),
        _groups(dataset, _OVERLAY_GROUPS),
        unused_bits(dataset),
        _nested_graphics(dataset),
        claims,
        _activation_layers(dataset),
    )


def _nested_graphics(dataset: pydicom.Dataset) -> int:
    """How many sequence items, at any depth, hold any of the graphics that
    the option removes."""
    count = 0
    for element in dataset:
        if element.VR != "SQ":
            continue
        for item in element.value or ():
            count += bool(graphics_of(item) & REMOVED_GRAPHICS)
            count += _nested_graphics(item)
    return count


def differences(first: bytes, second: bytes) -> dict[str, list[str]]:
    """The tags of the elements of two files, their file meta information's
    included, that one holds and the other does not, and that both hold
    with different values, at any depth below them."""
    datasets = [pydicom.dcmread(io.BytesIO(each)) for each in (first, second)]
    found: dict[str, list[str]] = {"added": [], "removed": [], "differ": []}
    for before, after in (
        (datasets[0].file_meta, datasets[1].file_meta),
        (datasets[0], datasets[1]),
    ):
        tags = set(before.keys()) | set(after.keys())
        for tag in sorted(tags):
            name = f"({tag.group:04X},{tag.element:04X})"
            if tag not in before:
                found["added"].append(name)
            elif tag not in after:
                found["removed"].append(name)
            elif before[tag] != after[tag]:
                found["differ"].append(name)
    return found


def _name(result: ReviewedAnnotation) -> str:
    if result.held_because is None:
        return result.outcome.value
    return f"{result.outcome.value}: {result.held_because.value}"


def instance_summary(ran: InstanceRuns) -> dict[str, Any]:
    """An instance's runs as the summary gives them: counts, codes, and tag
    numbers, and no value."""
    summary: dict[str, Any] = {
        "member": ran.label,
        "sop_class": uid_name(ran.sop_class),
        "holds": ran.holds,
        "runs": {},
    }
    if ran.crashed is not None:
        summary["crashed"] = ran.crashed
    for name, each in ran.runs.items():
        entry: dict[str, Any] = {"outcome": each.outcome}
        if each.reasons:
            entry["reasons"] = _sorted(each.reasons)
        if each.decisions is not None:
            entry["list"] = _sorted(each.decisions)
            entry["passes"] = each.passes
        if ran.annotations is not None and each.annotations:
            entry["annotations"] = _sorted(
                collections.Counter(
                    _name(result) for result in each.annotations.values()
                )
            )
        if ran.annotations is not None and each.sets:
            entry["sets"] = _sorted(
                collections.Counter(_name(result) for result in each.sets)
            )
        if each.written is not None:
            entry["written"] = _written_summary(each, ran.annotations)
        summary["runs"][name] = entry
    files = [ran.runs[name].written for name in WITHOUT_A_LIST if name in ran.runs]
    if len(files) == 2 and None not in files:
        first, second = (each.data for each in files if each is not None)
        summary["differences"] = differences(first, second)
    return summary


def _written_summary(ran: _Ran, source: _Annotations | None) -> dict[str, Any]:
    written = ran.written
    if written is None:
        return {}
    found: dict[str, Any] = {}
    if source is not None:
        found = {
            "graphic_annotations": len(written.digests),
            "text_objects": written.text_objects,
            "graphic_objects": written.graphic_objects,
            "kept_as_received": ran.kept_as_received(source),
            "activation_only_overlay_groups": len(written.activation_layers),
        }
    if written.unused_bits is not None:
        found["unused_bits"] = written.unused_bits
    if written.text_regions is not None:
        found["text_regions"] = written.text_regions
        found["changed_outside_text_regions"] = written.changed_outside_text_regions
    return {
        **found,
        "graphics": sorted(written.graphics),
        "curve_groups": written.curve_groups,
        "overlay_groups": written.overlay_groups,
        "nested_graphics": written.nested_graphics,
        "claims_clean_graphics": written.claims_clean_graphics,
    }


EXPECTATIONS: tuple[str, ...] = (
    "Without a reviewed annotations list, each Presentation State with "
    "annotations is sequestered for its Graphic Annotation Sequence alone, "
    "under Modified Dates alone and with Clean Graphics.",
    "With an empty list, each annotation is held as not reviewed and each set "
    "of annotations shown together is held, so each Presentation State is "
    "held for review, for its annotations alone.",
    "With each annotation kept and no decision on those shown together, each "
    "annotation shown with others is held, and so is each set; an annotation "
    "shown alone is kept unless it is held for its own text or drawing.",
    "With each annotation and each set kept, each annotation is kept unless "
    "it is held for its own text or drawing, as the same ones are without the "
    "decisions on the sets; each kept one is written as received but for its "
    "UIDs, and the Presentation State is released unless one is held.",
    "With each annotation removed, each Presentation State is sequestered, "
    "since its Type 1 Graphic Annotation Sequence would be left with no item.",
    "With each annotation that holds a text object removed, and the rest and "
    "their sets kept, only those are removed; the rest are kept unless held "
    "for their own text or drawing, each kept one is written as received but "
    "for its UIDs, and the Presentation State is released unless one is "
    "held. One whose annotations all hold text is sequestered.",
    "Where keeping every annotation holds one for echoing an identifier, "
    "removing those, and keeping the rest and their sets, removes only them "
    "and holds none of the rest that keeping them all did not; each kept one "
    "is written as received but for its UIDs, and the Presentation State is "
    "released unless one is held.",
    "Each image without an overlay in unused bits of Pixel Data holds curves "
    "or Overlay Data, and is released with each of its curve and overlay "
    "groups removed whole, under Modified Dates alone and with Clean "
    "Graphics.",
    "Clean Graphics changes nothing in the written file of an image without "
    "an overlay in unused bits of Pixel Data but its De-identification "
    "Method (0012,0063) and De-identification Method Code Sequence "
    "(0012,0064).",
    "Each image with an overlay in unused bits of Pixel Data is a Secondary "
    "Capture, and is sequestered as one whose Pixel Data is not cleaned, and "
    "for that alone, under Modified Dates alone and with Clean Graphics.",
    "With Clean Graphics and Clean Pixel Data, each image with an overlay in "
    "unused bits of Pixel Data, whose stored values hold more than their "
    "sign above High Bit, is written with none that does, with its Pixel "
    "Data described as received and each stored value as received outside "
    "the regions in which text was found in its frame, and with each of its "
    "overlay groups removed, claims Clean Graphics, and is held for review "
    "for its Pixel Data alone, as Clean Pixel Data holds each image that it "
    "cleans.",
    "Each Presentation State without annotations has an overlay group whose "
    "only attribute is Overlay Activation Layer (60xx,1001), and is released "
    "under Modified Dates alone and with Clean Graphics, with each such group "
    "kept as received; Clean Graphics changes nothing in its written file but "
    "its De-identification Method (0012,0063) and De-identification Method "
    "Code Sequence (0012,0064).",
    "Every file written under Clean Graphics claims it, with DCM 113103, and "
    "holds no Curve Data, Overlay Data, Overlay Comments, or overlay in Pixel "
    "Data, at any depth; no file written under Modified Dates alone claims it.",
    "No run raised.",
)


def evaluate(members: Sequence[InstanceRuns]) -> list[tuple[str, list[str]]]:
    """Each expectation, with the labels of the instances for which it is
    not met, or ``no instance`` where it applies to none."""
    unannotated = [each for each in members if _unannotated(each)]
    states = [
        each for each in members if each.presentation_state and not _unannotated(each)
    ]
    images = [
        each for each in members if not each.presentation_state and not each.embedded
    ]
    embedded = [each for each in members if each.embedded]
    tests: list[tuple[Sequence[InstanceRuns], Callable[[InstanceRuns], bool]]] = [
        (states, _sequestered_without_a_list),
        (states, _held_with_an_empty_list),
        (states, _held_without_the_sets),
        (states, _released_as_reviewed),
        (states, _sequestered_with_each_removed),
        (states, _released_without_the_text),
        (states, _released_without_the_echoes),
        (images, _groups_removed),
        (images, _only_the_markers_change),
        (embedded, _sequestered_as_uncleaned),
        (embedded, _cleared_and_held),
        (unannotated, _released_keeping_the_activation),
        (members, _claimed_and_clean),
        (members, _nothing_raised),
    ]
    found = []
    for text, (scope, test) in zip(EXPECTATIONS, tests, strict=True):
        if not scope:
            found.append((text, ["no instance"]))
            continue
        found.append((text, [each.label for each in scope if not _met(test, each)]))
    return found


def _unannotated(member: InstanceRuns) -> bool:
    """Whether a member is a Presentation State read without annotations;
    one that could not be read is taken to have them."""
    return (
        member.presentation_state
        and member.annotations is not None
        and not member.annotations.digests
    )


def _met(test: Callable[[InstanceRuns], bool], member: InstanceRuns) -> bool:
    return member.crashed is None and test(member)


def _sequestered(ran: _Ran | None) -> bool:
    return (
        ran is not None
        and ran.outcome == "sequestered"
        and ran.written is None
        and ran.reasons == collections.Counter({NO_DUMMY_VALUE: 1})
    )


def _sequestered_without_a_list(member: InstanceRuns) -> bool:
    return all(_sequestered(member.runs.get(name)) for name in WITHOUT_A_LIST)


def _held_with_an_empty_list(member: InstanceRuns) -> bool:
    ran, source = member.runs.get("empty_list"), member.annotations
    if ran is None or source is None or ran.written is None:
        return False
    count = len(source.digests)
    not_reviewed = ReviewedAnnotation(Outcome.HELD, Held.NOT_REVIEWED)
    return (
        ran.outcome == "held"
        and ran.reasons == collections.Counter({"annotations: not-reviewed": 1})
        and sorted(ran.annotations) == list(range(count))
        and all(result == not_reviewed for result in ran.annotations.values())
        and len(ran.sets) == len(source.sets(range(count)))
        and all(result.outcome is Outcome.HELD for result in ran.sets)
        and len(ran.written.digests) == count
    )


def _held_without_the_sets(member: InstanceRuns) -> bool:
    ran, source = member.runs.get("each_kept"), member.annotations
    if ran is None or source is None or ran.written is None:
        return False
    count = len(source.digests)
    sets = source.sets(range(count))
    together = {index for each in sets for index in each}
    if sorted(ran.annotations) != list(range(count)):
        return False
    for index, result in ran.annotations.items():
        if result.outcome is Outcome.REMOVED:
            return False
        if index in together and result.outcome is not Outcome.HELD:
            return False
        if result.outcome is Outcome.HELD and index not in together:
            if result.held_because not in _HELD_FOR_ITSELF:
                return False
    return (
        len(ran.sets) == len(sets)
        and all(result.outcome is Outcome.HELD for result in ran.sets)
        and _gated(ran)
        and len(ran.written.digests) == count
    )


def _released_as_reviewed(member: InstanceRuns) -> bool:
    ran, first = member.runs.get("each_and_sets_kept"), member.runs.get("each_kept")
    source = member.annotations
    if ran is None or first is None or source is None:
        return False
    count = len(source.digests)
    return (
        _kept_unless_held_for_itself(ran, range(count), source)
        and ran.held_for_itself() == first.held_for_itself()
    )


def _sequestered_with_each_removed(member: InstanceRuns) -> bool:
    return _sequestered(member.runs.get("each_removed"))


def _released_without_the_text(member: InstanceRuns) -> bool:
    ran, source = member.runs.get("text_removed"), member.annotations
    if ran is None or source is None:
        return False
    kept = [index for index, text in enumerate(source.with_text) if not text]
    return _removed(ran, kept, source)


def _released_without_the_echoes(member: InstanceRuns) -> bool:
    first, source = member.runs.get("each_and_sets_kept"), member.annotations
    if first is None or source is None:
        return False
    echoes = {
        index
        for index, result in first.annotations.items()
        if result.held_because is Held.ECHOES_IDENTIFIER
    }
    ran = member.runs.get("echoes_removed")
    if not echoes:
        return ran is None
    if ran is None:
        return False
    kept = [index for index in range(len(source.digests)) if index not in echoes]
    return _removed(ran, kept, source) and not (
        ran.held_for_itself() - first.held_for_itself()
    )


def _removed(ran: _Ran, kept: Sequence[int], source: _Annotations) -> bool:
    """Whether a run whose list removes every annotation but ``kept``, and
    keeps those and their sets, removes those alone and keeps the rest, as
    :func:`_kept_unless_held_for_itself` gives; or, where it keeps none,
    sequesters the instance."""
    if not kept:
        return _sequestered(ran)
    count = len(source.digests)
    removed = {
        index
        for index, result in ran.annotations.items()
        if result.outcome is Outcome.REMOVED
    }
    return removed == set(range(count)) - set(kept) and _kept_unless_held_for_itself(
        ran, kept, source
    )


def _kept_unless_held_for_itself(
    ran: _Ran, kept: Iterable[int], source: _Annotations
) -> bool:
    """Whether a run whose list keeps the annotations ``kept`` and their
    sets keeps each of them, unless it is held for its own text or drawing,
    keeps or holds as not drawn each set of them, writes them, and those
    kept as received, and releases the instance unless one is held."""
    kept = list(kept)
    if ran.written is None or ran.survivors(len(source.digests)) != kept:
        return False
    results = [ran.annotations[index] for index in kept]
    if any(
        result.outcome is not Outcome.KEPT
        and result.held_because not in _HELD_FOR_ITSELF
        for result in results
    ):
        return False
    sets_kept = len(ran.sets) == len(source.sets(kept)) and all(
        result.outcome is Outcome.KEPT or result.held_because is Held.NOT_DRAWN
        for result in ran.sets
    )
    received = ran.kept_as_received(source) == sum(
        result.outcome is Outcome.KEPT for result in results
    )
    return (
        sets_kept and received and len(ran.written.digests) == len(kept) and _gated(ran)
    )


def _gated(ran: _Ran) -> bool:
    """Whether the gate released a written file whose annotations are all
    kept or removed, and otherwise held it for its annotations alone."""
    held = any(result.outcome is Outcome.HELD for result in ran.annotations.values())
    if not held:
        return ran.outcome == "released"
    return (
        ran.outcome == "held" and bool(ran.reasons) and set(ran.reasons) <= _HELD_CODES
    )


def _groups_removed(member: InstanceRuns) -> bool:
    """Whether an image that holds curves or Overlay Data is released under
    each run without a list, with no attribute of a curve or overlay group
    left but a group length, at the top level or nested."""
    if not _HELD_GROUPS & set(member.holds.get("graphics", ())):
        return False
    for name in WITHOUT_A_LIST:
        ran = member.runs.get(name)
        if ran is None or ran.outcome != "released" or ran.written is None:
            return False
        written = ran.written
        if written.curve_groups or written.overlay_groups or written.nested_graphics:
            return False
    return True


def _only_the_markers_change(member: InstanceRuns) -> bool:
    first, second = (member.runs.get(name) for name in WITHOUT_A_LIST)
    if first is None or second is None:
        return False
    if first.written is None or second.written is None:
        return False
    return differences(first.written.data, second.written.data) == {
        "added": [],
        "removed": [],
        "differ": list(MARKERS),
    }


def _sequestered_as_uncleaned(member: InstanceRuns) -> bool:
    if member.sop_class not in SECONDARY_CAPTURES:
        return False
    for name in WITHOUT_A_LIST:
        ran = member.runs.get(name)
        if ran is None or ran.outcome != "sequestered" or ran.written is not None:
            return False
        if ran.reasons != collections.Counter({UNCLEANED_SECONDARY_CAPTURE: 1}):
            return False
    return True


def _cleared_and_held(member: InstanceRuns) -> bool:
    ran = member.runs.get("with_pixel_data")
    if not member.holds.get("unused_bits") or ran is None or ran.written is None:
        return False
    written = ran.written
    return (
        written.unused_bits == 0
        and written.changed_outside_text_regions == 0
        and written.overlay_groups == 0
        and written.claims_clean_graphics
        and ran.outcome == "held"
        and sum(ran.reasons.values()) == 1
        and set(ran.reasons) <= _PIXEL_DATA_CODES
    )


def _released_keeping_the_activation(member: InstanceRuns) -> bool:
    if not member.activation_layers:
        return False
    for name in WITHOUT_A_LIST:
        ran = member.runs.get(name)
        if ran is None or ran.outcome != "released" or ran.written is None:
            return False
        if ran.written.activation_layers != member.activation_layers:
            return False
    return _only_the_markers_change(member)


def _claimed_and_clean(member: InstanceRuns) -> bool:
    for name, ran in member.runs.items():
        if ran.written is None:
            continue
        if name == "modified_dates":
            if ran.written.claims_clean_graphics:
                return False
            continue
        if not ran.written.claims_clean_graphics:
            return False
        if ran.written.graphics & REMOVED_GRAPHICS or ran.written.nested_graphics:
            return False
    return True


def _nothing_raised(member: InstanceRuns) -> bool:
    return member.crashed is None and not any(
        ran.outcome.startswith("raised: ") for ran in member.runs.values()
    )


def _sorted(counter: Mapping[str, int]) -> dict[str, int]:
    return dict(sorted(counter.items()))
