# Copyright (C) 2019 Simon Biggs
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os
import pathlib
import platform
import shutil
import subprocess
import tempfile
import zipfile

import pymedphys

HERE: pathlib.Path = pathlib.Path(__file__).parent.resolve()

# https://stackoverflow.com/a/39110
def file_contents_replace(file_path, pattern, subst):
    fh, abs_path = tempfile.mkstemp()
    with open(fh, "w") as new_file:
        with open(file_path) as old_file:
            for line in old_file:
                new_file.write(line.replace(pattern, subst))
    os.remove(file_path)
    shutil.move(abs_path, file_path)


def get_embedded_python_executable(embedded_python_exe):
    if platform.system() == "Windows":
        return [embedded_python_exe]

    return ["wine", embedded_python_exe]


def call_embedded_python(embedded_python_dir, *args):
    embedded_python_exe = embedded_python_dir.joinpath("python.exe")
    to_be_called = [
        str(item)
        for item in get_embedded_python_executable(embedded_python_exe) + list(args)
    ]
    print(to_be_called)
    subprocess.check_call(to_be_called, cwd=embedded_python_dir)


def main(_):

    cwd = pathlib.Path(os.getcwd())
    build = cwd.joinpath("build")
    try:
        shutil.rmtree(build)
    except FileNotFoundError as _:
        pass

    final_path = cwd.joinpath("LibreApp Setup.exe")
    try:
        final_path.unlink()
    except FileNotFoundError as _:
        pass

    embedded_python_dir = build.joinpath("python")
    app_path = cwd.joinpath("app.py")
    requirements_path = cwd.joinpath("requirements.txt")

    if not app_path.exists():
        raise ValueError(
            "Need to have a streamlit file called `app.py` in this directory."
        )

    if not requirements_path.exists():
        raise ValueError(
            "Need to have a requirements.txt file in this directory. "
            "If you truly don't have any dependencies except streamlit "
            "you may create an empty requirements.txt file to continue."
        )

    embedded_python_path = pymedphys.data_path("python-windows-64-embedded.zip")

    with zipfile.ZipFile(embedded_python_path, "r") as zip_obj:
        zip_obj.extractall(embedded_python_dir)

    get_pip_path = pymedphys.data_path("get-pip.py")
    call_embedded_python(embedded_python_dir, get_pip_path)

    python_path_file = next(embedded_python_dir.glob("python*._pth"))

    temp_python_path_file = f"{python_path_file}.temp"
    file_contents_replace(python_path_file, "#import site", "import site")

    call_embedded_python(embedded_python_dir, "-m", "pip", "--version")

    os.rename(python_path_file, temp_python_path_file)
    call_embedded_python(
        embedded_python_dir,
        "-m",
        "pip",
        "install",
        "streamlit==0.57.3",
        "matplotlib",  # Needed since this is an undeclared dependency of streamlit
        "--no-warn-script-location",
    )
    call_embedded_python(
        embedded_python_dir,
        "-m",
        "pip",
        "install",
        "-r",
        requirements_path,
        "--no-warn-script-location",
    )
    os.rename(temp_python_path_file, python_path_file)

    build_files_to_copy = ["package.json", "yarn.lock", "run.py"]
    build_dirs_to_copy = ["src"]

    for file_to_copy in build_files_to_copy:
        try:
            shutil.copy2(HERE.joinpath(file_to_copy), build.joinpath(file_to_copy))
        except FileExistsError:
            pass

    for dirs_to_copy in build_dirs_to_copy:
        try:
            shutil.copytree(HERE.joinpath(dirs_to_copy), build.joinpath(dirs_to_copy))
        except FileExistsError:
            pass

    build_app_path = build.joinpath("app.py")

    try:
        build_app_path.unlink()
    except FileNotFoundError as _:
        pass

    shutil.copy2(app_path, build_app_path)

    os.chdir(str(build))
    os.system("yarn")
    os.system("yarn dist")
    os.chdir(str(cwd))

    produced_exe = build.joinpath("release", "LibreApp Setup 0.1.0.exe")

    shutil.copy2(produced_exe, final_path)
