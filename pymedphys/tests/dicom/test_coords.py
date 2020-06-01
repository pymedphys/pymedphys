# Copyright (C) 2018 Matthew Jennings

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

import pytest

import numpy as np

import pydicom

import pymedphys
from pymedphys._data import download
from pymedphys._dicom import coords

ORIENTATIONS_SUPPORTED = ["FFDL", "FFDR", "FFP", "FFS", "HFDL", "HFDR", "HFP", "HFS"]


def get_file_within_data_zip(zip_name, file_name):
    dose_data_files = pymedphys.zip_data_paths(zip_name)
    path_match = [path for path in dose_data_files if path.name == file_name]

    assert len(path_match) == 1

    return str(path_match[0])


def get_data_file(orientation_key):
    return download.get_file_within_data_zip(
        "dicom_dose_test_data.zip",
        "RD.DICOMORIENT.Dose_{}_empty.dcm".format(orientation_key),
    )


def run_xyz_function_tests(coord_system):
    r"""Run the xyz extraction test sequence for a given
    xyz extraction function"""

    expected_xyz_path = download.get_file_within_data_zip(
        "dicom_dose_test_data.zip", "expected_{}_xyz.json".format(coord_system.lower())
    )

    with open(expected_xyz_path) as fp:
        expected_xyz = json.load(fp)

    assert set(expected_xyz.keys()) == set(ORIENTATIONS_SUPPORTED)

    test_ds_dict = {
        key: pydicom.dcmread(get_data_file(key)) for key in ORIENTATIONS_SUPPORTED
    }

    for orient, dicom in test_ds_dict.items():
        test_xyz = coords.xyz_axes_from_dataset(dicom, coord_system)

        expected_xyz[orient] = np.array(expected_xyz[orient])

        # These tests were being skipped in the previous code
        assert np.array_equal(test_xyz[0], expected_xyz[orient][0])
        assert np.array_equal(test_xyz[1], expected_xyz[orient][1])
        assert np.array_equal(test_xyz[2], expected_xyz[orient][2])


@pytest.mark.pydicom
@pytest.mark.skip(
    reason=(
        "Test previously had a short circuit and did not run final "
        "assertions. Once the short circuit was removed the tests were "
        "failing."
    )
)
def test_extract_iec_patient_xyz():
    run_xyz_function_tests("PATIENT")


@pytest.mark.pydicom
def test_extract_iec_fixed_xyz():
    run_xyz_function_tests("FIXED")


@pytest.mark.pydicom
def test_extract_dicom_patient_xyz():
    run_xyz_function_tests("DICOM")
