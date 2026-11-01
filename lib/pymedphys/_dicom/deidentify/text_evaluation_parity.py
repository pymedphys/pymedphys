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

"""How much a model's boxes change with the resize alone (D-056).

A model measured at its publishers' settings
(:func:`~.text_evaluation_detector.published_variant`) is resized by
OpenCV, as their pipeline does, while today's settings resize by the
harness's own bilinear zoom. Text strokes one to three pixels wide can
cross a threshold under a sub-pixel shift, so :func:`resize_parity`
measures the difference directly: each frame of each case, as read and
with the plan's text burned in, through the same model at the same
points, once with each resize, counting frame by frame the regions that
only one resize gives and the texts that only one covers fully. It counts,
and names no case.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from pymedphys._imports import numpy as np

from .face_validation import crash_site
from .text_detection import TextBox
from .text_evaluation import INK_LEVEL, EvaluationSettings, _covered, split_of
from .text_evaluation_detector import (
    DetectorVariant,
    EvaluationDetector,
    MeasuredDetector,
)
from .text_evaluation_frames import EvaluationFrame, EvaluationRefused, tissue_mask
from .text_evaluation_injection import inject
from .text_evaluation_models import DetectionModel
from .text_evaluation_sources import CaseSource, Skipped

FORMAT = "pymedphys-deid-text-detector-resize-parity/1"
_FIELDS = (
    "frames",
    "regions_first",
    "regions_second",
    "regions_only_first",
    "regions_only_second",
    "texts",
    "fully_covered_first",
    "fully_covered_second",
    "texts_changed",
)


def resize_parity(
    cases: Sequence[CaseSource],
    model: DetectionModel,
    settings: EvaluationSettings,
    *,
    first: DetectorVariant,
    second: DetectorVariant,
    detector: Callable[..., MeasuredDetector] = EvaluationDetector,
) -> dict[str, Any]:
    """Count, for each point, how the boxes of ``model`` under ``first``
    differ from those under ``second``, frame by frame, as the module
    describes, over the part of the split that ``settings`` evaluates.

    The variants must differ in their resampler alone.
    """
    same = dataclasses.replace(
        first,
        name=second.name,
        network_input=dataclasses.replace(
            first.network_input, resampler=second.network_input.resampler
        ),
    )
    if same != second or first == second:
        raise EvaluationRefused("The variants must differ in their resize alone.")
    detectors = (
        detector(variant=first, model=model),
        detector(variant=second, model=model),
    )
    counts = [dict.fromkeys(_FIELDS, 0) for _ in settings.points]
    tally = {"cases": 0, "skipped": 0, "crashed": {}}
    for case in cases:
        split = split_of(case.collection, case.case, settings.held_out_collections)
        if settings.evaluated not in ("all", split):
            continue
        tally["cases"] += 1
        try:
            for item in case.read():
                if isinstance(item, Skipped):
                    tally["skipped"] += 1
                    continue
                for frame in _passes(item, settings):
                    _count(frame, detectors, settings, counts)
        # A case that raises is counted by where, never by its message.
        except Exception as error:  # pylint: disable = broad-exception-caught
            site = crash_site(error)
            tally["crashed"][site] = tally["crashed"].get(site, 0) + 1
    return {
        "format": FORMAT,
        "model": model.described(),
        "first": first.network_input.resampler,
        "second": second.network_input.resampler,
        "evaluated": settings.evaluated,
        **tally,
        "points": [
            {"index": index, "post_processing": point.described(), **count}
            for index, (point, count) in enumerate(zip(settings.points, counts))
        ],
    }


def _passes(
    frame: EvaluationFrame, settings: EvaluationSettings
) -> Iterator[EvaluationFrame]:
    yield frame
    if settings.plan is not None and not frame.rgb:
        injected = inject(frame, settings.plan).frame
        if len(injected.texts) > len(frame.texts):
            yield injected


def _count(
    frame: EvaluationFrame,
    detectors: tuple[MeasuredDetector, MeasuredDetector],
    settings: EvaluationSettings,
    counts: list[dict[str, int]],
) -> None:
    shape = frame.shape
    tissue = tissue_mask(frame)
    inks = [(text.ink(shape, INK_LEVEL), text.ink(shape, 0.0)) for text in frame.texts]
    zone_boxes = [text.zone(shape) for text in frame.texts]
    zones = np.zeros(shape, bool)
    for zone in zone_boxes:
        zones[zone.top : zone.bottom, zone.left : zone.right] = True
    boxes = [each.boxes_of_points(frame, settings.points) for each in detectors]
    for index, count in enumerate(counts):
        mine: tuple[TextBox, ...] = boxes[0][index]
        theirs: tuple[TextBox, ...] = boxes[1][index]
        covered = [
            _covered(each, inks, zone_boxes, zones, tissue) for each in (mine, theirs)
        ]
        count["frames"] += 1
        count["regions_first"] += len(mine)
        count["regions_second"] += len(theirs)
        count["regions_only_first"] += len(set(mine) - set(theirs))
        count["regions_only_second"] += len(set(theirs) - set(mine))
        count["texts"] += len(frame.texts)
        full = [[text[0] for text in each.texts] for each in covered]
        count["fully_covered_first"] += sum(full[0])
        count["fully_covered_second"] += sum(full[1])
        count["texts_changed"] += sum(a != b for a, b in zip(*full))
