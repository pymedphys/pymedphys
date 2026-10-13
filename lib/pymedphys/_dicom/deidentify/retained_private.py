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

"""Settle the C that the Retain Safe Private Option gives private attributes.

Under the Option, DICOM PS3.15 E.3.10 retains the private attributes "known
by the de-identifier to be safe from identity leakage", "together with the
Private Creator IDs that are required to fully define" them, and removes
every other, or processes it as Deidentification Action (0008,0307)
recommends. Table E.1-1 gives Private Attributes C under the Option, and the
reviewed rules of ``safe_private.toml`` say how each listed attribute is
cleaned (:mod:`~pymedphys._dicom.deidentify.safe_private`).
:func:`private_actions` gives every element of a private group of a source
file, at the top level and in the items of every sequence, the action that
settles its C, K, U, or X, from its rule and its value as the file holds it:

- A data element (gggg,xxyy), with xx from 10 to FF, is in the block that
  the private creator (gggg,00xx) of the same data set or item reserves
  (PS3.5 Section 7.8.1), and its rule is the one for that creator, group,
  and yy (:meth:`~.safe_private.SafePrivateRules.rule_for`), wherever the
  creator's block is and however deep its data set is nested. A creator is
  compared only where its Value Field, once trailing spaces and NULs are
  removed, holds printable ISO 646 bytes, 0x20 to 0x7E, and no backslash:
  without an escape sequence, every character set that DICOM allows reads
  those bytes as those characters, so no text is decoded. Any other
  creator, and one written with a VR other than LO, or as items, matches no
  rule.
- A rule settles its element only where its VR as written is the rule's,
  or is not written, in implicit VR or as UN, so that the rule's VR reads
  it:

  - ``numeric``: kept where the value is a whole number of values of a
    binary VR, or each value is a valid IS or DS, and the number of values
    is one that the rule's VM allows;
  - ``code``: kept where each value is a valid CS, of at most 16 upper-case
    letters, digits, spaces, and underscores, and the number of values is
    one that the rule's VM allows;
  - ``uid``: replaced, as every other UID is, where it is written
    as UI, and otherwise removed, since its value cannot be read as UIDs;
  - ``sequence``: kept as a container where the source holds its items, so
    that each element in them takes its own rule (E.3.10), and otherwise
    removed;
  - ``text``: removed, since no reviewed cleaner applies to private text;
  - ``remove``: removed.

  A value that does not pass its handling's check, a value where the rule
  expects items, and items where it expects a value, are removed.
- A private creator is kept where an element of its block in the same data
  set or item is kept or replaced, and removed otherwise.
- Every other element of a private group is removed: a data element without
  a rule, or whose block has no creator that matches one, and each element
  that PS3.5 Section 7.8.1 does not allow, at (gggg,0001) to (gggg,000F) and
  (gggg,0100) to (gggg,0FFF).

Two routes of E.3.10 are not yet applied, so what they would retain is
removed. Private Data Element Characteristics Sequence (0008,0300) is not
yet followed: a block that it marks SAFE in Block Identifying Information
Status (0008,0303), and an attribute that it lists in Nonidentifying Private
Elements (0008,0304), are retained only where a reviewed rule retains them,
and the sequence itself is removed by its supplementary rule, as under every
policy. A private sequence that no rule lists is removed whole, where E.3.10
asks for it to be parsed and each nested attribute handled on its own
merits. Removing what is not retained meets E.3.10's "removed or processed".

The actions name paths, never values. The values that decide them are read
from the source file's own bytes, and only those of private creators and of
elements that a rule would keep. :func:`private_plan` also gives the VR by
which each kept value whose VR the file does not write is read: the rule's,
or LO for a private creator, so that a creator, code, or number string kept
from Implicit VR Little Endian, or written as UN, is reviewed as the same
value written with its VR would be.
"""

from __future__ import annotations

import dataclasses
import types
from collections.abc import Mapping

from .file_layout import ElementPath
from .safe_private import Handling, SafePrivateRule, SafePrivateRules
from .source import SourceEvidence
from .standard import _RESERVED_ODD_GROUPS
from .values import values_problem, vm_problem

KEEP = "K"
REPLACE = "U"
REMOVE = "X"
# The VR with which PS3.5 Section 7.8.1 writes a private creator.
_CREATOR_VR = "LO"
# The VRs of an element whose VR is not written, so that its rule's VR reads it.
_UNWRITTEN = frozenset({None, "UN"})
# The bytes of a creator that are compared: printable ISO 646, but backslash,
# which would separate two values.
_CREATOR_BYTES = frozenset(range(0x20, 0x7F)) - {ord("\\")}
# The bytes of a CS, DS, or IS value that is checked: printable ISO 646.
_STRING_BYTES = frozenset(range(0x20, 0x7F))
_PADDING = b" \x00"
# The size of each value of a binary numeric VR, and of an attribute tag.
_SIZES = types.MappingProxyType(
    {"AT": 4, "FD": 8, "FL": 4, "SL": 4, "SS": 2, "SV": 8, "UL": 4, "US": 2, "UV": 8}
)
# A block's key: the items that hold it, its group, and its creator's element.
_Block = tuple[tuple, int, int]


