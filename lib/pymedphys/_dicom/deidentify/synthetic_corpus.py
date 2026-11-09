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

"""A synthetic collection with a conspicuous marker in each attribute to protect.

:func:`build_corpus` builds, in memory and the same way every time, one
linked collection of the first supported release's IODs, all of one
fictitious patient and study, with one Frame of Reference: three CT Image
slices, an RT Structure Set that references the CT series and slices, an RT
Plan that references the structure set and the dose, an RT Dose that
references the plan, a second RT Dose of the plan for review (below), one
instance of each of fifty-five other IODs, and two of the Segmentation
IOD, one of each of its SOP Classes, each in a series of its own, and a
second X-Ray Radiation Dose SR, of a CT scan.
The MR Image and PET Image instances reference the first CT slice, and each
enhanced, legacy converted enhanced, or MR Spectroscopy instance references
the single-frame instance of its modality: the first CT slice, the MR
Image, or the PET Image. The Spatial Registration registers the MR Image to
the Frame of Reference by an identity matrix, and the Deformable Spatial
Registration the PET Image by a two by two by one deformation grid; each
names its image in Referenced Image Sequence (0008,1140), whose item the
Basic Profile keeps, and the Spatial Registration's Used RT Structure Set
ROI Sequence (0070,0315) names the structure set. The RT Beams Treatment
Record references the plan. The RT Ion Plan references what the RT Plan
does, the structure set, the RT Dose, and the RT Plan, which it names as a
related plan, and the RT Ion Beams Treatment Record references the RT Ion
Plan. The RT Brachy Treatment Record references the RT Plan, which has
brachytherapy application setups as well as beams, and names the RT Beams
Treatment Record as a related record, and the RT Treatment Summary Record
references the RT Plan and, as a treatment record that it summarises, the
RT Brachy Treatment Record. The Encapsulated PDF names the RT Plan in its
Source Instance Sequence (0042,0013), and holds no document, since its
Encapsulated Document (0042,0011) and Content Sequence (0040,A730) would
sequester it (below). The RT Beams Delivery Instruction references
the RT Plan, the RT Beams Treatment Record as the record of the session that
it continues, and the RT Image as a reference image for verifying a beam;
the RT Brachy Application Setup Delivery Instruction references the RT Plan,
by its study, series, and instance; and the RT Radiation Set Delivery
Instruction references the RT Radiation Set and its C-Arm Photon-Electron
Radiation. The RT Image, a digitally reconstructed radiograph of 2 by 2
pixels, references the RT Plan, as do the Enhanced RT Image, a digitally
reconstructed radiograph, and the Enhanced Continuous RT Image, a simulator
image, each of two frames of 2 by 2 pixels. The X-Ray Radiation Dose SRs and
the Enhanced X-Ray Radiation Dose SR reference the first CT slice, the
Radiopharmaceutical Radiation Dose SR the PET Image, the Patient Radiation
Dose SR the CT dose report, which its estimate used, and the Basic Text
SR, Enhanced SR, Comprehensive SR, Comprehensive 3D SR, and Extensible SR
the MR Image. The Segmentations, a BINARY one of Segmentation Storage and a
LABELMAP one of Label Map Segmentation Storage, reference the CT series and
its first slice, and each segments the planes of the first two slices. The
Surface Segmentation, one closed tetrahedral mesh of a Tissue segment,
references the CT series and its first slice too. The
Key Object Selection Document selects the MR Image; the Mammography CAD SR
and Chest CAD SR name the RT Image, a projection radiograph, as the image that their CAD read, and the Colon CAD SR the CT
series; and the Procedure Log, Spectacle Prescription Report, Macular Grid
Thickness and Volume Report, and Waveform Annotation SR reference the MR
Image. The Parametric Map, an apparent diffusion coefficient map of 16-bit
integers whose two frames lie in the planes of the first two CT slices,
references the MR Image, and the Real World Value Mapping maps the PET
Image's stored values to a standardised uptake value and names it. Each
softcopy Presentation State names, in its Referenced Series Sequence
(0008,1115), or the blending one in its Blending Sequence (0070,0402), the
image that it presents: the grayscale, blending, and Variable Modality LUT
ones the first CT slice, the colour one the Enhanced MR Color Image, the
pseudo-colour one the PET Image, and the XA/XRF one the RT Image. It is the
input for validating each preset end to end: once the engine has written
the collection, the residual search
(:mod:`~pymedphys._dicom.deidentify.residuals`) should find none of the
markers that had to be removed or replaced.

**Markers.** Each attribute that Table E.1-1 lists and an instance's IOD
defines, at each place in the data set where the IOD's modules define it,
holds a marker: a value that is valid for the attribute's VR and VM in the
pinned PS3.6 data dictionary, and that no other placement in the collection
holds, except for the two placements that **Diagnostics and review**
describes. Text is ``SYNMK-00042``, a code string ``SYNMK_00042``, a person name
``SYNMK00042^MARKER00042``, a UID ``2.25.9999900042``, a URI
``https://synmk.invalid/SYNMK-00042``, a date before 1900 (see
:func:`_marker_date`), a datetime that date at noon, a time ``HHMMSS.424242`` whose seconds from
midnight are the time's number, and a binary value of VR OB, OW, or UN the
text marker in ASCII, padded to an even length. Dates and datetimes, times,
and values of VR SS and US are each numbered by a count of their own, so
that the dates, the times, and the 16-bit integers do not run out before
the five digits of the markers do. No text marker occurs inside
another value of its file. A number of a binary VR, such as US or SS, and an
age (AS) cannot be made conspicuous: each is distinct, but it is found by
its place in the manifest, not by searching bytes. Each sequence that holds
a placement has one item, created along the path where needed, so every
place is reached through items numbered 0, except in a Structured Report's
content tree (below).

**Content trees.** Each Structured Report's and the Key Object Selection
Document's Content Sequence (0040,A730) holds a content tree that a
template builds
(:mod:`~pymedphys._dicom.deidentify.synthetic_content_trees`), and its
root's Concept Name Code Sequence (0040,A043) the report's title, rather
than markers: the Content Sequence is recorded with
:attr:`NotPlantedReason.CONTENT_TREE`, as is each attribute that the IOD
defines below the Concept Name Code Sequence. The places that the IOD
defines below the Content Sequence are not recorded, since the tree's
items, which need not be numbered 0, decide what each holds. The value of each content item that can
identify a person, a device, or a time, of Value Type UIDREF, DATE, TIME,
DATETIME, PNAME, or TEXT, holds a marker of its VR, but the UIDs that name
the collection's study, series, or Frame of Reference, such as the X-ray
reports' Study Instance UID of their scope of accumulation and the colon
CAD report's image set and CT series, which are recorded as linked, and the
fixed text of an algorithm's name or a patient orientation, which is not
recorded; an IMAGE item references the instance that the report's header
references, and the patient dose report's COMPOSITE item names the CT dose
report, each recorded as linked at its Referenced SOP Instance UID
(0008,1155). Each placement records its item's concept name
(:attr:`Placement.concept`), whose row of PS3.15 Table E.3.4-1 gives its
action under Clean Structured Content, and its path through the items of
the tree. The Basic Profile gives the Content Sequence D, which a sequence
has no dummy value for (D-021), so a report is sequestered unless Clean
Structured Content can clean every item of its tree. Its required X/D
items take dummy values; selected Retain options determine which values
are kept instead (D-047).

Some attributes must stay linked, so the collection's references resolve and
the reference graph (:mod:`~pymedphys._dicom.deidentify.reference_graph`)
has no findings: SOP Instance, Series Instance, and Study Instance UIDs at
the top level, Frame of Reference UID and Referenced Frame of Reference UID
wherever they are, each UID at a reference site
(:func:`~pymedphys._dicom.deidentify.references.reference_sites`), and the
Patient ID and Issuer of Patient ID at the top level. These hold the
collection's own UIDs, under ``2.25.88888``, and one patient's identifiers,
and are recorded as linked. A reference names an instance of the collection
with its SOP Class, except that Referenced Patient Sequence (0008,1120)
names a synthetic patient with Detached Patient Management SOP Class, and
Referenced Performed Procedure Step Sequence (0008,1111) a synthetic
procedure step with Modality Performed Procedure Step SOP Class, which the
reference graph does not resolve or report, since neither is a storage
class.

A sequence that Table E.1-1 lists is present with its item. Where no marker
is planted below it, a marker is put in the first attribute that the IOD
defines in its item, text first, unless the Basic Profile keeps the item and
replaces only its UIDs, as X/Z/U* does where the IOD requires the sequence,
such as a registration's Referenced Image Sequence (0008,1140), and keeps
each sequence of the table that encloses it: the sequence is then recorded
with :attr:`NotPlantedReason.KEPT_SEQUENCE`. A linked value does not count, since a
preset that keeps the sequence and replaces its UIDs would leave no marker.
Where the IOD defines no attribute in the item that can carry a marker, as
in Modified Attributes Sequence (0400,0550), or Referenced Patient Sequence,
whose item holds only UIDs, the sequence is recorded with
:attr:`NotPlantedReason.NO_MARKER_CARRIER`: its removal is checked by its
absence at its path in the manifest, not by the residual search.

**Caps.** An attribute is planted only where it lies in at most
:data:`MAX_DEPTH` nested items, and a sequence only where its item does. The
deepest references of an RT Structure Set, its Contour Image Sequence in the
RT Referenced Series Sequence, lie at that depth; the deeper places, such as
the Code Sequence Macros nested in the Request Attributes Sequence, repeat
macros already planted at shallower places. A repeating group is planted in
its first group only: Overlay Data (60xx,3000), which of the collection's IODs
CT Image, MR Image, and PET Image define, is planted in group 6000 with VR
OW, of the OB or OW that PS3.6 allows, the VR that Implicit VR gives it. An
attribute that the pinned dictionary gives no single VR, and a tag whose element number is masked,
are not planted. Each placement not planted is recorded with a
:class:`NotPlantedReason`. Pixel Data is not an attribute of Table E.1-1 and
holds only a few synthetic samples: 2 by 2 pixels, in two frames in a
multi-frame IOD but one in the RT Image, and 4 by 4 in the BINARY
Segmentation, whose 1-bit frames then each fill whole bytes, monochrome but for the Enhanced MR
Color instance, whose RGB pixels come with the ICC Profile (0028,2000) its
IOD requires: :data:`SOURCE_ICC_PROFILE`, an sRGB profile
(:mod:`~pymedphys._dicom.deidentify.icc_profiles`) whose description,
copyright, device manufacturer and model descriptions, and a private tag
hold :data:`SOURCE_ICC_DESCRIPTION`, which begins with the marker prefix, so
that any of them would be found if kept. The MR Spectroscopy instance holds two values of
Spectroscopy Data (5600,0020) and no Pixel Data. A functional group sequence
has the one item that its markers need, not one for each frame; like every
instance of the corpus, the multi-frame instances do not hold every
attribute their IODs require.

**Sequestering attributes.** An attribute whose Basic Profile action is a
plain X, and whose removal sequesters the instance because the IOD requires
it at a place no Type 3 sequence encloses
(:func:`~pymedphys._dicom.deidentify.compound_actions.resolve_plain_x_in_iod`),
or whose Basic Profile action resolves to D at its place where its VR has
no dummy value and no reviewed rule gives it one
(:mod:`~pymedphys._dicom.deidentify.dummy_values`),
is planted only in :data:`SEQUESTERED_FILE`, the third CT slice, and
recorded in the other files with
:attr:`NotPlantedReason.SEQUESTERS_INSTANCE`, as is each attribute in the
item of such a sequence. Of the corpus's IODs these
are Responsible Person (0010,2297) and Responsible Organization (0010,2299)
at the top level, and Radiopharmaceutical Start DateTime (0018,1078) in the
Radiopharmaceutical Information Sequence (0054,0016) of an Enhanced PET
Image, and Encapsulated Document (0042,0011) and Content Sequence
(0040,A730), with each attribute of the sequence's items, in an
Encapsulated PDF, since the Basic Profile gives each D and neither VR has
a dummy value; and, in each softcopy Presentation State, Presentation
Creation Date (0070,0082) and Time (0070,0083), Type 1 at the top level, the Graphic
Annotation Sequence (0070,0001), and Overlay Data (60xx,3000), which these
IODs define in a conditional Overlay Plane Module. Institution Code Sequence
(0008,0082), which X/Z/D gives D where it is Type 1C, in the Interlock
Resolution User Sequence (300A,0746) of an RT
Beams Treatment Record's or RT Ion Beams Treatment Record's Interlock
Sequence (300A,0740), is planted there, since a reviewed rule gives it a
dummy item at that place and only there. Planted in
every file, the first two would sequester every
instance, and no preset could release any of the collection; planted in one,
that instance checks sequestration, :data:`REVIEW_FILE` checks review, and
the other sixty-three check each preset's output, the reports where their
trees are cleaned. Radiopharmaceutical Start
DateTime, which CT Image does not define there, is planted in no file, so
the Enhanced PET instance, which lacks an attribute of Type 1, is released
and its other markers are checked. So is each Presentation State: CT Image
does not define its creation date and time or Graphic Annotation Sequence,
and defines Overlay Data in a user-optional module, whose group the Basic
Profile removes, so these are planted in no file either. An Enhanced PET
Image instance that conforms to the IOD is sequestered under ``basic`` and
``basic-clean-descriptors``, as is a softcopy Presentation State that does.
Nor does CT Image define the Encapsulated PDF's document or Content Sequence,
which are planted in no file either,
so that the Encapsulated PDF is released and its header's markers are
checked; one that holds its document is sequestered under every preset.

**Edge cases.** Each file except the first RT Dose, ``06-rtdose.dcm``, and
the MR Image, ``10-mr.dcm``, is written in Explicit VR Little Endian, and
those two in Implicit VR Little Endian. pydicom 3.0.2 does not know some
newer attributes, such as (0008,001D), and reads them from those files as
UN; the engine reads them
with the pinned dictionary. The first CT slice holds Patient Comments
(0010,4000) encoded with VR UN.
The RT Structure Set declares Specific Character Set ``ISO_IR 100`` and its
Patient's Name holds a Latin-1 letter. Every file has a private block of a
synthetic private creator at the top level, and another in the item of
Procedure Code Sequence (0008,1032), which pydicom knows; in the Implicit VR
files neither has a VR in the file. Every file is admitted by the engine's
strict source reader
(:func:`~pymedphys._dicom.deidentify.source.read_source`); none is
deliberately outside admission.

**Diagnostics and review.** Two placements exercise paths that a clean
collection never reaches. The RT Plan's Device UID (0018,1002), which the
Basic Profile replaces, holds ``2.25.`` followed by a text marker, which VR
UI does not allow (:attr:`PlacementKind.INVALID`): the strict reader admits
it, and pydicom, by default, warns and quotes it whenever it converts it, so
a run must keep the warning's text out of what it shows.
:data:`REVIEW_FILE`, a second RT Dose that references the plan and that the
plan does not reference, keeps in
Manufacturer's Model Name (0008,1090), which Table E.1-1 does not list and
the Basic Profile keeps, a copy of the RT Plan's RT Plan Label marker
(:attr:`PlacementKind.REVIEW_COPY`), so the residual search finds a source
value of another instance in its output and sends it to review. The third
CT slice remains sequestered; the other sixty-three files stay releasable, the
reports where their trees are cleaned.

**Manifest.** :class:`CorpusManifest` records, for each file, each
placement: its element path, VR, values, kind, the Table E.1-1 row it
covers, why it was not planted where it was not, and a content item's
concept name.
:meth:`CorpusManifest.to_json` serialises it the same way every time.
Building reads the bundled tables, writes no files, uses no clock or
randomness, and logs nothing; :func:`write_corpus` writes the files to the
directory :data:`INSTANCES_DIRECTORY` of a directory its caller names, and
the manifest beside it, so that the directory of instances can be a run's
input.
"""

# The builder, its manifest's types, and its description stay together, so
# the module is long.
# pylint: disable = too-many-lines

from __future__ import annotations

import collections
import dataclasses
import datetime
import enum
import functools
import io
import json
import pathlib
import struct
import types
from collections.abc import Sequence

from pymedphys._imports import pydicom

from . import icc_profiles
from .compound_actions import (
    COMPOUND_ACTIONS,
    RemovalExtent,
    resolve_in_iod,
    resolve_plain_in_iod,
    resolve_plain_x_in_iod,
)
from .dummy_values import (
    DUMMY_VRS,
    INSTITUTION_CODE_SEQUENCE,
    PERSON_IDENTIFICATION_CODE_SEQUENCE,
    REFERENCED_PERFORMED_PROCEDURE_STEP_SEQUENCE,
    VERIFYING_OBSERVER_SEQUENCE,
    reviewed_within,
)
from .elements import dataset_codecs, new_element
from .file_layout import ElementPath
from .iods import IOD
from .references import (
    REFERENCE_TAGS,
    REFERENCED_SOP_CLASS_TAG,
    REFERENCED_SOP_INSTANCE_TAG,
    Level,
    reference_sites,
)
from .sop_classes import iod_for_sop_class
from .standard import (
    PRIVATE_ATTRIBUTES_TAG,
    VM_PATTERN,
    dictionary_attribute,
    load_table_e1_1,
)
from .synthetic_content_trees import (
    BASIC_TEXT_SR_STORAGE,
    CHEST_CAD_SR_STORAGE,
    COLON_CAD_SR_STORAGE,
    COMPREHENSIVE_3D_SR_STORAGE,
    COMPREHENSIVE_SR_STORAGE,
    CT_RADIATION_DOSE_TEMPLATE,
    ENHANCED_SR_STORAGE,
    ENHANCED_X_RAY_RADIATION_DOSE_SR_STORAGE,
    EXTENSIBLE_SR_STORAGE,
    KEY_OBJECT_SELECTION_DOCUMENT_STORAGE,
    MACULAR_GRID_THICKNESS_AND_VOLUME_REPORT_STORAGE,
    MAMMOGRAPHY_CAD_SR_STORAGE,
    PATIENT_RADIATION_DOSE_SR_STORAGE,
    PROCEDURE_LOG_STORAGE,
    RADIOPHARMACEUTICAL_RADIATION_DOSE_SR_STORAGE,
    ROOT_TEMPLATES,
    SPECTACLE_PRESCRIPTION_REPORT_STORAGE,
    WAVEFORM_ANNOTATION_SR_STORAGE,
    X_RAY_RADIATION_DOSE_SR_STORAGE,
    Image,
    chest_cad_tree,
    colon_cad_tree,
    ct_dose_tree,
    enhanced_x_ray_dose_tree,
    imaging_report_tree,
    key_object_selection_tree,
    macular_grid_tree,
    mammography_cad_tree,
    measurement_report_tree,
    patient_dose_tree,
    procedure_log_tree,
    radiopharmaceutical_dose_tree,
    spectacle_prescription_tree,
    waveform_annotation_tree,
    x_ray_dose_tree,
)
from .values import values_problem

IMPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2"
EXPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2.1"

CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
ENHANCED_CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2.1"
LEGACY_CONVERTED_ENHANCED_CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2.2"
MR_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.4"
ENHANCED_MR_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.4.1"
MR_SPECTROSCOPY_STORAGE = "1.2.840.10008.5.1.4.1.1.4.2"
ENHANCED_MR_COLOR_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.4.3"
LEGACY_CONVERTED_ENHANCED_MR_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.4.4"
PET_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.128"
LEGACY_CONVERTED_ENHANCED_PET_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.128.1"
ENHANCED_PET_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.130"
SPATIAL_REGISTRATION_STORAGE = "1.2.840.10008.5.1.4.1.1.66.1"
DEFORMABLE_SPATIAL_REGISTRATION_STORAGE = "1.2.840.10008.5.1.4.1.1.66.3"
RT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.1"
RT_DOSE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.2"
RT_STRUCTURE_SET_STORAGE = "1.2.840.10008.5.1.4.1.1.481.3"
RT_BEAMS_TREATMENT_RECORD_STORAGE = "1.2.840.10008.5.1.4.1.1.481.4"
RT_PLAN_STORAGE = "1.2.840.10008.5.1.4.1.1.481.5"
SEGMENTATION_STORAGE = "1.2.840.10008.5.1.4.1.1.66.4"
LABEL_MAP_SEGMENTATION_STORAGE = "1.2.840.10008.5.1.4.1.1.66.7"
SURFACE_SEGMENTATION_STORAGE = "1.2.840.10008.5.1.4.1.1.66.5"
RT_ION_PLAN_STORAGE = "1.2.840.10008.5.1.4.1.1.481.8"
RT_ION_BEAMS_TREATMENT_RECORD_STORAGE = "1.2.840.10008.5.1.4.1.1.481.9"
RT_BRACHY_TREATMENT_RECORD_STORAGE = "1.2.840.10008.5.1.4.1.1.481.6"
RT_TREATMENT_SUMMARY_RECORD_STORAGE = "1.2.840.10008.5.1.4.1.1.481.7"
PARAMETRIC_MAP_STORAGE = "1.2.840.10008.5.1.4.1.1.30"
REAL_WORLD_VALUE_MAPPING_STORAGE = "1.2.840.10008.5.1.4.1.1.67"
ENCAPSULATED_PDF_STORAGE = "1.2.840.10008.5.1.4.1.1.104.1"
ENHANCED_RT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.23"
ENHANCED_CONTINUOUS_RT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.24"
GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE = "1.2.840.10008.5.1.4.1.1.11.1"
COLOR_SOFTCOPY_PRESENTATION_STATE_STORAGE = "1.2.840.10008.5.1.4.1.1.11.2"
PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE_STORAGE = "1.2.840.10008.5.1.4.1.1.11.3"
BLENDING_SOFTCOPY_PRESENTATION_STATE_STORAGE = "1.2.840.10008.5.1.4.1.1.11.4"
XA_XRF_GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE = "1.2.840.10008.5.1.4.1.1.11.5"
VARIABLE_MODALITY_LUT_SOFTCOPY_PRESENTATION_STATE_STORAGE = (
    "1.2.840.10008.5.1.4.1.1.11.12"
)
PRESENTATION_STATE_STORAGE_CLASSES = frozenset(
    {
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        COLOR_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        BLENDING_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        XA_XRF_GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        VARIABLE_MODALITY_LUT_SOFTCOPY_PRESENTATION_STATE_STORAGE,
    }
)
RT_SEGMENT_ANNOTATION_STORAGE = "1.2.840.10008.5.1.4.1.1.481.11"
RT_RADIATION_SET_STORAGE = "1.2.840.10008.5.1.4.1.1.481.12"
C_ARM_PHOTON_ELECTRON_RADIATION_STORAGE = "1.2.840.10008.5.1.4.1.1.481.13"
TOMOTHERAPEUTIC_RADIATION_STORAGE = "1.2.840.10008.5.1.4.1.1.481.14"
ROBOTIC_ARM_RADIATION_STORAGE = "1.2.840.10008.5.1.4.1.1.481.15"
RT_BEAMS_DELIVERY_INSTRUCTION_STORAGE = "1.2.840.10008.5.1.4.34.7"
RT_BRACHY_APPLICATION_SETUP_DELIVERY_INSTRUCTION_STORAGE = "1.2.840.10008.5.1.4.34.10"
RT_RADIATION_SET_DELIVERY_INSTRUCTION_STORAGE = "1.2.840.10008.5.1.4.1.1.481.21"
# The retired class that PS3.3 Sections 10.6.1 and C.8.8.5.4 give a study in
# a Referenced Study Sequence or RT Referenced Study Sequence item.
DETACHED_STUDY_MANAGEMENT = "1.2.840.10008.3.1.2.3.1"

# The most items an attribute is planted in, nested one in another.
MAX_DEPTH = 4
# Every marker's number is below this, so markers have a fixed width of five
# digits and none is the start of another. Dates, times, and values of VR SS
# and US are numbered apart (_Markers), each within its own limit: every date
# before 1900, every time within one day, and the 16-bit integers within
# their VRs.
MAX_MARKERS = 10**5
MARKER_PREFIX = "SYNMK"
MARKER_UID_ROOT = "2.25.99999"
LINKED_UID_ROOT = "2.25.88888"
# The one file in which an attribute whose removal sequesters is planted.
SEQUESTERED_FILE = "03-ct-3.dcm"
# The file that keeps a copy of another file's marker, for review.
REVIEW_FILE = "07-rtdose-review.dcm"
# The Structured Reports and the Key Object Selection Document, whose Content
# Sequence holds a content tree, which the Basic Profile's D sequesters, as a
# sequence has no dummy value: the radiation dose reports, the general
# reports, and the documents of the IODs that each name their root template.
# The X-Ray Radiation Dose SR IOD has two, of a projection radiograph and of
# a CT scan, which the Patient Radiation Dose SR's estimate used.
CT_DOSE_REPORT_FILE = "31-sr-dose-ct.dcm"
DOSE_REPORT_FILES = (
    "22-sr-dose-x-ray.dcm",
    "23-sr-dose-radiopharmaceutical.dcm",
    "29-sr-dose-enhanced-x-ray.dcm",
    "30-sr-dose-patient.dcm",
    CT_DOSE_REPORT_FILE,
)
GENERAL_REPORT_FILES = (
    "24-sr-basic-text.dcm",
    "25-sr-enhanced.dcm",
    "26-sr-comprehensive.dcm",
    "27-sr-comprehensive-3d.dcm",
    "28-sr-extensible.dcm",
)
TEMPLATE_REPORT_FILES = (
    "34-sr-key-object-selection.dcm",
    "35-sr-mammography-cad.dcm",
    "36-sr-chest-cad.dcm",
    "37-sr-colon-cad.dcm",
    "38-sr-procedure-log.dcm",
    "39-sr-spectacle-prescription.dcm",
    "40-sr-macular-grid.dcm",
    "41-sr-waveform-annotation.dcm",
)
STRUCTURED_REPORT_FILES = tuple(
    sorted(DOSE_REPORT_FILES + GENERAL_REPORT_FILES + TEMPLATE_REPORT_FILES)
)
# The Segmentations, of Segmentation Storage and Label Map Segmentation
# Storage.
SEGMENTATION_FILES = ("32-seg.dcm", "33-seg-label-map.dcm")
# The RT Ion Plan and the RT Ion Beams Treatment Record of it, numbered after
# the files that open pull requests add.
ION_PLAN_FILE = "47-rt-ion-plan.dcm"
ION_TREATMENT_RECORD_FILE = "48-rt-ion-beams-record.dcm"
# The RT Brachy Treatment Record of the RT Plan and the RT Treatment Summary
# Record of its course, numbered after the files that open pull requests add.
BRACHY_TREATMENT_RECORD_FILE = "49-rt-brachy-record.dcm"
TREATMENT_SUMMARY_RECORD_FILE = "50-rt-treatment-summary-record.dcm"
# The Parametric Map of the MR Image, and the Real World Value Mapping of the
# PET Image, numbered after the files that open pull requests add.
PARAMETRIC_MAP_FILE = "51-parametric-map.dcm"
REAL_WORLD_VALUE_MAPPING_FILE = "52-real-world-value-mapping.dcm"
# An Encapsulated PDF derived from the RT Plan, such as a plan report,
# numbered after the files that open pull requests add.
ENCAPSULATED_PDF_FILE = "54-encapsulated-pdf.dcm"
# The Surface Segmentation of the CT series, numbered after the files that
# open pull requests add.
SURFACE_SEGMENTATION_FILE = "55-seg-surface.dcm"
# The Enhanced RT Image and the Enhanced Continuous RT Image, each of the RT
# Plan's beam, numbered after the files that open pull requests add.
ENHANCED_RT_IMAGE_FILE = "89-rt-image-enhanced.dcm"
ENHANCED_CONTINUOUS_RT_IMAGE_FILE = "90-rt-image-enhanced-continuous.dcm"
# The softcopy Presentation States, one of each of the six IODs of PS3.3
# Sections A.33.1 to A.33.4, A.33.6, and A.33.8, numbered after the files
# that open pull requests add.
GRAYSCALE_PRESENTATION_STATE_FILE = "56-pr-grayscale.dcm"
COLOR_PRESENTATION_STATE_FILE = "57-pr-color.dcm"
PSEUDO_COLOR_PRESENTATION_STATE_FILE = "58-pr-pseudo-color.dcm"
BLENDING_PRESENTATION_STATE_FILE = "59-pr-blending.dcm"
XA_XRF_PRESENTATION_STATE_FILE = "60-pr-xa-xrf-grayscale.dcm"
VARIABLE_MODALITY_LUT_PRESENTATION_STATE_FILE = "61-pr-variable-modality-lut.dcm"
PRESENTATION_STATE_FILES = (
    GRAYSCALE_PRESENTATION_STATE_FILE,
    COLOR_PRESENTATION_STATE_FILE,
    PSEUDO_COLOR_PRESENTATION_STATE_FILE,
    BLENDING_PRESENTATION_STATE_FILE,
    XA_XRF_PRESENTATION_STATE_FILE,
    VARIABLE_MODALITY_LUT_PRESENTATION_STATE_FILE,
)
# The RT Segment Annotation of the Segmentation, and the RT Radiation Set and
# the three radiations, one of each second-generation radiation IOD, that it
# gathers, numbered after the files that open pull requests add.
SEGMENT_ANNOTATION_FILE = "70-rt-segment-annotation.dcm"
RADIATION_SET_FILE = "71-rt-radiation-set.dcm"
C_ARM_RADIATION_FILE = "72-c-arm-radiation.dcm"
TOMOTHERAPEUTIC_RADIATION_FILE = "73-tomotherapeutic-radiation.dcm"
ROBOTIC_ARM_RADIATION_FILE = "74-robotic-arm-radiation.dcm"
# The delivery instructions of the RT Plan's beams, of its brachytherapy
# application setups, and of the RT Radiation Set's radiations, numbered
# after the files that open pull requests add.
BEAMS_DELIVERY_INSTRUCTION_FILE = "75-rt-beams-delivery-instruction.dcm"
BRACHY_DELIVERY_INSTRUCTION_FILE = "76-rt-brachy-delivery-instruction.dcm"
RADIATION_SET_DELIVERY_INSTRUCTION_FILE = "77-rt-radiation-set-delivery-instruction.dcm"
# The directory, within the one that write_corpus is given, of the files.
INSTANCES_DIRECTORY = "instances"

