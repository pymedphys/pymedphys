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
from .dose_defacing import DOSE_FRACTION
from .face_blocks import EYE_REACH
from .codes import load_context_group
from .conformance import (
    CLEAN_DESCRIPTORS_FALLBACK,
    ENGINE_REMOVAL,
    FILE_META_WRITTEN,
    GRAPHICS_NOT_CLEANED,
    OPTION_CODES,
    OVERLAY_GROUP,
    SEQUENCE_NOT_CLEANED,
    SEQUESTER,
    AttributeAction,
    ConformanceStatement,
)
from .conformance_values import code as _code
from .conformance_safe_private import safe_private_section
from .conformance_values import join as _join
from .markers import PROFILE_CODE
from .policy import CLEAN_PIXEL_DATA, CLEAN_STRUCTURED_CONTENT, ENGINE_OPTIONS, UIDS
from .reviewed_descriptors import CLEAN_DESCRIPTORS
from .reviewed_roi_names import Outcome, Review
from .roi_names import Reason
from .source import ENCAPSULATED_TRANSFER_SYNTAXES
from .standard import (
    _RESERVED_ODD_GROUPS,
    ALL_OPTIONS,
    PRIVATE_ATTRIBUTES_TAG,
    load_data_dictionary,
    load_table_e1_1a,
)
from .supplementary_actions import load_supplementary_actions
from .technique_descriptors import load_technique_vocabulary

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
            "validated result satisfies them."
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
            "applies one of them, leaving the other options unmet:"
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
    """Describe the removal or retention of private attributes (D-028, D-035)."""
    row = next(e for e in statement.attributes if e.tag == PRIVATE_ATTRIBUTES_TAG)
    if statement.safe_private:
        return safe_private_section(statement)
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
            "in-house can carry the institution's name as its Manufacturer. "
        ]
        if _rule_action(_MANUFACTURER) == "K"
        else []
    )
    return [
        "## Values that can name an institution",
        "",
        f"{_join(named(tag) for tag in _CODE_TAGS)} are kept ({_code('K')}) by "
        "their supplementary rules, whatever the coding scheme, so that coded "
        "meaning survives. A code of a local coding scheme, whose "
        'Coding Scheme Designator begins with "99" or is "L" (PS3.3 Section '
        "8.2), can carry the institution's name or abbreviation in those "
        f"values{url}. "
        + "".join(manufacturer)
        + "Each such value, like every other string that the engine keeps, is "
        "listed among the retained strings of the run's confidential QC pack, "
        "where a reviewer can find it.",
        "",
        "The engine does not itself assess the residual risk of these values. "
        "The design accepts it for Manufacturer and Coding Scheme URL because "
        "such a value names an institution, not a patient, and for the codes "
        "of local coding schemes requires this disclosure. The "
        "`public-release` preset has a person review every distinct retained "
        "string, and is ready for release only where an external risk "
        "assessment of the collection states how the institutional identity "
        "that the policy keeps, these values among it, was assessed, and "
        "whether the assessment supports keeping it; the other presets keep "
        "these values without review or assessment. "
        "For the first release, the residual risk of the output, these values "
        "included, is for whoever releases the data to accept, which they may "
        "confirm, yes or no, in the attestation of the run's QC pack, under "
        "the institution's governance.",
        "",
    ]


