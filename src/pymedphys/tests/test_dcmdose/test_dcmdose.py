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


import os

import numpy as np
import pydicom as dcm

from pymedphys.dcm import load_xyz_from_dicom

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIRECTORY = os.path.join(os.path.dirname(HERE), 'data', 'dcmdose')


def get_data_file(orientation_key):
    filename = 'RD.DICOMORIENT.Dose_{}.dcm'.format(orientation_key)
    return os.path.join(DATA_DIRECTORY, filename)


def test_load_xyz_from_dicom():
    expected_coords = np.load(os.path.join(
        DATA_DIRECTORY, "expected_coords.npy")).item()

    assert (
        set(expected_coords.keys()) ==
        set([
            'FFDL', 'FFDR', 'FFP', 'FFS', 'HFDL', 'HFDR', 'HFP', 'HFS'
        ]))

    test_dcms = {
        key: dcm.dcmread(get_data_file(key))
        for key in expected_coords
    }

    for orient, dicom in test_dcms.items():
        x, y, z = load_xyz_from_dicom(dicom)

        assert np.array_equal(x, expected_coords[orient][0])
        assert np.array_equal(y, expected_coords[orient][1])
        assert np.array_equal(z, expected_coords[orient][2])
