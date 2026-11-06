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

"""Synthetic Structured Reports of six IODs that each name their root template.

PS3.3 2026d Section A.35 has each of these IODs constructed from one
template of PS3.16 2026d invoked at the root node, and six builders give
one report each:

- :func:`chest_cad_report`, a Chest CAD SR, TID 4100 "Chest CAD Report"
  (A.35.6);
- :func:`colon_cad_report`, a Colon CAD SR, TID 4120 "Colon CAD Report"
  (A.35.10);
- :func:`procedure_log`, a Procedure Log, TID 3001 "Procedure Log", from
  which A.35.7 says the document may be constructed;
- :func:`spectacle_prescription`, a Spectacle Prescription Report, TID 2020
  "Spectacle Prescription Report" (A.35.9);
- :func:`macular_grid_report`, a Macular Grid Thickness and Volume Report,
  TID 2100 "Macular Grid Thickness and Volume Report" (A.35.11); and
- :func:`waveform_annotations`, a Waveform Annotation SR, TID 3750
  "Waveform Annotations" (A.35.23).

As in :mod:`._synthetic_structured_reports`, whose content item builders
these reuse, each content item's relationship, Value Type, and concept name
is a row of a template of PS3.16 2026d, cited beside it, and each coded
value is one of the context group that the row names. Code meanings are
those of PS3.16 Annex D for DCM codes, and those the templates and context
groups give for the others.

Each report holds every row that its templates require where they are
included, and the optional rows that carry identifying values, free text,
or coded concepts that Clean Structured Content cannot look up, keyed by
their template and row, such as ``"TID 3001 row 4"``. The header carries
identifying values too, as the other synthetic reports' do.

Text that must never reach a written file under the Basic Profile carries
``SENTINEL``, except the names of people, whose words occur in no code
meaning, since the residual search looks for each word of a name. Every UID
is invented under ``2.25.``, the patient is fictitious, and no value comes
from a real report.
"""

# The six reports share their codes, header, and observation context, so
# they stay in one module.
# pylint: disable = too-many-lines

from pymedphys._imports import pydicom

from . import _synthetic_structured_reports as reports

Code = reports.Code
item = reports.item
SENTINEL = reports.SENTINEL

# The SOP Classes of PS3.4 2026d Table B.5-1, and the IODs they name.
CHEST_CAD_SR = "1.2.840.10008.5.1.4.1.1.88.65"
COLON_CAD_SR = "1.2.840.10008.5.1.4.1.1.88.69"
PROCEDURE_LOG = "1.2.840.10008.5.1.4.1.1.88.40"
SPECTACLE_PRESCRIPTION_REPORT = "1.2.840.10008.5.1.4.1.1.78.6"
MACULAR_GRID_REPORT = "1.2.840.10008.5.1.4.1.1.79.1"
WAVEFORM_ANNOTATION_SR = "1.2.840.10008.5.1.4.1.1.88.77"
CHEST_CAD_SR_IOD = "Chest CAD SR"
COLON_CAD_SR_IOD = "Colon CAD SR"
PROCEDURE_LOG_IOD = "Procedure Log"
SPECTACLE_PRESCRIPTION_IOD = "Spectacle Prescription Report"
MACULAR_GRID_IOD = "Macular Grid Thickness and Volume Report"
WAVEFORM_ANNOTATION_IOD = "Waveform Annotation SR"
# The instances that the reports reference.
DX_FOR_PRESENTATION = "1.2.840.10008.5.1.4.1.1.1.1"
CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
ROUTINE_SCALP_EEG = "1.2.840.10008.5.1.4.1.1.9.7.1"

PATIENT_ID = "SYNTHETIC-7Q4K"
# Person names whose words occur in no code meaning, so that the residual
# search, which looks for each word of a name, finds them only where they
# are kept.
PATIENTS_NAME = "TAVISHER^MOLWENNA"
OBSERVERS_NAME = "KESTERFIELD^ORLAITH"
REFERRERS_NAME = "DUNMORROW^PELLICENT"
VERIFIERS_NAME = "ASHGROVE^FENWYRA"
STAFF_NAME = "HOLLERBY^JUSTANE"
PRIOR_OBSERVERS_NAME = "MERRIWICK^SOLVANE"
ANNOTATORS_NAME = "BRISENDALE^TORVIKA"
NAMES = (
    PATIENTS_NAME,
    OBSERVERS_NAME,
    REFERRERS_NAME,
    VERIFIERS_NAME,
    STAFF_NAME,
    PRIOR_OBSERVERS_NAME,
    ANNOTATORS_NAME,
)
STUDY = "2.25.9100"
DX_SERIES = "2.25.9200"
DX_IMAGE = "2.25.9201"
CT_SERIES = "2.25.9300"
CT_IMAGE = "2.25.9301"
EEG_SERIES = "2.25.9400"
EEG_WAVEFORM = "2.25.9401"
FRAME_OF_REFERENCE = "2.25.9500"
SYNCHRONIZATION_FRAME = "2.25.9501"
CHEST_CAD = ("2.25.9600", "2.25.9601")
COLON_CAD = ("2.25.9610", "2.25.9611")
LOG = ("2.25.9620", "2.25.9621")
SPECTACLES = ("2.25.9630", "2.25.9631")
MACULAR_GRID = ("2.25.9640", "2.25.9641")
WAVEFORM_ANNOTATIONS = ("2.25.9650", "2.25.9651")
# A Chest CAD SR of an earlier study, from which a finding is duplicated.
PRIOR_STUDY = "2.25.9700"
PRIOR_CHEST_CAD = ("2.25.9701", "2.25.9702")
# The UIDs that content items carry, other than the references above.
TRACKING_UID = "2.25.9801"
UIDS = (
    STUDY,
    DX_SERIES,
    DX_IMAGE,
    CT_SERIES,
    CT_IMAGE,
    EEG_SERIES,
    EEG_WAVEFORM,
    FRAME_OF_REFERENCE,
    SYNCHRONIZATION_FRAME,
    *CHEST_CAD,
    *COLON_CAD,
    *LOG,
    *SPECTACLES,
    *MACULAR_GRID,
    *WAVEFORM_ANNOTATIONS,
    PRIOR_STUDY,
    *PRIOR_CHEST_CAD,
    TRACKING_UID,
)
# The dates and times that the reports carry, none of which a modified or
# dummy value repeats.
STUDY_DATE = "20260517"
STUDY_TIME = "093000"
CONTENT_DATE = "20260518"
CONTENT_TIME = "151500"
BIRTH_DATE = "19640823"
LOG_DATETIME = "20260517094512"
# The times at which the log's events occurred, in the order of its first
# level items, each before the note's recording (LOG_DATETIME).
EVENT_DATETIMES = (
    "20260517093105",
    "20260517093340",
    "20260517093716",
    "20260517094058",
    "20260517094231",
)
ANNOTATED_DATETIME = "20260517101203.250000"
VERIFICATION_DATETIME = "20260519080000"
DATES = (
    STUDY_DATE,
    CONTENT_DATE,
    BIRTH_DATE,
    LOG_DATETIME,
    *EVENT_DATETIMES,
    ANNOTATED_DATETIME[:14],
    VERIFICATION_DATETIME,
)

