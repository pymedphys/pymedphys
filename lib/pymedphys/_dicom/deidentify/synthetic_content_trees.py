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

"""The content trees of the synthetic corpus's Structured Reports.

Each function gives the root of a tree that follows the root template of a
Structured Report or Key Object Selection Document IOD of DICOM PS3.16
2026d:

- :func:`x_ray_dose_tree`, of an X-Ray Radiation Dose SR, TID 10001
  "Projection X-Ray Radiation Dose";
- :func:`radiopharmaceutical_dose_tree`, of a Radiopharmaceutical Radiation
  Dose SR, TID 10021 "Radiopharmaceutical Radiation Dose";
- :func:`imaging_report_tree`, of a Basic Text SR, Enhanced SR, or
  Comprehensive SR, TID 2000 "Basic Diagnostic Imaging Report";
- :func:`measurement_report_tree`, of a Comprehensive 3D SR or Extensible
  SR, TID 1500 "Measurement Report";
- :func:`key_object_selection_tree`, of a Key Object Selection Document,
  TID 2010 "Key Object Selection";
- :func:`mammography_cad_tree`, of a Mammography CAD SR, TID 4000
  "Mammography CAD Document Root";
- :func:`chest_cad_tree`, of a Chest CAD SR, TID 4100 "Chest CAD Report";
- :func:`colon_cad_tree`, of a Colon CAD SR, TID 4120 "Colon CAD Report";
- :func:`procedure_log_tree`, of a Procedure Log, TID 3001 "Procedure Log";
- :func:`spectacle_prescription_tree`, of a Spectacle Prescription Report,
  TID 2020 "Spectacle Prescription Report";
- :func:`macular_grid_tree`, of a Macular Grid Thickness and Volume Report,
  TID 2100 "Macular Grid Thickness and Volume Report"; and
- :func:`waveform_annotation_tree`, of a Waveform Annotation SR, TID 3750
  "Waveform Annotations".

Each holds only the rows that its templates require where they are
included, for the procedure that its docstring names, apart from the
templates that it names as left out: the report that Clean Structured
Content is first assessed on (D-047). Each content item's relationship,
Value Type, and concept name is a row of a template of DICOM PS3.16 2026d,
cited beside it, and each coded value is one of the context group that the
row names. Code meanings are those of PS3.16 Annex D for DCM codes, and
those the templates and context groups give for the others.

The value of each content item that can identify a person, a device, or a
time, a UIDREF, DATE, TIME, DATETIME, or PNAME item, comes from the caller,
so that the synthetic corpus
(:mod:`~pymedphys._dicom.deidentify.synthetic_corpus`) can plant a marker in
it; but the UIDs that name the collection's own study, series, or frame of
reference, such as the Study Instance UID that names an X-ray report's
scope of accumulation, which are the collection's own. The frame of
reference of a measurement report's volumetric region, and the image that
an IMAGE item references, are the caller's too, so that they can be the
collection's. Every other value is a code, a number, a coordinate, or the
fixed text of an algorithm's name or a patient orientation, the same in
every tree. The tests build reports with the optional rows besides, from the
same codes (``tests/dicom/_synthetic_dose_reports.py``,
``tests/dicom/_synthetic_structured_reports.py``, and
``tests/dicom/_synthetic_specialised_reports.py``).
"""

# One module holds the trees of every report of the corpus, which share
# their codes and content item builders.
# pylint: disable = too-many-lines

from __future__ import annotations

import dataclasses
from collections.abc import Callable

from pymedphys._imports import pydicom

X_RAY_RADIATION_DOSE_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.67"
RADIOPHARMACEUTICAL_RADIATION_DOSE_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.68"
BASIC_TEXT_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.11"
ENHANCED_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.22"
COMPREHENSIVE_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.33"
COMPREHENSIVE_3D_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.34"
EXTENSIBLE_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.35"
KEY_OBJECT_SELECTION_DOCUMENT_STORAGE = "1.2.840.10008.5.1.4.1.1.88.59"
MAMMOGRAPHY_CAD_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.50"
CHEST_CAD_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.65"
COLON_CAD_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.69"
PROCEDURE_LOG_STORAGE = "1.2.840.10008.5.1.4.1.1.88.40"
SPECTACLE_PRESCRIPTION_REPORT_STORAGE = "1.2.840.10008.5.1.4.1.1.78.6"
MACULAR_GRID_THICKNESS_AND_VOLUME_REPORT_STORAGE = "1.2.840.10008.5.1.4.1.1.79.1"
WAVEFORM_ANNOTATION_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.77"
# The root template of each, as Content Template Sequence (0040,A504) names it.
ROOT_TEMPLATES = {
    X_RAY_RADIATION_DOSE_SR_STORAGE: "10001",
    RADIOPHARMACEUTICAL_RADIATION_DOSE_SR_STORAGE: "10021",
    BASIC_TEXT_SR_STORAGE: "2000",
    ENHANCED_SR_STORAGE: "2000",
    COMPREHENSIVE_SR_STORAGE: "2000",
    COMPREHENSIVE_3D_SR_STORAGE: "1500",
    EXTENSIBLE_SR_STORAGE: "1500",
    KEY_OBJECT_SELECTION_DOCUMENT_STORAGE: "2010",
    MAMMOGRAPHY_CAD_SR_STORAGE: "4000",
    CHEST_CAD_SR_STORAGE: "4100",
    COLON_CAD_SR_STORAGE: "4120",
    PROCEDURE_LOG_STORAGE: "3001",
    SPECTACLE_PRESCRIPTION_REPORT_STORAGE: "2020",
    MACULAR_GRID_THICKNESS_AND_VOLUME_REPORT_STORAGE: "2100",
    WAVEFORM_ANNOTATION_SR_STORAGE: "3750",
}


@dataclasses.dataclass(frozen=True)
class Code:
    """A code: its Code Value, Coding Scheme Designator, and Code Meaning."""

    value: str
    designator: str
    meaning: str

    def dataset(self) -> pydicom.Dataset:
        """Return the code as an item of a code sequence."""
        code = pydicom.Dataset()
        code.CodeValue = self.value
        code.CodingSchemeDesignator = self.designator
        code.CodeMeaning = self.meaning
        return code


