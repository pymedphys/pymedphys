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
:func:`render_markdown` writes it as CommonMark:

- the PS3.15 edition, the preset, and its options, with their CID 7050
  codes, and the options that are not supported;
- whether the policy can claim conformance, and why not where it cannot;
- the method digest of the policy (D-024) and the vocabulary it covers;
- the supported IODs, their Storage SOP Classes, and the transfer
  syntaxes they are read in (D-010);
- the action that the engine applies to each attribute of Table E.1-1, of
  each supplementary rule, and of each UI attribute that the table omits, by
  its UID role (D-003), with each compound action resolved at every place
  where a supported IOD defines the attribute (D-020), and where the engine
  applies another action than the policy gives, the reason;
- the rules that give every other element its action
  (:mod:`~pymedphys._dicom.deidentify.element_rules`, D-022);
- the values that Z, D, and U write (D-003, D-005, and D-021);
- the scope of referential integrity under a run-scoped key (D-004);
- that no attribute is encrypted for later re-identification (D-013).

What the statement cannot yet describe from the engine is listed in it, under
"Not yet described" (:data:`PENDING`, and the items that apply only to
some policies, such as :data:`PENDING_CLEANING`), and a statement with such
a list makes no conformance claim. A preset is to be enabled only once its statement is
complete. The statement names tags, actions, and the engine's parameters,
never a value from an instance.
"""

from __future__ import annotations

import base64
import dataclasses
import re
import types
from collections.abc import Callable, Iterable, Iterator, Mapping

from pymedphys import _version
from pymedphys._nomenclature import tg263

from . import compound_actions, dummy_values, keys, markers, pseudonyms, uids
from .markers import PROFILE_CODE
from .codes import load_context_group
from .element_rules import (
    _ENGINE_GROUPS,
    _ENGINE_TAGS,
    IOD_DEFINED_VRS,
    KEPT_VRS,
    ElementRules,
    RuleSource,
)
from .iods import load_iod_tables
from .method_digest import digest_inputs, method_digest
from .policy import TARGET_OPTIONS, Policy, PolicyError, ResolvedConflict
from .scope import SUPPORTED_IODS, SUPPORTED_TRANSFER_SYNTAXES, classify
from .sop_classes import load_storage_sop_classes
from .standard import (
    _RESERVED_ODD_GROUPS,
    OPTIONS,
    PRIVATE_ATTRIBUTES_TAG,
    load_data_dictionary,
    load_table_e1_1,
    load_table_e1_1a,
)
from .supplementary_actions import TEXT_VRS, UNCOVERED_TEXT_ACTION
from .uid_registry import load_uid_values
from .uid_roles import UIDRole, load_uid_roles

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

# The action at a place where no action that the compound action offers keeps
# the instance valid, so the instance is sequestered.
SEQUESTER = "sequester"

# Why the engine applies another action than the policy gives an attribute.
ENGINE_REMOVAL = "engine removal"
SEQUENCE_NOT_CLEANED = "sequence not cleaned"

# What each group that the engine removes from a data set holds.
ENGINE_GROUP_REASONS: Mapping[int, str] = types.MappingProxyType(
    {
        0x0000: "the command set of a DIMSE message (PS3.7)",
        0x0002: "the File Meta Information, which the engine writes itself "
        "(PS3.10 Section 7.1)",
        0x0004: "the directory information that belongs only in a DICOMDIR "
        "(PS3.3 Annex F)",
    }
)

# What the statement cannot yet describe from the engine. Each is to be
# generated once the engine decides it.
PENDING = (
    "The action where an IOD requires an attribute to which the policy gives "
    "a plain X or Z (D-020).",
)
# Pending only for a policy whose element rules the engine refuses.
PENDING_REFUSED = (
    "The actions that the engine applies under this policy, which it refuses "
    "until reviewed rules say which private attributes are safe to retain: "
    "the actions above are those that the policy gives, and the rules for "
    "elements that no row covers are not listed."
)
# Pending only for a policy that gives an attribute C.
PENDING_CLEANING = (
    "The manner of cleaning each attribute to which the policy gives C, "
    "including how dates and times are modified and how retained patient "
    "characteristics are cleaned (PS3.15 E.3.5, E.3.6, and E.3.7; D-007, "
    "D-009)."
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
_CLEAN_DESCRIPTORS = "clean_descriptors"

# The attributes that the markers write, and those in their items.
_PATIENT_IDENTITY_REMOVED = "(0012,0062)"
_DEIDENTIFICATION_METHOD = "(0012,0063)"
_DEIDENTIFICATION_METHOD_CODES = "(0012,0064)"
_TEMPORAL_INFORMATION_MODIFIED = "(0028,0303)"
_CONTRIBUTING_EQUIPMENT = "(0018,A001)"
_MANUFACTURER = "(0008,0070)"
_SOFTWARE_VERSIONS = "(0018,1020)"
_PURPOSE_OF_REFERENCE = "(0040,A170)"


@dataclasses.dataclass(frozen=True)
class Place:
    """The action of a compound action at one place in a supported IOD.

    Attributes
    ----------
    iod : str
        The IOD's name, such as ``"RT Plan"``.
    path : tuple of str
        The tags of the sequences that contain the attribute, outermost
        first, or ``()`` at the top level of the data set.
    action : str
        ``"X"``, ``"Z"``, ``"D"``, or ``"U"``, or :data:`SEQUESTER`.
    """

    iod: str
    path: tuple[str, ...]
    action: str


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
        For a compound action, its action at each place where a supported
        IOD defines the attribute, by IOD name and then in the IOD's order;
        otherwise ``()``.
    elsewhere : str
        For a compound action, its action where the IOD does not define the
        attribute, which counts as Type 3; otherwise ``""``.
    policy_action : str
        The action that the policy gives, where the engine applies another
        one as ``action``; otherwise ``""``.
    superseded_by : str
        Why the engine applies ``action`` in place of ``policy_action``:
        :data:`ENGINE_REMOVAL` or :data:`SEQUENCE_NOT_CLEANED`; otherwise
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
        The policy's method digest under the vocabulary given (D-024).
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
    markers : InsertedMarkers
        The parts of the markers that the policy decides.
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
    markers: InsertedMarkers
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


def _places(tag: str, action: str) -> tuple[tuple[Place, ...], str]:
    if action not in compound_actions.COMPOUND_ACTIONS:
        return (), ""
    tables = load_iod_tables()
    # A tag of a repeating group, such as (60xx,0022), is looked up as that of
    # its first group, which every group's definition matches.
    concrete = _REPEATING.sub(r"(\g<1>00,", tag)
    places = []
    for name in sorted(SUPPORTED_IODS):
        iod = tables.iods[name]
        for path in dict.fromkeys(d.path for d in iod.definitions if d.tag == tag):
            try:
                resolved = compound_actions.resolve_in_iod(iod, concrete, path, action)
            except compound_actions.SequesterInstance:
                resolved = SEQUESTER
            places.append(Place(name, path, resolved))
    return tuple(places), compound_actions.resolve(action, "3")


def _attribute(
    tag: str, name: str, rule: str, given: str, rules: ElementRules | None
) -> AttributeAction:
    """Return the action that the engine applies to one listed attribute."""
    # A masked tag is looked up as one of the tags it covers, as for its
    # places; one that stays masked, such as (50xx,xxxx), keeps the policy's
    # action, which its row gives every tag it covers.
    concrete = _REPEATING.sub(r"(\g<1>00,", tag)
    if rules is None or not _CONCRETE_TAG.fullmatch(concrete):
        return AttributeAction(tag, name, rule, given, *_places(tag, given))
    applied = rules.rule(concrete)
    if applied.action == given:
        return AttributeAction(tag, name, rule, given, *_places(tag, given))
    # The engine's own removals come first; otherwise the element rules give
    # a sequence to which the policy gives C its Basic Profile action.
    reason = (
        ENGINE_REMOVAL if applied.source is RuleSource.ENGINE else SEQUENCE_NOT_CLEANED
    )
    places = _places(tag, applied.action)
    return AttributeAction(tag, name, rule, applied.action, *places, given, reason)


def _attributes(policy: Policy, rules: ElementRules | None) -> Iterator[AttributeAction]:
    names = {a.tag: a.name for a in load_data_dictionary().attributes}
    table = load_table_e1_1().attributes
    for row in table:
        yield _attribute(row.tag, row.name, TABLE_E1_1, policy.actions[row.tag], rules)
    for tag, action in policy.supplementary_actions.items():
        yield _attribute(tag, names[tag], SUPPLEMENTARY, action, rules)
    listed = {row.tag for row in table}
    for tag, rule in load_uid_roles().rules.items():
        if tag not in listed:
            role = UID_INSTANCE if rule.role is UIDRole.INSTANCE else UID_DEFINITION
            yield _attribute(tag, names[tag], role, "U", rules)


def _other_elements() -> OtherElements:
    return OtherElements(
        engine_groups=tuple(sorted(_ENGINE_GROUPS)),
        engine_attributes=tuple(sorted(_ENGINE_TAGS)),
        text_vrs=tuple(sorted(TEXT_VRS)),
        text_action=UNCOVERED_TEXT_ACTION,
        kept_vrs=tuple(sorted(KEPT_VRS)),
        iod_defined_vrs=tuple(sorted(IOD_DEFINED_VRS)),
    )


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
    actions = {entry.action for entry in attributes}
    pending = PENDING + tuple(
        item
        for item, applies in (
            (PENDING_REFUSED, rules is None),
            (PENDING_CLEANING, "C" in actions),
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
    digest = method_digest(policy, vocabulary=vocabulary)
    return ConformanceStatement(
        engine_version=_version.__version__,
        edition=policy.edition,
        preset=policy.preset,
        options=policy.options,
        enabled=policy.enabled,
        resolved=policy.resolved,
        method_digest=digest,
        vocabulary_digest=digest_inputs(vocabulary=vocabulary).vocabulary,
        iods=tuple(sorted(SUPPORTED_IODS)),
        sop_classes=supported,
        transfer_syntaxes=syntaxes,
        attributes=attributes,
        other_elements=None if rules is None else _other_elements(),
        markers=_markers(policy, digest),
        pending=pending,
        acknowledgements=tuple(dict.fromkeys(t.acknowledgement for t in tables)),
    )


def _join(values: Iterable[str], conjunction: str = "and") -> str:
    """Join ``values`` as prose: ``"a"``, ``"a and b"``, or ``"a, b, and c"``."""
    values = list(values)
    if len(values) <= 2:
        return f" {conjunction} ".join(values)
    return ", ".join(values[:-1]) + f", {conjunction} " + values[-1]


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _resolution(
    entry: AttributeAction, iods: tuple[str, ...], names: Mapping[str, str]
) -> str:
    """Describe where a compound action resolves to an action other than its
    action elsewhere, naming each enclosing sequence, and naming the IODs only
    where not every supported IOD defines the attribute there."""
    if not entry.elsewhere:
        return ""
    found: dict[str, dict[tuple[str, ...], list[str]]] = {}
    for place in entry.places:
        if place.action != entry.elsewhere:
            found.setdefault(place.action, {}).setdefault(place.path, []).append(
                place.iod
            )
    parts = []
    for action, paths in found.items():
        where = [
            (
                "within " + " > ".join(f"{names[t]} {t}" for t in path)
                if path
                else "at the top level"
            )
            + ("" if tuple(iods_here) == iods else " in " + _join(iods_here))
            for path, iods_here in paths.items()
        ]
        label = "instance sequestered" if action == SEQUESTER else action
        parts.append(f"{label} " + "; ".join(where) + ". ")
    return "".join(parts) + f"{entry.elsewhere} elsewhere"


def _table(header: Iterable[str], rows: Iterable[Iterable[str]]) -> list[str]:
    header = list(header)
    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    for row in rows:
        lines.append("| " + " | ".join(_cell(c) for c in row) + " |")
    return [line.replace("|  |", "| |") for line in lines]


def _code(action: str) -> str:
    return f"`{action}`"


def _claim(
    statement: ConformanceStatement, preset: str, options: str, option
) -> list[str]:
    if statement.claims_conformance:
        return [
            "Output may be described as de-identified in accordance with the "
            f"DICOM PS3.15 {statement.edition} Basic Application Level "
            f"Confidentiality Profile with {options}, for each instance whose "
            "validated result satisfies them (D-011)."
        ]
    lines = [f"This statement makes no PS3.15 conformance claim for {preset}:", ""]
    if not statement.enabled:
        lines.append(
            f"- {preset} is not enabled: its behaviour is not yet implemented "
            "and validated."
        )
    if statement.resolved:
        lines.append(
            "- Its options give these attributes different actions, and it "
            "applies one of them, leaving the other options unmet (D-007):"
        )
        names = {e.tag: e.name for e in statement.attributes}
        for r in statement.resolved:
            applied = [o for o, a in r.conflict.actions.items() if a == r.action]
            lines.append(
                f"  - {r.conflict.tag} {names[r.conflict.tag]}: {_code(r.action)}, as "
                f"{_join(option(o) for o in applied)} requires, by its "
                f"{r.role.value} role; unmet: {_join(option(o) for o in r.unmet)}."
            )
    if statement.pending:
        lines.append("- Parts of the method are not yet described; see below.")
    return lines


def _private(statement: ConformanceStatement) -> list[str]:
    """Describe the removal of private attributes, where the policy removes them."""
    row = next(e for e in statement.attributes if e.tag == PRIVATE_ATTRIBUTES_TAG)
    if row.action != "X":
        return []
    return [
        "",
        "X on Private Attributes removes every element of an odd group at "
        "every level of nesting, in the items of every standard sequence: "
        "each private creator, including one that reserves a block with no "
        "elements; each private data element, whether or not its block has a "
        "creator; and each element in an odd group that PS3.5 Section 7.8.1 "
        "does not allow. A private sequence is removed whole, with its items "
        "(PS3.15 E.1.1 and E.3.10).",
    ]


def _superseded(statement: ConformanceStatement) -> list[str]:
    """Explain each action that the engine applies in place of the policy's."""
    found: dict[tuple[str, str], list[str]] = {}
    for e in statement.attributes:
        if e.superseded_by:
            key = (e.superseded_by, e.policy_action)
            found.setdefault(key, []).append(f"{e.name} {e.tag}")
    lines = []
    for (reason, given), names in sorted(
        found.items(), key=lambda item: item[0][0] != ENGINE_REMOVAL
    ):
        listed = f"to which the policy gives {_code(given)}: {_join(names)}."
        if reason == ENGINE_REMOVAL:
            text = (
                "The engine's own removals, under Other elements, come before "
                f"the policy's actions, so it removes these attributes, {listed}"
            )
        else:
            text = (
                "No rules for cleaning the contents of a sequence are designed "
                "yet, so these sequences take their Basic Profile actions, as "
                f"the table shows, although they are those {listed}"
            )
        lines += ["", text]
    return lines


