# Copyright (C) 2015-2018 Simon Biggs
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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


"""Compare two dose grids with the gamma index.

This module is a python implementation of the gamma index.
It computes 1, 2, or 3 dimensional gamma with arbitrary gird sizes while
interpolating on the fly.
This module makes use of some of the ideas presented within
<http://dx.doi.org/10.1118/1.2721657>.
"""

import sys

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from .._level1.gammainputcheck import run_input_checks


def gamma_shell(coords_reference, dose_reference,
                coords_evaluation, dose_evaluation,
                dose_percent_threshold, distance_mm_threshold,
                lower_percent_dose_cutoff=20, interp_fraction=10,
                max_gamma=np.inf, local_gamma=False,
                global_normalisation=None):
    """Compare two dose grids with the gamma index.

    To have this calculate in a timely manner it is recommended to set
    ``maximum_test_distance`` to a value of 2 * ``distance_mm_threshold``. This
    has the downside of having gamma values larger than 2 potentially being
    erroneous.

    Parameters
    ----------
    coords_reference : tuple
        The reference coordinates.
    dose_reference : np.array
        The reference dose grid.
    coords_evaluation : tuple
        The evaluation coordinates.
    dose_evaluation : np.array
        The evaluation dose grid.
    dose_percent_threshold : float
        The percent dose threshold
    distance_mm_threshold : float
        The gamma distance threshold. Units must
        match of the coordinates given.
    lower_percent_dose_cutoff : :obj:`float`, optional
        The percent lower dose cutoff below which gamma will not be calculated.
        If either the evaluation grid, or the interpolated reference grid fall
        below this dose percent then that evaluation point is not used.
    interp_fraction : :obj:`float`, optional
        The fraction which the distance threshold is divided into for
        interpolation. Defaults to 10 as recommended within
        <http://dx.doi.org/10.1118/1.2721657>.
    max_gamma : :obj:`float`, optional
        The maximum gamma searched for. This can be used to speed up
        calculation, once a search distance is reached that would give gamma
        values larger than this parameter, the search stops. Defaults to np.inf
    local_gamma
        Designates local gamma should be used instead of global. Defaults to
        False.
    global_normalisation
        The dose normalisation value that the percent inputs calculate from.
        Defaults to the maximum value of dose_reference.

    Returns
    -------
    gamma : np.ndarray
        The array of gamma values the same shape as that
        given by the evaluation coordinates and dose.
    """
    coords_reference, coords_evaluation = run_input_checks(
        coords_reference, dose_reference,
        coords_evaluation, dose_evaluation)

    if global_normalisation is None:
        global_normalisation = np.max(dose_reference)

    global_dose_threshold = dose_percent_threshold / 100 * global_normalisation
    lower_dose_cutoff = lower_percent_dose_cutoff / 100 * global_normalisation

    distance_step_size = distance_mm_threshold / interp_fraction
    maximum_test_distance = distance_mm_threshold * max_gamma

    reference_interpolation = RegularGridInterpolator(
        coords_reference, np.array(dose_reference),
        bounds_error=False, fill_value=np.inf
    )

    dose_evaluation = np.array(dose_evaluation)

    interpolated_reference_dose = interpolate_reference_dose_at_distance(
        reference_interpolation, coords_evaluation, 0,
        distance_step_size)[0, :]

    interpolated_reference_dose = np.reshape(
        interpolated_reference_dose, np.shape(dose_evaluation))

    reference_dose_interpolation_within_bounds = (
        interpolated_reference_dose != np.inf)
    reference_dose_above_threshold = (
        interpolated_reference_dose >= lower_dose_cutoff)
    evaluation_dose_above_threshold = dose_evaluation >= lower_dose_cutoff

    evaluation_points_to_calc = (
        reference_dose_interpolation_within_bounds &
        reference_dose_above_threshold &
        evaluation_dose_above_threshold
    )

    still_searching_for_gamma = np.ones_like(
        dose_evaluation).astype(bool)
    current_gamma = np.inf * np.ones_like(dose_evaluation)
    distance = 0

    while distance <= maximum_test_distance:
        to_be_checked = (
            evaluation_points_to_calc & still_searching_for_gamma)

        sys.stdout.write(
            '\rCurrent distance: {0:.2f} mm | Number of evaluation points remaining: {1}'.format(
                distance,
                np.sum(to_be_checked)))
        # sys.stdout.flush()

        min_relative_dose_difference = calculate_min_dose_difference(
            reference_interpolation, coords_evaluation, dose_evaluation,
            distance, distance_step_size, to_be_checked, global_dose_threshold,
            dose_percent_threshold, local_gamma)

        gamma_at_distance = np.sqrt(
            min_relative_dose_difference ** 2 +
            (distance / distance_mm_threshold) ** 2)

        current_gamma[to_be_checked] = np.min(
            np.vstack((
                gamma_at_distance, current_gamma[to_be_checked]
            )), axis=0)

        still_searching_for_gamma = (
            current_gamma > distance / distance_mm_threshold)

        distance += distance_step_size

        if np.sum(to_be_checked) == 0:
            break

    gamma = current_gamma
    gamma[np.isinf(gamma)] = np.nan

    # Verify that nans only appear where the dose wasn't above the threshold
    assert np.all(np.invert(np.isnan(gamma[evaluation_points_to_calc])))

    return gamma


