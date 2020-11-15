# Copyright (C) 2020 Cancer Care Associates

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

import pytest

import pymedphys
import pymedphys._utilities.test as pmp_test_utils

HERE = pathlib.Path(__file__).parent.resolve()


@pytest.mark.cypress
def test_cypress():
    pymedphys.zip_data_paths("metersetmap-gui-e2e-data.zip", extract_directory=HERE)

    pymedphys.zip_data_paths(
        "dummy-ct-and-struct.zip",
        extract_directory=HERE.joinpath("cypress", "fixtures"),
    )

    command = [
        pmp_test_utils.get_executable_even_when_embedded(),
        "-m",
        "pymedphys",
        "gui",
    ]

    with pmp_test_utils.process(command, cwd=HERE):
        subprocess.check_call("yarn", cwd=HERE, shell=True)

        subprocess.check_call("yarn cypress run", cwd=HERE, shell=True)
