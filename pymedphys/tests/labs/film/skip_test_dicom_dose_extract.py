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


# The following needs to be removed before leaving labs
# pylint: skip-file

import json
import lzma
import os
from pathlib import Path

import numpy as np

import pydicom

from fixtures import BASELINES_DIR, DATA_DIR
from pymedphys._dicom.dose import dicom_dose_interpolate

CREATE_BASELINE = False
DICOM_DOSE_BASELINE_FILEPATH = os.path.join(BASELINES_DIR, "dicom_dose_extract.json")


def test_dose_extract():
    x = np.arange(-60, 61)
    y = np.arange(-70, 71)
    z = np.array([0])

    compressed_dicom_path = list(Path(DATA_DIR).joinpath("Raw").glob("*.dcm.xz"))[0]

    with lzma.open(compressed_dicom_path) as a_file:
        dicom_dataset = pydicom.dcmread(a_file, force=True)

    result = dicom_dose_interpolate(dicom_dataset, (z, y, x))

    rounded_result = np.around(result, decimals=2)
    json_parsable_result = rounded_result.tolist()

    if CREATE_BASELINE:
        with open(DICOM_DOSE_BASELINE_FILEPATH, "w") as a_file:
            json.dump(json_parsable_result, a_file)

    else:
        with open(DICOM_DOSE_BASELINE_FILEPATH, "r") as a_file:
            baseline_result = json.load(a_file)

        assert baseline_result == json_parsable_result
