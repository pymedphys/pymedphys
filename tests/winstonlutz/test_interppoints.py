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
import pymedphys._wlutz.interppoints


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

    field = pymedphys._mocks.profiles.create_rectangular_field_function(
        centre, edge_lengths, penumbra, degrees
    )
    origin_field = pymedphys._mocks.profiles.create_rectangular_field_function(
        [0, 0], edge_lengths, penumbra, 0
    )

    (
        xx_origin_left_right,
        yy_origin_left_right,
        xx_origin_top_bot,
        yy_origin_top_bot,
    ) = pymedphys._wlutz.interppoints.define_penumbra_points_at_origin(
        edge_lengths, penumbra
    )

    points_at_origin = pymedphys._wlutz.interppoints.define_penumbra_points_at_origin(
        edge_lengths, penumbra
    )

    (
        xx_left_right,
        yy_left_right,
        xx_top_bot,
        yy_top_bot,
    ) = pymedphys._wlutz.interppoints.transform_penumbra_points(
        points_at_origin, centre, degrees
    )

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

    field = pymedphys._mocks.profiles.create_rectangular_field_function(
        centre, edge_lengths, penumbra, degrees
    )
    x_profile = pymedphys._mocks.profiles.create_profile_function(
        0, edge_lengths[0], penumbra
    )
    y_profile = pymedphys._mocks.profiles.create_profile_function(
        0, edge_lengths[1], penumbra
    )

    (
        xx_left_right,
        yy_left_right,
        xx_top_bot,
        yy_top_bot,
    ) = pymedphys._wlutz.interppoints.define_penumbra_points_at_origin(
        edge_lengths, penumbra
    )

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
