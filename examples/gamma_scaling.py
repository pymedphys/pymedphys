# Copyright (C) 2026 Matthew Jennings
# Licensed under the Apache License, Version 2.0.
"""Four-way gamma scaling study, with checkpointed results and logarithmic plots.

python examples/gamma_scaling.py --output gamma-scaling-run
python examples/gamma_scaling.py --resume gamma-scaling-run
python examples/gamma_scaling.py --merge parts --output gamma-scaling-combined

The default study covers 2D/3D, global 3%/3 mm, capped global and local 2%/2 mm,
five grid sizes through 100 times the baseline points, and four balanced rounds.
Each process performs one full untimed warm-up and one timed call by default.
Allow several hours. Git and the dependencies in gamma-scaling-requirements.txt
are required. See the performance notebook for interpretation and limitations.
"""

import argparse
import csv
import datetime
import hashlib
import itertools
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from gamma_performance import checked_checkout, machine_description

PREVIOUS = "866f83edad8586a42a739094e488f45242b72c95"
BASE_SHAPES = {2: (401, 401), 3: (41, 57, 57)}
VARIANTS = (
    "previous-pymedphys",
    "current-pymedphys",
    "previous-scipy",
    "current-scipy",
)
# Williams design: each variant occupies each position once across four rounds.
ORDERS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))
PROFILE_LABELS = {
    "global": "Global 3% / 3 mm",
    "cap2": "Global 3% / 3 mm, cap 2",
    "local": "Local 2% / 2 mm",
}


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def shape_for(dimension, scale):
    if dimension not in BASE_SHAPES or not 0 < scale <= 100:
        raise ValueError("Use 2D/3D and point multipliers in (0, 100]")
    shape = tuple(
        max(2, int(n * scale ** (1 / dimension))) for n in BASE_SHAPES[dimension]
    )
    if np.prod(shape) > 100 * max(np.prod(s) for s in BASE_SHAPES.values()):
        raise ValueError("Grid exceeds 100 times the former maximum point count")
    return shape


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def case_id(dimension, profile, scale):
    return f"{dimension}d-{profile}-{scale:g}x"


def compare_arrays(paths, atol=1e-10):
    """Compare every value in bounded-memory chunks; no checksums substitute."""
    arrays = {
        key: np.load(path, mmap_mode="r", allow_pickle=False)
        for key, path in paths.items()
    }
    try:
        if len({array.shape for array in arrays.values()}) != 1:
            raise AssertionError("Gamma shapes differ")
        maximum = 0.0
        squared_error = 0.0
        finite_count = 0
        classification_disagreements = 0
        for start in range(0, next(iter(arrays.values())).size, 1_000_000):
            chunks = {
                key: array.reshape(-1)[start : start + 1_000_000]
                for key, array in arrays.items()
            }
            for algorithm in ("pymedphys", "scipy"):
                np.testing.assert_array_equal(
                    chunks[f"previous-{algorithm}"], chunks[f"current-{algorithm}"]
                )
            left, right = chunks["current-pymedphys"], chunks["current-scipy"]
            np.testing.assert_array_equal(np.isnan(left), np.isnan(right))
            np.testing.assert_array_equal(np.isfinite(left), np.isfinite(right))
            finite = np.isfinite(left)
            error = left[finite] - right[finite]
            maximum = max(maximum, float(np.max(np.abs(error), initial=0)))
            squared_error += float(np.sum(error * error))
            finite_count += int(finite.sum())
            classification_disagreements += int(
                np.count_nonzero((left[finite] <= 1) != (right[finite] <= 1))
            )
            np.testing.assert_allclose(left, right, rtol=0, atol=atol, equal_nan=True)
        return {
            "revision_equality": "exact",
            "nan_pattern_equal": True,
            "algorithm_max_abs_difference": maximum,
            "algorithm_rmse": float(np.sqrt(squared_error / finite_count))
            if finite_count
            else None,
            "algorithm_absolute_tolerance": atol,
            "algorithm_pass_disagreements": classification_disagreements,
            "finite_points": finite_count,
        }
    finally:
        for array in arrays.values():
            array._mmap.close()


