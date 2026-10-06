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
  the absence of a reviewed-names list;
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
- the values that Z, D, and U write (D-003, D-005, and D-021);
- how dates and times are handled, by the policy's Retain Longitudinal
  Temporal Information Option, or without one (D-006, D-007, and D-023);
- the scope of referential integrity under a run-scoped key (D-004);
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

from . import compound_actions, markers, roi_names
from .codes import load_context_group
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
from .policy import Policy, PolicyError, ResolvedConflict
from .scope import SUPPORTED_IODS, SUPPORTED_TRANSFER_SYNTAXES, classify
from .sop_classes import load_storage_sop_classes
from .standard import (
    MUTUALLY_EXCLUSIVE,
    dictionary_attribute,
    load_data_dictionary,
    load_table_e1_1,
    load_table_e1_1a,
)
from .supplementary_actions import TEXT_VRS, UNCOVERED_TEXT_ACTION
from .temporal_roles import load_temporal_roles
from .uid_registry import load_uid_values
from .uid_roles import UIDRole, load_uid_roles
from .walker import DESCENDED

# The CID 7050 code of each option of Table E.1-1: those of the supported
# options from the markers, and those of the others, which the statement
# names as not supported.
OPTION_CODES: Mapping[str, str] = types.MappingProxyType(
    {
        **markers.OPTION_CODES,
        "retain_uids": "113110",
        "retain_institution_identity": "113112",
        "retain_longitudinal_full_dates": "113106",
        "clean_structured_content": "113104",
        "clean_graphics": "113103",
    }
)

# The CID 7050 codes of Clean Pixel Data and Clean Recognizable Visual
# Features, which PS3.15 E.1.1 Note 11 leaves out of Table E.1-1. Neither is
# supported, and the statement names both as not supported.
PIXEL_OPTION_CODES: tuple[str, ...] = ("113101", "113102")

_REPEATING = re.compile(r"^\((50|60)xx,")
_CONCRETE_TAG = re.compile(r"\([0-9A-F]{4},[0-9A-F]{4}\)")

# Where an attribute's action comes from.
TABLE_E1_1 = "Table E.1-1"
SUPPLEMENTARY = "supplementary rule"
UID_INSTANCE = "UID role: instance"
UID_DEFINITION = "UID role: definition"

# The action at a place where the instance is sequestered rather than written.
SEQUESTER = "sequester"
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


