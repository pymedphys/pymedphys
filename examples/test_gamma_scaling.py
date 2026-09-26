"""Checks for benchmark integrity; no expensive gamma run is needed here."""

import itertools
import tempfile
import unittest
from pathlib import Path

import numpy as np
from gamma_scaling import (
    BASE_SHAPES,
    ORDERS,
    VARIANTS,
    compare_arrays,
    paired_ratios,
    shape_for,
)


class ScalingIntegrityTests(unittest.TestCase):
    def paired_example(self):
        return {
            "records": [
                {
                    "case": "example",
                    "round": index,
                    "variant": variant,
                    "verified": True,
                    "times": [seconds],
                    "host": {"processor": "example CPU"},
                    "cloud": {"job": index},
                }
                for variant, times in (
                    ("previous-pymedphys", (1, 2, 10, 20)),
                    ("current-pymedphys", (0.5, 2, 1, 40)),
                )
                for index, seconds in enumerate(times)
            ]
        }

    def test_ratios_preserve_runner_pairing_before_aggregation(self):
        ratios = paired_ratios(
            self.paired_example(), "example", "current-pymedphys", "previous-pymedphys"
        )
        np.testing.assert_array_equal(ratios, [0.5, 1, 0.1, 2])
        self.assertEqual(np.median(ratios), 0.75)
        # Dividing the two overall medians would instead give 1.5 / 6 = 0.25.

    def test_ratios_reject_unmatched_runner_or_round(self):
        for change in ("runner", "round"):
            result = self.paired_example()
            if change == "runner":
                result["records"][-1]["cloud"] = {"job": "different runner"}
            else:
                result["records"].pop()
            with self.assertRaises(ValueError):
                paired_ratios(
                    result, "example", "current-pymedphys", "previous-pymedphys"
                )

    def test_balanced_order_and_carryover(self):
        for column in zip(*ORDERS):
            self.assertEqual(set(column), set(range(4)))
        transitions = [(a, b) for order in ORDERS for a, b in itertools.pairwise(order)]
        self.assertEqual(set(transitions), set(itertools.permutations(range(4), 2)))
        self.assertEqual(len(transitions), len(set(transitions)))

    def test_size_limit_and_monotonicity(self):
        ceiling = 100 * max(np.prod(s) for s in BASE_SHAPES.values())
        for dimension in (2, 3):
            counts = [
                np.prod(shape_for(dimension, scale)) for scale in (1, 3, 10, 30, 100)
            ]
            self.assertEqual(counts, sorted(set(counts)))
            self.assertLessEqual(counts[-1], ceiling)
            self.assertGreater(counts[-1], 95 * counts[0])
        with self.assertRaises(ValueError):
            shape_for(3, 101)

    def check_arrays(self, arrays):
        with tempfile.TemporaryDirectory() as directory:
            paths = {}
            for variant, array in zip(VARIANTS, arrays):
                path = Path(directory) / f"{variant}.npy"
                np.save(path, array, allow_pickle=False)
                paths[variant] = path
            return compare_arrays(paths)

    def test_exact_revision_and_tolerant_algorithm_comparisons(self):
        reference = np.array([0.2, np.nan, 1.1])
        scipy = np.array([0.2 + 1e-12, np.nan, 1.1])
        result = self.check_arrays([reference, reference, scipy, scipy])
        self.assertEqual(result["revision_equality"], "exact")
        self.assertGreater(result["algorithm_max_abs_difference"], 0)
        self.assertEqual(result["algorithm_pass_disagreements"], 0)

    def test_changed_revision_value_is_rejected(self):
        with self.assertRaises(AssertionError):
            self.check_arrays(
                [
                    np.array([1.0]),
                    np.array([1.0 + 1e-12]),
                    np.array([1.0]),
                    np.array([1.0]),
                ]
            )

    def test_changed_nan_position_is_rejected(self):
        with self.assertRaises(AssertionError):
            self.check_arrays(
                [np.array([np.nan, 0.5])] * 2 + [np.array([0.5, np.nan])] * 2
            )

    def test_large_algorithm_difference_is_rejected(self):
        with self.assertRaises(AssertionError):
            self.check_arrays([np.array([0.5])] * 2 + [np.array([0.51])] * 2)


if __name__ == "__main__":
    unittest.main()
