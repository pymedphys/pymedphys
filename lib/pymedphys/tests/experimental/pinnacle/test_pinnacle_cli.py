# Copyright (C) 2020 South Western Sydney Local Health District,
# University of New South Wales

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This work is derived from:
# https://github.com/AndrewWAlexander/Pinnacle-tar-DICOM
# which is released under the following license:

# Copyright (c) [2017] [Colleen Henschel, Andrew Alexander]

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# pylint: disable = redefined-outer-name

import os
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

from pymedphys._imports import pytest

from pymedphys._data import download
from pymedphys._utilities import test as pmp_test_utils

working_path = tempfile.mkdtemp()
data_path = os.path.join(working_path, "data")


def get_online_data(filename):
    return download.get_file_within_data_zip("pinnacle_test_data.zip", filename)


@pytest.fixture(scope="session")
def data():

    zip_ref = ZipFile(get_online_data("pinnacle_16.0_test_data.zip"), "r")
    zip_ref.extractall(data_path)
    zip_ref.close()

    return Path(data_path)


@pytest.mark.slow
def test_pinnacle_cli_output(data):

    output_path = tempfile.mkdtemp()

    for pinn_dir in data.joinpath("Pt1").joinpath("Pinnacle").iterdir():

        command = (
            [str(pmp_test_utils.get_executable_even_when_embedded()), "-m"]
            + "pymedphys experimental pinnacle export".split()
            + [
                "-o",
                output_path,
                "-m",
                "CT",
                "-m",
                "RTSTRUCT",
                "-m",
                "RTDOSE",
                "-m",
                "RTPLAN",
                "-t",
                "Trial_1",
                pinn_dir.as_posix(),
            ]
        )

        subprocess.check_call(command)

    # Just check that the number of output files is what we expect
    # The output itself is checked in the other function tests
    assert len(os.listdir(output_path)) == 119


@pytest.mark.slow
def test_pinnacle_cli_list(data):

    for pinn_dir in data.joinpath("Pt1").joinpath("Pinnacle").iterdir():

        command = (
            [str(pmp_test_utils.get_executable_even_when_embedded()), "-m"]
            + "pymedphys experimental pinnacle export".split()
            + ["-l", pinn_dir.as_posix()]
        )

        cli_output = str(subprocess.check_output(command))
        cli_output_parts = cli_output.split("\\n")
        assert "Plans and Trials" in cli_output_parts[0]
        assert "Plan_0" in cli_output_parts[1]
        assert "Trial_1" in cli_output_parts[2]
        assert "Images" in cli_output_parts[3]
        assert (
            "CT: 1.2.826.0.1.3680043.9.7225.3631975141391052922211556418733774032"
            in cli_output_parts[4]
        )


@pytest.mark.slow
def test_pinnacle_cli_missing_trial(data):

    output_path = tempfile.mkdtemp()

    for pinn_dir in data.joinpath("Pt1").joinpath("Pinnacle").iterdir():

        command = (
            [str(pmp_test_utils.get_executable_even_when_embedded()), "-m"]
            + "pymedphys experimental pinnacle export".split()
            + ["-o", output_path, "-t", "nonexistenttrial", pinn_dir.as_posix()]
        )

        cli_output = str(subprocess.check_output(command))
        assert "No Trial: nonexistenttrial found in Plan" in cli_output
