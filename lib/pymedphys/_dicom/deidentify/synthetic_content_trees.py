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

:func:`x_ray_dose_tree` gives the root of an X-Ray Radiation Dose SR's tree,
which follows TID 10001 "Projection X-Ray Radiation Dose", and
:func:`ct_dose_tree` that of one which follows TID 10011 "CT Radiation
Dose", which PS3.3 Section A.35.8 allows at the root too;
:func:`enhanced_x_ray_dose_tree` that of an Enhanced X-Ray Radiation Dose
SR, which follows TID 10040 "Enhanced X-Ray Radiation Dose";
:func:`patient_dose_tree` that of a Patient Radiation Dose SR, which
follows TID 10030 "Patient Radiation Dose";
:func:`radiopharmaceutical_dose_tree` that of a Radiopharmaceutical Radiation
Dose SR, which follows TID 10021 "Radiopharmaceutical Radiation Dose",
:func:`imaging_report_tree` that of a Basic Text SR, Enhanced SR, or
Comprehensive SR, which follows TID 2000 "Basic Diagnostic Imaging Report",
and :func:`measurement_report_tree` that of a Comprehensive 3D SR or
Extensible SR, which follows TID 1500 "Measurement Report". Each holds only
the rows that its templates require where they are included, for the
procedure that its docstring names, apart from the templates that it names
as left out: the report that Clean Structured Content is first assessed on
(D-047). Each content item's relationship, Value Type, and
concept name is a row of a template of DICOM PS3.16 2026d, cited beside it,
and each coded value is one of the context group that the row names. Code
meanings are those of PS3.16 Annex D for DCM codes, and those the templates
and context groups give for the others.

