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

"""Reviewed supplementary (L2) actions for attributes that Table E.1-1 omits."""

# The tests share the hand-checked lists of attributes and the helpers that
# rewrite the rules file below, so they stay in one module.
# pylint: disable = too-many-lines

import collections
import dataclasses
import itertools
import json
import re
import types

from pymedphys._imports import pytest, tomlkit

from pymedphys._dicom.deidentify import (
    actions,
    compound_actions,
    element_rules,
    iods,
    policy,
    scope,
    sop_classes,
    standard,
    supplementary_actions,
    temporal_roles,
    uid_roles,
)

# The actions of Table E.1-1a that never keep the value as received.
REMOVING_ACTIONS = {"X", "Z", "D", "X/Z", "Z/D", "X/D", "X/Z/D"}
TEXT_VRS = {"LO", "SH", "LT", "ST", "UC", "UT"}
TEMPORAL_VRS = {"DA", "DT", "TM"}
# The IODs of the first supported release.
# The CT and RT IODs that the first supported release has always supported,
# and the CT, MR, and PET IODs that the maintainer added on 7 October 2026.
CT_AND_RT_IODS = ("CT Image", "RT Dose", "RT Plan", "RT Structure Set")
ADDED_IODS = (
    "Enhanced CT Image",
    "Legacy Converted Enhanced CT Image",
    "MR Image",
    "Enhanced MR Image",
    "Enhanced MR Color Image",
    "Legacy Converted Enhanced MR Image",
    "MR Spectroscopy",
    "Positron Emission Tomography Image",
    "Enhanced PET Image",
    "Legacy Converted Enhanced PET Image",
)
# The IODs of the target coverage whose attributes were reviewed ahead of
# supporting them, against the CT, MR, PET, and RT IODs above, and those of
# them that the first supported release now supports.
TARGET_IODS = (
    "RT Beams Treatment Record",
    "RT Image",
    "Spatial Registration",
    "Deformable Spatial Registration",
    "Segmentation",
)
REGISTRATION_IODS = ("Spatial Registration", "Deformable Spatial Registration")
SUPPORTED_TARGET_IODS = (
    *REGISTRATION_IODS,
    "RT Beams Treatment Record",
    "RT Image",
    "Segmentation",
)
REVIEWED_AGAINST = CT_AND_RT_IODS + ADDED_IODS
# The Radiation Dose SR IODs, which the maintainer added to the planned
# coverage on 25 October 2026, whose text, UID, and date attributes were
# reviewed ahead of supporting them, against the IODs above, all of which
# the first supported release now supports.
RADIATION_DOSE_SR_IODS = (
    "X-Ray Radiation Dose SR",
    "Enhanced X-Ray Radiation Dose SR",
    "Radiopharmaceutical Radiation Dose SR",
    "Patient Radiation Dose SR",
)
SUPPORTED_DOSE_SR_IODS = RADIATION_DOSE_SR_IODS
# The IODs that the Radiation Dose SR IODs were reviewed against.
DOSE_SR_REVIEWED_AGAINST = REVIEWED_AGAINST + TARGET_IODS
# The general SR IODs, which the maintainer brought into scope with every
# other SR IOD on 25 October 2026. They use no attribute that the IODs above
# do not, so their support needed no review of their attributes.
GENERAL_SR_IODS = (
    "Basic Text SR",
    "Enhanced SR",
    "Comprehensive SR",
    "Comprehensive 3D SR",
    "Extensible SR",
)
# The other SR IODs of PS3.3 Section A.35, which the maintainer brought into
# scope with the general ones, and those of them that the first supported
# release now supports. They too use no attribute that the IODs above do
# not. Rendition Selection Document has no Storage SOP Class in the pinned
# PS3.4 Table B.5-1, so no instance is classified as it.
OTHER_SR_IODS = (
    "Key Object Selection Document",
    "Mammography CAD SR",
    "Chest CAD SR",
    "Colon CAD SR",
    "Procedure Log",
    "Spectacle Prescription Report",
    "Macular Grid Thickness and Volume Report",
    "Waveform Annotation SR",
    "Implantation Plan SR Document",
    "Simplified Adult Echo SR",
    "Planned Imaging Agent Administration SR",
    "Performed Imaging Agent Administration SR",
    "Acquisition Context SR",
    "Rendition Selection Document",
)
SUPPORTED_OTHER_SR_IODS = OTHER_SR_IODS[:8]
# The RT Ion IODs, which the maintainer added to the target coverage on 31
# October 2026, whose text, UID, and date attributes were reviewed ahead of
# supporting them, against every IOD above, and which the first supported
# release now supports.
ION_IODS = ("RT Ion Plan", "RT Ion Beams Treatment Record")
ION_REVIEWED_AGAINST = DOSE_SR_REVIEWED_AGAINST + RADIATION_DOSE_SR_IODS
# RT Brachy Treatment Record and RT Treatment Summary Record, which the
# maintainer added to the target coverage on 31 October 2026, whose
# attributes were reviewed ahead of supporting them, against every IOD above,
# and which the first supported release now supports.
RECORD_IODS = ("RT Brachy Treatment Record", "RT Treatment Summary Record")
RECORD_REVIEWED_AGAINST = ION_REVIEWED_AGAINST + ION_IODS
# Parametric Map and Real World Value Mapping, which the maintainer added to
# the target coverage on 31 October 2026 with the other IODs that RT exports
# carry, whose attributes were reviewed against every IOD above when the
# first supported release came to support them.
MAP_IODS = ("Parametric Map", "Real World Value Mapping")
MAP_REVIEWED_AGAINST = RECORD_REVIEWED_AGAINST + RECORD_IODS
# Enhanced RT Image and Enhanced Continuous RT Image, which the maintainer
# added to the target coverage on 31 October 2026, whose attributes were
# reviewed with their support, against every IOD above, and which the first
# supported release now supports.
ENHANCED_RT_IMAGE_IODS = ("Enhanced RT Image", "Enhanced Continuous RT Image")
ENHANCED_RT_IMAGE_REVIEWED_AGAINST = RECORD_REVIEWED_AGAINST + RECORD_IODS
# The 16 second-generation RT IODs, which the maintainer added to the target
# coverage on 31 October 2026, whose text, UID, and date attributes were
# reviewed ahead of supporting them, against every IOD above, and those of
# them that the first supported release now supports: RT Segment Annotation,
# RT Radiation Set, the three radiation IODs, and the three delivery
# instruction IODs.
SECOND_GENERATION_RT_IODS = (
    "RT Physician Intent",
    "RT Segment Annotation",
    "RT Radiation Set",
    "RT Radiation Record Set",
    "RT Radiation Salvage Record",
    "RT Treatment Preparation",
    "RT Patient Position Acquisition Instruction",
    "RT Beams Delivery Instruction",
    "RT Brachy Application Setup Delivery Instruction",
    "RT Radiation Set Delivery Instruction",
    "C-Arm Photon-Electron Radiation",
    "C-Arm Photon-Electron Radiation Record",
    "Tomotherapeutic Radiation",
    "Tomotherapeutic Radiation Record",
    "Robotic-Arm Radiation",
    "Robotic-Arm Radiation Record",
)
SUPPORTED_SECOND_GENERATION_RT_IODS = (
    "RT Segment Annotation",
    "RT Radiation Set",
    "C-Arm Photon-Electron Radiation",
    "Tomotherapeutic Radiation",
    "Robotic-Arm Radiation",
    "RT Beams Delivery Instruction",
    "RT Brachy Application Setup Delivery Instruction",
    "RT Radiation Set Delivery Instruction",
)
# The Nuclear Medicine Image IOD, which the maintainer added to the target
# coverage on 31 October 2026, and which the first supported release now
# supports, whose attributes the tests at the end of this module review.
NM_IODS = ("Nuclear Medicine Image",)
# The text attributes that it uses and the IODs above do not, by group,
# checked by hand against the 2026d PS3.3 Tables C.8-9 and C.8-10 and PS3.6:
# Processing Function, a description of the processing, and Energy Window
# Name, which PS3.3 calls user defined, are cleaned as descriptors; and Image
# ID, which the user or equipment generates, is among
# REMOVED_UNDER_EVERY_OPTION.
NM_OPERATOR_TEXT = {
    "(0018,5020)",  # Processing Function
    "(0054,0018)",  # Energy Window Name
}
NM_REMOVED_UNDER_EVERY_OPTION = {"(0054,0400)"}  # Image ID
# Surface Segmentation, which the maintainer brought into the target
# coverage on 31 October 2026 with the other IODs that radiotherapy exports
# carry, whose attributes were reviewed ahead of supporting it, against every
# IOD that the first supported release then supported, and which it now
# supports.
SURFACE_IODS = ("Surface Segmentation",)
# The six softcopy Presentation State IODs of PS3.3 Sections A.33.1 to A.33.4,
# A.33.6, and A.33.8, which the maintainer's pick of 31 October 2026 brought into
# the target coverage, whose attributes were reviewed against every IOD
# above but Surface Segmentation, reviewed alongside them, and which the
# first supported release now supports. The volumetric,
# advanced blending, and waveform Presentation States are not yet supported.
PRESENTATION_STATE_IODS = (
    "Grayscale Softcopy Presentation State",
    "Color Softcopy Presentation State",
    "Pseudo-Color Softcopy Presentation State",
    "Blending Softcopy Presentation State",
    "XA/XRF Grayscale Softcopy Presentation State",
    "Variable Modality LUT Softcopy Presentation State",
)
PRESENTATION_STATE_REVIEWED_AGAINST = (
    REVIEWED_AGAINST
    + SUPPORTED_TARGET_IODS
    + SUPPORTED_DOSE_SR_IODS
    + GENERAL_SR_IODS
    + SUPPORTED_OTHER_SR_IODS
    + ION_IODS
    + RECORD_IODS
    + MAP_IODS
    + ENHANCED_RT_IMAGE_IODS
)
SURFACE_REVIEWED_AGAINST = (
    REVIEWED_AGAINST
    + SUPPORTED_TARGET_IODS
    + SUPPORTED_DOSE_SR_IODS
    + GENERAL_SR_IODS
    + SUPPORTED_OTHER_SR_IODS
    + ION_IODS
    + RECORD_IODS
    + MAP_IODS
)
# Encapsulated PDF, which the maintainer added to the target coverage on 31
# October 2026 with the other IODs that RT exports carry, whose attributes
# were reviewed against the same IODs as Surface Segmentation's, beside it,
# and which the first supported release now supports.
ENCAPSULATED_PDF = "Encapsulated PDF"
ENCAPSULATED_PDF_REVIEWED_AGAINST = SURFACE_REVIEWED_AGAINST
SUPPORTED_IODS = (
    PRESENTATION_STATE_REVIEWED_AGAINST
    + SURFACE_IODS
    + SUPPORTED_SECOND_GENERATION_RT_IODS
    + NM_IODS
    + PRESENTATION_STATE_IODS
    + (ENCAPSULATED_PDF,)
)
# The IODs that the second-generation RT IODs were reviewed against:
# Nuclear Medicine Image, Surface Segmentation, the softcopy Presentation
# States and Encapsulated PDF were not supported yet. Enhanced RT Image
# IODs were already supported.
SECOND_GENERATION_REVIEWED_AGAINST = SURFACE_REVIEWED_AGAINST + ENHANCED_RT_IMAGE_IODS
CLEAN_DESCRIPTORS = "clean_descriptors"
DEVICE_IDENTITY = "retain_device_identity"
FULL_DATES = "retain_longitudinal_full_dates"
MODIFIED_DATES = "retain_longitudinal_modified_dates"
DEIDENTIFICATION_METHOD = "(0012,0063)"
ALTERNATIVE_CALENDAR_DATES = ("(0010,0033)", "(0010,0034)")
STUDY_UPDATE = "(0008,041F)"  # Study Update DateTime
# The actions that Table E.1-1 gives nearly every date under the two Retain
# Longitudinal Temporal Information Options.
DATE_OPTIONS = {FULL_DATES: "K", MODIFIED_DATES: "C"}

# The dates, times, and datetimes that Table E.1-1 omits, checked by hand
# against the 2026d PS3.6 and PS3.15: three general attributes, eight that
# PS3.6 marks DICONDE, and four that it marks DICOS.
OMITTED_DATES = {
    "(0008,0404)": "ItemInventoryDateTime",
    "(0008,0416)": "ExpirationDateTime",
    "(0008,041F)": "StudyUpdateDateTime",
    "(0014,0102)": "SecondaryReviewDate",
    "(0014,0103)": "SecondaryReviewTime",
    "(0014,1020)": "ExpiryDate",
    "(0014,3076)": "DateOfGainCalibration",
    "(0014,3077)": "TimeOfGainCalibration",
    "(0014,4076)": "ProcedureCreationDate",
    "(0014,4078)": "ProcedureExpirationDate",
    "(0014,407A)": "ProcedureLastModifiedDate",
    "(4010,1025)": "RouteSegmentStartTime",
    "(4010,1026)": "RouteSegmentEndTime",
    "(4010,102B)": "AlarmDecisionTime",
    "(4010,1041)": "OOIOwnerCreationTime",
}
# What each rule's note says Modified Dates does to the value, by the action
# of its temporal role.
SAID_OF = {
    temporal_roles.TemporalAction.SHIFT: "shifts it with the subject's other dates",
    temporal_roles.TemporalAction.DUMMY: "replaces it with a fixed dummy value",
}
# The claims that a note can make about the IODs that use its attribute,
# which the generated IOD tables can check: that none uses it, or none uses
# the only modules that define it ("which none of the IODs ... uses").
NO_GENERATED_IOD_USES_IT = re.compile(
    r"\b(?:none of the IODs whose Types are generated|no IOD whose Types are "
    r"generated|none of the generated IODs) uses\b"
)
NO_SUPPORTED_IOD_USES_IT = re.compile(
    r"\bno (?:supported IOD|IOD of the first supported release) uses\b"
)
INVENTORIED_STUDIES = "(0008,0423)"  # Inventoried Studies Sequence
# The omitted dates that, of the IODs whose Types are generated, only the
# Inventory IOD uses, in its Inventory Module, with the path and Type that
# Table C.38.1-1 gives each, checked by hand against the 2026d PS3.3.
INVENTORY_DATES = {
    "(0008,0404)": ((INVENTORIED_STUDIES,), "1"),  # Item Inventory DateTime
    "(0008,041F)": ((INVENTORIED_STUDIES,), "2"),  # Study Update DateTime
    # Expiration DateTime, in File Access Sequence (0008,041A) of each
    # inventoried instance of each inventoried series.
    "(0008,0416)": (
        (INVENTORIED_STUDIES, "(0008,0424)", "(0008,0425)", "(0008,041A)"),
        "3",
    ),
}

