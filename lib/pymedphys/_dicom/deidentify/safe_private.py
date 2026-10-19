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

"""Reviewed rules for the Retain Safe Private Option.

Under the Retain Safe Private Option, E.3.10 of DICOM PS3.15 retains the
private attributes "known by the de-identifier to be safe from identity
leakage", with the private creators that define them. Table E.3.10-1 is one
way of knowing, but its Note calls it a sample list that vendors do not
guarantee, suggests retaining numeric values only, with code strings a
possible exception, and calls bulk binary data particularly unsafe.

``safe_private.toml``, curated by hand for one edition of PS3.15, gives a
rule to every row of Table E.3.10-1 and to each reviewed addition. A rule is
keyed by private creator, group, and element within the block, so it applies
whichever block the creator reserves (MIDI §1.17.3), and says how a value is
handled (:class:`Handling`): numbers checked as numbers, code strings checked
as code strings, UIDs replaced, text cleaned as descriptors, sequences parsed
item by item, or removed. Table E.1-1 gives retained private attributes C, so
nothing is kept merely because the table lists it. A rule takes the handling
of its VR (:func:`default_handling`) unless its note says why not. A reviewed
addition must retain its value, and cites the public document that shows it
is safe.

A rule's private creator is printable ISO 646, the characters in which an
instance's private creators are compared. The engine applies the rules under
the Option (:mod:`~pymedphys._dicom.deidentify.retained_private`).
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import pathlib
import re
import types
from collections.abc import Callable, Mapping
from typing import Protocol

from pymedphys._imports import tomlkit

from .standard import (
    PRIVATE_TAG_PATTERN,
    VRS,
    SafePrivateAttribute,
    is_private_tag,
    is_vm,
    load_table_e3_10_1,
)

SCHEMA = "pymedphys-deid-safe-private/1"
SAFE_PRIVATE_PATH = pathlib.Path(__file__).resolve().parent / "safe_private.toml"

# A private Data Element as a rule gives it: the group, "xx" for the block,
# and the element within the block, in upper-case hexadecimal.
RULE_TAG_PATTERN = re.compile(r"\(([0-9A-F]{4}),xx([0-9A-F]{2})\)")
# The padding that PS3.5 Section 6.2 allows after a private creator (LO).
_CREATOR_PADDING = " \x00"
# A private creator is LO: at most 64 characters, without a backslash or a
# control character other than ESC (PS3.5 Table 6.2-1).
_CREATOR_LENGTH = 64
# The characters of a rule's private creator: printable ISO 646, the bytes
# that an instance's creator is compared in (retained_private).
_CREATOR_CHARACTERS = frozenset(map(chr, range(0x20, 0x7F)))

_TOP_LEVEL_FIELDS = frozenset(
    {"schema", "edition", "acknowledgement", "table", "addition"}
)
_TABLE_FIELDS = frozenset({"private_creator", "elements"})
_ELEMENT_FIELDS = frozenset({"tag", "vr", "vm", "handling"})
_ADDITION_FIELDS = frozenset(
    {"private_creator", "tag", "vr", "vm", "handling", "source", "note"}
)


# A rule's key: its private creator, group, and element within the block.
_Key = tuple[str, int, int]


class SafePrivateRuleError(ValueError):
    """A safe private rules file that cannot be used."""


class Handling(enum.Enum):
    """How a private attribute is handled under the Retain Safe Private Option."""

    NUMERIC = "numeric"  # kept only where each value is a number of its VR
    CODE = "code"  # kept only where each value has only the characters of CS
    UID = "uid"  # replaced as every other UID is (D-003)
    TEXT = "text"  # cleaned as a descriptor, and removed where nothing cleans it
    SEQUENCE = "sequence"  # items parsed, each nested attribute on its merits
    REMOVE = "remove"  # not retained

    @property
    def retains(self) -> bool:
        """Whether the attribute can be retained, after its value is checked."""
        return self is not Handling.REMOVE


class Basis(enum.Enum):
    """Why a private attribute has a rule."""

    TABLE = "table"  # PS3.15 Table E.3.10-1 lists it
    REVIEWED = "reviewed"  # a reviewed public document shows it is safe
    # The instance's own Private Data Element Characteristics Sequence
    # (0008,0300) marks its block SAFE or lists it as nonidentifying.
    DECLARED = "declared"
    # TCIA's Private Tag Dictionary keeps it, in a run that chooses that list.
    TCIA = "tcia"


class SafePrivateList(enum.Enum):
    """The list whose rules settle private attributes in a run under the Option."""

    # safe_private.toml: Table E.3.10-1 and the reviewed additions, the default.
    REVIEWED = "reviewed"
    # TCIA's Private Tag Dictionary, which a run may choose instead (D-035).
    TCIA = "tcia"


# The VRs whose values each retaining handling can check. Every other VR, an
# alternative such as "OW/OB", and the empty VR that the table gives some
# attributes, can only be removed.
HANDLING_VRS: Mapping[Handling, frozenset[str]] = types.MappingProxyType(
    {
        Handling.NUMERIC: frozenset(
            {"AT", "DS", "FD", "FL", "IS", "SL", "SS", "SV", "UL", "US", "UV"}
        ),
        Handling.CODE: frozenset({"CS"}),
        Handling.UID: frozenset({"UI"}),
        Handling.TEXT: frozenset({"LO", "LT", "SH", "ST", "UC", "UT"}),
        Handling.SEQUENCE: frozenset({"SQ"}),
    }
)


def default_handling(vr: str) -> Handling:
    """Return the handling that a rule takes from its VR unless its note says why not.

    It follows the Note to Table E.3.10-1: numbers and code strings are
    checked and kept, UIDs are replaced, text is cleaned, sequences are
    parsed, and every other value, such as bulk binary data, is removed.
    """
    for handling, vrs in HANDLING_VRS.items():
        if vr in vrs:
            return handling
    return Handling.REMOVE


def _allows(handling: Handling, vr: str) -> bool:
    """Whether ``handling`` can apply to a value of ``vr``."""
    return handling is Handling.REMOVE or vr in HANDLING_VRS[handling]


@dataclasses.dataclass(frozen=True)
class SafePrivateRule:
    """One private attribute's rule under the Retain Safe Private Option.

    Attributes
    ----------
    private_creator : str
        The Private Creator that reserves the attribute's block, without
        padding.
    group : int
        The odd group, such as ``0x0019``.
    element : int
        The element within the block, ``0x00`` to ``0xFF``, as in
        ``(0019,xx23)``.
    vr, vm : str
        As Table E.3.10-1 or the cited document gives them.
    handling : Handling
    basis : Basis
    note : str
        Why the rule departs from its VR's handling, or about a reviewed
        addition; may be ``""`` for a table row that takes its VR's handling.
        For a rule of TCIA's dictionary, TCIA's name for the attribute.
    source : str
        The public document that shows a reviewed addition is safe, or ``""``
        for a table row.
    """

    private_creator: str
    group: int
    element: int
    vr: str
    vm: str
    handling: Handling
    basis: Basis
    note: str = ""
    source: str = ""

    @property
    def tag(self) -> str:
        """The attribute in the form ``(gggg,xxee)``."""
        return f"({self.group:04X},xx{self.element:02X})"


@dataclasses.dataclass(frozen=True)
class SafePrivateRules:
    """The safe private rules, keyed by private creator, group, and element.

    Attributes
    ----------
    edition : str
        The edition of PS3.15 whose Table E.3.10-1 the rules cover.
    acknowledgement : str
        ``"DICOM PS3.15 <edition>, © NEMA"``.
    rules : mapping of (str, int, int) to SafePrivateRule
        Read-only, in the file's order.
    """

    edition: str
    acknowledgement: str
    # A mapping is not hashable, so it is left out of the hash.
    rules: Mapping[_Key, SafePrivateRule] = dataclasses.field(hash=False)

    def rule_for(
        self,
        group: int,
        private_creator: str,
        element: int,
        vr: str | None = None,  # pylint: disable = unused-argument
    ) -> SafePrivateRule | None:
        """Return the rule for a private data element, or None if it has none.

        Parameters
        ----------
        group : int
            The element's group, which must be odd and open to private use.
        private_creator : str
            The value of the private creator that reserves the element's
            block, in whichever block it is. Trailing spaces and NULs are
            padding; the comparison is otherwise exact, so a creator in
            another case or with leading spaces has no rule.
        element : int
            The element within the block, ``0x00`` to ``0xFF``: the low byte
            of the element number.
        vr : str, optional
            The element's VR as written, or None where it is not written.
            A reviewed rule is keyed without a VR, so it does not choose the
            rule, as it does for :class:`RuleList`'s other lists.

        Raises
        ------
        ValueError
            If ``group`` is not a private group or ``element`` is not
            ``0x00`` to ``0xFF``.
        """
        if not (0 <= group <= 0xFFFF and is_private_tag(f"({group:04X},xx00)")):
            raise ValueError("the group is not open to private use")
        if not 0 <= element <= 0xFF:
            raise ValueError("the element within the block is not 0x00 to 0xFF")
        return self.rules.get(
            (private_creator.rstrip(_CREATOR_PADDING), group, element)
        )

    def retained(self) -> tuple[SafePrivateRule, ...]:
        """Return the rules that can retain a value, in the file's order."""
        return tuple(rule for rule in self.rules.values() if rule.handling.retains)


