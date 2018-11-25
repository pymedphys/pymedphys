import pydicom as dcm
import numpy as np
from pymedphys.dcm import load_xyz_from_dicom


class TestDcmDose():

    def test_load_xyz_from_dicom(self):
        expected_coords = {'FFDL': 'he'}

        test_dcms = {}
        test_dcms['FFDL'] = dcm.dcmread(
            "../data/dcmdose/RD.DICOMORIENT.Dose_FFDL.dcm")
        test_dcms['FFDR'] = dcm.dcmread(
            "../data/dcmdose/RD.DICOMORIENT.Dose_FFDR.dcm")
        test_dcms['FFP'] = dcm.dcmread(
            "../data/dcmdose/RD.DICOMORIENT.Dose_FFP.dcm")
        test_dcms['FFS'] = dcm.dcmread(
            "../data/dcmdose/RD.DICOMORIENT.Dose_FFS.dcm")
        test_dcms['HFDL'] = dcm.dcmread(
            "../data/dcmdose/RD.DICOMORIENT.Dose_HFDL.dcm")
        test_dcms['HFDR'] = dcm.dcmread(
            "../data/dcmdose/RD.DICOMORIENT.Dose_HFDR.dcm")
        test_dcms['HFP'] = dcm.dcmread(
            "../data/dcmdose/RD.DICOMORIENT.Dose_HFP.dcm")
        test_dcms['HFS'] = dcm.dcmread(
            "../data/dcmdose/RD.DICOMORIENT.Dose_HFS.dcm")

        for orient, d in test_dcms.items():
            x, y, z = load_xyz_from_dicom(d)
            print(x)
            print(y)
            print(z)
            break

        # TODO: run load_xyz_from_dicom() on each file and compare x, y and z coordinate arrays to expected values
            # What values to use as expected?
            # Use a commercial DICOM RT Dose display tool?
            # What if coordinate system is incorrectly configured in software?

        return


if __name__ == "__main__":
    tdd = TestDcmDose()
    tdd.test_load_xyz_from_dicom()
