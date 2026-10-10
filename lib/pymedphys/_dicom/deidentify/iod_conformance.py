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

"""Check a written instance against the attributes its IOD requires (MIDI-BP-03).

De-identification must leave an instance conformant with its IOD (MIDI-BP-03,
PS3.15 E.1.1). The engine's actions are chosen so that it does: compound
actions resolve from the strictest Type of each attribute at its place, and a
plain X removes an enclosing Type 3 sequence or sequesters
(:mod:`~pymedphys._dicom.deidentify.compound_actions`). :func:`lost_requirements`
checks the written file against that, independently of the plan: every
attribute that the source holds where the IOD requires it, by the same
strictest Type, Type 1 or 1C, or 2 or 2C, must still be in the output, if the
item that held it is, and a Type 1 or 1C one must not have been emptied.

What the source already lacks is not the de-identification's doing, so only
attributes present in the source are checked, and a Type 1 or 1C attribute
only if its source value was not empty. No condition of a 1C or 2C Type is
evaluated, as for the compound actions. The two removals that
:func:`~pymedphys._dicom.deidentify.compound_actions.resolve_plain_x_in_iod`
allows without an enclosing sequence are not findings: the attributes of an
overlay group whose Overlay Plane Module is user-optional, where the whole
group was removed, and the attributes whose Type 1C condition lapses once
Table E.1-1 removes what it needs, such as ROI Interpreter Sequence
(3006,004E) with ROI Creator Sequence (3006,004D)
(:data:`~pymedphys._dicom.deidentify.compound_actions.LAPSED_CONDITIONS`).
Nor are the Common Instance Reference Module's Type 1C sequences, Referenced
Series Sequence (0008,1115) and Studies Containing Other Referenced Instances
Sequence (0008,1200), where the output holds no other reference to an
instance, so that neither condition holds
(:mod:`~pymedphys._dicom.deidentify.common_instance_reference`). Nor are the
items of a sequence that the engine replaced, such as the dummy item that D
writes, compared with the source's.

What the source lacks is reported instead, by :func:`source_gaps`, and never
acted on. Since no condition is evaluated, only an unconditional requirement
is reported: a Type 1 or 2 attribute of a mandatory module at the top level of
the data set, or of an item that the source holds, where a Functional Group
Macro that defines it is mandatory too. A conditional module, such as an
optional Overlay Plane Module, or a 1C or 2C Type would otherwise report what
the IOD does not require of that instance.

This module reads only the files' structure, the lengths and item counts of
their elements, and never a value.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Collection

from .common_instance_reference import (
    is_common_instance_reference,
    is_instance_reference,
)
from .compound_actions import RemovalExtent, resolve_plain_x_in_iod, strictest_type
from .file_layout import ElementPath
from .iods import IOD
from .source import SourceEvidence

# Each attribute of an overlay group, one of the even groups 6000 to 601E
# (PS3.5 Section 7.6), whose removal goes with that of its Overlay Data.
_OVERLAY_GROUP = re.compile(r"\((60[01][02468ACE]),[0-9A-F]{4}\)")
# The removals of a required attribute that a plain X allows on their own.
_ALLOWED = frozenset({RemovalExtent.ATTRIBUTE, RemovalExtent.OVERLAY_GROUP})


@dataclasses.dataclass(frozen=True)
class LostRequirement:
    """A required attribute that a written instance no longer holds as its source did.

    Attributes
    ----------
    path : ElementPath
        The attribute's place in the source, which the output keeps.
    type : str
        Its strictest Type there: ``"1"`` (1 or 1C) or ``"2"`` (2 or 2C).
    emptied : bool
        ``True`` where the output holds it empty, ``False`` where the output
        does not hold it.
    """

    path: ElementPath
    type: str
    emptied: bool


@dataclasses.dataclass(frozen=True)
class SourceGap:
    """An attribute that the IOD unconditionally requires and the source lacks.

    Attributes
    ----------
    path : ElementPath
        Where the source would hold it: the top level of the data set, or an
        item that the source holds.
    type : str
        ``"1"`` or ``"2"``, the strictest Type that requires it there.
    """

    path: ElementPath
    type: str


def source_gaps(source: SourceEvidence, iod: IOD) -> tuple[SourceGap, ...]:
    """Return each unconditional requirement of the IOD that the source lacks.

    Parameters
    ----------
    source : SourceEvidence
        The source file.
    iod : IOD
        The instance's IOD.

    Returns
    -------
    tuple of SourceGap
        For the top level of the data set, then each item in the source's
        file order, in the order of the IOD's modules and rows. An item
        within a table that includes itself, such as a nested Content
        Sequence item, is checked only as far as the IOD lists it.
    """
    required = _unconditional(iod)
    places: dict[tuple[tuple[str, int], ...], None] = {(): None}
    for path in source.paths():
        extent = source.element(path)
        for item in range(extent.items or 0):
            places[(*path.items, (path.tag, item))] = None
    gaps: list[SourceGap] = []
    for items in places:
        for tag, attribute_type in required.get(tuple(t for t, _ in items), {}).items():
            path = ElementPath(items, tag)
            if path not in source:
                gaps.append(SourceGap(path, attribute_type))
    return tuple(gaps)


def _unconditional(iod: IOD) -> dict[tuple[str, ...], dict[str, str]]:
    """Return each place's unconditionally required tags, with their Types."""
    usage = {module.module: module.usage for module in iod.modules}
    macros = {macro.macro: macro.usage for macro in iod.functional_group_macros}
    required: dict[tuple[str, ...], dict[str, str]] = {}
    for definition in iod.definitions:
        if (
            definition.type not in ("1", "2")
            or "xx" in definition.tag
            or (not definition.path and usage[definition.module] != "M")
            or macros.get(definition.functional_group, "M") != "M"
        ):
            continue
        place = required.setdefault(definition.path, {})
        place[definition.tag] = min(place.get(definition.tag, "2"), definition.type)
    return required


