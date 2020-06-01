import subprocess


def run_tests(_, remaining):
    command = " ".join(["pytest"] + remaining + ["--pyargs", "pymedphys"])
    print(command)

    subprocess.check_call(command, shell=True)
