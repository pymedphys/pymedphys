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

"""Legacy Converted Enhanced CT, MR, and PET instances, converted from
classic single-frame images for the text detector's evaluation (D-056).

To measure Legacy Converted Enhanced images on real scans, the evaluation
converts classic CT Image, MR Image, and Positron Emission
Tomography Image series, in memory on the runner, into Legacy Converted
Enhanced CT, MR, and PET Image instances (PS3.3 A.70 to A.72), and reads
their frames as a run reads them
(:class:`~.text_evaluation_converted.ConvertedCase`), so that the
multi-frame path is measured on real images. The conversion is the
evaluation's own, built on pydicom, and leaves every pixel unchanged: each
frame holds the stored values that a run gives the text detector for its
classic image, in the same Bits Allocated, Bits Stored, and Pixel
Representation.

:func:`convert` follows PS3.3's rules for these IODs:

* attributes that all the images share, that the IOD defines at the top
  level, are kept there, with the shipped tables of PS3.3
  (:func:`~.iods.load_iod_tables`) deciding which;
* attributes that a Functional Group Macro holds are moved into it: Pixel
  Measures, Plane Position and Orientation, Frame VOI LUT, Pixel Value
  Transformation (the CT macro for CT), the modality's Frame Type, Frame
  Content, Referenced Image, Derivation Image, Irradiation Event
  Identification, and Frame Anatomy, whose Anatomic Region Sequence is
  Annex L's code for Body Part Examined
  (:func:`~.codes.load_anatomic_regions`); a macro is shared when its item
  is the same for every frame;
* every other attribute, standard or private, goes into the Unassigned
  Shared Converted Attributes Sequence where all the images hold the same
  value, an absent attribute counting as empty, and into each frame's
  Unassigned Per-Frame Converted Attributes Sequence otherwise, as do the
  originals of attributes whose top-level value the conversion replaces,
  such as Instance Number and Series Instance UID;
* each frame's Image Frame Conversion Source macro names the image it came
  from.

A series is converted in groups of images that share their SOP Class,
Study, Frame of Reference, character set, and pixel layout
(:func:`convertible_groups`), one instance for each, its frames in order of
Instance Number. An image that PS3.3 does not let the IOD hold unchanged
is refused, by a code (:class:`ConversionRefused`): a Photometric
Interpretation other than MONOCHROME2, Bits Allocated and Bits Stored that
the IOD does not allow (CT 16 with 12 or 16, MR 8 with 8 or 16 with 12 or
16, PET 16 with 16), a Modality LUT, a multi-energy CT, or a Type 1 top-
level attribute that the images do not give. The converted instance's
UIDs are derived from name-based UUIDs of the originals' (PS3.5 B.2), so
that a conversion is repeatable,
and the instance never leaves the runner.

Two values are the conversion's own, where the images do not give them:
Frame Laterality, which Frame Anatomy requires, is "U" (unpaired) where no
image records a laterality, since classic images record Laterality
(0020,0060) only for paired body parts; and Frame VOI LUT, which the CT and
PET IODs require, spans the series' rescaled values where an image has no
window. Content Qualification, which the PET IOD requires, is RESEARCH
where the images do not give it, as it is of these instances.
"""

from __future__ import annotations

import collections
import dataclasses
import functools
import io
import math
import uuid
from collections.abc import Mapping, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from .codes import load_anatomic_regions
from .iods import IOD, load_iod_tables
from .text_evaluation_lce_values import (
    _Key,
    _acquisition_datetime,
    _canonical,
    _datetime,
    _elements,
    _geometry,
    _has,
    _items_of,
    _key_order,
    _laterality,
    _number,
    _place,
    _string,
    _study_item,
    _tag,
    _tag_number,
    _tag_text,
    _values,
    copy_element,
)

CT_IMAGE = "1.2.840.10008.5.1.4.1.1.2"
MR_IMAGE = "1.2.840.10008.5.1.4.1.1.4"
PET_IMAGE = "1.2.840.10008.5.1.4.1.1.128"
LCE_CT_IMAGE = "1.2.840.10008.5.1.4.1.1.2.2"
LCE_MR_IMAGE = "1.2.840.10008.5.1.4.1.1.4.4"
LCE_PET_IMAGE = "1.2.840.10008.5.1.4.1.1.128.1"


