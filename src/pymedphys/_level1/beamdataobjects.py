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


from copy import copy, deepcopy
from typing import Callable, Union

import numpy as np
from scipy import interpolate
import matplotlib.pyplot as plt

import xarray as xr

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


NumpyFunction = Callable[[np.ndarray], np.ndarray]


# pylint: disable = C0103, C0121


class _BaseDose:
    def __init__(self):
        self._dose_init: np.ndarray = None
        self._dist_init: np.ndarray = None
        self._func: Union[NumpyFunction, None] = None
        self._xarray: xr.DataArray = None

    @property
    def dose(self) -> np.ndarray:
        try:
            return self._xarray.data
        except AttributeError:
            return self._dose_init

    @dose.setter
    def dose(self, array) -> None:
        array = np.array(array)
        if len(np.shape(array)) != 1:
            raise ValueError("`dose` must be of one dimension.")

        try:
            self._xarray.data = array
        except AttributeError:
            self._dose_init = array
            self._create_xarray_if_both_init_defined()

    def _create_xarray_if_both_init_defined(self):
        if self._dist_init is not None and self._dose_init is not None:
            if self._xarray is None:
                self._xarray = xr.DataArray(
                    self._dose_init, coords=[('dist', self._dist_init)])

    @property
    def dist(self) -> np.ndarray:
        try:
            return self._xarray.dist.data
        except AttributeError:
            return self._dist_init

    @dist.setter
    def dist(self, array) -> None:
        array = np.array(array)
        if len(np.shape(array)) != 1:
            raise ValueError("`dist` must be of one dimension.")

        try:
            self._xarray.dist.data = array
        except AttributeError:
            self._dist_init = array
            self._create_xarray_if_both_init_defined()

        self._dist_init = array
        self._update_dose()

    def _update_dose(self):
        if self._dist_init is not None and self._func is not None:
            self.dose = self._func(self.dist)

    @property
    def func(self) -> NumpyFunction:
        if self._func is not None:
            return self._func

        if self._xarray is None:
            raise ValueError(
                "Either define a `func` or provide both `dist` and "
                "`dose` values for linear interpolation.")

        return self._interp1d()

    @func.setter
    def func(self, function: NumpyFunction) -> None:
        self._func = function
        self._update_dose()

    def _interp1d(self) -> NumpyFunction:
        return interpolate.interp1d(self.dist, self.dose)  # type: ignore

    def shift(self, applied_shift):
        if self._func is not None:
            old_func = copy(self._func)
            self._func = lambda x: old_func(x - applied_shift)

        self.dist = self.dist + applied_shift

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

    @property
    def deepcopy(self):
        return deepcopy(self)


class ProfileDose(_BaseDose):

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


class DepthDose(_BaseDose):
    pass
