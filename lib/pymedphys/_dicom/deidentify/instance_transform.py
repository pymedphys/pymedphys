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

# pylint: disable = too-many-lines
# One module joins the engine's per-instance steps, so it is long.

"""De-identify one instance of a run: the run's concrete transform.

:class:`InstanceTransform` is the
:class:`~pymedphys._dicom.deidentify.run.Transform` that a run calls for
each instance it may process. It joins the engine's per-instance steps:

1. :func:`~pymedphys._dicom.deidentify.source.read_source` admits the
   source file, whose every byte must be accounted for;
2. :func:`~pymedphys._dicom.deidentify.scope.classify` decides from its SOP
   Class and transfer syntax whether the release de-identifies it at all;
   for one it de-identifies whose Pixel Data is compressed,
   :func:`~pymedphys._dicom.deidentify.pixel_decoding.frames_problem`
   decodes each frame once, after the plan and edits below, so that its
   values are collected for the residual search either way, and
   :func:`~pymedphys._dicom.deidentify.codestreams.without_metadata` parses
   each frame's codestream and cuts its metadata segments, without
   recompression, before it is written, after which every frame must
   decode to the same pixels;
3. :func:`~pymedphys._dicom.deidentify.walker.plan_instance` gives each
   element its action under the run's policy and the instance's IOD;
4. :func:`~pymedphys._dicom.deidentify.edits.edit_instance` works out what
   each element becomes, with the run's key and the subject's identity, and
   collects the values removed or replaced for the residual search, and
   :func:`~pymedphys._dicom.deidentify.cleaners.apply_cleaners`, then, under
   Clean Descriptors,
   :func:`~pymedphys._dicom.deidentify.descriptor_cleaning.clean_descriptors`,
   settle the attributes that the policy gives C, and under Clean Pixel Data,
   :func:`~pymedphys._dicom.deidentify.pixel_cleaning.black_out` blacks out
   the text found in native Pixel Data (D-037), and under Clean Recognizable
   Visual Features writes air in the face block of a CT slice
   (:mod:`~pymedphys._dicom.deidentify.face_blocks`);
5. :func:`writer_plan` turns those edits into what the byte-preserving
   writer takes, and
   :func:`~pymedphys._dicom.deidentify.preserving_writer.write_data_set` and
   :func:`~pymedphys._dicom.deidentify.preserving_writer.write_file_bytes`
   write the file;
6. :func:`~pymedphys._dicom.deidentify.preservation.verify_preservation`
   checks the file written against its source and the same plan,
   :func:`~pymedphys._dicom.deidentify.pixel_cleaning.redaction_problem` any
   Pixel Data blacked out, and
   :func:`~pymedphys._dicom.deidentify.iod_conformance.lost_requirements`
   checks that it still holds each attribute that its IOD requires where
   the source held one; and
7. :func:`~pymedphys._dicom.deidentify.output_names.instance_path` names the
   file from its replacement Patient ID and UIDs alone (D-016), and where
   the policy keeps the Study, Series, or SOP Instance UID, as the Retain
   UIDs Option does, from that UID's keyed replacement
   (:func:`~pymedphys._dicom.deidentify.retained_uids.output_name_uid`),
   while its File Meta Information gives the SOP Instance UID as written.

Any step that refuses the instance sequesters it with that step's own
value-free reason: a :class:`~.scope.Disposition`, or an
:class:`~.scope.UnsupportedIod` that names the IOD of an instance of an
unsupported IOD (D-010), a :class:`~.source.SourceReason`, the walker's
:class:`~.walker.Sequestration` objects, a
:class:`~.preserving_writer.WriteReason`, a
:class:`~.preservation.PreservationReason`, or a :class:`TransformReason`,
such as :attr:`TransformReason.PENDING_EDIT` for the edits still to come
that :func:`writer_plan` names by :class:`PendingEdit`. No exception
message is kept, since some come from pydicom and can quote a value.

Whatever the outcome, once the instance has been planned and edited, its
:class:`~.release_gate.Coverage` goes with it as the transform's evidence:
every value that had to be collected for the residual search, those
collected, and those that could not be. :class:`ReleaseGate` is the run's
:class:`~pymedphys._dicom.deidentify.run.Gate`: it pools the coverage of the
file's subject, sequestered instances included, and asks
:func:`~.release_gate.release_condition` about the written file (D-027).
Where the edits sequester an instance, the values that they did not reach
are uncollected. An instance out of scope whose IOD the pinned tables
define, such as a nuclear medicine image or a spatial registration, is
planned and edited too when its source is readable, only so that its values
are collected for its subject's search; it is never written. Where an
instance of the subject gives no coverage at all, because its source is
refused, its SOP Class names no IOD of the tables, its Specific Character
Set cannot be decoded, the transform raises, or it changed during the run,
the gate withholds the file, since its values
could be there unsearched for.

A UID that the pinned tables register, and that U therefore retains, such
as a SOP Class UID, is meant to stay in the output, so it is neither planned
nor collected: the written file is searched only for values that must not
appear in it. For the same reason, a UID that the policy keeps
(:func:`~pymedphys._dicom.deidentify.retained_uids.retained_uid_tags`) is
left out of the search where it is removed with an enclosing sequence or by
the engine's own removals (D-040).
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
from collections.abc import Callable, Iterable, Mapping
from pathlib import PurePosixPath

from pymedphys._imports import pydicom

from . import output_names
from .clean_graphics import overlay_in_pixel_data
from .content_items import content_item_actions
from .cleaners import apply_cleaners, cleaners_for
from .descriptor_cleaning import (
    CLEAN_DESCRIPTORS,
    DescriptorCleaning,
    DescriptorsRefused,
    HeldRoiName,
    clean_descriptors,
    fallback_policy,
    kept_descriptors,
)
from .edits import Edit, EditKind, InstanceEdits, edit_instance, read_values
from .element_rules import ElementRules
from .safe_private import SafePrivateList
from .elements import (
    DEFAULT_CODECS,
    UndecodableElement,
    dataset_codecs,
    new_element,
    new_items,
    read_element,
)
from .face_review import (
    PIXEL_DATA_TAGS,
    FaceReview,
    carries_visual_features,
    pixel_data_sha256,
)
from .file_layout import ElementPath
from .iod_conformance import lost_requirements, source_gaps
from .iods import IOD, IODTables, load_iod_tables
from .keys import DeidKey
from .markers import MarkerError, Markers, apply_markers, markers_for
from .method_digest import method_digest
from .policy import (
    CLEAN_RECOGNIZABLE_VISUAL_FEATURES,
    CLEAN_PIXEL_DATA,
    Policy,
    PolicyError,
    select_policy,
)
from .preservation import Expectations, PreservationFailed, verify_preservation
from .preserving_writer import WriteRefused, write_data_set, write_file_bytes
from .qc_pack import DropReason
from .qc_retained import retained_paths, retained_text
from .reasons import (
    HeldPixelData,
    HeldVisualFeatures,
    TransformReason,
    VisualFeaturesReason,
)
from .reference_graph import ReferenceGraph
from .references import InstanceRecord
from .reviewed_roi_names import ReviewQueue
from .release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    ReleaseCondition,
    ReleaseReason,
    SubjectCoverages,
    Uncollected,
    release_condition,
)
from .residuals import NotSearched, has_written_constant, not_searched_of
from .retained_uids import output_name_uid, retained_uid_paths, retained_uid_tags
from .run import NO_EVIDENCE, HoldForReview, Release, Sequestered, Transformed
from .codestreams import CodestreamRefused, without_metadata
from .pixel_decoding import frames_problem, same_pixels
from .pixel_cleaning import (
    PixelDataRefused,
    Redaction,
    TextFinder,
    black_out,
    finder_description,
    redaction_problem,
)
from .face_blocks import (
    CT_IMAGE,
    CtDefacer,
    FaceBlockCounts,
    SeriesDefacing,
    Defaced,
    find_defaced,
    find_face_blocks,
)
from .pixel_risk import assess_pixel_risk, series_evidence
from .run_qc import (
    Dropped,
    PixelRiskMaterial,
    RedactionMaterial,
    SearchMaterial,
    SeriesEvidence,
)
from .run_report import ReleaseReporter
from .scope import Classification, classify
from .source import SourceEvidence, SourceRefused, read_source
from .uids import UIDOutcome, normalise_uid
from .values import value_problem
from .walker import (
    Consumer,
    InstancePlan,
    SequesterReason,
    Sequestration,
    plan_instance,
)
from .written_references import WrittenFinding, verify_written_references

_SOP_CLASS = ElementPath((), "(0008,0016)")
_SOP_INSTANCE = ElementPath((), "(0008,0018)")
_STUDY = ElementPath((), "(0020,000D)")
_SERIES = ElementPath((), "(0020,000E)")
_PATIENT_ID = ElementPath((), "(0010,0020)")
_PIXEL_DATA = ElementPath((), "(7FE0,0010)")
_RECOGNIZABLE_VISUAL_FEATURES = "(0028,0302)"


@dataclasses.dataclass(frozen=True)
class PendingEdit:
    """An element whose edit is still to come, by path and action.

    Such as a pseudonym without the subject's identity, cleaning (C), or a
    reviewed dummy item.
    """

    path: ElementPath
    action: str


@dataclasses.dataclass(frozen=True)
class WriterPlan:
    """What the writer takes from an instance's edits.

    Attributes
    ----------
    kept, removed : frozenset of ElementPath
    replacements : mapping of ElementPath to pydicom.DataElement
    introduced : frozenset of ElementPath
        The elements in the items of a sequence among ``replacements``,
        which the writer writes from the sequence. The source elements
        inside such a sequence are all in ``removed``, for the writer;
        verification expects those at an introduced path to be changed.
    """

    kept: frozenset[ElementPath]
    removed: frozenset[ElementPath]
    replacements: Mapping[ElementPath, pydicom.DataElement] = dataclasses.field(
        repr=False
    )
    introduced: frozenset[ElementPath] = frozenset()

    @property
    def expectations(self) -> Expectations:
        """What verification expects of the file written from this plan."""
        return Expectations(
            kept=self.kept,
            changed=frozenset(self.replacements) | self.introduced,
            removed=self.removed - self.introduced,
        )


def _left_out(edits: InstanceEdits) -> dict[ElementPath, DropReason]:
    """Return each path that the residual search leaves out, and why.

    These are the elements whose every UID U retains, and the elements whose
    UIDs the pinned tables all register, wherever they are, removed
    sequences included.
    """
    left_out = {
        edit.path: DropReason.RETAINED
        for edit in edits.edits
        if edit.uid_outcomes
        and all(outcome is UIDOutcome.RETAINED for outcome in edit.uid_outcomes)
    }
    collected = {value.source for value in edits.source_values}
    for path in edits.registered_uids:
        if path not in collected:
            left_out.setdefault(path, DropReason.REGISTERED_UID)
    return left_out


def dropped_of(
    edits: InstanceEdits, retained: frozenset[ElementPath] = frozenset()
) -> tuple[Dropped, ...]:
    """Return the QC pack's drops of an instance's edits (D-027).

    Each element whose every UID U retains; each element with a UID that the
    pinned tables register, since that UID is left out of the search even
    where the element's other UIDs are collected; and each value that could
    not be decoded to collect, by its place in the source and once for each
    reason; then each path in ``retained``, as :func:`coverage_of` takes it.
    A value equal to a written constant is dropped by the search itself,
    and given by :func:`omissions_of`.
    """
    left_out = _left_out(edits)
    drops: list[tuple[ElementPath, DropReason]] = [
        (path, reason)
        for path, reason in left_out.items()
        if reason is DropReason.RETAINED
    ]
    drops += [(path, DropReason.REGISTERED_UID) for path in edits.registered_uids]
    drops += [
        (missing.path, DropReason.UNDECODABLE)
        for missing in edits.not_collected
        if missing.path not in left_out
    ]
    drops += [(path, DropReason.RETAINED) for path in sorted(retained, key=str)]
    return tuple(Dropped(path, reason) for path, reason in dict.fromkeys(drops))


@dataclasses.dataclass(frozen=True)
class HeldEvidence:
    """The evidence of an instance that review holds.

    Descriptor cleaning holds an instance with a ROI Name held for review, a
    pixel option one whose pixel data await review, and the face review one
    that can show a face without a verdict of absent for its source file.

    Attributes
    ----------
    coverage : Coverage
        Its residual search's coverage, pooled with its subject's as any.
    held : tuple of HeldRoiName, HeldPixelData, or HeldVisualFeatures
        Each ROI Name held, by path and reason, then why its visual features
        hold it, if they do, and why a pixel option holds it, if one does.
    """

    coverage: Coverage
    held: tuple[HeldRoiName | HeldPixelData | HeldVisualFeatures, ...]


def omissions_of(
    evidence: Coverage | HeldEvidence,
) -> tuple[Dropped | NotSearched, ...]:
    """Return what every residual search leaves out of an instance's own values.

    A drop for each value equal to a constant that the engine writes, and
    each form not searched, as any search of the subject lists them (D-027).
    They are the instance's own QC material, whether or not its file is
    gated, since its values are searched for in its subject's other files.
    """
    coverage = evidence.coverage if isinstance(evidence, HeldEvidence) else evidence
    paths = (
        value.source for value in coverage.collected if has_written_constant(value)
    )
    constants = tuple(
        Dropped(path, DropReason.WRITTEN_CONSTANT) for path in dict.fromkeys(paths)
    )
    return (*constants, *not_searched_of(coverage.collected))


def coverage_of(
    plan: InstancePlan,
    edits: InstanceEdits,
    retained: frozenset[ElementPath] = frozenset(),
    options: tuple[str, ...] = (),
) -> Coverage:
    """Return the residual search's coverage of an instance's plan and edits.

    Every element that the plan has residual collection read is planned,
    and each value collected or not collected is carried over, but for an
    element whose every UID U retains, and for an element whose UIDs the
    pinned tables all register, which the edits leave out of collection
    wherever it is, removed sequences included, and for each path in
    ``retained``, such as a ROI Name that descriptor cleaning writes with a
    value. Where the edits sequester the instance, each planned value that
    they did not reach is uncollected. Each value read as ISO 8859-1, since
    no Specific Character Set applies, is carried over as read as bytes, so
    that its collection is incomplete (D-027). ``options``, the policy's,
    say which findings an option can explain, such as one that a kept value
    explains, or a date that Modified Dates shifted onto another source date.
    """
    left_out: set[ElementPath] = set(retained) | set(_left_out(edits))
    planned = frozenset(
        element.path
        for element in plan.elements
        if Consumer.RESIDUAL_COLLECTION in element.consumers
        and element.path not in left_out
    )
    collected = tuple(
        value for value in edits.source_values if value.source not in left_out
    )
    uncollected = [
        Uncollected(path=missing.path, reason=missing.reason)
        for missing in edits.not_collected
        if missing.path not in left_out
    ]
    if edits.sequestrations:
        # The edits stop at the first sequestration, so the values that they
        # did not reach are uncollected, which withholds the subject's other
        # files for that reason rather than as not reported.
        reached = {value.source for value in collected} | {
            missing.path for missing in uncollected
        }
        uncollected += [
            Uncollected(path=path, reason=_NOT_REACHED)
            for path in sorted(planned - reached, key=str)
        ]
    return Coverage(
        planned=planned,
        collected=collected,
        uncollected=tuple(uncollected),
        decoded_as_bytes=frozenset(edits.read_as_latin_1) - left_out,
        options=options,
    )


_NOT_REACHED = "the instance was sequestered before the value was read"


class _Refused(Exception):
    """An instance the transform sequesters, with its value-free reasons."""

    def __init__(self, *reasons: object) -> None:
        super().__init__()
        self.reasons = reasons


def writer_plan(
    plan: InstancePlan, edits: InstanceEdits, codecs: tuple[str, ...]
) -> WriterPlan:
    """Return what the writer takes from an instance's edits.

    A kept element, including a sequence kept as a container, is kept; a
    removed one, including each element inside a removed, emptied, or
    replaced sequence, is removed; and an emptied or replaced one is built
    with the VR that its plan reads it by, through
    :func:`~pymedphys._dicom.deidentify.elements.new_element`.

    Parameters
    ----------
    plan : InstancePlan
    edits : InstanceEdits
        The edits of ``plan``, with none sequestering the instance.
    codecs : tuple of str
        Those of the top-level data set, which every value the engine writes
        can be encoded in; the writer checks each value again against the
        character set in force at its place.

    Raises
    ------
    _Refused
        With a :class:`PendingEdit` for each edit still to come, or
        :attr:`TransformReason.UNWRITABLE_ELEMENT`.
    """
    pending = tuple(
        PendingEdit(edit.path, edit.action)
        for edit in edits.edits
        if edit.kind is EditKind.PENDING
    )
    if pending:
        raise _Refused(*pending)
    vrs = {element.path: element.vr for element in plan.elements}
    kept: set[ElementPath] = set()
    removed: set[ElementPath] = set()
    replacements: dict[ElementPath, pydicom.DataElement] = {}
    # The elements of the items that D writes in a reviewed dummy sequence.
    introduced: set[ElementPath] = set()
    for edit in edits.edits:
        if edit.kind is EditKind.KEEP:
            kept.add(edit.path)
        elif edit.kind is EditKind.REMOVE:
            removed.add(edit.path)
        else:
            replacements[edit.path] = _element(edit, vrs.get(edit.path), codecs)
            if edit.items:
                introduced.update(
                    _paths_within(replacements[edit.path], edit.path.items)
                )
    return WriterPlan(
        frozenset(kept), frozenset(removed), replacements, frozenset(introduced)
    )


# The attributes that PS3.15 E.1.1, E.2, and E.3.6 have a de-identifier add
# or update, which apply_markers writes; it writes Recognizable Visual
# Features (0028,0302) too, under E.3.2, only where the markers set it.
MARKER_TAGS = (
    "(0012,0062)",  # Patient Identity Removed
    "(0012,0063)",  # De-identification Method
    "(0012,0064)",  # De-identification Method Code Sequence
    "(0018,A001)",  # Contributing Equipment Sequence
    "(0028,0303)",  # Longitudinal Temporal Information Modified
)


def with_markers(
    writing: WriterPlan,
    source: SourceEvidence,
    dataset: pydicom.Dataset | None,
    markers: Markers,
) -> WriterPlan:
    """Return the writer's plan with the instance's markers written.

    The markers are added, by :func:`~.markers.apply_markers`, to what the
    plan already writes of each marker attribute: its replacement, or a kept
    element from the source with the plan's edits inside it applied, so that
    an element that the plan removes or replaces within a kept sequence,
    such as Institution Name in an item of Contributing Equipment Sequence,
    is removed or replaced there too. Each marker attribute is then written whole
    as a replacement, and the elements inside a source sequence it replaces
    are removed; verification expects those the new sequence writes at the
    same path to be changed instead.

    Raises
    ------
    _Refused
        With :attr:`TransformReason.UNMARKABLE` where a kept marker attribute
        cannot be read, holds an element that the plan does not plan, or the
        markers cannot be added to it.
    """
    tags = MARKER_TAGS + (
        ()
        if markers.recognizable_visual_features is None
        else (_RECOGNIZABLE_VISUAL_FEATURES,)
    )
    present = pydicom.Dataset()
    for tag in tags:
        path = ElementPath((), tag)
        if path in writing.replacements:
            present.add(copy.deepcopy(writing.replacements[path]))
        elif path in writing.kept:
            if dataset is None or _int_tag(tag) not in dataset:
                raise _Refused(TransformReason.UNMARKABLE)
            present.add(_as_planned(dataset[_int_tag(tag)], (), writing))
    try:
        marked = apply_markers(present, markers)
    except (MarkerError, TypeError, ValueError):
        raise _Refused(TransformReason.UNMARKABLE) from None
    kept, removed = set(writing.kept), set(writing.removed)
    replacements = dict(writing.replacements)
    introduced = set(writing.introduced)
    for tag in tags:
        if _int_tag(tag) not in marked:
            continue
        element = marked[_int_tag(tag)]
        path = ElementPath((), tag)
        within = {
            planned
            for planned in kept | removed | set(replacements) | introduced
            if planned.items and planned.items[0][0] == tag
        }
        kept -= within | {path}
        removed -= within | {path}
        introduced -= within
        for planned in within:
            replacements.pop(planned, None)
        removed |= {
            inside
            for inside in source.paths()
            if inside.items and inside.items[0][0] == tag
        }
        replacements[path] = element
        introduced |= set(_paths_within(element, ()))
    return WriterPlan(
        frozenset(kept), frozenset(removed), replacements, frozenset(introduced)
    )


def _as_planned(
    element: pydicom.DataElement,
    items: tuple[tuple[str, int], ...],
    writing: WriterPlan,
) -> pydicom.DataElement:
    """Return a copy of a kept source element with the plan's edits within it.

    Inside a kept sequence, each element that the plan removes is left out,
    each that it replaces is its replacement, and each that it keeps is
    copied, a kept sequence with the edits within it in turn.

    Raises
    ------
    _Refused
        With :attr:`TransformReason.UNMARKABLE` for an element within that
        the plan neither keeps, removes, nor replaces.
    """
    if element.VR != "SQ":
        return copy.deepcopy(element)
    tag = _tag_text(element.tag)
    edited = pydicom.Sequence()
    for index, item in enumerate(element.value):
        held = items + ((tag, index),)
        written = pydicom.Dataset()
        for inner in item:
            path = ElementPath(held, _tag_text(inner.tag))
            if path in writing.removed:
                continue
            if path in writing.replacements:
                written.add(copy.deepcopy(writing.replacements[path]))
            elif path in writing.kept:
                written.add(_as_planned(inner, held, writing))
            else:
                raise _Refused(TransformReason.UNMARKABLE)
        edited.append(written)
    return pydicom.DataElement(element.tag, element.VR, edited)


def _paths_within(
    element: pydicom.DataElement, items: tuple[tuple[str, int], ...]
) -> list[ElementPath]:
    """Return the path of each element inside the items of a sequence element."""
    if element.VR != "SQ":
        return []
    tag = _tag_text(element.tag)
    paths: list[ElementPath] = []
    for index, item in enumerate(element.value):
        held = items + ((tag, index),)
        for inner in item:
            paths.append(ElementPath(held, _tag_text(inner.tag)))
            paths.extend(_paths_within(inner, held))
    return paths


def _int_tag(tag: str) -> int:
    return int(tag[1:5] + tag[6:10], 16)


def _tag_text(tag: int) -> str:
    return f"({tag >> 16:04X},{tag & 0xFFFF:04X})"


# The options that each instance satisfies, or not, by its own outcome: Clean
# Descriptors, by descriptor cleaning (D-009), Clean Pixel Data, by what its
# pixel data hold (D-037), and Clean Recognizable Visual Features, by the face
# review of its source file.
PER_INSTANCE_OPTIONS = frozenset(
    {CLEAN_DESCRIPTORS, CLEAN_PIXEL_DATA, CLEAN_RECOGNIZABLE_VISUAL_FEATURES}
)


def satisfied_options(policy: Policy) -> tuple[str, ...]:
    """Return the options an instance satisfies by the policy's actions alone.

    Every selected option but those of :data:`PER_INSTANCE_OPTIONS`, which
    each instance satisfies by its own outcome, and but any option the
    policy records as unmet.
    """
    unmet = {option for resolution in policy.resolved for option in resolution.unmet}
    return tuple(
        option
        for option in policy.options
        if option not in PER_INSTANCE_OPTIONS and option not in unmet
    )


def _element(
    edit: Edit, vr: str | None, codecs: tuple[str, ...]
) -> pydicom.DataElement:
    values: tuple[object, ...] = () if edit.kind is EditKind.EMPTY else edit.values
    if vr is None:
        raise _Refused(TransformReason.UNWRITABLE_ELEMENT)
    try:
        if edit.items:
            values = new_items(edit.path, edit.items, codecs)
        return new_element(edit.path, vr, values, codecs)
    except ValueError:
        pass
    raise _Refused(TransformReason.UNWRITABLE_ELEMENT)


class InstanceTransform:
    """The run's transform under one policy and key.

    Parameters
    ----------
    policy : Policy
        The run's policy, such as ``compose_policy("basic")``.
    key : DeidKey
        The run's key, for keyed replacement UIDs and pseudonyms.
    iod_tables : IODTables, optional
        Defaults to :func:`~pymedphys._dicom.deidentify.iods.load_iod_tables`.
    cleaning : DescriptorCleaning, optional
        The vocabulary and reviewed-names list that ROI Names are cleaned
        with, and the reviewed descriptors list and technique vocabulary
        that free-text descriptors are cleaned with, which a policy
        selecting Clean Descriptors needs, and no other policy takes. The
        transform applies each list's decisions as they stand when it is
        made, the version whose keyed digest its markers and release report
        record; a decision recorded later does not apply.
    finder : TextFinder, optional
        What finds the regions of text in each frame, such as a
        :class:`~pymedphys._dicom.deidentify.text_detection.TextDetector`,
        which a policy selecting Clean Pixel Data needs, and no other policy
        takes. Its class and a copy of the description of its method, read
        once when the transform is made
        (:func:`~pymedphys._dicom.deidentify.pixel_cleaning.finder_description`),
        are an input to the method digest that the markers and the release
        report record.
    face_review : FaceReview, optional
        The face verdicts of an earlier run's attested QC pack, from
        :func:`~pymedphys._dicom.deidentify.face_review.read_face_review`,
        which a policy selecting Clean Recognizable Visual Features needs,
        and no other policy takes.
    safe_private_list : SafePrivateList, optional
        Under the Retain Safe Private Option, the list whose rules settle
        private attributes: the reviewed rules, the default, or TCIA's
        Private Tag Dictionary. The method digest, the release report, and
        the conformance statement record which.
    unvalidated_policy : bool, default False
        Allow a policy that is not enabled, such as a preset whose behaviour
        is not yet validated. For tests and validation runs only; nothing
        that de-identifies data for use sets it.

    Raises
    ------
    PolicyError
        If the policy is not enabled and ``unvalidated_policy`` is not set;
        if ``cleaning`` is given without Clean Descriptors, or left out with
        it; if ``finder`` is given without Clean Pixel Data, or left out with
        it; if ``face_review`` is given without Clean Recognizable Visual
        Features, or left out with it; if ``safe_private_list`` chooses
        TCIA's dictionary without the Retain Safe Private Option; or if the
        policy's other options cannot be composed into the policy whose
        actions descriptors take where they are not cleaned.
    TypeError
        If ``finder`` does not describe its method as a mapping that is not
        empty, or its description has a type that the method digest does not
        define.

    Attributes
    ----------
    review_queue : ReviewQueue
        The distinct ROI Names that the run's instances held for review,
        for the confidential QC material; empty without ``cleaning``.
    reporter : ~pymedphys._dicom.deidentify.run_report.ReleaseReporter
        The release report of a run with this transform, under its policy
        and vocabulary, for :func:`~pymedphys._dicom.deidentify.run.run`.

    Notes
    -----
    The subject's identity is the instance's own Patient ID with its issuer,
    as the run's first pass records it (``InstanceRecord.patient``). An
    instance without one has no pseudonyms, so its Patient's Name and
    Patient ID edits stay pending and it is sequestered.

    The cleaners of the options that the policy selects
    (:func:`~.cleaners.cleaners_for`) settle the attributes given C that they
    clean, such as Retain Device Identity's AE titles, and then, under Clean
    Descriptors, :func:`~.descriptor_cleaning.clean_descriptors` settles the
    others, where it can; an attribute given C that is still pending
    sequesters the instance. An instance with a ROI Name held for
    review is written with that name empty, and its evidence is a
    :class:`HeldEvidence`, which :class:`ReleaseGate` holds for review. The
    markers claim Clean Descriptors only for an instance that satisfies it.
    Under Clean Graphics, an instance whose overlay may lie in Pixel Data is
    sequestered (:func:`~.clean_graphics.overlay_in_pixel_data`). Under Clean
    Structured Content, the plan keeps each content-item sequence that it
    can and gives the values of its content items the actions of their
    concept names (:func:`~.content_items.content_item_actions`, D-047), as
    does the plan that descriptor cleaning falls back to.

    Under Clean Pixel Data, :func:`~.pixel_cleaning.black_out` blacks out the
    regions of text that ``finder`` finds in each frame of the instance's
    top-level native Pixel Data, :func:`~.pixel_cleaning.redaction_problem`
    checks the file written, and the instance's evidence is a
    :class:`HeldEvidence`, whether or not text was found, since the finder can
    miss text and only review can confirm the option (D-037). One whose
    pixel data the option cannot clean, such as compressed Pixel Data, is
    sequestered (:class:`~.pixel_cleaning.PixelDataRefused`), and one without
    top-level pixel data is written as under the other options. No instance's
    markers claim the option yet, since none can be released with Burned In
    Annotation (0028,0301) set to NO until a reviewer's decision can be
    applied.

    Under Clean Recognizable Visual Features, :meth:`prepare` finds the face
    block of each series of CT Image instances before the run writes any
    (:func:`~.face_blocks.find_face_blocks`), and each slice of a series
    with one is written with air in its block, as
    :func:`~.pixel_cleaning.black_out` writes a
    :class:`~.face_blocks.CtDefacer`'s masks, checked as a redaction is; a
    slice that cannot be is sequestered. A slice of a series with a
    target's contour in its block is not defaced, and is held for review
    (:attr:`~.reasons.VisualFeaturesReason.TARGET_IN_FACE_BLOCK`). An RT
    Structure Set, RT Dose, or PET instance in a defaced series' Frame of
    Reference, naming none, or referring to a defaced slice, is held
    whatever its verdict
    (:attr:`~.reasons.VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME`),
    since the run does not yet clean it of the face. An
    instance that can show a
    face (:func:`~.face_review.carries_visual_features`) satisfies the
    option only where the SHA-256 of its source file is in a series that the
    face review marks absent, and the pixel data that it is written with are
    those that the reviewed run wrote of that file
    (:attr:`~.reasons.VisualFeaturesReason.OTHER_PIXEL_DATA` otherwise), and
    an instance that cannot show a face satisfies it. Each is marked with the option's code and Recognizable
    Visual Features (0028,0302) set to NO, which PS3.15 E.3.2 adds whether
    or not its IOD defines the attribute. Any other instance that can show a
    face is written without them, and its evidence is a
    :class:`HeldEvidence` with its :class:`~.reasons.HeldVisualFeatures`, so
    it is never released.
    """

    def __init__(
        self,
        policy: Policy,
        key: DeidKey,
        iod_tables: IODTables | None = None,
        *,
        cleaning: DescriptorCleaning | None = None,
        finder: TextFinder | None = None,
        face_review: FaceReview | None = None,
        safe_private_list: SafePrivateList = SafePrivateList.REVIEWED,
        unvalidated_policy: bool = False,
    ) -> None:
        if not (policy.enabled or unvalidated_policy):
            raise PolicyError(
                "the policy is not enabled: its behaviour is not yet implemented "
                "and validated"
            )
        if (CLEAN_DESCRIPTORS in policy.options) != (cleaning is not None):
            raise PolicyError(
                "descriptor cleaning is given exactly when the policy selects "
                "Clean Descriptors"
            )
        if (CLEAN_PIXEL_DATA in policy.options) != (finder is not None):
            raise PolicyError(
                "a text finder is given exactly when the policy selects Clean "
                "Pixel Data"
            )
        self._finder = finder
        if (CLEAN_RECOGNIZABLE_VISUAL_FEATURES in policy.options) != (
            face_review is not None
        ):
            raise PolicyError(
                "a face review is given exactly when the policy selects Clean "
                "Recognizable Visual Features"
            )
        # One description of the finder, for both the markers' digest and
        # the release report's.
        finder_method = None if finder is None else finder_description(finder)
        if cleaning is not None:
            # One version of each list, for both cleaning and its digest.
            cleaning = dataclasses.replace(
                cleaning,
                reviewed=cleaning.reviewed.snapshot(),
                reviewed_descriptors=cleaning.reviewed_descriptors.snapshot(),
            )
        self._rules = ElementRules(policy, safe_private_list=safe_private_list)
        self._policy = policy
        self._options = policy.options
        self._key = key
        self._retained_uids = retained_uid_tags(policy)
        self._cleaners = cleaners_for(policy)
        self._cleaned_elsewhere = frozenset(
            tag for cleaner in self._cleaners for tag in cleaner.tags
        )
        self._cleaning = cleaning
        self._fallback = (
            None
            if cleaning is None
            else ElementRules(
                fallback_policy(policy), safe_private_list=safe_private_list
            )
        )
        self._vocabulary = None if cleaning is None else cleaning.vocabulary
        self.review_queue = ReviewQueue()
        nomenclature = None if cleaning is None else cleaning.nomenclature
        reviewed = None if cleaning is None else cleaning.reviewed.keyed_digest(key)
        descriptors = technique = None
        if cleaning is not None:
            descriptors = cleaning.reviewed_descriptors.keyed_digest(key)
            if cleaning.technique is not None:
                technique = cleaning.technique.sha256
        digest = method_digest(
            policy,
            vocabulary=nomenclature,
            reviewed_roi_names=reviewed,
            reviewed_descriptors=descriptors,
            technique_vocabulary=technique,
            text_finder=finder_method,
            safe_private_list=safe_private_list,
        )
        satisfied = satisfied_options(policy)
        # The markers of each set of per-instance options that an instance
        # can satisfy.
        per_instance = [o for o in policy.options if o in PER_INSTANCE_OPTIONS]
        self._markers = {
            frozenset(chosen): markers_for(
                policy,
                digest,
                satisfied=satisfied + tuple(o for o in per_instance if o in chosen),
            )
            for chosen in _subsets(per_instance)
        }
        self._face_review = face_review
        self._face_blocks: dict[str, SeriesDefacing] = {}
        self._defaced = Defaced()
        self._face_block_counts = None if face_review is None else FaceBlockCounts()
        self._iods = load_iod_tables() if iod_tables is None else iod_tables
        self.reporter = ReleaseReporter(
            policy,
            vocabulary=nomenclature,
            reviewed_roi_names=reviewed,
            reviewed_descriptors=descriptors,
            technique_vocabulary=technique,
            text_finder=finder_method,
            face_review=None if face_review is None else face_review.reference,
            safe_private_list=safe_private_list,
            face_blocks=self._face_block_counts,
        )

    def __repr__(self) -> str:
        return "InstanceTransform()"

    def prepare(
        self,
        records: Mapping[int, InstanceRecord],
        read: Callable[[int], bytes | None],
    ) -> None:
        """Find the face block of each CT series of a run, before it writes any.

        Only under Clean Recognizable Visual Features, as
        :func:`~pymedphys._dicom.deidentify.face_blocks.find_face_blocks`
        finds them, and counted for the release report. A run calls it with
        the records of the instances that it will transform, by run
        position, and a function that gives each file as its first pass
        read it, once, before it transforms any.
        """
        if self._face_block_counts is None:
            return
        self._face_blocks = find_face_blocks(records, read)
        self._face_block_counts.record(self._face_blocks.values())
        self._defaced = find_defaced(records, self._face_blocks)

    def written_check(
        self, graph: ReferenceGraph, written: Mapping[int, InstanceRecord]
    ) -> tuple[WrittenFinding, ...]:
        """Check what a run with this transform wrote against its first pass.

        The reference graph's second pass under the transform's key, for
        :func:`~pymedphys._dicom.deidentify.run.run`'s ``written_check``, as
        :func:`~pymedphys._dicom.deidentify.written_references.verify_written_references`
        makes it, with the UIDs that the transform's policy keeps.
        """
        return verify_written_references(
            self._key, graph, written, retained=self._retained_uids
        )

    def _unplanned(
        self,
        source: SourceEvidence,
        classification: Classification,
        character_set: ElementPath | None,
    ) -> tuple[object, ...]:
        """Why an instance that gives no coverage is sequestered.

        One whose SOP Class names no IOD of the pinned tables gives its scope's
        reason alone. One whose Specific Character Set cannot be decoded gives
        the walker's reason for it, by its path and planned action as the edits
        give an item's (D-010), after any scope reason: none of its text can be
        read, so none is collected, and its subject's files are withheld as not
        reported (D-027).
        """
        scope = (classification.reason,) if classification.sequestered else ()
        iod = self._iods.iods.get(classification.iod or "")
        if iod is None or character_set is None:
            return scope
        plan = plan_instance(source, self._rules, iod)
        planned = next((e for e in plan.elements if e.path == character_set), None)
        action = "K" if planned is None else planned.action
        reason = SequesterReason.UNSUPPORTED_CHARACTER_SET
        return (*scope, Sequestration(character_set, action, "CS", reason))

    def _identifiers(
        self, writing: WriterPlan, dataset: pydicom.Dataset, source: SourceEvidence
    ) -> _Identifiers:
        """Return the identifiers that the output is written and named with.

        Each of the Patient ID, Study, Series, and SOP Instance UIDs is its
        replacement, which names the file as it is written. One that the
        policy keeps, which only a UID can be, is written as it is, and
        names the file by its keyed replacement.

        Raises
        ------
        _Refused
            With :attr:`TransformReason.UNNAMED_OUTPUT` where an identifier
            is neither replaced by one text value, nor kept as a valid UID.
        """
        written: dict[ElementPath, str] = {}
        names: dict[ElementPath, str] = {}
        for path in (_PATIENT_ID, _STUDY, _SERIES, _SOP_INSTANCE):
            value = _replaced(writing.replacements, path)
            kept = value is None and path.tag in self._retained_uids
            if kept and path in writing.kept:
                value = _kept_uid(dataset, path, source)
            if value is None:
                raise _Refused(TransformReason.UNNAMED_OUTPUT)
            written[path] = value
            names[path] = output_name_uid(self._key, value, kept)
        return _Identifiers(written[_SOP_INSTANCE], names)

    def _face_hold(
        self, data: bytes, dataset: pydicom.Dataset, iod: IOD, writing: WriterPlan
    ) -> HeldVisualFeatures | None:
        """Return why the face review holds an instance, if it does.

        Nothing holds an instance without a face review, or one that cannot
        show a face. The review is of the source file and of the pixel data
        that ``writing`` writes.
        """
        review = self._face_review
        if review is None or not carries_visual_features(dataset, iod.name):
            return None
        reason = review.hold_reason(
            hashlib.sha256(data).digest(), _pixel_digest(writing, dataset)
        )
        return None if reason is None else HeldVisualFeatures(reason)

    def _frame_hold(
        self, iod: IOD, record: InstanceRecord
    ) -> HeldVisualFeatures | None:
        """Return why an instance that the run does not yet clean of the
        face is held, where it defaces the instance's frame
        (:meth:`~.face_blocks.Defaced.holds`)."""
        if not self._defaced.holds(iod.name, record):
            return None
        return HeldVisualFeatures(VisualFeaturesReason.UNDEFACED_IN_DEFACED_FRAME)

    def _defacing(self, iod: IOD, record: InstanceRecord) -> SeriesDefacing | None:
        """Return the outcome of a CT slice's series, if it has one."""
        if iod.name != CT_IMAGE or record.series is None:
            return None
        return self._face_blocks.get(record.series)

    def _black_out(
        self,
        source: SourceEvidence,
        dataset: pydicom.Dataset,
        defacing: SeriesDefacing | None,
    ) -> Redaction | None:
        """Return the instance's Pixel Data blacked out under Clean Pixel Data,
        and its face block written as air under Clean Recognizable Visual
        Features.

        None where neither applies, or the instance has no top-level pixel
        data.

        Raises
        ------
        _Refused
            With the reason of :class:`~.pixel_cleaning.PixelDataRefused`.
        """
        block = None if defacing is None else defacing.block
        if self._finder is None and block is None:
            return None
        try:
            defacer = None if block is None else CtDefacer(block, dataset)
            return black_out(source, dataset, self._finder, defacer)
        except PixelDataRefused as refused:
            raise _Refused(refused.reason) from None

    def _kept_descriptors(
        self, plan: InstancePlan, edits: InstanceEdits
    ) -> frozenset[ElementPath]:
        """Return the descriptors of a withheld instance that cleaning would keep.

        None without Clean Descriptors
        (:func:`~pymedphys._dicom.deidentify.descriptor_cleaning.kept_descriptors`).
        """
        if self._cleaning is None or self._fallback is None:
            return frozenset()
        return kept_descriptors(
            plan, edits, self._cleaning, cleaned_elsewhere=self._cleaned_elsewhere
        )

    def __call__(
        self, data: bytes, record: InstanceRecord
    ) -> Transformed | Sequestered:
        try:
            source = read_source(data)
            dataset = source.dataset()
        except SourceRefused as refused:
            return Sequestered((refused.reason,))
        try:
            codecs = dataset_codecs(dataset, source=source)
            character_set = None
        except UndecodableElement as error:
            codecs, character_set = DEFAULT_CODECS, error.path
        # The SOP Class UID is UI, which no character set changes.
        classification = classify(
            _text(dataset, _SOP_CLASS, source), source.transfer_syntax
        )
        if (
            classification.iod is None
            or (
                classification.sequestered and classification.iod not in self._iods.iods
            )
            or character_set is not None
        ):
            return Sequestered(self._unplanned(source, classification, character_set))
        iod = self._iods.iods[classification.iod]
        risk: tuple[object, ...] = _pixel_risk(dataset, record)
        if not classification.sequestered:
            risk += source_gaps(source, iod)
        plan = plan_instance(
            source, self._rules, iod, content_item_actions(source, self._policy, iod)
        )
        edits = edit_instance(
            source, plan, self._key, record.patient, record.series_numberings
        )
        kept_uids = retained_uid_paths(plan.elements, self._retained_uids)
        evidence: Coverage | HeldEvidence = coverage_of(
            plan, edits, kept_uids, self._options
        )
        if classification.sequestered:
            reasons: tuple[object, ...] = (classification.reason,)
        else:
            undecoded = None if edits.sequestrations else frames_problem(source)
            reasons = (
                edits.sequestrations
                or (() if undecoded is None else (undecoded,))
                or overlay_in_pixel_data(self._rules.policy, risk)
            )
        if reasons:
            # An instance out of scope is planned and edited only so that
            # its identifiers are collected for its subject's search (D-027).
            withheld = kept_uids | self._kept_descriptors(plan, edits)
            if withheld != kept_uids:
                evidence = coverage_of(plan, edits, withheld, self._options)
            return Sequestered(
                reasons,
                evidence,
                (*risk, *dropped_of(edits, withheld), *omissions_of(evidence)),
            )
        satisfied = False
        settled = apply_cleaners(edits, self._cleaners, self._key, record.patient)
        edits, retained = settled.edits, settled.retained | kept_uids
        if settled.retained:
            evidence = coverage_of(plan, edits, retained, self._options)
        names: tuple[object, ...] = ()
        if self._cleaning is not None and self._fallback is not None:
            fallback = self._fallback

            def fallen_back() -> InstanceEdits:
                return edit_instance(
                    source,
                    plan_instance(
                        source,
                        fallback,
                        iod,
                        content_item_actions(source, fallback.policy, iod),
                    ),
                    self._key,
                    record.patient,
                    record.series_numberings,
                )

            try:
                cleaned = clean_descriptors(
                    edits,
                    self._cleaning,
                    self._vocabulary,
                    self.review_queue,
                    fallen_back,
                    cleaned_elsewhere=self._cleaned_elsewhere,
                    private_texts=plan.private_texts,
                    private_text_vms=plan.private_text_vms,
                )
            except DescriptorsRefused as refused:
                withheld = retained | self._kept_descriptors(plan, edits)
                if withheld != retained:
                    evidence = coverage_of(plan, edits, withheld, self._options)
                return Sequestered(
                    (refused.reason,),
                    evidence,
                    (*risk, *dropped_of(edits, withheld), *omissions_of(evidence)),
                )
            edits, satisfied = cleaned.edits, cleaned.satisfied
            retained |= cleaned.retained
            names = cleaned.qc
            evidence = coverage_of(plan, edits, retained, self._options)
            if cleaned.held:
                evidence = HeldEvidence(evidence, cleaned.held)
        defacing = self._defacing(iod, record)
        qc = (*risk, *dropped_of(edits, retained), *omissions_of(evidence), *names)
        # No instance claims Clean Pixel Data until a reviewer's decision
        # can release its pixel data with Burned In Annotation set to NO
        # (D-037).
        chosen = {CLEAN_DESCRIPTORS} if satisfied else set()
        try:
            qc = (*qc, *_retained(source, plan, edits))
            redaction = self._black_out(source, dataset, defacing)
            # The markers write no pixel data, so the face review is of the
            # pixel data that this plan writes.
            writing = _without_bitstream_metadata(
                writer_plan(plan, edits, codecs), source
            )
            writing = _with_redaction(writing, dataset, redaction)
            face = (
                HeldVisualFeatures(VisualFeaturesReason.TARGET_IN_FACE_BLOCK)
                if defacing is not None and defacing.held
                else self._face_hold(data, dataset, iod, writing)
            )
            holds = [
                held
                for held in (face, self._frame_hold(iod, record))
                if held is not None
            ]
            for held in holds:
                evidence = _held(evidence, held)
            if not holds and self._face_review is not None:
                chosen.add(CLEAN_RECOGNIZABLE_VISUAL_FEATURES)
            if redaction is not None and self._finder is not None:
                evidence = _held(evidence, HeldPixelData(redaction.reason))
                qc = (*qc, _redaction_material(redaction, data))
            writing = with_markers(
                writing, source, dataset, self._markers[frozenset(chosen)]
            )
            identifiers = self._identifiers(writing, dataset, source)
            return Transformed(
                *_written(source, writing, iod, identifiers, redaction), evidence, qc
            )
        except _Refused as refused:
            reasons = tuple(
                TransformReason.PENDING_EDIT if isinstance(r, PendingEdit) else r
                for r in refused.reasons
            )
            return Sequestered(tuple(dict.fromkeys(reasons)), evidence, qc)


