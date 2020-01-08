# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import mpl_toolkits
from pymedphys._imports import numpy as np
from pymedphys._imports import plt, pydicom

from scipy.interpolate import splev, splprep
from scipy.optimize import basinhopping

from pymedphys._dicom.structure import pull_structure


def cubify_cube_definition(cube_definition):
    """Converts a set of 3-D points into the vertices that define a cube.

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
    >>> from pymedphys._imports import numpy as np
    >>> from pymedphys.labs.cube import cubify_cube_definition
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
    cube_definition_array = [np.array(list(item)) for item in cube_definition]
    start = cube_definition_array[0]
    length_decider_vector = cube_definition_array[1] - cube_definition_array[0]
    length = np.linalg.norm(length_decider_vector)

    rotation_decider_vector = cube_definition_array[2] - cube_definition_array[0]
    rotation_decider_vector = (
        rotation_decider_vector / np.linalg.norm(rotation_decider_vector) * length
    )

    orthogonal_vector = np.cross(length_decider_vector, rotation_decider_vector)
    orthogonal_vector = orthogonal_vector / np.linalg.norm(orthogonal_vector) * length

    orthogonal_rotation_decider_vector = np.cross(
        orthogonal_vector, length_decider_vector
    )
    orthogonal_rotation_decider_vector = (
        orthogonal_rotation_decider_vector
        / np.linalg.norm(orthogonal_rotation_decider_vector)
        * length
    )

    final_points = [
        tuple(start),
        tuple(start + length_decider_vector),
        tuple(start + orthogonal_rotation_decider_vector),
        tuple(start + orthogonal_vector),
    ]

    return final_points


def get_cube_definition_array(cube_definition):
    cube_definition_array = [np.array(list(item)) for item in cube_definition]

    return cube_definition_array


def cube_vectors(cube_definition):
    cube_definition_array = get_cube_definition_array(cube_definition)

    vectors = [
        cube_definition_array[1] - cube_definition_array[0],
        cube_definition_array[2] - cube_definition_array[0],
        cube_definition_array[3] - cube_definition_array[0],
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

    max_range = np.array([x_max - x_min, y_max - y_min, z_max - z_min]).max() / 2.0

    mid_x = (x_max + x_min) * 0.5
    mid_y = (y_max + y_min) * 0.5
    mid_z = (z_max + z_min) * 0.5

    return [
        [mid_y - max_range, mid_y + max_range],
        [mid_x - max_range, mid_x + max_range],
        [mid_z - max_range, mid_z + max_range],
    ]


def plot_cube(cube_definition):
    points_matplotlib_order = cube_vertices(cube_definition)
    points = points_matplotlib_order.copy()
    points[:, 0], points[:, 1] = points[:, 1], points[:, 0].copy()

    edges = [
        [points[0], points[3], points[5], points[1]],
        [points[1], points[5], points[7], points[4]],
        [points[4], points[2], points[6], points[7]],
        [points[2], points[6], points[3], points[0]],
        [points[0], points[2], points[4], points[1]],
        [points[3], points[6], points[7], points[5]],
    ]

    fig = plt.figure()
    ax = fig.add_subplot(111, projection="3d")

    faces = mpl_toolkits.mplot3d.art3d.Poly3DCollection(
        edges, linewidths=1, edgecolors="k"
    )
    faces.set_facecolor((0, 0, 1, 0.1))

    ax.add_collection3d(faces)

    bounding_box = get_bounding_box(points_matplotlib_order)

    ax.set_xlim(bounding_box[1])
    ax.set_ylim(bounding_box[0])
    ax.set_zlim(bounding_box[2])

    #     ax.set_aspect('equal')
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_zlabel("z")
    ax.set_aspect("equal")

    return ax


def test_if_in_range(point_test, point_start, point_end):
    point_test = np.array(point_test)
    point_start = np.array(point_start)
    point_end = np.array(point_end)

    vector = point_end - point_start
    dot = np.dot(point_test, vector)
    item = [dot, np.dot(vector, point_start), np.dot(vector, point_end)]
    item.sort()

    return item[1] == dot


def test_if_in_cube(point_test, cube_definition):
    return (
        test_if_in_range(point_test, cube_definition[0], cube_definition[1])
        and test_if_in_range(point_test, cube_definition[0], cube_definition[2])
        and test_if_in_range(point_test, cube_definition[0], cube_definition[3])
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
        z_dose[np.invert(z_outside)],
    )

    where_x = np.where(np.invert(x_outside))[0]
    where_y = np.where(np.invert(y_outside))[0]
    where_z = np.where(np.invert(z_outside))[0]

    bounded_dose = dose[
        where_y[0] : where_y[-1] + 1,
        where_x[0] : where_x[-1] + 1,
        where_z[0] : where_z[-1] + 1,
    ]

    points_to_test = np.array(
        [
            [y, x, z, d]
            for y, x, z, d in zip(
                np.ravel(yy), np.ravel(xx), np.ravel(zz), np.ravel(bounded_dose)
            )
        ]
    )

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
        c=points_inside_cube[:, 3],
        alpha=0.4,
    )

    return ax


def get_interpolated_dose(coords_grid, dose_interpolation):
    coords_grid_ij_indexing = np.array(
        [
            np.ravel(coords_grid[:, :, 1]),
            np.ravel(coords_grid[:, :, 0]),
            np.ravel(coords_grid[:, :, 2]),
        ]
    ).T

    interpolated_dose = dose_interpolation(coords_grid_ij_indexing)
    coords_dim = np.shape(coords_grid)
    interpolated_dose = np.reshape(interpolated_dose, (coords_dim[0], coords_dim[1]))

    return interpolated_dose


def resample_contour(contour, n=51):
    tck, _ = splprep([contour[0], contour[1], contour[2]], s=0, k=1)
    new_points = splev(np.linspace(0, 1, n), tck)

    return new_points


def resample_contour_set(contours, n=50):
    resampled_contours = [resample_contour([x, y, z], n) for x, y, z in zip(*contours)]

    return resampled_contours


def contour_to_points(contours):
    resampled_contours = resample_contour_set([contours[1], contours[0], contours[2]])
    contour_points = np.concatenate(resampled_contours, axis=1)

    return contour_points


def get_structure_aligned_cube(
    structure_name: str,
    dcm_struct: pydicom.dataset.FileDataset,
    quiet=False,
    niter=10,
    x0=None,
):
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
    >>> import pymedphys
    >>> from pymedphys.labs.cube import get_structure_aligned_cube
    >>>
    >>> struct_path = str(pymedphys.data_path('example_structures.dcm'))
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
            np.concatenate(contour_coord) for contour_coord in contours
        ]

        bounds = [
            (np.min(concatenated_contour), np.max(concatenated_contour))
            for concatenated_contour in concatenated_contours
        ]

        x0 = np.array(
            [
                (bounds[1][0], bounds[0][0], bounds[2][1]),
                (bounds[1][0], bounds[0][1], bounds[2][1]),
                (bounds[1][1], bounds[0][0], bounds[2][1]),
            ]
        )

    if quiet:

        def print_fun(x, f, accepted):  # pylint: disable = unused-argument
            pass

    else:

        def print_fun(x, f, accepted):  # pylint: disable = unused-argument
            print("at minimum %.4f accepted %d" % (f, int(accepted)))

    result = basinhopping(to_minimise, x0, callback=print_fun, niter=niter, stepsize=5)

    cube = result.x

    cube_definition = cubify_cube_definition(
        [tuple(cube[0:3]), tuple(cube[3:6]), tuple(cube[6::])]
    )

    cube_definition_array = np.array([np.array(list(item)) for item in cube_definition])

    vectors = [
        cube_definition_array[1] - cube_definition_array[0],
        cube_definition_array[2] - cube_definition_array[0],
        cube_definition_array[3] - cube_definition_array[0],
    ]

    return cube_definition_array, vectors


def calc_min_distance(cube_definition, contours):
    vertices = cube_vertices(cube_definition)

    vectors = cube_vectors(cube_definition)
    unit_vectors = [vector / np.linalg.norm(vector) for vector in vectors]

    plane_norms = np.array(
        [
            unit_vectors[1],
            -unit_vectors[0],
            -unit_vectors[1],
            unit_vectors[0],
            unit_vectors[2],
            -unit_vectors[2],
        ]
    )

    plane_points = np.array(
        [vertices[0], vertices[1], vertices[2], vertices[0], vertices[0], vertices[3]]
    )

    plane_origin_dist = -np.sum(plane_points * plane_norms, axis=1)

    distance_to_planes = np.dot(plane_norms, contours) + plane_origin_dist[:, None]

    min_dist_squared = np.min(distance_to_planes ** 2, axis=0)

    return min_dist_squared