# Examples of each group of text attributes, from the design document.
OPERATOR_TEXT = (
    "(300A,00C2)",  # Beam Name
    "(300A,00FE)",  # Block Name
    "(300A,0183)",  # Patient Setup Label
    "(3004,0006)",  # Dose Comment
    "(300A,0402)",  # Setup Image Comment
    "(0040,A160)",  # Text Value
)
ACCESSORY_IDENTIFIERS = (
    "(300A,00D4)",  # Wedge ID
    "(300A,00F5)",  # Block Tray ID
    "(300A,0108)",  # Applicator ID
    "(300A,00E5)",  # Compensator ID
    "(300A,00DC)",  # Bolus ID
    "(300A,0421)",  # General Accessory ID
)
# The text attributes that the supported IODs use and Table E.1-1 omits that
# are removed by Type under every option, checked by hand against the 2026d
# PS3.3: names and identifiers of people, organisations, records, and
# networks, identifiers that a device reads, and the text of overlays.
REMOVED_UNDER_EVERY_OPTION = {
    "(0008,0116)",  # Coding Scheme Responsible Organization
    "(0008,0122)",  # Mapping Resource Name
    "(0010,0214)",  # Strain Stock Number
    "(0010,0217)",  # Strain Source
    "(0010,2295)",  # Breed Registration Number
    "(0018,1803)",  # NTP Source Address
    "(0024,0202)",  # Algorithm Source
    "(0040,0031)",  # Local Namespace Entity ID
    "(0040,0032)",  # Universal Entity ID
    "(0040,E001)",  # HL7 Instance Identifier
    "(0054,0400)",  # Image ID
    "(0062,0020)",  # Tracking ID
    "(0088,0130)",  # Storage Media File-set ID
    "(300A,00F9)",  # Accessory Code
    "(300A,0354)",  # Patient Support Accessory Code
    "(300A,0355)",  # Tray Accessory Code
    "(60xx,0022)",  # Overlay Description
    "(60xx,1500)",  # Overlay Label
}
# Every text attribute that the CT and RT IODs use, Table E.1-1 omits, and
# the Basic Profile keeps, checked by hand against the 2026d PS3.3: coded
# values, and technical values that the equipment or software writes. The
# added IODs keep ADDED_KEPT_TEXT too.
KEPT_TEXT = {
    "(0008,0070)",  # Manufacturer
    "(0008,0100)",  # Code Value
    "(0008,0102)",  # Coding Scheme Designator
    "(0008,0103)",  # Coding Scheme Version
    "(0008,0104)",  # Code Meaning
    "(0008,0112)",  # Coding Scheme Registry
    "(0008,0114)",  # Coding Scheme External ID
    "(0008,0119)",  # Long Code Value
    "(0008,0302)",  # Private Creator Reference
    "(0008,030C)",  # Private Data Element Name
    "(0008,030D)",  # Private Data Element Keyword
    "(0008,1090)",  # Manufacturer's Model Name
    "(0010,0213)",  # Strain Nomenclature
    "(0010,0223)",  # Genetic Modifications Nomenclature
    "(0012,0063)",  # De-identification Method, which the engine adds to
    "(0018,1020)",  # Software Versions
    "(0018,1160)",  # Filter Type
    "(0018,1210)",  # Convolution Kernel
    "(0028,1054)",  # Rescale Type
    "(0066,0031)",  # Algorithm Version
    "(0072,0054)",  # Selector Sequence Pointer Private Creator
    "(0072,0056)",  # Selector Attribute Private Creator
    "(3002,0052)",  # Fluence Mode ID
    "(300A,007B)",  # Fraction Pattern
    "(300A,0226)",  # Source Isotope Name
    "(3010,001A)",  # Manufacturer's Model Version
    "(3010,001D)",  # Device Alternate Identifier Format
    "(60xx,0045)",  # Overlay Subtype
}
# The UR attributes that Table E.1-1 omits and the supported IODs use,
# checked by hand against the 2026d PS3.3, PS3.6, and PS3.15. Two name coding
# concepts and schemes and are kept, like Code Value and Coding Scheme
# Designator; the others are removed by Type.
KEPT_URLS = {
    "(0008,010E)": "CodingSchemeURL",
    "(0008,0120)": "URNCodeValue",
}
OTHER_URLS = {
    "(0008,1190)",  # Retrieve URL
    "(0028,7FE0)",  # Pixel Data Provider URL
    "(0040,E010)",  # Retrieve URI
    "(0068,7005)",  # Relative URI Reference Within Encapsulated Document
}


def _dictionary():
    return {
        attribute.tag: attribute
        for attribute in standard.load_data_dictionary().attributes
    }


def _table_e1_1():
    return {row.tag: row for row in standard.load_table_e1_1().attributes}


def _supported_text():
    """Return the text attributes that a supported IOD uses, at any depth."""
    dictionary = _dictionary()
    tables = iods.load_iod_tables()
    return {
        definition.tag
        for name in SUPPORTED_IODS
        for definition in tables.iods[name].definitions
        if TEXT_VRS.intersection(dictionary[definition.tag].vrs)
    }


def _omitted_text():
    """Return the text attributes that a supported IOD uses and Table E.1-1 omits.

    Derived here independently of the loader: Table E.1-1 lists none of the
    supported IODs' text attributes by a masked tag, such as the Curve group's
    (50xx,xxxx), so an exact comparison of tags suffices.
    """
    return _supported_text() - set(_table_e1_1())


def _rules():
    return supplementary_actions.load_supplementary_actions().rules


def _definitions_of(tags, names=None):
    """Return where the IODs whose Types are generated define each of ``tags``.

    Each definition, at any depth, is given as the IOD's name, the module's
    name, the path, and the Type. Only the IODs in ``names`` are searched, if
    given. An IOD's definitions include those in the items of every sequence;
    the items of a table that includes itself repeat definitions already
    listed.
    """
    tables = iods.load_iod_tables()
    found = collections.defaultdict(set)
    for name in tables.iods if names is None else names:
        for definition in tables.iods[name].definitions:
            if definition.tag in tags:
                found[definition.tag].add(
                    (name, definition.module, definition.path, definition.type)
                )
    return dict(found)


def _custom_option_sets():
    """Every set of the presets' options that a custom policy accepts."""
    preset_options = [
        option
        for option in standard.OPTIONS
        if any(option in options for options in policy.PRESETS.values())
    ]
    return [
        subset
        for size in range(len(preset_options) + 1)
        for subset in itertools.combinations(preset_options, size)
        if not {DEVICE_IDENTITY, MODIFIED_DATES} <= set(subset)
    ]


def _every_policy():
    return [policy.compose_policy(preset) for preset in policy.PRESETS] + [
        policy.compose_custom_policy(options) for options in _custom_option_sets()
    ]


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06")
def test_every_person_name_that_table_e1_1_omits_has_an_action():
    listed = _table_e1_1()
    omitted = {
        tag
        for tag, attribute in _dictionary().items()
        if "PN" in attribute.vrs and tag not in listed
    }

    # Checked by hand against the 2026d PS3.6 and PS3.15.
    assert omitted == {"(0014,0104)", "(0014,2006)", "(0040,A067)"}
    assert omitted <= set(supplementary_actions.load_supplementary_actions().rules)


@pytest.mark.deid_requirement("MIDI-BP-05")
def test_the_basic_profile_keeps_no_person_name():
    # Table E.1-1 and the supplementary actions together give every person
    # name in the dictionary an action that removes or replaces it.
    listed = _table_e1_1()
    rules = supplementary_actions.load_supplementary_actions().rules
    basic = {
        tag: listed[tag].basic_profile if tag in listed else rules[tag].action
        for tag, attribute in _dictionary().items()
        if "PN" in attribute.vrs
    }

    assert len(basic) == 32
    assert set(basic.values()) <= REMOVING_ACTIONS


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_every_text_attribute_a_supported_iod_uses_and_table_e1_1_omits_has_a_rule():
    omitted = _omitted_text()

    # Checked against the 2026d PS3.3, PS3.6, and PS3.15: the combined
    # scope includes the RT objects, among them the two RT Ion IODs, which
    # add 13, the brachy and summary treatment records, which add none, the
    # Enhanced and Enhanced Continuous RT Images, which add 1, RT Segment
    # Annotation and RT Radiation Set, which add 2, Segmentation, which adds
    # 4, Surface Segmentation, which adds 2, Nuclear Medicine Image, which
    # adds 3, the two dose-report IODs, the three delivery instructions, which add 1, the six softcopy Presentation
    # State IODs, which add 7, and Encapsulated PDF, which adds 8, whose
    # supplementary rules cover 196 text attributes.
    assert len(omitted) == 196
    assert omitted <= set(_rules())
    assert {"(0008,0100)", "(300A,00C2)", "(60xx,1500)"} <= omitted


@pytest.mark.deid_requirement("MIDI-BP-06")
def test_the_rules_for_omitted_text_fall_in_the_reviewed_groups():
    rules = _rules()
    groups = collections.Counter(
        (rules[tag].action, tuple(rules[tag].options.items()))
        for tag in _omitted_text()
    )

    assert groups == {
        # Operator-typed labels and text.
        ("X/Z/D", ((CLEAN_DESCRIPTORS, "C"),)): 92,
        # Accessory and equipment identifiers.
        ("X/Z/D", ((DEVICE_IDENTITY, "K"),)): 33,
        # Coded and technical values, and De-identification Method.
        ("K", ()): 51,
        # Names and identifiers of people, organisations, records, and
        # networks, identifiers that a device reads, and the text of overlays.
        ("X/Z/D", ()): 18,
        # Patient's Birth and Death Dates in Alternative Calendar.
        ("X", ()): 2,
    }


# The text attributes that the added IODs use and that neither Table E.1-1
# nor the CT and RT IODs cover, by group, checked by hand against the 2026d
# PS3.3.
ADDED_OPERATOR_TEXT = {
    "(0018,0024)",  # Sequence Name
    "(0018,0031)",  # Radiopharmaceutical
    "(0018,0034)",  # Intervention Drug Name
    "(0018,003A)",  # Intervention Description
    "(0018,1070)",  # Radiopharmaceutical Route
    "(0018,1085)",  # PVC Rejection
    "(0018,9046)",  # Multi-Coil Configuration
    "(0018,9080)",  # Metabolite Map Description
    "(0018,9252)",  # ASL Technique Description
    "(0018,925B)",  # ASL Crusher Description
    "(0018,925E)",  # ASL Bolus Cut-off Technique
    "(0020,9421)",  # Dimension Description Label
    "(0054,1101)",  # Attenuation Correction Method
    "(0054,1103)",  # Reconstruction Method
    "(0054,1104)",  # Detector Lines of Response Used
    "(0054,1105)",  # Scatter Correction Method
}
ADDED_DEVICE_IDENTITY = {
    "(0018,1250)",  # Receive Coil Name
    "(0018,1251)",  # Transmit Coil Name
    "(0018,9041)",  # Receive Coil Manufacturer Name
    "(0018,9047)",  # Multi-Coil Element Name
    "(0018,9050)",  # Transmit Coil Manufacturer Name
}
ADDED_KEPT_TEXT = {
    "(0018,0085)",  # Imaged Nucleus
    "(0018,1064)",  # Cardiac Framing Type
    "(0018,1180)",  # Collimator/Grid Name
    "(0018,9005)",  # Pulse Sequence Name
    "(0018,9175)",  # Applicable Safety Standard Description
    "(0018,9320)",  # Image Filter
    "(0020,9056)",  # Stack ID
    "(0020,9213)",  # Dimension Index Private Creator
    "(0020,9238)",  # Functional Group Private Creator
    "(0020,9453)",  # Frame Label
}


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_the_text_that_only_the_added_ct_mr_and_pet_iods_use_has_reviewed_rules():
    dictionary = _dictionary()
    tables = iods.load_iod_tables()

    def text_of(names):
        return {
            definition.tag
            for name in names
            for definition in tables.iods[name].definitions
            if TEXT_VRS.intersection(dictionary[definition.tag].vrs)
        } - set(_table_e1_1())

    added = text_of(ADDED_IODS) - text_of(CT_AND_RT_IODS)
    rules = _rules()

    assert added == ADDED_OPERATOR_TEXT | ADDED_DEVICE_IDENTITY | ADDED_KEPT_TEXT
    assert len(added) == 31
    for tags, action, options in (
        (ADDED_OPERATOR_TEXT, "X/Z/D", {CLEAN_DESCRIPTORS: "C"}),
        (ADDED_DEVICE_IDENTITY, "X/Z/D", {DEVICE_IDENTITY: "K"}),
        (ADDED_KEPT_TEXT, "K", {}),
    ):
        for tag in tags:
            assert (rules[tag].action, dict(rules[tag].options)) == (
                action,
                options,
            ), tag


# The text attributes that the target IODs use and that neither Table E.1-1
# nor the supported IODs cover, by group, checked by hand against the 2026d
# PS3.3.
TARGET_OPERATOR_TEXT = {
    "(0062,0005)",  # Segment Label
    "(0062,0006)",  # Segment Description
    "(0062,0009)",  # Segment Algorithm Name
    "(0070,0081)",  # Content Description
    "(3002,0002)",  # RT Image Label
    "(3002,0003)",  # RT Image Name
    "(3002,0004)",  # RT Image Description
    "(3006,00C8)",  # Frame of Reference Transformation Comment
    "(3008,0012)",  # Measured Dose Description
    "(3008,0066)",  # Override Reason
    "(3008,0074)",  # Calculated Dose Reference Description
    "(3008,0202)",  # Treatment Status Comment
    "(300A,0730)",  # Treatment Termination Description
}
TARGET_DEVICE_IDENTITY = {"(3002,0020)"}  # Radiation Machine Name
TARGET_KEPT_TEXT = {"(0028,3004)"}  # Modality LUT Type
# Of them, the text that the Basic Profile keeps in RT Image, which the first
# supported release now supports.
RT_IMAGE_KEPT_TEXT = TARGET_KEPT_TEXT
TARGET_REMOVED_UNDER_EVERY_OPTION = {"(0062,0020)"}  # Tracking ID
# The UID and temporal attributes that the target IODs use and the supported
# IODs do not, all listed in Table E.1-1, checked by hand against the 2026d
# PS3.3 and PS3.15.
TARGET_UIDS = {
    "(0008,0019)",  # Pyramid UID
    "(0028,1199)",  # Palette Color Lookup Table UID
    "(0062,0021)",  # Tracking UID
    "(0064,0003)",  # Source Frame of Reference UID
    "(0070,031A)",  # Fiducial UID
}
TARGET_DATES = {
    "(3008,0024)",  # Treatment Control Point Date
    "(3008,0025)",  # Treatment Control Point Time
    "(3008,0054)",  # First Treatment Date
    "(3008,0056)",  # Most Recent Treatment Date
    "(3008,0250)",  # Treatment Date
    "(3008,0251)",  # Treatment Time
    "(300A,0741)",  # Interlock DateTime
    "(300C,0127)",  # Beam Hold Transition DateTime
}


def _used_by(names, vrs):
    """Return the attributes of ``vrs`` that the IODs in ``names`` use."""
    dictionary = _dictionary()
    tables = iods.load_iod_tables()
    return {
        definition.tag
        for name in names
        for definition in tables.iods[name].definitions
        if vrs.intersection(dictionary[definition.tag].vrs)
    }


def test_the_target_iods_have_the_documented_support():
    tables = iods.load_iod_tables()

    assert set(TARGET_IODS) <= set(tables.iods)
    assert set(TARGET_IODS) & scope.SUPPORTED_IODS == set(SUPPORTED_TARGET_IODS)
    assert set(SUPPORTED_IODS) == scope.SUPPORTED_IODS


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_the_text_that_only_the_target_iods_use_has_reviewed_rules():
    listed = set(_table_e1_1())
    target = (
        _used_by(TARGET_IODS, TEXT_VRS) - _used_by(REVIEWED_AGAINST, TEXT_VRS) - listed
    )
    rules = _rules()

    assert target == (
        TARGET_OPERATOR_TEXT
        | TARGET_DEVICE_IDENTITY
        | TARGET_KEPT_TEXT
        | TARGET_REMOVED_UNDER_EVERY_OPTION
    )
    assert len(target) == 16
    for tags, action, options in (
        (TARGET_OPERATOR_TEXT, "X/Z/D", {CLEAN_DESCRIPTORS: "C"}),
        (TARGET_DEVICE_IDENTITY, "X/Z/D", {DEVICE_IDENTITY: "K"}),
        (TARGET_KEPT_TEXT, "K", {}),
        (TARGET_REMOVED_UNDER_EVERY_OPTION, "X/Z/D", {}),
    ):
        for tag in tags:
            assert (rules[tag].action, dict(rules[tag].options)) == (
                action,
                options,
            ), tag
            assert rules[tag].note.strip(), tag


def test_every_uid_and_date_that_the_target_iods_use_has_a_role():
    listed = _table_e1_1()
    uids = uid_roles.load_uid_roles()
    temporal = temporal_roles.load_temporal_roles()
    target_uids = _used_by(TARGET_IODS, {"UI"})
    target_dates = _used_by(TARGET_IODS, TEMPORAL_VRS)

    for tag in target_uids:
        assert isinstance(uids.role(tag), uid_roles.UIDRole), tag
    for tag in target_dates:
        assert isinstance(temporal.role(tag), temporal_roles.TemporalRole), tag
    # Those that none of the IODs reviewed against uses are all listed in
    # Table E.1-1: the UIDs are replaced as identifiers of instances, and the
    # dates and times of treatment move with the subject's other dates.
    assert target_uids - _used_by(REVIEWED_AGAINST, {"UI"}) == TARGET_UIDS
    assert target_dates - _used_by(REVIEWED_AGAINST, TEMPORAL_VRS) == TARGET_DATES
    for tag in TARGET_UIDS:
        assert listed[tag].basic_profile == "U", tag
        assert uids.role(tag) is uid_roles.UIDRole.INSTANCE, tag
    for tag in TARGET_DATES:
        assert listed[tag].basic_profile in REMOVING_ACTIONS, tag
        assert temporal.role(tag) is temporal_roles.TemporalRole.SUBJECT_EVENT, tag


# The text attributes that the Radiation Dose SR IODs use and that neither the
# supported IODs nor the target IODs use, checked by hand against the 2026d
# PS3.3 and PS3.15. Table E.1-1 lists three, all in SR Document General.
RADIATION_DOSE_SR_LISTED_TEXT = {
    "(0040,2016)",  # Placer Order Number / Imaging Service Request
    "(0040,2017)",  # Filler Order Number / Imaging Service Request
    "(0040,A027)",  # Verifying Organization
}
RADIATION_DOSE_SR_OPERATOR_TEXT = {
    "(0040,A492)",  # Completion Flag Description
    "(0072,006F)",  # Selector UC Value, the text of a TABLE item's cells
}
# The UID and temporal attributes that the Radiation Dose SR IODs use and the
# supported and target IODs do not, all listed in Table E.1-1, with the role
# of each, checked by hand against the 2026d PS3.3 and PS3.15.
RADIATION_DOSE_SR_UIDS = {"(0040,A171)"}  # Observation UID
RADIATION_DOSE_SR_DATES = {
    # Verification DateTime
    "(0040,A030)": temporal_roles.TemporalRole.SUBJECT_EVENT,
    # Participation DateTime
    "(0040,A082)": temporal_roles.TemporalRole.SUBJECT_EVENT,
    # Referenced DateTime
    "(0040,A13A)": temporal_roles.TemporalRole.SUBJECT_EVENT,
    # Selector DT Value, also the DateTime of a TABLE item's cells, whose
    # meaning only the table's row and column concepts give.
    "(0072,0063)": temporal_roles.TemporalRole.OTHER,
}


