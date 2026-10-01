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

"""Sequential, checkpointed benchmark controller with isolated workers."""

from __future__ import annotations

import csv
import importlib.metadata
import json
import math
import os
import platform
import random
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

from .common import (
    SCHEMA_VERSION,
    fingerprint,
    read_json,
    sha256_file,
    utc_now,
    write_json,
)
from .pymedphys_api import interpolation_algorithm

ROOT = Path(__file__).resolve().parents[1]
CASE_CONTROLS = {
    "dose_percent_threshold",
    "distance_mm_threshold",
    "lower_percent_dose_cutoff",
    "interp_fraction",
    "max_gamma",
    "local_gamma",
    "global_normalisation",
    "ram_available",
    "random_subset",
    "random_state",
    "skip_once_passed",
}
DEFAULT_SETTINGS = dict(
    warmups=1,
    gamma_abs_tolerance=1e-6,
    allowed_pass_disagreements=0,
    repeatability_atol=0.0,
    worker_timeout_seconds=600,
    memory_limit_gib=8.0,
    memory_sample_interval_ms=10,
    budget_minutes=240,
    max_reference_points=30_000_000,
    keep_arrays=False,
    keep_inputs=False,
    seed=1729,
)


def example_config(
    preset="standard",
    baseline_checkout="../pymedphys-baseline",
    candidate_checkout="../pymedphys-candidate",
    compare_interpolators=False,
):
    if compare_interpolators:
        baseline = "scipy"
        versions = [
            dict(name=algorithm, checkout=baseline_checkout, interp_algo=algorithm)
            for algorithm in ("scipy", "pymedphys")
        ]
    else:
        baseline = "baseline"
        versions = [
            dict(name="baseline", checkout=baseline_checkout, interp_algo="pymedphys"),
            dict(
                name="candidate", checkout=candidate_checkout, interp_algo="pymedphys"
            ),
        ]
    return dict(
        schema_version=SCHEMA_VERSION,
        preset=preset,
        baseline=baseline,
        versions=versions,
        gamma_options={},
        settings=dict(DEFAULT_SETTINGS),
    )


def resolved_config(path, require_checkouts=True):
    path = Path(path).resolve()
    config = read_json(path)
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported configuration schema_version")
    if "implementations" in config:
        raise ValueError(
            "Use versions with PyMedPhys checkout paths; generic implementation descriptors are not supported"
        )
    versions = config.get("versions", [])
    if not isinstance(versions, list) or not all(isinstance(v, dict) for v in versions):
        raise ValueError("versions must be a list of PyMedPhys versions")
    names = [item.get("name", "") for item in versions]
    if len(names) < 2 or len(set(names)) != len(names):
        raise ValueError(
            "Configure at least two PyMedPhys versions with distinct names"
        )
    if config.get("baseline") not in names:
        raise ValueError("baseline must name a configured PyMedPhys version")
    for spec in versions:
        if set(spec) - {"name", "checkout", "python", "interp_algo"}:
            raise ValueError(
                "Each version accepts only name, checkout, optional python and interp_algo; the function is always pymedphys.gamma"
            )
        spec["interp_algo"] = interpolation_algorithm(spec)
        if "checkout" not in spec:
            raise ValueError(
                "Each version must set checkout to a path or explicitly to null for installed PyMedPhys"
            )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", spec["name"]):
            raise ValueError(
                "Version names may contain letters, digits, underscores and hyphens"
            )
        checkout = spec.get("checkout")
        if checkout is not None:
            if not isinstance(checkout, str) or not checkout:
                raise ValueError(
                    "checkout must be a directory path or null for an installed PyMedPhys version"
                )
            root = (path.parent / checkout).resolve()
            if require_checkouts and not any(
                (root / relative / "__init__.py").is_file()
                for relative in ("lib/pymedphys", "pymedphys")
            ):
                raise ValueError(
                    f"PyMedPhys checkout does not contain lib/pymedphys or pymedphys: {root}"
                )
            spec["checkout"] = str(root)
        python = spec.get("python") or sys.executable
        if Path(python).is_absolute():
            executable = python
        elif (path.parent / python).is_file():
            executable = str((path.parent / python).resolve())
        else:
            executable = shutil.which(python)
        if not executable or not Path(executable).is_file():
            raise ValueError(f"Python executable not found: {python}")
        spec["python"] = str(Path(executable).resolve())
    options = config.setdefault("gamma_options", {})
    if not isinstance(options, dict):
        raise ValueError(
            "gamma_options must be an object of shared pymedphys.gamma keyword options"
        )
    if "interp_algo" in options:
        raise ValueError("Use per-version interp_algo, not gamma_options.interp_algo")
    if CASE_CONTROLS & options.keys():
        raise ValueError(
            "gamma_options cannot override case controls; change the plan instead"
        )
    settings = dict(DEFAULT_SETTINGS, **config.get("settings", {}))
    for key in ["warmups", "memory_sample_interval_ms", "max_reference_points"]:
        if (
            isinstance(settings[key], bool)
            or not isinstance(settings[key], int)
            or settings[key] <= 0
        ):
            raise ValueError(f"{key} must be a positive integer")
    for key in [
        "gamma_abs_tolerance",
        "repeatability_atol",
        "worker_timeout_seconds",
        "budget_minutes",
        "memory_limit_gib",
    ]:
        value = settings[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"{key} must be finite and non-negative")
    if settings["worker_timeout_seconds"] == 0:
        raise ValueError("worker_timeout_seconds must be positive")
    if (
        isinstance(settings["allowed_pass_disagreements"], bool)
        or not isinstance(settings["allowed_pass_disagreements"], int)
        or settings["allowed_pass_disagreements"] < 0
    ):
        raise ValueError("allowed_pass_disagreements must be a non-negative integer")
    if isinstance(settings["seed"], bool) or not isinstance(settings["seed"], int):
        raise ValueError("seed must be an integer")
    for key in ("keep_arrays", "keep_inputs"):
        if not isinstance(settings[key], bool):
            raise ValueError(f"{key} must be boolean")
    config["settings"] = settings
    return config


