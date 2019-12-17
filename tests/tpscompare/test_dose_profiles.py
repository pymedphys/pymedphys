# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import json
import lzma
import operator
import os

import pytest

import numpy as np
import pandas as pd

import pydicom

from pymedphys.dicom import depth_dose, profile
from pymedphys.labs.tpscompare import load_and_normalise_mephysto
from shared import (
    BASELINES_DIR,
    DICOM_DOSE_FILEPATHS,
    DICOM_PLAN_FILEPATH,
    MEASUREMENTS_DIR,
)

CREATE_BASELINE = False
BASELINE_FILEPATH = os.path.join(BASELINES_DIR, "dicom_dose_profiles.json")

# pylint: disable = redefined-outer-name


@pytest.fixture
def loaded_doses():
    doses = {}

    for key, filepath in DICOM_DOSE_FILEPATHS.items():

        with lzma.open(filepath) as a_file:
            doses[key] = pydicom.dcmread(a_file, force=True)

    return doses


@pytest.fixture
def loaded_plan():
    plan = pydicom.read_file(str(DICOM_PLAN_FILEPATH), force=True)

    return plan


def test_bulk_compare(loaded_doses, loaded_plan):
    absolute_dose_table = pd.read_csv(
        MEASUREMENTS_DIR.joinpath("AbsoluteDose.csv"), index_col=0
    )
    absolute_dose = absolute_dose_table["d10 @ 90 SSD"]["6 MV"]

    output_factors = pd.read_csv(
        MEASUREMENTS_DIR.joinpath("OutputFactors.csv"), index_col=0
    )

    absolute_doses = {
        key: output_factors[key]["6 MV"] * absolute_dose
        for key in output_factors.columns
    }

    absolute_scans_per_field = load_and_normalise_mephysto(
        MEASUREMENTS_DIR, r"06MV_(\d\dx\d\d)\.mcc", absolute_doses, 100
    )

    getter = operator.itemgetter("displacement", "dose")

    for key, absolute_scans in absolute_scans_per_field.items():
        dose_dataset = loaded_doses[key]

        depths, meas_dose = getter(absolute_scans["depth_dose"])
        tps_dose = depth_dose(depths, dose_dataset, loaded_plan) / 10
        diff = tps_dose - meas_dose

        assert np.abs(np.mean(diff)) <= 0.02
        assert np.std(diff) <= 0.05


def test_baseline_profiles(loaded_doses, loaded_plan):
    baselines = {}

    displacements = list(range(-100, 110, 10))
    depths = list(range(0, 310, 10))

    for key, dose_dataset in loaded_doses.items():
        baselines[key] = {}

        extracted_dose = depth_dose(depths, dose_dataset, loaded_plan)
        rounded_result = np.around(extracted_dose, decimals=2)
        baselines[key]["depth"] = rounded_result.tolist()

        for direction in ["inplane", "crossplane"]:
            baselines[key][direction] = {}
            for depth in [50, 100]:
                extracted_dose = profile(
                    displacements, depth, direction, dose_dataset, loaded_plan
                )
                rounded_result = np.around(extracted_dose, decimals=2)
                baselines[key][direction][str(depth)] = rounded_result.tolist()

    if CREATE_BASELINE:
        with open(BASELINE_FILEPATH, "w") as a_file:
            json.dump(baselines, a_file)

    else:
        with open(BASELINE_FILEPATH, "r") as a_file:
            baseline_result = json.load(a_file)

        assert baseline_result == baselines
