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

# pylint: disable = protected-access

import datetime

import pytest
from hypothesis import Verbosity, given, settings
from hypothesis.strategies import floats

import numpy as np

import pymedphys
import pymedphys._mocks.profiles
import pymedphys._wlutz.findfield
import pymedphys._wlutz.iview


def test_find_field_in_image():
    edge_lengths = [20, 20]

    expected_centre = [1.46, -1.9]
    expected_rotation = 12.1

    image_path = pymedphys.data_path("wlutz_image.png")
    x, y, img = pymedphys._wlutz.iview.iview_image_transform_from_path(image_path)

    _, centre, rotation = pymedphys._wlutz.core.find_field(x, y, img, edge_lengths)

    centre = np.round(centre, 2).tolist()
    rotation = float(np.round(rotation, 1))

    assert (expected_centre, expected_rotation) == (centre, rotation)


@pytest.mark.slow
@settings(
    deadline=datetime.timedelta(milliseconds=4000),
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

    try:
        pymedphys._wlutz.findfield.check_aspect_ratio(edge_lengths)
    except ValueError:
        return

    field = pymedphys._mocks.profiles.create_rectangular_field_function(
        actual_centre, edge_lengths, penumbra, actual_rotation
    )

    x = np.arange(-50, 50, 0.1)
    y = np.arange(-50, 50, 0.1)
    xx, yy = np.meshgrid(x, y)
    zz = field(xx, yy)

    initial_centre = pymedphys._wlutz.findfield.get_centre_of_mass(x, y, zz)
    (centre, rotation) = pymedphys._wlutz.findfield.field_centre_and_rotation_refining(
        field, edge_lengths, penumbra, initial_centre
    )

    try:
        pymedphys._wlutz.findfield.check_rotation_and_centre(
            edge_lengths, actual_centre, centre, actual_rotation, rotation
        )
    except ValueError:
        print("Failed during comparison to gold reference values")
        raise


def test_find_initial_field_centre():
    centre = [20, 5]

    field = pymedphys._mocks.profiles.create_square_field_function(
        centre=centre, side_length=10, penumbra_width=1, rotation=20
    )

    x = np.arange(-15, 30, 0.1)
    y = np.arange(-15, 15, 0.1)

    xx, yy = np.meshgrid(x, y)

    zz = field(xx, yy)

    initial_centre = pymedphys._wlutz.findfield.get_centre_of_mass(x, y, zz)

    assert np.allclose(initial_centre, centre)
