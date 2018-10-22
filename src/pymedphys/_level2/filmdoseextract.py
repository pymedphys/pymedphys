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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


import numpy as np
from scipy.optimize import basinhopping

from .._level1.dcmdose import (
    pull_structure, contour_to_points
)
from .._level1._geometry import (
    cubify_cube_definition, cube_vertices, get_bounding_box, test_if_in_cube,
    plot_cube, cube_vectors
)


def dose_inside_cube(x_dose, y_dose, z_dose, dose, cube):
    """Find the dose just within the given cube.
    """
    cube_definition = cubify_cube_definition(cube)
    print(cube_definition)
    vertices = cube_vertices(cube_definition)
    bounding_box = get_bounding_box(vertices)

    x_outside = (x_dose < bounding_box[1][0]) | (x_dose > bounding_box[1][1])
    y_outside = (y_dose < bounding_box[0][0]) | (y_dose > bounding_box[0][1])
    z_outside = (z_dose < bounding_box[2][0]) | (z_dose > bounding_box[2][1])

    xx, yy, zz = np.meshgrid(
        x_dose[np.invert(x_outside)],
        y_dose[np.invert(y_outside)],
        z_dose[np.invert(z_outside)])

    where_x = np.where(np.invert(x_outside))[0]
    where_y = np.where(np.invert(y_outside))[0]
    where_z = np.where(np.invert(z_outside))[0]

    bounded_dose = dose[
        where_y[0]:where_y[-1]+1,
        where_x[0]:where_x[-1]+1,
        where_z[0]:where_z[-1]+1
    ]

    points_to_test = np.array([
        [y, x, z, d]
        for y, x, z, d
        in zip(
            np.ravel(yy),
            np.ravel(xx),
            np.ravel(zz),
            np.ravel(bounded_dose)
        )
    ])

    inside_cube = [
        test_if_in_cube(point_test, cube_definition)
        for point_test in points_to_test[:, 0:3]
    ]

    points_inside_cube = points_to_test[inside_cube, :]

    ax = plot_cube(cube_definition)
    ax.scatter(
        points_inside_cube[:, 1],
        points_inside_cube[:, 0],
        points_inside_cube[:, 2],
        c=points_inside_cube[:, 3], alpha=0.4
    )

    return ax


def calc_min_distance(cube_definition, contours):
    vertices = cube_vertices(cube_definition)

    vectors = cube_vectors(cube_definition)
    unit_vectors = [
        vector / np.linalg.norm(vector)
        for vector in vectors
    ]

    plane_norms = np.array([
        unit_vectors[1],
        -unit_vectors[0],
        -unit_vectors[1],
        unit_vectors[0],
        unit_vectors[2],
        -unit_vectors[2]
    ])

    plane_points = np.array([
        vertices[0],
        vertices[1],
        vertices[2],
        vertices[0],
        vertices[0],
        vertices[3]
    ])

    plane_origin_dist = -np.sum(plane_points * plane_norms, axis=1)

    distance_to_planes = np.dot(
        plane_norms, contours) + plane_origin_dist[:, None]
    min_dist_squared = np.min(distance_to_planes**2, axis=0)

    return min_dist_squared


def create_minimise(structure_name, dcm_struct):
    contours = pull_structure(structure_name, dcm_struct)
    contour_points = contour_to_points(contours)

    def minimise(cube):
        cube_definition = cubify_cube_definition(
            [tuple(cube[0:3]), tuple(cube[3:6]), tuple(cube[6::])]
        )
        min_dist_squared = calc_min_distance(cube_definition, contour_points)
        return np.sum(min_dist_squared)

    return minimise


def get_interpolated_dose(coords_grid, dose_interpolation):
    coords_grid_ij_indexing = np.array([
        np.ravel(coords_grid[:, :, 1]),
        np.ravel(coords_grid[:, :, 0]),
        np.ravel(coords_grid[:, :, 2])
    ]).T

    interpolated_dose = dose_interpolation(coords_grid_ij_indexing)
    coords_dim = np.shape(coords_grid)
    interpolated_dose = np.reshape(
        interpolated_dose, (coords_dim[0], coords_dim[1]))

    return interpolated_dose


def get_structure_aligned_cube(x0, structure_name, dcm_struct):

    to_minimise = create_minimise(structure_name, dcm_struct)

    def print_fun(x, f, accepted):
        print("at minimum %.4f accepted %d" % (f, int(accepted)))

    result = basinhopping(
        to_minimise, x0, callback=print_fun, niter=10, stepsize=5)

    cube = result.x

    cube_definition = cubify_cube_definition(
        [tuple(cube[0:3]), tuple(cube[3:6]), tuple(cube[6::])]
    )

    cube_definition_array = [
        np.array(list(item))
        for item in cube_definition
    ]

    vectors = [
        cube_definition_array[1] - cube_definition_array[0],
        cube_definition_array[2] - cube_definition_array[0],
        cube_definition_array[3] - cube_definition_array[0]
    ]

    return cube_definition_array, vectors