# Document titles, the roots' concept names, and their containers.
CHEST_CAD_REPORT = Code("112000", "DCM", "Chest CAD Report")
COLON_CAD_REPORT = Code("112220", "DCM", "Colon CAD Report")
CATH_LAB_PROCEDURE_LOG = Code("121120", "DCM", "Cath Lab Procedure Log")  # CID 3400
SPECTACLE_PRESCRIPTION = Code("111671", "DCM", "Spectacle Prescription Report")
MACULAR_GRID_TITLE = Code("111690", "DCM", "Macular Grid Thickness and Volume Report")
NEUROPHYSIOLOGY_RECORDING_ANNOTATIONS = Code(
    "130867", "DCM", "Neurophysiology Recording Annotations"
)  # CID 3048
# TID 4100, 4101, 4015, 4016, 4017, 4019, 4020, 4022, 4104, 4107, 4108, 4120,
# 4121, and 4122.
IMAGE_LIBRARY = reports.IMAGE_LIBRARY
CAD_PROCESSING_AND_FINDINGS_SUMMARY = reports.CAD_PROCESSING_AND_FINDINGS_SUMMARY
SUMMARY_OF_DETECTIONS = reports.SUMMARY_OF_DETECTIONS
SUMMARY_OF_ANALYSES = reports.SUMMARY_OF_ANALYSES
SUCCESSFUL_DETECTIONS = reports.SUCCESSFUL_DETECTIONS
DETECTION_PERFORMED = reports.DETECTION_PERFORMED
ALGORITHM_NAME = reports.ALGORITHM_NAME
ALGORITHM_VERSION = reports.ALGORITHM_VERSION
ALGORITHM_MANUFACTURER = Code("122405", "DCM", "Algorithm Manufacturer")
ALGORITHM_PARAMETERS = Code("111002", "DCM", "Algorithm Parameters")
SERIES_INSTANCE_UID = reports.SERIES_INSTANCE_UID
SINGLE_IMAGE_FINDING = Code("111059", "DCM", "Single Image Finding")
ANATOMIC_IDENTIFIER = Code("112050", "DCM", "Anatomic Identifier")
RENDERING_INTENT = Code("111056", "DCM", "Rendering Intent")
CENTER = Code("111010", "DCM", "Center")
TRACKING_IDENTIFIER = reports.TRACKING_IDENTIFIER
TRACKING_UNIQUE_IDENTIFIER = reports.TRACKING_UNIQUE_IDENTIFIER
ORIGINAL_SOURCE = Code("111040", "DCM", "Original Source")
PATIENT_ORIENTATION_ROW = reports.PATIENT_ORIENTATION_ROW
PATIENT_ORIENTATION_COLUMN = reports.PATIENT_ORIENTATION_COLUMN
STUDY_DATE_CONCEPT = reports.STUDY_DATE_CONCEPT
STUDY_TIME_CONCEPT = reports.STUDY_TIME_CONCEPT
HORIZONTAL_PIXEL_SPACING = reports.HORIZONTAL_PIXEL_SPACING
VERTICAL_PIXEL_SPACING = reports.VERTICAL_PIXEL_SPACING
FRAME_OF_REFERENCE_UID = reports.FRAME_OF_REFERENCE_UID
IMAGE_SET_PROPERTIES = Code("112224", "DCM", "Image Set Properties")
STUDY_INSTANCE_UID = Code("110180", "DCM", "Study Instance UID")
MODALITY = reports.MODALITY
SLICE_THICKNESS = Code("112225", "DCM", "Slice Thickness")
SPACING_BETWEEN_SLICES = Code("112226", "DCM", "Spacing between slices")
RECUMBENT_PATIENT_POSITION = Code(
    "112228", "DCM", "Recumbent Patient Position with respect to gravity"
)
# TID 3001, 3601, and 3010.
PROCEDURE_DESCRIPTION = Code("121065", "DCM", "Procedure Description")
ROOM_IDENTIFICATION = Code("121121", "DCM", "Room identification")
EQUIPMENT_IDENTIFICATION = Code("121122", "DCM", "Equipment identification")
TECH_NOTE = Code("121171", "DCM", "Tech Note")  # CID 3401
PHYSICIAN_NOTE = Code("121173", "DCM", "Physician Note")  # CID 3401
PERSONNEL_ARRIVED = Code("122041", "DCM", "Personnel Arrived")  # CID 3404
EQUIPMENT_BROUGHT = Code(
    "122047", "DCM", "Equipment brought to procedure room"
)  # CID 3427
COMPLICATION_OF_PROCEDURE = Code("116224001", "SCT", "Complication of Procedure")
COMMENT = Code("121106", "DCM", "Comment")
PROCEDURE_ACTION_ID = Code("121124", "DCM", "Procedure Action ID")
LESION_IDENTIFIER = Code("121151", "DCM", "Lesion Identifier")
DATETIME_OF_RECORDING = Code("121125", "DCM", "DateTime of Recording of Log Entry")
# TID 2020 and 2021.
RIGHT_EYE_RX = Code("111688", "DCM", "Right Eye Rx")
LEFT_EYE_RX = Code("111689", "DCM", "Left Eye Rx")
SPHERE = Code("251795007", "SCT", "Sphere")
DISTANCE_PUPILLARY_DISTANCE = Code("111679", "DCM", "Distance Pupillary Distance")
# TID 2101 and 2102. Rows 1 and 4 to 14 of TID 2101 are coded in LOINC.
FINDINGS = Code("59776-5", "LN", "Findings")
FINDING_SITE = reports.FINDING_SITE
LATERALITY = reports.LATERALITY
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
# TID 3750, 3751, 3752, 3753, and 321.
WAVEFORM_ANNOTATIONS_CONTAINER = Code("130870", "DCM", "Waveform Annotations")
WAVEFORM_ANNOTATION_GROUP = Code("130872", "DCM", "Waveform Annotation Group")
GROUP_NUMBER = Code("130873", "DCM", "Waveform Annotation Group Number")
GROUP_LABEL = Code("130874", "DCM", "Waveform Annotation Group Label")
PATTERN_EVENT = Code("130860", "DCM", "Pattern Event")
SHORT_LABEL = Code("125309", "DCM", "Short Label")
ANNOTATION_NOTE = Code("130876", "DCM", "Annotation Note")
SOURCE = Code("260753009", "SCT", "Source")
SOURCE_OF_MEASUREMENT = Code("121112", "DCM", "Source of Measurement")

