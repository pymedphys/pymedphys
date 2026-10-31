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

"""CT Image, RT Structure Set, RT Dose, PET Image, and Segmentation files of
the analytic head, and multi-frame CT and PET instances of its slices, for
the defacing tests. Every UID and value here is invented."""

from __future__ import annotations

import copy
import io
from collections.abc import Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from . import _synthetic_head as head

CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
ENHANCED_CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2.1"
LEGACY_CONVERTED_ENHANCED_CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2.2"
ENHANCED_PET_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.130"
LEGACY_CONVERTED_ENHANCED_PET_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.128.1"
RT_STRUCTURE_SET_STORAGE = "1.2.840.10008.5.1.4.1.1.481.3"
RT_DOSE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.2"
PET_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.128"
SEGMENTATION_STORAGE = "1.2.840.10008.5.1.4.1.1.66.4"
LABEL_MAP_SEGMENTATION_STORAGE = "1.2.840.10008.5.1.4.1.1.66.7"
AXIAL = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
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
        files.append(written(dataset))
    return files


# The functional groups that place and rescale a frame, by the attributes
# that each holds.
GROUPS = {
    "PlanePositionSequence": ("ImagePositionPatient",),
    "PlaneOrientationSequence": ("ImageOrientationPatient",),
    "PixelMeasuresSequence": ("PixelSpacing",),
    "PixelValueTransformationSequence": (
        "RescaleIntercept",
        "RescaleSlope",
        "RescaleType",
    ),
}


def multi_frame(
    slices: Sequence[bytes],
    *,
    sop_class: str = ENHANCED_CT_IMAGE_STORAGE,
    instance: str = ROOT + ".6.1",
    shared: Sequence[str] = (
        "PlaneOrientationSequence",
        "PixelMeasuresSequence",
        "PixelValueTransformationSequence",
    ),
    rescale_type: str | None = "HU",
    template: pydicom.Dataset | None = None,
) -> bytes:
    """One multi-frame instance of ``sop_class`` whose frames are the
    single-frame files' slices, in their order.

    Each frame is placed and rescaled by functional groups: each group named
    in ``shared`` in the Shared Functional Groups Sequence, from the first
    slice, and every other in the frame's item of the Per-frame Functional
    Groups Sequence, from its slice. Rescale Type is ``rescale_type``, or
    left out where it is None. Every other attribute is the first slice's,
    less those that the groups hold, or, where ``template`` is given, such
    as the synthetic corpus' Enhanced PET Image, the template's, with the
    first slice's Image Pixel attributes and Frame of Reference UID.
    """
    datasets = [pydicom.dcmread(io.BytesIO(each)) for each in slices]
    first = datasets[0]
    dataset = copy.deepcopy(first if template is None else template)
    for keyword in (
        *(k for held in GROUPS.values() for k in held),
        "PixelData",
        "PixelPaddingValue",
        "SharedFunctionalGroupsSequence",
        "PerFrameFunctionalGroupsSequence",
    ):
        if keyword in dataset:
            del dataset[keyword]
    for keyword in (
        "Rows",
        "Columns",
        "SamplesPerPixel",
        "PhotometricInterpretation",
        "BitsAllocated",
        "BitsStored",
        "HighBit",
        "PixelRepresentation",
        "PixelPaddingValue",
        "FrameOfReferenceUID",
    ):
        if keyword in first:
            dataset[keyword] = copy.deepcopy(first[keyword])
    if template is not None:
        dataset.file_meta = copy.deepcopy(first.file_meta)
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = instance
    dataset.file_meta.MediaStorageSOPClassUID = sop_class
    dataset.file_meta.MediaStorageSOPInstanceUID = instance
    dataset.InstanceNumber = 1

    def group(source: pydicom.Dataset, keyword: str) -> pydicom.Dataset:
        item = pydicom.Dataset()
        for attribute in GROUPS[keyword]:
            if attribute == "RescaleType":
                if rescale_type is not None:
                    item.RescaleType = rescale_type
            elif attribute in source:
                setattr(item, attribute, source[attribute].value)
        if keyword == "PixelValueTransformationSequence":
            if "RescaleIntercept" not in item:
                item.RescaleIntercept = "0"
            if "RescaleSlope" not in item:
                item.RescaleSlope = "1"
        return item

    common = pydicom.Dataset()
    for keyword in shared:
        setattr(common, keyword, [group(first, keyword)])
    dataset.SharedFunctionalGroupsSequence = [common]
    dataset.PerFrameFunctionalGroupsSequence = []
    for each in datasets:
        item = pydicom.Dataset()
        for keyword in GROUPS:
            if keyword not in shared:
                setattr(item, keyword, [group(each, keyword)])
        dataset.PerFrameFunctionalGroupsSequence.append(item)
    dataset.NumberOfFrames = len(datasets)
    dataset.PixelData = b"".join(each.PixelData for each in datasets)
    dataset["PixelData"].VR = "OW"
    return written(dataset)


