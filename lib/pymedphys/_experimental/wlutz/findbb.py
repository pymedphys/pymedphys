# Copyright (C) 2021 Cancer Care Associates
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

import warnings
from typing import cast

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from . import bounds, imginterp, interppoints, pylinacwrapper
from .types import TwoNumbers

DEFAULT_BB_CONSISTENCY_TOL = 0.2  # mm

# A scaling factor utilised during the BB finding. The user provides
# a 'bb_diameter' parameter. The BB finding algorithm is then repeated
# with that BB size scaled according to the following factors.
# This is undergone so that should there be panel artefacts/noise
# that would cause internally inconsistent bb centre detection, this
# is flagged and an error is raised.
BB_SIZE_FACTORS_TO_SEARCH_OVER = [
    0.5,
    0.55,
    0.6,
    0.65,
    0.7,
    0.75,
    0.8,
    0.85,
    0.9,
    0.95,
    1.0,
]

# Retry limit on BB finding in case of an error.
DEFAULT_BB_REPEATS = 6

# The standard deviation of noise that is applied to initial bb
# positions so that the initial position isn't used in the same way
# exactly everytime.
JITTER_SIGMA = 0.2  # mm


def find_bb_centre(
    x: "np.ndarray",
    y: "np.ndarray",
    image: "np.ndarray",
    bb_diameter: float,
    edge_lengths: TwoNumbers,
    penumbra: float,
    field_centre: TwoNumbers,
    field_rotation: float,
    bb_repeats: int = DEFAULT_BB_REPEATS,
    bb_consistency_tol: float = DEFAULT_BB_CONSISTENCY_TOL,
    skip_pylinac=False,
    maximum_deviation_from_initial=None,
) -> TwoNumbers:
    """Search for a rotationally symmetric object within the image."""

    field = imginterp.create_interpolated_field(x, y, image)

    if skip_pylinac:
        initial_bb_centre = field_centre
    else:
        try:
            initial_bb_centre = pylinacwrapper.find_bb_only(
                x, y, image, edge_lengths, penumbra, field_centre, field_rotation
            )
        except ValueError:
            initial_bb_centre = field_centre

    if initial_bb_centre is None:
        initial_bb_centre = field_centre

    if maximum_deviation_from_initial is None:
        # This is needed to account for the issue that a "flat field" is
        # perfectly rotationally symmetric. Therefore a limitation
        # of this approach is, cannot search within the flat field
        # region at all. The following limits the search radius.
        maximum_deviation_from_initial = bb_diameter / 2

    bb_bounds = define_bb_bounds(
        field_centre=field_centre,
        edge_lengths=edge_lengths,
        bb_diameter=bb_diameter,
        initial_bb_centre=initial_bb_centre,
        maximum_deviation_from_initial=maximum_deviation_from_initial,
    )

    bb_centre = optimise_bb_centre(
        field=field,
        bb_diameter=bb_diameter,
        field_centre=field_centre,
        initial_bb_centre=initial_bb_centre,
        bb_bounds=bb_bounds,
        bb_repeats=bb_repeats,
        bb_consistency_tol=bb_consistency_tol,
    )

    return bb_centre


def optimise_bb_centre(
    field: imginterp.Field,
    bb_diameter: float,
    field_centre: TwoNumbers,
    initial_bb_centre: TwoNumbers,
    bb_bounds,
    bb_repeats=DEFAULT_BB_REPEATS,
    bb_consistency_tol=DEFAULT_BB_CONSISTENCY_TOL,
) -> TwoNumbers:
    """A recursive loop that searches for a rotationally symmetric object."""

    all_centre_predictions = np.array(
        _bb_finding_repetitions(
            field=field,
            bb_diameter=bb_diameter,
            initial_bb_centre=initial_bb_centre,
            bb_bounds=bb_bounds,
            field_centre=field_centre,
        )
    )

    median_of_predictions: TwoNumbers = np.nanmedian(all_centre_predictions, axis=0)

    diff = np.abs(all_centre_predictions - median_of_predictions)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        within_tolerance = cast(np.ndarray, np.all(diff < bb_consistency_tol, axis=1))
        within_tolerance[np.isnan(within_tolerance)] = False

    assert len(within_tolerance) == len(BB_SIZE_FACTORS_TO_SEARCH_OVER)

    if np.sum(within_tolerance) >= len(BB_SIZE_FACTORS_TO_SEARCH_OVER) - 1:
        return median_of_predictions

    if bb_repeats == 0:
        raise ValueError(
            "Unable to determine BB position within designated repeats. "
            "This is likely due to the BB centre not being able to be "
            "consistently determined. Predictions thus far were the "
            "following:\n"
            f"    {np.round(all_centre_predictions, 2)}\n"
            "Initial bb centre for this iteration was:\n"
            f"    {np.round(initial_bb_centre, 2)}\n"
            "BB bounds were set to:\n"
            f"    {np.round(bb_bounds, 2)}"
        )

    return optimise_bb_centre(
        field=field,
        bb_diameter=bb_diameter,
        field_centre=field_centre,
        initial_bb_centre=median_of_predictions,
        bb_bounds=bb_bounds,
        bb_repeats=bb_repeats - 1,
        bb_consistency_tol=bb_consistency_tol,
    )


