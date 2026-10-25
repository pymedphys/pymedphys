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

"""The face block check's counts as CommonMark (D-054).

:func:`markdown` renders :func:`~.face_validation.summarise`'s counts, and
nothing else, so the page shows no more than the JSON does.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .face_validation import SHARES, TISSUES


def markdown(summary: Mapping[str, Any]) -> str:
    """Render the counts as a CommonMark page."""
    data = summary["data"]
    software = summary["software"]
    cases = summary["cases"]
    series = summary["series"]
    lines = [
        f"# Face block check on {data['name']}",
        "",
        "Each case's CT, given to the face block finder and the CT defacer "
        "as a de-identification run under the Clean Recognizable Visual "
        "Features Option gives them a CT series, and the block found and the "
        "air written compared with the case's reference masks. Only counts "
        "are shown: no value, image, or case of the data set.",
        "",
        "| About | |",
        "| --- | --- |",
        f"| Data set | {data['name']} {data['version']}, "
        f"doi:{data['doi']}, {data['licence']} |",
        f"| File | {data['file']['size']} bytes, MD5 `{data['file']['md5']}`, "
        f"SHA-256 `{data['file']['sha256']}` |",
        "| Software | "
        + ", ".join(f"{name} {version}" for name, version in software.items())
        + " |",
        "",
        f"The data set: {data['citation']}.",
        "",
        "## Cases",
        "",
        "| Cases | Count |",
        "| --- | ---: |",
        f"| In the data set | {cases['total']} |",
        f"| Measured | {cases['measured']} |",
        *(
            f"| Not measured: `{reason}` | {count} |"
            for reason, count in cases["not_measured"].items()
        ),
        *(
            f"| Crashed: `{site}` | {count} |"
            for site, count in cases["crashed"].items()
        ),
        "",
        "## CT volumes",
        "",
        *_codes("Format", summary["ct"]["formats"], "Volumes"),
        *_codes(
            "Air at -900 HU or below in at least 1% of voxels",
            summary["ct"]["air_in_hounsfield_units"],
            "Volumes",
        ),
        *_bins(
            "Larger spacing within a slice", summary["ct"]["pixel_spacing"], "Volumes"
        ),
        *_bins("Spacing between slices", summary["ct"]["slice_spacing"], "Volumes"),
        "## Masks",
        "",
        *_codes("Format", summary["masks"]["formats"], "Masks"),
        *_codes("Not read", summary["masks"]["not_read"], "Masks"),
        f"Masks with a voxel outside the CT, left out: "
        f"{summary['masks']['partly_outside_ct']}.",
        "",
        "## Series",
        "",
        "| Outcome | Series |",
        "| --- | ---: |",
        f"| Defaced | {series['defaced']} |",
        *(
            f"| Not defaced: `{reason}` | {count} |"
            for reason, count in series["not_defaced"].items()
        ),
        "",
        "## Defaced series against the reference eyes",
        "",
        *_codes("Reference eyes", summary["eyes_of_defaced_series"], "Series"),
        f"Series whose globes found were taken for the other side's: "
        f"{summary['sides_swapped']}.",
        "",
        *_bins(
            "Distance from each globe found to its eye's centroid",
            summary["globe_centre_error"],
            "Globes",
        ),
        *_bins(
            "Distance from the farthest eye voxel to the nearer globe found",
            summary["eye_reach"],
            "Series",
        ),
        *_bins(
            "Height of the eyes' lowest voxel above the block's inferior limit",
            summary["eyes_above_inferior_limit"],
            "Series",
        ),
        "## Reference eyes",
        "",
        f"Cases with both eyes' masks: {summary['reference_eyes']['cases']}.",
        "",
        *_bins(
            "Diameter of a sphere of each eye's volume",
            summary["reference_eyes"]["globe_diameter"],
            "Eyes",
        ),
        *_bins(
            "Distance between the eyes' centroids across the axial plane",
            summary["reference_eyes"]["globe_separation"],
            "Cases",
        ),
        *_bins(
            "Turn of the line between the eyes from left-right",
            summary["reference_eyes"]["turn"],
            "Cases",
        ),
        "## Organs written as air in the defaced series",
        "",
        "Each organ's share of voxels written as air, by how many series.",
        "",
        "| Organ | " + " | ".join(SHARES) + " |",
        "| --- | " + " | ".join("---:" for _ in SHARES) + " |",
        *(
            f"| `{organ}` | "
            + " | ".join(str(shares[share]) for share in SHARES)
            + " |"
            for organ, shares in summary["written_as_air"].items()
        ),
        "",
        *_finder(summary["finder"]),
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


def _finder(finder: Mapping[str, Any]) -> list[str]:
    """The section on what the finder saw, by each case's outcome."""
    outcomes = list(finder["cases"])
    eyes, pair = finder["eyes"], finder["eye_pair"]

    def coded(title: str, counts: Mapping[str, Mapping[str, int]]) -> list[str]:
        return _by_outcome(title, outcomes, _coded_rows(counts, outcomes))

    def binned(title: str, counts: Mapping[str, Mapping[str, Any]]) -> list[str]:
        return _by_outcome(title, outcomes, _binned_rows(counts, outcomes))

    lines = [
        "## What the finder saw",
        "",
        "In each case with both eyes' masks, the finder's steps on the same "
        "slices, counted by the case's outcome. A ball is a region of soft "
        "tissue that the finder considered as a globe; it keeps those that "
        "other tissue or air mostly surrounds. The ball at an eye is the kept "
        "ball nearest the eye's centroid, within 5 mm of it. Rows with no "
        "count are left out; the JSON lists every bin.",
        "",
        *_codes("Cases inspected", finder["cases"], "Cases"),
        *_codes(
            "Cases with both eyes' masks not inspected",
            finder["not_inspected"],
            "Cases",
        ),
    ]
    if not outcomes:
        return lines
    lines += [
        *coded("The finder's own outcome", finder["finder_outcome"]),
        *binned("Side of the finder's voxels (mm)", finder["voxel"]),
        *binned("Balls considered", finder["balls_considered"]),
        *binned("Balls kept", finder["balls_kept"]),
        "### At each eye",
        "",
        *binned(
            "Distance from each eye's centroid to the nearest ball considered (mm)",
            eyes["nearest_ball"],
        ),
        *coded(
            "The nearest ball considered, where within 5 mm of each eye's centroid",
            eyes["nearest_ball_status"],
        ),
        *binned(
            "Its share of the surrounding sphere outside soft tissue",
            eyes["nearest_ball_outside"],
        ),
        *binned(
            "Its greatest share of one half of the sphere outside soft tissue",
            eyes["nearest_ball_best_half"],
        ),
        *binned(
            "Distance from each eye's centroid to the nearest kept ball (mm)",
            eyes["nearest_kept_ball"],
        ),
        *coded("Eyes with a kept ball within 5 mm", eyes["kept_ball_at_each_eye"]),
        *binned(
            "Greatest depth of soft tissue within 5 mm of each eye's centroid (mm)",
            eyes["depth"],
        ),
        *coded(
            "That depth against the depths at which a ball is looked for",
            eyes["depth_against_window"],
        ),
        "### The pair of balls at the eyes",
        "",
        *coded("Cases with a kept ball at each eye", pair["tested"]),
        *coded("Side by side", pair["side_by_side"]),
        *coded("Bone lateral to each ball", pair["bone_lateral"]),
        *coded("Bone superior to each ball", pair["bone_superior"]),
        *coded("Passes every test of a pair", pair["passes"]),
        *binned("Share of the region behind filled by tissue", pair["head_behind"]),
        *binned("Share of the region in front filled by tissue", pair["head_in_front"]),
        *binned("Behind less in front", pair["head_margin"]),
        *coded("Bone encloses more above the eyes than below", pair["cranium_above"]),
        "### Other pairs that pass the tests of a pair",
        "",
        *binned("Other pairs", finder["other_pairs"]),
        *coded(
            "Where their balls lie from the eyes' centroids: at an eye within "
            "15 mm, or above or below beyond 10 mm, and behind or in front "
            "beyond 15 mm",
            finder["other_pair_places"],
        ),
        "### Tissue about each kept ball",
        "",
        "Shares of the points of each kept ball's surround test, by its "
        "averaged value: soft tissue from -40 to 160 HU, fat from -200 HU up "
        "to that, air below -500 HU, and bone from 300 HU.",
        "",
    ]
    for kind, noun in (("eye", "the balls at the eyes"), ("other", "the others")):
        for tissue in TISSUES:
            lines += binned(
                f"Share in {tissue}, {noun}", finder["shells"][kind][tissue]
            )
    return lines


