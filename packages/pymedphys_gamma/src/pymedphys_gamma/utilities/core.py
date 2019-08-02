# Copyright (C) 2015 Simon Biggs
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


def create_point_combination(coords):
    mesh_index = np.meshgrid(*coords)
    point_combination = np.reshape(np.array(mesh_index), (3, -1))

    return point_combination


def convert_to_ravel_index(points):
    ravel_index = (
        points[2, :]
        + (points[2, -1] + 1) * points[1, :]
        + (points[2, -1] + 1) * (points[1, -1] + 1) * points[0, :]
    )

    return ravel_index


def calculate_pass_rate(gamma_array):
    valid_gamma = gamma_array[np.invert(np.isnan(gamma_array))]
    percent_pass = 100 * np.sum(valid_gamma < 1) / len(valid_gamma)

    return percent_pass


def run_input_checks(axes_reference, dose_reference, axes_evaluation, dose_evaluation):
    """Check user inputs."""

    if not isinstance(axes_evaluation, tuple) or not isinstance(axes_reference, tuple):

        if isinstance(axes_evaluation, np.ndarray) and isinstance(
            axes_reference, np.ndarray
        ):

            if (
                len(np.shape(axes_evaluation)) == 1
                and len(np.shape(axes_reference)) == 1
            ):

                axes_evaluation = (axes_evaluation,)
                axes_reference = (axes_reference,)

            else:
                raise Exception(
                    "Can only use numpy arrays as input " "for one dimensional gamma."
                )
        else:
            raise Exception(
                "Input coordinates must be inputted as a tuple, for "
                "one dimension input is (x,), for two dimensions, "
                "(x, y), for three dimensions input is (x, y, z)."
            )

    reference_coords_shape = tuple([len(item) for item in axes_reference])
    if reference_coords_shape != np.shape(dose_reference):
        raise Exception(
            "Length of items in axes_reference ({}) does not match the "
            "shape of dose_reference ({})".format(
                reference_coords_shape, np.shape(dose_reference)
            )
        )

    evaluation_coords_shape = tuple([len(item) for item in axes_evaluation])
    if evaluation_coords_shape != np.shape(dose_evaluation):
        raise Exception(
            "Length of items in axes_evaluation does not match the "
            "shape of dose_evaluation"
        )

    if not (
        len(np.shape(dose_evaluation))
        == len(np.shape(dose_reference))
        == len(axes_evaluation)
        == len(axes_reference)
    ):
        raise Exception("The dimensions of the input data do not match")

    return axes_reference, axes_evaluation