The value of each content item that can identify a person, a device, or a
time, a UIDREF, DATETIME, PNAME, or TEXT item, comes from the caller, so
that the synthetic corpus
(:mod:`~pymedphys._dicom.deidentify.synthetic_corpus`) can plant a marker in
it; but the Study Instance UID that names the scope of accumulation, which
is the study's own. The frame of reference of a measurement report's
volumetric region is the caller's too, so that it can be the collection's
own, and so is the report that a patient dose estimate used, so that it can
be the collection's CT dose report. Every other value is a code, a number,
or a coordinate, the same in every tree. The tests build reports with the
optional rows besides, from the same codes
(``tests/dicom/_synthetic_dose_reports.py`` and
``tests/dicom/_synthetic_structured_reports.py``).
"""

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
ENHANCED_X_RAY_RADIATION_DOSE_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.76"
PATIENT_RADIATION_DOSE_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.73"
# The root template of each, as Content Template Sequence (0040,A504) names it.
ROOT_TEMPLATES = {
    X_RAY_RADIATION_DOSE_SR_STORAGE: "10001",
    RADIOPHARMACEUTICAL_RADIATION_DOSE_SR_STORAGE: "10021",
    ENHANCED_X_RAY_RADIATION_DOSE_SR_STORAGE: "10040",
    PATIENT_RADIATION_DOSE_SR_STORAGE: "10030",
    BASIC_TEXT_SR_STORAGE: "2000",
    ENHANCED_SR_STORAGE: "2000",
    COMPREHENSIVE_SR_STORAGE: "2000",
    COMPREHENSIVE_3D_SR_STORAGE: "1500",
    EXTENSIBLE_SR_STORAGE: "1500",
}
# The other root template that PS3.3 Section A.35.8 allows in an X-Ray
# Radiation Dose SR, of a CT Radiation Dose report.
CT_RADIATION_DOSE_TEMPLATE = "10011"


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
# TID 10011 to 10015.
START_OF_X_RAY_IRRADIATION = Code("113809", "DCM", "Start of X-Ray Irradiation")
END_OF_X_RAY_IRRADIATION = Code("113810", "DCM", "End of X-Ray Irradiation")
CT_ACCUMULATED_DOSE_DATA = Code("113811", "DCM", "CT Accumulated Dose Data")
TOTAL_NUMBER_OF_IRRADIATION_EVENTS = Code(
    "113812", "DCM", "Total Number of Irradiation Events"
)
CT_DOSE_LENGTH_PRODUCT_TOTAL = Code("113813", "DCM", "CT Dose Length Product Total")
CT_ACQUISITION = Code("113819", "DCM", "CT Acquisition")
CT_ACQUISITION_TYPE = Code("113820", "DCM", "CT Acquisition Type")
CT_ACQUISITION_PARAMETERS = Code("113822", "DCM", "CT Acquisition Parameters")
EXPOSURE_TIME = Code("113824", "DCM", "Exposure Time")
SCANNING_LENGTH = Code("113825", "DCM", "Scanning Length")
NOMINAL_SINGLE_COLLIMATION_WIDTH = Code(
    "113826", "DCM", "Nominal Single Collimation Width"
)
NOMINAL_TOTAL_COLLIMATION_WIDTH = Code(
    "113827", "DCM", "Nominal Total Collimation Width"
)
PITCH_FACTOR = Code("113828", "DCM", "Pitch Factor")
NUMBER_OF_X_RAY_SOURCES = Code("113823", "DCM", "Number of X-Ray Sources")
CT_X_RAY_SOURCE_PARAMETERS = Code("113831", "DCM", "CT X-Ray Source Parameters")
IDENTIFICATION_OF_THE_X_RAY_SOURCE = Code(
    "113832", "DCM", "Identification of the X-Ray Source"
)
KVP = Code("113733", "DCM", "KVP")
MAXIMUM_X_RAY_TUBE_CURRENT = Code("113833", "DCM", "Maximum X-Ray Tube Current")
X_RAY_TUBE_CURRENT = Code("113734", "DCM", "X-Ray Tube Current")
EXPOSURE_TIME_PER_ROTATION = Code("113834", "DCM", "Exposure Time per Rotation")
CT_DOSE = Code("113829", "DCM", "CT Dose")
MEAN_CTDIVOL = Code("113830", "DCM", "Mean CTDIvol")
CTDIW_PHANTOM_TYPE = Code("113835", "DCM", "CTDIw Phantom Type")
DLP = Code("113838", "DCM", "DLP")
DOSE_CHECK_ALERT_DETAILS = Code("113900", "DCM", "Dose Check Alert Details")
DLP_ALERT_VALUE_CONFIGURED = Code("113901", "DCM", "DLP Alert Value Configured")
CTDIVOL_ALERT_VALUE_CONFIGURED = Code("113902", "DCM", "CTDIvol Alert Value Configured")
DLP_ALERT_VALUE = Code("113903", "DCM", "DLP Alert Value")
ACCUMULATED_DLP_FORWARD_ESTIMATE = Code(
    "113905", "DCM", "Accumulated DLP Forward Estimate"
)
DOSE_CHECK_NOTIFICATION_DETAILS = Code(
    "113908", "DCM", "Dose Check Notification Details"
)
DLP_NOTIFICATION_VALUE_CONFIGURED = Code(
    "113909", "DCM", "DLP Notification Value Configured"
)
CTDIVOL_NOTIFICATION_VALUE_CONFIGURED = Code(
    "113910", "DCM", "CTDIvol Notification Value Configured"
)
DLP_NOTIFICATION_VALUE = Code("113911", "DCM", "DLP Notification Value")
DLP_FORWARD_ESTIMATE = Code("113913", "DCM", "DLP Forward Estimate")
# TID 10040, 10042, and 10043.
IRRADIATION_EVENT_SUMMARY_DATA = Code("130501", "DCM", "Irradiation Event Summary Data")
DATETIME_ENDED = Code("111527", "DCM", "DateTime Ended")
IRRADIATION_DETAILS = Code("130505", "DCM", "Irradiation Details")
FRAME_OF_REFERENCE_UID_CONCEPT = Code("112227", "DCM", "Frame of Reference UID")
RDSR_FRAME_OF_REFERENCE_ORIGIN = Code("130506", "DCM", "RDSR Frame of Reference Origin")
# TID 10030, 10031, and 10033.
PATIENT_RADIATION_DOSE_REPORT = Code("128401", "DCM", "Patient Radiation Dose Report")
RADIATION_DOSE_ESTIMATE = Code("128402", "DCM", "Radiation Dose Estimate")
RADIATION_DOSE_ESTIMATE_NAME = Code("128403", "DCM", "Radiation Dose Estimate Name")
ORGAN = Code("113343008", "SCT", "Organ")
ORGAN_DOSE_INFORMATION = Code("113517", "DCM", "Organ Dose Information")
RADIATION_DOSE_ESTIMATE_METHODOLOGY = Code(
    "128415", "DCM", "Radiation Dose Estimate Methodology"
)
SR_INSTANCE_USED = Code("128416", "DCM", "SR Instance Used")
PATIENT_RADIATION_DOSE_MODEL = Code("128500", "DCM", "Patient Radiation Dose Model")
PATIENT_MODEL_TYPE = Code("128417", "DCM", "Patient Model Type")
RADIATION_TRANSPORT_MODEL_TYPE = Code("128420", "DCM", "Radiation Transport Model Type")
PATIENT_MODEL_DEMOGRAPHICS = Code("128427", "DCM", "Patient Model Demographics")
MODEL_MINIMUM_AGE = Code("128428", "DCM", "Model Minimum Age")
RADIATION_DOSE_ESTIMATE_METHOD = Code("128476", "DCM", "Radiation Dose Estimate Method")
RADIATION_DOSE_ESTIMATE_METHOD_TYPE = Code(
    "128477", "DCM", "Radiation Dose Estimate Method Type"
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
COMPUTED_TOMOGRAPHY_X_RAY = Code(
    "77477000", "SCT", "Computed Tomography X-Ray"
)  # TID 10011 row 2
SPIRAL_ACQUISITION = Code("116152004", "SCT", "Spiral Acquisition")  # CID 10013
BODY_PHANTOM = Code("113691", "DCM", "IEC 320mm Body CT Dosimetry Phantom")  # CID 4053
YES = Code("373066001", "SCT", "Yes")  # CID 230
NO = Code("373067005", "SCT", "No")  # CID 230
IRRADIATION_AUTHORIZING = Code("113850", "DCM", "Irradiation Authorizing")
PLAIN_RADIOGRAPHY = Code("168537006", "SCT", "Plain radiography")  # CID 10005
EQUIPMENT_ORIGIN = Code("130537", "DCM", "Equipment Origin")  # CID 10074
ENTIRE_BODY = Code("38266002", "SCT", "Entire body")  # CID 10060
MEAN_ABSORBED_RADIATION_DOSE = Code(
    "128533", "DCM", "Mean Absorbed Radiation Dose"
)  # CID 10061
ANTHROPOMORPHIC_MODEL = Code("128404", "DCM", "Anthropomorphic Model")  # CID 10064
VOXELIZED_TRANSPORT_MODEL = Code(
    "128422", "DCM", "Voxelized Radiation Transport Model"
)  # CID 10065
ANALYTICAL_ALGORITHM = Code("128480", "DCM", "Analytical Algorithm")  # CID 10068
# Units, as the rows give them.
GRAY_SQUARE_METRE = Code("Gy.m2", "UCUM", "Gy.m2")
SECONDS = Code("s", "UCUM", "seconds")
MEGABECQUEREL = Code("MBq", "UCUM", "MBq")
CUBIC_MILLIMETRE = Code("mm3", "UCUM", "cubic millimeter")  # CID 7181, by 7462
EVENTS = Code("{events}", "UCUM", "events")
MILLIGRAY_CENTIMETRE = Code("mGy.cm", "UCUM", "mGy.cm")
MILLIMETRE = Code("mm", "UCUM", "mm")
RATIO = Code("{ratio}", "UCUM", "ratio")
X_RAY_SOURCES = Code("{X-Ray sources}", "UCUM", "X-Ray sources")
KILOVOLT = Code("kV", "UCUM", "kV")
MILLIAMPERE = Code("mA", "UCUM", "mA")
MILLIGRAY = Code("mGy", "UCUM", "mGy")
YEAR = Code("a", "UCUM", "year")  # CID 7456

# The attribute of the value of each Value Type that ``item`` takes as text
# (PS3.3 Table 10-2).
_TEXT_VALUES = {
    "TEXT": "TextValue",
    "PNAME": "PersonName",
    "DATETIME": "DateTime",
    "UIDREF": "UID",
}


def item(
    relationship: str | None,
    value_type: str,
    concept: Code,
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
    concept : Code
        Its concept name.
    *children : pydicom.Dataset
        The items of its Content Sequence, if any.
    **value
        Its value, by Value Type: ``code`` (a :class:`Code`) for CODE,
        ``number`` and ``units`` for NUM, ``text`` for TEXT, PNAME,
        DATETIME, and UIDREF, ``sop_class`` and ``sop_instance`` for
        COMPOSITE, and ``graphic_type``, ``points``, and
        ``frame_of_reference`` for SCOORD3D.
    """
    dataset = pydicom.Dataset()
    if relationship is not None:
        dataset.RelationshipType = relationship
    dataset.ValueType = value_type
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
    elif value_type == "COMPOSITE":
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


