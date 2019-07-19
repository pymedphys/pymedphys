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

from shared import BASELINES_DIR, DATA_DIR, DICOM_DOSE_FILEPATHS

CREATE_BASELINE = False
BASELINE_FILEPATH = os.path.join(BASELINES_DIR,
                                 'dicom_dose_profiles.json')


def test_profile_diffs():
    dicom_datasets = {}

    for key, filepath in DICOM_DOSE_FILEPATHS.items():

        with lzma.open(filepath) as a_file:
            dicom_datasets[key] = pydicom.dcmread(a_file, force=True)
