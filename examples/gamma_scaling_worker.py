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

"""Isolated worker for gamma_scaling.py; timings exclude setup and checking."""

import hashlib
import importlib
import json
import os
import platform
import sys
import time
import warnings
from pathlib import Path

import numba
import numpy as np
import scipy
from scipy.special import erf

import pymedphys


def digest_arrays(arrays):
    digest = hashlib.sha256()
    for array in arrays:
        digest.update(memoryview(np.ascontiguousarray(array)).cast("B"))
    return digest.hexdigest()


def dose_field(axes, shift=None, scale=1.0, width_scale=1.0):
    """Sample one continuous Gaussian-blurred box model at any resolution.

    Nominal dose scale is 2 Gy; the fixed normalisation is independent of the
    sampled maximum. Sparse broadcasting avoids three full coordinate meshes.
    """
    ndim = len(axes)
    shift = (0.0,) * ndim if shift is None else shift
    dose = np.zeros(tuple(len(axis) for axis in axes), dtype=np.float64)
    boxes = [
        ((40, 60, 25), (0, 0, 0), 1.0),
        ((55, 30, 45), (0, 0, 0), 0.8),
        ((15, 15, 15), (5, -8, 4), 0.6),
    ]
    for widths, centre, weight in boxes:
        factors = []
        for dimension, (axis, half, origin, offset) in enumerate(
            zip(axes, widths, centre, shift)
        ):
            half, origin = half * width_scale, origin * width_scale
            coordinate = axis - origin - offset
            factor = 0.5 * (
                erf((coordinate + half) / (6 * np.sqrt(2)))
                - erf((coordinate - half) / (6 * np.sqrt(2)))
            )
            shape = [1] * ndim
            shape[dimension] = len(axis)
            factors.append(factor.reshape(shape))
        product = factors[0]
        for factor in factors[1:]:
            product = product * factor
        dose += weight * product
    return (2.0 * scale / 2.4) * dose


SCENARIOS = {
    "sabr": {"shape": (201, 241, 241), "spacing_mm": 1.25},
    "prostate-nodes": {"shape": (201, 161, 161), "spacing_mm": 2.5},
}


def scenario_field(axes, scenario, shift=(0, 0, 0), scale=1.0):
    """Analytic workload proxies, without patient anatomy or calculated dose.

    Ellipsoidal plateaux have smooth edges and a broad low-dose component.
    Coordinates, radii and Gaussian widths are in mm, in (z, y, x) order.
    Edge smoothing is referenced to the shortest semi-axis; the transition
    is broader along longer semi-axes, not a constant normal-distance blur.
    The fixed 2 Gy amplitude is a benchmark normalisation, not a prescription.
    """
    coordinates = np.ogrid[tuple(slice(0, n) for n in map(len, axes))]
    coordinates = [
        axis[index] - offset for axis, index, offset in zip(axes, coordinates, shift)
    ]

    def plateau(centre, radii, sigma):
        radius = np.sqrt(
            sum(((c - o) / r) ** 2 for c, o, r in zip(coordinates, centre, radii))
        )
        return 0.5 * (1 - erf((radius - 1) * min(radii) / (sigma * np.sqrt(2))))

    if scenario == "sabr":
        core = plateau((0, 0, 0), (20, 18, 16), 3)
        widths, amplitude = (50, 60, 60), 0.15
    elif scenario == "prostate-nodes":
        core = plateau((-120, 0, 0), (30, 25, 30), 6)
        for lateral in (-35, 35):
            core = np.maximum(core, 0.7 * plateau((15, 5, lateral), (110, 18, 18), 6))
        widths, amplitude = (140, 65, 90), 0.2
    else:
        raise ValueError("Unknown synthetic scenario")
    halo = amplitude * np.exp(
        -0.5 * sum((c / width) ** 2 for c, width in zip(coordinates, widths))
    )
    return 2 * scale * (core + halo) / (1 + amplitude)


