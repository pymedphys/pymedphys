# Copyright (C) 2026 Matthew Jennings
# Licensed under the Apache License, Version 2.0.
"""Rebuild the retained September 2026 workstation evidence, without timing.

python examples/gamma_scaling_evidence.py --input results.json --output evidence
The input may also be the published results.json.gz. No gamma calls are run.
"""

import argparse
import collections
import gzip
import hashlib
import json
import shutil
import statistics
import tempfile
from pathlib import Path

import numpy as np
from gamma_scaling import (
    PROFILE_LABELS,
    VARIANTS,
    paired_ratios,
    save_report,
    speed_ratios,
    summarise,
    validate_records,
)

RECORDED_SHA256 = "16ad7caba42e17d054759803e5d0b08acb8383ea98401e29debd5f4ba1dbd5dc"


def generate(source, output):
    raw = source.read_bytes()
    if source.suffix == ".gz":
        raw = gzip.decompress(raw)
    if hashlib.sha256(raw).hexdigest() != RECORDED_SHA256:
        raise ValueError(
            "This dated page describes the retained checkpoint only; use gamma_scaling.py --plot-only for another study"
        )
    result = json.loads(raw)
    validate_records(result)
    verified = [r for r in result["records"] if r.get("verified")]
    if not all(r["repeat_equality"] for r in result["records"] if r["status"] == "ok"):
        raise ValueError("A successful call did not reproduce its warm-up")
    if not verified:
        raise ValueError("No verified evidence")
    if len({json.dumps(r["host"], sort_keys=True) for r in verified}) != 1:
        raise ValueError("This workstation report requires one recorded host")
    # Public evidence contains synthetic fields, relative import origins and
    # hardware/software descriptions, not launch logs or local user paths.
    for record in result["records"]:
        for origin in record.get("origins", {}).values():
            if not origin.startswith("lib/pymedphys/") or ".." in Path(origin).parts:
                raise ValueError("Unexpected source origin; check it before publishing")
        if record.get("error"):
            raise ValueError("Review and redact diagnostic text before publication")

    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json.gz").write_bytes(gzip.compress(raw, mtime=0))
    with tempfile.TemporaryDirectory(prefix="gamma-evidence-") as directory:
        temporary = Path(directory)
        save_report(result, temporary)
        for path in [
            *temporary.glob("scaling-*.png"),
            temporary / "timings.csv",
            temporary / "summary.csv",
            temporary / "speed-ratios.csv",
            temporary / "speed-ratios.png",
        ]:
            shutil.copy2(path, output / path.name)

    rows = summarise(result)
    cases = sorted({r["case"] for r in verified})
    # Independently recalculate the paired ratios from individual records.
    # This catches changes to the aggregation helper used by the figures.
    reductions = {}
    for case in cases:
        for algorithm in ("pymedphys", "scipy"):
            selected = {
                v: {
                    r["round"]: r["times"][0]
                    for r in verified
                    if r["case"] == case and r["variant"] == v
                }
                for v in (f"previous-{algorithm}", f"current-{algorithm}")
            }
            old, new = selected.values()
            if result["config"]["repeats"] != 1 or old.keys() != new.keys():
                raise ValueError(
                    "This evidence page expects one timed call per matched round"
                )
            independent = [new[k] / old[k] for k in sorted(old)]
            np.testing.assert_array_equal(
                independent,
                paired_ratios(
                    result, case, f"current-{algorithm}", f"previous-{algorithm}"
                ),
            )
            reductions[case, algorithm] = 100 * (1 - statistics.median(independent))

        for revision in ("previous", "current"):
            times = {
                algorithm: {
                    r["round"]: r["times"][0]
                    for r in verified
                    if r["case"] == case and r["variant"] == f"{revision}-{algorithm}"
                }
                for algorithm in ("pymedphys", "scipy")
            }
            independent = [
                times["scipy"][r] / times["pymedphys"][r]
                for r in sorted(times["scipy"])
            ]
            np.testing.assert_array_equal(
                independent,
                paired_ratios(
                    result, case, f"{revision}-scipy", f"{revision}-pymedphys"
                ),
            )

    config = result["config"]
    status_counts = collections.Counter(r["status"] for r in result["records"])
    groups = len(result["comparisons"])
    maximum_error = max(
        c["algorithm_max_abs_difference"] for c in result["comparisons"].values()
    )
    disagreements = sum(
        c["algorithm_pass_disagreements"] for c in result["comparisons"].values()
    )
    first = verified[0]
    lines = [
        "# Gamma scaling: recorded workstation evidence",
        "",
        "**Partial study, recorded 26–27 September 2026.** These are saved workstation measurements from the original continuous-field scaling run, before the two-hour scheduler was introduced. They are distinct from the earlier fixed-grid notebook and from cloud measurements.",
        "",
        f"**{groups}/{result['expected_groups']} planned four-way groups are verified**, giving {len(verified)} plotted timed calls across {len(cases)} workloads. The run was stopped; the missing groups are listed in the raw record. In particular, no 3D local-criterion case was reached.",
        "",
        "## What the completed measurements show",
        "",
        f"At the largest 3D global grid (13,242,240 points), the PyMedPhys interpolation path used **{reductions['3d-global-100x', 'pymedphys']:.1f}% less time** across four paired rounds. The corresponding capped case used **{reductions['3d-cap2-100x', 'pymedphys']:.1f}% less time**, but only two rounds completed there, so its ordering is not fully balanced.",
        "",
        f"At the largest 2D grid (16,080,100 points), the global and local PyMedPhys paths used **{reductions['2d-global-100x', 'pymedphys']:.1f}%** and **{reductions['2d-local-100x', 'pymedphys']:.1f}%** less time respectively. These cases each have four paired rounds. The SciPy paths show much smaller, mixed changes; this run does not establish a consistent SciPy speed improvement.",
        "",
        "The table gives **median absolute seconds per complete warmed gamma call** at the largest available size. It excludes full warm-ups, imports, initial compilation and verification. A small number of rounds describes observed variation, not a confidence interval or a guarantee on another workstation.",
        "",
        "| Workload | Old PyMedPhys (s) | New PyMedPhys (s) | Old SciPy (s) | New SciPy (s) | Rounds |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for dimension in (2, 3):
        for profile in config["profiles"]:
            selected = [
                r
                for r in rows
                if r["dimension"] == dimension and r["profile"] == profile
            ]
            label = f"{dimension}D {PROFILE_LABELS[profile]}"
            if not selected:
                lines.append(
                    f"| {label} | Not measured | Not measured | Not measured | Not measured | 0 |"
                )
                continue
            largest = max(r["scale"] for r in selected)
            last = {r["variant"]: r for r in selected if r["scale"] == largest}
            lines.append(
                "| "
                + " | ".join(
                    [
                        label,
                        *[f"{last[v]['median_seconds']:.2f}" for v in VARIANTS],
                        str(next(iter(last.values()))["rounds"]),
                    ]
                )
                + " |"
            )
    lines += [
        "",
        "Percentages use `100 × (1 − median(new time / old time within each round))`. They need not equal percentages calculated by dividing the two absolute medians above. Ratios compare complete gamma calculations with a fixed SciPy version, not SciPy releases or an isolated interpolation kernel.",
        "",
        "## PyMedPhys versus SciPy",
        "",
        "**Speed ratio = PyMedPhys speed / SciPy speed = SciPy time / PyMedPhys time**, calculated within each matched round. A value of 5 means the PyMedPhys interpolation path completes gamma in approximately one fifth of the time. This compares full gamma calls with a fixed SciPy version and four Numba threads, not isolated interpolation kernels or SciPy releases.",
        "",
        "| Measured workloads | Old gamma source: speed ratio | New gamma source: speed ratio |",
        "| --- | ---: | ---: |",
    ]
    ratios = speed_ratios(result)
    for dimension, label in (
        (2, "2D: all three criteria"),
        (3, "3D: global and capped global only"),
    ):
        ranges = []
        for revision in ("previous", "current"):
            values = [
                r["median_speed_ratio"]
                for r in ratios
                if r["dimension"] == dimension and r["revision"] == revision
            ]
            ranges.append(f"{min(values):.2f}–{max(values):.2f}×")
        lines.append(f"| {label} | {' | '.join(ranges)} |")
    lines += [
        "",
        "These ranges span workload medians, not individual measurements or confidence intervals. The least favourable workload median was 1.42× for the old source and 1.74× for the new source, both on the smallest 2D global grid. Individual rounds varied more: minima were 1.27× and 1.33× respectively. No single multiplier describes both 2D and 3D.",
        "",
        "The largest fully repeated 3D global case gives a practical waiting-time example: **new PyMedPhys 3 min 28 s versus SciPy 18 min 5 s**, a median paired speed ratio of **5.19×**. Old PyMedPhys took 4 min 50 s versus SciPy 18 min 21 s, a ratio of 3.78×. The numerical comparisons passed. These are warmed-call times; first-use compilation and the audit's full warm-ups add to elapsed time.",
        "",
        "That case samples a **100 × 140 × 140 mm synthetic volume at approximately 0.53 mm spacing**. Its 13.2 million voxels are not evidence of clinical representativeness: dose extent, above-cutoff volume, gradients, criteria and mismatch affect gamma cost. The [completed uncertainty audit](../gamma-uncertainty-workstation/index.md) separately measures synthetic SABR-like and prostate/nodal workloads at specified 1.25 mm and 2.5 mm spacings, and tests runtime-model accuracy. Do not infer their timings from these curves or pool the two sessions.",
        "",
        "![Paired PyMedPhys to SciPy speed ratios across measured grid sizes](speed-ratios.png)",
        "",
        "Download [paired speed-ratio summaries](speed-ratios.csv). These ratios were independently recalculated from the raw observations when generating this page.",
        "",
        "## Coverage and numerical checks",
        "",
        "All 15 2D workloads (three criteria × five sizes) and all five 3D global workloads completed four rounds. The 3D capped workloads completed four rounds through 30× and two rounds at 100×. All five 3D local workloads are missing. Coverage therefore depends on the original scheduling order and computation cost; do not infer a single overall speed-up, impute missing timings or extrapolate a 3D local result.",
        "",
        f"The controller recorded exact old/new gamma-array equality for each interpolator in every plotted group, including NaN positions. All {status_counts['ok']} successfully timed calls matched their full warm-ups exactly. One successful call belongs to an unfinished group and is excluded from plots; the interrupted call supplies no timing. The maximum recorded PyMedPhys/SciPy absolute gamma difference was **{maximum_error:.3g}**, below `1e-10`; the recorded gamma-pass classification disagreement count was **{disagreements}**. These are numerical checks on synthetic fields, not clinical validation.",
        "",
        "The raw records and paired calculations were checked again when constructing this page. Large gamma arrays were removed by the original runner after their full comparisons; recreating those array comparisons requires rerunning the corresponding workloads.",
        "",
        "## Scaling curves",
        "",
        "Left panels show absolute seconds on logarithmic axes; right panels show matched-round new/old ratios. Bars span observed minimum to maximum. Each plotted point includes all four variants for the same completed rounds. Missing 3D local measurements remain explicitly blank.",
        "",
        "![Global gamma absolute times and paired ratios](scaling-global.png)",
        "",
        "![Capped global gamma absolute times and paired ratios](scaling-cap2.png)",
        "",
        "![Local gamma absolute times and paired ratios; no 3D measurements](scaling-local.png)",
        "",
        "## Source and reproducibility",
        "",
        f"Hardware: **{first['host']['processor']}**; {first['platform']}; Python {first['python'].split()[0]}. Packages: "
        + ", ".join(f"{k} {v}" for k, v in first["versions"].items())
        + ". Four Numba threads; OMP, OpenBLAS and MKL each limited to one thread. The fixed 1.5 GiB chunk budget is not a process memory limit.",
        "",
        f"Compared source: [previous `{config['revisions']['previous'][:12]}`](https://github.com/pymedphys/pymedphys/commit/{config['revisions']['previous']}) and [current `{config['revisions']['current'][:12]}`](https://github.com/pymedphys/pymedphys/commit/{config['revisions']['current']}). The raw record also contains worker/driver hashes, input/output hashes, import origins, thread settings and per-call timestamps.",
        "",
        "Same-host pairing controls hardware identity, but CPU affinity was not pinned and load, power state and thermal conditions were not controlled or recorded. This lengthy sequential run is not an independent repeat on several workstations. Within-round pairing and balanced ordering reduce some drift effects without eliminating them.",
        "",
        "The [study guide](../gamma-performance-study.md) describes the continuous synthetic fields and gamma criteria. The original schedule used five sizes (1, 3, 10, 30 and 100×), four rounds and case-first ordering. The newer audit calibrates a fixed matrix and adds two separate volume examples; it cannot retrospectively make this a complete study.",
        "",
        "Download the [raw checkpoint (gzip-compressed JSON)](results.json.gz), [individual timings](timings.csv) or [absolute timing summary](summary.csv). The checkpoint preserves all records, including the unverified and interrupted calls; only verified groups contribute to the figures.",
        "",
        f"SHA-256 of the uncompressed checkpoint: `{hashlib.sha256(raw).hexdigest()}`.",
        "",
        "Regenerate this page and its figures from the repository root, without running gamma:",
        "",
        "```console",
        "python examples/gamma_scaling_evidence.py --input lib/pymedphys/docs/contrib/info/gamma-scaling-workstation/results.json.gz --output gamma-scaling-evidence-rebuilt",
        "```",
    ]
    (output / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.input, args.output)


if __name__ == "__main__":
    main()
