# Copyright (C) 2019 Cancer Care Associates

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
from scipy import interpolate

import xlwings as xw


@xw.func
@xw.arg('x', np.array, ndim=1)
@xw.arg('y', np.array, ndim=1)
@xw.arg('xnew', np.array, ndim=1)
@xw.arg('fill_value')
@xw.ret(expand='table')
def linear_interpolation(x, y, xnew, fill_value=None):
    f = interpolate.interp1d(x, y, fill_value=fill_value)
    ynew = f(xnew)

    return np.expand_dims(ynew, axis=1)


@xw.func
@xw.arg('points', np.array, ndim=2)
@xw.arg('values', np.array, ndim=1)
@xw.arg('points_new', np.array, ndim=2)
@xw.ret(expand='table')
def nd_linear_interpolation(points, values, points_new):
    func = interpolate.LinearNDInterpolator(points, values)

    values_new = func(points_new)

    return np.expand_dims(values_new, axis=1)
