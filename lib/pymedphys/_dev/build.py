# Copyright (C) 2022 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import shutil
import subprocess

from .paths import REPO_ROOT

PYOXIDIZER_BUILD = REPO_ROOT.joinpath("build")
PYOXIDIZER_DIST = PYOXIDIZER_BUILD.joinpath("dist")

ELECTRON_APP_DIR = REPO_ROOT.joinpath("js", "app")
PYTHON_APP_DESTINATION = ELECTRON_APP_DIR.joinpath("python")


def build_binary(args):
    # shutil.which is needed for yarn to work on Windows
    # https://stackoverflow.com/a/32799942/3912576
    if args.install:
        subprocess.check_call([shutil.which("yarn"), "install"], cwd=ELECTRON_APP_DIR)

    # TODO: Propagate versions into bazel and package.json files

    try:
        shutil.rmtree(PYOXIDIZER_BUILD)
    except FileNotFoundError:
        pass

    try:
        shutil.rmtree(PYTHON_APP_DESTINATION)
    except FileNotFoundError:
        pass

    subprocess.check_call(
        ["poetry", "run", "pyoxidizer", "build", "install"], cwd=REPO_ROOT
    )
    shutil.move(PYOXIDIZER_DIST, PYTHON_APP_DESTINATION)

    subprocess.check_call([shutil.which("yarn"), "build"], cwd=ELECTRON_APP_DIR)