def run_study(config, roots, output, result):
    worker_source = (
        Path(__file__).with_name("gamma_scaling_worker.py").read_text(encoding="utf-8")
    )
    array_directory = output / "arrays"
    array_directory.mkdir(exist_ok=True)
    worker = output / "worker.py"
    worker.write_text(worker_source, encoding="utf-8")
    for dimension, profile, scale in itertools.product(
        config["dimensions"], config["profiles"], config["scales"]
    ):
        case = case_id(dimension, profile, scale)
        shape = shape_for(dimension, scale)
        for round_index in config["round_indices"]:
            group = f"{case}-round-{round_index}"
            if group in result["comparisons"]:
                continue
            paths = {}
            group_records = []
            for position in ORDERS[round_index % 4]:
                variant = VARIANTS[position]
                version, algorithm = variant.split("-")
                key = f"{group}-{variant}"
                array_path = array_directory / f"{key}.npy"
                paths[variant] = array_path
                existing = next((r for r in result["records"] if r["id"] == key), None)
                if (
                    existing is not None
                    and existing["status"] == "ok"
                    and array_path.exists()
                ):
                    group_records.append(existing)
                    continue
                if existing is not None:
                    result["records"].remove(existing)
                job = {
                    "dimension": dimension,
                    "profile": profile,
                    "shape": shape,
                    "algorithm": algorithm,
                    "ram_bytes": config["ram_bytes"],
                    "repeats": config["repeats"],
                    "checkout": str(roots[version]),
                    "array_path": str(array_path),
                }
                job_path = output / "worker-config.json"
                write_json(job_path, job)
                record = {
                    "id": key,
                    "case": case,
                    "dimension": dimension,
                    "profile": profile,
                    "scale": scale,
                    "shape": list(shape),
                    "points": int(np.prod(shape)),
                    "round": round_index,
                    "variant": variant,
                    "revision": config["revisions"][version],
                    "started_utc": utc_now(),
                    "host": result["host"],
                    "cloud": result["cloud"],
                }
                print(
                    f"{case}, {np.prod(shape):,} points, round {round_index + 1}: {variant}",
                    flush=True,
                )
                try:
                    process = subprocess.run(
                        [sys.executable, str(worker), str(job_path)],
                        cwd=output,
                        env=dict(
                            os.environ,
                            PYTHONPATH=str(roots[version] / "lib"),
                            NUMBA_NUM_THREADS=str(config["threads"]),
                            OMP_NUM_THREADS="1",
                            OPENBLAS_NUM_THREADS="1",
                            MKL_NUM_THREADS="1",
                            PYTHONDONTWRITEBYTECODE="1",
                        ),
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=config["worker_timeout"],
                    )
                    measured = json.loads(process.stdout)
                    if measured["numba_threads"] != config["threads"]:
                        raise ValueError(
                            "Worker did not use the requested thread count"
                        )
                    if (
                        measured["shape"] != list(shape)
                        or measured["finite_points"] != measured["eligible_points"]
                    ):
                        raise ValueError(
                            "Unexpected shape or non-finite eligible gamma points"
                        )
                    record.update(measured, status="ok")
                    print(
                        f"  {measured['times']} s; full warm-up {measured['warmup_seconds']:.3f} s",
                        flush=True,
                    )
                except subprocess.TimeoutExpired:
                    record.update(
                        status="timeout", worker_timeout=config["worker_timeout"]
                    )
                    print(
                        "  Worker time limit reached; not a measured gamma runtime",
                        flush=True,
                    )
                except subprocess.CalledProcessError as error:
                    record.update(
                        status="error", error=(error.stderr or error.stdout)[-10000:]
                    )
                    print(f"  Failed: {record['error']}", flush=True)
                result["records"].append(record)
                group_records.append(record)
                write_json(output / "results.json", result)
            if all(r["status"] == "ok" for r in group_records):
                if len({r["input_sha256"] for r in group_records}) != 1:
                    raise AssertionError(
                        "The four implementations received different inputs"
                    )
                if (
                    len(
                        {
                            json.dumps(r["versions"], sort_keys=True)
                            for r in group_records
                        }
                    )
                    != 1
                ):
                    raise AssertionError("Worker dependency versions differ")
                result["comparisons"][group] = compare_arrays(paths)
                for record in group_records:
                    record["verified"] = True
                print(
                    "  Exact old/new arrays; PyMedPhys/SciPy checked across every element",
                    flush=True,
                )
                write_json(output / "results.json", result)
                for path in paths.values():
                    path.unlink()
            else:
                result["incomplete_groups"].append(group)
                write_json(output / "results.json", result)
    for version, root in roots.items():
        checked_checkout(root, config["revisions"][version])
    result["completed_utc"] = utc_now()
    write_json(output / "results.json", result)
    return result


