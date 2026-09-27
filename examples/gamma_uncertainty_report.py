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

"""Analyse verified uncertainty-audit records without rerunning gamma."""

import argparse
import csv
import json
from pathlib import Path

import gamma_scaling as study
import numpy as np

BOOTSTRAPS = 4000
COLOURS = ("#a66828", "#004e64", "#9b83b3", "#a13646")
LABELS = ("Old PyMedPhys", "New PyMedPhys", "Old SciPy path", "New SciPy path")


def interval(samples):
    return [float(value) for value in np.percentile(samples, [2.5, 97.5])]


def paired_cube(result, cases):
    """Keep complete round blocks and all four implementations together."""
    lookup = {
        (r["case"], r["round"], r["variant"]): r
        for r in result["records"]
        if r.get("verified")
    }
    rounds = sorted(
        set.intersection(
            *[
                {
                    r["round"]
                    for r in result["records"]
                    if r["case"] == case and r.get("verified")
                }
                for case in cases
            ]
        )
    )
    if not rounds:
        return rounds, None, None
    metadata = [lookup[case, rounds[0], study.VARIANTS[0]] for case in cases]
    cube = np.array(
        [
            [
                [
                    np.median(lookup[case, round_index, variant]["times"])
                    for variant in study.VARIANTS
                ]
                for case in cases
            ]
            for round_index in rounds
        ]
    )
    return rounds, metadata, cube


def regression(x, y):
    """Return affine and proportional fits with whole-size hold-outs."""
    intercept, slope = np.linalg.lstsq(
        np.column_stack([np.ones(len(x)), x]), y, rcond=None
    )[0]
    origin = float(x @ y / (x @ x))
    affine_errors, origin_errors = [], []
    for index in range(len(x)):
        keep = np.arange(len(x)) != index
        a, b = np.linalg.lstsq(
            np.column_stack([np.ones(sum(keep)), x[keep]]), y[keep], rcond=None
        )[0]
        affine_errors.append(float(100 * ((a + b * x[index]) / y[index] - 1)))
        origin_errors.append(
            float(
                100
                * ((x[keep] @ y[keep]) / (x[keep] @ x[keep]) * x[index] / y[index] - 1)
            )
        )
    return {
        "affine_offset_seconds": float(intercept),
        "affine_slope_seconds_per_million": float(slope),
        "origin_slope_seconds_per_million": origin,
        "affine_leave_one_size_out_errors_percent": affine_errors,
        "origin_leave_one_size_out_errors_percent": origin_errors,
        "origin_max_abs_holdout_error_percent": max(map(abs, origin_errors)),
    }


