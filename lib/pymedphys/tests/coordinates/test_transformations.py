# Copyright (C) 2019 Matthew Jennings
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pymedphys._imports import numpy as np

from pymedphys._utilities.transforms.affine import (
    rotate_about_vector,
    rotate_about_x,
    rotate_about_y,
    rotate_about_z,
    translate,
)


def get_single_and_multi_test_coords():

    x_single = 1
    y_single = 2
    z_single = 3
    test_coords_single = np.array((x_single, y_single, z_single))

    number_of_coordinates = 11
    x_multi = np.array(range(-1, number_of_coordinates - 1, 1))
    y_multi = np.array(range(-2, 2 * (number_of_coordinates - 1), 2))
    z_multi = np.array(range(-3, 3 * (number_of_coordinates - 1), 3))
    test_coords_multi = np.array((x_multi, y_multi, z_multi))

    return test_coords_single, test_coords_multi


def test_rotate_about_vector():

    test_coords_single, test_coords_multi = get_single_and_multi_test_coords()

    rotation_vector = np.array((2, 2, 2))

    # Rotation of coords about own axis yields no change
    assert np.allclose(
        rotate_about_vector(np.array((1, 1, 1)), rotation_vector, 52),
        np.array((1, 1, 1)),
    )
    assert np.allclose(
        rotate_about_vector(np.array((1, 1, 1)), rotation_vector, 52, active=True),
        np.array((1, 1, 1)),
    )

    # Rotation of coords about each cardinal axis yields same result as axis rotation functions
    # Singles
    assert np.allclose(
        rotate_about_vector(test_coords_single, np.array((1, 0, 0)), 27),
        rotate_about_x(test_coords_single, 27),
    )
    assert np.allclose(
        rotate_about_vector(test_coords_single, np.array((1, 0, 0)), 27, active=True),
        rotate_about_x(test_coords_single, 27, active=True),
    )
    assert np.allclose(
        rotate_about_vector(test_coords_single, np.array((0, 1, 0)), 256),
        rotate_about_y(test_coords_single, 256),
    )
    assert np.allclose(
        rotate_about_vector(test_coords_single, np.array((0, 1, 0)), 256, active=True),
        rotate_about_y(test_coords_single, 256, active=True),
    )
    assert np.allclose(
        rotate_about_vector(test_coords_single, np.array((0, 0, 1)), 182),
        rotate_about_z(test_coords_single, 182),
    )
    assert np.allclose(
        rotate_about_vector(test_coords_single, np.array((0, 0, 1)), 182, active=True),
        rotate_about_z(test_coords_single, 182, active=True),
    )
    # Multis
    assert np.allclose(
        rotate_about_vector(test_coords_multi, np.array((1, 0, 0)), 27),
        rotate_about_x(test_coords_multi, 27),
    )
    assert np.allclose(
        rotate_about_vector(test_coords_multi, np.array((1, 0, 0)), 27, active=True),
        rotate_about_x(test_coords_multi, 27, active=True),
    )
    assert np.allclose(
        rotate_about_vector(test_coords_multi, np.array((0, 1, 0)), 256),
        rotate_about_y(test_coords_multi, 256),
    )
    assert np.allclose(
        rotate_about_vector(test_coords_multi, np.array((0, 1, 0)), 256, active=True),
        rotate_about_y(test_coords_multi, 256, active=True),
    )
    assert np.allclose(
        rotate_about_vector(test_coords_multi, np.array((0, 0, 1)), 182),
        rotate_about_z(test_coords_multi, 182),
    )
    assert np.allclose(
        rotate_about_vector(test_coords_multi, np.array((0, 0, 1)), 182, active=True),
        rotate_about_z(test_coords_multi, 182, active=True),
    )

    # Random test case verified against: http://www.nh.cas.cz/people/lazar/celler/online_tools.php
    assert np.allclose(
        rotate_about_vector(np.array((13, 29, -17)), np.array((41, -97, 61)), 197),
        np.array((-30.683355, 18.344803, -4.582567)),
    )
    assert np.allclose(
        rotate_about_vector(
            np.array((13, 29, -17)), np.array((41, -97, 61)), 197, active=True
        ),
        np.array((-30.106782, 11.185686, -16.354268)),
    )


