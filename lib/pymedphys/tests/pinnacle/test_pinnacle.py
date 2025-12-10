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
import numpy as np
import struct
import pytest

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._data import download
from pymedphys.pinnacle import PinnacleExport

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
@pytest.mark.pydicom
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


def assert_same_dose(dose_a, dose_b):
    # Check the same patient orientation
    assert dose_a.ImageOrientationPatient == dose_b.ImageOrientationPatient

    # Get the dose volumes
    exported_vol = dose_a.pixel_array.astype(np.int16)
    pinn_vol = dose_b.pixel_array.astype(np.int16)

    # Ensure dose volumes are the same size
    assert exported_vol.shape == pinn_vol.shape

    # Apply dose grid scaling
    exported_vol = exported_vol * dose_a.DoseGridScaling
    pinn_vol = pinn_vol * dose_b.DoseGridScaling

    # Make sure the maximum values are in the same locations
    assert exported_vol.argmax() == pinn_vol.argmax()

    # Make sure the absolute difference is (close to) zero
    assert np.allclose(exported_vol, pinn_vol, atol=0.01)


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

        assert_same_dose(pinn_dose, exported_dose)


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


@pytest.mark.slow
def test_missing_image():
    zip_ref = ZipFile(get_online_data("pinnacle_test_data_no_image.zip"), "r")
    zip_ref.extractall(data_path)
    zip_ref.close()

    pinn_path = os.path.join(data_path, "Pt3", "Pinnacle", "Patient_7430")
    pinn = PinnacleExport(pinn_path, None)

    # There is no image to export, so this line should fail gracefully and simply output
    # a warning to the logger
    pinn.export_image(pinn.plans[0].primary_image, export_path=".")


@pytest.fixture(scope="session")
def orientation_data():
    zip_ref = ZipFile(get_online_data("pinnacle_orientations_test_data.zip"), "r")

    zip_ref.extractall(data_path)
    zip_ref.close()

    return data_path


@pytest.fixture
def orientation_pinn(orientation_data):
    pinn_path = os.path.join(orientation_data, "pinnacle", "Patient_22902")

    pinn_obj = PinnacleExport(pinn_path, None)

    return pinn_obj


@pytest.mark.slow
@pytest.mark.pydicom
def test_dose_hfs(orientation_pinn):
    # Test exporting dose for patients in HFS position

    export_path = os.path.join(
        working_path, "output", "pinn_orientations", "RTDOSE", "HFS"
    )
    os.makedirs(export_path)

    export_plan = orientation_pinn.plans[0]

    orientation_pinn.export_dose(export_plan, export_path)

    # Get the exported RTDOSE file
    for f in os.listdir(export_path):
        if f.startswith("RD"):
            exported_dose = pydicom.read_file(os.path.join(export_path, f))
            assert exported_dose.Modality == "RTDOSE"
            break

    # Get the ground truth RTDOSE file
    gt_dose_file = "1.3.46.670589.13.997910418.20200707132626.548267.dcm"
    gt_dose_path = os.path.join(data_path, "dicom", "HFS", gt_dose_file)
    pinn_dose = pydicom.read_file(gt_dose_path)
    assert pinn_dose is not None

    assert_same_dose(exported_dose, pinn_dose)


@pytest.mark.slow
@pytest.mark.pydicom
def test_dose_hfp(orientation_pinn):
    # Test exporting dose for patients in HFP position

    export_path = os.path.join(
        working_path, "output", "pinn_orientations", "RTDOSE", "HFP"
    )
    os.makedirs(export_path)

    export_plan = orientation_pinn.plans[1]

    orientation_pinn.export_dose(export_plan, export_path)

    # Get the exported RTDOSE file
    for f in os.listdir(export_path):
        if f.startswith("RD"):
            exported_dose = pydicom.read_file(os.path.join(export_path, f))
            assert exported_dose.Modality == "RTDOSE"
            break

    # Get the ground truth RTDOSE file
    gt_dose_file = "1.3.46.670589.13.997910418.20200707132247.647011.dcm"
    gt_dose_path = os.path.join(data_path, "dicom", "HFP", gt_dose_file)
    pinn_dose = pydicom.read_file(gt_dose_path)
    assert pinn_dose is not None

    assert_same_dose(exported_dose, pinn_dose)