def _pixel_risk(
    dataset: pydicom.Dataset, record: InstanceRecord
) -> tuple[PixelRiskMaterial | SeriesEvidence, ...]:
    """The QC material of the source's indicators of risk in its pixel data.

    The source is assessed, since the Basic Profile removes some of the
    evidence, such as an overlay group whose graphics lie in the pixel data:
    its own indicators, if any, and what it gives the assessment of its
    series, by its source Series Instance UID.
    """
    assessment = assess_pixel_risk(dataset)
    return (
        *((PixelRiskMaterial(assessment),) if assessment.findings else ()),
        SeriesEvidence(record.series, series_evidence(dataset)),
    )


def transform_for(
    preset: str | None = None,
    key: DeidKey | None = None,
    *,
    options: Iterable[str] | None = None,
    cleaning: DescriptorCleaning | None = None,
    iod_tables: IODTables | None = None,
) -> InstanceTransform:
    """Return the run's transform for an enabled preset or custom option set.

    Parameters
    ----------
    preset : str, optional
        As :func:`~pymedphys._dicom.deidentify.policy.select_policy` takes
        it. Defaults to ``"basic"``, unless ``options`` is given.
    key : DeidKey, optional
        The run's key. By default, a new one, so that the run's replacement
        UIDs and pseudonyms match no other run's.
    options : iterable of str, optional
        A custom option set in place of a preset, as
        :func:`~pymedphys._dicom.deidentify.policy.select_policy` takes it
        (D-033).
    cleaning : DescriptorCleaning, optional
        As for :class:`InstanceTransform`: needed for a policy with Clean
        Descriptors, and refused without it.
    iod_tables : IODTables, optional
        As for :class:`InstanceTransform`.

    Raises
    ------
    PolicyError
        As :func:`~pymedphys._dicom.deidentify.policy.select_policy` raises
        it, for a preset or option that is unknown or not enabled, or as
        :class:`InstanceTransform` raises it for ``cleaning``.
    """
    policy = select_policy(preset, options=options)
    return InstanceTransform(
        policy,
        DeidKey.generate() if key is None else key,
        iod_tables,
        cleaning=cleaning,
    )


