# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pathlib
import subprocess
import shutil
import sys
import urllib.request
import zipfile

import tomlkit

HERE = pathlib.Path("__file__").parent.resolve()
REPO_ROOT = HERE.parent
PYPROJECT_TOML_PATH = REPO_ROOT.joinpath("pyproject.toml")

DIST = REPO_ROOT.joinpath("dist")
WHEELS = REPO_ROOT.joinpath("wheels")

DOWNLOADS = REPO_ROOT.joinpath("downloads")
PYTHON_EMBED_URL = (
    "https://www.python.org/ftp/python/3.7.9/python-3.7.9-embed-amd64.zip"
)
PYTHON_EMBED_PATH = DOWNLOADS.joinpath("python-embed.zip")
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
GET_PIP_PATH = DOWNLOADS.joinpath("get-pip.py")

BUILD = REPO_ROOT.joinpath("build")
BUILD_PYTHON_EMBED = BUILD.joinpath("python-embed")
BUILD_PYTHON_EMBED_XZTAR = BUILD_PYTHON_EMBED.with_suffix(".tar.xz")

BUILD_DIST = BUILD.joinpath("dist")


def main():
    if sys.platform == "win32":
        prepend = ""
        one_file_mode = True
    else:
        prepend = "wine "
        one_file_mode = False

    if one_file_mode:
        append = " --onefile"
    else:
        append = ""

    subprocess.check_call(
        f"{prepend}pip wheel -r requirements-deploy.txt -w wheels",
        shell=True,
        cwd=REPO_ROOT,
    )
    subprocess.check_call("poetry build -f wheel", shell=True, cwd=REPO_ROOT)

    version_string = _get_version_string().replace("-", ".")
    pymedphys_wheel = f"pymedphys-{version_string}-py3-none-any.whl"

    shutil.copy(DIST.joinpath(pymedphys_wheel), WHEELS.joinpath(pymedphys_wheel))

    DOWNLOADS.mkdir(exist_ok=True)
    if not PYTHON_EMBED_PATH.exists():
        urllib.request.urlretrieve(PYTHON_EMBED_URL, PYTHON_EMBED_PATH)

    if not GET_PIP_PATH.exists():
        urllib.request.urlretrieve(GET_PIP_URL, GET_PIP_PATH)

    BUILD_PYTHON_EMBED.mkdir(exist_ok=True, parents=True)
    with zipfile.ZipFile(PYTHON_EMBED_PATH, "r") as zip_ref:
        zip_ref.extractall(BUILD_PYTHON_EMBED)

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
        f"{prepend}python.exe -m pip install pymedphys[user,test] --no-index --find-links file://{WHEELS}",
        shell=True,
        cwd=BUILD_PYTHON_EMBED,
    )

    shutil.make_archive(BUILD_PYTHON_EMBED, "xztar", BUILD_PYTHON_EMBED)

    subprocess.check_call(
        f"{prepend}pip install pyinstaller", shell=True, cwd=REPO_ROOT
    )

    pyinstaller_script = pathlib.Path("pyinstaller-bundle-script.py")
    pymedphys_bat = "pymedphys.bat"

    for f in [pyinstaller_script, pymedphys_bat]:
        shutil.copy(HERE.joinpath(f), BUILD.joinpath(f))

    subprocess.check_call(
        (
            f"{prepend}pyinstaller {pyinstaller_script}"
            f' --add-data "{BUILD_PYTHON_EMBED_XZTAR.name};data"'
            f' --add-data "{pymedphys_bat};data"{append}'
        ),
        shell=True,
        cwd=BUILD,
    )

    if one_file_mode:
        shutil.move(
            BUILD_DIST.joinpath(pyinstaller_script.with_suffix(".exe")),
            BUILD_DIST.joinpath(f"PyMedPhysGUI-v{version_string}.exe"),
        )


def _read_pyproject():
    with open(PYPROJECT_TOML_PATH) as f:
        pyproject_contents = tomlkit.loads(f.read())

    return pyproject_contents


def _get_version_string():
    pyproject_contents = _read_pyproject()
    version_string = pyproject_contents["tool"]["poetry"]["version"]

    return version_string


if __name__ == "__main__":
    main()
