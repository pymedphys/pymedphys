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
  item too where it has a Value Type (PS3.3 Section C.17.3). Of the IODs of
  the first supported release, the X-Ray Radiation Dose SR and
  Radiopharmaceutical Radiation Dose SR define it.

Under the option, :func:`content_item_actions` gives the walker an action for
each such sequence and for the value of each content item in it, from the
item's Value Type (0040,A040) and the code of its Concept Name Code Sequence
(0040,A043), read from the source:

- Acquisition Context Sequence and Specimen Preparation Sequence are each
  kept, as a container whose items' elements take their own rules, where
  the IOD defines it at its place and every content item in it can be kept;
  otherwise it takes the action that the element rules give it, its Basic
  Profile action, which removes or empties it;
- a Content Sequence that the IOD defines at its place is kept with the
  content item that holds it, where that data set has a Value Type, and its
  items are cleaned at any depth of nested Content Sequence that the IOD
  defines at its place (:class:`_ContentTree`). An item that cannot be kept
  is removed on its own, with everything in it, and so, until nothing
  changes, is every item whose own elements hold a Referenced Content Item
  Identifier (0040,DB73) that names a removed item, or one inside it, such
  as a by-reference relationship, every item other than a CONTAINER whose
  item of Relationship Type HAS CONCEPT MOD is removed, and every CONTAINER
  whose items are all removed; any other item whose items are all removed
  loses its Content Sequence, which is Type 1C (PS3.3 Table C.17-6). A
  CONTAINER, the root among them, is kept without its removed HAS CONCEPT
  MOD item. Each Referenced Content
  Item Identifier that is kept is renumbered, so that it names the same
  item once the items before it are gone (PS3.3 Section C.17.3.2.5). The
  outermost Content Sequence takes its Basic Profile action instead, which
  sequesters a Structured Report, since its D has no dummy value (D-021),
  where the content item that holds it cannot be kept or is left with no
  items, where any item cannot be read, or where an item is removed and a
  Referenced Content Item Identifier names no item of the source. A nested
  Content Sequence that the IOD does not define at its place takes its own
  rule, as any element of a kept item does. A content item cannot be kept
  where the selected options give it X; where its concept name is coded in
  a scheme whose rows the pin leaves out (LOINC, NCDR, NCIt, and UMLS); or
  where it is coded by a retired SNOMED designator, SRT, SNM3, or 99SDM,
  with a SNOMED ID that PS3.16 Table O-1 does not map to a SNOMED CT Concept
  ID; nor can one whose modifier in Content Item Modifier Sequence
  (0040,0441) cannot be kept. One that Table O-1 maps is looked up as that
  SNOMED CT code, as PS3.16 Section 8.1 has a receiver read it
  (:func:`~.codes.snomed_ct_code`). A content item cannot be read where its
  Value Type or concept name cannot be read as one Value Type and one code.
  In Content Sequence, an item that PS3.3 Table C.17-5 lets have no concept
  name, such as an image reference, and has none, is not listed, and an item
  of a by-reference relationship, which has a Referenced Content Item
  Identifier in place of a Value Type and a concept name, is not a content
  item itself, since its target is cleaned where it is;
- an item whose concept name Table E.3.4-1 lists, which can be kept, gives
  its value attribute the action that the selected options give the concept,
  K, D, or C, as Table E.1-1's options give an attribute. So does an item
  whose concept and Value Type a reviewed supplementary row lists
  (:mod:`.supplementary_concepts`): a patient characteristic that the table
  omits, which is removed, and kept under Retain Patient Characteristics
  where Table E.1-1 keeps the attribute that holds it; a UDI as a CODE,
  which is removed, and kept under Retain Device Identity, as Table E.1-1
  keeps UDI Sequence (0018,100A); and Subject ID as a CODE, which TID 1007
  gives it and the table lists only as TEXT, and which
  is removed under every option (D-047). X/D gives D: the
  table gives D where a template requires the item, a template of PS3.16
  requires each X/D concept somewhere, and the engine reads every such item
  as required rather than matching it to the template row it fills, as a
  compound action resolves from the strictest Type (D-020); so do the X rows
  of DateTime Ended and X-Ray Attenuator Model Data
  (:data:`DUMMY_IN_PLACE_OF_REMOVAL`), which the templates of Enhanced X-Ray
  Radiation Dose reports require. D writes D-021's dummy value, a constant,
  for TEXT, DATE, TIME, and DATETIME; gives a UIDREF item's UID U's
  replacement, which keeps a UID that the pinned tables register, such as a
  public frame of reference, so that the item names what the attributes that
  U replaces name, and makes an item with no UID unkeepable, as D refuses
  one; and leaves an IMAGE or COMPOSITE item its reference, whose UIDs take
  their own rules. C under Clean Descriptors, which no cleaner of content
  items settles, falls back to the action that the concept takes without
  that option, as an attribute's does where descriptor cleaning does not
  write it (D-009). Where the remaining options give K and C, C applies, as
  ``tps-import`` resolves Retain Device Identity's K and Modified Dates' C;
  in 2026d no concept has both. C under Modified Dates is settled by its
  cleaner (:mod:`.modified_dates`), by the temporal role of the value
  attribute;
