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

"""Synthetic CT, Enhanced X-Ray, and Patient Radiation Dose Structured Reports.

Three builders give one report each, whose content tree follows the root
template that PS3.3 2026d Section A.35 names for its IOD:

- :func:`ct_dose_report`, an X-Ray Radiation Dose SR whose tree follows TID
  10011 "CT Radiation Dose", which Section A.35.8 allows at the root beside
  TID 10001, with TID 10015 "CT Dose Check Details";
- :func:`enhanced_dose_report`, an Enhanced X-Ray Radiation Dose SR whose
  tree follows TID 10040 "Enhanced X-Ray Radiation Dose" (Section
  A.35.22); and
- :func:`patient_dose_report`, a Patient Radiation Dose SR whose tree
  follows TID 10030 "Patient Radiation Dose" (Section A.35.18).

Each content item's relationship, Value Type, and concept name is a row of
a template of DICOM PS3.16 2026d, cited beside it, and each coded value is
one of the context group that the row names. Code meanings are those of
PS3.16 Annex D for DCM codes, and those the templates and context groups
give for the others; a language's is the description of its subtag in the
IANA Language Subtag Registry, which CID 5000 names.

Each tree is partial, as those of :mod:`._synthetic_dose_reports` are: it
holds the rows that its templates require where they are included, apart
from the templates that the builder's docstring names as left out, and the
optional rows that carry identifying values: names and identifiers of
people, devices, and organisations, free text, dates, UIDs, and references
to other instances. The optional rows are keyed by their template and row,
such as ``"TID 1004 row 2"``, so that a test can build a report with any of
them. Each report is observed by the device that recorded it, through TID
1004, whose builder and that of TID 1021 "Device Participant" are
:mod:`._synthetic_dose_reports`'s. The header is
:mod:`._synthetic_structured_reports`'s, with its identifying values, and
so are the builder of content items and of TID 1204, the language of the
content.

Text that must never reach a written file under the Basic Profile carries
``SENTINEL``, as in the header, except the name of a person participant,
whose words occur in no code meaning and no other value, since the residual
search looks for each word of a name. Every UID is invented under ``2.25.``, the
patient is fictitious, and no value comes from a real report.
"""

# The three reports share their codes and builders, so they stay in one
# module.
# pylint: disable = too-many-lines

from pymedphys._imports import pydicom

from . import _synthetic_dose_reports as dose
from . import _synthetic_structured_reports as general

Code = general.Code
item = general.item
SENTINEL = general.SENTINEL

X_RAY_RADIATION_DOSE_SR = dose.X_RAY_RADIATION_DOSE_SR
ENHANCED_X_RAY_RADIATION_DOSE_SR = "1.2.840.10008.5.1.4.1.1.88.76"
PATIENT_RADIATION_DOSE_SR = "1.2.840.10008.5.1.4.1.1.88.73"
X_RAY_IOD = dose.X_RAY_IOD
ENHANCED_IOD = "Enhanced X-Ray Radiation Dose SR"
PATIENT_IOD = "Patient Radiation Dose SR"
# The instances that the reports reference, other than each other.
DIGITAL_X_RAY_FOR_PRESENTATION = "1.2.840.10008.5.1.4.1.1.1.1"
SPATIAL_FIDUCIALS_STORAGE = "1.2.840.10008.5.1.4.1.1.66.2"
RT_DOSE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.2"

STUDY = general.STUDY
# A person name whose words occur in no code meaning and no other value, so
# that the residual search, which looks for each word of a name, finds it
# only where it is kept.
PARTICIPANTS_NAME = "TREVANION^ISOLDE"
# The Series and SOP Instance UIDs of each report and of each instance that
# a report references.
CT_REPORT = ("2.25.6200", "2.25.6201")
ENHANCED_REPORT = ("2.25.6300", "2.25.6301")
PATIENT_REPORT = ("2.25.6400", "2.25.6401")
ACQUIRED_IMAGE = ("2.25.6310", "2.25.6311")
SPATIAL_FIDUCIALS = ("2.25.6410", "2.25.6411")
DOSE_MAP = ("2.25.6420", "2.25.6421")
# The UIDs that content items carry, other than the references above.
CT_DEVICE_OBSERVER_UID = "2.25.6501"
CT_IRRADIATION_EVENT_UID = "2.25.6502"
CT_REPEATED_EVENT_UID = "2.25.6503"
CT_FRAME_OF_REFERENCE = "2.25.6504"
ENHANCED_DEVICE_OBSERVER_UID = "2.25.6511"
ENHANCED_IRRADIATION_EVENT_UID = "2.25.6512"
ENHANCED_REPEATED_EVENT_UID = "2.25.6513"
ENHANCED_FRAME_OF_REFERENCE = "2.25.6514"
RDSR_FRAME_OF_REFERENCE = "2.25.6515"
PATIENT_DEVICE_OBSERVER_UID = "2.25.6521"
PATIENT_MODEL_DATA_UID = "2.25.6522"
# The UIDs of the device participants, which TID 1021 gives, from
# :mod:`._synthetic_dose_reports`.
IRRADIATING_DEVICE_UID = dose.IRRADIATING_DEVICE_UID
UIDS = (
    *CT_REPORT,
    *ENHANCED_REPORT,
    *PATIENT_REPORT,
    *ACQUIRED_IMAGE,
    *SPATIAL_FIDUCIALS,
    *DOSE_MAP,
    CT_DEVICE_OBSERVER_UID,
    CT_IRRADIATION_EVENT_UID,
    CT_REPEATED_EVENT_UID,
    CT_FRAME_OF_REFERENCE,
    ENHANCED_DEVICE_OBSERVER_UID,
    ENHANCED_IRRADIATION_EVENT_UID,
    ENHANCED_REPEATED_EVENT_UID,
    ENHANCED_FRAME_OF_REFERENCE,
    RDSR_FRAME_OF_REFERENCE,
    PATIENT_DEVICE_OBSERVER_UID,
    PATIENT_MODEL_DATA_UID,
    IRRADIATING_DEVICE_UID,
)
# The datetimes that content items carry, all on the header's study date,
# none of which a modified or dummy value repeats.
CT_START = "20260412091205"
CT_END = "20260412091731"
CT_EVENT_START = "20260412091402"
ENHANCED_EVENT_START = "20260412094410"
ENHANCED_EVENT_END = "20260412094411"
ENHANCED_DETAILS_START = "20260412094402"
ENHANCED_DETAILS_END = "20260412094426"
CALIBRATION_DATETIME = "20250923101500"
DATETIMES = (
    CT_START,
    CT_END,
    CT_EVENT_START,
    ENHANCED_EVENT_START,
    ENHANCED_EVENT_END,
    ENHANCED_DETAILS_START,
    ENHANCED_DETAILS_END,
    CALIBRATION_DATETIME,
)

