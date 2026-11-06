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

"""The content trees of the synthetic corpus's planning and procedure reports.

Each function gives the root of a tree that follows the root template that
PS3.3 2026d Section A.35 names for an IOD:

- :func:`implantation_plan_tree`, of an Implantation Plan SR Document, TID
  7000 "Implantation Plan" (Section A.35.12);
- :func:`echo_tree`, of a Simplified Adult Echo SR, TID 5300 "Simplified
  Echo Procedure Report" (Section A.35.17);
- :func:`planned_administration_tree` and
  :func:`performed_administration_tree`, of a Planned and a Performed
  Imaging Agent Administration SR, TID 11001 "Planned Imaging Agent
  Administration" and TID 11020 "Performed Imaging Agent Administration"
  (Sections A.35.19 and A.35.20); and
- :func:`acquisition_context_tree`, of an Acquisition Context SR, TID 8101
  "Preclinical Small Animal Image Acquisition Context", the template that
  Section A.35.16 names for its root.

As in :mod:`~pymedphys._dicom.deidentify.synthetic_content_trees`, whose
content item builders these share, each holds only the rows that its
templates require where they are included, for the procedure that its
docstring names; each content item's relationship, Value Type, and concept
name is a row of a template of DICOM PS3.16 2026d, cited beside it; and each
coded value is one of the context group that the row names, with the Code
Meanings of PS3.16 Annex D for DCM codes, and those the templates and
context groups give for the others.

The value of each UIDREF or PNAME item, the only Value Types among the
required rows that can identify a person or a time, comes from the caller,
so that the synthetic corpus can plant a marker in it. The instances that a
COMPOSITE item references are the caller's too: the two implant templates
of an implantation plan, which belong to no patient, study, or series
(PS3.3 Section A.61), and the plan that a performed administration
followed. Every other
value is a code, a number, or the fixed text of an implant component's
identifier, an imaging agent's identifier, or the name of its
administration steps, the same in every tree. The tests build the reports
with their optional rows besides, from the same templates
(``tests/dicom/_synthetic_procedure_reports.py``).
"""

from __future__ import annotations

from pymedphys._imports import pydicom

from .synthetic_content_trees import (
    ENGLISH,
    LANGUAGE,
    PERSON_OBSERVER_NAME,
    Code,
    Values,
    item,
)

# The SOP Class of the implant templates that an implantation plan
# references, Generic Implant Template Storage, which PS3.4 Table B.5-1 does
# not list.
GENERIC_IMPLANT_TEMPLATE_STORAGE = "1.2.840.10008.5.1.4.43.1"

# Root concepts.
IMPLANTATION_PLAN = Code("112345", "DCM", "Implantation Plan")
ADULT_ECHO_REPORT = Code("125200", "DCM", "Adult Echocardiography Procedure Report")
PLANNED_ADMINISTRATION = Code("130226", "DCM", "Planned Imaging Agent Administration")
PERFORMED_ADMINISTRATION = Code(
    "130227", "DCM", "Performed Imaging Agent Administration"
)
PRECLINICAL_CONTEXT = Code(
    "127001", "DCM", "Preclinical Small Animal Imaging Acquisition Context"
)
# TID 7000.
IMPLANT_COMPONENT_LIST = Code("112360", "DCM", "Implant Component List")
SELECTED_IMPLANT_COMPONENT = Code("112346", "DCM", "Selected Implant Component")
COMPONENT_ID = Code("112347", "DCM", "Component ID")
FRAME_OF_REFERENCE_UID = Code("112227", "DCM", "Frame of Reference UID")
MANUFACTURER_IMPLANT_TEMPLATE = Code("112371", "DCM", "Manufacturer Implant Template")
# TID 5300 and 5301; the measurement is one of CID 12309 "Core Echo Strain
# Measurement", which CID 12300 includes, coded in DCM, as the measurements
# that CID 12300 lists itself are not.
PRE_COORDINATED_MEASUREMENTS = Code("125301", "DCM", "Pre-coordinated Measurements")
POST_COORDINATED_MEASUREMENTS = Code("125302", "DCM", "Post-coordinated Measurements")
ADHOC_MEASUREMENTS = Code("125303", "DCM", "Adhoc Measurements")
LV_GLOBAL_LONGITUDINAL_STRAIN = Code(
    "130686", "DCM", "LV End-systolic GLS Multiview Mean (Endocardial)"
)
# TID 11001, 11020, 11002, 11004, and 11006.
IMAGING_AGENT_INFORMATION = Code("130183", "DCM", "Imaging Agent Information")
IMAGING_AGENT_IDENTIFIER = Code("130254", "DCM", "Imaging Agent Identifier")
IMAGING_AGENT_WARMED = Code("130187", "DCM", "Imaging Agent Warmed")
COMPONENT_USAGE = Code("130191", "DCM", "Imaging Agent Component Usage")
IMAGING_AGENT_COMPONENT = Code("130238", "DCM", "Imaging Agent Component")
DRUG_ADMINISTERED = Code("122083", "DCM", "Drug administered")
ADMINISTRATION_STEPS = Code("130192", "DCM", "Imaging Agent Administration Steps")
STEPS_NAME = Code("130200", "DCM", "Imaging Agent Administration Steps Name")
PLANNED_ADMINISTRATION_INSTANCE = Code(
    "130236", "DCM", "Planned Imaging Agent Administration SOP Instance"
)
COMPLETION_STATUS = Code(
    "130211", "DCM", "Imaging Agent Administration Completion Status"
)

