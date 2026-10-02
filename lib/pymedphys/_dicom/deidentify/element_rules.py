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

"""Decide which rule gives each element its action under a policy.

An element's rule comes from the first of these that covers it:

1. the engine's own removals (X), inside a data set: elements of group
   0000, the DIMSE command set (PS3.7); of group 0002, the File Meta
   Information (PS3.10 Section 7.1), which the engine builds itself; and of
   group 0004, which belongs only in a DICOMDIR (PS3.3 Annex F); group
   lengths, (gggg,0000), which PS3.5
   Section 7.2 retires; Data Set Trailing Padding (FFFC,FFFC); and
   Encrypted Attributes Sequence (0400,0500), which can hold the original
   values that de-identification removes;
2. Table E.1-1's Private Attributes row, for each element of an odd group
   other than 0001, 0003, 0005, 0007, and FFFF, which PS3.5 Section 7.8.1
   does not allow for private use;
3. the policy's action for Table E.1-1's row of the attribute, by exact tag
   and then by masked tag, (50xx,xxxx), (60xx,3000), and (60xx,4000), which
   match only the repeating groups 5000 to 501E and 6000 to 601E (PS3.5
   Section 7.6);
4. the policy's action for the attribute's supplementary rule
   (:mod:`~pymedphys._dicom.deidentify.supplementary_actions`), by its tag
   in the pinned data dictionary;
5. U, by the UID role of a UI attribute
   (:mod:`~pymedphys._dicom.deidentify.uid_roles`);
6. removal by Type of a text attribute (VR LO, SH, LT, ST, UC, or UT),
   :data:`~pymedphys._dicom.deidentify.supplementary_actions.UNCOVERED_TEXT_ACTION`;
7. the default for any other attribute of the pinned data dictionary: K
   for a code string, an attribute tag, or a number (VR CS, AT, DS, IS,
   FL, FD, SL, SS, SV, UL, US, or UV); for a binary value (OB, OD, OF, OL,
   OV, OW, or UN) or a sequence (SQ), K where the instance's IOD defines
   the attribute at the element's place and X elsewhere, since a kept
   sequence's items keep their codes and numbers by this same default;
   and X for any other VR;
8. X for an element that the pinned data dictionary does not list.

No rules for cleaning the contents of a sequence are designed yet, so a
sequence to which the policy gives C, such as Reason for Visit Code
Sequence (0032,1067) under Clean Descriptors, takes its Basic Profile
action. An attribute
whose alternative VRs include a binary VR, such as LUT Data (0028,3006),
US or OW, is kept only where the IOD defines it.

Compound actions, such as X/Z/D, are kept as the rule gives them, for
:mod:`~pymedphys._dicom.deidentify.compound_actions` to resolve by Type.
No reviewed rules yet say which private attributes are safe, so a policy
that selects the Retain Safe Private Option is refused. Rules name tags,
never values.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence

from .file_layout import TAG_PATTERN
from .iods import IOD
from .policy import Policy, PolicyError
from .standard import (
    _RESERVED_ODD_GROUPS,
    DictionaryAttribute,
    dictionary_attribute,
    load_table_e1_1,
)
from .supplementary_actions import TEXT_VRS, UNCOVERED_TEXT_ACTION
from .uid_roles import load_uid_roles

PRIVATE_ROW = "(gggg,eeee) where gggg is odd"
RETAIN_SAFE_PRIVATE = "retain_safe_private"
REMOVE = "X"
KEEP = "K"
# The attributes that the engine removes by tag, wherever they are.
_ENGINE_TAGS = frozenset({"(FFFC,FFFC)", "(0400,0500)"})
# The groups that the engine removes from a data set.
_ENGINE_GROUPS = (0x0000, 0x0002, 0x0004)
# The VRs whose values the default keeps wherever they are, and the binary
# and sequence VRs whose values it keeps only where the IOD defines the
# attribute.
KEPT_VRS = frozenset(
    {"CS", "AT", "DS", "IS", "FL", "FD", "SL", "SS", "SV", "UL", "US", "UV"}
)
IOD_DEFINED_VRS = frozenset({"OB", "OD", "OF", "OL", "OV", "OW", "UN", "SQ"})


class RuleSource(enum.Enum):
    """Where an element's rule comes from, in the order the rules apply."""

    ENGINE = "engine"
    PRIVATE = "private"
    TABLE = "table"
    SUPPLEMENTARY = "supplementary"
    UID_ROLE = "uid-role"
    UNCOVERED_TEXT = "uncovered-text"
    DEFAULT = "default"
    NOT_IN_DICTIONARY = "not-in-dictionary"


