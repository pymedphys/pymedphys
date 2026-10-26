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

# pylint: disable = too-many-lines
# One statement describes every option the engine applies, so it is long.

"""Generate the conformance statement of a policy, as PS3.15 E.1.3 requires.

The statement is generated from the policy, the pinned tables, and the
engine's own parameters, never written by hand, so it changes when they
change and the same inputs always give the same text.
:func:`conformance_statement` gathers what it describes, and
:func:`~pymedphys._dicom.deidentify.conformance_markdown.render_markdown`
writes it as CommonMark:

- the PS3.15 edition, the preset, and its options, with their CID 7050
  codes, and the options that are not supported;
- whether the policy can claim conformance, and why not where it cannot;
- the method digest of the policy (D-024), the vocabulary it covers, and
  the absence of the technique vocabulary and of a reviewed-names or
  reviewed descriptors list;
- the supported IODs, their Storage SOP Classes, and the transfer
  syntaxes they are read in (D-010);
- the action that the engine applies to each attribute of Table E.1-1, of
  each supplementary rule, and of each UI attribute that the table omits, by
  its UID role (D-003), with each compound action, and each plain X, Z, and
  D, resolved at every place where a supported IOD defines the attribute,
  other than within a sequence that is removed with its contents (D-020),
  and where the engine applies another action than the policy gives, the
  reason;
- the rules that give every other element its action
  (:mod:`~pymedphys._dicom.deidentify.element_rules`, D-022);
- how the cleaner of each selected option that has one cleans the attributes
  that the policy gives C (:mod:`~pymedphys._dicom.deidentify.cleaners`,
  D-034);
- under the Retain Safe Private Option, the safe private attributes that
  the reviewed rules can retain
  (:mod:`~pymedphys._dicom.deidentify.retained_private`);
- the values that Z, D, and U write (D-003, D-005, and D-021);
- how dates and times are handled, by the policy's Retain Longitudinal
  Temporal Information Option, or without one (D-006, D-007, and D-023);
- the scope of referential integrity under a run-scoped key or a project
  key (D-004);
- that no attribute is encrypted for later re-identification (D-013);
- what the residual search of each written file covers (D-027);
- how the release report names sequestered instances and counts the
  values that the residual search does not search (D-026 and D-027).

What the statement cannot yet describe from the engine is listed in it, under
"Not yet described" (:data:`PENDING`, and the items that apply only to
some policies, such as :data:`PENDING_CLEANING`), and a statement with such
a list makes no conformance claim. A preset is to be enabled only once its statement is
complete. The statement names tags, actions, and the engine's parameters,
never a value from an instance.
"""

from __future__ import annotations

import dataclasses
import re
import types
from collections.abc import Callable, Iterable, Iterator, Mapping

from pymedphys import _version
from pymedphys._nomenclature import tg263

from . import compound_actions, markers, roi_names, tcia_private_tags
from .cleaners import cleaners_for
from .codes import load_context_group
from .content_items import CONTENT_ITEM_SEQUENCES
from .content_items import METHOD as CONTENT_ITEMS_METHOD
from .descriptor_cleaning import fallback_policy
from .dummy_values import (
    DUMMY_VRS,
    ICC_PROFILE,
    PERSON_IDENTIFICATION_CODE_SEQUENCE,
    REFERENCED_PERFORMED_PROCEDURE_STEP_SEQUENCE,
)
from .element_rules import (
    _ENGINE_GROUPS,
    _ENGINE_TAGS,
    IOD_DEFINED_VRS,
    KEPT_VRS,
    ElementRule,
    ElementRules,
    RuleSource,
)
from .iods import IOD, load_iod_tables
from .method_digest import digest_inputs, method_digest
from .policy import (
    CLEAN_RECOGNIZABLE_VISUAL_FEATURES,
    CLEAN_PIXEL_DATA,
    CLEAN_STRUCTURED_CONTENT,
    SAFE_PRIVATE,
    Policy,
    PolicyError,
    ResolvedConflict,
)
from .safe_private import Handling, SafePrivateList, SafePrivateRule
from .scope import SUPPORTED_IODS, SUPPORTED_TRANSFER_SYNTAXES, classify
from .sop_classes import load_storage_sop_classes
from .standard import (
    MUTUALLY_EXCLUSIVE,
    PRIVATE_ATTRIBUTES_TAG,
    dictionary_attribute,
    load_data_dictionary,
    load_table_e1_1,
    load_table_e1_1a,
)
from .supplementary_actions import TEXT_VRS, UNCOVERED_TEXT_ACTION
from .temporal_roles import TemporalRole, load_temporal_roles
from .uid_registry import load_uid_values
from .uid_roles import UIDRole, load_uid_roles
from .walker import DESCENDED

# The CID 7050 code of each option that a policy can compose: those of
# Table E.1-1, then Clean Pixel Data and Clean Recognizable Visual Features,
# which PS3.15 E.1.1 Note 11 leaves out of the table.
OPTION_CODES: Mapping[str, str] = markers.OPTION_CODES

