# Copyright (C) 2018 King Paul

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

"""
@author: king.r.paul@gmail.com
"""

import numpy as np


def unshuffle_sinogram(array):
    """
    Unshuffling sinogram, i.e. separate leaf pattern into the 51
    tomtherapy discretization angles, accepting a 2d list of lists
    and returning a 3-D nested list of gantry positions, each
    containting a list of leaf-open-fractions.
    Return a 3-D nested array from a 2-D nested array.
        Input
        -----
        [
          [ [leaf-open-fx] [leaf-open-fx] ... ] -> couch+gantry incr
          [ [leaf-open-fx] [leaf-open-fx] ... ] -> couch+gantry incr
        ]
        Output
        ------
        [
            [ -> gantry incr
                [ [leaf-open-fx] [leaf-open-fx] ... ]   -> couch incr
                [ [leaf-open-fx] [leaf-open-fx] ... ]   -> couch incr
            ]
            [ -> gantry incr
                [ [leaf-open-fx] [leaf-open-fx] ... ]   -> couch incr
                [ [leaf-open-fx] [leaf-open-fx] ... ]   -> couch incr
            ]
        ]
    """

    array = np.array(array)

    assert array.shape[1] == 64  # num leaves

    # SPLIT SINOGRAM INTO 51 ANGLE-INDEXED SEGMENTS
    result = [[] for i in range(51)]
    idx = 0
    for row in array:
        result[idx].append(row)
        idx = (idx + 1) % 51

    # EXCLUDE EXTERIOR LEAVES WITH ZERO LEAF-OPEN TIMES
    include = [False for f in range(64)]
    for i, angle in enumerate(result):
        for j, couch_step in enumerate(angle):
            for k, _ in enumerate(couch_step):
                if result[i][j][k] > 0.0:
                    include[k] = True
    gap = max([2 + max(i-32, 31-i) for i, v in enumerate(include) if v])
    result = [[p[31 - gap:32 + gap] for p in result[i]] for i in range(51)]

    return result
