import json
from os.path import abspath, dirname
from os.path import join as pjoin

import numpy as np

import pydicom

import pymedphys
from pymedphys._dicom.coords import xyz_axes_from_dataset

ORIENTATIONS_SUPPORTED = ["FFDL", "FFDR", "FFP", "FFS", "HFDL", "HFDR", "HFP", "HFS"]


def get_file_from_zenodo(filename):
    dose_data_files = pymedphys.zip_data_paths("dicom_dose_test_data.zip")
    path_match = [path for path in dose_data_files if path.name == filename]

    assert len(path_match) == 1

    return path_match[0]


def get_data_file(orientation_key):
    return get_file_from_zenodo(
        "RD.DICOMORIENT.Dose_{}_empty.dcm".format(orientation_key)
    )


def run_xyz_function_tests(coord_system):
    r"""Run the xyz extraction test sequence for a given
    xyz extraction function"""

    expected_xyz_path = get_file_from_zenodo(
        "expected_{}_xyz.json".format(coord_system.lower())
    )

    with open(expected_xyz_path) as fp:
        expected_xyz = json.load(fp)

    assert set(expected_xyz.keys()) == set(ORIENTATIONS_SUPPORTED)

    test_ds_dict = {
        key: pydicom.dcmread(get_data_file(key)) for key in ORIENTATIONS_SUPPORTED
    }

    for orient, dicom in test_ds_dict.items():
        test_xyz = xyz_axes_from_dataset(dicom, coord_system)

        expected_xyz[orient] = np.array(expected_xyz[orient])
        assert np.array_equal(test_xyz[0], expected_xyz[orient][0])
        assert np.array_equal(test_xyz[1], expected_xyz[orient][1])
        assert np.array_equal(test_xyz[2], expected_xyz[orient][2])


def test_extract_iec_patient_xyz():
    run_xyz_function_tests("PATIENT")


def test_extract_iec_fixed_xyz():
    run_xyz_function_tests("FIXED")


def test_extract_dicom_patient_xyz():
    run_xyz_function_tests("DICOM")
