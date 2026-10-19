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

"""Clean Descriptors in the transform: ROI Names and free text cleaned, others removed or replaced.

Under a policy that selects the Clean Descriptors Option, the edits leave
each attribute that Table E.1-1 gives C pending (D-009), and the cleaners of
the selected options settle those that they clean
(:mod:`~pymedphys._dicom.deidentify.cleaners`, D-034). This module settles
the rest for one instance:

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
  Other Patient IDs that the edits collected. An institutional list, if
  the run has one, renames nothing: a held name is given the list's names
  that it matches, for its reviewer.
- Each value of a free-text descriptor, one of
  :func:`~pymedphys._dicom.deidentify.reviewed_descriptors.descriptor_attributes`,
  is given the decision of the custodian's reviewed descriptors list, or,
  for a technique descriptor that the list does not cover, kept where it is
  made only of words of the reviewed technique vocabulary (D-036), by
  :func:`~pymedphys._dicom.deidentify.reviewed_descriptors.clean_descriptor_values`.
  What a kept or mapped value would write is checked for echoes of the same
  identifiers as ROI Names. An element is written with what cleaning gives
  its values where no value is left uncleaned, at least one is written with
  text, and no kept value is beside one that a reviewer mapped or emptied.
  Every other
  element takes its action under the policy without Clean Descriptors, as
  below, and its values are listed for review, so that a reviewer can
  record decisions for later runs. A descriptor that another selected
  option's cleaner cleans, such as Allergies (0010,2110) under Retain
  Patient Characteristics, is left to that cleaner, and what it leaves
  pending is not cleaned here (D-038).
- Under the Retain Safe Private Option, each value of private text that a
  safe private rule retains, which the plan gives C
  (:mod:`~pymedphys._dicom.deidentify.retained_private`), is cleaned in the
  same way by the reviewed descriptors list's decisions on its private
  attribute's key (:attr:`~.walker.InstancePlan.private_texts`), never by
  the technique vocabulary, where the edits collected it as its VR and
  character set read it. Every other such value, including one read as
  ISO 8859-1 since no Specific Character Set applies, is removed, as it is
  without Clean Descriptors, and so is a private creator that the
  instance kept only for text that is removed.
- Every other attribute given C takes its action under the policy without
  Clean Descriptors. Where that action removes or replaces it, the instance
  still satisfies the option, since PS3.15 E.3.5 specifies what the option
  removes, not what it retains, and E.1.1 makes Table E.1-1 the minimum
  actions; where it keeps it, the instance does not.

An instance satisfies Clean Descriptors only where no ROI Name was held or
emptied without review, and no other attribute given C was kept but by a
reviewer's decision or the technique vocabulary. A ROI Name kept as it is,
or renamed in the vocabulary's spelling, which the search, ignoring case,
could otherwise find in what is written, is retained, so its source value is
left out of the residual search, as D-027 has retained values dropped from
it, and so is a descriptor with a kept value. A mapped name's or value's
source is still searched, since a reviewer's replacement need not resemble
it, and so is an emptied value's; that is why neither is written beside a
kept value.
"""

from __future__ import annotations

import dataclasses
import functools
import types
from collections.abc import Callable, Collection, Mapping, Sequence

from pymedphys._nomenclature import roi_list, tg263

from .edits import Edit, EditKind, InstanceEdits
from .file_layout import ElementPath
from .policy import Policy, compose_custom_policy, compose_policy
from .qc_pack import RoiNameOutcome
from .reasons import DescriptorReason, HeldRoiName
from .retained_private import creator_of, is_private, is_private_creator
from .reviewed_descriptors import (
    CleanedDescriptor,
    ReviewedDescriptors,
    clean_descriptor_values,
    descriptor_vr,
)
from .reviewed_descriptors import Outcome as DescriptorOutcome
from .reviewed_roi_names import (
    CleanedRoiName,
    Outcome,
    ReviewedNames,
    ReviewQueue,
    clean_roi_names,
)
from .roi_names import InstitutionalNames, RoiNameVocabulary
from .run_qc import DescriptorMaterial, RetainedText, RoiNameMaterial
from .technique_descriptors import TechniqueVocabulary, load_technique_vocabulary
from .walker import InstancePlan