def _other(statement: ConformanceStatement, named: Callable[[str], str]) -> list[str]:
    """Describe the rules for the elements that no listed rule covers."""
    other = statement.other_elements
    if other is None:
        return []
    groups = "; ".join(
        f"group {group:04X} holds {ENGINE_GROUP_REASONS[group]}"
        for group in other.engine_groups
    )
    reserved = _join(f"{group:04X}" for group in sorted(_RESERVED_ODD_GROUPS))
    resolved = (
        ", resolved by Type at their place as for the rows above"
        if other.text_action in compound_actions.COMPOUND_ACTIONS
        else ""
    )
    return [
        "## Other elements",
        "",
        "Each element takes its action from the first of these that applies: "
        "the engine's own removals; the Private Attributes row, for an "
        f"element of an odd group other than {reserved}, which PS3.5 Section "
        "7.8.1 does not allow for private use; the other rows above; and then "
        "the rules below, by the attribute's VRs in the pinned data "
        "dictionary (D-022).",
        "",
        "- The engine removes from every data set each element of groups "
        f"{_join(f'{group:04X}' for group in other.engine_groups)}, and each "
        "group length, (gggg,0000), which PS3.5 Section 7.2 retires, and "
        f"removes {_join(named(tag) for tag in other.engine_attributes)} "
        f"wherever they are. In a data set, {groups}.",
        f"- Text attributes, of any of the VRs {_join(other.text_vrs, 'or')}, get "
        f"{_code(other.text_action)}{resolved}.",
        f"- Attributes whose VRs are all among {_join(other.kept_vrs)} are kept "
        f"({_code('K')}).",
        "- Attributes whose VRs are all among those and "
        f"{_join(other.iod_defined_vrs)} are kept where the instance's IOD "
        "defines the attribute at the element's place, and removed "
        f"({_code('X')}) elsewhere. The elements in the items of a kept "
        "sequence take their actions by these same rules, as Table E.1-1a "
        "requires of a retained sequence.",
        f"- Any other attribute is removed ({_code('X')}), as is an element "
        "that the pinned data dictionary does not list.",
        "",
    ]


