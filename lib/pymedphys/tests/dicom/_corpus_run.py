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

"""A policy run over the synthetic corpus, and what the run must do.

The end-to-end tests (``test_deidentify_corpus_end_to_end.py``) and the
independent validators' tests (``test_deidentify_dicom_validation_corpus.py``)
each run the engine over the synthetic corpus once for each
:class:`CorpusRun` in :data:`~pymedphys.tests.dicom.corpus_runs.CORPUS_RUNS`,
in a module-scoped fixture. A run is a policy, either a preset or a custom
option set, with its inputs and what it must do: which instances it
withholds and why, which planted markers it keeps, which CID 7050 codes its
released instances claim, and the names its released structure set gives
its ROIs.

Each run is a module of its own in :mod:`pymedphys.tests.dicom.corpus_runs`,
and each option joins as one new module once the engine applies it, so that
a pull request adds one corpus run to each test module, no fixture, and no
line that another option's pull request also changes. What follows from the standard is derived here from PS3.15, not
from the engine's composition of the policy: the markers kept are those in
the rows of Table E.1-1 that the selected options keep (action K), the codes
are CID 7050's, and Longitudinal Temporal Information Modified follows
E.2 and E.3.6. An entry overrides an expectation only where the standard
leaves its value to the engine, such as a cleaner's output, and says why.
"""

import contextlib
import dataclasses
import functools
import hashlib
import io
import types
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from pymedphys._imports import pydicom, pytest

from pymedphys._nomenclature import tg263