- the value of an item whose concept name neither the table nor a
  supplementary row lists, and every other element of a kept item, takes
  its own rule: Table E.1-1 gives Person
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
from .removed_items import Item, RemovedItems
from .source import SourceEvidence
from .structured_content import (
    VALUE_TYPES,
    ContentItemConcept,
    load_table_e3_4_1,
)
from .supplementary_concepts import SupplementaryConcept, load_supplementary_concepts
from .uids import normalise_uid

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
# The relationship of an item of Content Sequence to the item that holds it,
# and the one by which it modifies that item's concept name (PS3.3 Section
# C.17.3.2.4).
RELATIONSHIP_TYPE = "(0040,A010)"
HAS_CONCEPT_MOD = "HAS CONCEPT MOD"
# The position in the content tree of the target of a by-reference
# relationship, an item of Content Sequence that is not a content item
# itself (PS3.3 Table C.17-6).
REFERENCED_CONTENT_ITEM = "(0040,DB73)"
# The Value Type of an item that holds other items, under a heading.
CONTAINER = "CONTAINER"
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
DUMMY = "D"
REPLACE_UID = "U"
UID_VALUE = "(0040,A124)"
EITHER = "X/D"
# The rows that Table E.3.4-1 gives X whose concepts the templates of
# Enhanced X-Ray Radiation Dose reports require, which take D as an X/D
# concept does, so that such a report keeps the rows its templates require
# (D-047): DateTime Ended, required by TID 10042 to TID 10054, and X-Ray
# Attenuator Model Data, of which TID 10051 and TID 10052 each require
# exactly one of the three Value Types. By each row's key.
DUMMY_IN_PLACE_OF_REMOVAL = frozenset(
    {
        ("DCM", "111527", "DATETIME"),
        ("DCM", "128470", "COMPOSITE"),
        ("DCM", "128470", "IMAGE"),
        ("DCM", "128470", "UIDREF"),
    }
)

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
    "that holds its value. An item whose concept name and Value Type the "
    "table omits takes the action of a reviewed row instead where it holds "
    "a patient characteristic that PS3.15 Table E.1-1 removes: a coded "
    "patient state, the sex parameters for "
    "clinical use, a racial group, a pregnancy or smoking status, which are "
    "removed, and kept under Retain Patient Characteristics, and the comment "
    "on the sex parameters and a body mass index, which are removed under "
    "every option; a device's UDI as a CODE is removed, and kept under "
    "Retain Device Identity, as PS3.15 Table E.1-1 keeps UDI Sequence "
    "(0018,100A); and a Subject ID coded as a CODE, which the table lists "
    "only as TEXT, is removed under every option. "
    "X/D gives D wherever the concept appears, as "
    "though a template required the item there, since PS3.16's templates "
    "require each X/D concept in at least one place; X gives D too for "
    "DateTime Ended (111527, DCM) and X-Ray Attenuator Model Data (128470, "
    "DCM), which the templates of Enhanced X-Ray Radiation Dose reports "
    "require. D writes the dummy value of the value's VR; a UID takes the "
    "replacement that U gives it elsewhere, which keeps a UID that names a "
    "public definition, such as a registered frame of reference, and an "
    "item without one is not kept; and an image or "
    "composite reference is kept, with its UIDs taking their own rules. C "
    "under Clean Descriptors "
    "takes the action "
    "without that option, as for an attribute that descriptor cleaning "
    "does not write, and C under "
    "Retain Longitudinal Temporal Information with Modified Dates modifies "
    "the date, time, or datetime by its temporal role. Every other element "
    "of an item, and the value of an item whose concept name is not listed, "
    "takes its own rule, as in any kept sequence. In Content "
    "Sequence, an item that PS3.3 lets have no concept name, such as an "
    "image reference, and has none, is not listed, and a by-reference "
    "relationship keeps its Referenced Content Item Identifier (0040,DB73), "
    "since its target is cleaned where it is. An item cannot be kept where "
    "the options remove it (X), where its concept name is coded in LOINC, "
    "NCDR, NCIt, or UMLS, whose rows PyMedPhys does not include, or where it "
    "is coded by a retired SNOMED designator, SRT, SNM3, or 99SDM, with a "
    "code that PS3.16 Table O-1 does not map to a SNOMED CT code; nor can an "
    "item whose modifier cannot be kept. In Acquisition Context Sequence and "
    "Specimen Preparation Sequence, such an item, or one whose Value Type "
    "or concept name cannot be read as one Value Type and one code, leaves "
    "the whole sequence to take its Basic Profile action instead. In "
    "Content Sequence, an item that cannot be kept is "
    "removed on its own, with every item that it contains, and so is each "
    "item that names a removed item, or one inside it, by a Referenced "
    "Content Item Identifier, such as a by-reference relationship, each "
    "item other than a CONTAINER whose HAS CONCEPT MOD item is removed, and "
    "each CONTAINER whose items are all removed, while any other item whose "
    "items are all removed loses its Content Sequence, and a CONTAINER loses "
    "only its removed HAS CONCEPT MOD item; each Referenced "
    "Content Item Identifier that is kept is renumbered, so that it names "
    "the same item in the output. The whole Content Sequence takes its "
    "Basic Profile action instead where its root cannot be kept or is left "
    "with no items, where an item's Value Type or concept name cannot be "
    "read as one Value Type and one code, or where an item is removed and "
    "a Referenced Content Item Identifier names no item. A concept name "
    "coded by a retired SNOMED designator with a code that Table O-1 maps is "
    "looked up as that SNOMED CT code."
)


