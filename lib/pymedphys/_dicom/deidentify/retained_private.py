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
cleaned (:mod:`~pymedphys._dicom.deidentify.safe_private`). An instance may
also declare which of its private attributes are safe, in Private Data
Element Characteristics Sequence (0008,0300), which E.3.10 counts as a way
of knowing. :func:`private_actions` gives every element of a private group
of a source file, at the top level and in the items of every sequence, the
action that settles its C, K, U, or X, from its rule and its value as the
file holds it:

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
- An instance's (0008,0300), at the top level, describes blocks by Private
  Group Reference (0008,0301) and Private Creator Reference (0008,0302),
  the creator compared as above, so that it applies to that creator's block
  in that group wherever the block is. A data element that holds a value
  is declared safe where its block is marked SAFE in Block Identifying
  Information Status (0008,0303), or MIXED with the element listed in
  Nonidentifying Private Elements (0008,0304); it is declared possibly
  identifying where its block is marked UNSAFE, or MIXED without it listed,
  or an item of Deidentification Action Sequence (0008,0305) lists it in
  Identifying Private Elements (0008,0306). Where items disagree, possibly
  identifying wins. An item that names a block but whose status is not one
  of those Enumerated Values, or whose list of elements cannot be read,
  declares every element of the block possibly identifying; one that names
  no group open to private use, or no creator that is compared, is ignored.

  - An element declared possibly identifying is removed, even where a
    reviewed rule would keep it, since it is then not known to be safe.
  - An element declared safe that no reviewed rule lists takes the handling
    of its VR, as a row of Table E.3.10-1 does: its VR as written, or,
    where the file does not write it, the VR that Private Data Element
    Value Representation (0008,030A) defines for it, and it is removed
    where neither gives one or the two differ. Its values are checked
    against that VR, with any number of values. So a declared number or
    code string is kept, a declared UID replaced, and declared text, dates,
    times, names, and bulk binary data removed, as E.3.10's "removed or
    processed" allows.
  - A sequence is parsed whatever (0008,0300) says of it, so that each
    element in its items is settled on its own merits.
- A private sequence that no rule lists, in a block whose creator is
  compared, is parsed, as E.3.10 asks of a sequence "not known to always
  only contain safe content": it is kept as a container, so that each
  element in its items is "handled on its own merits" by its own rule, and
  :func:`~pymedphys._dicom.deidentify.walker.plan_instance` removes it,
  with everything in it, where nothing in its items, at any depth, is kept
  or replaced but private creators. Such a sequence is listed in
  :attr:`PrivatePlan.parsed`.
- A private creator is kept where an element of its block in the same data
  set or item is kept or replaced, and removed otherwise.
- Every other element of a private group is removed: a data element that
  is not a sequence and that neither a rule nor (0008,0300) declares safe,
  one whose block has no creator that is compared, and each element that PS3.5 Section 7.8.1 does not allow, at
  (gggg,0001) to (gggg,000F) and (gggg,0100) to (gggg,0FFF).

An element that Deidentification Action (0008,0307) asks to be processed
is removed, which meets E.3.10's "removed or processed". (0008,0300) itself
is removed by its supplementary rule, as under every policy.

