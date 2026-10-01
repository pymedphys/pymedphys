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

"""Process-flow tests with fabricated outputs only; no real gamma execution."""

import copy
from pathlib import Path
import shutil
import sys
import types

import numpy as np
import pytest

from gamma_bench import pymedphys_api as api, runner, worker, workloads
from gamma_bench.common import SCHEMA_VERSION, read_json, write_json


@pytest.fixture
def mock_source(tmp_path):
    checkout = tmp_path / "checkout"
    package = checkout / "lib" / "pymedphys"
    package.mkdir(parents=True)
    shutil.copyfile(
        Path(__file__).with_name("mock_implementations.py"), package / "__init__.py"
    )
    return checkout


def tiny_case(dimension=2, **updates):
    case = workloads.make_plan("quick")["cases"][0]
    return (
        case
        | {
            "id": f"fabricated-{dimension}d",
            "study": "fabricated_test",
            "dimension": dimension,
            "n": 4 if dimension == 2 else 3,
            "threads": 2,
        }
        | updates
    )


def mock_config(source):
    return {
        "schema_version": SCHEMA_VERSION,
        "preset": "quick",
        "baseline": "reference_mock",
        "versions": [
            {"name": name, "python": sys.executable, "checkout": str(source)}
            for name in ("reference_mock", "candidate_mock")
        ],
        "gamma_options": {},
        "settings": dict(
            runner.DEFAULT_SETTINGS,
            warmups=1,
            worker_timeout_seconds=30,
            budget_minutes=0,
            memory_limit_gib=0,
            memory_sample_interval_ms=2,
            keep_inputs=True,
            keep_arrays=True,
        ),
    }


def make_job(directory, source, function="constant", case=None):
    directory.mkdir(parents=True, exist_ok=True)
    case = case or tiny_case()
    fixture, controls, _ = runner.save_fixture(case, directory)
    with (source / "lib" / "pymedphys" / "__init__.py").open(
        "a", encoding="utf-8"
    ) as stream:
        stream.write(f"\ngamma = {function}\n")
    spec = mock_config(source)["versions"][0]
    return {
        "implementation": spec,
        "case": case,
        "fixture_path": str(fixture),
        "gamma_kwargs": controls,
        "result_path": str(directory / "result.json"),
        "output_path": str(directory / "outputs.npz"),
        "representative_path": str(directory / "representative.npz"),
        "phase_path": str(directory / "phase.json"),
        "cache_dir": str(directory / "cache"),
        "warmups": 1,
        "repeatability_atol": 0.0,
        "round": 0,
        "order_position": 0,
    }


def run_mock_worker(job):
    return runner.run_worker(
        job, timeout=30, memory_limit=0, interval=0.002, deadline=None
    )


def test_controller_round_trip_two_cases_and_resume(tmp_path, mock_source, monkeypatch):
    config_path = tmp_path / "configuration.json"
    configuration = mock_config(mock_source)
    for spec in configuration["versions"]:
        spec["checkout"] = "checkout"
    write_json(config_path, configuration)
    resolved = runner.resolved_config(config_path)
    assert all(
        s["checkout"] == str(mock_source.resolve()) for s in resolved["versions"]
    )
    round_trip = tmp_path / "resolved.json"
    write_json(round_trip, resolved)
    assert runner.resolved_config(round_trip) == resolved
    plan = {
        "schema_version": SCHEMA_VERSION,
        "preset": "fabricated_test",
        "repeats": 2,
        "cases": [tiny_case(2), tiny_case(3)],
        "notes": ["Mock outputs only, not gamma measurements"],
    }
    output = tmp_path / "run"
    summary = runner.execute_run(resolved, plan, output, make_report=False)
    assert summary["run_status"] == "completed"
    assert summary["completed_cases"] == summary["validated_cases"] == 2
    assert all(record["status"] == "ok" for record in summary["records"])
    for record in summary["records"]:
        for variant in record["variants"].values():
            assert len(variant["rounds"]) == 2
            for result in variant["rounds"]:
                assert (
                    result["provenance"]["thread_environment"]["NUMBA_NUM_THREADS"]
                    == "2"
                )
                assert (
                    result["provenance"]["thread_environment"]["OMP_NUM_THREADS"] == "2"
                )
                assert result["repeatable"] is True
                assert (
                    Path(result["provenance"]["module_file"])
                    == mock_source / "lib" / "pymedphys" / "__init__.py"
                )
                assert result["provenance"]["api"] == "pymedphys.gamma"
        assert record["comparisons"]["candidate_mock"]["verification"]["valid"] is True
        assert (
            len(record["comparisons"]["candidate_mock"]["timing"]["paired_speedups"])
            == 2
        )
    assert not (output / ".run.lock").exists()
    original_records = copy.deepcopy(summary["records"])
    original_run_worker = runner.run_worker
    probe_calls = []

    def only_probe(job, *args, **kwargs):
        assert job.get("mode") == "probe", "Resume reran a completed fabricated case"
        probe_calls.append(job["implementation"]["name"])
        return original_run_worker(job, *args, **kwargs)

    monkeypatch.setattr(runner, "run_worker", only_probe)
    resumed = runner.execute_run(resolved, plan, output, resume=True, make_report=False)
    assert resumed["records"] == original_records
    assert sorted(probe_calls) == ["candidate_mock", "reference_mock"]
    assert not (output / ".run.lock").exists()
    with (mock_source / "lib" / "pymedphys" / "__init__.py").open(
        "a", encoding="utf-8"
    ) as stream:
        stream.write("\n# Deliberate source-provenance change for the resume test.\n")
    with pytest.raises(ValueError, match="changed"):
        runner.execute_run(resolved, plan, output, resume=True, make_report=False)
    assert not (output / ".run.lock").exists()