_REPEATING = re.compile(r"^\((50|60)xx,")
_CONCRETE_TAG = re.compile(r"\([0-9A-F]{4},[0-9A-F]{4}\)")

# Where an attribute's action comes from.
TABLE_E1_1 = "Table E.1-1"
SUPPLEMENTARY = "supplementary rule"
UID_INSTANCE = "UID role: instance"
UID_DEFINITION = "UID role: definition"

# The action at a place where the instance is sequestered rather than written.
SEQUESTER = "sequester"
# The attributes whose dummy value a reviewed rule gives, whatever their VR
# (D-021).
_REVIEWED_DUMMY_ATTRIBUTES = frozenset(
    {
        PERSON_IDENTIFICATION_CODE_SEQUENCE,
        REFERENCED_PERFORMED_PROCEDURE_STEP_SEQUENCE,
        ICC_PROFILE,
    }
)
# What a plain X on Overlay Data removes with it: every attribute of its
# overlay group.
OVERLAY_GROUP = "overlay group"
# The plain actions that the Type decides at each place (D-020), and their
# actions where the IOD does not define the attribute.
_PLAIN_ELSEWHERE = types.MappingProxyType({"X": "X", "Z": "Z", "D": "X"})

# Why the engine applies another action than the policy gives an attribute.
ENGINE_REMOVAL = "engine removal"
FILE_META_WRITTEN = "file meta written"
SEQUENCE_NOT_CLEANED = "sequence not cleaned"
# Under Clean Descriptors, an attribute other than ROI Name given C takes the
# action that the policy gives it without that option (D-009).
CLEAN_DESCRIPTORS_FALLBACK = "clean descriptors fallback"
# Under Clean Graphics, a masked row given C, an overlay's or a curve's, takes
# its Basic Profile action (D-041).
GRAPHICS_NOT_CLEANED = "graphics not cleaned"


# What the statement cannot yet describe from the engine, whatever the
# policy. Each is to be generated once the engine decides it; none remains.
PENDING: tuple[str, ...] = ()
# Pending only for a policy that selects an option the engine does not yet
# apply.
PENDING_UNAPPLIED = (
    "The actions that the engine applies under this policy, which it refuses "
    "because it does not yet apply every selected option: the actions above "
    "are those that the policy gives, and the rules for elements that no row "
    "covers are not listed."
)
# Pending only for a policy that gives C to an attribute other than ROI Name
# that neither a cleaner of a selected option (D-034) nor Clean Descriptors'
# fallback (D-009) settles.
PENDING_CLEANING = (
    "The manner of cleaning each attribute other than ROI Name (3006,0026) "
    "to which the policy gives C and which no cleaner above cleans (PS3.15 "
    "Table E.1-1a)."
)
# Pending only for a policy that selects Retain Safe Private and an option
# that the engine does not yet apply, whose element rules it refuses.
PENDING_SAFE_PRIVATE = (
    "The safe private attributes that the policy retains, and the basis on "
    "which each is retained (PS3.15 E.3.10)."
)
_FULL_DATES = "retain_longitudinal_full_dates"
_ROI_NAME = "(3006,0026)"
_CLEAN_DESCRIPTORS = "clean_descriptors"
# The options that an instance satisfies, or not, by its own outcome, whose
# codes are therefore not among those that every instance gains.
_REVIEWED_OPTIONS = (
    _CLEAN_DESCRIPTORS,
    CLEAN_PIXEL_DATA,
    CLEAN_RECOGNIZABLE_VISUAL_FEATURES,
)
# The Retain Longitudinal Temporal Information Options, and the VRs of a date,
# time, or datetime.
_TEMPORAL_OPTIONS = next(o for o in MUTUALLY_EXCLUSIVE if _FULL_DATES in o)
_TEMPORAL_VRS = frozenset({"DA", "DT", "TM"})


@dataclasses.dataclass(frozen=True)
class Place:
    """The action resolved by Type at one place in a supported IOD.

    Attributes
    ----------
    iod : str
        The IOD's name, such as ``"RT Plan"``.
    path : tuple of str
        The tags of the sequences that contain the attribute, outermost
        first, or ``()`` at the top level of the data set.
    action : str
        ``"X"``, ``"Z"``, ``"D"``, or ``"U"``, or :data:`SEQUESTER`.
    removes : str
        For a plain X that removes more than the attribute, the tag of the
        enclosing sequence that it removes with the attribute, or
        :data:`OVERLAY_GROUP`; otherwise ``""``.
    """

    iod: str
    path: tuple[str, ...]
    action: str
    removes: str = ""


