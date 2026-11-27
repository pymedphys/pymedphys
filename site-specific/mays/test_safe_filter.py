"""Regression tests for GUI filter expressions."""

import unittest

import pandas as pd

from safe_filter import evaluate_filter


class FilterTests(unittest.TestCase):
    def test_numeric_and_chained_comparisons(self):
        values = pd.Series([1, 2, 3, 4])
        self.assertEqual(evaluate_filter(values, "_ >= 2").tolist(), [False, True, True, True])
        self.assertEqual(evaluate_filter(values, "1 < _ < 4").tolist(), [False, True, True, False])

    def test_composed_conditions_and_literal_underscores(self):
        values = pd.Series(["a_b", "a", "b"])
        self.assertEqual(evaluate_filter(values, "(_ == 'a_b') | (_ == 'b')").tolist(), [True, False, True])

    def test_rejects_executable_expressions(self):
        values = pd.Series([1, 2])
        for expression in (
            "__import__('os').system('echo UNSAFE')",
            "_.__class__",
            "_[0]",
            "(_ > 1) and (__import__('os'))",
        ):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                evaluate_filter(values, expression)

    def test_rejects_excessively_long_expressions(self):
        with self.assertRaises(ValueError):
            evaluate_filter(pd.Series([1]), "_" * 1025)


if __name__ == "__main__":
    unittest.main()