# Coded values, each from the context group cited beside it, and units.
NO = Code("373067005", "SCT", "No")  # CID 230
IOHEXOL = Code("109218004", "SCT", "Iohexol")  # CID 12
COMPLETE = Code("255594003", "SCT", "Complete")  # CID 67
PERCENT = Code("%", "UCUM", "%")  # CID 12309

# The fixed text of the TEXT items that the templates require.
COMPONENT_IDENTIFIER = "FIXTURE FEMORAL STEM"
AGENT_IDENTIFIER = "FIXTURE SYRINGE A"
STEPS_NAME_TEXT = "FIXTURE CONTRAST BOLUS"


def _observer(values: Values) -> pydicom.Dataset:
    """Return TID 1001's observer: a person, by TID 1002 and TID 1003 row 1.

    TID 1002 row 1, the Observer Type, is absent, so the observer is a
    person.
    """
    return item("HAS OBS CONTEXT", "PNAME", PERSON_OBSERVER_NAME, text=values("PNAME"))


def _template(concept: Code | None, sop_instance: str) -> pydicom.Dataset:
    """Return a COMPOSITE item that references the implant template ``sop_instance``."""
    return item(
        "CONTAINS",
        "COMPOSITE",
        concept,
        sop_class=GENERIC_IMPLANT_TEMPLATE_STORAGE,
        sop_instance=sop_instance,
    )


def implantation_plan_tree(
    values: Values, selected: str, manufacturers: str
) -> pydicom.Dataset:
    """Return the root of an implantation plan's tree, TID 7000.

    TID 7000 rows 1, 3, and 6 are required: the title, the observation
    context (TID 1001), whose observer, a person, is named, and the Implant
    Component List, which holds one Selected Implant Component (row 8) with
    its required rows: its Component ID (row 9), the template that was
    selected (row 11, unnamed), its Frame of Reference UID (row 12), and the
    manufacturer's template that it derives from (row 13). With one
    component, row 10, its type, is absent; no earlier or related plan
    exists, so rows 4 and 5 are absent; and the planning information (rows
    28 to 35) and the intraoperative information (rows 36 to 41) are
    optional and left out.

    Parameters
    ----------
    values : callable
        Returns the value of the Person Observer Name and of the
        component's Frame of Reference UID, given each one's Value Type, in
        that order.
    selected, manufacturers : str
        The SOP Instance UIDs of the selected template and of the
        manufacturer's template.
    """
    observer = _observer(values)
    frame_of_reference = values("UIDREF")
    return item(
        None,
        "CONTAINER",
        IMPLANTATION_PLAN,
        # TID 7000 row 3, TID 1001 row 1.
        observer,
        # TID 7000 row 6, M, and row 8, M: TID 7000 rows 9, 11, 12, and 13.
        item(
            "CONTAINS",
            "CONTAINER",
            IMPLANT_COMPONENT_LIST,
            item(
                "CONTAINS",
                "CONTAINER",
                SELECTED_IMPLANT_COMPONENT,
                item("CONTAINS", "TEXT", COMPONENT_ID, text=COMPONENT_IDENTIFIER),
                _template(None, selected),
                item(
                    "CONTAINS",
                    "UIDREF",
                    FRAME_OF_REFERENCE_UID,
                    text=frame_of_reference,
                ),
                _template(MANUFACTURER_IMPLANT_TEMPLATE, manufacturers),
            ),
        ),
    )


def echo_tree(values: Values) -> pydicom.Dataset:
    """Return the root of a simplified adult echo report's tree, TID 5300.

    TID 5300 rows 1, 3, 10, 12, and 14 are required: the title, the
    observation context (TID 1001), whose observer, a person, is named, and
    the three containers of measurements, of which only the
    pre-coordinated one requires an item (row 11, TID 5301 row 1). Its one
    measurement, a strain of the left ventricle, is a sample that is not
    flagged as preferred, so TID 5301 rows 2 and 3 are absent. The
    procedure's description (row 4) and the language (row 2) are optional
    and left out.

    Parameters
    ----------
    values : callable
        Returns the value of the Person Observer Name, given its Value Type.
    """
    return item(
        None,
        "CONTAINER",
        ADULT_ECHO_REPORT,
        # TID 5300 row 3, TID 1001 row 1.
        _observer(values),
        # TID 5300 rows 10 and 11, TID 5301 row 1.
        item(
            "CONTAINS",
            "CONTAINER",
            PRE_COORDINATED_MEASUREMENTS,
            item(
                "CONTAINS",
                "NUM",
                LV_GLOBAL_LONGITUDINAL_STRAIN,
                number="-19.5",
                units=PERCENT,
            ),
        ),
        # TID 5300 rows 12 and 14, M, which require no item.
        item("CONTAINS", "CONTAINER", POST_COORDINATED_MEASUREMENTS),
        item("CONTAINS", "CONTAINER", ADHOC_MEASUREMENTS),
    )


