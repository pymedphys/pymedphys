"""Audit planning and deadline checks without long gamma calculations."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gamma_performance_audit as audit
import gamma_scaling as study
import numpy as np
from gamma_scaling_worker import SCENARIOS, scenario_field


class AuditTests(unittest.TestCase):
    def test_frozen_plan_has_full_balanced_coverage_and_fixed_scenarios(self):
        selections = {f"{d}d-{p}": 0.1 if d == 3 else 1.0 for d, p in audit.FAMILIES}
        plan = audit.audit_plan(selections)
        self.assertEqual(len(plan), 74)
        self.assertEqual(len({tuple(group) for group in plan}), 74)
        for d, p in audit.FAMILIES:
            groups = [g for g in plan if g[:2] == [d, p]]
            self.assertEqual(len(groups), 12)
            self.assertEqual(len({study.shape_for(d, g[2]) for g in groups}), 3)
            for scale in {g[2] for g in groups}:
                self.assertEqual({g[3] for g in groups if g[2] == scale}, {0, 1, 2, 3})
        self.assertEqual(
            plan[-2:], [[3, "sabr", 1.0, 0], [3, "prostate-nodes", 1.0, 0]]
        )
        result = audit.empty_result({"plan": plan}, {}, {})
        study.validate_records(result)
        self.assertEqual(result["expected_groups"], 74)
        self.assertFalse(result["complete"])
        self.assertLessEqual(audit.maximum_measurement_seconds(), 108 * 60)

    def test_calibration_backs_off_and_keeps_probes_out_of_main_results(self):
        elapsed = [0.0]

        def probe(config, _roots, _output, result, *_):
            scale = config["plan"][0][2]
            result["complete"] = scale <= 0.4
            elapsed[0] += 20 if result["complete"] else 40

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with (
                patch.object(audit, "FAMILIES", ((2, "global"),)),
                patch(
                    "gamma_performance_audit.time.monotonic",
                    side_effect=lambda: elapsed[0],
                ),
                patch("gamma_scaling.run_study", side_effect=probe),
                patch("gamma_scaling.validate_records"),
            ):
                selected = audit.calibrate({}, {}, output, {}, {}, None, 1000)
            record = json.loads((output / "calibration.json").read_text())
            self.assertAlmostEqual(selected["2d-global"], 1 / 3)
            self.assertLessEqual(len(record["probes"]), 3)
            self.assertFalse((output / "results.json").exists())
            self.assertTrue(all("result" in p for p in record["probes"]))

    def test_comparison_deadline_is_shared_across_workers(self):
        elapsed = [100.0]
        allowances = []
        config = {
            "plan": [[2, "global", 0.1, 0]],
            "threads": 1,
            "worker_timeout": 600,
            "ram_bytes": 1024,
            "repeats": 1,
            "revisions": {"previous": "old", "current": "new"},
            "comparison_seconds": 13,
        }
        result = audit.empty_result(config, {}, {})

        def worker(command, *, timeout, **_):
            allowances.append(timeout)
            if len(allowances) == 2:
                elapsed[0] += timeout
                raise subprocess.TimeoutExpired(command, timeout)
            elapsed[0] += 0.8
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "numba_threads": 1,
                        "shape": list(study.shape_for(2, 0.1)),
                        "finite_points": 1,
                        "eligible_points": 1,
                        "times": [0.1],
                        "warmup_seconds": 0.1,
                    }
                ),
            )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with (
                patch("gamma_scaling.time.monotonic", side_effect=lambda: elapsed[0]),
                patch("gamma_scaling.run_command", side_effect=worker),
                patch("gamma_scaling.checked_checkout"),
            ):
                study.run_study(
                    config, {"previous": output, "current": output}, output, result
                )
        self.assertEqual(len(allowances), 2)
        self.assertAlmostEqual(allowances[0], 2)
        self.assertAlmostEqual(allowances[1], 1.2)
        self.assertNotIn("times", result["records"][-1])
        self.assertFalse(result["comparisons"])

    def test_scenario_extents_spacing_and_asymmetry(self):
        for name, extent, count in (
            ("sabr", (250, 300, 300), 11674281),
            ("prostate-nodes", (500, 400, 400), 5210121),
        ):
            spec = SCENARIOS[name]
            self.assertEqual(int(np.prod(spec["shape"])), count)
            self.assertEqual(
                tuple((n - 1) * spec["spacing_mm"] for n in spec["shape"]), extent
            )
        axes = (
            np.array([-120.0, 0.0, 120.0]),
            np.array([-35.0, 0.0, 35.0]),
            np.array([-35.0, 0.0, 35.0]),
        )
        sabr = scenario_field(axes, "sabr")
        np.testing.assert_array_equal(sabr, sabr[::-1, ::-1, ::-1])
        pelvis = scenario_field(axes, "prostate-nodes")
        self.assertGreater(pelvis[0, 1, 1], pelvis[2, 1, 1])
        self.assertTrue(np.isfinite(pelvis).all())
        self.assertTrue((pelvis >= 0).all())

    def test_verification_timeout_does_not_abandon_later_groups(self):
        config = {
            "plan": [[2, "global", 0.1, r] for r in range(2)],
            "threads": 1,
            "worker_timeout": 60,
            "ram_bytes": 1024,
            "repeats": 1,
            "revisions": {"previous": "old", "current": "new"},
            "comparison_seconds": 45,
        }
        result = audit.empty_result(config, {}, {})
        checks = []

        def worker(command, *, timeout, **_):
            if "--compare-arrays" in command:
                checks.append(command)
                raise subprocess.TimeoutExpired(command, timeout)
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "numba_threads": 1,
                        "shape": list(study.shape_for(2, 0.1)),
                        "finite_points": 1,
                        "eligible_points": 1,
                        "times": [0.1],
                        "warmup_seconds": 0.1,
                        "input_sha256": "same",
                        "versions": {},
                    }
                ),
            )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with (
                patch("gamma_scaling.run_command", side_effect=worker),
                patch("gamma_scaling.checked_checkout"),
            ):
                study.run_study(
                    config, {"previous": output, "current": output}, output, result
                )
        self.assertEqual(len(checks), 2)
        self.assertEqual(len(result["records"]), 8)
        self.assertEqual(len(result["incomplete_groups"]), 2)
        self.assertFalse(result["comparisons"])
        self.assertNotIn("stop_reason", result)


if __name__ == "__main__":
    unittest.main()
