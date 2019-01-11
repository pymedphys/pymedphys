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


from copy import copy, deepcopy
from typing import Callable, Union

import numpy as np
from scipy import interpolate
import matplotlib.pyplot as plt

import xarray as xr

from .._level0.libutils import get_imports
# from .._level1.coreobjects import _PyMedPhysBase
IMPORTS = get_imports(globals())


NumpyFunction = Callable[[np.ndarray], np.ndarray]


# pylint: disable = C0103, C0121


class DoseData():
    def __init__(self, dist, dose=None, func=None):
        if dose is None and func is None:
            raise ValueError("Must define either `dose` or `func`")

        if dose is not None and func is not None:
            raise ValueError("Cannot define both `dose` and `func`")

        self._func: Union[NumpyFunction, None] = None

        if func is not None:
            dose_init = func(np.array(dist))
        else:
            dose_init = dose

        self._xarray = xr.DataArray(dose_init, coords=[('dist', dist)])

        # Set each property so that they can raise errors if need be
        self.dist = dist

        if func is not None and dose is None:
            self.func = func
        elif dose is not None and func is None:
            self.dose = dose
        else:
            raise AssertionError()

    @property
    def dose(self) -> np.ndarray:
        return self._xarray.data  # type: ignore

    @dose.setter
    def dose(self, array) -> None:
        array = np.array(array)
        if len(np.shape(array)) != 1:
            raise ValueError("`dose` must be of one dimension.")

        self._xarray.data = array

    def has_custom_func(self):
        return self._func is not None

    @property
    def dist(self) -> np.ndarray:
        return self._xarray.dist.data  # type: ignore

    @dist.setter
    def dist(self, array) -> None:
        array = np.array(array)
        if len(np.shape(array)) != 1:
            raise ValueError("`dist` must be of one dimension.")

        self._xarray.dist.data = array

        if self.has_custom_func():
            self.dose = self._func(self.dist)  # type: ignore

    def _interp1d(self) -> NumpyFunction:
        return interpolate.interp1d(self.dist, self.dose)  # type: ignore

    @property
    def func(self) -> NumpyFunction:
        if self._func is not None:
            return self._func

        return self._interp1d()

    @func.setter
    def func(self, function: NumpyFunction) -> None:
        self._func = function
        self.dose = function(self.dist)  # type: ignore

    def shift(self, applied_shift, inplace=False):
        if inplace:
            adjusted_object = self
        else:
            adjusted_object = self.deepcopy()

        if adjusted_object.has_custom_func():
            old_func = copy(adjusted_object.func)
            adjusted_object.func = lambda x: old_func(x - applied_shift)

        adjusted_object.dist = adjusted_object.dist + applied_shift

        if not inplace:
            return adjusted_object

    def plot(self):
        return plt.plot(
            self.dist, self.dose, 'o-', label=self._func.__name__)

    def interactive(self):
        pass

    def to_xarray(self):
        return deepcopy(self._xarray)

    def to_pandas(self):
        return self.to_xarray().to_pandas()

    def to_dict(self):
        return self.to_xarray().to_dict()

    def deepcopy(self):
        return deepcopy(self)


class ProfileDoseData(DoseData):

    def resample(self):
        pass

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


class DepthDoseData(DoseData):
    pass
