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

"""A test suite for the DICOM RT Dose toolbox."""
import json
import uuid
from os import remove
from os.path import abspath, basename, dirname, join as pjoin
from zipfile import ZipFile

import numpy as np
import pydicom as dcm

from pymedphys_dicom.dicom import (
    DicomDose,
    xyz_from_dataset)

HERE = dirname(abspath(__file__))
DATA_DIRECTORY = pjoin(HERE, 'data', 'dose')
ORIENTATIONS_SUPPORTED = ['FFDL', 'FFDR', 'FFP', 'FFS',
                          'HFDL', 'HFDR', 'HFP', 'HFS']


def get_data_file(orientation_key):
    r"""Read in test DICOM files"""
    filename = 'RD.DICOMORIENT.Dose_{}_empty.dcm'.format(orientation_key)
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

    test_ds_dict = {key: dcm.dcmread(get_data_file(key))
                    for key in ORIENTATIONS_SUPPORTED}
    print()
    for orient, dicom in test_ds_dict.items():
        test_xyz = xyz_from_dataset(dicom, coord_system)

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
    run_xyz_function_tests('PATIENT')


def test_extract_iec_fixed_xyz():
    run_xyz_function_tests('FIXED')


def test_extract_dicom_patient_xyz():
    run_xyz_function_tests('DICOM')


def test_DicomDose_constancy():
    save_new_baseline = False

    wedge_basline_filename = "wedge_dose_baseline.json"

    baseline_dicom_dose_dict_filepath = pjoin(
        DATA_DIRECTORY, wedge_basline_filename)
    baseline_dicom_dose_dict_zippath = pjoin(
        DATA_DIRECTORY, "lfs-wedge_dose_baseline.zip")

    test_dicom_dose_filepath = pjoin(DATA_DIRECTORY, "RD.wedge.dcm")
    test_dicom_dose = DicomDose.from_file(test_dicom_dose_filepath)

    if save_new_baseline:
        # tolist() required for jsonification
        expected_dicom_dose_dict = {
            'values': test_dicom_dose.values.tolist(),
            'units': test_dicom_dose.units,
            'x': test_dicom_dose.x.tolist(),
            'y': test_dicom_dose.y.tolist(),
            'z': test_dicom_dose.z.tolist(),
            'coords': test_dicom_dose.coords.tolist(),
            'mask': test_dicom_dose.mask
        }
        with open(baseline_dicom_dose_dict_filepath, 'w') as fp:
            json.dump(expected_dicom_dose_dict, fp)
        ZipFile(baseline_dicom_dose_dict_zippath, 'w').write(baseline_dicom_dose_dict_filepath,
                                                             basename(baseline_dicom_dose_dict_filepath))
        remove(baseline_dicom_dose_dict_filepath)
    else:
        with ZipFile(baseline_dicom_dose_dict_zippath, 'r') as zip_ref:
            with zip_ref.open(wedge_basline_filename) as a_file:
                expected_dicom_dose_dict = json.load(a_file)

        assert np.allclose(test_dicom_dose.values, np.array(
            expected_dicom_dose_dict['values']))
        assert test_dicom_dose.units == expected_dicom_dose_dict['units']
        assert np.allclose(test_dicom_dose.x, np.array(
            expected_dicom_dose_dict['x']))
        assert np.allclose(test_dicom_dose.y, np.array(
            expected_dicom_dose_dict['y']))
        assert np.allclose(test_dicom_dose.z, np.array(
            expected_dicom_dose_dict['z']))
        assert np.allclose(test_dicom_dose.coords, np.array(
            expected_dicom_dose_dict['coords']))