@dataclasses.dataclass(frozen=True)
class _Target:
    """What one classic SOP Class converts to."""

    sop_class: str
    iod: str
    classic_iod: str
    modality: str
    frame_type: str
    # The Pixel Value Transformation macro's usage: "M" or "U".
    transformation: str
    # The Frame VOI LUT macro's usage: "M" or "U".
    window: str
    # Each allowed Bits Allocated, with the Bits Stored it allows.
    bits: Mapping[int, frozenset[int]]


TARGETS: Mapping[str, _Target] = {
    CT_IMAGE: _Target(
        LCE_CT_IMAGE,
        "Legacy Converted Enhanced CT Image",
        "CT Image",
        "CT",
        "CTImageFrameTypeSequence",
        "M",
        "M",
        {16: frozenset({12, 16})},
    ),
    MR_IMAGE: _Target(
        LCE_MR_IMAGE,
        "Legacy Converted Enhanced MR Image",
        "MR Image",
        "MR",
        "MRImageFrameTypeSequence",
        "U",
        "U",
        {8: frozenset({8}), 16: frozenset({12, 16})},
    ),
    PET_IMAGE: _Target(
        LCE_PET_IMAGE,
        "Legacy Converted Enhanced PET Image",
        "Positron Emission Tomography Image",
        "PT",
        "PETFrameTypeSequence",
        "M",
        "M",
        {16: frozenset({16})},
    ),
}
_SALT = "pymedphys-text-detector-evaluation-lce/1"

# Attributes never carried: the file's meta information, and those tied to
# the classic instance's encoding or integrity, which a converted instance
# cannot keep.
_NEVER = frozenset(
    {
        0x00080001,  # Length to End (retired)
        0x00280008,  # Number of Frames
        0x00287FE0,  # Pixel Data Provider URL
        0x04000500,  # Encrypted Attributes Sequence
        0x4FFE0001,  # MAC Parameters Sequence
        0x7FE00001,  # Extended Offset Table
        0x7FE00002,  # Extended Offset Table Lengths
        0x7FE00003,  # Encapsulated Pixel Data Value Total Length
        0x7FE00008,  # Float Pixel Data
        0x7FE00009,  # Double Float Pixel Data
        0x7FE00010,  # Pixel Data
        0xFFFAFFFA,  # Digital Signatures Sequence
        0xFFFCFFFC,  # Data Set Trailing Padding
    }
)
# Recorded in each frame's Conversion Source Attributes Sequence instead of
# the unassigned attributes, as PS3.3 C.7.6.16.2.25 says.
_CONVERSION_SOURCE = frozenset({0x00080016, 0x00080018})
# What the converted instance's top level holds that the conversion sets
# itself: its identity, layout, and summaries of the frames.
_SET = frozenset(
    {
        0x00080008,  # Image Type
        0x00080016,  # SOP Class UID
        0x00080018,  # SOP Instance UID
        0x00080023,  # Content Date
        0x00080033,  # Content Time
        0x0008002A,  # Acquisition DateTime
        0x00089205,  # Pixel Presentation
        0x00089206,  # Volumetric Properties
        0x00089207,  # Volume Based Calculation Technique
        0x00189004,  # Content Qualification
        0x00189100,  # Resonant Nucleus
        0x0020000E,  # Series Instance UID
        0x00200013,  # Instance Number
        0x00280301,  # Burned In Annotation
        0x00280302,  # Recognizable Visual Features
        0x00282110,  # Lossy Image Compression
        0x00282112,  # Lossy Image Compression Ratio
        0x00282114,  # Lossy Image Compression Method
        0x00089092,  # Referenced Image Evidence Sequence
        0x00089154,  # Source Image Evidence Sequence
        0x00400555,  # Acquisition Context Sequence
        0x20500020,  # Presentation LUT Shape
    }
)
# The pixel layout, which a group of images shares.
_LAYOUT = (
    "Rows",
    "Columns",
    "SamplesPerPixel",
    "PhotometricInterpretation",
    "BitsAllocated",
    "BitsStored",
    "HighBit",
    "PixelRepresentation",
)
_GROUPED = (
    "SOPClassUID",
    "StudyInstanceUID",
    "FrameOfReferenceUID",
    "SpecificCharacterSet",
)


