# Copyright (C) 2018 Paul King

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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


from collections import namedtuple

import numpy as np

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def read_prs(file_name):
    """
    Read and return dose profiles and CAX dose from native Profiler data file.

    Arguments:
        file_name -- long file name of profiler file

    Returns:
        The namedtuple Profiler which has the following:
            Profiler.cax = float(dose) at central axis
            Profiler.x = x profile, i.e. [(distance, dose), ...]
            Profiler.x = x profile, i.e. [(distance, dose), ...]
                distance = float(+/- distance from cax
                dose = float(absolute dose at detector)
    """

    Profiler = namedtuple('Profiler', ['cax', 'x', 'y'])

    with open(file_name) as profiler_file:
        for row in profiler_file.readlines():
            contents = row
            if contents[:11] == "Calibration" and "File" not in contents:
                calibs = np.array(contents.split())[1:].astype(float)
            elif contents[:5] == "Data:":
                counts = np.array(contents.split()[5:145]).astype(float)
            elif contents[:15] == "Dose Per Count:":
                dose_per_count = (float(contents.split()[-1]))
        assert (len(calibs)) == (len(counts)) == 140
        assert dose_per_count > 0.0
    dose = counts * dose_per_count * calibs

    y_vals = [-16.4 + 0.4*i for i in range(83)]
    x_vals = [-11.2 + 0.4*i for i in range(57)]

    x_prof = list(zip(y_vals, dose[:57]))
    y_prof = list(zip(x_vals, dose[57:]))

    assert np.allclose(y_prof[41][1], x_prof[28][1])
    cax_dose = y_prof[41][1]

    return Profiler(cax_dose, x_prof, y_prof)
