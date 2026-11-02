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

"""The face block check's counts on DICOM files as CommonMark (D-054).

:func:`markdown` renders :func:`~.face_validation_dicom.summarise`'s
counts, and nothing else, so the page shows no more than the JSON does.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .face_validation_markdown import _bins, _codes, _value


def markdown(summary: Mapping[str, Any]) -> str:
    """Render the counts as a CommonMark page."""
    files = summary["files"]
    ct = summary["ct"]
    series = summary["series"]
    eyes = summary["eye_rois"]
    targets = summary["targets"]
    doses = summary["rt_doses"]
    structure_sets = summary["rt_structure_sets"]
    plans = summary["rt_plans"]
    lines = [
        "# Face block check on DICOM files",
        "",
        "The files given to the face block finder, its holds, RT Dose "
        "defacing, and contour cutting as a de-identification run under the "
        "Clean Recognizable Visual Features Option gives them its files, and "
        "the block found compared with the eye ROIs and targets of the "
        "structure sets. Only counts are shown: no value, image, name, or "
        "date of the files, and nothing was rendered.",
        "",
        "| About | |",
        "| --- | --- |",
        "| Software | "
        + ", ".join(
            f"{name} {version}" for name, version in summary["software"].items()
        )
        + " |",
        "",
        "## Files",
        "",
        "| Files | Count |",
        "| --- | ---: |",
        f"| Found | {files['total']} |",
        f"| Read | {files['read']} |",
        f"| Not read | {files['not-read']} |",
        *(
            f"| Refused: `{reason}` | {count} |"
            for reason, count in files["refused"].items()
        ),
        *(
            f"| Crashed: `{site}` | {count} |"
            for site, count in summary["crashed"].items()
        ),
        "",
        *_codes("IOD", files["iods"], "Files"),
        "## CT series",
        "",
        f"CT series: {ct['series']}. CT Image instances without a Series "
        f"Instance UID, which a run does not deface: "
        f"{ct['instances_without_series']}.",
        "",
        *_codes("Storage of the first slice", ct["storage"], "Series"),
        *_codes(
            "Air at -900 HU or below in at least 1% of voxels",
            ct["air_in_hounsfield_units"],
            "Series",
        ),
        *_bins("Larger spacing within a slice", ct["pixel_spacing"], "Series"),
        *_bins("Median spacing between slices", ct["slice_spacing"], "Series"),
        "## Outcomes",
        "",
        "| Outcome | Series |",
        "| --- | ---: |",
        f"| Defaced | {series['defaced']} |",
        *(
            f"| Not defaced: `{reason}` | {count} |"
            for reason, count in series["not_defaced"].items()
        ),
        "",
        *_codes(
            "Series with an eye ROI, by outcome", series["with_eye_rois"], "Series"
        ),
        "## Eye ROIs against the globes found",
        "",
        f"Series with a block found, defaced or held: "
        f"{eyes['series_with_a_block']}. Eye ROIs whose points could not be "
        f"placed: {eyes['not_placed']}. Eye ROIs named for one side whose "
        f"centroid is nearer the other side's globe: {eyes['sides_swapped']}.",
        "",
        *_codes("Eye ROIs of the series", eyes["by_series"], "Series"),
        *_codes("Side that the name gives", eyes["sides"], "Eye ROIs"),
        *_bins(
            "Distance from the globe found to the eye ROI's centroid",
            eyes["globe_centre_error"],
            "Globes",
        ),
        *_bins(
            "Distance from the eye ROI's farthest point to the nearer globe found",
            eyes["eye_reach"],
            "Eye ROIs",
        ),
        *_bins(
            "Height of the eye ROI's lowest point above the block's inferior limit",
            eyes["eyes_above_inferior_limit"],
            "Eye ROIs",
        ),
        "## Targets",
        "",
        *_codes("Where each target lies", targets["by_where"], "Targets"),
        *_bins(
            "Clearance of each target clear of the block",
            targets["clearance"],
            "Targets",
        ),
        "## RT Doses in a defaced frame",
        "",
        *_codes("Outcome", doses["outcomes"], "RT Doses"),
        *_bins(
            "Greatest dose set to zero, of the grid's greatest",
            doses["share_set_to_zero"],
            "RT Doses",
        ),
        "## RT Structure Sets in a defaced frame",
        "",
        *_codes("Outcome", structure_sets["outcomes"], "RT Structure Sets"),
        *_codes(
            "ROIs cut, by RT ROI Interpreted Type", structure_sets["rois_cut"], "ROIs"
        ),
        "## RT Plans",
        "",
        f"RT Plans: {plans['total']}, of which in a defaced frame: "
        f"{plans['in_defaced_frames']}.",
        "",
        "## Settings",
        "",
        "| Setting | Value |",
        "| --- | --- |",
        *(
            f"| `{name}` | {_value(value)} |"
            for name, value in summary["settings"].items()
        ),
    ]
    return "\n".join(lines) + "\n"