def test_the_radiation_dose_sr_iods_are_generated_and_supported():
    tables = iods.load_iod_tables()

    assert set(RADIATION_DOSE_SR_IODS) <= set(tables.iods)
    assert set(RADIATION_DOSE_SR_IODS) & scope.SUPPORTED_IODS == set(
        SUPPORTED_DOSE_SR_IODS
    )


def test_the_general_sr_iods_use_no_attribute_that_the_reviewed_iods_do_not():
    tables = iods.load_iod_tables()
    reviewed = REVIEWED_AGAINST + TARGET_IODS + RADIATION_DOSE_SR_IODS

    def used(names):
        return {
            definition.tag
            for name in names
            for definition in tables.iods[name].definitions
        }

    # Of any VR, at any depth: SR Document General, SR Document Content, and
    # the Key Object Document, Key Object Document Series, and Timezone
    # Modules, which some of them add, define nothing new.
    assert set(GENERAL_SR_IODS) <= set(tables.iods)
    assert set(GENERAL_SR_IODS) <= scope.SUPPORTED_IODS
    assert used(GENERAL_SR_IODS) - used(reviewed) == set()


def test_the_other_sr_iods_use_no_attribute_that_the_reviewed_iods_do_not():
    tables = iods.load_iod_tables()
    reviewed = REVIEWED_AGAINST + TARGET_IODS + RADIATION_DOSE_SR_IODS

    def used(names):
        return {
            definition.tag
            for name in names
            for definition in tables.iods[name].definitions
        }

    # Of any VR, at any depth, the header review of every SR IOD left: the
    # Key Object Document, Synchronization, Enhanced General Equipment, and
    # Timezone Modules, which some of them add, define nothing new, so none
    # needs a rule that the reviewed IODs' attributes do not already have.
    assert set(OTHER_SR_IODS) <= set(tables.iods)
    assert set(OTHER_SR_IODS) & scope.SUPPORTED_IODS == set(SUPPORTED_OTHER_SR_IODS)
    assert used(OTHER_SR_IODS) - used(reviewed) == set()
    # Every IOD of the pinned tables with an SR Document Content Module is a
    # dose report, a general report, or one of these.
    assert {
        name
        for name, iod in tables.iods.items()
        if any(usage.module == "SR Document Content" for usage in iod.modules)
    } == set(RADIATION_DOSE_SR_IODS + GENERAL_SR_IODS + OTHER_SR_IODS)
    assert "Rendition Selection Document IOD" not in {
        row.iod for row in sop_classes.load_storage_sop_classes().rows
    }


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_the_text_that_only_the_radiation_dose_sr_iods_use_has_reviewed_rules():
    listed = _table_e1_1()
    others = DOSE_SR_REVIEWED_AGAINST
    added = _used_by(RADIATION_DOSE_SR_IODS, TEXT_VRS) - _used_by(others, TEXT_VRS)
    rules = _rules()

    assert added == RADIATION_DOSE_SR_LISTED_TEXT | RADIATION_DOSE_SR_OPERATOR_TEXT
    for tag in RADIATION_DOSE_SR_LISTED_TEXT:
        assert listed[tag].basic_profile in REMOVING_ACTIONS, tag
        assert tag not in rules, tag
    for tag in RADIATION_DOSE_SR_OPERATOR_TEXT:
        assert tag not in listed, tag
        assert (rules[tag].action, dict(rules[tag].options)) == (
            "X/Z/D",
            {CLEAN_DESCRIPTORS: "C"},
        ), tag
        assert rules[tag].note.strip(), tag


def test_every_uid_and_date_that_the_radiation_dose_sr_iods_use_has_a_role():
    listed = _table_e1_1()
    others = DOSE_SR_REVIEWED_AGAINST
    uids = uid_roles.load_uid_roles()
    temporal = temporal_roles.load_temporal_roles()
    dose_uids = _used_by(RADIATION_DOSE_SR_IODS, {"UI"})
    dose_dates = _used_by(RADIATION_DOSE_SR_IODS, TEMPORAL_VRS)

    for tag in dose_uids:
        assert isinstance(uids.role(tag), uid_roles.UIDRole), tag
    for tag in dose_dates:
        assert isinstance(temporal.role(tag), temporal_roles.TemporalRole), tag
    assert dose_uids - _used_by(others, {"UI"}) == RADIATION_DOSE_SR_UIDS
    assert dose_dates - _used_by(others, TEMPORAL_VRS) == set(RADIATION_DOSE_SR_DATES)
    for tag in RADIATION_DOSE_SR_UIDS:
        assert listed[tag].basic_profile == "U", tag
        assert uids.role(tag) is uid_roles.UIDRole.INSTANCE, tag
    for tag, role in RADIATION_DOSE_SR_DATES.items():
        assert listed[tag].basic_profile in REMOVING_ACTIONS, tag
        assert temporal.role(tag) is role, tag


# The text attributes that the RT Ion IODs use and that neither Table E.1-1 nor
# the IODs reviewed before them use, by group, checked by hand against the
# 2026d PS3.3 Tables C.8.8.25-1, C.8.8.26-1, and C.8.8.28-1 and Section
# C.8.8.25.5.
ION_OPERATOR_TEXT = {
    "(300A,0322)",  # Range Shifter Description
    "(300A,033A)",  # Lateral Spreading Device Description
    "(300A,034A)",  # Range Modulator Description
}
ION_DEVICE_IDENTITY = {
    "(300A,030F)",  # Snout ID
    "(300A,0318)",  # Range Shifter ID
    "(300A,0336)",  # Lateral Spreading Device ID
    "(300A,0346)",  # Range Modulator ID
    "(300A,0352)",  # Patient Support ID
}
ION_KEPT_TEXT = {
    "(300A,034C)",  # Beam Current Modulation ID
    "(300A,0362)",  # Range Shifter Setting
    "(300A,0372)",  # Lateral Spreading Device Setting
    "(300A,0390)",  # Scan Spot Tune ID
}
ION_REMOVED_UNDER_EVERY_OPTION = {"(300A,0354)"}  # Patient Support Accessory Code
ION_TEXT_GROUPS: tuple[tuple[set[str], str, dict[str, str]], ...] = (
    (ION_OPERATOR_TEXT, "X/Z/D", {CLEAN_DESCRIPTORS: "C"}),
    (ION_DEVICE_IDENTITY, "X/Z/D", {DEVICE_IDENTITY: "K"}),
    (ION_KEPT_TEXT, "K", {}),
    (ION_REMOVED_UNDER_EVERY_OPTION, "X/Z/D", {}),
)
# What removal by Type gives each removed attribute where the RT Ion IODs
# define it, as its note says: the accessories' identifiers are Type 1 in the
# items that describe them, their descriptions and the patient support's
# identifiers Type 3.
ION_RESOLVED = {
    **dict.fromkeys(ION_OPERATOR_TEXT, "X"),
    **dict.fromkeys(ION_DEVICE_IDENTITY - {"(300A,0352)"}, "D"),
    "(300A,0352)": "X",
    "(300A,0354)": "X",
}
# The other attributes that the RT Ion IODs use and the IODs reviewed before
# them do not, by VR, checked by hand against the 2026d PS3.3 and PS3.6:
# codes, numbers, and sequences of the ion beams, their accessories, and
# their delivery, none of which Table E.1-1 lists.
ION_OTHER_VRS = {"FL": 46, "SQ": 26, "IS": 15, "CS": 12, "DS": 8, "US": 1, "SS": 1}


def test_the_ion_iods_are_generated_and_supported():
    tables = iods.load_iod_tables()

    assert set(ION_IODS) <= set(tables.iods)
    assert set(ION_IODS) <= scope.SUPPORTED_IODS


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_the_text_that_only_the_ion_iods_use_has_reviewed_rules():
    listed = set(_table_e1_1())
    added = _used_by(ION_IODS, TEXT_VRS) - _used_by(ION_REVIEWED_AGAINST, TEXT_VRS)
    rules = _rules()

    assert not added & listed
    assert added == (
        ION_OPERATOR_TEXT
        | ION_DEVICE_IDENTITY
        | ION_KEPT_TEXT
        | ION_REMOVED_UNDER_EVERY_OPTION
    )
    assert len(added) == 13
    for tags, action, options in ION_TEXT_GROUPS:
        for tag in tags:
            assert (rules[tag].action, dict(rules[tag].options)) == (
                action,
                options,
            ), tag
            assert rules[tag].note.strip(), tag


def test_each_policy_gives_the_ion_text_the_action_of_its_group():
    for composed in _every_policy():
        for tags, action, options in ION_TEXT_GROUPS:
            selected = [a for o, a in options.items() if o in composed.options]
            for tag in tags:
                assert composed.supplementary_actions[tag] == (
                    selected[0] if selected else action
                ), (tag, composed.options)


def test_the_ion_text_that_is_removed_resolves_by_its_type_as_its_note_says():
    tables = iods.load_iod_tables()
    rules = _rules()

    for name in ION_IODS:
        iod = tables.iods[name]
        for definition in iod.definitions:
            if definition.tag not in ION_RESOLVED:
                continue
            resolved = compound_actions.resolve_in_iod(
                iod, definition.tag, definition.path, rules[definition.tag].action
            )
            assert resolved == ION_RESOLVED[definition.tag], (name, definition)
    # Each note says what removal by Type gives it where that differs from X.
    for tag, resolved in ION_RESOLVED.items():
        said = "dummy value where it is Type 1" in rules[tag].note
        assert said == (resolved == "D"), tag


def test_every_uid_date_and_name_that_the_ion_iods_use_has_a_role():
    uids = uid_roles.load_uid_roles()
    temporal = temporal_roles.load_temporal_roles()
    ion_uids = _used_by(ION_IODS, {"UI"})
    ion_dates = _used_by(ION_IODS, TEMPORAL_VRS)

    for tag in ion_uids:
        assert isinstance(uids.role(tag), uid_roles.UIDRole), tag
    for tag in ion_dates:
        assert isinstance(temporal.role(tag), temporal_roles.TemporalRole), tag
    # The IODs reviewed before them use every UID, date, time, datetime,
    # person name, and URL that the RT Ion IODs use.
    for vrs in ({"UI"}, TEMPORAL_VRS, {"PN"}, {"UR"}):
        assert not _used_by(ION_IODS, vrs) - _used_by(ION_REVIEWED_AGAINST, vrs), vrs


def test_the_ion_iods_other_new_attributes_are_kept_by_the_default():
    dictionary = _dictionary()
    tables = iods.load_iod_tables()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    other = (
        _used_by(ION_IODS, every_vr)
        - _used_by(ION_REVIEWED_AGAINST, every_vr)
        - _used_by(ION_IODS, TEXT_VRS)
    )
    listed = set(_table_e1_1())
    rules = _rules()
    uids = set(uid_roles.load_uid_roles().rules)
    by_vr = collections.Counter(vr for tag in other for vr in dictionary[tag].vrs)

    assert by_vr == ION_OTHER_VRS
    assert all(len(dictionary[tag].vrs) == 1 for tag in other)
    assert not other & (listed | set(rules) | uids)
    # So each takes the default, which keeps it where these IODs define it,
    # under every preset, with a sequence's items handled by their own rules.
    for preset in policy.PRESETS:
        rules_of = element_rules.ElementRules(policy.compose_policy(preset))
        for name in ION_IODS:
            iod = tables.iods[name]
            for definition in iod.definitions:
                tag = definition.tag.replace("(60xx,", "(6000,")
                if tag not in other:
                    continue
                rule = rules_of.rule(tag, definition.path, iod=iod)
                assert (rule.source, rule.action) == (
                    element_rules.RuleSource.DEFAULT,
                    element_rules.KEEP,
                ), (preset, name, definition)


# The attributes that RT Brachy Treatment Record and RT Treatment Summary
# Record use and the IODs reviewed before them do not, checked by hand against
# the 2026d PS3.3 Tables A.30.3-1, A.31.3-1, and C.8-58 and PS3.6: only RT
# Brachy Treatment Record adds any, all in its RT Brachy Session Record Module.
RECORD_SAFE_POSITION_DATES = {
    "(3008,0162)",  # Safe Position Exit Date
    "(3008,0164)",  # Safe Position Exit Time
    "(3008,0166)",  # Safe Position Return Date
    "(3008,0168)",  # Safe Position Return Time
}
# The others, by VR: the recorded channels, sources, applicators, shields,
# accessories, and control points delivered, and the pulses of a pulsed
# delivery.
RECORD_OTHER_VRS = {"SQ": 9, "IS": 6, "DS": 4, "CS": 1, "US": 1}
# Where removal by Type gives an attribute of these IODs an action that it
# takes nowhere in the IODs reviewed before them: Source Serial Number, which
# Table E.1-1 gives X/Z, is Type 2 in Recorded Source Sequence (3008,0100) and
# Type 3 in RT Plan's Source Sequence (300A,0210).
SOURCE_SERIAL_NUMBER = "(3008,0105)"
RECORD_NEW_RESOLUTIONS = {SOURCE_SERIAL_NUMBER: ({"Z"}, {"X"})}
BRACHY_SESSION_RECORD = "RT Brachy Session Record"


def _record_actions():
    """Return the Basic Profile action of each attribute with one, by tag.

    That of Table E.1-1 for an attribute it lists, else that of its rule.
    """
    actions_by_tag = {tag: row.basic_profile for tag, row in _table_e1_1().items()}
    for tag, rule in _rules().items():
        actions_by_tag.setdefault(tag, rule.action)
    return actions_by_tag


def _resolved_in(names, tag, action):
    """Return what removal by Type gives ``tag`` where ``names`` define it."""
    tables = iods.load_iod_tables()
    return {
        compound_actions.resolve_in_iod(
            tables.iods[name], definition.tag, definition.path, action
        )
        for name in names
        for definition in tables.iods[name].definitions
        if definition.tag == tag
    }


def test_the_brachy_and_summary_records_are_generated_and_supported():
    tables = iods.load_iod_tables()

    assert set(RECORD_IODS) <= set(tables.iods)
    assert set(RECORD_IODS) <= scope.SUPPORTED_IODS


def test_the_brachy_and_summary_records_add_only_the_brachy_session_record():
    tables = iods.load_iod_tables()
    beams = {
        (usage.module, usage.table)
        for usage in tables.iods["RT Beams Treatment Record"].modules
    }
    brachy = {
        (usage.module, usage.table)
        for usage in tables.iods["RT Brachy Treatment Record"].modules
    }
    summary = {
        (usage.module, usage.table)
        for usage in tables.iods["RT Treatment Summary Record"].modules
    }

    assert brachy - beams == {(BRACHY_SESSION_RECORD, "Table C.8-58")}
    assert summary <= beams


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_the_brachy_and_summary_records_use_no_text_without_a_reviewed_action():
    listed = set(_table_e1_1())
    rules = _rules()
    text = _used_by(RECORD_IODS, TEXT_VRS)

    assert not text - _used_by(RECORD_REVIEWED_AGAINST, TEXT_VRS)
    for tag in text - listed:
        assert rules[tag].note.strip(), tag
    # The text of the RT Brachy Session Record Module is that of the module
    # the plan's application setups are in, or of the photon record's session.
    tables = iods.load_iod_tables()
    dictionary = _dictionary()

    def text_of(name, module):
        return {
            definition.tag
            for definition in tables.iods[name].definitions
            if definition.module == module
            and TEXT_VRS.intersection(dictionary[definition.tag].vrs)
        }

    session = text_of("RT Brachy Treatment Record", BRACHY_SESSION_RECORD)
    assert session
    assert session <= (
        text_of("RT Plan", "RT Brachy Application Setups")
        | text_of("RT Beams Treatment Record", "RT Beams Session Record")
    )


