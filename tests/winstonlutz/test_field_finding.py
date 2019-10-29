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

import pymedphys._mocks.profiles
import pymedphys.labs.winstonlutz.findfield


@pytest.mark.slow
@settings(
    deadline=datetime.timedelta(milliseconds=1500),
    max_examples=10,
    verbosity=Verbosity.verbose,
)
@given(
    floats(-20, 20),
    floats(-20, 20),
    floats(10, 20),
    floats(10, 20),
    floats(0.5, 2),
    floats(-360, 360),
)
def test_field_finding(x_centre, y_centre, x_edge, y_edge, penumbra, actual_rotation):
    edge_lengths = [x_edge, y_edge]
    actual_centre = [x_centre, y_centre]

    field = pymedphys._mocks.profiles.create_rectangular_field_function(
        actual_centre, edge_lengths, penumbra, actual_rotation
    )

    x = np.arange(-50, 50, 0.1)
    y = np.arange(-50, 50, 0.1)
    xx, yy = np.meshgrid(x, y)
    zz = field(xx, yy)

    initial_centre = pymedphys.labs.winstonlutz.findfield._initial_centre(x, y, zz)
    centre, rotation = pymedphys.labs.winstonlutz.findfield.field_finding_loop(
        field, edge_lengths, penumbra, initial_centre
    )

    assert np.allclose(actual_centre, centre, rtol=0.01, atol=0.01)

    if np.allclose(*edge_lengths):
        diff = (actual_rotation - rotation) % 90
        assert diff < 0.01 or diff > 89.99
    else:
        diff = (actual_rotation - rotation) % 180
        assert diff < 0.01 or diff > 179.99


def test_find_initial_field_centre():
    centre = [20, 5]

    field = pymedphys._mocks.profiles.create_square_field_function(
        centre=centre, side_length=10, penumbra_width=1, rotation=20
    )

    x = np.arange(-15, 30, 0.1)
    y = np.arange(-15, 15, 0.1)

    xx, yy = np.meshgrid(x, y)

    zz = field(xx, yy)

    initial_centre = pymedphys.labs.winstonlutz.findfield._initial_centre(x, y, zz)

    assert np.allclose(initial_centre, centre)
