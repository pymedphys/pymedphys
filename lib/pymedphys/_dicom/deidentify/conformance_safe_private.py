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

"""Write the conformance statement's section on the safe private attributes.

PS3.15 E.3.10 requires that "The safe Private Attributes that are retained
shall be described in the Conformance Statement".
:func:`safe_private_section` describes, under the Retain Safe Private Option,
how the reviewed rules settle the C that Table E.1-1 gives private
attributes (:mod:`~pymedphys._dicom.deidentify.retained_private`),
and lists each rule that can retain an attribute, with the meaning that
Table E.3.10-1 gives it.
:func:`~pymedphys._dicom.deidentify.conformance_markdown.render_markdown`
takes it in place of the paragraph on the removal of private attributes.
"""

from __future__ import annotations

from .conformance import ConformanceStatement
from .safe_private import Basis
from .standard import PRIVATE_TAG_PATTERN, load_table_e3_10_1

# What each handling that can retain an attribute does, as the statement
# says it.
_HANDLINGS = (
    (
        "numeric",
        "kept where its value is a whole number of values of its binary VR, "
        "or each value is a valid IS or DS, and the number of values is one "
        "that the rule's VM allows",
    ),
    (
        "code",
        "kept where each value is a valid CS, of at most 16 upper-case "
        "letters, digits, spaces, and underscores, and the number of values "
        "is one that the rule's VM allows",
    ),
    (
        "uid",
        "replaced (U), as every other UID is, where it is written as UI, and "
        "otherwise removed, since its value cannot be read as UIDs",
    ),
    (
        "sequence",
        "kept as a container where the source holds its items, so that each "
        "element in them takes its own rule, as E.3.10 requires, and "
        "otherwise removed",
    ),
)


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _meanings() -> dict[tuple[str, int, int], str]:
    """Return Table E.3.10-1's meaning of each row, by creator, group, and element."""
    found = {}
    for row in load_table_e3_10_1().attributes:
        match = PRIVATE_TAG_PATTERN.fullmatch(row.tag)
        assert match, row.tag  # the table's loader accepts only such tags
        group, element = int(match.group(1), 16), int(match.group(2), 16)
        found[(row.private_creator, group, element)] = row.meaning
    return found


def safe_private_section(statement: ConformanceStatement) -> list[str]:
    """Describe the safe private attributes that the statement's policy retains.

    Parameters
    ----------
    statement : ConformanceStatement
        Of a policy that selects the Retain Safe Private Option, whose
        element rules the engine applies.

    Returns
    -------
    list of str
        The section's lines, starting with a blank line and its heading.
    """
    meanings = _meanings()
    rows = [
        "| Private Creator | Tag | VR | VM | Handling | Meaning |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for rule in statement.safe_private:
        meaning = (
            meanings.get((rule.private_creator, rule.group, rule.element), "")
            if rule.basis is Basis.TABLE
            else f"Reviewed addition: {rule.source}"
        )
        cells = (
            rule.private_creator,
            rule.tag,
            rule.vr,
            rule.vm,
            rule.handling.value,
            meaning,
        )
        line = "| " + " | ".join(_cell(cell) for cell in cells) + " |"
        rows.append(line.replace("|  |", "| |"))
    return [
        "",
        "## Safe private attributes",
        "",
        "Under the Retain Safe Private Option, Table E.1-1 gives Private "
        "Attributes C, which the reviewed rules of `safe_private.toml` settle "
        "for each private attribute, at the top level and in the items of "
        "every sequence that is kept (PS3.15 E.3.10, D-035). A rule is keyed "
        "by the private creator that reserves the attribute's block, the odd "
        "group, and the element within the block, written (gggg,xxee), so it "
        "applies in whichever block the creator reserves. A private creator "
        "matches a rule only where its value, without trailing spaces and "
        "NULs, is printable ISO 646 without a backslash, written as LO or "
        "without a VR, and is exactly the rule's.",
        "",
        "A rule settles its attribute only where the attribute is written "
        "with the rule's VR, or without one, in Implicit VR Little Endian or "
        "as UN. By its handling, the attribute is:",
        "",
        *(f"- {handling}: {meaning};" for handling, meaning in _HANDLINGS[:-1]),
        f"- {_HANDLINGS[-1][0]}: {_HANDLINGS[-1][1]}.",
        "",
        "A private sequence that no rule lists is parsed, as E.3.10 asks of a "
        "sequence not known to hold only safe content, where its block's "
        "creator is printable ISO 646 without a backslash, written as LO or "
        "without a VR: each attribute in its items takes its own rule, and the "
        "sequence is kept only where one of them, at any depth, other than a "
        "private creator, is kept or replaced, and is otherwise removed with "
        "everything in it. A creator that no rule names, kept for such a "
        "sequence, is among the retained strings that the QC pack lists for "
        "review.",
        "",
        "Every other private attribute is removed: one whose rule is for text, "
        "since no reviewed cleaner cleans private text (D-009), or removes it; "
        "one without a rule that is not such a sequence; one in a block "
        "without such a creator; one whose value does not pass its handling's "
        "check; and each element in an odd group that PS3.5 Section 7.8.1 does "
        "not allow. A private creator is kept where an attribute of its block "
        "in the same data set or item is kept or replaced, and removed "
        "otherwise. Private Data Element Characteristics Sequence (0008,0300) "
        "is not yet followed, and is removed by its supplementary rule; this "
        "is among what the statement does not yet describe.",
        "",
        f"These are the {len(statement.safe_private)} rules that can retain "
        f"an attribute, for Table E.3.10-1 of PS3.15 {statement.edition} and "
        "any reviewed addition, with the meaning that the table gives each:",
        "",
        *rows,
    ]
