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

"""Synthetic general Structured Reports and Key Object Selection documents.

Four builders give one report each, whose content tree follows a root
template of DICOM PS3.16 2026d:

- :func:`imaging_report`, a Comprehensive SR whose tree follows TID 2000
  "Basic Diagnostic Imaging Report";
- :func:`measurement_report`, a Comprehensive 3D SR whose tree follows TID
  1500 "Measurement Report", with a volumetric region of TID 1411 given by
  SCOORD3D;
- :func:`key_object_selection`, a Key Object Selection Document whose tree
  follows TID 2010 "Key Object Selection"; and
- :func:`mammography_cad_report`, a Mammography CAD SR whose tree follows
  TID 4000 "Mammography CAD Document Root".

Each content item's relationship, Value Type, and concept name is a row of
a template of PS3.16 2026d, cited beside it, and each coded value is one of
the context group that the row names, or, where the row names none, of the
context group cited beside it. Code meanings are those of PS3.16 Annex D
for DCM codes, and those the templates and context groups give for the
others; a language's is the description of its subtag in the IANA Language
Subtag Registry, which CID 5000 names.

Each report holds every row that its templates require where they are
included, and the optional rows that carry identifying values or coded
concepts that Clean Structured Content cannot look up. The optional rows
are keyed by their template and row, such as ``"TID 1003 row 2"``, so that
a test can build a report with any of them. The header carries identifying
values too: the institution, station, and device serial number, the
referring physician, the accession number, and, in a report whose
Verification Flag is VERIFIED, the verifying observer and organisation.

Text that must never reach a written file under the Basic Profile carries
``SENTINEL``, except the names of people, whose words occur in no code
meaning, since the residual search looks for each word of a name. Every UID is invented under ``2.25.``, the patient is
fictitious, and no value comes from a real report.
"""

# The four reports share their codes, header, and observation context, so
# they stay in one module.
# pylint: disable = too-many-lines

import dataclasses

from pymedphys._imports import pydicom

COMPREHENSIVE_SR = "1.2.840.10008.5.1.4.1.1.88.33"
COMPREHENSIVE_3D_SR = "1.2.840.10008.5.1.4.1.1.88.34"
KEY_OBJECT_SELECTION_DOCUMENT = "1.2.840.10008.5.1.4.1.1.88.59"
MAMMOGRAPHY_CAD_SR = "1.2.840.10008.5.1.4.1.1.88.50"
COMPREHENSIVE_SR_IOD = "Comprehensive SR"
COMPREHENSIVE_3D_SR_IOD = "Comprehensive 3D SR"
KEY_OBJECT_SELECTION_IOD = "Key Object Selection Document"
MAMMOGRAPHY_CAD_SR_IOD = "Mammography CAD SR"
# The images that the reports reference.
MR_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.4"
MAMMOGRAPHY_FOR_PRESENTATION = "1.2.840.10008.5.1.4.1.1.1.2"

SENTINEL = "SENTINEL"
PATIENT_ID = "SYNTHETIC-3M8R"
# Person names whose words occur in no code meaning, so that the residual
# search, which looks for each word of a name, finds them only where they
# are kept.
PATIENTS_NAME = "ZORVANE^QUILLA"
OBSERVERS_NAME = "YARROWBY^TESSALIN"
REFERRERS_NAME = "WINTERCOMBE^ODALYS"
VERIFIERS_NAME = "VELLACOTT^RHIANNE"
NAMES = (PATIENTS_NAME, OBSERVERS_NAME, REFERRERS_NAME, VERIFIERS_NAME)
STUDY = "2.25.8100"
MR_SERIES = "2.25.8200"
MR_IMAGE = "2.25.8201"
MG_SERIES = "2.25.8300"
MG_IMAGE = "2.25.8301"
FRAME_OF_REFERENCE = "2.25.8400"
IMAGING_REPORT = ("2.25.8500", "2.25.8501")
MEASUREMENT_REPORT = ("2.25.8510", "2.25.8511")
KEY_OBJECTS = ("2.25.8520", "2.25.8521")
CAD_REPORT = ("2.25.8530", "2.25.8531")
# The UIDs that content items carry, other than the references above.
TRACKING_UID = "2.25.8601"
DEVICE_OBSERVER_UID = "2.25.8602"
SUBJECT_UID = "2.25.8603"
UIDS = (
    STUDY,
    MR_SERIES,
    MR_IMAGE,
    MG_SERIES,
    MG_IMAGE,
    FRAME_OF_REFERENCE,
    *IMAGING_REPORT,
    *MEASUREMENT_REPORT,
    *KEY_OBJECTS,
    *CAD_REPORT,
    TRACKING_UID,
    DEVICE_OBSERVER_UID,
    SUBJECT_UID,
)
# The dates and times that the reports carry, none of which a modified or
# dummy value repeats.
STUDY_DATE = "20260412"
STUDY_TIME = "101500"
CONTENT_DATE = "20260413"
CONTENT_TIME = "143000"
BIRTH_DATE = "19700521"
FOLLOW_UP_DATE = "20270412"
VERIFICATION_DATETIME = "20260414091500"
DATES = (
    STUDY_DATE,
    CONTENT_DATE,
    BIRTH_DATE,
    FOLLOW_UP_DATE,
    VERIFICATION_DATETIME,
)


@dataclasses.dataclass(frozen=True)
class Code:
    """A code: its Code Value, Coding Scheme Designator, and Code Meaning."""

    value: str
    designator: str
    meaning: str

    def dataset(self):
        """Return the code as an item of a code sequence."""
        code = pydicom.Dataset()
        code.CodeValue = self.value
        code.CodingSchemeDesignator = self.designator
        code.CodeMeaning = self.meaning
        return code


