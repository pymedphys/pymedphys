# Copyright (C) 2015 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Model insert factors and parameterise inserts as equivalent ellipses."""


from pymedphys._imports import numpy as np
from pymedphys._imports import scipy, shapely


def spline_model(
    width_test, ratio_perim_area_test, width_data, ratio_perim_area_data, factor_data
):
    """Return the result of the spline model.

    The bounding box is chosen so as to allow extrapolation. The spline orders
    are two in the width direction and one in the perimeter/area direction. For
    justification on using this method for modelling electron insert factors
    see the *Methods: Bivariate spline model* section within
    <http://dx.doi.org/10.1016/j.ejmp.2015.11.002>.

    Parameters
    ----------
    width_test : np.ndarray
        The width point(s) which are to have the electron insert factor
        interpolated.
    ratio_perim_area_test : np.ndarray
        The perimeter/area which are to have the electron insert factor
        interpolated.

    width_data : np.ndarray
        The width data points for the relevant applicator, energy and ssd.
    ratio_perim_area_data : np.ndarray
        The perimeter/area data points for the relevant applicator, energy and
        ssd.
    factor_data : np.ndarray
        The insert factor data points for the relevant applicator, energy and
        ssd.

    Returns
    -------
    result : np.ndarray
        The interpolated electron insert factors for width_test and
        ratio_perim_area_test.

    """
    bbox = [
        np.min([np.min(width_data), np.min(width_test)]),
        np.max([np.max(width_data), np.max(width_test)]),
        np.min([np.min(ratio_perim_area_data), np.min(ratio_perim_area_test)]),
        np.max([np.max(ratio_perim_area_data), np.max(ratio_perim_area_test)]),
    ]

    spline = scipy.interpolate.SmoothBivariateSpline(
        width_data, ratio_perim_area_data, factor_data, kx=2, ky=1, bbox=bbox
    )

    return spline.ev(width_test, ratio_perim_area_test)


def _single_calculate_deformability(x_test, y_test, x_data, y_data, z_data):
    """Return the result of the deformability test for a single test point.

    The deformability test applies a shift to the spline to determine whether
    or not sufficient information for modelling is available. For further
    details on the deformability test see the *Methods: Defining valid
    prediction regions of the spline* section within
    <http://dx.doi.org/10.1016/j.ejmp.2015.11.002>.

    Parameters
    ----------
    x_test : float
        The x coordinate of the point to test
    y_test : float
        The y coordinate of the point to test
    x_data : np.ndarray
        The x coordinates of the model data to test
    y_data : np.ndarray
        The y coordinates of the model data to test
    z_data : np.ndarray
        The z coordinates of the model data to test

    Returns
    -------
    deformability : float
        The resulting deformability between 0 and 1
        representing the ratio of deviation the spline model underwent at
        the point in question by introducing an outlier at the point in
        question.

    """
    deviation = 0.02

    adjusted_x_data = np.append(x_data, x_test)
    adjusted_y_data = np.append(y_data, y_test)

    bbox = [
        min(adjusted_x_data),
        max(adjusted_x_data),
        min(adjusted_y_data),
        max(adjusted_y_data),
    ]

    initial_model = scipy.interpolate.SmoothBivariateSpline(
        x_data, y_data, z_data, bbox=bbox, kx=2, ky=1
    ).ev(x_test, y_test)

    pos_adjusted_z_data = np.append(z_data, initial_model + deviation)
    neg_adjusted_z_data = np.append(z_data, initial_model - deviation)

    pos_adjusted_model = scipy.interpolate.SmoothBivariateSpline(
        adjusted_x_data, adjusted_y_data, pos_adjusted_z_data, kx=2, ky=1
    ).ev(x_test, y_test)
    neg_adjusted_model = scipy.interpolate.SmoothBivariateSpline(
        adjusted_x_data, adjusted_y_data, neg_adjusted_z_data, kx=2, ky=1
    ).ev(x_test, y_test)

    deformability_from_pos_adjustment = (pos_adjusted_model - initial_model) / deviation
    deformability_from_neg_adjustment = (initial_model - neg_adjusted_model) / deviation

    deformability = np.max(
        [deformability_from_pos_adjustment, deformability_from_neg_adjustment]
    )

    return deformability