from pymedphys._dicom.deidentify import (
    dummy_values,
    pixel_decoding,
    roi_names,
    run,
    standard,
    structured_content,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.face_review import (
    FaceReview,
    contour_data_sha256,
    pixel_data_sha256,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.pixel_cleaning import TextFinder
from pymedphys._dicom.deidentify.redaction_review import RedactionReview
from pymedphys._dicom.deidentify.policy import (
    PRESETS,
    Policy,
    compose_custom_policy,
    compose_policy,
)
from pymedphys._dicom.deidentify.release_gate import (
    Decision,
    ReasonCode,
    ReleaseReason,
)
from pymedphys._dicom.deidentify.reviewed_roi_names import (
    Review,
    ReviewedName,
    ReviewedNames,
)
from pymedphys._dicom.deidentify.source import SourceRefused, read_source
from pymedphys._dicom.deidentify.text_detection import TextBox
from pymedphys._dicom.deidentify.walker import SequesterReason, Sequestration

from . import _synthetic_compressed as compressed

KEY = DeidKey(bytes(range(32)))
# An invented reference of a QC pack.
FACE_REVIEW_REFERENCE = "A-" + "0123456789abcdef" * 2
# An invented reference of the QC pack whose redaction verdicts a run applies.
REDACTION_REVIEW_REFERENCE = "A-" + "fedcba9876543210" * 2
# The region that a reviewed Clean Pixel Data run blacks out in every frame:
# the top left corner, one row by two columns, which lies within every frame
# of the corpus, each two by two pixels, since a reviewed region past its
# frame refuses the instance, and leaves the frame's second row as it was.
CORNER = TextBox(0, 0, 1, 2)

# The CID 7050 code of the Basic Application Level Confidentiality Profile
# and of each option of Table E.1-1 (PS3.16 CID 7050), written out here
# rather than read from the engine, and their Coding Scheme Designator.
DCM = "DCM"
BASIC_PROFILE_CODE = "113100"
OPTION_CODES: Mapping[str, str] = types.MappingProxyType(
    {
        "retain_safe_private": "113111",
        "retain_uids": "113110",
        "retain_device_identity": "113109",
        "retain_institution_identity": "113112",
        "retain_patient_characteristics": "113108",
        "retain_longitudinal_full_dates": "113106",
        "retain_longitudinal_modified_dates": "113107",
        "clean_descriptors": "113105",
        "clean_structured_content": "113104",
        "clean_graphics": "113103",
    }
)
# The codes of the pixel options, which Table E.1-1 does not list.
PIXEL_OPTION_CODES: Mapping[str, str] = types.MappingProxyType(
    {
        "clean_pixel_data": "113101",
        "clean_recognizable_visual_features": "113102",
    }
)
FULL_DATES = "retain_longitudinal_full_dates"
MODIFIED_DATES = "retain_longitudinal_modified_dates"
CLEAN_STRUCTURED_CONTENT = "clean_structured_content"
CONTENT_SEQUENCE = "(0040,A730)"
CLEAN_RECOGNIZABLE_VISUAL_FEATURES = "clean_recognizable_visual_features"

# The generic parts of every marker.
MARKER_SIGNATURES = (
    corpus_module.MARKER_PREFIX,
    corpus_module.MARKER_UID_ROOT,
    corpus_module.LINKED_UID_ROOT,
    ".424242",
    "MARKER",
    "synmk.invalid",
)

CLEAN_DESCRIPTORS = "basic-clean-descriptors"
# The basic preset over the corpus with its images compressed, and text
# planted in their codestreams' metadata segments.
COMPRESSED = "basic-compressed"
ROI_SEQUENCE = "(3006,0020)"
ROI_NAME = "(3006,0026)"
REFERENCED_FRAME_OF_REFERENCE = "(3006,0024)"
# The second ROI's name, which the automatic tier renames, and what it and
# the reviewer write.
UNCLEANED_NAME = "lung l"
VOCABULARY_NAME = "Lung_L"
MAPPED_NAME = "GTV_Primary"
VOCABULARY = tg263.Nomenclature(
    source=tg263.Source(file="invented.xls", sha256="0" * 64, sheet="Invented"),
    attribution=tg263.ATTRIBUTION,
    structures=(
        tg263.Structure(
            target_type="Anatomic",
            major_category="Invented",
            minor_category="",
            anatomic_group="",
            primary_name=VOCABULARY_NAME,
            reverse_order_name="L_Lung",
            description="",
            fma_id=None,
        ),
    ),
)


@contextlib.contextmanager
def published_vocabulary() -> Iterator[None]:
    """Treat the invented vocabulary as a published edition, so nothing is downloaded."""
    entries = [dataclasses.asdict(s) for s in VOCABULARY.structures]
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(
            roi_names.PUBLISHED_TG263, "TG263 vInvented", tg263.content_sha256(entries)
        )
        yield


def reason_key(reason: object) -> object:
    """Return what a run's reason for withholding an instance is compared by.

    A walker's sequestration by its path and reason, a release gate's reason
    by its decision, code, and path, and any other reason as itself.
    """
    if isinstance(reason, Sequestration):
        return (reason.path, reason.reason)
    if isinstance(reason, ReleaseReason):
        return (reason.decision, reason.code, reason.path)
    return reason


@dataclasses.dataclass(frozen=True)
class Withheld:
    """An instance a run must withhold, and why.

    Attributes
    ----------
    status : run.Status
        :attr:`run.Status.SEQUESTERED` or :attr:`run.Status.HELD_FOR_REVIEW`.
    reasons : frozenset
        Every reason of the instance's outcome, each as :func:`reason_key`
        gives it.
    """

    status: run.Status
    reasons: frozenset


def sequestered(reason: SequesterReason, *tags: str) -> Withheld:
    """Return a walker's sequestration of the top-level attributes ``tags``."""
    return Withheld(
        run.Status.SEQUESTERED,
        frozenset((ElementPath((), tag), reason) for tag in tags),
    )


def held(decision: Decision, code: ReasonCode, *tags: str) -> Withheld:
    """Return the release gate's hold of the top-level attributes ``tags``."""
    return Withheld(
        run.Status.HELD_FOR_REVIEW,
        frozenset((decision, code, ElementPath((), tag)) for tag in tags),
    )


# What every run of the corpus withholds under the Basic Profile: the
# instance whose Responsible Person and Responsible Organization its IOD
# requires (Type 1C), which the profile removes, the RT Dose that holds the
# plan's RT Plan Label in its Manufacturer's Model Name, which the residual
# search finds, and each Structured Report, whose Content Sequence the
# profile gives D, which a sequence has no dummy value for (D-021).
BASIC_WITHHELD: Mapping[str, Withheld] = types.MappingProxyType(
    {
        corpus_module.SEQUESTERED_FILE: sequestered(
            SequesterReason.REQUIRED_BY_IOD, "(0010,2297)", "(0010,2299)"
        ),
        corpus_module.REVIEW_FILE: held(
            Decision.QC_REVIEW, ReasonCode.RESIDUAL_TEXT, "(300A,0002)"
        ),
        **dict.fromkeys(
            corpus_module.STRUCTURED_REPORT_FILES,
            sequestered(SequesterReason.NO_DUMMY_VALUE, CONTENT_SEQUENCE),
        ),
    }
)


@functools.cache
def _rows() -> tuple[standard.ProfileAttribute, ...]:
    return standard.load_table_e1_1().attributes


@functools.cache
def _listed() -> frozenset[str]:
    return frozenset(row.tag for row in _rows())


@functools.cache
def kept_rows(options: tuple[str, ...]) -> frozenset[str]:
    """Return the tags of the rows of Table E.1-1 that the options keep.

    A row is kept when every selected option that gives it an action gives
    K. Where options give a row different actions, a custom option set is
    refused, and ``tps-import`` applies Modified Dates' C, so the row is not
    kept.
    """
    kept = set()
    for row in _rows():
        actions = {row.options[o] for o in options if o in row.options}
        if actions == {"K"}:
            kept.add(row.tag)
    return frozenset(kept)


@functools.cache
def kept_concepts(options: tuple[str, ...]) -> frozenset[tuple[str, str, str]]:
    """Return the keys of the rows of Table E.3.4-1 that the options keep.

    A content item's concept name is kept, as :func:`kept_rows` keeps a row
    of Table E.1-1, when every selected option that gives it an action
    gives K. Each key is the row's Coding Scheme Designator, Code Value, and
    Value Type, as a content item's placement records its concept name.
    """
    kept = set()
    for concept in structured_content.load_table_e3_4_1().concepts:
        actions = {concept.options[o] for o in options if o in concept.options}
        if actions == {"K"}:
            kept.add(concept.key)
    return frozenset(kept)


@functools.cache
def _content_item_sequences() -> frozenset[str]:
    """The sequences to which Clean Structured Content gives C."""
    return frozenset(
        row.tag for row in _rows() if row.options.get(CLEAN_STRUCTURED_CONTENT) == "C"
    )


def removed_rows(options: tuple[str, ...]) -> frozenset[str]:
    """Return the tags of the rows of Table E.1-1 removed under the options.

    Those whose Basic Profile action is X and to which no selected option
    gives an action, since an option's action is K or C.
    """
    return frozenset(
        row.tag
        for row in _rows()
        if row.basic_profile == "X" and not any(o in row.options for o in options)
    )


def temporal_value(options: tuple[str, ...]) -> str:
    """Return Longitudinal Temporal Information Modified under the options.

    UNMODIFIED under Full Dates and MODIFIED under Modified Dates (PS3.15
    E.3.6), and otherwise REMOVED (E.2).
    """
    if FULL_DATES in options:
        return "UNMODIFIED"
    return "MODIFIED" if MODIFIED_DATES in options else "REMOVED"


def _unchanged(
    corpus: corpus_module.SyntheticCorpus,
) -> corpus_module.SyntheticCorpus:
    return corpus


def without_reports(
    corpus: corpus_module.SyntheticCorpus,
) -> corpus_module.SyntheticCorpus:
    """Return the corpus without its Structured Reports, which no file references."""
    return dataclasses.replace(
        corpus,
        files=tuple(
            file
            for file in corpus.files
            if file.name not in corpus_module.STRUCTURED_REPORT_FILES
        ),
    )


# BASIC_WITHHELD without the Structured Reports, for a run whose corpus has
# none.
WITHHELD_WITHOUT_REPORTS: Mapping[str, Withheld] = types.MappingProxyType(
    {
        name: withheld
        for name, withheld in BASIC_WITHHELD.items()
        if name not in corpus_module.STRUCTURED_REPORT_FILES
    }
)

# Accession Number (0008,0050) and Referenced Study Sequence (0008,1110),
# which dcentvfy's own tables place in the Study entity for a Structured
# Report and in the Series entity for an image, whatever the files hold.
# dcentvfy finds that difference wherever a report is released with an
# image, in their inputs as often.
REPORT_ENTITIES = frozenset({"(0008,0050)", "(0008,1110)"})


@dataclasses.dataclass(frozen=True)
class CorpusRun:
    """A policy run over the synthetic corpus, with what the run must do.

    Attributes
    ----------
    name : str
        The test ID, and the name of the run's validation report directory,
        such as ``"basic"``. A preset's own run takes the preset's name.
    preset : str or None
        The preset, composed with
        :func:`~pymedphys._dicom.deidentify.policy.compose_policy`; or None
        for the custom option set ``options``.
    options : tuple of str
        A custom option set, composed with
        :func:`~pymedphys._dicom.deidentify.policy.compose_custom_policy`;
        empty with a preset.
    corpus : callable
        Returns the variant of the synthetic corpus to run over, given it.
    reviewed_roi_names : callable or None
        Returns the reviewed-names list for the corpus it is given, to clean
        ROI Names with the invented vocabulary; or None to run without
        descriptor cleaning.
    finder : TextFinder or None
        What finds text in each frame under Clean Pixel Data; or None for a
        run without that option.
    face_review : callable or None
        Returns the face review of the corpus it is given, for a run under
        Clean Recognizable Visual Features; or None for any other run.
    redaction_review : callable or None
        Returns the redaction review of the corpus it is given, for a run
        under Clean Pixel Data; or None for a run without one.
    withheld : Mapping of str to Withheld
        Each instance the run must withhold, by its file name in the
        corpus. Every other instance must be released.
    kept : frozenset of str or None
        The rows of Table E.1-1, by tag, whose planted markers the run must
        keep at their place in every released instance, where no sequence
        that holds them is removed (:meth:`keeps`), and which no other
        released place may hold. None for the rows that the selected options
        keep (:func:`kept_rows`).
    codes : frozenset of str or None
        The CID 7050 code values that every released instance claims. None
        for the Basic Profile's and each selected option's.
    roi_names : tuple of str or None
        The ROI Names of the released structure set, in order; or None where
        the run withholds it.
    inconsistent : frozenset of str
        The attributes, by tag, whose differing values among one patient's
        instances, which the corpus plants, the run keeps or modifies alike,
        so that dcentvfy finds each of them in the released instances as
        often as in their inputs. The Basic Profile removes or replaces
        every such value alike, so by default there are none. They include
        :data:`REPORT_ENTITIES` where the run releases a Structured Report.
    kept_content : frozenset of str
        The sequences of Table E.1-1, by tag, whose content items Clean
        Structured Content cleans, and which the engine keeps, since the
        run's corpus makes every item one it can clean (D-047). The elements
        of their items take their own actions, so a marker in one is kept
        where its row is. Every other sequence that the option gives C may be
        removed or emptied, as the engine does where an item cannot be
        cleaned, so nothing in it is kept. Empty without the option.
    marks : tuple
        pytest marks of the run's parameter, such as a skip.
    """

    name: str
    preset: str | None = None
    options: tuple[str, ...] = ()
    corpus: Callable[[corpus_module.SyntheticCorpus], corpus_module.SyntheticCorpus] = (
        _unchanged
    )
    reviewed_roi_names: (
        Callable[[corpus_module.SyntheticCorpus], ReviewedNames] | None
    ) = None
    finder: TextFinder | None = None
    face_review: Callable[[corpus_module.SyntheticCorpus], FaceReview] | None = None
    redaction_review: (
        Callable[[corpus_module.SyntheticCorpus], RedactionReview] | None
    ) = None
    withheld: Mapping[str, Withheld] = BASIC_WITHHELD
    kept: frozenset[str] | None = None
    codes: frozenset[str] | None = None
    roi_names: tuple[str, ...] | None = ("",)
    inconsistent: frozenset[str] = frozenset()
    kept_content: frozenset[str] = frozenset()
    marks: tuple = ()

    def __post_init__(self):
        if isinstance(self.options, str):
            raise TypeError("options must be a tuple of option names")
        if self.preset is not None and self.options:
            raise ValueError(f"{self.name}: give a preset or options, not both")
        if self.kept_content and CLEAN_STRUCTURED_CONTENT not in self.selected:
            raise ValueError(
                f"{self.name}: kept_content needs Clean Structured Content"
            )
        if not self.kept_content <= _content_item_sequences():
            raise ValueError(
                f"{self.name}: kept_content names no sequence of content items"
            )

    @property
    def selected(self) -> tuple[str, ...]:
        """The selected options, the preset's or the custom option set."""
        return PRESETS[self.preset] if self.preset is not None else self.options

    def policy(self) -> Policy:
        """Compose the run's policy."""
        if self.preset is not None:
            return compose_policy(self.preset)
        return compose_custom_policy(self.options)

    def kept_rows(self) -> frozenset[str]:
        """The rows whose planted markers the run keeps (:attr:`kept`)."""
        return kept_rows(self.selected) if self.kept is None else self.kept

    def keeps(self, placement: corpus_module.Placement) -> bool:
        """Whether the run keeps a placement's marker at its place.

        Its row must be kept (:meth:`kept_rows`), or, for the value of a
        content item, the row of Table E.3.4-1 of its concept name
        (:func:`kept_concepts`), and so must every sequence of Table E.1-1
        that holds it, since a sequence's other actions remove, empty,
        replace, or clean what it holds; but a sequence whose content items
        the run cleans and keeps (:attr:`kept_content`) keeps what its
        items' own actions keep, and so does Verifying Observer Sequence
        for the attributes of its items that its reviewed D keeps
        (:data:`~pymedphys._dicom.deidentify.dummy_values.KEPT_ITEM_ATTRIBUTES`).
        """
        kept = self.kept_rows()
        passed = kept | self.kept_content
        if placement.concept is not None:
            own = placement.concept in kept_concepts(self.selected)
        else:
            own = placement.profile_tag in kept
        tags = [tag for tag, _ in placement.path.items]
        inner = [*tags[1:], placement.path.tag]
        return own and all(
            tag in passed
            or tag not in _listed()
            or held in dummy_values.KEPT_ITEM_ATTRIBUTES.get(tag, ())
            for tag, held in zip(tags, inner)
        )

    def method_codes(self) -> frozenset[tuple[str, str]]:
        """The codes every released instance claims, with their designator."""
        values = (
            {
                BASIC_PROFILE_CODE,
                *({**OPTION_CODES, **PIXEL_OPTION_CODES}[o] for o in self.selected),
            }
            if self.codes is None
            else self.codes
        )
        return frozenset((value, DCM) for value in values)

    def temporal_value(self) -> str:
        """Longitudinal Temporal Information Modified under the run's options."""
        return temporal_value(self.selected)

    def param(self) -> Any:
        """The run as a pytest parameter."""
        return pytest.param(self, id=self.name, marks=self.marks)


@dataclasses.dataclass(frozen=True)
class Prepared:
    """A run's corpus, what its transform cleans descriptors and finds text
    with, and its face and redaction reviews."""

    corpus: corpus_module.SyntheticCorpus
    reviewed: ReviewedNames | None
    cleaning: DescriptorCleaning | None
    finder: TextFinder | None = None
    face_review: FaceReview | None = None
    redaction_review: RedactionReview | None = None

    def transform(self, policy: Policy) -> InstanceTransform:
        """The run's instance transform, which applies a policy not yet enabled."""
        return InstanceTransform(
            policy,
            KEY,
            cleaning=self.cleaning,
            finder=self.finder,
            face_review=self.face_review,
            redaction_review=self.redaction_review,
            unvalidated_policy=True,
        )


def prepare(corpus_run: CorpusRun) -> Prepared:
    """Build the corpus a run is over, its reviewed-names list, its finder, and
    its face and redaction reviews."""
    corpus = corpus_run.corpus(corpus_module.build_corpus())
    faces = None if corpus_run.face_review is None else corpus_run.face_review(corpus)
    redactions = (
        None
        if corpus_run.redaction_review is None
        else corpus_run.redaction_review(corpus)
    )
    reviewed = (
        None
        if corpus_run.reviewed_roi_names is None
        else corpus_run.reviewed_roi_names(corpus)
    )
    return Prepared(
        corpus,
        reviewed,
        None if reviewed is None else DescriptorCleaning(VOCABULARY, reviewed),
        finder=corpus_run.finder,
        face_review=faces,
        redaction_review=redactions,
    )


def structure_set(corpus: corpus_module.SyntheticCorpus) -> corpus_module.CorpusFile:
    (file,) = [file for file in corpus.files if file.manifest.iod == "RT Structure Set"]
    return file


def planted_roi_name(corpus: corpus_module.SyntheticCorpus) -> str:
    (placement,) = [
        placement
        for placement in structure_set(corpus).manifest.placements
        if placement.path.tag == ROI_NAME
    ]
    return placement.values[0]


def with_a_second_roi(
    corpus: corpus_module.SyntheticCorpus,
) -> corpus_module.SyntheticCorpus:
    """Return the corpus with a second ROI, named for the automatic tier.

    pydicom writes the structure set again, which keeps every planted value.
    The second ROI references the first's frame of reference, whose linked
    UID it copies, so the manifest records the copy as a placement too: an
    option that keeps the UID, such as Retain UIDs, keeps it at both places.
    """
    file = structure_set(corpus)
    dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(file.data))
    first = dataset.StructureSetROISequence[0]
    item = pydicom.Dataset()
    item.ROINumber = max(each.ROINumber for each in dataset.StructureSetROISequence) + 1
    item.ReferencedFrameOfReferenceUID = first.ReferencedFrameOfReferenceUID
    item.ROIName = UNCLEANED_NAME
    item.ROIGenerationAlgorithm = "MANUAL"
    dataset.StructureSetROISequence.append(item)
    buffer = pydicom.filebase.DicomBytesIO()
    dataset.save_as(buffer, enforce_file_format=True)
    first_reference = ElementPath(((ROI_SEQUENCE, 0),), REFERENCED_FRAME_OF_REFERENCE)
    copied = ElementPath(
        ((ROI_SEQUENCE, len(dataset.StructureSetROISequence) - 1),),
        REFERENCED_FRAME_OF_REFERENCE,
    )
    manifest = dataclasses.replace(
        file.manifest,
        placements=(
            *file.manifest.placements,
            *(
                dataclasses.replace(placement, path=copied)
                for placement in file.manifest.placements
                if placement.path == first_reference
            ),
        ),
    )
    replaced = dataclasses.replace(file, data=buffer.getvalue(), manifest=manifest)
    return dataclasses.replace(
        corpus,
        files=tuple(replaced if each is file else each for each in corpus.files),
    )


def mapped_planted_name(corpus: corpus_module.SyntheticCorpus) -> ReviewedNames:
    """Return a reviewed-names list that maps the planted ROI Name."""
    reviewed = ReviewedNames.empty()
    reviewed.record(planted_roi_name(corpus), ReviewedName(Review.MAP, MAPPED_NAME))
    return reviewed


def decoders_installed() -> bool:
    """Whether a decoding plugin of every syntax of the compressed corpus is installed."""
    return all(
        pixel_decoding.decoder_available(syntax)
        for syntax in compressed.CORPUS_SYNTAXES
    )


# A face review with no verdicts, as the first run of a collection under
# Clean Recognizable Visual Features is given, which holds every instance
# that can show a face.
NO_FACE_VERDICTS = FaceReview(
    FACE_REVIEW_REFERENCE, frozenset(), frozenset(), frozenset(), frozenset()
)


def face_review_for(composed: Policy) -> FaceReview | None:
    """Return :data:`NO_FACE_VERDICTS` where the policy selects Clean
    Recognizable Visual Features, whose transform needs a face review, as
    ``public-release`` does, or None for any other policy."""
    return (
        NO_FACE_VERDICTS
        if CLEAN_RECOGNIZABLE_VISUAL_FEATURES in composed.options
        else None
    )


def every_face_absent(corpus: corpus_module.SyntheticCorpus) -> FaceReview:
    """Return a face review that marks every file of the corpus free of a face.

    It is matched by each file's SHA-256, and the SHA-256 of the pixel data
    and contours that a run writes of it unchanged, as an attested review's
    verdicts are, and gives each RT Dose's every frame as shown by its dose
    levels, so each instance that can show a face, and whose pixel data and
    contours the run does not change, satisfies the option.
    """
    digests = frozenset(hashlib.sha256(file.data).digest() for file in corpus.files)
    pixels = frozenset(
        (hashlib.sha256(file.data).digest(), digest)
        for file in corpus.files
        if (digest := _written_sha256(pixel_data_sha256, file.data)) is not None
    )
    doses = frozenset(
        (hashlib.sha256(file.data).digest(), digest, int(frames))
        for file in corpus.files
        if (dataset := pydicom.dcmread(io.BytesIO(file.data))).get("Modality")
        == "RTDOSE"
        and (frames := dataset.get("NumberOfFrames") or 1)
        and (digest := _written_sha256(pixel_data_sha256, file.data)) is not None
    )
    contours = frozenset(
        (hashlib.sha256(file.data).digest(), digest)
        for file in corpus.files
        if (digest := _written_sha256(contour_data_sha256, file.data)) is not None
    )
    return FaceReview(
        FACE_REVIEW_REFERENCE,
        digests,
        frozenset(),
        pixels,
        contours,
        absent_dose_frames=doses,
    )


def _written_sha256(
    digester: Callable[[pydicom.Dataset], bytes], data: bytes
) -> bytes | None:
    """The digest of a file's pixel data or contours, or None where it
    cannot be read."""
    try:
        return digester(read_source(data).dataset())
    except (SourceRefused, ValueError):
        return None


def every_corner_accepted(corpus: corpus_module.SyntheticCorpus) -> RedactionReview:
    """Return a redaction review that accepts :data:`CORNER` in every frame of
    every file of the corpus with Pixel Data.

    It is matched by each file's SHA-256, as an attested review's verdicts
    are, so each instance with Pixel Data has its corner blacked out, and
    satisfies the option, without the finder.
    """
    approved = {}
    for file in corpus.files:
        dataset = pydicom.dcmread(io.BytesIO(file.data))
        if "PixelData" in dataset:
            frames = int(dataset.get("NumberOfFrames", 1) or 1)
            approved[hashlib.sha256(file.data).digest()] = tuple(
                (index, (CORNER,)) for index in range(frames)
            )
    return RedactionReview(REDACTION_REVIEW_REFERENCE, approved, frozenset())
