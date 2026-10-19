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
cleaned (:mod:`~pymedphys._dicom.deidentify.safe_private`), unless the run
chooses TCIA's Private Tag Dictionary in their place
(:mod:`~pymedphys._dicom.deidentify.tcia_private_tags`). An instance may
also declare which of its private attributes are safe, in Private Data
Element Characteristics Sequence (0008,0300), which E.3.10 counts as a way
of knowing. :func:`private_actions` gives every element of a private group
of a source file, at the top level and in the items of every sequence, the
action that settles its C, K, U, or X, from its rule and its value as the
file holds it:

- A data element (gggg,xxyy), with xx from 10 to FF, is in the block that
  the private creator (gggg,00xx) of the same data set or item reserves
  (PS3.5 Section 7.8.1), and its rule is the one for that creator, group,
  and yy in the run's list, given the VR as written, or none where it is
  not written (:meth:`~.safe_private.RuleList.rule_for`), wherever the
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
    as UI and the number of values is one that the rule's VM allows, and
    otherwise removed, since its value cannot be read as UIDs;
  - ``sequence``: kept as a container where the source holds its items, so
    that each element in them takes its own rule (E.3.10), and otherwise
    removed;
  - ``text``: under Clean Descriptors, cleaned (C) where its VR is written,
    so that its value is decoded as its VR and character set give it, as
    descriptor cleaning
    (:func:`~pymedphys._dicom.deidentify.descriptor_cleaning.clean_descriptors`)
    cleans a free-text descriptor, by the reviewer's decisions on the values
    of its :func:`~.reviewed_descriptors.private_descriptor` key, and
    removed where it cleans none; otherwise removed, since no other reviewed
    cleaner applies to private text;
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
    where neither gives one, the two differ, or the definitions of it in
    (0008,0300) disagree or one cannot be read. Its values are checked
    against that VR, and their number against the VM that Private Data
    Element Value Multiplicity (0008,0309) defines with it, or against a
    single value where (0008,0310) defines none, or one that PS3.6 has no
    form for. So a declared number or code string is kept, a declared UID
    replaced, and declared text and every value of another VR, such as a
    date, a name, or OB, OW, or UN data, removed, as E.3.10's "removed or
    processed" allows. Declared text is cleaned under Clean Descriptors, as
    a rule's text is.
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
  set or item is kept, replaced, or cleaned, and removed otherwise.
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
from .reviewed_descriptors import private_descriptor
from .safe_private import (
    Basis,
    Handling,
    RuleList,
    SafePrivateRule,
    default_handling,
)
from .source import SourceEvidence
from .standard import _RESERVED_ODD_GROUPS, VRS
from .values import values_problem, vm_problem

KEEP = "K"
REPLACE = "U"
REMOVE = "X"
CLEAN = "C"
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
# The text VRs whose values a backslash separates (PS3.5 Section 6.2).
_MULTI_VALUED_TEXT = frozenset({"SH", "LO", "UC"})
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
_DEFINED_VM = "(0008,0309)"
_DEFINED_VR = "(0008,030A)"
# The Enumerated Values of Block Identifying Information Status (0008,0303).
_SAFE, _MIXED, _UNSAFE = "SAFE", "MIXED", "UNSAFE"
# The elements of a block, by the low byte of their element numbers.
_BLOCK_ELEMENTS = frozenset(range(0x100))
# A declared block's key: its group and its private creator.
_Described = tuple[int, str]
# The VM of a declared element that (0008,0310) does not define.
_UNDEFINED_VM = "1"
# The VR and VM that (0008,0310) defines for an element.
_Defined = tuple[str, str]


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


def creator_of(path: ElementPath) -> ElementPath:
    """Return the path of the private creator that reserves an element's block.

    It is in the same data set or item, at (gggg,00bb) for an element at
    (gggg,bbee) (PS3.5 Section 7.8.1).
    """
    return ElementPath(path.items, f"({path.tag[1:5]},00{path.tag[6:8]})")