def calculate_deformability(x_test, y_test, x_data, y_data, z_data):
    """Return the result of the deformability test.

    This function takes an array of test points and loops over
    ``_single_calculate_deformability``.

    The deformability test applies a shift to the spline to determine whether
    or not sufficient information for modelling is available. For further
    details on the deformability test see the *Methods: Defining valid
    prediction regions of the spline* section within
    <http://dx.doi.org/10.1016/j.ejmp.2015.11.002>.

    Parameters
    ----------
    x_test : np.ndarray
        The x coordinate of the point(s) to test
    y_test : np.ndarray
        The y coordinate of the point(s) to test
    x_data : np.ndarray
        The x coordinate of the model data to test
    y_data : np.ndarray
        The y coordinate of the model data to test
    z_data : np.ndarray
        The z coordinate of the model data to test

    Returns
    -------
    deformability : float
        The resulting deformability between 0 and 1
        representing the ratio of deviation the spline model underwent at
        the point in question by introducing an outlier at the point in
        question.

    """
    dim = np.shape(x_test)

    if np.size(dim) == 0:
        deformability = _single_calculate_deformability(
            x_test, y_test, x_data, y_data, z_data
        )

    elif np.size(dim) == 1:
        deformability = np.array(
            [
                _single_calculate_deformability(
                    x_test[i], y_test[i], x_data, y_data, z_data
                )
                for i in range(dim[0])
            ]
        )

    else:
        deformability = np.array(
            [
                [
                    _single_calculate_deformability(
                        x_test[i, j], y_test[i, j], x_data, y_data, z_data
                    )
                    for j in range(dim[1])
                ]
                for i in range(dim[0])
            ]
        )

    return deformability


def spline_model_with_deformability(
    width_test, ratio_perim_area_test, width_data, ratio_perim_area_data, factor_data
):
    """Return the spline model for points with sufficient deformability.

    Calls both ``spline_model`` and ``calculate_deformability`` and then adjusts
    the result so that points with  deformability greater than 0.5 return
    ``np.nan``.

    Parameters
    ----------
    width_test : np.ndarray
        The width point(s) which are to have the
        electron insert factor interpolated.
    ratio_perim_area_test : np.ndarray
        The perimeter/area which are to
        have the electron insert factor interpolated.

    width_data : np.ndarray
        The width data points for the relevant
        applicator, energy and ssd.
    ratio_perim_area_data : np.ndarray
        The perimeter/area data points for
        the relevant applicator, energy and ssd.
    factor_data : np.ndarray
        The insert factor data points for the
        relevant applicator, energy and ssd.

    Returns
    -------
    model_factor : np.ndarray
        The interpolated electron insert factors for width_test
        and ratio_perim_area_test with points outside the valid prediction
        region set to ``np.nan``.

    """
    deformability = calculate_deformability(
        width_test,
        ratio_perim_area_test,
        width_data,
        ratio_perim_area_data,
        factor_data,
    )

    model_factor = spline_model(
        width_test,
        ratio_perim_area_test,
        width_data,
        ratio_perim_area_data,
        factor_data,
    )

    model_factor[deformability > 0.5] = np.nan

    return model_factor


def calculate_percent_prediction_differences(
    width_data, ratio_perim_area_data, factor_data
):
    """Return the percent prediction differences.

    Calculates the model factor for each data point with that point removed
    from the data set. Used to determine an estimated uncertainty for
    prediction.

    Parameters
    ----------
    width_data : np.ndarray
        The width data points for a specific
        applicator, energy and ssd.
    ratio_perim_area_data : np.ndarray
        The perimeter/area data points for
        a specific applicator, energy and ssd.
    factor_data : np.ndarray
        The insert factor data points for a specific
        applicator, energy and ssd.

    Returns
    -------
    percent_prediction_differences : np.ndarray
        The predicted electron insert factors for each data point
        with that given data point removed.

    """
    predictions = [
        spline_model_with_deformability(
            width_data[i],
            ratio_perim_area_data[i],
            np.delete(width_data, i),
            np.delete(ratio_perim_area_data, i),
            np.delete(factor_data, i),
        )
        for i in range(len(width_data))
    ]

    percent_prediction_differences = 100 * (factor_data - predictions) / factor_data

    return percent_prediction_differences


def shapely_insert(x, y):
    """Return a shapely object from x and y coordinates."""
    return shapely.geometry.Polygon(np.transpose((x, y)))


def search_for_centre_of_largest_bounded_circle(x, y, callback=None):
    """Find the centre of the largest bounded circle within the insert."""
    insert = shapely_insert(x, y)
    boundary = insert.boundary
    centroid = insert.centroid

    furthest_distance = np.hypot(
        np.diff(insert.bounds[::2]), np.diff(insert.bounds[1::2])
    )

    def minimising_function(optimiser_input):
        x, y = optimiser_input
        point = shapely.geometry.Point(x, y)

        if insert.contains(point):
            edge_distance = point.distance(boundary)
        else:
            edge_distance = -point.distance(boundary)

        return -edge_distance

    x0 = np.squeeze(centroid.coords)
    niter = 200
    T = furthest_distance / 3
    stepsize = furthest_distance / 2
    niter_success = 50
    output = scipy.optimize.basinhopping(
        minimising_function,
        x0,
        niter=niter,
        T=T,
        stepsize=stepsize,
        niter_success=niter_success,
        callback=callback,
    )

    circle_centre = output.x

    return circle_centre


