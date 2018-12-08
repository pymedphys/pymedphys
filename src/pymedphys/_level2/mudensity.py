# Copyright (C) 2018 Simon Biggs

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

"""Calculate the MU Density given mu, mlc, and jaw control points.

.. WARNING::
   Although this is a useful tool in the toolbox for patient specific IMRT QA,
   in and of itself it is not a sufficient stand in replacement. This tool does
   not verify that the reported dose within the treatment planning system is
   delivered by the Linac.

   Deficiencies or limitations in the agreement between the treatment planning
   system's beam model and the Linac delivery will not be able to be
   highlighted by this tool. An example might be an overly modulated beam with
   many thin sweeping strips, the Linac may deliver those control points with
   positional accuracy but if the beam model in the TPS cannot sufficiently
   accurately model the dose effects of those MLC control points the dose
   delivery will not sufficiently agree with the treatment plan. In this case
   however, this tool will say everything is in agreement.

   It also may be the case that due to a hardware or calibration fault the
   Linac itself may be incorrectly reporting its MLC and/or Jaw postions. In
   this case the logfile record can agree exactly with the planned positions
   while the true real world positions be in significant deviation.

   The impact of these issues may be able to be limited by including with this
   tool an automated independent IMRT 3-D dose calculation tool as well as a
   daily automated MLC/jaw logfile to EPI to baseline agreement test that
   moves the EPI so as to measure the full set of leaf pairs and the full range
   of MLC and Jaw travel.
"""


# pylint: disable=C0103,C1801

import numpy as np
import matplotlib.pyplot as plt

from .._level1.plthelpers import pcolormesh_grid

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


__AGILITY_LEAF_PAIR_WIDTHS = (5,) * 80

__DEFAULT_GRID_RESOLUTION = 1
__DEFAULT_MAX_LEAF_GAP = 400
__DEFAULT_MIN_STEP_PER_PIXEL = 10


