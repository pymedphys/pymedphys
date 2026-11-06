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

"""Synthetic Radiation Dose Structured Reports, built in code.

:func:`x_ray_dose_report` gives an X-Ray Radiation Dose SR, whose content
tree follows TID 10001 "Projection X-Ray Radiation Dose", and
:func:`radiopharmaceutical_dose_report` a Radiopharmaceutical Radiation Dose
SR, whose tree follows TID 10021 "Radiopharmaceutical Radiation Dose". Each
content item's relationship, Value Type, and concept name is a row of a
template of DICOM PS3.16 2026d, cited beside it, and each coded value is one
of the context group that the row names. Code meanings are those of PS3.16
Annex D for DCM codes, and those the templates and context groups give for
the others. The codes that the synthetic corpus's reports also use, and
:func:`item`, which builds a content item, come from
:mod:`~pymedphys._dicom.deidentify.synthetic_content_trees`.

Each tree is partial: it holds the rows that its templates require where
they are included, apart from the templates that the builder's docstring
names as left out, and the optional rows that carry identifying values:
names and identifiers of people, devices, and organisations, free text,
dates, and UIDs. So it does not conform to its templates in full, and the
templates left out can hold identifying values of their own, such as free
text and image references, which these trees do not test. The optional rows are keyed by their template
and row, such as ``"TID 1004 row 2"``, so that a test can build a report
with any of them. The header carries identifying values too: the
institution, station, and device serial number, the referring physician,
and, in a report whose Verification Flag is VERIFIED, the verifying observer
and organisation.

Text that must never reach a written file under the Basic Profile carries
``SENTINEL``. Every UID is invented under ``2.25.``, the patient is
fictitious, and no value comes from a real report.
"""

from pymedphys._imports import pydicom

from pymedphys._dicom.deidentify.synthetic_content_trees import (
    ACCUMULATED_X_RAY_DOSE_DATA,
    ACQUISITION_PLANE,
    ADMINISTERED_ACTIVITY,
    ADMINISTRATION_EVENT_UID_CONCEPT,
    ASSOCIATED_PROCEDURE,
    AUTOMATED_DATA_COLLECTION,
    CHEST,
    Code,
    DATETIME_STARTED,
    DEVICE,
    DEVICE_OBSERVER_UID_CONCEPT,
    DIAGNOSTIC_INTENT,
    DOSE_AREA_PRODUCT,
    FDG,
    FLUORINE_18,
    GRAY_SQUARE_METRE,
    HAS_INTENT,
    INTRAVENOUS_ROUTE,
    IRRADIATION_ADMINISTERING,
    IRRADIATION_EVENT_TYPE,
    IRRADIATION_EVENT_UID_CONCEPT,
    IRRADIATION_EVENT_X_RAY_DATA,
    MEGABECQUEREL,
    OBSERVER_TYPE,
    PERSON_NAME,
    PERSON_ROLE_IN_PROCEDURE,
    PROCEDURE_REPORTED,
    PROJECTION_X_RAY,
    RADIONUCLIDE,
    RADIONUCLIDE_HALF_LIFE,
    RADIOPHARMACEUTICAL_ADMINISTRATION,
    RADIOPHARMACEUTICAL_AGENT,
    RADIOPHARMACEUTICAL_RADIATION_DOSE_REPORT,
    ROUTE_OF_ADMINISTRATION,
    SCOPE_OF_ACCUMULATION,
    SECONDS,
    SINGLE_PLANE,
    SITE_OF,
    SOURCE_OF_DOSE_INFORMATION,
    START_DATETIME,
    STATIONARY_ACQUISITION,
    STUDY_INSTANCE_UID,
    STUDY_SCOPE,
    TARGET_REGION,
    TUMOR_LOCALIZATION,
    VIA_ARM_VEIN,
    X_RAY_RADIATION_DOSE_REPORT,
    item,
)

X_RAY_RADIATION_DOSE_SR = "1.2.840.10008.5.1.4.1.1.88.67"
RADIOPHARMACEUTICAL_RADIATION_DOSE_SR = "1.2.840.10008.5.1.4.1.1.88.68"
X_RAY_IOD = "X-Ray Radiation Dose SR"
RADIOPHARMACEUTICAL_IOD = "Radiopharmaceutical Radiation Dose SR"