# Concept names, by the first template row that uses them.
X_RAY_RADIATION_DOSE_REPORT = Code("113701", "DCM", "X-Ray Radiation Dose Report")
PROCEDURE_REPORTED = Code("121058", "DCM", "Procedure reported")
HAS_INTENT = Code("363703001", "SCT", "Has Intent")
SCOPE_OF_ACCUMULATION = Code("113705", "DCM", "Scope of Accumulation")
ACCUMULATED_X_RAY_DOSE_DATA = Code("113702", "DCM", "Accumulated X-Ray Dose Data")
SOURCE_OF_DOSE_INFORMATION = Code("113854", "DCM", "Source of Dose Information")
# TID 1002 and 1004.
OBSERVER_TYPE = Code("121005", "DCM", "Observer Type")
DEVICE_OBSERVER_UID_CONCEPT = Code("121012", "DCM", "Device Observer UID")
# TID 1020.
PERSON_NAME = Code("113870", "DCM", "Person Name")
PERSON_ROLE_IN_PROCEDURE = Code("113875", "DCM", "Person Role in Procedure")
# TID 10002 and 10003.
ACQUISITION_PLANE = Code("113764", "DCM", "Acquisition Plane")
IRRADIATION_EVENT_X_RAY_DATA = Code("113706", "DCM", "Irradiation Event X-Ray Data")
IRRADIATION_EVENT_UID_CONCEPT = Code("113769", "DCM", "Irradiation Event UID")
DATETIME_STARTED = Code("111526", "DCM", "DateTime Started")
IRRADIATION_EVENT_TYPE = Code("113721", "DCM", "Irradiation Event Type")
TARGET_REGION = Code("123014", "DCM", "Target Region")
DOSE_AREA_PRODUCT = Code("122130", "DCM", "Dose Area Product")
# TID 10021 and 10022.
RADIOPHARMACEUTICAL_RADIATION_DOSE_REPORT = Code(
    "113500", "DCM", "Radiopharmaceutical Radiation Dose Report"
)
ASSOCIATED_PROCEDURE = Code("363589002", "SCT", "Associated Procedure")
RADIOPHARMACEUTICAL_ADMINISTRATION = Code(
    "113502", "DCM", "Radiopharmaceutical Administration"
)
RADIOPHARMACEUTICAL_AGENT = Code("349358000", "SCT", "Radiopharmaceutical agent")
RADIONUCLIDE = Code("89457008", "SCT", "Radionuclide")
RADIONUCLIDE_HALF_LIFE = Code("304283002", "SCT", "Radionuclide Half Life")
ADMINISTRATION_EVENT_UID_CONCEPT = Code(
    "113503", "DCM", "Radiopharmaceutical Administration Event UID"
)
START_DATETIME = Code("123003", "DCM", "Radiopharmaceutical Start DateTime")
ADMINISTERED_ACTIVITY = Code("113507", "DCM", "Administered activity")
ROUTE_OF_ADMINISTRATION = Code("410675002", "SCT", "Route of administration")
SITE_OF = Code("272737002", "SCT", "Site of")
# TID 2000, 1204, and 1002; the title is from CID 7000.
BREAST_IMAGING_REPORT = Code("111400", "DCM", "Breast Imaging Report")
LANGUAGE = Code("121049", "DCM", "Language of Content Item and Descendants")
PERSON_OBSERVER_NAME = Code("121008", "DCM", "Person Observer Name")
# TID 1500, 1411, and 1419; the volume is from CID 218, by CID 7469 and 7472.
IMAGING_MEASUREMENT_REPORT = Code("126000", "DCM", "Imaging Measurement Report")
IMAGING_MEASUREMENTS = Code("126010", "DCM", "Imaging Measurements")
MEASUREMENT_GROUP = Code("125007", "DCM", "Measurement Group")
VOLUME_SURFACE = Code("121231", "DCM", "Volume Surface")
SOURCE_SERIES_FOR_SEGMENTATION = Code("121232", "DCM", "Source series for segmentation")
VOLUME = Code("118565006", "SCT", "Volume")
# TID 2010; the title is from CID 7010.
OF_INTEREST = Code("113000", "DCM", "Of Interest")
# TID 4000, 4001, 4015, 4017, 4019, and 4020.
MAMMOGRAPHY_CAD_REPORT = Code("111036", "DCM", "Mammography CAD Report")
IMAGE_LIBRARY = Code("111028", "DCM", "Image Library")
CAD_PROCESSING_AND_FINDINGS_SUMMARY = Code(
    "111017", "DCM", "CAD Processing and Findings Summary"
)
SUMMARY_OF_DETECTIONS = Code("111064", "DCM", "Summary of Detections")
SUMMARY_OF_ANALYSES = Code("111065", "DCM", "Summary of Analyses")
SUCCESSFUL_DETECTIONS = Code("111063", "DCM", "Successful Detections")
DETECTION_PERFORMED = Code("111022", "DCM", "Detection Performed")
ALGORITHM_NAME = Code("111001", "DCM", "Algorithm Name")
ALGORITHM_VERSION = Code("111003", "DCM", "Algorithm Version")
IMAGE_LATERALITY = Code("111027", "DCM", "Image Laterality")
IMAGE_VIEW = Code("111031", "DCM", "Image View")
PATIENT_ORIENTATION_ROW = Code("111044", "DCM", "Patient Orientation Row")
PATIENT_ORIENTATION_COLUMN = Code("111043", "DCM", "Patient Orientation Column")
STUDY_DATE = Code("111060", "DCM", "Study Date")
STUDY_TIME = Code("111061", "DCM", "Study Time")
HORIZONTAL_PIXEL_SPACING = Code("111026", "DCM", "Horizontal Pixel Spacing")
VERTICAL_PIXEL_SPACING = Code("111066", "DCM", "Vertical Pixel Spacing")
# TID 4100 and 4120 to 4122.
CHEST_CAD_REPORT = Code("112000", "DCM", "Chest CAD Report")
COLON_CAD_REPORT = Code("112220", "DCM", "Colon CAD Report")
IMAGE_SET_PROPERTIES = Code("112224", "DCM", "Image Set Properties")
FRAME_OF_REFERENCE_UID = Code("112227", "DCM", "Frame of Reference UID")
MODALITY = Code("121139", "DCM", "Modality")
SLICE_THICKNESS = Code("112225", "DCM", "Slice Thickness")
SPACING_BETWEEN_SLICES = Code("112226", "DCM", "Spacing between slices")
RECUMBENT_PATIENT_POSITION = Code(
    "112228", "DCM", "Recumbent Patient Position with respect to gravity"
)
SERIES_INSTANCE_UID = Code("112002", "DCM", "Series Instance UID")
# TID 3001; the title is from CID 3400.
CATH_LAB_PROCEDURE_LOG = Code("121120", "DCM", "Cath Lab Procedure Log")
# TID 2020 and 2021.
SPECTACLE_PRESCRIPTION_REPORT = Code("111671", "DCM", "Spectacle Prescription Report")
RIGHT_EYE_RX = Code("111688", "DCM", "Right Eye Rx")
SPHERE = Code("251795007", "SCT", "Sphere")
# TID 2100, 2101, and 2102. Rows 1 and 4 to 14 of TID 2101 are coded in
# LOINC.
MACULAR_GRID_REPORT = Code("111690", "DCM", "Macular Grid Thickness and Volume Report")
FINDINGS = Code("59776-5", "LN", "Findings")
FINDING_SITE = Code("363698007", "SCT", "Finding Site")
LATERALITY = Code("272741003", "SCT", "Laterality")
MACULAR_GRID_THICKNESSES = (
    Code("57108-3", "LN", "Macular Grid.Center Point Thickness"),
    Code("57109-1", "LN", "Macular Grid.Center Subfield Thickness"),
    Code("57110-9", "LN", "Macular Grid.Inner Superior Subfield Thickness"),
    Code("57111-7", "LN", "Macular Grid.Inner Nasal Subfield Thickness"),
    Code("57112-5", "LN", "Macular Grid.Inner Inferior Subfield Thickness"),
    Code("57113-3", "LN", "Macular Grid.Inner Temporal Subfield Thickness"),
    Code("57114-1", "LN", "Macular Grid.Outer Superior Subfield Thickness"),
    Code("57115-8", "LN", "Macular Grid.Outer Nasal Subfield Thickness"),
    Code("57116-6", "LN", "Macular Grid.Outer Inferior Subfield Thickness"),
    Code("57117-4", "LN", "Macular Grid.Outer Temporal Subfield Thickness"),
)
MACULAR_GRID_TOTAL_VOLUME = Code("57118-2", "LN", "Macular Grid.Total Volume")
IMAGES_USED = Code("111691", "DCM", "Number of Images Used for Macular Measurements")
SAMPLES_USED = Code("111692", "DCM", "Number of Samples Used per Image")
ANALYSIS_QUALITY_RATING = Code("111693", "DCM", "Analysis Quality Rating")
IMAGE_SET_QUALITY_RATING = Code("111694", "DCM", "Image Set Quality Rating")
ALGORITHM_MANUFACTURER = Code("122405", "DCM", "Algorithm Manufacturer")
# TID 3750; the title is from CID 3048.
NEUROPHYSIOLOGY_RECORDING_ANNOTATIONS = Code(
    "130867", "DCM", "Neurophysiology Recording Annotations"
)
WAVEFORM_ANNOTATIONS = Code("130870", "DCM", "Waveform Annotations")
WAVEFORM_ANNOTATION_GROUP = Code("130872", "DCM", "Waveform Annotation Group")
WAVEFORM_ANNOTATION_GROUP_NUMBER = Code(
    "130873", "DCM", "Waveform Annotation Group Number"
)

