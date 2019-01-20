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


"""End to end regression testing.
"""

import os

import numpy as np

from pymedphys.mudensity import calc_mu_density


DATA_DIRECTORY = os.path.join(
    os.path.dirname(__file__), "../data/mudensity")
DELIVERY_DATA_FILEPATH = os.path.abspath(os.path.join(
    DATA_DIRECTORY, 'mu_density_example_arrays.npz'))


def test_regression():
    """The results of MU Density calculation should not change
    """
    regress_test_arrays = np.load(DELIVERY_DATA_FILEPATH)

    mu = regress_test_arrays['mu']
    mlc = regress_test_arrays['mlc']
    jaw = regress_test_arrays['jaw']

    cached_mu_density = regress_test_arrays['mu_density']
    mu_density = calc_mu_density(mu, mlc, jaw)
    assert np.allclose(mu_density, cached_mu_density, atol=0.1)
