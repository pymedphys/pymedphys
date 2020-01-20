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

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

import pymedphys._vendor.pylinac.winstonlutz

from .interppoints import (
    define_penumbra_points_at_origin,
    define_rotation_field_points_at_origin,
    transform_penumbra_points,
    transform_rotation_field_points,
)
from .pylinac import PylinacComparisonDeviation, run_wlutz

BASINHOPPING_NITER = 200
INITIAL_ROTATION = 0


def get_initial_centre(x, y, img):
    wl_image = pymedphys._vendor.pylinac.winstonlutz.WLImageOld(  # pylint: disable = protected-access
        img
    )
    min_x = np.min(x)
    dx = x[1] - x[0]
    min_y = np.min(y)
    dy = y[1] - y[0]

    field_centre = [
        wl_image.field_cax.x * dx + min_x,
        wl_image.field_cax.y * dy + min_y,
    ]

    return field_centre


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
    fixed_rotation=None,
    niter=10,
    pylinac_tol=0.2,
):

    if fixed_rotation is None:
        check_aspect_ratio(edge_lengths)

        predicted_rotation = optimise_rotation(
            field, initial_centre, edge_lengths, penumbra
        )
    else:
        predicted_rotation = fixed_rotation

    predicted_centre = optimise_centre(
        field, initial_centre, edge_lengths, penumbra, predicted_rotation
    )

    for _ in range(niter):
        if fixed_rotation is None:
            previous_rotation = predicted_rotation
            predicted_rotation = optimise_rotation(
                field, predicted_centre, edge_lengths, penumbra
            )
            try:
                check_rotation_close(
                    edge_lengths, previous_rotation, predicted_rotation
                )
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

    if fixed_rotation is None:
        verification_rotation = optimise_rotation(
            field, predicted_centre, edge_lengths, penumbra
        )

        check_rotation_close(edge_lengths, verification_rotation, predicted_rotation)

    if not pylinac_tol is None:
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
        if not (diff < 0.3 or diff > 89.7):
            raise ValueError(
                _rotation_error_string(verification_rotation, predicted_rotation, diff)
            )
    else:
        diff = (verification_rotation - predicted_rotation) % 180
        if not (diff < 0.3 or diff > 179.7):
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
        raise ValueError(
            "Field centre not able to be reproducibly determined.\n"
            f"    Verification Centre: {verification_centre}\n"
            f"    Predicted Centre: {predicted_centre}\n"
        )


def optimise_rotation(field, centre, edge_lengths, penumbra):
    to_minimise = create_rotation_only_minimiser(field, centre, edge_lengths, penumbra)
    result = scipy.optimize.basinhopping(
        to_minimise,
        INITIAL_ROTATION,
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


def get_centre_of_mass(x, y, img):
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