# Coded values, each from the context group that its row names.
PROJECTION_X_RAY = Code("113704", "DCM", "Projection X-Ray")  # TID 10001 row 2
DIAGNOSTIC_INTENT = Code("261004008", "SCT", "Diagnostic Intent")  # CID 3629
DEVICE = Code("121007", "DCM", "Device")  # CID 270
STUDY_SCOPE = Code("113014", "DCM", "Study")  # CID 10000
STUDY_INSTANCE_UID = Code("110180", "DCM", "Study Instance UID")  # CID 10001
AUTOMATED_DATA_COLLECTION = Code("113856", "DCM", "Automated Data Collection")
SINGLE_PLANE = Code("113622", "DCM", "Single Plane")  # TID 10001 row 11
STATIONARY_ACQUISITION = Code("113611", "DCM", "Stationary Acquisition")  # CID 10002
CHEST = Code("816094009", "SCT", "Chest")  # CID 4031
IRRADIATION_ADMINISTERING = Code("113851", "DCM", "Irradiation Administering")
TUMOR_LOCALIZATION = Code(
    "45316007", "SCT", "Radionuclide localization of tumor"
)  # CID 3108
FDG = Code("35321007", "SCT", "Fluorodeoxyglucose F^18^")  # CID 25
FLUORINE_18 = Code("77004003", "SCT", "^18^Fluorine")  # CID 4020
INTRAVENOUS_ROUTE = Code("47625008", "SCT", "Intravenous route")  # CID 11
VIA_ARM_VEIN = Code("261459001", "SCT", "Via arm vein")  # CID 3746
ENGLISH = Code("en", "RFC5646", "English")  # CID 5000
ALL_SUCCEEDED_WITHOUT_FINDINGS = Code(
    "111241", "DCM", "All algorithms succeeded; without findings"
)  # CID 6047
SUCCEEDED = Code("111222", "DCM", "Succeeded")  # CID 6042
NOT_ATTEMPTED = Code("111225", "DCM", "Not Attempted")  # CID 6042
CALCIFICATION_CLUSTER = Code(
    "129769006", "SCT", "Calcification Cluster"
)  # CID 6014, by CID 6015
LEFT_BREAST = Code("80248007", "SCT", "Left breast")  # CID 6022, by CID 6023
CRANIO_CAUDAL = Code("399162004", "SCT", "cranio-caudal")  # CID 4014
ABNORMAL_OPACITY = Code("112033", "DCM", "Abnormal opacity")  # CID 6101
POLYP_OF_COLON = Code("68496003", "SCT", "Polyp of colon")  # CID 6201
COMPUTED_TOMOGRAPHY = Code("CT", "DCM", "Computed Tomography")  # CID 29
SUPINE = Code("40199007", "SCT", "Supine")  # CID 6206
EYE = Code("81745001", "SCT", "Eye")  # TID 2101 row 2
# TID 2100 row 4, from CID 244. Left, not Right: the subject's residual
# search looks for each removed code meaning in every file of the subject,
# and "Right" is in the "copyright" of the corpus's ICC profile.
LEFT = Code("7771000", "SCT", "Left")
# Units, as the rows give them.
GRAY_SQUARE_METRE = Code("Gy.m2", "UCUM", "Gy.m2")
SECONDS = Code("s", "UCUM", "seconds")
MEGABECQUEREL = Code("MBq", "UCUM", "MBq")
CUBIC_MILLIMETRE = Code("mm3", "UCUM", "cubic millimeter")  # CID 7181, by 7462
MILLIMETRE = Code("mm", "UCUM", "millimeter")
MILLIMETRES_PER_PIXEL = Code("mm/{pixel}", "UCUM", "millimeters per pixel")
DIOPTRES = Code("[diop]", "UCUM", "diopters")
MICROMETRE = Code("um", "UCUM", "micrometer")
MACULAR_VOLUME_UNITS = Code("mm3", "UCUM", "mm3")
IMAGES = Code("{images}", "UCUM", "images")
SAMPLES = Code("{samples}", "UCUM", "samples")
RANGE_0_100 = Code("{0:100}", "UCUM", "range:0:100")
NO_UNITS = Code("1", "UCUM", "no units")

