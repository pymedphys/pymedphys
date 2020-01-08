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


def create_interpolated_field(x, y, img):
    interpolation = scipy.interpolate.RectBivariateSpline(x, y, img.T, kx=1, ky=1)

    def field(x, y):
        if np.shape(x) != np.shape(y):
            raise ValueError("x and y required to be the same shape")

        result = interpolation.ev(np.ravel(x), np.ravel(y))
        result.shape = x.shape

        return result

    return field