class RuleList(Protocol):
    """A list of safe private rules, as the engine applies it.

    :class:`SafePrivateRules` is the default list; a run may choose TCIA's
    dictionary instead
    (:class:`~pymedphys._dicom.deidentify.tcia_private_tags.TciaSafePrivateRules`).
    """

    def rule_for(
        self, group: int, private_creator: str, element: int, vr: str | None = None
    ) -> SafePrivateRule | None:
        """Return the rule for a private data element written with ``vr``, or None.

        ``vr`` is None where the element's VR is not written, in Implicit VR
        or as UN.
        """

    def retained(self) -> tuple[SafePrivateRule, ...]:
        """Return the rules that can retain a value."""


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _creator_problem(value: object) -> str | None:
    """Return what is wrong with a private creator, or None if it is valid."""
    if not _text(value):
        return "has a private creator that is not non-empty text"
    assert isinstance(value, str)
    if value != value.rstrip(_CREATOR_PADDING):
        return "has a private creator with trailing padding"
    if len(value) > _CREATOR_LENGTH or any(
        character == "\\" or (ord(character) < 0x20 and character != "\x1b")
        for character in value
    ):
        return "has a private creator that VR LO cannot hold"
    if not set(value) <= _CREATOR_CHARACTERS:
        return (
            "has a private creator outside printable ISO 646, in which an "
            "instance's private creators are compared"
        )
    return None


