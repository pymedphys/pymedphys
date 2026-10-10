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

"""Write the conformance statement of a policy as CommonMark.

:func:`render_markdown` writes a
:class:`~pymedphys._dicom.deidentify.conformance.ConformanceStatement`,
which :func:`~pymedphys._dicom.deidentify.conformance.conformance_statement`
gathers, as the sections that PS3.15 E.1.3 requires, in a fixed order. The
same statement always gives the same text, which names tags, actions, and
the engine's parameters, never a value from an instance.
"""

from __future__ import annotations

import types
from collections.abc import Callable, Iterable, Mapping

from . import compound_actions, conformance_values, keys, markers
from .codes import load_context_group
from .conformance import (
    CLEAN_DESCRIPTORS_FALLBACK,
    ENGINE_REMOVAL,
    FILE_META_WRITTEN,
    OPTION_CODES,
    OVERLAY_GROUP,
    PIXEL_OPTION_CODES,
    SEQUENCE_NOT_CLEANED,
    SEQUESTER,
    AttributeAction,
    ConformanceStatement,
)
from .conformance_values import code as _code
from .conformance_values import join as _join
from .markers import PROFILE_CODE
from .policy import TARGET_OPTIONS
from .reviewed_roi_names import Outcome, Review
from .roi_names import Reason
from .source import ENCAPSULATED_TRANSFER_SYNTAXES
from .standard import (
    _RESERVED_ODD_GROUPS,
    OPTIONS,
    PRIVATE_ATTRIBUTES_TAG,
    load_data_dictionary,
    load_table_e1_1a,
)
from .supplementary_actions import load_supplementary_actions

_ROI_NAME_NAMED = "ROI Name (3006,0026)"
# Why the automatic tier sends a ROI Name to review rather than renaming it.
ROI_REVIEW_REASONS: Mapping[Reason, str] = types.MappingProxyType(
    {
        Reason.UNMATCHED: "it matches no vocabulary name, including where it "
        "holds a character outside printable ASCII, or starts with `_` or `-` "
        "once its padding is removed, since TG-263 marks a structure not used "
        "for dose evaluation with a leading `_`, so `_Heart` is not `Heart`",
        Reason.AMBIGUOUS: "it matches more than one vocabulary name",
        Reason.ECHOES_IDENTIFIER: "it, or the vocabulary name it would take, "
        "echoes a known patient or other person identifier of the instance: a "
        "word of more than one character is a word of the identifier, or the "
        "whole name equals the whole identifier, once case and characters "
        "that are not letters or digits are disregarded",
        Reason.WOULD_DUPLICATE: "another, differently spelt ROI Name of the "
        "same structure set would be written as the same name",
    }
)
# What is written for a ROI Name after both tiers.
ROI_OUTCOMES: Mapping[Outcome, str] = types.MappingProxyType(
    {
        Outcome.RENAMED: "the vocabulary's spelling, where the automatic tier "
        "renames the name",
        Outcome.EMPTY: "an empty value, where the name is empty once its "
        "padding is removed",
        Outcome.KEPT: "the name as it is, where a reviewer kept it",
        Outcome.MAPPED: "the reviewer's name, where a reviewer mapped it",
        Outcome.EMPTIED: "an empty value, where a reviewer had it emptied",
        Outcome.HELD: "an empty value, where the name is held, in a file "
        "that is not released: unless the run or the release gate sequesters "
        "it, the run holds its instance for review, deletes the file from the "
        "staging area, and the release report counts the instance as held for "
        "review, and a later run writes it once a reviewer has decided",
        Outcome.EMPTIED_UNREVIEWED: "an empty value, where the name is held "
        "and the run's descriptor cleaning is set to empty held names, in an "
        "instance that may then be released without the Clean Descriptors "
        "code",
    }
)

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

