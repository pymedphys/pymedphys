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
it imports the QC pack, which imports the release report; and those of the
face review (:mod:`~pymedphys._dicom.deidentify.face_review`), for the same
reason.
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
    # the output by (D-016), or, for a UID that the policy keeps, no valid
    # UID to write and name it by (D-040)
    UNNAMED_OUTPUT = "unnamed-output"
    # the output file cannot be read back as a source file
    UNREADABLE_OUTPUT = "unreadable-output"
    # the de-identification markers cannot be added to what the instance
    # already holds, such as a marker attribute read as UN (PS3.15 E.1.1)
    UNMARKABLE = "unmarkable"
    # a value that the plan keeps as it is cannot be decoded for D-017's
    # review of every retained string, such as text outside ISO 646 where no
    # Specific Character Set applies
    UNREVIEWABLE_RETAINED_TEXT = "unreviewable-retained-text"
    # an edit still to come when the output is written, such as a pseudonym
    # without the subject's identity
    PENDING_EDIT = "pending-edit"
    # the output no longer holds, or holds empty, an attribute that the IOD
    # requires where its source held it (MIDI-BP-03)
    REQUIRED_ATTRIBUTE_LOST = "required-attribute-lost"
    # compressed pixel data whose decoder is not installed, so its frames
    # cannot be checked
    NO_DECODER = "no-decoder"
    # compressed pixel data whose Basic or Extended Offset Table does not give
    # where its frames start (PS3.5 Section A.4)
    OFFSET_TABLE_MISMATCH = "offset-table-mismatch"
    # compressed pixel data with a frame that does not decode, or whose
    # codestream has no header that its transfer syntax allows
    UNDECODABLE_PIXEL_DATA = "undecodable-pixel-data"
    # compressed pixel data whose frames, or their codestream headers, do
    # not match Number of Frames, Rows, Columns, Samples per Pixel, or Bits
    # Stored
    FRAME_MISMATCH = "frame-mismatch"
    # compressed pixel data with a frame that cannot be found or parsed, or
    # that holds bytes outside its codestream other than padding
    UNPARSABLE_CODESTREAM = "unparsable-codestream"
    # compressed pixel data with a metadata segment that could be cut only by
    # changing other values, such as a tile-part's length or an Extended
    # Offset Table
    UNCUTTABLE_METADATA = "uncuttable-metadata"
    # compressed pixel data whose frames, with metadata segments cut, do not
    # decode to the same pixels as before
    CUT_CHANGED_PIXELS = "cut-changed-pixels"
    # under Clean Graphics, an overlay group without Overlay Data (60xx,3000),
    # whose overlay may lie in unused bits of Pixel Data, which the engine
    # does not change
    OVERLAY_IN_PIXEL_DATA = "overlay-in-pixel-data"
    # under Clean Pixel Data, compressed Pixel Data, which the engine does not
    # yet black out (D-037)
    COMPRESSED_PIXEL_DATA = "compressed-pixel-data"
    # under Clean Pixel Data, top-level Float Pixel Data or Double Float Pixel
    # Data, or native Pixel Data that cannot be read as frames of stored
    # values: a layout other than whole bytes of 8, 16, or 32 bits with its
    # High Bit one less than Bits Stored, a photometric interpretation other
    # than MONOCHROME1, MONOCHROME2, or 8-bit RGB, a length that does not fit
    # its frames, or bits above Bits Stored that hold more than the value's
    # sign, such as an overlay (D-037)
    UNCLEANABLE_PIXEL_DATA = "uncleanable-pixel-data"
    # under Clean Pixel Data, written Pixel Data that differs from its source
    # other than by the blacked-out regions (D-037)
    REDACTION_MISMATCH = "redaction-mismatch"


class DescriptorReason(enum.Enum):
    """Why descriptor cleaning sequesters an instance."""

    # a ROI Name whose value could not be decoded
    UNDECODABLE_ROI_NAME = "undecodable-roi-name"
    # an attribute given C whose action without Clean Descriptors is still
    # to come, or under which the instance would be sequestered
    UNSETTLED_DESCRIPTOR = "unsettled-descriptor"


class PixelDataReason(enum.Enum):
    """Why a pixel option holds an instance for review."""

    # Clean Pixel Data blacked out text that the detector found; review
    # checks the regions and looks for text that it missed (D-037)
    TEXT_BLACKED_OUT = "text-blacked-out"
    # Clean Pixel Data's detector found no text; review looks for text that
    # it missed (D-037)
    NO_TEXT_FOUND = "no-text-found"


@dataclasses.dataclass(frozen=True)
class HeldRoiName:
    """A ROI Name held for review, by its path and reason, never its value."""

    path: ElementPath
    reason: Reason


@dataclasses.dataclass(frozen=True)
class HeldPixelData:
    """An instance held for review because its pixel data await review."""

    reason: PixelDataReason

    def __post_init__(self) -> None:
        if not isinstance(self.reason, PixelDataReason):
            raise TypeError("a held instance's pixel data need their reason")


class VisualFeaturesReason(enum.Enum):
    """Why an instance that can show a face does not satisfy the option.

    The Clean Recognizable Visual Features Option, under which such an
    instance is held for review.
    """

    # the reviewer saw a recognisable face in its series' previews
    FACE_PRESENT = "face-present"
    # no reviewer's verdict covers its source file: its series has no
    # verdict, or the file is not one that the review saw
    NO_FACE_VERDICT = "no-face-verdict"
    # its series is marked absent, but the run writes other pixel data of it
    # than the reviewed run did, such as a CT slice defaced since the
    # reviewer saw it as received, so the verdict is not of what it releases
    OTHER_PIXEL_DATA = "face-verdict-on-other-pixel-data"
    # a CT slice of a series whose face block holds a point of a target's
    # contour, so that the series is not defaced
    TARGET_IN_FACE_BLOCK = "target-in-face-block"


@dataclasses.dataclass(frozen=True)
class HeldVisualFeatures:
    """An instance held for review because it does not satisfy the option."""

    reason: VisualFeaturesReason

    def __post_init__(self) -> None:
        if not isinstance(self.reason, VisualFeaturesReason):
            raise TypeError("a held instance's visual features need their reason")
