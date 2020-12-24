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

import datetime

import pytest
from hypothesis import Verbosity, given, settings
from hypothesis.strategies import floats

import numpy as np

import pymedphys._mocks.wlutz as mock_wlutz

from pymedphys._experimental.wlutz import pylinacwrapper


@pytest.mark.slow
@settings(
    max_examples=10,
    deadline=datetime.timedelta(milliseconds=4000),
    verbosity=Verbosity.verbose,
)
@given(
    floats(-20, 20),
    floats(-20, 20),
    floats(10, 20),
    floats(10, 20),
    floats(0.5, 3),
    floats(-360, 360),
)
def test_field_finding(x_centre, y_centre, x_edge, y_edge, penumbra, actual_rotation):
    edge_lengths = [x_edge, y_edge]
    actual_centre = [x_centre, y_centre]

    # BB not actually being tested here
    bb_diameter = 8
    bb_max_attenuation = 0.3
    bb_centre = [0, 0]

    x = np.arange(-20, 20.1, 0.1)
    y = np.arange(-22, 22.1, 0.1)
    img = mock_wlutz.create_test_image(
        x,
        y,
        actual_centre,
        edge_lengths,
        penumbra,
        actual_rotation,
        bb_centre,
        bb_diameter,
        bb_max_attenuation,
    )

    results = pylinacwrapper.run_wlutz(
        x, y, img, field_rotation=actual_rotation, find_bb=False
    )

    assert np.allclose(actual_centre, results["2.2.6"]["field_centre"], atol=0.2)
    assert np.allclose(actual_centre, results["2.2.7"]["field_centre"], atol=0.2)
    assert np.allclose(actual_centre, results["2.3.2"]["field_centre"], atol=0.2)
