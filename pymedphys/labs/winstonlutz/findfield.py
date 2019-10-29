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

from .interppoints import define_penumbra_points


def field_finding_loop(
    field, edge_lengths, penumbra, initial_centre=(0, 0), initial_rotation=0
):
    to_minimise_all = create_penumbra_minimisation(field, edge_lengths, penumbra)

    predicted_rotation = optimise_rotation(
        initial_centre, initial_rotation, to_minimise_all
    )

    while True:
        while True:
            initial_rotation = predicted_rotation

            predicted_centre = optimise_centre(
                initial_centre, predicted_rotation, to_minimise_all, penumbra
            )

            if np.allclose(predicted_centre, initial_centre):
                break

            initial_centre = predicted_centre

            predicted_rotation = optimise_rotation(
                predicted_centre, initial_rotation, to_minimise_all
            )

            if np.allclose(predicted_rotation, initial_rotation):
                break

        verification_centre = optimise_centre(
            predicted_centre, predicted_rotation, to_minimise_all, penumbra
        )
        verification_rotation = optimise_rotation(
            predicted_centre, predicted_rotation, to_minimise_all
        )

        if np.allclose(verification_centre, predicted_centre) and np.allclose(
            verification_rotation, predicted_rotation
        ):
            break

        print("Field finding did not agree during verification, repeating...")

    centre = predicted_centre.tolist()
    return centre, predicted_rotation


def _initial_centre(x, y, img):
    centre_of_mass_index = scipy.ndimage.measurements.center_of_mass(img)

    centre = [
        float(_interp_coords(x)(centre_of_mass_index[1])),
        float(_interp_coords(y)(centre_of_mass_index[0])),
    ]

    return centre


def _interp_coords(coord):
    return scipy.interpolate.interp1d(np.arange(len(coord)), coord)


def create_penumbra_minimisation(field, edge_lengths, penumbra):
    def to_minimise(inputs):
        centre = [inputs[0], inputs[1]]
        rotation = inputs[2]

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


def create_rotation_only_to_minimise(centre, to_minimise_all):
    def to_minimise(rotation):
        return to_minimise_all([centre[0], centre[1], rotation])

    return to_minimise


def create_shift_only_to_minimise(rotation, to_minimise_all):
    def to_minimise(centre):
        return to_minimise_all([centre[0], centre[1], rotation])

    return to_minimise


def optimise_rotation(predicted_centre, initial_rotation, to_minimise_all):
    rotation_only_to_minimise = create_rotation_only_to_minimise(
        predicted_centre, to_minimise_all
    )
    result = scipy.optimize.basinhopping(
        rotation_only_to_minimise,
        initial_rotation,
        T=1,
        niter=200,
        niter_success=3,
        stepsize=30,
        minimizer_kwargs={"method": "L-BFGS-B"},
    )

    predicted_rotation = result.x[0]
    return predicted_rotation % 90


def optimise_centre(initial_centre, predicted_rotation, to_minimise_all, penumbra):
    bounds = [
        (initial_centre[0] - penumbra, initial_centre[0] + penumbra),
        (initial_centre[1] - penumbra, initial_centre[1] + penumbra),
    ]

    shift_only_to_minimise = create_shift_only_to_minimise(
        predicted_rotation, to_minimise_all
    )

    result = scipy.optimize.basinhopping(
        shift_only_to_minimise,
        initial_centre,
        T=1,
        niter=200,
        niter_success=5,
        stepsize=0.25,
        minimizer_kwargs={"method": "L-BFGS-B", "bounds": bounds},
    )

    predicted_centre = result.x
    return predicted_centre