def concept_action(
    concept: ContentItemConcept | SupplementaryConcept, options: Collection[str]
) -> str:
    """Return the action that a policy's options give a content item's value.

    Parameters
    ----------
    concept : ContentItemConcept or SupplementaryConcept
        The row of Table E.3.4-1, or the supplementary row.
    options : collection of str
        The policy's options, as named in Table E.1-1.

    Returns
    -------
    str
        ``"X"`` where the item is to be removed; otherwise ``"K"``,
        ``"D"``, or ``"C"``. X/D gives D, as does X for a row of
        :data:`DUMMY_IN_PLACE_OF_REMOVAL`. C under Clean Descriptors is left
        out, so that the concept takes the action without that option
        (D-009); where the remaining options give K and C, C applies; and an
        action other than K or C from an option, which the 2026d table does
        not give, removes the item.

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
    >>> concept_action(rows["Device Serial Number"], ())
    'D'
    """
    given = {
        action
        for option, action in concept.options.items()
        if option in options and not (option == CLEAN_DESCRIPTORS and action == "C")
    }
    if not given:
        if concept.basic_profile == EITHER or (
            concept.basic_profile == REMOVE and concept.key in DUMMY_IN_PLACE_OF_REMOVAL
        ):
            return DUMMY
        return concept.basic_profile
    if given == {KEEP}:
        return KEEP
    return "C" if given <= {KEEP, "C"} else REMOVE


@functools.lru_cache(maxsize=None)
def concept_actions(options: tuple[str, ...]) -> Mapping[tuple[str, str, str], str]:
    """Return :func:`concept_action` of each row, by its key.

    The rows are those of Table E.3.4-1 and the supplementary rows
    (:mod:`.supplementary_concepts`), which never share a key. The key is
    the row's coding scheme designator, code value, and Value Type
    (:attr:`~.structured_content.ContentItemConcept.key`).
    """
    rows = (
        *load_table_e3_4_1().concepts,
        *load_supplementary_concepts().concepts,
    )
    return types.MappingProxyType(
        {concept.key: concept_action(concept, options) for concept in rows}
    )


