# Copyright (C) 2018 Matthew Jennings
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

"""A test suite for the DICOM RT Dose toolbox"""
import json
from os import remove
from os.path import abspath, basename, dirname, join as pjoin
from zipfile import ZipFile

import numpy as np
import pydicom as dcm

from pymedphys.dcm import (
    DicomDose,
    extract_iec_patient_xyz,
    extract_iec_fixed_xyz,
    extract_dicom_patient_xyz)

HERE = dirname(abspath(__file__))
DATA_DIRECTORY = pjoin(dirname(HERE), 'data', 'dcmdose')
ORIENTATIONS_SUPPORTED = ['FFDL', 'FFDR', 'FFP', 'FFS',
                          'HFDL', 'HFDR', 'HFP', 'HFS']


def get_data_file(orientation_key):
    r"""Read in test DICOM files"""
    filename = 'RD.DICOMORIENT.Dose_{}_empty.dcm'.format(orientation_key)
    return pjoin(DATA_DIRECTORY, filename)


def run_xyz_function_tests(xyz_function, save_new_baseline=False):
    r"""Run the xyz extraction test sequence for a given
    xyz extraction function"""

    expected_xyz_filename = "expected_{}.json".format(
        '_'.join(xyz_function.__name__.split('_')[1:]))

    if save_new_baseline:
        expected_xyz = {}
    else:
        with open(pjoin(DATA_DIRECTORY, expected_xyz_filename)) as fp:
            expected_xyz = json.load(fp)

        assert set(expected_xyz.keys()) == set(ORIENTATIONS_SUPPORTED)

    test_dcms = {key: dcm.dcmread(get_data_file(key))
                 for key in ORIENTATIONS_SUPPORTED}

    for orient, dicom in test_dcms.items():
        test_xyz = xyz_function(dicom)

        if save_new_baseline:
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
        raise ValueError("Filename must end in \".json\"")

    elif not set(xyz_dict.keys()) == set(ORIENTATIONS_SUPPORTED):
        raise ValueError("xyz baselines must be provided for "
                         "all eight supported patient orientations")

    elif not tuples_are_correct_length:
        raise ValueError("Each orientation's new baseline must be a tuple"
                         "of length 3 containing x, y and z values")

    else:
        with open(pjoin(DATA_DIRECTORY, filename), 'w') as fp:
            json.dump(xyz_dict, fp)


def test_extract_iec_patient_xyz():
    run_xyz_function_tests(extract_iec_patient_xyz)


def test_extract_iec_fixed_xyz():
    run_xyz_function_tests(extract_iec_fixed_xyz)


def test_extract_dicom_patient_xyz():
    run_xyz_function_tests(extract_dicom_patient_xyz)


def test_DicomDose_constancy():

    save_new_baseline = False

    baseline_dcmdose_dict_filepath = pjoin(DATA_DIRECTORY, "wedge_dose_baseline.json")
    baseline_dcmdose_dict_zippath = pjoin(DATA_DIRECTORY, "lfs-wedge_dose_baseline.zip")

    test_dcmdose_filepath = pjoin(DATA_DIRECTORY, "RD.wedge.dcm")
    test_dcmdose = DicomDose(test_dcmdose_filepath)

    if save_new_baseline:
        # tolist() required for jsonification
        expected_dcmdose_dict = {
            'values': test_dcmdose.values.tolist(),
            'units': test_dcmdose.units,
            'x': test_dcmdose.x.tolist(),
            'y': test_dcmdose.y.tolist(),
            'z': test_dcmdose.z.tolist(),
            'coords': test_dcmdose.coords.tolist(),
            'mask': test_dcmdose.mask
        }
        with open(baseline_dcmdose_dict_filepath, 'w') as fp:
            json.dump(expected_dcmdose_dict, fp)
        ZipFile(baseline_dcmdose_dict_zippath, 'w').write(baseline_dcmdose_dict_filepath,
                                                          basename(baseline_dcmdose_dict_filepath))
        remove(baseline_dcmdose_dict_filepath)
    else:
        with ZipFile(baseline_dcmdose_dict_zippath, 'r') as zip_ref:
            zip_ref.extractall(DATA_DIRECTORY)
        with open(baseline_dcmdose_dict_filepath, 'r') as fp:
            expected_dcmdose_dict = json.load(fp)
        remove(baseline_dcmdose_dict_filepath)
        assert np.allclose(test_dcmdose.values, np.array(expected_dcmdose_dict['values']))
        assert test_dcmdose.units == expected_dcmdose_dict['units']
        assert np.allclose(test_dcmdose.x, np.array(expected_dcmdose_dict['x']))
        assert np.allclose(test_dcmdose.y, np.array(expected_dcmdose_dict['y']))
        assert np.allclose(test_dcmdose.z, np.array(expected_dcmdose_dict['z']))
        assert np.allclose(test_dcmdose.coords, np.array(expected_dcmdose_dict['coords']))
