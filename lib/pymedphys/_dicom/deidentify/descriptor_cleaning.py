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

"""Clean Descriptors in the transform: ROI Names cleaned, others removed or replaced.

Under a policy that selects the Clean Descriptors Option, the edits leave
each attribute that Table E.1-1 gives C pending (D-009). This module settles
them for one instance:

- Each ROI Name (3006,0026) of Structure Set ROI Sequence (3006,0020) is
  cleaned in both tiers by
  :func:`~pymedphys._dicom.deidentify.reviewed_roi_names.clean_roi_names`:
  renamed in the TG-263 vocabulary's spelling, or given a reviewer's
  decision from the custodian's reviewed-names list. A name the list does
  not cover, or whose decision would echo an identifier or duplicate
  another name, is held for review, and written empty in the staged file,
  which is not released (D-027); the user may instead choose to empty such
  names so that the run proceeds. The identifiers checked are the decoded
  source values of every person name, Patient ID, Issuer of Patient ID, and
  Other Patient IDs that the edits collected.
- Every other attribute given C, which D-009 does not yet clean, takes its
  action under the policy without Clean Descriptors. Where that action
  removes or replaces it, the instance still satisfies the option, since
  PS3.15 E.3.5 specifies what the option removes, not what it retains, and
  E.1.1 makes Table E.1-1 the minimum actions; where it keeps it, the
  instance does not.

An instance satisfies Clean Descriptors only where no ROI Name was held or
emptied without review, and no other attribute given C was kept. A ROI Name
kept as it is, or renamed in the vocabulary's spelling, which the search,
ignoring case, could otherwise find in what is written, is retained, so its
source value is left out of the residual search, as D-027 has retained
values dropped from it. A mapped name's source is still searched, since a
reviewer's replacement need not resemble it.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence

from pymedphys._nomenclature import tg263

from .edits import Edit, EditKind, InstanceEdits
from .file_layout import ElementPath
from .policy import Policy, compose_custom_policy, compose_policy
from .qc_pack import RoiNameOutcome
from .reasons import DescriptorReason, HeldRoiName
from .reviewed_roi_names import (
    CleanedRoiName,
    Outcome,
    ReviewedNames,
    ReviewQueue,
    clean_roi_names,
)
from .roi_names import RoiNameVocabulary
from .run_qc import RetainedText, RoiNameMaterial

CLEAN_DESCRIPTORS = "clean_descriptors"
_ROI_SEQUENCE = "(3006,0020)"
_ROI_NAME = "(3006,0026)"
# Identifiers that are not person names: Patient ID, Issuer of Patient ID,
# and Other Patient IDs, anywhere in the data set, such as in Other Patient
# IDs Sequence (0010,1002).
_IDENTIFIER_TAGS = frozenset({"(0010,0020)", "(0010,0021)", "(0010,1000)"})
_REVIEWED = frozenset(
    {Outcome.RENAMED, Outcome.EMPTY, Outcome.KEPT, Outcome.MAPPED, Outcome.EMPTIED}
)
# The outcomes whose written name the residual search, which ignores case,
# could find for its source value.
_WRITES_ITS_SOURCE = frozenset({Outcome.RENAMED, Outcome.KEPT})


@dataclasses.dataclass(frozen=True)
class DescriptorCleaning:
    """What a run cleans descriptors with. Its ``repr`` shows neither input.

    Attributes
    ----------
    nomenclature : ~pymedphys._nomenclature.tg263.Nomenclature or None
        A published edition of TG-263, such as
        ``pymedphys._nomenclature.tg263_published.load()`` gives, or None,
        in which case every ROI Name needs a reviewed decision. The method
        digest covers the same object.
    reviewed : ReviewedNames
        The custodian's reviewed-names list for the site or project, which
        may be :meth:`ReviewedNames.empty`.
    empty_held : bool
        Whether to empty a ROI Name that would be held for review, as the
        user may choose explicitly so that the run proceeds.

    Raises
    ------
    TypeError
        If an attribute is not of its type.
    ValueError
        If ``nomenclature`` is not a published edition of TG-263, for any
        reason :class:`~.roi_names.RoiNameVocabulary` gives.
    """

    nomenclature: tg263.Nomenclature | None = dataclasses.field(repr=False)
    reviewed: ReviewedNames = dataclasses.field(repr=False)
    empty_held: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.reviewed, ReviewedNames):
            raise TypeError("reviewed must be ReviewedNames")
        if not isinstance(self.empty_held, bool):
            raise TypeError("empty_held must be True or False")
        if self.nomenclature is not None:
            RoiNameVocabulary(self.nomenclature)  # checks it is published

    @property
    def vocabulary(self) -> RoiNameVocabulary | None:
        """The vocabulary that the automatic tier matches against."""
        if self.nomenclature is None:
            return None
        return RoiNameVocabulary(self.nomenclature)


@dataclasses.dataclass(frozen=True)
class CleanedDescriptors:
    """An instance's edits with every attribute given C settled.

    Attributes
    ----------
    edits : InstanceEdits
        The edits, with no edit pending for an attribute given C.
    held : tuple of HeldRoiName
        Each ROI Name held for review, in file order; the instance is not to
        be released while there is one.
    satisfied : bool
        Whether the instance satisfies Clean Descriptors: no ROI Name held
        or emptied without review, and no other attribute given C kept.
    retained : frozenset of ElementPath
        The ROI Names written with a value, which the residual search leaves
        out.
    qc : tuple
        The QC pack's material of the instance's ROI Names: what was written
        for each, as :class:`~.run_qc.RoiNameMaterial`, and each kept source
        name as :class:`~.run_qc.RetainedText`, in file order. Left out of
        the ``repr``, since it holds source names.
    """

    edits: InstanceEdits
    held: tuple[HeldRoiName, ...]
    satisfied: bool
    retained: frozenset[ElementPath]
    qc: tuple[RoiNameMaterial | RetainedText, ...] = dataclasses.field(
        default=(), repr=False
    )


class DescriptorsRefused(Exception):
    """Descriptor cleaning sequesters the instance, for a value-free reason."""

    def __init__(self, reason: DescriptorReason) -> None:
        super().__init__(reason)
        self.reason = reason


def fallback_policy(policy: Policy) -> Policy:
    """Return the policy without Clean Descriptors, whose actions apply instead.

    Raises
    ------
    PolicyError
        If the other options cannot be composed into a policy, as for
        ``tps-import``, whose conflicts only that preset resolves.
    """
    if policy.preset == "basic-clean-descriptors":
        return compose_policy("basic")
    return compose_custom_policy(
        option for option in policy.options if option != CLEAN_DESCRIPTORS
    )


def clean_descriptors(
    edits: InstanceEdits,
    cleaning: DescriptorCleaning,
    vocabulary: RoiNameVocabulary | None,
    queue: ReviewQueue,
    fallback: Callable[[], InstanceEdits],
) -> CleanedDescriptors:
    """Settle each edit that the policy's C leaves pending in one instance.

    Parameters
    ----------
    edits : InstanceEdits
        The instance's edits, with none sequestering it.
    cleaning : DescriptorCleaning
    vocabulary : RoiNameVocabulary or None
        ``cleaning.vocabulary``, built once for the run.
    queue : ReviewQueue
        Given the instance's ROI Names and what is written for each, for
        the confidential QC material.
    fallback : callable
        Returns the instance's edits under :func:`fallback_policy`; called
        only where an attribute other than ROI Name is given C.

    Raises
    ------
    DescriptorsRefused
        Where a ROI Name could not be decoded, or the fallback leaves an
        attribute given C unsettled or sequesters the instance.
    """
    pending = [
        edit
        for edit in edits.edits
        if edit.kind is EditKind.PENDING and edit.action == "C"
    ]
    names = [edit for edit in pending if _is_roi_name(edit.path)]
    others = [edit for edit in pending if not _is_roi_name(edit.path)]
    settled: dict[ElementPath, Edit] = {}
    held: list[HeldRoiName] = []
    retained: set[ElementPath] = set()
    qc: list[RoiNameMaterial | RetainedText] = []
    satisfied = True
    if names:
        texts, results = _cleaned_names(edits, names, cleaning, vocabulary)
        for edit, text, result in zip(names, texts, results):
            qc.extend(_material(edit.path, text, result))
            if result.outcome is Outcome.HELD:
                assert result.held_because is not None
                held.append(HeldRoiName(edit.path, result.held_because))
            satisfied = satisfied and result.outcome in _REVIEWED
            if result.value and result.outcome in _WRITES_ITS_SOURCE:
                retained.add(edit.path)
            if result.value:
                settled[edit.path] = dataclasses.replace(
                    edit, kind=EditKind.REPLACE, values=(result.value,)
                )
            else:
                settled[edit.path] = dataclasses.replace(
                    edit, kind=EditKind.EMPTY, values=()
                )
    if others:
        instead = _fallen_back(others, fallback())
        settled.update(instead)
        # A descriptor that its action without the option removes or
        # replaces still meets it, since E.3.5 specifies what the option
        # removes, not what it retains; one that the action keeps does not.
        satisfied = satisfied and all(
            edit.kind is not EditKind.KEEP for edit in instead.values()
        )
    if names:
        # Only once the instance is settled, so that a refused instance adds
        # nothing to the review.
        queue.add(texts, results)
    return CleanedDescriptors(
        dataclasses.replace(
            edits, edits=tuple(settled.get(edit.path, edit) for edit in edits.edits)
        ),
        tuple(held),
        satisfied,
        frozenset(retained),
        tuple(qc),
    )


def _material(
    path: ElementPath, source: str, result: CleanedRoiName
) -> tuple[RoiNameMaterial | RetainedText, ...]:
    """Return the QC pack's material of one cleaned ROI Name."""
    material = RoiNameMaterial(
        path,
        source,
        RoiNameOutcome(result.outcome.value),
        result.held_because,
        result.value,
    )
    if result.outcome is Outcome.KEPT and result.value:
        return (material, RetainedText(result.value, path))
    return (material,)


