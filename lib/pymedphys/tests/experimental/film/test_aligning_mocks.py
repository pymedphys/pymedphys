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
from pymedphys._imports import plt, pytest

from pymedphys._mocks.profiles import create_rectangular_field_function

from pymedphys._experimental.film import (
    align_images,
    create_image_interpolation,
    interpolated_rotation,
    shift_and_rotate,
)


def test_shift_alignment():
    alignment_assertions((5, 5, 0))


def test_rotation_alignment():
    alignment_assertions((0, 0, 20))


@pytest.mark.skip(
    reason="This function is flakey. Not for use until it is able to be reliable"
)
def test_rotation_and_shift_alignment():
    alignment_assertions((-6, 4, -15))


def alignment_assertions(expected):
    ref_field = create_rectangular_field_function((0, 0), (20, 25), 5, rotation=0)

    moving_field = create_rectangular_field_function(
        (-expected[0], -expected[1]), (20, 25), 5, rotation=-expected[2]
    )

    x_span = np.arange(-50, 51)
    y_span = np.arange(-60, 61)
    axes = (x_span, y_span)

    ref_image = ref_field(x_span[:, None], y_span[None, :])
    moving_image = moving_field(x_span[:, None], y_span[None, :])

    x_shift, y_shift, angle = align_images(
        axes, ref_image, axes, moving_image, max_shift=10, max_rotation=30
    )
    shifted_image = shift_and_rotate(axes, axes, moving_image, x_shift, y_shift, angle)

    try:
        # assert np.allclose(expected, (x_shift, y_shift, angle), rtol=0.1, atol=0.1)
        assert np.allclose(shifted_image, ref_image, rtol=0.01, atol=0.01)
    except AssertionError:
        print(x_shift, y_shift, angle)

        plt.figure()
        plt.imshow(ref_image)
        plt.colorbar()

        plt.figure()
        plt.imshow(shifted_image)
        plt.colorbar()

        plt.figure()
        plt.imshow(shifted_image - ref_image)
        plt.colorbar()

        plt.show()
        raise


def test_interpolated_rotation():
    ref_field = create_rectangular_field_function((0, 0), (5, 7), 2, rotation=30)

    moving_field = create_rectangular_field_function((0, 0), (5, 7), 2, rotation=10)

    x_span = np.linspace(-20, 20, 100)
    y_span = np.linspace(-30, 30, 120)

    ref_image = ref_field(x_span[:, None], y_span[None, :])
    moving_image = moving_field(x_span[:, None], y_span[None, :])

    moving_interp = create_image_interpolation((x_span, y_span), moving_image)

    no_rotation = interpolated_rotation(moving_interp, (x_span, y_span), 0)

    try:
        assert np.allclose(no_rotation, moving_image)
    except AssertionError:
        plt.figure()
        plt.imshow(moving_image)
        plt.axis("equal")

        plt.figure()
        plt.imshow(no_rotation)
        plt.axis("equal")

        plt.show()
        raise

    rotated = interpolated_rotation(moving_interp, (x_span, y_span), -20)

    try:
        assert np.allclose(ref_image, rotated, atol=1.0e-1)
    except AssertionError:
        plt.figure()
        plt.imshow(ref_image)
        plt.axis("equal")

        plt.figure()
        plt.imshow(rotated)
        plt.axis("equal")

        plt.figure()
        plt.imshow(rotated - ref_image)
        plt.axis("equal")

        plt.show()
        raise
