# Copyright (C) 2018-2021 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import copy
import json

from pymedphys._imports import matplotlib
from pymedphys._imports import numpy as np
from pymedphys._imports import plt, pydicom, pytest

import pymedphys
from pymedphys._data import download
from pymedphys._dicom import coords, create

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

        expected_xyz[orient] = np.array(expected_xyz[orient], dtype=object)

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


@pytest.mark.pydicom
def test_coords_in_datasets_are_equal():
    bits_allocated = 32

    test_dicom_dict = {
        "ImagePositionPatient": [-1.0, -1.0, -1.0],
        "ImageOrientationPatient": [1, 0, 0, 0, 1, 0],
        "BitsAllocated": bits_allocated,
        "BitsStored": bits_allocated,
        "Rows": 3,
        "Columns": 3,
        "PixelRepresentation": 0,
        "SamplesPerPixel": 1,
        "PhotometricInterpretation": "MONOCHROME2",
        "PixelSpacing": [1.0, 1.0],
        "GridFrameOffsetVector": [0.0, 1.0, 2.0],
        "PixelData": np.ones((3, 3, 3)).tobytes(),
    }

    ds1 = create.dicom_dataset_from_dict(test_dicom_dict)
    ds1.fix_meta_info(enforce_standard=False)
    ds2 = copy.deepcopy(ds1)
    assert coords.coords_in_datasets_are_equal([ds1, ds2])

    # only one coords supplied:
    assert coords.coords_in_datasets_are_equal([ds1])

    # y-shift (for DICOM HFS)
    ds2.ImagePositionPatient = [-1.0, -1.1, -1.0]
    assert not coords.coords_in_datasets_are_equal([ds1, ds2])

    # same coords but rotated using IOP
    # (so mapping to PixelData would be incorrect)
    ds2.ImagePositionPatient = [-1.0, 1.0, 1.0]
    ds2.ImageOrientationPatient = [1.0, 0, 0, 0, -1, 0]
    assert not coords.coords_in_datasets_are_equal([ds1, ds2])

    # same coords but rotated using GFOV
    # (so mapping to PixelData would be incorrect)
    ds2.ImagePositionPatient = [-1.0, -1.0, 1.0]
    ds2.ImageOrientationPatient = [1.0, 0, 0, 0, 1, 0]
    ds2.GridFrameOffsetVector = [0, -1, -2]
    assert not coords.coords_in_datasets_are_equal([ds1, ds2])


@pytest.mark.pydicom
def test_non_square_pixels():
    path_to_downloaded_file = pymedphys.data_path("rtdose_non_square_pixels.dcm")
    rtdose = pydicom.read_file(path_to_downloaded_file, force=True)
    zyx, dose = pymedphys.dicom.zyx_and_dose_from_dataset(rtdose)
    test_points = []
    for p in rtdose.ROIContourSequence:
        test_points.append(p.ContourData)
    test_points = np.array(test_points)
    prescription = 100 * rtdose.DoseGridScaling
    z, y, x = zyx
    index = np.argmin(np.abs(z - test_points[0][2]))
    try:
        fig, ax = plt.subplots()
        cs = ax.contour(x, y, dose[index], levels=[2 * prescription], colors=["r"])
        is_inside_count = 0
        for p in test_points:
            for contour in cs.allsegs[0]:
                path = matplotlib.path.Path(contour)
                if path.contains_point(p[:2]):
                    is_inside_count += 1
    finally:
        plt.close(fig)

    assert is_inside_count == 3