@dataclasses.dataclass(frozen=True)
class AttributeAction:
    """The action that the policy gives one attribute.

    Attributes
    ----------
    tag : str
        The tag, as its table gives it, such as ``"(0010,0020)"``.
    name : str
        The attribute's name, as its table gives it.
    rule : str
        Where the action comes from: :data:`TABLE_E1_1`,
        :data:`SUPPLEMENTARY`, :data:`UID_INSTANCE`, or
        :data:`UID_DEFINITION`.
    action : str
        The action code of Table E.1-1a under the policy, such as ``"X/Z/D"``.
    places : tuple of Place
        For a compound action, or a plain X, Z, or D, its action at each
        place where a supported IOD defines the attribute, other than within
        a sequence that is removed with its contents, by IOD name and then
        in the IOD's order; otherwise ``()``.
    elsewhere : str
        For a compound action, or a plain X, Z, or D, its action where the IOD
        does not define the attribute, which counts as Type 3; otherwise ``""``.
    policy_action : str
        The action that the policy gives, where the engine applies another
        one as ``action``; otherwise ``""``.
    superseded_by : str
        Why the engine applies ``action`` in place of ``policy_action``:
        :data:`ENGINE_REMOVAL`, :data:`FILE_META_WRITTEN`, or
        :data:`SEQUENCE_NOT_CLEANED`, :data:`GRAPHICS_NOT_CLEANED`, or
        :data:`CLEAN_DESCRIPTORS_FALLBACK`; otherwise
        ``""``.
    """

    tag: str
    name: str
    rule: str
    action: str
    places: tuple[Place, ...] = ()
    elsewhere: str = ""
    policy_action: str = ""
    superseded_by: str = ""


@dataclasses.dataclass(frozen=True)
class OtherElements:
    """The rules that give an action to each element that no row covers.

    From :mod:`~pymedphys._dicom.deidentify.element_rules` (D-022).

    Attributes
    ----------
    engine_groups : tuple of int
        The groups whose elements the engine removes from a data set.
    engine_attributes : tuple of str
        The tags of the attributes that the engine removes wherever they are.
    text_vrs : tuple of str
        The VRs of a text attribute, which gets ``text_action``.
    text_action : str
        The action of a text attribute that no rule covers.
    kept_vrs : tuple of str
        The VRs whose values are kept wherever they are.
    iod_defined_vrs : tuple of str
        The VRs whose values are kept only where the instance's IOD defines
        the attribute at the element's place.
    """

    engine_groups: tuple[int, ...]
    engine_attributes: tuple[str, ...]
    text_vrs: tuple[str, ...]
    text_action: str
    kept_vrs: tuple[str, ...]
    iod_defined_vrs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class TemporalHandling:
    """How the policy handles dates and times (D-006, D-007, and D-023).

    Attributes
    ----------
    option : str
        The selected Retain Longitudinal Temporal Information Option, or
        ``""`` for none.
    attributes : int
        How many attributes the temporal roles cover: every DA, DT, and TM
        attribute of the pinned data dictionary, and each attribute of
        another VR that Table E.1-1 cleans under Modified Dates.
    other_attributes : tuple of str
        The tags of the attributes of another VR among them, in order.
    actions : tuple of tuple of str and int
        Each action listed for those attributes, with how many have it, most
        first and then in the order of the actions.
    roles : tuple of tuple of str and int
        Each temporal role of those of them that the policy gives C, by its
        name in the roles file, with how many have it, in the order of
        :class:`~pymedphys._dicom.deidentify.temporal_roles.TemporalRole`;
        ``()`` where it gives none C.
    """

    option: str
    attributes: int
    other_attributes: tuple[str, ...]
    actions: tuple[tuple[str, int], ...]
    roles: tuple[tuple[str, int], ...] = ()


@dataclasses.dataclass(frozen=True)
class SOPClass:
    """A Storage SOP Class that is de-identified rather than sequestered."""

    uid: str
    name: str
    iod: str


@dataclasses.dataclass(frozen=True)
class TransferSyntax:
    """A transfer syntax that supported instances are read in."""

    uid: str
    name: str


@dataclasses.dataclass(frozen=True)
class InsertedMarkers:
    """The parts of the markers that the policy decides (D-012).

    Attributes
    ----------
    method : str
        The readable value that De-identification Method (0012,0063) gains
        after the method digest.
    codes : tuple of str
        The CID 7050 Code Values of the items that De-identification Method
        Code Sequence (0012,0064) gains in every instance: the Basic
        Profile's and each selected option's that the policy applies, but
        Clean Descriptors', Clean Pixel Data's, and Clean Recognizable Visual
        Features', or none for a policy that claims no conformance.
    review_codes : tuple of str
        The Code Values that it gains only in an instance that satisfies
        their options, in the policy's order, where the policy can claim
        conformance: Clean Descriptors', where the policy selects it, in an
        instance in which every ROI Name was renamed, was empty, or took a
        reviewer's decision, and whose other attributes given C are removed
        or replaced; Clean Pixel Data's, where the policy selects it, in an
        instance without top-level pixel data or whose blacked-out regions a
        reviewer approved; and Clean Recognizable Visual Features', where the
        policy selects it, in an instance that cannot show a face or whose
        source file the face review found free of one.
    temporal : str
        Longitudinal Temporal Information Modified (0028,0303), unless the
        value already present is stricter.
    """

    method: str
    codes: tuple[str, ...]
    review_codes: tuple[str, ...]
    temporal: str


