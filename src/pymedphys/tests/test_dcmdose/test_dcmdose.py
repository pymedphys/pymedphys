import pydicom as dcm
import numpy as np
from pymedphys.dcm import load_xyz_from_dicom

class TestDcmDose():

    def test_load_xyz_from_dicom_coordinates(self):
        # TODO: read in HFS, HFP, FFS and FFP skeleton dcm dose files using pydicom

        # TODO: run load_xyz_from_dicom() on each file and compare x, y and z coordinate arrays to expected values
            # What values to use as expected?
                # Use a commercial DICOM RT Dose display tool?
                # What if coordinate system

        return
