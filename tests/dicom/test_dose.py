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
from os import remove
from os.path import abspath, basename, dirname
from os.path import join as pjoin
from zipfile import ZipFile

import pytest

import numpy as np

import pydicom

from pymedphys._dicom.collection import DicomDose
from pymedphys._dicom.dose import require_patient_orientation_be_HFS
from test_coords import get_data_file

HERE = dirname(abspath(__file__))
DATA_DIRECTORY = pjoin(HERE, "data", "dose")
ORIENTATIONS_SUPPORTED = ["FFDL", "FFDR", "FFP", "FFS", "HFDL", "HFDR", "HFP", "HFS"]


def test_DicomDose_constancy():
    save_new_baseline = False

    wedge_basline_filename = "wedge_dose_baseline.json"

    baseline_dicom_dose_dict_filepath = pjoin(DATA_DIRECTORY, wedge_basline_filename)
    baseline_dicom_dose_dict_zippath = pjoin(
        DATA_DIRECTORY, "lfs-wedge_dose_baseline.zip"
    )

    test_dicom_dose_filepath = pjoin(DATA_DIRECTORY, "RD.wedge.dcm")
    test_dicom_dose = DicomDose.from_file(test_dicom_dose_filepath)

    if save_new_baseline:
        # tolist() required for jsonification
        expected_dicom_dose_dict = {
            "values": test_dicom_dose.values.tolist(),
            "units": test_dicom_dose.units,
            "x": test_dicom_dose.x.tolist(),
            "y": test_dicom_dose.y.tolist(),
            "z": test_dicom_dose.z.tolist(),
            "coords": test_dicom_dose.coords.tolist(),
            "mask": test_dicom_dose.mask,
        }
        with open(baseline_dicom_dose_dict_filepath, "w") as fp:
            json.dump(expected_dicom_dose_dict, fp)
        ZipFile(baseline_dicom_dose_dict_zippath, "w").write(
            baseline_dicom_dose_dict_filepath,
            basename(baseline_dicom_dose_dict_filepath),
        )
        remove(baseline_dicom_dose_dict_filepath)
    else:
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


def test_require_patient_orientation_be_HFS():
    test_ds_dict = {
        key: pydicom.dcmread(get_data_file(key)) for key in ORIENTATIONS_SUPPORTED
    }

    ds_no_orient = pydicom.dcmread(
        pjoin(dirname(DATA_DIRECTORY), "struct", "example_structures.dcm"), force=True
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
