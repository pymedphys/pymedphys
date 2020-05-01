# Copyright (C) 2018 Paul King

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import csv
from collections import namedtuple

from pymedphys._imports import numpy as np


def read_mapcheck_txt(file_name):
    """
    Read native MapCheck data file and return dose array.

    Parameters
    ----------
    file_name : string
        | file name of MapCheck file including path

    Returns
    -------
    MapCheck : named tuple
        | MapCheck.x = np.array, float x-coords
        | MapCheck.y = np.array, float y-coords
        | MapCheck.dose = np.array (x,y), float dose
    """

    Mapcheck = namedtuple("Mapcheck", ["x", "y", "dose"])

    with open(file_name, "r") as mapcheck_file:
        m_chk = "\n".join(mapcheck_file.readlines())
        m_chk = m_chk.split("Dose Interpolated")[-1]
        m_chk = m_chk.split("\n")[2:]

    temp = [r for r in csv.reader(m_chk, delimiter="\t") if "Xcm" in r]
    x_coord = np.array(temp[0][2:]).astype(float)
    y_coord, dose = np.array([]), np.array([])

    for line in csv.reader(m_chk, delimiter="\t"):
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
