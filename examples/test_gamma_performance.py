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

"""How the fixed-grid benchmark compares gamma within and between revisions.

Each revision must repeat its gamma exactly. Two revisions may differ by the
rounding of the search step, within REVISION_ABSOLUTE_TOLERANCE, but not in
NaN or infinite positions or in pass or fail. No gamma calculation runs here:
the workers are replaced by arrays chosen for each check.
"""

import copy
import hashlib
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import gamma_performance
from gamma_performance import (
    REVISION_ABSOLUTE_TOLERANCE,
    compare_revisions,
    run_benchmark,
    validate_result,
)


class CompareRevisionsTests(unittest.TestCase):
    def test_equal_arrays_are_exact(self):
        gamma = np.array([np.nan, 0.5, 1.0, np.inf])
        compared = compare_revisions(gamma, gamma.copy())
        self.assertEqual(
            compared,
            {"exact": True, "max_abs_difference": 0.0, "pass_disagreements": 0},
        )

    def test_rounding_differences_are_accepted_and_recorded(self):
        old = np.array([np.nan, 0.5, 0.9])
        compared = compare_revisions(old, old + [0, 3e-13, -7e-15])
        self.assertFalse(compared["exact"])
        self.assertAlmostEqual(compared["max_abs_difference"], 3e-13, delta=1e-15)

    def test_a_difference_above_the_allowance_is_rejected(self):
        old = np.array([0.5])
        new = old + 2 * REVISION_ABSOLUTE_TOLERANCE
        with self.assertRaisesRegex(AssertionError, "differs by up to 2e-10"):
            compare_revisions(old, new)

    def test_a_pass_fail_disagreement_is_rejected_even_within_the_allowance(self):
        with self.assertRaisesRegex(AssertionError, "1 points pass in one"):
            compare_revisions(np.array([1.0, 0.5]), np.array([1.0 + 1e-12, 0.5]))

    def test_a_change_in_nan_or_infinite_positions_is_rejected(self):
        for old, new in (
            ([np.nan, 0.5], [0.5, 0.5]),
            ([0.5, 0.5], [0.5, np.nan]),
            ([np.inf, 0.5], [3.0, 0.5]),
            ([np.inf, 0.5], [np.nan, 0.5]),
        ):
            with self.subTest(old=old, new=new):
                with self.assertRaisesRegex(AssertionError, "NaN or infinite"):
                    compare_revisions(np.array(old), np.array(new))

    def test_a_change_of_shape_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, "shapes differ"):
            compare_revisions(np.ones((2, 3)), np.ones((3, 2)))

    def test_every_disagreement_is_reported(self):
        with self.assertRaises(AssertionError) as raised:
            compare_revisions(np.array([np.nan, 0.5]), np.array([0.5, 1.5]))
        message = str(raised.exception)
        self.assertIn("NaN or infinite", message)
        self.assertIn("pass in one revision", message)
        self.assertIn("differs by up to 1", message)


def worker(arrays):
    """Stand in for subprocess.run of the benchmark worker.

    ``arrays`` gives the gamma that each (case, version, round) returns.
    """
    calls = {}

    def run(command, env, **_):
        _, _, case, repeats, root, array_path = command
        version = Path(root).name
        index = calls.get((case, version), 0)
        calls[(case, version)] = index + 1
        gamma = np.asarray(arrays[(case, version, index)])
        np.save(array_path, gamma, allow_pickle=False)
        finite = np.isfinite(gamma)
        record = {
            "case": case,
            "shape": list(gamma.shape),
            "input_sha256": "same inputs",
            "eligible_points": int(finite.sum()),
            "finite_points": int(finite.sum()),
            "pass_count": int(np.count_nonzero(gamma <= 1)),
            "nan_count": int(np.isnan(gamma).sum()),
            "points": int(gamma.size),
            "times": [0.5] * int(repeats),
            "origins": {"pymedphys": str(Path(root) / "lib/pymedphys/__init__.py")},
            "python": "3.14.0",
            "platform": "test",
            "processor": "test",
            "versions": {"numpy": np.__version__},
            "numba_threads": int(env["NUMBA_NUM_THREADS"]),
        }
        return types.SimpleNamespace(stdout=json.dumps(record))

    return run