def _is_roi_name(path: ElementPath) -> bool:
    return (
        path.tag == _ROI_NAME
        and len(path.items) == 1
        and path.items[0][0] == _ROI_SEQUENCE
    )


def _cleaned_names(
    edits: InstanceEdits,
    names: Sequence[Edit],
    cleaning: DescriptorCleaning,
    vocabulary: RoiNameVocabulary | None,
) -> tuple[list[str], tuple[CleanedRoiName, ...]]:
    undecoded = {missing.path for missing in edits.not_collected}
    if any(edit.path in undecoded for edit in names):
        raise DescriptorsRefused(DescriptorReason.UNDECODABLE_ROI_NAME)
    values = {value.source: value.value for value in edits.source_values}
    texts = []
    for edit in names:
        # A name that was not collected is not taken as empty, which would
        # write it empty and count it as reviewed.
        value = values.get(edit.path)
        if not isinstance(value, str):
            raise DescriptorsRefused(DescriptorReason.UNDECODABLE_ROI_NAME)
        texts.append(value)
    # Only the values that the edits collected: under every preset, each
    # person name and patient identifier is removed or replaced, so all are
    # collected. An option that keeps one would need to collect it here too.
    identifiers = [
        value.value
        for value in edits.source_values
        if isinstance(value.value, str)
        and (value.vr == "PN" or value.source.tag in _IDENTIFIER_TAGS)
    ]
    results = clean_roi_names(
        texts,
        vocabulary,
        cleaning.reviewed,
        identifiers=identifiers,
        empty_held=cleaning.empty_held,
    )
    return texts, results


def _fallen_back(
    others: Sequence[Edit], fallback: InstanceEdits
) -> dict[ElementPath, Edit]:
    if fallback.sequestrations:
        raise DescriptorsRefused(DescriptorReason.UNSETTLED_DESCRIPTOR)
    by_path = {edit.path: edit for edit in fallback.edits}
    settled = {}
    for edit in others:
        instead = by_path.get(edit.path)
        if instead is None or instead.kind is EditKind.PENDING:
            raise DescriptorsRefused(DescriptorReason.UNSETTLED_DESCRIPTOR)
        settled[edit.path] = instead
    return settled
