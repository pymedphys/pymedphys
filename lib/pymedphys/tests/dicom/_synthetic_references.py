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

"""Synthetic CT and RT instances that refer to each other, built in code.

:func:`collection` gives three CT slices, an RT Structure Set that references
them from its Referenced Frame of Reference Sequence and its ROI Contour
Sequence, an RT Plan that references the structure set and the dose, and an
RT Dose that references the plan and the structure set. Every instance UID is
invented under ``2.25.``, and the patient is fictitious. :func:`written_and_read`
writes an instance to a file in memory and reads it back.
"""

import io

from pymedphys._imports import pydicom

CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
MR_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.4"
RT_DOSE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.2"
RT_STRUCTURE_SET_STORAGE = "1.2.840.10008.5.1.4.1.1.481.3"
RT_PLAN_STORAGE = "1.2.840.10008.5.1.4.1.1.481.5"
ENCAPSULATED_PDF_STORAGE = "1.2.840.10008.5.1.4.1.1.104.1"
# SOP Classes of other service classes, which PS3.4 Table B.5-1 does not
# list. PS3.3 Sections 10.6.1 and C.8.8.5.4 give Detached Study Management, a
# retired SOP Class, in the Referenced Study Sequence and the RT Referenced
# Study Sequence.
DETACHED_STUDY_MANAGEMENT = "1.2.840.10008.3.1.2.3.1"
MODALITY_PERFORMED_PROCEDURE_STEP = "1.2.840.10008.3.1.2.3.3"
# Storage SOP Classes that Table B.5-1 does not list either: a Private SOP
# Class, invented under 2.25., and a retired one.
PRIVATE_SOP_CLASS = "2.25.700"
NM_IMAGE_STORAGE_RETIRED = "1.2.840.10008.5.1.4.1.1.5"
# A well-known SOP Instance of PS3.6 Table A-1.
HOT_IRON_COLOR_PALETTE = "1.2.840.10008.1.5.1"

STUDY = "2.25.100"
CT_SERIES = "2.25.200"
CT_SLICES = ("2.25.201", "2.25.202", "2.25.203")
STRUCTURE_SET_SERIES = "2.25.300"
STRUCTURE_SET = "2.25.301"
PLAN_SERIES = "2.25.400"
PLAN = "2.25.401"
DOSE_SERIES = "2.25.500"
DOSE = "2.25.501"
OTHER_SERIES = "2.25.600"
OTHER = "2.25.601"
PATIENT_ID = "SYNTHETIC-7Q2K"
PATIENTS_NAME = "FICTITIOUS^PERSON"

# The attributes, as tag paths, at which the collection's instances refer to
# each other.
RT_REFERENCED_STUDY = ("(3006,0010)", "(3006,0012)", "(0008,1155)")
RT_REFERENCED_SERIES = ("(3006,0010)", "(3006,0012)", "(3006,0014)", "(0020,000E)")
CONTOUR_IMAGES = (
    "(3006,0010)",
    "(3006,0012)",
    "(3006,0014)",
    "(3006,0016)",
    "(0008,1155)",
)
ROI_CONTOUR_IMAGES = ("(3006,0039)", "(3006,0040)", "(3006,0016)", "(0008,1155)")
REFERENCED_STRUCTURE_SET = ("(300C,0060)", "(0008,1155)")
REFERENCED_DOSE = ("(300C,0080)", "(0008,1155)")
REFERENCED_PLAN = ("(300C,0002)", "(0008,1155)")
REFERENCED_IMAGE = ("(0008,1140)", "(0008,1155)")
# Referenced SOP Instance UID names a study in these, as in the RT Referenced
# Study Sequence: the General Study module's, and each request's.
REFERENCED_STUDY = ("(0008,1110)", "(0008,1155)")
REQUESTED_REFERENCED_STUDY = ("(0040,0275)", "(0008,1110)", "(0008,1155)")
# Places where every definition in the IOD is Type 3.
REQUESTED_STUDY = ("(0040,0275)", "(0020,000D)")
PERTINENT_DOCUMENTS = ("(0044,0110)", "(0038,0100)", "(0008,1155)")
# RT Assertions Sequence, which pydicom 3.0.2 does not know.
RT_ASSERTIONS_SEQUENCE = 0x00440110


