# Copyright (C) 2019 Matthew Jennings

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
from math import sin, cos, pi

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())

def rotate_about_z(coords_to_rotate, theta):
    r"""Rotates a 4 x n vector of the form np.array((x, y, z)) about the z-axis
    """
    z_rotation_matrix = np.array([[ cos((theta)*pi/180), sin((theta)*pi/180), 0],
                                  [-sin((theta)*pi/180), cos((theta)*pi/180), 0],
                                  [                   0,                   0, 1]])

    return z_rotation_matrix @ coords_to_rotate


def translate(coords_to_translate, translation_vector):
    r"""Translates a 3 x Y array of the form np.array((x, y, z)) by a given
    displacement vector of the same form
    """

    if len(coords_to_translate.shape) == 1:
        coords_to_translate_4d = np.append(coords_to_translate, 1)
    else:
        coords_to_translate_4d = np.vstack((coords_to_translate, np.ones(coords_to_translate.shape[1])))

    translation_matrix = np.array([[1, 0, 0, translation_vector[0]],
                                   [0, 1, 0, translation_vector[1]],
                                   [0, 0, 1, translation_vector[2]],
                                   [0, 0, 0,                    1]])

    return (translation_matrix @ coords_to_translate_4d)[:-1]
