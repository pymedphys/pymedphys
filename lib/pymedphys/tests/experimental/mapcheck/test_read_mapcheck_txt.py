# Copyright (C) 2018 Paul King

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

from pymedphys._imports import numpy as np

import pymedphys
from pymedphys.experimental.fileformats import read_mapcheck

DATA_DIRECTORY = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))


def test_read_mapcheck_txt():
    """Test for successful read of mapcheck file with consistent results."""

    file_path = pymedphys.data_path("tomo_mapcheck_test.txt")

    result = read_mapcheck(file_path)
    assert result.dose.shape == (len(result.x), len(result.y))  # x,y -> (x,y)
    assert result.x[0] < result.x[-1]  # x ascending
    assert result.y[0] < result.y[-1]  # y ascending
    assert len(set(result.x)) == len(set(result.x))  # x vals unique
    assert len(set(result.y)) == len(set(result.y))  # y vals unique
    assert np.all([i >= 0 for i in result.dose.flatten()])  # doses >= 0
    assert np.allclose(result.dose[20][20], 92.03876716076289)