def test_rotate_about_x():

    test_coords_single, test_coords_multi = get_single_and_multi_test_coords()

    x_s = test_coords_single[0]
    y_s = test_coords_single[1]
    z_s = test_coords_single[2]
    x_m = test_coords_multi[0]
    y_m = test_coords_multi[1]
    z_m = test_coords_multi[2]

    # Passive rotations
    assert np.allclose(
        rotate_about_x(test_coords_single, 90), np.array((x_s, z_s, np.negative(y_s)))
    )
    assert np.allclose(
        rotate_about_x(test_coords_single, 180),
        np.array((x_s, np.negative(y_s), np.negative(z_s))),
    )
    assert np.allclose(
        rotate_about_x(test_coords_single, 270), np.array((x_s, np.negative(z_s), y_s))
    )

    assert np.allclose(
        rotate_about_x(test_coords_multi, 90), np.array((x_m, z_m, np.negative(y_m)))
    )
    assert np.allclose(
        rotate_about_x(test_coords_multi, 180),
        np.array((x_m, np.negative(y_m), np.negative(z_m))),
    )
    assert np.allclose(
        rotate_about_x(test_coords_multi, 270), np.array((x_m, np.negative(z_m), y_m))
    )

    # Active rotations
    assert np.allclose(
        rotate_about_x(test_coords_single, 90, active=True),
        np.array((x_s, np.negative(z_s), y_s)),
    )
    assert np.allclose(
        rotate_about_x(test_coords_single, 180, active=True),
        np.array((x_s, np.negative(y_s), np.negative(z_s))),
    )
    assert np.allclose(
        rotate_about_x(test_coords_single, 270, active=True),
        np.array((x_s, z_s, np.negative(y_s))),
    )

    assert np.allclose(
        rotate_about_x(test_coords_multi, 90, active=True),
        np.array((x_m, np.negative(z_m), y_m)),
    )
    assert np.allclose(
        rotate_about_x(test_coords_multi, 180, active=True),
        np.array((x_m, np.negative(y_m), np.negative(z_m))),
    )
    assert np.allclose(
        rotate_about_x(test_coords_multi, 270, active=True),
        np.array((x_m, z_m, np.negative(y_m))),
    )


def test_rotate_about_y():

    test_coords_single, test_coords_multi = get_single_and_multi_test_coords()
    x_s = test_coords_single[0]
    y_s = test_coords_single[1]
    z_s = test_coords_single[2]
    x_m = test_coords_multi[0]
    y_m = test_coords_multi[1]
    z_m = test_coords_multi[2]

    # Passive
    assert np.allclose(
        rotate_about_y(test_coords_single, 90), np.array((np.negative(z_s), y_s, x_s))
    )
    assert np.allclose(
        rotate_about_y(test_coords_single, 180),
        np.array((np.negative(x_s), y_s, np.negative(z_s))),
    )
    assert np.allclose(
        rotate_about_y(test_coords_single, 270), np.array((z_s, y_s, np.negative(x_s)))
    )

    assert np.allclose(
        rotate_about_y(test_coords_multi, 90), np.array((np.negative(z_m), y_m, x_m))
    )
    assert np.allclose(
        rotate_about_y(test_coords_multi, 180),
        np.array((np.negative(x_m), y_m, np.negative(z_m))),
    )
    assert np.allclose(
        rotate_about_y(test_coords_multi, 270), np.array((z_m, y_m, np.negative(x_m)))
    )

    # Active
    assert np.allclose(
        rotate_about_y(test_coords_single, 90, active=True),
        np.array((z_s, y_s, np.negative(x_s))),
    )
    assert np.allclose(
        rotate_about_y(test_coords_single, 180, active=True),
        np.array((np.negative(x_s), y_s, np.negative(z_s))),
    )
    assert np.allclose(
        rotate_about_y(test_coords_single, 270, active=True),
        np.array((np.negative(z_s), y_s, x_s)),
    )

    assert np.allclose(
        rotate_about_y(test_coords_multi, 90, active=True),
        np.array((z_m, y_m, np.negative(x_m))),
    )
    assert np.allclose(
        rotate_about_y(test_coords_multi, 180, active=True),
        np.array((np.negative(x_m), y_m, np.negative(z_m))),
    )
    assert np.allclose(
        rotate_about_y(test_coords_multi, 270, active=True),
        np.array((np.negative(z_m), y_m, x_m)),
    )


