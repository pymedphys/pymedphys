# Copyright (C) 2019 Cancer Care Associates

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

import numpy as np

import imageio

import pymedphys
import pymedphys._wlutz.imginterp


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

    field = pymedphys._wlutz.imginterp.create_interpolated_field(  # pylint:disable = protected-access
        x, y, img
    )

    assert np.all(field(xx, yy) == img)
