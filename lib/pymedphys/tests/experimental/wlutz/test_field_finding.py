# Copyright (C) 2020 Cancer Care Associates and Simon Biggs
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

import datetime

from hypothesis import Verbosity, given, settings
from hypothesis.strategies import floats
from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys
from pymedphys._mocks import profiles

from pymedphys._experimental.wlutz import findfield, iview
from pymedphys._experimental.wlutz import main as _wlutz


def test_find_field_in_image():
    edge_lengths = [20, 20]

    expected_centre = [1.46, -1.9]
    expected_rotation = 12.1

    image_path = pymedphys.data_path("wlutz_image.png")
    x, y, img = iview.iview_image_transform_from_path(image_path)

    centre, _ = _wlutz.pymedphys_wlutz_calculate(
        x, y, img, np.nan, edge_lengths, 2, expected_rotation
    )

    centre = np.round(centre, 2).tolist()

    assert expected_centre == centre


@pytest.mark.slow
@settings(
    deadline=datetime.timedelta(milliseconds=10000),
    max_examples=10,
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

    field = profiles.create_rectangular_field_function(
        actual_centre, edge_lengths, penumbra, actual_rotation
    )

    x = np.arange(-50, 50, 0.1)
    y = np.arange(-50, 50, 0.1)
    xx, yy = np.meshgrid(x, y)
    zz = field(xx, yy)

    centre = findfield.find_field_centre(
        x, y, zz, edge_lengths, penumbra, field_rotation=actual_rotation
    )

    try:
        findfield.check_centre_close(actual_centre, centre)
    except ValueError:
        print("Failed during comparison to gold reference values")
        raise


def test_find_initial_field_centre():
    centre = [20, 5]
    rotation = 20
    side_length = 10
    edge_lengths = [side_length, side_length]

    field = profiles.create_square_field_function(
        centre=centre, side_length=side_length, penumbra_width=1, rotation=rotation
    )

    x = np.arange(-30, 30, 0.25)
    y = np.arange(-32, 32, 0.25)

    xx, yy = np.meshgrid(x, y)

    zz = field(xx, yy)

    initial_centre = findfield.get_initial_centre(x, y, zz, edge_lengths, rotation)

    assert np.allclose(initial_centre, centre, atol=0.4)
