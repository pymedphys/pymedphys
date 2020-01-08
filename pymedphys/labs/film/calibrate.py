# Copyright (C) 2019 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import warnings
from pathlib import Path

from pymedphys._imports import numpy as np
from pymedphys._imports import plt

from scipy.optimize import basinhopping

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