def _tag(value: object) -> tuple[int, int] | None:
    """Return the group and element of a rule's tag, or None if it is invalid."""
    if not isinstance(value, str) or not is_private_tag(value):
        return None
    match = RULE_TAG_PATTERN.fullmatch(value)
    if not match:
        return None
    return int(match.group(1), 16), int(match.group(2), 16)


def _table_tag(value: str) -> tuple[int, int]:
    """Return the group and element of a tag as Table E.3.10-1 gives it."""
    match = PRIVATE_TAG_PATTERN.fullmatch(value)
    assert match, value  # the table's loader accepts only such tags
    return int(match.group(1), 16), int(match.group(2), 16)


def _handling(value: object) -> Handling | None:
    try:
        return Handling(value)
    except ValueError:
        return None


def _handling_problem(value: object, vr: str) -> str | None:
    """Return what is wrong with a rule's handling for its VR, or None."""
    handling = _handling(value)
    if handling is None:
        return "has a handling that is not one of " + ", ".join(
            each.value for each in Handling
        )
    if not _allows(handling, vr):
        return (
            f"has the handling {handling.value}, which cannot check a value of its VR"
        )
    return None


def _element_problem(entry: dict, row: SafePrivateAttribute | None) -> str | None:
    """Return what is wrong with a rule for a row of Table E.3.10-1, or None."""
    if row is None:
        return "is not a row of Table E.3.10-1 for its private creator"
    if entry["vr"] != row.vr or entry["vm"] != row.vm:
        return "has a VR or VM other than Table E.3.10-1 gives"
    problem = _handling_problem(entry["handling"], row.vr)
    if problem:
        return problem
    if "note" in entry and not _text(entry["note"]):
        return "has a note that is not non-empty text"
    if Handling(entry["handling"]) is not default_handling(row.vr) and (
        "note" not in entry
    ):
        return "departs from the handling of its VR without a note that says why"
    return None


