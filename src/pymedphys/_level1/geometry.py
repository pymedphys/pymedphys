# Copyright (C) 2018 Cancer Care Associates

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
import matplotlib.pyplot as plt

from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


def cubify_cube_definition(cube_definition):
    """Convertes a set of 3-D points into the vertices that define a cube.

    Each point is defined as a length 3 tuple.

    Parameters
    ----------
    cube_definition : str
        A list containing three 3-D points.

        | cube_definition[0]: The origin of the cube.
        | cube_definition[1]: Point that primarily determines the cube edge lengths.
        | cube_definition[2]: Point that primarily defines the cube rotation.


    Returns
    -------
    final_points
        A list containing four 3-D points on the vertices of a cube.

    Examples
    --------
    >>> import numpy as np
    >>> from pymedphys.geometry import cubify_cube_definition
    >>>
    >>> cube_definition = [(0, 0, 0), (0, 1, 0), (0, 0, 1)]
    >>> np.array(cubify_cube_definition(cube_definition))
    array([[0., 0., 0.],
           [0., 1., 0.],
           [0., 0., 1.],
           [1., 0., 0.]])


    The second point has primary control over the resulting edge lengths.

    >>> cube_definition = [(0, 0, 0), (0, 3, 0), (0, 0, 1)]
    >>> np.array(cubify_cube_definition(cube_definition))
    array([[0., 0., 0.],
           [0., 3., 0.],
           [0., 0., 3.],
           [3., 0., 0.]])


    The third point has control over the final cube rotation.

    >>> cube_definition = [(0, 0, 0), (0, 1, 0), (1, 0, 0)]
    >>> np.array(cubify_cube_definition(cube_definition))
    array([[ 0.,  0.,  0.],
           [ 0.,  1.,  0.],
           [ 1.,  0.,  0.],
           [ 0.,  0., -1.]])
    """
    cube_definition_array = [
        np.array(list(item))
        for item in cube_definition
    ]
    start = cube_definition_array[0]
    length_decider_vector = (
        cube_definition_array[1] - cube_definition_array[0])
    length = np.linalg.norm(length_decider_vector)

    rotation_decider_vector = (
        cube_definition_array[2] - cube_definition_array[0])
    rotation_decider_vector = rotation_decider_vector / \
        np.linalg.norm(rotation_decider_vector) * length

    orthogonal_vector = np.cross(
        length_decider_vector, rotation_decider_vector)
    orthogonal_vector = orthogonal_vector / \
        np.linalg.norm(orthogonal_vector) * length

    orthogonal_rotation_decider_vector = np.cross(
        orthogonal_vector, length_decider_vector)
    orthogonal_rotation_decider_vector = (
        orthogonal_rotation_decider_vector /
        np.linalg.norm(orthogonal_rotation_decider_vector) * length)

    final_points = [
        tuple(start),
        tuple(start + length_decider_vector),
        tuple(start + orthogonal_rotation_decider_vector),
        tuple(start + orthogonal_vector)
    ]

    return final_points


def get_cube_definition_array(cube_definition):
    cube_definition_array = [
        np.array(list(item))
        for item in cube_definition
    ]

    return cube_definition_array


def cube_vectors(cube_definition):
    cube_definition_array = get_cube_definition_array(cube_definition)

    vectors = [
        cube_definition_array[1] - cube_definition_array[0],
        cube_definition_array[2] - cube_definition_array[0],
        cube_definition_array[3] - cube_definition_array[0]
    ]

    return vectors


def cube_vertices(cube_definition):
    cube_definition_array = get_cube_definition_array(cube_definition)

    points = []
    points += cube_definition_array
    vectors = cube_vectors(cube_definition)

    points += [cube_definition_array[0] + vectors[0] + vectors[1]]
    points += [cube_definition_array[0] + vectors[0] + vectors[2]]
    points += [cube_definition_array[0] + vectors[1] + vectors[2]]
    points += [cube_definition_array[0] + vectors[0] + vectors[1] + vectors[2]]

    points = np.array(points)

    return points


def get_bounding_box(points):
    x_min = np.min(points[:, 1])
    x_max = np.max(points[:, 1])
    y_min = np.min(points[:, 0])
    y_max = np.max(points[:, 0])
    z_min = np.min(points[:, 2])
    z_max = np.max(points[:, 2])

    max_range = np.array(
        [x_max-x_min, y_max-y_min, z_max-z_min]).max() / 2.0

    mid_x = (x_max+x_min) * 0.5
    mid_y = (y_max+y_min) * 0.5
    mid_z = (z_max+z_min) * 0.5

    return [
        [mid_y - max_range, mid_y + max_range],
        [mid_x - max_range, mid_x + max_range],
        [mid_z - max_range, mid_z + max_range]
    ]


def plot_cube(cube_definition):
    points_matpltlib_order = cube_vertices(cube_definition)
    points = points_matpltlib_order.copy()
    points[:, 0], points[:, 1] = points[:, 1], points[:, 0].copy()

    edges = [
        [points[0], points[3], points[5], points[1]],
        [points[1], points[5], points[7], points[4]],
        [points[4], points[2], points[6], points[7]],
        [points[2], points[6], points[3], points[0]],
        [points[0], points[2], points[4], points[1]],
        [points[3], points[6], points[7], points[5]]
    ]

    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    faces = Poly3DCollection(edges, linewidths=1, edgecolors='k')
    faces.set_facecolor((0, 0, 1, 0.1))

    ax.add_collection3d(faces)

    bounding_box = get_bounding_box(points_matpltlib_order)

    ax.set_xlim(bounding_box[1])
    ax.set_ylim(bounding_box[0])
    ax.set_zlim(bounding_box[2])


#     ax.set_aspect('equal')
    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.set_zlabel('z')
    ax.set_aspect('equal')

    return ax


def test_if_in_range(point_test, point_start, point_end):
    point_test = np.array(point_test)
    point_start = np.array(point_start)
    point_end = np.array(point_end)

    vector = point_end - point_start
    dot = np.dot(point_test, vector)
    item = [
        dot,
        np.dot(vector, point_start),
        np.dot(vector, point_end)
    ]
    item.sort()

    return item[1] == dot


def test_if_in_cube(point_test, cube_definition):
    return (
        test_if_in_range(point_test, cube_definition[0], cube_definition[1]) and
        test_if_in_range(point_test, cube_definition[0], cube_definition[2]) and
        test_if_in_range(point_test, cube_definition[0], cube_definition[3])
    )
