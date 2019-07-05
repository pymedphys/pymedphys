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

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import basinhopping
from scipy.interpolate import RegularGridInterpolator

import skimage
import imageio

DEFAULT_CAL_STRING_END = ' cGy.tif'


def align_images(ref_image, moving_image, max_shift=20, max_rotation=30):
    ref_edge_filtered = scharr_gray(ref_image)
    moving_edge_filtered = scharr_gray(moving_image)

    ref_shape = np.shape(ref_edge_filtered)
    ref_x = np.arange(0, ref_shape[0])
    ref_y = np.arange(0, ref_shape[1])

    move_shape = np.shape(moving_edge_filtered)
    move_x = np.arange(0, move_shape[0])
    move_y = np.arange(0, move_shape[1])

    moving_interp = create_image_interpolation((move_x, move_y),
                                               moving_edge_filtered)

    def to_minimise(inputs):
        x_shift = inputs[0]
        y_shift = inputs[1]
        angle = inputs[2]

        interpolated = shift_and_rotate_with_interp(moving_interp,
                                                    (ref_x, ref_y),
                                                    (x_shift, y_shift), angle)

        return np.sum((interpolated - ref_edge_filtered)**2)

    result = basinhopping(to_minimise, [0, 0, 0],
                          minimizer_kwargs={
                              'method':
                              'L-BFGS-B',
                              'bounds': ((-max_shift, max_shift), (-max_shift,
                                                                   max_shift),
                                         (-max_rotation, max_rotation))
                          })

    x_shift, y_shift, angle = result.x

    return x_shift, y_shift, angle


def create_image_interpolation(axes, image):
    x_span, y_span = axes

    return RegularGridInterpolator((x_span, y_span),
                                   image,
                                   bounds_error=False,
                                   fill_value=0)


def shift_and_rotate(image, x_shift, y_shift, angle):
    shape = np.shape(image)
    x_span = np.arange(0, shape[0])
    y_span = np.arange(0, shape[1])

    interp = create_image_interpolation((x_span, y_span), image)

    return shift_and_rotate_with_interp(interp, (x_span, y_span),
                                        (x_shift, y_shift), angle)


def shift_and_rotate_with_interp(interpolation, axes, shifts, angle):
    x_span, y_span = axes
    x_shift, y_shift = shifts

    interpolated = interpolated_rotation(interpolation,
                                         (x_span - x_shift, y_span - y_shift),
                                         angle)

    return interpolated


def interpolated_rotation(interpolation, axes, angle):
    x_span = axes[0]
    y_span = axes[1]

    xx, yy = do_rotation(x_span, y_span, angle)

    return interpolation((xx, yy))


# https://stackoverflow.com/a/29709641/3912576
def do_rotation(x_span, y_span, angle):
    """Generate a meshgrid and rotate it by `angle` degrees."""

    radians = angle * np.pi / 180

    rotation_matrix = np.array([[np.cos(radians),
                                 np.sin(radians)],
                                [-np.sin(radians),
                                 np.cos(radians)]])

    xx, yy = np.meshgrid(x_span, y_span, indexing='ij')
    return np.einsum('ji, mni -> jmn', rotation_matrix, np.dstack([xx, yy]))


def as_gray(image_filter, image, *args, **kwargs):
    gray_image = skimage.color.rgb2gray(image)
    return image_filter(gray_image, *args, **kwargs)


@skimage.color.adapt_rgb.adapt_rgb(as_gray)
def scharr_gray(image):
    return skimage.filters.scharr(image)


def load_image(path):
    return imageio.imread(path)


def load_cal_scans(path, cal_string_end=DEFAULT_CAL_STRING_END):
    path = Path(path)

    cal_pattern = '*' + cal_string_end
    filepaths = path.glob(cal_pattern)

    calibrations = {
        float(path.name.rstrip(cal_string_end)): load_image(path)
        for path in filepaths
    }

    return calibrations
