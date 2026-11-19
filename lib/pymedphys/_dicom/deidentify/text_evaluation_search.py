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

"""The named detector variants and post-processing grids that a tuning run
of the text detector's evaluation searches (D-056, step 3).

A tuning run of the ``Text Detector Evaluation`` workflow names one variant
(:data:`VARIANTS`), which changes the network's maps and so needs a pass of
its own, and one grid (:data:`GRIDS`), whose points one pass measures
together. Both are fixed here, by name, so that a run's inputs are choices
that a reviewer has read, never settings typed into a dispatch, and so that
a run can be repeated from its inputs and its commit alone.

Every grid's first point is today's post-processing, the baseline that the
criteria compare the others with; every variant but ``"today"`` differs from
today's detector in one respect only, so that a run shows what that one
respect changes. Combinations are added once single changes have been
measured. Nothing here changes what a run of the Clean Pixel Data Option
does: variants and grids are measured, never used, until one is adopted.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType

from .text_detection import RENDERINGS, DetectionParameters
from .text_evaluation_detector import (
    DetectorVariant,
    InputVariant,
    PostProcessing,
    RenderingVariant,
    post_processing_grid,
)

_TODAY = DetectionParameters()


def _variant(name: str, **changes: object) -> DetectorVariant:
    return DetectorVariant(name=name, **changes)  # type: ignore[arg-type]


def _parameters(**changes: object) -> DetectionParameters:
    return dataclasses.replace(_TODAY, **changes)  # type: ignore[arg-type]


# Today's detector keeps its own variant, named "default", so that a run of
# it is described as every earlier run of it was.
VARIANTS: Mapping[str, DetectorVariant] = MappingProxyType(
    {
        "today": DetectorVariant(),
        **{
            each.name: each
            for each in (
                # Each top-hat's noise estimated over the frame's tissue, not
                # over the whole frame, whose air can hold almost none.
                _variant(
                    "noise over tissue", rendering=RenderingVariant(noise="tissue")
                ),
                # Each top-hat windowed to fewer or more noise deviations than
                # today's 20.
                _variant(
                    "top-hats to 10 deviations",
                    parameters=_parameters(hat_noise_multiple=10.0),
                ),
                _variant(
                    "top-hats to 40 deviations",
                    parameters=_parameters(hat_noise_multiple=40.0),
                ),
                # The top-hats' structuring element sized in millimetres.
                _variant("top-hats of 8 mm", rendering=RenderingVariant(hat_mm=8.0)),
                # No rendering's window narrower than 100 of the modality's
                # units, Hounsfield units for a CT.
                _variant(
                    "window of at least 100 units",
                    rendering=RenderingVariant(window_floor=100.0),
                ),
                # The network's input scaled up further, or by millimetres.
                _variant(
                    "input of at least 1024", parameters=_parameters(limit_side=1024)
                ),
                _variant(
                    "input at 0.5 mm",
                    network_input=InputVariant(scaling="millimetres", millimetres=0.5),
                ),
            )
        },
    }
)

# Each post-processing setting varied alone about today's, each value once.
_SINGLES: dict[str, tuple[object, ...]] = {
    "threshold": (0.2, 0.25, 0.4),
    "box_threshold": (0.4, 0.6, 0.7, 0.8),
    "unclip_ratio": (2.0, 2.5, 3.0),
    "margin": (4, 6, 8),
    "short_side_pixels": (24, 64, 96),
    "short_side_fraction": (0.04, 0.12, 0.16),
    "min_fill": (0.1, 0.4, 0.5, 0.6),
    "renderings": tuple(
        tuple(name for name in RENDERINGS if name != dropped) for dropped in RENDERINGS
    )
    + tuple((name,) for name in RENDERINGS),
}


def _singles() -> tuple[PostProcessing, ...]:
    points: dict[PostProcessing, None] = {PostProcessing(): None}
    for name, values in _SINGLES.items():
        for point in post_processing_grid(**{name: values}):
            points[point] = None
    # The shape filter for nearly square regions, which must spare single
    # letters, by the side from which it applies.
    for point in post_processing_grid(
        min_elongation=(1.5, 2.0, 3.0), elongation_from_side=(16.0, 32.0)
    ):
        points[point] = None
    return tuple(points)


GRIDS: Mapping[str, tuple[PostProcessing, ...]] = MappingProxyType(
    {
        "today": (PostProcessing(),),
        "single settings": _singles(),
    }
)