# Document titles, from CID 7000, CID 7021, and CID 7010, and the root of
# TID 4000. Most of CID 7000's titles are coded in LOINC; it gives DCM codes
# only to a few, among them the breast imaging report.
DIAGNOSTIC_IMAGING_REPORT = Code("18748-4", "LN", "Diagnostic Imaging Report")
BREAST_IMAGING_REPORT = Code("111400", "DCM", "Breast Imaging Report")
IMAGING_MEASUREMENT_REPORT = Code("126000", "DCM", "Imaging Measurement Report")
OF_INTEREST = Code("113000", "DCM", "Of Interest")
MAMMOGRAPHY_CAD_REPORT = Code("111036", "DCM", "Mammography CAD Report")
# Concept names, by the first template row that uses them.
LANGUAGE = Code("121049", "DCM", "Language of Content Item and Descendants")
# TID 1002, 1003, 1004, 1005, and 1007.
OBSERVER_TYPE = Code("121005", "DCM", "Observer Type")
PERSON_OBSERVER_NAME = Code("121008", "DCM", "Person Observer Name")
PERSON_OBSERVERS_LOGIN_NAME = Code("128774", "DCM", "Person Observer's Login Name")
PERSON_OBSERVERS_ORGANIZATION_NAME = Code(
    "121009", "DCM", "Person Observer's Organization Name"
)
DEVICE_OBSERVER_UID_CONCEPT = Code("121012", "DCM", "Device Observer UID")
DEVICE_OBSERVER_NAME = Code("121013", "DCM", "Device Observer Name")
UNIQUE_DEVICE_IDENTIFIERS = Code("121000", "DCM", "Unique Device Identifiers")
UNIQUE_DEVICE_IDENTIFIER = Code("74711-3", "LN", "Unique Device Identifier")
PROCEDURE_STUDY_INSTANCE_UID = Code("121018", "DCM", "Procedure Study Instance UID")
ACCESSION_NUMBER = Code("121022", "DCM", "Accession Number")
SUBJECT_UID_CONCEPT = Code("121028", "DCM", "Subject UID")
SUBJECT_NAME = Code("121029", "DCM", "Subject Name")
SUBJECT_ID = Code("121030", "DCM", "Subject ID")
SUBJECT_BIRTH_DATE = Code("121031", "DCM", "Subject Birth Date")
SUBJECT_SEX = Code("121032", "DCM", "Subject Sex")
SUBJECT_AGE = Code("121033", "DCM", "Subject Age")
# TID 2000 and 2002.
IMPRESSIONS = Code("19005-8", "LN", "Impressions")  # CID 7001
IMPRESSION = Code("121073", "DCM", "Impression")  # CID 7002
# The concepts of CID 7002 "Diagnostic Imaging Report Element", which TID
# 2002 gives its narrative's TEXT items, in the context group's order.
DIAGNOSTIC_IMAGING_REPORT_ELEMENTS = (
    Code("11329-0", "LN", "History"),
    Code("55115-0", "LN", "Request"),
    Code("121065", "DCM", "Procedure Description"),
    Code("121069", "DCM", "Previous Finding"),
    Code("121071", "DCM", "Finding"),
    IMPRESSION,
    Code("121075", "DCM", "Recommendation"),
    Code("121077", "DCM", "Conclusion"),
    Code("116224001", "SCT", "Complication of Procedure"),
    Code("55108-5", "LN", "Patient Presentation"),
    Code("55112-7", "LN", "Summary"),
)
# TID 1500, 1411, 1419, 1502, 1600, 1601, and 1602.
PROCEDURE_REPORTED = Code("121058", "DCM", "Procedure reported")
IMAGE_LIBRARY = Code("111028", "DCM", "Image Library")
IMAGE_LIBRARY_GROUP = Code("126200", "DCM", "Image Library Group")
MODALITY = Code("121139", "DCM", "Modality")
STUDY_DATE_CONCEPT = Code("111060", "DCM", "Study Date")
STUDY_TIME_CONCEPT = Code("111061", "DCM", "Study Time")
SERIES_INSTANCE_UID = Code("112002", "DCM", "Series Instance UID")
SERIES_DESCRIPTION = Code("131563", "DCM", "Series Description")
CONTENT_DATE_CONCEPT = Code("111018", "DCM", "Content Date")
CONTENT_TIME_CONCEPT = Code("111019", "DCM", "Content Time")
FRAME_OF_REFERENCE_UID = Code("112227", "DCM", "Frame of Reference UID")
IMAGING_MEASUREMENTS = Code("126010", "DCM", "Imaging Measurements")
MEASUREMENT_GROUP = Code("125007", "DCM", "Measurement Group")
ACTIVITY_SESSION = Code("C67447", "NCIt", "Activity Session")
TRACKING_IDENTIFIER = Code("112039", "DCM", "Tracking Identifier")
TRACKING_UNIQUE_IDENTIFIER = Code("112040", "DCM", "Tracking Unique Identifier")
TIME_POINT = Code("C2348792", "UMLS", "Time Point")
SUBJECT_TIME_POINT_IDENTIFIER = Code("126070", "DCM", "Subject Time Point Identifier")
VOLUME_SURFACE = Code("121231", "DCM", "Volume Surface")
SOURCE_SERIES_FOR_SEGMENTATION = Code("121232", "DCM", "Source series for segmentation")
ILLUSTRATION_OF_ROI = Code("121200", "DCM", "Illustration of ROI")
FINDING_SITE = Code("363698007", "SCT", "Finding Site")
LATERALITY = Code("272741003", "SCT", "Laterality")
# The SNOMED IDs that PS3.16 Annex O, Table O-1, gives the same concepts,
# coded by the retired designator SRT.
FINDING_SITE_SRT = Code("G-C0E3", "SRT", "Finding Site")
LATERALITY_SRT = Code("G-C171", "SRT", "Laterality")
# TID 2010.
KEY_OBJECT_DESCRIPTION = Code("113012", "DCM", "Key Object Description")
# TID 4000, 4001, 4002, 4015, 4017, 4019, and 4020.
CAD_PROCESSING_AND_FINDINGS_SUMMARY = Code(
    "111017", "DCM", "CAD Processing and Findings Summary"
)
SUMMARY_OF_DETECTIONS = Code("111064", "DCM", "Summary of Detections")
SUMMARY_OF_ANALYSES = Code("111065", "DCM", "Summary of Analyses")
SUCCESSFUL_DETECTIONS = Code("111063", "DCM", "Successful Detections")
DETECTION_PERFORMED = Code("111022", "DCM", "Detection Performed")
ALGORITHM_NAME = Code("111001", "DCM", "Algorithm Name")
ALGORITHM_VERSION = Code("111003", "DCM", "Algorithm Version")
IMPRESSION_DESCRIPTION = Code("111033", "DCM", "Impression Description")
RECOMMENDED_FOLLOW_UP_DATE = Code("111054", "DCM", "Recommended Follow-up Date")
IMAGE_LATERALITY = Code("111027", "DCM", "Image Laterality")
IMAGE_VIEW = Code("111031", "DCM", "Image View")
PATIENT_ORIENTATION_ROW = Code("111044", "DCM", "Patient Orientation Row")
PATIENT_ORIENTATION_COLUMN = Code("111043", "DCM", "Patient Orientation Column")
HORIZONTAL_PIXEL_SPACING = Code("111026", "DCM", "Horizontal Pixel Spacing")
VERTICAL_PIXEL_SPACING = Code("111066", "DCM", "Vertical Pixel Spacing")