def lost_requirements(
    source: SourceEvidence,
    output: SourceEvidence,
    iod: IOD,
    replaced: Collection[ElementPath] = (),
) -> tuple[LostRequirement, ...]:
    """Return each required attribute of the source that the output lost.

    Parameters
    ----------
    source : SourceEvidence
        The source file.
    output : SourceEvidence
        The file written from it, read back.
    iod : IOD
        The instance's IOD.
    replaced : collection of ElementPath, optional
        The elements that the engine wrote new values for. The items of a
        replaced sequence, such as the dummy item that D writes, are the
        engine's own, so the source's items there are not compared with
        them.

    Returns
    -------
    tuple of LostRequirement
        In the source's file order; empty where the output keeps every
        requirement that its source met.
    """
    lost: list[LostRequirement] = []
    for path in source.paths():
        if _in_replaced_sequence(path, replaced):
            continue
        tags = tuple(tag for tag, _ in path.items)
        required = strictest_type(iod, path.tag, tags)
        if required == "3" or not _item_kept(output, path):
            continue
        if path not in output:
            if not _allowed_removal(iod, path, output):
                lost.append(LostRequirement(path, required, emptied=False))
        elif required == "1" and _empty(output, path) and not _empty(source, path):
            lost.append(LostRequirement(path, required, emptied=True))
    return tuple(lost)


def _in_replaced_sequence(path: ElementPath, replaced: Collection[ElementPath]) -> bool:
    """Return whether a sequence that holds ``path`` was given new items."""
    return any(
        ElementPath(path.items[:depth], tag) in replaced
        for depth, (tag, _) in enumerate(path.items)
    )


def _item_kept(output: SourceEvidence, path: ElementPath) -> bool:
    """Return whether the output holds the item, or data set, that holds ``path``."""
    if not path.items:
        return True
    *outer, (tag, item) = path.items
    sequence = ElementPath(tuple(outer), tag)
    if sequence not in output:
        return False
    return item < (output.element(sequence).items or 0)


def _empty(evidence: SourceEvidence, path: ElementPath) -> bool:
    """Return whether the element at ``path`` has no value: no items, or length 0."""
    extent = evidence.element(path)
    if extent.items is not None:
        return extent.items == 0
    return not extent.undefined_length and extent.end == extent.value_start


def _allowed_removal(iod: IOD, path: ElementPath, output: SourceEvidence) -> bool:
    """Return whether the required attribute may be removed on its own.

    An attribute of an overlay group may go only with its whole group, so
    none of the group's attributes may remain in the data set, or item, that
    held it. A sequence of the Common Instance Reference Module may go only
    where the output holds no other reference to an instance with a value.
    """
    if is_common_instance_reference(path):
        return not any(
            is_instance_reference(kept) and not _empty(output, kept)
            for kept in output.paths()
        )
    tag = path.tag
    tags = tuple(each for each, _ in path.items)
    overlay = _OVERLAY_GROUP.fullmatch(tag)
    if overlay:
        group = overlay.group(1)
        if any(
            kept.items == path.items and kept.tag[1:5] == group
            for kept in output.paths()
        ):
            return False
        tag = f"({group},3000)"
    return resolve_plain_x_in_iod(iod, tag, tags).extent in _ALLOWED
