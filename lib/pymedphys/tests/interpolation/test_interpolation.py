# Copyright (C) 2024 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pymedphys._imports import numpy as np, pytest, scipy

# from pymedphys._imports import pyplot as plt
from pymedphys._interp import interp


@pytest.fixture
def setup_3d_interp(plot=False):
    x_size = 11
    y_size = 6
    z_size = 31

    x = np.linspace(0, 10, x_size)
    y = np.linspace(10, 20, y_size)
    z = np.linspace(-20, 10, z_size)

    xi = np.linspace(0, 10, x_size * 5 - 1)
    yi = np.linspace(10, 20, y_size * 5 - 1)
    zi = np.linspace(-20, 10, z_size * 5 - 1)

    X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

    values = X**2 + Y**2 + Z**2
    values_interp = interp.multilinear_interp(
        (x, y, z), values, axes_interp=(xi, yi, zi)
    ).reshape((xi.size, yi.size, zi.size))

    if plot:
        interp.plot_interp_comparison_heatmap(values, values_interp, 2, 0, 0)

    return (x, y, z), values, (xi, yi, zi), values_interp


# pylint: disable=invalid-name
def test_3d_minmax(setup_3d_interp):
    _, values, _, values_interp = setup_3d_interp

    assert np.isclose(values.min(), values_interp.min())
    assert np.isclose(values.max(), values_interp.max())


def test_3d_vs_scipy_independent(setup_3d_interp):
    axes_known, values, axes_interp, values_interp = setup_3d_interp

    mgrids = np.meshgrid(*axes_interp, indexing="ij")
    points_interp = np.column_stack([mgrid.ravel() for mgrid in mgrids])

    f = scipy.interpolate.RegularGridInterpolator(axes_known, values)
    values_interp_scipy = f(points_interp).reshape(values_interp.shape)

    assert np.allclose(values_interp, values_interp_scipy)


def test_3d_vs_scipy(setup_3d_interp):
    axes_known, values, axes_interp, values_interp = setup_3d_interp

    expected_shape = (axes_interp[0].size, axes_interp[1].size, axes_interp[2].size)

    values_interp_scipy = interp.multilinear_interp(
        axes_known, values, axes_interp, algo="scipy"
    ).reshape(expected_shape)

    assert np.allclose(values_interp, values_interp_scipy)
