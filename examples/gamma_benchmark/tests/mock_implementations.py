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

"""Fabricated outputs for harness tests; no gamma algorithm is implemented."""

import os

_calls = 0
_buffer = None


def _result(reference, dose_threshold, distance_threshold, controls, value):
    import numpy as np

    cutoff = (
        controls["lower_percent_dose_cutoff"] / 100 * controls["global_normalisation"]
    )
    selected = reference >= cutoff
    subset = controls.get("random_subset")
    if subset is not None:
        indices = np.flatnonzero(selected)
        indices = np.random.default_rng(controls.get("random_state")).permutation(
            indices
        )
        selected = np.zeros(reference.size, dtype=bool)
        selected[indices[:subset]] = True
        selected = selected.reshape(reference.shape)
    result = np.full(reference.shape, np.nan)
    result[selected] = value
    pairs = [
        (float(d), float(r))
        for d in np.atleast_1d(dose_threshold)
        for r in np.atleast_1d(distance_threshold)
    ]
    return result if len(pairs) == 1 else {pair: result.copy() for pair in pairs}


def constant(
    axes_reference,
    dose_reference,
    axes_evaluation,
    dose_evaluation,
    dose_percent_threshold,
    distance_mm_threshold,
    **controls,
):
    """Return fabricated 0.5 values; one warm-up and one timed call per worker."""
    global _calls
    _calls += 1
    assert _calls <= 2, "The mock PyMedPhys package was reused across workers"
    assert not dose_reference.flags.writeable
    assert not dose_evaluation.flags.writeable
    assert all(not a.flags.writeable for a in (*axes_reference, *axes_evaluation))
    result = _result(
        dose_reference, dose_percent_threshold, distance_mm_threshold, controls, 0.5
    )
    assert os.environ.get("NUMBA_NUM_THREADS") == "2"
    assert os.environ.get("OMP_NUM_THREADS") == "2"
    return result


def shared_changing_buffer(
    axes_reference,
    dose_reference,
    axes_evaluation,
    dose_evaluation,
    dose_percent_threshold,
    distance_mm_threshold,
    **controls,
):
    """Reuse one output buffer and alter it, exposing mistaken warm-up aliasing."""
    global _calls, _buffer
    _calls += 1
    result = _result(
        dose_reference,
        dose_percent_threshold,
        distance_mm_threshold,
        controls,
        0.25 if _calls == 1 else 0.5,
    )
    if _buffer is None:
        _buffer = result
    else:
        _buffer[:] = result
    return _buffer


def mutates_input(
    axes_reference,
    dose_reference,
    axes_evaluation,
    dose_evaluation,
    dose_percent_threshold,
    distance_mm_threshold,
    **controls,
):
    """An accidental input mutation must fail under the worker contract."""
    dose_reference.flat[0] = -999
    return dose_reference


def raises_error(*args, **kwargs):
    raise RuntimeError("fabricated implementation failure")


def isolated_dependencies(*args, **kwargs):
    """Check bootstrap import isolation, then return the usual fabricated array."""
    import importlib.util
    from pathlib import Path
    import sys

    assert (
        importlib.util.find_spec("gamma_benchmark_forbidden_controller_dependency")
        is None
    )
    forbidden = Path(os.environ["FORBIDDEN_HARNESS_PARENT"]).resolve()
    search_paths = [Path(path).resolve() for path in sys.path if path]
    assert forbidden not in search_paths
    assert forbidden / "gamma_bench" not in search_paths
    return constant(*args, **kwargs)


gamma = constant
