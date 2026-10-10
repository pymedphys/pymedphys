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

"""Load the selected PyMedPhys version and check its gamma result structure.

Each version runs in a fresh worker process. A selected checkout must supply
the imported package; an installed package is used only when checkout is null.
The parent selects Python and thread settings before numerical imports. The
interpolator is an explicit per-version factor; other gamma options are shared.
"""

from collections.abc import Mapping
import hashlib
import importlib
import inspect
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys


_CRITERIA = ("dose_percent_threshold", "distance_mm_threshold")
_SOURCE_SUFFIXES = {".py", ".pyi", ".pyx", ".pxd"}
_BUILD_FILES = {"pyproject.toml", "setup.cfg"}
_EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
}


def interpolation_algorithm(spec):
    """Validate the only per-version gamma option, without importing PyMedPhys."""
    algorithm = spec.get("interp_algo", "pymedphys")
    if not isinstance(algorithm, str) or algorithm not in ("pymedphys", "scipy"):
        raise ValueError("Per-version interp_algo must be 'pymedphys' or 'scipy'")
    return algorithm


def criterion_key(dose, distance):
    """Give equivalent scalar criteria a stable, JSON-safe identity."""
    values = []
    for name, value in zip(_CRITERIA, (dose, distance)):
        if isinstance(value, (bool, str, bytes)):
            raise ValueError(f"{name} must be a finite positive number")
        try:
            number = float(value)
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError(f"{name} must be a finite positive number") from error
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"{name} must be a finite positive number")
        values.append(repr(number))
    return f"dose={values[0]};distance={values[1]}"


def _checkout_paths(spec):
    unexpected = set(spec) - {"name", "checkout", "python", "interp_algo"}
    if unexpected:
        raise ValueError(
            f"Unsupported version options: {', '.join(sorted(unexpected))}"
        )
    interpolation_algorithm(spec)
    raw_checkout = spec.get("checkout")
    if raw_checkout is None:
        return None, None
    checkout = Path(raw_checkout).expanduser().resolve()
    for root in (checkout / "lib", checkout):
        if (root / "pymedphys" / "__init__.py").is_file():
            return checkout, root
    raise ValueError(
        f"Checkout does not contain lib/pymedphys or pymedphys: {checkout}"
    )


def load_callable(spec):
    """Return only ``pymedphys.gamma`` from the selected version.

    The source import root remains available for lazy package imports. Previously
    imported packages are not unloaded; a conflicting loaded package causes an
    error rather than a silent fallback. The parent selects the interpreter.
    """
    checkout, root = _checkout_paths(spec)
    if root is not None:
        path = str(root)
        sys.path[:] = [path] + [item for item in sys.path if item != path]
    importlib.invalidate_caches()
    module = importlib.import_module("pymedphys")
    if root is not None:
        loaded_file = getattr(module, "__file__", None)
        expected_package = (root / "pymedphys").resolve()
        if not loaded_file or not Path(loaded_file).resolve().is_relative_to(
            expected_package
        ):
            raise ImportError(
                f"Loaded pymedphys is outside selected checkout {checkout}: {loaded_file}"
            )
    implementation = getattr(module, "gamma")
    if not callable(implementation):
        raise TypeError("pymedphys.gamma is not callable")
    return implementation


def _canonical_call(args, kwargs):
    import numpy as np

    args = tuple(args)
    controls = dict(kwargs)
    if len(args) == 4:
        missing = [name for name in _CRITERIA if name not in controls]
        if missing:
            raise ValueError(f"Missing gamma criteria: {', '.join(missing)}")
        args += tuple(controls.pop(name) for name in _CRITERIA)
    elif len(args) == 6:
        if any(name in controls for name in _CRITERIA):
            raise ValueError(
                "Gamma criteria were supplied both positionally and by keyword"
            )
    else:
        raise ValueError(
            "Gamma invocation requires four grid arguments and two criteria"
        )

    criteria = []
    for name, values in zip(_CRITERIA, args[4:]):
        values = np.asarray(values)
        if values.ndim > 1 or values.size == 0 or values.dtype.kind not in "iuf":
            raise ValueError(f"{name} must be a number or a non-empty 1D numeric array")
        values = np.atleast_1d(values)
        if not np.all(np.isfinite(values)) or not np.all(values > 0):
            raise ValueError(f"{name} must contain finite positive values")
        if len(set(float(value) for value in values)) != values.size:
            raise ValueError(f"{name} must not contain duplicate criteria")
        criteria.append(values)
    expected = [
        criterion_key(dose, distance)
        for dose in criteria[0]
        for distance in criteria[1]
    ]
    return args, controls, expected


