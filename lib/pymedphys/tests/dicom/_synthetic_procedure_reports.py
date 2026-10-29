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

"""Synthetic planning, procedure, and acquisition context Structured Reports.

Five builders give one report each, whose content tree follows the root
template that PS3.3 2026d Section A.35 names for its IOD:

- :func:`implantation_plan`, an Implantation Plan SR Document whose tree
  follows TID 7000 "Implantation Plan" (Section A.35.12);
- :func:`echo_report`, a Simplified Adult Echo SR whose tree follows TID
  5300 "Simplified Echo Procedure Report" (Section A.35.17);
- :func:`planned_administration` and :func:`performed_administration`, a
  Planned and a Performed Imaging Agent Administration SR whose trees
  follow TID 11001 "Planned Imaging Agent Administration" and TID 11020
  "Performed Imaging Agent Administration" (Sections A.35.19 and A.35.20),
  which share TID 11002 "Imaging Agent Information", TID 11006 "Imaging
  Agent Administration Steps", and TID 10024 "Imaging Agent Administration
  Patient Characteristics"; and
- :func:`acquisition_context`, an Acquisition Context SR whose tree follows
  TID 8101 "Preclinical Small Animal Image Acquisition Context", the
  template that Section A.35.16 names for its root.

Each content item's relationship, Value Type, and concept name is a row of
a template of DICOM PS3.16 2026d, cited beside it, and each coded value is
one of the context group that the row names. Code meanings are those of
PS3.16 Annex D for DCM codes, and those the templates and context groups
give for the others.

Each report holds every row that its templates require where they are
included, and optional rows that carry identifying values, free text, or
concept names coded in a scheme that Clean Structured Content cannot look
up. The optional rows are keyed by their template and row, such as ``"TID
7000 row 37"``, so that a test can build a report with any of them; a row
that another optional row holds is included only with it
(:data:`HELD_BY`). TID 1001 "Observation Context", which TID 7000, TID
5300, and TID 8101 include, holds only its required person observer: its
optional rows are :mod:`._synthetic_structured_reports`'s, whose tests
cover them. That module's header, with its identifying values, and its
builders of content items and of TID 1001, 1002, 1005, and 1204 are shared
here.

Text that must never reach a written file under the Basic Profile carries
``SENTINEL``, as in the header. Every UID is invented under ``2.25.``, the
patient is fictitious, and no value comes from a real report.
"""

# The five reports share their codes, header, and builders, so they stay in
# one module.
# pylint: disable = too-many-lines

from . import _synthetic_structured_reports as general

# The general reports' builders, which this module shares rather than
# repeats.
# pylint: disable = protected-access
_row = general._row
_chosen = general._chosen
_checked = general._checked
_language = general._language
_observation_context = general._observation_context
_evidence = general._evidence
_report = general._report
# pylint: enable = protected-access

Code = general.Code
item = general.item
SENTINEL = general.SENTINEL

IMPLANTATION_PLAN_SR = "1.2.840.10008.5.1.4.1.1.88.70"
ACQUISITION_CONTEXT_SR = "1.2.840.10008.5.1.4.1.1.88.71"
SIMPLIFIED_ADULT_ECHO_SR = "1.2.840.10008.5.1.4.1.1.88.72"
PLANNED_ADMINISTRATION_SR = "1.2.840.10008.5.1.4.1.1.88.74"
PERFORMED_ADMINISTRATION_SR = "1.2.840.10008.5.1.4.1.1.88.75"
IMPLANTATION_PLAN_IOD = "Implantation Plan SR Document"
ACQUISITION_CONTEXT_IOD = "Acquisition Context SR"
SIMPLIFIED_ADULT_ECHO_IOD = "Simplified Adult Echo SR"
PLANNED_ADMINISTRATION_IOD = "Planned Imaging Agent Administration SR"
PERFORMED_ADMINISTRATION_IOD = "Performed Imaging Agent Administration SR"
# The instances that the reports reference.
GENERIC_IMPLANT_TEMPLATE = "1.2.840.10008.5.1.4.43.1"
IMPLANT_ASSEMBLY_TEMPLATE_STORAGE = "1.2.840.10008.5.1.4.44.1"
CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
SPATIAL_REGISTRATION_STORAGE = "1.2.840.10008.5.1.4.1.1.66.1"
SPATIAL_FIDUCIALS_STORAGE = "1.2.840.10008.5.1.4.1.1.66.2"
# The synchronisation frame of Coordinated Universal Time (PS3.3 Section
# C.7.4.2.1.1), a public definition.
UTC = "1.2.840.10008.15.1.1"