def summarise(result):
    """Only groups with successful four-way correctness checks enter plots."""
    rows = []
    for case in sorted({r["case"] for r in result["records"]}):
        for variant in VARIANTS:
            records = [
                r
                for r in result["records"]
                if r["case"] == case and r["variant"] == variant and r.get("verified")
            ]
            if not records:
                continue
            times = [time for record in records for time in record["times"]]
            first = records[0]
            rows.append(
                {
                    "case": case,
                    "dimension": first["dimension"],
                    "profile": first["profile"],
                    "scale": first["scale"],
                    "points": first["points"],
                    "eligible_points": first["eligible_points"],
                    "variant": variant,
                    "median_seconds": float(np.median(times)),
                    "min_seconds": min(times),
                    "max_seconds": max(times),
                    "rounds": len(records),
                    "timed_calls": len(times),
                    "peak_process_rss_bytes": max(
                        (r["peak_process_rss_bytes"] or 0) for r in records
                    )
                    or None,
                }
            )
    return rows


def validate_records(result):
    """Validate provenance, counts and coverage before accepting any plot."""
    config = result["config"]
    expected = {
        f"{case_id(d, p, s)}-round-{r}"
        for d, p, s, r in itertools.product(
            config["dimensions"],
            config["profiles"],
            config["scales"],
            config["round_indices"],
        )
    }
    ids = set()
    for record in result["records"]:
        if record["id"] in ids:
            raise ValueError("Duplicate measurement identifier")
        ids.add(record["id"])
        if not record.get("verified"):
            continue
        group = f"{record['case']}-round-{record['round']}"
        if group not in expected or group not in result["comparisons"]:
            raise ValueError("Measurement has no matching full-array comparison")
        if record["revision"] != config["revisions"][record["variant"].split("-")[0]]:
            raise ValueError("Measurement revision does not match the study")
        times = record["times"]
        if (
            len(times) != config["repeats"]
            or not np.isfinite(times).all()
            or min(times) <= 0
        ):
            raise ValueError("Invalid or incomplete timing samples")
        if (
            not record["repeat_equality"]
            or record["numba_threads"] != config["threads"]
        ):
            raise ValueError("Worker correctness or thread check failed")
    for group, comparison in result["comparisons"].items():
        selected = [
            r
            for r in result["records"]
            if f"{r['case']}-round-{r['round']}" == group and r.get("verified")
        ]
        if {r["variant"] for r in selected} != set(VARIANTS) or len(selected) != 4:
            raise ValueError("A verified group must contain all four implementations")
        if len({r["input_sha256"] for r in selected}) != 1:
            raise ValueError("Four-way comparison used different inputs")
        if (
            comparison["revision_equality"] != "exact"
            or not comparison["nan_pattern_equal"]
        ):
            raise ValueError(
                "Incorrect gamma results cannot be plotted as a speed gain"
            )
    versions = {
        json.dumps(r["versions"], sort_keys=True)
        for r in result["records"]
        if r.get("verified")
    }
    if len(versions) > 1:
        raise ValueError("Cannot combine different scientific dependency versions")
    result["incomplete_groups"] = sorted(expected - result["comparisons"].keys())
    result["expected_groups"] = len(expected)
    result["complete"] = not result["incomplete_groups"]


