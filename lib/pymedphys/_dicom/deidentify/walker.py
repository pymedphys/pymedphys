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

"""Plan each element's action, and what must read its value, before any is read.

The walker applies each element's effective action to one data set. Its first
step, here, is the plan: from a source file's
:class:`~pymedphys._dicom.deidentify.source.SourceEvidence`, the instance's
IOD, and the rule of every element
(:class:`~pymedphys._dicom.deidentify.element_rules.ElementRules`), it gives
each element of the data set, in file order:

1. its rule, at its place in the data set;
2. its action: the rule's action, with a compound action, such as X/Z/D,
   resolved from the element's Type at that place
   (:func:`~pymedphys._dicom.deidentify.compound_actions.resolve_in_iod`),
   so that X/Z on a Type 1 or 1C attribute gives D, as the maintainer
   decided on 1 October 2026; a plain D on an attribute that the IOD does
   not define at that place gives X, following Note 13 after Table E.1-1a;
   and a plain Z on an attribute that is Type 1 or 1C there gives D, the
   dummy value that Table E.1-1a allows Z
   (:func:`~pymedphys._dicom.deidentify.compound_actions.resolve_plain_in_iod`,
   D-020);
3. its consumers: what must read its value to apply the action, or to
   collect the value for the residual search.

A sequence whose action is K or U is kept as a container, and its items'
elements take their own rules: K does not keep a sequence's contents
wholesale. Under any other action, the sequence's descendants go with it:
they take no rule of their own, and each is planned as removed with the
outermost sequence that removes it. Removing a sequence does not waive
collecting its descendants' values.

Every element whose value is removed or replaced, a descendant of a removed
sequence included, is collected for the residual search
(:mod:`~pymedphys._dicom.deidentify.residuals`), whatever its VR: what
is searched, and what is listed as not searched, is for that search's own
contract to decide. A sequence holds no value of its own to collect. The plan
records the VR that the element is read by, as
:attr:`~pymedphys._dicom.deidentify.file_layout.Location.vr` gives it: as
written, or, in implicit VR and in place of UN, the one VR that the pinned
data dictionary gives; where neither gives one, as for a private element in
implicit VR, it records none, for the collection to say whether the value
can be collected.

D writes a dummy value, which must differ from the source value, so the
source value is read to compare (D-021). Only the VRs of
:data:`~pymedphys._dicom.deidentify.dummy_values.DUMMY_VRS` have a generic
dummy value. Reviewed ones exist besides for Person Identification Code
Sequence (0040,1101), whose items' Code Value (0008,0100) and Code Meaning
(0008,0104) are compared, for Referenced Performed Procedure Step Sequence
(0008,1111), whose items' Referenced SOP Instance UID (0008,1155) is read
for its keyed replacement, and for ICC Profile (0028,2000) of VR OB
(D-021). A dummy value on any other element, such as another sequence, adds
a :class:`Sequestration` to the plan, as
:func:`~pymedphys._dicom.deidentify.dummy_values.values_for_d` would refuse
it. So does an attribute of the pinned data dictionary that is not removed
but whose value the source evidence holds in a form that the dictionary does
not allow: written with a VR other than UN that the dictionary does not give
it, since the value could not be read or kept as the attribute. Admission
reads a value written as UN or in implicit VR as items only where the
dictionary gives SQ, and refuses one there that does not read as items
(:func:`~pymedphys._dicom.deidentify.source.read_source`). A plan with a
sequestration is not to be applied; every element is still planned, so that
every reason is known.

A plain X always removes its attribute (D-020). Where the IOD requires the
attribute at its place,
:func:`~pymedphys._dicom.deidentify.compound_actions.resolve_plain_x_in_iod`
says what goes with it: the innermost enclosing sequence that is Type 3 at
its own place is planned X, with everything in it, before the attribute or
after; for Overlay Data (60xx,3000), so is every other attribute of its
overlay group in the same data set or item; and where neither applies, a
:class:`Sequestration` is added. Each element so removed that its own rule
would not remove names the attribute in :attr:`ElementPlan.removed_for`.
The engine's own removals, such as Encrypted Attributes Sequence
(0400,0500), apply alone, whatever the Type. The consumers here are those
of the actions; the
inputs of options that keep or modify values, such as patient pseudonyms
and modified dates, are added with those options.

Making the plan reads no value: only the structure that the source evidence
has already validated. The plan, its ``repr``, and its sequestrations name
tags, item numbers, actions, and VRs, never a value.

Examples
--------
>>> from pymedphys._dicom.deidentify.file_layout import ElementPath
>>> from pymedphys._dicom.deidentify.iods import load_iod_tables
>>> from pymedphys._dicom.deidentify.policy import compose_policy
>>> from pymedphys._dicom.deidentify.source import read_source
>>> name = b"\\x10\\x00\\x10\\x00PN\\x0e\\x00ZEBEDEE^QUILL "
>>> meta = b"\\x02\\x00\\x10\\x00UI\\x14\\x001.2.840.10008.1.2.1\\x00"
>>> evidence = read_source(bytes(128) + b"DICM" + meta + name)
>>> rules = ElementRules(compose_policy("basic"))
>>> plan = plan_instance(evidence, rules, load_iod_tables().iods["RT Plan"])
>>> (element,) = plan.elements
>>> str(element.path), element.action, element.vr
('(0010,0010)', 'Z', 'PN')
>>> sorted(consumer.value for consumer in element.consumers)
['residual-collection']
"""

