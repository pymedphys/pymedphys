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

import toml

import numpy as np

import pylinac

import pymedphys

from pymedphys._experimental.streamlit.utilities import wlutz as _wlutz

# import matplotlib.pyplot as plt
# from pymedphys._wlutz import reporting


def test_line_artefact_images():
    data_files = pymedphys.zip_data_paths("26x20mm_out_of_sync_iview_images.zip")
    collimator_angles = toml.load(
        [item for item in data_files if item.suffix == ".toml"][0]
    )

    jpg_paths = {item.name: item for item in data_files if item.suffix == ".jpg"}

    edge_lengths = [20, 26]
    penumbra = 2
    bb_diameter = 8

    algorithm_pymedphys = "PyMedPhys"
    algorithm_pylinac = f"PyLinac v{pylinac.__version__}"
    algorithms = [algorithm_pymedphys, algorithm_pylinac]

    filename = "000057E2.jpg"
    full_image_path = jpg_paths[filename]
    icom_field_rotation = -collimator_angles[filename]

    results = {}
    for algorithm in algorithms:
        field_centre, bb_centre = _wlutz.calculate(
            full_image_path,
            algorithm,
            bb_diameter,
            edge_lengths,
            penumbra,
            icom_field_rotation,
        )

        results[algorithm] = {"field_centre": field_centre, "bb_centre": bb_centre}

        # x, y, image = _wlutz.load_iview_image(full_image_path)
        # fig, axs = reporting.image_analysis_figure(
        #     x,
        #     y,
        #     image,
        #     bb_centre,
        #     field_centre,
        #     icom_field_rotation,
        #     bb_diameter,
        #     edge_lengths,
        #     penumbra,
        # )
        # plt.show()

    assert np.allclose(
        results[algorithm_pymedphys]["field_centre"],
        results[algorithm_pylinac]["field_centre"],
        atol=0.2,
    )
    assert np.allclose(
        results[algorithm_pymedphys]["bb_centre"],
        results[algorithm_pylinac]["bb_centre"],
        atol=0.2,
    )