# The attributes that the markers write, and those in their items.
_PATIENT_IDENTITY_REMOVED = "(0012,0062)"
_DEIDENTIFICATION_METHOD = "(0012,0063)"
_DEIDENTIFICATION_METHOD_CODES = "(0012,0064)"
_TEMPORAL_INFORMATION_MODIFIED = "(0028,0303)"
_CONTRIBUTING_EQUIPMENT = "(0018,A001)"
_MANUFACTURER = "(0008,0070)"
_SOFTWARE_VERSIONS = "(0018,1020)"
_PURPOSE_OF_REFERENCE = "(0040,A170)"


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _where(
    path: tuple[str, ...],
    named: bool,
    iods_here: list[str],
    iods: tuple[str, ...],
    names: Mapping[str, str],
) -> str:
    """Describe the places at ``path``, naming the IODs unless all define it.

    Where the label already names the place's own enclosing sequence, the
    rest of the path is named, or nothing at the top level.
    """
    if path:
        within = "within " + " > ".join(f"{names[t]} {t}" for t in path)
    else:
        within = "" if named else "at the top level"
    where = "" if tuple(iods_here) == iods else "in " + _join(iods_here)
    return " ".join(text for text in (within, where) if text)


def _resolution(
    entry: AttributeAction, iods: tuple[str, ...], names: Mapping[str, str]
) -> str:
    """Describe where an action resolves by Type to another than its action
    elsewhere, or a plain X removes more than the attribute, naming each
    enclosing sequence, and naming the IODs only where not every supported
    IOD defines the attribute there."""
    if not entry.elsewhere:
        return ""
    # Each label's places, by the sequences named as where it applies, and
    # whether the place's own enclosing sequence is named by the label.
    found: dict[str, dict[tuple[tuple[str, ...], bool], list[str]]] = {}
    for place in entry.places:
        path, named = place.path, False
        if place.action == SEQUESTER:
            label = "instance sequestered"
        elif place.removes == OVERLAY_GROUP:
            label = f"{place.action} with its overlay group"
        elif place.removes:
            label = (
                f"{place.action} with the enclosing {names[place.removes]} "
                f"{place.removes}"
            )
            named = place.removes == path[-1]
            path = path[:-1] if named else path
        elif place.action != entry.elsewhere:
            label = place.action
        else:
            continue
        found.setdefault(label, {}).setdefault((path, named), []).append(place.iod)
    parts = []
    for label, paths in found.items():
        where = [
            _where(path, named, iods_here, iods, names)
            for (path, named), iods_here in paths.items()
        ]
        parts.append(" ".join((label, "; ".join(where))).strip() + ". ")
    return "".join(parts) + f"{entry.elsewhere} elsewhere."


def _table(header: Iterable[str], rows: Iterable[Iterable[str]]) -> list[str]:
    header = list(header)
    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    for row in rows:
        lines.append("| " + " | ".join(_cell(c) for c in row) + " |")
    return [line.replace("|  |", "| |") for line in lines]


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
        *(
            [
                "",
                "Private Data Element Characteristics Sequence (0008,0300), which "
                "describes the private blocks by their private creators, is "
                "removed by its supplementary rule, so no private creator of a "
                "removed block survives in its items.",
            ]
            if _rule_action(_PRIVATE_CHARACTERISTICS) != "K"
            else []
        ),
    ]


_PRIVATE_CHARACTERISTICS = "(0008,0300)"
# Code Value, Coding Scheme Designator, and Code Meaning.
_CODE_TAGS = ("(0008,0100)", "(0008,0102)", "(0008,0104)")
_CODING_SCHEME_URL = "(0008,010E)"


def _rule_action(tag: str) -> str | None:
    """Return the Basic Profile action of an attribute's supplementary rule."""
    rule = load_supplementary_actions().rules.get(tag)
    return None if rule is None else rule.action


