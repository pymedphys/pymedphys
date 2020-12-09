import datetime
import glob

import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence

import config


def get_file_meta(dcms):
    dcm = dcms[0]
    file_meta = FileMetaDataset()
    file_meta.FileMetaInformationVersion = dcm.file_meta.FileMetaInformationVersion
    file_meta.MediaStorageSOPClassUID = "RT Structure Set Storage"
    file_meta.MediaStorageSOPInstanceUID = "Anonymous"  # TODO
    file_meta.TransferSyntaxUID = dcm.file_meta.TransferSyntaxUID
    file_meta.ImplementationClassUID = dcm.file_meta.ImplementationClassUID
    file_meta.ImplementationVersionName = dcm.file_meta.ImplementationVersionName
    return file_meta


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
    rt_refd_study1.ReferencedSOPClassUID = ds.file_meta.MediaStorageSOPClassUID
    rt_refd_study1.ReferencedSOPInstanceUID = (
        "2.25.152307708682568459392858274513677418485"  # TODO
    )

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


def add_structure_set_roi_sequence(ds):
    # Structure Set ROI Sequence
    structure_set_roi_sequence = Sequence()
    ds.StructureSetROISequence = structure_set_roi_sequence

    # Structure Set ROI Sequence: Structure Set ROI 1
    structure_set_roi1 = Dataset()
    structure_set_roi1.ROINumber = "27"
    structure_set_roi1.ReferencedFrameOfReferenceUID = dcm.FrameOfReferenceUID
    structure_set_roi1.ROIName = "Vacbag"
    structure_set_roi1.ROIGenerationAlgorithm = "AUTOMATIC"
    structure_set_roi_sequence.append(structure_set_roi1)

    return ds


def add_roi_contour_sequence(ds, dcms):
    # ROI Contour Sequence
    roi_contour_sequence = Sequence()
    ds.ROIContourSequence = roi_contour_sequence

    # ROI Contour Sequence: ROI Contour 1
    roi_contour1 = Dataset()
    roi_contour1.ROIDisplayColor = [128, 128, 255]

    # Contour Sequence
    contour_sequence = Sequence()
    roi_contour1.ContourSequence = contour_sequence

    for dcm in dcms:
        z = dcm.SliceLocation

        # Contour Sequence: Contour 1
        contour1 = Dataset()

        # Contour Image Sequence
        contour_image_sequence = Sequence()
        contour1.ContourImageSequence = contour_image_sequence

        # Contour Image Sequence: Contour Image 1
        contour_image1 = Dataset()
        contour_image1.ReferencedSOPClassUID = "CT Image Storage"
        contour_image1.ReferencedSOPInstanceUID = (
            "2.25.152306916480171479263212437161921183733.1"  # TODO
        )
        contour_image_sequence.append(contour_image1)

        contour1.ContourGeometricType = "CLOSED_PLANAR"
        contour1.ContourData = [
            -100.5,
            -100.5,
            z,
            -99.9,
            -100.5,
            z,
        ]  # TODO - GET CONTOUR DATA FROM INFERENCE
        contour1.NumberOfContourPoints = len(contour1.ContourData) // 3
        contour_sequence.append(contour1)

    roi_contour1.ReferencedROINumber = "27"
    roi_contour_sequence.append(roi_contour1)


def add_rt_roi_observations_sequence(ds):
    # RT ROI Observations Sequence
    rtroi_observations_sequence = Sequence()
    ds.RTROIObservationsSequence = rtroi_observations_sequence

    # RT ROI Observations Sequence: RT ROI Observations 1
    rtroi_observations1 = Dataset()
    rtroi_observations1.ObservationNumber = "27"
    rtroi_observations1.ReferencedROINumber = "27"
    rtroi_observations1.RTROIInterpretedType = "ORGAN"
    rtroi_observations1.ROIInterpreter = ""
    rtroi_observations_sequence.append(rtroi_observations1)

    return ds


dcm_paths = glob.glob(config.DATA_PATH + "/*")

dcms = [pydicom.dcmread(path, force=True) for path in dcm_paths]

try:
    dcms = sorted(dcms, key=lambda dcm: dcm.SliceLocation)
except AttributeError:
    dcms = sorted(dcms, key=lambda dcm: dcm.SOPInstanceUID)

dcm = dcms[0]

ds = Dataset()
ds.file_meta = get_file_meta(dcms)
ds.is_implicit_VR = True
ds.is_little_endian = True
ds.fix_meta_info(enforce_standard=True)

dt = datetime.datetime.now()

ds.InstanceCreationDate = dt.strftime("%Y%m%d")
ds.InstanceCreationTime = dt.strftime("%H%M%S.%f")
ds.InstanceCreatorUID = "Anonymous"  # TODO
ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID
ds.StudyDate = dcm.StudyDate
ds.StudyTime = dcm.StudyTime
ds.AccessionNumber = dcm.AccessionNumber
ds.Modality = "RTSTRUCT"
ds.Manufacturer = dcm.Manufacturer
ds.ReferringPhysicianName = dcm.ReferringPhysicianName
ds.InstitutionalDepartmentName = "Anonymous"  # TODO
ds.ManufacturerModelName = dcm.ManufacturerModelName
ds.PatientName = dcm.PatientName
ds.PatientID = dcm.PatientID
ds.PatientBirthDate = dcm.PatientBirthDate
ds.PatientSex = dcm.PatientSex
ds.StudyInstanceUID = dcm.StudyInstanceUID
ds.StudyID = "Anonymous"  # TODO
ds.SeriesNumber = "1"  # TODO
ds.StructureSetLabel = "STRCTRLABEL"
ds.StructureSetName = "STRCTRNAME"
ds.StructureSetDate = ds.InstanceCreationDate
ds.StructureSetTime = ds.InstanceCreationTime

ds = add_referenced_frame_of_reference_sequence(ds, dcms)
ds = add_structure_set_roi_sequence(ds)

# ds = add_roi_contour_sequence(ds, dcms)
ds = add_rt_roi_observations_sequence(ds)

for x in ds:
    print(x)

ds.save_as("Test")
