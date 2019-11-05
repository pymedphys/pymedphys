# Copyright (C) 2015-2018 Simon Biggs
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


def calculate_coordinates_shell(distance, num_dimensions, distance_step_size):
    """Create the shell of coordinate shifts for the given testing distance.

    Coordinate shifts are determined to check the evaluation dose for a
    given distance, dimension, and step size
    """
    if num_dimensions == 1:
        return calculate_coordinates_shell_1d(distance)

    if num_dimensions == 2:
        return calculate_coordinates_shell_2d(distance, distance_step_size)

    if num_dimensions == 3:
        return calculate_coordinates_shell_3d(distance, distance_step_size)

    raise Exception("No valid dimension")


def calculate_coordinates_shell_1d(distance):
    """Output the two points that are of the defined distance in one-dimension
    """
    if distance == 0:
        x_coords = np.array([0])
    else:
        x_coords = np.array([distance, -distance])

    return (x_coords,)


def calculate_coordinates_shell_2d(distance, distance_step_size):
    """Create points along the circumference of a circle. The spacing
    between points is not larger than the defined distance_step_size
    """
    amount_to_check = np.ceil(2 * np.pi * distance / distance_step_size).astype(int) + 1
    theta = np.linspace(0, 2 * np.pi, amount_to_check + 1)[:-1:]
    x_coords = distance * np.cos(theta)
    y_coords = distance * np.sin(theta)

    return (x_coords, y_coords)


def calculate_coordinates_shell_3d(distance, distance_step_size):
    """Create points along the surface of a sphere (a shell) where no gap
    between points is larger than the defined distance_step_size"""

    number_of_rows = np.ceil(np.pi * distance / distance_step_size).astype(int) + 1

    elevation = np.linspace(0, np.pi, number_of_rows)
    row_radii = distance * np.sin(elevation)
    row_circumference = 2 * np.pi * row_radii
    amount_in_row = np.ceil(row_circumference / distance_step_size).astype(int) + 1

    x_coords = []
    y_coords = []
    z_coords = []
    for i, phi in enumerate(elevation):
        azimuth = np.linspace(0, 2 * np.pi, amount_in_row[i] + 1)[:-1:]
        x_coords.append(distance * np.sin(phi) * np.cos(azimuth))
        y_coords.append(distance * np.sin(phi) * np.sin(azimuth))
        z_coords.append(distance * np.cos(phi) * np.ones_like(azimuth))

    return (np.hstack(x_coords), np.hstack(y_coords), np.hstack(z_coords))
