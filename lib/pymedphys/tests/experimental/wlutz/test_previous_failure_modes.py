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

import pytest
import toml
from pymedphys._imports import numpy as np

import pymedphys

from pymedphys._experimental.vendor.pylinac_vendored._pylinac_installed import (
    pylinac as _pylinac_installed,
)
from pymedphys._experimental.wlutz import main as _wlutz

EDGE_LENGTHS = [20, 26]
PENUMBRA = 2
BB_DIAMETER = 8

ALGORITHM_PYMEDPHYS = "PyMedPhys"


def get_pylinac_algorithm():
    ALGORITHM_PYLINAC = f"PyLinac v{_pylinac_installed.__version__}"
    return ALGORITHM_PYLINAC


def data_files():
    zip_filenames = ["previously_failing_iview_images.zip", "saturated-images.zip"]

    collated_collimator_angles = {}
    collated_jpg_paths = {}
    for zip_filename in zip_filenames:
        collimator_angles, jpg_paths = _get_data_files_by_zip_name(zip_filename)
        collated_collimator_angles = {**collated_collimator_angles, **collimator_angles}
        collated_jpg_paths = {**collated_jpg_paths, **jpg_paths}

    return collated_collimator_angles, collated_jpg_paths


def _get_data_files_by_zip_name(zip_filename):
    zenodo_data_files = pymedphys.zip_data_paths(zip_filename)
    collimator_angles = toml.load(
        [item for item in zenodo_data_files if item.suffix == ".toml"][0]
    )

    jpg_paths = {item.name: item for item in zenodo_data_files if item.suffix == ".jpg"}

    return collimator_angles, jpg_paths


# TODO: Add a "should be able to find BB on 000058F3.jpg"

# TODO: Add 00005A50.jpg


def test_slightly_wrong_collimator_angle():
    filename = "0000528F.jpg"
    expected_field_centre = [0.38, -2.44]
    expected_bb_centre = [0.39, -2.33]

    _compare_to_expected(
        filename, expected_field_centre, expected_bb_centre, ALGORITHM_PYMEDPHYS
    )


def test_offset_pylinac():
    filename = "000058A7.jpg"
    expected_field_centre = [-0.70, -2.75]
    expected_bb_centre = [-0.10, -2.33]

    _compare_to_expected(
        filename, expected_field_centre, expected_bb_centre, ALGORITHM_PYMEDPHYS
    )

    _compare_to_expected(
        filename, expected_field_centre, expected_bb_centre, get_pylinac_algorithm()
    )


def test_line_artefact_images_pymedphys():
    filename = "000057E2.jpg"
    expected_field_centre = [-0.11, -2.07]
    expected_bb_centre = [-0.17, -2.41]

    _compare_to_expected(
        filename, expected_field_centre, expected_bb_centre, ALGORITHM_PYMEDPHYS
    )


@pytest.mark.slow
def test_saturated_fff_images():
    test_map = {
        "000059DB.jpg": {"centre": [-1.29, -3.49], "bb": [-0.47, -3.03]},
        "000059DC.jpg": {"centre": [-0.85, -3.25], "bb": [-0.46, -2.92]},
        "000059DD.jpg": {"centre": [-0.86, -3.07], "bb": [-0.53, -2.82]},
        "000059DE.jpg": {"centre": [-1.0, -2.9], "bb": [-0.63, -2.71]},
        "000059DF.jpg": {"centre": [-1.0, -2.67], "bb": [-0.75, -2.62]},
        "000059E0.jpg": {"centre": [-0.97, -2.49], "bb": [-0.76, -2.51]},
        "000059E1.jpg": {"centre": [-1.02, -2.34], "bb": [-0.76, -2.42]},
        "000059E4.jpg": {"centre": [-0.71, -1.9], "bb": [-0.73, -2.27]},
        "000059E5.jpg": {"centre": [-0.73, -1.8], "bb": [-0.77, -2.21]},
    }

    for filename, expected in test_map.items():
        _compare_to_expected(
            filename, expected["centre"], expected["bb"], ALGORITHM_PYMEDPHYS
        )


def _get_path_and_rotation(filename):
    collimator_angles, jpg_paths = data_files()
    full_image_path = jpg_paths[filename]
    icom_field_rotation = -collimator_angles[filename]

    return full_image_path, icom_field_rotation


def _compare_to_expected(
    filename, expected_field_centre, expected_bb_centre, algorithm
):
    filepath, rotation = _get_path_and_rotation(filename)

    field_centre, bb_centre = _wlutz.calculate(
        filepath,
        algorithm,
        BB_DIAMETER,
        EDGE_LENGTHS,
        PENUMBRA,
        rotation,
        fill_errors_with_nan=False,
    )

    assert np.allclose(field_centre, expected_field_centre, atol=0.05)
    assert np.allclose(bb_centre, expected_bb_centre, atol=0.05)
