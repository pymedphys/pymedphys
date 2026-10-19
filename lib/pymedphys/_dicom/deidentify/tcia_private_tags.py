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

"""TCIA's Private Tag Dictionary, a second source of safe private attributes.

The Cancer Imaging Archive (TCIA) curates its collections under the Retain
Safe Private Option, and publishes the dictionary of private attributes that
it uses, with a disposition for each, saying whether it is kept. PyMedPhys
ships one file of it unchanged in ``_tcia/``, with TCIA's attribution and
licence beside it. :data:`PIN` records where it came from and its SHA-256,
and :func:`load_tcia_private_tags` refuses a file that no longer matches, so
the shipped copy is always the original; ``pymedphys dev tcia-check``
downloads TCIA's file and compares the two, each month and on pull requests
that change the dictionary.

Each row describes one attribute by its path: the private creator, group,
and element within the block of each private step, and the tag of each
standard step, from the top level down through the sequences that hold it.
Only the disposition ``k`` keeps an attribute. A ``k`` records that TCIA
keeps the attribute in its own curation; it checks no value, so a value that
it keeps must still pass the handling of its VR.

The reviewed rules of ``safe_private.toml`` are the default list, and this
is the list that a run may choose instead (D-035).
:func:`tcia_safe_private_rules` gives its rules
(:class:`TciaSafePrivateRules`), which the engine applies as it applies the
reviewed rules:

- A rule is made from each row at the top level that names a private
  creator in printable ISO 646, without a backslash, as an instance's
  creators are compared. A row below the top level makes none, so an
  attribute that only such a row keeps is removed; a rule made from a
  top-level row applies wherever its creator's block is, as a reviewed rule
  does.
- The dictionary gives an attribute a row for each VR that TCIA has seen it
  with, such as DS, and OB or UN where a file held it without a readable
  VR. An attribute written with a VR takes the rule of the row for that VR,
  and has none where no row gives it. One whose VR is not written, in
  Implicit VR or as UN, takes the rule of the one VR other than OB, UN, or
  none that its rows give, and has none where they give several or none.
- A row that keeps its attribute (``k``) makes a rule with the handling of
  its VR (:func:`~pymedphys._dicom.deidentify.safe_private.default_handling`),
  so a value that it keeps still passes that check, and with a single value.
  Where a reviewed rule has the same private creator, group, element, and
  VR, the rule takes that rule's handling and VM instead. Any other row
  makes a rule that removes its attribute, as do rows for one VR that
  disagree.
"""

from __future__ import annotations

import csv
import dataclasses
import functools
import hashlib
import io
import pathlib
import re
import types
from collections.abc import Mapping

from .safe_private import (
    Basis,
    Handling,
    SafePrivateRule,
    default_handling,
    load_safe_private_rules,
)
from .standard import VRS

TCIA_DIR = pathlib.Path(__file__).resolve().parent / "_tcia"

# The columns of the dictionary, in order.
HEADER = ("element_sig_pattern", "tag_name", "vr", "private_disposition")
# The dispositions that the dictionary gives, after stripping spaces and
# folding case. Only KEEP retains an attribute.
KEEP = "k"
DISPOSITIONS = frozenset({KEEP, "d", "h", "o", "oi", "na", ""})

# One step of a path: a tag, such as (0008,1115), or a private attribute,
# such as (0019,"GEMS_ACQU_01",23). The dictionary quotes some private
# creators, leaves the opening quote off others, and gives no creator for
# some private attributes, as in (0009,,02).
_TAG_STEP = re.compile(r"\(([0-9A-Fa-f]{4}),([0-9A-Fa-f]{4})\)")
_PRIVATE_STEP = re.compile(r'\(([0-9A-Fa-f]{4}),"?(.*?)"?,([0-9A-Fa-f]{2})\)')
# Between steps, the depth of the item that the next step is in: [<0>] for
# an item of a top-level sequence, [<1>] one level down, and so on.
_DEPTH = re.compile(r"\[<([0-9]+)>\]")
_RESERVED_ODD_GROUPS = frozenset({0x0001, 0x0003, 0x0005, 0x0007, 0xFFFF})
# The padding that PS3.5 Section 6.2 allows after a private creator.
_CREATOR_PADDING = " \x00"
# The characters of a private creator that an instance's creators are
# compared in: printable ISO 646 without a backslash (retained_private).
_CREATOR_CHARACTERS = frozenset(map(chr, range(0x20, 0x7F))) - {"\\"}
# The VRs of rows that say nothing of how a value is read: those of an
# attribute that a file held as bytes, without a VR, or as UN.
_UNREAD_VRS = frozenset({"OB", "UN", ""})
# The VM of a rule that keeps an attribute that no reviewed rule gives a VM.
_SINGLE_VALUE = "1"