# Concept names, by the first template row that uses them.
X_RAY_RADIATION_DOSE_REPORT = dose.X_RAY_RADIATION_DOSE_REPORT
PROCEDURE_REPORTED = dose.PROCEDURE_REPORTED
HAS_INTENT = dose.HAS_INTENT
SCOPE_OF_ACCUMULATION = dose.SCOPE_OF_ACCUMULATION
COMMENT = dose.COMMENT
SOURCE_OF_DOSE_INFORMATION = dose.SOURCE_OF_DOSE_INFORMATION
# TID 10011.
START_OF_X_RAY_IRRADIATION = Code("113809", "DCM", "Start of X-Ray Irradiation")
END_OF_X_RAY_IRRADIATION = Code("113810", "DCM", "End of X-Ray Irradiation")
# TID 10012.
CT_ACCUMULATED_DOSE_DATA = Code("113811", "DCM", "CT Accumulated Dose Data")
TOTAL_NUMBER_OF_IRRADIATION_EVENTS = Code(
    "113812", "DCM", "Total Number of Irradiation Events"
)
CT_DOSE_LENGTH_PRODUCT_TOTAL = Code("113813", "DCM", "CT Dose Length Product Total")
CT_EFFECTIVE_DOSE_TOTAL = Code("113814", "DCM", "CT Effective Dose Total")
REFERENCE_AUTHORITY = Code("121406", "DCM", "Reference Authority")
MEASUREMENT_METHOD = Code("370129005", "SCT", "Measurement Method")
PATIENT_MODEL = Code("113815", "DCM", "Patient Model")
# TID 10013 and 10014.
CT_ACQUISITION = Code("113819", "DCM", "CT Acquisition")
ACQUISITION_PROTOCOL = dose.ACQUISITION_PROTOCOL
TARGET_REGION = dose.TARGET_REGION
CT_ACQUISITION_TYPE = Code("113820", "DCM", "CT Acquisition Type")
IRRADIATION_EVENT_UID = dose.IRRADIATION_EVENT_UID_CONCEPT
IRRADIATION_EVENT_LABEL = dose.IRRADIATION_EVENT_LABEL
IS_REPEATED_ACQUISITION = Code("128551", "DCM", "Is Repeated Acquisition")
REASON_FOR_REPEATING_ACQUISITION = Code(
    "128552", "DCM", "Reason for Repeating Acquisition"
)
DATETIME_STARTED = dose.DATETIME_STARTED
CT_ACQUISITION_PARAMETERS = Code("113822", "DCM", "CT Acquisition Parameters")
EXPOSURE_TIME = Code("113824", "DCM", "Exposure Time")
SCANNING_LENGTH = Code("113825", "DCM", "Scanning Length")
TOP_Z_LOCATION_OF_SCANNING_LENGTH = Code(
    "113897", "DCM", "Top Z Location of Scanning Length"
)
FRAME_OF_REFERENCE_UID = Code("112227", "DCM", "Frame of Reference UID")
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
# TID 10015.
DOSE_CHECK_ALERT_DETAILS = Code("113900", "DCM", "Dose Check Alert Details")
DLP_ALERT_VALUE_CONFIGURED = Code("113901", "DCM", "DLP Alert Value Configured")
CTDIVOL_ALERT_VALUE_CONFIGURED = Code("113902", "DCM", "CTDIvol Alert Value Configured")
DLP_ALERT_VALUE = Code("113903", "DCM", "DLP Alert Value")
ACCUMULATED_DLP_FORWARD_ESTIMATE = Code(
    "113905", "DCM", "Accumulated DLP Forward Estimate"
)
REASON_FOR_PROCEEDING = Code("113907", "DCM", "Reason for Proceeding")
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
# TID 10040, 10041, 10042, and 10043.
ACCUMULATED_DOSE_DATA = Code("130500", "DCM", "Accumulated Dose Data")
CALIBRATION = dose.CALIBRATION
DOSE_MEASUREMENT_DEVICE = dose.DOSE_MEASUREMENT_DEVICE
CALIBRATION_DATETIME_CONCEPT = dose.CALIBRATION_DATETIME_CONCEPT
CALIBRATION_FACTOR = dose.CALIBRATION_FACTOR
CALIBRATION_UNCERTAINTY = dose.CALIBRATION_UNCERTAINTY
CALIBRATION_RESPONSIBLE_PARTY = dose.CALIBRATION_RESPONSIBLE_PARTY
CALIBRATION_PROTOCOL = dose.CALIBRATION_PROTOCOL
CALIBRATION_INTENDED_ACQUISITION_PROTOCOL = Code(
    "131331", "DCM", "Calibration Intended Acquisition Protocol"
)
REFERENCE_POINT_DOSIMETRY = Code("130502", "DCM", "Reference Point Dosimetry")
REFERENCE_POINT_DEFINITION = Code("113780", "DCM", "Reference Point Definition")
IRRADIATION_EVENT_SUMMARY_DATA = Code("130501", "DCM", "Irradiation Event Summary Data")
DATETIME_ENDED = Code("111527", "DCM", "DateTime Ended")
IRRADIATION_EVENT_TYPE = dose.IRRADIATION_EVENT_TYPE
ACQUIRED_IMAGE_CONCEPT = Code("113795", "DCM", "Acquired Image")
IRRADIATION_DETAILS = Code("130505", "DCM", "Irradiation Details")
RDSR_FRAME_OF_REFERENCE_ORIGIN = Code("130506", "DCM", "RDSR Frame of Reference Origin")
RDSR_FRAME_OF_REFERENCE_DESCRIPTION = Code(
    "130507", "DCM", "RDSR Frame of Reference Description"
)
# TID 10030, 10031, 10032, and 10033.
PATIENT_RADIATION_DOSE_REPORT = Code("128401", "DCM", "Patient Radiation Dose Report")
RADIATION_DOSE_ESTIMATE = Code("128402", "DCM", "Radiation Dose Estimate")
RADIATION_DOSE_ESTIMATE_NAME = Code("128403", "DCM", "Radiation Dose Estimate Name")
RADIATION_DOSE_ESTIMATE_REPRESENTATION = Code(
    "128412", "DCM", "Radiation Dose Estimate Representation"
)
DISTRIBUTION_REPRESENTATION = Code("128413", "DCM", "Distribution Representation")
RADIATION_DOSE_REPRESENTATION_DATA = Code(
    "128414", "DCM", "Radiation Dose Representation Data"
)
ORGAN = Code("113343008", "SCT", "Organ")
ORGAN_DOSE_INFORMATION = Code("113517", "DCM", "Organ Dose Information")
REFERENCE_TO_UNCERTAINTY_DETERMINATION_METHOD = Code(
    "128511", "DCM", "Reference to Uncertainty Determination Method"
)
RADIATION_DOSE_ESTIMATE_METHODOLOGY = Code(
    "128415", "DCM", "Radiation Dose Estimate Methodology"
)
SR_INSTANCE_USED = Code("128416", "DCM", "SR Instance Used")
SPATIAL_FIDUCIALS_CONCEPT = Code("128447", "DCM", "Spatial Fiducials")
EVENT_UID_USED = Code("128429", "DCM", "Event UID Used")
PATIENT_RADIATION_DOSE_MODEL = Code("128500", "DCM", "Patient Radiation Dose Model")
PATIENT_MODEL_TYPE = Code("128417", "DCM", "Patient Model Type")
RADIATION_TRANSPORT_MODEL_TYPE = Code("128420", "DCM", "Radiation Transport Model Type")
PATIENT_RADIATION_DOSE_MODEL_DATA = Code(
    "128425", "DCM", "Patient Radiation Dose Model Data"
)
PATIENT_RADIATION_DOSE_MODEL_REFERENCE = Code(
    "128426", "DCM", "Patient Radiation Dose Model Reference"
)
PATIENT_MODEL_DEMOGRAPHICS = Code("128427", "DCM", "Patient Model Demographics")
MODEL_MINIMUM_AGE = Code("128428", "DCM", "Model Minimum Age")
RADIATION_DOSE_ESTIMATE_METHOD = Code("128476", "DCM", "Radiation Dose Estimate Method")
RADIATION_DOSE_ESTIMATE_METHOD_TYPE = Code(
    "128477", "DCM", "Radiation Dose Estimate Method Type"
)
RADIATION_DOSE_ESTIMATE_METHOD_REFERENCE = Code(
    "128482", "DCM", "Radiation Dose Estimate Method Reference"
)

