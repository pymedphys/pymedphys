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

"""Check design identifiability, pairing and bounded audit allowances."""

import copy
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import gamma_scaling as study
import gamma_uncertainty as audit
import gamma_uncertainty_report as report
import numpy as np
from gamma_scaling_worker import inputs


def recorded_fixture():
    """Known slopes with shared round noise, explicitly not measured evidence."""
    config = {
        "plan": [[3, "global", size, r] for r in range(8) for size in (1, 3, 9, 27)],
        "cases": {},
        "revisions": {"previous": "old", "current": "new"},
        "repeats": 1,
        "threads": 4,
    }
    result = {
        "config": config,
        "records": [],
        "comparisons": {},
        "host": {"processor": "SYNTHETIC TEST FIXTURE"},
        "cloud": {},
    }
    for _, profile, size, round_index in config["plan"]:
        case = study.case_id(3, profile, size)
        group = f"{case}-round-{round_index}"
        result["comparisons"][group] = {
            "revision_equality": "exact",
            "nan_pattern_equal": True,
        }
        noise = (0.97, 1.03, 0.98, 1.02, 1.01, 0.99, 1.04, 0.96)[round_index]
        for variant, slope in zip(study.VARIANTS, (4, 3, 16, 16)):
            result["records"].append(
                {
                    "id": f"{group}-{variant}",
                    "case": case,
                    "dimension": 3,
                    "profile": profile,
                    "scale": size,
                    "round": round_index,
                    "variant": variant,
                    "revision": config["revisions"][variant.split("-")[0]],
                    "verified": True,
                    "repeat_equality": True,
                    "numba_threads": 4,
                    "times": [slope * size * 0.1 * noise],
                    "points": size * 300000,
                    "eligible_points": size * 100000,
                    "input_sha256": f"input-{size}",
                    "versions": {},
                    "peak_process_rss_bytes": None,
                    "host": result["host"],
                    "cloud": {},
                    "status": "ok",
                }
            )
    return result