# The Series and SOP Instance UIDs of each report and of each instance that
# a report references. Implant templates belong to no study or series.
IMPLANTATION_PLAN = ("2.25.5100", "2.25.5101")
ECHO_REPORT = ("2.25.5110", "2.25.5111")
PLANNED_ADMINISTRATION = ("2.25.5120", "2.25.5121")
PERFORMED_ADMINISTRATION = ("2.25.5130", "2.25.5131")
ACQUISITION_CONTEXT = ("2.25.5140", "2.25.5141")
CT_IMAGE = ("2.25.5150", "2.25.5151")
REGISTRATION = ("2.25.5160", "2.25.5161")
FIDUCIALS = ("2.25.5170", "2.25.5171")
SELECTED_TEMPLATE = "2.25.5201"
MANUFACTURER_TEMPLATE = "2.25.5202"
ASSEMBLY_TEMPLATE = "2.25.5203"
# The UIDs that content items carry, other than the references above.
IMPLANT_FRAME_OF_REFERENCE = "2.25.5301"
CT_FRAME_OF_REFERENCE = "2.25.5302"
FIDUCIAL_UID = "2.25.5303"
PERFORMED_STEP_UID = "2.25.5304"
PERFORMED_PHASE_UID = "2.25.5305"
UIDS = (
    *IMPLANTATION_PLAN,
    *ECHO_REPORT,
    *PLANNED_ADMINISTRATION,
    *PERFORMED_ADMINISTRATION,
    *ACQUISITION_CONTEXT,
    *CT_IMAGE,
    *REGISTRATION,
    *FIDUCIALS,
    SELECTED_TEMPLATE,
    MANUFACTURER_TEMPLATE,
    ASSEMBLY_TEMPLATE,
    IMPLANT_FRAME_OF_REFERENCE,
    CT_FRAME_OF_REFERENCE,
    FIDUCIAL_UID,
    PERFORMED_STEP_UID,
    PERFORMED_PHASE_UID,
)
# The dates and datetimes that content items carry, none of which a modified
# or dummy value repeats.
EXPIRATION_DATE = "20290131"
PHASE_START = "20260412102231"
ADVERSE_EVENT_DATETIME = "20260412102904"
HANDLING_START = "20260412081500"
HANDLING_END = "20260412093000"
LIGHTS_ON = "063000"
DATES = (
    EXPIRATION_DATE,
    PHASE_START,
    ADVERSE_EVENT_DATETIME,
    HANDLING_START,
    HANDLING_END,
)
# The Unique Device Identifier of a syringe, in the human-readable form of
# the GS1 issuing agency's, with a serial number (AI 21) that no other value
# repeats.
SYRINGE_UDI = "(01)00000000000017(17)290131(10)A42(21)SYNTHUDI0731"
TIMEZONE = "+1000"

# Root concepts.
IMPLANTATION_PLAN_TITLE = Code("112345", "DCM", "Implantation Plan")
ADULT_ECHO_REPORT = Code("125200", "DCM", "Adult Echocardiography Procedure Report")
PLANNED_ADMINISTRATION_TITLE = Code(
    "130226", "DCM", "Planned Imaging Agent Administration"
)
PERFORMED_ADMINISTRATION_TITLE = Code(
    "130227", "DCM", "Performed Imaging Agent Administration"
)
PRECLINICAL_CONTEXT = Code(
    "127001", "DCM", "Preclinical Small Animal Imaging Acquisition Context"
)
# TID 7000.
IMPLANT_COMPONENT_LIST = Code("112360", "DCM", "Implant Component List")
IMPLANT_ASSEMBLY_TEMPLATE = Code("112366", "DCM", "Implant Assembly Template")
SELECTED_IMPLANT_COMPONENT = Code("112346", "DCM", "Selected Implant Component")
COMPONENT_ID = Code("112347", "DCM", "Component ID")
MANUFACTURER_IMPLANT_TEMPLATE = Code("112371", "DCM", "Manufacturer Implant Template")
INFORMATION_USED_FOR_PLANNING = Code("112358", "DCM", "Information used for planning")
PATIENT_IMAGE = Code("112354", "DCM", "Patient Image")
PATIENT_DATA_USED_DURING_PLANNING = Code(
    "112361", "DCM", "Patient Data Used During Planning"
)
USER_SELECTED_FIDUCIAL = Code("112356", "DCM", "User Selected Fiducial")
FIDUCIAL_INTENT = Code("112369", "DCM", "Fiducial Intent")
INTRAOPERATIVE_USAGE = Code(
    "112367", "DCM", "Planning Information for Intraoperative Usage"
)
PHYSICIAN_NOTE = Code("121173", "DCM", "Physician Note")
SPATIAL_REGISTRATION = Code("112353", "DCM", "Spatial Registration")
# TID 5300, 5301.
CURRENT_PROCEDURE_DESCRIPTIONS = Code("55111-9", "LN", "Current Procedure Descriptions")
ACQUISITION_PROTOCOL = Code("125203", "DCM", "Acquisition Protocol")
PRE_COORDINATED_MEASUREMENTS = Code("125301", "DCM", "Pre-coordinated Measurements")
POST_COORDINATED_MEASUREMENTS = Code("125302", "DCM", "Post-coordinated Measurements")
ADHOC_MEASUREMENTS = Code("125303", "DCM", "Adhoc Measurements")
SHORT_LABEL = Code("125309", "DCM", "Short Label")
# Measurements of CID 12300 "Core Echo Measurement", for TID 5301 row 1's
# $Measurement. All but those it includes from CID 12309 "Core Echo Strain
# Measurement", coded in DCM, are coded in LOINC.
LV_GLOBAL_LONGITUDINAL_STRAIN = Code(
    "130686", "DCM", "LV End-systolic GLS Multiview Mean (Endocardial)"
)
AORTIC_ANNULUS_DIAMETER = Code("79940-3", "LN", "Aortic annulus diameter")
# TID 11001, 11020, 11002, 11004, 11006, 11007, 11008, and 11021.
COMMENT = Code("121106", "DCM", "Comment")
SUMMARY = Code("55112-7", "LN", "Summary")
PLANNED_ADMINISTRATION_INSTANCE = Code(
    "130236", "DCM", "Planned Imaging Agent Administration SOP Instance"
)
COMPLETION_STATUS = Code(
    "130211", "DCM", "Imaging Agent Administration Completion Status"
)
IMAGING_AGENT_INFORMATION = Code("130183", "DCM", "Imaging Agent Information")
IMAGING_AGENT_IDENTIFIER = Code("130254", "DCM", "Imaging Agent Identifier")
IMAGING_AGENT_WARMED = Code("130187", "DCM", "Imaging Agent Warmed")
COMPONENT_USAGE = Code("130191", "DCM", "Imaging Agent Component Usage")
IMAGING_AGENT_COMPONENT = Code("130238", "DCM", "Imaging Agent Component")
DRUG_ADMINISTERED = Code("122083", "DCM", "Drug administered")
BILLING_CODE = Code("121147", "DCM", "Billing Code")
DESCRIPTION_OF_MATERIAL = Code("121145", "DCM", "Description of Material")
EXPIRATION_DATE_CONCEPT = Code("C70854", "NCIt", "Medical Product Expiration Date")
MANUFACTURER_NAME = Code("C0947322", "UMLS", "Manufacturer Name")
BRAND_NAME = Code("111529", "DCM", "Brand Name")
BARCODE_VALUE = Code("130231", "DCM", "Barcode Value")
UNIT_SERIAL_IDENTIFIER = Code("121148", "DCM", "Unit Serial Identifier")
LOT_IDENTIFIER = Code("121149", "DCM", "Lot Identifier")
UDI = Code("128739", "DCM", "UDI")
ADMINISTRATION_STEPS = Code("130192", "DCM", "Imaging Agent Administration Steps")
STEPS_NAME = Code("130200", "DCM", "Imaging Agent Administration Steps Name")
STEPS_DESCRIPTION = Code(
    "130199", "DCM", "Imaging Agent Administration Steps Description"
)
ADMINISTRATION_STEP = Code("130195", "DCM", "Imaging Agent Administration Step")
STEP_IDENTIFIER = Code("130196", "DCM", "Imaging Agent Administration Step Identifier")
PERFORMED_STEP_UID_CONCEPT = Code(
    "130246", "DCM", "Imaging Agent Administration Performed Step UID"
)
ADMINISTRATION_MODE = Code("130181", "DCM", "Administration Mode")
PERSON_ROLE_IN_ORGANIZATION = Code("113874", "DCM", "Person Role in Organization")
STEP_TYPE = Code("130250", "DCM", "Administration Step Type")
ROUTE_OF_ADMINISTRATION = Code("410675002", "SCT", "Route of Administration")
STEP_SEQUENCE_NUMBER = Code(
    "130445", "DCM", "Imaging Agent Administration Step Sequence Number"
)
ADMINISTRATION_PHASE = Code("130202", "DCM", "Imaging Agent Administration Phase")
PHASE_IDENTIFIER = Code(
    "130203", "DCM", "Imaging Agent Administration Phase Identifier"
)
PERFORMED_PHASE_UID_CONCEPT = Code(
    "130261", "DCM", "Imaging Agent Administration Performed Phase UID"
)
TOTAL_PHASE_VOLUME = Code("130240", "DCM", "Total Phase Volume Administered")
DATETIME_STARTED = Code("111526", "DCM", "DateTime Started")
ADVERSE_EVENTS = Code("130212", "DCM", "Imaging Agent Administration Adverse Events")
ADVERSE_EVENT = Code("C41331", "NCIt", "Adverse Event")
ADVERSE_EVENT_DETECTION = Code("130215", "DCM", "Adverse Event Detection DateTime")
# TID 10024.
PATIENT_CHARACTERISTICS = Code("121118", "DCM", "Patient Characteristics")
PATIENT_WEIGHT = Code("29463-7", "LN", "Patient Weight")
BODY_MASS_INDEX = Code("60621009", "SCT", "Body Mass Index")
RECENT_PHYSICAL_ACTIVITY = Code("113552", "DCM", "Recent Physical Activity")
# TID 8101, 8110, 8121, and 8170.
BIOSAFETY_CONDITIONS = Code("127010", "DCM", "Biosafety conditions")
ANIMAL_HANDLING = Code("127005", "DCM", "Animal handling during specified phase")
PHASE_OF_ANIMAL_HANDLING = Code("127006", "DCM", "Phase of animal handling")
DATETIME_ENDED = Code("111527", "DCM", "DateTime Ended")
ANIMAL_HOUSING = Code("127120", "DCM", "Animal housing")
ANIMAL_ROOM_IDENTIFIER = Code("127122", "DCM", "Animal room identifier")
ENVIRONMENTAL_TEMPERATURE = Code("C90380", "NCIt", "Environmental temperature")
CIRCADIAN_EFFECTS = Code("127050", "DCM", "Circadian effects")
LIGHTS_ON_TIME = Code("127215", "DCM", "Lights on time of day")