@pytest.mark.slow
@pytest.mark.pydicom
def test_dose_ffs(orientation_pinn):
    # Test exporting dose for patients in FFS position

    export_path = os.path.join(
        working_path, "output", "pinn_orientations", "RTDOSE", "FFS"
    )
    os.makedirs(export_path)

    export_plan = orientation_pinn.plans[2]

    orientation_pinn.export_dose(export_plan, export_path)

    # Get the exported RTDOSE file
    for f in os.listdir(export_path):
        if f.startswith("RD"):
            exported_dose = pydicom.read_file(os.path.join(export_path, f))
            assert exported_dose.Modality == "RTDOSE"
            break

    # Get the ground truth RTDOSE file
    gt_dose_file = "1.3.46.670589.13.997910418.20200707132449.572508.dcm"
    gt_dose_path = os.path.join(data_path, "dicom", "FFS", gt_dose_file)
    pinn_dose = pydicom.read_file(gt_dose_path)
    assert pinn_dose is not None

    assert_same_dose(exported_dose, pinn_dose)


@pytest.mark.slow
@pytest.mark.pydicom
def test_dose_ffp(orientation_pinn):
    # Test exporting dose for patients in FFP position

    export_path = os.path.join(
        working_path, "output", "pinn_orientations", "RTDOSE", "FFP"
    )
    os.makedirs(export_path)

    export_plan = orientation_pinn.plans[3]

    orientation_pinn.export_dose(export_plan, export_path)

    # Get the exported RTDOSE file
    for f in os.listdir(export_path):
        if f.startswith("RD"):
            exported_dose = pydicom.read_file(os.path.join(export_path, f))
            assert exported_dose.Modality == "RTDOSE"
            break

    # Get the ground truth RTDOSE file
    gt_dose_file = "1.3.46.670589.13.997910418.20200707132737.923688.dcm"
    gt_dose_path = os.path.join(data_path, "dicom", "FFP", gt_dose_file)
    pinn_dose = pydicom.read_file(gt_dose_path)
    assert pinn_dose is not None

    assert_same_dose(exported_dose, pinn_dose)

    @pytest.fixture
def temp_binary_file():
    """Fixture to create and cleanup temporary binary files"""
    files = []

    def _create_file(data):
        tf = tempfile.NamedTemporaryFile(delete=False)
        tf.write(data)
        tf.flush()
        tf.close()
        files.append(tf.name)
        return tf.name

    yield _create_file

    # Cleanup
    for f in files:
        if os.path.exists(f):
            os.unlink(f)


# Tests for construct_dose_from_binary
    @pytest.mark.array
def test_basic_dose_construction():
    """Test basic dose array construction from binary data"""
    # Create a 2x2x2 array
    array = np.zeros((2, 2, 2), dtype=np.float32)

    # Create binary data for 8 float values (2*2*2)
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    binary_data = b''.join(struct.pack(">f", v) for v in values)

    result = construct_dose_from_binary(binary_data, array)

    # Verify shape is preserved
    assert result.shape == (2, 2, 2)

    # Verify data is populated
    assert isinstance(result, np.ndarray)
    assert np.any(result != 0)

    @pytest.mark.array
def test_single_voxel_array():
    """Test with 1x1x1 array"""
    array = np.zeros((1, 1, 1), dtype=np.float32)
    binary_data = struct.pack(">f", 42.5)

    result = construct_dose_from_binary(binary_data, array)

    assert result[0, 0, 0] == 42.5

    @pytest.mark.array
def test_negative_values():
    """Test handling of negative dose values"""
    array = np.zeros((2, 1, 1), dtype=np.float32)
    binary_data = struct.pack(">f", -10.5) + struct.pack(">f", -20.3)

    result = construct_dose_from_binary(binary_data, array)

    assert result[0, 0, 0] == -10.5
    assert result[1, 0, 0] == -20.3

    @pytest.mark.array
