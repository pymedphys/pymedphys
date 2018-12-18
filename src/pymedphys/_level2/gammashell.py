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
# Affero General Public License. These additional terms are Sections 1, 5,
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
# from multiprocessing import Process, Queue

import numpy as np
from scipy.interpolate import RegularGridInterpolator

import psutil

from .._level1.gammainputcheck import run_input_checks

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def gamma_shell(coords_reference, dose_reference,
                coords_evaluation, dose_evaluation,
                dose_percent_threshold, distance_mm_threshold,
                lower_percent_dose_cutoff=20, interp_fraction=10,
                max_gamma=np.inf, local_gamma=False,
                global_normalisation=None, skip_once_passed=False,
                mask_evaluation=False, random_subset=None, ram_available=None,
                quiet=False):
    """Compare two dose grids with the gamma index.

    Parameters
    ----------
    coords_reference : tuple
        The reference coordinates.
    dose_reference : np.array
        The reference dose grid. Each point in the reference grid becomes the
        centre of a Gamma ellipsoid. For each point of the reference, nearby
        evaluation points are searched at increasing distances.
    coords_evaluation : tuple
        The evaluation coordinates.
    dose_evaluation : np.array
        The evaluation dose grid. Evaluation here is defined as the grid which
        is interpolated and searched over at increasing distances away from
        each reference point.
    dose_percent_threshold : float
        The percent dose threshold
    distance_mm_threshold : float
        The gamma distance threshold. Units must
        match of the coordinates given.
    lower_percent_dose_cutoff : float, optional
        The percent lower dose cutoff below which gamma will not be calculated.
        By default this is only applied to the reference grid. Set
        :obj:`mask_evaluation` to True to have this apply to the evaluation grid
        also.
    interp_fraction : float, optional
        The fraction which gamma distance threshold is divided into for
        interpolation. Defaults to 10 as recommended within
        <http://dx.doi.org/10.1118/1.2721657>. If a 3 mm distance threshold is chosen
        this default value would mean that the evaluation grid is interpolated at
        a step size of 0.3 mm.
    max_gamma : float, optional
        The maximum gamma searched for. This can be used to speed up
        calculation, once a search distance is reached that would give gamma
        values larger than this parameter, the search stops. Defaults to :obj:`np.inf`
    local_gamma
        Designates local gamma should be used instead of global. Defaults to
        False.
    global_normalisation : float, optional
        The dose normalisation value that the percent inputs calculate from.
        Defaults to the maximum value of :obj:`dose_reference`.
    mask_evaluation : bool
        Whether or not the :obj:`lower_percent_dose_cutoff` is applied to the
        evaluation grid as well as the reference grid.
    random_subset : int, optional
        Used to only calculate a random subset of the reference grid. The
        number chosen is how many random points to calculate.
    ram_available : int, optional
        The number of bytes of RAM available for use by this function. Defaults
        to 0.8 times your total RAM as determined by psutil.

    Returns
    -------
    gamma : np.ndarray
        The array of gamma values the same shape as that
        given by the reference coordinates and dose.
    """

    coords_reference, coords_evaluation = run_input_checks(
        coords_reference, dose_reference,
        coords_evaluation, dose_evaluation)

    if global_normalisation is None:
        global_normalisation = np.max(dose_reference)

    global_dose_threshold = dose_percent_threshold / 100 * global_normalisation
    lower_dose_cutoff = lower_percent_dose_cutoff / 100 * global_normalisation

    if not quiet:
        if local_gamma:
            print('Calcing using local normalisation point for gamma')
        else:
            print('Calcing using global normalisation point for gamma')
        print('Global normalisation set to {} Gy'.format(global_normalisation))
        print('Global dose threshold set to {} Gy ({}%)'.format(
            global_dose_threshold, dose_percent_threshold))
        print('Distance threshold set to {} mm'.format(distance_mm_threshold))
        print('Lower dose cutoff set to {} Gy ({}%)'.format(
            lower_dose_cutoff, lower_percent_dose_cutoff))
        print('')

    distance_step_size = distance_mm_threshold / interp_fraction
    maximum_test_distance = distance_mm_threshold * max_gamma

    evaluation_interpolation = RegularGridInterpolator(
        coords_evaluation, np.array(dose_evaluation),
        bounds_error=False, fill_value=np.inf
    )

    dose_reference = np.array(dose_reference)
    reference_dose_above_threshold = dose_reference >= lower_dose_cutoff

    mesh_coords_reference = np.meshgrid(*coords_reference, indexing='ij')
    flat_mesh_coords_reference = [
        np.ravel(item)
        for item in mesh_coords_reference]

    if mask_evaluation:
        coordinates_at_distance_shell = calculate_coordinates_shell(
            0, len(coords_reference), distance_step_size)

        interpolated_evaluation_dose = interpolate_evaluation_dose_at_distance(
            evaluation_interpolation, flat_mesh_coords_reference,
            coordinates_at_distance_shell)[0, :]

        interpolated_evaluation_dose = np.reshape(
            interpolated_evaluation_dose, np.shape(dose_reference))

        evaluation_dose_interpolation_within_bounds = (
            interpolated_evaluation_dose != np.inf)
        evaluation_dose_above_threshold = (
            interpolated_evaluation_dose >= lower_dose_cutoff)

        reference_points_to_calc = (
            evaluation_dose_interpolation_within_bounds &
            evaluation_dose_above_threshold &
            reference_dose_above_threshold
        )
    else:
        reference_points_to_calc = reference_dose_above_threshold

    reference_points_to_calc = np.ravel(reference_points_to_calc)

    if random_subset is not None:
        to_calc_index = np.where(reference_points_to_calc)[0]

        np.random.shuffle(to_calc_index)
        random_subset_to_calc = np.zeros_like(
            reference_points_to_calc).astype(bool)
        random_subset_to_calc[to_calc_index[0:random_subset]] = True

        reference_points_to_calc = random_subset_to_calc

    flat_dose_reference = np.ravel(dose_reference)

    if ram_available is None:
        memory = psutil.virtual_memory()
        total_memory = memory.total

        ram_available = total_memory * 0.8

    still_searching_for_gamma = np.ones_like(
        flat_dose_reference).astype(bool)
    current_gamma = np.inf * np.ones_like(flat_dose_reference)
    distance = 0
    while distance <= maximum_test_distance:
        to_be_checked = (
            reference_points_to_calc & still_searching_for_gamma)

        if not quiet:
            sys.stdout.write(
                '\rCurrent distance: {0:.2f} mm | Number of reference points remaining: {1}'.format(
                    distance,
                    np.sum(to_be_checked)))
        # sys.stdout.flush()

        min_relative_dose_difference = calculate_min_dose_difference(
            evaluation_interpolation, flat_mesh_coords_reference, flat_dose_reference,
            distance, distance_step_size, to_be_checked, global_dose_threshold,
            dose_percent_threshold, local_gamma, ram_available, quiet)

        gamma_at_distance = np.sqrt(
            min_relative_dose_difference ** 2 +
            (distance / distance_mm_threshold) ** 2)

        current_gamma[to_be_checked] = np.min(
            np.vstack((
                gamma_at_distance, current_gamma[to_be_checked]
            )), axis=0)

        still_searching_for_gamma = (
            current_gamma > distance / distance_mm_threshold)

        if skip_once_passed:
            still_searching_for_gamma = (
                still_searching_for_gamma & (current_gamma >= 1))

        distance += distance_step_size

        if np.sum(to_be_checked) == 0:
            break

    gamma = np.reshape(
        current_gamma, np.shape(dose_reference))
    gamma[np.isinf(gamma)] = np.nan

    # Verify that nans only appear where the dose wasn't above the threshold
    # assert np.all(np.invert(np.isnan(gamma[evaluation_points_to_calc])))

    with np.errstate(invalid='ignore'):
        gamma_greater_than_ref = gamma > max_gamma
        gamma[gamma_greater_than_ref] = max_gamma

    print('')

    return gamma


