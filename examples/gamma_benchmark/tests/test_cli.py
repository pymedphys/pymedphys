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

"""Planning/checking commands only: importing or executing gamma is forbidden."""

import importlib
import pytest

from gamma_bench import cli, pymedphys_api, workloads
from gamma_bench.common import read_json, write_json


@pytest.fixture(autouse=True)
def forbid_implementation_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError(
            "A planning/checking CLI test attempted to load or run an implementation"
        )

    monkeypatch.setattr(cli, "execute_run", forbidden)
    monkeypatch.setattr(pymedphys_api, "load_callable", forbidden)
    monkeypatch.setattr(pymedphys_api, "prepare_call", forbidden)
    monkeypatch.setattr(pymedphys_api, "invoke", forbidden)
    original_import = importlib.import_module

    def checked_import(name, *args, **kwargs):
        if name == "pymedphys" or name.startswith("pymedphys."):
            forbidden()
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", checked_import)


def test_init_creates_editable_standard_configuration_and_frozen_plan(tmp_path, capsys):
    destination = tmp_path / "setup"
    assert cli.main(["init", "--directory", str(destination)]) == 0
    config, plan = (
        read_json(destination / "config.json"),
        read_json(destination / "plan.json"),
    )
    assert plan == workloads.make_plan("standard")
    assert config["preset"] == "standard"
    assert config["baseline"] == "baseline"
    assert config["schema_version"] == 2
    assert [spec["name"] for spec in config["versions"]] == ["baseline", "candidate"]
    assert all(
        set(spec) == {"name", "checkout", "interp_algo"} for spec in config["versions"]
    )
    assert all(spec["interp_algo"] == "pymedphys" for spec in config["versions"])
    assert config["gamma_options"] == {}
    assert "implementations" not in config
    assert (
        "No gamma implementation has been imported or executed"
        in capsys.readouterr().out
    )


def test_init_accepts_explicit_checkout_paths_relative_to_current_directory(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    destination = tmp_path / "setup"
    assert (
        cli.main(
            [
                "init",
                "--directory",
                str(destination),
                "--preset",
                "quick",
                "--baseline-checkout",
                "baseline-tree",
                "--candidate-checkout",
                "candidate-tree",
            ]
        )
        == 0
    )
    config = read_json(destination / "config.json")
    assert [version["checkout"] for version in config["versions"]] == [
        str((tmp_path / "baseline-tree").resolve()),
        str((tmp_path / "candidate-tree").resolve()),
    ]


def test_init_refuses_to_overwrite_a_nonempty_directory(tmp_path, capsys):
    existing = tmp_path / "keep.txt"
    existing.write_text("preserve this")
    assert cli.main(["init", "--directory", str(tmp_path)]) == 2
    assert existing.read_text() == "preserve this"
    assert not (tmp_path / "config.json").exists()
    assert "empty directory" in capsys.readouterr().err


def test_plan_filters_studies_and_dimension_and_honours_repeats(tmp_path):
    destination = tmp_path / "selected.json"
    assert (
        cli.main(
            [
                "plan",
                "--output",
                str(destination),
                "--preset",
                "standard",
                "--study",
                "grid_size_fixed_extent",
                "--study",
                "cutoff_selection",
                "--dimension",
                "3",
                "--repeats",
                "2",
            ]
        )
        == 0
    )
    plan = read_json(destination)
    assert plan["repeats"] == 2
    assert {case["dimension"] for case in plan["cases"]} == {3}
    assert {case["study"] for case in plan["cases"]} == {
        "grid_size_fixed_extent",
        "cutoff_selection",
    }
    expected = [
        case
        for case in workloads.make_plan("standard")["cases"]
        if case["dimension"] == 3
        and case["study"] in {"grid_size_fixed_extent", "cutoff_selection"}
    ]
    assert plan["cases"] == expected


def test_plan_rejects_an_unknown_study_without_writing_output(tmp_path, capsys):
    destination = tmp_path / "invalid.json"
    assert (
        cli.main(["plan", "--output", str(destination), "--study", "absent_study"]) == 2
    )
    assert not destination.exists()
    assert "Unknown studies" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["plan", "matrix"])