@dataclasses.dataclass(frozen=True)
class _Declaration:
    """What an instance's (0008,0300) says of the elements of one block.

    ``safe`` holds the elements that it marks safe and no item of it marks
    identifying; ``identifying`` those that some item marks as possibly
    identifying; ``defined`` the VR and VM that it defines for an element,
    where every definition of the element in its items agrees, and None
    where two disagree or one cannot be read.
    """

    safe: frozenset[int]
    identifying: frozenset[int]
    defined: Mapping[int, _Defined | None]


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
    texts : mapping of ElementPath to str
        The key (:func:`~.reviewed_descriptors.private_descriptor`) of each
        private element whose text is cleaned.
    text_vms : mapping of ElementPath to str
        The VM of the rule of each private element whose text is cleaned,
        which its decoded values are checked against, since its raw bytes
        are counted before they are decoded.
    """

    actions: Mapping[ElementPath, str]
    vrs: Mapping[ElementPath, str]
    parsed: frozenset[ElementPath] = frozenset()
    texts: Mapping[ElementPath, str] = dataclasses.field(
        default_factory=lambda: types.MappingProxyType({})
    )
    text_vms: Mapping[ElementPath, str] = dataclasses.field(
        default_factory=lambda: types.MappingProxyType({})
    )


def private_actions(
    source: SourceEvidence, rules: RuleList
) -> Mapping[ElementPath, str]:
    """Return the action that settles the C of each private element of a source file.

    Parameters
    ----------
    source : SourceEvidence
        The source file, from
        :func:`~pymedphys._dicom.deidentify.source.read_source`.
    rules : RuleList
        The run's list of rules: the reviewed rules, from
        :func:`~pymedphys._dicom.deidentify.safe_private.load_safe_private_rules`,
        or TCIA's, from
        :func:`~pymedphys._dicom.deidentify.tcia_private_tags.tcia_safe_private_rules`.

    Returns
    -------
    mapping of ElementPath to str
        Read-only: ``"K"``, ``"U"``, or ``"X"`` for each element of a
        private group, at every level of nesting, in file order, as the
        module describes. A private sequence that no rule lists is
        ``"K"``, as parsed, whatever is kept in it. Text is removed, as
        without Clean Descriptors; :func:`private_plan` gives the actions
        under it.
    """
    return private_plan(source, rules).actions


def private_plan(
    source: SourceEvidence,
    rules: RuleList,
    unkept: frozenset[ElementPath] = frozenset(),
    *,
    clean_text: bool = False,
) -> PrivatePlan:
    """Return the actions of :func:`private_actions`, with the VRs that read them.

    Parameters
    ----------
    source : SourceEvidence
    rules : RuleList
    unkept : frozenset of ElementPath, optional
        The private sequences that no rule lists, and that the plan found
        nothing kept in, which are removed. Defaults to none.
    clean_text : bool, optional
        Whether the policy selects Clean Descriptors, so that text that a
        rule retains, written with its VR, is cleaned (``"C"``) rather than
        removed. Defaults to False.

    Returns
    -------
    PrivatePlan
        Its mappings are read-only.
    """
    actions: dict[ElementPath, str] = {}
    vrs: dict[ElementPath, str] = {}
    parsed: set[ElementPath] = set()
    texts: dict[ElementPath, str] = {}
    text_vms: dict[ElementPath, str] = {}
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
                actions[path] = _action(source, path, rule, clean_text)
            if actions[path] == CLEAN:
                assert rule is not None and creator is not None
                texts[path] = private_descriptor(
                    group, creator, element & 0xFF, rule.vr
                )
                text_vms[path] = rule.vm
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
        types.MappingProxyType(texts),
        types.MappingProxyType(text_vms),
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
    rules: RuleList,
    declaration: _Declaration | None,
    key: tuple[int, str, int],
    extent: Extent,
) -> SafePrivateRule | None:
    """Return the rule that settles a private data element, or None if none does.

    The rule of the run's list for the element as written settles it unless
    the instance declares that the element may be identifying. An element
    without one that the
    instance declares safe takes the handling of its VR, as written or as
    the instance defines it where the file does not write it, and the VM
    that the instance defines, or a single value where it defines none; it
    is removed where the instance's definitions of it are disputed. The
    declaration settles only an element that holds a value: a sequence is
    parsed whatever it says.
    """
    group, creator, element = key
    written = None if extent.vr in _UNWRITTEN else extent.vr
    rule = rules.rule_for(group, creator, element, written)
    if declaration is None or extent.items is not None:
        return rule
    if element in declaration.identifying:
        return None
    if rule is not None or element not in declaration.safe:
        return rule
    defined = declaration.defined.get(element, (None, _UNDEFINED_VM))
    if defined is None:
        return None
    defined_vr, vm = defined
    if extent.vr in _UNWRITTEN:
        vr = defined_vr
    elif defined_vr in (None, extent.vr):
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
        vm,
        default_handling(vr),
        Basis.DECLARED,
    )


def _declarations(source: SourceEvidence) -> Mapping[_Described, _Declaration]:
    """Return what the instance's (0008,0300) says of each block it describes.

    Only the sequence at the top level, in the SOP Common Module, is read.
    Where several items describe one block, an element is safe only where
    one marks it safe and none marks it possibly identifying, and it is
    defined only where every definition of it agrees.
    """
    sequence = ElementPath((), _CHARACTERISTICS)
    if sequence not in source or not source.element(sequence).items:
        return {}
    safe: dict[_Described, set[int]] = {}
    identifying: dict[_Described, set[int]] = {}
    definitions: dict[_Described, dict[int, _Defined | None]] = {}
    for index in range(source.element(sequence).items or 0):
        read = _declared(source, ((_CHARACTERISTICS, index),))
        if read is None:
            continue
        key, item_safe, item_identifying, item_defined = read
        safe.setdefault(key, set()).update(item_safe)
        identifying.setdefault(key, set()).update(item_identifying)
        defined = definitions.setdefault(key, {})
        for element, definition in item_defined.items():
            defined[element] = _agreed(defined, element, definition)
    return {
        key: _Declaration(
            frozenset(elements - identifying[key]),
            frozenset(identifying[key]),
            types.MappingProxyType(definitions[key]),
        )
        for key, elements in safe.items()
    }


def _declared(
    source: SourceEvidence, item: tuple
) -> (
    tuple[_Described, frozenset[int], frozenset[int], dict[int, _Defined | None]] | None
):
    """Return the block that one item of (0008,0300) describes, and what it says.

    That is the block's key, the elements it marks safe, those it marks as
    possibly identifying, and the VR and VM it defines for each element,
    None where its definitions of an element disagree or one cannot be read;
    or None where the item does not name a compared creator of a private
    group.
    Where it names one but its status is not one of the Enumerated Values,
    or a list of elements in it cannot be read, it marks no element safe
    and every element possibly identifying.
    """
    group = _unsigned(_field(source, ElementPath(item, _GROUP_REFERENCE), "US"))
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
    defined: dict[int, _Defined | None] = {}
    for each in _items(source, ElementPath(item, _DEFINITIONS)):
        elements = (
            None
            if each is None
            else _elements(source, ElementPath(each, _DEFINED_ELEMENT))
        )
        if elements is None:
            continue
        vr = _code(_field(source, ElementPath(each, _DEFINED_VR), "CS"))
        definition = None
        # A definition of several elements cannot be read for any of them.
        if len(elements) == 1 and vr in VRS:
            multiplicity = _unsigned(
                _field(source, ElementPath(each, _DEFINED_VM), "UL"), "L"
            )
            definition = (vr, _vm(multiplicity) or _UNDEFINED_VM)
        for element in elements:
            defined[element] = _agreed(defined, element, definition)
    return (key, frozenset(safe - identifying), frozenset(identifying), defined)


def _agreed(
    defined: Mapping[int, _Defined | None], element: int, definition: _Defined | None
) -> _Defined | None:
    """Return an element's definition where it agrees with any earlier one."""
    if element in defined and defined[element] != definition:
        return None
    return definition


