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
import scipy.interpolate
import scipy.ndimage.measurements

from .interppoints import define_all_field_points, define_penumbra_points

BASINHOPPING_NITER = 200


def field_finding_loop(
    field, edge_lengths, penumbra, initial_centre, initial_rotation=0, max_loops=5
):
    loop_num = 0

    while True:
        predicted_rotation = optimise_rotation(
            field, initial_centre, edge_lengths, initial_rotation
        )
        predicted_centre = optimise_centre(
            field, initial_centre, edge_lengths, penumbra, predicted_rotation
        )
        while True:
            if loop_num > max_loops:
                raise ValueError(
                    f"Unable to find the field within the defined `max_loops = {max_loops}`"
                )

            initial_rotation = predicted_rotation
            predicted_rotation = optimise_rotation(
                field, predicted_centre, edge_lengths, initial_rotation
            )
            if np.allclose(predicted_rotation, initial_rotation):
                break

            initial_centre = predicted_centre
            predicted_centre = optimise_centre(
                field, initial_centre, edge_lengths, penumbra, predicted_rotation
            )
            if np.allclose(predicted_centre, initial_centre):
                break

            loop_num += 1

        verification_centre = optimise_centre(
            field, predicted_centre, edge_lengths, penumbra, predicted_rotation
        )
        verification_rotation = optimise_rotation(
            field, predicted_centre, edge_lengths, predicted_rotation
        )

        if np.allclose(
            verification_centre, predicted_centre, rtol=0.01, atol=0.01
        ) and np.allclose(
            verification_rotation, predicted_rotation, rtol=0.01, atol=0.01
        ):
            break

        print("Field finding did not agree during verification, repeating...")
        print(f"{predicted_centre}, {predicted_rotation}")
        print(f"{verification_centre}, {verification_rotation}")

        loop_num += 1

    centre = predicted_centre.tolist()
    return centre, predicted_rotation


def optimise_rotation(field, centre, edge_lengths, initial_rotation):
    to_minimise = create_rotation_only_minimiser(field, centre, edge_lengths)
    result = scipy.optimize.basinhopping(
        to_minimise,
        initial_rotation,
        T=1,
        niter=BASINHOPPING_NITER,
        niter_success=3,
        stepsize=90,
        minimizer_kwargs={"method": "L-BFGS-B"},
    )

    predicted_rotation = result.x[0]

    if np.allclose(*edge_lengths, rtol=0.001, atol=0.001):
        return predicted_rotation % 90

    return predicted_rotation % 180


def optimise_centre(field, initial_centre, edge_lengths, penumbra, rotation):
    bounds = [
        (initial_centre[0] - penumbra, initial_centre[0] + penumbra),
        (initial_centre[1] - penumbra, initial_centre[1] + penumbra),
    ]

    to_minimise = create_penumbra_minimiser(field, edge_lengths, penumbra, rotation)

    result = scipy.optimize.basinhopping(
        to_minimise,
        initial_centre,
        T=1,
        niter=BASINHOPPING_NITER,
        niter_success=3,
        stepsize=0.25,
        minimizer_kwargs={"method": "L-BFGS-B", "bounds": bounds},
    )

    predicted_centre = result.x
    return predicted_centre


def _initial_centre(x, y, img):
    centre_of_mass_index = scipy.ndimage.measurements.center_of_mass(img)

    centre = [
        float(_interp_coords(x)(centre_of_mass_index[1])),
        float(_interp_coords(y)(centre_of_mass_index[0])),
    ]

    return centre


def _interp_coords(coord):
    return scipy.interpolate.interp1d(np.arange(len(coord)), coord)


def create_penumbra_minimiser(field, edge_lengths, penumbra, rotation):
    def to_minimise(centre):
        xx_left_right, yy_left_right, xx_top_bot, yy_top_bot = define_penumbra_points(
            centre, edge_lengths, penumbra, rotation
        )

        left_right_interpolated = field(xx_left_right, yy_left_right)
        top_bot_interpolated = field(xx_top_bot, yy_top_bot)

        left_right_weighted_diff = (
            2
            * (left_right_interpolated - left_right_interpolated[:, ::-1])
            / (left_right_interpolated + left_right_interpolated[:, ::-1])
        )
        top_bot_weighted_diff = (
            2
            * (top_bot_interpolated - top_bot_interpolated[::-1, :])
            / (top_bot_interpolated + top_bot_interpolated[::-1, :])
        )

        return np.sum(left_right_weighted_diff ** 2) + np.sum(
            top_bot_weighted_diff ** 2
        )

    return to_minimise


def create_rotation_only_minimiser(field, centre, edge_lengths):
    def to_minimise(rotation):
        all_field_points = define_all_field_points(centre, edge_lengths, rotation)
        return -np.mean(field(*all_field_points))

    return to_minimise
