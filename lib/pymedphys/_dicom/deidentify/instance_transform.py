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

"""De-identify one instance of a run: the run's concrete transform.

:class:`InstanceTransform` is the
:class:`~pymedphys._dicom.deidentify.run.Transform` that a run calls for
each instance it may process. It joins the engine's per-instance steps:

1. :func:`~pymedphys._dicom.deidentify.source.read_source` admits the
   source file, whose every byte must be accounted for;
2. :func:`~pymedphys._dicom.deidentify.scope.classify` decides from its SOP
   Class and transfer syntax whether the release de-identifies it at all;
3. :func:`~pymedphys._dicom.deidentify.walker.plan_instance` gives each
   element its action under the run's policy and the instance's IOD;
4. :func:`~pymedphys._dicom.deidentify.edits.edit_instance` works out what
   each element becomes, with the run's key and the subject's identity, and
   collects the values removed or replaced for the residual search;
5. :func:`writer_plan` turns those edits into what the byte-preserving
   writer takes, and
   :func:`~pymedphys._dicom.deidentify.preserving_writer.write_data_set` and
   :func:`~pymedphys._dicom.deidentify.preserving_writer.write_file_bytes`
   write the file;
6. :func:`~pymedphys._dicom.deidentify.preservation.verify_preservation`
   checks the file written against its source and the same plan, and
   :func:`~pymedphys._dicom.deidentify.iod_conformance.lost_requirements`
   checks that it still holds each attribute that its IOD requires where
   the source held one; and
7. :func:`~pymedphys._dicom.deidentify.output_names.instance_path` names the
   file from its replacement Patient ID and UIDs alone (D-016).

Any step that refuses the instance sequesters it with that step's own
value-free reason: a :class:`~.scope.Disposition`, a
:class:`~.source.SourceReason`, the walker's
:class:`~.walker.Sequestration` objects, a
:class:`~.preserving_writer.WriteReason`, a
:class:`~.preservation.PreservationReason`, or a :class:`TransformReason`,
such as :attr:`TransformReason.PENDING_EDIT` for the edits still to come
that :func:`writer_plan` names by :class:`PendingEdit`.
No exception message is kept, since some come from pydicom and can quote a
value.

Whatever the outcome, once the instance has been planned and edited, its
:class:`~.release_gate.Coverage` goes with it as the transform's evidence:
every value that had to be collected for the residual search, those
collected, and those that could not be. :class:`ReleaseGate` is the run's
:class:`~pymedphys._dicom.deidentify.run.Gate`: it pools the coverage of the
file's subject, sequestered instances included, and asks
:func:`~.release_gate.release_condition` about the written file (D-027).
Where the edits sequester an instance, the values that they did not reach
are uncollected. An instance out of scope whose IOD the pinned tables
define, such as an MR image or a spatial registration, is planned and
edited too when its source is readable, only so that its values are
collected for its subject's search; it is never written. Where
an instance of the subject gives no coverage at all, because its source is
refused, its SOP Class names no IOD of the tables, the transform raises, or
it changed during the run, the gate withholds the file, since its values
could be there unsearched for.

A UID that the pinned tables register, and that U therefore retains, such
as a SOP Class UID, is meant to stay in the output, so it is neither planned
nor collected: the written file is searched only for values that must not
appear in it.
"""

from __future__ import annotations

import copy
import dataclasses
from collections.abc import Callable, Mapping
from pathlib import PurePosixPath

from pymedphys._imports import pydicom

from . import output_names
from .descriptor_cleaning import (
    CLEAN_DESCRIPTORS,
    DescriptorCleaning,
    DescriptorsRefused,
    HeldRoiName,
    clean_descriptors,
    fallback_policy,
)
from .edits import Edit, EditKind, InstanceEdits, edit_instance, read_values
from .element_rules import ElementRules
from .elements import (
    DEFAULT_CODECS,
    UndecodableElement,
    dataset_codecs,
    new_element,
    read_element,
)
from .file_layout import ElementPath
from .iod_conformance import lost_requirements, source_gaps
from .iods import IOD, IODTables, load_iod_tables
from .keys import DeidKey
from .markers import MarkerError, Markers, apply_markers, markers_for
from .method_digest import method_digest
from .policy import DEFAULT_PRESET, Policy, PolicyError, select_policy
from .preservation import Expectations, PreservationFailed, verify_preservation
from .preserving_writer import WriteRefused, write_data_set, write_file_bytes
from .qc_pack import DropReason
from .qc_retained import retained_paths, retained_text
from .reasons import TransformReason
from .reference_graph import ReferenceGraph
from .references import InstanceRecord
from .reviewed_roi_names import ReviewQueue
from .release_gate import (
    Coverage,
    Decision,
    ReasonCode,
    ReleaseCondition,
    ReleaseReason,
    Uncollected,
    release_condition,
)
from .residuals import NotSearched, has_written_constant, not_searched_of
from .run import NO_EVIDENCE, HoldForReview, Release, Sequestered, Transformed
from .pixel_risk import assess_pixel_risk
from .run_qc import Dropped, PixelRiskMaterial, SearchMaterial
from .run_report import ReleaseReporter
from .scope import classify
from .source import SourceEvidence, SourceRefused, read_source
from .uids import UIDOutcome
from .walker import Consumer, InstancePlan, plan_instance
from .written_references import WrittenFinding, verify_written_references