# A function that returns a new value for a content item of a Value Type,
# UIDREF, DATETIME, or PNAME.
Values = Callable[[str], str]


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


def _device_observer(uid: str) -> tuple[pydicom.Dataset, pydicom.Dataset]:
    """Return TID 1002 row 1 and TID 1004 row 1, M, for the recording device."""
    return (
        item("HAS OBS CONTEXT", "CODE", OBSERVER_TYPE, code=DEVICE),
        item("HAS OBS CONTEXT", "UIDREF", DEVICE_OBSERVER_UID_CONCEPT, text=uid),
    )


def _procedure(procedure: Code) -> pydicom.Dataset:
    """Return the Procedure reported, M, with its Has Intent, diagnostic."""
    return item(
        "HAS CONCEPT MOD",
        "CODE",
        PROCEDURE_REPORTED,
        item("HAS CONCEPT MOD", "CODE", HAS_INTENT, code=DIAGNOSTIC_INTENT),
        code=procedure,
    )


def _number(concept: Code, number: str, units: Code) -> pydicom.Dataset:
    """Return a NUM item that the root's tree CONTAINS."""
    return item("CONTAINS", "NUM", concept, number=number, units=units)


def _code(concept: Code, code: Code) -> pydicom.Dataset:
    """Return a CODE item that the root's tree CONTAINS."""
    return item("CONTAINS", "CODE", concept, code=code)