class _Unkept(Exception):
    """A content item that cannot be read, so its sequence is not kept."""


class _Removed(_Unkept):
    """A content item that can be read but not kept.

    In Content Sequence, it is removed on its own, with everything in it;
    in any other sequence, its sequence is not kept.
    """


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

    def numbers(self, path: ElementPath) -> tuple[int, ...]:
        """Return an element's values as integers, such as those of an UL."""
        dataset, ancestors, codecs = self._holder(path.items)
        values = read_element(
            dataset, path, codecs, ancestors, source=self._source
        ).values
        if not values or not all(
            isinstance(value, int) and not isinstance(value, bool) for value in values
        ):
            raise _Unkept
        return tuple(int(value) for value in values)

    def paths(self) -> tuple[ElementPath, ...]:
        """Return the path of every element of the source, in file order."""
        return tuple(self._source.paths())


@dataclasses.dataclass
class _Sequences:
    """Find the actions of the content-item sequences of one instance."""

    reader: _Reader
    actions: Mapping[tuple[str, str, str], str]
    iod: IOD

    def outermost(self, path: ElementPath) -> _Outcome:
        """Return what is done with a kept sequence that no other one holds.

        A Content Sequence is cleaned as a tree (:class:`_ContentTree`), and
        any other sequence whole.
        """
        if path.tag == CONTENT_SEQUENCE:
            return _ContentTree(self, path).outcome()
        return _Outcome(self.sequence(path))

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
            raise _Removed
        found = {}
        value = ElementPath(items, VALUE_ATTRIBUTES.get(value_type, VALUE_TYPE))
        if action is not None and value.tag != VALUE_TYPE:
            found[value] = self._value_action(value, action)
        modifiers = ElementPath(items, MODIFIERS)
        for index in range(self.reader.count(modifiers)):
            found.update(self.item((*items, (MODIFIERS, index))))
        nested = ElementPath(items, CONTENT_SEQUENCE)
        if contents and nested in self.reader and _defined(self.iod, nested):
            found.update(self.sequence(nested))
        return found

    def _value_action(self, value: ElementPath, action: str) -> str:
        """Return the action of a listed content item's value attribute.

        D on the UID of a UIDREF item gives U's replacement, which keeps a
        UID that the pinned tables register, such as a public frame of
        reference, so that the item names what the attributes that U
        replaces name in the output, such as Frame of Reference UID
        (0020,0052). An item with no UID to replace cannot be kept,
        as D refuses one (D-021).
        """
        if value.tag != UID_VALUE or action != DUMMY:
            return action
        uid = self.reader.text(value)
        if uid is None or not normalise_uid(uid):
            raise _Removed
        return REPLACE_UID

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
                    raise _Removed
                return None
            raise _Unkept
        if not designator:
            raise _Unkept
        if designator in UNMATCHED_SCHEMES:
            raise _Removed
        if designator in RETIRED_SNOMED_DESIGNATORS:
            mapped = snomed_ct_code(designator, value)
            if mapped is None:
                raise _Removed
            designator, value = mapped
        return self.actions.get((designator, value, value_type))


@dataclasses.dataclass(frozen=True)
class _Outcome:
    """What is done with one outermost sequence, as :class:`ContentItemPlan`."""

    actions: Mapping[ElementPath, str]
    removed_items: frozenset[Item] = frozenset()
    emptied: frozenset[ElementPath] = frozenset()
    renumbered: Mapping[ElementPath, tuple[int, ...]] = dataclasses.field(
        default_factory=dict
    )


@dataclasses.dataclass
class _Node:
    """A content item of a Content Sequence that can be kept on its own.

    ``children`` are the items of the Content Sequence that it holds, where
    the IOD defines it there, and ``None`` where it holds none that is
    cleaned with the tree.
    """

    actions: Mapping[ElementPath, str]
    container: bool
    children: tuple[Item, ...] | None


@dataclasses.dataclass(frozen=True)
class _Reference:
    """A Referenced Content Item Identifier in the tree, and what it names.

    ``holder`` is the content item that holds it, which is removed with its
    target, and ``target`` the item it names, or ``None`` where it names
    none that the source holds.
    """

    path: ElementPath
    holder: Item
    values: tuple[int, ...]
    target: Item | None


