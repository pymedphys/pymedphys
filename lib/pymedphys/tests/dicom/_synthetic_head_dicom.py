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

"""CT Image and RT Structure Set files of the analytic head, for the
defacing tests. Every UID and value here is invented."""

from __future__ import annotations

import copy
import io
from collections.abc import Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import _synthetic_head as head

CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
RT_STRUCTURE_SET_STORAGE = "1.2.840.10008.5.1.4.1.1.481.3"
EXPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2.1"
ROOT = "2.25.1234567890123456789"
FRAME = ROOT + ".1"
SERIES = ROOT + ".2"
STUDY = ROOT + ".3"


def ct_files(
    scan: head.Scan,
    *heads: head.Head,
    series: str = SERIES,
    frame: str = FRAME,
    intercept: float = -1024.0,
    signed: bool = True,
    bits_stored: int = 16,
    padding: int | None = None,
    template: pydicom.Dataset | None = None,
) -> list[bytes]:
    """Each slice of the scan of the heads as a CT Image file.

    The slices' stored values are the heads' Hounsfield units less
    ``intercept``, rounded and clipped to what ``bits_stored`` holds; where
    ``padding`` is given, it is Pixel Padding Value, and the stored value of
    each pixel outside the heads' skin. ``template``, such as a CT Image of
    the synthetic corpus, gives every other attribute.
    """
    low, high = (
        (-(1 << (bits_stored - 1)), (1 << (bits_stored - 1)) - 1)
        if signed
        else (0, (1 << bits_stored) - 1)
    )
    files = []
    for index, values in enumerate(scan.slices(*heads)):
        stored = np.clip(np.rint(values - intercept), low, high)
        if padding is not None:
            stored[values < -900] = padding
        dataset = _dataset(CT_IMAGE_STORAGE, f"{series}.{index + 1}", template)
        dataset.Modality = "CT"
        dataset.SeriesInstanceUID = series
        dataset.FrameOfReferenceUID = frame
        dataset.InstanceNumber = index + 1
        dataset.ImagePositionPatient = [_ds(v) for v in scan.positions[index]]
        dataset.ImageOrientationPatient = [_ds(v) for v in scan.orientation]
        dataset.PixelSpacing = [_ds(v) for v in scan.spacing]
        dataset.Rows, dataset.Columns = scan.shape
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = "MONOCHROME2"
        dataset.BitsAllocated = 16
        dataset.BitsStored = bits_stored
        dataset.HighBit = bits_stored - 1
        dataset.PixelRepresentation = int(signed)
        dataset.RescaleIntercept = _ds(intercept)
        dataset.RescaleSlope = "1"
        if padding is not None:
            dataset.PixelPaddingValue = padding
            dataset["PixelPaddingValue"].VR = "SS" if signed else "US"
        words = stored.astype("<i2" if signed else "<u2")
        dataset.PixelData = words.tobytes()
        dataset["PixelData"].VR = "OW"
        files.append(_written(dataset))
    return files


def structure_set(
    rois: Sequence[tuple[str, np.ndarray]],
    *,
    frame: str = FRAME,
    template: pydicom.Dataset | None = None,
) -> bytes:
    """An RT Structure Set with one ROI for each RT ROI Interpreted Type
    and its points, x, y, and z in rows, as one closed planar contour."""
    dataset = _dataset(RT_STRUCTURE_SET_STORAGE, ROOT + ".4.1", template)
    dataset.Modality = "RTSTRUCT"
    dataset.StructureSetLabel = "S"
    frames = pydicom.Dataset()
    frames.FrameOfReferenceUID = frame
    dataset.ReferencedFrameOfReferenceSequence = [frames]
    dataset.StructureSetROISequence = []
    dataset.ROIContourSequence = []
    dataset.RTROIObservationsSequence = []
    for number, (kind, points) in enumerate(rois, start=1):
        roi = pydicom.Dataset()
        roi.ROINumber = number
        roi.ReferencedFrameOfReferenceUID = frame
        roi.ROIName = f"R{number}"
        roi.ROIGenerationAlgorithm = "MANUAL"
        dataset.StructureSetROISequence.append(roi)
        contour = pydicom.Dataset()
        contour.ContourGeometricType = "CLOSED_PLANAR"
        contour.NumberOfContourPoints = len(points)
        contour.ContourData = [_ds(v) for v in np.ravel(points)]
        item = pydicom.Dataset()
        item.ReferencedROINumber = number
        item.ROIDisplayColor = [255, 0, 0]
        item.ContourSequence = [contour]
        dataset.ROIContourSequence.append(item)
        observation = pydicom.Dataset()
        observation.ObservationNumber = number
        observation.ReferencedROINumber = number
        observation.RTROIInterpretedType = kind
        observation.ROIInterpreter = ""
        dataset.RTROIObservationsSequence.append(observation)
    return _written(dataset)


def square(centre: Sequence[float], half: float = 2.0) -> np.ndarray:
    """A square contour in the axial plane about ``centre``."""
    x, y, z = centre
    return np.array(
        [
            (x - half, y - half, z),
            (x + half, y - half, z),
            (x + half, y + half, z),
            (x - half, y + half, z),
        ]
    )


def _dataset(
    sop_class: str, instance: str, template: pydicom.Dataset | None
) -> pydicom.Dataset:
    if template is None:
        dataset = pydicom.Dataset()
        dataset.PatientName = "Head^Analytic"
        dataset.PatientID = "H1"
        dataset.StudyInstanceUID = STUDY
        dataset.SeriesInstanceUID = ROOT + ".5"
        dataset.StudyDate = "20260101"
    else:
        dataset = copy.deepcopy(template)
        for keyword in ("PixelData", "PixelPaddingValue"):
            if keyword in dataset:
                del dataset[keyword]
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = instance
    meta = pydicom.dataset.FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    meta.MediaStorageSOPInstanceUID = instance
    meta.TransferSyntaxUID = EXPLICIT_VR_LITTLE_ENDIAN
    dataset.file_meta = meta
    return dataset


def _written(dataset: pydicom.Dataset) -> bytes:
    buffer = io.BytesIO()
    dataset.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()


def _ds(value: float) -> str:
    """A DS value of up to 16 characters."""
    text = f"{float(value):.6g}"
    return "0" if text == "-0" else text
