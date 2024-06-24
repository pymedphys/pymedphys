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

from typing import Sequence

from pymedphys._imports import numba as nb, numpy as np, plt, scipy, interpolation


def plot_interp_comparison_heatmap(
    values, values_interp, slice_axis: int, slice_number: int, slice_number_interp: int
):
    _, (ax1, ax2) = plt.subplots(1, 2)

    plot_min = min(values.min(), values_interp.min())
    plot_max = max(values.max(), values_interp.max())

    ax1.imshow(
        values.take(axis=slice_axis, indices=slice_number), vmin=plot_min, vmax=plot_max
    )

    im2 = ax2.imshow(
        values_interp.take(axis=slice_axis, indices=slice_number_interp),
        vmin=plot_min,
        vmax=plot_max,
    )
    plt.colorbar(im2, ax=(ax1, ax2), orientation="vertical")
    plt.show()


def __check_inputs(
    axes_known: Sequence["np.ndarray"],
    values: "np.ndarray",
    points_interp: "np.ndarray",
    bounds_error=False,
) -> None:
    if not 1 <= len(axes_known) == points_interp.shape[-1] <= 3:
        raise ValueError(
            f"axes_known (len {len(axes_known)}) and points_interp (len {points_interp.shape[-1]}) must have the same length; either 1, 2, or 3"
        )

    for i, axis_known in enumerate(axes_known):
        if not axis_known.ndim == points_interp[i].ndim == 1:
            raise ValueError(
                f"axes_known[{i}] (shape {[{axis_known.shape}]}) and interp_structure[{i}] (shape {[{points_interp[i].shape}]}) must be 1D arrays"
            )
        if not axis_known.size == values.shape[i]:
            raise ValueError(
                f"axes_known[{i}] (size {axis_known.size}) must match the size of the corresponding dimension of values ({values.shape[i]})"
            )
        if bounds_error and (
            points_interp[:, i].min() < axis_known.min()
            or points_interp[:, i].max() > axis_known.max()
        ):
            raise ValueError(
                f"""points_interp[:, {i}] must be within the range of axes_known[{i}]\n
                ({points_interp[:, i].min()}, {points_interp[:, i].max()}) vs. ({axis_known.min()}, {axis_known.max()})"""
            )

    axes_known = tuple(np.array(axis, dtype=np.float64) for axis in axes_known)
    values = np.array(values, dtype=np.float64)

    return axes_known, values


@nb.njit(parallel=True, fastmath=True, cache=True)
def interp1d(axis_known, values, points_interp, extrap_fill_value):
    interpolated_values = np.zeros(points_interp.shape[0], dtype=np.float64)
    diff = axis_known[1] - axis_known[0]

    for i in nb.prange(points_interp.shape[0]):
        xpi = points_interp[i, 0]

        if xpi < axis_known[0] or xpi > axis_known[-1]:
            interpolated_values[i] = extrap_fill_value
            continue

        x1_idx = np.searchsorted(axis_known, xpi)
        x0_idx = x1_idx - 1

        if x0_idx < 0:
            x0_idx = 0
        if x1_idx >= axis_known.size:
            x1_idx = axis_known.size - 1

        wx = (xpi - axis_known[x0_idx]) / diff

        interpolated_values[i] = values[x0_idx] * (1 - wx) + values[x1_idx] * wx

    return interpolated_values


@nb.njit(parallel=True, fastmath=True, cache=True)
def interp2d(axes_known, values, points_interp, extrap_fill_value):
    interpolated_values = np.zeros((points_interp.shape[0]), dtype=np.float64)
    diffs = np.zeros(2)
    for i, axis in enumerate(axes_known):
        diffs[i] = axis[1] - axis[0]
    x, y = axes_known

    for i in nb.prange(points_interp.shape[0]):
        xpi, ypi = points_interp[i, 0], points_interp[i, 1]

        if xpi < x[0] or xpi > x[-1] or ypi < y[0] or ypi > y[-1]:
            interpolated_values[i] = extrap_fill_value
            continue

        # Find the indices of the surrounding grid points
        x1_idx = np.searchsorted(x, xpi)
        x0_idx = x1_idx - 1
        y1_idx = np.searchsorted(y, ypi)
        y0_idx = y1_idx - 1

        if x0_idx < 0:
            x0_idx = 0
        if y0_idx < 0:
            y0_idx = 0
        if x1_idx >= x.size:
            x1_idx = x.size - 1
        if y1_idx >= y.size:
            y1_idx = y.size - 1

        c00 = values[x0_idx, y0_idx]
        c01 = values[x0_idx, y1_idx]
        c10 = values[x1_idx, y0_idx]
        c11 = values[x1_idx, y1_idx]

        wx = (xpi - x[x0_idx]) / diffs[0]
        wy = (ypi - y[y0_idx]) / diffs[1]

        c0 = c00 * (1 - wx) + c10 * wx
        c1 = c01 * (1 - wx) + c11 * wx

        interpolated_values[i] = c0 * (1 - wy) + c1 * wy

    return interpolated_values


