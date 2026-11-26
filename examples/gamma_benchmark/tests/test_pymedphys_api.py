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
import inspect
from pathlib import Path
import subprocess
import sys
import types

import numpy as np
import pytest

import pymedphys

from gamma_bench import pymedphys_api as api

# The signature of this checkout's gamma. No test here calls the function.
_GAMMA_SIGNATURE = inspect.signature(pymedphys.gamma)


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


def _renamed_gamma(observed, returned):
    """A stand-in with the signature of this checkout's ``pymedphys.gamma``.

    Each call is bound to that signature, so an option the function does not
    take raises a TypeError, as it would from the function itself.
    """

    def gamma(*args, **options):
        _GAMMA_SIGNATURE.bind(*args, **options)
        observed.update(criteria=args[4:], options=options)
        return returned

    gamma.__signature__ = _GAMMA_SIGNATURE
    return gamma


def _result(dose, distance, values):
    settings = types.SimpleNamespace(
        dose_criterion_percent=dose, distance_criterion_mm=distance
    )
    return types.SimpleNamespace(gamma=values, settings=settings)


def test_options_are_translated_for_a_version_that_renamed_them(inputs, mock_version):
    spec, module = mock_version
    spec["interp_algo"] = "scipy"
    observed = {}
    values = np.full((2, 2), 0.25)
    module.gamma = _renamed_gamma(observed, _result(3.0, 2.0, values))

    outputs, _ = api.invoke(
        spec,
        inputs + (3, 2),
        {
            "lower_percent_dose_cutoff": 10,
            "interp_fraction": 20,
            "max_gamma": 2,
            "local_gamma": False,
            "global_normalisation": 2.0,
            "ram_available": 2**20,
            "skip_once_passed": True,
        },
    )

    assert observed["criteria"] == (3, 2)
    assert observed["options"] == {
        "lower_dose_cutoff_percent": 10,
        "search_step_fraction": 1 / 20,
        "gamma_cap": 2,
        "normalisation": "global",
        "normalisation_dose": 2.0,
        "memory_budget_bytes": 2**20,
        "skip_once_passed": True,
        "interpolator": "scipy",
    }
    # The array is passed on as the result holds it, without a copy or cast.
    assert outputs[api.criterion_key(3, 2)] is values


def test_local_gamma_selects_local_normalisation(inputs, mock_version):
    spec, module = mock_version
    observed = {}
    module.gamma = _renamed_gamma(observed, _result(3, 2, np.zeros((2, 2))))

    api.invoke(spec, inputs + (3, 2), {"local_gamma": True})

    assert observed["options"]["normalisation"] == "local"


def test_quiet_is_left_out_for_a_version_that_removed_it(inputs, mock_version):
    # quiet had no effect; from 0.42.0 gamma does not take it.
    spec, module = mock_version
    observed = {}
    module.gamma = _renamed_gamma(observed, _result(3, 2, np.zeros((2, 2))))

    api.invoke(spec, inputs + (3, 2), {"quiet": None})

    assert observed["options"] == {"interpolator": "pymedphys"}


def test_quiet_still_reaches_a_version_with_the_earlier_names(inputs, mock_version):
    spec, module = mock_version
    observed = {}

    def gamma(*args, **kwargs):
        observed.update(kwargs)
        return np.full_like(args[1], 0.5)

    module.gamma = gamma
    api.invoke(spec, inputs + (3, 2), {"quiet": None})

    assert observed == {"quiet": None, "interp_algo": "pymedphys"}


def test_a_tuple_of_results_is_keyed_by_the_criteria_of_each_result(
    inputs, mock_version
):
    spec, module = mock_version
    module.gamma = _renamed_gamma(
        {},
        (
            _result(2.0, 2.0, np.full((2, 2), 0.2)),
            _result(3.0, 2.0, np.full((2, 2), 0.3)),
        ),
    )

    outputs, _ = api.invoke(spec, inputs + ([2, 3], 2), {})

    assert list(outputs) == [api.criterion_key(2, 2), api.criterion_key(3, 2)]
    assert outputs[api.criterion_key(3, 2)][0, 0] == 0.3


def test_results_that_do_not_match_the_case_are_rejected(inputs, mock_version):
    spec, module = mock_version
    module.gamma = _renamed_gamma({}, _result(1.0, 2.0, np.zeros((2, 2))))
    with pytest.raises(ValueError, match="do not match"):
        api.invoke(spec, inputs + (3, 2), {})

    duplicated = (_result(3, 2, np.zeros((2, 2))), _result(3.0, 2.0, np.zeros((2, 2))))
    module.gamma = _renamed_gamma({}, duplicated)
    with pytest.raises(ValueError, match="Duplicate"):
        api.invoke(spec, inputs + ([3], [2]), {})


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
