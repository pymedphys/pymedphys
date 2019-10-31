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

from hypothesis import given
from hypothesis.strategies import floats

import numpy as np

import pymedphys._mocks.profiles
import pymedphys.labs.winstonlutz.createaxis


@given(
    floats(-20, 20),
    floats(-20, 20),
    floats(10, 20),
    floats(10, 20),
    floats(0, 2),
    floats(0, 360),
)
def test_transformed_field_interp(
    x_centre, y_centre, x_edge, y_edge, penumbra, degrees
):
    edge_lengths = [x_edge, y_edge]
    centre = [x_centre, y_centre]

    field = pymedphys._mocks.profiles.create_rectangular_field_function(
        centre, edge_lengths, penumbra, degrees
    )
    x_profile = pymedphys._mocks.profiles.create_profile_function(
        0, edge_lengths[0], penumbra
    )
    y_profile = pymedphys._mocks.profiles.create_profile_function(
        0, edge_lengths[1], penumbra
    )

    interp_size = np.max(edge_lengths) * 1.2

    field_x_interp = np.linspace(-interp_size / 2, interp_size / 2, 30)
    field_y_interp = np.linspace(-interp_size / 2, interp_size / 2, 40)

    x_interp, y_interp = pymedphys.labs.winstonlutz.createaxis.transform_axis(
        field_x_interp, field_y_interp, centre, degrees
    )

    assert np.allclose(
        x_profile(field_x_interp), field(*x_interp), rtol=0.0001, atol=0.0001
    )
    assert np.allclose(
        y_profile(field_y_interp), field(*y_interp), rtol=0.0001, atol=0.0001
    )
