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

"""Harness checks using fabricated arrays only; no gamma implementation runs."""

import hashlib
from pathlib import Path

import numpy as np
import pytest

from gamma_bench import runner, workloads
from gamma_bench.common import read_json, write_json


def _write_version_config(tmp_path, layout="lib/pymedphys"):
    config = runner.example_config("quick")
    for version in config["versions"]:
        checkout = tmp_path / version["name"]
        package = checkout / layout
        package.mkdir(parents=True)
        # Configuration validation must inspect paths without importing code.
        (package / "__init__.py").write_text(
            "raise AssertionError('Planning imported PyMedPhys')\n"
        )
        version["checkout"] = version["name"]
    path = tmp_path / "config.json"
    write_json(path, config)
    return path, config


@pytest.mark.parametrize("layout", ["lib/pymedphys", "pymedphys"])
def test_configuration_accepts_checkout_layouts_without_importing_them(
    tmp_path, layout
):
    path, config = _write_version_config(tmp_path, layout)
    resolved = runner.resolved_config(path)
    assert resolved["schema_version"] == 2
    for original, version in zip(config["versions"], resolved["versions"]):
        assert version["checkout"] == str((tmp_path / original["checkout"]).resolve())
        assert version["python"]
    assert resolved["gamma_options"] == {}
    assert "implementations" not in resolved


def test_null_checkout_explicitly_selects_installed_versions_without_importing_them(
    tmp_path,
):
    config = runner.example_config("quick")
    for version in config["versions"]:
        version["checkout"] = None
    path = tmp_path / "config.json"
    write_json(path, config)
    resolved = runner.resolved_config(path)
    assert all(version["checkout"] is None for version in resolved["versions"])


def test_missing_checkout_requires_explicit_planning_override(tmp_path):
    path = tmp_path / "config.json"
    write_json(path, runner.example_config("quick"))
    with pytest.raises(ValueError, match="PyMedPhys checkout"):
        runner.resolved_config(path)
    resolved = runner.resolved_config(path, require_checkouts=False)
    assert len(resolved["versions"]) == 2