SENTINEL = "SENTINEL"
PATIENT_ID = "SYNTHETIC-7Q2K"
PATIENTS_NAME = "FICTITIOUS^PERSON"
STUDY = "2.25.7100"
X_RAY_SERIES = "2.25.7200"
X_RAY_REPORT = "2.25.7201"
RADIOPHARMACEUTICAL_SERIES = "2.25.7300"
RADIOPHARMACEUTICAL_REPORT = "2.25.7301"
# The UIDs that content items carry.
DEVICE_OBSERVER_UID = "2.25.7401"
IRRADIATING_DEVICE_UID = "2.25.7402"
IRRADIATION_EVENT_UID = "2.25.7403"
ADMINISTRATION_EVENT_UID = "2.25.7404"
DOSE_CALIBRATOR_UID = "2.25.7405"
UIDS = (
    DEVICE_OBSERVER_UID,
    IRRADIATING_DEVICE_UID,
    IRRADIATION_EVENT_UID,
    ADMINISTRATION_EVENT_UID,
    DOSE_CALIBRATOR_UID,
)
# The dates and datetimes that the reports carry, none of which a modified or
# dummy value repeats.
STUDY_DATE = "20260314"
CONTENT_DATE = "20260316"
VERIFICATION_DATETIME = "20260317101500"
CALIBRATION_DATETIME = "20250611083000"
IRRADIATION_DATETIME = "20260314093000"
ADMINISTRATION_START = "20260314110500"
ADMINISTRATION_STOP = "20260314110700"
DATES = (
    STUDY_DATE,
    CONTENT_DATE,
    VERIFICATION_DATETIME,
    CALIBRATION_DATETIME,
    IRRADIATION_DATETIME,
    ADMINISTRATION_START,
    ADMINISTRATION_STOP,
)


# Concept names, by the first template row that uses them.
COMMENT = Code("121106", "DCM", "Comment")
# TID 1002, 1003, and 1004.
PERSON_OBSERVER_NAME = Code("121008", "DCM", "Person Observer Name")
PERSON_OBSERVERS_ORGANIZATION_NAME = Code(
    "121009", "DCM", "Person Observer's Organization Name"
)
DEVICE_OBSERVER_NAME = Code("121013", "DCM", "Device Observer Name")
DEVICE_OBSERVER_MANUFACTURER = Code("121014", "DCM", "Device Observer Manufacturer")
DEVICE_OBSERVER_MODEL_NAME = Code("121015", "DCM", "Device Observer Model Name")
DEVICE_OBSERVER_SERIAL_NUMBER = Code("121016", "DCM", "Device Observer Serial Number")
DEVICE_OBSERVER_PHYSICAL_LOCATION = Code(
    "121017", "DCM", "Device Observer Physical Location During Observation"
)
# TID 1020 and 1021.
PERSON_ID = Code("113871", "DCM", "Person ID")
ORGANIZATION_NAME = Code("113873", "DCM", "Organization Name")
DEVICE_ROLE_IN_PROCEDURE = Code("113876", "DCM", "Device Role in Procedure")
DEVICE_NAME = Code("113877", "DCM", "Device Name")
DEVICE_MANUFACTURER = Code("113878", "DCM", "Device Manufacturer")
DEVICE_MODEL_NAME = Code("113879", "DCM", "Device Model Name")
DEVICE_SERIAL_NUMBER = Code("113880", "DCM", "Device Serial Number")
# TID 10002 and 10003.
CALIBRATION = Code("122505", "DCM", "Calibration")
DOSE_MEASUREMENT_DEVICE = Code("113794", "DCM", "Dose Measurement Device")
CALIBRATION_DATETIME_CONCEPT = Code("113723", "DCM", "Calibration DateTime")
CALIBRATION_FACTOR = Code("122322", "DCM", "Calibration Factor")
CALIBRATION_UNCERTAINTY = Code("113763", "DCM", "Calibration Uncertainty")
CALIBRATION_RESPONSIBLE_PARTY = Code("113724", "DCM", "Calibration Responsible Party")
CALIBRATION_PROTOCOL = Code("113720", "DCM", "Calibration Protocol")
IRRADIATION_EVENT_LABEL = Code("113605", "DCM", "Irradiation Event Label")
ACQUISITION_PROTOCOL = Code("125203", "DCM", "Acquisition Protocol")
# TID 10021, 10022, and 10024.
STOP_DATETIME = Code("123004", "DCM", "Radiopharmaceutical Stop DateTime")
PRE_ADMINISTRATION_ACTIVITY = Code(
    "113508", "DCM", "Pre-Administration Measured Activity"
)
ACTIVITY_MEASUREMENT_DEVICE = Code("113540", "DCM", "Activity Measurement Device")
BRAND_NAME = Code("111529", "DCM", "Brand Name")
DISPENSE_UNIT_IDENTIFIER = Code(
    "113511", "DCM", "Radiopharmaceutical Dispense Unit Identifier"
)
LOT_IDENTIFIER = Code("113512", "DCM", "Radiopharmaceutical Lot Identifier")
PRESCRIPTION_IDENTIFIER = Code("113516", "DCM", "Prescription Identifier")
PATIENT_CHARACTERISTICS = Code("121118", "DCM", "Patient Characteristics")
SUBJECT_AGE = Code("121033", "DCM", "Subject Age")
SUBJECT_SEX = Code("121032", "DCM", "Subject Sex")
PATIENT_WEIGHT = Code("29463-7", "LN", "Patient Weight")
RECENT_PHYSICAL_ACTIVITY = Code("113552", "DCM", "Recent Physical Activity")

