import pathlib
import subprocess

LIBRARY_ROOT = pathlib.Path(__file__).parent.parent.resolve()


def run_tests(_, remaining):
    command = " ".join(
        ["pytest"] + remaining + ["--pyargs", "pymedphys", "--failed-first"]
    )

    subprocess.check_call(command, shell=True)
