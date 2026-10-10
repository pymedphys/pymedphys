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

"""Parse the Enumerated Values and Defined Terms of PS3.3's CS attributes.

PS3.3 gives an attribute's terms as a list titled "Enumerated Values:" or
"Defined Terms:", such as "Defined Terms for Value 3:" or "Retired Defined
Terms:", with each term in its own ``dt`` element. A list is in the
description of the attribute's row of a module or macro table, or in the
text of a section that the row's description refers to, such as Section
C.7.6.1.1.2 for Image Type (0008,0008); a row takes every list in such a
section. A list whose title names attributes by tag, as "Defined Terms for
Lossy Image Compression Method (0028,2114):" does, also gives the terms of
those attributes, and a list in a row gives that row's attribute only the
lists that name no other; tags after "if" or "when" in a title are
conditions, not the attributes it gives terms for.

Each term of an attribute is kept where the generated data dictionary gives
the attribute VR CS, its tag names one group and element rather than a
repeating group such as (60xx,0040), and the term is a value that VR CS can
hold: at most 16 upper-case letters, digits, spaces, and underscores. A list
in a row without exactly one tag is not kept, since its attribute is unknown.
"""

from __future__ import annotations

import collections
import dataclasses
import re
from collections.abc import Mapping
from html.parser import HTMLParser

from .chtml import TableFormatError

TERMS_LABEL = "Enumerated Values and Defined Terms"

_TAG = re.compile(r"\([0-9A-Fa-f]{4},[0-9A-Fa-f]{4}\)")
_ROW_TAG = re.compile(r"\([0-9A-Fa-fx]{4},[0-9A-Fa-fx]{4}\)")
_TERMS_TITLE = re.compile(
    r"(?:Retired )?(?:Value [0-9]+ )?(?:Enumerated Values|Defined Terms)\b", re.I
)
_CONDITION = re.compile(r"\b(?:if|when)\b", re.I)
_CS_VALUE = re.compile(r"[A-Z0-9 _]{1,16}")
_WHITESPACE = re.compile(r"\s+")


@dataclasses.dataclass
class _List:
    depth: int  # the number of open div elements outside it
    title: list[str] = dataclasses.field(default_factory=list)
    terms: list[str] = dataclasses.field(default_factory=list)
    in_title: bool = False
    in_term: list[str] | None = None


@dataclasses.dataclass
class _Row:
    cells: list[list[str]] = dataclasses.field(default_factory=list)
    terms: list[str] = dataclasses.field(default_factory=list)
    references: set[str] = dataclasses.field(default_factory=set)


class _TermsCollector(HTMLParser):
    """Collect each list of terms by the row, section, or tags it belongs to."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.section = ""
        self.rows: list[_Row | None] = []  # the open row of each open table
        self.divs = 0
        self.lists: list[_List] = []
        self.by_row: dict[str, set[str]] = collections.defaultdict(set)
        self.references: dict[str, set[str]] = collections.defaultdict(set)
        self.by_section: dict[str, set[str]] = collections.defaultdict(set)
        self.by_title: dict[str, set[str]] = collections.defaultdict(set)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        kind = attributes.get("class") or ""
        anchor = attributes.get("id") or ""
        href = attributes.get("href") or ""
        row = self.rows[-1] if self.rows else None
        if tag == "a" and anchor.startswith("sect_") and not self.rows:
            self.section = anchor.removeprefix("sect_")
        elif tag == "a" and kind == "xref" and href.startswith("#sect_") and row:
            row.references.add(href.removeprefix("#sect_"))
        elif tag == "table":
            self.rows.append(None)
        elif tag == "tr" and self.rows:
            self.rows[-1] = _Row()
        elif tag in ("td", "th") and row is not None:
            row.cells.append([])
        elif tag == "div":
            if kind == "variablelist":
                self.lists.append(_List(self.divs))
            self.divs += 1
        elif tag == "p" and kind == "title" and self.lists and not self.lists[-1].terms:
            self.lists[-1].in_title = True
        elif tag == "span" and kind == "term" and self.lists:
            self.lists[-1].in_term = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self.lists:
            self.lists[-1].in_title = False
        elif tag == "span" and self.lists and self.lists[-1].in_term is not None:
            current = self.lists[-1]
            current.terms.append(_text(current.in_term or []))
            current.in_term = None
        elif tag == "div":
            self.divs -= 1
            if self.lists and self.lists[-1].depth == self.divs:
                self._close(self.lists.pop())
        elif tag == "tr" and self.rows and self.rows[-1] is not None:
            row = self.rows[-1]
            self.rows[-1] = None
            tags = [
                text for cell in row.cells if _ROW_TAG.fullmatch(text := _text(cell))
            ]
            if len(tags) == 1:
                self.by_row[tags[0].upper()].update(row.terms)
                self.references[tags[0].upper()].update(row.references)
        elif tag == "table" and self.rows:
            self.rows.pop()

    def handle_data(self, data: str) -> None:
        if self.lists:
            current = self.lists[-1]
            if current.in_title:
                current.title.append(data)
            if current.in_term is not None:
                current.in_term.append(data)
        if self.rows and self.rows[-1] is not None and self.rows[-1].cells:
            self.rows[-1].cells[-1].append(data)

    def _close(self, closed: _List) -> None:
        title = _text(closed.title)
        if not _TERMS_TITLE.match(title):
            return
        named = _TAG.findall(_CONDITION.split(title, maxsplit=1)[0])
        row = self.rows[-1] if self.rows else None
        for each in named:
            self.by_title[each.upper()].update(closed.terms)
        if not self.rows:
            self.by_section[self.section].update(closed.terms)
        elif row is not None and not named:
            row.terms += closed.terms


def _text(parts: list[str]) -> str:
    return _WHITESPACE.sub(" ", "".join(parts)).strip()


def parse_terms(page: str, dictionary: Mapping[str, str]) -> list[dict[str, str]]:
    """Return each term of each CS attribute, as the module describes.

    Parameters
    ----------
    page : str
        PS3.3 on one page.
    dictionary : mapping of str to str
        The VR of each attribute of the generated data dictionary, by tag.

    Returns
    -------
    list of dict
        Each with the ``tag`` and a ``term``, in the order of the tags and
        then of the terms.

    Raises
    ------
    TableFormatError
        If the page gives no term of any CS attribute.
    """
    collector = _TermsCollector()
    collector.feed(page)
    collector.close()
    terms: dict[str, set[str]] = collections.defaultdict(set)
    for tag in {*collector.by_row, *collector.by_title}:
        terms[tag].update(
            collector.by_row.get(tag, ()), collector.by_title.get(tag, ())
        )
        for section in collector.references.get(tag, ()):
            terms[tag].update(collector.by_section.get(section, ()))
    rows = [
        {"tag": tag, "term": term}
        for tag in sorted(terms)
        if _TAG.fullmatch(tag) and dictionary.get(tag) == "CS"
        for term in sorted(terms[tag])
        if _CS_VALUE.fullmatch(term)
    ]
    if not rows:
        raise TableFormatError(f"PS3.3 gives no {TERMS_LABEL} of a CS attribute")
    return rows
