# Copyright (C) 2019 Simon Biggs

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

from pymedphys._imports import numpy as np
from pymedphys._imports import plt

from pymedphys._utilities.constants import AGILITY
from pymedphys._utilities.controlpoints import remove_irrelevant_control_points

from .plt import pcolormesh_grid

__DEFAULT_LEAF_PAIR_WIDTHS = AGILITY
__DEFAULT_GRID_RESOLUTION = 1
__DEFAULT_MAX_LEAF_GAP = 400
__DEFAULT_MIN_STEP_PER_PIXEL = 10


def calc_metersetmap(
    mu,
    mlc,
    jaw,
    grid_resolution=None,
    max_leaf_gap=None,
    leaf_pair_widths=None,
    min_step_per_pixel=None,
):
    """Determine the MetersetMap.

    Both jaw and mlc positions are defined in bipolar format for each control
    point. A negative value indicates travel over the isocentre. All positional
    arguments are defined at the isocentre projection with the units of mm.

    Parameters
    ----------
    mu : numpy.ndarray
        1-D array containing an MU value for each control point.
    mlc : numpy.ndarray
        3-D array containing the MLC positions

            | axis 0: control point
            | axis 1: mlc pair
            | axis 2: leaf bank

    jaw : numpy.ndarray
        2-D array containing the jaw positions.

            | axis 0: control point
            | axis 1: diaphragm

    grid_resolution : float, optional
        The calc grid resolution. Defaults to 1 mm.

    max_leaf_gap : float, optional
        The maximum possible distance between opposing leaves. Defaults to
        400 mm.

    leaf_pair_widths : tuple, optional
        The widths of each leaf pair in the
        MLC limiting device. The number of entries in the tuples defines
        the number of leaf pairs. Each entry itself defines that particular
        leaf pair width. Defaults to 80 leaf pairs each 5 mm wide.

    min_step_per_pixel : int, optional
        The minimum number of time steps
        used per pixel for each control point. Defaults to 10.

    Returns
    -------
    metersetmap : numpy.ndarray
        2-D array containing the calculated metersetmap.

            | axis 0: jaw direction
            | axis 1: mlc direction

    Examples
    --------
    >>> import numpy as np
    >>> import pymedphys
    >>>
    >>> leaf_pair_widths = (5, 5, 5)
    >>> max_leaf_gap = 10
    >>> mu = np.array([0, 2, 5, 10])
    >>> mlc = np.array([
    ...     [
    ...         [1, 1],
    ...         [2, 2],
    ...         [3, 3]
    ...     ],
    ...     [
    ...         [2, 2],
    ...         [3, 3],
    ...         [4, 4]
    ...     ],
    ...     [
    ...         [-2, 3],
    ...         [-2, 4],
    ...         [-2, 5]
    ...     ],
    ...     [
    ...         [0, 0],
    ...         [0, 0],
    ...         [0, 0]
    ...     ]
    ... ])
    >>> jaw = np.array([
    ...     [7.5, 7.5],
    ...     [7.5, 7.5],
    ...     [-2, 7.5],
    ...     [0, 0]
    ... ])
    >>>
    >>> grid = pymedphys.metersetmap.grid(
    ...    max_leaf_gap=max_leaf_gap, leaf_pair_widths=leaf_pair_widths)
    >>> grid['mlc']
    array([-5., -4., -3., -2., -1.,  0.,  1.,  2.,  3.,  4.,  5.])
    >>>
    >>> grid['jaw']
    array([-8., -7., -6., -5., -4., -3., -2., -1.,  0.,  1.,  2.,  3.,  4.,
            5.,  6.,  7.,  8.])
    >>>
    >>> metersetmap = pymedphys.metersetmap.calculate(
    ...    mu, mlc, jaw, max_leaf_gap=max_leaf_gap,
    ...    leaf_pair_widths=leaf_pair_widths)
    >>> pymedphys.metersetmap.display(grid, metersetmap)
    >>>
    >>> np.round(metersetmap, 1)
    array([[0. , 0. , 0. , 0. , 0. , 0. , 0. , 0. , 0. , 0. , 0. ],
           [0. , 0. , 0. , 0.3, 1.9, 2.2, 1.9, 0.4, 0. , 0. , 0. ],
           [0. , 0. , 0. , 0.4, 2.2, 2.5, 2.2, 0.6, 0. , 0. , 0. ],
           [0. , 0. , 0. , 0.4, 2.4, 2.8, 2.5, 0.8, 0. , 0. , 0. ],
           [0. , 0. , 0. , 0.4, 2.5, 3.1, 2.8, 1. , 0. , 0. , 0. ],
           [0. , 0. , 0. , 0.4, 2.5, 3.4, 3.1, 1.3, 0. , 0. , 0. ],
           [0. , 0. , 0.4, 2.3, 3.2, 3.7, 3.7, 3.5, 1.6, 0. , 0. ],
           [0. , 0. , 0.4, 2.3, 3.2, 3.8, 4. , 3.8, 1.9, 0.1, 0. ],
           [0. , 0. , 0.4, 2.3, 3.2, 3.8, 4.3, 4.1, 2.3, 0.1, 0. ],
           [0. , 0. , 0.4, 2.3, 3.2, 3.9, 5.2, 4.7, 2.6, 0.2, 0. ],
           [0. , 0. , 0.4, 2.3, 3.2, 3.8, 5.4, 6.6, 3.8, 0.5, 0. ],
           [0. , 0.3, 2.2, 3. , 3.5, 4. , 5.1, 7.5, 6.7, 3.9, 0.5],
           [0. , 0.3, 2.2, 3. , 3.5, 4. , 4.7, 6.9, 6.7, 3.9, 0.5],
           [0. , 0.3, 2.2, 3. , 3.5, 4. , 4.5, 6.3, 6.4, 3.9, 0.5],
           [0. , 0.3, 2.2, 3. , 3.5, 4. , 4.5, 5.6, 5.7, 3.8, 0.5],
           [0. , 0.3, 2.2, 3. , 3.5, 4. , 4.5, 5.1, 5.1, 3.3, 0.5],
           [0. , 0. , 0. , 0. , 0. , 0. , 0. , 0. , 0. , 0. , 0. ]])


    MetersetMap from a Mosaiq record

    >>> import pymedphys
    >>>
    >>> def metersetmap_from_mosaiq(msq_server_name, field_id):
    ...     with pymedphys.mosaiq.connect(msq_server_name) as connection:
    ...         delivery = pymedphys.Delivery.from_mosaiq(connection, field_id)
    ...
    ...     grid = pymedphys.metersetmap.grid()
    ...     metersetmap = delivery.metersetmap()
    ...     pymedphys.metersetmap.display(grid, metersetmap)
    >>>
    >>> metersetmap_from_mosaiq('a_server_name', 11111) # doctest: +SKIP


    MetersetMap from a logfile at a given filepath

    >>> import pymedphys
    >>>
    >>> def metersetmap_from_logfile(filepath):
    ...     delivery_data = Delivery.from_logfile(filepath)
    ...     metersetmap = Delivery.metersetmap()
    ...
    ...     grid = pymedphys.metersetmap.grid()
    ...     pymedphys.metersetmap.display(grid, metersetmap)
    >>>
    >>> metersetmap_from_logfile(r"a/path/goes/here")  # doctest: +SKIP

    """

    if grid_resolution is None:
        grid_resolution = __DEFAULT_GRID_RESOLUTION

    if max_leaf_gap is None:
        max_leaf_gap = __DEFAULT_MAX_LEAF_GAP

    if leaf_pair_widths is None:
        leaf_pair_widths = __DEFAULT_LEAF_PAIR_WIDTHS

    if min_step_per_pixel is None:
        min_step_per_pixel = __DEFAULT_MIN_STEP_PER_PIXEL

    divisibility_of_max_leaf_gap = np.array(max_leaf_gap / 2 / grid_resolution)
    max_leaf_gap_is_divisible = (
        divisibility_of_max_leaf_gap.astype(int) == divisibility_of_max_leaf_gap
    )

    if not max_leaf_gap_is_divisible:
        raise ValueError(
            "The grid resolution needs to be able to divide the max leaf gap exactly by"
            " four"
        )

    leaf_pair_widths = np.array(leaf_pair_widths)

    if not np.max(np.abs(mlc)) <= max_leaf_gap / 2:  # pylint: disable = unneeded-not
        first_failing_control_point = np.where(np.abs(mlc) > max_leaf_gap / 2)[0][0]

        raise ValueError(
            "The mlc should not travel further out than half the maximum leaf gap.\n"
            "The first failing control point has the following positions:\n"
            f"{np.array(mlc)[first_failing_control_point, :, :]}"
        )

    mu, mlc, jaw = remove_irrelevant_control_points(mu, mlc, jaw)

    full_grid = get_grid(max_leaf_gap, grid_resolution, leaf_pair_widths)

    metersetmap = np.zeros((len(full_grid["jaw"]), len(full_grid["mlc"])))

    for i in range(len(mu) - 1):
        control_point_slice = slice(i, i + 2, 1)
        current_mlc = mlc[control_point_slice, :, :]
        current_jaw = jaw[control_point_slice, :]
        delivered_mu = np.diff(mu[control_point_slice])

        grid, metersetmap_of_slice = calc_single_control_point(
            current_mlc,
            current_jaw,
            delivered_mu,
            leaf_pair_widths=leaf_pair_widths,
            grid_resolution=grid_resolution,
            min_step_per_pixel=min_step_per_pixel,
        )
        full_grid_metersetmap_of_slice = _convert_to_full_grid(
            grid, full_grid, metersetmap_of_slice
        )

        metersetmap += full_grid_metersetmap_of_slice

    return metersetmap


