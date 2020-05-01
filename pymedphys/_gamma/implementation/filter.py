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


"""Gamma filters that only calculate pass or fail for each evaluation point.

No interpolation is undergone with these at the moment. Interpolation is
planned for the future.
"""


import sys

from pymedphys._imports import numpy as np

from ..utilities import (
    calculate_pass_rate,
    convert_to_ravel_index,
    create_point_combination,
)


def gamma_filter_numpy(
    axes_reference,
    dose_reference,
    axes_evaluation,
    dose_evaluation,
    distance_mm_threshold,
    dose_threshold,
    lower_dose_cutoff=0,
    **_
):

    coord_diffs = [
        coord_ref[:, None] - coord_eval[None, :]
        for coord_ref, coord_eval in zip(axes_reference, axes_evaluation)
    ]

    all_in_vicinity = [
        np.where(np.abs(diff) < distance_mm_threshold) for diff in coord_diffs
    ]

    ref_coord_points = create_point_combination(
        [in_vicinity[0] for in_vicinity in all_in_vicinity]
    )

    eval_coord_points = create_point_combination(
        [in_vicinity[1] for in_vicinity in all_in_vicinity]
    )

    distances = np.sqrt(
        np.sum(
            [
                coord_diff[ref_points, eval_points] ** 2
                for ref_points, eval_points, coord_diff in zip(
                    ref_coord_points, eval_coord_points, coord_diffs
                )
            ],
            axis=0,
        )
    )

    within_distance_threshold = distances < distance_mm_threshold

    distances = distances[within_distance_threshold]
    ref_coord_points = ref_coord_points[:, within_distance_threshold]
    eval_coord_points = eval_coord_points[:, within_distance_threshold]

    dose_diff = (
        dose_evaluation[
            eval_coord_points[0, :], eval_coord_points[1, :], eval_coord_points[2, :]
        ]
        - dose_reference[
            ref_coord_points[0, :], ref_coord_points[1, :], ref_coord_points[2, :]
        ]
    )

    gamma = np.sqrt(
        (dose_diff / dose_threshold) ** 2 + (distances / distance_mm_threshold) ** 2
    )

    gamma_pass = gamma < 1

    eval_pass = eval_coord_points[:, gamma_pass]

    ravel_index = convert_to_ravel_index(eval_pass)
    gamma_pass_array = np.zeros_like(dose_evaluation).astype(np.bool)

    gamma_pass_array = np.ravel(gamma_pass_array)
    dose_above_cut_off = np.ravel(dose_evaluation) > lower_dose_cutoff

    gamma_pass_array[ravel_index] = True
    gamma_pass_percentage = np.mean(gamma_pass_array[dose_above_cut_off]) * 100

    return gamma_pass_percentage


def gamma_filter_brute_force(
    axes_reference,
    dose_reference,
    axes_evaluation,
    dose_evaluation,
    distance_mm_threshold,
    dose_threshold,
    lower_dose_cutoff=0,
    **_
):

    xx_ref, yy_ref, zz_ref = np.meshgrid(*axes_reference, indexing="ij")
    gamma_array = np.ones_like(dose_evaluation).astype(np.float) * np.nan

    mesh_index = np.meshgrid(
        *[np.arange(len(coord_eval)) for coord_eval in axes_evaluation]
    )

    eval_index = np.reshape(np.array(mesh_index), (3, -1))
    run_index = np.arange(np.shape(eval_index)[1])
    np.random.shuffle(run_index)

    sys.stdout.write("    ")

    for counter, point_index in enumerate(run_index):
        i, j, k = eval_index[:, point_index]
        eval_x = axes_evaluation[0][i]
        eval_y = axes_evaluation[1][j]
        eval_z = axes_evaluation[2][k]

        if dose_evaluation[i, j, k] < lower_dose_cutoff:
            continue

        distance = np.sqrt(
            (xx_ref - eval_x) ** 2 + (yy_ref - eval_y) ** 2 + (zz_ref - eval_z) ** 2
        )

        dose_diff = dose_evaluation[i, j, k] - dose_reference

        gamma = np.min(
            np.sqrt(
                (dose_diff / dose_threshold) ** 2
                + (distance / distance_mm_threshold) ** 2
            )
        )

        gamma_array[i, j, k] = gamma

        if counter // 30 == counter / 30:
            percent_pass = str(np.round(calculate_pass_rate(gamma_array), decimals=1))
            sys.stdout.write(
                "\rPercent Pass: {0}% | Percent Complete: {1:.2f}%".format(
                    percent_pass, counter / np.shape(eval_index)[1] * 100
                )
            )
            sys.stdout.flush()

    return calculate_pass_rate(gamma_array)