def _retained(
    source: SourceEvidence, plan: InstancePlan, edits: InstanceEdits
) -> tuple[object, ...]:
    """Return the QC material of each string that the plan keeps (D-017).

    A string that ``edits`` removes after all, such as a private creator
    kept only for private text that cleaning did not write (D-035), is not
    written, so it is left out.

    Raises
    ------
    _Refused
        If a kept value cannot be decoded for review, such as text outside
        ISO 646 where no Specific Character Set applies.
    """
    kept = read_values(source, plan, retained_paths(plan))
    if None in kept.values():
        raise _Refused(TransformReason.UNREVIEWABLE_RETAINED_TEXT)
    removed = {edit.path for edit in edits.edits if edit.kind is EditKind.REMOVE}
    return tuple(item for item in retained_text(plan, kept) if item.path not in removed)


@dataclasses.dataclass(frozen=True)
class _Identifiers:
    """The SOP Instance UID that an output is written with, and its name's values.

    ``names`` gives the Patient ID, Study, Series, and SOP Instance UIDs that
    name the output, by their paths.
    """

    sop_instance_uid: str
    names: Mapping[ElementPath, str]


def _kept_uid(
    dataset: pydicom.Dataset, path: ElementPath, source: SourceEvidence
) -> str | None:
    """Return a kept top-level UID without padding, or None if it is not valid."""
    value = _text(dataset, path, source)
    if not isinstance(value, str):
        return None
    value = normalise_uid(value)
    if not value or value_problem("UI", value):
        return None
    return value


