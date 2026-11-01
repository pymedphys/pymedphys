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

"""Render the text detector's evaluation summary as CommonMark (D-056).

:func:`markdown` shows the counts of
:func:`~.text_evaluation.summarise`, and of
:func:`~.text_evaluation.assess` where given, and nothing else, so that the
page shows no more than the JSON does: a trade-off table of every point of
the grid, then the counts by stratum of each point shown in detail, every
point of a grid of ten or fewer and otherwise the first, with the others'
in the JSON.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def markdown(
    summary: Mapping[str, Any],
    assessment: Sequence[Mapping[str, Any]] | None = None,
    *,
    detailed: Sequence[int] | None = None,
) -> str:
    """Render a summary, and its assessment against criteria, as a page,
    with the counts by stratum of the points ``detailed``: by default every
    point of a grid of ten or fewer, otherwise the first."""
    detector = summary["detector"]
    method = detector.get("method", detector)
    variant = method.get("variant", {})
    plan = summary["plan"]
    split = summary["split"]
    benchmark = summary.get("tier") == "benchmark-only"
    lines = [
        "# Text detector evaluation",
        "",
        *(
            [
                "**Benchmark only**: this detector is measured for comparison "
                "and cannot be adopted, whatever its counts.",
                "",
            ]
            if benchmark
            else []
        ),
        "Each frame given to a text detector variant, each frame without "
        "text also with synthetic text burned in where a plan is given, and "
        "the boxes of every post-processing setting counted against the "
        "text's exact ink. Only counts are shown: no value, image, or case.",
        "",
        "| About | |",
        "| --- | --- |",
        f"| Format | `{summary['format']}` |",
        "| Software | "
        + ", ".join(
            f"{name} {version}" for name, version in summary["software"].items()
        )
        + " |",
        f"| Variant | `{_cell(variant.get('name', 'unknown'))}` |",
        f"| Model | {_model(method)} |",
        f"| Tier | {summary.get('tier', 'adoptable')} |",
        f"| Part evaluated | {split['evaluated']} |",
        f"| Cases by part | tuning {split['cases']['tuning']}, "
        f"held out {split['cases']['held-out']} |",
        f"| Frames without text measured as they are | "
        f"{'yes' if summary['negatives'] else 'no'} |",
        "",
        f"The split: {split['rule']}",
        "",
    ]
    if plan is not None:
        lines += [
            "| Injected text | Drawn from |",
            "| --- | --- |",
            *(
                f"| {name.replace('_', ' ').capitalize()} | "
                f"{_cell(', '.join(str(each) for each in values))} |"
                for name, values in plan.items()
                if isinstance(values, list)
            ),
            f"| Texts per frame | {plan['texts']} |",
            f"| Seed | {plan['seed']} |",
            "",
        ]
    lines += _collections(summary["collections"])
    lines += _codes("Frames by IOD", summary["frames"], "Frames")
    lines += _codes("Frames not read", summary["skipped"], "Files or volumes")
    lines += _codes("Texts not placed", summary["not_placed"], "Texts")
    lines += _codes("Frames not injected", summary["not_injected"], "Frames")
    lines += _trade_off(summary["points"], assessment)
    lines += _unknown(summary["points"])
    points = summary["points"]
    shown = set(
        (range(len(points)) if len(points) <= 10 else (0,))
        if detailed is None
        else detailed
    )
    for point in points:
        if point["index"] in shown:
            lines += _detail(point)
    if len(shown) < len(points):
        lines += [
            "The other points' counts by stratum are in the JSON summary.",
            "",
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


_ZONE_KINDS = (
    ("negative", "Frames without text"),
    ("away", "Away from text"),
    ("unknown", "Where text is unknown, as read"),
    ("unknown-away", "Where text is unknown, away from injected text"),
)


def _unknown(points: Sequence[Mapping[str, Any]]) -> list[str]:
    """Regions on frames whose text is unknown, which may be text, so are
    shown apart from false positives; nothing where there are none."""
    if not any(
        point["text_unknown"]["frames"]
        or point["text_unknown_away_from_injected"]["frames"]
        for point in points
    ):
        return []
    lines = [
        "## Where text is unknown",
        "",
        "Frames whose text as read is unknown, such as a clinic's RT Images: "
        "their regions may be text, so they are not false positives.",
        "",
        "| Point | Frames | With a region | Wilson | Regions | Tissue blacked out "
        "| With injected text | With a region away from it |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for point in points:
        as_read = point["text_unknown"]
        away = point["text_unknown_away_from_injected"]
        lines.append(
            f"| {point['index']} | {as_read['frames']} | {_share(as_read['share'])} "
            f"| {_interval(as_read['wilson'])} | {as_read['regions']} "
            f"| {_share(as_read['tissue_blacked_out'], 3)} | {away['frames']} "
            f"| {_share(away['share'])} |"
        )
    return [*lines, ""]


def _model(method: Mapping[str, Any]) -> str:
    model = method.get("model")
    rule = method.get("rule")
    if isinstance(rule, Mapping) and isinstance(model, Mapping):
        return f"{_model(model)} with rule `{_cell(str(rule.get('rule')))}`"
    named = (
        f"{_cell(str(model['name']))}, "
        if isinstance(model, Mapping) and "name" in model
        else ""
    )
    if "model_sha256" in method:
        return f"{named}SHA-256 `{method['model_sha256']}`"
    if "rule" in method:
        return f"rule `{_cell(str(method['rule']))}`"
    if "network" in method:
        return f"{named}test network `{_cell(str(method['network']))}`"
    if "runner" in method:
        return f"{named}runner `{_cell(str(method['runner']))}`"
    return "unknown"


def _collections(collections: Mapping[str, Any]) -> list[str]:
    if not collections:
        return ["Collections: none.", ""]
    return [
        "| Collection | Cases | Evaluated | Crashed |",
        "| --- | ---: | ---: | --- |",
        *(
            f"| {_cell(name)} | {entry['cases']} | {entry['evaluated']} | "
            + (
                ", ".join(
                    f"`{_cell(site)}` {count}"
                    for site, count in entry["crashed"].items()
                )
                or "none"
            )
            + " |"
            for name, entry in collections.items()
        ),
        "",
    ]


def _codes(title: str, counts: Mapping[str, int], noun: str) -> list[str]:
    if not counts:
        return [f"{title}: none.", ""]
    return [
        f"| {title} | {noun} |",
        "| --- | ---: |",
        *(f"| `{_cell(code)}` | {count} |" for code, count in counts.items()),
        "",
    ]


def _varying(points: Sequence[Mapping[str, Any]]) -> list[str]:
    """The post-processing settings that differ between points."""
    if not points:
        return []
    names = list(points[0]["post_processing"])
    return [
        name
        for name in names
        if len({repr(point["post_processing"][name]) for point in points}) > 1
    ]


def _trade_off(
    points: Sequence[Mapping[str, Any]],
    assessment: Sequence[Mapping[str, Any]] | None,
) -> list[str]:
    varying = _varying(points)
    met = {each["index"]: each for each in assessment or ()}
    header = [
        "Point",
        *(name.replace("_", " ") for name in varying),
        "Texts",
        "Fully covered",
        "Wilson",
        "Bootstrap",
        "Frames without text",
        "With a region",
        "Wilson",
        "Bootstrap",
        "Tissue blacked out",
        "Regions away from text",
    ]
    if assessment is not None:
        header.append("Meets the criteria")
    lines = [
        "## Trade-off",
        "",
        "Fully covered: texts all of whose ink the boxes cover. With a region: "
        "frames without text given at least one box. Intervals are 95%: "
        "Wilson's for the share, and a bootstrap that resamples cases.",
        "",
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---:" for _ in header) + " |",
    ]
    for point in points:
        sensitivity = point["sensitivity"]
        negatives = point["false_positives"]
        cells = [
            str(point["index"]),
            *(_setting(point["post_processing"][name]) for name in varying),
            str(sensitivity["texts"]),
            _share(sensitivity["share"]),
            _interval(sensitivity["wilson"]),
            _interval(sensitivity.get("bootstrap")),
            str(negatives["frames"]),
            _share(negatives["share"]),
            _interval(negatives["wilson"]),
            _interval(negatives.get("bootstrap")),
            _share(negatives["tissue_blacked_out"], 3),
            str(point["away_from_text"]["regions"]),
        ]
        if assessment is not None:
            entry = met.get(point["index"])
            cells.append(
                "none" if entry is None else ("yes" if entry["meets"] else "no")
            )
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    if assessment:
        for entry in assessment:
            if entry["failures"]:
                lines += [
                    f"Point {entry['index']} fails {len(entry['failures'])} criteria, "
                    "the first of them:",
                    "",
                    *(f"- {_cell(each)}" for each in entry["failures"][:20]),
                    "",
                ]
    return lines


def _detail(point: Mapping[str, Any]) -> list[str]:
    groupings = sorted(point["by"], key=lambda name: name != "iod")
    lines = [f"## Point {point['index']} by stratum", ""]
    zones = point["zones"]
    lines += [
        "| Regions by zone | Corner | Edge | Centre |",
        "| --- | ---: | ---: | ---: |",
        *(
            f"| {label} | {zones[kind]['corner']} | {zones[kind]['edge']} "
            f"| {zones[kind]['centre']} |"
            for kind, label in _ZONE_KINDS
        ),
        "",
    ]
    for grouping in groupings:
        rows = point["by"][grouping]
        names = grouping.split("+")
        # A grouping by a text's dimension counts only texts.
        per_frame = all("false_positives" in row for row in rows)
        lines += [
            f"By {', '.join(name.replace('_', ' ') for name in names)}:",
            "",
            "| "
            + " | ".join(name.replace("_", " ").capitalize() for name in names)
            + " | Texts | Fully covered | Wilson | Partly covered | Missed |"
            + (
                " Frames without text | With a region | Tissue blacked out |"
                if per_frame
                else ""
            ),
            "| "
            + " | ".join("---" for _ in names)
            + " | ---: | ---: | ---: | ---: | ---: |"
            + (" ---: | ---: | ---: |" if per_frame else ""),
        ]
        for row in rows:
            sensitivity = row["sensitivity"]
            line = (
                "| "
                + " | ".join(_cell(str(row["value"][name])) for name in names)
                + f" | {sensitivity['texts']} | {_share(sensitivity['share'])} "
                f"| {_interval(sensitivity['wilson'])} "
                f"| {sensitivity['partly_covered']} | {sensitivity['missed']} |"
            )
            if per_frame:
                negatives = row["false_positives"]
                line += (
                    f" {negatives['frames']} | {_share(negatives['share'])} "
                    f"| {_share(negatives['tissue_blacked_out'], 3)} |"
                )
            lines.append(line)
        lines.append("")
    return lines


def _setting(value: object) -> str:
    if isinstance(value, list):
        return _cell(" + ".join(str(each) for each in value))
    return _cell(f"{value:g}" if isinstance(value, float) else str(value))


def _share(value: float | None, digits: int = 1) -> str:
    return "none" if value is None else f"{value:.{digits}%}"


def _interval(value: Sequence[float] | None) -> str:
    return "none" if value is None else f"{value[0]:.1%} to {value[1]:.1%}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
