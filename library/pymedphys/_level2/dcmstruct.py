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
from scipy.optimize import basinhopping

import pydicom

from .._level1.geometry import (
    cubify_cube_definition, cube_vertices, cube_vectors)
from .._level1.dcmdose import (
    pull_structure, contour_to_points)

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


# pylint: disable=C0103


def get_structure_aligned_cube(x0: np.ndarray, structure_name: str,
                               dcm_struct: pydicom.dataset.FileDataset,
                               quiet=False, niter=10):
    """Align a cube to a dicom structure set.

    Designed to allow arbitrary references frames within a dicom file to be
    extracted via contouring a cube.

    Parameters
    ----------
    x0
        A 3x3 array with each row defining a 3-D point in space.
        These three points are used as initial conditions to search for
        a cube that fits the contours. Choosing initial values close to the
        structure set, and in the desired orientation will allow consistent
        results. See examples within
        `pymedphys.geometry.cubify_cube_definition`_ on what the effects
        of each of the three points are on the resulting cube.
    structure_name
        The DICOM label of the cube structure
    dcm_struct
        The pydicom reference to the DICOM structure file.
    quiet : bool
        Tell the function to not print anything. Defaults to False.

    Returns
    -------
    cube_definition_array
        Four 3-D points the define the vertices of the cube.

    vectors
        The vectors between the points that can be used to traverse the cube.

    Examples
    --------
    >>> import numpy as np
    >>> import pydicom
    >>> from pymedphys.dcm import get_structure_aligned_cube
    >>>
    >>> struct_path = 'data/srs/max_structure_set.dcm'
    >>> dcm_struct = pydicom.dcmread(struct_path, force=True)
    >>>
    >>> x0 = np.array([
    ...     -270, -35, -20,
    ...     -270, 30, -20,
    ...     -260, -35, 40
    ... ])
    >>>
    >>> structure_name = 'ANT Box'
    >>> cube_definition_array, vectors = get_structure_aligned_cube(
    ...     x0, structure_name, dcm_struct, quiet=True, niter=1)
    >>> np.round(cube_definition_array)
    array([[-276.,  -31.,  -16.],
           [-275.,   29.,  -17.],
           [-266.,  -31.,   43.],
           [-217.,  -32.,  -26.]])
    >>>
    >>> np.round(vectors, 1)
    array([[ 0.7, 59.9, -0.5],
           [ 9.7,  0.4, 59.1],
           [59.1, -0.8, -9.7]])
    """

    to_minimise = create_minimise(structure_name, dcm_struct)

    if quiet:
        def print_fun(x, f, accepted):
            pass
    else:
        def print_fun(x, f, accepted):
            print("at minimum %.4f accepted %d" % (f, int(accepted)))

    result = basinhopping(
        to_minimise, x0, callback=print_fun, niter=niter, stepsize=5)

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
