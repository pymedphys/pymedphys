# Copyright (C) 2026 Matthew Jennings
# Licensed under the Apache License, Version 2.0.
"""Rebuild figures and tables for the completed 27 September 2026 audit.

Accept the original upload ZIP or the published results.json.gz. The accompanying
index.md is an authored interpretation; this script never overwrites it.
No gamma calculations are executed.
"""

import argparse
import csv
import gzip
import hashlib
import json
import statistics
import zipfile
from pathlib import Path

import gamma_scaling as study
import matplotlib
import numpy as np
from gamma_uncertainty_report import analyse

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, NullFormatter

RAW_SHA256 = "42c959f1757d4bdd156f83ce77ac2414b7108a2b1f14c962090643f89673688e"
ZIP_SHA256 = "4b56abc09d4f9fe3fb95c8edae37f05894059f84b24ac4cde203ca4e43b2fd1a"
COLOURS = ("#69a4b4", "#005d73", "#cc9674", "#a24343")
LABELS = ("Old PyMedPhys", "New PyMedPhys", "Old SciPy path", "New SciPy path")
VOLUMES = ("3d-sabr-1x", "3d-prostate-nodes-1x")
VOLUME_LABELS = ("SABR-like", "Prostate and nodes")


def read_source(source):
    if source.suffix == ".zip":
        if hashlib.sha256(source.read_bytes()).hexdigest() != ZIP_SHA256:
            raise ValueError("This dated evidence page requires the recorded upload")
        with zipfile.ZipFile(source) as archive:
            raw = archive.read("study/results.json")
            result = json.loads(raw)
            for name, expected in result["config"]["source_hashes"].items():
                if (
                    hashlib.sha256(archive.read(f"benchmark-source/{name}")).hexdigest()
                    != expected
                ):
                    raise ValueError(f"Runner hash mismatch: {name}")
            if analyse(result) != json.loads(archive.read("study/uncertainty.json")):
                raise ValueError("Recorded model analysis does not reproduce")
    else:
        raw = (
            gzip.decompress(source.read_bytes())
            if source.suffix == ".gz"
            else source.read_bytes()
        )
    if hashlib.sha256(raw).hexdigest() != RAW_SHA256:
        raise ValueError("Unexpected checkpoint; do not overwrite this dated study")
    return raw, json.loads(raw)


def times(result, case, variant):
    return {
        r["round"]: r["times"][0]
        for r in result["records"]
        if r["case"] == case and r["variant"] == variant and r.get("verified")
    }


def ratios(
    result, numerator_case, numerator_variant, denominator_case, denominator_variant
):
    top = times(result, numerator_case, numerator_variant)
    bottom = times(result, denominator_case, denominator_variant)
    if not top or top.keys() != bottom.keys():
        raise ValueError("Ratios require complete matched rounds")
    return np.array([top[r] / bottom[r] for r in sorted(top)])


def independent_checks(result, models):
    study.validate_records(result)
    if (
        not result["complete"]
        or len(result["comparisons"]) != 84
        or len(result["records"]) != 336
    ):
        raise ValueError("This publication requires all 84 planned groups")
    for record in result["records"]:
        if not record.get("verified") or record.get("error"):
            raise ValueError(
                "Review unverified records or error text before publishing"
            )
        if any(
            not origin.startswith("lib/pymedphys/") or ".." in Path(origin).parts
            for origin in record["origins"].values()
        ):
            raise ValueError("Unexpected import origin")
    # Scalar arithmetic is independent of the NumPy regression/report helper.
    for model in models["models"]:
        selected = [
            r
            for r in study.summarise(result)
            if r["profile"] == "global"
            and r["dimension"] == model["dimension"]
            and r["variant"] == model["variant"]
        ]
        x = [r["eligible_points"] / 1e6 for r in selected]
        y = [
            statistics.median(times(result, r["case"], r["variant"]).values())
            for r in selected
        ]
        origin = sum(a * b for a, b in zip(x, y)) / sum(a * a for a in x)
        mx, my = statistics.mean(x), statistics.mean(y)
        slope = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sum(
            (a - mx) ** 2 for a in x
        )
        np.testing.assert_allclose(
            [origin, slope, my - slope * mx],
            [
                model["origin_slope_seconds_per_million"],
                model["affine_slope_seconds_per_million"],
                model["affine_offset_seconds"],
            ],
            rtol=1e-11,
            atol=1e-12,
        )
    for row in study.speed_ratios(result):
        values = ratios(
            result,
            row["case"],
            row["revision"] + "-scipy",
            row["case"],
            row["revision"] + "-pymedphys",
        )
        np.testing.assert_allclose(
            [statistics.median(values), min(values), max(values)],
            [row["median_speed_ratio"], row["min_speed_ratio"], row["max_speed_ratio"]],
            rtol=0,
            atol=0,
        )


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def finish(fig, output, name, note, bottom=0.15):
    fig.text(
        0.08,
        bottom - 0.055,
        note,
        fontsize=9,
        color="#49515a",
        va="top",
        linespacing=1.5,
    )
    fig.savefig(output / f"{name}.png", dpi=170, facecolor="white")
    plt.close(fig)