def test_existing_non_pymedphys_directory_is_not_a_valid_checkout(tmp_path):
    path, config = _write_version_config(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    config["versions"][0]["checkout"] = "empty"
    write_json(path, config)
    with pytest.raises(ValueError, match="PyMedPhys checkout"):
        runner.resolved_config(path)


@pytest.mark.parametrize(
    "extra",
    [
        {"callable": "arbitrary:gamma"},
        {"source_paths": []},
        {"kwargs": {"interp_algo": "scipy"}},
        {"env": {}},
    ],
)
def test_versions_reject_generic_callable_source_kwargs_and_environment_options(
    tmp_path, extra
):
    path, config = _write_version_config(tmp_path)
    config["versions"][0].update(extra)
    write_json(path, config)
    with pytest.raises(ValueError, match="always pymedphys.gamma"):
        runner.resolved_config(path)


def test_shared_gamma_options_apply_once_at_configuration_level(tmp_path):
    path, config = _write_version_config(tmp_path)
    config["gamma_options"] = {"quiet": None}
    write_json(path, config)
    resolved = runner.resolved_config(path)
    assert resolved["gamma_options"] == {"quiet": None}
    assert all("kwargs" not in version for version in resolved["versions"])


def test_versions_can_select_the_two_supported_interpolators(tmp_path):
    path, config = _write_version_config(tmp_path)
    config["versions"][0]["interp_algo"] = "scipy"
    config["versions"][1]["interp_algo"] = "pymedphys"
    write_json(path, config)
    resolved = runner.resolved_config(path)
    assert [version["interp_algo"] for version in resolved["versions"]] == [
        "scipy",
        "pymedphys",
    ]


@pytest.mark.parametrize("backend", ["other", None, 3, True])
def test_versions_reject_unsupported_interpolator_values(tmp_path, backend):
    path, config = _write_version_config(tmp_path)
    config["versions"][0]["interp_algo"] = backend
    write_json(path, config)
    with pytest.raises(ValueError, match="interp_algo"):
        runner.resolved_config(path)


def test_shared_gamma_options_cannot_replace_per_version_interpolator_selection(
    tmp_path,
):
    path, config = _write_version_config(tmp_path)
    config["gamma_options"] = {"interp_algo": "scipy"}
    write_json(path, config)
    with pytest.raises(ValueError, match="interp_algo"):
        runner.resolved_config(path)


@pytest.mark.parametrize("control", sorted(runner.CASE_CONTROLS))
def test_shared_gamma_options_cannot_override_plan_controls(tmp_path, control):
    path, config = _write_version_config(tmp_path)
    config["gamma_options"] = {control: 1}
    write_json(path, config)
    with pytest.raises(ValueError, match="cannot override case controls"):
        runner.resolved_config(path)


def test_a_version_must_explicitly_select_a_checkout_or_installed_package(tmp_path):
    path, config = _write_version_config(tmp_path)
    del config["versions"][0]["checkout"]
    write_json(path, config)
    with pytest.raises(ValueError, match="checkout"):
        runner.resolved_config(path)


@pytest.mark.parametrize("preset", ["quick", "standard", "thorough"])
def test_generated_plans_pass_the_controller_validation(preset):
    runner.validate_plan(workloads.make_plan(preset), runner.DEFAULT_SETTINGS)


def _single_case_plan(**updates):
    plan = workloads.make_plan("quick")
    plan["cases"] = [plan["cases"][0] | {"n": 8} | updates]
    return plan


def test_plan_validation_accepts_several_gamma_criteria():
    plan = _single_case_plan(
        dose_percent_threshold=[2.0, 3.0], distance_mm_threshold=[1.0, 3.0]
    )
    runner.validate_plan(plan, runner.DEFAULT_SETTINGS)


@pytest.mark.parametrize(
    "updates",
    [
        {"n": True},
        {"dimension": 2.5},
        {"threads": True},
        {"seed": -1},
        {"dose_percent_threshold": []},
        {"distance_mm_threshold": [1.0, 1.0]},
        {"distance_mm_threshold": [[1.0]]},
        {"max_gamma": float("nan")},
        {"field_width_mm": 0},
        {"evaluation_padding_mm": -1},
        {"fraction_mode": "cutoff", "above_fraction_target": None},
        {
            "fraction_mode": "width",
            "above_fraction_target": 0.5,
            "lower_percent_dose_cutoff": 100,
        },
        {"above_fraction_target": 0.5},
        {"dose_scale": float("inf")},
        {"shift_mm": float("nan")},
        {"ram_mib": 1e-12},
        {"local_gamma": "false"},
        {"skip_once_passed": 1},
    ],
)
def test_plan_validation_rejects_invalid_controls_before_fixture_generation(updates):
    with pytest.raises(ValueError):
        runner.validate_plan(_single_case_plan(**updates), runner.DEFAULT_SETTINGS)


def test_padding_allocation_is_bounded_independently_of_reference_size():
    plan = _single_case_plan(evaluation_padding_mm=100000.0)
    with pytest.raises(ValueError, match="padded evaluation grid"):
        runner.validate_plan(plan, runner.DEFAULT_SETTINGS)


def test_fixture_memory_estimate_is_checked_before_allocation():
    plan = _single_case_plan(n=100, evaluation_padding_mm=0.0)
    settings = dict(runner.DEFAULT_SETTINGS, memory_limit_gib=0.0001)
    with pytest.raises(ValueError, match="estimated fixture working memory"):
        runner.validate_plan(plan, settings)


def test_zero_memory_limit_disables_memory_guard_but_keeps_point_limit():
    runner.validate_plan(
        _single_case_plan(), dict(runner.DEFAULT_SETTINGS, memory_limit_gib=0)
    )
    with pytest.raises(ValueError, match="max_reference_points"):
        runner.validate_plan(
            _single_case_plan(),
            dict(runner.DEFAULT_SETTINGS, memory_limit_gib=0, max_reference_points=10),
        )


def test_fixture_mask_uses_the_same_percent_conversion_as_the_gamma_contract(
    tmp_path, monkeypatch
):
    # Both expressions are mathematically equal but differ by one ulp here.
    cutoff = 1.8550000000000002
    reference = np.full((2, 2), 1.855)
    axes = (np.array([0.0, 1.0]), np.array([0.0, 1.0]))
    kwargs = {"lower_percent_dose_cutoff": cutoff, "global_normalisation": 100.0}
    metadata = {"eligible_points": 4}
    monkeypatch.setattr(
        workloads,
        "make_inputs",
        lambda case: ((axes, reference, axes, reference.copy()), kwargs, metadata),
    )
    path, _, _ = runner.save_fixture({}, tmp_path)
    with np.load(path, allow_pickle=False) as fixture:
        expected = reference >= cutoff / 100 * 100.0
        np.testing.assert_array_equal(fixture["eligible_mask"], expected)


def test_zero_random_subset_preserves_eligibility_but_expects_no_analysed_points(
    tmp_path,
):
    case = workloads.make_plan("quick")["cases"][0] | {
        "n": 5,
        "extent_mm": 20.0,
        "random_subset": 0,
    }
    path, kwargs, metadata = runner.save_fixture(case, tmp_path)
    with np.load(path, allow_pickle=False) as fixture:
        assert np.count_nonzero(fixture["eligible_mask"]) > 0
    assert kwargs["random_subset"] == 0
    assert metadata["analysed_mask_checked"] is False
    assert metadata["expected_analysed_points"] == 0


def _save_outputs(path, values):
    np.savez(path, **{"dose=3.0;distance=3.0": np.asarray(values, dtype=float)})


@pytest.mark.parametrize(
    "values", [np.full((2, 2), np.nan), np.full((2, 2), np.inf), np.full((2, 2), -0.2)]
)
def test_agreement_on_invalid_outputs_does_not_validate_an_implementation(
    tmp_path, values
):
    baseline, candidate = tmp_path / "baseline.npz", tmp_path / "candidate.npz"
    _save_outputs(baseline, values)
    _save_outputs(candidate, values)
    result = runner.compare_arrays(
        baseline, candidate, np.ones((2, 2), dtype=bool), runner.DEFAULT_SETTINGS
    )
    assert result["valid"] is False


def test_pass_fail_disagreements_are_rejected_even_within_numeric_tolerance(tmp_path):
    baseline, candidate = tmp_path / "baseline.npz", tmp_path / "candidate.npz"
    _save_outputs(baseline, np.full((2, 2), 1.0 - 1e-8))
    _save_outputs(candidate, np.full((2, 2), 1.0 + 1e-8))
    result = runner.compare_arrays(
        baseline, candidate, np.ones((2, 2), dtype=bool), runner.DEFAULT_SETTINGS
    )
    assert result["within_tolerance"] is True
    assert result["pass_disagreements"] == 4
    assert result["valid"] is False


@pytest.mark.parametrize(
    "cap,value,valid",
    [
        (2.0, 2.0, True),
        (2.0, 2.0 + 0.5e-6, True),
        (2.0, 2.0 + 2e-6, False),
        (None, 3.0, True),
    ],
)
def test_agreement_does_not_override_the_requested_gamma_cap(
    tmp_path, cap, value, valid
):
    baseline, candidate = tmp_path / "baseline.npz", tmp_path / "candidate.npz"
    _save_outputs(baseline, np.full((2, 2), value))
    _save_outputs(candidate, np.full((2, 2), value))
    result = runner.compare_arrays(
        baseline,
        candidate,
        np.ones((2, 2), dtype=bool),
        dict(runner.DEFAULT_SETTINGS, max_gamma=cap),
    )
    assert result["within_cap"] is valid
    assert result["valid"] is valid


@pytest.mark.parametrize(
    "values,expected_count,valid",
    [
        ([[0.2, np.nan], [np.nan, np.nan]], 1, True),
        ([[np.nan, np.nan], [np.nan, np.nan]], 1, False),
        ([[0.2, 0.3], [np.nan, np.nan]], 1, False),
        ([[np.nan, np.nan], [0.2, np.nan]], 1, False),
        ([[0.2, np.nan], [np.inf, np.nan]], 1, False),
        ([[np.nan, np.nan], [np.nan, np.nan]], 0, True),
    ],
)
def test_subset_validation_checks_count_and_eligibility_even_when_implementations_agree(
    tmp_path, values, expected_count, valid
):
    baseline, candidate = tmp_path / "baseline.npz", tmp_path / "candidate.npz"
    _save_outputs(baseline, values)
    _save_outputs(candidate, values)
    eligible = np.array([[True, True], [False, False]])
    result = runner.compare_arrays(
        baseline,
        candidate,
        eligible,
        runner.DEFAULT_SETTINGS,
        check_mask=False,
        expected_count=expected_count,
    )
    assert result["valid"] is valid


def _fabricated_round(directory, name, round_index, values, seconds):
    _save_outputs(directory / f"{name}-{round_index}.npz", values)
    return {
        "status": "ok",
        "seconds": seconds,
        "first_call_seconds": seconds,
        "peak_rss_bytes": 1024,
        "pre_gamma_rss_bytes": 512,
        "representative_file": str(directory / f"{name}-representative.npz"),
        "output_sha256": hashlib.sha256(np.asarray(values).tobytes()).hexdigest(),
        "provenance": {
            "source_hashes": {"mock": "same"},
            "packages": {},
            "python": "mock",
        },
        "repeatable": True,
        "round": round_index,
    }


def _aggregate_fabricated(
    tmp_path, values_per_round, baseline_seconds, candidate_seconds
):
    np.savez(tmp_path / "inputs.npz", eligible_mask=np.ones((2, 2), dtype=bool))
    per_variant = {}
    for name, seconds in [
        ("baseline", baseline_seconds),
        ("candidate", candidate_seconds),
    ]:
        per_variant[name] = [
            _fabricated_round(tmp_path, name, index, values, elapsed)
            for index, (values, elapsed) in enumerate(zip(values_per_round, seconds))
        ]
    return runner.aggregate_case(
        {"id": "mock", "dimension": 2, "n": 2},
        {"analysed_mask_checked": True},
        per_variant,
        tmp_path,
        {"baseline": "baseline", "settings": dict(runner.DEFAULT_SETTINGS)},
        len(values_per_round),
        tmp_path,
    )


def test_fresh_process_rounds_must_agree_before_outputs_are_called_repeatable(tmp_path):
    record = _aggregate_fabricated(
        tmp_path, [np.full((2, 2), 0.2), np.full((2, 2), 0.3)], [1.0, 2.0], [0.5, 1.0]
    )
    # Both implementations agree within each pair and each mock worker says
    # its own warm/timed calls agree. Across-process repeatability still fails.
    assert record["comparisons"]["candidate"]["verification"]["repeatable"] is False
    assert record["status"] == "mismatch"


def test_speedup_uses_matched_round_ratios_not_a_ratio_of_medians(tmp_path):
    values = [np.full((2, 2), 0.2)] * 3
    record = _aggregate_fabricated(
        tmp_path, values, [1.0, 10.0, 100.0], [1.0, 5.0, 100.0]
    )
    timing = record["comparisons"]["candidate"]["timing"]
    assert record["status"] == "ok"
    assert timing["paired_speedups"] == [1.0, 2.0, 1.0]
    assert timing["median_speedup"] == 1.0


def test_missing_implementation_rounds_are_incomplete_not_zero_time(tmp_path):
    np.savez(tmp_path / "inputs.npz", eligible_mask=np.ones((2, 2), dtype=bool))
    good = _fabricated_round(tmp_path, "baseline", 0, np.full((2, 2), 0.2), 1.0)
    record = runner.aggregate_case(
        {"id": "mock"},
        {"analysed_mask_checked": True},
        {"baseline": [good], "candidate": []},
        tmp_path,
        {"baseline": "baseline", "settings": dict(runner.DEFAULT_SETTINGS)},
        1,
        tmp_path,
    )
    assert record["status"] == "pending"
    assert record["variants"]["candidate"]["seconds"] == []
    assert record["comparisons"]["candidate"]["timing"]["median_speedup"] is None
    assert record["comparisons"]["candidate"]["verification"]["valid"] is False


@pytest.mark.parametrize(
    "changed_field",
    [
        "source_hashes",
        "packages",
        "python",
        "executable",
        "module_file",
        "interp_algo",
    ],
)
def test_changed_provenance_between_cases_stops_the_study(
    tmp_path, monkeypatch, changed_field
):
    config = runner.example_config("quick")
    config["settings"].update(keep_arrays=True, keep_inputs=True)
    plan = workloads.make_plan("quick")
    template = plan["cases"][0] | {"n": 2, "extent_mm": 20.0}
    plan.update(
        repeats=1,
        cases=[template | {"id": name} for name in ("first", "changed", "unattempted")],
    )
    original = {
        "source_hashes": {"mock": "original"},
        "packages": {"numpy": "original"},
        "python": "original",
        "executable": "original",
        "module_file": "original",
        "interp_algo": "pymedphys",
    }
    probes = {
        version["name"]: runner.provenance_identity(original)
        for version in config["versions"]
    }
    monkeypatch.setattr(runner, "probe_implementations", lambda *_: probes)
    monkeypatch.setattr(runner, "environment_record", lambda: {})
    attempted = []

    def fabricated_worker(job, *_):
        case_id, name = job["case"]["id"], job["implementation"]["name"]
        attempted.append((case_id, name))
        result = _fabricated_round(
            Path(job["output_path"]).parent,
            name,
            job["round"],
            np.full((2, 2), 0.2),
            1.0,
        )
        result["provenance"] = dict(original)
        if case_id == "changed" and name == "candidate":
            result["provenance"][changed_field] = (
                {"mock": "changed"}
                if changed_field in ("source_hashes", "packages")
                else "changed"
            )
        write_json(job["result_path"], result)
        return result

    monkeypatch.setattr(runner, "run_worker", fabricated_worker)
    output = tmp_path / "study"
    summary = runner.execute_run(config, plan, output, make_report=False)

    assert summary["run_status"] == "failed"
    assert [record["status"] for record in summary["records"]] == ["ok", "error"]
    assert (
        summary["records"][1]["comparisons"]["candidate"]["verification"]["valid"]
        is False
    )
    rejected = read_json(output / "cases" / "changed" / "candidate-0.json")
    assert rejected["status"] == "error"
    assert rejected["provenance_changed"] is True
    assert "initial provenance probe" in rejected["error"]
    assert all(case_id != "unattempted" for case_id, _ in attempted)
    assert not (output / ".run.lock").exists()