STUDY = f"{LINKED_UID_ROOT}00001"
FRAME_OF_REFERENCE = f"{LINKED_UID_ROOT}00002"
CT_SERIES = f"{LINKED_UID_ROOT}00100"
CT_SLICES = tuple(f"{LINKED_UID_ROOT}0010{number}" for number in (1, 2, 3))
STRUCTURE_SET_SERIES = f"{LINKED_UID_ROOT}00200"
STRUCTURE_SET = f"{LINKED_UID_ROOT}00201"
PLAN_SERIES = f"{LINKED_UID_ROOT}00300"
PLAN = f"{LINKED_UID_ROOT}00301"
DOSE_SERIES = f"{LINKED_UID_ROOT}00400"
DOSE = f"{LINKED_UID_ROOT}00401"
REVIEW_DOSE = f"{LINKED_UID_ROOT}00402"
# One instance, in a series of its own, of each IOD of the first supported
# release that is not CT Image or an RT IOD.
ENHANCED_CT_SERIES = f"{LINKED_UID_ROOT}00500"
ENHANCED_CT = f"{LINKED_UID_ROOT}00501"
LEGACY_CT_SERIES = f"{LINKED_UID_ROOT}00600"
LEGACY_CT = f"{LINKED_UID_ROOT}00601"
MR_SERIES = f"{LINKED_UID_ROOT}00700"
MR = f"{LINKED_UID_ROOT}00701"
ENHANCED_MR_SERIES = f"{LINKED_UID_ROOT}00800"
ENHANCED_MR = f"{LINKED_UID_ROOT}00801"
MR_COLOR_SERIES = f"{LINKED_UID_ROOT}00900"
MR_COLOR = f"{LINKED_UID_ROOT}00901"
LEGACY_MR_SERIES = f"{LINKED_UID_ROOT}01000"
LEGACY_MR = f"{LINKED_UID_ROOT}01001"
SPECTROSCOPY_SERIES = f"{LINKED_UID_ROOT}01100"
SPECTROSCOPY = f"{LINKED_UID_ROOT}01101"
PET_SERIES = f"{LINKED_UID_ROOT}01200"
PET = f"{LINKED_UID_ROOT}01201"
ENHANCED_PET_SERIES = f"{LINKED_UID_ROOT}01300"
ENHANCED_PET = f"{LINKED_UID_ROOT}01301"
LEGACY_PET_SERIES = f"{LINKED_UID_ROOT}01400"
LEGACY_PET = f"{LINKED_UID_ROOT}01401"
REGISTRATION_SERIES = f"{LINKED_UID_ROOT}01500"
REGISTRATION = f"{LINKED_UID_ROOT}01501"
DEFORMABLE_REGISTRATION_SERIES = f"{LINKED_UID_ROOT}01600"
DEFORMABLE_REGISTRATION = f"{LINKED_UID_ROOT}01601"
TREATMENT_RECORD_SERIES = f"{LINKED_UID_ROOT}01700"
TREATMENT_RECORD = f"{LINKED_UID_ROOT}01701"
RT_IMAGE_SERIES = f"{LINKED_UID_ROOT}01800"
RT_IMAGE = f"{LINKED_UID_ROOT}01801"
X_RAY_DOSE_REPORT_SERIES = f"{LINKED_UID_ROOT}01900"
X_RAY_DOSE_REPORT = f"{LINKED_UID_ROOT}01901"
RADIOPHARMACEUTICAL_DOSE_REPORT_SERIES = f"{LINKED_UID_ROOT}02000"
RADIOPHARMACEUTICAL_DOSE_REPORT = f"{LINKED_UID_ROOT}02001"
BASIC_TEXT_REPORT_SERIES = f"{LINKED_UID_ROOT}02100"
BASIC_TEXT_REPORT = f"{LINKED_UID_ROOT}02101"
ENHANCED_REPORT_SERIES = f"{LINKED_UID_ROOT}02200"
ENHANCED_REPORT = f"{LINKED_UID_ROOT}02201"
COMPREHENSIVE_REPORT_SERIES = f"{LINKED_UID_ROOT}02300"
COMPREHENSIVE_REPORT = f"{LINKED_UID_ROOT}02301"
COMPREHENSIVE_3D_REPORT_SERIES = f"{LINKED_UID_ROOT}02400"
COMPREHENSIVE_3D_REPORT = f"{LINKED_UID_ROOT}02401"
EXTENSIBLE_REPORT_SERIES = f"{LINKED_UID_ROOT}02500"
EXTENSIBLE_REPORT = f"{LINKED_UID_ROOT}02501"
ENHANCED_X_RAY_DOSE_REPORT_SERIES = f"{LINKED_UID_ROOT}02600"
ENHANCED_X_RAY_DOSE_REPORT = f"{LINKED_UID_ROOT}02601"
PATIENT_DOSE_REPORT_SERIES = f"{LINKED_UID_ROOT}02700"
PATIENT_DOSE_REPORT = f"{LINKED_UID_ROOT}02701"
CT_DOSE_REPORT_SERIES = f"{LINKED_UID_ROOT}02800"
CT_DOSE_REPORT = f"{LINKED_UID_ROOT}02801"
SEGMENTATION_SERIES = f"{LINKED_UID_ROOT}02900"
SEGMENTATION = f"{LINKED_UID_ROOT}02901"
LABEL_MAP_SEGMENTATION_SERIES = f"{LINKED_UID_ROOT}03000"
LABEL_MAP_SEGMENTATION = f"{LINKED_UID_ROOT}03001"
KEY_OBJECT_SELECTION_SERIES = f"{LINKED_UID_ROOT}03100"
KEY_OBJECT_SELECTION = f"{LINKED_UID_ROOT}03101"
MAMMOGRAPHY_CAD_REPORT_SERIES = f"{LINKED_UID_ROOT}03200"
MAMMOGRAPHY_CAD_REPORT = f"{LINKED_UID_ROOT}03201"
CHEST_CAD_REPORT_SERIES = f"{LINKED_UID_ROOT}03300"
CHEST_CAD_REPORT = f"{LINKED_UID_ROOT}03301"
COLON_CAD_REPORT_SERIES = f"{LINKED_UID_ROOT}03400"
COLON_CAD_REPORT = f"{LINKED_UID_ROOT}03401"
PROCEDURE_LOG_SERIES = f"{LINKED_UID_ROOT}03500"
PROCEDURE_LOG = f"{LINKED_UID_ROOT}03501"
SPECTACLE_PRESCRIPTION_SERIES = f"{LINKED_UID_ROOT}03600"
SPECTACLE_PRESCRIPTION = f"{LINKED_UID_ROOT}03601"
MACULAR_GRID_REPORT_SERIES = f"{LINKED_UID_ROOT}03700"
MACULAR_GRID_REPORT = f"{LINKED_UID_ROOT}03701"
WAVEFORM_ANNOTATION_SERIES = f"{LINKED_UID_ROOT}03800"
WAVEFORM_ANNOTATION = f"{LINKED_UID_ROOT}03801"
ION_PLAN_SERIES = f"{LINKED_UID_ROOT}04400"
ION_PLAN = f"{LINKED_UID_ROOT}04401"
ION_TREATMENT_RECORD_SERIES = f"{LINKED_UID_ROOT}04500"
ION_TREATMENT_RECORD = f"{LINKED_UID_ROOT}04501"
BRACHY_TREATMENT_RECORD_SERIES = f"{LINKED_UID_ROOT}04600"
BRACHY_TREATMENT_RECORD = f"{LINKED_UID_ROOT}04601"
TREATMENT_SUMMARY_RECORD_SERIES = f"{LINKED_UID_ROOT}04700"
TREATMENT_SUMMARY_RECORD = f"{LINKED_UID_ROOT}04701"
PARAMETRIC_MAP_SERIES = f"{LINKED_UID_ROOT}04800"
PARAMETRIC_MAP = f"{LINKED_UID_ROOT}04801"
REAL_WORLD_VALUE_MAPPING_SERIES = f"{LINKED_UID_ROOT}04900"
REAL_WORLD_VALUE_MAPPING = f"{LINKED_UID_ROOT}04901"
ENCAPSULATED_PDF_SERIES = f"{LINKED_UID_ROOT}05100"
ENCAPSULATED_PDF = f"{LINKED_UID_ROOT}05101"
SURFACE_SEGMENTATION_SERIES = f"{LINKED_UID_ROOT}05200"
SURFACE_SEGMENTATION = f"{LINKED_UID_ROOT}05201"
ENHANCED_RT_IMAGE_SERIES = f"{LINKED_UID_ROOT}08500"
ENHANCED_RT_IMAGE = f"{LINKED_UID_ROOT}08501"
ENHANCED_CONTINUOUS_RT_IMAGE_SERIES = f"{LINKED_UID_ROOT}08600"
ENHANCED_CONTINUOUS_RT_IMAGE = f"{LINKED_UID_ROOT}08601"
GRAYSCALE_PRESENTATION_STATE_SERIES = f"{LINKED_UID_ROOT}05300"
GRAYSCALE_PRESENTATION_STATE = f"{LINKED_UID_ROOT}05301"
COLOR_PRESENTATION_STATE_SERIES = f"{LINKED_UID_ROOT}05400"
COLOR_PRESENTATION_STATE = f"{LINKED_UID_ROOT}05401"
PSEUDO_COLOR_PRESENTATION_STATE_SERIES = f"{LINKED_UID_ROOT}05500"
PSEUDO_COLOR_PRESENTATION_STATE = f"{LINKED_UID_ROOT}05501"
BLENDING_PRESENTATION_STATE_SERIES = f"{LINKED_UID_ROOT}05600"
BLENDING_PRESENTATION_STATE = f"{LINKED_UID_ROOT}05601"
XA_XRF_PRESENTATION_STATE_SERIES = f"{LINKED_UID_ROOT}05700"
XA_XRF_PRESENTATION_STATE = f"{LINKED_UID_ROOT}05701"
VARIABLE_MODALITY_LUT_PRESENTATION_STATE_SERIES = f"{LINKED_UID_ROOT}05800"
VARIABLE_MODALITY_LUT_PRESENTATION_STATE = f"{LINKED_UID_ROOT}05801"
SEGMENT_ANNOTATION_SERIES = f"{LINKED_UID_ROOT}06600"
SEGMENT_ANNOTATION = f"{LINKED_UID_ROOT}06601"
RADIATION_SET_SERIES = f"{LINKED_UID_ROOT}06700"
RADIATION_SET = f"{LINKED_UID_ROOT}06701"
C_ARM_RADIATION_SERIES = f"{LINKED_UID_ROOT}06800"
C_ARM_RADIATION = f"{LINKED_UID_ROOT}06801"
TOMOTHERAPEUTIC_RADIATION_SERIES = f"{LINKED_UID_ROOT}06900"
TOMOTHERAPEUTIC_RADIATION = f"{LINKED_UID_ROOT}06901"
ROBOTIC_ARM_RADIATION_SERIES = f"{LINKED_UID_ROOT}07000"
ROBOTIC_ARM_RADIATION = f"{LINKED_UID_ROOT}07001"
BEAMS_DELIVERY_INSTRUCTION_SERIES = f"{LINKED_UID_ROOT}07100"
BEAMS_DELIVERY_INSTRUCTION = f"{LINKED_UID_ROOT}07101"
BRACHY_DELIVERY_INSTRUCTION_SERIES = f"{LINKED_UID_ROOT}07200"
BRACHY_DELIVERY_INSTRUCTION = f"{LINKED_UID_ROOT}07201"
RADIATION_SET_DELIVERY_INSTRUCTION_SERIES = f"{LINKED_UID_ROOT}07300"
RADIATION_SET_DELIVERY_INSTRUCTION = f"{LINKED_UID_ROOT}07301"
# A patient and a procedure step that the collection names but does not hold.
PATIENT_REFERENCE = f"{LINKED_UID_ROOT}00003"
PROCEDURE_STEP = f"{LINKED_UID_ROOT}00004"
DETACHED_PATIENT_MANAGEMENT = "1.2.840.10008.3.1.2.1.1"
MODALITY_PERFORMED_PROCEDURE_STEP = "1.2.840.10008.3.1.2.3.3"
IMPLEMENTATION_CLASS = f"{LINKED_UID_ROOT}99999"
PATIENT_ID = f"{MARKER_PREFIX}-LINKED-PATIENT"
ISSUER_OF_PATIENT_ID = f"{MARKER_PREFIX}-LINKED-ISSUER"
PRIVATE_GROUP = 0x0009
# The sequence whose item holds the second private block: Procedure Code
# Sequence, which every IOD of the corpus defines and pydicom 3.0 knows.
PRIVATE_ITEM_SEQUENCE = "(0008,1032)"

_SOP_INSTANCE_TAG = "(0008,0018)"
_SERIES_TAG = "(0020,000E)"
_STUDY_TAG = "(0020,000D)"
_PATIENT_ID_TAG = "(0010,0020)"
_ISSUER_TAG = "(0010,0021)"
_PATIENTS_NAME_TAG = "(0010,0010)"
# Frame of Reference UID, Referenced Frame of Reference UID, and the Source
# Frame of Reference UID of a deformable registration.
_FRAME_OF_REFERENCE_TAGS = frozenset({"(0020,0052)", "(3006,0024)", "(0064,0003)"})
_CONTOUR_IMAGE_SEQUENCE = "(3006,0016)"
_CONTENT_SEQUENCE = "(0040,A730)"
# The frame of reference of a SCOORD3D content item's coordinates.
_REFERENCED_FRAME_OF_REFERENCE = "(3006,0024)"
# The instance that an IMAGE content item references or a COMPOSITE one names.
_REFERENCED_SOP = "(0008,1199)"
# The sequences of a Structured Report's root content item, its Concept Name
# Code Sequence and Content Sequence, which its template builds.
_CONTENT_TREE_ROOT = frozenset({"(0040,A043)", _CONTENT_SEQUENCE})
# The VR, and the attribute, of the value of each Value Type of a content
# item that can identify someone or something (PS3.3 Table 10-2).
_CONTENT_ITEM_VRS = types.MappingProxyType(
    {
        "UIDREF": "UI",
        "DATE": "DA",
        "TIME": "TM",
        "DATETIME": "DT",
        "PNAME": "PN",
        "TEXT": "UT",
    }
)
_CONTENT_ITEM_VALUES = types.MappingProxyType(
    {
        "UIDREF": "(0040,A124)",
        "DATE": "(0040,A121)",
        "TIME": "(0040,A122)",
        "DATETIME": "(0040,A120)",
        "PNAME": "(0040,A123)",
        "TEXT": "(0040,A160)",
    }
)
# The collection's own UIDs that a content tree's UIDREF items can name, and
# that are then recorded as linked.
_COLLECTION_UIDS = frozenset({STUDY, FRAME_OF_REFERENCE, CT_SERIES})
# The sequences whose D a reviewed rule writes (D-021), Institution Code
# Sequence's only where reviewed_within says.
_REVIEWED_DUMMY_SEQUENCES = frozenset(
    {
        INSTITUTION_CODE_SEQUENCE,
        PERSON_IDENTIFICATION_CODE_SEQUENCE,
        REFERENCED_PERFORMED_PROCEDURE_STEP_SEQUENCE,
        VERIFYING_OBSERVER_SEQUENCE,
    }
)
# Where an RT Structure Set references every CT slice, not only the first.
_RT_REFERENCED_CONTOUR_IMAGES = ("(3006,0010)", "(3006,0012)", "(3006,0014)")
_REFERENCED_RT_PLAN_SEQUENCE = "(300C,0002)"
_RT_RADIATION_SEQUENCE = "(300A,0616)"
_REFERENCED_RT_RADIATION_SEQUENCE = "(300A,0630)"
_REFERENCED_TREATMENT_RECORD_SEQUENCE = "(3008,0030)"
_RELATED_REFERENCE_RT_IMAGE_SEQUENCE = "(0074,1040)"
# The instance a reference names, by the innermost sequence that holds it.
_TARGETS = types.MappingProxyType(
    {
        _REFERENCED_RT_PLAN_SEQUENCE: PLAN,
        "(300C,0060)": STRUCTURE_SET,  # Referenced Structure Set Sequence
        "(300C,0080)": DOSE,  # Referenced Dose Sequence
        "(0070,0315)": STRUCTURE_SET,  # Used RT Structure Set ROI Sequence
        _CONTOUR_IMAGE_SEQUENCE: CT_SLICES[0],
        "(0008,1120)": PATIENT_REFERENCE,  # Referenced Patient Sequence
        "(0008,1111)": PROCEDURE_STEP,  # Referenced Performed Procedure Step
    }
)
# The RT Radiation Set and the radiations, whose Modality PS3.3 Sections
# A.86.1.4.4.1 to A.86.1.7.4.1 make RTRAD.
_RADIATIONS = frozenset(
    {
        RT_RADIATION_SET_STORAGE,
        C_ARM_PHOTON_ELECTRON_RADIATION_STORAGE,
        TOMOTHERAPEUTIC_RADIATION_STORAGE,
        ROBOTIC_ARM_RADIATION_STORAGE,
    }
)
_SOP_CLASSES = types.MappingProxyType(
    {
        **dict.fromkeys(CT_SLICES, CT_IMAGE_STORAGE),
        STRUCTURE_SET: RT_STRUCTURE_SET_STORAGE,
        PLAN: RT_PLAN_STORAGE,
        DOSE: RT_DOSE_STORAGE,
        REVIEW_DOSE: RT_DOSE_STORAGE,
        ENHANCED_CT: ENHANCED_CT_IMAGE_STORAGE,
        LEGACY_CT: LEGACY_CONVERTED_ENHANCED_CT_IMAGE_STORAGE,
        MR: MR_IMAGE_STORAGE,
        ENHANCED_MR: ENHANCED_MR_IMAGE_STORAGE,
        MR_COLOR: ENHANCED_MR_COLOR_IMAGE_STORAGE,
        LEGACY_MR: LEGACY_CONVERTED_ENHANCED_MR_IMAGE_STORAGE,
        SPECTROSCOPY: MR_SPECTROSCOPY_STORAGE,
        PET: PET_IMAGE_STORAGE,
        ENHANCED_PET: ENHANCED_PET_IMAGE_STORAGE,
        LEGACY_PET: LEGACY_CONVERTED_ENHANCED_PET_IMAGE_STORAGE,
        REGISTRATION: SPATIAL_REGISTRATION_STORAGE,
        DEFORMABLE_REGISTRATION: DEFORMABLE_SPATIAL_REGISTRATION_STORAGE,
        TREATMENT_RECORD: RT_BEAMS_TREATMENT_RECORD_STORAGE,
        RT_IMAGE: RT_IMAGE_STORAGE,
        X_RAY_DOSE_REPORT: X_RAY_RADIATION_DOSE_SR_STORAGE,
        RADIOPHARMACEUTICAL_DOSE_REPORT: RADIOPHARMACEUTICAL_RADIATION_DOSE_SR_STORAGE,
        BASIC_TEXT_REPORT: BASIC_TEXT_SR_STORAGE,
        ENHANCED_REPORT: ENHANCED_SR_STORAGE,
        COMPREHENSIVE_REPORT: COMPREHENSIVE_SR_STORAGE,
        COMPREHENSIVE_3D_REPORT: COMPREHENSIVE_3D_SR_STORAGE,
        EXTENSIBLE_REPORT: EXTENSIBLE_SR_STORAGE,
        ENHANCED_X_RAY_DOSE_REPORT: ENHANCED_X_RAY_RADIATION_DOSE_SR_STORAGE,
        PATIENT_DOSE_REPORT: PATIENT_RADIATION_DOSE_SR_STORAGE,
        CT_DOSE_REPORT: X_RAY_RADIATION_DOSE_SR_STORAGE,
        SEGMENTATION: SEGMENTATION_STORAGE,
        LABEL_MAP_SEGMENTATION: LABEL_MAP_SEGMENTATION_STORAGE,
        KEY_OBJECT_SELECTION: KEY_OBJECT_SELECTION_DOCUMENT_STORAGE,
        MAMMOGRAPHY_CAD_REPORT: MAMMOGRAPHY_CAD_SR_STORAGE,
        CHEST_CAD_REPORT: CHEST_CAD_SR_STORAGE,
        COLON_CAD_REPORT: COLON_CAD_SR_STORAGE,
        PROCEDURE_LOG: PROCEDURE_LOG_STORAGE,
        SPECTACLE_PRESCRIPTION: SPECTACLE_PRESCRIPTION_REPORT_STORAGE,
        MACULAR_GRID_REPORT: MACULAR_GRID_THICKNESS_AND_VOLUME_REPORT_STORAGE,
        WAVEFORM_ANNOTATION: WAVEFORM_ANNOTATION_SR_STORAGE,
        ION_PLAN: RT_ION_PLAN_STORAGE,
        ION_TREATMENT_RECORD: RT_ION_BEAMS_TREATMENT_RECORD_STORAGE,
        BRACHY_TREATMENT_RECORD: RT_BRACHY_TREATMENT_RECORD_STORAGE,
        TREATMENT_SUMMARY_RECORD: RT_TREATMENT_SUMMARY_RECORD_STORAGE,
        PARAMETRIC_MAP: PARAMETRIC_MAP_STORAGE,
        REAL_WORLD_VALUE_MAPPING: REAL_WORLD_VALUE_MAPPING_STORAGE,
        ENCAPSULATED_PDF: ENCAPSULATED_PDF_STORAGE,
        SURFACE_SEGMENTATION: SURFACE_SEGMENTATION_STORAGE,
        ENHANCED_RT_IMAGE: ENHANCED_RT_IMAGE_STORAGE,
        ENHANCED_CONTINUOUS_RT_IMAGE: ENHANCED_CONTINUOUS_RT_IMAGE_STORAGE,
        GRAYSCALE_PRESENTATION_STATE: GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        COLOR_PRESENTATION_STATE: COLOR_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        PSEUDO_COLOR_PRESENTATION_STATE: (
            PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE_STORAGE
        ),
        BLENDING_PRESENTATION_STATE: BLENDING_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        XA_XRF_PRESENTATION_STATE: (
            XA_XRF_GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE
        ),
        VARIABLE_MODALITY_LUT_PRESENTATION_STATE: (
            VARIABLE_MODALITY_LUT_SOFTCOPY_PRESENTATION_STATE_STORAGE
        ),
        SEGMENT_ANNOTATION: RT_SEGMENT_ANNOTATION_STORAGE,
        RADIATION_SET: RT_RADIATION_SET_STORAGE,
        C_ARM_RADIATION: C_ARM_PHOTON_ELECTRON_RADIATION_STORAGE,
        TOMOTHERAPEUTIC_RADIATION: TOMOTHERAPEUTIC_RADIATION_STORAGE,
        ROBOTIC_ARM_RADIATION: ROBOTIC_ARM_RADIATION_STORAGE,
        BEAMS_DELIVERY_INSTRUCTION: RT_BEAMS_DELIVERY_INSTRUCTION_STORAGE,
        BRACHY_DELIVERY_INSTRUCTION: (
            RT_BRACHY_APPLICATION_SETUP_DELIVERY_INSTRUCTION_STORAGE
        ),
        RADIATION_SET_DELIVERY_INSTRUCTION: (
            RT_RADIATION_SET_DELIVERY_INSTRUCTION_STORAGE
        ),
        PATIENT_REFERENCE: DETACHED_PATIENT_MANAGEMENT,
        PROCEDURE_STEP: MODALITY_PERFORMED_PROCEDURE_STEP,
    }
)
# The units of the Parametric Map's apparent diffusion coefficients and of
# the Real World Value Mapping's standardised uptake values, as UCUM codes
# from PS3.16 CID 7181 and CID 85, with each code's meaning and the LUT
# Explanation (0028,3003) of the mapping.
_APPARENT_DIFFUSION = ("um2/s", "um2/s", "ADC")
_SUV_BODY_WEIGHT = ("{SUVbw}g/ml", "Standardized Uptake Value body weight", "SUVbw")
# The registrations, whose structure _add_registration adds.
_REGISTRATIONS = frozenset(
    {SPATIAL_REGISTRATION_STORAGE, DEFORMABLE_SPATIAL_REGISTRATION_STORAGE}
)
# The Segmentations, whose structure _add_segmentation adds.
_SEGMENTATIONS = frozenset({SEGMENTATION_STORAGE, LABEL_MAP_SEGMENTATION_STORAGE})
# The VR given to an attribute with alternatives, as Implicit VR gives it
# (PS3.5 Section A.1).
_DECIDED_VRS = types.MappingProxyType({"(60xx,3000)": "OW"})
# A registration's Frame of Reference Transformation Matrix that leaves the
# registered frame unchanged.
_IDENTITY_MATRIX = [
    "1", "0", "0", "0",
    "0", "1", "0", "0",
    "0", "0", "1", "0",
    "0", "0", "0", "1",
]  # fmt: skip
# The text VRs, which a sequence's content marker has where it can.
_CONTENT_VRS = frozenset({"LO", "LT", "PN", "SH", "ST", "UC", "UT"})
_WORD_BYTES = {"OB": 1, "UN": 1, "OW": 2, "OF": 4, "OL": 4, "OD": 8, "OV": 8}
# Every value has an even length (PS3.5 Section 7.1.1).
_EVEN = 2
# The fractional seconds of every TM marker, so that times are conspicuous.
_TIME_SIGNATURE = ".424242"
# The time of every DT marker, which no TM marker matches.
_NOON = "120000"
_FIRST_DATE = datetime.date(900, 1, 1)
# Dates come in runs of consecutive days, each run the same number of days
# after the one before it, so that no two date markers are 364 to 3,640 days
# apart: the range of the Retain Longitudinal Temporal Information Modified
# Dates Option's backward shift of 52 to 520 whole weeks
# (pymedphys._dicom.deidentify.dates). A shifted date then never equals
# another marker's date, which the residual search would find.
_DATE_RUN_DAYS = 363
_DATE_RUN_PERIOD = 4004
_SECONDS_IN_A_DAY = 86_400
# The kinds of marker numbered apart from the others, by VR, and how many of
# each the corpus can hold: dates and datetimes, which share their days, up
# to the last before 1900 (_marker_date); times, up to the last second of a
# day; and VR SS, whose markers are negated, and US, up to the limits of
# their 16 bits.
_NUMBERED_APART = types.MappingProxyType(
    {"DA": "date", "DT": "date", "TM": "time", "SS": "SS", "US": "US"}
)
_KIND_LIMITS = types.MappingProxyType(
    {"date": 2**15 - 1, "time": _SECONDS_IN_A_DAY - 1, "SS": 2**15, "US": 2**16 - 1}
)


