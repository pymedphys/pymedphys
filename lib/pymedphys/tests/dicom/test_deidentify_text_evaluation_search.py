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

"""The named variants and grids that a tuning run searches."""

import dataclasses
import pathlib
import re

from pymedphys._dicom.deidentify import text_evaluation_search as search
from pymedphys._dicom.deidentify.text_evaluation_detector import (
    DetectorVariant,
    PostProcessing,
)

WORKFLOW = (
    pathlib.Path(__file__).parents[4]
    / ".github"
    / "workflows"
    / "text-detector-evaluation.yml"
)


def _changed(variant: DetectorVariant) -> list[str]:
    """The settings in which a variant differs from today's detector."""
    today = DetectorVariant()
    changed = []
    for part in ("parameters", "rendering", "network_input"):
        mine, theirs = getattr(variant, part), getattr(today, part)
        changed += [
            f"{part}.{field.name}"
            for field in dataclasses.fields(mine)
            if getattr(mine, field.name) != getattr(theirs, field.name)
        ]
    return changed


def test_today_is_todays_detector_and_each_other_variant_changes_one_setting():
    assert search.VARIANTS["today"] == DetectorVariant()
    for name, variant in search.VARIANTS.items():
        if name == "today":
            continue
        assert variant.name == name
        # A scaling by millimetres is one change with its millimetres.
        changed = set(_changed(variant)) - {"network_input.millimetres"}
        assert len(changed) == 1, name


def test_every_grid_starts_at_todays_point_and_repeats_none():
    for name, points in search.GRIDS.items():
        assert points[0] == PostProcessing(), name
        assert len(set(points)) == len(points), name


def test_each_point_of_the_single_settings_changes_one_setting():
    today = PostProcessing()
    for point in search.GRIDS["single settings"][1:]:
        changed = {
            field.name
            for field in dataclasses.fields(point)
            if getattr(point, field.name) != getattr(today, field.name)
        }
        # The shape filter is one setting with the side it applies from.
        assert len(changed - {"elongation_from_side"}) == 1, changed


def test_the_workflow_offers_exactly_the_named_variants_and_grids():
    text = WORKFLOW.read_text(encoding="utf-8")
    variant = re.search(r"\n      variant:\n(.*?)\n        default:", text, re.S)
    grid = re.search(r"\n      grid:\n(.*?)\n        default:", text, re.S)
    assert variant is not None and grid is not None
    offered = re.findall(r"\n          - (.+)", variant.group(1))
    assert offered == list(search.VARIANTS)
    (options,) = re.findall(r"options: \[(.*)\]", grid.group(1))
    assert [each.strip() for each in options.split(",")] == list(search.GRIDS)
