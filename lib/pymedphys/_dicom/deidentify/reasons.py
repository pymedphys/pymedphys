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

"""The reason codes of the run and the transform, for every module that names them.

They are here, apart from :mod:`~pymedphys._dicom.deidentify.run` and
:mod:`~pymedphys._dicom.deidentify.instance_transform`, which re-export
them, so that :mod:`~pymedphys._dicom.deidentify.release_report` can name
them without importing either; and those of descriptor cleaning, which
:mod:`~pymedphys._dicom.deidentify.descriptor_cleaning` re-exports, since
it imports the QC pack, which imports the release report.
"""

from __future__ import annotations

import dataclasses
import enum

from .file_layout import ElementPath
from .roi_names import Reason


class RunReason(enum.Enum):
    """Why the run itself refused or sequestered an input."""

    # discovery
    SYMBOLIC_LINK = "symbolic-link"  # or another link, such as a junction
    NOT_A_REGULAR_FILE = "not-a-regular-file"
    DICOMDIR = "dicomdir"
    # the first pass
    UNREADABLE_FILE = "unreadable-file"  # the operating system cannot read it
    NOT_READABLE_AS_DICOM = "not-readable-as-dicom"
    UNREADABLE_SEQUENCE = "unreadable-sequence"
    # the second pass and after
    CHANGED_DURING_RUN = "changed-during-run"
    INVALID_OUTPUT_NAME = "invalid-output-name"
    SHARED_OUTPUT_NAME = "shared-output-name"
    STAGED_FILE_CHANGED = "staged-file-changed"
    # the reference graph's second pass found what was written at fault, or
    # could not record it to check
    INCONSISTENT_REFERENCES = "inconsistent-references"
    INVALID_REASON = "invalid-reason"
    INTERNAL_ERROR = "internal-error"


class TransformReason(enum.Enum):
    """Why the transform sequesters an instance, where no step's own reason does."""

    # an emptied or replaced element without a VR to write it with, or whose
    # new value does not fit it
    UNWRITABLE_ELEMENT = "unwritable-element"
    # no replacement Patient ID, Study, Series, or SOP Instance UID to name
    # the output by (D-016)
    UNNAMED_OUTPUT = "unnamed-output"
    # the output file cannot be read back as a source file
    UNREADABLE_OUTPUT = "unreadable-output"
    # the de-identification markers cannot be added to what the instance
    # already holds, such as a marker attribute read as UN (PS3.15 E.1.1)
    UNMARKABLE = "unmarkable"
    # an edit still to come when the output is written, such as a pseudonym
    # without the subject's identity
    PENDING_EDIT = "pending-edit"


class DescriptorReason(enum.Enum):
    """Why descriptor cleaning sequesters an instance."""

    # a ROI Name whose value could not be decoded
    UNDECODABLE_ROI_NAME = "undecodable-roi-name"
    # an attribute given C whose action without Clean Descriptors is still
    # to come, or under which the instance would be sequestered
    UNSETTLED_DESCRIPTOR = "unsettled-descriptor"


@dataclasses.dataclass(frozen=True)
class HeldRoiName:
    """A ROI Name held for review, by its path and reason, never its value."""

    path: ElementPath
    reason: Reason
