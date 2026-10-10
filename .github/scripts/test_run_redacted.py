"""Tests of run_redacted.py."""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from run_redacted import CRASHED, code_location, run

SECRET = "SYNTHETIC-PATIENT-NAME"


def _quiet(main, arguments=()):
    output = StringIO()
    with redirect_stdout(output):
        status = run(main, list(arguments))
    return status, output.getvalue()


class RunRedactedTests(unittest.TestCase):
    def test_returns_the_status_of_main(self):
        self.assertEqual(_quiet(lambda arguments: 0), (0, ""))
        self.assertEqual(_quiet(lambda arguments: None), (0, ""))
        self.assertEqual(_quiet(lambda arguments: 3), (3, ""))

    def test_passes_the_arguments(self):
        seen = []
        _quiet(seen.extend, ["--a", "b"])
        self.assertEqual(seen, ["--a", "b"])

    def test_prints_a_refusal_which_quotes_no_value_by_contract(self):
        def main(arguments):
            raise SystemExit("the work directory must not exist")

        self.assertEqual(_quiet(main), (1, "the work directory must not exist\n"))

    def test_keeps_a_numeric_exit(self):
        def main(arguments):
            raise SystemExit(4)

        self.assertEqual(_quiet(main), (4, ""))

    def test_a_crash_names_its_type_and_frames_but_no_message(self):
        def inner():
            try:
                raise KeyError(SECRET)
            except KeyError as error:
                raise ValueError(f"/data/{SECRET}/1.dcm") from error

        def main(arguments):
            inner()

        status, output = _quiet(main)
        self.assertEqual(status, CRASHED)
        self.assertNotIn(SECRET, output)
        self.assertNotIn("/data", output)
        self.assertIn("builtins.ValueError was raised at:", output)
        self.assertIn("while handling:", output)
        self.assertIn("builtins.KeyError was raised at:", output)
        self.assertIn(" in inner", output)

    def test_a_private_stdout_keeps_the_modules_output_and_not_the_report(self):
        script = Path(__file__).with_name("run_redacted.py")
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "leaky.py").write_text(
                textwrap.dedent(
                    f"""
                    import subprocess, sys

                    def main(arguments):
                        print("{SECRET}")
                        subprocess.run(
                            [sys.executable, "-c", "print('{SECRET} child')"],
                            check=True,
                        )
                        raise ValueError("{SECRET}")
                    """
                ),
                encoding="utf-8",
            )
            private = Path(directory, "stdout.log")
            completed = subprocess.run(
                [sys.executable, script, "--private-stdout", private, "leaky"],
                capture_output=True,
                text=True,
                cwd=directory,
                env={**os.environ, "PYTHONPATH": directory},
                check=False,
            )
            kept = private.read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, CRASHED)
        self.assertNotIn(SECRET, completed.stdout)
        self.assertIn("builtins.ValueError was raised at:", completed.stdout)
        self.assertEqual(kept, f"{SECRET}\n{SECRET} child\n")

    def test_code_locations_drop_installation_paths(self):
        self.assertEqual(
            code_location("/v/lib/python3.14/site-packages/pydicom/x.py"),
            "pydicom/x.py",
        )
        self.assertEqual(
            code_location("/w/pymedphys/lib/pymedphys/_dicom/run.py"),
            "pymedphys/_dicom/run.py",
        )
        self.assertEqual(code_location(f"/data/{SECRET}/a.py"), "<elsewhere>")


if __name__ == "__main__":
    unittest.main()