# Coded values, each from the context group or row that it is cited beside.
COMPUTED_TOMOGRAPHY_X_RAY = Code(
    "77477000", "SCT", "Computed Tomography X-Ray"
)  # TID 10011 row 2
PLAIN_RADIOGRAPHY = Code("168537006", "SCT", "Plain radiography")  # CID 10005
DIAGNOSTIC_INTENT = dose.DIAGNOSTIC_INTENT  # CID 3629
STUDY_SCOPE = dose.STUDY_SCOPE  # CID 10000
STUDY_INSTANCE_UID = dose.STUDY_INSTANCE_UID  # CID 10001
AUTOMATED_DATA_COLLECTION = dose.AUTOMATED_DATA_COLLECTION  # CID 10020, 10021
CHEST = dose.CHEST  # CID 4030, by CID 4031
SPIRAL_ACQUISITION = Code("116152004", "SCT", "Spiral Acquisition")  # CID 10013
BODY_PHANTOM = Code("113691", "DCM", "IEC 320mm Body CT Dosimetry Phantom")  # CID 4053
DLP_TO_E_VIA_MC = Code(
    "113800", "DCM", "DLP to E conversion via MC computation"
)  # CID 10011
YES = Code("373066001", "SCT", "Yes")  # CID 230, 231
NO = Code("373067005", "SCT", "No")  # CID 230
PATIENT_MOTION = Code("128553", "DCM", "Patient motion")  # CID 10034
IRRADIATION_AUTHORIZING = dose.IRRADIATION_AUTHORIZING
IRRADIATION_ADMINISTERING = dose.IRRADIATION_ADMINISTERING
STATIONARY_ACQUISITION = dose.STATIONARY_ACQUISITION  # CID 10002
DOSIMETER = dose.DOSIMETER  # CID 10010
EQUIPMENT_ORIGIN = Code("130537", "DCM", "Equipment Origin")  # CID 10074
SKIN_DOSE_MAP = Code("128485", "DCM", "Skin Dose Map")  # CID 10063
ENTIRE_BODY = Code("38266002", "SCT", "Entire body")  # CID 10060
MEAN_ABSORBED_RADIATION_DOSE = Code(
    "128533", "DCM", "Mean Absorbed Radiation Dose"
)  # CID 10061
MEASUREMENT_UNCERTAINTY = Code(
    "371884006", "SCT", "+/-, range of measurement uncertainty"
)  # CID 225
ANTHROPOMORPHIC_MODEL = Code("128404", "DCM", "Anthropomorphic Model")  # CID 10064
VOXELIZED_TRANSPORT_MODEL = Code(
    "128422", "DCM", "Voxelized Radiation Transport Model"
)  # CID 10065
ANALYTICAL_ALGORITHM = Code("128480", "DCM", "Analytical Algorithm")  # CID 10068
# Units, as the rows give them, or from CID 7456 for an age.
EVENTS = Code("{events}", "UCUM", "events")
MILLIGRAY_CENTIMETRE = Code("mGy.cm", "UCUM", "mGy.cm")
MILLISIEVERT = Code("mSv", "UCUM", "mSv")
SECONDS = Code("s", "UCUM", "s")
MILLIMETRE = Code("mm", "UCUM", "mm")
RATIO = Code("{ratio}", "UCUM", "ratio")
X_RAY_SOURCES = Code("{X-Ray sources}", "UCUM", "X-Ray sources")
KILOVOLT = Code("kV", "UCUM", "kV")
MILLIAMPERE = Code("mA", "UCUM", "mA")
MILLIGRAY = Code("mGy", "UCUM", "mGy")
NO_UNITS = dose.NO_UNITS
PERCENT = dose.PERCENT
YEAR = dose.YEAR


def _chosen(optional, rows):
    """Return the items of ``rows``, keyed by template row, that ``optional`` names."""
    return [built() for key, built in rows if key in optional]


def _checked(optional, rows):
    """Raise ValueError if ``optional`` names a row that ``rows`` does not hold."""
    unknown = set(optional) - set(rows)
    if unknown:
        raise ValueError(f"not an optional row: {sorted(unknown)}")


def _text(key, relationship, concept, text):
    """Return an optional TEXT row, keyed by its template and row, and its builder."""
    return key, lambda: item(relationship, "TEXT", concept, text=text)


def _comment(key, text):
    """Return an optional Comment row, which every root template here allows."""
    return _text(key, "CONTAINS", COMMENT, f"{SENTINEL} {text}")


def _language():
    """Return TID 1204 row 1, the language of the content, in English."""
    return general.item(
        "HAS CONCEPT MOD", "CODE", general.LANGUAGE, code=general.ENGLISH
    )


def _procedure(procedure):
    """Return the Procedure reported, with its Has Intent, diagnostic."""
    return item(
        "HAS CONCEPT MOD",
        "CODE",
        PROCEDURE_REPORTED,
        item("HAS CONCEPT MOD", "CODE", HAS_INTENT, code=DIAGNOSTIC_INTENT),
        code=procedure,
    )


def _evidence(*references):
    """Return a Current Requested Procedure Evidence Sequence.

    ``references`` gives each instance's SOP Class UID and its Series and
    SOP Instance UIDs; PS3.3 Table C.17-2 requires the sequence where the
    content tree references instances, and every one of them is in the
    header's study.
    """
    series = {}
    for sop_class, (series_uid, sop_instance) in references:
        referenced = pydicom.Dataset()
        referenced.ReferencedSOPClassUID = sop_class
        referenced.ReferencedSOPInstanceUID = sop_instance
        series.setdefault(series_uid, []).append(referenced)
    in_study = pydicom.Dataset()
    in_study.StudyInstanceUID = STUDY
    in_study.ReferencedSeriesSequence = pydicom.Sequence()
    for series_uid, instances in series.items():
        in_series = pydicom.Dataset()
        in_series.SeriesInstanceUID = series_uid
        in_series.ReferencedSOPSequence = pydicom.Sequence(instances)
        in_study.ReferencedSeriesSequence.append(in_series)
    return pydicom.Sequence([in_study])


# Each optional row that another optional row holds, with the row that holds
# it, for every report.
HELD_BY = {
    "TID 10015 row 8": "TID 10015 row 1",
    "TID 10015 row 17": "TID 10015 row 10",
    "TID 10015 row 18": "TID 10015 row 10",
    "TID 10013 row 38 TID 1020 row 3": "TID 10013 row 38",
    "TID 10013 row 38 TID 1020 row 5": "TID 10013 row 38",
    "TID 10041 row 3": "TID 10040 row 7",
    "TID 10041 row 9": "TID 10041 row 3",
    "TID 10041 row 9b": "TID 10041 row 3",
    "TID 10041 row 10": "TID 10040 row 7",
    "TID 10041 row 20": "TID 10040 row 7",
    "TID 10041 row 28": "TID 10040 row 7",
    "TID 10042 row 46 TID 1020 row 3": "TID 10042 row 46",
    "TID 10042 row 46 TID 1020 row 5": "TID 10042 row 46",
    "TID 10032 row 7": "TID 10031 row 5",
    "TID 10031 row 12": "TID 10031 row 11",
}


