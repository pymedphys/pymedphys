import functools
import os
import pathlib
import platform
import shutil
import subprocess
import tempfile
import zipfile

import pymedphys

HERE: pathlib.Path = pathlib.Path(__file__).parent.resolve()
BUILD = HERE.joinpath("build")
EMBEDDED_PYTHON_DIR = BUILD.joinpath("python")
EMBEDDED_PYTHON_EXE = EMBEDDED_PYTHON_DIR.joinpath("python.exe")
EMBEDDED_SCRIPTS = EMBEDDED_PYTHON_DIR.joinpath("Scripts")
EMBEDDED_PIP_EXE = EMBEDDED_SCRIPTS.joinpath("pip.exe")

PYMEDPHYS_GIT = HERE.parent
PYMEDPHYS_DIST = PYMEDPHYS_GIT.joinpath("dist")

# https://stackoverflow.com/a/39110
def file_contents_replace(file_path, pattern, subst):
    fh, abs_path = tempfile.mkstemp()
    with open(fh, "w") as new_file:
        with open(file_path) as old_file:
            for line in old_file:
                new_file.write(line.replace(pattern, subst))
    os.remove(file_path)
    shutil.move(abs_path, file_path)


@functools.lru_cache(maxsize=1)
def get_embedded_python_executable():
    if platform.system() == "Windows":
        return [EMBEDDED_PYTHON_EXE]

    return ["wine", EMBEDDED_PYTHON_EXE]


def call_embedded_python(*args):
    to_be_called = get_embedded_python_executable() + list(args)
    print(to_be_called)
    subprocess.call(to_be_called, cwd=EMBEDDED_PYTHON_DIR)


def main():
    BUILD.mkdir(exist_ok=True)

    embedded_python_path = pymedphys.data_path("python-windows-64-embedded.zip")

    with zipfile.ZipFile(embedded_python_path, "r") as zip_obj:
        zip_obj.extractall(EMBEDDED_PYTHON_DIR)

    get_pip_path = pymedphys.data_path("get-pip.py")
    call_embedded_python(get_pip_path)

    file_contents_replace(
        next(EMBEDDED_PYTHON_DIR.glob("python*._pth")), "#import site", "import site"
    )

    shutil.rmtree(PYMEDPHYS_DIST)

    subprocess.call(["poetry", "build"], cwd=PYMEDPHYS_GIT)
    next(PYMEDPHYS_DIST.glob("*.whl"))
    call_embedded_python("-m", "pip", "install", next(PYMEDPHYS_DIST.glob("*.whl")))


if __name__ == "__main__":
    main()
