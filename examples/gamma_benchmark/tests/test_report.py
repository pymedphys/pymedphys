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

"""Renderer verification using fabricated TEST DATA only; never runs gamma."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from gamma_bench.report import (
    _by_study,
    _groups,
    _paired_ratios,
    _verified,
    build_report,
)


def _verification(valid=True):
    return {
        "same_nan_mask": True,
        "all_finite_analysed": True,
        "max_abs_difference": 0.0 if valid else 0.2,
        "pass_disagreements": 0 if valid else 1,
        "exact_equal": valid,
        "repeatable": True,
        "within_tolerance": valid,
        "gamma_abs_tolerance": 1e-6,
        "allowed_pass_disagreements": 0,
        "valid": valid,
    }


def _fixture(directory: Path):
    names = ["reference engine", "candidate/one", "candidate <two>"]
    records = []
    for number, (n, fraction) in enumerate([(8, 0.3), (8, 0.6), (12, 0.3), (12, 0.6)]):
        case = {
            "id": f"TEST-DATA-{number}",
            "study": "TEST DATA grid/fraction",
            "dimension": 2,
            "n": n,
            "field": "gaussian",
            "above_fraction_target": fraction,
            "fraction_mode": "cutoff",
            "distance_mm_threshold": 3,
            "interp_fraction": 10,
            "max_gamma": 2,
            "ram_mib": 64,
            "threads": 1,
            "shift_mm": 1,
            "dose_scale": 1,
        }
        variants = {}
        for index, name in enumerate(names):
            factor = (1.0, 0.7, 1.2)[index]
            seconds = [
                (1 + number * 0.2) * multiplier * factor for multiplier in (1.0, 1.05)
            ]
            variants[name] = {
                "status": "ok",
                "seconds": seconds,
                "first_call_seconds": seconds[0] * 1.5,
                "peak_rss_bytes": (60 + n) * 2**20,
                "pre_gamma_rss_bytes": 50 * 2**20,
                "memory_sample_interval_ms": 5,
                "rounds": [
                    {
                        "round": i,
                        "seconds": seconds[i],
                        "started_at": f"2026-01-01T00:{number * 3 + index:02d}:{i * 10:02d}+00:00",
                        "order_position": index,
                    }
                    for i in range(2)
                ],
                "diagnostics": {
                    "total_candidate_queries": n * n * 5,
                    "trace": [
                        {
                            "distance": 0,
                            "active": 20,
                            "shell_points": 1,
                            "candidate_queries": 20,
                        },
                        {
                            "distance": 0.3,
                            "active": 12,
                            "shell_points": 7,
                            "candidate_queries": 84,
                        },
                    ],
                },
            }
            if number == 0:
                filename = f"representative-{index}.npz"
                reference = np.arange(16, dtype=float).reshape(4, 4)
                gamma = reference / 16
                gamma[0, 0] = np.nan
                np.savez_compressed(
                    directory / filename,
                    reference_slice=reference,
                    evaluation_slice=reference * 1.01,
                    gamma_slice=gamma,
                    finite_gamma_sample=gamma[np.isfinite(gamma)],
                )
                variants[name]["representative_file"] = filename
        comparisons = {
            name: {
                "verification": _verification(),
                "timing": {"paired_speedups": [1 / factor, 1 / factor]},
            }
            for name, factor in zip(names[1:], (0.7, 1.2))
        }
        # A failing second candidate must not suppress the first candidate's
        # valid pairwise comparison in a multi-version run.
        if number == 1:
            comparisons[names[2]]["verification"] = _verification(False)
            comparisons[names[2]]["timing"]["paired_speedups"] = [99, 99]
        records.append(
            {
                "case": case,
                "metadata": {
                    "total_points": n * n,
                    "eligible_points": round(n * n * fraction),
                    "eligible_fraction": round(n * n * fraction) / (n * n),
                },
                "status": "mismatch" if number == 1 else "ok",
                "variants": variants,
                "comparisons": comparisons,
            }
        )
    pending_case = {"id": "TEST-DATA-pending", "study": "TEST DATA missing"}
    timeout_case = {"id": "TEST-DATA-timeout", "study": "TEST DATA missing"}
    records.append(
        {
            "case": timeout_case,
            "status": "timeout",
            "error": "TEST DATA <timeout>",
            "variants": {},
        }
    )
    plan = {
        "schema_version": 1,
        "test_data": True,
        "cases": [r["case"] for r in records] + [pending_case],
    }
    summary = {
        "schema_version": 1,
        "test_data": True,
        "baseline": names[0],
        "implementations": names,
        "run_status": "TEST DATA incomplete",
        "planned_cases": len(plan["cases"]),
        "completed_cases": 4,
        "records": records,
        "settings": {"gamma_abs_tolerance": 1e-6},
    }
    for name, data in [
        ("plan.json", plan),
        ("summary.json", summary),
        ("environment.json", {"test_data": True}),
    ]:
        (directory / name).write_text(json.dumps(data), encoding="utf-8")
    (directory / "config.resolved.json").write_text(
        json.dumps({"test_data": True}), encoding="utf-8"
    )
    (directory / "summary.csv").write_text("test_data\ntrue\n", encoding="utf-8")
    return summary


class VerificationGateTests(unittest.TestCase):
    def test_study_membership_and_notes_do_not_split_control_groups(self):
        records = [
            {
                "case": {
                    "id": "one",
                    "study": "grid",
                    "studies": ["grid", "fraction"],
                    "n": 8,
                    "threads": 1,
                }
            },
            {
                "case": {
                    "id": "two",
                    "study": "grid",
                    "studies": ["grid"],
                    "notes": "TEST DATA",
                    "n": 12,
                    "threads": 1,
                }
            },
        ]
        self.assertEqual(len(_groups(records, {"n"})), 1)
        studies = _by_study(records)
        self.assertEqual(len(studies["grid"]), 2)
        self.assertEqual(len(studies["fraction"]), 1)

    def test_only_valid_paired_ratios_are_accepted(self):
        record = {"status": "mismatch"}
        comparison = {
            "verification": _verification(),
            "timing": {"paired_speedups": [2.0, 2.1]},
        }
        self.assertTrue(_verified(record, comparison))
        np.testing.assert_array_equal(_paired_ratios(record, comparison), [2.0, 2.1])
        for field in (
            "valid",
            "within_tolerance",
            "same_nan_mask",
            "all_finite_analysed",
            "repeatable",
        ):
            failed = deepcopy(comparison)
            failed["verification"][field] = False
            self.assertEqual(_paired_ratios(record, failed).size, 0)

    def test_configured_pass_tolerance_is_honoured(self):
        comparison = {"verification": _verification()}
        comparison["verification"]["pass_disagreements"] = 1
        self.assertFalse(_verified({}, comparison))
        comparison["verification"]["allowed_pass_disagreements"] = 1
        self.assertTrue(_verified({}, comparison))

    def test_missing_pairing_is_not_invented_from_medians(self):
        comparison = {"verification": _verification(), "timing": {"median_speedup": 2}}
        self.assertEqual(_paired_ratios({}, comparison).size, 0)


class RenderingTests(unittest.TestCase):
    def test_mock_evidence_generates_offline_exportable_report(self):
        with tempfile.TemporaryDirectory(prefix="gamma-report-TEST-DATA-") as temporary:
            directory = Path(temporary)
            summary = _fixture(directory)
            produced = build_report(directory)
            self.assertTrue(
                all(path.is_file() and path.stat().st_size > 0 for path in produced)
            )
            html = (directory / "index.html").read_text(encoding="utf-8")
            self.assertIn("TEST DATA", html)
            self.assertIn("candidate &lt;two&gt;", html)
            self.assertIn("TEST DATA &lt;timeout&gt;", html)
            self.assertNotIn("https://", html)
            self.assertIn('alt="', html)
            self.assertIn('href="summary.csv"', html)
            self.assertIn('href="config.resolved.json"', html)
            self.assertIn("TEST-DATA-pending", html)
            manifest = json.loads(
                (directory / "report_manifest.json").read_text(encoding="utf-8")
            )
            stems = [figure["files"][0] for figure in manifest["figures"]]
            for expected in (
                "coverage",
                "planned-design",
                "runtime-grid",
                "runtime-eligible-fraction",
                "speedups",
                "heatmap-grid-fraction",
                "memory",
                "agreement",
                "timing-stability",
                "candidate-queries",
                "trace",
                "atlas",
                "gamma-distribution",
                "illustration-shell",
            ):
                self.assertTrue(any(expected in stem for stem in stems), expected)
            for figure in manifest["figures"]:
                self.assertEqual(
                    {Path(file).suffix for file in figure["files"]},
                    {".png", ".svg", ".pdf"},
                )
                self.assertTrue(figure["alt"])
            # The rejected 99x ratio remains in raw evidence and is never
            # accepted by the speed-up selection helper.
            invalid = summary["records"][1]["comparisons"]["candidate <two>"]
            self.assertEqual(_paired_ratios(summary["records"][1], invalid).size, 0)

    def test_empty_plan_does_not_fabricate_measurements(self):
        with tempfile.TemporaryDirectory(
            prefix="gamma-report-EMPTY-TEST-DATA-"
        ) as temporary:
            directory = Path(temporary)
            (directory / "plan.json").write_text(
                json.dumps({"test_data": True, "cases": []}), encoding="utf-8"
            )
            build_report(directory)
            html = (directory / "index.html").read_text(encoding="utf-8")
            self.assertIn("No measurements recorded yet", html)
            self.assertIn("No speed-up figure", html)
            manifest = json.loads(
                (directory / "report_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(manifest["figures"]), 2)
            self.assertTrue(
                all("Illustration:" in item["title"] for item in manifest["figures"])
            )

    def test_representative_path_cannot_escape_run_directory(self):
        with tempfile.TemporaryDirectory(
            prefix="gamma-report-PATH-TEST-DATA-"
        ) as temporary:
            directory = Path(temporary)
            summary = {
                "test_data": True,
                "baseline": "name",
                "records": [
                    {
                        "case": {"id": "TEST DATA"},
                        "status": "pending",
                        "variants": {
                            "name": {"representative_file": "../unrelated.npz"}
                        },
                    }
                ],
            }
            (directory / "summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )
            build_report(directory)
            manifest = json.loads(
                (directory / "report_manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                any("outside the run directory" in note for note in manifest["notes"])
            )


if __name__ == "__main__":
    unittest.main()