# The attribute of the value of each Value Type that ``item`` takes as text
# (PS3.3 Table 10-2).
_TEXT_VALUES = {
    "TEXT": "TextValue",
    "PNAME": "PersonName",
    "DATE": "Date",
    "TIME": "Time",
    "DATETIME": "DateTime",
    "UIDREF": "UID",
}


def item(
    relationship: str | None,
    value_type: str,
    concept: Code | None,
    *children: pydicom.Dataset,
    **value: object,
) -> pydicom.Dataset:
    """Return a content item whose Content Sequence holds ``children``.

    Parameters
    ----------
    relationship : str or None
        Its Relationship Type (0040,A010), or None for the root.
    value_type : str
        Its Value Type (0040,A040).
    concept : Code or None
        Its concept name, or None for an item that PS3.3 Table C.17-5 lets
        have none, such as an image reference.
    *children : pydicom.Dataset
        The items of its Content Sequence, if any.
    **value
        Its value, by Value Type: ``code`` (a :class:`Code`) for CODE,
        ``number`` and ``units`` for NUM, ``text`` for TEXT, PNAME, DATE,
        TIME, DATETIME, and UIDREF, ``sop_class`` and ``sop_instance`` for
        IMAGE, and ``graphic_type``, ``points``, and ``frame_of_reference``
        for SCOORD3D.
    """
    dataset = pydicom.Dataset()
    if relationship is not None:
        dataset.RelationshipType = relationship
    dataset.ValueType = value_type
    if concept is not None:
        dataset.ConceptNameCodeSequence = pydicom.Sequence([concept.dataset()])
    if value_type == "CONTAINER":
        dataset.ContinuityOfContent = "SEPARATE"
    elif value_type == "CODE":
        code = value["code"]
        assert isinstance(code, Code)
        dataset.ConceptCodeSequence = pydicom.Sequence([code.dataset()])
    elif value_type == "NUM":
        units = value["units"]
        assert isinstance(units, Code)
        measured = pydicom.Dataset()
        measured.NumericValue = value["number"]
        measured.MeasurementUnitsCodeSequence = pydicom.Sequence([units.dataset()])
        dataset.MeasuredValueSequence = pydicom.Sequence([measured])
    elif value_type == "IMAGE":
        referenced = pydicom.Dataset()
        referenced.ReferencedSOPClassUID = value["sop_class"]
        referenced.ReferencedSOPInstanceUID = value["sop_instance"]
        dataset.ReferencedSOPSequence = pydicom.Sequence([referenced])
    elif value_type == "SCOORD3D":
        dataset.GraphicType = value["graphic_type"]
        dataset.GraphicData = list(value["points"])  # type: ignore[call-overload]
        dataset.ReferencedFrameOfReferenceUID = value["frame_of_reference"]
    else:
        setattr(dataset, _TEXT_VALUES[value_type], value["text"])
    if children:
        dataset.ContentSequence = pydicom.Sequence(list(children))
    return dataset


def by_reference(relationship: str, position: tuple[int, ...]) -> pydicom.Dataset:
    """Return an item of a by-reference relationship to the item at ``position``.

    ``relationship`` is its Relationship Type, which a template gives with
    the prefix "R-" that marks a relationship by reference. ``position`` is
    the target's place along the tree, from the root, as Referenced Content
    Item Identifier (0040,DB73) gives it (PS3.3 Section C.17.3.2.5).
    """
    dataset = pydicom.Dataset()
    dataset.RelationshipType = relationship
    dataset.ReferencedContentItemIdentifier = list(position)
    return dataset


# A function that returns a new value for a content item of a Value Type,
# UIDREF, DATE, TIME, DATETIME, or PNAME.
Values = Callable[[str], str]


@dataclasses.dataclass(frozen=True)
class Image:
    """An image that a content tree references: its SOP Class and Instance UIDs."""

    sop_class: str
    sop_instance: str


def _image(relationship: str, image: Image, *children: pydicom.Dataset):
    """Return an IMAGE item, with no concept name, that references ``image``."""
    return item(
        relationship,
        "IMAGE",
        None,
        *children,
        sop_class=image.sop_class,
        sop_instance=image.sop_instance,
    )