def calculate_min_dose_difference(
        evaluation_interpolation, flat_mesh_coords_reference,
        flat_dose_reference,
        distance, distance_step_size, to_be_checked, global_dose_threshold,
        dose_percent_threshold, local_gamma, ram_available, quiet):
    """Determine the minimum dose difference.

    Calculated for a given distance from each reference point.
    """

    min_relative_dose_difference = np.nan * np.ones_like(
        flat_dose_reference[to_be_checked])

    num_dimensions = len(flat_mesh_coords_reference)

    coordinates_at_distance_shell = calculate_coordinates_shell(
        distance, num_dimensions, distance_step_size)

    num_points_in_shell = np.shape(coordinates_at_distance_shell)[1]

    estimated_ram_needed = (np.uint64(num_points_in_shell)
                            * np.sum(to_be_checked).astype(np.uint64)
                            * np.uint64(32)
                            * np.uint64(num_dimensions)
                            * np.uint64(2))

    num_slices = np.floor(
        estimated_ram_needed / ram_available).astype(np.uint64) + 1

    if not quiet:
        sys.stdout.write(' | Points tested per reference point: {} | RAM split count: {}'.format(
            num_points_in_shell, num_slices))
        sys.stdout.flush()

    all_checks = np.where(np.ravel(to_be_checked))[0]
    index = np.arange(len(all_checks))
    sliced = np.array_split(index, num_slices)

    sorted_sliced = [
        np.sort(current_slice) for current_slice in sliced
    ]

    for current_slice in sorted_sliced:
        to_be_checked_sliced = np.zeros_like(to_be_checked).astype(bool)
        to_be_checked_sliced[all_checks[current_slice]] = True

        assert np.all(to_be_checked[to_be_checked_sliced])

        evaluation_dose = interpolate_evaluation_dose_at_distance(
            evaluation_interpolation, flat_mesh_coords_reference,
            coordinates_at_distance_shell, to_be_checked_sliced)

        if local_gamma:
            with np.errstate(divide='ignore'):
                relative_dose_difference = (
                    evaluation_dose -
                    flat_dose_reference[to_be_checked_sliced][None, :]
                ) / (
                    flat_dose_reference[to_be_checked_sliced][None, :] *
                    dose_percent_threshold / 100
                )
        else:
            relative_dose_difference = (
                evaluation_dose -
                flat_dose_reference[to_be_checked_sliced][None, :]
            ) / global_dose_threshold

        min_relative_dose_difference[current_slice] = np.min(
            np.abs(relative_dose_difference), axis=0)

    # assert np.all(np.invert(np.isnan(min_relative_dose_difference)))

    return min_relative_dose_difference


def interpolate_evaluation_dose_at_distance(
        evaluation_interpolation, flat_mesh_coords_reference,
        coordinates_at_distance_shell, to_be_checked=None):
    """Determine the evaluation dose for the points a given distance away for
    each reference coordinate.
    """
    if to_be_checked is None:
        to_be_checked = np.ones_like(
            flat_mesh_coords_reference[0]).astype(bool)

    # Add the distance shells to each evaluation coordinate to make a set of
    # points to be tested for this given distance
    coordinates_at_distance = []
    for shell_coord, eval_coord in zip(coordinates_at_distance_shell,
                                       flat_mesh_coords_reference):
        # import pdb
        # pdb.set_trace()

        coordinates_at_distance.append(np.array(
            eval_coord[to_be_checked][None, :] +
            shell_coord[:, None])[:, :, None])

    all_points = np.concatenate(coordinates_at_distance, axis=2)
    evaluation_dose = evaluation_interpolation(all_points)

    return evaluation_dose


def calculate_coordinates_shell(distance, num_dimensions, distance_step_size):
    """Create the shell of coordinate shifts for the given testing distance.

    Coordinate shifts are determined to check the evaluation dose for a
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
