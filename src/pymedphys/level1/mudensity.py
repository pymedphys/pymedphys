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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


# pylint: disable=C0103,C1801

import numpy as np
import matplotlib.pyplot as plt


AGILITY_LEAF_PAIR_WIDTHS = (
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5
)


def calc_mu_density(mu, mlc, jaw, grid_resolution=1, max_leaf_gap=400,
                    leaf_pair_widths=AGILITY_LEAF_PAIR_WIDTHS, time_steps=50):
    """Determine the MU Density.

    Examples:
        Calculating the MU Density from a Mosaiq Field ID.

        >>> from pymedphys.level1.mudensity import (
                calc_mu_density, get_grid, display_mu_density)

        >>> from pymedphys.level1.msqconnect import mosaiq_connect
        >>> from pymedphys.level2.msqdelivery import (
                multi_fetch_and_verify_mosaiq)

        >>> field_id = 0  # provide a mosaiq field id here
        >>> msq_server_name = 'a_name'

        >>> with mosaiq_connect(msq_server_name) as cursor:
                delivery_data = multi_fetch_and_verify_mosaiq(cursor, field_id)

        >>> mu = delivery_data.monitor_units
        >>> mlc = delivery_data.mlc
        >>> jaw = delivery_data.jaw

        >>> grid = get_grid()
        >>> mu_density = calc_mu_density(mu, mlc, jaw)
        >>> display_mu_density(grid, mu_density)


        Calculating the MU Density given the filepath of a logfile.

        >>> from pymedphys.level1.mudensity import (
                calc_mu_density, get_grid, display_mu_density)

        >>> from pymedphys.level2.trfdecode import (
                delivery_data_from_logfile)

        >>> filepath = r"a/path/goes/here"
        >>> delivery_data = delivery_data_from_logfile(filepath)

        >>> mu = delivery_data.monitor_units
        >>> mlc = delivery_data.mlc
        >>> jaw = delivery_data.jaw

        >>> grid = get_grid()
        >>> mu_density = calc_mu_density(mu, mlc, jaw)
        >>> display_mu_density(grid, mu_density)
    """
    leaf_pair_widths = np.array(leaf_pair_widths)

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
            time_steps=time_steps)
        full_grid_mu_density_of_slice = _convert_to_full_grid(
            grid, full_grid, mu_density_of_slice)

        mu_density += full_grid_mu_density_of_slice

    return mu_density


def calc_single_control_point(mlc, jaw, delivered_mu=1,
                              leaf_pair_widths=AGILITY_LEAF_PAIR_WIDTHS,
                              grid_resolution=1, time_steps=50):
    """Calculate the MU Density for a single control point.

    Example:
        >>> from pymedphys.level1.mudensity import (
                calc_single_control_point, display_mu_density)

        >>> leaf_pair_widths = [2, 2]
        >>> mlc = np.array([
                [
                    [1, 1],
                    [2, 2],
                ],
                [
                    [2, 2],
                    [3, 3],
                ]
            ])
        >>> jaw = np.array([
                [1.5, 1.2],
                [1.5, 1.2]
            ])
        >>> grid, mu_density = calc_single_control_point(
                mlc, jaw, leaf_pair_widths=leaf_pair_widths)
        >>> display_mu_density(grid, mu_density)
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

    blocked_by_device = _calc_blocked_by_device(
        grid, positions, grid_resolution, time_steps)
    device_open = _calc_device_open(blocked_by_device)
    mlc_open, jaw_open = _remap_mlc_and_jaw(device_open, grid_leaf_map)
    open_fraction = _calc_open_fraction(mlc_open, jaw_open)

    mu_density = open_fraction * delivered_mu

    return grid, mu_density


def single_mlc_pair(left_mlc, right_mlc, grid_resolution=1, time_steps=50):
    """Calculate the MU Density of a single leaf pair.

    Example:
        >>> import matplotlib.pyplot as plt

        >>> mlc_left = (-2.3, 3.1)  # (start position, end position)
        >>> mlc_right = (0, 7.7)

        >>> x, mu_density = single_mlc_pair(mlc_left, mlc_right)
        >>> plt.plot(x, mu_density, '-o')
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
        grid_resolution=grid_resolution, time_steps=time_steps
    )

    return grid['mlc'], mu_density[0, :]


def calc_mu_density_return_grid(mu, mlc, jaw, grid_resolution=1,
                                max_leaf_gap=400,
                                leaf_pair_widths=AGILITY_LEAF_PAIR_WIDTHS,
                                time_steps=50):
    """DEPRECATED. This is a temporary helper function to provide the old
    api.
    """
    leaf_pair_widths = np.array(leaf_pair_widths)
    mu_density = calc_mu_density(
        mu, mlc, jaw, grid_resolution=grid_resolution,
        max_leaf_gap=max_leaf_gap, leaf_pair_widths=leaf_pair_widths,
        time_steps=time_steps)

    full_grid = get_grid(
        max_leaf_gap, grid_resolution, leaf_pair_widths)

    grid_xx, grid_yy = np.meshgrid(full_grid['mlc'], full_grid['jaw'])

    return grid_xx, grid_yy, mu_density


def get_grid(max_leaf_gap=400, grid_resolution=1,
             leaf_pair_widths=AGILITY_LEAF_PAIR_WIDTHS):
    """Get the MU Density grid for plotting purposes.

    Example:
        See `calc_mu_density`.
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

    Example:
        See `calc_mu_density`.
    """
    if grid_resolution is None:
        grid_resolution = grid['mlc'][1] - grid['mlc'][0]

    x, y = _colormesh_grid(grid['mlc'], grid['jaw'], grid_resolution)
    plt.pcolormesh(x, y, mu_density)
    plt.colorbar()
    plt.title('MU density')
    plt.xlabel('MLC direction (mm)')
    plt.ylabel('Jaw direction (mm)')
    plt.axis('equal')
    plt.gca().invert_yaxis()


def _colormesh_grid(x, y, grid_resolution):
    new_x = np.concatenate(
        [x - grid_resolution/2, [x[-1] + grid_resolution/2]])
    new_y = np.concatenate(
        [y - grid_resolution/2, [y[-1] + grid_resolution/2]])

    return new_x, new_y


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


def _calc_blocked_by_device(grid, positions, grid_resolution, time_steps):
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
