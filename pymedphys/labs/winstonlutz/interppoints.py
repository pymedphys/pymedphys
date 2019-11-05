# Copyright (C) 2019 Cancer Care Associates

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

import matplotlib.transforms

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
    xx_flat = np.ravel(xx)
    transformed = transform @ np.vstack([xx_flat, np.ravel(yy), np.ones_like(xx_flat)])

    xx_transformed = transformed[0]
    yy_transformed = transformed[1]

    xx_transformed.shape = xx.shape
    yy_transformed.shape = yy.shape

    return xx_transformed, yy_transformed


def create_bb_points_function(bb_diameter):
    min_dist = 0.5
    distances = np.arange(0, bb_diameter * 0.8, min_dist)

    x = []
    y = []
    dist = []

    for _, distance in enumerate(distances):
        (
            new_x,
            new_y,
        ) = pymedphys._utilities.createshells.calculate_coordinates_shell_2d(  # pylint: disable = protected-access
            distance, min_dist
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