def _dose_check(person: str) -> tuple[pydicom.Dataset, pydicom.Dataset]:
    """Return TID 10015 "CT Dose Check Details" of a scanner that implements it.

    Rows 1 and 10, the alert and notification containers, are required
    where the scanner implements dose alerts and notifications. Each is of
    an event whose forward estimate exceeded its configured DLP value, so
    that rows 2 to 4 and 6, and rows 11 to 13 and 15, are required, with
    row 9, TID 1020 rows 1 and 2, the person who authorised the event. The
    CTDIvol values are not configured, and the optional reasons for
    proceeding, rows 8 and 17, which are free text, are left out.
    """
    return (
        item(
            "CONTAINS",
            "CONTAINER",
            DOSE_CHECK_ALERT_DETAILS,
            _code(DLP_ALERT_VALUE_CONFIGURED, YES),
            _code(CTDIVOL_ALERT_VALUE_CONFIGURED, NO),
            _number(DLP_ALERT_VALUE, "1000", MILLIGRAY_CENTIMETRE),
            _number(ACCUMULATED_DLP_FORWARD_ESTIMATE, "1210", MILLIGRAY_CENTIMETRE),
            item(
                "CONTAINS",
                "PNAME",
                PERSON_NAME,
                item(
                    "HAS PROPERTIES",
                    "CODE",
                    PERSON_ROLE_IN_PROCEDURE,
                    code=IRRADIATION_AUTHORIZING,
                ),
                text=person,
            ),
        ),
        item(
            "CONTAINS",
            "CONTAINER",
            DOSE_CHECK_NOTIFICATION_DETAILS,
            _code(DLP_NOTIFICATION_VALUE_CONFIGURED, YES),
            _code(CTDIVOL_NOTIFICATION_VALUE_CONFIGURED, NO),
            _number(DLP_NOTIFICATION_VALUE, "500", MILLIGRAY_CENTIMETRE),
            _number(DLP_FORWARD_ESTIMATE, "640", MILLIGRAY_CENTIMETRE),
        ),
    )


