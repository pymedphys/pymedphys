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


def _create_template_from_setup(template_setup):
    """Helper to create template dataset from setup configuration."""
    if not template_setup:
        return None
        
    template = pydicom.Dataset()
    if "is_implicit_VR" in template_setup:
        template.is_implicit_VR = template_setup["is_implicit_VR"]
    if "is_little_endian" in template_setup:
        template.is_little_endian = template_setup["is_little_endian"]
    if "transfer_syntax_uid" in template_setup:
        template.file_meta = pydicom.dataset.FileMetaDataset()
        template.file_meta.TransferSyntaxUID = template_setup["transfer_syntax_uid"]
    if "invalid_ts" in template_setup and template_setup["invalid_ts"]:
        template.file_meta = pydicom.dataset.FileMetaDataset()
        template.file_meta.TransferSyntaxUID = "INVALID_TRANSFER_SYNTAX"
    return template


@pytest.mark.pydicom
@pytest.mark.parametrize(
    "input_dict,template_setup,expected_transfer_syntax_uid,expected_is_implicit_vr,expected_is_little_endian",
    [
        # Test 1: Dataset without any transfer syntax settings
        (
            {"PatientName": "Test^Patient"},
            None,
            pydicom.uid.ImplicitVRLittleEndian,
            True,
            True,
        ),
        # Test 2: Dataset with template that has different settings
        (
            {"PatientName": "Test^Patient"},
            {"is_implicit_VR": False, "is_little_endian": True},
            pydicom.uid.ExplicitVRLittleEndian,
            False,
            True,
        ),
        # Test 3: Missing transfer syntax metadata
        (
            {"PatientID": "12345", "StudyDate": "20230101", "Modality": "CT"},
            None,
            pydicom.uid.ImplicitVRLittleEndian,
            True,
            True,
        ),
        # Test 4: Existing file_meta preserved from template
        (
            {"SeriesDescription": "Test Series"},
            {
                "is_implicit_VR": False,
                "is_little_endian": False,
                "transfer_syntax_uid": pydicom.uid.ExplicitVRBigEndian,
            },
            pydicom.uid.ExplicitVRBigEndian,
            False,
            False,
        ),
        # Test 5: Conflicting transfer syntax values (implicit VR but big endian is retired)
        (
            {"PatientID": "54321", "StudyDate": "20231231", "Modality": "MR"},
            {"is_implicit_VR": True, "is_little_endian": False},
            pydicom.uid.ExplicitVRBigEndian,  # ensure_transfer_syntax handles this by using False,False mapping
            False,
            False,
        ),
        # Test 6: Invalid transfer syntax value in template (keeps the invalid value)
        (
            {"PatientID": "67890", "StudyDate": "20231111", "Modality": "US"},
            {"invalid_ts": True},
            "INVALID_TRANSFER_SYNTAX",  # Invalid value is preserved
            False,  # Default from ensure_transfer_syntax
            True,  # Default from ensure_transfer_syntax
        ),
        # Test 7: file_meta missing in both input and template
        (
            {},  # Empty dict
            None,  # No template
            pydicom.uid.ImplicitVRLittleEndian,  # Default from ensure_transfer_syntax
            True,  # Default from ensure_transfer_syntax
            True,  # Default from ensure_transfer_syntax
        ),
    ],
)
def test_dicom_from_dict_transfer_syntax(
    input_dict,
    template_setup,
    expected_transfer_syntax_uid,
    expected_is_implicit_vr,
    expected_is_little_endian,
):
    """Test that ensure_transfer_syntax is properly applied when creating datasets."""
    template = _create_template_from_setup(template_setup)
    dataset = dicom_dataset_from_dict(input_dict, template_ds=template)

    # Verify that file_meta and TransferSyntaxUID are set
    assert hasattr(dataset, "file_meta")
    assert hasattr(dataset.file_meta, "TransferSyntaxUID")
    assert dataset.file_meta.TransferSyntaxUID == expected_transfer_syntax_uid
    assert dataset.is_implicit_VR is expected_is_implicit_vr
    assert dataset.is_little_endian is expected_is_little_endian


@pytest.mark.pydicom
def test_pinnacle_rtstruct_transfer_syntax():
    """Test that RTStruct files created via Pinnacle export have proper transfer syntax."""
    # This test verifies that the convert_struct workflow properly applies
    # ensure_transfer_syntax to the created dataset
    from pymedphys._dicom.compat import ensure_transfer_syntax
    
    # Create a mock dataset similar to what convert_struct creates
    file_meta = pydicom.dataset.FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.481.3"  # RT Structure Set
    file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    file_meta.ImplementationClassUID = pydicom.uid.generate_uid()
    
    # Create dataset without transfer syntax
    ds = pydicom.dataset.FileDataset(
        "test.dcm", {}, file_meta=file_meta, preamble=b"\x00" * 128
    )
    
    # Apply ensure_transfer_syntax like convert_struct does
    ensure_transfer_syntax(ds)
    
    # Verify transfer syntax was set properly
    assert hasattr(ds.file_meta, "TransferSyntaxUID")
    assert ds.file_meta.TransferSyntaxUID == pydicom.uid.ImplicitVRLittleEndian
    assert ds.is_implicit_VR is True
    assert ds.is_little_endian is True
