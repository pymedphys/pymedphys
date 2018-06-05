# Copyright (C) 2018 CCA Health Care

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


import psutil
import numpy as np


AGILITY_LEAF_PAIR_WIDTHS = [
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5
]


def calc_a_single_blocked_fraction(start_diffs, end_diffs,
                                   start_blocked, end_blocked):
    blocked_fraction = np.ones(np.shape(start_diffs)) * np.nan
    all_open = ~start_blocked & ~end_blocked
    blocked_fraction[all_open] = 0

    all_blocked = start_blocked & end_blocked
    blocked_fraction[all_blocked] = 1

    start_blocked_fraction = np.copy(blocked_fraction)
    end_blocked_fraction = np.copy(blocked_fraction)

    partial_blocked = start_blocked != end_blocked
    travel = np.abs(
        start_diffs[partial_blocked] -
        end_diffs[partial_blocked])

    start_partial_blocked_ref = start_blocked[partial_blocked]
    end_partial_blocked_ref = end_blocked[partial_blocked]

    start_blocked_fraction[partial_blocked & start_blocked] = np.abs(
        start_diffs[partial_blocked][start_partial_blocked_ref] /
        travel[start_partial_blocked_ref]
    )
    start_blocked_fraction[partial_blocked & end_blocked] = 0

    end_blocked_fraction[partial_blocked & end_blocked] = np.abs(
        end_diffs[partial_blocked][end_partial_blocked_ref] /
        travel[end_partial_blocked_ref]
    )
    end_blocked_fraction[partial_blocked & start_blocked] = 0

    assert np.all(~np.isnan(start_blocked_fraction))
    assert np.all(~np.isnan(end_blocked_fraction))

    return start_blocked_fraction, end_blocked_fraction


def calc_leaf_blocked_fractions(leaf_xx, mlc):
    start_left_diffs = leaf_xx - -mlc[0:-1, :, 0][:, :, None]
    end_left_diffs = leaf_xx - -mlc[1::, :, 0][:, :, None]

    start_left_blocked = start_left_diffs <= 0
    end_left_blocked = end_left_diffs <= 0

    (
        start_left_blocked_fraction, end_left_blocked_fraction
    ) = calc_a_single_blocked_fraction(
        start_left_diffs, end_left_diffs,
        start_left_blocked, end_left_blocked)

    start_right_diffs = leaf_xx - mlc[0:-1, :, 1][:, :, None]
    end_right_diffs = leaf_xx - mlc[1::, :, 1][:, :, None]

    start_right_blocked = start_right_diffs >= 0
    end_right_blocked = end_right_diffs >= 0

    (
        start_right_blocked_fraction, end_right_blocked_fraction
    ) = calc_a_single_blocked_fraction(
        start_right_diffs, end_right_diffs,
        start_right_blocked, end_right_blocked)

    return {
        'start_left_blocked_fraction': start_left_blocked_fraction,
        'end_left_blocked_fraction': end_left_blocked_fraction,
        'start_right_blocked_fraction': start_right_blocked_fraction,
        'end_right_blocked_fraction': end_right_blocked_fraction
    }


def calc_jaw_blocked_fraction(grid_y, jaw, repeats):
    start_top_diffs = grid_y - jaw[0:-1, 1][:, None]
    end_top_diffs = grid_y - jaw[1::, 1][:, None]

    start_top_blocked = start_top_diffs >= 0
    end_top_blocked = end_top_diffs >= 0

    (
        start_top_blocked_fraction, end_top_blocked_fraction
    ) = calc_a_single_blocked_fraction(
        start_top_diffs, end_top_diffs,
        start_top_blocked, end_top_blocked)

    start_bottom_diffs = grid_y - -jaw[0:-1, 0][:, None]
    end_bottom_diffs = grid_y - -jaw[1::, 0][:, None]

    start_bottom_blocked = start_bottom_diffs <= 0
    end_bottom_blocked = end_bottom_diffs <= 0

    (
        start_bottom_blocked_fraction, end_bottom_blocked_fraction
    ) = calc_a_single_blocked_fraction(
        start_bottom_diffs, end_bottom_diffs,
        start_bottom_blocked, end_bottom_blocked)

    return {
        'start_top_blocked_fraction': np.repeat(
            start_top_blocked_fraction[:, :, None], repeats, axis=2),
        'end_top_blocked_fraction': np.repeat(
            end_top_blocked_fraction[:, :, None], repeats, axis=2),
        'start_bottom_blocked_fraction': np.repeat(
            start_bottom_blocked_fraction[:, :, None], repeats, axis=2),
        'end_bottom_blocked_fraction': np.repeat(
            end_bottom_blocked_fraction[:, :, None], repeats, axis=2)
    }


