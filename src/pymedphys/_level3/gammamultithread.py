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


import numpy as np

from multiprocessing import Process, Queue

import psutil

# from .._level2.gammashell import initialisation


def gamma_multithread(coords_reference, dose_reference,
                      coords_evaluation, dose_evaluation,
                      dose_percent_threshold, distance_mm_threshold,
                      lower_percent_dose_cutoff=20, interp_fraction=10,
                      max_gamma=np.inf, local_gamma=False,
                      global_normalisation=None, skip_once_passed=False,
                      mask_reference=True):
    """Compare two dose grids with the gamma index.

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
        This is always applied to the evaluation grid, and then also applied
        to the reference grid if `mask_reference` is set to `True`.
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
    mask_reference : bool
        Whether or not the `lower_percent_dose_cutoff` is applied to the
        reference as well as the evaluation grid.

    Returns
    -------
    gamma : np.ndarray
        The array of gamma values the same shape as that
        given by the evaluation coordinates and dose.
    """
    (
        coords_reference, coords_evaluation, global_dose_threshold,
        maximum_test_distance,
        evaluation_points_to_calc, distance_step_size, reference_interpolation
    ) = initialisation(
        coords_reference, dose_reference, coords_evaluation,
        dose_evaluation, global_normalisation,
        dose_percent_threshold, distance_mm_threshold,
        interp_fraction, lower_percent_dose_cutoff, max_gamma,
        mask_reference)

    dose_evaluation_flat = np.ravel(dose_evaluation)

    mesh_coords_evaluation = np.meshgrid(*coords_evaluation, indexing='ij')
    coords_evaluation_flat = [
        np.ravel(item)
        for item in mesh_coords_evaluation]

    evaluation_index = np.arange(len(dose_evaluation_flat))
    np.random.shuffle(evaluation_index)
    thread_indicies = np.array_split(evaluation_index, num_threads)

    output = Queue()

    kwargs = {
        "coords_reference": coords_reference,
        "num_dimensions": len(coords_evaluation),
        "reference_interpolation": reference_interpolation,
        "lower_dose_cutoff": lower_dose_cutoff,
        "distance_threshold": distance_threshold,
        "dose_threshold": dose_threshold,
        "distance_step_size": distance_step_size,
        "max_concurrent_calc_points": max_concurrent_calc_points / num_threads,
        "maximum_test_distance": maximum_test_distance}

    for thread_index in thread_indicies:
        thread_index.sort()
        thread_dose_evaluation = dose_evaluation_flat[thread_index]
        thread_coords_evaluation = [
            coords[thread_index]
            for coords in coords_evaluation_flat]
        kwargs['dose_evaluation'] = thread_dose_evaluation
        kwargs['mesh_coords_evaluation'] = thread_coords_evaluation

        Process(
            target=_new_thread,
            args=(
                kwargs, output, thread_index,
                np.nan * np.ones_like(dose_evaluation_flat))).start()

    gamma_flat = np.nan * np.ones_like(dose_evaluation_flat)

    for i in range(num_threads):
        result = output.get()
        thread_reference = np.invert(np.isnan(result))
        gamma_flat[thread_reference] = result[thread_reference]

    assert np.all(np.invert(np.isnan(gamma_flat)))

    gamma_flat[np.isinf(gamma_flat)] = np.nan
    gamma = np.reshape(gamma_flat, np.shape(dose_evaluation))

    return gamma


def _calculate_min_dose_difference_by_slice(
        max_concurrent_calc_points,
        num_dimensions, mesh_coords_evaluation, to_be_checked,
        reference_interpolation, dose_evaluation,
        coordinates_at_distance_kernel, **kwargs):
    """Determine minimum dose differences.
    Calculation is made with the evaluation set divided into slices. This
    enables less RAM usage.
    """
    all_checks = np.where(to_be_checked)
    min_dose_difference = (np.nan * np.ones_like(all_checks[0]))

    num_slices = np.floor(
        len(coordinates_at_distance_kernel[0]) *
        len(all_checks[0]) / max_concurrent_calc_points) + 1

    index = np.arange(len(all_checks[0]))
    np.random.shuffle(index)
    sliced = np.array_split(index, num_slices)

    for current_slice in sliced:
        current_to_be_checked = np.zeros_like(to_be_checked).astype(bool)
        current_to_be_checked[[
            item[current_slice] for
            item in all_checks]] = True

        assert np.all(to_be_checked[current_to_be_checked])

        min_dose_difference[np.sort(current_slice)] = (
            _calculate_min_dose_difference(
                num_dimensions, mesh_coords_evaluation, current_to_be_checked,
                reference_interpolation, dose_evaluation,
                coordinates_at_distance_kernel))

    assert np.all(np.invert(np.isnan(min_dose_difference)))

    return min_dose_difference


def _new_thread(kwargs, output, thread_index, gamma_store):
    gamma_store[thread_index] = _calculation_loop(**kwargs)
    output.put(gamma_store)


def _calculation_loop(**kwargs):
    """Iteratively calculates gamma at increasing distances."""
    dose_valid = kwargs['dose_evaluation'] >= kwargs['lower_dose_cutoff']
    gamma_valid = np.ones_like(kwargs['dose_evaluation']).astype(bool)
    running_gamma = np.inf * np.ones_like(kwargs['dose_evaluation'])
    distance = 0

    while True:
        to_be_checked = (
            dose_valid & gamma_valid)

        coordinates_at_distance_kernel = _calculate_coordinates_kernel(
            distance, kwargs['num_dimensions'], kwargs['distance_step_size'])
        min_dose_difference = _calculate_min_dose_difference_by_slice(
            to_be_checked=to_be_checked,
            coordinates_at_distance_kernel=coordinates_at_distance_kernel,
            **kwargs)

        gamma_at_distance = np.sqrt(
            min_dose_difference ** 2 / kwargs['dose_threshold'] ** 2 +
            distance ** 2 / kwargs['distance_threshold'] ** 2)

        running_gamma[to_be_checked] = np.min(
            np.vstack((
                gamma_at_distance, running_gamma[to_be_checked]
            )), axis=0)

        gamma_valid = running_gamma > distance / kwargs['distance_threshold']

        distance += kwargs['distance_step_size']

        if (
                (np.sum(to_be_checked) == 0) |
                (distance > kwargs['maximum_test_distance'])):
            break

    return running_gamma
