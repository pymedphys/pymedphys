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
from pymedphys._imports import pylinac, scipy

from .interppoints import (
    define_penumbra_points_at_origin,
    define_rotation_field_points_at_origin,
    transform_penumbra_points,
    transform_rotation_field_points,
)
from .pylinac import run_wlutz

BASINHOPPING_NITER = 200
INITIAL_ROTATION = 0


def get_initial_centre(x, y, image, field_rotation):
    pylinac_version = pylinac.__version__

    pylinac_results = run_wlutz(
        x, y, image, field_rotation, find_bb=False, pylinac_versions=[pylinac_version]
    )

    field_centre = pylinac_results[pylinac_version]["field_centre"]

    return field_centre


def refine_field_centre(initial_centre, field, edge_lengths, penumbra, field_rotation):
    predicted_centre = optimise_centre(
        field, initial_centre, edge_lengths, penumbra, field_rotation
    )

    predicted_centre_with_double_penumbra = optimise_centre(
        field, initial_centre, edge_lengths, penumbra * 2, field_rotation
    )

    check_centre_close(predicted_centre, predicted_centre_with_double_penumbra)

    field_centre = predicted_centre.tolist()
    return field_centre


def check_centre_close(verification_centre, predicted_centre):
    if not np.allclose(verification_centre, predicted_centre, rtol=0.01, atol=0.01):
        raise ValueError(
            "Field centre not able to be reproducibly determined.\n"
            f"    Verification Centre: {verification_centre}\n"
            f"    Predicted Centre: {predicted_centre}\n"
        )


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
