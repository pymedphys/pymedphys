# Copyright (C) 2018, 2021 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" A test suite for the DICOM RT Dose toolbox."""

import copy
import json
from os.path import abspath, dirname
from os.path import join as pjoin
from zipfile import ZipFile

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

import pymedphys
from pymedphys._data import download
from pymedphys._dicom import collection, create, dose, orientation

from . import test_coords

HERE = dirname(abspath(__file__))
DATA_DIRECTORY = pjoin(HERE, "data", "dose")
ORIENTATIONS_SUPPORTED = ["FFDL", "FFDR", "FFP", "FFS", "HFDL", "HFDR", "HFP", "HFS"]


@pytest.mark.pydicom
def test_dicom_dose_constancy():
    wedge_basline_filename = "wedge_dose_baseline.json"

    baseline_dicom_dose_dict_zippath = download.get_file_within_data_zip(
        "dicom_dose_test_data.zip", "lfs-wedge_dose_baseline.zip"
    )
    test_dicom_dose_filepath = download.get_file_within_data_zip(
        "dicom_dose_test_data.zip", "RD.wedge.dcm"
    )

    test_dicom_dose = collection.DicomDose.from_file(test_dicom_dose_filepath)

    with ZipFile(baseline_dicom_dose_dict_zippath, "r") as zip_ref:
        with zip_ref.open(wedge_basline_filename) as a_file:
            expected_dicom_dose_dict = json.load(a_file)

    assert np.allclose(
        test_dicom_dose.values, np.array(expected_dicom_dose_dict["values"])
    )
    assert test_dicom_dose.units == expected_dicom_dose_dict["units"]
    assert np.allclose(test_dicom_dose.x, np.array(expected_dicom_dose_dict["x"]))
    assert np.allclose(test_dicom_dose.y, np.array(expected_dicom_dose_dict["y"]))
    assert np.allclose(test_dicom_dose.z, np.array(expected_dicom_dose_dict["z"]))
    assert np.allclose(
        test_dicom_dose.coords, np.array(expected_dicom_dose_dict["coords"])
    )


@pytest.mark.pydicom
def test_require_dicom_patient_position():
    test_ds_dict = {
        key: pydicom.dcmread(test_coords.get_data_file(key))
        for key in ORIENTATIONS_SUPPORTED
    }

    ds_no_orient = pydicom.dcmread(
        str(pymedphys.data_path("example_structures.dcm")), force=True
    )

    test_ds_dict["no orient"] = ds_no_orient

    test_orientations = ("HFS", "HFP", "FFS", "FFP")

    for orient, ds in test_ds_dict.items():

        for test_orient in test_orientations:
            if orient == test_orient:
                orientation.require_dicom_patient_position(ds, test_orient)

            elif orient == "no orient":
                with pytest.raises(AttributeError):
                    orientation.require_dicom_patient_position(ds, test_orient)

            else:
                with pytest.raises(ValueError):
                    orientation.require_dicom_patient_position(ds, test_orient)


@pytest.mark.pydicom
def test_sum_doses_in_datasets():

    scale1 = 1e-2
    data1 = (
        np.array(
            [
                [[0.90, 0.80, 0.70], [0.60, 0.50, 0.40]],
                [[0.91, 0.81, 0.71], [0.61, 0.51, 0.41]],
                [[0.92, 0.82, 0.72], [0.62, 0.52, 0.42]],
                [[0.93, 0.83, 0.73], [0.63, 0.53, 0.43]],
            ]
        )
        / scale1
    ).astype(np.uint32)

    scale2 = 5e-9
    data2 = (
        np.array(
            [
                [[0.10, 0.20, 0.30], [0.40, 0.50, 0.60]],
                [[0.09, 0.19, 0.29], [0.39, 0.49, 0.59]],
                [[0.08, 0.18, 0.28], [0.38, 0.48, 0.58]],
                [[0.07, 0.17, 0.27], [0.37, 0.47, 0.57]],
            ]
        )
        / scale2
    ).astype(np.uint32)

    expected_sum = np.ones((4, 2, 3))

    bits_allocated = 32

    test_dicom_dict = {
        "PatientID": "PMP",
        "Modality": "RTDOSE",
        "ImagePositionPatient": [-1.0, -1.0, -1.0],
        "ImageOrientationPatient": [1, 0, 0, 0, 1, 0],
        "BitsAllocated": bits_allocated,
        "BitsStored": bits_allocated,
        "Rows": 2,
        "Columns": 3,
        "PixelRepresentation": 0,
        "SamplesPerPixel": 1,
        "PhotometricInterpretation": "MONOCHROME2",
        "PixelSpacing": [1.0, 1.0],
        "GridFrameOffsetVector": [0, 1, 2, 3],
        "PixelData": data1.tobytes(),
        "DoseGridScaling": scale1,
        "DoseSummationType": "PLAN",
        "DoseType": "PHYSICAL",
        "DoseUnits": "GY",
    }

    ds1 = create.dicom_dataset_from_dict(test_dicom_dict)
    ds1.fix_meta_info(enforce_standard=False)

    ds2 = copy.deepcopy(ds1)
    ds2.PixelData = data2.tobytes()
    ds2.DoseGridScaling = scale2

    ds_summed = dose.sum_doses_in_datasets([ds1, ds2])
    assert np.allclose(dose.dose_from_dataset(ds_summed), expected_sum)
    assert ds_summed.DoseType == "PHYSICAL"

    # Effective dose type:
    ds2.DoseType = "EFFECTIVE"
    ds_summed = dose.sum_doses_in_datasets([ds1, ds2])
    assert ds_summed.DoseType == "EFFECTIVE"

    # Single dataset
    ds_summed = dose.sum_doses_in_datasets([ds1])
    assert np.allclose(dose.dose_from_dataset(ds_summed), dose.dose_from_dataset(ds1))

    # More than two doses:
    ds_summed = dose.sum_doses_in_datasets([ds1, ds1, ds2, ds2])
    assert np.allclose(dose.dose_from_dataset(ds_summed), 2 * expected_sum)

    # Unmatched patient IDs
    with pytest.raises(ValueError):
        ds2.PatientID = "PMX"
        dose.sum_doses_in_datasets([ds1, ds2])
    ds2.PatientID = "PMP"

    # Bad modality
    with pytest.raises(ValueError):
        ds2.Modality = "CT"
        dose.sum_doses_in_datasets([ds1, ds2])
    ds2.Modality = "RTDOSE"

    # Nothing supplied:
    with pytest.raises(IndexError):
        dose.sum_doses_in_datasets([])

    # BEAM dose present:
    with pytest.raises(ValueError):
        ds2.DoseSummationType = "BEAM"
        dose.sum_doses_in_datasets([ds1, ds2])
    ds2.DoseSummationType = "PLAN"

    # Bad dose units
    with pytest.raises(ValueError):
        ds2.DoseUnits = "RELATIVE"
        dose.sum_doses_in_datasets([ds1, ds2])
    ds2.Modality = "GY"

    # Unmatched coords
    with pytest.raises(ValueError):
        ds2.ImagePositionPatient = [-1, -1.1, -1]
        dose.sum_doses_in_datasets([ds1, ds2])
    ds2.ImagePositionPatient = [-1, -1, -1]
