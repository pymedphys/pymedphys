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

from pymedphys._imports import numpy as np

from pymedphys._data import download
from pymedphys.experimental.fileformats import read_prs


def test_read_prs():
    data_zip_name = "profiler_test_data.zip"

    file_name = download.get_file_within_data_zip(data_zip_name, "test_varian_open.prs")
    assert np.allclose(read_prs(file_name).cax, 45.50562901780488)
    assert np.allclose(read_prs(file_name).x[0][1], 0.579460838649598)
    assert np.allclose(read_prs(file_name).y[0][1], 0.2910764234184594)

    file_name = download.get_file_within_data_zip(
        data_zip_name, "test_varian_wedge.prs"
    )
    assert np.allclose(read_prs(file_name).cax, 21.863167869662274)
    assert np.allclose(read_prs(file_name).x[0][1], 0.5626051581458927)
    assert np.allclose(read_prs(file_name).y[0][1], 0.260042064635505)

    file_name = download.get_file_within_data_zip(data_zip_name, "test_tomo_50mm.prs")
    assert np.allclose(read_prs(file_name).cax, 784.320114110518)
    assert np.allclose(read_prs(file_name).x[0][1], 563.4064789252321)
    assert np.allclose(read_prs(file_name).y[0][1], 1.8690221773721463)