class PlacementKind(enum.Enum):
    """What a :class:`Placement` holds.

    Attributes
    ----------
    PLANTED
        A marker that no other placement holds, in an attribute of Table
        E.1-1, or in the value of a content item whose concept name is a
        row of Table E.3.4-1.
    LINKED_UID
        One of the collection's own UIDs, which other placements share so
        that identities and references stay linked: an instance's SOP
        Instance, Series Instance, or Study Instance UID at the top level,
        the Frame of Reference UID, or a UID at a reference site.
    LINKED_PATIENT
        The patient's Patient ID or Issuer of Patient ID at the top level,
        the same in every file, so the study has one patient.
    SEQUENCE
        A sequence of Table E.1-1, present with the item that holds the
        markers below it. It has no values of its own.
    CONTENT
        A marker in an attribute that Table E.1-1 does not list, in the item
        of a sequence that it does and that holds no other marker.
    PRIVATE
        A private creator or private attribute of the synthetic private
        block, which Table E.1-1 covers by its row for private attributes.
    UN_ENCODED
        A marker in an attribute of Table E.1-1 written with VR UN in
        Explicit VR, in place of its own VR.
    NOT_PLANTED
        An attribute of Table E.1-1 that the IOD defines there but that is
        not planted, for the placement's ``reason``.
    INVALID
        A value of a UI attribute of Table E.1-1, ``2.25.`` followed by a
        text marker, which VR UI does not allow, so that pydicom warns,
        quoting it, when it converts it.
    REVIEW_COPY
        A copy of another file's marker, whose values equal that
        placement's, in an attribute that Table E.1-1 does not list and the
        Basic Profile keeps, so that the residual search finds it and sends
        the file to review.
    """

    PLANTED = "planted"
    LINKED_UID = "linked-uid"
    LINKED_PATIENT = "linked-patient"
    SEQUENCE = "sequence"
    CONTENT = "content"
    PRIVATE = "private"
    UN_ENCODED = "un-encoded"
    NOT_PLANTED = "not-planted"
    INVALID = "invalid"
    REVIEW_COPY = "review-copy"


# The kinds of placement that leave a marker below a sequence.
_MARKER_KINDS = frozenset({PlacementKind.PLANTED, PlacementKind.CONTENT})


class NotPlantedReason(enum.Enum):
    """Why an attribute of Table E.1-1 that the IOD defines is not planted."""

    DEPTH_CAP = "depth-cap"  # deeper than MAX_DEPTH items
    # A sequence whose item the IOD gives no attribute that can carry a
    # marker; the sequence itself is present.
    NO_MARKER_CARRIER = "no-marker-carrier"
    NO_SINGLE_VR = "no-single-vr"  # the pinned dictionary gives no single VR
    MASKED_ELEMENT = "masked-element"  # its element number is masked
    # Removing it sequesters the instance, so it is planted only in
    # SEQUESTERED_FILE.
    SEQUESTERS_INSTANCE = "sequesters-instance"
    # A sequence that the Basic Profile keeps, replacing only its UIDs, so
    # that a marker in its item would be kept; the sequence itself is
    # present.
    KEPT_SEQUENCE = "kept-sequence"
    # A sequence of a Structured Report's root content item, its Concept
    # Name Code Sequence or the Content Sequence that holds its content tree,
    # which a template (synthetic_content_trees) builds rather than the
    # markers, and each attribute that the IOD defines below the first.
    CONTENT_TREE = "content-tree"


@dataclasses.dataclass(frozen=True)
class Placement:
    """One place in a file where a marker is, or would have been, planted.

    Attributes
    ----------
    path : ElementPath
        The sequences and items that hold the element, outermost first, and
        its tag, with a repeating group's first group, such as
        ``(6000,3000)``.
    vr : str
        The VR the element is built with, which an Implicit VR file does not
        hold; ``"UN"`` for :attr:`PlacementKind.UN_ENCODED`; or ``""`` where
        it is not planted for want of one.
    values : tuple of str
        The values as text: numbers in decimal, a tag as eight hexadecimal
        digits, and a binary value as the ASCII text it holds, which is
        padded to an even whole number of words with NUL, or with a space
        for UN.
        ``()`` for a sequence and for an attribute not planted.
    kind : PlacementKind
    profile_tag : str
        The tag of the row of Table E.1-1 that the placement covers, such as
        ``"(60xx,3000)"``, or its row for private attributes; ``""`` for
        :attr:`PlacementKind.CONTENT` and :attr:`PlacementKind.REVIEW_COPY`.
        The value of a content item names the attribute that holds it, such
        as DateTime (0040,A120), or Text Value (0040,A160), which Table
        E.1-1 does not list; its ``concept`` gives the row that covers it.
    reason : NotPlantedReason or None
        Why it is not planted, for :attr:`PlacementKind.NOT_PLANTED`; or,
        for a :attr:`PlacementKind.SEQUENCE` in whose item no marker is
        planted for it, :attr:`NotPlantedReason.NO_MARKER_CARRIER`,
        :attr:`NotPlantedReason.KEPT_SEQUENCE`, or
        :attr:`NotPlantedReason.CONTENT_TREE`; otherwise ``None``.
    concept : tuple of str or None
        For the value of a content item of a Structured Report's content
        tree, the item's concept name, as the key of its row of PS3.15
        Table E.3.4-1 would be: its Coding Scheme Designator, Code Value,
        and Value Type, such as ``("DCM", "111526", "DATETIME")``, since
        Clean Structured Content gives the value the action of that row
        rather than the attribute's (D-047); otherwise ``None``.
    """

    path: ElementPath
    vr: str
    values: tuple[str, ...]
    kind: PlacementKind
    profile_tag: str
    reason: NotPlantedReason | None = None
    concept: tuple[str, str, str] | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the placement as JSON-ready data."""
        return {
            "items": [[tag, index] for tag, index in self.path.items],
            "tag": self.path.tag,
            "vr": self.vr,
            "values": list(self.values),
            "kind": self.kind.value,
            "profile_tag": self.profile_tag,
            "reason": None if self.reason is None else self.reason.value,
            "concept": None if self.concept is None else list(self.concept),
        }


@dataclasses.dataclass(frozen=True)
class FileManifest:
    """What one file of the corpus holds, and where.

    Attributes
    ----------
    name : str
        The file's name, such as ``"01-ct-1.dcm"``.
    iod : str
        The name of its IOD, such as ``"CT Image"``.
    sop_class : str
    sop_instance : str
    transfer_syntax : str
        Implicit or Explicit VR Little Endian.
    specific_character_set : str
        The Specific Character Set (0008,0005) it declares, or ``""``.
    placements : tuple of Placement
        Those of the IOD's attributes of Table E.1-1 in the order of its
        definitions, then the content markers of sequences, the extra
        references, the private block, any review copy, and a Structured
        Report's content items, in the order of its content tree.
    """

    name: str
    iod: str
    sop_class: str
    sop_instance: str
    transfer_syntax: str
    specific_character_set: str
    placements: tuple[Placement, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the file's manifest as JSON-ready data."""
        return {
            "name": self.name,
            "iod": self.iod,
            "sop_class": self.sop_class,
            "sop_instance": self.sop_instance,
            "transfer_syntax": self.transfer_syntax,
            "specific_character_set": self.specific_character_set,
            "placements": [placement.to_dict() for placement in self.placements],
        }


