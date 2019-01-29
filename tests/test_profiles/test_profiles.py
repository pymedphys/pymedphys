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

from pymedphys.profiles import DoseProfile

# pylint: disable = E1102


def cubed(x):
    return np.array(x) ** 3


def test_conversion():
    x = range(-3, 4)
    profile = DoseProfile(x=x, data=cubed(x))

    expected_x = [-3, -2, -1, 0, 1, 2, 3]
    expected_data = [-27, -8, -1, 0, 1, 8, 27]

    expected_pandas = pd.Series(
        expected_data, pd.Index(expected_x, name='x')).astype(float)
    expected_xarray = xr.DataArray(
        expected_data, coords=[('x', expected_x)], name='dose')

    expected_dict = {
        'coords': {'x': {'data': expected_x,
                         'dims': ('x',),
                         'attrs': {}}},
        'attrs': {},
        'dims': ('x',),
        'data': expected_data,
        'name': 'dose'}

    assert np.array_equal(profile.x, np.array(expected_x))
    assert np.array_equal(profile.data, np.array(expected_data))
    assert expected_pandas.equals(profile.to_pandas().astype(float))
    assert expected_xarray.identical(profile.to_xarray())
    assert DeepDiff(profile.to_dict(), expected_dict) == {}


def test_function_updating_with_shift():
    x = np.array([1, 2, 3])

    profile = DoseProfile(x=x, data=x**2)
    assert np.array_equal(profile.data, [1, 4, 9])

    profile.shift(2, inplace=True)
    assert np.array_equal(profile.data, [1, 4, 9])
    assert np.array_equal(profile.x, [3, 4, 5])

    # profile.x = [1, 2, 3]
    # assert np.array_equal(profile.dose, [1, 0, 1])

    profile.dist = [3, 4, 5]
    assert np.array_equal(profile.data, [1, 4, 9])

    # profile_copy = profile.shift(2)
    # assert np.array_equal(profile.dist, [3, 4, 5])
    # assert np.array_equal(profile_copy.dist, [5, 6, 7])


def test_default_interp_function():
    profile = DoseProfile(x=[-10, 0, 10], data=[3, 8, 2])

    assert np.array_equal(profile.interp([1, 3, 4]), [7.4, 6.2, 5.6])