def calc_single_control_point(
    mlc,
    jaw,
    delivered_mu=1,
    leaf_pair_widths=__DEFAULT_LEAF_PAIR_WIDTHS,
    grid_resolution=__DEFAULT_GRID_RESOLUTION,
    min_step_per_pixel=__DEFAULT_MIN_STEP_PER_PIXEL,
):
    """Calculate the MetersetMap for a single control point.

    Examples
    --------
    >>> from pymedphys._imports import numpy as np
    >>> from pymedphys._metersetmap.metersetmap import (
    ...     calc_single_control_point, display_metersetmap)
    >>>
    >>> leaf_pair_widths = (2, 2)
    >>> mlc = np.array([
    ...     [
    ...         [1, 1],
    ...         [2, 2],
    ...     ],
    ...     [
    ...         [2, 2],
    ...         [3, 3],
    ...     ]
    ... ])
    >>> jaw = np.array([
    ...     [1.5, 1.2],
    ...     [1.5, 1.2]
    ... ])
    >>> grid, metersetmap = calc_single_control_point(
    ...     mlc, jaw, leaf_pair_widths=leaf_pair_widths)
    >>> display_metersetmap(grid, metersetmap)
    >>>
    >>> grid['mlc']
    array([-3., -2., -1.,  0.,  1.,  2.,  3.])
    >>>
    >>> grid['jaw']
    array([-1.5, -0.5,  0.5,  1.5])
    >>>
    >>> np.round(metersetmap, 2)
    array([[0.  , 0.07, 0.43, 0.5 , 0.43, 0.07, 0.  ],
           [0.  , 0.14, 0.86, 1.  , 0.86, 0.14, 0.  ],
           [0.14, 0.86, 1.  , 1.  , 1.  , 0.86, 0.14],
           [0.03, 0.17, 0.2 , 0.2 , 0.2 , 0.17, 0.03]])
    """
    mlc = np.array(mlc, copy=False)
    jaw = np.array(jaw, copy=False)

    leaf_pair_widths = np.array(leaf_pair_widths)
    leaf_division = leaf_pair_widths / grid_resolution

    if not np.all(leaf_division.astype(int) == leaf_division):
        raise ValueError(
            "The grid resolution needs to exactly divide every leaf pair width."
        )

    if (
        not np.max(np.abs(jaw))  # pylint: disable = unneeded-not
        <= np.sum(leaf_pair_widths) / 2
    ):
        raise ValueError(
            "The jaw should not travel further out than the maximum leaf limits. "
            f"Max travel was {np.max(np.abs(jaw))}"
        )

    (grid, grid_leaf_map, mlc) = _determine_calc_grid_and_adjustments(
        mlc, jaw, leaf_pair_widths, grid_resolution
    )

    positions = {
        "mlc": {
            1: (-mlc[0, :, 0], -mlc[1, :, 0]),  # left
            -1: (mlc[0, :, 1], mlc[1, :, 1]),  # right
        },
        "jaw": {
            1: (-jaw[0::-1, 0], -jaw[1::, 0]),  # bot
            -1: (jaw[0::-1, 1], jaw[1::, 1]),  # top
        },
    }

    time_steps = _calc_time_steps(positions, grid_resolution, min_step_per_pixel)
    blocked_by_device = _calc_blocked_by_device(
        grid, positions, grid_resolution, time_steps
    )
    device_open = _calc_device_open(blocked_by_device)
    mlc_open, jaw_open = _remap_mlc_and_jaw(device_open, grid_leaf_map)
    open_fraction = _calc_open_fraction(mlc_open, jaw_open)

    metersetmap = open_fraction * delivered_mu

    return grid, metersetmap