def structure_set(
    rois: Sequence[tuple[str, np.ndarray | list[np.ndarray]]],
    *,
    frame: str = FRAME,
    template: pydicom.Dataset | None = None,
    names: Sequence[str] | None = None,
) -> bytes:
    """An RT Structure Set with one ROI for each RT ROI Interpreted Type
    and its points, x, y, and z in rows, as one closed planar contour, or
    for each type and list of such contours; each ROI is named by
    ``names``, or ``R1`` onwards."""
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
        roi.ROIName = f"R{number}" if names is None else names[number - 1]
        roi.ROIGenerationAlgorithm = "MANUAL"
        dataset.StructureSetROISequence.append(roi)
        item = pydicom.Dataset()
        item.ReferencedROINumber = number
        item.ROIDisplayColor = [255, 0, 0]
        item.ContourSequence = []
        for each in points if isinstance(points, list) else [points]:
            contour = pydicom.Dataset()
            contour.ContourGeometricType = "CLOSED_PLANAR"
            contour.NumberOfContourPoints = len(each)
            contour.ContourData = [_ds(v) for v in np.ravel(each)]
            item.ContourSequence.append(contour)
        dataset.ROIContourSequence.append(item)
        observation = pydicom.Dataset()
        observation.ObservationNumber = number
        observation.ReferencedROINumber = number
        observation.RTROIInterpretedType = kind
        observation.ROIInterpreter = ""
        dataset.RTROIObservationsSequence.append(observation)
    return written(dataset)


def dose(
    stored: np.ndarray,
    *,
    position: Sequence[float],
    spacing: Sequence[float],
    offsets: Sequence[float] | None,
    orientation: Sequence[float] = AXIAL,
    frame: str = FRAME,
    instance: str = ROOT + ".6.1",
    template: pydicom.Dataset | None = None,
) -> bytes:
    """An RT Dose of 32-bit stored values, frames by rows by columns,
    signed where ``stored`` is, with Dose Grid Scaling 0.001.

    ``spacing`` is Pixel Spacing, between rows then between columns, and
    ``offsets`` Grid Frame Offset Vector, left out where None. ``template``,
    such as the synthetic corpus' RT Dose, gives every other attribute.
    """
    stored = np.asarray(stored)
    signed = bool(np.issubdtype(stored.dtype, np.signedinteger))
    dataset = _dataset(RT_DOSE_STORAGE, instance, template)
    dataset.Modality = "RTDOSE"
    dataset.FrameOfReferenceUID = frame
    dataset.ImagePositionPatient = [_ds(v) for v in position]
    dataset.ImageOrientationPatient = [_ds(v) for v in orientation]
    dataset.PixelSpacing = [_ds(v) for v in spacing]
    if offsets is not None:
        dataset.GridFrameOffsetVector = [_ds(v) for v in offsets]
    elif "GridFrameOffsetVector" in dataset:
        del dataset.GridFrameOffsetVector
    dataset.NumberOfFrames = stored.shape[0]
    dataset.FrameIncrementPointer = 0x3004000C
    dataset.Rows, dataset.Columns = stored.shape[1:]
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 32
    dataset.BitsStored = 32
    dataset.HighBit = 31
    dataset.PixelRepresentation = int(signed)
    dataset.DoseUnits = "GY"
    dataset.DoseType = "PHYSICAL"
    dataset.DoseSummationType = "PLAN"
    dataset.DoseGridScaling = "0.001"
    dataset.PixelData = stored.astype("<i4" if signed else "<u4").tobytes()
    dataset["PixelData"].VR = "OW"
    return written(dataset)


