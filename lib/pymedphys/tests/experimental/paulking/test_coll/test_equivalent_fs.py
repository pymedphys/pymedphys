# Copyright (C) 2018 Paul King

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pymedphys._imports import numpy as np

from pymedphys._utilities.constants import A_LEAF_TYPE, AGILITY

from pymedphys._experimental.paulking.collequivalent import (
    mlc_equivalent_square_fs as equivalent_square,
)

# import pytest


def test_equivalent_mlc():
    """Compare effective field size for known pattern against benchmark."""
    mlc_segments = [(0.0, 0.0)] * 14
    mlc_segments += [
        (3.03, 2.47),
        (2.88, 2.46),
        (3.08, 2.51),
        (2.86, 2.46),
        (2.88, 2.46),
        (2.91, 5.04),
        (2.5, 5.04),
        (2.55, 4.87),
        (2.38, 4.61),
        (2.38, 7.04),
        (2.61, 7.46),
        (2.48, 6.55),
        (3.02, 6.52),
        (3.9, 7.2),
        (4.5, 7.5),
        (4.5, 7.5),
        (4.5, 7.5),
        (4.5, 7.5),
        (4.45, 7.5),
        (4.0, 7.5),
        (3.5, 7.5),
        (3.49, 7.5),
        (3.0, 7.5),
        (3.0, 7.5),
        (3.0, 7.5),
        (2.5, 7.5),
        (2.5, 7.5),
        (2.49, 6.52),
    ]
    mlc_segments += [(0.0, 0.0)] * 18

    mlc_segments = np.array(mlc_segments) * 10  # convert to mm

    assert abs(equivalent_square(mlc_segments, A_LEAF_TYPE) - 107.25) < 0.05


def an_equivalent_square(square_size):
    open_leaves = square_size // 5

    # Make sure evenly divides
    assert open_leaves == square_size / 5

    num_remaining_leaves = 80 - open_leaves
    leaves_on_top = num_remaining_leaves // 2
    leaves_on_bottom = num_remaining_leaves - leaves_on_top

    mlc_segments = (
        [(0, 0)] * leaves_on_top
        + [(square_size / 2, square_size / 2)] * open_leaves
        + [(0, 0)] * leaves_on_bottom
    )

    assert equivalent_square(mlc_segments, AGILITY) == square_size


# @pytest.mark.xfail
def test_equivalent_squares():
    sizes_to_test = (10, 20, 50, 100, 200, 400)

    for square_size in sizes_to_test:
        an_equivalent_square(square_size)
