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

"""Render recorded PyMedPhys gamma comparisons; this module never runs gamma.

All numerical charts are derived from the JSON/NPZ files in a run directory.
Illustrative search diagrams are labelled separately from measurements. Missing
evidence is reported explicitly, and speed-up charts require verified agreement.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from html import escape
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable

import numpy as np


PALETTE = ("#22577A", "#B98527", "#368579", "#875783", "#6B7380", "#BC6544")
INK = "#243746"
MUTED = "#607080"
RED = "#AD4548"


@dataclass
class Figure:
    stem: str
    title: str
    caption: str
    alt: str
    files: list[Path]


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _numbers(values: Any, *, positive: bool = False) -> np.ndarray:
    if not isinstance(values, (list, tuple, np.ndarray)):
        return np.array([], dtype=float)
    result = [_number(value) for value in values]
    return np.array(
        [
            value
            for value in result
            if value is not None and (not positive or value > 0)
        ],
        dtype=float,
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")[:100] or "figure"


def _read_json(path: Path, notes: list[str]) -> dict:
    if not path.exists():
        notes.append(f"{path.name} was not available.")
        return {}
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        notes.append(f"Could not read {path.name}: {error}")
        return {}
    if not isinstance(result, dict):
        notes.append(f"{path.name} must contain a JSON object.")
        return {}
    return result


def _case_id(record: dict) -> str:
    return str(record.get("case", {}).get("id", "unidentified case"))


def _case_studies(case: dict) -> list[str]:
    memberships = case.get("studies", [])
    if not isinstance(memberships, list):
        memberships = []
    names = [case.get("study")] + memberships
    return list(dict.fromkeys(str(name) for name in names if name)) or ["unspecified"]


def _by_study(records: Iterable[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        for study in _case_studies(record.get("case", {})):
            result[study].append(record)
    return result


def _variants(record: dict) -> dict:
    variants = record.get("variants", {})
    return variants if isinstance(variants, dict) else {}


def _comparisons(record: dict, baseline: str) -> dict:
    """Normalise pairwise evidence; retain the original two-engine schema."""
    comparisons = record.get("comparisons")
    if isinstance(comparisons, dict):
        return comparisons
    candidates = [name for name in _variants(record) if name != baseline]
    if len(candidates) == 1 and isinstance(record.get("verification"), dict):
        return {
            candidates[0]: {
                "verification": record["verification"],
                "timing": record.get("timing", {}),
                "status": record.get("status"),
            }
        }
    return {}


def _verified(record: dict, comparison: dict) -> bool:
    verification = comparison.get("verification", {})
    allowed = _number(verification.get("allowed_pass_disagreements", 0))
    disagreements = _number(verification.get("pass_disagreements"))
    return (
        verification.get("valid") is True
        and verification.get("within_tolerance") is True
        and verification.get("same_nan_mask") is True
        and verification.get("all_finite_analysed") is True
        and verification.get("repeatable") is True
        and allowed is not None
        and disagreements is not None
        and 0 <= disagreements <= allowed
    )


def _paired_ratios(record: dict, comparison: dict) -> np.ndarray:
    # Never divide independent aggregate medians or infer pairing from unequal
    # lists: the runner records ratios after matching the actual rounds.
    if not _verified(record, comparison):
        return np.array([], dtype=float)
    return _numbers(comparison.get("timing", {}).get("paired_speedups"), positive=True)


def _stats(variant: dict) -> tuple[float, float, float] | None:
    values = _numbers(variant.get("seconds"), positive=True)
    if values.size == 0:
        return None
    return float(np.median(values)), float(np.min(values)), float(np.max(values))


def _groups(records: Iterable[dict], excluded: set[str]) -> list[list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        controls = {
            key: value
            for key, value in record.get("case", {}).items()
            if key not in excluded | {"id", "study", "studies", "notes"}
        }
        groups[json.dumps(controls, sort_keys=True)].append(record)
    return list(groups.values())


@contextmanager
def _style():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.labelsize": 9,
            "axes.labelcolor": INK,
            "text.color": INK,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#B9C3CB",
            "axes.grid": True,
            "grid.color": "#E4E9ED",
            "grid.linewidth": 0.6,
            "axes.axisbelow": True,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    ):
        yield plt


class _Report:
    def __init__(self, output_dir: Path):
        self.root = output_dir.resolve()
        self.notes: list[str] = []
        self.plan = _read_json(self.root / "plan.json", self.notes)
        self.environment = _read_json(self.root / "environment.json", self.notes)
        self.summary = _read_json(self.root / "summary.json", self.notes)
        self.test_data = (
            self.summary.get("test_data") is True or self.plan.get("test_data") is True
        )
        self.records = [
            r for r in self.summary.get("records", []) if isinstance(r, dict)
        ]
        declared_names = [
            name
            for name in self.summary.get("implementations", [])
            if isinstance(name, str)
        ]
        self.names = list(
            dict.fromkeys(
                declared_names + [name for r in self.records for name in _variants(r)]
            )
        )
        self.baseline = str(
            self.summary.get("baseline", self.plan.get("baseline", "baseline"))
        )
        if self.baseline not in self.names and self.names:
            self.baseline = self.names[0]
            self.notes.append(
                f"No matching baseline name was recorded; {self.baseline!r} is the display reference."
            )
        self.colours = {
            name: PALETTE[i % len(PALETTE)] for i, name in enumerate(self.names)
        }
        self.figures: list[Figure] = []
        self.figure_dir = self.root / "figures"
        self.figure_dir.mkdir(parents=True, exist_ok=True)

    def save(self, figure, stem: str, title: str, caption: str, alt: str) -> None:
        import matplotlib.pyplot as plt

        if self.test_data:
            figure.text(
                0.995,
                -0.025,
                "TEST DATA · fabricated renderer fixture",
                ha="right",
                va="top",
                fontsize=7,
                color=RED,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.95},
            )
        stem = _slug(stem)
        existing = {item.stem for item in self.figures}
        original, suffix = stem, 2
        while stem in existing:
            stem = f"{original}-{suffix}"
            suffix += 1
        files = []
        try:
            for extension in ("png", "svg", "pdf"):
                path = self.figure_dir / f"{stem}.{extension}"
                figure.savefig(path, dpi=160, bbox_inches="tight")
                files.append(path)
        finally:
            plt.close(figure)
        self.figures.append(Figure(stem, title, caption, alt, files))

    def coverage(self, plt) -> None:
        planned_cases = self.plan.get("cases", [])
        planned = self.summary.get("planned_cases", len(planned_cases))
        planned = max(int(_number(planned) or 0), len(planned_cases))
        counts = Counter(str(r.get("status", "unknown")) for r in self.records)
        missing = max(0, planned - len(self.records))
        if missing:
            counts["not attempted"] += missing
        if not counts:
            self.notes.append(
                "No case attempts were recorded; numerical charts are omitted."
            )
            return
        labels = list(counts)
        values = [counts[key] for key in labels]
        fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.0), layout="constrained")
        axes[0].barh(
            labels,
            values,
            color=[
                PALETTE[0] if key == "ok" else RED if key == "mismatch" else PALETTE[1]
                for key in labels
            ],
        )
        axes[0].invert_yaxis()
        axes[0].set(title="Case outcomes", xlabel="Number of cases")
        for i, value in enumerate(values):
            axes[0].text(value, i, f"  {value}", va="center")
        studies = list(
            dict.fromkeys(
                study for case in planned_cases for study in _case_studies(case)
            )
        )
        studies += [
            study
            for record in self.records
            for study in _case_studies(record.get("case", {}))
        ]
        studies = list(dict.fromkeys(studies))
        fig.set_size_inches(10.4, max(4.0, len(studies) * 0.24 + 1.5))
        starts = np.zeros(len(studies))
        for status in labels:
            amounts = []
            for study in studies:
                if status == "not attempted":
                    expected = sum(
                        study in _case_studies(case) for case in planned_cases
                    )
                    actual = sum(
                        study in _case_studies(record.get("case", {}))
                        for record in self.records
                    )
                    amount = max(0, expected - actual)
                else:
                    amount = sum(
                        str(record.get("status", "unknown")) == status
                        and study in _case_studies(record.get("case", {}))
                        for record in self.records
                    )
                amounts.append(amount)
            axes[1].barh(
                studies,
                amounts,
                left=starts,
                label=status,
                color=PALETTE[0]
                if status == "ok"
                else RED
                if status == "mismatch"
                else PALETTE[(labels.index(status) + 1) % len(PALETTE)],
            )
            starts += np.array(amounts)
        axes[1].set(title="Coverage by study", xlabel="Number of cases")
        axes[1].invert_yaxis()
        axes[1].legend(fontsize=8)
        self.save(
            fig,
            "coverage",
            "Coverage and incomplete work",
            "Timeouts, errors, memory limits, mismatches, and unattempted cases are separate outcomes. They are not zero runtimes or successful measurements. A case tagged for several studies contributes to each relevant study's coverage bar but once to the overall outcome count.",
            "; ".join(f"{key}: {value}" for key, value in counts.items()),
        )

    def planned_design(self, plt) -> None:
        cases = [case for case in self.plan.get("cases", []) if isinstance(case, dict)]
        if not cases:
            return
        studies = list(
            dict.fromkeys(study for case in cases for study in _case_studies(case))
        )
        fig, axes = plt.subplots(
            2,
            2,
            figsize=(11.4, max(8.6, len(studies) * 0.24 + 4)),
            layout="constrained",
        )
        dimensions = sorted(
            set(
                int(case["dimension"])
                for case in cases
                if _number(case.get("dimension")) in (1, 2, 3)
            )
        )
        for index, dimension in enumerate(dimensions):
            colour = PALETTE[index % len(PALETTE)]
            selected = [case for case in cases if case.get("dimension") == dimension]
            grid_points = [
                (float(case["n"]) ** dimension, studies.index(study))
                for case in selected
                if _number(case.get("n")) is not None and float(case["n"]) > 0
                for study in _case_studies(case)
            ]
            if grid_points:
                axes[0, 0].scatter(
                    [point[0] for point in grid_points],
                    [point[1] for point in grid_points],
                    color=colour,
                    label=f"{dimension}D",
                    s=22,
                    alpha=0.65,
                )
            settings = [
                (float(case["distance_mm_threshold"]), float(case["interp_fraction"]))
                for case in selected
                if _number(case.get("distance_mm_threshold")) is not None
                and _number(case.get("interp_fraction")) is not None
            ]
            if settings:
                axes[0, 1].scatter(
                    [point[0] for point in settings],
                    [point[1] for point in settings],
                    color=colour,
                    label=f"{dimension}D",
                    marker="o" if dimension == 2 else "x",
                    s=36,
                    alpha=0.7,
                )
        axes[0, 0].set_yticks(range(len(studies)), studies, fontsize=7)
        axes[0, 0].invert_yaxis()
        axes[0, 0].set(
            xlabel="Planned reference-grid points (nᵈ)",
            title="Grid-size coverage",
            xscale="log",
        )
        axes[0, 1].set(
            xlabel="Planned distance criterion (mm)",
            ylabel="Planned interpolation fraction",
            title="Distance and resolution controls",
        )
        for ax in axes[0]:
            handles, _ = ax.get_legend_handles_labels()
            if handles:
                ax.legend(fontsize=8)
        modes = []
        for dimension in dimensions:
            for mode in ("cutoff", "width"):
                values = [
                    _number(case.get("above_fraction_target"))
                    for case in cases
                    if case.get("dimension") == dimension
                    and case.get("fraction_mode") == mode
                ]
                values = [value for value in values if value is not None]
                if values:
                    label = f"{dimension}D · {mode}"
                    modes.append(label)
                    axes[1, 0].scatter(
                        values,
                        [len(modes) - 1] * len(values),
                        color=PALETTE[0] if mode == "cutoff" else PALETTE[1],
                        s=28,
                        alpha=0.75,
                    )
        axes[1, 0].set_yticks(range(len(modes)), modes)
        axes[1, 0].set(
            xlabel="Target eligible fraction (achieved fraction unmeasured)",
            title="Two distinct fraction controls",
            xlim=(-0.03, 1.03),
        )
        from matplotlib.ticker import PercentFormatter

        axes[1, 0].xaxis.set_major_formatter(PercentFormatter(1))
        caps = Counter(
            "uncapped" if case.get("max_gamma") is None else str(case["max_gamma"])
            for case in cases
            if "max_gamma" in case
        )
        if caps:
            axes[1, 1].bar(list(caps), list(caps.values()), color=PALETTE[0])
        axes[1, 1].set(
            xlabel="Planned maximum gamma setting",
            ylabel="Number of planned cases",
            title="Search-cap coverage",
        )
        fig.suptitle(
            "PLANNED DESIGN · controls and case counts, not measured performance",
            fontsize=12,
        )
        self.save(
            fig,
            "planned-design",
            "Planned experiment coverage",
            "All values in this figure come from plan.json. Repeated points represent repeated control combinations across other factors; they are not timing observations. Grid counts are calculated from the planned n and dimension, not from generated arrays. Target eligible fractions have not necessarily been achieved: cutoff and field-width studies are distinct and require recorded metadata to establish actual selection. Finite and uncapped gamma settings are counted separately.",
            "Planned grid-size coverage by study, distance/interpolation combinations, target eligible fractions split by cutoff and width controls, and case counts by gamma cap.",
        )

    def sweeps(self, plt) -> None:
        specifications = [
            (
                "grid",
                "Reference-grid points",
                lambda r: r.get("metadata", {}).get("total_points"),
                {"n"},
                True,
            ),
            (
                "eligible-fraction",
                "Achieved fraction above dose cutoff",
                lambda r: r.get("metadata", {}).get("eligible_fraction"),
                {"above_fraction_target", "lower_percent_dose_cutoff"},
                False,
            ),
            (
                "distance",
                "Distance criterion (coordinate units)",
                lambda r: r.get("case", {}).get("distance_mm_threshold"),
                {"distance_mm_threshold"},
                False,
            ),
            (
                "interpolation",
                "Interpolation fraction",
                lambda r: r.get("case", {}).get("interp_fraction"),
                {"interp_fraction"},
                False,
            ),
            (
                "gamma-cap",
                "Gamma cap (finite caps only)",
                lambda r: r.get("case", {}).get("max_gamma"),
                {"max_gamma"},
                False,
            ),
            (
                "shift",
                "Field displacement (mm)",
                lambda r: r.get("case", {}).get("shift_mm"),
                {"shift_mm"},
                False,
            ),
            (
                "dose-scale",
                "Evaluation dose scale",
                lambda r: r.get("case", {}).get("dose_scale"),
                {"dose_scale"},
                False,
            ),
            (
                "threads",
                "Requested threads",
                lambda r: r.get("case", {}).get("threads"),
                {"threads"},
                False,
            ),
            (
                "ram-budget",
                "Requested interpolation RAM budget (MiB)",
                lambda r: r.get("case", {}).get("ram_mib"),
                {"ram_mib"},
                True,
            ),
        ]
        studies = _by_study(self.records)
        for key, label, getter, excluded, logarithmic in specifications:
            useful = []
            for study, records in studies.items():
                records = [
                    r
                    for r in records
                    if _number(getter(r)) is not None
                    and any(_stats(v) for v in _variants(r).values())
                ]
                if len(set(_number(getter(r)) for r in records)) >= 2:
                    useful.append((study, records))
            for page in range(0, len(useful), 4):
                selected = useful[page : page + 4]
                fig, axes = plt.subplots(
                    len(selected),
                    1,
                    figsize=(10, 3.3 * len(selected)),
                    squeeze=False,
                    layout="constrained",
                )
                for ax, (study, records) in zip(axes[:, 0], selected):
                    labelled = set()
                    for group in _groups(records, excluded):
                        for name in self.names:
                            points = sorted(
                                (
                                    float(getter(r)),
                                    _stats(_variants(r).get(name, {})),
                                    r.get("status"),
                                )
                                for r in group
                                if _stats(_variants(r).get(name, {}))
                            )
                            if not points:
                                continue
                            x = np.array([p[0] for p in points])
                            centre = np.array([p[1][0] for p in points])
                            low = np.array([p[1][1] for p in points])
                            high = np.array([p[1][2] for p in points])
                            ax.errorbar(
                                x,
                                centre,
                                yerr=[centre - low, high - centre],
                                fmt="o-",
                                ms=4,
                                lw=1.2,
                                capsize=3,
                                color=self.colours[name],
                                label=name if name not in labelled else None,
                            )
                            labelled.add(name)
                            invalid = [
                                i for i, point in enumerate(points) if point[2] != "ok"
                            ]
                            if invalid:
                                ax.scatter(
                                    x[invalid],
                                    centre[invalid],
                                    marker="x",
                                    s=65,
                                    color=RED,
                                    zorder=4,
                                )
                    ax.set(
                        title=study,
                        xlabel=label,
                        ylabel="Warm runtime (seconds)",
                        yscale="log",
                    )
                    if logarithmic and all(float(getter(r)) > 0 for r in records):
                        ax.set_xscale("log")
                    if key == "eligible-fraction":
                        from matplotlib.ticker import PercentFormatter

                        ax.xaxis.set_major_formatter(PercentFormatter(1))
                    ax.legend()
                self.save(
                    fig,
                    f"runtime-{key}-{page // 4 + 1}",
                    f"Runtime versus {label.lower()}",
                    "Points show medians; whiskers show observed minimum–maximum repetition times, not confidence intervals. Lines join cases matching all remaining recorded case controls. Red crosses identify case-level incomplete or mismatching evidence; runtime is shown for transparency, not as a validated speed-up. Fields are synthetic.",
                    f"Runtime curves for {', '.join(study for study, _ in selected)}; horizontal variable: {label}.",
                )

    def speedups(self, plt) -> None:
        rows = []
        for record in self.records:
            for name, comparison in _comparisons(record, self.baseline).items():
                values = _paired_ratios(record, comparison)
                if values.size:
                    rows.append(
                        (
                            _case_id(record),
                            name,
                            float(np.median(values)),
                            float(values.min()),
                            float(values.max()),
                        )
                    )
        if not rows:
            self.notes.append(
                "No speed-up figure: no comparison had complete successful verification and recorded paired ratios."
            )
            return
        for start in range(0, len(rows), 28):
            selected = rows[start : start + 28]
            fig, ax = plt.subplots(
                figsize=(10.3, max(3.5, 0.3 * len(selected) + 1.6)),
                layout="constrained",
            )
            for y, (case, name, median, low, high) in enumerate(selected):
                ax.errorbar(
                    median,
                    y,
                    xerr=[[median - low], [high - median]],
                    fmt="o",
                    color=self.colours.get(name, PALETTE[1]),
                    capsize=3,
                )
            ax.set_yticks(
                range(len(selected)),
                [f"{case} · {name}" for case, name, *_ in selected],
                fontsize=8,
            )
            ax.invert_yaxis()
            ax.axvline(1, ls="--", color=MUTED)
            ax.set(
                xscale="log",
                xlabel=f"Paired runtime ratio: {self.baseline} / candidate (larger is faster)",
                title="Verified paired speed-ups",
            )
            self.save(
                fig,
                f"speedups-{start // 28 + 1}",
                "Verified paired speed-ups",
                "Dots are medians of within-round runtime ratios; whiskers are the observed ratio range, not confidence intervals. Only comparisons marked valid with successful repeatability, identical NaN masks, finite analysed outputs, and differences within the recorded gamma and pass-disagreement tolerances are included. The tolerances are recorded in summary.json; a nonzero allowed pass-disagreement count permits changed decisions. Baseline agreement is not independent scientific correctness.",
                f"Observed speed-up ranges for {len(selected)} validated case/version comparisons. The dashed line marks equal runtime.",
            )
        self.speedup_heatmaps(plt)

    def speedup_heatmaps(self, plt) -> None:
        specs = [
            (
                "grid-fraction",
                "Grid points",
                "Target eligible fraction",
                lambda r: r.get("metadata", {}).get("total_points"),
                lambda r: r.get("case", {}).get("above_fraction_target"),
                {"n", "above_fraction_target"},
            ),
            (
                "interpolation-distance",
                "Interpolation fraction",
                "Distance criterion",
                lambda r: r.get("case", {}).get("interp_fraction"),
                lambda r: r.get("case", {}).get("distance_mm_threshold"),
                {"interp_fraction", "distance_mm_threshold"},
            ),
        ]
        from matplotlib.colors import TwoSlopeNorm

        for key, xlabel, ylabel, xget, yget, excluded in specs:
            records = [
                r
                for r in self.records
                if _number(xget(r)) is not None and _number(yget(r)) is not None
            ]
            studies = _by_study(records)
            for study, cases in studies.items():
                for group_number, group in enumerate(_groups(cases, excluded), 1):
                    xs = sorted(set(float(xget(r)) for r in group))
                    ys = sorted(set(float(yget(r)) for r in group))
                    if len(xs) < 2 or len(ys) < 2:
                        continue
                    for name in self.names:
                        if name == self.baseline:
                            continue
                        cells = defaultdict(list)
                        for record in group:
                            comparison = _comparisons(record, self.baseline).get(
                                name, {}
                            )
                            ratios = _paired_ratios(record, comparison)
                            if ratios.size:
                                cells[
                                    (float(xget(record)), float(yget(record)))
                                ].append(float(np.median(ratios)))
                        # Ambiguous duplicate controls are not silently pooled.
                        values = np.full((len(ys), len(xs)), np.nan)
                        for (x, y), cell in cells.items():
                            if len(cell) == 1:
                                values[ys.index(y), xs.index(x)] = cell[0]
                        if not np.isfinite(values).any():
                            continue
                        logs = np.log2(values)
                        bound = max(0.25, float(np.nanmax(np.abs(logs))))
                        fig, ax = plt.subplots(figsize=(8.6, 5), layout="constrained")
                        cmap = plt.get_cmap("BrBG").with_extremes(bad="#E8EDF1")
                        im = ax.imshow(
                            logs,
                            origin="lower",
                            cmap=cmap,
                            norm=TwoSlopeNorm(vmin=-bound, vcenter=0, vmax=bound),
                            aspect="auto",
                        )
                        ax.set_xticks(range(len(xs)), [f"{x:g}" for x in xs])
                        ax.set_yticks(
                            range(len(ys)),
                            [
                                f"{y:.2%}" if key == "grid-fraction" else f"{y:g}"
                                for y in ys
                            ],
                        )
                        ax.set(
                            xlabel=xlabel,
                            ylabel=ylabel,
                            title=f"{study} · {name} vs {self.baseline}",
                        )
                        ax.grid(False)
                        ax.set_xticks(np.arange(-0.5, len(xs), 1), minor=True)
                        ax.set_yticks(np.arange(-0.5, len(ys), 1), minor=True)
                        ax.grid(which="minor", color="white", linewidth=0.6)
                        ax.tick_params(which="minor", bottom=False, left=False)
                        for y in range(len(ys)):
                            for x in range(len(xs)):
                                text_colour = (
                                    "white"
                                    if np.isfinite(logs[y, x])
                                    and abs(logs[y, x]) > 0.6 * bound
                                    else INK
                                )
                                ax.text(
                                    x,
                                    y,
                                    f"{values[y, x]:.2f}×"
                                    if np.isfinite(values[y, x])
                                    else "—",
                                    ha="center",
                                    va="center",
                                    fontsize=8,
                                    color=text_colour,
                                )
                        fig.colorbar(
                            im, ax=ax, label="log₂ paired speed-up (0 = equal runtime)"
                        )
                        achieved = [
                            _number(r.get("metadata", {}).get("eligible_fraction"))
                            for r in group
                        ]
                        achieved = [value for value in achieved if value is not None]
                        fraction_note = (
                            f" The fraction rows use the planned target; achieved fractions span {min(achieved):.2%}–{max(achieved):.2%} across this panel and are retained per case in summary.json. Cutoff and width controls are kept separate."
                            if key == "grid-fraction" and achieved
                            else ""
                        )
                        self.save(
                            fig,
                            f"heatmap-{key}-{study}-{group_number}-{name}",
                            "Two-factor verified speed-up map",
                            "Each populated cell is one case's median paired speed-up. Other case controls match within this panel. Grey cells are absent, unverified, or ambiguous duplicate measurements; they are not interpolated."
                            + fraction_note,
                            f"{name} speed-up over {self.baseline} across {xlabel.lower()} and {ylabel.lower()} in {study}.",
                        )

    def memory(self, plt) -> None:
        points = []
        for record in self.records:
            size = _number(record.get("metadata", {}).get("total_points"))
            if size is None or size <= 0:
                continue
            for name, variant in _variants(record).items():
                peak = _number(variant.get("peak_rss_bytes"))
                before = _number(variant.get("pre_gamma_rss_bytes"))
                if peak is not None and peak > 0:
                    points.append(
                        (
                            size,
                            peak / 2**20,
                            None if before is None else (peak - before) / 2**20,
                            name,
                        )
                    )
        if not points:
            self.notes.append(
                "No RSS figure: process memory measurements were not recorded."
            )
            return
        fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.3), layout="constrained")
        for name in self.names:
            selected = [p for p in points if p[3] == name]
            if not selected:
                continue
            axes[0].scatter(
                [p[0] for p in selected],
                [p[1] for p in selected],
                color=self.colours[name],
                label=name,
                alpha=0.8,
            )
            increments = [p for p in selected if p[2] is not None]
            axes[1].scatter(
                [p[0] for p in increments],
                [p[2] for p in increments],
                color=self.colours[name],
                label=name,
                alpha=0.8,
            )
        axes[0].set(
            title="Recorded process-tree peak",
            ylabel="Peak summed resident memory (MiB)",
            yscale="log",
        )
        axes[1].set(
            title="Peak relative to pre-gamma worker RSS",
            ylabel="Maximum peak − median pre-gamma RSS (MiB)",
        )
        for ax in axes:
            ax.set(xlabel="Reference-grid points", xscale="log")
            ax.legend()
        self.save(
            fig,
            "memory",
            "Resident memory and grid size",
            "Each point is a case/version measurement; points from different controls are not joined. Peak RSS is the sampled sum across the worker's process tree, including interpreters, inputs, caches, and PyMedPhys. Shared pages can be counted more than once; GPU memory is excluded. Sampling can miss short-lived peaks. The right panel subtracts median pre-gamma worker RSS from the maximum recorded tree peak across rounds: this mixes scopes and rounds and is only a diagnostic difference, not an allocation measurement. Inspect each round and sampling interval in the raw evidence. The interpolation RAM budget is not a total-process memory limit.",
            "Peak summed process-tree memory and its diagnostic difference from median pre-gamma worker RSS versus total reference-grid points.",
        )

    def accuracy(self, plt) -> None:
        rows = []
        for record in self.records:
            for name, comparison in _comparisons(record, self.baseline).items():
                evidence = comparison.get("verification", {})
                if evidence:
                    rows.append((_case_id(record), name, evidence))
        if not rows:
            self.notes.append(
                "No agreement figure: pairwise output verification was not recorded."
            )
            return
        for start in range(0, len(rows), 35):
            selected = rows[start : start + 35]
            fig, axes = plt.subplots(
                3, 1, figsize=(11, 8), sharex=True, layout="constrained"
            )
            for x, (_, name, evidence) in enumerate(selected):
                difference = _number(evidence.get("max_abs_difference"))
                pass_difference = _number(evidence.get("pass_disagreements"))
                if difference is not None:
                    axes[0].scatter(
                        x, difference, color=self.colours.get(name, PALETTE[1]), s=22
                    )
                if pass_difference is not None:
                    axes[1].bar(
                        x, pass_difference, color=RED if pass_difference else PALETTE[0]
                    )
                flags = [
                    evidence.get("same_nan_mask"),
                    evidence.get("all_finite_analysed"),
                    evidence.get("repeatable"),
                ]
                for y, flag in enumerate(flags):
                    axes[2].scatter(
                        x,
                        y,
                        marker="o" if flag is True else "x" if flag is False else "s",
                        color=PALETTE[0]
                        if flag is True
                        else RED
                        if flag is False
                        else MUTED,
                        s=24,
                    )
            axes[0].set(
                yscale="symlog",
                ylabel="Maximum |Δgamma|",
                title=f"Output agreement with {self.baseline}",
            )
            axes[1].set(ylabel="Pass disagreements")
            axes[2].set_yticks(
                range(3), ["Same NaN mask", "Finite analysed values", "Repeatable"]
            )
            axes[2].set_xticks(
                range(len(selected)),
                [f"{case}\n{name}" for case, name, _ in selected],
                rotation=75,
                ha="right",
                fontsize=6,
            )
            axes[2].set_ylim(-0.6, 2.6)
            self.save(
                fig,
                f"agreement-{start // 35 + 1}",
                "Numerical agreement and changed decisions",
                "All available comparisons are shown, including mismatches. Missing numerical evidence has no plotted value. Blue circles indicate verified true flags, red crosses false flags, and grey squares missing flags. Agreement with another PyMedPhys version is not independent validation of the gamma method. Inspect diagnostics.json for any separately recorded known-answer checks.",
                f"Maximum gamma differences, pass disagreement counts, NaN-mask agreement, analysed-value finiteness, and repeatability for {len(selected)} comparisons.",
            )

    def timing_stability(self, plt) -> None:
        for name in self.names:
            rows = [
                (r, _numbers(_variants(r).get(name, {}).get("seconds"), positive=True))
                for r in self.records
            ]
            rows = [(r, values) for r, values in rows if values.size >= 2]
            for start in range(0, len(rows), 30):
                selected = rows[start : start + 30]
                longest = max(len(values) for _, values in selected)
                normalised = np.full((len(selected), longest), np.nan)
                for i, (_, values) in enumerate(selected):
                    normalised[i, : len(values)] = values / np.median(values)
                fig, ax = plt.subplots(
                    figsize=(9, max(3.3, 0.25 * len(selected) + 1.8)),
                    layout="constrained",
                )
                cmap = plt.get_cmap("YlGnBu").with_extremes(bad="#E8EDF1")
                im = ax.imshow(
                    normalised,
                    cmap=cmap,
                    aspect="auto",
                    vmin=min(0.8, float(np.nanmin(normalised))),
                    vmax=max(1.2, float(np.nanmax(normalised))),
                )
                ax.set_xticks(range(longest), range(1, longest + 1))
                ax.set_yticks(
                    range(len(selected)),
                    [
                        _case_id(r)
                        + (
                            f" [{r.get('status', 'unknown')}]"
                            if r.get("status") != "ok"
                            else ""
                        )
                        for r, _ in selected
                    ],
                    fontsize=7,
                )
                ax.set(
                    xlabel="Recorded warm repetition number",
                    title=f"Timing stability · {name}",
                )
                ax.grid(False)
                fig.colorbar(im, ax=ax, label="Runtime / this case's median runtime")
                self.save(
                    fig,
                    f"timing-stability-{name}-{start // 30 + 1}",
                    "Timing variation across repetitions",
                    "Each row is normalised by its own median. Non-ok case status appears beside the case identifier; these observations are not verified speed-up claims. Repetition order is the recorded order for that PyMedPhys version; without timestamps this is not an elapsed-time thermal-drift analysis. Compilation/first calls are excluded from warm repetition arrays and shown separately when recorded.",
                    f"Warm repetition runtimes relative to each case's median for {name}; grey cells have no repetition.",
                )
        first_calls = [
            (r, name, _number(v.get("first_call_seconds")), _stats(v))
            for r in self.records
            for name, v in _variants(r).items()
        ]
        first_calls = [
            p for p in first_calls if p[2] is not None and p[2] > 0 and p[3] is not None
        ]
        if first_calls:
            fig, ax = plt.subplots(figsize=(8, 4.7), layout="constrained")
            for name in self.names:
                points = [p for p in first_calls if p[1] == name]
                if points:
                    ax.scatter(
                        [p[3][0] for p in points],
                        [p[2] for p in points],
                        color=self.colours[name],
                        label=name,
                    )
                    invalid = [p for p in points if p[0].get("status") != "ok"]
                    if invalid:
                        ax.scatter(
                            [p[3][0] for p in invalid],
                            [p[2] for p in invalid],
                            marker="x",
                            color=RED,
                            s=60,
                        )
            bounds = [p[2] for p in first_calls] + [p[3][0] for p in first_calls]
            ax.plot(
                [min(bounds), max(bounds)],
                [min(bounds), max(bounds)],
                "--",
                color=MUTED,
                lw=1,
            )
            ax.set(
                xscale="log",
                yscale="log",
                xlabel="Median warm runtime (seconds)",
                ylabel="Recorded first call (seconds)",
                title="First-call cost and warm runtime",
            )
            ax.legend()
            self.save(
                fig,
                "first-call",
                "First-call overhead",
                "Each repetition uses a fresh worker. The process-first call can include compilation, cache loading, and initialisation; a fresh process does not guarantee uncached JIT compilation. Inspect worker provenance. The dashed line is equal first-call and warm duration. Red crosses mark non-ok cases.",
                "Recorded first-call duration versus warm median duration for every available case and PyMedPhys version.",
            )

    def search_work(self, plt) -> None:
        measured = []
        for record in self.records:
            for name, variant in _variants(record).items():
                diagnostics = variant.get("diagnostics", {})
                count = _number(
                    diagnostics.get(
                        "total_candidate_queries",
                        variant.get("total_candidate_queries"),
                    )
                )
                stats = _stats(variant)
                if count is not None and count > 0 and stats:
                    measured.append((count, stats[0], name, record.get("status")))
        if measured:
            fig, ax = plt.subplots(figsize=(8.4, 4.8), layout="constrained")
            for name in self.names:
                points = [p for p in measured if p[2] == name]
                if points:
                    ax.scatter(
                        [p[0] for p in points],
                        [p[1] for p in points],
                        color=self.colours[name],
                        label=name,
                    )
                    invalid = [p for p in points if p[3] != "ok"]
                    if invalid:
                        ax.scatter(
                            [p[0] for p in invalid],
                            [p[1] for p in invalid],
                            marker="x",
                            color=RED,
                            s=60,
                        )
            ax.set(
                xscale="log",
                yscale="log",
                xlabel="Instrumented candidate queries",
                ylabel="Median warm runtime (seconds)",
                title="Runtime and actual recorded search work",
            )
            ax.legend()
            self.save(
                fig,
                "candidate-queries",
                "Measured candidate work",
                "Counts come from optional instrumentation and are not inferred from timings or theoretical complexity. Instrumentation overhead and scope must be checked in worker provenance; these counts alone do not imply identical interpolation or stopping behaviour. Red crosses mark non-ok cases.",
                "Warm runtime versus instrumented candidate-query counts for PyMedPhys versions with recorded counts.",
            )
        else:
            self.notes.append(
                "Actual candidate-query charts were omitted: instrumented counts were not recorded."
            )
        candidates = [
            r
            for r in self.records
            if any(
                v.get("diagnostics", {}).get("trace", v.get("trace"))
                for v in _variants(r).values()
            )
        ]
        for record in _representatives(candidates, limit=4):
            fig, axes = plt.subplots(
                3, 1, figsize=(9, 7.8), sharex=True, layout="constrained"
            )
            plotted = False
            for name, variant in _variants(record).items():
                trace = variant.get("diagnostics", {}).get(
                    "trace", variant.get("trace", [])
                )
                if not isinstance(trace, list):
                    continue
                for ax, key, label in zip(
                    axes,
                    ("active", "shell_points", "candidate_queries"),
                    ("Active reference points", "Points in shell", "Queries at shell"),
                ):
                    points = [
                        (_number(t.get("distance")), _number(t.get(key)))
                        for t in trace
                        if isinstance(t, dict)
                    ]
                    points = [
                        (x, y) for x, y in points if x is not None and y is not None
                    ]
                    if points:
                        ax.plot(
                            [p[0] for p in points],
                            [p[1] for p in points],
                            color=self.colours.get(name, PALETTE[0]),
                            label=name,
                        )
                        plotted = True
                    ax.set_ylabel(label)
                    ax.set_yscale("symlog")
            if not plotted:
                plt.close(fig)
                continue
            axes[0].set_title(f"Recorded search progression · {_case_id(record)}")
            axes[0].legend()
            axes[-1].set_xlabel("Recorded search radius (coordinate units)")
            self.save(
                fig,
                f"trace-{_case_id(record)}",
                "Search progression",
                "Optional recorded instrumentation for a representative case. These are observed traces, not a reconstruction from the shell algorithm. A differing trace can indicate changed work even when the final output agrees. Up to four cases are selected deterministically across dimensions and fields.",
                f"Active points, shell sizes, and candidate queries versus radius for {_case_id(record)}.",
            )

    def elapsed_timing(self, plt) -> None:
        points = []
        for record in self.records:
            for name, variant in _variants(record).items():
                stats = _stats(variant)
                if stats is None:
                    continue
                for run in variant.get("rounds", []):
                    if not isinstance(run, dict):
                        continue
                    seconds = _number(run.get("seconds"))
                    timestamp = _number(run.get("started_at"))
                    if timestamp is None and isinstance(run.get("started_at"), str):
                        try:
                            parsed = datetime.fromisoformat(
                                run["started_at"].replace("Z", "+00:00")
                            )
                            timestamp = (
                                parsed.timestamp()
                                if parsed.tzinfo is not None
                                else None
                            )
                        except ValueError:
                            pass
                    if timestamp is not None and seconds is not None and seconds > 0:
                        points.append(
                            (
                                timestamp,
                                seconds / stats[0],
                                name,
                                _number(run.get("order_position")),
                                record.get("status"),
                            )
                        )
        if not points:
            self.notes.append(
                "Elapsed-time drift chart omitted: per-round timestamps with explicit time zones were not recorded."
            )
            return
        first = min(point[0] for point in points)
        fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.3), layout="constrained")
        for name in self.names:
            selected = [point for point in points if point[2] == name]
            if not selected:
                continue
            axes[0].scatter(
                [(p[0] - first) / 60 for p in selected],
                [p[1] for p in selected],
                color=self.colours[name],
                label=name,
                s=20,
                alpha=0.75,
            )
            invalid = [point for point in selected if point[4] != "ok"]
            if invalid:
                axes[0].scatter(
                    [(p[0] - first) / 60 for p in invalid],
                    [p[1] for p in invalid],
                    marker="x",
                    color=RED,
                    s=40,
                )
            ordered = [point for point in selected if point[3] is not None]
            if ordered:
                axes[1].scatter(
                    [p[3] for p in ordered],
                    [p[1] for p in ordered],
                    color=self.colours[name],
                    label=name,
                    s=20,
                    alpha=0.75,
                )
                invalid_ordered = [point for point in ordered if point[4] != "ok"]
                if invalid_ordered:
                    axes[1].scatter(
                        [p[3] for p in invalid_ordered],
                        [p[1] for p in invalid_ordered],
                        marker="x",
                        color=RED,
                        s=40,
                    )
        for ax in axes:
            ax.axhline(1, ls="--", color=MUTED, lw=1)
            ax.set_ylabel("Warm time / this case's median")
            ax.legend(fontsize=8)
        axes[0].set(
            xlabel="Minutes since first recorded timed-call start",
            title="Timings across elapsed run time",
        )
        axes[1].set(
            xlabel="Recorded version order position",
            title="Timings and execution order",
        )
        self.save(
            fig,
            "timing-over-elapsed-time",
            "Elapsed time and execution-order effects",
            "Each observation is normalised by that PyMedPhys version's median for the same case. Timed-call start timestamps and recorded order positions provide context; these plots do not establish a causal thermal, cache, or ordering effect. Points can come from different cases and are not joined. The axis retains the runner's order-position numbering. Red crosses mark non-ok cases.",
            "Normalised warm runtimes versus elapsed timed-call-start time and recorded version order position.",
        )

    def atlas(self, plt) -> None:
        available = [
            r
            for r in self.records
            if any(v.get("representative_file") for v in _variants(r).values())
        ]
        for record in _representatives(available, limit=6):
            arrays = {}
            for name, variant in _variants(record).items():
                filename = variant.get("representative_file")
                if not isinstance(filename, str):
                    continue
                path = (self.root / filename).resolve()
                if not path.is_relative_to(self.root):
                    self.notes.append(
                        f"Ignored representative path outside the run directory for {_case_id(record)}."
                    )
                    continue
                try:
                    with np.load(path, allow_pickle=False) as data:
                        arrays[name] = {
                            key: np.asarray(data[key])
                            for key in data.files
                            if key
                            in {
                                "reference_slice",
                                "evaluation_slice",
                                "gamma_slice",
                                "finite_gamma_sample",
                                "gamma_hist_counts",
                                "gamma_hist_edges",
                            }
                        }
                except (OSError, ValueError, KeyError) as error:
                    self.notes.append(
                        f"Representative arrays unavailable for {_case_id(record)}, {name}: {error}"
                    )
            base = arrays.get(self.baseline, next(iter(arrays.values()), {}))
            if "reference_slice" not in base or "evaluation_slice" not in base:
                continue
            gamma_names = [
                name for name in self.names if "gamma_slice" in arrays.get(name, {})
            ]
            columns = 2 + len(gamma_names)
            fig, axes = plt.subplots(
                1,
                columns,
                figsize=(max(8, 3 * columns), 3.8),
                layout="constrained",
                squeeze=False,
            )
            doses = [base["reference_slice"], base["evaluation_slice"]]
            finite = np.concatenate([a[np.isfinite(a)].ravel() for a in doses])
            dose_limits = (
                (float(finite.min()), float(finite.max())) if finite.size else (0, 1)
            )
            gammas = [arrays[name]["gamma_slice"] for name in gamma_names]
            finite_gamma = (
                np.concatenate([a[np.isfinite(a)].ravel() for a in gammas])
                if gammas
                else np.array([])
            )
            gamma_limit = max(1, float(finite_gamma.max())) if finite_gamma.size else 1
            for ax, array, title, is_gamma in zip(
                axes[0],
                doses + gammas,
                ["Reference dose", "Evaluation dose"]
                + [f"Gamma · {name}" for name in gamma_names],
                [False, False] + [True] * len(gamma_names),
            ):
                array = np.squeeze(array)
                if array.ndim == 1:
                    ax.plot(array, color=PALETTE[0])
                    ax.set_xlabel("Slice sample index")
                    ax.set_ylim(
                        0 if is_gamma else dose_limits[0],
                        gamma_limit if is_gamma else dose_limits[1],
                    )
                elif array.ndim == 2:
                    im = ax.imshow(
                        np.ma.masked_invalid(array),
                        origin="lower",
                        cmap="magma" if is_gamma else "viridis",
                        vmin=0 if is_gamma else dose_limits[0],
                        vmax=gamma_limit if is_gamma else dose_limits[1],
                        interpolation="nearest",
                    )
                    fig.colorbar(
                        im,
                        ax=ax,
                        shrink=0.78,
                        label="Gamma" if is_gamma else "Dose (input units)",
                    )
                    ax.set(xlabel="Slice column index", ylabel="Slice row index")
                    ax.grid(False)
                else:
                    ax.text(
                        0.5,
                        0.5,
                        "No supported slice shape",
                        ha="center",
                        va="center",
                        transform=ax.transAxes,
                    )
                ax.set_title(title, fontsize=9)
            self.save(
                fig,
                f"atlas-{_case_id(record)}",
                f"Synthetic workload atlas · {_case_id(record)}",
                "Recorded synthetic reference/evaluation slices and available gamma slices. Dose scales are shared across the two input images; gamma scales are shared across PyMedPhys versions. Indices are shown because slice physical extents are not recorded with these arrays. Invalid values are masked. Slices cannot establish full-volume agreement.",
                f"Reference dose, evaluation dose, and gamma slices for synthetic case {_case_id(record)}.",
            )
            self.gamma_distribution(plt, record, arrays)
        if not available:
            self.notes.append(
                "Workload atlas omitted: no representative NPZ files were recorded."
            )

    def gamma_distribution(self, plt, record: dict, arrays: dict) -> None:
        fig, ax = plt.subplots(figsize=(8.3, 4.6), layout="constrained")
        plotted = False
        for name, data in arrays.items():
            counts, edges = data.get("gamma_hist_counts"), data.get("gamma_hist_edges")
            if (
                counts is not None
                and edges is not None
                and counts.ndim == edges.ndim == 1
                and len(edges) == len(counts) + 1
                and np.sum(counts) > 0
            ):
                ax.stairs(
                    counts / np.sum(counts),
                    edges,
                    color=self.colours.get(name, PALETTE[0]),
                    label=f"{name} · stored histogram",
                )
                plotted = True
            elif "finite_gamma_sample" in data:
                sample = _numbers(data["finite_gamma_sample"])
                if sample.size:
                    ax.hist(
                        sample,
                        bins=40,
                        weights=np.ones(sample.size) / sample.size,
                        histtype="step",
                        color=self.colours.get(name, PALETTE[0]),
                        label=f"{name} · stored sample",
                    )
                    plotted = True
        if not plotted:
            plt.close(fig)
            return
        ax.axvline(1, ls="--", color=MUTED)
        ax.set(
            xlabel="Gamma",
            ylabel="Fraction of represented values in each bin",
            title=f"Recorded gamma distributions · {_case_id(record)}",
        )
        ax.legend()
        self.save(
            fig,
            f"gamma-distribution-{_case_id(record)}",
            "Recorded gamma distribution",
            "Histogram counts are normalised within each represented dataset. Stored samples are explicitly labelled and need not represent the full population. Capped gamma produces a pile-up at the cap; skip-once-passed values are early witnesses, not minimised gamma. No full-population pass rate is inferred from these samples.",
            f"Available stored gamma histograms or finite-value samples for {_case_id(record)}; dashed line at gamma one.",
        )

    def illustrations(self, plt) -> None:
        fig = plt.figure(figsize=(10.6, 3.7), layout="constrained")
        ax1 = fig.add_subplot(131)
        ax2 = fig.add_subplot(132)
        ax3 = fig.add_subplot(133, projection="3d")
        for radius in (0.4, 0.8, 1.2):
            ax1.scatter([-radius, radius], [0, 0], s=22, color=PALETTE[0])
            theta = np.linspace(
                0, 2 * np.pi, max(8, round(24 * radius)), endpoint=False
            )
            ax2.scatter(
                radius * np.cos(theta), radius * np.sin(theta), s=12, color=PALETTE[0]
            )
        ax1.scatter([0], [0], color=PALETTE[1], s=45)
        ax1.set(
            title="1D: pairs at each radius",
            ylim=(-0.5, 0.5),
            yticks=[],
            xlabel="Position",
        )
        ax2.scatter([0], [0], color=PALETTE[1], s=45)
        ax2.set(
            title="2D: sampled circles",
            aspect="equal",
            xlabel="Position",
            ylabel="Position",
        )
        elevation = np.linspace(0.2, np.pi - 0.2, 8)
        for phi in elevation:
            theta = np.linspace(
                0, 2 * np.pi, max(5, round(24 * np.sin(phi))), endpoint=False
            )
            ax3.scatter(
                np.sin(phi) * np.cos(theta),
                np.sin(phi) * np.sin(theta),
                np.full(theta.shape, np.cos(phi)),
                s=8,
                color=PALETTE[0],
                alpha=0.8,
            )
        ax3.scatter([0], [0], [0], color=PALETTE[1], s=30)
        ax3.set(title="3D: sampled sphere", xticks=[], yticks=[], zticks=[])
        fig.suptitle(
            "ILLUSTRATION · radial sampling geometry, not measured work", fontsize=12
        )
        self.save(
            fig,
            "illustration-shell-geometry",
            "Illustration: radial search geometry",
            "Conceptual diagrams of shell sampling relevant to PyMedPhys. These points and densities are illustrative, not a trace of a measured version. A future branch may change its search method. Gold marks a reference point. Higher dimensional shell searches need more angular samples at a given spacing.",
            "Conceptual 1D pairs, 2D circular samples, and a 3D spherical sample cloud around a reference point.",
        )
        fig, axes = plt.subplots(1, 2, figsize=(10.2, 4), layout="constrained")
        radius = np.linspace(0.2, 3, 200)
        for dimension, colour in zip((1, 2, 3), PALETTE):
            axes[0].plot(radius, radius**dimension, label=f"{dimension}D", color=colour)
        axes[0].set(
            xlabel="Search radius / reference radius",
            ylabel="Relative candidate-volume model",
            title="Illustrative growth ∝ radiusᵈ",
        )
        axes[0].legend()
        axes[1].plot(
            radius, radius, color=PALETTE[0], label="Distance-only lower bound"
        )
        axes[1].axhline(1.6, color=PALETTE[1], label="Example current upper bound")
        axes[1].axvspan(1.6, 3, color=PALETTE[1], alpha=0.12)
        axes[1].set(
            xlabel="Radius / distance criterion",
            ylabel="Gamma bound",
            title="Why radial pruning can be valid",
        )
        axes[1].legend(fontsize=8)
        fig.suptitle(
            "ILLUSTRATION · mathematical models, not benchmark observations",
            fontsize=12,
        )
        self.save(
            fig,
            "illustration-growth-and-pruning",
            "Illustration: search growth and a stopping bound",
            "The left panel is the idealised rᵈ volume scaling at fixed sample density, normalised at r=1; it is not an operation count or timing prediction. The right panel shows gamma ≥ distance / distance criterion, so points beyond a known upper-bound radius cannot improve it. This geometric bound does not bound errors caused by finite sampling or interpolation.",
            "Idealised candidate growth in one, two, and three dimensions, and the distance-only lower bound crossing an example gamma upper bound.",
        )

    def write_index(self) -> list[Path]:
        raw_names = [
            name
            for name in (
                "plan.json",
                "config.resolved.json",
                "environment.json",
                "summary.json",
                "diagnostics.json",
                "summary.csv",
            )
            if (self.root / name).exists()
        ]
        raw_links = " · ".join(f'<a href="{name}">{name}</a>' for name in raw_names)
        status = str(self.summary.get("run_status", "no recorded run status"))
        title = "PyMedPhys gamma benchmark evidence"
        test_data = (
            self.summary.get("test_data") is True or self.plan.get("test_data") is True
        )
        if test_data:
            title = "TEST DATA — " + title
        parts = [
            '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{escape(title)}</title>",
            "<style>body{margin:0;background:#f4f6f8;color:#243746;font:16px/1.6 system-ui,sans-serif}main{max-width:1160px;margin:auto;padding:38px 28px}h1{font-size:32px;line-height:1.2}h2{font-size:22px}a{color:#22577a}figure{margin:32px 0;padding:22px;background:white;border:1px solid #dfe5e9;border-radius:8px}figure img{display:block;max-width:100%;height:auto;margin:auto}figcaption{max-width:1000px}nav ul{columns:2;column-gap:36px}.meta{color:#607080}.note{padding:15px 20px;background:#fff8e8;border-left:4px solid #b98527}table{border-collapse:collapse;font-size:14px;width:100%;background:white}td,th{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid #dfe5e9;overflow-wrap:anywhere}code{overflow-wrap:anywhere}@media(max-width:650px){main{padding:22px 14px}nav ul{columns:1}figure{padding:12px}}</style>",
            f"<main><h1>{escape(title)}</h1>",
            f'<p class="meta">Recorded run status: <strong>{escape(status)}</strong> · Baseline: {escape(self.baseline)}</p>',
            "<p>This offline report renders recorded evidence only. Fields are synthetic. Observed repetition ranges are not confidence intervals. Baseline agreement does not independently establish scientific correctness, and an incomplete comparison does not establish a speed-up.</p>",
            f"<p>Source evidence: {raw_links or 'No source files available.'}</p>",
        ]
        if test_data:
            parts.append(
                '<p class="note"><strong>TEST DATA:</strong> fabricated renderer-test inputs. These are not benchmark measurements.</p>'
            )
        if not self.records:
            parts.append(
                '<p class="note"><strong>No measurements recorded yet.</strong> Planned cases and mathematical illustrations are not benchmark results.</p>'
            )
        settings = self.summary.get("settings", {})
        if isinstance(settings, dict) and settings:
            parts.append(
                "<details><summary>Recorded run settings and acceptance controls</summary><table><tbody>"
                + "".join(
                    f"<tr><th>{escape(str(key))}</th><td>{escape(json.dumps(value, ensure_ascii=False))}</td></tr>"
                    for key, value in settings.items()
                )
                + "</tbody></table></details>"
            )
        if self.notes:
            parts.append(
                '<div class="note"><strong>Missing evidence and rendering notes</strong><ul>'
                + "".join(f"<li>{escape(note)}</li>" for note in self.notes)
                + "</ul></div>"
            )
        parts.append(
            '<nav aria-label="Figures"><h2>Figures</h2><ul>'
            + "".join(
                f'<li><a href="#{item.stem}">{escape(item.title)}</a></li>'
                for item in self.figures
            )
            + "</ul></nav>"
        )
        for item in self.figures:
            downloads = " · ".join(
                f'<a href="{path.relative_to(self.root).as_posix()}">{path.suffix[1:].upper()}</a>'
                for path in item.files
            )
            parts.append(
                f'<figure id="{item.stem}"><h2>{escape(item.title)}</h2><img src="figures/{item.stem}.png" alt="{escape(item.alt, quote=True)}" loading="lazy"><figcaption><p>{escape(item.caption)}</p><p>{downloads} · <a href="summary.json">Raw observations</a> · <a href="plan.json">Case definitions</a></p></figcaption></figure>'
            )
        parts.append(
            "<h2>Planned and attempted case inventory</h2><p>Unattempted cases show planned controls only. Expand a case to inspect every parameter.</p><table><thead><tr><th>Case and controls</th><th>Studies</th><th>Status</th><th>Recorded error</th></tr></thead><tbody>"
        )
        by_id = {_case_id(record): record for record in self.records}
        inventory = []
        seen_ids = set()
        for case in self.plan.get("cases", []):
            if not isinstance(case, dict):
                continue
            identifier = str(case.get("id", "unidentified case"))
            record = by_id.get(identifier, {"case": case, "status": "not attempted"})
            inventory.append(record)
            seen_ids.add(identifier)
        inventory.extend(
            record for record in self.records if _case_id(record) not in seen_ids
        )
        for record in inventory:
            case = record.get("case", {})
            controls = escape(json.dumps(case, indent=2, ensure_ascii=False))
            first_cell = f"<td><details><summary>{escape(_case_id(record))}</summary><pre><code>{controls}</code></pre></details></td>"
            parts.append(
                "<tr>"
                + first_cell
                + "".join(
                    f"<td>{escape(str(value))}</td>"
                    for value in (
                        ", ".join(_case_studies(case)),
                        record.get("status", "unknown"),
                        record.get("error", ""),
                    )
                )
                + "</tr>"
            )
        parts.append(
            "</tbody></table><p>Generated by the report renderer without importing PyMedPhys or calling gamma.</p></main></html>"
        )
        html_path = self.root / "index.html"
        html_path.write_text("\n".join(parts), encoding="utf-8")
        markdown = [
            f"# {title}",
            "",
            f"Recorded run status: **{status}**. Display baseline: **{self.baseline}**.",
            "",
            "[Open the offline figure report](index.html). Every figure is available as PNG, SVG, and PDF.",
            "",
            "Synthetic workloads; observed ranges are not confidence intervals. Same-method agreement is not independent scientific validation.",
            "",
            "Source files: "
            + ", ".join(f"[{name}]({name})" for name in raw_names)
            + ".",
            "",
        ]
        if test_data:
            markdown += [
                "**TEST DATA: fabricated renderer-test inputs, not benchmark measurements.**",
                "",
            ]
        if not self.records:
            markdown += [
                "**No measurements recorded yet.** Planned cases and mathematical illustrations are not benchmark results.",
                "",
            ]
        if self.notes:
            markdown += (
                ["## Missing evidence", ""]
                + [f"- {note}" for note in self.notes]
                + [""]
            )
        markdown += ["## Figures", ""]
        for item in self.figures:
            markdown += [
                f"### {item.title}",
                "",
                item.caption,
                "",
                f"![{item.alt}](figures/{item.stem}.png)",
                "",
            ]
        markdown_path = self.root / "report.md"
        markdown_path.write_text("\n".join(markdown), encoding="utf-8")
        manifest = self.root / "report_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "baseline": self.baseline,
                    "notes": self.notes,
                    "figures": [
                        {
                            "title": item.title,
                            "caption": item.caption,
                            "alt": item.alt,
                            "files": [
                                path.relative_to(self.root).as_posix()
                                for path in item.files
                            ],
                        }
                        for item in self.figures
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return [html_path, markdown_path, manifest] + [
            path for item in self.figures for path in item.files
        ]


def _representatives(records: list[dict], limit: int) -> list[dict]:
    """Select the largest available case from each dimension/field group first."""
    groups = defaultdict(list)
    for record in records:
        case = record.get("case", {})
        groups[(str(case.get("dimension", "?")), str(case.get("field", "?")))].append(
            record
        )
    selected = []
    for key in sorted(groups):
        ordered = sorted(
            groups[key],
            key=lambda r: (
                _number(r.get("metadata", {}).get("total_points")) or 0,
                _case_id(r),
            ),
        )
        selected.append(ordered[-1])
        if len(selected) >= limit:
            return selected
    for record in records:
        if record not in selected:
            selected.append(record)
        if len(selected) >= limit:
            break
    return selected


def build_report(output_dir: Path) -> list[Path]:
    """Create an offline, static evidence report from an existing run directory.

    Missing optional measurements omit their charts and leave an explicit note.
    No inputs are generated, PyMedPhys is not imported, and no benchmark is
    executed. Matplotlib is imported lazily with a non-interactive backend.
    """
    report = _Report(Path(output_dir))
    with _style() as plt:
        for method in (
            report.coverage,
            report.planned_design,
            report.sweeps,
            report.speedups,
            report.memory,
            report.accuracy,
            report.timing_stability,
            report.elapsed_timing,
            report.search_work,
            report.atlas,
            report.illustrations,
        ):
            method(plt)
    return report.write_index()