def define_bb_bounds(
    field_centre,
    edge_lengths,
    bb_diameter,
    initial_bb_centre,
    maximum_deviation_from_initial,
):
    """Define the bounds beyond which a BB is not allowed to be searched for.

    The bounds are defined by two constraints. The first being that the
    BB is not to be searched for outside of the field itself. These
    second constraint however stems as a fundamental result of the
    unique approach being used for this WLutz algorithm.

    This WLutz algorithm was designed to try and be sufficiently
    different from others in use so that there were non-overlapping
    failure modes. The BB algorithm is designed to find regions of the
    field that have the most rotational symmetry about a given axis
    (the bb_centre). There is a fatal flaw in this approach however.
    The flat region of a field is also rotationally symmetric. In order
    to work around this issue the initial position of the ball bearing
    is chosen to be close (within a bb diameter) to it's true location
    and the search area is limited to be within that bb shape.

    The second portion of these bounds definition is defining that
    region which cannot be searched over due to it being too far away
    from the initial position.
    """
    distances_from_centre_to_field_edge = np.array(edge_lengths) / 2 - bb_diameter / 2

    circle_centre_bounds = [
        (
            np.max(
                [
                    field_centre[0] - distances_from_centre_to_field_edge[0],
                    initial_bb_centre[0] - maximum_deviation_from_initial,
                ]
            ),
            np.min(
                [
                    field_centre[0] + distances_from_centre_to_field_edge[0],
                    initial_bb_centre[0] + maximum_deviation_from_initial,
                ]
            ),
        ),
        (
            np.max(
                [
                    field_centre[1] - distances_from_centre_to_field_edge[1],
                    initial_bb_centre[1] - maximum_deviation_from_initial,
                ]
            ),
            np.min(
                [
                    field_centre[1] + distances_from_centre_to_field_edge[1],
                    initial_bb_centre[1] + maximum_deviation_from_initial,
                ]
            ),
        ),
    ]

    return circle_centre_bounds


def _bb_finding_repetitions(
    field,
    bb_diameter,
    initial_bb_centre,
    bb_bounds,
    field_centre,
):
    """Iterate through each of the BB size factors and get a bb centre
    prodiction for each."""
    all_centre_predictions = []
    for bb_size_factor in BB_SIZE_FACTORS_TO_SEARCH_OVER:
        jittered_initial_bb_centre = _jitter_initial_bb_centre(initial_bb_centre)

        prediction_with_adjusted_bb_size = _minimise_bb(
            field=field,
            field_centre=field_centre,
            bb_diameter=bb_diameter * bb_size_factor,
            initial_bb_centre=jittered_initial_bb_centre,
            bb_bounds=bb_bounds,
            set_nan_if_at_bounds=True,
        )

        all_centre_predictions.append(prediction_with_adjusted_bb_size)

    return all_centre_predictions