# Coded values, each from the context group that its row names.
PERSON = Code("121006", "DCM", "Person")  # CID 270
DOSIMETER = Code("15869005", "SCT", "Dosimeter")  # CID 10010
IRRADIATING_DEVICE = Code("113859", "DCM", "Irradiating Device")  # TID 10002 row 14
IRRADIATION_AUTHORIZING = Code("113850", "DCM", "Irradiation Authorizing")
DOSE_CALIBRATOR = Code("113541", "DCM", "Dose Calibrator")  # CID 10041
FEMALE = Code("F", "DCM", "Female")  # CID 7455
# Units, as the rows give them, or from CID 7456 for an age.
NO_UNITS = Code("1", "UCUM", "no units")
PERCENT = Code("%", "UCUM", "Percent")
YEAR = Code("a", "UCUM", "year")
KILOGRAM = Code("kg", "UCUM", "kg")


def _chosen(optional, rows):
    """Return the items of ``rows``, keyed by template row, that ``optional`` names."""
    return [built() for key, built in rows if key in optional]


def _device_observer(relationship, uid, optional, prefix=""):
    """Return the items of TID 1002 for a device observer, with TID 1004's rows.

    TID 1002 row 1 gives the Observer Type, required for a device, and row 3
    includes TID 1004, whose rows inherit its relationship. ``prefix`` keeps
    the keys of the optional rows apart where a report includes TID 1004
    more than once.
    """

    def text(concept, value):
        return lambda: item(relationship, "TEXT", concept, text=value)

    return [
        item(relationship, "CODE", OBSERVER_TYPE, code=DEVICE),
        # TID 1004 row 1, M.
        item(relationship, "UIDREF", DEVICE_OBSERVER_UID_CONCEPT, text=uid),
        *_chosen(
            optional,
            [
                (
                    f"{prefix}TID 1004 row 2",
                    text(DEVICE_OBSERVER_NAME, f"{SENTINEL} STATION"),
                ),
                (
                    f"{prefix}TID 1004 row 3",
                    text(DEVICE_OBSERVER_MANUFACTURER, "FIXTURE MAKER"),
                ),
                (
                    f"{prefix}TID 1004 row 4",
                    text(DEVICE_OBSERVER_MODEL_NAME, "FIXTURE MODEL"),
                ),
                (
                    f"{prefix}TID 1004 row 5",
                    text(DEVICE_OBSERVER_SERIAL_NUMBER, f"{SENTINEL} SERIAL 1"),
                ),
                (
                    f"{prefix}TID 1004 row 6",
                    text(DEVICE_OBSERVER_PHYSICAL_LOCATION, f"{SENTINEL} ROOM 1"),
                ),
            ],
        ),
    ]


