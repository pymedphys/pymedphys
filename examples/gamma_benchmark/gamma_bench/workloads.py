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

"""Deterministic inputs shared across PyMedPhys gamma versions.

This module generates arrays and experiment plans only. It never imports or
calls a gamma implementation, starts a timer, or changes thread settings.
Coordinates are millimetres and dose is in arbitrary units with a fixed
normalisation of 100. A case ID describes parameters, not measured results.
"""

from __future__ import annotations

import hashlib
import json
import math
from itertools import product

import numpy as np

from .common import SCHEMA_VERSION

NORMALISATION = 100.0


def case_id(case: dict) -> str:
    """Hash semantic parameters; names and membership of studies are excluded."""
    parameters = {
        key: value
        for key, value in case.items()
        if key not in {"id", "study", "studies", "notes"}
    }
    canonical = json.dumps(
        parameters, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{case.get('study', 'custom')}-d{case['dimension']}-n{case['n']}-{digest}"


def _baseline(dimension: int, n: int) -> dict:
    return {
        "dimension": dimension,
        "n": n,
        "grid_mode": "fixed_extent",
        "extent_mm": 80.0,
        "spacing_mm": 1.0,
        "evaluation_padding_mm": 6.0,
        "field": "gaussian",
        "field_width_mm": 18.4,
        "fraction_mode": "fixed_cutoff",
        "above_fraction_target": None,
        "lower_percent_dose_cutoff": 20.0,
        "dose_percent_threshold": 3.0,
        "distance_mm_threshold": 3.0,
        "interp_fraction": 10.0,
        "max_gamma": 2.0,
        "local_gamma": False,
        "ram_mib": 256,
        "threads": 1,
        "shift_mm": 1.0,
        "dose_scale": 1.01,
        "seed": 20261001,
    }


def make_plan(preset: str = "standard") -> dict:
    """Return a JSON-serialisable plan without generating or benchmarking inputs.

    Identical parameter combinations in different studies retain separate IDs
    so each study has its own baseline. Reference size sweeps keep physical
    extent and the analytic dose field fixed. The separate fixed-spacing
    family increases physical coverage as well as the number of points.
    """
    if preset not in {"quick", "standard", "thorough"}:
        raise ValueError("preset must be 'quick', 'standard', or 'thorough'")
    quick = preset == "quick"
    thorough = preset == "thorough"
    base_sizes = {2: 64 if quick else 96, 3: 20 if quick else 32}
    by_id: dict[str, dict] = {}

    def add(dimension: int, study: str, **updates) -> None:
        case = _baseline(dimension, base_sizes[dimension]) | updates | {"study": study}
        identifier = case_id(case)
        if identifier in by_id:
            if study not in by_id[identifier]["studies"]:
                by_id[identifier]["studies"].append(study)
            return
        by_id[identifier] = case | {
            "id": identifier,
            "study": study,
            "studies": [study],
        }

    sizes = {
        2: [32, 64, 96] if quick else [48, 96, 144, 192],
        3: [12, 20, 28] if quick else [16, 32, 48, 64],
    }
    if thorough:
        sizes = {2: [32, 48, 64, 96, 128, 192, 256], 3: [12, 16, 24, 32, 40, 48, 64]}

    for dimension in (2, 3):
        add(dimension, "baseline")
        for n in sizes[dimension]:
            add(dimension, "grid_size_fixed_extent", n=n)
        fractions = [0.15, 0.7] if quick else [0.05, 0.2, 0.5, 0.8]
        if thorough:
            fractions = [0.02, 0.05, 0.1, 0.2, 0.4, 0.6, 0.8, 0.95]
        for fraction in fractions:
            add(
                dimension,
                "cutoff_selection",
                fraction_mode="cutoff",
                above_fraction_target=fraction,
            )
        if quick and dimension == 3:
            continue
        for dta in [1.0, 5.0] if quick else [1.0, 2.0, 3.0, 5.0]:
            add(dimension, "distance_threshold", distance_mm_threshold=dta)
        for interpolation in [5.0, 20.0] if quick else [5.0, 10.0, 20.0, 40.0]:
            add(dimension, "interpolation_resolution", interp_fraction=interpolation)
        for cap in [None] if quick else [1.1, 2.0, 4.0, None]:
            add(dimension, "search_cap", max_gamma=cap)
        for fraction in [0.3] if quick else [0.1, 0.3, 0.7]:
            add(
                dimension,
                "field_width_fixed_cutoff",
                fraction_mode="width",
                above_fraction_target=fraction,
            )
        if quick:
            add(dimension, "mismatch", shift_mm=3.0, dose_scale=1.05)
            add(
                dimension,
                "size_by_fraction",
                n=32,
                fraction_mode="cutoff",
                above_fraction_target=0.7,
            )
            add(
                dimension,
                "distance_by_interpolation",
                distance_mm_threshold=1.0,
                interp_fraction=20.0,
            )
            continue
        for shift, scale in [(0.0, 1.0), (0.5, 1.01), (3.0, 1.05)]:
            add(dimension, "mismatch", shift_mm=shift, dose_scale=scale)
        matrix_sizes = sizes[dimension][::2] if not thorough else sizes[dimension][1::2]
        matrix_fractions = [0.1, 0.7] if not thorough else [0.05, 0.2, 0.5, 0.8]
        for n, fraction in product(matrix_sizes, matrix_fractions):
            add(
                dimension,
                "size_by_fraction",
                n=n,
                fraction_mode="cutoff",
                above_fraction_target=fraction,
            )
        dtas = [1.0, 5.0] if not thorough else [1.0, 2.0, 3.0, 5.0]
        interpolations = [5.0, 20.0] if not thorough else [5.0, 10.0, 20.0, 40.0]
        for dta, interpolation in product(dtas, interpolations):
            add(
                dimension,
                "distance_by_interpolation",
                distance_mm_threshold=dta,
                interp_fraction=interpolation,
            )
        for cap, shift in product(
            [1.1, None] if not thorough else [1.1, 2.0, 4.0, None], [0.0, 3.0]
        ):
            add(
                dimension,
                "cap_by_mismatch",
                max_gamma=cap,
                shift_mm=shift,
                dose_scale=1.0 if shift == 0 else 1.05,
            )
        for field in ["double", "plateau"]:
            add(dimension, "field_shape", field=field)
        add(dimension, "normalisation", local_gamma=True)
        for ram_mib in [32, 1024] if not thorough else [16, 32, 128, 1024]:
            add(dimension, "memory_budget", ram_mib=ram_mib)
        for threads in [2, 4] if not thorough else [2, 4, 8]:
            add(dimension, "thread_count", threads=threads)
        add(
            dimension,
            "multiple_criteria",
            dose_percent_threshold=[2.0, 3.0],
            distance_mm_threshold=[1.0, 3.0],
        )
        if thorough:
            for n in sizes[dimension][1::2]:
                add(
                    dimension,
                    "grid_growth_fixed_spacing",
                    n=n,
                    grid_mode="fixed_spacing",
                    spacing_mm=80.0 / (base_sizes[dimension] - 1),
                )
            for field, fraction in product(["double", "plateau"], [0.1, 0.5, 0.8]):
                add(
                    dimension,
                    "shape_by_fraction",
                    field=field,
                    fraction_mode="cutoff",
                    above_fraction_target=fraction,
                )
            for field, fraction in product(["double", "plateau"], [0.1, 0.5]):
                add(
                    dimension,
                    "shape_by_width",
                    field=field,
                    fraction_mode="width",
                    above_fraction_target=fraction,
                )

    return {
        "schema_version": SCHEMA_VERSION,
        "preset": preset,
        "repeats": {"quick": 3, "standard": 5, "thorough": 7}[preset],
        "cases": list(by_id.values()),
        "notes": [
            "Plans contain synthetic workloads, not measured performance or clinical validation.",
            "Grid-size sweeps keep physical extent, field width, displacement, and nominal dose fixed; spacing changes.",
            "Cutoff-selection sweeps reuse identical dose fields; the eligible set changes and includes all ties at the selected dose.",
            "Field-width sweeps change the dose field at a fixed cutoff; their gradients and mismatch difficulty also change.",
            "Fixed-spacing growth changes both physical coverage and point count and is a separate study.",
            "Evaluation padding is physical, rounded upwards to whole intervals; evaluation point counts therefore change with grid spacing.",
            "The explicit global normalisation is 100 dose units for every workload; local mode still uses that value for the lower cutoff.",
            "shift_mm is the norm of a physical field displacement, not a translation of either coordinate grid.",
            "RAM and thread counts are requested controls; each PyMedPhys version receives the same settings, which are recorded with the results.",
            "max_gamma, interp_fraction, random_subset, and skip_once_passed alter requested work or result semantics; compare like-for-like settings.",
            "Case IDs combine study names and parameter hashes; identical cases in different studies retain separate measurements.",
        ],
    }


def _positive(value, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _field(
    axes: tuple[np.ndarray, ...], name: str, width: float, shift: np.ndarray
) -> np.ndarray:
    """Analytic fields sampled directly, without resampling either dose array."""
    dimensions = len(axes)
    scales = np.array([1.0, 0.8, 1.15])[:dimensions]
    coordinates = [
        ((axis - shift[index]) / (width * scales[index])).reshape(
            (1,) * index + (axis.size,) + (1,) * (dimensions - index - 1)
        )
        for index, axis in enumerate(axes)
    ]
    if name == "gaussian":
        return NORMALISATION * np.exp(
            -0.5 * sum(coordinate**2 for coordinate in coordinates)
        )
    if name == "plateau":
        return NORMALISATION * np.exp(
            -0.5 * sum(coordinate**8 for coordinate in coordinates)
        )
    if name == "double":
        transverse = sum(coordinate**2 for coordinate in coordinates[1:])
        # Fixed physical centres keep widening monotone at every point;
        # changing width does not also move the two peaks.
        first = np.exp(
            -0.5 * (((coordinates[0] + 12.0 / width) / 0.65) ** 2 + transverse)
        )
        second = np.exp(
            -0.5 * (((coordinates[0] - 12.0 / width) / 0.65) ** 2 + transverse)
        )
        return NORMALISATION * (0.65 * first + 0.35 * second)
    raise ValueError("field must be 'gaussian', 'double', or 'plateau'")


def _select_cutoff(dose: np.ndarray, fraction: float) -> tuple[float, int]:
    target = math.ceil(fraction * dose.size)
    if target == 0:
        return float(np.nextafter(dose.max(), np.inf)), target
    cutoff = float(np.partition(dose.ravel(), dose.size - target)[dose.size - target])
    return cutoff, target


def make_inputs(case: dict) -> tuple[tuple, dict, dict]:
    """Return canonical gamma arguments, controls, and realised workload metadata.

    Thread settings are metadata for the runner to apply before loading the
    implementation. ``args`` contains tuples of float64 coordinate arrays and
    two C-contiguous dose arrays, suitable for an NPZ serialisation boundary.
    No gamma call or performance measurement occurs here.
    """
    dimension = case["dimension"]
    n = case["n"]
    if isinstance(dimension, bool) or dimension not in (2, 3):
        raise ValueError("dimension must be 2 or 3")
    if isinstance(n, bool) or not isinstance(n, int) or n < 2:
        raise ValueError("n must be an integer of at least 2")
    mode = case["grid_mode"]
    if mode == "fixed_extent":
        extent = _positive(case["extent_mm"], "extent_mm")
        spacing = extent / (n - 1)
    elif mode == "fixed_spacing":
        spacing = _positive(case["spacing_mm"], "spacing_mm")
        extent = spacing * (n - 1)
    else:
        raise ValueError("grid_mode must be 'fixed_extent' or 'fixed_spacing'")
    padding = float(case.get("evaluation_padding_mm", 6.0))
    if not math.isfinite(padding) or padding < 0:
        raise ValueError("evaluation_padding_mm must be finite and non-negative")
    padding_points = math.ceil(padding / spacing)
    axis = np.linspace(-extent / 2, extent / 2, n, dtype=np.float64)
    # An exact common interval avoids independently spaced evaluation grids.
    eval_axis = np.concatenate(
        (
            axis[0] + np.arange(-padding_points, 0, dtype=np.float64) * spacing,
            axis,
            axis[-1] + np.arange(1, padding_points + 1, dtype=np.float64) * spacing,
        )
    )
    reference_axes = tuple(axis.copy() for _ in range(dimension))
    evaluation_axes = tuple(eval_axis.copy() for _ in range(dimension))
    direction = np.array([1.0, -0.6, 0.3], dtype=np.float64)[:dimension]
    direction /= np.linalg.norm(direction)
    displacement = float(case["shift_mm"])
    if not math.isfinite(displacement):
        raise ValueError("shift_mm must be finite")
    shift = displacement * direction
    dose_scale = _positive(case["dose_scale"], "dose_scale")
    width = _positive(case.get("field_width_mm", 18.4), "field_width_mm")
    cutoff = float(case.get("lower_percent_dose_cutoff", 20.0))
    if not math.isfinite(cutoff) or cutoff < 0:
        raise ValueError("lower_percent_dose_cutoff must be finite and non-negative")
    fraction_mode = case["fraction_mode"]
    target_fraction = case.get("above_fraction_target")
    if fraction_mode in {"cutoff", "width"}:
        if (
            target_fraction is None
            or not math.isfinite(float(target_fraction))
            or not 0 <= target_fraction <= 1
        ):
            raise ValueError("above_fraction_target must be between 0 and 1")
    elif fraction_mode != "fixed_cutoff":
        raise ValueError("fraction_mode must be 'cutoff', 'width', or 'fixed_cutoff'")

    zeros = np.zeros(dimension)
    if fraction_mode == "width":
        if cutoff <= 0:
            raise ValueError("width selection requires a positive fixed cutoff")
        # Discrete counts form a staircase; retain the closest observed count.
        # Include both ends so target zero/one and unattainable ties are explicit.
        low, high = spacing / 1024, extent * 1024
        candidates = []
        for _ in range(48):
            current = math.sqrt(low * high)
            sampled = _field(reference_axes, case["field"], current, zeros)
            achieved = float(np.count_nonzero(sampled >= cutoff) / sampled.size)
            candidates.append((abs(achieved - target_fraction), current))
            if achieved < target_fraction:
                low = current
            else:
                high = current
        # Stable tie-break: prefer the narrower field.
        width = min(candidates)[1]

    reference_dose = np.ascontiguousarray(
        _field(reference_axes, case["field"], width, zeros), dtype=np.float64
    )
    evaluation_dose = np.ascontiguousarray(
        dose_scale * _field(evaluation_axes, case["field"], width, shift),
        dtype=np.float64,
    )
    target_points = None
    selected_dose_quantile = None
    if fraction_mode == "cutoff":
        cutoff, target_points = _select_cutoff(reference_dose, float(target_fraction))
        selected_dose_quantile = cutoff
        # Match the public percent-to-dose arithmetic. A one-ulp round-off
        # must not drop every point tied at the chosen quantile.
        if target_points:
            while cutoff / 100 * NORMALISATION > selected_dose_quantile:
                cutoff = float(np.nextafter(cutoff, -np.inf))
        else:
            while cutoff / 100 * NORMALISATION <= reference_dose.max():
                cutoff = float(np.nextafter(cutoff, np.inf))
    elif target_fraction is not None:
        target_points = math.ceil(float(target_fraction) * reference_dose.size)
    effective_dose_cutoff = cutoff / 100 * NORMALISATION
    eligible = reference_dose >= effective_dose_cutoff
    eligible_points = int(np.count_nonzero(eligible))

    def criterion(name):
        value = case[name]
        values = value if isinstance(value, list) else [value]
        if not values:
            raise ValueError(f"{name} cannot be empty")
        checked = [_positive(item, name) for item in values]
        return checked if isinstance(value, list) else checked[0]

    cap = case["max_gamma"]
    if cap is not None and (not math.isfinite(float(cap)) or cap <= 1):
        raise ValueError("max_gamma must be null or finite and greater than 1")
    threads = case["threads"]
    if isinstance(threads, bool) or not isinstance(threads, int) or threads < 1:
        raise ValueError("threads must be a positive integer")
    kwargs = {
        "dose_percent_threshold": criterion("dose_percent_threshold"),
        "distance_mm_threshold": criterion("distance_mm_threshold"),
        "lower_percent_dose_cutoff": cutoff,
        "interp_fraction": _positive(case["interp_fraction"], "interp_fraction"),
        "max_gamma": cap,
        "local_gamma": bool(case["local_gamma"]),
        "global_normalisation": NORMALISATION,
        "ram_available": int(_positive(case["ram_mib"], "ram_mib") * 2**20),
    }
    if kwargs["local_gamma"] and np.any(reference_dose[eligible] == 0):
        raise ValueError("local gamma cannot analyse zero reference dose")
    if case.get("random_subset") is not None:
        subset = case["random_subset"]
        if isinstance(subset, bool) or not isinstance(subset, int) or subset < 0:
            raise ValueError("random_subset must be a non-negative integer")
        kwargs.update(random_subset=subset, random_state=case["seed"])
    if "skip_once_passed" in case:
        kwargs["skip_once_passed"] = bool(case["skip_once_passed"])

    metadata = {
        "total_points": int(reference_dose.size),
        "evaluation_points": int(evaluation_dose.size),
        "eligible_points": eligible_points,
        "eligible_fraction": eligible_points / reference_dose.size,
        "above_fraction_target": target_fraction,
        "target_eligible_points": target_points,
        "cutoff_tie_points": int(
            np.count_nonzero(
                reference_dose
                == (
                    selected_dose_quantile
                    if selected_dose_quantile is not None
                    else effective_dose_cutoff
                )
            )
        ),
        "selected_dose_quantile": selected_dose_quantile,
        "effective_dose_cutoff": effective_dose_cutoff,
        "lower_percent_dose_cutoff": cutoff,
        "shape": list(reference_dose.shape),
        "evaluation_shape": list(evaluation_dose.shape),
        "spacing_mm": [spacing] * dimension,
        "extent_mm": [extent] * dimension,
        "evaluation_extent_mm": [float(eval_axis[-1] - eval_axis[0])] * dimension,
        "evaluation_padding_requested_mm": padding,
        "evaluation_padding_realised_mm": [padding_points * spacing] * dimension,
        "grid_mode": mode,
        "coordinate_order": "ij; axes match dose-array dimensions",
        "field_summary": {
            "name": case["field"],
            "width_mm": width,
            "axis_width_multipliers": [1.0, 0.8, 1.15][:dimension],
            "fraction_mode": fraction_mode,
            "shift_vector_mm": shift.tolist(),
            "dose_scale": dose_scale,
            "global_normalisation": NORMALISATION,
            "reference_dose_min": float(reference_dose.min()),
            "reference_dose_max": float(reference_dose.max()),
            "synthetic": True,
        },
        "requested_threads": threads,
        "seed": case["seed"],
        "selection_note": "Cutoff includes equality and all tied doses; achieved counts may differ from the requested fraction.",
    }
    return (
        (reference_axes, reference_dose, evaluation_axes, evaluation_dose),
        kwargs,
        metadata,
    )
