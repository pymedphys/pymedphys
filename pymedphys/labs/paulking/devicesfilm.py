# Copyright (C) 2019 Paul King

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# The following needs to be removed before leaving labs
# pylint: skip-file


from pymedphys._imports import matplotlib
from pymedphys._imports import numpy as np
from pymedphys._imports import plt

from PIL import Image


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
    assert image_file.mode == "RGB"
    dpi_horiz, dpi_vert = image_file.info["dpi"]

    image_array = mpimg.imread(file_name)

    # DIMENSIONS TO AVG ACROSS DIFFERENT FOR HORIZ VS VERT IMG
    if image_array.shape[0] > 5 * image_array.shape[1]:  # VERT
        image_vector = np.average(image_array, axis=(1, 2))
        pixel_size_in_cm = 2.54 / dpi_vert
    elif image_array.shape[1] > 5 * image_array.shape[0]:  # HORIZ
        image_vector = np.average(image_array, axis=(0, 2))
        pixel_size_in_cm = 2.54 / dpi_horiz
    else:
        raise ValueError("The PNG file is not a narrow strip.")
    assert step_size > 5 * pixel_size_in_cm, "step size too small"

    if image_vector.shape[0] % 2 == 0:
        image_vector = image_vector[:-1]  # SO ZERO DISTANCE IS MID-PIXEL

    length_in_cm = image_vector.shape[0] * pixel_size_in_cm
    full_resolution_distances = np.arange(
        -length_in_cm / 2, length_in_cm / 2, pixel_size_in_cm
    )

    # TO MOVE FROM FILM RESOLUTION TO DESIRED PROFILE RESOLUTION
    num_pixels_to_avg_over = int(step_size / pixel_size_in_cm)
    sample_indices = np.arange(
        num_pixels_to_avg_over / 2,
        len(full_resolution_distances),
        num_pixels_to_avg_over,
    ).astype(int)
    downsampled_distances = list(full_resolution_distances[sample_indices])

    downsampled_density = []
    for idx in sample_indices:  # AVERAGE OVER THE SAMPLING WINDOW
        avg_density = np.average(
            image_vector[
                int(idx - num_pixels_to_avg_over / 2) : int(
                    idx + num_pixels_to_avg_over / 2
                )
            ]
        )
        downsampled_density.append(avg_density)

    zipped_profile = list(zip(downsampled_distances, downsampled_density))
    return zipped_profile