def determine_leaves_to_be_calced(grid_yy, grid_leaf_map, jaw):
    calc_top = np.invert(grid_yy[:, 0] >= np.max(jaw[:, 1]))
    top_leaves_calc = np.unique(grid_leaf_map[calc_top])

    calc_bot = np.invert(grid_yy[:, 0] <= np.min(-jaw[:, 0]))
    bot_leaves_calc = np.unique(grid_leaf_map[calc_bot])

    leaves_to_be_calced = np.intersect1d(top_leaves_calc, bot_leaves_calc)

    return leaves_to_be_calced


def determine_x_pos_to_be_calced(leaf_xx, mlc):
    leaf_x = leaf_xx[0, :]
    calc_left = np.invert(leaf_x <= np.min(-mlc[:, :, 0]))
    calc_right = np.invert(leaf_x >= np.max(mlc[:, :, 1]))

    x_pos_to_be_calced = calc_left & calc_right

    return x_pos_to_be_calced


def calc_blocked_fraction(leaf_xx, mlc, grid_leaf_map,
                          grid_yy, jaw):

    virtual_memory_start = psutil.virtual_memory()

    leaf_blocked_fractions = calc_leaf_blocked_fraction_define_subset(
        leaf_xx, grid_yy, mlc, grid_leaf_map)

    jaw_blocked_fractions = calc_jaw_blocked_fraction(
        grid_yy[:, 0], jaw, len(leaf_xx[0, :]))

    all_start_blocked_fractions = np.concatenate([
        np.expand_dims(
            leaf_blocked_fractions['start_left_blocked_fraction'], axis=0),
        np.expand_dims(
            leaf_blocked_fractions['start_right_blocked_fraction'], axis=0),
        np.expand_dims(
            jaw_blocked_fractions['start_top_blocked_fraction'], axis=0),
        np.expand_dims(
            jaw_blocked_fractions['start_bottom_blocked_fraction'], axis=0)
    ], axis=0)

    start_blocked_fraction = np.max(all_start_blocked_fractions, axis=0)

    all_end_blocked_fractions = np.concatenate([
        np.expand_dims(
            leaf_blocked_fractions['end_left_blocked_fraction'], axis=0),
        np.expand_dims(
            leaf_blocked_fractions['end_right_blocked_fraction'], axis=0),
        np.expand_dims(
            jaw_blocked_fractions['end_top_blocked_fraction'], axis=0),
        np.expand_dims(
            jaw_blocked_fractions['end_bottom_blocked_fraction'], axis=0)
    ], axis=0)

    end_blocked_fraction = np.max(all_end_blocked_fractions, axis=0)

    blocked_fraction = start_blocked_fraction + end_blocked_fraction
    blocked_fraction[blocked_fraction > 1] = 1

    virtual_memory_end = psutil.virtual_memory()
    ram_used = virtual_memory_end.used - virtual_memory_start.used

    return blocked_fraction, ram_used


def calc_mu_density_over_slice(mu, mlc, jaw, slice_to_check,
                               grid_xx, grid_yy, leaf_xx, grid_leaf_map):

    blocked_fraction, ram_used = calc_blocked_fraction(
        leaf_xx, mlc[slice_to_check, :, :], grid_leaf_map,
        grid_yy, jaw[slice_to_check, :])

    mu_density = np.sum(
        np.diff(mu[slice_to_check])[:, None, None] *
        (1 - blocked_fraction), axis=0)

    return mu_density, ram_used


def calc_max_index(current_index, number_of_sections, final_index):
    max_index = current_index + number_of_sections + 1
    if max_index > final_index:
        max_index = final_index

    return max_index


def calc_leaf_blocked_fraction_define_subset(leaf_xx, grid_yy, mlc,
                                             grid_leaf_map):
    leaf_blocked_fractions = calc_leaf_blocked_fractions(leaf_xx, mlc)

    for key in leaf_blocked_fractions.keys():
        leaf_blocked_fractions[key] = (
            leaf_blocked_fractions[key][:, grid_leaf_map, :])

    return leaf_blocked_fractions


def determine_leaf_y(leaf_pair_widths):
    total_leaf_widths = np.sum(leaf_pair_widths)
    leaf_y = (
        np.cumsum(leaf_pair_widths) -
        leaf_pair_widths/2 - total_leaf_widths/2)

    return leaf_y