def inputs(config):
    ndim = config["dimension"]
    extents = (50, 70, 70) if ndim == 3 else (100, 100)
    scenario = config.get("scenario")
    geometry = config.get("model_geometry")
    if geometry:
        # Padding retains every original grid coordinate and the same spacing.
        axes = tuple(
            (np.arange(n, dtype=np.float64) - (n - 1) / 2) * (2 * extent / (base - 1))
            for n, base, extent in zip(
                config["shape"], geometry["base_shape"], (60, 80, 80)
            )
        )
        reference = dose_field(axes, width_scale=geometry["width_scale"])
        difficult = geometry["difficulty"] == "hard"
        evaluation = dose_field(
            axes,
            shift=(4, -5, 2) if difficult else (0.375, -0.5, 0.1875),
            scale=1.08 if difficult else 1.005,
            width_scale=geometry["width_scale"],
        )
        if any(
            np.any(np.take(reference, [0, -1], axis=axis) >= 0.2)
            for axis in range(ndim)
        ):
            raise ValueError("Diagnostic reference field reaches the grid boundary")
    elif scenario:
        specification = SCENARIOS[scenario]
        if tuple(config["shape"]) != specification["shape"]:
            raise ValueError(
                "Scenario grid must retain its documented spacing and extent"
            )
        axes = tuple(
            (np.arange(n, dtype=np.float64) - (n - 1) / 2) * specification["spacing_mm"]
            for n in specification["shape"]
        )
        reference = scenario_field(axes, scenario)
        evaluation = scenario_field(axes, scenario, shift=(1.5, -2.0, 0.75), scale=1.02)
    else:
        axes = tuple(
            np.linspace(-extent, extent, count, dtype=np.float64)
            for extent, count in zip(extents, config["shape"])
        )
        reference = dose_field(axes)
        evaluation = dose_field(axes, shift=(1.5, -2.0, 0.75)[:ndim], scale=1.02)
    options = {
        "dose_percent_threshold": 3,
        "distance_mm_threshold": 3,
        "lower_percent_dose_cutoff": 10,
        "interp_fraction": 10,
        "global_normalisation": 2.0,
        "skip_once_passed": False,
        "random_subset": None,
        "ram_available": config["ram_bytes"],
        "interp_algo": config["algorithm"],
    }
    if config["profile"] == "local":
        options.update(
            dose_percent_threshold=2, distance_mm_threshold=2, local_gamma=True
        )
    if config["profile"] == "cap2":
        options["max_gamma"] = 2
    if geometry:
        options["max_gamma"] = 2
    if scenario:
        options["distance_mm_threshold"] = config.get("distance_mm_threshold", 2)
    return axes, reference, evaluation, options


def main():
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    root = Path(config["checkout"]).resolve(strict=True)
    origins = {}
    for name in (
        "pymedphys",
        "pymedphys._gamma.implementation.shell",
        "pymedphys._interp.interp",
    ):
        origin = Path(importlib.import_module(name).__file__).resolve()
        if not origin.is_relative_to(root / "lib/pymedphys"):
            raise RuntimeError(
                f"Incorrect import: {name} from {origin}, expected {root}"
            )
        origins[name] = origin.relative_to(root).as_posix()
    warnings.simplefilter("error")
    axes, reference, evaluation, options = inputs(config)
    input_hash = digest_arrays((*axes, reference, evaluation))
    warmup_start = time.perf_counter()
    expected = pymedphys.gamma(axes, reference, axes, evaluation, **options)
    warmup_seconds = time.perf_counter() - warmup_start
    times = []
    for _ in range(config["repeats"]):
        start = time.perf_counter()
        gamma = pymedphys.gamma(axes, reference, axes, evaluation, **options)
        times.append(time.perf_counter() - start)
        # Every timed call must reproduce the full warm-up array exactly.
        for start in range(0, gamma.size, 1_000_000):
            np.testing.assert_array_equal(
                gamma.ravel()[start : start + 1_000_000],
                expected.ravel()[start : start + 1_000_000],
            )
    np.save(config["array_path"], gamma, allow_pickle=False)
    peak_rss = None
    if sys.platform != "win32":
        import resource

        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            peak_rss *= 1024
    print(
        json.dumps(
            {
                "times": times,
                "warmup_seconds": warmup_seconds,
                "shape": list(gamma.shape),
                "points": int(gamma.size),
                "eligible_points": int(np.count_nonzero(reference >= 0.2)),
                "finite_points": int(np.isfinite(gamma).sum()),
                "nan_points": int(np.isnan(gamma).sum()),
                "pass_points": int(np.count_nonzero(gamma <= 1)),
                "input_sha256": input_hash,
                "gamma_sha256": digest_arrays((gamma,)),
                "repeat_equality": True,
                "options": options,
                "model_geometry": config.get("model_geometry"),
                "origins": origins,
                "python": sys.version,
                "platform": platform.platform(),
                "versions": {
                    "numpy": np.__version__,
                    "scipy": scipy.__version__,
                    "numba": numba.__version__,
                },
                "numba_threads": numba.get_num_threads(),
                "thread_environment": {
                    name: os.environ.get(name)
                    for name in (
                        "NUMBA_NUM_THREADS",
                        "OMP_NUM_THREADS",
                        "OPENBLAS_NUM_THREADS",
                        "MKL_NUM_THREADS",
                    )
                },
                "peak_process_rss_bytes": peak_rss,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