def _written(
    source: SourceEvidence,
    writing: WriterPlan,
    iod: IOD,
    identifiers: _Identifiers,
    redaction: Redaction | None = None,
) -> tuple[PurePosixPath, bytes]:
    """Return the output's path and bytes, verified against the source and IOD.

    Pixel Data that the plan replaces must decode to the source's pixels, or,
    where Clean Pixel Data blacked out ``redaction``'s regions, differ from
    the source's only as that redaction planned.
    """
    path = _output_path(identifiers.names)
    sop_class = _replaced(writing.replacements, _SOP_CLASS)
    if sop_class is None:
        raise _Refused(TransformReason.UNNAMED_OUTPUT)
    try:
        data_set = write_data_set(
            source,
            kept=writing.kept,
            removed=writing.removed,
            replacements=writing.replacements,
        )
        data = write_file_bytes(
            data_set,
            sop_class_uid=sop_class,
            sop_instance_uid=identifiers.sop_instance_uid,
            transfer_syntax_uid=source.transfer_syntax,
        )
    except WriteRefused as refused:
        raise _Refused(refused.reason) from None
    try:
        output = read_source(data)
    except SourceRefused:
        raise _Refused(TransformReason.UNREADABLE_OUTPUT) from None
    try:
        verify_preservation(source, output, writing.expectations)
    except PreservationFailed as failed:
        raise _Refused(failed.reason) from None
    if lost_requirements(source, output, iod, frozenset(writing.replacements)):
        raise _Refused(TransformReason.REQUIRED_ATTRIBUTE_LOST)
    if redaction is not None:
        if redaction_problem(source, output, redaction):
            raise _Refused(TransformReason.REDACTION_MISMATCH)
    elif _PIXEL_DATA in writing.replacements and not same_pixels(source, output):
        raise _Refused(TransformReason.CUT_CHANGED_PIXELS)
    return path, data


