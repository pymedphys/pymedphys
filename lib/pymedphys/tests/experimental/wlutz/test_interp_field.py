# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pymedphys._imports import imageio
from pymedphys._imports import numpy as np

import pymedphys

from pymedphys._experimental.wlutz import imginterp


def test_interp_field():
    image_path = pymedphys.data_path("wlutz_image.png")
    img = imageio.imread(image_path)
    assert np.shape(img) == (1024, 1024)
    img = img[:, 1:-1]
    assert np.shape(img) == (1024, 1022)
    assert img.dtype == np.dtype("uint16")
    img = 1 - img[::-1, :] / 2 ** 16
    assert img.dtype == np.dtype("float64")

    shape = np.shape(img)
    x = np.arange(-shape[1] / 2, shape[1] / 2) / 4
    y = np.arange(-shape[0] / 2, shape[0] / 2) / 4
    xx, yy = np.meshgrid(x, y)

    field = imginterp.create_interpolated_field(x, y, img)

    assert np.all(field(xx, yy) == img)
