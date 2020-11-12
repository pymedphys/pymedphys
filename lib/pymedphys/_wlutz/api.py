# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os  # pylint: disable = unused-import
from typing import Any, Union, cast  # pylint: disable = unused-import

from pymedphys._imports import imageio
from pymedphys._imports import numpy as np

path_or_numpy_array = Union["np.ndarray", "os.PathLike[Any]", str]
path_types = Union["os.PathLike[Any]", str]


def load_potentially_lossless_image(image: path_or_numpy_array):
    if isinstance(path_or_numpy_array, np.ndarray):
        return image

    image_path = cast(path_or_numpy_array, path_types)

    try:
        return imageio.imread(image_path)
    except:
        raise


# class WinstonLutz:
#     def __init__(self, image: path_or_numpy_array):
#         if isinstance(path_or_numpy_array, np.array):
#             self._image = image

#             return

#         image_path = cast(path_or_numpy_array, path_types)

#         try:
#             self._image = imageio.imread(image_path)