class UncertaintyTests(unittest.TestCase):
    def test_complete_balanced_design_and_two_hour_budget(self):
        plan, cases = audit.design({"2d": 1, "3d": 0.3, "diagnostic": 0.05})
        self.assertEqual(len(plan), 84)
        self.assertEqual(len(set(map(tuple, plan))), 84)
        counts = Counter(study.case_id(*g[:3]) for g in plan)
        self.assertEqual(sorted(counts.values()), [4] * 13 + [8] * 4)
        for case, count in counts.items():
            rounds = [g[3] for g in plan if study.case_id(*g[:3]) == case]
            self.assertEqual(sorted(rounds), list(range(count)))
            orders = np.array([study.ORDERS[r % 4] for r in rounds])
            for position in range(4):
                self.assertEqual(
                    Counter(orders[:, position]), dict.fromkeys(range(4), count // 4)
                )
        measured = sum(cases[study.case_id(*g[:3])]["comparison_seconds"] for g in plan)
        calibrated = 3 * sum(limit for _, limit, _ in audit.CALIBRATION.values())
        self.assertEqual(measured + calibrated, audit.maximum_measurement_seconds())
        self.assertLessEqual(measured + calibrated, 113 * 60)
        self.assertEqual(max(s["comparison_seconds"] for s in cases.values()), 300)
        self.assertEqual(cases["3d-sabr-1x"]["distance_mm_threshold"], 3)

    def test_padding_preserves_every_interior_dose_and_eligible_voxel(self):
        for width in (0.35, 0.65):
            values = []
            for padding in (1, 1.5):
                spec = audit.diagnostic_case(0.05, padding, width, "hard")
                config = dict(
                    spec,
                    dimension=3,
                    profile="diagnostic",
                    algorithm="pymedphys",
                    ram_bytes=2**28,
                )
                values.append(inputs(config))
            axes, reference, evaluation, options = values[0]
            padded_axes, padded_reference, padded_evaluation, _ = values[1]
            crop = tuple(
                slice((b - a) // 2, (b + a) // 2)
                for a, b in zip(reference.shape, padded_reference.shape)
            )
            np.testing.assert_array_equal(reference, padded_reference[crop])
            np.testing.assert_array_equal(evaluation, padded_evaluation[crop])
            for axis, padded_axis, selection in zip(axes, padded_axes, crop):
                np.testing.assert_array_equal(axis, padded_axis[selection])
            self.assertEqual(
                np.count_nonzero(reference >= 0.2),
                np.count_nonzero(padded_reference >= 0.2),
            )
            self.assertEqual(options["max_gamma"], 2)

    def test_resume_reconstructs_derived_cases_and_rejects_a_changed_workload(self):
        selected = {"2d": 1, "3d": 0.3, "diagnostic": 0.05}
        plan, cases = audit.design(selected)
        config = {"plan": plan, "cases": cases}
        audit.validate_plan(config, selected)
        config["cases"]["3d-sabr-1x"]["distance_mm_threshold"] = 2
        with self.assertRaisesRegex(ValueError, "original calibrated"):
            audit.validate_plan(config, selected)

    def test_affine_model_and_whole_size_holdout_recover_known_coefficients(self):
        x = np.array([0.05, 0.2, 0.8, 3.2])
        fitted = report.regression(x, 0.4 + 7 * x)
        self.assertAlmostEqual(fitted["affine_offset_seconds"], 0.4)
        self.assertAlmostEqual(fitted["affine_slope_seconds_per_million"], 7)
        np.testing.assert_allclose(
            fitted["affine_leave_one_size_out_errors_percent"], 0, atol=1e-10
        )

    def test_bootstrap_keeps_round_and_implementation_pairing(self):
        analysis = report.analyse(recorded_fixture())
        for model, expected in zip(analysis["models"], (4, 3, 16, 16)):
            self.assertAlmostEqual(model["origin_slope_seconds_per_million"], expected)
            lo, hi = model["origin_slope_repeat_interval_95"]
            self.assertLess(lo, expected)
            self.assertGreater(hi, expected)
        for ratio, expected in zip(analysis["ratios"], (4, 16 / 3)):
            self.assertAlmostEqual(ratio["ratio_of_origin_slopes"], expected)
            # Common round noise cancels only when pairing is retained.
            np.testing.assert_allclose(
                ratio["repeat_interval_95"], expected, atol=1e-12
            )

    def test_incomplete_round_is_excluded_as_a_whole_and_no_interval_invented(self):
        result = recorded_fixture()
        group = "3d-global-27x-round-7"
        del result["comparisons"][group]
        result["records"] = [
            r for r in result["records"] if not r["id"].startswith(group)
        ]
        analysis = report.analyse(result)
        self.assertFalse(result["complete"])
        self.assertEqual(
            analysis["coverage"]["3d-global"]["common_rounds"], list(range(7))
        )
        self.assertTrue(
            all(
                m["origin_slope_repeat_interval_95"] is None for m in analysis["models"]
            )
        )

    def test_input_changes_between_rounds_invalidate_repeatability(self):
        result = recorded_fixture()
        for record in result["records"]:
            if record["round"] == 7:
                record["input_sha256"] += "-different"
        with self.assertRaisesRegex(ValueError, "Inputs changed"):
            report.analyse(result)

    def test_report_renders_coefficients_and_figures_for_verified_data(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report.save_report(recorded_fixture(), output)
            for name in (
                "README.md",
                "uncertainty.json",
                "uncertainty.png",
                "model-coefficients.csv",
                "speed-ratios.csv",
                "timings.csv",
            ):
                self.assertTrue((output / name).is_file(), name)
            self.assertIn(
                "SYNTHETIC TEST FIXTURE",
                (output / "README.md").read_text(encoding="utf-8"),
            )

    def test_calibration_backoff_is_separate_from_main_measurements(self):
        elapsed = [0.0]

        def probe(config, _roots, _output, result, *_):
            scale = config["plan"][0][2]
            result["complete"] = scale <= 0.4
            elapsed[0] += 20 if result["complete"] else 40

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(audit.CALIBRATION, {"2d": (1.0, 45, 25)}, clear=True),
                patch(
                    "gamma_uncertainty.time.monotonic", side_effect=lambda: elapsed[0]
                ),
                patch("gamma_scaling.run_study", side_effect=probe),
                patch("gamma_scaling.validate_records"),
            ):
                selected = audit.calibrate({}, {}, Path(directory), {}, {}, None, 1000)
            self.assertAlmostEqual(selected["2d"], 1 / 3)
            self.assertFalse((Path(directory) / "results.json").exists())

    def test_diagnostic_report_identifies_separate_grid_and_eligible_cost(self):
        result = recorded_fixture()
        result["config"]["plan"] = []
        result["config"]["cases"] = {}
        template = copy.deepcopy(result["records"][0])
        result["records"], result["comparisons"] = [], {}
        for cell, (grid, eligible) in enumerate(
            ((1, 0.1), (1, 0.3), (3, 0.1), (3, 0.3)), 1
        ):
            case = study.case_id(3, "diagnostic", cell)
            result["config"]["cases"][case] = {"model_geometry": {"difficulty": "easy"}}
            for r in range(4):
                result["config"]["plan"].append([3, "diagnostic", cell, r])
                group = f"{case}-round-{r}"
                result["comparisons"][group] = {
                    "revision_equality": "exact",
                    "nan_pattern_equal": True,
                }
                for variant in study.VARIANTS:
                    result["records"].append(
                        {
                            **template,
                            "id": f"{group}-{variant}",
                            "case": case,
                            "profile": "diagnostic",
                            "round": r,
                            "variant": variant,
                            "revision": result["config"]["revisions"][
                                variant.split("-")[0]
                            ],
                            "points": int(grid * 1e6),
                            "eligible_points": int(eligible * 1e6),
                            "times": [0.2 + 2 * grid + 7 * eligible],
                        }
                    )
        fitted = report.analyse(result)["diagnostic_models"]
        self.assertEqual(len(fitted), 4)
        for model in fitted:
            self.assertAlmostEqual(model["offset_seconds"], 0.2)
            self.assertAlmostEqual(model["grid_seconds_per_million"], 2)
            self.assertAlmostEqual(model["eligible_seconds_per_million"], 7)


if __name__ == "__main__":
    unittest.main()
