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

import os
from pathlib import Path

import pytest

from pymedphys.labs.film import load_cal_scans, load_image

HERE = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(HERE, "data/spine_case")

PRESCANS_CAL_DIR = os.path.join(DATA_DIR, "DatasetA/prescans/calibration")
POSTSCANS_CAL_DIR = os.path.join(DATA_DIR, "DatasetA/postscans/calibration")

BASELINES_DIR = os.path.join(DATA_DIR, "Baselines")


@pytest.fixture
def prescans():
    filepath = Path(DATA_DIR).joinpath("DatasetA/prescans/treatment.tif")
    scans = load_cal_scans(PRESCANS_CAL_DIR)
    scans["treatment"] = load_image(filepath)

    return scans


@pytest.fixture
def postscans():
    filepath = Path(DATA_DIR).joinpath("DatasetA/postscans/treatment.tif")
    scans = load_cal_scans(POSTSCANS_CAL_DIR)
    scans["treatment"] = load_image(filepath)

    return scans