def calc_mu_density(mu, mlc, jaw, grid_resolution=__DEFAULT_GRID_RESOLUTION,
                    max_leaf_gap=__DEFAULT_MAX_LEAF_GAP,
                    leaf_pair_widths=__AGILITY_LEAF_PAIR_WIDTHS,
                    min_step_per_pixel=__DEFAULT_MIN_STEP_PER_PIXEL):
    """Determine the MU Density.

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
    mu_density : numpy.ndarray
        2-D array containing the calculated mu density.

            | axis 0: jaw direction
            | axis 1: mlc direction

    Examples
    --------
    >>> import numpy as np
    >>>
    >>> from pymedphys.mudensity import (
    ...     calc_mu_density, get_grid, display_mu_density)
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
    >>> grid = get_grid(
    ...    max_leaf_gap=max_leaf_gap, leaf_pair_widths=leaf_pair_widths)
    >>> grid['mlc']
    array([-5., -4., -3., -2., -1.,  0.,  1.,  2.,  3.,  4.,  5.])
    >>>
    >>> grid['jaw']
    array([-8., -7., -6., -5., -4., -3., -2., -1.,  0.,  1.,  2.,  3.,  4.,
            5.,  6.,  7.,  8.])
    >>>
    >>> mu_density = calc_mu_density(
    ...    mu, mlc, jaw, max_leaf_gap=max_leaf_gap,
    ...    leaf_pair_widths=leaf_pair_widths)
    >>> display_mu_density(grid, mu_density)
    >>>
    >>> np.round(mu_density, 1)
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


    MU Density from a Mosaiq record

    >>> from pymedphys.mudensity import (
    ...     calc_mu_density, get_grid, display_mu_density)
    >>>
    >>> from pymedphys.msq import (
    ...     mosaiq_connect, multi_fetch_and_verify_mosaiq)
    >>>
    >>> def mu_density_from_mosaiq(msq_server_name, field_id):
    ...     with mosaiq_connect(msq_server_name) as cursor:
    ...         delivery_data = multi_fetch_and_verify_mosaiq(
    ...             cursor, field_id)
    ...
    ...
    ...     mu = delivery_data.monitor_units
    ...     mlc = delivery_data.mlc
    ...     jaw = delivery_data.jaw
    ...
    ...     grid = get_grid()
    ...     mu_density = calc_mu_density(mu, mlc, jaw)
    ...     display_mu_density(grid, mu_density)
    >>>
    >>> mu_density_from_mosaiq('a_server_name', 11111) # doctest: +SKIP


    MU Density from a logfile at a given filepath

    >>> from pymedphys.mudensity import (
    ...     calc_mu_density, get_grid, display_mu_density)
    >>>
    >>> from pymedphys.trf import delivery_data_from_logfile
    >>>
    >>> def mu_density_from_logfile(filepath):
    ...     delivery_data = delivery_data_from_logfile(filepath)
    ...
    ...     mu = delivery_data.monitor_units
    ...     mlc = delivery_data.mlc
    ...     jaw = delivery_data.jaw
    ...
    ...     grid = get_grid()
    ...     mu_density = calc_mu_density(mu, mlc, jaw)
    ...     display_mu_density(grid, mu_density)
    >>>
    >>> mu_density_from_logfile(r"a/path/goes/here") # doctest: +SKIP

    """
    leaf_pair_widths = np.array(leaf_pair_widths)

    assert np.max(np.abs(mlc)) <= max_leaf_gap / 2, (
        "The mlc should not travel further out than half the maximum leaf "
        "gap."
    )

    mu, mlc, jaw = _remove_irrelevant_control_points(mu, mlc, jaw)

    full_grid = get_grid(
        max_leaf_gap, grid_resolution, leaf_pair_widths)

    mu_density = np.zeros((len(full_grid['jaw']), len(full_grid['mlc'])))

    for i in range(len(mu) - 1):
        control_point_slice = slice(i, i + 2, 1)
        current_mlc = mlc[control_point_slice, :, :]
        current_jaw = jaw[control_point_slice, :]
        delivered_mu = np.diff(mu[control_point_slice])

        grid, mu_density_of_slice = calc_single_control_point(
            current_mlc, current_jaw, delivered_mu,
            leaf_pair_widths=leaf_pair_widths, grid_resolution=grid_resolution,
            min_step_per_pixel=min_step_per_pixel)
        full_grid_mu_density_of_slice = _convert_to_full_grid(
            grid, full_grid, mu_density_of_slice)

        mu_density += full_grid_mu_density_of_slice

    return mu_density


def calc_single_control_point(mlc, jaw, delivered_mu=1,
                              leaf_pair_widths=__AGILITY_LEAF_PAIR_WIDTHS,
                              grid_resolution=__DEFAULT_GRID_RESOLUTION,
                              min_step_per_pixel=__DEFAULT_MIN_STEP_PER_PIXEL):
    """Calculate the MU Density for a single control point.

    Examples
    --------
    >>> import numpy as np
    >>> from pymedphys.mudensity import (
    ...     calc_single_control_point, display_mu_density)
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
    >>> grid, mu_density = calc_single_control_point(
    ...     mlc, jaw, leaf_pair_widths=leaf_pair_widths)
    >>> display_mu_density(grid, mu_density)
    >>>
    >>> grid['mlc']
    array([-3., -2., -1.,  0.,  1.,  2.,  3.])
    >>>
    >>> grid['jaw']
    array([-1.5, -0.5,  0.5,  1.5])
    >>>
    >>> np.round(mu_density, 2)
    array([[0.  , 0.07, 0.43, 0.5 , 0.43, 0.07, 0.  ],
           [0.  , 0.14, 0.86, 1.  , 0.86, 0.14, 0.  ],
           [0.14, 0.86, 1.  , 1.  , 1.  , 0.86, 0.14],
           [0.03, 0.17, 0.2 , 0.2 , 0.2 , 0.17, 0.03]])
    """
    leaf_pair_widths = np.array(leaf_pair_widths)
    leaf_division = leaf_pair_widths / grid_resolution
    assert np.all(leaf_division.astype(int) == leaf_division), (
        "The grid resolution needs to exactly divide every leaf pair width."
    )
    assert np.max(np.abs(jaw)) <= np.sum(leaf_pair_widths) / 2, (
        "The jaw should not travel further out than the maximum leaf limits."
    )

    (
        grid, grid_leaf_map, mlc
    ) = _determine_calc_grid_and_adjustments(
        mlc, jaw,
        leaf_pair_widths, grid_resolution)

    positions = {
        'mlc': {
            1: (-mlc[0, :, 0], -mlc[1, :, 0]),  # left
            -1: (mlc[0, :, 1], mlc[1, :, 1])  # right
        },
        'jaw': {
            1: (-jaw[0::-1, 0], -jaw[1::, 0]),  # bot
            -1: (jaw[0::-1, 1], jaw[1::, 1])  # top
        }
    }

    time_steps = _calc_time_steps(
        positions, grid_resolution, min_step_per_pixel)
    blocked_by_device = _calc_blocked_by_device(
        grid, positions, grid_resolution, time_steps)
    device_open = _calc_device_open(blocked_by_device)
    mlc_open, jaw_open = _remap_mlc_and_jaw(device_open, grid_leaf_map)
    open_fraction = _calc_open_fraction(mlc_open, jaw_open)

    mu_density = open_fraction * delivered_mu

    return grid, mu_density