def analyse(result):
    study.validate_records(result)
    # A changed input between rounds invalidates a repeatability estimate.
    for case in {r["case"] for r in result["records"] if r.get("verified")}:
        hashes = {
            r["input_sha256"]
            for r in result["records"]
            if r["case"] == case and r.get("verified")
        }
        if len(hashes) != 1:
            raise ValueError(f"Inputs changed between rounds for {case}")
    rng = np.random.default_rng(2066)
    analysis = {"models": [], "ratios": [], "diagnostic_models": [], "coverage": {}}
    for dimension in (2, 3):
        cases = sorted(
            {
                study.case_id(d, p, s)
                for d, p, s, _ in result["config"]["plan"]
                if d == dimension and p == "global"
            }
        )
        if not cases:
            continue
        rounds, metadata, cube = paired_cube(result, cases)
        analysis["coverage"][f"{dimension}d-global"] = {
            "sizes": len(cases),
            "common_rounds": rounds,
        }
        if len(rounds) < 4 or len(cases) < 3:
            continue
        x = np.array([r["eligible_points"] / 1e6 for r in metadata])
        order = np.argsort(x)
        x, cube = x[order], cube[:, order, :]
        if len(set(x)) != len(x) or min(x) <= 0:
            continue
        medians = np.median(cube, axis=0)
        boot_slopes = boot_affine = None
        if len(rounds) >= 8:
            # Resample complete rounds, preserving size and implementation pairing.
            indices = rng.integers(0, len(rounds), (BOOTSTRAPS, len(rounds)))
            boot_medians = np.median(cube[indices], axis=1)
            boot_slopes = np.einsum("s,bsv->bv", x, boot_medians) / (x @ x)
            inverse = np.linalg.pinv(np.column_stack([np.ones(len(x)), x]))
            boot_affine = np.einsum("ks,bsv->bkv", inverse, boot_medians)
        for index, variant in enumerate(study.VARIANTS):
            fitted = regression(x, medians[:, index])
            split = len(rounds) // 2
            early = x @ np.median(cube[:split, :, index], axis=0) / (x @ x)
            late = x @ np.median(cube[split:, :, index], axis=0) / (x @ x)
            analysis["models"].append(
                {
                    "dimension": dimension,
                    "variant": variant,
                    "sizes": len(x),
                    "rounds": len(rounds),
                    "min_eligible_points": round(min(x) * 1e6),
                    "max_eligible_points": round(max(x) * 1e6),
                    **fitted,
                    "origin_slope_repeat_interval_95": interval(boot_slopes[:, index])
                    if boot_slopes is not None
                    else None,
                    "affine_offset_repeat_interval_95": interval(
                        boot_affine[:, 0, index]
                    )
                    if boot_affine is not None
                    else None,
                    "affine_slope_repeat_interval_95": interval(
                        boot_affine[:, 1, index]
                    )
                    if boot_affine is not None
                    else None,
                    "later_half_slope_change_percent": float(100 * (late / early - 1)),
                }
            )
        for revision, py_index, scipy_index in (("previous", 0, 2), ("current", 1, 3)):
            py_slope = x @ medians[:, py_index] / (x @ x)
            scipy_slope = x @ medians[:, scipy_index] / (x @ x)
            analysis["ratios"].append(
                {
                    "dimension": dimension,
                    "revision": revision,
                    "ratio_of_origin_slopes": float(scipy_slope / py_slope),
                    "repeat_interval_95": interval(
                        boot_slopes[:, scipy_index] / boot_slopes[:, py_index]
                    )
                    if boot_slopes is not None
                    else None,
                }
            )
    for difficulty in ("easy", "hard"):
        cases = [
            case
            for case, spec in result["config"]["cases"].items()
            if spec.get("model_geometry", {}).get("difficulty") == difficulty
        ]
        if len(cases) != 4:
            continue
        rounds, metadata, cube = paired_cube(result, cases)
        if len(rounds) < 4:
            continue
        grid = np.array([r["points"] / 1e6 for r in metadata])
        eligible = np.array([r["eligible_points"] / 1e6 for r in metadata])
        matrix = np.column_stack([np.ones(4), grid, eligible])
        if np.linalg.matrix_rank(matrix) != 3:
            continue
        for index, variant in enumerate(study.VARIANTS):
            y = np.median(cube[:, :, index], axis=0)
            a, b_grid, b_eligible = np.linalg.lstsq(matrix, y, rcond=None)[0]
            analysis["diagnostic_models"].append(
                {
                    "difficulty": difficulty,
                    "variant": variant,
                    "rounds": len(rounds),
                    "offset_seconds": float(a),
                    "grid_seconds_per_million": float(b_grid),
                    "eligible_seconds_per_million": float(b_eligible),
                    "max_abs_fitted_error_percent": float(
                        max(abs(100 * (matrix @ [a, b_grid, b_eligible] / y - 1)))
                    ),
                    "interpretation": "Exploratory four-cell fit; no confidence interval or independent validation",
                }
            )
    analysis["transfer_checks"] = []
    for row in study.summarise(result):
        if row["profile"] not in ("sabr", "prostate-nodes") or row["rounds"] < 4:
            continue
        model = next(
            (
                m
                for m in analysis["models"]
                if m["dimension"] == 3 and m["variant"] == row["variant"]
            ),
            None,
        )
        if model:
            predicted = (
                model["origin_slope_seconds_per_million"] * row["eligible_points"] / 1e6
            )
            analysis["transfer_checks"].append(
                {
                    "case": row["case"],
                    "variant": row["variant"],
                    "measured_median_seconds": row["median_seconds"],
                    "predicted_seconds": predicted,
                    "prediction_error_percent": 100
                    * (predicted / row["median_seconds"] - 1),
                    "eligible_points_within_fitted_range": model["min_eligible_points"]
                    <= row["eligible_points"]
                    <= model["max_eligible_points"],
                }
            )
    return analysis


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_report(result, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    analysis = analyse(result)
    rows = study.summarise(result)
    study.write_json(output / "uncertainty.json", analysis)
    write_csv(output / "summary.csv", rows)
    write_csv(output / "speed-ratios.csv", study.speed_ratios(result))
    write_csv(output / "model-coefficients.csv", analysis["models"])
    timings = []
    for record in result["records"]:
        for repeat, seconds in enumerate(record.get("times", []), 1):
            timings.append(
                {
                    **{
                        key: record.get(key)
                        for key in (
                            "case",
                            "dimension",
                            "profile",
                            "points",
                            "eligible_points",
                            "round",
                            "variant",
                            "revision",
                            "started_utc",
                            "status",
                            "verified",
                        )
                    },
                    "repeat": repeat,
                    "seconds": seconds,
                }
            )
    write_csv(output / "timings.csv", timings)
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    fig.subplots_adjust(top=0.86, bottom=0.17, hspace=0.4, wspace=0.28)
    for column, dimension in enumerate((2, 3)):
        ax = axes[0, column]
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
            if not group:
                continue
            x = np.array([r["eligible_points"] / 1e6 for r in group])
            y = np.array([r["median_seconds"] for r in group])
            ax.errorbar(
                x,
                y,
                yerr=[
                    [r["median_seconds"] - r["min_seconds"] for r in group],
                    [r["max_seconds"] - r["median_seconds"] for r in group],
                ],
                fmt="o",
                color=colour,
                label=label,
                capsize=3,
                markersize=4,
            )
            model = next(
                (
                    m
                    for m in analysis["models"]
                    if m["dimension"] == dimension and m["variant"] == variant
                ),
                None,
            )
            if model:
                ax.plot(
                    x, x * model["origin_slope_seconds_per_million"], color=colour, lw=1
                )
        ax.set(
            title=f"{dimension}D global 3% / 3 mm",
            xscale="log",
            yscale="log",
            xlabel="Eligible reference voxels (millions)",
            ylabel="Warmed gamma time (s)",
        )
        ax.grid(alpha=0.2)
        if not any(
            r["dimension"] == dimension and r["profile"] == "global" for r in rows
        ):
            ax.text(
                0.5,
                0.5,
                "No verified measurements",
                transform=ax.transAxes,
                ha="center",
            )
    for ax, profiles, title in (
        (
            axes[1, 0],
            ("diagnostic",),
            "3D padding × field width × search difficulty",
        ),
        (
            axes[1, 1],
            ("sabr", "prostate-nodes"),
            "Specified larger volumes · global 3% / 3 mm",
        ),
    ):
        cases = [
            case
            for case, spec in result["config"]["cases"].items()
            if ("diagnostic" in profiles and "model_geometry" in spec)
            or spec.get("scenario") in profiles
        ]
        labels = []
        for case in cases:
            spec = result["config"]["cases"][case]
            if "model_geometry" in spec:
                geo = spec["model_geometry"]
                labels.append(
                    f"{'Padded' if geo['padding'] > 1 else 'Base'}\n{'Broad' if geo['width_scale'] > 0.5 else 'Small'}\n{geo['difficulty']}"
                )
            else:
                labels.append(spec["scenario"])
        for index, (variant, colour) in enumerate(zip(study.VARIANTS, COLOURS)):
            for position, case in enumerate(cases):
                row = next(
                    (r for r in rows if r["case"] == case and r["variant"] == variant),
                    None,
                )
                if row:
                    ax.errorbar(
                        position + (index - 1.5) * 0.16,
                        row["median_seconds"],
                        yerr=[
                            [row["median_seconds"] - row["min_seconds"]],
                            [row["max_seconds"] - row["median_seconds"]],
                        ],
                        fmt="o",
                        color=colour,
                        capsize=2,
                        markersize=4,
                    )
        ax.set(title=title, ylabel="Warmed gamma time (s)", yscale="log")
        ax.set_xticks(range(len(cases)), labels, fontsize=8)
        ax.grid(alpha=0.2, axis="y")
        if not any(r["profile"] in profiles for r in rows):
            ax.text(
                0.5,
                0.5,
                "No verified measurements",
                transform=ax.transAxes,
                ha="center",
            )
    handles = [
        Line2D([], [], marker="o", color=colour, label=label)
        for label, colour in zip(LABELS, COLOURS)
    ]
    fig.legend(
        handles,
        LABELS,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.93),
        ncol=4,
        frameon=False,
    )
    fig.suptitle(
        "Gamma runtime audit: repeatability and model transfer",
        fontsize=17,
        fontweight="bold",
        y=0.97,
    )
    fig.text(
        0.08,
        0.065,
        f"Verified groups: {len(result['comparisons'])}/{result['expected_groups']}. Points: medians; bars: observed ranges, not confidence intervals.\n"
        "Fitted lines use complete common rounds across all planned sizes. Missing groups remain missing; see the raw records.\n"
        "Bootstrap intervals in the report describe repeat-timing uncertainty on this workstation, conditional on sampled workloads.\n"
        "They do not bound prediction errors for new dose distributions. The SciPy package version is fixed.",
        fontsize=9,
    )
    fig.savefig(output / "uncertainty.png", dpi=160, facecolor="white")
    fig.savefig(output / "uncertainty.svg", facecolor="white")
    plt.close(fig)
    text = [
        "# Gamma runtime uncertainty audit",
        "",
        f"**{len(result['comparisons'])}/{result['expected_groups']} four-way groups verified.** Full completion: {result['complete']}.",
        "",
        "![Measured times and runtime models](uncertainty.png)",
        "",
        "Time is per complete warmed gamma call; setup, imports, full warm-ups and checking are excluded from these times but included in the audit deadline. Old/new refer to gamma source, with the same SciPy package version.",
        "",
        "## What the intervals mean",
        "",
        "Models minimise squared seconds with equal weight per grid-size median. N is millions of eligible reference voxels. The affine model is t = a + bN; the proportional model is t = bN. Neither establishes zero or negative physical overhead. Large cases strongly influence these fits.",
        "",
        "For at least eight complete common rounds, 95% percentile bootstrap intervals resample whole rounds (4,000 resamples, fixed seed), keeping grid sizes and all four implementations paired. These are exploratory repeat-timing intervals on one workstation, assuming exchangeable rounds. They are conditional on the sampled workloads and are not prediction intervals or guarantees of clinical transfer. With four rounds, only observed ranges are reported. Early/late changes and whole-size hold-out errors are separate checks, not confidence intervals.",
        "",
        "| Workload/path | Seconds per million eligible voxels | 95% repeat interval | Largest held-out size error | Later-half slope change |",
        "| --- | ---: | --- | ---: | ---: |",
    ]
    for model in analysis["models"]:
        bounds = model["origin_slope_repeat_interval_95"]
        formatted = (
            f"{bounds[0]:.3g}–{bounds[1]:.3g}" if bounds else "Insufficient rounds"
        )
        text.append(
            f"| {model['dimension']}D {model['variant']} | {model['origin_slope_seconds_per_million']:.3g} | {formatted} | {model['origin_max_abs_holdout_error_percent']:.1f}% | {model['later_half_slope_change_percent']:+.1f}% |"
        )
    text += [
        "",
        "## Fitted PyMedPhys / SciPy speed ratios",
        "",
        "These are ratios of proportional-model slopes, not medians of paired individual ratios. The paired workload ratios are in `speed-ratios.csv`.",
        "",
    ]
    for ratio in analysis["ratios"]:
        bounds = ratio["repeat_interval_95"]
        uncertainty = (
            f"95% repeat interval {bounds[0]:.3g}–{bounds[1]:.3g}"
            if bounds
            else "insufficient rounds for an interval"
        )
        text.append(
            f"- {ratio['dimension']}D {ratio['revision']}: **{ratio['ratio_of_origin_slopes']:.3g}×** ({uncertainty})."
        )
    text += [
        "",
        "## Predictions for the separate larger volumes",
        "",
        "The core 3D proportional model predicts these workloads without fitting their timings. All use global 3% / 3 mm and the same cutoff. A prediction outside the fitted eligible-count range tests extrapolation and field transfer together.",
        "",
        "| Case/path | Measured (s) | Predicted (s) | Prediction error | Eligible count within fitted range? |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for check in analysis["transfer_checks"]:
        text.append(
            f"| {check['case']} {check['variant']} | {check['measured_median_seconds']:.3g} | {check['predicted_seconds']:.3g} | {check['prediction_error_percent']:+.1f}% | {check['eligible_points_within_fitted_range']} |"
        )
    text += [
        "",
        "## Scope and next checks",
        "",
        "The diagnostic 2 × 2 × 2 design changes grid padding, field width and dose mismatch independently. Padding preserves the original coordinates and eligible reference voxels. Field width changes the volume and spatial distribution of dose; it is not a pure eligible-count intervention. All diagnostic cases use global 3% / 3 mm, gamma capped at 2, with fixed 6 mm Gaussian edge smoothing. Exploratory fits t = a + b_grid N_grid + b_eligible N_eligible are in `uncertainty.json`, separately by difficulty. Four cells per difficulty cannot validate a universal model; negative coefficients must not be treated as physical costs.",
        "",
        "The specified SABR-like and prostate/nodal examples are separate synthetic workloads. This design uses 3% / 3 mm for these volumes to match the fitted model; the coverage audit instead uses 3% / 2 mm. Neither is a clinical acceptance recommendation. No patient-dose generalisation is established. This focused audit does not replace the separate local-gamma coverage audit.",
        "",
        "Do not pool this run with the historical study or another host. A repeated invocation in a fresh directory tests session-to-session stability; compare it separately. If early/late slope changes are substantial, timing intervals may understate drift. No CPU affinity, power state or thermal stability is guaranteed by the launcher.",
        "",
        "## Files and provenance",
        "",
        "`results.json` retains all observations, including incomplete groups and numerical checks; `timings.csv` includes a verified flag. Only verified four-way groups enter `summary.csv`, `speed-ratios.csv` and the figures. `model-coefficients.csv` and `uncertainty.json` include coefficients, intervals, held-out errors, drift and diagnostic fits. `audit-plan.json` records the frozen workload definitions. The upload ZIP also contains exact runner source and the Python package environment.",
        "",
        f"Source revisions: `{result['config']['revisions']['previous']}` / `{result['config']['revisions']['current']}`; Numba threads: {result['config']['threads']}.",
        "",
        f"Host: {result['host']}",
        "",
    ]
    (output / "README.md").write_text("\n".join(text), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    args = parser.parse_args()
    save_report(
        json.loads((args.study / "results.json").read_text(encoding="utf-8")),
        args.study,
    )
