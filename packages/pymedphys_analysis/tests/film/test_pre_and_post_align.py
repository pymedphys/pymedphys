# Copyright (C) 2019 Cancer Care Associates

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

import os
from pathlib import Path

import pytest

import numpy as np
import matplotlib.pyplot as plt

from pymedphys_analysis.film import (load_cal_scans, align_images, load_image,
                                     interpolated_rotation,
                                     create_image_interpolation,
                                     shift_and_rotate)
from pymedphys_analysis.mocks import create_rectangular_field_function

CREATE_BASELINE = True
SHOW_FIGURES = True

HERE = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(HERE, 'data/spine_case')
PRESCANS_CAL_DIR = os.path.join(DATA_DIR, 'DatasetA/prescans/calibration')
POSTSCANS_CAL_DIR = os.path.join(DATA_DIR, 'DatasetA/postscans/calibration')

BASELINES_DIR = os.path.join(DATA_DIR, 'Baselines')
ALIGNMENT_BASELINES_FILEPATH = os.path.join(BASELINES_DIR,
                                            'pre_post_alignment.json')


@pytest.fixture
def prescans():
    filepath = Path(DATA_DIR).joinpath('DatasetA/prescans/treatment.tif')
    scans = load_cal_scans(PRESCANS_CAL_DIR)
    scans['treatment'] = load_image(filepath)

    return scans


@pytest.fixture
def postscans():
    filepath = Path(DATA_DIR).joinpath('DatasetA/postscans/treatment.tif')
    scans = load_cal_scans(POSTSCANS_CAL_DIR)
    scans['treatment'] = load_image(filepath)

    return scans


def create_axes(image, dpcm=100):
    shape = np.shape(image)
    x_span = (np.arange(0, shape[0]) - shape[0] // 2) * 10 / dpcm
    y_span = (np.arange(0, shape[1]) - shape[1] // 2) * 10 / dpcm

    return x_span, y_span


def compare_alignment_to_baseline(prescan, postscan, baseline=None):
    prescan_axes = create_axes(prescan)
    postscan_axes = create_axes(postscan)

    alignment = align_images(prescan_axes,
                             prescan,
                             postscan_axes,
                             postscan,
                             max_shift=20)

    shifted_image = shift_and_rotate(postscan_axes, prescan_axes, postscan,
                                     *alignment)

    if SHOW_FIGURES:
        plt.figure()
        plt.imshow(prescan)

        plt.figure()
        plt.imshow(shifted_image)
        print(np.shape(shifted_image))

        plt.figure()
        plt.imshow(shifted_image - prescan)

        plt.show()


def test_pre_and_post_align(prescans, postscans):
    keys = prescans.keys()
    assert keys == postscans.keys()

    for key in keys:
        compare_alignment_to_baseline(prescans[key], postscans[key])