def calculate_width(x, y, circle_centre):
    """Return the equivalent ellipse width."""
    insert = shapely_insert(x, y)
    point = shapely.geometry.Point(*circle_centre)

    if insert.contains(point):
        distance = point.distance(insert.boundary)
    else:
        raise Exception("Circle centre not within insert")

    return distance * 2


def calculate_length(x, y, width):
    """Return the equivalent ellipse length."""
    insert = shapely_insert(x, y)
    length = 4 * insert.area / (np.pi * width)

    return length


def parameterise_insert(x, y, callback=None):
    """Return the parameterisation of an insert given x and y coords."""
    circle_centre = search_for_centre_of_largest_bounded_circle(x, y, callback=callback)
    width = calculate_width(x, y, circle_centre)
    length = calculate_length(x, y, width)

    return width, length, circle_centre


def visual_alignment_of_equivalent_ellipse(x, y, width, length, callback):
    """Visually align the equivalent ellipse to the insert."""
    insert = shapely_insert(x, y)
    unit_circle = shapely.geometry.Point(0, 0).buffer(1)
    initial_ellipse = shapely.affinity.scale(
        unit_circle, xfact=width / 2, yfact=length / 2
    )

    def minimising_function(optimiser_input):
        x_shift, y_shift, rotation_angle = optimiser_input
        rotated = shapely.affinity.rotate(
            initial_ellipse, rotation_angle, use_radians=True
        )
        translated = shapely.affinity.translate(rotated, xoff=x_shift, yoff=y_shift)

        disjoint_area = (
            translated.difference(insert).area + insert.difference(translated).area
        )

        return disjoint_area / 400

    x0 = np.append(np.squeeze(insert.centroid.coords), np.pi / 4)
    niter = 10
    T = insert.area / 40000
    stepsize = 3
    niter_success = 2
    output = scipy.optimize.basinhopping(
        minimising_function,
        x0,
        niter=niter,
        T=T,
        stepsize=stepsize,
        niter_success=niter_success,
        callback=callback,
    )

    x_shift, y_shift, rotation_angle = output.x

    return x_shift, y_shift, rotation_angle


def parameterise_insert_with_visual_alignment(
    x,
    y,
    circle_callback=None,
    visual_ellipse_callback=None,
    complete_parameterisation_callback=None,
):
    """Return an equivalent ellipse with visual alignment parameters."""
    width, length, circle_centre = parameterise_insert(x, y, callback=circle_callback)
    if complete_parameterisation_callback is not None:
        complete_parameterisation_callback(width, length, circle_centre)
    x_shift, y_shift, rotation_angle = visual_alignment_of_equivalent_ellipse(
        x, y, width, length, callback=visual_ellipse_callback
    )

    return width, length, circle_centre, x_shift, y_shift, rotation_angle


def convert2_ratio_perim_area(width, length):
    """Convert width and length data into ratio of perimeter to area."""
    perimeter = (
        np.pi
        / 2
        * (3 * (width + length) - np.sqrt((3 * width + length) * (3 * length + width)))
    )
    area = np.pi / 4 * width * length

    return perimeter / area


def create_transformed_mesh(width_data, length_data, factor_data):
    """Return factor data meshgrid."""
    x = np.arange(
        np.floor(np.min(width_data)) - 1, np.ceil(np.max(width_data)) + 1, 0.1
    )
    y = np.arange(
        np.floor(np.min(length_data)) - 1, np.ceil(np.max(length_data)) + 1, 0.1
    )

    xx, yy = np.meshgrid(x, y)

    zz = spline_model_with_deformability(
        xx,
        convert2_ratio_perim_area(xx, yy),
        width_data,
        convert2_ratio_perim_area(width_data, length_data),
        factor_data,
    )

    zz[xx > yy] = np.nan

    no_data_x = np.all(np.isnan(zz), axis=0)
    no_data_y = np.all(np.isnan(zz), axis=1)

    x = x[np.invert(no_data_x)]
    y = y[np.invert(no_data_y)]

    zz = zz[np.invert(no_data_y), :]
    zz = zz[:, np.invert(no_data_x)]

    return x, y, zz
