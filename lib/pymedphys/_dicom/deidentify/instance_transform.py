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
   checks the file written against its source and the same plan; and
7. :func:`~pymedphys._dicom.deidentify.output_names.instance_path` names the
   file from its replacement Patient ID and UIDs alone (D-016).

Any step that refuses the instance sequesters it with that step's own
value-free reason: a :class:`~.scope.Disposition`, a
:class:`~.source.SourceReason`, the walker's
:class:`~.walker.Sequestration` objects, a
:class:`~.preserving_writer.WriteReason`, a
:class:`~.preservation.PreservationReason`, or a :class:`TransformReason`.
No exception message is kept, since some come from pydicom and can quote a
value.

Whatever the outcome, once the instance has been planned and edited, its
:class:`~.release_gate.Coverage` goes with it as the transform's evidence:
every value that had to be collected for the residual search, those
collected, and those that could not be. :class:`ReleaseGate` is the run's
:class:`~pymedphys._dicom.deidentify.run.Gate`: it pools the coverage of the
file's subject, sequestered instances included, and asks
:func:`~.release_gate.release_condition` about the written file (D-027).

A UID that the pinned tables register, and that U therefore retains, such
as a SOP Class UID, is meant to stay in the output, so it is neither planned
nor collected: the written file is searched only for values that must not
appear in it.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Callable, Mapping
from pathlib import PurePosixPath

from pymedphys._imports import pydicom

from . import output_names
from .edits import Edit, EditKind, InstanceEdits, edit_instance
from .element_rules import ElementRules
from .elements import (
    DEFAULT_CODECS,
    UndecodableElement,
    dataset_codecs,
    new_element,
    read_element,
)
from .file_layout import ElementPath
from .iods import IODTables, load_iod_tables
from .keys import DeidKey
from .policy import Policy
from .preservation import Expectations, PreservationFailed, verify_preservation
from .preserving_writer import WriteRefused, write_data_set, write_file_bytes
from .references import InstanceRecord
from .release_gate import (
    Coverage,
    Decision,
    ReleaseCondition,
    Uncollected,
    release_condition,
)
from .run import HoldForReview, Release, Sequestered, Transformed
from .scope import classify
from .source import SourceEvidence, SourceRefused, read_source
from .uids import UIDOutcome
from .walker import Consumer, InstancePlan, plan_instance

_SOP_CLASS = ElementPath((), "(0008,0016)")
_SOP_INSTANCE = ElementPath((), "(0008,0018)")
_STUDY = ElementPath((), "(0020,000D)")
_SERIES = ElementPath((), "(0020,000E)")
_PATIENT_ID = ElementPath((), "(0010,0020)")


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
    """

    kept: frozenset[ElementPath]
    removed: frozenset[ElementPath]
    replacements: Mapping[ElementPath, pydicom.DataElement] = dataclasses.field(
        repr=False
    )

    @property
    def expectations(self) -> Expectations:
        """What verification expects of the file written from this plan."""
        return Expectations(
            kept=self.kept,
            changed=frozenset(self.replacements),
            removed=self.removed,
        )


def coverage_of(plan: InstancePlan, edits: InstanceEdits) -> Coverage:
    """Return the residual search's coverage of an instance's plan and edits.

    Every element that the plan has residual collection read is planned,
    and each value collected or not collected is carried over, but for an
    element whose every UID U retains.
    """
    retained = {
        edit.path
        for edit in edits.edits
        if edit.uid_outcomes
        and all(outcome is UIDOutcome.RETAINED for outcome in edit.uid_outcomes)
    }
    return Coverage(
        planned=frozenset(
            element.path
            for element in plan.elements
            if Consumer.RESIDUAL_COLLECTION in element.consumers
            and element.path not in retained
        ),
        collected=tuple(
            value for value in edits.source_values if value.source not in retained
        ),
        uncollected=tuple(
            Uncollected(path=missing.path, reason=missing.reason)
            for missing in edits.not_collected
            if missing.path not in retained
        ),
    )


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

    Notes
    -----
    The subject's identity is the instance's own Patient ID with its issuer,
    as the run's first pass records it (``InstanceRecord.patient``). An
    instance without one has no pseudonyms, so its Patient's Name and
    Patient ID edits stay pending and it is sequestered.
    """

    def __init__(
        self, policy: Policy, key: DeidKey, iod_tables: IODTables | None = None
    ) -> None:
        self._rules = ElementRules(policy)
        self._key = key
        self._iods = load_iod_tables() if iod_tables is None else iod_tables

    def __repr__(self) -> str:
        return "InstanceTransform()"

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
        if classification.sequestered or classification.iod is None:
            return Sequestered((classification.disposition,))
        plan = plan_instance(source, self._rules, self._iods.iods[classification.iod])
        edits = edit_instance(source, plan, self._key, record.patient)
        evidence = coverage_of(plan, edits)
        if edits.sequestrations:
            return Sequestered(edits.sequestrations, evidence)
        try:
            return Transformed(*_written(source, plan, edits, codecs), evidence)
        except _Refused as refused:
            return Sequestered(refused.reasons, evidence)


def _written(
    source: SourceEvidence,
    plan: InstancePlan,
    edits: InstanceEdits,
    codecs: tuple[str, ...],
) -> tuple[PurePosixPath, bytes]:
    """Return the output's path and bytes, verified against the source."""
    writing = writer_plan(plan, edits, codecs)
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
    never values. Evidence that is not a :class:`~.release_gate.Coverage`
    raises :class:`TypeError`, which the run takes as an internal error and
    sequesters the file for.
    """

    def __init__(self, condition: _Condition = release_condition) -> None:
        self._condition = condition

    def __repr__(self) -> str:
        return "ReleaseGate()"

    def __call__(
        self, written: bytes, evidence: object, subject: tuple[object, ...]
    ) -> Release | HoldForReview | Sequestered:
        coverages = tuple(each for each in subject if isinstance(each, Coverage))
        if not isinstance(evidence, Coverage) or len(coverages) != len(subject):
            raise TypeError("the release gate needs the Coverage of each instance")
        condition = self._condition(Coverage.merge(*coverages), written)
        if condition.decision is Decision.RELEASE:
            return Release()
        if condition.decision is Decision.QC_REVIEW:
            return HoldForReview(condition.reasons)
        return Sequestered(condition.reasons)