def _vm(multiplicity: tuple[int, ...] | None) -> str | None:
    """Return the VM, as PS3.6 writes it, that (0008,0309) gives, or None.

    PS3.3 Section C.12.1.1.7.1 gives a fixed multiplicity as one value, and
    a variable one as its least, its greatest (0 where it is open-ended),
    and its stride (1 where it is omitted). None where the values are not
    of that form, or give a VM that PS3.6 has no form for.
    """
    if (
        multiplicity is None
        or len(multiplicity) not in (1, 2, 3)
        or multiplicity == (0,)
    ):
        return None
    if len(multiplicity) == 1:
        multiplicity = (multiplicity[0], multiplicity[0])
    least, greatest, stride = (*multiplicity, 1)[:3]
    # An attribute may be empty whatever its VM, so a least of 0 adds nothing.
    least = least or stride
    if not stride or least % stride:
        return None
    if not greatest:
        # Open-ended: a stride of 1, or one equal to the least, as in 2-2n.
        return {least: f"{least}-{least}n", 1: f"{least}-n"}.get(stride)
    if greatest < least or stride != 1:
        return None
    return str(least) if least == greatest else f"{least}-{greatest}"


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


def _unsigned(value: bytes | None, code: str = "H") -> tuple[int, ...] | None:
    """Return the values of a US or UL Value Field, or None if it holds none.

    ``code`` is the :mod:`struct` code of one value: H for US, L for UL.
    """
    size = struct.calcsize(f"<{code}")
    if not value or len(value) % size:
        return None
    return struct.unpack(f"<{len(value) // size}{code}", value)