CLEAN_DESCRIPTORS = "clean_descriptors"
# No private text to clean.
_NO_PRIVATE_TEXTS: Mapping[ElementPath, str] = types.MappingProxyType({})
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
# The VRs whose values a backslash separates (PS3.5 Section 6.2).
_MULTI_VALUED = frozenset({"SH", "LO", "UC"})
# The outcomes of a descriptor value that write the source value itself.
_KEEPS_ITS_SOURCE = frozenset(
    {DescriptorOutcome.KEPT, DescriptorOutcome.KEPT_BY_VOCABULARY}
)


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
    institutional : ~pymedphys._nomenclature.roi_list.RoiList or None
        An institutional list of ROI names, converted from CSV, or None. It
        renames nothing: a held name that matches one of its names is still
        held, and the QC pack shows its reviewer the names it matched
        (D-009). Since it changes no value written, the method digest does
        not cover it.
    reviewed_descriptors : ReviewedDescriptors
        The custodian's reviewed descriptors list for the site or project,
        by default :meth:`ReviewedDescriptors.empty`.
    technique : TechniqueVocabulary or None
        The reviewed technique vocabulary (D-036), by default the one that
        PyMedPhys bundles, or None, in which case no descriptor value is
        kept without a reviewer's decision. The method digest covers it by
        its SHA-256.

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
    institutional: roi_list.RoiList | None = dataclasses.field(default=None, repr=False)
    reviewed_descriptors: ReviewedDescriptors = dataclasses.field(
        default_factory=ReviewedDescriptors.empty, repr=False
    )
    technique: TechniqueVocabulary | None = dataclasses.field(
        default_factory=load_technique_vocabulary, repr=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.reviewed, ReviewedNames):
            raise TypeError("reviewed must be ReviewedNames")
        if not isinstance(self.reviewed_descriptors, ReviewedDescriptors):
            raise TypeError("reviewed_descriptors must be ReviewedDescriptors")
        if self.technique is not None and not isinstance(
            self.technique, TechniqueVocabulary
        ):
            raise TypeError("technique must be a TechniqueVocabulary or None")
        if not isinstance(self.empty_held, bool):
            raise TypeError("empty_held must be True or False")
        if self.institutional is not None and not isinstance(
            self.institutional, roi_list.RoiList
        ):
            raise TypeError("institutional must be a converted institutional list")
        if self.nomenclature is not None:
            RoiNameVocabulary(self.nomenclature)  # checks it is published

    @property
    def vocabulary(self) -> RoiNameVocabulary | None:
        """The vocabulary that the automatic tier matches against."""
        if self.nomenclature is None:
            return None
        return RoiNameVocabulary(self.nomenclature)

    @functools.cached_property
    def institutional_names(self) -> InstitutionalNames | None:
        """The institutional list's names, indexed once, for held names to match."""
        if self.institutional is None:
            return None
        return InstitutionalNames(self.institutional)


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
        The ROI Names written with a value, and the descriptors written with
        a kept value, which the residual search leaves out.
    qc : tuple
        The QC pack's material of the instance's ROI Names and free-text
        descriptors: what was written for each name, as
        :class:`~.run_qc.RoiNameMaterial`, and for each descriptor, as
        :class:`~.run_qc.DescriptorMaterial`, and each kept source name or
        descriptor value as :class:`~.run_qc.RetainedText`. Left out of the
        ``repr``, since it holds source values.
    """

    edits: InstanceEdits
    held: tuple[HeldRoiName, ...]
    satisfied: bool
    retained: frozenset[ElementPath]
    qc: tuple[RoiNameMaterial | DescriptorMaterial | RetainedText, ...] = (
        dataclasses.field(default=(), repr=False)
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


def clean_descriptors(  # pylint: disable = too-many-locals
    edits: InstanceEdits,
    cleaning: DescriptorCleaning,
    vocabulary: RoiNameVocabulary | None,
    queue: ReviewQueue,
    fallback: Callable[[], InstanceEdits],
    *,
    cleaned_elsewhere: Collection[str],
    private_texts: Mapping[ElementPath, str] = _NO_PRIVATE_TEXTS,
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
        only where an attribute given C is neither a ROI Name nor a
        descriptor that cleaning writes.
    cleaned_elsewhere : collection of str
        The tags of the attributes that the cleaners of the policy's other
        options clean (:func:`~.cleaners.cleaners_for`). A descriptor among
        them that its cleaner left pending is not cleaned, so it takes its
        action without Clean Descriptors, which is that other option's C, so
        it is left unsettled, as for Retain Patient Characteristics (D-038).
    private_texts : mapping of ElementPath to str, optional
        The key of each private element whose text the plan cleans, from
        :attr:`~.walker.InstancePlan.private_texts`. Defaults to none.

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
    identifiers = _identifiers(edits)
    texts_of = _descriptor_texts(edits, [edit.path for edit in others], private_texts)
    described = {
        edit.path: clean_descriptor_values(
            private_texts.get(edit.path, edit.path.tag),
            texts_of[edit.path],
            cleaning.reviewed_descriptors,
            identifiers=identifiers,
            vocabulary=cleaning.technique,
        )
        for edit in others
        if edit.path in texts_of and edit.path.tag not in cleaned_elsewhere
    }
    settled: dict[ElementPath, Edit] = {}
    held: list[HeldRoiName] = []
    retained: set[ElementPath] = set()
    qc: list[RoiNameMaterial | DescriptorMaterial | RetainedText] = []
    satisfied = True
    if names:
        texts, results = _cleaned_names(edits, names, cleaning, vocabulary, identifiers)
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
    cleaned: dict[ElementPath, Edit] = {}
    for edit in others:
        values = _written(described.get(edit.path, ()))
        if values is not None:
            cleaned[edit.path] = dataclasses.replace(
                edit, kind=EditKind.REPLACE, values=values
            )
    settled.update(cleaned)
    others = [edit for edit in others if edit.path not in cleaned]
    if others:
        without = fallback()
        instead = _fallen_back(others, without)
        settled.update(instead)
        settled.update(_creators_left(edits, settled, without))
        # A descriptor that its action without the option removes or
        # replaces still meets it, since E.3.5 specifies what the option
        # removes, not what it retains; one that the action keeps does not.
        satisfied = satisfied and all(
            edit.kind is not EditKind.KEEP for edit in instead.values()
        )
    for path, outcomes in described.items():
        # A cleaned descriptor in a sequence that another's action removes
        # (D-020) goes with it.
        applied = path in cleaned and settled[path] is cleaned[path]
        qc.append(
            DescriptorMaterial(
                path,
                tuple(texts_of[path]),
                outcomes,
                applied,
                private_texts.get(path),
            )
        )
        kept = [
            result.value
            for result in outcomes
            if applied and result.outcome in _KEEPS_ITS_SOURCE and result.value
        ]
        if kept:
            retained.add(path)
            qc.extend(RetainedText(value, path) for value in kept)
    # The plan collects each private creator that it keeps where it cleans
    # private text, since a creator can be removed with that text; one that
    # is still written is retained.
    collected = {value.source for value in edits.source_values}
    retained.update(
        edit.path
        for edit in edits.edits
        if edit.path in collected
        and is_private_creator(edit.path.tag)
        and settled.get(edit.path, edit).kind is not EditKind.REMOVE
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
        result.institutional_matches,
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


def _identifiers(edits: InstanceEdits) -> list[str]:
    """Return the identifiers that cleaned values are checked for echoes of.

    Only the values that the edits collected: under every preset, each
    person name and patient identifier is removed or replaced, so all are
    collected. An option that keeps one would need to collect it here too.
    """
    return [
        value.value
        for value in edits.source_values
        if isinstance(value.value, str)
        and (value.vr == "PN" or value.source.tag in _IDENTIFIER_TAGS)
    ]


def _descriptor_texts(
    edits: InstanceEdits,
    paths: Sequence[ElementPath],
    private_texts: Mapping[ElementPath, str] = _NO_PRIVATE_TEXTS,
) -> dict[ElementPath, list[str]]:
    """Return the values of each free-text descriptor that cleaning can read.

    A descriptor is read where the edits collected its decoded source value
    in the VR that the data dictionary gives it, or, for private text, its
    rule, split at backslashes where that VR holds several values. Any
    other, such as one read as UN, or private text read as ISO 8859-1, takes
    its action without the option.
    """
    sources = {value.source: value for value in edits.source_values}
    guessed = frozenset(edits.read_as_latin_1)
    texts = {}
    for path in paths:
        source = sources.get(path)
        vr = descriptor_vr(private_texts.get(path, path.tag))
        if source is None or vr is None or source.vr != vr or path in guessed:
            continue
        if not isinstance(source.value, str):
            continue
        texts[path] = (
            source.value.split("\\") if vr in _MULTI_VALUED else [source.value]
        )
    return texts


def kept_descriptors(
    plan: InstancePlan,
    edits: InstanceEdits,
    cleaning: DescriptorCleaning,
    *,
    cleaned_elsewhere: Collection[str],
) -> frozenset[ElementPath]:
    """Return the free-text descriptors of a withheld instance that cleaning would keep.

    An instance withheld before its descriptors are cleaned is still edited
    so that its values are collected for its subject's residual search
    (D-027). A descriptor that cleaning would write with a value that a tier
    keeps, by the rules of :func:`clean_descriptors`, is left out of that
    collection, as it is from an instance that is written, so that the same
    value written in another instance, such as the Series Description of the
    rest of a series, is not found from it. A value that a reviewer maps or
    empties, that no tier cleans, or that echoes an identifier stays in it.
    So does a kept value in a sequence that also holds an attribute given C
    that cleaning would not write, since that attribute's action without the
    option may remove the sequence with both (D-020), which only an instance
    that is written settles. A private creator that the plan keeps is left
    out where something else in its block would be written for certain.

    Parameters
    ----------
    plan : InstancePlan
        The instance's plan, under a policy with Clean Descriptors.
    edits : InstanceEdits
        Its edits, with the values that they collected.
    cleaning : DescriptorCleaning
        What descriptors are cleaned with.
    cleaned_elsewhere : collection of str
        As for :func:`clean_descriptors`: descriptors that are not cleaned.

    Returns
    -------
    frozenset of ElementPath
        The descriptors whose values would be kept, each a retained value.
    """
    paths = [
        element.path
        for element in plan.elements
        if element.action == "C" and not _is_roi_name(element.path)
    ]
    identifiers = _identifiers(edits)
    texts_of = _descriptor_texts(
        edits,
        [path for path in paths if path.tag not in cleaned_elsewhere],
        plan.private_texts,
    )
    written, kept = set(), set()
    for path, texts in texts_of.items():
        results = clean_descriptor_values(
            plan.private_texts.get(path, path.tag),
            texts,
            cleaning.reviewed_descriptors,
            identifiers=identifiers,
            vocabulary=cleaning.technique,
        )
        if _written(results) is None:
            continue
        written.add(path)
        if any(
            result.outcome in _KEEPS_ITS_SOURCE and result.value for result in results
        ):
            kept.add(path)
    fallen_back = [path for path in paths if path not in written]

    def stays(path: ElementPath) -> bool:
        return not any(_shares_a_sequence(path, other) for other in fallen_back)

    # A kept private creator, which the plan collects where it cleans
    # private text, is retained where something else in its block would be
    # written for certain.
    holding = {
        creator_of(element.path)
        for element in plan.elements
        if element.action != "X"
        and is_private(element.path.tag)
        and not is_private_creator(element.path.tag)
        and (element.path in written or element.path not in plan.private_texts)
        and stays(element.path)
    }
    creators = {
        element.path
        for element in plan.elements
        if element.action == "K" and element.path in holding
    }
    return frozenset(path for path in kept if stays(path)) | frozenset(creators)


def _shares_a_sequence(path: ElementPath, other: ElementPath) -> bool:
    """Return whether ``path`` is in a sequence that holds, or is, ``other``."""
    return any(
        _within(path, ElementPath(other.items[:depth], tag))
        for depth, (tag, _) in enumerate(other.items)
    ) or _within(path, other)


def _written(results: Sequence[CleanedDescriptor]) -> tuple[str, ...] | None:
    """Return what is written for a descriptor's values, or None to fall back.

    None where a value is not cleaned, where no value is written with text,
    or where a kept value is written beside one that a reviewer mapped or
    emptied, since the residual search leaves a kept value's whole element
    out of its search, which would leave out that value's source too.
    """
    outcomes = {result.outcome for result in results}
    if any(result.value is None for result in results):
        return None
    if outcomes & _KEEPS_ITS_SOURCE and outcomes - _KEEPS_ITS_SOURCE - {
        DescriptorOutcome.EMPTY
    }:
        return None
    values = tuple(result.value or "" for result in results)
    return values if any(values) else None


def _cleaned_names(
    edits: InstanceEdits,
    names: Sequence[Edit],
    cleaning: DescriptorCleaning,
    vocabulary: RoiNameVocabulary | None,
    identifiers: Sequence[str],
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
    results = clean_roi_names(
        texts,
        vocabulary,
        cleaning.reviewed,
        identifiers=identifiers,
        empty_held=cleaning.empty_held,
        institutional=cleaning.institutional_names,
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
        # Where the action removes an attribute that the IOD requires, it
        # removes an enclosing sequence with it (D-020), which goes too.
        removed = _removed_sequence(edit.path, by_path)
        if removed is not None:
            settled.update(
                (path, by_path[path]) for path in by_path if _within(path, removed)
            )
    return settled


def _creators_left(
    edits: InstanceEdits,
    settled: Mapping[ElementPath, Edit],
    fallback: InstanceEdits,
) -> dict[ElementPath, Edit]:
    """Return the fallback's edit of each private creator kept only for text removed.

    A private creator is kept only for what its block keeps (D-035), so
    one that the plan kept for private text to clean, but whose block keeps
    nothing once that text takes its action without the option, takes the
    fallback's action too. Only a creator that the fallback does not keep
    can be.
    """
    final = {edit.path: settled.get(edit.path, edit) for edit in edits.edits}
    removed = {
        edit.path: edit for edit in fallback.edits if edit.kind is EditKind.REMOVE
    }
    holding = {
        (path.items, path.tag[1:5], path.tag[6:8])
        for path, edit in final.items()
        if edit.kind is not EditKind.REMOVE
        and not is_private_creator(path.tag)
        and int(path.tag[6:10], 16) >= 0x1000
    }
    return {
        path: removed[path]
        for path, edit in final.items()
        if path in removed
        and is_private_creator(path.tag)
        and edit.kind is not EditKind.REMOVE
        and (path.items, path.tag[1:5], path.tag[8:10]) not in holding
    }


def _removed_sequence(
    path: ElementPath, by_path: Mapping[ElementPath, Edit]
) -> ElementPath | None:
    """Return the outermost sequence holding ``path`` that ``by_path`` removes."""
    for depth, (tag, _) in enumerate(path.items):
        sequence = ElementPath(path.items[:depth], tag)
        found = by_path.get(sequence)
        if found is not None and found.kind is EditKind.REMOVE:
            return sequence
    return None


def _within(path: ElementPath, sequence: ElementPath) -> bool:
    """Return whether ``path`` is ``sequence`` or an element in its items."""
    depth = len(sequence.items)
    return path == sequence or (
        len(path.items) > depth
        and path.items[:depth] == sequence.items
        and path.items[depth][0] == sequence.tag
    )
