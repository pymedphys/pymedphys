# Copyright (C) 2019 Matthew Jennings
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
from math import sin, cos
from pymedphys.coordinates import translate, rotate_about_z


def test_translate():
    test_vector = np.array((1, 2, 3, 1))

    assert np.allclose(translate(np.array((1, 2, 3))) @ test_vector,
                       np.array((2, 4, 6, 1)))
    assert np.allclose(translate(np.array((-1, -2, -3))) @ test_vector,
                       np.array((0, 0, 0, 1)))


def test_rotate_about_z():
    number_of_coordinates = 11
    x = np.array(range(-1, number_of_coordinates-1, 1))
    y = np.array(range(-2, 2*(number_of_coordinates-1), 2))
    z = np.array(range(-3, 3*(number_of_coordinates-1), 3))
    extra = np.ones(number_of_coordinates)
    coords = np.array((x, y, z, extra))

    coords = np.array((x, y, z, extra))

    coords_rotated_90_about_z = rotate_about_z(90) @ coords
    expected_coords_rotated_90_about_z = np.array((y, np.negative(x), z, extra))

    coords_rotated_180_about_z = rotate_about_z(180) @ coords
    expected_coords_rotated_180_about_z = np.array((np.negative(x), np.negative(y), z, extra))

    coords_rotated_270_about_z = rotate_about_z(270) @ coords
    expected_coords_rotated_270_about_z = np.array((np.negative(y), x, z, extra))

    assert np.allclose(coords_rotated_90_about_z, expected_coords_rotated_90_about_z)
    assert np.allclose(coords_rotated_180_about_z, expected_coords_rotated_180_about_z)
    assert np.allclose(coords_rotated_270_about_z, expected_coords_rotated_270_about_z)
