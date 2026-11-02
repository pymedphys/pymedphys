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

"""The Clean Structured Content Option: content items by their concept names.

PS3.15 E.3.4 has the option remove "any information encoded in SR Content
Items or Acquisition Context or Specimen Preparation Sequence Items
corresponding to the Attribute information specified to be removed by the
Profile and any other Options specified", and Table E.3.4-1 gives the
action of the Basic Profile and of each option for each content item, by
its concept name and Value Type (:mod:`.structured_content`). Table E.1-1
gives C under the option to the four sequences that hold content items, and
the engine cleans three of them (D-047):

- Acquisition Context Sequence (0040,0555), whose items are content items
  (PS3.3 Section C.7.6.14), in the Enhanced and Legacy Converted Enhanced
  images, the PET Image, and MR Spectroscopy;
- Specimen Preparation Sequence (0040,0610), whose items each hold their
  content items in Specimen Preparation Step Content Item Sequence
  (0040,0612) (PS3.3 Section C.7.6.22), in the Specimen Module, which every
  supported image IOD allows; and
- Content Sequence (0040,A730), whose items are content items, each of
  which may hold its own Content Sequence, and so on, as the Document
  Relationship Macro includes itself (PS3.3 Table C.17-6), in the SR
  Document Content Module of Structured Reports and Key Object Selection
  documents, and in the Encapsulated Document Module. The data set that
  holds the outermost one, such as a Structured Report's root, is a content
  item too where it has a Value Type (PS3.3 Section C.17.3). No IOD of the
  first supported release defines it, so it is cleaned only once one does.

Under the option, :func:`content_item_actions` gives the walker an action for
each such sequence and for the value of each content item in it, from the
item's Value Type (0040,A040) and the code of its Concept Name Code Sequence
(0040,A043), read from the source:

- a sequence is kept, as a container whose items' elements take their own
  rules, where the IOD defines it at its place and every content item in it
  can be kept, at any depth of nested Content Sequence, with the content
  item that holds an outermost Content Sequence; otherwise it takes the
  action that the element rules give it, its Basic Profile action, which
  removes or empties it, or sequesters the instance where it is D, since a
  sequence has no dummy value (D-021). A nested Content Sequence that the
  IOD does not define at its place takes its own rule, as any element of a
  kept item does. A content item cannot be kept where Table E.3.4-1 gives
  it X, or X/D, which removes it, since no template that the engine checks
  requires it; where its Value Type or concept name cannot be read as one
  Value Type and one code; where its concept name is coded in a scheme whose
  rows the pin leaves out (LOINC, NCDR, NCIt, and UMLS); or where it is
  coded by a retired SNOMED designator, SRT, SNM3, or 99SDM, with a SNOMED
  ID that PS3.16 Table O-1 does not map to a SNOMED CT Concept ID. One that
  Table O-1 maps is looked up as that SNOMED CT code, as PS3.16 Section 8.1
  has a receiver read it (:func:`~.codes.snomed_ct_code`). In Content Sequence, an item that PS3.3 Table C.17-5 lets have no
  concept name, such as an image reference, and has none, is not listed,
  and an item of a by-reference relationship, which has a Referenced
  Content Item Identifier (0040,DB73) in place of a Value Type and a
  concept name, is not a content item itself, since its target is cleaned
  where it is. The writer keeps every item of a kept sequence, so a single
  item cannot be removed on its own, which also keeps the place in the
  tree that each Referenced Content Item Identifier names;
- an item whose concept name Table E.3.4-1 lists, which can be kept, gives
  its value attribute the action that the selected options give the concept,
  K, D, or C, as Table E.1-1's options give an attribute. C under Clean
  Descriptors, which no cleaner of content items settles, falls back to the
  action that the concept takes without that option, as an attribute's does
  where descriptor cleaning does not write it (D-009). Where the remaining options give K and C, C applies, as
  ``tps-import`` resolves Retain Device Identity's K and Modified Dates' C;
  in 2026d no concept has both. C under Modified Dates is settled by its
  cleaner (:mod:`.modified_dates`), by the temporal role of the value
  attribute;
- the value of an item whose concept name the table does not list, and every
  other element of a kept item, takes its own rule: Table E.1-1 gives Person
  Name (0040,A123), Date (0040,A121), Time (0040,A122), and DateTime
  (0040,A120) D, and UID (0040,A124) U; Text Value (0040,A160) has a
  supplementary rule; and codes and numbers are kept, as in any kept
  sequence (D-022).

Waveform Annotation Sequence (0040,B020), which only IODs outside the first
supported release define, takes its Basic Profile action, as any sequence
given C does (:class:`~.element_rules.ElementRules`).
"""

