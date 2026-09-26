# Copyright (C) 2026 Matthew Jennings
# Licensed under the Apache License, Version 2.0.
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


def dose_field(axes, shift=None, scale=1.0):
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


def inputs(config):
    ndim = config["dimension"]
    extents = (50, 70, 70) if ndim == 3 else (100, 100)
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