def calculate_min_dose_difference(
        reference_interpolation, coords_evaluation, dose_evaluation,
        distance, distance_step_size, to_be_checked, global_dose_threshold,
        dose_percent_threshold, local_gamma):
    """Determine the minimum dose difference.

    Calculated for a given distance from each evaluation point.
    """

    reference_dose = interpolate_reference_dose_at_distance(
        reference_interpolation, coords_evaluation, distance,
        distance_step_size, to_be_checked)

    if local_gamma:
        relative_dose_difference = (
            reference_dose - dose_evaluation[to_be_checked][None, :]
        ) / (reference_dose * dose_percent_threshold / 100)
    else:
        relative_dose_difference = (
            reference_dose - dose_evaluation[to_be_checked][None, :]
        ) / global_dose_threshold

    min_relative_dose_difference = np.min(
        np.abs(relative_dose_difference), axis=0)

    return min_relative_dose_difference


def interpolate_reference_dose_at_distance(
        reference_interpolation, coords_evaluation, distance,
        distance_step_size, to_be_checked=None):
    """Determine the reference dose for the points a given distance away for
    each evaluation coordinate.
    """
    num_dimensions = len(coords_evaluation)

    coordinates_at_distance_shell = calculate_coordinates_shell(
        distance, num_dimensions, distance_step_size)

    sys.stdout.write(' | Points tested per evaluation point: {}'.format(
        np.shape(coordinates_at_distance_shell)[1]))
    sys.stdout.flush()

    mesh_coords_evaluation = np.meshgrid(*coords_evaluation, indexing='ij')

    if to_be_checked is None:
        to_be_checked = np.ones_like(mesh_coords_evaluation[0]).astype(bool)

    # Add the distance shells to each evaluation coordinate to make a set of
    # points to be tested for this given distance
    coordinates_at_distance = []
    for i in range(num_dimensions):
        coordinates_at_distance.append(np.array(
            mesh_coords_evaluation[i][to_be_checked][None, :] +
            coordinates_at_distance_shell[i][:, None])[:, :, None])

    all_points = np.concatenate(coordinates_at_distance, axis=2)
    reference_dose = reference_interpolation(all_points)

    return reference_dose


def calculate_coordinates_shell(distance, num_dimensions, distance_step_size):
    """Create the shell of coordinate shifts for the given testing distance.

    Coordinate shifts are determined to check the reference dose for a
    given distance, dimension, and step size
    """
    if num_dimensions == 1:
        # Output the two points that are of the defined distance in
        # one-dimension
        if distance == 0:
            x_coords = np.array([0])
        else:
            x_coords = np.array([distance, -distance])

        return (x_coords,)

    elif num_dimensions == 2:
        # Create points along the circumference of a circle. The spacing
        # between points is not larger than the defined distance_step_size
        amount_to_check = np.ceil(
            2 * np.pi * distance / distance_step_size).astype(int) + 1
        theta = np.linspace(0, 2*np.pi, amount_to_check + 1)[:-1:]
        x_coords = distance * np.cos(theta)
        y_coords = distance * np.sin(theta)

        return (x_coords, y_coords)

    elif num_dimensions == 3:
        # Create points along the surface of a sphere (a shell) where no gap
        # between points is larger than the defined distance_step_size
        number_of_rows = np.ceil(
            np.pi * distance / distance_step_size).astype(int) + 1

        elevation = np.linspace(0, np.pi, number_of_rows)
        row_radii = distance * np.sin(elevation)
        row_circumference = 2 * np.pi * row_radii
        amount_in_row = np.ceil(
            row_circumference / distance_step_size).astype(int) + 1

        x_coords = []
        y_coords = []
        z_coords = []
        for i, phi in enumerate(elevation):
            azimuth = np.linspace(0, 2*np.pi, amount_in_row[i] + 1)[:-1:]
            x_coords.append(distance * np.sin(phi) * np.cos(azimuth))
            y_coords.append(distance * np.sin(phi) * np.sin(azimuth))
            z_coords.append(distance * np.cos(phi) * np.ones_like(azimuth))

        return (
            np.hstack(x_coords), np.hstack(y_coords), np.hstack(z_coords))

    else:
        raise Exception("No valid dimension")