# Coded values, each from the context group that its row names, or that is
# cited beside it, and units, each that its row gives.
TRANSTHORACIC_ECHOCARDIOGRAPHY = Code(
    "433236007", "SCT", "Transthoracic echocardiography"
)  # CID 12001
COMPLETE = Code("255594003", "SCT", "Complete")  # CID 67
NO = Code("373067005", "SCT", "No")  # CID 230
IOHEXOL = Code("109218004", "SCT", "Iohexol")  # CID 12
MANUAL_ADMINISTRATION = Code("130174", "DCM", "Manual Administration")  # CID 63
NURSE = Code("106292003", "SCT", "Nurse")  # CID 7450, by CID 7452
DIAGNOSTIC_ADMINISTRATION = Code("130249", "DCM", "Diagnostic Administration")  # CID 72
INTRAVENOUS_ROUTE = Code("47625008", "SCT", "Intravenous route")  # CID 11
NAUSEA_AND_VOMITING = Code("16932000", "SCT", "Nausea and vomiting")  # CID 60
PERCENT = Code("%", "UCUM", "%")  # CID 12309
CENTIMETRE = Code("cm", "UCUM", "cm")  # CID 12300
MM_PER_PIXEL = Code("mm/{pixel}", "UCUM", "mm/pixel")  # TID 7000 rows 31, 32
MILLILITRE = Code("ml", "UCUM", "ml")  # TID 11008 row 6
NO_UNITS = Code("1", "UCUM", "no units")  # TID 11007 row 20
KILOGRAM = Code("kg", "UCUM", "kg")  # TID 10024 row 6
KG_PER_SQUARE_METRE = Code("kg/m2", "UCUM", "kg/m2")  # TID 10024 row 9
YEAR = Code("a", "UCUM", "year")  # CID 7456
CELSIUS = Code("Cel", "UCUM", "C")  # TID 8121 row 25

