# Copyright (C) 2025 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for structure set splitting functionality."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from pymedphys._imports import pydicom

import pymedphys
import pymedphys._utilities.test as pmp_test_utils
from pymedphys._dicom.create import dicom_dataset_from_dict
from pymedphys._dicom.structure.split import (
    RegistrationGenerator,
    StructureSetSplitter,
    split_structure_set_by_frame_of_reference,
)
from pymedphys._dicom.uid import generate_uid


@pytest.mark.pydicom
def test_structure_set_splitter_single_for():
    """Test that structure sets with single FOR are returned unchanged."""
    # Create a structure set with only one Frame of Reference
    for_uid = generate_uid()
    ds = create_test_structure_set(
        roi_data=[
            {"name": "ROI1", "number": 1, "for_uid": for_uid},
            {"name": "ROI2", "number": 2, "for_uid": for_uid},
        ]
    )
    
    splitter = StructureSetSplitter(ds)
    result = splitter.split()
    
    assert len(result) == 1
    assert result[0] == ds  # Should return original dataset unchanged


@pytest.mark.pydicom
def test_structure_set_splitter_multiple_for():
    """Test splitting structure set with multiple Frame of Reference UIDs."""
    for_uid1 = generate_uid()
    for_uid2 = generate_uid()
    
    ds = create_test_structure_set(
        roi_data=[
            {"name": "ROI1", "number": 1, "for_uid": for_uid1},
            {"name": "ROI2", "number": 2, "for_uid": for_uid1},
            {"name": "ROI3", "number": 3, "for_uid": for_uid2},
            {"name": "ROI4", "number": 4, "for_uid": for_uid2},
        ]
    )
    
    splitter = StructureSetSplitter(ds)
    result = splitter.split()
    
    assert len(result) == 2
    
    # Check first split
    roi_names_1 = [roi.ROIName for roi in result[0].StructureSetROISequence]
    assert set(roi_names_1) == {"ROI1", "ROI2"}
    
    # Check second split
    roi_names_2 = [roi.ROIName for roi in result[1].StructureSetROISequence]
    assert set(roi_names_2) == {"ROI3", "ROI4"}
    
    # Check that new SOP Instance UIDs were generated
    assert result[0].SOPInstanceUID != ds.SOPInstanceUID
    assert result[1].SOPInstanceUID != ds.SOPInstanceUID
    assert result[0].SOPInstanceUID != result[1].SOPInstanceUID


@pytest.mark.pydicom
def test_registration_generator():
    """Test generation of spatial registration objects."""
    for_uid1 = generate_uid()
    for_uid2 = generate_uid()
    for_uid3 = generate_uid()
    
    # Create three structure sets
    structure_sets = []
    for for_uid in [for_uid1, for_uid2, for_uid3]:
        ds = create_test_structure_set(
            roi_data=[{"name": "ROI", "number": 1, "for_uid": for_uid}]
        )
        structure_sets.append(ds)
    
    generator = RegistrationGenerator(structure_sets)
    registrations = generator.generate_registrations()
    
    # Should generate 3 registrations for 3 structure sets (3 choose 2)
    assert len(registrations) == 3
    
    # Check each registration
    for reg in registrations:
        assert reg.SOPClassUID == "1.2.840.10008.5.1.4.1.1.66.1"  # Spatial Registration
        assert reg.Modality == "REG"
        assert hasattr(reg, "RegistrationSequence")
        assert len(reg.RegistrationSequence) == 1
        
        reg_seq = reg.RegistrationSequence[0]
        assert hasattr(reg_seq, "MatrixRegistrationSequence")
        
        matrix_seq = reg_seq.MatrixRegistrationSequence[0]
        assert hasattr(matrix_seq, "MatrixSequence")
        
        matrix = matrix_seq.MatrixSequence[0]
        assert matrix.FrameOfReferenceTransformationMatrixType == "RIGID"
        assert len(matrix.FrameOfReferenceTransformationMatrix) == 16
        
        # Check it's an identity matrix
        expected_identity = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0
        ]
        assert matrix.FrameOfReferenceTransformationMatrix == expected_identity