def _agent_information() -> pydicom.Dataset:
    """Return TID 11001 and TID 11020 row 7, TID 11002, with its M rows.

    The agent is identified (row 2) and not warmed (row 3, from CID 230),
    and its one component usage (row 4) includes TID 11004 (row 5), whose
    row 2, the drug administered, is iohexol, from CID 12; with one usage,
    row 6 is absent.
    """
    return item(
        "CONTAINS",
        "CONTAINER",
        IMAGING_AGENT_INFORMATION,
        item("CONTAINS", "TEXT", IMAGING_AGENT_IDENTIFIER, text=AGENT_IDENTIFIER),
        item("CONTAINS", "CODE", IMAGING_AGENT_WARMED, code=NO),
        item(
            "CONTAINS",
            "CONTAINER",
            COMPONENT_USAGE,
            item(
                "CONTAINS",
                "CONTAINER",
                IMAGING_AGENT_COMPONENT,
                item("CONTAINS", "CODE", DRUG_ADMINISTERED, code=IOHEXOL),
            ),
        ),
    )


def _steps() -> pydicom.Dataset:
    """Return TID 11001 and TID 11020 row 10, TID 11006, with its name (row 2).

    Its description (row 3) and its steps (row 4, TID 11007) are optional and
    left out.
    """
    return item(
        "CONTAINS",
        "CONTAINER",
        ADMINISTRATION_STEPS,
        item("CONTAINS", "TEXT", STEPS_NAME, text=STEPS_NAME_TEXT),
    )


def planned_administration_tree(values: Values) -> pydicom.Dataset:
    """Return the root of a planned imaging agent administration's tree, TID 11001.

    TID 11001 rows 1, 3, 4, 7, and 10 are required: the title, an observer,
    a person (TID 1002), the procedure's context (TID 1005, none of whose
    rows is required, so that it adds no item), one agent's information
    (TID 11002), and the steps (TID 11006). The language (row 2), the
    patient's characteristics (row 6, TID 10024), and a comment (row 8) are
    optional and left out.

    Parameters
    ----------
    values : callable
        Returns the value of the Person Observer Name, given its Value Type.
    """
    return item(
        None,
        "CONTAINER",
        PLANNED_ADMINISTRATION,
        # TID 11001 row 3, TID 1002 row 2, TID 1003 row 1.
        _observer(values),
        # TID 11001 rows 7 and 10.
        _agent_information(),
        _steps(),
    )


def performed_administration_tree(
    values: Values, plan: tuple[str, str]
) -> pydicom.Dataset:
    """Return the root of a performed imaging agent administration's tree, TID 11020.

    TID 11020 rows 1, 3, 7, 10, and 12 are required: the title, an observer,
    a person (TID 1002), one agent's information (TID 11002), the steps (TID
    11006), and the completion status, from CID 67, complete. The
    administration followed a plan, so row 11, which references it, is
    required too. The language (row 2), the patient's characteristics (row
    6, TID 10024), a summary (row 8), and the adverse events (row 13, TID
    11021) are optional and left out.

    Parameters
    ----------
    values : callable
        Returns the value of the Person Observer Name, given its Value Type.
    plan : tuple of str
        The SOP Class and SOP Instance UIDs of the Planned Imaging Agent
        Administration SR that the administration followed.
    """
    return item(
        None,
        "CONTAINER",
        PERFORMED_ADMINISTRATION,
        # TID 11020 row 3, TID 1002 row 2, TID 1003 row 1.
        _observer(values),
        # TID 11020 rows 7 and 10.
        _agent_information(),
        _steps(),
        # TID 11020 row 11, MC.
        item(
            "CONTAINS",
            "COMPOSITE",
            PLANNED_ADMINISTRATION_INSTANCE,
            sop_class=plan[0],
            sop_instance=plan[1],
        ),
        # TID 11020 row 12, M.
        item("CONTAINS", "CODE", COMPLETION_STATUS, code=COMPLETE),
    )


def acquisition_context_tree(values: Values) -> pydicom.Dataset:
    """Return the root of a preclinical acquisition context's tree, TID 8101.

    TID 8101 rows 1, 2, and 3 are required: the title, the language (TID
    1204 row 1), and the observation context (TID 1001), whose observer, a
    person, is named. The biosafety conditions (row 5, TID 8110) and the
    animal's handling (row 6) are optional and left out.

    Parameters
    ----------
    values : callable
        Returns the value of the Person Observer Name, given its Value Type.
    """
    return item(
        None,
        "CONTAINER",
        PRECLINICAL_CONTEXT,
        # TID 8101 row 2, TID 1204 row 1.
        item("HAS CONCEPT MOD", "CODE", LANGUAGE, code=ENGLISH),
        # TID 8101 row 3, TID 1001 row 1.
        _observer(values),
    )