def _superseded(statement: ConformanceStatement) -> list[str]:
    """Explain each action that the engine applies in place of the policy's."""
    found: dict[tuple[str, str], list[str]] = {}
    for e in statement.attributes:
        if e.superseded_by:
            key = (e.superseded_by, e.policy_action)
            found.setdefault(key, []).append(f"{e.name} {e.tag}")
    order = (
        ENGINE_REMOVAL,
        FILE_META_WRITTEN,
        SEQUENCE_NOT_CLEANED,
        GRAPHICS_NOT_CLEANED,
    )
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
                "Storage SOP Instance UID (0002,0003), which is the SOP Instance "
                "UID that the instance is written with, Transfer Syntax UID "
                "(0002,0010), "
                "and PyMedPhys's Implementation Class UID (0002,0012) and "
                "Implementation Version Name (0002,0013)."
            )
        elif reason == CLEAN_DESCRIPTORS_FALLBACK:
            text = (
                f"Under Clean Descriptors, each attribute other than "
                f"{_ROI_NAME_NAMED} to which the policy gives {_code(given)} "
                "takes the action that the policy gives it without Clean "
                "Descriptors, at each place, which the maintainer decided on "
                "6 October 2026, unless it is a free-text descriptor "
                "that cleaning writes, as Cleaning free-text descriptors "
                "describes; the table gives that action for each of these "
                f"{len(names)} attributes. Where that action removes "
                "or replaces the attribute, the instance still meets the "
                "option, since PS3.15 E.3.5 specifies what the option removes, "
                "and Table E.1-1 gives the minimum actions; where it keeps the "
                "attribute, the instance does not gain the option's code, as "
                "Attributes inserted describes."
            )
        elif reason == GRAPHICS_NOT_CLEANED:
            text = (
                "No cleaner for overlays and curves is designed yet, so under "
                "Clean Graphics each masked row to which the policy gives "
                f"{_code(given)} takes its Basic Profile action, as the table "
                f"shows: {_join(names)}. That action removes the attribute, and "
                "removing Overlay Data removes every attribute of its overlay "
                "group where the IOD's Overlay Plane Module is user-optional, "
                "so the instance still meets the option, since PS3.15 "
                "E.3.3 specifies what the option removes, and Table E.1-1 "
                "gives the minimum actions. An overlay group without "
                "Overlay Data may keep its overlay in unused bits of Pixel "
                "Data, as PS3.3 allowed before 2004. Under this option, the "
                "bit plane of such an overlay above High Bit in native Pixel "
                "Data is cleared, each bit set as the value's sign gives it, "
                "the written Pixel Data is checked to differ from the source "
                "in nothing else, and every attribute of the overlay's group "
                "is removed. An instance whose overlay cannot be "
                "so cleared, such as one in compressed Pixel Data or within "
                "Bits Stored, is sequestered as `overlay-in-pixel-data`."
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
        "the engine's own removals; the Private "
        f"Attributes row, for an element of an odd group other than {reserved}, "
        "which PS3.5 Section 7.8.1 does not allow for private use; the other "
        "rows of Table E.1-1, by exact tag and then by masked tag, where "
        "(50xx,eeee) and (60xx,eeee) match only the repeating groups 5000 to "
        "501E and 6000 to 601E (PS3.5 Section 7.6); the supplementary rules; "
        "U by the role of a UI attribute; and then the rules below, by the "
        "attribute's VRs in the pinned data dictionary.",
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
        "requires of a retained sequence. Referenced Series Sequence (0008,1115) "
        "and Studies Containing Other Referenced Instances Sequence (0008,1200) of "
        "the Common Instance Reference Module are removed, with their items, "
        "where the instance keeps no other reference to an instance, since their "
        "Type 1C conditions then do not hold.",
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
        f"The policy gives {_ROI_NAME_NAMED} C, which is done in two tiers. "
        "The first renames a name automatically against the TG-263 "
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
        "one this statement gives, which describes the policy without a list. "
        "What would then be written is checked again: a kept or "
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


# The rules by which the technique vocabulary keeps a value (D-036), as
# technique_descriptors applies them.
TECHNIQUE_RULES = (
    "it is printable ISO 646 (ASCII), without control characters, and holds "
    "no `^`, which separates the components of a person's name;",
    "it holds no date or time, with any separators, including a clock time "
    "written with an hour unit, as in `14H30` or `1430HRS`, no run of five or "
    "more digits, and no digits that run on across separators from one word "
    "into the next to five or more;",
    "it has at most one bare number, a word of only digits, of at most three "
    "digits before its decimal point and three after, other than two digits, "
    "a point, and two digits from `10.00` up, which could be a time;",
    "every other word is a reconstruction kernel of a reviewed prefix, two "
    "digits, and at most one of the suffixes D, F, H, S, and U, as in "
    "`B70f`, or is made of letter runs that are each a vocabulary word, or "
    "two or three vocabulary words of at least three letters joined, and "
    "digit runs of at most four digits before any decimal point and three "
    "after that are not a year from 1900 to 2099, with at most one digit run "
    "in a word, as in `T2`, `120KV`, and `0.625MM`;",
    "a single letter after digits, in a word or as the next word, is a unit "
    "or the `D` of `2D`, `3D`, or `4D`, and no two single-letter words are "
    "next to each other, as initials are;",
    "no letter run is a common personal name that is not a reviewed "
    "exception, and no title (`MR`, `MRS`, or `MS`) comes before an "
    "exception that is also a common name; and",
    "it has a vocabulary word of at least two letters.",
)


def _descriptors(
    statement: ConformanceStatement, named: Callable[[str], str]
) -> list[str]:
    """Describe how free-text descriptors are cleaned, under Clean Descriptors."""
    if CLEAN_DESCRIPTORS not in statement.options:
        return []
    technique = sorted(load_technique_vocabulary().attributes)
    reviews = _join((f"`{review.value}`" for review in Review), "or")
    return [
        "## Cleaning free-text descriptors",
        "",
        f"Each attribute other than {_ROI_NAME_NAMED} to which the policy "
        "gives C under Clean Descriptors and whose VR is SH, LO, ST, LT, UC, "
        "or UT, such as Series Description (0008,103E) or Protocol Name "
        "(0018,1030), is a free-text descriptor, and its values are cleaned "
        "where they can be, in two tiers. Each value of such "
        "an element, once its padding is removed, takes the reviewer's "
        f"decision, {reviews}, that the reviewed descriptors list holds for "
        "exactly that value of that attribute; `empty` writes an empty value. "
        "The list is the site's or project's, which the custodian keeps with "
        "the key since it holds source values verbatim, and it is never "
        "written to the output. A run records the list's keyed digest in its "
        "method digest.",
        "",
        "A value that the list does not cover is kept without review only "
        "where it is a value of a technique descriptor and every word of it "
        "is in the reviewed technique vocabulary that PyMedPhys bundles, of "
        "technique, anatomy, and equipment words, units, and the prefixes of "
        "reconstruction kernels, whose SHA-256 the run's method digest "
        "records. The technique descriptors are "
        f"{_join(named(tag) for tag in technique)}. A value is read as "
        "words, the runs of letters and digits between other characters, "
        "with any decimal places, and kept only where it echoes no "
        "identifier, as below, and:",
        "",
        *(f"- {rule}" for rule in TECHNIQUE_RULES),
        "",
        "The rules hold a value rather than keep it wherever they are unsure. "
        "A value made only of vocabulary words can still be a person's name, "
        "such as `HAND`, which is the residual risk of this tier.",
        "",
        "What a kept or mapped value would write is checked for echoes of the "
        "instance's patient and other person identifiers, as for ROI Names, "
        "and also for a whole identifier, or a word of one, of at least four "
        "letters and digits among the value's letters and digits; a value "
        "that echoes one is not cleaned. An element is written with what "
        "cleaning gives its values only where every value is cleaned, at "
        "least one is written with text, and no kept value is written beside "
        "one that a reviewer mapped or emptied, whose source the residual "
        "search must still look for. Every other such element takes the action that the "
        "policy gives it without Clean Descriptors, as the Actions table "
        "shows, and the confidential QC pack lists its values, so that a "
        "reviewer can record decisions for later runs. A value kept is "
        "left out of the residual search, as other retained values are.",
        "",
    ]


def _cleaned(
    statement: ConformanceStatement,
    named: Callable[[str], str],
    option: Callable[[str], str],
) -> list[str]:
    """Describe how each selected option's cleaner cleans its attributes."""
    lines: list[str] = []
    for cleaned in statement.cleaned:
        tags = _join(named(tag) for tag in cleaned.tags)
        settled = (
            f"{tags}, which hold content items, and the engine cleans them by "
            "their concept names."
            if cleaned.option == CLEAN_STRUCTURED_CONTENT
            else f"{tags}, wherever they are in the data set, and a reviewed "
            "cleaner settles them."
        )
        lines += [
            f"## Cleaning under the {option(cleaned.option)}",
            "",
            f"The policy gives C under this option to {settled} {cleaned.method}",
            "",
        ]
    return lines


# When an instance gains each option's code that it gains only after review.
_REVIEW_CONDITIONS = {
    markers.OPTION_CODES["clean_descriptors"]: (
        f"only in an instance in which every {_ROI_NAME_NAMED} was renamed by "
        "the automatic tier, was empty, or took a reviewer's "
        "decision. Every other attribute given C is a free-text "
        "descriptor that cleaning writes, or takes the action "
        "that the policy gives it without Clean Descriptors, as the "
        "Actions table shows; where that action removes "
        "or replaces it, the instance still meets the option, since "
        "PS3.15 E.3.5 specifies what the option removes, and Table "
        "E.1-1 gives the minimum actions. An instance with a held "
        "name, a name emptied without review, or another attribute "
        "given C that that action keeps does not gain that code"
    ),
    markers.OPTION_CODES["clean_pixel_data"]: (
        "only in an instance that has nothing for the option to clean, having "
        "no Pixel Data, Float Pixel Data, or Double Float Pixel Data at the top "
        "level of its data set, or whose source file is, by its SHA-256, one "
        "whose blacked-out regions a reviewer accepted, or added to, after "
        "seeing every frame, in the attested QC pack of an earlier run of the "
        "same files. The engine then blacks out exactly the regions that the "
        "reviewer approved, without its text finder, and sequesters the "
        "instance where one goes past its frame. Such an instance also has Burned In "
        "Annotation (0028,0301) set to NO, as PS3.15 E.3.1 requires, including "
        "in an IOD that does not define the attribute, which of the supported "
        "IODs are RT Plan, RT Structure Set, RT Beams Treatment Record, MR "
        "Spectroscopy, Spatial Registration, Deformable Spatial "
        "Registration, X-Ray Radiation Dose SR, and Radiopharmaceutical "
        "Radiation Dose SR. There it is a "
        "standard attribute of a Standard Extended SOP Class (PS3.2 Section "
        "7.3), added to the top level of the data set as an attribute of the "
        "instance, where every PS3.3 module that defines it, such as the "
        "General Image Module, places it. Any other instance with Pixel Data "
        "does not gain that code: it is held for review, or sequestered where "
        "the reviewer rejected it, so it is never released"
    ),
    markers.OPTION_CODES["clean_recognizable_visual_features"]: (
        "only in an instance that cannot show a face, having no Pixel Data, "
        "Float Pixel Data, Double Float Pixel Data, or deformable "
        "registration grid and not being an RT Structure Set, or whose "
        "source file is, by its SHA-256, in a series that a reviewer marked "
        "free of a recognisable face in the attested "
        "QC pack of an earlier run of the same files, and whose pixel data, "
        "by their SHA-256, are written as that run wrote them, which its "
        "review showed, as are an RT Structure Set's contours, which it does "
        "not show. Such an instance also "
        "has Recognizable Visual Features (0028,0302) set to NO, as PS3.15 "
        "E.3.2 requires, including in an IOD that does not define the "
        "attribute, which of the supported IODs are RT Plan, RT Structure "
        "Set, RT Beams Treatment Record, MR Spectroscopy, Spatial "
        "Registration, Deformable Spatial Registration, X-Ray Radiation Dose "
        "SR, and Radiopharmaceutical Radiation Dose SR. There it is a "
        "standard attribute of a "
        "Standard Extended SOP Class (PS3.2 Section 7.3), added to the top "
        "level of the data set as an attribute of the instance, where every "
        "PS3.3 module that defines it, such as the General Image Module, "
        "places it. Any other instance that can show a face, including every "
        "one with a deformable registration grid, which no preview of the "
        "pack draws, does not gain that code, and is held for review, so it "
        "is never released. The "
        "run also sets to air the region in front of a plane just behind the "
        "centres of the eyes, from their lower edge up, of each CT Image "
        "series in which it finds both eyes, keeping the brain in the "
        "cranial cavity above the orbits, though not the air of a sinus "
        "ahead of that plane that bone parts from the brain within a "
        "slice; this alone never "
        "gains the code, a verdict on "
        "a series seen before it was defaced does not cover it defaced, a "
        "series with a PTV, CTV, or GTV in its Frame of Reference that "
        "reaches that region, judged by the convex hull "
        "of its contours so that anything interpolated between them "
        "counts, or with such a target anywhere in another Frame of "
        "Reference that its structure set ties to the series' slices by a "
        "contour image, is held for review, a target naming no Frame of "
        "Reference, or none that can be read as one UID that its structure "
        "set declares alone, counting as one in the series' frame and in "
        "each frame its set declares where that set is in the series' "
        "frame, names no valid one, refers to its slices, or does not give "
        "a Patient ID that differs from the series', Patient IDs being "
        "compared without padding or case, and one that is empty, not "
        "text, of several values, or holds a character other than "
        "printable ASCII differing from none, "
        "while a target in another "
        "Frame of Reference that its structure set does not tie to them, "
        "such as one on a registered MR, does not hold it, as is a series "
        "whose structure set, of those searched for such targets, draws an "
        "eye, by its ROI Name, in its Frame of Reference or naming none "
        "that can be read as one UID that the set declares alone, "
        f"more than {EYE_REACH:.0f} mm from the nearer of the eyes that the "
        "run found, and so is "
        "each RT Structure Set, RT Dose with pixel data, and PET "
        "instance that is in a defaced series' "
        "Frame of Reference, names none, or refers to a defaced slice, which "
        "the run does not clean. An RT Structure Set in the Frame of "
        "Reference of only one defaced series, each of whose ROIs is in that "
        "frame, is cleaned instead: each contour that reaches the region "
        "where it is set to air, other than the brain kept, loses "
        "its part there, keeping its part in the brain kept, where the contour "
        "is closed and it and each other closed contour of its ROI in its "
        "plane are simple, but for a point that repeats the one before it, "
        "lie at one z with every point within them nearest one axial slice "
        "within half the slices' spacing, and "
        "have pieces there that join into closed contours, a "
        "CLOSED_PLANAR contour's being split along edges between columns "
        "of pixels until none bounds a hole, and otherwise cut "
        "by the region's two planes, as "
        "is each other closed "
        "contour of its ROI in its plane, such as a hole's, a contour wholly "
        "within the region being removed, and every other contour is "
        "kept as received, unless a contour cannot be cut, such as a closed "
        "one that lies in no one plane in an ROI that is cut, when the "
        "structure set is held. A single-frame PET image there is cleaned "
        "too: its activity in that region, less the brain kept, is "
        "set to zero. An RT Dose in the Frame of "
        "Reference of only one defaced series, with native pixel data of no "
        "negative value "
        "on a grid placed as PS3.3 Section C.8.8.3.2 defines, is cleaned "
        "instead: its dose in that region, "
        "less the brain kept, is set to zero, never recalculated, "
        "and its dose-volume histograms are kept as received; where the "
        f"greatest dose set to zero would be more than {DOSE_FRACTION:.0%} of "
        "the grid's "
        "greatest, it is not set to zero, and the RT Dose is held for review. "
        "A verdict on an instance held for either reason, given "
        "beside the defaced images, does not cover it in a later run"
    ),
}


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
        for code in found.review_codes:
            codes += f", then {coded(code)} " + _REVIEW_CONDITIONS[code]
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
        "record what was done (PS3.15 E.1.1, E.2, and E.3.6). The values "
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


def _key_scope(statement: ConformanceStatement, bits: int) -> list[str]:
    """Say how far the run's generated values agree, by its key's scope (D-004)."""
    derived = (
        "Replacement UIDs and patient pseudonyms are each derived from the "
        "source as an HMAC-SHA256 under that key, in a domain of their own. "
    )
    same = (
        "every occurrence of a source UID therefore gets the same replacement, "
        "in every instance, series, study, and patient, including nested "
        "references and the File Meta Information, and every instance of a "
        "subject gets the same pseudonyms."
    )
    if not statement.project_key:
        return [
            f"Each run has its own {bits}-bit key, from a cryptographically "
            "secure generator, which is discarded after the run. "
            + derived
            + "Within a run, "
            + same
            + " Across runs they are not consistent: de-identifying the same "
            "study in two runs gives unrelated replacements, and no map from "
            "source to replacement values is kept."
        ]
    return [
        f"The run's key is a project key of {bits} bits, from a "
        "cryptographically secure generator, which its custodian keeps, "
        "outside the release and the QC pack, for every run of the project. "
        + derived
        + "In every run under the key, "
        + same
        + " Each subject's date offset is recorded in the custodian's subject "
        "profiles when the subject is first exported, and read back for every "
        "later run, so a study de-identified in a later run keeps its "
        "intervals to the earlier ones. Releases under one key can therefore "
        "be linked to each other by their replacement values, and anyone who "
        "holds the key can recompute them from candidate source values, so "
        "the key is kept as securely as a map from source to replacement "
        "values would be; the release records only its non-secret identifier."
    ]


def _retained_uids(
    statement: ConformanceStatement, option: Callable[[str], str]
) -> list[str]:
    """Say what keeping UIDs does to referential integrity, where it applies."""
    if UIDS not in statement.options:
        return []
    return [
        "",
        f"Under the {option(UIDS)}, each UID of an attribute to which "
        "Table E.1-1 gives K under it is kept as it is, wherever it occurs, "
        "and Media Storage SOP Instance UID (0002,0003) is the kept SOP "
        "Instance UID. The UIDs of every other attribute are "
        "replaced as described above, so a reference at such an attribute, "
        "such as Multi-frame Source SOP Instance UID (0008,1167), no longer "
        "names the kept UID of the instance that it named. Where that "
        "instance is in the same run, the residual search finds the "
        "reference's source value in its kept UIDs, and withholds it and "
        "each instance that keeps a reference to it. Kept UIDs link "
        "each instance to its source: anyone with access to the source "
        "images, or to a database of them, can recover the patient's "
        "identity from them (PS3.15 E.3.9). Output files are still named by "
        "keyed replacement UIDs, so no source UID is in a file's name.",
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
        + _join(option(o) for o in ALL_OPTIONS)
        + ".",
        "- Options whose policies the engine applies: "
        + _join(option(o) for o in ENGINE_OPTIONS)
        + "; it refuses a policy that selects any other.",
        "- Options that are not supported, since the engine does not yet "
        "apply them: "
        + (_join(option(o) for o in ALL_OPTIONS if o not in ENGINE_OPTIONS) or "none")
        + ".",
        "",
        "## Conformance claim",
        "",
        *_claim(statement, preset, options, option),
        "",
        "## Method digest",
        "",
        f"The method digest of {preset}, {vocabulary}, without the technique "
        "vocabulary of free-text descriptors, "
        + (
            "without a reviewed-names or reviewed descriptors list, and "
            "without a text finder or region rules, "
            if CLEAN_PIXEL_DATA in statement.options
            else "and without a reviewed-names or reviewed descriptors list, "
        )
        + f"is `{statement.method_digest}`. "
        "It identifies the policy and the PyMedPhys implementation "
        "and resources that apply it.",
        "",
        "## Supported instances",
        "",
        f"Instances of the {_join(statement.iods)} IODs, of these Storage SOP "
        "Classes and in these transfer syntaxes, are de-identified. Every "
        "other instance is sequestered: it is not written, and is excluded "
        "from any claim.",
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
        "its supplementary rule, or, for a UI attribute, "
        "U by its UID role. The actions are those of Table E.1-1a:",
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
        "counts as Type 3.",
        "",
        "The Type also decides what three plain actions do. A plain D "
        "gives X where the IOD does not define the attribute at that place, "
        "as Note 13 after Table E.1-1a says, and a plain Z on a Type 1 or 1C "
        "attribute gives D. Clinical Trial Protocol Ethics Committee Name "
        "(0012,0081), which Table E.1-1 gives D, or K under the Retain "
        "Institution Identity Option, is removed, since it is Type "
        "1C, required if Clinical Trial Protocol Ethics Committee Approval "
        "Number (0012,0082) is present, which the table removes, and PS3.5 "
        "Section 7.4.2 does not allow it otherwise. A plain X always removes "
        "the attribute. Where the "
        "IOD requires it at that place, by its strictest Type, the innermost "
        "enclosing sequence that the IOD makes Type 3 at its own place is "
        "removed with it, with everything in it, and where no such sequence "
        "encloses it, the instance is sequestered. Two attributes are "
        "exceptions: removing Overlay Data (60xx,3000) removes every attribute "
        "of its overlay group where the IOD's Overlay Plane Module is "
        "user-optional, and ROI Interpreter Sequence (3006,004E) is removed "
        "alone, since its condition lapses once ROI Creator Sequence "
        "(3006,004D) is removed. Requested Procedure ID (0040,1001), which "
        "Table E.1-1 gives X, is Type 2 in Referenced Request Sequence "
        "(0040,A370), which a Structured Report holds where it was made for "
        "a request, and no Type 3 sequence encloses it there, so it is "
        "emptied there instead, rather than sequester the report. This "
        "departs from the table's X; the zero-length value discloses "
        "nothing that removal would not.",
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
        *_descriptors(statement, named),
        *_cleaned(statement, named, option),
        *conformance_values.values_written(statement, named),
        "",
        *conformance_values.dates_and_times(statement, named, option),
        "",
        "## Attributes inserted",
        "",
        *_inserted(statement, named, coded),
        "",
        "## Referential integrity",
        "",
        *_key_scope(statement, bits),
        *_retained_uids(statement, option),
        "",
        "## Encrypted Attributes",
        "",
        "No attribute is placed in an Encrypted Attributes Data Set for later "
        "re-identification: the engine writes no Encrypted Attributes "
        "Sequence (0400,0500), and no other data from which identities could "
        "be recovered. No transfer syntax therefore encodes such a "
        "data set, and no key is selected to encrypt one. The engine uses no "
        f"public keys; its only key is the run's {bits}-bit key.",
        "",
        *conformance_values.residual_search(named),
        "",
        *conformance_values.release_report(),
        "",
        *conformance_values.qc_pack(statement, named),
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
