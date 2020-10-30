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


from pymedphys._imports import numpy as np
from pymedphys._imports import scipy


def gaussian_cdf(x, mu=0, sig=1):
    x = np.array(x, copy=False)
    return 0.5 * (1 + scipy.special.erf((x - mu) / (sig * np.sqrt(2))))


def scaled_penumbra_sig(profile_shoulder_edge=0.8):
    sig = 1 / (2 * np.sqrt(2) * scipy.special.erfinv(profile_shoulder_edge * 2 - 1))

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
