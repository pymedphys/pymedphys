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

# pylint: disable=invalid-name, redefined-outer-name

from pymedphys._imports import numpy as np, pytest

from pymedphys._interp import interp

INTERP_MULTIPLE_TEST = 5


@pytest.fixture
def setup_interp(plot=False):
    x_size = 11
    y_size = 6
    z_size = 31

    x = np.linspace(0, 10, x_size)
    y = np.linspace(10, 20, y_size)
    z = np.linspace(-20, 10, z_size)

    xi = np.linspace(0, 10, x_size * INTERP_MULTIPLE_TEST - 1)
    yi = np.linspace(10, 20, y_size * INTERP_MULTIPLE_TEST - 1)
    zi = np.linspace(-20, 10, z_size * INTERP_MULTIPLE_TEST - 1)

    X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

    values = X**2 + Y**2 + Z**2
    values_interp = interp.multilinear_interp(
        (x, y, z), values, axes_interp=(xi, yi, zi)
    )

    if plot:
        interp.plot_interp_comparison_heatmap(values, values_interp, 2, 0, 0)

    return (x, y, z), values, (xi, yi, zi), values_interp


def test_3d_minmax(setup_interp):
    _, values, _, values_interp = setup_interp

    assert np.isclose(values.min(), values_interp.min())
    assert np.isclose(values.max(), values_interp.max())


def test_3d_vs_scipy(setup_interp):
    axes_known, values, axes_interp, values_interp = setup_interp

    values_interp_scipy = interp.interp_scipy(
        axes_known, values, axes_interp=axes_interp
    )

    assert np.allclose(values_interp, values_interp_scipy)


def test_keepdims(setup_interp):
    (x, y, z), values, (xi, yi, zi), values_interp = setup_interp

    # 3D
    values_interp_keepdims = interp.multilinear_interp(
        (x, y, z), values, axes_interp=(xi, yi, zi), keep_dims=True
    )
    shape_expected = (xi.size, yi.size, zi.size)
    values_interp_reshaped_expected = values_interp.reshape(shape_expected)

    assert np.allclose(values_interp_keepdims, values_interp_reshaped_expected)

    # 2D
    values_interp_keepdims = interp.multilinear_interp(
        (x, y), values[:, :, 0], axes_interp=(xi, yi), keep_dims=True
    )

    assert np.allclose(values_interp_keepdims, values_interp_reshaped_expected[:, :, 0])

    # 1D
    values_interp_keepdims = interp.multilinear_interp(
        (x,), values[:, 0, 0], axes_interp=(xi,), keep_dims=True
    )

    assert np.allclose(values_interp_keepdims, values_interp_reshaped_expected[:, 0, 0])


def test_extrap(setup_interp):
    (x, y, z), values, (xi, yi, zi), _ = setup_interp

    # x_start
    xi = np.concatenate([[xi[0] - 1], xi])
    with pytest.raises(ValueError):
        interp.multilinear_interp(
            (x, y, z), values, axes_interp=(xi, yi, zi), bounds_error=True
        )
    values_interp = interp.multilinear_interp(
        (x, y, z),
        values,
        axes_interp=(xi, yi, zi),
        keep_dims=True,
        bounds_error=False,
        extrap_fill_value=np.inf,
    )
    assert np.all(values_interp[0, :, :] == np.inf)

    # x_end
    xi = np.concatenate([xi, [xi[-1] + 1]])
    with pytest.raises(ValueError):
        interp.multilinear_interp(
            (x, y, z), values, axes_interp=(xi, yi, zi), bounds_error=True
        )
    values_interp = interp.multilinear_interp(
        (x, y, z),
        values,
        axes_interp=(xi, yi, zi),
        keep_dims=True,
        bounds_error=False,
        extrap_fill_value=np.inf,
    )
    assert np.all(values_interp[-1, :, :] == np.inf)

    # y_start
    yi = np.concatenate([[yi[0] - 1], yi])
    with pytest.raises(ValueError):
        interp.multilinear_interp(
            (x, y, z), values, axes_interp=(xi, yi, zi), bounds_error=True
        )
    values_interp = interp.multilinear_interp(
        (x, y, z),
        values,
        axes_interp=(xi, yi, zi),
        keep_dims=True,
        bounds_error=False,
        extrap_fill_value=np.inf,
    )
    assert np.all(values_interp[:, 0, :] == np.inf)

    # y_end
    yi = np.concatenate([yi, [yi[-1] + 1]])
    with pytest.raises(ValueError):
        interp.multilinear_interp(
            (x, y, z), values, axes_interp=(xi, yi, zi), bounds_error=True
        )
    values_interp = interp.multilinear_interp(
        (x, y, z),
        values,
        axes_interp=(xi, yi, zi),
        keep_dims=True,
        bounds_error=False,
        extrap_fill_value=np.inf,
    )
    assert np.all(values_interp[:, -1, :] == np.inf)

    # z_start
    zi = np.concatenate([[zi[0] - 1], zi])
    with pytest.raises(ValueError):
        interp.multilinear_interp(
            (x, y, z), values, axes_interp=(xi, yi, zi), bounds_error=True
        )
    values_interp = interp.multilinear_interp(
        (x, y, z),
        values,
        axes_interp=(xi, yi, zi),
        keep_dims=True,
        bounds_error=False,
        extrap_fill_value=np.inf,
    )
    assert np.all(values_interp[:, :, 0] == np.inf)

    # z_end
    zi = np.concatenate([zi, [zi[-1] + 1]])
    with pytest.raises(ValueError):
        interp.multilinear_interp(
            (x, y, z), values, axes_interp=(xi, yi, zi), bounds_error=True
        )
    values_interp = interp.multilinear_interp(
        (x, y, z),
        values,
        axes_interp=(xi, yi, zi),
        keep_dims=True,
        bounds_error=False,
        extrap_fill_value=np.inf,
    )
    assert np.all(values_interp[:, :, -1] == np.inf)


def test_2d_vs_scipy(setup_interp):
    (x, y, _), values, (xi, yi, _), _ = setup_interp

    values_interp = interp.multilinear_interp(
        (x, y), values[:, :, 0], axes_interp=(xi, yi)
    )

    values_interp_scipy = interp.interp_scipy(
        (x, y), values[:, :, 0], axes_interp=(xi, yi)
    )

    assert np.allclose(values_interp, values_interp_scipy)


def test_1d_vs_scipy(setup_interp):
    (x, _, _), values, (xi, _, _), _ = setup_interp

    values_interp = interp.multilinear_interp((x,), values[:, 0, 0], axes_interp=(xi,))

    values_interp_scipy = interp.interp_scipy((x,), values[:, 0, 0], axes_interp=(xi,))

    assert np.allclose(values_interp, values_interp_scipy)
