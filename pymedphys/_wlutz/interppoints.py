# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import matplotlib
from pymedphys._imports import numpy as np

import pymedphys._utilities.createshells


def transform_penumbra_points(points_at_origin, centre, rotation):
    transform = translate_and_rotate_transform(centre, rotation)

    xx_left_right, yy_left_right, xx_top_bot, yy_top_bot = points_at_origin

    xx_left_right_transformed, yy_left_right_transformed = apply_transform(
        xx_left_right, yy_left_right, transform
    )
    xx_top_bot_transformed, yy_top_bot_transformed = apply_transform(
        xx_top_bot, yy_top_bot, transform
    )

    return (
        xx_left_right_transformed,
        yy_left_right_transformed,
        xx_top_bot_transformed,
        yy_top_bot_transformed,
    )


def translate_and_rotate_transform(centre, rotation):
    transform = matplotlib.transforms.Affine2D()
    try:
        transform.rotate_deg(-rotation)
        transform.translate(*centre)
    except ValueError:
        print(centre, rotation)
        raise

    return transform


def define_penumbra_points_at_origin(edge_lengths, penumbra):
    penumbra_range = np.linspace(-penumbra / 2, penumbra / 2, 11)

    def _each_edge(current_edge_length, orthogonal_edge_length):
        half_field_range = np.linspace(
            -orthogonal_edge_length / 4, orthogonal_edge_length / 4, 51
        )

        a_side_lookup = -current_edge_length / 2 + penumbra_range
        b_side_lookup = current_edge_length / 2 + penumbra_range
        current_axis_lookup = np.concatenate([a_side_lookup, b_side_lookup])

        return current_axis_lookup, half_field_range

    edge_points_left_right = _each_edge(edge_lengths[0], edge_lengths[1])
    edge_points_top_bot = _each_edge(edge_lengths[1], edge_lengths[0])

    xx_left_right, yy_left_right = np.meshgrid(*edge_points_left_right)
    xx_top_bot, yy_top_bot = np.meshgrid(*edge_points_top_bot[::-1])

    return xx_left_right, yy_left_right, xx_top_bot, yy_top_bot


def transform_rotation_field_points(points_at_origin, centre, rotation):
    transform = translate_and_rotate_transform(centre, rotation)

    xx_flat, yy_flat = points_at_origin
    tranformed_xx, transformed_yy = apply_transform(xx_flat, yy_flat, transform)

    return tranformed_xx, transformed_yy


def define_rotation_field_points_at_origin(edge_lengths, penumbra):
    x_half_range = edge_lengths[0] / 2 + penumbra / 2
    y_half_range = edge_lengths[1] / 2 + penumbra / 2

    num_x = np.ceil(x_half_range * 2 * 8) + 1
    num_y = np.ceil(y_half_range * 2 * 8) + 1

    x = np.linspace(-x_half_range, x_half_range, int(num_x))
    y = np.linspace(-y_half_range, y_half_range, int(num_y))

    xx, yy = np.meshgrid(x, y)
    xx_flat = np.ravel(xx)
    yy_flat = np.ravel(yy)

    inside = np.logical_and(
        (np.abs(xx_flat) < x_half_range), (np.abs(yy_flat) < y_half_range)
    )

    xx_flat = xx_flat[np.invert(inside)]
    yy_flat = yy_flat[np.invert(inside)]

    return xx_flat, yy_flat


def apply_transform(xx, yy, transform):
    xx = np.array(xx, copy=False)
    yy = np.array(yy, copy=False)

    xx_flat = np.ravel(xx)
    transformed = transform @ np.vstack([xx_flat, np.ravel(yy), np.ones_like(xx_flat)])

    xx_transformed = transformed[0]
    yy_transformed = transformed[1]

    xx_transformed.shape = xx.shape
    yy_transformed.shape = yy.shape

    return xx_transformed, yy_transformed


def create_bb_points_function(bb_diameter):
    max_distance = bb_diameter * 0.5
    min_distance = 0
    num_steps = 11
    min_dist_between_points = (max_distance - min_distance) / num_steps
    distances = np.arange(
        min_distance, max_distance + min_dist_between_points, min_dist_between_points
    )

    x = []
    y = []
    dist = []

    for _, distance in enumerate(distances):
        (
            new_x,
            new_y,
        ) = pymedphys._utilities.createshells.calculate_coordinates_shell_2d(  # pylint: disable = protected-access
            distance, min_dist_between_points
        )
        x.append(new_x)
        y.append(new_y)
        dist.append(distance * np.ones_like(new_x))

    x = np.concatenate(x)
    y = np.concatenate(y)
    dist = np.concatenate(dist)

    def points_to_check(bb_centre):
        x_shifted = x + bb_centre[0]
        y_shifted = y + bb_centre[1]

        return x_shifted, y_shifted

    return points_to_check, dist


def create_centralised_field(field, centre, rotation):
    transform = translate_and_rotate_transform(centre, rotation)

    def new_field(x, y):
        x_prime, y_prime = apply_transform(x, y, transform)
        return field(x_prime, y_prime)

    return new_field
