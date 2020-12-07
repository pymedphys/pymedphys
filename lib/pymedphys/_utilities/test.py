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

import functools
import pathlib
import subprocess
import sys
from contextlib import contextmanager

from pymedphys._imports import numpy as np
from pymedphys._imports import psutil


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


def test_exe(path):
    subprocess.check_call([path, "-c", "import os"])


@functools.lru_cache()
def get_executable_even_when_embedded():
    """Get the Python executable path.

    In some environments, for example a pyinstaller bundle, the Python
    executable is not able to be found via ``sys.executable``. When
    calling the CLI within tests it needs to be ensured that the same
    Python that is running the tests, is the same Python that the CLI
    command is being called with.

    Returns
    -------
    exe : str
        The full path to the Python executable.

    Raises
    ------
    ValueError
        If each attempt at finding the Python interpreter fails.

    """
    exe = str(sys.executable)
    if pathlib.Path(exe).name.startswith("python"):
        try:
            test_exe(exe)
            return exe
        except FileNotFoundError:
            pass

    exe = str(pathlib.Path(np.__file__).parents[4].joinpath("bin", "python"))

    try:
        test_exe(exe)
        return exe
    except FileNotFoundError:
        pass

    exe = str(pathlib.Path(np.__file__).parents[3].joinpath("python"))

    try:
        test_exe(exe)
    except FileNotFoundError as e:
        raise ValueError(
            "Tried to determine the python interpreter path, but was unsuccessful."
        ) from e

    return exe


def get_pymedphys_dicom_cli():
    python_executable = get_executable_even_when_embedded()
    return [str(python_executable), "-m", "pymedphys", "dicom"]