def test_shared_output_buffer_does_not_hide_nonrepeatability(tmp_path, mock_source):
    job = make_job(tmp_path / "shared", mock_source, "shared_changing_buffer")
    result = run_mock_worker(job)
    assert result["status"] == "ok"
    assert result["repeatable"] is False
    assert result["max_repeat_difference"] == 0.25
    assert not Path(job["output_path"]).with_suffix(".warmup.npz").exists()


@pytest.mark.parametrize(
    "function, message",
    [
        ("raises_error", "fabricated implementation failure"),
        ("mutates_input", "read-only"),
    ],
)
def test_worker_reports_failure_and_does_not_reuse_stale_success(
    tmp_path, mock_source, function, message
):
    job = make_job(tmp_path / function, mock_source, function)
    write_json(job["result_path"], {"status": "ok", "seconds": 123})
    write_json(job["phase_path"], {"phase": "timed"})
    np.savez(job["output_path"], stale=np.ones(1))
    result = run_mock_worker(job)
    assert result["status"] == "error"
    assert message in result["error"]
    assert "seconds" not in result
    assert not Path(job["output_path"]).exists()
    assert read_json(job["result_path"])["status"] == "error"


def test_multiple_criteria_survive_worker_serialisation(tmp_path, mock_source):
    case = tiny_case(dose_percent_threshold=[2, 3], distance_mm_threshold=[1, 3])
    job = make_job(tmp_path / "criteria", mock_source, case=case)
    result = run_mock_worker(job)
    assert result["status"] == "ok"
    assert result["repeatable"] is True
    with np.load(job["output_path"], allow_pickle=False) as outputs:
        assert set(outputs.files) == {
            api.criterion_key(d, r) for d in (2, 3) for r in (1, 3)
        }


def test_zero_subset_retains_zero_expected_analysed_count(tmp_path):
    _, _, metadata = runner.save_fixture(tiny_case(random_subset=0), tmp_path)
    assert metadata["eligible_points"] > 0
    assert metadata["analysed_mask_checked"] is False
    assert metadata["expected_analysed_points"] == 0


def test_timer_only_encloses_callable_execution(tmp_path, mock_source, monkeypatch):
    job = make_job(tmp_path / "clock", mock_source)
    clock_reads = []
    prepared_reads = []
    normalised_reads = []
    call_reads = []
    ticks = iter((10.0, 12.0, 20.0, 23.0))

    def clock():
        value = next(ticks)
        clock_reads.append(value)
        return value

    def prepare(spec, args, controls):
        prepared_reads.append(len(clock_reads))

        def implementation(*unused_args, **unused_kwargs):
            call_reads.append(len(clock_reads))
            return np.full(args[1].shape, 0.5)

        def normalise(raw):
            normalised_reads.append(len(clock_reads))
            return {"dose=3.0;distance=3.0": raw}, {}

        return implementation, args, {}, normalise

    monkeypatch.setattr(worker.time, "perf_counter", clock)
    monkeypatch.setattr(api, "prepare_call", prepare)
    monkeypatch.setattr(api, "implementation_provenance", lambda spec: {})
    # execute changes process environment; isolate those changes to this test.
    monkeypatch.setattr(worker.os, "environ", dict(worker.os.environ))
    result = worker.execute(job)
    assert prepared_reads == [0]
    assert call_reads == [1, 3]
    assert normalised_reads == [2, 4]
    assert result["first_call_seconds"] == 2.0
    assert result["seconds"] == 3.0