@dataclasses.dataclass(frozen=True)
class ElementRule:
    """The rule that gives one element its action.

    Attributes
    ----------
    tag : str
        The element's tag, such as ``"(6002,3000)"``.
    source : RuleSource
        Where the rule comes from.
    action : str
        An action code of Table E.1-1a, such as ``"X"`` or ``"X/Z/D"``.
    entry : str
        The tag by which the source names the rule: a row of Table E.1-1,
        such as ``"(60xx,3000)"`` or the Private Attributes row; the
        attribute of the pinned data dictionary, such as ``"(60xx,0022)"``;
        ``"(0000,eeee)"``, ``"(0002,eeee)"``, ``"(0004,eeee)"``,
        ``"(gggg,0000)"``, or the tag that the engine removes; or ``""``
        for an element that the dictionary does not list.
    """

    tag: str
    source: RuleSource
    action: str
    entry: str


def _is_sequence(tag: str) -> bool:
    attribute = dictionary_attribute(tag) if TAG_PATTERN.fullmatch(tag) else None
    return attribute is not None and "SQ" in attribute.vrs


def _matches(pattern: str, tag: str) -> bool:
    """Whether a masked tag of Table E.1-1, such as (60xx,3000), covers ``tag``.

    In (50xx,eeee) and (60xx,eeee), "xx" covers only the repeating groups,
    5000 to 501E and 6000 to 601E (PS3.5 Section 7.6); odd groups are
    private, so the rule for private attributes has already covered them.
    """
    return all(want in ("x", got) for want, got in zip(pattern, tag)) and (
        pattern[1:5] not in ("50xx", "60xx") or tag[3] in "01"
    )


def _engine_entry(tag: str) -> str | None:
    """Return the entry of an element that the engine removes, or None."""
    group = int(tag[1:5], 16)
    if group in _ENGINE_GROUPS:
        return f"({group:04X},eeee)"
    if tag.endswith(",0000)"):
        return "(gggg,0000)"
    return tag if tag in _ENGINE_TAGS else None