def _inserted(
    statement: ConformanceStatement,
    named: Callable[[str], str],
    coded: Callable[[str], str],
) -> list[str]:
    """Describe the markers that every de-identified instance gains (D-012)."""
    found = statement.markers
    if found.codes:
        codes = (
            "gains an item for each of these codes, with Coding Scheme "
            f"Designator `{markers.DCM}` and its Code Meaning, in this order: "
            f"{_join(coded(c) for c in found.codes)}"
        )
        if found.review_codes:
            codes += (
                ", then "
                f"{_join(coded(c) for c in found.review_codes)} only in an "
                "instance whose retained descriptors have passed pooled human "
                "review, since otherwise the Basic Profile's actions apply to "
                "the descriptors"
            )
        codes += (
            ". A code is not added where an item already present has the same "
            "Code Value and Coding Scheme Designator, and the same Coding "
            "Scheme Version where either has one."
        )
    else:
        codes = (
            "gains no item, since the policy claims no conformance; it is left "
            "out where it would have no item."
        )
    order = _join(f"`{value}`" for value in markers.TEMPORAL_VALUES)
    return [
        "Every de-identified instance gains or updates these attributes, which "
        "record what was done (PS3.15 E.1.1, E.2, and E.3.6; D-012). The values "
        "added depend only on the policy, the method digest, the options that "
        "the instance satisfies, and the versions of the runtime, and never "
        "quote a value from the instance. Any value already present is kept "
        "unless this list says otherwise.",
        "",
        f"- {named(_PATIENT_IDENTITY_REMOVED)}: `YES`, in place of any value "
        "already present.",
        f"- {named(_DEIDENTIFICATION_METHOD)} gains two values: the method "
        f"digest above, then `{found.method}`. It gains neither where that "
        "pair is already present as two consecutive values.",
        f"- {named(_DEIDENTIFICATION_METHOD_CODES)} {codes}",
        f"- {named(_TEMPORAL_INFORMATION_MODIFIED)}: `{found.temporal}`, or "
        f"the value already present where it is stricter, in the order {order}.",
        f"- {named(_CONTRIBUTING_EQUIPMENT)} gains an item, unless an item "
        "already present has the same Manufacturer, Software Versions in the "
        "same order, and purpose of reference. The item's "
        f"{named(_MANUFACTURER)} is `{markers.MANUFACTURER}`. Its "
        f"{named(_SOFTWARE_VERSIONS)} has four values, as the runtime that "
        "ran gives them: PyMedPhys's full version; the Python implementation "
        "and version as one value, such as `CPython 3.14.0`; `pydicom "
        "<version>`; and `tomlkit <version>`. Its "
        f"{named(_PURPOSE_OF_REFERENCE)} has "
        f"{coded(markers.DEIDENTIFYING_EQUIPMENT)}. The method digest does not "
        "cover the runtime, so this item is how an instance records it.",
    ]


