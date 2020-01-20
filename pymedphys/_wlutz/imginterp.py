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


from pymedphys._imports import numpy as np
from pymedphys._imports import scipy


class Field:
    def __init__(self, x, y, img):
        self._x = x
        self._y = y
        self._img = img
        self._interpolation = scipy.interpolate.RectBivariateSpline(
            x, y, img.T, kx=1, ky=1
        )

    @property
    def x(self):
        return self._x

    @property
    def y(self):
        return self._y

    @property
    def img(self):
        return self._img

    def __call__(self, x, y):
        if np.shape(x) != np.shape(y):
            raise ValueError("x and y required to be the same shape")

        result = self._interpolation.ev(np.ravel(x), np.ravel(y))
        result.shape = x.shape

        return result


def create_interpolated_field(x, y, img):
    field = Field(x, y, img)

    return field
