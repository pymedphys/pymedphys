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
# from pathlib import Path

import pytest

import matplotlib.pyplot as plt

from pymedphys_analysis.film import load_cal_scans, align

CREATE_BASELINE = True
SHOW_FIGURES = True

HERE = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(HERE, 'data/spine_case')
PRESCANS_DIR = os.path.join(DATA_DIR, 'DatasetA/prescans/calibration')
POSTSCANS_DIR = os.path.join(DATA_DIR, 'DatasetA/postscans/calibration')

BASELINES_DIR = os.path.join(DATA_DIR, 'Baselines')
ALIGNMENT_BASELINES_FILEPATH = os.path.join(BASELINES_DIR,
                                            'pre_post_alignment.json')


@pytest.fixture
def prescans():
    return load_cal_scans(PRESCANS_DIR)


@pytest.fixture
def postscans():
    return load_cal_scans(POSTSCANS_DIR)


def test_pre_and_post_align(prescans, postscans):
    plt.figure()
    plt.imshow(prescans[0])

    plt.show()
