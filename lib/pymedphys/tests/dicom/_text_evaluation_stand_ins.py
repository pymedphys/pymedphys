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

"""Stand-ins shared by the text detector evaluation's tests: a detector
whose boxes are known, invented frames, texts, and cases, and a run of the
evaluation on them. Every value is invented."""

import dataclasses

from pymedphys._imports import numpy as np

from pymedphys._dicom.deidentify import text_evaluation as evaluation
from pymedphys._dicom.deidentify.text_detection import RENDERINGS, RenderedProbability
from pymedphys._dicom.deidentify.text_evaluation_detector import (
    PostProcessing,
    grid_boxes,
)
from pymedphys._dicom.deidentify.text_evaluation_frames import (
    BurnedText,
    EvaluationFrame,
)

from . import _synthetic_references as synthetic

SECRET = "SECRET^CASE^4711"
SHAPE = (64, 64)
# A detector's probability is 0.9 inside these regions of every frame, and
# a region of 8 or more network pixels at the default settings gives a box
# grown by the unclip offset and the margin.
REGION_TEXT = (8, 8, 16, 40)
REGION_ANATOMY = (40, 20, 50, 30)


class BoxDetector:
    """A stand-in detector: its full-range map is 0.9 inside its regions,
    on the frame's own grid, and its other maps are empty."""

    def __init__(self, regions=(REGION_TEXT, REGION_ANATOMY)):
        self.regions = tuple(regions)

    @property
    def method(self):
        return {"network": "boxes", "variant": {"name": "boxes"}}

    def probabilities(self, frame):
        maps = []
        for name in RENDERINGS:
            probability = np.zeros(frame.shape, np.float32)
            if name == "full-range":
                for top, left, bottom, right in self.regions:
                    probability[top:bottom, left:right] = 0.9
            maps.append(RenderedProbability(name, frame.shape, probability))
        return tuple(maps)

    def boxes_of_points(self, frame, points):
        return grid_boxes(self.probabilities(frame), points)


def box_detector():
    """Makes a :class:`BoxDetector`, picklable for worker processes."""
    return BoxDetector()


def _frame(stored=None, *, case=SECRET, collection="collection", texts=(), **options):
    stored = np.full(SHAPE, 1024, np.uint16) if stored is None else stored
    return EvaluationFrame(
        stored=stored,
        collection=collection,
        case=case,
        iod=options.pop("iod", "CT Image Storage"),
        modality=options.pop("modality", "CT"),
        intercept=-1024.0,
        pixel_spacing=options.pop("pixel_spacing", 1.0),
        texts=tuple(texts),
        **options,
    )


def _text(top, left, rows, columns, **strata):
    return BurnedText(top, left, np.ones((rows, columns)), float(rows), strata)


@dataclasses.dataclass(frozen=True)
class Frames:
    """A case whose frames are given."""

    collection: str
    case: str
    frames: tuple

    def read(self):
        yield from self.frames


@dataclasses.dataclass(frozen=True)
class Raising:
    """A case whose reading raises, with a message that quotes a value."""

    collection: str = "collection"
    case: str = SECRET

    def read(self):
        yield _frame()
        raise ValueError(SECRET)


def _settings(**options):
    return evaluation.EvaluationSettings(
        points=options.pop("points", (PostProcessing(),)),
        evaluated=options.pop("evaluated", "all"),
        **options,
    )


def _run(cases, **options):
    workers = options.pop("workers", 1)
    run = evaluation.evaluate(
        cases, box_detector, _settings(**options), workers=workers
    )
    return evaluation.summarise(run, replicates=200)


def _ct_dataset(frames, **attributes):
    words = np.asarray(frames)
    dataset = synthetic.ct_slice(0)
    dataset.Modality = "CT"
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows, dataset.Columns = words.shape[1:]
    dataset.BitsAllocated, dataset.BitsStored, dataset.HighBit = 16, 12, 11
    dataset.PixelRepresentation = 0
    if words.shape[0] > 1:
        dataset.NumberOfFrames = words.shape[0]
    for keyword, value in attributes.items():
        setattr(dataset, keyword, value)
    dataset.PixelData = words.astype("<u2").tobytes()
    return dataset