class TciaPrivateTagError(ValueError):
    """A TCIA Private Tag Dictionary that cannot be used."""


@dataclasses.dataclass(frozen=True)
class Pin:
    """Where the shipped dictionary came from.

    Attributes
    ----------
    file_name : str
        The file in ``_tcia/``, named as TCIA names it.
    url : str
        Where TCIA publishes it.
    page_url : str
        The page of TCIA's site that links to it.
    sha256 : str
        The SHA-256 of the file, in lower-case hexadecimal.
    size : int
        Its length in bytes.
    retrieved : str
        The date it was downloaded, as YYYY-MM-DD.
    """

    file_name: str
    url: str
    page_url: str
    sha256: str
    size: int
    retrieved: str


PIN = Pin(
    file_name="TCIAPrivateTagKB-02-01-2024-formatted.csv",
    url=(
        "https://wiki.cancerimagingarchive.net/download/attachments/3539047/"
        "TCIAPrivateTagKB-02-01-2024-formatted.csv"
        "?version=2&modificationDate=1707174689263&api=v2"
    ),
    page_url=(
        "https://www.cancerimagingarchive.net/"
        "submission-and-de-identification-overview/"
    ),
    sha256="68e38b67778ddb8ffa60f46bef894f3931330781e375c52bc06fc86cad44d111",
    size=674200,
    retrieved="2026-10-12",
)

# The attribution that CC BY 3.0 asks of anything that reproduces the
# dictionary, such as a conformance statement that lists its rules.
ACKNOWLEDGEMENT = (
    "Private Tag Dictionary of The Cancer Imaging Archive (TCIA), "
    "CC BY 3.0 (https://creativecommons.org/licenses/by/3.0/)"
)


@dataclasses.dataclass(frozen=True)
class Step:
    """One step of an attribute's path.

    Attributes
    ----------
    group : int
        The group.
    element : int
        The element within the block, ``0x00`` to ``0xFF``, of a private
        attribute, or the whole element number of a tag.
    private_creator : str or None
        The private creator that reserves the block of a private attribute,
        as the dictionary gives it, which is ``""`` where it gives none, or
        None for a tag.
    """

    group: int
    element: int
    private_creator: str | None = None

    @property
    def is_private(self) -> bool:
        """Whether the step is a private attribute named by its creator."""
        return self.private_creator is not None


@dataclasses.dataclass(frozen=True)
class TciaPrivateTag:
    """One row of the dictionary.

    Attributes
    ----------
    path : tuple of Step
        From the top level down: each step but the last is a sequence, and
        the last is the attribute that the row describes.
    name : str
        TCIA's name for the attribute, prefixed by the names of the sequences
        that hold it.
    vr : str
        The VR, or ``""`` where the dictionary gives none.
    disposition : str
        The disposition, stripped of spaces and in lower case: one of
        :data:`DISPOSITIONS`.
    """

    path: tuple[Step, ...]
    name: str
    vr: str
    disposition: str

    @property
    def keeps(self) -> bool:
        """Whether TCIA keeps the attribute."""
        return self.disposition == KEEP


@dataclasses.dataclass(frozen=True)
class TciaPrivateTags:
    """The dictionary, with the rows for each top-level private attribute.

    Attributes
    ----------
    pin : Pin
        Where the file came from.
    rows : tuple of TciaPrivateTag
        In the file's order.
    top_level : mapping of (str, int, int) to tuple of TciaPrivateTag
        The rows of each private attribute at the top level, keyed by private
        creator without trailing spaces and NULs, group, and element within
        the block; one attribute can have a row for each of several VRs.
        Read-only.
    """

    pin: Pin
    rows: tuple[TciaPrivateTag, ...]
    # A mapping is not hashable, so it is left out of the hash.
    top_level: Mapping[tuple[str, int, int], tuple[TciaPrivateTag, ...]] = (
        dataclasses.field(hash=False)
    )

    def rows_for(
        self, group: int, private_creator: str, element: int
    ) -> tuple[TciaPrivateTag, ...]:
        """Return the rows for a private attribute at the top level.

        ``private_creator`` is compared exactly, apart from trailing spaces
        and NULs, which are padding. The dictionary writes some creators in
        upper case, and such a row matches only a creator in upper case.
        """
        return self.top_level.get(
            (private_creator.rstrip(_CREATOR_PADDING), group, element), ()
        )


def _step(text: str) -> Step | None:
    """Return a step of a path, or None if it is not one."""
    match = _TAG_STEP.fullmatch(text)
    if match:
        return Step(int(match.group(1), 16), int(match.group(2), 16))
    match = _PRIVATE_STEP.fullmatch(text)
    if not match:
        return None
    group = int(match.group(1), 16)
    if group % 2 == 0 or group in _RESERVED_ODD_GROUPS:
        return None
    return Step(group, int(match.group(3), 16), match.group(2))


