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
import pandas as pd
import xarray as xr

from deepdiff import DeepDiff

from pymedphys_labs.simonbiggs.profilescore import DoseProfile


def linear(x):
    return np.array(x) * 4


def test_resample():
    x = np.arange(-3, 4)
    profile = DoseProfile(x=x, data=linear(x))

    new_x = x / 2

    assert np.all(profile.x == x)
    assert np.all(profile.data == linear(x))

    assert ~np.all(profile.x == new_x)
    assert ~np.all(profile.data == linear(new_x))

    new_profile = profile.resample(new_x)

    assert np.all(new_profile.x == new_x)
    assert np.all(new_profile.data == linear(new_x))

    assert ~np.all(new_profile.x == x)
    assert ~np.all(new_profile.data == linear(x))