@nb.njit(parallel=True, fastmath=True, cache=True)
# pylint: disable=invalid-name
def interp3d(axes_known, values, points_interp, extrap_fill_value):
    x, y, z = axes_known[0], axes_known[1], axes_known[2]

    interpolated_values = np.zeros(
        points_interp.shape[0],
        dtype=np.float64,
    )

    diffs = np.zeros(3)
    for i, axis in enumerate(axes_known):
        diffs[i] = axis[1] - axis[0]

    # pylint: disable=not-an-iterable
    for i in nb.prange(points_interp.shape[0]):
        xpi, ypi, zpi = (
            points_interp[i, 0],
            points_interp[i, 1],
            points_interp[i, 2],
        )

        if (
            xpi < x[0]
            or xpi > x[-1]
            or ypi < y[0]
            or ypi > y[-1]
            or zpi < z[0]
            or zpi > z[-1]
        ):
            interpolated_values[i] = extrap_fill_value
            continue

        # Find the indices of the surrounding grid points
        x1_idx = np.searchsorted(x, xpi)
        x0_idx = x1_idx - 1
        y1_idx = np.searchsorted(y, ypi)
        y0_idx = y1_idx - 1
        z1_idx = np.searchsorted(z, zpi)
        z0_idx = z1_idx - 1

        if x0_idx < 0:
            x0_idx = 0
        if y0_idx < 0:
            y0_idx = 0
        if z0_idx < 0:
            z0_idx = 0
        if x1_idx >= x.size:
            x1_idx = x.size - 1
        if y1_idx >= y.size:
            y1_idx = y.size - 1
        if z1_idx >= z.size:
            z1_idx = z.size - 1

        # Compute interpolation weights
        wx = (xpi - x[x0_idx]) / diffs[0]
        wy = (ypi - y[y0_idx]) / diffs[1]
        wz = (zpi - z[z0_idx]) / diffs[2]

        # Extract values values at corner points
        c000 = values[x0_idx, y0_idx, z0_idx]
        c001 = values[x0_idx, y0_idx, z1_idx]
        c010 = values[x0_idx, y1_idx, z0_idx]
        c011 = values[x0_idx, y1_idx, z1_idx]
        c100 = values[x1_idx, y0_idx, z0_idx]
        c101 = values[x1_idx, y0_idx, z1_idx]
        c110 = values[x1_idx, y1_idx, z0_idx]
        c111 = values[x1_idx, y1_idx, z1_idx]

        # Perform trilinear interpolation
        c00 = c000 * (1 - wx) + c100 * wx
        c01 = c001 * (1 - wx) + c101 * wx
        c10 = c010 * (1 - wx) + c110 * wx
        c11 = c011 * (1 - wx) + c111 * wx

        c0 = c00 * (1 - wy) + c10 * wy
        c1 = c01 * (1 - wy) + c11 * wy

        interpolated_values[i] = c0 * (1 - wz) + c1 * wz

    return interpolated_values


def interp3d_scipy(axes_known, values, positions):
    interp = scipy.interpolate.RegularGridInterpolator(axes_known, values)
    return interp(positions)


def interp3d_econforge(grid, values, positions):
    return interpolation.splines.eval_linear(grid, values, positions)


# pylint: disable=invalid-name
def multilinear_interp(
    axes_known: Sequence["np.ndarray"],
    values: "np.ndarray",
    axes_interp: Sequence["np.ndarray"] = None,
    points_interp: "np.ndarray" = None,
    algo: str = "pymedphys",
    bounds_error=True,
    extrap_fill_value=np.nan,
) -> "np.ndarray":
    if axes_interp is not None and points_interp is None:
        mgrids = np.meshgrid(*axes_interp, indexing="ij")
        points_interp = np.column_stack([mgrid.ravel() for mgrid in mgrids])
    elif axes_interp is None and points_interp is not None:
        pass
    else:
        raise ValueError(
            "Exactly one of either axes_interp or points_interp must be specified"
        )
    axes_known, values = __check_inputs(axes_known, values, points_interp, bounds_error)

    axes_known_diffs = [np.diff(axis) for axis in axes_known]

    # Handle ascending vs. descending vs. bad order.
    for i, diff in enumerate(axes_known_diffs):
        if not np.all(diff > 0):
            raise ValueError(
                f"axes_known[{i}] is not monotonically ascending or descending"
            )
        if not np.allclose(diff, diff[0]):
            raise ValueError(f"axis_known[{i}] must be evenly spaced")

    if len(axes_known) == 1:
        values_interp = interp1d(
            axes_known[0],
            values,
            points_interp,
            extrap_fill_value,
        )

    elif len(axes_known) == 2:
        values_interp = interp2d(
            axes_known,
            values,
            points_interp,
            extrap_fill_value,
        )
    else:
        if algo.lower() == "pymedphys":
            values_interp = interp3d(
                axes_known,
                values,
                points_interp,
                extrap_fill_value,
            )

        elif algo.lower() == "scipy":
            values_interp = interp3d_scipy(axes_known, values, points_interp)

        elif algo.lower() == "econforge":
            grid = interpolation.splines.CGrid(*axes_known)
            values_interp = interp3d_econforge(grid, values, points_interp)

    return values_interp
