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


"""Testing of a single mlc pair.
"""

import numpy as np

from pymedphys.mudensity import single_mlc_pair


def test_minimal_variance_with_resolution():
    mlc_left = (-2.3, 3.1)
    mlc_right = (0, 7.7)

    x_coarse, mu_density_coarse = single_mlc_pair(
        mlc_left, mlc_right, 1)
    x_fine, mu_density_fine = single_mlc_pair(
        mlc_left, mlc_right, 0.01)

    reference = np.argmin(np.abs(x_fine[None, :] - x_coarse[:, None]), axis=0)

    average_mu_density_fine = []
    for i in range(2, len(x_coarse) - 2):
        average_mu_density_fine.append(
            np.mean(mu_density_fine[reference == i]))

    average_mu_density_fine = np.array(average_mu_density_fine)

    assert np.allclose(
        average_mu_density_fine, mu_density_coarse[2:-2], 0.1)


def test_stationary_partial_occlusion():
    _, mu_density = single_mlc_pair((-1, -1), (2.7, 2.7), 1)

    assert np.allclose(mu_density, [0.5, 1, 1, 1, 0.2])


def test_large_travel():
    x, mu_density = single_mlc_pair(
        (-400, 400), (400, 400)
    )

    linear = (x + 400) / 800
    linear[-1] = 0.5

    assert np.allclose(linear, mu_density, atol=0.001)
