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

# Changes to revert to v2.2.6 code determined from https://github.com/jrkerns/pylinac/compare/v2.2.6...v2.2.7#diff-49572d03390f5858885f645e7034ff24
# and https://github.com/jrkerns/pylinac/blob/v2.2.6/pylinac/winston_lutz.py

"""The Winston-Lutz module loads and processes EPID images that have acquired Winston-Lutz type images.

Features:

* **Couch shift instructions** - After running a WL test, get immediate feedback on how to shift the couch.
  Couch values can also be passed in and the new couch values will be presented so you don't have to do that pesky conversion.
  "Do I subtract that number or add it?"
* **Automatic field & BB positioning** - When an image or directory is loaded, the field CAX and the BB
  are automatically found, along with the vector and scalar distance between them.
* **Isocenter size determination** - Using backprojections of the EPID images, the 3D gantry isocenter size
  and position can be determined *independent of the BB position*. Additionally, the 2D planar isocenter size
  of the collimator and couch can also be determined.
* **Image plotting** - WL images can be plotted separately or together, each of which shows the field CAX, BB and
  scalar distance from BB to CAX.
* **Axis deviation plots** - Plot the variation of the gantry, collimator, couch, and EPID in each plane
  as well as RMS variation.
* **File name interpretation** - Rename DICOM filenames to include axis information for linacs that don't include
  such information in the DICOM tags. E.g. "myWL_gantry45_coll0_couch315.dcm".
"""

from typing import List, Tuple

from pymedphys._imports import numpy as np
from pymedphys._imports import scipy, skimage

from .core import image
from .core.geometry import Point, Vector
from .core.mask import bounding_box, filled_area_ratio
from .core.profile import SingleProfile

GANTRY = "Gantry"
COLLIMATOR = "Collimator"
COUCH = "Couch"
COMBO = "Combo"
EPID = "Epid"
REFERENCE = "Reference"
ALL = "All"


class WLImage(image.ArrayImage):
    """Holds individual Winston-Lutz EPID images, image properties, and automatically finds the field CAX and BB."""

    def __init__(self, array, *, dpi=None, sid=None, dtype=None):
        super().__init__(array, dpi=dpi, sid=sid, dtype=dtype)
        self.check_inversion_by_histogram(percentiles=(0.01, 50, 99.99))
        self._clean_edges()
        self.field_cax, self.rad_field_bounding_box = self._find_field_centroid()
        self._bb = None

    @property
    def bb(self):
        if self._bb is None:
            self._bb = self._find_bb()

        return self._bb

    def _clean_edges(self, window_size: int = 2):
        """Clean the edges of the image to be near the background level."""

        def has_noise(self, window_size):
            """Helper method to determine if there is spurious signal at any of the image edges.

            Determines if the min or max of an edge is within 10% of the baseline value and trims if not.
            """
            near_min, near_max = np.percentile(self.array, [5, 99.5])
            img_range = near_max - near_min
            top = self[:window_size, :]
            left = self[:, :window_size]
            bottom = self[-window_size:, :]
            right = self[:, -window_size:]
            edge_array = np.concatenate(
                (top.flatten(), left.flatten(), bottom.flatten(), right.flatten())
            )
            edge_too_low = edge_array.min() < (near_min - img_range / 10)
            edge_too_high = edge_array.max() > (near_max + img_range / 10)
            return edge_too_low or edge_too_high

        safety_stop = np.min(self.shape) / 10
        while has_noise(self, window_size) and safety_stop > 0:
            self.remove_edges(window_size)
            safety_stop -= 1

    def _find_field_centroid(self) -> Tuple[Point, List]:
        """Find the centroid of the radiation field based on a 50% height threshold.

        Returns
        -------
        p
            The CAX point location.
        edges
            The bounding box of the field, plus a small margin.
        """
        min_val, max_val = np.percentile(self.array, [5, 99.9])
        threshold_img = self.as_binary((max_val - min_val) / 2 + min_val)
        # clean single-pixel noise from outside field
        cleaned_img = scipy.ndimage.binary_erosion(threshold_img)
        [*edges] = bounding_box(cleaned_img)
        edges[0] -= 10
        edges[1] += 10
        edges[2] -= 10
        edges[3] += 10
        coords = scipy.ndimage.measurements.center_of_mass(threshold_img)
        p = Point(x=coords[-1], y=coords[0])
        return p, edges

    def _find_bb(self) -> Point:
        """Find the BB within the radiation field. Iteratively searches for a circle-like object
        by lowering a low-pass threshold value until found.

        Returns
        -------
        Point
            The weighted-pixel value location of the BB.
        """
        # get initial starting conditions
        hmin, hmax = np.percentile(self.array, [5, 99.9])
        spread = hmax - hmin
        max_thresh = hmax
        lower_thresh = hmax - spread / 1.5
        # search for the BB by iteratively lowering the low-pass threshold value until the BB is found.
        found = False
        while not found:
            try:
                binary_arr = np.logical_and((max_thresh > self), (self >= lower_thresh))
                labeled_arr, num_roi = scipy.ndimage.measurements.label(binary_arr)
                roi_sizes, _ = np.histogram(labeled_arr, bins=num_roi + 1)
                bw_bb_img = np.where(
                    labeled_arr == np.argsort(roi_sizes)[-3], 1, 0
                )  # we pick the 3rd largest one because the largest is the background, 2nd is rad field, 3rd is the BB
                bb_regionprops = skimage.measure.regionprops(bw_bb_img)[0]

                if not is_round(bb_regionprops):
                    raise ValueError
                if not is_modest_size(bw_bb_img, self.rad_field_bounding_box):
                    raise ValueError
                if not is_symmetric(bw_bb_img):
                    raise ValueError
            except (IndexError, ValueError):
                max_thresh -= 0.05 * spread
                if max_thresh < hmin:
                    raise ValueError(
                        "Pylinac v2.2.7: Unable to locate the BB. Make sure the field "
                        "edges do not obscure the BB and that there is no artifacts in "
                        "the images."
                    )
            else:
                found = True

        # determine the center of mass of the BB
        inv_img = image.ArrayImage(self.array)
        # we invert so BB intensity increases w/ attenuation
        inv_img.check_inversion_by_histogram(percentiles=(0.01, 50, 99.99))
        bb_rprops = skimage.measure.regionprops(bw_bb_img, intensity_image=inv_img)[0]
        return Point(bb_rprops.weighted_centroid[1], bb_rprops.weighted_centroid[0])

    @property
    def epid(self) -> Point:
        """Center of the EPID panel"""
        return self.center

    @property
    def cax2epid_vector(self) -> Vector:
        """The vector in mm from the CAX to the EPID center pixel"""
        dist = (self.epid - self.field_cax) / self.dpmm
        return Vector(dist.x, dist.y, dist.z)

    @property
    def cax2bb_distance(self):
        """The scalar distance in mm from the CAX to the BB."""
        dist = self.field_cax.distance_to(self.bb)
        return dist / self.dpmm

    @property
    def cax2epid_distance(self):
        """The scalar distance in mm from the CAX to the EPID center pixel"""
        return self.field_cax.distance_to(self.epid) / self.dpmm