@pytest.mark.pydicom
def test_split_structure_set_api():
    """Test the public API function."""
    for_uid1 = generate_uid()
    for_uid2 = generate_uid()
    
    ds = create_test_structure_set(
        roi_data=[
            {"name": "ROI1", "number": 1, "for_uid": for_uid1},
            {"name": "ROI2", "number": 2, "for_uid": for_uid2},
        ]
    )
    
    # Test with registrations
    structs, regs = split_structure_set_by_frame_of_reference(ds, generate_registrations=True)
    assert len(structs) == 2
    assert len(regs) == 1
    
    # Test without registrations
    structs, regs = split_structure_set_by_frame_of_reference(ds, generate_registrations=False)
    assert len(structs) == 2
    assert len(regs) == 0


@pytest.mark.pydicom
def test_split_structure_set_invalid_input():
    """Test that invalid input raises appropriate error."""
    # Create a non-structure-set DICOM
    ds = pydicom.Dataset()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"  # CT Image Storage
    
    with pytest.raises(ValueError, match="Input must be an RT Structure Set"):
        split_structure_set_by_frame_of_reference(ds)


@pytest.mark.pydicom
def test_cli_split_structure_set():
    """Test CLI functionality for splitting structure sets."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test structure set
        for_uid1 = generate_uid()
        for_uid2 = generate_uid()
        
        ds = create_test_structure_set(
            roi_data=[
                {"name": "ROI1", "number": 1, "for_uid": for_uid1},
                {"name": "ROI2", "number": 2, "for_uid": for_uid2},
            ]
        )
        
        input_file = temp_path / "test_struct.dcm"
        pydicom.dcmwrite(input_file, ds, write_like_original=False)
        
        output_dir = temp_path / "output"
        
        # Run CLI command
        command = pmp_test_utils.get_pymedphys_dicom_cli() + [
            "split-structure-set",
            str(input_file),
            str(output_dir),
        ]
        
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0
        
        # Check output files
        output_files = list(output_dir.glob("*.dcm"))
        assert len(output_files) == 3  # 2 structure sets + 1 registration
        
        # Check structure files
        struct_files = [f for f in output_files if "registration" not in f.name]
        assert len(struct_files) == 2
        
        # Check registration files
        reg_files = [f for f in output_files if "registration" in f.name]
        assert len(reg_files) == 1


@pytest.mark.pydicom
def test_cli_split_structure_set_no_registrations():
    """Test CLI with --no-registrations flag."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test structure set
        for_uid1 = generate_uid()
        for_uid2 = generate_uid()
        
        ds = create_test_structure_set(
            roi_data=[
                {"name": "ROI1", "number": 1, "for_uid": for_uid1},
                {"name": "ROI2", "number": 2, "for_uid": for_uid2},
            ]
        )
        
        input_file = temp_path / "test_struct.dcm"
        pydicom.dcmwrite(input_file, ds, write_like_original=False)
        
        output_dir = temp_path / "output"
        
        # Run CLI command with --no-registrations
        command = pmp_test_utils.get_pymedphys_dicom_cli() + [
            "split-structure-set",
            str(input_file),
            str(output_dir),
            "--no-registrations",
        ]
        
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0
        
        # Check output files - should only have structure sets
        output_files = list(output_dir.glob("*.dcm"))
        assert len(output_files) == 2
        assert all("registration" not in f.name for f in output_files)