def volume_times(result, output):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.9), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.17, right=0.95, top=0.76, bottom=0.26, wspace=0.26)
    fig.suptitle(
        "Absolute runtime on the two specified volume examples",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )
    for ax, case, label in zip(axes, VOLUMES, VOLUME_LABELS):
        for index, (variant, colour) in enumerate(zip(study.VARIANTS, COLOURS)):
            samples = list(times(result, case, variant).values())
            median = statistics.median(samples)
            y = 3 - index
            ax.barh(y, median, height=0.52, color=colour, alpha=0.85)
            ax.plot(samples, np.full(4, y), "|", color="#20252b", markersize=10)
            ax.text(max(samples) + 0.5, y, f"{median:.2f} s", va="center", fontsize=10)
        metadata = next(r for r in result["records"] if r["case"] == case)
        ax.set(
            title=f"{label}\n{metadata['points'] / 1e6:.2f} M total; {metadata['eligible_points']:,} eligible",
            xlabel="Seconds per warmed gamma call",
            xlim=(0, 29),
        )
        ax.set_yticks([3, 2, 1, 0], LABELS)
        ax.grid(axis="x", alpha=0.15)
        ax.set_axisbelow(True)
    finish(
        fig,
        output,
        "volume-times",
        "Bars: medians; ticks: all four measured rounds. Global 3% / 3 mm, 10% cutoff, four Numba threads.\nSynthetic fields at 1.25 mm (SABR-like) and 2.5 mm (prostate/nodal) spacing; these are not patient treatment plans.",
        bottom=0.20,
    )


def case_label(result, case):
    first = next(r for r in result["records"] if r["case"] == case)
    if case in VOLUMES:
        return VOLUME_LABELS[VOLUMES.index(case)]
    if first["profile"] == "global":
        return f"{first['dimension']}D global · {first['eligible_points']:,} eligible"
    geometry = result["config"]["cases"][case]["model_geometry"]
    return f"Diagnostic · {'compact' if geometry['width_scale'] < 0.5 else 'broad'}, {'base' if geometry['padding'] == 1 else 'padded'}, {geometry['difficulty']}"


def benefit(result, output):
    cases = sorted(
        {r["case"] for r in result["records"]},
        key=lambda c: (
            next(
                r["profile"] == "diagnostic"
                for r in result["records"]
                if r["case"] == c
            ),
            c,
        ),
    )
    rows = []
    fig, ax = plt.subplots(figsize=(11.6, 8.9))
    fig.subplots_adjust(left=0.41, right=0.91, top=0.88, bottom=0.17)
    for index, case in enumerate(cases):
        values = 100 * (
            1 - ratios(result, case, "current-pymedphys", case, "previous-pymedphys")
        )
        median = statistics.median(values)
        ax.hlines(index, min(values), max(values), color=COLOURS[1], alpha=0.5, lw=2)
        ax.plot(values, np.full(len(values), index), "|", color=COLOURS[1], alpha=0.5)
        ax.plot(median, index, "o", color=COLOURS[1])
        ax.text(47, index, f"{median:.1f}%", va="center", ha="left", fontsize=9)
        rows.append(
            {
                "case": case,
                "label": case_label(result, case),
                "rounds": len(values),
                "median_time_saved_percent": median,
                "min_time_saved_percent": min(values),
                "max_time_saved_percent": max(values),
            }
        )
    ax.set_yticks(range(len(cases)), [case_label(result, c) for c in cases])
    ax.invert_yaxis()
    ax.axvline(0, color="#777777", lw=0.8)
    ax.set(
        xlim=(-6, 51),
        xlabel="Time saved by the PR with the PyMedPhys interpolation path (%)",
    )
    ax.grid(axis="x", alpha=0.15)
    fig.suptitle(
        "Time saved by the PR across all 17 measured workloads",
        fontsize=15,
        fontweight="bold",
        y=0.965,
    )
    finish(
        fig,
        output,
        "pr-benefit",
        "Dots: median of matched-round percentage reductions; lines and ticks: observed ranges and individual rounds.\nAll 17 workload medians improve, by 13–31%. One small diagnostic round was 3.2% slower; ranges are not confidence intervals.",
    )
    write_csv(output / "pr-benefit.csv", rows)