def validate_plan(plan, settings):
    """Validate JSON controls and bound fixture allocation before creating arrays.

    The fixture memory estimate allows eight float64 arrays per reference and
    evaluation grid for generation, copies, and serialisation. It is a planning
    guard, not a bound on an implementation's working memory or total RSS.
    """
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported plan schema_version")
    cases = plan.get("cases", [])
    if (
        not isinstance(cases, list)
        or not cases
        or not all(isinstance(c, dict) for c in cases)
    ):
        raise ValueError("Plan must contain a non-empty list of case dictionaries")
    if not all(isinstance(c.get("id"), str) for c in cases) or len(
        {c["id"] for c in cases}
    ) != len(cases):
        raise ValueError("Plan must contain cases with unique IDs")
    if (
        isinstance(plan.get("repeats"), bool)
        or not isinstance(plan.get("repeats"), int)
        or plan["repeats"] < 1
    ):
        raise ValueError("Plan repeats must be a positive integer")

    def number(value, label, minimum=0.0, strict=False):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} must be a finite number")
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite or value < minimum or (strict and value == minimum):
            qualifier = "greater than" if strict else "at least"
            raise ValueError(f"{label} must be finite and {qualifier} {minimum}")
        return value

    def integer(value, label, minimum=0):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{label} must be an integer of at least {minimum}")
        return value

    required = {
        "study",
        "dimension",
        "n",
        "grid_mode",
        "extent_mm",
        "spacing_mm",
        "field",
        "fraction_mode",
        "above_fraction_target",
        "dose_percent_threshold",
        "distance_mm_threshold",
        "interp_fraction",
        "max_gamma",
        "local_gamma",
        "ram_mib",
        "threads",
        "shift_mm",
        "dose_scale",
        "seed",
    }
    point_limit = integer(settings["max_reference_points"], "max_reference_points", 1)
    memory_gib = number(settings["memory_limit_gib"], "memory_limit_gib")
    for case in cases:
        missing = required - case.keys()
        if missing:
            raise ValueError(
                f"{case['id']}: missing required controls: {', '.join(sorted(missing))}"
            )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", case["id"]):
            raise ValueError("Case IDs must be safe file names")
        if not isinstance(case["study"], str) or not case["study"]:
            raise ValueError("study must be a non-empty string")
        dimension = integer(case["dimension"], "dimension", 2)
        if dimension not in (2, 3):
            raise ValueError("Cases require 2D or 3D grids")
        n = integer(case["n"], "n", 2)
        reference_points = n**dimension
        if reference_points > point_limit:
            raise ValueError(
                f"{case['id']} exceeds max_reference_points; raise that explicit limit if intended"
            )
        for key in ("distance_mm_threshold", "dose_percent_threshold"):
            raw = case[key]
            values = raw if isinstance(raw, list) else [raw]
            if not values:
                raise ValueError(f"{key} must contain at least one criterion")
            for value in values:
                number(value, key, strict=True)
            if len(set(values)) != len(values):
                raise ValueError(f"{key} must not contain duplicate criteria")
        number(case["interp_fraction"], "interp_fraction", strict=True)
        number(case["ram_mib"], "ram_mib", minimum=1 / 2**20)
        integer(case["threads"], "threads", 1)
        if case["max_gamma"] is not None:
            number(case["max_gamma"], "max_gamma", minimum=1, strict=True)
        if not isinstance(case["local_gamma"], bool):
            raise ValueError("local_gamma must be a boolean")
        if "skip_once_passed" in case and not isinstance(
            case["skip_once_passed"], bool
        ):
            raise ValueError("skip_once_passed must be a boolean")
        integer(case["seed"], "seed")
        if case.get("random_subset") is not None:
            integer(case["random_subset"], "random_subset")
        number(case["dose_scale"], "dose_scale", strict=True)
        number(case["shift_mm"], "shift_mm", minimum=-math.inf)
        width = number(case.get("field_width_mm", 18.4), "field_width_mm", strict=True)
        cutoff = number(
            case.get("lower_percent_dose_cutoff", 20.0), "lower_percent_dose_cutoff"
        )
        if case["field"] not in {"gaussian", "double", "plateau"}:
            raise ValueError("field must be gaussian, double, or plateau")
        fraction_mode = case["fraction_mode"]
        if fraction_mode not in {"cutoff", "width", "fixed_cutoff"}:
            raise ValueError("fraction_mode must be cutoff, width, or fixed_cutoff")
        target = case["above_fraction_target"]
        if fraction_mode in {"cutoff", "width"}:
            if number(target, "above_fraction_target") > 1:
                raise ValueError("above_fraction_target must be at most 1")
        elif target is not None:
            raise ValueError(
                "fixed_cutoff does not use above_fraction_target; set it to null"
            )
        if fraction_mode == "width" and not 0 < cutoff < 100:
            raise ValueError(
                "Field-width selection requires a fixed cutoff strictly between 0 and 100"
            )

        extent = number(case["extent_mm"], "extent_mm", strict=True)
        spacing = number(case["spacing_mm"], "spacing_mm", strict=True)
        if case["grid_mode"] == "fixed_extent":
            spacing = extent / (n - 1)
        elif case["grid_mode"] == "fixed_spacing":
            extent = spacing * (n - 1)
        else:
            raise ValueError("grid_mode must be fixed_extent or fixed_spacing")
        number(extent, "derived extent_mm", strict=True)
        number(spacing, "derived spacing_mm", strict=True)
        # Avoid overflow in width-search bracketing and physical coordinates.
        number(extent * 1024, "field-width upper search bound", strict=True)
        number(spacing / 1024, "field-width lower search bound", strict=True)
        number(width * 1.15, "largest field width", strict=True)
        padding = number(
            case.get("evaluation_padding_mm", 6.0), "evaluation_padding_mm"
        )
        intervals = padding / spacing
        if not math.isfinite(intervals):
            raise ValueError("Evaluation padding divided by spacing is too large")
        evaluation_n = n + 2 * math.ceil(intervals)
        evaluation_points = evaluation_n**dimension
        if evaluation_points > point_limit:
            raise ValueError(
                f"{case['id']}: padded evaluation grid exceeds max_reference_points; reduce padding or raise the explicit limit"
            )
        coordinate_bytes = 8 * dimension * (n + evaluation_n)
        estimated_fixture_bytes = (
            8 * 8 * (reference_points + evaluation_points) + coordinate_bytes
        )
        if memory_gib and estimated_fixture_bytes > memory_gib * 1024**3:
            raise ValueError(
                f"{case['id']}: estimated fixture working memory ({estimated_fixture_bytes} bytes) exceeds memory_limit_gib; reduce grid size/padding or raise the explicit limit"
            )


