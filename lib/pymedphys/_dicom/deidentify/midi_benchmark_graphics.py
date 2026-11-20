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

"""Count the graphics that Clean Graphics removes in a MIDI benchmark's run (D-018).

The Clean Graphics Option (PS3.15 E.3.3) gives C to four rows of Table
E.1-1: Curve Data (50xx,xxxx), Overlay Data (60xx,3000), Overlay Comments
(60xx,4000), and Graphic Annotation Sequence (0070,0001). The engine gives
each its Basic Profile action, and clears an overlay that an overlay group
without Overlay Data places in unused bits of Pixel Data (D-041), so a run
under the option releases what a run under ``basic`` does, apart from its
markers, and that alone cannot show whether the test data set holds any
graphics for the option to remove. The design document's validation table
asks a MIDI-B run under the option to show how many of MIDI-B's instances
carry overlays or graphic annotations.

:class:`GraphicsCounter` wraps the transform that the benchmark gives the
run, and counts, by the SOP Class of each instance that the transform
receives, as the standard names it, the instances that hold each of the
four rows, and an overlay group without Overlay Data, as the engine finds
one (:func:`~pymedphys._dicom.deidentify.pixel_risk.overlay_groups_without_data`);
and, of the instances that the transform writes, whether or not the run
then releases them, those whose source held any of them, and those whose
written file still holds any of them. An instance that holds any of them
and that the transform sequesters is not written, so only the written
instances whose source held any show the option removing them. It reads
which attributes are present at the top level of each data set, where the
IODs define them, and no value of the instance: an empty Graphic Annotation
Sequence counts as one, and an overlay that lies in Pixel Data is found by
its group's attributes, not by its bits, which the engine's own check of
the written file verifies (D-041).
"""

from __future__ import annotations

import collections
import io
import threading
from collections.abc import Iterable

from pymedphys._imports import pydicom

from .midi_benchmark_errors import uid_name
from .pixel_risk import overlay_groups_without_data
from .references import InstanceRecord
from .run_results import Sequestered, Transform, Transformed

# What an instance can hold that the option removes: its four rows of Table
# E.1-1, in the table's order, and an overlay that may lie in Pixel Data.
GRAPHICS = (
    "curve_data",
    "overlay_data",
    "overlay_comments",
    "graphic_annotation_sequence",
    "overlay_in_pixel_data",
)
# The counts of each SOP Class, in their order.
COUNTED = (
    "instances",
    "instances_with_graphics",
    *GRAPHICS,
    "written",
    "written_with_graphics_before",
    "written_with_graphics_after",
)

_CURVE_GROUPS = 0x5000
_OVERLAY_GROUPS = 0x6000
_OVERLAY_DATA = 0x3000
_OVERLAY_COMMENTS = 0x4000
_GRAPHIC_ANNOTATION_SEQUENCE = 0x00700001


def _in_repeating_group(group: int, first: int) -> bool:
    """Whether ``group`` is one of the 16 even groups of a repeating group
    from ``first``, as (50xx,xxxx) and (60xx,xxxx) are."""
    return first <= group <= first + 0x1E and group % 2 == 0


def graphics_of(dataset: pydicom.Dataset) -> frozenset[str]:
    """Return which of :data:`GRAPHICS` a data set holds at its top level.

    Curve Data is any attribute of a curve group but its group length, and
    an overlay in Pixel Data is an overlay group without Overlay Data, as
    :func:`~pymedphys._dicom.deidentify.pixel_risk.overlay_groups_without_data`
    finds it. No value is read.

    >>> dataset = pydicom.Dataset()
    >>> graphics_of(dataset)
    frozenset()
    >>> dataset.add_new(0x60003000, "OW", b"\\x00\\x00")
    >>> dataset.add_new(0x50020005, "US", 2)
    >>> sorted(graphics_of(dataset))
    ['curve_data', 'overlay_data']
    >>> dataset.add_new(0x60020100, "US", 16)
    >>> sorted(graphics_of(dataset))
    ['curve_data', 'overlay_data', 'overlay_in_pixel_data']
    """
    found: set[str] = set()
    for tag in dataset.keys():
        if not tag.element:
            continue
        if _in_repeating_group(tag.group, _CURVE_GROUPS):
            found.add("curve_data")
        elif _in_repeating_group(tag.group, _OVERLAY_GROUPS):
            if tag.element == _OVERLAY_DATA:
                found.add("overlay_data")
            elif tag.element == _OVERLAY_COMMENTS:
                found.add("overlay_comments")
        elif tag == _GRAPHIC_ANNOTATION_SEQUENCE:
            found.add("graphic_annotation_sequence")
    if overlay_groups_without_data(dataset):
        found.add("overlay_in_pixel_data")
    return frozenset(found)


def _read(data: bytes) -> tuple[str, frozenset[str]] | None:
    """Return a Part 10 file's SOP Class, by name, and the graphics that it
    holds, or ``None`` where it cannot be read."""
    try:
        dataset = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
        return uid_name(dataset.get("SOPClassUID")), graphics_of(dataset)
    except Exception:  # pylint: disable = broad-exception-caught
        # The run refuses or sequesters what cannot be read.
        return None


class GraphicsCounter:
    """Count the graphics that Clean Graphics removes, by SOP Class."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, collections.Counter[str]] = {}

    def transform(self, transform: Transform) -> Transform:
        """Return ``transform``, counting the graphics of each instance that
        it receives, and of each file that it writes.

        Each written instance is counted under ``written``, under
        ``written_with_graphics_before`` where its source held any graphics,
        and under ``written_with_graphics_after`` where its written file
        still holds any. An instance whose file cannot be read is counted
        under ``unreadable``, with no graphics. A written file that cannot be
        read counts as one that holds graphics, since it cannot be shown not
        to.
        A transform's ``prepare`` method, which the run calls before any
        instance, is kept, as
        :meth:`~pymedphys._dicom.deidentify.midi_benchmark_errors.ErrorRecorder.transform`
        keeps it.
        """

        def counted(data: bytes, record: InstanceRecord) -> Transformed | Sequestered:
            source = _read(data)
            sop_class, found = ("unreadable", frozenset()) if source is None else source
            self._count(
                sop_class,
                ["instances", *found, *(["instances_with_graphics"] if found else [])],
            )
            result = transform(data, record)
            if isinstance(result, Transformed):
                written = _read(result.data)
                kept = written is None or bool(written[1])
                self._count(
                    sop_class,
                    [
                        "written",
                        *(["written_with_graphics_before"] if found else []),
                        *(["written_with_graphics_after"] if kept else []),
                    ],
                )
            return result

        prepare = getattr(transform, "prepare", None)
        if callable(prepare):
            setattr(counted, "prepare", prepare)
        return counted

    def _count(self, sop_class: str, fields: Iterable[str]) -> None:
        with self._lock:
            self._counts.setdefault(sop_class, collections.Counter()).update(fields)

    def counts(self) -> dict[str, dict[str, int]]:
        """Return the counts of each SOP Class, the classes in order of name.

        Each holds every one of :data:`COUNTED`, in its order.
        """
        with self._lock:
            counted = {name: dict(counts) for name, counts in self._counts.items()}
        return {
            name: {field: counts.get(field, 0) for field in COUNTED}
            for name, counts in sorted(counted.items())
        }
