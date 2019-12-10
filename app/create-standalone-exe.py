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
EMBEDDED_SITE_PACKAGES = EMBEDDED_PYTHON_DIR.joinpath("lib").joinpath("site-packages")

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
    to_be_called = get_embedded_python_executable() + list(args)
    print(to_be_called)
    subprocess.check_call(to_be_called, cwd=EMBEDDED_PYTHON_DIR)


def main():
    embedded_python_path = pymedphys.data_path("python-windows-64-embedded.zip")

    with zipfile.ZipFile(embedded_python_path, "r") as zip_obj:
        zip_obj.extractall(EMBEDDED_PYTHON_DIR)

    shutil.rmtree(PYMEDPHYS_DIST)

    # Waiting for https://github.com/sdispater/poetry/issues/875 to be fixed before
    # using the following:
    # with open(PYMEDPHYS_REQUIREMENTS, "w") as req_txt:
    #     subprocess.call(
    #         ["poetry", "export", "-f", "requirements.txt"],
    #         cwd=PYMEDPHYS_GIT,
    #         stdout=req_txt,
    #     )

    subprocess.call(["poetry", "build"], cwd=PYMEDPHYS_GIT)

    package_with_extras = f"{next(PYMEDPHYS_DIST.glob('*.whl'))}"
    subprocess.call(
        [
            "python",
            "-m",
            "pip",
            "install",
            "--platform",
            "win_amd64",
            "--only-binary=:all:",
            "--target",
            EMBEDDED_SITE_PACKAGES,
            package_with_extras,
        ]
    )


if __name__ == "__main__":
    main()
