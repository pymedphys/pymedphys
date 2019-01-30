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

# from pymedphys.devices import read_profiler_prs

DATA_DIRECTORY = os.path.join(
    os.path.dirname(__file__), "../../data/devices/profiler")


# def test_read_profiler_prs():

#     file_name = os.path.join(DATA_DIRECTORY, 'test_varian_open.prs')
#     assert np.allclose(read_profiler_prs(file_name).cax, 45.50562901780488)
#     assert np.allclose(read_profiler_prs(file_name).x[0][1], 0.579460838649598)
#     assert np.allclose(read_profiler_prs(
#         file_name).y[0][1], 0.2910764234184594)

#     file_name = os.path.join(DATA_DIRECTORY, 'test_varian_wedge.prs')
#     assert np.allclose(read_profiler_prs(file_name).cax, 21.863167869662274)
#     assert np.allclose(read_profiler_prs(
#         file_name).x[0][1], 0.5626051581458927)
#     assert np.allclose(read_profiler_prs(file_name).y[0][1], 0.260042064635505)

#     file_name = os.path.join(DATA_DIRECTORY, 'test_tomo_50mm.prs')
#     assert np.allclose(read_profiler_prs(file_name).cax, 784.320114110518)
#     assert np.allclose(read_profiler_prs(file_name).x[0][1], 563.4064789252321)
#     assert np.allclose(read_profiler_prs(
#         file_name).y[0][1], 1.8690221773721463)
