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

from hypothesis import given
from hypothesis.strategies import floats

import numpy as np

import pymedphys._mocks.profiles
import pymedphys._wlutz.createaxis
import pymedphys._wlutz.interppoints


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

    transform = pymedphys._wlutz.interppoints.translate_and_rotate_transform(
        centre, degrees
    )

    x_interp, y_interp = pymedphys._wlutz.createaxis.transform_axis(
        field_x_interp, field_y_interp, transform
    )

    assert np.allclose(
        x_profile(field_x_interp), field(*x_interp), rtol=0.0001, atol=0.0001
    )
    assert np.allclose(
        y_profile(field_y_interp), field(*y_interp), rtol=0.0001, atol=0.0001
    )
