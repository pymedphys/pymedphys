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
import os

import pytest

import numpy as np

import pydicom as dcm
from pymedphys.dcm import *

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIRECTORY = os.path.join(os.path.dirname(HERE), 'data', 'dcmdose')


def get_data_file(orientation_key):
    r"""Read in test DICOM files"""
    filename = 'RD.DICOMORIENT.Dose_{}.dcm'.format(orientation_key)
    return os.path.join(DATA_DIRECTORY, filename)


def run_coords_function_tests(coords_function):
    r"""Run the coordinate extraction test sequence for a given
    coordinate extraction function"""

    expected_coords_filename = "expected_{}.npy".format(
        '_'.join(coords_function.__name__.split('_')[1:]))

    expected_coords = np.load(os.path.join(
        DATA_DIRECTORY, expected_coords_filename)).item()

    assert (set(expected_coords.keys()) == set(['FFDL', 'FFDR', 'FFP', 'FFS',
                                                'HFDL', 'HFDR', 'HFP', 'HFS']))

    test_dcms = {key: dcm.dcmread(get_data_file(key))
                 for key in expected_coords}

    for orient, dicom in test_dcms.items():
        test_coords = coords_function(dicom)

        # print(orient)
        # print("{}, {}".format(test_coords.x[0], test_coords.x[-1]))
        # print("{}, {}".format(test_coords.y[0], test_coords.y[-1]))
        # print("{}, {}\n".format(test_coords.z[0], test_coords.z[-1]))

        # For baseline saving only!
        # expected_coords[orient] = test_coords

        assert np.array_equal(test_coords.x, expected_coords[orient].x)
        assert np.array_equal(test_coords.y, expected_coords[orient].y)
        assert np.array_equal(test_coords.z, expected_coords[orient].z)

    # For baseline saving only!
    # save_coords_baseline(expected_coords_filename, expected_coords)


def save_coords_baseline(filename, coords_dict):
    r"""Save a new baseline for any of the coordinate extraction functions.

    `coords_dict` should have key : value in the following form:
    <orientation string> : (x_coords, y_coords, z_coords)
    """
    tuples_are_correct_length = True

    for val in coords_dict.values():
        if len(val) != 3:
            tuples_are_correct_length = False

    if not filename.endswith(".npy"):
        raise ValueError("Filename must end in \".npy\"")

    elif not (set(coords_dict.keys()) == set(['FFDL', 'FFDR', 'FFP', 'FFS',
                                              'HFDL', 'HFDR', 'HFP', 'HFS'])):
        raise ValueError("Coordinate baselines must be provided for "
                         "all eight supported patient orientations")

    elif not tuples_are_correct_length:
        raise ValueError("Each orientation's new baseline must be a tuple"
                         "of length 3 containing x, y and z values")

    else:
        np.save(os.path.join(DATA_DIRECTORY, filename), coords_dict)


@pytest.mark.skip(reason=(
    "This test appears to have a dependency on the directory structure of "
    "pymedphys"))
def test_extract_iec_patient_coords():
    run_coords_function_tests(extract_iec_patient_coords)


@pytest.mark.skip(reason=(
    "This test appears to have a dependency on the directory structure of "
    "pymedphys"))
def test_extract_iec_fixed_coords():
    run_coords_function_tests(extract_iec_fixed_coords)


@pytest.mark.skip(reason=(
    "This test appears to have a dependency on the directory structure of "
    "pymedphys"))
def test_extract_dicom_patient_coords():
    run_coords_function_tests(extract_dicom_patient_coords)


def test_extract_dose():

    expected_dose = Dose(*np.load(os.path.join(
        DATA_DIRECTORY, "expected_wedge_dose.npy")))

    test_file = os.path.join(DATA_DIRECTORY, "RD.wedge.dcm")
    test_dcm = dcm.dcmread(test_file)

    test_dose = extract_dose(test_dcm)

    # Test - Constancy with wedge field baseline.
    assert(np.array_equal(test_dose.values, expected_dose.values))
    assert(test_dose.units == expected_dose.units)
    assert(test_dose.type == expected_dose.type)
    assert(test_dose.summation == expected_dose.summation)
    assert(test_dose.heterogeneity_correction
           == expected_dose.heterogeneity_correction)
