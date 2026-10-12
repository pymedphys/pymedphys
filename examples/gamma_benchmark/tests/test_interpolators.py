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

"""Interpolator selection with fabricated packages, never real gamma calls."""

from pathlib import Path
import sys

import numpy as np
import pytest

from gamma_bench import cli, pymedphys_api as api, runner, workloads
from gamma_bench.common import read_json, write_json


@pytest.mark.parametrize("explicit_checkout", [False, True])
def test_interpolator_initialisation_selects_one_checkout_without_importing_gamma(
    tmp_path, monkeypatch, explicit_checkout
):
    def forbidden(*args, **kwargs):
        raise AssertionError("Planning attempted to load or execute PyMedPhys")

    monkeypatch.setattr(cli, "execute_run", forbidden)
    monkeypatch.setattr(api, "load_callable", forbidden)
    destination = tmp_path / "study"
    arguments = [
        "init",
        "--directory",
        str(destination),
        "--preset",
        "quick",
        "--compare-interpolators",
    ]
    if explicit_checkout:
        arguments += ["--baseline-checkout", str(tmp_path / "source")]
    assert cli.main(arguments) == 0
    config = read_json(destination / "config.json")
    assert config["baseline"] == "scipy"
    assert [spec["name"] for spec in config["versions"]] == ["scipy", "pymedphys"]
    assert [spec["interp_algo"] for spec in config["versions"]] == [
        "scipy",
        "pymedphys",
    ]
    assert config["versions"][0]["checkout"] == config["versions"][1]["checkout"]
    if explicit_checkout:
        assert config["versions"][0]["checkout"] == str((tmp_path / "source").resolve())
    resolved = runner.resolved_config(
        destination / "config.json", require_checkouts=False
    )
    assert resolved["versions"][0]["python"] == resolved["versions"][1]["python"]
    assert read_json(destination / "plan.json") == workloads.make_plan("quick")


def test_interpolator_initialisation_rejects_a_second_checkout_before_writing(
    tmp_path, capsys
):
    destination = tmp_path / "absent"
    assert (
        cli.main(
            [
                "init",
                "--directory",
                str(destination),
                "--compare-interpolators",
                "--candidate-checkout",
                str(tmp_path / "other"),
            ]
        )
        == 2
    )
    assert not destination.exists()
    assert "omit --candidate-checkout" in capsys.readouterr().err


def test_omitted_backend_is_resolved_explicitly_without_importing_gamma(tmp_path):
    config = runner.example_config()
    for spec in config["versions"]:
        spec.pop("interp_algo")
        spec["checkout"] = None
    path = tmp_path / "config.json"
    write_json(path, config)
    assert all(
        spec["interp_algo"] == "pymedphys"
        for spec in runner.resolved_config(path)["versions"]
    )


@pytest.mark.parametrize("backend", [None, "scipy", "pymedphys"])
def test_api_prepares_the_selected_backend_before_any_call(monkeypatch, backend):
    calls = []

    def fabricated_gamma(*args, **kwargs):
        calls.append(kwargs)
        return np.zeros_like(args[1])

    monkeypatch.setattr(api, "load_callable", lambda spec: fabricated_gamma)
    spec = {"name": "mock", "checkout": None}
    if backend is not None:
        spec["interp_algo"] = backend
    axes, dose = (np.arange(2), np.arange(2)), np.ones((2, 2))
    function, args, kwargs, normalise = api.prepare_call(
        spec, (axes, dose, axes, dose, 3, 2), {"local_gamma": True}
    )
    assert calls == []
    assert kwargs == {"local_gamma": True, "interp_algo": backend or "pymedphys"}
    outputs, _ = normalise(function(*args, **kwargs))
    assert list(outputs) == [api.criterion_key(3, 2)]
    assert len(calls) == 1


def test_api_rejects_an_ambiguous_shared_backend_before_loading(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid options reached a package import")

    monkeypatch.setattr(api, "load_callable", forbidden)
    with pytest.raises(ValueError, match="per-version interp_algo"):
        api.prepare_call(
            {"name": "mock", "checkout": None}, (), {"interp_algo": "scipy"}
        )


def test_provenance_probe_retains_the_interpolator_factor(tmp_path, monkeypatch):
    config = runner.example_config(compare_interpolators=True)

    def fabricated_probe(job, *args):
        assert job["mode"] == "probe"
        return {
            "status": "ok",
            "provenance": {
                "source_hashes": {"same_source": "same_hash"},
                "interp_algo": job["implementation"]["interp_algo"],
            },
        }

    monkeypatch.setattr(runner, "run_worker", fabricated_probe)
    probes = runner.probe_implementations(config, tmp_path)
    assert probes["scipy"]["interp_algo"] == "scipy"
    assert probes["pymedphys"]["interp_algo"] == "pymedphys"
    assert probes["scipy"]["source_hashes"] == probes["pymedphys"]["source_hashes"]


@pytest.mark.parametrize("backend,value", [("scipy", 0.25), ("pymedphys", 0.5)])
def test_isolated_worker_forwards_and_records_backend_with_fabricated_package(
    tmp_path, backend, value
):
    package = tmp_path / "checkout" / "lib" / "pymedphys"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "def gamma(axes_r, dose_r, axes_e, dose_e, dose, distance, **kwargs):\n"
        "    import numpy as np\n"
        "    values = {'scipy': 0.25, 'pymedphys': 0.5}\n"
        "    return np.full_like(dose_r, values[kwargs['interp_algo']])\n",
        encoding="utf-8",
    )
    case = workloads.make_plan("quick")["cases"][0] | {"n": 4, "extent_mm": 12.0}
    directory = tmp_path / "worker"
    directory.mkdir()
    fixture, controls, _ = runner.save_fixture(case, directory)
    job = {
        "implementation": {
            "name": backend,
            "checkout": str(package.parents[1]),
            "python": sys.executable,
            "interp_algo": backend,
        },
        "case": case,
        "fixture_path": str(fixture),
        "gamma_kwargs": controls,
        "result_path": str(directory / "result.json"),
        "output_path": str(directory / "output.npz"),
        "representative_path": str(directory / "representative.npz"),
        "phase_path": str(directory / "phase.json"),
        "cache_dir": str(directory / "cache"),
        "warmups": 1,
        "repeatability_atol": 0.0,
        "round": 0,
        "order_position": 0,
    }
    result = runner.run_worker(
        job, timeout=30, memory_limit=0, interval=0.01, deadline=None
    )
    assert result["status"] == "ok"
    assert result["provenance"]["interp_algo"] == backend
    assert Path(result["provenance"]["module_file"]) == package / "__init__.py"
    with np.load(job["output_path"], allow_pickle=False) as outputs:
        assert all(np.all(outputs[key] == value) for key in outputs.files)
