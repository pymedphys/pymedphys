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

"""Functionality for splitting RT Structure Sets by Frame of Reference UID."""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pymedphys._imports import pydicom

from ..uid import generate_uid


class StructureSetSplitter:
    """Splits RT Structure Sets that reference multiple Frame of Reference UIDs.
    
    This is useful when converting structure sets from systems like Oncentra
    (which allow multiple Frame of Reference UIDs) to systems like Eclipse
    (which require a single Frame of Reference UID per structure set).
    """
    
    def __init__(self, ds: pydicom.Dataset):
        """Initialize the splitter with an RT Structure Set.
        
        Parameters
        ----------
        ds : pydicom.Dataset
            The RT Structure Set to analyze and potentially split.
        """
        self.original_ds = ds
        self.for_to_roi_map: Dict[str, List[int]] = {}
        self.for_to_image_map: Dict[str, List[str]] = {}
        
    def analyze(self) -> None:
        """Analyze the structure set to build Frame of Reference mappings.
        
        This method populates:
        - for_to_roi_map: Maps Frame of Reference UID to ROI numbers
        - for_to_image_map: Maps Frame of Reference UID to referenced image UIDs
        """
        # Build mapping of Frame of Reference UID to ROI numbers
        if hasattr(self.original_ds, 'StructureSetROISequence'):
            for roi in self.original_ds.StructureSetROISequence:
                roi_number = roi.ROINumber
                for_uid = roi.ReferencedFrameOfReferenceUID
                
                if for_uid not in self.for_to_roi_map:
                    self.for_to_roi_map[for_uid] = []
                self.for_to_roi_map[for_uid].append(roi_number)
        
        # Build mapping of Frame of Reference UID to referenced images
        if hasattr(self.original_ds, 'ReferencedFrameOfReferenceSequence'):
            for ref_for in self.original_ds.ReferencedFrameOfReferenceSequence:
                for_uid = ref_for.FrameOfReferenceUID
                
                if for_uid not in self.for_to_image_map:
                    self.for_to_image_map[for_uid] = []
                    
                if hasattr(ref_for, 'RTReferencedStudySequence'):
                    for study in ref_for.RTReferencedStudySequence:
                        if hasattr(study, 'RTReferencedSeriesSequence'):
                            for series in study.RTReferencedSeriesSequence:
                                if hasattr(series, 'ContourImageSequence'):
                                    for image in series.ContourImageSequence:
                                        self.for_to_image_map[for_uid].append(
                                            image.ReferencedSOPInstanceUID
                                        )
    
    def split(self) -> List[pydicom.Dataset]:
        """Split the structure set by Frame of Reference UID.
        
        Returns
        -------
        List[pydicom.Dataset]
            List of split RT Structure Sets, one per Frame of Reference UID.
            If only one Frame of Reference UID is found, returns the original
            dataset unchanged.
        """
        self.analyze()
        
        # If only one Frame of Reference, return original
        if len(self.for_to_roi_map) <= 1:
            return [self.original_ds]
        
        # Create a new structure set for each Frame of Reference
        split_datasets = []
        for for_uid, roi_numbers in self.for_to_roi_map.items():
            new_ds = self._create_subset_structure_set(for_uid, roi_numbers)
            split_datasets.append(new_ds)
            
        return split_datasets
    
    def _create_subset_structure_set(
        self, for_uid: str, roi_numbers: List[int]
    ) -> pydicom.Dataset:
        """Create a new structure set containing only specified ROIs.
        
        Parameters
        ----------
        for_uid : str
            Frame of Reference UID for this subset
        roi_numbers : List[int]
            List of ROI numbers to include
            
        Returns
        -------
        pydicom.Dataset
            New RT Structure Set containing only the specified ROIs
        """
        # Create a deep copy of the original dataset
        new_ds = self.original_ds.copy()
        
        # Generate new SOP Instance UID
        new_ds.SOPInstanceUID = generate_uid()
        
        # Update series description to indicate split
        if hasattr(new_ds, 'SeriesDescription'):
            new_ds.SeriesDescription = f"{new_ds.SeriesDescription} - FOR Split"
        else:
            new_ds.SeriesDescription = "Structure Set - FOR Split"
            
        # Update instance creation date/time
        dt = datetime.now()
        new_ds.InstanceCreationDate = dt.strftime("%Y%m%d")
        new_ds.InstanceCreationTime = dt.strftime("%H%M%S.%f")[:-3]
        
        # Filter sequences to include only relevant ROIs
        self._filter_sequences(new_ds, roi_numbers)
        
        # Update Referenced Frame of Reference Sequence
        self._update_referenced_frame_of_reference(new_ds, for_uid)
        
        return new_ds
    
    def _filter_sequences(
        self, ds: pydicom.Dataset, roi_numbers: List[int]
    ) -> None:
        """Filter ROI-related sequences to include only specified ROIs.
        
        Parameters
        ----------
        ds : pydicom.Dataset
            Dataset to modify in-place
        roi_numbers : List[int]
            List of ROI numbers to keep
        """
        roi_set = set(roi_numbers)
        
        # Filter StructureSetROISequence
        if hasattr(ds, 'StructureSetROISequence'):
            ds.StructureSetROISequence = [
                roi for roi in ds.StructureSetROISequence
                if roi.ROINumber in roi_set
            ]
        
        # Filter ROIContourSequence
        if hasattr(ds, 'ROIContourSequence'):
            ds.ROIContourSequence = [
                contour for contour in ds.ROIContourSequence
                if contour.ReferencedROINumber in roi_set
            ]
        
        # Filter RTROIObservationsSequence
        if hasattr(ds, 'RTROIObservationsSequence'):
            ds.RTROIObservationsSequence = [
                obs for obs in ds.RTROIObservationsSequence
                if obs.ReferencedROINumber in roi_set
            ]
    
    def _update_referenced_frame_of_reference(
        self, ds: pydicom.Dataset, for_uid: str
    ) -> None:
        """Update Referenced Frame of Reference Sequence for single FOR.
        
        Parameters
        ----------
        ds : pydicom.Dataset
            Dataset to modify in-place
        for_uid : str
            Frame of Reference UID to keep
        """
        if hasattr(ds, 'ReferencedFrameOfReferenceSequence'):
            # Find the sequence item for this FOR
            for ref_for in ds.ReferencedFrameOfReferenceSequence:
                if ref_for.FrameOfReferenceUID == for_uid:
                    # Keep only this one
                    ds.ReferencedFrameOfReferenceSequence = [ref_for]
                    break