@dataclasses.dataclass(frozen=True)
class RoiNameCleaning:
    """How ROI Name (3006,0026) is cleaned, where the policy gives it C (D-009).

    Attributes
    ----------
    edition : str or None
        The published edition of the TG-263 Structure Spreadsheet, by its
        worksheet name in
        :data:`~pymedphys._dicom.deidentify.roi_names.PUBLISHED_TG263`,
        whose names ROI Names are renamed to automatically, or None where no
        ROI Name is renamed automatically: without a vocabulary, or with one
        that is not a published edition.
    """

    edition: str | None


@dataclasses.dataclass(frozen=True)
class CleanedAttributes:
    """How the cleaner of a selected option cleans the attributes given C (D-034).

    Under Clean Structured Content, it is how the engine cleans the content
    items of the sequences that the policy gives C (D-047).

    Attributes
    ----------
    option : str
        The option, such as ``"retain_device_identity"``.
    tags : tuple of str
        The attributes that the policy gives C and the cleaner cleans,
        wherever they are in the data set, or, under Clean Structured
        Content, the sequences whose content items are cleaned, in the order
        of their tags.
    method : str
        How the cleaner cleans them, naming no value.
    """

    option: str
    tags: tuple[str, ...]
    method: str


@dataclasses.dataclass(frozen=True)
class ConformanceStatement:
    """What the conformance statement of a policy describes.

    Attributes
    ----------
    engine_version : str
        PyMedPhys's version.
    edition : str
        The edition of PS3.15 whose tables the policy is composed from.
    preset : str or None
        The preset, or None for a custom option set.
    options : tuple of str
        The selected options, in Table E.1-1's order.
    enabled : bool
        Whether the policy is that of an enabled preset.
    resolved : tuple of ResolvedConflict
        The conflicts between options that the preset resolves.
    method_digest : str
        The policy's method digest under the vocabulary given, without the
        technique vocabulary or a reviewed-names or reviewed descriptors
        list (D-024).
    vocabulary_digest : str or None
        The content digest of the vocabulary's entries, or None without one.
    iods, sop_classes, transfer_syntaxes : tuple
        The supported IODs by name, their Storage SOP Classes, and the
        transfer syntaxes they are read in.
    attributes : tuple of AttributeAction
        The rows of Table E.1-1, then the supplementary rules, then the UI
        attributes that the table omits, each in its table's order.
    other_elements : OtherElements or None
        The rules for every other element, or None for a policy whose
        element rules the engine refuses.
    roi_names : RoiNameCleaning or None
        How ROI Names are cleaned, or None where the policy does not give
        ROI Name C.
    cleaned : tuple of CleanedAttributes
        How the cleaner of each selected option that has one cleans the
        attributes that the policy gives C, in the order of the options in
        Table E.1-1.
    safe_private : tuple of SafePrivateRule
        Under the Retain Safe Private Option, the rules of the chosen list
        that can retain a private attribute, other than those for text
        without the Clean Descriptors Option, whose cleaning alone retains
        private text, in their file's order; otherwise ``()``.
    safe_private_list : SafePrivateList or None
        Under the Retain Safe Private Option, the list whose rules settle
        private attributes; otherwise None.
    markers : InsertedMarkers
        The parts of the markers that the policy decides.
    temporal : TemporalHandling
        How the policy handles dates and times.
    pending : tuple of str
        What the statement cannot yet describe.
    acknowledgements : tuple of str
        The attribution of each table the statement quotes.
    project_key : bool
        Whether the run's key is a project key, whose generated values agree
        with every other run under it, rather than a run-scoped key (D-004).
    """

    engine_version: str
    edition: str
    preset: str | None
    options: tuple[str, ...]
    enabled: bool
    resolved: tuple[ResolvedConflict, ...]
    method_digest: str
    vocabulary_digest: str | None
    iods: tuple[str, ...]
    sop_classes: tuple[SOPClass, ...]
    transfer_syntaxes: tuple[TransferSyntax, ...]
    attributes: tuple[AttributeAction, ...]
    other_elements: OtherElements | None
    roi_names: RoiNameCleaning | None
    cleaned: tuple[CleanedAttributes, ...]
    safe_private: tuple[SafePrivateRule, ...]
    safe_private_list: SafePrivateList | None
    markers: InsertedMarkers
    temporal: TemporalHandling
    pending: tuple[str, ...]
    acknowledgements: tuple[str, ...]
    project_key: bool = False

    @property
    def claims_conformance(self) -> bool:
        """Whether output may claim PS3.15 conformance under this statement.

        Only for an enabled preset whose options are all applied and whose
        statement is complete. Each instance's claim still comes from its own
        validated result (D-011).
        """
        return self.enabled and not self.resolved and not self.pending