def _coded_rows(
    counts: Mapping[str, Mapping[str, int]], outcomes: list[str]
) -> list[tuple[str, list[int]]]:
    codes = sorted({code for outcome in outcomes for code in counts[outcome]})
    return [
        (f"`{code}`", [counts[outcome].get(code, 0) for outcome in outcomes])
        for code in codes
    ]


def _binned_rows(
    counts: Mapping[str, Mapping[str, Any]], outcomes: list[str]
) -> list[tuple[str, list[int]]]:
    rows = []
    for index, each in enumerate(counts[outcomes[0]]["bins"]):
        found = [counts[outcome]["bins"][index]["count"] for outcome in outcomes]
        if any(found):
            rows.append((_range(each), found))
    return rows


def _by_outcome(
    title: str, outcomes: list[str], rows: list[tuple[str, list[int]]]
) -> list[str]:
    """A table of counts with a column for each outcome."""
    if not rows:
        return [f"{title}: none.", ""]
    return [
        f"| {title} | " + " | ".join(f"`{outcome}`" for outcome in outcomes) + " |",
        "| --- | " + " | ".join("---:" for _ in outcomes) + " |",
        *(
            f"| {label} | " + " | ".join(str(count) for count in found) + " |"
            for label, found in rows
        ),
        "",
    ]


def _codes(title: str, counts: Mapping[str, int], noun: str) -> list[str]:
    """A table of counts by code."""
    if not counts:
        return [f"{title}: none.", ""]
    return [
        f"| {title} | {noun} |",
        "| --- | ---: |",
        *(f"| `{code}` | {count} |" for code, count in counts.items()),
        "",
    ]


def _bins(title: str, counts: Mapping[str, Any], noun: str) -> list[str]:
    """A table of counts by bin."""
    unit = counts["unit"]
    return [
        f"| {title} ({unit}) | {noun} |",
        "| --- | ---: |",
        *(f"| {_range(each)} | {each['count']} |" for each in counts["bins"]),
        "",
    ]


def _range(each: Mapping[str, Any]) -> str:
    low, high = each["from"], each["to"]
    if low is None:
        return f"below {high:g}"
    if high is None:
        return f"{low:g} or more"
    return f"{low:g} to under {high:g}"


def _value(value: Any) -> str:
    if isinstance(value, list):
        return " to ".join(f"{each:g}" for each in value)
    return f"{value:g}"