The actions name paths, never values. The values that decide them are read
from the source file's own bytes, and only those of private creators, of
elements that a rule would keep, and of the attributes of (0008,0300) named
above, which describe private blocks rather than the patient.
:func:`private_plan` also gives the VR by which each kept value whose VR the
file does not write is read: the rule's, the VR that (0008,0300) defines for
a declared element, or LO for a private creator, so that a creator, code, or
number string kept from Implicit VR Little Endian, or written as UN, is
reviewed as the same value written with its VR would be. A sequence holds
no value of its own, so none is given for one.
"""

from __future__ import annotations

import dataclasses
import struct
import types
from collections.abc import Mapping

from .file_layout import ElementPath, Extent
from .safe_private import (
    Basis,
    Handling,
    SafePrivateRule,
    SafePrivateRules,
    default_handling,
)
from .source import SourceEvidence
from .standard import _RESERVED_ODD_GROUPS, VRS
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
# Private Data Element Characteristics Sequence (0008,0300), and the
# attributes of its items that say which elements of a block are safe
# (PS3.3 Section C.12.1).
_CHARACTERISTICS = "(0008,0300)"
_GROUP_REFERENCE = "(0008,0301)"
_CREATOR_REFERENCE = "(0008,0302)"
_STATUS = "(0008,0303)"
_NONIDENTIFYING = "(0008,0304)"
_ACTIONS = "(0008,0305)"
_IDENTIFYING = "(0008,0306)"
_DEFINITIONS = "(0008,0310)"
_DEFINED_ELEMENT = "(0008,0308)"
_DEFINED_VR = "(0008,030A)"
# The Enumerated Values of Block Identifying Information Status (0008,0303).
_SAFE, _MIXED, _UNSAFE = "SAFE", "MIXED", "UNSAFE"
# The elements of a block, by the low byte of their element numbers.
_BLOCK_ELEMENTS = frozenset(range(0x100))
# A declared block's key: its group and its private creator.
_Described = tuple[int, str]
# The VM of a declared element, whose values are checked against its VR only.
_DECLARED_VM = "1-n"


def is_private(tag: str) -> bool:
    """Return whether an element of the form ``(gggg,eeee)`` is in a private group.

    Its group is odd, and not one of 0001, 0003, 0005, 0007, and FFFF,
    which PS3.5 Section 7.8.1 does not allow for private use.
    """
    group = int(tag[1:5], 16)
    return group % 2 == 1 and group not in _RESERVED_ODD_GROUPS


def is_private_creator(tag: str) -> bool:
    """Return whether an element of the form ``(gggg,eeee)`` is a private creator.

    It is in a private group, at (gggg,0010) to (gggg,00FF) (PS3.5 Section
    7.8.1).
    """
    return is_private(tag) and 0x0010 <= int(tag[6:10], 16) <= 0x00FF


@dataclasses.dataclass(frozen=True)
class _Declaration:
    """What an instance's (0008,0300) says of the elements of one block.

    ``safe`` holds the elements that it marks safe and no item of it marks
    identifying; ``identifying`` those that some item marks as possibly
    identifying; ``vrs`` the VR that it defines for an element, where its
    items agree on one.
    """

    safe: frozenset[int]
    identifying: frozenset[int]
    vrs: Mapping[int, str]


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
        rule's, or LO for a private creator. A sequence is not given one.
    parsed : frozenset of ElementPath
        The private sequences that no rule lists, kept so that their items
        are parsed, which are removed where nothing in them is kept.
    """

    actions: Mapping[ElementPath, str]
    vrs: Mapping[ElementPath, str]
    parsed: frozenset[ElementPath] = frozenset()


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
        module describes. A private sequence that no rule lists is
        ``"K"``, as parsed, whatever is kept in it.
    """
    return private_plan(source, rules).actions


def private_plan(
    source: SourceEvidence,
    rules: SafePrivateRules,
    unkept: frozenset[ElementPath] = frozenset(),
) -> PrivatePlan:
    """Return the actions of :func:`private_actions`, with the VRs that read them.

    Parameters
    ----------
    source : SourceEvidence
    rules : SafePrivateRules
    unkept : frozenset of ElementPath, optional
        The private sequences that no rule lists, and that the plan found
        nothing kept in, which are removed. Defaults to none.

    Returns
    -------
    PrivatePlan
        Its mappings are read-only.
    """
    actions: dict[ElementPath, str] = {}
    vrs: dict[ElementPath, str] = {}
    parsed: set[ElementPath] = set()
    creators: dict[_Block, str | None] = {}
    kept: set[_Block] = set()
    declarations = _declarations(source)
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
            extent = source.element(path)
            rule = None
            if creator is not None:
                rule = _rule(
                    rules,
                    declarations.get((group, creator)),
                    (group, creator, element & 0xFF),
                    extent,
                )
            if creator is not None and rule is None and extent.items is not None:
                if path not in unkept:
                    actions[path] = KEEP
                    parsed.add(path)
            else:
                actions[path] = _action(source, path, rule)
            if actions[path] != REMOVE:
                kept.add(block)
                if (
                    rule is not None
                    and extent.items is None
                    and extent.vr in _UNWRITTEN
                ):
                    vrs[path] = rule.vr
    for path in actions:
        element = int(path.tag[6:10], 16)
        if 0x0010 <= element <= 0x00FF:
            if (path.items, int(path.tag[1:5], 16), element) in kept:
                actions[path] = KEEP
                if source.element(path).vr in _UNWRITTEN:
                    vrs[path] = _CREATOR_VR
    return PrivatePlan(
        types.MappingProxyType(actions),
        types.MappingProxyType(vrs),
        frozenset(parsed),
    )


def _creator(source: SourceEvidence, path: ElementPath) -> str | None:
    """Return a private creator to compare with the rules, or None."""
    extent = source.element(path)
    if (
        extent.items is not None
        or extent.undefined_length
        or extent.vr not in _UNWRITTEN | {_CREATOR_VR}
    ):
        return None
    return _compared(source.value_field(path))


def _compared(value: bytes) -> str | None:
    """Return a private creator's Value Field as the text that is compared, or None."""
    value = value.rstrip(_PADDING)
    if not value or not set(value) <= _CREATOR_BYTES:
        return None
    return value.decode("ascii")


