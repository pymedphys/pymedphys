# Copyright (C) 2020 Simon Biggs

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

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy

from . import profiles


def create_bb_attenuation_func(diameter, penumbra, max_attenuation):
    dx = diameter / 100
    radius = diameter / 2
    image_half_width = penumbra * 2 + radius

    x = np.arange(-image_half_width, image_half_width + dx, dx)
    xx, yy = np.meshgrid(x, x)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        z = np.sqrt(radius ** 2 - xx ** 2 - yy ** 2) / radius

    z[np.isnan(z)] = 0

    sig = profiles.scaled_penumbra_sig() * penumbra
    sig_pixel = sig / dx

    filtered = scipy.ndimage.gaussian_filter(z, sig_pixel)
    interp = scipy.interpolate.RegularGridInterpolator(
        (x, x), filtered, bounds_error=False, fill_value=None
    )

    def attenuation(x, y):
        return 1 - interp((x, y)) * max_attenuation

    return attenuation


def create_test_image(
    x,
    y,
    field_centre,
    field_side_lengths,
    field_penumbra,
    field_rotation,
    bb_centre,
    bb_diameter,
    bb_max_attenuation,
):
    field = create_field_with_bb_func(
        field_centre,
        field_side_lengths,
        field_penumbra,
        field_rotation,
        bb_centre,
        bb_diameter,
        bb_max_attenuation,
    )

    xx, yy = np.meshgrid(x, y)
    img = field(xx, yy)

    return img


def create_field_with_bb_func(
    field_centre,
    field_side_lengths,
    field_penumbra,
    field_rotation,
    bb_centre,
    bb_diameter,
    bb_max_attenuation,
):
    field = profiles.create_rectangular_field_function(
        field_centre, field_side_lengths, field_penumbra, field_rotation
    )

    bb_penumbra = field_penumbra / 3
    bb_attenuation_map = create_bb_attenuation_func(
        bb_diameter, bb_penumbra, bb_max_attenuation
    )

    def field_with_bb(x, y):
        return field(x, y) * bb_attenuation_map(x - bb_centre[0], y - bb_centre[1])

    return field_with_bb


def stripes_artefact_func(x, attenuation=0.05, period=1.6):
    sin_result = np.sin(x * 2 * np.pi / period)
    return 1 - (sin_result + 1) / 2 * attenuation


def create_striped_field_func(field, attenuation=0.05, period=1.6):
    def striped_field(x, y):
        return stripes_artefact_func(x, attenuation, period) * field(x, y)

    return striped_field


def create_saturated_field_func(field, level=0.9):
    def saturated_field(x, y):
        result = field(x, y)
        result[result > level] = level

        return result

    return saturated_field