def test_unexpected_controller_error_is_not_checkpointed_as_completed(
    tmp_path, mock_source, monkeypatch
):
    configuration = mock_config(mock_source)
    plan = {"schema_version": SCHEMA_VERSION, "repeats": 1, "cases": [tiny_case()]}
    output = tmp_path / "fixture-error"

    def fail(*args, **kwargs):
        raise OSError("fabricated fixture write failure")

    monkeypatch.setattr(runner, "save_fixture", fail)
    with pytest.raises(OSError, match="fabricated fixture"):
        runner.execute_run(configuration, plan, output, make_report=False)
    assert read_json(output / "summary.json")["run_status"] == "failed"
    assert not (output / ".run.lock").exists()


def test_timeout_terminates_observed_descendants_without_waiting_for_real_work(
    tmp_path, mock_source, monkeypatch
):
    """Model a running process tree; exercise cleanup without a live child or sleep."""
    job = make_job(tmp_path / "timeout", mock_source)

    class FakeProcessError(Exception):
        pass

    class Child:
        pid = 43211
        killed = False

        def memory_info(self):
            return types.SimpleNamespace(rss=700)

        def kill(self):
            if self.killed:
                raise FakeProcessError("already terminated")
            self.killed = True

    child = Child()

    class RootMonitor:
        def children(self, recursive):
            assert recursive is True
            return [child] if not child.killed else []

        def memory_info(self):
            return types.SimpleNamespace(rss=1000)

    class Popen:
        pid = 43210
        returncode = None
        waited = False

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9

        def wait(self):
            self.waited = True
            return self.returncode

    process = Popen()
    waited_children = []

    def wait_procs(processes, timeout):
        assert timeout == 2
        waited_children.extend(processes)
        return processes, []

    fake_psutil = types.SimpleNamespace(
        Process=lambda pid: RootMonitor(),
        Error=FakeProcessError,
        NoSuchProcess=FakeProcessError,
        wait_procs=wait_procs,
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: process)
    calls = []

    def monotonic():
        calls.append(None)
        return 0.0 if len(calls) == 1 else 2.0

    monkeypatch.setattr(runner.time, "monotonic", monotonic)
    result = runner.run_worker(
        job, timeout=1, memory_limit=0, interval=0.002, deadline=None
    )
    assert result["status"] == "timeout"
    assert process.returncode == -9 and process.waited is True
    assert child.killed is True and child in waited_children
    assert result["worker_peak_rss_bytes"] == 1700
    assert "seconds" not in result


def test_worker_bootstrap_does_not_expose_controller_site_packages(
    tmp_path, mock_source, monkeypatch
):
    """Use the same interpreter but mimic a harness beside controller-only packages."""
    controller_packages = tmp_path / "controller-site-packages"
    harness = controller_packages / "gamma_bench"
    harness.mkdir(parents=True)
    actual_harness = Path(runner.__file__).resolve().parent
    for module in actual_harness.glob("*.py"):
        shutil.copyfile(module, harness / module.name)
    sentinel = (
        controller_packages / "gamma_benchmark_forbidden_controller_dependency.py"
    )
    sentinel.write_text("CONTROLLER_ONLY = True\n", encoding="utf-8")
    job = make_job(tmp_path / "isolated-job", mock_source, "isolated_dependencies")
    monkeypatch.setenv("FORBIDDEN_HARNESS_PARENT", str(controller_packages))
    monkeypatch.setenv("PYTHONPATH", str(controller_packages))
    unrelated_home = tmp_path / "unrelated-python-home"
    unrelated_home.mkdir()
    monkeypatch.setenv("PYTHONHOME", str(unrelated_home))
    # Point the real subprocess launcher at the copied harness. The previous
    # cwd=ROOT/-m entry or inherited PYTHONPATH would expose the sentinel;
    # inherited PYTHONHOME would prevent this interpreter from starting.
    monkeypatch.setattr(runner, "__file__", str(harness / "runner.py"))
    monkeypatch.setattr(runner, "ROOT", controller_packages)
    result = run_mock_worker(job)
    assert result["status"] == "ok", result.get("error")
    assert result["repeatable"] is True
    assert result["provenance"]["api"] == "pymedphys.gamma"