def _place(iod: IOD, name: str, tag: str, path: tuple[str, ...], action: str) -> Place:
    """Return the action that the Type gives ``action`` at one place."""
    if action in compound_actions.COMPOUND_ACTIONS:
        resolved = compound_actions.resolve_in_iod(iod, tag, path, action)
    elif action != "X":
        resolved = compound_actions.resolve_plain_in_iod(iod, tag, path, action)
    else:
        return _plain_x_place(iod, name, tag, path)
    if resolved == "D" and not _has_dummy_value(tag):
        return Place(name, path, SEQUESTER)
    return Place(name, path, resolved)


def _has_dummy_value(tag: str) -> bool:
    """Whether D can write a dummy value for ``tag`` (D-021).

    It can where the attribute's VR has a generic dummy value or a reviewed
    rule gives the attribute one; otherwise D sequesters the instance.
    """
    if tag in _REVIEWED_DUMMY_ATTRIBUTES:
        return True
    attribute = dictionary_attribute(tag)
    return attribute is None or bool(DUMMY_VRS.intersection(attribute.vrs))


def _plain_x_place(iod: IOD, name: str, tag: str, path: tuple[str, ...]) -> Place:
    """Return what a plain X removes at one place."""
    removal = compound_actions.resolve_plain_x_in_iod(iod, tag, path)
    extent = removal.extent
    if extent is compound_actions.RemovalExtent.SEQUESTER:
        return Place(name, path, SEQUESTER)
    if extent is compound_actions.RemovalExtent.OVERLAY_GROUP:
        return Place(name, path, "X", OVERLAY_GROUP)
    if extent is compound_actions.RemovalExtent.SEQUENCE:
        assert removal.sequence is not None
        return Place(name, path, "X", path[removal.sequence])
    return Place(name, path, "X")


# The action that the applied rules give a sequence at its place in an IOD.
SequenceAction = Callable[[IOD, str, tuple[str, ...]], str]


def _removed_with_a_sequence(
    iod: IOD, path: tuple[str, ...], sequence_action: SequenceAction
) -> bool:
    """Whether a sequence enclosing ``path`` is removed with its contents.

    The walker keeps a sequence as a container only under K or U; under any
    other action, everything in it goes with it, and takes no action of its
    own.
    """
    for depth, sequence in enumerate(path):
        within = path[:depth]
        action = sequence_action(iod, sequence, within)
        if action in compound_actions.COMPOUND_ACTIONS:
            action = compound_actions.resolve_in_iod(iod, sequence, within, action)
        elif action in compound_actions.PLAIN_ACTIONS:
            action = compound_actions.resolve_plain_in_iod(
                iod, sequence, within, action
            )
        if action not in DESCENDED:
            return True
    return False


def _places(
    tag: str, action: str, sequence_action: SequenceAction
) -> tuple[tuple[Place, ...], str]:
    if action in compound_actions.COMPOUND_ACTIONS:
        elsewhere = compound_actions.resolve(action, "3")
    elif action in _PLAIN_ELSEWHERE:
        elsewhere = _PLAIN_ELSEWHERE[action]
    elif tag in compound_actions.LAPSED_CONDITIONS and action == "K":
        # Clinical Trial Protocol Ethics Committee Name, which Retain
        # Institution Identity gives K, is removed wherever it is, as its
        # Type 1C condition never holds in the output (D-020).
        elsewhere = "X"
    else:
        return (), ""
    # A tag of a repeating group, such as (60xx,0022), is looked up as that of
    # its first group, which every group's definition matches. A row that
    # stays masked, such as the Private Attributes row or (50xx,xxxx), has no
    # place in an IOD. A place within a sequence that is removed with its
    # contents is not listed, since the attribute is removed with it.
    concrete = _REPEATING.sub(r"(\g<1>00,", tag)
    if not _CONCRETE_TAG.fullmatch(concrete):
        return (), ""
    tables = load_iod_tables()
    places = []
    for name in sorted(SUPPORTED_IODS):
        iod = tables.iods[name]
        for path in iod.paths(tag):
            if not _removed_with_a_sequence(iod, path, sequence_action):
                places.append(_place(iod, name, concrete, path, action))
    return tuple(places), elsewhere


def _attribute(  # pylint: disable=too-many-arguments
    tag: str,
    name: str,
    rule: str,
    given: str,
    rules: ElementRules | None,
    sequence_action: SequenceAction,
) -> AttributeAction:
    """Return the action that the engine applies to one listed attribute."""
    # A masked tag is looked up as one of the tags it covers, as for its
    # places; one that stays masked, such as (50xx,xxxx), takes the action
    # that the rules give its row, which applies to every tag it covers.
    concrete = _REPEATING.sub(r"(\g<1>00,", tag)
    if rules is not None and given == "C" and tag in CONTENT_ITEM_SEQUENCES:
        # The engine cleans the sequence's content items by their concept
        # names, and gives it its Basic Profile action where it cannot keep
        # them (D-047).
        return AttributeAction(tag, name, rule, given)
    if rules is not None and _CONCRETE_TAG.fullmatch(concrete):
        applied = rules.rule(concrete)
    elif rules is not None and rule == TABLE_E1_1:
        applied = ElementRule(tag, RuleSource.TABLE, rules.row_action(tag), tag)
    else:
        places = _places(tag, given, sequence_action)
        return AttributeAction(tag, name, rule, given, *places)
    if applied.action == given:
        places = _places(tag, given, sequence_action)
        return AttributeAction(tag, name, rule, given, *places)
    places = _places(tag, applied.action, sequence_action)
    return AttributeAction(
        tag, name, rule, applied.action, *places, given, _reason(applied, given)
    )