def test_removal_by_type_gives_the_records_attributes_the_actions_reviewed():
    actions_by_tag = _record_actions()
    dictionary = _dictionary()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    new = {}

    for tag in sorted(_used_by(RECORD_IODS, every_vr)):
        action = actions_by_tag.get(tag)
        if action not in compound_actions.COMPOUND_ACTIONS:
            continue
        resolved = _resolved_in(RECORD_IODS, tag, action)
        reviewed = _resolved_in(RECORD_REVIEWED_AGAINST, tag, action)
        if not resolved <= reviewed:
            new[tag] = (resolved, reviewed)

    assert new == RECORD_NEW_RESOLUTIONS
    # Source Serial Number is emptied where it is Type 2, as Table E.1-1 sets,
    # and kept under Retain Device Identity, as for every device's serial
    # number.
    row = _table_e1_1()[SOURCE_SERIAL_NUMBER]
    assert (row.basic_profile, dict(row.options)) == ("X/Z", {DEVICE_IDENTITY: "K"})
    assert {
        definition.module
        for definition in iods.load_iod_tables()
        .iods["RT Brachy Treatment Record"]
        .definitions
        if definition.tag == SOURCE_SERIAL_NUMBER
    } == {BRACHY_SESSION_RECORD}


def test_every_uid_date_and_name_that_the_brachy_and_summary_records_use_has_a_role():
    uids = uid_roles.load_uid_roles()
    temporal = temporal_roles.load_temporal_roles()
    table = _table_e1_1()

    for tag in _used_by(RECORD_IODS, {"UI"}):
        assert isinstance(uids.role(tag), uid_roles.UIDRole), tag
    for tag in _used_by(RECORD_IODS, TEMPORAL_VRS):
        assert isinstance(temporal.role(tag), temporal_roles.TemporalRole), tag
    # The IODs reviewed before them use every UID, person name, and URL that
    # these IODs use, and every date, time, and datetime but the four that
    # record when a brachytherapy source left and returned to its safe
    # position, which Table E.1-1 lists as it lists Treatment Date.
    for vrs in ({"UI"}, {"PN"}, {"UR"}):
        assert not _used_by(RECORD_IODS, vrs) - _used_by(
            RECORD_REVIEWED_AGAINST, vrs
        ), vrs
    new_dates = _used_by(RECORD_IODS, TEMPORAL_VRS) - _used_by(
        RECORD_REVIEWED_AGAINST, TEMPORAL_VRS
    )
    assert new_dates == RECORD_SAFE_POSITION_DATES
    for tag in new_dates:
        assert temporal.role(tag) is temporal_roles.TemporalRole.SUBJECT_EVENT, tag
        assert (table[tag].basic_profile, dict(table[tag].options)) == (
            "D",
            DATE_OPTIONS,
        ), tag


def test_the_brachy_and_summary_records_other_new_attributes_are_kept_by_the_default():
    dictionary = _dictionary()
    tables = iods.load_iod_tables()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    new = _used_by(RECORD_IODS, every_vr) - _used_by(RECORD_REVIEWED_AGAINST, every_vr)
    other = new - RECORD_SAFE_POSITION_DATES
    listed = set(_table_e1_1())
    rules = _rules()
    uids = set(uid_roles.load_uid_roles().rules)
    by_vr = collections.Counter(vr for tag in other for vr in dictionary[tag].vrs)

    assert not new - _used_by(("RT Brachy Treatment Record",), every_vr)
    assert by_vr == RECORD_OTHER_VRS
    assert all(len(dictionary[tag].vrs) == 1 for tag in other)
    assert not other & (listed | set(rules) | uids)
    # So each takes the default, which keeps it where RT Brachy Treatment
    # Record defines it, under every preset, with a sequence's items handled
    # by their own rules.
    iod = tables.iods["RT Brachy Treatment Record"]
    for preset in policy.PRESETS:
        rules_of = element_rules.ElementRules(policy.compose_policy(preset))
        for definition in iod.definitions:
            if definition.tag not in other:
                continue
            assert definition.module == BRACHY_SESSION_RECORD, definition
            rule = rules_of.rule(definition.tag, definition.path, iod=iod)
            assert (rule.source, rule.action) == (
                element_rules.RuleSource.DEFAULT,
                element_rules.KEEP,
            ), (preset, definition)


# The text attributes that the six softcopy Presentation State IODs use and
# that neither Table E.1-1 nor the IODs reviewed before them use, by group,
# checked by hand against the 2026d PS3.3 Sections C.7.6.10, C.10.5, C.10.7,
# and C.10.11 and Table C.10-5a.
PRESENTATION_STATE_OPERATOR_TEXT = {
    "(0028,6190)",  # Mask Operation Explanation
    "(0070,0068)",  # Graphic Layer Description
    "(0070,0207)",  # Graphic Group Label
    "(0070,0208)",  # Graphic Group Description
    "(0070,0289)",  # Tick Label
}
PRESENTATION_STATE_KEPT_TEXT = {
    "(0070,0227)",  # Font Name
    "(0070,0229)",  # CSS Font Name
}
# The attributes that these IODs use, the IODs reviewed before them do not,
# and Table E.1-1 lists, with their Basic Profile actions: the Graphic
# Annotation Sequence and the text of its Text Object Sequence, and when the
# Presentation State was created.
PRESENTATION_STATE_LISTED = {
    "(0070,0001)": "D",  # Graphic Annotation Sequence
    "(0070,0006)": "D",  # Unformatted Text Value
    "(0070,0082)": "X",  # Presentation Creation Date
    "(0070,0083)": "X",  # Presentation Creation Time
}
# The others, by VR: the shutters, masks, displayed areas, spatial
# transformations, LUTs, graphic layers, groups, and annotations' geometry
# and style, and the blending and XA/XRF frame and pixel shift settings.
PRESENTATION_STATE_OTHER_VRS = {
    "CS": 31,
    "SQ": 21,
    "FL": 19,
    "US": 18,
    "IS": 9,
    "UL": 3,
    "SL": 2,
    "SS": 2,
    "DS": 1,
    "FD": 1,
    "OB": 1,
}
GRAPHIC_ANNOTATION_SEQUENCE = "(0070,0001)"
PRESENTATION_CREATION_DATES = ("(0070,0082)", "(0070,0083)")


def test_the_softcopy_presentation_states_are_generated_and_supported():
    tables = iods.load_iod_tables()

    assert set(PRESENTATION_STATE_IODS) <= set(tables.iods)
    assert set(PRESENTATION_STATE_IODS) <= scope.SUPPORTED_IODS
    # The other Presentation State IODs of the pinned tables are not yet.
    others = {
        name
        for name in tables.iods
        if name.endswith("Presentation State") and name not in PRESENTATION_STATE_IODS
    }
    assert others == {
        "Advanced Blending Presentation State",
        "Planar MPR Volumetric Presentation State",
        "Volume Rendering Volumetric Presentation State",
        "Waveform Presentation State",
        "Waveform Acquisition Presentation State",
    }
    assert not others & scope.SUPPORTED_IODS


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_the_text_that_only_the_softcopy_presentation_states_use_has_reviewed_rules():
    listed = _table_e1_1()
    rules = _rules()
    added = _used_by(PRESENTATION_STATE_IODS, TEXT_VRS) - _used_by(
        PRESENTATION_STATE_REVIEWED_AGAINST, TEXT_VRS
    )

    assert added - set(listed) == (
        PRESENTATION_STATE_OPERATOR_TEXT | PRESENTATION_STATE_KEPT_TEXT
    )
    for tags, action, options in (
        (PRESENTATION_STATE_OPERATOR_TEXT, "X/Z/D", {CLEAN_DESCRIPTORS: "C"}),
        (PRESENTATION_STATE_KEPT_TEXT, "K", {}),
    ):
        for tag in tags:
            assert tag not in listed, tag
            assert (rules[tag].action, dict(rules[tag].options)) == (
                action,
                options,
            ), tag
            assert rules[tag].note.strip(), tag
    # Tick Label, which a ruler draws over the image, takes the actions that
    # Table E.1-1 gives Unformatted Text Value, the text of a text object.
    text = listed["(0070,0006)"]
    tick = rules["(0070,0289)"]
    assert (tick.action, dict(tick.options)) == ("X/Z/D", dict(text.options))
    assert text.basic_profile == "D"


def test_every_new_attribute_of_the_softcopy_presentation_states_has_its_action():
    listed = _table_e1_1()
    rules = _rules()
    dictionary = _dictionary()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    new = _used_by(PRESENTATION_STATE_IODS, every_vr) - _used_by(
        PRESENTATION_STATE_REVIEWED_AGAINST, every_vr
    )
    text = PRESENTATION_STATE_OPERATOR_TEXT | PRESENTATION_STATE_KEPT_TEXT

    assert {
        tag: listed[tag].basic_profile for tag in new if tag in listed
    } == PRESENTATION_STATE_LISTED
    assert {tag for tag in new if tag in rules} == text
    other = new - set(PRESENTATION_STATE_LISTED) - text
    assert all(len(dictionary[tag].vrs) == 1 for tag in other)
    assert (
        collections.Counter(dictionary[tag].vrs[0] for tag in other)
        == PRESENTATION_STATE_OTHER_VRS
    )
    assert not other & set(uid_roles.load_uid_roles().rules)
    # Each other takes the default, which keeps it where its IOD defines it,
    # under every preset, with a sequence's items handled by their own rules.
    # Overlay Activation Layer (60xx,1001), the code string that names the
    # graphic layer of an overlay group, is checked in the first group.
    assert {tag for tag in other if "x" in tag} == {"(60xx,1001)"}
    other = {tag for tag in other if "x" not in tag} | {"(6000,1001)"}
    tables = iods.load_iod_tables()
    for preset in policy.PRESETS:
        rules_of = element_rules.ElementRules(policy.compose_policy(preset))
        for name in PRESENTATION_STATE_IODS:
            iod = tables.iods[name]
            for definition in iod.definitions:
                tag = definition.tag.replace("(60xx,", "(6000,")
                if tag not in other:
                    continue
                rule = rules_of.rule(tag, definition.path, iod=iod)
                assert (rule.source, rule.action) == (
                    element_rules.RuleSource.DEFAULT,
                    element_rules.KEEP,
                ), (preset, name, definition)


# The attributes that Encapsulated PDF uses and the IODs reviewed before it do
# not, checked by hand against the 2026d PS3.3 Tables A.45.1-1, C.8-24, and
# C.24-2, by group. Its Encapsulated Document Series Module uses nothing new.
# The text of its Encapsulated Document Module: the title, which can be
# copied from the PDF's own Title entry, and the media types, which the IOD
# fixes as application/pdf (PS3.3 Section A.45.1.4.1).
PDF_DOCUMENT_TITLE = {"(0042,0010)"}  # Document Title
PDF_MEDIA_TYPES = {
    "(0042,0012)",  # MIME Type of Encapsulated Document
    "(0042,0014)",  # List of MIME Types
}
# The text of its SC Equipment Module, which describes the equipment that
# captured or converted the document. Its manufacturer, model, and software
# can be a site's own system, as an MR coil's manufacturer can, so they are
# device identity, as Secondary Capture Device ID is; and the formats it
# captured, which name signal and interface formats, are kept.
PDF_CAPTURE_DEVICE = {
    "(0018,1016)",  # Secondary Capture Device Manufacturer
    "(0018,1018)",  # Secondary Capture Device Manufacturer's Model Name
    "(0018,1019)",  # Secondary Capture Device Software Versions
}
PDF_CAPTURE_FORMATS = {
    "(0018,1022)",  # Video Image Format Acquired
    "(0018,1023)",  # Digital Image Format Acquired
}
PDF_TEXT_GROUPS: tuple[tuple[set[str], str, dict[str, str]], ...] = (
    (PDF_DOCUMENT_TITLE, "X/Z/D", {CLEAN_DESCRIPTORS: "C"}),
    (PDF_MEDIA_TYPES, "K", {}),
    (PDF_CAPTURE_DEVICE, "X/Z/D", {DEVICE_IDENTITY: "K"}),
    (PDF_CAPTURE_FORMATS, "K", {}),
)
# The one new text attribute that Table E.1-1 lists: the capture device's own
# identifier, removed, and kept under Retain Device Identity.
SECONDARY_CAPTURE_DEVICE_ID = "(0018,1010)"
# The document itself, which Table E.1-1 gives D.
ENCAPSULATED_DOCUMENT = "(0042,0011)"
# A URI into the document, which a rule removes by Type.
RELATIVE_URI_IN_DOCUMENT = "(0068,7005)"
# The others: the document's length and its classification codes, which take
# the default.
PDF_OTHER_VRS = {"UL": 1, "SQ": 1}


def test_the_encapsulated_pdf_is_generated_and_supported():
    tables = iods.load_iod_tables()

    assert ENCAPSULATED_PDF in tables.iods
    assert ENCAPSULATED_PDF in scope.SUPPORTED_IODS
    # The other encapsulated documents are not supported.
    assert {
        name
        for name in tables.iods
        if name.startswith("Encapsulated ") and name in scope.SUPPORTED_IODS
    } == {ENCAPSULATED_PDF}


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_the_text_that_only_the_encapsulated_pdf_uses_has_reviewed_rules():
    listed = _table_e1_1()
    added = _used_by((ENCAPSULATED_PDF,), TEXT_VRS) - _used_by(
        ENCAPSULATED_PDF_REVIEWED_AGAINST, TEXT_VRS
    )
    rules = _rules()

    assert added - set(listed) == (
        PDF_DOCUMENT_TITLE | PDF_MEDIA_TYPES | PDF_CAPTURE_DEVICE | PDF_CAPTURE_FORMATS
    )
    assert added & set(listed) == {SECONDARY_CAPTURE_DEVICE_ID}
    row = listed[SECONDARY_CAPTURE_DEVICE_ID]
    assert (row.basic_profile, dict(row.options)) == ("X", {DEVICE_IDENTITY: "K"})
    for tags, action, options in PDF_TEXT_GROUPS:
        for tag in tags:
            assert (rules[tag].action, dict(rules[tag].options)) == (
                action,
                options,
            ), tag
            assert rules[tag].note.strip(), tag
    # The capture device's manufacturer is treated as an MR receive coil's
    # manufacturer is, which can also be a site that builds its own.
    coil_manufacturer = rules["(0018,9041)"]
    for tag in PDF_CAPTURE_DEVICE:
        assert (rules[tag].action, dict(rules[tag].options)) == (
            coil_manufacturer.action,
            dict(coil_manufacturer.options),
        ), tag


def test_each_policy_gives_the_encapsulated_pdf_text_the_action_of_its_group():
    for composed in _every_policy():
        for tags, action, options in PDF_TEXT_GROUPS:
            selected = [a for o, a in options.items() if o in composed.options]
            for tag in tags:
                assert composed.supplementary_actions[tag] == (
                    selected[0] if selected else action
                ), (tag, composed.options)


def test_the_encapsulated_pdf_title_is_emptied_where_it_is_type_2():
    tables = iods.load_iod_tables()
    iod = tables.iods[ENCAPSULATED_PDF]
    (title,) = (
        definition
        for definition in iod.definitions
        if definition.tag in PDF_DOCUMENT_TITLE
    )

    assert (title.path, title.type) == ((), "2")
    assert (
        compound_actions.resolve_in_iod(
            iod, title.tag, title.path, _rules()[title.tag].action
        )
        == "Z"
    )


def test_every_uid_date_and_name_that_the_encapsulated_pdf_uses_has_a_role():
    uids = uid_roles.load_uid_roles()
    temporal = temporal_roles.load_temporal_roles()
    names = (ENCAPSULATED_PDF,)

    for tag in _used_by(names, {"UI"}):
        assert isinstance(uids.role(tag), uid_roles.UIDRole), tag
    for tag in _used_by(names, TEMPORAL_VRS):
        assert isinstance(temporal.role(tag), temporal_roles.TemporalRole), tag
    # The IODs reviewed before it use every UID, date, time, datetime, and
    # person name that it uses, and every URL but the URI into the document.
    for vrs in ({"UI"}, TEMPORAL_VRS, {"PN"}):
        assert not _used_by(names, vrs) - _used_by(
            ENCAPSULATED_PDF_REVIEWED_AGAINST, vrs
        ), vrs
    assert _used_by(names, {"UR"}) - _used_by(
        ENCAPSULATED_PDF_REVIEWED_AGAINST, {"UR"}
    ) == {RELATIVE_URI_IN_DOCUMENT}
    assert _rules()[RELATIVE_URI_IN_DOCUMENT].action == "X/Z/D"


def test_the_encapsulated_document_takes_d_under_every_option():
    # No option of Table E.1-1 keeps or cleans the document, and no rule
    # gives it a dummy value, so an instance that holds one is sequestered.
    row = _table_e1_1()[ENCAPSULATED_DOCUMENT]

    assert (row.basic_profile, dict(row.options)) == ("D", {})
    assert ENCAPSULATED_DOCUMENT not in _rules()
    (document,) = _definitions_of({ENCAPSULATED_DOCUMENT}, (ENCAPSULATED_PDF,))[
        ENCAPSULATED_DOCUMENT
    ]
    assert document == (ENCAPSULATED_PDF, "Encapsulated Document", (), "1")


