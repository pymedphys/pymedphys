""" Copyright (C) 2018-2021 Matthew Jennings

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

"""A test suite for the DICOM RT Dose toolbox."""

import copy
import json
from os.path import abspath, dirname
from os.path import join as pjoin
from zipfile import ZipFile

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

import pymedphys
from pymedphys._data import download
from pymedphys._dicom.collection import DicomDose
from pymedphys._dicom.create import dicom_dataset_from_dict
from pymedphys._dicom.dose import (
    dose_from_dataset,
    require_patient_orientation,
    sum_doses_in_datasets,
)

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

    test_dicom_dose = DicomDose.from_file(test_dicom_dose_filepath)

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
def test_require_patient_orientation():
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
                require_patient_orientation(ds, test_orient)

            elif orient == "no orient":
                with pytest.raises(AttributeError):
                    require_patient_orientation(ds, test_orient)

            else:
                with pytest.raises(ValueError):
                    require_patient_orientation(ds, test_orient)


@pytest.mark.pydicom
def test_sum_doses_in_datasets():

    data1 = np.array([[[30, 20], [10, 5]], [[40, 25], [15, 8]]], dtype=np.uint32) * int(
        1e6
    )
    scale1 = 1e-8

    data2 = np.array(
        [[[350, 400], [450, 475]], [[300, 375], [425, 460]]], dtype=np.uint32
    ) * int(1e6)
    scale2 = 2e-9

    expected_sum = np.ones((2, 2, 2))

    test_dicom_dict = {
        "PatientID": "PMP",
        "Modality": "RTDOSE",
        "ImagePositionPatient": [-1.0, -1.0, -1.0],
        "ImageOrientationPatient": [1, 0, 0, 0, 1, 0],
        "BitsAllocated": 32,
        "Rows": 2,
        "Columns": 2,
        "PixelRepresentation": 0,
        "SamplesPerPixel": 1,
        "PhotometricInterpretation": "MONOCHROME2",
        "PixelSpacing": [2.0, 2.0],
        "GridFrameOffsetVector": [0.0, 2.0],
        "PixelData": data1.tobytes(),
        "DoseGridScaling": scale1,
        "DoseSummationType": "PLAN",
        "DoseType": "PHYSICAL",
        "DoseUnits": "GY",
    }

    ds1 = dicom_dataset_from_dict(test_dicom_dict, ensure_file_meta=True)

    ds2 = copy.deepcopy(ds1)
    ds2.PixelData = data2.tobytes()
    ds2.DoseGridScaling = scale2

    ds_summed = sum_doses_in_datasets([ds1, ds2])
    assert np.allclose(dose_from_dataset(ds_summed), expected_sum)
    assert ds_summed.DoseType == "PHYSICAL"

    # Effective dose type:
    ds2.DoseType = "EFFECTIVE"
    ds_summed = sum_doses_in_datasets([ds1, ds2])
    assert ds_summed.DoseType == "EFFECTIVE"

    # More than two doses:
    ds_summed = sum_doses_in_datasets([ds1, ds1, ds2, ds2])
    assert np.allclose(dose_from_dataset(ds_summed), 2 * expected_sum)

    # Unmatched patient IDs
    with pytest.raises(ValueError):
        ds2.PatientID = "PMX"
        sum_doses_in_datasets([ds1, ds2])
    ds2.PatientID = "PMP"

    # Bad modality
    with pytest.raises(ValueError):
        ds2.Modality = "CT"
        sum_doses_in_datasets([ds1, ds2])
    ds2.Modality = "RTDOSE"

    # Nothing supplied:
    with pytest.raises(IndexError):
        sum_doses_in_datasets([])

    # BEAM dose present:
    with pytest.raises(ValueError):
        ds2.DoseSummationType = "BEAM"
        sum_doses_in_datasets([ds1, ds2])
    ds2.DoseSummationType = "PLAN"

    # Bad dose units
    with pytest.raises(ValueError):
        ds2.DoseUnits = "RELATIVE"
        sum_doses_in_datasets([ds1, ds2])
    ds2.Modality = "GY"

    # Unmatched coords
    with pytest.raises(ValueError):
        ds2.ImagePositionPatient = [-1, -1.1, -1]
        sum_doses_in_datasets([ds1, ds2])
    ds2.ImagePositionPatient = [-1, -1, -1]
