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
import json
import lzma
from pathlib import Path

import numpy as np

import pydicom

from pymedphys_dicom.dicom import dicom_dose_interpolate
from fixtures import BASELINES_DIR, DATA_DIR

CREATE_BASELINE = False
DICOM_DOSE_BASELINE_FILEPATH = os.path.join(BASELINES_DIR,
                                            'dicom_dose_extract.json')


def test_dose_extract():
    x = np.arange(-60, 61)
    y = np.arange(-70, 71)
    z = np.array([0])

    compressed_dicom_path = list(
        Path(DATA_DIR).joinpath('Raw').glob('*.dcm.xz'))[0]

    with lzma.open(compressed_dicom_path) as a_file:
        dicom_dataset = pydicom.dcmread(a_file, force=True)

    result = dicom_dose_interpolate(dicom_dataset, (z, y, x))

    rounded_result = np.around(result, decimals=2)
    json_parsable_result = rounded_result.tolist()

    if CREATE_BASELINE:
        with open(DICOM_DOSE_BASELINE_FILEPATH, 'w') as a_file:
            json.dump(json_parsable_result, a_file)

    else:
        with open(DICOM_DOSE_BASELINE_FILEPATH, 'r') as a_file:
            baseline_result = json.load(a_file)

        assert baseline_result == json_parsable_result
