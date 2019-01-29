# Copyright (C) 2018 Simon Biggs

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


# pylint: disable=C0103,C1801


"""Regression testing of the single control point function.
"""

import numpy as np

from pymedphys.mudensity import calc_single_control_point

MLC = np.array([
    [
        [1, 1],
        [2, 2],
    ],
    [
        [2, 2],
        [3, 3],
    ]
])

JAW = np.array([
    [1.5, 1.2],
    [1.5, 1.2]
])

LEAF_PAIR_WIDTHS = [2, 2]

REFERENCE_MU_DENSITY = [[0., 0.07, 0.43, 0.5, 0.43, 0.07, 0.],
                        [0., 0.14, 0.86, 1., 0.86, 0.14, 0.],
                        [0.14, 0.86, 1., 1., 1., 0.86, 0.14],
                        [0.03, 0.17, 0.2, 0.2, 0.2, 0.17, 0.03]]


def test_partial_jaws():
    """Parital jaw location should give a fractional result.
    """
    _, mu_density = calc_single_control_point(
        MLC, JAW, leaf_pair_widths=LEAF_PAIR_WIDTHS
    )

    assert np.allclose(np.round(mu_density, 2), REFERENCE_MU_DENSITY)
