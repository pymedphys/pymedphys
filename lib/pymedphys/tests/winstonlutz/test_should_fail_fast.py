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

from pymedphys._experimental.streamlit.utilities import wlutz as _wlutz

EDGE_LENGTHS = [20, 26]
PENUMBRA = 2
BB_DIAMETER = 8

ALGORITHM_PYMEDPHYS = "PyMedPhys"
ALGORITHM_PYLINAC = f"PyLinac v{pylinac.__version__}"
ALGORITHMS = [ALGORITHM_PYMEDPHYS, ALGORITHM_PYLINAC]


def data_files():
    zenodo_data_files = pymedphys.zip_data_paths(
        "iview-images-where-wlutz-should-fail-fast.zip"
    )
    collimator_angles = toml.load(
        [item for item in zenodo_data_files if item.suffix == ".toml"][0]
    )

    jpg_paths = {item.name: item for item in zenodo_data_files if item.suffix == ".jpg"}

    return collimator_angles, jpg_paths


def test_start_fields_with_panel_artefacts():
    filename = "00005848.jpg"

    _should_raise_value_error(filename, ALGORITHM_PYMEDPHYS)


def _get_path_and_rotation(filename):
    collimator_angles, jpg_paths = data_files()
    full_image_path = jpg_paths[filename]
    icom_field_rotation = -collimator_angles[filename]

    return full_image_path, icom_field_rotation


def _should_raise_value_error(filename, algorithm):
    filepath, rotation = _get_path_and_rotation(filename)

    with pytest.raises(ValueError):
        field_centre, bb_centre = _wlutz.calculate(
            filepath, algorithm, BB_DIAMETER, EDGE_LENGTHS, PENUMBRA, rotation
        )