def _reason(applied: ElementRule, given: str) -> str:
    """Return why the engine applies another action than the policy gives."""
    # The engine's own removals come first, and it writes its own File Meta
    # Information in place of the source's (D-025).
    if applied.source is RuleSource.ENGINE:
        return FILE_META_WRITTEN if applied.tag.startswith("(0002,") else ENGINE_REMOVAL
    # The element rules give a masked row to which the policy gives C, which
    # only Clean Graphics does, its Basic Profile action.
    if given == "C" and applied.source is RuleSource.TABLE and "x" in applied.entry:
        return GRAPHICS_NOT_CLEANED
    # And a sequence to which the policy gives C.
    attribute = dictionary_attribute(applied.tag)
    if (
        given == "C"
        and applied.source is RuleSource.TABLE
        and attribute is not None
        and "SQ" in attribute.vrs
    ):
        return SEQUENCE_NOT_CLEANED
    raise RuntimeError(
        f"the engine gives {applied.tag} {applied.action} rather than the "
        f"policy's {given} for a reason that the statement does not describe"
    )


def _sequence_action(policy: Policy, rules: ElementRules | None) -> SequenceAction:
    """Return the action that the applied rules give a sequence at a place.

    Without element rules, which the engine refuses for some policies, the
    policy's own action applies, U for a UID, and K for any other sequence.
    """
    if rules is not None:
        return lambda iod, tag, path: rules.rule(tag, path, iod=iod).action
    given = {**policy.actions, **policy.supplementary_actions}
    roles = load_uid_roles().rules
    return lambda iod, tag, path: given.get(tag, "U" if tag in roles else "K")


def _attributes(
    policy: Policy, rules: ElementRules | None
) -> Iterator[AttributeAction]:
    names = {a.tag: a.name for a in load_data_dictionary().attributes}
    table = load_table_e1_1().attributes
    sequence_action = _sequence_action(policy, rules)
    for row in table:
        given = policy.actions[row.tag]
        yield _attribute(row.tag, row.name, TABLE_E1_1, given, rules, sequence_action)
    for tag, action in policy.supplementary_actions.items():
        yield _attribute(tag, names[tag], SUPPLEMENTARY, action, rules, sequence_action)
    listed = {row.tag for row in table}
    for tag, rule in load_uid_roles().rules.items():
        if tag not in listed:
            role = UID_INSTANCE if rule.role is UIDRole.INSTANCE else UID_DEFINITION
            yield _attribute(tag, names[tag], role, "U", rules, sequence_action)


def _fallen_back(
    policy: Policy, rules: ElementRules | None, attributes: Iterable[AttributeAction]
) -> Iterator[AttributeAction]:
    """Give each attribute other than ROI Name that keeps C its fallback action.

    Under Clean Descriptors, the engine gives such an attribute the action
    that the policy gives it without that option, at each place, as the
    maintainer decided on 6 October 2026 (D-009). One to which that policy
    also gives C keeps it, as does each attribute of a policy that the engine
    refuses.
    """
    fallback: dict[str, AttributeAction] = {}
    if rules is not None and _CLEAN_DESCRIPTORS in policy.options:
        composed = fallback_policy(policy)
        fallback = {e.tag: e for e in _attributes(composed, ElementRules(composed))}
    for entry in attributes:
        other = fallback.get(entry.tag)
        if (
            entry.action != "C"
            or entry.tag == _ROI_NAME
            or other is None
            or other.action == "C"
        ):
            yield entry
            continue
        yield dataclasses.replace(
            other,
            name=entry.name,
            rule=entry.rule,
            policy_action="C",
            superseded_by=CLEAN_DESCRIPTORS_FALLBACK,
        )


def _other_elements() -> OtherElements:
    return OtherElements(
        engine_groups=tuple(sorted(_ENGINE_GROUPS)),
        engine_attributes=tuple(sorted(_ENGINE_TAGS)),
        text_vrs=tuple(sorted(TEXT_VRS)),
        text_action=UNCOVERED_TEXT_ACTION,
        kept_vrs=tuple(sorted(KEPT_VRS)),
        iod_defined_vrs=tuple(sorted(IOD_DEFINED_VRS)),
    )