# Each optional row that another optional row holds, with the row that holds
# it.
HELD_BY = {
    "TID 7000 row 35": "TID 7000 row 33",
    "TID 8101 row 8": "TID 8101 row 6",
    "TID 8101 row 9": "TID 8101 row 6",
    "TID 8101 row 10": "TID 8101 row 6",
    "TID 8101 row 14": "TID 8101 row 6",
    "TID 8121 row 2b": "TID 8101 row 10",
    "TID 8121 row 25": "TID 8101 row 10",
}


def with_holders(key):
    """Return the optional row ``key`` with every optional row that holds it."""
    keys = [key]
    while keys[-1] in HELD_BY:
        keys.append(HELD_BY[keys[-1]])
    return tuple(keys)


def _composite(relationship, concept, sop_class, sop_instance, *children):
    return item(
        relationship,
        "COMPOSITE",
        concept,
        *children,
        sop_class=sop_class,
        sop_instance=sop_instance,
    )


IMPLANTATION_OPTIONAL_ROWS = (
    "TID 7000 row 2",
    "TID 7000 row 7",
    "TID 7000 row 30",
    "TID 7000 row 33",
    "TID 7000 row 35",
    "TID 7000 row 37",
    "TID 7000 row 40",
)


def _selected_component():
    """Return TID 7000 row 8, one Selected Implant Component, with its M rows.

    Row 10, the Component Type, is required only where row 8 has more than
    one item. Row 11, unnamed, and row 13 each reference a Generic Implant
    Template: the one selected and the manufacturer's that it derives from.
    """
    return item(
        "CONTAINS",
        "CONTAINER",
        SELECTED_IMPLANT_COMPONENT,
        item("CONTAINS", "TEXT", COMPONENT_ID, text=f"{SENTINEL} STEM"),
        _composite("CONTAINS", None, GENERIC_IMPLANT_TEMPLATE, SELECTED_TEMPLATE),
        item(
            "CONTAINS",
            "UIDREF",
            general.FRAME_OF_REFERENCE_UID,
            text=IMPLANT_FRAME_OF_REFERENCE,
        ),
        _composite(
            "CONTAINS",
            MANUFACTURER_IMPLANT_TEMPLATE,
            GENERIC_IMPLANT_TEMPLATE,
            MANUFACTURER_TEMPLATE,
        ),
    )


def _planning_information(optional):
    """Return TID 7000 row 28, where ``optional`` names one of its rows.

    Row 30 references a CT image, with its pixel spacing (rows 31 and 32,
    M), and row 33 a Spatial Fiducials instance, so that row 34, the
    fiducial that the user selected, is required; row 35 adds its intent.
    """
    spacing = {"number": "0.7", "units": MM_PER_PIXEL}
    fiducial = item(
        "HAS PROPERTIES",
        "UIDREF",
        USER_SELECTED_FIDUCIAL,
        *_chosen(
            optional,
            [
                _row(
                    "TID 7000 row 35",
                    "HAS CONCEPT MOD",
                    "TEXT",
                    FIDUCIAL_INTENT,
                    text=f"{SENTINEL} LANDMARK",
                )
            ],
        ),
        text=FIDUCIAL_UID,
    )
    rows = _chosen(
        optional,
        [
            (
                "TID 7000 row 30",
                lambda: item(
                    "CONTAINS",
                    "IMAGE",
                    PATIENT_IMAGE,
                    item(
                        "HAS PROPERTIES",
                        "NUM",
                        general.HORIZONTAL_PIXEL_SPACING,
                        **spacing,
                    ),
                    item(
                        "HAS PROPERTIES",
                        "NUM",
                        general.VERTICAL_PIXEL_SPACING,
                        **spacing,
                    ),
                    sop_class=CT_IMAGE_STORAGE,
                    sop_instance=CT_IMAGE[1],
                ),
            ),
            (
                "TID 7000 row 33",
                lambda: _composite(
                    "CONTAINS",
                    PATIENT_DATA_USED_DURING_PLANNING,
                    SPATIAL_FIDUCIALS_STORAGE,
                    FIDUCIALS[1],
                    fiducial,
                ),
            ),
        ],
    )
    if not rows:
        return []
    return [item("CONTAINS", "CONTAINER", INFORMATION_USED_FOR_PLANNING, *rows)]


def _intraoperative_information(optional):
    """Return TID 7000 row 36, where ``optional`` names one of its rows.

    Row 37 is the physician's note, and row 40 references a Spatial
    Registration instance, with the frame of reference it registers (row
    41).
    """
    rows = _chosen(
        optional,
        [
            _row(
                "TID 7000 row 37",
                "CONTAINS",
                "TEXT",
                PHYSICIAN_NOTE,
                text=f"{SENTINEL} CHECK LEG LENGTH",
            ),
            (
                "TID 7000 row 40",
                lambda: _composite(
                    "CONTAINS",
                    SPATIAL_REGISTRATION,
                    SPATIAL_REGISTRATION_STORAGE,
                    REGISTRATION[1],
                    item(
                        "HAS PROPERTIES",
                        "UIDREF",
                        general.FRAME_OF_REFERENCE_UID,
                        text=CT_FRAME_OF_REFERENCE,
                    ),
                ),
            ),
        ],
    )
    if not rows:
        return []
    return [item("CONTAINS", "CONTAINER", INTRAOPERATIVE_USAGE, *rows)]


