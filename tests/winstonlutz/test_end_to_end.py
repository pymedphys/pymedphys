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


import pathlib

import pytest

import numpy as np
import pandas as pd

import pymedphys
import pymedphys._wlutz.iview

HERE = pathlib.Path(__file__).parent.resolve()


@pytest.mark.slow
def test_end_to_end():
    edge_lengths = [20, 20]

    image_paths = pymedphys.zip_data_paths("wlutz_images.zip")
    results = pymedphys._wlutz.iview.batch_process(  # pylint:disable = protected-access
        image_paths, edge_lengths, display_figure=False
    )

    reference_dataframe = pd.read_csv(HERE.joinpath("end_to_end.csv"))

    assert np.max(np.abs(results["Rotation"] - reference_dataframe["Rotation"])) <= 0.1
    assert (
        np.max(
            np.max(
                np.abs(
                    results.drop(columns=["Rotation"])
                    - reference_dataframe.drop(columns=["Rotation"])
                )
            )
        )
        <= 0.05
    )