def x_ray_dose_tree(values: Values, study: str) -> pydicom.Dataset:
    """Return the root of an X-Ray Radiation Dose SR's tree, TID 10001.

    The report is of a single-plane projection radiograph whose dose was
    collected automatically (TID 10001 rows 2, 11, and 18), observed by the
    device that recorded it, so that TID 10001 rows 2, 3, 5 to 7, 11, 14,
    and 18 are required, as are TID 10002 rows 1 and 2 and TID 10003 rows 1
    to 3, 6, 7, 17, and 18. It leaves out TID 10002 row 10, TID 10004
    "Accumulated Fluoroscopy and Acquisition Projection X-Ray Dose", whose
    rows carry codes and numbers, and TID 10003 rows 27 to 29, TIDs 10003A
    to 10003C, the detector, source, and mechanical data. Its target region
    is the chest: where the report is not written, the residual search looks
    for each value that its removed tree held, Code Meanings included, in
    the other instances of its subject, and a kept technique description
    such as ``AXIAL CHEST`` that holds the meaning is released, since a
    registered scheme's meaning that only unwritten instances held is
    exempt.

    Parameters
    ----------
    values : callable
        Returns the value of the Device Observer UID, the Irradiation Event
        UID, and the DateTime Started, given each one's Value Type, in that
        order.
    study : str
        The Study Instance UID that the scope of accumulation names.
    """
    observer_uid = values("UIDREF")
    event_uid = values("UIDREF")
    started = values("DATETIME")
    return item(
        None,
        "CONTAINER",
        X_RAY_RADIATION_DOSE_REPORT,
        # TID 10001 row 2, M, and row 3.
        item(
            "HAS CONCEPT MOD",
            "CODE",
            PROCEDURE_REPORTED,
            item("HAS CONCEPT MOD", "CODE", HAS_INTENT, code=DIAGNOSTIC_INTENT),
            code=PROJECTION_X_RAY,
        ),
        # TID 10001 row 5, TID 1002 row 1 and TID 1004 row 1, M.
        item("HAS OBS CONTEXT", "CODE", OBSERVER_TYPE, code=DEVICE),
        item(
            "HAS OBS CONTEXT", "UIDREF", DEVICE_OBSERVER_UID_CONCEPT, text=observer_uid
        ),
        # TID 10001 rows 6 and 7, M.
        item(
            "HAS OBS CONTEXT",
            "CODE",
            SCOPE_OF_ACCUMULATION,
            item("HAS PROPERTIES", "UIDREF", STUDY_INSTANCE_UID, text=study),
            code=STUDY_SCOPE,
        ),
        # TID 10001 row 11, TID 10002 rows 1 and 2.
        item(
            "CONTAINS",
            "CONTAINER",
            ACCUMULATED_X_RAY_DOSE_DATA,
            item("HAS CONCEPT MOD", "CODE", ACQUISITION_PLANE, code=SINGLE_PLANE),
        ),
        # TID 10001 row 14, TID 10003 rows 1 to 3, 6, 7, 17, and 18.
        item(
            "CONTAINS",
            "CONTAINER",
            IRRADIATION_EVENT_X_RAY_DATA,
            item("HAS CONCEPT MOD", "CODE", ACQUISITION_PLANE, code=SINGLE_PLANE),
            item("CONTAINS", "UIDREF", IRRADIATION_EVENT_UID_CONCEPT, text=event_uid),
            item("CONTAINS", "DATETIME", DATETIME_STARTED, text=started),
            item(
                "CONTAINS", "CODE", IRRADIATION_EVENT_TYPE, code=STATIONARY_ACQUISITION
            ),
            item("CONTAINS", "CODE", TARGET_REGION, code=CHEST),
            item(
                "CONTAINS",
                "NUM",
                DOSE_AREA_PRODUCT,
                number="0.00012",
                units=GRAY_SQUARE_METRE,
            ),
        ),
        # TID 10001 row 18, M.
        item(
            "CONTAINS",
            "CODE",
            SOURCE_OF_DOSE_INFORMATION,
            code=AUTOMATED_DATA_COLLECTION,
        ),
    )


def radiopharmaceutical_dose_tree(values: Values) -> pydicom.Dataset:
    """Return the root of a Radiopharmaceutical Radiation Dose SR's tree, TID 10021.

    The report is of an intravenous administration of a PET
    radiopharmaceutical, so that TID 10021 rows 2 to 4 and TID 10022 rows 2
    to 4, 6, 9, 11, 20, 21, and 23 are required, with TID 1020 rows 1 and 2
    of the person who administered it. TID 10021 row 5, TID 10024, is
    optional and left out, and so is TID 10022 row 19, TID 10023 "Organ
    Dose".

    Parameters
    ----------
    values : callable
        Returns the value of the Radiopharmaceutical Administration Event
        UID, the Radiopharmaceutical Start DateTime, and the Person Name of
        the person who administered it, given each one's Value Type, in that
        order.
    """
    event_uid = values("UIDREF")
    started = values("DATETIME")
    person = values("PNAME")
    return item(
        None,
        "CONTAINER",
        RADIOPHARMACEUTICAL_RADIATION_DOSE_REPORT,
        # TID 10021 rows 2 and 3, M.
        item(
            "HAS CONCEPT MOD",
            "CODE",
            ASSOCIATED_PROCEDURE,
            item("HAS CONCEPT MOD", "CODE", HAS_INTENT, code=DIAGNOSTIC_INTENT),
            code=TUMOR_LOCALIZATION,
        ),
        # TID 10021 row 4, TID 10022.
        item(
            "CONTAINS",
            "CONTAINER",
            RADIOPHARMACEUTICAL_ADMINISTRATION,
            # TID 10022 rows 2 to 4, M.
            item(
                "CONTAINS",
                "CODE",
                RADIOPHARMACEUTICAL_AGENT,
                item("HAS PROPERTIES", "CODE", RADIONUCLIDE, code=FLUORINE_18),
                item(
                    "HAS PROPERTIES",
                    "NUM",
                    RADIONUCLIDE_HALF_LIFE,
                    number="6586.2",
                    units=SECONDS,
                ),
                code=FDG,
            ),
            # TID 10022 rows 6 and 9, M.
            item(
                "CONTAINS",
                "UIDREF",
                ADMINISTRATION_EVENT_UID_CONCEPT,
                text=event_uid,
            ),
            item("CONTAINS", "DATETIME", START_DATETIME, text=started),
            # TID 10022 row 11, M.
            item(
                "CONTAINS",
                "NUM",
                ADMINISTERED_ACTIVITY,
                number="370",
                units=MEGABECQUEREL,
            ),
            # TID 10022 rows 20 and 21, M and required for an intravenous
            # route.
            item(
                "CONTAINS",
                "CODE",
                ROUTE_OF_ADMINISTRATION,
                item("HAS PROPERTIES", "CODE", SITE_OF, code=VIA_ARM_VEIN),
                code=INTRAVENOUS_ROUTE,
            ),
            # TID 10022 row 23, M: TID 1020 rows 1 and 2.
            item(
                "CONTAINS",
                "PNAME",
                PERSON_NAME,
                item(
                    "HAS PROPERTIES",
                    "CODE",
                    PERSON_ROLE_IN_PROCEDURE,
                    code=IRRADIATION_ADMINISTERING,
                ),
                text=person,
            ),
        ),
    )