def implantation_tree(optional=()):
    """Return the root of an implantation plan's tree, TID 7000.

    TID 7000 rows 1, 3, and 6 are required: the title, the observation
    context (TID 1001), whose observer, a person, is named, and the Implant
    Component List, which holds one Selected Implant Component (row 8). No
    earlier or related plan exists, so rows 4 and 5 are absent.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`IMPLANTATION_OPTIONAL_ROWS`.
    """
    _checked(optional, IMPLANTATION_OPTIONAL_ROWS)
    assembly = _row(
        "TID 7000 row 7",
        "CONTAINS",
        "COMPOSITE",
        IMPLANT_ASSEMBLY_TEMPLATE,
        sop_class=IMPLANT_ASSEMBLY_TEMPLATE_STORAGE,
        sop_instance=ASSEMBLY_TEMPLATE,
    )
    return item(
        None,
        "CONTAINER",
        IMPLANTATION_PLAN_TITLE,
        *_chosen(optional, [("TID 7000 row 2", _language)]),
        *_observation_context(()),
        item(
            "CONTAINS",
            "CONTAINER",
            IMPLANT_COMPONENT_LIST,
            *_chosen(optional, [assembly]),
            _selected_component(),
        ),
        *_planning_information(optional),
        *_intraoperative_information(optional),
    )


ECHO_OPTIONAL_ROWS = (
    "TID 5300 row 2",
    "TID 5300 row 4",
    "TID 5301 row 6",
)


def echo_tree(optional=(), measurement=LV_GLOBAL_LONGITUDINAL_STRAIN):
    """Return the root of a simplified adult echo report's tree, TID 5300.

    TID 5300 rows 1, 3, 10, 12, and 14 are required: the title, the
    observation context (TID 1001), whose observer, a person, is named, and
    the three containers of measurements, of which only the pre-coordinated
    one requires an item (row 11, TID 5301). Its one measurement is a sample
    that is not flagged as preferred, so TID 5301 rows 2 and 3 are absent.
    ``"TID 5300 row 4"`` adds the procedure's description, under a LOINC
    heading, with its protocol (row 5, from CID 12001).

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`ECHO_OPTIONAL_ROWS`.
    measurement : Code
        The measurement's concept name, from CID 12300, with its value and
        units. Defaults to a strain measurement of CID 12309, coded in DCM;
        :data:`AORTIC_ANNULUS_DIAMETER` is one of the measurements coded in
        LOINC.
    """
    _checked(optional, ECHO_OPTIONAL_ROWS)
    number, units = (
        ("-19.5", PERCENT)
        if measurement == LV_GLOBAL_LONGITUDINAL_STRAIN
        else ("2.3", CENTIMETRE)
    )
    label = _row(
        "TID 5301 row 6",
        "HAS PROPERTIES",
        "TEXT",
        SHORT_LABEL,
        text=f"{SENTINEL} LABEL",
    )
    description = item(
        "CONTAINS",
        "CONTAINER",
        CURRENT_PROCEDURE_DESCRIPTIONS,
        item(
            "CONTAINS",
            "CODE",
            ACQUISITION_PROTOCOL,
            code=TRANSTHORACIC_ECHOCARDIOGRAPHY,
        ),
    )
    return item(
        None,
        "CONTAINER",
        ADULT_ECHO_REPORT,
        *_chosen(optional, [("TID 5300 row 2", _language)]),
        *_observation_context(()),
        *_chosen(optional, [("TID 5300 row 4", lambda: description)]),
        item(
            "CONTAINS",
            "CONTAINER",
            PRE_COORDINATED_MEASUREMENTS,
            item(
                "CONTAINS",
                "NUM",
                measurement,
                *_chosen(optional, [label]),
                number=number,
                units=units,
            ),
        ),
        item("CONTAINS", "CONTAINER", POST_COORDINATED_MEASUREMENTS),
        item("CONTAINS", "CONTAINER", ADHOC_MEASUREMENTS),
    )


# The optional rows of TID 11004 that both administration reports hold. Its
# Barcode Value is row 22 in a plan and row 23 in a performed administration.
COMPONENT_ROWS = (
    "TID 11004 row 17",
    "TID 11004 row 18",
    "TID 11004 row 19",
    "TID 11004 row 20",
    "TID 11004 row 21",
    "TID 11004 row 24",
    "TID 11004 row 25",
    "TID 11004 row 26",
)
ADMINISTRATION_ROWS = (
    "TID 1005 row 1",
    "TID 1005 row 7",
    *COMPONENT_ROWS,
    "TID 10024 row 3",
    "TID 10024 row 6",
    "TID 10024 row 9",
    "TID 10024 row 14",
    "TID 11006 row 3",
    "TID 11006 row 4",
)
PLANNED_OPTIONAL_ROWS = (
    "TID 11001 row 2",
    *ADMINISTRATION_ROWS,
    "TID 11004 row 22",
    "TID 11001 row 8",
)
PERFORMED_OPTIONAL_ROWS = (
    "TID 11020 row 2",
    *ADMINISTRATION_ROWS,
    "TID 11004 row 23",
    "TID 11020 row 8",
    "TID 11020 row 11",
    "TID 11020 row 13",
)


def udi_item():
    """Return TID 11004 row 26, the UDI of a component's syringe, as a CODE.

    The row's concept, UDI (128739, DCM), is "the entire Human Readable Form
    of the Unique Device Identifier as defined by the Issuing Agency"
    (PS3.16 Annex D). The template names no coding scheme for it, so the
    code is in a local one, whose designator begins with "99" (PS3.3
    Section 8.2), and the form, longer than Code Value's 16 characters, is
    its Long Code Value (0008,0119).
    """
    dataset = item("CONTAINS", "CODE", UDI, code=Code("", "99SYNTHETIC", "Syringe UDI"))
    code = dataset.ConceptCodeSequence[0]
    del code.CodeValue
    code.LongCodeValue = SYRINGE_UDI
    return dataset