class _ContentTree:
    """Clean one outermost Content Sequence, removing single items (D-047).

    Each item of the sequence, at any depth of nested Content Sequence that
    the IOD defines at its place, is kept, with its value's action, or, where
    it cannot be kept, removed on its own with everything in it. Then, until
    nothing changes, an item that holds a Referenced Content Item Identifier
    (0040,DB73) naming a removed item, or an item inside one, is removed
    too: a by-reference relationship, or an item whose own elements name
    one, such as a TABLE's Cell Values Sequence (0040,A808); an item other
    than a CONTAINER whose item of Relationship Type HAS CONCEPT MOD is
    removed is removed, since what is left would no longer say what its
    concept name means, while a CONTAINER, the root among them, is kept
    without it; a CONTAINER whose items are all removed is removed; and any
    other item whose items are all removed loses its Content Sequence, which
    is Type 1C (PS3.3 Table C.17-6). Every Referenced Content Item Identifier that is kept is
    renumbered to name the same item in the output (PS3.3 Section
    C.17.3.2.5). An item that cannot be read, the root where it cannot be
    kept or is left with no items, the root other than a CONTAINER whose
    HAS CONCEPT MOD item is removed, or an identifier that names no item
    where an item is removed, leaves the whole sequence to take its Basic
    Profile action, raising :class:`_Unkept`.
    """

    def __init__(self, sequences: _Sequences, path: ElementPath) -> None:
        self._sequences = sequences
        self._reader = sequences.reader
        self._path = path
        self._root: Item = path.items
        self._nodes: dict[Item, _Node] = {}
        self._removed: set[Item] = set()

    def outcome(self) -> _Outcome:
        """Return the tree's actions, removed items, and renumbering."""
        found: dict[ElementPath, str] = {self._path: KEEP}
        if ElementPath(self._root, VALUE_TYPE) in self._reader:
            try:
                found.update(self._sequences.item(self._root, contents=False))
            except _Removed:
                raise _Unkept from None
        children = self._walk(self._path)
        references = self._references()
        emptied = self._cascade(references)
        if children and all(child in self._removed for child in children):
            raise _Unkept
        emptied = {sequence for sequence in emptied if not self._gone(sequence.items)}
        removed = frozenset(
            item
            for item in self._removed
            if not self._gone(item, strict=True)
            and ElementPath(item[:-1], item[-1][0]) not in emptied
        )
        for items, node in self._nodes.items():
            if self._gone(items):
                continue
            found.update(node.actions)
            nested = ElementPath(items, CONTENT_SEQUENCE)
            if node.children is not None and nested not in emptied:
                found[nested] = KEEP
        return _Outcome(
            types.MappingProxyType(found),
            removed,
            frozenset(emptied),
            types.MappingProxyType(self._renumbered(references, removed)),
        )

    def _walk(self, sequence: ElementPath) -> tuple[Item, ...]:
        """Read the items of a Content Sequence, at any depth."""
        children = []
        for index in range(self._reader.count(sequence)):
            items = (*sequence.items, (sequence.tag, index))
            children.append(items)
            try:
                actions = self._sequences.item(items, contents=False)
            except _Removed:
                self._removed.add(items)
                continue
            nested = ElementPath(items, CONTENT_SEQUENCE)
            grandchildren = (
                self._walk(nested)
                if nested in self._reader and _defined(self._sequences.iod, nested)
                else None
            )
            container = (
                ElementPath(items, VALUE_TYPE) in self._reader
                and self._reader.text(ElementPath(items, VALUE_TYPE)) == CONTAINER
            )
            self._nodes[items] = _Node(actions, container, grandchildren)
        return tuple(children)

    def _holder(self, path: ElementPath) -> Item | None:
        """Return the content item of the tree that holds ``path``, if any.

        That is the innermost item reached from the root through Content
        Sequence alone, or the root; ``None`` where that item is not in the
        tree, being inside a Content Sequence that is not cleaned with it.
        """
        depth = len(self._root)
        if path.items[:depth] != self._root:
            return None
        while depth < len(path.items) and path.items[depth][0] == CONTENT_SEQUENCE:
            depth += 1
        holder = path.items[:depth]
        if holder == self._root or holder in self._nodes or self._gone(holder):
            return holder
        return None

    def _references(self) -> tuple[_Reference, ...]:
        """Return each Referenced Content Item Identifier in the tree."""
        found = []
        for path in self._reader.paths():
            if path.tag != REFERENCED_CONTENT_ITEM:
                continue
            holder = self._holder(path)
            if holder is None or self._gone(holder):
                continue
            values = self._reader.numbers(path)
            found.append(_Reference(path, holder, values, self._target(values)))
        return tuple(found)

    def _target(self, values: tuple[int, ...]) -> Item | None:
        """Return the item that a Referenced Content Item Identifier names.

        Its first value names the root, and each other the position, from 1,
        of an item in the Content Sequence of the one before (PS3.3 Section
        C.17.3.2.5).
        """
        if values[0] != 1 or any(value < 1 for value in values):
            return None
        target = (
            *self._root,
            *((CONTENT_SEQUENCE, value - 1) for value in values[1:]),
        )
        if target == self._root or target in self._nodes or self._gone(target):
            return target
        return None

    def _cascade(self, references: tuple[_Reference, ...]) -> set[ElementPath]:
        """Remove what goes with the removed items; return the emptied sequences."""
        emptied: set[ElementPath] = set()
        changed = True
        while changed:
            changed = False
            for reference in references:
                if self._gone(reference.holder) or reference.target is None:
                    continue
                if self._gone(reference.target):
                    if reference.holder == self._root:
                        raise _Unkept
                    self._removed.add(reference.holder)
                    changed = True
            for items in tuple(self._removed):
                if self._modifies(items):
                    self._removed.add(items[:-1])
                    changed = True
            for items, node in self._nodes.items():
                nested = ElementPath(items, CONTENT_SEQUENCE)
                if (
                    not node.children
                    or nested in emptied
                    or self._gone(items)
                    or not all(child in self._removed for child in node.children)
                ):
                    continue
                if node.container:
                    self._removed.add(items)
                else:
                    emptied.add(nested)
                changed = True
        if self._removed and any(
            reference.target is None and not self._gone(reference.holder)
            for reference in references
        ):
            raise _Unkept
        return emptied

    def _modifies(self, items: Item) -> bool:
        """Return whether a removed item takes the item holding it with it.

        That is an item of Relationship Type HAS CONCEPT MOD held by a kept
        item other than a CONTAINER. The root, if it is not a CONTAINER,
        cannot go, so it leaves the whole sequence to take its Basic Profile
        action, raising :class:`_Unkept`.
        """
        holder = items[:-1]
        if holder != self._root and (holder not in self._nodes or self._gone(holder)):
            return False
        if holder == self._root:
            value_type = ElementPath(holder, VALUE_TYPE)
            if (
                value_type in self._reader
                and self._reader.text(value_type) == CONTAINER
            ):
                return False
        elif self._nodes[holder].container:
            return False
        if self._reader.text(ElementPath(items, RELATIONSHIP_TYPE)) != HAS_CONCEPT_MOD:
            return False
        if holder == self._root:
            raise _Unkept
        return True

    def _gone(self, items: Item, strict: bool = False) -> bool:
        """Return whether a removed item is, or holds, the item ``items``."""
        end = len(items) if strict else len(items) + 1
        return any(items[:depth] in self._removed for depth in range(1, end))

    def _renumbered(
        self, references: tuple[_Reference, ...], removed: frozenset[Item]
    ) -> dict[ElementPath, tuple[int, ...]]:
        """Return the new values of each kept identifier whose target moved."""
        if not removed:
            return {}
        numbering = RemovedItems(removed)
        found = {}
        for reference in references:
            if self._gone(reference.holder):
                continue
            assert reference.target is not None  # _cascade raises otherwise
            moved = numbering.output_path(
                ElementPath(reference.target, REFERENCED_CONTENT_ITEM)
            )
            assert moved is not None  # the holder would be removed otherwise
            values = (1, *(index + 1 for _, index in moved.items[len(self._root) :]))
            if values != reference.values:
                found[reference.path] = values
        return found


