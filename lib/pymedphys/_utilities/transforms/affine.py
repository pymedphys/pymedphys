# Copyright (C) 2019 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pymedphys._imports import numpy as np


def rotate_about_vector(coords_to_rotate, vector, theta, active=False):
    r"""Rotates a 3 x n vector of the form np.array((x, y, z)) about the axis specified
    by `vector`. Transforms can be active (alibi) or passive (alias). Default is
    passive.
    """
    unit_vector = vector / np.linalg.norm(vector)

    u_x = unit_vector[0]
    u_y = unit_vector[1]
    u_z = unit_vector[2]

    s = np.sin(np.radians(theta))
    c = np.cos(np.radians(theta))

    rotation_matrix = np.array(
        [
            [
                c + u_x * u_x * (1 - c),
                u_x * u_y * (1 - c) - u_z * s,
                u_x * u_z * (1 - c) + u_y * s,
            ],
            [
                u_y * u_x * (1 - c) + u_z * s,
                c + u_y * u_y * (1 - c),
                u_y * u_z * (1 - c) - u_x * s,
            ],
            [
                u_z * u_x * (1 - c) - u_y * s,
                u_z * u_y * (1 - c) + u_x * s,
                c + u_z * u_z * (1 - c),
            ],
        ]
    )

    # Rotation matrix above is active (unlike in other functions). Will manually
    # transpose to avoid confusion later...
    if not active:
        rotation_matrix = rotation_matrix.transpose()

    return rotation_matrix @ coords_to_rotate


def rotate_about_x(coords_to_rotate, psi, active=False):
    r"""Rotates a 3 x n vector of the form np.array((x, y, z)) about the x-axis.
    Transforms can be active (alibi) or passive (alias), but are passive by default.
    """
    s = np.sin(np.radians(psi))
    c = np.cos(np.radians(psi))

    x_rotation_matrix = np.array([[1, 0, 0], [0, c, s], [0, -s, c]])

    if active:
        x_rotation_matrix = x_rotation_matrix.transpose()

    return x_rotation_matrix @ coords_to_rotate


def rotate_about_y(coords_to_rotate, phi, active=False):
    r"""Rotates a 3 x n vector of the form np.array((x, y, z)) about the y-axis
    Transforms can be active (alibi) or passive (alias), but are passive by default.
    """
    s = np.sin(np.radians(phi))
    c = np.cos(np.radians(phi))

    y_rotation_matrix = np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])
    if active:
        y_rotation_matrix = y_rotation_matrix.transpose()

    return y_rotation_matrix @ coords_to_rotate


def rotate_about_z(coords_to_rotate, theta, active=False):
    r"""Rotates a 3 x n vector of the form np.array((x, y, z)) about the z-axis
    Transforms can be active (alibi) or passive (alias), but are passive by default.
    """
    s = np.sin(np.radians(theta))
    c = np.cos(np.radians(theta))

    z_rotation_matrix = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])

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