def _path(pattern: str) -> tuple[Step, ...] | None:
    """Return the path of a row's pattern, or None if it is not one."""
    parts = _DEPTH.split(pattern)
    steps, depths = parts[0::2], parts[1::2]
    if depths != [str(depth) for depth in range(len(depths))]:
        return None
    path = [_step(step) for step in steps]
    if not all(path):
        return None
    return tuple(step for step in path if step is not None)


def _row(cells: list[str]) -> TciaPrivateTag | str:
    """Return a row of the dictionary, or what is wrong with it."""
    if len(cells) != len(HEADER):
        return f"does not have the {len(HEADER)} columns of the header"
    pattern, name, vr, disposition = cells
    path = _path(pattern)
    if path is None:
        return (
            "has an element pattern that is not a path of tags and private attributes"
        )
    if not any(step.is_private for step in path):
        return "describes no private attribute"
    if vr and vr not in VRS:
        return "has a VR that is not empty or one PS3.5 VR"
    normalised = disposition.strip().lower()
    if normalised not in DISPOSITIONS:
        return "has a disposition that is not one of " + ", ".join(
            sorted(DISPOSITIONS - {""})
        )
    return TciaPrivateTag(path=path, name=name, vr=vr, disposition=normalised)


def load_tcia_private_tags(path: pathlib.Path | None = None) -> TciaPrivateTags:
    """Load TCIA's Private Tag Dictionary.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The dictionary. Defaults to the one shipped with PyMedPhys, which
        must match :data:`PIN`.

    Raises
    ------
    TciaPrivateTagError
        If the file cannot be read; is not the length and SHA-256 that
        :data:`PIN` records; is not UTF-8 CSV with the columns of
        :data:`HEADER`; or has a row without those four columns, with an
        element pattern that is not a path of tags and private attributes in
        odd groups open to private use, with item depths [<0>], [<1>], and
        so on in order, that names no private attribute, with a VR that is
        not empty or one PS3.5 VR, or with a disposition, stripped of spaces
        and in lower case, not in :data:`DISPOSITIONS`. A message names the
        row by its number, never by its content.
    """
    return _load((path or TCIA_DIR / PIN.file_name).resolve())


@functools.lru_cache(maxsize=None)
def _load(path: pathlib.Path) -> TciaPrivateTags:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise TciaPrivateTagError(f"{path.name} could not be read") from error
    if len(content) != PIN.size or hashlib.sha256(content).hexdigest() != PIN.sha256:
        raise TciaPrivateTagError(
            f"{path.name} is not TCIA's file of {PIN.retrieved}: its length or "
            "SHA-256 does not match the pin"
        )
    return parse_tcia_private_tags(content, path.name)


def parse_tcia_private_tags(content: bytes, name: str) -> TciaPrivateTags:
    """Parse the bytes of a Private Tag Dictionary, without checking the pin.

    :func:`load_tcia_private_tags` checks the pin, then calls this.

    Parameters
    ----------
    content : bytes
        The file's bytes.
    name : str
        What to call the file in messages.

    Raises
    ------
    TciaPrivateTagError
        For each problem with the file's content that
        :func:`load_tcia_private_tags` lists.
    """
    try:
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""))
        table = list(reader)
    except (UnicodeDecodeError, csv.Error) as error:
        raise TciaPrivateTagError(f"{name} is not UTF-8 CSV") from error
    if not table or tuple(table[0]) != HEADER:
        raise TciaPrivateTagError(
            f"{name} does not have the columns " + ", ".join(HEADER)
        )
    rows: list[TciaPrivateTag] = []
    top_level: dict[tuple[str, int, int], list[TciaPrivateTag]] = {}
    for number, cells in enumerate(table[1:], start=1):
        row = _row(cells)
        if isinstance(row, str):
            raise TciaPrivateTagError(f"{name} row {number} {row}")
        rows.append(row)
        (step, *nested) = row.path
        if not nested and step.private_creator is not None:
            creator = step.private_creator.rstrip(_CREATOR_PADDING)
            key = (creator, step.group, step.element)
            top_level.setdefault(key, []).append(row)
    return TciaPrivateTags(
        pin=PIN,
        rows=tuple(rows),
        top_level=types.MappingProxyType(
            {key: tuple(each) for key, each in top_level.items()}
        ),
    )


# The key of an attribute: its private creator, group, and element within
# the block.
_Key = tuple[str, int, int]


