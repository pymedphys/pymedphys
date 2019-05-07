# Copyright (C) 2018 Paul King

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

import numpy as np
# import pytest

from pymedphys_labs.paulking.collequivalent import (
    mlc_equivalent_square_fs, A_LEAF_TYPE, AGILITY)


def test_equivalent_mlc():
    """Compare effective field size for known pattern against benchmark."""
    mlc_segments = [(0.0, 0.0)] * 14
    mlc_segments += [
        (3.03, 2.47), (2.88, 2.46), (3.08, 2.51), (2.86, 2.46),
        (2.88, 2.46), (2.91, 5.04), (2.5, 5.04), (2.55, 4.87),
        (2.38, 4.61), (2.38, 7.04), (2.61, 7.46), (2.48, 6.55),
        (3.02, 6.52), (3.9, 7.2), (4.5, 7.5), (4.5, 7.5), (4.5, 7.5),
        (4.5, 7.5), (4.45, 7.5), (4.0, 7.5), (3.5, 7.5), (3.49, 7.5),
        (3.0, 7.5), (3.0, 7.5), (3.0, 7.5), (2.5, 7.5), (2.5, 7.5),
        (2.49, 6.52)]
    mlc_segments += [(0.0, 0.0)] * 18

    mlc_segments = np.array(mlc_segments) * 10  # convert to mm

    assert abs(
        mlc_equivalent_square_fs(mlc_segments, A_LEAF_TYPE) - 107.25
    ) < 0.05


def an_equivalent_square(square_size):
    open_leaves = square_size // 5

    # Make sure evenly divides
    assert open_leaves == square_size / 5

    num_remaining_leaves = 80 - open_leaves
    leaves_on_top = num_remaining_leaves // 2
    leaves_on_bottom = num_remaining_leaves - leaves_on_top

    mlc_segments = (
        [(0, 0)]*leaves_on_top +
        [(square_size/2, square_size/2)] * open_leaves +
        [(0, 0)]*leaves_on_bottom)

    assert mlc_equivalent_square_fs(mlc_segments, AGILITY) == square_size


# @pytest.mark.xfail
def test_equivalent_squares():
    sizes_to_test = (
        10, 20, 50, 100, 200, 400
    )

    for square_size in sizes_to_test:
        an_equivalent_square(square_size)