def environment_record():
    import psutil

    packages = {}
    for name in ["numpy", "scipy", "numba", "matplotlib", "psutil"]:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    return dict(
        recorded_at=utc_now(),
        python=sys.version,
        executable=sys.executable,
        platform=platform.platform(),
        machine=platform.machine(),
        processor=platform.processor(),
        logical_cpus=psutil.cpu_count(),
        physical_cpus=psutil.cpu_count(logical=False),
        total_ram_bytes=psutil.virtual_memory().total,
        packages=packages,
        limitations="Power state, affinity, thermal state and background workloads are not controlled; GPU memory is not measured.",
    )


def harness_fingerprint():
    return fingerprint(
        {
            str(p.relative_to(ROOT)): sha256_file(p)
            for p in sorted((ROOT / "gamma_bench").glob("*.py"))
        }
    )


def provenance_identity(provenance):
    """Select the identity fields that must stay fixed throughout a study."""
    return {
        key: provenance.get(key)
        for key in (
            "source_hashes",
            "packages",
            "python",
            "executable",
            "module_file",
            "interp_algo",
        )
    }


def probe_implementations(config, output):
    """Import and fingerprint each configured environment; never call gamma."""
    probes = {}
    directory = output / "provenance"
    directory.mkdir(exist_ok=True)
    for spec in config["versions"]:
        name = spec["name"]
        job = dict(
            mode="probe",
            implementation=spec,
            case={"threads": 1},
            cache_dir=str(output / "cache" / name),
            result_path=str(directory / f"{name}.json"),
            phase_path=str(directory / f"{name}.phase.json"),
            output_path=str(directory / f"{name}.unused"),
            round=-1,
            order_position=-1,
        )
        settings = config["settings"]
        result = run_worker(
            job,
            settings["worker_timeout_seconds"],
            settings["memory_limit_gib"] * 1024**3,
            settings["memory_sample_interval_ms"] / 1000,
            None,
        )
        if result["status"] != "ok":
            raise ValueError(
                f"Implementation preflight failed for {name}: {result.get('error', result['status'])}"
            )
        provenance = result["provenance"]
        probes[name] = provenance_identity(provenance)
    return probes


