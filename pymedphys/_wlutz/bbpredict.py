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