def with_holders(key):
    """Return the optional row ``key`` with every optional row that holds it."""
    keys = [key]
    while keys[-1] in HELD_BY:
        keys.append(HELD_BY[keys[-1]])
    return tuple(keys)


# The optional rows of TID 1004 that each report's device observer can hold.
DEVICE_OBSERVER_ROWS = (
    "TID 1004 row 2",
    "TID 1004 row 3",
    "TID 1004 row 4",
    "TID 1004 row 5",
    "TID 1004 row 6",
)


def _device_observer(uid, optional):
    """Return TID 1002 rows 1 and 3 for the recording device, with TID 1004's rows."""
    # pylint: disable-next = protected-access
    return dose._device_observer("HAS OBS CONTEXT", uid, optional)


def _person_participant(role, optional, prefix=None):
    """Return TID 1020 "Person Participant" for ``role``, included with CONTAINS.

    Rows 2 to 6 are HAS PROPERTIES children of row 1. Rows 3 and 5 are
    optional, keyed with ``prefix``; with none, it holds neither.
    """
    rows = (
        []
        if prefix is None
        else [
            _text(
                f"{prefix}TID 1020 row 3",
                "HAS PROPERTIES",
                dose.PERSON_ID,
                f"{SENTINEL}-ID-1",
            ),
            _text(
                f"{prefix}TID 1020 row 5",
                "HAS PROPERTIES",
                dose.ORGANIZATION_NAME,
                f"{SENTINEL} HOSPITAL",
            ),
        ]
    )
    return item(
        "CONTAINS",
        "PNAME",
        dose.PERSON_NAME,
        # TID 1020 row 2, M.
        item("HAS PROPERTIES", "CODE", dose.PERSON_ROLE_IN_PROCEDURE, code=role),
        *_chosen(optional, rows),
        text=PARTICIPANTS_NAME,
    )


def _irradiating_device():
    """Return TID 1021 "Device Participant" for the irradiating device.

    It is :mod:`._synthetic_dose_reports`'s, whose optional row 2, the
    name by which the site manages the device, is included.
    """
    # pylint: disable-next = protected-access
    return dose._irradiating_device()


def _dose_check(optional):
    """Return the items of TID 10015 "CT Dose Check Details" that ``optional`` names.

    Each container is required where the scanner has implemented dose alerts
    (row 1) or notifications (row 10), and both are counted as optional
    here. Each is of an event whose forward estimate exceeded its configured
    DLP value, so that rows 4 and 6, and rows 13 and 15, are required, as is
    row 9, the person who authorised the event; row 18, its counterpart, is
    optional, as are the reasons for proceeding (rows 8 and 17), free text.
    The CTDIvol values are not configured.
    """

    def configured(concept, value):
        return item("CONTAINS", "CODE", concept, code=value)

    def number(concept, value, units):
        return item("CONTAINS", "NUM", concept, number=value, units=units)

    def alerts():
        return item(
            "CONTAINS",
            "CONTAINER",
            DOSE_CHECK_ALERT_DETAILS,
            configured(DLP_ALERT_VALUE_CONFIGURED, YES),
            configured(CTDIVOL_ALERT_VALUE_CONFIGURED, NO),
            number(DLP_ALERT_VALUE, "1000", MILLIGRAY_CENTIMETRE),
            number(ACCUMULATED_DLP_FORWARD_ESTIMATE, "1210", MILLIGRAY_CENTIMETRE),
            *_chosen(
                optional,
                [
                    _text(
                        "TID 10015 row 8",
                        "CONTAINS",
                        REASON_FOR_PROCEEDING,
                        f"{SENTINEL} ALERT REASON",
                    )
                ],
            ),
            _person_participant(IRRADIATION_AUTHORIZING, optional),
        )

    def notifications():
        return item(
            "CONTAINS",
            "CONTAINER",
            DOSE_CHECK_NOTIFICATION_DETAILS,
            configured(DLP_NOTIFICATION_VALUE_CONFIGURED, YES),
            configured(CTDIVOL_NOTIFICATION_VALUE_CONFIGURED, NO),
            number(DLP_NOTIFICATION_VALUE, "500", MILLIGRAY_CENTIMETRE),
            number(DLP_FORWARD_ESTIMATE, "640", MILLIGRAY_CENTIMETRE),
            *_chosen(
                optional,
                [
                    _text(
                        "TID 10015 row 17",
                        "CONTAINS",
                        REASON_FOR_PROCEEDING,
                        f"{SENTINEL} NOTIFICATION REASON",
                    ),
                    (
                        "TID 10015 row 18",
                        lambda: _person_participant(IRRADIATION_AUTHORIZING, ()),
                    ),
                ],
            ),
        )

    return _chosen(
        optional, [("TID 10015 row 1", alerts), ("TID 10015 row 10", notifications)]
    )


def _ct_accumulated(optional):
    """Return TID 10011 row 9, TID 10012 "CT Accumulated Dose Data"."""
    effective = (
        "TID 10012 row 4",
        lambda: item(
            "CONTAINS",
            "NUM",
            CT_EFFECTIVE_DOSE_TOTAL,
            # Row 5, required where row 6 is absent, row 7, M, and row 8,
            # required for a Monte Carlo conversion.
            item(
                "HAS PROPERTIES",
                "TEXT",
                REFERENCE_AUTHORITY,
                text=f"{SENTINEL} AUTHORITY",
            ),
            item("HAS CONCEPT MOD", "CODE", MEASUREMENT_METHOD, code=DLP_TO_E_VIA_MC),
            item(
                "HAS PROPERTIES",
                "TEXT",
                PATIENT_MODEL,
                text=f"{SENTINEL} PATIENT MODEL",
            ),
            number="9.1",
            units=MILLISIEVERT,
        ),
    )
    return item(
        "CONTAINS",
        "CONTAINER",
        CT_ACCUMULATED_DOSE_DATA,
        # Rows 2 and 3, M.
        item(
            "CONTAINS",
            "NUM",
            TOTAL_NUMBER_OF_IRRADIATION_EVENTS,
            number="1",
            units=EVENTS,
        ),
        item(
            "CONTAINS",
            "NUM",
            CT_DOSE_LENGTH_PRODUCT_TOTAL,
            number="640",
            units=MILLIGRAY_CENTIMETRE,
        ),
        *_chosen(
            optional,
            [
                effective,
                _comment("TID 10012 row 12", "ACCUMULATED COMMENT"),
                ("TID 10012 row 13", _irradiating_device),
            ],
        ),
    )