def imaging_report_tree(values: Values) -> pydicom.Dataset:
    """Return the root of a diagnostic imaging report's tree, TID 2000.

    TID 2000 rows 1, 5, and 7 are required: the title, a code of CID 7000
    that the engine can look up, the language (TID 1204 row 1), and the
    observation context (TID 1001), whose observer is a person, named by
    TID 1002 row 2 and TID 1003 row 1. The report has no sections (TID 2000
    row 8), so its tree holds no text, and every Value Type in it is one
    that a Basic Text SR allows.

    Parameters
    ----------
    values : callable
        Returns the value of the Person Observer Name, given its Value Type.
    """
    observer = values("PNAME")
    return item(
        None,
        "CONTAINER",
        BREAST_IMAGING_REPORT,
        # TID 2000 row 5, TID 1204 row 1.
        item("HAS CONCEPT MOD", "CODE", LANGUAGE, code=ENGLISH),
        # TID 2000 row 7, TID 1001 row 1, TID 1002 row 2, TID 1003 row 1.
        item("HAS OBS CONTEXT", "PNAME", PERSON_OBSERVER_NAME, text=observer),
    )


def measurement_report_tree(values: Values, frame_of_reference: str) -> pydicom.Dataset:
    """Return the root of a measurement report's tree, TID 1500.

    TID 1500 rows 1, 3, and 6 are required: the title, from CID 7021, the
    observation context (TID 1001), whose observer is a person, named, and
    the Imaging Measurements, since neither row 10 nor row 12 is present.
    Row 2, the language (TID 1204 row 1), which is optional, comes first,
    as in the imaging report, so that the first item of each tree is a
    code.
    They hold one volumetric region (row 8, TID 1411), a point given by a
    Volume Surface (row 10), in three dimensions, so that its source series
    (row 12) is required too, and TID 1419 (row 15) gives its volume (row
    5, M).

    Parameters
    ----------
    values : callable
        Returns the value of the Person Observer Name and of the source
        series's Series Instance UID, given each one's Value Type, in that
        order.
    frame_of_reference : str
        The Frame of Reference UID that the Volume Surface's coordinates are
        in.
    """
    observer = values("PNAME")
    series = values("UIDREF")
    return item(
        None,
        "CONTAINER",
        IMAGING_MEASUREMENT_REPORT,
        # TID 1500 row 2, TID 1204 row 1.
        item("HAS CONCEPT MOD", "CODE", LANGUAGE, code=ENGLISH),
        # TID 1500 row 3, TID 1001 row 1, TID 1002 row 2, TID 1003 row 1.
        item("HAS OBS CONTEXT", "PNAME", PERSON_OBSERVER_NAME, text=observer),
        # TID 1500 rows 6 and 8.
        item(
            "CONTAINS",
            "CONTAINER",
            IMAGING_MEASUREMENTS,
            item(
                "CONTAINS",
                "CONTAINER",
                MEASUREMENT_GROUP,
                # TID 1411 rows 10 and 12.
                item(
                    "CONTAINS",
                    "SCOORD3D",
                    VOLUME_SURFACE,
                    graphic_type="POINT",
                    points=(12.5, -40.0, 63.25),
                    frame_of_reference=frame_of_reference,
                ),
                item(
                    "CONTAINS",
                    "UIDREF",
                    SOURCE_SERIES_FOR_SEGMENTATION,
                    text=series,
                ),
                # TID 1411 row 15, TID 1419 row 5.
                item(
                    "CONTAINS",
                    "NUM",
                    VOLUME,
                    number="1840",
                    units=CUBIC_MILLIMETRE,
                ),
            ),
        ),
    )


def key_object_selection_tree(image: Image) -> pydicom.Dataset:
    """Return the root of a Key Object Selection Document's tree, TID 2010.

    TID 2010 row 1, the title, from CID 7010, is required, and so is one of
    rows 8 to 10, here row 8, an image of interest. The tree holds no value
    that identifies anyone: the image's reference, whose UIDs take their
    own rules, is its only value.

    Parameters
    ----------
    image : Image
        The image that the document selects.
    """
    return item(
        None,
        "CONTAINER",
        OF_INTEREST,
        # TID 2010 row 8.
        _image("CONTAINS", image),
    )


def _algorithm(relationship: str) -> list[pydicom.Dataset]:
    """Return TID 4019 rows 1 and 2, the algorithm's name and version, both M."""
    return [
        item(relationship, "TEXT", ALGORITHM_NAME, text="FIXTURE DETECTOR"),
        item(relationship, "TEXT", ALGORITHM_VERSION, text="1.0"),
    ]


def _summaries(detection: pydicom.Dataset) -> list[pydicom.Dataset]:
    """Return a CAD report's summaries: no findings, one detection, no analysis.

    The CAD Processing and Findings Summary is from CID 6047; the detections
    succeeded, so the Summary of Detections infers from a container of
    Successful Detections (TID 4015) that holds ``detection``, a Detection
    Performed (TID 4017); no analysis was attempted, so no Summary of
    Analyses infers from anything.
    """
    detections = item("INFERRED FROM", "CONTAINER", SUCCESSFUL_DETECTIONS, detection)
    return [
        item(
            "CONTAINS",
            "CODE",
            CAD_PROCESSING_AND_FINDINGS_SUMMARY,
            code=ALL_SUCCEEDED_WITHOUT_FINDINGS,
        ),
        item("CONTAINS", "CODE", SUMMARY_OF_DETECTIONS, detections, code=SUCCEEDED),
        item("CONTAINS", "CODE", SUMMARY_OF_ANALYSES, code=NOT_ATTEMPTED),
    ]


