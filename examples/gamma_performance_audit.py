# Copyright (C) 2026 Matthew Jennings
# Licensed under the Apache License, Version 2.0.
"""Calibrate and run a fixed performance audit inside a supplied deadline.

Use gamma_scaling_background.py for the independent two-hour watchdog.
Calibration selects grid sizes; its observations never enter the audit plots.
"""

import argparse
import copy
import hashlib
import itertools
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import gamma_scaling as study
from gamma_performance import checked_checkout, machine_description
from gamma_scaling_worker import SCENARIOS, scenario_field

FAMILIES = tuple(itertools.product((2, 3), ("global", "cap2", "local")))
COMPARISON_SECONDS = 45
CALIBRATION_PROBES = 3
CALIBRATION_TARGET = 25
SCENARIO_SECONDS = 1200


def save_scenarios(output):
    """Illustrate the specified physical fields without running gamma."""
    import matplotlib
    import numpy as np

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 6), layout="constrained")
    for ax, (name, spec) in zip(axes, SCENARIOS.items()):
        z, _, x = tuple(
            (np.arange(n) - (n - 1) / 2) * spec["spacing_mm"] for n in spec["shape"]
        )
        dose = scenario_field((z, np.array([0.0]), x), name)[:, 0, :] / 2
        mesh = ax.pcolormesh(
            x, z, dose, vmin=0, vmax=1, cmap="viridis", shading="nearest"
        )
        ax.contour(
            x, z, dose, levels=[0.1], colors="white", linestyles="--", linewidths=1
        )
        ax.set(
            aspect="equal",
            xlabel="x (mm)",
            ylabel="z (mm)",
            title=f"{'SABR-like' if name == 'sabr' else 'Prostate and nodes'} · {spec['spacing_mm']:g} mm grid",
        )
    fig.colorbar(
        mesh, ax=axes, label="Reference dose / fixed 2 Gy normalisation", shrink=0.8
    )
    fig.suptitle(
        "Synthetic workload proxies · coronal plane y = 0 mm\nWhite dashed contour: 10% cutoff; no patient anatomy or calculated plan dose",
        fontsize=12,
    )
    fig.savefig(output / "audit-scenarios.png", dpi=160, facecolor="white")
    plt.close(fig)


def empty_result(config, host, cloud):
    return {
        "schema_version": 1,
        "config": copy.deepcopy(config),
        "host": host,
        "cloud": cloud,
        "created_utc": study.utc_now(),
        "records": [],
        "comparisons": {},
        "incomplete_groups": [],
    }


def selected_scales(dimension, largest):
    scales = [float(f"{largest / factor:.8g}") for factor in (9, 3, 1)]
    if len({study.shape_for(dimension, s) for s in scales}) != 3:
        raise ValueError("Calibration reached grids too small for three distinct sizes")
    return scales


def audit_plan(selections):
    """Freeze 72 balanced groups, then two explicitly single-round proxies."""
    groups = []
    for size, round_index, (dimension, profile) in itertools.product(
        range(3), range(4), FAMILIES
    ):
        scales = selected_scales(dimension, selections[f"{dimension}d-{profile}"])
        groups.append([dimension, profile, scales[size], round_index])
    groups.extend([[3, scenario, 1.0, 0] for scenario in SCENARIOS])
    return groups


def maximum_measurement_seconds():
    # Every allowance includes imports, full warm-ups, timed calls and checks.
    return (
        len(FAMILIES) * CALIBRATION_PROBES * COMPARISON_SECONDS
        + 72 * COMPARISON_SECONDS
        + len(SCENARIOS) * SCENARIO_SECONDS
    )