def _local_codes(named: Callable[[str], str]) -> list[str]:
    """Say which kept values can name an institution, and who accepts that."""
    if any(_rule_action(tag) != "K" for tag in _CODE_TAGS):
        return []
    url = (
        f", and such a scheme's {named(_CODING_SCHEME_URL)}, also kept, can name "
        "the institution's host"
        if _rule_action(_CODING_SCHEME_URL) == "K"
        else ""
    )
    manufacturer = (
        [
            f"{named(_MANUFACTURER)} is kept ({_code('K')}) too, since it names "
            "the maker of a product that many sites share, but a device made "
            "in-house can carry the institution's name as its Manufacturer "
            "(D-022). "
        ]
        if _rule_action(_MANUFACTURER) == "K"
        else []
    )
    return [
        "## Values that can name an institution",
        "",
        f"{_join(named(tag) for tag in _CODE_TAGS)} are kept ({_code('K')}) by "
        "their supplementary rules, whatever the coding scheme, so that coded "
        "meaning survives (D-022). A code of a local coding scheme, whose "
        'Coding Scheme Designator begins with "99" or is "L" (PS3.3 Section '
        "8.2), can carry the institution's name or abbreviation in those "
        f"values{url}. "
        + "".join(manufacturer)
        + "Each such value, like every other string that the engine keeps, is "
        "listed among the retained strings of the run's confidential QC pack, "
        "where a reviewer can find it (D-017).",
        "",
        "The engine does not itself assess the residual risk of these values. "
        "The design accepts it for Manufacturer and Coding Scheme URL because "
        "such a value names an institution, not a patient, and for the codes "
        "of local coding schemes requires this disclosure (D-022). The "
        "`public-release` preset has a person review every distinct retained "
        "string (D-017); the other presets keep these values without review. "
        "For the first release, the residual risk of the output, these values "
        "included, is for whoever releases the data to accept, which they may "
        "confirm, yes or no, in the attestation of the run's QC pack, under "
        "the institution's governance (D-016).",
        "",
    ]


def _superseded(statement: ConformanceStatement) -> list[str]:
    """Explain each action that the engine applies in place of the policy's."""
    found: dict[tuple[str, str], list[str]] = {}
    for e in statement.attributes:
        if e.superseded_by:
            key = (e.superseded_by, e.policy_action)
            found.setdefault(key, []).append(f"{e.name} {e.tag}")
    order = (ENGINE_REMOVAL, FILE_META_WRITTEN, SEQUENCE_NOT_CLEANED)
    lines = []
    for (reason, given), names in sorted(
        found.items(),
        key=lambda item: order.index(item[0][0]) if item[0][0] in order else 2,
    ):
        listed = f"to which the policy gives {_code(given)}: {_join(names)}."
        if reason == ENGINE_REMOVAL:
            text = (
                "The engine's own removals, under Other elements, come before "
                f"the policy's actions, so it removes these attributes, {listed}"
            )
        elif reason == FILE_META_WRITTEN:
            text = (
                "The engine writes its own File Meta Information in place of "
                "the source's, as PS3.15 E.1.1 requires, so it removes the "
                f"source's File Meta Information, including these attributes, "
                f"{listed} The File Meta Information it writes holds only "
                "File Meta Information Group Length (0002,0000), File Meta "
                "Information Version (0002,0001), Media Storage SOP Class UID "
                "(0002,0002), which is the instance's SOP Class UID, Media "
                "Storage SOP Instance UID (0002,0003), which is the instance's "
                "replacement SOP Instance UID, Transfer Syntax UID (0002,0010), "
                "and PyMedPhys's Implementation Class UID (0002,0012) and "
                "Implementation Version Name (0002,0013) (D-025)."
            )
        elif reason == CLEAN_DESCRIPTORS_FALLBACK:
            text = (
                f"Under Clean Descriptors, each attribute other than "
                f"{_ROI_NAME_NAMED} to which the policy gives {_code(given)} "
                "takes the action that the policy gives it without Clean "
                "Descriptors, at each place, which the maintainer decided on "
                "6 October 2026 (D-009); the table gives that action for each "
                f"of these {len(names)} attributes. Where that action removes "
                "or replaces the attribute, the instance still meets the "
                "option, since PS3.15 E.3.5 specifies what the option removes, "
                "and Table E.1-1 gives the minimum actions; where it keeps the "
                "attribute, the instance does not gain the option's code, as "
                "Attributes inserted describes."
            )
        else:
            text = (
                "No rules for cleaning the contents of a sequence are designed "
                f"yet, so each sequence to which the policy gives {_code(given)} "
                "takes its Basic Profile action, as the table shows: "
                f"{_join(names)}."
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
        "the engine's own removals (D-013, D-016, and D-025); the Private "
        f"Attributes row, for an element of an odd group other than {reserved}, "
        "which PS3.5 Section 7.8.1 does not allow for private use; the other "
        "rows of Table E.1-1, by exact tag and then by masked tag, where "
        "(50xx,eeee) and (60xx,eeee) match only the repeating groups 5000 to "
        "501E and 6000 to 601E (PS3.5 Section 7.6); the supplementary rules; "
        "U by the role of a UI attribute; and then the rules below, by the "
        "attribute's VRs in the pinned data dictionary (D-022).",
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
        "sequence take their actions by the rules of this statement, as Table E.1-1a "
        "requires of a retained sequence.",
        f"- Any other attribute is removed ({_code('X')}), as is an element "
        "that the pinned data dictionary does not list.",
        "",
    ]


