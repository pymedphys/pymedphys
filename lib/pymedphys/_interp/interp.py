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

from functools import cache
from typing import Sequence

from pymedphys._imports import numba as nb, numpy as np, plt, scipy


def plot_interp_comparison_heatmap(
    values, values_interp, slice_axis: int, slice_number: int, slice_number_interp: int
):
    """
    Plot a comparison heatmap of original and interpolated 3D data slices.

    This function creates a side-by-side heatmap comparison of a slice from the
    original data and a corresponding slice from the interpolated data.

    Parameters
    ----------
    values : array-like
        The original 3D data array.
    values_interp : array-like
        The interpolated 3D data array.
    slice_axis : int
        The axis along which to take the slice (0, 1, or 2).
    slice_number : int
        The index of the slice to display from the original data.
    slice_number_interp : int
        The index of the slice to display from the interpolated data. Note that auto
        matching between the original and interpolated slices is not implemented. The
        user must ensure the slices correspond.

    Returns
    -------
    None
        This function displays the plot directly and does not return any value.

    Notes
    -----
    - The function creates a figure with two subplots side by side.
    - The left subplot shows the slice from the original data.
    - The right subplot shows the slice from the interpolated data.
    - It is up to the user to ensure that
    - Both heatmaps use the same color scale, determined by the minimum and
      maximum values across both datasets.
    - A shared colorbar is displayed on the right side of the figure.
    - The plot is automatically displayed using plt.show().
    """
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


@cache
def _get_interp_linear_1d():
    @nb.njit(parallel=True, fastmath=True, cache=True)
    def _interp_linear_1d(axis_known, values, points_interp, extrap_fill_value=np.nan):
        values_interp = np.zeros(points_interp.shape[0], dtype=np.float64)
        diff = axis_known[1] - axis_known[0]

        # pylint: disable=not-an-iterable
        for i in nb.prange(points_interp.shape[0]):
            xpi = points_interp[i, 0]

            if not axis_known[0] <= xpi <= axis_known[-1]:
                values_interp[i] = extrap_fill_value
                continue

            x1_idx = np.searchsorted(axis_known, xpi)
            x0_idx = x1_idx - 1

            if x0_idx < 0:
                x0_idx = 0
            if x1_idx >= axis_known.size:
                x1_idx = axis_known.size - 1

            wx = (xpi - axis_known[x0_idx]) / diff

            values_interp[i] = values[x0_idx] * (1 - wx) + values[x1_idx] * wx

        return values_interp

    return _interp_linear_1d


def interp_linear_1d(axis_known, values, points_interp, extrap_fill_value=None):
    _interp_linear_1d = _get_interp_linear_1d()
    if extrap_fill_value is None:
        extrap_fill_value = np.nan
    return _interp_linear_1d(
        axis_known=axis_known,
        values=values,
        points_interp=points_interp,
        extrap_fill_value=extrap_fill_value,
    )


@cache
def _get_interp_linear_2d():
    @nb.njit(parallel=True, fastmath=True, cache=True)
    def _interp_linear_2d(axes_known, values, points_interp, extrap_fill_value=np.nan):
        values_interp = np.zeros((points_interp.shape[0]), dtype=np.float64)
        diffs = np.zeros(2)
        for i, axis in enumerate(axes_known):
            diffs[i] = axis[1] - axis[0]
        x, y = axes_known

        # pylint: disable=not-an-iterable
        for i in nb.prange(points_interp.shape[0]):
            xpi, ypi = points_interp[i, 0], points_interp[i, 1]

            if not x[0] <= xpi <= x[-1] or not y[0] <= ypi <= y[-1]:
                values_interp[i] = extrap_fill_value
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

            values_interp[i] = c0 * (1 - wy) + c1 * wy

        return values_interp

    return _interp_linear_2d


def interp_linear_2d(axes_known, values, points_interp, extrap_fill_value=None):
    _interp_linear_2d = _get_interp_linear_2d()
    if extrap_fill_value is None:
        extrap_fill_value = np.nan
    return _interp_linear_2d(
        axes_known=axes_known,
        values=values,
        points_interp=points_interp,
        extrap_fill_value=extrap_fill_value,
    )


@cache
def _get_interp_linear_3d():
    @nb.njit(parallel=True, fastmath=True, cache=True)
    # pylint: disable=invalid-name
    def _interp_linear_3d(axes_known, values, points_interp, extrap_fill_value=np.nan):
        x, y, z = axes_known[0], axes_known[1], axes_known[2]

        values_interp = np.zeros(
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
                not x[0] <= xpi <= x[-1]
                or not y[0] <= ypi <= y[-1]
                or not z[0] <= zpi <= z[-1]
            ):
                values_interp[i] = extrap_fill_value
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

            values_interp[i] = c0 * (1 - wz) + c1 * wz

        return values_interp

    return _interp_linear_3d


def interp_linear_3d(axes_known, values, points_interp, extrap_fill_value=None):
    _interp_linear_3d = _get_interp_linear_3d()
    if extrap_fill_value is None:
        extrap_fill_value = np.nan
    return _interp_linear_3d(
        axes_known=axes_known,
        values=values,
        points_interp=points_interp,
        extrap_fill_value=extrap_fill_value,
    )


