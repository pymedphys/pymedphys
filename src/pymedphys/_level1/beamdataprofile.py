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


from copy import copy
from typing import Callable

import numpy as np
from scipy import interpolate
import matplotlib.pyplot as plt

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


# pylint: disable = C0103


def _verify_shape_agreement_if_not_none(a, b, message="Does not agree"):
    if a is not None and b is not None:
        if np.any(np.shape(a) != np.shape(b)):
            raise ValueError(message)


class Profile:
    _dose: np.ndarray = None
    _dist: np.ndarray = None
    _func: Callable = None

    @property
    def dose(self) -> np.ndarray:
        return self._dose

    @dose.setter
    def dose(self, array) -> None:
        if self._func is not None:
            raise ValueError("Cannot set dose when `func` is defined")
        _verify_shape_agreement_if_not_none(
            self._dist, array, "`dose` does not match dimensions of `dist`")

        self._dose = np.array(array)

    @property
    def dist(self) -> np.ndarray:
        return self._dist

    @dist.setter
    def dist(self, array) -> None:
        _verify_shape_agreement_if_not_none(
            self._dose, array, "`dist` does not match dimensions of `dose`")

        self._dist = np.array(array)
        self._update_dose()

    def _update_dose(self):
        if self._dist is not None and self._func is not None:
            self._dose = self._func(self._dist)

    @property
    def func(self) -> np.ndarray:
        if self._func is not None:
            return self._func

        if self._dose is None or self._dist is None:
            raise ValueError(
                "Either define a `func` or provide both `dist` and "
                "`dose` values for linear interpolation.")

        return self._interp1d()

    def _interp1d(self) -> Callable:
        return interpolate.interp1d(self._dist, self._dose)

    @func.setter
    def func(self, function: Callable) -> None:
        self._func = function
        self._update_dose()

    def shift(self, applied_shift):
        if self._func is not None:
            old_func = copy(self._func)
            self._func = lambda x: old_func(x - applied_shift)

        self._dist = self._dist + applied_shift

    def plot(self):
        return plt.plot(
            self._dist, self._dose, 'o-', label=self._func.__name__)

    @property
    def umbra(self):
        pass

    @property
    def centre(self):
        pass

    @property
    def edges(self):
        pass

    @property
    def flatness(self):
        pass

    @property
    def symmetry(self):
        pass

    def shift_to_centre(self):
        pass

    def symmetrise(self):
        pass

    def resample(self):
        pass

    def dose_normalise(self):
        pass

    def dist_normalise(self):
        pass
