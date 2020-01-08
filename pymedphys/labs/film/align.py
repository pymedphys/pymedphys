# Copyright (C) 2019 Simon Biggs, Cancer Care Associates

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

from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import basinhopping

import skimage
import skimage.color.adapt_rgb
import skimage.filters


def align_images(
    ref_axes, ref_image, moving_axes, moving_image, max_shift=np.inf, max_rotation=30
):
    ref_edge_filtered = scharr_gray(ref_image)
    moving_edge_filtered = scharr_gray(moving_image)

    # blurred_ref_edge = skimage.filters.gaussian(ref_edge_filtered)
    # valid_region = np.where(blurred_ref_edge > np.max(blurred_ref_edge)/2)

    filter_loss = 0
    try:
        assert np.shape(ref_image)[0] - np.shape(ref_edge_filtered)[0] == filter_loss
    except AssertionError:
        print(np.shape(ref_image))
        print(np.shape(ref_edge_filtered))
        raise

    ref_x, ref_y = ref_axes
    move_x, move_y = moving_axes

    moving_interp = create_image_interpolation((move_x, move_y), moving_edge_filtered)

    def to_minimise(inputs):
        x_shift = inputs[0]
        y_shift = inputs[1]
        angle = inputs[2]

        interpolated = shift_and_rotate_with_interp(
            moving_interp, (ref_x, ref_y), (x_shift, y_shift), angle
        )

        return np.sum((interpolated - ref_edge_filtered) ** 2) - np.sum(interpolated)

    result = basinhopping(
        to_minimise,
        [0, 0, 0],
        niter_success=5,
        minimizer_kwargs={
            "method": "L-BFGS-B",
            "bounds": (
                (-max_shift, max_shift),
                (-max_shift, max_shift),
                (-max_rotation, max_rotation),
            ),
        },
    )

    x_shift, y_shift, angle = result.x

    return x_shift, y_shift, angle


def create_image_interpolation(axes, image):
    x_span, y_span = axes

    return RegularGridInterpolator(
        (x_span, y_span), image, bounds_error=False, fill_value=0
    )


def shift_and_rotate(original_axes, new_axes, image, x_shift, y_shift, angle):
    interp = create_image_interpolation(original_axes, image)

    return shift_and_rotate_with_interp(interp, new_axes, (x_shift, y_shift), angle)


def shift_and_rotate_with_interp(interpolation, axes, shifts, angle):
    x_span, y_span = axes
    x_shift, y_shift = shifts

    interpolated = interpolated_rotation(
        interpolation, (x_span - x_shift, y_span - y_shift), -angle
    )

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

    rotation_matrix = np.array(
        [[np.cos(radians), np.sin(radians)], [-np.sin(radians), np.cos(radians)]]
    )

    xx, yy = np.meshgrid(x_span, y_span, indexing="ij")
    return np.einsum("ji, mni -> jmn", rotation_matrix, np.dstack([xx, yy]))


def as_gray(image_filter, image, *args, **kwargs):
    gray_image = skimage.color.rgb2gray(image)
    return image_filter(gray_image, *args, **kwargs)


@skimage.color.adapt_rgb.adapt_rgb(as_gray)
def scharr_gray(image):
    return skimage.filters.scharr(image)
