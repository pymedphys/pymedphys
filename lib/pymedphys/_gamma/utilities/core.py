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


from collections.abc import Mapping

from pymedphys._imports import numpy as np


def calculate_pass_rate(gamma) -> float:
    """The percentage of analysed reference points that pass gamma.

    A point passes when its gamma is at most 1. NaN marks reference points
    that :func:`pymedphys.gamma` did not analyse (below the lower dose
    cutoff, or not selected by ``random_subset``), so they are left out of
    both the count and the total, as are the masked values of a masked array.

    Every NaN is taken to mark a point that was not analysed. Gamma from other
    software, or from :func:`pymedphys.gamma` before version 0.42.0, can also
    be NaN at analysed points, which would then be left out and raise the
    pass rate. Recalculate such gamma with this version of
    :func:`pymedphys.gamma` first.

    Parameters
    ----------
    gamma : array_like
        Gamma values of any shape, as returned by :func:`pymedphys.gamma` for
        one pair of dose and distance thresholds.

    Returns
    -------
    float
        The pass rate, in percent.

    Raises
    ------
    TypeError
        If ``gamma`` is the dict that :func:`pymedphys.gamma` returns for
        several thresholds, rather than one of its values.
    ValueError
        If no reference point was analysed, so every value is NaN or masked,
        or if any gamma value is negative.
    """
    if isinstance(gamma, Mapping):
        raise TypeError(
            "gamma holds results for several thresholds, keyed by (dose, "
            "distance). Pass the result for one pair of thresholds, for "
            "example gamma[(3, 3)]."
        )

    # Masked values, like NaN, were not analysed.
    gamma = np.ma.filled(np.ma.asarray(gamma, dtype=float), np.nan)
    valid_gamma = gamma[~np.isnan(gamma)]
    if valid_gamma.size == 0:
        raise ValueError(
            "No reference point was analysed, so there is no pass rate. Every "
            "gamma value is NaN or masked; check the lower dose cutoff, "
            "random_subset, and any mask."
        )

    negative = np.count_nonzero(valid_gamma < 0)
    if negative:
        raise ValueError(
            f"Gamma cannot be negative, but {negative} of the values are. "
            "Check that the input is a gamma array."
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
