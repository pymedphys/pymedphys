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
import functools

import tomlkit

HERE = pathlib.Path("__file__").parent.resolve()
REPO_ROOT = HERE.parent
PYPROJECT_TOML_PATH = REPO_ROOT.joinpath("pyproject.toml")
LICENSE_PATH = REPO_ROOT.joinpath("LICENSE")

DIST = REPO_ROOT.joinpath("dist")

BUILD = HERE.joinpath("build")
WHEELS = BUILD.joinpath("wheels")

DOWNLOADS = BUILD.joinpath("downloads")
PYTHON_EMBED_URL = (
    "https://www.python.org/ftp/python/3.7.9/python-3.7.9-embed-amd64.zip"
)
PYTHON_EMBED_PATH = DOWNLOADS.joinpath("python-embed.zip")
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
GET_PIP_PATH = DOWNLOADS.joinpath("get-pip.py")

BUILD_PYTHON_EMBED = BUILD.joinpath("python-embed")
BUILD_PYTHON_EMBED_XZTAR = BUILD_PYTHON_EMBED.with_suffix(".tar.xz")

BUILD_DIST = BUILD.joinpath("dist")


def main():
    """Builds ``PyMedPhysGUI-vX.Y.Z.exe`` that when run extracts an
    embedded Python distro, spins up the PyMedPhys GUI, and lastly
    exposes the CLI via a ``pymedphys.bat``.

    Note
    ----
    Under the hood this does use pyinstaller to create the exe. However
    the pyinstaller section of the resulting code just ends up being an
    "installer script". PyMedPhys is not installed or utilised within
    the pyinstaller script itself. Instead, PyMedPhys is installed
    within the embedded Python distribution which is bundled as a
    compressed file within the executable. See
    ``pyinstaller-bundle-script.py`` for more details on what occurs
    when the executable is run.

    """
    prepend, append, one_file_mode = _linux_and_windows_support()

    _build_and_collate_wheels(prepend)
    _download_and_extract_embedded_python()
    _get_pip(prepend)
    _install_pymedphys_in_offline_mode(prepend)
    _create_compressed_python_embed()

    _run_pyinstaller_to_build_the_exe(prepend, append, one_file_mode)


def _linux_and_windows_support():
    """Shimming to allow for building the exe on Linux with wine as well as on Windows.

    If the OS isn't Windows all python calls a prepended with ``wine``.
    Also, if it is being built for testing on Linux --onefile mode is not used due
    to the following issue:

    <https://github.com/pyinstaller/pyinstaller/issues/4628#issuecomment-632025449>
    """
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

    return prepend, append, one_file_mode


def _build_and_collate_wheels(prepend):
    """Utilises the dependencies within requirements-deploy to build
    a directory full of wheels.

    This is undergone due to issues with the embedded Python not being
    able to build wheels by itself.

    Note
    ----
    Of importance, this means that the version of the Python within the
    embedded environment needs to match the version of Python used here
    to build the wheels.

    """

    subprocess.check_call(
        f"{prepend}pip wheel -r requirements-deploy.txt -w {WHEELS}",
        shell=True,
        cwd=REPO_ROOT,
    )

    # Recent dev commits remove pylinac gui, delete production pylinac
    # wheel and test with a recent development commit.
    WHEELS.joinpath("pylinac-2.3.2-py3-none-any.whl").unlink()
    subprocess.check_call(
        f"{prepend}python -m pip wheel git+https://github.com/jrkerns/pylinac.git@446d4cf7fd1999ac1c418765db329f394515d5c0",
        shell=True,
        cwd=WHEELS,
    )

    subprocess.check_call("poetry build -f wheel", shell=True, cwd=REPO_ROOT)

    pymedphys_wheel = f"pymedphys-{_get_version_string()}-py3-none-any.whl"

    shutil.copy(DIST.joinpath(pymedphys_wheel), WHEELS.joinpath(pymedphys_wheel))


def _download_and_extract_embedded_python():
    """Creates a Python embedded directory adjusted for pip compatibility.

    Note
    ----
    After the embedded python is extracted the ``import site`` line
    needs to be uncommented so that pip (and for that matter pymedphys)
    is able to be called via ``python -m pip``.

    """
    DOWNLOADS.mkdir(exist_ok=True)
    if not PYTHON_EMBED_PATH.exists():
        urllib.request.urlretrieve(PYTHON_EMBED_URL, PYTHON_EMBED_PATH)

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


def _get_pip(prepend):
    """Install pip within the embedded Python distribution.

    Note
    ----
    Python embedded doesn't come with pip.

    """
    if not GET_PIP_PATH.exists():
        urllib.request.urlretrieve(GET_PIP_URL, GET_PIP_PATH)

    subprocess.check_call(
        f"{prepend}python.exe {GET_PIP_PATH}", shell=True, cwd=BUILD_PYTHON_EMBED
    )


def _install_pymedphys_in_offline_mode(prepend):
    """Utilising the wheels downloaded prior, install PyMedPhys.

    Note
    ----
    This is method is undergone since the embedded Python install has
    no issues installing wheel files, but it would often struggle with
    various packages when trying to install from their source tarballs.

    """
    subprocess.check_call(
        f"{prepend}python.exe -m pip install pymedphys[user,tests] --no-index --find-links file://{WHEELS}",
        shell=True,
        cwd=BUILD_PYTHON_EMBED,
    )


def _create_compressed_python_embed():
    """Compress the created embedded python distribution to a tar.xz file.

    Note
    ----
    Here the "xztar" option is chosen so as to utilise LZMA compression.
    This takes longer to build but is ~1/2 the size of the corresponding
    ``.zip`` file.

    """
    shutil.make_archive(BUILD_PYTHON_EMBED, "xztar", BUILD_PYTHON_EMBED)


def _run_pyinstaller_to_build_the_exe(prepend, append, one_file_mode):
    pyinstaller_script = pathlib.Path("pyinstaller-bundle-script.py")
    pymedphys_bat = "pymedphys.bat"

    for f in [pyinstaller_script, pymedphys_bat]:
        shutil.copy(HERE.joinpath(f), BUILD.joinpath(f))

    subprocess.check_call(
        (
            f"{prepend}pyinstaller {pyinstaller_script}"
            f' --add-data "{LICENSE_PATH};data"'
            f' --add-data "{BUILD_PYTHON_EMBED_XZTAR.name};data"'
            f' --add-data "{pymedphys_bat};data"{append}'
        ),
        shell=True,
        cwd=BUILD,
    )

    if one_file_mode:
        shutil.move(
            BUILD_DIST.joinpath(pyinstaller_script.with_suffix(".exe")),
            BUILD_DIST.joinpath(f"PyMedPhysGUI-v{_get_version_string()}.exe"),
        )


def _read_pyproject():
    with open(PYPROJECT_TOML_PATH) as f:
        pyproject_contents = tomlkit.loads(f.read())

    return pyproject_contents


@functools.lru_cache()
def _get_version_string():
    """Get the PyMedPhys version string.

    Note
    ----
    Replacing the - with a . here so as to be consistent with Python
    wheel naming.

    """
    pyproject_contents = _read_pyproject()
    version_string = pyproject_contents["tool"]["poetry"]["version"]

    return version_string.replace("-", ".")


if __name__ == "__main__":
    main()
