# Copyright (C) 2015 Simon Biggs
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


def calculate_pass_rate(gamma_array) -> float:
    """Percentage of evaluated points that pass, with gamma <= 1.

    NaN marks points that were not evaluated, so they are not counted.
    Raises ``ValueError`` if no point was evaluated.
    """
    gamma_array = np.asarray(gamma_array, dtype=float)
    valid_gamma = gamma_array[~np.isnan(gamma_array)]
    if valid_gamma.size == 0:
        raise ValueError(
            "No gamma values were evaluated, so there is no pass rate. Check "
            "the lower dose cutoff and random_subset."
        )

    return float(100 * np.count_nonzero(valid_gamma <= 1) / valid_gamma.size)


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
                raise ValueError(
                    "Can only use numpy arrays as input for one dimensional gamma."
                )
        else:
            raise ValueError(
                "Input coordinates must be inputted as a tuple, for "
                "one dimension input is (x,), for two dimensions, "
                "(x, y), for three dimensions input is (x, y, z)."
            )

    reference_coords_shape = tuple(len(item) for item in axes_reference)
    if reference_coords_shape != np.shape(dose_reference):
        raise ValueError(
            "Length of items in axes_reference ({}) does not match the "
            "shape of dose_reference ({})".format(
                reference_coords_shape, np.shape(dose_reference)
            )
        )

    evaluation_coords_shape = tuple(len(item) for item in axes_evaluation)
    if evaluation_coords_shape != np.shape(dose_evaluation):
        raise ValueError(
            "Length of items in axes_evaluation does not match the "
            "shape of dose_evaluation"
        )

    if not (
        len(np.shape(dose_evaluation))
        == len(np.shape(dose_reference))
        == len(axes_evaluation)
        == len(axes_reference)
    ):
        raise ValueError("The dimensions of the input data do not match")

    return axes_reference, axes_evaluation