def _pixel_digest(writing: WriterPlan, dataset: pydicom.Dataset) -> bytes | None:
    """Return the SHA-256 of the pixel data that the writer's plan writes.

    As :func:`~.face_review.pixel_data_sha256` gives it of the file written,
    each element being the plan's replacement, or the source's where the
    plan keeps it; None where a value is not bytes.
    """
    planned = pydicom.Dataset()
    for tag in PIXEL_DATA_TAGS:
        path = ElementPath((), _tag_text(tag))
        if path in writing.replacements:
            planned.add(writing.replacements[path])
        elif path in writing.kept and tag in dataset:
            planned.add(dataset[tag])
    try:
        return pixel_data_sha256(planned)
    except ValueError:
        return None


def _with_redaction(
    writing: WriterPlan, dataset: pydicom.Dataset, redaction: Redaction | None
) -> WriterPlan:
    """Return the writer's plan with Pixel Data replaced by its redaction.

    The new value is written with the source element's VR, or, where pydicom
    reads it as neither OB nor OW, by Bits Allocated as PS3.5 Section A.1
    gives it for the native transfer syntaxes. Pixel Data without a region
    to black out is kept, and Pixel Data that the plan does not keep is left
    as planned, which :func:`_written` refuses.
    """
    if redaction is None or not redaction.changed or _PIXEL_DATA not in writing.kept:
        return writing
    vr = dataset[0x7FE00010].VR
    if vr not in ("OB", "OW"):
        vr = "OW" if redaction.layout.bits_allocated > 8 else "OB"
    element = pydicom.DataElement(0x7FE00010, vr, redaction.value)
    return dataclasses.replace(
        writing,
        kept=writing.kept - {_PIXEL_DATA},
        replacements={**writing.replacements, _PIXEL_DATA: element},
    )


