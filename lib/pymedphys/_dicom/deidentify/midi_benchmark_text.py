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

"""Count what the text detector found in a MIDI benchmark's run (D-018).

Under the Clean Pixel Data Option, the run's transform gives each frame of
an instance's Pixel Data to the text detector, blacks out each region that
it finds, and holds the instance for review whether or not it found one,
until a reviewer approves its regions (D-037). No one reviews a benchmark's
regions, so a benchmark under the option releases none of those instances;
what it can show is what the detector found. :class:`TextCounter` wraps the
transform that the benchmark gives the run, and counts, from the QC
material of each instance that the transform cleaned, by the instance's
SOP Class as the standard names it, the instances and frames that the
detector searched, those in which it found a region, and the regions, and
the frames by how many regions each has, in the bins in which the Text
Detector Check counts a slice's regions
(:data:`~pymedphys._dicom.deidentify.pixel_text_validation.REGIONS_PER_SLICE`),
so that the counts on MIDI-B's images can be set beside those on HaN-Seg's.
No region's place or size is counted, and no value of the instance.
"""

from __future__ import annotations

import collections
import threading

from .midi_benchmark_errors import kinds_of
from .references import InstanceRecord
from .run_qc import RedactionMaterial
from .run_results import Sequestered, Transform, Transformed

# The lower edges of the bins of a frame's regions, each bin from its edge
# to under the next, the last from its edge up, as the Text Detector Check
# bins a slice's.
REGION_EDGES = (0, 1, 2, 3, 4, 5, 10, 20)
# The counts of each SOP Class, in their order.
COUNTED = (
    "instances",
    "instances_with_a_region",
    "frames",
    "frames_with_a_region",
    "regions",
)
FRAMES_BY_REGIONS = "frames_by_regions"


def region_bin(regions: int) -> str:
    """Return the bin of a frame's number of regions, as the check names it.

    >>> [region_bin(n) for n in (0, 1, 4, 5, 9, 10, 25)]  # doctest: +NORMALIZE_WHITESPACE
    ['0 to under 1', '1 to under 2', '4 to under 5', '5 to under 10',
     '5 to under 10', '10 to under 20', '20 or more']
    """
    if regions < 0:
        raise ValueError("a frame cannot have fewer than no regions")
    for low, high in zip(REGION_EDGES, REGION_EDGES[1:]):
        if regions < high:
            return f"{low} to under {high}"
    return f"{REGION_EDGES[-1]} or more"


REGION_BINS = tuple(region_bin(edge) for edge in REGION_EDGES)


class TextCounter:
    """Count what Clean Pixel Data's text detector found, by SOP Class."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, collections.Counter[str]] = {}

    def transform(self, transform: Transform) -> Transform:
        """Return ``transform``, counting what the detector found in each
        instance that it cleans.

        A transform's ``prepare`` method, which the run calls before any
        instance, is kept, as
        :meth:`~pymedphys._dicom.deidentify.midi_benchmark_errors.ErrorRecorder.transform`
        keeps it.
        """

        def counted(data: bytes, record: InstanceRecord) -> Transformed | Sequestered:
            result = transform(data, record)
            for material in result.qc:
                if isinstance(material, RedactionMaterial):
                    self._count(kinds_of(data)[0], material)
            return result

        prepare = getattr(transform, "prepare", None)
        if callable(prepare):
            setattr(counted, "prepare", prepare)
        return counted

    def _count(self, sop_class: str, material: RedactionMaterial) -> None:
        regions = [len(boxes) for _, boxes in material.regions]
        found = sum(1 for each in regions if each)
        with self._lock:
            counts = self._counts.setdefault(sop_class, collections.Counter())
            counts["instances"] += 1
            counts["instances_with_a_region"] += 1 if found else 0
            counts["frames"] += material.frames
            counts["frames_with_a_region"] += found
            counts["regions"] += sum(regions)
            counts[region_bin(0)] += material.frames - found
            for each in regions:
                if each:
                    counts[region_bin(each)] += 1

    def counts(self) -> dict[str, dict[str, object]]:
        """Return the counts of each SOP Class, the classes in order of name.

        Each holds :data:`COUNTED`, then :data:`FRAMES_BY_REGIONS`, the
        frames in each of :data:`REGION_BINS`, every bin given.
        """
        with self._lock:
            counted = {name: dict(counts) for name, counts in self._counts.items()}
        return {
            name: {
                **{field: counts.get(field, 0) for field in COUNTED},
                FRAMES_BY_REGIONS: {
                    label: counts.get(label, 0) for label in REGION_BINS
                },
            }
            for name, counts in sorted(counted.items())
        }
