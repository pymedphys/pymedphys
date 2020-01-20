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

# Adapted from https://github.com/jrkerns/pylinac/tree/698254258ff4cb87812840c42b34c93ae32a4693

# pylint: disable = inconsistent-return-statements

"""This module holds classes for image loading and manipulation."""


from typing import Tuple

from pymedphys._imports import numpy as np

from .decorators import type_accept
from .geometry import Point

ARRAY = "Array"
DICOM = "DICOM"
IMAGE = "Image"
MM_PER_INCH = 25.4


# pylint: disable = attribute-defined-outside-init


class BaseImage:
    """Base class for the Image classes.

    Attributes
    ----------
    array : numpy.ndarray
        The actual image pixel array.
    """

    @property
    def center(self) -> Point:
        """Return the center position of the image array as a Point."""
        x_center = self.shape[1] / 2
        y_center = self.shape[0] / 2
        return Point(x_center, y_center)

    @type_accept(pixels=int)
    def crop(
        self,
        pixels: int = 15,
        edges: Tuple[str, ...] = ("top", "bottom", "left", "right"),
    ):
        """Removes pixels on all edges of the image in-place.

        Parameters
        ----------
        pixels : int
            Number of pixels to cut off all sides of the image.
        edges : tuple
            Which edges to remove from. Can be any combination of the four edges.
        """
        if pixels < 0:
            raise ValueError("Pixels to remove must be a positive number")
        if "top" in edges:
            self.array = self.array[pixels:, :]  # type: ignore
        if "bottom" in edges:
            self.array = self.array[:-pixels, :]
        if "left" in edges:
            self.array = self.array[:, pixels:]
        if "right" in edges:
            self.array = self.array[:, :-pixels]

    def remove_edges(
        self,
        pixels: int = 15,
        edges: Tuple[str, ...] = ("top", "bottom", "left", "right"),
    ):
        """Removes pixels on all edges of the image in-place.

        Parameters
        ----------
        pixels : int
            Number of pixels to cut off all sides of the image.
        edges : tuple
            Which edges to remove from. Can be any combination of the four edges.
        """
        DeprecationWarning(
            "`remove_edges` is deprecated and will be removed in a future version. Use `crop` instead"
        )
        self.crop(pixels=pixels, edges=edges)

    def as_binary(self, threshold: int):
        """Return a binary (black & white) image based on the given threshold.

        Parameters
        ----------
        threshold : int, float
            The threshold value. If the value is above or equal to the threshold it is set to 1, otherwise to 0.

        Returns
        -------
        ArrayImage
        """
        array = np.where(self.array >= threshold, 1, 0)
        return ArrayImage(array)

    def invert(self):
        """Invert (imcomplement) the image."""
        orig_array = self.array
        self.array = -orig_array + orig_array.max() + orig_array.min()

    def flipud(self):
        """ Flip the image array upside down in-place. Wrapper for np.flipud()"""
        self.array = np.flipud(self.array)

    def ground(self):
        """Ground the profile such that the lowest value is 0.

        .. note::
            This will also "ground" profiles that are negative or partially-negative.
            For such profiles, be careful that this is the behavior you desire.

        Returns
        -------
        float
            The amount subtracted from the image.
        """
        min_val = self.array.min()
        self.array -= min_val
        return min_val

    def normalize(self, norm_val="max"):
        """Normalize the image values to the given value.

        Parameters
        ----------
        norm_val : str, number
            If a string, must be 'max', which normalizes the values to the maximum value.
            If a number, normalizes all values to that number.
        """
        if norm_val == "max":
            val = self.array.max()
        else:
            val = norm_val
        self.array = self.array / val

    def check_inversion_by_histogram(self, percentiles=(5, 50, 95)):
        """Check the inversion of the image using histogram analysis. The assumption is that the image
        is mostly background-like values and that there is a relatively small amount of dose getting to the image
        (e.g. a picket fence image). This function looks at the distance from one percentile to another to determine
        if the image should be inverted.

        Parameters
        ----------
        percentiles : 3-element tuple
            The 3 percentiles to compare. Default is (5, 50, 95). Recommend using (x, 50, y). To invert the other way
            (where pixel value is *decreasing* with dose, reverse the percentiles, e.g. (95, 50, 5).
        """
        p5 = np.percentile(self.array, percentiles[0])
        p50 = np.percentile(self.array, percentiles[1])
        p95 = np.percentile(self.array, percentiles[2])
        dist_to_5 = abs(p50 - p5)
        dist_to_95 = abs(p50 - p95)
        if dist_to_5 > dist_to_95:
            self.invert()

    @property
    def ndim(self):
        return self.array.ndim

    @property
    def shape(self):
        return self.array.shape

    @property
    def size(self):
        return self.array.size

    def sum(self):
        return self.array.sum()

    def __len__(self):
        return len(self.array)

    def __getitem__(self, item):
        return self.array[item]


class ArrayImage(BaseImage):
    """An image constructed solely from a numpy array."""

    def __init__(self, array, *, dpi=None, sid=None, dtype=None):
        """
        Parameters
        ----------
        array : numpy.ndarray
            The image array.
        dpi : int, float
            The dots-per-inch of the image, defined at isocenter.

            .. note:: If a DPI tag is found in the image, that value will override the parameter, otherwise this one
                will be used.
        sid : int, float
            The Source-to-Image distance in mm.
        dtype : dtype, None, optional
            The data type to cast the image data as. If None, will use whatever raw image format is.
        """
        if dtype is not None:
            self.array = np.array(array, dtype=dtype)
        else:
            self.array = array
        self._dpi = dpi
        self.sid = sid

    @property
    def dpmm(self):
        """The Dots-per-mm of the image, defined at isocenter. E.g. if an EPID image is taken at 150cm SID,
        the dpmm will scale back to 100cm."""
        try:
            return self.dpi / MM_PER_INCH
        except AttributeError:
            return

    @property
    def dpi(self):
        """The dots-per-inch of the image, defined at isocenter."""
        dpi = None
        if self._dpi is not None:
            dpi = self._dpi
            if self.sid is not None:
                dpi *= self.sid / 1000
        return dpi

    def __sub__(self, other):
        return ArrayImage(self.array - other.array)