def is_private(tag: str) -> bool:
    """Return whether an element of the form ``(gggg,eeee)`` is in a private group.

    Its group is odd, and not one of 0001, 0003, 0005, 0007, and FFFF,
    which PS3.5 Section 7.8.1 does not allow for private use.
    """
    group = int(tag[1:5], 16)
    return group % 2 == 1 and group not in _RESERVED_ODD_GROUPS


@dataclasses.dataclass(frozen=True)
class PrivatePlan:
    """The actions that settle the C of each private element, and how to read it.

    Attributes
    ----------
    actions : mapping of ElementPath to str
        As :func:`private_actions` gives them.
    vrs : mapping of ElementPath to str
        The VR by which the value of each kept or replaced private element
        whose VR is not written, in implicit VR or as UN, is read: its
        rule's, or LO for a private creator.
    """

    actions: Mapping[ElementPath, str]
    vrs: Mapping[ElementPath, str]


def private_actions(
    source: SourceEvidence, rules: SafePrivateRules
) -> Mapping[ElementPath, str]:
    """Return the action that settles the C of each private element of a source file.

    Parameters
    ----------
    source : SourceEvidence
        The source file, from
        :func:`~pymedphys._dicom.deidentify.source.read_source`.
    rules : SafePrivateRules
        The reviewed rules, from
        :func:`~pymedphys._dicom.deidentify.safe_private.load_safe_private_rules`.

    Returns
    -------
    mapping of ElementPath to str
        Read-only: ``"K"``, ``"U"``, or ``"X"`` for each element of a
        private group, at every level of nesting, in file order, as the
        module describes.
    """
    return private_plan(source, rules).actions


def private_plan(source: SourceEvidence, rules: SafePrivateRules) -> PrivatePlan:
    """Return the actions of :func:`private_actions`, with the VRs that read them.

    Parameters
    ----------
    source : SourceEvidence
    rules : SafePrivateRules

    Returns
    -------
    PrivatePlan
        Its mappings are read-only.
    """
    actions: dict[ElementPath, str] = {}
    vrs: dict[ElementPath, str] = {}
    creators: dict[_Block, str | None] = {}
    kept: set[_Block] = set()
    for path in source.paths():
        if not is_private(path.tag):
            continue
        group, element = int(path.tag[1:5], 16), int(path.tag[6:10], 16)
        actions[path] = REMOVE
        if 0x0010 <= element <= 0x00FF:
            creators[(path.items, group, element)] = _creator(source, path)
        elif element >= 0x1000:
            block = (path.items, group, element >> 8)
            # A block's creator comes before its elements, in tag order.
            creator = creators.get(block)
            rule = None
            if creator is not None:
                rule = rules.rule_for(group, creator, element & 0xFF)
            actions[path] = _action(source, path, rule)
            if actions[path] != REMOVE:
                kept.add(block)
                if rule is not None and source.element(path).vr in _UNWRITTEN:
                    vrs[path] = rule.vr
    for path in actions:
        element = int(path.tag[6:10], 16)
        if 0x0010 <= element <= 0x00FF:
            if (path.items, int(path.tag[1:5], 16), element) in kept:
                actions[path] = KEEP
                if source.element(path).vr in _UNWRITTEN:
                    vrs[path] = _CREATOR_VR
    return PrivatePlan(types.MappingProxyType(actions), types.MappingProxyType(vrs))


def _creator(source: SourceEvidence, path: ElementPath) -> str | None:
    """Return a private creator to compare with the rules, or None."""
    extent = source.element(path)
    if (
        extent.items is not None
        or extent.undefined_length
        or extent.vr not in _UNWRITTEN | {_CREATOR_VR}
    ):
        return None
    value = source.value_field(path).rstrip(_PADDING)
    if not value or not set(value) <= _CREATOR_BYTES:
        return None
    return value.decode("ascii")


def _action(
    source: SourceEvidence, path: ElementPath, rule: SafePrivateRule | None
) -> str:
    """Return the action that settles a private data element's C."""
    if rule is None or not rule.handling.retains:
        return REMOVE
    extent = source.element(path)
    container = extent.items is not None
    if extent.vr not in _UNWRITTEN | {rule.vr} or container != (
        rule.handling is Handling.SEQUENCE
    ):
        return REMOVE
    if container:
        return KEEP
    if extent.undefined_length or rule.handling is Handling.TEXT:
        return REMOVE
    if rule.handling is Handling.UID:
        return REPLACE if extent.vr == "UI" else REMOVE
    return KEEP if _valid(source.value_field(path), rule.vr, rule.vm) else REMOVE


def _valid(value: bytes, vr: str, vm: str) -> bool:
    """Return whether a numeric or code value is valid for its rule's VR and VM."""
    if vr in _SIZES:
        size = _SIZES[vr]
        return len(value) % size == 0 and vm_problem(vm, len(value) // size) is None
    if not set(value) <= _STRING_BYTES:
        return False
    # A CS, DS, or IS value is padded to an even length with a space.
    text = value.decode("ascii").rstrip(" ")
    values = text.split("\\") if text else []
    return values_problem(vr, vm, values) is None