# Coded values, each from the context group that its row names, or that is
# cited beside it.
ENGLISH = Code("en", "RFC5646", "English")  # CID 5000
DEVICE = Code("121007", "DCM", "Device")  # CID 270
FEMALE = Code("F", "DCM", "Female")  # CID 7455
IMAGING_PROCEDURE = Code("363679005", "SCT", "Imaging procedure")  # CID 100
MAGNETIC_RESONANCE = Code("MR", "DCM", "Magnetic Resonance")  # CID 33
# TID 1500 row 8 gives TID 1411 no $TargetSite, so the site is from CID
# 4031, which TID 1600 and TID 1602 name for an anatomic region, and its
# SNOMED ID is the one that CID 4031 gives beside it.
BREAST = Code("76752008", "SCT", "Breast")
BREAST_SRT = Code("T-04000", "SRT", "Breast")
LEFT = Code("7771000", "SCT", "Left")  # CID 244, by CID 247
LEFT_SRT = Code("G-A101", "SRT", "Left")  # CID 247's SNOMED ID
VOLUME = Code("118565006", "SCT", "Volume")  # CID 218, by CID 7469 and 7472
CUBIC_MILLIMETRE = Code("mm3", "UCUM", "cubic millimeter")  # CID 7181, by 7462
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
MILLIMETRE = Code("mm", "UCUM", "millimeter")  # TID 4020 rows 11 and 12


def item(relationship, value_type, concept, *children, **value):
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
        Its value, by Value Type: ``code`` (a :class:`Code`) for CODE;
        ``number`` and ``units`` for NUM; ``text`` for TEXT, PNAME, DATE,
        TIME, DATETIME, and UIDREF; ``sop_class`` and ``sop_instance`` for
        IMAGE and COMPOSITE; and ``graphic_type`` and ``points`` for SCOORD
        and SCOORD3D, with ``frame_of_reference`` for SCOORD3D.
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
        dataset.ConceptCodeSequence = pydicom.Sequence([value["code"].dataset()])
    elif value_type == "NUM":
        measured = pydicom.Dataset()
        measured.NumericValue = value["number"]
        measured.MeasurementUnitsCodeSequence = pydicom.Sequence(
            [value["units"].dataset()]
        )
        dataset.MeasuredValueSequence = pydicom.Sequence([measured])
    elif value_type in ("IMAGE", "COMPOSITE"):
        referenced = pydicom.Dataset()
        referenced.ReferencedSOPClassUID = value["sop_class"]
        referenced.ReferencedSOPInstanceUID = value["sop_instance"]
        dataset.ReferencedSOPSequence = pydicom.Sequence([referenced])
    elif value_type in ("SCOORD", "SCOORD3D"):
        dataset.GraphicType = value["graphic_type"]
        dataset.GraphicData = list(value["points"])
        if value_type == "SCOORD3D":
            dataset.ReferencedFrameOfReferenceUID = value["frame_of_reference"]
    else:
        keyword = {
            "TEXT": "TextValue",
            "PNAME": "PersonName",
            "DATE": "Date",
            "TIME": "Time",
            "DATETIME": "DateTime",
            "UIDREF": "UID",
        }[value_type]
        setattr(dataset, keyword, value["text"])
    if children:
        dataset.ContentSequence = pydicom.Sequence(list(children))
    return dataset


def by_reference(relationship, position):
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


def _row(key, *args, **value):
    """Return an optional row, keyed by its template and row, and its builder.

    The builder returns the content item that :func:`item` gives ``args``
    and ``value``.
    """
    return key, lambda: item(*args, **value)


def _chosen(optional, rows):
    """Return the items of ``rows``, keyed by template row, that ``optional`` names."""
    return [built() for key, built in rows if key in optional]


def _checked(optional, rows):
    """Raise ValueError if ``optional`` names a row that ``rows`` does not hold."""
    unknown = set(optional) - set(rows)
    if unknown:
        raise ValueError(f"not an optional row: {sorted(unknown)}")


def _language(relationship="HAS CONCEPT MOD"):
    """Return TID 1204 row 1, the language of the content, in English."""
    return item(relationship, "CODE", LANGUAGE, code=ENGLISH)


