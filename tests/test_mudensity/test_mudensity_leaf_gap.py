# Copyright (C) 2019 Simon Biggs

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
import pytest

from pymedphys.mudensity import calc_mu_density

MU = [0, 30]

MLC = np.array([
    [
        [4, -3],
        [4, -3],
        [4, -3]
    ],
    [
        [-3, 4],
        [-3, 4],
        [-3, 4]
    ]
])

JAW = np.array([
    [3, 3],
    [3, 3]
])

LEAF_PAIR_WIDTHS = [2, 2, 2]


def test_max_leaf_gap():
    max_leaf_gap_init = 2 * np.max(np.abs(MLC))
    grid_resolution = 2
    how_many_to_test = 20

    max_leaf_gap_init = (
        np.ceil(max_leaf_gap_init / 2 / grid_resolution) * 2 * grid_resolution)

    multiple_max_leaf_gaps = np.arange(
        max_leaf_gap_init,
        max_leaf_gap_init + how_many_to_test * 2 * grid_resolution,
        2 * grid_resolution)

    init_mu_density = calc_mu_density(
        MU, MLC, JAW,
        leaf_pair_widths=LEAF_PAIR_WIDTHS,
        max_leaf_gap=max_leaf_gap_init, grid_resolution=grid_resolution)

    for i, max_leaf_gap in enumerate(multiple_max_leaf_gaps):
        mu_density = calc_mu_density(
            MU, MLC, JAW,
            leaf_pair_widths=LEAF_PAIR_WIDTHS,
            max_leaf_gap=max_leaf_gap, grid_resolution=grid_resolution)

        assert not np.all(mu_density == 0)
        if i != 0:
            assert np.all(mu_density[:, i:-i] == init_mu_density)

    with pytest.raises(ValueError):
        calc_mu_density(
            MU, MLC, JAW,
            leaf_pair_widths=LEAF_PAIR_WIDTHS,
            max_leaf_gap=max_leaf_gap_init + 1, grid_resolution=grid_resolution
        )