@dataclasses.dataclass(frozen=True)
class CorpusManifest:
    """The manifest of every file of the corpus.

    Attributes
    ----------
    files : tuple of FileManifest
        In the order the files are built.
    max_depth : int
        :data:`MAX_DEPTH` when the corpus was built.
    """

    files: tuple[FileManifest, ...]
    max_depth: int = MAX_DEPTH

    def to_json(self) -> str:
        """Return the manifest as JSON text, the same for the same manifest."""
        document = {
            "schema": "pymedphys-deid-synthetic-corpus/2",
            "max_depth": self.max_depth,
            "files": [file.to_dict() for file in self.files],
        }
        return json.dumps(document, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


@dataclasses.dataclass(frozen=True)
class CorpusFile:
    """One written file of the corpus. Its ``repr`` shows only its manifest."""

    manifest: FileManifest
    data: bytes = dataclasses.field(repr=False)

    @property
    def name(self) -> str:
        """The file's name."""
        return self.manifest.name


@dataclasses.dataclass(frozen=True)
class SyntheticCorpus:
    """The corpus's files, in the order they are built."""

    files: tuple[CorpusFile, ...]

    @property
    def manifest(self) -> CorpusManifest:
        """The manifest of every file."""
        return CorpusManifest(tuple(file.manifest for file in self.files))


@dataclasses.dataclass(frozen=True)
class _Image:
    """The image of an instance other than a CT slice or an RT Dose."""

    modality: str
    # Its Number of Frames, or 0 for a single-frame IOD, which has none.
    frames: int = 0
    colour: bool = False


_IMAGES = types.MappingProxyType(
    {
        ENHANCED_CT_IMAGE_STORAGE: _Image("CT", 2),
        LEGACY_CONVERTED_ENHANCED_CT_IMAGE_STORAGE: _Image("CT", 2),
        MR_IMAGE_STORAGE: _Image("MR"),
        ENHANCED_MR_IMAGE_STORAGE: _Image("MR", 2),
        ENHANCED_MR_COLOR_IMAGE_STORAGE: _Image("MR", 2, colour=True),
        LEGACY_CONVERTED_ENHANCED_MR_IMAGE_STORAGE: _Image("MR", 2),
        PET_IMAGE_STORAGE: _Image("PT"),
        ENHANCED_PET_IMAGE_STORAGE: _Image("PT", 2),
        LEGACY_CONVERTED_ENHANCED_PET_IMAGE_STORAGE: _Image("PT", 2),
    }
)
# The text of the Enhanced MR Color instance's ICC profile, which D cleans
# away, so that the search for the markers' signatures finds it if kept.
SOURCE_ICC_DESCRIPTION = f"{MARKER_PREFIX} SOURCE ICC PROFILE"
# The Enhanced MR Color instance's ICC profile: the sRGB colorimetry, with
# the text above in its text tags and in a private tag, each tag's different
# so that none shares another's data.
SOURCE_ICC_PROFILE = icc_profiles.assemble(
    icc_profiles.SRGB_HEADER,
    [
        (signature, data)
        for signature, data in icc_profiles.srgb_tags(SOURCE_ICC_DESCRIPTION)
        if signature != b"cprt"
    ]
    + [
        (b"cprt", icc_profiles.text_type(f"{SOURCE_ICC_DESCRIPTION} COPYRIGHT")),
        (b"dmnd", icc_profiles.text_description(f"{SOURCE_ICC_DESCRIPTION} MAKER")),
        (b"dmdd", icc_profiles.text_description(f"{SOURCE_ICC_DESCRIPTION} MODEL")),
        (b"SYNM", icc_profiles.text_type(f"{SOURCE_ICC_DESCRIPTION} PRIVATE")),
    ],
)


@dataclasses.dataclass(frozen=True)
class _Spec:
    """An instance of the corpus, before its markers are planted."""

    name: str
    sop_class: str
    sop_instance: str
    series: str
    # The instance that a reference names where _TARGETS does not decide.
    default_target: str
    transfer_syntax: str = EXPLICIT_VR_LITTLE_ENDIAN
    character_set: str = ""
    # The tag of a top-level attribute written with VR UN.
    un_encoded: str = ""
    # The tag of a top-level UI attribute whose marker is invalid for VR UI.
    invalid: str = ""
    # The tag of a top-level attribute that keeps a copy of a marker, the
    # file that holds the marker, and the tag of its top-level attribute.
    review_copy: tuple[str, str, str] | None = None
    slice_index: int = 0
    # The root template of a Structured Report's tree, where it is not the
    # one that ROOT_TEMPLATES gives its SOP Class.
    template: str = ""
    # The instance that a reference names, by the innermost sequence that
    # holds it, where it differs from _TARGETS.
    targets: tuple[tuple[str, str], ...] = ()
    # The series that a reference names by its Series Instance UID, which
    # holds the instance that the reference names within it.
    referenced_series: str = CT_SERIES


_SPECS = (
    _Spec(
        "01-ct-1.dcm",
        CT_IMAGE_STORAGE,
        CT_SLICES[0],
        CT_SERIES,
        CT_SLICES[1],
        un_encoded="(0010,4000)",  # Patient Comments
        slice_index=0,
    ),
    _Spec(
        "02-ct-2.dcm",
        CT_IMAGE_STORAGE,
        CT_SLICES[1],
        CT_SERIES,
        CT_SLICES[2],
        slice_index=1,
    ),
    _Spec(
        "03-ct-3.dcm",
        CT_IMAGE_STORAGE,
        CT_SLICES[2],
        CT_SERIES,
        CT_SLICES[0],
        slice_index=2,
    ),
    _Spec(
        "04-rtstruct.dcm",
        RT_STRUCTURE_SET_STORAGE,
        STRUCTURE_SET,
        STRUCTURE_SET_SERIES,
        CT_SLICES[0],
        character_set="ISO_IR 100",
    ),
    _Spec(
        "05-rtplan.dcm",
        RT_PLAN_STORAGE,
        PLAN,
        PLAN_SERIES,
        STRUCTURE_SET,
        invalid="(0018,1002)",  # Device UID
    ),
    _Spec(
        "06-rtdose.dcm",
        RT_DOSE_STORAGE,
        DOSE,
        DOSE_SERIES,
        PLAN,
        transfer_syntax=IMPLICIT_VR_LITTLE_ENDIAN,
    ),
    _Spec(
        REVIEW_FILE,
        RT_DOSE_STORAGE,
        REVIEW_DOSE,
        DOSE_SERIES,
        PLAN,
        # Manufacturer's Model Name keeps the plan's RT Plan Label.
        review_copy=("(0008,1090)", "05-rtplan.dcm", "(300A,0002)"),
    ),
    # The MR and PET Images reference the first CT slice, and each enhanced,
    # legacy converted enhanced, or MR Spectroscopy instance the
    # single-frame instance of its modality.
    _Spec(
        "08-ct-enhanced.dcm",
        ENHANCED_CT_IMAGE_STORAGE,
        ENHANCED_CT,
        ENHANCED_CT_SERIES,
        CT_SLICES[0],
    ),
    _Spec(
        "09-ct-legacy-enhanced.dcm",
        LEGACY_CONVERTED_ENHANCED_CT_IMAGE_STORAGE,
        LEGACY_CT,
        LEGACY_CT_SERIES,
        CT_SLICES[0],
    ),
    _Spec(
        "10-mr.dcm",
        MR_IMAGE_STORAGE,
        MR,
        MR_SERIES,
        CT_SLICES[0],
        transfer_syntax=IMPLICIT_VR_LITTLE_ENDIAN,
    ),
    _Spec(
        "11-mr-enhanced.dcm",
        ENHANCED_MR_IMAGE_STORAGE,
        ENHANCED_MR,
        ENHANCED_MR_SERIES,
        MR,
    ),
    _Spec(
        "12-mr-enhanced-color.dcm",
        ENHANCED_MR_COLOR_IMAGE_STORAGE,
        MR_COLOR,
        MR_COLOR_SERIES,
        MR,
    ),
    _Spec(
        "13-mr-legacy-enhanced.dcm",
        LEGACY_CONVERTED_ENHANCED_MR_IMAGE_STORAGE,
        LEGACY_MR,
        LEGACY_MR_SERIES,
        MR,
    ),
    _Spec(
        "14-mr-spectroscopy.dcm",
        MR_SPECTROSCOPY_STORAGE,
        SPECTROSCOPY,
        SPECTROSCOPY_SERIES,
        MR,
    ),
    _Spec(
        "15-pet.dcm",
        PET_IMAGE_STORAGE,
        PET,
        PET_SERIES,
        CT_SLICES[0],
    ),
    _Spec(
        "16-pet-enhanced.dcm",
        ENHANCED_PET_IMAGE_STORAGE,
        ENHANCED_PET,
        ENHANCED_PET_SERIES,
        PET,
    ),
    _Spec(
        "17-pet-legacy-enhanced.dcm",
        LEGACY_CONVERTED_ENHANCED_PET_IMAGE_STORAGE,
        LEGACY_PET,
        LEGACY_PET_SERIES,
        PET,
    ),
    # The spatial registration registers the MR Image, and the deformable
    # registration the PET Image, to the collection's one Frame of Reference.
    _Spec(
        "18-registration.dcm",
        SPATIAL_REGISTRATION_STORAGE,
        REGISTRATION,
        REGISTRATION_SERIES,
        MR,
    ),
    _Spec(
        "19-registration-deformable.dcm",
        DEFORMABLE_SPATIAL_REGISTRATION_STORAGE,
        DEFORMABLE_REGISTRATION,
        DEFORMABLE_REGISTRATION_SERIES,
        PET,
    ),
    # The treatment record references the plan it records.
    _Spec(
        "20-rt-beams-record.dcm",
        RT_BEAMS_TREATMENT_RECORD_STORAGE,
        TREATMENT_RECORD,
        TREATMENT_RECORD_SERIES,
        PLAN,
    ),
    # The RT Image, a digitally reconstructed radiograph of a beam of the plan.
    _Spec(
        "21-rt-image.dcm",
        RT_IMAGE_STORAGE,
        RT_IMAGE,
        RT_IMAGE_SERIES,
        PLAN,
    ),
    # The radiation dose reports, whose header references the first CT
    # slice, and the PET Image.
    _Spec(
        DOSE_REPORT_FILES[0],
        X_RAY_RADIATION_DOSE_SR_STORAGE,
        X_RAY_DOSE_REPORT,
        X_RAY_DOSE_REPORT_SERIES,
        CT_SLICES[0],
    ),
    _Spec(
        DOSE_REPORT_FILES[1],
        RADIOPHARMACEUTICAL_RADIATION_DOSE_SR_STORAGE,
        RADIOPHARMACEUTICAL_DOSE_REPORT,
        RADIOPHARMACEUTICAL_DOSE_REPORT_SERIES,
        PET,
    ),
    # The general Structured Reports, whose header references the MR Image:
    # imaging reports of TID 2000 in the IODs that allow no spatial
    # coordinates in three dimensions, and measurement reports of TID 1500
    # in those that do.
    *(
        _Spec(name, sop_class, instance, series, MR)
        for name, sop_class, instance, series in (
            (
                GENERAL_REPORT_FILES[0],
                BASIC_TEXT_SR_STORAGE,
                BASIC_TEXT_REPORT,
                BASIC_TEXT_REPORT_SERIES,
            ),
            (
                GENERAL_REPORT_FILES[1],
                ENHANCED_SR_STORAGE,
                ENHANCED_REPORT,
                ENHANCED_REPORT_SERIES,
            ),
            (
                GENERAL_REPORT_FILES[2],
                COMPREHENSIVE_SR_STORAGE,
                COMPREHENSIVE_REPORT,
                COMPREHENSIVE_REPORT_SERIES,
            ),
            (
                GENERAL_REPORT_FILES[3],
                COMPREHENSIVE_3D_SR_STORAGE,
                COMPREHENSIVE_3D_REPORT,
                COMPREHENSIVE_3D_REPORT_SERIES,
            ),
            (
                GENERAL_REPORT_FILES[4],
                EXTENSIBLE_SR_STORAGE,
                EXTENSIBLE_REPORT,
                EXTENSIBLE_REPORT_SERIES,
            ),
        )
    ),
    # The other radiation dose reports: an Enhanced X-Ray Radiation Dose SR,
    # whose header references the first CT slice; a Patient Radiation Dose
    # SR, whose estimate used the CT dose report, which its header
    # references too; and the CT dose report, an X-Ray Radiation Dose SR
    # whose header references the first CT slice.
    _Spec(
        DOSE_REPORT_FILES[2],
        ENHANCED_X_RAY_RADIATION_DOSE_SR_STORAGE,
        ENHANCED_X_RAY_DOSE_REPORT,
        ENHANCED_X_RAY_DOSE_REPORT_SERIES,
        CT_SLICES[0],
    ),
    _Spec(
        DOSE_REPORT_FILES[3],
        PATIENT_RADIATION_DOSE_SR_STORAGE,
        PATIENT_DOSE_REPORT,
        PATIENT_DOSE_REPORT_SERIES,
        CT_DOSE_REPORT,
    ),
    _Spec(
        CT_DOSE_REPORT_FILE,
        X_RAY_RADIATION_DOSE_SR_STORAGE,
        CT_DOSE_REPORT,
        CT_DOSE_REPORT_SERIES,
        CT_SLICES[0],
        template=CT_RADIATION_DOSE_TEMPLATE,
    ),
    # The Segmentations, each of a segment in the first two CT slices'
    # planes, which reference the CT series and its first slice.
    _Spec(
        SEGMENTATION_FILES[0],
        SEGMENTATION_STORAGE,
        SEGMENTATION,
        SEGMENTATION_SERIES,
        CT_SLICES[0],
    ),
    _Spec(
        SEGMENTATION_FILES[1],
        LABEL_MAP_SEGMENTATION_STORAGE,
        LABEL_MAP_SEGMENTATION,
        LABEL_MAP_SEGMENTATION_SERIES,
        CT_SLICES[0],
    ),
    # The documents of the IODs that each name their root template. The Key
    # Object Selection Document selects the MR Image; the mammography and
    # chest CAD reports name the RT Image, the collection's one projection
    # radiograph, as the image that they were computed on, and the colon
    # CAD report the CT series; the others reference the MR Image, as the
    # general reports do.
    *(
        _Spec(name, sop_class, instance, series, target)
        for name, sop_class, instance, series, target in (
            (
                TEMPLATE_REPORT_FILES[0],
                KEY_OBJECT_SELECTION_DOCUMENT_STORAGE,
                KEY_OBJECT_SELECTION,
                KEY_OBJECT_SELECTION_SERIES,
                MR,
            ),
            (
                TEMPLATE_REPORT_FILES[1],
                MAMMOGRAPHY_CAD_SR_STORAGE,
                MAMMOGRAPHY_CAD_REPORT,
                MAMMOGRAPHY_CAD_REPORT_SERIES,
                RT_IMAGE,
            ),
            (
                TEMPLATE_REPORT_FILES[2],
                CHEST_CAD_SR_STORAGE,
                CHEST_CAD_REPORT,
                CHEST_CAD_REPORT_SERIES,
                RT_IMAGE,
            ),
            (
                TEMPLATE_REPORT_FILES[3],
                COLON_CAD_SR_STORAGE,
                COLON_CAD_REPORT,
                COLON_CAD_REPORT_SERIES,
                CT_SLICES[0],
            ),
            (
                TEMPLATE_REPORT_FILES[4],
                PROCEDURE_LOG_STORAGE,
                PROCEDURE_LOG,
                PROCEDURE_LOG_SERIES,
                MR,
            ),
            (
                TEMPLATE_REPORT_FILES[5],
                SPECTACLE_PRESCRIPTION_REPORT_STORAGE,
                SPECTACLE_PRESCRIPTION,
                SPECTACLE_PRESCRIPTION_SERIES,
                MR,
            ),
            (
                TEMPLATE_REPORT_FILES[6],
                MACULAR_GRID_THICKNESS_AND_VOLUME_REPORT_STORAGE,
                MACULAR_GRID_REPORT,
                MACULAR_GRID_REPORT_SERIES,
                MR,
            ),
            (
                TEMPLATE_REPORT_FILES[7],
                WAVEFORM_ANNOTATION_SR_STORAGE,
                WAVEFORM_ANNOTATION,
                WAVEFORM_ANNOTATION_SERIES,
                MR,
            ),
        )
    ),
    # The RT Ion Plan references what the RT Plan does: the structure set,
    # the RT Dose, and the RT Plan, which it names as a related plan. The RT
    # Ion Beams Treatment Record references the RT Ion Plan, as the RT Beams
    # Treatment Record references the RT Plan.
    _Spec(
        ION_PLAN_FILE,
        RT_ION_PLAN_STORAGE,
        ION_PLAN,
        ION_PLAN_SERIES,
        STRUCTURE_SET,
    ),
    _Spec(
        ION_TREATMENT_RECORD_FILE,
        RT_ION_BEAMS_TREATMENT_RECORD_STORAGE,
        ION_TREATMENT_RECORD,
        ION_TREATMENT_RECORD_SERIES,
        ION_PLAN,
        targets=((_REFERENCED_RT_PLAN_SEQUENCE, ION_PLAN),),
    ),
    # The RT Brachy Treatment Record references the RT Plan, whose
    # application setups it records, as the RT Beams Treatment Record
    # references it for its beams, and names the RT Beams Treatment Record as
    # a related record, as a brachytherapy boost's record may name the
    # external beam record of the same course. The RT Treatment Summary Record
    # references the RT Plan and names the RT Brachy Treatment Record in its
    # Referenced Treatment Record Sequence, as a record of the course that it
    # sums.
    _Spec(
        BRACHY_TREATMENT_RECORD_FILE,
        RT_BRACHY_TREATMENT_RECORD_STORAGE,
        BRACHY_TREATMENT_RECORD,
        BRACHY_TREATMENT_RECORD_SERIES,
        PLAN,
        targets=((_REFERENCED_TREATMENT_RECORD_SEQUENCE, TREATMENT_RECORD),),
    ),
    _Spec(
        TREATMENT_SUMMARY_RECORD_FILE,
        RT_TREATMENT_SUMMARY_RECORD_STORAGE,
        TREATMENT_SUMMARY_RECORD,
        TREATMENT_SUMMARY_RECORD_SERIES,
        PLAN,
        targets=((_REFERENCED_TREATMENT_RECORD_SEQUENCE, BRACHY_TREATMENT_RECORD),),
    ),
    # The Parametric Map, an apparent diffusion coefficient map derived from
    # the MR Image, references it, and the Real World Value Mapping maps the
    # PET Image's stored values to a standardised uptake value, naming it in
    # its Referenced Image Sequence (0008,1140).
    _Spec(
        PARAMETRIC_MAP_FILE,
        PARAMETRIC_MAP_STORAGE,
        PARAMETRIC_MAP,
        PARAMETRIC_MAP_SERIES,
        MR,
    ),
    _Spec(
        REAL_WORLD_VALUE_MAPPING_FILE,
        REAL_WORLD_VALUE_MAPPING_STORAGE,
        REAL_WORLD_VALUE_MAPPING,
        REAL_WORLD_VALUE_MAPPING_SERIES,
        PET,
    ),
    # The Encapsulated PDF, a report of the RT Plan, names the plan as the
    # instance that it was derived from, in its Source Instance Sequence. It
    # holds no document: Encapsulated Document (0042,0011), which the Basic
    # Profile gives D and no reviewed rule a dummy value, would sequester it
    # (see Sequestering attributes), so its header's markers are checked.
    _Spec(
        ENCAPSULATED_PDF_FILE,
        ENCAPSULATED_PDF_STORAGE,
        ENCAPSULATED_PDF,
        ENCAPSULATED_PDF_SERIES,
        PLAN,
    ),
    # The Surface Segmentation, of a mesh in the CT slices' space, which
    # references the CT series and its first slice, from which its surface
    # was generated.
    _Spec(
        SURFACE_SEGMENTATION_FILE,
        SURFACE_SEGMENTATION_STORAGE,
        SURFACE_SEGMENTATION,
        SURFACE_SEGMENTATION_SERIES,
        CT_SLICES[0],
    ),
    # Each softcopy Presentation State names, in the Referenced Image
    # Sequence (0008,1140) of its Referenced Series Sequence (0008,1115), the
    # image that it presents: the grayscale and Variable Modality LUT ones
    # the first CT slice, the colour one the Enhanced MR Color Image, the
    # pseudo-colour one the PET Image, the blending one the first CT slice,
    # under the PET Image that its Blending Sequence (0070,0402) would
    # superimpose, and the XA/XRF one the RT Image, a projection radiograph.
    _Spec(
        GRAYSCALE_PRESENTATION_STATE_FILE,
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        GRAYSCALE_PRESENTATION_STATE,
        GRAYSCALE_PRESENTATION_STATE_SERIES,
        CT_SLICES[0],
    ),
    _Spec(
        COLOR_PRESENTATION_STATE_FILE,
        COLOR_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        COLOR_PRESENTATION_STATE,
        COLOR_PRESENTATION_STATE_SERIES,
        MR_COLOR,
    ),
    _Spec(
        PSEUDO_COLOR_PRESENTATION_STATE_FILE,
        PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        PSEUDO_COLOR_PRESENTATION_STATE,
        PSEUDO_COLOR_PRESENTATION_STATE_SERIES,
        PET,
    ),
    _Spec(
        BLENDING_PRESENTATION_STATE_FILE,
        BLENDING_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        BLENDING_PRESENTATION_STATE,
        BLENDING_PRESENTATION_STATE_SERIES,
        CT_SLICES[0],
    ),
    _Spec(
        XA_XRF_PRESENTATION_STATE_FILE,
        XA_XRF_GRAYSCALE_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        XA_XRF_PRESENTATION_STATE,
        XA_XRF_PRESENTATION_STATE_SERIES,
        RT_IMAGE,
    ),
    _Spec(
        VARIABLE_MODALITY_LUT_PRESENTATION_STATE_FILE,
        VARIABLE_MODALITY_LUT_SOFTCOPY_PRESENTATION_STATE_STORAGE,
        VARIABLE_MODALITY_LUT_PRESENTATION_STATE,
        VARIABLE_MODALITY_LUT_PRESENTATION_STATE_SERIES,
        CT_SLICES[0],
    ),
    # The RT Segment Annotation annotates the BINARY Segmentation's segments.
    # The RT Radiation Set gathers the C-Arm Photon-Electron Radiation, which
    # its RT Radiation Sequence and Referenced RT Radiation Sequences name;
    # each radiation names the structure set as the source of its Conceptual
    # Volumes, as an RT Plan names the structure set that it was planned on.
    _Spec(
        SEGMENT_ANNOTATION_FILE,
        RT_SEGMENT_ANNOTATION_STORAGE,
        SEGMENT_ANNOTATION,
        SEGMENT_ANNOTATION_SERIES,
        SEGMENTATION,
    ),
    _Spec(
        RADIATION_SET_FILE,
        RT_RADIATION_SET_STORAGE,
        RADIATION_SET,
        RADIATION_SET_SERIES,
        STRUCTURE_SET,
        targets=(
            (_RT_RADIATION_SEQUENCE, C_ARM_RADIATION),
            (_REFERENCED_RT_RADIATION_SEQUENCE, C_ARM_RADIATION),
        ),
    ),
    *(
        _Spec(name, sop_class, instance, series, STRUCTURE_SET)
        for name, sop_class, instance, series in (
            (
                C_ARM_RADIATION_FILE,
                C_ARM_PHOTON_ELECTRON_RADIATION_STORAGE,
                C_ARM_RADIATION,
                C_ARM_RADIATION_SERIES,
            ),
            (
                TOMOTHERAPEUTIC_RADIATION_FILE,
                TOMOTHERAPEUTIC_RADIATION_STORAGE,
                TOMOTHERAPEUTIC_RADIATION,
                TOMOTHERAPEUTIC_RADIATION_SERIES,
            ),
            (
                ROBOTIC_ARM_RADIATION_FILE,
                ROBOTIC_ARM_RADIATION_STORAGE,
                ROBOTIC_ARM_RADIATION,
                ROBOTIC_ARM_RADIATION_SERIES,
            ),
        )
    ),
    # The RT Beams Delivery Instruction instructs the delivery of the RT
    # Plan's beams: it references the RT Plan, names the RT Beams Treatment
    # Record as the record of the session that it continues, and names the
    # RT Image as a reference image for the verification of its beams. The RT
    # Brachy Application Setup Delivery Instruction instructs the delivery of
    # the RT Plan's application setups, which it references in Referenced
    # SOP Sequence within the RT Plan's series.
    _Spec(
        BEAMS_DELIVERY_INSTRUCTION_FILE,
        RT_BEAMS_DELIVERY_INSTRUCTION_STORAGE,
        BEAMS_DELIVERY_INSTRUCTION,
        BEAMS_DELIVERY_INSTRUCTION_SERIES,
        PLAN,
        targets=(
            (_REFERENCED_TREATMENT_RECORD_SEQUENCE, TREATMENT_RECORD),
            (_RELATED_REFERENCE_RT_IMAGE_SEQUENCE, RT_IMAGE),
        ),
    ),
    _Spec(
        BRACHY_DELIVERY_INSTRUCTION_FILE,
        RT_BRACHY_APPLICATION_SETUP_DELIVERY_INSTRUCTION_STORAGE,
        BRACHY_DELIVERY_INSTRUCTION,
        BRACHY_DELIVERY_INSTRUCTION_SERIES,
        PLAN,
        referenced_series=PLAN_SERIES,
    ),
    # The RT Radiation Set Delivery Instruction instructs the delivery of the
    # RT Radiation Set's C-Arm Photon-Electron Radiation, which it names, as
    # the set does, in each task's and in its omitted radiations' Referenced
    # RT Radiation Sequence, and names the set itself elsewhere, including in
    # a task's Referenced RT Treatment Preparation Sequence, as the RT Beams
    # Treatment Record names the plan in its verification image references.
    _Spec(
        RADIATION_SET_DELIVERY_INSTRUCTION_FILE,
        RT_RADIATION_SET_DELIVERY_INSTRUCTION_STORAGE,
        RADIATION_SET_DELIVERY_INSTRUCTION,
        RADIATION_SET_DELIVERY_INSTRUCTION_SERIES,
        RADIATION_SET,
        targets=((_REFERENCED_RT_RADIATION_SEQUENCE, C_ARM_RADIATION),),
    ),
    # Numbered after the second-generation RT IODs' files.
    # The Enhanced RT Image, two digitally reconstructed radiographs of the
    # RT Plan's beam, and the Enhanced Continuous RT Image, two frames of a
    # kV acquisition during it, each referencing the RT Plan, as the RT Image
    # does.
    _Spec(
        ENHANCED_RT_IMAGE_FILE,
        ENHANCED_RT_IMAGE_STORAGE,
        ENHANCED_RT_IMAGE,
        ENHANCED_RT_IMAGE_SERIES,
        PLAN,
    ),
    _Spec(
        ENHANCED_CONTINUOUS_RT_IMAGE_FILE,
        ENHANCED_CONTINUOUS_RT_IMAGE_STORAGE,
        ENHANCED_CONTINUOUS_RT_IMAGE,
        ENHANCED_CONTINUOUS_RT_IMAGE_SERIES,
        PLAN,
    ),
)


def build_corpus() -> SyntheticCorpus:
    """Build the corpus's files and their manifest, the same way every time.

    Returns
    -------
    SyntheticCorpus
        Sixty-five files: three CT slices; the RT Structure Set, RT Plan, RT
        Dose, and the RT Dose for review; the Enhanced CT Image and Legacy
        Converted Enhanced CT Image; the MR Image, Enhanced MR Image,
        Enhanced MR Color Image, Legacy Converted Enhanced MR Image, and MR
        Spectroscopy; the PET Image, Enhanced PET Image, and Legacy
        Converted Enhanced PET Image; the Spatial Registration and
        Deformable Spatial Registration; the RT Beams Treatment Record; the
        RT Image; the X-Ray Radiation Dose SR and Radiopharmaceutical
        Radiation Dose SR; the Basic Text SR, Enhanced SR, Comprehensive SR,
        Comprehensive 3D SR, and Extensible SR; the Enhanced X-Ray Radiation
        Dose SR, the Patient Radiation Dose SR, and a second X-Ray Radiation
        Dose SR, of a CT scan; the Segmentation and label map Segmentation;
        the Key Object Selection Document, Mammography CAD SR, Chest CAD SR,
        Colon CAD SR, Procedure Log, Spectacle Prescription Report, Macular
        Grid Thickness and Volume Report, and Waveform Annotation SR; the RT
        Ion Plan and RT Ion Beams Treatment Record; the RT Brachy Treatment
        Record and RT Treatment Summary Record; the Parametric Map and Real
        World Value Mapping; the Encapsulated PDF; the Surface Segmentation;
        the Grayscale, Color, Pseudo-Color, Blending, XA/XRF Grayscale, and Variable Modality LUT
        Softcopy Presentation States; the RT Segment Annotation, RT
        Radiation Set, and C-Arm Photon-Electron, Tomotherapeutic, and
        Robotic-Arm Radiations; the RT Beams Delivery Instruction, RT Brachy
        Application Setup Delivery Instruction, and RT Radiation Set
        Delivery Instruction; and the Enhanced RT Image and Enhanced
        Continuous RT Image. Two builds give the same bytes and the same
        manifest.
    """
    markers = _Markers()
    files: list[CorpusFile] = []
    for spec in _SPECS:
        earlier = {file.name: file.manifest for file in files}
        dataset, manifest = _Instance(spec, markers, earlier).build()
        files.append(CorpusFile(manifest, _written(dataset, spec)))
    return SyntheticCorpus(tuple(files))


def write_corpus(
    corpus: SyntheticCorpus, directory: pathlib.Path
) -> tuple[pathlib.Path, ...]:
    """Write the corpus's files, and its manifest as ``manifest.json``.

    The files go in ``directory / INSTANCES_DIRECTORY``, created if needed,
    which holds nothing else, so it can be given to a run as its input; the
    manifest, which holds every marker, goes in ``directory``.

    Parameters
    ----------
    corpus : SyntheticCorpus
    directory : pathlib.Path
        An existing directory. No file in it is overwritten.

    Returns
    -------
    tuple of pathlib.Path
        The paths written, the files in order and then the manifest.

    Raises
    ------
    FileExistsError
        If a file to be written already exists, before anything is written.
    """
    instances = directory / INSTANCES_DIRECTORY
    paths = [instances / file.name for file in corpus.files]
    path = directory / "manifest.json"
    for each in (*paths, path):
        if each.exists():
            raise FileExistsError(f"{each.name} already exists in the directory")
    instances.mkdir(exist_ok=True)
    written = []
    for each, file in zip(paths, corpus.files):
        with open(each, "xb") as stream:
            stream.write(file.data)
        written.append(each)
    with open(path, "x", encoding="utf-8", newline="\n") as stream:
        stream.write(corpus.manifest.to_json())
    written.append(path)
    return tuple(written)


class _Markers:
    """Number the markers in the order they are planted, across the corpus.

    Every marker takes the next number, which its text, UID, and other
    values hold. A date or datetime, a time, and a value of VR SS or US also
    takes the next number of its own kind, which its value holds instead,
    since each of those has fewer values to give than the five digits.
    """

    def __init__(self) -> None:
        self._number = 0
        self._ages = 0
        self._kinds: collections.Counter[str] = collections.Counter()

    def values(
        self, vr: str, count: int, *, latin_1: bool = False
    ) -> tuple[list[object], tuple[str, ...]]:
        """Return ``count`` new markers for ``vr``, as values and as text."""
        values: list[object] = []
        for _ in range(count):
            self._number += 1
            if self._number >= MAX_MARKERS:
                raise ValueError("the corpus has more markers than their width")
            if vr == "AS":
                # Ages have only a thousand values of each unit.
                self._ages += 1
                if self._ages > 999:
                    raise ValueError("the corpus has more ages than weeks to give")
                values.append(f"{self._ages:03d}W")
                continue
            kind = _NUMBERED_APART.get(vr)
            own = self._number
            if kind is not None:
                self._kinds[kind] += 1
                own = self._kinds[kind]
                if own > _KIND_LIMITS[kind]:
                    raise ValueError(f"the corpus has more {kind} markers than values")
            values.append(_marker(vr, self._number, latin_1, own))
        return values, tuple(_as_text(vr, value) for value in values)


def _marker_date(number: int) -> datetime.date:
    """Return the date of the date marker numbered ``number``.

    Within a run of ``_DATE_RUN_DAYS`` consecutive days dates are at most
    362 days apart, and between runs at least ``_DATE_RUN_PERIOD`` less 362,
    3,642 days, so no two are 364 to 3,640 days apart. Every date of a
    number below 2**15 is from 900 to before 1900.
    """
    run, day = divmod(number, _DATE_RUN_DAYS)
    return _FIRST_DATE + datetime.timedelta(days=run * _DATE_RUN_PERIOD + day)


def _marker(vr: str, number: int, latin_1: bool, own: int) -> object:
    """Return the marker numbered ``number`` as a value of ``vr``.

    ``own`` is its number among the markers of its kind (``_NUMBERED_APART``),
    which a date, a time, and a value of VR SS or US hold.
    """
    text = f"{MARKER_PREFIX}-{number:05d}"
    if vr in _WORD_BYTES:
        return _padded(text, vr)
    day = _marker_date(own)
    # strftime does not pad a year before 1000 to four digits on every platform.
    date = f"{day.year:04d}{day.month:02d}{day.day:02d}"
    seconds = own % _SECONDS_IN_A_DAY
    time = f"{seconds // 3600:02d}{seconds // 60 % 60:02d}{seconds % 60:02d}"
    time += _TIME_SIGNATURE
    given = "MÄRKER" if latin_1 else "MARKER"
    formats: dict[str, object] = {
        "AE": text,
        "CS": f"{MARKER_PREFIX}_{number:05d}",
        "DA": date,
        "DS": f"8{number:05d}.5",
        "DT": date + _NOON,
        "IS": f"7{number:05d}",
        "PN": f"{MARKER_PREFIX}{number:05d}^{given}{number:05d}",
        "TM": time,
        "UI": f"{MARKER_UID_ROOT}{number:05d}",
        "UR": f"https://synmk.invalid/{text}",
        "AT": 0x7FFF0000 + number,
        "FD": number + 0.5,
        "FL": number + 0.5,
        "SL": -(900_000_000 + number),
        "SS": -own,
        "SV": -(9_000_000_000 + number),
        "UL": 900_000_000 + number,
        "US": own,
        "UV": 9_000_000_000 + number,
    }
    return formats.get(vr, text)


def _padded(text: str, vr: str) -> bytes:
    """Return ``text`` in ASCII, padded to a whole number of the VR's words."""
    data = text.encode("ascii")
    width = max(_WORD_BYTES[vr], _EVEN)
    pad = b" " if vr == "UN" else b"\x00"
    return data + pad * (-len(data) % width)


def _as_text(vr: str, value: object) -> str:
    """Return a value as the manifest records it."""
    if isinstance(value, bytes):
        return value.decode("ascii").rstrip("\x00 ")
    if vr == "AT":
        return f"{value:08X}"
    return str(value)


def _least_count(vm: str) -> int:
    """Return the fewest values that the VM allows, and at least one."""
    match = VM_PATTERN.fullmatch(vm.split(" or ")[0])
    return max(1, int(match.group(1))) if match else 1


def _number(tag: str) -> int:
    return int(tag[1:5] + tag[6:10], 16)


def _items(path: Sequence[str]) -> tuple[tuple[str, int], ...]:
    """Return the items numbered 0 of each sequence of ``path``."""
    return tuple((tag, 0) for tag in path)


def _item(
    dataset: pydicom.Dataset, items: Sequence[tuple[str, int]]
) -> pydicom.Dataset:
    """Return the item at ``items``, creating each sequence and item needed."""
    for tag, index in items:
        number = _number(tag)
        if number not in dataset:
            dataset[number] = pydicom.DataElement(number, "SQ", pydicom.Sequence())
        sequence = dataset[number].value
        while len(sequence) <= index:
            sequence.append(pydicom.Dataset())
        dataset = sequence[index]
    return dataset


@functools.lru_cache(maxsize=None)
def _basic_profile_actions() -> types.MappingProxyType[str, str]:
    """Return the Basic Profile's action for each row of Table E.1-1."""
    return types.MappingProxyType(
        {row.tag: row.basic_profile for row in load_table_e1_1().attributes}
    )


@functools.lru_cache(maxsize=None)
def _profile_places(iod: IOD) -> tuple[tuple[tuple[str, ...], str, str], ...]:
    """Return each place the IOD defines an attribute of Table E.1-1.

    Each is its path, the tag the IOD gives, and the tag of its row of the
    table, once for each path and tag, in the order of the definitions.
    """
    rows = [
        row.tag
        for row in load_table_e1_1().attributes
        if row.tag != PRIVATE_ATTRIBUTES_TAG
    ]
    exact = frozenset(rows)
    masked = [row for row in rows if "x" in row]
    places: dict[tuple[tuple[str, ...], str], str] = {}
    for definition in iod.definitions:
        tag = definition.tag
        row = (
            tag
            if tag in exact
            else next((mask for mask in masked if _matches(mask, tag)), None)
        )
        if row is not None:
            places.setdefault((definition.path, tag), row)
    return tuple((path, tag, row) for (path, tag), row in places.items())


def _matches(mask: str, tag: str) -> bool:
    """Return whether a tag of Table E.1-1 with ``x`` digits covers ``tag``."""
    return len(mask) == len(tag) and all(
        digit in ("x", found) for digit, found in zip(mask, tag)
    )


class _Instance:
    """Plant the markers of one instance of the corpus."""

    def __init__(
        self,
        spec: _Spec,
        markers: _Markers,
        earlier: dict[str, FileManifest] | None = None,
    ) -> None:
        iod = iod_for_sop_class(spec.sop_class)
        if iod is None:
            raise ValueError("the corpus's SOP Classes have generated IODs")
        self.spec = spec
        self.iod = iod
        self.markers = markers
        self.dataset = pydicom.Dataset()
        if spec.character_set:
            self.dataset[0x00080005] = pydicom.DataElement(
                0x00080005, "CS", spec.character_set
            )
        self.codecs = dataset_codecs(self.dataset)
        self.levels = {
            (site.path, site.tag): site.level for site in reference_sites(iod)
        }
        self.placements: list[Placement] = []
        self.earlier = earlier or {}

    def build(self) -> tuple[pydicom.Dataset, FileManifest]:
        """Return the instance's data set and its manifest."""
        for path, tag, row in _profile_places(self.iod):
            self._place(path, tag, row)
        self._fill_sequences()
        self._reference_every_slice()
        self._add_private_blocks()
        self._add_review_copy()
        self._add_structure()
        manifest = FileManifest(
            self.spec.name,
            self.iod.name,
            self.spec.sop_class,
            self.spec.sop_instance,
            self.spec.transfer_syntax,
            self.spec.character_set,
            tuple(self.placements),
        )
        return self.dataset, manifest

    def _record(
        self,
        path: ElementPath,
        vr: str,
        values: tuple[str, ...],
        kind: PlacementKind,
        row: str,
        reason: NotPlantedReason | None = None,
    ) -> None:
        self.placements.append(Placement(path, vr, values, kind, row, reason))

    def _place(self, path: tuple[str, ...], tag: str, row: str) -> None:
        """Plant one attribute of Table E.1-1, or record why it is not."""
        written = tag.replace("xx,", "00,", 1) if tag[3:5] == "xx" else tag
        element_path = ElementPath(_items(path), written)
        attribute = dictionary_attribute(written) if "x" not in written else None
        vr = _DECIDED_VRS.get(tag) or (
            attribute.vrs[0] if attribute and len(attribute.vrs) == 1 else ""
        )
        reason = None
        if (
            self.spec.sop_class in ROOT_TEMPLATES
            and (path[:1] or (tag,))[0] in _CONTENT_TREE_ROOT
        ):
            # The content tree takes the place of the markers. A place below
            # the Content Sequence is not recorded, since the tree's items,
            # not items numbered 0, decide what is there.
            if path[:1] != (_CONTENT_SEQUENCE,):
                kind = (
                    PlacementKind.SEQUENCE if path == () else PlacementKind.NOT_PLANTED
                )
                self._record(
                    element_path, vr, (), kind, row, NotPlantedReason.CONTENT_TREE
                )
            return
        if "x" in written:
            reason = NotPlantedReason.MASKED_ELEMENT
        elif attribute is None or not vr:
            reason = NotPlantedReason.NO_SINGLE_VR
        elif len(path) + (vr == "SQ") > MAX_DEPTH:
            reason = NotPlantedReason.DEPTH_CAP
        elif self.spec.name != SEQUESTERED_FILE and (
            self._sequesters(path, written, row) or self._in_sequestering_sequence(path)
        ):
            reason = NotPlantedReason.SEQUESTERS_INSTANCE
        if reason is not None or attribute is None:
            self._record(element_path, vr, (), PlacementKind.NOT_PLANTED, row, reason)
            return
        item = _item(self.dataset, element_path.items)
        if vr == "SQ":
            _item(item, ((written, 0),))
            self._record(element_path, vr, (), PlacementKind.SEQUENCE, row)
            return
        linked = self._linked(path, tag)
        if linked is not None:
            kind, value = linked
            item[_number(written)] = new_element(element_path, vr, [value], self.codecs)
            self._record(element_path, vr, (value,), kind, row)
            return
        if not path and tag == self.spec.un_encoded:
            values, text = self.markers.values("UN", 1)
            element = pydicom.DataElement(_number(written), "UN", values[0])
            # pydicom gives a known attribute its own VR in place of UN.
            element.VR = "UN"
            item[_number(written)] = element
            self._record(element_path, "UN", text, PlacementKind.UN_ENCODED, row)
            return
        if not path and tag == self.spec.invalid and vr == "UI":
            _, (marker,) = self.markers.values("LO", 1)
            value = f"2.25.{marker}"
            # Built without pydicom's check, which would warn.
            item[_number(written)] = pydicom.DataElement(
                _number(written),
                vr,
                value,
                validation_mode=pydicom.config.IGNORE,
            )
            self._record(element_path, vr, (value,), PlacementKind.INVALID, row)
            return
        latin_1 = (
            bool(self.spec.character_set) and not path and (tag == _PATIENTS_NAME_TAG)
        )
        values, text = self.markers.values(
            vr, _least_count(attribute.vm), latin_1=latin_1
        )
        item[_number(written)] = new_element(element_path, vr, values, self.codecs)
        self._record(element_path, vr, text, PlacementKind.PLANTED, row)

    def _sequesters(self, path: tuple[str, ...], tag: str, row: str) -> bool:
        """Return whether the Basic Profile's action on a place sequesters.

        A plain X sequesters where it removes an attribute that the IOD
        requires outside any Type 3 sequence, and a D where the attribute's
        VR has no dummy value and no reviewed rule gives it one at the place,
        unless the Basic Profile removes a sequence that encloses it.
        """
        action = _basic_profile_actions()[row]
        if action == "X":
            return (
                resolve_plain_x_in_iod(self.iod, tag, path).extent
                is RemovalExtent.SEQUESTER
            )
        attribute = dictionary_attribute(tag)
        return (
            not (tag in _REVIEWED_DUMMY_SEQUENCES and reviewed_within(tag, path))
            and attribute is not None
            and not DUMMY_VRS.intersection(attribute.vrs)
            and self._resolved(path, tag, action) == "D"
            and not any(
                self._resolved(path[:depth], path[depth]) == "X"
                for depth in range(len(path))
            )
        )

    def _resolved(
        self, path: tuple[str, ...], tag: str, action: str | None = None
    ) -> str | None:
        """Return the Basic Profile's action at a place, resolved by Type."""
        if action is None:
            action = _basic_profile_actions().get(tag)
        if action in COMPOUND_ACTIONS:
            return resolve_in_iod(self.iod, tag, path, action)
        if action is not None:
            return resolve_plain_in_iod(self.iod, tag, path, action)
        return None

    def _in_sequestering_sequence(self, path: tuple[str, ...]) -> bool:
        """Return whether a sequence that encloses a place sequesters."""
        actions = _basic_profile_actions()
        return any(
            path[depth] in actions
            and self._sequesters(path[:depth], path[depth], path[depth])
            for depth in range(len(path))
        )

    def _linked(
        self, path: tuple[str, ...], tag: str
    ) -> tuple[PlacementKind, str] | None:
        """Return the linked value of an attribute, and set its item's class."""
        top_level = {
            _SOP_INSTANCE_TAG: (PlacementKind.LINKED_UID, self.spec.sop_instance),
            _SERIES_TAG: (PlacementKind.LINKED_UID, self.spec.series),
            _STUDY_TAG: (PlacementKind.LINKED_UID, STUDY),
            _PATIENT_ID_TAG: (PlacementKind.LINKED_PATIENT, PATIENT_ID),
            _ISSUER_TAG: (PlacementKind.LINKED_PATIENT, ISSUER_OF_PATIENT_ID),
        }
        if not path and tag in top_level:
            return top_level[tag]
        if tag in _FRAME_OF_REFERENCE_TAGS:
            return PlacementKind.LINKED_UID, FRAME_OF_REFERENCE
        level = self.levels.get((path, tag))
        if level is None or tag not in REFERENCE_TAGS:
            return None
        if level is Level.STUDY:
            self._set_class(path, DETACHED_STUDY_MANAGEMENT, 0)
            return PlacementKind.LINKED_UID, STUDY
        if level is Level.SERIES:
            return PlacementKind.LINKED_UID, self.spec.referenced_series
        target = dict(self.spec.targets).get(
            path[-1], _TARGETS.get(path[-1], self.spec.default_target)
        )
        self._set_class(path, _SOP_CLASSES[target], 0)
        return PlacementKind.LINKED_UID, target

    def _set_class(self, path: tuple[str, ...], sop_class: str, index: int) -> None:
        """Give an item its Referenced SOP Class UID, where the IOD defines it."""
        if not self.iod.lookup(REFERENCED_SOP_CLASS_TAG, path):
            return
        items = (*_items(path[:-1]), (path[-1], index))
        item = _item(self.dataset, items)
        number = _number(REFERENCED_SOP_CLASS_TAG)
        if number not in item:
            element_path = ElementPath(items, REFERENCED_SOP_CLASS_TAG)
            item[number] = new_element(element_path, "UI", [sop_class], self.codecs)

    def _fill_sequences(self) -> None:
        """Give each sequence of Table E.1-1 without a marker below it one.

        The deepest sequences go first, so a marker put in one counts for
        the sequences that hold it. Only a marker counts: a linked value
        stays with a sequence that a preset keeps.
        """
        sequences = sorted(
            (
                (position, placement)
                for position, placement in enumerate(self.placements)
                if placement.kind is PlacementKind.SEQUENCE
            ),
            key=lambda each: (-len(each[1].path.items), each[0]),
        )
        profile = {(path, tag) for path, tag, _ in _profile_places(self.iod)}
        for position, sequence in sequences:
            inside = (*sequence.path.items, (sequence.path.tag, 0))
            if sequence.reason is NotPlantedReason.CONTENT_TREE or any(
                placement.path.items[: len(inside)] == inside
                and placement.kind in _MARKER_KINDS
                for placement in self.placements
            ):
                continue
            path = tuple(tag for tag, _ in inside)
            candidates = [
                attribute
                for definition in self.iod.definitions
                if definition.path == path
                and "x" not in definition.tag
                and (path, definition.tag) not in profile
                and (attribute := dictionary_attribute(definition.tag)) is not None
                and attribute.vr not in ("SQ", "UI")
                and len(attribute.vrs) == 1
            ]
            # Text first, which the residual search looks for.
            candidates.sort(key=lambda attribute: attribute.vr not in _CONTENT_VRS)
            if not candidates:
                self.placements[position] = dataclasses.replace(
                    sequence, reason=NotPlantedReason.NO_MARKER_CARRIER
                )
                continue
            if self._kept(sequence):
                self.placements[position] = dataclasses.replace(
                    sequence, reason=NotPlantedReason.KEPT_SEQUENCE
                )
                continue
            attribute = candidates[0]
            values, text = self.markers.values(attribute.vr, _least_count(attribute.vm))
            element_path = ElementPath(inside, attribute.tag)
            _item(self.dataset, inside)[_number(attribute.tag)] = new_element(
                element_path, attribute.vr, values, self.codecs
            )
            self._record(element_path, attribute.vr, text, PlacementKind.CONTENT, "")

    def _kept(self, sequence: Placement) -> bool:
        """Return whether the Basic Profile keeps a sequence's item.

        It does where it keeps the sequence and replaces only its UIDs, as
        X/Z/U* does where the IOD requires the sequence at its place, and
        keeps each sequence of Table E.1-1 that encloses it.
        """
        actions = _basic_profile_actions()
        tags = (*(tag for tag, _ in sequence.path.items), sequence.path.tag)
        return all(
            "/" in actions[tag]
            and resolve_in_iod(self.iod, tag, tags[:depth], actions[tag]) == "U"
            for depth, tag in enumerate(tags)
            if tag in actions
        )

    def _reference_every_slice(self) -> None:
        """Have the structure set's RT Referenced Series reference each slice."""
        if self.spec.sop_class != RT_STRUCTURE_SET_STORAGE:
            return
        path = (*_RT_REFERENCED_CONTOUR_IMAGES, _CONTOUR_IMAGE_SEQUENCE)
        tag = "(0008,1155)"
        for index, target in enumerate(CT_SLICES[1:], start=1):
            items = (*_items(path[:-1]), (path[-1], index))
            element_path = ElementPath(items, tag)
            _item(self.dataset, items)[_number(tag)] = new_element(
                element_path, "UI", [target], self.codecs
            )
            self._set_class(path, CT_IMAGE_STORAGE, index)
            self._record(element_path, "UI", (target,), PlacementKind.LINKED_UID, tag)

    def _add_private_blocks(self) -> None:
        """Add a private block at the top level, and in an item."""
        places: list[tuple[tuple[str, int], ...]] = [
            (),
            ((PRIVATE_ITEM_SEQUENCE, 0),),
        ]
        for items in places:
            item = _item(self.dataset, items)
            creator = f"({PRIVATE_GROUP:04X},0010)"
            elements = [(creator, "LO")] + [
                (f"({PRIVATE_GROUP:04X},10{offset:02X})", vr)
                for offset, vr in enumerate(("LO", "PN", "DA"), start=1)
            ]
            for tag, vr in elements:
                values, text = self.markers.values(vr, 1)
                if values_problem(vr, "1", values):
                    raise ValueError("a private marker is invalid for its VR")
                item[_number(tag)] = pydicom.DataElement(_number(tag), vr, values[0])
                self._record(
                    ElementPath(items, tag),
                    vr,
                    text,
                    PlacementKind.PRIVATE,
                    PRIVATE_ATTRIBUTES_TAG,
                )

    def _add_review_copy(self) -> None:
        """Copy an earlier file's marker into an attribute the profile keeps."""
        if self.spec.review_copy is None:
            return
        tag, name, source = self.spec.review_copy
        (marker,) = [
            placement
            for placement in self.earlier[name].placements
            if placement.path == ElementPath((), source)
            and placement.kind is PlacementKind.PLANTED
        ]
        attribute = dictionary_attribute(tag)
        if attribute is None or attribute.vrs != ("LO",):
            raise ValueError("the copy goes in an attribute of VR LO")
        if tag in _basic_profile_actions() or _number(tag) in self.dataset:
            raise ValueError(
                "the copy goes in an empty attribute that Table E.1-1 does not list"
            )
        path = ElementPath((), tag)
        self.dataset[_number(tag)] = new_element(
            path, "LO", list(marker.values), self.codecs
        )
        self._record(path, "LO", marker.values, PlacementKind.REVIEW_COPY, "")

    def _set(self, items: Sequence[tuple[str, int]], tag: str, values: list) -> None:
        """Set an attribute that holds no marker, unless a marker is there."""
        item = _item(self.dataset, items)
        if _number(tag) in item:
            return
        attribute = dictionary_attribute(tag)
        if attribute is None:
            raise ValueError(f"{tag} is not in the pinned data dictionary")
        vr = "OW" if tag == "(7FE0,0010)" else attribute.vrs[0]
        item[_number(tag)] = new_element(
            ElementPath(tuple(items), tag), vr, values, self.codecs
        )

    def _add_structure(self) -> None:
        """Add the attributes that make the instance an image, ROI, plan, or dose."""
        put = self._set
        put((), "(0008,0016)", [self.spec.sop_class])
        if self.spec.sop_class == CT_IMAGE_STORAGE:
            put((), "(0008,0060)", ["CT"])
            put((), "(0008,0008)", ["ORIGINAL", "PRIMARY", "AXIAL"])
            put((), "(0018,0050)", ["2"])
            put((), "(0020,0032)", ["-1", "-1", str(2 * self.spec.slice_index)])
            put((), "(0020,0037)", ["1", "0", "0", "0", "1", "0"])
            put((), "(0028,1052)", ["-1024"])
            put((), "(0028,1053)", ["1"])
            self._add_pixels(16, 1, struct.pack("<4h", 0, 1024, 2048, 3072))
        elif self.spec.sop_class == RT_STRUCTURE_SET_STORAGE:
            put((), "(0008,0060)", ["RTSTRUCT"])
            put(_items(["(3006,0020)"]), "(3006,0022)", ["1"])
            put(_items(["(3006,0020)"]), "(3006,0036)", ["MANUAL"])
            put(_items(["(3006,0039)"]), "(3006,0084)", ["1"])
            contour = _items(["(3006,0039)", "(3006,0040)"])
            put(contour, "(3006,0042)", ["POINT"])
            put(contour, "(3006,0046)", ["1"])
            put(contour, "(3006,0050)", ["0", "0", "0"])
        elif self.spec.sop_class in (RT_PLAN_STORAGE, RT_ION_PLAN_STORAGE):
            put((), "(0008,0060)", ["RTPLAN"])
            put((), "(300A,000C)", ["PATIENT"])
        elif self.spec.sop_class in ROOT_TEMPLATES:
            self._add_content_tree()
        elif self.spec.sop_class in (
            RT_BEAMS_TREATMENT_RECORD_STORAGE,
            RT_ION_BEAMS_TREATMENT_RECORD_STORAGE,
            RT_BRACHY_TREATMENT_RECORD_STORAGE,
            RT_TREATMENT_SUMMARY_RECORD_STORAGE,
        ):
            put((), "(0008,0060)", ["RTRECORD"])
        elif self.spec.sop_class in (
            RT_BEAMS_DELIVERY_INSTRUCTION_STORAGE,
            RT_BRACHY_APPLICATION_SETUP_DELIVERY_INSTRUCTION_STORAGE,
            RT_RADIATION_SET_DELIVERY_INSTRUCTION_STORAGE,
        ):
            # PS3.3 Sections A.64.4.1, A.79.4.1, and A.86.1.13.4.1.
            put((), "(0008,0060)", ["PLAN"])
        elif self.spec.sop_class == MR_SPECTROSCOPY_STORAGE:
            put((), "(0008,0060)", ["MR"])
            put((), "(0008,0008)", ["ORIGINAL", "PRIMARY", "SPECTROSCOPY", "NONE"])
            put((), "(0028,0008)", ["1"])
            put((), "(0028,0010)", [1])
            put((), "(0028,0011)", [1])
            put((), "(0028,9001)", [1])
            put((), "(0028,9002)", [2])
            put((), "(0028,9003)", ["FREQUENCY"])
            put((), "(0028,9108)", ["REAL"])
            put((), "(5600,0020)", [struct.pack("<2f", 1.0, 2.0)])
        elif self.spec.sop_class in _IMAGES:
            self._add_image(_IMAGES[self.spec.sop_class])
        elif self.spec.sop_class in _REGISTRATIONS:
            self._add_registration()
        elif self.spec.sop_class in _SEGMENTATIONS:
            self._add_segmentation()
        elif self.spec.sop_class == PARAMETRIC_MAP_STORAGE:
            self._add_parametric_map()
        elif self.spec.sop_class == REAL_WORLD_VALUE_MAPPING_STORAGE:
            put((), "(0008,0060)", ["RWV"])
            # Each item maps the images it names by the items of its own Real
            # World Value Mapping Sequence (PS3.3 Table C.25.2-1).
            self._add_value_mapping(
                _items(["(0040,9094)", "(0040,9096)"]),
                _SUV_BODY_WEIGHT,
                (0, 32767),
                0.0005,
            )
        elif self.spec.sop_class == ENCAPSULATED_PDF_STORAGE:
            put((), "(0008,0060)", ["DOC"])
            put((), "(0042,0012)", ["application/pdf"])
        elif self.spec.sop_class == SURFACE_SEGMENTATION_STORAGE:
            self._add_surface_segmentation()
        elif self.spec.sop_class in PRESENTATION_STATE_STORAGE_CLASSES:
            put((), "(0008,0060)", ["PR"])
        elif self.spec.sop_class == RT_IMAGE_STORAGE:
            put((), "(0008,0060)", ["RTIMAGE"])
            put((), "(0008,0008)", ["DERIVED", "SECONDARY", "DRR"])
            put((), "(3002,000C)", ["NORMAL"])  # RT Image Plane
            self._add_pixels(16, 0, struct.pack("<4H", 0, 100, 200, 300))
        elif self.spec.sop_class in (
            ENHANCED_RT_IMAGE_STORAGE,
            ENHANCED_CONTINUOUS_RT_IMAGE_STORAGE,
        ):
            self._add_enhanced_rt_image()
        elif self.spec.sop_class == RT_SEGMENT_ANNOTATION_STORAGE:
            put((), "(0008,0060)", ["RTSEGANN"])
        elif self.spec.sop_class in _RADIATIONS:
            put((), "(0008,0060)", ["RTRAD"])
        else:
            put((), "(0008,0060)", ["RTDOSE"])
            put((), "(0020,0032)", ["-1", "-1", "0"])
            put((), "(0020,0037)", ["1", "0", "0", "0", "1", "0"])
            put((), "(0028,0008)", ["2"])
            put((), "(0028,0009)", [0x3004000C])
            put((), "(3004,0002)", ["GY"])
            put((), "(3004,0004)", ["PHYSICAL"])
            put((), "(3004,000A)", ["PLAN"])
            put((), "(3004,000C)", ["0", "2"])
            put((), "(3004,000E)", ["0.001"])
            self._add_pixels(32, 0, struct.pack("<8I", *range(0, 8000, 1000)))

    def _add_enhanced_rt_image(self) -> None:
        """Add the attributes that make the instance an Enhanced or Enhanced
        Continuous RT Image.

        It holds two frames of 2 by 2 pixels, whose spacing the Shared
        Functional Groups Sequence (5200,9229) gives. An Enhanced Continuous
        RT Image's Selected Frame Functional Groups Sequence (3002,0101)
        selects only the first frame, by its Selected Frame Number
        (3002,0100), since the Sparse Multi-frame Functional Groups Module of
        PS3.3 C.7.6.29 selects fewer frames than the image has; the markers
        of the macros are planted in that item.
        """
        put = self._set
        continuous = self.spec.sop_class == ENHANCED_CONTINUOUS_RT_IMAGE_STORAGE
        put((), "(0008,0060)", ["RTIMAGE"])
        if continuous:
            put((), "(0008,0008)", ["ORIGINAL", "PRIMARY", "SIMULATOR", "NONE"])
        else:
            put((), "(0008,0008)", ["DERIVED", "PRIMARY", "DRR", "NONE"])
        put((), "(0028,0008)", ["2"])
        shared = _items(["(5200,9229)"])
        put((*shared, ("(0028,9110)", 0)), "(0028,0030)", ["1", "1"])
        if continuous:
            put((("(3002,0101)", 0),), "(3002,0100)", ["1"])
        self._add_pixels(16, 0, struct.pack("<8H", *range(0, 800, 100)))

    def _add_registration(self) -> None:
        """Add the attributes that make the instance a rigid or deformable registration."""
        put = self._set
        put((), "(0008,0060)", ["REG"])
        if self.spec.sop_class == SPATIAL_REGISTRATION_STORAGE:
            matrix = _items(["(0070,0308)", "(0070,0309)", "(0070,030A)"])
            put(matrix, "(3006,00C6)", _IDENTITY_MATRIX)
            put(matrix, "(0070,030C)", ["RIGID"])
        else:
            grid = _items(["(0064,0002)", "(0064,0005)"])
            put(grid, "(0020,0032)", ["-1", "-1", "0"])
            put(grid, "(0020,0037)", ["1", "0", "0", "0", "1", "0"])
            put(grid, "(0064,0007)", [2, 2, 1])
            put(grid, "(0064,0008)", [1.0, 1.0, 1.0])
            # A displacement of each of the grid's four points, in mm.
            put(grid, "(0064,0009)", [struct.pack("<12f", *range(12))])

    def _add_segmentation(self) -> None:
        """Add the attributes that make the instance a Segmentation.

        Its one segment, of Tissue, is in two frames, in the planes of the
        first two CT slices, placed by their functional groups, so that a
        segments sheet can draw it. A BINARY Segmentation's frames are 4 by
        4 pixels, so that each fills whole bytes of its 1-bit Pixel Data, in
        which the segment holds the pixels of the first two rows; a LABELMAP
        one's are 2 by 2 pixels of 8 bits, in which the segment holds the
        first row's and the rest are its Pixel Padding Value, 0, which a
        second item of its Segment Sequence describes, as PS3.3 C.8.20.2.3.3
        requires of each value that a label map's pixels hold.
        """
        put = self._set
        labelmap = self.spec.sop_class == LABEL_MAP_SEGMENTATION_STORAGE
        put((), "(0008,0060)", ["SEG"])
        put((), "(0008,0008)", ["DERIVED", "PRIMARY"])
        put((), "(0070,0080)", ["SEGMENTS"])  # Content Label
        put((), "(0062,0001)", ["LABELMAP" if labelmap else "BINARY"])
        for index, (number, label) in enumerate(
            ((1, "TISSUE"), (0, "BACKGROUND"))[: 1 + labelmap]
        ):
            segment = (("(0062,0002)", index),)
            put(segment, "(0062,0004)", [number])  # Segment Number
            put(segment, "(0062,0005)", [label])  # Segment Label
            put(segment, "(0062,0008)", ["MANUAL"])  # Segment Algorithm Type
            for sequence in ("(0062,0003)", "(0062,000F)"):
                code = (*segment, (sequence, 0))
                put(code, "(0008,0100)", ["85756007"])
                put(code, "(0008,0102)", ["SCT"])
                put(code, "(0008,0104)", ["Tissue"])
        shared = _items(["(5200,9229)"])
        put(
            (*shared, ("(0020,9116)", 0)), "(0020,0037)", ["1", "0", "0", "0", "1", "0"]
        )
        measures = (*shared, ("(0028,9110)", 0))
        put(measures, "(0028,0030)", ["1", "1"])
        put(measures, "(0018,0050)", ["2"])
        put(measures, "(0018,0088)", ["2"])
        for frame in range(2):
            groups = (("(5200,9230)", frame),)
            put(
                (*groups, ("(0020,9113)", 0)),
                "(0020,0032)",
                ["-1", "-1", str(2 * frame)],
            )
            if not labelmap:
                put((*groups, ("(0062,000A)", 0)), "(0062,000B)", [1])
        put((), "(0028,0008)", ["2"])
        if labelmap:
            put((), "(0028,0120)", [0])  # Pixel Padding Value
            self._add_pixels(8, 0, bytes([1, 1, 0, 0] * 2))
        else:
            self._add_pixels(1, 0, bytes([0xFF, 0x00] * 2), size=4)

    def _add_parametric_map(self) -> None:
        """Add the attributes that make the instance a Parametric Map.

        Its two frames, of 2 by 2 unsigned 16-bit apparent diffusion
        coefficients, lie in the planes of the first two CT slices, placed
        by their functional groups, as a Segmentation's are, and its shared
        Real World Value Mapping functional group maps each stored value to
        a coefficient in square micrometres per second, as an ADC map
        written as integers does (PS3.3 Section A.75).
        """
        put = self._set
        put((), "(0008,0060)", ["MR"])
        # Image Flavor VOLUME and Derived Pixel Contrast ADC (PS3.3 Sections
        # C.8.16.1.3 and C.8.13.1.1.1.4), for the image and its frames alike.
        flavour = ["DERIVED", "PRIMARY", "VOLUME", "ADC"]
        put((), "(0008,0008)", flavour)
        put((), "(0070,0080)", ["ADC"])  # Content Label
        put((), "(2050,0020)", ["IDENTITY"])  # Presentation LUT Shape
        put((), "(0028,2110)", ["00"])  # Lossy Image Compression
        put((), "(0018,9004)", ["RESEARCH"])  # Content Qualification
        shared = _items(["(5200,9229)"])
        put(
            (*shared, ("(0020,9116)", 0)), "(0020,0037)", ["1", "0", "0", "0", "1", "0"]
        )
        measures = (*shared, ("(0028,9110)", 0))
        put(measures, "(0028,0030)", ["1", "1"])
        put(measures, "(0018,0050)", ["2"])
        put(measures, "(0018,0088)", ["2"])
        put((*shared, ("(0040,9092)", 0)), "(0008,9007)", flavour)
        self._add_value_mapping(
            (*shared, ("(0040,9096)", 0)), _APPARENT_DIFFUSION, (0, 4000), 1.0
        )
        for frame in range(2):
            put(
                (("(5200,9230)", frame), ("(0020,9113)", 0)),
                "(0020,0032)",
                ["-1", "-1", str(2 * frame)],
            )
        put((), "(0028,0008)", ["2"])
        self._add_pixels(
            16, 0, struct.pack("<8H", 0, 800, 1600, 2400, 0, 900, 1800, 2700)
        )

    def _add_value_mapping(
        self,
        item: tuple[tuple[str, int], ...],
        units: tuple[str, str, str],
        mapped: tuple[int, int],
        slope: float,
    ) -> None:
        """Map unsigned stored values from ``mapped``'s first to its last to
        ``units``, a UCUM code, by ``slope``, in the item of a Real World
        Value Mapping Item Macro (PS3.3 Table C.7.6.16-12)."""
        put = self._set
        put(item, "(0040,9216)", [mapped[0]])  # Real World Value First Value Mapped
        put(item, "(0040,9211)", [mapped[1]])  # Real World Value Last Value Mapped
        put(item, "(0040,9224)", [0.0])  # Real World Value Intercept
        put(item, "(0040,9225)", [slope])  # Real World Value Slope
        put(item, "(0028,3003)", [units[2]])  # LUT Explanation
        put(item, "(0040,9210)", [units[2][:16]])  # LUT Label
        code = (*item, ("(0040,08EA)", 0))
        put(code, "(0008,0100)", [units[0]])
        put(code, "(0008,0102)", ["UCUM"])
        put(code, "(0008,0104)", [units[1]])

    def _add_surface_segmentation(self) -> None:
        """Add the attributes that make the instance a Surface Segmentation.

        Its one segment, of Tissue, has one surface: a closed, manifold
        tetrahedron of four points and four triangles, within the extent of
        the first two CT slices, without normals, whose triangles index its
        points from 1.
        """
        put = self._set
        put((), "(0008,0060)", ["SEG"])
        put((), "(0070,0080)", ["SURFACES"])  # Content Label
        segment = _items(["(0062,0002)"])
        put(segment, "(0062,0004)", [1])  # Segment Number
        put(segment, "(0062,0005)", ["TISSUE"])  # Segment Label
        put(segment, "(0062,0008)", ["MANUAL"])  # Segment Algorithm Type
        for sequence in ("(0062,0003)", "(0062,000F)"):
            code = (*segment, (sequence, 0))
            put(code, "(0008,0100)", ["85756007"])
            put(code, "(0008,0102)", ["SCT"])
            put(code, "(0008,0104)", ["Tissue"])
        put(segment, "(0066,002A)", [1])  # Surface Count
        referenced = (*segment, ("(0066,002B)", 0))
        put(referenced, "(0066,002C)", [1])  # Referenced Surface Number
        algorithm = (*referenced, ("(0066,002D)", 0))
        family = (*algorithm, ("(0066,002F)", 0))
        put(family, "(0008,0100)", ["123109"])
        put(family, "(0008,0102)", ["DCM"])
        put(family, "(0008,0104)", ["Manual Processing"])
        put(algorithm, "(0066,0036)", ["MANUAL"])  # Algorithm Name
        put(algorithm, "(0066,0031)", ["1"])  # Algorithm Version
        put((), "(0066,0001)", [1])  # Number of Surfaces
        surface = _items(["(0066,0002)"])
        put(surface, "(0066,0003)", [1])  # Surface Number
        put(surface, "(0066,0009)", ["NO"])  # Surface Processing
        put(surface, "(0062,000C)", [0xFFFF])  # Recommended Display Grayscale
        put(surface, "(0062,000D)", [0xFFFF, 0x8080, 0x8080])  # CIELab
        put(surface, "(0066,000C)", [1.0])  # Recommended Presentation Opacity
        put(surface, "(0066,000D)", ["SURFACE"])  # Recommended Presentation Type
        put(surface, "(0066,000E)", ["YES"])  # Finite Volume
        put(surface, "(0066,0010)", ["YES"])  # Manifold
        points = (*surface, ("(0066,0011)", 0))
        put(points, "(0066,0015)", [4])  # Number of Surface Points
        put(
            points,
            "(0066,0016)",
            [struct.pack("<12f", -1, -1, 0, 1, -1, 0, -1, 1, 0, -1, -1, 2)],
        )
        put(surface, "(0066,0012)", [])  # Surface Points Normals Sequence
        primitives = (*surface, ("(0066,0013)", 0))
        put(
            primitives,
            "(0066,0041)",  # Long Triangle Point Index List
            [struct.pack("<12I", 1, 3, 2, 1, 2, 4, 2, 3, 4, 3, 1, 4)],
        )
        for empty in (
            "(0066,0043)",  # Long Vertex Point Index List
            "(0066,0042)",  # Long Edge Point Index List
            "(0066,0026)",  # Triangle Strip Sequence
            "(0066,0027)",  # Triangle Fan Sequence
            "(0066,0028)",  # Line Sequence
            "(0066,0034)",  # Facet Sequence
        ):
            put(primitives, empty, [])

    def _add_content_tree(self) -> None:
        """Add the attributes that make the instance a Structured Report.

        The content tree's identifying values, of its UIDREF, DATE, TIME,
        DATETIME, PNAME, and TEXT items, are markers, but the UIDs that name
        the collection's study, series, or Frame of Reference, such as the
        study that an X-ray report's scope of accumulation names, which are
        the collection's, and the fixed text of an algorithm's name or a
        patient orientation, which is not recorded; each marker is recorded
        with its item's concept name. A measurement report's volumetric
        region is in the collection's Frame of Reference, an IMAGE item
        references the instance that the report's header references, and
        the report that a patient dose estimate used is the collection's CT
        dose report, each recorded as linked. A report is VERIFIED, so its
        Verifying Observer Sequence, whose markers are planted as any
        attribute's, is one that its IOD requires; a Key Object Selection
        Document has no Verification Flag. A Procedure Log has the
        Synchronization Module that its IOD requires.
        """
        put = self._set
        template = self.spec.template or ROOT_TEMPLATES[self.spec.sop_class]
        if template == "2010":
            put((), "(0008,0060)", ["KO"])
        else:
            put((), "(0008,0060)", ["SR"])
            put((), "(0040,A491)", ["COMPLETE"])  # Completion Flag
            put((), "(0040,A493)", ["VERIFIED"])  # Verification Flag
        if template == "3001":
            put((), "(0018,106A)", ["NO TRIGGER"])  # Synchronization Trigger
            put((), "(0018,1800)", ["N"])  # Acquisition Time Synchronized
        content_template = _items(["(0040,A504)"])  # Content Template Sequence
        put(content_template, "(0008,0105)", ["DCMR"])  # Mapping Resource
        put(content_template, "(0040,DB00)", [template])
        # The text values that are markers; any other text is fixed.
        planted_text: set[str] = set()

        def values(value_type: str) -> str:
            _, (text,) = self.markers.values(_CONTENT_ITEM_VRS[value_type], 1)
            if value_type == "TEXT":
                planted_text.add(text)
            return text

        target = self.spec.default_target
        image = Image(_SOP_CLASSES[target], target)
        trees = {
            "10001": lambda: x_ray_dose_tree(values, STUDY),
            CT_RADIATION_DOSE_TEMPLATE: lambda: ct_dose_tree(values, STUDY),
            "10040": lambda: enhanced_x_ray_dose_tree(values),
            "10030": lambda: patient_dose_tree(values, CT_DOSE_REPORT),
            "10021": lambda: radiopharmaceutical_dose_tree(values),
            "2000": lambda: imaging_report_tree(values),
            "1500": lambda: measurement_report_tree(values, FRAME_OF_REFERENCE),
            "2010": lambda: key_object_selection_tree(image),
            "4000": lambda: mammography_cad_tree(values, image),
            "4100": lambda: chest_cad_tree(image),
            "4120": lambda: colon_cad_tree(
                values, STUDY, FRAME_OF_REFERENCE, CT_SERIES
            ),
            "3001": lambda: procedure_log_tree(values),
            "2020": spectacle_prescription_tree,
            "2100": lambda: macular_grid_tree(values),
            "3750": lambda: waveform_annotation_tree(values),
        }
        root = trees[template]()
        for element in root:
            self.dataset.add(element)
        self._record_content(root, (), frozenset(planted_text))

    def _record_content(
        self,
        item: pydicom.Dataset,
        items: tuple[tuple[str, int], ...],
        planted_text: frozenset[str],
    ) -> None:
        """Record the identifying value of each content item below ``item``.

        The frame of reference of a SCOORD3D item, and the instance that an
        IMAGE item references or a COMPOSITE item names, are recorded too, as
        linked, with no concept name, since each takes its own row of Table
        E.1-1. A TEXT item is recorded only if its value is one of
        ``planted_text``, the markers; any other text is fixed.
        """
        for index, child in enumerate(item.get("ContentSequence", ())):
            within = (*items, (_CONTENT_SEQUENCE, index))
            value_type = child.get("ValueType")
            if value_type == "SCOORD3D":
                self._record(
                    ElementPath(within, _REFERENCED_FRAME_OF_REFERENCE),
                    "UI",
                    (str(child.ReferencedFrameOfReferenceUID),),
                    PlacementKind.LINKED_UID,
                    _REFERENCED_FRAME_OF_REFERENCE,
                )
            if value_type in ("IMAGE", "COMPOSITE"):
                (reference,) = child.ReferencedSOPSequence
                self._record(
                    ElementPath(
                        (*within, (_REFERENCED_SOP, 0)), REFERENCED_SOP_INSTANCE_TAG
                    ),
                    "UI",
                    (str(reference.ReferencedSOPInstanceUID),),
                    PlacementKind.LINKED_UID,
                    REFERENCED_SOP_INSTANCE_TAG,
                )
            tag = _CONTENT_ITEM_VALUES.get(value_type)
            value = "" if tag is None else str(child[_number(tag)].value)
            if tag is not None and (value_type != "TEXT" or value in planted_text):
                (code,) = child.ConceptNameCodeSequence
                self.placements.append(
                    Placement(
                        ElementPath(within, tag),
                        _CONTENT_ITEM_VRS[value_type],
                        (value,),
                        (
                            PlacementKind.LINKED_UID
                            if value in _COLLECTION_UIDS
                            else PlacementKind.PLANTED
                        ),
                        tag,
                        concept=(
                            code.CodingSchemeDesignator,
                            code.CodeValue,
                            value_type,
                        ),
                    )
                )
            self._record_content(child, within, planted_text)

    def _add_image(self, image: _Image) -> None:
        """Add the attributes that make the instance an MR, PET, or CT image."""
        put = self._set
        put((), "(0008,0060)", [image.modality])
        if image.frames:
            put((), "(0008,0008)", ["ORIGINAL", "PRIMARY", "AXIAL", "NONE"])
            put((), "(0028,0008)", [str(image.frames)])
        else:
            put((), "(0008,0008)", ["ORIGINAL", "PRIMARY", "AXIAL"])
            put((), "(0020,0032)", ["-1", "-1", "0"])
            put((), "(0020,0037)", ["1", "0", "0", "0", "1", "0"])
        if image.modality == "PT" and not image.frames:
            put((), "(0028,1052)", ["0"])
            put((), "(0028,1053)", ["1"])
            put((), "(0054,1001)", ["BQML"])
        frames = max(1, image.frames)
        if image.colour:
            put((), "(0028,2000)", [SOURCE_ICC_PROFILE])
            self._add_pixels(8, 0, bytes(range(12 * frames)), colour=True)
        else:
            samples = range(0, 400 * frames, 100)
            self._add_pixels(
                16,
                int(image.modality == "CT"),
                struct.pack(f"<{4 * frames}H", *samples),
            )

    def _add_pixels(
        self,
        bits: int,
        representation: int,
        data: bytes,
        *,
        colour: bool = False,
        size: int = 2,
    ) -> None:
        """Add ``size`` by ``size`` monochrome, or RGB, frames of
        ``bits``-bit samples."""
        put = self._set
        if colour:
            put((), "(0028,0002)", [3])
            put((), "(0028,0004)", ["RGB"])
            put((), "(0028,0006)", [0])
        else:
            put((), "(0028,0002)", [1])
            put((), "(0028,0004)", ["MONOCHROME2"])
        put((), "(0028,0010)", [size])
        put((), "(0028,0011)", [size])
        if self.spec.sop_class not in (
            *_SEGMENTATIONS,
            ENHANCED_RT_IMAGE_STORAGE,
            ENHANCED_CONTINUOUS_RT_IMAGE_STORAGE,
        ):
            put((), "(0028,0030)", ["1", "1"])
        put((), "(0028,0100)", [bits])
        put((), "(0028,0101)", [bits])
        put((), "(0028,0102)", [bits - 1])
        put((), "(0028,0103)", [representation])
        put((), "(7FE0,0010)", [data])


def _written(dataset: pydicom.Dataset, spec: _Spec) -> bytes:
    """Return the instance written as a file in its transfer syntax."""
    meta = pydicom.dataset.FileMetaDataset()
    meta.MediaStorageSOPClassUID = pydicom.uid.UID(spec.sop_class)
    meta.MediaStorageSOPInstanceUID = pydicom.uid.UID(spec.sop_instance)
    meta.TransferSyntaxUID = pydicom.uid.UID(spec.transfer_syntax)
    meta.ImplementationClassUID = pydicom.uid.UID(IMPLEMENTATION_CLASS)
    meta.ImplementationVersionName = f"{MARKER_PREFIX}_CORPUS"
    dataset.file_meta = meta
    stream = io.BytesIO()
    pydicom.dcmwrite(stream, dataset, enforce_file_format=True)
    return stream.getvalue()
