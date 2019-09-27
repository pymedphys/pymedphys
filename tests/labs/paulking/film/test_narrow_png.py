# Copyright (C) 2019 Paul King

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