def _ct_acquisition_parameters(optional):
    """Return TID 10013 row 7, the CT Acquisition Parameters of a spiral scan.

    TID 10014 row 8, the Frame of Reference UID, is required where row 6 is
    present, and the two are included together.
    """
    scanned = [
        item("CONTAINS", "NUM", SCANNING_LENGTH, number="412", units=MILLIMETRE),
        *(
            [
                item(
                    "CONTAINS",
                    "NUM",
                    TOP_Z_LOCATION_OF_SCANNING_LENGTH,
                    number="-35",
                    units=MILLIMETRE,
                ),
                item(
                    "CONTAINS",
                    "UIDREF",
                    FRAME_OF_REFERENCE_UID,
                    text=CT_FRAME_OF_REFERENCE,
                ),
            ]
            if "TID 10014 row 8" in optional
            else []
        ),
    ]
    source = item(
        "CONTAINS",
        "CONTAINER",
        CT_X_RAY_SOURCE_PARAMETERS,
        # Rows 15 to 19, M or MC and required for a spiral scan.
        item("CONTAINS", "TEXT", IDENTIFICATION_OF_THE_X_RAY_SOURCE, text="A"),
        item("CONTAINS", "NUM", KVP, number="120", units=KILOVOLT),
        item(
            "CONTAINS",
            "NUM",
            MAXIMUM_X_RAY_TUBE_CURRENT,
            number="380",
            units=MILLIAMPERE,
        ),
        item("CONTAINS", "NUM", X_RAY_TUBE_CURRENT, number="210", units=MILLIAMPERE),
        item(
            "CONTAINS", "NUM", EXPOSURE_TIME_PER_ROTATION, number="0.5", units=SECONDS
        ),
    )
    return item(
        "CONTAINS",
        "CONTAINER",
        CT_ACQUISITION_PARAMETERS,
        # Rows 8 to 14, M or MC and required for a spiral scan; row 9
        # includes TID 10014, whose rows are not nested.
        item("CONTAINS", "NUM", EXPOSURE_TIME, number="9.6", units=SECONDS),
        *scanned,
        item(
            "CONTAINS",
            "NUM",
            NOMINAL_SINGLE_COLLIMATION_WIDTH,
            number="0.625",
            units=MILLIMETRE,
        ),
        item(
            "CONTAINS",
            "NUM",
            NOMINAL_TOTAL_COLLIMATION_WIDTH,
            number="40",
            units=MILLIMETRE,
        ),
        item("CONTAINS", "NUM", PITCH_FACTOR, number="0.984", units=RATIO),
        item(
            "CONTAINS", "NUM", NUMBER_OF_X_RAY_SOURCES, number="1", units=X_RAY_SOURCES
        ),
        source,
    )


def _ct_acquisition(optional):
    """Return TID 10011 row 10, TID 10013 "CT Irradiation Event Data"."""
    repeated = (
        "TID 10013 row 6d",
        lambda: item(
            "CONTAINS",
            "CODE",
            IS_REPEATED_ACQUISITION,
            # Row 6e, required for a repeat, and row 6e1, the event that it
            # repeats.
            item(
                "HAS CONCEPT MOD",
                "CODE",
                REASON_FOR_REPEATING_ACQUISITION,
                code=PATIENT_MOTION,
            ),
            item(
                "HAS PROPERTIES",
                "UIDREF",
                IRRADIATION_EVENT_UID,
                text=CT_REPEATED_EVENT_UID,
            ),
            code=YES,
        ),
    )
    dose_ = item(
        "CONTAINS",
        "CONTAINER",
        CT_DOSE,
        # Rows 22, 23, 26, and 35, M; row 35 includes TID 10015.
        item("CONTAINS", "NUM", MEAN_CTDIVOL, number="11.3", units=MILLIGRAY),
        item("CONTAINS", "CODE", CTDIW_PHANTOM_TYPE, code=BODY_PHANTOM),
        item("CONTAINS", "NUM", DLP, number="640", units=MILLIGRAY_CENTIMETRE),
        *_dose_check(optional),
    )
    return item(
        "CONTAINS",
        "CONTAINER",
        CT_ACQUISITION,
        *_chosen(
            optional,
            [
                _text(
                    "TID 10013 row 2",
                    "CONTAINS",
                    ACQUISITION_PROTOCOL,
                    f"{SENTINEL} CHEST CT",
                )
            ],
        ),
        # Rows 3, 4, and 6, M.
        item("CONTAINS", "CODE", TARGET_REGION, code=CHEST),
        item("CONTAINS", "CODE", CT_ACQUISITION_TYPE, code=SPIRAL_ACQUISITION),
        item(
            "CONTAINS",
            "UIDREF",
            IRRADIATION_EVENT_UID,
            text=CT_IRRADIATION_EVENT_UID,
        ),
        *_chosen(
            optional,
            [
                _text(
                    "TID 10013 row 6b",
                    "CONTAINS",
                    IRRADIATION_EVENT_LABEL,
                    f"{SENTINEL} LABEL",
                ),
                repeated,
                (
                    "TID 10013 row 6f",
                    lambda: item(
                        "CONTAINS", "DATETIME", DATETIME_STARTED, text=CT_EVENT_START
                    ),
                ),
            ],
        ),
        # Rows 7 and 21, M, and required for a spiral scan.
        _ct_acquisition_parameters(optional),
        dose_,
        *_chosen(
            optional,
            [
                _comment("TID 10013 row 37", "EVENT COMMENT"),
                (
                    "TID 10013 row 38",
                    lambda: _person_participant(
                        IRRADIATION_ADMINISTERING, optional, "TID 10013 row 38 "
                    ),
                ),
                ("TID 10013 row 39", _irradiating_device),
            ],
        ),
    )


# The optional rows of the CT Radiation Dose report, by template and row. A
# row whose items have optional rows of their own, such as a Person
# Participant's, prefixes their keys with its own.
CT_OPTIONAL_ROWS = (
    *DEVICE_OBSERVER_ROWS,
    "TID 10012 row 4",
    "TID 10012 row 12",
    "TID 10012 row 13",
    "TID 10013 row 2",
    "TID 10013 row 6b",
    "TID 10013 row 6d",
    "TID 10013 row 6f",
    "TID 10014 row 8",
    "TID 10015 row 1",
    "TID 10015 row 8",
    "TID 10015 row 10",
    "TID 10015 row 17",
    "TID 10015 row 18",
    "TID 10013 row 37",
    "TID 10013 row 38",
    "TID 10013 row 38 TID 1020 row 3",
    "TID 10013 row 38 TID 1020 row 5",
    "TID 10013 row 39",
    "TID 10011 row 11",
    "TID 10011 row 13",
)


def ct_tree(optional=CT_OPTIONAL_ROWS):
    """Return the root of a CT Radiation Dose report's tree, TID 10011.

    The report is of one spiral scan of the chest, whose dose was collected
    automatically (TID 10011 row 12) by the scanner, which recorded it, so
    that TID 10011 rows 1 to 10 and 12, TID 10012 rows 1 to 3, and TID 10013
    rows 1, 3, 4, 6, 7 to 19, 21 to 23, 26, and 35 are required, with TID 10014
    row 1. TID 10015, which TID 10013 row 35 includes, requires its rows only of
    a scanner that implements dose checks, as :func:`_dose_check` says. Of the rows
    required where they are included, it leaves out TID 10012 row 3a, the
    subtotals for events whose DLP used different phantoms, which carry
    codes and numbers.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`CT_OPTIONAL_ROWS`. The
        irradiating device (``"TID 10012 row 13"`` and ``"TID 10013 row
        39"``) is required only where it is not the recording device, and
        the dose check containers (``"TID 10015 row 1"`` and ``"TID 10015
        row 10"``) only where the scanner implements them, so each is
        counted as optional here. Defaults to all of them.
    """
    _checked(optional, CT_OPTIONAL_ROWS)
    return item(
        None,
        "CONTAINER",
        X_RAY_RADIATION_DOSE_REPORT,
        # Rows 2 and 3, M.
        _procedure(COMPUTED_TOMOGRAPHY_X_RAY),
        # Row 4, TID 1002, for a device.
        *_device_observer(CT_DEVICE_OBSERVER_UID, optional),
        # Rows 5 to 8, M.
        item("HAS OBS CONTEXT", "DATETIME", START_OF_X_RAY_IRRADIATION, text=CT_START),
        item("HAS OBS CONTEXT", "DATETIME", END_OF_X_RAY_IRRADIATION, text=CT_END),
        item(
            "HAS OBS CONTEXT",
            "CODE",
            SCOPE_OF_ACCUMULATION,
            item("HAS PROPERTIES", "UIDREF", STUDY_INSTANCE_UID, text=STUDY),
            code=STUDY_SCOPE,
        ),
        # Rows 9 and 10, M.
        _ct_accumulated(optional),
        _ct_acquisition(optional),
        *_chosen(optional, [_comment("TID 10011 row 11", "REPORT COMMENT")]),
        # Row 12, M.
        item(
            "CONTAINS",
            "CODE",
            SOURCE_OF_DOSE_INFORMATION,
            code=AUTOMATED_DATA_COLLECTION,
        ),
        *_chosen(
            optional,
            [
                (
                    "TID 10011 row 13",
                    lambda: _person_participant(IRRADIATION_AUTHORIZING, ()),
                )
            ],
        ),
    )


