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

"""Clean Descriptors in the transform: ROI Names cleaned, other descriptors not.

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
  action under the policy without Clean Descriptors, so the instance does
  not satisfy the option and does not claim it.

An instance satisfies Clean Descriptors only where every attribute given C
was a ROI Name, and none was held or emptied without review. A ROI Name
written with a value is retained, so its source value is left out of the
residual search, as D-027 has retained values dropped from it.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Callable, Sequence

from pymedphys._nomenclature import tg263

from .edits import Edit, EditKind, InstanceEdits
from .file_layout import ElementPath
from .policy import Policy, compose_custom_policy, compose_policy
from .reviewed_roi_names import (
    CleanedRoiName,
    Outcome,
    ReviewedNames,
    ReviewQueue,
    clean_roi_names,
)
from .roi_names import Reason, RoiNameVocabulary

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


class DescriptorReason(enum.Enum):
    """Why descriptor cleaning sequesters an instance."""

    # a ROI Name whose value could not be decoded
    UNDECODABLE_ROI_NAME = "undecodable-roi-name"
    # an attribute given C whose action without Clean Descriptors is still
    # to come, or under which the instance would be sequestered
    UNSETTLED_DESCRIPTOR = "unsettled-descriptor"


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
class HeldRoiName:
    """A ROI Name held for review, by its path and reason, never its value."""

    path: ElementPath
    reason: Reason


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
        Whether the instance satisfies Clean Descriptors.
    retained : frozenset of ElementPath
        The ROI Names written with a value, which the residual search leaves
        out.
    """

    edits: InstanceEdits
    held: tuple[HeldRoiName, ...]
    satisfied: bool
    retained: frozenset[ElementPath]


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
    satisfied = not others
    if names:
        results = _cleaned_names(edits, names, cleaning, vocabulary, queue)
        for edit, result in zip(names, results):
            if result.outcome is Outcome.HELD:
                assert result.held_because is not None
                held.append(HeldRoiName(edit.path, result.held_because))
            satisfied = satisfied and result.outcome in _REVIEWED
            if result.value:
                retained.add(edit.path)
                settled[edit.path] = dataclasses.replace(
                    edit, kind=EditKind.REPLACE, values=(result.value,)
                )
            else:
                settled[edit.path] = dataclasses.replace(
                    edit, kind=EditKind.EMPTY, values=()
                )
    if others:
        settled.update(_fallen_back(others, fallback()))
    return CleanedDescriptors(
        dataclasses.replace(
            edits, edits=tuple(settled.get(edit.path, edit) for edit in edits.edits)
        ),
        tuple(held),
        satisfied,
        frozenset(retained),
    )


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
    queue: ReviewQueue,
) -> tuple[CleanedRoiName, ...]:
    undecoded = {missing.path for missing in edits.not_collected}
    if any(edit.path in undecoded for edit in names):
        raise DescriptorsRefused(DescriptorReason.UNDECODABLE_ROI_NAME)
    values = {value.source: value.value for value in edits.source_values}
    texts = []
    for edit in names:
        value = values.get(edit.path, "")
        if not isinstance(value, str):
            raise DescriptorsRefused(DescriptorReason.UNDECODABLE_ROI_NAME)
        texts.append(value)
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
    queue.add(texts, results)
    return results


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