from __future__ import annotations

import dataclasses
import functools
import types
from collections.abc import Collection, Iterator, Mapping

from .codes import RETIRED_SNOMED_DESIGNATORS, snomed_ct_code
from .elements import UndecodableElement, dataset_codecs, read_element
from .file_layout import ElementPath
from .iods import IOD
from .policy import CLEAN_DESCRIPTORS, CLEAN_STRUCTURED_CONTENT, Policy
from .source import SourceEvidence
from .structured_content import (
    VALUE_TYPES,
    ContentItemConcept,
    load_table_e3_4_1,
)

ACQUISITION_CONTEXT = "(0040,0555)"
SPECIMEN_PREPARATION = "(0040,0610)"
SPECIMEN_PREPARATION_STEP = "(0040,0612)"
CONTENT_SEQUENCE = "(0040,A730)"
# The sequences under the option whose content items are cleaned, each with
# the sequences, from one of its items, whose items are the content items.
CONTENT_ITEM_SEQUENCES: Mapping[str, tuple[str, ...]] = types.MappingProxyType(
    {
        ACQUISITION_CONTEXT: (),
        SPECIMEN_PREPARATION: (SPECIMEN_PREPARATION_STEP,),
        CONTENT_SEQUENCE: (),
    }
)
VALUE_TYPE = "(0040,A040)"
CONCEPT_NAME = "(0040,A043)"
# A content item's modifiers, themselves content items (PS3.3 Table 10.2.1-1).
MODIFIERS = "(0040,0441)"
# The position in the content tree of the target of a by-reference
# relationship, an item of Content Sequence that is not a content item
# itself (PS3.3 Table C.17-6).
REFERENCED_CONTENT_ITEM = "(0040,DB73)"
# The Value Types of the items of Content Sequence that may have no concept
# name: a CONTAINER without a heading, other than the root, and a reference
# or coordinates whose purpose the concept name does not convey (PS3.3 Table
# C.17-5).
UNNAMED_VALUE_TYPES = frozenset(
    {"CONTAINER", "COMPOSITE", "IMAGE", "WAVEFORM", "SCOORD", "SCOORD3D", "TCOORD"}
)
CODE_VALUE = "(0008,0100)"
DESIGNATOR = "(0008,0102)"
# The codes that a concept name may give in place of Code Value, none of
# which Table E.3.4-1 lists, since its codes are short and have designators.
OTHER_CODE_VALUES = ("(0008,0119)", "(0008,0120)")
# The attribute that holds the value of a content item of each Value Type
# whose value one attribute holds (PS3.3 Table 10-2).
VALUE_ATTRIBUTES: Mapping[str, str] = types.MappingProxyType(
    {
        "DATETIME": "(0040,A120)",
        "DATE": "(0040,A121)",
        "TIME": "(0040,A122)",
        "PNAME": "(0040,A123)",
        "UIDREF": "(0040,A124)",
        "TEXT": "(0040,A160)",
    }
)
# The Content Item Macro's Value Type of a number (PS3.3 Table 10-2), which
# Table E.3.4-1, following Section C.17.3, gives as NUM.
NUMERIC = "NUMERIC"
NUM = "NUM"
# The coding schemes whose rows the pin leaves out of the generated table, so
# that their concepts cannot be matched. A code of a retired SNOMED
# designator is matched as the SNOMED CT code that PS3.16 Table O-1 maps it
# to, and cannot be matched where the table maps it to none.
UNMATCHED_SCHEMES = frozenset({"LN", "NCDR", "NCIt", "UMLS"})
KEEP = "K"
REMOVE = "X"

