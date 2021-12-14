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


"""A set of tests where the artefacts on the image mean that PyMedPhys
should fail instead of producing a return value.
"""


import pytest
import toml
from pymedphys._imports import numpy as np

import pymedphys

from pymedphys._experimental.wlutz import main as _wlutz

PENUMBRA = 2
BB_DIAMETER = 8

ALGORITHM_PYMEDPHYS = "PyMedPhys"


def data_files():
    zenodo_data_files = pymedphys.zip_data_paths(
        "iview-images-where-wlutz-should-fail-fast.zip"
    )
    config = toml.load(
        [item for item in zenodo_data_files if item.suffix == ".toml"][0]
    )

    jpg_paths = {item.name: item for item in zenodo_data_files if item.suffix == ".jpg"}

    return config, jpg_paths


@pytest.mark.slow
def test_start_fields_with_panel_artefacts():
    config, jpg_paths = data_files()

    field_centres_that_can_be_found = ["000057B6.jpg", "00005848.jpg", "000058B0.jpg"]

    for filename, full_image_path in jpg_paths.items():
        print(filename)

        file_config = config[filename]
        icom_field_rotation = -file_config["collimator"]
        edge_lengths = file_config["edge_lengths"]

        field_centre, bb_centre = _wlutz.calculate(
            full_image_path,
            ALGORITHM_PYMEDPHYS,
            BB_DIAMETER,
            edge_lengths,
            PENUMBRA,
            icom_field_rotation,
        )

        if not filename in field_centres_that_can_be_found:
            assert np.all(np.isnan(field_centre))

        assert np.all(np.isnan(bb_centre))
