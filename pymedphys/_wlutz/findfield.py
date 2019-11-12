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

from .imginterp import create_interpolated_field
from .interppoints import (
    define_penumbra_points_at_origin,
    define_rotation_field_points_at_origin,
    transform_penumbra_points,
    transform_rotation_field_points,
)
from .pylinac import PylinacComparisonDeviation, run_wlutz

BASINHOPPING_NITER = 200


def find_centre_and_rotation(
    x, y, img, edge_lengths, penumbra=2, initial_rotation=0, rounding=True
):
    field = create_interpolated_field(x, y, img)
    initial_centre = _initial_centre(x, y, img)

    centre, rotation = field_centre_and_rotation_refining(
        field, edge_lengths, penumbra, initial_centre, initial_rotation=initial_rotation
    )

    if rounding:
        centre = np.round(centre, decimals=2).tolist()
        rotation = np.round(rotation, decimals=1)

    return centre, rotation


def check_aspect_ratio(edge_lengths):
    if not np.allclose(*edge_lengths):
        if np.min(edge_lengths) > 0.95 * np.max(edge_lengths):
            raise ValueError(
                "For non-square rectangular fields, "
                "to accurately determine the rotation, "
                "need to have the small edge be less than 95% of the long edge."
            )


def field_centre_and_rotation_refining(
    field,
    edge_lengths,
    penumbra,
    initial_centre,
    initial_rotation=0,
    niter=10,
    pylinac_tol=0.2,
):
    check_aspect_ratio(edge_lengths)

    predicted_rotation = optimise_rotation(
        field, initial_centre, edge_lengths, penumbra, initial_rotation
    )

    predicted_centre = optimise_centre(
        field, initial_centre, edge_lengths, penumbra, predicted_rotation
    )

    for _ in range(niter):
        previous_rotation = predicted_rotation
        predicted_rotation = optimise_rotation(
            field, predicted_centre, edge_lengths, penumbra, predicted_rotation
        )
        try:
            check_rotation_close(edge_lengths, previous_rotation, predicted_rotation)
            break
        except ValueError:
            pass

        previous_centre = predicted_centre
        predicted_centre = optimise_centre(
            field, predicted_centre, edge_lengths, penumbra, predicted_rotation
        )
        try:
            check_centre_close(previous_centre, predicted_centre)
            break
        except ValueError:
            pass

    verification_centre = optimise_centre(
        field, initial_centre, edge_lengths, penumbra, predicted_rotation
    )

    verification_rotation = optimise_rotation(
        field, predicted_centre, edge_lengths, penumbra, initial_rotation
    )

    check_rotation_and_centre(
        edge_lengths,
        verification_centre,
        predicted_centre,
        verification_rotation,
        predicted_rotation,
    )

    try:
        pylinac = run_wlutz(
            field,
            edge_lengths,
            penumbra,
            predicted_centre,
            predicted_rotation,
            find_bb=False,
        )
    except ValueError as e:
        raise ValueError(
            "After finding the field centre during comparison to Pylinac the pylinac "
            f"code raised the following error:\n    {e}"
        )

    pylinac_2_2_6_out_of_tol = np.any(
        np.abs(np.array(pylinac["v2.2.6"]["field_centre"]) - predicted_centre)
        > pylinac_tol
    )
    pylinac_2_2_7_out_of_tol = np.any(
        np.abs(np.array(pylinac["v2.2.7"]["field_centre"]) - predicted_centre)
        > pylinac_tol
    )
    if pylinac_2_2_6_out_of_tol or pylinac_2_2_7_out_of_tol:
        raise PylinacComparisonDeviation(
            "The determined field centre deviates from pylinac more "
            "than the defined tolerance"
        )

    centre = predicted_centre.tolist()
    return centre, predicted_rotation


def check_rotation_and_centre(
    edge_lengths,
    verification_centre,
    predicted_centre,
    verification_rotation,
    predicted_rotation,
):
    check_centre_close(verification_centre, predicted_centre)
    check_rotation_close(edge_lengths, verification_rotation, predicted_rotation)


def check_rotation_close(edge_lengths, verification_rotation, predicted_rotation):
    if np.allclose(*edge_lengths):
        diff = (verification_rotation - predicted_rotation) % 90
        if not (diff < 0.1 or diff > 89.9):
            raise ValueError(
                _rotation_error_string(verification_rotation, predicted_rotation, diff)
            )
    else:
        diff = (verification_rotation - predicted_rotation) % 180
        if not (diff < 0.1 or diff > 179.9):
            raise ValueError(
                _rotation_error_string(verification_rotation, predicted_rotation, diff)
            )


def _rotation_error_string(verification_rotation, predicted_rotation, diff):
    return (
        "Rotation not able to be consistently determined.\n"
        f"    Predicted Rotation = {predicted_rotation}\n"
        f"    Verification Rotation = {verification_rotation}\n"
        f"    Diff = {diff}\n"
    )


def check_centre_close(verification_centre, predicted_centre):
    if not np.allclose(verification_centre, predicted_centre, rtol=0.01, atol=0.01):
        raise ValueError("Field centre not able to be reproducibly determined.")


def optimise_rotation(field, centre, edge_lengths, penumbra, initial_rotation):
    to_minimise = create_rotation_only_minimiser(field, centre, edge_lengths, penumbra)
    result = scipy.optimize.basinhopping(
        to_minimise,
        initial_rotation,
        T=1,
        niter=BASINHOPPING_NITER,
        niter_success=5,
        stepsize=90,
        minimizer_kwargs={"method": "L-BFGS-B"},
    )

    predicted_rotation = result.x[0]

    if np.allclose(*edge_lengths, rtol=0.001, atol=0.001):
        modulo_rotation = predicted_rotation % 90
        if modulo_rotation >= 45:
            modulo_rotation = modulo_rotation - 90
        return modulo_rotation

    modulo_rotation = predicted_rotation % 180
    if modulo_rotation >= 90:
        modulo_rotation = modulo_rotation - 180
    return modulo_rotation


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

    points_at_origin = define_penumbra_points_at_origin(edge_lengths, penumbra)

    def to_minimise(centre):
        (
            xx_left_right,
            yy_left_right,
            xx_top_bot,
            yy_top_bot,
        ) = transform_penumbra_points(points_at_origin, centre, rotation)

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


def create_rotation_only_minimiser(field, centre, edge_lengths, penumbra):
    points_at_origin = define_rotation_field_points_at_origin(edge_lengths, penumbra)

    def to_minimise(rotation):
        all_field_points = transform_rotation_field_points(
            points_at_origin, centre, rotation
        )
        return np.mean(field(*all_field_points) ** 2)

    return to_minimise