def single_mlc_pair(
    left_mlc,
    right_mlc,
    grid_resolution=__DEFAULT_GRID_RESOLUTION,
    min_step_per_pixel=__DEFAULT_MIN_STEP_PER_PIXEL,
):
    """Calculate the MetersetMap of a single leaf pair.

    Examples
    --------
    >>> from pymedphys._imports import numpy as np
    >>> import matplotlib.pyplot as plt
    >>>
    >>> from pymedphys._metersetmap.metersetmap import single_mlc_pair
    >>>
    >>> mlc_left = (-2.3, 3.1)  # (start position, end position)
    >>> mlc_right = (0, 7.7)
    >>>
    >>> x, metersetmap = single_mlc_pair(mlc_left, mlc_right)
    >>> fig = plt.plot(x, metersetmap, '-o')
    >>>
    >>> x
    array([-2., -1.,  0.,  1.,  2.,  3.,  4.,  5.,  6.,  7.,  8.])
    >>>
    >>> np.round(metersetmap, 3)
    array([0.064, 0.244, 0.408, 0.475, 0.53 , 0.572, 0.481, 0.352, 0.224,
           0.096, 0.004])
    """
    leaf_pair_widths = [grid_resolution]
    jaw = np.array(
        [
            [grid_resolution / 2, grid_resolution / 2],
            [grid_resolution / 2, grid_resolution / 2],
        ]
    )
    mlc = np.array([[[-left_mlc[0], right_mlc[0]]], [[-left_mlc[1], right_mlc[1]]]])

    grid, metersetmap = calc_single_control_point(
        mlc,
        jaw,
        leaf_pair_widths=leaf_pair_widths,
        grid_resolution=grid_resolution,
        min_step_per_pixel=min_step_per_pixel,
    )

    return grid["mlc"], metersetmap[0, :]