def _redaction_material(redaction: Redaction, source: bytes) -> RedactionMaterial:
    """The QC material of what Clean Pixel Data did, for the reviewer.

    The source is kept only where a frame has regions, since only those
    frames are shown as received.
    """
    return RedactionMaterial(
        redaction.reason,
        redaction.layout.frames,
        tuple((regions.frame, regions.boxes) for regions in redaction.regions),
        source if redaction.regions else None,
    )


def _held(
    evidence: Coverage | HeldEvidence, held: HeldPixelData | HeldVisualFeatures
) -> HeldEvidence:
    """Return the evidence of an instance that review holds, with ``held``."""
    if isinstance(evidence, HeldEvidence):
        return dataclasses.replace(evidence, held=(*evidence.held, held))
    return HeldEvidence(evidence, (held,))


def _subsets(options: list[str]) -> list[tuple[str, ...]]:
    """Return every subset of ``options``, each in their order."""
    subsets: list[tuple[str, ...]] = [()]
    for option in options:
        subsets += [(*subset, option) for subset in subsets]
    return subsets


def _without_bitstream_metadata(
    writing: WriterPlan, source: SourceEvidence
) -> WriterPlan:
    """Return the writer's plan with kept compressed Pixel Data's metadata
    segments cut, without recompression (Architecture item 7, MIDI-BP-14).

    Where :func:`~.codestreams.without_metadata` cuts something, Pixel Data
    is written as a replacement, and :func:`_written` then shows that every
    frame decodes to the same pixels as its source's. Otherwise it is kept
    byte for byte.

    Raises
    ------
    _Refused
        With the reason of :class:`~.codestreams.CodestreamRefused`.
    """
    if _PIXEL_DATA not in writing.kept:
        return writing
    try:
        value = without_metadata(source)
    except CodestreamRefused as refused:
        raise _Refused(refused.reason) from None
    if value is None:
        return writing
    element = pydicom.DataElement(0x7FE00010, "OB", value, is_undefined_length=True)
    return dataclasses.replace(
        writing,
        kept=writing.kept - {_PIXEL_DATA},
        replacements={**writing.replacements, _PIXEL_DATA: element},
    )


