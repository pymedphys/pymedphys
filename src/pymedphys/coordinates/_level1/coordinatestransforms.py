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
from numpy import sin, cos, pi, radians
from numpy import linalg as LA

from ...libutils import get_imports
IMPORTS = get_imports(globals())


def rotate_about_vector(coords_to_rotate, vector, theta, active=False):
    r"""Rotates a 3 x n vector of the form np.array((x, y, z)) about the axis specified by
    `vector`. Transforms can be active (alibi) or passive (alias). Default is passive.
    """
    unit_vector = vector / LA.norm(vector)

    u_x = unit_vector[0]
    u_y = unit_vector[1]
    u_z = unit_vector[2]

    s = sin(radians(theta))
    c = cos(radians(theta))

    rotation_matrix = np.array([[c + u_x*u_x*(1-c), u_x*u_y*(1-c) - u_z*s, u_x*u_z*(1-c) + u_y*s],
                                [u_y*u_x*(1-c) + u_z*s,     c + u_y *
                                 u_y*(1-c), u_y*u_z*(1-c) - u_x*s],
                                [u_z*u_x*(1-c) - u_y*s, u_z*u_y*(1-c) + u_x*s,     c + u_z*u_z*(1-c)]])

    # Rotation matrix above is active (unlike in other functions). Will manually transpose to avoid
    # confusion later...
    if not active:
        rotation_matrix = rotation_matrix.transpose()

    return rotation_matrix @ coords_to_rotate


def rotate_about_x(coords_to_rotate, psi, active=False):
    r"""Rotates a 3 x n vector of the form np.array((x, y, z)) about the x-axis.
    Transforms can be active (alibi) or passive (alias), but are passive by default.
    """
    s = sin(radians(psi))
    c = cos(radians(psi))

    x_rotation_matrix = np.array([[1, 0, 0],
                                  [0, c, s],
                                  [0, -s, c]])

    if active:
        x_rotation_matrix = x_rotation_matrix.transpose()

    return x_rotation_matrix @ coords_to_rotate


def rotate_about_y(coords_to_rotate, phi, active=False):
    r"""Rotates a 3 x n vector of the form np.array((x, y, z)) about the y-axis
    Transforms can be active (alibi) or passive (alias), but are passive by default.
    """
    s = sin(radians(phi))
    c = cos(radians(phi))

    y_rotation_matrix = np.array([[c, 0, -s],
                                  [0, 1, 0],
                                  [s, 0, c]])
    if active:
        y_rotation_matrix = y_rotation_matrix.transpose()

    return y_rotation_matrix @ coords_to_rotate


def rotate_about_z(coords_to_rotate, theta, active=False):
    r"""Rotates a 3 x n vector of the form np.array((x, y, z)) about the z-axis
    Transforms can be active (alibi) or passive (alias), but are passive by default.
    """
    s = sin(radians(theta))
    c = cos(radians(theta))

    z_rotation_matrix = np.array([[c, s, 0],
                                  [-s, c, 0],
                                  [0, 0, 1]])

    if active:
        z_rotation_matrix = z_rotation_matrix.transpose()

    return z_rotation_matrix @ coords_to_rotate


def translate(coords_to_translate, translation_vector, active=False):
    r"""Translates a 3 x Y array of the form np.array((x, y, z)) by a given
    displacement vector of the same form. Transforms can be active (alibi)
    or passive (alias), but are passive by default.
    """
    translation_dims = np.shape(coords_to_translate)

    for _ in translation_dims[1::]:
        translation_vector = np.expand_dims(translation_vector, axis=-1)

    if active:
        translation_vector = -translation_vector

    return coords_to_translate - translation_vector