def test_rotate_about_z():

    test_coords_single, test_coords_multi = get_single_and_multi_test_coords()

    x_s = test_coords_single[0]
    y_s = test_coords_single[1]
    z_s = test_coords_single[2]
    x_m = test_coords_multi[0]
    y_m = test_coords_multi[1]
    z_m = test_coords_multi[2]

    # Passive
    assert np.allclose(
        rotate_about_z(test_coords_single, 90), np.array((y_s, np.negative(x_s), z_s))
    )
    assert np.allclose(
        rotate_about_z(test_coords_single, 180),
        np.array((np.negative(x_s), np.negative(y_s), z_s)),
    )
    assert np.allclose(
        rotate_about_z(test_coords_single, 270), np.array((np.negative(y_s), x_s, z_s))
    )

    assert np.allclose(
        rotate_about_z(test_coords_multi, 90), np.array((y_m, np.negative(x_m), z_m))
    )
    assert np.allclose(
        rotate_about_z(test_coords_multi, 180),
        np.array((np.negative(x_m), np.negative(y_m), z_m)),
    )
    assert np.allclose(
        rotate_about_z(test_coords_multi, 270), np.array((np.negative(y_m), x_m, z_m))
    )

    # Active
    assert np.allclose(
        rotate_about_z(test_coords_single, 90, active=True),
        np.array((np.negative(y_s), x_s, z_s)),
    )
    assert np.allclose(
        rotate_about_z(test_coords_single, 180, active=True),
        np.array((np.negative(x_s), np.negative(y_s), z_s)),
    )
    assert np.allclose(
        rotate_about_z(test_coords_single, 270, active=True),
        np.array((y_s, np.negative(x_s), z_s)),
    )

    assert np.allclose(
        rotate_about_z(test_coords_multi, 90, active=True),
        np.array((np.negative(y_m), x_m, z_m)),
    )
    assert np.allclose(
        rotate_about_z(test_coords_multi, 180, active=True),
        np.array((np.negative(x_m), np.negative(y_m), z_m)),
    )
    assert np.allclose(
        rotate_about_z(test_coords_multi, 270, active=True),
        np.array((y_m, np.negative(x_m), z_m)),
    )


def test_translate():

    test_coords_single, test_coords_multi = get_single_and_multi_test_coords()

    assert np.allclose(
        translate(test_coords_single, np.array((10, 20, 30))), np.array((-9, -18, -27))
    )
    assert np.allclose(
        translate(test_coords_single, test_coords_single), np.array((0, 0, 0))
    )
    assert np.allclose(
        translate(test_coords_multi, np.array((1, 1, 1))), test_coords_multi - 1
    )

    assert np.allclose(
        translate(test_coords_single, np.array((10, 20, 30)), active=True),
        np.array((11, 22, 33)),
    )
    assert np.allclose(
        translate(test_coords_single, np.array((-1, -2, -3)), active=True),
        np.array((0, 0, 0)),
    )
    assert np.allclose(
        translate(test_coords_multi, np.array((1, 1, 1)), active=True),
        test_coords_multi + 1,
    )
