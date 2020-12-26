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

import numpy as np

import pylinac

import pymedphys

from pymedphys._experimental.wlutz import main as _wlutz

EDGE_LENGTHS = [20, 26]
PENUMBRA = 2
BB_DIAMETER = 8

ALGORITHM_PYMEDPHYS = "PyMedPhys"
ALGORITHM_PYLINAC = f"PyLinac v{pylinac.__version__}"
ALGORITHMS = [ALGORITHM_PYMEDPHYS, ALGORITHM_PYLINAC]


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


def test_offset_pylinac():
    filename = "000058A7.jpg"
    expected_field_centre = [-0.70, -2.75]
    expected_bb_centre = [-0.10, -2.33]

    _compare_to_expected(
        filename, expected_field_centre, expected_bb_centre, ALGORITHM_PYMEDPHYS
    )

    _compare_to_expected(
        filename, expected_field_centre, expected_bb_centre, ALGORITHM_PYLINAC
    )


def test_line_artefact_images_pymedphys():
    filename = "000057E2.jpg"
    expected_field_centre = [-0.11, -2.07]
    expected_bb_centre = [-0.17, -2.41]

    _compare_to_expected(
        filename, expected_field_centre, expected_bb_centre, ALGORITHM_PYMEDPHYS
    )


def test_saturated_fff_image():
    filename = "000059DB.jpg"
    expected_field_centre = [-1.29, -3.49]
    expected_bb_centre = [-0.47, -3.03]

    _compare_to_expected(
        filename, expected_field_centre, expected_bb_centre, ALGORITHM_PYMEDPHYS
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
        filepath, algorithm, BB_DIAMETER, EDGE_LENGTHS, PENUMBRA, rotation
    )

    assert np.allclose(field_centre, expected_field_centre, atol=0.05)
    assert np.allclose(bb_centre, expected_bb_centre, atol=0.05)