def _component(optional, barcode):
    """Return TID 11002 row 5, TID 11004 "Imaging Agent Component".

    Row 2, the drug administered, here iohexol from CID 12, is required.
    ``barcode`` is the key of the row of the Barcode Value that the root
    selects: TID 11004 row 22 for a plan, and row 23 for a performed
    administration.
    """

    def text(key, concept, value):
        return _row(key, "CONTAINS", "TEXT", concept, text=value)

    return item(
        "CONTAINS",
        "CONTAINER",
        IMAGING_AGENT_COMPONENT,
        item("CONTAINS", "CODE", DRUG_ADMINISTERED, code=IOHEXOL),
        *_chosen(
            optional,
            [
                text("TID 11004 row 17", BILLING_CODE, f"{SENTINEL}-BILL"),
                text(
                    "TID 11004 row 18",
                    DESCRIPTION_OF_MATERIAL,
                    f"{SENTINEL} PREFILLED SYRINGE",
                ),
                _row(
                    "TID 11004 row 19",
                    "CONTAINS",
                    "DATE",
                    EXPIRATION_DATE_CONCEPT,
                    text=EXPIRATION_DATE,
                ),
                text("TID 11004 row 20", MANUFACTURER_NAME, f"{SENTINEL} PHARMA"),
                text("TID 11004 row 21", BRAND_NAME, f"{SENTINEL} BRAND"),
                text(barcode, BARCODE_VALUE, f"{SENTINEL}-BARCODE"),
                text("TID 11004 row 24", UNIT_SERIAL_IDENTIFIER, f"{SENTINEL}-UNIT"),
                text("TID 11004 row 25", LOT_IDENTIFIER, f"{SENTINEL}-LOT"),
                ("TID 11004 row 26", udi_item),
            ],
        ),
    )


def _agent_information(optional, barcode):
    """Return TID 11001 and TID 11020 row 7, TID 11002, with its M rows.

    The agent is not warmed (row 3, from CID 230), and its one component
    usage (row 4) includes TID 11004 (row 5); with one usage, row 6 is
    absent.
    """
    return item(
        "CONTAINS",
        "CONTAINER",
        IMAGING_AGENT_INFORMATION,
        item(
            "CONTAINS", "TEXT", IMAGING_AGENT_IDENTIFIER, text=f"{SENTINEL} SYRINGE A"
        ),
        item("CONTAINS", "CODE", IMAGING_AGENT_WARMED, code=NO),
        item(
            "CONTAINS",
            "CONTAINER",
            COMPONENT_USAGE,
            _component(optional, barcode),
        ),
    )


def _patient_characteristics(optional):
    """Return TID 11001 and TID 11020 row 6, TID 10024, with ``optional``'s rows.

    TID 10024 requires none of its rows, so the container is included only
    with one of them.
    """
    rows = _chosen(
        optional,
        [
            _row(
                "TID 10024 row 3",
                "CONTAINS",
                "NUM",
                general.SUBJECT_AGE,
                number="56",
                units=YEAR,
            ),
            _row(
                "TID 10024 row 6",
                "CONTAINS",
                "NUM",
                PATIENT_WEIGHT,
                number="71",
                units=KILOGRAM,
            ),
            _row(
                "TID 10024 row 9",
                "CONTAINS",
                "NUM",
                BODY_MASS_INDEX,
                number="24.6",
                units=KG_PER_SQUARE_METRE,
            ),
            _row(
                "TID 10024 row 14",
                "CONTAINS",
                "TEXT",
                RECENT_PHYSICAL_ACTIVITY,
                text=f"{SENTINEL} RAN TO CLINIC",
            ),
        ],
    )
    if not rows:
        return []
    return [item("CONTAINS", "CONTAINER", PATIENT_CHARACTERISTICS, *rows)]


def _step(performed):
    """Return TID 11006 row 4, TID 11007, one manual step, with its M rows.

    The step is a diagnostic administration (row 6, from CID 72) given
    intravenously (row 10, from CID 11) by hand (row 4, from CID 63), so
    that row 5, the role of the person who gave it, from CID 7450, is
    required, and the rows required only of automated administration are
    absent. It has one phase (row 13, TID 11008), whose total volume (row 6)
    is required. A plan numbers the step (TID 11007 row 20); a performed
    administration gives the step and its phase UIDs (TID 11007 row 3 and
    TID 11008 row 3) and the phase its start (TID 11008 row 7).
    """
    if performed:
        step_uid = [
            item(
                "CONTAINS",
                "UIDREF",
                PERFORMED_STEP_UID_CONCEPT,
                text=PERFORMED_STEP_UID,
            )
        ]
        phase_uid = [
            item(
                "CONTAINS",
                "UIDREF",
                PERFORMED_PHASE_UID_CONCEPT,
                text=PERFORMED_PHASE_UID,
            )
        ]
        start = [item("CONTAINS", "DATETIME", DATETIME_STARTED, text=PHASE_START)]
        number = []
    else:
        step_uid = phase_uid = start = []
        number = [
            item("CONTAINS", "NUM", STEP_SEQUENCE_NUMBER, number="1", units=NO_UNITS)
        ]
    phase = item(
        "CONTAINS",
        "CONTAINER",
        ADMINISTRATION_PHASE,
        item("CONTAINS", "TEXT", PHASE_IDENTIFIER, text=f"{SENTINEL} PHASE 1"),
        *phase_uid,
        item("CONTAINS", "NUM", TOTAL_PHASE_VOLUME, number="80", units=MILLILITRE),
        *start,
    )
    return item(
        "CONTAINS",
        "CONTAINER",
        ADMINISTRATION_STEP,
        item("CONTAINS", "TEXT", STEP_IDENTIFIER, text=f"{SENTINEL} STEP 1"),
        *step_uid,
        item("CONTAINS", "CODE", ADMINISTRATION_MODE, code=MANUAL_ADMINISTRATION),
        item("CONTAINS", "CODE", PERSON_ROLE_IN_ORGANIZATION, code=NURSE),
        item("CONTAINS", "CODE", STEP_TYPE, code=DIAGNOSTIC_ADMINISTRATION),
        item("CONTAINS", "CODE", ROUTE_OF_ADMINISTRATION, code=INTRAVENOUS_ROUTE),
        phase,
        *number,
    )


