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

import pytest

import numpy as np

from pymedphys._mocks.profiles import create_square_field_function
from pymedphys.labs.winstonlutz.profiles import (
    penumbra_flip_diff,
    field_points_to_compare,
)


# pylint: disable=bad-whitespace,C1801


def test_field_points_to_compare():
    profile_centre = [4, 2]
    side_length = 8
    penumbra_width = 2
    rotations = 0
    num_points_across_penumbra = 3
    num_points_across_field_edge = 5

    expected_coords = {
        "left-right": {
            "y": [0, 1, 2, 3, 4],
            "x-left": [-1, 0, 1],
            "x-right": [7, 8, 9],
        },
        "top-bot": {"x": [2, 3, 4, 5, 6], "y-top": [5, 6, 7], "y-bot": [-3, -2, -1]},
    }


@pytest.mark.xfail(reason="Test not yet finished")
def test_profile_flip_diff():
    profile_centre = [1.7, -3.5]
    side_length = 2
    penumbra_width = 0.3
    rotations = [0, 10, 45]

    x_to_test = [0, 1, 1.6, 1.69, 1.699, 1.7, 1.701, 1.71, 1.8, 2, 3, 10]
    y_to_test = [-2, -3, -3.499, -3.5, -3.501, -4, -5]
    expected_smallest_indicies = (
        x_to_test.index(profile_centre[0]),
        y_to_test.index(profile_centre[1]),
    )

    for rotation in rotations:
        field = create_square_field_function(
            profile_centre, side_length, penumbra_width, rotation
        )

        flip_diffs = [
            [
                penumbra_flip_diff(field, (x, y), side_length, penumbra_width, rotation)
                for y in y_to_test
            ]
            for x in x_to_test
        ]

        assert np.all(np.argmin(flip_diffs) == expected_smallest_indicies)