# What the statement cannot yet describe from the engine. Each is to be
# generated once the engine decides it.
PENDING: tuple[str, ...] = (
    "What the engine does not yet do for each run's release report and "
    "residual search: write the release report with each run; search each "
    "written file; record the "
    "values that it does not give the residual search, for the reasons "
    "listed under Release report (D-027); act on the search's findings, by "
    "sequestering an instance whose written file fails the search and "
    "moving output from a staging area to the release directory only after "
    "a clean search (D-027); and write the confidential QC pack, which maps "
    "each label to its source instance and lists each value not searched by "
    "instance and place (D-016, D-026, and D-027). The report cannot yet "
    "record an instance that the run itself sequesters, such as one whose "
    "file changes during the run, or that a gate sequesters, since neither "
    "is one of the stages listed under Release report.",
)
PENDING_RELEASE_REPORT = PENDING[0]
# Pending only for a policy whose element rules the engine refuses.
PENDING_REFUSED = (
    "The actions that the engine applies under this policy, which it refuses "
    "until reviewed rules say which private attributes are safe to retain: "
    "the actions above are those that the policy gives, and the rules for "
    "elements that no row covers are not listed."
)
# Pending only for a policy that gives an attribute C.
PENDING_CLEANING = (
    "The manner of cleaning each attribute other than ROI Name (3006,0026) "
    "to which the policy gives C, including how dates and times are modified "
    "and how retained patient characteristics are cleaned (PS3.15 E.3.5, "
    "E.3.6, and E.3.7; D-007, D-009)."
)
# Pending only for a policy that gives ROI Name C.
PENDING_ROI_NAMES = (
    "Cleaning each ROI Name (3006,0026) in a run as the section Cleaning "
    "ROI names describes: no run yet writes the cleaned names, holds an instance in the "
    "staging area, or empties held names where it is told to (D-009)."
)
# Pending only for a policy that selects Retain Safe Private.
PENDING_SAFE_PRIVATE = (
    "The safe private attributes that the policy retains, and the basis on "
    "which each is retained (PS3.15 E.3.10)."
)
# Pending only for tps-import, whose Z writes a synthetic birth date.
PENDING_BIRTH_DATES = (
    "The synthetic birth date that Z writes to Patient's Birth Date "
    "(0010,0030) in place of a zero-length value (D-008, D-021)."
)
_TPS_IMPORT = "tps-import"
_FULL_DATES = "retain_longitudinal_full_dates"
_ROI_NAME = "(3006,0026)"
_CLEAN_DESCRIPTORS = "clean_descriptors"
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
        :data:`SEQUENCE_NOT_CLEANED`; otherwise
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
    """

    option: str
    attributes: int
    other_attributes: tuple[str, ...]
    actions: tuple[tuple[str, int], ...]


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
        Profile's and each selected option's that the policy applies, or none
        for a policy that claims no conformance.
    review_codes : tuple of str
        The Code Values that it gains only in an instance whose retained
        descriptors have passed pooled human review: Clean Descriptors',
        where the policy selects it and can claim conformance.
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
        The policy's method digest under the vocabulary given, without a
        reviewed-names list (D-024).
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
    markers : InsertedMarkers
        The parts of the markers that the policy decides.
    temporal : TemporalHandling
        How the policy handles dates and times.
    pending : tuple of str
        What the statement cannot yet describe.
    acknowledgements : tuple of str
        The attribution of each table the statement quotes.
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
    markers: InsertedMarkers
    temporal: TemporalHandling
    pending: tuple[str, ...]
    acknowledgements: tuple[str, ...]

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
        return Place(
            name, path, compound_actions.resolve_in_iod(iod, tag, path, action)
        )
    if action != "X":
        return Place(
            name, path, compound_actions.resolve_plain_in_iod(iod, tag, path, action)
        )
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
        for path in dict.fromkeys(d.path for d in iod.definitions if d.tag == tag):
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
    # places; one that stays masked, such as (50xx,xxxx), keeps the policy's
    # action, which its row gives every tag it covers.
    concrete = _REPEATING.sub(r"(\g<1>00,", tag)
    if rules is None or not _CONCRETE_TAG.fullmatch(concrete):
        places = _places(tag, given, sequence_action)
        return AttributeAction(tag, name, rule, given, *places)
    applied = rules.rule(concrete)
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
    # The element rules give a sequence to which the policy gives C its Basic
    # Profile action.
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
    return TemporalHandling(
        option=next((o for o in policy.options if o in _TEMPORAL_OPTIONS), ""),
        attributes=len(roles),
        other_attributes=tuple(sorted(others)),
        actions=tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0]))),
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


def _markers(policy: Policy, digest: str) -> InsertedMarkers:
    """Return the parts of the markers that the policy decides.

    They are those that :func:`markers.markers_for` gives an instance that
    satisfies every selected option it can without review: all but Clean
    Descriptors and any option that the policy records as unmet.
    """
    unmet = {option for resolution in policy.resolved for option in resolution.unmet}
    satisfied = [
        option
        for option in policy.options
        if option != _CLEAN_DESCRIPTORS and option not in unmet
    ]
    found = markers.markers_for(policy, digest, satisfied=satisfied)
    review = policy.claims_conformance and _CLEAN_DESCRIPTORS in policy.options
    return InsertedMarkers(
        method=found.method[1],
        codes=tuple(code.code_value for code in found.method_codes),
        review_codes=(OPTION_CODES[_CLEAN_DESCRIPTORS],) if review else (),
        temporal=found.temporal_information_modified,
    )


def conformance_statement(
    policy: Policy, *, vocabulary: tg263.Nomenclature | None
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
        The digest is always computed without a reviewed-names list, which
        is a site's confidential resource, and the statement says so.

    Returns
    -------
    ConformanceStatement

    Raises
    ------
    TypeError
        If ``policy`` is not a Policy, or for any reason
        :func:`~pymedphys._dicom.deidentify.method_digest.method_digest`
        gives.
    ValueError
        If the policy was not composed from the pinned Table E.1-1, such as
        one composed from an altered table.
    MarkerError
        If the markers cannot be written as valid values, as
        :func:`~pymedphys._dicom.deidentify.markers.markers_for` refuses
        them, such as for a PyMedPhys version too long for the readable
        De-identification Method value. The engine would refuse them too.
    """
    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
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
        rules: ElementRules | None = ElementRules(policy)
    except PolicyError:
        rules = None
    attributes = tuple(_attributes(policy, rules))
    actions = {entry.action for entry in attributes if entry.tag != _ROI_NAME}
    roi_name_actions = {e.action for e in attributes if e.tag == _ROI_NAME}
    pending = PENDING + tuple(
        item
        for item, applies in (
            (PENDING_REFUSED, rules is None),
            (PENDING_CLEANING, "C" in actions),
            (PENDING_ROI_NAMES, "C" in roi_name_actions),
            (PENDING_SAFE_PRIVATE, "retain_safe_private" in policy.options),
            (PENDING_BIRTH_DATES, policy.preset == _TPS_IMPORT),
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
    # A statement describes a policy, never a site's reviewed-names list.
    digest = method_digest(policy, vocabulary=vocabulary, reviewed_roi_names=None)
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
        markers=_markers(policy, digest),
        temporal=_temporal(policy, attributes),
        pending=pending,
        acknowledgements=tuple(dict.fromkeys(t.acknowledgement for t in tables)),
    )
