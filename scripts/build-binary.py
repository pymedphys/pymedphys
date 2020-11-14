import pathlib
import subprocess
import shutil
import sys
import tomlkit
import urllib.request
import zipfile

HERE = pathlib.Path("__file__").parent.resolve()
REPO_ROOT = HERE.parent
PYPROJECT_TOML_PATH = REPO_ROOT.joinpath("pyproject.toml")
DIST = REPO_ROOT.joinpath("dist")
WHEELS = REPO_ROOT.joinpath("wheels")

DOWNLOADS = REPO_ROOT.joinpath("downloads")
PYTHON_EMBED_URL = (
    "https://www.python.org/ftp/python/3.8.6/python-3.8.6-embed-amd64.zip"
)
PYTHON_EMBED_PATH = DOWNLOADS.joinpath("python-embed.zip")
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
GET_PIP_PATH = DOWNLOADS.joinpath("get-pip.py")

BUILD = REPO_ROOT.joinpath("build")
BUILD_PYTHON_EMBED = BUILD.joinpath("python-embed")


def read_pyproject():
    with open(PYPROJECT_TOML_PATH) as f:
        pyproject_contents = tomlkit.loads(f.read())

    return pyproject_contents


def get_version_string():
    pyproject_contents = read_pyproject()
    version_string = pyproject_contents["tool"]["poetry"]["version"]

    return version_string


def main():
    if sys.platform == "win32":
        prepend = ""
    else:
        prepend = "wine "

    # subprocess.check_call(
    #     f"{prepend}pip wheel -r requirements-deploy.txt -w wheels",
    #     shell=True,
    #     cwd=REPO_ROOT,
    # )
    # subprocess.check_call("poetry build -f wheel", shell=True, cwd=REPO_ROOT)

    # version_string = get_version_string().replace("-", ".")
    # pymedphys_wheel = f"pymedphys-{version_string}-py3-none-any.whl"

    # shutil.copy(DIST.joinpath(pymedphys_wheel), WHEELS.joinpath(pymedphys_wheel))

    # DOWNLOADS.mkdir(exist_ok=True)
    # if not PYTHON_EMBED_PATH.exists():
    #     urllib.request.urlretrieve(PYTHON_EMBED_URL, PYTHON_EMBED_PATH)

    # if not GET_PIP_PATH.exists():
    #     urllib.request.urlretrieve(GET_PIP_URL, GET_PIP_PATH)

    # BUILD_PYTHON_EMBED.mkdir(exist_ok=True, parents=True)
    # with zipfile.ZipFile(PYTHON_EMBED_PATH, "r") as zip_ref:
    #     zip_ref.extractall(BUILD_PYTHON_EMBED)

    path_file = list(BUILD_PYTHON_EMBED.glob("*._pth"))
    if len(path_file) != 1:
        raise ValueError("Only one _pth file should exist.")

    path_file = path_file[0]

    with open(path_file) as f:
        path_file_contents = f.read()

    path_file_contents = path_file_contents.replace("#import site", "import site")

    with open(path_file, "w") as f:
        f.write(path_file_contents)

    subprocess.check_call(
        f"{prepend}python.exe {GET_PIP_PATH}", shell=True, cwd=BUILD_PYTHON_EMBED
    )

    subprocess.check_call(
        f"{prepend}python.exe -m pip install pymedphys[user] --no-index --find-links file://{WHEELS}",
        shell=True,
        cwd=BUILD_PYTHON_EMBED,
    )


if __name__ == "__main__":
    main()
