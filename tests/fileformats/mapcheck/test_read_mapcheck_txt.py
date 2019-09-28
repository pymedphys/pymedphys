# Copyright (C) 2018 Paul King

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.

import os

import numpy as np
from pymedphys.labs.fileformats.mapcheck import read_mapcheck_txt

DATA_DIRECTORY = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))


def test_read_mapcheck_txt():
    """Test for successful read of mapcheck file with consistent results."""
    file_name = os.path.join(DATA_DIRECTORY, "tomo_mapcheck_test.txt")
    result = read_mapcheck_txt(file_name)
    assert result.dose.shape == (len(result.x), len(result.y))  # x,y -> (x,y)
    assert result.x[0] < result.x[-1]  # x ascending
    assert result.y[0] < result.y[-1]  # y ascending
    assert len(set(result.x)) == len(set(result.x))  # x vals unique
    assert len(set(result.y)) == len(set(result.y))  # y vals unique
    assert np.all([i >= 0 for i in result.dose.flatten()])  # doses >= 0
    assert np.allclose(result.dose[20][20], 92.03876716076289)


if __name__ == "__main__":
    test_read_mapcheck_txt()