_SOP_CLASS = ElementPath((), "(0008,0016)")
_SOP_INSTANCE = ElementPath((), "(0008,0018)")
_STUDY = ElementPath((), "(0020,000D)")
_SERIES = ElementPath((), "(0020,000E)")
_PATIENT_ID = ElementPath((), "(0010,0020)")


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
    """The evidence of an instance that descriptor cleaning holds for review.

    Attributes
    ----------
    coverage : Coverage
        Its residual search's coverage, pooled with its subject's as any.
    held : tuple of HeldRoiName
        Each ROI Name held, by path and reason.
    """

    coverage: Coverage
    held: tuple[HeldRoiName, ...]


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
    that its collection is incomplete (D-027).
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
    for edit in edits.edits:
        if edit.kind is EditKind.KEEP:
            kept.add(edit.path)
        elif edit.kind is EditKind.REMOVE:
            removed.add(edit.path)
        else:
            replacements[edit.path] = _element(edit, vrs.get(edit.path), codecs)
    return WriterPlan(frozenset(kept), frozenset(removed), replacements)


# The attributes that PS3.15 E.1.1, E.2, and E.3.6 have a de-identifier add
# or update, which apply_markers writes.
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
    present = pydicom.Dataset()
    for tag in MARKER_TAGS:
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
    for tag in MARKER_TAGS:
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


def satisfied_options(policy: Policy) -> tuple[str, ...]:
    """Return the options an instance satisfies by the policy's actions alone.

    Every selected option but Clean Descriptors, which descriptor cleaning
    must satisfy for each instance (D-009), and but any option the policy
    records as unmet.
    """
    unmet = {option for resolution in policy.resolved for option in resolution.unmet}
    return tuple(
        option
        for option in policy.options
        if option != "clean_descriptors" and option not in unmet
    )


