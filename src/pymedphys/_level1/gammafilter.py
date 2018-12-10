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


"""Gamma filters that only calculate pass or fail for each evaluation point.
No interpolation is undergone with these at the moment. Interpolation is
planned for the future.
"""


import sys

import numpy as np

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def convert_to_percent_pass(gamma_array):
    valid_gamma = gamma_array[np.invert(np.isnan(gamma_array))]
    percent_pass = 100 * np.sum(valid_gamma < 1) / len(valid_gamma)

    return percent_pass


def gamma_filter_brute_force(coords_reference, dose_reference,
                             coords_evaluation, dose_evaluation,
                             distance_mm_threshold, dose_threshold,
                             lower_dose_cutoff=0, **kwargs):

    xx_ref, yy_ref, zz_ref = np.meshgrid(*coords_reference, indexing='ij')
    gamma_array = np.ones_like(dose_evaluation).astype(np.float) * np.nan

    mesh_index = np.meshgrid(*[
        np.arange(len(coord_eval))
        for coord_eval in coords_evaluation
    ])

    eval_index = np.reshape(np.array(mesh_index), (3, -1))
    run_index = np.arange(np.shape(eval_index)[1])
    np.random.shuffle(run_index)

    sys.stdout.write('    ')

    for counter, point_index in enumerate(run_index):
        i, j, k = eval_index[:, point_index]
        eval_x = coords_evaluation[0][i]
        eval_y = coords_evaluation[1][j]
        eval_z = coords_evaluation[2][k]

        if dose_evaluation[i, j, k] < lower_dose_cutoff:
            continue

        distance = np.sqrt(
            (xx_ref - eval_x)**2 +
            (yy_ref - eval_y)**2 +
            (zz_ref - eval_z)**2
        )

        dose_diff = dose_evaluation[i, j, k] - dose_reference

        gamma = np.min(
            np.sqrt((dose_diff/dose_threshold)**2 +
                    (distance/distance_mm_threshold)**2))

        gamma_array[i, j, k] = gamma

        if counter // 30 == counter / 30:
            percent_pass = str(
                np.round(convert_to_percent_pass(gamma_array), decimals=1))
            sys.stdout.write(
                '\rPercent Pass: {0}% | Percent Complete: {1:.2f}%'.format(
                    percent_pass,
                    counter / np.shape(eval_index)[1] * 100))
            sys.stdout.flush()

    return convert_to_percent_pass(gamma_array)


def create_point_combination(coords):
    mesh_index = np.meshgrid(*coords)
    point_combination = np.reshape(np.array(mesh_index), (3, -1))

    return point_combination


def convert_to_ravel_index(points):
    ravel_index = (
        points[2, :] +
        (points[2, -1] + 1) * points[1, :] +
        (points[2, -1] + 1) * (points[1, -1] + 1) * points[0, :])

    return ravel_index


def gamma_filter_numpy(coords_reference, dose_reference,
                       coords_evaluation, dose_evaluation,
                       distance_mm_threshold, dose_threshold,
                       lower_dose_cutoff=0, **kwargs):

    coord_diffs = [
        coord_ref[:, None] - coord_eval[None, :]
        for coord_ref, coord_eval in zip(coords_reference, coords_evaluation)
    ]

    all_in_vicinity = [
        np.where(np.abs(diff) < distance_mm_threshold)
        for diff in coord_diffs
    ]

    ref_coord_points = create_point_combination([
        in_vicinity[0] for in_vicinity in all_in_vicinity
    ])

    eval_coord_points = create_point_combination([
        in_vicinity[1] for in_vicinity in all_in_vicinity
    ])

    distances = np.sqrt(np.sum([
        coord_diff[ref_points, eval_points]**2
        for ref_points, eval_points, coord_diff
        in zip(ref_coord_points, eval_coord_points, coord_diffs)
    ], axis=0))

    within_distance_threshold = distances < distance_mm_threshold

    distances = distances[within_distance_threshold]
    ref_coord_points = ref_coord_points[:, within_distance_threshold]
    eval_coord_points = eval_coord_points[:, within_distance_threshold]

    dose_diff = (
        dose_evaluation[
            eval_coord_points[0, :],
            eval_coord_points[1, :], eval_coord_points[2, :]
        ] -
        dose_reference[
            ref_coord_points[0, :],
            ref_coord_points[1, :], ref_coord_points[2, :]
        ]
    )

    gamma = np.sqrt((dose_diff / dose_threshold)**2 +
                    (distances / distance_mm_threshold)**2)

    gamma_pass = gamma < 1

    eval_pass = eval_coord_points[:, gamma_pass]

    ravel_index = convert_to_ravel_index(eval_pass)
    gamma_pass_array = np.zeros_like(dose_evaluation).astype(np.bool)

    gamma_pass_array = np.ravel(gamma_pass_array)
    dose_above_cut_off = np.ravel(dose_evaluation) > lower_dose_cutoff

    gamma_pass_array[ravel_index] = True
    gamma_pass_percentage = np.mean(gamma_pass_array[dose_above_cut_off]) * 100

    return gamma_pass_percentage