# Coded values, each from the context group that its row names, or that is
# cited beside it.
ALL_SUCCEEDED_WITHOUT_FINDINGS = reports.ALL_SUCCEEDED_WITHOUT_FINDINGS  # CID 6047
ALL_SUCCEEDED_WITH_FINDINGS = Code(
    "111242", "DCM", "All algorithms succeeded; with findings"
)  # CID 6047
SUCCEEDED = reports.SUCCEEDED  # CID 6042
NOT_ATTEMPTED = reports.NOT_ATTEMPTED  # CID 6042
ABNORMAL_OPACITY = Code("112033", "DCM", "Abnormal opacity")  # CID 6101
PRESENTATION_REQUIRED = Code(
    "111150", "DCM", "Presentation Required: Rendering device is expected to present"
)  # CID 6034
POLYP_OF_COLON = Code("68496003", "SCT", "Polyp of colon")  # CID 6201
COMPUTED_TOMOGRAPHY = Code("CT", "DCM", "Computed Tomography")  # CID 29
SUPINE = Code("40199007", "SCT", "Supine")  # CID 6206
DEATH_DURING_CATHETERIZATION = Code(
    "122167", "DCM", "Death During Catheterization"
)  # CID 3413
EYE = Code("81745001", "SCT", "Eye")  # TID 2101 row 2
RIGHT = Code("24028007", "SCT", "Right")  # TID 2100 row 4
APNEA = Code("3:3072", "MDC", "Apnea")  # CID 3038
CIRCUM_HEAD = Code("2:22784", "MDC", "Circum head")  # CID 3040
# Units, each the one that its row gives.
MILLIMETRE = reports.MILLIMETRE
MILLIMETRES_PER_PIXEL = Code("mm/{pixel}", "UCUM", "millimeters per pixel")
DIOPTRES = Code("[diop]", "UCUM", "diopters")
MILLIMETRE_PD = Code("mm", "UCUM", "mm")  # TID 2020 row 6
MICROMETRE = Code("um", "UCUM", "micrometer")
CUBIC_MILLIMETRE = Code("mm3", "UCUM", "mm3")
IMAGES = Code("{images}", "UCUM", "images")
SAMPLES = Code("{samples}", "UCUM", "samples")
RANGE_0_100 = Code("{0:100}", "UCUM", "range:0:100")
NO_UNITS = Code("1", "UCUM", "no units")
CENTIMETRE = Code("cm", "UCUM", "centimeter")  # UCUM, for a head circumference

OBSERVATION = reports.OBSERVATION
ACQUISITION = reports.ACQUISITION


def _row(key, *args, **value):
    """Return an optional row, keyed by its template and row, and its builder."""
    return key, lambda: item(*args, **value)


def _chosen(optional, rows):
    """Return the items of ``rows``, keyed by template row, that ``optional`` names."""
    return [built() for key, built in rows if key in optional]


def _checked(optional, rows):
    """Raise ValueError if ``optional`` names a row that ``rows`` does not hold."""
    unknown = set(optional) - set(rows)
    if unknown:
        raise ValueError(f"not an optional row: {sorted(unknown)}")


def _reference(relationship, value_type, concept, sop_class, sop_instance, **extra):
    """Return a WAVEFORM item, which :func:`~._synthetic_structured_reports.item` cannot build.

    Its Referenced SOP Sequence holds one item, with ``extra``'s attributes,
    such as Referenced Waveform Channels (0040,A0B0).
    """
    dataset = pydicom.Dataset()
    dataset.RelationshipType = relationship
    dataset.ValueType = value_type
    if concept is not None:
        dataset.ConceptNameCodeSequence = pydicom.Sequence([concept.dataset()])
    referenced = pydicom.Dataset()
    referenced.ReferencedSOPClassUID = sop_class
    referenced.ReferencedSOPInstanceUID = sop_instance
    for keyword, value in extra.items():
        setattr(referenced, keyword, value)
    dataset.ReferencedSOPSequence = pydicom.Sequence([referenced])
    return dataset


def _waveform(relationship, concept):
    """Return a WAVEFORM item that selects the first channel of the EEG."""
    return _reference(
        relationship,
        "WAVEFORM",
        concept,
        ROUTINE_SCALP_EEG,
        EEG_WAVEFORM,
        ReferencedWaveformChannels=[1, 1],
    )


def _temporal(concept, *children, at_datetime=False):
    """Return a TCOORD item, which :func:`~._synthetic_structured_reports.item` cannot build.

    The coordinates are a segment of sample positions (PS3.3 Table C.18.7-1),
    or, with ``at_datetime``, a point given by its Referenced DateTime
    (0040,A13A), which Table E.1-1 lists.
    """
    dataset = pydicom.Dataset()
    dataset.RelationshipType = "INFERRED FROM"
    dataset.ValueType = "TCOORD"
    dataset.ConceptNameCodeSequence = pydicom.Sequence([concept.dataset()])
    if at_datetime:
        dataset.TemporalRangeType = "POINT"
        dataset.ReferencedDateTime = ANNOTATED_DATETIME
    else:
        dataset.TemporalRangeType = "SEGMENT"
        dataset.ReferencedSamplePositions = [1200, 3600]
    dataset.ContentSequence = pydicom.Sequence(list(children))
    return dataset


