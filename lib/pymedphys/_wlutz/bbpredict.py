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


def create_bb_predictor(bb_x, bb_y, gantries, directions, default_tol=0.1):
    bb_coords_keys = ["x", "y"]
    direction_options = np.unique(directions)
    prediction_functions = {}

    for bb_coords_key, bb_coords in zip(bb_coords_keys, [bb_x, bb_y]):
        for current_direction in direction_options:
            prediction_functions[
                (bb_coords_key, current_direction)
            ] = define_inner_prediction_func(
                gantries, bb_coords, directions, current_direction
            )

    def predict_bb(gantry, direction, tol=default_tol):
        results = []
        for bb_coords_key in bb_coords_keys:
            results.append(
                prediction_functions[(bb_coords_key, direction)](gantry, tol)
            )

        return results

    return predict_bb


def define_inner_prediction_func(gantries, bb_coords, directions, current_direction):
    interps = [
        scipy.interpolate.interp1d(
            gantry, bb_coord, bounds_error=False, fill_value="extrapolate"
        )
        for gantry, bb_coord, direction in zip(gantries, bb_coords, directions)
        if direction == current_direction
    ]

    def prediction_func(gantry, tol):
        results = []

        for interp in interps:
            results.append(interp(gantry))

        min_val = np.nanmin(results, axis=0)
        max_val = np.nanmax(results, axis=0)
        # result = np.nanmean(results, axis=0)
        result = (max_val + min_val) / 2

        out_of_tol = np.logical_or(max_val - result > tol, result - min_val > tol)
        result[out_of_tol] = np.nan

        return result

    return prediction_func
