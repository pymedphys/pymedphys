import unittest
import pytest


class PytestExitCode(unittest.TestCase):
    def test_pytest(self):
        self.assertEqual(main(), 0)


def main():
    return pytest.main([
        "-v", "--pylint", "--pylint-error-types=EF", "--mypy",
        "--doctest-modules", "--doctest-continue-on-failure",
        "--doctest-plus", "--doctest-rst"])
