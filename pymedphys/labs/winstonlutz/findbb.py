# Copyright (C) 2019 Cancer Care Associates

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


import numpy as np
import scipy.optimize

from .interppoints import (
    apply_transform,
    create_bb_points_function,
    translate_and_rotate_transform,
)


def optimise_bb_centre(
    field, bb_diameter, edge_lengths, penumbra, field_centre, field_rotation
):
    centralised_field = create_centralised_field(field, field_centre, field_rotation)
    to_minimise = create_bb_to_minimise(centralised_field, bb_diameter)
    bb_bounds = define_bb_bounds(bb_diameter, edge_lengths, penumbra)

    bb_results = scipy.optimize.basinhopping(
        to_minimise,
        [0, 0],
        T=1,
        niter=200,
        niter_success=5,
        stepsize=0.25,
        minimizer_kwargs={"method": "L-BFGS-B", "bounds": bb_bounds},
    )
    bb_centre_in_centralised_field = bb_results.x

    transform = translate_and_rotate_transform(field_centre, field_rotation)
    bb_centre = apply_transform(*bb_centre_in_centralised_field, transform)
    bb_centre = np.array(bb_centre).tolist()

    return bb_centre


def create_bb_to_minimise(field, bb_diameter):
    """This is a numpy vectorised version of `create_bb_to_minimise_simple`
    """

    points_to_check, dist = create_bb_points_function(bb_diameter)
    dist_mask = np.unique(dist)[:, None] == dist[None, :]
    num_in_mask = np.sum(dist_mask, axis=1)
    mask_count_per_item = np.sum(num_in_mask[:, None] * dist_mask, axis=0)
    mask_mean_lookup = np.where(dist_mask)[0]

    def to_minimise(centre):
        x, y = points_to_check(centre)

        results = field(x, y)
        masked_results = results * dist_mask
        mask_mean = np.sum(masked_results, axis=1) / num_in_mask
        diff_to_mean_square = (results - mask_mean[mask_mean_lookup]) ** 2
        mean_of_layers = np.sum(diff_to_mean_square[1::] / mask_count_per_item[1::]) / (
            len(mask_mean) - 1
        )

        return mean_of_layers

    return to_minimise


def create_bb_to_minimise_simple(field, bb_diameter):

    points_to_check, dist = create_bb_points_function(bb_diameter)
    dist_mask = np.unique(dist)[:, None] == dist[None, :]

    def to_minimise(centre):
        x, y = points_to_check(centre)

        total_minimisation = 0

        for current_mask in dist_mask[1::]:
            current_layer = field(x[current_mask], y[current_mask])
            total_minimisation += np.mean((current_layer - np.mean(current_layer)) ** 2)

        return total_minimisation / (len(dist_mask) - 1)

    return to_minimise


def create_centralised_field(field, centre, rotation):

    transform = translate_and_rotate_transform(centre, rotation)

    def new_field(x, y):
        x_prime, y_prime = apply_transform(x, y, transform)
        return field(x_prime, y_prime)

    return new_field


def define_bb_bounds(bb_diameter, edge_lengths, penumbra):
    half_field_bounds = [
        (edge_lengths[0] - penumbra / 2) / 2,
        (edge_lengths[1] - penumbra / 2) / 2,
    ]

    bb_radius = bb_diameter / 2

    circle_centre_bounds = [
        (-half_field_bounds[0] + bb_radius, half_field_bounds[0] - bb_radius),
        (-half_field_bounds[1] + bb_radius, half_field_bounds[1] - bb_radius),
    ]

    return circle_centre_bounds
