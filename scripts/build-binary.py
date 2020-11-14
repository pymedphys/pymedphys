import pathlib
import subprocess
import shutil
import tomlkit

HERE = pathlib.Path("__file__").parent.resolve()
REPO_ROOT = HERE.parent
PYPROJECT_TOML_PATH = REPO_ROOT.joinpath("pyproject.toml")
DIST = REPO_ROOT.joinpath("dist")
WHEELS = REPO_ROOT.joinpath("wheels")


def read_pyproject():
    with open(PYPROJECT_TOML_PATH) as f:
        pyproject_contents = tomlkit.loads(f.read())

    return pyproject_contents


def get_version_string():
    pyproject_contents = read_pyproject()
    version_string = pyproject_contents["tool"]["poetry"]["version"]

    return version_string


def main():
    subprocess.check_call(
        "pip wheel -r requirements-deploy.txt -w wheels", shell=True, cwd=REPO_ROOT
    )
    subprocess.check_call("poetry build -f wheel", shell=True, cwd=REPO_ROOT)

    version_string = get_version_string().replace("-", ".")
    pymedphys_wheel = f"pymedphys-{version_string}-py3-none-any.whl"

    shutil.copy(DIST.joinpath(pymedphys_wheel), WHEELS.joinpath(pymedphys_wheel))


if __name__ == "__main__":
    main()