def test_plan_commands_refuse_to_overwrite_existing_files(tmp_path, capsys, command):
    destination = tmp_path / "existing.json"
    destination.write_text("preserve existing output")
    arguments = [command, "--output", str(destination)]
    if command == "matrix":
        arguments += ["--design", str(tmp_path / "not_read.json")]
    assert cli.main(arguments) == 2
    assert destination.read_text() == "preserve existing output"
    assert "Refusing to overwrite" in capsys.readouterr().err


def _write_matrix_design(path, factors):
    template = workloads.make_plan("quick")["cases"][0] | {
        "study": "custom_matrix",
        "n": 8,
    }
    write_json(path, {"template": template, "factors": factors, "repeats": 2})


def test_matrix_generates_every_factorial_combination_and_stable_ids(tmp_path):
    design, destination = tmp_path / "design.json", tmp_path / "matrix.json"
    _write_matrix_design(design, {"n": [8, 16], "interp_fraction": [5, 20]})
    assert (
        cli.main(["matrix", "--design", str(design), "--output", str(destination)]) == 0
    )
    plan = read_json(destination)
    assert plan["preset"] == "custom"
    assert plan["repeats"] == 2
    assert {(case["n"], case["interp_fraction"]) for case in plan["cases"]} == {
        (8, 5),
        (8, 20),
        (16, 5),
        (16, 20),
    }
    assert len(plan["cases"]) == len({case["id"] for case in plan["cases"]}) == 4
    assert all(case["id"] == workloads.case_id(case) for case in plan["cases"])
    assert all(case["study"] == "custom_matrix" for case in plan["cases"])


@pytest.mark.parametrize(
    "factors,expected",
    [
        ({}, "non-empty lists"),
        ({"n": []}, "non-empty lists"),
        ({"n": 8}, "non-empty lists"),
        ({"n": [8, 8]}, "unique IDs"),
    ],
)
def test_matrix_rejects_empty_or_duplicate_factor_designs(
    tmp_path, capsys, factors, expected
):
    design, destination = tmp_path / "design.json", tmp_path / "matrix.json"
    _write_matrix_design(design, factors)
    assert (
        cli.main(["matrix", "--design", str(design), "--output", str(destination)]) == 2
    )
    assert not destination.exists()
    assert expected in capsys.readouterr().err


def test_check_can_validate_placeholder_checkouts_without_importing_pymedphys(
    tmp_path, capsys
):
    config_path, plan_path = tmp_path / "config.json", tmp_path / "plan.json"
    config = cli.example_config("quick")
    for spec in config["versions"]:
        spec["checkout"] = str(tmp_path / spec["name"] / "missing")
    write_json(config_path, config)
    write_json(plan_path, workloads.make_plan("quick"))
    arguments = ["check", "--config", str(config_path), "--plan", str(plan_path)]
    assert cli.main(arguments) == 2
    assert "PyMedPhys checkout" in capsys.readouterr().err
    assert cli.main(arguments + ["--allow-missing-checkouts"]) == 0
    output = capsys.readouterr().out
    assert "full gamma calls including warm-ups" in output
    assert "duration is unknown until measured" in output


def test_check_rejects_the_previous_generic_configuration(tmp_path, capsys):
    config = cli.example_config("quick")
    config["implementations"] = [{"name": "baseline", "callable": "arbitrary:gamma"}]
    config_path, plan_path = tmp_path / "config.json", tmp_path / "plan.json"
    write_json(config_path, config)
    write_json(plan_path, workloads.make_plan("quick"))
    assert (
        cli.main(
            [
                "check",
                "--config",
                str(config_path),
                "--plan",
                str(plan_path),
                "--allow-missing-checkouts",
            ]
        )
        == 2
    )
    assert (
        "generic implementation descriptors are not supported"
        in capsys.readouterr().err
    )


def test_report_rejects_missing_directory_without_rendering_or_running(
    tmp_path, capsys
):
    assert cli.main(["report", "--output", str(tmp_path / "absent")]) == 2
    assert "Report directory does not exist" in capsys.readouterr().err