def is_symmetric(logical_array) -> bool:
    """Whether the binary object's dimensions are symmetric, i.e. a perfect circle. Used to find the BB."""
    ymin, ymax, xmin, xmax = bounding_box(logical_array)
    y = abs(ymax - ymin)
    x = abs(xmax - xmin)
    if x > max(y * 1.05, y + 3) or x < min(y * 0.95, y - 3):
        return False
    return True


def is_modest_size(logical_array, field_bounding_box):
    """Decide whether the ROI is roughly the size of a BB; not noise and not an artifact. Used to find the BB."""
    bbox = field_bounding_box
    rad_field_area = (bbox[1] - bbox[0]) * (bbox[3] - bbox[2])
    return rad_field_area * 0.003 < np.sum(logical_array) < rad_field_area * 0.3


def is_round(rprops):
    """Decide if the ROI is circular in nature by testing the filled area vs bounding box. Used to find the BB."""
    expected_fill_ratio = np.pi / 4  # area of a circle inside a square
    actual_fill_ratio = rprops.filled_area / rprops.bbox_area
    return expected_fill_ratio * 1.2 > actual_fill_ratio > expected_fill_ratio * 0.8


def is_round_old(logical_array):
    """Decide if the ROI is circular in nature by testing the filled area vs bounding box. Used to find the BB."""
    expected_fill_ratio = np.pi / 4
    actual_fill_ratio = filled_area_ratio(logical_array)
    return expected_fill_ratio * 1.2 > actual_fill_ratio > expected_fill_ratio * 0.8


class WLImageOld(WLImage):
    def _find_bb(self) -> Point:
        """Find the BB within the radiation field. Iteratively searches for a circle-like object
        by lowering a low-pass threshold value until found.
        Returns
        -------
        Point
            The weighted-pixel value location of the BB.
        """
        # get initial starting conditions
        hmin, hmax = np.percentile(self.array, [5, 99.9])
        spread = hmax - hmin
        max_thresh = hmax
        lower_thresh = hmax - spread / 1.5
        # search for the BB by iteratively lowering the low-pass threshold value until the BB is found.
        found = False
        while not found:
            try:
                binary_arr = np.logical_and((max_thresh > self), (self >= lower_thresh))
                labeled_arr, num_roi = scipy.ndimage.measurements.label(binary_arr)
                roi_sizes, _ = np.histogram(labeled_arr, bins=num_roi + 1)
                bw_bb_img = np.where(labeled_arr == np.argsort(roi_sizes)[-3], 1, 0)

                if not is_round_old(bw_bb_img):
                    raise ValueError
                if not is_modest_size(bw_bb_img, self.rad_field_bounding_box):
                    raise ValueError
                if not is_symmetric(bw_bb_img):
                    raise ValueError
            except (IndexError, ValueError):
                max_thresh -= 0.05 * spread
                if max_thresh < hmin:
                    raise ValueError(
                        "Pylinac v2.2.6: Unable to locate the BB. Make sure the field "
                        "edges do not obscure the BB and that there is no artifacts in "
                        "the images."
                    )
            else:
                found = True

        # determine the center of mass of the BB
        inv_img = image.ArrayImage(self.array)
        inv_img.invert()
        x_arr = np.abs(np.average(bw_bb_img, weights=inv_img, axis=0))
        x_com = SingleProfile(x_arr).fwxm_center(interpolate=True)
        y_arr = np.abs(np.average(bw_bb_img, weights=inv_img, axis=1))
        y_com = SingleProfile(y_arr).fwxm_center(interpolate=True)
        return Point(x_com, y_com)