def _steps(optional, performed):
    """Return TID 11001 and TID 11020 row 10, TID 11006, with its name (row 2)."""
    return item(
        "CONTAINS",
        "CONTAINER",
        ADMINISTRATION_STEPS,
        item("CONTAINS", "TEXT", STEPS_NAME, text=f"{SENTINEL} CT ANGIOGRAM"),
        *_chosen(
            optional,
            [
                _row(
                    "TID 11006 row 3",
                    "CONTAINS",
                    "TEXT",
                    STEPS_DESCRIPTION,
                    text=f"{SENTINEL} BOLUS THEN FLUSH",
                ),
                ("TID 11006 row 4", lambda: _step(performed)),
            ],
        ),
    )


def planned_tree(optional=()):
    """Return the root of a planned imaging agent administration's tree, TID 11001.

    TID 11001 rows 1, 3, 4, 7, and 10 are required: the title, an observer,
    a person (TID 1002), the procedure's context (TID 1005, none of whose
    rows is required), one agent's information (TID 11002), and the steps
    (TID 11006).

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`PLANNED_OPTIONAL_ROWS`.
    """
    _checked(optional, PLANNED_OPTIONAL_ROWS)
    return item(
        None,
        "CONTAINER",
        PLANNED_ADMINISTRATION_TITLE,
        *_chosen(optional, [("TID 11001 row 2", _language)]),
        *_observation_context([key for key in optional if key.startswith("TID 1005 ")]),
        *_patient_characteristics(optional),
        _agent_information(optional, "TID 11004 row 22"),
        *_chosen(
            optional,
            [
                _row(
                    "TID 11001 row 8",
                    "CONTAINS",
                    "TEXT",
                    COMMENT,
                    text=f"{SENTINEL} WARM IF POSSIBLE",
                )
            ],
        ),
        _steps(optional, performed=False),
    )


def _adverse_events():
    """Return TID 11020 row 13, TID 11021, with one adverse event (row 3, M).

    The event, from CID 60, has its detection datetime (row 6, M).
    """
    event = item(
        "CONTAINS",
        "CODE",
        ADVERSE_EVENT,
        item(
            "HAS PROPERTIES",
            "DATETIME",
            ADVERSE_EVENT_DETECTION,
            text=ADVERSE_EVENT_DATETIME,
        ),
        code=NAUSEA_AND_VOMITING,
    )
    return item("CONTAINS", "CONTAINER", ADVERSE_EVENTS, event)


def performed_tree(optional=()):
    """Return the root of a performed imaging agent administration's tree, TID 11020.

    TID 11020 rows 1, 3, 7, 10, and 12 are required: the title, an
    observer, a person (TID 1002), one agent's information (TID 11002), the
    steps (TID 11006), and the completion status, from CID 67, complete.
    ``"TID 11020 row 11"`` references the plan that the administration
    followed.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from :data:`PERFORMED_OPTIONAL_ROWS`.
    """
    _checked(optional, PERFORMED_OPTIONAL_ROWS)
    plan = _row(
        "TID 11020 row 11",
        "CONTAINS",
        "COMPOSITE",
        PLANNED_ADMINISTRATION_INSTANCE,
        sop_class=PLANNED_ADMINISTRATION_SR,
        sop_instance=PLANNED_ADMINISTRATION[1],
    )
    return item(
        None,
        "CONTAINER",
        PERFORMED_ADMINISTRATION_TITLE,
        *_chosen(optional, [("TID 11020 row 2", _language)]),
        *_observation_context([key for key in optional if key.startswith("TID 1005 ")]),
        *_patient_characteristics(optional),
        _agent_information(optional, "TID 11004 row 23"),
        *_chosen(
            optional,
            [
                _row(
                    "TID 11020 row 8",
                    "CONTAINS",
                    "TEXT",
                    SUMMARY,
                    text=f"{SENTINEL} UNEVENTFUL",
                )
            ],
        ),
        _steps(optional, performed=True),
        *_chosen(optional, [plan]),
        item("CONTAINS", "CODE", COMPLETION_STATUS, code=COMPLETE),
        *_chosen(optional, [("TID 11020 row 13", _adverse_events)]),
    )


ACQUISITION_CONTEXT_OPTIONAL_ROWS = (
    "TID 8101 row 5",
    "TID 8101 row 6",
    "TID 8101 row 8",
    "TID 8101 row 9",
    "TID 8101 row 10",
    "TID 8121 row 2b",
    "TID 8121 row 25",
    "TID 8101 row 14",
)


def _housing(optional):
    """Return TID 8101 row 10, TID 8121 "Animal Housing", with ``optional``'s rows."""
    return item(
        "CONTAINS",
        "CONTAINER",
        ANIMAL_HOUSING,
        *_chosen(
            optional,
            [
                _row(
                    "TID 8121 row 2b",
                    "CONTAINS",
                    "TEXT",
                    ANIMAL_ROOM_IDENTIFIER,
                    text=f"{SENTINEL} ROOM 4",
                ),
                _row(
                    "TID 8121 row 25",
                    "CONTAINS",
                    "NUM",
                    ENVIRONMENTAL_TEMPERATURE,
                    number="22",
                    units=CELSIUS,
                ),
            ],
        ),
    )