def linear_models(result, analysis, output):
    rows = study.summarise(result)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.8))
    fig.subplots_adjust(left=0.09, right=0.97, top=0.76, bottom=0.25, wspace=0.28)
    for ax, dimension in zip(axes, (2, 3)):
        for variant, label, colour in zip(study.VARIANTS, LABELS, COLOURS):
            group = sorted(
                [
                    r
                    for r in rows
                    if r["dimension"] == dimension
                    and r["profile"] == "global"
                    and r["variant"] == variant
                ],
                key=lambda r: r["eligible_points"],
            )
            x = np.array([r["eligible_points"] for r in group])
            y = np.array([r["median_seconds"] for r in group])
            ax.errorbar(
                x,
                y,
                yerr=[
                    [r["median_seconds"] - r["min_seconds"] for r in group],
                    [r["max_seconds"] - r["median_seconds"] for r in group],
                ],
                fmt="s" if variant.startswith("previous") else "o",
                color=colour,
                capsize=3,
                markersize=4,
            )
            model = next(
                m
                for m in analysis["models"]
                if m["dimension"] == dimension and m["variant"] == variant
            )
            ax.plot(
                x,
                x / 1e6 * model["origin_slope_seconds_per_million"],
                "--" if variant.startswith("previous") else "-",
                color=colour,
                lw=1.5,
                label=label,
            )
        ax.set(
            xscale="log",
            yscale="log",
            xlabel="Eligible reference voxels (log scale)",
            ylabel="Warmed gamma runtime (seconds)",
            title=f"{dimension}D · {4 if dimension == 2 else 8} rounds per size",
        )
        ax.set_xticks(
            [5000, 10000, 20000, 50000]
            if dimension == 2
            else [2000, 5000, 10000, 20000, 50000]
        )
        ax.set_yticks(
            [0.02, 0.05, 0.1, 0.2, 0.5]
            if dimension == 2
            else [0.05, 0.1, 0.5, 1, 5, 10]
        )
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1000:g}k"))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.grid(alpha=0.17)
    fig.suptitle(
        "Scaling within one synthetic dose-field family",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        loc="upper center",
        bbox_to_anchor=(0.5, 0.92),
        ncol=4,
        frameon=False,
    )
    finish(
        fig,
        output,
        "linear-models",
        "Points and bars: medians and observed ranges. Lines: proportional fits t = bN; they are not universal runtime laws.\nThe 3D range is only 1,764–52,711 eligible voxels. Prediction errors on withheld sizes reach 18% for new PyMedPhys.",
        bottom=0.19,
    )