class ElementRules:
    """The rule of every element under one policy.

    Parameters
    ----------
    policy : Policy
        A validated policy, composed from the pinned Table E.1-1, such as
        that of :func:`~pymedphys._dicom.deidentify.policy.compose_policy`.

    Attributes
    ----------
    policy : Policy

    Raises
    ------
    PolicyError
        If the policy selects the Retain Safe Private Option, or was not
        composed from the pinned Table E.1-1.

    Examples
    --------
    >>> from pymedphys._dicom.deidentify.policy import compose_policy
    >>> rules = ElementRules(compose_policy("basic"))
    >>> rule = rules.rule("(6002,3000)")
    >>> rule.source, rule.action, rule.entry
    (<RuleSource.TABLE: 'table'>, 'X', '(60xx,3000)')
    >>> rules.rule("(0009,1001)").source
    <RuleSource.PRIVATE: 'private'>
    >>> rules.rule("(300A,00C2)").action  # Beam Name, by a supplementary rule
    'X/Z/D'
    """

    def __init__(self, policy: Policy) -> None:
        if RETAIN_SAFE_PRIVATE in policy.options:
            raise PolicyError(
                "the Retain Safe Private Option is not supported until "
                "reviewed rules say which private attributes are safe"
            )
        table = load_table_e1_1()
        rows = {row.tag: row for row in table.attributes}
        if table.edition != policy.edition or rows.keys() != policy.actions.keys():
            raise PolicyError("the policy was not composed from the pinned Table E.1-1")
        self.policy = policy
        self._private = policy.actions[PRIVATE_ROW]
        self._table = {
            tag: rows[tag].basic_profile
            if action == "C" and _is_sequence(tag)
            else action
            for tag, action in policy.actions.items()
            if tag != PRIVATE_ROW
        }
        self._masked = tuple(tag for tag in self._table if "x" in tag)
        self._uid_roles = frozenset(load_uid_roles().rules)

    def rule(
        self, tag: str, path: Sequence[str] = (), *, iod: IOD | None = None
    ) -> ElementRule:
        """Return the rule of the element with ``tag`` at ``path``.

        Parameters
        ----------
        tag : str
            The element's tag, such as ``"(0010,0010)"``, with upper-case
            hexadecimal digits.
        path : sequence of str, optional
            The tags of the sequences whose items hold the element, outermost
            first. Defaults to the top level of the data set.
        iod : IOD, optional
            The instance's IOD. Only the default for a binary value depends
            on it: without one, no IOD defines the attribute, so the value
            is removed.

        Returns
        -------
        ElementRule

        Raises
        ------
        ValueError
            If ``tag``, or a tag of ``path``, is not of the form
            ``(gggg,eeee)`` with upper-case hexadecimal digits, or if
            ``path`` is a single string.
        """
        if isinstance(path, str) or not all(
            isinstance(each, str) and TAG_PATTERN.fullmatch(each)
            for each in (*path, tag)
        ):
            raise ValueError(
                "tags must be of the form (gggg,eeee) with upper-case "
                "hexadecimal digits, and path a sequence of them"
            )
        engine = _engine_entry(tag)
        if engine is not None:
            return ElementRule(tag, RuleSource.ENGINE, REMOVE, engine)
        group = int(tag[1:5], 16)
        if group % 2 and group not in _RESERVED_ODD_GROUPS:
            return ElementRule(tag, RuleSource.PRIVATE, self._private, PRIVATE_ROW)
        entry = tag if tag in self._table else None
        entry = entry or next((p for p in self._masked if _matches(p, tag)), None)
        if entry is not None:
            return ElementRule(tag, RuleSource.TABLE, self._table[entry], entry)
        attribute = dictionary_attribute(tag)
        if attribute is None:
            return ElementRule(tag, RuleSource.NOT_IN_DICTIONARY, REMOVE, "")
        source, action = self._attribute_rule(attribute, tag, tuple(path), iod)
        return ElementRule(tag, source, action, attribute.tag)

    def _attribute_rule(
        self,
        attribute: DictionaryAttribute,
        tag: str,
        path: tuple[str, ...],
        iod: IOD | None,
    ) -> tuple[RuleSource, str]:
        """Return the source and action of a dictionary attribute's rule."""
        vrs = frozenset(attribute.vrs)
        if attribute.tag in self.policy.supplementary_actions:
            action = self.policy.supplementary_actions[attribute.tag]
            return RuleSource.SUPPLEMENTARY, action
        if attribute.tag in self._uid_roles:
            return RuleSource.UID_ROLE, "U"
        if vrs & TEXT_VRS:
            return RuleSource.UNCOVERED_TEXT, UNCOVERED_TEXT_ACTION
        if vrs and vrs <= KEPT_VRS:
            return RuleSource.DEFAULT, KEEP
        if vrs and vrs <= KEPT_VRS | IOD_DEFINED_VRS and iod and iod.lookup(tag, path):
            return RuleSource.DEFAULT, KEEP
        return RuleSource.DEFAULT, REMOVE
