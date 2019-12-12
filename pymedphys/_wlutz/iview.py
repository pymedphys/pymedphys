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


import numpy as np
import pandas as pd

import matplotlib.pyplot as plt

import imageio

from .core import find_field_and_bb
from .reporting import image_analysis_figure


def iview_find_bb_and_field(
    image_path, edge_lengths, bb_diameter=8, penumbra=2, display_figure=True
):
    x, y, img = iview_image_transform(image_path)

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


def iview_image_transform(image_path):
    img = imageio.imread(image_path)
    if np.shape(img) != (1024, 1024):
        raise ValueError(
            f"Expect iView images to be 1024x1024 pixels\nShhape = {np.shape(img)}"
        )
    img = img[:, 1:-1]

    if img.dtype != np.dtype("uint16"):
        raise ValueError("Expect iView images to have a pixel type of unsigned 16 bit")
    img = 1 - img[::-1, :] / 2 ** 16

    shape = np.shape(img)
    x = np.arange(-shape[1] / 2, shape[1] / 2) / 4
    y = np.arange(-shape[0] / 2, shape[0] / 2) / 4

    return x, y, img
