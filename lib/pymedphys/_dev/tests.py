# Copyright (C) 2021 Cancer Care Associates, Simon Biggs
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

import os
import pathlib
import subprocess

import pymedphys._utilities.test as pmp_test_utils
import pymedphys.tests.e2e.utilities as cypress_test_utilities

LIBRARY_ROOT = pathlib.Path(__file__).parent.parent.resolve()
PYLINT_RC_FILE = LIBRARY_ROOT.joinpath(".pylintrc")


def run_tests(_, remaining):
    _call_pytest(remaining, "pytest")


def run_doctests(_, remaining):
    remaining = ["--doctest-modules"] + remaining
    _call_pytest(remaining, "doctests")


def _call_pytest(remaining, label):
    original_cwd = os.getcwd()

    os.chdir(LIBRARY_ROOT)
    print(f"Running {label} with cwd set to:\n    {os.getcwd()}\n")

    python_executable = pmp_test_utils.get_executable_even_when_embedded()
    command = [
        python_executable,
        "-m",
        "pytest",
        "--pyargs",
        "pymedphys",
    ] + remaining

    try:
        subprocess.check_call(command)
    finally:
        os.chdir(original_cwd)


def run_pylint(_, remaining):
    original_cwd = os.getcwd()

    if LIBRARY_ROOT.parent.name == "lib":
        working_directory_to_use = LIBRARY_ROOT.parent.parent
    else:
        working_directory_to_use = LIBRARY_ROOT.parent

    os.chdir(working_directory_to_use)
    print(f"Linting with cwd set to:\n    {os.getcwd()}\n")

    python_executable = pmp_test_utils.get_executable_even_when_embedded()
    command = [
        python_executable,
        "-m",
        "pylint",
        "pymedphys",
        f"--rcfile={str(PYLINT_RC_FILE)}",
    ] + remaining

    try:
        subprocess.check_call(command)
    finally:
        os.chdir(original_cwd)


def run_cypress(_):
    cypress_test_utilities.run_test_commands_with_gui_process(["yarn cypress open"])
