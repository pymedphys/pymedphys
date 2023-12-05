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


from hypothesis import given
from hypothesis.strategies import floats
from pymedphys._imports import numpy as np

from pymedphys._mocks import profiles

from pymedphys._experimental.wlutz import interppoints


@given(
    floats(-20, 20),
    floats(-20, 20),
    floats(10, 20),
    floats(10, 20),
    floats(0.5, 2),
    floats(0, 360),
)
def test_field_interp_points(x_centre, y_centre, x_edge, y_edge, penumbra, degrees):

    edge_lengths = [x_edge, y_edge]
    centre = [x_centre, y_centre]

    field = profiles.create_rectangular_field_function(
        centre, edge_lengths, penumbra, degrees
    )
    origin_field = profiles.create_rectangular_field_function(
        [0, 0], edge_lengths, penumbra, 0
    )

    (
        xx_origin_left_right,
        yy_origin_left_right,
        xx_origin_top_bot,
        yy_origin_top_bot,
    ) = interppoints.define_penumbra_points_at_origin(edge_lengths, penumbra)

    points_at_origin = interppoints.define_penumbra_points_at_origin(
        edge_lengths, penumbra
    )

    (
        xx_left_right,
        yy_left_right,
        xx_top_bot,
        yy_top_bot,
    ) = interppoints.transform_penumbra_points(points_at_origin, centre, degrees)

    assert np.allclose(
        origin_field(xx_origin_left_right, yy_origin_left_right),
        field(xx_left_right, yy_left_right),
    )

    assert np.allclose(
        origin_field(xx_origin_top_bot, yy_origin_top_bot),
        field(xx_top_bot, yy_top_bot),
    )


@given(floats(8, 20), floats(8, 20), floats(0.5, 2))
def test_field_interp_at_origin(x_edge, y_edge, penumbra):
    centre = [0, 0]
    degrees = 0
    edge_lengths = [x_edge, y_edge]

    field = profiles.create_rectangular_field_function(
        centre, edge_lengths, penumbra, degrees
    )
    x_profile = profiles.create_profile_function(0, edge_lengths[0], penumbra)
    y_profile = profiles.create_profile_function(0, edge_lengths[1], penumbra)

    (
        xx_left_right,
        yy_left_right,
        xx_top_bot,
        yy_top_bot,
    ) = interppoints.define_penumbra_points_at_origin(edge_lengths, penumbra)

    penumbra_range = np.linspace(-penumbra / 2, penumbra / 2, 11)

    x_penumbra_left_lookup = -edge_lengths[0] / 2 + penumbra_range
    y_penumbra_bot_lookup = -edge_lengths[1] / 2 + penumbra_range

    assert np.all(np.abs(np.diff(field(xx_left_right, yy_left_right), axis=0)) < 0.01)
    assert np.all(np.abs(np.diff(field(xx_top_bot, yy_top_bot), axis=1)) < 0.01)

    left_right = np.mean(field(xx_left_right, yy_left_right), axis=0)
    top_bot = np.mean(field(xx_top_bot, yy_top_bot), axis=1)

    assert np.allclose(left_right, left_right[::-1])
    assert np.allclose(top_bot, top_bot[::-1])

    x_profile_penumbra = np.concatenate(
        [x_profile(x_penumbra_left_lookup), x_profile(-x_penumbra_left_lookup[::-1])]
    )
    y_profile_penumbra = np.concatenate(
        [y_profile(y_penumbra_bot_lookup), y_profile(-y_penumbra_bot_lookup[::-1])]
    )

    assert np.allclose(left_right, x_profile_penumbra, rtol=0.01, atol=0.01)
    assert np.allclose(top_bot, y_profile_penumbra, rtol=0.01, atol=0.01)
