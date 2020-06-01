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

"""A test suite for the DICOM RT Dose toolbox."""

import json
from os.path import abspath, dirname
from os.path import join as pjoin
from zipfile import ZipFile

import pytest

import numpy as np

import pydicom

import pymedphys
from pymedphys._data import download
from pymedphys._dicom.collection import DicomDose
from pymedphys._dicom.dose import require_patient_orientation_be_HFS

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
def test_require_patient_orientation_be_HFS():
    test_ds_dict = {
        key: pydicom.dcmread(test_coords.get_data_file(key))
        for key in ORIENTATIONS_SUPPORTED
    }

    ds_no_orient = pydicom.dcmread(
        str(pymedphys.data_path("example_structures.dcm")), force=True
    )

    test_ds_dict["no orient"] = ds_no_orient

    for orient, ds in test_ds_dict.items():
        if orient == "HFS":
            require_patient_orientation_be_HFS(ds)

        elif orient == "no orient":
            with pytest.raises(AttributeError) as ea:
                require_patient_orientation_be_HFS(ds)
            assert "object has no attribute 'ImageOrientationPatient'" in str(ea.value)

        else:
            with pytest.raises(ValueError) as ev:
                require_patient_orientation_be_HFS(ds)
            assert (
                "The supplied dataset has a patient orientation "
                "other than head-first supine" in str(ev.value)
            )