def _person_participant(role, optional, prefix):
    """Return TID 1020 "Person Participant" for ``role``, as included with CONTAINS.

    Rows 2 to 6 are HAS PROPERTIES children of row 1. Rows 3 and 5 are
    optional, keyed with ``prefix``.
    """
    return item(
        "CONTAINS",
        "PNAME",
        PERSON_NAME,
        # TID 1020 row 2, M.
        item("HAS PROPERTIES", "CODE", PERSON_ROLE_IN_PROCEDURE, code=role),
        *_chosen(
            optional,
            [
                (
                    f"{prefix}TID 1020 row 3",
                    lambda: item(
                        "HAS PROPERTIES", "TEXT", PERSON_ID, text=f"{SENTINEL}-ID-1"
                    ),
                ),
                (
                    f"{prefix}TID 1020 row 5",
                    lambda: item(
                        "HAS PROPERTIES",
                        "TEXT",
                        ORGANIZATION_NAME,
                        text=f"{SENTINEL} HOSPITAL",
                    ),
                ),
            ],
        ),
        text=f"{SENTINEL}^PARTICIPANT",
    )


def _calibration(optional):
    """Return TID 10002 row 3, a Calibration, with its rows 4 to 9."""
    return item(
        "CONTAINS",
        "CONTAINER",
        CALIBRATION,
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
                (
                    "TID 10002 row 9",
                    lambda: item(
                        "CONTAINS",
                        "TEXT",
                        CALIBRATION_PROTOCOL,
                        text=f"{SENTINEL} PROTOCOL",
                    ),
                ),
            ],
        ),
    )


def _irradiating_device():
    """Return TID 10002 row 14, TID 1021 "Device Participant" for the irradiating device.

    Rows 2 to 6 are HAS PROPERTIES children of row 1. Row 2, the name by
    which the site manages the device, is optional, and included.
    """
    return item(
        "CONTAINS",
        "CODE",
        DEVICE_ROLE_IN_PROCEDURE,
        item("HAS PROPERTIES", "TEXT", DEVICE_NAME, text=f"{SENTINEL} ROOM 2"),
        item("HAS PROPERTIES", "TEXT", DEVICE_MANUFACTURER, text="FIXTURE MAKER"),
        item("HAS PROPERTIES", "TEXT", DEVICE_MODEL_NAME, text="FIXTURE MODEL"),
        item(
            "HAS PROPERTIES",
            "TEXT",
            DEVICE_SERIAL_NUMBER,
            text=f"{SENTINEL} SERIAL 2",
        ),
        item(
            "HAS PROPERTIES",
            "UIDREF",
            DEVICE_OBSERVER_UID_CONCEPT,
            text=IRRADIATING_DEVICE_UID,
        ),
        code=IRRADIATING_DEVICE,
    )


def _irradiation_event(optional):
    """Return TID 10001 row 14, TID 10003 "Irradiation Event X-Ray Data"."""
    return item(
        "CONTAINS",
        "CONTAINER",
        IRRADIATION_EVENT_X_RAY_DATA,
        # TID 10003 rows 2, 3, 6, 7, 17, and 18, each M or MC and required.
        item("HAS CONCEPT MOD", "CODE", ACQUISITION_PLANE, code=SINGLE_PLANE),
        item(
            "CONTAINS",
            "UIDREF",
            IRRADIATION_EVENT_UID_CONCEPT,
            text=IRRADIATION_EVENT_UID,
        ),
        *_chosen(
            optional,
            [
                (
                    "TID 10003 row 4",
                    lambda: item(
                        "CONTAINS",
                        "TEXT",
                        IRRADIATION_EVENT_LABEL,
                        text=f"{SENTINEL} LABEL",
                    ),
                ),
            ],
        ),
        item("CONTAINS", "DATETIME", DATETIME_STARTED, text=IRRADIATION_DATETIME),
        item("CONTAINS", "CODE", IRRADIATION_EVENT_TYPE, code=STATIONARY_ACQUISITION),
        *_chosen(
            optional,
            [
                (
                    "TID 10003 row 8",
                    lambda: item(
                        "CONTAINS",
                        "TEXT",
                        ACQUISITION_PROTOCOL,
                        text=f"{SENTINEL} CHEST PA",
                    ),
                ),
            ],
        ),
        item("CONTAINS", "CODE", TARGET_REGION, code=CHEST),
        item(
            "CONTAINS",
            "NUM",
            DOSE_AREA_PRODUCT,
            number="0.00012",
            units=GRAY_SQUARE_METRE,
        ),
        *_chosen(
            optional,
            [
                (
                    "TID 10003 row 25",
                    lambda: item(
                        "CONTAINS", "TEXT", COMMENT, text=f"{SENTINEL} EVENT COMMENT"
                    ),
                ),
                (
                    "TID 10003 row 26",
                    lambda: _person_participant(
                        IRRADIATION_ADMINISTERING, optional, "TID 10003 row 26 "
                    ),
                ),
            ],
        ),
    )