class RegistrationGenerator:
    """Generates DICOM Spatial Registration objects between Frame of Reference pairs."""
    
    def __init__(self, structure_sets: List[pydicom.Dataset]):
        """Initialize with split structure sets.
        
        Parameters
        ----------
        structure_sets : List[pydicom.Dataset]
            List of RT Structure Sets to generate registrations between
        """
        self.structure_sets = structure_sets
        self._extract_for_pairs()
        
    def _extract_for_pairs(self) -> None:
        """Extract Frame of Reference UID pairs from structure sets."""
        self.for_uids = []
        
        for ds in self.structure_sets:
            if hasattr(ds, 'ReferencedFrameOfReferenceSequence'):
                for ref_for in ds.ReferencedFrameOfReferenceSequence:
                    self.for_uids.append(ref_for.FrameOfReferenceUID)
        
        # Create pairs for registration
        self.for_pairs = []
        for i in range(len(self.for_uids)):
            for j in range(i + 1, len(self.for_uids)):
                self.for_pairs.append((self.for_uids[i], self.for_uids[j]))
    
    def generate_registrations(self) -> List[pydicom.Dataset]:
        """Generate spatial registration objects for all FOR pairs.
        
        Returns
        -------
        List[pydicom.Dataset]
            List of Spatial Registration objects
        """
        registrations = []
        
        for source_for, target_for in self.for_pairs:
            reg = self._create_spatial_registration(source_for, target_for)
            registrations.append(reg)
            
        return registrations
    
    def _create_spatial_registration(
        self, source_for: str, target_for: str
    ) -> pydicom.Dataset:
        """Create a DICOM Spatial Registration object.
        
        Parameters
        ----------
        source_for : str
            Source Frame of Reference UID
        target_for : str
            Target Frame of Reference UID
            
        Returns
        -------
        pydicom.Dataset
            Spatial Registration object with identity transform
        """
        ds = pydicom.Dataset()
        
        # File Meta Information
        ds.file_meta = pydicom.Dataset()
        ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
        ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.66.1"
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.file_meta.ImplementationClassUID = generate_uid()
        
        # SOP Common Module
        ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.66.1"  # Spatial Registration
        ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
        
        # Copy patient/study/series info from first structure set if available
        if self.structure_sets:
            ref_ds = self.structure_sets[0]
            
            # Patient Module
            for attr in ['PatientName', 'PatientID', 'PatientBirthDate', 'PatientSex']:
                if hasattr(ref_ds, attr):
                    setattr(ds, attr, getattr(ref_ds, attr))
            
            # Study Module
            for attr in ['StudyInstanceUID', 'StudyDate', 'StudyTime', 
                        'ReferringPhysicianName', 'StudyID', 'AccessionNumber']:
                if hasattr(ref_ds, attr):
                    setattr(ds, attr, getattr(ref_ds, attr))
        
        # Series Module
        ds.Modality = "REG"
        ds.SeriesInstanceUID = generate_uid()
        ds.SeriesNumber = 1
        dt = datetime.now()
        ds.SeriesDate = dt.strftime("%Y%m%d")
        ds.SeriesTime = dt.strftime("%H%M%S.%f")[:-3]
        ds.SeriesDescription = f"Spatial Registration {source_for[:8]} to {target_for[:8]}"
        
        # Spatial Registration Module
        ds.ContentDate = ds.SeriesDate
        ds.ContentTime = ds.SeriesTime
        ds.InstanceNumber = 1
        ds.ContentLabel = "REGISTRATION"
        ds.ContentDescription = f"Registration from {source_for} to {target_for}"
        ds.ContentCreatorName = "PyMedPhys"
        
        # Registration Sequence
        reg_seq = pydicom.Dataset()
        reg_seq.FrameOfReferenceUID = target_for
        
        # Matrix Registration Sequence
        matrix_reg_seq = pydicom.Dataset()
        matrix_reg_seq.MatrixSequence = pydicom.Sequence()
        
        # Matrix entry
        matrix_item = pydicom.Dataset()
        matrix_item.FrameOfReferenceTransformationMatrixType = "RIGID"
        
        # Identity matrix (4x4) as we don't have actual transformation data
        # Format: row-major order
        matrix_item.FrameOfReferenceTransformationMatrix = [
            1.0, 0.0, 0.0, 0.0,  # Row 1
            0.0, 1.0, 0.0, 0.0,  # Row 2
            0.0, 0.0, 1.0, 0.0,  # Row 3
            0.0, 0.0, 0.0, 1.0   # Row 4
        ]
        
        # Source Frame of Reference
        matrix_item.SourceFrameOfReferenceUID = source_for
        
        matrix_reg_seq.MatrixSequence.append(matrix_item)
        reg_seq.MatrixRegistrationSequence = pydicom.Sequence([matrix_reg_seq])
        
        ds.RegistrationSequence = pydicom.Sequence([reg_seq])
        
        # Set is_little_endian and is_implicit_VR
        ds.is_little_endian = True
        ds.is_implicit_VR = False
        
        return ds