OBSERVATION = "HAS OBS CONTEXT"
ACQUISITION = "HAS ACQ CONTEXT"


def _person_observer(optional, prefix=""):
    """Return TID 1002 for a person observer, with TID 1003's rows.

    TID 1002 row 1 is absent, so the observer is a person, and row 2
    includes TID 1003, whose row 1 is required. ``prefix`` keeps the keys of
    the optional rows apart where a template includes TID 1002 itself.
    """
    return [
        item(OBSERVATION, "PNAME", PERSON_OBSERVER_NAME, text=OBSERVERS_NAME),
        *_chosen(
            optional,
            [
                _row(
                    f"{prefix}TID 1003 row 1a",
                    OBSERVATION,
                    "TEXT",
                    PERSON_OBSERVERS_LOGIN_NAME,
                    text=f"{SENTINEL}LOGIN",
                ),
                _row(
                    f"{prefix}TID 1003 row 2",
                    OBSERVATION,
                    "TEXT",
                    PERSON_OBSERVERS_ORGANIZATION_NAME,
                    text=f"{SENTINEL} HOSPITAL",
                ),
            ],
        ),
    ]


def _device_observer(optional):
    """Return TID 1002 for a second observer, a device, with TID 1004's rows.

    TID 1002 row 1 gives the Observer Type, required for a device, and row 3
    includes TID 1004, whose row 1 is required. TID 1004 row 10, a Unique
    Device Identifiers container, requires its row 11, coded in LOINC.
    """
    identifier = item(
        "CONTAINS", "TEXT", UNIQUE_DEVICE_IDENTIFIER, text=f"{SENTINEL}-UDI"
    )
    return [
        item(OBSERVATION, "CODE", OBSERVER_TYPE, code=DEVICE),
        item(
            OBSERVATION,
            "UIDREF",
            DEVICE_OBSERVER_UID_CONCEPT,
            text=DEVICE_OBSERVER_UID,
        ),
        *_chosen(
            optional,
            [
                _row(
                    "TID 1004 row 2",
                    OBSERVATION,
                    "TEXT",
                    DEVICE_OBSERVER_NAME,
                    text=f"{SENTINEL} STATION",
                ),
                _row(
                    "TID 1004 row 10",
                    OBSERVATION,
                    "CONTAINER",
                    UNIQUE_DEVICE_IDENTIFIERS,
                    identifier,
                ),
            ],
        ),
    ]


def subject_identifier(code_value=PATIENT_ID):
    """Return TID 1007 row 3, the Subject ID, with the Value Type CODE.

    PS3.16 2026d gives the row the Value Type CODE, while Table E.3.4-1
    lists Subject ID only as TEXT. The identifier is the Code Value, in a
    local coding scheme, whose designator begins with "99" (PS3.3 Section
    8.2).
    """
    return item(
        OBSERVATION,
        "CODE",
        SUBJECT_ID,
        code=Code(code_value, "99SYNTHETIC", f"{SENTINEL} PATIENT"),
    )


def _observation_context(optional):
    """Return TID 1001's items: an observer, and the procedure and subject.

    TID 1001 row 1 includes TID 1002 for a person, from
    :func:`_person_observer`, and, with ``"TID 1001 row 1 device"``, a
    second, a device. Row 2 includes TID 1005 and row 3 TID 1006, whose row
    2 includes TID 1007; each is required only where its context is not
    inherited, and is included only with one of its own rows.
    """
    items = _person_observer(optional)
    if "TID 1001 row 1 device" in optional:
        items += _device_observer(optional)
    age = Code("a", "UCUM", "year")  # CID 7456
    items += _chosen(
        optional,
        [
            _row(
                "TID 1005 row 1",
                OBSERVATION,
                "UIDREF",
                PROCEDURE_STUDY_INSTANCE_UID,
                text=STUDY,
            ),
            _row(
                "TID 1005 row 7",
                OBSERVATION,
                "TEXT",
                ACCESSION_NUMBER,
                text=f"{SENTINEL}-ACC",
            ),
            _row(
                "TID 1007 row 1",
                OBSERVATION,
                "UIDREF",
                SUBJECT_UID_CONCEPT,
                text=SUBJECT_UID,
            ),
            _row(
                "TID 1007 row 2", OBSERVATION, "PNAME", SUBJECT_NAME, text=PATIENTS_NAME
            ),
            ("TID 1007 row 3", subject_identifier),
            _row(
                "TID 1007 row 3 TEXT",
                OBSERVATION,
                "TEXT",
                SUBJECT_ID,
                text=PATIENT_ID,
            ),
            _row(
                "TID 1007 row 4",
                OBSERVATION,
                "DATE",
                SUBJECT_BIRTH_DATE,
                text=BIRTH_DATE,
            ),
            _row("TID 1007 row 5", OBSERVATION, "CODE", SUBJECT_SEX, code=FEMALE),
            _row(
                "TID 1007 row 6",
                OBSERVATION,
                "NUM",
                SUBJECT_AGE,
                number="56",
                units=age,
            ),
        ],
    )
    return items


# The optional rows of TID 1001 as TID 2000 and TID 1500 include it at the
# root. A device observer's rows, those of TID 1004, are included only with
# "TID 1001 row 1 device", and "TID 1007 row 3 TEXT" gives row 3 the Value
# Type TEXT, which Table E.3.4-1 lists, in place of CODE.
OBSERVATION_CONTEXT_ROWS = (
    "TID 1003 row 1a",
    "TID 1003 row 2",
    "TID 1001 row 1 device",
    "TID 1004 row 2",
    "TID 1004 row 10",
    "TID 1005 row 1",
    "TID 1005 row 7",
    "TID 1007 row 1",
    "TID 1007 row 2",
    "TID 1007 row 3",
    "TID 1007 row 3 TEXT",
    "TID 1007 row 4",
    "TID 1007 row 5",
    "TID 1007 row 6",
)
IMAGING_OPTIONAL_ROWS = (*OBSERVATION_CONTEXT_ROWS, "TID 2000 row 8")