# How the conformance statement describes the cleaning, naming no value.
METHOD = (
    "Each sequence is kept where the IOD defines it at its place, and each "
    "content item in it is cleaned by its Value Type (0040,A040) and the "
    "code of its Concept Name Code Sequence (0040,A043), as PS3.15 Table "
    "E.3.4-1 gives them: in Acquisition Context Sequence, its items and "
    "their modifiers in Content Item Modifier Sequence (0040,0441); in "
    "Specimen Preparation Sequence, the items of each item's Specimen "
    "Preparation Step Content Item Sequence (0040,0612); and in Content "
    "Sequence (0040,A730), its items and, at any depth, the items of each "
    "Content Sequence that an item holds where the IOD defines it, with the "
    "data set that holds the outermost one, such as a Structured Report's "
    "root, where it has a Value Type. An item whose "
    "concept name the table lists takes the action that the selected "
    "options give it, or else its Basic Profile action, on the attribute "
    "that holds its value; C under Clean Descriptors takes the action "
    "without that option, as for an attribute that descriptor cleaning "
    "does not write, and C under "
    "Retain Longitudinal Temporal Information with Modified Dates modifies "
    "the date, time, or datetime by its temporal role. Every other element "
    "of an item, and the value of an item whose concept name the table does "
    "not list, takes its own rule, as in any kept sequence. In Content "
    "Sequence, an item that PS3.3 lets have no concept name, such as an "
    "image reference, and has none, is not listed, and a by-reference "
    "relationship keeps its Referenced Content Item Identifier (0040,DB73), "
    "since its target is cleaned where it is. Where the table "
    "removes an item (X or X/D), where an item's Value Type or concept name "
    "cannot be read as one Value Type and one code, where its concept "
    "name is coded in LOINC, NCDR, NCIt, or UMLS, whose rows PyMedPhys does "
    "not include, or where it is coded by a retired SNOMED designator, SRT, "
    "SNM3, or 99SDM, with a code that PS3.16 Table O-1 does not map to a "
    "SNOMED CT code, the whole sequence takes its Basic Profile action "
    "instead, since a single item is not removed on its own. A concept name "
    "coded by a retired SNOMED designator with a code that Table O-1 maps is "
    "looked up as that SNOMED CT code."
)


def concept_action(concept: ContentItemConcept, options: Collection[str]) -> str:
    """Return the action that a policy's options give a content item's value.

    Parameters
    ----------
    concept : ContentItemConcept
        The row of Table E.3.4-1.
    options : collection of str
        The policy's options, as named in Table E.1-1.

    Returns
    -------
    str
        ``"X"`` where the item is to be removed, from X or X/D; otherwise
        ``"K"``, ``"D"``, or ``"C"``. C under Clean Descriptors is left out,
        so that the concept takes the action without that option (D-009);
        where the remaining options give K and C, C applies; and an action
        other than K or C from an option, which the 2026d table does not
        give, removes the item.

    Examples
    --------
    >>> from pymedphys._dicom.deidentify.structured_content import (
    ...     load_table_e3_4_1,
    ... )
    >>> rows = {c.code_meaning: c for c in load_table_e3_4_1().concepts}
    >>> concept_action(rows["Person Observer Name"], ())
    'D'
    >>> concept_action(rows["Acquisition Protocol"], ("clean_descriptors",))
    'X'
    """
    given = {
        action
        for option, action in concept.options.items()
        if option in options and not (option == CLEAN_DESCRIPTORS and action == "C")
    }
    if not given:
        return REMOVE if concept.basic_profile == "X/D" else concept.basic_profile
    if given == {KEEP}:
        return KEEP
    return "C" if given <= {KEEP, "C"} else REMOVE


@functools.lru_cache(maxsize=None)
def concept_actions(options: tuple[str, ...]) -> Mapping[tuple[str, str, str], str]:
    """Return :func:`concept_action` of each row of the table, by its key.

    The key is the row's coding scheme designator, code value, and Value
    Type (:attr:`~.structured_content.ContentItemConcept.key`).
    """
    return types.MappingProxyType(
        {
            concept.key: concept_action(concept, options)
            for concept in load_table_e3_4_1().concepts
        }
    )


class _Unkept(Exception):
    """A content item that cannot be kept, so its sequence is not kept."""


