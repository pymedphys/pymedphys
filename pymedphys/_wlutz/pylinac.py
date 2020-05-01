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


from pymedphys._imports import numpy as np

import pymedphys._vendor.pylinac.winstonlutz

from .utilities import create_centralised_field, transform_point


class PylinacComparisonDeviation(ValueError):
    pass


VERSION_TO_CLASS_MAP = {
    "v2.2.6": pymedphys._vendor.pylinac.winstonlutz.WLImageOld,  # pylint: disable = protected-access
    "v2.2.7": pymedphys._vendor.pylinac.winstonlutz.WLImage,  # pylint: disable = protected-access
}


def run_wlutz(
    field,
    edge_lengths,
    penumbra,
    field_centre,
    field_rotation,
    find_bb=True,
    pixel_size=0.1,
    pylinac_versions=("v2.2.6", "v2.2.7"),
):
    centralised_straight_field = create_centralised_field(
        field, field_centre, field_rotation
    )

    half_x_range = edge_lengths[0] / 2 + penumbra * 3
    half_y_range = edge_lengths[1] / 2 + penumbra * 3

    x_range = np.arange(-half_x_range, half_x_range + pixel_size, pixel_size)
    y_range = np.arange(-half_y_range, half_y_range + pixel_size, pixel_size)

    xx_range, yy_range = np.meshgrid(x_range, y_range)
    centralised_image = centralised_straight_field(xx_range, yy_range)

    results = {}
    for key in pylinac_versions:
        pylinac_field_centre, pylinac_bb_centre = run_pylinac_with_class(
            VERSION_TO_CLASS_MAP[key],
            centralised_image,
            pixel_size,
            half_x_range,
            half_y_range,
            field_centre,
            field_rotation,
            find_bb=find_bb,
        )
        results[key] = {
            "field_centre": pylinac_field_centre,
            "bb_centre": pylinac_bb_centre,
        }

    return results


def run_pylinac_with_class(
    class_to_use,
    centralised_image,
    pixel_size,
    half_x_range,
    half_y_range,
    field_centre,
    field_rotation,
    find_bb=True,
):
    wl_image = class_to_use(centralised_image)
    centralised_pylinac_field_centre = [
        wl_image.field_cax.x * pixel_size - half_x_range,
        wl_image.field_cax.y * pixel_size - half_y_range,
    ]

    field_centre = transform_point(
        centralised_pylinac_field_centre, field_centre, field_rotation
    )

    if find_bb:
        centralised_pylinac_bb_centre = [
            wl_image.bb.x * pixel_size - half_x_range,
            wl_image.bb.y * pixel_size - half_y_range,
        ]

        bb_centre = transform_point(
            centralised_pylinac_bb_centre, field_centre, field_rotation
        )
    else:
        bb_centre = [None, None]

    return field_centre, bb_centre
