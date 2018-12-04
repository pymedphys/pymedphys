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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


import os

import numpy as np
import pydicom as dcm

from pymedphys.dcm import load_xyz_from_dicom

# Fixed the finding of the data files by referencing the path based on HERE
# variable
HERE = os.path.dirname(os.path.abspath(__file__))
print(HERE)
DATA_DIRECTORY = os.path.join(os.path.dirname(HERE), 'data', 'dcmdose')
print(DATA_DIRECTORY)


def get_data_file(orientation_key):
    filename = 'RD.DICOMORIENT.Dose_{}.dcm'.format(orientation_key)
    return os.path.join(DATA_DIRECTORY, filename)


class TestDcmDose():
   
    def test_load_xyz_from_dicom(self):
        expected_coords = {
            'FFDL': 'he',
            'FFDR': None,
            'FFP': None,
            'FFS': None,
            'HFDL': None,
            'HFDR': None,
            'HFP': None,
            'HFS': None
        }
       
        test_dcms = {
            key: dcm.dcmread(get_data_file(key))
            for key in expected_coords
        }
        
        for orient, d in test_dcms.items():
            x, y, z = load_xyz_from_dicom(d)
            print()
            print(orient)
            print(x)
            print(y)
            print(z)

        # TODO: run load_xyz_from_dicom() on each file and compare x, y and z coordinate arrays to expected values
            # What values to use as expected?
            # Use a commercial DICOM RT Dose display tool?
            # What if coordinate system is incorrectly configured in software?

        return

        
if __name__ == "__main__":
    TestDcmDose().test_load_xyz_from_dicom()
    