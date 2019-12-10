import functools
import pathlib
import platform
import subprocess
import zipfile

import pymedphys

HERE: pathlib.Path = pathlib.Path(__file__).parent.resolve()
BUILD = HERE.joinpath("build")
EMBEDDED_PYTHON_DIR = BUILD.joinpath("python")
EMBEDDED_PYTHON_EXE = EMBEDDED_PYTHON_DIR.joinpath("python.exe")


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


if __name__ == "__main__":
    main()