# The optional rows of the X-Ray Radiation Dose SR, by template and row. A
# row whose items have optional rows of their own, such as a Person
# Participant's, prefixes their keys with its own.
X_RAY_OPTIONAL_ROWS = (
    "TID 1004 row 2",
    "TID 1004 row 3",
    "TID 1004 row 4",
    "TID 1004 row 5",
    "TID 1004 row 6",
    "TID 10001 row 5 person observer",
    "TID 1003 row 2",
    "TID 10002 row 3",
    "TID 10002 row 9",
    "TID 10002 row 14",
    "TID 10003 row 4",
    "TID 10003 row 8",
    "TID 10003 row 25",
    "TID 10003 row 26",
    "TID 10003 row 26 TID 1020 row 3",
    "TID 10003 row 26 TID 1020 row 5",
    "TID 10001 row 15",
    "TID 10001 row 17",
)


# Each optional row that another optional row holds, with the row that holds
# it.
HELD_BY = {
    "TID 1003 row 2": "TID 10001 row 5 person observer",
    "TID 10002 row 9": "TID 10002 row 3",
    "TID 10003 row 26 TID 1020 row 3": "TID 10003 row 26",
    "TID 10003 row 26 TID 1020 row 5": "TID 10003 row 26",
    "TID 10022 row 15 TID 1004 row 2": "TID 10022 row 13",
    "TID 10022 row 15 TID 1004 row 5": "TID 10022 row 13",
    "TID 10022 row 28": "TID 10022 row 27",
}


def with_holders(key):
    """Return the optional row ``key`` with every optional row that holds it."""
    keys = [key]
    while keys[-1] in HELD_BY:
        keys.append(HELD_BY[keys[-1]])
    return tuple(keys)