def _element(
    edit: Edit, vr: str | None, codecs: tuple[str, ...]
) -> pydicom.DataElement:
    values = () if edit.kind is EditKind.EMPTY else edit.values
    if vr is None:
        raise _Refused(TransformReason.UNWRITABLE_ELEMENT)
    try:
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
        with, which a policy selecting Clean Descriptors needs, and no other
        policy takes. The transform applies the list's decisions as they
        stand when it is made, the version whose keyed digest its markers and
        release report record; a decision recorded later does not apply.
    unvalidated_policy : bool, default False
        Allow a policy that is not enabled, such as a preset whose behaviour
        is not yet validated. For tests and validation runs only; nothing
        that de-identifies data for use sets it.

    Raises
    ------
    PolicyError
        If the policy is not enabled and ``unvalidated_policy`` is not set;
        if ``cleaning`` is given without Clean Descriptors, or left out with
        it; or if the policy's other options cannot be composed into the
        policy whose actions descriptors take where they are not cleaned.

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

    Under Clean Descriptors, :func:`~.descriptor_cleaning.clean_descriptors`
    settles the attributes given C. An instance with a ROI Name held for
    review is written with that name empty, and its evidence is a
    :class:`HeldEvidence`, which :class:`ReleaseGate` holds for review. The
    markers claim Clean Descriptors only for an instance that satisfies it.
    """

    def __init__(
        self,
        policy: Policy,
        key: DeidKey,
        iod_tables: IODTables | None = None,
        *,
        cleaning: DescriptorCleaning | None = None,
        unvalidated_policy: bool = False,
    ) -> None:
        if not (policy.enabled or unvalidated_policy):
            raise PolicyError(
                "the policy is not enabled: no preset's behaviour is validated yet"
            )
        if (CLEAN_DESCRIPTORS in policy.options) != (cleaning is not None):
            raise PolicyError(
                "descriptor cleaning is given exactly when the policy selects "
                "Clean Descriptors"
            )
        if cleaning is not None:
            # One version of the list, for both cleaning and its digest.
            cleaning = dataclasses.replace(
                cleaning, reviewed=cleaning.reviewed.snapshot()
            )
        self._rules = ElementRules(policy)
        self._key = key
        self._cleaning = cleaning
        self._fallback = (
            None if cleaning is None else ElementRules(fallback_policy(policy))
        )
        self._vocabulary = None if cleaning is None else cleaning.vocabulary
        self.review_queue = ReviewQueue()
        nomenclature = None if cleaning is None else cleaning.nomenclature
        reviewed = None if cleaning is None else cleaning.reviewed.keyed_digest(key)
        digest = method_digest(
            policy, vocabulary=nomenclature, reviewed_roi_names=reviewed
        )
        satisfied = satisfied_options(policy)
        self._markers = {
            False: markers_for(policy, digest, satisfied=satisfied),
            True: markers_for(
                policy,
                digest,
                satisfied=satisfied + ((CLEAN_DESCRIPTORS,) if cleaning else ()),
            ),
        }
        self._iods = load_iod_tables() if iod_tables is None else iod_tables
        self.reporter = ReleaseReporter(
            policy, vocabulary=nomenclature, reviewed_roi_names=reviewed
        )

    def __repr__(self) -> str:
        return "InstanceTransform()"

    def written_check(
        self, graph: ReferenceGraph, written: Mapping[int, InstanceRecord]
    ) -> tuple[WrittenFinding, ...]:
        """Check what a run with this transform wrote against its first pass.

        The reference graph's second pass under the transform's key, for
        :func:`~pymedphys._dicom.deidentify.run.run`'s ``written_check``, as
        :func:`~pymedphys._dicom.deidentify.written_references.verify_written_references`
        makes it.
        """
        return verify_written_references(self._key, graph, written)

    def __call__(
        self, data: bytes, record: InstanceRecord
    ) -> Transformed | Sequestered:
        try:
            source = read_source(data)
        except SourceRefused as refused:
            return Sequestered((refused.reason,))
        try:
            dataset = source.dataset()
            codecs = dataset_codecs(dataset, source=source)
        except (SourceRefused, UndecodableElement):
            codecs = DEFAULT_CODECS
            dataset = None
        classification = classify(
            _text(dataset, _SOP_CLASS, source), source.transfer_syntax
        )
        if classification.iod is None or (
            classification.sequestered and classification.iod not in self._iods.iods
        ):
            return Sequestered((classification.disposition,))
        iod = self._iods.iods[classification.iod]
        risk: tuple[object, ...] = _pixel_risk(dataset)
        if not classification.sequestered:
            risk += source_gaps(source, iod)
        plan = plan_instance(source, self._rules, iod)
        edits = edit_instance(source, plan, self._key, record.patient)
        evidence: Coverage | HeldEvidence = coverage_of(plan, edits)
        if classification.sequestered or edits.sequestrations:
            # An instance out of scope is planned and edited only so that
            # its identifiers are collected for its subject's search (D-027).
            return Sequestered(
                (classification.disposition,)
                if classification.sequestered
                else edits.sequestrations,
                evidence,
                (*risk, *dropped_of(edits), *omissions_of(evidence)),
            )
        satisfied = False
        retained: frozenset[ElementPath] = frozenset()
        names: tuple[object, ...] = ()
        if self._cleaning is not None and self._fallback is not None:
            fallback = self._fallback

            def fallen_back() -> InstanceEdits:
                return edit_instance(
                    source,
                    plan_instance(source, fallback, iod),
                    self._key,
                    record.patient,
                )

            try:
                cleaned = clean_descriptors(
                    edits,
                    self._cleaning,
                    self._vocabulary,
                    self.review_queue,
                    fallen_back,
                )
            except DescriptorsRefused as refused:
                return Sequestered(
                    (refused.reason,),
                    evidence,
                    (*risk, *dropped_of(edits), *omissions_of(evidence)),
                )
            edits, satisfied = cleaned.edits, cleaned.satisfied
            retained = frozenset(cleaned.retained)
            names = cleaned.qc
            evidence = coverage_of(plan, edits, retained)
            if cleaned.held:
                evidence = HeldEvidence(evidence, cleaned.held)
        qc = (*risk, *dropped_of(edits, retained), *omissions_of(evidence), *names)
        try:
            qc = (*qc, *_retained(source, plan))
            writing = with_markers(
                writer_plan(plan, edits, codecs),
                source,
                dataset,
                self._markers[satisfied],
            )
            return Transformed(*_written(source, writing, iod), evidence, qc)
        except _Refused as refused:
            reasons = tuple(
                TransformReason.PENDING_EDIT if isinstance(r, PendingEdit) else r
                for r in refused.reasons
            )
            return Sequestered(tuple(dict.fromkeys(reasons)), evidence, qc)


def _pixel_risk(dataset: pydicom.Dataset | None) -> tuple[PixelRiskMaterial, ...]:
    """The QC material of the source's indicators of risk in its pixel data.

    The source is assessed, since the Basic Profile removes some of the
    evidence, such as an overlay group whose graphics lie in the pixel data.
    A source whose data set does not decode gives none: the walker and the
    gate decide what becomes of it.
    """
    if dataset is None:
        return ()
    assessment = assess_pixel_risk(dataset)
    return (PixelRiskMaterial(assessment),) if assessment.findings else ()


def transform_for(
    preset: str = DEFAULT_PRESET,
    key: DeidKey | None = None,
    *,
    cleaning: DescriptorCleaning | None = None,
    iod_tables: IODTables | None = None,
) -> InstanceTransform:
    """Return the run's transform for an enabled preset.

    Parameters
    ----------
    preset : str, optional
        As :func:`~pymedphys._dicom.deidentify.policy.select_policy` takes
        it. Defaults to ``"basic"``.
    key : DeidKey, optional
        The run's key. By default, a new one, so that the run's replacement
        UIDs and pseudonyms match no other run's.
    cleaning : DescriptorCleaning, optional
        As for :class:`InstanceTransform`: needed for a preset with Clean
        Descriptors, and refused without it.
    iod_tables : IODTables, optional
        As for :class:`InstanceTransform`.

    Raises
    ------
    PolicyError
        As :func:`~pymedphys._dicom.deidentify.policy.select_policy` raises
        it, for a preset that is unknown or not enabled, or as
        :class:`InstanceTransform` raises it for ``cleaning``.
    """
    policy = select_policy(preset)
    return InstanceTransform(
        policy,
        DeidKey.generate() if key is None else key,
        iod_tables,
        cleaning=cleaning,
    )


def _retained(source: SourceEvidence, plan: InstancePlan) -> tuple[object, ...]:
    """Return the QC material of each string that the plan keeps (D-017).

    Raises
    ------
    _Refused
        If a kept value cannot be decoded for review, such as text outside
        ISO 646 where no Specific Character Set applies.
    """
    kept = read_values(source, plan, retained_paths(plan))
    if None in kept.values():
        raise _Refused(TransformReason.UNREVIEWABLE_RETAINED_TEXT)
    return retained_text(plan, kept)


def _written(
    source: SourceEvidence, writing: WriterPlan, iod: IOD
) -> tuple[PurePosixPath, bytes]:
    """Return the output's path and bytes, verified against the source and IOD."""
    path = _output_path(writing.replacements)
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
            sop_instance_uid=path.stem,
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
    return path, data


