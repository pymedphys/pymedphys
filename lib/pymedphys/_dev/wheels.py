import pathlib
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
REQUIREMENTS_USER = REPO_ROOT.joinpath("requirements-user.txt")
WHEELS = REPO_ROOT.joinpath("wheels")


def wheels(_):
    subprocess.check_call(
        f"poetry run pip wheel -r {REQUIREMENTS_USER} -w {WHEELS}",
        shell=True,
        cwd=REPO_ROOT,
    )

    subprocess.check_call("poetry build -f wheel", shell=True, cwd=REPO_ROOT)
