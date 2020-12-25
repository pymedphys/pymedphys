# Copyright (C) 2020 Cancer Care Associates and Simon Biggs
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

from typing import cast

from pymedphys._imports import numpy as np
from pymedphys._imports import pylinac as _pylinac_installed

from pymedphys._experimental.vendor.pylinac import winstonlutz as _pylinac_vendored

from . import utilities as _utilities


def run_wlutz_raw(
    x, y, image, find_bb=True, pylinac_version=None, fill_errors_with_nan=False
):
    if pylinac_version is None:
        pylinac_version = _pylinac_installed.__version__

    nan_coords = [np.nan, np.nan]

    VERSION_TO_CLASS_MAP = _pylinac_vendored.get_version_to_class_map()
    WLImage = VERSION_TO_CLASS_MAP[pylinac_version]
    wl_image = WLImage(image)

    dx = _convert_grid_to_step_size(x)
    dy = _convert_grid_to_step_size(y)

    try:
        field_centre = [
            wl_image.field_cax.x * dx + np.min(x),
            wl_image.field_cax.y * dy + np.min(y),
        ]
    except ValueError:
        if fill_errors_with_nan:
            field_centre = nan_coords

        else:
            raise

    if find_bb:
        try:
            bb_centre = [wl_image.bb.x * dx + np.min(x), wl_image.bb.y * dy + np.min(y)]
        except ValueError:
            if fill_errors_with_nan:
                bb_centre = nan_coords
            else:
                raise
    else:
        bb_centre = nan_coords

    return field_centre, bb_centre


def _convert_grid_to_step_size(x):
    diff_x = np.diff(x)
    dx_all = np.unique(diff_x)
    if len(dx_all) != 1:
        raise ValueError("Exactly one grid step size required.")

    dx = dx_all[0]

    return dx


def run_wlutz(
    x,
    y,
    image,
    field_rotation,
    search_radius=None,
    find_bb=True,
    interpolated_pixel_size=0.25,
    pylinac_versions=None,
    fill_errors_with_nan=False,
):
    if search_radius is None:
        new_x, new_y = x, y
    else:
        search_radius_defined = cast(float, search_radius)
        new_x = np.arange(
            -search_radius_defined,  # pylint: disable = invalid-unary-operand-type
            search_radius_defined + interpolated_pixel_size,
            interpolated_pixel_size,
        )
        new_y = new_x

    rotated_image = _utilities.create_rotated_image(
        x, y, image, field_rotation, new_x=new_x, new_y=new_y
    )

    if pylinac_versions is None:
        VERSION_TO_CLASS_MAP = _pylinac_vendored.get_version_to_class_map()
        pylinac_versions = VERSION_TO_CLASS_MAP.keys()

    results = {}
    for pylinac_version in pylinac_versions:
        raw_field_centre, raw_bb_centre = run_wlutz_raw(
            new_x,
            new_y,
            rotated_image,
            find_bb=find_bb,
            pylinac_version=pylinac_version,
            fill_errors_with_nan=fill_errors_with_nan,
        )

        bb_centre = _utilities.rotate_point(raw_bb_centre, field_rotation)
        field_centre = _utilities.rotate_point(raw_field_centre, field_rotation)

        results[pylinac_version] = {
            "field_centre": field_centre,
            "bb_centre": bb_centre,
        }

    return results
