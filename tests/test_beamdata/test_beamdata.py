# Copyright (C) 2018 Cancer Care Associates
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
import pandas as pd
import xarray as xr

from deepdiff import DeepDiff

from pymedphys.beamdata import ProfileDose


def cubed(x):
    return x ** 3


def test_conversion():
    profile = ProfileDose()
    profile.dist = range(-3, 4)
    profile.func = cubed

    expected_dist = [-3, -2, -1, 0, 1, 2, 3]
    expected_dose = [-27, -8, -1, 0, 1, 8, 27]

    expected_pandas = pd.Series(
        expected_dose, pd.Index(expected_dist, name='dist'))
    expected_xarray = xr.DataArray(
        expected_dose, coords=[('dist', expected_dist)])

    expected_dict = {
        'coords': {'dist': {'data': expected_dist,
                            'dims': ('dist',),
                            'attrs': {}}},
        'attrs': {},
        'dims': ('dist',),
        'data': expected_dose,
        'name': None}

    assert np.array_equal(profile.dist, np.array(expected_dist))
    assert np.array_equal(profile.dose, np.array(expected_dose))
    assert expected_pandas.equals(profile.to_pandas())
    assert expected_xarray.identical(profile.to_xarray())
    assert DeepDiff(profile.to_dict(), expected_dict) == {}