def ct_dose_tree(values: Values, study: str) -> pydicom.Dataset:
    """Return the root of a CT Radiation Dose report's tree, TID 10011.

    The report, an X-Ray Radiation Dose SR's, is of one spiral scan of the
    chest, whose dose was collected automatically (TID 10011 row 12) by
    the scanner, which recorded it and implements dose checks, so that TID
    10011 rows 1 to 10 and 12, TID 10012 rows 1 to 3, TID 10013 rows 1, 3,
    4, 6 to 19, 21 to 23, 26, and 35, TID 10014 row 1, and the rows of TID
    10015 that :func:`_dose_check` names are required. It leaves out TID
    10012 row 3a, the subtotals for events whose DLP used different
    phantoms, which carry codes and numbers. Its target region is the
    chest, as :func:`x_ray_dose_tree`'s is.

    Parameters
    ----------
    values : callable
        Returns the value of the Device Observer UID, the Start and End of
        X-Ray Irradiation, the Irradiation Event UID, the Identification of
        the X-Ray Source, and the Person Name of the person who authorised
        the dose check's alert, given each one's Value Type, in that order.
    study : str
        The Study Instance UID that the scope of accumulation names.
    """
    observer_uid = values("UIDREF")
    started = values("DATETIME")
    ended = values("DATETIME")
    event_uid = values("UIDREF")
    source = values("TEXT")
    person = values("PNAME")
    parameters = item(
        "CONTAINS",
        "CONTAINER",
        CT_ACQUISITION_PARAMETERS,
        # TID 10013 rows 8 to 14, with TID 10014 row 1 by row 9.
        _number(EXPOSURE_TIME, "9.6", SECONDS),
        _number(SCANNING_LENGTH, "412", MILLIMETRE),
        _number(NOMINAL_SINGLE_COLLIMATION_WIDTH, "0.625", MILLIMETRE),
        _number(NOMINAL_TOTAL_COLLIMATION_WIDTH, "40", MILLIMETRE),
        _number(PITCH_FACTOR, "0.984", RATIO),
        _number(NUMBER_OF_X_RAY_SOURCES, "1", X_RAY_SOURCES),
        # TID 10013 rows 14 to 19.
        item(
            "CONTAINS",
            "CONTAINER",
            CT_X_RAY_SOURCE_PARAMETERS,
            item("CONTAINS", "TEXT", IDENTIFICATION_OF_THE_X_RAY_SOURCE, text=source),
            _number(KVP, "120", KILOVOLT),
            _number(MAXIMUM_X_RAY_TUBE_CURRENT, "380", MILLIAMPERE),
            _number(X_RAY_TUBE_CURRENT, "210", MILLIAMPERE),
            _number(EXPOSURE_TIME_PER_ROTATION, "0.5", SECONDS),
        ),
    )
    return item(
        None,
        "CONTAINER",
        X_RAY_RADIATION_DOSE_REPORT,
        # TID 10011 rows 2 and 3, M.
        _procedure(COMPUTED_TOMOGRAPHY_X_RAY),
        # TID 10011 row 4, TID 1002 row 1 and TID 1004 row 1.
        *_device_observer(observer_uid),
        # TID 10011 rows 5 to 8, M.
        item("HAS OBS CONTEXT", "DATETIME", START_OF_X_RAY_IRRADIATION, text=started),
        item("HAS OBS CONTEXT", "DATETIME", END_OF_X_RAY_IRRADIATION, text=ended),
        item(
            "HAS OBS CONTEXT",
            "CODE",
            SCOPE_OF_ACCUMULATION,
            item("HAS PROPERTIES", "UIDREF", STUDY_INSTANCE_UID, text=study),
            code=STUDY_SCOPE,
        ),
        # TID 10011 row 9, TID 10012 rows 1 to 3.
        item(
            "CONTAINS",
            "CONTAINER",
            CT_ACCUMULATED_DOSE_DATA,
            _number(TOTAL_NUMBER_OF_IRRADIATION_EVENTS, "1", EVENTS),
            _number(CT_DOSE_LENGTH_PRODUCT_TOTAL, "640", MILLIGRAY_CENTIMETRE),
        ),
        # TID 10011 row 10, TID 10013 rows 1, 3, 4, 6, 7, and 21.
        item(
            "CONTAINS",
            "CONTAINER",
            CT_ACQUISITION,
            _code(TARGET_REGION, CHEST),
            _code(CT_ACQUISITION_TYPE, SPIRAL_ACQUISITION),
            item("CONTAINS", "UIDREF", IRRADIATION_EVENT_UID_CONCEPT, text=event_uid),
            parameters,
            # TID 10013 rows 21 to 23, 26, and 35, which includes TID 10015.
            item(
                "CONTAINS",
                "CONTAINER",
                CT_DOSE,
                _number(MEAN_CTDIVOL, "11.3", MILLIGRAY),
                _code(CTDIW_PHANTOM_TYPE, BODY_PHANTOM),
                _number(DLP, "640", MILLIGRAY_CENTIMETRE),
                *_dose_check(person),
            ),
        ),
        # TID 10011 row 12, M.
        _code(SOURCE_OF_DOSE_INFORMATION, AUTOMATED_DATA_COLLECTION),
    )


