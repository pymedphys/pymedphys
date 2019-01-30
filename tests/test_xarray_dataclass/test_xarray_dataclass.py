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


# pylint: disable = E1101

import numpy as np

from pymedphys.xarray import xarray_dataclass


MU = [0, 10, 20]

MLC = [
    [
        [3, -3],
        [3, -3],
        [3, -3]
    ],
    [
        [3, 3],
        [3, 3],
        [3, 3]
    ],
    [
        [-3, 3],
        [-3, 3],
        [-3, 3]
    ]
]

JAW = [
    [3, 3],
    [3, 3],
    [3, 3]
]

GANTRY = [0, 0, 0]
COLLIMATOR = [0, 0, 0]


def test_decorator():

    @xarray_dataclass
    class DummyDeliveryData:
        monitor_units: 'control_point'
        mlc: ['control_point', 'leaf_pair', 'leaf_bank']
        jaw: ['control_point', 'jaw_bank']
        gantry: 'control_point'
        collimator: 'control_point'

    new_container = DummyDeliveryData(MU, MLC, JAW, GANTRY, COLLIMATOR)

    # assert np.all(new_container.to_tuple() == (
    #     np.array(MU), np.array(MLC), np.array(JAW), np.array(GANTRY),
    #     np.array(COLLIMATOR)
    # ))