def pet(
    stored: np.ndarray,
    *,
    position: Sequence[float],
    spacing: Sequence[float],
    frame: str = FRAME,
    instance: str = ROOT + ".7.1",
    template: pydicom.Dataset | None = None,
) -> bytes:
    """A PET Image slice in the axial plane of 16-bit unsigned stored
    values, rows by columns, with Rescale Slope 1 and Rescale Intercept 0.

    ``spacing`` is Pixel Spacing, between rows then between columns.
    ``template``, such as the synthetic corpus' PET Image, gives every
    other attribute.
    """
    dataset = _dataset(PET_IMAGE_STORAGE, instance, template)
    dataset.Modality = "PT"
    dataset.FrameOfReferenceUID = frame
    dataset.ImagePositionPatient = [_ds(v) for v in position]
    dataset.ImageOrientationPatient = [_ds(v) for v in AXIAL]
    dataset.PixelSpacing = [_ds(v) for v in spacing]
    dataset.Rows, dataset.Columns = np.shape(stored)
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.RescaleSlope = "1"
    dataset.RescaleIntercept = "0"
    dataset.PixelData = np.asarray(stored).astype("<u2").tobytes()
    dataset["PixelData"].VR = "OW"
    return written(dataset)


def segmentation(
    scan: head.Scan,
    masks: Sequence[np.ndarray],
    *,
    kind: str = "BINARY",
    frame: str | None = FRAME,
    series: str | None = SERIES,
    instance: str = ROOT + ".8.1",
    codes: Sequence[tuple[str, str, str]] | None = None,
    keep_empty: bool = False,
    template: pydicom.Dataset | None = None,
) -> bytes:
    """A Segmentation of the scan with a segment for each mask, slices by
    rows by columns, numbered from 1.

    Of ``kind`` BINARY, with a frame for each slice that a segment holds, or
    for every slice where ``keep_empty``, segment by segment, and its 1-bit
    pixels packed across frames; FRACTIONAL, framed so, of 8-bit
    probabilities, 255 where the mask holds a pixel; or LABELMAP, of 8-bit
    pixels, a frame for each slice, each pixel holding the number of the
    last mask that holds it, or 0, the Pixel Padding Value, for none. Each
    segment's Segmented Property Type is ``codes``' (scheme, value, meaning),
    or Tissue's. It references ``series`` where given, and is in ``frame``.
    """
    masks = [np.asarray(mask, bool) for mask in masks]
    labelmap = kind == "LABELMAP"
    dataset = _dataset(
        LABEL_MAP_SEGMENTATION_STORAGE if labelmap else SEGMENTATION_STORAGE,
        instance,
        template,
    )
    dataset.Modality = "SEG"
    dataset.SeriesInstanceUID = ROOT + ".8"
    if frame is not None:
        dataset.FrameOfReferenceUID = frame
    if series is not None:
        referenced = pydicom.Dataset()
        referenced.SeriesInstanceUID = series
        referenced.ReferencedInstanceSequence = []
        dataset.ReferencedSeriesSequence = [referenced]
    dataset.SegmentationType = kind
    if kind == "FRACTIONAL":
        dataset.SegmentationFractionalType = "PROBABILITY"
        dataset.MaximumFractionalValue = 255
    dataset.SegmentSequence = []
    for number in range(1, len(masks) + 1):
        segment = pydicom.Dataset()
        segment.SegmentNumber = number
        segment.SegmentLabel = f"S{number}"
        segment.SegmentAlgorithmType = "MANUAL"
        scheme, value, meaning = (
            ("SCT", "85756007", "Tissue") if codes is None else codes[number - 1]
        )
        for keyword, code in (
            ("SegmentedPropertyCategoryCodeSequence", ("SCT", "85756007", "Tissue")),
            ("SegmentedPropertyTypeCodeSequence", (scheme, value, meaning)),
        ):
            item = pydicom.Dataset()
            item.CodingSchemeDesignator, item.CodeValue, item.CodeMeaning = code
            setattr(segment, keyword, [item])
        dataset.SegmentSequence.append(segment)
    orientation = pydicom.Dataset()
    orientation.ImageOrientationPatient = [_ds(v) for v in scan.orientation]
    measures = pydicom.Dataset()
    measures.PixelSpacing = [_ds(v) for v in scan.spacing]
    # The scan's own slab, as a writer such as highdicom keeps its source's.
    step = 1.0
    if len(scan.positions) > 1:
        step = float(np.linalg.norm(np.subtract(scan.positions[1], scan.positions[0])))
    measures.SliceThickness = measures.SpacingBetweenSlices = _ds(step)
    shared = pydicom.Dataset()
    shared.PlaneOrientationSequence = [orientation]
    shared.PixelMeasuresSequence = [measures]
    dataset.SharedFunctionalGroupsSequence = [shared]
    planes: list[np.ndarray] = []
    dataset.PerFrameFunctionalGroupsSequence = []
    if labelmap:
        chosen = [(index, None) for index in range(len(scan.positions))]
    else:
        chosen = [
            (index, number)
            for number, mask in enumerate(masks, start=1)
            for index in range(len(scan.positions))
            if keep_empty or mask[index].any()
        ]
    for index, number in chosen:
        if number is None:
            plane = np.zeros(scan.shape, np.uint8)
            for each, mask in enumerate(masks, start=1):
                plane[mask[index]] = each
        else:
            plane = masks[number - 1][index].astype(np.uint8)
        planes.append(plane)
        group = pydicom.Dataset()
        position = pydicom.Dataset()
        position.ImagePositionPatient = [_ds(v) for v in scan.positions[index]]
        group.PlanePositionSequence = [position]
        if number is not None:
            identified = pydicom.Dataset()
            identified.ReferencedSegmentNumber = number
            group.SegmentIdentificationSequence = [identified]
        dataset.PerFrameFunctionalGroupsSequence.append(group)
    dataset.NumberOfFrames = len(planes)
    dataset.Rows, dataset.Columns = scan.shape
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.PixelRepresentation = 0
    stacked = np.stack(planes)
    if kind == "FRACTIONAL":
        stacked = stacked * np.uint8(255)
    if labelmap:
        dataset.PixelPaddingValue = 0
        dataset["PixelPaddingValue"].VR = "US"
    if kind == "BINARY":
        dataset.BitsAllocated = dataset.BitsStored = 1
        dataset.HighBit = 0
        data = bytes(np.packbits(stacked.ravel(), bitorder="little"))
    else:
        dataset.BitsAllocated = dataset.BitsStored = 8
        dataset.HighBit = 7
        data = stacked.tobytes()
    dataset.PixelData = data + b"\0" * (len(data) % 2)
    dataset["PixelData"].VR = "OB"
    return written(dataset)


def ellipse(
    centre: Sequence[float], axes: Sequence[float], count: int = 72
) -> np.ndarray:
    """An elliptical contour in the axial plane about ``centre``, of
    semi-axes along x and y."""
    x, y, z = centre
    angles = 2 * np.pi * np.arange(count) / count
    return np.column_stack(
        [
            x + axes[0] * np.cos(angles),
            y + axes[1] * np.sin(angles),
            np.full(count, z),
        ]
    )


def circle(centre: Sequence[float], radius: float, count: int = 24) -> np.ndarray:
    """A circular contour in the axial plane about ``centre``."""
    return ellipse(centre, (radius, radius), count)


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


def written(dataset: pydicom.Dataset) -> bytes:
    buffer = io.BytesIO()
    dataset.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()


def _ds(value: float) -> str:
    """A DS value of up to 16 characters."""
    text = f"{float(value):.6g}"
    return "0" if text == "-0" else text