def enhanced_x_ray_dose_tree(values: Values) -> pydicom.Dataset:
    """Return the root of an Enhanced X-Ray Radiation Dose SR's tree, TID 10040.

    The report is of one stationary radiograph whose dose was collected
    automatically (TID 10040 row 12) by the device that recorded it, so
    that TID 10040 rows 1 to 6, 8, 9, and 12, TID 10042 rows 1 to 5 and 8,
    and TID 10043 rows 1 to 5 are required. TID 10040 row 7, TID 10041
    "Accumulated Dose Data", is optional and left out. Of the rows required
    where they are included, it leaves out TID 10043 rows 7, 8, and 11 to
    14, TID 10044 "Radiation Source Characteristics", 10045 "Radiation
    Technique", 10048 "Radiation Output", 10049 "Radiation Field Area",
    10050 "X-Ray Source Reference Coordinate System", and 10051 "Beam
    Position", and the filtration and attenuator templates that rows 9, 10,
    15, and 16 include where they apply, whose values are mostly of the
    Value Types TABLE and SCOORD3D. Its DateTime Ended items, which Table
    E.3.4-1 gives X, are required.

    Parameters
    ----------
    values : callable
        Returns the value of the Device Observer UID; the Irradiation Event
        UID, DateTime Started, DateTime Ended, and Identification of the
        X-Ray Source of the event summary; and the DateTime Started,
        DateTime Ended, and Frame of Reference UID of the irradiation
        details, given each one's Value Type, in that order.
    """
    observer_uid = values("UIDREF")
    event_uid = values("UIDREF")
    event_started = values("DATETIME")
    event_ended = values("DATETIME")
    source = values("TEXT")
    details_started = values("DATETIME")
    details_ended = values("DATETIME")
    frame_of_reference = values("UIDREF")
    return item(
        None,
        "CONTAINER",
        X_RAY_RADIATION_DOSE_REPORT,
        # TID 10040 rows 2 to 4, M; row 2 is TID 1204 row 1.
        item("HAS CONCEPT MOD", "CODE", LANGUAGE, code=ENGLISH),
        _procedure(PLAIN_RADIOGRAPHY),
        # TID 10040 row 5, TID 1002 row 1 and TID 1004 row 1.
        *_device_observer(observer_uid),
        # TID 10040 row 6, M.
        item("HAS OBS CONTEXT", "CODE", SCOPE_OF_ACCUMULATION, code=STUDY_SCOPE),
        # TID 10040 row 8, TID 10042 rows 1 to 5 and 8.
        item(
            "CONTAINS",
            "CONTAINER",
            IRRADIATION_EVENT_SUMMARY_DATA,
            item("CONTAINS", "UIDREF", IRRADIATION_EVENT_UID_CONCEPT, text=event_uid),
            item("CONTAINS", "DATETIME", DATETIME_STARTED, text=event_started),
            item("CONTAINS", "DATETIME", DATETIME_ENDED, text=event_ended),
            item("CONTAINS", "TEXT", IDENTIFICATION_OF_THE_X_RAY_SOURCE, text=source),
            _code(IRRADIATION_EVENT_TYPE, STATIONARY_ACQUISITION),
        ),
        # TID 10040 row 9, TID 10043 rows 1 to 5.
        item(
            "CONTAINS",
            "CONTAINER",
            IRRADIATION_DETAILS,
            item("CONTAINS", "DATETIME", DATETIME_STARTED, text=details_started),
            item("CONTAINS", "DATETIME", DATETIME_ENDED, text=details_ended),
            item(
                "CONTAINS",
                "UIDREF",
                FRAME_OF_REFERENCE_UID_CONCEPT,
                text=frame_of_reference,
            ),
            _code(RDSR_FRAME_OF_REFERENCE_ORIGIN, EQUIPMENT_ORIGIN),
        ),
        # TID 10040 row 12, M.
        _code(SOURCE_OF_DOSE_INFORMATION, AUTOMATED_DATA_COLLECTION),
    )