def _accumulated(optional):
    """Return TID 10040 row 7, TID 10041 "Accumulated Dose Data"."""
    calibration = (
        "TID 10041 row 3",
        lambda: item(
            "CONTAINS",
            "CONTAINER",
            CALIBRATION,
            # Rows 4 to 8, M.
            item("HAS CONCEPT MOD", "CODE", DOSE_MEASUREMENT_DEVICE, code=DOSIMETER),
            item(
                "CONTAINS",
                "DATETIME",
                CALIBRATION_DATETIME_CONCEPT,
                text=CALIBRATION_DATETIME,
            ),
            item("CONTAINS", "NUM", CALIBRATION_FACTOR, number="1.02", units=NO_UNITS),
            item("CONTAINS", "NUM", CALIBRATION_UNCERTAINTY, number="5", units=PERCENT),
            item(
                "CONTAINS",
                "TEXT",
                CALIBRATION_RESPONSIBLE_PARTY,
                text=f"{SENTINEL} PHYSICIST",
            ),
            *_chosen(
                optional,
                [
                    _text(
                        "TID 10041 row 9",
                        "CONTAINS",
                        CALIBRATION_PROTOCOL,
                        f"{SENTINEL} PROTOCOL",
                    ),
                    _text(
                        "TID 10041 row 9b",
                        "CONTAINS",
                        CALIBRATION_INTENDED_ACQUISITION_PROTOCOL,
                        f"{SENTINEL} INTENDED PROTOCOL",
                    ),
                ],
            ),
        ),
    )
    reference_point = (
        "TID 10041 row 20",
        lambda: item(
            "CONTAINS",
            "CONTAINER",
            REFERENCE_POINT_DOSIMETRY,
            # Row 21, as free text, XOR row 22.
            item(
                "CONTAINS",
                "TEXT",
                REFERENCE_POINT_DEFINITION,
                text=f"{SENTINEL} REFERENCE POINT",
            ),
        ),
    )
    return item(
        "CONTAINS",
        "CONTAINER",
        ACCUMULATED_DOSE_DATA,
        # Row 2, M.
        item("CONTAINS", "TEXT", IDENTIFICATION_OF_THE_X_RAY_SOURCE, text="A"),
        *_chosen(
            optional,
            [
                calibration,
                ("TID 10041 row 10", _irradiating_device),
                reference_point,
                _comment("TID 10041 row 28", "ACCUMULATED COMMENT"),
            ],
        ),
    )


def _event_summary(optional):
    """Return TID 10040 row 8, TID 10042 "Irradiation Event Summary Data"."""
    repeated = (
        "TID 10042 row 18",
        lambda: item(
            "CONTAINS",
            "CODE",
            IS_REPEATED_ACQUISITION,
            # Row 19, required for a repeat, and row 20, the event that it
            # repeats.
            item(
                "HAS CONCEPT MOD",
                "CODE",
                REASON_FOR_REPEATING_ACQUISITION,
                code=PATIENT_MOTION,
            ),
            item(
                "CONTAINS",
                "UIDREF",
                IRRADIATION_EVENT_UID,
                text=ENHANCED_REPEATED_EVENT_UID,
            ),
            code=YES,
        ),
    )
    return item(
        "CONTAINS",
        "CONTAINER",
        IRRADIATION_EVENT_SUMMARY_DATA,
        # Rows 2 to 5, M.
        item(
            "CONTAINS",
            "UIDREF",
            IRRADIATION_EVENT_UID,
            text=ENHANCED_IRRADIATION_EVENT_UID,
        ),
        item("CONTAINS", "DATETIME", DATETIME_STARTED, text=ENHANCED_EVENT_START),
        item("CONTAINS", "DATETIME", DATETIME_ENDED, text=ENHANCED_EVENT_END),
        item("CONTAINS", "TEXT", IDENTIFICATION_OF_THE_X_RAY_SOURCE, text="A"),
        *_chosen(
            optional,
            [
                _text(
                    "TID 10042 row 6",
                    "CONTAINS",
                    IRRADIATION_EVENT_LABEL,
                    f"{SENTINEL} LABEL",
                )
            ],
        ),
        # Row 8, M.
        item("CONTAINS", "CODE", IRRADIATION_EVENT_TYPE, code=STATIONARY_ACQUISITION),
        *_chosen(
            optional,
            [
                (
                    "TID 10042 row 15",
                    lambda: item(
                        "CONTAINS",
                        "IMAGE",
                        ACQUIRED_IMAGE_CONCEPT,
                        sop_class=DIGITAL_X_RAY_FOR_PRESENTATION,
                        sop_instance=ACQUIRED_IMAGE[1],
                    ),
                ),
                repeated,
                (
                    "TID 10042 row 44",
                    lambda: item(
                        "CONTAINS",
                        "UIDREF",
                        FRAME_OF_REFERENCE_UID,
                        text=ENHANCED_FRAME_OF_REFERENCE,
                    ),
                ),
                _comment("TID 10042 row 45", "EVENT COMMENT"),
                (
                    "TID 10042 row 46",
                    lambda: _person_participant(
                        IRRADIATION_ADMINISTERING, optional, "TID 10042 row 46 "
                    ),
                ),
                ("TID 10042 row 47", _irradiating_device),
            ],
        ),
    )


def _irradiation_details(optional):
    """Return TID 10040 row 9, TID 10043 "Irradiation Details", in part.

    It holds rows 1 to 5, M, and the optional row 6, and leaves out the
    templates that rows 7, 8, and 11 to 14 require, TID 10044, 10045, and
    10048 to 10051, as the docstring of :func:`enhanced_tree` says.
    """
    return item(
        "CONTAINS",
        "CONTAINER",
        IRRADIATION_DETAILS,
        item("CONTAINS", "DATETIME", DATETIME_STARTED, text=ENHANCED_DETAILS_START),
        item("CONTAINS", "DATETIME", DATETIME_ENDED, text=ENHANCED_DETAILS_END),
        item(
            "CONTAINS",
            "UIDREF",
            FRAME_OF_REFERENCE_UID,
            text=RDSR_FRAME_OF_REFERENCE,
        ),
        item("CONTAINS", "CODE", RDSR_FRAME_OF_REFERENCE_ORIGIN, code=EQUIPMENT_ORIGIN),
        *_chosen(
            optional,
            [
                _text(
                    "TID 10043 row 6",
                    "CONTAINS",
                    RDSR_FRAME_OF_REFERENCE_DESCRIPTION,
                    f"{SENTINEL} ROOM AXES",
                )
            ],
        ),
    )


