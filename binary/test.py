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
import sys

from contextlib import contextmanager

import psutil


HERE = pathlib.Path("__file__").parent.resolve()
REPO_ROOT = HERE.parent
BUILD = REPO_ROOT.joinpath("build")
BUILD_DIST = BUILD.joinpath("dist")

CYPRESS = REPO_ROOT.joinpath("lib", "pymedphys", "tests", "e2e")


@contextmanager
def process(*args, **kwargs):
    """Provides a process running with the provided arguments, useful for CLI unit tests

    Yields
    -------
    subprocess.Popen
        The process being run
    """
    proc = subprocess.Popen(*args, **kwargs)
    try:
        yield proc
    finally:
        for child in psutil.Process(proc.pid).children(recursive=True):
            child.kill()
        proc.kill()


def main():
    if sys.platform == "win32":
        prepend = ""
    else:
        prepend = "wine "

    built_executables = list(BUILD_DIST.glob("*.exe"))
    if len(built_executables) != 1:
        raise ValueError("There should be only one executable.")

    exe = built_executables[0]

    with process(f"{prepend}{exe}", cwd=BUILD_DIST, shell=True):
        subprocess.check_call("yarn", cwd=CYPRESS, shell=True)
        subprocess.check_call("yarn cypress run", cwd=CYPRESS, shell=True)


if __name__ == "__main__":
    main()