def single_mlc_pair(left_mlc, right_mlc,
                    grid_resolution=__DEFAULT_GRID_RESOLUTION,
                    min_step_per_pixel=__DEFAULT_MIN_STEP_PER_PIXEL):
    """Calculate the MU Density of a single leaf pair.

    Examples
    --------
    >>> import numpy as np
    >>> import matplotlib.pyplot as plt
    >>>
    >>> from pymedphys.mudensity import single_mlc_pair
    >>>
    >>> mlc_left = (-2.3, 3.1)  # (start position, end position)
    >>> mlc_right = (0, 7.7)
    >>>
    >>> x, mu_density = single_mlc_pair(mlc_left, mlc_right)
    >>> fig = plt.plot(x, mu_density, '-o')
    >>>
    >>> x
    array([-2., -1.,  0.,  1.,  2.,  3.,  4.,  5.,  6.,  7.,  8.])
    >>>
    >>> np.round(mu_density, 3)
    array([0.064, 0.244, 0.408, 0.475, 0.53 , 0.572, 0.481, 0.352, 0.224,
           0.096, 0.004])
    """
    leaf_pair_widths = [grid_resolution]
    jaw = np.array([
        [grid_resolution/2, grid_resolution/2],
        [grid_resolution/2, grid_resolution/2]
    ])
    mlc = np.array([
        [
            [-left_mlc[0], right_mlc[0]],
        ],
        [
            [-left_mlc[1], right_mlc[1]],
        ]
    ])

    grid, mu_density = calc_single_control_point(
        mlc, jaw, leaf_pair_widths=leaf_pair_widths,
        grid_resolution=grid_resolution, min_step_per_pixel=min_step_per_pixel
    )

    return grid['mlc'], mu_density[0, :]


def calc_mu_density_return_grid(mu, mlc, jaw,
                                grid_resolution=__DEFAULT_GRID_RESOLUTION,
                                max_leaf_gap=__DEFAULT_MAX_LEAF_GAP,
                                leaf_pair_widths=__AGILITY_LEAF_PAIR_WIDTHS,
                                min_step_per_pixel=__DEFAULT_MIN_STEP_PER_PIXEL):
    """DEPRECATED. This is a temporary helper function to provide the old
    api.
    """
    leaf_pair_widths = np.array(leaf_pair_widths)
    mu_density = calc_mu_density(
        mu, mlc, jaw, grid_resolution=grid_resolution,
        max_leaf_gap=max_leaf_gap, leaf_pair_widths=leaf_pair_widths,
        min_step_per_pixel=min_step_per_pixel)

    full_grid = get_grid(
        max_leaf_gap, grid_resolution, leaf_pair_widths)

    grid_xx, grid_yy = np.meshgrid(full_grid['mlc'], full_grid['jaw'])

    return grid_xx, grid_yy, mu_density