def _rule(
    rules: SafePrivateRules,
    declaration: _Declaration | None,
    key: tuple[int, str, int],
    extent: Extent,
) -> SafePrivateRule | None:
    """Return the rule that settles a private data element, or None if none does.

    A reviewed rule settles its element unless the instance declares that
    the element may be identifying. An element without one that the
    instance declares safe takes the handling of its VR, as written or as
    the instance defines it where the file does not write it. The
    declaration settles only an element that holds a value: a sequence is
    parsed whatever it says.
    """
    group, creator, element = key
    rule = rules.rule_for(group, creator, element)
    if declaration is None or extent.items is not None:
        return rule
    if element in declaration.identifying:
        return None
    if rule is not None or element not in declaration.safe:
        return rule
    defined = declaration.vrs.get(element)
    if extent.vr in _UNWRITTEN:
        vr = defined
    elif defined in (None, extent.vr):
        vr = extent.vr
    else:
        vr = None
    if vr is None:
        return None
    return SafePrivateRule(
        creator,
        group,
        element,
        vr,
        _DECLARED_VM,
        default_handling(vr),
        Basis.DECLARED,
    )


def _declarations(source: SourceEvidence) -> Mapping[_Described, _Declaration]:
    """Return what the instance's (0008,0300) says of each block it describes.

    Only the sequence at the top level, in the SOP Common Module, is read.
    Where several items describe one block, an element is safe only where
    one marks it safe and none marks it possibly identifying.
    """
    sequence = ElementPath((), _CHARACTERISTICS)
    if sequence not in source or not source.element(sequence).items:
        return {}
    safe: dict[_Described, set[int]] = {}
    identifying: dict[_Described, set[int]] = {}
    vrs: dict[_Described, dict[int, str | None]] = {}
    for index in range(source.element(sequence).items or 0):
        read = _declared(source, ((_CHARACTERISTICS, index),))
        if read is None:
            continue
        key, item_safe, item_identifying, item_vrs = read
        safe.setdefault(key, set()).update(item_safe)
        identifying.setdefault(key, set()).update(item_identifying)
        defined = vrs.setdefault(key, {})
        for element, vr in item_vrs.items():
            defined[element] = vr if defined.get(element, vr) == vr else None
    return {
        key: _Declaration(
            frozenset(elements - identifying[key]),
            frozenset(identifying[key]),
            types.MappingProxyType(
                {element: vr for element, vr in vrs[key].items() if vr is not None}
            ),
        )
        for key, elements in safe.items()
    }


