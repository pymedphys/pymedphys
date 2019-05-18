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

from PIL import Image

import numpy as np
import matplotlib.image as mpimg


def read_narrow_png(file_name, step_size=0.1):
    """  Extract a an relative-density profilee from a narrow png file.

    Source file is a full color PNG that is sufficiently narrow that
    density uniform along its short dimension. The image density along
    its long dimension is reflective of a dose distribution. Requires
    Python PIL.

    Parameters
    ----------
    file_name : str
    step-size : float, optional
        Distance output increment in cm, defaults to 1 mm

    Returns
    -------
    array_like
        Image profile as a list of (distance, density) tuples, where density
        is an average color intensity value as represented in the source file.

    Raises
    ------
    ValueError
        If image is not narrow, i.e. aspect ratio <= 5
    AssertionError
        If step_size is too small, i.e. step_size <= 12.7 / dpi

    """

    image_file = Image.open(file_name)
    assert image_file.mode == 'RGB'
    dpi_horiz, dpi_vert = image_file.info['dpi']

    image_array = mpimg.imread(file_name)

    # DIMENSIONS TO AVG ACROSS DIFFERENT FOR HORIZ VS VERT IMG
    if image_array.shape[0] > 5*image_array.shape[1]:    # VERT
        image_vector = np.average(image_array, axis=(1, 2))
        pixel_size_in_cm = (2.54 / dpi_vert)
    elif image_array.shape[1] > 5*image_array.shape[0]:  # HORIZ
        image_vector = np.average(image_array, axis=(0, 2))
        pixel_size_in_cm = (2.54 / dpi_horiz)
    else:
        raise ValueError('The PNG file is not a narrow strip.')
    assert step_size > 5 * pixel_size_in_cm, "step size too small"

    if image_vector.shape[0] % 2 == 0:
        image_vector = image_vector[:-1]  # SO ZERO DISTANCE IS MID-PIXEL

    length_in_cm = image_vector.shape[0] * pixel_size_in_cm
    full_resolution_distances = np.arange(-length_in_cm/2,
                                          length_in_cm/2,
                                          pixel_size_in_cm)

    # TO MOVE FROM FILM RESOLUTION TO DESIRED PROFILE RESOLUTION
    num_pixels_to_avg_over = int(step_size/pixel_size_in_cm)
    sample_indices = np.arange(num_pixels_to_avg_over/2,
                               len(full_resolution_distances),
                               num_pixels_to_avg_over).astype(int)
    downsampled_distances = list(full_resolution_distances[sample_indices])

    downsampled_density = []
    for idx in sample_indices:  # AVERAGE OVER THE SAMPLING WINDOW
        avg_density = np.average(
            image_vector[int(idx - num_pixels_to_avg_over / 2):
                         int(idx + num_pixels_to_avg_over / 2)])
        downsampled_density.append(avg_density)

    zipped_profile = list(zip(downsampled_distances, downsampled_density))
    return zipped_profile