def _language():
    """Return TID 1204 row 1, the language of the content, in English."""
    return item("HAS CONCEPT MOD", "CODE", reports.LANGUAGE, code=reports.ENGLISH)


def _person_observer(name, optional=(), prefix=""):
    """Return TID 1002 for a person observer, with TID 1003's optional rows.

    ``prefix`` keeps the keys of the optional rows apart where a report
    includes TID 1002 in more than one place.
    """
    return [
        item(OBSERVATION, "PNAME", reports.PERSON_OBSERVER_NAME, text=name),
        *_chosen(
            optional,
            [
                _row(
                    f"{prefix}TID 1003 row 1a",
                    OBSERVATION,
                    "TEXT",
                    reports.PERSON_OBSERVERS_LOGIN_NAME,
                    text=f"{SENTINEL}LOGIN",
                ),
                _row(
                    f"{prefix}TID 1003 row 2",
                    OBSERVATION,
                    "TEXT",
                    reports.PERSON_OBSERVERS_ORGANIZATION_NAME,
                    text=f"{SENTINEL} HOSPITAL",
                ),
            ],
        ),
    ]


def _algorithm(relationship, optional=(), prefix=""):
    """Return TID 4019 rows 1 and 2, and ``optional``'s rows 2b and 3.

    Row 3, the algorithm's parameters, is free text that the table does not
    list.
    """
    return [
        item(relationship, "TEXT", ALGORITHM_NAME, text="FIXTURE DETECTOR"),
        item(relationship, "TEXT", ALGORITHM_VERSION, text="2.1"),
        *_chosen(
            optional,
            [
                _row(
                    f"{prefix}TID 4019 row 3",
                    relationship,
                    "TEXT",
                    ALGORITHM_PARAMETERS,
                    text=f"{SENTINEL} PARAMETERS",
                ),
            ],
        ),
    ]


# Each optional row that another optional row holds, with the row that holds
# it.
HELD_BY = {
    "TID 4020 row 17": "TID 4100 row 3",
    "TID 4104 row 3": "TID 4101 row 3",
    "TID 4108 row 1": "TID 4101 row 3",
    "TID 4108 row 2": "TID 4101 row 3",
    "TID 4104 row 10": "TID 4101 row 3",
    "TID 3010 row 2": "TID 3001 row 6",
    "TID 3010 row 3": "TID 3001 row 6",
    "TID 3010 row 4": "TID 3001 row 6",
    "TID 3010 row 5": "TID 3001 row 6",
    "TID 321 row 3 datetime": "TID 3750 row 12",
    "TID 3751 row 3": "TID 3750 row 12",
    "TID 3751 row 6": "TID 3750 row 12",
}


def with_holders(key):
    """Return the optional row ``key`` with every optional row that holds it."""
    keys = [key]
    while keys[-1] in HELD_BY:
        keys.append(HELD_BY[keys[-1]])
    return tuple(keys)


def _evidence(series, sop_class, sop_instance, study=STUDY):
    """Return an evidence sequence that references one instance."""
    referenced = pydicom.Dataset()
    referenced.ReferencedSOPClassUID = sop_class
    referenced.ReferencedSOPInstanceUID = sop_instance
    in_series = pydicom.Dataset()
    in_series.SeriesInstanceUID = series
    in_series.ReferencedSOPSequence = pydicom.Sequence([referenced])
    in_study = pydicom.Dataset()
    in_study.StudyInstanceUID = study
    in_study.ReferencedSeriesSequence = pydicom.Sequence([in_series])
    return pydicom.Sequence([in_study])


CHEST_CAD_OPTIONAL_ROWS = (
    "TID 4100 row 3",
    "TID 4020 row 17",
    "TID 4017 row 5",
    "TID 4019 row 3",
    "TID 4101 row 3",
    "TID 4104 row 3",
    "TID 4108 row 1",
    "TID 4108 row 2",
    "TID 4104 row 10",
)


def _dx_image(relationship, *children):
    """Return an IMAGE item that references the chest radiograph."""
    return item(
        relationship,
        "IMAGE",
        None,
        *children,
        sop_class=DX_FOR_PRESENTATION,
        sop_instance=DX_IMAGE,
    )


def _chest_image_library(optional):
    """Return TID 4100 row 3, an Image Library holding TID 4020 for the radiograph.

    The radiograph has a Patient Orientation, a Study Date and Time, and an
    Imager Pixel Spacing, and neither an Image Laterality, since the chest
    is not a paired part, nor a View Code Sequence, so that TID 4020 rows 5
    to 8, 11, and 12 are required. Its Frame of Reference UID (row 17) is
    optional.
    """
    spacing = {"number": "0.143", "units": MILLIMETRE}
    entry = _dx_image(
        "CONTAINS",
        item(ACQUISITION, "TEXT", PATIENT_ORIENTATION_ROW, text="L"),
        item(ACQUISITION, "TEXT", PATIENT_ORIENTATION_COLUMN, text="F"),
        item(ACQUISITION, "DATE", STUDY_DATE_CONCEPT, text=STUDY_DATE),
        item(ACQUISITION, "TIME", STUDY_TIME_CONCEPT, text=STUDY_TIME),
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
    )
    return item("CONTAINS", "CONTAINER", IMAGE_LIBRARY, entry)


