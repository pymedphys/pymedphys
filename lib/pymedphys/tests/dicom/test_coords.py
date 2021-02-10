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

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

import pymedphys
from pymedphys._data import download
from pymedphys._dicom import coords, create


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


def test_axis_extraction_all_orients_and_coord_systems():
    r"""Run the xyz extraction test sequence for a given
    xyz extraction function"""

    test_ds_dict = {
        key: pydicom.dcmread(get_data_file(key))
        for key in coords.ORIENTATIONS_SUPPORTED
    }

    for orient, dicom in test_ds_dict.items():
        axes_dicom = coords.xyz_axes_from_dataset(dicom, "DICOM")
        axes_patient = coords.xyz_axes_from_dataset(dicom, "PATIENT")
        axes_fixed = coords.xyz_axes_from_dataset(dicom, "FIXED")

        assert np.array_equal(axes_dicom[0], axes_patient[0])
        assert np.array_equal(axes_dicom[1], -axes_patient[2])
        assert np.array_equal(axes_dicom[2], axes_patient[1])

        if orient == "HFS":  # iex fixed should match iec patient for HFS
            assert np.array_equal(axes_patient[0], axes_fixed[0])
            assert np.array_equal(axes_patient[1], axes_fixed[1])
            assert np.array_equal(axes_patient[2], axes_fixed[2])

        elif orient == "HFP":
            assert np.array_equal(axes_patient[0], -axes_fixed[0])
            assert np.array_equal(axes_patient[1], axes_fixed[1])
            assert np.array_equal(axes_patient[2], -axes_fixed[2])

        elif orient == "FFS":
            assert np.array_equal(axes_patient[0], -axes_fixed[0])
            assert np.array_equal(axes_patient[1], -axes_fixed[1])
            assert np.array_equal(axes_patient[2], axes_fixed[2])

        elif orient == "FFP":
            assert np.array_equal(axes_patient[0], axes_fixed[0])
            assert np.array_equal(axes_patient[1], -axes_fixed[1])
            assert np.array_equal(axes_patient[2], -axes_fixed[2])

        elif orient == "HFDL":
            assert np.array_equal(axes_patient[0], -axes_fixed[2])
            assert np.array_equal(axes_patient[1], axes_fixed[1])
            assert np.array_equal(axes_patient[2], axes_fixed[0])

        elif orient == "HFDR":
            assert np.array_equal(axes_patient[0], axes_fixed[2])
            assert np.array_equal(axes_patient[1], axes_fixed[1])
            assert np.array_equal(axes_patient[2], -axes_fixed[0])

        elif orient == "FFDL":
            assert np.array_equal(axes_patient[0], -axes_fixed[2])
            assert np.array_equal(axes_patient[1], -axes_fixed[1])
            assert np.array_equal(axes_patient[2], -axes_fixed[0])

        elif orient == "FFDR":
            assert np.array_equal(axes_patient[0], axes_fixed[2])
            assert np.array_equal(axes_patient[1], -axes_fixed[1])
            assert np.array_equal(axes_patient[2], axes_fixed[0])


@pytest.mark.pydicom
def test_coords_in_datasets_are_equal():
    test_dicom_dict = {
        "ImagePositionPatient": [-1.0, -1.0, -1.0],
        "ImageOrientationPatient": [1, 0, 0, 0, 1, 0],
        "BitsAllocated": 32,
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


def test_coords_from_dataset():

    pixels = np.ones((4, 2, 3), dtype=np.uint32)

    test_dicom_dict = {
        "Modality": "RTDOSE",
        "ImagePositionPatient": [-1.0, -1.0, -1.0],
        "ImageOrientationPatient": [1, 0, 0, 0, 1, 0],
        "BitsAllocated": 32,
        "Rows": 2,
        "Columns": 3,
        "NumberOfFrames": 4,
        "PixelRepresentation": 0,
        "SamplesPerPixel": 1,
        "PhotometricInterpretation": "MONOCHROME2",
        "PixelSpacing": [1.0, 1.0],
        "GridFrameOffsetVector": [0.0, 1.0, 2.0, 3.0],
        "PixelData": pixels.tobytes(),
        "DoseGridScaling": 1,
    }

    ds = create.dicom_dataset_from_dict(test_dicom_dict)
    ds.fix_meta_info(enforce_standard=False)

    for test_coord_system in ("DICOM", "IEC FIXED", "IEC PATIENT"):
        for _, im_orient_pat in coords.ORIENTATIONS_SUPPORTED.items():

            ds.ImageOrientationPatient = im_orient_pat
            ds_coords = coords.coords_from_dataset(ds, coord_system=test_coord_system)

            for i, coord_meshgrid in enumerate(ds_coords.grid):
                print(i)
                assert coord_meshgrid.shape == pixels.shape
