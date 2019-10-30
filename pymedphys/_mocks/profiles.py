# Copyright (C) 2019 Cancer Care Associates

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


import numpy as np
from scipy.special import erf, erfinv  # pylint: disable=no-name-in-module


def gaussian_cdf(x, mu=0, sig=1):
    x = np.array(x, copy=False)
    return 0.5 * (1 + erf((x - mu) / (sig * np.sqrt(2))))


def scaled_penumbra_sig(profile_shoulder_edge=0.8):
    sig = 1 / (2 * np.sqrt(2) * erfinv(profile_shoulder_edge * 2 - 1))

    return sig


def create_profile_function(centre, field_width, penumbra_width):
    sig = scaled_penumbra_sig() * penumbra_width
    mu = [centre - field_width / 2, centre + field_width / 2]

    def profile(x):
        x = np.array(x, copy=False)
        return gaussian_cdf(x, mu[0], sig) * gaussian_cdf(-x, -mu[1], sig)

    return profile


def rotate_coords(x, y, theta):
    x_prime = x * np.cos(theta) + y * np.sin(theta)
    y_prime = -x * np.sin(theta) + y * np.cos(theta)

    return x_prime, y_prime


def create_rectangular_field_function(centre, side_lengths, penumbra_width, rotation=0):
    width_profile = create_profile_function(0, side_lengths[0], penumbra_width)
    length_profile = create_profile_function(0, side_lengths[1], penumbra_width)

    theta = -rotation / 180 * np.pi

    def field(x, y):
        x = np.array(x, copy=False)
        y = np.array(y, copy=False)
        x_shifted = x - centre[0]
        y_shifted = y - centre[1]
        x_rotated, y_rotated = rotate_coords(x_shifted, y_shifted, theta)

        return width_profile(x_rotated) * length_profile(y_rotated)

    return field


def create_square_field_function(centre, side_length, penumbra_width, rotation=0):

    side_lengths = [side_length, side_length]
    return create_rectangular_field_function(
        centre, side_lengths, penumbra_width, rotation
    )