from __future__ import annotations

import dataclasses
import enum

from .compound_actions import (
    COMPOUND_ACTIONS,
    RemovalExtent,
    resolve_in_iod,
    resolve_plain_in_iod,
    resolve_plain_x_in_iod,
)
from .dummy_values import DUMMY_VRS, ICC_PROFILE
from .element_rules import ElementRule, ElementRules, RuleSource
from .file_layout import ElementPath
from .iods import IOD
from .source import SourceEvidence
from .standard import dictionary_attribute

# The actions under which a sequence is kept as a container, so that its
# items' elements take their own rules.
DESCENDED = frozenset({"K", "U"})
_REMOVED = "X"
# The sequences whose dummy value a reviewed rule gives, and the attributes
# of their items that are compared with it (D-021).
REVIEWED_DUMMY_SEQUENCES = {
    "(0040,1101)": frozenset({"(0008,0100)", "(0008,0104)"}),
    "(0008,1111)": frozenset({"(0008,1155)"}),
}


class Consumer(enum.Enum):
    """What must read an element's value."""

    UID_REPLACEMENT = "uid-replacement"  # U
    # a dummy value, which must differ from the source's (D-021)
    DUMMY_COMPARISON = "dummy-comparison"
    CLEANING = "cleaning"  # C
    # a value removed or replaced, to search the output for
    RESIDUAL_COLLECTION = "residual-collection"


_ACTION_CONSUMERS = {
    "U": Consumer.UID_REPLACEMENT,
    "D": Consumer.DUMMY_COMPARISON,
    "C": Consumer.CLEANING,
}


class SequesterReason(enum.Enum):
    """Why an instance must be sequestered."""

    # a dummy value on an element whose VR has none, such as SQ
    NO_DUMMY_VALUE = "no-dummy-value"
    # written with a VR other than UN that the dictionary does not give
    VR_NOT_IN_DICTIONARY = "vr-not-in-dictionary"
    # a value that the action needs, and that cannot be decoded
    UNDECODABLE = "undecodable"
    # a Specific Character Set that is not supported, or cannot be read (D-010)
    UNSUPPORTED_CHARACTER_SET = "unsupported-character-set"
    # a plain X on an attribute that the IOD requires there, with no enclosing
    # sequence that is Type 3 at its own place to remove with it (D-020)
    REQUIRED_BY_IOD = "required-by-iod"


_EXPLANATIONS = {
    SequesterReason.NO_DUMMY_VALUE: (
        "{action} on {path} needs a dummy value, which {vr} does not have "
        "and no reviewed rule gives"
    ),
    SequesterReason.VR_NOT_IN_DICTIONARY: (
        "{path} is written with {vr}, which the pinned data dictionary does not give it"
    ),
    SequesterReason.UNDECODABLE: (
        "{action} on {path} needs its value, which cannot be decoded"
    ),
    SequesterReason.UNSUPPORTED_CHARACTER_SET: (
        "{path} is not, or cannot be read as, a supported Specific Character Set"
    ),
    SequesterReason.REQUIRED_BY_IOD: (
        "{action} on {path} removes an attribute that the IOD requires there, "
        "and no enclosing sequence that the IOD makes Type 3 can be removed "
        "with it"
    ),
}


@dataclasses.dataclass(frozen=True)
class Sequestration:
    """Why the instance must be sequestered, at one element.

    Attributes
    ----------
    path : ElementPath
        The element.
    action : str
        Its action, such as ``"D"``.
    vr : str or None
        Its VR as written for :attr:`SequesterReason.VR_NOT_IN_DICTIONARY`,
        and otherwise as :attr:`ElementPlan.vr` gives it.
    reason : SequesterReason
    """

    path: ElementPath
    action: str
    vr: str | None
    reason: SequesterReason

    def __str__(self) -> str:
        vr = "an unknown VR" if self.vr is None else f"VR {self.vr}"
        explanation = _EXPLANATIONS[self.reason].format(
            action=self.action, path=self.path, vr=vr
        )
        return f"{explanation}, so the instance must be sequestered"