def transfer(analysis, output):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.3))
    fig.subplots_adjust(left=0.17, right=0.96, top=0.77, bottom=0.26, wspace=0.35)
    for ax, variant, colour, limit, title in zip(
        axes,
        ("current-pymedphys", "current-scipy"),
        (COLOURS[1], COLOURS[3]),
        (11, 60),
        ("New PyMedPhys", "New SciPy path"),
    ):
        for index, case in enumerate(VOLUMES):
            row = next(
                c
                for c in analysis["transfer_checks"]
                if c["case"] == case and c["variant"] == variant
            )
            for delta, key, fill, label in (
                (-0.16, "measured_median_seconds", colour, "Measured"),
                (0.16, "predicted_seconds", "#bac1c8", "Small-grid model prediction"),
            ):
                value = row[key]
                ax.barh(
                    index + delta,
                    value,
                    height=0.27,
                    color=fill,
                    label=label if index == 0 else None,
                )
                ax.text(
                    value + limit * 0.025,
                    index + delta,
                    f"{value:.2f}",
                    va="center",
                    fontsize=9,
                )
        ax.set_yticks(range(2), VOLUME_LABELS)
        ax.invert_yaxis()
        ax.set(title=title, xlabel="Seconds per warmed gamma call", xlim=(0, limit))
        ax.grid(axis="x", alpha=0.15)
        ax.set_axisbelow(True)
    fig.suptitle(
        "The small-grid model overpredicts the separate volume cases",
        fontsize=16,
        fontweight="bold",
        y=0.97,
    )
    fig.text(
        0.5,
        0.865,
        "Coloured bars: measured; grey bars: small-grid model prediction",
        ha="center",
        fontsize=10,
    )
    finish(
        fig,
        output,
        "model-transfer",
        "Predictions use the core 3D fit without fitting these volumes. Both eligible counts exceed the fitted range.\nThis tests field transfer and extrapolation together. Panels use different horizontal scales; all times are seconds.",
        bottom=0.19,
    )


def diagnostic_effects(result, output):
    effects = []
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.5), sharey=True)
    fig.subplots_adjust(left=0.09, right=0.97, top=0.80, bottom=0.28, wspace=0.18)
    for ax, variant, colour, title in zip(
        axes,
        ("current-pymedphys", "current-scipy"),
        (COLOURS[1], COLOURS[3]),
        ("New PyMedPhys", "New SciPy path"),
    ):
        for index, easy in enumerate((1, 3, 5, 7)):
            low_case, high_case = f"3d-diagnostic-{easy}x", f"3d-diagnostic-{easy + 1}x"
            lows, highs = (
                list(times(result, low_case, variant).values()),
                list(times(result, high_case, variant).values()),
            )
            low, high = statistics.median(lows) * 1000, statistics.median(highs) * 1000
            ax.vlines(index, low, high, color=colour, alpha=0.5, lw=1.5)
            for values, y, marker, fill in (
                (lows, low, "o", "white"),
                (highs, high, "D", colour),
            ):
                ax.errorbar(
                    index,
                    y,
                    yerr=[[y - min(values) * 1000], [max(values) * 1000 - y]],
                    fmt=marker,
                    color=colour,
                    markerfacecolor=fill,
                    capsize=4,
                    markersize=6,
                )
            values = ratios(result, high_case, variant, low_case, variant)
            median = statistics.median(values)
            ax.text(
                index,
                (low * high) ** 0.5,
                f"{median:.0f}×",
                ha="center",
                va="center",
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 2},
            )
            effects.append(
                {
                    "effect": "hard/easy",
                    "denominator_case": low_case,
                    "numerator_case": high_case,
                    "variant": variant,
                    "median_multiplier": median,
                    "minimum": min(values),
                    "maximum": max(values),
                }
            )
        ax.set(title=title, yscale="log", ylim=(1.2, 8000), xlim=(-0.5, 3.5))
        ax.set_xticks(
            range(4),
            [
                "Compact\nBase grid",
                "Broad\nBase grid",
                "Compact\nPadded grid",
                "Broad\nPadded grid",
            ],
            fontsize=9,
        )
        ax.grid(axis="y", alpha=0.17)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    axes[0].set_ylabel("Runtime (milliseconds, log scale)")
    fig.suptitle(
        "The same reference voxels can require very different search effort",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )
    fig.legend(
        [
            Line2D([], [], marker="o", markerfacecolor="white", color="#333333", lw=0),
            Line2D([], [], marker="D", color="#333333", lw=0),
        ],
        ["Easy mismatch", "Harder mismatch"],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.91),
        ncol=2,
        frameon=False,
    )
    finish(
        fig,
        output,
        "search-difficulty",
        "Ends: median runtime with observed range. Labels: median matched-round hard/easy multiplier, four rounds.\nReference dose, grid and eligible count are fixed within each comparison; only evaluation shift and dose scaling change.\nCompact fields: 293 eligible voxels; broad fields: 1,745. Global 3% / 3 mm, gamma capped at 2.",
        bottom=0.19,
    )

    fig, ax = plt.subplots(figsize=(10, 4.8))
    fig.subplots_adjust(left=0.24, right=0.95, top=0.77, bottom=0.28)
    for index, (a, b) in enumerate(((1, 5), (3, 7), (2, 6), (4, 8))):
        for offset, variant, colour, label in (
            (-0.12, "current-pymedphys", COLOURS[1], "New PyMedPhys"),
            (0.12, "current-scipy", COLOURS[3], "New SciPy path"),
        ):
            low_case, high_case = f"3d-diagnostic-{a}x", f"3d-diagnostic-{b}x"
            values = ratios(result, high_case, variant, low_case, variant)
            median = statistics.median(values)
            ax.hlines(index + offset, min(values), max(values), color=colour)
            ax.plot(
                median,
                index + offset,
                "o",
                color=colour,
                label=label if index == 0 else None,
            )
            effects.append(
                {
                    "effect": "padded/base",
                    "denominator_case": low_case,
                    "numerator_case": high_case,
                    "variant": variant,
                    "median_multiplier": median,
                    "minimum": min(values),
                    "maximum": max(values),
                }
            )
    ax.axvline(1, color="#777777", lw=1)
    ax.axvline(68479 / 20181, color="#777777", lw=1, linestyle="--")
    ax.text(
        0.90,
        0.96,
        "3.39× total grid voxels",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
    )
    ax.set_yticks(
        range(4),
        ["Compact · easy", "Broad · easy", "Compact · harder", "Broad · harder"],
    )
    ax.invert_yaxis()
    ax.set(xlim=(0.8, 3.6), xlabel="Runtime multiplier after padding the grid")
    ax.grid(axis="x", alpha=0.15)
    fig.suptitle(
        "Effect of adding below-cutoff grid voxels",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )
    fig.legend(
        *ax.get_legend_handles_labels(),
        loc="upper center",
        bbox_to_anchor=(0.5, 0.91),
        ncol=2,
        frameon=False,
    )
    finish(
        fig,
        output,
        "padding-effect",
        "Dots: median matched-round multiplier; lines: observed ranges across four rounds. Reference samples and eligible counts are preserved.\nTotal grid voxels increase from 20,181 to 68,479. Timing noise can put an individual multiplier below one.",
        bottom=0.19,
    )
    write_csv(output / "diagnostic-effects.csv", effects)


