# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Synthetic classic CT, MR, and PET series that conform to their IODs, to
test the evaluation's conversion to the Legacy Converted Enhanced IODs.

Every value is invented. dciodvfy finds no error in any image that
:func:`classic_series` makes.
"""

from __future__ import annotations

import io

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

ROOT = "2.25.77777"
STUDY = f"{ROOT}1"
FRAME_OF_REFERENCE = f"{ROOT}2"
MODALITIES = {
    "CT": "1.2.840.10008.5.1.4.1.1.2",
    "MR": "1.2.840.10008.5.1.4.1.1.4",
    "PT": "1.2.840.10008.5.1.4.1.1.128",
}


def classic_series(
    modality: str,
    slices: int = 3,
    *,
    rows: int = 16,
    columns: int = 12,
    series: int = 1,
    seed: int = 0,
    references: bool = True,
) -> list[pydicom.Dataset]:
    """A series of classic single-frame images of one modality, its slices
    1.5 mm apart along the patient's axis, each with distinct stored
    values, and each after the first referencing the first, where
    ``references``."""
    rng = np.random.default_rng(seed)
    images = []
    for number in range(1, slices + 1):
        dataset = _common(modality, series, number)
        _pixels(dataset, modality, rng, rows, columns)
        _modality(dataset, modality, number)
        if references and images:
            reference = pydicom.Dataset()
            reference.ReferencedSOPClassUID = images[0].SOPClassUID
            reference.ReferencedSOPInstanceUID = images[0].SOPInstanceUID
            dataset.ReferencedImageSequence = [reference]
        images.append(dataset)
    return images


def _common(modality: str, series: int, number: int) -> pydicom.Dataset:
    dataset = pydicom.Dataset()
    dataset.SpecificCharacterSet = "ISO_IR 100"
    dataset.SOPClassUID = MODALITIES[modality]
    dataset.SOPInstanceUID = f"{ROOT}3{series}{number:03d}"
    dataset.StudyDate = "20200102"
    dataset.StudyTime = "101500"
    dataset.ContentDate = "20200102"
    dataset.ContentTime = f"1016{number:02d}"
    dataset.AcquisitionDate = "20200102"
    dataset.AcquisitionTime = f"1015{number:02d}.5"
    dataset.AccessionNumber = "A1"
    dataset.Modality = modality
    dataset.Manufacturer = "Synthetic"
    dataset.ReferringPhysicianName = ""
    dataset.PatientName = "Synthetic^Patient"
    dataset.PatientID = "SYN1"
    dataset.PatientBirthDate = "19700101"
    dataset.PatientSex = "O"
    dataset.StudyInstanceUID = STUDY
    dataset.SeriesInstanceUID = f"{ROOT}4{series}"
    dataset.StudyID = "S1"
    dataset.SeriesNumber = series
    dataset.InstanceNumber = number
    dataset.AcquisitionNumber = 1
    dataset.PatientOrientation = ""
    dataset.FrameOfReferenceUID = FRAME_OF_REFERENCE
    dataset.PositionReferenceIndicator = ""
    if modality != "PT":
        # PET gives Patient Orientation Code Sequence instead.
        dataset.PatientPosition = "HFS"
    dataset.BodyPartExamined = "CHEST"
    dataset.ImagePositionPatient = [-10.0, -12.0, 1.5 * number]
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.PixelSpacing = [0.8, 0.8]
    dataset.SliceThickness = "1.5"
    dataset.SliceLocation = f"{1.5 * number:g}"
    dataset.BurnedInAnnotation = "NO"
    # A private attribute that every image shares, and one that differs.
    block = dataset.private_block(0x0009, "SYNTHETIC CONVERSION", create=True)
    block.add_new(0x01, "LO", "shared")
    block.add_new(0x02, "IS", number)
    return dataset


def _pixels(
    dataset: pydicom.Dataset,
    modality: str,
    rng: np.random.Generator,
    rows: int,
    columns: int,
) -> None:
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows = rows
    dataset.Columns = columns
    dataset.BitsAllocated = 16
    if modality == "CT":
        dataset.BitsStored = 12
        dataset.PixelRepresentation = 0
        values = rng.integers(0, 4096, (rows, columns), dtype=np.uint16)
    elif modality == "MR":
        dataset.BitsStored = 12
        dataset.PixelRepresentation = 0
        values = rng.integers(0, 4096, (rows, columns), dtype=np.uint16)
    else:
        dataset.BitsStored = 16
        dataset.PixelRepresentation = 1
        values = rng.integers(-1000, 30000, (rows, columns), dtype=np.int16)
    dataset.HighBit = dataset.BitsStored - 1
    dataset.PixelData = values.astype(values.dtype.newbyteorder("<")).tobytes()


def _modality(dataset: pydicom.Dataset, modality: str, number: int) -> None:
    if modality == "CT":
        dataset.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
        dataset.RescaleIntercept = "-1024"
        dataset.RescaleSlope = "1"
        dataset.KVP = "120"
        dataset.WindowCenter = "40"
        dataset.WindowWidth = "400"
        dataset.ConvolutionKernel = "STANDARD"
    elif modality == "MR":
        dataset.ImageType = ["ORIGINAL", "PRIMARY", "M", "ND"]
        dataset.ScanningSequence = "SE"
        dataset.SequenceVariant = "NONE"
        dataset.ScanOptions = ""
        dataset.MRAcquisitionType = "2D"
        dataset.RepetitionTime = "500"
        dataset.EchoTime = "15"
        dataset.EchoTrainLength = "1"
        dataset.ImagedNucleus = "1H"
        dataset.MagneticFieldStrength = "1.5"
        dataset.SpacingBetweenSlices = "1.5"
        # The classic Contrast/Bolus Module, whose Contrast/Bolus Agent
        # Sequence the Enhanced Contrast/Bolus Module holds with more.
        dataset.ContrastBolusAgent = "Synthetic agent"
        agent = pydicom.Dataset()
        agent.CodeValue = "387467008"
        agent.CodingSchemeDesignator = "SCT"
        agent.CodeMeaning = "Synthetic agent"
        dataset.ContrastBolusAgentSequence = [agent]
    else:
        dataset.ImageType = ["ORIGINAL", "PRIMARY"]
        dataset.RescaleIntercept = "0"
        dataset.RescaleSlope = "0.5"
        dataset.SeriesDate = "20200102"
        dataset.SeriesTime = "101500"
        dataset.Units = "BQML"
        dataset.CountsSource = "EMISSION"
        dataset.SeriesType = ["STATIC", "IMAGE"]
        dataset.NumberOfSlices = 3
        dataset.DecayCorrection = "START"
        dataset.CorrectedImage = ["DECY", "ATTN"]
        dataset.CollimatorType = "NONE"
        dataset.ImageIndex = number
        dataset.FrameReferenceTime = "0"
        dataset.ActualFrameDuration = 600000
        dataset.DecayFactor = "1.0"
        dataset.PatientGantryRelationshipCodeSequence = []
        dataset.RandomsCorrectionMethod = "NONE"
        item = pydicom.Dataset()
        item.RadiopharmaceuticalStartTime = "100000"
        item.RadionuclideTotalDose = "370000000"
        item.RadionuclideHalfLife = "6586.2"
        code = pydicom.Dataset()
        code.CodeValue = "77004003"
        code.CodingSchemeDesignator = "SCT"
        code.CodeMeaning = "^18^Fluorine"
        item.RadionuclideCodeSequence = [code]
        dataset.RadiopharmaceuticalInformationSequence = [item]
        dataset.PatientOrientationCodeSequence = []
        dataset.ReconstructionMethod = "OSEM"
        dataset.ScatterCorrectionMethod = "NONE"
        dataset.AttenuationCorrectionMethod = "CT"
        dataset.DecayCorrection = "START"


def encoded(dataset: pydicom.Dataset) -> bytes:
    """An image as a PS3.10 file in Explicit VR Little Endian."""
    meta = pydicom.dataset.FileMetaDataset()
    meta.MediaStorageSOPClassUID = dataset.SOPClassUID
    meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
    meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    file = pydicom.dataset.FileDataset(
        "", dataset, file_meta=meta, preamble=b"\0" * 128
    )
    buffer = io.BytesIO()
    pydicom.dcmwrite(buffer, file, enforce_file_format=True)
    return buffer.getvalue()
