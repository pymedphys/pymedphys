import os
from glob import glob

import imageio

import numpy as np
import matplotlib.pyplot as plt

from scipy.interpolate import RectBivariateSpline
from scipy.special import erf, erfinv
from scipy.optimize import basinhopping


# Copied from https://github.com/pymedphys/pymedphys/blob/07f451894eed84ae77ffec8f106ec2b45fd24e0a/packages/pymedphys_analysis/src/pymedphys_analysis/mocks/profiles.py
def gaussian_cdf(x, mu=0, sig=1):
    x = np.array(x, copy=False)
    return 0.5 * (1 + erf((x - mu) / (sig * np.sqrt(2))))


def scaled_penumbra_sig(profile_shoulder_edge=0.8):
    sig = 1 / (2 * np.sqrt(2) * erfinv(profile_shoulder_edge * 2 - 1))

    return sig


def create_profile_function(centre, field_width, penumbra_width):
    sig = scaled_penumbra_sig() * penumbra_width
    mu = [centre - field_width / 2, centre + field_width / 2]

    def profile(x):
        x = np.array(x, copy=False)
        return gaussian_cdf(x, mu[0], sig) * gaussian_cdf(-x, -mu[1], sig)  # pylint: disable=invalid-unary-operand-type

    return profile


def rotate_coords(x, y, theta):
    x_prime = x * np.cos(theta) + y * np.sin(theta)
    y_prime = -x * np.sin(theta) + y * np.cos(theta)

    return x_prime, y_prime


def create_rectangular_field_function(centre,
                                      side_lengths,
                                      penumbra_width,
                                      rotation=0):
    width_profile = create_profile_function(0, side_lengths[0], penumbra_width)
    length_profile = create_profile_function(0, side_lengths[1],
                                             penumbra_width)

    theta = -rotation / 180 * np.pi

    def field(x, y):
        x = np.array(x, copy=False)
        y = np.array(y, copy=False)
        x_shifted = x - centre[0]
        y_shifted = y - centre[1]
        x_rotated, y_rotated = rotate_coords(x_shifted, y_shifted, theta)

        return width_profile(x_rotated) * length_profile(y_rotated)

    return field


def create_square_field_function(centre,
                                 side_length,
                                 penumbra_width,
                                 rotation=0):

    side_lengths = [side_length, side_length]
    return create_rectangular_field_function(centre, side_lengths,
                                             penumbra_width, rotation)


def create_dummy_fields():
    rect_1 = create_rectangular_field_function((1.5, 2.1), (5, 7),
                                               0.6,
                                               rotation=45)
    rect_2 = create_rectangular_field_function((-0.5, 1.8), (5, 7),
                                               1,
                                               rotation=45)

    size = (-20, 21)

    x_grid = np.linspace(-20, 20, 100)
    y_grid = np.linspace(-20, 20, 100)

    xx, yy = np.meshgrid(x_grid, y_grid)

    shape = np.shape(xx)

    image_1 = rect_1(xx, yy)
    image_2 = rect_2(xx, yy)

    image_1 = image_1 + np.random.normal(0, 0.05, shape)
    image_2 = image_2 + np.random.normal(0, 0.05, shape)

    interp_1 = RectBivariateSpline(x_grid, y_grid, image_1, kx=1, ky=1)
    interp_2 = RectBivariateSpline(x_grid, y_grid, image_2, kx=1, ky=1)

    return interp_1, interp_2