def test_the_encapsulated_pdf_other_new_attributes_are_kept_by_the_default():
    dictionary = _dictionary()
    tables = iods.load_iod_tables()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    names = (ENCAPSULATED_PDF,)
    new = _used_by(names, every_vr) - _used_by(
        ENCAPSULATED_PDF_REVIEWED_AGAINST, every_vr
    )
    other = (
        new
        - _used_by(names, TEXT_VRS)
        - {ENCAPSULATED_DOCUMENT, RELATIVE_URI_IN_DOCUMENT}
    )
    listed = set(_table_e1_1())
    rules = _rules()
    uids = set(uid_roles.load_uid_roles().rules)
    by_vr = collections.Counter(vr for tag in other for vr in dictionary[tag].vrs)

    assert by_vr == PDF_OTHER_VRS
    assert other == {"(0042,0015)", "(0040,E008)"}
    assert not other & (listed | set(rules) | uids)
    # So each takes the default, which keeps it where the IOD defines it,
    # under every preset, with the code sequence's items handled by their own
    # rules.
    iod = tables.iods[ENCAPSULATED_PDF]
    for preset in policy.PRESETS:
        rules_of = element_rules.ElementRules(policy.compose_policy(preset))
        for definition in iod.definitions:
            if definition.tag not in other:
                continue
            rule = rules_of.rule(definition.tag, definition.path, iod=iod)
            assert (rule.source, rule.action) == (
                element_rules.RuleSource.DEFAULT,
                element_rules.KEEP,
            ), (preset, definition)


# The text attributes that Enhanced RT Image and Enhanced Continuous RT Image
# use and the IODs reviewed before them do not, checked by hand against the
# 2026d PS3.3 Tables C.36.26-1, C.36.27-1, C.36.2.4.11-1 (RT Image Frame
# Radiation Acquisition Parameters Macro), 10.32-1 (Entity Long Labeling
# Macro), and 10.34-1 (Conceptual Volume Segmentation Reference and
# Combination Macro), and Section 10.34.1.1: four that Table E.1-1 lists, with
# its actions, and one that it omits, which is kept.
ENHANCED_RT_IMAGE_LISTED_TEXT = {
    "(300A,067C)": "D",  # Radiation Generation Mode Label
    "(300A,067D)": "Z",  # Radiation Generation Mode Description
    "(3010,000F)": "Z",  # Conceptual Volume Combination Description
    "(3010,0037)": "X",  # Entity Description
}
CONCEPTUAL_VOLUME_COMBINATION_EXPRESSION = "(3010,000C)"
ENHANCED_RT_IMAGE_KEPT_TEXT = {CONCEPTUAL_VOLUME_COMBINATION_EXPRESSION}
# The UIDs that they add, which Table E.1-1 lists with U.
ENHANCED_RT_IMAGE_UIDS = {
    "(300A,0785)",  # Referenced Treatment Position Group UID
    "(3010,0013)",  # Constituent Conceptual Volume UID
}
# The others, by VR: codes, numbers, and sequences of the frames'
# acquisition, the imaging and treatment devices, the treatment positions,
# and the Conceptual Volumes named.
ENHANCED_RT_IMAGE_OTHER_VRS = {"SQ": 36, "US": 11, "FD": 6, "DS": 6, "CS": 5, "IS": 1}
# Where removal by Type gives an attribute of these IODs an action that it
# takes nowhere in the IODs reviewed before them: Instance Creation Date and
# Time, which are Type 1 in the Radiotherapy Common Instance Module (PS3.3
# Table C.36.4-1) and Type 3 in the SOP Common Module.
ENHANCED_RT_IMAGE_NEW_RESOLUTIONS = {
    "(0008,0012)": ({"D"}, {"X"}),  # Instance Creation Date, X/D
    "(0008,0013)": ({"D"}, {"X"}),  # Instance Creation Time, X/Z/D
}


def test_the_enhanced_rt_images_are_generated_and_supported():
    tables = iods.load_iod_tables()

    assert set(ENHANCED_RT_IMAGE_IODS) <= set(tables.iods)
    assert set(ENHANCED_RT_IMAGE_IODS) <= scope.SUPPORTED_IODS


def test_the_enhanced_rt_images_differ_only_in_the_modules_of_their_frames():
    tables = iods.load_iod_tables()
    enhanced, continuous = (
        {(usage.module, usage.table) for usage in tables.iods[name].modules}
        for name in ENHANCED_RT_IMAGE_IODS
    )

    assert enhanced - continuous == {
        ("Multi-frame Functional Groups", "Table C.7.6.16-1"),
        ("Multi-frame Dimension", "Table C.7.6.17-1"),
        ("Frame Extraction", "Table C.12-9"),
    }
    assert continuous - enhanced == {
        ("Sparse Multi-frame Functional Groups", "Table C.7.6.29-1")
    }
    # Their macros are the same, with the same usages; only the condition of
    # Derivation Image is worded for frames in one and not the other.
    enhanced_macros, continuous_macros = (
        [
            (macro.macro, macro.section, macro.usage, macro.table)
            for macro in tables.iods[name].functional_group_macros
        ]
        for name in ENHANCED_RT_IMAGE_IODS
    )
    assert enhanced_macros == continuous_macros


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_the_text_that_only_the_enhanced_rt_images_use_has_its_reviewed_action():
    table = _table_e1_1()
    rules = _rules()
    added = _used_by(ENHANCED_RT_IMAGE_IODS, TEXT_VRS) - _used_by(
        ENHANCED_RT_IMAGE_REVIEWED_AGAINST, TEXT_VRS
    )

    assert added == {
        *ENHANCED_RT_IMAGE_LISTED_TEXT,
        CONCEPTUAL_VOLUME_COMBINATION_EXPRESSION,
    }
    for tag, action in ENHANCED_RT_IMAGE_LISTED_TEXT.items():
        assert tag not in rules, tag
        assert table[tag].basic_profile == action, tag
    # The combination expression, which Table E.1-1 omits, is kept as
    # software-generated structure, as Fraction Pattern is, under every
    # option.
    rule = rules[CONCEPTUAL_VOLUME_COMBINATION_EXPRESSION]
    assert CONCEPTUAL_VOLUME_COMBINATION_EXPRESSION not in table
    assert (rule.action, dict(rule.options)) == ("K", {})
    assert "10.34.1.1" in rule.note
    for composed in _every_policy():
        assert (
            composed.supplementary_actions[CONCEPTUAL_VOLUME_COMBINATION_EXPRESSION]
            == "K"
        ), composed.options


def test_removal_by_type_gives_the_enhanced_rt_images_attributes_the_actions_reviewed():
    actions_by_tag = _record_actions()
    dictionary = _dictionary()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    new = {}

    for tag in sorted(_used_by(ENHANCED_RT_IMAGE_IODS, every_vr)):
        action = actions_by_tag.get(tag)
        if action not in compound_actions.COMPOUND_ACTIONS:
            continue
        resolved = _resolved_in(ENHANCED_RT_IMAGE_IODS, tag, action)
        reviewed = _resolved_in(ENHANCED_RT_IMAGE_REVIEWED_AGAINST, tag, action)
        if not resolved <= reviewed:
            new[tag] = (resolved, reviewed)

    assert new == ENHANCED_RT_IMAGE_NEW_RESOLUTIONS
    # Each is a date or time that Full Dates keeps and Modified Dates
    # modifies, where D writes the dummy value.
    table = _table_e1_1()
    for tag in new:
        assert dict(table[tag].options) == DATE_OPTIONS, tag
        assert {
            definition.module
            for name in ENHANCED_RT_IMAGE_IODS
            for definition in iods.load_iod_tables().iods[name].definitions
            if definition.tag == tag and definition.type == "1"
        } == {"Radiotherapy Common Instance"}, tag


def test_every_uid_date_and_name_that_the_enhanced_rt_images_use_has_a_role():
    uids = uid_roles.load_uid_roles()
    temporal = temporal_roles.load_temporal_roles()
    table = _table_e1_1()

    for tag in _used_by(ENHANCED_RT_IMAGE_IODS, {"UI"}):
        assert isinstance(uids.role(tag), uid_roles.UIDRole), tag
    for tag in _used_by(ENHANCED_RT_IMAGE_IODS, TEMPORAL_VRS):
        assert isinstance(temporal.role(tag), temporal_roles.TemporalRole), tag
    # The IODs reviewed before them use every date, time, datetime, person
    # name, and URL that these IODs use, and every UID but two, which Table
    # E.1-1 replaces, each the UID of an instance.
    for vrs in (TEMPORAL_VRS, {"PN"}, {"UR"}):
        assert not _used_by(ENHANCED_RT_IMAGE_IODS, vrs) - _used_by(
            ENHANCED_RT_IMAGE_REVIEWED_AGAINST, vrs
        ), vrs
    new_uids = _used_by(ENHANCED_RT_IMAGE_IODS, {"UI"}) - _used_by(
        ENHANCED_RT_IMAGE_REVIEWED_AGAINST, {"UI"}
    )
    assert new_uids == ENHANCED_RT_IMAGE_UIDS
    for tag in new_uids:
        assert table[tag].basic_profile == "U", tag
        assert uids.role(tag) is uid_roles.UIDRole.INSTANCE, tag


def test_the_enhanced_rt_images_other_new_attributes_are_kept_by_the_default():
    dictionary = _dictionary()
    tables = iods.load_iod_tables()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    new = _used_by(ENHANCED_RT_IMAGE_IODS, every_vr) - _used_by(
        ENHANCED_RT_IMAGE_REVIEWED_AGAINST, every_vr
    )
    other = new - _used_by(ENHANCED_RT_IMAGE_IODS, TEXT_VRS) - ENHANCED_RT_IMAGE_UIDS
    listed = set(_table_e1_1())
    rules = _rules()
    uids = set(uid_roles.load_uid_roles().rules)
    by_vr = collections.Counter(vr for tag in other for vr in dictionary[tag].vrs)

    assert by_vr == ENHANCED_RT_IMAGE_OTHER_VRS
    assert all(len(dictionary[tag].vrs) == 1 for tag in other)
    assert not other & (listed | set(rules) | uids)
    # So each takes the default, which keeps it where these IODs define it,
    # under every preset, with a sequence's items handled by their own rules.
    for preset in policy.PRESETS:
        rules_of = element_rules.ElementRules(policy.compose_policy(preset))
        for name in ENHANCED_RT_IMAGE_IODS:
            iod = tables.iods[name]
            for definition in iod.definitions:
                if definition.tag not in other:
                    continue
                rule = rules_of.rule(definition.tag, definition.path, iod=iod)
                assert (rule.source, rule.action) == (
                    element_rules.RuleSource.DEFAULT,
                    element_rules.KEEP,
                ), (preset, name, definition)


def test_every_uid_date_and_name_that_the_softcopy_presentation_states_use_has_a_role():
    uids = uid_roles.load_uid_roles()
    temporal = temporal_roles.load_temporal_roles()
    table = _table_e1_1()

    for tag in _used_by(PRESENTATION_STATE_IODS, {"UI"}):
        assert isinstance(uids.role(tag), uid_roles.UIDRole), tag
    for tag in _used_by(PRESENTATION_STATE_IODS, TEMPORAL_VRS):
        assert isinstance(temporal.role(tag), temporal_roles.TemporalRole), tag
    # The IODs reviewed before them use every UID, person name, and URL that
    # these IODs use, and every date and time but when the Presentation State
    # was created, which Table E.1-1 removes, keeps under Retain Longitudinal
    # Temporal Information with Full Dates, and shifts under Modified Dates.
    for vrs in ({"UI"}, {"PN"}, {"UR"}):
        assert not _used_by(PRESENTATION_STATE_IODS, vrs) - _used_by(
            PRESENTATION_STATE_REVIEWED_AGAINST, vrs
        ), vrs
    new_dates = _used_by(PRESENTATION_STATE_IODS, TEMPORAL_VRS) - _used_by(
        PRESENTATION_STATE_REVIEWED_AGAINST, TEMPORAL_VRS
    )
    assert new_dates == set(PRESENTATION_CREATION_DATES)
    for tag in new_dates:
        assert temporal.role(tag) is temporal_roles.TemporalRole.SUBJECT_EVENT, tag
        assert (table[tag].basic_profile, dict(table[tag].options)) == (
            "X",
            DATE_OPTIONS,
        ), tag


def test_the_basic_profile_sequesters_every_conforming_softcopy_presentation_state():
    # Presentation Creation Date and Time are Type 1 at the top level of the
    # mandatory Presentation State Identification Module, where Table
    # E.1-1's plain X sequesters the instance (D-020), so the basic and
    # basic-clean-descriptors presets release none; the Graphic Annotation
    # Sequence is Type 1 wherever these IODs define it, so D, which a
    # sequence has no dummy value for, sequesters one that holds it under
    # every option, as Clean Graphics gives it its Basic Profile action
    # (D-041).
    tables = iods.load_iod_tables()
    for name in PRESENTATION_STATE_IODS:
        iod = tables.iods[name]
        for tag in PRESENTATION_CREATION_DATES:
            assert compound_actions.strictest_type(iod, tag, ()) == "1", (name, tag)
            assert (
                compound_actions.resolve_plain_x_in_iod(iod, tag, ()).extent
                is compound_actions.RemovalExtent.SEQUESTER
            ), (name, tag)
        assert {
            definition.type
            for definition in iod.definitions
            if definition.tag == GRAPHIC_ANNOTATION_SEQUENCE
        } == {"1"}, name


# The text attributes that the second-generation RT IODs use and that neither
# Table E.1-1 nor the IODs reviewed before them use, by group, checked by hand
# against the 2026d PS3.3 Sections C.8.8.30, C.36.8, C.36.22, and C.36.29 and
# the parameter specification items that RT Patient Position Acquisition
# Instruction and the radiation records share with the defined protocols.
SECOND_GENERATION_OPERATOR_TEXT = {
    "(0074,140B)",  # Reason for Channel Omission Description
    "(0082,0033)",  # Specification Selection Guidance
    "(0082,0037)",  # Constraint Violation Condition
    "(3002,0120)",  # Position Acquisition Template ID
    "(300A,0735)",  # Treatment Tolerance Violation Identification
    "(3010,001E)",  # Segmentation Creation Template Label
}
SECOND_GENERATION_KEPT_TEXT = {
    "(0082,0018)",  # Selector Attribute Name
    "(0082,0019)",  # Selector Attribute Keyword
    "(3010,0086)",  # Intended Start Day of Week
}
# Of the kept text, what the supported second-generation RT IODs use: RT
# Radiation Set uses Intended Start Day of Week.
SUPPORTED_SECOND_GENERATION_KEPT_TEXT = {"(3010,0086)"}
SECOND_GENERATION_TEXT_GROUPS: tuple[tuple[set[str], str, dict[str, str]], ...] = (
    (SECOND_GENERATION_OPERATOR_TEXT, "X/Z/D", {CLEAN_DESCRIPTORS: "C"}),
    (SECOND_GENERATION_KEPT_TEXT, "K", {}),
)
# What removal by Type gives each removed attribute where the
# second-generation RT IODs define it, as its note says: the condition, the
# template's identifier, and the violation's identification are Type 1C, the
# others Type 3.
SECOND_GENERATION_RESOLVED = {
    "(0074,140B)": "X",
    "(0082,0033)": "X",
    "(0082,0037)": "D",
    "(3002,0120)": "D",
    "(300A,0735)": "D",
    "(3010,001E)": "X",
}
# The UIDs that the second-generation RT IODs use and the IODs reviewed before
# them do not, with their roles: the UIDs of instances and items that Table
# E.1-1 lists, which it replaces; Creator Version UID, which identifies the
# equipment and software version that created a radiation set, and Selector
# UI Value, which can hold any UID that a constraint names, both replaced as
# instances' UIDs are; and the SOP Classes pertinent to a referenced study or
# series, which are kept.
SECOND_GENERATION_UIDS = {
    "(0008,9123)": uid_roles.UIDRole.INSTANCE,  # Creator Version UID
    "(0072,007F)": uid_roles.UIDRole.INSTANCE,  # Selector UI Value
    "(300A,0609)": uid_roles.UIDRole.INSTANCE,  # Treatment Position Group UID
    "(3010,0031)": uid_roles.UIDRole.INSTANCE,  # Referenced Fiducials UID
    "(3010,003B)": uid_roles.UIDRole.INSTANCE,  # RT Treatment Phase UID
    "(3010,0052)": uid_roles.UIDRole.DEFINITION,  # Pertinent SOP Classes in Study
    "(3010,0053)": uid_roles.UIDRole.DEFINITION,  # Pertinent SOP Classes in Series
    "(3010,006E)": uid_roles.UIDRole.INSTANCE,  # Dosimetric Objective UID
    "(3010,006F)": uid_roles.UIDRole.INSTANCE,  # Referenced Dosimetric Objective UID
}
# The dates, times, and datetimes that the second-generation RT IODs use and
# the IODs reviewed before them do not, all listed in Table E.1-1, with their
# roles: those of treatment, which move with the subject's other dates, and
# the date and time that a constraint can hold, as in a TABLE content item.
SECOND_GENERATION_DATES = {
    "(0072,0061)": temporal_roles.TemporalRole.OTHER,  # Selector DA Value
    "(0072,006B)": temporal_roles.TemporalRole.OTHER,  # Selector TM Value
    "(300A,0736)": temporal_roles.TemporalRole.SUBJECT_EVENT,
    "(300A,073A)": temporal_roles.TemporalRole.SUBJECT_EVENT,
    "(300A,0760)": temporal_roles.TemporalRole.SUBJECT_EVENT,
    "(3010,004C)": temporal_roles.TemporalRole.SUBJECT_EVENT,
    "(3010,004D)": temporal_roles.TemporalRole.SUBJECT_EVENT,
    "(3010,0085)": temporal_roles.TemporalRole.SUBJECT_EVENT,
}
# The other attributes that the second-generation RT IODs use, the IODs
# reviewed before them do not, and Table E.1-1 does not list, by VR, checked
# by hand against the 2026d PS3.3 and PS3.6: codes, numbers, indices, and
# sequences of the radiations, their devices, prescriptions, and delivery;
# the thickness maps of a compensator and the edge of a block; and the binary
# values that a constraint can hold, which Table E.1-1 does not list.
SECOND_GENERATION_OTHER_VRS = {
    "SQ": 122,
    "FD": 45,
    "CS": 44,
    "US": 32,
    "OF": 4,
    "DS": 4,
    "IS": 3,
    "UL": 3,
    "FL": 1,
    "AT": 1,
    "OD": 1,
    "OL": 1,
    "OV": 1,
    "OW": 1,
}


