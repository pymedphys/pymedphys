import os
import pathlib
import subprocess

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent.parent.resolve()


def run_tests(_, remaining):
    original_cwd = os.getcwd()
    os.chdir(REPO_ROOT)
    print(f"Running tests with cwd set to {os.getcwd()}")

    try:
        command = " ".join(
            ["pytest"] + remaining + ["--pyargs", "pymedphys", "--failed-first"]
        )

        subprocess.check_call(command, shell=True)
    finally:
        os.chdir(original_cwd)
