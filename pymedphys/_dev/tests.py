import os
import pathlib
import subprocess

LIBRARY_ROOT = pathlib.Path(__file__).parent.parent.resolve()


def run_tests(_, remaining):
    original_cwd = os.getcwd()
    os.chdir(LIBRARY_ROOT.parent)

    try:
        command = " ".join(
            ["pytest"] + remaining + ["--pyargs", "pymedphys", "--failed-first"]
        )

        subprocess.check_call(command, shell=True)
    finally:
        os.chdir(original_cwd)
