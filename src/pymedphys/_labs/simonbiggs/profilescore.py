# Copyright (C) 2019 Paul King, Simon Biggs

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


from copy import deepcopy
from typing import Callable

import numpy as np
from scipy import interpolate
import matplotlib.pyplot as plt

import xarray as xr

from pymedphys.libutils import get_imports
# from .._level1.coreobjects import _PyMedPhysBase
IMPORTS = get_imports(globals())


NumpyFunction = Callable[[np.ndarray], np.ndarray]


# pylint: disable = C0103, C0121


class DoseBase():
    def __init__(self, data, coords=None, dims=None):
        self.new_xarray(data, coords=coords, dims=dims)

    def new_xarray(self, data, coords=None, dims=None):
        self._xarray = xr.DataArray(data, coords, dims, name='dose')

    @property
    def data(self) -> np.ndarray:
        return self._xarray.data  # type: ignore

    @data.setter
    def data(self, array) -> None:
        array = np.array(array)
        self._xarray.data = array

    def to_xarray(self):
        return deepcopy(self._xarray)

    def to_pandas(self):
        return self.to_xarray().to_pandas()

    def to_dict(self):
        return self.to_xarray().to_dict()

    def deepcopy(self):
        return deepcopy(self)


class Dose1D(DoseBase):
    def __init__(self, x, data):
        self.new_xarray(x, data)

    def new_xarray(self, x, data):
        coords = [('x', x)]
        super().new_xarray(data, coords=coords)

    @property
    def x(self) -> np.ndarray:
        return self._xarray.x.data  # type: ignore

    @x.setter
    def x(self, array) -> None:
        array = np.array(array)
        if len(np.shape(array)) != 1:
            raise ValueError("`x` must be of one dimension.")

        self._xarray.x.data = array

    @property
    def interp(self) -> NumpyFunction:
        return interpolate.interp1d(self.x, self.data)  # type: ignore

    def shift(self, applied_shift, inplace=False):
        if inplace:
            adjusted_object = self
        else:
            adjusted_object = self.deepcopy()

        adjusted_object.x = adjusted_object.x + applied_shift

        if not inplace:
            return adjusted_object

    def plot(self):
        return plt.plot(self.x, self.data, 'o-')

    def interactive(self):
        pass


class DoseProfile(Dose1D):
    def interactive(self):
        pass

    def resample(self, new_x):
        resampled_profile = self.deepcopy()

        new_data = resampled_profile.interp(new_x)
        resampled_profile.new_xarray(new_x, new_data)

        return resampled_profile

    def dose_normalise(self):
        pass

    def dist_normalise(self):
        pass

    @property
    def umbra(self):
        pass

    @property
    def edges(self):
        pass

    @property
    def centre(self):
        pass

    def shift_to_centre(self):
        pass

    @property
    def flatness(self):
        pass

    @property
    def symmetry(self):
        pass

    def symmetrise(self):
        pass


class DoseDepth(Dose1D):
    pass