def _defined(iod: IOD, path: ElementPath) -> bool:
    """Return whether the IOD defines the element at ``path`` at its place."""
    return bool(iod.lookup(path.tag, tuple(tag for tag, _ in path.items)))


def _held(path: ElementPath, sequences: Collection[ElementPath]) -> bool:
    """Return whether one of ``sequences`` holds ``path`` in its items."""
    return any(
        ElementPath(path.items[:depth], tag) in sequences
        for depth, (tag, _) in enumerate(path.items)
    )


@dataclasses.dataclass(frozen=True, eq=False)
class ContentItemPlan(Mapping[ElementPath, str]):
    """What Clean Structured Content does with one instance's content items.

    As a mapping, it gives the action of each element that takes one in
    place of its rule's: ``"K"`` for each content-item sequence that is
    kept, and the action of the value attribute of each content item in it
    whose concept the table or a supplementary row lists.

    Attributes
    ----------
    actions : mapping of ElementPath to str
        The actions that the mapping gives.
    removed_items : frozenset of tuple of (str, int)
        Each item of a kept Content Sequence that is removed on its own,
        with everything in it, by the items tuple of a path that ends with
        it, in the source's numbering (:mod:`.removed_items`).
    emptied : frozenset of ElementPath
        Each nested Content Sequence whose items are all removed, which is
        removed with them, since it is Type 1C.
    renumbered : mapping of ElementPath to tuple of int
        The new values of each kept Referenced Content Item Identifier
        (0040,DB73) whose target an earlier removed item moves.
    """

    actions: Mapping[ElementPath, str] = dataclasses.field(
        default_factory=lambda: types.MappingProxyType({})
    )
    removed_items: frozenset[Item] = frozenset()
    emptied: frozenset[ElementPath] = frozenset()
    renumbered: Mapping[ElementPath, tuple[int, ...]] = dataclasses.field(
        default_factory=lambda: types.MappingProxyType({})
    )

    def __getitem__(self, path: ElementPath) -> str:
        return self.actions[path]

    def __iter__(self) -> Iterator[ElementPath]:
        return iter(self.actions)

    def __len__(self) -> int:
        return len(self.actions)


