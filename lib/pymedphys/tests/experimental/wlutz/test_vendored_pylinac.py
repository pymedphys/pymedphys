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

from hypothesis import Verbosity, given, settings
from hypothesis.strategies import floats
from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys._mocks.wlutz as mock_wlutz

from pymedphys._experimental.vendor.pylinac_vendored._pylinac_installed import (
    pylinac as _pylinac_installed,
)
from pymedphys._experimental.wlutz import pylinacwrapper


@pytest.mark.slow
@settings(
    max_examples=10,
    deadline=datetime.timedelta(milliseconds=4000),
    verbosity=Verbosity.verbose,
)
@given(
    floats(-15, 15),
    floats(-15, 15),
    floats(15, 30),
    floats(15, 30),
    floats(-3, 3),
    floats(-3, 3),
    floats(0.5, 3),
    floats(-360, 360),
)
def test_field_finding(
    x_centre,
    y_centre,
    x_edge,
    y_edge,
    bb_offset_x,
    bb_offset_y,
    penumbra,
    actual_rotation,
):
    edge_lengths = [x_edge, y_edge]
    actual_centre = [x_centre, y_centre]

    bb_diameter = 3
    bb_max_attenuation = 0.3
    bb_centre = [x_centre + bb_offset_x, y_centre + bb_offset_y]

    x = np.arange(-50, 50.1, 0.25)
    y = np.arange(-52, 52.1, 0.25)
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
        x, y, img, edge_lengths, actual_rotation, find_bb=False
    )

    assert np.allclose(actual_centre, results["2.2.6"]["field_centre"], atol=0.2)
    assert np.allclose(actual_centre, results["2.2.7"]["field_centre"], atol=0.2)
    assert np.allclose(
        actual_centre, results[_pylinac_installed.__version__]["field_centre"], atol=0.2
    )

    bb_centre_when_finding_it_only = pylinacwrapper.find_bb_only(
        x, y, img, edge_lengths, penumbra, actual_centre, actual_rotation
    )

    results_with_bb = pylinacwrapper.run_wlutz(
        x,
        y,
        img,
        edge_lengths,
        actual_rotation,
        pylinac_versions=[_pylinac_installed.__version__],
    )
    predicted_bb_centre = results_with_bb[_pylinac_installed.__version__]["bb_centre"]
    assert np.allclose(bb_centre_when_finding_it_only, predicted_bb_centre, atol=0.1)

    assert np.allclose(bb_centre, predicted_bb_centre, atol=0.2)