def calc_metersetmap_return_grid(
    mu,
    mlc,
    jaw,
    grid_resolution=__DEFAULT_GRID_RESOLUTION,
    max_leaf_gap=__DEFAULT_MAX_LEAF_GAP,
    leaf_pair_widths=__DEFAULT_LEAF_PAIR_WIDTHS,
    min_step_per_pixel=__DEFAULT_MIN_STEP_PER_PIXEL,
):
    """DEPRECATED. This is a temporary helper function to provide the old
    api.
    """

    leaf_pair_widths = np.array(leaf_pair_widths)
    metersetmap = calc_metersetmap(
        mu,
        mlc,
        jaw,
        grid_resolution=grid_resolution,
        max_leaf_gap=max_leaf_gap,
        leaf_pair_widths=leaf_pair_widths,
        min_step_per_pixel=min_step_per_pixel,
    )

    full_grid = get_grid(max_leaf_gap, grid_resolution, leaf_pair_widths)

    grid_xx, grid_yy = np.meshgrid(full_grid["mlc"], full_grid["jaw"])

    return grid_xx, grid_yy, metersetmap


def get_grid(
    max_leaf_gap=__DEFAULT_MAX_LEAF_GAP,
    grid_resolution=__DEFAULT_GRID_RESOLUTION,
    leaf_pair_widths=__DEFAULT_LEAF_PAIR_WIDTHS,
):
    """Get the MetersetMap grid for plotting purposes.

    Examples
    --------
    See :func:`pymedphys.metersetmap.calculate`.
    """

    leaf_pair_widths = np.array(leaf_pair_widths)

    grid = dict()

    grid["mlc"] = np.arange(
        -max_leaf_gap / 2, max_leaf_gap / 2 + grid_resolution, grid_resolution
    ).astype("float")

    _, top_of_reference_leaf = _determine_leaf_centres(leaf_pair_widths)
    grid_reference_position = _determine_reference_grid_position(
        top_of_reference_leaf, grid_resolution
    )

    # It might be better to use round instead of ceil here.
    total_leaf_widths = np.sum(leaf_pair_widths)
    top_grid_pos = (
        np.ceil((total_leaf_widths / 2 - grid_reference_position) / grid_resolution)
        * grid_resolution
        + grid_reference_position
    )

    bot_grid_pos = (
        grid_reference_position
        - np.ceil((total_leaf_widths / 2 + grid_reference_position) / grid_resolution)
        * grid_resolution
    )

    grid["jaw"] = np.arange(
        bot_grid_pos, top_grid_pos + grid_resolution, grid_resolution
    )

    return grid