def save_report(result, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    validate_records(result)
    write_json(output / "results.json", result)
    rows = summarise(result)
    if not rows:
        raise ValueError("No fully verified four-way comparison is available to plot")
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (output / "timings.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = [
            "case",
            "dimension",
            "profile",
            "scale",
            "points",
            "eligible_points",
            "round",
            "variant",
            "revision",
            "status",
            "verified",
            "repeat",
            "seconds",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in result["records"]:
            for repeat, seconds in enumerate(record.get("times", []), 1):
                writer.writerow(
                    {
                        **{field: record.get(field) for field in fields},
                        "repeat": repeat,
                        "seconds": seconds,
                    }
                )
    colours = {
        "previous-pymedphys": "#A8541B",
        "current-pymedphys": "#176B91",
        "previous-scipy": "#826A9C",
        "current-scipy": "#28764B",
    }
    labels = {
        "previous-pymedphys": "Old PyMedPhys",
        "current-pymedphys": "New PyMedPhys",
        "previous-scipy": "Old SciPy",
        "current-scipy": "New SciPy",
    }
    markers = dict(zip(VARIANTS, ("o", "s", "^", "D")))
    plt.rcParams.update(
        {"font.size": 11, "axes.spines.top": False, "axes.spines.right": False}
    )
    for profile in result["config"]["profiles"]:
        dimensions = result["config"]["dimensions"]
        fig, axs = plt.subplots(
            len(dimensions), 2, figsize=(12, 4.1 * len(dimensions) + 1.4), squeeze=False
        )
        fig.subplots_adjust(
            left=0.09, right=0.98, top=0.84, bottom=0.16, wspace=0.28, hspace=0.5
        )
        for row_index, dimension in enumerate(dimensions):
            absolute, relative = axs[row_index]
            for variant in VARIANTS:
                selected = sorted(
                    (
                        r
                        for r in rows
                        if r["profile"] == profile
                        and r["dimension"] == dimension
                        and r["variant"] == variant
                    ),
                    key=lambda r: r["points"],
                )
                if not selected:
                    continue
                x = [r["points"] for r in selected]
                y = [r["median_seconds"] for r in selected]
                absolute.plot(
                    x,
                    y,
                    marker=markers[variant],
                    color=colours[variant],
                    linestyle="--" if variant.startswith("previous") else "-",
                    label=labels[variant],
                )
                absolute.vlines(
                    x,
                    [r["min_seconds"] for r in selected],
                    [r["max_seconds"] for r in selected],
                    color=colours[variant],
                    alpha=0.6,
                )
            for algorithm, colour, marker in (
                ("pymedphys", "#176B91", "s"),
                ("scipy", "#28764B", "D"),
            ):
                old = {
                    r["scale"]: r
                    for r in rows
                    if r["profile"] == profile
                    and r["dimension"] == dimension
                    and r["variant"] == f"previous-{algorithm}"
                }
                new = {
                    r["scale"]: r
                    for r in rows
                    if r["profile"] == profile
                    and r["dimension"] == dimension
                    and r["variant"] == f"current-{algorithm}"
                }
                scales = sorted(old.keys() & new.keys())
                relative.plot(
                    [new[s]["points"] for s in scales],
                    [
                        new[s]["median_seconds"] / old[s]["median_seconds"]
                        for s in scales
                    ],
                    marker=marker,
                    color=colour,
                    label=f"{algorithm.capitalize()}: new / old",
                )
            absolute.set(
                xscale="log",
                yscale="log",
                xlabel="Total reference grid points (log scale)",
                ylabel="Complete gamma-call time (s, log scale)",
                title=f"{dimension}D · absolute runtime",
            )
            relative.set(
                xscale="log",
                xlabel="Total reference grid points (log scale)",
                ylabel="New / old runtime",
                title=f"{dimension}D · effect of this change",
            )
            relative.axhline(1, color="#666666", linestyle=":", linewidth=1)
            relative.legend(fontsize=9)
            for ax in (absolute, relative):
                ax.grid(True, which="major", alpha=0.2)
        handles, names = axs[0, 0].get_legend_handles_labels()
        fig.legend(
            handles,
            names,
            loc="upper center",
            bbox_to_anchor=(0.52, 0.91),
            ncol=2,
            frameon=False,
        )
        fig.suptitle(
            f"Gamma scaling · {PROFILE_LABELS[profile]}",
            y=0.985,
            fontsize=18,
            fontweight="bold",
        )
        fig.text(
            0.5,
            0.94,
            "All four implementations use identical inputs, criteria and RAM chunk budgets",
            ha="center",
        )
        config = result["config"]
        count = len({r["round"] for r in result["records"] if r.get("verified")})
        footer = (
            f"Previous {config['revisions']['previous'][:12]} · Current {config['revisions']['current'][:12]} · {config['threads']} Numba threads\n"
            f"{count} observed round(s); median and individual-call min–max, not confidence intervals. Full warm-ups excluded.\n"
            "Fixed physical fields; increasing resolution. Old/new arrays equal exactly; PyMedPhys/SciPy checked to 1e-10.\n"
            f"Verified groups: {len(result['comparisons'])}; incomplete groups: {len(set(result['incomplete_groups']))}. Missing runs are not zero runtimes."
        )
        fig.text(0.03, 0.025, footer, fontsize=9, va="bottom", color="#444444")
        fig.savefig(output / f"scaling-{profile}.png", dpi=180, facecolor="white")
        fig.savefig(output / f"scaling-{profile}.svg", facecolor="white")
        plt.close(fig)
    headers = [
        "Case",
        "Points",
        "Old PyMedPhys (s)",
        "New PyMedPhys (s)",
        "Old SciPy (s)",
        "New SciPy (s)",
        "Rounds",
    ]
    lines = [
        "# Four-way gamma scaling results",
        "",
        "Absolute medians in seconds; only fully verified four-way groups contribute.",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for case in sorted({r["case"] for r in rows}):
        selected = {r["variant"]: r for r in rows if r["case"] == case}
        first = next(iter(selected.values()))
        lines.append(
            "| "
            + " | ".join(
                [
                    case,
                    f"{first['points']:,}",
                    *[
                        f"{selected[v]['median_seconds']:.4f}"
                        if v in selected
                        else "missing"
                        for v in VARIANTS
                    ],
                    str(first["rounds"]),
                ]
            )
            + " |"
        )
    lines += [
        "",
        "Raw observations and provenance: `results.json` and `timings.csv`.",
        "",
        "PyMedPhys/SciPy ratios compare the full gamma call, not an isolated interpolation kernel. Log axes show multiplicative changes. Peak RSS includes input preparation, warm-up and verification; the RAM chunk budget is not a process memory cap.",
    ]
    (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def merge_results(directory, output):
    parts = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.rglob("results.json"))
    ]
    if not parts:
        raise ValueError("No results.json files found")
    keys = (
        "revisions",
        "threads",
        "repeats",
        "ram_bytes",
        "worker_sha256",
        "driver_sha256",
    )
    for key in keys:
        if (
            len({json.dumps(part["config"][key], sort_keys=True) for part in parts})
            != 1
        ):
            raise ValueError(f"Cannot combine studies with different {key}")
    result = {
        **parts[0],
        "records": [],
        "comparisons": {},
        "incomplete_groups": [],
        "sources": [],
    }
    result["config"] = dict(parts[0]["config"])
    for key in ("dimensions", "profiles", "scales", "round_indices"):
        result["config"][key] = sorted(
            {value for part in parts for value in part["config"][key]}
        )
    seen = set()
    for part in parts:
        result["sources"].append({"host": part["host"], "cloud": part["cloud"]})
        for record in part["records"]:
            if record["id"] in seen:
                raise ValueError(f"Duplicate observation: {record['id']}")
            seen.add(record["id"])
            result["records"].append(record)
        result["comparisons"].update(part["comparisons"])
        result["incomplete_groups"].extend(part["incomplete_groups"])
    # Cloud runners may have different vector maths implementations. Full-array
    # checks are paired within each host; record cross-host hash consistency
    # separately rather than pretending that hashes quantify numerical error.
    result["cross_host_hash_consistency"] = {}
    for case, variant in itertools.product(
        {r["case"] for r in result["records"]}, VARIANTS
    ):
        selected = [
            r
            for r in result["records"]
            if r["case"] == case and r["variant"] == variant and r.get("verified")
        ]
        result["cross_host_hash_consistency"][f"{case}-{variant}"] = {
            key: len({r[key] for r in selected}) <= 1
            for key in ("input_sha256", "gamma_sha256")
        }
    result["completed_utc"] = utc_now()
    write_json(output / "results.json", result)
    save_report(result, output)
    return result


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--previous-ref", default=PREVIOUS)
    parser.add_argument("--current-ref", default="HEAD")
    parser.add_argument(
        "--dimensions", nargs="+", type=int, choices=[2, 3], default=[2, 3]
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=list(PROFILE_LABELS),
        default=list(PROFILE_LABELS),
    )
    parser.add_argument("--scales", nargs="+", type=float, default=[1, 3, 10, 30, 100])
    parser.add_argument("--round-indices", nargs="+", type=int, default=[0, 1, 2, 3])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--ram-mib", type=int, default=1536)
    parser.add_argument(
        "--worker-timeout",
        type=int,
        default=3600,
        help="Whole-worker seconds, including setup, warm-up and repeats",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--merge", type=Path)
    parser.add_argument("--plot-only", type=Path)
    args = parser.parse_args()
    if args.resume and (args.output or args.merge or args.plot_only):
        parser.error("Use --resume on its own, with matching study options")
    if (
        min(args.repeats, args.threads, args.ram_mib, args.worker_timeout) < 1
        or min(args.round_indices) < 0
    ):
        parser.error(
            "Use positive resource/repeat values and non-negative round indices"
        )
    for dimension, scale in itertools.product(args.dimensions, args.scales):
        shape_for(dimension, scale)
    for values in (args.dimensions, args.profiles, args.scales, args.round_indices):
        if len(set(values)) != len(values):
            parser.error("Study selections must not contain duplicates")
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    output = (
        args.resume or args.output or Path(f"gamma-scaling-{timestamp}")
    ).resolve()
    output.mkdir(parents=True, exist_ok=bool(args.resume))
    if args.merge:
        merge_results(args.merge, output)
        return
    if args.plot_only:
        result = json.loads(args.plot_only.read_text(encoding="utf-8"))
        write_json(output / "results.json", result)
        save_report(result, output)
        return
    repo = args.repo.resolve(strict=True)

    def git(*arguments):
        return subprocess.check_output(
            ["git", "-C", str(repo), *arguments], text=True, stderr=subprocess.STDOUT
        ).strip()

    revisions = {
        "previous": git("rev-parse", "--verify", f"{args.previous_ref}^{{commit}}"),
        "current": git("rev-parse", "--verify", f"{args.current_ref}^{{commit}}"),
    }
    if len(set(revisions.values())) != 2:
        parser.error("Choose two distinct revisions")
    config = {
        "revisions": revisions,
        "dimensions": args.dimensions,
        "profiles": args.profiles,
        "scales": sorted(args.scales),
        "round_indices": args.round_indices,
        "repeats": args.repeats,
        "threads": args.threads,
        "ram_bytes": args.ram_mib * 2**20,
        "worker_timeout": args.worker_timeout,
        "worker_sha256": hashlib.sha256(
            Path(__file__).with_name("gamma_scaling_worker.py").read_bytes()
        ).hexdigest(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    host = {
        "processor": machine_description(),
        "platform": platform.platform(),
        "python": sys.version,
    }
    cloud = {
        key: os.environ.get(key)
        for key in (
            "GITHUB_SERVER_URL",
            "GITHUB_REPOSITORY",
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
            "GITHUB_SHA",
            "BENCHMARK_JOB_LABEL",
            "ImageOS",
            "ImageVersion",
        )
    }
    result = {
        "schema_version": 1,
        "config": config,
        "host": host,
        "cloud": cloud,
        "created_utc": utc_now(),
        "records": [],
        "comparisons": {},
        "incomplete_groups": [],
    }
    if args.resume:
        result = json.loads((output / "results.json").read_text(encoding="utf-8"))
        if result["config"] != config or result["host"] != host:
            raise ValueError(
                "Resume requires matching source, worker, options and host"
            )
        result["incomplete_groups"] = []
    write_json(output / "results.json", result)
    with tempfile.TemporaryDirectory(prefix="pymedphys-scaling-") as directory:
        roots = {}
        try:
            for version, revision in revisions.items():
                root = Path(directory) / version
                git("worktree", "add", "--detach", str(root), revision)
                checked_checkout(root, revision)
                roots[version] = root
            run_study(config, roots, output, result)
        finally:
            for root in roots.values():
                if not root.resolve().is_relative_to(Path(directory).resolve()):
                    raise RuntimeError("Temporary checkout escaped its parent")
                git("worktree", "remove", "--force", str(root))
    save_report(result, output)
    print(
        f"Saved verified observations, tables and logarithmic plots in {output}",
        flush=True,
    )
    if result["incomplete_groups"]:
        raise SystemExit(
            "Study contains incomplete groups; inspect results.json and resume if appropriate"
        )


if __name__ == "__main__":
    main()