def get_grid(max_leaf_gap=__DEFAULT_MAX_LEAF_GAP, grid_resolution=__DEFAULT_GRID_RESOLUTION,
             leaf_pair_widths=__AGILITY_LEAF_PAIR_WIDTHS):
    """Get the MU Density grid for plotting purposes.

    Examples
    --------
    See `pymedphys.mudensity.calc_mu_density`_.
    """
    leaf_pair_widths = np.array(leaf_pair_widths)

    grid = dict()

    grid['mlc'] = np.arange(
        -max_leaf_gap/2,
        max_leaf_gap/2 + grid_resolution,
        grid_resolution).astype('float')

    _, top_of_reference_leaf = _determine_leaf_centres(
        leaf_pair_widths)
    grid_reference_position = _determine_reference_grid_position(
        top_of_reference_leaf, grid_resolution)

    # It might be better to use round instead of ceil here.
    total_leaf_widths = np.sum(leaf_pair_widths)
    top_grid_pos = (
        np.ceil(
            (total_leaf_widths/2 - grid_reference_position)
            / grid_resolution) *
        grid_resolution + grid_reference_position)

    bot_grid_pos = (
        grid_reference_position -
        np.ceil(
            (total_leaf_widths/2 + grid_reference_position)
            / grid_resolution) *
        grid_resolution)

    grid['jaw'] = np.arange(
        bot_grid_pos, top_grid_pos + grid_resolution, grid_resolution)

    return grid


def find_relevant_control_points(mu):
    """Removes control points that will not contribute to the MU Density.
    """
    mu_diff = np.diff(mu)
    no_change = mu_diff == 0
    no_change_before = no_change[0:-1]
    no_change_after = no_change[1::]

    no_change_before_and_after = no_change_before & no_change_after
    irrelevant_control_point = np.hstack(
        [no_change[0], no_change_before_and_after, no_change[-1]])
    relevant_control_points = np.invert(irrelevant_control_point)

    return relevant_control_points


def display_mu_density(grid, mu_density, grid_resolution=None):
    """Prints a colour plot of the MU Density.

    Examples
    --------
    See `pymedphys.mudensity.calc_mu_density`_.
    """
    if grid_resolution is None:
        grid_resolution = grid['mlc'][1] - grid['mlc'][0]

    x, y = pcolormesh_grid(grid['mlc'], grid['jaw'], grid_resolution)
    plt.pcolormesh(x, y, mu_density)
    plt.colorbar()
    plt.title('MU density')
    plt.xlabel('MLC direction (mm)')
    plt.ylabel('Jaw direction (mm)')
    plt.axis('equal')
    plt.gca().invert_yaxis()


def _calc_blocked_t(travel_diff, grid_resolution):
    blocked_t = np.ones_like(travel_diff) * np.nan

    fully_blocked = travel_diff <= -grid_resolution/2
    fully_open = travel_diff >= grid_resolution/2
    blocked_t[fully_blocked] = 1
    blocked_t[fully_open] = 0

    transient = ~fully_blocked & ~fully_open

    blocked_t[transient] = (
        (-travel_diff[transient] + grid_resolution/2) /
        grid_resolution)

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


def _calc_blocked_by_device(grid, positions, grid_resolution,
                            time_steps):
    blocked_by_device = {}

    for device, value in positions.items():
        blocked_by_device[device] = dict()

        for multiplier, (start, end) in value.items():
            dt = (end - start) / (time_steps - 1)
            travel = (
                start[None, :] +
                np.arange(0, time_steps)[:, None] * dt[None, :])
            travel_diff = multiplier * (
                grid[device][None, None, :] - travel[:, :, None])

            blocked_by_device[device][multiplier] = _calc_blocked_t(
                travel_diff, grid_resolution)

    return blocked_by_device


def _calc_device_open(blocked_by_device):
    device_open = {}

    for device, value in blocked_by_device.items():
        device_sum = np.sum(np.concatenate([
            np.expand_dims(blocked, axis=0)
            for _, blocked in value.items()
        ], axis=0), axis=0)

        device_open[device] = 1 - device_sum

    return device_open