def test_z_axis_reversal():
    """Test that z-axis is filled in reverse order"""
    array = np.zeros((1, 1, 3), dtype=np.float32)
    values = [1.0, 2.0, 3.0]
    binary_data = b''.join(struct.pack(">f", v) for v in values)

    result = construct_dose_from_binary(binary_data, array)

    # First value in binary should go to highest z index
    assert result[0, 0, 2] == 1.0
    assert result[0, 0, 1] == 2.0
    assert result[0, 0, 0] == 3.0

    @pytest.mark.array
def test_large_array():
    """Test with a larger array"""
    shape = (10, 10, 10)
    array = np.zeros(shape, dtype=np.float32)
    binary_data = b''.join(struct.pack(">f", float(i)) for i in range(1000))

    result = construct_dose_from_binary(binary_data, array)

    assert result.shape == shape
    assert np.any(result != 0)

    @pytest.mark.array
def test_exact_binary_size():
    """Test that binary data size matches array size"""
    array = np.zeros((2, 2, 2), dtype=np.float32)
    # Each float is 4 bytes, so 2*2*2*4 = 32 bytes
    binary_data = b''.join(struct.pack(">f", 1.0) for _ in range(8))

    result = construct_dose_from_binary(binary_data, array)

    assert len(binary_data) == 32
    assert result is not None

    @pytest.mark.array
def test_preserves_array_type():
    """Test that the returned array maintains float32 type"""
    array = np.zeros((2, 2, 2), dtype=np.float32)
    binary_data = b''.join(struct.pack(">f", 1.0) for _ in range(8))

    result = construct_dose_from_binary(binary_data, array)

    assert result.dtype == np.float32


# Tests for read_binary_data
    @pytest.mark.binary
def test_read_valid_binary_file(temp_binary_file):
    """Test reading a valid binary file with data"""
    test_data = struct.pack(">f", 1.5) + struct.pack(">f", 2.5)
    file_path = temp_binary_file(test_data)

    result = read_binary_data(file_path)

    assert result == test_data

    @pytest.mark.binary
def test_read_all_zeros_file(temp_binary_file):
    """Test that file with all zeros returns False"""
    test_data = b'\x00' * 16
    file_path = temp_binary_file(test_data)

    result = read_binary_data(file_path)

    assert result is False

    @pytest.mark.binary
def test_nonexistent_file():
    """Test handling of nonexistent file"""
    result = read_binary_data('/nonexistent/path/file.bin')

    assert result is None

    @pytest.mark.binary
def test_empty_file(temp_binary_file):
    """Test reading an empty file"""
    file_path = temp_binary_file(b'')

    result = read_binary_data(file_path)

    # Empty file has no bytes, so all() on empty sequence returns True
    # This means it will return False
    assert result is False

    @pytest.mark.binary
def test_mixed_zeros_and_data(temp_binary_file):
    """Test file with some zeros and some data"""
    test_data = b'\x00\x00\x01\x02'
    file_path = temp_binary_file(test_data)

    result = read_binary_data(file_path)

    # Should return data since not all bytes are zero
    assert result == test_data

    @pytest.mark.binary
def test_large_binary_file(temp_binary_file):
    """Test reading a larger binary file"""
    test_data = b''.join(struct.pack(">f", float(i)) for i in range(1000))
    file_path = temp_binary_file(test_data)

    result = read_binary_data(file_path)

    assert result == test_data
    assert len(result) == 4000  # 1000 floats * 4 bytes

    @pytest.mark.binary
def test_single_nonzero_byte(temp_binary_file):
    """Test file with single non-zero byte"""
    test_data = b'\x01'
    file_path = temp_binary_file(test_data)

    result = read_binary_data(file_path)

    assert result == test_data

    @pytest.mark.binary
def test_file_size_check(temp_binary_file):
    """Test that file size is correctly evaluated"""
    test_data = struct.pack(">f", 1.0) * 100
    file_path = temp_binary_file(test_data)

    result = read_binary_data(file_path)

    assert result is not None
    assert len(result) == 400  # 100 floats * 4 bytes
