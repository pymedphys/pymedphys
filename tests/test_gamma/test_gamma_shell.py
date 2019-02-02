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


"""Tests for npgamma."""

import numpy as np
from pymedphys.gamma import gamma_shell, calculate_coordinates_shell


def test_lower_dose_threshold():
    """Verify that the lower dose threshold works as expected"""
    ref = [0, 1, 1.9, 2, 2.1, 3, 4, 5, 10, 10]
    coords_ref = (np.arange(len(ref)),)

    evl = [10]*(len(ref) + 2)
    coords_evl = (np.arange(len(evl)) - 4,)

    result = gamma_shell(coords_ref, ref, coords_evl, evl, 10, 1)

    assert np.array_equal(ref < 0.2*np.max(ref), np.isnan(result))


class TestGamma():
    """Testing class."""

    def setup_method(self):
        """Run before each test."""
        grid_x = np.arange(0, 1, 0.1)
        grid_y = np.arange(0, 1.2, 0.1)
        grid_z = np.arange(0, 1.4, 0.1)
        self.dimensions = (len(grid_x), len(grid_y), len(grid_z))
        self.coords = (grid_x, grid_y, grid_z)

        self.reference = np.zeros(self.dimensions)
        self.reference[3:-2:, 4:-2:, 5:-2:] = 1.015

        self.evaluation = np.zeros(self.dimensions)
        self.evaluation[2:-2:, 2:-2:, 2:-2:] = 1

        self.expected_gamma = np.zeros(self.dimensions)
        self.expected_gamma[2:-2:, 2:-2:, 2:-2:] = 0.4
        self.expected_gamma[3:-3:, 3:-3:, 3:-3:] = 0.7
        self.expected_gamma[4:-4:, 4:-4:, 4:-4:] = 1
        self.expected_gamma[3:-2:, 4:-2:, 5:-2:] = 0.5

    def test_regression_of_gamma_3d(self):
        """Test for changes in expected 3D gamma."""
        self.gamma3d = np.round(gamma_shell(
            self.coords, self.reference,
            self.coords, self.evaluation,
            3, 0.3, lower_percent_dose_cutoff=0), decimals=1)

        assert np.all(self.expected_gamma == self.gamma3d)

    def test_regression_of_gamma_2d(self):
        """Test for changes in expected 2D gamma."""
        self.gamma2d = np.round(gamma_shell(
            self.coords[1::], self.reference[5, :, :],
            self.coords[1::], self.evaluation[5, :, :],
            3, 0.3, lower_percent_dose_cutoff=0), decimals=1)

        assert np.all(self.expected_gamma[5, :, :] == self.gamma2d)

    def test_regression_of_gamma_1d(self):
        """Test for changes in expected 3D gamma."""
        self.gamma1d = np.round(gamma_shell(
            self.coords[2], self.reference[5, 5, :],
            self.coords[2], self.evaluation[5, 5, :],
            3, 0.3, lower_percent_dose_cutoff=0), decimals=1)

        assert np.all(self.expected_gamma[5, 5, :] == self.gamma1d)

    def test_coords_stepsize(self):
        """Testing correct stepsize implementation.

        Confirm that the the largest distance between one point and any other
        is less than the defined step size
        """
        distance_step_size = 0.1
        num_dimensions = 3
        distance = 1

        x, y, z = calculate_coordinates_shell(
            distance, num_dimensions, distance_step_size)

        distance_between_coords = np.sqrt(
            (x[:, None] - x[None, :])**2 +
            (y[:, None] - y[None, :])**2 +
            (z[:, None] - z[None, :])**2)

        distance_between_coords[
            distance_between_coords == 0] = np.nan

        largest_difference = np.max(np.nanmin(distance_between_coords, axis=0))

        assert largest_difference <= distance_step_size
        assert largest_difference > distance_step_size * 0.9

    def test_distance_0_gives_1_point(self):
        """Testing correct stepsize implementation.

        Confirm that the the largest distance between one point and any other
        is less than the defined step size
        """
        distance_step_size = 0.03
        num_dimensions = 3
        distance = 0

        x, y, z = calculate_coordinates_shell(
            distance, num_dimensions, distance_step_size)

        assert len(x) == 1 & len(y) == 1 & len(z) == 1

    # def test_calc_by_sections(self):
    #     """Testing that splitting into sections doesn't change the result."""
    #     self.concurrent_reduction = np.round(gamma_shell(
    #         self.coords, self.reference,
    #         self.coords, self.evaluation,
    #         0.03, 0.3, max_concurrent_calc_points=10000), decimals=3)

    #     # print(self.expected_gamma - self.concurrent_reduction)
    #     assert np.all(self.expected_gamma == self.concurrent_reduction)