def test_the_second_generation_rt_iods_are_generated_and_have_the_documented_support():
    tables = iods.load_iod_tables()

    assert len(SECOND_GENERATION_RT_IODS) == 16
    assert set(SECOND_GENERATION_RT_IODS) <= set(tables.iods)
    assert set(SECOND_GENERATION_RT_IODS) & scope.SUPPORTED_IODS == set(
        SUPPORTED_SECOND_GENERATION_RT_IODS
    )


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_the_text_that_only_the_second_generation_rt_iods_use_has_reviewed_rules():
    listed = set(_table_e1_1())
    added = _used_by(SECOND_GENERATION_RT_IODS, TEXT_VRS) - _used_by(
        SECOND_GENERATION_REVIEWED_AGAINST, TEXT_VRS
    )
    rules = _rules()

    assert (added - listed) == (
        SECOND_GENERATION_OPERATOR_TEXT | SECOND_GENERATION_KEPT_TEXT
    )
    assert len(added - listed) == 9
    for tags, action, options in SECOND_GENERATION_TEXT_GROUPS:
        for tag in tags:
            assert (rules[tag].action, dict(rules[tag].options)) == (
                action,
                options,
            ), tag
            assert rules[tag].note.strip(), tag
    # Table E.1-1 lists the others, each with an action that removes or
    # replaces its value.
    for tag in added & listed:
        assert _table_e1_1()[tag].basic_profile in REMOVING_ACTIONS, tag


def test_each_policy_gives_the_second_generation_rt_text_the_action_of_its_group():
    for composed in _every_policy():
        for tags, action, options in SECOND_GENERATION_TEXT_GROUPS:
            selected = [a for o, a in options.items() if o in composed.options]
            for tag in tags:
                assert composed.supplementary_actions[tag] == (
                    selected[0] if selected else action
                ), (tag, composed.options)


def test_the_second_generation_rt_text_that_is_removed_resolves_as_its_note_says():
    tables = iods.load_iod_tables()
    rules = _rules()
    resolved_where = collections.defaultdict(set)

    for name in SECOND_GENERATION_RT_IODS:
        iod = tables.iods[name]
        for definition in iod.definitions:
            if definition.tag not in SECOND_GENERATION_RESOLVED:
                continue
            resolved_where[definition.tag].add(
                compound_actions.resolve_in_iod(
                    iod, definition.tag, definition.path, rules[definition.tag].action
                )
            )
    assert resolved_where == {
        tag: {resolved} for tag, resolved in SECOND_GENERATION_RESOLVED.items()
    }
    # Each note says what removal by Type gives it where that differs from X.
    for tag, resolved in SECOND_GENERATION_RESOLVED.items():
        said = "dummy value where it is Type 1C" in rules[tag].note
        assert said == (resolved == "D"), tag


def test_every_uid_date_and_name_that_the_second_generation_rt_iods_use_has_a_role():
    listed = _table_e1_1()
    uids = uid_roles.load_uid_roles()
    temporal = temporal_roles.load_temporal_roles()
    new_uids = _used_by(SECOND_GENERATION_RT_IODS, {"UI"}) - _used_by(
        SECOND_GENERATION_REVIEWED_AGAINST, {"UI"}
    )
    new_dates = _used_by(SECOND_GENERATION_RT_IODS, TEMPORAL_VRS) - _used_by(
        SECOND_GENERATION_REVIEWED_AGAINST, TEMPORAL_VRS
    )

    for tag in _used_by(SECOND_GENERATION_RT_IODS, {"UI"}):
        assert isinstance(uids.role(tag), uid_roles.UIDRole), tag
    for tag in _used_by(SECOND_GENERATION_RT_IODS, TEMPORAL_VRS):
        assert isinstance(temporal.role(tag), temporal_roles.TemporalRole), tag
    assert {tag: uids.role(tag) for tag in new_uids} == SECOND_GENERATION_UIDS
    assert {tag: temporal.role(tag) for tag in new_dates} == SECOND_GENERATION_DATES
    for tag in new_dates:
        assert listed[tag].basic_profile in REMOVING_ACTIONS, tag
    for tag, role in SECOND_GENERATION_UIDS.items():
        if role is uid_roles.UIDRole.INSTANCE and tag in listed:
            assert listed[tag].basic_profile == "U", tag
    # The one new person name and the one new URL are Selector PN Value and
    # Selector UR Value, which Table E.1-1 gives D, as it gives the other
    # values that a constraint or a TABLE content item can hold.
    for vr, tag in (("PN", "(0072,006A)"), ("UR", "(0072,0071)")):
        assert _used_by(SECOND_GENERATION_RT_IODS, {vr}) - _used_by(
            SECOND_GENERATION_REVIEWED_AGAINST, {vr}
        ) == {tag}, vr
        assert listed[tag].basic_profile == "D", tag


def test_the_second_generation_rt_iods_other_new_attributes_are_kept_by_the_default():
    dictionary = _dictionary()
    tables = iods.load_iod_tables()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    listed = set(_table_e1_1())
    rules = _rules()
    uids = set(uid_roles.load_uid_roles().rules)
    other = (
        _used_by(SECOND_GENERATION_RT_IODS, every_vr)
        - _used_by(SECOND_GENERATION_REVIEWED_AGAINST, every_vr)
        - _used_by(SECOND_GENERATION_RT_IODS, TEXT_VRS)
        - listed
        - uids
    )
    by_vr = collections.Counter(vr for tag in other for vr in dictionary[tag].vrs)

    assert by_vr == SECOND_GENERATION_OTHER_VRS
    assert all(len(dictionary[tag].vrs) == 1 for tag in other)
    assert not other & set(rules)
    # So each takes the default, which keeps it where these IODs define it,
    # under every preset, with a sequence's items handled by their own rules.
    for preset in policy.PRESETS:
        rules_of = element_rules.ElementRules(policy.compose_policy(preset))
        for name in SECOND_GENERATION_RT_IODS:
            iod = tables.iods[name]
            for definition in iod.definitions:
                if definition.tag not in other:
                    continue
                rule = rules_of.rule(definition.tag, definition.path, iod=iod)
                assert (rule.source, rule.action) == (
                    element_rules.RuleSource.DEFAULT,
                    element_rules.KEEP,
                ), (preset, name, definition)


def test_names_identifiers_and_overlay_text_are_removed_under_every_option():
    rules = _rules()

    assert {
        tag
        for tag in _omitted_text()
        if rules[tag].action == "X/Z/D" and not rules[tag].options
    } == REMOVED_UNDER_EVERY_OPTION
    for composed in _every_policy():
        for tag in REMOVED_UNDER_EVERY_OPTION:
            assert composed.supplementary_actions[tag] == "X/Z/D", (
                tag,
                composed.options,
            )


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize(
    "options, operator_text, accessory_identifier",
    [
        ((), "X/Z/D", "X/Z/D"),
        ((CLEAN_DESCRIPTORS,), "C", "X/Z/D"),
        ((DEVICE_IDENTITY,), "X/Z/D", "K"),
        ((DEVICE_IDENTITY, CLEAN_DESCRIPTORS), "C", "K"),
    ],
)
def test_each_group_takes_the_action_of_its_option(
    options, operator_text, accessory_identifier
):
    composed = policy.compose_custom_policy(options).supplementary_actions

    for tag in OPERATOR_TEXT:
        assert composed[tag] == operator_text, tag
    for tag in ACCESSORY_IDENTIFIERS:
        assert composed[tag] == accessory_identifier, tag
    for tag in (
        KEPT_TEXT
        | ADDED_KEPT_TEXT
        | RT_IMAGE_KEPT_TEXT
        | ION_KEPT_TEXT
        | ENHANCED_RT_IMAGE_KEPT_TEXT
        | SUPPORTED_SECOND_GENERATION_KEPT_TEXT
    ):
        assert composed[tag] == "K", tag


@pytest.mark.parametrize(
    "preset, operator_text, accessory_identifier",
    [
        ("basic", "X/Z/D", "X/Z/D"),
        ("public-release", "C", "X/Z/D"),
        ("tps-import", "C", "K"),
    ],
)
def test_each_preset_gives_each_group_its_action(
    preset, operator_text, accessory_identifier
):
    composed = policy.compose_policy(preset).supplementary_actions

    assert {composed[tag] for tag in OPERATOR_TEXT} == {operator_text}
    assert {composed[tag] for tag in ACCESSORY_IDENTIFIERS} == {accessory_identifier}


@pytest.mark.deid_requirement("MIDI-BP-11")
def test_the_basic_profile_keeps_only_the_reviewed_coded_and_technical_text():
    # Every text attribute of the supported IODs, whether Table E.1-1 lists
    # it or a supplementary rule covers it.
    composed = policy.compose_policy("basic")
    basic = {
        tag: composed.actions.get(tag) or composed.supplementary_actions[tag]
        for tag in _supported_text()
    }

    # The three delivery instructions add 3: Reason for Channel Omission
    # Description (0074,140B), Displacement Reference Label (300A,079A), and
    # Reason for Omission Description (300C,0113), none of them kept; and
    # Nuclear Medicine Image adds 3: Processing Function (0018,5020), Energy
    # Window Name (0054,0018), and Image ID (0054,0400), none of them kept.
    assert len(basic) == 338
    assert {tag for tag, action in basic.items() if action == "K"} == (
        KEPT_TEXT
        | ADDED_KEPT_TEXT
        | RT_IMAGE_KEPT_TEXT
        | ION_KEPT_TEXT
        | PRESENTATION_STATE_KEPT_TEXT
        | PDF_MEDIA_TYPES
        | PDF_CAPTURE_FORMATS
        | ENHANCED_RT_IMAGE_KEPT_TEXT
        | SUPPORTED_SECOND_GENERATION_KEPT_TEXT
    )
    assert set(basic.values()) - {"K"} <= REMOVING_ACTIONS


@pytest.mark.deid_requirement("MIDI-BP-05")
def test_no_option_keeps_more_than_the_coded_text_and_device_identity():
    rules = _rules()
    device_identity = {
        tag for tag in _omitted_text() if rules[tag].options.get(DEVICE_IDENTITY)
    }
    for composed in _every_policy():
        kept = {
            tag for tag in _omitted_text() if composed.supplementary_actions[tag] == "K"
        }
        expected = (
            KEPT_TEXT
            | ADDED_KEPT_TEXT
            | RT_IMAGE_KEPT_TEXT
            | ION_KEPT_TEXT
            | PRESENTATION_STATE_KEPT_TEXT
            | PDF_MEDIA_TYPES
            | PDF_CAPTURE_FORMATS
            | ENHANCED_RT_IMAGE_KEPT_TEXT
            | SUPPORTED_SECOND_GENERATION_KEPT_TEXT
            | (device_identity if DEVICE_IDENTITY in composed.options else set())
        )
        assert kept == expected, composed.options


@pytest.mark.parametrize("tag", ALTERNATIVE_CALENDAR_DATES)
def test_the_alternative_calendar_dates_are_removed_under_every_option(tag):
    rule = _rules()[tag]

    assert (rule.action, dict(rule.options)) == ("X", {})
    for composed in _every_policy():
        assert composed.supplementary_actions[tag] == "X", composed.options


def test_deidentification_method_keeps_earlier_values_for_the_engine_to_add_to():
    rule = _rules()[DEIDENTIFICATION_METHOD]

    assert (rule.keyword, rule.action, dict(rule.options)) == (
        "DeidentificationMethod",
        "K",
        {},
    )
    # The rule says that the engine writes the attribute itself.
    assert "the engine keeps the values already present and adds" in rule.note
    for composed in _every_policy():
        assert composed.supplementary_actions[DEIDENTIFICATION_METHOD] == "K"


@pytest.mark.deid_requirement("MIDI-BP-05")
def test_the_urls_that_name_coding_concepts_and_schemes_are_kept():
    rules = _rules()
    listed = _table_e1_1()
    omitted = {
        tag
        for tag, attribute in _dictionary().items()
        if "UR" in attribute.vrs and tag not in listed
    }

    assert len(omitted) == 12
    assert set(_definitions_of(omitted, SUPPORTED_IODS)) == (
        set(KEPT_URLS) | OTHER_URLS
    )
    for tag, keyword in KEPT_URLS.items():
        rule = rules[tag]
        assert (rule.keyword, rule.action, dict(rule.options)) == (keyword, "K", {})
        assert rule.note.strip()
        for composed in _every_policy():
            assert composed.supplementary_actions[tag] == "K", composed.options


def test_the_declared_default_for_text_without_a_rule_removes_by_type():
    rules = _rules()
    listed = _table_e1_1()
    uncovered = {
        tag
        for tag, attribute in _dictionary().items()
        if TEXT_VRS.intersection(attribute.vrs)
        and tag not in listed
        and tag not in rules
    }

    # Such as Stage Name, an ultrasound attribute that no supported IOD uses.
    assert "(0008,2120)" in uncovered
    assert not uncovered & _omitted_text()
    assert supplementary_actions.UNCOVERED_TEXT_ACTION == "X/Z/D"


@pytest.mark.deid_requirement("MIDI-BP-06")
def test_every_date_and_time_that_table_e1_1_omits_has_a_rule():
    # Derived here independently of the loader: Table E.1-1 lists no date or
    # time by a masked tag, so an exact comparison of tags suffices.
    dictionary = _dictionary()
    listed = _table_e1_1()
    omitted = {
        tag
        for tag, attribute in dictionary.items()
        if TEMPORAL_VRS.intersection(attribute.vrs) and tag not in listed
    }

    assert omitted == set(OMITTED_DATES)
    assert collections.Counter(dictionary[tag].status for tag in omitted) == {
        "": 3,
        "DICONDE": 8,
        "DICOS": 4,
    }
    assert omitted <= set(_rules())


def test_the_basic_profile_keeps_no_date_or_time():
    # Table E.1-1 and the supplementary actions together give every date,
    # time, and datetime in the dictionary an action that removes or
    # replaces it.
    listed = _table_e1_1()
    rules = _rules()
    basic = {
        tag: listed[tag].basic_profile if tag in listed else rules[tag].action
        for tag, attribute in _dictionary().items()
        if TEMPORAL_VRS.intersection(attribute.vrs)
    }

    assert len(basic) == 184
    assert set(basic.values()) <= REMOVING_ACTIONS


@pytest.mark.parametrize("tag, keyword", OMITTED_DATES.items())
def test_each_omitted_date_is_removed_by_type_and_kept_or_cleaned_by_the_date_options(
    tag, keyword
):
    rule = _rules()[tag]

    assert (rule.tag, rule.keyword, rule.action) == (tag, keyword, "X/Z/D")
    assert dict(rule.options) == DATE_OPTIONS
    assert rule.note.strip()


