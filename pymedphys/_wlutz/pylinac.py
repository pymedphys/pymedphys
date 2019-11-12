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

import pymedphys._vendor.pylinac.winstonlutz

from .utilities import create_centralised_field, transform_point


class PylinacComparisonDeviation(ValueError):
    pass


def run_wlutz(
    field,
    edge_lengths,
    penumbra,
    field_centre,
    field_rotation,
    find_bb=True,
    pixel_size=0.1,
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

    pylinac_new_field_centre, pylinac_new_bb_centre = run_pylinac_with_class(
        pymedphys._vendor.pylinac.winstonlutz.WLImage,  # pylint: disable = protected-access
        centralised_image,
        pixel_size,
        half_x_range,
        half_y_range,
        field_centre,
        field_rotation,
        find_bb=find_bb,
    )

    pylinac_old_field_centre, pylinac_old_bb_centre = run_pylinac_with_class(
        pymedphys._vendor.pylinac.winstonlutz.WLImageOld,  # pylint: disable = protected-access
        centralised_image,
        pixel_size,
        half_x_range,
        half_y_range,
        field_centre,
        field_rotation,
        find_bb=find_bb,
    )

    return {
        "v2.2.6": {
            "field_centre": pylinac_old_field_centre,
            "bb_centre": pylinac_old_bb_centre,
        },
        "v2.2.7": {
            "field_centre": pylinac_new_field_centre,
            "bb_centre": pylinac_new_bb_centre,
        },
    }


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