def x_ray_tree(optional=X_RAY_OPTIONAL_ROWS):
    """Return the root of an X-Ray Radiation Dose SR's tree, TID 10001.

    The report is of a single-plane projection radiograph whose dose was
    collected automatically (TID 10001 rows 2, 11, and 18), observed by the
    device that recorded it, so that TID 10001 rows 2, 3, 5 to 7, 11, 14,
    and 18 are required, as are TID 10002 rows 1 and 2 and TID 10003 rows 1
    to 3, 6, 7, 17, and 18. Of the rows required where they are included,
    it leaves out TID 10002 row 10, TID 10004 "Accumulated Fluoroscopy and
    Acquisition Projection X-Ray Dose", whose rows carry codes and numbers,
    and TID 10003 rows 27 to 29, TIDs 10003A to 10003C, the detector,
    source, and mechanical data. Most of their rows carry codes and numbers
    too, but not all: TID 10003A row 5 references the Acquired Image, which
    Table E.3.4-1 gives D, and K under Retain UIDs; TID 10003B row 2 can
    give the Reference Point Definition as free text, which the table does
    not list; and both can include TID 1021 "Device Participant", which
    TID 10002 row 14 includes here. The image reference and the free-text
    Reference Point Definition are not tested.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`X_RAY_OPTIONAL_ROWS`.
        A Calibration (``"TID 10002 row 3"``) and the irradiating device
        (``"TID 10002 row 14"``) are each required only where they apply,
        and are counted as optional here. Defaults to all of them.
    """
    unknown = set(optional) - set(X_RAY_OPTIONAL_ROWS)
    if unknown:
        raise ValueError(f"not an optional row: {sorted(unknown)}")
    observers = _device_observer("HAS OBS CONTEXT", DEVICE_OBSERVER_UID, optional)
    if "TID 10001 row 5 person observer" in optional:
        # A second observer, a person: TID 1002 row 1 names the type, and
        # row 2 includes TID 1003.
        observers += [
            item("HAS OBS CONTEXT", "CODE", OBSERVER_TYPE, code=PERSON),
            item(
                "HAS OBS CONTEXT",
                "PNAME",
                PERSON_OBSERVER_NAME,
                text=f"{SENTINEL}^OBSERVER",
            ),
            *_chosen(
                optional,
                [
                    (
                        "TID 1003 row 2",
                        lambda: item(
                            "HAS OBS CONTEXT",
                            "TEXT",
                            PERSON_OBSERVERS_ORGANIZATION_NAME,
                            text=f"{SENTINEL} HOSPITAL",
                        ),
                    ),
                ],
            ),
        ]
    accumulated = item(
        "CONTAINS",
        "CONTAINER",
        ACCUMULATED_X_RAY_DOSE_DATA,
        item("HAS CONCEPT MOD", "CODE", ACQUISITION_PLANE, code=SINGLE_PLANE),
        *_chosen(
            optional,
            [
                ("TID 10002 row 3", lambda: _calibration(optional)),
                ("TID 10002 row 14", _irradiating_device),
            ],
        ),
    )
    return item(
        None,
        "CONTAINER",
        X_RAY_RADIATION_DOSE_REPORT,
        item(
            "HAS CONCEPT MOD",
            "CODE",
            PROCEDURE_REPORTED,
            item("HAS CONCEPT MOD", "CODE", HAS_INTENT, code=DIAGNOSTIC_INTENT),
            code=PROJECTION_X_RAY,
        ),
        *observers,
        item(
            "HAS OBS CONTEXT",
            "CODE",
            SCOPE_OF_ACCUMULATION,
            item("HAS PROPERTIES", "UIDREF", STUDY_INSTANCE_UID, text=STUDY),
            code=STUDY_SCOPE,
        ),
        accumulated,
        _irradiation_event(optional),
        *_chosen(
            optional,
            [
                (
                    "TID 10001 row 15",
                    lambda: item(
                        "CONTAINS", "TEXT", COMMENT, text=f"{SENTINEL} COMMENT"
                    ),
                ),
                (
                    "TID 10001 row 17",
                    lambda: _person_participant(
                        IRRADIATION_AUTHORIZING, (), "TID 10001 row 17 "
                    ),
                ),
            ],
        ),
        item(
            "CONTAINS",
            "CODE",
            SOURCE_OF_DOSE_INFORMATION,
            code=AUTOMATED_DATA_COLLECTION,
        ),
    )


def _administration(optional):
    """Return TID 10021 row 4, TID 10022 "Radiopharmaceutical Administration Event Data"."""

    def text(key, concept, value, *children):
        return (key, lambda: item("CONTAINS", "TEXT", concept, *children, text=value))

    measured = (
        "TID 10022 row 13",
        lambda: item(
            "CONTAINS",
            "NUM",
            PRE_ADMINISTRATION_ACTIVITY,
            # TID 10022 rows 14 and 15, observed by a dose calibrator.
            item(
                "HAS OBS CONTEXT",
                "CODE",
                ACTIVITY_MEASUREMENT_DEVICE,
                code=DOSE_CALIBRATOR,
            ),
            *_device_observer(
                "HAS OBS CONTEXT",
                DOSE_CALIBRATOR_UID,
                optional,
                "TID 10022 row 15 ",
            ),
            number="372",
            units=MEGABECQUEREL,
        ),
    )
    dispensed = (
        "TID 10022 row 27",
        lambda: item(
            "CONTAINS",
            "TEXT",
            DISPENSE_UNIT_IDENTIFIER,
            *_chosen(
                optional,
                [
                    text(
                        "TID 10022 row 28",
                        LOT_IDENTIFIER,
                        f"{SENTINEL}-LOT-1",
                    )
                ],
            ),
            text=f"{SENTINEL}-UNIT-1",
        ),
    )
    return item(
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
        # TID 10022 row 6, M.
        item(
            "CONTAINS",
            "UIDREF",
            ADMINISTRATION_EVENT_UID_CONCEPT,
            text=ADMINISTRATION_EVENT_UID,
        ),
        # TID 10022 row 9, M.
        item("CONTAINS", "DATETIME", START_DATETIME, text=ADMINISTRATION_START),
        *_chosen(
            optional,
            [
                (
                    "TID 10022 row 10",
                    lambda: item(
                        "CONTAINS", "DATETIME", STOP_DATETIME, text=ADMINISTRATION_STOP
                    ),
                ),
            ],
        ),
        # TID 10022 row 11, M.
        item(
            "CONTAINS",
            "NUM",
            ADMINISTERED_ACTIVITY,
            number="370",
            units=MEGABECQUEREL,
        ),
        *_chosen(optional, [measured]),
        # TID 10022 rows 20 and 21, M and required for an intravenous route.
        item(
            "CONTAINS",
            "CODE",
            ROUTE_OF_ADMINISTRATION,
            item("HAS PROPERTIES", "CODE", SITE_OF, code=VIA_ARM_VEIN),
            code=INTRAVENOUS_ROUTE,
        ),
        # TID 10022 row 23, M.
        _person_participant(IRRADIATION_ADMINISTERING, optional, "TID 10022 row 23 "),
        *_chosen(
            optional,
            [
                text("TID 10022 row 26", BRAND_NAME, "FIXTURE BRAND"),
                dispensed,
                text(
                    "TID 10022 row 31",
                    PRESCRIPTION_IDENTIFIER,
                    f"{SENTINEL}-RX-1",
                ),
                text("TID 10022 row 32", COMMENT, f"{SENTINEL} ADMINISTRATION COMMENT"),
            ],
        ),
    )