def test_the_omitted_dates_take_the_date_option_actions_of_the_dates_the_table_lists():
    # Table E.1-1 keeps under Full Dates, and cleans under Modified Dates,
    # every date and time it lists but Patient's Birth Date, Patient's Birth
    # Time, and GPS Time Stamp, which it removes under every option. The
    # rules do the same for the dates that it omits.
    dictionary = _dictionary()
    date_options = collections.Counter(
        tuple(
            (option, action)
            for option, action in row.options.items()
            if option in (FULL_DATES, MODIFIED_DATES)
        )
        for tag, row in _table_e1_1().items()
        if tag in dictionary and TEMPORAL_VRS.intersection(dictionary[tag].vrs)
    )

    assert date_options == {tuple(DATE_OPTIONS.items()): 166, (): 3}
    for tag in OMITTED_DATES:
        assert dict(_rules()[tag].options) == DATE_OPTIONS, tag


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize(
    "options, action",
    [
        ((), "X/Z/D"),
        ((FULL_DATES,), "K"),
        ((MODIFIED_DATES,), "C"),
        # No other option gives them an action, so Retain Device Identity
        # keeps none of them, not even the dates of gain calibration.
        ((DEVICE_IDENTITY,), "X/Z/D"),
        ((CLEAN_DESCRIPTORS,), "X/Z/D"),
        ((FULL_DATES, DEVICE_IDENTITY, CLEAN_DESCRIPTORS), "K"),
        ((DEVICE_IDENTITY, MODIFIED_DATES, CLEAN_DESCRIPTORS), "C"),
    ],
)
def test_only_the_date_options_override_the_action_of_an_omitted_date(options, action):
    effective = actions.effective_supplementary_actions(options)

    assert not effective.conflicts
    assert {effective.actions[tag] for tag in OMITTED_DATES} == {action}


def test_every_policy_cleans_the_omitted_dates_only_under_modified_dates():
    # Every preset, including basic (X/Z/D), and public-release and
    # tps-import (C), and every custom option set.
    for composed in _every_policy():
        expected = "C" if MODIFIED_DATES in composed.options else "X/Z/D"
        assert {composed.supplementary_actions[tag] for tag in OMITTED_DATES} == {
            expected
        }, composed.options
        # No conflict involves them, for a preset to resolve.
        assert not {r.conflict.tag for r in composed.resolved} & set(OMITTED_DATES)


def test_each_date_rule_says_what_the_date_options_and_its_role_do():
    rules = _rules()
    roles = temporal_roles.load_temporal_roles()

    for tag in OMITTED_DATES:
        note = rules[tag].note
        assert "kept (K) under Full Dates" in note, tag
        assert "cleaned (C) under Modified Dates" in note, tag
        assert SAID_OF[roles.role(tag).action] in note, tag
    # The dates of gain calibration say why Retain Device Identity, which
    # keeps the calibration dates that Table E.1-1 lists, does not keep them.
    for tag in ("(0014,3076)", "(0014,3077)"):
        assert roles.role(tag) is temporal_roles.TemporalRole.DEVICE
        assert "Retain Device Identity" in rules[tag].note


@pytest.mark.parametrize(
    "claim, names, claimed_of",
    [
        # The DICONDE and DICOS person names and dates.
        (
            NO_GENERATED_IOD_USES_IT,
            None,
            {"(0014,0104)", "(0014,2006)"}
            | (set(OMITTED_DATES) - set(INVENTORY_DATES)),
        ),
        (NO_SUPPORTED_IOD_USES_IT, SUPPORTED_IODS, set(INVENTORY_DATES)),
    ],
    ids=["generated", "supported"],
)
def test_a_note_that_no_iod_uses_its_attribute_is_true(claim, names, claimed_of):
    # Checked again whenever the IOD tables are regenerated, since an IOD
    # whose Types are newly generated can use an attribute that none did.
    claimed = {tag for tag, rule in _rules().items() if claim.search(rule.note)}

    assert claimed_of <= claimed
    assert not _definitions_of(claimed, names)


def test_only_the_inventory_iod_uses_the_inventory_dates_as_their_notes_say():
    found = _definitions_of(set(INVENTORY_DATES))
    rules = _rules()

    for tag, (path, attribute_type) in INVENTORY_DATES.items():
        assert found[tag] == {("Inventory", "Inventory", path, attribute_type)}, tag
        note = rules[tag].note
        assert (
            f"PS3.3 defines it only in the Inventory Module, as Type {attribute_type}"
            in note
        ), tag
        assert "Only the Inventory IOD uses the Inventory Module" in note, tag


def test_the_options_override_the_basic_profile_action_of_a_rule():
    effective = actions.effective_supplementary_actions([CLEAN_DESCRIPTORS])
    rules = _rules()

    assert effective.edition == "2026d"
    assert effective.options == (CLEAN_DESCRIPTORS,)
    assert not effective.conflicts
    assert set(effective.actions) == set(rules)
    for tag, rule in rules.items():
        assert effective.actions[tag] == rule.options.get(
            CLEAN_DESCRIPTORS, rule.action
        )
    basic = actions.effective_supplementary_actions()
    assert dict(basic.actions) == {tag: rule.action for tag, rule in rules.items()}


def _with_beam_name_options(given):
    """Return the rules with Beam Name's option actions replaced, unchecked."""
    loaded = supplementary_actions.load_supplementary_actions()
    rules = dict(loaded.rules)
    rules["(300A,00C2)"] = dataclasses.replace(
        rules["(300A,00C2)"], options=types.MappingProxyType(given)
    )
    return dataclasses.replace(loaded, rules=types.MappingProxyType(rules))


def test_a_rule_whose_options_conflict_is_reported_as_a_conflict():
    rules = _with_beam_name_options({DEVICE_IDENTITY: "K", CLEAN_DESCRIPTORS: "C"})
    effective = actions.effective_supplementary_actions(
        [CLEAN_DESCRIPTORS, DEVICE_IDENTITY], rules=rules
    )

    assert [(c.name, c.tag, dict(c.actions)) for c in effective.conflicts] == [
        ("BeamName", "(300A,00C2)", {DEVICE_IDENTITY: "K", CLEAN_DESCRIPTORS: "C"})
    ]
    assert "(300A,00C2)" not in effective.actions
    alone = actions.effective_supplementary_actions([CLEAN_DESCRIPTORS], rules=rules)
    assert not alone.conflicts
    assert alone.actions["(300A,00C2)"] == "C"


def test_a_policy_rejects_a_conflict_between_the_options_of_a_rule(monkeypatch):
    rules = _with_beam_name_options({DEVICE_IDENTITY: "K", CLEAN_DESCRIPTORS: "C"})
    monkeypatch.setattr(actions, "load_supplementary_actions", lambda: rules)

    with pytest.raises(policy.PolicyError, match="no precedence") as raised:
        policy.compose_policy("tps-import")
    assert "(300A,00C2)" in str(raised.value)
    assert (
        policy.compose_policy("public-release").supplementary_actions["(300A,00C2)"]
        == "C"
    )


@pytest.mark.parametrize(
    "tag, keyword, action",
    [
        # Marked DICONDE in PS3.6 and used by none of the generated IODs, so
        # the action suits any Type an IOD gives them.
        ("(0014,0104)", "SecondaryReviewerName", "X/Z/D"),
        ("(0014,2006)", "EvaluatorName", "X/Z/D"),
        # Retired, like the other (Trial) person names, which Table E.1-1
        # removes.
        ("(0040,A067)", "DocumentAuthorTrial", "X"),
        # Kept as received, since the pixel data are unchanged. Burned In
        # Annotation is never set to NO, and Recognizable Visual Features
        # only by the markers, under its option.
        ("(0028,0301)", "BurnedInAnnotation", "K"),
        ("(0028,0302)", "RecognizableVisualFeatures", "K"),
    ],
)
def test_actions(tag, keyword, action):
    rule = supplementary_actions.load_supplementary_actions().rules[tag]

    assert (rule.tag, rule.keyword, rule.action) == (tag, keyword, action)
    assert rule.note


def test_uids_are_left_to_their_roles_and_dates_have_actions_besides():
    # pylint: disable=protected-access
    assert supplementary_actions._ROLES_ONLY_VRS == uid_roles._FORMAT.vrs
    assert supplementary_actions.TEMPORAL_VRS == temporal_roles._FORMAT.vrs
    assert supplementary_actions.COVERED_VRS == {"PN"} | TEMPORAL_VRS


def test_each_option_that_can_give_an_action_names_the_attributes_it_applies_to():
    # Otherwise a rule's action under such an option would raise a KeyError,
    # not a SupplementaryActionError.
    # pylint: disable=protected-access
    assert set(supplementary_actions._OPTION_ATTRIBUTES) == set(
        supplementary_actions.OPTION_ACTIONS
    )


def test_every_note_says_why_without_citing_a_decision_number():
    # Decision numbers belong to the design document and its register.
    for rule in supplementary_actions.load_supplementary_actions().rules.values():
        assert rule.note.strip(), rule.tag
        assert not re.search(r"\bD-[0-9]{3}\b", rule.note), rule.tag


def test_the_actions_follow_the_editions_of_the_tables():
    loaded = supplementary_actions.load_supplementary_actions()

    assert loaded.edition == standard.load_data_dictionary().edition
    assert loaded.edition == standard.load_table_e1_1().edition
    assert loaded.edition == iods.load_iod_tables().edition
    assert loaded.acknowledgement == f"DICOM PS3.6 {loaded.edition}, © NEMA"


def test_the_rules_are_read_only():
    rules = supplementary_actions.load_supplementary_actions().rules

    with pytest.raises(TypeError):
        rules["(0010,0010)"] = rules["(0028,0301)"]  # type: ignore[index]


def _document():
    return tomlkit.parse(
        supplementary_actions.SUPPLEMENTARY_ACTIONS_PATH.read_text(encoding="utf-8")
    ).unwrap()


def _write(path, document):
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


def _drop(document, tag):
    document["attribute"] = [
        rule for rule in document["attribute"] if rule["tag"] != tag
    ]


def _first(**fields):
    return lambda document: document["attribute"][0].update(fields)


def _rule(tag, **fields):
    """Return a change that updates the rule for ``tag`` with ``fields``."""

    def change(document):
        (rule,) = [rule for rule in document["attribute"] if rule["tag"] == tag]
        rule.update(fields)

    return change


BEAM_NAME = "(300A,00C2)"


@pytest.mark.parametrize(
    "change, message",
    [
        (
            lambda d: d.update(schema="pymedphys-deid-supplementary-actions/0"),
            "schema",
        ),
        (lambda d: d.update(edition="2099a"), "edition"),
        (lambda d: d.update(acknowledgement="NEMA"), "acknowledgement"),
        (lambda d: d.update(attribute=1), "rules are not an array of tables"),
        (lambda d: d.update(attribute={}), "rules are not an array of tables"),
        (_first(extra=1), "rule 1 does not have"),
        (lambda d: d["attribute"][0].pop("keyword"), "rule 1 does not have"),
        (lambda d: d["attribute"][0].pop("note"), "rule 1 does not have"),
        (_first(tag="(7777,7777)"), "rule 1 is not an attribute of the data"),
        (_first(tag=[]), "rule 1 is not an attribute of the data"),
        (_first(keyword="EvaluatorName"), "rule 1 names"),
        (
            _first(tag="(0010,0010)", keyword="PatientName"),
            "rule 1 is listed in Table E.1-1",
        ),
        # Table E.1-1 lists the whole retired Curve group as (50xx,xxxx).
        (
            _first(tag="(50xx,2500)", keyword="CurveLabel"),
            "rule 1 is listed in Table E.1-1",
        ),
        (
            _first(tag="(50xx,200A)", keyword="TotalTime"),
            "rule 1 is listed in Table E.1-1",
        ),
        # A date that Table E.1-1 lists keeps the table's actions.
        (
            _first(tag="(0008,0020)", keyword="StudyDate"),
            "rule 1 is listed in Table E.1-1",
        ),
        (
            _first(tag="(0008,0016)", keyword="SOPClassUID"),
            "rule 1 is a UI attribute, which the UID roles file covers",
        ),
        (_first(action="retain"), "rule 1 has an action not defined in Table"),
        (_first(action="U*"), "rule 1 has an action not defined in Table"),
        (_first(action=[]), "rule 1 has an action not defined in Table"),
        (_first(note=""), "rule 1 has a note that is not non-empty text"),
        (_first(note=" "), "rule 1 has a note that is not non-empty text"),
        (lambda d: d["attribute"].append(dict(d["attribute"][0])), "repeats"),
        (lambda d: _drop(d, "(0014,2006)"), "has no action for (0014,2006)"),
        # Text attributes that the supported IODs use and Table E.1-1 omits.
        (lambda d: _drop(d, BEAM_NAME), f"has no action for {BEAM_NAME}"),
        (lambda d: _drop(d, "(60xx,1500)"), "has no action for (60xx,1500)"),
        (lambda d: _drop(d, "(0008,0100)"), "has no action for (0008,0100)"),
        # Dates and times that Table E.1-1 omits.
        (lambda d: _drop(d, STUDY_UPDATE), f"has no action for {STUDY_UPDATE}"),
        (lambda d: _drop(d, "(0014,3077)"), "has no action for (0014,3077)"),
        (lambda d: _drop(d, "(4010,1041)"), "has no action for (4010,1041)"),
        # Option actions.
        (_rule(BEAM_NAME, options=1), "has options that are not a table"),
        (_rule(BEAM_NAME, options={}), "has options that are not a table"),
        (_rule(BEAM_NAME, options=[]), "has options that are not a table"),
        (
            _rule(BEAM_NAME, options={"retain_everything": "K"}),
            "has an option that Table E.1-1 does not define",
        ),
        (
            _rule(BEAM_NAME, options={CLEAN_DESCRIPTORS: "clean"}),
            "has an option action not defined in Table E.1-1a",
        ),
        (
            _rule(BEAM_NAME, options={CLEAN_DESCRIPTORS: []}),
            "has an option action not defined in Table E.1-1a",
        ),
        # Defined, but not an action a supplementary rule may give.
        (
            _rule(BEAM_NAME, options={CLEAN_DESCRIPTORS: "K"}),
            "gives clean_descriptors an action other than C",
        ),
        (
            _rule(BEAM_NAME, options={DEVICE_IDENTITY: "C"}),
            "gives retain_device_identity an action other than K",
        ),
        (
            _rule(STUDY_UPDATE, options={FULL_DATES: "C", MODIFIED_DATES: "C"}),
            "gives retain_longitudinal_full_dates an action other than K",
        ),
        (
            _rule(STUDY_UPDATE, options={FULL_DATES: "K", MODIFIED_DATES: "K"}),
            "gives retain_longitudinal_modified_dates an action other than C",
        ),
        (
            _rule(BEAM_NAME, options={"retain_uids": "K"}),
            "gives an action under retain_uids; a rule may give one only under "
            "retain_device_identity, retain_longitudinal_full_dates, "
            "retain_longitudinal_modified_dates, or clean_descriptors",
        ),
        (
            _rule(BEAM_NAME, options={DEVICE_IDENTITY: "K", CLEAN_DESCRIPTORS: "C"}),
            "gives different actions under two or more options that can be "
            "selected together",
        ),
        (
            _rule(STUDY_UPDATE, options={FULL_DATES: "K", CLEAN_DESCRIPTORS: "C"}),
            "gives different actions under two or more options that can be "
            "selected together",
        ),
        # An option action on a rule whose design does not allow one.
        (
            _rule("(0008,0100)", options={CLEAN_DESCRIPTORS: "C"}),
            "has an option action, but its Basic Profile action keeps the value",
        ),
        (
            _rule("(0028,0301)", options={DEVICE_IDENTITY: "K"}),
            "has an option action, but its Basic Profile action keeps the value",
        ),
        (
            _rule(STUDY_UPDATE, action="K"),
            "has an option action, but its Basic Profile action keeps the value",
        ),
        (
            _first(options={CLEAN_DESCRIPTORS: "C"}),
            "rule 1 has an option action under clean_descriptors, but is not a "
            "text attribute",
        ),
        # Each option gives an action only to the attributes it applies to.
        (
            _rule(BEAM_NAME, options={MODIFIED_DATES: "C"}),
            "has an option action under retain_longitudinal_modified_dates, but is "
            "not a date, time, or datetime attribute",
        ),
        (
            _rule(BEAM_NAME, options={FULL_DATES: "K", MODIFIED_DATES: "C"}),
            "has an option action under retain_longitudinal_full_dates, but is not "
            "a date, time, or datetime attribute",
        ),
        (
            _rule(STUDY_UPDATE, options={DEVICE_IDENTITY: "K"}),
            "has an option action under retain_device_identity, but is not a text "
            "attribute",
        ),
        # Every option is checked, not only the first.
        (
            _rule(STUDY_UPDATE, options={FULL_DATES: "K", DEVICE_IDENTITY: "K"}),
            "has an option action under retain_device_identity, but is not a text "
            "attribute",
        ),
        (
            _rule(STUDY_UPDATE, options={CLEAN_DESCRIPTORS: "C"}),
            "has an option action under clean_descriptors, but is not a text attribute",
        ),
    ],
)
def test_a_malformed_file_is_rejected(tmp_path, change, message):
    document = _document()
    change(document)

    with pytest.raises(
        supplementary_actions.SupplementaryActionError, match=re.escape(message)
    ):
        supplementary_actions.load_supplementary_actions(
            _write(tmp_path / "supplementary_actions.toml", document)
        )


