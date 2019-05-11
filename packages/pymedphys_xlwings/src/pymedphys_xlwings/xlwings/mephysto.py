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

from pymedphys_utilities.utilities import wildcard_file_resolution
from pymedphys_fileformats.mephysto import load_single_item


@xw.func
@xw.arg('filepath')
@xw.arg('index')
@xw.ret(expand='table')
def mephysto(filepath, index):
    filepath_found = wildcard_file_resolution(filepath)

    (
        axis, reading, scan_curvetype, scan_depth
    ) = load_single_item(filepath_found, int(index))

    second_column_header = ["Reading"]

    if scan_curvetype == "PDD":
        first_column_header = [
            "Depth Profile", "Depth (mm)"
        ]
        second_column_header = [None] + second_column_header
    elif scan_curvetype == "INPLANE_PROFILE":
        first_column_header = [
            "Inplane Profile", "y (mm)"
        ]
        second_column_header = (
            ["Depth = {} mm".format(scan_depth)] + second_column_header)
    elif scan_curvetype == "CROSSPLANE_PROFILE":
        first_column_header = [
            "Crossplane Profile", "x (mm)"
        ]
        second_column_header = (
            ["Depth = {} mm".format(scan_depth)] + second_column_header)
    else:
        raise ValueError("Unexpected Profile Type")

    first_column = np.concatenate([first_column_header, axis])
    second_column = np.concatenate([second_column_header, reading])

    return np.vstack([first_column, second_column]).T