def _elements(source: SourceEvidence, path: ElementPath) -> frozenset[int] | None:
    """Return the elements within a block that a US attribute lists, or None.

    None where it is absent, holds no value, or lists a value above 00FFH.
    """
    values = _unsigned(_field(source, path, "US"))
    if values is None or not set(values) <= _BLOCK_ELEMENTS:
        return None
    return frozenset(values)


def _code(value: bytes | None) -> str | None:
    """Return a single-valued CS without its padding, or None if it is not one."""
    if value is None or not set(value) <= _STRING_BYTES or b"\\" in value:
        return None
    return value.decode("ascii").strip(" ")


def _action(
    source: SourceEvidence,
    path: ElementPath,
    rule: SafePrivateRule | None,
    clean_text: bool = False,
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
    if extent.undefined_length:
        return REMOVE
    return _value_action(source.value_field(path), extent.vr, rule, clean_text)


def _value_action(
    value: bytes, written: str | None, rule: SafePrivateRule, clean_text: bool
) -> str:
    """Return the action that settles a private value of a retaining rule."""
    if rule.handling is Handling.TEXT:
        # Text is decoded only by its VR as written. Its values are counted
        # by their separators in its bytes, where a byte 5CH within a
        # character of a multi-byte character set would add one, so the
        # count errs only towards removing it.
        text = value.rstrip(_PADDING)
        separated = rule.vr in _MULTI_VALUED_TEXT
        count = (len(text.split(b"\\")) if separated else 1) if text else 0
        cleaned = clean_text and written == rule.vr
        return CLEAN if cleaned and vm_problem(rule.vm, count) is None else REMOVE
    if rule.handling is Handling.UID:
        uids = value.rstrip(_PADDING)
        count = len(uids.split(b"\\")) if uids else 0
        replaceable = written == "UI" and vm_problem(rule.vm, count) is None
        return REPLACE if replaceable else REMOVE
    return KEEP if _valid(value, rule.vr, rule.vm) else REMOVE


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