def save_fixture(case, directory):
    import hashlib
    import numpy as np
    from .workloads import make_inputs

    arguments, kwargs, metadata = make_inputs(case)
    axes_r, reference, axes_e, evaluation = arguments
    arrays = dict(reference_dose=reference, evaluation_dose=evaluation)
    arrays.update({f"reference_axis_{i}": a for i, a in enumerate(axes_r)})
    arrays.update({f"evaluation_axis_{i}": a for i, a in enumerate(axes_e)})
    mask = (
        reference
        >= kwargs["lower_percent_dose_cutoff"] / 100 * kwargs["global_normalisation"]
    )
    metadata["analysed_mask_checked"] = case.get("random_subset") is None
    subset = case.get("random_subset")
    metadata["expected_analysed_points"] = (
        min(int(mask.sum()), subset) if subset is not None else int(mask.sum())
    )
    arrays["eligible_mask"] = mask
    metadata["array_sha256"] = {
        k: hashlib.sha256(np.ascontiguousarray(v).tobytes()).hexdigest()
        for k, v in arrays.items()
    }
    metadata["array_dtypes"] = {k: str(v.dtype) for k, v in arrays.items()}
    path = directory / "inputs.npz"
    np.savez(path, **arrays)
    write_json(
        directory / "fixture.json", {"metadata": metadata, "gamma_kwargs": kwargs}
    )
    return path, kwargs, metadata