def _chest_finding(optional):
    """Return TID 4101 row 3, TID 4104, an abnormal opacity in the radiograph.

    Rows 1, 6, 11 (TID 4019), and 14 (TID 4107, whose row 1 gives the
    finding's centre in the radiograph) are required. Row 8 includes TID
    4108, the finding's tracking identifier (row 1) or UID (row 2), and row
    10, required where the finding is duplicated from another report,
    includes TID 4022: the original report (row 1), its language (row 2),
    and its observer (row 3, TID 1001).
    """
    original = item(
        OBSERVATION,
        "COMPOSITE",
        ORIGINAL_SOURCE,
        _language(),
        sop_class=CHEST_CAD_SR,
        sop_instance=PRIOR_CHEST_CAD[1],
    )
    centre = item(
        "HAS PROPERTIES",
        "SCOORD",
        CENTER,
        _dx_image("SELECTED FROM"),
        graphic_type="POINT",
        points=(812.0, 1044.5),
    )
    return item(
        "INFERRED FROM",
        "CODE",
        SINGLE_IMAGE_FINDING,
        *_chosen(
            optional,
            [
                _row(
                    "TID 4104 row 3",
                    "HAS CONCEPT MOD",
                    "TEXT",
                    ANATOMIC_IDENTIFIER,
                    text=f"{SENTINEL} LOBE",
                ),
            ],
        ),
        item("HAS CONCEPT MOD", "CODE", RENDERING_INTENT, code=PRESENTATION_REQUIRED),
        *_chosen(
            optional,
            [
                _row(
                    "TID 4108 row 1",
                    OBSERVATION,
                    "TEXT",
                    TRACKING_IDENTIFIER,
                    text=f"{SENTINEL} NODULE 1",
                ),
                _row(
                    "TID 4108 row 2",
                    OBSERVATION,
                    "UIDREF",
                    TRACKING_UNIQUE_IDENTIFIER,
                    text=TRACKING_UID,
                ),
            ],
        ),
        *(
            [original, *_person_observer(PRIOR_OBSERVERS_NAME)]
            if "TID 4104 row 10" in optional
            else []
        ),
        *_algorithm(OBSERVATION),
        centre,
        code=ABNORMAL_OPACITY,
    )


def chest_cad_tree(optional=()):
    """Return the root of a chest CAD report's tree, TID 4100.

    TID 4100 rows 1, 2 (TID 1204), 5 (TID 4101, whose row 1 is required), 6,
    and 8 are required. The detections succeeded, so row 7 includes TID
    4015, whose one detection performed (TID 4017) names its algorithm (TID
    4019) and the radiograph (row 3); no analysis was attempted, so row 9 is
    absent. ``"TID 4101 row 3"`` adds a finding, so that the summary is
    "with findings".

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`CHEST_CAD_OPTIONAL_ROWS`.
    """
    _checked(optional, CHEST_CAD_OPTIONAL_ROWS)
    findings = "TID 4101 row 3" in optional
    detection = item(
        "CONTAINS",
        "CODE",
        DETECTION_PERFORMED,
        *_algorithm("HAS PROPERTIES", optional),
        _dx_image("HAS PROPERTIES"),
        *_chosen(
            optional,
            [
                _row(
                    "TID 4017 row 5",
                    "HAS PROPERTIES",
                    "UIDREF",
                    SERIES_INSTANCE_UID,
                    text=DX_SERIES,
                ),
            ],
        ),
        code=ABNORMAL_OPACITY,
    )
    return item(
        None,
        "CONTAINER",
        CHEST_CAD_REPORT,
        _language(),
        *_chosen(
            optional, [("TID 4100 row 3", lambda: _chest_image_library(optional))]
        ),
        item(
            "CONTAINS",
            "CODE",
            CAD_PROCESSING_AND_FINDINGS_SUMMARY,
            *([_chest_finding(optional)] if findings else []),
            code=(
                ALL_SUCCEEDED_WITH_FINDINGS
                if findings
                else ALL_SUCCEEDED_WITHOUT_FINDINGS
            ),
        ),
        item(
            "CONTAINS",
            "CODE",
            SUMMARY_OF_DETECTIONS,
            item("INFERRED FROM", "CONTAINER", SUCCESSFUL_DETECTIONS, detection),
            code=SUCCEEDED,
        ),
        item("CONTAINS", "CODE", SUMMARY_OF_ANALYSES, code=NOT_ATTEMPTED),
    )


COLON_CAD_OPTIONAL_ROWS = ("TID 4019 row 3",)


def colon_cad_tree(optional=()):
    """Return the root of a colon CAD report's tree, TID 4120.

    TID 4120 rows 1 to 5 and 7 are required: the language (TID 1204), one
    Image Set Properties of TID 4122, whose rows 1 to 10 are required, and
    row 11 since the CT gives a Patient Position, the summary (TID 4121 row
    1), and
    the detections, which succeeded, so that row 6 includes TID 4015, whose
    one detection performed (TID 4017) names its algorithm (TID 4019) and
    the CT series (row 5). No analysis was attempted, so row 8 is absent.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`COLON_CAD_OPTIONAL_ROWS`.
    """
    _checked(optional, COLON_CAD_OPTIONAL_ROWS)
    millimetres_per_pixel = {"number": "0.68", "units": MILLIMETRES_PER_PIXEL}
    properties = item(
        "CONTAINS",
        "CONTAINER",
        IMAGE_SET_PROPERTIES,
        item("CONTAINS", "UIDREF", FRAME_OF_REFERENCE_UID, text=FRAME_OF_REFERENCE),
        item("CONTAINS", "UIDREF", STUDY_INSTANCE_UID, text=STUDY),
        item("CONTAINS", "DATE", STUDY_DATE_CONCEPT, text=STUDY_DATE),
        item("CONTAINS", "TIME", STUDY_TIME_CONCEPT, text=STUDY_TIME),
        item("CONTAINS", "CODE", MODALITY, code=COMPUTED_TOMOGRAPHY),
        item("CONTAINS", "NUM", HORIZONTAL_PIXEL_SPACING, **millimetres_per_pixel),
        item("CONTAINS", "NUM", VERTICAL_PIXEL_SPACING, **millimetres_per_pixel),
        item("CONTAINS", "NUM", SLICE_THICKNESS, number="1.25", units=MILLIMETRE),
        item("CONTAINS", "NUM", SPACING_BETWEEN_SLICES, number="1", units=MILLIMETRE),
        item("CONTAINS", "CODE", RECUMBENT_PATIENT_POSITION, code=SUPINE),
    )
    detection = item(
        "CONTAINS",
        "CODE",
        DETECTION_PERFORMED,
        *_algorithm("HAS PROPERTIES", optional),
        item("HAS PROPERTIES", "UIDREF", SERIES_INSTANCE_UID, text=CT_SERIES),
        code=POLYP_OF_COLON,
    )
    return item(
        None,
        "CONTAINER",
        COLON_CAD_REPORT,
        _language(),
        properties,
        item(
            "CONTAINS",
            "CODE",
            CAD_PROCESSING_AND_FINDINGS_SUMMARY,
            code=ALL_SUCCEEDED_WITHOUT_FINDINGS,
        ),
        item(
            "CONTAINS",
            "CODE",
            SUMMARY_OF_DETECTIONS,
            item("INFERRED FROM", "CONTAINER", SUCCESSFUL_DETECTIONS, detection),
            code=SUCCEEDED,
        ),
        item("CONTAINS", "CODE", SUMMARY_OF_ANALYSES, code=NOT_ATTEMPTED),
    )