# The place of the mammography CAD report's image library entry along its
# tree: the first item of the root's second.
MAMMOGRAPHY_CAD_ENTRY = (1, 2, 1)


def mammography_cad_tree(values: Values, image: Image) -> pydicom.Dataset:
    """Return the root of a Mammography CAD SR's tree, TID 4000.

    The CAD found nothing in one image: TID 4000 rows 1 to 6 and 8 are
    required, with the language (TID 1204 row 1), the image library's entry
    (TID 4020), the summary (TID 4001 row 1), and the detections, which
    succeeded, so that row 7 includes TID 4015, whose one detection
    performed (TID 4017) names its algorithm (TID 4019) and refers by
    reference to the entry (row 4, R-HAS PROPERTIES). The entry describes a
    left cranio-caudal mammogram, which has an Image Laterality, a View Code
    Sequence, a Patient Orientation, a Study Date and Time, and an Imager
    Pixel Spacing, so that TID 4020 rows 2, 3, 5 to 8, 11, and 12 are
    required.

    Parameters
    ----------
    values : callable
        Returns the value of the entry's Study Date and Study Time, given
        each one's Value Type, in that order.
    image : Image
        The image that the entry references.
    """
    study_date = values("DATE")
    study_time = values("TIME")
    spacing = {"number": "0.1", "units": MILLIMETRE}
    entry = _image(
        "CONTAINS",
        image,
        item("HAS ACQ CONTEXT", "CODE", IMAGE_LATERALITY, code=LEFT_BREAST),
        item("HAS ACQ CONTEXT", "CODE", IMAGE_VIEW, code=CRANIO_CAUDAL),
        item("HAS ACQ CONTEXT", "TEXT", PATIENT_ORIENTATION_ROW, text="A"),
        item("HAS ACQ CONTEXT", "TEXT", PATIENT_ORIENTATION_COLUMN, text="R"),
        item("HAS ACQ CONTEXT", "DATE", STUDY_DATE, text=study_date),
        item("HAS ACQ CONTEXT", "TIME", STUDY_TIME, text=study_time),
        item("HAS ACQ CONTEXT", "NUM", HORIZONTAL_PIXEL_SPACING, **spacing),
        item("HAS ACQ CONTEXT", "NUM", VERTICAL_PIXEL_SPACING, **spacing),
    )
    detection = item(
        "CONTAINS",
        "CODE",
        DETECTION_PERFORMED,
        *_algorithm("HAS PROPERTIES"),
        by_reference("HAS PROPERTIES", MAMMOGRAPHY_CAD_ENTRY),
        code=CALCIFICATION_CLUSTER,
    )
    return item(
        None,
        "CONTAINER",
        MAMMOGRAPHY_CAD_REPORT,
        # TID 4000 row 2, TID 1204 row 1.
        item("HAS CONCEPT MOD", "CODE", LANGUAGE, code=ENGLISH),
        # TID 4000 rows 3 and 4.
        item("CONTAINS", "CONTAINER", IMAGE_LIBRARY, entry),
        # TID 4000 rows 5 to 8.
        *_summaries(detection),
    )


def chest_cad_tree(image: Image) -> pydicom.Dataset:
    """Return the root of a Chest CAD SR's tree, TID 4100.

    TID 4100 rows 1, 2 (TID 1204), 5 (TID 4101, whose row 1 is required), 6,
    and 8 are required. The CAD found nothing: the detections succeeded, so
    row 7 includes TID 4015, whose one detection performed (TID 4017) names
    its algorithm (TID 4019) and the radiograph (row 3); no analysis was
    attempted, so row 9 is absent. The image library (row 3) is optional and
    left out, so the tree holds no value that identifies anyone.

    Parameters
    ----------
    image : Image
        The radiograph that the detection names.
    """
    detection = item(
        "CONTAINS",
        "CODE",
        DETECTION_PERFORMED,
        *_algorithm("HAS PROPERTIES"),
        _image("HAS PROPERTIES", image),
        code=ABNORMAL_OPACITY,
    )
    return item(
        None,
        "CONTAINER",
        CHEST_CAD_REPORT,
        item("HAS CONCEPT MOD", "CODE", LANGUAGE, code=ENGLISH),
        *_summaries(detection),
    )


def colon_cad_tree(
    values: Values, study: str, frame_of_reference: str, series: str
) -> pydicom.Dataset:
    """Return the root of a Colon CAD SR's tree, TID 4120.

    TID 4120 rows 1 to 5 and 7 are required: the language (TID 1204), one
    Image Set Properties of TID 4122, whose rows 1 to 10 are required, and
    row 11 since the CT gives a Patient Position, the summary (TID 4121 row
    1), and the detections, which succeeded, so that row 6 includes TID
    4015, whose one detection performed (TID 4017) names its algorithm (TID
    4019) and the CT series (row 5). No analysis was attempted, so row 8 is
    absent.

    Parameters
    ----------
    values : callable
        Returns the value of the image set's Study Date and Study Time,
        given each one's Value Type, in that order.
    study, frame_of_reference, series : str
        The image set's Study Instance UID and Frame of Reference UID, and
        the Series Instance UID of the CT series that the detection names.
    """
    study_date = values("DATE")
    study_time = values("TIME")
    per_pixel = {"number": "0.68", "units": MILLIMETRES_PER_PIXEL}
    properties = item(
        "CONTAINS",
        "CONTAINER",
        IMAGE_SET_PROPERTIES,
        item("CONTAINS", "UIDREF", FRAME_OF_REFERENCE_UID, text=frame_of_reference),
        item("CONTAINS", "UIDREF", STUDY_INSTANCE_UID, text=study),
        item("CONTAINS", "DATE", STUDY_DATE, text=study_date),
        item("CONTAINS", "TIME", STUDY_TIME, text=study_time),
        item("CONTAINS", "CODE", MODALITY, code=COMPUTED_TOMOGRAPHY),
        item("CONTAINS", "NUM", HORIZONTAL_PIXEL_SPACING, **per_pixel),
        item("CONTAINS", "NUM", VERTICAL_PIXEL_SPACING, **per_pixel),
        item("CONTAINS", "NUM", SLICE_THICKNESS, number="2", units=MILLIMETRE),
        item("CONTAINS", "NUM", SPACING_BETWEEN_SLICES, number="2", units=MILLIMETRE),
        item("CONTAINS", "CODE", RECUMBENT_PATIENT_POSITION, code=SUPINE),
    )
    detection = item(
        "CONTAINS",
        "CODE",
        DETECTION_PERFORMED,
        *_algorithm("HAS PROPERTIES"),
        item("HAS PROPERTIES", "UIDREF", SERIES_INSTANCE_UID, text=series),
        code=POLYP_OF_COLON,
    )
    return item(
        None,
        "CONTAINER",
        COLON_CAD_REPORT,
        item("HAS CONCEPT MOD", "CODE", LANGUAGE, code=ENGLISH),
        properties,
        *_summaries(detection),
    )


