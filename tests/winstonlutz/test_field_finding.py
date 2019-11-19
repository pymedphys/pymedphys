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
    x, y, img = pymedphys._wlutz.iview.iview_image_transform(image_path)

    centre, rotation = pymedphys._wlutz.findfield.find_centre_and_rotation(
        x, y, img, edge_lengths
    )

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

    initial_centre = pymedphys._wlutz.findfield._initial_centre(x, y, zz)
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

    initial_centre = pymedphys._wlutz.findfield._initial_centre(x, y, zz)

    assert np.allclose(initial_centre, centre)
