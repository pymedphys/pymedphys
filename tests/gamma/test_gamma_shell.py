# Copyright (C) 2015, 2019 Simon Biggs
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


"""Tests for gamma shell."""


import numpy as np
from pymedphys._gamma.implementation import gamma_shell
from pymedphys._gamma.implementation.shell import calculate_coordinates_shell


def does_gamma_scale_as_expected(
    init_distance_threshold, threshold_ratio, scales_to_test
):
    coords, reference, evaluation, _ = get_dummy_gamma_set()

    all_scales = np.concatenate([[1], scales_to_test])

    distance_thresholds_to_test = init_distance_threshold * all_scales
    dose_thresholds_to_test = distance_thresholds_to_test * threshold_ratio

    gamma_results = []
    for dose, distance in zip(dose_thresholds_to_test, distance_thresholds_to_test):
        gamma_results.append(
            gamma_shell(
                coords,
                reference,
                coords,
                evaluation,
                dose,
                distance,
                lower_percent_dose_cutoff=0,
            )
        )

    for i, scale in enumerate(scales_to_test):
        print(scale)

        abs_diff = np.abs(gamma_results[i + 1] - gamma_results[0] / scale)

        print(np.max(abs_diff))

        assert np.all(abs_diff <= 0.1)


def test_a_set_of_gamma_scaling():
    does_gamma_scale_as_expected(0.6, 10, [2, 3, 4])
    does_gamma_scale_as_expected(0.6, 15, [2, 3, 4])
    does_gamma_scale_as_expected(0.6, 20, [2, 3, 4])


def test_multiple_threshold_inputs():
    coords, reference, evaluation, _ = get_dummy_gamma_set()

    gamma_shell(
        coords,
        reference,
        coords,
        evaluation,
        [3],
        [0.3, 0.5],
        lower_percent_dose_cutoff=0,
    )


def test_lower_dose_threshold():
    """Verify that the lower dose threshold works as expected"""
    ref = [0, 1, 1.9, 2, 2.1, 3, 4, 5, 10, 10]
    coords_ref = (np.arange(len(ref)),)

    evl = [10] * (len(ref) + 2)
    coords_evl = (np.arange(len(evl)) - 4,)

    result = gamma_shell(coords_ref, ref, coords_evl, evl, 10, 1)

    assert np.array_equal(ref < 0.2 * np.max(ref), np.isnan(result))


def get_dummy_gamma_set():
    grid_x = np.arange(0, 1, 0.1)
    grid_y = np.arange(0, 1.2, 0.1)
    grid_z = np.arange(0, 1.4, 0.1)
    dimensions = (len(grid_x), len(grid_y), len(grid_z))
    coords = (grid_x, grid_y, grid_z)

    reference = np.zeros(dimensions)
    reference[3:-2:, 4:-2:, 5:-2:] = 1.015

    evaluation = np.zeros(dimensions)
    evaluation[2:-2:, 2:-2:, 2:-2:] = 1

    expected_gamma = np.zeros(dimensions)
    expected_gamma[2:-2:, 2:-2:, 2:-2:] = 0.4
    expected_gamma[3:-3:, 3:-3:, 3:-3:] = 0.7
    expected_gamma[4:-4:, 4:-4:, 4:-4:] = 1
    expected_gamma[3:-2:, 4:-2:, 5:-2:] = 0.5

    return coords, reference, evaluation, expected_gamma


def test_regression_of_gamma_3d():
    """Test for changes in expected 3D gamma."""
    coords, reference, evaluation, expected_gamma = get_dummy_gamma_set()

    gamma3d = np.round(
        gamma_shell(
            coords, reference, coords, evaluation, 3, 0.3, lower_percent_dose_cutoff=0
        ),
        decimals=1,
    )

    assert np.all(expected_gamma == gamma3d)


def test_regression_of_gamma_2d():
    """Test for changes in expected 2D gamma."""
    coords, reference, evaluation, expected_gamma = get_dummy_gamma_set()

    gamma2d = np.round(
        gamma_shell(
            coords[1::],
            reference[5, :, :],
            coords[1::],
            evaluation[5, :, :],
            3,
            0.3,
            lower_percent_dose_cutoff=0,
        ),
        decimals=1,
    )

    assert np.all(expected_gamma[5, :, :] == gamma2d)


def test_regression_of_gamma_1d():
    """Test for changes in expected 3D gamma."""

    coords, reference, evaluation, expected_gamma = get_dummy_gamma_set()

    gamma1d = np.round(
        gamma_shell(
            coords[2],
            reference[5, 5, :],
            coords[2],
            evaluation[5, 5, :],
            3,
            0.3,
            lower_percent_dose_cutoff=0,
        ),
        decimals=1,
    )

    assert np.all(expected_gamma[5, 5, :] == gamma1d)


def test_coords_stepsize():
    """Testing correct stepsize implementation.

    Confirm that the the largest distance between one point and any other
    is less than the defined step size
    """
    distance_step_size = 0.1
    num_dimensions = 3
    distance = 1

    x, y, z = calculate_coordinates_shell(distance, num_dimensions, distance_step_size)

    distance_between_coords = np.sqrt(
        (x[:, None] - x[None, :]) ** 2
        + (y[:, None] - y[None, :]) ** 2
        + (z[:, None] - z[None, :]) ** 2
    )

    distance_between_coords[distance_between_coords == 0] = np.nan

    largest_difference = np.max(np.nanmin(distance_between_coords, axis=0))

    assert largest_difference <= distance_step_size
    assert largest_difference > distance_step_size * 0.9


def test_distance_0_gives_1_point():
    """Testing correct stepsize implementation.

    Confirm that the the largest distance between one point and any other
    is less than the defined step size
    """
    distance_step_size = 0.1
    num_dimensions = 3
    distance = 0

    x, y, z = calculate_coordinates_shell(distance, num_dimensions, distance_step_size)

    assert len(x) == 1 & len(y) == 1 & len(z) == 1
