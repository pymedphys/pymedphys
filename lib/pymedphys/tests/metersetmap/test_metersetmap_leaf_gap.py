# Copyright (C) 2019 Simon Biggs

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
from pymedphys._imports import pytest

from pymedphys._metersetmap.metersetmap import calc_metersetmap

MU = [0, 30]
MLC = [[[4, -3], [4, -3], [4, -3]], [[-3, 4], [-3, 4], [-3, 4]]]
JAW = [[3, 3], [3, 3]]
LEAF_PAIR_WIDTHS = [2, 2, 2]


def test_max_leaf_gap():
    max_leaf_gap_init = 2 * np.max(np.abs(MLC))
    grid_resolution = 2
    how_many_to_test = 20

    max_leaf_gap_init = (
        np.ceil(max_leaf_gap_init / 2 / grid_resolution) * 2 * grid_resolution
    )

    multiple_max_leaf_gaps = np.arange(
        max_leaf_gap_init,
        max_leaf_gap_init + how_many_to_test * 2 * grid_resolution,
        2 * grid_resolution,
    )

    init_metersetmap = calc_metersetmap(
        MU,
        MLC,
        JAW,
        leaf_pair_widths=LEAF_PAIR_WIDTHS,
        max_leaf_gap=max_leaf_gap_init,
        grid_resolution=grid_resolution,
    )

    for i, max_leaf_gap in enumerate(multiple_max_leaf_gaps):
        metersetmap = calc_metersetmap(
            MU,
            MLC,
            JAW,
            leaf_pair_widths=LEAF_PAIR_WIDTHS,
            max_leaf_gap=max_leaf_gap,
            grid_resolution=grid_resolution,
        )

        assert not np.all(metersetmap == 0)
        if i != 0:
            assert np.all(metersetmap[:, i:-i] == init_metersetmap)

    with pytest.raises(ValueError):
        calc_metersetmap(
            MU,
            MLC,
            JAW,
            leaf_pair_widths=LEAF_PAIR_WIDTHS,
            max_leaf_gap=max_leaf_gap_init + 1,
            grid_resolution=grid_resolution,
        )
