# Copyright (C) 2019 Cancer Care Associates

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


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

    assert np.all(np.abs(results["Rotation"] - reference_dataframe["Rotation"])) <= 0.1
    assert (
        np.all(
            np.abs(
                results.drop(columns=["Rotation"])
                - reference_dataframe.drop(columns=["Rotation"])
            )
        )
        <= 0.01
    )
