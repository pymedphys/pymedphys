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

"""A QC pack of synthetic images for the redaction review app (D-059).

Each image is a geometric CT phantom with invented text burned in at known
places, from :mod:`._synthetic_text`; no frame holds real data. A finder
proposes a region over each string it is told of, and a region over the
phantom that covers no text, so that a reviewer has a false positive to
drop; it misses one string, so that a reviewer has a region to draw.
"""

from __future__ import annotations

import json
from pathlib import Path

from pymedphys._imports import numpy as np

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.instance_transform import (
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.policy import (
    CLEAN_PIXEL_DATA,
    compose_custom_policy,
)
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _synthetic_references as synthetic
from . import _synthetic_text as text
from .test_deidentify_pixel_cleaning import KEY, _ct

SIZE = 128
# A region over the phantom that covers no text, in every frame.
FALSE_POSITIVE = TextBox(60, 40, 72, 70)


class PlannedFinder:
    """Proposes the regions planned for each frame, in the order it sees them."""

    method = {"finder": "planned regions", "version": 1}

    def __init__(self, plans):
        self.plans = list(plans)
        self.seen = 0

    def find(self, frame):  # pylint: disable = unused-argument
        boxes = self.plans[self.seen] if self.seen < len(self.plans) else ()
        self.seen += 1
        return tuple(boxes)


def _burned(rng, strings):
    """A phantom slice with each (text, top, left) burned in, and the box of
    each string's ink."""
    frame = text.ct_slice(rng, SIZE)
    boxes = []
    for words, top, left in strings:
        frame, burned = text.burn(frame, words, top, left, 4095)
        rows, columns = np.nonzero(burned.ink)
        boxes.append(
            TextBox(
                int(rows.min()),
                int(columns.min()),
                int(rows.max()) + 1,
                int(columns.max()) + 1,
            )
        )
    return frame, boxes


def write_pack(directory: Path) -> tuple[Path, dict[str, int]]:
    """Run the synthetic images once under Clean Pixel Data, and return the
    QC pack's directory and each image's run position, by file name.

    ``one.dcm`` is a slice with two strings, both proposed, and the false
    positive; ``three.dcm`` holds three frames: the first with a string
    proposed, the second with a string that the finder misses, and the third
    with none, but the false positive proposed.
    """
    rng = np.random.default_rng(20261101)
    source = directory / "source"
    source.mkdir(parents=True)
    one, one_boxes = _burned(rng, [("ZQ 0001", 4, 4), ("MRN 99", 116, 80)])
    frames, plans = [], [[*one_boxes, FALSE_POSITIVE]]
    first, first_boxes = _burned(rng, [("SITE A", 4, 70)])
    missed, _ = _burned(rng, [("1.2.3", 110, 4)])
    clear, _ = _burned(rng, [])
    frames = [first, missed, clear]
    plans += [first_boxes, [], [FALSE_POSITIVE]]
    single = _ct(one.astype(np.uint16))
    single.SOPInstanceUID = "2.25.9101"
    multi = _ct(np.stack(frames).astype(np.uint16))
    multi.SOPInstanceUID = "2.25.9102"
    (source / "one.dcm").write_bytes(synthetic.written(single))
    (source / "three.dcm").write_bytes(synthetic.written(multi))
    transform = InstanceTransform(
        compose_custom_policy([CLEAN_PIXEL_DATA]),
        KEY,
        finder=PlannedFinder(plans),
        unvalidated_policy=True,
    )
    result = run.run(
        run.discover(source),
        directory / "release",
        transform,
        ReleaseGate(),
        qc_destination=directory / "qc",
        reporter=transform.reporter,
    )
    document = json.loads(result.qc_pack.read_text("utf-8"))
    positions = {
        Path(entry["source"]).name: entry["position"] for entry in document["instances"]
    }
    return result.qc_pack.parent, positions