def determine_full_grid(max_leaf_gap, grid_resolution, leaf_pair_widths):
    leaf_x = np.arange(
        -max_leaf_gap/2,
        max_leaf_gap/2 + grid_resolution,
        grid_resolution).astype('float')

    leaf_y = determine_leaf_y(leaf_pair_widths)

    initial_leaf_grid_y_pos = leaf_y[len(leaf_y)//2]

    total_leaf_widths = np.sum(leaf_pair_widths)
    top_grid_pos = (
        (total_leaf_widths/2 - initial_leaf_grid_y_pos) // grid_resolution *
        grid_resolution + initial_leaf_grid_y_pos)

    bot_grid_pos = (
        initial_leaf_grid_y_pos -
        (total_leaf_widths/2 + initial_leaf_grid_y_pos) // grid_resolution *
        grid_resolution)

    grid_y = np.arange(
        bot_grid_pos, top_grid_pos + grid_resolution, grid_resolution)

    grid_xx, grid_yy = np.meshgrid(leaf_x, grid_y)

    return grid_xx, grid_yy


def determine_calc_grid_and_adjustments(mlc, jaw, leaf_pair_widths,
                                        grid_resolution):
    min_x = np.floor(np.min(-mlc[:, :, 0]) / grid_resolution) * grid_resolution
    max_x = np.ceil(np.max(mlc[:, :, 1]) / grid_resolution) * grid_resolution

    min_y = np.min(-jaw[:, 0])
    max_y = np.max(jaw[:, 1])

    leaf_x = np.arange(
        min_x, max_x + grid_resolution, grid_resolution
    ).astype('float')

    leaf_y = determine_leaf_y(leaf_pair_widths)

    leaf_xx, _ = np.meshgrid(leaf_x, leaf_y)

    initial_leaf_grid_y_pos = leaf_y[len(leaf_y)//2]

    top_grid_pos = (
        (max_y - initial_leaf_grid_y_pos) // grid_resolution *
        grid_resolution + initial_leaf_grid_y_pos)

    bot_grid_pos = (
        initial_leaf_grid_y_pos -
        (-min_y + initial_leaf_grid_y_pos) // grid_resolution *
        grid_resolution)

    grid_y = np.arange(
        bot_grid_pos, top_grid_pos + grid_resolution, grid_resolution)

    grid_leaf_map = np.argmin(
        np.abs(grid_y[:, None] - leaf_y[None, :]), axis=1)

    grid_xx, grid_yy = np.meshgrid(leaf_x, grid_y)
    adjusted_grid_leaf_map = grid_leaf_map - np.min(grid_leaf_map)

    leaves_to_be_calced = np.unique(grid_leaf_map)
    adjusted_mlc = mlc[:, leaves_to_be_calced, :]
    adjusted_leaf_xx = leaf_xx[leaves_to_be_calced, :]

    return (
        grid_xx, grid_yy,
        adjusted_grid_leaf_map, adjusted_mlc, adjusted_leaf_xx)


def remove_irrelevant_control_points(mu, mlc, jaw):
    mu_diff = np.diff(mu)
    no_change = mu_diff == 0
    no_change_before = no_change[0:-1]
    no_change_after = no_change[1::]

    no_change_before_and_after = no_change_before & no_change_after
    irrelevant_control_point = np.hstack(
        [no_change[0], no_change_before_and_after, no_change[-1]])
    control_points_to_use = np.invert(irrelevant_control_point)

    mu = mu[control_points_to_use]
    mlc = mlc[control_points_to_use, :, :]
    jaw = jaw[control_points_to_use, :]

    return mu, mlc, jaw


def calc_mu_density(mu, mlc, jaw, grid_resolution=1, max_leaf_gap=400,
                    leaf_pair_widths=AGILITY_LEAF_PAIR_WIDTHS,
                    ram_fraction=0.8):
    leaf_pair_widths = np.array(leaf_pair_widths)
    min_number_of_sections = 20

    number_of_sections = min_number_of_sections
    current_index = 0

    mu, mlc, jaw = remove_irrelevant_control_points(mu, mlc, jaw)

    (
        grid_xx, grid_yy, adjusted_grid_leaf_map, adjusted_mlc,
        adjusted_leaf_xx
    ) = determine_calc_grid_and_adjustments(
        mlc, jaw, leaf_pair_widths, grid_resolution)

    final_index = len(mu)
    max_index = 0

    mu_density = np.zeros_like(grid_xx)

    while max_index < final_index:
        max_index = calc_max_index(
            current_index, number_of_sections, final_index)

        slice_to_check = slice(current_index, max_index, 1)
        mu_density_of_slice, ram_used = calc_mu_density_over_slice(
            mu, adjusted_mlc, jaw, slice_to_check,
            grid_xx, grid_yy, adjusted_leaf_xx, adjusted_grid_leaf_map)
        mu_density += mu_density_of_slice

        current_index = current_index + number_of_sections

        current_ram_fraction = ram_used / psutil.virtual_memory().available
        if current_ram_fraction != 0:
            number_of_sections = number_of_sections * int(
                np.floor(ram_fraction / current_ram_fraction))

            if number_of_sections < min_number_of_sections:
                number_of_sections = min_number_of_sections

    full_grid_xx, full_grid_yy = determine_full_grid(
        max_leaf_gap, grid_resolution, leaf_pair_widths)

    xx_from, xx_to = np.where(
        np.abs(full_grid_xx[None, 0, :] - grid_xx[0, :, None]) < 0.0001)
    yy_from, yy_to = np.where(
        np.abs(full_grid_yy[None, :, 0] - grid_yy[:, 0, None]) < 0.0001)

    full_grid_mu_density = np.zeros_like(full_grid_xx)
    full_grid_mu_density[np.ix_(yy_to, xx_to)] = (
        mu_density[np.ix_(yy_from, xx_from)])

    return full_grid_xx, full_grid_yy, full_grid_mu_density