def _addition_element_problem(entry: dict) -> str | None:
    """Return what is wrong with a reviewed addition's attribute, or None."""
    if _tag(entry["tag"]) is None:
        return "has a tag that is not a private Data Element such as (0019,xx0C)"
    if entry["vr"] not in VRS:
        return "has a VR that is not one PS3.5 VR"
    if not is_vm(entry["vm"]):
        return "has a VM that is not of the form 1, 1-n, or 3-4 in ascending order"
    return None


def _addition_handling_problem(entry: dict) -> str | None:
    """Return what is wrong with a reviewed addition's handling and basis, or None."""
    handling = _handling(entry["handling"])
    if handling is None or not handling.retains:
        return "has a handling that does not retain its value"
    problem = _handling_problem(handling.value, entry["vr"])
    if problem:
        return problem
    if not (_text(entry["source"]) and _text(entry["note"])):
        return "has a source or note that is not non-empty text"
    return None


def _addition_problem(entry: object) -> str | None:
    """Return what is wrong with a reviewed addition, or None if it is valid."""
    if not isinstance(entry, dict) or entry.keys() != _ADDITION_FIELDS:
        return (
            "does not have exactly the fields private_creator, tag, vr, vm, "
            "handling, source, and note"
        )
    return (
        _creator_problem(entry["private_creator"])
        or _addition_element_problem(entry)
        or _addition_handling_problem(entry)
    )


def load_safe_private_rules(path: pathlib.Path | None = None) -> SafePrivateRules:
    """Load the safe private rules.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The rules file. Defaults to the one shipped with PyMedPhys.

    Raises
    ------
    SafePrivateRuleError
        If the file cannot be read; has another schema, a field other than
        schema, edition, acknowledgement, table, and addition, another
        edition than Table E.3.10-1, or lacks its acknowledgement; does not
        give its table rules and additions as arrays of tables; has table
        rules without exactly the fields private_creator and elements, for a
        private creator that the table does not list or that another table
        entry repeats, or without an array of elements; has an element
        without exactly the fields tag, vr, vm, and handling, and optionally
        note, with a tag that is not a private Data Element in upper case,
        such as (0019,xx0C), or that is not a row of the table for its
        private creator, with another VR or VM than the table gives, with a
        handling not in :class:`Handling` or one that cannot check a value
        of its VR, with an empty note, or that departs from
        :func:`default_handling` without a note; has an addition without
        exactly the fields private_creator, tag, vr, vm, handling, source,
        and note, with a private creator that is not text that VR LO can
        hold without padding, a tag as above, a VR that is not one PS3.5 VR,
        a VM that is not valid, a handling that does not retain its value or
        cannot check a value of its VR, or an empty source or note; repeats
        a private creator, group, and element, or adds a row of the table;
        or has no rule for a row of the table.
    """
    return _load((path or SAFE_PRIVATE_PATH).resolve())


