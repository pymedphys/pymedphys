import pathlib
import subprocess

LIBRARY_ROOT = pathlib.Path(__file__).parent.parent.resolve()


def run_tests(_, remaining):
    print(remaining)

    command = " ".join(["pytest"] + remaining + ["--pyargs", "pymedphys"])

    print(command)

    subprocess.check_call(command, shell=True)