def imaging_tree(optional=(), title=BREAST_IMAGING_REPORT):
    """Return the root of a diagnostic imaging report's tree, TID 2000.

    TID 2000 rows 1, 5, and 7 are required: the title, from CID 7000, the
    language (TID 1204 row 1), and the observation context (TID 1001), whose
    observer, a person, is named. ``"TID 2000 row 8"`` adds a section, whose
    heading is from CID 7001, every code of which is in LOINC, holding an
    impression in free text (TID 2002 row 3, with a concept from CID 7002).

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`IMAGING_OPTIONAL_ROWS`.
    title : Code
        The document title, from CID 7000. Defaults to its DCM code for a
        breast imaging report; most of its titles, such as
        :data:`DIAGNOSTIC_IMAGING_REPORT`, are coded in LOINC.
    """
    _checked(optional, IMAGING_OPTIONAL_ROWS)
    impression = item("CONTAINS", "TEXT", IMPRESSION, text=f"{SENTINEL} IMPRESSION")
    sections = _chosen(
        optional,
        [_row("TID 2000 row 8", "CONTAINS", "CONTAINER", IMPRESSIONS, impression)],
    )
    return item(
        None,
        "CONTAINER",
        title,
        _language(),
        *_observation_context(optional),
        *sections,
    )


# The optional rows of the measurement report: TID 1001's at the root, and
# those of TID 1500, 1411, 1419, and 1602, by template and row. The
# descriptors of TID 1602 are included only with "TID 1500 row 5", the
# image library that holds them. "TID 1419 row 2" adds a finding site, with
# its laterality from row 3.
MEASUREMENT_OPTIONAL_ROWS = (
    *OBSERVATION_CONTEXT_ROWS,
    "TID 1500 row 2",
    "TID 1500 row 4",
    "TID 1500 row 5",
    "TID 1602 row 1",
    "TID 1602 row 4",
    "TID 1602 row 5a",
    "TID 1602 row 5c",
    "TID 1602 row 6",
    "TID 1602 row 10",
    "TID 1411 row 1b",
    "TID 1411 row 2",
    "TID 1411 row 3",
    "TID 1411 row 4",
    "TID 1411 row 13",
    "TID 1419 row 2",
)
# Each optional row that another optional row holds, with the row that holds
# it.
HELD_BY = {
    "TID 1004 row 2": "TID 1001 row 1 device",
    "TID 1004 row 10": "TID 1001 row 1 device",
    "TID 1602 row 1": "TID 1500 row 5",
    "TID 1602 row 4": "TID 1500 row 5",
    "TID 1602 row 5a": "TID 1500 row 5",
    "TID 1602 row 5c": "TID 1500 row 5",
    "TID 1602 row 6": "TID 1500 row 5",
    "TID 1602 row 10": "TID 1500 row 5",
    "TID 2010 row 6 TID 1003 row 1a": "TID 2010 row 6",
    "TID 2010 row 6 TID 1003 row 2": "TID 2010 row 6",
}


def with_holders(key):
    """Return the optional row ``key`` with every optional row that holds it."""
    keys = [key]
    while keys[-1] in HELD_BY:
        keys.append(HELD_BY[keys[-1]])
    return tuple(keys)


def _image_library(optional):
    """Return TID 1500 row 5, TID 1600 "Image Library", with one MR image.

    The image is an entry of TID 1601 row 1, in an Image Library Group (TID
    1600 row 2), with the descriptors of TID 1602 that ``optional`` names.
    """
    descriptors = _chosen(
        optional,
        [
            _row(
                "TID 1602 row 1",
                ACQUISITION,
                "CODE",
                MODALITY,
                code=MAGNETIC_RESONANCE,
            ),
            _row(
                "TID 1602 row 4",
                ACQUISITION,
                "DATE",
                STUDY_DATE_CONCEPT,
                text=STUDY_DATE,
            ),
            _row(
                "TID 1602 row 5a",
                ACQUISITION,
                "UIDREF",
                SERIES_INSTANCE_UID,
                text=MR_SERIES,
            ),
            _row(
                "TID 1602 row 5c",
                ACQUISITION,
                "TEXT",
                SERIES_DESCRIPTION,
                text=f"{SENTINEL} SERIES",
            ),
            _row(
                "TID 1602 row 6",
                ACQUISITION,
                "DATE",
                CONTENT_DATE_CONCEPT,
                text=STUDY_DATE,
            ),
            _row(
                "TID 1602 row 10",
                ACQUISITION,
                "UIDREF",
                FRAME_OF_REFERENCE_UID,
                text=FRAME_OF_REFERENCE,
            ),
        ],
    )
    entry = item(
        "CONTAINS",
        "IMAGE",
        None,
        *descriptors,
        sop_class=MR_IMAGE_STORAGE,
        sop_instance=MR_IMAGE,
    )
    group = item("CONTAINS", "CONTAINER", IMAGE_LIBRARY_GROUP, entry)
    return item("CONTAINS", "CONTAINER", IMAGE_LIBRARY, group)


def _finding_site(snomed_ids):
    """Return TID 1419 row 2, a finding site, with its laterality from row 3.

    With ``snomed_ids``, the concept names and values are coded by their
    SNOMED IDs under the retired designator SRT, as PS3.16 Annex O and the
    context groups give them.
    """
    if snomed_ids:
        site, laterality, values = (
            FINDING_SITE_SRT,
            LATERALITY_SRT,
            (BREAST_SRT, LEFT_SRT),
        )
    else:
        site, laterality, values = FINDING_SITE, LATERALITY, (BREAST, LEFT)
    side = item("HAS CONCEPT MOD", "CODE", laterality, code=values[1])
    return item("HAS CONCEPT MOD", "CODE", site, side, code=values[0])