# No content item is cleaned.
NO_CONTENT_ITEMS = ContentItemPlan()


def content_item_actions(
    source: SourceEvidence, policy: Policy, iod: IOD
) -> ContentItemPlan:
    """Return what the walker does with content items under the option.

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
    ContentItemPlan
        Empty unless the policy selects Clean Structured Content. Otherwise,
        each sequence of :data:`CONTENT_ITEM_SEQUENCES` that is kept gives
        ``"K"``, and the value attribute of each content item in it whose
        concept name Table E.3.4-1 or a supplementary row lists gives the
        action that :func:`concept_action` gives the concept, at each
        place, with the items of a Content Sequence removed on their own,
        the nested Content Sequences emptied, and the identifiers
        renumbered, as :class:`_ContentTree` describes. A sequence that is
        not kept, and everything in it, is left out, so that it takes the
        action that the element rules give it. So is one whose items cannot
        be decoded, or whose character set is not supported. A Content
        Sequence in an item of another is cleaned with the outermost one,
        and is left out with it.
    """
    if CLEAN_STRUCTURED_CONTENT not in policy.options:
        return NO_CONTENT_ITEMS
    candidates = [
        path
        for path in source.paths()
        if path.tag in CONTENT_ITEM_SEQUENCES and _defined(iod, path)
    ]
    found: dict[ElementPath, str] = {}
    removed: set[Item] = set()
    emptied: set[ElementPath] = set()
    renumbered: dict[ElementPath, tuple[int, ...]] = {}
    if candidates:
        sequences = _Sequences(_Reader(source), concept_actions(policy.options), iod)
        held = frozenset(candidates)
        for path in candidates:
            if _held(path, held):
                continue
            try:
                outcome = sequences.outermost(path)
            except (_Unkept, UndecodableElement, IndexError):
                continue
            found.update(outcome.actions)
            removed |= outcome.removed_items
            emptied |= outcome.emptied
            renumbered.update(outcome.renumbered)
    return ContentItemPlan(
        types.MappingProxyType(found),
        frozenset(removed),
        frozenset(emptied),
        types.MappingProxyType(renumbered),
    )
