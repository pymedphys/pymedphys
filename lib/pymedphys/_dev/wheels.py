import pathlib
import shutil
import subprocess

from . import propagate

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
REQUIREMENTS_USER = REPO_ROOT.joinpath("requirements-user.txt")
WHEELS = REPO_ROOT.joinpath("wheels")
DIST = REPO_ROOT.joinpath("dist")


def wheels(_):
    propagate.propagate_all(None)

    subprocess.check_call(
        f"poetry run pip wheel -r {REQUIREMENTS_USER} -w {WHEELS}",
        shell=True,
        cwd=REPO_ROOT,
    )

    subprocess.check_call("poetry build -f wheel", shell=True, cwd=REPO_ROOT)

    version_string = propagate.get_version_string().replace("-", ".")
    pymedphys_wheel = f"pymedphys-{version_string}-py3-none-any.whl"

    shutil.copy(DIST.joinpath(pymedphys_wheel), WHEELS.joinpath(pymedphys_wheel))
