# Copyright (C) 2019 Simon Biggs

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

import warnings
from pathlib import Path

import numpy as np
from scipy.optimize import basinhopping

import matplotlib.pyplot as plt

import imageio

from .optical_density import calc_net_od

DEFAULT_CAL_STRING_END = " cGy.tif"


def create_dose_function(net_od, dose):
    net_od = np.array(net_od, copy=False)
    dose = np.array(dose, copy=False)

    to_minimise = create_to_minimise(net_od, dose)
    result = basinhopping(to_minimise, [np.max(dose) / np.max(net_od), 1, 1])

    return create_cal_fit(*result.x)


def create_cal_fit(a, b, n):
    def cal_fit(net_od):
        net_od = np.array(net_od, copy=False)
        return a * net_od + b * net_od ** n

    return cal_fit


def create_to_minimise(net_od, dose):
    def to_minimise(x):
        a, b, n = x

        cal_fit = create_cal_fit(a, b, n)
        return np.sum((cal_fit(net_od) - dose) ** 2)

    return to_minimise


def calc_calibration_points(
    prescans, postscans, alignments=None, figures=False, pixel_trim=0
):
    """Returns calibration points based on dictionaries of prescans and postscans.

    The key of the dictionaries of images is to represent the dose calibration
    point. If the key cannot be converted into a float that image will be
    ignored.
    """
    keys = prescans.keys()
    assert keys == postscans.keys()

    calibration_points = {}

    if alignments is None:
        alignments = {key: None for key in keys}

    for key in keys:
        try:
            dose_value = float(key)
        except ValueError:
            warnings.warn(
                "{} does not appear to be a calibration image key. This will "
                "be skipped."
            )
            continue

        net_od, alignment = calc_net_od(
            prescans[key], postscans[key], alignment=alignments[key]
        )

        if pixel_trim != 0:
            trim_ref = (slice(pixel_trim, -pixel_trim), slice(pixel_trim, -pixel_trim))
            net_od = net_od[trim_ref]

        if figures:
            plt.figure()
            plt.imshow(net_od)
            plt.show()

        calibration_points[dose_value] = np.median(net_od)
        alignments[key] = alignment

    return calibration_points, alignments


def load_cal_scans(path, cal_string_end=DEFAULT_CAL_STRING_END):
    path = Path(path)

    cal_pattern = "*" + cal_string_end
    filepaths = path.glob(cal_pattern)

    calibrations = {
        float(path.name.rstrip(cal_string_end)): load_image(path) for path in filepaths
    }

    return calibrations


def load_image(path):
    return imageio.imread(path)