def _output_path(names: Mapping[ElementPath, str]) -> PurePosixPath:
    patient, study, series, instance = (
        names[path] for path in (_PATIENT_ID, _STUDY, _SERIES, _SOP_INSTANCE)
    )
    try:
        return output_names.instance_path(
            patient_id=str(patient),
            study_instance_uid=str(study),
            series_instance_uid=str(series),
            sop_instance_uid=str(instance),
        )
    except output_names.OutputNameError:
        pass
    raise _Refused(TransformReason.UNNAMED_OUTPUT)


def _replaced(
    replacements: Mapping[ElementPath, pydicom.DataElement], path: ElementPath
) -> str | None:
    """Return the one text value that ``path`` is replaced by, if there is one."""
    element = replacements.get(path)
    if element is None or not isinstance(element.value, str):
        return None
    return element.value


def _text(
    dataset: pydicom.Dataset, path: ElementPath, source: SourceEvidence
) -> object:
    """Return the top-level value at ``path``, or ``None`` if it cannot be read."""
    if path not in source:
        return None
    try:
        values = read_element(dataset, path, DEFAULT_CODECS, source=source).values
    except UndecodableElement:
        return None
    return values[0] if len(values) == 1 else None


_Condition = Callable[[Coverage, bytes], ReleaseCondition]