def calibrate(config, roots, output, host, cloud, stop_file, deadline):
    path = output / "calibration.json"
    record = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {"probes": [], "selections": {}}
    )
    for dimension, profile in FAMILIES:
        family = f"{dimension}d-{profile}"
        if family in record["selections"]:
            continue
        scale = 1.0 if dimension == 2 else (0.02 if profile == "local" else 0.1)
        successful = []
        for index in range(CALIBRATION_PROBES):
            if time.monotonic() >= deadline or (
                stop_file is not None and stop_file.exists()
            ):
                return None
            previous = next(
                (
                    p
                    for p in record["probes"]
                    if p["family"] == family and p["index"] == index
                ),
                None,
            )
            if previous is None:
                probe_config = {**config, "plan": [[dimension, profile, scale, index]]}
                probe = empty_result(probe_config, host, cloud)
                probe_output = output / "calibration" / f"{family}-{index}"
                probe_output.mkdir(parents=True, exist_ok=True)
                print(
                    f"Calibration {family}: multiplier {scale:g} (at most {COMPARISON_SECONDS} s)",
                    flush=True,
                )
                started = time.monotonic()
                study.run_study(
                    probe_config, roots, probe_output, probe, stop_file, deadline
                )
                study.validate_records(probe)
                previous = {
                    "family": family,
                    "index": index,
                    "scale": scale,
                    "wall_seconds": time.monotonic() - started,
                    "result": probe,
                }
                if probe.get("stop_reason"):
                    record.setdefault("interrupted_probes", []).append(previous)
                    study.write_json(path, record)
                    study.write_json(probe_output / "results.json", probe)
                    return None
                record["probes"].append(previous)
                study.write_json(path, record)
            scale = previous["scale"]
            fits = (
                previous["result"]["complete"]
                and previous["wall_seconds"] <= CALIBRATION_TARGET
            )
            if fits:
                successful.append(scale)
            next_scale = float(f"{min(100, scale * (3 if fits else 1 / 3)):.8g}")
            if any(
                p["family"] == family and p["scale"] == next_scale
                for p in record["probes"]
            ):
                break
            scale = next_scale
        if not successful:
            raise RuntimeError(
                f"{family} could not complete a calibration group within {CALIBRATION_TARGET} s. Check workstation load; no complete audit is claimed."
            )
        record["selections"][family] = max(successful)
        selected_scales(dimension, max(successful))
        study.write_json(path, record)
    return record["selections"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--previous-ref", required=True)
    parser.add_argument("--current-ref", required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--worker-timeout", type=float, default=1200)
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--stop-file", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=Path)
    action.add_argument("--resume", type=Path)
    args = parser.parse_args()
    deadline = time.monotonic() + max(0, args.deadline - time.time())
    output = (args.resume or args.output).resolve()
    output.mkdir(parents=True, exist_ok=bool(args.resume))

    def git(*arguments):
        return subprocess.check_output(
            ["git", "-C", str(args.repo), *arguments],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()

    revisions = {
        "previous": git("rev-parse", "--verify", f"{args.previous_ref}^{{commit}}"),
        "current": git("rev-parse", "--verify", f"{args.current_ref}^{{commit}}"),
    }
    if len(set(revisions.values())) != 2:
        raise ValueError("Choose two distinct source revisions")
    config = {
        "revisions": revisions,
        "dimensions": [2, 3],
        "profiles": ["global", "cap2", "local", *SCENARIOS],
        "scales": [],
        "round_indices": [0, 1, 2, 3],
        "plan": [],
        "threads": args.threads,
        "repeats": 1,
        "ram_bytes": 1536 * 2**20,
        "worker_timeout": args.worker_timeout,
        "comparison_seconds": COMPARISON_SECONDS,
        "cases": {
            study.case_id(3, name, 1): {
                "scenario": name,
                "shape": list(spec["shape"]),
                "spacing_mm": spec["spacing_mm"],
                "comparison_seconds": SCENARIO_SECONDS,
            }
            for name, spec in SCENARIOS.items()
        },
        "source_hashes": {
            name: hashlib.sha256(
                Path(__file__).with_name(name).read_bytes()
            ).hexdigest()
            for name in (
                "gamma_performance_audit.py",
                "gamma_scaling.py",
                "gamma_scaling_worker.py",
                "gamma_scaling_process.py",
                "gamma_performance.py",
            )
        },
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
    result = empty_result(config, host, cloud)
    if args.resume:
        result = json.loads((output / "results.json").read_text(encoding="utf-8"))
        for key in config.keys() - {"plan", "scales"}:
            if result["config"][key] != config[key]:
                raise ValueError(f"Resume requires the original {key}")
        if result["host"] != host or result["cloud"] != cloud:
            raise ValueError("Resume requires the original host")
        config = result["config"]
        result.pop("stop_reason", None)
    study.write_json(output / "results.json", result)
    with tempfile.TemporaryDirectory(prefix="pymedphys-audit-") as directory:
        roots = {}
        try:
            for version, revision in revisions.items():
                root = Path(directory) / version
                git("worktree", "add", "--detach", str(root), revision)
                roots[version] = root
                checked_checkout(root, revision)
            if not config["plan"]:
                selections = calibrate(
                    config, roots, output, host, cloud, args.stop_file, deadline
                )
                if selections is None:
                    result["stop_reason"] = (
                        "user_stop"
                        if args.stop_file and args.stop_file.exists()
                        else "time_budget"
                    )
                else:
                    config["plan"] = audit_plan(selections)
                    config["scales"] = sorted({g[2] for g in config["plan"]})
                    result["config"] = config
                    study.write_json(
                        output / "audit-plan.json",
                        {
                            "plan": config["plan"],
                            "cases": config["cases"],
                            "routine_groups": 72,
                            "scenario_groups": 2,
                            "maximum_measurement_seconds": maximum_measurement_seconds(),
                            "calibration_target_seconds": CALIBRATION_TARGET,
                        },
                    )
                    study.write_json(output / "results.json", result)
            if not result.get("stop_reason"):
                study.run_study(config, roots, output, result, args.stop_file, deadline)
        finally:
            for root in roots.values():
                if not root.resolve().is_relative_to(Path(directory).resolve()):
                    raise RuntimeError("Temporary checkout escaped its parent")
                git("worktree", "remove", "--force", str(root))
    result["routine_complete"] = bool(config["plan"]) and all(
        f"{study.case_id(d, p, s)}-round-{r}" in result["comparisons"]
        for d, p, s, r in config["plan"][:72]
    )
    study.validate_records(result)
    study.write_json(output / "results.json", result)
    if result["comparisons"]:
        study.save_report(result, output)
        save_scenarios(output)
    print(
        f"Audit complete: {result['complete']}; routine matrix complete: {result['routine_complete']}; {len(result['comparisons'])}/74 groups verified",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
