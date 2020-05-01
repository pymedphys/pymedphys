# Copyright (c) 2014-2019 James Kerns

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions
# of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
# TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

# Vendored from https://github.com/jrkerns/pylinac/tree/698254258ff4cb87812840c42b34c93ae32a4693

"""Module for processing "masked" arrays, i.e. binary images."""
from typing import Tuple

from pymedphys._imports import numpy as np

from .geometry import Point


def bounding_box(array) -> Tuple[float, ...]:
    """Get the bounding box values of an ROI in a 2D array."""
    binary_arr = np.argwhere(array)
    (ymin, xmin), (ymax, xmax) = binary_arr.min(0), binary_arr.max(0) + 1
    return ymin, ymax, xmin, xmax


def filled_area_ratio(array) -> float:
    """Return the ratio of filled pixels to empty pixels in the ROI bounding box.

    For example a solid square would be 1.0, while a sold circle would be ~0.785.
    """
    ymin, ymax, xmin, xmax = bounding_box(array)
    box_area = (ymax - ymin) * (xmax - xmin)
    filled_area = np.sum(array)
    return float(filled_area / box_area)


def square_ratio(array) -> float:
    """Determine the width/height ratio of the ROI"""
    ymin, ymax, xmin, xmax = bounding_box(array)
    y = abs(ymax - ymin)
    x = abs(xmax - xmin)
    return y / x


def sector_mask(shape: Tuple, center: Point, radius, angle_range: Tuple = (0, 360)):
    """Return a circular arc-shaped boolean mask.

    Parameters
    ----------
    shape : tuple
        Shape of the image matrix. Usually easiest to pass something like array.shape
    center : Point, iterable
        The center point of the desired mask.
    radius : int, float
        Radius of the mask.
    angle_range : iterable
        The angle range of the mask. E.g. the default (0, 360) creates an entire circle.
        The start/stop angles should be given in clockwise order. 0 is right (0 on unit circle).

    References
    ----------
    https://stackoverflow.com/questions/18352973/mask-a-circular-sector-in-a-numpy-array/18354475#18354475
    """

    x, y = np.ogrid[: shape[0], : shape[1]]
    cy, cx = center.x, center.y
    # tmin, tmax = np.deg2rad(angle_range)
    tmin, tmax = angle_range

    # ensure stop angle > start angle
    if tmax < tmin:
        tmax += 2 * np.pi

    # convert cartesian --> polar coordinates
    r2 = (x - cx) * (x - cx) + (y - cy) * (y - cy)
    theta = np.arctan2(x - cx, y - cy) - tmin

    # wrap angles between 0 and 2*pi
    theta %= 2 * np.pi

    # circular mask
    circmask = r2 <= radius * radius

    # angular mask
    anglemask = theta <= (tmax - tmin)

    return circmask * anglemask