@functools.lru_cache(maxsize=None)
def _load(path: pathlib.Path) -> SafePrivateRules:
    try:
        document = tomlkit.parse(path.read_text(encoding="utf-8")).unwrap()
    except (OSError, ValueError, tomlkit.exceptions.TOMLKitError) as error:
        raise SafePrivateRuleError(f"{path.name} could not be read") from error
    if document.get("schema") != SCHEMA:
        raise SafePrivateRuleError(f"{path.name} is not a {SCHEMA} file (schema)")
    unknown = sorted(document.keys() - _TOP_LEVEL_FIELDS)
    if unknown:
        raise SafePrivateRuleError(f"{path.name} has an unknown field {unknown[0]}")
    table = load_table_e3_10_1()
    if document.get("edition") != table.edition:
        raise SafePrivateRuleError(
            f"{path.name} does not cover the edition of Table E.3.10-1, {table.edition}"
        )
    acknowledgement = f"DICOM PS3.15 {table.edition}, © NEMA"
    if document.get("acknowledgement") != acknowledgement:
        raise SafePrivateRuleError(
            f"{path.name} lacks the acknowledgement {acknowledgement}"
        )
    rows = {
        (row.private_creator, *_table_tag(row.tag)): row for row in table.attributes
    }
    rules: dict[_Key, SafePrivateRule] = {}

    def add(rule: SafePrivateRule, label: str) -> None:
        key = (rule.private_creator, rule.group, rule.element)
        if key in rules:
            raise SafePrivateRuleError(
                f"{path.name} {label} repeats {rule.private_creator} {rule.tag}"
            )
        rules[key] = rule

    for number, entry in enumerate(_tables(document, "table", path), start=1):
        _read_table_entry(entry, f"table rule {number}", rows, rules, add, path)
    for number, entry in enumerate(_tables(document, "addition", path), start=1):
        label = f"addition {number}"
        problem = _addition_problem(entry)
        if problem:
            raise SafePrivateRuleError(f"{path.name} {label} {problem}")
        group, element = _tag(entry["tag"]) or (0, 0)
        if (entry["private_creator"], group, element) in rows:
            raise SafePrivateRuleError(
                f"{path.name} {label} adds a row of Table E.3.10-1, which a "
                "table rule covers"
            )
        add(
            SafePrivateRule(
                private_creator=entry["private_creator"],
                group=group,
                element=element,
                vr=entry["vr"],
                vm=entry["vm"],
                handling=Handling(entry["handling"]),
                basis=Basis.REVIEWED,
                note=entry["note"],
                source=entry["source"],
            ),
            label,
        )

    missing = [key for key in rows if key not in rules]
    if missing:
        creator, group, element = missing[0]
        raise SafePrivateRuleError(
            f"{path.name} has no rule for {creator} ({group:04X},xx{element:02X}) "
            f"of Table E.3.10-1, or for {len(missing) - 1} other rows"
        )
    return SafePrivateRules(
        edition=table.edition,
        acknowledgement=acknowledgement,
        rules=types.MappingProxyType(rules),
    )


def _tables(document: dict, field: str, path: pathlib.Path) -> list:
    """Return an array of tables of the document, which may be absent."""
    entries = document.get(field, [])
    if not isinstance(entries, list):
        raise SafePrivateRuleError(f"{path.name} {field} is not an array of tables")
    return entries


def _read_table_entry(
    entry: object,
    label: str,
    rows: Mapping[_Key, SafePrivateAttribute],
    rules: Mapping[_Key, SafePrivateRule],
    add: Callable[[SafePrivateRule, str], None],
    path: pathlib.Path,
) -> None:
    """Add the rules of one private creator's table entry."""
    if not isinstance(entry, dict) or entry.keys() != _TABLE_FIELDS:
        raise SafePrivateRuleError(
            f"{path.name} {label} does not have exactly the fields "
            "private_creator and elements"
        )
    creator = entry["private_creator"]
    if not any(key[0] == creator for key in rows):
        raise SafePrivateRuleError(
            f"{path.name} {label} has a private creator that Table E.3.10-1 "
            "does not list"
        )
    if any(key[0] == creator for key in rules):
        raise SafePrivateRuleError(
            f"{path.name} {label} repeats a private creator of an earlier table rule"
        )
    elements = entry["elements"]
    if not isinstance(elements, list) or not elements:
        raise SafePrivateRuleError(f"{path.name} {label} has no array of elements")
    for number, element in enumerate(elements, start=1):
        where = f"{label} element {number}"
        if not isinstance(element, dict) or not (
            _ELEMENT_FIELDS <= element.keys() <= _ELEMENT_FIELDS | {"note"}
        ):
            raise SafePrivateRuleError(
                f"{path.name} {where} does not have exactly the fields tag, vr, "
                "vm, and handling, and optionally note"
            )
        tag = _tag(element["tag"])
        if tag is None:
            raise SafePrivateRuleError(
                f"{path.name} {where} has a tag that is not a private Data "
                "Element in upper case, such as (0019,xx0C)"
            )
        problem = _element_problem(element, rows.get((creator, *tag)))
        if problem:
            raise SafePrivateRuleError(f"{path.name} {where} {problem}")
        add(
            SafePrivateRule(
                private_creator=creator,
                group=tag[0],
                element=tag[1],
                vr=element["vr"],
                vm=element["vm"],
                handling=Handling(element["handling"]),
                basis=Basis.TABLE,
                note=element.get("note", ""),
            ),
            where,
        )