def benchmark(arrays, rounds=2):
    """Run the benchmark's controller on the arrays given for each round."""
    with tempfile.TemporaryDirectory() as directory:
        roots = {}
        for version in ("previous", "current"):
            roots[version] = Path(directory) / version
            (roots[version] / "lib" / "pymedphys").mkdir(parents=True)
        with (
            mock.patch.object(
                gamma_performance, "checked_checkout", lambda path, _: Path(path)
            ),
            mock.patch.object(gamma_performance.subprocess, "run", worker(arrays)),
        ):
            return run_benchmark(
                roots["previous"],
                "a" * 40,
                roots["current"],
                "b" * 40,
                cases=["2d"],
                rounds=rounds,
                repeats=2,
                threads=2,
            )


class RunBenchmarkTests(unittest.TestCase):
    def test_revisions_that_differ_by_rounding_are_compared_and_plotted(self):
        old = np.array([np.nan, 0.25, 0.9, 1.5])
        new = old + [0, 7e-15, -3e-13, 0]
        arrays = {("2d", "previous", r): old for r in range(2)}
        arrays.update({("2d", "current", r): new for r in range(2)})

        result = benchmark(arrays)

        compared = result["revision_agreement"]["2d"]
        self.assertFalse(compared["exact"])
        self.assertAlmostEqual(compared["max_abs_difference"], 3e-13, delta=1e-15)
        self.assertEqual(
            result["revision_absolute_tolerance"], REVISION_ABSOLUTE_TOLERANCE
        )
        self.assertTrue(all(record["repeat_equal"] for record in result["records"]))
        agreement, tolerance = validate_result(result)
        self.assertEqual(agreement, result["revision_agreement"])
        self.assertEqual(tolerance, REVISION_ABSOLUTE_TOLERANCE)

    def test_a_revision_must_repeat_its_gamma_exactly(self):
        gamma = np.array([0.25, 0.9])
        arrays = {("2d", version, 0): gamma for version in ("previous", "current")}
        arrays[("2d", "previous", 1)] = gamma
        # The second round differs by less than the cross-revision allowance.
        arrays[("2d", "current", 1)] = gamma + [1e-13, 0]
        with self.assertRaisesRegex(AssertionError, "current revision did not repeat"):
            benchmark(arrays)

    def test_revisions_that_sample_differently_are_reported(self):
        # A change in the sampled points, as a change in the step's rounding
        # can cause, turns a fail into a pass.
        arrays = {
            ("2d", "previous", 0): np.array([1.55, 0.5]),
            ("2d", "current", 0): np.array([0.24, 0.5]),
        }
        with self.assertRaisesRegex(
            AssertionError, "2d: .*1 points pass in one revision"
        ):
            benchmark(arrays, rounds=1)


class ValidateResultTests(unittest.TestCase):
    def setUp(self):
        old = np.array([np.nan, 0.25, 0.9])
        new = old + [0, 0, 3e-13]
        arrays = {("2d", "previous", r): old for r in range(2)}
        arrays.update({("2d", "current", r): new for r in range(2)})
        self.result = benchmark(arrays)

    def test_a_result_saved_before_the_allowance_is_accepted_if_equal(self):
        legacy = copy.deepcopy(self.result)
        del legacy["revision_agreement"], legacy["revision_absolute_tolerance"]
        legacy["elementwise_equal"] = True
        for record in legacy["records"]:
            record["elementwise_equal"] = record.pop("repeat_equal")
            record["gamma_sha256"] = hashlib.sha256(b"equal").hexdigest()
        agreement, tolerance = validate_result(legacy)
        self.assertEqual(tolerance, 0.0)
        self.assertTrue(agreement["2d"]["exact"])

        # Those results never held unequal arrays.
        legacy["records"][0]["gamma_sha256"] = "different"
        with self.assertRaises(AssertionError):
            validate_result(legacy)

    def test_inconsistent_results_are_refused(self):
        def changed(edit):
            result = copy.deepcopy(self.result)
            edit(result)
            return result

        def different_repeat(result):
            result["records"][0]["gamma_sha256"] = "different"

        def looser_tolerance(result):
            result["revision_absolute_tolerance"] = 1e-6
            result["revision_agreement"]["2d"]["max_abs_difference"] = 1e-7

        def pass_disagreement(result):
            result["revision_agreement"]["2d"]["pass_disagreements"] = 1

        def different_pass_count(result):
            result["records"][0]["pass_count"] += 1

        def claimed_exact(result):
            result["revision_agreement"]["2d"]["exact"] = True

        for edit in (
            different_repeat,
            looser_tolerance,
            pass_disagreement,
            different_pass_count,
            claimed_exact,
        ):
            with self.subTest(edit=edit.__name__):
                with self.assertRaises(AssertionError):
                    validate_result(changed(edit))


if __name__ == "__main__":
    unittest.main()
