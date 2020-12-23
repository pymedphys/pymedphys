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

from pymedphys._vendor.pylinac import winstonlutz as _pylinac_wlutz

from . import imginterp as _imginterp
from . import utilities as _utilities


class PylinacComparisonDeviation(ValueError):
    pass


def run_wlutz_raw(x, y, image, pylinac_versions=None, fill_errors_with_nan=False):
    pass


def run_wlutz(
    x,
    y,
    image,
    field_rotation,
    search_radius=40,
    find_bb=True,
    interpolated_pixel_size=0.25,
    pylinac_versions=None,
    fill_errors_with_nan=False,
):
    VERSION_TO_CLASS_MAP = _pylinac_wlutz.get_version_to_class_map()

    if pylinac_versions is None:
        pylinac_versions = VERSION_TO_CLASS_MAP.keys()

    field = _imginterp.create_interpolated_field(x, y, image)

    centralised_straight_field = _utilities.create_centralised_field(
        field, [0, 0], field_rotation
    )

    interp_coord = np.arange(
        -search_radius, search_radius + interpolated_pixel_size, interpolated_pixel_size
    )

    xx_range, yy_range = np.meshgrid(interp_coord, interp_coord)
    centralised_image = centralised_straight_field(xx_range, yy_range)

    results = {}
    for key in pylinac_versions:
        pylinac_field_centre, pylinac_bb_centre = run_pylinac_with_class(
            VERSION_TO_CLASS_MAP[key],
            centralised_image,
            interpolated_pixel_size,
            search_radius,
            field_rotation,
            find_bb=find_bb,
            fill_errors_with_nan=fill_errors_with_nan,
        )
        results[key] = {
            "field_centre": pylinac_field_centre,
            "bb_centre": pylinac_bb_centre,
        }

    return results


def run_pylinac_with_class(
    class_to_use,
    interpolated_image,
    interpolated_pixel_size,
    search_radius,
    field_rotation_for_interpolation,
    find_bb=True,
    fill_errors_with_nan=False,
):
    wl_image = class_to_use(interpolated_image)
    interpolated_image_field_centre = [
        wl_image.field_cax.x * interpolated_pixel_size - search_radius,
        wl_image.field_cax.y * interpolated_pixel_size - search_radius,
    ]

    try:
        field_centre = _utilities.transform_point(
            interpolated_image_field_centre, [0, 0], -field_rotation_for_interpolation
        )
    except ValueError:
        if fill_errors_with_nan:
            field_centre = [np.nan, np.nan]
        else:
            raise

    if find_bb:
        try:
            interpolated_image_bb_centre = [
                wl_image.bb.x * interpolated_pixel_size - search_radius,
                wl_image.bb.y * interpolated_pixel_size - search_radius,
            ]

            bb_centre = _utilities.transform_point(
                interpolated_image_bb_centre, [0, 0], -field_rotation_for_interpolation
            )
        except ValueError:
            if fill_errors_with_nan:
                bb_centre = [np.nan, np.nan]
            else:
                raise
    else:
        bb_centre = [np.nan, np.nan]

    return field_centre, bb_centre
