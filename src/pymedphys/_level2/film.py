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

from .._level1.geometry import (
    cubify_cube_definition, cube_vertices, get_bounding_box, test_if_in_cube,
    plot_cube
)

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


# pylint: disable=C0103

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