class _Reader:
    """Read the structure and codes of content items against the source.

    Each data set is reached once, through the sequences that hold it, as the
    edits read values (:mod:`.edits`).
    """

    def __init__(self, source: SourceEvidence) -> None:
        self._source = source
        self._holders: dict[tuple, tuple] = {}

    def __contains__(self, path: object) -> bool:
        return path in self._source

    def count(self, path: ElementPath) -> int:
        """Return how many items the sequence at ``path`` holds, 0 if absent."""
        if path not in self._source:
            return 0
        items = self._source.element(path).items
        if items is None:
            raise _Unkept
        return items

    def _holder(self, items: tuple) -> tuple:
        """Return the data set at ``items``, its ancestors, and its codecs."""
        if items not in self._holders:
            if not items:
                root = self._source.dataset()
                self._holders[()] = (
                    root,
                    (),
                    dataset_codecs(root, source=self._source),
                )
            else:
                dataset, ancestors, inherited = self._holder(items[:-1])
                tag, index = items[-1]
                path = ElementPath(items[:-1], tag)
                item = read_element(
                    dataset, path, inherited, ancestors, source=self._source
                ).items[index]
                self._holders[items] = (
                    item,
                    (dataset, *ancestors),
                    dataset_codecs(item, inherited, items, source=self._source),
                )
        return self._holders[items]

    def text(self, path: ElementPath) -> str | None:
        """Return an element's one value, without padding, or None if absent."""
        if path not in self._source:
            return None
        dataset, ancestors, codecs = self._holder(path.items)
        values = read_element(
            dataset, path, codecs, ancestors, source=self._source
        ).values
        if len(values) != 1 or not isinstance(values[0], str):
            raise _Unkept
        return values[0].strip(" ")


@dataclasses.dataclass
class _Sequences:
    """Find the actions of the content-item sequences of one instance."""

    reader: _Reader
    actions: Mapping[tuple[str, str, str], str]
    iod: IOD

    def outermost(self, path: ElementPath) -> dict[ElementPath, str]:
        """Return the actions of a kept sequence that no other one holds.

        The data set that holds a Content Sequence is a content item itself
        where it has a Value Type, as a Structured Report's root is (PS3.3
        Section C.17.3), so it is cleaned too, apart from that Content
        Sequence, which is ``path``.
        """
        found = self.sequence(path)
        value_type = ElementPath(path.items, VALUE_TYPE)
        if path.tag == CONTENT_SEQUENCE and value_type in self.reader:
            found.update(self.item(path.items, contents=False))
        return found

    def sequence(self, path: ElementPath) -> dict[ElementPath, str]:
        """Return the actions of a kept sequence and of its items' values."""
        found = {path: KEEP}
        for index in range(self.reader.count(path)):
            holder = (*path.items, (path.tag, index))
            for items in self._content_items(holder, CONTENT_ITEM_SEQUENCES[path.tag]):
                found.update(self.item(items))
        return found

    def _content_items(self, holder: tuple, via: tuple[str, ...]) -> Iterator[tuple]:
        """Yield the items of the content items that ``holder`` reaches."""
        if not via:
            yield holder
            return
        step = ElementPath(holder, via[0])
        for index in range(self.reader.count(step)):
            yield from self._content_items((*holder, (via[0], index)), via[1:])

    def item(self, items: tuple, contents: bool = True) -> dict[ElementPath, str]:
        """Return the actions of a content item's value and its modifiers' values.

        With ``contents``, also those of the Content Sequence that the item
        holds, where the IOD defines it there, and of its items, at any
        depth. One that the IOD does not define there takes its own rule.

        An item of Content Sequence that has a Referenced Content Item
        Identifier and neither a Value Type nor a concept name is a
        by-reference relationship, whose target is cleaned where it is in
        the tree, so it gives no action. One whose Value Type
        :data:`UNNAMED_VALUE_TYPES` lists may have no concept name, and is
        then not listed.
        """
        in_tree = bool(items) and items[-1][0] == CONTENT_SEQUENCE
        value_type_path = ElementPath(items, VALUE_TYPE)
        if (
            in_tree
            and value_type_path not in self.reader
            and ElementPath(items, CONCEPT_NAME) not in self.reader
            and ElementPath(items, REFERENCED_CONTENT_ITEM) in self.reader
        ):
            return {}
        value_type = self.reader.text(value_type_path)
        value_type = NUM if value_type == NUMERIC else value_type
        if value_type not in VALUE_TYPES:
            raise _Unkept
        if (
            in_tree
            and value_type in UNNAMED_VALUE_TYPES
            and ElementPath(items, CONCEPT_NAME) not in self.reader
        ):
            action = None
        else:
            action = self._concept_action(items, value_type)
        if action == REMOVE:
            raise _Unkept
        found = {}
        value = ElementPath(items, VALUE_ATTRIBUTES.get(value_type, VALUE_TYPE))
        if action is not None and value.tag != VALUE_TYPE:
            found[value] = action
        modifiers = ElementPath(items, MODIFIERS)
        for index in range(self.reader.count(modifiers)):
            found.update(self.item((*items, (MODIFIERS, index))))
        nested = ElementPath(items, CONTENT_SEQUENCE)
        if contents and nested in self.reader and _defined(self.iod, nested):
            found.update(self.sequence(nested))
        return found

    def _concept_action(self, items: tuple, value_type: str) -> str | None:
        """Return the action of a content item's concept, or None if unlisted."""
        concept = ElementPath(items, CONCEPT_NAME)
        if self.reader.count(concept) != 1:
            raise _Unkept
        code = (*items, (CONCEPT_NAME, 0))
        value = self.reader.text(ElementPath(code, CODE_VALUE))
        designator = self.reader.text(ElementPath(code, DESIGNATOR))
        if value is None:
            # A long or URN code value, which the table does not list, and
            # which no SNOMED ID is.
            if any(ElementPath(code, tag) in self.reader for tag in OTHER_CODE_VALUES):
                if (
                    designator in UNMATCHED_SCHEMES
                    or designator in RETIRED_SNOMED_DESIGNATORS
                ):
                    raise _Unkept
                return None
            raise _Unkept
        if not designator or designator in UNMATCHED_SCHEMES:
            raise _Unkept
        if designator in RETIRED_SNOMED_DESIGNATORS:
            mapped = snomed_ct_code(designator, value)
            if mapped is None:
                raise _Unkept
            designator, value = mapped
        return self.actions.get((designator, value, value_type))