def generate(source, output):
    raw, result = read_source(source)
    analysis = analyse(result)
    independent_checks(result, analysis)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json.gz").write_bytes(gzip.compress(raw, mtime=0))
    write_json(output / "uncertainty.json", analysis)
    write_json(
        output / "provenance.json",
        {
            "source_archive_sha256": ZIP_SHA256,
            "uncompressed_results_sha256": RAW_SHA256,
            "started_utc": "2026-09-27T11:48:39.184589+00:00",
            "finished_utc": "2026-09-27T12:31:15.841769+00:00",
            "verified_groups": 84,
            "verified_timed_calls": 336,
            "workloads": 17,
            "revisions": result["config"]["revisions"],
            "host": result["host"],
            "versions": result["records"][0]["versions"],
            "thread_environment": result["records"][0]["thread_environment"],
            "numerical_checks": "Recorded full-array checks; source input arrays and hashes independently regenerated during publication review. Gamma calculations were not rerun.",
            "max_recorded_gamma_difference": max(
                c["algorithm_max_abs_difference"]
                for c in result["comparisons"].values()
            ),
            "pass_classification_disagreements": sum(
                c["algorithm_pass_disagreements"]
                for c in result["comparisons"].values()
            ),
        },
    )
    write_csv(output / "summary.csv", study.summarise(result))
    write_csv(output / "speed-ratios.csv", study.speed_ratios(result))
    write_csv(output / "model-coefficients.csv", analysis["models"])
    write_csv(
        output / "timings.csv",
        [
            {
                **{
                    k: r[k]
                    for k in (
                        "case",
                        "dimension",
                        "profile",
                        "points",
                        "eligible_points",
                        "round",
                        "variant",
                        "revision",
                        "started_utc",
                    )
                },
                "seconds": r["times"][0],
                "warmup_seconds": r["warmup_seconds"],
            }
            for r in result["records"]
        ],
    )
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    volume_times(result, output)
    benefit(result, output)
    linear_models(result, analysis, output)
    transfer(analysis, output)
    diagnostic_effects(result, output)
    print(
        f"Validated 84 groups; wrote six figures and reproducible evidence to {output}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.input, args.output)