# The optional rows of the Enhanced X-Ray Radiation Dose report, keyed as
# CT_OPTIONAL_ROWS are.
ENHANCED_OPTIONAL_ROWS = (
    *DEVICE_OBSERVER_ROWS,
    "TID 10040 row 7",
    "TID 10041 row 3",
    "TID 10041 row 9",
    "TID 10041 row 9b",
    "TID 10041 row 10",
    "TID 10041 row 20",
    "TID 10041 row 28",
    "TID 10042 row 6",
    "TID 10042 row 15",
    "TID 10042 row 18",
    "TID 10042 row 44",
    "TID 10042 row 45",
    "TID 10042 row 46",
    "TID 10042 row 46 TID 1020 row 3",
    "TID 10042 row 46 TID 1020 row 5",
    "TID 10042 row 47",
    "TID 10043 row 6",
    "TID 10040 row 10",
    "TID 10040 row 11",
)


def enhanced_tree(optional=ENHANCED_OPTIONAL_ROWS):
    """Return the root of an Enhanced X-Ray Radiation Dose report's tree, TID 10040.

    The report is of one stationary radiograph whose dose was collected
    automatically (TID 10040 row 12) by the device that recorded it, so
    that TID 10040 rows 1 to 6, 8, 9, and 12, TID 10042 rows 1 to 5 and 8,
    and TID 10043 rows 1 to 5 are required. Of the rows required where they
    are included, it leaves out TID 10043 rows 7, 8, and 11 to 14, TID
    10044 "Radiation Source Characteristics", 10045 "Radiation Technique",
    10048 "Radiation Output", 10049 "Radiation Field Area", 10050 "X-Ray
    Source Reference Coordinate System", and 10051 "Beam Position", and the
    filtration and attenuator templates that rows 9, 10, 15, and 16 include
    where they apply. Each of them holds a DateTime Started and a DateTime
    Ended, as TID 10042 and 10043 do here, and an Identification of the
    X-Ray Source but TID 10047's and 10052's, and most hold values of the
    Value Types TABLE or SCOORD3D, which these trees do not test; TID 10051
    and 10052 can also hold X-Ray Attenuator Model Data, a reference.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`ENHANCED_OPTIONAL_ROWS`.
        A Calibration (``"TID 10041 row 3"``) and the irradiating device
        (``"TID 10041 row 10"`` and ``"TID 10042 row 47"``) are each
        required only where they apply, and are counted as optional here;
        the rows of TID 10041 are included only with TID 10040 row 7, which
        holds them. Defaults to all of them.
    """
    _checked(optional, ENHANCED_OPTIONAL_ROWS)
    return item(
        None,
        "CONTAINER",
        X_RAY_RADIATION_DOSE_REPORT,
        # Rows 2 to 4, M.
        _language(),
        _procedure(PLAIN_RADIOGRAPHY),
        # Row 5, TID 1002, for a device.
        *_device_observer(ENHANCED_DEVICE_OBSERVER_UID, optional),
        # Row 6, M.
        item("HAS OBS CONTEXT", "CODE", SCOPE_OF_ACCUMULATION, code=STUDY_SCOPE),
        *_chosen(optional, [("TID 10040 row 7", lambda: _accumulated(optional))]),
        # Rows 8 and 9, M.
        _event_summary(optional),
        _irradiation_details(optional),
        *_chosen(
            optional,
            [
                _comment("TID 10040 row 10", "REPORT COMMENT"),
                (
                    "TID 10040 row 11",
                    lambda: _person_participant(IRRADIATION_AUTHORIZING, ()),
                ),
            ],
        ),
        # Row 12, M.
        item(
            "CONTAINS",
            "CODE",
            SOURCE_OF_DOSE_INFORMATION,
            code=AUTOMATED_DATA_COLLECTION,
        ),
    )


def _methodology(optional):
    """Return TID 10031 row 4, TID 10033 "Radiation Dose Estimate Methodology".

    The estimate used the CT Radiation Dose report of :func:`ct_dose_report`
    (row 2), with an anthropomorphic model for adults, whose minimum age
    row 14 gives, and an analytical method. Rows 21 to 39, the model's
    registration and the beam attenuators, are left out: they are required
    only where the estimate used them, and hold free text, codes, numbers,
    and references, as the rows here do.
    """
    used = item(
        "CONTAINS",
        "COMPOSITE",
        SR_INSTANCE_USED,
        *_chosen(
            optional,
            [
                (
                    "TID 10033 row 3",
                    lambda: item(
                        "HAS OBS CONTEXT",
                        "COMPOSITE",
                        SPATIAL_FIDUCIALS_CONCEPT,
                        sop_class=SPATIAL_FIDUCIALS_STORAGE,
                        sop_instance=SPATIAL_FIDUCIALS[1],
                    ),
                ),
                (
                    "TID 10033 row 4",
                    lambda: item(
                        "HAS PROPERTIES",
                        "UIDREF",
                        EVENT_UID_USED,
                        text=CT_IRRADIATION_EVENT_UID,
                    ),
                ),
            ],
        ),
        sop_class=X_RAY_RADIATION_DOSE_SR,
        sop_instance=CT_REPORT[1],
    )
    model = item(
        "CONTAINS",
        "CONTAINER",
        PATIENT_RADIATION_DOSE_MODEL,
        # Rows 6 and 7, M.
        item("CONTAINS", "CODE", PATIENT_MODEL_TYPE, code=ANTHROPOMORPHIC_MODEL),
        item(
            "CONTAINS",
            "CODE",
            RADIATION_TRANSPORT_MODEL_TYPE,
            code=VOXELIZED_TRANSPORT_MODEL,
        ),
        *_chosen(
            optional,
            [
                (
                    "TID 10033 row 10",
                    lambda: item(
                        "CONTAINS",
                        "UIDREF",
                        PATIENT_RADIATION_DOSE_MODEL_DATA,
                        text=PATIENT_MODEL_DATA_UID,
                    ),
                ),
                _text(
                    "TID 10033 row 11",
                    "CONTAINS",
                    PATIENT_RADIATION_DOSE_MODEL_REFERENCE,
                    f"{SENTINEL} MODEL REFERENCE",
                ),
                _comment("TID 10033 row 12", "MODEL COMMENT"),
            ],
        ),
        # Rows 13 and 14, required for a model that sets a minimum age.
        item(
            "CONTAINS",
            "CONTAINER",
            PATIENT_MODEL_DEMOGRAPHICS,
            item("CONTAINS", "NUM", MODEL_MINIMUM_AGE, number="18", units=YEAR),
        ),
    )
    method = item(
        "CONTAINS",
        "CONTAINER",
        RADIATION_DOSE_ESTIMATE_METHOD,
        # Row 41, M.
        item(
            "CONTAINS",
            "CODE",
            RADIATION_DOSE_ESTIMATE_METHOD_TYPE,
            code=ANALYTICAL_ALGORITHM,
        ),
        *_chosen(
            optional,
            [
                _text(
                    "TID 10033 row 43",
                    "CONTAINS",
                    RADIATION_DOSE_ESTIMATE_METHOD_REFERENCE,
                    f"{SENTINEL} METHOD REFERENCE",
                )
            ],
        ),
    )
    return item(
        "CONTAINS",
        "CONTAINER",
        RADIATION_DOSE_ESTIMATE_METHODOLOGY,
        used,
        model,
        method,
    )


