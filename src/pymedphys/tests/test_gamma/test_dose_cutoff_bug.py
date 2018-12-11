# Copyright (C) 2018 Simon Biggs

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
from pymedphys.gamma import gamma_shell

DATA_DIRECTORY = os.path.join(
    os.path.dirname(__file__), "../data/gamma/dose-cutoff-bug")

REFERENCE_FILE = os.path.join(
    DATA_DIRECTORY, 'lfs-reference.csv')
EVALUATION_FILE = os.path.join(
    DATA_DIRECTORY, 'lfs-evaluation.csv')


# def test_bug():
#     data1_raw = np.genfromtxt(REFERENCE_FILE, delimiter=',')
#     data1 = data1_raw.reshape((411, 534, 273))
#     data2_raw = np.genfromtxt(EVALUATION_FILE, delimiter=',')
#     data2 = data2_raw.reshape((411, 534, 273))

#     x = np.arange(411)
#     y = np.arange(534)
#     z = np.arange(273)
#     coords = (x, y, z)

#     gamma_shell(coords, data1, coords, data2, 3, 30)


# if __name__ == "__main__":
#     test_bug()
