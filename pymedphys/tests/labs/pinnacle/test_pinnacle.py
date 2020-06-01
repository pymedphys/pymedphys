# Copyright (C) 2019 South Western Sydney Local Health District,
# University of New South Wales

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This work is derived from:
# https://github.com/AndrewWAlexander/Pinnacle-tar-DICOM
# which is released under the following license:

# Copyright (c) [2017] [Colleen Henschel, Andrew Alexander]

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# pylint: disable = redefined-outer-name

import os
import tempfile
from zipfile import ZipFile

import pytest

import numpy as np

import pydicom

from pymedphys._data import download
from pymedphys.labs.pinnacle import PinnacleExport

working_path = tempfile.mkdtemp()
data_path = os.path.join(working_path, "data")


def get_online_data(filename):
    return download.get_file_within_data_zip("pinnacle_test_data.zip", filename)


@pytest.fixture(scope="session")
def data():

    zip_ref = ZipFile(get_online_data("pinnacle_16.0_test_data.zip"), "r")
    zip_ref.extractall(data_path)
    zip_ref.close()

    return data_path


@pytest.fixture
def pinn(data):

    pinn_objs = []

    for d in os.listdir(data):
        pinn_dir = os.path.join(data, d, "Pinnacle")
        for pat_dir in os.listdir(pinn_dir):
            pinn_objs.append(PinnacleExport(os.path.join(pinn_dir, pat_dir), None))

    return pinn_objs


@pytest.mark.slow
def test_pinnacle(pinn):

    for p in pinn:
        plans = p.plans
        assert len(plans) == 1


def find_corresponding_dicom(dcm):

    for root, _, files in os.walk(data_path):

        dicom_files = [f for f in files if f.endswith(".dcm")]
        for f in dicom_files:

            dcm_file = os.path.join(root, f)
            ds = pydicom.read_file(dcm_file)

            if ds.PatientID == dcm.PatientID and ds.Modality == dcm.Modality:

                if ds.Modality == "CT":
                    # Also match the SliceLocation
                    if not ds.SliceLocation == dcm.SliceLocation:
                        continue
                return ds

    return None


@pytest.mark.slow
@pytest.mark.pydicom
def test_ct(pinn):

    for p in pinn:
        export_path = os.path.join(
            working_path, "output", p.patient_info["MedicalRecordNumber"], "CT"
        )
        os.makedirs(export_path)

        export_plan = p.plans[0]

        p.export_image(export_plan.primary_image, export_path=export_path)

        # Get the exported CT file
        for f in os.listdir(export_path):
            if f.startswith("CT"):
                exported_ct = pydicom.read_file(os.path.join(export_path, f))
                assert exported_ct.Modality == "CT"

                # Get the ground truth CT file
                pinn_ct = find_corresponding_dicom(exported_ct)
                assert pinn_ct is not None

                # Some (very) basic sanity checks
                assert pinn_ct.PatientID == exported_ct.PatientID
                assert pinn_ct.SliceLocation == exported_ct.SliceLocation

                # Get the image data
                exported_img = exported_ct.pixel_array.astype(np.int16)
                pinn_img = pinn_ct.pixel_array.astype(np.int16)

                # Ensure images are the same size
                assert exported_img.shape == pinn_img.shape

                # Make sure the absolute difference is (close to) zero
                assert np.allclose(exported_img, pinn_img, atol=0.00001)


@pytest.mark.slow
def test_struct(pinn):

    for p in pinn:
        export_path = os.path.join(
            working_path, "output", p.patient_info["MedicalRecordNumber"], "RTSTRUCT"
        )
        os.makedirs(export_path)

        export_plan = p.plans[0]

        p.export_struct(export_plan, export_path=export_path)

        # Get the exported struct file
        for f in os.listdir(export_path):
            if f.startswith("RS"):
                exported_struct = pydicom.read_file(os.path.join(export_path, f))
                assert exported_struct.Modality == "RTSTRUCT"

        # Get the ground truth RTSTRUCT file
        pinn_struct = find_corresponding_dicom(exported_struct)
        assert pinn_struct is not None

        assert len(pinn_struct.StructureSetROISequence) == len(
            exported_struct.StructureSetROISequence
        )

        for s1, s2 in zip(
            pinn_struct.StructureSetROISequence, exported_struct.StructureSetROISequence
        ):
            assert s1.ROIName == s2.ROIName

        # TODO: Generate a mask for each contour and do a comparison of these


@pytest.mark.slow
@pytest.mark.pydicom
def test_dose(pinn):

    for p in pinn:
        export_path = os.path.join(
            working_path, "output", p.patient_info["MedicalRecordNumber"], "RTDOSE"
        )
        os.makedirs(export_path)

        export_plan = p.plans[0]

        p.export_dose(export_plan, export_path)

        # Get the exported RTDOSE file
        for f in os.listdir(export_path):
            if f.startswith("RD"):
                exported_dose = pydicom.read_file(os.path.join(export_path, f))
                assert exported_dose.Modality == "RTDOSE"
                break

        # Get the ground truth RTDOSE file
        pinn_dose = find_corresponding_dicom(exported_dose)
        assert pinn_dose is not None

        # Get the dose volumes
        exported_vol = exported_dose.pixel_array.astype(np.int16)
        pinn_vol = pinn_dose.pixel_array.astype(np.int16)

        # Ensure dose volumes are the same size
        assert exported_vol.shape == pinn_vol.shape

        # Apply dose grid scaling
        exported_vol = exported_vol * exported_dose.DoseGridScaling
        pinn_vol = pinn_vol * pinn_dose.DoseGridScaling

        # Make sure the maximum values are in the same locations
        assert exported_vol.argmax() == pinn_vol.argmax()

        # Make sure the absolute difference is (close to) zero
        assert np.allclose(exported_vol, pinn_vol, atol=0.01)


@pytest.mark.slow
@pytest.mark.pydicom
def test_plan(pinn):

    for p in pinn:
        export_path = os.path.join(
            working_path, "output", p.patient_info["MedicalRecordNumber"], "RTPLAN"
        )
        os.makedirs(export_path)

        export_plan = p.plans[0]

        p.export_plan(export_plan, export_path)

        # Get the exported RTPLAN file
        for f in os.listdir(export_path):
            if f.startswith("RP"):
                exported_plan = pydicom.read_file(os.path.join(export_path, f))
                assert exported_plan.Modality == "RTPLAN"
                break

        # Get the ground truth RTDOSE file
        pinn_plan = find_corresponding_dicom(exported_plan)
        assert pinn_plan is not None

        assert pinn_plan.RTPlanName == exported_plan.RTPlanName
        assert pinn_plan.RTPlanLabel == exported_plan.RTPlanLabel

        # TODO The RTPLAN export isn't fully functional yet, so we need
        # to test more as we add that functionality