def _minimise_bb(
    field,
    field_centre,
    bb_diameter,
    initial_bb_centre,
    bb_bounds,
    set_nan_if_at_bounds=False,
    retries=1,
):
    """Use scipy's basinhopping to find a rotationally symmetric object."""
    to_minimise_edge_agreement = create_bb_to_minimise(
        field=field, bb_diameter=bb_diameter
    )

    bb_centre = bb_basinhopping(
        to_minimise_edge_agreement, bb_bounds, initial_bb_centre
    )

    if bounds.check_if_at_bounds(bb_centre, bb_bounds):
        if set_nan_if_at_bounds:
            return _single_minimise_retry(
                field=field,
                field_centre=field_centre,
                bb_diameter=bb_diameter,
                initial_bb_centre=initial_bb_centre,
                bb_bounds=bb_bounds,
                set_nan_if_at_bounds=set_nan_if_at_bounds,
                retries=retries,
            )
        else:
            raise ValueError("BB found at bounds, likely incorrect")

    if np.all(np.array(bb_centre) == np.all(initial_bb_centre)):
        return _single_minimise_retry(
            field=field,
            field_centre=field_centre,
            bb_diameter=bb_diameter,
            initial_bb_centre=initial_bb_centre,
            bb_bounds=bb_bounds,
            set_nan_if_at_bounds=set_nan_if_at_bounds,
            retries=retries,
        )

    return bb_centre


def _jitter_initial_bb_centre(initial_bb_centre):
    jittered_initial_bb_centre = np.array(initial_bb_centre) + np.random.normal(
        loc=0, scale=JITTER_SIGMA, size=2
    )

    return jittered_initial_bb_centre


def _single_minimise_retry(
    field,
    field_centre,
    bb_diameter,
    initial_bb_centre,
    bb_bounds,
    set_nan_if_at_bounds,
    retries,
):
    """Recursively retry the minimisation with a jittered initial position."""
    if retries == 0:
        return [np.nan, np.nan]

    jittered_initial_bb_centre = _jitter_initial_bb_centre(initial_bb_centre)

    return _minimise_bb(
        field=field,
        field_centre=field_centre,
        bb_diameter=bb_diameter,
        initial_bb_centre=jittered_initial_bb_centre,
        bb_bounds=bb_bounds,
        set_nan_if_at_bounds=set_nan_if_at_bounds,
        retries=retries - 1,
    )


def bb_basinhopping(to_minimise, bb_bounds, initial_bb_centre):
    bb_results = scipy.optimize.basinhopping(
        to_minimise,
        initial_bb_centre,
        T=1,
        niter=200,
        niter_success=5,
        stepsize=0.25,
        minimizer_kwargs={"method": "L-BFGS-B", "bounds": bb_bounds},
    )

    return bb_results.x


def create_bb_to_minimise(field, bb_diameter):
    """This is a numpy vectorised version of `create_bb_to_minimise_simple`"""

    points_to_check_edge_agreement, dist = interppoints.create_bb_points_function(
        bb_diameter
    )
    dist_mask = np.unique(dist)[:, None] == dist[None, :]
    num_in_mask = np.sum(dist_mask, axis=1)
    mask_count_per_item = np.sum(num_in_mask[:, None] * dist_mask, axis=0)
    mask_mean_lookup = np.where(dist_mask)[0]

    def to_minimise_edge_agreement(centre):
        x, y = points_to_check_edge_agreement(centre)

        results = field(x, y)
        masked_results = results * dist_mask
        mask_mean = np.sum(masked_results, axis=1) / num_in_mask
        diff_to_mean_square = (results - mask_mean[mask_mean_lookup]) ** 2
        mean_of_layers = np.sum(diff_to_mean_square[1::] / mask_count_per_item[1::]) / (
            len(mask_mean) - 1
        )

        return mean_of_layers

    return to_minimise_edge_agreement


def create_bb_to_minimise_simple(field, bb_diameter):
    points_to_check_edge_agreement, dist = interppoints.create_bb_points_function(
        bb_diameter
    )
    dist_mask = np.unique(dist)[:, None] == dist[None, :]

    def to_minimise_edge_agreement(centre):
        x, y = points_to_check_edge_agreement(centre)

        total_minimisation = 0

        for current_mask in dist_mask[1::]:
            current_layer = field(x[current_mask], y[current_mask])
            total_minimisation += np.mean((current_layer - np.mean(current_layer)) ** 2)

        return total_minimisation / (len(dist_mask) - 1)

    return to_minimise_edge_agreement
