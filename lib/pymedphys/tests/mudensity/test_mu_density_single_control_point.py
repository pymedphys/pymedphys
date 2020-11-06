# Copyright (C) 2018 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# pylint: disable=C0103,C1801


"""Regression testing of the single control point function.
"""

import numpy as np

from pymedphys._mudensity.mudensity import calc_single_control_point

MLC = np.array([[[1, 1], [2, 2]], [[2, 2], [3, 3]]])

JAW = np.array([[1.5, 1.2], [1.5, 1.2]])

LEAF_PAIR_WIDTHS = [2, 2]

REFERENCE_MU_DENSITY = [
    [0.0, 0.07, 0.43, 0.5, 0.43, 0.07, 0.0],
    [0.0, 0.14, 0.86, 1.0, 0.86, 0.14, 0.0],
    [0.14, 0.86, 1.0, 1.0, 1.0, 0.86, 0.14],
    [0.03, 0.17, 0.2, 0.2, 0.2, 0.17, 0.03],
]


def test_partial_jaws():
    """Parital jaw location should give a fractional result.
    """
    _, mu_density = calc_single_control_point(
        MLC, JAW, leaf_pair_widths=LEAF_PAIR_WIDTHS
    )

    assert np.allclose(np.round(mu_density, 2), REFERENCE_MU_DENSITY)