def _patient_characteristics(optional):
    """Return TID 10021 row 5, TID 10024 "Imaging Agent Administration Patient Characteristics"."""
    return item(
        "CONTAINS",
        "CONTAINER",
        PATIENT_CHARACTERISTICS,
        *_chosen(
            optional,
            [
                (
                    "TID 10024 row 3",
                    lambda: item(
                        "CONTAINS", "NUM", SUBJECT_AGE, number="56", units=YEAR
                    ),
                ),
                (
                    "TID 10024 row 4",
                    lambda: item("CONTAINS", "CODE", SUBJECT_SEX, code=FEMALE),
                ),
                (
                    "TID 10024 row 6",
                    lambda: item(
                        "CONTAINS", "NUM", PATIENT_WEIGHT, number="71", units=KILOGRAM
                    ),
                ),
                (
                    "TID 10024 row 14",
                    lambda: item(
                        "CONTAINS",
                        "TEXT",
                        RECENT_PHYSICAL_ACTIVITY,
                        text=f"{SENTINEL} ACTIVITY",
                    ),
                ),
            ],
        ),
    )


# The optional rows of the Radiopharmaceutical Radiation Dose SR, keyed as
# X_RAY_OPTIONAL_ROWS are. TID 10024's rows are optional, and so is the
# template, which is included only with at least one of them.
RADIOPHARMACEUTICAL_OPTIONAL_ROWS = (
    "TID 10022 row 10",
    "TID 10022 row 13",
    "TID 10022 row 15 TID 1004 row 2",
    "TID 10022 row 15 TID 1004 row 5",
    "TID 10022 row 23 TID 1020 row 3",
    "TID 10022 row 23 TID 1020 row 5",
    "TID 10022 row 26",
    "TID 10022 row 27",
    "TID 10022 row 28",
    "TID 10022 row 31",
    "TID 10022 row 32",
    "TID 10024 row 3",
    "TID 10024 row 4",
    "TID 10024 row 6",
    "TID 10024 row 14",
    "TID 10021 row 6",
)