def run_worker(job, timeout, memory_limit, interval, deadline):
    import psutil

    job_path = Path(job["result_path"]).with_suffix(".job.json")
    # A crashed retry must not inherit a previous result or phase.
    for key in ("result_path", "phase_path", "output_path"):
        Path(job[key]).unlink(missing_ok=True)
    write_json(job_path, job)
    log_path = job_path.with_suffix(".log")
    env = os.environ.copy()
    # Thread settings are set inside the worker before numerical imports.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.monotonic()
    peaks = {"all": 0, "timed": 0, "first_call": 0}
    phase = "starting"
    reason = None
    with log_path.open("w", encoding="utf-8") as log:
        entry = Path(__file__).with_name("worker_entry.py")
        # Ignore inherited Python paths/home and user-site packages; dependencies
        # must come from the selected interpreter's environment.
        process = subprocess.Popen(
            [job["implementation"]["python"], "-I", "-B", str(entry), str(job_path)],
            cwd=job_path.parent,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        monitor = psutil.Process(process.pid)
        observed_children = {}

        def stop_tree():
            try:
                observed_children.update(
                    {p.pid: p for p in monitor.children(recursive=True)}
                )
            except psutil.Error:
                pass
            for child in list(observed_children.values())[::-1]:
                try:
                    child.kill()
                except psutil.Error:
                    pass
            if process.poll() is None:
                process.kill()
            psutil.wait_procs(list(observed_children.values()), timeout=2)

        try:
            while process.poll() is None:
                try:
                    descendants = monitor.children(recursive=True)
                    observed_children.update({p.pid: p for p in descendants})
                    rss = monitor.memory_info().rss
                    for child in descendants:
                        try:
                            rss += child.memory_info().rss
                        except psutil.Error:
                            pass
                    peaks["all"] = max(peaks["all"], rss)
                    phase_file = Path(job["phase_path"])
                    if phase_file.exists():
                        phase = read_json(phase_file).get("phase", phase)
                    if phase in peaks:
                        peaks[phase] = max(peaks[phase], rss)
                    if memory_limit and rss > memory_limit:
                        reason = "memory_limit"
                    elif time.monotonic() - started > timeout:
                        reason = "timeout"
                    elif deadline and time.monotonic() > deadline:
                        reason = "budget_exhausted"
                    if reason:
                        stop_tree()
                        break
                except (psutil.NoSuchProcess, ProcessLookupError):
                    break
                time.sleep(interval)
        except BaseException:
            stop_tree()
            process.wait()
            raise
        process.wait()
        stop_tree()
    if reason:
        result = dict(status=reason, error=f"Worker stopped: {reason}")
    elif Path(job["result_path"]).exists():
        result = read_json(job["result_path"])
    else:
        result = dict(
            status="error",
            error=f"Worker exited {process.returncode} without a result; inspect {log_path.name}",
        )
    result.update(
        worker_wall_seconds=time.monotonic() - started,
        memory_scope="sampled sum of process-tree RSS; shared pages may be counted more than once; excludes GPU",
        peak_rss_bytes=max(
            peaks["timed"],
            result.get("pre_gamma_rss_bytes", 0),
            result.get("post_gamma_rss_bytes", 0),
        ),
        worker_peak_rss_bytes=peaks["all"],
        first_call_peak_rss_bytes=peaks["first_call"],
        memory_sample_interval_ms=round(interval * 1000),
        round=job["round"],
        order_position=job["order_position"],
    )
    write_json(job["result_path"], result)
    return result


def compare_arrays(
    base_path, candidate_path, mask, settings, check_mask=True, expected_count=None
):
    import numpy as np

    result = dict(
        same_nan_mask=True,
        all_finite_analysed=True,
        max_abs_difference=0.0,
        pass_disagreements=0,
        exact_equal=True,
        nonnegative=True,
        within_cap=True,
        within_tolerance=True,
    )
    with (
        np.load(base_path, allow_pickle=False) as base,
        np.load(candidate_path, allow_pickle=False) as candidate,
    ):
        if set(base.files) != set(candidate.files):
            raise ValueError("Implementation outputs have different criterion keys")
        for key in base.files:
            a, b = base[key], candidate[key]
            if a.shape != b.shape or a.shape != mask.shape:
                raise ValueError("Output/reference shapes differ")
            result["same_nan_mask"] &= bool(np.array_equal(np.isnan(a), np.isnan(b)))
            if check_mask:
                result["all_finite_analysed"] &= bool(
                    np.isfinite(a[mask]).all() and np.isfinite(b[mask]).all()
                )
                result["same_nan_mask"] &= bool(
                    np.array_equal(np.isnan(a), ~mask)
                    and np.array_equal(np.isnan(b), ~mask)
                )
            else:
                result["all_finite_analysed"] &= bool(
                    not np.isinf(a).any() and not np.isinf(b).any()
                )
                result["all_finite_analysed"] &= bool(
                    not np.isfinite(a[~mask]).any() and not np.isfinite(b[~mask]).any()
                )
                if expected_count is not None:
                    result["all_finite_analysed"] &= bool(
                        np.isfinite(a).sum() == expected_count
                        and np.isfinite(b).sum() == expected_count
                    )
            finite = np.isfinite(a) & np.isfinite(b)
            result["nonnegative"] &= bool(
                np.all(a[finite] >= 0) and np.all(b[finite] >= 0)
            )
            cap = settings.get("max_gamma")
            if cap is not None:
                result["within_cap"] &= bool(
                    np.all(a[np.isfinite(a)] <= cap + settings["gamma_abs_tolerance"])
                    and np.all(
                        b[np.isfinite(b)] <= cap + settings["gamma_abs_tolerance"]
                    )
                )
            if finite.any():
                result["max_abs_difference"] = max(
                    result["max_abs_difference"],
                    float(np.max(np.abs(a[finite] - b[finite]))),
                )
            result["pass_disagreements"] += int(np.count_nonzero((a <= 1) != (b <= 1)))
            result["exact_equal"] &= bool(np.array_equal(a, b, equal_nan=True))
            result["within_tolerance"] &= bool(
                np.allclose(
                    a, b, atol=settings["gamma_abs_tolerance"], rtol=0, equal_nan=True
                )
            )
    result["valid"] = bool(
        result["same_nan_mask"]
        and result["all_finite_analysed"]
        and result["nonnegative"]
        and result["within_cap"]
        and result["within_tolerance"]
        and result["pass_disagreements"] <= settings["allowed_pass_disagreements"]
    )
    return result


def aggregate_case(case, metadata, per_variant, directory, config, repeats, output):
    import numpy as np

    settings, baseline = (
        dict(config["settings"], max_gamma=case.get("max_gamma")),
        config["baseline"],
    )
    with np.load(directory / "inputs.npz", allow_pickle=False) as inputs:
        mask = inputs["eligible_mask"]
    variants, comparisons = {}, {}
    for name, rounds in per_variant.items():
        good = [r for r in rounds if r.get("status") == "ok"]
        complete = len(good) == repeats
        variant = dict(
            status="ok"
            if complete
            else next((r["status"] for r in rounds if r["status"] != "ok"), "pending"),
            seconds=[r["seconds"] for r in good],
            rounds=rounds,
        )
        if good:
            first = good[0]
            variant.update(
                first_call_seconds=statistics.median(
                    r["first_call_seconds"] for r in good
                ),
                peak_rss_bytes=max(r["peak_rss_bytes"] for r in good),
                pre_gamma_rss_bytes=statistics.median(
                    r["pre_gamma_rss_bytes"] for r in good
                ),
                memory_sample_interval_ms=settings["memory_sample_interval_ms"],
                diagnostics=first.get("diagnostics", {}),
                output_sha256=first["output_sha256"],
                representative_file=str(
                    Path(first["representative_file"]).relative_to(output)
                ).replace("\\", "/"),
                provenance=first["provenance"],
                repeatable=all(r["repeatable"] for r in good),
            )
            signatures = [
                fingerprint(
                    {
                        "source": r["provenance"].get("source_hashes"),
                        "packages": r["provenance"].get("packages"),
                        "python": r["provenance"].get("python"),
                        "interp_algo": r["provenance"].get("interp_algo"),
                    }
                )
                for r in good
            ]
            if len(set(signatures)) != 1:
                variant["status"] = "error"
                variant["error"] = (
                    "Implementation source, environment or interpolator changed between rounds"
                )
            repeat_settings = dict(
                settings,
                gamma_abs_tolerance=settings["repeatability_atol"],
                allowed_pass_disagreements=0,
            )
            for result in good[1:]:
                try:
                    repeated = compare_arrays(
                        directory / f"{name}-{first['round']}.npz",
                        directory / f"{name}-{result['round']}.npz",
                        mask,
                        repeat_settings,
                        metadata["analysed_mask_checked"],
                        metadata.get("expected_analysed_points"),
                    )
                    variant["repeatable"] &= repeated["valid"]
                except (ValueError, OSError) as exc:
                    variant["repeatable"] = False
                    variant["error"] = str(exc)
        variants[name] = variant
    for name in variants:
        if name == baseline:
            continue
        verification = dict(
            same_nan_mask=True,
            all_finite_analysed=True,
            max_abs_difference=0.0,
            pass_disagreements=0,
            exact_equal=True,
            repeatable=True,
            within_tolerance=True,
            nonnegative=True,
            within_cap=True,
            valid=True,
            gamma_abs_tolerance=settings["gamma_abs_tolerance"],
            allowed_pass_disagreements=settings["allowed_pass_disagreements"],
        )
        ratios = []
        compared_rounds = 0
        if variants[baseline]["status"] == variants[name]["status"] == "ok":
            for round_index in range(repeats):
                a, b = (
                    per_variant[baseline][round_index],
                    per_variant[name][round_index],
                )
                try:
                    checked = compare_arrays(
                        directory / f"{baseline}-{round_index}.npz",
                        directory / f"{name}-{round_index}.npz",
                        mask,
                        settings,
                        metadata["analysed_mask_checked"],
                        metadata.get("expected_analysed_points"),
                    )
                except (ValueError, OSError) as exc:
                    verification["valid"] = False
                    verification["error"] = str(exc)
                    continue
                compared_rounds += 1
                for flag in [
                    "same_nan_mask",
                    "all_finite_analysed",
                    "exact_equal",
                    "within_tolerance",
                    "nonnegative",
                    "within_cap",
                    "valid",
                ]:
                    verification[flag] &= checked[flag]
                verification["max_abs_difference"] = max(
                    verification["max_abs_difference"], checked["max_abs_difference"]
                )
                verification["pass_disagreements"] = max(
                    verification["pass_disagreements"], checked["pass_disagreements"]
                )
                verification["repeatable"] &= bool(a["repeatable"] and b["repeatable"])
                ratios.append(a["seconds"] / b["seconds"])
            verification["repeatable"] &= (
                variants[baseline]["repeatable"] and variants[name]["repeatable"]
            )
            verification["valid"] &= verification["repeatable"]
        else:
            verification["valid"] = False
            verification["error"] = "Incomplete implementation rounds"
        if not compared_rounds:
            for key in (
                "same_nan_mask",
                "all_finite_analysed",
                "max_abs_difference",
                "pass_disagreements",
                "exact_equal",
                "repeatable",
                "within_tolerance",
                "nonnegative",
                "within_cap",
            ):
                verification[key] = None
        verification["compared_rounds"] = compared_rounds
        timing = dict(
            paired_speedups=ratios,
            median_speedup=statistics.median(ratios) if ratios else None,
            speedup_min=min(ratios) if ratios else None,
            speedup_max=max(ratios) if ratios else None,
        )
        comparisons[name] = dict(verification=verification, timing=timing)
    statuses = [v["status"] for v in variants.values()]
    status = (
        "ok"
        if all(s == "ok" for s in statuses)
        and all(c["verification"]["valid"] for c in comparisons.values())
        else "mismatch"
    )
    for failed in ["budget_exhausted", "memory_limit", "timeout", "error", "pending"]:
        if failed in statuses:
            status = failed
            break
    return dict(
        case=case,
        metadata=metadata,
        status=status,
        variants=variants,
        comparisons=comparisons,
    )


def export_tables(output, summary):
    rows = []
    for record in summary["records"]:
        for name, variant in record.get("variants", {}).items():
            values = variant.get("seconds", [])
            pair = record.get("comparisons", {}).get(name, {})
            row = dict(record["case"])
            row["requested_lower_percent_dose_cutoff"] = row.pop(
                "lower_percent_dose_cutoff", None
            )
            row.update(
                case_id=record["case"]["id"],
                implementation=name,
                status=record["status"],
                interp_algo=variant.get("provenance", {}).get("interp_algo"),
                median_seconds=statistics.median(values) if values else None,
                min_seconds=min(values) if values else None,
                max_seconds=max(values) if values else None,
                peak_rss_bytes=variant.get("peak_rss_bytes"),
                paired_median_speedup=pair.get("timing", {}).get("median_speedup"),
                **{
                    k: record.get("metadata", {}).get(k)
                    for k in [
                        "total_points",
                        "eligible_points",
                        "eligible_fraction",
                        "lower_percent_dose_cutoff",
                    ]
                },
            )
            row.update(pair.get("verification", {}))
            rows.append(row)
    if rows:
        keys = sorted(set().union(*(r.keys() for r in rows)))
        with (output / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)


def execute_run(config, plan, output, resume=False, make_report=True):
    """Hold an exclusive output lock for the complete run, including reporting."""
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()) and not resume:
        raise ValueError(
            "Output directory is not empty. Choose a new directory or use --resume."
        )
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".run.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError(
            "Output directory is locked. If its recorded process has stopped, remove .run.lock before resuming."
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                {"pid": os.getpid(), "created_at": utc_now(), "host": platform.node()},
                stream,
            )
        return _execute_run(config, plan, output, resume, make_report)
    finally:
        lock.unlink(missing_ok=True)


