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
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt

from .core import find_field_and_bb
from .reporting import image_analysis_figure


def iview_find_bb_and_field(
    image_path, edge_lengths, bb_diameter=8, penumbra=2, display_figure=True
):
    x, y, img = iview_image_transform_from_path(image_path)

    bb_centre, field_centre, field_rotation = find_field_and_bb(
        x, y, img, edge_lengths, bb_diameter, penumbra=penumbra
    )

    if display_figure:
        image_analysis_figure(
            x,
            y,
            img,
            bb_centre,
            field_centre,
            field_rotation,
            bb_diameter,
            edge_lengths,
            penumbra,
        )

    return bb_centre, field_centre, field_rotation


def batch_process(
    image_paths, edge_lengths, bb_diameter=8, penumbra=2, display_figure=True
):
    bb_centres = []
    field_centres = []
    field_rotations = []

    for image_path in image_paths:
        bb_centre, field_centre, field_rotation = iview_find_bb_and_field(
            image_path,
            edge_lengths,
            bb_diameter=bb_diameter,
            penumbra=penumbra,
            display_figure=display_figure,
        )

        bb_centres.append(bb_centre)
        field_centres.append(field_centre)
        field_rotations.append(field_rotation)

        if display_figure:
            plt.show()

    data = np.concatenate(
        [bb_centres, field_centres, np.array(field_rotations)[:, None]], axis=1
    )
    return pd.DataFrame(
        data=data, columns=["BB x", "BB y", "Field x", "Field y", "Rotation"]
    )


def iview_image_transform_from_path(image_path):
    img = imageio.imread(image_path)

    return iview_image_transform(img)


def iview_image_transform(img):
    if np.shape(img) == (1024, 1024):
        pixels_per_mm = 4
    elif np.shape(img) == (512, 512):
        pixels_per_mm = 2
    else:
        raise ValueError(
            "Expect iView images to be either 1024x1024 or 512x512 "
            f"pixels\nShape = {np.shape(img)}"
        )

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