def _volumetric_group(optional, snomed_ids):
    """Return TID 1500 row 8, TID 1411 "Volumetric ROI Measurements".

    The region is a point given by a Volume Surface (row 10), so that the
    source series (row 12) is required too, and TID 1419 (row 15) gives its
    volume (row 5, M). ``"TID 1411 row 4"`` includes TID 1502, whose row 3,
    coded in UMLS, is required.
    """
    return item(
        "CONTAINS",
        "CONTAINER",
        MEASUREMENT_GROUP,
        *_chosen(
            optional,
            [
                _row(
                    "TID 1411 row 1b",
                    OBSERVATION,
                    "TEXT",
                    ACTIVITY_SESSION,
                    text=f"{SENTINEL} SESSION",
                ),
                _row(
                    "TID 1411 row 2",
                    OBSERVATION,
                    "TEXT",
                    TRACKING_IDENTIFIER,
                    text=f"{SENTINEL} LESION 1",
                ),
                _row(
                    "TID 1411 row 3",
                    OBSERVATION,
                    "UIDREF",
                    TRACKING_UNIQUE_IDENTIFIER,
                    text=TRACKING_UID,
                ),
                _row(
                    "TID 1411 row 4",
                    OBSERVATION,
                    "TEXT",
                    TIME_POINT,
                    text=f"{SENTINEL} BASELINE",
                ),
            ],
        ),
        item(
            "CONTAINS",
            "SCOORD3D",
            VOLUME_SURFACE,
            graphic_type="POINT",
            points=(12.5, -40.0, 63.25),
            frame_of_reference=FRAME_OF_REFERENCE,
        ),
        item("CONTAINS", "UIDREF", SOURCE_SERIES_FOR_SEGMENTATION, text=MR_SERIES),
        *_chosen(
            optional,
            [
                _row(
                    "TID 1411 row 13",
                    "CONTAINS",
                    "IMAGE",
                    ILLUSTRATION_OF_ROI,
                    sop_class=MR_IMAGE_STORAGE,
                    sop_instance=MR_IMAGE,
                ),
                ("TID 1419 row 2", lambda: _finding_site(snomed_ids)),
            ],
        ),
        item("CONTAINS", "NUM", VOLUME, number="1840", units=CUBIC_MILLIMETRE),
    )


def measurement_tree(optional=(), snomed_ids=False):
    """Return the root of a measurement report's tree, TID 1500.

    TID 1500 rows 1, 3, and 6 are required: the title, from CID 7021, the
    observation context (TID 1001), whose observer, a person, is named, and
    the Imaging Measurements, since neither row 10 nor row 12 is present.
    They hold one volumetric region (row 8, TID 1411).

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`MEASUREMENT_OPTIONAL_ROWS`.
    snomed_ids : bool
        Whether the finding site of ``"TID 1419 row 2"`` is coded by its
        retired SNOMED IDs.
    """
    _checked(optional, MEASUREMENT_OPTIONAL_ROWS)
    procedure = _row(
        "TID 1500 row 4",
        "HAS CONCEPT MOD",
        "CODE",
        PROCEDURE_REPORTED,
        code=IMAGING_PROCEDURE,
    )
    return item(
        None,
        "CONTAINER",
        IMAGING_MEASUREMENT_REPORT,
        *_chosen(optional, [("TID 1500 row 2", _language)]),
        *_observation_context(optional),
        *_chosen(
            optional,
            [procedure, ("TID 1500 row 5", lambda: _image_library(optional))],
        ),
        item(
            "CONTAINS",
            "CONTAINER",
            IMAGING_MEASUREMENTS,
            _volumetric_group(optional, snomed_ids),
        ),
    )


KEY_OBJECT_OPTIONAL_ROWS = (
    "TID 2010 row 5",
    "TID 2010 row 6",
    "TID 2010 row 6 TID 1003 row 1a",
    "TID 2010 row 6 TID 1003 row 2",
    "TID 2010 row 7",
)


def key_object_tree(optional=()):
    """Return the root of a key object selection's tree, TID 2010.

    TID 2010 row 1, the title, from CID 7010, is required, and so is one of
    rows 8 to 10, here row 8, an MR image. ``"TID 2010 row 6"`` adds an
    observer, a person, by TID 1002, whose TID 1003 has its own optional
    rows.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`KEY_OBJECT_OPTIONAL_ROWS`;
        TID 1003's are included only with ``"TID 2010 row 6"``.
    """
    _checked(optional, KEY_OBJECT_OPTIONAL_ROWS)
    observer = (
        _person_observer(optional, "TID 2010 row 6 ")
        if "TID 2010 row 6" in optional
        else []
    )
    description = _row(
        "TID 2010 row 7",
        "CONTAINS",
        "TEXT",
        KEY_OBJECT_DESCRIPTION,
        text=f"{SENTINEL} WHY THIS IMAGE",
    )
    return item(
        None,
        "CONTAINER",
        OF_INTEREST,
        *_chosen(optional, [("TID 2010 row 5", _language)]),
        *observer,
        *_chosen(optional, [description]),
        item(
            "CONTAINS",
            "IMAGE",
            None,
            sop_class=MR_IMAGE_STORAGE,
            sop_instance=MR_IMAGE,
        ),
    )


CAD_OPTIONAL_ROWS = (
    "TID 4020 row 9",
    "TID 4020 row 10",
    "TID 4020 row 17",
    "TID 4002 row 5",
    "TID 4002 row 9",
)
# The place of the CAD report's image library entry along its tree: the
# first item of the root's second.
CAD_ENTRY = (1, 2, 1)


