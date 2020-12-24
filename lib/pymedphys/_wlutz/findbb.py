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

# import warnings

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from . import imginterp, interppoints, utilities

BB_MIN_SEARCH_DIST = 2
BB_REPEAT_TOL = 0.1


def optimise_bb_centre(
    field: imginterp.Field,
    bb_diameter,
    edge_lengths,
    penumbra,
    field_centre,
    field_rotation,
):
    centralised_field = utilities.create_centralised_field(
        field, field_centre, field_rotation
    )

    bb_centre_in_centralised_field = _minimise_bb(
        centralised_field, bb_diameter, edge_lengths, penumbra
    )
    verification_repeat_with_smaller_bb = _minimise_bb(
        centralised_field, bb_diameter / 2, edge_lengths, penumbra
    )
    repeat_agreement = np.abs(
        verification_repeat_with_smaller_bb - bb_centre_in_centralised_field
    )

    bb_centre = utilities.transform_point(
        bb_centre_in_centralised_field, field_centre, field_rotation
    )
    bb_repeated = utilities.transform_point(
        verification_repeat_with_smaller_bb, field_centre, field_rotation
    )

    if np.any(repeat_agreement > BB_REPEAT_TOL):

        raise ValueError(
            "BB centre not able to be consistently determined\n"
            f"  First iteration:  {bb_centre}\n"
            f"  Second iteration: {bb_repeated}"
        )

    return np.mean([bb_centre, bb_repeated], axis=0)


def _minimise_bb(field, bb_diameter, edge_lengths, penumbra):
    to_minimise_edge_agreement = create_bb_to_minimise(field, bb_diameter)
    bb_bounds = define_bb_bounds(bb_diameter, edge_lengths, penumbra)

    bb_centre = bb_basinhopping(to_minimise_edge_agreement, bb_bounds)

    if check_if_at_bounds(bb_centre, bb_bounds):
        raise ValueError("BB found at bounds, likely incorrect")

    return bb_centre


def check_if_at_bounds(bb_centre, bb_bounds):
    x_at_bounds = np.any(np.array(bb_centre[0]) == np.array(bb_bounds[0]))
    y_at_bounds = np.any(np.array(bb_centre[1]) == np.array(bb_bounds[1]))

    any_at_bounds = x_at_bounds or y_at_bounds
    return any_at_bounds


def bb_basinhopping(to_minimise, bb_bounds):
    bb_results = scipy.optimize.basinhopping(
        to_minimise,
        [0, 0],
        T=1,
        niter=200,
        niter_success=5,
        stepsize=0.25,
        minimizer_kwargs={"method": "L-BFGS-B", "bounds": bb_bounds},
    )

    return bb_results.x


def create_bb_to_minimise(field, bb_diameter):
    """This is a numpy vectorised version of `create_bb_to_minimise_simple`
    """

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


def define_bb_bounds(bb_diameter, edge_lengths, penumbra):
    # TODO: This does not allow the BB to search right up to the edge of the field
    # this is a crude work around for the fact that a significantly flat area will
    # currently be optimised for over the BB itself.
    half_field_bounds = [
        (edge_lengths[0] - penumbra * 2) / 2,
        (edge_lengths[1] - penumbra * 2) / 2,
    ]

    bb_radius = bb_diameter / 2

    circle_centre_bounds = [
        (-half_field_bounds[0] + bb_radius, half_field_bounds[0] - bb_radius),
        (-half_field_bounds[1] + bb_radius, half_field_bounds[1] - bb_radius),
    ]

    return circle_centre_bounds
