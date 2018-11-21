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
                dose_threshold, distance_mm_threshold,
                lower_dose_cutoff=0, distance_step_size=None,
                maximum_test_distance=np.inf):
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
    dose_threshold : float
        An absolute dose threshold.
        If you wish to use 3% of maximum reference dose input
        np.max(dose_reference) * 0.03 here.
    distance_mm_threshold : float
        The gamma distance threshold. Units must
        match of the coordinates given.
    lower_dose_cutoff : :obj:`float`, optional
        The lower dose cutoff below
        which gamma will not be calculated.
    distance_step_size : :obj:`float`, optional
        The step size to use in
        within the reference grid interpolation. Defaults to a tenth of the
        distance threshold as recommended within
        <http://dx.doi.org/10.1118/1.2721657>.
    maximum_test_distance : :obj:`float`, optional
        The distance beyond
        which searching will stop. Defaults to np.inf. To speed up
        calculation it is recommended that this parameter is set to
        something reasonable such as 2*distance_mm_threshold

    Returns
    -------
    gamma : np.ndarray
        The array of gamma values the same shape as that
        given by the evaluation coordinates and dose.
    """
    coords_reference, coords_evaluation = run_input_checks(
        coords_reference, dose_reference,
        coords_evaluation, dose_evaluation)

    if distance_step_size is None:
        distance_step_size = distance_mm_threshold / 10

    reference_interpolation = RegularGridInterpolator(
        coords_reference, np.array(dose_reference),
        bounds_error=False, fill_value=np.inf
    )

    dose_evaluation = np.array(dose_evaluation)

    dose_above_threshold = dose_evaluation >= lower_dose_cutoff
    still_searching_for_gamma = np.ones_like(
        dose_evaluation).astype(bool)
    current_gamma = np.inf * np.ones_like(dose_evaluation)
    distance = 0

    while True:
        to_be_checked = (
            dose_above_threshold & still_searching_for_gamma)

        min_dose_difference = calculate_min_dose_difference(
            reference_interpolation, coords_evaluation, dose_evaluation,
            distance, distance_step_size, to_be_checked)

        gamma_at_distance = np.sqrt(
            min_dose_difference ** 2 / dose_threshold ** 2 +
            distance ** 2 / distance_mm_threshold ** 2)

        current_gamma[to_be_checked] = np.min(
            np.vstack((
                gamma_at_distance, current_gamma[to_be_checked]
            )), axis=0)

        still_searching_for_gamma = (
            current_gamma > distance / distance_mm_threshold)

        distance += distance_step_size

        is_complete = (
            (np.sum(to_be_checked) == 0) | (distance > maximum_test_distance))
        if is_complete:
            break

    gamma = current_gamma
    gamma[np.isinf(gamma)] = np.nan

    # Verify that nans only appear where the dose wasn't above the threshold
    assert np.all(np.invert(np.isnan(gamma[dose_above_threshold])))

    return gamma


def calculate_min_dose_difference(
        reference_interpolation, coords_evaluation, dose_evaluation,
        distance, distance_step_size, to_be_checked):
    """Determine the minimum dose difference.

    Calculated for a given distance from each evaluation point.
    """
    reference_dose = interpolate_reference_dose_at_distance(
        reference_interpolation, coords_evaluation, distance,
        distance_step_size, to_be_checked)

    dose_difference = reference_dose - dose_evaluation[to_be_checked][None, :]
    min_dose_difference = np.min(np.abs(dose_difference), axis=0)

    return min_dose_difference


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
        amount_to_check = np.floor(
            2 * np.pi * distance / distance_step_size).astype(int) + 1  # may need to make this + 2
        theta = np.linspace(0, 2*np.pi, amount_to_check + 1)[:-1:]
        x_coords = distance * np.cos(theta)
        y_coords = distance * np.sin(theta)

        return (x_coords, y_coords)

    elif num_dimensions == 3:
        # Create points along the surface of a sphere (a shell) where no gap
        # between points is larger than the defined distance_step_size
        number_of_rows = np.floor(
            np.pi * distance / distance_step_size).astype(int) + 1  # may need to make this + 2

        elevation = np.linspace(0, np.pi, number_of_rows)
        row_radii = distance * np.sin(elevation)
        row_circumference = 2 * np.pi * row_radii
        amount_in_row = np.floor(
            row_circumference / distance_step_size).astype(int) + 1  # may need to make this + 2

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
