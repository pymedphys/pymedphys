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

import csv
import numpy as np

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def read_mapcheck_txt(file_name):
    """
    Read and return dose array from native Profiler data file.

    Arguments:
        file_name -- long file name of profiler file

    Returns:
        The namedtuple MapCheck which has the following:
            MapCheck.x = 1-D np.array of float x-coordinates
            MapCheck.y = 1-D np.array of float y-coordinates
            MapCheck.dose = 2-D np.array of float dose, shape described by x, y
    """

    Mapcheck = namedtuple('Mapcheck', ['x', 'y', 'dose'])

    with open(file_name, 'r') as mapcheck_file:
        m_chk = '\n'.join(mapcheck_file.readlines())
        m_chk = m_chk.split('Dose Interpolated')[-1]
        m_chk = m_chk.split('\n')[2:]

    temp = [r for r in csv.reader(m_chk, delimiter='\t') if 'Xcm' in r]
    x_coord = np.array(temp[0][2:]).astype(float)
    y_coord, dose = np.array([]), np.array([])

    for line in csv.reader(m_chk, delimiter='\t'):
        if len(line) > 1:
            try:
                line = [float(r) for r in line]
                y_coord = np.insert(y_coord, 0, float(line[0]))
                dose = np.append(dose, line[2:])
            except ValueError:
                pass
    dose = np.array(dose).flatten().astype(float)
    dose.shape = (len(x_coord), len(y_coord))
    return Mapcheck(x_coord, y_coord, dose)