def _defined(iod: IOD, path: ElementPath) -> bool:
    """Return whether the IOD defines the element at ``path`` at its place."""
    return bool(iod.lookup(path.tag, tuple(tag for tag, _ in path.items)))


def _held(path: ElementPath, sequences: Collection[ElementPath]) -> bool:
    """Return whether one of ``sequences`` holds ``path`` in its items."""
    return any(
        ElementPath(path.items[:depth], tag) in sequences
        for depth, (tag, _) in enumerate(path.items)
    )


def content_item_actions(
    source: SourceEvidence, policy: Policy, iod: IOD
) -> Mapping[ElementPath, str]:
    """Return the actions that the walker gives content items under the option.

    Parameters
    ----------
    source : SourceEvidence
        The instance's source.
    policy : Policy
        The run's policy, or the policy whose plan descriptor cleaning falls
        back to.
    iod : IOD
        The instance's IOD.

    Returns
    -------
    Mapping of ElementPath to str
        Empty unless the policy selects Clean Structured Content. Otherwise,
        each sequence of :data:`CONTENT_ITEM_SEQUENCES` that is kept gives
        ``"K"``, and the value attribute of each content item in it whose
        concept name Table E.3.4-1 lists gives the action that
        :func:`concept_action` gives the concept, at each place. A sequence
        that is not kept, and everything in it, is left out, so that it
        takes the action that the element rules give it. So is one whose
        items cannot be decoded, or whose character set is not supported.
        A Content Sequence in an item of another is cleaned with the
        outermost one, and is left out with it.
    """
    if CLEAN_STRUCTURED_CONTENT not in policy.options:
        return types.MappingProxyType({})
    candidates = [
        path
        for path in source.paths()
        if path.tag in CONTENT_ITEM_SEQUENCES and _defined(iod, path)
    ]
    found: dict[ElementPath, str] = {}
    if candidates:
        sequences = _Sequences(_Reader(source), concept_actions(policy.options), iod)
        held = frozenset(candidates)
        for path in candidates:
            if _held(path, held):
                continue
            try:
                found.update(sequences.outermost(path))
            except (_Unkept, UndecodableElement, IndexError):
                continue
    return types.MappingProxyType(found)