@dataclasses.dataclass(frozen=True)
class ElementPlan:
    """One element's action, and what must read its value.

    Attributes
    ----------
    path : ElementPath
    vr : str or None
        The VR that the value is read by: as written, or, in implicit VR or
        in place of UN, the one VR that the pinned data dictionary gives;
        ``None`` where neither gives one.
    rule : ElementRule or None
        The element's rule, or ``None`` if it is removed with a sequence.
    action : str
        ``"K"``, ``"X"``, ``"Z"``, ``"D"``, ``"U"``, or ``"C"``; ``"X"`` if
        it is removed with a sequence.
    removed_with : ElementPath or None
        The outermost sequence that removes it, or ``None``.
    consumers : frozenset of Consumer
    removed_for : ElementPath or None
        The attribute whose plain X, where the IOD requires that attribute,
        removes this element, which its own rule would not remove (D-020):
        the innermost enclosing sequence that is Type 3 at its own place, or
        another attribute of the overlay group of Overlay Data (60xx,3000).
        Otherwise ``None``.
    """

    path: ElementPath
    vr: str | None
    rule: ElementRule | None
    action: str
    removed_with: ElementPath | None
    consumers: frozenset[Consumer]
    removed_for: ElementPath | None = None


@dataclasses.dataclass(frozen=True)
class InstancePlan:
    """The plan of every element of one data set.

    Attributes
    ----------
    elements : tuple of ElementPlan
        In file order, nested elements included.
    sequestrations : tuple of Sequestration
        Each reason found that the instance must be sequestered, in file
        order; ``()`` if there is none.
    """

    elements: tuple[ElementPlan, ...]
    sequestrations: tuple[Sequestration, ...]

    def to_decode(self) -> tuple[ElementPath, ...]:
        """Return the paths of the elements that a consumer must read, in file order."""
        return tuple(element.path for element in self.elements if element.consumers)


def _consumers(action: str, container: bool, dummy: bool) -> frozenset[Consumer]:
    if container:
        return frozenset()
    found = {_ACTION_CONSUMERS[action]} if action in _ACTION_CONSUMERS else set()
    if dummy:
        found.add(Consumer.DUMMY_COMPARISON)
    if action != "K":
        found.add(Consumer.RESIDUAL_COLLECTION)
    return frozenset(found)


def _vr_contradicts_dictionary(tag: str, written: str | None) -> bool:
    """Whether a dictionary attribute is written with a VR it is not given."""
    attribute = dictionary_attribute(tag)
    return (
        attribute is not None
        and written not in (None, "UN")
        and written not in attribute.vrs
    )


def _has_dummy(tag: str, vr: str | None, container: bool, action: str) -> bool:
    """Whether a generic or reviewed dummy value exists for the element."""
    if container:
        return action == "D" and tag in REVIEWED_DUMMY_SEQUENCES
    return vr in DUMMY_VRS or (tag == ICC_PROFILE and vr == "OB")


def _removing_ancestor(
    path: ElementPath, removing: dict[ElementPath, str]
) -> ElementPath | None:
    """Return the outermost sequence in ``removing`` that holds ``path``."""
    for depth, (tag, _) in enumerate(path.items):
        container = ElementPath(path.items[:depth], tag)
        if container in removing:
            return container
    return None


def _compared_in_reviewed_dummy(
    path: ElementPath, removed_with: ElementPath, action: str
) -> bool:
    """Whether a reviewed dummy sequence's rule compares this element."""
    compared = REVIEWED_DUMMY_SEQUENCES.get(removed_with.tag, frozenset())
    return (
        action == "D"
        and len(path.items) == len(removed_with.items) + 1
        and path.tag in compared
    )


@dataclasses.dataclass
class _PlainRemovals:
    """What plain X, where the IOD requires the attribute, removes with it.

    Each removed sequence, and each overlay group, by its items' path and
    group, maps to the first attribute in file order that removes it.
    """

    sequences: dict[ElementPath, ElementPath] = dataclasses.field(default_factory=dict)
    overlay_groups: dict[tuple[tuple, str], ElementPath] = dataclasses.field(
        default_factory=dict
    )

    def removed_for(self, path: ElementPath) -> ElementPath | None:
        """Return the attribute whose plain X removes ``path``, if any."""
        found = self.sequences.get(path)
        if found is None:
            found = self.overlay_groups.get((path.items, _group(path.tag)))
        return None if found == path else found