@pytest.mark.pydicom
def test_sequences_filtered_correctly():
    """Test that all ROI-related sequences are filtered correctly."""
    for_uid1 = generate_uid()
    for_uid2 = generate_uid()
    
    ds = create_test_structure_set(
        roi_data=[
            {"name": "ROI1", "number": 1, "for_uid": for_uid1},
            {"name": "ROI2", "number": 2, "for_uid": for_uid1},
            {"name": "ROI3", "number": 3, "for_uid": for_uid2},
        ],
        include_observations=True
    )
    
    structs, _ = split_structure_set_by_frame_of_reference(ds, generate_registrations=False)
    
    # Check first structure set
    struct1 = structs[0]
    roi_numbers_1 = {roi.ROINumber for roi in struct1.StructureSetROISequence}
    contour_refs_1 = {c.ReferencedROINumber for c in struct1.ROIContourSequence}
    obs_refs_1 = {o.ReferencedROINumber for o in struct1.RTROIObservationsSequence}
    
    assert roi_numbers_1 == {1, 2}
    assert contour_refs_1 == {1, 2}
    assert obs_refs_1 == {1, 2}
    
    # Check second structure set
    struct2 = structs[1]
    roi_numbers_2 = {roi.ROINumber for roi in struct2.StructureSetROISequence}
    contour_refs_2 = {c.ReferencedROINumber for c in struct2.ROIContourSequence}
    obs_refs_2 = {o.ReferencedROINumber for o in struct2.RTROIObservationsSequence}
    
    assert roi_numbers_2 == {3}
    assert contour_refs_2 == {3}
    assert obs_refs_2 == {3}


# Helper functions for creating test data

def create_test_structure_set(roi_data, include_observations=False):
    """Create a test RT Structure Set with specified ROIs and Frame of Reference UIDs."""
    ds_dict = {
        "SOPClassUID": "1.2.840.10008.5.1.4.1.1.481.3",  # RT Structure Set
        "SOPInstanceUID": generate_uid(),
        "Modality": "RTSTRUCT",
        "PatientName": "TestPatient",
        "PatientID": "12345",
        "StudyInstanceUID": generate_uid(),
        "SeriesInstanceUID": generate_uid(),
        "StructureSetLabel": "Test Structure Set",
        "StructureSetROISequence": [],
        "ROIContourSequence": [],
        "ReferencedFrameOfReferenceSequence": [],
    }
    
    # Build Frame of Reference mapping
    for_map = {}
    for roi in roi_data:
        for_uid = roi["for_uid"]
        if for_uid not in for_map:
            for_map[for_uid] = {
                "FrameOfReferenceUID": for_uid,
                "RTReferencedStudySequence": [
                    {
                        "ReferencedSOPClassUID": "1.2.840.10008.3.1.2.3.1",
                        "ReferencedSOPInstanceUID": generate_uid(),
                        "RTReferencedSeriesSequence": [
                            {
                                "SeriesInstanceUID": generate_uid(),
                                "ContourImageSequence": [
                                    {
                                        "ReferencedSOPClassUID": "1.2.840.10008.5.1.4.1.1.2",
                                        "ReferencedSOPInstanceUID": generate_uid(),
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
    
    ds_dict["ReferencedFrameOfReferenceSequence"] = list(for_map.values())
    
    # Add ROIs
    for roi in roi_data:
        # StructureSetROISequence
        ds_dict["StructureSetROISequence"].append({
            "ROINumber": roi["number"],
            "ReferencedFrameOfReferenceUID": roi["for_uid"],
            "ROIName": roi["name"],
            "ROIGenerationAlgorithm": "MANUAL",
        })
        
        # ROIContourSequence
        ds_dict["ROIContourSequence"].append({
            "ReferencedROINumber": roi["number"],
            "ContourSequence": [
                {
                    "ContourGeometricType": "CLOSED_PLANAR",
                    "NumberOfContourPoints": 4,
                    "ContourData": [
                        0, 0, 0,
                        10, 0, 0,
                        10, 10, 0,
                        0, 10, 0
                    ],
                }
            ]
        })
    
    # Add observations if requested
    if include_observations:
        ds_dict["RTROIObservationsSequence"] = []
        for roi in roi_data:
            ds_dict["RTROIObservationsSequence"].append({
                "ObservationNumber": roi["number"],
                "ReferencedROINumber": roi["number"],
                "ROIObservationLabel": f"{roi['name']} Observation",
                "RTROIInterpretedType": "ORGAN",
            })
    
    return dicom_dataset_from_dict(ds_dict)