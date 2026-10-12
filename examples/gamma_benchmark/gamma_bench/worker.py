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

"""Isolated worker. Only the controller invokes this module."""

from __future__ import annotations

import gc
import importlib.metadata
import os
import platform
import sys
import time
import traceback
from pathlib import Path

from .common import read_json, utc_now, write_json


def configure_environment(job):
    # Set thread settings before importing any numerical library.
    case = job["case"]
    thread_keys = (
        "NUMBA_NUM_THREADS",
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    os.environ.update({key: str(case["threads"]) for key in thread_keys})
    os.environ["NUMBA_CACHE_DIR"] = job["cache_dir"]
    return thread_keys


def provenance_for(spec, thread_keys):
    from .pymedphys_api import implementation_provenance

    provenance = implementation_provenance(spec)
    provenance.update(
        python=sys.version,
        executable=sys.executable,
        platform=platform.platform(),
        thread_environment={key: os.environ[key] for key in thread_keys},
    )
    provenance["packages"] = {
        dist.metadata["Name"]: dist.version
        for dist in importlib.metadata.distributions()
        if dist.metadata["Name"]
    }
    return provenance


def execute(job):
    thread_keys = configure_environment(job)
    spec, case = job["implementation"], job["case"]
    import hashlib
    import numpy as np
    import psutil
    from .pymedphys_api import prepare_call

    process = psutil.Process()
    phase_path = Path(job["phase_path"])

    def phase(name):
        rss = process.memory_info().rss
        write_json(phase_path, {"phase": name, "rss_bytes": rss, "at": utc_now()})
        return rss

    phase("loading")
    with np.load(job["fixture_path"], allow_pickle=False) as fixture:
        axes_r = tuple(
            fixture[f"reference_axis_{i}"].copy() for i in range(case["dimension"])
        )
        axes_e = tuple(
            fixture[f"evaluation_axis_{i}"].copy() for i in range(case["dimension"])
        )
        reference, evaluation = (
            fixture["reference_dose"].copy(),
            fixture["evaluation_dose"].copy(),
        )
    # Inputs are read-only: mutation is a benchmark-contract failure.
    for array in (*axes_r, *axes_e, reference, evaluation):
        array.setflags(write=False)
    arguments = (axes_r, reference, axes_e, evaluation)
    function, call_args, call_kwargs, normalise = prepare_call(
        spec, arguments, job["gamma_kwargs"]
    )
    provenance = provenance_for(spec, thread_keys)
    phase("first_call")
    started = time.perf_counter()
    raw = function(*call_args, **call_kwargs)
    first_seconds = time.perf_counter() - started
    phase("idle")
    warm, _ = normalise(raw)
    warm_path = Path(job["output_path"]).with_suffix(".warmup.npz")
    np.savez(warm_path, **warm)
    del raw, warm
    for _ in range(job["warmups"] - 1):
        phase("warmup")
        raw = function(*call_args, **call_kwargs)
        phase("idle")
        del raw
    gc.collect()
    pre_rss = phase("timed")
    started_at = utc_now()
    start = time.perf_counter()
    raw = function(*call_args, **call_kwargs)
    elapsed = time.perf_counter() - start
    post_rss = phase("idle")
    outputs, _ = normalise(raw)
    repeatable = True
    max_repeat_difference = 0.0
    with np.load(warm_path, allow_pickle=False) as warm:
        if set(warm.files) != set(outputs):
            repeatable = False
        else:
            for key, values in outputs.items():
                old = warm[key]
                finite = np.isfinite(values) & np.isfinite(old)
                if finite.any():
                    max_repeat_difference = max(
                        max_repeat_difference,
                        float(np.max(np.abs(values[finite] - old[finite]))),
                    )
                repeatable &= bool(
                    np.allclose(
                        values,
                        old,
                        rtol=0,
                        atol=job["repeatability_atol"],
                        equal_nan=True,
                    )
                )
                repeatable &= bool(np.array_equal(values <= 1, old <= 1))
    warm_path.unlink()
    np.savez(job["output_path"], **outputs)
    digest = hashlib.sha256()
    for key, values in sorted(outputs.items()):
        digest.update(key.encode())
        digest.update(str(values.shape).encode())
        digest.update(str(values.dtype).encode())
        digest.update(np.ascontiguousarray(values).tobytes())
    selected_key = sorted(outputs)[0]
    values = outputs[selected_key]
    finite_gamma = values[np.isfinite(values)]
    # Keep the sampled distribution and full-array histogram outside the timer.
    sample = (
        finite_gamma[
            np.linspace(
                0,
                max(finite_gamma.size - 1, 0),
                min(5000, finite_gamma.size),
                dtype=int,
            )
        ]
        if finite_gamma.size
        else np.array([])
    )
    maximum = max(1.05, float(finite_gamma.max())) if finite_gamma.size else 1.05
    hist, edges = np.histogram(finite_gamma, bins=np.linspace(0, maximum, 81))

    def middle(array):
        return array[array.shape[0] // 2, ...] if array.ndim == 3 else array

    np.savez_compressed(
        job["representative_path"],
        reference_slice=middle(reference),
        evaluation_slice=middle(evaluation),
        gamma_slice=middle(values),
        finite_gamma_sample=sample,
        gamma_hist_counts=hist,
        gamma_hist_edges=edges,
        criterion=np.array(selected_key),
    )
    phase("complete")
    return dict(
        status="ok",
        seconds=elapsed,
        first_call_seconds=first_seconds,
        started_at=started_at,
        pre_gamma_rss_bytes=pre_rss,
        post_gamma_rss_bytes=post_rss,
        worker_pid=os.getpid(),
        output_sha256=digest.hexdigest(),
        provenance=provenance,
        repeatable=repeatable,
        max_repeat_difference=max_repeat_difference,
        representative_file=job["representative_path"],
        selected_criterion=selected_key,
    )


def main():
    job = read_json(sys.argv[1])
    try:
        if job.get("mode") == "probe":
            thread_keys = configure_environment(job)
            result = {
                "status": "ok",
                "provenance": provenance_for(job["implementation"], thread_keys),
            }
        else:
            result = execute(job)
    except Exception as exc:
        result = {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    write_json(job["result_path"], result)
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
