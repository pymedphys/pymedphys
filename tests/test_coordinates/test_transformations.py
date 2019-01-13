import numpy as np
from math import sin, cos
from pymedphys.coordinates import rotate_about_z


def test_rotate_about_z():
    x = np.array(range(-1, 10, 1))
    y = np.array(range(-2, 20, 2))
    z = np.array(range(-3, 30, 3))
    extra = np.zeros(11)

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