@dataclasses.dataclass(frozen=True)
class TciaSafePrivateRules:
    """TCIA's dictionary as safe private rules, for a run that chooses it.

    Attributes
    ----------
    pin : Pin
        Where the dictionary came from.
    rules : mapping of (str, int, int) to mapping of str to SafePrivateRule
        The rule of each attribute at the top level for each VR that its
        rows give, keyed by private creator, group, and element within the
        block, then by VR, in the file's order. Read-only.
    unwritten : mapping of (str, int, int) to SafePrivateRule
        The rule of each attribute whose VR is not written, where its rows
        give one VR other than OB, UN, or none. Read-only.
    """

    pin: Pin
    # Mappings are not hashable, so they are left out of the hash.
    rules: Mapping[_Key, Mapping[str, SafePrivateRule]] = dataclasses.field(hash=False)
    unwritten: Mapping[_Key, SafePrivateRule] = dataclasses.field(hash=False)

    def rule_for(
        self, group: int, private_creator: str, element: int, vr: str | None = None
    ) -> SafePrivateRule | None:
        """Return the rule for a private data element, or None if it has none.

        Parameters
        ----------
        group : int
            The element's group.
        private_creator : str
            The value of the private creator that reserves the element's
            block. Trailing spaces and NULs are padding; the comparison is
            otherwise exact, as for a reviewed rule.
        element : int
            The element within the block, ``0x00`` to ``0xFF``.
        vr : str, optional
            The element's VR as written, or None, the default, where it is
            not written, in Implicit VR or as UN.
        """
        key = (private_creator.rstrip(_CREATOR_PADDING), group, element)
        if vr is None:
            return self.unwritten.get(key)
        return self.rules.get(key, {}).get(vr)

    def retained(self) -> tuple[SafePrivateRule, ...]:
        """Return the rules that can retain a value, in the file's order."""
        return tuple(
            rule
            for by_vr in self.rules.values()
            for rule in by_vr.values()
            if rule.handling.retains
        )


def tcia_safe_private_rules(
    tags: TciaPrivateTags | None = None,
) -> TciaSafePrivateRules:
    """Return the rules that TCIA's dictionary gives, as the module describes.

    Parameters
    ----------
    tags : TciaPrivateTags, optional
        The dictionary. Defaults to the one shipped with PyMedPhys, whose
        rules are made once and cached.

    Raises
    ------
    TciaPrivateTagError
        If the shipped dictionary cannot be used, as
        :func:`load_tcia_private_tags` refuses it.
    ~pymedphys._dicom.deidentify.safe_private.SafePrivateRuleError
        If the reviewed rules cannot be loaded.
    """
    if tags is None:
        return _shipped_rules()
    return _rules(tags)


@functools.lru_cache(maxsize=None)
def _shipped_rules() -> TciaSafePrivateRules:
    return _rules(load_tcia_private_tags())


def _rules(tags: TciaPrivateTags) -> TciaSafePrivateRules:
    reviewed = load_safe_private_rules().rules
    rules: dict[_Key, Mapping[str, SafePrivateRule]] = {}
    unwritten: dict[_Key, SafePrivateRule] = {}
    # The parser keys top_level by the creator without its padding, so rows
    # for spellings that differ only by padding already share a key.
    for key, rows in tags.top_level.items():
        creator = key[0]
        if not creator or not set(creator) <= _CREATOR_CHARACTERS:
            continue
        by_vr: dict[str, SafePrivateRule] = {}
        for row in rows:
            if row.vr:
                rule = _rule(key, row, reviewed.get(key))
                # Rows that disagree about one VR keep nothing.
                if by_vr.get(row.vr, rule).handling is not rule.handling:
                    rule = dataclasses.replace(
                        rule, vm=_SINGLE_VALUE, handling=Handling.REMOVE
                    )
                by_vr[row.vr] = rule
        readable = [vr for vr in by_vr if vr not in _UNREAD_VRS]
        if by_vr:
            rules[key] = types.MappingProxyType(by_vr)
        if len(readable) == 1:
            unwritten[key] = by_vr[readable[0]]
    return TciaSafePrivateRules(
        pin=tags.pin,
        rules=types.MappingProxyType(rules),
        unwritten=types.MappingProxyType(unwritten),
    )


def _rule(
    key: _Key, row: TciaPrivateTag, reviewed: SafePrivateRule | None
) -> SafePrivateRule:
    """Return the rule that one row of the dictionary makes."""
    creator, group, element = key
    if not row.keeps:
        handling, vm = Handling.REMOVE, _SINGLE_VALUE
    elif reviewed is not None and reviewed.vr == row.vr:
        handling, vm = reviewed.handling, reviewed.vm
    else:
        handling, vm = default_handling(row.vr), _SINGLE_VALUE
    return SafePrivateRule(
        creator, group, element, row.vr, vm, handling, Basis.TCIA, note=row.name
    )