LOG_OPTIONAL_ROWS = (
    "TID 1003 row 1a",
    "TID 1003 row 2",
    "TID 3601 row 1",
    "TID 3001 row 4",
    "TID 3001 row 5",
    "TID 3001 row 6",
    "TID 3010 row 2",
    "TID 3010 row 3",
    "TID 3010 row 4",
    "TID 3010 row 5",
    "TID 3001 row 6 Physician Note",
    "TID 3001 row 10",
    "TID 3001 row 12",
    "TID 3001 row 23",
)


def _log_entry(optional):
    """Return TID 3001 row 6, a technologist's note, with TID 3010's rows.

    The note's concept is from CID 3401, and TID 3010 qualifies it with a
    comment (row 2), a procedure action's identifier (row 3), a lesion's
    identifier (row 4), and the date and time of its recording (row 5).
    """
    return item(
        "CONTAINS",
        "TEXT",
        TECH_NOTE,
        *_chosen(
            optional,
            [
                _row(
                    "TID 3010 row 2",
                    "HAS PROPERTIES",
                    "TEXT",
                    COMMENT,
                    text=f"{SENTINEL} COMMENT",
                ),
                _row(
                    "TID 3010 row 3",
                    OBSERVATION,
                    "TEXT",
                    PROCEDURE_ACTION_ID,
                    text=f"{SENTINEL}-ACTION",
                ),
                _row(
                    "TID 3010 row 4",
                    OBSERVATION,
                    "TEXT",
                    LESION_IDENTIFIER,
                    text="12",
                ),
                _row(
                    "TID 3010 row 5",
                    OBSERVATION,
                    "DATETIME",
                    DATETIME_OF_RECORDING,
                    text=LOG_DATETIME,
                ),
            ],
        ),
        text=f"{SENTINEL} SHEATH INSERTED",
    )


def log_tree(optional=()):
    """Return the root of a procedure log's tree, TID 3001.

    TID 3001 rows 1 to 3 are required: the title, from CID 3400, an
    observer, a person, by TID 1002, and TID 3601, all of whose rows are
    optional. The other rows are the log's entries and the room and
    equipment of the procedure. PS3.3 Section A.35.7.3.1.2 has each first
    level item that the root CONTAINS, a log event, give the time at which
    the event occurred in Observation DateTime (0040,A032), Type 1, in
    strictly increasing order; they take :data:`EVENT_DATETIMES` in turn.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`LOG_OPTIONAL_ROWS`; TID
        3010's are included only with ``"TID 3001 row 6"``.
    """
    _checked(optional, LOG_OPTIONAL_ROWS)
    root = item(
        None,
        "CONTAINER",
        CATH_LAB_PROCEDURE_LOG,
        *_person_observer(OBSERVERS_NAME, optional),
        *_chosen(
            optional,
            [
                _row(
                    "TID 3601 row 1",
                    ACQUISITION,
                    "TEXT",
                    PROCEDURE_DESCRIPTION,
                    text=f"{SENTINEL} PROCEDURE",
                ),
                _row(
                    "TID 3001 row 4",
                    ACQUISITION,
                    "TEXT",
                    ROOM_IDENTIFICATION,
                    text=f"{SENTINEL} ROOM",
                ),
                _row(
                    "TID 3001 row 5",
                    ACQUISITION,
                    "TEXT",
                    EQUIPMENT_IDENTIFICATION,
                    text=f"{SENTINEL} EQUIPMENT",
                ),
                ("TID 3001 row 6", lambda: _log_entry(optional)),
                _row(
                    "TID 3001 row 6 Physician Note",
                    "CONTAINS",
                    "TEXT",
                    PHYSICIAN_NOTE,
                    text=f"{SENTINEL} PHYSICIAN NOTE",
                ),
                _row(
                    "TID 3001 row 10",
                    "CONTAINS",
                    "PNAME",
                    PERSONNEL_ARRIVED,
                    text=STAFF_NAME,
                ),
                _row(
                    "TID 3001 row 12",
                    "CONTAINS",
                    "TEXT",
                    EQUIPMENT_BROUGHT,
                    text=f"{SENTINEL} INJECTOR",
                ),
                _row(
                    "TID 3001 row 23",
                    "CONTAINS",
                    "CODE",
                    COMPLICATION_OF_PROCEDURE,
                    code=DEATH_DURING_CATHETERIZATION,
                ),
            ],
        ),
    )
    events = [i for i in root.ContentSequence if i.RelationshipType == "CONTAINS"]
    for event, occurred in zip(events, EVENT_DATETIMES[: len(events)], strict=True):
        event.ObservationDateTime = occurred
    return root


SPECTACLE_OPTIONAL_ROWS = ("TID 2020 row 4", "TID 2020 row 6", "TID 2020 row 8")


def _lens(concept, sphere):
    """Return TID 2020 row 2 or 4, an eye's prescription, with TID 2021 row 1."""
    return item(
        "CONTAINS",
        "CONTAINER",
        concept,
        item("CONTAINS", "NUM", SPHERE, number=sphere, units=DIOPTRES),
    )


def spectacle_tree(optional=()):
    """Return the root of a spectacle prescription's tree, TID 2020.

    Only TID 2020 row 1 is required; the right eye's lens is prescribed, so
    row 2, with TID 2021 row 1, the sphere, is present. TID 2020 includes no
    observation context.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`SPECTACLE_OPTIONAL_ROWS`.
    """
    _checked(optional, SPECTACLE_OPTIONAL_ROWS)
    return item(
        None,
        "CONTAINER",
        SPECTACLE_PRESCRIPTION,
        _lens(RIGHT_EYE_RX, "-1.25"),
        *_chosen(
            optional,
            [
                ("TID 2020 row 4", lambda: _lens(LEFT_EYE_RX, "-1.5")),
                _row(
                    "TID 2020 row 6",
                    "CONTAINS",
                    "NUM",
                    DISTANCE_PUPILLARY_DISTANCE,
                    number="63",
                    units=MILLIMETRE_PD,
                ),
                _row(
                    "TID 2020 row 8",
                    "CONTAINS",
                    "TEXT",
                    COMMENT,
                    text=f"{SENTINEL} COMMENT",
                ),
            ],
        ),
    )


