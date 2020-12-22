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

# import matplotlib.pyplot as plt
# from pymedphys._wlutz import reporting

EDGE_LENGTHS = [20, 26]
PENUMBRA = 2
BB_DIAMETER = 8

ALGORITHM_PYMEDPHYS = "PyMedPhys"
ALGORITHM_PYLINAC = f"PyLinac v{pylinac.__version__}"
ALGORITHMS = [ALGORITHM_PYMEDPHYS, ALGORITHM_PYLINAC]


@pytest.fixture
def data_files():
    zenodo_data_files = pymedphys.zip_data_paths("previously_failing_iview_images.zip")
    collimator_angles = toml.load(
        [item for item in zenodo_data_files if item.suffix == ".toml"][0]
    )

    jpg_paths = {item.name: item for item in zenodo_data_files if item.suffix == ".jpg"}

    return collimator_angles, jpg_paths


def test_offset_pylinac(data_files):
    collimator_angles, jpg_paths = data_files

    algorithm_pylinac = f"PyLinac v{pylinac.__version__}"


def test_line_artefact_images(data_files):
    collimator_angles, jpg_paths = data_files

    expected_field_centre = [-0.11, -2.07]
    expected_bb_centre = [-0.17, -2.41]

    filename = "000057E2.jpg"
    full_image_path = jpg_paths[filename]
    icom_field_rotation = -collimator_angles[filename]

    field_centre, bb_centre = _wlutz.calculate(
        full_image_path,
        ALGORITHM_PYMEDPHYS,
        BB_DIAMETER,
        EDGE_LENGTHS,
        PENUMBRA,
        icom_field_rotation,
    )

    assert np.allclose(field_centre, expected_field_centre, atol=0.05)
    assert np.allclose(bb_centre, expected_bb_centre, atol=0.05)
