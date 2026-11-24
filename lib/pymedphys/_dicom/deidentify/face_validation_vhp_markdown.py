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

"""The Visible Human face block check's measures as CommonMark (D-057).

:func:`markdown` renders
:func:`~pymedphys._dicom.deidentify.face_validation_vhp.check_visible_human`'s
summary, and nothing else, so the page shows no more than the JSON does.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def markdown(summary: Mapping[str, Any]) -> str:
    """Render the summary as a CommonMark page."""
    source = summary["source"]
    reference = summary["reference"]
    lines = [
        "# Face block check on the NLM Visible Human Project",
        "",
        f"**{source['attribution']}** {source['notice']}",
        "",
        f"{summary['held_out']}",
        "",
        "Each CT series is given to the face block finder three ways: as a "
        "de-identification run under the Clean Recognizable Visual Features "
        "Option gives it a series (*engine*); each stack of slices that share "
        "a geometry as a series of its own (*by stack*); and the slices within "
        "the head reach resampled onto one grid (*resampled*), which a run "
        "does not do. Each block found, and a *reference* block placed from "
        "globe centres placed by hand, is given to the CT defacer slice by "
        "slice.",
        "",
        "| About | |",
        "| --- | --- |",
        f"| Collection | `{source['collection']}`, IDC data release "
        f"{source['idc_release']}, doi:{source['record_doi']} |",
        f"| Bucket | `{source['bucket']}` |",
        f"| Licence | {source['licence']}, <{source['terms']}> |",
        f"| Reference globes | placed by hand within {reference['tolerance_mm']} "
        f"mm; spheres of {reference['radius_mm']} mm |",
        "| Software | "
        + ", ".join(
            f"{name} {version}" for name, version in summary["software"].items()
        )
        + " |",
        "",
        "## Outcomes",
        "",
        "| Subject | Series | Covers | Files | Engine | By stack | Resampled |",
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for each in summary["series"]:
        if "crashed" in each:
            outcome = f"crashed: `{each['crashed']}`"
            lines.append(
                f"| {each['subject']} | `{each['series']}` | {each['description']} "
                f"| {each['files']} | {outcome} | | |"
            )
            continue
        stacks = ", ".join(
            f"{stack['stack']}: `{stack['outcome']}`" for stack in each["by_stack"]
        )
        lines.append(
            f"| {each['subject']} | `{each['series']}` | {each['description']} "
            f"| {each['files']} | `{each['engine']['outcome']}` | {stacks} "
            f"| `{each['resampled']['outcome']}` |"
        )
    for each in summary["series"]:
        if each.get("reference_globes") is None or "crashed" in each:
            continue
        lines += _head(each)
    lines += [
        "## Settings",
        "",
        "| Setting | Value |",
        "| --- | --- |",
        *(f"| `{name}` | {value} |" for name, value in summary["settings"].items()),
        "",
        f"{source['attribution']} {source['notice']}",
        "",
    ]
    return "\n".join(lines)


def _head(each: Mapping[str, Any]) -> list[str]:
    lines = [
        "",
        f"## {each['subject']}: {each['description']}",
        "",
        f"Series `{each['series']}`. Reference globes, right then left: "
        + "; ".join(_point(globe) for globe in each["reference_globes"])
        + " mm.",
        "",
        "### Stacks",
        "",
        "| Stack | Slices | Pixel spacing (mm) | First z (mm) | Last z (mm) | Gaps (mm) |",
        "| ---: | ---: | --- | ---: | ---: | --- |",
    ]
    for number, stack in enumerate(each["stacks"], start=1):
        lines.append(
            f"| {number} | {stack['slices']} | "
            f"{' by '.join(str(v) for v in stack['pixel_spacing_mm'])} | "
            f"{stack['first_position_mm'][2]} | {stack['last_position_mm'][2]} | "
            f"{', '.join(str(v) for v in stack['slice_gaps_mm'])} |"
        )
    lines += [
        "",
        "### What the finder saw",
        "",
        "| Way | Outcome | Voxel (mm) | Balls kept | Pairs passing "
        "| Globe errors (mm) | Ball at right globe | Ball at left globe |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    ways = [("engine", each["engine"])]
    ways += [(f"stack {stack['stack']}", stack) for stack in each["by_stack"]]
    ways.append(("resampled", each["resampled"]))
    for name, found in ways:
        inspection = found.get("inspection", {})
        at = found.get("at_reference", {})
        errors = found.get("globe_error_mm")
        lines.append(
            f"| {name} | `{found['outcome']}` | {inspection.get('voxel_mm', '')} "
            f"| {inspection.get('balls_kept', '')} "
            f"| {inspection.get('pairs_passing', '')} "
            f"| {'' if errors is None else ', '.join(str(e) for e in errors)}"
            f"{' (swapped)' if found.get('swapped') else ''} "
            f"| {_ball(at.get('right'))} | {_ball(at.get('left'))} |"
        )
    lines += [
        "",
        "A ball's entry gives its distance from the reference centre, its "
        "radius, its surround test's two shares (outside the soft tissue over "
        "the whole sphere, and on its best half), and whether it was kept.",
        "",
        "### Tissue about the reference globes",
        "",
        "| Globe | Core median (HU) | Core in soft tissue window | "
        "Shell median (HU) | Shell in soft tissue window |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for side, tissue in zip(("right", "left"), each["reference_tissue"]):
        lines.append(
            f"| {side} | {tissue['core']['median_hu']} "
            f"| {tissue['core']['soft_tissue_share']} "
            f"| {tissue['shell']['median_hu']} "
            f"| {tissue['shell']['soft_tissue_share']} |"
        )
    lines += [
        "",
        "### Defacing",
        "",
        "| Block | Slices written | Written (ml) | Tissue written (ml) "
        "| Tissue kept in block (ml) | Written outside block "
        "| Right globe written | Left globe written | Against reference |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for label, measures in each["defacing"].items():
        globes = measures.get("reference_globes", [{}, {}])
        against = measures.get("against_reference")
        lines.append(
            f"| {label} | {measures['slices_written']} | {measures['written_ml']} "
            f"| {measures['tissue_written_ml']} "
            f"| {measures['tissue_kept_in_block_ml']} "
            f"| {measures['pixels_written_outside_block']} "
            f"| {_globe(globes[0])} | {_globe(globes[1])} "
            f"| {_against(against)} |"
        )
    lines += [
        "",
        "A globe's entry gives the share of its reference sphere written as "
        "air, and whether its anterior pole is. *Against reference* gives how "
        "far the block's plane lies ahead of the reference block's at the "
        "reference globes' midpoint, the angle between them, and how far its "
        "floor lies above the reference floor.",
    ]
    if each.get("renders"):
        lines += [
            "",
            "Renders: " + ", ".join(f"`{name}`" for name in each["renders"]) + ".",
        ]
    lines.append("")
    return lines


def _point(point: Sequence[float]) -> str:
    return "(" + ", ".join(str(v) for v in point) + ")"


def _ball(side: Mapping[str, Any] | None) -> str:
    if not side or "nearest_tested" not in side:
        return "none"
    ball = side["nearest_tested"]
    return (
        f"{ball['distance_mm']} mm off, r {ball['radius_mm']} mm, "
        f"{ball['outside']} / {ball['best_half']}, "
        f"{'kept' if ball['kept'] else 'not kept'}"
    )


def _globe(globe: Mapping[str, Any]) -> str:
    if not globe:
        return ""
    pole = "pole written" if globe["anterior_pole_written"] else "pole kept"
    return f"{globe['share_written']}, {pole}"


def _against(against: Mapping[str, Any] | None) -> str:
    if not against:
        return ""
    return (
        f"plane {against['plane_ahead_mm']} mm, {against['angle_degrees']}°, "
        f"floor {against['floor_above_mm']} mm"
    )
