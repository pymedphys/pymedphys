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


from pymedphys._imports import imageio
from pymedphys._imports import numpy as np


def iview_image_transform_from_path(image_path):
    img = imageio.imread(image_path)

    return iview_image_transform(img)


def infer_pixels_per_mm_from_shape(img):
    """This is not ideal. Instead, it would be better to use the MMPIX
    values stored within the iView database. There is something I need
    to get to the bottom of before making the swap though.

    """
    if np.shape(img) == (1024, 1024):
        pixels_per_mm = 4
    elif np.shape(img) == (512, 512):
        pixels_per_mm = 2
    else:
        raise ValueError(
            "Expect iView images to be either 1024x1024 or 512x512 "
            f"pixels\nShape = {np.shape(img)}"
        )

    return pixels_per_mm


def iview_image_transform(img):
    pixels_per_mm = infer_pixels_per_mm_from_shape(img)
    img = img[:, 1:-1]

    if img.dtype != np.dtype("uint16") and img.dtype != np.dtype("int32"):
        raise ValueError(
            "Expect iView images to have a pixel type of unsigned 16 bit "
            "or signed 32 bit."
            f"Instead the type was {img.dtype}\n"
            f"  Min pixel value was {np.min(img)}\n"
            f"  Max pixel value was {np.max(img)}"
        )
    img = 1 - img[::-1, :] / 2 ** 16

    shape = np.shape(img)
    x = np.arange(-shape[1] / 2, shape[1] / 2) / pixels_per_mm
    y = np.arange(-shape[0] / 2, shape[0] / 2) / pixels_per_mm

    return x, y, img