def uid(dataset, keyword, value):
    """Set a UI attribute without pydicom's checks, so that it can be padded."""
    tag = pydicom.datadict.tag_for_keyword(keyword)
    dataset[tag] = pydicom.DataElement(
        tag, "UI", value, validation_mode=pydicom.config.IGNORE
    )


def item(**attributes):
    """Return a sequence item with the attributes given by keyword."""
    dataset = pydicom.Dataset()
    for keyword, value in attributes.items():
        setattr(dataset, keyword, value)
    return dataset


def reference(sop_class, sop_instance):
    """Return an item that references an instance, with its SOP Class if given."""
    dataset = pydicom.Dataset()
    if sop_class is not None:
        uid(dataset, "ReferencedSOPClassUID", sop_class)
    uid(dataset, "ReferencedSOPInstanceUID", sop_instance)
    return dataset


def instance(sop_class, sop_instance, series, **sequences):
    """Return an instance of the study, with the sequences given by keyword."""
    dataset = pydicom.Dataset()
    dataset.PatientID = PATIENT_ID
    dataset.PatientName = PATIENTS_NAME
    if sop_class is not None:
        dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = sop_instance
    dataset.StudyInstanceUID = STUDY
    dataset.SeriesInstanceUID = series
    for keyword, items in sequences.items():
        setattr(dataset, keyword, items)
    return dataset


def sequence(tag, items):
    """Return a sequence element, which need not be in pydicom's dictionary."""
    return pydicom.DataElement(tag, "SQ", items)


def rt_assertions(*documents):
    """Return an RT Assertions Sequence whose item references ``documents``."""
    return sequence(
        RT_ASSERTIONS_SEQUENCE, [item(PertinentDocumentsSequence=list(documents))]
    )


def contour(sop_instance):
    """Return a Contour Sequence item on the CT slice ``sop_instance``."""
    return item(ContourImageSequence=[reference(CT_IMAGE_STORAGE, sop_instance)])


def ct_slice(number):
    return instance(CT_IMAGE_STORAGE, CT_SLICES[number], CT_SERIES)


def structure_set():
    contour_images = [reference(CT_IMAGE_STORAGE, slice_) for slice_ in CT_SLICES]
    return instance(
        RT_STRUCTURE_SET_STORAGE,
        STRUCTURE_SET,
        STRUCTURE_SET_SERIES,
        ReferencedFrameOfReferenceSequence=[
            item(
                RTReferencedStudySequence=[
                    item(
                        ReferencedSOPClassUID=DETACHED_STUDY_MANAGEMENT,
                        ReferencedSOPInstanceUID=STUDY,
                        RTReferencedSeriesSequence=[
                            item(
                                SeriesInstanceUID=CT_SERIES,
                                ContourImageSequence=contour_images,
                            )
                        ],
                    )
                ]
            )
        ],
        ROIContourSequence=[
            item(
                ReferencedROINumber=1,
                ContourSequence=[contour(slice_) for slice_ in CT_SLICES],
            )
        ],
    )


def rt_plan():
    return instance(
        RT_PLAN_STORAGE,
        PLAN,
        PLAN_SERIES,
        ReferencedStructureSetSequence=[
            reference(RT_STRUCTURE_SET_STORAGE, STRUCTURE_SET)
        ],
        ReferencedDoseSequence=[reference(RT_DOSE_STORAGE, DOSE)],
    )


def rt_dose():
    return instance(
        RT_DOSE_STORAGE,
        DOSE,
        DOSE_SERIES,
        ReferencedRTPlanSequence=[reference(RT_PLAN_STORAGE, PLAN)],
        ReferencedStructureSetSequence=[
            reference(RT_STRUCTURE_SET_STORAGE, STRUCTURE_SET)
        ],
    )


def collection():
    """Return the CT slices at positions 0 to 2, then the structure set, plan, and dose."""
    return [
        ct_slice(0),
        ct_slice(1),
        ct_slice(2),
        structure_set(),
        rt_plan(),
        rt_dose(),
    ]


def written_and_read(dataset, transfer_syntax):
    """Return ``dataset`` written in ``transfer_syntax`` and read back."""
    dataset.file_meta = pydicom.dataset.FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = transfer_syntax
    written = io.BytesIO()
    pydicom.dcmwrite(written, dataset, enforce_file_format=True)
    return pydicom.dcmread(io.BytesIO(written.getvalue()))
