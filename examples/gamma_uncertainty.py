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

"""A fixed, bounded design for repeatability and runtime-model uncertainty."""

import copy
import itertools
import json
import math
import random
import time

import gamma_scaling as study
from gamma_scaling_worker import SCENARIOS

# Shared four-way allowances include preparation, warm-ups and verification.
CORE_LIMITS = {2: (35, 40, 45), 3: (35, 40, 55, 100)}
CALIBRATION = {
    "2d": (1.0, 45, 30),
    "3d": (0.3, 100, 65),
    "diagnostic": (0.05, 45, 30),
}
DIAGNOSTIC_SECONDS = 45
SCENARIO_SECONDS = 300
EXPECTED_GROUPS = 84
SEED = 2066


def diagnostic_case(scale, padding, width_scale, difficulty):
    base = [max(9, n // 2 * 2 + 1) for n in study.shape_for(3, scale)]
    shape = [2 * math.ceil((n - 1) / 2 * padding) + 1 for n in base]
    return {
        "shape": shape,
        "comparison_seconds": DIAGNOSTIC_SECONDS,
        "model_geometry": {
            "base_shape": base,
            "padding": padding,
            "width_scale": width_scale,
            "difficulty": difficulty,
        },
    }


def design(selections):
    """Freeze all workloads before measuring; distribute repeats over time."""
    core, other, cases = [], [], {}
    for dimension, limits in CORE_LIMITS.items():
        count = len(limits)
        scales = [
            float(f"{selections[f'{dimension}d'] / 3**power:.8g}")
            for power in reversed(range(count))
        ]
        if len({study.shape_for(dimension, scale) for scale in scales}) != count:
            raise ValueError("Calibrated sizes must remain distinct")
        for scale, limit in zip(scales, limits):
            case = [dimension, "global", scale]
            (core if dimension == 3 else other).append(case)
            cases[study.case_id(*case)] = {"comparison_seconds": limit}
    for index, (padding, width, difficulty) in enumerate(
        itertools.product((1.0, 1.5), (0.35, 0.65), ("easy", "hard")), 1
    ):
        case = [3, "diagnostic", float(index)]
        other.append(case)
        cases[study.case_id(*case)] = diagnostic_case(
            selections["diagnostic"], padding, width, difficulty
        )
    for name, spec in SCENARIOS.items():
        case = [3, name, 1.0]
        other.append(case)
        cases[study.case_id(*case)] = {
            "scenario": name,
            "shape": list(spec["shape"]),
            "spacing_mm": spec["spacing_mm"],
            "distance_mm_threshold": 3,
            "comparison_seconds": SCENARIO_SECONDS,
        }
    rng = random.Random(SEED)
    plan = []
    for round_index in range(8):
        batch = [case + [round_index] for case in core]
        if round_index % 2 == 0:
            batch += [case + [round_index // 2] for case in other]
        rng.shuffle(batch)
        plan.extend(batch)
    return plan, cases


def maximum_measurement_seconds():
    return (
        3 * sum(limit for _, limit, _ in CALIBRATION.values())
        + 8 * sum(CORE_LIMITS[3])
        + 4 * sum(CORE_LIMITS[2])
        + 8 * 4 * DIAGNOSTIC_SECONDS
        + len(SCENARIOS) * 4 * SCENARIO_SECONDS
    )


def validate_plan(config, selections):
    expected_plan, expected_cases = design(selections)
    if config["plan"] != expected_plan or config["cases"] != expected_cases:
        raise ValueError("Resume requires the original calibrated uncertainty plan")


def calibrate(config, roots, output, host, cloud, stop_file, deadline):
    # Import here to share the result schema without a module import cycle.
    from gamma_performance_audit import empty_result

    path = output / "calibration.json"
    record = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {"probes": [], "selections": {}}
    )
    for family, (initial, limit, target) in CALIBRATION.items():
        if family in record["selections"]:
            continue
        scale, successful = initial, []
        for index in range(3):
            if time.monotonic() >= deadline or (stop_file and stop_file.exists()):
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
                dimension = 2 if family == "2d" else 3
                profile = "diagnostic" if family == "diagnostic" else "global"
                case = [dimension, profile, scale]
                options = (
                    diagnostic_case(scale, 1.5, 0.65, "hard")
                    if family == "diagnostic"
                    else {"comparison_seconds": limit}
                )
                probe_config = copy.deepcopy(config)
                probe_config.update(
                    plan=[case + [index]], cases={study.case_id(*case): options}
                )
                probe = empty_result(probe_config, host, cloud)
                probe_output = output / "calibration" / f"{family}-{index}"
                probe_output.mkdir(parents=True, exist_ok=True)
                print(
                    f"Uncertainty calibration {family}: {scale:g}x; shared limit {limit} s",
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
                if probe.get("stop_reason") or (stop_file and stop_file.exists()):
                    record.setdefault("interrupted_probes", []).append(previous)
                    study.write_json(path, record)
                    return None
                record["probes"].append(previous)
                study.write_json(path, record)
            scale = previous["scale"]
            fits = previous["result"]["complete"] and previous["wall_seconds"] <= target
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
                f"{family} calibration could not complete within {target} seconds; no full audit claimed"
            )
        record["selections"][family] = max(successful)
        study.write_json(path, record)
    return record["selections"]
