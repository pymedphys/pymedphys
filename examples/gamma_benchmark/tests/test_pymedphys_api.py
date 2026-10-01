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

"""PyMedPhys selection and output checks using mock packages, never real gamma."""

import hashlib
from pathlib import Path
import subprocess
import sys
import types

import numpy as np
import pytest

from gamma_bench import pymedphys_api as api


@pytest.fixture
def inputs():
    axes = (np.array([0.0, 1.0]), np.array([0.0, 1.0]))
    dose = np.ones((2, 2))
    return axes, dose, axes, dose.copy()


@pytest.fixture
def mock_version(monkeypatch):
    module = types.ModuleType("pymedphys")
    module.gamma = lambda *args, **kwargs: np.full_like(args[1], 0.5)
    monkeypatch.setitem(sys.modules, "pymedphys", module)
    return {"name": "mock", "checkout": None, "python": sys.executable}, module


def test_fixed_api_receives_six_arguments_and_shared_controls(inputs, mock_version):
    spec, module = mock_version
    spec["interp_algo"] = "scipy"
    observed = {}

    def gamma(*args, **kwargs):
        observed.update(args=args, kwargs=kwargs)
        return np.full_like(args[1], 0.5)

    module.gamma = gamma
    outputs, diagnostics = api.invoke(
        spec,
        inputs,
        {
            "dose_percent_threshold": 3,
            "distance_mm_threshold": 2,
            "local_gamma": True,
        },
    )
    assert observed["args"][4:] == (3, 2)
    assert len(observed["args"]) == 6
    assert observed["kwargs"] == {"local_gamma": True, "interp_algo": "scipy"}
    assert list(outputs) == ["dose=3.0;distance=2.0"]
    assert diagnostics == {}


def test_multiple_criteria_remain_identifiable(inputs, mock_version):
    spec, module = mock_version
    module.gamma = lambda *args, **kwargs: {
        (3, 2): np.full((2, 2), 0.3),
        (2, 2): np.full((2, 2), 0.2),
    }
    outputs, _ = api.invoke(spec, inputs + ([2, 3], 2), {})
    assert list(outputs) == [api.criterion_key(2, 2), api.criterion_key(3, 2)]
    assert outputs[api.criterion_key(3, 2)][0, 0] == 0.3


def test_preparation_does_not_execute_gamma(inputs, mock_version):
    spec, module = mock_version
    calls = []
    module.gamma = lambda *a, **kw: calls.append(1) or np.zeros((2, 2))
    function, args, kwargs, normalise = api.prepare_call(spec, inputs + (3, 2), {})
    assert calls == []
    raw = function(*args, **kwargs)
    outputs, _ = normalise(raw)
    assert calls == [1]
    assert outputs[api.criterion_key(3, 2)] is raw


@pytest.mark.parametrize(
    "value", [0, -1, float("nan"), float("inf"), [], [[2]], [2, 2], True, "3"]
)
def test_invalid_criteria_are_rejected(inputs, mock_version, value):
    spec, _ = mock_version
    with pytest.raises(ValueError):
        api.invoke(spec, inputs + (value, 2), {})


def test_criteria_cannot_be_supplied_twice(inputs, mock_version):
    spec, _ = mock_version
    with pytest.raises(ValueError, match="both positionally"):
        api.invoke(spec, inputs + (3, 2), {"dose_percent_threshold": 3})


@pytest.mark.parametrize(
    "output, error",
    [
        ({(2, 2): np.zeros((2, 2))}, "do not match"),
        ({}, "do not match"),
        ({"3/2": np.zeros((2, 2))}, "criterion tuples"),
        (np.zeros(4), "expected reference shape"),
        ({"gamma": np.zeros((2, 2)), "diagnostics": {}}, "criterion tuples"),
    ],
)
def test_invalid_output_structure_is_rejected(inputs, mock_version, output, error):
    spec, module = mock_version
    module.gamma = lambda *a, **kw: output
    with pytest.raises(ValueError, match=error):
        api.invoke(spec, inputs + (3, 2), {})


def test_array_is_ambiguous_for_multiple_criteria(inputs, mock_version):
    spec, _ = mock_version
    with pytest.raises(ValueError, match="Several gamma criteria"):
        api.invoke(spec, inputs + ([2, 3], 2), {})


