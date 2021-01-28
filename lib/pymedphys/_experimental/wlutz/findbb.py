# Copyright (C) 2020 Cancer Care Associates and Simon Biggs
# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import warnings

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from . import bounds, imginterp, interppoints, pylinacwrapper

BB_MIN_SEARCH_DIST = 2  # mm
BB_REPEAT_TOL = 0.2  # mm

BB_SIZE_FACTORS_TO_SEARCH_OVER = [
    0.5,
    0.55,
    0.6,
    0.65,
    0.7,
    0.75,
    0.8,
    0.85,
    0.9,
    0.95,
    1.0,
]

DEFAULT_BB_REPEATS = 2


def find_bb_centre(
    x, y, image, bb_diameter, edge_lengths, penumbra, field_centre, field_rotation
):
    field = imginterp.create_interpolated_field(x, y, image)

    try:
        initial_bb_centre = pylinacwrapper.find_bb_only(
            x, y, image, edge_lengths, penumbra, field_centre, field_rotation
        )
    except ValueError:
        initial_bb_centre = field_centre

    bb_centre = optimise_bb_centre(
        field, bb_diameter, field_centre, initial_bb_centre=initial_bb_centre
    )

    return bb_centre


def optimise_bb_centre(
    field: imginterp.Field,
    bb_diameter,
    field_centre,
    initial_bb_centre=None,
    repeats=DEFAULT_BB_REPEATS,
):
    if initial_bb_centre is None:
        initial_bb_centre = field_centre

    search_square_edge_length = bb_diameter / np.sqrt(2) / (DEFAULT_BB_REPEATS + 1)
    all_centre_predictions = np.array(
        _bb_finding_repetitions(
            field, bb_diameter, search_square_edge_length, initial_bb_centre
        )
    )
    median_of_predictions = np.nanmedian(all_centre_predictions, axis=0)

    diff = np.abs(all_centre_predictions - median_of_predictions)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        within_tolerance = np.all(diff < BB_REPEAT_TOL, axis=1)

    assert len(within_tolerance) == len(BB_SIZE_FACTORS_TO_SEARCH_OVER)

    if np.sum(within_tolerance) >= len(BB_SIZE_FACTORS_TO_SEARCH_OVER) - 1:
        return median_of_predictions

    if repeats == 0:
        raise ValueError("Unable to determine BB position within designated repeats")

    out_of_tolerance = np.invert(within_tolerance)
    if np.sum(out_of_tolerance) > len(BB_SIZE_FACTORS_TO_SEARCH_OVER) / 3:
        raise ValueError(
            "BB centre not able to be consistently determined. "
            "Predictions thus far were the following:\n"
            f"    {all_centre_predictions}\n"
            "Initial bb centre for this iteration was:\n"
            f"    {initial_bb_centre}"
        )

    return optimise_bb_centre(
        field,
        bb_diameter,
        field_centre,
        initial_bb_centre=median_of_predictions,
        repeats=repeats - 1,
    )


def _bb_finding_repetitions(
    field, bb_diameter, search_square_edge_length, initial_bb_centre
):
    all_centre_predictions = []
    for bb_size_factor in BB_SIZE_FACTORS_TO_SEARCH_OVER:
        prediction_with_adjusted_bb_size = _minimise_bb(
            field,
            bb_diameter * bb_size_factor,
            search_square_edge_length,
            initial_bb_centre,
            set_nan_if_at_bounds=True,
        )

        all_centre_predictions.append(prediction_with_adjusted_bb_size)

    return all_centre_predictions


def _minimise_bb(
    field,
    bb_diameter,
    search_square_edge_length,
    initial_bb_centre,
    set_nan_if_at_bounds=False,
):
    to_minimise_edge_agreement = create_bb_to_minimise(field, bb_diameter)
    bb_bounds = define_bb_bounds(search_square_edge_length, initial_bb_centre)

    bb_centre = bb_basinhopping(
        to_minimise_edge_agreement, bb_bounds, initial_bb_centre
    )

    if bounds.check_if_at_bounds(bb_centre, bb_bounds):
        if set_nan_if_at_bounds:
            return [np.nan, np.nan]
        else:
            raise ValueError("BB found at bounds, likely incorrect")

    return bb_centre


def bb_basinhopping(to_minimise, bb_bounds, initial_bb_centre):
    bb_results = scipy.optimize.basinhopping(
        to_minimise,
        initial_bb_centre,
        T=1,
        niter=200,
        niter_success=5,
        stepsize=0.25,
        minimizer_kwargs={"method": "L-BFGS-B", "bounds": bb_bounds},
    )

    return bb_results.x


def create_bb_to_minimise(field, bb_diameter):
    """This is a numpy vectorised version of `create_bb_to_minimise_simple`"""

    points_to_check_edge_agreement, dist = interppoints.create_bb_points_function(
        bb_diameter
    )
    dist_mask = np.unique(dist)[:, None] == dist[None, :]
    num_in_mask = np.sum(dist_mask, axis=1)
    mask_count_per_item = np.sum(num_in_mask[:, None] * dist_mask, axis=0)
    mask_mean_lookup = np.where(dist_mask)[0]

    def to_minimise_edge_agreement(centre):
        x, y = points_to_check_edge_agreement(centre)

        results = field(x, y)
        masked_results = results * dist_mask
        mask_mean = np.sum(masked_results, axis=1) / num_in_mask
        diff_to_mean_square = (results - mask_mean[mask_mean_lookup]) ** 2
        mean_of_layers = np.sum(diff_to_mean_square[1::] / mask_count_per_item[1::]) / (
            len(mask_mean) - 1
        )

        return mean_of_layers

    return to_minimise_edge_agreement


def create_bb_to_minimise_simple(field, bb_diameter):
    points_to_check_edge_agreement, dist = interppoints.create_bb_points_function(
        bb_diameter
    )
    dist_mask = np.unique(dist)[:, None] == dist[None, :]

    def to_minimise_edge_agreement(centre):
        x, y = points_to_check_edge_agreement(centre)

        total_minimisation = 0

        for current_mask in dist_mask[1::]:
            current_layer = field(x[current_mask], y[current_mask])
            total_minimisation += np.mean((current_layer - np.mean(current_layer)) ** 2)

        return total_minimisation / (len(dist_mask) - 1)

    return to_minimise_edge_agreement


def define_bb_bounds(search_square_edge_length, initial_bb_centre):
    half_field_bounds = search_square_edge_length / 2
    circle_centre_bounds = [
        (
            initial_bb_centre[0] - half_field_bounds,
            initial_bb_centre[0] + half_field_bounds,
        ),
        (
            initial_bb_centre[1] - half_field_bounds,
            initial_bb_centre[1] + half_field_bounds,
        ),
    ]

    return circle_centre_bounds