def _algorithm(relationship):
    """Return TID 4019 rows 1 and 2, the algorithm's name and version, both M."""
    return [
        item(relationship, "TEXT", ALGORITHM_NAME, text="FIXTURE DETECTOR"),
        item(relationship, "TEXT", ALGORITHM_VERSION, text="1.0"),
    ]


def _cad_image_entry(optional):
    """Return TID 4000 row 4, TID 4020 "CAD Image Library Entry", for an MG image.

    The image is a left cranio-caudal mammogram, which has an Image
    Laterality, a View Code Sequence, a Patient Orientation, a Study Date
    and Time, and an Imager Pixel Spacing, so that TID 4020 rows 2, 3, 5 to
    8, 11, and 12 are required. Its Content Date and Time (rows 9 and 10)
    and Frame of Reference UID (row 17) are optional here.
    """
    spacing = {"number": "0.1", "units": MILLIMETRE}
    return item(
        "CONTAINS",
        "IMAGE",
        None,
        item(ACQUISITION, "CODE", IMAGE_LATERALITY, code=LEFT_BREAST),
        item(ACQUISITION, "CODE", IMAGE_VIEW, code=CRANIO_CAUDAL),
        item(ACQUISITION, "TEXT", PATIENT_ORIENTATION_ROW, text="A"),
        item(ACQUISITION, "TEXT", PATIENT_ORIENTATION_COLUMN, text="R"),
        item(ACQUISITION, "DATE", STUDY_DATE_CONCEPT, text=STUDY_DATE),
        item(ACQUISITION, "TIME", STUDY_TIME_CONCEPT, text=STUDY_TIME),
        *_chosen(
            optional,
            [
                _row(
                    "TID 4020 row 9",
                    ACQUISITION,
                    "DATE",
                    CONTENT_DATE_CONCEPT,
                    text=STUDY_DATE,
                ),
                _row(
                    "TID 4020 row 10",
                    ACQUISITION,
                    "TIME",
                    CONTENT_TIME_CONCEPT,
                    text=STUDY_TIME,
                ),
            ],
        ),
        item(ACQUISITION, "NUM", HORIZONTAL_PIXEL_SPACING, **spacing),
        item(ACQUISITION, "NUM", VERTICAL_PIXEL_SPACING, **spacing),
        *_chosen(
            optional,
            [
                _row(
                    "TID 4020 row 17",
                    ACQUISITION,
                    "UIDREF",
                    FRAME_OF_REFERENCE_UID,
                    text=FRAME_OF_REFERENCE,
                ),
            ],
        ),
        sop_class=MAMMOGRAPHY_FOR_PRESENTATION,
        sop_instance=MG_IMAGE,
    )


def _impression(optional):
    """Return TID 4001 row 2, TID 4002, where ``optional`` names one of its rows.

    TID 4002 requires one of its rows 1, 3, 5, 6, 8, and 9, and the
    algorithm (row 11, TID 4019).
    """
    rows = _chosen(
        optional,
        [
            _row(
                "TID 4002 row 5",
                "HAS PROPERTIES",
                "TEXT",
                IMPRESSION_DESCRIPTION,
                text=f"{SENTINEL} CAD IMPRESSION",
            ),
            _row(
                "TID 4002 row 9",
                "HAS PROPERTIES",
                "DATE",
                RECOMMENDED_FOLLOW_UP_DATE,
                text=FOLLOW_UP_DATE,
            ),
        ],
    )
    return [*rows, *_algorithm("HAS PROPERTIES")] if rows else []


def cad_tree(optional=()):
    """Return the root of a mammography CAD report's tree, TID 4000.

    The CAD found nothing in one image: TID 4000 rows 1 to 6 and 8 are
    required, with the language (TID 1204 row 1), the image library's entry
    (TID 4020), the summary (TID 4001 row 1, from CID 6047), and the
    detections, which succeeded, so that row 7 includes TID 4015, whose one
    detection performed (TID 4017) names its algorithm (TID 4019) and refers
    by reference to the entry (row 4, R-HAS PROPERTIES). No analysis was
    attempted (row 8), so row 9 is absent.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`CAD_OPTIONAL_ROWS`.
    """
    _checked(optional, CAD_OPTIONAL_ROWS)
    detection = item(
        "CONTAINS",
        "CODE",
        DETECTION_PERFORMED,
        *_algorithm("HAS PROPERTIES"),
        by_reference("HAS PROPERTIES", CAD_ENTRY),
        code=CALCIFICATION_CLUSTER,
    )
    detections = item("INFERRED FROM", "CONTAINER", SUCCESSFUL_DETECTIONS, detection)
    return item(
        None,
        "CONTAINER",
        MAMMOGRAPHY_CAD_REPORT,
        _language(),
        item("CONTAINS", "CONTAINER", IMAGE_LIBRARY, _cad_image_entry(optional)),
        item(
            "CONTAINS",
            "CODE",
            CAD_PROCESSING_AND_FINDINGS_SUMMARY,
            *_impression(optional),
            code=ALL_SUCCEEDED_WITHOUT_FINDINGS,
        ),
        item("CONTAINS", "CODE", SUMMARY_OF_DETECTIONS, detections, code=SUCCEEDED),
        item("CONTAINS", "CODE", SUMMARY_OF_ANALYSES, code=NOT_ATTEMPTED),
    )


def _evidence(series, sop_class, sop_instance):
    """Return a Current Requested Procedure Evidence Sequence for one image."""
    referenced = pydicom.Dataset()
    referenced.ReferencedSOPClassUID = sop_class
    referenced.ReferencedSOPInstanceUID = sop_instance
    in_series = pydicom.Dataset()
    in_series.SeriesInstanceUID = series
    in_series.ReferencedSOPSequence = pydicom.Sequence([referenced])
    in_study = pydicom.Dataset()
    in_study.StudyInstanceUID = STUDY
    in_study.ReferencedSeriesSequence = pydicom.Sequence([in_series])
    return pydicom.Sequence([in_study])


