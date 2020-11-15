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

LIBRARY_ROOT = pathlib.Path(__file__).parent.parent.resolve()
PYLINT_RC_FILE = LIBRARY_ROOT.joinpath(".pylintrc")


def run_tests(_, remaining):
    original_cwd = os.getcwd()

    if "--pylint" in remaining:
        remaining.append(f"--pylint-rcfile={str(PYLINT_RC_FILE)}")

        if LIBRARY_ROOT.parent.name == "lib":
            working_directory_to_use = LIBRARY_ROOT.parent.parent
        else:
            working_directory_to_use = LIBRARY_ROOT.parent
    else:
        working_directory_to_use = LIBRARY_ROOT

    os.chdir(working_directory_to_use)
    print(f"Running tests with cwd set to:\n    {os.getcwd()}\n")

    python_executable = pmp_test_utils.get_executable_even_when_embedded()

    try:
        # By prepending the python executable like this, instead of
        # searching the user's path for pytest it will explicitly use
        # the pytest that is installed within the Python distribution
        # that called ``pymedphys dev tests``.

        # This supports a range of cases, such as poetry virtual
        # environments, and embedded python installs.
        command = (
            [python_executable, "-m", "pytest"]
            + remaining
            + ["--pyargs", "pymedphys", "--failed-first"]
        )

        print(f"Running the following command:\n    {' '.join(command)}\n")

        subprocess.check_call(command)
    finally:
        os.chdir(original_cwd)