def patient_dose_tree(values: Values, report: str) -> pydicom.Dataset:
    """Return the root of a Patient Radiation Dose SR's tree, TID 10030.

    The report gives one estimate, the mean dose to the entire body,
    observed by the device, an application, that estimated it from a CT
    Radiation Dose report, with an anthropomorphic model for adults, whose
    minimum age TID 10033 row 14 gives, and an analytical method. So TID
    10030 rows 1 to 4, TID 10031 rows 1, 2, 4, 6, 7, and 10, and TID 10033
    rows 1, 2, 5 to 7, 13, 14, 40, and 41 are required. It leaves out the
    model's data (TID 10033 rows 8 to 10), required only where the model
    has data of its own, and rows 21 to 39, the model's registration and
    the beam attenuators, required only where the estimate used them.

    Parameters
    ----------
    values : callable
        Returns the value of the Device Observer UID and of the Radiation
        Dose Estimate Name, given each one's Value Type, in that order.
    report : str
        The SOP Instance UID of the X-Ray Radiation Dose SR that the
        estimate used (TID 10033 row 2).
    """
    observer_uid = values("UIDREF")
    name = values("TEXT")
    methodology = item(
        "CONTAINS",
        "CONTAINER",
        RADIATION_DOSE_ESTIMATE_METHODOLOGY,
        # TID 10033 row 2.
        item(
            "CONTAINS",
            "COMPOSITE",
            SR_INSTANCE_USED,
            sop_class=X_RAY_RADIATION_DOSE_SR_STORAGE,
            sop_instance=report,
        ),
        # TID 10033 rows 5 to 7, 13, and 14.
        item(
            "CONTAINS",
            "CONTAINER",
            PATIENT_RADIATION_DOSE_MODEL,
            _code(PATIENT_MODEL_TYPE, ANTHROPOMORPHIC_MODEL),
            _code(RADIATION_TRANSPORT_MODEL_TYPE, VOXELIZED_TRANSPORT_MODEL),
            item(
                "CONTAINS",
                "CONTAINER",
                PATIENT_MODEL_DEMOGRAPHICS,
                _number(MODEL_MINIMUM_AGE, "18", YEAR),
            ),
        ),
        # TID 10033 rows 40 and 41.
        item(
            "CONTAINS",
            "CONTAINER",
            RADIATION_DOSE_ESTIMATE_METHOD,
            _code(RADIATION_DOSE_ESTIMATE_METHOD_TYPE, ANALYTICAL_ALGORITHM),
        ),
    )
    return item(
        None,
        "CONTAINER",
        PATIENT_RADIATION_DOSE_REPORT,
        # TID 10030 row 2, TID 1204 row 1.
        item("HAS CONCEPT MOD", "CODE", LANGUAGE, code=ENGLISH),
        # TID 10030 row 3, TID 1002 row 1 and TID 1004 row 1.
        *_device_observer(observer_uid),
        # TID 10030 row 4, TID 10031 rows 1, 2, 4, and 6.
        item(
            "CONTAINS",
            "CONTAINER",
            RADIATION_DOSE_ESTIMATE,
            item("HAS CONCEPT MOD", "TEXT", RADIATION_DOSE_ESTIMATE_NAME, text=name),
            methodology,
            # TID 10031 rows 6, 7, and 10.
            item(
                "CONTAINS",
                "CONTAINER",
                ORGAN_DOSE_INFORMATION,
                _code(ORGAN, ENTIRE_BODY),
                _number(MEAN_ABSORBED_RADIATION_DOSE, "3.2", MILLIGRAY),
            ),
        ),
    )
