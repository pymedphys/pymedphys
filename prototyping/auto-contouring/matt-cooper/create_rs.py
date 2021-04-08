# Copyright (C) 2020 Matthew Cooper
# Produced in part from pydicom's codify.py

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import datetime

import pydicom
import pydicom._storage_sopclass_uids
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence


def copy_attrs(obj_from, obj_to, names):
    for n in names:
        if hasattr(obj_from, n):
            attr = getattr(obj_from, n)
            setattr(obj_to, n, attr)


def get_file_meta(dcm, root_uid):
    file_meta = FileMetaDataset()

    # From pydicom
    file_meta.MediaStorageSOPClassUID = (
        pydicom._storage_sopclass_uids.RTStructureSetStorage
    )
    file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid(
        root_uid
    )  # TODO Generate this properly
    file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian

    # From dicom imaging file
    imaging_meta = [
        "FileMetaInformationVersion",
        "ImplementationClassUID",
        "ImplementationVersionName",
    ]

    copy_attrs(dcm.file_meta, file_meta, imaging_meta)

    # file_meta.FileMetaInformationVersion = dcm.file_meta.FileMetaInformationVersion
    # file_meta.ImplementationClassUID = (
    #     dcm.file_meta.ImplementationClassUID
    # )  # TODO Check this is true on non-anon data
    # file_meta.ImplementationVersionName = dcm.file_meta.ImplementationVersionName

    return file_meta


def add_top_level(ds, dcm):
    # From date
    date = datetime.datetime.now()
    ds.InstanceCreationDate = date.strftime("%Y%m%d")
    ds.InstanceCreationTime = date.strftime("%H%M%S.%f")
    ds.StructureSetDate = ds.InstanceCreationDate
    ds.StructureSetTime = ds.InstanceCreationTime

    # From file_meta
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID

    # RS specific
    ds.Modality = "RTSTRUCT"
    ds.StructureSetLabel = "STRCTRLABEL"
    ds.StructureSetName = "STRCTRNAME"

    # From dicom imaging file
    imaging_attrs = [
        "StudyDate",
        "StudyTime",
        "AccessionNumber",
        "ReferringPhysicianName",
        "PatientName",
        "PatientID",
        "PatientBirthDate",
        "PatientSex",
        "StudyInstanceUID",
        "StudyID",
        "InstanceCreatorUID",
        "InstanceCreatorUID",
        "InstitutionalDepartmentName",
        "SeriesInstanceUID",
        "OtherPatientIDs",
        "OtherPatientNames",
        "SeriesNumber",
        "Manufacturer",
        "ManufacturerModelName",
    ]

    copy_attrs(dcm, ds, imaging_attrs)

    # try:
    #     ds.StudyDate = dcm.StudyDate
    #     ds.StudyTime = dcm.StudyTime
    #     ds.AccessionNumber = dcm.AccessionNumber
    #     ds.ReferringPhysicianName = dcm.ReferringPhysicianName
    #     ds.PatientName = dcm.PatientName
    #     ds.PatientID = dcm.PatientID
    #     ds.PatientBirthDate = dcm.PatientBirthDate
    #     ds.PatientSex = dcm.PatientSex
    #     ds.StudyInstanceUID = dcm.StudyInstanceUID
    #     ds.StudyID = dcm.StudyID
    # except AttributeError:
    #     print("Missing some top level attributes from dcm file")

    # ds.InstanceCreatorUID = "Anonymous"  # TODO
    # ds.InstitutionalDepartmentName = "Anonymous"  # TODO
    # ds.SeriesInstanceUID = "Anonymous"  # TODO
    # ds.OtherPatientIDs = "Anonymous"  # TODO
    # ds.OtherPatientNames = "Anonymous"  # TODO
    # ds.SeriesNumber = "1"  # TODO
    # ds.Manufacturer = "Anonymous"  # TODO
    # ds.ManufacturerModelName = "Anonymous"  # TODO

    return ds


