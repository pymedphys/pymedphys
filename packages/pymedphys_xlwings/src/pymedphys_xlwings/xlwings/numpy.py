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

import xlwings as xw


@xw.func
@xw.arg('values', np.array, ndim=2)
@xw.ret(expand='table')
def npravel(values):
    return np.expand_dims(np.ravel(values.T), axis=1)


@xw.func
@xw.arg('values', np.array, ndim=2)
@xw.arg('repeats')
@xw.ret(expand='table')
def nprepeat(values, repeats):
    return np.expand_dims(np.repeat(values, repeats), axis=1)
