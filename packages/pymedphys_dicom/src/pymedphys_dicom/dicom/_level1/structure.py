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


import operator
from functools import reduce
from collections import namedtuple

import numpy as np

from scipy.optimize import basinhopping
from scipy.interpolate import splprep, splev

import pydicom

from pymedphys_utilities.libutils import get_imports
from pymedphys_analysis.geometry import (
    cubify_cube_definition, cube_vertices, cube_vectors)

IMPORTS = get_imports(globals())


# pylint: disable=C0103


Structure = namedtuple('Structure', ['name', 'number', 'coords'])


def concatenate_a_contour_slice(x, y, z):
    return reduce(operator.add, [[str(x_i), str(y_i), str(z_i)]
                                 for x_i, y_i, z_i in zip(x, y, z)])


def create_contour_sequence_dict(structure: Structure):
    merged_contours = [concatenate_a_contour_slice(x, y, z)
                       for x, y, z in structure.coords]

    return {
        'ReferencedROINumber': structure.number,
        'ContourSequence': [
            {
                'ContourData': merged_contour
            }
            for merged_contour in merged_contours
        ]
    }


def pull_coords_from_contour_sequence(contour_sequence):
    contours_by_slice_raw = [item.ContourData for item in contour_sequence]

    x = [np.array(item[0::3]) for item in contours_by_slice_raw]
    y = [np.array(item[1::3]) for item in contours_by_slice_raw]
    z = [np.array(item[2::3]) for item in contours_by_slice_raw]

    return x, y, z


def pull_structure(structure_name, dcm_struct):
    ROI_name_to_number_map = {
        structure_set.ROIName: structure_set.ROINumber
        for structure_set in dcm_struct.StructureSetROISequence
    }

    ROI_number_to_contour_map = {
        contour.ReferencedROINumber: contour.ContourSequence
        for contour in dcm_struct.ROIContourSequence
    }

    try:
        ROI_number = ROI_name_to_number_map[structure_name]
    except KeyError:
        raise ValueError("Structure name not found (case sensitive)")

    contour_sequence = ROI_number_to_contour_map[ROI_number]
    x, y, z = pull_coords_from_contour_sequence(contour_sequence)

    return x, y, z


def list_structures(dcm_struct):
    return [item.ROIName for item in dcm_struct.StructureSetROISequence]


def resample_contour(contour, n=51):
    tck, u = splprep([contour[0], contour[1], contour[2]], s=0, k=1)
    new_points = splev(np.linspace(0, 1, n), tck)

    return new_points


def resample_contour_set(contours, n=50):
    resampled_contours = [resample_contour([x, y, z], n)
                          for x, y, z in zip(*contours)]

    return resampled_contours


def contour_to_points(contours):
    resampled_contours = resample_contour_set([
        contours[1], contours[0], contours[2]])
    contour_points = np.concatenate(resampled_contours, axis=1)

    return contour_points


def get_structure_aligned_cube(structure_name: str,
                               dcm_struct: pydicom.dataset.FileDataset,
                               quiet=False, niter=10, x0=None):
    """Align a cube to a dicom structure set.

    Designed to allow arbitrary references frames within a dicom file
    to be extracted via contouring a cube.

    Parameters
    ----------
    structure_name
        The DICOM label of the cube structure
    dcm_struct
        The pydicom reference to the DICOM structure file.
    quiet : ``bool``
        Tell the function to not print anything. Defaults to False.
    x0 : ``np.ndarray``, optional
        A 3x3 array with each row defining a 3-D point in space.
        These three points are used as initial conditions to search for
        a cube that fits the contours. Choosing initial values close to
        the structure set, and in the desired orientation will allow
        consistent results. See examples within
        `pymedphys.geometry.cubify_cube_definition`_ on what the
        effects of each of the three points are on the resulting cube.
        By default, this parameter is defined using the min/max values
        of the contour structure.

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
    >>> from pymedphys.geometry import get_structure_aligned_cube
    >>>
    >>> struct_path = 'packages/pymedphys_dicom/tests/data/struct/example_structures.dcm'
    >>> dcm_struct = pydicom.dcmread(struct_path, force=True)
    >>> structure_name = 'ANT Box'
    >>> cube_definition_array, vectors = get_structure_aligned_cube(
    ...     structure_name, dcm_struct, quiet=True, niter=1)
    >>> np.round(cube_definition_array)
    array([[-266.,  -31.,   43.],
           [-266.,   29.,   42.],
           [-207.,  -31.,   33.],
           [-276.,  -31.,  -16.]])
    >>>
    >>> np.round(vectors, 1)
    array([[  0.7,  59.9,  -0.5],
           [ 59.2,  -0.7,  -9.7],
           [ -9.7,  -0.4, -59.2]])
    """

    contours = pull_structure(structure_name, dcm_struct)
    contour_points = contour_to_points(contours)

    def to_minimise(cube):
        cube_definition = cubify_cube_definition(
            [tuple(cube[0:3]), tuple(cube[3:6]), tuple(cube[6::])]
        )
        min_dist_squared = calc_min_distance(cube_definition, contour_points)
        return np.sum(min_dist_squared)

    if x0 is None:
        concatenated_contours = [
            np.concatenate(contour_coord)
            for contour_coord in contours
        ]

        bounds = [
            (np.min(concatenated_contour), np.max(concatenated_contour))
            for concatenated_contour in concatenated_contours
        ]

        x0 = np.array([
            (bounds[1][0], bounds[0][0], bounds[2][1]),
            (bounds[1][0], bounds[0][1], bounds[2][1]),
            (bounds[1][1], bounds[0][0], bounds[2][1])
        ])

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

    cube_definition_array = np.array([
        np.array(list(item))
        for item in cube_definition
    ])

    vectors = [
        cube_definition_array[1] - cube_definition_array[0],
        cube_definition_array[2] - cube_definition_array[0],
        cube_definition_array[3] - cube_definition_array[0]
    ]

    return cube_definition_array, vectors


def calc_min_distance(cube_definition, contours):
    vertices = cube_vertices(cube_definition)

    vectors = cube_vectors(cube_definition)
    unit_vectors = [vector / np.linalg.norm(vector) for vector in vectors]

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

    distance_to_planes = np.dot(plane_norms, contours) \
        + plane_origin_dist[:, None]

    min_dist_squared = np.min(distance_to_planes**2, axis=0)

    return min_dist_squared
