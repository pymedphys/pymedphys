# Copyright (C) 2026 Matthew Jennings
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

import os
import warnings

from pymedphys._imports import numpy as np

# Frames in the gamma package are skipped when a warning is attributed, so
# that it names the line that called pymedphys.gamma.
_GAMMA_PACKAGE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "")


def warn_caller(message: str) -> None:
    """Warn the user, naming the line of their code that called gamma."""
    warnings.warn(message, UserWarning, skip_file_prefixes=(_GAMMA_PACKAGE,))


def run_input_checks(axes_reference, dose_reference, axes_evaluation, dose_evaluation):
    """Check that the axes and doses fit together.

    Returns the reference and evaluation axes as tuples.
    """

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
                    "axes_reference and axes_evaluation may be single NumPy "
                    "arrays only for one-dimensional doses, where each is a "
                    "1D array. Otherwise pass a tuple of 1D arrays."
                )
        else:
            raise ValueError(
                "axes_reference and axes_evaluation must each be a tuple with "
                "one 1D array of coordinates for each dimension of the dose, "
                "in the order of its dimensions. For one-dimensional doses a "
                "single 1D NumPy array is also accepted for each."
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