class ReleaseGate:
    """The run's gate: the release condition of the subject's pooled coverage.

    Parameters
    ----------
    condition : callable, optional
        ``(coverage, written) -> ReleaseCondition``. Defaults to
        :func:`~pymedphys._dicom.deidentify.release_gate.release_condition`.

    Notes
    -----
    A release decision releases the file; QC review holds it for review and
    withholding sequesters it, each with the condition's reasons, which are
    :class:`~.release_gate.ReleaseReason` objects naming codes and paths,
    never values. A file of a subject with an instance that gave no evidence
    (:data:`~pymedphys._dicom.deidentify.run.NO_EVIDENCE`) is withheld, with
    :attr:`~.release_gate.ReasonCode.NOT_REPORTED` for the file as a whole,
    since that instance's values may be in it unsearched for (D-027). An
    instance whose evidence is a :class:`HeldEvidence` is held for review,
    with its held ROI Names, visual features, and pixel data first among
    the reasons, unless the condition withholds it. Evidence that is neither a
    :class:`~.release_gate.Coverage` nor a :class:`HeldEvidence` raises
    :class:`TypeError`, which the run takes as an internal error and
    sequesters the file for.

    Each verdict carries, as its QC material, the residual search's findings
    in the file, with the file. What the search leaves out of the instance's
    own values is the transform's material (:func:`omissions_of`), since the
    search covers the subject's other instances' values too.

    A gate merges each subject's coverages once
    (:class:`~.release_gate.SubjectCoverages`), so one gate is made for each
    run.
    """

    def __init__(self, condition: _Condition = release_condition) -> None:
        self._condition = condition
        self._subjects = SubjectCoverages()

    def __repr__(self) -> str:
        return "ReleaseGate()"

    def __call__(
        self, written: bytes, evidence: object, subject: tuple[object, ...]
    ) -> Release | HoldForReview | Sequestered:
        given = tuple(each for each in subject if each is not NO_EVIDENCE)
        coverages = tuple(_coverage(each) for each in (evidence, *given))
        condition = self._condition(self._subjects.merge(coverages[1:]), written)
        held = evidence.held if isinstance(evidence, HeldEvidence) else ()
        # Each value's omissions are its own instance's material, from the
        # transform, so the pooled search's are left out here.
        search = dataclasses.replace(condition.search, not_searched=(), unsearched=())
        qc = (SearchMaterial(search, written),)
        reasons = condition.reasons
        if len(given) < len(subject):
            # An instance of the subject gave no evidence, so its values may be
            # in this file unsearched for (D-027).
            reasons = (*reasons, _SUBJECT_NOT_REPORTED)
        if condition.decision is Decision.WITHHOLD or len(given) < len(subject):
            return Sequestered(reasons, qc=qc)
        if held or condition.decision is Decision.QC_REVIEW:
            return HoldForReview((*held, *condition.reasons), qc)
        return Release(qc)


# An instance of the file's subject whose values could not be collected at all.
_SUBJECT_NOT_REPORTED = ReleaseReason(Decision.WITHHOLD, ReasonCode.NOT_REPORTED)


def _coverage(evidence: object) -> Coverage:
    if isinstance(evidence, HeldEvidence):
        evidence = evidence.coverage
    if not isinstance(evidence, Coverage):
        raise TypeError("the release gate needs the Coverage of each instance")
    return evidence
