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

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def run_input_checks(
        coords_reference, dose_reference,
        coords_evaluation, dose_evaluation):
    """Check user inputs."""
    if (
            not isinstance(coords_evaluation, tuple) or
            not isinstance(coords_reference, tuple)):
        if (
                isinstance(coords_evaluation, np.ndarray) and
                isinstance(coords_reference, np.ndarray)):
            if (
                    len(np.shape(coords_evaluation)) == 1 and
                    len(np.shape(coords_reference)) == 1):

                coords_evaluation = (coords_evaluation,)
                coords_reference = (coords_reference,)

            else:
                raise Exception(
                    "Can only use numpy arrays as input for one dimensional "
                    "gamma."
                )
        else:
            raise Exception(
                "Input coordinates must be inputted as a tuple, for "
                "one dimension input is (x,), for two dimensions, (x, y),  "
                "for three dimensions input is (x, y, z).")

    reference_coords_shape = tuple([len(item) for item in coords_reference])
    if reference_coords_shape != np.shape(dose_reference):
        raise Exception(
            "Length of items in coords_reference does not match the shape of "
            "dose_reference")

    evaluation_coords_shape = tuple([len(item) for item in coords_evaluation])
    if evaluation_coords_shape != np.shape(dose_evaluation):
        raise Exception(
            "Length of items in coords_evaluation does not match the shape of "
            "dose_evaluation")

    if not (len(np.shape(dose_evaluation)) ==
            len(np.shape(dose_reference)) ==
            len(coords_evaluation) ==
            len(coords_reference)):
        raise Exception(
            "The dimensions of the input data do not match")

    return coords_reference, coords_evaluation