def test_a_file_that_cannot_be_read_is_rejected(tmp_path):
    with pytest.raises(
        supplementary_actions.SupplementaryActionError, match="could not be read"
    ):
        supplementary_actions.load_supplementary_actions(tmp_path / "missing.toml")


def test_an_option_action_is_read_as_given(tmp_path):
    document = _document()
    _rule(BEAM_NAME, options={CLEAN_DESCRIPTORS: "C"})(document)
    loaded = supplementary_actions.load_supplementary_actions(
        _write(tmp_path / "supplementary_actions.toml", document)
    )

    assert dict(loaded.rules[BEAM_NAME].options) == {CLEAN_DESCRIPTORS: "C"}
    # A rule without options has none, and the options are read-only.
    assert not loaded.rules["(0014,0104)"].options
    with pytest.raises(TypeError):
        loaded.rules[BEAM_NAME].options[DEVICE_IDENTITY] = "K"  # type: ignore[index]


def test_rules_for_iod_tables_of_another_edition_are_rejected(tmp_path, monkeypatch):
    other = dataclasses.replace(iods.load_iod_tables(), edition="2099a")
    monkeypatch.setattr(supplementary_actions, "load_iod_tables", lambda: other)

    with pytest.raises(supplementary_actions.SupplementaryActionError, match="edition"):
        supplementary_actions.load_supplementary_actions(
            _write(tmp_path / "supplementary_actions.toml", _document())
        )


def _with_definition(tmp_path, iod_name, tag):
    """Return IOD tables in which ``iod_name`` defines ``tag`` in a sequence.

    The tables are loaded, through the public loader, from copies of the
    generated files with a module added: its attribute table defines ``tag``
    in Beam Sequence (300A,00B0). An IOD that the files lack is added too.
    """
    modules, attributes = (
        json.loads((standard.STANDARD_DIR / name).read_text(encoding="utf-8"))
        for name in ("iod_modules.json", "module_attributes.json")
    )
    attributes["rows"].append(
        {
            "label": "Table X.0-1",
            "title": "Test Module Attributes",
            "rows": [
                {
                    "depth": 0,
                    "name": "Beam Sequence",
                    "tag": "(300A,00B0)",
                    "type": "3",
                    "include": "",
                },
                {"depth": 1, "name": "Test", "tag": tag, "type": "3", "include": ""},
            ],
        }
    )
    entry = next((row for row in modules["rows"] if row["iod"] == iod_name), None)
    if entry is None:
        entry = {"label": "Table X.0-2", "iod": iod_name, "modules": []}
        modules["rows"].append(entry)
    entry["modules"].append(
        {
            "information_entity": "Equipment",
            "module": "Test",
            "section": "X.0",
            "usage": "U",
            "condition": "",
            "table": "Table X.0-1",
        }
    )
    paths = []
    for name, document in (
        ("iod_modules.json", modules),
        ("module_attributes.json", attributes),
    ):
        document["content_sha256"] = standard.content_sha256(document["rows"])
        paths.append(tmp_path / name)
        paths[-1].write_text(json.dumps(document), encoding="utf-8")
    return iods.load_iod_tables(*paths)


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize(
    "iod_name, required",
    [
        # A supported IOD that comes to use Stage Name, which has no rule, at
        # any depth, needs a rule for it.
        ("RT Plan", True),
        # An IOD that is not supported does not, even once its Types are
        # generated.
        ("Ultrasound Image", False),
    ],
)
def test_only_the_text_of_the_supported_iods_needs_rules(
    tmp_path, monkeypatch, iod_name, required
):
    tables = _with_definition(tmp_path, iod_name, "(0008,2120)")
    assert tables.iods[iod_name].lookup("(0008,2120)", ["(300A,00B0)"])
    monkeypatch.setattr(supplementary_actions, "load_iod_tables", lambda: tables)
    path = _write(tmp_path / "supplementary_actions.toml", _document())

    if required:
        with pytest.raises(
            supplementary_actions.SupplementaryActionError,
            match=re.escape("has no action for (0008,2120)"),
        ):
            supplementary_actions.load_supplementary_actions(path)
    else:
        assert "(0008,2120)" not in (
            supplementary_actions.load_supplementary_actions(path).rules
        )


NEW_TAG = "(0014,0109)"  # Not in the 2026d data dictionary.


def _with_dictionary_attribute(tmp_path, vr):
    """Return the data dictionary with an attribute of ``vr`` added at ``NEW_TAG``.

    The dictionary is loaded, through the public loader, from a copy of the
    generated file with the row added, as a regenerated dictionary would add
    an attribute that Table E.1-1 omits.
    """
    document = json.loads(
        (standard.STANDARD_DIR / "data_dictionary.json").read_text(encoding="utf-8")
    )
    document["rows"].append(
        {
            "tag": NEW_TAG,
            "name": "Test Attribute",
            "keyword": "TestAttribute",
            "vr": vr,
            "vm": "1",
            "status": "",
        }
    )
    document["content_sha256"] = standard.content_sha256(document["rows"])
    path = tmp_path / "data_dictionary.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return standard.load_data_dictionary(path)


@pytest.mark.deid_requirement("MIDI-BP-06")
@pytest.mark.parametrize(
    "vr, required",
    [
        ("DA", True),
        ("DT", True),
        ("TM", True),
        ("PN", True),
        # An attribute of another VR, such as CS, needs no rule.
        ("CS", False),
    ],
)
def test_a_new_attribute_that_table_e1_1_omits_needs_a_rule_by_its_vr(
    tmp_path, monkeypatch, vr, required
):
    dictionary = _with_dictionary_attribute(tmp_path, vr)
    monkeypatch.setattr(
        supplementary_actions, "load_data_dictionary", lambda: dictionary
    )
    document = _document()
    path = _write(tmp_path / "supplementary_actions.toml", document)

    if not required:
        assert (
            NEW_TAG not in supplementary_actions.load_supplementary_actions(path).rules
        )
        return
    with pytest.raises(
        supplementary_actions.SupplementaryActionError,
        match=re.escape(f"has no action for {NEW_TAG}"),
    ):
        supplementary_actions.load_supplementary_actions(path)
    # A reviewed rule for the attribute lets the rules load again.
    document["attribute"].append(
        {
            "tag": NEW_TAG,
            "keyword": "TestAttribute",
            "action": "X/Z/D",
            "note": "A test.",
        }
    )
    loaded = supplementary_actions.load_supplementary_actions(
        _write(tmp_path / "reviewed.toml", document)
    )
    assert loaded.rules[NEW_TAG].action == "X/Z/D"


# The Nuclear Medicine Image IOD's text, by group, with the action of each.
NM_TEXT_GROUPS: tuple[tuple[set[str], str, dict[str, str]], ...] = (
    (NM_OPERATOR_TEXT, "X/Z/D", {CLEAN_DESCRIPTORS: "C"}),
    (NM_REMOVED_UNDER_EVERY_OPTION, "X/Z/D", {}),
)
# The IODs supported when Nuclear Medicine was reviewed, before it and
# Surface Segmentation were added independently.
NM_REVIEWED_AGAINST = SURFACE_REVIEWED_AGAINST
# The other attributes that the Nuclear Medicine Image IOD uses and those IODs
# do not, by VR, checked by hand against the 2026d PS3.3 and PS3.6: the
# vectors, counts, and sequences of the NM Multi-frame, NM Image, NM
# Isotope, NM Detector, NM TOMO Acquisition, NM Multi-gated Acquisition, NM
# Phase, and NM Reconstruction Modules, such as Energy Window Vector, Angular
# Step, and Whole Body Technique, and two attributes of the Multi-frame
# Overlay Module, none of which Table E.1-1 lists.
NM_OTHER_VRS = {"US": 18, "DS": 12, "IS": 10, "SQ": 8, "CS": 2}


def test_the_nm_iod_is_generated_and_supported():
    tables = iods.load_iod_tables()

    assert set(NM_IODS) <= set(tables.iods)
    assert set(NM_IODS) <= scope.SUPPORTED_IODS


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_the_text_that_only_the_nm_iod_uses_has_reviewed_rules():
    listed = set(_table_e1_1())
    added = _used_by(NM_IODS, TEXT_VRS) - _used_by(NM_REVIEWED_AGAINST, TEXT_VRS)
    rules = _rules()

    assert not added & listed
    assert added == NM_OPERATOR_TEXT | NM_REMOVED_UNDER_EVERY_OPTION
    for tags, action, options in NM_TEXT_GROUPS:
        for tag in tags:
            assert (rules[tag].action, dict(rules[tag].options)) == (
                action,
                options,
            ), tag
            assert rules[tag].note.strip(), tag


def test_each_policy_gives_the_nm_text_the_action_of_its_group():
    for composed in _every_policy():
        for tags, action, options in NM_TEXT_GROUPS:
            selected = [a for o, a in options.items() if o in composed.options]
            for tag in tags:
                assert composed.supplementary_actions[tag] == (
                    selected[0] if selected else action
                ), (tag, composed.options)


def test_the_nm_text_that_is_removed_is_type_3_so_removal_by_type_removes_it():
    tables = iods.load_iod_tables()
    iod = tables.iods[NM_IODS[0]]
    rules = _rules()
    removed = NM_OPERATOR_TEXT | NM_REMOVED_UNDER_EVERY_OPTION
    definitions = [d for d in iod.definitions if d.tag in removed]

    # Processing Function and Image ID are in the NM Image Module, and Energy
    # Window Name in the items of the NM Isotope Module's Energy Window
    # Information Sequence (0054,0012).
    assert {(d.tag, d.path) for d in definitions} == {
        ("(0018,5020)", ()),
        ("(0054,0018)", ("(0054,0012)",)),
        ("(0054,0400)", ()),
    }
    for definition in definitions:
        assert definition.type == "3", definition
        assert (
            compound_actions.resolve_in_iod(
                iod, definition.tag, definition.path, rules[definition.tag].action
            )
            == "X"
        ), definition


def test_the_nm_iod_uses_no_uid_date_name_or_url_that_the_others_do_not():
    for vrs in ({"UI"}, TEMPORAL_VRS, {"PN"}, {"UR"}):
        assert not _used_by(NM_IODS, vrs) - _used_by(NM_REVIEWED_AGAINST, vrs), vrs


def test_the_nm_iods_other_new_attributes_are_kept_by_the_default():
    dictionary = _dictionary()
    tables = iods.load_iod_tables()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    other = (
        _used_by(NM_IODS, every_vr)
        - _used_by(NM_REVIEWED_AGAINST, every_vr)
        - _used_by(NM_IODS, TEXT_VRS)
    )
    listed = set(_table_e1_1())
    rules = _rules()
    uids = set(uid_roles.load_uid_roles().rules)
    by_vr = collections.Counter(vr for tag in other for vr in dictionary[tag].vrs)

    assert by_vr == NM_OTHER_VRS
    assert all(len(dictionary[tag].vrs) == 1 for tag in other)
    assert not other & (listed | set(rules) | uids)
    # So each takes the default, which keeps it where the IOD defines it,
    # under every preset, with a sequence's items handled by their own rules;
    # an overlay's attributes are checked in its first repeating group.
    iod = tables.iods[NM_IODS[0]]
    for preset in policy.PRESETS:
        rules_of = element_rules.ElementRules(policy.compose_policy(preset))
        for definition in iod.definitions:
            if definition.tag not in other:
                continue
            tag = definition.tag.replace("(60xx,", "(6000,")
            rule = rules_of.rule(tag, definition.path, iod=iod)
            assert (rule.source, rule.action) == (
                element_rules.RuleSource.DEFAULT,
                element_rules.KEEP,
            ), (preset, definition)


# Surface Segmentation.

# The text of the Surface Mesh Module that no IOD reviewed before it uses:
# Surface Comments and Surface Processing Description, each typed text.
SURFACE_TEXT = {"(0066,0004)", "(0066,000B)"}
# The other attributes that it adds, of its Surface Segmentation and Surface
# Mesh Modules: counts, numbers, coded flags, opacities, distances, and the
# meshes themselves, its points' coordinates and normals and the indices of
# its primitives, each a VR that cannot hold a name or a date.
SURFACE_OTHER_VRS = {"SQ": 12, "FL": 11, "UL": 6, "OL": 4, "CS": 4, "OF": 2, "US": 1}
SURFACE_MESH_MODULES = {"Surface Segmentation", "Surface Mesh"}


def test_surface_segmentation_is_generated_and_supported():
    tables = iods.load_iod_tables()

    assert set(SURFACE_IODS) <= set(tables.iods)
    assert set(SURFACE_IODS) <= scope.SUPPORTED_IODS


@pytest.mark.deid_requirement("MIDI-BP-05", "MIDI-BP-06", "MIDI-BP-11")
def test_the_text_that_only_surface_segmentation_uses_has_reviewed_rules():
    listed = set(_table_e1_1())
    rules = _rules()
    added = _used_by(SURFACE_IODS, TEXT_VRS) - _used_by(
        SURFACE_REVIEWED_AGAINST, TEXT_VRS
    )

    assert added == SURFACE_TEXT
    assert not added & listed
    for tag in added:
        # Typed text, removed by Type, which removes it, since it is Type 3,
        # and cleaned as a descriptor under Clean Descriptors.
        assert (rules[tag].action, dict(rules[tag].options)) == (
            "X/Z/D",
            {CLEAN_DESCRIPTORS: "C"},
        ), tag
        assert rules[tag].note.strip(), tag
        assert _resolved_in(SURFACE_IODS, tag, "X/Z/D") == {"X"}, tag
    # Every other text that it uses, such as its segments' labels, has the
    # action that it has where the IODs reviewed before it use it.
    for tag in _used_by(SURFACE_IODS, TEXT_VRS) - added - listed:
        assert rules[tag].note.strip(), tag


def test_every_uid_date_and_name_that_surface_segmentation_uses_has_a_role():
    uids = uid_roles.load_uid_roles()
    temporal = temporal_roles.load_temporal_roles()

    for tag in _used_by(SURFACE_IODS, {"UI"}):
        assert isinstance(uids.role(tag), uid_roles.UIDRole), tag
    for tag in _used_by(SURFACE_IODS, TEMPORAL_VRS):
        assert isinstance(temporal.role(tag), temporal_roles.TemporalRole), tag
    # The IODs reviewed before it use every UID, person name, URL, date,
    # time, and datetime that it uses.
    for vrs in ({"UI"}, {"PN"}, {"UR"}, TEMPORAL_VRS):
        assert not _used_by(SURFACE_IODS, vrs) - _used_by(
            SURFACE_REVIEWED_AGAINST, vrs
        ), vrs


def test_removal_by_type_gives_surface_segmentation_only_the_reviewed_actions():
    actions_by_tag = _record_actions()
    dictionary = _dictionary()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    new = {}

    for tag in sorted(_used_by(SURFACE_IODS, every_vr)):
        action = actions_by_tag.get(tag)
        if action not in compound_actions.COMPOUND_ACTIONS:
            continue
        resolved = _resolved_in(SURFACE_IODS, tag, action)
        reviewed = _resolved_in(SURFACE_REVIEWED_AGAINST, tag, action)
        if not resolved <= reviewed:
            new[tag] = resolved

    # Only its own text, which no IOD reviewed before it uses, so nowhere
    # does removal by Type replace a value with a dummy that it did not.
    assert new == {tag: {"X"} for tag in SURFACE_TEXT}


def test_surface_segmentations_other_new_attributes_are_kept_by_the_default():
    dictionary = _dictionary()
    tables = iods.load_iod_tables()
    every_vr = {vr for attribute in dictionary.values() for vr in attribute.vrs}
    new = _used_by(SURFACE_IODS, every_vr) - _used_by(
        SURFACE_REVIEWED_AGAINST, every_vr
    )
    other = new - SURFACE_TEXT
    listed = set(_table_e1_1())
    rules = _rules()
    uids = set(uid_roles.load_uid_roles().rules)
    by_vr = collections.Counter(vr for tag in other for vr in dictionary[tag].vrs)

    assert by_vr == SURFACE_OTHER_VRS
    assert all(len(dictionary[tag].vrs) == 1 for tag in other)
    assert not other & (listed | set(rules) | uids)
    # So each takes the default, which keeps it where Surface Segmentation
    # defines it, under every preset, its meshes included, with a sequence's
    # items handled by their own rules: no profile action removes a mesh,
    # which only Clean Recognizable Visual Features answers for (D-046).
    iod = tables.iods["Surface Segmentation"]
    for preset in policy.PRESETS:
        rules_of = element_rules.ElementRules(policy.compose_policy(preset))
        for definition in iod.definitions:
            if definition.tag not in other:
                continue
            assert definition.module in SURFACE_MESH_MODULES, definition
            rule = rules_of.rule(definition.tag, definition.path, iod=iod)
            assert (rule.source, rule.action) == (
                element_rules.RuleSource.DEFAULT,
                element_rules.KEEP,
            ), (preset, definition)