def _quality(concept, number):
    """Return TID 2101 row 17 or 19, a quality rating, with TID 2102 rows 1 to 3."""
    return item(
        "CONTAINS",
        "NUM",
        concept,
        item(OBSERVATION, "TEXT", ALGORITHM_NAME, text="FIXTURE GRID"),
        item(OBSERVATION, "TEXT", ALGORITHM_VERSION, text="3.0"),
        item(OBSERVATION, "TEXT", ALGORITHM_MANUFACTURER, text="FIXTURE MAKER"),
        number=number,
        units=RANGE_0_100,
    )


def macular_grid_tree():
    """Return the root of a macular grid report's tree, TID 2100, for the right eye.

    Every row of the tree is required: TID 2100 rows 1 to 4, with the
    language (TID 1204), the observation context (TID 1001), whose
    observer, a person, is named, and TID 2101 for the right eye, whose rows
    1 to 17 and 19 are required, rows 17 and 19 each with TID 2102 rows 1 to
    3. TID 2101 codes the findings' container (row 1) and its thicknesses and
    volume (rows 4 to 14) in LOINC.
    """
    side = item("HAS CONCEPT MOD", "CODE", LATERALITY, code=RIGHT)
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
            units=CUBIC_MILLIMETRE,
        ),
        item("CONTAINS", "NUM", IMAGES_USED, number="25", units=IMAGES),
        item("CONTAINS", "NUM", SAMPLES_USED, number="512", units=SAMPLES),
        _quality(ANALYSIS_QUALITY_RATING, "92"),
        _quality(IMAGE_SET_QUALITY_RATING, "88"),
    )
    return item(
        None,
        "CONTAINER",
        MACULAR_GRID_TITLE,
        _language(),
        *_person_observer(OBSERVERS_NAME),
        findings,
    )


WAVEFORM_OPTIONAL_ROWS = (
    "TID 3750 row 11",
    "TID 3750 row 12",
    "TID 321 row 3 datetime",
    "TID 3751 row 3",
    "TID 3751 row 6",
    "TID 3750 row 19",
    "TID 3750 row 20",
)


def _pattern_event(optional):
    """Return TID 3750 row 12, TID 3751, an apnoea in a segment of the EEG.

    Row 5 includes TID 321 with $Purpose (260753009, SCT, "Source"): its row
    3, the segment's temporal coordinates, selected from the waveform (row
    4). ``"TID 321 row 3 datetime"`` gives the coordinates as a point in
    time, by its Referenced DateTime, rather than by sample positions. Row 3
    includes TID 1001 for the annotation's own observer, a person, and row 6
    is a short label, free text.
    """
    return item(
        "CONTAINS",
        "CODE",
        PATTERN_EVENT,
        *(_person_observer(ANNOTATORS_NAME) if "TID 3751 row 3" in optional else []),
        _temporal(
            SOURCE,
            _waveform("SELECTED FROM", None),
            at_datetime="TID 321 row 3 datetime" in optional,
        ),
        *_chosen(
            optional,
            [
                _row(
                    "TID 3751 row 6",
                    "HAS PROPERTIES",
                    "TEXT",
                    SHORT_LABEL,
                    text=f"{SENTINEL} LABEL",
                ),
            ],
        ),
        code=APNEA,
    )


def waveform_tree(optional=()):
    """Return the root of a waveform annotation document's tree, TID 3750.

    TID 3750 rows 1, 3, 7, 9, and 10 are required: the title, from CID 3048,
    the observation context (TID 1001), whose observer, a person, is named,
    and the annotations' container, holding one group with its number. The
    group's annotations are optional: a pattern event (row 12, TID 3751), a
    measurement (row 19, TID 3752), and a note (row 20, TID 3753), each of
    which includes TID 321: the pattern event its row 3, temporal
    coordinates selected from the EEG, and the measurement and the note its
    row 1, a reference to the EEG.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`WAVEFORM_OPTIONAL_ROWS`;
        those of TID 3751 and TID 321's datetime only with ``"TID 3750 row
        12"``.
    """
    _checked(optional, WAVEFORM_OPTIONAL_ROWS)
    measurement = item(
        "CONTAINS",
        "NUM",
        CIRCUM_HEAD,
        _waveform("INFERRED FROM", SOURCE_OF_MEASUREMENT),
        number="56",
        units=CENTIMETRE,
    )
    note = item(
        "CONTAINS",
        "TEXT",
        ANNOTATION_NOTE,
        _waveform("INFERRED FROM", SOURCE),
        text=f"{SENTINEL} NOTE",
    )
    group = item(
        "CONTAINS",
        "CONTAINER",
        WAVEFORM_ANNOTATION_GROUP,
        item(OBSERVATION, "NUM", GROUP_NUMBER, number="1", units=NO_UNITS),
        *_chosen(
            optional,
            [
                _row(
                    "TID 3750 row 11",
                    OBSERVATION,
                    "TEXT",
                    GROUP_LABEL,
                    text=f"{SENTINEL} GROUP",
                ),
                ("TID 3750 row 12", lambda: _pattern_event(optional)),
                ("TID 3750 row 19", lambda: measurement),
                ("TID 3750 row 20", lambda: note),
            ],
        ),
    )
    return item(
        None,
        "CONTAINER",
        NEUROPHYSIOLOGY_RECORDING_ANNOTATIONS,
        *_person_observer(OBSERVERS_NAME),
        item("CONTAINS", "CONTAINER", WAVEFORM_ANNOTATIONS_CONTAINER, group),
    )