def display_metersetmap_diff(
    grid, metersetmap_eval, metersetmap_ref, grid_resolution=None, colour_range=None
):
    cmap = "bwr"
    diff = metersetmap_eval - metersetmap_ref
    if colour_range is None:
        colour_range = np.max(np.abs(diff))

    # pylint: disable=invalid-unary-operand-type
    display_metersetmap(
        grid,
        diff,
        grid_resolution=grid_resolution,
        cmap=cmap,
        vmin=-colour_range,
        vmax=colour_range,
    )


def display_metersetmap(
    grid, metersetmap, grid_resolution=None, cmap=None, vmin=None, vmax=None
):
    """Prints a colour plot of the MetersetMap.

    Examples
    --------
    See :func:`pymedphys.metersetmap.calculate`.
    """
    if grid_resolution is None:
        grid_resolution = grid["mlc"][1] - grid["mlc"][0]

    x, y = pcolormesh_grid(grid["mlc"], grid["jaw"], grid_resolution)
    plt.pcolormesh(x, y, metersetmap, cmap=cmap, vmin=vmin, vmax=vmax)
    plt.colorbar()
    plt.title("MetersetMap")
    plt.xlabel("MLC direction (mm)")
    plt.ylabel("Jaw direction (mm)")
    plt.axis("equal")
    plt.gca().invert_yaxis()


def _calc_blocked_t(travel_diff, grid_resolution):
    blocked_t = np.ones_like(travel_diff) * np.nan

    fully_blocked = travel_diff <= -grid_resolution / 2
    fully_open = travel_diff >= grid_resolution / 2
    blocked_t[fully_blocked] = 1
    blocked_t[fully_open] = 0

    transient = ~fully_blocked & ~fully_open

    blocked_t[transient] = (
        -travel_diff[transient] + grid_resolution / 2
    ) / grid_resolution

    assert np.all(~np.isnan(blocked_t))

    return blocked_t


def _calc_time_steps(positions, grid_resolution, min_step_per_pixel):
    maximum_travel = []
    for _, value in positions.items():
        for _, (start, end) in value.items():
            maximum_travel.append(np.max(np.abs(end - start)))

    maximum_travel = np.max(maximum_travel)
    number_of_pixels = np.ceil(maximum_travel / grid_resolution)
    time_steps = number_of_pixels * min_step_per_pixel

    if time_steps < 10:
        time_steps = 10

    return time_steps


def _calc_blocked_by_device(grid, positions, grid_resolution, time_steps):
    blocked_by_device = {}

    for device, value in positions.items():
        blocked_by_device[device] = dict()

        for multiplier, (start, end) in value.items():
            dt = (end - start) / (time_steps - 1)
            travel = start[None, :] + np.arange(0, time_steps)[:, None] * dt[None, :]
            travel_diff = multiplier * (
                grid[device][None, None, :] - travel[:, :, None]
            )

            blocked_by_device[device][multiplier] = _calc_blocked_t(
                travel_diff, grid_resolution
            )

    return blocked_by_device