def _representation(optional):
    """Return TID 10031 row 5, TID 10032, a skin dose map stored as an RT Dose."""
    return item(
        "CONTAINS",
        "CONTAINER",
        RADIATION_DOSE_ESTIMATE_REPRESENTATION,
        # Rows 2, 4 (XOR row 3), and 5, M.
        item("CONTAINS", "CODE", DISTRIBUTION_REPRESENTATION, code=SKIN_DOSE_MAP),
        item(
            "CONTAINS",
            "COMPOSITE",
            RADIATION_DOSE_REPRESENTATION_DATA,
            sop_class=RT_DOSE_STORAGE,
            sop_instance=DOSE_MAP[1],
        ),
        item("CONTAINS", "CODE", ORGAN, code=ENTIRE_BODY),
        *_chosen(optional, [_comment("TID 10032 row 7", "REPRESENTATION COMMENT")]),
    )


def _organ_dose(optional):
    """Return TID 10031 row 6, the Organ Dose Information for the entire body."""
    uncertainty = (
        "TID 10031 row 11",
        lambda: item(
            "HAS PROPERTIES",
            "NUM",
            MEASUREMENT_UNCERTAINTY,
            *_chosen(
                optional,
                [
                    _text(
                        "TID 10031 row 12",
                        "HAS PROPERTIES",
                        REFERENCE_TO_UNCERTAINTY_DETERMINATION_METHOD,
                        f"{SENTINEL} UNCERTAINTY METHOD",
                    )
                ],
            ),
            number="0.4",
            units=MILLIGRAY,
        ),
    )
    return item(
        "CONTAINS",
        "CONTAINER",
        ORGAN_DOSE_INFORMATION,
        # Rows 7 and 10, M.
        item("CONTAINS", "CODE", ORGAN, code=ENTIRE_BODY),
        *_chosen(optional, [_comment("TID 10031 row 9", "ORGAN COMMENT")]),
        item(
            "CONTAINS",
            "NUM",
            MEAN_ABSORBED_RADIATION_DOSE,
            *_chosen(optional, [uncertainty]),
            number="3.2",
            units=MILLIGRAY,
        ),
    )


# The optional rows of the Patient Radiation Dose report, keyed as
# CT_OPTIONAL_ROWS are.
PATIENT_OPTIONAL_ROWS = (
    *DEVICE_OBSERVER_ROWS,
    "TID 10031 row 3",
    "TID 10033 row 3",
    "TID 10033 row 4",
    "TID 10033 row 10",
    "TID 10033 row 11",
    "TID 10033 row 12",
    "TID 10033 row 43",
    "TID 10031 row 5",
    "TID 10032 row 7",
    "TID 10031 row 9",
    "TID 10031 row 11",
    "TID 10031 row 12",
    "TID 10030 row 5",
)


def patient_tree(optional=PATIENT_OPTIONAL_ROWS):
    """Return the root of a Patient Radiation Dose report's tree, TID 10030.

    The report gives one estimate, the mean dose to the entire body,
    observed by the device, an application, that estimated it, so that TID
    10030 rows 1 to 4, TID 10031 rows 1, 2, 4, 6, 7, and 10, and TID 10033
    rows 1, 2, 5 to 7, 13, 40, and 41 are required, with the rows that
    :func:`_methodology` names. The model's data (``"TID 10033 row 10"``),
    one of rows 8 to 10, is required only where the model has data of its
    own, and is counted as optional here, as are the events used (``"TID
    10033 row 4"``), required where the estimate left some events of the
    report out.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`PATIENT_OPTIONAL_ROWS`.
        Defaults to all of them.
    """
    _checked(optional, PATIENT_OPTIONAL_ROWS)
    estimate = item(
        "CONTAINS",
        "CONTAINER",
        RADIATION_DOSE_ESTIMATE,
        # Row 2, M.
        item(
            "HAS CONCEPT MOD",
            "TEXT",
            RADIATION_DOSE_ESTIMATE_NAME,
            text=f"{SENTINEL} ESTIMATE",
        ),
        *_chosen(optional, [_comment("TID 10031 row 3", "ESTIMATE COMMENT")]),
        # Row 4, M.
        _methodology(optional),
        *_chosen(optional, [("TID 10031 row 5", lambda: _representation(optional))]),
        # Row 6, M.
        _organ_dose(optional),
    )
    return item(
        None,
        "CONTAINER",
        PATIENT_RADIATION_DOSE_REPORT,
        # Row 2, M.
        _language(),
        # Row 3, TID 1002, for a device.
        *_device_observer(PATIENT_DEVICE_OBSERVER_UID, optional),
        # Row 4, M.
        estimate,
        *_chosen(optional, [_comment("TID 10030 row 5", "REPORT COMMENT")]),
    )


def _report(identity, tree, verified, references=()):
    """Return a report whose SR Document Content Module holds ``tree``.

    ``identity`` gives its SOP Class, its Series and SOP Instance UIDs, and
    its root template, and ``references`` the instances that its tree
    references, for its evidence. The header is that of
    :mod:`._synthetic_structured_reports`, and ``verified`` is as there.
    """
    # pylint: disable-next = protected-access
    return general._report(
        identity,
        tree,
        verified,
        evidence=_evidence(*references) if references else None,
    )


def ct_dose_report(optional=CT_OPTIONAL_ROWS, *, verified=False):
    """Return an X-Ray Radiation Dose SR whose tree is :func:`ct_tree`.

    ``verified`` gives it the Verification Flag VERIFIED, with a Verifying
    Observer Sequence, rather than UNVERIFIED.
    """
    return _report(
        (X_RAY_RADIATION_DOSE_SR, CT_REPORT, "10011"), ct_tree(optional), verified
    )


def enhanced_dose_report(optional=ENHANCED_OPTIONAL_ROWS, *, verified=False):
    """Return an Enhanced X-Ray Radiation Dose SR whose tree is :func:`enhanced_tree`.

    ``verified`` is as for :func:`ct_dose_report`.
    """
    references = (
        [(DIGITAL_X_RAY_FOR_PRESENTATION, ACQUIRED_IMAGE)]
        if "TID 10042 row 15" in optional
        else []
    )
    return _report(
        (ENHANCED_X_RAY_RADIATION_DOSE_SR, ENHANCED_REPORT, "10040"),
        enhanced_tree(optional),
        verified,
        references,
    )


def patient_dose_report(optional=PATIENT_OPTIONAL_ROWS, *, verified=False):
    """Return a Patient Radiation Dose SR whose tree is :func:`patient_tree`.

    ``verified`` is as for :func:`ct_dose_report`.
    """
    references = [
        (X_RAY_RADIATION_DOSE_SR, CT_REPORT),
        *(
            [(SPATIAL_FIDUCIALS_STORAGE, SPATIAL_FIDUCIALS)]
            if "TID 10033 row 3" in optional
            else []
        ),
        *([(RT_DOSE_STORAGE, DOSE_MAP)] if "TID 10031 row 5" in optional else []),
    ]
    return _report(
        (PATIENT_RADIATION_DOSE_SR, PATIENT_REPORT, "10030"),
        patient_tree(optional),
        verified,
        references,
    )