def _temporal(
    policy: Policy, attributes: tuple[AttributeAction, ...]
) -> TemporalHandling:
    """Return how the policy handles the attributes that have a temporal role."""
    roles = load_temporal_roles().rules
    actions = {e.tag: e.action for e in attributes}
    counts: dict[str, int] = {}
    for tag in roles:
        counts[actions[tag]] = counts.get(actions[tag], 0) + 1
    others = []
    for tag in roles:
        attribute = dictionary_attribute(tag)
        if attribute is None or not set(attribute.vrs) <= _TEMPORAL_VRS:
            others.append(tag)
    cleaned = [roles[tag].role for tag in roles if actions[tag] == "C"]
    return TemporalHandling(
        option=next((o for o in policy.options if o in _TEMPORAL_OPTIONS), ""),
        attributes=len(roles),
        other_attributes=tuple(sorted(others)),
        actions=tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0]))),
        roles=tuple(
            (role.value, cleaned.count(role))
            for role in TemporalRole
            if role in cleaned
        ),
    )


def _roi_names(
    attributes: Iterable[AttributeAction], vocabulary: tg263.Nomenclature | None
) -> RoiNameCleaning | None:
    """Return how ROI Names are cleaned, where the policy gives ROI Name C."""
    if next(e for e in attributes if e.tag == _ROI_NAME).action != "C":
        return None
    if vocabulary is None:
        return RoiNameCleaning(None)
    try:
        roi_names.RoiNameVocabulary(vocabulary)
    except ValueError:
        # Not a published edition, so the automatic tier renames nothing.
        return RoiNameCleaning(None)
    entries = [dataclasses.asdict(s) for s in vocabulary.structures]
    digest = tg263.content_sha256(entries)
    edition = next(n for n, d in roi_names.PUBLISHED_TG263.items() if d == digest)
    return RoiNameCleaning(edition)


def _safe_private(rules: ElementRules | None) -> tuple[SafePrivateRule, ...]:
    """Return the safe private rules that can retain an attribute.

    Rules for text retain one only under Clean Descriptors, which cleans it.
    """
    if rules is None or rules.safe_private is None:
        return ()
    cleaned = _CLEAN_DESCRIPTORS in rules.policy.options
    return tuple(
        rule
        for rule in rules.safe_private.retained()
        if cleaned or rule.handling is not Handling.TEXT
    )


def _cleaned(
    policy: Policy, attributes: Iterable[AttributeAction]
) -> tuple[CleanedAttributes, ...]:
    """Return how each cleaner of the policy cleans the attributes given C.

    Under Clean Structured Content, the content items of the sequences that
    hold them are cleaned by their concept names (D-047), after the
    cleaners of the options before it in Table E.1-1.
    """
    given_c = {entry.tag for entry in attributes if entry.action == "C"}
    cleaned = [
        CleanedAttributes(
            cleaner.option, tuple(sorted(cleaner.tags & given_c)), cleaner.method
        )
        for cleaner in cleaners_for(policy)
        if cleaner.tags & given_c
    ]
    sequences = given_c & CONTENT_ITEM_SEQUENCES.keys()
    if CLEAN_STRUCTURED_CONTENT in policy.options and sequences:
        cleaned.append(
            CleanedAttributes(
                CLEAN_STRUCTURED_CONTENT, tuple(sorted(sequences)), CONTENT_ITEMS_METHOD
            )
        )
    return tuple(cleaned)


def _markers(policy: Policy, digest: str) -> InsertedMarkers:
    """Return the parts of the markers that the policy decides.

    They are those that :func:`markers.markers_for` gives an instance that
    satisfies every selected option it can without review: all but Clean
    Descriptors, Clean Pixel Data, Clean Recognizable Visual Features, and
    any option that the policy records as unmet.
    """
    unmet = {option for resolution in policy.resolved for option in resolution.unmet}
    satisfied = [
        option
        for option in policy.options
        if option not in _REVIEWED_OPTIONS and option not in unmet
    ]
    found = markers.markers_for(policy, digest, satisfied=satisfied)
    reviewed = [o for o in policy.options if o in _REVIEWED_OPTIONS]
    return InsertedMarkers(
        method=found.method[1],
        codes=tuple(code.code_value for code in found.method_codes),
        review_codes=(
            tuple(OPTION_CODES[o] for o in reviewed)
            if policy.claims_conformance
            else ()
        ),
        temporal=found.temporal_information_modified,
    )