def _animal_handling(optional):
    """Return TID 8101 row 6, the animal's handling during imaging.

    Its phase (row 7, from CID 634) is required. ``optional`` adds its start
    and end (rows 8 and 9), its housing (row 10, TID 8121), and the
    circadian effects (row 14, TID 8170), with the time the lights came on
    (TID 8170 row 4).
    """
    circadian = item(
        "CONTAINS",
        "CONTAINER",
        CIRCADIAN_EFFECTS,
        item("CONTAINS", "TIME", LIGHTS_ON_TIME, text=LIGHTS_ON),
    )
    return item(
        "CONTAINS",
        "CONTAINER",
        ANIMAL_HANDLING,
        item(
            "HAS CONCEPT MOD",
            "CODE",
            PHASE_OF_ANIMAL_HANDLING,
            code=general.IMAGING_PROCEDURE,
        ),
        *_chosen(
            optional,
            [
                _row(
                    "TID 8101 row 8",
                    "CONTAINS",
                    "DATETIME",
                    DATETIME_STARTED,
                    text=HANDLING_START,
                ),
                _row(
                    "TID 8101 row 9",
                    "CONTAINS",
                    "DATETIME",
                    DATETIME_ENDED,
                    text=HANDLING_END,
                ),
                ("TID 8101 row 10", lambda: _housing(optional)),
                ("TID 8101 row 14", lambda: circadian),
            ],
        ),
    )


def acquisition_context_tree(optional=()):
    """Return the root of a preclinical acquisition context's tree, TID 8101.

    TID 8101 rows 1, 2, and 3 are required: the title, the language (TID
    1204 row 1), and the observation context (TID 1001), whose observer, a
    person, is named. ``"TID 8101 row 5"`` adds TID 8110 "Biosafety
    Conditions" with a comment (its row 4), and ``"TID 8101 row 6"`` the
    animal's handling during imaging.

    Parameters
    ----------
    optional : collection of str
        The optional rows to include, from
        :data:`ACQUISITION_CONTEXT_OPTIONAL_ROWS`.
    """
    _checked(optional, ACQUISITION_CONTEXT_OPTIONAL_ROWS)
    biosafety = item(
        "CONTAINS",
        "CONTAINER",
        BIOSAFETY_CONDITIONS,
        item("CONTAINS", "TEXT", COMMENT, text=f"{SENTINEL} ISOLATED"),
    )
    return item(
        None,
        "CONTAINER",
        PRECLINICAL_CONTEXT,
        _language(),
        *_observation_context(()),
        *_chosen(
            optional,
            [
                ("TID 8101 row 5", lambda: biosafety),
                ("TID 8101 row 6", lambda: _animal_handling(optional)),
            ],
        ),
    )


def implantation_plan(optional=(), *, verified=False):
    """Return an Implantation Plan SR Document whose tree is :func:`implantation_tree`.

    ``verified`` gives it the Verification Flag VERIFIED, with a Verifying
    Observer Sequence, rather than UNVERIFIED. The implant templates that it
    references belong to no study or series (PS3.3 Sections A.61 and A.62), so the
    Current Requested Procedure Evidence Sequence, which would list them,
    cannot be built and is left out; it lists the CT image of ``"TID 7000
    row 30"`` only, where that row is included.
    """
    evidence = (
        _evidence(CT_IMAGE[0], CT_IMAGE_STORAGE, CT_IMAGE[1])
        if "TID 7000 row 30" in optional
        else None
    )
    return _report(
        (IMPLANTATION_PLAN_SR, IMPLANTATION_PLAN, "7000"),
        implantation_tree(optional),
        verified,
        evidence,
    )


def echo_report(
    optional=(), *, measurement=LV_GLOBAL_LONGITUDINAL_STRAIN, verified=False
):
    """Return a Simplified Adult Echo SR whose tree is :func:`echo_tree`.

    ``verified`` is as for :func:`implantation_plan`. The Timezone Module,
    which the IOD requires, gives the offset from UTC.
    """
    dataset = _report(
        (SIMPLIFIED_ADULT_ECHO_SR, ECHO_REPORT, "5300"),
        echo_tree(optional, measurement),
        verified,
    )
    dataset.TimezoneOffsetFromUTC = TIMEZONE
    return dataset


def planned_administration(optional=(), *, verified=False):
    """Return a Planned Imaging Agent Administration SR whose tree is :func:`planned_tree`.

    ``verified`` is as for :func:`implantation_plan`.
    """
    return _report(
        (PLANNED_ADMINISTRATION_SR, PLANNED_ADMINISTRATION, "11001"),
        planned_tree(optional),
        verified,
    )


def performed_administration(optional=(), *, verified=False):
    """Return a Performed Imaging Agent Administration SR whose tree is :func:`performed_tree`.

    ``verified`` is as for :func:`implantation_plan`. The Synchronization
    Module, which the IOD requires, synchronises the injector to UTC. With
    ``"TID 11020 row 11"``, its evidence is the plan that it references.
    """
    evidence = (
        _evidence(
            PLANNED_ADMINISTRATION[0],
            PLANNED_ADMINISTRATION_SR,
            PLANNED_ADMINISTRATION[1],
        )
        if "TID 11020 row 11" in optional
        else None
    )
    dataset = _report(
        (PERFORMED_ADMINISTRATION_SR, PERFORMED_ADMINISTRATION, "11020"),
        performed_tree(optional),
        verified,
        evidence,
    )
    dataset.SynchronizationFrameOfReferenceUID = UTC
    dataset.SynchronizationTrigger = "NO TRIGGER"
    dataset.AcquisitionTimeSynchronized = "Y"
    return dataset


def acquisition_context(optional=(), *, verified=False):
    """Return an Acquisition Context SR whose tree is :func:`acquisition_context_tree`.

    ``verified`` is as for :func:`implantation_plan`.
    """
    return _report(
        (ACQUISITION_CONTEXT_SR, ACQUISITION_CONTEXT, "8101"),
        acquisition_context_tree(optional),
        verified,
    )
