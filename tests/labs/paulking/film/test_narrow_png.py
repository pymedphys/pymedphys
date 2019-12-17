# Copyright (C) 2019 Paul King

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

import numpy as np

from pymedphys.labs.paulking.narrow_png import read_narrow_png

DATA_DIRECTORY = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))


def test_read_narrow_png():
    vert_strip = os.path.join(DATA_DIRECTORY, "FilmCalib_EBT_vert_strip.png")
    horz_strip = os.path.join(DATA_DIRECTORY, "FilmCalib_EBT_horz_strip.png")
    assert np.allclose(
        read_narrow_png(vert_strip)[0][0], read_narrow_png(horz_strip)[0][0]
    )


if __name__ == "__main__":
    test_read_narrow_png()
