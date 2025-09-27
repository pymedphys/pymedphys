# Copyright (C) 2019 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.create import dicom_dataset_from_dict


@pytest.mark.pydicom
def test_dicom_from_dict():
    baseline_dataset = pydicom.Dataset()
    baseline_dataset.Manufacturer = "PyMedPhys"
    beam_sequence = pydicom.Dataset()
    beam_sequence.Manufacturer = "PyMedPhys"
    baseline_dataset.BeamSequence = [beam_sequence]

    created_dataset = dicom_dataset_from_dict(
        {"Manufacturer": "PyMedPhys", "BeamSequence": [{"Manufacturer": "PyMedPhys"}]}
    )

    assert created_dataset == baseline_dataset


@pytest.mark.pydicom
def test_dicom_from_dict_transfer_syntax():
    """Test that ensure_transfer_syntax is properly applied when creating datasets."""
    # Test 1: Dataset without any transfer syntax settings
    dataset1 = dicom_dataset_from_dict({"PatientName": "Test^Patient"})
    
    # Verify that file_meta and TransferSyntaxUID are set
    assert hasattr(dataset1, "file_meta")
    assert hasattr(dataset1.file_meta, "TransferSyntaxUID")
    assert dataset1.file_meta.TransferSyntaxUID == pydicom.uid.ImplicitVRLittleEndian
    assert dataset1.is_implicit_VR is True
    assert dataset1.is_little_endian is True
    
    # Test 2: Dataset with template that has different settings
    template = pydicom.Dataset()
    template.is_implicit_VR = False
    template.is_little_endian = True
    
    dataset2 = dicom_dataset_from_dict(
        {"PatientName": "Test^Patient"}, template_ds=template
    )
    
    # Verify the appropriate TransferSyntaxUID is set based on template settings
    assert dataset2.file_meta.TransferSyntaxUID == pydicom.uid.ExplicitVRLittleEndian
    assert dataset2.is_implicit_VR is False
    assert dataset2.is_little_endian is True


@pytest.mark.pydicom
def test_dicom_from_dict_missing_transfer_syntax():
    """Test that datasets missing transfer syntax info get defaults applied."""
    # Create a dataset with no transfer syntax metadata
    dataset = dicom_dataset_from_dict({
        "PatientID": "12345",
        "StudyDate": "20230101",
        "Modality": "CT"
    })
    
    # Ensure defaults are applied
    assert hasattr(dataset, "file_meta")
    assert hasattr(dataset.file_meta, "TransferSyntaxUID")
    # Default should be Implicit VR Little Endian
    assert dataset.file_meta.TransferSyntaxUID == pydicom.uid.ImplicitVRLittleEndian


@pytest.mark.pydicom
def test_dicom_from_dict_with_existing_file_meta():
    """Test that existing file_meta is preserved when provided via template."""
    template = pydicom.Dataset()
    template.file_meta = pydicom.dataset.FileMetaDataset()
    template.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRBigEndian
    template.is_implicit_VR = False
    template.is_little_endian = False
    
    dataset = dicom_dataset_from_dict(
        {"SeriesDescription": "Test Series"}, template_ds=template
    )
    
    # Verify the TransferSyntaxUID is preserved from template
    assert dataset.file_meta.TransferSyntaxUID == pydicom.uid.ExplicitVRBigEndian
    assert dataset.is_implicit_VR is False
    assert dataset.is_little_endian is False
