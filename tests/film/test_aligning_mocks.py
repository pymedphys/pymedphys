# Copyright (C) 2019 Simon Biggs, Cancer Care Associates

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
import matplotlib.pyplot as plt

from pymedphys.labs.film import (
    align_images,
    interpolated_rotation,
    create_image_interpolation,
    shift_and_rotate,
)
from pymedphys._mocks.profiles import create_rectangular_field_function


def test_shift_alignment():
    alignment_assertions((5, 5, 0))


def test_rotation_alignment():
    alignment_assertions((0, 0, 20))


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

    results = align_images(axes, ref_image, axes, moving_image, max_shift=20)
    shifted_image = shift_and_rotate(axes, axes, moving_image, *results)

    try:
        assert np.allclose(shifted_image, ref_image, rtol=0.01, atol=0.01)
    except AssertionError:
        plt.figure()
        plt.imshow(ref_image)

        plt.figure()
        plt.imshow(shifted_image)

        plt.figure()
        plt.imshow(shifted_image - ref_image)

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