class ConversionRefused(Exception):
    """Images that this conversion cannot convert unchanged, for why: a code
    such as ``"photometric-interpretation"``, which quotes no value."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclasses.dataclass(frozen=True)
class ClassicImage:
    """A classic single-frame image and its stored values, as a run gives
    them to the text detector.

    Attributes
    ----------
    dataset : pydicom.Dataset
    stored : numpy.ndarray
        Rows by columns of integer stored values.
    """

    dataset: pydicom.Dataset
    stored: np.ndarray


def convertible_groups(
    images: Sequence[ClassicImage],
) -> tuple[list[list[ClassicImage]], list[tuple[ClassicImage, str]]]:
    """The images of a series in the groups that are each converted to one
    instance, in order of their first image, each in order of Instance
    Number and then SOP Instance UID; and each image that cannot be
    converted, with why."""
    groups: dict[tuple, list[ClassicImage]] = {}
    refused = []
    for image in images:
        reason = _refusal(image)
        if reason is not None:
            refused.append((image, reason))
            continue
        key = tuple(_canonical(image.dataset.get(name)) for name in _GROUPED + _LAYOUT)
        groups.setdefault(key, []).append(image)
    return [sorted(group, key=_order) for group in groups.values()], refused


def _order(image: ClassicImage) -> tuple[float, str]:
    number = _number(image.dataset, "InstanceNumber")
    return (
        math.inf if number is None else number,
        _string(image.dataset, "SOPInstanceUID"),
    )


def _refusal(  # pylint: disable = too-many-return-statements
    image: ClassicImage,
) -> str | None:
    dataset = image.dataset
    target = TARGETS.get(_string(dataset, "SOPClassUID"))
    if target is None:
        return "not-a-classic-ct-mr-or-pet-image"
    if _number(dataset, "NumberOfFrames") not in (None, 1):
        return "not-single-frame"
    if _string(dataset, "PhotometricInterpretation") != "MONOCHROME2":
        return "photometric-interpretation"
    if _number(dataset, "SamplesPerPixel") != 1:
        return "samples-per-pixel"
    allocated = _number(dataset, "BitsAllocated")
    stored = _number(dataset, "BitsStored")
    allowed = target.bits.get(int(allocated)) if allocated is not None else None
    if allowed is None or stored is None or int(stored) not in allowed:
        return "bits-not-allowed"
    if _number(dataset, "HighBit") != stored - 1:
        return "high-bit"
    if "ModalityLUTSequence" in dataset:
        return "modality-lut"
    if _string(dataset, "MultienergyCTAcquisition") == "YES":
        return "multi-energy"
    rows, columns = _number(dataset, "Rows"), _number(dataset, "Columns")
    if image.stored.shape != (rows, columns) or image.stored.dtype.kind not in "iu":
        return "stored-values"
    if (
        _string(dataset, "SOPInstanceUID") == ""
        or _string(dataset, "SeriesInstanceUID") == ""
    ):
        return "uid-missing"
    return None


def convert(
    images: Sequence[ClassicImage],
    known: Sequence[pydicom.Dataset] = (),
) -> pydicom.Dataset:
    """Convert one group of classic images (:func:`convertible_groups`) to a
    Legacy Converted Enhanced instance, its frames in the order given.

    The evidence of the images that its frames reference (PS3.3 C.8.13.2.1.2)
    names those of ``images`` and ``known``, such as the other images of
    their series, by their study and series; the classic images do not say
    which study and series another image is in, so one that is neither is
    left out of it.

    Raises
    ------
    ConversionRefused
        If the images are not one group, or the instance would lack an
        attribute that its IOD requires and the images do not give.
    """
    if not images:
        raise ConversionRefused("no-images")
    groups, refused = convertible_groups(images)
    if refused:
        raise ConversionRefused(refused[0][1])
    if len(groups) != 1:
        raise ConversionRefused("not-one-group")
    return _Conversion(tuple(images), tuple(known)).dataset()


def encode(dataset: pydicom.Dataset) -> bytes:
    """A converted instance as a PS3.10 file in Explicit VR Little Endian."""
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


class _Conversion:
    """The state of one conversion."""

    def __init__(
        self, images: tuple[ClassicImage, ...], known: tuple[pydicom.Dataset, ...]
    ) -> None:
        self.images = images
        # Each image whose study and series are known, by its SOP Instance UID.
        self.known = {
            _string(each, "SOPInstanceUID"): (
                _string(each, "StudyInstanceUID"),
                _string(each, "SeriesInstanceUID"),
            )
            for each in (*known, *(image.dataset for image in images))
        }
        self.datasets = [image.dataset for image in images]
        self.target = TARGETS[_string(self.datasets[0], "SOPClassUID")]
        tables = load_iod_tables()
        self.iod: IOD = tables.iods[self.target.iod]
        self.classic_modules = {
            module.module for module in tables.iods[self.target.classic_iod].modules
        }
        self.elements = [_elements(dataset) for dataset in self.datasets]
        # Keys that a Functional Group Macro holds, which no other place does.
        self.assigned: set[_Key] = set()
        self.top = pydicom.Dataset()
        self.shared = pydicom.Dataset()
        self.per_frame = [pydicom.Dataset() for _ in images]

    def dataset(self) -> pydicom.Dataset:
        for macro in (
            self._pixel_measures,
            self._plane_position,
            self._plane_orientation,
            self._frame_type,
            self._pixel_value_transformation,
            self._frame_voi_lut,
            self._frame_content,
            self._referenced_image,
            self._derivation_image,
            self._irradiation_event,
            self._frame_anatomy,
            self._conversion_source,
        ):
            macro()
        self._identity()
        self._summaries()
        self._references()
        self._top_level()
        self._unassigned()
        self._required()
        self._pixel_data()
        self.top.SharedFunctionalGroupsSequence = [self.shared]
        self.top.PerFrameFunctionalGroupsSequence = self.per_frame
        return self.top

    # Functional groups -------------------------------------------------

    def _group(
        self,
        contents: Sequence[pydicom.Dataset],
        *,
        shared: bool = True,
        assigned: Sequence[str] = (),
    ) -> None:
        """Place one macro, given what it adds to each frame's functional
        group: in the shared group where that is the same for every frame
        and the macro may be shared, else in each frame's."""
        same = all(_canonical(each) == _canonical(contents[0]) for each in contents)
        targets = [self.shared] if shared and same else self.per_frame
        for group, content in zip(targets, contents):
            for element in content:
                group.add(element)
        self.assigned.update(_tag(keyword) for keyword in assigned)

    def _wrapped(
        self, sequence: str, items: Sequence[pydicom.Dataset]
    ) -> list[pydicom.Dataset]:
        """Each frame's item of a macro's sequence, as that frame's content."""
        contents = []
        for item in items:
            content = pydicom.Dataset()
            setattr(content, sequence, [item])
            contents.append(content)
        return contents

    def _copied(
        self, dataset: pydicom.Dataset, keywords: Sequence[str]
    ) -> pydicom.Dataset:
        item = pydicom.Dataset()
        for keyword in keywords:
            if keyword in dataset:
                item.add(copy_element(dataset[keyword]))
        return item

    def _pixel_measures(self) -> None:
        keywords = ("PixelSpacing", "SliceThickness", "SpacingBetweenSlices")
        if not all(_number(each, "PixelSpacing", 0) for each in self.datasets):
            raise ConversionRefused("pixel-spacing-missing")
        # Required for frames whose Volumetric Properties is VOLUME.
        if not all(_number(each, "SliceThickness") for each in self.datasets):
            raise ConversionRefused("slice-thickness-missing")
        items = [self._copied(each, keywords) for each in self.datasets]
        self._group(self._wrapped("PixelMeasuresSequence", items), assigned=keywords)

    def _plane_position(self) -> None:
        if not all(_has(each, "ImagePositionPatient") for each in self.datasets):
            raise ConversionRefused("image-position-missing")
        items = [
            self._copied(each, ("ImagePositionPatient",)) for each in self.datasets
        ]
        self._group(
            self._wrapped("PlanePositionSequence", items),
            assigned=("ImagePositionPatient",),
        )

    def _plane_orientation(self) -> None:
        if not all(_has(each, "ImageOrientationPatient") for each in self.datasets):
            raise ConversionRefused("image-orientation-missing")
        items = [
            self._copied(each, ("ImageOrientationPatient",)) for each in self.datasets
        ]
        self._group(
            self._wrapped("PlaneOrientationSequence", items),
            assigned=("ImageOrientationPatient",),
        )

    def frame_types(self) -> list[list[str]]:
        """Each frame's Frame Type (PS3.3 C.8.16.1): its image's Image Type
        Values 1 and 3, PRIMARY, and NONE for an original frame or its
        image's Value 4 otherwise; Value 3 is the series' geometry where the
        image gives none."""
        flavour = _geometry(self.datasets)
        types = []
        for dataset in self.datasets:
            values = [str(value).strip() for value in _values(dataset, "ImageType")]
            if not values or values[0] not in ("ORIGINAL", "DERIVED"):
                raise ConversionRefused("image-type")
            third = values[2] if len(values) > 2 and values[2] else flavour
            if values[0] == "ORIGINAL":
                fourth = "NONE"
            else:
                fourth = values[3] if len(values) > 3 else ""
            types.append([values[0], "PRIMARY", third, fourth])
        return types

    @functools.cached_property
    def _frame_types(self) -> list[list[str]]:
        return self.frame_types()

    def _frame_type(self) -> None:
        items = []
        for frame_type in self._frame_types:
            item = pydicom.Dataset()
            item.FrameType = frame_type
            item.PixelPresentation = "MONOCHROME"
            item.VolumetricProperties = "VOLUME"
            item.VolumeBasedCalculationTechnique = "NONE"
            items.append(item)
        self._group(
            self._wrapped(self.target.frame_type, items), assigned=("ImageType",)
        )

    def _pixel_value_transformation(self) -> None:
        keywords = ("RescaleIntercept", "RescaleSlope", "RescaleType")
        given = [
            _has(each, "RescaleIntercept") and _has(each, "RescaleSlope")
            for each in self.datasets
        ]
        if self.target.transformation == "U" and not any(given):
            return
        items = []
        for dataset, present in zip(self.datasets, given):
            item = pydicom.Dataset()
            if present:
                item.add(copy_element(dataset["RescaleIntercept"]))
                item.add(copy_element(dataset["RescaleSlope"]))
            else:
                item.RescaleIntercept = "0"
                item.RescaleSlope = "1"
            if self.target.modality == "CT":
                # Classic CT gives Rescale Type only where it is not HU.
                item.RescaleType = _string(dataset, "RescaleType") or "HU"
            else:
                item.RescaleType = "US"
            items.append(item)
        self._group(
            self._wrapped("PixelValueTransformationSequence", items), assigned=keywords
        )

    def _frame_voi_lut(self) -> None:
        keywords = (
            "WindowCenter",
            "WindowWidth",
            "WindowCenterWidthExplanation",
            "VOILUTFunction",
        )
        given = [
            _has(each, "WindowCenter") and _has(each, "WindowWidth")
            for each in self.datasets
        ]
        if self.target.window == "U" and not any(given):
            return
        spanned = None if all(given) else self._spanning_window()
        items = []
        for dataset, present in zip(self.datasets, given):
            if present:
                item = self._copied(dataset, keywords)
            else:
                item = pydicom.Dataset()
                item.WindowCenter, item.WindowWidth = spanned
            items.append(item)
        self._group(self._wrapped("FrameVOILUTSequence", items), assigned=keywords)

    def _spanning_window(self) -> tuple[pydicom.valuerep.DSfloat, ...]:
        """A window that spans the series' rescaled values."""
        low, high = math.inf, -math.inf
        for image in self.images:
            slope = _number(image.dataset, "RescaleSlope", 0) or 1.0
            intercept = _number(image.dataset, "RescaleIntercept", 0) or 0.0
            ends = (
                float(image.stored.min()) * slope + intercept,
                float(image.stored.max()) * slope + intercept,
            )
            low, high = min(low, *ends), max(high, *ends)
        width = max(high - low, 1.0)
        return (
            pydicom.valuerep.DSfloat((low + high) / 2, auto_format=True),
            pydicom.valuerep.DSfloat(width, auto_format=True),
        )

    def _frame_content(self) -> None:
        items = [pydicom.Dataset() for _ in self.datasets]
        if all(
            0 <= (_number(each, "AcquisitionNumber") or -1) < 1 << 16
            for each in self.datasets
        ):
            for item, dataset in zip(items, self.datasets):
                item.FrameAcquisitionNumber = int(_number(dataset, "AcquisitionNumber"))
            self.assigned.add(_tag("AcquisitionNumber"))
        if all(_has(each, "ImageComments") for each in self.datasets):
            for item, dataset in zip(items, self.datasets):
                item.FrameComments = dataset.ImageComments
            self.assigned.add(_tag("ImageComments"))
        times = [_acquisition_datetime(each) for each in self.datasets]
        for item, time in zip(items, times):
            if time:
                item.FrameAcquisitionDateTime = time
        if all(times):
            self.assigned.update(
                _tag(each)
                for each in (
                    "AcquisitionDate",
                    "AcquisitionTime",
                    "AcquisitionDateTime",
                )
            )
        self._group(self._wrapped("FrameContentSequence", items), shared=False)

    def _referenced_image(self) -> None:
        if any("ReferencedImageSequence" in each for each in self.datasets):
            items = [
                self._copied(each, ("ReferencedImageSequence",))
                for each in self.datasets
            ]
            for item in items:
                if "ReferencedImageSequence" not in item:
                    item.ReferencedImageSequence = []
            self._group(items, assigned=("ReferencedImageSequence",))

    def _derivation_image(self) -> None:
        keywords = (
            "DerivationDescription",
            "DerivationCodeSequence",
            "SourceImageSequence",
        )
        if any("SourceImageSequence" in each for each in self.datasets):
            items = []
            for dataset in self.datasets:
                derivation = self._copied(dataset, keywords)
                if "SourceImageSequence" not in derivation:
                    derivation.SourceImageSequence = []
                items.append(derivation)
            self._group(
                self._wrapped("DerivationImageSequence", items), assigned=keywords
            )

    def _irradiation_event(self) -> None:
        given = [_has(each, "IrradiationEventUID") for each in self.datasets]
        if self.target.modality == "MR" or not any(given):
            return
        if not all(given):
            raise ConversionRefused("irradiation-event-partial")
        items = [self._copied(each, ("IrradiationEventUID",)) for each in self.datasets]
        self._group(
            self._wrapped("IrradiationEventIdentificationSequence", items),
            assigned=("IrradiationEventUID",),
        )

    def _frame_anatomy(self) -> None:
        regions = {row.term: row for row in load_anatomic_regions().rows}
        coded = [
            "AnatomicRegionSequence" in each
            or _string(each, "BodyPartExamined") in regions
            for each in self.datasets
        ]
        if not any(coded):
            return
        items = []
        for dataset in self.datasets:
            item = pydicom.Dataset()
            if "AnatomicRegionSequence" in dataset:
                item.add(copy_element(dataset["AnatomicRegionSequence"]))
            else:
                row = regions.get(_string(dataset, "BodyPartExamined"))
                if row is None or not row.code_value:
                    raise ConversionRefused("anatomic-region-not-coded")
                code = pydicom.Dataset()
                code.CodeValue = row.code_value
                code.CodingSchemeDesignator = row.scheme_designator
                code.CodeMeaning = row.code_meaning
                item.AnatomicRegionSequence = [code]
            if "PrimaryAnatomicStructureSequence" in dataset:
                item.add(copy_element(dataset["PrimaryAnatomicStructureSequence"]))
            item.FrameLaterality = _laterality(dataset, item)
            items.append(item)
        self._group(
            self._wrapped("FrameAnatomySequence", items),
            assigned=("AnatomicRegionSequence", "PrimaryAnatomicStructureSequence"),
        )

    def _conversion_source(self) -> None:
        for group, dataset in zip(self.per_frame, self.datasets):
            item = pydicom.Dataset()
            item.ReferencedSOPClassUID = _string(dataset, "SOPClassUID")
            item.ReferencedSOPInstanceUID = _string(dataset, "SOPInstanceUID")
            group.ConversionSourceAttributesSequence = [item]

    # The top level -----------------------------------------------------

    def _identity(self) -> None:
        sources = [_string(each, "SOPInstanceUID") for each in self.datasets]
        series = _string(self.datasets[0], "SeriesInstanceUID")
        self.top.SOPClassUID = self.target.sop_class
        self.top.SOPInstanceUID = _uid("instance", *sources)
        self.top.SeriesInstanceUID = _uid("series", series)
        self.top.InstanceNumber = 1
        self.top.NumberOfFrames = len(self.images)

    def _summaries(self) -> None:
        """The top level's summaries of the frames (PS3.3 C.8.16.1 and the
        Enhanced CT, MR, and PET Image Modules)."""
        types = self._frame_types
        image_type = []
        for index in (0, 1, 2, 3):
            values = [each[index] for each in types]
            if index == 2:
                # Value 3 summarises; it is never MIXED.
                counts = collections.Counter(values)
                image_type.append(
                    min(counts.items(), key=lambda item: (-item[1], item[0]))[0]
                )
            elif len(set(values)) == 1:
                image_type.append(values[0])
            else:
                image_type.append("MIXED")
        self.top.ImageType = image_type
        self.top.PixelPresentation = "MONOCHROME"
        self.top.VolumetricProperties = "VOLUME"
        self.top.VolumeBasedCalculationTechnique = "NONE"
        self.top.PresentationLUTShape = "IDENTITY"
        content = sorted(
            filter(None, (_datetime(each, "Content") for each in self.datasets))
        )
        if not content:
            raise ConversionRefused("content-date-missing")
        self.top.ContentDate, self.top.ContentTime = content[0][:8], content[0][8:]
        acquired = sorted(filter(None, map(_acquisition_datetime, self.datasets)))
        if acquired:
            self.top.AcquisitionDateTime = acquired[0]
        for keyword, yes, no in (
            ("BurnedInAnnotation", "YES", "NO"),
            ("RecognizableVisualFeatures", "YES", "NO"),
            ("LossyImageCompression", "01", "00"),
        ):
            values = {_string(each, keyword) for each in self.datasets}
            if yes in values:
                setattr(self.top, keyword, yes)
            elif values == {no}:
                setattr(self.top, keyword, no)
        if self.top.get("LossyImageCompression") == "01":
            for keyword in (
                "LossyImageCompressionRatio",
                "LossyImageCompressionMethod",
            ):
                values = {_canonical(each.get(keyword)) for each in self.datasets}
                if len(values) != 1:
                    raise ConversionRefused("lossy-compression-history-differs")
                if keyword in self.datasets[0]:
                    self.top.add(copy_element(self.datasets[0][keyword]))
        self._shared_or_default(
            "ContentQualification", "RESEARCH" if self.target.modality == "PT" else None
        )
        if self.target.modality == "MR":
            nuclei = {_string(each, "ImagedNucleus") for each in self.datasets}
            if len(nuclei) == 1 and "" not in nuclei:
                self.top.ResonantNucleus = nuclei.pop()
        context = [each.get("AcquisitionContextSequence") for each in self.datasets]
        if len({_canonical(each) for each in context}) == 1 and context[0] is not None:
            self.top.add(copy_element(self.datasets[0]["AcquisitionContextSequence"]))
        else:
            self.top.AcquisitionContextSequence = []

    def _shared_or_default(self, keyword: str, default: str | None) -> None:
        values = {_canonical(each.get(keyword)) for each in self.datasets}
        if len(values) == 1 and keyword in self.datasets[0]:
            self.top.add(copy_element(self.datasets[0][keyword]))
        elif default is not None:
            setattr(self.top, keyword, default)

    def _top_level(self) -> None:
        """Copy each attribute that every image holds with the same value,
        that the IOD defines at the top level, and that nothing else sets or
        holds, unless it would begin a module of the IOD that the classic
        IOD lacks and the images do not complete (:meth:`_begins`)."""
        candidates = {}
        for key, elements in self._by_key().items():
            if not isinstance(key, int) or key in _NEVER or key in _SET:
                continue
            if key in self.assigned or key in self.top:
                continue
            if any(element is None for element in elements):
                continue
            if len({_canonical(element) for element in elements}) != 1:
                continue
            if not self.iod.lookup(_tag_text(key)):
                continue
            candidates[key] = elements[0]
        for key, element in candidates.items():
            if not self._begins(key, candidates):
                self.top.add(copy_element(element))

    def _begins(self, key: int, candidates: Mapping[int, pydicom.DataElement]) -> bool:
        """Whether an attribute would begin an incomplete module that the
        IOD has and the classic IOD lacks, such as Enhanced Contrast/Bolus,
        whose Contrast/Bolus Agent Sequence the classic Contrast/Bolus Module
        also holds, with less in its items. An attribute that a module of
        both IODs requires begins nothing."""
        definitions = self.iod.lookup(_tag_text(key))
        if any(
            each.module in self.classic_modules and each.type != "3"
            for each in definitions
        ):
            return False
        return any(
            each.module not in self.classic_modules
            and not self._complete(each.module, candidates)
            for each in definitions
        )

    def _complete(
        self, module: str, candidates: Mapping[int, pydicom.DataElement]
    ) -> bool:
        """Whether the candidates hold every Type 1 and 2 attribute of a
        module's top level, and of the items of its sequences that they
        hold, conditions aside."""
        for definition in self.iod.definitions:
            if definition.module != module or definition.type not in ("1", "2"):
                continue
            if len(definition.path) > 1 or "x" in definition.tag:
                continue
            tag = _tag_number(definition.tag)
            if not definition.path:
                element = candidates.get(tag)
                if element is None or (definition.type == "1" and element.is_empty):
                    return False
                continue
            sequence = candidates.get(_tag_number(definition.path[0]))
            if sequence is None or sequence.VR != "SQ":
                continue
            for item in sequence.value:
                if tag not in item or (definition.type == "1" and item[tag].is_empty):
                    return False
        return True

    def _references(self) -> None:
        """The evidence of the images that the frames reference, which names
        each whose study and series are known. The Common Instance
        Reference Module, which these IODs make optional, is not written."""
        found: dict[str, list[tuple[str, str]]] = {}
        for keyword in ("ReferencedImageSequence", "SourceImageSequence"):
            references = []
            for group in (self.shared, *self.per_frame):
                for item in _items_of(group, keyword):
                    references.append(
                        (
                            _string(item, "ReferencedSOPClassUID"),
                            _string(item, "ReferencedSOPInstanceUID"),
                        )
                    )
            found[keyword] = references
        evidence = {
            "ReferencedImageSequence": "ReferencedImageEvidenceSequence",
            "SourceImageSequence": "SourceImageEvidenceSequence",
        }
        for keyword, references in found.items():
            hierarchy = self._hierarchy(references)
            if hierarchy:
                setattr(
                    self.top,
                    evidence[keyword],
                    [_study_item(study, series) for study, series in hierarchy.items()],
                )

    def _hierarchy(
        self, references: Sequence[tuple[str, str]]
    ) -> dict[str, dict[str, dict[str, str]]]:
        """The references whose study and series are known, by study, then
        series, then SOP Instance UID, to SOP Class UID."""
        hierarchy: dict[str, dict[str, dict[str, str]]] = {}
        for sop_class, instance in references:
            if instance not in self.known or not sop_class:
                continue
            study, series = self.known[instance]
            hierarchy.setdefault(study, {}).setdefault(series, {})[instance] = sop_class
        return hierarchy

    def _by_key(self) -> dict[_Key, list[pydicom.DataElement | None]]:
        keys = sorted({key for each in self.elements for key in each}, key=_key_order)
        return {key: [each.get(key) for each in self.elements] for key in keys}

    def _unassigned(self) -> None:
        """Place every other attribute in the unassigned shared or per-frame
        attributes, as PS3.3 C.7.6.16.2.25 says."""
        shared = pydicom.Dataset()
        per_frame = [pydicom.Dataset() for _ in self.datasets]
        creators: list[dict[tuple[int, str], int]] = [
            {} for _ in range(len(self.datasets) + 1)
        ]
        for key, elements in self._by_key().items():
            if isinstance(key, int) and (
                key in _NEVER or key in _CONVERSION_SOURCE or key in self.assigned
            ):
                continue
            canonical = {_canonical(element) for element in elements}
            if isinstance(key, int) and key in self.top and len(canonical) == 1:
                if _canonical(self.top[key]) in canonical:
                    continue
            if len(canonical) == 1:
                if elements[0] is not None:
                    _place(shared, key, elements[0], creators[-1])
                continue
            for index, element in enumerate(elements):
                if element is not None:
                    _place(per_frame[index], key, element, creators[index])
        if len(shared):
            self.shared.UnassignedSharedConvertedAttributesSequence = [shared]
        for group, item in zip(self.per_frame, per_frame):
            if len(item):
                group.UnassignedPerFrameConvertedAttributesSequence = [item]

    def _required(self) -> None:
        """Give each Type 2 top-level attribute of the IOD's mandatory
        modules that no image gives as empty, and refuse an instance without
        a Type 1 one."""
        mandatory = {
            module.module for module in self.iod.modules if module.usage == "M"
        }
        for definition in self.iod.definitions:
            if definition.path or definition.module not in mandatory:
                continue
            if "x" in definition.tag:
                continue
            tag = _tag_number(definition.tag)
            if tag in (0x7FE00010, 0x52009229, 0x52009230):
                continue
            if definition.type == "2" and tag not in self.top:
                self.top.add_new(tag, pydicom.datadict.dictionary_VR(tag), None)
            elif definition.type == "1" and (
                tag not in self.top or self.top[tag].is_empty
            ):
                raise ConversionRefused(f"type-1-missing/{definition.tag}")

    def _pixel_data(self) -> None:
        first = self.datasets[0]
        allocated = int(_number(first, "BitsAllocated"))
        signed = _number(first, "PixelRepresentation") == 1
        dtype = np.dtype(f"<{'i' if signed else 'u'}{allocated // 8}")
        frames = []
        for image in self.images:
            values = np.asarray(image.stored)
            if values.min() < np.iinfo(dtype).min or values.max() > np.iinfo(dtype).max:
                raise ConversionRefused("stored-values")
            frames.append(values.astype(dtype))
        data = np.stack(frames).tobytes()
        if len(data) % 2:
            data += b"\0"
        self.top.PixelData = data
        self.top["PixelData"].VR = "OW" if allocated > 8 else "OB"


def _uid(*parts: str) -> str:
    """A UID derived from a name-based UUID of ``parts`` (PS3.5 B.2), so
    that the same images give the same UID."""
    name = "\n".join([_SALT, *parts])
    return f"2.25.{uuid.uuid5(uuid.NAMESPACE_URL, name).int}"
