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

# pylint: disable=C0326


import io
import os
import zipfile
from glob import glob

import pytest

import numpy as np

import pydicom
from pydicom.filebase import DicomBytesIO

from pymedphys.dcm import dcm_from_dict
from pymedphys.mudensity import MUDensity

MU = [0, 10, 20]

MLC = np.array([
    [
        [3, -3],
        [3, -3],
        [3, -3]
    ],
    [
        [3, 3],
        [3, 3],
        [3, 3]
    ],
    [
        [-3, 3],
        [-3, 3],
        [-3, 3]
    ]
])

JAW = np.array([
    [3, 3],
    [3, 3],
    [3, 3]
])

LEAF_PAIR_WIDTHS = [2, 2, 2]

GRID_RESOLUTION = 2
MAX_LEAF_GAP = 8

REFERENCE_MU_DENSITY = [
    [0,  0,  0,  0, 0],
    [0, 10, 10, 10, 0],
    [0, 10, 10, 10, 0],
    [0, 10, 10, 10, 0],
    [0,  0,  0,  0, 0]
]

DATA_DIRECTORY = os.path.join(
    os.path.dirname(__file__), "../data/logfiles")
LOGFILE_ZIPS = glob(os.path.abspath(os.path.join(
    DATA_DIRECTORY, '*/lfs-*.zip')))


@pytest.mark.skip("Deleted LFS files, need to implement test file storage")
def test_compare_varian_logfiles_to_dicom():
    for zip_filepath in LOGFILE_ZIPS:
        compare_logfile_within_zip(zip_filepath)


def compare_logfile_within_zip(zip_filepath):
    with open(zip_filepath, 'rb') as input_file:
        data = io.BytesIO(input_file.read())

    data_zip = zipfile.ZipFile(data)

    namelist = data_zip.namelist()
    dicom_files = [path for path in namelist if path.endswith('.dcm')]

    assert len(dicom_files) == 1
    dicom_file = dicom_files[0]

    with data_zip.open(dicom_file) as file_object:
        dcm_bytes = DicomBytesIO(file_object.read())
        dcm = pydicom.dcmread(dcm_bytes)

    MUDensity.from_dicom(dcm)


def test_from_dicom():
    leaf_boundaries = [0] + np.cumsum(LEAF_PAIR_WIDTHS).tolist()
    leaf_boundaries = np.array(leaf_boundaries) - np.mean(leaf_boundaries)

    total_mu = MU[-1]
    mu_weights = np.array(MU) / total_mu

    control_point_sequence = [
        {
            'CumulativeMetersetWeight': mu_weight,
            'BeamLimitingDevicePositionSequence': [
                {
                    'RTBeamLimitingDeviceType': 'ASYMY',
                    'LeafJawPositions': None
                },
                {

                }
            ]
        }
        for mu_weight in mu_weights
    ]

    dcm = dcm_from_dict({
        'BeamSequence': [
            {
                'BeamLimitingDeviceSequence': [
                    {
                        'RTBeamLimitingDeviceType': 'MLCX',
                        'LeafPositionBoundaries': leaf_boundaries,
                        'NumberOfLeafJawPairs': len(leaf_boundaries) - 1
                    }
                ],
                'ControlPointSequence': [

                ]
            }
        ]
    })

    # MUDensity.from_dicom()