def _group(tag: str) -> str:
    return tag[1:5]


def _plan_plain_x(
    iod: IOD,
    path: ElementPath,
    vr: str | None,
    found: _PlainRemovals,
    sequestrations: list[Sequestration],
) -> None:
    """Record what a plain X on an attribute removes with it (D-020)."""
    removal = resolve_plain_x_in_iod(iod, path.tag, tuple(t for t, _ in path.items))
    if removal.extent is RemovalExtent.SEQUENCE:
        depth = removal.sequence
        assert depth is not None  # PlainRemoval checks this
        sequence = ElementPath(path.items[:depth], path.items[depth][0])
        found.sequences.setdefault(sequence, path)
    elif removal.extent is RemovalExtent.OVERLAY_GROUP:
        found.overlay_groups.setdefault((path.items, _group(path.tag)), path)
    elif removal.extent is RemovalExtent.SEQUESTER:
        sequestrations.append(
            Sequestration(path, _REMOVED, vr, SequesterReason.REQUIRED_BY_IOD)
        )


def _resolve(iod: IOD, path: ElementPath, rule: ElementRule) -> str:
    """Resolve a rule's action from the element's Type at its place (D-020)."""
    resolve = (
        resolve_in_iod if rule.action in COMPOUND_ACTIONS else resolve_plain_in_iod
    )
    return resolve(iod, path.tag, tuple(tag for tag, _ in path.items), rule.action)


def _plan(
    source: SourceEvidence, rules: ElementRules, iod: IOD, forced: _PlainRemovals
) -> tuple[InstancePlan, _PlainRemovals]:
    """Plan every element, removing what ``forced`` says plain X removes.

    Also return what each plain X found removes with its attribute.
    """
    elements: list[ElementPlan] = []
    sequestrations: list[Sequestration] = []
    found = _PlainRemovals()
    removing: dict[ElementPath, str] = {}  # each removing sequence's action
    for path in source.paths():
        extent = source.element(path)
        vr = extent.location.vr
        container = extent.items is not None
        removed_with = _removing_ancestor(path, removing)
        if removed_with is not None:
            consumers = _consumers(
                _REMOVED,
                container,
                _compared_in_reviewed_dummy(path, removed_with, removing[removed_with]),
            )
            elements.append(
                ElementPlan(path, vr, None, _REMOVED, removed_with, consumers)
            )
            continue
        rule = rules.rule(path.tag, tuple(tag for tag, _ in path.items), iod=iod)
        action = _resolve(iod, path, rule)
        removed_for = forced.removed_for(path) if action != _REMOVED else None
        if removed_for is not None:
            action = _REMOVED
        elif rule.action == _REMOVED and rule.source is not RuleSource.ENGINE:
            # The engine's own removals apply whatever the Type.
            _plan_plain_x(iod, path, vr, found, sequestrations)
        if action != _REMOVED and _vr_contradicts_dictionary(path.tag, extent.vr):
            sequestrations.append(
                Sequestration(
                    path, action, extent.vr, SequesterReason.VR_NOT_IN_DICTIONARY
                )
            )
        elif action == "D" and not _has_dummy(path.tag, vr, container, action):
            sequestrations.append(
                Sequestration(path, action, vr, SequesterReason.NO_DUMMY_VALUE)
            )
        if container and action not in DESCENDED:
            removing[path] = action
        consumers = _consumers(action, container, False)
        elements.append(
            ElementPlan(path, vr, rule, action, None, consumers, removed_for)
        )
    return InstancePlan(tuple(elements), tuple(sequestrations)), found


def plan_instance(
    source: SourceEvidence, rules: ElementRules, iod: IOD
) -> InstancePlan:
    """Return the plan of every element of a source file's data set.

    A plain X can remove a sequence that encloses its attribute, or the
    other attributes of an overlay group, some of which come before it in
    file order, so the data set is planned again where one does.

    Parameters
    ----------
    source : SourceEvidence
        The source file, from
        :func:`~pymedphys._dicom.deidentify.source.read_source`.
    rules : ElementRules
        The rule of every element under the run's policy.
    iod : IOD
        The instance's IOD, from its SOP Class UID
        (:func:`~pymedphys._dicom.deidentify.scope.classify`).

    Returns
    -------
    InstancePlan
    """
    plan, removals = _plan(source, rules, iod, _PlainRemovals())
    if removals.sequences or removals.overlay_groups:
        # Planning again only removes more, so it finds nothing new to force.
        plan, _ = _plan(source, rules, iod, removals)
    return plan