def _roi_names(statement: ConformanceStatement) -> list[str]:
    """Describe how ROI Names are cleaned, where the policy gives ROI Name C."""
    cleaning = statement.roi_names
    if cleaning is None:
        return []
    if cleaning.edition is not None:
        automatic = (
            "The vocabulary is the published edition of the TG-263 "
            f"Structure Spreadsheet `{cleaning.edition}`, whose entries have "
            f"the digest `{statement.vocabulary_digest}`. A ROI Name that "
            "matches one of its names, primary or reverse-order, once case, "
            "spaces, and the separators `_` and `-` are disregarded, is "
            "written in the vocabulary's spelling of the name it matches, so "
            "`lung l` and `LUNG-L` both become `Lung_L`, and `l lung` becomes "
            "the reverse-order `L_Lung`. TG-263 writes `-` for a subtraction, as in "
            "`Lungs-PTV`, so a vocabulary name that contains `-` matches only "
            "a name with `-` in the same place."
        )
    elif statement.vocabulary_digest is None:
        automatic = (
            "This statement is for a run without a vocabulary, so no ROI Name "
            "is renamed automatically. With a published edition of the TG-263 "
            "Structure Spreadsheet, a ROI Name that matches one of its names "
            "once case, spaces, and the separators `_` and `-` are disregarded "
            "is written in the vocabulary's spelling, so `lung l` and `LUNG-L` "
            "both become `Lung_L`."
        )
    else:
        automatic = (
            "The vocabulary is not a published edition of the TG-263 "
            "Structure Spreadsheet, so no ROI Name is renamed automatically "
            "and every ROI Name takes a reviewer's decision. Only with a "
            "published edition, whose entries are generic names of anatomy "
            "and targets, is a name renamed without review."
        )
    reviews = _join((f"`{review.value}`" for review in Review), "or")
    return [
        "## Cleaning ROI names",
        "",
        f"The policy gives {_ROI_NAME_NAMED} C, which is done in two tiers "
        "(D-009). The first renames a name automatically against the TG-263 "
        "vocabulary; every other name takes a reviewer's decision.",
        "",
        automatic,
        "",
        "A run may also be given an institutional list of ROI names, "
        "converted from CSV. It renames nothing: a held name that matches one "
        "of its names, as the automatic tier matches, stays held, and the "
        "confidential QC pack shows the reviewer the list's names it matched.",
        "",
        "The automatic tier sends a name to review, rather than renaming it, "
        "where any of these holds:",
        "",
        *(f"- {text}." for text in ROI_REVIEW_REASONS.values()),
        "",
        f"Every other name takes the reviewer's decision, {reviews}, that the "
        "reviewed list holds for exactly its spelling, once its padding is "
        "removed; `empty` writes an empty value. The list is the site's or "
        "project's, which the custodian keeps with the key since it holds "
        "source names verbatim, or one kept for a single run, and it is never "
        "written to the output. A run with a reviewed list records the list's "
        "keyed digest in its method digest, so that digest differs from the "
        "one this statement gives, which describes the policy without a list "
        "(D-024). What would then be written is checked again: a kept or "
        "mapped name that echoes an identifier of the instance, and different "
        "names of one structure set that would be written as the same name, "
        "ignoring case, are held, as is a name the list does not cover. "
        "Several empty names are not duplicates.",
        "",
        "For each ROI Name, cleaning writes one of these:",
        "",
        *(f"- {text}." for text in ROI_OUTCOMES.values()),
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
                f"instance in which every {_ROI_NAME_NAMED} was renamed by "
                "the automatic tier, was empty, or took a reviewer's "
                "decision. Every other attribute given C takes the action "
                "that the policy gives it without Clean Descriptors, as the "
                "Actions table shows (D-009); where that action removes "
                "or replaces it, the instance still meets the option, since "
                "PS3.15 E.3.5 specifies what the option removes, and Table "
                "E.1-1 gives the minimum actions. An instance with a held "
                "name, a name emptied without review, or another attribute "
                "given C that that action keeps does not gain that code"
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
        "and version as one value, `<implementation> <version>`, such as "
        "`CPython <version>`; `pydicom "
        "<version>`; and `tomlkit <version>`. Its "
        f"{named(_PURPOSE_OF_REFERENCE)} has "
        f"{coded(markers.DEIDENTIFYING_EQUIPMENT)}. The method digest does not "
        "cover the runtime, so this item is how an instance records it.",
    ]


