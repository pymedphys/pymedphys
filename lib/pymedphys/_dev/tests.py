import os
import pathlib
import subprocess

LIBRARY_ROOT = pathlib.Path(__file__).parent.parent.resolve()
PYLINT_RC_FILE = LIBRARY_ROOT.joinpath(".pylintrc")


def run_tests(_, remaining):
    original_cwd = os.getcwd()

    if "--pylint" in remaining:
        remaining.append(f"--pylint-rcfile={str(PYLINT_RC_FILE)}")

        if LIBRARY_ROOT.parent.name == "lib":
            working_directory_to_use = LIBRARY_ROOT.parent.parent
        else:
            working_directory_to_use = LIBRARY_ROOT.parent
    else:
        working_directory_to_use = LIBRARY_ROOT

    os.chdir(working_directory_to_use)
    print(f"Running tests with cwd set to:\n    {os.getcwd()}\n")

    try:
        command = " ".join(
            ["pytest"] + remaining + ["--pyargs", "pymedphys", "--failed-first"]
        )

        print(f"Running the following command:\n    {command}\n")

        subprocess.check_call(command, shell=True)
    finally:
        os.chdir(original_cwd)
