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
EMBEDDED_PYTHON_DIR = HERE.joinpath("python")
EMBEDDED_PYTHON_EXE = EMBEDDED_PYTHON_DIR.joinpath("python.exe")

PYMEDPHYS_GIT = HERE.parent
PYMEDPHYS_DIST = PYMEDPHYS_GIT.joinpath("dist")
PYMEDPHYS_REQUIREMENTS = PYMEDPHYS_GIT.joinpath("requirements.txt")

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
    to_be_called = [str(item) for item in get_embedded_python_executable() + list(args)]
    print(to_be_called)
    subprocess.check_call(to_be_called, cwd=EMBEDDED_PYTHON_DIR)


def main():
    shutil.rmtree(EMBEDDED_PYTHON_DIR, ignore_errors=True)

    embedded_python_path = pymedphys.data_path("python-windows-64-embedded.zip")

    with zipfile.ZipFile(embedded_python_path, "r") as zip_obj:
        zip_obj.extractall(EMBEDDED_PYTHON_DIR)

    get_pip_path = pymedphys.data_path("get-pip.py")
    call_embedded_python(get_pip_path)

    python_path_file = next(EMBEDDED_PYTHON_DIR.glob("python*._pth"))
    temp_python_path_file = f"{python_path_file}.temp"

    file_contents_replace(python_path_file, "#import site", "import site")

    call_embedded_python("-m", "pip", "--version")

    # shutil.rmtree(PYMEDPHYS_DIST, ignore_errors=True)

    # Waiting for https://github.com/sdispater/poetry/issues/875 to be fixed before
    # using the following:
    # with open(PYMEDPHYS_REQUIREMENTS, "w") as req_txt:
    #     subprocess.call(
    #         ["poetry", "export", "-f", "requirements.txt"],
    #         cwd=PYMEDPHYS_GIT,
    #         stdout=req_txt,
    #     )

    os.rename(python_path_file, temp_python_path_file)

    # call_embedded_python("-m", "pip", "install", "-r", PYMEDPHYS_REQUIREMENTS)

    # subprocess.check_call(["poetry", "build"], cwd=PYMEDPHYS_GIT)

    package_with_extras = f"{next(PYMEDPHYS_DIST.glob('*.whl'))}[gui]"

    call_embedded_python(
        "-m", "pip", "install", package_with_extras, "--no-warn-script-location"
    )

    os.rename(temp_python_path_file, python_path_file)

    # subprocess.check_call(["yarn", "dist"], cwd=HERE)


if __name__ == "__main__":
    main()