def add_referenced_frame_of_reference_sequence(ds, dcms):
    dcm = dcms[0]

    # Referenced Frame of Reference Sequence
    refd_frame_of_ref_sequence = Sequence()
    ds.ReferencedFrameOfReferenceSequence = refd_frame_of_ref_sequence

    # Referenced Frame of Reference Sequence: Referenced Frame of Reference 1
    refd_frame_of_ref1 = Dataset()
    refd_frame_of_ref1.FrameOfReferenceUID = dcm.FrameOfReferenceUID

    # RT Referenced Study Sequence
    rt_refd_study_sequence = Sequence()
    refd_frame_of_ref1.RTReferencedStudySequence = rt_refd_study_sequence

    # RT Referenced Study Sequence: RT Referenced Study 1
    rt_refd_study1 = Dataset()
    rt_refd_study1.ReferencedSOPClassUID = (
        pydicom._storage_sopclass_uids.RTStructureSetStorage
    )
    rt_refd_study1.ReferencedSOPInstanceUID = "Anonymous"  # TODO

    # RT Referenced Series Sequence
    rt_refd_series_sequence = Sequence()
    rt_refd_study1.RTReferencedSeriesSequence = rt_refd_series_sequence

    # RT Referenced Series Sequence: RT Referenced Series 1
    rt_refd_series1 = Dataset()
    rt_refd_series1.SeriesInstanceUID = dcm.SeriesInstanceUID

    # Contour Image Sequence
    contour_image_sequence = Sequence()
    rt_refd_series1.ContourImageSequence = contour_image_sequence

    for dcm in dcms:
        contour_image = Dataset()
        contour_image.ReferencedSOPClassUID = dcm.SOPClassUID
        contour_image.ReferencedSOPInstanceUID = dcm.SOPInstanceUID
        contour_image_sequence.append(contour_image)

    rt_refd_series_sequence.append(rt_refd_series1)
    rt_refd_study_sequence.append(rt_refd_study1)
    refd_frame_of_ref_sequence.append(refd_frame_of_ref1)

    return ds


def add_rt_roi_observations_sequence(ds):
    ds.RTROIObservationsSequence = Sequence()

    # Vacbag
    rtroi_observations = Dataset()
    rtroi_observations.ObservationNumber = "1"
    rtroi_observations.ReferencedROINumber = "1"
    rtroi_observations.RTROIInterpretedType = "SUPPORT"
    rtroi_observations.ROIInterpreter = ""

    ds.RTROIObservationsSequence.append(rtroi_observations)
    return ds


def add_structure_set_roi_sequence(ds, dcm):
    ds.StructureSetROISequence = Sequence()

    # Vacbag
    structure_set_roi = Dataset()
    structure_set_roi.ROINumber = "1"
    structure_set_roi.ReferencedFrameOfReferenceUID = dcm.FrameOfReferenceUID
    structure_set_roi.ROIName = "Vacbag"
    structure_set_roi.ROIGenerationAlgorithm = "AUTOMATIC"

    ds.StructureSetROISequence.append(structure_set_roi)
    return ds


def add_roi_contour_sequence(ds, dcms, contours):
    # ROI Contour Sequence
    roi_contour_sequence = Sequence()
    ds.ROIContourSequence = roi_contour_sequence

    # ROI Contour Sequence: ROI Contour 1
    roi_contour1 = Dataset()
    roi_contour1.ROIDisplayColor = [220, 160, 120]

    # Contour Sequence
    contour_sequence = Sequence()
    roi_contour1.ContourSequence = contour_sequence

    for dcm, contour in zip(dcms, contours):

        if len(contour) > 0:

            for roi in contour:  # TODO Test this loop with two squares

                # Contour Sequence: Contour 1
                contour1 = Dataset()

                # Contour Image Sequence
                contour_image_sequence = Sequence()
                contour1.ContourImageSequence = contour_image_sequence

                # Contour Image Sequence: Contour Image 1
                contour_image1 = Dataset()
                contour_image1.ReferencedSOPClassUID = dcm.SOPClassUID
                contour_image1.ReferencedSOPInstanceUID = dcm.SOPInstanceUID
                contour_image_sequence.append(contour_image1)

                contour1.ContourGeometricType = "CLOSED_PLANAR"

                contour1.ContourData = roi

                contour1.NumberOfContourPoints = (
                    len(contour1.ContourData) // 3
                )  # TODO Test this is this case
                contour_sequence.append(contour1)

    roi_contour1.ReferencedROINumber = "1"
    roi_contour_sequence.append(roi_contour1)

    return ds


def create_rs_file(dicom_series, contours, root_uid):
    dicom_file = dicom_series[0]

    # Create structure file
    dicom_structure_file = Dataset()

    # File meta
    dicom_structure_file.file_meta = get_file_meta(dicom_file, root_uid)
    dicom_structure_file.is_implicit_VR = True
    dicom_structure_file.is_little_endian = True
    dicom_structure_file.fix_meta_info(enforce_standard=True)

    # Top level
    dicom_structure_file = add_top_level(dicom_structure_file, dicom_file)

    # Sequences
    dicom_structure_file = add_referenced_frame_of_reference_sequence(
        dicom_structure_file, dicom_series
    )

    dicom_structure_file = add_structure_set_roi_sequence(
        dicom_structure_file, dicom_file
    )

    dicom_structure_file = add_rt_roi_observations_sequence(dicom_structure_file)

    dicom_structure_file = add_roi_contour_sequence(
        dicom_structure_file, dicom_series, contours
    )

    return dicom_structure_file