def split_structure_set_by_frame_of_reference(
    ds: pydicom.Dataset,
    generate_registrations: bool = True
) -> Tuple[List[pydicom.Dataset], List[pydicom.Dataset]]:
    """Split RT Structure Set by Frame of Reference UID.
    
    This function splits an RT Structure Set that references multiple Frame of
    Reference UIDs into separate structure sets, one per Frame of Reference.
    This is useful when converting from systems like Oncentra (which allow
    multiple Frame of Reference UIDs) to systems like Eclipse (which require
    a single Frame of Reference UID per structure set).
    
    Parameters
    ----------
    ds : pydicom.Dataset
        RT Structure Set to split
    generate_registrations : bool, optional
        Whether to generate spatial registration objects between the split
        structure sets. Default is True.
        
    Returns
    -------
    structure_sets : List[pydicom.Dataset]
        List of split structure sets, one per Frame of Reference. If the input
        structure set only references one Frame of Reference, returns a list
        containing the original dataset unchanged.
    registrations : List[pydicom.Dataset]
        List of spatial registration objects linking the Frame of Reference
        UIDs. Empty list if generate_registrations is False or if only one
        Frame of Reference was found.
        
    Examples
    --------
    >>> import pydicom
    >>> import pymedphys
    >>> 
    >>> # Load a structure set with multiple Frame of Reference UIDs
    >>> ds = pydicom.dcmread("multi_for_struct.dcm")
    >>> 
    >>> # Split by Frame of Reference
    >>> split_structs, registrations = pymedphys.dicom.split_structure_set_by_frame_of_reference(ds)
    >>> 
    >>> # Save the split files
    >>> for i, struct in enumerate(split_structs):
    ...     struct.save_as(f"split_struct_{i}.dcm")
    >>> 
    >>> for i, reg in enumerate(registrations):
    ...     reg.save_as(f"registration_{i}.dcm")
    """
    # Validate input
    if ds.SOPClassUID != "1.2.840.10008.5.1.4.1.1.481.3":
        raise ValueError("Input must be an RT Structure Set")
    
    # Split the structure set
    splitter = StructureSetSplitter(ds)
    structure_sets = splitter.split()
    
    # Generate registrations if requested
    registrations = []
    if generate_registrations and len(structure_sets) > 1:
        generator = RegistrationGenerator(structure_sets)
        registrations = generator.generate_registrations()
    
    return structure_sets, registrations


