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

from pymedphys_base.delivery.utilities import to_tuple
from pymedphys_analysis.film import dicom_dose_extract


CREATE_BASELINE = True
HERE = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(HERE, 'data/spine_case')
BASELINES_DIR = os.path.join(DATA_DIR, 'Baselines')

DICOM_DOSE_BASELINE_FILEPATH = os.path.join(
    BASELINES_DIR, 'dicom_dose_extract.json')


def test_dose_plane_extract():

    # Variables named as if patient is HFS
    left_right_interp = np.arange(-60, 61)
    ant_post_interp = np.arange(-70, 71)
    sup_inf_interp = np.array([0, ])

    compressed_dicom_paths = list(Path(DATA_DIR).joinpath('Raw').glob(
        '*.dcm.xz.*'))

    compressed_dicom_paths.sort()

    print(compressed_dicom_paths)

    for item in compressed_dicom_paths:
        data = []
        with open(item, 'rb') as a_file:
            data.append(a_file.read())

    dicom_dataset = pydicom.dcmread(
        lzma.decompress(data), force=True)

    result = dicom_dose_extract(
        dicom_dataset,
        (sup_inf_interp, ant_post_interp, left_right_interp))

    rounded_result = np.around(result, decimals=2)
    tuple_result = to_tuple(rounded_result)

    if CREATE_BASELINE:
        with open(DICOM_DOSE_BASELINE_FILEPATH, 'w') as a_file:
            json.dump(tuple_result, a_file)

    else:
        with open(DICOM_DOSE_BASELINE_FILEPATH, 'r') as a_file:
            baseline_result = json.load(a_file)

        assert baseline_result == tuple_result
