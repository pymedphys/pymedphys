import os
import pathlib
import subprocess

LIBRARY_ROOT = pathlib.Path(__file__).parent.parent.resolve()
PYLINT_RC_FILE = LIBRARY_ROOT.joinpath(".pylintrc")


def run_tests(_, remaining):
    original_cwd = os.getcwd()

    if "--pylint" in remaining:
        remaining.append(["--pylint-rcfile", str(PYLINT_RC_FILE)])
        working_directory_to_use = LIBRARY_ROOT.parent
    else:
        working_directory_to_use = LIBRARY_ROOT

    os.chdir(working_directory_to_use)
    print(f"Running tests with cwd set to {os.getcwd()}")

    try:
        command = " ".join(
            ["pytest"] + remaining + ["--pyargs", "pymedphys", "--failed-first"]
        )

        print(command)

        subprocess.check_call(command, shell=True)
    finally:
        os.chdir(original_cwd)
