# Copyright (C) 2020 Simon Biggs, Matthew Cooper

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import warnings

from pymedphys._imports import numpy as np
from pymedphys._imports import plt, skimage


def get_image_transformation_parameters(dcm_ct):
    position = dcm_ct.ImagePositionPatient
    spacing = dcm_ct.PixelSpacing
    orientation = dcm_ct.ImageOrientationPatient

    dx, dy = spacing
    Cx, Cy, *_ = position
    Ox, Oy = orientation[0], orientation[4]

    return dx, dy, Cx, Cy, Ox, Oy


def reduce_expanded_mask(expanded_mask, img_size, expansion):
    return np.mean(
        np.mean(
            np.reshape(expanded_mask, (img_size, expansion, img_size, expansion)),
            axis=1,
        ),
        axis=2,
    )


def get_grid(dcm_ct, transformation_params=None):
    if transformation_params is None:
        dx, dy, Cx, Cy, Ox, Oy = get_image_transformation_parameters(dcm_ct)
    else:
        dx, dy, Cx, Cy, Ox, Oy = transformation_params

    ct_size = np.shape(dcm_ct.pixel_array)
    x_grid = np.arange(Cx, Cx + ct_size[0] * dx * Ox, dx * Ox)
    y_grid = np.arange(Cy, Cy + ct_size[1] * dy * Oy, dy * Oy)

    return x_grid, y_grid, ct_size


def calculate_anti_aliased_mask(contours, dcm_ct, expansion=5):
    transformation_params = get_image_transformation_parameters(dcm_ct)
    dx, dy, Cx, Cy, Ox, Oy = transformation_params

    x_grid, y_grid, ct_size = get_grid(
        dcm_ct, transformation_params=transformation_params
    )

    new_ct_size = np.array(ct_size) * expansion

    expanded_mask = np.zeros(new_ct_size)

    for xyz in contours:
        x = np.array(xyz[0::3])
        y = np.array(xyz[1::3])
        z = xyz[2::3]

        assert len(set(z)) == 1

        r = (((y - Cy) / dy * Oy)) * expansion + (expansion - 1) * 0.5
        c = (((x - Cx) / dx * Ox)) * expansion + (expansion - 1) * 0.5

        expanded_mask = np.logical_or(
            expanded_mask,
            skimage.draw.polygon2mask(new_ct_size, np.array(list(zip(r, c)))),
        )

    mask = reduce_expanded_mask(expanded_mask, ct_size[0], expansion)
    mask = 2 * mask - 1

    return x_grid, y_grid, mask


def get_contours_from_mask(x_grid, y_grid, mask):
    fig, ax = plt.subplots()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        cs = ax.contour(x_grid, y_grid, mask, [0])

    contours = [path.vertices for path in cs.collections[0].get_paths()]
    plt.close(fig)

    return contours
