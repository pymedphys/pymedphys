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


import functools

from pymedphys._imports import numpy as np
from pymedphys._imports import pylinac

from pymedphys import _losslessjpeg as lljpeg
from pymedphys._wlutz import findbb, findfield, imginterp, iview
from pymedphys._wlutz import pylinac as pmp_pylinac_api


def calculate(
    image_path, algorithm, bb_diameter, edge_lengths, penumbra, icom_field_rotation
):
    x, y, image = load_iview_image(image_path)

    ALGORITHM_FUNCTION_MAP = get_algorithm_function_map()

    calculate_function = ALGORITHM_FUNCTION_MAP[algorithm]
    field_centre, bb_centre = calculate_function(
        x=x,
        y=y,
        image=image,
        bb_diameter=bb_diameter,
        edge_lengths=edge_lengths,
        penumbra=penumbra,
        icom_field_rotation=icom_field_rotation,
    )

    return field_centre, bb_centre


@functools.lru_cache()
def get_algorithm_function_map():
    ALGORITHM_FUNCTION_MAP = {
        "PyMedPhys": _pymedphys_wlutz_calculate,
        f"PyLinac v{pylinac.__version__}": functools.partial(
            _pylinac_wlutz_calculate, pylinac_version=pylinac.__version__
        ),
        "PyLinac v2.2.6": functools.partial(
            _pylinac_wlutz_calculate, pylinac_version="2.2.6"
        ),
    }

    return ALGORITHM_FUNCTION_MAP


def load_iview_image(image_path):
    raw_image = lljpeg.imread(image_path)
    x, y, image = iview.iview_image_transform(raw_image)

    return x, y, image


def _pymedphys_wlutz_calculate(
    x, y, image, bb_diameter, edge_lengths, penumbra, icom_field_rotation, **_
):

    initial_centre = findfield.get_initial_centre(x, y, image, icom_field_rotation)
    field = imginterp.create_interpolated_field(x, y, image)
    try:
        field_centre, _ = findfield.field_centre_and_rotation_refining(
            field,
            edge_lengths,
            penumbra,
            initial_centre,
            pylinac_tol=None,
            fixed_rotation=icom_field_rotation,
        )
    except ValueError:
        field_centre = [np.nan, np.nan]

    try:
        bb_centre = findbb.optimise_bb_centre(
            field,
            bb_diameter,
            edge_lengths,
            penumbra,
            field_centre,
            icom_field_rotation,
            pylinac_tol=None,
        )
    except ValueError:
        bb_centre = [np.nan, np.nan]

    return field_centre, bb_centre


def _pylinac_wlutz_calculate(x, y, image, icom_field_rotation, pylinac_version, **_):
    try:
        pylinac_results = pmp_pylinac_api.run_wlutz(
            x,
            y,
            image,
            icom_field_rotation,
            find_bb=True,
            pylinac_versions=[pylinac_version],
            fill_errors_with_nan=True,
        )

        field_centre = pylinac_results[pylinac_version]["field_centre"]
        bb_centre = pylinac_results[pylinac_version]["bb_centre"]

    except ValueError:
        field_centre = [np.nan, np.nan]
        bb_centre = [np.nan, np.nan]

    return field_centre, bb_centre