def render_markdown(statement: ConformanceStatement) -> str:
    """Write a conformance statement as CommonMark.

    Parameters
    ----------
    statement : ConformanceStatement
        From :func:`conformance_statement`.

    Returns
    -------
    str
        The statement, ending with one newline. The same statement always
        gives the same text.
    """
    meanings = {
        c.code_value: c.code_meaning
        for cid in (7050, 7005)
        for c in load_context_group(cid).rows
        if c.scheme_designator == markers.DCM
    }
    sequences = {a.tag: a.name for a in load_data_dictionary().attributes}

    def named(tag: str) -> str:
        return f"{sequences[tag]} {tag}"

    def coded(code: str) -> str:
        return f"{meanings[code]} (DCM {code})"

    def option(name: str) -> str:
        return coded(OPTION_CODES[name])

    preset = f"`{statement.preset}`" if statement.preset else "a custom option set"
    options = _join(option(o) for o in statement.options) or "no options"
    vocabulary = (
        "without a vocabulary"
        if statement.vocabulary_digest is None
        else "with the vocabulary whose entries have the digest "
        f"`{statement.vocabulary_digest}`"
    )
    bits = keys.KEY_BYTES * 8
    code_length = len(base64.b32encode(bytes(pseudonyms.CODE_BYTES)).rstrip(b"="))
    lines = [
        f"# DICOM PS3.15 conformance statement for {preset}",
        "",
        f"Generated by PyMedPhys {statement.engine_version} from the policy of "
        f"{preset} and the tables of DICOM PS3.15 {statement.edition}. It "
        "names tags, actions, and the engine's parameters, never a value from "
        "an instance.",
        "",
        "## Profile and options",
        "",
        f"- Profile: the DICOM PS3.15 {statement.edition} "
        f"{meanings[PROFILE_CODE]} (DCM {PROFILE_CODE}).",
        f"- Options applied: {options}.",
        "- Options that PyMedPhys can compose into a policy: "
        + _join(option(o) for o in TARGET_OPTIONS)
        + ".",
        "- Options that are not supported: "
        + _join(
            [option(o) for o in OPTIONS if o not in TARGET_OPTIONS]
            + [coded(c) for c in PIXEL_OPTION_CODES]
        )
        + ".",
        "",
        "## Conformance claim",
        "",
        *_claim(statement, preset, options, option),
        "",
        "## Method digest",
        "",
        f"The method digest of {preset}, {vocabulary}, is "
        f"`{statement.method_digest}` (D-024). It identifies the policy and "
        "the PyMedPhys implementation and resources that apply it.",
        "",
        "## Supported instances",
        "",
        f"Instances of the {_join(statement.iods)} IODs, of these Storage SOP "
        "Classes and in these transfer syntaxes, are de-identified. Every "
        "other instance is sequestered: it is not written, and is excluded "
        "from any claim (D-010).",
        "",
        *_table(
            ("SOP Class UID", "SOP Class", "IOD"),
            ((s.uid, s.name, s.iod) for s in statement.sop_classes),
        ),
        "",
        *_table(
            ("Transfer Syntax UID", "Transfer Syntax"),
            ((t.uid, t.name) for t in statement.transfer_syntaxes),
        ),
        "",
        "## Actions",
        "",
        "Each attribute takes the action that Table E.1-1 gives it under the "
        "selected options; an attribute that the table omits takes that of "
        "its supplementary rule (D-022 and D-023), or, for a UI attribute, "
        "U by its UID role (D-003). The actions are those of Table E.1-1a:",
        "",
        *_table(
            ("Action", "Meaning"),
            ((_code(c.code), c.description) for c in load_table_e1_1a().codes),
        ),
        "",
        "A compound action is resolved from the strictest Type that the "
        "instance's IOD gives the attribute at its place in the data set: Type "
        "1 or 1C gives D, 2 or 2C gives Z, and 3 gives X, or else the next of "
        "X, Z, and D that the action offers, and in X/Z/U*, U takes the place "
        "of D. An attribute that the IOD does not define at that place counts "
        "as Type 3 (D-020). The last column gives the resolved action at each "
        "place where a supported IOD defines the attribute, and elsewhere.",
        "",
        *_table(
            ("Tag", "Attribute", "Rule", "Action", "In the supported IODs"),
            (
                (
                    e.tag,
                    e.name,
                    e.rule,
                    _code(e.action)
                    + (f", in place of {_code(e.policy_action)}" * bool(e.policy_action)),
                    _resolution(e, statement.iods, sequences),
                )
                for e in statement.attributes
            ),
        ),
        *_private(statement),
        *_superseded(statement),
        "",
        *_other(statement, named),
        "## Values written",
        "",
        "Z writes a zero-length value, except where this statement says "
        "otherwise. D writes one constant for each VR, "
        "valid for that VR, whatever the source value. Where any source value "
        "equals the first constant, as the VR defines equality, D writes the "
        "second, so the value always changes. It writes the fewest values that "
        "the attribute's VM allows (D-021).",
        "",
        *_table(
            ("VR", "Value", "Value where the source equals the first"),
            (
                (vr, f"`{first}`", f"`{second}`")
                for vr, (first, second) in dummy_values.CONSTANTS.items()
            ),
        ),
        "",
        "D on a UI attribute writes the keyed replacement of each source UID. "
        "D on an attribute of any other VR, such as CS or SQ, needs a reviewed "
        "rule for that attribute; without one, the instance is sequestered "
        "(D-021).",
        "",
        "Patient ID (0010,0020) and Patient's Name (0010,0010) take the "
        "subject's keyed pseudonyms wherever Z or D applies to them (D-005): "
        f"`{pseudonyms.PATIENT_ID_PREFIX}` followed by the subject's code, and "
        f"`{pseudonyms.FAMILY_NAME}^` followed by the same code. The code is "
        f"the {code_length} characters of the base32 form (RFC 4648) of the "
        f"first {pseudonyms.CODE_BYTES * 8} bits of the key's `patient` "
        "derivation of the subject's identity: a Patient ID with its issuer, "
        "or a curated subject identifier.",
        "",
        f"U replaces a UID with `{uids.UID_ROOT}` followed by the decimal form "
        "of a name-based (version 5) UUID, at most 44 characters in all. The "
        f"UUID's namespace is `{uids.UID_NAMESPACE}`, and its name is the "
        "HMAC-SHA256 of the unpadded source UID under the key (D-003). A UID "
        "that the pinned tables of PS3.6 Annex A and PS3.16 register, such as "
        "a well-known frame of reference, is retained, because it names a "
        "public definition rather than an instance; this interprets U for "
        "such values. A replaced value of a UI attribute of the definition "
        "role is also reported.",
        "",
        "No value that Z, D, or U writes names PyMedPhys.",
        "",
        "## Attributes inserted",
        "",
        *_inserted(statement, named, coded),
        "",
        "## Referential integrity",
        "",
        f"Each run has its own {bits}-bit key, from a cryptographically secure "
        "generator, which is discarded after the run (D-004). Replacement UIDs "
        "and patient pseudonyms are each derived from the source as an "
        "HMAC-SHA256 under that key, in a domain of their own. Within a run, "
        "every occurrence of a source UID therefore gets the same replacement, "
        "in every instance, series, study, and patient, including nested "
        "references and the File Meta Information, and every instance of a "
        "subject gets the same pseudonyms. Across runs they are not "
        "consistent: de-identifying the same study in two runs gives unrelated "
        "replacements, and no map from source to replacement values is kept.",
        "",
        "## Encrypted Attributes",
        "",
        "No attribute is placed in an Encrypted Attributes Data Set for later "
        "re-identification: the engine writes no Encrypted Attributes "
        "Sequence (0400,0500), and no other data from which identities could "
        "be recovered (D-013). No transfer syntax therefore encodes such a "
        "data set, and no key is selected to encrypt one. The engine uses no "
        f"public keys; its only key is the run's {bits}-bit key.",
    ]
    if statement.pending:
        lines += ["", "## Not yet described", ""]
        lines += [f"- {item}" for item in statement.pending]
    lines += [
        "",
        "## Acknowledgements",
        "",
        "This statement quotes these parts of the DICOM standard:",
        "",
        *(f"- {a}" for a in statement.acknowledgements),
    ]
    return "\n".join(lines) + "\n"