def procedure_log_tree(values: Values) -> pydicom.Dataset:
    """Return the root of a Procedure Log's tree, TID 3001.

    TID 3001 rows 1 to 3 are required: the title, from CID 3400, an
    observer, a person, by TID 1002, whose TID 1003 row 1 names them, and
    TID 3601, all of whose rows are optional. The log's entries, room, and
    equipment are optional and left out.

    Parameters
    ----------
    values : callable
        Returns the value of the Person Observer Name, given its Value Type.
    """
    observer = values("PNAME")
    return item(
        None,
        "CONTAINER",
        CATH_LAB_PROCEDURE_LOG,
        item("HAS OBS CONTEXT", "PNAME", PERSON_OBSERVER_NAME, text=observer),
    )


def spectacle_prescription_tree() -> pydicom.Dataset:
    """Return the root of a Spectacle Prescription Report's tree, TID 2020.

    Only TID 2020 row 1 is required; the right eye's lens is prescribed, so
    row 2, with TID 2021 row 1, the sphere, is present. TID 2020 includes no
    observation context, so the tree holds only codes and a number.
    """
    return item(
        None,
        "CONTAINER",
        SPECTACLE_PRESCRIPTION_REPORT,
        item(
            "CONTAINS",
            "CONTAINER",
            RIGHT_EYE_RX,
            item("CONTAINS", "NUM", SPHERE, number="-1.25", units=DIOPTRES),
        ),
    )


def _quality(concept: Code, number: str) -> pydicom.Dataset:
    """Return TID 2101 row 17 or 19, a quality rating, with TID 2102 rows 1 to 3."""
    return item(
        "CONTAINS",
        "NUM",
        concept,
        item("HAS OBS CONTEXT", "TEXT", ALGORITHM_NAME, text="FIXTURE GRID"),
        item("HAS OBS CONTEXT", "TEXT", ALGORITHM_VERSION, text="3.0"),
        item("HAS OBS CONTEXT", "TEXT", ALGORITHM_MANUFACTURER, text="FIXTURE MAKER"),
        number=number,
        units=RANGE_0_100,
    )


def macular_grid_tree(values: Values) -> pydicom.Dataset:
    """Return the root of a Macular Grid Thickness and Volume Report's tree, TID 2100.

    Every row of the tree is required: TID 2100 rows 1 to 4, with the
    language (TID 1204), the observation context (TID 1001), whose
    observer, a person, is named, and TID 2101 for the right eye, whose rows
    1 to 17 and 19 are required, rows 17 and 19 each with TID 2102 rows 1 to
    3. TID 2101 codes the findings' container (row 1) and its thicknesses
    and volume (rows 4 to 14) in LOINC.

    Parameters
    ----------
    values : callable
        Returns the value of the Person Observer Name, given its Value Type.
    """
    observer = values("PNAME")
    side = item("HAS CONCEPT MOD", "CODE", LATERALITY, code=LEFT)
    thicknesses = [
        item("CONTAINS", "NUM", concept, number=str(250 + 10 * index), units=MICROMETRE)
        for index, concept in enumerate(MACULAR_GRID_THICKNESSES)
    ]
    findings = item(
        "CONTAINS",
        "CONTAINER",
        FINDINGS,
        item("HAS CONCEPT MOD", "CODE", FINDING_SITE, side, code=EYE),
        *thicknesses,
        item(
            "CONTAINS",
            "NUM",
            MACULAR_GRID_TOTAL_VOLUME,
            number="8.4",
            units=MACULAR_VOLUME_UNITS,
        ),
        item("CONTAINS", "NUM", IMAGES_USED, number="25", units=IMAGES),
        item("CONTAINS", "NUM", SAMPLES_USED, number="512", units=SAMPLES),
        _quality(ANALYSIS_QUALITY_RATING, "92"),
        _quality(IMAGE_SET_QUALITY_RATING, "88"),
    )
    return item(
        None,
        "CONTAINER",
        MACULAR_GRID_REPORT,
        item("HAS CONCEPT MOD", "CODE", LANGUAGE, code=ENGLISH),
        item("HAS OBS CONTEXT", "PNAME", PERSON_OBSERVER_NAME, text=observer),
        findings,
    )


def waveform_annotation_tree(values: Values) -> pydicom.Dataset:
    """Return the root of a Waveform Annotation SR's tree, TID 3750.

    TID 3750 rows 1, 3, 7, 9, and 10 are required: the title, from CID 3048,
    the observation context (TID 1001), whose observer, a person, is named,
    and the annotations' container, holding one group with its number. The
    group's annotations, which reference the waveform, are optional and
    left out.

    Parameters
    ----------
    values : callable
        Returns the value of the Person Observer Name, given its Value Type.
    """
    observer = values("PNAME")
    group = item(
        "CONTAINS",
        "CONTAINER",
        WAVEFORM_ANNOTATION_GROUP,
        item(
            "HAS OBS CONTEXT",
            "NUM",
            WAVEFORM_ANNOTATION_GROUP_NUMBER,
            number="1",
            units=NO_UNITS,
        ),
    )
    return item(
        None,
        "CONTAINER",
        NEUROPHYSIOLOGY_RECORDING_ANNOTATIONS,
        item("HAS OBS CONTEXT", "PNAME", PERSON_OBSERVER_NAME, text=observer),
        item("CONTAINS", "CONTAINER", WAVEFORM_ANNOTATIONS, group),
    )