def _header(sop_class, instance):
    """Return the header of a report, with its SR Document General Module's flags.

    ``instance`` gives its Series and SOP Instance UIDs. The header holds
    the Patient, General Study, SR Document Series, General Equipment, and
    Enhanced General Equipment Modules' required attributes, the SOP Common
    Module's, and the instance number and content date and time, with
    identifying values of their own.
    """
    series, sop_instance = instance
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = sop_instance
    dataset.PatientName = PATIENTS_NAME
    dataset.PatientID = PATIENT_ID
    dataset.PatientBirthDate = BIRTH_DATE
    dataset.PatientSex = "M"
    dataset.StudyInstanceUID = STUDY
    dataset.StudyDate = STUDY_DATE
    dataset.StudyTime = STUDY_TIME
    dataset.ReferringPhysicianName = REFERRERS_NAME
    dataset.StudyID = ""
    dataset.AccessionNumber = f"{SENTINEL}-ACC"
    dataset.Modality = "SR"
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
    dataset.CompletionFlag = "COMPLETE"
    dataset.PerformedProcedureCodeSequence = pydicom.Sequence()
    return dataset


def _report(identity, tree, verified, **evidence):
    """Return a Structured Report whose SR Document Content Module holds ``tree``.

    ``identity`` gives its SOP Class, its Series and SOP Instance UIDs, and
    its root template. Its Verification Flag is VERIFIED, with a Verifying
    Observer Sequence, where ``verified``, and UNVERIFIED otherwise.
    ``evidence`` gives its Current Requested Procedure Evidence Sequence
    and Pertinent Other Evidence Sequence, by keyword, where it has them.
    """
    sop_class, instance, template = identity
    dataset = _header(sop_class, instance)
    dataset.VerificationFlag = "VERIFIED" if verified else "UNVERIFIED"
    if verified:
        # PS3.3 Table C.17-2: Type 1C, required where VERIFIED.
        observer = pydicom.Dataset()
        observer.VerifyingObserverName = VERIFIERS_NAME
        observer.VerifyingObserverIdentificationCodeSequence = pydicom.Sequence()
        observer.VerifyingOrganization = f"{SENTINEL} HOSPITAL"
        observer.VerificationDateTime = VERIFICATION_DATETIME
        dataset.VerifyingObserverSequence = pydicom.Sequence([observer])
    for keyword, sequence in evidence.items():
        setattr(dataset, keyword, sequence)
    for element in tree:
        dataset.add(element)
    template_item = pydicom.Dataset()
    template_item.MappingResource = "DCMR"
    template_item.TemplateIdentifier = template
    dataset.ContentTemplateSequence = pydicom.Sequence([template_item])
    return dataset


def chest_cad_report(optional=(), *, verified=False):
    """Return a Chest CAD SR whose tree is :func:`chest_cad_tree`.

    ``verified`` gives it the Verification Flag VERIFIED, with a Verifying
    Observer Sequence, rather than UNVERIFIED. Its evidence is the
    radiograph that its tree references, and, where a finding is duplicated
    from an earlier report, that report.
    """
    evidence = {
        "CurrentRequestedProcedureEvidenceSequence": _evidence(
            DX_SERIES, DX_FOR_PRESENTATION, DX_IMAGE
        )
    }
    if "TID 4104 row 10" in optional:
        evidence["PertinentOtherEvidenceSequence"] = _evidence(
            PRIOR_CHEST_CAD[0], CHEST_CAD_SR, PRIOR_CHEST_CAD[1], PRIOR_STUDY
        )
    return _report(
        (CHEST_CAD_SR, CHEST_CAD, "4100"),
        chest_cad_tree(optional),
        verified,
        **evidence,
    )


def colon_cad_report(optional=(), *, verified=False):
    """Return a Colon CAD SR whose tree is :func:`colon_cad_tree`.

    ``verified`` is as for :func:`chest_cad_report`. Its evidence is an
    image of the CT series that its tree names.
    """
    return _report(
        (COLON_CAD_SR, COLON_CAD, "4120"),
        colon_cad_tree(optional),
        verified,
        CurrentRequestedProcedureEvidenceSequence=_evidence(
            CT_SERIES, CT_IMAGE_STORAGE, CT_IMAGE
        ),
    )


def procedure_log(optional=(), *, verified=False):
    """Return a Procedure Log whose tree is :func:`log_tree`.

    ``verified`` is as for :func:`chest_cad_report`. The IOD requires the
    Synchronization Module, whose required attributes the log holds.
    """
    dataset = _report((PROCEDURE_LOG, LOG, "3001"), log_tree(optional), verified)
    dataset.SynchronizationFrameOfReferenceUID = SYNCHRONIZATION_FRAME
    dataset.SynchronizationTrigger = "NO TRIGGER"
    dataset.AcquisitionTimeSynchronized = "N"
    return dataset


def spectacle_prescription(optional=(), *, verified=False):
    """Return a Spectacle Prescription Report whose tree is :func:`spectacle_tree`.

    ``verified`` is as for :func:`chest_cad_report`.
    """
    return _report(
        (SPECTACLE_PRESCRIPTION_REPORT, SPECTACLES, "2020"),
        spectacle_tree(optional),
        verified,
    )


def macular_grid_report(optional=(), *, verified=False):
    """Return a Macular Grid Thickness and Volume Report, :func:`macular_grid_tree`.

    ``verified`` is as for :func:`chest_cad_report`. The tree has no
    optional rows, so ``optional`` must be empty.
    """
    _checked(optional, ())
    return _report(
        (MACULAR_GRID_REPORT, MACULAR_GRID, "2100"),
        macular_grid_tree(),
        verified,
    )


def waveform_annotations(optional=(), *, verified=False):
    """Return a Waveform Annotation SR whose tree is :func:`waveform_tree`.

    ``verified`` is as for :func:`chest_cad_report`. Its evidence, where
    its tree references the EEG, is the EEG.
    """
    references = {"TID 3750 row 12", "TID 3750 row 19", "TID 3750 row 20"}
    evidence = (
        {
            "CurrentRequestedProcedureEvidenceSequence": _evidence(
                EEG_SERIES, ROUTINE_SCALP_EEG, EEG_WAVEFORM
            )
        }
        if references & set(optional)
        else {}
    )
    return _report(
        (WAVEFORM_ANNOTATION_SR, WAVEFORM_ANNOTATIONS, "3750"),
        waveform_tree(optional),
        verified,
        **evidence,
    )