def _execute_run(config, plan, output, resume=False, make_report=True):
    output = Path(output).resolve()
    settings = config["settings"]
    validate_plan(plan, settings)
    output.mkdir(parents=True, exist_ok=True)
    scientific_settings = {
        k: v
        for k, v in settings.items()
        if k
        not in {
            "budget_minutes",
            "worker_timeout_seconds",
            "memory_limit_gib",
            "keep_arrays",
            "keep_inputs",
        }
    }
    probes = probe_implementations(config, output)
    signature = fingerprint(
        dict(
            plan=plan,
            versions=config["versions"],
            baseline=config["baseline"],
            gamma_options=config.get("gamma_options", {}),
            settings=scientific_settings,
            harness=harness_fingerprint(),
            probes=probes,
        )
    )
    state_path = output / "run_state.json"
    state = (
        read_json(state_path)
        if resume and state_path.exists()
        else dict(signature=signature, active_wall_seconds=0.0, started_at=utc_now())
    )
    if state["signature"] != signature:
        raise ValueError(
            "Plan, source, harness or scientific configuration changed. Use a new output directory."
        )
    write_json(output / "config.resolved.json", config)
    write_json(output / "plan.json", plan)
    if not (output / "environment.json").exists():
        write_json(output / "environment.json", environment_record())
    initial_elapsed = state["active_wall_seconds"]
    start = time.monotonic()
    remaining = settings["budget_minutes"] * 60 - initial_elapsed
    deadline = start + max(0, remaining) if settings["budget_minutes"] else None
    names = [s["name"] for s in config["versions"]]
    records = []
    run_status = "completed"
    summary = {}

    def checkpoint():
        state["active_wall_seconds"] = initial_elapsed + time.monotonic() - start
        state["updated_at"] = utc_now()
        state["status"] = run_status
        write_json(state_path, state)
        summary.update(
            schema_version=SCHEMA_VERSION,
            run_status=run_status,
            planned_cases=len(plan["cases"]),
            completed_cases=len(records),
            validated_cases=sum(r["status"] == "ok" for r in records),
            records=records,
            generated_at=utc_now(),
            baseline=config["baseline"],
            implementations=names,
            settings=settings,
        )
        write_json(output / "summary.json", summary)

    try:
        for case_number, case in enumerate(plan["cases"]):
            directory = output / "cases" / case["id"]
            directory.mkdir(parents=True, exist_ok=True)
            final_record = directory / "case.json"
            if resume and final_record.exists():
                record = read_json(final_record)
                if record["status"] in [
                    "ok",
                    "mismatch",
                    "error",
                    "timeout",
                    "memory_limit",
                ]:
                    records.append(record)
                    checkpoint()
                    continue
            if deadline and time.monotonic() >= deadline:
                run_status = "budget_exhausted"
                break
            fixture_path, kwargs, metadata = save_fixture(case, directory)
            kwargs = dict(config.get("gamma_options", {}), **kwargs)
            per_variant = {name: [] for name in names}
            order = list(names)
            random.Random(settings["seed"] + case_number).shuffle(order)
            print(
                f"[{case_number + 1}/{len(plan['cases'])}] {case['id']} ({case['n']}^{case['dimension']})",
                flush=True,
            )
            for round_index in range(plan["repeats"]):
                # Rotate implementation position each matched round.
                this_order = (
                    order[round_index % len(order) :]
                    + order[: round_index % len(order)]
                )
                for position, name in enumerate(this_order):
                    spec = next(s for s in config["versions"] if s["name"] == name)
                    result_path = directory / f"{name}-{round_index}.json"
                    array_path = directory / f"{name}-{round_index}.npz"
                    if (
                        resume
                        and result_path.exists()
                        and array_path.exists()
                        and read_json(result_path).get("status") == "ok"
                    ):
                        result = read_json(result_path)
                    else:
                        job = dict(
                            implementation=spec,
                            case=case,
                            gamma_kwargs=kwargs,
                            fixture_path=str(fixture_path),
                            result_path=str(result_path),
                            output_path=str(array_path),
                            representative_path=str(
                                directory / f"{name}-{round_index}-representative.npz"
                            ),
                            phase_path=str(
                                directory / f"{name}-{round_index}.phase.json"
                            ),
                            cache_dir=str(output / "cache" / name),
                            warmups=settings["warmups"],
                            repeatability_atol=settings["repeatability_atol"],
                            round=round_index,
                            order_position=position,
                        )
                        result = run_worker(
                            job,
                            settings["worker_timeout_seconds"],
                            settings["memory_limit_gib"] * 1024**3,
                            settings["memory_sample_interval_ms"] / 1000,
                            deadline,
                        )
                    if (
                        result.get("status") == "ok"
                        and provenance_identity(result.get("provenance", {}))
                        != probes[name]
                    ):
                        result = dict(
                            result,
                            status="error",
                            provenance_changed=True,
                            error="PyMedPhys source, environment, or interpolator changed after the initial provenance probe. Keep the selected versions fixed and use a new output directory.",
                        )
                        write_json(result_path, result)
                    per_variant[name].append(result)
                    checkpoint()
                    print(
                        f"  round {round_index + 1} {name}: {result['status']}"
                        + (
                            f" {result['seconds']:.4g} s" if "seconds" in result else ""
                        ),
                        flush=True,
                    )
                    if result["status"] == "budget_exhausted":
                        run_status = "budget_exhausted"
                        break
                    if result.get("provenance_changed"):
                        run_status = "failed"
                        break
                if run_status != "completed":
                    break
            record = aggregate_case(
                case, metadata, per_variant, directory, config, plan["repeats"], output
            )
            write_json(final_record, record)
            records.append(record)
            checkpoint()
            if run_status != "budget_exhausted":
                if not settings["keep_arrays"]:
                    for name in names:
                        for round_index in range(plan["repeats"]):
                            (directory / f"{name}-{round_index}.npz").unlink(
                                missing_ok=True
                            )
                if not settings["keep_inputs"]:
                    fixture_path.unlink(missing_ok=True)
            if run_status != "completed":
                break
        if run_status == "completed" and any(r["status"] != "ok" for r in records):
            run_status = "completed_with_failures"
    except KeyboardInterrupt:
        run_status = "interrupted"
    except Exception:
        run_status = "failed"
        raise
    finally:
        checkpoint()
        export_tables(output, summary)
    if make_report:
        from .report import build_report

        build_report(output)
    return summary