def _compressed(statement: ConformanceStatement) -> list[str]:
    """Say how instances in a compressed transfer syntax are written."""
    if not any(
        t.uid in ENCAPSULATED_TRANSFER_SYNTAXES for t in statement.transfer_syntaxes
    ):
        return []
    return [
        "An instance in a transfer syntax that encapsulates Pixel Data keeps "
        "that transfer syntax and its coded pixel data, without decoding and "
        "re-encoding: the comment and application segments of each frame's "
        "codestream are cut, and the instance is written only where every "
        "frame decodes, by the decoding plugin pinned to its transfer syntax, "
        "to the same pixels as its source's frame. One whose plugin is not "
        "installed, or whose frames or codestreams fail those checks, is "
        "sequestered. Under JPEG 2000 Lossless, HTJ2K Lossless, or HTJ2K "
        "Lossless RPCL, a frame is also written only where its packet headers "
        "show every coding pass of every code-block they include; a "
        "code-block that no packet includes is decoded as all zero, so a "
        "frame truncated so far that it drops only whole code-blocks is not "
        "detected.",
        "",
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
        f"The method digest of {preset}, {vocabulary} and without a "
        f"reviewed-names list, is "
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
        *_compressed(statement),
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
        "of D. X/Z on a Type 1 or 1C attribute gives D, the dummy value that "
        "Z may write. An attribute that the IOD does not define at that place "
        "counts as Type 3 (D-020).",
        "",
        "The Type also decides what three plain actions do (D-020). A plain D "
        "gives X where the IOD does not define the attribute at that place, "
        "as Note 13 after Table E.1-1a says, and a plain Z on a Type 1 or 1C "
        "attribute gives D. A plain X always removes the attribute. Where the "
        "IOD requires it at that place, by its strictest Type, the innermost "
        "enclosing sequence that the IOD makes Type 3 at its own place is "
        "removed with it, with everything in it, and where no such sequence "
        "encloses it, the instance is sequestered. Two attributes are "
        "exceptions: removing Overlay Data (60xx,3000) removes every attribute "
        "of its overlay group where the IOD's Overlay Plane Module is "
        "user-optional, and ROI Interpreter Sequence (3006,004E) is removed "
        "alone, since its condition lapses once ROI Creator Sequence "
        "(3006,004D) is removed.",
        "",
        "For each compound action, and each plain X, Z, or D, the last column "
        "gives the action at each place where a supported IOD defines the "
        "attribute and the action differs from that elsewhere or removes more "
        "than the attribute, and then the action elsewhere. A place within a "
        "sequence that the engine removes, or replaces, with everything in it "
        "is not listed, since the attribute goes with that sequence.",
        "",
        *_table(
            ("Tag", "Attribute", "Rule", "Action", "In the supported IODs"),
            (
                (
                    e.tag,
                    e.name,
                    e.rule,
                    _code(e.action)
                    + (
                        f", in place of {_code(e.policy_action)}"
                        * bool(e.policy_action)
                    ),
                    _resolution(e, statement.iods, sequences),
                )
                for e in statement.attributes
            ),
        ),
        *_private(statement),
        *_superseded(statement),
        "",
        *_other(statement, named),
        *_local_codes(named),
        *_roi_names(statement),
        *conformance_values.values_written(named),
        "",
        *conformance_values.dates_and_times(statement, named, option),
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
        "",
        *conformance_values.residual_search(named),
        "",
        *conformance_values.release_report(),
        "",
        *conformance_values.qc_pack(named),
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
