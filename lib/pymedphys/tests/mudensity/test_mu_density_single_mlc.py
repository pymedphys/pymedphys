# Copyright (C) 2018 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# pylint: disable=C0103,C1801


"""Testing of a single mlc pair.
"""

import numpy as np

from pymedphys._mudensity.mudensity import single_mlc_pair


def test_minimal_variance_with_resolution():
    mlc_left = (-2.3, 3.1)
    mlc_right = (0, 7.7)

    x_coarse, mu_density_coarse = single_mlc_pair(mlc_left, mlc_right, 1)
    x_fine, mu_density_fine = single_mlc_pair(mlc_left, mlc_right, 0.01)

    reference = np.argmin(np.abs(x_fine[None, :] - x_coarse[:, None]), axis=0)

    average_mu_density_fine = []
    for i in range(2, len(x_coarse) - 2):
        average_mu_density_fine.append(np.mean(mu_density_fine[reference == i]))

    average_mu_density_fine = np.array(average_mu_density_fine)

    assert np.allclose(average_mu_density_fine, mu_density_coarse[2:-2], 0.1)


def test_stationary_partial_occlusion():
    _, mu_density = single_mlc_pair((-1, -1), (2.7, 2.7), 1)

    assert np.allclose(mu_density, [0.5, 1, 1, 1, 0.2])


def test_large_travel():
    x, mu_density = single_mlc_pair((-400, 400), (400, 400))

    linear = (x + 400) / 800
    linear[-1] = 0.5

    assert np.allclose(linear, mu_density, atol=0.001)
