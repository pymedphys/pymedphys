# Copyright (C) 2019 Paul King

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
import matplotlib.image as mpimg

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def read_narrow_png(file_name, dpi=600, step_size=0.1):
    """  Extract a an relative-density profilee from a narrow png file.

    Image density is assumed to be uniform along its short dimension and
    contain an image density along its long dimension, reflective of a dose
    distribution.

    Parameters
    ----------
    file_name : str
    dpi : int, optional
    step-size : float, optional
        Distance output increment in cm

    Returns
    -------
    array_like
        Image profile as a list of (distance, density) tuples, where density
        is an average color intensity value as represented in the source file.

    Raises
    ------
    AssertionError
        If image is not narrow, i.e. aspect ratio <= 5
        If step_size is too small, i.e. step_size <= 12.7 / dpi

    """

    image_array = mpimg.imread(file_name)

    # AVG ACROSS NARROW DIMENSION & COLORS
    if image_array.shape[0] > 5*image_array.shape[1]:    # VERTICAL
        image_vector = np.average(image_array, axis=(1, 2))
    elif image_array.shape[1] > 5*image_array.shape[0]:  # HORIZONTAL
        image_vector = np.average(image_array, axis=(0, 2))
    else:
        assert False, "png not narrow"

    # FIND PIXEL SIZE
    pixel_size_in_cm = (2.54 / dpi)
    assert step_size > 5 * pixel_size_in_cm, "step size too small"

    # ENFORCE AN ODD NUMBER OF PIXELS
    if image_vector.shape[0] % 2 == 0:
        image_vector = image_vector[:-1]

    # FIND THE UN-DOWNSAMPLED DISTANCES
    length_in_cm = image_vector.shape[0] * pixel_size_in_cm
    image_vector_distances = np.arange(-length_in_cm/2,
                                       length_in_cm/2,
                                       pixel_size_in_cm)

    # DOWNSAMPLE THE IMAGE VECTOR DISTANCES
    num_pixels_to_avg_over = int(step_size/pixel_size_in_cm)

    sample_indices = np.arange(num_pixels_to_avg_over/2,
                               len(image_vector_distances),
                               num_pixels_to_avg_over).astype(int)
    downsampled_distance = list(image_vector_distances[sample_indices])

    # DOWNSAMPLE DENSITY BY AVERAGING OVER THE WINDOW
    downsampled_density = []
    for idx in sample_indices:
        avg_density = np.average(
            image_vector[int(idx - num_pixels_to_avg_over / 2):
                         int(idx + num_pixels_to_avg_over / 2)])
        downsampled_density.append(avg_density)

    # ZIP & RETURN
    density_profile = list(zip(downsampled_distance, downsampled_density))
    return density_profile
