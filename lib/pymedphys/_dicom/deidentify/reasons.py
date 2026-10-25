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
reason; and those of the readiness gates of a ``public-release`` run
(:mod:`~pymedphys._dicom.deidentify.readiness`), whose statistical gate's
module, :mod:`~pymedphys._dicom.deidentify.risk_assessment`, re-exports its
own, since it imports the release report.
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
    # compressed pixel data whose decoder is not installed, or cannot be run,
    # so its frames cannot be checked
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
    # whose overlay may lie in Pixel Data where it cannot be cleared: within
    # Bits Stored, in compressed Pixel Data, or otherwise than
    # pixel_cleaning.overlay_planes allows (D-041)
    OVERLAY_IN_PIXEL_DATA = "overlay-in-pixel-data"
    # under Clean Pixel Data, top-level Float Pixel Data or Double Float Pixel
    # Data, or Pixel Data that cannot be read as frames of stored values: a
    # layout other than whole bytes of 8, 16, or 32 bits with its High Bit one
    # less than Bits Stored, a photometric interpretation other than
    # MONOCHROME1, MONOCHROME2, or 8-bit RGB, or, compressed, 8-bit YBR_FULL,
    # YBR_FULL_422, YBR_ICT, or YBR_RCT, which decode to RGB, a length that
    # does not fit its frames, or bits above Bits Stored that hold more than
    # the value's sign once any overlay that an overlay group without Overlay
    # Data places there is cleared (D-037)
    UNCLEANABLE_PIXEL_DATA = "uncleanable-pixel-data"
    # under Clean Pixel Data, written Pixel Data that differs from its source
    # other than by the blacked-out regions (D-037), or reviewed regions in a
    # frame that the Pixel Data does not hold
    REDACTION_MISMATCH = "redaction-mismatch"
    # under Clean Pixel Data, an instance whose cleaned Pixel Data a reviewer
    # rejected in an attested QC pack, so that it is never released
    REDACTION_REJECTED = "redaction-rejected"
    # under tps-import, an instance of a subject whose instances in the run
    # contradict the reference study from which its profile's synthetic
    # birth date was derived, so that the subject is stopped for review
    # (D-008)
    BIRTH_DATE_CONFLICT = "birth-date-conflict"


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
    # verdict, the file is not one that the review saw, the reviewed run
    # held it beside a CT series that it defaced, so the verdict was of the
    # defaced images rather than of the file, or it holds a deformable
    # registration's grid, which no preview of the QC pack draws
    NO_FACE_VERDICT = "no-face-verdict"
    # its series is marked absent, but the run writes other pixel data of it
    # than the reviewed run did, such as a CT slice defaced since the
    # reviewer saw it as received, so the verdict is not of what it releases
    OTHER_PIXEL_DATA = "face-verdict-on-other-pixel-data"
    # its series is marked absent, but the run writes other contours of it
    # than the reviewed run did, such as a structure set cut by a face block
    # that the reviewed run did not find, so the verdict is not of what it
    # releases
    OTHER_CONTOURS = "face-verdict-on-other-contours"
    # an RT Dose in the Frame of Reference of a CT series that the run
    # defaces, whose dose in the series' face block is too great to set to
    # zero there, so that it is written as received
    DOSE_IN_FACE_BLOCK = "dose-in-face-block"
    # an RT Structure Set, RT Dose, or PET instance in the Frame of
    # Reference of a CT series that the run defaces, whose outline or pixel
    # data the run does not clean of the face, such as one in other frames
    # too or that cannot be cut, and which a reviewer may have judged from
    # the defaced CT
    UNDEFACED_IN_DEFACED_FRAME = "undefaced-in-defaced-frame"
    # a CT slice of a series whose face block a target may reach, so that
    # the series is not defaced
    TARGET_IN_FACE_BLOCK = "target-in-face-block"
    # a CT slice of a series whose structure set draws an eye away from the
    # globes that its face block was found from, so that the series is not
    # defaced
    EYES_DISAGREE_WITH_ROIS = "eyes-disagree-with-rois"


@dataclasses.dataclass(frozen=True)
class HeldVisualFeatures:
    """An instance held for review because it does not satisfy the option."""

    reason: VisualFeaturesReason

    def __post_init__(self) -> None:
        if not isinstance(self.reason, VisualFeaturesReason):
            raise TypeError("a held instance's visual features need their reason")


class StatisticalReason(enum.Enum):
    """Why the statistical gate failed, as a release report records it (D-053)."""

    # no assessment was given
    NO_ASSESSMENT = "no-assessment"
    # the assessment is of other source files
    OTHER_COLLECTION = "other-collection"
    # the assessment is of another policy, or of another engine
    OTHER_POLICY = "other-policy"
    # the assessment is of other reviewed ROI names or descriptors lists
    OTHER_LISTS = "other-lists"
    # the assessment counts fewer subjects than the run releases
    FEWER_SUBJECTS = "fewer-subjects"
    # the assessment counts more subjects than the run releases, as an
    # assessment that counted images, frames, or visits would
    MORE_SUBJECTS = "more-subjects"
    # the maximum per-subject probability is above the threshold
    ABOVE_THRESHOLD = "above-threshold"


class ReviewReason(enum.Enum):
    """Why a readiness gate that rests on a reviewed QC pack failed.

    The pixel and face gate and the attestation gate of a ``public-release``
    run each read the QC pack of an earlier run of the collection, which a
    reviewer attested (D-017); some reasons are of one gate alone.
    """

    # the run was given no reviewed QC pack
    NO_REVIEW = "no-review"
    # no reviewer has attested to the reviewed pack
    NOT_ATTESTED = "not-attested"
    # the reviewer rejected it
    REJECTED = "rejected"
    # the reviewed pack is of other source files
    OTHER_COLLECTION = "other-collection"
    # the reviewed run had another policy, or another engine, so what the
    # reviewer saw is not what this run writes
    OTHER_POLICY = "other-policy"
    # the attestation gate: the releaser did not confirm in the attestation
    # that the output's residual risk was accepted
    RESIDUAL_RISK_NOT_ACCEPTED = "residual-risk-not-accepted"
    # the attestation gate: the run releases an instance that the reviewed
    # run neither released nor held, so that no series preview showed it
    UNREVIEWED_INSTANCE = "unreviewed-instance"
    # the attestation gate: the run releases a retained string that the
    # reviewed pack does not list
    UNREVIEWED_RETAINED_STRING = "unreviewed-retained-string"
    # the pixel and face gate: the run releases an instance in a high-risk
    # category that the reviewed pack did not list as one, released or held
    UNREVIEWED_HIGH_RISK = "unreviewed-high-risk-instance"
    # the pixel and face gate, for an instance that the run releases that
    # can show a face, without an assessment that covers faces: the
    # reviewer saw a recognisable face in its series' previews
    FACE_PRESENT = VisualFeaturesReason.FACE_PRESENT.value
    # no verdict of absent covers its source file
    NO_FACE_VERDICT = VisualFeaturesReason.NO_FACE_VERDICT.value
    # its series is marked absent, but the run writes pixel data of it that
    # the reviewed run's previews did not show in every frame
    OTHER_PIXEL_DATA = VisualFeaturesReason.OTHER_PIXEL_DATA.value
    # its series is marked absent, but the run writes contours of it that
    # the reviewed run's contour sheet did not show
    OTHER_CONTOURS = VisualFeaturesReason.OTHER_CONTOURS.value
