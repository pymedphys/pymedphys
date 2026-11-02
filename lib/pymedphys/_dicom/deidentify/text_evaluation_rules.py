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

"""A rule that finds overlays at a frame's extreme values, for the
evaluation alone (D-056).

Devices often draw their overlays, burned-in text among them, at the
greatest or least value a frame holds, which anatomy rarely reaches in a
region the size of a glyph. :class:`SaturatedOverlayDetector` needs no
model: it finds the connected components of pixels at a frame's minimum or
maximum, keeps those of a glyph's size, joins glyphs that lie close
together along a line into one box, and grows each box by a margin. It is
measured through the same harness as the models
(:class:`~.text_evaluation_detector.MeasuredDetector`), at each of its own
settings (:class:`OverlayPoint`), as a comparator, and, through
:class:`CombinedDetector`, joined with a model's boxes, as a candidate to
combine with one.

Only the evaluation library makes these detectors: nothing in a run or its
command selects one, and their method names the rule, so that their boxes
are never taken for a run's.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from .text_detection import TextBox
from .text_evaluation_detector import MeasuredDetector, PostProcessing
from .text_evaluation_frames import EvaluationFrame, EvaluationRefused
from .text_evaluation_models import BoxPoint

RULE = "saturated-overlay"
# Raised whenever what the rule finds for the same settings changes.
RULE_VERSION = 1
LEVELS = ("minimum", "maximum")
REFERENCES = ("frame", "stored-range")


@dataclasses.dataclass(frozen=True)
class OverlayPoint:
    """One setting of the rule.

    Attributes
    ----------
    levels : tuple of str
        Which of :data:`LEVELS` an overlay may be drawn at.
    reference : str
        ``"frame"``: the least and greatest values the frame holds; or
        ``"stored-range"``: the least and greatest its Pixel Data can hold.
    tolerance : int
        Stored values within this of an extreme count as at it.
    min_rows, max_rows : int
        A glyph's height, in frame pixels: the rows of a component's box.
    max_columns : int
        A glyph's greatest width, in frame pixels.
    min_pixels : int
        A glyph's fewest pixels, so that isolated pixels of noise are not
        glyphs.
    join_rows, join_columns : int
        Glyphs whose pixels lie within twice these of each other, in frame
        pixels, join into one box.
    margin : int
        Frame pixels added to every side of each box.
    renderings : tuple of str
        Empty: the rule reads stored values, not renderings. Kept so that
        the rule's settings are :class:`~.text_evaluation_models.BoxPoint`.

    For an RGB frame, a pixel is at the maximum where any channel is at its
    own maximum, since coloured overlays saturate a channel, and at the
    minimum where every channel is at its own.
    """

    levels: tuple[str, ...] = LEVELS
    reference: str = "frame"
    tolerance: int = 0
    min_rows: int = 2
    max_rows: int = 48
    max_columns: int = 64
    min_pixels: int = 3
    join_rows: int = 1
    join_columns: int = 3
    margin: int = 2
    renderings: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.levels or tuple(
            level for level in LEVELS if level in self.levels
        ) != tuple(self.levels):
            raise EvaluationRefused("The levels must be known ones, each once.")
        if self.reference not in REFERENCES:
            raise EvaluationRefused("The reference must be a known one.")
        numbers = (
            self.tolerance,
            self.min_rows,
            self.max_rows,
            self.max_columns,
            self.min_pixels,
            self.join_rows,
            self.join_columns,
            self.margin,
        )
        if not all(isinstance(each, int) and each >= 0 for each in numbers):
            raise EvaluationRefused("The rule's settings must be whole numbers.")
        if not 1 <= self.min_rows <= self.max_rows or self.max_columns < 1:
            raise EvaluationRefused("A glyph's size must be a range of pixels.")
        if self.renderings:
            raise EvaluationRefused("The rule reads stored values, not renderings.")

    def described(self) -> dict[str, object]:
        """The setting, for the summary."""
        described = {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in dataclasses.asdict(self).items()
        }
        del described["renderings"]
        return described


class SaturatedOverlayDetector:
    """The rule, as the module describes, measured at each of its settings."""

    @property
    def method(self) -> Mapping[str, object]:
        """What decides the boxes: the rule, its version, and the versions
        of NumPy and SciPy."""
        return {
            "rule": RULE,
            "rule_version": RULE_VERSION,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        }

    def boxes_of_points(
        self, frame: EvaluationFrame, points: Sequence[Any]
    ) -> list[tuple[TextBox, ...]]:
        """The boxes of each setting, for one frame, each once, sorted.

        Raises
        ------
        EvaluationRefused
            For a point that is not an :class:`OverlayPoint`.
        """
        if not all(isinstance(point, OverlayPoint) for point in points):
            raise EvaluationRefused("A point is not one of the rule's settings.")
        masks: dict[tuple, list[np.ndarray]] = {}
        found = []
        for point in points:
            key = (point.levels, point.reference, point.tolerance)
            if key not in masks:
                masks[key] = saturated(frame, point)
            found.append(overlay_boxes(masks[key], point))
        return found


def saturated(frame: EvaluationFrame, point: OverlayPoint) -> list[np.ndarray]:
    """The pixels at each of the setting's extremes of the frame's stored
    values, one mask for each level, since a glyph at the maximum that
    touches air at the minimum is still a glyph."""
    values = np.asarray(frame.stored, dtype=np.int64)
    if not frame.rgb:
        values = values[..., np.newaxis]
    if point.reference == "frame":
        low = values.min(axis=(0, 1))
        high = values.max(axis=(0, 1))
    else:
        low = np.full(values.shape[2], frame.stored_range[0], np.int64)
        high = np.full(values.shape[2], frame.stored_range[1], np.int64)
    masks = []
    if "minimum" in point.levels:
        masks.append((values <= low + point.tolerance).all(axis=2))
    if "maximum" in point.levels:
        masks.append((values >= high - point.tolerance).any(axis=2))
    return masks


def overlay_boxes(
    masks: Sequence[np.ndarray], point: OverlayPoint
) -> tuple[TextBox, ...]:
    """The boxes of the masks' components of glyph size, each mask's
    components found apart, then joined along lines and grown by the
    margin."""
    ndimage = scipy.ndimage
    eight = np.ones((3, 3), bool)
    kept = np.zeros(masks[0].shape, bool)
    for mask in masks:
        kept |= _glyphs(mask, point, eight)
    if not kept.any():
        return ()
    reach = np.ones((2 * point.join_rows + 1, 2 * point.join_columns + 1), bool)
    joined, _ = ndimage.label(
        ndimage.binary_dilation(kept, structure=reach), structure=eight
    )
    joined = np.where(kept, joined, 0)
    rows_count, columns_count = kept.shape
    found = set()
    for each in ndimage.find_objects(joined):
        if each is None:
            continue
        rows, columns = each
        found.add(
            TextBox(
                top=max(0, rows.start - point.margin),
                left=max(0, columns.start - point.margin),
                bottom=min(rows_count, rows.stop + point.margin),
                right=min(columns_count, columns.stop + point.margin),
            )
        )
    return tuple(sorted(found))


def _glyphs(mask: np.ndarray, point: OverlayPoint, eight: np.ndarray) -> np.ndarray:
    """The pixels of a mask's components of a glyph's size."""
    ndimage = scipy.ndimage
    labels, count = ndimage.label(mask, structure=eight)
    if count == 0:
        return np.zeros(mask.shape, bool)
    indices = np.arange(1, count + 1)
    sizes = np.asarray(ndimage.sum_labels(mask, labels, indices), np.int64)
    glyph = np.zeros(count + 1, bool)
    for index, (rows, columns) in enumerate(ndimage.find_objects(labels), start=1):
        glyph[index] = (
            point.min_rows <= rows.stop - rows.start <= point.max_rows
            and columns.stop - columns.start <= point.max_columns
            and sizes[index - 1] >= point.min_pixels
        )
    return glyph[labels]


@dataclasses.dataclass(frozen=True)
class CombinedPoint:
    """A model's point joined with one of the rule's settings.

    Attributes
    ----------
    model : PostProcessing or BoxPoint
        A point of the model's detector.
    rule : OverlayPoint
    """

    model: PostProcessing | BoxPoint
    rule: OverlayPoint

    def __post_init__(self):
        if not isinstance(self.rule, OverlayPoint):
            raise EvaluationRefused("A combined point needs one of the rule's.")
        if isinstance(self.model, OverlayPoint):
            raise EvaluationRefused("A combined point needs a model's point.")

    def described(self) -> dict[str, object]:
        """The two settings, each named by its side, for the summary."""
        return {
            **{f"model.{key}": value for key, value in self.model.described().items()},
            **{f"rule.{key}": value for key, value in self.rule.described().items()},
        }


class CombinedDetector:
    """A model's detector and the rule, whose boxes are joined: a region
    is boxed where either boxes it.

    Parameters
    ----------
    model : MeasuredDetector
        The model's detector, such as an
        :class:`~.text_evaluation_detector.EvaluationDetector`, which still
        takes its grid from one pass.
    rule : SaturatedOverlayDetector, optional
    """

    def __init__(
        self, model: MeasuredDetector, rule: SaturatedOverlayDetector | None = None
    ):
        if isinstance(model, (SaturatedOverlayDetector, CombinedDetector)):
            raise EvaluationRefused("The rule is combined with a model's detector.")
        self._model = model
        self._rule = SaturatedOverlayDetector() if rule is None else rule

    @property
    def method(self) -> Mapping[str, object]:
        """The methods of the model's detector and of the rule."""
        return {"model": dict(self._model.method), "rule": dict(self._rule.method)}

    def boxes_of_points(
        self, frame: EvaluationFrame, points: Sequence[Any]
    ) -> list[tuple[TextBox, ...]]:
        """The joined boxes of each combined point, for one frame, each
        once, sorted.

        Raises
        ------
        EvaluationRefused
            For a point that is not a :class:`CombinedPoint`.
        """
        if not all(isinstance(point, CombinedPoint) for point in points):
            raise EvaluationRefused("A point is not a combined one.")
        models = _distinct([point.model for point in points])
        rules = _distinct([point.rule for point in points])
        model_boxes = dict(zip(models, self._model.boxes_of_points(frame, models)))
        rule_boxes = dict(zip(rules, self._rule.boxes_of_points(frame, rules)))
        return [
            tuple(sorted(set(model_boxes[point.model]) | set(rule_boxes[point.rule])))
            for point in points
        ]


def _distinct(points: Sequence[Any]) -> list[Any]:
    """The points, each once, in their first order."""
    return list(dict.fromkeys(points))