@pytest.mark.parametrize(
    "output",
    [
        np.ones((2, 2), dtype=bool),
        np.ones((2, 2), dtype=complex),
        np.full((2, 2), "0.5"),
        np.ma.array(np.ones((2, 2))),
    ],
)
def test_unsupported_array_types_are_rejected(inputs, mock_version, output):
    spec, module = mock_version
    module.gamma = lambda *a, **kw: output
    with pytest.raises(TypeError):
        api.invoke(spec, inputs + (3, 2), {})


def test_numerical_errors_are_preserved_for_verification(inputs, mock_version):
    spec, module = mock_version
    output = np.array([[np.nan, np.inf], [-1, 0]], dtype=np.float32)
    module.gamma = lambda *a, **kw: output
    outputs, _ = api.invoke(spec, inputs + (3, 2), {})
    assert outputs[api.criterion_key(3, 2)] is output


@pytest.mark.parametrize("layout", ["lib/pymedphys", "pymedphys"])
def test_checkout_selection_and_source_provenance(tmp_path, monkeypatch, layout):
    package = tmp_path / layout
    package.mkdir(parents=True)
    source = package / "__init__.py"
    source.write_text(
        "def gamma(*args, **kwargs):\n    return args[1]\n", encoding="utf-8"
    )
    helper = package / "helper.py"
    helper.write_text("VALUE = 3\n", encoding="utf-8")
    build = tmp_path / "pyproject.toml"
    build.write_text('[project]\nname = "fabricated-pymedphys"\n', encoding="utf-8")
    spec = {"name": "checkout", "checkout": str(tmp_path), "python": sys.executable}
    previous_path = list(sys.path)
    monkeypatch.delitem(sys.modules, "pymedphys", raising=False)
    monkeypatch.setattr(
        api,
        "_git_provenance",
        lambda path: {
            "status": "ok",
            "root": str(tmp_path),
            "commit": "abc",
            "dirty": True,
        },
    )
    try:
        assert callable(api.load_callable(spec))
        provenance = api.implementation_provenance(spec)
    finally:
        sys.path[:] = previous_path
        sys.modules.pop("pymedphys", None)
    assert provenance["api"] == "pymedphys.gamma"
    assert provenance["interp_algo"] == "pymedphys"
    assert provenance["checkout"] == str(tmp_path.resolve())
    assert (
        provenance["module_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    )
    assert str(helper.resolve()) in provenance["source_hashes"]
    assert str(build.resolve()) in provenance["source_hashes"]
    assert provenance["git"][0]["dirty"] is True


def test_selected_checkout_cannot_fall_back_to_another_loaded_package(
    tmp_path, mock_version
):
    _, module = mock_version
    package = tmp_path / "selected" / "lib" / "pymedphys"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    module.__file__ = str(tmp_path / "other" / "pymedphys" / "__init__.py")
    previous = list(sys.path)
    try:
        with pytest.raises(ImportError, match="outside selected checkout"):
            api.load_callable(
                {"name": "selected", "checkout": str(tmp_path / "selected")}
            )
    finally:
        sys.path[:] = previous


def test_missing_checkout_does_not_fall_back_to_installed_package(
    tmp_path, mock_version
):
    with pytest.raises(ValueError, match="does not contain"):
        api.load_callable({"name": "missing", "checkout": str(tmp_path)})


@pytest.mark.parametrize("option", ["callable", "source_paths", "kwargs", "env"])
def test_generic_version_options_are_rejected(mock_version, option):
    spec, _ = mock_version
    with pytest.raises(ValueError, match="Unsupported version options"):
        api.load_callable(spec | {option: {}})


def test_git_unavailable_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda name: None)
    assert api._git_provenance(tmp_path)["status"] == "unavailable"


def test_module_import_does_not_load_numpy_or_pymedphys():
    root = Path(__file__).resolve().parents[1]
    code = "import gamma_bench.pymedphys_api, sys; assert 'numpy' not in sys.modules; assert 'pymedphys' not in sys.modules"
    subprocess.run(
        [sys.executable, "-c", code], cwd=root, check=True, capture_output=True
    )


def test_stable_criterion_key():
    assert api.criterion_key(3, 2) == api.criterion_key(3.0, np.int64(2))
    assert api.criterion_key(3, 2) != api.criterion_key(2, 3)