def _header(sop_class, instance, modality):
    """Return the header of a report, without its document module's flags.

    ``instance`` gives its Series and SOP Instance UIDs. The header holds
    the Patient, General Study, SR Document Series or Key Object Document
    Series, and General Equipment Modules' required attributes, the SOP
    Common Module's, and the instance number and content date and time,
    with identifying values of their own.
    """
    series, sop_instance = instance
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = sop_instance
    dataset.PatientName = PATIENTS_NAME
    dataset.PatientID = PATIENT_ID
    dataset.PatientBirthDate = BIRTH_DATE
    dataset.PatientSex = "F"
    dataset.StudyInstanceUID = STUDY
    dataset.StudyDate = STUDY_DATE
    dataset.StudyTime = STUDY_TIME
    dataset.ReferringPhysicianName = REFERRERS_NAME
    dataset.StudyID = ""
    dataset.AccessionNumber = f"{SENTINEL}-ACC"
    dataset.Modality = modality
    dataset.SeriesInstanceUID = series
    dataset.SeriesNumber = 1
    dataset.ReferencedPerformedProcedureStepSequence = pydicom.Sequence()
    dataset.Manufacturer = "FIXTURE MAKER"
    dataset.InstitutionName = f"{SENTINEL} HOSPITAL"
    dataset.StationName = f"{SENTINEL}-ST"
    dataset.ManufacturerModelName = "FIXTURE MODEL"
    dataset.DeviceSerialNumber = f"{SENTINEL}-SN"
    dataset.SoftwareVersions = "1.0"
    dataset.InstanceNumber = 1
    dataset.ContentDate = CONTENT_DATE
    dataset.ContentTime = CONTENT_TIME
    return dataset


def _with_tree(dataset, tree, template):
    """Add the root content item ``tree`` and its template to ``dataset``."""
    for element in tree:
        dataset.add(element)
    template_item = pydicom.Dataset()
    template_item.MappingResource = "DCMR"
    template_item.TemplateIdentifier = template
    dataset.ContentTemplateSequence = pydicom.Sequence([template_item])
    return dataset


def _report(identity, tree, verified, evidence=None):
    """Return a Structured Report whose SR Document Content Module holds ``tree``.

    ``identity`` gives its SOP Class, its Series and SOP Instance UIDs, and
    its root template. Its SR Document General Module has the Verification
    Flag VERIFIED, with a Verifying Observer Sequence, where ``verified``,
    and UNVERIFIED otherwise, and a Current Requested Procedure Evidence
    Sequence where ``evidence`` gives one.
    """
    sop_class, instance, template = identity
    dataset = _header(sop_class, instance, "SR")
    dataset.CompletionFlag = "COMPLETE"
    dataset.VerificationFlag = "VERIFIED" if verified else "UNVERIFIED"
    if verified:
        # PS3.3 Table C.17-2: Type 1C, required where VERIFIED.
        observer = pydicom.Dataset()
        observer.VerifyingObserverName = VERIFIERS_NAME
        observer.VerifyingObserverIdentificationCodeSequence = pydicom.Sequence()
        observer.VerifyingOrganization = f"{SENTINEL} HOSPITAL"
        observer.VerificationDateTime = VERIFICATION_DATETIME
        dataset.VerifyingObserverSequence = pydicom.Sequence([observer])
    if evidence is not None:
        dataset.CurrentRequestedProcedureEvidenceSequence = evidence
    dataset.PerformedProcedureCodeSequence = pydicom.Sequence()
    return _with_tree(dataset, tree, template)


def imaging_report(optional=(), *, title=BREAST_IMAGING_REPORT, verified=False):
    """Return a Comprehensive SR whose tree is :func:`imaging_tree`.

    ``verified`` gives it the Verification Flag VERIFIED, with a Verifying
    Observer Sequence, rather than UNVERIFIED.
    """
    return _report(
        (COMPREHENSIVE_SR, IMAGING_REPORT, "2000"),
        imaging_tree(optional, title),
        verified,
    )


def measurement_report(optional=(), *, snomed_ids=False, verified=False):
    """Return a Comprehensive 3D SR whose tree is :func:`measurement_tree`.

    ``verified`` is as for :func:`imaging_report`. The report's evidence is
    the MR image that its tree references.
    """
    return _report(
        (COMPREHENSIVE_3D_SR, MEASUREMENT_REPORT, "1500"),
        measurement_tree(optional, snomed_ids),
        verified,
        _evidence(MR_SERIES, MR_IMAGE_STORAGE, MR_IMAGE),
    )


def key_object_selection(optional=()):
    """Return a Key Object Selection Document whose tree is :func:`key_object_tree`.

    Its Key Object Document Module has no Verification Flag (PS3.3 Table
    C.17.6-2), so it is neither VERIFIED nor UNVERIFIED. Its evidence, which
    the module requires, is the MR image that it selects.
    """
    dataset = _header(KEY_OBJECT_SELECTION_DOCUMENT, KEY_OBJECTS, "KO")
    dataset.CurrentRequestedProcedureEvidenceSequence = _evidence(
        MR_SERIES, MR_IMAGE_STORAGE, MR_IMAGE
    )
    return _with_tree(dataset, key_object_tree(optional), "2010")


def mammography_cad_report(optional=(), *, verified=False):
    """Return a Mammography CAD SR whose tree is :func:`cad_tree`.

    ``verified`` is as for :func:`imaging_report`. The report's evidence is
    the mammogram that its tree references.
    """
    return _report(
        (MAMMOGRAPHY_CAD_SR, CAD_REPORT, "4000"),
        cad_tree(optional),
        verified,
        _evidence(MG_SERIES, MAMMOGRAPHY_FOR_PRESENTATION, MG_IMAGE),
    )