def conformance_statement(
    policy: Policy,
    *,
    vocabulary: tg263.Nomenclature | None,
    safe_private_list: SafePrivateList = SafePrivateList.REVIEWED,
    project_key: bool = False,
) -> ConformanceStatement:
    """Gather what the conformance statement of a policy describes.

    Parameters
    ----------
    policy : Policy
        A validated policy, such as one from
        :func:`~pymedphys._dicom.deidentify.policy.compose_policy`.
    vocabulary : ~pymedphys._nomenclature.tg263.Nomenclature or None
        The TG-263 vocabulary of the run, or None without one, which gives
        the published baseline digest of a preset (D-024). It must be given
        by name, as for
        :func:`~pymedphys._dicom.deidentify.method_digest.method_digest`.
        The digest is always computed without a reviewed-names list or a
        reviewed descriptors list, which are a site's confidential
        resources, and without the technique vocabulary, as D-024's
        published baseline is, and the statement says so.
    safe_private_list : SafePrivateList, optional
        Under the Retain Safe Private Option, the list whose rules settle
        private attributes: the reviewed rules, the default, or TCIA's
        Private Tag Dictionary. The digest is computed with it.
    project_key : bool, optional
        Whether the run's key is a project key, whose subject profiles it
        reads and records, rather than a run-scoped key, the default
        (D-004). The statement describes referential integrity, and how far
        generated values agree, for that scope.

    Returns
    -------
    ConformanceStatement

    Raises
    ------
    TypeError
        If ``policy`` is not a Policy, ``safe_private_list`` is not a
        SafePrivateList, or for any reason
        :func:`~pymedphys._dicom.deidentify.method_digest.method_digest`
        gives.
    ValueError
        If the policy was not composed from the pinned Table E.1-1, such as
        one composed from an altered table, or ``safe_private_list`` chooses
        TCIA's dictionary for a policy without the Retain Safe Private
        Option.
    MarkerError
        If the markers cannot be written as valid values, as
        :func:`~pymedphys._dicom.deidentify.markers.markers_for` refuses
        them, such as for a PyMedPhys version too long for the readable
        De-identification Method value. The engine would refuse them too.
    """
    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    if not isinstance(safe_private_list, SafePrivateList):
        raise TypeError("safe_private_list must be a SafePrivateList")
    if SAFE_PRIVATE not in policy.options and (
        safe_private_list is not SafePrivateList.REVIEWED
    ):
        raise ValueError(
            "a safe private list can be chosen only under the Retain Safe "
            "Private Option"
        )
    table = load_table_e1_1()
    if policy.edition != table.edition or list(policy.actions) != [
        row.tag for row in table.attributes
    ]:
        raise ValueError(
            "the policy was not composed from the pinned Table E.1-1, whose "
            "attributes the statement lists"
        )
    sop_classes = load_storage_sop_classes()
    supported = tuple(
        SOPClass(row.uid, row.name, row.iod_name)
        for row in sop_classes.rows
        if not any(
            classify(row.uid, syntax, sop_classes).sequestered
            for syntax in SUPPORTED_TRANSFER_SYNTAXES
        )
    )
    registered = load_uid_values()
    syntaxes = tuple(
        TransferSyntax(row.uid, row.name)
        for row in registered.rows
        if row.uid in SUPPORTED_TRANSFER_SYNTAXES
    )
    try:
        rules: ElementRules | None = ElementRules(
            policy, safe_private_list=safe_private_list
        )
    except PolicyError:
        rules = None
    attributes = tuple(_fallen_back(policy, rules, _attributes(policy, rules)))
    safe_private = SAFE_PRIVATE in policy.options
    cleaned = _cleaned(policy, attributes)
    # The safe private rules settle the C of private attributes.
    by_cleaner = {tag for each in cleaned for tag in each.tags} | (
        {PRIVATE_ATTRIBUTES_TAG} if rules is not None and safe_private else set()
    )
    actions = {
        entry.action
        for entry in attributes
        if entry.tag != _ROI_NAME and entry.tag not in by_cleaner
    }
    pending = PENDING + tuple(
        item
        for item, applies in (
            (PENDING_UNAPPLIED, rules is None),
            (PENDING_CLEANING, "C" in actions),
            (PENDING_SAFE_PRIVATE, rules is None and safe_private),
        )
        if applies
    )
    tables = (
        table,
        load_table_e1_1a(),
        load_iod_tables(),
        sop_classes,
        load_data_dictionary(),
        registered,
        load_context_group(7050),
        load_context_group(7005),
    )
    # A statement describes a policy, never a site's reviewed lists, and
    # gives D-024's baseline, without the technique vocabulary.
    digest = method_digest(
        policy,
        vocabulary=vocabulary,
        reviewed_roi_names=None,
        safe_private_list=safe_private_list,
    )
    return ConformanceStatement(
        engine_version=_version.__version__,
        edition=policy.edition,
        preset=policy.preset,
        options=policy.options,
        enabled=policy.enabled,
        resolved=policy.resolved,
        method_digest=digest,
        vocabulary_digest=digest_inputs(
            vocabulary=vocabulary, reviewed_roi_names=None
        ).vocabulary,
        iods=tuple(sorted(SUPPORTED_IODS)),
        sop_classes=supported,
        transfer_syntaxes=syntaxes,
        attributes=attributes,
        other_elements=None if rules is None else _other_elements(),
        roi_names=_roi_names(attributes, vocabulary),
        cleaned=cleaned,
        safe_private=_safe_private(rules),
        safe_private_list=None if rules is None else rules.safe_private_list,
        markers=_markers(policy, digest),
        temporal=_temporal(policy, attributes),
        pending=pending,
        acknowledgements=tuple(dict.fromkeys(t.acknowledgement for t in tables))
        + (
            (tcia_private_tags.ACKNOWLEDGEMENT,)
            if rules is not None and rules.safe_private_list is SafePrivateList.TCIA
            else ()
        ),
        project_key=project_key,
    )