def _calc_device_open(blocked_by_device):
    device_open = {}

    for device, value in blocked_by_device.items():
        device_sum = np.sum(
            np.concatenate(
                [np.expand_dims(blocked, axis=0) for _, blocked in value.items()],
                axis=0,
            ),
            axis=0,
        )

        device_open[device] = 1 - device_sum

    return device_open


def _remap_mlc_and_jaw(device_open, grid_leaf_map):
    mlc_open = device_open["mlc"][:, grid_leaf_map, :]
    jaw_open = device_open["jaw"][:, 0, :]

    return mlc_open, jaw_open


def _calc_open_fraction(mlc_open, jaw_open):
    open_t = mlc_open * jaw_open[:, :, None]
    open_fraction = np.mean(open_t, axis=0)

    return open_fraction


def _determine_leaf_centres(leaf_pair_widths):
    total_leaf_widths = np.sum(leaf_pair_widths)
    leaf_centres = (
        np.cumsum(leaf_pair_widths) - leaf_pair_widths / 2 - total_leaf_widths / 2
    )

    reference_leaf_index = len(leaf_centres) // 2

    top_of_reference_leaf = (
        leaf_centres[reference_leaf_index] + leaf_pair_widths[reference_leaf_index] / 2
    )

    return leaf_centres, top_of_reference_leaf


def _determine_reference_grid_position(top_of_reference_leaf, grid_resolution):
    grid_reference_position = top_of_reference_leaf - grid_resolution / 2

    return grid_reference_position


def _determine_calc_grid_and_adjustments(mlc, jaw, leaf_pair_widths, grid_resolution):
    mlc = np.array(mlc, copy=False)
    jaw = np.array(jaw, copy=False)

    min_y = np.min(-jaw[:, 0])
    max_y = np.max(jaw[:, 1])

    leaf_centres, top_of_reference_leaf = _determine_leaf_centres(leaf_pair_widths)
    grid_reference_position = _determine_reference_grid_position(
        top_of_reference_leaf, grid_resolution
    )

    top_grid_pos = (
        np.round((max_y - grid_reference_position) / grid_resolution)
    ) * grid_resolution + grid_reference_position

    bot_grid_pos = (
        grid_reference_position
        - (np.round((-min_y + grid_reference_position) / grid_resolution))
        * grid_resolution
    )

    grid = dict()
    grid["jaw"] = np.arange(
        bot_grid_pos, top_grid_pos + grid_resolution, grid_resolution
    ).astype("float")

    grid_leaf_map = np.argmin(
        np.abs(grid["jaw"][:, None] - leaf_centres[None, :]), axis=1
    )

    adjusted_grid_leaf_map = grid_leaf_map - np.min(grid_leaf_map)

    leaves_to_be_calced = np.unique(grid_leaf_map)
    adjusted_mlc = mlc[:, leaves_to_be_calced, :]

    min_x = np.round(np.min(-adjusted_mlc[:, :, 0]) / grid_resolution) * grid_resolution
    max_x = np.round(np.max(adjusted_mlc[:, :, 1]) / grid_resolution) * grid_resolution

    grid["mlc"] = np.arange(min_x, max_x + grid_resolution, grid_resolution).astype(
        "float"
    )

    return grid, adjusted_grid_leaf_map, adjusted_mlc


def _convert_to_full_grid(grid, full_grid, metersetmap):
    grid_xx, grid_yy = np.meshgrid(grid["mlc"], grid["jaw"])
    full_grid_xx, full_grid_yy = np.meshgrid(full_grid["mlc"], full_grid["jaw"])

    xx_from, xx_to = np.where(
        np.abs(full_grid_xx[None, 0, :] - grid_xx[0, :, None]) < 0.0001
    )
    yy_from, yy_to = np.where(
        np.abs(full_grid_yy[None, :, 0] - grid_yy[:, 0, None]) < 0.0001
    )

    full_grid_metersetmap = np.zeros_like(full_grid_xx)
    full_grid_metersetmap[  # pylint: disable=unsupported-assignment-operation
        np.ix_(yy_to, xx_to)
    ] = metersetmap[np.ix_(yy_from, xx_from)]

    return full_grid_metersetmap