def _output_path(
    replacements: Mapping[ElementPath, pydicom.DataElement],
) -> PurePosixPath:
    values = [
        _replaced(replacements, path)
        for path in (_PATIENT_ID, _STUDY, _SERIES, _SOP_INSTANCE)
    ]
    patient, study, series, instance = values
    if None in values:
        raise _Refused(TransformReason.UNNAMED_OUTPUT)
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
    dataset: pydicom.Dataset | None, path: ElementPath, source: SourceEvidence
) -> object:
    """Return the top-level value at ``path``, or ``None`` if it cannot be read."""
    if dataset is None or path not in source:
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
    instance whose evidence is a :class:`HeldEvidence` is
    held for review, with its held ROI Names first among the reasons, unless
    the condition withholds it. Evidence that is neither a
    :class:`~.release_gate.Coverage` nor a :class:`HeldEvidence` raises
    :class:`TypeError`, which the run takes as an internal error and
    sequesters the file for.

    Each verdict carries, as its QC material, the residual search's findings
    in the file, with the file. What the search leaves out of the instance's
    own values is the transform's material (:func:`omissions_of`), since the
    search covers the subject's other instances' values too.
    """

    def __init__(self, condition: _Condition = release_condition) -> None:
        self._condition = condition

    def __repr__(self) -> str:
        return "ReleaseGate()"

    def __call__(
        self, written: bytes, evidence: object, subject: tuple[object, ...]
    ) -> Release | HoldForReview | Sequestered:
        given = tuple(each for each in subject if each is not NO_EVIDENCE)
        coverages = tuple(_coverage(each) for each in (evidence, *given))
        condition = self._condition(Coverage.merge(*coverages[1:]), written)
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