def split_structure_set_cli(args):
    """CLI handler for splitting structure sets.
    
    Parameters
    ----------
    args : argparse.Namespace
        Command line arguments containing:
        - input_file: Path to input RT Structure Set
        - output_dir: Directory for output files
        - no_registrations: Flag to skip registration generation
        - prefix: Optional prefix for output filenames
    """
    import os
    from pathlib import Path
    
    # Read input file
    ds = pydicom.dcmread(args.input_file, force=True)
    
    # Create output directory if needed
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Split the structure set
    structure_sets, registrations = split_structure_set_by_frame_of_reference(
        ds, generate_registrations=not args.no_registrations
    )
    
    # Determine output prefix
    prefix = args.prefix if args.prefix else Path(args.input_file).stem
    
    # Save split structure sets
    if len(structure_sets) == 1:
        print("Structure set references only one Frame of Reference UID. No splitting needed.")
        # Still save to output directory for consistency
        output_path = output_dir / f"{prefix}_single_for.dcm"
        pydicom.dcmwrite(output_path, structure_sets[0], write_like_original=False)
        print(f"Saved original structure set to: {output_path}")
    else:
        print(f"Split structure set into {len(structure_sets)} files by Frame of Reference UID.")
        for i, struct_ds in enumerate(structure_sets):
            output_path = output_dir / f"{prefix}_for_{i:02d}.dcm"
            pydicom.dcmwrite(output_path, struct_ds, write_like_original=False)
            print(f"Saved structure set {i}: {output_path}")
        
        # Save registrations
        if registrations:
            print(f"\nGenerated {len(registrations)} registration files.")
            for i, reg_ds in enumerate(registrations):
                output_path = output_dir / f"{prefix}_registration_{i:02d}.dcm"
                pydicom.dcmwrite(output_path, reg_ds, write_like_original=False)
                print(f"Saved registration {i}: {output_path}")