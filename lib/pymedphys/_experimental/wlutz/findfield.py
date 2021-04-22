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

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from pymedphys._experimental.vendor.pylinac_vendored._pylinac_installed import (
    pylinac as _pylinac_installed,
)

from . import bounds, imginterp, interppoints, pylinacwrapper

BASINHOPPING_NITER = 200
FIELD_REPEAT_TOL = 0.2  # mm


def find_field_centre(x, y, image, edge_lengths, penumbra, field_rotation):
    field = imginterp.create_interpolated_field(x, y, image)

    initial_field_centre = get_initial_centre(x, y, image, edge_lengths, field_rotation)
    field_centre = refine_field_centre(
        initial_field_centre, field, edge_lengths, penumbra, field_rotation
    )

    return field_centre


def get_initial_centre(x, y, image, edge_lengths, field_rotation):
    pylinac_version = _pylinac_installed.__version__

    try:
        pylinac_results = pylinacwrapper.run_wlutz(
            x,
            y,
            image,
            edge_lengths,
            field_rotation,
            find_bb=False,
            pylinac_versions=[pylinac_version],
        )
    except ValueError:
        return [0, 0]

    initial_centre = pylinac_results[pylinac_version]["field_centre"]

    return initial_centre


def refine_field_centre(initial_centre, field, edge_lengths, penumbra, field_rotation):
    search_distance = penumbra * 2

    field_bounds = [
        (initial_centre[0] - search_distance, initial_centre[0] + search_distance),
        (initial_centre[1] - search_distance, initial_centre[1] + search_distance),
    ]

    predicted_centre = optimise_centre(
        field, initial_centre, edge_lengths, penumbra, field_rotation, field_bounds
    )

    all_centre_predictions = [predicted_centre]
    for penumbra_ratio in [0.5, 1.5, 2]:
        prediction_with_adjusted_penumbra = optimise_centre(
            field,
            initial_centre,
            edge_lengths,
            penumbra * penumbra_ratio,
            field_rotation,
            field_bounds,
        )
        check_centre_close(predicted_centre, prediction_with_adjusted_penumbra)
        all_centre_predictions.append(prediction_with_adjusted_penumbra)

    return np.mean(all_centre_predictions, axis=0)


def check_centre_close(verification_centre, predicted_centre):
    if not np.allclose(verification_centre, predicted_centre, atol=FIELD_REPEAT_TOL):
        raise ValueError(
            "Field centre not able to be reproducibly determined.\n"
            f"    Verification Centre: {verification_centre}\n"
            f"    Predicted Centre: {predicted_centre}\n"
        )


def optimise_centre(
    field, initial_centre, edge_lengths, penumbra, rotation, field_bounds
):
    to_minimise = create_penumbra_minimiser(field, edge_lengths, penumbra, rotation)

    result = scipy.optimize.basinhopping(
        to_minimise,
        initial_centre,
        T=1,
        niter=BASINHOPPING_NITER,
        niter_success=3,
        stepsize=0.25,
        minimizer_kwargs={"method": "L-BFGS-B", "bounds": field_bounds},
    )

    predicted_centre = result.x

    if bounds.check_if_at_bounds(predicted_centre, field_bounds):
        raise ValueError("Field found at bounds, likely incorrect")

    return predicted_centre


def create_penumbra_minimiser(field, edge_lengths, penumbra, rotation):
    points_at_origin = interppoints.define_penumbra_points_at_origin(
        edge_lengths, penumbra
    )

    def to_minimise(centre):
        (
            xx_left_right,
            yy_left_right,
            xx_top_bot,
            yy_top_bot,
        ) = interppoints.transform_penumbra_points(points_at_origin, centre, rotation)

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
