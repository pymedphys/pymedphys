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
from pymedphys.coordinates import translate, rotate_about_z


def get_single_and_multi_test_coords():

    x_single = 1
    y_single = 2
    z_single = 3
    test_single_coords = np.array((x_single, y_single, z_single))

    number_of_coordinates = 11
    x_multi = np.array(range(-1, number_of_coordinates-1, 1))
    y_multi = np.array(range(-2, 2*(number_of_coordinates-1), 2))
    z_multi = np.array(range(-3, 3*(number_of_coordinates-1), 3))
    test_multi_coords = np.array((x_multi, y_multi, z_multi))

    return test_single_coords, test_multi_coords


def test_translate():

    test_single_coords, test_multi_coords = get_single_and_multi_test_coords()

    assert np.allclose(translate(test_single_coords, np.array((10, 20, 30))),
                       np.array((11, 22, 33)))
    assert np.allclose(translate(test_single_coords, np.array((-1, -2, -3))),
                       np.array((0, 0, 0)))

    assert np.allclose(translate(test_multi_coords, np.array((1, 1, 1))),
                       test_multi_coords + 1)

def test_rotate_about_z():

    test_single_coords, test_multi_coords = get_single_and_multi_test_coords()

    x_s = test_single_coords[0]
    y_s = test_single_coords[1]
    z_s = test_single_coords[2]
    x_m = test_multi_coords[0]
    y_m = test_multi_coords[1]
    z_m = test_multi_coords[2]

    assert np.allclose(rotate_about_z(test_single_coords, 90),
                       np.array((y_s, np.negative(x_s), z_s)))
    assert np.allclose(rotate_about_z(test_single_coords, 180),
                       np.array((np.negative(x_s), np.negative(y_s), z_s)))
    assert np.allclose(rotate_about_z(test_single_coords, 270),
                       np.array((np.negative(y_s), x_s, z_s)))

    assert np.allclose(rotate_about_z(test_multi_coords, 90),
                       np.array((y_m, np.negative(x_m), z_m)))
    assert np.allclose(rotate_about_z(test_multi_coords, 180),
                       np.array((np.negative(x_m), np.negative(y_m), z_m)))
    assert np.allclose(rotate_about_z(test_multi_coords, 270),
                       np.array((np.negative(y_m), x_m, z_m)))