def radiopharmaceutical_tree(optional=RADIOPHARMACEUTICAL_OPTIONAL_ROWS):
    """Return the root of a Radiopharmaceutical Radiation Dose SR's tree, TID 10021.

    The report is of an intravenous administration of a PET
    radiopharmaceutical, so that TID 10021 rows 2 to 4 and TID 10022 rows 2
    to 4, 6, 9, 11, 20, 21, and 23 are required. TID 10022 row 19, TID
    10023 "Organ Dose", is optional and left out. The activity measured
    before the administration (``"TID 10022 row 13"``) is observed by a
    dose calibrator, as rows 14 and 15 allow, whose TID 1004 has its own
    optional rows.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from
        :data:`RADIOPHARMACEUTICAL_OPTIONAL_ROWS`; TID 10022 row 28 is
        included only with row 27, which holds it. Defaults to all of them.
    """
    unknown = set(optional) - set(RADIOPHARMACEUTICAL_OPTIONAL_ROWS)
    if unknown:
        raise ValueError(f"not an optional row: {sorted(unknown)}")
    characteristics = (
        [_patient_characteristics(optional)]
        if any(key.startswith("TID 10024 ") for key in optional)
        else []
    )
    return item(
        None,
        "CONTAINER",
        RADIOPHARMACEUTICAL_RADIATION_DOSE_REPORT,
        item(
            "HAS CONCEPT MOD",
            "CODE",
            ASSOCIATED_PROCEDURE,
            item("HAS CONCEPT MOD", "CODE", HAS_INTENT, code=DIAGNOSTIC_INTENT),
            code=TUMOR_LOCALIZATION,
        ),
        _administration(optional),
        *characteristics,
        *_chosen(
            optional,
            [
                (
                    "TID 10021 row 6",
                    lambda: item(
                        "CONTAINS", "TEXT", COMMENT, text=f"{SENTINEL} REPORT COMMENT"
                    ),
                ),
            ],
        ),
    )


def _report(identity, tree, verified):
    """Return a report whose SR Document Content Module holds ``tree``.

    ``identity`` gives its SOP Class, SOP Instance UID, Series Instance UID,
    and root template.

    The header holds the Patient, General Study, SR Document Series, General
    and Enhanced General Equipment, SR Document General, and SOP Common
    Modules' required attributes, and identifying values of their own.
    """
    sop_class, sop_instance, series, template = identity
    dataset = pydicom.Dataset()
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = sop_instance
    dataset.PatientName = PATIENTS_NAME
    dataset.PatientID = PATIENT_ID
    dataset.PatientBirthDate = ""
    dataset.PatientSex = ""
    dataset.StudyInstanceUID = STUDY
    dataset.StudyDate = STUDY_DATE
    dataset.StudyTime = "093000"
    dataset.ReferringPhysicianName = f"{SENTINEL}^REFERRER"
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
    dataset.CompletionFlag = "COMPLETE"
    dataset.VerificationFlag = "VERIFIED" if verified else "UNVERIFIED"
    dataset.ContentDate = CONTENT_DATE
    dataset.ContentTime = "120000"
    if verified:
        # PS3.3 Table C.17-2: Type 1C, required where VERIFIED.
        observer = pydicom.Dataset()
        observer.VerifyingObserverName = f"{SENTINEL}^VERIFIER"
        observer.VerifyingObserverIdentificationCodeSequence = pydicom.Sequence()
        observer.VerifyingOrganization = f"{SENTINEL} HOSPITAL"
        observer.VerificationDateTime = VERIFICATION_DATETIME
        dataset.VerifyingObserverSequence = pydicom.Sequence([observer])
    dataset.PerformedProcedureCodeSequence = pydicom.Sequence()
    for element in tree:
        dataset.add(element)
    template_item = pydicom.Dataset()
    template_item.MappingResource = "DCMR"
    template_item.TemplateIdentifier = template
    dataset.ContentTemplateSequence = pydicom.Sequence([template_item])
    return dataset


def x_ray_dose_report(optional=X_RAY_OPTIONAL_ROWS, *, verified=False):
    """Return an X-Ray Radiation Dose SR whose tree is :func:`x_ray_tree`.

    ``verified`` gives it the Verification Flag VERIFIED, with a Verifying
    Observer Sequence, rather than UNVERIFIED.
    """
    return _report(
        (X_RAY_RADIATION_DOSE_SR, X_RAY_REPORT, X_RAY_SERIES, "10001"),
        x_ray_tree(optional),
        verified,
    )


def radiopharmaceutical_dose_report(
    optional=RADIOPHARMACEUTICAL_OPTIONAL_ROWS, *, verified=False
):
    """Return a Radiopharmaceutical Radiation Dose SR.

    Its tree is :func:`radiopharmaceutical_tree`, and ``verified`` is as for
    :func:`x_ray_dose_report`.
    """
    return _report(
        (
            RADIOPHARMACEUTICAL_RADIATION_DOSE_SR,
            RADIOPHARMACEUTICAL_REPORT,
            RADIOPHARMACEUTICAL_SERIES,
            "10021",
        ),
        radiopharmaceutical_tree(optional),
        verified,
    )