def _remap_mlc_and_jaw(device_open, grid_leaf_map):
    mlc_open = device_open['mlc'][:, grid_leaf_map, :]
    jaw_open = device_open['jaw'][:, 0, :]

    return mlc_open, jaw_open


def _calc_open_fraction(mlc_open, jaw_open):
    open_t = mlc_open * jaw_open[:, :, None]
    open_fraction = np.mean(open_t, axis=0)

    return open_fraction


def _determine_leaf_centres(leaf_pair_widths):
    total_leaf_widths = np.sum(leaf_pair_widths)
    leaf_centres = (
        np.cumsum(leaf_pair_widths) -
        leaf_pair_widths/2 - total_leaf_widths/2)

    reference_leaf_index = len(leaf_centres)//2

    top_of_reference_leaf = (
        leaf_centres[reference_leaf_index] +
        leaf_pair_widths[reference_leaf_index] / 2
    )

    return leaf_centres, top_of_reference_leaf


def _determine_reference_grid_position(top_of_reference_leaf, grid_resolution):
    grid_reference_position = top_of_reference_leaf - grid_resolution/2

    return grid_reference_position


def _determine_calc_grid_and_adjustments(mlc, jaw, leaf_pair_widths,
                                         grid_resolution):
    min_y = np.min(-jaw[:, 0])
    max_y = np.max(jaw[:, 1])

    leaf_centres, top_of_reference_leaf = _determine_leaf_centres(
        leaf_pair_widths)
    grid_reference_position = _determine_reference_grid_position(
        top_of_reference_leaf, grid_resolution)

    top_grid_pos = (
        (np.round((max_y - grid_reference_position) / grid_resolution)) *
        grid_resolution + grid_reference_position)

    bot_grid_pos = (
        grid_reference_position -
        (np.round((-min_y + grid_reference_position) / grid_resolution)) *
        grid_resolution)

    grid = dict()
    grid['jaw'] = np.arange(
        bot_grid_pos, top_grid_pos + grid_resolution, grid_resolution
    ).astype('float')

    grid_leaf_map = np.argmin(
        np.abs(grid['jaw'][:, None] - leaf_centres[None, :]), axis=1)

    adjusted_grid_leaf_map = grid_leaf_map - np.min(grid_leaf_map)

    leaves_to_be_calced = np.unique(grid_leaf_map)
    adjusted_mlc = mlc[:, leaves_to_be_calced, :]

    min_x = np.round(
        np.min(-adjusted_mlc[:, :, 0]) / grid_resolution) * grid_resolution
    max_x = np.round(
        np.max(adjusted_mlc[:, :, 1]) / grid_resolution) * grid_resolution

    grid['mlc'] = np.arange(
        min_x, max_x + grid_resolution, grid_resolution
    ).astype('float')

    return grid, adjusted_grid_leaf_map, adjusted_mlc


def _remove_irrelevant_control_points(mu, mlc, jaw):
    assert len(mu) > 0, "No control points found"

    mu = np.array(mu)
    mlc = np.array(mlc)
    jaw = np.array(jaw)

    control_points_to_use = find_relevant_control_points(mu)

    mu = mu[control_points_to_use]
    mlc = mlc[control_points_to_use, :, :]
    jaw = jaw[control_points_to_use, :]

    return mu, mlc, jaw


def _convert_to_full_grid(grid, full_grid, mu_density):
    grid_xx, grid_yy = np.meshgrid(grid['mlc'], grid['jaw'])
    full_grid_xx, full_grid_yy = np.meshgrid(
        full_grid['mlc'], full_grid['jaw'])

    xx_from, xx_to = np.where(
        np.abs(full_grid_xx[None, 0, :] - grid_xx[0, :, None]) < 0.0001)
    yy_from, yy_to = np.where(
        np.abs(full_grid_yy[None, :, 0] - grid_yy[:, 0, None]) < 0.0001)

    full_grid_mu_density = np.zeros_like(full_grid_xx)
    full_grid_mu_density[np.ix_(yy_to, xx_to)] = (
        mu_density[np.ix_(yy_from, xx_from)])

    return full_grid_mu_density
