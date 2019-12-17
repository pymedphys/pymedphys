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

# import numpy as np

# from pymedphys.devices import read_profiler_prs

DATA_DIRECTORY = os.path.join(os.path.dirname(__file__), "../../data/devices/profiler")


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