def interp_linear_scipy(
    axes_known,
    values,
    axes_interp: Sequence["np.ndarray"] = None,
    points_interp: "np.ndarray" = None,
    keep_dims=False,
    bounds_error=True,
    extrap_fill_value=None,
):
    if axes_interp is not None and points_interp is None:
        mgrids = np.meshgrid(*axes_interp, indexing="ij")
        points_interp = np.column_stack([mgrid.ravel() for mgrid in mgrids])
    elif axes_interp is None and points_interp is not None:
        pass
    else:
        raise ValueError(
            "Exactly one of either `axes_interp` or `points_interp` must be specified"
        )

    if extrap_fill_value is None:
        extrap_fill_value = np.nan

    f = scipy.interpolate.RegularGridInterpolator(
        axes_known, values, bounds_error=bounds_error, fill_value=extrap_fill_value
    )

    if keep_dims:
        if axes_interp is not None:
            return f(points_interp).reshape(axis.size for axis in axes_interp)
        else:
            raise ValueError(
                "If `keep_dims` is True, `axes_interp` must be specified to determine the shape of the output"
            )
    else:
        return f(points_interp)


# pylint: disable=invalid-name
def interp(
    axes_known: Sequence["np.ndarray"],
    values: "np.ndarray",
    axes_interp: Sequence["np.ndarray"] = None,
    points_interp: "np.ndarray" = None,
    keep_dims=False,
    bounds_error=True,
    extrap_fill_value=None,
    skip_checks=False,
) -> "np.ndarray":
    """
    Perform fast linear interpolation on 1D, 2D, or 3D data.

    Parameters
    ----------
    axes_known : Sequence[np.ndarray]
        The coordinate vectors or axis coordinates of the known data points.
    values : np.ndarray
        The known values at the points defined by `axes_known`. Its shape should match
        a tuple of the lengths of the axes in `axes_known` in the same order.
    axes_interp : Sequence[np.ndarray], optional
        The coordinate vectors or axis coordinates for which to interpolate values.
        These axes will be expanded to flattened meshgrids and interpolation will occur
        for each point in these grids. Either `axes_interp` or `points_interp` must be
        provided, but not both.
    points_interp : np.ndarray, optional
        The exact coordinates of the points where interpolation is desired.
        Shape should be (n, d) where n is the number of points and d is the number of
        dimensions. Either `axes_interp` or `points_interp` must be provided, but not
        both.
    keep_dims : bool, optional
        If True, return the interpolated values with the same shape as defined by
        `axes_interp`. Only applicable when `axes_interp` is provided. Default is False.
    bounds_error : bool, optional
        If True, raise an error when interpolation is attempted outside the bounds of
        the input data. Default is True.
    extrap_fill_value : float, optional
        The value to use for points outside the bounds of the input data when
        `bounds_error` is False. Default is None, which results in using np.nan.
    skip_checks : bool, optional
        If True, skip input validation checks. Skipping these checks can produce a
        significant improve in performance for some applications. Default is False.

    Returns
    -------
    np.ndarray
        The interpolated values. If `keep_dims` is True and `axes_interp` is provided,
        the output will have the same shape as defined by `axes_interp`.
        Otherwise, it will be a 1D array.

    Raises
    ------
    ValueError
        If neither or both of `axes_interp` and `points_interp` are provided.
        If `keep_dims` is True but `axes_interp` is not provided.
        If the input axes are not monotonically increasing or evenly spaced.

    Notes
    -----
    This function performs linear interpolation for 1D, 2D, or 3D data.
    It supports both grid-based interpolation (using `axes_interp`) and
    point-based interpolation (using `points_interp`).

    The input axes must be monotonically increasing and evenly spaced.
    """
    if axes_interp is not None and points_interp is None:
        mgrids = np.meshgrid(*axes_interp, indexing="ij")
        points_interp = np.column_stack([mgrid.ravel() for mgrid in mgrids])
    elif axes_interp is None and points_interp is not None:
        if keep_dims:
            raise ValueError(
                "If `keep_dims` is True, `axes_interp` must be specified to determine the shape of the output"
            )
    else:
        raise ValueError(
            "Exactly one of either `axes_interp` or `points_interp` must be specified"
        )
    if not skip_checks:
        axes_known, values = __check_inputs(
            axes_known, values, points_interp, bounds_error
        )

        axes_known_diffs = [np.diff(axis) for axis in axes_known]

        # Handle ascending vs. descending vs. bad order.
        for i, diff in enumerate(axes_known_diffs):
            if not np.all(diff > 0):
                raise ValueError(
                    f"axes_known[{i}] is not monotonically ascending or descending"
                )
            if not np.allclose(diff, diff[0]):
                raise ValueError(f"axis_known[{i}] must be evenly spaced")

    if extrap_fill_value is None:
        extrap_fill_value = np.nan

    if len(axes_known) == 1:
        # keep_dims has no effect for 1D interpolation
        return interp_linear_1d(
            axes_known[0],
            values,
            points_interp,
            extrap_fill_value,
        )

    elif len(axes_known) == 2:
        values_interp = interp_linear_2d(
            axes_known,
            values,
            points_interp,
            extrap_fill_value,
        )
    else:
        values_interp = interp_linear_3d(
            axes_known,
            values,
            points_interp,
            extrap_fill_value,
        )

    if keep_dims:
        values_interp = values_interp.reshape([axis.size for axis in axes_interp])

    return values_interp
