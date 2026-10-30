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
:func:`radiopharmaceutical_dose_tree` that of a Radiopharmaceutical Radiation
Dose SR, which follows TID 10021 "Radiopharmaceutical Radiation Dose". Each
holds only the rows that its templates require where they are included, for
the procedure that its docstring names, apart from the templates that it
names as left out: the report that Clean Structured Content is first
assessed on (D-047). Each content item's relationship, Value Type, and
concept name is a row of a template of DICOM PS3.16 2026d, cited beside it,
and each coded value is one of the context group that the row names. Code
meanings are those of PS3.16 Annex D for DCM codes, and those the templates
and context groups give for the others.

The value of each content item that can identify a person, a device, or a
time, a UIDREF, DATETIME, or PNAME item, comes from the caller, so that the
synthetic corpus (:mod:`~pymedphys._dicom.deidentify.synthetic_corpus`) can
plant a marker in it; but the Study Instance UID that names the scope of
accumulation, which is the study's own. Every other value is a code or a
number, the same in every tree. The tests build reports with the optional
rows besides, from the same codes (``tests/dicom/_synthetic_dose_reports.py``).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

from pymedphys._imports import pydicom

X_RAY_RADIATION_DOSE_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.67"
RADIOPHARMACEUTICAL_RADIATION_DOSE_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.68"
# The root template of each, as Content Template Sequence (0040,A504) names it.
ROOT_TEMPLATES = {
    X_RAY_RADIATION_DOSE_SR_STORAGE: "10001",
    RADIOPHARMACEUTICAL_RADIATION_DOSE_SR_STORAGE: "10021",
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
# Units, as the rows give them.
GRAY_SQUARE_METRE = Code("Gy.m2", "UCUM", "Gy.m2")
SECONDS = Code("s", "UCUM", "seconds")
MEGABECQUEREL = Code("MBq", "UCUM", "MBq")

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
        ``number`` and ``units`` for NUM, and ``text`` for TEXT, PNAME,
        DATETIME, and UIDREF.
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