def _declared(
    source: SourceEvidence, item: tuple
) -> tuple[_Described, frozenset[int], frozenset[int], dict[int, str]] | None:
    """Return the block that one item of (0008,0300) describes, and what it says.

    That is the block's key, the elements it marks safe, those it marks as
    possibly identifying, and the VR it defines for each element; or None
    where the item does not name a compared creator of a private group.
    Where it names one but its status is not one of the Enumerated Values,
    or a list of elements in it cannot be read, it marks no element safe
    and every element possibly identifying.
    """
    group = _shorts(_field(source, ElementPath(item, _GROUP_REFERENCE), "US"))
    creator_field = _field(source, ElementPath(item, _CREATOR_REFERENCE), "LO")
    creator = None if creator_field is None else _compared(creator_field)
    if (
        group is None
        or len(group) != 1
        or not is_private(f"({group[0]:04X},0000)")
        or creator is None
    ):
        return None
    key = (group[0], creator)
    unread = (key, frozenset(), _BLOCK_ELEMENTS, {})
    status = _code(_field(source, ElementPath(item, _STATUS), "CS"))
    if status == _SAFE:
        safe = _BLOCK_ELEMENTS
    elif status == _MIXED:
        listed = _elements(source, ElementPath(item, _NONIDENTIFYING))
        if listed is None:
            return unread
        safe = listed
    elif status == _UNSAFE:
        safe = frozenset()
    else:
        return unread
    identifying = set(_BLOCK_ELEMENTS - safe)
    for each in _items(source, ElementPath(item, _ACTIONS)):
        listed = (
            None if each is None else _elements(source, ElementPath(each, _IDENTIFYING))
        )
        if listed is None:
            return unread
        identifying |= listed
    defined: dict[int, str | None] = {}
    for each in _items(source, ElementPath(item, _DEFINITIONS)):
        if each is None:
            continue
        elements = _elements(source, ElementPath(each, _DEFINED_ELEMENT))
        vr = _code(_field(source, ElementPath(each, _DEFINED_VR), "CS"))
        if elements is not None and len(elements) == 1 and vr in VRS:
            (element,) = elements
            defined[element] = vr if defined.get(element, vr) == vr else None
    return (
        key,
        frozenset(safe - identifying),
        frozenset(identifying),
        {element: vr for element, vr in defined.items() if vr is not None},
    )


def _items(source: SourceEvidence, path: ElementPath) -> list[tuple | None]:
    """Return the items of a sequence of (0008,0300), each as the path to it.

    An absent sequence has none; one that does not hold its value in items
    has one, None, which cannot be read.
    """
    if path not in source:
        return []
    count = source.element(path).items
    if count is None:
        return [None]
    return [(*path.items, (path.tag, index)) for index in range(count)]


def _field(source: SourceEvidence, path: ElementPath, vr: str) -> bytes | None:
    """Return the Value Field of an attribute of (0008,0300), or None.

    None where it is absent or holds items, or its VR as written is not the
    one that PS3.6 gives it.
    """
    if path not in source:
        return None
    extent = source.element(path)
    if extent.items is not None or extent.undefined_length:
        return None
    if extent.vr not in (None, vr):
        return None
    return source.value_field(path)


def _shorts(value: bytes | None) -> tuple[int, ...] | None:
    """Return the values of a US Value Field, or None if it holds none."""
    if not value or len(value) % 2:
        return None
    return struct.unpack(f"<{len(value) // 2}H", value)


def _elements(source: SourceEvidence, path: ElementPath) -> frozenset[int] | None:
    """Return the elements within a block that a US attribute lists, or None.

    None where it is absent, holds no value, or lists a value above 00FFH.
    """
    values = _shorts(_field(source, path, "US"))
    if values is None or not set(values) <= _BLOCK_ELEMENTS:
        return None
    return frozenset(values)


def _code(value: bytes | None) -> str | None:
    """Return a single-valued CS without its padding, or None if it is not one."""
    if value is None or not set(value) <= _STRING_BYTES or b"\\" in value:
        return None
    return value.decode("ascii").strip(" ")


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
