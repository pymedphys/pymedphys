import json
from os.path import abspath, dirname, join as pjoin

import numpy as np
import pydicom

from pymedphys._dicom.coords import xyz_axes_from_dataset

HERE = dirname(abspath(__file__))
DATA_DIRECTORY = pjoin(HERE, "data", "dose")
ORIENTATIONS_SUPPORTED = ["FFDL", "FFDR", "FFP", "FFS", "HFDL", "HFDR", "HFP", "HFS"]


def get_data_file(orientation_key):
    r"""Read in test DICOM files"""
    filename = "RD.DICOMORIENT.Dose_{}_empty.dcm".format(orientation_key)
    return pjoin(DATA_DIRECTORY, filename)


def run_xyz_function_tests(coord_system, save_new_baseline=False):
    r"""Run the xyz extraction test sequence for a given
    xyz extraction function"""

    print_ = True

    expected_xyz_filename = "expected_{}_xyz.json".format(coord_system.lower())

    if save_new_baseline:
        expected_xyz = {}
    else:
        with open(pjoin(DATA_DIRECTORY, expected_xyz_filename)) as fp:
            expected_xyz = json.load(fp)

        assert set(expected_xyz.keys()) == set(ORIENTATIONS_SUPPORTED)

    test_ds_dict = {
        key: pydicom.dcmread(get_data_file(key)) for key in ORIENTATIONS_SUPPORTED
    }
    print()
    for orient, dicom in test_ds_dict.items():
        test_xyz = xyz_axes_from_dataset(dicom, coord_system)

        if save_new_baseline or print_:
            print(orient)
            print("{}, {}".format(test_xyz[0][0], test_xyz[0][-1]))
            print("{}, {}".format(test_xyz[1][0], test_xyz[1][-1]))
            print("{}, {}\n".format(test_xyz[2][0], test_xyz[2][-1]))

            # tolist() required for jsonification
            test_xyz = tuple([axis.tolist() for axis in test_xyz])
            expected_xyz[orient] = test_xyz
        else:
            expected_xyz[orient] = np.array(expected_xyz[orient])
            assert np.array_equal(test_xyz[0], expected_xyz[orient][0])
            assert np.array_equal(test_xyz[1], expected_xyz[orient][1])
            assert np.array_equal(test_xyz[2], expected_xyz[orient][2])

    if save_new_baseline:
        save_xyz_baseline(expected_xyz_filename, expected_xyz)


def save_xyz_baseline(filename, xyz_dict):
    r"""Save a new baseline for any of the coordinate extraction functions.

    `xyz_dict` should have key : value in the following form:
    <orientation string> : (x, y, z)
    """
    tuples_are_correct_length = True

    for val in xyz_dict.values():
        if len(val) != 3:
            tuples_are_correct_length = False

    if not filename.endswith(".json"):
        raise ValueError('Filename must end in ".json"')

    elif not set(xyz_dict.keys()) == set(ORIENTATIONS_SUPPORTED):
        raise ValueError(
            "xyz baselines must be provided for "
            "all eight supported patient orientations"
        )

    elif not tuples_are_correct_length:
        raise ValueError(
            "Each orientation's new baseline must be a tuple"
            "of length 3 containing x, y and z values"
        )

    else:
        with open(pjoin(DATA_DIRECTORY, filename), "w") as fp:
            json.dump(xyz_dict, fp)


def test_extract_iec_patient_xyz():
    run_xyz_function_tests("PATIENT")


def test_extract_iec_fixed_xyz():
    run_xyz_function_tests("FIXED")


def test_extract_dicom_patient_xyz():
    run_xyz_function_tests("DICOM")