def _normalise_result(result, expected, reference_shape):
    import numpy as np

    outputs = {}
    if isinstance(result, Mapping):
        for key, value in result.items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise ValueError(
                    "Gamma mapping keys must be (dose, distance) criterion tuples"
                )
            normalised_key = criterion_key(*key)
            if normalised_key in outputs:
                raise ValueError(
                    f"Duplicate normalised gamma criterion: {normalised_key}"
                )
            outputs[normalised_key] = value
    else:
        if len(expected) != 1:
            raise ValueError(
                "Several gamma criteria require a mapping of criterion tuples to arrays"
            )
        outputs[expected[0]] = result

    if set(outputs) != set(expected):
        missing = sorted(set(expected) - set(outputs))
        extra = sorted(set(outputs) - set(expected))
        raise ValueError(
            f"Returned gamma criteria do not match the case; missing={missing}, extra={extra}"
        )

    normalised = {}
    for key in expected:
        if np.ma.isMaskedArray(outputs[key]):
            raise TypeError(
                "Masked gamma arrays must be explicitly converted to the agreed NaN convention"
            )
        values = np.asarray(outputs[key])
        if values.shape != reference_shape:
            raise ValueError(
                f"Gamma {key} has shape {values.shape}; expected reference shape {reference_shape}"
            )
        if values.dtype.kind not in "iuf":
            raise TypeError(f"Gamma {key} must be a real numeric array")
        # Do not cast or repair NaNs, infinities, negative values, precision, or
        # contiguity: those are evidence for the worker's numerical verification.
        normalised[key] = values
    return normalised, {}


def invoke(spec, args, kwargs):
    """Call PyMedPhys gamma and return criterion-keyed arrays.

    Loading, input checks, and result normalisation are included in this helper.
    A worker measuring only gamma execution must load and prepare the callable
    before its timer and normalise the raw result afterwards. Use ``prepare_call``
    for that boundary; timing this convenience helper would include setup costs.
    """
    implementation, call_args, call_kwargs, normalise = prepare_call(spec, args, kwargs)
    return normalise(implementation(*call_args, **call_kwargs))


def prepare_call(spec, args, kwargs):
    """Return ``(callable, args, kwargs, normalise_result)`` for clean timing."""
    import numpy as np

    if "interp_algo" in kwargs:
        raise ValueError(
            "Use per-version interp_algo, not shared gamma keyword options"
        )
    call_args, call_kwargs, expected = _canonical_call(args, kwargs)
    call_kwargs["interp_algo"] = interpolation_algorithm(spec)
    reference_shape = np.asarray(call_args[1]).shape
    implementation = load_callable(spec)

    def normalise(result):
        return _normalise_result(result, expected, reference_shape)

    return implementation, call_args, call_kwargs, normalise


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_provenance(path):
    executable = shutil.which("git")
    if executable is None:
        return {"status": "unavailable", "reason": "git executable was not found"}

    def command(*args):
        return subprocess.run(
            [executable, "--no-optional-locks", "-C", str(path), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        ).stdout.strip()

    try:
        root = command("rev-parse", "--show-toplevel")
        commit = command("rev-parse", "HEAD")
        branch = command("branch", "--show-current")
        status = command("status", "--porcelain=v1", "--untracked-files=normal")
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        return {"status": "unavailable", "reason": type(error).__name__}
    return {
        "status": "ok",
        "root": root,
        "commit": commit,
        "branch": branch,
        "dirty": bool(status),
        "status_porcelain": status,
    }


def implementation_provenance(spec):
    """Record loaded PyMedPhys code, checkout hashes, and available Git state.

    Checkout manifests cover Python/Cython files and Python build
    configuration, excluding environment and cache directories. They do not
    claim to identify every native dependency or data file; the parent records
    the worker's environment separately. Git state includes untracked paths.
    Importing the implementation may execute its module initialisation; no
    gamma call or Git write is performed.
    """
    implementation = load_callable(spec)
    module = sys.modules["pymedphys"]
    raw_module_file = getattr(module, "__file__", None)
    module_file = Path(raw_module_file).resolve() if raw_module_file else None
    try:
        source_file = inspect.getsourcefile(implementation)
    except (TypeError, OSError):
        source_file = None
    source_file = Path(source_file).resolve() if source_file else None
    checkout, root = _checkout_paths(spec)
    roots = [root] if root is not None else []
    files = {path for path in (module_file, source_file) if path and path.is_file()}
    if checkout is not None:
        files.update(
            path
            for path in (
                checkout / "pyproject.toml",
                checkout / "setup.cfg",
                checkout / "setup.py",
            )
            if path.is_file()
        )
    for root in roots:
        for directory, names, filenames in os.walk(root, followlinks=False):
            names[:] = [name for name in names if name not in _EXCLUDED_DIRECTORIES]
            for filename in filenames:
                path = Path(directory) / filename
                if path.suffix in _SOURCE_SUFFIXES or path.name in _BUILD_FILES:
                    # A symlink may resolve outside a declared source tree; do not
                    # silently read another tree into that tree's manifest.
                    resolved = path.resolve()
                    if resolved.is_file() and resolved.is_relative_to(root):
                        files.add(resolved)
    hashes = {str(path): _sha256(path) for path in sorted(files)}
    git_locations = list(roots)
    if module_file is not None:
        git_locations.append(module_file.parent)
    repositories = {}
    for location in dict.fromkeys(git_locations):
        details = _git_provenance(location)
        key = details.get("root", str(location))
        repositories.setdefault(key, details)
    return {
        "name": spec.get("name"),
        "api": "pymedphys.gamma",
        "interp_algo": interpolation_algorithm(spec),
        "checkout": str(checkout) if checkout is not None else None,
        "python_executable": sys.executable,
        "module_file": str(module_file) if module_file else None,
        "module_sha256": hashes.get(str(module_file)) if module_file else None,
        "callable_source_file": str(source_file) if source_file else None,
        "import_root": str(root) if root is not None else None,
        "source_hashes": hashes,
        "source_hash_scope": "loaded PyMedPhys/gamma source, selected Python/Cython import tree, and checkout build configuration",
        "git": list(repositories.values()),
    }
